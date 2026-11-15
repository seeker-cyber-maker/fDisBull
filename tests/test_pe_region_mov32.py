"""PE64 dword MOV clears the destination's high half without changing FLAGS."""
from copy import deepcopy

import pytest

pytest.importorskip('z3')

from fdisbull.pe_region_equivalence import compare_pe_regions, expand_pe_contraction
from test_pe_region_equivalence import _pair


@pytest.mark.parametrize('value', [0, 2, 0x80000000, 0xffffffff])
@pytest.mark.parametrize('incoming', [0xffffffffffffffff, 0x1234567887654321])
def test_dword_immediate_matches_full_width_constant_and_preserves_state(value, incoming):
    # Independent Unicorn captures start with a nonzero high half. A model that
    # merges the old high half, or sign-extends the immediate, cannot pass.
    short = 'b8' + value.to_bytes(4, 'little').hex()
    wide = '48b8' + value.to_bytes(8, 'little').hex()
    (baseline, _), (layer, _) = _pair(short, wide,
        general={'rax': incoming, 'rbx': 0x8877665544332211}, flags=0x8d7)
    before = deepcopy((baseline, layer))
    assert int(baseline['events'][-1]['registers']['general']['rax'], 16) == value
    assert baseline['events'][-1]['registers']['rflags'] == baseline['events'][0]['registers']['rflags']
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'equivalent_under_contract', result
    expanded = expand_pe_contraction(result['contraction'], baseline, layer)
    assert expanded['baseline'] == baseline and expanded['layer'] == layer
    assert (baseline, layer) == before


@pytest.mark.parametrize('short,wide,destination,source', [
    ('89d8', '4889d8', 'rax', 'rbx'),
    ('89f1', '4889f1', 'rcx', 'rsi'),
    ('4589c8', '4d89c8', 'r8', 'r9'),
    ('4589f7', '4d89f7', 'r15', 'r14'),
    ('89c0', '4889c0', 'rax', 'rax'),
])
def test_dword_register_source_reads_only_low_half(short, wide, destination, source):
    (baseline, _), (layer, _) = _pair(short, wide,
        general={destination: 0xaaaaaaaa55555555, source: 0x1234567887654321}, flags=0xad7)
    assert int(baseline['events'][-1]['registers']['general'][destination], 16) == 0x87654321
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'different', result
    assert destination in result['counterexample']['differing_live_registers']
    # The difference vanishes exactly under a low-half source precondition.
    (baseline, _), (layer, _) = _pair(short, wide,
        general={destination: 0xaaaaaaaa55555555, source: 0x87654321}, flags=0xad7)
    result = compare_pe_regions(baseline, layer, contract={
        'entry_register_ranges': {source: {'min': '0x0', 'max': '0xffffffff'}}}, same_source=True)
    assert result['status'] == 'equivalent_under_contract', result


def test_changed_constant_has_a_live_rax_witness_and_contract_can_exclude_it():
    (baseline, _), (layer, _) = _pair('b801000000', 'b802000000',
        general={'rax': 0xfacefeeddeadbeef}, flags=0x8d7)
    result = compare_pe_regions(baseline, layer, contract={}, same_source=True)
    assert result['status'] == 'different', result
    assert result['counterexample']['differing_live_registers'] == {
        'rax': {'baseline': '0x1', 'layer': '0x2'}}
    assert result['counterexample']['masked_flags']['baseline'] == result['counterexample']['masked_flags']['layer']
    assert compare_pe_regions(baseline, layer, contract={'live_registers': []},
                              same_source=True)['status'] == 'equivalent_under_contract'


@pytest.mark.parametrize('corruption', ['high_half', 'other_register', 'flags'])
def test_observed_transition_checks_still_reject_contradictory_evidence(corruption):
    (trace, _), _ = _pair('b802000000', 'b802000000',
        general={'rax': 0x1234567887654321}, flags=0x8d7)
    bad = deepcopy(trace)
    following = bad['events'][1]['registers']
    if corruption == 'high_half':
        following['general']['rax'] = '0x1234567800000002'
    elif corruption == 'other_register':
        following['general']['rbx'] = '0x1'
    else:
        following['rflags'] = hex(int(following['rflags'], 16) ^ 0x40)
    result = compare_pe_regions(bad, trace, contract={}, same_source=True)
    assert result['status'] == 'unknown', result
    assert 'contradict' in result['reason'] and 'regional model' in result['reason']


@pytest.mark.parametrize('code', [
    'b002',              # MOV AL,2: byte alias remains unsupported.
    '66b80200',          # MOV AX,2: word alias/legacy prefix remains unsupported.
    '83c001',            # ADD EAX,1: dword arithmetic is outside this extension.
    '8b00',              # MOV EAX,[RAX]: dword loads are not silently admitted.
])
def test_partial_alias_arithmetic_and_memory_loads_remain_unknown(code):
    # Point the load at mapped ordinary RAM so this is a model-scope rejection,
    # rather than a Unicorn execution failure.
    (trace, _), _ = _pair(code, code, general={'rax': 0x3000}, memory=bytes(8))
    result = compare_pe_regions(trace, trace, contract={}, same_source=True)
    assert result['status'] == 'unknown', result
    assert result.get('contraction') is None
