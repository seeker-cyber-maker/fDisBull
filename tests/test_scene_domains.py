"""Authored coordinate metadata; no original inputs, transforms or native claims."""
from copy import deepcopy

import pytest

from fdisbull.scene_domains import audit_coordinate_domains, validate_coordinate_domains


def descriptor():
    return {'format': 'fdisbull-coordinate-domains-1',
            'space': {'name': 'declared-common-space', 'unit': 'game-unit'},
            'bounds': {'world': [0, 0, 20, 20], 'room': [0, 0, 20, 20],
                       'collision': [0, 0, 20, 20], 'viewport': [0, 0, 10, 10]},
            'objects': [{'id': 'actor', 'role': 'actor', 'pose': [9, 5],
                         'render': [0, -2, 3, 1], 'collision': [0, 0, 1, 1]}],
            'expectations': [], 'alerts': True,
            'provenance': {'scope': 'Authored geometry only; no live observation.'}}


def relation(result, part='render', domain='viewport', ident='actor'):
    return next(r for r in result['relations']
                if (r['object_id'], r['part'], r['domain']) == (ident, part, domain))


def expectation():
    return {'id': 'declared-buffer', 'mechanism': 'scroll-prefetch',
            'roles': ['actor'], 'domains': ['viewport'], 'parts': ['render'],
            'max_margins': {'left': 0, 'top': 0, 'right': 2, 'bottom': 0},
            'reason': 'Authored expected buffer, not an engine whitelist.',
            'evidence_status': 'declared'}


def test_render_and_collision_extents_are_independent_and_half_open():
    result = audit_coordinate_domains(descriptor())
    render = relation(result)
    assert result['complete'] is True and result['examined'] == result['total_comparisons'] == 8
    assert render['absolute_bounds'] == [9, 3, 12, 6]
    assert render['clipped_bounds'] == [9, 3, 10, 6]
    assert render['overhang'] == {'left': 0, 'top': 0, 'right': 2, 'bottom': 0}
    assert render['relation'] == 'crosses' and render['anomaly_flag'] is True
    baseline = relation(result, 'collision')
    assert baseline['relation'] == 'contained' and baseline['absolute_bounds'] == [9, 5, 10, 6]
    assert baseline['anomaly_flag'] is False and baseline['layout_notice'] is False
    assert 'classification' not in render and 'safe' not in result


def test_anchor_inside_room_does_not_hide_extent_outside_room():
    doc = descriptor(); doc['objects'][0]['pose'] = [19, 5]
    record = relation(audit_coordinate_domains(doc), domain='room')
    assert record['pose'] == [19, 5]
    assert record['absolute_bounds'] == [19, 3, 22, 6]
    assert record['relation'] == 'crosses' and record['overhang']['right'] == 2


def test_signed_pose_completely_outside_is_preserved_without_clipping_it_away():
    doc = descriptor(); doc['objects'][0].update(pose=[-3, 5], render=[-2, -4, 2, 1])
    record = relation(audit_coordinate_domains(doc), domain='room')
    assert record['absolute_bounds'] == [-5, 1, -1, 6]
    assert record['local_bounds'] == [-2, -4, 2, 1]
    assert record['relation'] == 'outside' and record['clipped_bounds'] is None
    assert record['overhang']['left'] == 5


def test_edge_touch_is_outside_not_positive_overlap():
    doc = descriptor(); doc['objects'][0]['pose'] = [10, 5]
    record = relation(audit_coordinate_domains(doc))
    assert record['relation'] == 'outside' and record['clipped_bounds'] is None


def test_tall_render_box_can_cross_top_while_baseline_is_inside():
    doc = descriptor(); doc['objects'][0].update(pose=[5, 0], render=[-2, -4, 2, 1])
    result = audit_coordinate_domains(doc)
    assert relation(result)['overhang']['top'] == 4
    assert relation(result)['clipped_bounds'] == [3, 0, 7, 1]
    assert relation(result, 'collision')['relation'] == 'contained'


