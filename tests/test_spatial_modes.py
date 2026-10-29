import pytest
import base64
import hashlib
from fdisbull.spatial_modes import SpatialActionHandle


def predicate(field, value):
    return {'field':field,'op':'eq','value':value}


def action():
    fields={key:{'status':key} for key in ('room','ready','done','x','y')}
    return {'format':'fdisbull-spatial-action-1','id':'door','version':1,'map_revision':'map1',
            'observations':fields,'context':predicate('room',1),
            'nonspatial_before':predicate('ready',1),'nonspatial_after':predicate('ready',1),
            'outcome':predicate('done',1),'proximity':predicate('x',4),
            'position':{'x':'x','y':'y'},'inputs':[{'key':'enter'}],
            'guest_ms':100,'slice_ms':50,'stationary':True,
            'spatial_guards':[{'kind':'spatial-resource','binding':'logic','offset':3,
                               'expected_hex':'0b000a0b1415','data_hex':'0b0000009fa7',
                               'provenance':{'source_sha256':'source','version_sha256':'version',
                               'resource_sha256':hashlib.sha256(b'\x0b\x00\xff\x0b\x00\x0a\x0b\x14\x15\xff\x00\x00\x00').hexdigest(),
                               'resource_offset':3,'file':'logic','evidence':'guard-trace'}}]}


class Session:
    version={'id':1}; metadata={'source_sha256':'source','version_sha256':'version'}
    def __init__(self):
        self.values={'room':1,'ready':1,'done':0,'x':4,'y':3}
        self.active=['prior']; self.events=[]; self.presses=0; self.stop=False; self.fail_restore=False
        source=b'\x0b\x00\xff\x0b\x00\x0a\x0b\x14\x15\xff\x00\x00\x00'
        self.memory_bytes=bytearray(source);self._runtime_names={'logic':'id'}
        self._runtime_bindings={'id':{'address':4096,'length':len(source),'expected_hex':source[:2].hex()}}
        class Project:
            def file_bytes(self,name,offset,size,version):
                return {'bytes':source.hex(),'complete':True,'sha256':hashlib.sha256(source).hexdigest()}
        self.project=Project()
    def keyboard_state(self): return {'keyboard':{'pending_events':0,'owned_keys':0}}
    def keyboard_press(self,**kw): self.presses+=1; return {}
    def runtime_memory(self,binding,offset,length): return {'hex':self.memory_bytes[offset:offset+length].hex()}
    def call(self,op,params):
        offset=int(params['address']['offset'],16)-4096; data=base64.b64decode(params['data_base64'])
        assert hashlib.sha256(self.memory_bytes[offset:offset+len(data)]).hexdigest()==params['expected_sha256']
        self.memory_bytes[offset:offset+len(data)]=data
    def code(self,*a,**kw): return {'hex':'7502'}
    def layer_patch(self,*a,**kw): assert kw['kind']=='execute' and kw['activate'] is False; return {'layer':'guard'}
    def layers(self,active=None):
        if active is not None:
            if self.fail_restore and active==['prior']: raise ValueError('restore failed')
            self.active=list(active)
        return {'active':list(self.active)}
    def run(self,**kw):
        if self.stop: return {'outcome':'breakpoint'}
        self.values['done']=1
        return {'outcome':'guest_time','guest_elapsed_ms':50,'hook_hits':[]}
    def _event(self,name,data): self.events.append((name,data))


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr('fdisbull.spatial_modes.capture_observations',lambda s, specs: {'complete':True,'values':dict(s.values)})
    return Session()


def test_physical_requires_proximity_without_edits(session):
    session.values['x']=8
    result=SpatialActionHandle(session,'map1').interact(action())
    assert not result['ok'] and session.presses==0 and session.active==['prior']
    session.values['x']=4
    assert SpatialActionHandle(session,'map1').interact(action())['ok']


def test_story_runs_original_input_and_restores_stack_on_success_and_stop(session):
    session.values['x']=8
    handle=SpatialActionHandle(session,'map1',mode='story')
    result=handle.interact(action())
    assert result['ok'] and session.presses==1 and session.values['x']==8
    assert result['rollback']=={'ok':True,'active':['prior']}
    session.stop=True
    result=handle.interact(action())
    assert result['status']=='stopped' and not result['ok'] and session.active==['prior']


