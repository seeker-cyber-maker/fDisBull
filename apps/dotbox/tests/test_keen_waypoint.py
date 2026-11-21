"""Authored physics cases and a saved numeric trace; no live-game qualification."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    'keen_waypoint', Path(__file__).resolve().parents[1] / 'scripts/experiments/keen_waypoint.py')
waypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(waypoint)

STAND = 0x0FE8
W1, W2, W3, W4 = 0x1498, 0x14B6, 0x14D4, 0x14F2


def player(x=33280, state=STAND, ticcount=1, xdir=-1, xmove=0):
    return {'x': x, 'state': state, 'ticcount': ticcount, 'xdir': xdir, 'xmove': xmove}


def state(motion=None, axis=0, ymove=0):
    motion = motion or player()
    walking = motion['state'] in (W1, W2, W3, W4)
    following = (W2, W3, W4, W1)[(W1, W2, W3, W4).index(motion['state'])] if walking else STAND
    return {'phase': 'pre_input', 'coherent_game_update': True, 'corridor_verified': True,
            'level': 1, 'playstate': 0, 'lives': 3,
            'map': {'width': 136, 'height': 37, 'plane_segments': [24888, 26106, 26735],
                    'tile_info_segment': 9336},
            'clock': {'tics': 2, 'time_count': 895, 'last_time_count': 895},
            'camera': {'x': 29184, 'y': 5632, 'tile_x': 114, 'tile_y': 22},
            'input': {'xaxis': axis, 'yaxis': 0, 'button0': 0, 'button1': 0,
                      'button0held': 0, 'button1held': 0},
            'player': {**motion, 'y': 7695, 'ymove': ymove, 'nothink': 0,
                       'hitnorth': 1, 'hiteast': 0, 'hitsouth': 0, 'hitwest': 0,
                       'left': motion['x'] + 64, 'right': motion['x'] + 304,
                       'top': 7695, 'bottom': 8191,
                       'state_record': {'progress': 4 if walking else 3,
                            'skippable': int(walking), 'push_to_floor': 1,
                            'tic_time': 6 if walking else 4, 'x_move': 24 if walking else 0,
                            'y_move': 0 if walking else 16, 'next_state': following}},
            'nearby': [{'slot': 31, 'class_name': 'bonus', 'active': 1,
                        'left': 32000, 'top': 6912, 'right': 32240, 'bottom': 7152}]}


def args(**changes):
    return SimpleNamespace(**({'direction': 'left', 'distance_px': 32, 'input_delay_updates': 1,
                               'tolerance_px': 3, 'cycles': 80, 'settle_samples': 3} | changes))


def observation(sequence, data):
    data = deepcopy(data)
    data['clock']['time_count'] += sequence * 2
    data['clock']['last_time_count'] += sequence * 2
    return {'sequence': sequence, 'state': data, 'coherence': 'qualified_hook'}


# The prior threshold-release run: 32 px requested, 39 px actually traveled.
# Values are observations, independent of the predictor's algorithm.
OLD_TRACE = [
    (33280, STAND, 3, 0, 0), (33208, W1, 1, -72, -1),
    (33160, W1, 3, -48, -1), (33112, W1, 5, -48, -1),
    (33064, W2, 1, -48, -1), (33016, W2, 3, -48, -1),
    (32968, W2, 5, -48, -1), (32920, W3, 1, -48, -1),
    (32872, W3, 3, -48, -1), (32824, W3, 5, -48, -1),
    (32776, W4, 1, -48, -1), (32728, W4, 3, -48, -1),
    (32680, W4, 5, -48, -1), (32656, STAND, 1, -24, 0),
    (32656, STAND, 3, 0, 0),
]


def test_saved_fifteen_update_trace_including_start_and_release():
    current = player()
    delayed_axis = 0
    for index, (x, action, ticcount, xmove, sampled_axis) in enumerate(OLD_TRACE):
        desired_axis = -1 if index < 12 else 0
        assert delayed_axis == sampled_axis
        current = waypoint.predict_update(current, delayed_axis)
        assert current == player(x, action, ticcount, -1, xmove)
        delayed_axis = desired_axis
    assert (33280 - current['x']) / 16 == 39


@pytest.mark.parametrize('phase,dx,next_phase', [(0, 48, 0), (1, 48, 0), (2, 48, 0), (3, 72, 1)])
@pytest.mark.parametrize('direction', [-1, 1])
def test_stand_start_uses_global_ticks_and_state_boundary_excess(phase, dx, next_phase, direction):
    assert waypoint.predict_update(player(ticcount=phase), direction) == player(
        33280 + direction * dx, W1, next_phase, direction, direction * dx)


@pytest.mark.parametrize('phase,dx,next_phase', [(0, 48, 0), (1, 48, 0), (2, 48, 0),
                                                (3, 48, 0), (4, 48, 0), (5, 24, 1)])
@pytest.mark.parametrize('action', [W1, W2, W3, W4])
@pytest.mark.parametrize('direction', [-1, 1])
def test_release_moves_before_thinker_can_enter_stand(phase, dx, next_phase, action, direction):
    assert waypoint.predict_update(player(state=action, ticcount=phase, xdir=direction), 0) == player(
        33280 + direction * dx, STAND, next_phase, direction, direction * dx)


@pytest.mark.parametrize('phase,travel', [(0, 96), (1, 96), (2, 96), (3, 72), (4, 96), (5, 96)])
def test_calibrated_one_update_delay_changes_release_phase(phase, travel):
    assert waypoint.predict_stop_x(player(state=W4, ticcount=phase), 1) == 33280 - travel


def test_last_walk_state_wraps_and_neutral_standing_does_not_drift():
    assert waypoint.predict_update(player(state=W4, ticcount=5), -1) == player(33232, W1, 1, -1, -48)
    assert waypoint.predict_update(player(ticcount=3), 0) == player(ticcount=1)


def test_nearest_reachable_choice_accounts_for_uneven_stop_spacing():
    now, later = waypoint.stop_choices(player(32872, W3, 3, -1, -48), 1)
    assert (now, later) == (32800, 32728)
    assert abs(now - 32768) == 32  # 30 px total, 2 px short.
    assert abs(later - 32768) == 40  # 34.5 px total, 2.5 px past.


@pytest.mark.parametrize('tolerance,outcome', [(3, 'settled'), (1, 'outside_tolerance')])
def test_policy_releases_early_and_confirms_three_stable_coordinates(tolerance, outcome):
    policy = waypoint.make_policy(state(), args(tolerance_px=tolerance))
    assert policy(observation(0, state())) == {'left'}
    for sequence, (x, action, phase, dx, axis) in enumerate(OLD_TRACE[:9], 1):
        value = policy(observation(sequence, state(player(x, action, phase, -1, dx), axis)))
        assert value == (set() if sequence == 9 else {'left'})
    # Independently calculated continuation after early release at sample 9.
    follow = [
        (10, 32824, W3, 5, -48, -1, 64),
        (11, 32800, STAND, 1, -24, 0, 40),
        (12, 32800, STAND, 3, 0, 0, 0),
        (13, 32800, STAND, 1, 0, 0, 16),
        (14, 32800, STAND, 3, 0, 0, 0),
    ]
    for sequence, x, action, phase, dx, axis, dy in follow:
        value = policy(observation(sequence, state(player(x, action, phase, -1, dx), axis, dy)))
        assert value == (None if sequence == 14 else set())
    assert policy.result['outcome'] == outcome
    assert policy.result['settled_x'] == 32800
    assert policy.result['error_px'] == 2
    assert policy.result['stable_samples'] == 3
    assert policy.result['release_sequence'] == 9


@pytest.mark.parametrize('path,value,reason', [
    (('clock', 'tics'), 3, 'ticks'),
    (('map', 'width'), 135, 'map'),
    (('map', 'plane_segments'), [24889, 26106, 26735], 'map'),
    (('map', 'tile_info_segment'), 9337, 'map'),
    (('player', 'hitnorth'), 0, 'floor'),
    (('player', 'hitnorth'), 2, 'floor'),
    (('player', 'hitnorth'), 9, 'floor'),
    (('player', 'hiteast'), 1, 'contact'),
    (('player', 'state'), 0x15E2, 'state'),
    (('player', 'nothink'), 1, 'thinker'),
    (('player', 'y'), 7696, 'corridor'),
    (('player', 'right'), 34304, 'corridor'),
    (('player', 'x'), 33279, 'prediction'),
    (('input', 'xaxis'), -1, 'sampled input'),
    (('input', 'button0'), 1, 'input'),
    (('camera', 'x'), 29183, 'camera'),
    (('phase',), 'post_actor_pre_refresh', 'phase'),
    (('playstate',), 1, 'scene'),
    (('lives',), 2, 'scene'),
    (('corridor_verified',), False, 'corridor'),
])
def test_changed_assumption_refuses_without_another_hold(path, value, reason):
    policy = waypoint.make_policy(state(), args())
    assert policy(observation(0, state())) == {'left'}
    data = state(player(ticcount=3))
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert policy(observation(1, data)) is None
    assert policy.result['outcome'] == 'refused'
    assert reason in policy.result['reason'].lower()
    assert policy(observation(2, state())) is None  # Terminal; no automatic retry.


def test_new_active_threat_and_missing_required_fields_refuse():
    data = state()
    data['nearby'][0]['class_name'] = 'tater'
    with pytest.raises(ValueError, match='actor'):
        waypoint.make_policy(data, args())
    del data['player']['nothink']
    with pytest.raises(ValueError):
        waypoint.make_policy(data, args())


@pytest.mark.parametrize('change', [{'input_delay_updates': None}, {'input_delay_updates': 2},
                                   {'input_delay_updates': True}, {'direction': 'up'},
                                   {'distance_px': 0}, {'distance_px': 1}, {'distance_px': 100},
                                   {'direction': 'right', 'distance_px': 40}, {'tolerance_px': 4}])
def test_invalid_parameters_do_not_create_a_control_policy(change):
    values = vars(args()) | change
    with pytest.raises(ValueError):
        waypoint.make_policy(state(), SimpleNamespace(**values))


def test_coherence_and_observation_sequence_are_not_inferred():
    policy = waypoint.make_policy(state(), args())
    value = observation(0, state())
    value['coherence'] = 'renderer_unqualified'
    assert policy(value) is None
    assert 'coherence' in policy.result['reason']
    policy = waypoint.make_policy(state(), args())
    assert policy(observation(0, state())) == {'left'}
    assert policy(observation(0, state())) is None
    assert 'sequence' in policy.result['reason']


def test_motion_prediction_refuses_reversal_and_non_two_tick_updates():
    with pytest.raises(ValueError, match='reversal'):
        waypoint.predict_update(player(state=W1), 1)
    with pytest.raises(ValueError, match='ticks'):
        waypoint.predict_update(player(), -1, tics=3)