def test_unknown_viewport_does_not_invent_a_camera_transform():
    doc = descriptor(); doc['bounds']['viewport'] = None
    result = audit_coordinate_domains(doc)
    record = relation(result)
    assert record['relation'] == 'unknown' and record['unknown'] == ['domain']
    assert record['anomaly_candidate'] is None and record['anomaly_flag'] is None
    assert record['layout_notice'] is True and record['overhang'] is None
    assert relation(result, domain='room')['relation'] == 'contained'


@pytest.mark.parametrize('missing', ['pose', 'render'])
def test_missing_pose_or_part_is_unknown(missing):
    doc = descriptor(); doc['objects'][0][missing] = None
    record = relation(audit_coordinate_domains(doc))
    assert record['relation'] == 'unknown'
    assert record['unknown'] == (['pose'] if missing == 'pose' else ['part'])
    assert record['absolute_bounds'] is None


def test_bounds_only_census_has_no_invented_boxes_or_movement_authority():
    doc = descriptor()
    doc['bounds'] = {'world': [0, 0, 80, 50], 'room': None, 'collision': None, 'viewport': None}
    doc['objects'][0].update(role='census', pose=[12, 9], render=None, collision=None)
    result = audit_coordinate_domains(doc)
    assert all(r['relation'] == 'unknown' for r in result['relations'])
    assert all(r['absolute_bounds'] is None and r['expectation'] is None for r in result['relations'])


def test_declared_camera_translation_changes_only_viewport_comparisons():
    doc = descriptor(); doc['objects'][0]['pose'] = [15, 5]
    before = audit_coordinate_domains(doc)
    doc['bounds']['viewport'] = [10, 0, 20, 10]
    after = audit_coordinate_domains(doc)
    assert relation(before)['relation'] == 'outside'
    assert relation(after)['relation'] == 'contained'
    assert [r for r in before['relations'] if r['domain'] != 'viewport'] == [r for r in after['relations'] if r['domain'] != 'viewport']


def test_expected_margin_suppresses_flag_but_retains_raw_relation_and_layout_note():
    doc = descriptor(); doc['expectations'] = [expectation()]
    record = relation(audit_coordinate_domains(doc))
    assert record['relation'] == 'crosses' and record['anomaly_candidate'] is True
    assert record['disposition'] == 'expected' and record['anomaly_flag'] is False
    assert record['layout_notice'] is True and record['overhang']['right'] == 2
    assert record['expectation']['id'] == 'declared-buffer'
    assert record['expectation']['evidence_status'] == 'declared'
    assert record['suppressed_by'] == ['expectation:declared-buffer']


@pytest.mark.parametrize('change', ['role', 'part', 'domain', 'exceeded', 'mechanism_name_only'])
def test_expectations_apply_only_to_explicit_scope_and_margin(change):
    doc = descriptor(); rule = expectation(); doc['expectations'] = [rule]
    if change == 'role': rule['roles'] = ['prefetch']
    elif change == 'part': rule['parts'] = ['collision']
    elif change == 'domain': rule['domains'] = ['room']
    elif change == 'exceeded': doc['objects'][0]['pose'][0] = 10
    else: doc['expectations'] = []  # No automatic policy follows a mechanism name/role.
    record = relation(audit_coordinate_domains(doc))
    assert record['expectation'] is None and record['anomaly_flag'] is True
    assert record['disposition'] == 'unexplained'


def test_global_alerts_switch_preserves_known_and_unknown_layout_notices():
    doc = descriptor(); doc['alerts'] = False; doc['bounds']['collision'] = None
    result = audit_coordinate_domains(doc)
    known = relation(result); unknown = relation(result, domain='collision')
    assert known['relation'] == 'crosses' and known['anomaly_candidate'] is True
    assert known['anomaly_flag'] is False and known['layout_notice'] is True
    assert known['suppressed_by'] == ['global_alerts_disabled']
    assert unknown['relation'] == 'unknown' and unknown['anomaly_candidate'] is None
    assert unknown['anomaly_flag'] is False and unknown['layout_notice'] is True


