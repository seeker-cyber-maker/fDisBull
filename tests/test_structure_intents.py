"""Authored behavioral contracts, not extracted game semantics or native traces."""
from copy import deepcopy
from hashlib import sha256
import json
import pytest

from fdisbull.structure_intents import (parse_composition, audit_invocations,
    compare_observations, intent_drafts, read_json)
from fdisbull.structure_discovery import scan_directory


def fixture():
    contracts={};phases={}
    terminals={'confirm':'complete','commit':'committed','scene':'ready','sound':'finished'}
    for name,end in terminals.items():
        contracts[name]={'format':'fdisbull-block-contract-1','name':name,'inputs':{},'outputs':{},
                         'behavior':{'kind':'service','service':'authored.'+name}}
        phases[name]={'terminal':end,'observations':{
            'accepted':{'condition':'request admitted','evidence':'authored-spec','after':[]},
            end:{'condition':'declared observable result present','evidence':'authored-spec','after':['accepted']}}}
    def child(slot,contract,owner='parent',after=None):
        return {'slot':slot,'contract':contract,'owner':owner,'on_restore':'cancel','on_cancel':'cancel','after':after or []}
    implementations={name+'.original':{'contract':name,'children':[],'complete_after':[],'evidence':'authored-provider'} for name in contracts}
    implementations['confirm.original']['children']=[child('commit','commit'),
        child('scene','scene',after=[{'slot':'commit','phase':'committed'}]),child('sound','sound','context')]
    implementations['confirm.original']['complete_after']=[{'slot':'commit','phase':'committed'},
        {'slot':'scene','phase':'ready'},{'slot':'sound','phase':'accepted'}]
    implementations['confirm.replacement']={'contract':'confirm','children':[],'complete_after':[],'evidence':'authored-provider'}
    return {'format':'fdisbull-structure-composition-1','root':'confirm','contracts':contracts,'phases':phases,
            'implementations':implementations,'selection':{k:k+'.original' for k in contracts},'evidence':'authored-example'}


def trace():
    events=[]
    def begin(ident,contract,parent=None,slot=None):
        events.append({'kind':'begin','epoch':0,'tick':len(events),'evidence':'authored-witness','invocation':ident,
                       'contract':contract,'implementation':contract+'.original','parent':parent,'slot':slot})
    def phase(ident,p):
        events.append({'kind':'phase','epoch':0,'tick':len(events),'evidence':'authored-witness','invocation':ident,'phase':p})
    begin('parent','confirm');phase('parent','accepted')
    begin('c','commit','parent','commit');phase('c','accepted');phase('c','committed')
    begin('s','sound','parent','sound');phase('s','accepted')
    begin('view','scene','parent','scene');phase('view','accepted');phase('view','ready')
    phase('parent','complete');phase('s','finished')
    return {'source_sha256':'0'*64,'run':'authored','clock':{'domain':'logical','unit':'tick'},'initial_epoch':0,'events':events}


def codes(t):return {v['code'] for v in audit_invocations(fixture(),t)['violations']}


def test_composition_uses_existing_contracts_and_does_not_execute():
    r=parse_composition(fixture())
    assert r['status']=='validated_analysis_plan' and not r['scheduler_implemented'] and not r['execution_authorized']


def test_replacement_parent_bypasses_undelegated_children():
    d=fixture();d['selection']['confirm']='confirm.replacement'
    r=parse_composition(d)
    assert r['selected_contracts']==['confirm'] and r['inactive_selections']==['commit','scene','sound']


def test_delegating_replacement_selects_only_invoked_child():
    d=fixture();p=d['implementations']['confirm.replacement']
    p['children']=[d['implementations']['confirm.original']['children'][0]]
    p['complete_after']=[{'slot':'commit','phase':'committed'}];d['selection']['confirm']='confirm.replacement'
    assert parse_composition(d)['selected_contracts']==['commit','confirm']


def test_sound_can_outlive_parent_but_not_lose_owner():
    r=audit_invocations(fixture(),trace())
    assert r['violations']==[] and r['outstanding']==[]
    t=trace();t['events'].pop()
    r=audit_invocations(fixture(),t)
    assert r['violations']==[] and r['outstanding'][0]['invocation']=='s'
    assert r['status']=='consistent-prefix'


