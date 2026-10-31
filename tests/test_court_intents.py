"""Independent acceptance cases with authored text, never original game data.

These tests exercise the declared dispatch boundary, including branch-local
states that the stricter native-context adapter may decline to admit.
"""
from copy import deepcopy

import pytest

from fdisbull.court_intents import (
    CourtIntentError, build_definition, evaluate_event, validate_intent,
)


def definition():
    return build_definition({
        'response': 'The fictional host acknowledges the gesture.',
        'invisible': 'The fictional host cannot see the visitor.',
        'improper_position': 'The visitor stands in the wrong place.',
        'repeat': 'The visitor has already offered this greeting.',
        'distant': 'The visitor must move nearer.',
    })


def state(**changes):
    return {
        'actor_x': 70, 'actor_y': 110, 'score': 1, 'direction': 7,
        'sequence_countdown': 0, 'treasure_count': 0,
        'player_control': True, 'bowed_this_visit': False,
        'respect_awarded': False, 'invisible': False,
        'standing_animation': False, 'bow_complete': False,
        'input_ready': True, 'input_consumed': False, 'command': 'bow',
        **changes,
    }


def cycle(before=None, document=None):
    return evaluate_event(definition() if document is None else document,
                          state() if before is None else before, {'kind': 'cycle'})


def acknowledge(result, document=None):
    return evaluate_event(definition() if document is None else document,
                          result['state'],
                          {'kind': 'ack', 'continuation': result['continuation']})


def resources(result):
    return [effect['resource'] for effect in result['effects'] if 'resource' in effect]


def test_initial_bow_changes_score_at_start_without_printing_or_completing():
    before = state(score=250)
    original = deepcopy(before)
    result = cycle(before)
    assert result['status'] == 'slice_complete'
    assert result['outcome'] == 'bow_started'
    assert result['state'] == state(
        actor_x=63, score=253, direction=0, player_control=False,
        bowed_this_visit=True, respect_awarded=True, standing_animation=True,
        input_consumed=True,
    )
    assert resources(result) == []
    assert result['continuation'] is None
    assert result['effects'] == [
        {'residual_ir': 'refresh_position_flag'},
        {'intent': 'input.claim'},
        {'intent': 'court.begin_bow'},
        {'intent': 'court.award_first_respect'},
    ]
    assert result['executed_intents'] == [
        'input.claim', 'court.begin_bow', 'court.award_first_respect']
    assert before == original


@pytest.mark.parametrize('command', ['bow', 'bow_to_king'])
def test_both_admitted_command_identities_execute_the_same_bow(command):
    result = cycle(state(command=command))
    assert result['outcome'] == 'bow_started'
    assert result['state']['score'] == 4
    assert result['state']['input_consumed'] is True


def test_score_wraps_as_a_byte_and_visit_latch_is_distinct_from_score_latch():
    assert cycle(state(score=255))['state']['score'] == 2
    already_rewarded = cycle(state(respect_awarded=True, score=12))
    assert already_rewarded['outcome'] == 'bow_started'
    assert already_rewarded['state']['score'] == 12
    assert already_rewarded['state']['bowed_this_visit'] is True
    assert already_rewarded['state']['standing_animation'] is True
    assert already_rewarded['executed_intents'] == ['input.claim', 'court.begin_bow']


def test_no_animation_completion_or_modal_is_invented_by_repeated_dispatches():
    started = cycle()
    current = started['state']
    for _ in range(3):
        waiting = cycle(current)
        assert waiting['status'] == 'slice_complete'
        assert waiting['outcome'] == 'no_bow_action'
        assert waiting['state'] == current
        assert waiting['executed_intents'] == []
        assert waiting['effects'] == [{'residual_ir': 'refresh_position_flag'}]
        current = waiting['state']


