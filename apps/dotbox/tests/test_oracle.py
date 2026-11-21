"""Authored situation/choice contracts; no original-game physics claims."""
from copy import deepcopy
import hashlib
import json

import pytest

from dotbox.scenes import project_scene, select_choice, validate_scene
from dotbox.scene_state import SceneStore


SOURCE = 'a' * 64
OBSERVATION = 'observation-7'


def fact(identity, value, *, audience='player', observation=OBSERVATION):
    return {'id': identity, 'subject': identity, 'predicate': 'value', 'value': value,
            'text': f'Observed {identity}: {value}.', 'audience': audience,
            'observation_id': observation, 'evidence_ref': 'authored/current-observation'}


def scene(facts, choices):
    return {'format': 'dotbox-scene-1', 'source_sha256': SOURCE, 'edition': 'authored-oracle-1',
            'scene_id': 'courtyard', 'observation_id': OBSERVATION, 'title': 'Courtyard',
            'facts': facts, 'choices': [
                {'id': identity, 'label': identity.replace('_', ' ').capitalize(), 'requires': [],
                 'observation_id': OBSERVATION, 'available': True, 'enabled': True, 'ready': True,
                 'route': {'kind': 'ordinary', 'reference': 'authored-supported-' + identity}}
                for identity in choices],
            'guide_sources': [], 'guide_claims': [],
            'state_context': {'provider_id': 'authored-provider', 'session_id': 'session-one',
                              'branch_id': 'branch-one', 'revision': 7, 'context_token': 'token-7'}}


def condition(identity, op, value):
    return {'fact_id': identity, 'op': op, 'value': value}


def situation(identity, *, kind='context', priority=50, when=None, fact_ids=None, text=None):
    return {'id': identity, 'kind': kind, 'priority': priority,
            'text': text or identity.replace('_', ' ').capitalize() + '.',
            'when': [] if when is None else when, 'fact_ids': [] if fact_ids is None else fact_ids}


def action(identity, *, when=None, situation_ids=None, priority=50):
    return {'choice_id': identity, 'when': [] if when is None else when,
            'situation_ids': [] if situation_ids is None else situation_ids,
            'priority': priority, 'reason': 'The declared current requirements are satisfied.'}


def rules(situations=(), actions=()):
    return {'format': 'dotbox-oracle-rules-1', 'source_sha256': SOURCE,
            'edition': 'authored-oracle-1', 'qualification': 'Authored contract fixture only',
            'situations': list(situations), 'actions': list(actions)}


def assess(document, policy, **changes):
    from dotbox.oracle import evaluate_oracle
    arguments = {'expected_scene_sha256': project_scene(document)['scene_sha256'],
                 'expected_observation_id': document['observation_id'],
                 'expected_state_context': deepcopy(document.get('state_context')), 'choice_limit': 3}
    arguments.update(changes)
    return evaluate_oracle(document, policy, **arguments)


def offered(result):
    return [choice['id'] for choice in result['view']['choices']]


def enemy(ammo=2):
    document = scene([fact('enemy_closing', True), fact('ammo', ammo)], ['attack', 'retreat', 'look'])
    document['choices'][2]['suggestion'] = 'on_request'
    policy = rules([
        situation('enemy', kind='encounter', priority=80,
                  when=[condition('enemy_closing', 'eq', True)], fact_ids=['enemy_closing'])
    ], [action('attack', when=[condition('ammo', 'ge', 1)], situation_ids=['enemy'], priority=80),
        action('retreat', situation_ids=['enemy'], priority=70)])
    return document, policy


def test_enemy_choices_use_current_ammo_without_mutating_inventory():
    document, policy = enemy(2)
    before = deepcopy((document, policy))
    result = assess(document, policy)
    assert result['format'] == 'dotbox-oracle-assessment-1'
    assert result['execution'] == 'not_performed'
    assert result['view']['suggested_choice_ids'] == ['attack', 'retreat']
    assert offered(result) == ['attack', 'retreat', 'look']
    assert result['scene']['facts'] == document['facts']
    assert (document, policy) == before
    assert next(f for f in result['scene']['facts'] if f['id'] == 'ammo')['value'] == 2
    assert validate_scene(result['scene']) == result['scene']


