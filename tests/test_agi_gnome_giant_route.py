"""Authored QuestRun control tests; no original game or native execution."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest
import examples.agi.verify_gnome_giant as module


def initial_state():
    return {'room':40, 'score':14, 'shield_carried':True, 'key_carried':False,
            'chest_carried':False, 'quest_variables':{'84':0},
            'quest_flags':{'21':False,'22':False,'23':True,'102':True}}


def authored_run(tmp_path):
    run=object.__new__(module.QuestRun)
    run.root=tmp_path;run.guest_elapsed=0;run.inputs=[];run.messages=[];run.clip_actions=[]
    run.report={};run.quest_probe=None;run.motion_probe=None;run.distance_probe=None
    run.capture_checkpoints=False;run.execution_blocked=False
    run.guess_observations=[];run.events=[];run.current=initial_state();run.frame_id=0
    run.safe_state=lambda:deepcopy(run.current)
    run.ready=lambda:run.events.append(('ready',))
    def advance(ms):
        run.events.append(('advance',ms));run.guest_elapsed+=ms
    run.advance=advance
    def screenshot(name,*,hooks):
        run.events.append(('screenshot',name,hooks));run.frame_id+=1
        return {'metadata':{'frame_id':run.frame_id,'mode_id':5}}
    run.d=SimpleNamespace(screenshot=screenshot)
    def frame(name):
        run.frame_id+=1;run.events.append(('frame',name))
        return {'sha256':sha256(name.encode()).hexdigest(),'metadata':{'frame_id':run.frame_id,'mode_id':5}}
    run.frame=frame
    def command(text):
        run.events.append(('command',text));run.inputs.append({'key':text})
        if text=='hi':run.current['quest_flags']['22']=True
        if text=='get key':run.current['quest_variables']['84']=1
    run.command=command
    def press(key,duration,**kwargs):
        run.events.append(('press',key,duration,kwargs));run.inputs.append({'key':key})
        if key=='enter':
            run.current['quest_variables']['84']+=1
            if run.current['quest_variables']['84']==3:
                run.current['quest_flags']['22']=False;run.current['quest_flags']['21']=True
    run.press=press
    def wait_for(predicate,label,*args):
        run.events.append(('wait',label));assert predicate(run.current);return deepcopy(run.current)
    run.wait_for=wait_for
    def quest_action(name,before,after,start):
        run.events.append(('action',name,before,after,start))
        run.clip_actions.append({'id':name,'before':before,'after':after})
    run.quest_action=quest_action
    return run


def room68_run(tmp_path, selectors=(200,)):
    run=authored_run(tmp_path)
    run.current.update(room=68,score=19,key_carried=True,initializing=False,window=0,
                       player_control=1,ego={'x':95,'y':159,'direction':0,'drawn':True},
                       quest_actors={'1':{'drawn':False}})
    run.current['quest_flags'].update({'148':True,'23':selectors[0]<150})
    run.current['quest_variables'].update({'1':67,'62':selectors[0],'70':0})
    run.resources={68:SimpleNamespace(resource_sha256='779fcbf87c2c07318e24289fdf5d5619e5615e09e972543fa456d7a62bba4469')}
    run._idle=lambda:True
    remaining=iter(selectors[1:])
    def precise(**targets):
        run.events.append(('precise',targets));run.current['ego'].update(targets)
    run.precise=precise
    def stair_ready(room,point):
        run.events.append(('stair-ready',room,point));run.current['room']=room
        run.current['ego'].update(x=point[0],y=point[1])
        if room==68:
            value=next(remaining)
            run.current['quest_variables'].update({'1':67,'62':value,'70':0})
            run.current['quest_flags']['23']=value<150
    run.stair_ready=stair_ready
    return run


def test_room68_empty_visit_requires_no_input(tmp_path):
    run=room68_run(tmp_path);run.admit_room68()
    assert run.events==[] and run.report['room68_visits'][0]['admitted'] is True
    assert len(run.report['room68_visits'])==1


def test_hidden_eligible_dwarf_is_retired_through_observed_room_transitions(tmp_path):
    run=room68_run(tmp_path,(132,200));run.admit_room68()
    assert [v['admitted'] for v in run.report['room68_visits']]==[False,True]
    assert run.events==[('precise',{'x':94}),('precise',{'y':165}),
        ('press','down',20,{'hold_ms':1,'gap_ms':1}),('stair-ready',67,(119,42)),
        ('press','up',20,{'hold_ms':1,'gap_ms':1}),('stair-ready',68,(95,159))]
    assert run.report['room68_visits'][0]['retreat_state']['room']==67
    assert run.current['score']==19 and run.current['shield_carried']


@pytest.mark.parametrize('fault',['source','repeat','random_bool','random_range','timer_bool','timer_range',
    'contradictory_flag','scheduled_timer','drawn','wrong_previous','position','direction','control',
    'initializing','window','entry_callback','keyboard','key','chest','shield'])
def test_room68_inconsistent_entry_is_preserved_without_input(tmp_path,fault):
    run=room68_run(tmp_path)
    if fault=='source':run.resources[68].resource_sha256='0'*64
    if fault=='repeat':run.report['room68_visits']=[{'prior':True}]
    if fault=='random_bool':run.current['quest_variables']['62']=True
    if fault=='random_range':run.current['quest_variables']['62']=251
    if fault=='timer_bool':run.current['quest_variables']['70']=False
    if fault=='timer_range':run.current['quest_variables']['70']=46
    if fault=='contradictory_flag':run.current['quest_flags']['23']=True
    if fault=='scheduled_timer':run.current['quest_variables']['70']=4
    if fault=='drawn':run.current['quest_actors']['1']['drawn']=True
    if fault=='wrong_previous':run.current['quest_variables']['1']=69
    if fault=='position':run.current['ego']['x']=96
    if fault=='direction':run.current['ego']['direction']=3
    if fault=='control':run.current['player_control']=0
    if fault=='initializing':run.current['initializing']=True
    if fault=='window':run.current['window']=1
    if fault=='entry_callback':run.current['quest_flags']['148']=False
    if fault=='keyboard':run._idle=lambda:False
    if fault=='key':run.current['key_carried']=False
    if fault=='chest':run.current['chest_carried']=True
    if fault=='shield':run.current['shield_carried']=False
    before=deepcopy(run.current)
    with pytest.raises(RuntimeError):run.admit_room68()
    assert run.events==[] and run.current==before


def test_room68_visit_budget_is_finite_and_does_not_start_a_seventeenth_visit(tmp_path):
    run=room68_run(tmp_path,(132,)*16)
    with pytest.raises(RuntimeError,match='budget exhausted'):run.admit_room68()
    assert len(run.report['room68_visits'])==16
    assert sum(event[0]=='stair-ready' and event[1]==68 for event in run.events)==15
    assert not any(v['admitted'] for v in run.report['room68_visits'])


def test_room68_uncertain_retreat_does_not_send_reentry(tmp_path):
    run=room68_run(tmp_path,(132,200))
    def uncertain(**targets):raise RuntimeError('retreat not observed')
    run.precise=uncertain
    with pytest.raises(RuntimeError,match='not observed'):run.admit_room68()
    assert len(run.report['room68_visits'])==1 and run.events==[]


def test_active_probe_receives_stop_and_inactive_delegates(monkeypatch,tmp_path):
    run=authored_run(tmp_path);calls=[];stop={'authored':'stop'}
    monkeypatch.setattr(module.CaveRun,'handle_stop',lambda self,out:calls.append(('inherited',out)) or 'parent')
    run.quest_probe=SimpleNamespace(active=True,handle_stop=lambda out:calls.append(('probe',out)) or 'owned')
    assert run.handle_stop(stop)=='owned' and calls==[('probe',stop)]
    run.quest_probe.active=False
    assert run.handle_stop(stop)=='parent' and calls[-1]==('inherited',stop)
    run.quest_probe=None
    assert run.handle_stop(stop)=='parent' and len(calls)==3


def test_message_observation_uses_current_guest_time_without_advancing(tmp_path):
    run=authored_run(tmp_path);run.guest_elapsed=237;msg={'status':'completed'}
    run.message_observed(msg)
    assert msg=={'status':'completed','guest_ms':237} and run.events==[] and run.guest_elapsed==237


@pytest.mark.parametrize('change',[{'shield_carried':False},{'room':39},{'score':13}])
def test_quest_safety_rejects_missing_shield_wrong_room_or_score(tmp_path,change):
    run=authored_run(tmp_path);run.current.update(change)
    with pytest.raises(RuntimeError):run.quest_safe(40,14)
    assert run.events==[]


def test_quest_safety_rejects_unset_shield_flag(tmp_path):
    run=authored_run(tmp_path);run.current['quest_flags']['102']=False
    with pytest.raises(RuntimeError,match='shield'):run.quest_safe(40,14)


def test_wrong_names_use_one_typed_guess_then_original_repeat_key(tmp_path):
    run=authored_run(tmp_path);run.gnome()
    events=[e for e in run.events if e[0] in ('command','press')]
    assert events==[('command','hi'),('command','get key'),
        ('press','f3',100,{'hold_ms':1,'gap_ms':1}),('press','enter',300,{'hold_ms':1,'gap_ms':1}),
        ('press','f3',100,{'hold_ms':1,'gap_ms':1}),('press','enter',300,{'hold_ms':1,'gap_ms':1})]
    assert [x['stage'] for x in run.guess_observations]==[1,2,3]
    assert [x['guest_ms'] for x in run.guess_observations]==[50,100,150]
    assert [x['state']['quest_flags']['21'] for x in run.guess_observations]==[False,False,True]
    assert [x['frame']['metadata']['frame_id'] for x in run.guess_observations]==[2,4,6]
    assert run.clip_actions==[{'id':'wrong-names','before':'gnome-ready','after':'key-on-ground'}]


@pytest.mark.parametrize('fault',['stage','carried','already_dialogue','key_actor'])
def test_gnome_rejects_invalid_initial_state_before_any_input(tmp_path,fault):
    run=authored_run(tmp_path)
    if fault=='stage':run.current['quest_variables']['84']=1
    if fault=='carried':run.current['key_carried']=True
    if fault=='already_dialogue':run.current['quest_flags']['22']=True
    if fault=='key_actor':run.current['quest_flags']['21']=True
    with pytest.raises(RuntimeError):run.gnome()
    assert not run.inputs and not run.guess_observations and not run.clip_actions


@pytest.mark.parametrize('fault',['stage','carried','dialogue','key_actor'])
def test_guess_frame_rejects_contradiction_after_freshness_advance(tmp_path,fault):
    run=authored_run(tmp_path);run.current['quest_variables']['84']=1;run.current['quest_flags']['22']=True
    def advance(ms):
        run.guest_elapsed+=ms
        if fault=='stage':run.current['quest_variables']['84']=2
        if fault=='carried':run.current['key_carried']=True
        if fault=='dialogue':run.current['quest_flags']['22']=False
        if fault=='key_actor':run.current['quest_flags']['21']=True
    run.advance=advance
    with pytest.raises(RuntimeError):run.guess_frame(1)
    assert run.guess_observations==[]


def test_guess_failure_preserves_earlier_frames_without_new_action(tmp_path):
    run=authored_run(tmp_path);original=run.frame
    def frame(name):
        if name=='gnome-guess-2.png':raise OSError('authored frame loss')
        return original(name)
    run.frame=frame
    with pytest.raises(OSError,match='frame loss'):run.gnome()
    assert [x['stage'] for x in run.guess_observations]==[1] and not run.clip_actions
    assert [e[1] for e in run.events if e[0]=='press']==['f3','enter']


@pytest.mark.parametrize('name,values',[('key',(40,5,0x2d6,0x2db,3,14,('item','return','score'))),
                                         ('chest',(58,2,0x25d,0x25a,8,26,('score','item','return')))])
def test_pickup_constructs_distinct_probe_and_binds_only_complete_action(tmp_path,monkeypatch,name,values):
    run=authored_run(tmp_path);logic,item,off,score_off,delta,before,order=values
    run.current.update(room=logic,score=before)
    created=[]
    class Probe:
        def __init__(self,owner,**kwargs):
            assert owner is run;created.append(kwargs);self.active=False;self.proof={'complete':False}
        def start(self):self.active=True;run.events.append(('probe-start',))
    class Distance:
        def __init__(self,owner):
            assert owner is run;self.active=False;self.stage='write';self.proof={'complete':False}
        def start(self):self.active=True;run.events.append(('distance-start',))
        def handle_stop(self,out):
            assert not run.quest_probe.active
            run.events.append(('distance-stop',out['stage']))
            assert out['stage']==self.stage
            if self.stage=='write':self.stage='return';return
            (tmp_path/'giant-distance.private.json').write_bytes(b'authored distance')
            self.proof={'complete':True,'status':'verified','native_execution':True};self.active=False
    monkeypatch.setattr(module,'PickupProbe',Probe)
    monkeypatch.setattr(module,'DistanceProbe',Distance)
    def command(text):
        assert text=='get '+name
        run.events.append(('command',text));run.inputs.append({'key':text})
        if name=='chest':
            assert run.distance_probe.active and not run.quest_probe.active
            run.handle_stop({'stage':'write'})
            assert not run.quest_probe.active
            run.handle_stop({'stage':'return'})
        assert run.quest_probe.active
        (tmp_path/(name+'-pickup.private.json')).write_bytes(b'authored proof')
        run.quest_probe.proof={'complete':True,'status':'verified','native_execution':True}
        run.quest_probe.active=False;run.current[name+'_carried']=True;run.current['score']=before+delta
    run.command=command
    run.pickup(name)
    assert created==[{'name':name,'logic':logic,'item':item,'item_offset':off,'score_offset':score_off,
                      'score_delta':delta,'before_score':before,'order':order}]
    if name=='chest':
        assert [e for e in run.events if e[0] in ('probe-start','distance-start','command','distance-stop')]==[
            ('distance-start',),('command','get chest'),('distance-stop','write'),
            ('distance-stop','return'),('probe-start',)]
        assert run.clip_actions[-1]['native_distance']=={'path':'giant-distance.private.json',
            'sha256':sha256(b'authored distance').hexdigest()}
    else:assert run.events.index(('probe-start',))<run.events.index(('command','get '+name))
    assert run.clip_actions[-1]['native_pickup']=={'path':name+'-pickup.private.json','sha256':sha256(b'authored proof').hexdigest()}


def test_probe_start_failure_sends_no_pickup_input(tmp_path,monkeypatch):
    run=authored_run(tmp_path)
    class Probe:
        def __init__(self,owner,**kwargs):self.active=False
        def start(self):raise RuntimeError('authored arm failure')
    monkeypatch.setattr(module,'PickupProbe',Probe)
    with pytest.raises(RuntimeError,match='arm failure'):run.get_key()
    assert not run.inputs and not run.clip_actions and not any(e[0]=='command' for e in run.events)


def test_incomplete_pickup_proof_never_produces_action(tmp_path,monkeypatch):
    run=authored_run(tmp_path)
    class Probe:
        def __init__(self,owner,**kwargs):self.active=True;self.proof={'complete':False}
        def start(self):pass
    monkeypatch.setattr(module,'PickupProbe',Probe)
    def command(text):run.quest_probe.active=False;run.current['key_carried']=True;run.current['score']=17
    run.command=command
    with pytest.raises(RuntimeError,match='proof incomplete'):run.get_key()
    assert not run.clip_actions


@pytest.mark.parametrize('fault',['unchanged','older'])
def test_guess_frame_rejects_nonfresh_stored_frame(tmp_path,fault):
    run=authored_run(tmp_path);run.current['quest_variables']['84']=1;run.current['quest_flags']['22']=True
    run.frame=lambda name:{'sha256':sha256(name.encode()).hexdigest(),
                           'metadata':{'frame_id':1 if fault=='unchanged' else 0,'mode_id':5}}
    with pytest.raises(RuntimeError,match='fresh'):run.guess_frame(1)
    assert not run.guess_observations


def test_observe_clip_adds_guest_timestamp_without_advancing(monkeypatch,tmp_path):
    run=authored_run(tmp_path);run.guest_elapsed=190;run.clip_observations={}
    def observe(self,name):
        self.clip_observations[name]={'state':{'authored':True},'frame':{'sha256':'f'*64}}
        return name
    monkeypatch.setattr(module.CaveRun,'observe_clip',observe)
    assert module.QuestRun.observe_clip(run,'authored')=='authored'
    assert run.clip_observations['authored']['guest_ms']==190 and not run.events


@pytest.mark.parametrize('stage,prior',[(True,0),(0,0),(4,0),(2,0),(1,1)])
def test_guess_snapshots_require_exact_order_and_integer_stage(tmp_path,stage,prior):
    run=authored_run(tmp_path);run.guess_observations=[{'stage':1}]*prior
    with pytest.raises(RuntimeError,match='out of order'):run.guess_frame(stage)
    assert not run.events and len(run.guess_observations)==prior


def test_guess_frame_rejects_changed_video_mode(tmp_path):
    run=authored_run(tmp_path);run.current['quest_variables']['84']=1;run.current['quest_flags']['22']=True
    run.frame=lambda name:{'sha256':sha256(name.encode()).hexdigest(),'metadata':{'frame_id':2,'mode_id':6}}
    with pytest.raises(RuntimeError,match='fresh'):run.guess_frame(1)
    assert not run.guess_observations


@pytest.mark.parametrize('field,value',[('status','incomplete'),('native_execution',False),('complete',False)])
def test_contradictory_pickup_proof_cannot_produce_action(tmp_path,monkeypatch,field,value):
    run=authored_run(tmp_path)
    class Probe:
        def __init__(self,owner,**kwargs):self.active=True;self.proof={'complete':True,'status':'verified','native_execution':True}
        def start(self):pass
    monkeypatch.setattr(module,'PickupProbe',Probe)
    def command(text):
        run.quest_probe.active=False;run.quest_probe.proof[field]=value
        run.current['key_carried']=True;run.current['score']=17
    run.command=command
    with pytest.raises(RuntimeError,match='proof incomplete'):run.get_key()
    assert not run.clip_actions


@pytest.mark.parametrize('fault',['control_before','idle_before','control_after','idle_after'])
def test_quest_action_requires_control_and_idle_across_capture(tmp_path,fault):
    run=authored_run(tmp_path);run.clip_observations={};run.current['player_control']=0 if fault=='control_before' else 1
    run.state=lambda:deepcopy(run.current)
    idle_calls=[]
    def idle():
        idle_calls.append(True)
        return not (fault=='idle_before' and len(idle_calls)==1 or fault=='idle_after' and len(idle_calls)==2)
    run._idle=idle
    def observe(name):
        state=deepcopy(run.current)
        if fault=='control_after':state['player_control']=0
        run.clip_observations[name]={'state':state};return name
    run.observe_clip=observe
    run.action=lambda *args:run.clip_actions.append(args)
    with pytest.raises(RuntimeError,match='controls'):module.QuestRun.quest_action(run,'action','before','after',(0,0))
    assert not run.clip_actions


@pytest.mark.parametrize('fault',['missing_mode','boolean_mode','boolean_frame','missing_frame'])
def test_guess_frame_rejects_missing_or_boolean_identity(tmp_path,fault):
    run=authored_run(tmp_path);run.current['quest_variables']['84']=1;run.current['quest_flags']['22']=True
    before={'frame_id':0,'mode_id':5};after={'frame_id':2,'mode_id':5}
    if fault=='missing_mode':before.pop('mode_id');after.pop('mode_id')
    if fault=='boolean_mode':before['mode_id']=True;after['mode_id']=1
    if fault=='boolean_frame':after['frame_id']=True
    if fault=='missing_frame':after.pop('frame_id')
    run.d.screenshot=lambda *args,**kwargs:{'metadata':before}
    run.frame=lambda name:{'sha256':sha256(name.encode()).hexdigest(),'metadata':after}
    with pytest.raises((RuntimeError,KeyError)):run.guess_frame(1)
    assert not run.guess_observations


def test_quest_action_records_only_after_ready_capture(tmp_path):
    run=authored_run(tmp_path);run.current['player_control']=1;run.clip_observations={}
    run.state=lambda:deepcopy(run.current);run._idle=lambda:True
    def observe(name):
        run.events.append(('capture',name));run.clip_observations[name]={'state':deepcopy(run.current)}
    run.observe_clip=observe
    run.action=lambda *args:run.clip_actions.append(args)
    module.QuestRun.quest_action(run,'move','from','to',(2,3))
    assert run.events==[('ready',),('capture','to')]
    assert run.clip_actions==[('move','from','to',2,3)]


def test_failed_active_probe_stop_never_falls_back_to_cave_handler(monkeypatch,tmp_path):
    run=authored_run(tmp_path);fallback=[]
    monkeypatch.setattr(module.CaveRun,'handle_stop',lambda self,out:fallback.append(out))
    def fail(out):raise RuntimeError('authored stop unknown')
    run.quest_probe=SimpleNamespace(active=True,failed=True,handle_stop=fail)
    with pytest.raises(RuntimeError,match='stop unknown'):run.handle_stop({'outcome':'breakpoint'})
    assert not fallback and not run.events


def sleeping_run(tmp_path):
    run=authored_run(tmp_path);run.journal=[]
    run.current.update(room=58,score=26,ego={'x':10,'y':130},ego_width=6,ignore_blocks=False,
        quest_actors={'1':{'x':70,'y':70,'width':20,'height':20,'view':52,'drawn':True,
                           'motion':0,'direction':0,'motion_bit':False}},
        quest_variables={'86':1,'70':0},quest_flags={'102':True,'205':True,'104':False},chest_carried=False)
    run.plans=[];run.moves=[]
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append((room,start,target,allow_priority_one))
        return {'status':'found','path':[list(start),list(target)]},None
    run.path_model=plan
    def move(x,y):
        run.moves.append((x,y));run.current['ego']={'x':x,'y':y}
    run.static_path=move
    return run


@pytest.mark.parametrize('fault',['wrong_room','wrong_score','shield','unscored','v86','view','undrawn','motion','direction','chest'])
def test_sleeping_giant_rejects_invalid_initial_state_before_path(tmp_path,fault):
    run=sleeping_run(tmp_path);s=run.current;a=s['quest_actors']['1']
    if fault=='wrong_room':s['room']=59
    if fault=='wrong_score':s['score']=19
    if fault=='shield':s['shield_carried']=False
    if fault=='unscored':s['quest_flags']['205']=False
    if fault=='v86':s['quest_variables']['86']=0
    if fault=='view':a['view']=36
    if fault=='undrawn':a['drawn']=False
    if fault=='motion':a['motion']=1
    if fault=='direction':a['direction']=7
    if fault=='chest':s['chest_carried']=True
    with pytest.raises(RuntimeError):run.approach_sleeping_giant()
    assert not run.plans and not run.moves and not run.inputs and run.guest_elapsed in (0,100)


@pytest.mark.parametrize('motion_bit',[False,True])
def test_sleeping_giant_at_qualified_distance_needs_no_path_or_input(tmp_path,motion_bit):
    run=sleeping_run(tmp_path);run.current['ego']={'x':56,'y':70};run.current['quest_variables']['70']=21
    run.current['quest_actors']['1']['motion_bit']=motion_bit
    run.approach_sleeping_giant()
    assert run.events==[('advance',100)] and not run.plans and not run.moves and not run.inputs
    assert run.report['pre_chest_geometry']['distance']==21
    assert run.report['pre_chest_geometry']['native_distance_observed'] is False


@pytest.mark.parametrize('field,value',[('motion',False),('motion',0.0),('direction',False),('direction',0.0)])
def test_sleeping_giant_motion_and_direction_are_typed_native_bytes(tmp_path,field,value):
    run=sleeping_run(tmp_path);run.current['quest_actors']['1'][field]=value
    with pytest.raises(RuntimeError,match='sleeping giant'):run.approach_sleeping_giant()
    assert not run.plans and not run.moves and not run.inputs


@pytest.mark.parametrize('status',['unreachable','blocked_endpoint','budget_exhausted'])
def test_sleeping_giant_rejects_missing_static_proposal_without_input(tmp_path,status):
    run=sleeping_run(tmp_path)
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append(target);return {'status':status,'path':[]},None
    run.path_model=plan
    with pytest.raises(RuntimeError,match='No conservative'):run.approach_sleeping_giant()
    assert run.plans and not run.moves and not run.inputs and not run.journal


def test_sleeping_giant_uses_one_proposal_and_rechecks_host_geometry(tmp_path):
    run=sleeping_run(tmp_path);run.approach_sleeping_giant()
    assert len(run.moves)==1 and len(run.journal)==1 and not run.inputs
    assert run.guest_elapsed==200 and run.journal[0]['target']==run.moves[0]
    s=run.current;a=s['quest_actors']['1'];e=s['ego']
    assert run.report['pre_chest_geometry']['distance']==abs(e['x']+3-a['x']-a['width']//2)+abs(e['y']-a['y'])<=30
    assert run.report['pre_chest_geometry']['kind']=='host-derived'
    assert run.report['pre_chest_geometry']['native_distance_observed'] is False
    assert s['quest_variables']['70']==0


@pytest.mark.parametrize('fault',['changed_actor','changed_width','changed_height','motion','direction','view','unscored','chest'])
def test_sleeping_giant_rejects_changed_actor_or_state_after_approach(tmp_path,fault):
    run=sleeping_run(tmp_path);move=run.static_path
    def change(x,y):
        move(x,y);s=run.current;a=s['quest_actors']['1']
        if fault=='changed_actor':a['x']+=1;s['quest_variables']['70']=abs(x+3-a['x']-a['width']//2)+abs(y-a['y'])
        if fault=='changed_width':a['width']+=2;s['quest_variables']['70']=abs(x+3-a['x']-a['width']//2)+abs(y-a['y'])
        if fault=='changed_height':a['height']+=1
        if fault=='motion':a['motion']=1
        if fault=='direction':a['direction']=7
        if fault=='view':a['view']=36
        if fault=='unscored':s['quest_flags']['205']=False
        if fault=='chest':s['chest_carried']=True
    run.static_path=change
    with pytest.raises(RuntimeError):run.approach_sleeping_giant()
    assert len(run.moves)==1 and not run.inputs


def door_run(tmp_path):
    run=authored_run(tmp_path);run.current.update(room=19,score=19,ignore_blocks=True,player_control=1,
        quest_variables={'66':2},quest_actors={'1':{'view':20,'cel':3,'drawn':True}})
    run._idle=lambda:True
    return run


def test_door_frame_qualifies_original_pose_and_stored_fresh_timestamp(tmp_path):
    run=door_run(tmp_path);run.door_frame()
    assert run.door_observation['guest_ms']==50
    assert run.door_observation['state']['quest_actors']['1']=={'view':20,'cel':3,'drawn':True}
    assert run.door_observation['frame']['metadata']=={'frame_id':2,'mode_id':5}


@pytest.mark.parametrize('phase',['before','after'])
@pytest.mark.parametrize('field,value',[('variable',1),('view',21),('cel',2),('drawn',False),('ignore_blocks',False),('player_control',0)])
def test_door_frame_rejects_nonready_or_changed_state(tmp_path,phase,field,value):
    run=door_run(tmp_path)
    def change():
        s=run.current
        if field=='variable':s['quest_variables']['66']=value
        elif field in ('view','cel','drawn'):s['quest_actors']['1'][field]=value
        else:s[field]=value
    if phase=='before':change()
    else:
        def advance(ms):run.guest_elapsed+=ms;change()
        run.advance=advance
    with pytest.raises(RuntimeError,match='door animation'):run.door_frame()
    assert not hasattr(run,'door_observation')


@pytest.mark.parametrize('fault',['stale','wrong_mode','bool_mode','bool_frame','idle_before','idle_after'])
def test_door_frame_rejects_unqualified_identity_or_keyboard(tmp_path,fault):
    run=door_run(tmp_path);calls=[]
    if fault=='idle_before':run._idle=lambda:False
    if fault=='idle_after':
        def idle():calls.append(1);return len(calls)==1
        run._idle=idle
    if fault in ('stale','wrong_mode','bool_mode','bool_frame'):
        prior={'frame_id':0 if fault=='bool_frame' else 1,'mode_id':True if fault=='bool_mode' else 5}
        after={'frame_id':True if fault=='bool_frame' else 1 if fault=='stale' else 2,
               'mode_id':1 if fault=='bool_mode' else 6 if fault=='wrong_mode' else 5}
        run.d.screenshot=lambda *a,**k:{'metadata':prior}
        run.frame=lambda name:{'sha256':sha256(name.encode()).hexdigest(),'metadata':after}
    with pytest.raises(RuntimeError):run.door_frame()
    assert not hasattr(run,'door_observation')


def test_sleeping_giant_refuses_static_path_through_actor_body(tmp_path):
    run=sleeping_run(tmp_path)
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append(target)
        return {'status':'found','path':[list(start),[70,70],list(target)]},None
    run.path_model=plan
    with pytest.raises(RuntimeError,match='No conservative'):run.approach_sleeping_giant()
    assert run.plans and not run.moves and not run.inputs


@pytest.mark.parametrize('stale_distance',[0,22,255])
def test_near_giant_accepts_host_geometry_without_claiming_stale_native_distance(tmp_path,stale_distance):
    run=sleeping_run(tmp_path);run.current['ego']={'x':56,'y':70};run.current['quest_variables']['70']=stale_distance
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append(target);return {'status':'blocked_endpoint','path':[]},None
    run.path_model=plan
    run.approach_sleeping_giant()
    assert not run.plans and not run.moves and not run.inputs
    assert run.current['quest_variables']['70']==stale_distance
    assert run.report['pre_chest_geometry']['distance']==21
    assert run.report['pre_chest_geometry']['native_distance_observed'] is False


@pytest.mark.parametrize('fault',['position','y_position','width','height','motion','direction','unscored','already_taken'])
def test_sleeping_giant_requires_stable_initial_observation(tmp_path,fault):
    run=sleeping_run(tmp_path)
    def advance(ms):
        run.guest_elapsed+=ms;a=run.current['quest_actors']['1']
        if fault=='position':a['x']+=1
        if fault=='y_position':a['y']+=1
        if fault=='width':a['width']+=1
        if fault=='height':a['height']+=1
        if fault=='motion':a['motion']=1
        if fault=='direction':a['direction']=7
        if fault=='unscored':run.current['quest_flags']['205']=False
        if fault=='already_taken':run.current['quest_flags']['104']=True
    run.advance=advance
    with pytest.raises(RuntimeError):run.approach_sleeping_giant()
    assert not run.plans and not run.moves and not run.inputs


@pytest.mark.parametrize('fault',['empty','wrong_start','wrong_end'])
def test_sleeping_giant_rejects_missing_or_unbound_found_path(tmp_path,fault):
    run=sleeping_run(tmp_path)
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append(target)
        path=[] if fault=='empty' else [[0,0],list(target)] if fault=='wrong_start' else [list(start),[1,1]]
        return {'status':'found','path':path},None
    run.path_model=plan
    with pytest.raises(RuntimeError):run.approach_sleeping_giant()
    assert run.plans and not run.moves and not run.inputs


def test_main_retains_completed_prefix_trace_when_first_artifact_write_fails(tmp_path,monkeypatch):
    """A real authored shield stop reaches the failed final-artifact branch."""
    from contextlib import contextmanager
    import json
    import sys
    from pathlib import Path
    from test_agi_leprechaun_route import shield_run,set_phase,stop

    source=tmp_path/'source';source.mkdir();output=tmp_path/'output';output.mkdir()
    run=shield_run(tmp_path,monkeypatch);run.root=output;set_phase(run,'score')
    run.quest_probe=None;run.distance_probe=None;run.trace_active=True;run.trace_start_index=0
    run.trace_receipt={'format':'fdisbull-agi-shield-trace-1','maximum_count':128,
                       'complete':False,'events':[],'runs':[]}
    run.journal=[{'result':{'outcome':'breakpoint'}}]
    run.route=lambda:run.handle_stop(stop(run))
    report={}
    @contextmanager
    def native_game(*args,**kwargs):
        yield None,run.d,None,None,lambda name:None,report,None
    monkeypatch.setattr(module,'native_game',native_game)
    monkeypatch.setattr(module,'QuestRun',lambda *args:run)
    monkeypatch.setattr(module,'retain_private_evidence',lambda *args:[])
    monkeypatch.setattr(sys,'argv',['quest','--source',str(source),'--backend',str(tmp_path/'backend'),'--output',str(output)])
    original=Path.write_text
    def fail_final_once(path,*args,**kwargs):
        if path.name=='shield-trace.private.json':raise OSError('authored final trace storage failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',fail_final_once)
    with pytest.raises(OSError,match='final trace storage failure'):
        module.main()
    partial=json.loads((output/'partial-prefix-trace.private.json').read_text())
    assert partial['complete'] is True and len(partial['events'])==12
    assert partial['events']==run.trace_receipt['events'] and partial['runs']==run.trace_receipt['runs']
    assert run.predicate_proof['known_effects']=={'score':11,'item_location':255}
    assert not (output/'shield-trace.private.json').exists()
    assert report['normal_gnome_giant_complete'] is False and not run.d.runs


def test_main_retains_current_pickup_when_canonical_proof_destination_fails(tmp_path,monkeypatch):
    """A qualified authored item stop must survive its canonical storage fault."""
    from contextlib import contextmanager
    import json
    from pathlib import Path
    import shutil
    import sys
    import time
    from examples.agi import inventory_probe,verify_leprechaun
    from examples.agi.spatial_trial import manifest
    from test_agi_inventory_probe import case as pickup_case,stop_for

    source=tmp_path/'source';source.mkdir();output=tmp_path/'output';output.mkdir()
    # Reuse the authored OBJECT/handler/source fixture without starting early:
    # main must exercise the baseline write and the subsequent observed effect.
    with monkeypatch.context() as setup:
        setup.setattr(inventory_probe.PickupProbe,'start',lambda self:None)
        spec=('key',40,5,0x2d6,0x2db,3,14,('item','return','score'))
        run,probe=pickup_case.__wrapped__(SimpleNamespace(param=spec),source,monkeypatch)
    run.__class__=module.QuestRun;run.root=output
    (source/'AGI').write_bytes(b'authored identity only; not an original executable')
    shutil.copytree(source,output/'game')
    monkeypatch.setattr(verify_leprechaun,'OBJECT_SHA256',sha256((source/'OBJECT').read_bytes()).hexdigest())
    run.report={'source_manifest':manifest(source)};report=run.report
    run.quest_probe=probe;run.motion_probe=None;run.distance_probe=None;run.quest_started=True;run.execution_blocked=False
    run.inputs=[];run.messages=[];run.observations={};run.actions=[]
    run.clip_observations={};run.clip_actions=[];run.samples=[];run.pictures={}
    run.preparation=[];run.guess_observations=[];run.guest_elapsed=0
    run.deadline=time.monotonic()+30;run.fast_forward=False;run.bp=None
    run.d.session_id='authored-no-native-execution'
    run.predicate_proof={'format':'fdisbull-agi-shield-pickup-1','source_logic':77,
                         'complete':True,'known_effects':{'score':11,'item_location':255}}
    run.state=lambda:{'room':40,'score':run.d.memory[run.ds+12],
                      'key_carried':run.d.memory[probe.location]==255}
    run.frame=lambda name:None
    def authored_stop(**kwargs):
        run.d.runs.append(kwargs)
        return dict(stop_for(run,probe,'item'),guest_elapsed_ms=10)
    run.d.run=authored_stop
    def route():
        probe.start()
        run.advance(10)
        pytest.fail('Canonical proof failure must abort the action')
    run.route=route
    @contextmanager
    def native_game(*args,**kwargs):yield None,run.d,None,None,run.frame,report,None
    monkeypatch.setattr(module,'native_game',native_game)
    monkeypatch.setattr(module,'QuestRun',lambda *args:run)
    monkeypatch.setattr(sys,'argv',['quest','--source',str(source),'--backend',str(tmp_path/'backend'),
                                  '--output',str(output)])
    canonical=output/'key-pickup.private.json';writes=[];original=Path.write_text
    fault=OSError('authored canonical proof destination failed after baseline')
    def fail_canonical_after_baseline(path,*args,**kwargs):
        if path==canonical:
            writes.append(path)
            if len(writes)>1:raise fault
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',fail_canonical_after_baseline)
    with pytest.raises(OSError) as raised:module.main()
    assert raised.value is fault and len(writes)>1
    baseline=json.loads(canonical.read_text())
    assert baseline['known_effects']=={'score':14,'item_location':0} and 'item_writer' not in baseline
    retained=json.loads((output/'retained-pickup-proof.private.json').read_text())
    result=json.loads((output/'result.json').read_text())
    assert retained==result['retained_pickup_proof']==probe.proof
    assert retained['source_logic']==40 and retained['source_logic_sha256']==run.resources[40].resource_sha256
    assert retained['known_effects']=={'score':14,'item_location':255}
    assert retained['item_writer']=={'cause_offset':0x7482,'resume_offset':0x7486,'di_offset':0x100f}
    assert retained['complete'] is False and retained['status']=='incomplete'
    assert result['normal_gnome_giant_complete'] is False and run.execution_blocked
    assert (output/'partial-capture.private.json').is_file()
    assert result['post_teardown_source_unchanged'] and result['post_teardown_copy_unchanged']
    with pytest.raises(RuntimeError,match='Earlier execution/observation failed'):
        module.CaveRun.advance(run,10)
    assert len(run.d.runs)==1


def checkpoint_run(tmp_path):
    run=authored_run(tmp_path);run.capture_checkpoints=True
    run.watch=None;run.trace_active=False;run._idle=lambda:True;run.guest_elapsed=123
    payload=b'authored checkpoint fixture; not original emulator state'
    artifact={'artifact':{'id':'authored-state'},'sha256':sha256(payload).hexdigest()}
    def save(name):run.events.append(('save',name));return deepcopy(artifact)
    def export(reference,path):
        run.events.append(('export',reference,path.name));path.write_bytes(payload)
    run.d=SimpleNamespace(save_state=save);run.p=SimpleNamespace(debug_export=export)
    return run,payload,artifact


def test_private_checkpoint_is_opt_in_and_hash_bound_save_only(tmp_path):
    run,payload,artifact=checkpoint_run(tmp_path);run.capture_checkpoints=False
    run.checkpoint('giant-asleep')
    assert not run.events and not list(tmp_path.iterdir())
    run.capture_checkpoints=True;run.checkpoint('giant-asleep')
    assert run.events==[('save','giant-asleep.sav'),('export',artifact['artifact'],'giant-asleep.sav')]
    assert (tmp_path/'giant-asleep.sav').read_bytes()==payload
    assert run.report['private_checkpoints']==[{'path':'giant-asleep.sav','sha256':sha256(payload).hexdigest(),
                                               'guest_ms':123,'loaded':False}]
    assert not run.execution_blocked


@pytest.mark.parametrize('fault',['idle','watch','trace','idle_query','save','export','hash'])
def test_private_checkpoint_failure_latches_and_preserves_primary_without_execution(tmp_path,fault):
    run,_,_=checkpoint_run(tmp_path);error=OSError('authored checkpoint '+fault)
    def fail(*args,**kwargs):raise error
    if fault=='idle':run._idle=lambda:False
    if fault=='watch':run.watch='owned-watch'
    if fault=='trace':run.trace_active=True
    if fault=='idle_query':run._idle=fail
    if fault=='save':run.d.save_state=fail
    if fault=='export':run.p.debug_export=fail
    if fault=='hash':run.p.debug_export=lambda reference,path:path.write_bytes(b'wrong authored state')
    with pytest.raises((RuntimeError,OSError)) as raised:run.checkpoint('giant-asleep')
    if fault in ('idle_query','save','export'):assert raised.value is error
    assert run.execution_blocked and run.report['checkpoint_failure']['name']=='giant-asleep'
    assert 'private_checkpoints' not in run.report
    if fault in ('idle','watch','trace','idle_query'):assert not run.events
    with pytest.raises(RuntimeError,match='Earlier execution/observation failed'):
        module.CaveRun.advance(run,10)


@pytest.mark.parametrize('after',['gnome-ready','key-on-ground','key-taken','tree-ready',
                                  'tree-unlocked','giant-awake','giant-asleep','chest-taken'])
def test_quest_action_checkpoints_only_selected_completed_boundaries(tmp_path,after):
    run=authored_run(tmp_path);run.current['player_control']=1;run.clip_observations={}
    run.state=lambda:deepcopy(run.current);run._idle=lambda:True
    def observe(name):
        run.events.append(('capture',name));run.clip_observations[name]={'state':deepcopy(run.current)}
    run.observe_clip=observe
    run.action=lambda *args:run.events.append(('action',args))
    run.checkpoint=lambda name:run.events.append(('checkpoint',name))
    module.QuestRun.quest_action(run,'authored-action','before',after,(0,0))
    checkpoints=[event for event in run.events if event[0]=='checkpoint']
    assert checkpoints==([('checkpoint',after)] if after in ('tree-unlocked','giant-awake','giant-asleep') else [])
    assert run.events.index(('capture',after))<next(i for i,e in enumerate(run.events) if e[0]=='action')
    if checkpoints:assert run.events[-1]==('checkpoint',after)


def test_prefix_checkpoint_follows_qualified_quest_start_capture(tmp_path,monkeypatch):
    run=authored_run(tmp_path);run.quest_started=False;run.current['room']=36
    monkeypatch.setattr(module.CaveRun,'route',lambda self:{'scope':'authored prefix only'})
    run.observe_clip=lambda name:run.events.append(('capture',name))
    run.checkpoint=lambda name:run.events.append(('checkpoint',name))
    run.capture=lambda:{'scope':'authored quest only'}
    assert run.prepare_prefix()=={'scope':'authored quest only'}
    assert run.quest_started and run.events==[('capture','quest-start'),('checkpoint','quest-start')]


def test_distance_failure_does_not_start_pickup_or_fall_back(tmp_path,monkeypatch):
    run=authored_run(tmp_path);calls=[];error=OSError('authored distance observation lost')
    def fail(out):calls.append(('distance',out));raise error
    run.distance_probe=SimpleNamespace(active=True,handle_stop=fail)
    run.quest_probe=SimpleNamespace(active=False,start=lambda:calls.append(('pickup',)))
    monkeypatch.setattr(module.CaveRun,'handle_stop',lambda self,out:calls.append(('fallback',)))
    with pytest.raises(OSError) as raised:run.handle_stop({'stage':'write'})
    assert raised.value is error and calls==[('distance',{'stage':'write'})]


def test_main_retains_distance_result_when_canonical_destination_fails(tmp_path,monkeypatch):
    """Use the real authored distance ABI fixture and real advance/main cleanup."""
    from contextlib import contextmanager
    import json
    from pathlib import Path
    import shutil
    import sys
    import time
    from examples.agi import distance_probe
    from examples.agi.spatial_trial import manifest
    from test_agi_distance_probe import case as distance_case,stop_for

    source=tmp_path/'source';source.mkdir();output=tmp_path/'output';output.mkdir()
    with monkeypatch.context() as setup:
        setup.setattr(distance_probe.DistanceProbe,'start',lambda self:None)
        run,probe=distance_case.__wrapped__(source,monkeypatch)
    run.__class__=module.QuestRun;run.root=output
    shutil.copytree(source,output/'game')
    report=run.report;report['source_manifest']=manifest(source)
    run.distance_probe=probe;run.quest_probe=SimpleNamespace(name='chest',active=False,proof=None)
    run.quest_started=True;run.journal=[];run.inputs=[];run.messages=[]
    run.observations={};run.actions=[];run.clip_observations={};run.clip_actions=[]
    run.samples=[];run.pictures={};run.preparation=[];run.guess_observations=[]
    run.guest_elapsed=0;run.deadline=time.monotonic()+30;run.fast_forward=False
    run.trace_receipt=None;run.bp=None;run.frame=lambda name:None
    run.predicate_proof=None;run.state=lambda:{'room':58,'score':26,'distance':run.d.memory[run.ds+79]}
    def authored_stop(**kwargs):
        run.d.runs.append(kwargs)
        return dict(stop_for(run,probe,'write'),guest_elapsed_ms=10)
    run.d.run=authored_stop
    def route():
        probe.start();run.advance(10);pytest.fail('Canonical distance fault must stop the action')
    run.route=route
    @contextmanager
    def native_game(*args,**kwargs):yield None,run.d,None,None,run.frame,report,None
    monkeypatch.setattr(module,'native_game',native_game);monkeypatch.setattr(module,'QuestRun',lambda *args:run)
    monkeypatch.setattr(sys,'argv',['quest','--source',str(source),'--backend',str(tmp_path/'backend'),
                                  '--output',str(output)])
    canonical=output/'giant-distance.private.json';original=Path.write_text;writes=[]
    fault=OSError('authored canonical distance destination failed after baseline')
    def fail_canonical(path,*args,**kwargs):
        if path==canonical:
            writes.append(path)
            if len(writes)>1:raise fault
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',fail_canonical)
    with pytest.raises(OSError) as raised:module.main()
    assert raised.value is fault
    assert 'known_result' not in json.loads(canonical.read_text())
    retained=json.loads((output/'retained-distance-proof.private.json').read_text())
    result=json.loads((output/'result.json').read_text())
    assert retained==result['retained_distance_proof']==probe.proof
    assert retained['source_logic']==58 and retained['source_offset']==0x234 and retained['known_result']==24
    assert retained['distance_writer']['cause_offset']==0x48a2 and retained['distance_writer']['resume_offset']==0x48a6
    assert retained['native_execution'] is True and retained['complete'] is False and retained['status']=='incomplete'
    assert run.execution_blocked and len(run.d.runs)==1 and run.quest_probe.proof is None
    assert result['normal_gnome_giant_complete'] is False
    assert result['post_teardown_source_unchanged'] and result['post_teardown_copy_unchanged']
    with pytest.raises(RuntimeError,match='Earlier execution/observation failed'):
        module.CaveRun.advance(run,10)
    assert len(run.d.runs)==1
