"""Authored selector and episode cases; no game code, pixels or offsets."""
from copy import deepcopy
from hashlib import sha256
import json
import subprocess
import sys
from pathlib import Path
import pytest
from fdisbull.structure_events import SELECTOR_RULE, classify_episode, selector_facts
from fdisbull.structure_native import native_facts
from fdisbull.structure_patterns import match_graph, RULES


def native(code, bits=16):
    b=bytes.fromhex(code)
    v={'bytes':b,'bits':bits,'base':0,'entry':0,'entry_ip':0,'entry_cs':0,
       'kind':'authored-source','sha256':sha256(b).hexdigest(),
       'qualification':'authored fixture','file_mapping':[]}
    n,e,c=native_facts(v,{'sha256':sha256(b).hexdigest()})
    return match_graph(n,e,rules=(SELECTOR_RULE,)),c


@pytest.mark.parametrize('bits',[16,32])
def test_selected_register_call(bits):
    # CMP AL,1; JNE out; CALL target; RET; target: RET.
    code='3c017504e80100c3c3' if bits==16 else '3c017506e801000000c3c3'
    r,c=native(code,bits)
    calls=[m for m in r['matches'] if m['bindings']['effect']['operation']=='call']
    assert len(calls)==1
    effect=calls[0]['bindings']['effect']
    assert effect['selector_relation']=='equal' and effect['callee_summary']=='unknown'
    assert calls[0]['runtime_observed'] is False and not calls[0]['execution_authorized']


@pytest.mark.parametrize('branch,equal', [('74','equal'),('75','not_equal')])
def test_branch_polarity_and_first_memory_effect(branch,equal):
    # CMP AL,1; Jcc selected; RET; selected: MOV [0x100],1; RET.
    r,c=native('3c01'+branch+'01c3c606000101c3')
    writes=[m['bindings']['effect'] for m in r['matches'] if m['bindings']['effect']['operation']=='memory_write']
    assert len(writes)==1 and writes[0]['selector_relation']==equal
    assert writes[0]['write_operation']=='mov' and writes[0]['storage_role']=='unresolved'


def test_indirect_call_does_not_invent_callback_destination():
    r,c=native('3c017503ffd3c3c3')
    calls=[m['bindings']['effect'] for m in r['matches'] if m['bindings']['effect']['operation']=='call']
    assert len(calls)==1 and calls[0]['target'] is None


@pytest.mark.parametrize('code',[
    '3c01407401c3c3', # INC changes flags
    '3c01907401c3c3', # pilot requires adjacency even if NOP is harmless
    '3c010f95c0c3',   # no JE/JNE consumer
    '3c01eb007401c3c3', # a transfer between comparison and consumer
])
def test_missing_immediate_predicate_connection(code):
    assert not native(code)[0]['matches']


def test_unknown_instruction_stops_an_arm():
    r,c=native('3c017507cd21c606000101c3')
    assert not any(m['bindings']['effect']['operation']=='memory_write' for m in r['matches'])
    assert c['event_candidates']['unresolved_count']>0


def test_return_reached_from_both_arms_is_not_attributed_to_one():
    r,c=native('3c01740190c3')
    assert not r['matches']


def test_call_is_a_summary_barrier_not_the_callee_effect():
    r,c=native('3c017504e80100c3c606000101c3')
    assert all(m['bindings']['effect']['operation']!='memory_write' for m in r['matches'])


@pytest.mark.parametrize('kw',[{'max_arm_steps':0},{'max_arm_steps':65},{'max_sites':True},{'max_sites':10001}])
def test_invalid_selector_budgets(kw):
    with pytest.raises(ValueError):selector_facts({}, {},None,None,bits=16,base=0,**kw)


def obs(tick, context='menu', value=0, ready=True, **extras):
    return {'identity':{'source_sha256':'a'*64,'run':'authored','epoch':'initial'},
            'tick':tick,'context':context,'fields':{'setting':value},'ready':ready,
            'evidence':f'authored:{tick}',**extras}


def episode(*after):return {'before':obs(10),'idle':[obs(0),obs(5)],'after':list(after)}


@pytest.mark.parametrize('after,category,nav,state',[
    (obs(20,value=1),'local-effect','same','changed'),
    (obs(20,context='other'),'dispatch-effect','changed','unchanged-selected'),
    (obs(20,context='other',value=1),'mixed','changed','changed'),
    (obs(20),'no-selected-effect','same','unchanged-selected'),
    (obs(20,presentation_changed=True),'presentation-only-candidate','same','unchanged-selected'),
    (obs(20,context=None),'pending-or-unresolved','unresolved','unchanged-selected'),
    (obs(20,ready=False),'pending-or-unresolved','unresolved','unchanged-selected'),
    (obs(20,pending=True),'pending-or-unresolved','unresolved','unchanged-selected'),
])
def test_independent_axes(after,category,nav,state):
    r=classify_episode(episode(after))
    assert (r['category'],r['context_effect'],r['state_effect'])==(category,nav,state)
    assert r['execution_authorized'] is False


