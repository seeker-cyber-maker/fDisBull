"""Mock GDB/QMP boundaries, no VM; candidate copied from sealed S5."""
from types import SimpleNamespace
import threading
import pytest
from fdisbull import qemu_machine as q

class Clock:
 def __init__(self):self.now=0.0
 def monotonic(self):return self.now
 def sleep(self,value):self.now+=value
class Recorder:
 def __init__(self):self.internal_breakpoints=set();self.events=[];self.provider=object()
 def before_execution(self,reason):self.events.append(('before',reason))
 def after_stop(self,reason):self.events.append(('after',reason))
 def internal_stop(self,event):self.events.append(('internal',tuple(sorted(event['breakpoints']))));return set(event['breakpoints'])<=self.internal_breakpoints
 def status(self):return dict(enabled=True)
 def close(self,reason):self.events.append(('close',reason))
class Remote:
 def __init__(self,machine,clock):self.machine=machine;self.clock=clock;self.socket=object();self.stops=[];self.calls=[];self.requests=[]
 def request(self,text):self.requests.append(text);return b'OK'
 def execute(self,command,timeout_ms,**kwargs):
  self.calls.append(command);pc,timed_out,elapsed,reply=self.stops.pop(0);self.machine.pc=pc;self.clock.now+=elapsed;return reply,timed_out
class Machine(q.MachineContext):
 def __init__(self,clock):
  vm=SimpleNamespace(lock=threading.RLock(),gdb=None,machine_stopped=True,qmp=SimpleNamespace(call=lambda *a,**kw:{'running':False}),close=lambda:None)
  super().__init__(vm);self.pc=0x20100;self.remote=Remote(self,clock);vm.gdb=self.remote;vm.debugger=lambda:self.remote;self._automatic_runtime_tracker=Recorder()
 def registers(self):return dict(linear_pc=hex(self.pc),registers=dict(cs='0x2000',eip=hex(self.pc-0x20000)),cpu_mode='v86',address_state=dict(machine_vcpus=1))
def owned(machine,address=0x20200):
 machine._automatic_tracking_callback_active=True
 try:bp=machine.breakpoint(address)['breakpoint_id']
 finally:machine._automatic_tracking_callback_active=False
 machine._automatic_runtime_tracker.internal_breakpoints.add(bp);return bp
@pytest.fixture
def stopped(monkeypatch):
 clock=Clock();monkeypatch.setattr(q,'time',clock);machine=Machine(clock);return machine,clock

def count(machine):return len([e for e in machine._automatic_runtime_tracker.events if e[0]=='internal'])

def test_public_timeout_contract_preserved_for_late_user_breakpoint(stopped):
 machine,_=stopped;user=machine.breakpoint(0x20200)['breakpoint_id'];machine.remote.stops=[(0x20200,True,.11,b'T05')]
 result=machine.run(timeout_ms=100)
 assert result['outcome']=='timeout' and result['timed_out']is True
 assert result['session']['stop_reason']['kind']=='timeout' and result['breakpoints']==[user]
 assert count(machine)==0 and machine.remote.calls==['c']

