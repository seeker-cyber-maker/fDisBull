"""CHIP-8 frame key ownership contracts against a stopped fake QMP peer."""
from copy import deepcopy
import pytest
from fdisbull.chip8_keys import KEY_SUBSET,KEY_ENV,KEY_MODEL,validate_edges,validate_schedule,validate_key_snapshot
from fdisbull.dosbox_rpc import DebuggerError
from test_chip8_layers import machine
from test_chip8_history import project


def key_machine():
    s,add,layer,env=machine();s.identity['cpu_subset']=KEY_SUBSET;s.vm.fault['cpu-subset']=KEY_SUBSET
    env.update({'cpu-subset':KEY_SUBSET,'env-model':KEY_ENV});s.vm._chip8_key_owner=None
    s._chip8_frame_idle=lambda:None
    info={'model':KEY_MODEL,'subset':KEY_SUBSET,'environment-model':KEY_ENV,'epoch':1,'active':False,
          'valid':True,'needs-adoption':False,'generation':0,'accepted-edges':0,'held-mask':0,'key-mask':0,
          'state-generation':env['state-generation'],'token':'','held':[],'edge-capacity':16,'repeat-supported':False}
    calls=[];old=s.vm.qmp.call
    def call(method,args=None,**kwargs):
        calls.append((method,deepcopy(args)))
        if method=='query-chip8-frame-keys':return deepcopy(info)
        if method=='x-chip8-apply-frame-key-edges':
            assert args['expected-generation']==info['generation'] and args['expected-state-generation']==info['state-generation']
            mask=info['held-mask']
            for edge in args['edges']:
                bit=1<<int(edge['key'],16);mask=(mask|bit) if edge['pressed'] else (mask&~bit)
            info.update(active=True,token=args['token'],generation=info['generation']+1,
                        **{'held-mask':mask,'key-mask':mask,'state-generation':info['state-generation']+1,
                           'accepted-edges':info['accepted-edges']+len(args['edges']),
                           'held':[k for k in '0123456789abcdef' if mask&(1<<int(k,16))]})
            env.update({'state-generation':info['state-generation'],'key-mask':mask})
            return deepcopy(info)
        if method=='x-chip8-detach-frame-keys':
            assert not info['held-mask'] and args['token']==info['token'] and args['expected-generation']==info['generation']
            info.update(active=False,token='',generation=info['generation']+1);return deepcopy(info)
        if method=='x-chip8-adopt-frame-keys':
            assert info['needs-adoption'] and args['held-mask']==info['held-mask']
            info.update(token=args['token'],generation=info['generation']+1,**{'needs-adoption':False});return deepcopy(info)
        return old(method,args,**kwargs)
    s.vm.qmp.call=call
    return s,info,env,calls


def test_edge_ownership_manual_interlock_and_checked_detach():
    s,info,env,calls=key_machine()
    result=s.frame_inputs([{'key':'a','pressed':True},{'key':'0','pressed':True}])
    assert result['held']==['0','a'] and result['native']['accepted-edges']==2
    with pytest.raises(ValueError,match='Release'):s._chip8_key_before_manual()
    s.frame_inputs([{'key':'a','pressed':False},{'key':'0','pressed':False}])
    before=info['accepted-edges'];s._chip8_key_before_manual()
    assert not info['active'] and info['accepted-edges']==before and s.vm._chip8_key_owner is None


def test_unjournaled_native_mutation_is_detected():
    s,info,env,calls=key_machine();s.frame_inputs([{'key':'a','pressed':True}])
    info.update(generation=info['generation']+1,**{'held-mask':3,'key-mask':3,'held':['0','1'],'accepted-edges':2})
    with pytest.raises(DebuggerError,match='ownership differs'):s._chip8_keys_query()


def test_cold_adoption_rotates_token_without_key_edges():
    s,info,env,calls=key_machine();s.frame_inputs([{'key':'f','pressed':True}]);saved=s._chip8_key_snapshot()
    s.vm._chip8_key_owner=None;info.update(epoch=2,token='',**{'needs-adoption':True})
    adopted=s._chip8_key_adopt(saved)
    assert adopted['epoch']==2 and adopted['generation']==saved['generation']+1
    assert adopted['held']==['f'] and adopted['accepted-edges']==saved['accepted-edges']
    assert adopted['state-generation']==saved['state-generation']
    assert [name for name,_ in calls].count('x-chip8-apply-frame-key-edges')==1