@pytest.mark.parametrize('ammo, expected_status', [(0, 'blocked'), (None, 'unknown'),
                                                 (True, 'unknown'), ('2', 'unknown')])
def test_resource_absence_or_wrong_type_withholds_attack_without_hiding_retreat(ammo, expected_status):
    document, policy = enemy(ammo)
    result = assess(document, policy)
    assert result['view']['suggested_choice_ids'] == ['retreat']
    assert offered(result) == ['retreat', 'look']
    attack = next(a for a in result['action_assessments'] if a['choice_id'] == 'attack')
    assert attack['status'] == expected_status
    assert attack['audience'] == 'internal'
    assert [s['id'] for s in result['situations']] == ['enemy']


@pytest.mark.parametrize('mode', ['missing', 'stale', 'internal'])
def test_noncurrent_or_nonpublic_ammo_never_enables_attack(mode):
    document, policy = enemy()
    ammo = document['facts'][1]
    if mode == 'missing':
        document['facts'].remove(ammo)
    elif mode == 'stale':
        ammo['observation_id'] = 'observation-6'
    else:
        ammo['audience'] = 'internal'
    result = assess(document, policy)
    assert result['view']['suggested_choice_ids'] == ['retreat']
    assert 'attack' not in offered(result)


@pytest.mark.parametrize('gate, value', [('available', False), ('enabled', False), ('enabled', None),
                                       ('ready', False), ('ready', None)])
def test_oracle_priority_cannot_override_provider_refusal_or_unknown(gate, value):
    document, policy = enemy()
    document['choices'][0][gate] = value
    result = assess(document, policy)
    assert 'attack' not in offered(result)
    assert result['view']['suggested_choice_ids'] == ['retreat']
    assert next(a for a in result['action_assessments'] if a['choice_id'] == 'attack')['provider_eligible'] is False


def test_false_condition_dominates_unknown_without_treating_unknown_as_zero():
    document, policy = enemy(0)
    policy['actions'][0]['when'].append(condition('unobserved_cooldown', 'eq', 0))
    result = assess(document, policy)
    item = next(a for a in result['action_assessments'] if a['choice_id'] == 'attack')
    assert item['condition_status'] == 'false'
    assert item['status'] == 'blocked'
    document['facts'][1]['value'] = None
    item = next(a for a in assess(document, policy)['action_assessments'] if a['choice_id'] == 'attack')
    assert item['condition_status'] == 'unknown'
    assert item['status'] == 'unknown'


@pytest.mark.parametrize('op, threshold, expected', [('eq', 2, True), ('ne', 2, False),
                                                   ('lt', 2, False), ('le', 2, True),
                                                   ('gt', 1, True), ('ge', 3, False),
                                                   ('eq', True, False)])
def test_conditions_compare_typed_values_at_actual_boundaries(op, threshold, expected):
    document, policy = enemy(2)
    if type(threshold) is bool:
        document['facts'][1]['value'] = 1
    policy['actions'][0]['when'] = [condition('ammo', op, threshold)]
    assert ('attack' in offered(assess(document, policy))) is expected


def falling_fixture():
    # Bottom 76 + six steps * 4 = 100. At five steps it is still 96.
    # Horizontal position 10 + six steps * 3 = 28; origin frame 40 -> 46.
    document = scene([fact('falling', True), fact('frame', 40), fact('anvil_x', 10),
                      fact('anvil_bottom', 76), fact('anvil_vx', 3), fact('anvil_vy', 4),
                      fact('ground_y', 100)], ['move_left', 'move_right', 'wait'])
    falling = situation('falling_anvil', kind='hazard', priority=100,
                        when=[condition('falling', 'eq', True)], fact_ids=['falling'],
                        text='An anvil is falling.')
    falling['forecast'] = {'kind': 'linear_impact', 'model_id': 'linear-point-downward-v1',
        'qualification': 'Authored constant-velocity fixture; not recovered Keen physics',
        'clock_fact': 'frame', 'clock_unit': 'frames', 'x_fact': 'anvil_x',
        'y_fact': 'anvil_bottom', 'vx_fact': 'anvil_vx', 'vy_fact': 'anvil_vy',
        'surface_y_fact': 'ground_y', 'horizon': 120}
    policy = rules([falling], [action('move_left', situation_ids=['falling_anvil'], priority=100),
                              action('move_right', situation_ids=['falling_anvil'], priority=100)])
    return document, policy