def test_expectation_cannot_resolve_unknown_extent():
    doc = descriptor(); doc['expectations'] = [expectation()]; doc['objects'][0]['render'] = None
    record = relation(audit_coordinate_domains(doc))
    assert record['relation'] == 'unknown' and record['expectation'] is None
    assert record['anomaly_flag'] is None


def test_huge_declared_domains_and_absolute_sums_need_no_raster_canvas():
    doc = descriptor(); doc['bounds'] = {k: [-2**31, -2**31, 2**31-1, 2**31-1] for k in doc['bounds']}
    doc['objects'][0].update(pose=[2**31-1, 2**31-1], render=[0, 0, 2**31-1, 2**31-1])
    record = relation(audit_coordinate_domains(doc))
    assert record['absolute_bounds'] == [2**31-1, 2**31-1, 2**32-2, 2**32-2]
    assert record['relation'] == 'outside'


def test_validation_and_audit_do_not_mutate_or_alias_input():
    doc = descriptor(); original = deepcopy(doc)
    assert validate_coordinate_domains(doc) is doc
    result = audit_coordinate_domains(doc)
    assert doc == original
    result['relations'][0]['domain_bounds'][0] = 99
    result['provenance']['scope'] = 'changed output'
    assert doc == original


def test_partial_budget_retains_records_and_exact_total_without_claiming_complete():
    result = audit_coordinate_domains(descriptor(), max_checks=3)
    assert result['complete'] is False and result['examined'] == 3 and result['total_comparisons'] == 8
    assert [(r['part'], r['domain']) for r in result['relations']] == [('render', 'world'), ('render', 'room'), ('render', 'collision')]


def test_full_budget_and_empty_object_list_are_complete():
    assert audit_coordinate_domains(descriptor(), max_checks=8)['complete'] is True
    doc = descriptor(); doc['objects'] = []
    result = audit_coordinate_domains(doc)
    assert result['complete'] is True and result['examined'] == 0 and result['relations'] == []


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(alerts=1), lambda d: d.update(extra=True),
    lambda d: d['bounds'].update(camera=None), lambda d: d['bounds'].pop('room'),
    lambda d: d['bounds'].update(world=[0, 0, 0, 3]),
    lambda d: d['bounds'].update(world=[0, 0, True, 3]),
    lambda d: d['bounds'].update(world=[0, 0, 2**31, 3]),
    lambda d: d['objects'][0].update(pose=[0.0, 1]),
    lambda d: d['objects'][0].update(pose=[0, 1, 2]),
    lambda d: d['objects'][0].update(render=[3, 0, 2, 1]),
    lambda d: d['objects'][0].update(extra=True),
    lambda d: d['objects'].append(deepcopy(d['objects'][0])),
    lambda d: d.update(provenance={}), lambda d: d.update(provenance={'number': float('nan')}),
    lambda d: d.update(space={'name': 'world'}), lambda d: d['space'].update(unit=''),
])
def test_malformed_descriptor_is_refused(mutate):
    doc = descriptor(); mutate(doc)
    with pytest.raises(ValueError): validate_coordinate_domains(doc)


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(roles=[]), lambda r: r.update(domains=['unknown']),
    lambda r: r.update(parts=['visual']), lambda r: r.update(roles=['actor', 'actor']),
    lambda r: r['max_margins'].update(right=-1), lambda r: r['max_margins'].update(right=True),
    lambda r: r['max_margins'].pop('left'), lambda r: r.update(reason=''),
    lambda r: r.update(evidence_status=''), lambda r: r.update(extra=True),
])
def test_malformed_expectation_is_refused(mutate):
    doc = descriptor(); rule = expectation(); mutate(rule); doc['expectations'] = [rule]
    with pytest.raises(ValueError): validate_coordinate_domains(doc)


def test_duplicate_expectation_and_count_document_budgets_are_refused():
    doc = descriptor(); doc['expectations'] = [expectation(), expectation()]
    with pytest.raises(ValueError): validate_coordinate_domains(doc)
    doc = descriptor(); doc['objects'] *= 1025
    with pytest.raises(ValueError): validate_coordinate_domains(doc)
    doc = descriptor(); doc['provenance']['oversized'] = 'x'*(1024*1024)
    with pytest.raises(ValueError): validate_coordinate_domains(doc)


