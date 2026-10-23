"""Function candidates have many-to-many, context-sensitive CFG membership."""
import pytest

from fdisbull.decoder import decode
from fdisbull.function_analysis import function_membership


def native(address, raw, arch='x86', bits=64, context=None):
    node = decode(bytes.fromhex(raw), address, arch, bits)
    assert node is not None
    return dict(node, id=f'{context or arch}@{address:x}', context=context or arch,
                next_address=address + node['size'])


def edge(source, target, kind='branch'):
    return dict(source=source['id'], target=target['id'], kind=kind, evidence='native direct CFG fact')


def function(result, entry):
    return next(item for item in result['functions'] if item['entry'] == entry['id'])


def test_native_x86_distinct_entries_share_a_tail_without_exclusive_ownership():
    first = native(0x1000, 'eb0e')
    second = native(0x1004, 'eb0a')
    tail = native(0x1010, 'b801000000')
    end = native(0x1015, 'c3')
    result = function_membership([first, second, tail, end],
                                 [edge(first, tail), edge(second, tail), edge(tail, end, 'fallthrough')],
                                 [first['id'], second['id'], {'id': tail['id'], 'source': 'symbol', 'name': 'shared'}])
    assert result['complete'] and result['status'] == 'candidate'
    assert result['function_boundary_proven'] is False
    assert function(result, first)['instruction_ids'] == [first['id'], tail['id'], end['id']]
    assert function(result, second)['instruction_ids'] == [second['id'], tail['id'], end['id']]
    shared = next(item for item in result['shared_tails'] if tail['id'] in item['instruction_ids'])
    assert set(shared['candidate_entries']) == {first['id'], second['id'], tail['id']}
    overlap = next(item for item in result['overlapping_entries'] if item['entry'] == tail['id'])
    assert set(overlap['reachable_from']) == {first['id'], second['id']}
    assert {item['source'] for item in result['tail_call_candidates']} == {first['id'], second['id']}
    assert all(item['ownership_traversal_continues'] for item in result['tail_call_candidates'])


def test_entry_inside_a_straight_line_is_an_explicit_overlapping_entry():
    first, middle, end = native(0x1000, '90'), native(0x1001, '90'), native(0x1002, 'c3')
    result = function_membership([first, middle, end],
                                 [edge(first, middle, 'fallthrough'), edge(middle, end, 'fallthrough')],
                                 [first['id'], middle['id']])
    assert len(result['basic_blocks']) == 2
    assert function(result, first)['instruction_count'] == 3
    assert function(result, middle)['instruction_count'] == 2
    assert function(result, first)['overlapping_entries'] == [middle['id']]
    assert result['overlapping_entries'][0]['entry'] == middle['id']
    membership = next(item for item in result['instruction_membership'] if item['instruction'] == middle['id'])
    assert membership['candidate_entries'] == [first['id'], middle['id']]


def test_call_target_is_excluded_but_call_continuation_is_followed():
    call, end, callee = native(0x1000, 'e81b000000'), native(0x1005, 'c3'), native(0x1020, 'c3')
    result = function_membership([call, end, callee],
                                 [edge(call, callee, 'call'), edge(call, end, 'fallthrough')],
                                 [call['id'], callee['id']])
    assert function(result, call)['instruction_ids'] == [call['id'], end['id']]
    assert function(result, callee)['instruction_ids'] == [callee['id']]
    assert len(result['excluded_call_edges']) == 1
    assert result['shared_tails'] == [] and result['complete']


def test_context_aliases_require_an_exact_entry_and_remain_distinct():
    near = native(0x10040, 'c3', bits=16, context='x86:16:little:cs=1004')
    alias = native(0x10040, 'c3', bits=16, context='x86:16:little:cs=1003')
    result = function_membership([near, alias], [],
                                 [{'address': '0x10040'}, {'address': 0x10040, 'context': near['context']}])
    assert result['resolved_entry_count'] == 1
    assert result['unresolved'][0]['reason'] == 'ambiguous_entry_context'
    assert set(result['unresolved'][0]['candidates']) == {near['id'], alias['id']}
    assert result['functions'][0]['instruction_ids'] == [near['id']]
    assert next(item for item in result['instruction_membership'] if item['id'] == alias['id'])['candidate_entries'] == []


