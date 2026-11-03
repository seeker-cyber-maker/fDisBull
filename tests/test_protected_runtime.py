"""Protected DOS RAM contracts through the existing observation peer seam."""
import base64
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from fdisbull.runtime_observations import RuntimeMemoryWriteError
from fdisbull.dosbox_rpc import DebuggerError
from test_runtime_observations import Session


ADDRESS=0x240010


class ProtectedSession(Session):
    backend_name='dosbox-x'

    def __init__(self,*,paging=False):
        super().__init__()
        self.ram={};self.calls=[];self.revision=1;self.closed=False;self.close_count=0
        self.write_fault=None;self.after_read=None;self.after_write=None
        self.context_missing=False
        self.set_mode('protected',paging=paging)

    def set_mode(self,mode,*,paging=False):
        self.mode=mode
        self.address_context=dict(cpu_mode=mode,paging_enabled=paging,
            cr0=hex((1 if mode in ('protected','v86') else 0)|(0x80000000 if paging else 0)),
            cr3='0x2000' if paging else '0x0',cr4='0x0',a20_enabled=True,
            code_bits=32 if mode=='protected' else 16,stack_bits=32 if mode=='protected' else 16)

    def seed(self,space,address,data):
        for index,byte in enumerate(data):self.ram[space,address+index]=byte

    def bytes_at(self,space,address,length):
        return bytes(self.ram.get((space,address+index),0) for index in range(length))

    def call(self,method,params=None):
        self.calls.append((method,deepcopy(params)))
        if method=='session.status':return {'state':'stopped' if self.stopped else 'running','state_revision':self.revision}
        if method=='state.get_registers':
            return {'cpu_mode':self.mode,**({} if self.context_missing else {'address_context':deepcopy(self.address_context)})}
        if method=='memory.read':
            address=int(params['address']['offset'],16);space=params['address']['space']
            data=self.bytes_at(space,address,params['length'])
            callback,self.after_read=self.after_read,None
            if callback is not None:callback()
            return {'data_base64':base64.b64encode(data).decode()}
        if method=='memory.write':
            address=int(params['address']['offset'],16);space=params['address']['space']
            data=base64.b64decode(params['data_base64'],validate=True)
            assert params['expected_sha256']==hashlib.sha256(self.bytes_at(space,address,len(data))).hexdigest()
            self.seed(space,address,data);self.revision+=1
            if self.after_write is not None:self.after_write()
            if self.write_fault=='timeout':raise TimeoutError('Authored write acknowledgment lost after dispatch')
            if self.write_fault=='corrupt':self.seed(space,address,bytes([data[0]^255])+data[1:])
            return {'written':len(data)}
        raise AssertionError('Unexpected runtime operation '+method)

    def _event(self,name,result):self.events.append((name,deepcopy(result)))
    def close(self):self.closed=True;self.close_count+=1
    def save_state(self,*args,**kwargs):raise AssertionError('Live RAM edit attempted state save')
    def load_state(self,*args,**kwargs):raise AssertionError('Live RAM edit attempted state restore')


def bind(session,*,space='linear'):
    session.seed(space,ADDRESS,b'AB\x12\x34')
    return session.bind_runtime_memory('allocation',ADDRESS,length=4,expected_hex='4142',
        provenance={'source':'authored RAM witness; no source mapping'},space=space)


def reads(session):return [params for method,params in session.calls if method=='memory.read']
def writes(session):return [params for method,params in session.calls if method=='memory.write']


def test_unpaged_protected_linear_binding_reads_above_real_mode_limit():
    session=ProtectedSession();binding=bind(session)
    result=session.runtime_memory(binding['id'],offset=2,length=2)
    assert result['hex']=='1234' and binding['address']==ADDRESS
    assert binding['observed_cpu_mode']=='protected'
    assert binding['identity']['memory_context']==dict(space='linear',cpu_mode='protected',paging_enabled=False,a20_enabled=True)
    assert all(item['address']['space']=='linear' for item in reads(session))
    assert reads(session)[0]['address']['offset']=='0x00240010'


def test_paged_linear_binding_refuses_before_any_memory_read_or_binding():
    session=ProtectedSession(paging=True)
    with pytest.raises(ValueError,match='Paged linear bindings'):bind(session)
    assert not reads(session) and not writes(session) and not session._runtime_bindings


def test_explicit_physical_binding_survives_translation_and_cpu_mode_changes_between_reads():
    session=ProtectedSession(paging=True);binding=bind(session,space='physical')
    for mode,paging in [('protected',True),('real',False),('v86',True)]:
        session.set_mode(mode,paging=paging)
        result=session.runtime_memory(binding['id'],offset=2,length=2)
        assert result['hex']=='1234' and result['identity']==binding['identity']
    assert all(item['address']['space']=='physical' for item in reads(session))
    assert binding['identity']['memory_context']['space']=='physical'


def test_linear_binding_without_observed_protected_context_refuses_before_read():
    session=ProtectedSession();session.context_missing=True
    with pytest.raises(ValueError,match='observed address_context'):bind(session)
    assert not reads(session)


