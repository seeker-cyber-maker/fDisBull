"""Authored motion protocol checks; no game assets or replacement runtime."""
from copy import deepcopy
import pytest
from fdisbull.native_controller import BoundedNativeController, NativeControlError


class Rig:
    def __init__(self, *, x=0, y=0, moving=False, clock=None):
        self.value=dict(x=x,y=y,moving=moving,room=39,safe=True)
        self.direction=(0,0);self.actions=[];self.runs=[];self.tick=None
        self.c=BoundedNativeController(self,read_state=lambda:deepcopy(self.value),
            total_guest_ms=1000,total_timeout_ms=10000,clock=clock or (lambda:0))
    def run(self, **kw):
        self.runs.append(kw)
        if self.tick is not None:self.tick()
        elif self.value['moving']:
            self.value['x']+=self.direction[0];self.value['y']+=self.direction[1]
        return {'outcome':'guest_time','guest_elapsed_ms':kw['guest_ms']}
    def start(self,direction):
        self.actions.append(('start',direction));self.direction=direction;self.value['moving']=True
    def stop(self):self.actions.append(('stop',));self.value['moving']=False
    def align(self, targets, **options):
        args=dict(position=lambda s:{k:s[k] for k in ('x','y')},start=self.start,stop=self.stop,
                  settled=lambda s:not s['moving'],guard=lambda s:s['safe'],context=lambda s:s['room'])
        args.update(options)
        return self.c.align(targets,**args)


def test_initial_exact_neutral_goal_needs_no_inputs_or_execution():
    r=Rig(x=110,y=167);out=r.align({'y':167})
    assert out['y']==167 and r.actions==r.runs==[]
    assert r.c.alignments[0]['complete'] and r.c.alignments[0]['guest_elapsed_ms']==0


def test_exact_leg_records_actual_points_and_stops_normally():
    r=Rig();out=r.align({'x':3},slice_ms=10)
    a=r.c.alignments[0]
    assert out['x']==3 and not out['moving']
    assert r.actions==[('start',(1,0)),('stop',)] and len(r.runs)==3
    assert [s['position']['x'] for s in a['samples']]==[0,0,1,2,3,3]
    assert a['settled'] and a['guest_elapsed_ms']==30 and r.c.guest_budget_ms==1000


def test_range_is_declared_and_not_silently_expanded():
    r=Rig();out=r.align({'x':[2,4]})
    assert out['x']==2 and r.c.alignments[0]['targets']=={'x':[2,4]}


def test_diagonal_ranges_must_intersect_on_the_requested_leg():
    r=Rig();out=r.align({'x':[2,4],'y':[3,5]})
    assert (out['x'],out['y'])==(3,3) and r.actions[0]==('start',(1,1))
    bad=Rig()
    with pytest.raises(NativeControlError,match='separate straight'):
        bad.align({'x':3,'y':5})
    assert bad.actions==bad.runs==[]


def test_negative_unit_diagonal_remains_supported():
    r=Rig(x=5,y=5);out=r.align({'x':2,'y':2})
    assert (out['x'],out['y'])==(2,2) and r.actions[0]==('start',(-1,-1))


def test_initial_goal_in_motion_uses_stop_without_start():
    r=Rig(x=3,moving=True);out=r.align({'x':3})
    assert not out['moving'] and r.actions==[('stop',)] and r.runs==[]


def test_stop_may_settle_inside_an_explicit_range():
    r=Rig(x=3,moving=True)
    def stop():r.stop();r.value['x']=4
    assert r.align({'x':[2,4]},stop=stop)['x']==4


@pytest.mark.parametrize('patch,message',[
    ({'x':4},'overshoot'),({'x':-1},'opposite'),({'x':2,'y':1},'stationary axis'),
    ({'room':40},'context changed'),({'safe':False},'safety guard')])
def test_unsafe_or_displaced_sample_is_retained_without_recovery_input(patch,message):
    r=Rig();r.tick=lambda:r.value.update(patch)
    with pytest.raises(NativeControlError,match=message):r.align({'x':2})
    a=r.c.alignments[0]
    assert not a['complete'] and a['last_observation']==r.value and len(r.runs)==1
    assert r.actions==[('start',(1,0))] and r.c.blocked_reason
    with pytest.raises(NativeControlError):r.align({'x':2})
    assert len(r.runs)==1 and r.c.guest_budget_ms==1000


def test_diagonal_drift_is_refused_even_when_inside_goal_rectangle():
    r=Rig();r.tick=lambda:r.value.update(x=3,y=2)
    with pytest.raises(NativeControlError,match='unit-diagonal'):
        r.align({'x':[2,4],'y':[2,4]})
    assert r.c.alignments[0]['samples'][-1]['position']=={'x':3,'y':2}
    assert r.actions==[('start',(1,1))]


def test_settling_cannot_move_outside_an_exact_goal():
    r=Rig()
    def stop():r.stop();r.value['x']+=1
    with pytest.raises(NativeControlError,match='overshoot'):r.align({'x':1},stop=stop)
    assert r.c.alignments[0]['last_observation']['x']==2


def test_stalled_route_has_finite_poll_bound_and_no_automatic_reversal():
    r=Rig();r.tick=lambda:None
    with pytest.raises(NativeControlError,match='stalled'):r.align({'x':2},max_still_polls=2)
    assert len(r.runs)==2 and r.actions==[('start',(1,0))]


def test_poll_budget_is_checked_before_dispatching_an_unobservable_start():
    r=Rig()
    with pytest.raises(NativeControlError,match='before start'):r.align({'x':2},max_polls=1)
    assert r.actions==r.runs==[]