def test_completion_uses_current_position_and_waits_for_separate_acknowledgement():
    started = cycle()
    signalled = {**started['state'], 'actor_x': 66, 'actor_y': 109,
                 'input_ready': False, 'bow_complete': True}
    completed = cycle(signalled)
    assert completed['status'] == 'awaiting_ack'
    assert completed['outcome'] == 'bow_completed'
    assert completed['state']['actor_x'] == 73
    assert completed['state']['actor_y'] == 109
    assert completed['state']['score'] == 4
    assert completed['state']['bowed_this_visit'] is True
    assert completed['state']['respect_awarded'] is True
    assert completed['state']['standing_animation'] is False
    assert completed['state']['bow_complete'] is False
    assert completed['state']['direction'] == 0
    assert completed['state']['player_control'] is True
    assert completed['executed_intents'] == ['court.finish_bow', 'narration.modal']
    assert resources(completed) == ['response']
    finished = acknowledge(completed)
    assert finished['status'] == 'slice_complete'
    assert finished['state'] == completed['state']
    assert finished['effects'] == [] and finished['continuation'] is None


def test_completed_repeat_has_no_new_reward_or_animation():
    before = state(bowed_this_visit=True, respect_awarded=True, score=4)
    result = cycle(before)
    assert result['status'] == 'awaiting_ack'
    assert resources(result) == ['repeat']
    assert result['state'] == {**before, 'input_consumed': True}
    assert result['executed_intents'] == ['input.claim', 'narration.modal']


@pytest.mark.parametrize('changes,resource', [
    ({'invisible': True}, 'invisible'),
    ({'invisible': True, 'actor_x': 60, 'actor_y': 90,
      'sequence_countdown': 5, 'bowed_this_visit': True}, 'invisible'),
    ({'actor_x': 60, 'actor_y': 90}, 'improper_position'),
    ({'actor_x': 60, 'actor_y': 90, 'sequence_countdown': 5,
      'bowed_this_visit': True}, 'improper_position'),
    ({'sequence_countdown': 1}, 'repeat'),
    ({'bowed_this_visit': True}, 'repeat'),
    ({'actor_x': 90, 'invisible': True}, 'distant'),
])
def test_refusals_follow_source_precedence_and_claim_input(changes, resource):
    before = state(**changes)
    result = cycle(before)
    assert result['status'] == 'awaiting_ack'
    assert resources(result) == [resource]
    assert result['state'] == {**before, 'input_consumed': True}
    assert result['executed_intents'] == ['input.claim', 'narration.modal']


@pytest.mark.parametrize('x,y,outcome', [
    (18, 80, 'improper_position'), (67, 107, 'improper_position'),
    (68, 80, 'bow_started'), (86, 80, 'bow_started'),
    (18, 108, 'bow_started'), (18, 113, 'bow_started'),
    (86, 113, 'bow_started'), (17, 80, 'too_far'),
    (87, 113, 'too_far'), (70, 79, 'too_far'), (70, 114, 'too_far'),
])
def test_inclusive_geometry_uses_actor_baseline_coordinates(x, y, outcome):
    assert cycle(state(actor_x=x, actor_y=y))['outcome'] == outcome


@pytest.mark.parametrize('x,y,shifted,resource', [
    (68, 90, 61, 'improper_position'),
    (18, 108, 11, 'distant'),
    (70, 110, 63, 'repeat'),
])
def test_new_input_during_animation_reclassifies_shifted_pose(x, y, shifted, resource):
    started = cycle(state(actor_x=x, actor_y=y))
    assert started['state']['actor_x'] == shifted
    repeated = cycle({**started['state'], 'input_consumed': False})
    assert resources(repeated) == [resource]
    assert repeated['state']['standing_animation'] is True
    assert repeated['state']['bow_complete'] is False
    assert repeated['state']['player_control'] is False
    assert repeated['state']['score'] == 4
    resumed = acknowledge(repeated)
    assert resumed['status'] == 'slice_complete'
    assert resumed['state'] == repeated['state']
    assert resumed['effects'] == []


