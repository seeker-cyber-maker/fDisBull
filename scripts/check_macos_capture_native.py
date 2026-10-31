#!/usr/bin/env python3
"""EXPLICIT live acceptance using only a uniquely identified authored fixture.

Screenshots and journals remain private. This does not qualify original apps,
restore arbitrary apps, alter permissions, or test live SIGKILL recovery.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import signal
import struct
import subprocess
import time
import uuid

from fdisbull.macos_capture import NativeCapture
from fdisbull.macos_session import _private_path, run_session

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args, timeout=90):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout).stdout.strip()


def png_check(path, metadata):
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR', 'capture is not a PNG'
    assert struct.unpack('>II', data[16:24]) == (metadata['pixel_width'], metadata['pixel_height'])
    return {'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
            'pixel_width': metadata['pixel_width'], 'pixel_height': metadata['pixel_height'],
            'display_id': metadata['display']['id'], 'global_rect': metadata['global_rect'],
            'display_local_rect': metadata['display_local_rect']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New private directory outside Git; parent must exist')
    parser.add_argument('--swiftc', type=Path, help='Explicit Apple Swift compiler; otherwise resolve with xcrun')
    parser.add_argument('--sdk', type=Path, help='Explicit macOS SDK; otherwise resolve with xcrun')
    args = parser.parse_args()
    output = _private_path(args.output, new=True)
    bundle = 'local.fdisbull.capturefixture.' + uuid.uuid4().hex
    app = output / 'Fixture.app'
    report = {'kind': 'authored-macos-live-acceptance', 'status': 'failed', 'bundle_id': bundle,
              'captures': [], 'scope': 'authored fixture only; original apps and live SIGKILL recovery untested'}
    native, owned = None, None
    previous = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        assert platform.system() == 'Darwin', 'macOS is required'
        executable = app / 'Contents/MacOS/Fixture'
        executable.parent.mkdir(parents=True)
        info = {'CFBundleIdentifier': bundle, 'CFBundleExecutable': 'Fixture', 'CFBundlePackageType': 'APPL',
                'CFBundleName': 'fDisBull authored capture fixture', 'LSUIElement': True}
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        source = ROOT / 'tests/macos_capture_fixture.swift'
        compiler = str(args.swiftc or command('/usr/bin/xcrun', '--find', 'swiftc', timeout=10))
        sdk = str(args.sdk or command('/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path', timeout=10))
        command(compiler, '-parse-as-library', '-target', platform.machine() + '-apple-macosx14.0',
                '-sdk', sdk, str(source), '-o', str(executable), '-framework', 'AppKit')
        native = NativeCapture(timeout=5)
        report.update(fixture_source_sha256=sha(source), fixture_binary_sha256=sha(executable), native=native.identity)
        command('/usr/bin/open', '-gj', str(app), timeout=10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            before = native('snapshot', bundle_id=bundle)
            target, items = before['target'], before.get('status_items', [])
            if target.get('running') and target.get('launch_date'):
                # LaunchServices can canonicalize case on case-insensitive APFS.
                assert os.path.samefile(target['bundle_path'], app), 'fixture bundle identity mismatch'
                assert sha(Path(target['bundle_path'])/'Contents/MacOS/Fixture') == report['fixture_binary_sha256']
                owned = {'pid': target['pid'], 'expected_launch_date': target['launch_date']}
                if items and before['menu']['open'] is False:
                    break
            time.sleep(0.2)
        else:
            raise RuntimeError('authored fixture did not expose a PID/launch date/status item within the launch budget')
        assert len(items) == 1, 'fixture status item must be unambiguous'
        frame = items[0]['global_frame']
        displays = before['displays']
        display = next(d for d in displays if d['global_bounds']['x'] <= frame['x'] + frame['width']/2 < d['global_bounds']['x'] + d['global_bounds']['width']
                       and d['global_bounds']['y'] <= frame['y'] + frame['height']/2 < d['global_bounds']['y'] + d['global_bounds']['height'])
        bounds = display['global_bounds']
        width, height = min(320, bounds['width']), min(200, bounds['height'])
        rect = {'x': max(bounds['x'], min(frame['x'], bounds['x'] + bounds['width'] - width)),
                'y': bounds['y'], 'width': width, 'height': height}
        value = base64.b64encode(plistlib.dumps({'value': '日本語'}, fmt=plistlib.FMT_BINARY)).decode()
        key = 'fdisbullAcceptanceTransientLanguage'
        receipt = run_session(bundle_id=bundle, output=output/'session', native=native, live=True,
                              status_index=items[0]['index'], display_id=display['id'], rect=rect,
                              keys=[key], preference_changes={key: value})
        assert receipt['status'] == 'confirmed' and receipt['cleanup']['status'] == 'confirmed', receipt
        journal = json.loads((output/'session/journal.json').read_text())
        assert journal['changes'][0]['before']['present'] is False
        assert journal['changes'][0]['expected']['value_base64'] == value
        actions = {name: journal[name] for name in ('menu_open_result', 'menu_close_result')}
        assert all('delivery' in action and action['observed_effect']['status'] == 'confirmed' for action in actions.values())
        after = native('snapshot', bundle_id=bundle, **owned)
        assert after['menu']['open'] is False
        assert native('prefs_get', bundle_id=bundle, keys=[key])['preferences'][key]['present'] is False
        metadata = json.loads((output/'session/capture.json').read_text())
        report['captures'].append(png_check(output/'session/capture.png', metadata))
        report['menu_actions'] = {name: {'delivery': action['delivery'], 'observed_effect': action['observed_effect']} for name, action in actions.items()}
        for display in displays:
            bounds = display['global_bounds']
            rect = {'x': bounds['x'] + min(10, bounds['width']/4), 'y': bounds['y'] + min(40, bounds['height']/4),
                    'width': min(64, bounds['width']/2), 'height': min(48, bounds['height']/2)}
            image = output / ('display-' + str(display['id']) + '.png')
            capture = native('capture', display_id=display['id'], rect=rect, output=str(image))
            assert capture['global_rect'] == rect
            assert capture['display_local_rect']['x'] == rect['x'] - bounds['x']
            assert capture['display_local_rect']['y'] == rect['y'] - bounds['y']
            assert capture['pixel_width'] == round(rect['width'] * display['scale_x'])
            assert capture['pixel_height'] == round(rect['height'] * display['scale_y'])
            report['captures'].append(png_check(image, capture))
        report.update(status='passed', display_count=len(displays), preference_absence_restored=True, menu_closed=True)
    except Exception as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)[:2000]}
    finally:
        report['fixture_termination'] = 'not_launched_or_identity_unconfirmed'
        if native is not None and owned is not None:
            try:
                native('snapshot', bundle_id=bundle, **owned)
                os.kill(owned['pid'], signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if not native('snapshot', bundle_id=bundle)['target']['running']:
                        report['fixture_termination'] = 'confirmed'
                        break
                    time.sleep(0.2)
                else:
                    raise RuntimeError('owned fixture termination was not observed')
            except Exception as exc:
                report['fixture_termination'] = {'status': 'unresolved', 'reason': str(exc)[:1024]}
                report['status'] = 'failed'
        signal.signal(signal.SIGTERM, previous)
        (output/'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' and report['fixture_termination'] == 'confirmed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