def test_poll_budget_is_checked_before_an_unobservable_next_slice():
    r=Rig()
    def start(direction):r.start(direction);r.c.advance(10)
    with pytest.raises(NativeControlError,match='before execution'):
        r.align({'x':3},start=start,max_polls=2)
    assert r.actions==[('start',(1,0))] and len(r.runs)==1
    assert r.c.alignments[0]['samples'][-1]['position']=={'x':1,'y':0}


def test_missing_context_is_not_a_qualified_stable_context():
    r=Rig()
    with pytest.raises(NativeControlError,match='context is unavailable'):
        r.align({'x':0},context=lambda s:None)
    assert r.actions==r.runs==[] and not r.c.alignments[0]['complete']


def test_start_callback_uses_the_local_cap_for_all_native_runs():
    r=Rig()
    def start(direction):r.start(direction);r.c.advance(100)
    with pytest.raises(NativeControlError):r.align({'x':10},start=start,budget=20)
    assert [s['guest_ms'] for s in r.runs]==[20] and r.c.guest_elapsed==20
    assert r.actions==[('start',(1,0))] and r.c.guest_budget_ms==1000


def test_exact_local_cap_can_succeed_when_already_settled():
    r=Rig()
    def tick():r.value.update(x=1,moving=False)
    r.tick=tick
    out=r.align({'x':1},budget=10,slice_ms=10)
    assert out['x']==1 and r.c.alignments[0]['complete'] and r.actions==[('start',(1,0))]


def test_no_stop_input_is_dispatched_after_local_guest_budget_is_consumed():
    r=Rig()
    with pytest.raises(NativeControlError,match='no remaining budget to settle'):
        r.align({'x':1},budget=10,slice_ms=10)
    assert r.actions==[('start',(1,0))] and len(r.runs)==1


def test_measured_overshoot_is_retained_before_another_run():
    r=Rig();normal=r.run
    def run(**kw):out=normal(**kw);out['guest_elapsed_ms']=115;return out
    r.run=run
    with pytest.raises(NativeControlError):r.align({'x':1},budget=100)
    assert r.c.guest_elapsed==115 and len(r.runs)==1 and not r.c.alignments[0]['complete']
    assert r.c.journal[-1]['result']['guest_elapsed_ms']==115


def test_slow_settlement_predicate_does_not_become_success():
    now=[0];r=Rig(clock=lambda:now[0])
    def settled(state):now[0]=11;return True
    with pytest.raises(NativeControlError,match='wall budget'):r.align({'x':0},settled=settled)
    assert r.runs==r.actions==[] and not r.c.alignments[0]['complete']


def test_owner_advance_adapter_keeps_progress_synchronized():
    r=Rig();owner={'guest':0};calls=[]
    def advance(ms):
        calls.append(ms);out=r.c.advance(ms);owner['guest']=r.c.guest_elapsed;return out
    r.c.input_advance=advance;r.align({'x':2})
    assert calls==[10,10] and owner['guest']==r.c.guest_elapsed==20


def test_foreign_stop_during_movement_is_not_resumed_or_stopped_by_more_input():
    r=Rig()
    def run(**kw):r.runs.append(kw);return {'outcome':'breakpoint','guest_elapsed_ms':3}
    r.run=run
    with pytest.raises(NativeControlError,match='Foreign'):r.align({'x':2})
    assert r.actions==[('start',(1,0))] and len(r.runs)==1
    assert r.c.alignments[0]['guest_elapsed_ms']==3 and r.c.blocked_reason


@pytest.mark.parametrize('targets',[{}, {'z':1},{'x':True},{'x':float('nan')},{'x':[2,1]},{'x':[1]}])
def test_invalid_targets_do_not_dispatch_inputs(targets):
    r=Rig()
    with pytest.raises(ValueError):r.align(targets)
    assert r.actions==r.runs==[]


def test_status_returns_copies_of_alignment_and_frame_records():
    r=Rig();r.align({'x':0});r.c.frame_captures.append({'complete':False})
    value=r.c.status();value['alignments'][0]['complete']=False;value['frame_captures'][0]['complete']=True
    assert r.c.alignments[0]['complete'] and not r.c.frame_captures[0]['complete']


@pytest.mark.parametrize('pickup,score,allowed',[(True,1,True),(False,1,False),(True,2,False)])
def test_inherited_mushroom_alignment_preserves_its_score_policy(pickup,score,allowed):
    from examples.agi.verify_mushroom import MushroomRun
    run=object.__new__(MushroomRun)
    run.guest_elapsed=0;run.pickup_active=pickup;run.samples=[];run.ready=lambda:None;run._idle=lambda:True
    state={'room':47,'score':score,'ego':{'x':110,'y':166,'direction':0},'control_direction':0,
           'dead':False,'in_water':False,'swimming':0,'bridge_active':False,'troll_paid':False,
           'troll_removed':False,'ego_width':6,'ego_view':0,'step_size':1}
    run.state=lambda:deepcopy(state)
    c=BoundedNativeController(None,read_state=run.state,total_guest_ms=1000,total_timeout_ms=1000)
    run._transport=lambda:c
    if allowed:assert run._precise(x=110)==state and c.alignments[0]['complete']
    else:
        with pytest.raises(RuntimeError,match='Unexpected score'):run._precise(x=110)
        assert not c.alignments[0]['complete'] and c.blocked_reason
    assert c.alignments[0]['last_observation']==state and run.samples[-1]['state']==state
