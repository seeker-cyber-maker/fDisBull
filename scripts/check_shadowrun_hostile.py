#!/usr/bin/env python3
"""Compare an assisted source-constructed actor tick with the original core.

The input contract is the private, source-constructor-backed arena contract;
its pinned hash prevents arbitrary actor profiles from being silently attested.
The output is private because the native probe retains original RAM and traces.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_hostile import lift_hostile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for key in ('rom', 'core', 'contract', 'output'):
        ap.add_argument('--' + key, required=True)
    ap.add_argument('--diagonal', action='store_true', help='check varied actor x/y sight lines')
    args = ap.parse_args()
    raw = Path(args.contract).read_bytes()
    contract = json.loads(raw)
    # Pin every setup field except the controlled variations below by requiring
    # the reviewed private baseline contract, not merely a user-supplied bit.
    if digest(raw) != 'aa13cd56cfbcb9e95a19ddfa5fbc7c09f091966589bf94842a1398d41e41f047':
        raise ValueError('requires the reviewed source-constructed arena contract')
    rom = Path(args.rom).read_bytes()
    program = lift_hostile(rom)
    contract['max_instructions'] = 5400
    contract['stop_pcs'].remove(0x14146)
    contract['stop_pcs'] = [0x151e8 if pc == 0x151da else pc for pc in contract['stop_pcs']]
    contract['stop_pcs'] += [0xac9e, 0x1415e]
    next(item for item in contract['code_ranges'] if item['start'] == 0x14d8e)['end'] = 0x15318
    cases = []
    descriptions = []
    points = ((16096, 10954), (16096, 11466), (16352, 10954)) if args.diagonal else (
        (15840, 11210), (16096, 11210), (16352, 11210))
    for x, y in points:
        for seed in (0, 2, 65535):
            for existing in (0, 1):
                descriptions.append((x, y, seed, existing, 0, 0, 0))
    if not args.diagonal:
        descriptions.extend(((16096, 11210, 2, 0, 1, 0, 0), (16096, 11210, 2, 0, 20, 0, 0),
                             (16096, 11210, 2, 0, 0, 127, 0), (16096, 11210, 2, 0, 0, 128, 0),
                             (16096, 11210, 2, 0, 0, 0, 2), (16096, 11210, 2, 1, 0, 0, 20)))
    for x, y, seed, existing, timer, blocked, cooldown in descriptions:
        ram = copy.deepcopy(contract['ram'])
        actors = bytearray.fromhex(ram[0]['data'])
        actor = memoryview(actors)[0x300:0x400]
        actor[0:2] = x.to_bytes(2, 'big')
        actor[4:6] = y.to_bytes(2, 'big')
        # Same captured camera; original $5A56 projection, in pixels.
        actor[10:12] = ((x - 13312) // 16 + 128).to_bytes(2, 'big')
        actor[12:14] = ((y - 10016) // 16 + 128).to_bytes(2, 'big')
        actor[0xb6:0xb8] = timer.to_bytes(2, 'big')
        actor[0xdc:0xde] = cooldown.to_bytes(2, 'big')
        actor[0xa2:0xa6] = (0xff0100 if existing else 0).to_bytes(4, 'big')
        ram[0]['data'] = actors.hex()
        tail = bytearray.fromhex(ram[4]['data'])
        tail[0x9f8:0x9fa] = seed.to_bytes(2, 'big')
        ram[4]['data'] = tail.hex()
        if blocked:
            terrain = bytearray.fromhex(ram[2]['data'])
            if terrain[1374] != 0:
                raise ValueError('baseline sight-line cell changed')
            terrain[1374] = blocked
            ram[2]['data'] = terrain.hex()
        cases.append({'name': f'x{x}-y{y}-rng{seed}-existing{existing}-timer{timer}-block{blocked}-cool{cooldown}', 'ram': ram})
    contract['cases'] = cases
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(mode=0o700, parents=True)
    casefile = out / 'contract.json'
    casefile.write_text(json.dumps(contract))
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
                           '--rom', args.rom, '--core', args.core, '--contract', str(casefile),
                           '--output', str(out / 'native')], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-4000:])
    receipt_path = out / 'native/receipt.json'
    receipt = json.loads(receipt_path.read_text())
    blocked_or_unknown = 0
    for case, (x, y, seed, existing, timer, blocked, cooldown) in zip(receipt['cases'], descriptions, strict=True):
        m = GameMachine(program, {0: rom})
        m.set_state({'shadowrun_hostile_profile': 1, 'shadowrun_hostile_x': x,
                     'shadowrun_hostile_y': y, 'shadowrun_hostile_player_x': 15584,
                     'shadowrun_hostile_player_y': 11210, 'shadowrun_hostile_ammo': 48,
                     'shadowrun_hostile_contact': (y - 10016) // 16 + 128,
                     'shadowrun_terrain_map': list(bytes.fromhex(case['contract']['ram'][2]['data'])),
                     'shadowrun_x_min': 44, 'shadowrun_x_max': 1876,
                     'shadowrun_y_min': 44, 'shadowrun_y_max': 1304,
                     'shadowrun_hostile_rng': seed, 'shadowrun_hostile_target_existing': existing,
                     'shadowrun_hostile_timer': timer, 'shadowrun_hostile_cooldown': cooldown})
        m.call('shadowrun_hostile_tick')
        state = m.snapshot()
        if args.diagonal and case['registers_after']['PC'] == 0x14070:
            if state['shadowrun_hostile_supported'] or state['shadowrun_hostile_los_result'] not in (0, 2):
                raise AssertionError('source blocked, model did not refuse')
            blocked_or_unknown += 1
            continue
        if blocked:
            if (case['registers_after']['PC'] != 0x14070 or state['shadowrun_hostile_supported'] or
                    state['shadowrun_hostile_los_result'] != 2 or state['shadowrun_hostile_ammo'] != 48 or
                    state['shadowrun_hostile_rng'] != seed):
                raise AssertionError('blocked sight-line disagreement')
            continue
        actor_bytes = bytes.fromhex(case['ram_after']['actors'])
        actor, projectile = actor_bytes[0x300:0x400], actor_bytes[0xa00:0xb00]
        glob = bytes.fromhex(case['ram_after']['other_globals_b'])
        scene = bytes.fromhex(case['ram_after']['global'])
        word = lambda b, i: int.from_bytes(b[i:i+2], 'big')
        actual = (word(actor, 0xb6), word(actor, 0xdc), actor[0x4e], word(glob, 0x7f8), actor[0xb5])
        expected = tuple(state['shadowrun_hostile_' + key] for key in
                         ('timer', 'cooldown', 'ammo', 'rng', 'target_timer'))
        if actual != expected or not state['shadowrun_hostile_supported']:
            raise AssertionError((case['contract']['name'], actual, expected))
        if cooldown:
            if (case['registers_after']['PC'] != 0x1415e or state['shadowrun_hostile_fired'] or
                    state['shadowrun_hostile_pursuit_required'] != 1):
                raise AssertionError('cooldown did not reach the source pursuit boundary')
        elif timer:
            if case['registers_after']['PC'] != 0xac9e or state['shadowrun_hostile_fired']:
                raise AssertionError('idle timer did not reach the expected boundary')
        else:
            actual = (word(projectile, 0), word(projectile, 4), word(projectile, 0x2e),
                      word(projectile, 0x4c), word(projectile, 0x4e), projectile[0x9f], projectile[0x89])
            expected = tuple(state['shadowrun_hostile_' + key] for key in
                             ('projectile_x', 'projectile_y', 'heading', 'velocity_x',
                              'velocity_y', 'effect', 'lifetime'))
            if case['registers_after']['PC'] != 0x151e8 or actual != expected:
                raise AssertionError((case['contract']['name'], actual, expected))
            if (projectile[0x41], projectile[0x8b]) != (
                    state['shadowrun_hostile_burst_remaining'], state['shadowrun_hostile_burst_mode']):
                raise AssertionError('source burst setup differs')
            if (word(scene, 0x286), word(scene, 0x2de), int.from_bytes(actor_bytes[0xac:0xb0], 'big')) != (
                    state['shadowrun_hostile_combat_timer'], state['shadowrun_hostile_combat_mode'], 0xff0400):
                raise AssertionError('source combat globals or player attacker link differ')
            if state['shadowrun_hostile_player_attacker'] != 1:
                raise AssertionError('player attacker handoff missing')
    report = {'status': 'passed', 'cases': len(cases),
              'firing_cases': 18 - blocked_or_unknown, 'timer_cases': 0 if args.diagonal else 2,
              'blocked_terrain_cases': blocked_or_unknown if args.diagonal else 2,
              'cooldown_boundary_cases': 0 if args.diagonal else 2,
              'source_sha256': digest(rom), 'core_sha256': digest(Path(args.core).read_bytes()),
              'baseline_contract_sha256': digest(raw), 'native_receipt_sha256': digest(receipt_path.read_bytes()),
              'scope': 'assisted source-constructed profile, one target; clear/blocked sight and '
                       'cooldown boundary; no natural reachability or full-frame encounter claim'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
