"""Passive scene contracts through actual FDB, script and public dispatch."""
from copy import copy, deepcopy
import hashlib
import json
import time

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from fdisbull.scenes import SceneError, SceneHandle, encoded
from fdisbull.runtime_scenes import validate_definition
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_qemu_movement import moving
from test_scene_domain_integration import scene as frame_definition


def definition(binding='move-state'):
    context=dict(state='authored passive actor',triggers=['independent RAM witness'])
    return dict(format='fdisbull-scene-2',observation_profile=dict(kind='runtime-memory',version=1),
        context=context,match={'runtime_memory':dict(binding=binding,offset=2,length=1,hex='00')},
        objects=[dict(name='actor',context=context,visible={'constant':True},
            ready={'compare':dict(left={'runtime_memory':dict(binding=binding,offset=3,type='u8')},op='eq',right=1)},
            enabled={'constant':True},outcome={'constant':False})])


def save(o,doc=None,name='room'):
    return o.project.debug_save_scene(name,definition() if doc is None else doc)


def test_public_check_assert_persists_profile_and_exact_stop_without_frame(moving):
    o=moving;info=save(o);s=o.session
    workspace=DebugWorkspace();workspace.sessions[s.run_id]=s
    before=deepcopy(s._process)
    try:
        response=respond(dict(method='debug-scene-check',params=dict(project=str(o.project.path),run=s.run_id,
            scene=info['id'],object='actor')),debugger=workspace)
    finally:workspace.sessions.clear()
    assert response['ok'],response
    result=response['result']
    assert result['status']=='matched' and result['complete']
    assert result['format']=='fdisbull-scene-observation-2'
    assert result['completion_scope']=='declared-runtime-predicates' and 'frame' not in result
    assert result['source_identity']['version_sha256']==s.version['sha256']
    assert result['observation_context']['clock']['before']==result['observation_context']['clock']['after']
    assert result['read_statistics']['unique_reads']==2
    stored=o.project.debug_scene_observation(result['observation'])
    assert stored['result']==result and stored['historical'] and not stored['live_state_verified']
    assert not o.runs and not o.writes and not o.deliveries and s._process==before
    assert s.scene_assert('room',object=info['definition']['objects'][0]['id'])['complete']


def test_false_and_missing_capture_keep_shared_scene_error_meaning(moving):
    o=moving;save(o);o.ram[2]=1
    result=o.session.scene_check('room',object='actor')
    assert result['status']=='mismatch' and result['complete']
    with pytest.raises(SceneError) as error:o.session.scene_assert('room',object='actor',compact=True)
    assert error.value.result['status']=='mismatch' and error.value.result['observation']
    assert 'memory_captures' not in error.value.result
    o.ram[2]=0
    assert o.session.scene_check('room')['status']=='matched'
    o.session._runtime_epoch='source-run:process:2';o.session._process['capture_epoch']=o.session._runtime_epoch
    unavailable=o.session.scene_check('room')
    assert unavailable['status']=='unavailable' and not unavailable['complete']
    assert not o.session._runtime_bindings
    o.session.bind_runtime_memory('move-state',ADDRESS,length=4,expected_hex='4142',provenance='fresh epoch witness',space='physical')
    assert o.session.scene_assert('room')['status']=='matched'
    assert not o.runs and not o.writes


def test_revisions_restart_and_source_identity_are_real_storage(moving):
    o=moving;first=save(o);doc=deepcopy(first['definition']);doc['objects'][0]['name']='renamed'
    second=o.project.debug_save_scene('room',doc,parent=first['id'])
    assert second['definition']['objects'][0]['id']==first['definition']['objects'][0]['id']
    assert second['definition']['objects'][0]['aliases']==['actor']
    with Project(o.project.path) as reopened:
        assert reopened.debug_scene_info('room')==second
        assert reopened.debug_scene_info(first['id'])==first
    assert o.session.scene_check('room',object='actor')['status']=='matched'
    assert o.project.db.execute('SELECT count(*) FROM debug_scene_evidence').fetchone()[0]==0


