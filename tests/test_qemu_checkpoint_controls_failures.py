"""Primary failures survive uncertain native checkpoint cleanup."""
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_checkpoint_controls import restore_controls
from fdisbull import qemu_instrumented_checkpoint as instrumented
from fdisbull import qemu_layers
from test_qemu_hooks import Harness


def closing_session(vm, *, close_fails=True):
    session=SimpleNamespace(vm=vm,close_calls=0)
    def close():
        session.close_calls+=1
        if close_fails:raise RuntimeError('authored cleanup failure')
    session.close=close
    return session


def control_session(primary, *, close_fails=True):
    session=closing_session(SimpleNamespace(),close_fails=close_fails)
    session.project=SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    session.metadata={'source_sha256':'a'*64}
    session.version={'id':1,'sha256':'b'*64}
    session.capabilities={};session.breakpoints={}
    session._layer_active=[];session._layer_generation=0;session._layer_exec={}
    session._layer_epoch=lambda:2
    session._stopped=lambda:None
    session.breakpoint_calls=[]
    def breakpoint(address,**options):
        session.breakpoint_calls.append((address,options))
        raise primary
    session.breakpoint=breakpoint
    controls=dict(format='fdisbull-qemu-controls-1',run='original-run',epoch=1,
        source_sha256='a'*64,version=1,version_sha256='b'*64,
        active=[],definitions={},hooks=[],pending_hook=None,observed=[],
        maps={key:[] for key in ('ram_base','ram_applied','exec_base','exec')},
        breakpoints=[dict(id='user-breakpoint',address=0x1000,access='x',length=1)])
    return session,controls


@pytest.mark.parametrize('close_fails',[True,False])
def test_control_restore_retains_original_failure_after_mutation(close_fails):
    primary=OSError('authored breakpoint restoration failure')
    primary.result={'observed_stop':'retained'}
    original_result=primary.result
    session,controls=control_session(primary,close_fails=close_fails)
    with pytest.raises(OSError) as caught:restore_controls(session,controls,1)
    assert caught.value is primary and caught.value.result is original_result
    assert session.breakpoint_calls==[(0x1000,{'access':'x','length':1})]
    assert session.close_calls==1 and session.vm._fdisbull_control_quarantine
    if close_fails:assert primary.machine_cleanup_error=='RuntimeError'
    else:assert not hasattr(primary,'machine_cleanup_error')


def test_control_preflight_refusal_does_not_close_or_quarantine():
    session,controls=control_session(OSError('must not dispatch'))
    controls['epoch']=0
    with pytest.raises(ValueError,match='origin epoch'):restore_controls(session,controls,1)
    assert not session.breakpoint_calls and session.close_calls==0
    assert not hasattr(session.vm,'_fdisbull_control_quarantine')


def capture_session(*, error=None, value=None):
    calls=[]
    def call(command,**options):
        calls.append(command)
        if error is not None:raise error
        return value
    vm=SimpleNamespace(machine_configuration={'clock_profile':{'profile':'virtual'}},
                       qmp=SimpleNamespace(call=call))
    session=closing_session(vm)
    session._clock_snapshot=lambda:dict(counter={'value':7},virtual_ns=11,
                                      virtual_clock={'native':{'epoch':1}})
    return session,calls


@pytest.mark.parametrize('error_type',[OSError,DebuggerError])
def test_instrumented_export_retains_transport_error_and_result(error_type):
    primary=error_type('authored incomplete native export')
    primary.result={'native_observation':'retained'}
    original_result=primary.result
    session,calls=capture_session(error=primary)
    with pytest.raises(error_type) as caught:instrumented.capture(session)
    assert caught.value is primary and caught.value.result is original_result
    assert primary.machine_cleanup_error=='RuntimeError'
    assert session.close_calls==1 and session.vm._fdisbull_control_quarantine
    assert calls==[instrumented.PREFIX+'checkpoint-export']


@pytest.mark.parametrize('value,error_type,message',[
    ({'token':''},DebuggerError,'export token'),
    ({'token':'owned','state':'{}','sha256':'invalid'},ValueError,'state or hash'),
])
def test_instrumented_malformed_export_retains_validation_failure(value,error_type,message):
    session,calls=capture_session(value=value)
    with pytest.raises(error_type,match=message) as caught:instrumented.capture(session)
    assert caught.value.machine_cleanup_error=='RuntimeError'
    assert session.close_calls==1 and session.vm._fdisbull_control_quarantine
    assert calls==[instrumented.PREFIX+'checkpoint-export']


