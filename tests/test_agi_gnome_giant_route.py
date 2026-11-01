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
            assert owner is run;created.append(kwargs);self.active=True;self.proof={'complete':False}
        def start(self):run.events.append(('probe-start',))
    monkeypatch.setattr(module,'PickupProbe',Probe)
    def command(text):
        assert text=='get '+name and run.quest_probe.active
        run.events.append(('command',text));run.inputs.append({'key':text})
        (tmp_path/(name+'-pickup.private.json')).write_bytes(b'authored proof')
        run.quest_probe.proof={'complete':True,'status':'verified','native_execution':True}
        run.quest_probe.active=False;run.current[name+'_carried']=True;run.current['score']=before+delta
    run.command=command
    run.pickup(name)
    assert created==[{'name':name,'logic':logic,'item':item,'item_offset':off,'score_offset':score_off,
                      'score_delta':delta,'before_score':before,'order':order}]
    assert run.events.index(('probe-start',))<run.events.index(('command','get '+name))
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
        a=run.current['quest_actors']['1']
        run.current['quest_variables']['70']=abs(x+3-a['x']-a['width']//2)+abs(y-a['y'])
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


def test_sleeping_giant_uses_one_proposal_and_rechecks_native_distance(tmp_path):
    run=sleeping_run(tmp_path);run.approach_sleeping_giant()
    assert len(run.moves)==1 and len(run.journal)==1 and not run.inputs
    assert run.guest_elapsed==200 and run.journal[0]['target']==run.moves[0]
    s=run.current;a=s['quest_actors']['1'];e=s['ego']
    assert s['quest_variables']['70']==abs(e['x']+3-a['x']-a['width']//2)+abs(e['y']-a['y'])<=30


@pytest.mark.parametrize('fault',['changed_actor','changed_width','changed_height','motion','direction','view','unscored','chest','wrong_native_distance'])
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
        if fault=='wrong_native_distance':s['quest_variables']['70']+=1
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


def test_near_giant_must_not_shortcut_on_wrong_native_distance(tmp_path):
    run=sleeping_run(tmp_path);run.current['ego']={'x':56,'y':70};run.current['quest_variables']['70']=22
    def plan(room,start,target,*,allow_priority_one):
        run.plans.append(target);return {'status':'blocked_endpoint','path':[]},None
    run.path_model=plan
    with pytest.raises(RuntimeError,match='No conservative'):run.approach_sleeping_giant()
    assert run.plans and not run.moves and not run.inputs


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
    run.quest_probe=None;run.trace_active=True;run.trace_start_index=0
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
    run.quest_probe=probe;run.motion_probe=None;run.quest_started=True;run.execution_blocked=False
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