@pytest.mark.parametrize('x,y,invisible,first_resource', [
    (63, 110, False, 'repeat'),
    (61, 90, False, 'improper_position'),
    (11, 108, False, 'distant'),
    (63, 110, True, 'invisible'),
])
def test_refusal_and_signalled_completion_are_two_ordered_modals(
        x, y, invisible, first_resource):
    before = state(actor_x=x, actor_y=y, invisible=invisible, score=4,
                   bowed_this_visit=True, respect_awarded=True,
                   standing_animation=True, bow_complete=True,
                   player_control=False, direction=0)
    refused = cycle(before)
    assert refused['status'] == 'awaiting_ack'
    assert resources(refused) == [first_resource]
    assert refused['state']['bow_complete'] is True
    assert refused['state']['standing_animation'] is True
    assert refused['state']['actor_x'] == x
    completed = acknowledge(refused)
    assert completed['status'] == 'awaiting_ack'
    assert completed['outcome'] == 'bow_completed'
    assert resources(completed) == ['response']
    assert completed['state']['actor_x'] == x + 7
    assert completed['state']['score'] == 4
    assert completed['state']['standing_animation'] is False
    assert completed['state']['bow_complete'] is False
    assert completed['state']['player_control'] is True
    assert completed['effects'][0] == {'intent': 'court.finish_bow'}
    end = acknowledge(completed)
    assert end['status'] == 'slice_complete' and end['effects'] == []


def test_new_bow_resets_a_stale_completion_before_completion_phase():
    # This is branch-local source behavior; it is not a native-context admission.
    result = cycle(state(bow_complete=True))
    assert result['outcome'] == 'bow_started'
    assert result['state']['bow_complete'] is False
    assert resources(result) == []
    assert 'court.finish_bow' not in result['executed_intents']


def test_completion_uses_byte_arithmetic_at_the_declared_script_boundary():
    result = cycle(state(actor_x=254, input_ready=False, bow_complete=True))
    assert result['state']['actor_x'] == 5
    assert resources(result) == ['response']


@pytest.mark.parametrize('ready,consumed', [(False, False), (False, True), (True, True)])
def test_unavailable_input_does_not_claim_or_dispatch_a_command(ready, consumed):
    before = state(input_ready=ready, input_consumed=consumed, command=None)
    result = cycle(before)
    assert result['status'] == 'slice_complete'
    assert result['state'] == before
    assert result['executed_intents'] == []


def test_unconsumed_unknown_command_remains_unrecovered():
    before = state(command=None)
    result = cycle(before)
    assert result['status'] == 'unrecovered'
    assert result['state'] == before
    assert result['effects'] == [] and result['executed_intents'] == []


def test_far_countdown_does_not_consume_input_and_leaves_fallback_available():
    before = state(actor_x=90, sequence_countdown=1)
    result = cycle(before)
    assert result['outcome'] == 'no_bow_action'
    assert result['state'] == before
    assert result['executed_intents'] == []


def test_treasure_return_audience_is_explicitly_outside_this_definition():
    before = state(treasure_count=3, bow_complete=True)
    result = cycle(before)
    assert result['status'] == 'unrecovered'
    assert result['state'] == before
    assert result['effects'] == []


@pytest.mark.parametrize('field', [
    'actor_x', 'actor_y', 'treasure_count', 'input_ready', 'input_consumed',
    'invisible', 'sequence_countdown', 'bowed_this_visit', 'respect_awarded', 'score',
])
def test_required_unknown_state_refuses_without_partially_applying_intents(field):
    before = state(**{field: None})
    result = cycle(before)
    assert result['status'] == 'unrecovered'
    assert result['state'] == before
    assert result['effects'] == [] and result['continuation'] is None


def test_unknown_score_is_not_fabricated_when_the_reward_was_already_awarded():
    result = cycle(state(score=None, respect_awarded=True))
    assert result['status'] == 'slice_complete'
    assert result['state']['score'] is None
    assert result['outcome'] == 'bow_started'
    assert 'court.award_first_respect' not in result['executed_intents']


@pytest.mark.parametrize('change,expected', [
    (lambda d: d['reward'].__setitem__('points', 9), {'score': 10, 'actor_x': 63}),
    (lambda d: d['gesture'].__setitem__('start_dx', -3), {'score': 4, 'actor_x': 67}),
])
def test_executable_definition_parameters_determine_effects(change, expected):
    document = definition()
    change(document)
    validate_intent(document)
    result = cycle(document=document)
    for key, value in expected.items():
        assert result['state'][key] == value