def forecast(result):
    return next(s for s in result['situations'] if s['id'] == 'falling_anvil')['forecast']


def test_six_frame_anvil_forecast_has_explicit_clock_point_dependencies_and_assumptions():
    document, policy = falling_fixture()
    result = assess(document, policy)
    prediction = forecast(result)
    assert prediction['status'] == 'predicted'
    assert prediction['origin_clock'] == 40
    assert prediction['clock_unit'] == 'frames'
    assert prediction['eta'] == 6 and prediction['deadline'] == 46
    assert prediction['contact_point'] == [28, 100]
    assert prediction['horizon'] == 120
    assert prediction['model_id'] == 'linear-point-downward-v1'
    assert prediction['source_sha256'] == SOURCE
    assert prediction['observation_id'] == OBSERVATION
    assert prediction['scene_sha256'] == project_scene(document)['scene_sha256']
    assert prediction['rules_sha256'] == result['binding']['rules_sha256']
    assert set(prediction['dependency_fact_ids']) == {
        'frame', 'anvil_x', 'anvil_bottom', 'anvil_vx', 'anvil_vy', 'ground_y'}
    assert prediction['assumptions']
    assert result['scene']['facts'] == document['facts']
    assert 'deadline' not in json.dumps(result['scene'])


def test_first_crossing_uses_integer_ceiling_and_preserves_declared_clock_domain():
    document, policy = falling_fixture()
    document['facts'][3]['value'] = 77  # 77+5*4=97; first crossing is still update six.
    policy['situations'][0]['forecast']['clock_unit'] = 'game_ticks'
    prediction = forecast(assess(document, policy))
    assert (prediction['eta'], prediction['deadline'], prediction['contact_point']) == (6, 46, [28, 100])
    assert prediction['clock_unit'] == 'game_ticks'


@pytest.mark.parametrize('case', ['end_step_y', 'deadline', 'horizontal_product'])
def test_signed_64_forecast_overflow_is_unavailable_even_when_contact_would_be_near(case):
    document, policy = falling_fixture()
    by_id = {f['id']: f for f in document['facts']}
    maximum = (1 << 63) - 1
    if case == 'end_step_y':
        # The first step crosses a surface only one unit away, but its full
        # discrete y position would overflow before contact clipping.
        by_id['anvil_bottom']['value'] = maximum - 1
        by_id['ground_y']['value'] = maximum
        by_id['anvil_vy']['value'] = maximum
    elif case == 'deadline':
        # The ordinary six-step trajectory cannot fit its deadline in int64.
        by_id['frame']['value'] = maximum
    else:
        # All supplied operands are int64; the six-step horizontal product is not.
        by_id['anvil_vx']['value'] = maximum
    prediction = forecast(assess(document, policy))
    assert prediction['status'] == 'unavailable'
    assert prediction['reason'] == 'prediction_out_of_range'
    assert prediction['eta'] is None and prediction['deadline'] is None
    assert prediction['contact_point'] is None


def test_player_hud_expresses_the_six_frame_forecast_without_machine_provenance():
    document, policy = falling_fixture()
    document['facts'][0]['evidence_ref'] = 'PRIVATE_EVIDENCE_MARKER'
    policy['qualification'] = 'PRIVATE_RULE_QUALIFICATION'
    policy['situations'][0]['forecast']['qualification'] = 'PRIVATE_MODEL_QUALIFICATION'
    result = assess(document, policy)
    hud = result['hud']
    assert hud['format'] == 'dotbox-oracle-hud-1'
    prediction = next(s for s in hud['situations'] if s['id'] == 'falling_anvil')['forecast']
    assert prediction['eta'] == 6 and prediction['contact_point'] == [28, 100]
    assert '6 simulation frames' in prediction['text']
    assert '(28, 100)' in prediction['text']
    encoded = json.dumps(hud)
    for forbidden in ('PRIVATE_', 'source_sha256', 'rules_sha256', 'qualification',
                      'evidence_ref', 'state_context', 'action_assessments', 'dependency_fact_ids'):
        assert forbidden not in encoded
    assert hud['scene_sha256'] == result['view']['scene_sha256']
    assert hud['choices'] == result['view']['choices']