def test_parent_owned_child_requires_terminal_join():
    d=fixture();d['implementations']['confirm.original']['children'][2]['owner']='parent'
    with pytest.raises(ValueError,match='parent-owned'):parse_composition(d)


def test_unknown_phase_not_accepted():
    d=fixture();d['implementations']['confirm.original']['complete_after'][0]['phase']='made-up'
    with pytest.raises(ValueError,match='phase'):parse_composition(d)


def test_phase_definition_needs_condition():
    d=fixture();d['phases']['sound']['observations']['accepted']['condition']=''
    with pytest.raises(ValueError):parse_composition(d)


def test_child_cycle_refused():
    d=fixture();d['implementations']['confirm.original']['children'][0]['after']=[{'slot':'scene','phase':'ready'}]
    with pytest.raises(ValueError,match='cycle'):parse_composition(d)


def test_phase_cycle_refused():
    d=fixture();d['phases']['commit']['observations']['accepted']['after']=['committed']
    with pytest.raises(ValueError,match='cycle'):parse_composition(d)


def test_contract_recursion_not_silently_expanded():
    d=fixture();d['implementations']['confirm.replacement']['children']=[{'slot':'again','contract':'confirm','owner':'session','on_restore':'cancel','on_cancel':'cancel','after':[]}]
    d['selection']['confirm']='confirm.replacement'
    with pytest.raises(ValueError,match='cycle'):parse_composition(d)


def test_selection_wrong_contract_rejected():
    d=fixture();d['selection']['sound']='commit.original'
    with pytest.raises(ValueError,match='same contract'):parse_composition(d)


def test_invalid_existing_contract_rejected():
    d=fixture();d['contracts']['sound']['outputs']={'x':'imaginary'}
    with pytest.raises(ValueError):parse_composition(d)


def test_duplicate_slot_refused():
    d=fixture();d['implementations']['confirm.original']['children'][1]['slot']='commit'
    with pytest.raises(ValueError,match='duplicate'):parse_composition(d)


def test_missing_selected_child_rejected():
    d=fixture();del d['selection']['sound']
    with pytest.raises(ValueError,match='unselected'):parse_composition(d)


def test_no_synchronous_order_inferred_for_sound():
    t=trace();sound=t['events'][5:7];del t['events'][5:7]
    t['events'][2:2]=sound
    for i,e in enumerate(t['events']):e['tick']=i
    assert codes(t)==set()


def test_premature_destination_detected():
    t=trace();t['events']=[e for e in t['events'] if not (e['invocation']=='c' and e.get('phase')=='committed')]
    assert 'dependency-not-complete' in codes(t) and 'premature-parent-completion' in codes(t)


def test_duplicate_effect_retained_as_failure():
    t=trace();e={'kind':'effect','epoch':0,'tick':6,'evidence':'authored','invocation':'s','effect_id':'start-sound','payload':{'sound':1}}
    t['events'][6:6]=[e,dict(e)]
    for i,x in enumerate(t['events']):x['tick']=i
    assert 'duplicate-effect-id' in codes(t)


def test_replacement_does_not_trigger_original_descendant():
    d=fixture();d['selection']['confirm']='confirm.replacement'
    t=trace();t['events'][0]['implementation']='confirm.replacement'
    r=audit_invocations(d,t)
    assert 'child-not-in-selected-implementation' in {v['code'] for v in r['violations']}


def test_duplicate_phase_and_missing_phase_prerequisite():
    t=trace();t['events'][3]['phase']='committed'
    assert 'phase-prerequisite-missing' in codes(t) and 'duplicate-phase' in codes(t)


def test_stale_completion_after_restore():
    t=trace();t['events']=t['events'][:7]+[
        {'kind':'restore','epoch':1,'tick':0,'evidence':'authored-restore'},
        {'kind':'phase','epoch':0,'tick':100,'evidence':'late-host-result','invocation':'s','phase':'finished'}]
    r=audit_invocations(fixture(),t)
    assert r['violations'][0]['code']=='stale-or-foreign-epoch'
    assert r['restoration_obligations'] and not r['restoration_obligations'][0]['effect_undo_observed']