@pytest.mark.parametrize('replacement',[
    {'pixels':{'samples':[{'x':0,'y':0,'rgb':[0,0,0]}]}},
    {'memory':{'address':'0x1000','length':1,'hex':'00'}},
    {'compare':{'left':{'engine_state':{'path':['x']}},'op':'eq','right':1}},
    {'compare':{'left':{'before':{'memory':{'address':'0x1000','type':'u8'}}},'op':'eq','right':1}},
    {'runtime_memory':{'binding':'$prior.id','offset':0,'length':1,'hex':'00'}},
    {'runtime_memory':{'binding':'bound','offset':65535,'length':2,'hex':'0000'}},
    {'compare':{'left':{'runtime_memory':{'binding':'bound','type':'u8','offset':-1}},'op':'eq','right':1}},
])
def test_hidden_invalid_predicates_never_save_or_read(moving,replacement):
    o=moving;doc=definition();doc['match']={'any':[{'constant':True},replacement]}
    before=(len(o.reads),len(o.peer.qmp_calls))
    with pytest.raises((ValueError,TypeError)):save(o,doc)
    assert o.project.debug_scenes()['scenes']==[] and before==(len(o.reads),len(o.peer.qmp_calls))


@pytest.mark.parametrize('extra',[
    dict(reference='capture'),dict(width=320),dict(video={}),dict(navigation={}),dict(handlers=[]),
    dict(observation_profile={'kind':'runtime-memory','version':True}),
    dict(source_identity={'source_sha256':'forged','version':1,'version_sha256':'forged'}),
])
def test_closed_profile_refuses_inferred_frame_and_source_authority(moving,extra):
    with pytest.raises(ValueError):save(moving,dict(definition(),**extra))
    assert moving.project.debug_scenes()['scenes']==[]


@pytest.mark.parametrize('field,value',[
    ('action',{'kind':'press','key':'a'}),('area',{'rect':[0,0,1,1]}),('point',[0,0]),('guest_ms',100),
])
def test_passive_object_never_stores_action_authority(moving,field,value):
    doc=definition();doc['objects'][0][field]=value
    with pytest.raises(ValueError):save(moving,doc)


@pytest.mark.parametrize('change',[
    {'scene':'$dynamic.id','compact':1}, {'scene':'$dynamic.id','object':42},
    {'scene':[],'compact':'$dynamic.compact'}, {'scene':'room','object':'unknown','compact':'$dynamic.compact'},
])
def test_all_known_script_literals_refuse_before_an_actual_prior_ram_write(moving,change):
    o=moving;save(o)
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
        dict(op='scene-check',**change)])
    before=len(o.peer.qmp_calls)
    with pytest.raises((ValueError,TypeError)):o.session.script(script)
    assert not o.writes and o.ram[2]==0 and len(o.peer.qmp_calls)==before


def test_script_resolves_one_field_without_deferring_other_literal_validation(moving):
    o=moving;info=save(o)
    result=o.session.script(dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='scene-check',scene='room',object='actor',**{'as':'checked'}),
        dict(op='scene-assert',scene='$checked.scene_revision',object='actor',compact=True),
        dict(op='assert',value='$checked.status',equals='matched')]))
    assert result['ok'],result
    assert result['steps'][0]['result']['scene_revision']==info['id'] and not o.runs and not o.writes


def test_frozen_selected_undo_and_existing_key_lease_remain_unchanged(moving):
    o=moving;save(o);s=o.session
    lease=s.keyboard_key_down('left')['lease'];before=deepcopy(s.input_state())
    s._qemu_cpu_delta_history=dict(frozen=True,valid=False)
    assert s.scene_check('room')['status']=='unavailable'
    s.bind_runtime_memory('move-state',ADDRESS,length=4,expected_hex='4142',
        provenance='new caller witness of selected frozen CPU/RAM',space='physical')
    assert s.scene_check('room')['status']=='matched'
    assert s._qemu_cpu_delta_history==dict(frozen=True,valid=False)
    assert s.input_state()==before and lease in before['leases'] and not o.runs and not o.writes


