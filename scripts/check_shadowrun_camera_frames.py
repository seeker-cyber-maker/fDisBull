#!/usr/bin/env python3
"""Check the source camera model against adjacent original scene snapshots.

Uses current-frame player state after movement, previous camera state, and
compares every declared camera state field. Sparse gaps are counted separately.
The caller selects field frames; UI/scheduler and whole-game recovery are not
established by this component check.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_camera import lift_camera
from check_shadowrun_camera import FIELDS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--before', type=int, default=10000)
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or not out.parent.is_dir() or any((q / '.git').exists() for q in (out, *out.parents)):
        raise ValueError('Choose a new private output outside Git')
    rom = a.rom.read_bytes()
    program = lift_camera(rom)
    snapshots = {}
    identities = {}
    for folder in sorted(a.native.glob('scene-*')):
        frame = int(folder.name.removeprefix('scene-'))
        if frame >= a.before:
            continue
        raw = (folder / 'ram.bin').read_bytes()
        if len(raw) != 65536:
            raise ValueError('Expected complete byte-paired Genesis RAM')
        identities[str(frame)] = hashlib.sha256(raw).hexdigest()
        snapshots[frame] = {
            'shadowrun_camera_' + key: int.from_bytes(
                bytes(raw[(offset+i) ^ 1] for i in range(n)), 'big')
            for key, (offset, n) in FIELDS.items()}
    if not snapshots:
        raise ValueError('No snapshots selected')
    machine = GameMachine(program, {0: rom})
    compared = 0
    gaps = 0
    bad = []
    actor = ('shadowrun_camera_player_x', 'shadowrun_camera_player_y', 'shadowrun_camera_heading')
    # Other source components can change these inputs before the camera call,
    # notably the door request setting the field-busy freeze in its own tick.
    inputs = actor + tuple('shadowrun_camera_' + k for k in
                           ('min_x', 'max_x', 'min_y', 'max_y', 'freeze_a',
                            'freeze_b', 'freeze_c', 'mode'))
    for frame, current in snapshots.items():
        if frame-1 not in snapshots:
            gaps += 1
            continue
        state = {**snapshots[frame-1], **{k: current[k] for k in inputs}}
        machine.set_state(state)
        machine.call('shadowrun_camera_tick')
        actual = machine.snapshot()
        differences = {k: {'native': v, 'uil': actual[k]} for k, v in current.items()
                       if k not in actor and v != actual[k]}
        if actual['shadowrun_camera_supported'] != 1:
            differences['supported'] = {'native': 'normal field camera required', 'uil': 0}
        if differences:
            bad.append({'frame': frame, 'differences': differences})
        compared += 1
    result = {'format': 'fdisbull-shadowrun-camera-frame-check-1',
              'program_sha256': hashlib.sha256(canonical(program)).hexdigest(),
              'source_sha256': hashlib.sha256(rom).hexdigest(),
              'frames_compared': compared, 'gaps_not_compared': gaps,
              'snapshot_ram_sha256': identities, 'mismatches': bad,
              'scope': 'camera state after current player commit; scheduler and UI excluded'}
    out.write_text(json.dumps(result, indent=2) + '\n')
    if not compared or bad:
        raise AssertionError(f'{compared} comparisons, {len(bad)} differences')
    print(out)


if __name__ == '__main__':
    main()
