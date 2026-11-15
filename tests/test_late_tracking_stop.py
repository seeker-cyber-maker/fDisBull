"""Mock GDB/QMP boundaries, no VM; candidate copied from sealed S5."""
from copy import deepcopy
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
 def __init__(self,machine,clock):self.machine=machine;self.clock=clock;self.socket=object();self.stops=[];self.calls=[];self.requests=[];self.request_budgets=[]
 def request(self,text,*,timeout_ms=10000):self.requests.append(text);self.request_budgets.append(timeout_ms);return b'OK'
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
 assert second['tracking_control_repair']['grace_used'] and second['tracking_control_repair']['complete']
 third=machine.step(timeout_ms=100)
 assert third['outcome']=='step' and count(machine)==2 and machine.remote.calls==['c','s','s']

def test_inner_step_over_arriving_at_late_owned_hook_records_without_more_execution(stopped):
 machine,_=stopped;owned(machine);b=owned(machine,0x20300)
 machine.remote.stops=[(0x20200,False,0,b'T05'),(0x20300,True,.11,b'T05'),(0x20301,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='timeout' and first['timed_out']is True and count(machine)==2
 assert first['internal_tracking_stops']==2 and machine.remote.calls==['c','s']
 assert first['automatic_breakpoints']==[b] and machine._automatic_internal_pending['pc']=='0x20300'
 assert first['tracking_control_repair']['budget_ms']==1000
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

@pytest.mark.parametrize('phase',['suspension','repair-grace'])
def test_internal_control_timeout_uses_one_budget_and_retains_latest_native_stop(stopped,phase):
 machine,clock=stopped;owned(machine)
 machine.remote.stops=[(0x20200,True,.11,b'T05'),(0x20201,False,.11,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='timeout' and machine._automatic_internal_pending
 closed=[];machine.vm.close=lambda:closed.append(True)
 original=machine.remote.request;machine.remote.requests=[];machine.remote.request_budgets=[]
 def delayed(text,*,timeout_ms=10000):
  result=original(text,timeout_ms=timeout_ms)
  if text.startswith('z' if phase=='suspension' else 'Z'):
   clock.now+=timeout_ms/1000
   raise TimeoutError('authored control acknowledgement deadline')
  return result
 machine.remote.request=delayed
 with pytest.raises((TimeoutError,q.DebuggerError)) as caught:
  machine.step(timeout_ms=100)
 expected_pc='0x20200' if phase=='suspension' else '0x20201'
 assert caught.value.result['registers']['linear_pc']==expected_pc
 assert caught.value.result['session']['stop_reason']['native_reply']=='T05'
 assert machine.remote.calls==(['c'] if phase=='suspension' else ['c','s'])
 assert machine.remote.requests==(['z1,20200,1'] if phase=='suspension' else ['z1,20200,1','Z1,20200,1'])
 assert 0<machine.remote.request_budgets[0]<=100
 if phase=='repair-grace':
  assert 0<machine.remote.request_budgets[1]<=1000
  assert caught.value.result['tracking_control_repair']['grace_used']
  assert not caught.value.result['tracking_control_repair']['complete']
 assert closed and machine._automatic_internal_pending is None

def test_expired_inherited_budget_preserves_pending_controls_without_dispatch(stopped):
 machine,clock=stopped;point=owned(machine)
 machine.remote.stops=[(0x20200,True,.11,b'T05')]
 machine.run(timeout_ms=100)
 pending=machine._automatic_internal_pending
 machine.remote.requests=[];closed=[];machine.vm.close=lambda:closed.append(True)
 machine.vm.operation_deadline=clock.now
 result=machine.step(timeout_ms=100)
 assert result['outcome']=='tracking-budget' and result['timed_out']
 assert machine.remote.calls==['c'] and machine.remote.requests==[] and not closed
 assert machine._automatic_internal_pending==pending and point in machine.breakpoints


@pytest.mark.parametrize('stage',['provider-register-read','native-lifecycle-journal'])
@pytest.mark.parametrize('late',[False,True])
@pytest.mark.parametrize('secondary',['none','retirement','cleanup'])
def test_internal_tracking_failure_retains_arrived_stop_and_closes_without_replay(stopped,stage,late,secondary):
 from types import MethodType
 from fdisbull.runtime_tracking import AutomaticRuntimeTracker
 machine,_=stopped;point=owned(machine);tracker=machine._automatic_runtime_tracker
 tracker.session=machine
 tracker.provider=SimpleNamespace(source_identity={'provider':'authored'},
     interpret_event=lambda registers:dict(kind='other',handle=None,source_identity={'provider':'authored'}))
 tracker.internal_stop=MethodType(AutomaticRuntimeTracker.internal_stop,tracker)
 failure=OSError('authored '+stage+' failure');records=[];closed=[]
 def record(kind,document):
  records.append(kind)
  if stage=='native-lifecycle-journal':raise failure
  return dict(kind='recorded',reference='authored',sha256='0'*64)
 tracker._record=record
 original=machine.registers
 def registers():
  if stage=='provider-register-read' and getattr(machine,'_automatic_tracking_callback_active',False):raise failure
  return original()
 machine.registers=registers
 def retire(reason):
  tracker.events.append(('close',reason))
  if secondary=='retirement':raise RuntimeError('authored retirement failure')
 tracker.close=retire
 def close():
  closed.append(True)
  if secondary=='cleanup':
   machine.remote.socket=None
   raise BrokenPipeError('authored cleanup failure')
 machine.vm.close=close;machine.remote.requests=[]
 machine.remote.stops=[(0x20200,late,.11 if late else 0,b'T05')]
 with pytest.raises(OSError) as caught:machine.run(timeout_ms=100)
 assert caught.value is failure
 result=caught.value.result
 assert result['outcome']==('timeout' if late else 'breakpoint') and result['timed_out'] is late
 assert result['registers']['linear_pc']=='0x20200'
 assert result['session']['stop_reason']['native_reply']=='T05'
 assert result['session']['stop_reason']['breakpoint_ids']==[point]
 assert result['breakpoints']==[point]
 assert machine.remote.calls==['c'] and machine.remote.requests==[]
 assert machine._automatic_internal_pending is None and closed==[True]
 assert ('close','machine-internal-stop-publication-failed') in tracker.events
 assert records==(['native-lifecycle'] if stage=='native-lifecycle-journal' else [])
 if secondary=='retirement':assert caught.value.tracking_retirement_error=='RuntimeError'
 if secondary=='cleanup':assert caught.value.machine_cleanup_error=='BrokenPipeError'
 calls,requests=list(machine.remote.calls),list(machine.remote.requests)
 for operation in (machine.run,machine.step,machine._stopped):
  with pytest.raises(q.DebuggerError,match='quarantined'):operation()
 assert machine.remote.calls==calls and machine.remote.requests==requests


@pytest.mark.parametrize('route',['tail','control-repair'])
def test_failed_cleanup_keeps_tail_and_control_repair_owners_quarantined(stopped,route):
 machine,_=stopped;closed=[]
 failure=OSError('authored '+route+' failure')
 if route=='tail':
  def after(reason):raise failure
  machine._automatic_runtime_tracker.after_stop=after
  machine.remote.stops=[(0x20200,False,0,b'T05')]
 else:
  owned(machine);machine.remote.stops=[(0x20200,True,.11,b'T05')]
  machine.run(timeout_ms=100)
  def request(*args,**kwargs):raise failure
  machine.remote.request=request
 def close():
  closed.append(True)
  machine.remote.socket=None
  raise BrokenPipeError('authored disposal failure')
 machine.vm.close=close
 with pytest.raises(OSError) as caught:
  if route=='tail':machine.run(timeout_ms=100)
  else:machine.step(timeout_ms=100)
 assert caught.value is failure and caught.value.result['session']['stop_reason']['native_reply']=='T05'
 assert caught.value.machine_cleanup_error=='BrokenPipeError' and closed==[True]
 calls,requests=list(machine.remote.calls),list(machine.remote.requests)
 for operation in (machine.run,machine.step,machine._stopped):
  with pytest.raises(q.DebuggerError,match='quarantined'):operation()
 assert machine.remote.calls==calls and machine.remote.requests==requests
 # Disposal remains callable after the public control gate has closed.
 with pytest.raises(BrokenPipeError):machine.vm.close()
 assert closed==[True,True]


def test_quarantine_keeps_only_offline_diagnostics_readable(stopped):
 from fdisbull.qemu_dos_process import QemuDOSProcessSession
 machine,_=stopped
 machine.vm._fdisbull_control_quarantine='authored failed cleanup'
 machine._process={'state':'observation_failed','machine_closed':True,'source_mapping':{'live':False,'live_ranges':[]}}
 def unexpected(*args,**kwargs):pytest.fail('Offline diagnostic touched a native owner')
 machine.vm.process=SimpleNamespace(poll=unexpected)
 machine.vm.close=unexpected;machine.vm.qmp.call=unexpected
 process=QemuDOSProcessSession.dos_process_info(machine)
 assert process==machine._process and process is not machine._process
 assert machine.tracking_status()['enabled'] is True
 for operation in (machine.run,machine.step,machine.status,machine._stopped):
  with pytest.raises(q.DebuggerError,match='quarantined'):operation()
 assert machine.remote.calls==[] and machine.remote.requests==[]


class PhysicalInputQMP:
 def __init__(self):self.running=False;self.calls=[]
 def call(self,method,arguments=None,**options):
  self.calls.append((method,deepcopy(arguments)))
  if method=='query-status':return dict(running=self.running)
  assert method=='input-send-event' and self.running
  return {}


class PhysicalInputRemote(Remote):
 def __init__(self,machine,clock):super().__init__(machine,clock);self.intervals=[];self.failure=None
 def execute(self,command,timeout_ms,*,after_send=None):
  self.intervals.append((command,deepcopy(self.machine.vm._physical_input),after_send is not None))
  if self.failure is not None:raise self.failure
  self.machine.vm.qmp.running=command=='c'
  try:
   if after_send is not None:after_send(self.clock.now+timeout_ms/1000)
   return super().execute(command,timeout_ms)
  finally:self.machine.vm.qmp.running=False


def pending_with_physical_edges(stopped,monkeypatch):
 from fdisbull import qemu_input
 machine,clock=stopped;owned(machine)
 machine.remote.stops=[(0x20200,True,.11,b'T05')]
 assert machine.run(timeout_ms=100)['outcome']=='timeout'
 monkeypatch.setattr(qemu_input,'time',clock)
 machine.vm.qmp=PhysicalInputQMP();machine.vm.qmp_commands={'input-send-event'}
 remote=PhysicalInputRemote(machine,clock);machine.remote=remote;machine.vm.gdb=remote
 lease=machine.keyboard_key_down('a')['lease'];machine.keyboard_key_up(lease)
 machine.vm.qmp.calls.clear()
 return machine,clock,lease


def test_pending_owned_step_keeps_physical_edges_until_public_continue_once(stopped,monkeypatch):
 machine,_,lease=pending_with_physical_edges(stopped,monkeypatch)
 before=deepcopy(machine.vm._physical_input)
 machine.remote.stops=[(0x20201,False,0,b'T05'),(0x20400,False,0,b'T05'),(0x20500,False,0,b'T05')]
 first=machine.run(timeout_ms=100)
 assert first['outcome']=='stopped' and machine.remote.calls==['s','c']
 assert machine.remote.intervals[0]==('s',before,False)
 assert machine.remote.intervals[1]==('c',before,True)
 assert len([1 for method,_ in machine.vm.qmp.calls if method=='input-send-event'])==1
 assert machine.vm.qmp.calls[-1][1]['events']==[
  {'type':'key','data':{'key':{'type':'qcode','data':'a'},'down':True}},
  {'type':'key','data':{'key':{'type':'qcode','data':'a'},'down':False}}]
 state=machine.input_state()
 assert not state['pending_edges'] and lease not in state['leases']
 assert first['input_delivery']['delivery']=='qmp_accepted' and first['input_delivery']['guest_consumed'] is None
 machine.run(timeout_ms=100)
 assert machine.remote.calls==['s','c','c'] and machine.remote.intervals[-1][2] is False
 assert len([1 for method,_ in machine.vm.qmp.calls if method=='input-send-event'])==1


@pytest.mark.parametrize('operation',['step','trace'])
def test_public_step_and_trace_with_pending_hook_keep_physical_input_refusal(stopped,monkeypatch,operation):
 machine,_,_=pending_with_physical_edges(stopped,monkeypatch)
 state=deepcopy(machine.vm._physical_input);pending=deepcopy(machine._automatic_internal_pending)
 with pytest.raises(ValueError,match='requires run'):
  getattr(machine,operation)(timeout_ms=100)
 assert machine.vm._physical_input==state and machine._automatic_internal_pending==pending
 assert machine.remote.calls==machine.remote.requests==machine.vm.qmp.calls==[]
 assert not getattr(machine.vm,'_fdisbull_control_quarantine',None)


@pytest.mark.parametrize('kind',['ordinary','press','typing','click','motion','retrace'])
def test_owned_step_refuses_bound_input_plans_before_suspending_controls(stopped,monkeypatch,kind):
 machine,_,_=pending_with_physical_edges(stopped,monkeypatch)
 state=machine.vm._physical_input
 state['schedule']=dict(bound=True,records=deepcopy(state['pending']),native={'state':'armed'},applied_count=0)
 if kind!='ordinary':state['schedule'][kind]={'authored':'opaque native plan'}
 before=deepcopy(state);pending=deepcopy(machine._automatic_internal_pending)
 machine._layer_exec=True
 machine._layer_before_execution=lambda:pytest.fail('Policy refusal entered mutating layer preflight')
 with pytest.raises(ValueError,match='do not support scheduled input'):machine.run(timeout_ms=100)
 assert state==before and machine._automatic_internal_pending==pending
 assert machine.remote.calls==machine.remote.requests==[]
 assert not any(method=='input-send-event' for method,_ in machine.vm.qmp.calls)
 assert not getattr(machine.vm,'_fdisbull_control_quarantine',None)


def test_late_owned_step_keeps_edges_and_layers_until_next_explicit_continue(stopped,monkeypatch):
 machine,_,_=pending_with_physical_edges(stopped,monkeypatch)
 state=deepcopy(machine.vm._physical_input);preflights=[]
 machine._layer_exec=True;machine._layer_before_execution=lambda:preflights.append(deepcopy(machine.vm._physical_input))
 machine._layer_native_observe=lambda:{}
 machine.remote.stops=[(0x20201,True,.11,b'T05'),(0x20400,False,0,b'T05')]
 stopped_result=machine.run(timeout_ms=100)
 assert stopped_result['outcome']=='timeout' and stopped_result['timed_out']
 assert stopped_result['tracking_control_repair']['complete']
 assert machine.remote.calls==['s'] and machine.remote.intervals==[('s',state,False)]
 assert machine.vm._physical_input==state and not any(method=='input-send-event' for method,_ in machine.vm.qmp.calls)
 assert preflights==[state]
 result=machine.run(timeout_ms=100)
 assert result['input_delivery']['delivery']=='qmp_accepted' and machine.remote.calls==['s','c']
 assert preflights==[state,state] and not machine._input_pending()
 assert len([1 for method,_ in machine.vm.qmp.calls if method=='input-send-event'])==1


def test_expired_owned_step_preserves_unsent_edges_and_pending_stop(stopped,monkeypatch):
 machine,clock,_=pending_with_physical_edges(stopped,monkeypatch)
 state=deepcopy(machine.vm._physical_input);pending=deepcopy(machine._automatic_internal_pending)
 machine.vm.operation_deadline=clock.now
 with pytest.raises(TimeoutError,match='deadline'):machine.run(timeout_ms=100)
 assert machine.vm._physical_input==state and machine._automatic_internal_pending==pending
 assert machine.remote.calls==machine.remote.requests==machine.vm.qmp.calls==[]
 assert not getattr(machine.vm,'_fdisbull_control_quarantine',None)


def test_owned_step_transport_failure_never_dispatches_unsent_edges(stopped,monkeypatch):
 machine,_,_=pending_with_physical_edges(stopped,monkeypatch)
 before=deepcopy(machine.vm._physical_input);closed=[]
 def close():
  closed.append(True);machine._input_on_close()
 machine.vm.close=close;machine.remote.failure=OSError('authored internal step transport failure')
 with pytest.raises(OSError,match='authored internal step'):machine.run(timeout_ms=100)
 assert machine.remote.intervals==[('s',before,False)]
 assert closed and not any(method=='input-send-event' for method,_ in machine.vm.qmp.calls)
 state=machine.vm._physical_input
 assert state['last_delivery'] is None and state['valid'] is False
 assert state['invalidated_edges']==2 and state['invalidated_leases']==1
 assert state['pending']==[] and state['leases']=={}
 assert machine.vm._fdisbull_control_quarantine and machine._automatic_internal_pending is None
