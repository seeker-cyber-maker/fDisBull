#!/usr/bin/env python3
"""Qualify original item-10 projectile impact sprite-pass counters."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_hostile_animation import lift_hostile_animation


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for arg in ('rom', 'core', 'ram', 'output'):
        parser.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    ram = Path(args.ram).read_bytes()
    if len(ram) != 65536 or sha(ram) != '7c6eb1c1c9607055b6d7c53fada746284917e9eaf65cedcd88425373972a08ef':
        raise ValueError('requires the reviewed original source impact RAM')
    rom = Path(args.rom).read_bytes()
    program = lift_hostile_animation(rom)
    original = ram[0xb00:0xc00]
    variants = [(a, inc, acc, idx) for a in (0, 4, 12, 16, 20)
                for inc in (0, 2, 1024, 2048) for acc in (0, 3072) for idx in (0, 4, 5)]
    # Follow the exact source impact through successive sprite passes. Each
    # source boundary is then checked independently against the native core.
    current = (12, 0, 0, 0)
    sequence = []
    for _ in range(32):
        sequence.append(current)
        a, inc, acc, idx = current
        m = GameMachine(program, {0: rom})
        m.set_state({'shadowrun_burst_anim_profile': 1, 'shadowrun_burst_anim_word': a,
                     'shadowrun_burst_anim_increment': inc, 'shadowrun_burst_anim_accumulator': acc,
                     'shadowrun_burst_anim_threshold': 4096, 'shadowrun_burst_anim_index': idx,
                     'shadowrun_burst_anim_flags': 9})
        m.call('shadowrun_burst_animation_tick'); s = m.snapshot()
        current = tuple(s['shadowrun_burst_anim_' + k] for k in ('word', 'increment', 'accumulator', 'index'))
        if current[0] & 32768:
            break
    else:
        raise AssertionError('source impact animation did not reach its boundary')
    variants.extend(sequence)
    cases = []
    for i, (a, inc, acc, idx) in enumerate(variants):
        actor = bytearray(original)
        actor[0x11] = 1 if a == 20 else 9
        for offset, value in ((0x16, a), (0x18, inc), (0x1a, acc), (0x1e, idx)):
            actor[offset:offset + 2] = value.to_bytes(2, 'big')
        cases.append({'name': f'sprite-pass-{i:03d}', 'ram': [
            {'address': 0xff0b00, 'data': actor.hex()},
            {'address': 0xffdd3c, 'data': ram[0xdd3c:0xdd40].hex()},
            # Join the source counter RTS to the source selector; this is a
            # controlled leaf composition, not an assumed frame scheduler.
            {'address': 0xfffe00, 'data': '0000600e'}]})
    contract = {'name': 'source-projectile-impact-sprite-pass', 'entry': 0x5fdc,
                'registers': {'A0': 0xff0b00}, 'stop_pcs': [0x60ae], 'max_instructions': 100,
                'code_ranges': [{'start': 0x5fdc, 'end': 0x60ae}],
                'watch': [{'name': 'actor', 'address': 0xff0b00, 'length': 256},
                          {'name': 'scratch', 'address': 0xffdd3c, 'length': 4}], 'cases': cases}
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
    word = lambda b, i: int.from_bytes(b[i:i + 2], 'big')
    for case, (a, inc, acc, idx) in zip(receipt['cases'], variants, strict=True):
        m = GameMachine(program, {0: rom})
        m.set_state({'shadowrun_burst_anim_profile': 1, 'shadowrun_burst_anim_word': a,
                     'shadowrun_burst_anim_increment': inc, 'shadowrun_burst_anim_accumulator': acc,
                     'shadowrun_burst_anim_threshold': 4096, 'shadowrun_burst_anim_index': idx,
                     'shadowrun_burst_anim_flags': 1 if a == 20 else 9})
        m.call('shadowrun_burst_animation_tick'); s = m.snapshot()
        actor = bytes.fromhex(case['ram_after']['actor'])
        actual = (word(actor, 0x16), word(actor, 0x18), word(actor, 0x1a), word(actor, 0x1e), actor[0x11])
        expected = tuple(s['shadowrun_burst_anim_' + k] for k in ('word', 'increment', 'accumulator', 'index', 'flags'))
        if not s['shadowrun_burst_anim_supported'] or actual != expected:
            raise AssertionError((case['contract']['name'], actual, expected))
    report = {'status': 'passed', 'cases': len(cases), 'source_impact_sprite_passes': len(sequence),
              'source_sha256': sha(rom), 'core_sha256': sha(Path(args.core).read_bytes()),
              'native_receipt_sha256': sha(receipt_file.read_bytes()),
              'scope': 'controlled source sprite passes after assisted impact; '
                       'sprite-pass frequency and natural encounter not established'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
