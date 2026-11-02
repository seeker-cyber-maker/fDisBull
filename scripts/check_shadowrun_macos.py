#!/usr/bin/env python3
"""Compare complete native arena state with independent GameMachine contexts.

Native libraries are generated separately for the two assisted seeds. The
original snapshots are comparison evidence, never inputs to either runtime.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom

EXPECTED = 'bed27370cb4625331b9c2de870a48acfff8f4c91d5630d24d2d1c8874fcf7227'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Native:
    def __init__(self, path, rom):
        self.lib = ctypes.CDLL(str(path))
        l = self.lib
        l.fdisbull_create.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        l.fdisbull_create.restype = ctypes.c_int
        l.fdisbull_destroy.argtypes = [ctypes.c_void_p]
        l.fdisbull_reset.argtypes = [ctypes.c_void_p]; l.fdisbull_reset.restype = ctypes.c_int
        l.fdisbull_step.argtypes = [ctypes.c_void_p, ctypes.c_uint8]; l.fdisbull_step.restype = ctypes.c_int
        l.fdisbull_state_get.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_int64)]
        l.fdisbull_state_get.restype = ctypes.c_int
        l.fdisbull_state_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int64]
        l.fdisbull_state_set.restype = ctypes.c_int
        self.ctx = ctypes.c_void_p()
        if l.fdisbull_create(str(rom).encode(), ctypes.byref(self.ctx)) != 0 or not self.ctx.value:
            raise ValueError('native create failed')

    def close(self):
        if self.ctx:
            self.lib.fdisbull_destroy(self.ctx); self.ctx = ctypes.c_void_p()

    def compare(self, expected, label):
        count = 0
        for name, value in expected.items():
            values = value if isinstance(value, list) else [value]
            key = name.encode()
            for index, item in enumerate(values):
                actual = ctypes.c_int64()
                rc = self.lib.fdisbull_state_get(self.ctx, key, index, ctypes.byref(actual))
                if rc or actual.value != item:
                    raise AssertionError((label, name, index, item, actual.value, rc))
                count += 1
        return count

    def step(self, pad):
        return self.lib.fdisbull_step(self.ctx, pad)


def main():
    parser = argparse.ArgumentParser()
    for name in ('rom', 'capture', 'moving-library', 'stationary-library', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--moving-original', required=True, type=Path)
    parser.add_argument('--moving-extension', required=True, type=Path)
    parser.add_argument('--stationary-original', required=True, type=Path)
    parser.add_argument('--terminal-original', required=True, type=Path)
    parser.add_argument('--held-original', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(mode=0o700, parents=True)
    watched = [Path(__file__).resolve(), ROOT / 'src/fdisbull/udc_macos.py',
               ROOT / 'src/fdisbull/shadowrun_assisted_arena.py',
               args.stationary_library, args.moving_library]
    watched_hashes = {str(path): sha(path.read_bytes()) for path in watched}
    rom = _read_rom(args.rom)
    base = assisted_arena_from_capture(rom, args.capture)
    moving = assisted_arena_from_capture(rom, args.capture, moving=True)
    if sha(canonical(base.program)) != EXPECTED or sha(canonical(moving.program)) != EXPECTED:
        raise ValueError('unexpected shared GameIL program')
    build_receipts = {}
    for label, lib, machine in (('stationary', args.stationary_library, base),
                                 ('moving', args.moving_library, moving)):
        receipt_path = lib.parent / 'receipt.json'
        raw = receipt_path.read_bytes(); build = json.loads(raw)
        seed = json.dumps(machine.snapshot(), sort_keys=True, separators=(',', ':')).encode()
        if (build['program_sha256'] != EXPECTED or build['dylib_sha256'] != sha(lib.read_bytes()) or
            build['seed_sha256'] != sha(seed) or build['architecture'] != 'arm64' or
            build['source_sha256'] != sha((lib.parent / 'fdisbull_native.c').read_bytes()) or
            build['header_sha256'] != sha((lib.parent / 'fdisbull_native.h').read_bytes())):
            raise ValueError(f'{label} native build receipt mismatch')
        build_receipts[label] = sha(raw)
    source = {}
    reviewed = {'moving': '731cb1ec2f51c207d3acaf3443a4de0c231bd4db9922a9b7f0c57a6333858ff6',
                'extension': '68d87f40204f975f293479dcea72249ad045fc10a583401d901bddbca1111d6b',
                'stationary': 'b40dd5e704b7bba2c3c746a10473f120978f884e9528573da966c2245b4e8510',
                'terminal': 'a1c969d5c64b651e9be1fb53bc840b60c223d7ef30eb2b3defadeadfc31a982f',
                'held': '3e8ea721088dfaea695ead43633f2a21b98a6bfecab46594e0d50be8c9cca32a'}
    reviewed_capture = {'moving': '2a3b93a30be1655f51020703fa43b610109be60e2ba223d861b47a77b5e193d3',
                        'extension': 'ec431d99312caa71ce97930bad4fb7268af711a327f77d584823ab3ca535337b',
                        'stationary': '848cc21f3dc8bbfeac991b6af9a7b73ad21ba362a2f709db33c1d9e94b3e1f95',
                        'terminal': '626f509e1ea1018955e2d0c2f7d76f625d6c8c277e482022a5b30890df974b1f',
                        'held': 'a4b1f40b59b3c3d035e96b6e079ec038e8bc8967a67d0a8acd8a18dcd5743563'}
    for label, root in (('moving', args.moving_original), ('extension', args.moving_extension),
                        ('stationary', args.stationary_original), ('terminal', args.terminal_original),
                        ('held', args.held_original)):
        if sha((root / 'native/receipt.json').read_bytes()) != reviewed[label]:
            raise ValueError(f'unreviewed {label} capture')
        capture_raw = (root / 'capture.json').read_bytes()
        if sha(capture_raw) != reviewed_capture[label]:
            raise ValueError(f'changed {label} capture manifest')
        source[label] = (root, json.loads(capture_raw))
    def original(label, frame, state):
        root, cap = source[label]
        key = f'native/scene-{frame:06d}/ram.bin'
        if key not in cap['files']:
            return False
        raw = (root / key).read_bytes()
        if len(raw) != 65536 or sha(raw) != cap['files'][key]['sha256']:
            raise ValueError('original capture changed')
        b = bytes(raw[i ^ 1] for i in range(len(raw)))
        fields = (('shadowrun_player_x', 0x100, 2), ('shadowrun_player_y', 0x104, 2),
                  ('shadowrun_arena_hp', 0x14c, 1), ('shadowrun_hostile_x', 0x400, 2),
                  ('shadowrun_hostile_y', 0x404, 2), ('shadowrun_hostile_ammo', 0x44e, 1),
                  ('shadowrun_hostile_rng', 0xf9f8, 2))
        for name, offset, size in fields:
            expected = int.from_bytes(b[offset:offset + size], 'big')
            if state[name] != expected:
                raise AssertionError(('original', label, frame, name, state[name], expected))
        return True

    results = {}; native_objects = []
    def instance(library):
        start = time.perf_counter_ns(); n = Native(library, args.rom)
        elapsed = time.perf_counter_ns() - start; native_objects.append(n)
        return n, elapsed
    def trace(label, library, machine, pads, source_for_frame):
        native, setup_ns = instance(library)
        initial = machine.snapshot(); elements = native.compare(initial, label + ':initial')
        source_matches = completed = 0; refusal = False
        for index, pad in enumerate(pads):
            before = machine.snapshot()
            machine.call('shadowrun_arena_frame', pad)
            after = machine.snapshot(); rc = native.step(pad)
            if after['shadowrun_arena_frame_status'] == 2:
                if rc != 1:
                    raise AssertionError((label, index, 'expected transactional refusal', rc))
                native.compare(before, label + ':rollback'); refusal = True; break
            if rc:
                raise AssertionError((label, index, 'native fault', rc))
            native.compare(after, label + ':' + str(index)); completed += 1
            kind = source_for_frame(index)
            if kind and original(kind, 6000 + index, after):
                source_matches += 1
        results[label] = {'completed_ticks': completed, 'full_state_elements_per_tick': elements,
                          'original_snapshots_compared': source_matches, 'setup_ns': setup_ns,
                          'transactional_refusal_checked': refusal}
        return native, machine
    try:
        stationary, terminal = trace('stationary_terminal', args.stationary_library, base,
                                     [0] * 243, lambda i: 'terminal' if i >= 209 else 'stationary')
        if terminal.snapshot()['shadowrun_arena_hp'] != 0 or terminal.snapshot()['shadowrun_arena_frame_status'] != 3:
            raise AssertionError('terminal boundary not reached')
        terminal_before = terminal.snapshot()
        terminal.call('shadowrun_arena_frame', 0)
        if stationary.step(0):
            raise AssertionError('terminal hold failed')
        stationary.compare(terminal.snapshot(), 'terminal hold')
        if terminal.snapshot() != terminal_before:
            raise AssertionError('terminal state changed')
        if stationary.lib.fdisbull_reset(stationary.ctx) != 0:
            raise AssertionError('reset failed')
        seed = assisted_arena_from_capture(rom, args.capture).snapshot()
        stationary.compare(seed, 'reset')
        move, _ = trace('moving', args.moving_library, moving,
                        [0] + [4] * 40 + [0] * 84,
                        lambda i: 'moving' if i < 50 else 'extension')
        if not results['moving']['transactional_refusal_checked']:
            raise AssertionError('moving unsupported boundary not reached')
        held, held_model = trace('held_fire', args.stationary_library,
                        assisted_arena_from_capture(rom, args.capture),
                        [0] * 13 + [64] * 67, lambda i: 'held')
        if (results['stationary_terminal']['original_snapshots_compared'] < 97 or
            results['moving']['original_snapshots_compared'] < 103 or
            results['held_fire']['original_snapshots_compared'] < 15):
            raise AssertionError('missing reviewed original checkpoints')
        for name in (b'not_a_global',):
            out = ctypes.c_int64()
            if held.lib.fdisbull_state_get(held.ctx, name, 0, ctypes.byref(out)) != 1:
                raise AssertionError('unknown global accepted')
        out = ctypes.c_int64()
        if held.lib.fdisbull_state_get(held.ctx, b'shadowrun_arena_hp', 1, ctypes.byref(out)) != 1:
            raise AssertionError('invalid scalar index accepted')
        absent = ctypes.c_void_p()
        if held.lib.fdisbull_create(b'/nonexistent/fdisbull-rom', ctypes.byref(absent)) != 1 or absent.value:
            raise AssertionError('invalid ROM accepted')
        for name, length in (('bad-size.bin', 3), ('bad-hash.bin', len(rom))):
            path = args.output / name
            path.write_bytes(bytes(length))
            absent = ctypes.c_void_p()
            if held.lib.fdisbull_create(str(path).encode(), ctypes.byref(absent)) != 1 or absent.value:
                raise AssertionError('invalid ROM accepted: ' + name)
        if held.lib.fdisbull_step(None, 0) != 1 or held.lib.fdisbull_reset(None) != 1:
            raise AssertionError('null context accepted')
        if held.lib.fdisbull_state_set(held.ctx, b'not_a_global', 0, 1) != 1 or \
           held.lib.fdisbull_state_set(held.ctx, b'shadowrun_arena_hp', 1, 1) != 1:
            raise AssertionError('invalid state write accepted')
        held.compare(held_model.snapshot(), 'invalid state write rollback')
        # Separate contexts must not share mutable model state.
        a, _ = instance(args.stationary_library); b, _ = instance(args.stationary_library)
        m1 = assisted_arena_from_capture(rom, args.capture); m2 = assisted_arena_from_capture(rom, args.capture)
        for value in (257, -1):
            if a.lib.fdisbull_state_set(a.ctx, b'shadowrun_arena_hp', 0, value):
                raise AssertionError('typed state write failed')
            m1.set_state({'shadowrun_arena_hp': value})
            a.compare(m1.snapshot(), 'typed state casting')
        if a.lib.fdisbull_reset(a.ctx): raise AssertionError('reset after diagnostic failed')
        m1 = assisted_arena_from_capture(rom, args.capture)
        for x, y in zip([0]*15, [0]*13+[64]*2):
            m1.call('shadowrun_arena_frame', x); m2.call('shadowrun_arena_frame', y)
            if a.step(x) or b.step(y): raise AssertionError('concurrent context refused')
            a.compare(m1.snapshot(), 'context-a'); b.compare(m2.snapshot(), 'context-b')
        # Equal completed budgets, no unsupported continuation; excludes GUI rendering.
        timings = []
        for _ in range(10):
            if a.lib.fdisbull_reset(a.ctx): raise AssertionError('benchmark reset failed')
            start = time.perf_counter_ns()
            for _ in range(60):
                if a.step(0): raise AssertionError('benchmark did not complete its budget')
            timings.append(time.perf_counter_ns() - start)
        results['benchmark'] = {'repeats': len(timings), 'completed_ticks_per_repeat': 60,
                                'total_ns_each': timings,
                                'median_repeat_mean_ns_per_tick': statistics.median(timings)/60,
                                'slowest_repeat_mean_ns_per_tick': max(timings)/60,
                                'scope': 'native update calls including ctypes overhead, excluding rendering and setup'}
        results['invalid_name_index_rom_null_and_typed_casting'] = 'passed'
        results['interleaved_contexts_ticks_each'] = 15
    finally:
        for n in native_objects: n.close()
    if watched_hashes != {str(path): sha(path.read_bytes()) for path in watched}:
        raise ValueError('checker, native emitter, model, or library changed during qualification')
    report = {'status': 'passed', 'program_sha256': EXPECTED,
              'native_libraries_sha256': {'stationary': sha(args.stationary_library.read_bytes()),
                                          'moving': sha(args.moving_library.read_bytes())},
              'checker_sha256': watched_hashes[str(Path(__file__).resolve())],
              'native_emitter_sha256': watched_hashes[str(ROOT / 'src/fdisbull/udc_macos.py')],
              'native_build_receipt_sha256': build_receipts,
              'original_receipt_sha256': reviewed,
              'original_capture_sha256': reviewed_capture,
              'results': results,
              'limits': ['assisted, bounded source-constructed arena', 'original snapshots compare a named projection only',
                         'timing is conditional on the measured machine and completed budgets',
                         'rendering, audio, natural encounter and general game parity are not established']}
    path = args.output / 'summary.json'; path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'summary_sha256': sha(path.read_bytes()), 'results': results}))

if __name__ == '__main__':
    main()
