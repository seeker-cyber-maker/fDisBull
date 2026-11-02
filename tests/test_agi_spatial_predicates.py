"""Authored AGI encodings; no original game resource or message text."""
from hashlib import sha256

import pytest

from fdisbull.agi_spatial_predicates import analyze_posn_boundaries, describe_posn_boundaries


def conditional(tests, body):
    return b'\xff'+tests+b'\xff'+len(body).to_bytes(2, 'little')+body


def sample(rect=(3, 2, 6, 5), *, reverse=False, other_context=False, marker=b'', extra_inside=b''):
    position = bytes((11, 0, *rect))
    context = bytes((1, 7, 0))
    other = bytes((1, 7, 1 if other_context else 0))
    # A guarded parser action drops item 3. IDs and labels are unit-only.
    action = bytes((7, 8, 14, 2, 42, 0, 43, 0))
    inside = conditional(action, bytes((13, 8, 101, 9, 94, 3, 7, 3, 2))+extra_inside)
    outside = conditional(action, bytes((13, 8, 101, 10, 94, 3, 7, 3, 2, 5, 3, 7)))
    positive = conditional(marker+position+context, inside)
    negative = conditional(b'\xfd'+position+other, outside)
    code = negative+positive+b'\0' if reverse else positive+negative+b'\0'
    return len(code).to_bytes(2, 'little')+code


def analyze(payload=None, **kwargs):
    options = dict(logic_number=17, width=10, height=7, origin=(5, 3), actor_width=2,
                   variables={'7': 0}, item_labels={3: 'unit water'})
    options.update(kwargs)
    return analyze_posn_boundaries(sample() if payload is None else payload, **options)


def test_source_pair_band_and_effects_are_decoded_without_preset_coordinates():
    payload = sample()
    report = analyze(payload)
    assert report['complete'] is True
    assert report['source'] == {'logic': 17, 'resource_sha256': sha256(payload).hexdigest()}
    pair = report['source_pairs'][0]
    assert pair['arguments'] == [0, 3, 2, 6, 5]
    assert pair['shared_scalar_context']['matches_supplied_state'] is True
    finding = report['findings'][0]
    band = finding['bands'][0]['predicate_band']
    assert band['row_runs'] == [[6, 3, 7]] and band['count'] == 4 and band['thickness'] == 1
    assert band['witness'] == {'inside': [5, 5], 'outside': [5, 6], 'selection': 'start_projection'}
    assert band['reachability'] == {'status': 'unknown'}
    contrast = finding['action_contrasts'][0]
    assert contrast['item'] == 3 and contrast['label'] == 'unit water'
    assert contrast['inside']['linear_score_delta'] == -2
    assert contrast['outside']['linear_score_delta'] == 5
    code = payload[2:]
    for side, message in (('inside', 9), ('outside', 10)):
        prints = [op for op in contrast[side]['operations'] if op['operation'] == 'print']
        assert len(prints) == 1 and prints[0]['arguments'] == [message]
        assert prints[0]['source_offset'] == code.index(bytes((101, message)))
    assert finding['bands'][0]['static_geometry']['status'] == 'not_supplied'
    assert report['native_reachability'] == 'not_established_by_this_capture'
    assert 'Native reachability' in describe_posn_boundaries(report, focus_item=3)


def test_pic_ray_is_separate_from_reachability_and_adjacent_column_is_derived():
    plane = bytearray([4]*70)
    plane[5*10+6] = 0
    report = analyze(priority_plane=bytes(plane), picture_sha256='a'*64,
                     reference_actor={'x': 0, 'y': 1, 'width': 2})
    record = report['findings'][0]['bands'][0]
    geometry = record['static_geometry']
    assert geometry['origin_ray']['static_passable'] is False
    assert geometry['origin_ray']['first_blocked']['origin'] == [5, 5]
    assert geometry['origin_ray']['first_blocked']['blocked_offsets'] == [1]
    assert geometry['proposal']['inside'] == [4, 5] and geometry['proposal']['outside'] == [4, 6]
    assert geometry['proposal']['ray']['waypoints'] == [[5, 3], [4, 3], [4, 6]]
    assert geometry['native_reachability'] == 'unknown'
    assert record['predicate_band']['reachability'] == {'status': 'unknown'}
    contrast = record['geometric_contrast']
    assert (contrast['origin_distance'], contrast['inside_distance'], contrast['outside_distance']) == (7, 8, 9)
    assert contrast['outside_no_closer_than_inside'] and contrast['outside_no_closer_than_origin']
    text = describe_posn_boundaries(report, focus_item=3)
    assert 'Static proposal: (4, 6)' in text and 'no closer' in text
    assert 'throw-range predicate' in contrast['scope']


