#!/usr/bin/env python3
"""Compare camera state with controlled original-68000 execution.

The native cases deliberately stay inside one eight-pixel stream cell so the
Genesis graphics-stream helpers are not called. Ordinary captured frame tests
qualify that separate boundary. All raw receipts remain private.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_camera import lift_camera

FIELDS = {'player_x': (0x100, 2), 'player_y': (0x104, 2), 'heading': (0x12e, 2),
          'x': (0xddc6, 2), 'y': (0xddc8, 2), 'min_x': (0xddca, 2),
          'max_x': (0xddce, 2), 'min_y': (0xddcc, 2), 'max_y': (0xddd0, 2),
          'scroll_ax': (0xdd08, 2), 'scroll_ay': (0xdd0a, 2),
          'scroll_bx': (0xdd0c, 2), 'scroll_by': (0xdd0e, 2),
          'stream_x': (0xdf38, 2), 'stream_y': (0xdf36, 2),
          'freeze_a': (0xe100, 2), 'freeze_b': (0xe102, 2),
          'freeze_c': (0xdfe8, 2), 'mode': (0xe186, 1),
          'previous_x': (0xe173, 1), 'previous_y': (0xe174, 1)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'core', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or not out.parent.is_dir() or any(
            (q / '.git').exists() for q in (out, *out.parents)):
        raise ValueError('Choose a fresh private output outside Git')
    rom = a.rom.read_bytes()
    program = lift_camera(rom)
    out.mkdir(mode=0o700)
    inputs = []
    cases = []
    previous = (0, 1, 2, 254, 255)
    for h in range(16):
        for j, prev in enumerate(previous):
            for freeze in range(4):
                state = {k: 0 for k in FIELDS}
                state.update(player_x=0x3ce0, player_y=0x2bca if h % 2 else 0x31c0,
                             heading=h << 12, x=0x3440, y=0x2740,
                             max_x=0x6700, max_y=0x4400,
                             scroll_ay=90, scroll_by=90,
                             stream_x=0x3400, stream_y=0x2700,
                             previous_x=prev, previous_y=previous[(h+j) % 5])
                if freeze:
                    state[('freeze_a', 'freeze_b', 'freeze_c')[freeze-1]] = 1
                seeds = [{'address': 0xff0000 + offset,
                          'data': state[key].to_bytes(n, 'big').hex()}
                         for key, (offset, n) in FIELDS.items()]
                seeds.append({'address': 0xfffc04, 'data': '00ff0100'})
                inputs.append(state)
                cases.append({'name': f'camera-{h}-{j}-{freeze}', 'ram': seeds})
    contract = {'name': 'normal-field-camera-state', 'entry': 0x3a3c,
                'code_ranges': [{'start': 0x3a3c, 'end': 0x3d18},
                                {'start': 0x15dcc, 'end': 0x15df6}],
                'watch': [{'name': 'camera', 'address': 0xffdd00, 'length': 0x300},
                          {'name': 'flags', 'address': 0xffe100, 'length': 0x88}],
                'stack_scratch_bytes': 32, 'max_instructions': 300, 'cases': cases}
    contract_path = out / 'contract.json'
    contract_path.write_text(json.dumps(contract) + '\n')
    command = [sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
               '--core', str(a.core.resolve()), '--rom', str(a.rom.resolve()),
               '--contract', str(contract_path), '--output', str(out / 'native'),
               '--timeout', '120']
    run = subprocess.run(command, capture_output=True, text=True, timeout=150)
    (out / 'run.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(run.stderr[-3000:])
    native_raw = (out / 'native/receipt.json').read_bytes()
    native = json.loads(native_raw)
    if not native.get('complete') or len(native['cases']) != len(inputs):
        raise ValueError('Native cases incomplete')
    mismatches = []
    machine = GameMachine(program, {0: rom})
    for index, (state, case) in enumerate(zip(inputs, native['cases'])):
        machine.set_state({'shadowrun_camera_' + k: v for k, v in state.items()})
        machine.call('shadowrun_camera_tick')
        actual = machine.snapshot()
        ram = {name: bytes.fromhex(value) for name, value in case['ram_after'].items()}
        for key, (offset, n) in FIELDS.items():
            if offset < 0xdd00 or key.startswith('player') or key == 'heading':
                continue
            region, base = ('camera', 0xdd00) if offset < 0xe100 else ('flags', 0xe100)
            expected = int.from_bytes(ram[region][offset-base:offset-base+n], 'big')
            if actual['shadowrun_camera_' + key] != expected:
                mismatches.append({'case': index, 'field': key, 'native': expected,
                                   'uil': actual['shadowrun_camera_' + key]})
    receipt = {'format': 'fdisbull-shadowrun-camera-check-1',
               'source_sha256': hashlib.sha256(rom).hexdigest(),
               'program_sha256': hashlib.sha256(canonical(program)).hexdigest(),
               'native_receipt_sha256': hashlib.sha256(native_raw).hexdigest(),
               'cases': len(inputs), 'mismatches': mismatches,
               'scope': 'controlled camera state, all 16 heading sectors, five prior steps, four freeze states; no graphics streaming calls or ordinary reachability proof'}
    (out / 'summary.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if mismatches:
        raise AssertionError(f'{len(mismatches)} camera state mismatches')
    print(out / 'summary.json')


if __name__ == '__main__':
    main()
