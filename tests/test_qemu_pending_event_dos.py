"""DOS return sequencing with real helper verification and bounded QMP framing.

Only the native QMP/GDB/UART peers are authored; this does not qualify actual
QEMU or DOS execution, native throttle states, or held-key device behavior.
"""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull import dos_process_helper as helper
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_machine import QemuMachine
from fdisbull.qemu_observation_authority import ObservationAuthority, _Admission
from fdisbull.qemu_pending_events import COMMAND
from test_qemu_dos_async_resume import owned
from test_qemu_observation_cleanup import Process, Resource
from test_qemu_pending_events import Wire, line, response, event


class DOSWire(Wire):
    def __init__(self, peer):
        super().__init__()
        self.peer, self.events, self.cuts = peer, [], []
        self.on_cut = None

    def sendall(self, data):
        request = json.loads(data)
        self.requests.append(request)
        if request['execute'] == COMMAND:
            self.cuts.append(request)
            if self.on_cut is not None:
                self.on_cut()
            reply = response(deepcopy(self.events), request_id=request['id'], status=self.peer.runstate)
        else:
            value = self.peer.call(request['execute'], request.get('arguments'))
            reply = {'id':request['id'], 'return':value}
        self.buffer.extend(line(reply))


@pytest.fixture
def pending_dos(owned):
    o=owned
    # Keep production process/session behavior and cleanup. The OS process and
    # protocol channels remain authored, so no executable is started.
    vm=QemuMachine.__new__(QemuMachine)
    vm.__dict__.update(o.vm.__dict__)
    del vm.close
    vm.process, vm.closed = Process(), False
    vm.close_observer=o.session._on_machine_closed
    vm.transport='pipe'
    vm.qmp_commands=frozenset((COMMAND,))
    o.session.vm=o.session.rpc=vm
    o.vm=vm
    o.peer.socket=Resource('authored-gdb')
    wire=DOSWire(o.peer)
    qmp=QemuControl.__new__(QemuControl)
    qmp.socket,qmp.buffer,qmp.sequence=wire,bytearray(),0
    qmp.lock,qmp.operation_deadline=threading.Lock(),None
    vm.qmp=qmp
    vm.observation_authority=ObservationAuthority(vm)
    vm.observation_authority.bind(qmp=qmp,gdb=o.peer)
    o.wire,o.qmp,o.process,o.gdb_channel=wire,qmp,vm.process,o.peer.socket
    return o


@pytest.mark.parametrize(('category','outcome','process_state'),[
    (0,'guest_exit','exited'),(3,'guest_tsr','resident')])
def test_verified_return_cuts_after_classification_cleanup_and_tracker(pending_dos,category,outcome,process_state):
    o=pending_dos;s=o.session;revision=o.vm.session_revision
    s.resume();o.finish(category=category)
    o.wire.events=[event(offset=0),event(offset=0)]
    projections=[]
    def after(reason):
        assert s._process['state']==process_state and s._return_breakpoint is None
        temporary=s.breakpoint(0x20200)['breakpoint_id']
        s.delete_breakpoint(temporary)
        projections.append(revision.snapshot())
    s._automatic_runtime_tracker=SimpleNamespace(after_stop=after,
        status=lambda:{'observations':len(projections)},close=lambda reason:None)
    def at_cut():
        assert projections and s._dos_async_pending is None
        assert s._return_breakpoint is None and not o.peer.points
        assert s._process['state']==process_state and o.serial.reads==1
    o.wire.on_cut=at_cut
    result=s.status()
    assert len(o.wire.cuts)==1 and result['process_stop']['outcome']==outcome
    assert result['process']['state']==process_state and result['state']=='stopped'
    assert result['automatic_runtime_tracking']=={'observations':1}
    assert result['state_revision']==projections[-1]['state_revision']+2
    assert {key:result[key] for key in revision.snapshot()}==revision.snapshot()
    assert o.wire.requests[-1]['execute']==COMMAND
    assert not o.process.terminates and not o.wire.closed


