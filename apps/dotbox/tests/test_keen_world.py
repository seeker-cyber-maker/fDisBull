"""Authored state-stream cases; no native runtime or original game data."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'keen_world', Path(__file__).resolve().parents[1] / 'scripts/experiments/keen_world.py')
world = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(world)


def state(x=10):
    return {'phase': 'authored_boundary', 'coherent_game_update': True,
            'phase_meaning': 'An authored fixture', 'input_semantics': 'sampled',
            'map': {'width': 8, 'height': 6, 'plane_segments': [10, 20, 30]},
            'corridor_verified': True, 'level': 1, 'playstate': 0, 'lives': 3,
            'player': {'x': x, 'y': 20, 'state': 1234, 'state_name': None,
                       'state_record': {'next_state': 1234, 'x_move': 2},
                       'left': x, 'right': x + 4},
            'input': {'xaxis': 0}, 'clock': {'tics': 2},
            'physics': {'jump_time': 0}, 'camera': {'x': 0, 'y': 0},
            'nearby': [{'slot': 5, 'x': 99}], 'live_objects': 2,
            'extra': {'unknown': None, 'flag': False, 'ratio': 1.25, 'labels': ['a', 'b']}}


def test_complete_stream_round_trip_keeps_all_dynamic_and_unknown_fields():
    first, second = state(), state(12)
    second.update(level=2, playstate=3, lives=2)
    second['input']['xaxis'] = -1
    second['clock']['tics'] = 4
    second['physics']['jump_time'] = 9
    second['camera']['x'] = 2
    second['nearby'][0]['x'] = 98
    second['extra']['labels'].append('new')
    states = [first, second, first]
    records = world.encode_states(states)
    assert [r['type'] for r in records] == ['start', 'context', 'definition', 'state', 'state', 'state']
    assert world.decode_records(json.loads(json.dumps(records))) == states
    for record in records:
        if record['type'] == 'state':
            assert set(('level', 'playstate', 'lives', 'player', 'input', 'clock', 'physics',
                        'camera', 'nearby', 'live_objects', 'extra')) <= set(record['value'])


@pytest.mark.parametrize('field,value', [('map', {'width': 9}), ('corridor_verified', False),
                                        ('phase', 'another_boundary')])
def test_changed_context_gets_new_reference_and_old_content_can_be_reused(field, value):
    initial = state()
    changed = deepcopy(initial)
    changed[field] = value
    records = world.encode_states([initial, changed, initial])
    contexts = [r for r in records if r['type'] == 'context']
    frames = [r for r in records if r['type'] == 'state']
    assert len(contexts) == 2 and contexts[0]['sha256'] != contexts[1]['sha256']
    assert [r['context'] for r in frames] == [0, 1, 0]
    assert world.decode_records(records) == [initial, changed, initial]


def test_same_pointer_with_changed_definition_uses_content_identity():
    first, second = state(), state()
    second['player']['state_record']['x_move'] = 7
    records = world.encode_states([first, second])
    definitions = [r for r in records if r['type'] == 'definition']
    assert len(definitions) == 2 and definitions[0]['sha256'] != definitions[1]['sha256']
    assert first['player']['state'] == second['player']['state']
    assert world.decode_records(records) == [first, second]


def test_missing_optional_factored_fields_remain_missing():
    original = {'player': {'x': 5}, 'level': 1}
    assert world.decode_records(world.encode_states([original])) == [original]


@pytest.mark.parametrize('missing', ['context', 'definition'])
def test_unknown_references_are_refused(missing):
    records = world.encode_states([state()])
    records = [r for r in records if r['type'] != missing]
    with pytest.raises(ValueError, match='unknown'):
        world.decode_records(records)


@pytest.mark.parametrize('alteration', ['bad_hash', 'bad_reference', 'extra_field',
                                       'duplicate_context_field', 'duplicate_definition_field'])
def test_malformed_records_are_refused(alteration):
    records = world.encode_states([state()])
    if alteration == 'bad_hash':
        records[1]['value']['map']['width'] += 1
    elif alteration == 'bad_reference':
        records[-1]['context'] = True
    elif alteration == 'extra_field':
        records[-1]['other'] = 1
    elif alteration == 'duplicate_context_field':
        records[-1]['value']['map'] = {}
    else:
        records[-1]['value']['player']['state_record'] = {}
    with pytest.raises(ValueError):
        world.decode_records(records)


def test_header_and_reference_redefinition_are_refused():
    records = world.encode_states([state()])
    for bad in (records[1:], records[:2] + [records[0]], records[:2] + [records[1]]):
        with pytest.raises(ValueError):
            world.decode_records(bad)


def test_input_and_decoded_states_do_not_alias_encoder_or_decoder_memory():
    original = state()
    expected = deepcopy(original)
    encoder, decoder = world.StateEncoder(), world.StateDecoder()
    records = encoder.encode(original)
    original['map']['width'] = 99
    original['player']['state_record']['x_move'] = 99
    original['nearby'][0]['x'] = 99_999
    for record in records:
        result = decoder.accept(record)
    assert result == expected
    result['map']['width'] = 77
    result['player']['state_record']['x_move'] = 77
    result['nearby'][0]['x'] = 77_777
    records[1]['value']['map']['width'] = 55
    assert decoder.accept(encoder.encode(expected)[0]) == expected


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), (1, 2), {1: 'key'}])
def test_nonfinite_or_coerced_json_is_refused(invalid):
    original = state()
    original['extra'] = invalid
    with pytest.raises(ValueError):
        world.StateEncoder().encode(original)


def test_state_and_reference_budgets_are_enforced(monkeypatch):
    huge = state()
    huge['extra'] = 'x' * world.MAX_STATE_BYTES
    with pytest.raises(ValueError, match='bytes'):
        world.encode_states([huge])
    monkeypatch.setattr(world, 'MAX_REFERENCES', 1)
    encoder = world.StateEncoder()
    encoder.encode(state())
    different = state()
    different['phase'] = 'different'
    with pytest.raises(ValueError, match='count'):
        encoder.encode(different)
    # Refusal leaves the original content usable.
    assert len(encoder.encode(state())) == 1
    monkeypatch.setattr(world, 'MAX_STATES', 2)
    with pytest.raises(ValueError, match='count'):
        encoder.encode(state())


def actor(slot, pointer, **changes):
    return {'slot': slot, 'pointer': pointer, 'state': 4321, 'state_name': None,
            'state_record': {'next_state': 4321, 'x_move': 3},
            'class_name': 'authored_actor', 'active': 1, 'x': slot * 10,
            'temp1': 5, 'unknown': {'definition': 'ordinary user data'}, **changes}


def test_nearby_definitions_are_shared_by_content_with_actor_order_and_fields_preserved():
    first = state()
    first['nearby'] = [actor(3, 30), {'slot': 1, 'unknown': None}, actor(2, 20)]
    second = deepcopy(first)
    second['nearby'].reverse()
    second['nearby'][0].update(x=100, active=0, temp1=6, pointer=77)
    second['nearby'][2]['unknown']['definition'] = 'still ordinary data'
    records = world.encode_states([first, second])
    frames = [record for record in records if record['type'] == 'state']
    assert len([record for record in records if record['type'] == 'definition']) == 2
    assert frames[0]['nearby_definitions'] == [1, None, 1]
    assert frames[1]['nearby_definitions'] == [1, None, 1]
    assert [row['slot'] for row in frames[1]['value']['nearby']] == [2, 1, 3]
    for source, frame in zip((first, second), frames):
        for original, retained in zip(source['nearby'], frame['value']['nearby']):
            assert retained == {key: value for key, value in original.items()
                                if key not in world.DEFINITION_FIELDS}
    assert world.decode_records(records) == [first, second]


def test_nearby_same_pointer_changed_definition_gets_new_content_reference():
    first = state()
    first['nearby'] = [actor(3, 30)]
    second = deepcopy(first)
    second['nearby'][0]['state_record']['x_move'] = 99
    third = deepcopy(second)
    third['nearby'][0].pop('state_name')
    records = world.encode_states([first, second, third, first])
    frames = [record for record in records if record['type'] == 'state']
    assert [record['nearby_definitions'] for record in frames] == [[1], [2], [3], [1]]
    assert world.decode_records(records) == [first, second, third, first]


@pytest.mark.parametrize('nearby', [None, 7, 'opaque', {'actors': []}, [],
                                   [None, actor(1, 10)], [actor(2, 20), ['nested']],
                                   [{'state_record': {}}] * 101])
def test_noncanonical_nearby_values_and_long_lists_pass_through_unchanged(nearby):
    original = state()
    original['nearby'] = nearby
    records = world.encode_states([original])
    assert 'nearby_definitions' not in records[-1]
    assert records[-1]['value']['nearby'] == nearby
    assert world.decode_records(records) == [original]


def test_nearby_definition_values_are_not_normalized_or_semantically_interpreted():
    original = state()
    original['nearby'] = [{'state_name': ['opaque'], 'state_record': None},
                          {'state_record': 'unknown shape'}, {'state_name': False}, {}]
    records = world.encode_states([original])
    assert world.decode_records(records) == [original]


@pytest.mark.parametrize('alteration', ['unknown', 'boolean', 'length', 'non_list',
                                       'mixed_actors', 'duplicate', 'all_null'])
def test_invalid_nearby_reference_records_are_refused(alteration):
    original = state()
    original['nearby'] = [actor(1, 10)]
    records = world.encode_states([original])
    frame = records[-1]
    if alteration == 'unknown':
        frame['nearby_definitions'] = [20]
    elif alteration == 'boolean':
        frame['nearby_definitions'] = [True]
    elif alteration == 'length':
        frame['nearby_definitions'].append(1)
    elif alteration == 'non_list':
        frame['nearby_definitions'] = 1
    elif alteration == 'mixed_actors':
        frame['value']['nearby'] = [None]
    elif alteration == 'duplicate':
        frame['value']['nearby'][0]['state_record'] = {}
    else:
        frame['nearby_definitions'] = [None]
    with pytest.raises(ValueError):
        world.decode_records(records)


def test_nearby_output_and_input_cannot_mutate_shared_definitions():
    original = state()
    original['nearby'] = [actor(1, 10), actor(2, 20)]
    expected = deepcopy(original)
    encoder, decoder = world.StateEncoder(), world.StateDecoder()
    records = encoder.encode(original)
    original['nearby'][0]['state_record']['x_move'] = 50
    for record in records:
        restored = decoder.accept(record)
    assert restored == expected
    restored['nearby'][0]['state_record']['x_move'] = 75
    assert restored['nearby'][1]['state_record']['x_move'] == 3
    assert decoder.accept(encoder.encode(expected)[0]) == expected


def test_nearby_definition_budget_refusal_is_atomic(monkeypatch):
    monkeypatch.setattr(world, 'MAX_REFERENCES', 2)
    encoder = world.StateEncoder()
    original = state()
    original['nearby'] = [actor(1, 10), actor(2, 20, state_name='different')]
    with pytest.raises(ValueError, match='count'):
        encoder.encode(original)
    records = encoder.encode(state())
    assert records[0] == {'type': 'start', 'format': world.FORMAT}
    assert world.decode_records(records) == [state()]


def test_format_one_header_requires_its_original_decoder():
    with pytest.raises(ValueError, match='header'):
        world.decode_records([{'type': 'start', 'format': 'dotbox-keen-world-stream-1'}])


def test_maximum_state_depth_round_trips_through_one_record_wrapper():
    nested = 0
    for _ in range(31):
        nested = [nested]
    original = {'player': {}, 'unknown': nested}
    assert world.decode_records(world.encode_states([original])) == [original]
    too_deep = {'player': {}, 'unknown': [nested]}
    with pytest.raises(ValueError, match='nesting'):
        world.encode_states([too_deep])
