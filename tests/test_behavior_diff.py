"""Bounded behavioral diffing keeps code, path and sampled effects separate."""
import pytest

from fdisbull.behavior_diff import compare_trace_topology
from fdisbull.debug_experiments import compare_trials


def event(address, *, version=1, code='90', ax='0x1', flags='0x0', context='flat'):
    return {'identity': {'source_version': version, 'context': context,
                         'project_address': address},
            'project_address': address, 'bytes': code,
            'registers': {'general': {'ax': ax}, 'flags': flags}}


def trace(events, *, semantics='completed_steps'):
    return {'events': events, 'semantics': semantics}


def trial(events, *, memory='000000', registers=None):
    return {'ok': True, 'registers': registers or {'general': {'ax': '0x1'}, 'flags': '0x0'},
            'memory': [{'project_address': '0x200', 'hex': memory}],
            'traces': [{'step': 1, 'artifact': 'trace', **trace(events)}],
            'screenshots': [], 'observations': []}


def test_code_replacement_at_same_site_does_not_invent_behavioral_effect():
    baseline = [event('0x100'), event('0x101', code='b80100'), event('0x104')]
    layer = [event('0x100'), event('0x101', code='b80200'), event('0x104')]
    topology = compare_trace_topology(trace(baseline), trace(layer), same_source=True)
    assert [x['kind'] for x in topology['segments']] == ['common']
    assert topology['code_difference'] is True
    assert topology['control_flow_difference'] is False
    assert topology['observed_register_difference'] is False
    result = compare_trials(trial(baseline), trial(layer), same_source=True)
    assert result['observed_difference'] is True  # Existing byte-sensitive verdict.
    assert result['code_difference'] is True
    assert result['observed_effect_difference'] is False
    assert result['semantic_equivalence'] is None


def test_diverge_and_rejoin_distinguishes_path_from_sampled_state():
    baseline = [event('0x100'), event('0x101'), event('0x102', ax='0x2'),
                event('0x110', ax='0x2', flags='0x1'), event('0x111', ax='0x1')]
    layer = [event('0x100'), event('0x105'), event('0x106', ax='0x2'),
             event('0x110', ax='0x2', flags='0x0'), event('0x111', ax='0x1')]
    result = compare_trace_topology(trace(baseline), trace(layer), same_source=True)
    assert [x['kind'] for x in result['segments']] == ['common', 'divergent', 'common']
    assert result['segments'][1]['baseline'] == [1, 3]
    assert result['segments'][1]['layer'] == [1, 3]
    assert result['segments'][1]['rejoin']['registers']['different_fields'] == ['flags']
    assert result['segments'][2]['exit_registers']['relation'] == 'equal'
    assert result['control_flow_difference'] is True
    assert result['observed_register_difference'] is True


def test_repeated_loop_site_without_unique_anchor_has_no_claimed_rejoin():
    baseline = [event('0x100'), event('0x101'), event('0x101')]
    layer = [event('0x100'), event('0x101'), event('0x101'), event('0x101')]
    result = compare_trace_topology(trace(baseline), trace(layer), same_source=True)
    assert result['segments'][-1]['kind'] == 'open_tail'
    assert result['segments'][-1]['rejoin'] is None
    assert result['control_flow_difference'] is None
    assert result['coverage']['aligned_pairs'] == 3


def test_distinct_binary_versions_need_evidenced_correspondence():
    a = trace([event('0x100', version=1), event('0x101', version=1)])
    b = trace([event('0x900', version=2), event('0x901', version=2)])
    assert compare_trace_topology(a, b)['alignment'] == 'unknown'
    correspondence = [{'baseline': {'source_version': 1, 'context': 'flat', 'project_address': f'0x10{i}'},
                       'layer': {'source_version': 2, 'context': 'flat', 'project_address': f'0x90{i}'},
                       'evidence': 'authored fixture correspondence'} for i in (0, 1)]
    result = compare_trace_topology(a, b, correspondence=correspondence)
    assert result['alignment'] == 'evidenced'
    assert result['coverage']['aligned_pairs'] == 2
    assert result['control_flow_difference'] is False
    correspondence[0]['evidence'] = ''
    with pytest.raises(ValueError, match='provenance'):
        compare_trace_topology(a, b, correspondence=correspondence)


def test_same_local_version_number_does_not_align_separate_binaries():
    a = trace([event('0x100', version=1)])
    b = trace([event('0x100', version=1)])
    result = compare_trace_topology(a, b)
    assert result['alignment'] == 'unknown'
    assert result['control_flow_difference'] is None
    assert result['code_difference'] is None


def test_partial_cross_binary_map_keeps_unmatched_path_unknown():
    a = trace([event('0x100', version=1), event('0x101', version=1)])
    b = trace([event('0x900', version=2), event('0x901', version=2)])
    correspondence = [{'baseline': {'source_version': 1, 'context': 'flat', 'project_address': '0x100'},
                       'layer': {'source_version': 2, 'context': 'flat', 'project_address': '0x900'},
                       'evidence': 'authored fixture correspondence'}]
    result = compare_trace_topology(a, b, correspondence=correspondence)
    assert result['alignment'] == 'partial'
    assert result['control_flow_difference'] is None
    assert result['coverage']['aligned_pairs'] == 1
    assert result['code_difference'] is None
    assert result['observed_register_difference'] is None


