"""Authored river-witness guards; no original assets or native execution."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import examples.agi.verify_river_walk as module


def observed(*, room=41, x=154, y=120, water=False, swimming=0,
             dead=False, width=6, view=0, direction=5):
    return {
        'room': room, 'score': 0,
        'ego': {'x': x, 'y': y, 'direction': direction, 'drawn': True},
        'ego_width': width, 'ego_view': view,
        'in_water': water, 'swimming': swimming, 'dead': dead,
        'bridge_active': False, 'troll_removed': False, 'troll_paid': False,
    }


def authored_route(samples, *, x=154, after_snapshots=None):
    """Supply independent semantic observations at the collector's input seam."""
    run = object.__new__(module.RiverRun)
    run.target_x = x
    run.samples, run.river_observations, run.report = [], [], {}
    run.guest_elapsed = 0
    current = observed(room=1, x=110, y=100)
    current['ego']['direction'] = 0
    crossing = False
    index = 0

    def state():
        return deepcopy(current)

    def move(key, *, room=None, axis=None, target=None, **kwargs):
        nonlocal current
        if room is not None:
            current['room'] = room
            current['ego'].update(x=0 if room == 8 else 70, y=100 if room == 8 else 43)
        if axis:
            current['ego'][axis] = target
        return state()

    def align():
        current['ego']['x'] = x

    def snapshot(name):
        nonlocal current
        if after_snapshots and name in after_snapshots:
            current = deepcopy(after_snapshots[name])
        item = {'id': name, 'state': state(), 'frame': {'sha256': 'authored-frame'}}
        run.river_observations.append(item)
        return item

    def press(key, *args, **kwargs):
        nonlocal current, crossing
        if key == 'down' and not crossing:
            crossing = True
            current = deepcopy(samples[0])

    def advance(ms):
        nonlocal current, index
        run.guest_elapsed += ms
        if crossing:
            index = min(index + 1, len(samples) - 1)
            current = deepcopy(samples[index])

    def neutral():
        current['ego']['direction'] = 0

    def ready():
        neutral()
        return state()

    run.state, run.move, run.align = state, move, align
    run.snapshot, run.press, run.advance = snapshot, press, advance
    run.ready, run.neutral = ready, neutral
    return run


