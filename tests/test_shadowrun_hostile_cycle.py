"""Transactional composition and source sprite/burst sequencing."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_hostile_cycle import (
    ANIMATION, BURST, DAMAGE, MOTION, SELF_HIT, SOURCE, TRANSACTION_SOURCE,
)


def machine():
    prelude = ('typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;\n'
               'u8 rom8(u8 region,u32 offset); u16 rom16(u8 region,u32 offset);\n'
               'u8 shadowrun_terrain_map[2816],shadowrun_target_flags[7],shadowrun_play_actor_hp[7];\n'
               'u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;\n'
               'u16 shadowrun_target_x[7],shadowrun_target_y[7];\n')
    parts = []
    for path in (MOTION, ANIMATION, BURST, DAMAGE, SELF_HIT, SOURCE, TRANSACTION_SOURCE):
        parts.append('\n'.join(line for line in path.read_text().splitlines()
                               if not line.startswith(('typedef ', 'extern ', 'u8 rom8(', 'u16 rom16('))))
    rom = bytearray(0x170000)
    rom[0x62b0:0x62b4] = (0x200).to_bytes(4, 'big')
    for offset, target, count, increment in ((12, 0x300, 5, 1024), (20, 0x310, 1, 2)):
        rom[0x200 + offset:0x204 + offset] = target.to_bytes(4, 'big')
        rom[target:target + 4] = (0x8000 | count).to_bytes(2, 'big') + increment.to_bytes(2, 'big')
    return GameMachine(author_program(prelude + '\n'.join(parts)), {0: bytes(rom)})


def prepared(m):
    m.set_state({'shadowrun_burst_profile': 1, 'shadowrun_burst_flags': 1,
                 'shadowrun_burst_flags_low': 9, 'shadowrun_burst_counter': 2,
                 'shadowrun_burst_anim_word': 12, 'shadowrun_burst_anim_threshold': 4096,
                 'shadowrun_burst_origin_x': 15920, 'shadowrun_burst_origin_y': 11210,
                 'shadowrun_burst_heading': 0xc000, 'shadowrun_burst_rng': 2,
                 'shadowrun_player_damage_hp': 5, 'shadowrun_player_damage_armor': 1,
                 'shadowrun_play_actor_hp': [10, 0, 0, 0, 0, 0, 0],
                 'shadowrun_x_min': 44, 'shadowrun_x_max': 1876,
                 'shadowrun_y_min': 44, 'shadowrun_y_max': 1304})


def test_animation_boundary_then_source_burst_on_next_actor_pass():
    m = machine(); prepared(m)
    for _ in range(21):
        m.call('shadowrun_hostile_cycle_tick')
        assert m.snapshot()['shadowrun_hostile_cycle_supported'] == 1
    s = m.snapshot()
    assert s['shadowrun_burst_anim_word'] == 0x800c and s['shadowrun_burst_counter'] == 2
    m.call('shadowrun_hostile_cycle_tick'); s = m.snapshot()
    assert (s['shadowrun_hostile_cycle_supported'], s['shadowrun_burst_counter'],
            s['shadowrun_burst_anim_word'], s['shadowrun_burst_anim_increment'],
            s['shadowrun_burst_lifetime']) == (1, 1, 20, 2, 32)


def test_unsupported_late_sprite_or_damage_rolls_back_all_shared_state():
    for mode in ('animation', 'damage', 'pending-reaction'):
        m = machine(); prepared(m)
        if mode == 'animation':
            m.set_state({'shadowrun_burst_anim_threshold': 0})
        elif mode == 'damage':
            m.set_state({'shadowrun_burst_flags_low': 1, 'shadowrun_burst_effect': 5,
                         'shadowrun_burst_lifetime': 32, 'shadowrun_burst_x': 15920 * 65536,
                         'shadowrun_burst_y': 11210 * 65536, 'shadowrun_burst_vx': 0xa000,
                         'shadowrun_hostile_motion_player_x': 15584,
                         'shadowrun_hostile_motion_player_y': 11210})
        else:
            m.set_state({'shadowrun_hostile_cycle_reaction': 1})
        before = m.snapshot(); m.call('shadowrun_hostile_cycle_tick'); after = m.snapshot()
        assert after['shadowrun_hostile_cycle_supported'] == 0
        assert {k: v for k, v in after.items() if k != 'shadowrun_hostile_cycle_supported'} == {
            k: v for k, v in before.items() if k != 'shadowrun_hostile_cycle_supported'}
