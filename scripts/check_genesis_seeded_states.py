#!/usr/bin/env python3
"""Shadow all procedural fields after an explicitly assisted Genesis stage seed.

Pause in the diagnostic loop before changing state; release it only after the
complete state and empty publication ring have been installed. This is not
ordinary player reachability. Input files, seeds, ROMs and raw traces stay private.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from check_genesis_game import (
    GEN_SHA, capture_inputs, debug_bytes, physical_patches, run_host,
    save, shadow_publications, state_writes, watches_for,
)
from check_miniplanets_native import _private_output


def seed_stage(program, rom, stage):
    if type(stage) is not int or not 0 <= stage < 55:
        raise ValueError('stage index must be 0..54')
    machine = GameMachine(program, {0: rom},
                          environment={'hv16': [0] * 32, 'sound_busy': [0]})
    machine.call('game_boot')
    machine.call('start_game')
    machine.set_state({'stage': stage})
    machine.call('begin_stage', 0)
    if machine.snapshot()['stage'] != stage:
        raise AssertionError('stage seed did not select the requested original stage')
    return machine.snapshot()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'cartridge', 'core', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--stage', required=True, type=int)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--frames', type=int, default=600)
    args = parser.parse_args()
    if not 300 <= args.frames <= 10000:
        parser.error('frames must be 300..10000')
    cartridge = args.cartridge.resolve()
    paths = {'rom': args.rom, 'cartridge': cartridge, 'core': args.core,
             'manifest': cartridge.with_name('manifest.json'),
             'program': cartridge.with_name('program.json'), 'inputs': args.inputs,
             'host': ROOT / 'scripts/check_console_udc.py',
             'verifier': ROOT / 'scripts/check_genesis_game.py',
             'seed_verifier': Path(__file__).resolve(),
             'game_il': ROOT / 'src/fdisbull/game_il.py'}
    out = _private_output(args.output)
    out.mkdir()
    captured, identities = capture_inputs(out, paths)
    rom = captured['rom'].read_bytes()
    manifest = json.loads(captured['manifest'].read_text())
    program = json.loads(captured['program'].read_text())
    sha = lambda data: hashlib.sha256(data).hexdigest()
    if (manifest.get('format') != 'fdisbull-genesis-game-1' or
            manifest.get('rom_sha256') != identities['cartridge']['sha256'] or
            manifest.get('program_sha256') != sha(canonical(program)) or
            manifest.get('source_rom_sha256') != sha(rom) or
            identities['core']['sha256'] != GEN_SHA):
        raise ValueError('source/program/native/core identity mismatch')
    state = seed_stage(program, rom, args.stage)
    save(out / 'seed.json', state)
    watches, _, _ = watches_for(manifest)
    # Initial hardware/VDP setup is complete before frame 220. Twenty frames in
    # the diagnostic spin loop also allow any interrupted game iteration to end.
    patches = physical_patches(220, [(0x1f04, b'\x01')])
    patches += physical_patches(240, state_writes(state, manifest['state_layout']) +
                                [(0, bytes(4 * 704)), (0x1f02, b'\0\0')])
    patches += physical_patches(260, [(0x1f04, b'\0')])
    inputs = json.loads(captured['inputs'].read_text())
    receipt, trace = run_host(captured['core'], captured['cartridge'], captured['host'],
                              out / 'native', args.frames, watches,
                              patches=patches, inputs=inputs)
    for row in trace['frames'][225:260]:
        if debug_bytes(row)[4] != 1 or debug_bytes(row)[5] != 0:
            raise AssertionError('diagnostic pause did not settle before seeding')
    result = shadow_publications(program, rom, manifest, receipt, trace,
                                 initial_state=state, start_frame=260)
    if result['controller_mapping_gaps']:
        raise AssertionError('ambiguous controller mapping after stage seed')
    if not result['completed_ticks']:
        raise AssertionError('no seeded stage ticks observed')
    for name, original in identities.items():
        if (sha(Path(original['source']).read_bytes()) != original['sha256'] or
                sha(captured[name].read_bytes()) != original['sha256']):
            raise AssertionError('qualification input changed')
    summary = {'format': 'fdisbull-genesis-seeded-state-check-1', 'status': 'passed',
               'stage_index': args.stage, 'frames': args.frames,
               'assistance': 'diagnostic pause, full 79-field seed from source-ROM UIL, skip intro',
               'seed_sha256': sha(canonical(state)), 'inputs': identities,
               'state_checks': result, 'inputs_unchanged': True,
               'scope': 'native stage rules vs UIL with observed device inputs; no natural reachability claim'}
    save(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('status', 'stage_index', 'state_checks')}))


if __name__ == '__main__':
    main()
