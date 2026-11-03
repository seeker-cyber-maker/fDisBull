"""Verify native responder and stored-state view adapters on the Snake corpus.

The adapter process receives programmatically constructed NSEvents. This checks
the production responder, palette and drawRect paths without claiming physical
hardware consumption or operating the GUI to capture screenshots.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import platform
import struct
import subprocess


CANONICAL_UIL = 'a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def same(actual, expected, label):
    if len(actual) != len(expected):
        raise AssertionError(f'{label}: length {len(actual)} != {len(expected)}')
    for index, (left, right) in enumerate(zip(actual, expected)):
        if left != right:
            raise AssertionError(f'{label}: element {index}: {left} != {right}')


def palette_rgba(indexed, palette):
    colors = {int(key): bytes([*color, 255]) for key, color in palette.items()}
    return b''.join(colors[value] for value in indexed)


def input_coverage(commands, keymap):
    """Derive deterministic coverage from commands actually sent to the app."""
    keys = Counter(command['code'] for command in commands if command['kind'] == 'key')
    pointers = [command for command in commands if command['kind'] == 'pointer']
    phases = Counter(command['phase'] for command in pointers)
    clocks = [command['clock'] for command in commands if command['kind'] == 'clock']
    return {'keyboard': {'commands': sum(keys.values()), 'declared_codes': sorted(keymap),
                'commands_by_code': dict(sorted(keys.items())),
                'unexercised_declared_codes': sorted(set(keymap) - keys.keys()),
                'modifiers_exercised': ['none']},
            'pointer': {'commands': len(pointers), 'commands_by_phase': dict(sorted(phases.items())),
                'button_numbers': sorted({command['button'] for command in pointers}),
                'coordinate_spaces': sorted({command['space'] for command in pointers})},
            'timer': {'commands': len(clocks), 'clock_values_in_order': clocks}}


def fitted_view(indexed, palette, source_width, source_height, width, height):
    """Independent pixel-center nearest-neighbor/letterbox adapter reference."""
    scale = min(width / source_width, height / source_height)
    game_width, game_height = source_width * scale, source_height * scale
    left, top = (width - game_width) / 2, (height - game_height) / 2
    rect = [left, top, game_width, game_height]
    colors = {int(key): bytes([*color, 255]) for key, color in palette.items()}
    black = bytes([0, 0, 0, 255])
    output = bytearray(width * height * 4)
    for y in range(height):
        py = y + .5
        for x in range(width):
            px = x + .5
            if left <= px < left + game_width and top <= py < top + game_height:
                ix = min(source_width - 1, math.floor((px - left) * source_width / game_width))
                iy = min(source_height - 1, math.floor((py - top) * source_height / game_height))
                color = colors[indexed[iy * source_width + ix]]
            else:
                color = black
            offset = (y * width + x) * 4
            output[offset:offset + 4] = color
    return bytes(output), rect


def verify_nearest_view(actual, expected, indexed, palette, source_width, source_height,
                        width, height, rect, label):
    """Check finite nearest-pixel and geometric edge-coverage tie sets.

    CoreGraphics is free to choose either equidistant nearest source pixel.
    Exactly on a geometric image edge, binary coverage may choose background
    black or a nearest in-bounds edge pixel. This drawing contract does not
    change the input adapter's half-open hit tests. No interpolated color,
    edge coverage blend or channel tolerance is allowed.
    """
    if len(actual) != len(expected):
        raise AssertionError(f'{label}: length {len(actual)} != {len(expected)}')
    scale = min(Fraction(width, source_width), Fraction(height, source_height))
    game_width, game_height = source_width * scale, source_height * scale
    left, top = (width - game_width) / 2, (height - game_height) / 2
    colors = {int(key): bytes([*color, 255]) for key, color in palette.items()}

    def coordinates(position, start, extent, count):
        value = (Fraction(2 * position + 1, 2) - start) * count / extent
        lower = math.floor(value)
        candidates = [min(count - 1, max(0, lower))]
        boundary = value.numerator
        if value.denominator == 1 and 0 < boundary < count:
            candidates = [boundary - 1, boundary]
        return candidates

    inside_x = [x for x in range(width) if left < Fraction(2 * x + 1, 2) < left + game_width]
    inside_y = [y for y in range(height) if top < Fraction(2 * y + 1, 2) < top + game_height]
    closed_x = [x for x in range(width) if left <= Fraction(2 * x + 1, 2) <= left + game_width]
    closed_y = [y for y in range(height) if top <= Fraction(2 * y + 1, 2) <= top + game_height]
    edges_x = [x for x in closed_x if Fraction(2 * x + 1, 2) in (left, left + game_width)]
    edges_y = [y for y in closed_y if Fraction(2 * y + 1, 2) in (top, top + game_height)]
    edge_pixels = {y * width + x for x in edges_x for y in closed_y}
    edge_pixels.update(y * width + x for y in edges_y for x in closed_x)
    tie_x = sum(len(coordinates(x, left, game_width, source_width)) == 2 for x in inside_x)
    tie_y = sum(len(coordinates(y, top, game_height, source_height)) == 2 for y in inside_y)
    tie_pixels = tie_x * len(inside_y) + tie_y * len(inside_x) - tie_x * tie_y
    differing_ties = 0
    edge_choices = {'background_only': 0, 'source_only': 0,
                    'source_and_background_indistinguishable': 0}
    differing_edges = 0
    black = bytes([0, 0, 0, 255])
    for offset in range(0, len(actual), 4):
        pixel = offset // 4
        x, y = pixel % width, pixel // width
        if pixel in edge_pixels:
            xs = coordinates(x, left, game_width, source_width)
            ys = coordinates(y, top, game_height, source_height)
            allowed_source = {colors[indexed[sy * source_width + sx]] for sx in xs for sy in ys}
            value = actual[offset:offset + 4]
            if value != black and value not in allowed_source:
                raise AssertionError(f'{label}: outer-edge tie pixel ({x},{y}): '
                    f'{list(value)} outside black-or-nearest-source edge set '
                    f'{sorted(map(list, allowed_source | {black}))}')
            edge_choices['source_and_background_indistinguishable' if value == black and black in allowed_source
                         else 'background_only' if value == black else 'source_only'] += 1
            differing_edges += value != expected[offset:offset + 4]
            continue
        if actual[offset:offset + 4] == expected[offset:offset + 4]:
            continue
        if not (left <= Fraction(2 * x + 1, 2) < left + game_width and
                top <= Fraction(2 * y + 1, 2) < top + game_height):
            raise AssertionError(f'{label}: letterbox pixel ({x},{y}): '
                f'{list(actual[offset:offset + 4])} != opaque black')
        xs = coordinates(x, left, game_width, source_width)
        ys = coordinates(y, top, game_height, source_height)
        allowed = {colors[indexed[sy * source_width + sx]] for sx in xs for sy in ys}
        if actual[offset:offset + 4] not in allowed:
            raise AssertionError(f'{label}: pixel ({x},{y}): '
                f'{list(actual[offset:offset + 4])} outside nearest source set '
                f'{sorted(map(list, allowed))}; source candidates x={xs}, y={ys}')
        differing_ties += 1
    return {'policy': 'Exact nearest source pixel; either neighbor only at an exact equidistant source-center tie; background black or nearest in-bounds source edge pixel only at an exact geometric pixel-center/image-edge tie; no interpolated colors or edge coverage blending; input hit tests remain half-open',
        'source_center_tie_pixels': tie_pixels, 'tie_pixels_different_from_floor_choice': differing_ties,
        'outer_edge_tie_pixels': len(edge_pixels), 'outer_edge_choices': edge_choices,
        'outer_edge_pixels_different_from_half_open_reference': differing_edges,
        'non_tie_or_letterbox_pixels': width * height - tie_pixels - len(edge_pixels),
        'non_tie_or_letterbox_differences': 0}


def verify(bundle, study_path, destination):
    bundle, study_path, destination = map(lambda p: Path(p).expanduser().resolve(),
                                         (bundle, study_path, destination))
    if destination.exists() or any((p / '.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('Choose a new private adapter output outside Git')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Actual native macOS ARM64 execution is required')
    manifest = json.loads((bundle / 'native-shell.json').read_text())
    study = json.loads(study_path.read_text())
    if (study['uil_sha256'] != CANONICAL_UIL or digest(manifest['program']) != CANONICAL_UIL or
            manifest['module_uil_sha256'] != CANONICAL_UIL):
        raise ValueError('Canonical source UIL differs')
    udl = digest({**manifest['program'], 'role': 'udl'})
    if manifest['module_udl_sha256'] != udl or udl != '986713c25859408dcefe33186b74eb249956934d71d69ad71797c787da9c56d1':
        raise ValueError('Canonical source UDL differs')
    relative = manifest.get('application')
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Native application is absent or outside the bundle')
    application = (bundle / relative).resolve(strict=True)
    if not application.is_relative_to(bundle):
        raise ValueError('Native application escapes the bundle')
    raw = application.read_bytes()
    if len(raw) < 32 or struct.unpack_from('<II', raw) != (0xfeedfacf, 0x0100000c):
        raise ValueError('Application is not a thin ARM64 Mach-O')
    expected_hash = manifest.get('artifacts', {}).get(relative)
    if expected_hash is None or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('Native application artifact identity differs')
    config_path = bundle / 'config.json'
    if file_hash(config_path) != manifest['runtime']['config_sha256']:
        raise ValueError('Native config identity differs')
    initial = json.loads((bundle / manifest.get('initial_file', 'initial.json')).read_text())
    words = list(initial)
    for name, value in study['initial_services'].items():
        words[study['layout']['state'][name]] = value
    controls = manifest['runtime']['region_controls']
    slot = next(index for index, control in enumerate(controls) if control['name'] == 'rng')
    variants = {value['name']: index for index, value in enumerate(controls[slot]['variants'])}
    if not {'original', 'lfsr16'} <= variants.keys():
        raise ValueError('Both RNG variants are required')
    plan = manifest['plan']
    frame = plan['frame']
    width, height = frame['width'], frame['height']
    clock = study['initial_services']['last_tick']
    destination.mkdir(parents=True, mode=0o700)
    summary = {'format': 'fdisbull-snake-appkit-qualification-1', 'status': 'passed',
        'verifier_sha256': file_hash(__file__),
        'module_uil_sha256': CANONICAL_UIL, 'application_sha256': expected_hash,
        'module_udl_sha256': udl,
        'config_sha256': file_hash(config_path), 'manifest_sha256': file_hash(bundle / 'native-shell.json'),
        'study_sha256': file_hash(study_path), 'arms': {},
        'scope': 'Programmatic NSEvents through the native window-key and production-view pointer responders, production timer path and controlled stored-state drawRect; no physical hardware or window hit-testing claim'}
    expected_views = {}
    try:
        for choice, rows in [('original', study['observations']),
                             ('lfsr16', study['rng']['alternate_observations'])]:
            commands = [
                {'kind': 'resize', 'width': width, 'height': height},
                {'kind': 'select', 'slot': slot, 'variant': variants[choice], 'clock': clock},
                {'kind': 'initialize', 'clock': clock},
            ]
            # These stored-state view checks introduce no game input or reset.
            for name, size in [('two-times', (width * 2, height * 2)),
                               ('wide', (800, 600)), ('tall', (600, 800))]:
                commands.extend([
                    {'kind': 'resize', 'width': size[0], 'height': size[1]},
                    {'kind': 'snapshot', 'id': 'view-' + name, 'capture_view': True},
                ])
            commands.append({'kind': 'resize', 'width': width, 'height': height})
            buttons, normalized_events, native_events, interventions = 0, 0, 0, 0
            for row in rows:
                intervention = row.get('intervention')
                if intervention:
                    if intervention['kind'] != 'declared-original-ram-state':
                        raise ValueError('Undeclared RAM intervention')
                    commands.append({'kind': 'replace', 'prefix_words': intervention['words']})
                    interventions += 1
                for event in row['events']:
                    kind = event['kind']
                    if kind == plan['events']['keyboard_kind']:
                        matches = [code for code, pair in plan['keymap'].items()
                                   if pair['ascii'] == event['ascii'] and pair['scan'] == event['scan']]
                        if len(matches) != 1:
                            raise ValueError('Original key has no unique declared physical adapter')
                        commands.append({'kind': 'key', 'code': matches[0], 'clock': event['clock']})
                        native_events += 1
                    elif kind == plan['events']['pointer_kind']:
                        current = event['buttons']
                        if current not in (0, 1) or buttons not in (0, 1):
                            raise ValueError('Frozen pointer corpus exceeds its declared left-button scope')
                        phase = 'down' if current and not buttons else 'up' if buttons and not current else 'drag' if current else 'move'
                        commands.append({'kind': 'pointer', 'phase': phase, 'button': 0,
                            'x': event['x'], 'y': event['y'], 'space': 'pixels', 'clock': event['clock']})
                        buttons = current
                        native_events += 1
                    elif kind == plan['events']['clock_kind']:
                        commands.append({'kind': 'clock', 'clock': event['clock']})
                    else:
                        raise ValueError('Unknown source event kind')
                    normalized_events += 1
                capture = {'kind': 'snapshot', 'id': row['id'], 'capture_frame': True, 'capture_view': True}
                if row['id'] in ('initial', 'ordinary-right-step-04', 'escape-quit-before-teardown'):
                    capture['frame_png'] = str(destination / (choice + '-' + row['id'] + '.png'))
                commands.append(capture)
            script = {'format': 'fdisbull-native-adapter-study-1', 'initial_clock': clock,
                'initial_words': words, 'initial_pointer': {'x': study['initial_services']['mouse_x'],
                    'y': study['initial_services']['mouse_y'], 'buttons': 0}, 'commands': commands}
            script_path = destination / (choice + '-script.json')
            result_path = destination / (choice + '-result.json')
            script_path.write_text(json.dumps(script, separators=(',', ':')) + '\n')
            command = [str(application), str(config_path), '--adapter-test', str(script_path), str(result_path)]
            try:
                execution = subprocess.run(command, capture_output=True, timeout=180, check=False)
            except subprocess.TimeoutExpired as error:
                (destination / (choice + '-stdout.log')).write_bytes(error.stdout or b'')
                (destination / (choice + '-stderr.log')).write_bytes(error.stderr or b'')
                raise AssertionError(f'{choice} native adapter timed out') from error
            (destination / (choice + '-stdout.log')).write_bytes(execution.stdout)
            (destination / (choice + '-stderr.log')).write_bytes(execution.stderr)
            if not result_path.exists():
                raise AssertionError(f'{choice} adapter produced no receipt: exit {execution.returncode}; {execution.stderr.decode(errors="replace")[:1200]}')
            actual = json.loads(result_path.read_text())
            if execution.returncode or actual['status'] != 'passed':
                raise AssertionError(f'{choice} adapter failed: {actual.get("error", execution.returncode)}')
            snapshots = {row['id']: row for row in actual['rows'] if 'id' in row}
            first = rows[0]
            first_pixels = base64.b64decode(study['raster_data'][first['frame']['sha256']])
            views = []
            for name, size in [('two-times', (width * 2, height * 2)),
                               ('wide', (800, 600)), ('tall', (600, 800))]:
                observed = snapshots['view-' + name]
                if observed['view_size'] != list(size):
                    raise AssertionError('Controlled view size differs')
                cache = (first['frame']['sha256'], *size)
                if cache not in expected_views:
                    expected_views[cache] = fitted_view(first_pixels, frame['palette'], width, height, *size)
                expected, rect = expected_views[cache]
                if any(abs(left - right) > 1e-7 for left, right in zip(observed['game_rect'], rect)):
                    raise AssertionError('Independent fitted game rectangle differs')
                view = base64.b64decode(observed['view_rgba_base64'])
                sampling = verify_nearest_view(view, expected, first_pixels, frame['palette'],
                    width, height, *size, rect, choice + ' ' + name + ' complete view RGBA')
                same(observed['words'][:621], first['expected_state'], 'View export must preserve game state')
                views.append({'name': name, 'size': list(size), 'game_rect': rect,
                    'rgba_sha256': hashlib.sha256(view).hexdigest(), 'sampling': sampling})
            observations = []
            for expected in rows:
                observed = snapshots[expected['id']]
                same(observed['words'][:len(expected['expected_state'])], expected['expected_state'], choice + ' ' + expected['id'] + ' state')
                indexed = bytes(observed['words'][frame['offset']:frame['offset'] + width * height])
                expected_pixels = base64.b64decode(study['raster_data'][expected['frame']['sha256']])
                same(indexed, expected_pixels, choice + ' ' + expected['id'] + ' indexed frame')
                rgba = palette_rgba(expected_pixels, frame['palette'])
                actual_frame = base64.b64decode(observed['frame_rgba_base64'])
                same(actual_frame, rgba, choice + ' ' + expected['id'] + ' palette RGBA')
                if observed['view_size'] != [width, height]:
                    raise AssertionError('Corpus view must use intrinsic dimensions')
                actual_view = base64.b64decode(observed['view_rgba_base64'])
                same(actual_view, rgba, choice + ' ' + expected['id'] + ' actual drawRect RGBA')
                if observed['closed'] != bool(expected['expected_state'][study['layout']['state']['quit_requested']]):
                    raise AssertionError('Native close boundary differs')
                if not observed['closed'] and observed['selected'][slot] != variants[choice]:
                    raise AssertionError('Native selector differs from chosen RNG')
                observations.append({'id': expected['id'],
                    'state_sha256': hashlib.sha256(struct.pack('<' + str(len(expected['expected_state'])) + 'I', *observed['words'][:len(expected['expected_state'])])).hexdigest(),
                    'indexed_sha256': hashlib.sha256(indexed).hexdigest(),
                    'frame_rgba_sha256': hashlib.sha256(actual_frame).hexdigest(),
                    'view_rgba_sha256': hashlib.sha256(actual_view).hexdigest()})
            summary['arms'][choice] = {'status': 'passed', 'observations': observations,
                'input_coverage': input_coverage(commands, plan['keymap']),
                'normalized_events': normalized_events, 'native_event_commands': native_events,
                'declared_ram_interventions': interventions, 'ordinary_answer_resets': 0,
                'view_checks': views, 'closed': snapshots[rows[-1]['id']]['closed'],
                'script_sha256': file_hash(script_path), 'raw_receipt_sha256': file_hash(result_path),
                'process_exit': execution.returncode, 'process_reaped': True}
    except Exception as error:
        summary.update(status='failed', error=str(error))
        (destination / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
        raise
    summary['checks'] = ['native-window-physical-keycode-mapping', 'production-view-pointer-mapping',
        'source-clock-events-through-timer-adapter', 'carried-state-without-answer-resets',
        'complete-indexed-palette-and-drawRect-output', 'nearest-neighbor-wide-tall-and-two-times-view-with-explicit-tie-set',
        'native-generator-selector-both-implementations', 'quit-capture-before-teardown']
    (destination / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('study', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    report = verify(args.bundle, args.study, args.destination)
    print(json.dumps({'status': report['status'], 'arms': {name: {
        'observations': len(arm['observations']), 'events': arm['normalized_events'],
        'native_events': arm['native_event_commands'], 'view_checks': len(arm['view_checks']),
        'closed': arm['closed']} for name, arm in report['arms'].items()}}))
