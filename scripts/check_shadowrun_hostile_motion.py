#!/usr/bin/env python3
"""Compare bounded hostile projectile flight/contact against the original core."""
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
from fdisbull.shadowrun_hostile_motion import lift_hostile_motion


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for arg in ('rom', 'core', 'contract', 'output'):
        parser.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    raw = Path(args.contract).read_bytes()
    if sha(raw) != 'f7bdb5053244b7466eaf433620073a60fdc8cbad8c6369288a90cea1d5375206':
        raise ValueError('requires the reviewed source-launched projectile contract')
    contract = json.loads(raw)
    contract['stop_pcs'] = [0x14e30, 0x14e60, 0x14e82]
    contract['max_instructions'] = 6000
    # The miss/effect, far player and wall inputs are explicit diagnostic
    # variants of the exact source-produced launch, not natural encounters.
    variants = [('hit', 5, 15584, 32, 0), ('miss', 0, 15584, 32, 0),
                ('flight', 5, 15000, 32, 0), ('wall', 5, 15000, 32, 127),
                ('expiry', 5, 15000, 0, 0), ('other-actor', 5, 15000, 32, 0),
                ('shooter-hit', 5, 15000, 32, 0), ('shooter-miss', 0, 15000, 32, 0)]
    cases = []
    for name, effect, player_x, life, wall in variants:
        ram = copy.deepcopy(contract['ram'])
        actors = bytearray.fromhex(ram[0]['data'])
        actors[0:2] = player_x.to_bytes(2, 'big')
        actors[0xa9f] = effect
        actors[0xa89] = life
        if name == 'other-actor':
            actors[0x400:0x402] = (15824).to_bytes(2, 'big')
            actors[0x404:0x406] = (11210).to_bytes(2, 'big')
        if name.startswith('shooter-'):
            actors[0x300:0x302] = (15824).to_bytes(2, 'big')
            actors[0x304:0x306] = (11210).to_bytes(2, 'big')
        ram[0]['data'] = actors.hex()
        terrain = bytearray.fromhex(ram[1]['data'])
        if wall:
            if terrain[1374] != 0:
                raise ValueError('baseline flight cell changed')
            terrain[1374] = wall
        ram[1]['data'] = terrain.hex()
        cases.append({'name': name, 'ram': ram})
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
    rom = Path(args.rom).read_bytes()
    program = lift_hostile_motion(rom)
    for case, (name, effect, player_x, life, wall) in zip(receipt['cases'], variants, strict=True):
        m = GameMachine(program, {0: rom})
        memory = bytes.fromhex(case['ram_before']['actors'])
        proj = memory[0xa00:0xb00]
        word = lambda b, i: int.from_bytes(b[i:i + 2], 'big')
        m.set_state({'shadowrun_hostile_motion_profile': 1, 'shadowrun_hostile_motion_state': 1,
                     'shadowrun_hostile_motion_x': int.from_bytes(proj[:4], 'big'),
                     'shadowrun_hostile_motion_y': int.from_bytes(proj[4:8], 'big'),
                     'shadowrun_hostile_motion_vx': word(proj, 0x4c),
                     'shadowrun_hostile_motion_vy': word(proj, 0x4e),
                     'shadowrun_hostile_motion_lifetime': life, 'shadowrun_hostile_motion_effect': effect,
                     'shadowrun_hostile_motion_player_x': player_x, 'shadowrun_hostile_motion_player_y': 11210,
                     'shadowrun_target_x': [word(memory, 0x300 + i * 0x100) for i in range(7)],
                     'shadowrun_target_y': [word(memory, 0x304 + i * 0x100) for i in range(7)],
                     'shadowrun_target_flags': [memory[0x310 + i * 0x100] for i in range(7)],
                     'shadowrun_play_actor_hp': [memory[0x34c + i * 0x100] for i in range(7)],
                     'shadowrun_terrain_map': list(bytes.fromhex(case['contract']['ram'][1]['data'])),
                     'shadowrun_x_min': 44, 'shadowrun_x_max': 1876,
                     'shadowrun_y_min': 44, 'shadowrun_y_max': 1304})
        m.call('shadowrun_hostile_motion_tick')
        s = m.snapshot()
        if name == 'other-actor':
            if (case['registers_after']['PC'] != 0x14e82 or case['registers_after']['A1'] != 0xff0500 or
                    s['shadowrun_hostile_motion_supported'] or
                    s['shadowrun_hostile_motion_x'] != int.from_bytes(proj[:4], 'big')):
                raise AssertionError('unmodeled source actor contact did not fail closed')
            continue
        native = bytes.fromhex(case['ram_after']['actors'])[0xa00:0xb00]
        expected_state = {'hit': 2, 'miss': 5, 'flight': 1, 'wall': 3, 'expiry': 4,
                          'shooter-hit': 6, 'shooter-miss': 7}[name]
        expected_pc = {'hit': 0x14e82, 'miss': 0x14e60, 'flight': 0x14e30,
                       'wall': 0x14e60, 'expiry': 0x14e60,
                       'shooter-hit': 0x14e82, 'shooter-miss': 0x14e60}[name]
        observed = (int.from_bytes(native[:4], 'big'), int.from_bytes(native[4:8], 'big'),
                    word(native, 0x4c), word(native, 0x4e), native[0x89])
        model = tuple(s['shadowrun_hostile_motion_' + k] for k in ('x', 'y', 'vx', 'vy', 'lifetime'))
        if (not s['shadowrun_hostile_motion_supported'] or s['shadowrun_hostile_motion_state'] != expected_state or
                case['registers_after']['PC'] != expected_pc or observed != model):
            raise AssertionError((name, hex(case['registers_after']['PC']), observed, model, s))
    result = {'status': 'passed', 'cases': [v[0] for v in variants], 'source_sha256': sha(rom),
              'core_sha256': sha(Path(args.core).read_bytes()), 'baseline_contract_sha256': sha(raw),
              'native_receipt_sha256': sha(receipt_path.read_bytes()),
              'scope': 'assisted source launch with controlled miss/player/wall/lifetime variants; '
                       'before separate player damage; no whole encounter claim'}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
