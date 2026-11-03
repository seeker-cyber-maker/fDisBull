#!/usr/bin/env python3
"""Compare source-timed LEFT animation and actor flag scan to private captures.

Motion, pose, depth, camera and the prior-stage flags are observed inputs for
this component check, not predictions. The 7F tables come from the initial
capture. Presentation queue effects and whole-frame state are excluded.
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
RAM_SHA = '0032d4c7e01fce638a8ef653be6ab94871d7aa51ce48bb65d5d7b1444f791211'
CORE_SHA = '89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
OBSERVER_SHA = '1617d549840551e9faa6864c0c36a8ee9608c8aee6eba90cccb1a620a0dd48be'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def left_route(receipt):
    for frame in range(3000, 3120):
        buttons = [button for event in receipt['inputs'] if event['start'] <= frame < event['end']
                   for button in event['buttons']]
        if buttons != ['LEFT']:
            raise ValueError('unexpected source input sequence')


def main():
    p = argparse.ArgumentParser()
    for arg in ('rom', 'initial-ram', 'trace-run', 'capture-a', 'capture-b', 'output'):
        p.add_argument('--' + arg, required=True)
    a = p.parse_args()
    rom, ram = Path(a.rom).read_bytes(), Path(a.initial_ram).read_bytes()
    if sha(rom) != ROM_SHA or sha(ram) != RAM_SHA:
        raise ValueError('source identity mismatch')
    trace_run = Path(a.trace_run)
    trace_receipt = json.loads((trace_run / 'receipt.json').read_bytes())
    trace_raw = (trace_run / 'snes_trace.json').read_bytes()
    if (trace_receipt['rom_sha256'] != ROM_SHA or trace_receipt['core_sha256'] != OBSERVER_SHA or
        trace_receipt['patches'] or trace_receipt['snes_trace_sha256'] != sha(trace_raw)):
        raise ValueError('observer trace identity mismatch')
    left_route(trace_receipt)
    captures = {}
    for run in (Path(a.capture_a), Path(a.capture_b)):
        receipt = json.loads((run / 'receipt.json').read_bytes())
        if receipt['rom_sha256'] != ROM_SHA or receipt['core_sha256'] != CORE_SHA or receipt['patches']:
            raise ValueError('baseline capture identity mismatch')
        left_route(receipt)
        for entry in receipt['frame_ram']:
            raw = (run / entry['file']).read_bytes()
            if len(raw) != 131072 or sha(raw) != entry['sha256'] or entry['frame'] in captures:
                raise ValueError('baseline snapshot mismatch or duplicate')
            captures[entry['frame']] = raw
    regions = [{'id': i, 'length': len(data), 'sha256': sha(data)} for i, data in ((0, rom), (1, ram))]
    m = GameMachine(author_program(SOURCE.read_text(), regions), {0: rom, 1: ram})
    m.set_state({'shadowrun_snes_flag_requested_direction': 3})
    m.call('shadowrun_snes_flag_walk_start')
    frames = json.loads(trace_raw)['frames']
    if [f['frame'] for f in frames] != list(range(3000, 3120)):
        raise ValueError('expected contiguous source trace')
    queue_frames = 0
    for frame in frames:
        f = frame['frame']
        if frame['dropped'] or f not in captures:
            raise ValueError('incomplete source observation')
        events = frame['events']
        prior = [e for e in events if e['kind'] == 2 and e['pc'] == 0x80b208 and e['address'] == 0x8014b6]
        scratch = [e for e in events if e['kind'] == 1 and e['pc'] == 0x80b7eb and e['y'] == 0x42]
        if len(prior) != 1 or len(scratch) != 1:
            raise ValueError('ambiguous actor stage')
        if any(e['p'] & 0x130 or e['db'] != 0x80 or e['d'] != 0 for e in prior + scratch):
            raise ValueError('unexpected CPU mode or bank')
        b = captures[f]
        def w(offset):
            return int.from_bytes(b[offset:offset + 2], 'little')
        m.call('shadowrun_snes_flag_walk_tick')
        m.set_state({'shadowrun_snes_flag_x': w(0xe86), 'shadowrun_snes_flag_y': w(0xede),
                     'shadowrun_snes_flag_z': w(0xf36), 'shadowrun_snes_flag_depth': w(0xf8e),
                     'shadowrun_snes_flag_camera_x': w(0xce0) >> 2,
                     'shadowrun_snes_flag_camera_y': w(0xce2) >> 2,
                     'shadowrun_snes_flags_in': prior[0]['a']})
        m.call('shadowrun_snes_flags_project')
        s = m.snapshot()
        if (s['shadowrun_snes_flag_animation_status'] != 1 or s['shadowrun_snes_flag_status'] != 1 or
            s['shadowrun_snes_flag_sprite'] != w(0x3f9e) or
            s['shadowrun_snes_flags_scratch'] != scratch[0]['a'] or s['shadowrun_snes_flags_out'] != w(0x14b6)):
            raise AssertionError(f'source actor projection mismatch at frame {f}')
        queue_frames += bool(s['shadowrun_snes_flag_queue_effect'])
    result = {'status': 'passed', 'frames': 120, 'trace_sha256': sha(trace_raw),
              'program_sha256': sha(canonical(m.program)), 'source_sha256': sha(SOURCE.read_bytes()),
              'rom_sha256': sha(rom), 'initial_ram_sha256': sha(ram),
              'frames_with_omitted_queue_effect': queue_frames,
              'scope': 'Flag projection with observed pose/depth/camera and prior-stage flags; presentation excluded.'}
    with open(a.output, 'x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(f"matched {len(frames)} source frames; queue effects marked in {queue_frames}")


if __name__ == '__main__':
    main()