def test_repeated_contract_occurrences_keep_identity():
    t=trace();again=deepcopy(t['events'])
    for e in again:
        e['tick']+=20;e['invocation']+='2'
        if e.get('parent') is not None:e['parent']+='2'
    t['events']+=again
    r=audit_invocations(fixture(),t)
    assert not r['violations'] and r['invocations']==8


@pytest.mark.parametrize('kind',['cancel','uncertain'])
def test_no_automatic_retry_after_uncertain_effect(kind):
    t=trace();t['events'].insert(6,{'kind':kind,'epoch':0,'tick':6,'evidence':'authored','invocation':'s'})
    for i,e in enumerate(t['events']):e['tick']=i
    assert 'completion-after-cancel-or-uncertainty' in codes(t)


def test_effect_after_terminal_refused():
    t=trace();t['events'].append({'kind':'effect','epoch':0,'tick':100,'evidence':'authored','invocation':'s','effect_id':'late','payload':{}})
    assert 'effect-after-terminal-phase' in codes(t)


def test_foreign_invocation_refused():
    t=trace();t['events'][3]['invocation']='foreign'
    assert 'unknown-invocation' in codes(t)


def test_duplicate_invocation_is_not_a_second_execution():
    t=trace();t['events'].insert(1,deepcopy(t['events'][0]))
    assert 'duplicate-invocation' in codes(t)


def test_parent_after_complete_cannot_spawn_original_children():
    t=trace();e=deepcopy(t['events'][2]);e.update(invocation='c2',tick=100)
    t['events'].append(e)
    assert 'inactive-parent' in codes(t)


@pytest.mark.parametrize('clock',[{'domain':'host','unit':'second'},{'domain':'logical','unit':'second'},{}])
def test_clock_not_inferred(clock):
    t=trace();t['clock']=clock
    with pytest.raises(ValueError,match='clock'):audit_invocations(fixture(),t)


def observation():
    return {'contract_sha256':'1'*64,'scope':'authored menu outputs and ordered effects',
            'inputs':{'accepted':True},'outputs':{'cash':123,'view':'new'},
            'effects':[{'kind':'sound','asset':1},{'kind':'image','asset':2}],'complete':True}


def test_macro_observations_ignore_internal_implementation():
    a=observation();r=compare_observations(a,deepcopy(a))
    assert r['status']=='matched-declared-observations'


def test_image_subcomponent_failure_is_localized():
    a=observation();b=deepcopy(a);b['effects'][1]['asset']=3
    assert compare_observations(a,b)['differences'][0]['path']=='effects[1].asset'


def test_output_state_and_effect_both_required():
    a=observation();b=deepcopy(a);b['outputs']['cash']=0
    assert compare_observations(a,b)['differences'][0]['path']=='outputs.cash'


def test_sound_twice_is_not_same_silent_final_state():
    a=observation();b=deepcopy(a);b['effects'].append(b['effects'][0])
    assert compare_observations(a,b)['equivalent'] is False


def test_effect_order_is_not_discarded():
    a=observation();b=deepcopy(a);b['effects'].reverse()
    assert compare_observations(a,b)['equivalent'] is False


def test_bool_and_integer_not_equal_observations():
    a=observation();b=deepcopy(a);b['outputs']['cash']=True;a['outputs']['cash']=1
    assert compare_observations(a,b)['equivalent'] is False


def test_incomplete_is_not_a_pass():
    a=observation();b=deepcopy(a);b['complete']=False
    assert compare_observations(a,b)['equivalent'] is None


@pytest.mark.parametrize('key,value',[('contract_sha256','2'*64),('scope','other'),('inputs',{'accepted':False})])
def test_compare_requires_same_boundary(key,value):
    a=observation();b=deepcopy(a);b[key]=value
    with pytest.raises(ValueError):compare_observations(a,b)