def test_native_arm64_noncontiguous_runs_do_not_absorb_intervening_bytes():
    first, other, end = native(0x1000, '08000014', 'arm64'), native(0x1004, 'c0035fd6', 'arm64'), native(0x1020, 'c0035fd6', 'arm64')
    result = function_membership([first, other, end], [edge(first, end)], [first['id']])
    routine = function(result, first)
    assert routine['instruction_ids'] == [first['id'], end['id']]
    assert [(run['start'], run['end']) for run in routine['runs']] == [('0x1000', '0x1004'), ('0x1020', '0x1024')]
    assert result['complete'] and routine['complete']


def test_loop_is_deduplicated_and_budget_stop_retains_an_explicit_frontier():
    first, branch, end = native(0x1000, '90'), native(0x1001, '75fd'), native(0x1003, 'c3')
    edges = [edge(first, branch, 'fallthrough'), edge(branch, first), edge(branch, end, 'fallthrough')]
    complete = function_membership([first, branch, end], edges, [first['id']])
    assert complete['work'] == 3 and complete['complete']
    partial = function_membership([first, branch, end], edges, [first['id']], max_work=1)
    assert partial['work'] == 1 and partial['budget_exhausted'] and not partial['complete']
    assert partial['frontier'] == [dict(entry=first['id'], source=None, target=branch['id'], reason='work_budget')]
    assert not function(partial, first)['complete']


def test_budget_cut_inside_block_does_not_claim_unvisited_instructions_are_shared():
    first, second = native(0x1000, 'eb0e'), native(0x1004, 'eb0a')
    tail, middle, end = native(0x1010, '90'), native(0x1011, '90'), native(0x1012, 'c3')
    result = function_membership([first, second, tail, middle, end],
                                 [edge(first, tail), edge(second, tail), edge(tail, middle, 'fallthrough'), edge(middle, end, 'fallthrough')],
                                 [first['id'], second['id']], max_work=5)
    assert result['budget_exhausted']
    shared = result['shared_tails'][0]
    assert shared['instruction_ids'] == [tail['id']]
    assert shared['partial_membership']
    assert set(shared['instruction_membership'][0]['candidate_entries']) == {first['id'], second['id']}
    assert not next(item for item in result['instruction_membership'] if item['id'] == end['id'])['candidate_entries']


def test_missing_facts_and_unknown_indirect_flow_are_not_called_complete():
    indirect = native(0x1000, '00001fd6', 'arm64')  # BR X0
    result = function_membership([indirect], [], [indirect['id']])
    assert result['unresolved'][0]['reason'] == 'no_stored_branch_target'
    assert not result['complete'] and not result['budget_exhausted']
    jump = native(0x2000, 'eb00')
    missing = dict(source=jump['id'], target='missing@2002', kind='branch')
    result = function_membership([jump], [missing], [jump['id'], {'address': '0x9999'}])
    assert result['frontier'][0]['reason'] == 'no_stored_instruction_at_target'
    assert result['unresolved'][0]['reason'] == 'entry_not_stored'
    assert not function(result, jump)['complete']
    ordinary = native(0x3000, '90')
    assert function_membership([ordinary], [], [ordinary['id']])['unresolved'][0]['reason'] == 'no_stored_fallthrough'


def test_validation_and_non_control_references_do_not_change_membership():
    end = native(0x1000, 'c3')
    result = function_membership([end], [dict(source=end['id'], target='data', kind='data')], [end['id']])
    assert result['excluded_non_flow_edge_count'] == 1 and result['complete']
    for budget in (True, 0, 20_000_001):
        with pytest.raises(ValueError, match='max_work'):
            function_membership([end], [], [end['id']], max_work=budget)
    with pytest.raises(ValueError, match='unique'):
        function_membership([end, end], [], [end['id']])
    with pytest.raises(ValueError, match='at most 100000'):
        function_membership([{}] * 100001, [], [])