def test_edge_and_schedule_validation_and_snapshot_consistency():
    for invalid in ([{'key':'g','pressed':True}],[{'key':'A','pressed':True}],
                    [{'key':'0','pressed':1}],[{'key':'0','pressed':True},{'key':'0','pressed':False}]):
        with pytest.raises(ValueError):validate_edges(invalid)
    validate_schedule([{'frame':0,'edges':[{'key':'a','pressed':True}]}],1)
    with pytest.raises(ValueError):validate_schedule([{'frame':1,'edges':[]}],1)
    with pytest.raises(ValueError):validate_key_snapshot({'epoch':1,'active':True,'generation':1,'accepted-edges':1,
        'held-mask':1,'key-mask':1,'state-generation':2},{'key-mask':0,'state-generation':2})


def test_caller_transaction_refuses_before_frame_key_rpc():
    s,info,env,calls=key_machine();s.project.db.in_transaction=True
    with pytest.raises(ValueError,match='transaction'):s.frame_inputs([{'key':'1','pressed':True}])
    assert not calls and not s.closed


class KeyFrameHarness:
    """Real FDB timeline with an authored stopped native-key stub."""
    pass


def test_scheduled_edges_preflight_dirty_rewind_and_cold_restore(project):
    from types import SimpleNamespace
    from test_chip8_frames import FrameHarness
    from fdisbull.chip8_keys import Chip8KeysMixin
    from fdisbull.chip8_history import KEY_STATE_FORMAT
    from fdisbull.qemu_chip8 import Chip8DebugSession
    import json,uuid
    class S(Chip8KeysMixin,FrameHarness):
        _budget=Chip8DebugSession._budget
        def __init__(self,p,run):
            super().__init__(p,run);self.identity['cpu_subset']=KEY_SUBSET;self.capabilities['frame_key_ownership']=True
            self.vm._chip8_key_owner=None;self._event=lambda *args:None
            self.key={'model':KEY_MODEL,'subset':KEY_SUBSET,'environment-model':KEY_ENV,'epoch':1,'active':False,
                'valid':True,'needs-adoption':False,'generation':0,'accepted-edges':0,'held-mask':0,'key-mask':0,
                'state-generation':0,'token':'','held':[],'edge-capacity':16,'repeat-supported':False}
            self.vm.qmp=SimpleNamespace(call=self.call,operation_deadline=None)
        def call(self,method,args=None,**kwargs):
            if method=='query-chip8-frame-keys':
                self.key['state-generation']=self.generation;return deepcopy(self.key)
            if method=='x-chip8-apply-frame-key-edges':
                mask=self.key['held-mask']
                for edge in args['edges']:
                    bit=1<<int(edge['key'],16);mask=(mask|bit) if edge['pressed'] else (mask&~bit)
                self.generation+=1
                self.key.update(active=True,token=args['token'],generation=self.key['generation']+1,
                    **{'held-mask':mask,'key-mask':mask,'state-generation':self.generation,
                       'accepted-edges':self.key['accepted-edges']+len(args['edges']),
                       'held':[k for k in '0123456789abcdef' if mask&(1<<int(k,16))]})
                return deepcopy(self.key)
            raise AssertionError(method)
        def _frame_admit(self,*,future_mask=None,will_apply=False):
            if self._chip8_hook_pending is not None:raise ValueError('pending hook')
        def chip8_environment(self,**kwargs):
            return super().chip8_environment(**kwargs)|{'key-mask':self.key['key-mask']}
        def save_state(self,name,*,max_bytes=None,timeout_ms=60000):
            state={'pc':self.pc,'tick':self.tick,'phase':self.phase,'deadline':self.deadline,'now':self.now,'generation':self.generation}
            data=json.dumps(state).encode();environment=self.chip8_environment();keys=self._chip8_key_snapshot()
            return self.project._debug_artifact(self.run_id,name,'state',data,
                    {'format':KEY_STATE_FORMAT,'identity':self.identity,'host_files_restored':False,'environment':environment,'key_state':keys})
        def load_state(self,artifact,*,timeout_ms=60000):
            row=self.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
            data=json.loads(bytes(row['data']));keys=json.loads(row['metadata'])['key_state']
            for field in ('pc','tick','phase','deadline','now','generation'):setattr(self,field,data[field])
            epoch=self.key['epoch']+1;token=uuid.uuid4().hex if keys['active'] else ''
            self.key.update(epoch=epoch,active=keys['active'],token=token,generation=keys['generation']+int(keys['active']),
                **{'accepted-edges':keys['accepted-edges'],'held-mask':keys['held-mask'],'key-mask':keys['key-mask'],
                   'held':[k for k in '0123456789abcdef' if keys['held-mask']&(1<<int(k,16))]})
            self.vm._chip8_key_owner=(epoch,token,self.key['generation'],keys['accepted-edges'],keys['held-mask']) if keys['active'] else None
            self.vm.history_epoch=uuid.uuid4().hex;return {'host_files_restored':False}
    s=S(project,'keys');root=s.timeline_start(max_frames=6,max_bytes=100000,max_state_bytes=4096,max_image_bytes=4096)
    before=project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]
    with pytest.raises(ValueError,match='already'):s.timeline_advance(frames=2,inputs=[
        {'frame':0,'edges':[{'key':'a','pressed':True}]},{'frame':1,'edges':[{'key':'a','pressed':True}]}])
    assert project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='rewind-history'").fetchone()[0]==before
    assert not s.key['active']
    receipt=s.frame_inputs([{'key':'a','pressed':True}]);assert receipt['held']==['a']
    assert s.timeline_status()['input_dirty']
    with pytest.raises(ValueError,match='dirty'):s.timeline_pin()
    s.timeline_rewind(frames=0);assert s.keyboard_state()['keyboard']['frame_keys']==[]
    sample=s.timeline_advance(frames=2,inputs=[{'frame':0,'edges':[{'key':'a','pressed':True}]},
                                               {'frame':1,'edges':[{'key':'a','pressed':False}]}])
    assert [n['frame']['keys'] for n in sample['nodes']]==[[],['a'],[]]
    first=sample['nodes'][1]['id'];s.timeline_rewind(point=first,frames=0)
    assert s.keyboard_state()['keyboard']['frame_keys']==['a']


