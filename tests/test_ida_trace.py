"""Bounded trace collection preserves completed-instruction evidence and stops."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from fdisbull.ida_remote import RemoteDebugger
from fdisbull.ida_trace import collect_trace
from fdisbull.ida_wire import ProtocolError, Reader, dd
from fdisbull import ida_wire as w


class CPU:
    def __init__(self, stop='step'):
        self.pc=0x1000;self.steps=0;self.reads=[];self.reg_reads=0
        self.pending={'tid':7,'eid':6};self.breakpoints={};self.scope=False;self.stop=stop
        self.last_state={'state':'stopped','stop_reason':{'kind':'step','thread':7,'native_event':dict(self.pending)}}

    @contextmanager
    def step_scope(self):
        self.scope=True
        try:yield
        finally:self.scope=False

    def registers(self):
        self.reg_reads+=1
        return dict.fromkeys(['rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','efl',*(f'r{i}' for i in range(8,16))],0) | {'rip':self.pc}

    def read_code(self, address):
        assert self.scope
        self.reads.append(address)
        # A second visit to the same address observes self-modified code.
        return b'\x90' if self.steps==0 else b'\x91'

    def step(self, timeout_ms):
        assert self.scope and timeout_ms>0
        self.steps+=1
        if self.stop=='timeout':raise TimeoutError('unfinished native step')
        self.last_state={'state':'stopped','stop_reason':{'kind':self.stop,'thread':7,'native_event':dict(self.pending)}}
        return self.last_state

    def breakpoint_boundary(self, pc):
        if self.breakpoints:
            self.last_state={'state':'stopped','stop_reason':{'kind':'breakpoint','thread':7,'native_kind':'step'}}
        return self.last_state

    def close(self):self.closed=True


def test_trace_reuses_register_snapshot_but_reads_self_modifying_code_each_time():
    cpu=CPU();result=collect_trace(cpu,2,1000)
    assert result['complete'] and [event['bytes'] for event in result['events']]==['90','91']
    assert cpu.reads==[0x1000,0x1000] and cpu.reg_reads==3
    assert result['statistics']['completed_instructions']==2 and not cpu.scope


@pytest.mark.parametrize('count,timeout',[(True,100),(0,100),(10001,100),(1,0),(1,True),(1,600001)])
def test_trace_preflight_never_touches_target(count,timeout):
    cpu=CPU()
    with pytest.raises(ValueError):collect_trace(cpu,count,timeout)
    assert cpu.reg_reads==cpu.steps==0 and not cpu.scope


def test_faulting_instruction_is_not_a_completed_trace_event():
    cpu=CPU('exception');result=collect_trace(cpu,3,1000)
    assert result['events']==[] and not result['complete']
    assert result['session']['stop_reason']['kind']=='exception' and not cpu.scope


def test_incomplete_native_step_closes_channel_without_pretending_target_is_paused():
    cpu=CPU('timeout')
    with pytest.raises(TimeoutError):collect_trace(cpu,3,1000)
    assert cpu.closed and not cpu.scope


def test_trace_stops_at_next_breakpoint_before_executing_it():
    cpu=CPU();cpu.breakpoints={'bp-1':{'address':0x1000}}
    result=collect_trace(cpu,3,1000)
    assert cpu.steps==1 and len(result['events'])==1 and not result['complete']
    assert result['session']['stop_reason']['kind']=='breakpoint'


def test_deadline_between_steps_returns_completed_prefix_and_real_stop(monkeypatch):
    cpu=CPU();clock=iter([0,0,0,0,2,2,2,2,2,2,2])
    monkeypatch.setattr('fdisbull.ida_trace.time.monotonic',lambda:next(clock))
    result=collect_trace(cpu,10,1000)
    assert not result['complete'] and cpu.steps<=1
    assert result['session']['stop_reason']['kind']=='timeout' and not cpu.scope


def test_budget_exhaustion_at_initial_breakpoint_does_not_claim_a_new_hit(monkeypatch):
    cpu=CPU();cpu.last_state['stop_reason']['kind']='breakpoint'
    clock=iter([0,2,2])
    monkeypatch.setattr('fdisbull.ida_trace.time.monotonic',lambda:next(clock))
    result=collect_trace(cpu,10,1)
    assert result['events']==[] and cpu.steps==0
    assert result['session']['stop_reason']['kind']=='timeout'
    assert result['session']['stop_reason']['native_kind']=='breakpoint'


def remote_stub():
    client=RemoteDebugger.__new__(RemoteDebugger)
    client.pending={'tid':7,'eid':6};client.exited=False;client.threads={7,8,9}
    client._step_scope_tid=None;client._step_scope_held=set()
    client.channel=SimpleNamespace(stream=True);client.breakpoints={};client.displaced=None
    client.operations=[]
    client.checked=lambda code,data=b'',**kw:client.operations.append((code,Reader(data).dd()))
    return client


def test_step_scope_holds_peers_once_and_always_releases_them():
    client=remote_stub()
    with pytest.raises(RuntimeError,match='interrupted'):
        with client.step_scope():
            with client.step_scope():assert client._step_scope_tid==7
            raise RuntimeError('interrupted')
    assert client.operations==[(w.SUSPEND,8),(w.SUSPEND,9),(w.RESUME,8),(w.RESUME,9)]
    assert client._step_scope_tid is None and not client._step_scope_held


def test_new_thread_is_held_before_its_start_event_is_continued():
    client=remote_stub()
    events=iter([{'eid':3,'tid':10},{'eid':6,'tid':7}])
    def event(deadline):
        client.pending=next(events);client.threads.add(client.pending['tid']);return client.pending
    client.get_event=event
    client.continue_event=lambda:client.operations.append(('continue',client.pending['tid']))
    client._stop=lambda event:{'stop_reason':{'kind':'step','breakpoint_ids':[]}}
    with client.step_scope():client._wait_stop(100,stepping=True)
    assert client.operations.index((w.SUSPEND,10))<client.operations.index(('continue',10))
    assert client.operations[-3:]==[(w.RESUME,8),(w.RESUME,9),(w.RESUME,10)]


def test_selected_thread_exit_interrupts_trace_without_continuing_another_thread():
    client=remote_stub();event={'eid':4,'tid':7,'address':0x1000}
    client.get_event=lambda deadline:event
    client._stop=lambda event:{'stop_reason':{'kind':'thread-exited'}}
    client.continue_event=lambda:pytest.fail('Selected thread exit must be returned')
    with client.step_scope():
        assert client._wait_stop(100,stepping=True)['stop_reason']['kind']=='thread-exited'


def test_partially_failed_peer_hold_releases_only_successfully_held_threads():
    client=remote_stub()
    def checked(code,data=b''):
        tid=Reader(data).dd()
        if code==w.SUSPEND and tid==9:raise RuntimeError('could not hold peer')
        client.operations.append((code,tid))
    client.checked=checked
    with pytest.raises(RuntimeError,match='could not hold'):
        with client.step_scope():pytest.fail('Should not execute after failed hold')
    assert client.operations==[(w.SUSPEND,8),(w.RESUME,8)]
    assert client._step_scope_tid is None


def test_breakpoint_at_step_boundary_preserves_actual_native_step_event():
    client=remote_stub();client.debugger_id=0
    client.breakpoints={'bp-1':{'address':0x1000,'access':'x','armed':True}}
    event={'eid':6,'tid':7,'address':0x1000}
    client.last_state={'state':'stopped','stop_reason':{'kind':'step','thread':7,'native_event':event}}
    client._remove=lambda record:record.update(armed=False)
    result=client.breakpoint_boundary(0x1000)
    assert result['stop_reason']['kind']=='breakpoint' and result['stop_reason']['native_event']==event
    assert result['stop_reason']['stop_origin']=='single-step-boundary'
    assert client.displaced=='bp-1' and not client.breakpoints['bp-1']['armed']


def test_code_read_accepts_valid_short_page_boundary_without_inventing_bytes():
    client=remote_stub();client.request=lambda *args,**kw:Reader(dd(2)+b'\x90\xc3')
    assert client.read_code(0x1ffe)==b'\x90\xc3'
    for response in (dd(0),dd(16)+b'x'*16,dd(2)+b'\x90'):
        client.request=lambda *args,**kw:Reader(response)
        with pytest.raises(ProtocolError):client.read_code(0x1ffe)