@pytest.mark.parametrize('kind',['clock','epoch'])
def test_context_change_during_read_never_publishes_a_success(moving,kind):
    o=moving;save(o)
    def change():
        if kind=='clock':o.now+=1
        else:o.session._runtime_epoch='source-run:process:2';o.session._process['capture_epoch']=o.session._runtime_epoch
    o.after_read=change
    with pytest.raises(ValueError) as error:o.session.scene_check('room')
    assert error.value.result['status']=='unavailable' and not error.value.result['complete']
    assert o.project.debug_scene_observations()['observations']==[]


def test_late_persistence_preserves_observation_receipt(moving,monkeypatch):
    import fdisbull.qemu_scenes as module
    o=moving;save(o);original=module.store
    def late(s,result):
        result=original(s,result)
        monkeypatch.setattr(module.time,'monotonic',lambda:10**12)
        return result
    monkeypatch.setattr(module,'store',late)
    with pytest.raises(TimeoutError) as error:o.session.scene_check('room')
    assert error.value.result['observation']
    assert o.project.debug_scene_observation(error.value.result['observation'])['result']==error.value.result
    assert not o.runs and not o.writes and not o.closed


def test_expired_deadline_rejects_before_native_observations(moving):
    o=moving;save(o);o.session._rpc_deadline=time.monotonic()-1;before=len(o.peer.qmp_calls)
    with pytest.raises(TimeoutError):o.session.scene_check('room')
    assert len(o.peer.qmp_calls)==before and not o.closed


def test_conflicting_and_unknown_candidates_do_not_qualify(moving):
    o=moving;save(o);other=save(o,name='other')
    assert o.session.scene_check('room')['status']=='ambiguous'
    doc=deepcopy(other['definition']);doc['match']['runtime_memory']['binding']='missing'
    o.project.debug_save_scene('other',doc,parent=other['id'])
    result=o.session.scene_check('room')
    assert result['status']=='unavailable' and not result['complete']


def test_saved_manifest_hash_and_identity_both_must_match(moving):
    o=moving;info=save(o);doc=deepcopy(info['definition']);doc['source_identity']['version_sha256']='0'*64
    raw=encoded(doc)
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_scene_revisions SET document=?,sha256=? WHERE id=?',
            (raw.decode(),hashlib.sha256(raw).hexdigest(),info['id']))
    before=len(o.peer.qmp_calls)
    with pytest.raises(ValueError,match='version'):o.session.scene_check('room')
    assert len(o.peer.qmp_calls)==before and not o.writes


def test_all_frame_consumers_refuse_and_legacy_save_bytes_stay_unchanged(moving,tmp_path):
    o=moving;info=save(o);p=o.project
    for consume in (lambda:SceneHandle(o.session,'room'),lambda:p.debug_scene_overlay('room'),
                    lambda:p.debug_scene_domain_audit('room'),lambda:p.debug_export_scenes(['room'],tmp_path/'bad.zip')):
        with pytest.raises(ValueError,match='frame-backed'):consume()
    assert not (tmp_path/'bad.zip').exists()
    legacy=p.debug_save_scene('legacy',frame_definition(p));unchanged=deepcopy(legacy)
    assert p.debug_scene_info('legacy')==unchanged
    assert legacy['definition']['format']=='fdisbull-scene-1' and 'observation_profile' not in legacy['definition']
    with pytest.raises(ValueError,match='profile'):p.debug_save_scene('legacy',definition(),parent=legacy['id'])
    with pytest.raises(ValueError,match='profile'):p.debug_save_scene('room',frame_definition(p),parent=info['id'])


def test_mixed_catalog_keeps_legacy_frame_observations_working(moving):
    from test_scene_readiness import Session, fixture
    legacy=fixture();legacy['format']='fdisbull-scene-1';legacy['content']['displayed']={'constant':True}
    session=Session(legacy)
    session.project.debug_scenes=lambda version=None:{'scenes':[dict(id='runtime',scene='runtime',definition=definition())]}
    assert SceneHandle(session,'scene')._observe('button')['status']=='matched'