def test_source_patterns_are_not_executable_contracts():
    report={'format':'fdisbull-structure-discovery-pilot-1','findings':[{'id':'lead-1','pattern':'p','why':['test -> effect'],
        'next_probe':'qualify consumer','bindings':{'effect':{'id':'e','role':'effect','operation':'call','evidence':{'space':'s','source_sha256':'0'*64}}}}]}
    r=intent_drafts(report);d=r['items'][0]
    assert d['contract_ref'] is None and d['proposed_intent'] is None
    assert not d['execution_authorized'] and d['components'][0]['operation_kind']=='call'


def test_file_reader_refuses_duplicate_keys_and_nonfinite(tmp_path):
    p=tmp_path/'x.json'
    for text in ('{"a":1,"a":2}','{"a":NaN}'):
        p.write_text(text)
        with pytest.raises(ValueError):read_json(p)


def test_input_spec_not_mutated():
    d=fixture();t=trace();old=deepcopy((d,t))
    audit_invocations(d,t)
    assert (d,t)==old


def test_child_cannot_commit_after_parent_cancel():
    t=trace();t['events'].insert(4,{'kind':'cancel','epoch':0,'tick':4,'evidence':'authored','invocation':'parent'})
    for i,e in enumerate(t['events']):e['tick']=i
    assert 'child-completion-after-parent-cancellation' in codes(t)


def test_comparison_error_budget_is_bounded():
    a=observation();b=deepcopy(a);b['outputs']={str(i):i for i in range(1000)}
    r=compare_observations(a,b)
    assert len(r['differences'])<=32 and r['comparison_truncated']


def test_terminal_cannot_precede_another_phase():
    d=fixture();d['phases']['sound']['observations']['later']={'after':['finished'],'condition':'later','evidence':'authored'}
    with pytest.raises(ValueError,match='terminal'):parse_composition(d)


def test_six_node_composition_rule_with_incoming_join():
    from fdisbull.structure_patterns import match_graph
    ev={'space':'s','source_sha256':'0'*64}
    nodes=[{'id':k,'role':k,'evidence':ev} for k in ('input','gate','feedback','request','consumer','ready')]
    edges=[('input','gate','predicate'),('gate','feedback','controls'),('gate','request','controls'),
           ('request','consumer','channel'),('consumer','ready','publishes')]
    rule={'id':'authored-chain','nodes':{k:k for k in ('input','gate','feedback','request','consumer','ready')},
          'edges':[edges[3],edges[1],edges[0],edges[2],edges[4]],'rank':1,'title':'authored connected chain',
          'next':'qualify each witness','limits':'authored facts only'}
    r=match_graph(nodes,edges,rules=[rule])
    assert len(r['matches'])==1 and len(r['matches'][0]['bindings'])==6
    assert r==match_graph(list(reversed(nodes)),list(reversed(edges)),rules=[rule])
    edges.pop(3)
    assert match_graph(nodes,edges,rules=[rule])['matches']==[]


def test_extended_matcher_preserves_cross_source_refusal():
    from fdisbull.structure_patterns import match_graph,RULES
    nodes=[{'id':'r','role':'read','evidence':{'space':'s','source_sha256':'0'*64}},
           {'id':'m','role':'mask','evidence':{'space':'s','source_sha256':'1'*64}},
           {'id':'b','role':'branch','evidence':{'space':'s','source_sha256':'0'*64}}]
    assert not match_graph(nodes,[('r','m','value'),('m','b','predicate')])['matches']


def test_extended_matcher_budget_bounds_high_fanout():
    from fdisbull.structure_patterns import match_graph
    ev={'space':'s','source_sha256':'0'*64}
    nodes=[{'id':str(i),'role':'x','evidence':ev} for i in range(30)]
    edges=[(str(i),str(j),'next') for i in range(30) for j in range(30) if i!=j]
    rule={'id':'fan','nodes':{str(i):'x' for i in range(8)},'edges':[(str(i),str(i+1),'next') for i in range(7)],'rank':1,'title':'fan','next':'stop','limits':'authored'}
    r=match_graph(nodes,edges,rules=[rule],max_work=20)
    assert r['join_work']==20 and r['work_budget_exhausted']
