#!/usr/bin/env python3
"""Qualify bounded authored console programs against independent Libretro cores."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import write_console_rom
from fdisbull.interaction_il import execute_il, validate_il
from fdisbull.udl_genesis import lift


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def marker():
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
            'variables': {'$x': {'type': 'u8', 'initial': 8}, '$ticks': {'type': 'u16', 'initial': 0}, '$buttons': {'type': 'u8', 'initial': 0}},
            'body': [{'id': 'right', 'op': 'if', 'condition': {'op': 'bit_test', 'value': {'var': '$buttons'}, 'bit': 0}, 'then': [{'id': 'inc', 'op': 'add', 'var': '$x', 'value': 1}], 'else': []},
                     {'id': 'left', 'op': 'if', 'condition': {'op': 'bit_test', 'value': {'var': '$buttons'}, 'bit': 1}, 'then': [{'id': 'dec', 'op': 'subtract', 'var': '$x', 'value': 1}], 'else': []},
                     {'id': 'tick', 'op': 'add', 'var': '$ticks', 'value': 1}]}


def route_program():
    return {'format': 'fdisbull-il-1', 'role': 'uil', 'resources': {},
            'variables': {'$x': {'type': 'u8', 'initial': 250}, '$ticks': {'type': 'u16', 'initial': 65534}, '$copy': {'type': 'u16', 'initial': 0}},
            'body': [{'id': 'x', 'op': 'add', 'var': '$x', 'value': 1}, {'id': 'ticks', 'op': 'add', 'var': '$ticks', 'value': 1}, {'id': 'copy', 'op': 'set', 'var': '$copy', 'value': {'var': '$ticks'}}, {'id': 'sub', 'op': 'subtract', 'var': '$copy', 'value': 1}]}


def get_value(raw, offset, width, target):
    data = bytes(raw[(offset + i) ^ (1 if target == 'genesis' else 0)] for i in range(width // 8))
    return int.from_bytes(data, 'big' if target == 'genesis' else 'little')


def run_case(root, name, target, program, core, frames, expected=None):
    folder = root / name / target
    folder.mkdir(parents=True)
    package = folder / 'package'
    display = '$x' if '$x' in program['variables'] and program['variables']['$x']['type'] == 'u8' else None
    started = time.perf_counter()
    manifest = write_console_rom(program, target=target, output=package, display_variable=display)
    compile_write_seconds = time.perf_counter() - started
    layout = manifest['variables']
    base = 0 if target == 'nes' else 0xff0000
    first = min(v['address'] - base for v in layout.values()) & ~1
    end = (max(v['address'] - base + v['width'] // 8 for v in layout.values()) + 1) & ~1
    counter = manifest['symbols']['runtime_frame_counter'] - base
    slices = [{'name': 'vars', 'offset': first, 'length': end-first}, {'name': 'control', 'offset': counter, 'length': 4}]
    watch = folder / 'watch.json'
    watch.write_text(json.dumps(slices))
    inputs = ([{'start': 20, 'end': 40, 'buttons': ['RIGHT']}, {'start': 50, 'end': 70, 'buttons': ['LEFT']}, {'start': 80, 'end': 100, 'buttons': ['A']}, {'start': 110, 'end': 130, 'buttons': ['B', 'UP']}, {'start': 140, 'end': 150, 'buttons': ['RIGHT', 'A', 'START']}]
              if '$buttons' in layout and frames >= 150 else [])
    input_file = folder / 'inputs.json'
    input_file.write_text(json.dumps(inputs))
    rom_path = package / ('program.nes' if target == 'nes' else 'program.md')
    command = [sys.executable, str(ROOT / 'scripts/check_console_udc.py'), '--core', str(core), '--rom', str(rom_path), '--system', target, '--frames', str(frames), '--inputs', str(input_file), '--watch', str(watch), '--output', str(folder / 'run')]
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=90)
    native_subprocess_seconds = time.perf_counter() - started
    if proc.returncode:
        raise RuntimeError(f'{name}/{target} host failed: {proc.stderr[-2000:]}')
    receipt = json.loads((folder / 'run/receipt.json').read_text())
    trace = json.loads((folder / 'run/ram_trace.json').read_text())
    state = {key: value['initial'] for key, value in program['variables'].items()}
    prev, checked, ready_frame, initial_ready_count = 0, 0, None, None
    for frame in trace['frames']:
        control = bytes.fromhex(frame['raw']['control'])
        ready = get_value(control, 2, 16, target)
        if ready != 0xa55a:
            if ready_frame is not None:
                raise AssertionError(f'{name}/{target}: ready marker disappeared at frame {frame["frame"]}')
            continue
        count = get_value(control, 0, 16, target)
        if ready_frame is None:
            ready_frame = frame['frame']
            initial_ready_count = count
        delta = (count - prev) & 0xffff
        if delta not in (0, 1):
            raise AssertionError(f'{name}/{target}: counter jumped {prev} to {count} at frame {frame["frame"]}')
        if not delta:
            if checked:
                raise AssertionError(f'{name}/{target}: counter did not advance after first tick at frame {frame["frame"]} (count {count})')
            continue
        mask = frame['input_mask']
        if '$buttons' in state:
            mapping = receipt['input_map']
            state['$buttons'] = sum(bit for key, bit in [('RIGHT', 1), ('LEFT', 2), ('UP', 4), ('DOWN', 8), ('A', 16), ('B', 32), ('START', 64), ('SELECT', 128)] if key in mapping and mask & (1 << mapping[key]))
        result = execute_il(program, state)
        if not result['complete']:
            raise AssertionError(f'{name}/{target}: UIL reference did not complete: {result}')
        state = result['state']
        data = bytes.fromhex(frame['raw']['vars'])
        actual = {key: get_value(data, v['address'] - base - first, v['width'], target) for key, v in layout.items()}
        if actual != state:
            raise AssertionError(f'{name}/{target}: first divergence frame={frame["frame"]} tick={count} input_mask={mask} expected={state} observed={actual}')
        if expected and checked < len(expected) and state != expected[checked]:
            raise AssertionError(f'{name}/{target}: differs from independently authored expected tick {checked+1}: {state}')
        checked += 1
        prev = count
    if ready_frame is None or checked < 3:
        raise AssertionError(f'{name}/{target}: insufficient completed ticks ({checked})')
    return {'target': target, 'program_sha256': manifest['program_sha256'], 'rom_sha256': manifest['rom_sha256'], 'core_sha256': receipt['core_sha256'], 'core_name': receipt['core_name'], 'core_version': receipt['core_version'], 'trace_sha256': receipt['ram_trace_sha256'], 'frame_sha256': receipt['frame_rgb_sha256'], 'ready_frame': ready_frame, 'initial_ready_count': initial_ready_count, 'checked_ticks': checked, 'compile_write_seconds': compile_write_seconds, 'native_subprocess_seconds': native_subprocess_seconds, 'emulator_fps': receipt['fps'], 'emulator_frames': receipt['frames'], 'compiler_profile': manifest['profile'], 'final_state': state, 'inputs': inputs, 'variables': layout}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True)
    ap.add_argument('--nes-core', required=True)
    ap.add_argument('--genesis-core', required=True)
    ap.add_argument('--frames', type=int, default=180)
    args = ap.parse_args()
    if not 150 <= args.frames <= 600:
        ap.error('frames must be 150..600')
    nes_sha = hashlib.sha256(Path(args.nes_core).read_bytes()).hexdigest()
    if nes_sha != '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60':
        ap.error('NES RAM mapping is qualified only for the tested core hash')
    genesis_sha = hashlib.sha256(Path(args.genesis_core).read_bytes()).hexdigest()
    if genesis_sha != '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268':
        ap.error('Genesis RAM mapping is qualified only for the independently probed core hash')
    source_paths = [
        'src/fdisbull/console_udc.py', 'src/fdisbull/udc_nes.py',
        'src/fdisbull/udc_genesis.py', 'src/fdisbull/udl_genesis.py',
        'src/fdisbull/interaction_il.py', 'src/fdisbull/roms.py',
        'tests/test_console_udc_semantics.py', 'scripts/check_console_udc.py',
        'scripts/verify_console_udc.py']
    def source_hashes():
        return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in source_paths}
    initial_hashes = source_hashes()
    root = Path(args.output).resolve()
    if root.exists() or any((p / '.git').exists() for p in (root, *root.parents)):
        ap.error('output must be a new directory outside Git')
    root.mkdir(parents=True)
    summary = {'scope': 'authored UIL subset and bounded generated ROM execution; not full game conversion or hardware parity', 'status': 'running', 'cases': [], 'memory_assumptions': {'nes': 'direct bytes, little endian', 'genesis': 'paired raw byte swap, big endian; independently probed for this core'}, 'limits': {'no_genesis_select': True, 'frame_phase': 'RAM sampled immediately after retro_run'}}
    summary['source_sha256'] = initial_hashes
    def save():
        (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    save()
    try:
        helpers = runpy.run_path(str(ROOT / 'tests/test_console_udc_semantics.py'))
        cases = [('marker', marker(), None)] + [(c['name'], helpers['program'](c), c['expected']) for c in helpers['semantic_cases']()]
        for name, program, expected in cases:
            validate_il(program)
            for target, core in [('nes', args.nes_core), ('genesis', args.genesis_core)]:
                summary['cases'].append({'name': name, **run_case(root, name, target, program, core, args.frames, expected)})
                save()
        source = route_program()
        source_run = run_case(root, 'source_route', 'genesis', source, args.genesis_core, args.frames)
        summary['cases'].append({'name': 'source_route', **source_run})
        package = root / 'source_route/genesis/package'
        manifest = json.loads((package / 'manifest.json').read_text())
        rom = (package / 'program.md').read_bytes()
        symbols = manifest['symbols']
        recovered = lift(rom, logic_offset=symbols['logic_tick'], logic_length=symbols['logic_tick_end']-symbols['logic_tick'], layout=manifest['variables'])
        (root / 'source_route/recovered.uil.json').write_text(json.dumps(recovered, indent=2) + '\n')
        derived = recovered['program']
        summary['route'] = {'source_program_sha256': manifest['program_sha256'], 'source_rom_sha256': manifest['rom_sha256'], 'recovered_uil_digest': digest(derived), 'binding_assumptions': recovered['provenance']['bindings'], 'logic_sha256': recovered['provenance']['logic_sha256']}
        source_state = derived_state = None
        for tick in range(args.frames):
            source_state = execute_il(source, source_state)['state']
            derived_state = execute_il(derived, derived_state)['state']
            if source_state != derived_state:
                raise AssertionError(f'source/recovered reference divergence at tick {tick + 1}: {source_state} != {derived_state}')
        summary['route']['reference_ticks_compared'] = args.frames
        target_run = run_case(root, 'source_route', 'nes', derived, args.nes_core, args.frames)
        summary['cases'].append({'name': 'recovered_route', **target_run})
        if source_hashes() != initial_hashes:
            raise RuntimeError('compiler, reference, fixture or harness source changed during verification')
        summary['source_unchanged'] = True
        summary['status'] = 'passed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['failure'] = f'{type(exc).__name__}: {exc}'
        save()
        raise
    save()
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