def test_unknown_hud_forecast_has_no_private_dependency_name_point_or_deadline():
    document, policy = falling_fixture()
    hidden = next(f for f in document['facts'] if f['id'] == 'anvil_x')
    hidden.update(id='PRIVATE_POSITION', subject='PRIVATE_POSITION', audience='internal',
                  value=123456789, text='PRIVATE_POSITION is 123456789.')
    policy['situations'][0]['forecast']['x_fact'] = 'PRIVATE_POSITION'
    hud = assess(document, policy)['hud']
    prediction = next(s for s in hud['situations'] if s['id'] == 'falling_anvil')['forecast']
    assert prediction['status'] == 'unknown'
    assert set(prediction) == {'status', 'text'}
    encoded = json.dumps(hud)
    assert 'PRIVATE_POSITION' not in encoded and '123456789' not in encoded


def test_unavailable_hud_forecast_does_not_narrate_a_safe_interval_or_collision_point():
    document, policy = falling_fixture()
    policy['situations'][0]['forecast']['horizon'] = 5
    hud = assess(document, policy)['hud']
    prediction = next(s for s in hud['situations'] if s['id'] == 'falling_anvil')['forecast']
    assert prediction['status'] == 'unavailable'
    assert set(prediction) == {'status', 'text'}
    assert 'safe' not in prediction['text'].casefold()


@pytest.mark.parametrize('case', ['horizon', 'stopped', 'rising', 'unknown_speed', 'stale_clock',
                                  'internal_x', 'bool_speed', 'already_at_surface'])
def test_unsupported_forecasts_remain_unknown_or_unavailable_without_a_position(case):
    document, policy = falling_fixture()
    by_id = {f['id']: f for f in document['facts']}
    if case == 'horizon':
        policy['situations'][0]['forecast']['horizon'] = 5
    elif case == 'stopped':
        by_id['anvil_vy']['value'] = 0
    elif case == 'rising':
        by_id['anvil_vy']['value'] = -4
    elif case == 'unknown_speed':
        by_id['anvil_vy']['value'] = None
    elif case == 'stale_clock':
        by_id['frame']['observation_id'] = 'older'
    elif case == 'internal_x':
        by_id['anvil_x']['audience'] = 'internal'
    elif case == 'bool_speed':
        by_id['anvil_vy']['value'] = True
    else:
        by_id['anvil_bottom']['value'] = 100
    prediction = forecast(assess(document, policy))
    assert prediction['status'] in ('unknown', 'unavailable')
    assert prediction['contact_point'] is None
    assert prediction['eta'] is None and prediction['deadline'] is None
    assert prediction['reason']


def test_urgent_choices_precede_optional_cherry_without_deleting_other_choices():
    document, policy = falling_fixture()
    document['facts'].append(fact('cherry_present', True))
    document['choices'].insert(0, scene([], ['collect_cherry'])['choices'][0])
    policy['situations'].append(situation('cherry', kind='objective', priority=20,
        when=[condition('cherry_present', 'eq', True)], fact_ids=['cherry_present'],
        text='A cherry is an optional star objective.'))
    policy['actions'].append(action('collect_cherry', situation_ids=['cherry'], priority=20))
    result = assess(document, policy, choice_limit=2)
    assert result['view']['suggested_choice_ids'] == ['move_left', 'move_right']
    assert set(offered(result)) == {'collect_cherry', 'move_left', 'move_right', 'wait'}
    assert result['view']['omitted_choices'] == 2
    assert [s['id'] for s in result['situations']] == ['falling_anvil', 'cherry']


