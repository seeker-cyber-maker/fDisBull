"""Authored instruction witnesses for bounded execution-event searches."""
from copy import deepcopy
import hashlib

import pytest

from fdisbull.execution_events import (
    evaluate_predicate, normalize_trace, refine_search, search_results,
    start_search, validate_predicate, validate_regions, validate_search,
)


def trace(events=None, *, run='run-a', backend='dosbox', complete=True):
    events = events if events is not None else [event()]
    return {'version': 1, 'run': {'run': run},
            'mapping': {'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64,
                        'runtime_load_segment': 0x800, 'static_load_segment': 0x1000},
            'observation_contract': {'backend': backend, 'trace_registers_stage': 'before-instruction'},
            'events': events, 'complete': complete, 'requested_count': len(events)}


def event(pc=0x100, *, sequence=1, code='90', regs=None, **extra):
    return {'address': {'space': 'segmented', 'segment': '0x800', 'offset': hex(pc)},
            'project_address': hex(0x10000 + pc), 'cpu_mode': 'real', 'code_bits': 16,
            'execution_bytes': code, 'sequence': sequence,
            'register_changes': {'eax': 1, 'ebx': 0x12345678} if regs is None else regs,
            'observation': {'registers_stage': 'before-instruction', 'instruction_completed': None,
                            'evidence': 'native fetch'}, **extra}


def compiled(events=None, **kwargs):
    document = trace(events, **kwargs)
    result = normalize_trace(document)
    result['artifact'] = {'id': 'artifact-' + result['run'], 'sha256': 'c' * 64}
    return result


def test_native_style_sparse_deltas_and_exact_instruction_identity():
    values = normalize_trace(trace([
        event(code='4090ebfa', regs={'eax': 1, 'ebx': 0x12345678}),
        event(0x101, sequence=2, code='90ebfa', regs={'eax': 2}),
        event(0x102, sequence=3, code='ebfa', regs={}),
    ]))
    first, second, third = values['events']
    assert (first['mnemonic'], first['size']) == ('inc', 1)
    assert first['instruction_sha256'] == hashlib.sha256(bytes.fromhex('40')).hexdigest()
    assert second['registers']['ebx'] == 0x12345678
    assert third['registers']['eax'] == 2
    assert third['site']['address'] == 0x10102
    assert values['window']['closed'] is True
    assert 'execution_bytes' not in first and 'bytes' not in first


def test_gap_does_not_carry_registers_or_close_window():
    value = normalize_trace(trace([event(), event(0x101, sequence=3, regs={})]))
    assert 'eax' not in value['events'][1]['registers']
    assert value['window']['closed'] is False
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'equals': 0},
                              value['events'][1])['matched'] is None


@pytest.mark.parametrize('mode', ['protected', 'v86', None])
def test_unqualified_dos_modes_do_not_invent_source_projection(mode):
    value = normalize_trace(trace([event(cpu_mode=mode, code_bits=32)]))
    assert value['events'][0]['site'] is None
    assert value['events'][0]['pc']['project'] is None
    assert value['unqualified_events'] == 1


def test_runtime_predicates_work_without_project_projection():
    e = normalize_trace(trace([event(cpu_mode='v86')]))['events'][0]
    assert evaluate_predicate({'kind': 'pc-range', 'space': 'segmented', 'segment': 0x800,
                               'start': 0x100, 'end': 0x101}, e)['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'ax', 'equals': 1}, e)['matched'] is True


def test_mnemonic_uses_prefix_safe_live_decode_not_claimed_text():
    e = normalize_trace(trace([event(code='f3a490', instruction='push ax')]))['events'][0]
    assert (e['mnemonic'], e['size']) == ('movsb', 2)
    assert evaluate_predicate({'kind': 'mnemonic', 'equals': 'MOVSB'}, e)['matched'] is True


def test_alias_width_and_partial_update_do_not_invent_upper_bits():
    values = normalize_trace(trace([
        event(regs={'eax': 0x12345678}),
        event(0x101, sequence=2, regs={'ax': 0xabcd}),
    ]))['events']
    assert evaluate_predicate({'kind': 'register', 'register': 'ah', 'equals': 0x56}, values[0])['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'al', 'equals': 0x78}, values[0])['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'equals': 0xabcd}, values[1])['matched'] is None
    assert evaluate_predicate({'kind': 'register', 'register': 'ax', 'equals': 0xabcd}, values[1])['matched'] is True
    with pytest.raises(ValueError):
        validate_predicate({'kind': 'register', 'register': 'al', 'equals': 256})


