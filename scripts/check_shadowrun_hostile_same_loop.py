#!/usr/bin/env python3
"""Re-run an assisted original actor-loop launch-to-player-HP boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for arg in ('rom', 'core', 'contract', 'output'):
        parser.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    raw = Path(args.contract).read_bytes()
    if sha(raw) != '4404e34eb0a1bfe793addf3b442eddd380bd84cc7e1f4e2d61f442566ba5b9e9':
        raise ValueError('requires the reviewed assisted, audio-disabled same-loop contract')
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(mode=0o700, parents=True)
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_genesis_function.py'),
                           '--rom', args.rom, '--core', args.core, '--contract', args.contract,
                           '--output', str(out / 'native')], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-4000:])
    receipt_file = out / 'native/receipt.json'
    receipt = json.loads(receipt_file.read_text())
    case = receipt['cases'][0]
    before = bytes.fromhex(case['ram_before']['actors'])
    after = bytes.fromhex(case['ram_after']['actors'])
    steps = json.loads((out / 'native/trace.json').read_text())[0]['steps']
    observed = [(s['pc'], s['index']) for s in steps if s['pc'] in (0x151d0, 0x15310, 0x14e0a, 0x14e82, 0x36ae)]
    if ([pc for pc, _ in observed] != [0x151d0, 0x15310, 0x14e0a, 0x14e82, 0x36ae] or
            case['registers_after']['PC'] != 0x36b2 or
            (before[0x4c], after[0x4c], before[0x34e], after[0x34e], after[0xa89]) != (10, 5, 48, 47, 29)):
        raise AssertionError('source loop did not reproduce the launch-to-player-HP boundary')
    actor_slots = [s['registers_after']['A0'] for s in steps if s['pc'] == 0xa8fc]
    if actor_slots != list(range(0xff0400, 0xff0c00, 0x100)):
        raise AssertionError('source actor-loop ordering changed')
    result = {'status': 'passed', 'source_sha256': sha(Path(args.rom).read_bytes()),
              'core_sha256': sha(Path(args.core).read_bytes()), 'contract_sha256': sha(raw),
              'native_receipt_sha256': sha(receipt_file.read_bytes()), 'player_hp': [10, 5],
              'ammo': [48, 47], 'projectile_lifetime_at_impact': 29,
              'scope': 'source-constructed assisted scene2 arena; audio disabled for CPU-only '
                       'Z80 handshake; same actor-loop pass, not natural encounter or whole frame'}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