def test_observed_mailbox_opening_removes_only_the_now_inapplicable_open_action():
    document = scene([fact('mailbox_open', False)], ['open_mailbox', 'move_north'])
    policy = rules([situation('closed_mailbox', when=[condition('mailbox_open', 'eq', False)],
                              fact_ids=['mailbox_open'])],
                   [action('open_mailbox', situation_ids=['closed_mailbox'])])
    assert 'open_mailbox' in offered(assess(document, policy))
    document['facts'][0]['value'] = True
    result = assess(document, policy)
    assert offered(result) == ['move_north']
    assert result['situations'] == []


def test_on_request_stays_off_shortlist_but_remains_explicitly_selectable():
    document, policy = enemy()
    document['choices'][0]['suggestion'] = 'on_request'
    result = assess(document, policy)
    assert 'attack' in offered(result)
    assert 'attack' not in result['view']['suggested_choice_ids']
    intent = select_choice(result['scene'], 'attack', result['view']['scene_sha256'], OBSERVATION)
    assert intent['route'] == document['choices'][0]['route']
    assert intent['execution'] == 'not_performed' and intent['live_applicability'] == 'unverified'


def test_public_situations_and_ranking_do_not_reveal_internal_values_or_guide_claims():
    document, policy = enemy()
    document['facts'].append(fact('secret', True, audience='internal'))
    policy['situations'].append(situation('secret_situation', priority=100,
        when=[condition('secret', 'eq', True)], text='SECRET object is revealed.', fact_ids=['secret']))
    policy['actions'][0]['situation_ids'] = ['secret_situation']
    document['guide_sources'] = [{'id': 'manual', 'reference': 'authored-guide',
                                  'edition': document['edition'], 'origin_group': 'authored'}]
    document['guide_claims'] = [{'id': 'secret_claim', 'source_id': 'manual', 'subject': 'secret',
        'predicate': 'value', 'value': True, 'text': 'SECRET guide claim.', 'condition': ''}]
    first = assess(document, policy)
    document['facts'][-1]['value'] = False
    second = assess(document, policy)
    for result in (first, second):
        assert 'SECRET' not in json.dumps(result['view'])
        assert 'SECRET' not in json.dumps(result['situations'])
        assert 'secret_situation' not in [s['id'] for s in result['situations']]
        assert result['view']['suggested_choice_ids'] == ['retreat']
    assert first['view']['choices'] == second['view']['choices']


def test_declared_extra_dependency_must_be_current_public_known_before_text_is_disclosed():
    document, policy = enemy()
    policy['situations'][0]['fact_ids'].append('unknown_location')
    result = assess(document, policy)
    assert result['situations'] == []
    assert result['view']['suggested_choice_ids'] == []
    assert offered(result) == ['look']


def test_guide_ammunition_cannot_substitute_for_missing_observed_inventory():
    document, policy = enemy()
    document['facts'].pop()
    document['guide_sources'] = [{'id': 'manual', 'reference': 'authored-guide',
                                  'edition': document['edition'], 'origin_group': 'authored'}]
    document['guide_claims'] = [{'id': 'guide_ammo', 'source_id': 'manual', 'subject': 'ammo',
        'predicate': 'value', 'value': 2, 'text': 'The guide expects two rounds.', 'condition': ''}]
    assert offered(assess(document, policy)) == ['retreat', 'look']


@pytest.mark.parametrize('change', ['scene_sha', 'observation', 'branch', 'revision', 'token',
                                   'rule_source', 'rule_edition', 'missing_context'])
def test_stale_or_mismatched_binding_is_refused(change):
    document, policy = enemy()
    kwargs = {}
    if change == 'scene_sha':
        kwargs['expected_scene_sha256'] = 'b' * 64
    elif change == 'observation':
        kwargs['expected_observation_id'] = 'observation-6'
    elif change in ('branch', 'revision', 'token'):
        expected = deepcopy(document['state_context'])
        field = {'branch': 'branch_id', 'revision': 'revision', 'token': 'context_token'}[change]
        expected[field] = 6 if field == 'revision' else 'different'
        kwargs['expected_state_context'] = expected
    elif change == 'rule_source':
        policy['source_sha256'] = 'b' * 64
    elif change == 'rule_edition':
        policy['edition'] = 'another-edition'
    else:
        document.pop('state_context')
    with pytest.raises(ValueError):
        assess(document, policy, **kwargs)