def test_polarity_order_is_not_assumed_and_context_must_match():
    finding = analyze(sample(reverse=True))['findings'][0]
    assert finding['inside_if_offset'] > finding['outside_if_offset']
    assert finding['action_contrasts'][0]['inside']['linear_score_delta'] == -2
    assert analyze(sample(other_context=True))['findings'] == []
    assert analyze(variables={})['source_pairs'][0]['shared_scalar_context']['matches_supplied_state'] is None
    assert analyze(variables={'7': 1})['source_pairs'][0]['shared_scalar_context']['matches_supplied_state'] is False


def test_valid_empty_complement_and_no_posn_pair_are_not_errors():
    report = analyze(sample((0, 0, 9, 6)))
    assert report['complete'] is True and report['findings'] == []
    assert len(report['source_pairs']) == 1
    assert analyze(b'\x01\x00\x00')['source_pairs'] == []


@pytest.mark.parametrize('marker', [b'\xfc\xfc', b'\xfc\xfc\xfc\xfc'])
def test_or_markers_are_not_treated_as_an_and_rectangle(marker):
    assert analyze(sample(marker=marker))['findings'] == []


@pytest.mark.parametrize('payload', [b'', b'\x05\x00\x00',
    sample(marker=b'\xfd\xfd'), sample(marker=b'\xfc')])
def test_malformed_source_and_repeated_not_fail_explicitly(payload):
    with pytest.raises(ValueError): analyze(payload)


@pytest.mark.parametrize('kwargs', [{'actor_width': True}, {'logic_number': False},
    {'variables': []}, {'variables': {'7': True}}, {'flags': {'8': 1}},
    {'max_checks': True}, {'max_source_steps': 0}, {'max_pairs': False},
    {'origin': (10, 3)}, {'priority_plane': bytes(69), 'picture_sha256': 'a'*64},
    {'priority_plane': bytes(70)}, {'reference_actor': {'x': True, 'y': 1, 'width': 2}}])
def test_strict_types_and_declared_geometry(kwargs):
    with pytest.raises(ValueError): analyze(**kwargs)


def test_cell_budget_marks_partial_output_without_native_or_complete_claim():
    report = analyze(max_checks=2)
    assert report['complete'] is False and report['examined'] == 2
    band = report['findings'][0]['bands'][0]['predicate_band']
    assert band['complete'] is False and band['count'] == 2
    assert band['reachability']['status'] == 'unknown'
    assert 'incomplete' in describe_posn_boundaries(report).lower()


def test_source_operation_and_node_caps_fail_incomplete_instead_of_running_unbounded():
    report = analyze(max_source_steps=1)
    assert report['complete'] is False and report['source_work']['used'] <= 1
    assert report['budget_stop'] == 'source parsing budget'
    code = b'\0'*4097
    report = analyze(len(code).to_bytes(2, 'little')+code)
    assert report['complete'] is False and report['budget_stop'] == 'source instruction cap'


def test_truncated_effect_group_never_gets_a_qualified_score_delta():
    payload = sample(extra_inside=bytes((5, 3, 1))*100)
    report = analyze(payload, max_source_steps=350)
    assert report['complete'] is False and report['source_work']['used'] <= 350
    assert report['budget_stop'] == 'source effect budget'
    groups = [g for finding in report['findings'] for side in finding['effect_groups'].values() for g in side]
    assert any(not g['complete'] for g in groups)
    assert all(g['linear_score_delta'] is None for g in groups if not g['complete'])


@pytest.mark.parametrize('operation', [bytes(v) for v in (
    (1, 3), (2, 3), (3, 3, 100), (4, 3, 9), (6, 3, 9), (8, 3, 9),
    (9, 9, 8), (10, 3, 9), (11, 9, 100), (130, 0, 10, 3), (39, 0, 3, 9),
    (51, 0, 3), (22, 9), (23, 9), (0,), (254, 0, 0), (165, 3, 2))])
def test_score_aliases_assignments_and_unproved_control_flow_invalidate_delta(operation):
    report = analyze(sample(extra_inside=operation+bytes((5, 3, 2))))
    group = report['findings'][0]['action_contrasts'][0]['inside']
    assert group['complete'] is True
    assert group['linear_score_delta'] is None
    assert any(op['opcode'] == operation[0] for op in group['operations'])


def test_unrelated_direct_variable_write_does_not_invalidate_constant_operand_sum():
    report = analyze(sample(extra_inside=bytes((3, 9, 100))))
    group = report['findings'][0]['action_contrasts'][0]['inside']
    assert group['linear_score_delta'] == -2
    assert 'Mathematical' in group['linear_score_delta_scope']
    assert 'wrap' in group['linear_score_delta_scope']