@pytest.mark.parametrize('death_flag,expected_dead', [(63, True), (50, False)])
def test_native_state_uses_the_qualified_width_word_and_death_flag(monkeypatch, death_flag, expected_dead):
    """KQ1's shared death completion is f63, independent of f50."""
    run = object.__new__(module.RiverRun)
    run.ds = 0x20000
    memory = bytearray(0x30000)
    table = 0x3000
    memory[run.ds + 0x963:run.ds + 0x965] = table.to_bytes(2, 'little')
    memory[run.ds + table + 26:run.ds + table + 28] = (6).to_bytes(2, 'little')
    memory[run.ds + table + 7] = 0
    memory[run.ds + 0x109 + death_flag // 8] |= 0x80 >> (death_flag % 8)
    run.d = SimpleNamespace(memory=memory)
    monkeypatch.setattr(module, 'read', lambda session, address, size: bytes(session.memory[address:address + size]))
    monkeypatch.setattr(module.GoatRun, 'state', lambda self: {'room': 41, 'ego': {'x': 154, 'y': 120}})

    result = run.state()

    assert result['ego_width'] == 6
    assert result['ego_view'] == 0
    assert result['dead'] is expected_dead


@pytest.mark.parametrize('water,swimming', [(True, 0), (False, 1)])
def test_adjacent_control_accepts_water_at_the_actual_river(water, swimming):
    run = authored_route([observed(x=153, water=water, swimming=swimming)], x=153)

    result = run.route()

    assert result['complete'] is True
    assert result['result'] == 'adjacent-pixel-enters-water'
    assert run.report['river_control_water_observed'] is True


@pytest.mark.parametrize('sample,target,accepted', [
    (observed(x=153, y=109, water=True), 153, True),
    (observed(x=153, y=150, swimming=1), 153, True),
    (observed(x=153, y=108, water=True), 153, False),
    (observed(x=153, y=151, water=True), 153, False),
    (observed(x=153), 153, False),
    (observed(x=153, water=True), 154, False),
    (observed(room=42, x=153, water=True), 153, False),
    (observed(x=152, water=True), 153, False),
])
def test_adjacent_water_predicate_has_exact_spatial_and_experiment_scope(sample, target, accepted):
    assert bool(module.adjacent_water(sample, target)) is accepted


def test_control_preserves_the_trigger_before_later_snapshot_execution():
    trigger = observed(x=153, y=120, water=True)
    later = observed(x=153, y=142, swimming=1, view=93)
    run = authored_route([trigger], x=153, after_snapshots={'adjacent-enters-water': later})

    result = run.route()

    assert result['trigger_state'] == trigger
    assert result['state'] == later


@pytest.mark.parametrize('sample', [
    observed(room=42, x=153, water=True),
    observed(x=152, water=True),
    observed(x=153, y=80, water=True),
])
def test_adjacent_control_refuses_water_outside_the_declared_baseline(sample):
    run = authored_route([sample], x=153)

    with pytest.raises(RuntimeError):
        run.route()

    assert not run.report.get('river_control_water_observed')


@pytest.mark.parametrize('sample', [
    observed(room=40, water=True),
    observed(room=40, swimming=1),
    observed(room=40, dead=True),
])
def test_boundary_never_accepts_an_unsafe_final_state(sample):
    run = authored_route([sample])

    with pytest.raises(RuntimeError):
        run.route()

    assert not run.report.get('river_edge_crossing_complete')


@pytest.mark.parametrize('later', [
    observed(room=40, water=True, direction=0),
    observed(room=40, swimming=1, direction=0),
    observed(room=40, dead=True, direction=0),
    observed(room=41, direction=0),
    observed(room=40, x=153, direction=0),
    observed(room=40, width=7, direction=0),
    observed(room=40, view=93, direction=0),
    observed(room=40, direction=5),
])
def test_boundary_revalidates_after_native_time_spent_capturing_the_final_frame(later):
    run = authored_route([observed(room=40)], after_snapshots={'river-crossed': later})

    with pytest.raises(RuntimeError):
        run.route()

    assert not run.report.get('river_edge_crossing_complete')


def test_adjacent_dry_crossing_is_not_reported_as_the_boundary_experiment():
    run = authored_route([observed(room=40, x=153)], x=153)

    with pytest.raises(RuntimeError, match='Adjacent control crossed'):
        run.route()

    assert not run.report.get('river_edge_crossing_complete')


def test_boundary_crossing_retains_the_exact_edge_alignment():
    run = authored_route([observed(room=40, x=153)])

    with pytest.raises(RuntimeError):
        run.route()

    assert not run.report.get('river_edge_crossing_complete')


@pytest.mark.parametrize('width,view', [(7, 0), (6, 93)])
def test_boundary_refuses_a_changed_actor_geometry_or_view(width, view):
    run = authored_route([observed(room=40, width=width, view=view)])

    with pytest.raises(RuntimeError):
        run.route()

    assert not run.report.get('river_edge_crossing_complete')


def test_boundary_accepts_a_clean_aligned_crossing_without_troll_resolution():
    run = authored_route([observed(), observed(room=40, y=43)])

    result = run.route()

    assert result['complete'] is True
    assert result['result'] == 'boundary-waterwalk'
    assert run.report['river_edge_crossing_complete'] is True
    assert [item['id'] for item in run.river_observations] == [
        'river-before', 'river-middle', 'river-crossed',
    ]


def test_alignment_refuses_overshoot_before_any_corrective_key():
    run = object.__new__(module.RiverRun)
    run.target_x, run.guest_elapsed = 154, 0
    run.move = lambda *args, **kwargs: None
    run.ready = lambda: None
    keys = []
    run.press = lambda key, *args, **kwargs: keys.append(key)
    run.state = lambda: observed(x=155)
    run.neutral = lambda: pytest.fail('Overshoot must be preserved without another key')

    with pytest.raises(RuntimeError, match='Alignment crossed'):
        run.align()

    assert keys == ['right']


def test_alignment_requires_the_exact_position_after_stopping():
    run = object.__new__(module.RiverRun)
    run.target_x, run.guest_elapsed = 154, 0
    run.move = lambda *args, **kwargs: None
    run.ready = lambda: None
    run.press = lambda *args, **kwargs: None
    states = iter([observed(x=154), observed(x=153)])
    run.state = lambda: next(states)
    run.neutral = lambda: None

    with pytest.raises(RuntimeError, match='did not settle at exact border'):
        run.align()