def test_late_owned_stop_is_recorded_once_without_turning_timeout_into_hit(stopped):
 machine,_=stopped;bp=owned(machine);machine.remote.stops=[(0x20200,True,.11,b'T05'),(0x20201,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='timeout' and first['timed_out']is True and first['breakpoints']==[bp]
 assert first['session']['stop_reason']['native_reply']=='T05'
 assert count(machine)==1 and machine.remote.calls==['c']
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==1
 assert machine.remote.calls==['c','s'] and machine._automatic_internal_pending is None

def test_arrived_owned_stop_after_host_deadline_is_recorded_before_budget(stopped):
 machine,_=stopped;owned(machine);machine.remote.stops=[(0x20200,False,.11,b'T05'),(0x20201,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='tracking-budget' and first['internal_tracking_stops']==1
 assert count(machine)==1 and machine.remote.calls==['c']
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==1 and machine.remote.calls==['c','s']

def test_count_budget_pauses_before_resuming_to_an_unrecorded_next_event(stopped,monkeypatch):
 machine,_=stopped;owned(machine);monkeypatch.setattr(q,'_MAX_INTERNAL_STOPS',1)
 machine.remote.stops=[(0x20200,False,0,b'T05'),(0x20201,False,0,b'T05'),(0x20200,False,0,b'T05'),(0x20201,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='tracking-budget' and first['internal_tracking_stops']==1
 assert machine.remote.calls==['c'] and count(machine)==1
 second=machine.run(timeout_ms=100)
 assert second['outcome']=='tracking-budget' and second['internal_tracking_stops']==1
 assert machine.remote.calls==['c','s','c'] and count(machine)==2
 third=machine.step(timeout_ms=100)
 assert third['outcome']=='step' and count(machine)==2 and machine.remote.calls==['c','s','c','s']

def test_late_user_collision_remains_visible_and_explicit_step_does_not_duplicate(stopped):
 machine,_=stopped;bp=owned(machine);user=machine.breakpoint(0x20200)['breakpoint_id'];machine.remote.stops=[(0x20200,True,.11,b'T05'),(0x20201,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='timeout' and first['timed_out']is True
 assert first['breakpoints']==[user] and first['automatic_breakpoints']==[bp]
 assert count(machine)==1 and machine.remote.calls==['c']
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==1 and machine.remote.calls==['c','s']

def test_interrupt_timeout_at_owned_PC_does_not_invent_a_hook_hit(stopped):
 machine,_=stopped;bp=owned(machine);machine.remote.stops=[(0x20200,True,.11,b'S02')]
 result=machine.run(timeout_ms=100)
 assert result['outcome']=='timeout' and result['timed_out']is True
 assert result['session']['stop_reason']['native_reply']=='S02' and result['breakpoints']==[]
 assert count(machine)==0 and getattr(machine,'_automatic_internal_pending',None) is None and machine.remote.calls==['c']

def test_late_user_watchpoint_remains_a_timeout_without_owned_event(stopped):
 machine,_=stopped;user=machine.breakpoint(0x30000,access='w')['breakpoint_id'];machine.remote.stops=[(0x20200,True,.11,b'T05thread:1;watch:30000;')]
 result=machine.run(timeout_ms=100)
 assert result['outcome']=='timeout' and result['session']['stop_reason']['kind']=='timeout'
 assert result['breakpoints']==[user] and count(machine)==0 and machine.remote.calls==['c']

def test_pending_step_arriving_at_another_late_owned_hook_records_both_once(stopped):
 machine,_=stopped;owned(machine);b=owned(machine,0x20300)
 machine.remote.stops=[(0x20200,True,.11,b'T05'),(0x20300,True,.11,b'T05'),(0x20301,False,0,b'T05')]
 first=machine.run(timeout_ms=100);assert first['outcome']=='timeout' and count(machine)==1
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='timeout' and second['timed_out']is True and count(machine)==2
 assert machine.remote.calls==['c','s'] and machine._automatic_internal_pending['pc']=='0x20300'
 assert second['automatic_breakpoints']==[b]
 third=machine.step(timeout_ms=100)
 assert third['outcome']=='step' and count(machine)==2 and machine.remote.calls==['c','s','s']

def test_inner_step_over_arriving_at_late_owned_hook_records_without_more_execution(stopped):
 machine,_=stopped;owned(machine);b=owned(machine,0x20300)
 machine.remote.stops=[(0x20200,False,0,b'T05'),(0x20300,True,.11,b'T05'),(0x20301,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='timeout' and first['timed_out']is True and count(machine)==2
 assert first['internal_tracking_stops']==2 and machine.remote.calls==['c','s']
 assert first['automatic_breakpoints']==[b] and machine._automatic_internal_pending['pc']=='0x20300'
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==2 and machine.remote.calls==['c','s','s']

def test_explicit_step_records_new_hook_but_does_not_execute_its_instruction(stopped):
 machine,_=stopped;b=owned(machine,0x20300)
 machine.remote.stops=[(0x20300,False,0,b'T05'),(0x20301,False,0,b'T05')]
 first=machine.step(timeout_ms=100)
 assert first['outcome']=='breakpoint' and first['automatic_breakpoints']==[b]
 assert count(machine)==1 and machine.remote.calls==['s'] and machine._automatic_internal_pending['pc']=='0x20300'
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==1 and machine.remote.calls==['s','s']

def test_count_budget_does_not_hide_colliding_user_breakpoint(stopped,monkeypatch):
 machine,_=stopped;bp=owned(machine);user=machine.breakpoint(0x20200)['breakpoint_id'];monkeypatch.setattr(q,'_MAX_INTERNAL_STOPS',1)
 machine.remote.stops=[(0x20200,False,0,b'T05'),(0x20201,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='breakpoint' and first['breakpoints']==[user] and first['automatic_breakpoints']==[bp]
 assert first['internal_tracking_stops']==1 and machine.remote.calls==['c']
 second=machine.step(timeout_ms=100)
 assert second['outcome']=='step' and count(machine)==1 and machine.remote.calls==['c','s']
