"""Memory-search contracts over authored bytes; no target payloads or live VM."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.memory_search import (
    MAX_CANDIDATES,
    MAX_INTERVALS,
    MAX_SNAPSHOT_BYTES,
    plan_edit,
    refine_search,
    search_results,
    snapshot_metadata,
    start_search,
    validate_search,
    validate_snapshot,
)


def context(length, **updates):
    result = dict(source_sha256='ab' * 32, run_id='run-1',
                  address_space='physical', region=dict(start=0x12000, length=length),
                  task_id='machine-physical', mapping_id='flat-a20-enabled', version_id=1)
    result.update(updates)
    return result


def snap(data, capture='capture-1', *, identity=None, **updates):
    return snapshot_metadata(data, context=identity or context(len(data)),
                             capture_id=capture, **updates)


def offsets(state, data, metadata, **kwargs):
    return [row['offset'] for row in search_results(state, data, metadata, **kwargs)['rows']]


def test_exact_unaligned_search_and_complete_last_scalar():
    # 0x1234 begins at unaligned offset 1 and at the last complete word.
    data = bytes([0x55, 0x34, 0x12, 0x77, 0x34, 0x12])
    metadata = snap(data)
    state = start_search(data, metadata, width=2, mode='equal', value=0x1234)
    result = search_results(state, data, metadata)
    assert state['candidate_count'] == 2 and state['complete'] is True
    assert offsets(state, data, metadata) == [1, 4]
    assert result['rows'][0]['address'] == '0x12001'
    assert result['rows'][0]['value'] == 0x1234
    assert result['rows'][0]['previous_value'] is None
    assert offsets(start_search(data, metadata, width=2, stride=2,
                                mode='equal', value=0x1234), data, metadata) == [4]


def test_unknown_candidates_are_compact_and_pagination_does_not_lose_them():
    data = bytes(1 << 20)
    metadata = snap(data)
    state = start_search(data, metadata)
    assert state['candidate_count'] == 1 << 20
    assert state['candidate_ranges'] == [[0, 1 << 20]]
    assert len(json.dumps(state)) < 2000
    page = search_results(state, data, metadata, offset=(1 << 20) - 2, limit=1)
    assert page['rows'][0]['offset'] == (1 << 20) - 2
    assert page['truncated'] is True and page['next_offset'] == (1 << 20) - 1
    last = search_results(state, data, metadata, offset=page['next_offset'], limit=1)
    assert last['truncated'] is False and last['next_offset'] is None
    assert state['candidate_count'] == 1 << 20


@pytest.mark.parametrize('width', [1, 2, 4, 8])
@pytest.mark.parametrize('byteorder', ['little', 'big'])
@pytest.mark.parametrize('signed', [False, True])
def test_scalar_width_signedness_and_byte_order(width, byteorder, signed):
    value = -(1 << (width * 8 - 1)) if signed else (1 << (width * 8)) - 1
    data = value.to_bytes(width, byteorder, signed=signed) + bytes(width)
    metadata = snap(data)
    state = start_search(data, metadata, width=width, signed=signed,
                         byteorder=byteorder, stride=width, mode='equal', value=value)
    assert offsets(state, data, metadata) == [0]
    assert search_results(state, data, metadata)['rows'][0]['value'] == value


def test_range_is_inclusive_and_bias_is_explicit():
    data = bytes([0, 1, 2, 3, 4, 5, 6])
    metadata = snap(data)
    state = start_search(data, metadata, mode='range', minimum=2, maximum=4, bias=-1)
    assert offsets(state, data, metadata) == [1, 2, 3]
    row = search_results(state, data, metadata)['rows'][0]
    assert row['value'] == 1 and row['displayed_value'] == 2
    plain = start_search(data, metadata, mode='equal', value=2)
    biased = start_search(data, metadata, mode='equal', value=2, bias=-1)
    assert offsets(plain, data, metadata) == [2]
    assert offsets(biased, data, metadata) == [1]


@pytest.mark.parametrize('mode,options,expected', [
    ('changed', {}, [0, 1, 3]),
    ('unchanged', {}, [2]),
    ('increased', {}, [0, 3]),
    ('decreased', {}, [1]),
    ('delta', {'delta': 2}, [0]),
    ('equal', {'value': 5}, [2]),
    ('not_equal', {'value': 5}, [0, 1, 3]),
])
def test_iterative_comparison_modes(mode, options, expected):
    before, after = bytes([1, 9, 5, 0]), bytes([3, 7, 5, 255])
    previous, current = snap(before), snap(after, 'capture-2')
    initial = start_search(before, previous)
    result = refine_search(initial, before, previous, after, current, mode=mode, **options)
    assert offsets(result, after, current) == expected
    assert result['generation'] == 1 and result['parent_sha256'] == initial['state_sha256']
    rows = search_results(result, after, current, before_data=before, before_snapshot=previous)['rows']
    assert [(r['previous_value'], r['value']) for r in rows] == [(before[i], after[i]) for i in expected]


def test_refinement_never_resurrects_eliminated_candidates_or_wraps_delta():
    one, two, three = bytes([5, 5, 9, 255]), bytes([4, 5, 5, 0]), bytes([5, 5, 5, 1])
    a, b, c = snap(one), snap(two, 'capture-2'), snap(three, 'capture-3')
    initial = start_search(one, a, mode='equal', value=5)
    narrowed = refine_search(initial, one, a, two, b, mode='decreased')
    final = refine_search(narrowed, two, b, three, c, mode='equal', value=5)
    assert offsets(narrowed, two, b) == [0]
    assert offsets(final, three, c) == [0]
    unknown = start_search(one, a)
    wrap = refine_search(unknown, one, a, two, b, mode='delta', delta=1)
    assert offsets(wrap, two, b) == []
    nonwrap = refine_search(unknown, one, a, two, b, mode='delta', delta=-255)
    assert offsets(nonwrap, two, b) == [3]


@pytest.mark.parametrize('change', [
    {'source_sha256': 'cd' * 32}, {'run_id': 'run-2'}, {'address_space': 'virtual'},
    {'region': {'start': 0x22000, 'length': 4}}, {'task_id': 'other-window'},
    {'mapping_id': 'another-ems-bank'}, {'version_id': 2}, {'mapping_epoch': 2},
])
def test_every_identity_component_prevents_cross_context_comparison(change):
    data = b'abcd'
    before = snap(data)
    after = snap(data, 'capture-2', identity=context(len(data), **change))
    state = start_search(data, before)
    with pytest.raises(ValueError, match='context'):
        refine_search(state, data, before, data, after, mode='unchanged')


def test_capture_metadata_may_change_without_changing_identity():
    data = b'abc'
    a = snap(data, captured_at='2026-11-07T14:00:00Z')
    b = snap(data, 'capture-2', captured_at='2026-11-07T14:00:01Z')
    assert a['context_sha256'] == b['context_sha256']
    assert a['snapshot_sha256'] != b['snapshot_sha256']
    state = refine_search(start_search(data, a), data, a, data, b, mode='unchanged')
    assert state['candidate_count'] == 3


def test_snapshot_and_state_roundtrip_are_detached_from_caller_mutations():
    data = b'abc'
    identity = context(len(data), evidence={'kind': 'observed', 'pages': [1, 2]})
    a = snap(data, identity=identity)
    identity['evidence']['pages'].append(3)
    assert a['context']['evidence']['pages'] == [1, 2]
    state = start_search(data, a)
    saved = json.loads(json.dumps(state))
    assert validate_snapshot(data, json.loads(json.dumps(a))) == a
    assert validate_search(saved, data, a) == saved
    returned = validate_search(saved, data, a)
    returned['candidate_ranges'][0][1] = 1
    assert saved['candidate_ranges'] == [[0, 3]]


def test_stale_snapshot_wrong_payload_and_replayed_capture_are_rejected():
    data, changed = b'abc', b'abd'
    a, b = snap(data), snap(changed, 'capture-2')
    state = start_search(data, a)
    with pytest.raises(ValueError, match='snapshot'):
        refine_search(state, changed, b, data, snap(data, 'capture-3'), mode='changed')
    with pytest.raises(ValueError, match='snapshot'):
        start_search(changed, a)
    with pytest.raises(ValueError, match='capture'):
        refine_search(state, data, a, data, a, mode='unchanged')
    next_state = refine_search(state, data, a, changed, b, mode='changed')
    with pytest.raises(ValueError, match='previous'):
        search_results(next_state, changed, b, before_data=data, before_snapshot=snap(data, 'wrong'))


@pytest.mark.parametrize('mutate', [
    lambda s: s['candidate_ranges'].append([0, 1]),
    lambda s: s['candidate_ranges'].__setitem__(0, [-1, 2]),
    lambda s: s['candidate_ranges'].__setitem__(0, [0, 5]),
    lambda s: s['candidate_ranges'].__setitem__(0, [True, 2]),
    lambda s: s.__setitem__('candidate_count', 1),
    lambda s: s.__setitem__('complete', False),
    lambda s: s.__setitem__('snapshot_sha256', '00' * 32),
    lambda s: s['spec'].__setitem__('stride', 0),
    lambda s: s.__setitem__('extra', 'unrecognized'),
])
def test_malformed_or_tampered_candidate_state_is_not_trusted(mutate):
    data = b'abcd'
    metadata = snap(data)
    state = start_search(data, metadata)
    mutate(state)
    with pytest.raises(ValueError):
        validate_search(state, data, metadata)


def test_budget_failures_never_return_a_truncated_reusable_state():
    data = bytes([7, 0, 7, 0, 7])
    metadata = snap(data)
    with pytest.raises(ValueError, match='candidate'):
        start_search(data, metadata, max_candidates=4)
    with pytest.raises(ValueError, match='candidate'):
        start_search(data, metadata, mode='equal', value=7, max_candidates=2)
    with pytest.raises(ValueError, match='candidate'):
        start_search(data, metadata, max_candidates=MAX_CANDIDATES + 1)
    alternating = b'\1\0' * (MAX_INTERVALS + 1)
    with pytest.raises(ValueError, match='interval'):
        start_search(alternating, snap(alternating), mode='equal', value=1)


def test_empty_result_remains_empty_and_small_region_has_no_partial_scalar():
    data = b'\1'
    metadata = snap(data)
    empty = start_search(data, metadata, width=2)
    assert empty['candidate_count'] == 0 and empty['total_positions'] == 0
    assert search_results(empty, data, metadata)['rows'] == []
    after = snap(b'\2', 'capture-2')
    assert refine_search(empty, data, metadata, b'\2', after, mode='changed')['candidate_count'] == 0


def test_guarded_edit_preserves_expected_bytes_and_observed_predicate():
    data = bytes([10, 20, 30])
    metadata = snap(data)
    state = start_search(data, metadata, mode='equal', value=21, bias=-1)
    plan = plan_edit(state, data, metadata, offset=1, value=100,
                     condition='less', compare_value=22)
    assert plan['address'] == '0x12001' and plan['offset'] == 1 and plan['length'] == 1
    assert plan['expected_hex'] == '14' and plan['replacement_hex'] == '63'
    assert plan['eligible'] is True and plan['condition']['matched'] is True
    assert plan['condition']['observed_value'] == 20
    assert plan['condition']['stored_comparison_value'] == 21
    assert plan['snapshot_sha256'] == metadata['snapshot_sha256']
    assert plan['context'] == metadata['context'] and plan['write_performed'] is False
    assert data == bytes([10, 20, 30])


@pytest.mark.parametrize('condition,comparison,eligible', [
    ('equal', 20, True), ('equal', None, True), ('equal', 19, False),
    ('not_equal', 20, False), ('not_equal', 19, True),
    ('greater', 19, True), ('greater', 20, False),
    ('greater_equal', 20, True), ('less', 20, False),
    ('less_equal', 20, True), ('always', None, True),
])
def test_conditional_edit_has_an_explicit_non_writing_false_result(condition, comparison, eligible):
    data = bytes([20])
    metadata = snap(data)
    plan = plan_edit(start_search(data, metadata), data, metadata,
                     offset=0, value=21, condition=condition, compare_value=comparison)
    assert plan['eligible'] is eligible
    assert plan['status'] == ('planned' if eligible else 'condition-not-met')
    assert plan['write_performed'] is False and plan['expected_hex'] == '14'


@pytest.mark.parametrize('options', [
    {'offset': 0, 'value': 256}, {'offset': 0, 'value': -1},
    {'offset': 0, 'value': True}, {'offset': 0, 'value': 2, 'condition': 'mystery'},
    {'offset': 0, 'value': 2, 'condition': 'greater'},
    {'offset': 1, 'value': 2}, {'offset': True, 'value': 2},
])
def test_edit_refuses_overflow_unsupported_conditions_and_non_candidates(options):
    data = bytes([1, 0])
    metadata = snap(data)
    state = start_search(data, metadata, mode='equal', value=1)
    with pytest.raises(ValueError):
        plan_edit(state, data, metadata, **options)


@pytest.mark.parametrize('options', [
    {'width': 0}, {'width': 3}, {'width': True}, {'signed': 1},
    {'byteorder': 'native'}, {'stride': 0}, {'stride': True},
    {'mode': 'equal'}, {'mode': 'unknown', 'value': 5},
    {'mode': 'range', 'minimum': 4, 'maximum': 3},
    {'mode': 'equal', 'value': 256}, {'mode': 'equal', 'value': -1},
    {'mode': 'equal', 'value': 0, 'bias': -1}, {'bias': True},
    {'max_candidates': True},
])
def test_invalid_scalar_or_predicate_contracts_refuse(options):
    data = b'\1\2\3\4'
    with pytest.raises(ValueError):
        start_search(data, snap(data), **options)


@pytest.mark.parametrize('missing', [
    'source_sha256', 'run_id', 'address_space', 'region', 'task_id', 'mapping_id', 'version_id',
])
def test_missing_context_identity_refuses(missing):
    identity = context(1)
    identity.pop(missing)
    with pytest.raises(ValueError, match='context'):
        snap(b'x', identity=identity)


def test_snapshot_bounds_and_metadata_shape():
    with pytest.raises(ValueError):
        snap(b'')
    with pytest.raises(ValueError):
        snap(bytearray(b'a'))
    with pytest.raises(ValueError):
        snap(bytes(MAX_SNAPSHOT_BYTES + 1))
    with pytest.raises(ValueError):
        snap(b'x', identity=context(2))
    with pytest.raises(ValueError):
        snap(b'x', identity=context(1, region={'start': (1 << 64) - 1, 'length': 2}))
    with pytest.raises(ValueError):
        snap(b'x', identity=context(1, extra=float('nan')))
    recursive = context(1)
    recursive['self'] = recursive
    with pytest.raises(ValueError):
        snap(b'x', identity=recursive)
    original = snap(b'x')
    altered = deepcopy(original)
    altered['context']['region']['start'] += 1
    with pytest.raises(ValueError, match='snapshot'):
        validate_snapshot(b'x', altered)


def test_boolean_metadata_never_aliases_numeric_fields_even_with_a_recomputed_checksum():
    data = b'\1'
    metadata = snap(data)
    altered = deepcopy(metadata)
    altered['length'] = True
    with pytest.raises(ValueError):
        validate_snapshot(data, altered)
    state = start_search(data, metadata, mode='equal', value=1)
    state['query']['stored_value'] = True
    # Structural checks must not depend solely on someone retaining the old
    # checksum. This is an invalid scalar representation despite equal Python
    # comparisons between True and 1.
    payload = {key: value for key, value in state.items() if key != 'state_sha256'}
    state['state_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True,
        ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
    with pytest.raises(ValueError, match='query'):
        validate_search(state, data, metadata)


def test_bias_keeps_large_display_values_exact_without_scalar_wrap():
    data = bytes([255]) * 8
    metadata = snap(data)
    state = start_search(data, metadata, width=8, mode='equal', value=1 << 64, bias=-1)
    assert search_results(state, data, metadata)['rows'][0]['displayed_value'] == 1 << 64
    plan = plan_edit(state, data, metadata, offset=0, value=1 << 64)
    assert plan['replacement_hex'] == 'ff' * 8 and plan['condition']['matched'] is True
    with pytest.raises(ValueError, match='wrapping'):
        plan_edit(state, data, metadata, offset=0, value=(1 << 64) + 1)