def test_any_register_and_three_valued_boolean_predicates():
    e = normalize_trace(trace())['events'][0]
    assert evaluate_predicate({'kind': 'any-register', 'registers': ['eax', 'ebx'], 'equals': 1}, e)['matched'] is True
    unknown = {'kind': 'register', 'register': 'ecx', 'equals': 0}
    yes = {'kind': 'register', 'register': 'eax', 'equals': 1}
    no = {'kind': 'register', 'register': 'eax', 'equals': 2}
    assert evaluate_predicate({'any': [unknown, yes]}, e)['matched'] is True
    assert evaluate_predicate({'all': [unknown, no]}, e)['matched'] is False
    assert evaluate_predicate({'all': [unknown, yes]}, e)['matched'] is None
    assert evaluate_predicate({'kind': 'register', 'register': 'ebx', 'equals': 0x78, 'mask': 0xff}, e)['matched'] is True


def test_regions_use_bounds_and_identity_not_display_name():
    regions = [{'id': 'a', 'name': 'same', 'space': 'project', 'start': '0x10100', 'end': '0x10101'},
               {'id': 'b', 'name': 'same', 'space': 'project', 'start': '0x10101', 'end': '0x10200'}]
    values = normalize_trace(trace([event(), event(0x101, sequence=2)]), regions=regions)['events']
    assert evaluate_predicate({'kind': 'region-change'}, values[1], initial=values[0])['matched'] is True
    renamed = deepcopy(values[0]); renamed['region']['name'] = 'other'
    assert evaluate_predicate({'kind': 'region-change'}, renamed, initial=values[0])['matched'] is False
    assert evaluate_predicate({'kind': 'region-change'}, values[0])['matched'] is None
    with pytest.raises(ValueError, match='overlap'):
        validate_regions([regions[0], dict(regions[1], start=0x10100)])


def test_nonsequential_is_observed_fallthrough_not_instruction_kind():
    values = normalize_trace(trace([event(code='7402'), event(0x102, sequence=2),
                                    event(0x110, sequence=3)]))['events']
    p = {'kind': 'nonsequential'}
    assert evaluate_predicate(p, values[0])['matched'] is None
    assert evaluate_predicate(p, values[1], previous=values[0])['matched'] is False
    assert evaluate_predicate(p, values[2], previous=values[1])['matched'] is True
    gap = deepcopy(values[2]); gap['sequence'] = 8
    assert evaluate_predicate(p, gap, previous=values[1])['matched'] is None


def test_fallthrough_wrap_cs_changes_and_thread_changes_are_distinct():
    wrap = normalize_trace(trace([event(0xffff), event(0, sequence=2)]))['events']
    assert evaluate_predicate({'kind': 'nonsequential'}, wrap[1], previous=wrap[0])['matched'] is False
    other_cs = event(0x101, sequence=2, address={'space': 'segmented', 'segment': '0x801', 'offset': '0x101'},
                     project_address='0x10111')
    far = normalize_trace(trace([event(), other_cs]))['events']
    assert evaluate_predicate({'kind': 'nonsequential'}, far[1], previous=far[0])['matched'] is True
    changed = normalize_trace(trace([event(thread=1), event(0x110, sequence=2, thread=2, regs={})]))['events']
    assert 'eax' not in changed[1]['registers']
    assert evaluate_predicate({'kind': 'nonsequential'}, changed[1], previous=changed[0])['matched'] is None


def test_runtime_pc_register_is_fresh_and_full_eip_preserves_ip_alias():
    value = normalize_trace(trace([event(regs={'instruction_pointer': 0x100}),
                                   event(0x102, sequence=2, regs={})]))['events']
    assert value[1]['registers']['eip'] == 0x102
    assert evaluate_predicate({'kind': 'register', 'register': 'ip', 'equals': 0x102}, value[1])['matched'] is True
    bad = trace([event(regs={'instruction_pointer': 0x200})])
    with pytest.raises(ValueError, match='pointer'):
        normalize_trace(bad)


