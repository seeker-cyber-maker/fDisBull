"""Qualify native ARM64 Snake logic/raster output against private DOS witnesses.

This runner uses the generated library's owned-state ABI. Logical word patches
qualify the native computation boundary; AppKit responder, view and physical
input claims require the separate adapter checks. Original and deliberately
different RNG expectations remain distinct.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import struct


SCALARS = ('snake_length', 'direction', 'pending_direction', 'paused',
           'game_status', 'score', 'rng_seed', 'tick_count', 'key_events',
           'mouse_events', 'frame_count', 'mouse_present', 'food_cell', 'turn_queued')
CANONICAL_UIL = 'a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(actual, expected, label):
    if len(actual) != len(expected):
        raise AssertionError(f'{label}: length {len(actual)} != {len(expected)}')
    for index, (left, right) in enumerate(zip(actual, expected)):
        if left != right:
            raise AssertionError(f'{label}: word {index}: {left} != {right}')


class NativeShell:
    """One synchronous owner on this Python main thread, matching AppKit."""
    def __init__(self, bundle, manifest):
        self.manifest = manifest
        library = bundle / manifest.get('library', 'memory-runtime.dylib')
        raw = library.read_bytes()
        if len(raw) < 32 or struct.unpack_from('<I', raw)[0] != 0xfeedfacf or struct.unpack_from('<I', raw, 4)[0] != 0x0100000c:
            raise ValueError('Native library must be a thin ARM64 Mach-O')
        self.library_sha256 = hashlib.sha256(raw).hexdigest()
        self.lib = ctypes.CDLL(str(library))
        self.count = manifest['program']['memory']['words']
        self.buffer_type = ctypes.c_uint32 * self.count
        self.pointer = ctypes.POINTER(ctypes.c_uint32)
        signatures = {
            'fdb_config_sha256': ([], ctypes.c_char_p),
            'fdb_word_count': ([], ctypes.c_size_t),
            'fdb_copy_words': ([self.pointer, ctypes.c_size_t], ctypes.c_int),
            'fdb_function_index': ([ctypes.c_char_p], ctypes.c_int),
            'fdb_call': ([ctypes.c_size_t, self.pointer, self.pointer, ctypes.c_size_t, ctypes.c_int], ctypes.c_int),
            'fdb_dispatch': ([self.pointer, self.pointer, ctypes.c_size_t, ctypes.c_int], ctypes.c_int),
            'fdb_initialize': ([ctypes.c_uint32], ctypes.c_int),
            'fdb_select_region': ([ctypes.c_size_t, ctypes.c_size_t], ctypes.c_int),
            'fdb_selected_region': ([ctypes.c_size_t], ctypes.c_int),
            'fdb_revision': ([], ctypes.c_uint64),
            'fdb_invocation_count': ([ctypes.c_size_t], ctypes.c_uint64),
            'fdb_region_invocation_count': ([ctypes.c_size_t, ctypes.c_size_t], ctypes.c_uint64),
            'fdb_last_steps': ([], ctypes.c_uint32),
            'fdb_last_error': ([], ctypes.c_char_p),
            'fdb_replace_words': ([self.pointer, ctypes.c_size_t], ctypes.c_int),
            'fdb_close': ([], None),
            'fdb_closed': ([], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes = arguments
            fn.restype = result
        self.config_sha256 = (self.lib.fdb_config_sha256() or b'').decode()
        if self.config_sha256 != manifest['runtime']['config_sha256']:
            raise ValueError('Native compiled config identity differs')
        if self.lib.fdb_word_count() != self.count:
            raise ValueError('Native arena length differs from canonical module')
        self.functions = {}
        for index, name in enumerate(manifest['runtime']['function_order']):
            actual = self.lib.fdb_function_index(name.encode())
            if actual != index:
                raise ValueError('Native function table differs from manifest')
            self.functions[name] = actual
        controls = manifest['runtime']['region_controls']
        self.region = next(index for index, control in enumerate(controls) if control['name'] == 'rng')
        self.variants = {variant['name']: index for index, variant in enumerate(controls[self.region]['variants'])}
        if not {'original', 'lfsr16'} <= self.variants.keys():
            raise ValueError('Both declared RNG variants are required')

    def require(self, code, label):
        if code:
            raw = self.lib.fdb_last_error()
            raise AssertionError(f'{label}: {raw.decode() if raw else "native refusal"}')

    def snapshot(self):
        words = self.buffer_type()
        self.require(self.lib.fdb_copy_words(words, self.count), 'snapshot')
        return list(words)

    def replace(self, words):
        self.require(self.lib.fdb_replace_words(self.buffer_type(*words), self.count), 'replacement')

    def choose(self, name):
        before = self.snapshot()
        self.require(self.lib.fdb_select_region(self.region, self.variants[name]), 'RNG selection')
        if self.lib.fdb_selected_region(self.region) != self.variants[name]:
            raise AssertionError('Selected RNG index differs')
        same(self.snapshot(), before, 'RNG selection must preserve game state')

    def counter(self, name):
        return int(self.lib.fdb_region_invocation_count(self.region, self.variants[name]))

    def call(self, function, patch=None, render=True):
        patch = patch or {}
        size = len(patch)
        indices = (ctypes.c_uint32 * max(1, size))(*patch.keys())
        values = (ctypes.c_uint32 * max(1, size))(*patch.values())
        if function == self.manifest['plan']['events']['function']:
            result = self.lib.fdb_dispatch(indices, values, size, int(render))
        else:
            result = self.lib.fdb_call(self.functions[function], indices, values, size, int(render))
        self.require(result, function)
        return self.snapshot()


def verify(bundle, study_path, destination):
    bundle, study_path, destination = map(lambda p: Path(p).expanduser().resolve(),
                                         (bundle, study_path, destination))
    if destination.exists() or any((p / '.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('Choose a new private verification destination outside Git')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Actual Apple ARM64 execution is required')
    manifest = json.loads((bundle / 'native-shell.json').read_text())
    study = json.loads(study_path.read_text())
    if (study['uil_sha256'] != CANONICAL_UIL or digest(manifest['program']) != study['uil_sha256'] or
            manifest['module_uil_sha256'] != study['uil_sha256']):
        raise ValueError('Canonical source UIL identity differs')
    destination.mkdir(parents=True, mode=0o700)
    initial = json.loads((bundle / manifest.get('initial_file', 'initial.json')).read_text())
    shell = NativeShell(bundle, manifest)
    state = study['layout']['state']
    frame = manifest['plan']['frame']
    result = {'format': 'fdisbull-snake-macos-computation-qualification-1',
        'status': 'passed', 'platform': platform.platform(), 'architecture': platform.machine(),
        'module_uil_sha256': study['uil_sha256'], 'library_sha256': shell.library_sha256,
        'config_sha256': shell.config_sha256,
        'manifest_sha256': file_hash(bundle / 'native-shell.json'), 'study_sha256': file_hash(study_path),
        'cases': {}, 'carried': {}, 'outcomes': {}, 'seed_probes': [], 'natural_switch': {},
        'scope': 'Native C ABI logical events and complete state/indexed rasters; AppKit input/view qualification is separate'}

    def source_initial():
        words = list(initial)
        for name, value in study['initial_services'].items():
            words[state[name]] = value
        return words

    def start(choice, clock):
        shell.choose(choice)
        shell.replace(source_initial())
        shell.require(shell.lib.fdb_initialize(clock), 'initialization')

    def event_patch(event):
        fields = manifest['plan']['events']
        return {fields[name]: event.get(name, 0) for name in ('kind', 'ascii', 'scan', 'x', 'y', 'buttons', 'clock')}

    def compare(words, row, label):
        same(words[:len(row['expected_state'])], row['expected_state'], label + ' state')
        actual = bytes(words[frame['offset']:frame['offset'] + frame['width'] * frame['height']])
        expected = base64.b64decode(study['raster_data'][row['frame']['sha256']])
        same(actual, expected, label + ' indexed raster')
        frame_hash = hashlib.sha256(actual).hexdigest()
        if frame_hash != row['frame']['sha256']:
            raise AssertionError(label + ' frame identity differs')
        return {'id': row['id'], 'state_sha256': hashlib.sha256(struct.pack('<' + str(len(row['expected_state'])) + 'I', *words[:len(row['expected_state'])])).hexdigest(),
                'frame_sha256': frame_hash}

    try:
        for choice, cases, expected_key in [('original', study['cases'], 'original'),
                                             ('lfsr16', study['rng']['cases'], 'alternate')]:
            shell.choose(choice)
            before = shell.counter(choice)
            hashes, changed = [], 0
            for item in cases:
                words = list(initial)
                words[:621] = [0] * 621
                cells = item['initial'].get('all_cells', item['initial']['cells'])
                words[:len(cells)] = cells
                for name in SCALARS:
                    words[state[name]] = item['initial'][name]
                shell.replace(words)
                actual = shell.call('step', render=False)
                expected = item[expected_key]
                same(actual[:600], expected['all_cells'], item['id'] + ' cells')
                for name in SCALARS:
                    if actual[state[name]] != expected[name]:
                        raise AssertionError(f"{choice} {item['id']} {name} differs")
                if choice == 'lfsr16' and expected['rng_seed'] != item['original']['rng_seed']:
                    changed += 1
                hashes.append(hashlib.sha256(struct.pack('<614I', *actual[:614])).hexdigest())
            result['cases'][choice] = {'cases': len(cases), 'mismatches': 0,
                'intentionally_changed_cases': changed, 'region_invocations': shell.counter(choice) - before,
                'projection_sha256': digest(hashes)}
            if choice == 'lfsr16' and changed != 84:
                raise AssertionError('Alternative negative control did not change the expected 84 cases')

        for choice, rows in [('original', study['observations']),
                             ('lfsr16', study['rng']['alternate_observations'])]:
            start(choice, study['initial_services']['last_tick'])
            before = shell.counter(choice)
            events, interventions, observations = 0, 0, []
            for row in rows:
                if row.get('intervention'):
                    if row['intervention']['kind'] != 'declared-original-ram-state':
                        raise ValueError('Undeclared diagnostic intervention')
                    words = shell.snapshot()
                    words[:len(row['intervention']['words'])] = row['intervention']['words']
                    shell.replace(words)
                    interventions += 1
                for event in row['events']:
                    shell.call(manifest['plan']['events']['function'], event_patch(event))
                    events += 1
                observations.append(compare(shell.snapshot(), row, choice + ' ' + row['id']))
            result['carried'][choice] = {'observations': observations, 'events': events,
                'declared_interventions': interventions, 'ordinary_answer_resets': 0,
                'region_invocations': shell.counter(choice) - before}

        for choice in ('original', 'lfsr16', 'hot_swap'):
            start('original' if choice == 'hot_swap' else choice, 100)
            before = {name: shell.counter(name) for name in ('original', 'lfsr16')}
            observations = []
            for number, row in enumerate(study['rng']['outcome'][choice], 1):
                if choice == 'hot_swap' and number == 5:
                    old = shell.snapshot()
                    if old[state['rng_seed']] != 10589 or old[state['food_cell']] != 389:
                        raise AssertionError('Natural first meal differs')
                    shell.choose('lfsr16')
                    result['natural_switch']['selection'] = {'after_step': 4, 'seed': old[state['rng_seed']],
                        'food': old[state['food_cell']], 'all_words_preserved': True}
                for event in row['events']:
                    shell.call(manifest['plan']['events']['function'], event_patch(event))
                words = shell.snapshot()
                observations.append({**compare(words, row, choice + ' ' + row['id']),
                    **{name: words[state[name]] for name in ('snake_length', 'score', 'rng_seed', 'food_cell', 'game_status')},
                    'head': words[0]})
            counts = {name: shell.counter(name) - before[name] for name in before}
            result['outcomes'][choice] = {'observations': observations, 'region_invocations': counts,
                'board_or_seed_interventions': 0}
            if choice == 'hot_swap':
                result['natural_switch'].update(status='passed', steps=len(observations),
                    after_second_meal=observations[22], region_invocations=counts)
                if observations[22]['rng_seed'] != 41134 or observations[22]['food_cell'] != 334 or counts != {'original': 1, 'lfsr16': 1}:
                    raise AssertionError('Natural switch did not consume the retained current seed')

        for choice in ('original', 'lfsr16'):
            shell.choose(choice)
            for row in study['rng']['transitions']:
                words = list(initial)
                words[state['rng_seed']] = row['before']
                shell.replace(words)
                before = shell.counter(choice)
                actual = shell.call('rng', render=False)
                expected = row['original_next' if choice == 'original' else 'alternate_next']
                if actual[state['rng_seed']] != expected or shell.counter(choice) != before + 1:
                    raise AssertionError('Direct seed provider or transition differs')
                actual[state['rng_seed']] = words[state['rng_seed']]
                same(actual, words, 'One-word RNG output footprint')
                result['seed_probes'].append({'choice': choice, 'before': row['before'], 'after': expected})

        before = shell.snapshot()
        revision = shell.lib.fdb_revision()
        immutable = (ctypes.c_uint32 * 1)(study['layout']['font'])
        value = (ctypes.c_uint32 * 1)(0)
        if shell.lib.fdb_call(shell.functions['step'], immutable, value, 1, 0) == 0:
            raise AssertionError('Undeclared input patch was accepted')
        same(shell.snapshot(), before, 'Invalid patch rollback')
        invalid = list(before)
        invalid[1] = invalid[0]
        if shell.lib.fdb_replace_words(shell.buffer_type(*invalid), shell.count) == 0:
            raise AssertionError('Duplicate/nonadjacent active body was accepted')
        same(shell.snapshot(), before, 'Invalid state replacement rollback')
        if shell.lib.fdb_revision() != revision:
            raise AssertionError('Refused admission changed the committed revision')
        result['guard_refusals'] = ['immutable-input-patch', 'invalid-active-body', 'unchanged-state-and-revision']

        result['checks'] = ['original-342-source-cases', 'alternative-342-intentional-cases',
            'original-and-alternative-carried-state-and-full-indexed-rasters',
            'original-and-alternative-outcome-route', 'natural-current-seed-switch',
            'one-word-seed-footprint', 'actual-region-invocation-counters']
        shell.lib.fdb_close()
        if not shell.lib.fdb_closed():
            raise AssertionError('Native owner did not close')
        result['closed'] = True
    except Exception as error:
        result.update(status='failed', error=str(error))
        (destination / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
        shell.lib.fdb_close()
        raise
    (destination / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('study', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    report = verify(args.bundle, args.study, args.destination)
    print(json.dumps({'status': report['status'], 'cases': report['cases'],
        'carried_observations': {name: len(arm['observations']) for name, arm in report['carried'].items()},
        'outcome_steps': {name: len(arm['observations']) for name, arm in report['outcomes'].items()},
        'natural_switch': report['natural_switch'], 'closed': report['closed']}))