@pytest.mark.parametrize('operation,params',[
    ('scene-act',dict(scene='room',object='actor')),
    ('scene-click',dict(scene='room',object='actor')),
    ('scene-wait',dict(scene='room')),
    ('scene-navigation',dict(scene='room',point=[0,0])),
    ('scene-check',dict(scene='room')),
])
def test_legacy_literal_profile_refusal_precedes_an_actual_ram_write(moving,operation,params):
    from fdisbull.debugger import DebugSession
    o=moving;save(o)
    legacy=DebugSession.__new__(DebugSession)
    legacy.project,legacy.version,legacy.run_id=o.project,o.session.version,o.session.run_id
    legacy.metadata={'backend':'dosbox'}
    legacy.write_runtime_memory=o.session.write_runtime_memory
    with pytest.raises(ValueError,match='frame-backed'):
        legacy.script(dict(format='fdisbull-script-1',steps=[
            dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
            dict(op=operation,**params)]))
    assert not o.writes and o.ram[2]==0


def test_poisoned_read_channel_closes_owner_without_hiding_error(moving):
    from fdisbull.dosbox_rpc import DebuggerError
    o=moving;save(o);original=DebuggerError('authored dead QMP peer')
    def failed(*args,**kwargs):
        o.peer.socket=None
        raise original
    o.peer.call=failed
    with pytest.raises(DebuggerError) as error:o.session.scene_check('room')
    assert error.value is original and o.closed


def test_profile_requires_explicit_virtual_clock_before_native_reads(moving):
    o=moving;save(o);o.session.vm.machine_configuration['clock_profile']={'profile':'standard'}
    before=len(o.peer.qmp_calls)
    with pytest.raises(ValueError,match='virtual clock'):o.session.scene_check('room')
    assert len(o.peer.qmp_calls)==before and not o.writes


def test_closed_owner_has_a_deliberate_admission_error(moving):
    o=moving;save(o);o.session.vm=None
    with pytest.raises(ValueError,match='owned machine'):o.session.scene_check('room')


def test_large_witness_receipts_stop_before_additional_reads(moving):
    o=moving;o.ram[:]=b'AB'+bytes(65534)
    o.session.bind_runtime_memory('large',ADDRESS,length=65536,expected_hex=o.ram.hex(),
        provenance='authored largest valid witness',space='physical')
    doc=definition('large');doc['objects'][0]['ready']={'constant':True}
    doc['match']={'all':[{'runtime_memory':dict(binding='large',offset=index,length=1,hex='00')} for index in range(2,34)]}
    save(o,doc);before=len(o.reads);clocks=[]
    o.session.clock_observe=lambda:clocks.append(True) or dict(epoch='epoch',virtual_ns=0)
    result=o.session.scene_check('room')
    assert result['status']=='unavailable' and not result['complete'] and '4 MiB' in result['error']
    assert len(encoded(result['memory_captures']))<=4*1024*1024
    assert len(o.reads)-before<32*2 and len(clocks)==1
    assert not result['capture_context_verified'] and result['observation_context']['clock']['after'] is None


def test_combined_companion_work_refuses_before_any_native_read(moving):
    o=moving;doc=definition()
    doc['match']={'all':[definition()['match'],*({'all':[{'constant':True} for _ in range(64)]} for _ in range(40))]}
    save(o,doc);save(o,doc,name='other');before=(len(o.reads),len(o.peer.qmp_calls))
    with pytest.raises(ValueError,match='Combined scene predicate'):o.session.scene_check('room')
    assert before==(len(o.reads),len(o.peer.qmp_calls))