def test_phase_change_cannot_inherit_registers_from_an_after_state():
    after = event(regs={'eax': 7}, observation={'registers_stage': 'after-instruction'})
    value = normalize_trace(trace([after, event(0x101, sequence=2, regs={})]))['events']
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'equals': 7}, value[0])['matched'] is None
    assert 'eax' not in value[1]['registers']


@pytest.mark.parametrize('location', ['full', 'top', 'delta'])
def test_observed_page_table_change_is_not_sequential_flow(location):
    raw = []
    for index, cr3 in enumerate((0x1000, 0x2000)):
        item = event(0x100 + index, sequence=index + 1, cpu_mode='protected', code_bits=32,
                     project_address=None, regs={'eax': 7} if index == 0 else {})
        context = {'cpu_mode': 'protected', 'code_bits': 32, 'paging_enabled': True, 'cr3': hex(cr3)}
        if location == 'full':
            item.pop('register_changes')
            item['registers'] = {'general': {'eax': 7}, 'address_context': context}
        elif location == 'top':
            item['address_context'] = context
        else:
            item['register_changes']['cr3'] = cr3
        raw.append(item)
    first, second = normalize_trace(trace(raw))['events']
    assert first['registers']['cr3'] == 0x1000
    assert second['registers']['cr3'] == 0x2000
    assert first['execution_context'] != second['execution_context']
    result = evaluate_predicate({'kind': 'nonsequential'}, second, previous=first)
    assert result['matched'] is None and result['unknown']
    if location != 'full':
        assert 'eax' not in second['registers']


def test_unchanged_sparse_mapping_register_remains_known_without_false_context_change():
    raw = [event(regs={'eax': 7, 'cr3': 0x1000}), event(0x101, sequence=2, regs={})]
    first, second = normalize_trace(trace(raw))['events']
    assert first['execution_context'] == second['execution_context']
    assert second['registers']['eax'] == 7 and second['registers']['cr3'] == 0x1000
    assert evaluate_predicate({'kind': 'nonsequential'}, second, previous=first)['matched'] is False


def test_historical_dos_lazy_flags_are_unknown_even_when_seed_and_delta_look_complete():
    raw = [event(code='f7c30100', regs={'ebx': 1, 'flags': 0x7246}),
           event(0x104, sequence=2, regs={})]
    values = normalize_trace(trace(raw))['events']
    for value in values:
        for name in ('flags', 'eflags', 'rflags'):
            assert evaluate_predicate({'kind': 'register', 'register': name, 'equals': 0x7246}, value)['matched'] is None
        assert evaluate_predicate({'kind': 'register', 'register': 'bx', 'equals': 1}, value)['matched'] is True


def test_materialized_dos_stop_flags_are_qualified_but_do_not_leak_into_later_sparse_fetch():
    observed = {'registers_stage': 'before-instruction', 'instruction_completed': False,
                'evidence': 'stopped boundary snapshot', 'flags_materialized': True}
    raw = [event(regs={'flags': 0x7202}, observation=observed),
           event(0x101, sequence=2, regs={})]
    first, historical = normalize_trace(trace(raw))['events']
    assert evaluate_predicate({'kind': 'register', 'register': 'flags', 'equals': 0x7202}, first)['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'eflags', 'equals': 0x7202}, first)['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'flags', 'equals': 0x7202}, historical)['matched'] is None
    assert first['observation']['flags_materialized'] is True


def test_pe_full_flags_remain_available_without_dos_materialization_marker():
    raw = {'address': '0x180001000', 'project_address': '0x140001000', 'bytes': '90',
           'registers': {'bits': 64, 'rip': '0x180001000', 'rflags': '0x202', 'general': {'rax': 1}},
           'observation': {'registers_stage': 'before-instruction', 'instruction_completed': True}}
    value = normalize_trace(trace([raw], backend='wine-qemu'))['events'][0]
    assert evaluate_predicate({'kind': 'register', 'register': 'rflags', 'equals': 0x202}, value)['matched'] is True


def test_rewritten_instruction_at_same_pc_is_a_different_candidate():
    original = start_search(compiled([event(code='90')]))
    rewritten = compiled([event(code='40')], run='rewritten')
    assert refine_search(original, rewritten, mode='retain')['candidate_count'] == 0
    assert refine_search(original, rewritten, mode='exclude')['candidate_count'] == 1


