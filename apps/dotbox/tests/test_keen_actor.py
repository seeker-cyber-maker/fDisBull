"""Authored source-semantic cases, not active-enemy gameplay qualification."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'keen_actor', Path(__file__).resolve().parents[1] / 'scripts/experiments/keen_actor.py')
actor_model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actor_model)

SOURCE = 'a' * 64
WALKS = (100, 130, 160, 190)
LEAP = 220
FOLLOWING = {100: 130, 130: 160, 160: 190, 190: 100}


def profile():
    return {'format': actor_model.PROFILE_FORMAT, 'source_sha256': SOURCE,
            'qualification': 'authored-fixture-only', 'walk_states': list(WALKS), 'leap_state': LEAP}


def actor(state=100, count=0, direction=1, **changes):
    walking = state in FOLLOWING
    return {'class_name': 'carrot', 'active': 1, 'state': state, 'ticcount': count,
            'xdir': direction, 'xmove': 128, 'ymove': 144, 'xspeed': 0, 'yspeed': 0,
            'hitnorth': 1, 'hiteast': 0, 'hitsouth': 0, 'hitwest': 0,
            'state_record': {'progress': 0 if walking else 2, 'skippable': 0,
                             'push_to_floor': int(walking), 'tic_time': 5 if walking else 0,
                             'x_move': 128 if walking else 0, 'y_move': 0,
                             'next_state': FOLLOWING[state] if walking else 0}, **changes}


def predict(value, **changes):
    return actor_model.CarrotModel(profile()).predict_walk_phase(
        value, **({'tics': 2, 'source_sha256': SOURCE} | changes))


def react(value, **changes):
    return actor_model.CarrotModel(profile()).reaction_decision(
        value, **({'tics': 2, 'source_sha256': SOURCE, 'phase': 'reaction_callback_entry'} | changes))


# A five-tick step state moves only at expiry; excess ticks enter the next state.
@pytest.mark.parametrize('count,next_count,crossed', [(0, 2, False), (1, 3, False),
                                                     (2, 4, False), (3, 0, True), (4, 1, True)])
@pytest.mark.parametrize('state,next_state', [(100, 130), (130, 160), (160, 190), (190, 100)])
@pytest.mark.parametrize('direction,step', [(-1, -128), (1, 128)])
def test_walk_phase_expected_counter_boundary_and_proposed_motion(count, next_count, crossed,
                                                                 state, next_state, direction, step):
    result = predict(actor(state, count, direction))
    assert (result['state'], result['ticcount']) == (next_state if crossed else state, next_count)
    assert result['proposed_xmove'] == (step if crossed else 0)
    assert result['proposed_ymove'] == 0
    assert result['crossed_state_boundary'] is crossed
    assert result['collision_resolved'] is False
    assert result['scope'] == 'state_machine_before_clipping'
    assert 'x' not in result and 'y' not in result


def test_ground_walk_does_not_integrate_xspeed_or_previous_movement():
    first = predict(actor(count=3, xspeed=99, xmove=-200, ymove=255))
    second = predict(actor(count=3, xspeed=0, xmove=0, ymove=0))
    assert first == second
    assert first['proposed_xmove'] == 128


@pytest.mark.parametrize('direction,contacts,decision,effects', [
    (1, {'hitwest': 1, 'hitnorth': 0}, 'turn_left', {'xdir': -1}),
    (-1, {'hiteast': 1, 'hitnorth': 0}, 'turn_right', {'xdir': 1}),
    (1, {'hitwest': 1, 'hiteast': 1}, 'turn_left', {'xdir': -1}),
    (-1, {'hiteast': 1, 'hitwest': 1}, 'turn_right', {'xdir': 1}),
    (1, {'hiteast': 1}, 'no_motion_state_change', {}),
    (-1, {'hitwest': 1}, 'no_motion_state_change', {}),
])
def test_directional_wall_reversal_precedes_ledge_branch(direction, contacts, decision, effects):
    result = react(actor(direction=direction, **contacts))
    assert (result['decision'], result['effects']) == (decision, effects)
    assert result['intermediate_rollback'] is None
    assert result['change_state_reclips'] is False


@pytest.mark.parametrize('direction,xmove,xspeed', [(-1, -128, -32), (1, 128, 32)])
def test_ledge_leap_predicts_speeds_and_state_but_not_final_position(direction, xmove, xspeed):
    result = react(actor(direction=direction, hitnorth=0, xmove=xmove, ymove=144))
    assert result['decision'] == 'ledge_leap'
    assert result['effects'] == {'state': LEAP, 'ticcount': 0, 'xspeed': xspeed, 'yspeed': -40}
    assert result['intermediate_rollback'] == {'x_delta': -xmove, 'y_delta': -144}
    assert result['change_state_reclips'] is True
    assert result['final_position'] is None and result['collision_resolved'] is False


@pytest.mark.parametrize('floor,ceiling,decision,effects,reclips', [
    (0, 0, 'no_motion_state_change', {}, False),
    (0, 1, 'ceiling_stop', {'yspeed': 0}, False),
    (1, 0, 'land', {'state': 100, 'ticcount': 0}, True),
    (1, 1, 'land', {'state': 100, 'ticcount': 0, 'yspeed': 0}, True),
])
def test_air_ceiling_and_floor_checks_are_independent(floor, ceiling, decision, effects, reclips):
    result = react(actor(LEAP, hitnorth=floor, hitsouth=ceiling))
    assert (result['decision'], result['effects']) == (decision, effects)
    assert result['change_state_reclips'] is reclips
    assert result['final_position'] is None


@pytest.mark.parametrize('tics', [0, 1, 3, 6, True, 2.0, '2'])
def test_unsupported_tick_domains_refuse(tics):
    with pytest.raises(ValueError, match='two game ticks'):
        predict(actor(), tics=tics)


def test_source_and_phase_guards_are_not_inferred_from_actor_contents():
    with pytest.raises(ValueError, match='source'):
        predict(actor(), source_sha256='b' * 64)
    with pytest.raises(ValueError, match='phase'):
        react(actor(), phase='pre_input')


@pytest.mark.parametrize('changes', [{'class_name': 'bonus'}, {'active': 0}, {'active': 2},
                                    {'active': True}, {'xdir': 0}, {'xdir': True},
                                    {'state': 999}, {'ticcount': 5}, {'ticcount': -1}])
def test_inactive_wrong_class_and_invalid_walk_state_refuse(changes):
    with pytest.raises(ValueError):
        predict(actor(**changes))


@pytest.mark.parametrize('field,bad', [('progress', 4), ('skippable', 1), ('push_to_floor', 0),
                                    ('tic_time', 6), ('x_move', 24), ('y_move', 1),
                                    ('next_state', 999), ('push_to_floor', True)])
def test_observed_walk_record_must_match_qualified_rule(field, bad):
    value = actor()
    value['state_record'][field] = bad
    with pytest.raises(ValueError, match='State record'):
        predict(value)


def test_air_record_and_contact_types_are_checked():
    value = actor(LEAP)
    value['state_record']['progress'] = 0
    with pytest.raises(ValueError, match='State record'):
        react(value)
    with pytest.raises(ValueError, match='hitnorth'):
        react(actor(hitnorth=True))
    with pytest.raises(ValueError, match='Unmodeled'):
        predict(actor(LEAP))


@pytest.mark.parametrize('change', [{'source_sha256': 'not-a-hash'}, {'qualification': ''},
                                   {'walk_states': [100, 100, 160, 190]},
                                   {'walk_states': [100, 130, 160]}, {'leap_state': 100},
                                   {'leap_state': True}, {'format': 'unknown'}])
def test_invalid_finite_profiles_refuse(change):
    with pytest.raises(ValueError):
        actor_model.CarrotModel(profile() | change)


def test_supplied_profile_and_actor_are_not_mutated_or_aliased():
    configuration = profile()
    model = actor_model.CarrotModel(configuration)
    configuration['walk_states'][1] = 999
    value = actor(count=3)
    original = deepcopy(value)
    result = model.predict_walk_phase(value, tics=2, source_sha256=SOURCE)
    assert result['state'] == 130 and value == original
    reaction = model.reaction_decision(value, tics=2, source_sha256=SOURCE,
                                       phase='reaction_callback_entry')
    reaction['effects']['xdir'] = 77
    assert value == original
