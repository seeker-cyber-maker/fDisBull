"""Normal machine API contracts at the native GDB/QMP boundary; no VM."""
from types import SimpleNamespace
import threading
import pytest
from fdisbull.qemu_machine import MachineContext


class Recorder:
    def __init__(self):
        self.events=[];self.internal_breakpoints=set();self.provider=object();self.fail=False;self.machine=None;self.drop=False
    def before_execution(self,reason):
        self.events.append(('before',reason))
        if self.fail:raise ValueError('journal unavailable')
    def after_stop(self,reason):self.events.append(('after',reason))
    def close(self,reason):self.events.append(('close',reason))
    def status(self):return {'enabled':True,'events':list(self.events)}
    def internal_stop(self,event):
        ids=set(event['breakpoints']);self.events.append(('internal',tuple(sorted(ids))))
        owned=ids&self.internal_breakpoints
        if self.drop:
            for key in list(owned):self.machine.delete_breakpoint(key)
            self.internal_breakpoints-=owned;self.provider=None
        return bool(owned) and ids<=owned


class FakeQMP:
    def __init__(self):self.running=False;self.sent=[]
    def call(self,method,args=None,**kwargs):
        if method=='query-status':return {'running':self.running}
        if method=='send-key':
            assert self.running, 'QMP input was dispatched while paused'
            self.sent.append(args);return {}
        if method=='stop':self.running=False;return {}
        if method=='cont':self.running=True;return {}
        raise AssertionError(method)


class FakeRemote:
    def __init__(self,machine):
        self.machine=machine;self.socket=object();self.stops=[];self.calls=[];self.requests=[];self.running_on_continue=True
    def request(self,text):self.requests.append(text);return b'OK'
    def close(self):self.socket=None
    def execute(self,command,timeout_ms,**kwargs):
        self.calls.append((command,timeout_ms));self.machine.vm.qmp.running=self.running_on_continue
        if kwargs.get('on_continue'):kwargs['on_continue'](__import__('time').monotonic()+timeout_ms/1000)
        self.machine.vm.qmp.running=False
        self.machine.pc=self.stops.pop(0) if self.stops else self.machine.pc+1
        return b'T05',False


class FakeMachine(MachineContext):
    def __init__(self):
        vm=SimpleNamespace(lock=threading.RLock(),qmp=FakeQMP(),gdb=None,machine_stopped=True,close=lambda:None)
        super().__init__(vm);self.pc=0x20100;self.remote=FakeRemote(self);vm.gdb=self.remote
        vm.debugger=lambda:self.remote
        self._automatic_runtime_tracker=Recorder();self._automatic_runtime_tracker.machine=self
    def registers(self):
        return {'linear_pc':hex(self.pc),'registers':{'cs':'0x2000','eip':hex(self.pc-0x20000)},
                'cpu_mode':'v86','address_state':{'machine_vcpus':1}}


def internal(machine,address):
    machine._automatic_tracking_callback_active=True
    try:point=machine.breakpoint(address)
    finally:machine._automatic_tracking_callback_active=False
    machine._automatic_runtime_tracker.internal_breakpoints.add(point['breakpoint_id'])
    return point['breakpoint_id']


def test_paused_input_is_queued_then_sent_only_after_normal_continue():
    machine=FakeMachine();queued=machine.keyboard.press('enter',hold_ms=1,gap_ms=1)
    assert queued['queued'] and machine.vm.qmp.sent==[]
    assert machine.keyboard.state()['keyboard']['pending_events']==1
    result=machine.run(timeout_ms=100)
    assert machine.vm.qmp.sent==[{'keys':[{'type':'qcode','data':'ret'}],'hold-time':1}]
    assert result['pending_keyboard_events']==0 and machine.keyboard.state()['keyboard']['dispatched_events']==1
    assert machine._automatic_runtime_tracker.events[0][0]=='before'
    assert machine._automatic_runtime_tracker.events[-1][0]=='after'


def test_text_uses_us_physical_keys_without_persisting_plaintext_in_result():
    machine=FakeMachine();result=machine.keyboard.type('A:\\x',hold_ms=1,gap_ms=1)
    assert 'A:\\x' not in repr(result)
    machine.run(timeout_ms=200)
    assert [[k['data'] for k in event['keys']] for event in machine.vm.qmp.sent]==[
        ['shift','a'],['shift','semicolon'],['backslash'],['x']]


def test_early_stop_retains_undelivered_input_without_replay():
    machine=FakeMachine();machine.keyboard.press('enter',hold_ms=1,gap_ms=1)
    machine.remote.running_on_continue=False
    machine.run(timeout_ms=5)
    assert machine.vm.qmp.sent==[] and machine.keyboard.state()['keyboard']['pending_events']==1
    machine.remote.running_on_continue=True;machine.run(timeout_ms=100)
    assert len(machine.vm.qmp.sent)==1 and machine.keyboard.state()['keyboard']['pending_events']==0


def test_invalid_input_has_no_native_dispatch_or_queue_side_effect():
    machine=FakeMachine()
    with pytest.raises(ValueError):machine.keyboard.type('é')
    with pytest.raises(ValueError):machine.keyboard.press('not-a-key')
    assert machine.remote.calls==[] and machine.vm.qmp.sent==[]
    assert machine._automatic_runtime_tracker.events==[]


