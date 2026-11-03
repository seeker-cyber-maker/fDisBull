"""Deterministic protocol checks; no original game or replacement emulator."""
from types import SimpleNamespace
import pytest
from fdisbull.native_controller import BoundedNativeController, NativeControlError


class Session:
    def __init__(self):
        self.runs=[];self.keys=[];self.accepted=True;self.progress=None;self.outcome='guest_time'
    def run(self,**kwargs):
        self.runs.append(kwargs)
        return {'outcome':self.outcome,'guest_elapsed_ms':kwargs['guest_ms'] if self.progress is None else self.progress}
    def keyboard_state(self):return {'keyboard':dict(pending_events=0,owned_keys=0,queued_guest_ms=0)}
    def keyboard_press(self,key,**kwargs):self.keys.append(key);return {'accepted':self.accepted}
    def keyboard_type(self,text,**kwargs):self.keys.append(text);return {'accepted':self.accepted}


def controller(session=None, **kwargs):
    return BoundedNativeController(session or Session(),read_state=kwargs.pop('read_state',lambda:{'ok':True}),
             total_guest_ms=kwargs.pop('total_guest_ms',1000),total_timeout_ms=10000,**kwargs)


def test_wait_initial_truth_avoids_guest_execution():
    s=Session();c=controller(s)
    assert c.wait(lambda v:v['ok'],'ready')['ok'] and s.runs==[]
    assert c.waits[0]['polls']==1 and c.waits[0]['guest_elapsed_ms']==0


def test_wait_accepts_truth_at_exact_guest_budget_and_records_actual_progress():
    s=Session();c=controller(s,total_guest_ms=100,read_state=lambda:{'ready':len(s.runs)==2})
    assert c.wait(lambda v:v['ready'],'ready',budget=100,slice_ms=50)=={'ready':True}
    assert c.guest_elapsed==100 and c.waits[-1]['polls']==3


def test_false_wait_retains_last_observation_and_latches_without_extra_run():
    s=Session();c=controller(s,read_state=lambda:{'value':7})
    with pytest.raises(NativeControlError,match='within budget'):c.wait(lambda v:False,'condition',budget=100)
    assert c.waits[-1]['last_observation']=={'value':7} and len(s.runs)==2
    with pytest.raises(NativeControlError):c.press('left')
    assert s.keys==[] and len(s.runs)==2


@pytest.mark.parametrize('outcome',['breakpoint','hook','guest_error','timeout'])
def test_unowned_native_stops_latch_and_are_not_run_through(outcome):
    s=Session();s.outcome=outcome;c=controller(s)
    with pytest.raises(NativeControlError):c.advance()
    with pytest.raises(NativeControlError):c.advance()
    assert len(s.runs)==1 and c.journal[-1]['result']['outcome']==outcome


def test_owned_stop_requires_explicit_resolution_and_accounts_observer_progress():
    s=Session();s.outcome='breakpoint';s.progress=0
    c=controller(s)
    def owned(out):c.account_guest(25);s.outcome='guest_time';s.progress=None;return True
    c.stop_handler=owned;c.advance(100)
    assert c.guest_elapsed==100 and len(s.runs)==2
    bad=controller(s);s.outcome='breakpoint'
    bad.stop_handler=lambda out:None
    with pytest.raises(NativeControlError):bad.advance()


@pytest.mark.parametrize('acceptance',[False,None,'true'])
def test_uncertain_or_rejected_input_never_executes_or_retries(acceptance):
    s=Session();s.accepted=acceptance;c=controller(s)
    with pytest.raises(NativeControlError):c.press('left')
    with pytest.raises(NativeControlError):c.press('left')
    assert s.keys==['left'] and s.runs==[] and c.inputs[0]['complete'] is False


def test_lost_input_reply_retains_attempt_without_advancing():
    s=Session()
    def lost(*a,**kw):s.keys.append('left');raise TimeoutError('lost reply')
    s.keyboard_press=lost;c=controller(s)
    with pytest.raises(TimeoutError):c.press('left')
    assert c.inputs[0]['delivered'] is None and c.inputs[0]['error']=='lost reply'
    assert s.runs==[]


def test_returned_progress_and_fast_forward_are_used_not_requested_duration():
    s=Session();s.progress=115;c=controller(s,fast_forward=True)
    c.advance(10)
    assert c.guest_elapsed==115 and len(s.runs)==1 and s.runs[0]['fast_forward'] is True


@pytest.mark.parametrize('progress',[None,True,-1,float('nan'),float('inf'),0])
def test_invalid_or_zero_progress_stops_before_second_slice(progress):
    s=Session();c=controller(s)
    def result(**kw):s.runs.append(kw);return {'outcome':'guest_time','guest_elapsed_ms':progress}
    s.run=result
    with pytest.raises((ValueError,NativeControlError)):c.advance()
    assert len(s.runs)==1 and c.blocked_reason is not None


def test_wall_expiry_during_observation_is_not_success():
    now=[0.0];s=Session()
    def observe():now[0]=11.0;return {'ready':True}
    c=controller(s,read_state=observe,clock=lambda:now[0])
    with pytest.raises(NativeControlError,match='wall budget'):c.wait(lambda v:v['ready'],'ready')
    assert not c.waits[0]['complete'] and s.runs==[]


def test_text_input_has_no_implicit_enter_and_journal_is_before_dispatch():
    s=Session();journal=[];inputs=[];c=controller(s,journal=journal,inputs=inputs)
    def typed(text,**kw):
        assert inputs[0]['complete'] is False and journal[0]['kind']=='input'
        s.keys.append(text);return {'accepted':True}
    s.keyboard_type=typed;c.type_text('look')
    assert s.keys==['look'] and inputs[0]['complete'] is True


def test_slow_final_state_read_keeps_observation_but_does_not_succeed():
    now=[0.0]
    def read():now[0]=11;return {'committed':True}
    c=controller(read_state=read,clock=lambda:now[0])
    with pytest.raises(NativeControlError,match='after observation'):c.advance(100)
    assert c.status()['last_observation']=={'committed':True} and c.blocked_reason


def test_slow_final_keyboard_read_keeps_consumption_without_claiming_complete():
    now=[0.0];s=Session();calls=[];normal=s.keyboard_state
    def idle():
        calls.append(True)
        if len(calls)==2:now[0]=11
        return normal()
    s.keyboard_state=idle;c=controller(s,clock=lambda:now[0])
    with pytest.raises(NativeControlError,match='keyboard observation'):c.press('left')
    assert c.inputs[0]['delivered'] is True and c.inputs[0]['complete'] is False
    assert c.status()['last_keyboard_state']['keyboard']['pending_events']==0


def test_wait_refuses_local_guest_overshoot_even_if_goal_is_observed():
    s=Session();s.progress=115;c=controller(s,read_state=lambda:{'ready':bool(s.runs)})
    with pytest.raises(NativeControlError,match='measured guest budget'):
        c.wait(lambda state:state['ready'],'ready',budget=100)
    assert c.waits[-1]['last_observation']=={'ready':True}
    assert c.guest_elapsed==115 and not c.waits[-1]['complete']


def test_slow_predicate_cannot_turn_wall_expiry_into_success():
    now=[0.0];c=controller(clock=lambda:now[0])
    def predicate(state):now[0]=11;return True
    with pytest.raises(NativeControlError,match='after predicate'):c.wait(predicate,'ready')
    assert c.waits[-1]['polls']==1 and not c.waits[-1]['complete']
