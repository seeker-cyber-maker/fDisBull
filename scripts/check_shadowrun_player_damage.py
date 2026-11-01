#!/usr/bin/env python3
"""Compare captured-player bullet defense/HP with controlled original code.

This starts at the damage consumer with a supplied projectile effect. It does
not establish ordinary enemy reachability, aiming, collision, HUD or death.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_player_damage import lift_player_damage
from fdisbull.shadowrun_combat import ROM_SHA256
from check_shadowrun_opening_route import captured_file, checked_receipt, GENESIS_CORE_SHA


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'core', 'capture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    if sha(rom) != ROM_SHA256 or sha(args.core.read_bytes()) != GENESIS_CORE_SHA:
        raise ValueError('source/core identity mismatch')
    cap_raw = (args.capture / 'capture.json').read_bytes()
    cap = json.loads(cap_raw)
    receipt_raw = captured_file(args.capture, cap, 'native/receipt.json')
    checked_receipt(json.loads(receipt_raw), system='genesis',
                    core_sha=GENESIS_CORE_SHA, rom_sha=ROM_SHA256)
    raw = captured_file(args.capture, cap, 'native/scene-006037/ram.bin')
    if len(raw) != 65536:
        raise ValueError('incorrect source RAM size')
    memory = bytes(raw[i ^ 1] for i in range(len(raw)))
    player = memory[0x100:0x200]
    projectile = memory[0xB00:0xC00]
    expected = {0x10: 15, 0x3E: 0, 0x3F: 0, 0x4C: 10,
                0x4D: 2, 0x76: 1, 0x77: 4, 0x78: 3, 0x7B: 2,
                0x7C: 4, 0x90: 0, 0x91: 4, 0xDF: 0}
    if any(player[offset] != value for offset, value in expected.items()):
        raise ValueError('captured player profile mismatch')
    if any(item in (39, 40) for item in player[0x66:0x6E]):
        raise ValueError('unmodeled defense equipment')
    if projectile[0x11] & 32 or 39 in projectile[0x66:0x6E]:
        raise ValueError('unmodeled projectile mitigation')
    cases = []
    parameters = list(itertools.product((1, 2, 6, 10, 12), (0, 1, 3, 7),
                      (1, 5, 10), (0, 1, 4, 5, 12), (0, 2, 21845, 65535)))
    for item, armor, hp, effect, seed in parameters:
        target = bytearray(player)
        target[0x4C], target[0x76] = hp, armor
        shot = bytearray(projectile)
        shot[0x57], shot[0x9F] = item, effect
        globals_ = bytearray(memory[0xF000:0xFE00])
        globals_[0x9F8:0x9FA] = seed.to_bytes(2, 'big')
        cases.append({'name': f'{item}-{armor}-{hp}-{effect}-{seed}',
            'registers': {'A0': 0xFF0B00, 'A1': 0xFF0100},
            'ram': [{'address': 0xFF0100, 'data': target.hex()},
                    {'address': 0xFF0B00, 'data': shot.hex()},
                    {'address': 0xFFE100, 'data': memory[0xE100:0xE200].hex()},
                    {'address': 0xFFF000, 'data': globals_.hex()}]})
    contract = {'name': 'captured-player-defense-before-hud', 'entry': 0x55948,
        'code_ranges': [{'start': lo, 'end': hi} for lo, hi in
            ((0x55948, 0x55B16), (0x55E62, 0x55F44), (0x55786, 0x55848),
             (0x3674, 0x36F0), (0xD3A, 0xDFC))],
        'stop_pcs': [0x36F0, 0x559E4, 0x55B14], 'stack_scratch_bytes': 192,
        'max_instructions': 1600,
        'watch': [{'name': 'player', 'address': 0xFF0100, 'length': 256},
                  {'name': 'projectile', 'address': 0xFF0B00, 'length': 256},
                  {'name': 'globals', 'address': 0xFFF000, 'length': 3584}],
        }
    out = _private_directory(args.output)
    out.mkdir(mode=0o700)
    original_cases, native_receipts = [], []
    # Keep each explicit seed contract below the harness's 1-MiB limit.
    for batch, start in enumerate(range(0, len(cases), 64)):
        group = cases[start:start + 64]
        contract_path = out / f'contract-{batch:02d}.json'
        contract_path.write_text(json.dumps({**contract, 'cases': group}))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
            '--rom', str(args.rom), '--core', str(args.core), '--contract', str(contract_path),
            '--output', str(out / f'native-{batch:02d}')],
            capture_output=True, text=True, timeout=600)
        (out / f'native-{batch:02d}.stdout').write_text(result.stdout)
        (out / f'native-{batch:02d}.stderr').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:])
        native_raw = (out / f'native-{batch:02d}/receipt.json').read_bytes()
        native = json.loads(native_raw)
        if not native['complete'] or not native['inputs_unchanged'] or len(native['cases']) != len(group):
            raise AssertionError('incomplete original comparison')
        original_cases.extend(native['cases'])
        native_receipts.append({'batch': batch, 'sha256': sha(native_raw), 'cases': len(group)})
        print(f'Original batch {batch + 1}: {len(group)} cases', flush=True)
    receipt_index = json.dumps(native_receipts, sort_keys=True).encode()
    (out / 'native-receipts.json').write_bytes(receipt_index)
    program = lift_player_damage(rom)
    model = GameMachine(program, {0: rom})
    rows, mismatches = [], []
    for values, original in zip(parameters, original_cases):
        item, armor, hp, effect, seed = values
        model.set_state({'shadowrun_player_damage_profile': 1,
            'shadowrun_player_damage_item': item, 'shadowrun_player_damage_effect': effect,
            'shadowrun_player_damage_armor': armor, 'shadowrun_player_damage_hp': hp,
            'shadowrun_player_damage_rng': seed})
        model.call('shadowrun_player_hit')
        state = model.snapshot()
        after = bytes.fromhex(original['ram_after']['player'])
        global_after = bytes.fromhex(original['ram_after']['globals'])
        expected_state = (after[0x4C], int.from_bytes(global_after[0x9F8:0x9FA], 'big'),
                          global_after[0xDD])
        actual = tuple(state['shadowrun_player_damage_' + k] for k in ('hp', 'rng', 'successes'))
        if not state['shadowrun_player_damage_supported'] or actual != expected_state:
            mismatches.append({'input': list(values), 'model': actual, 'source': expected_state})
        for offset in range(256):
            before = hp if offset == 0x4C else armor if offset == 0x76 else player[offset]
            if offset != 0x4C and after[offset] != before:
                raise AssertionError(('unexpected player mutation', offset))
        rows.append({'input': list(values), 'hp': after[0x4C],
                     'rng': expected_state[1], 'successes': expected_state[2]})
    summary = {'format': 'fdisbull-shadowrun-player-damage-1',
        'status': 'passed' if not mismatches else 'failed', 'cases': len(cases),
        'mismatches': mismatches, 'source_sha256': ROM_SHA256,
        'core_sha256': GENESIS_CORE_SHA, 'capture_sha256': sha(cap_raw),
        'source_receipt_sha256': sha(receipt_raw), 'native_receipts_sha256': sha(receipt_index),
        'program_sha256': sha(canonical(program)),
        'scope': 'controlled original damage consumer with supplied item/effect/RNG; '
                 'captured party stats, armor and HP variations; stops before HUD/death; '
                 'no ordinary enemy reachability or full projectile pipeline claim'}
    (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
