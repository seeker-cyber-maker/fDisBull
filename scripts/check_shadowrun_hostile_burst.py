#!/usr/bin/env python3
"""Qualify item-10 burst transitions at controlled source animation boundaries."""
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
from fdisbull.shadowrun_hostile_burst import lift_hostile_burst


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for arg in ('rom', 'core', 'contract', 'output'):
        parser.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    raw = Path(args.contract).read_bytes()
    if sha(raw) != 'f7f1eacd05238935f95c33924f8d820a94e3187d7ad0d1946869a92515d3e45d':
        raise ValueError('requires reviewed source-produced projectile contract')
    contract = json.loads(raw)
    contract.pop('cases')
    contract['stop_pcs'].append(0x14f24)
    variants = [(counter, seed, 65535) for counter in (2, 1) for seed in (0, 2, 21845, 65535)]
    variants += [(0, 2, 65535), (2, 2, 12)]
    cases = []
    for counter, seed, animation in variants:
        ram = copy.deepcopy(contract['ram'])
        actors = bytearray.fromhex(ram[0]['data'])
        actors[0xa41] = counter
        actors[0xa16:0xa18] = animation.to_bytes(2, 'big')
        if counter == 1:
            actors[0xa2e:0xa30] = (0xbc00).to_bytes(2, 'big')
        ram[0]['data'] = actors.hex()
        glob = bytearray.fromhex(ram[4]['data'])
        glob[0x7f8:0x7fa] = seed.to_bytes(2, 'big')
        ram[4]['data'] = glob.hex()
        cases.append({'name': f'counter{counter}-rng{seed}-animation{animation}', 'ram': ram})
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
    receipt_file = out / 'native/receipt.json'
    receipt = json.loads(receipt_file.read_text())
    rom = Path(args.rom).read_bytes()
    program = lift_hostile_burst(rom)
    word = lambda b, i: int.from_bytes(b[i:i + 2], 'big')
    for case, (counter, seed, animation) in zip(receipt['cases'], variants, strict=True):
        before = bytes.fromhex(case['ram_before']['actors'])
        pr = before[0xa00:0xb00]
        m = GameMachine(program, {0: rom})
        m.set_state({'shadowrun_burst_profile': 1, 'shadowrun_burst_x': int.from_bytes(pr[:4], 'big'),
                     'shadowrun_burst_y': int.from_bytes(pr[4:8], 'big'),
                     'shadowrun_burst_origin_x': word(pr, 0x58), 'shadowrun_burst_origin_y': word(pr, 0x5a),
                     'shadowrun_burst_heading': word(pr, 0x2e), 'shadowrun_burst_vx': word(pr, 0x4c),
                     'shadowrun_burst_vy': word(pr, 0x4e), 'shadowrun_burst_animation': animation,
                     'shadowrun_burst_counter': counter, 'shadowrun_burst_rng': seed,
                     'shadowrun_burst_flags': pr[0x10], 'shadowrun_burst_flags_low': pr[0x11],
                     'shadowrun_burst_lifetime': pr[0x89], 'shadowrun_burst_effect': pr[0x9f],
                     'shadowrun_burst_shooter_effect': before[0x39f]})
        m.call('shadowrun_burst_tick'); state = m.snapshot()
        after = bytes.fromhex(case['ram_after']['actors']); pr = after[0xa00:0xb00]
        glob = bytes.fromhex(case['ram_after']['global_c'])
        actual = (int.from_bytes(pr[:4], 'big'), int.from_bytes(pr[4:8], 'big'), word(pr, 0x2e),
                  word(pr, 0x4c), word(pr, 0x4e), word(pr, 0x16), pr[0x41], pr[0x10], pr[0x11],
                  pr[0x89], pr[0x9f], after[0x39f], word(glob, 0x7f8))
        expected = tuple(state['shadowrun_burst_' + k] for k in
                         ('x', 'y', 'heading', 'vx', 'vy', 'animation', 'counter', 'flags', 'flags_low',
                          'lifetime', 'effect', 'shooter_effect', 'rng'))
        pc = 0x14f24 if animation == 12 else (0x14ff6 if counter == 0 else 0x14fee)
        if not state['shadowrun_burst_supported'] or case['registers_after']['PC'] != pc or actual != expected:
            raise AssertionError((case['contract']['name'], actual, expected))
    report = {'status': 'passed', 'cases': len(cases), 'source_sha256': sha(rom),
              'core_sha256': sha(Path(args.core).read_bytes()), 'contract_sha256': sha(raw),
              'native_receipt_sha256': sha(receipt_file.read_bytes()),
              'scope': 'controlled animation boundaries after assisted source item10 hit; '
                       'animation timing and natural encounter not established'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