def test_identical_instruction_lookahead_changes_do_not_split_site():
    a = compiled([event(code='9090')])
    b = compiled([event(code='90cc')], run='changed-lookahead')
    assert a['events'][0]['site'] == b['events'][0]['site']
    assert refine_search(start_search(a), b)['candidate_count'] == 1


def test_pe_full_register_snapshot_and_cross_run_source_site_identity():
    def pe(runtime, run):
        raw = {'address': hex(runtime), 'project_address': '0x140001000', 'bytes': '90',
               'registers': {'bits': 64, 'rip': hex(runtime), 'thread': 3,
                             'general': {'rax': '0x1234567800000001'}},
               'observation': {'registers_stage': 'before-instruction', 'instruction_completed': True}}
        result = trace([raw], run=run, backend='ida-wine-qemu')
        result['mapping'] = {'source_sha256': 'a'*64, 'version_sha256': 'b'*64,
                             'static_image_base': '0x140000000', 'runtime_image_base': hex(runtime-0x1000)}
        return normalize_trace(result)
    a, b = pe(0x180001000, 'a'), pe(0x190001000, 'b')
    assert a['events'][0]['site'] == b['events'][0]['site']
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'equals': 1}, a['events'][0])['matched'] is True


def test_same_handler_different_register_value_survives_control_subtraction():
    a = compiled([event(regs={'eax': 1})])
    b = compiled([event(regs={'eax': 2})], run='run-b')
    sites = refine_search(start_search(a), b, mode='exclude')
    assert search_results(sites)['count'] == 0
    state = start_search(a, feature='register-value', registers=['eax'])
    narrowed = refine_search(state, b, mode='exclude', label='click-B')
    rows = search_results(narrowed)['rows']
    assert len(rows) == 1 and rows[0]['register'] == 'eax' and rows[0]['value'] == 1
    assert validate_search(narrowed) == narrowed
    assert state['candidate_count'] == 1 and len(state['history']) == 1


def test_control_loops_do_not_align_event_ordinals_and_refinement_is_monotonic():
    a = compiled([event(), event(0x101, sequence=2), event(0x102, sequence=3)])
    b = compiled([event(), event(sequence=2), event(0x102, sequence=3)], run='run-b')
    state = start_search(a)
    narrowed = refine_search(state, b, mode='retain')
    assert {r['site']['address'] for r in search_results(narrowed)['rows']} == {0x10100, 0x10102}
    restored = refine_search(narrowed, a, mode='retain')
    assert restored['candidate_count'] == 2
    assert state['candidate_count'] == 3


def test_search_state_has_evidence_refs_but_no_instruction_bytes():
    state = start_search(compiled(), label='click-A')
    assert state['history'][0]['artifact']['id'] == 'artifact-run-a'
    assert state['samples'][0]['index'] == 0
    assert state['samples'][0]['artifact']['sha256'] == 'c'*64
    assert 'bytes' not in state['candidates'][0]
    tampered = deepcopy(state); tampered['candidate_count'] = 0
    with pytest.raises(ValueError):
        validate_search(tampered)


def test_paginated_results_return_only_witnesses_used_by_that_page():
    state = start_search(compiled([event(), event(0x101, sequence=2), event(0x102, sequence=3)]))
    page = search_results(state, offset=1, limit=1)
    assert page['candidate_count'] == page['count'] == page['total'] == 3
    assert page['returned_count'] == 1
    assert len(page['samples']) == 1
    assert page['samples'][0]['sample_index'] == page['rows'][0]['samples'][0]
    assert page['next_offset'] == 2
    assert search_results(state, offset=3, limit=1)['samples'] == []


def test_candidate_sample_history_and_result_limits_are_hard_errors(monkeypatch):
    import fdisbull.execution_events as module
    values = compiled([event(), event(0x101, sequence=2), event(0x102, sequence=3)])
    monkeypatch.setattr(module, 'MAX_CANDIDATES', 2)
    with pytest.raises(ValueError, match='candidate budget'):
        start_search(values)
    monkeypatch.setattr(module, 'MAX_CANDIDATES', 32768)
    monkeypatch.setattr(module, 'MAX_SAMPLES', 2)
    with pytest.raises(ValueError, match='sample budget'):
        start_search(values)
    monkeypatch.setattr(module, 'MAX_SAMPLES', 10000)
    state = start_search(compiled())
    monkeypatch.setattr(module, 'MAX_HISTORY', 1)
    with pytest.raises(ValueError, match='history budget'):
        refine_search(state, compiled())
    with pytest.raises(ValueError):
        search_results(state, limit=4097)