def test_verified_layer_return_closes_and_never_cuts_or_queries_after_cleanup(pending_dos):
    o=pending_dos;s=o.session;revision=o.vm.session_revision
    s.resume();s._layer_active=['authored-layer'];o.finish()
    at_close=[]
    original=o.vm.close_observer
    def closed():
        at_close.append((len(o.wire.requests),len(o.peer.requests),len(o.peer.reads)))
        original()
    o.vm.close_observer=closed
    result=s.status()
    assert result['state']=='closed' and result['process_stop']['outcome']=='guest_exit'
    assert result['process']['machine_closed'] is True and o.wire.cuts==[]
    assert at_close==[(len(o.wire.requests),len(o.peer.requests),len(o.peer.reads))]
    assert {key:result[key] for key in revision.snapshot()}==revision.snapshot()
    assert o.process.terminates==o.process.waits==1 and not o.process.kills
    assert o.wire.closed==o.gdb_channel.closes==1
    assert o.vm.qmp is None and o.vm.gdb is None


@pytest.mark.parametrize('fault',['ready-only','nonce','serial-mismatch','serial-missing','identity'])
def test_helper_pc_or_unverified_return_never_authorizes_cut(pending_dos,fault):
    o=pending_dos;s=o.session;p=o.peer
    s.resume()
    if fault=='ready-only':
        p.cs,p.ip=0x1800,s._ready['exit_wait_ip']
        p.running,p.runstate=False,'debug'
        o.serial.data.extend(s._ready_bytes)
    else:
        o.finish(serial=fault!='serial-missing')
        if fault=='nonce':
            # The first byte of the full report nonce is bound by parse_report.
            offset=8
            p.ram[o.report_address+offset]^=1
            o.serial.data[offset]^=1
        elif fault=='serial-mismatch':o.serial.data[helper.REPORT_FIELDS['dos_result']]^=1
        elif fault=='identity':
            offset=helper.REPORT_FIELDS['child_psp']
            p.ram[o.report_address+offset]^=1;o.serial.data[offset]^=1
    with pytest.raises((DebuggerError,ValueError,TimeoutError)):s.status()
    assert o.wire.cuts==[] and o.process.terminates==o.process.waits==1
    assert o.wire.closed==o.gdb_channel.closes==1
    assert s._process['termination'] is None


def test_nonreturn_async_stop_defers_cut_until_later_ordinary_status(pending_dos):
    o=pending_dos;s=o.session
    s.resume();o.peer.running=False;o.peer.runstate='paused'
    result=s.status()
    assert result['process']['state']=='active' and o.wire.cuts==[]
    assert 'process_stop' not in result and s._dos_async_pending is None
    later=s.status()
    assert later['process']['state']=='active' and len(o.wire.cuts)==1
    assert o.serial.reads==0 and not o.process.terminates


def test_late_process_projection_replacement_refuses_without_foreign_access(pending_dos,monkeypatch):
    o=pending_dos;s=o.session
    s.resume();o.finish()
    import fdisbull.qemu_dos_process as module
    original=module.deepcopy
    foreign=SimpleNamespace(operation_deadline=123)
    changed=[]
    def copy(value,*args,**kwargs):
        result=original(value,*args,**kwargs)
        if value is s._process and getattr(s,'_dos_async_pending',None) is None and not changed:
            changed.append(True);s.vm=foreign
        return result
    monkeypatch.setattr(module,'deepcopy',copy)
    with pytest.raises(DebuggerError):s.status()
    assert changed and o.wire.cuts==[] and foreign.__dict__=={'operation_deadline':123}
    assert o.process.terminates==o.process.waits==1
    assert o.wire.closed==o.gdb_channel.closes==1


def test_cut_callback_reentering_foreign_public_operation_is_fenced(pending_dos,monkeypatch):
    o=pending_dos;s=o.session
    s.resume();o.finish();o.wire.events=[event(),event()]
    original=_Admission.event
    foreign=SimpleNamespace(operation_deadline=123)
    callbacks=[]
    def delivered(admission,value):
        callbacks.append(value);original(admission,value)
        s.vm=foreign
        s.registers()
    monkeypatch.setattr(_Admission,'event',delivered)
    with pytest.raises(DebuggerError) as caught:s.status()
    assert len(callbacks)==1 and foreign.__dict__=={'operation_deadline':123}
    assert caught.value.pending_events['batch_callbacks_started']==1
    assert caught.value.pending_events['batch_callbacks_returned']==0
    assert o.process.terminates==o.process.waits==1