def test_repeated_cached_predicates_have_a_global_evidence_budget(moving):
    o=moving
    o.session.bind_runtime_memory('cached',ADDRESS,length=64,expected_hex='4142',provenance='large cached read',space='physical')
    predicate={'runtime_memory':dict(binding='cached',length=64,hex=o.ram.hex())}
    doc=definition();doc['objects'][0]['ready']={'constant':True}
    doc['match']={'all':[{'all':[deepcopy(predicate) for _ in range(64)]} for _ in range(48)]}
    save(o,doc);before=len(o.reads);clocks=[]
    o.session.clock_observe=lambda:clocks.append(True) or dict(epoch='epoch',virtual_ns=0)
    result=o.session.scene_check('room')
    assert result['status']=='unavailable' and 'predicate evidence' in result['error']
    assert result['evaluation_budget']['predicate_evidence_bytes']<=1024*1024
    assert result['read_statistics']['unique_reads']==1 and len(o.reads)-before==2
    assert len(clocks)==1 and not result['capture_context_verified']


def test_unique_capture_count_stops_before_the_next_native_read(moving):
    o=moving;o.ram[:]=b'AB'+bytes(510)
    o.session.bind_runtime_memory('many',ADDRESS,length=512,expected_hex='4142',provenance='many observations',space='physical')
    doc=definition();doc['objects'][0]['ready']={'constant':True}
    doc['match']={'all':[{'all':[{'runtime_memory':dict(binding='many',offset=2+64*group+index,length=1,hex='00')}
        for index in range(64)]} for group in range(5)]}
    save(o,doc);before=len(o.reads)
    result=o.session.scene_check('room')
    assert result['status']=='unavailable' and '256 unique' in result['error']
    assert len(o.reads)-before==512 and len(result['memory_captures'])==256


def test_inherited_deadline_expires_during_constants_without_read_or_clock_retry(moving,monkeypatch):
    import fdisbull.scenes as shared
    o=moving;doc=definition();doc['match']={'all':[{'constant':True},doc['match']]};save(o,doc);clocks=[]
    o.session.clock_observe=lambda:clocks.append(True) or dict(epoch='epoch',virtual_ns=0)
    original=shared._evaluate;delayed=[]
    def delayed_constant(spec,*args,**kwargs):
        result=original(spec,*args,**kwargs)
        if spec=={'constant':True} and not delayed:
            delayed.append(True);time.sleep(.15)
        return result
    monkeypatch.setattr(shared,'_evaluate',delayed_constant)
    o.session._rpc_deadline=time.monotonic()+.1
    before=len(o.reads)
    with pytest.raises(TimeoutError) as error:o.session.scene_check('room')
    assert error.value.result['status']=='unavailable' and not error.value.result['complete']
    assert len(clocks)==1 and len(o.reads)==before
    assert not o.project.debug_scene_observations()['observations']


@pytest.mark.parametrize('stage',['cpu','clock','capture'])
def test_owner_replacement_between_native_stages_never_locks_replacement(moving,stage):
    o=moving;s=o.session;save(o);owner=s.vm;replacement=copy(owner);replacement.process=copy(owner.process)
    class ForeignLock:
        calls=0
        def acquire(self,**kwargs):self.calls+=1;return True
        def release(self):pass
    replacement.lock=ForeignLock()
    method={'cpu':'_runtime_paused','clock':'clock_observe','capture':'runtime_memory'}[stage]
    original=getattr(s,method)
    def replace(*args,**kwargs):
        result=original(*args,**kwargs);s.vm=replacement;return result
    setattr(s,method,replace)
    try:
        with pytest.raises(ValueError,match='owner|epoch') as error:s.scene_check('room')
        assert replacement.lock.calls==0 and not o.runs and not o.writes and not o.closed
        assert error.value.result['status']=='unavailable' and not error.value.result['complete']
    finally:s.vm=owner


def test_primary_native_clock_error_keeps_its_receipt_and_partial_scene(moving):
    o=moving;save(o);original=TimeoutError('authored clock read failure');receipt={'native':'original receipt'}
    original.result=receipt
    def failed():raise original
    o.session.clock_observe=failed
    with pytest.raises(TimeoutError) as error:o.session.scene_check('room')
    assert error.value is original and error.value.result is receipt
    assert error.value.scene_result['status']=='unavailable' and not error.value.scene_result['complete']