def test_active_snapshot_with_exhausted_adoption_generation_refuses():
    saved={'epoch':1,'active':True,'generation':(1<<64)-1,'accepted-edges':1,'held-mask':1,'key-mask':1,'state-generation':2}
    with pytest.raises(ValueError):validate_key_snapshot(saved,{'key-mask':1,'state-generation':2})


def test_manual_keypad_refuses_active_fence_before_owner_or_history_changes():
    s,info,env,calls=key_machine();s._qemu_history_live={'valid':True,'cursor':'unchanged'}
    def busy():raise ValueError('CHIP-8 frame fence is active')
    s._chip8_frame_idle=busy
    with pytest.raises(ValueError,match='fence'):s.chip8_keypad([])
    assert not calls and not s.closed and s._qemu_history_live=={'valid':True,'cursor':'unchanged'}


@pytest.mark.parametrize('field',['generation','accepted-edges'])
def test_active_snapshot_requires_prior_claim_and_edge(field):
    saved={'epoch':1,'active':True,'generation':1,'accepted-edges':1,'held-mask':1,'key-mask':1,'state-generation':2}
    saved[field]=0
    with pytest.raises(ValueError):validate_key_snapshot(saved,{'key-mask':1,'state-generation':2})


def test_manual_keypad_failure_reports_prior_checked_detach():
    s,info,env,calls=key_machine()
    s.frame_inputs([{'key':'0','pressed':True}]);s.frame_inputs([{'key':'0','pressed':False}])
    call=s.vm.qmp.call
    def fail_set(method,args=None,**kwargs):
        if method=='x-chip8-set-keys':raise DebuggerError('lost keypad reply')
        return call(method,args,**kwargs)
    s.vm.qmp.call=fail_set
    with pytest.raises(DebuggerError) as raised:s.chip8_keypad([1])
    assert s.closed and raised.value.result['key_detach']['active'] is False
    assert raised.value.result['cause_result']['disposition'].endswith('do not replay')
