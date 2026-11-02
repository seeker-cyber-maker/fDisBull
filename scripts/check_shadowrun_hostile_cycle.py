#!/usr/bin/env python3
"""Compare one assisted projectile's actor/sprite steps to full-core frames."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine
from fdisbull.shadowrun_hostile_cycle import lift_hostile_cycle
from fdisbull.shadowrun_player_reaction import lift_player_reaction


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser()
    for arg in ('rom', 'capture', 'output'):
        p.add_argument('--' + arg, required=True)
    p.add_argument('--end', type=int, default=6037)
    p.add_argument('--from-launch', action='store_true')
    args = p.parse_args()
    if not 6001 <= args.end <= (6051 if args.from_launch else 6037):
        raise ValueError('frame limit outside the reviewed capture')
    root = Path(args.capture)
    cap = json.loads((root / 'capture.json').read_text())
    receipt_raw = (root / 'native/receipt.json').read_bytes()
    expected_receipt = ('b40dd5e704b7bba2c3c746a10473f120978f884e9528573da966c2245b4e8510'
                        if args.from_launch else
                        '36f857e0835e061ba72821e11c55f1846fb2a99eea4a7f5982e2353340526bbc')
    if sha(receipt_raw) != expected_receipt:
        raise ValueError('requires the selected reviewed assisted full-core capture')
    def frame(n):
        key = f'native/scene-{n:06d}/ram.bin'
        raw = (root / key).read_bytes()
        if len(raw) != 65536 or sha(raw) != cap['files'][key]['sha256']:
            raise ValueError(f'captured RAM mismatch at frame {n}')
        return bytes(raw[i ^ 1] for i in range(65536))
    word = lambda b, i: int.from_bytes(b[i:i + 2], 'big')
    long = lambda b, i: int.from_bytes(b[i:i + 4], 'big')
    rom = Path(args.rom).read_bytes()
    machine = GameMachine(lift_hostile_cycle(rom), {0: rom})
    start = frame(6000); pr = start[0xb00:0xc00]
    machine.set_state({'shadowrun_burst_profile': 1, 'shadowrun_burst_x': long(pr, 0),
                       'shadowrun_burst_y': long(pr, 4), 'shadowrun_burst_origin_x': word(pr, 0x58),
                       'shadowrun_burst_origin_y': word(pr, 0x5a), 'shadowrun_burst_heading': word(pr, 0x2e),
                       'shadowrun_burst_vx': word(pr, 0x4c), 'shadowrun_burst_vy': word(pr, 0x4e),
                       'shadowrun_burst_counter': pr[0x41], 'shadowrun_burst_flags': pr[0x10],
                       'shadowrun_burst_flags_low': pr[0x11], 'shadowrun_burst_lifetime': pr[0x89],
                       'shadowrun_burst_effect': pr[0x9f], 'shadowrun_burst_shooter_effect': start[0x49f],
                       'shadowrun_burst_anim_word': word(pr, 0x16),
                       'shadowrun_burst_anim_increment': word(pr, 0x18),
                       'shadowrun_burst_anim_accumulator': word(pr, 0x1a),
                       'shadowrun_burst_anim_threshold': word(pr, 0x1c),
                       'shadowrun_burst_anim_index': word(pr, 0x1e),
                       'shadowrun_player_damage_hp': start[0x14c], 'shadowrun_player_damage_armor': start[0x176],
                       'shadowrun_x_min': word(start, 0xddd6), 'shadowrun_x_max': word(start, 0xddd2),
                       'shadowrun_y_min': word(start, 0xddd8), 'shadowrun_y_max': word(start, 0xddd4)})
    checked_rng = 0
    reaction_handoffs = 0
    previous = start
    for n in range(6001, args.end + 1):
        observed = frame(n)
        # Actor service precedes this projectile's callback in source order.
        # Feed the captured current-frame actor positions and shared map; their
        # motion is independently modeled and is not asserted by this check.
        machine.set_state({'shadowrun_burst_rng': word(previous, 0xf9f8),
                           'shadowrun_terrain_map': list(observed[0x1700:0x2200]),
                           'shadowrun_hostile_motion_player_x': word(observed, 0x100),
                           'shadowrun_hostile_motion_player_y': word(observed, 0x104),
                           'shadowrun_target_x': [word(observed, 0x400 + i * 0x100) for i in range(7)],
                           'shadowrun_target_y': [word(observed, 0x404 + i * 0x100) for i in range(7)],
                           'shadowrun_target_flags': [observed[0x410 + i * 0x100] for i in range(7)],
                           'shadowrun_play_actor_hp': [observed[0x44c + i * 0x100] for i in range(7)]})
        machine.call('shadowrun_hostile_cycle_tick'); s = machine.snapshot(); pr = observed[0xb00:0xc00]
        actual = (long(pr, 0), long(pr, 4), word(pr, 0x2e), word(pr, 0x4c), word(pr, 0x4e),
                  pr[0x10], pr[0x11], pr[0x41], pr[0x89], pr[0x9f], word(pr, 0x16), word(pr, 0x18),
                  word(pr, 0x1a), word(pr, 0x1e), observed[0x14c])
        expected = tuple(s[k] for k in ('shadowrun_burst_x', 'shadowrun_burst_y', 'shadowrun_burst_heading',
                          'shadowrun_burst_vx', 'shadowrun_burst_vy', 'shadowrun_burst_flags',
                          'shadowrun_burst_flags_low', 'shadowrun_burst_counter', 'shadowrun_burst_lifetime',
                          'shadowrun_burst_effect', 'shadowrun_burst_anim_word', 'shadowrun_burst_anim_increment',
                          'shadowrun_burst_anim_accumulator', 'shadowrun_burst_anim_index', 'shadowrun_player_damage_hp'))
        if not s['shadowrun_hostile_cycle_supported'] or actual != expected:
            raise AssertionError((n, actual, expected, s['shadowrun_hostile_motion_state']))
        if args.from_launch or n <= 6032:
            if s['shadowrun_burst_rng'] != word(observed, 0xf9f8):
                raise AssertionError(f'shared RNG mismatch at frame {n}')
            checked_rng += 1
        if s['shadowrun_hostile_cycle_reaction']:
            if s['shadowrun_hostile_cycle_reaction'] != 1:
                raise AssertionError('unqualified non-player reaction')
            # Independently qualify the source reaction start and the first
            # sprite pass before acknowledging the transactional handoff.
            reaction = GameMachine(lift_player_reaction(rom), {0: rom})
            reaction.set_state({'shadowrun_reaction_kind': word(previous, 0x10e),
                                'shadowrun_reaction_flags': previous[0x110],
                                'shadowrun_reaction_flags_low': previous[0x111],
                                'shadowrun_reaction_hp': observed[0x14c],
                                'shadowrun_reaction_max_hp': previous[0x19c],
                                'shadowrun_reaction_heading': word(previous, 0x12e),
                                'shadowrun_reaction_increment': word(previous, 0x118),
                                'shadowrun_reaction_accumulator': word(previous, 0x11a),
                                'shadowrun_reaction_threshold': word(previous, 0x11c),
                                'shadowrun_reaction_index': word(previous, 0x11e)})
            for action in ('shadowrun_reaction_start', 'shadowrun_reaction_advance', 'shadowrun_reaction_select'):
                reaction.call(action)
                if not reaction.snapshot()['shadowrun_reaction_supported']:
                    raise AssertionError(f'player reaction unsupported at frame {n}')
            reaction_state = reaction.snapshot()
            got = tuple(reaction_state['shadowrun_reaction_' + k] for k in
                        ('callback', 'animation', 'increment', 'accumulator', 'index', 'counter'))
            expected_reaction = (long(observed, 0x13a), word(observed, 0x116), word(observed, 0x118),
                                 word(observed, 0x11a), word(observed, 0x11e), observed[0x1ce])
            if got != expected_reaction:
                raise AssertionError((n, got, expected_reaction))
            machine.set_state({'shadowrun_hostile_cycle_reaction': 0})
            reaction_handoffs += 1
        previous = observed
    out = Path(args.output)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(mode=0o700, parents=True)
    result = {'status': 'passed', 'frame_start': 6000, 'frame_end': args.end,
              'transitions': args.end - 6000, 'shared_rng_checked': checked_rng,
              'source_reaction_handoffs_checked': reaction_handoffs,
              'source_sha256': sha(rom), 'capture_receipt_sha256': sha(receipt_raw),
              'scope': ('assisted from-launch full-core scene; ' if args.from_launch else
                        'assisted post-impact full-core scene; ') + 'observed actor positions and terrain '
                       'fed to projectile model each loop; not NPC motion or natural encounter parity'}
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