def test_predicate_depth_budget_and_mask_comparisons():
    value = {'kind': 'region-change'}
    for _ in range(8):
        value = {'all': [value]}
    with pytest.raises(ValueError, match='depth'):
        validate_predicate(value)
    e = compiled([event(regs={'eax': 0x80000001})])['events'][0]
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'gt': 0x7fffffff}, e)['matched'] is True
    assert evaluate_predicate({'kind': 'register', 'register': 'eax', 'not_equals': 0, 'mask': 1}, e)['matched'] is True


def test_register_filtered_search_preserves_shared_site_and_unknowns():
    values = compiled([event(regs={'eax': 1}), event(sequence=2, regs={'eax': 2}),
                       event(sequence=3, regs={'eax': 1})])
    state = start_search(values, predicate={'kind': 'register', 'register': 'eax', 'equals': 1})
    assert state['candidates'][0]['hit_count'] == 2
    assert state['candidate_count'] == 1
    unknown = start_search(values, feature='register-value', registers=['ecx'])
    assert unknown['candidate_count'] == 0
    assert unknown['history'][0]['unknown_observations'] == 3


def test_duplicate_sequence_and_conflicting_register_aliases_are_rejected():
    with pytest.raises(ValueError, match='sequence'):
        normalize_trace(trace([event(), event(sequence=1)]))
    with pytest.raises(ValueError, match='aliases'):
        normalize_trace(trace([event(regs={'eax': 1, 'ax': 2})]))
    with pytest.raises(ValueError, match='duplicate'):
        normalize_trace(trace([event(regs={'eax': 1, 'EAX': 2})]))


@pytest.mark.parametrize('identity', [
    {'source_version': 2}, {'project_address': '0x10101'},
    {'runtime_address': {'space': 'segmented', 'segment': '0x800', 'offset': '0x102'}},
    {'context': 'real:1001'},
])
def test_contradictory_event_identity_cannot_qualify_a_source_site(identity):
    with pytest.raises(ValueError):
        normalize_trace(trace([event(identity=identity)]))


def test_incomplete_windows_and_identity_mismatch_are_refused():
    with pytest.raises(ValueError, match='closed'):
        start_search(compiled(complete=False))
    a = compiled(); state = start_search(a)
    b = deepcopy(a); b['identity']['source_sha256'] = 'd'*64
    with pytest.raises(ValueError, match='identity'):
        refine_search(state, b, mode='retain')
    document = trace(complete=False); document['window'] = {'closed': True, 'reason': 'predicate'}
    assert normalize_trace(document)['window']['closed'] is True


@pytest.mark.parametrize('mutation', [
    lambda d: d['mapping'].update(source_sha256='bad'),
    lambda d: d.update(version=True),
    lambda d: d['events'][0].update(register_changes={'eax': -1}),
    lambda d: d['events'][0].update(register_changes={'eax': 'not-hex'}),
    lambda d: d['events'][0].update(sequence=True),
])
def test_malformed_trace_inputs_are_rejected(mutation):
    value = trace(); mutation(value)
    with pytest.raises(ValueError):
        normalize_trace(value)


@pytest.mark.parametrize('value', [
    {'kind': 'register', 'register': 'eax', 'equals': True},
    {'kind': 'register', 'register': 'invalid', 'equals': 1},
    {'kind': 'register', 'register': 'eax', 'equals': 1, 'gt': 2},
    {'kind': 'any-register', 'registers': [], 'equals': 0},
    {'kind': 'pc-range', 'space': 'linear', 'start': 3, 'end': 3},
    {'kind': 'pc-range', 'space': 'segmented', 'start': 1, 'end': 2},
    {'kind': 'mnemonic', 'equals': 'rep movsb'},
    {'any': []}, {'all': [{'kind': 'region-change'}] * 65},
])
def test_predicate_schema_rejects_ambiguous_or_unbounded_inputs(value):
    with pytest.raises(ValueError):
        validate_predicate(value)
