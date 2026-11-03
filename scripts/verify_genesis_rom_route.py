#!/usr/bin/env python3
"""Qualify one hash-bound real Miniplanets ROM function through UIL to NES.

The original game is an external input. Raw CPU traces, recovered UIL, generated
cartridges and RAM stay in a new private directory. This is a function-boundary
experiment, not a complete game port or naturally reached gameplay trace.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.interaction_il import execute_il
from fdisbull.udl_genesis import lift_native

ROM_SHA = 'e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7'
NES_SHA = '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
GENESIS_SHA = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
OBJECT = 0xff0894
FILES = ('src/fdisbull/udl_genesis.py', 'src/fdisbull/console_udc.py',
         'src/fdisbull/udc_nes.py', 'src/fdisbull/interaction_il.py',
         'scripts/check_console_udc.py', 'scripts/probe_genesis_function.py',
         'scripts/verify_console_udc.py', 'scripts/verify_genesis_rom_route.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in FILES}


def lift_game(rom, kind=27, timer=1):
    return lift_native(rom, logic_offset=0x54d4, logic_length=12,
        layout={'$object_type': {'address': OBJECT, 'width': 8, 'initial': kind},
                '$timer': {'address': OBJECT + 3, 'width': 8, 'initial': timer}},
        address_registers={'A0': OBJECT})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ('rom', 'nes-core', 'genesis-core', 'output'):
        ap.add_argument('--' + arg, required=True)
    args = ap.parse_args()
    rom = Path(args.rom).read_bytes()
    if sha(rom) != ROM_SHA:
        ap.error('this pilot requires the exact upstream Miniplanets REV04 ROM')
    if sha(Path(args.nes_core).read_bytes()) != NES_SHA or sha(Path(args.genesis_core).read_bytes()) != GENESIS_SHA:
        ap.error('this experiment requires the two qualified core binaries')
    root = Path(args.output).resolve()
    if root.exists() or any((p / '.git').exists() for p in (root, *root.parents)):
        ap.error('output must be a new directory outside Git')
    frozen = hashes()
    root.mkdir(parents=True)
    summary = {'format': 'fdisbull-real-genesis-route-1', 'status': 'running',
        'source_sha256': ROM_SHA, 'source_size': len(rom), 'source_sha256_before': sha(rom),
        'core_sha256': {'nes': NES_SHA, 'genesis': GENESIS_SHA}, 'source_hashes': frozen,
        'scope': 'controlled original-ROM function state projection to UIL and native NES; not a whole-game port',
        'cases': []}
    def save():
        (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    save()
    try:
        contract = {'entry': 0x54d4, 'code_ranges': [{'start': 0x54d4, 'end': 0x54e0}],
            'registers': {'A0': OBJECT}, 'watch': [
                {'name': 'object_type', 'address': OBJECT, 'length': 1},
                {'name': 'timer', 'address': OBJECT + 3, 'length': 1}],
            'max_instructions': 16, 'max_master_cycles': 10000,
            'cases': [{'name': f'type{k}-timer{t}', 'ram': [
                {'address': OBJECT, 'data': bytes((k, 0, 0, t)).hex()}]}
                for k in (0, 27, 255) for t in range(256)]}
        contract_path = root / 'contract.json'
        contract_path.write_text(json.dumps(contract, indent=2) + '\n')
        started = time.perf_counter()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
            '--core', args.genesis_core, '--rom', args.rom, '--contract', str(contract_path),
            '--output', str(root / 'native')], capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise RuntimeError('original CPU probe failed: ' + proc.stderr[-2000:])
        native = json.loads((root / 'native/receipt.json').read_text())
        if not native['complete'] or not native['inputs_unchanged'] or native['source_sha256'] != ROM_SHA:
            raise AssertionError('native source/probe did not complete with unchanged inputs')
        summary['native_probe_seconds'] = time.perf_counter() - started
        recovered = lift_game(rom)
        (root / 'recovered.uil.json').write_text(json.dumps(recovered, indent=2) + '\n')
        provenance = recovered['provenance']
        # The full source-bound instruction facts remain private with the UIL.
        summary['lift'] = {k: v for k, v in provenance.items() if k != 'instructions'}
        summary['lifted_uil_sha256'] = sha(json.dumps(recovered['program'], sort_keys=True, separators=(',', ':')).encode())
        oracle, mutant_failures = {}, 0
        mutant = copy.deepcopy(recovered['program'])
        mutant['body'][0]['op'] = 'add'
        for case in native['cases']:
            initial = {'$object_type': int(case['ram_before']['object_type'], 16),
                       '$timer': int(case['ram_before']['timer'], 16)}
            expected = {'$object_type': int(case['ram_after']['object_type'], 16),
                        '$timer': int(case['ram_after']['timer'], 16)}
            actual = execute_il(recovered['program'], initial)
            if not actual['complete'] or actual['state'] != expected or case['changes_outside_watches_and_stack']:
                raise AssertionError(f'original CPU / UIL divergence: {case["contract"]["name"]}')
            # Independent arithmetic expectation supplements the CPU oracle.
            timer = (initial['$timer'] - 1) & 255
            if expected != {'$object_type': initial['$object_type'] if timer else 0, '$timer': timer}:
                raise AssertionError('native output differs from hand-derived function rule')
            oracle[(initial['$object_type'], initial['$timer'])] = expected
            mutant_failures += execute_il(mutant, initial)['state'] != expected
        if len(oracle) != 768 or mutant_failures != 768:
            raise AssertionError('native input coverage or mutation sensitivity incomplete')
        summary['native_cases_checked'] = len(oracle)
        summary['mutant_mismatches'] = mutant_failures
        summary['native_instruction_count'] = sum(c['instructions_executed'] for c in native['cases'])
        summary['native_master_cycle_total'] = sum(c['master_cycles'] for c in native['cases'])
        summary['native_trace_sha256'] = sha((root / 'native/trace.json').read_bytes())
        helpers = runpy.run_path(str(ROOT / 'scripts/verify_console_udc.py'))
        cases = [(27, t, False) for t in (0, 1, 2, 60, 255)] + [(0, 1, False), (255, 1, False), (27, 60, True)]
        for kind, timer, guarded in cases:
            program = lift_game(rom, kind, timer)['program']
            if guarded:
                # Presentation and single-object dispatch are authored adapters,
                # attributed separately from the recovered function itself.
                program['body'] = [{'id': 'authored_dispatch', 'op': 'if',
                    'condition': {'op': 'eq', 'left': {'var': '$object_type'}, 'right': 27},
                    'then': program['body'], 'else': []},
                    {'id': 'authored_marker', 'op': 'set', 'var': '$x', 'value': {'var': '$timer'}}]
                program['variables']['$x'] = {'type': 'u8', 'initial': timer}
            name = f'type{kind}_timer{timer}' + ('_guarded_demo' if guarded else '_bare_function')
            result = helpers['run_case'](root, name, 'nes', program, args.nes_core, 180)
            package = root / name / 'nes/package'
            manifest = json.loads((package / 'manifest.json').read_text())
            trace = json.loads((root / name / 'nes/run/ram_trace.json').read_text())
            first = min(v['address'] for v in manifest['variables'].values()) & ~1
            previous = {'$object_type': kind, '$timer': timer}
            count = checked = 0
            for frame in trace['frames']:
                control = bytes.fromhex(frame['raw']['control'])
                if int.from_bytes(control[2:4], 'little') != 0xa55a:
                    continue
                tick = int.from_bytes(control[:2], 'little')
                if tick == count:
                    continue
                if tick != count + 1:
                    raise AssertionError('NES counter gap')
                data = bytes.fromhex(frame['raw']['vars'])
                actual = {key: data[manifest['variables'][key]['address'] - first] for key in previous}
                expected = oracle[(previous['$object_type'], previous['$timer'])] if not guarded or previous['$object_type'] == 27 else previous
                if actual != expected:
                    raise AssertionError(f'original CPU / NES divergence at {name}, tick {tick}')
                previous, count = actual, tick
                checked += 1
            if checked != result['checked_ticks']:
                raise AssertionError('NES native-oracle trace coverage mismatch')
            summary['cases'].append({'name': name, 'authored_dispatch_and_display': guarded,
                'original_cpu_transitions_checked': checked, **result})
            save()
        if hashes() != frozen or sha(Path(args.rom).read_bytes()) != ROM_SHA:
            raise AssertionError('source or compiler/harness changed during verification')
        summary['native_to_nes_transitions_checked'] = sum(c['original_cpu_transitions_checked'] for c in summary['cases'])
        summary['inputs_unchanged'] = True
        summary['status'] = 'passed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['failure'] = f'{type(exc).__name__}: {exc}'
        save()
        raise
    save()
    print(root / 'summary.json')


if __name__ == '__main__':
    main()