def test_story_rejects_source_mismatch_and_failed_rollback(session):
    handle=SpatialActionHandle(session,'map1',mode='story')
    d=action(); d['spatial_guards'][0]['provenance']['source_sha256']='other'
    assert not handle.interact(d)['ok'] and session.presses==0
    session.fail_restore=True
    result=handle.interact(action())
    assert not result['ok'] and result['rollback']['ok'] is False


def test_assisted_refuses_unknown_map_and_unqualified_writes(session):
    handle=SpatialActionHandle(session,'map1',mode='assisted',check_point=lambda *a:{'classification':'unknown'},
                               choose_anchor=lambda *a:[4,3],travel_plan=lambda *a:{})
    assert 'not known clear' in handle.interact(action())['error']
    assert session.presses==0


def test_fair_play_rejects_nonphysical(session):
    with pytest.raises(ValueError): SpatialActionHandle(session,'map1',mode='story',fair_play=True)


def test_assisted_qualifies_anchor_and_rechecks_after_guest_settles(session):
    d=action()
    for axis in ('x','y'):
        d['observations'][axis]={'runtime_memory':{'binding':'actor','offset':8 if axis=='x' else 10,'type':'u16'}}
    recipe={'x':{'binding':'actor','offset':8,'type':'u16'},'y':{'binding':'actor','offset':10,'type':'u16'},'refresh':[]}
    plan={'kind':'within-room','inputs':[], 'destination':{'room_field':'room'}, 'writes':[recipe['x']|{'value':4},recipe['y']|{'value':3}]}
    def travel(value,timeout_ms):
        assert value==plan
        session.values.update(x=4,y=3)
        return {'ok':True,'complete':True}
    session.assisted_travel=travel
    session.values['x']=9
    checks=[]
    def check(revision,point):
        checks.append((revision,point))
        return {'classification':'clear'}
    handle=SpatialActionHandle(session,'map1',mode='assisted',check_point=check,
          choose_anchor=lambda *args:[4,3],travel_plan=lambda *args:plan,actor_recipe=recipe)
    result=handle.interact(d)
    assert result['ok'] and session.presses==1 and checks==[('map1',[4,3]),('map1',[4,3])]


def test_assisted_rejects_coordinate_recipe_mismatch_before_writes(session):
    d=action(); called=[]
    recipe={'x':{'binding':'actor','offset':8,'type':'u16'},'y':{'binding':'actor','offset':10,'type':'u16'},'refresh':[]}
    handle=SpatialActionHandle(session,'map1',mode='assisted',check_point=lambda *args:{'classification':'clear'},
          choose_anchor=lambda *args:[4,3],travel_plan=lambda *args:{},actor_recipe=recipe)
    session.assisted_travel=lambda *args,**kwargs: called.append(True)
    assert not handle.interact(d)['ok'] and not called