def test_unmapped_sites_are_not_assumed_equal_and_dos_fetch_is_uncertain():
    a = event('0x100')
    b = event('0x100')
    a['identity']['project_address'] = b['identity']['project_address'] = None
    result = compare_trace_topology(trace([a], semantics='pre_execution_fetch_last_pending'),
                                    trace([b], semantics='pre_execution_fetch_last_pending'),
                                    same_source=True)
    assert result['alignment'] == 'partial'
    assert result['coverage']['aligned_pairs'] == 0
    assert result['segments'][0]['kind'] == 'unresolved'
    assert result['control_flow_difference'] is None
    assert any('retirement' in reason for reason in result['unknown'])


def test_selected_memory_reports_changed_byte_runs_and_flags():
    a, b = event('0x100'), event('0x100', flags='0x40')
    result = compare_trials(trial([a], memory='000000000000'),
                            trial([b], memory='000102000300', registers={'general': {'ax': '0x1'}, 'flags': '0x40'}),
                            same_source=True)
    assert result['memory'][0]['changed'] == {
        'runs': [{'offset': 1, 'length': 2}, {'offset': 4, 'length': 1}],
        'run_count': 2, 'changed_bytes': 3, 'runs_truncated': False}
    assert result['observed_effect_difference'] is True
    assert result['traces'][0]['topology']['register_changes'][0]['fields'] == ['flags']


def test_trace_budget_and_missing_registers_remain_unknown():
    a = event('0x100')
    b = event('0x100')
    del b['registers']
    result = compare_trace_topology({**trace([a]), 'requested_count': 1}, trace([b]), same_source=True)
    assert any('budget' in reason for reason in result['unknown'])
    assert any('Register snapshots' in reason for reason in result['unknown'])
    with pytest.raises(ValueError, match='event budget'):
        compare_trace_topology(trace([a, a]), trace([a]), same_source=True, max_events=1)


def test_instruction_text_is_not_a_code_byte_change_and_missing_bytes_are_unknown():
    a, b = event('0x100'), event('0x100')
    a['instruction'], b['instruction'] = 'nop', 'NOP'
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    assert result['code_difference'] is False
    assert result['presentation_changes'] == [{'baseline_index': 0, 'layer_index': 0}]
    del b['bytes']
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    assert result['code_difference'] is None
    assert any('Code bytes' in reason for reason in result['unknown'])


def test_empty_trace_and_empty_register_projection_cannot_prove_equality():
    assert compare_trace_topology(trace([]), trace([]), same_source=True)['alignment'] == 'unknown'
    a, b = event('0x100'), event('0x100')
    a['registers'] = b['registers'] = {}
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    assert result['observed_register_difference'] is None
    assert any('Empty register' in reason for reason in result['unknown'])


def test_address_spelling_normalizes_but_malformed_identity_stays_unmapped():
    a, b = event('0x0100'), event('0x100')
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    assert result['coverage']['aligned_pairs'] == 1
    b['identity']['context'] = []
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    assert result['alignment'] == 'partial'
    assert result['control_flow_difference'] is None


def test_extra_open_tail_is_not_a_proven_path_or_effect_change():
    shared = [event('0x100'), event('0x101')]
    topology = compare_trace_topology({**trace(shared), 'requested_count': 3},
                                      {**trace(shared + [event('0x102')]), 'requested_count': 3},
                                      same_source=True)
    assert topology['segments'][-1]['kind'] == 'open_tail'
    assert topology['control_flow_difference'] is None
    assert topology['code_difference'] is None
    assert topology['observed_register_difference'] is None
    result = compare_trials(trial(shared), trial(shared + [event('0x102')]), same_source=True)
    assert result['control_flow_difference'] is None
    assert result['observed_effect_difference'] is False


def test_paired_change_is_positive_even_with_unpaired_tail():
    a = [event('0x100', code='90', ax='0x1')]
    b = [event('0x100', code='91', ax='0x2'), event('0x101')]
    result = compare_trace_topology(trace(a), trace(b), same_source=True)
    assert result['code_difference'] is True
    assert result['observed_register_difference'] is True
    assert result['coverage']['all_events_paired'] is False


def test_distinct_observed_tail_sites_are_path_difference():
    a = [event('0x100'), event('0x101')]
    b = [event('0x100'), event('0x105')]
    result = compare_trace_topology(trace(a), trace(b), same_source=True)
    assert result['segments'][-1]['kind'] == 'divergent'
    assert result['control_flow_difference'] is True


def test_obfuscated_detour_can_change_path_without_sampled_effect():
    baseline = [event('0x100'), event('0x101'), event('0x110')]
    detour = [event('0x100'), event('0x105'), event('0x106'), event('0x107'), event('0x110')]
    result = compare_trials(trial(baseline), trial(detour), same_source=True)
    assert result['control_flow_difference'] is True
    assert result['code_difference'] is None  # Unpaired detour code is not compared.
    assert result['observed_difference'] is True
    assert result['observed_effect_difference'] is False
    assert result['traces'][0]['topology']['segments'][1]['rejoin']['registers']['relation'] == 'equal'
    assert result['semantic_equivalence'] is None


def test_trace_stage_mismatch_prevents_effect_verdicts():
    a = [event('0x100')]
    result = compare_trace_topology(trace(a), trace(a, semantics='pre_execution_fetch_last_pending'),
                                    same_source=True)
    assert result['alignment'] == 'unknown'
    assert result['control_flow_difference'] is None
    assert result['observed_register_difference'] is None


def test_partial_register_relation_retains_different_shared_fields():
    a, b = event('0x100'), event('0x100')
    b['registers'] = {'general': {'ax': '0x2'}}
    result = compare_trace_topology(trace([a]), trace([b]), same_source=True)
    relation = result['segments'][0]['entry_registers']
    assert relation['relation'] == 'partial'
    assert relation['different_fields'] == ['general.ax']
    assert result['observed_register_difference'] is True
