import pytest
from fdisbull.influence_pilot import InfluenceError, analyze_linear_influence, projected_equal


def doc(steps, sinks=('control.pc',)):
    return {'format':'fdisbull-influence-pilot-1','scope':'linear',
            'steps':steps, 'observables':list(sinks),
            'closed_semantics':True,'closed_observers':True}


def instruction(name, reads=(), deps=None):
    deps = deps or {}
    return {'id':name,'reads':list(reads),'writes':list(deps),
            'dependencies':{k:list(v) for k,v in deps.items()}}


def test_cmp_jz_only_zf_is_relevant():
    steps=[instruction('cmp',('reg.ax','reg.bx'),{
        flag:['reg.ax','reg.bx'] for flag in ('flag.zf','flag.cf','flag.sf','flag.of')}),
        instruction('jz',('flag.zf',),{'control.pc':['flag.zf']})]
    result=analyze_linear_influence(doc(steps))
    assert result['required_entry']==['reg.ax','reg.bx']
    cmp=result['contracts'][0]
    assert cmp['produced_live']==['flag.zf']
    assert cmp['dead_written_candidates']==['flag.cf','flag.of','flag.sf']
    assert projected_equal({'control.pc':10,'flag.cf':0},{'control.pc':10,'flag.cf':1},['control.pc'])
    assert not projected_equal({'control.pc':10},{'control.pc':11},['control.pc'])
    assert len(result['relevant_edges']) == 3


def test_inc_does_not_kill_carry_before_jc():
    steps=[instruction('cmp',('reg.ax','reg.bx'),{
         'flag.cf':['reg.ax','reg.bx'],'flag.zf':['reg.ax','reg.bx']}),
         instruction('inc',('reg.cx',),{'reg.cx':['reg.cx'],'flag.zf':['reg.cx']}),
         instruction('jc',('flag.cf',),{'control.pc':['flag.cf']})]
    result=analyze_linear_influence(doc(steps))
    assert result['required_entry']==['reg.ax','reg.bx']
    assert result['contracts'][0]['produced_live']==['flag.cf']
    assert result['contracts'][1]['dead_written_candidates']==['flag.zf','reg.cx']


def test_last_writer_kills_prior_dependency():
    steps=[instruction('cmp',('reg.ax','reg.bx'),{'flag.zf':['reg.ax','reg.bx']}),
           instruction('clear',(),{'flag.zf':[]}),
           instruction('jz',('flag.zf',),{'control.pc':['flag.zf']})]
    result=analyze_linear_influence(doc(steps))
    assert result['required_entry']==[]
    assert result['contracts'][0]['dead_written_candidates']==['flag.zf']


def test_unknown_observer_or_partial_semantics_never_implies_dead():
    p=doc([instruction('cmp',('reg.ax',),{'flag.zf':['reg.ax']})])
    for key in ('closed_semantics','closed_observers'):
        q=dict(p);q[key]=False
        with pytest.raises(InfluenceError,match='Unknown'):analyze_linear_influence(q)
    with pytest.raises(InfluenceError,match='Missing required'):
        projected_equal({}, {}, ['flag.zf'])


def test_conditional_branch_is_one_path_only():
    result=analyze_linear_influence(doc([
        instruction('x',('reg.ax',),{'flag.zf':['reg.ax']}),
        instruction('jz',('flag.zf',),{'control.pc':['flag.zf']})]))
    assert 'one closed linear path' in result['scope']
