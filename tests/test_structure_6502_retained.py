"""Authored fixtures only. No original game byte sequences are embedded."""
import pytest
from fdisbull.structure_6502 import probe
from fdisbull.structure_patterns import match_graph, RULES
from fdisbull.structure_events import SELECTOR_RULE


def run(code, *, entries=None, base=0x8000, mapping='authored', budget=200):
    return probe(bytes(code),[{'cpu_start':base,'file_start':0,'size':len(code)}],
                 entries or [base],mapping_id=mapping,budget=budget)


def matches(d, pat):
    return [x for x in match_graph(d['nodes'],d['edges'],rules=(*RULES,SELECTOR_RULE))['matches'] if x['pattern']==pat]


def test_mask_branch():
    d=run([0xa5,0x12,0x29,0x04,0xf0,1,0xea,0x60])
    assert len(matches(d,'loaded-mask-controls-branch'))==1


def test_changed_flags_refused():
    d=run([0xa5,0x12,0x29,0x04,0xe8,0xf0,1,0xea,0x60])
    assert matches(d,'loaded-mask-controls-branch')==[]


def test_no_cross_call_mask_propagation():
    d=run([0xa5,0x12,0x20,0x0b,0x80,0x29,0x04,0xf0,1,0xea,0x60,0x60])
    assert matches(d,'loaded-mask-controls-branch')==[]


def test_selector_branches_bind_opposite_relations():
    d=run([0xc9,3,0xf0,3,0x85,0x10,0x60,0x85,0x11,0x60])
    ms=matches(d,'selector-controls-operation')
    assert len(ms)==2
    assert {m['bindings']['effect']['selector_relation'] for m in ms}=={'equal','not_equal'}


def test_selector_bne_polarity():
    d=run([0xc9,3,0xd0,3,0x85,0x10,0x60,0x85,0x11,0x60])
    ms=matches(d,'selector-controls-operation')
    assert next(m for m in ms if m['bindings']['effect']['evidence']['cpu_address']==0x8004)['bindings']['effect']['selector_relation']=='equal'


def test_register_only_not_state_effect():
    d=run([0xc9,3,0xf0,3,0xa9,5,0x60,0xa2,9,0x60])
    assert all(m['bindings']['effect']['operation']=='return' for m in matches(d,'selector-controls-operation'))


def test_calls_are_effect_boundaries():
    d=run([0xc9,3,0xd0,4,0x20,0x0a,0x80,0x60,0x60,0xea,0x85,0x10,0x60])
    assert any(m['bindings']['effect']['operation']=='call' for m in matches(d,'selector-controls-operation'))


def test_mapper_write_stops():
    d=run([0xa9,1,0x8d,0x00,0x80,0xc9,3,0xf0,1,0x60,0x60])
    assert d['decoded_candidate_instructions']==2
    assert any('mapper' in e['reason'] for e in d['issues'])


def test_indirect_write_stops():
    d=run([0x91,0x12,0xa9,0,0x60])
    assert d['decoded_candidate_instructions']==1
    assert any('mapper' in e['reason'] for e in d['issues'])


def test_indirect_jump_unresolved():
    d=run([0x6c,0x12,0x00,0x60])
    assert d['decoded_candidate_instructions']==1
    assert d['issues'][0]['reason']=='indirect jump unresolved'


def test_join_rejected():
    d=run([0xc9,3,0xd0,3,0x85,0x10,0x60,0x85,0x11,0x60],entries=[0x8000,0x8004])
    ms=matches(d,'selector-controls-operation')
    assert len(ms)==1 and ms[0]['bindings']['effect']['evidence']['cpu_address']==0x8007


def test_mapping_identity_separates_matches():
    data=[0xc9,3,0xf0,1,0x60,0x60]
    a=matches(run(data,mapping='first'),'selector-controls-operation')
    b=matches(run(data,mapping='second'),'selector-controls-operation')
    assert {x['id'] for x in a}.isdisjoint(x['id'] for x in b)


def test_bounded_decode():
    d=run([0xea]*25+[0x60],budget=3)
    assert d['instruction_budget_exhausted'] and d['decoded_candidate_instructions']==3


def test_deterministic():
    code=[0xc9,3,0xf0,1,0x60,0x60]
    assert run(code)==run(code)


def test_unknown_role_never_infers_scene():
    ms=matches(run([0xc9,3,0xf0,1,0x60,0x60]),'selector-controls-operation')
    assert all(not m['runtime_observed'] and not m['execution_authorized'] for m in ms)


@pytest.mark.parametrize('windows',[
 [],[{'cpu_start':0x10000,'file_start':0,'size':1}],
 [{'cpu_start':0x8000,'file_start':10,'size':1}],
 [{'cpu_start':0x8000,'file_start':0,'size':-1}],
 [{'cpu_start':0x8000,'file_start':0,'size':1},{'cpu_start':0x8000,'file_start':0,'size':1}],
])
def test_invalid_maps(windows):
    with pytest.raises(ValueError):probe(b'\x60',windows,[0x8000],mapping_id='authored')
