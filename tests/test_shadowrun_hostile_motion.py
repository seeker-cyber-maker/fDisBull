from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_hostile_motion import SOURCE


def machine():
    m = GameMachine(author_program(SOURCE.read_text()))
    m.set_state({'shadowrun_hostile_motion_profile': 1, 'shadowrun_hostile_motion_state': 1,
                 'shadowrun_hostile_motion_x': 15920 * 65536,
                 'shadowrun_hostile_motion_y': 11210 * 65536,
                 'shadowrun_hostile_motion_vx': 0xa000, 'shadowrun_hostile_motion_vy': 0,
                 'shadowrun_hostile_motion_lifetime': 32, 'shadowrun_hostile_motion_effect': 5,
                 'shadowrun_hostile_motion_player_x': 15584, 'shadowrun_hostile_motion_player_y': 11210,
                 'shadowrun_x_min': 44, 'shadowrun_x_max': 1876,
                 'shadowrun_y_min': 44, 'shadowrun_y_max': 1304})
    return m


def test_hit_and_zero_effect_miss_are_distinct():
    for effect, state in ((5, 2), (0, 5)):
        m = machine(); m.set_state({'shadowrun_hostile_motion_effect': effect})
        m.call('shadowrun_hostile_motion_tick'); s = m.snapshot()
        assert (s['shadowrun_hostile_motion_supported'], s['shadowrun_hostile_motion_state'],
                s['shadowrun_hostile_motion_lifetime']) == (1, state, 29)
        assert (s['shadowrun_hostile_motion_x'] // 65536,
                s['shadowrun_hostile_motion_y'] // 65536) == (15584, 11226)


def test_flight_wall_and_expiry():
    for name, state, life in (('flight', 1, 28), ('wall', 3, 32), ('expiry', 4, 255)):
        m = machine(); m.set_state({'shadowrun_hostile_motion_player_x': 15000})
        if name == 'wall':
            terrain = [0] * 2816; terrain[1374] = 127
            m.set_state({'shadowrun_terrain_map': terrain})
        if name == 'expiry':
            m.set_state({'shadowrun_hostile_motion_lifetime': 0})
        m.call('shadowrun_hostile_motion_tick'); s = m.snapshot()
        assert (s['shadowrun_hostile_motion_supported'], s['shadowrun_hostile_motion_state'],
                s['shadowrun_hostile_motion_lifetime']) == (1, state, life)


def test_unknown_terrain_and_nonplayer_collision_do_not_mutate_projectile():
    for other_actor in (False, True):
        m = machine(); m.set_state({'shadowrun_hostile_motion_player_x': 15000})
        if other_actor:
            m.set_state({'shadowrun_target_x': [0, 15824, 0, 0, 0, 0, 0],
                         'shadowrun_target_y': [0, 11210, 0, 0, 0, 0, 0],
                         'shadowrun_target_flags': [0, 1, 0, 0, 0, 0, 0],
                         'shadowrun_play_actor_hp': [0, 10, 0, 0, 0, 0, 0]})
        else:
            terrain = [0] * 2816; terrain[1374] = 1
            m.set_state({'shadowrun_terrain_map': terrain})
        before = m.snapshot(); m.call('shadowrun_hostile_motion_tick'); after = m.snapshot()
        assert after['shadowrun_hostile_motion_supported'] == 0
        assert all(after[k] == before[k] for k in (
            'shadowrun_hostile_motion_x', 'shadowrun_hostile_motion_y',
            'shadowrun_hostile_motion_lifetime', 'shadowrun_hostile_motion_state'))


def test_shooter_contact_is_separate_from_other_npc_and_player_contacts():
    for effect, expected in ((5, 6), (0, 7)):
        m = machine()
        m.set_state({'shadowrun_hostile_motion_player_x': 15000,
                     'shadowrun_hostile_motion_effect': effect,
                     'shadowrun_target_x': [15824, 0, 0, 0, 0, 0, 0],
                     'shadowrun_target_y': [11210, 0, 0, 0, 0, 0, 0],
                     'shadowrun_target_flags': [5, 0, 0, 0, 0, 0, 0],
                     'shadowrun_play_actor_hp': [10, 0, 0, 0, 0, 0, 0]})
        m.call('shadowrun_hostile_motion_tick'); s = m.snapshot()
        assert (s['shadowrun_hostile_motion_supported'], s['shadowrun_hostile_motion_state'],
                s['shadowrun_hostile_motion_continuation_required']) == (1, expected, 1)