def test_output_binds_every_rule_and_cannot_reuse_a_selection_after_route_change():
    document, policy = enemy()
    result = assess(document, policy)
    expected = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':'),
                                         allow_nan=False).encode()).hexdigest()
    assert result['binding']['rules_sha256'] == expected
    assert result['binding']['scene_sha256'] == project_scene(document)['scene_sha256']
    assert result['binding']['state_context'] == document['state_context']
    changed = deepcopy(result['scene'])
    changed['choices'][0]['route']['reference'] = 'changed-route'
    with pytest.raises(ValueError, match='Stale'):
        select_choice(changed, 'attack', result['view']['scene_sha256'], OBSERVATION)
    with pytest.raises(ValueError):
        select_choice(result['scene'], 'invented_choice', result['view']['scene_sha256'], OBSERVATION)


def test_deterministic_result_and_independent_copies_preserve_routes_and_current_facts():
    document, policy = enemy()
    original = deepcopy((document, policy))
    first = assess(document, policy)
    second = assess(document, policy)
    assert first == second
    assert (document, policy) == original
    routes = {c['id']: c['route'] for c in first['scene']['choices']}
    assert routes == {c['id']: c['route'] for c in document['choices']}
    first['scene']['facts'][0]['text'] = 'changed copy'
    first['binding']['state_context']['revision'] = 100
    assert (document, policy) == original
    assert second['scene']['facts'][0]['text'] == document['facts'][0]['text']


def test_scene_store_receives_only_observed_facts_and_existing_selection_intents(tmp_path):
    document, policy = falling_fixture()
    result = assess(document, policy)
    with SceneStore(tmp_path / 'scene.sqlite', create=True) as store:
        store.record(result['scene'])
        assert store.current() == result['scene']
        remembered = store.memory()['facts']
        assert len(remembered) == len(document['facts'])
        assert {item['subject'] for item in remembered} == {item['subject'] for item in document['facts']}
        assert all('forecast' not in item and 'deadline' not in item for item in remembered)
        intent = store.choose('move_left', result['view']['scene_sha256'], OBSERVATION)
        assert intent['route'] == document['choices'][0]['route']
        assert intent['execution'] == 'not_performed'


@pytest.mark.parametrize('case', ['unknown_rule_field', 'unknown_choice', 'unknown_situation',
                                  'duplicate_action', 'duplicate_situation', 'too_many_conditions',
                                  'too_many_situations', 'bad_operator', 'bad_priority',
                                  'bad_forecast_horizon', 'bad_clock_unit'])
def test_closed_rule_schema_and_finite_bounds(case):
    document, policy = falling_fixture()
    if case == 'unknown_rule_field':
        policy['python'] = 'do_not_evaluate()'
    elif case == 'unknown_choice':
        policy['actions'][0]['choice_id'] = 'invented'
    elif case == 'unknown_situation':
        policy['actions'][0]['situation_ids'] = ['invented']
    elif case == 'duplicate_action':
        policy['actions'].append(deepcopy(policy['actions'][0]))
    elif case == 'duplicate_situation':
        policy['situations'].append(deepcopy(policy['situations'][0]))
    elif case == 'too_many_conditions':
        policy['actions'][0]['when'] = [condition('falling', 'eq', True)] * 9
    elif case == 'too_many_situations':
        policy['situations'] = [situation('s' + str(i)) for i in range(17)]
        policy['actions'] = []
    elif case == 'bad_operator':
        policy['situations'][0]['when'][0]['op'] = 'eval'
    elif case == 'bad_priority':
        policy['situations'][0]['priority'] = True
    elif case == 'bad_forecast_horizon':
        policy['situations'][0]['forecast']['horizon'] = 121
    else:
        policy['situations'][0]['forecast']['clock_unit'] = 'whatever'
    with pytest.raises(ValueError):
        assess(document, policy)