def test_instrumented_explicit_native_policy_refusal_preserves_live_owner():
    primary=DebuggerError('QMP '+instrumented.PREFIX+'checkpoint-export: authored policy refusal')
    session,calls=capture_session(error=primary)
    with pytest.raises(ValueError,match='Native instrumented checkpoint refused') as caught:
        instrumented.capture(session)
    assert caught.value.__cause__ is primary
    assert session.close_calls==0 and not hasattr(session.vm,'_fdisbull_control_quarantine')
    assert calls==[instrumented.PREFIX+'checkpoint-export']


@pytest.mark.parametrize('through_controls',[False,True])
def test_hook_publication_failure_survives_nested_cleanup(through_controls):
    primary=OSError('authored hook publication failure')
    primary.result={'hook_native_observation':'retained'}
    original_result=primary.result
    session=Harness()
    session.metadata={'source_sha256':'a'*64}
    session.version={'id':1,'sha256':'b'*64}
    session.breakpoints={};session._layer_active=[];session._layer_generation=0
    session._layer_exec={};session._layer_epoch=lambda:2;session._stopped=lambda:None
    session.close_calls=0
    def event(name,data):
        session.events.append((name,data))
        raise primary
    def close():
        session.close_calls+=1
        raise RuntimeError('authored nested cleanup failure')
    session._event=event;session.close=close
    actions=[{'op':'layers','layers':[]}]
    with pytest.raises(OSError) as caught:
        if through_controls:
            controls=dict(format='fdisbull-qemu-controls-1',run='original-run',epoch=1,
                source_sha256='a'*64,version=1,version_sha256='b'*64,
                active=[],definitions={},observed=[],pending_hook=None,breakpoints=[],
                maps={key:[] for key in ('ram_base','ram_applied','exec_base','exec')},
                hooks=[dict(hook='original-hook',epoch=1,hits=0,max_hits=1,
                    address=0x1000,runtime_address=0x1000,actions=actions,once=True,
                    cs=None,access='x',length=1,space='linear')])
            restore_controls(session,controls,1)
        else:
            session.hook(0x1000,actions=actions,space='linear')
    assert caught.value is primary and caught.value.result is original_result
    assert primary.machine_cleanup_error=='RuntimeError'
    assert session.vm._fdisbull_control_quarantine
    assert session.close_calls==(2 if through_controls else 1)
    assert session.points=={'bp-1':0x1000}
    assert [name for name,_ in session.events]==['hook-create']


@pytest.mark.parametrize('through_controls',[False,True])
@pytest.mark.parametrize('receipt',[
    {'generation':1,'execution-bytes':0},
    {'generation':0,'execution-bytes':1},
])
def test_invalid_layer_receipt_retains_intended_error_before_cleanup(
        monkeypatch,through_controls,receipt):
    message='QEMU layer state differs from the owned layer stack'
    primary=DebuggerError(message);primary.result={'native_receipt':receipt}
    original_result=primary.result;constructed=[];calls=[]
    def error(message):
        constructed.append(message)
        return primary
    monkeypatch.setattr(qemu_layers,'DebuggerError',error)
    session,controls=control_session(primary)
    def call(command,*args,**kwargs):
        calls.append(command)
        return receipt
    session.vm.qmp=SimpleNamespace(call=call)
    session._layer_native_observe=lambda **extent:qemu_layers.QemuLayerSessionMixin._layer_native_observe(session,**extent)
    definition=dict(version=1,name='authored execute layer',kind='execute',
        patches=[dict(address=0x1000,expected_hex='90',data_hex='cc')])
    session.capabilities={'code_layers':True}
    session.project.debug_layer_info=lambda _:definition
    session._layer_spans=lambda address,length,space,cs=None:(address,address,[(address,length)],{})
    session._layer_ram_extent=lambda address,length:None
    session._stopped=lambda:SimpleNamespace(memory=lambda address,length,**_:b'\x90'*length)
    controls.update(active=['execute-layer'],definitions={'execute-layer':definition},
        breakpoints=[],observed=[[0x1000,0x90]],
        maps=dict(ram_base=[],ram_applied=[],exec_base=[[0x1000,0x90]],exec=[[0x1000,0xcc]]))
    with pytest.raises(DebuggerError,match=message) as caught:
        if through_controls:restore_controls(session,controls,1)
        else:session._layer_native_observe()
    assert caught.value is primary and caught.value.result is original_result
    assert constructed==[message] and primary.machine_cleanup_error=='RuntimeError'
    assert session.close_calls==1 and session.vm._fdisbull_control_quarantine
    assert calls==['x-fdisbull-layer-observe']