@pytest.mark.parametrize('change',['mode','a20'])
def test_linear_binding_rejects_changed_address_context_before_read(change):
    session=ProtectedSession();bind(session);session.calls.clear()
    if change=='mode':session.set_mode('real')
    else:session.address_context['a20_enabled']=False
    with pytest.raises(ValueError,match='context changed'):session.runtime_memory('allocation',length=1)
    assert not reads(session)


def test_context_change_during_bind_cannot_publish_a_binding():
    session=ProtectedSession();session.after_read=lambda:session.set_mode('real')
    with pytest.raises(ValueError,match='observation_cpu_mode changed'):bind(session)
    assert not session._runtime_bindings and not session.events


def test_witness_change_and_epoch_invalidation_refuse_without_data_view():
    session=ProtectedSession();binding=bind(session)
    session.seed('linear',ADDRESS,b'ZZ');session.calls.clear()
    with pytest.raises(ValueError,match='witness mismatch'):session.runtime_memory('allocation',offset=2,length=2)
    assert len(reads(session))==1
    session._invalidate_runtime_bindings();session.calls.clear()
    with pytest.raises(ValueError,match='invalidated'):session.runtime_memory(binding['id'],length=1)
    assert not reads(session)


@pytest.mark.parametrize('space,paging',[('linear',False),('physical',True)])
def test_guarded_live_write_verifies_readback_without_state_restore(space,paging):
    session=ProtectedSession(paging=paging);binding=bind(session,space=space)
    result=session.write_runtime_memory('allocation','aabb',offset=2,expected_hex='1234')
    assert result['verified'] and result['dispatch_outcome']=='readback-verified'
    assert result['before_hex']=='1234' and result['after_hex']=='aabb'
    assert result['state_restore_used'] is False and result['frame_presentation_verified'] is False
    assert result['binding_invalidated'] is False and not session.closed
    assert session.runtime_memory(binding['id'],offset=2,length=2)['hex']=='aabb'
    assert len(writes(session))==1 and writes(session)[0]['address']['space']==space


def test_wrong_expected_live_bytes_refuse_before_write_dispatch():
    session=ProtectedSession();bind(session)
    with pytest.raises(ValueError,match='expected bytes mismatch'):
        session.write_runtime_memory('allocation','aabb',offset=2,expected_hex='ffff')
    assert not writes(session) and not session.closed
    assert not any(name=='runtime-memory-write-attempt' for name,result in session.events)


def test_live_write_consuming_witness_invalidates_binding_after_verified_commit():
    session=ProtectedSession();binding=bind(session)
    result=session.write_runtime_memory('allocation','4344',expected_hex='4142')
    assert result['verified'] and result['binding_invalidated']
    assert session.bytes_at('linear',ADDRESS,4)==b'CD\x12\x34' and not session.closed
    with pytest.raises(ValueError,match='invalidated'):session.runtime_memory(binding['id'],length=1)


@pytest.mark.parametrize('fault',['timeout','corrupt','epoch','context'])
def test_uncertain_or_mismatched_dispatched_write_closes_without_replay(fault):
    session=ProtectedSession();bind(session)
    if fault in ('timeout','corrupt'):session.write_fault=fault
    elif fault=='epoch':session.after_write=session._invalidate_runtime_bindings
    else:session.after_write=lambda:session.address_context.update(a20_enabled=False)
    with pytest.raises(RuntimeMemoryWriteError) as failed:
        session.write_runtime_memory('allocation','aabb',offset=2,expected_hex='1234')
    assert session.closed and session.close_count==1 and len(writes(session))==1
    receipt=failed.value.result
    assert receipt['dispatch_outcome']=='unknown' and not receipt['verified']
    assert receipt['state_restore_used'] is False
    assert [name for name,result in session.events][-1]=='runtime-memory-write-unknown'


class ProtectedCheckpoint(ProtectedSession):
    """Borrow the public debugger checkpoint methods without an emulator."""
    def __init__(self):
        super().__init__()
        self.rpc=SimpleNamespace(capabilities={'save_states':True})
        self.metadata=dict(self.metadata,emulator_sha256='emulator',runtime_load_segment=0x1000,
                           runtime_profile='authored-project-profile',game_dir='owned-fixture')
        self._layers=[];self._ram_base={};self._ram_applied={}
        self.load_fault=None;self.layer_setup_calls=0

    def registers(self):
        return dict(cpu_mode=self.mode,address_context=deepcopy(self.address_context),
            general={'eax':'0x1','ebx':'0x2'},segments={'cs':'0x8','ds':'0x10','ss':'0x10'},
            instruction_pointer='0x123456',flags='0x202')

    def _disk_manifest(self):return []
    def _layer_state(self):return dict(active=list(self._layers),ram_applied=deepcopy(self._ram_applied))
    def _layer_setup(self):self.layer_setup_calls+=1
    def _view(self,*args,**kwargs):raise AssertionError('Protected restore entered real-mode source view')
    def _restore_layer_state(self,*args,**kwargs):raise AssertionError('Protected restore entered real-mode layer restoration')

    def call(self,method,params=None):
        if method in ('state.save','state.load','input.mouse.state'):
            self.calls.append((method,deepcopy(params)))
            if method=='input.mouse.state':return {'mouse':{}}
            if method=='state.save':
                Path(params['path']).write_bytes(b'owned-native-checkpoint')
                return {'saved':True}
            assert Path(params['path']).read_bytes()==b'owned-native-checkpoint'
            self.set_mode('protected')
            if self.load_fault=='mode':self.set_mode('real')
            elif self.load_fault=='context':self.address_context['a20_enabled']=False
            return {'loaded':True}
        return super().call(method,params)


