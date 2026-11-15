"""Automatic lifecycle integration at real RPC/GDB seams; no guest or probe."""
import socket
import threading
import time
from types import SimpleNamespace
import pytest
from fdisbull.debugger import DebugSession, _attach_runtime_tracking
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote


class Recorder:
    def __init__(self,order):self.order=order;self.fail=False;self.session=None;self.recurse=False
    def before_execution(self,reason):
        self.order.append(('before',reason))
        if self.fail:raise ValueError('invalidation failed')
    def after_stop(self,reason):
        self.order.append(('after',reason))
        if self.recurse:DebugSession.call(self.session,'execution.wait')
    def close(self,reason):self.order.append(('close',reason))
    def status(self):return {'state':'recorded-status'}


def session(result=None):
    order=[];result=result if result is not None else {'state':'stopped','running':False}
    class RPC:
        def call(self,method,params,**kwargs):order.append(('rpc',method));return result
    value=SimpleNamespace(closed=False,session_id='owned-native-session',rpc=RPC(),metadata={})
    value._automatic_runtime_tracker=Recorder(order);value._automatic_runtime_tracker.session=value
    return value,order,result


def test_rpc_invalidation_precedes_dispatch_and_stopped_wait_observes_after():
    value,order,result=session()
    assert DebugSession.call(value,'execution.continue') is result
    assert order==[('before','execution.continue'),('rpc','execution.continue')]
    DebugSession.call(value,'execution.wait')
    assert order[-2:]==[('rpc','execution.wait'),('after','execution.wait')]
    assert result=={'state':'stopped','running':False}


@pytest.mark.parametrize('method',['input.keyboard.press','input.mouse.click','input.mouse.move','memory.write','state.set_register','state.load'])
def test_all_native_mutation_paths_invalidate_before_dispatch(method):
    value,order,_=session();DebugSession.call(value,method)
    assert order[:2]==[('before',method),('rpc',method)]


def test_running_wait_and_read_only_queries_never_publish_a_stop():
    value,order,_=session({'state':'running','running':True})
    for method in ['execution.wait','state.get_registers','memory.read','input.keyboard.state']:
        DebugSession.call(value,method)
    assert all(kind=='rpc' for kind,_ in order)


def test_observer_reads_do_not_recursively_observe_themselves():
    value,order,_=session();value._automatic_runtime_tracker.recurse=True
    DebugSession.call(value,'execution.wait')
    assert order==[('rpc','execution.wait'),('after','execution.wait'),('rpc','execution.wait')]


def test_failed_invalidation_dispatches_nothing_and_is_not_retried():
    value,order,_=session();value._automatic_runtime_tracker.fail=True
    with pytest.raises(ValueError,match='invalidation failed'):DebugSession.call(value,'execution.continue')
    assert order==[('before','execution.continue')]


def test_owned_native_exit_closes_tracking_and_retains_native_evidence():
    native={'state':'exited','running':False,'stop_reason':{'kind':'guest_exit','guest_exit':{'psp':'0x2345'}}}
    value,order,_=session(native);assert DebugSession.call(value,'execution.wait') is native
    assert order[-1]==('close','native-target-exit')
    assert value._automatic_runtime_stop is native
    assert DebugSession.tracking_status(value)=={'state':'recorded-status'}


def test_tracker_attachment_is_once_and_observes_startup(monkeypatch):
    from fdisbull import runtime_tracking
    made=[];value=SimpleNamespace()
    def factory(given):
        made.append(given);return Recorder([])
    monkeypatch.setattr(runtime_tracking,'AutomaticRuntimeTracker',factory)
    _attach_runtime_tracking(value);_attach_runtime_tracking(value)
    assert made==[value]
    assert value._automatic_runtime_tracker.order==[('after','session-start')]


def test_outer_machine_without_parent_tracker_keeps_backend_context_unchanged():
    context=object()
    value=SimpleNamespace(project=object(),run_id='untracked-ne',rpc=SimpleNamespace(
        machine=SimpleNamespace(bind=lambda project,run:context)))
    assert DebugSession.machine.fget(value) is context


def test_owned_dos_outer_machine_still_invalidates_parent_before_execution():
    from fdisbull.qemu_machine import _before_machine_execution
    parent,order,_=session();parent.project=object();parent.run_id='owned-dos'
    context=SimpleNamespace()
    parent.rpc.machine=SimpleNamespace(bind=lambda project,run:context)
    assert DebugSession.machine.fget(parent) is context
    assert context._automatic_runtime_parent is parent
    _before_machine_execution(context,'machine-gdb-run')
    assert order==[('before','parent-machine-machine-gdb-run')]
