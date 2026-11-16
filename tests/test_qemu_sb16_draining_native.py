"""A real inactive SB16 voice drains saved mixer PCM after hot/cold restore.

Uses the main SB16 native test's explicit runtime selectors. Root alone launches
guests. The stopped state must actually be inactive-but-enabled; a completed,
already silent stream does not qualify this case.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_sb16_fixture import sb16_pcm
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_process_native import assert_completion, read_bytes
from test_qemu_sb16_native import (
    _assert_future, _device, _known_wave, _launch, _load, _runtime, _sample,
    _symbols, _word,
)


DRAIN_NS = 200_000_000


def _draining(debug):
    device = _device(debug)
    audio = debug.audio_observe()
    assert device['voice-present'] is True
    assert device['voice-active'] is False and device['dma-active'] is False
    assert device['aux-timer-pending'] is False
    # On this admitted one-voice graph, an inactive SW voice with its capture
    # source still enabled is the HW pending-disable/draining state.
    assert audio['native']['enabled'] is True, 'No inactive draining graph observed'
    return dict(device=device, audio=audio)


def _drain_future(project, debug, symbols, offsets, control, label):
    before = debug.clock_observe()
    budget_receipt(debug.clock_advance(DRAIN_NS, timeout_ms=10000), DRAIN_NS,
                   before=before)
    assert _word(debug, symbols, 'irq_count') == 1
    assert _word(debug, symbols, 'stage') == 2
    state = _sample(project, debug, symbols, offsets, label)
    assert state['device']['voice-active'] is False
    assert state['device']['dma-active'] is False
    assert debug.audio_observe()['native']['enabled'] is False
    prefix = bytes.fromhex(control['captured']['pcm_hex'])
    samples = bytes.fromhex(state['pcm_hex'])
    assert samples.startswith(prefix), 'Previously retained PCM changed'
    tail = samples[len(prefix):]
    assert tail and any(abs(value - 128) > 1 for value in tail), (
        'The saved inactive state did not emit remaining nonconstant source PCM')
    state['remaining_frames'] = len(tail)
    state['remaining_sha256'] = hashlib.sha256(tail).hexdigest()
    state['oracle'] = _known_wave(samples, offsets['rate'], channels=offsets['channels'])
    return state


def _compare_future(actual, expected):
    _assert_future(actual, expected)
    for key in ('remaining_frames', 'remaining_sha256'):
        assert actual[key] == expected[key], key
    assert actual['clock']['virtual_ns'] == expected['clock']['virtual_ns']


def _exit(debug):
    lease = debug.keyboard_key_down('q')['lease']
    debug.keyboard_key_up(lease)
    assert_completion(debug, debug.run(timeout_ms=5000), exit_code=42)


def _child_restore(path):
    control = json.loads(Path(path).read_text())
    runtime, directory = _runtime(), Path(control['directory'])
    disk = {'image': Path(control['disk'])}
    assert digest(disk['image']) == control['disk_sha256']
    assert digest(directory / 'SB16.COM') == control['source_sha256']
    result = dict(passed=False, pid=os.getpid())
    try:
        with Project(control['db']) as project:
            info = project.debug_state_info(control['saved']['artifact'])
            assert info['sha256'] == control['saved']['sha256']
            exported = directory / 'draining-child-checkpoint.state'
            project.debug_export(control['saved']['artifact'], exported)
            assert digest(exported) == control['saved']['sha256']
            with _launch(project, runtime, directory, disk) as debug:
                assert debug.run_id != control['origin_run']
                symbols, restored, initial = _load(
                    project, debug, control['offsets'], control, 'draining-child')
                draining = _draining(debug)
                future = _drain_future(project, debug, symbols, control['offsets'],
                                       control, 'draining-child-future')
                _compare_future(future, control['future'])
                result.update(restored=restored, initial=initial,
                              draining=draining, future=future)
                _exit(debug)
                owner = debug.vm.process
            assert owner.poll() is not None
        result['passed'] = True
    finally:
        result['disk_unchanged'] = digest(disk['image']) == control['disk_sha256']
        (directory / 'draining-child-result.json').write_text(
            json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=result['passed'], pid=os.getpid())))


def test_native_sb16_inactive_draining_checkpoint_hot_and_separate_process_cold(tmp_path):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(
        boot, tmp_path / 'draining-boot.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = sb16_pcm(tmp_path, runtime['NASM'], rate=8000,
                             guest_dma_service=True)
    source = tmp_path / 'SB16.COM'
    source.write_bytes(code)
    db = tmp_path / 'draining.fdb'
    control = dict(directory=str(tmp_path), db=str(db), disk=str(disk['image']),
        disk_sha256=disk['prepared_sha256'], source_sha256=digest(source), offsets=offsets)
    report = dict(format='fdisbull-authored-sb16-draining-native-1', success=False,
                  source_rate=8000, source_channels=1, future_ns=DRAIN_NS)
    try:
        with Project.create(db, source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['ready'])
                assert read_bytes(debug, symbols['reset_byte'], 3) == b'\xaa\x04\x05'
                debug.audio_start(max_frames=80000)
                park(debug, symbols['started'])
                # Stop on the first post-IRQ guest instruction, rather than
                # advancing a long clock budget beyond the draining frontier.
                park(debug, symbols['finished'])
                assert _word(debug, symbols, 'irq_count') == 1
                assert _word(debug, symbols, 'stage') == 2
                draining = _draining(debug)
                captured = _sample(project, debug, symbols, offsets, 'draining-captured')
                saved = debug.save_state('sb16-inactive-draining.state')
                control.update(saved=saved, captured=captured, origin_run=debug.run_id,
                               origin_epoch=debug.dos_process_info()['capture_epoch'])
                original = _drain_future(project, debug, symbols, offsets, control,
                                         'draining-original-future')
                control['future'] = original
                symbols, restored, initial = _load(
                    project, debug, offsets, control, 'draining-hot')
                hot_draining = _draining(debug)
                hot = _drain_future(project, debug, symbols, offsets, control,
                                    'draining-hot-future')
                _compare_future(hot, original)
                report.update(draining=draining, captured=captured, saved=saved,
                    original_future=original, hot_restore=restored, hot_initial=initial,
                    hot_draining=hot_draining, hot_future=hot)
                _exit(debug)
                owner = debug.vm.process
            assert owner.poll() is not None
        control_path = tmp_path / 'draining-child-control.json'
        control_path.write_text(json.dumps(control, indent=2, sort_keys=True) + '\n')
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), '--child-restore', str(control_path)],
            check=False, capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        (tmp_path / 'draining-child.log').write_text(child.stdout + child.stderr)
        assert child.returncode == 0, child.stdout + child.stderr
        child_result = json.loads((tmp_path / 'draining-child-result.json').read_text())
        assert child_result['passed'] and child_result['disk_unchanged']
        assert child_result['pid'] != os.getpid()
        report.update(child=child_result, success=True)
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash
        assert digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-sb16-draining.json').write_text(
            json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--child-restore':
        raise SystemExit('Use pytest, or the explicit child-restore route')
    _child_restore(sys.argv[2])