def test_executable_definition_geometry_and_rule_order_determine_outcome():
    document = definition()
    document['geometry']['improper_position'][2] = 70
    assert cycle(state(actor_y=90), document)['outcome'] == 'improper_position'
    document = definition()
    rules = document['command_outcomes']
    rules[0], rules[1] = rules[1], rules[0]
    result = cycle(state(actor_x=60, actor_y=90, invisible=True), document)
    assert resources(result) == ['improper_position']


def test_modal_continuation_binds_both_definition_and_exact_semantic_state():
    document = definition()
    pending = cycle(state(bowed_this_visit=True), document)
    changed_state = {**pending['state'], 'score': 99}
    with pytest.raises(CourtIntentError, match='continuation'):
        evaluate_event(document, changed_state,
                       {'kind': 'ack', 'continuation': pending['continuation']})
    changed_definition = deepcopy(document)
    changed_definition['resources']['repeat'] += ' Altered authored response.'
    with pytest.raises(CourtIntentError, match='continuation'):
        acknowledge(pending, changed_definition)
    assert acknowledge(pending, document)['status'] == 'slice_complete'


@pytest.mark.parametrize('change', [
    lambda token: token.__setitem__('next_phase', 'command'),
    lambda token: token.__setitem__('resource', 'not_a_resource'),
    lambda token: token.__setitem__('resource', []),
    lambda token: token.__setitem__('model_sha256', 'wrong'),
    lambda token: token.__setitem__('state_sha256', 'wrong'),
    lambda token: token.__setitem__('extra', True),
])
def test_invalid_acknowledgement_tokens_are_rejected(change):
    pending = cycle(state(bowed_this_visit=True))
    change(pending['continuation'])
    with pytest.raises(CourtIntentError):
        acknowledge(pending)


@pytest.mark.parametrize('changes', [
    {'score': True}, {'score': -1}, {'score': 256}, {'score': 1.0},
    {'player_control': 1}, {'input_consumed': 0}, {'bow_complete': []},
    {'command': 'talk'}, {'extra': 1},
])
def test_invalid_semantic_types_do_not_expand_the_qualified_domain(changes):
    with pytest.raises(CourtIntentError):
        cycle(state(**changes))


@pytest.mark.parametrize('change', [
    lambda d: d['reward'].__setitem__('points', True),
    lambda d: d['reward'].__setitem__('points', 256),
    lambda d: d['reward'].__setitem__('modulus', 256.0),
    lambda d: d['gesture'].__setitem__('finish_dx', False),
    lambda d: d['geometry'].__setitem__('addressing', [90, 80, 18, 113]),
    lambda d: d['geometry'].__setitem__('addressing', [18, 80, True, 113]),
    lambda d: d['resources'].__setitem__('response', []),
    lambda d: d['requires'].__setitem__(0, {'field': 'treasure_count', 'ne': True}),
    lambda d: d['requires'].__setitem__(0, {'field': 'input_ready', 'eq': 1}),
    lambda d: d['requires'][0].__setitem__('field', []),
    lambda d: d['command_outcomes'][0]['when'][0].__setitem__('zone', []),
    lambda d: d['command_outcomes'][0].__setitem__('steps', []),
    lambda d: d['command_outcomes'][0]['steps'].append({'intent': 'input.claim'}),
    lambda d: d['command_outcomes'][0]['steps'].__setitem__(0, {'intent': 'invented'}),
    lambda d: d['command_outcomes'][0]['steps'][0].__setitem__('intent', []),
    lambda d: d['command_outcomes'][0]['steps'][-1].__setitem__('resource', []),
    lambda d: d['command_outcomes'][1].__setitem__('id', 'unseen'),
    lambda d: d.__setitem__('extra', True),
])
def test_invalid_definitions_fail_before_execution(change):
    document = definition()
    change(document)
    before = state()
    original = deepcopy(before)
    with pytest.raises(CourtIntentError):
        cycle(before, document)
    assert before == original


def test_definition_and_input_state_are_not_changed_by_execution():
    document, before = definition(), state()
    saved_document, saved_before = deepcopy(document), deepcopy(before)
    first, second = cycle(before, document), cycle(before, document)
    assert first == second
    assert document == saved_document and before == saved_before
    first['state']['score'] = 88
    first['effects'].append({'authored_external_mutation': True})
    assert second['state']['score'] == 4
    assert document == saved_document and before == saved_before