def checkpoint(session):
    from fdisbull.debugger import DebugSession
    return DebugSession._capture_native_checkpoint(session)


@pytest.mark.parametrize('layers,ram', [(['active-layer'],{}),([],{0x10000:7})])
def test_protected_capture_refuses_real_mode_layers_before_native_state_save(layers,ram):
    session=ProtectedCheckpoint();session._layers=layers;session._ram_applied=ram
    with pytest.raises(ValueError,match='real-mode code layers'):checkpoint(session)
    assert not any(method=='state.save' for method,params in session.calls)
    assert not session.closed


@pytest.mark.parametrize('layers,ram', [(['active-layer'],{}),([],{0x10000:7})])
def test_protected_saved_layer_state_refuses_before_native_state_load(layers,ram):
    from fdisbull.debugger import DebugSession
    session=ProtectedCheckpoint();saved=checkpoint(session);session.calls.clear()
    saved['metadata']['code_layers']={'active':layers,'ram_applied':ram}
    with pytest.raises(ValueError,match='cannot restore real-mode code layers'):
        DebugSession._restore_native_checkpoint(session,saved)
    assert not any(method=='state.load' for method,params in session.calls)
    assert not session.closed


@pytest.mark.parametrize('fault,field',[('mode','cpu_mode'),('context','address_context')])
def test_post_load_protected_context_mismatch_closes_owned_guest(fault,field):
    from fdisbull.debugger import DebugSession
    session=ProtectedCheckpoint();saved=checkpoint(session);session.load_fault=fault
    with pytest.raises(DebuggerError,match=field):DebugSession._restore_native_checkpoint(session,saved)
    assert session.closed and session.close_count==1
    assert len([method for method,params in session.calls if method=='state.load'])==1


def test_empty_layer_protected_restore_bypasses_real_mode_view_and_invalidates_runtime_bindings():
    from fdisbull.debugger import DebugSession
    session=ProtectedCheckpoint();binding=bind(session);saved=checkpoint(session)
    previous_epoch=session._runtime_epoch
    session._layers=['old-live-layer'];session._ram_base={1:2};session._ram_applied={1:3}
    session._keyboard_leases={'old':'right'}
    result=DebugSession._restore_native_checkpoint(session,saved)
    assert result['registers']['cpu_mode']=='protected' and not session.closed
    assert result['intervention']['kind']=='full-native-checkpoint-restore'
    assert session._layers==[] and session._ram_base==session._ram_applied=={}
    assert session.layer_setup_calls==1 and session._keyboard_leases=={}
    assert session._runtime_epoch!=previous_epoch
    with pytest.raises(ValueError,match='invalidated'):session.runtime_memory(binding['id'],length=1)


@pytest.mark.parametrize('changes',[
    {'data_hex':'0g'},
    {'expected_hex':'zz'},
    {'data_hex':'0001'},
    {'data_hex':'$earlier.hex','expected_hex':'invalid'},
    {'expected_hex':''},
    {'offset':-1},
    {'offset':True},
    {'offset':65536},
])
def test_malformed_later_live_write_is_rejected_before_any_script_operation(changes):
    from fdisbull.debug_script import execute_script
    session=ProtectedSession()
    def forbidden(*args,**kwargs):pytest.fail('Malformed script reached a guest operation or artifact storage')
    session.registers=forbidden;session._artifact=forbidden
    step={'op':'write-runtime-memory','binding':'allocation','data_hex':'00','expected_hex':'00',**changes}
    with pytest.raises(ValueError):
        execute_script(session,{'format':'fdisbull-script-1','steps':[{'op':'registers'},step]})
    assert not session.calls and not session.events


def test_loaded_edited_fork_provenance_survives_protected_recapture():
    from fdisbull.debugger import DebugSession
    session=ProtectedCheckpoint();saved=checkpoint(session)
    derivation={'kind':'authored-assisted-fork','parent_artifact':'retained-parent','edits':{'memory':['declared edit']}}
    saved['metadata']['derivation']=derivation
    DebugSession._restore_native_checkpoint(session,saved)
    assert session._state_provenance==derivation
    recaptured=checkpoint(session)
    assert recaptured['metadata']['derivation']==derivation


def test_loading_normal_protected_state_clears_previous_fork_provenance():
    from fdisbull.debugger import DebugSession
    session=ProtectedCheckpoint();saved=checkpoint(session)
    session._state_provenance={'kind':'unrelated-earlier-edit'}
    result=DebugSession._restore_native_checkpoint(session,saved)
    assert not result['intervention']['edited_fork'] and not hasattr(session,'_state_provenance')
    assert 'derivation' not in checkpoint(session)['metadata']
