"""Authored adapter observations; these cases do not qualify original gameplay."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from dotbox.oracle import evaluate_oracle
from dotbox.scenes import project_scene


SPEC = importlib.util.spec_from_file_location(
    'keen_oracle', Path(__file__).resolve().parents[1] / 'scripts/experiments/keen_oracle.py')
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
OBSERVATION = 'authored-update-7'


def body(x):
    return {'x': x, 'y': 1000, 'left': x, 'top': 1000,
            'right': x + 100, 'bottom': 1200}


def state(*, carrot_x=650, flowers=2, clock=100):
    return {'phase': 'post_actor_pre_refresh', 'coherent_game_update': True,
            'level': 1, 'playstate': 0, 'difficulty': 2,
            'map': {'width': 136, 'height': 37, 'plane_segments': [101, 102, 103],
                    'tile_info_segment': 104},
            'clock': {'tics': 2, 'time_count': clock}, 'flowers': flowers, 'score': 0,
            'player': {'slot': 0, 'class_name': 'keen', **body(1000)},
            'objects': [
                {'slot': 40, 'pointer': 2000, 'class_name': 'carrot', 'active': 1,
                 **body(carrot_x)},
                {'slot': 31, 'pointer': 3000, 'class_name': 'bonus', 'active': 1,
                 'temp1': 0, **body(1400)}],
            'live_actor_slots': [0, 40, 31]}


def context(revision=7):
    return {'provider_id': 'authored-provider', 'session_id': 'authored-session',
            'branch_id': 'authored-branch', 'revision': revision,
            'context_token': 'PRIVATE_CONTEXT_' + str(revision)}


def choices():
    return [{'id': identity, 'label': identity.replace('_', ' ').capitalize(),
             'requires': [], 'observation_id': OBSERVATION,
             'available': True, 'enabled': True, 'ready': True,
             'route': {'kind': 'ordinary', 'reference': 'authored-existing-' + identity},
             **({'suggestion': 'on_request'} if identity == 'look' else {})}
            for identity in ('attack', 'retreat', 'collect_bonus', 'look')]


def arguments(**changes):
    return {'source_sha256': adapter.SOURCE_SHA256, 'edition': 'authored-keen-adapter',
            'observation_id': OBSERVATION, 'state_context': context(),
            'evidence_ref': 'PRIVATE_CURRENT_EVIDENCE', 'choices': choices(),
            'choice_roles': {'attack': 'attack', 'collect_bonus': 'collect_bonus'},
            **changes}


def previous(value=None):
    return {'state': state(carrot_x=600, clock=98) if value is None else value,
            'observation_id': 'authored-update-6', 'state_context': context(6),
            'evidence_ref': 'PRIVATE_PREVIOUS_EVIDENCE'}


def facts(inputs):
    return {item['id']: item for item in inputs['scene']['facts']}


def assess(inputs):
    scene = inputs['scene']
    return evaluate_oracle(scene, inputs['rules'],
                           expected_scene_sha256=project_scene(scene)['scene_sha256'],
                           expected_observation_id=scene['observation_id'],
                           expected_state_context=scene['state_context'])


def test_default_projection_is_private_and_preserves_inputs_and_provider_choices():
    current, kwargs = state(), arguments(previous=previous())
    untouched = deepcopy((current, kwargs))
    inputs = adapter.build_keen_oracle_inputs(current, **kwargs)
    assert (current, kwargs) == untouched
    assert inputs == adapter.build_keen_oracle_inputs(current, **kwargs)
    assert inputs['scene']['choices'] == kwargs['choices']
    assert all(item['audience'] == 'internal' for item in facts(inputs).values())
    result = assess(inputs)
    assert result['hud']['facts'] == [] and result['hud']['situations'] == []
    assert [item['id'] for item in result['hud']['choices']] == ['retreat', 'look']
    assert result['execution'] == 'not_performed'


def test_adjacent_active_observations_describe_closing_motion_in_world_coordinates():
    inputs = adapter.build_keen_oracle_inputs(
        state(), **arguments(previous=previous(), permitted_actor_slots=(0, 40, 31)))
    observed = facts(inputs)
    assert observed['carrot_gap_world']['value'] == 250
    assert observed['carrot_approaching']['value'] is True
    assert observed['bonus_points']['value'] == 100
    assert observed['game_ticks']['audience'] == 'internal'
    result = assess(inputs)
    assert [item['id'] for item in result['hud']['situations']] == [
        'carrot_closing', 'carrot_encounter', 'optional_bonus']
    assert all('forecast' not in item for item in result['situations'])
    assert all(item['value'] is not None for item in result['scene']['facts'])


@pytest.mark.parametrize('change', ['activation', 'reused_slot'])
def test_activation_or_actor_replacement_does_not_establish_closing_motion(change):
    prior = state(carrot_x=600, clock=98)
    prior['objects'][0]['active' if change == 'activation' else 'pointer'] = (
        0 if change == 'activation' else 1999)
    inputs = adapter.build_keen_oracle_inputs(
        state(), **arguments(previous=previous(prior), permitted_actor_slots=(0, 40)))
    assert facts(inputs)['carrot_approaching']['value'] is None
    assert 'carrot_closing' not in [item['id'] for item in assess(inputs)['situations']]


def test_player_motion_alone_is_not_reported_as_an_approaching_enemy():
    prior = state(carrot_x=650, clock=98)
    prior['player'].update(body(1050))
    inputs = adapter.build_keen_oracle_inputs(
        state(), **arguments(previous=previous(prior), permitted_actor_slots=(0, 40)))
    assert facts(inputs)['carrot_gap_world']['value'] == 250
    assert facts(inputs)['carrot_approaching']['value'] is False


@pytest.mark.parametrize('mode, expected', [
    ('consumed_actor_still_present', False), ('absent_from_complete_list', False),
    ('absent_locally_but_still_live', None)])
def test_objective_ends_at_consumption_and_local_absence_remains_unknown(mode, expected):
    current = state()
    if mode == 'consumed_actor_still_present':
        current['objects'][1]['class_name'] = 'inert'
    else:
        current['objects'].pop()
        if mode == 'absent_from_complete_list':
            current['live_actor_slots'].remove(31)
    inputs = adapter.build_keen_oracle_inputs(
        current, **arguments(permitted_actor_slots=(0, 40, 31)))
    observed = facts(inputs)
    assert observed['bonus_collectible']['value'] is expected
    assert observed['bonus_x']['value'] is None and observed['bonus_points']['value'] is None
    result = assess(inputs)
    assert 'optional_bonus' not in [item['id'] for item in result['situations']]
    assert 'collect_bonus' not in [item['id'] for item in result['hud']['choices']]


@pytest.mark.parametrize('flowers, ready, offered', [
    (2, True, True), (0, True, False), (2, False, False), (2, None, False)])
def test_resource_rule_only_narrows_existing_provider_attack_readiness(flowers, ready, offered):
    kwargs = arguments(permitted_actor_slots=(0, 40))
    kwargs['choices'][0]['ready'] = ready
    inputs = adapter.build_keen_oracle_inputs(state(flowers=flowers), **kwargs)
    assert inputs['scene']['choices'] == kwargs['choices']
    result = assess(inputs)
    available = [item['id'] for item in result['hud']['choices']]
    assert ('attack' in available) is offered
    assert 'retreat' in available and 'look' in available
    assert facts(inputs)['flower_power']['value'] == flowers


@pytest.mark.parametrize('mismatch', ['source', 'clock', 'branch', 'map'])
def test_unqualified_source_or_nonadjacent_observations_are_refused(mismatch):
    current = state()
    kwargs = arguments(previous=previous(), permitted_actor_slots=(0, 40))
    if mismatch == 'source':
        kwargs['source_sha256'] = 'a' * 64
    elif mismatch == 'clock':
        current['clock']['time_count'] = 101
    elif mismatch == 'branch':
        kwargs['previous']['state_context']['branch_id'] = 'other-branch'
    else:
        kwargs['previous']['state']['map']['plane_segments'][0] = 201
    with pytest.raises(ValueError):
        adapter.build_keen_oracle_inputs(current, **kwargs)


def test_public_hud_omits_current_and_previous_evidence_and_internal_context():
    inputs = adapter.build_keen_oracle_inputs(
        state(), **arguments(previous=previous(), permitted_actor_slots=(0, 40, 31)))
    hud = assess(inputs)['hud']
    assert any(item['id'] == 'carrot_closing' for item in hud['situations'])
    encoded = json.dumps(hud)
    for forbidden in ('PRIVATE_', 'evidence_ref', 'state_context', 'qualification',
                      'source_sha256', 'rules_sha256', 'game_ticks'):
        assert forbidden not in encoded
