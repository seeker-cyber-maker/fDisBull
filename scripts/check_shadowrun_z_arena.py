#!/usr/bin/env python3
"""Exercise the shared Z protocol against a bounded assisted original capture."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_city import captured_entities
from fdisbull.game_il import canonical
from fdisbull.shadowrun_z import ShadowrunRuntime, ShadowrunZBackend


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser()
    for arg in ('rom', 'snapshot', 'capture', 'output'):
        p.add_argument('--' + arg, required=True)
    p.add_argument('--end', type=int, choices=(6021, 6040, 6049, 6051, 6060, 6070, 6079), default=6051)
    p.add_argument('--moving', action='store_true')
    args = p.parse_args()
    if args.moving and args.end > 6049:
        raise ValueError('moving comparison exceeds the reviewed capture')
    capture = Path(args.capture)
    cap = json.loads((capture / 'capture.json').read_text())
    receipt_raw = (capture / 'native/receipt.json').read_bytes()
    expected_receipt = ('731cb1ec2f51c207d3acaf3443a4de0c231bd4db9922a9b7f0c57a6333858ff6'
                        if args.moving else 'b40dd5e704b7bba2c3c746a10473f120978f884e9528573da966c2245b4e8510')
    if sha(receipt_raw) != expected_receipt:
        raise ValueError('requires the reviewed assisted original from-launch capture')
    rom = Path(args.rom).read_bytes()
    def source_inventory():
        return sorted({str(path.relative_to(ROOT)) for path in
                       [*(ROOT / 'src/fdisbull').glob('shadowrun_*.py'),
                        *(ROOT / 'src/fdisbull/game_sources').glob('shadowrun_*.c'),
                        ROOT / 'src/fdisbull/game_il.py', ROOT / 'src/fdisbull/udl_shadowrun.py',
                        ROOT / 'scripts/check_shadowrun_z_arena.py']})
    source_paths = source_inventory()
    source_hashes = {name: sha((ROOT / name).read_bytes()) for name in source_paths}
    runtime = ShadowrunRuntime(assisted_arena_from_capture(rom, Path(args.snapshot), moving=args.moving),
                               captured_entities=captured_entities(rom, Path(args.snapshot)))
    program_hash = sha(canonical(runtime.machine.program))
    z = ShadowrunZBackend(runtime, policy='assisted')
    initial = z.observe()
    if initial['captured_entities'][0]['hp_current'] != 10:
        raise AssertionError('unexpected initial shared player HP')
    compared = 0
    frames = list(range(6000, min(args.end, 6060) + 1))
    frames += [frame for frame in (6070, 6079) if frame <= args.end]
    previous = 5999
    for frame in frames:
        for action_frame in range(previous + 1, frame + 1):
            before = z.observe()
            move_left = args.moving and 6001 <= action_frame < 6041
            result = z.act({'verb': 'go' if move_left else 'wait',
                            'target': 'direction.west' if move_left else 'wait.1', 'item': None,
                            'context_token': before['context']['token']})
            if not result.get('complete') or result.get('detail', {}).get('frames_executed') != 1:
                raise AssertionError((frame, result))
        previous = frame
        observed = z.observe()
        player = next(a for a in observed['captured_entities'] if a.get('slot_address') == 0xff0100)
        hostile = next(a for a in observed['captured_entities'] if a.get('slot_address') == 0xff0400)
        key = f'native/scene-{frame:06d}/ram.bin'
        raw = (capture / key).read_bytes()
        if len(raw) != 65536 or sha(raw) != cap['files'][key]['sha256']:
            raise ValueError(f'original RAM mismatch at frame {frame}')
        original = bytes(raw[i ^ 1] for i in range(65536))
        word = lambda i: int.from_bytes(original[i:i + 2], 'big')
        actual = (player['x'], player['y'], player['hp_current'], hostile['x'], hostile['y'], hostile['hp_current'])
        expected = (word(0x100), word(0x104), original[0x14c], word(0x400), word(0x404), original[0x44c])
        if (actual != expected or hostile['kind'] != 8 or
                hostile['id'] != 'shadowrun.assisted.scene.02.actor.ff0400.kind08'):
            raise AssertionError((frame, actual, expected))
        if observed['player_state']['hp_current'] != player['hp_current']:
            raise AssertionError('Z player and actor HP projections diverged')
        if any(actor['x'] is not None or actor['hp_current'] is not None or actor.get('present') is not None or
               actor.get('current_position_reason') != 'not simulated by the assisted arena profile'
               for actor in observed['captured_entities'] if actor.get('slot_address') in (0xff0500, 0xff0600)):
            raise AssertionError('an unmodeled captured NPC appeared as a current actor')
        compared += 1
    if (source_paths != source_inventory() or
            source_hashes != {name: sha((ROOT / name).read_bytes()) for name in source_paths} or
            program_hash != sha(canonical(runtime.machine.program))):
        raise ValueError('Z source or shared model changed during the comparison')
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(mode=0o700, parents=True)
    report = {'status': 'passed', 'frames_advanced': args.end - 5999, 'snapshots_compared': compared,
              'first_frame': 6000, 'last_frame': args.end,
              'source_sha256': sha(rom), 'original_receipt_sha256': sha(receipt_raw),
              'source_files_sha256': source_hashes, 'shared_program_sha256': program_hash,
              'player_hp_start': 10, 'player_hp_end': z.observe()['captured_entities'][0]['hp_current'],
              'scope': 'assisted source-constructed arena, Z directional/wait actions on the shared model; '
                       'original actor/player fields are comparison outputs only; no natural encounter claim'}
    summary = out / 'summary.json'
    summary.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'frames_advanced': report['frames_advanced'],
                      'snapshots_compared': report['snapshots_compared'],
                      'shared_program_sha256': program_hash, 'summary_sha256': sha(summary.read_bytes())}))


if __name__ == '__main__':
    main()
