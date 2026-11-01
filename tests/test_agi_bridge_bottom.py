"""Authored stopping tests; no native game or assets."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from examples.agi.verify_bridge_bottom import BottomRun, classify


@pytest.mark.parametrize('name,fresh',[('row-start',True),('west-exit',True),
                                     ('over-water',False),('control-water',False)])
def test_frame_wrapper_only_requests_guest_progress_at_settled_boundaries(name,fresh):
    run=object.__new__(BottomRun);run.fast_forward=True;run.guest_elapsed=0
    run.inputs=[];run.messages=[];run.bottom_observations=[];seen=[]
    metadata={'source':'last_completed_guest_frame','frame_id':5,'mode_id':1}
    run.frame=lambda filename:dict(sha256='a'*64,metadata=metadata)
    run.d=SimpleNamespace(frame_probe=lambda points:seen.append(points))
    def capture(frame,**kwargs):
        assert 'status_reader' not in kwargs
        seen.append((kwargs['require_fresh'],run.fast_forward));item=frame()
        return dict(complete=True,state_after=state(),frame=item,issues=[],
                    freshness='confirmed' if fresh else 'not_requested')
    controller=SimpleNamespace(guest_elapsed=123,capture_frame_state=capture)
    run._transport=lambda:controller
    result=run.observe(name)
    assert seen==[(fresh,not fresh)] and run.fast_forward is True
    assert run.guest_elapsed==123 and result['frame']['path']==name+'.png'
    assert result['frame_state']['complete'] and run.bottom_observations==[result]


def test_incomplete_frame_bracket_is_retained_before_route_refusal():
    run=object.__new__(BottomRun);run.fast_forward=False;run.guest_elapsed=0
    run.inputs=[];run.messages=[];run.bottom_observations=[]
    captured=dict(complete=False,state_after=state(),frame=None,issues=['missing frame'],freshness='not_observed')
    run.d=SimpleNamespace(call=lambda method:None)
    run._transport=lambda:SimpleNamespace(guest_elapsed=20,capture_frame_state=lambda *a,**k:captured)
    with pytest.raises(RuntimeError,match='Frame/state observation incomplete'):run.observe('row-start')
    assert run.bottom_observations[0]['frame_state']==captured
    assert run.guest_elapsed==20 and run.fast_forward is False


def state(**changes):
    s={'room':39,'score':0,'ego':{'x':110,'y':166,'direction':0,'drawn':True},
       'dead':False,'in_water':False,'swimming':0,'bridge_active':False,
       'troll_paid':False,'troll_removed':False,'ego_width':6,'ego_view':0,
       'step_size':1,'edge':0,'ignore_blocks':True}
    s.update(changes);return s


def test_control_water_and_bottom_transition_are_distinct():
    assert classify(state(in_water=True,ego={'x':80,'y':166}),target_y=166,crossing_seen=False)=='control-water'
    assert classify(state(in_water=True),target_y=166,crossing_seen=False)=='unsafe'
    assert classify(state(in_water=True),target_y=167,crossing_seen=False)=='unsafe'
    assert classify(state(dead=True,in_water=True),target_y=166,crossing_seen=False)=='unsafe'
    assert classify(state(room=26),target_y=167,crossing_seen=True)=='bottom-transition'
    assert classify(state(room=40),target_y=167,crossing_seen=False)=='unexpected-room'
    assert classify(state(room=40),target_y=167,crossing_seen=True)=='west-exit'


@pytest.mark.parametrize('patch,expected',[
    ({'edge':3},'border-pending'),({'ignore_blocks':False},'blocks-enabled'),
    ({'ego':{'x':90,'y':165}},'displaced-row'),({'bridge_active':True},'unexpected-state'),
    ({'ego_width':4},'unexpected-state'),({'score':1},'unexpected-state')])
def test_unqualified_conditions_stop(patch,expected):
    assert classify(state(**patch),target_y=166,crossing_seen=False)==expected


class Fake:
    run_case=BottomRun.run_case
    def __init__(self,following):
        self.current=state();self.following=following;self.guest_elapsed=0
        self.bottom_samples=[];self.actions=[]
    def prefix(self):self.actions.append('prefix')
    def safe_state(self):return deepcopy(self.current)
    def state(self):return deepcopy(self.current)
    def precise(self,*,y):self.actions.append('precise:'+str(y));self.current['ego']['y']=y
    def _idle(self):return True
    def observe(self,name):self.actions.append('observe:'+name);return {'state':self.state()}
    def press(self,*a,**k):self.actions.append('press:'+a[0]);self.current=self.following
    def advance(self,*a):self.actions.append('UNEXPECTED_ADVANCE');raise AssertionError('resumed after stop')


def test_control_stops_without_another_guest_run_or_input():
    f=Fake(state(in_water=True,ego={'x':82,'y':166,'direction':7,'drawn':True}))
    out=f.run_case(166)
    assert out['result']=='adjacent-row-water-observed'
    assert f.actions==['prefix','observe:row-start','press:left','observe:control-water']
    assert len(f.bottom_samples)==1


@pytest.mark.parametrize('change',[{'room':26},{'dead':True},{'edge':3},{'ignore_blocks':False}])
def test_unsafe_post_input_stop_does_not_resume(change):
    f=Fake(state(**change))
    with pytest.raises(RuntimeError):f.run_case(166)
    assert f.actions==['prefix','observe:row-start','press:left']
    assert len(f.bottom_samples)==1


def test_bottom_row_transition_to_26_is_not_crossing_or_resumed():
    f=Fake(state(room=26,ego={'x':110,'y':44,'direction':0,'drawn':True}))
    with pytest.raises(RuntimeError,match='bottom-transition'):f.run_case(167)
    assert f.actions==['prefix','precise:167','observe:row-start','press:left']
    assert len(f.bottom_samples)==1


def test_room40_cannot_trigger_neutral_on_unqualified_score():
    bad=state(room=40,score=1)
    assert classify(bad,target_y=167,crossing_seen=True)=='unexpected-state'


def test_only_observed_west_boundary_can_finish_ordinary_exit():
    s=state(edge=4,control_direction=7,initializing=False,window=0,
            ego={'x':0,'y':167,'direction':7,'drawn':True})
    assert classify(s,target_y=167,crossing_seen=True)=='west-border'
    assert classify(s,target_y=167,crossing_seen=False)=='border-pending'
    assert classify(s,target_y=166,crossing_seen=True)=='border-pending'
    for patch in ({'edge':3},{'window':1},{'initializing':True},{'control_direction':0}):
        assert classify({**s,**patch},target_y=167,crossing_seen=True)=='border-pending'


def test_expected_room_initialization_waits_before_requiring_drawn_actor():
    s=state(room=40,initializing=True,ignore_blocks=False,
            ego={'x':154,'y':167,'direction':0,'drawn':False})
    assert classify(s,target_y=167,crossing_seen=True)=='arrival-pending'
    assert classify(s,target_y=167,crossing_seen=False)=='unexpected-state'
    assert classify({**s,'initializing':False},target_y=167,crossing_seen=True)=='unexpected-state'
    assert classify({**s,'dead':True},target_y=167,crossing_seen=True)=='unsafe'
    assert classify({**s,'score':1},target_y=167,crossing_seen=True)=='unexpected-state'


def test_failed_key_delivery_is_never_replayed():
    class Lost(Fake):
        def press(self,*args,**kwargs):
            self.actions.append('press:'+args[0])
            raise OSError('authored lost keyboard reply')
    f=Lost(state())
    with pytest.raises(OSError,match='lost keyboard reply'):f.run_case(166)
    assert f.actions==['prefix','observe:row-start','press:left']
    assert not f.bottom_samples