@pytest.mark.parametrize("opcode", [11, 16, 17, 18])
def test_story_resource_patch_restores_after_original_action_and_stop(session, tmp_path, opcode):
    import base64
    import hashlib
    from fdisbull.project import Project
    source=b'\x0b\x00\xff'+bytes([opcode,0,10,11,20,21,255,0,0,0])
    memory=bytearray(source)
    digest=hashlib.sha256(source).hexdigest()
    binary=tmp_path / 'program.bin'; binary.write_bytes(b'\xc3'+bytes(127))
    resource=tmp_path / 'logic.bin'; resource.write_bytes(source)
    session.project=Project.create(tmp_path / 'test.fdb',binary,arch='x86',base=0x1000)
    session.project.attach_file(resource,name='logic')
    session._runtime_names={'logic':'id'}
    session._runtime_bindings={'id':{'address':4096,'length':len(source),'expected_hex':source[:2].hex()}}
    session.runtime_memory=lambda binding,offset,length: {'hex':memory[offset:offset+length].hex()}
    def call(op,params):
        assert op=='memory.write'
        offset=int(params['address']['offset'],16)-4096
        data=base64.b64decode(params['data_base64'])
        assert hashlib.sha256(memory[offset:offset+len(data)]).hexdigest()==params['expected_sha256']
        memory[offset:offset+len(data)]=data
    session.call=call
    original_run=session.run
    def run(**kwargs):
        assert memory[3:9]==bytes([opcode,0,0,0,159,167])
        return original_run(**kwargs)
    session.run=run
    d=action(); d['spatial_guards']=[{'kind':'spatial-resource','binding':'logic','offset':3,
        'expected_hex':bytes([opcode,0,10,11,20,21]).hex(),'data_hex':bytes([opcode,0,0,0,159,167]).hex(),
        'provenance':{'source_sha256':'source','version_sha256':'version','resource_sha256':digest,
                      'resource_offset':3,'file':'logic','evidence':'decoded condition'}}]
    session.values['x']=9
    handle=SpatialActionHandle(session,'map1',mode='story')
    result=handle.interact(d)
    assert result['ok'] and memory==source and result['resource_rollback'][0]['ok']
    session.stop=True
    result=handle.interact(d)
    assert result['status']=='stopped' and memory==source
    session.stop=False
    duplicate=dict(d['spatial_guards'][0])
    d['spatial_guards'].append(duplicate)
    overlap=handle.interact(d)
    assert 'overlap' in overlap['error'] and memory==source
    d['spatial_guards'].pop()
    d['nonspatial_after']=predicate('ready',0)
    failed=handle.interact(d)
    assert 'postconditions' in failed['error'] and memory==source and failed['resource_rollback'][0]['ok']
    d['nonspatial_after']=predicate('ready',1)
    def change_room(**kwargs):
        session.values['room']=2
        return {'outcome':'guest_time','guest_elapsed_ms':50,'hook_hits':[]}
    session.run=change_room
    failed=handle.interact(d)
    assert 'context changed' in failed['error'] and memory==source and failed['resource_rollback'][0]['ok']
    d['spatial_guards'][0]['data_hex']='0b0100009fa7'
    assert not handle.interact(d)['ok'] and memory==source
    session.project.db.close()


def test_session_policy_cannot_be_bypassed(session):
    session._fair_play=True
    with pytest.raises(ValueError,match='Fair play'):
        SpatialActionHandle(session,'map1',mode='story')
    session._fair_play=False; session._spatial_mode='assisted'
    with pytest.raises(ValueError,match='session policy'):
        SpatialActionHandle(session,'map1',mode='story')


def test_layer_restore_failure_poison_closes_session(session):
    session.fail_restore=True
    session.close=lambda: setattr(session,'closed',True)
    result=SpatialActionHandle(session,'map1',mode='story').interact(action())
    assert not result['ok'] and not result['rollback']['ok']
    assert session.closed and session._spatial_guard_failed
    assert 'unavailable' in SpatialActionHandle(session,'map1',mode='story').interact(action())['error']


def test_multiple_inputs_drain_and_use_one_budget(session):
    d=action(); d['inputs']=[{'text':'get radio'},{'key':'enter'}]; d['guest_ms']=150
    pending=[]; seen=[]
    def queue(**kw):
        assert not pending
        pending.append(True); seen.append(kw); return {}
    session.keyboard_type=queue; session.keyboard_press=queue
    session.keyboard_state=lambda: {'keyboard':{'pending_events':len(pending),'owned_keys':0}}
    def run(**kwargs):
        assert kwargs['guest_ms']<=50
        pending.clear()
        session.values['done']=1  # An intermediate match cannot finish the action.
        return {'outcome':'guest_time','guest_elapsed_ms':50,'hook_hits':[]}
    session.run=run
    result=SpatialActionHandle(session,'map1').interact(d)
    assert result['ok'] and len(seen)==2 and result['guest_elapsed_ms']==100
    assert len(result['runs'])==2


def test_drain_stop_prevents_later_input(session):
    d=action(); d['inputs']=[{'text':'get radio'},{'key':'enter'}]
    sent=[]; session.keyboard_type=lambda **kw: sent.append(kw) or {}
    session.keyboard_press=lambda **kw: sent.append(kw) or {}
    session.run=lambda **kwargs: {'outcome':'breakpoint'}
    result=SpatialActionHandle(session,'map1').interact(d)
    assert result['status']=='stopped' and len(sent)==1


