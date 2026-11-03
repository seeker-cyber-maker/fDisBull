#!/usr/bin/env python3
"""Compare one observed actor-stage merge to a private SNES trace.

This checks the merge only. The source's scan, side effects and full frame are
not reconstructed by this comparison. The trace must include the player flag
writes and instructions $80:B7E8-$B82E, with no dropped events.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, author_program, canonical

SOURCE = ROOT / 'src/fdisbull/game_sources/shadowrun_snes_flags.c'
ROM_SHA = 'e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4'
OBSERVER_SHA = '1617d549840551e9faa6864c0c36a8ee9608c8aee6eba90cccb1a620a0dd48be'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='private observer capture')
    parser.add_argument('--output', required=True, help='new private receipt')
    args = parser.parse_args()
    run = Path(args.run)
    receipt_raw = (run / 'receipt.json').read_bytes()
    receipt = json.loads(receipt_raw)
    raw = (run / 'snes_trace.json').read_bytes()
    if (receipt['system'] != 'snes' or receipt['rom_sha256'] != ROM_SHA or
        receipt['core_sha256'] != OBSERVER_SHA or
        receipt['patches'] or receipt['snes_trace_sha256'] != sha(raw)):
        raise ValueError('unqualified capture identity, patch, or trace hash')
    trace = json.loads(raw)
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    frames = []
    for frame in trace['frames']:
        events = frame['events']
        selected = [e for e in events if (e['kind'] == 1 and
                    e['pc'] == 0x80b7eb and e['y'] == 0x42) or
                    (e['kind'] == 2 and e['address'] == 0x8014b6 and
                     e['pc'] in (0x80b208, 0x80b804, 0x80b811, 0x80b81b, 0x80b82b))]
        if any(e['p'] & 0x30 or e['db'] != 0x80 or e['d'] != 0 for e in selected):
            raise ValueError(f"unexpected CPU width or bank at frame {frame['frame']}")
        scratch = [e['a'] for e in selected if e['kind'] == 1 and
                   e['pc'] == 0x80b7eb and e['y'] == 0x42]
        before = [e['a'] for e in selected if e['kind'] == 2 and
                  e['pc'] == 0x80b208 and e['address'] == 0x8014b6]
        after = [e['a'] for e in selected if e['kind'] == 2 and
                 e['pc'] in (0x80b804, 0x80b811, 0x80b81b, 0x80b82b) and
                 e['address'] == 0x8014b6]
        if frame['dropped'] or len(scratch) != 1 or len(before) != 1 or len(after) != 1:
            raise ValueError(f"incomplete or ambiguous trace at frame {frame['frame']}")
        machine.set_state({'shadowrun_snes_flags_in': before[0],
                           'shadowrun_snes_flags_scratch': scratch[0]})
        machine.call('shadowrun_snes_flags_merge')
        if machine.snapshot()['shadowrun_snes_flags_out'] != after[0]:
            raise AssertionError(f"flag merge mismatch at frame {frame['frame']}")
        frames.append(frame['frame'])
    if not frames:
        raise ValueError('empty trace')
    result = {'status': 'passed', 'frames': frames, 'trace_sha256': sha(raw),
              'observer_receipt_sha256': sha(receipt_raw),
              'observer_core_sha256': receipt['core_sha256'],
              'source_sha256': sha(SOURCE.read_bytes()),
              'program_sha256': sha(canonical(machine.program)),
              'scope': 'Actor-stage flag merge only; scan and other frame effects excluded.'}
    with open(args.output, 'x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(f"matched {len(frames)} source actor-stage merges")


if __name__ == '__main__':
    main()
