"""Contract checks for the bounded assisted hostile actor slice."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_hostile import SOURCE


def machine():
    return GameMachine(author_program(SOURCE.read_text()), {0: bytes(0x17000)})


def prepared(m):
    m.set_state({'shadowrun_hostile_profile': 1, 'shadowrun_hostile_x': 16096,
                 'shadowrun_hostile_y': 11210, 'shadowrun_hostile_player_x': 15584,
                 'shadowrun_hostile_player_y': 11210, 'shadowrun_hostile_ammo': 48,
                 'shadowrun_hostile_contact': 203, 'shadowrun_x_min': 44,
                 'shadowrun_x_max': 1876, 'shadowrun_y_min': 44, 'shadowrun_y_max': 1304,
                 'shadowrun_hostile_rng': 65535})


def test_service_timer_updates_without_firing():
    m = machine(); prepared(m); m.set_state({'shadowrun_hostile_timer': 2})
    m.call('shadowrun_hostile_tick'); s = m.snapshot()
    assert (s['shadowrun_hostile_supported'], s['shadowrun_hostile_fired'],
            s['shadowrun_hostile_timer'], s['shadowrun_hostile_cooldown'],
            s['shadowrun_hostile_ammo'], s['shadowrun_hostile_rng']) == (1, 0, 1, 65535, 48, 65535)


def test_refused_conditions_do_not_commit_actor_or_projectile_state():
    for update in ({'shadowrun_hostile_contact': 0},
                   {'shadowrun_hostile_ammo': 0},
                   {'shadowrun_hostile_profile': 0}):
        m = machine(); prepared(m); m.set_state(update)
        before = m.snapshot(); m.call('shadowrun_hostile_tick'); after = m.snapshot()
        assert after['shadowrun_hostile_supported'] == 0
        diagnostics = ('shadowrun_hostile_supported', 'shadowrun_hostile_los_result',
                       'shadowrun_hostile_los_clear')
        assert {k: v for k, v in after.items() if k not in diagnostics} == {
            k: v for k, v in before.items() if k not in diagnostics}


def test_blocked_or_unrecovered_terrain_fails_closed():
    for terrain, result in ((127, 2), (128, 2), (1, 0)):
        m = machine(); prepared(m)
        cells = [0] * 2816; cells[1375] = terrain
        m.set_state({'shadowrun_terrain_map': cells}); before = m.snapshot()
        m.call('shadowrun_hostile_tick'); after = m.snapshot()
        assert (after['shadowrun_hostile_supported'], after['shadowrun_hostile_los_result']) == (0, result)
        assert after['shadowrun_hostile_ammo'] == before['shadowrun_hostile_ammo']
        assert after['shadowrun_hostile_rng'] == before['shadowrun_hostile_rng']


def test_zero_effect_is_a_fired_miss_and_target_selection_persists():
    m = machine(); prepared(m); m.call('shadowrun_hostile_tick'); s = m.snapshot()
    assert (s['shadowrun_hostile_supported'], s['shadowrun_hostile_fired'],
            s['shadowrun_hostile_effect'], s['shadowrun_hostile_ammo'],
            s['shadowrun_hostile_target_existing'], s['shadowrun_hostile_lifetime']) == (1, 1, 0, 47, 1, 32)


def test_cooldown_reports_pending_source_pursuit_without_firing():
    m = machine(); prepared(m); m.set_state({'shadowrun_hostile_cooldown': 2})
    m.call('shadowrun_hostile_tick'); s = m.snapshot()
    assert (s['shadowrun_hostile_supported'], s['shadowrun_hostile_pursuit_required'],
            s['shadowrun_hostile_cooldown'], s['shadowrun_hostile_ammo'],
            s['shadowrun_hostile_timer'], s['shadowrun_hostile_fired']) == (1, 1, 1, 48, 20, 0)
    m.call('shadowrun_hostile_tick'); after = m.snapshot()
    assert after['shadowrun_hostile_supported'] == 0
    assert (after['shadowrun_hostile_timer'], after['shadowrun_hostile_rng']) == (
        s['shadowrun_hostile_timer'], s['shadowrun_hostile_rng'])