def test_stop_race_marks_dispatched_key_uncertain_and_never_replays_it():
    machine=FakeMachine();native=machine.vm.qmp.call
    def race(method,*args,**kwargs):
        result=native(method,*args,**kwargs)
        if method=='send-key':machine.vm.qmp.running=False
        return result
    machine.vm.qmp.call=race;machine.keyboard.press('enter',hold_ms=1,gap_ms=1)
    result=machine.run(timeout_ms=100)
    assert result['uncertain_keyboard_events']==1
    assert machine.keyboard.state()['keyboard']['pending_events']==0
    machine.run(timeout_ms=100)
    assert len(machine.vm.qmp.sent)==1


def test_failed_invalidation_blocks_execution_and_input():
    machine=FakeMachine();machine._automatic_runtime_tracker.fail=True
    with pytest.raises(ValueError,match='journal unavailable'):machine.run(timeout_ms=100)
    with pytest.raises(ValueError,match='journal unavailable'):machine.keyboard.press('enter')
    assert not machine.remote.calls and machine.keyboard.state()['keyboard']['pending_events']==0


def test_internal_and_user_alias_share_one_native_breakpoint():
    machine=FakeMachine();owned=internal(machine,0x20200);user=machine.breakpoint(0x20200)['breakpoint_id']
    assert machine.remote.requests==['Z1,20200,1']
    with pytest.raises(ValueError,match='Duplicate'):machine.breakpoint(0x20200)
    machine.delete_breakpoint(owned);assert machine.remote.requests==['Z1,20200,1']
    machine.delete_breakpoint(user);assert machine.remote.requests[-1]=='z1,20200,1'


def test_internal_stop_steps_original_instruction_and_continues_to_user_stop():
    machine=FakeMachine();internal(machine,0x20200);user=machine.breakpoint(0x20300)['breakpoint_id']
    machine.remote.requests=[];machine.remote.stops=[0x20200,0x20201,0x20300]
    result=machine.run(timeout_ms=100)
    assert result['outcome']=='breakpoint' and result['breakpoints']==[user]
    assert [c for c,_ in machine.remote.calls]==['c','s','c']
    assert machine.remote.requests==['z1,20200,1','Z1,20200,1']
    assert result['internal_tracking_stops']==1


def test_user_collision_is_visible_and_next_explicit_step_does_not_repeat_event():
    machine=FakeMachine();owned=internal(machine,0x20200);user=machine.breakpoint(0x20200)['breakpoint_id']
    machine.remote.stops=[0x20200,0x20201]
    first=machine.run(timeout_ms=100)
    assert first['outcome']=='breakpoint' and first['breakpoints']==[user]
    assert len([e for e in machine._automatic_runtime_tracker.events if e[0]=='internal'])==1
    machine.remote.requests=[];second=machine.step(timeout_ms=100)
    assert second['outcome']=='step'
    assert [c for c,_ in machine.remote.calls]==['c','s']
    assert machine.remote.requests==['z1,20200,1','Z1,20200,1']
    assert len([e for e in machine._automatic_runtime_tracker.events if e[0]=='internal'])==1
    assert owned in machine.breakpoints and user in machine.breakpoints


def test_retired_internal_hook_is_not_reinserted_after_original_instruction():
    machine=FakeMachine();owned=internal(machine,0x20200);machine._automatic_runtime_tracker.drop=True
    machine.remote.stops=[0x20200,0x20201,0x20300];machine.remote.requests=[]
    result=machine.run(timeout_ms=100)
    assert result['outcome']=='stopped' and owned not in machine.breakpoints
    assert machine.remote.requests==['z1,20200,1']
    assert [c for c,_ in machine.remote.calls]==['c','s','c']


def test_internal_event_budget_is_visible_and_stays_stopped(monkeypatch):
    from fdisbull import qemu_machine
    monkeypatch.setattr(qemu_machine,'_MAX_INTERNAL_STOPS',1)
    machine=FakeMachine();internal(machine,0x20200);machine.remote.stops=[0x20200,0x20201,0x20200]
    result=machine.run(timeout_ms=100)
    assert result['outcome']=='tracking-budget' and result['session']['state']=='stopped'
    assert result['internal_tracking_stops']==1
    assert len([e for e in machine._automatic_runtime_tracker.events if e[0]=='internal'])==1


def test_deadline_after_internal_callback_does_not_record_same_event_twice(monkeypatch):
    from fdisbull import qemu_machine
    clock=[0.0]
    monkeypatch.setattr(qemu_machine,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda value:None))
    machine=FakeMachine();internal(machine,0x20200);machine.remote.stops=[0x20200,0x20201,0x20300]
    tracker=machine._automatic_runtime_tracker;original=tracker.internal_stop
    def slow(event):
        result=original(event);clock[0]+=.2;return result
    tracker.internal_stop=slow
    first=machine.run(timeout_ms=100)
    assert first['outcome']=='tracking-budget' and machine._automatic_internal_pending
    tracker.internal_stop=original;second=machine.run(timeout_ms=100)
    assert second['outcome']=='stopped' and machine._automatic_internal_pending is None
    assert [c for c,_ in machine.remote.calls]==['c','s','c']
    assert len([e for e in tracker.events if e[0]=='internal'])==1


def test_deadline_expiring_during_invalidation_never_dispatches_native_execution(monkeypatch):
    from fdisbull import qemu_machine
    clock=[0.0]
    monkeypatch.setattr(qemu_machine,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda value:None))
    machine=FakeMachine();tracker=machine._automatic_runtime_tracker
    original=tracker.before_execution
    def slow(reason):
        original(reason);clock[0]+=.101
    tracker.before_execution=slow
    result=machine.run(timeout_ms=100)
    assert result['outcome']=='timeout' and result['session']['state']=='stopped'
    assert machine.remote.calls==[] and machine.vm.qmp.sent==[]
    assert tracker.events==[('before','machine-gdb-run'),('after','machine-timeout')]