def test_maximum_object_count_has_exact_bounded_comparison_budget():
    doc = descriptor(); template = doc['objects'][0]
    doc['objects'] = [dict(deepcopy(template), id='actor-'+str(i)) for i in range(1024)]
    partial = audit_coordinate_domains(doc)
    assert partial['complete'] is False
    assert partial['examined'] == 4096 and partial['total_comparisons'] == 8192
    complete = audit_coordinate_domains(doc, max_checks=8192)
    assert complete['complete'] is True and complete['examined'] == 8192
    assert complete['relations'][-1]['object_id'] == 'actor-1023'


def test_expectation_count_budget_and_unknown_multiple_reasons():
    doc = descriptor(); doc['expectations'] = [dict(expectation(), id='rule-'+str(i)) for i in range(129)]
    with pytest.raises(ValueError): validate_coordinate_domains(doc)
    doc = descriptor(); doc['objects'][0].update(pose=None, render=None); doc['bounds']['viewport'] = None
    record = relation(audit_coordinate_domains(doc))
    assert record['unknown'] == ['pose', 'part', 'domain']
    assert record['absolute_bounds'] is None and record['relation'] == 'unknown'


def test_expectation_does_not_change_any_geometry_relation_or_other_domain_policy():
    doc = descriptor(); doc['objects'][0]['pose'] = [19, 5]
    before = audit_coordinate_domains(doc)
    rule = expectation(); rule['max_margins']['right'] = 12; doc['expectations'] = [rule]
    after = audit_coordinate_domains(doc)
    for left, right in zip(before['relations'], after['relations']):
        for key in ['absolute_bounds', 'domain_bounds', 'clipped_bounds', 'overhang', 'relation']:
            assert left[key] == right[key]
    assert relation(after)['anomaly_flag'] is False
    assert relation(after, domain='room')['anomaly_flag'] is True
    assert relation(after, domain='collision')['anomaly_flag'] is True


def test_summary_counts_expected_suppression_and_unknown_geometry_independently():
    doc = descriptor(); doc['bounds']['collision'] = None; doc['expectations'] = [expectation()]
    summary = audit_coordinate_domains(doc)['summary']
    assert summary == {'count_scope': 'all_comparisons', 'examined': 8,
                       'total_comparisons': 8, 'unexamined': 0,
                       'dispositions': {'contained': 5, 'expected': 1, 'unexplained': 0, 'unknown': 2},
                       'anomaly_flags': {'raised': 0, 'not_raised': 6, 'unknown': 2},
                       'unknown_relations': 2, 'suppressed_candidates': 1, 'layout_notices': 3}
    doc['alerts'] = False
    disabled = audit_coordinate_domains(doc)['summary']
    assert disabled['anomaly_flags'] == {'raised': 0, 'not_raised': 8, 'unknown': 0}
    assert disabled['unknown_relations'] == 2 and disabled['layout_notices'] == 3


def test_partial_summary_counts_are_explicitly_examined_only():
    summary = audit_coordinate_domains(descriptor(), max_checks=3)['summary']
    assert summary['count_scope'] == 'examined_only'
    assert (summary['examined'], summary['unexamined'], summary['total_comparisons']) == (3, 5, 8)
    assert summary['dispositions'] == {'contained': 3, 'expected': 0, 'unexplained': 0, 'unknown': 0}
    assert summary['anomaly_flags'] == {'raised': 0, 'not_raised': 3, 'unknown': 0}


@pytest.mark.parametrize('budget', [0, True, 8193, 1.5])
def test_invalid_audit_budget_is_refused(budget):
    with pytest.raises(ValueError): audit_coordinate_domains(descriptor(), max_checks=budget)


def test_invalid_tail_is_validated_even_when_comparison_budget_is_small():
    doc = descriptor(); doc['objects'].append({'id': 'bad'})
    with pytest.raises(ValueError): audit_coordinate_domains(doc, max_checks=1)
