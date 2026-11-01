#!/usr/bin/env python3
"""Check wound difficulty against original $D5A for both health channels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_player_attack import lift_player_attack
from fdisbull.shadowrun_combat import ROM_SHA256
from check_shadowrun_opening_route import GENESIS_CORE_SHA


def main():
    p = argparse.ArgumentParser()
    for name in ('rom', 'core', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    rom = a.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256 or hashlib.sha256(a.core.read_bytes()).hexdigest() != GENESIS_CORE_SHA:
        raise ValueError('source/core identity mismatch')
    out = _private_directory(a.output); out.mkdir(mode=0o700)
    cases = []
    for hp in range(1, 11):
        for alt in range(1, 11):
            actor = bytearray(256); actor[0x4C], actor[0x9C] = hp, alt
            cases.append({'name': f'{hp}-{alt}', 'registers': {'A0': 0xFF0100, 'D4': 4},
                          'ram': [{'address': 0xFF0100, 'data': actor.hex()}]})
    contract = {'name': 'party-wound-threshold', 'entry': 0xD5A,
        'code_ranges': [{'start': 0xD5A, 'end': 0xD94}],
        'stop_pcs': [0xD82, 0xD8E, 0xD92], 'max_instructions': 50,
        'watch': [{'name': 'actor', 'address': 0xFF0100, 'length': 256}], 'cases': cases}
    cp = out / 'contract.json'; cp.write_text(json.dumps(contract))
    q = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
        '--rom', str(a.rom), '--core', str(a.core), '--contract', str(cp),
        '--output', str(out / 'native')], capture_output=True, text=True)
    (out / 'stdout.txt').write_text(q.stdout); (out / 'stderr.txt').write_text(q.stderr)
    if q.returncode: raise RuntimeError(q.stderr[-4000:])
    rr = (out / 'native/receipt.json').read_bytes(); r = json.loads(rr)
    if not r['complete'] or not r['inputs_unchanged'] or len(r['cases']) != 100:
        raise AssertionError('incomplete source probe')
    program = lift_player_attack(rom); m = GameMachine(program, {})
    for inp, actual in zip(cases, r['cases']):
        hp, alt = map(int, inp['name'].split('-'))
        m.set_state({'shadowrun_player_attack_hp': hp, 'shadowrun_player_attack_alternate_hp': alt})
        m.call('shadowrun_player_attack_threshold'); s = m.snapshot()
        if not s['shadowrun_player_attack_supported'] or s['shadowrun_player_attack_difficulty'] != actual['registers_after']['D4']:
            raise AssertionError((inp['name'], s, actual['registers_after']))
        if actual['ram_after']['actor'] != inp['ram'][0]['data']:
            raise AssertionError('unexpected source actor mutation')
    summary = {'format': 'fdisbull-shadowrun-player-attack-1', 'status': 'passed',
        'cases': 100, 'source_sha256': ROM_SHA256, 'core_sha256': GENESIS_CORE_SHA,
        'native_receipt_sha256': hashlib.sha256(rr).hexdigest(),
        'program_sha256': hashlib.sha256(canonical(program)).hexdigest(),
        'scope': 'original wound modifier with base difficulty4; other attack modifiers and readiness excluded'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