def test_roundtrip_is_not_a_same_screen_noop():
    r=classify_episode(episode(obs(20,'dialog'),obs(30,'menu')))
    assert r['context_effect']=='roundtrip' and r['category']=='dispatch-effect'


def test_requested_destination_is_not_ready_destination():
    e=episode(obs(20,pending=True),obs(30,context='new',ready=False))
    assert classify_episode(e)['category']=='pending-or-unresolved'
    e['after'].append(obs(40,context='new',ready=True,pending=False))
    assert classify_episode(e)['category']=='dispatch-effect'


def test_animation_only_noise_does_not_establish_a_local_mutation():
    e=episode(obs(20,value=3));e['idle'][1]['fields']['setting']=2
    r=classify_episode(e)
    assert r['state_effect']=='unresolved' and not r['changed_fields']
    assert r['idle_varying_fields']==['setting']


def test_unknown_state_is_not_claimed_unchanged():
    e=episode(obs(20,context='new'))
    for o in [e['before'],*e['idle'],*e['after']]:o['fields']={}
    r=classify_episode(e)
    assert r['state_effect']=='unobserved' and r['category']=='dispatch-effect'


def test_missing_field_is_not_a_deleted_entity():
    e=episode(obs(20));e['after'][0]['fields']={}
    assert classify_episode(e)['state_effect']=='unresolved'


@pytest.mark.parametrize('key,value', [('run','another'),('epoch','restored'),('source_sha256','b'*64)])
def test_stale_observation_identity_refused(key,value):
    e=episode(obs(20));e['after'][0]['identity'][key]=value
    with pytest.raises(ValueError):classify_episode(e)


@pytest.mark.parametrize('mutation',[
    lambda e:e['after'][0].update(tick=10),
    lambda e:e['after'][0].update(evidence=''),
    lambda e:e['after'][0].update(ready=1),
    lambda e:e['after'][0].update(pending='yes'),
    lambda e:e['after'][0].update(context={}),
    lambda e:e['idle'][1].update(tick=11),
    lambda e:e.update(after=[]),
])
def test_malformed_episode_refused(mutation):
    e=episode(obs(20));mutation(e)
    with pytest.raises(ValueError):classify_episode(e)


def test_classifier_does_not_mutate_input_and_is_deterministic():
    e=episode(obs(20,value=1));saved=deepcopy(e)
    assert classify_episode(e)==classify_episode(e) and e==saved


def test_unready_start_cannot_authorize_action_outcome():
    e=episode(obs(20,value=1));e['before']['ready']=False
    assert classify_episode(e)['context_effect']=='unresolved'


def test_module_cli(tmp_path):
    p=tmp_path/'episode.json';p.write_text(json.dumps(episode(obs(20,value=1))))
    result=subprocess.run([sys.executable,'-m','fdisbull.structure_events',str(p)],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['category']=='local-effect'
    p.write_text('{}')
    assert subprocess.run([sys.executable,'-m','fdisbull.structure_events',str(p)],capture_output=True).returncode==2


def test_scan_uses_updated_rules_identity(tmp_path):
    from fdisbull.structure_discovery import scan_directory
    r=scan_directory(tmp_path)
    assert r['rules_sha256']==match_graph([],[],rules=RULES+(SELECTOR_RULE,))['rules_sha256']


def test_branch_into_instruction_interior_is_not_a_qualified_arm():
    r,c=native('3c017505cd21c606000101c3')
    assert not any(m['bindings']['effect']['operation']=='memory_write' for m in r['matches'])
    assert c['event_candidates']['overlapping_rows']>0


@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_nonfinite_fields_refused(value):
    with pytest.raises(ValueError):classify_episode(episode(obs(20,value=value)))


def test_zero_epoch_can_identify_initial_session():
    e=episode(obs(20))
    for o in [e['before'],*e['idle'],*e['after']]:o['identity']['epoch']=0
    assert classify_episode(e)['category']=='no-selected-effect'


def test_changing_idle_context_is_explicit_not_clean_control():
    e=episode(obs(20,'other'));e['idle'][0]['context']='attract'
    r=classify_episode(e)
    assert r['idle_context_stable'] is False and 'not a matched counterfactual' in r['control_design']


def test_missing_pending_channel_is_unknown_not_false():
    assert classify_episode(episode(obs(20)))['pending'] is None
    assert classify_episode(episode(obs(20,pending=False)))['pending'] is False