def test_drain_consumes_budget_before_next_input(session):
    d=action(); d['inputs']=[{'text':'get radio'},{'key':'enter'}]; d['guest_ms']=50
    sent=[]; session.keyboard_type=lambda **kw: sent.append(kw) or {}
    session.keyboard_press=lambda **kw: sent.append(kw) or {}
    result=SpatialActionHandle(session,'map1').interact(d)
    assert not result['ok'] and len(sent)==1 and result['guest_elapsed_ms']==50
    assert 'budget expired' in result['error']


def test_story_guard_marker_covers_execution_and_rejects_nested_action(session):
    handle=SpatialActionHandle(session,'map1',mode='story')
    run=session.run
    def nested(**kwargs):
        assert session._spatial_guard_active is True
        before_presses=session.presses
        before_layers=list(session.active)
        refused=handle.interact(action())
        assert 'already active' in refused['error']
        assert session._spatial_guard_active is True
        assert session.presses==before_presses and session.active==before_layers
        return run(**kwargs)
    session.run=nested
    result=handle.interact(action())
    assert result['ok'] and session._spatial_guard_active is False
    session.stop=True
    result=handle.interact(action())
    assert result['status']=='stopped' and session._spatial_guard_active is False


def test_guard_marker_remains_if_restore_fails_and_close_fails(session):
    session.fail_restore=True
    def fail_close(): raise ValueError('close failed')
    session.close=fail_close
    result=SpatialActionHandle(session,'map1',mode='story').interact(action())
    assert not result['ok'] and not result['rollback']['ok']
    assert session._spatial_guard_failed is True and session._spatial_guard_active is True


def test_story_rejects_generic_execution_patch(session):
    d=action();d['spatial_guards']=[{'kind':'spatial','address':'1000:0000','expected_hex':'7502','data_hex':'9090',
       'provenance':{'source_sha256':'source','version_sha256':'version','evidence':'not-position'}}]
    result=SpatialActionHandle(session,'map1',mode='story').interact(d)
    assert not result['ok'] and session.presses==0 and session.active==['prior']


def test_story_rejects_matching_bytes_in_action_operands(session):
    # First six-byte pattern starts in an action operand; a genuine IF follows.
    source=bytes.fromhex('13007a0b000a0b141500ff0b000a0b1415ff000000')
    session.memory_bytes=bytearray(source)
    session._runtime_bindings['id']['length']=len(source)
    session._runtime_bindings['id']['expected_hex']=source[:2].hex()
    class Project:
        def file_bytes(self,name,offset,size,version):
            return {'bytes':source.hex(),'complete':True,'sha256':hashlib.sha256(source).hexdigest()}
    session.project=Project()
    d=action();d['spatial_guards'][0]['expected_hex']=source[3:9].hex()
    d['spatial_guards'][0]['data_hex']=source[3:5].hex()+'00009fa7'
    d['spatial_guards'][0]['provenance']['resource_sha256']=hashlib.sha256(source).hexdigest()
    result=SpatialActionHandle(session,'map1',mode='story').interact(d)
    assert 'decoded AGI position condition' in result['error'] and session.presses==0 and session.memory_bytes==source


def test_context_qualification_refuses_before_input(session):
    h=SpatialActionHandle(session,'map1',qualify_context=lambda:{'qualified':False})
    result=h.interact(action())
    assert 'context is not qualified' in result['error'] and session.presses==0


def test_context_change_after_guest_execution_restores_story_guard(session):
    checks=iter([{'qualified':True,'frame':'initial'}, {'qualified':False}])
    handle=SpatialActionHandle(session,'map1',mode='story',qualify_context=lambda:next(checks))
    original=bytes(session.memory_bytes)
    result=handle.interact(action())
    assert not result['ok'] and 'context is not qualified' in result['error']
    assert result['before']['map_context']=={'qualified':True,'frame':'initial'}
    assert len(result['runs'])==1 and session.presses==1 and session.memory_bytes==original
    assert result['resource_rollback'][0]['ok'] and session.active==['prior']
