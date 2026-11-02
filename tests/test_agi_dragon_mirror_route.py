"""Authored unit checks only; no original runtime or native qualification."""
from hashlib import sha256
from types import SimpleNamespace
import json

import pytest
from examples.agi import dragon_probes as module
from examples.agi import inventory_probe
from examples.agi.verify_mushroom import MushroomRun
from test_agi_mushroom_route import AuthoredSession, memory_read, word


def probe_fixture(tmp_path,monkeypatch,kind):
    monkeypatch.setattr(module,'read',memory_read);monkeypatch.setattr(inventory_probe,'read',memory_read)
    o=object.__new__(MushroomRun);o.d=AuthoredSession();o.d.session_id='authored-session';o.root=o.source=tmp_path
    o.cs=0x1000;o.ds=0x20000;o.inventory={'base':0x1000,'end':0x1051};o.report={}
    o.watch=None;o.watch_kind=None;o.trace_active=False;o.trace_receipt=None;o.journal=[];o.execution_blocked=False
    item=19 if kind=='mirror' else 26;name='authored-mirror' if kind=='mirror' else 'authored-water'
    data=bytearray(0x150);data[:2]=(81).to_bytes(2,'little');name_off=0x90
    data[3+3*item:5+3*item]=name_off.to_bytes(2,'little');data[3+name_off:3+name_off+len(name)+1]=name.encode()+b'\0'
    raw=bytes(x^b'Avis Durgan'[i%11] for i,x in enumerate(data));(tmp_path/'OBJECT').write_bytes(raw)
    monkeypatch.setattr(inventory_probe,'OBJECT_SHA256',sha256(raw).hexdigest())
    word(o.d,o.ds+0x969,0x1000);word(o.d,o.ds+0x96b,0x1051)
    word(o.d,o.ds+0x1000+3*item,name_off)
    o.d.memory[o.ds+0x1000+name_off:o.ds+0x1000+name_off+len(name)+1]=name.encode()+b'\0'
    code=bytearray(0x490)
    if kind=='mirror':code[0x37f:0x388]=bytes((92,19,101,24,1,74,5,3,8));score=20
    else:code[0x45e:0x468]=bytes((101,34,94,26,7,3,2,5,3,7));score=15
    payload=len(code).to_bytes(2,'little')+code
    o.resources={51:SimpleNamespace(code=bytes(code),payload=payload,resource_sha256=sha256(payload).hexdigest())}
    word(o.d,o.ds+0x979,0x3000);o.d.memory[o.ds+0x3002]=51;word(o.d,o.ds+0x3004,0x4000)
    o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code;o.d.memory[o.ds+12]=score
    o.d.memory[o.cs*16+0x7471:o.cs*16+0x7471+len(inventory_probe.GET_HANDLER)]=inventory_probe.GET_HANDLER
    o.d.memory[o.cs*16+0x72d4:o.cs*16+0x72d4+len(module.SCORE_WRITER)]=module.SCORE_WRITER
    word(o.d,o.ds+0x78d,0x7471)
    if kind=='water':
        drop=b'D'*28;sub=b'S'*13
        o.d.memory[o.cs*16+0x74a9:o.cs*16+0x74a9+28]=drop;o.d.memory[o.cs*16+0x72f4:o.cs*16+0x72f4+13]=sub
        monkeypatch.setattr(module,'DROP_SHA',sha256(drop).hexdigest());monkeypatch.setattr(module,'SUB_SHA',sha256(sub).hexdigest())
        word(o.d,o.ds+0x61d+94*4,0x74a9);o.d.memory[o.ds+0x1000+3*item+2]=255
    probe=module.MirrorProbe(o) if kind=='mirror' else module.DragonWaterProbe(o)
    probe.start();return o,probe


def stop(o,p,stage):
    water=p.name=='dragon-water';item=p.proof['known_effects']['item_location'];score=p.proof['known_effects']['score']
    if stage=='item':item=255
    if stage=='drop':item=0
    if stage=='score':score=28
    if stage=='subtract':score=13
    if stage=='add':score=20
    o.d.memory[p.location]=item;o.d.memory[o.ds+12]=score
    cursor=0x4000+(0x462 if water else 0x381)
    offset={'item':0x7482,'drop':0x74ba,'score':0x72da,'subtract':0x72fa,'add':0x72da,'return':0x2fa}[stage]
    ip={'item':0x7486,'drop':0x74be,'score':0x72de,'subtract':0x72fe,'add':0x72de,'return':0x2fa}[stage]
    delta={'item':8,'drop':7,'score':8,'subtract':2,'add':7,'return':0}[stage]
    src={'score':0x388,'subtract':0x465,'add':0x468}.get(stage,0)
    o.d.register_state={'segments':{'cs':'0x1000','ds':'0x2000','ss':'0x4000'},'instruction_pointer':hex(ip),
        'general':{'eax':hex(cursor if stage=='return' else delta),'ebx':'0x3','esi':hex(0x4000+src),
                   'edi':hex(0x1000+3*p.item),'ebp':'0x100','esp':hex(0x108 if stage=='return' else 0x100)}}
    word(o.d,0x40106,0x2fa);word(o.d,0x40108,cursor)
    reason={'breakpoint_id':o.watch}
    if stage!='return':reason['data_access']={'access':'w','instruction':{'space':'segmented','segment':'0x1000','offset':hex(offset)}}
    if stage=='return':o.journal.append({'result':{'outcome':'authored'}})
    return {'outcome':'breakpoint','session':{'stop_reason':reason}}


def test_mirror_trace_stops_before_modal_then_real_score(tmp_path,monkeypatch):
    o,p=probe_fixture(tmp_path,monkeypatch,'mirror')
    p.handle_stop(stop(o,p,'item'));assert o.trace_active
    p.handle_stop(stop(o,p,'return'))
    assert not o.trace_active and p.pre_print_trace['event_count']==12 and p.proof['known_effects']=={'score':20,'item_location':255}
    p.handle_stop(stop(o,p,'score'))
    assert p.proof['status']=='verified' and p.proof['after']=={'score':28,'item_location':255}
    assert p.proof['trace']==p.proof['pre_print_trace'] and not o.d.runs


def test_water_drop_then_score_writes_are_bound_in_order(tmp_path,monkeypatch):
    o,p=probe_fixture(tmp_path,monkeypatch,'water')
    for stage in ('drop','return','subtract','add'):p.handle_stop(stop(o,p,stage))
    assert p.proof['status']=='verified' and p.proof['after']=={'score':20,'item_location':0}
    assert p.proof['order']==['drop','return','subtract','add'] and p.proof['trace']['event_count']==12
    assert not o.d.runs and not o.trace_active


@pytest.mark.parametrize('stage,fault',[('drop','foreign'),('drop','handler'),('return','cursor'),('subtract','writer'),('add','operand')])
def test_water_fault_latches_and_retains_earlier_effects(tmp_path,monkeypatch,stage,fault):
    o,p=probe_fixture(tmp_path,monkeypatch,'water')
    for prior in p.order[:p.order.index(stage)]:p.handle_stop(stop(o,p,prior))
    out=stop(o,p,stage);r=o.d.register_state
    if fault=='foreign':out['session']['stop_reason']['breakpoint_id']='foreign'
    if fault=='handler':o.d.memory[o.ds+0x4000+0x460]=0
    if fault=='cursor':r['general']['eax']='0x4461'
    if fault=='writer':out['session']['stop_reason']['data_access']['instruction']['offset']='0x72da'
    if fault=='operand':r['general']['eax']='0x6'
    with pytest.raises(RuntimeError):p.handle_stop(out)
    assert p.failed and o.execution_blocked and not p.proof['complete'] and not o.d.runs
    if stage!='drop':assert p.proof['known_effects']['item_location']==0
    if stage=='add':assert p.proof['known_effects']['score']==13


def test_water_first_raw_read_survives_second_read_failure(tmp_path,monkeypatch):
    o,p=probe_fixture(tmp_path,monkeypatch,'water');out=stop(o,p,'drop');original=module.read
    def fail_item(d,address,length):
        if address==p.location:raise OSError('authored item read loss')
        return original(d,address,length)
    monkeypatch.setattr(module,'read',fail_item)
    with pytest.raises(OSError,match='item read loss'):p.handle_stop(out)
    assert p.proof['last_observation']=={'stage':'drop','score':15}
    assert p.proof['known_effects']=={'score':15,'item_location':255} and o.execution_blocked and not o.d.runs


def test_rock_approach_stays_above_actor_and_rechecks_dagger_guard(monkeypatch):
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    s={'room':1,'score':0,'ego':{'x':110,'y':100},'quest_flags':{'67':False},'dagger_carried':False}
    calls=[];run=SimpleNamespace(inputs=[],messages=[],ds=0,d=object())
    def exit_(key,room):s['room']=room;calls.append(('exit',key,room))
    def path(x,y):s['ego'].update(x=x,y=y);calls.append(('path',x,y))
    def precise(*,y):s['ego']['y']=y;calls.append(('precise-y',y))
    def command(text):
        calls.append(('command',text))
        if text=='push rock':s['score']=2
        elif text=='get dagger':s.update(score=7,dagger_carried=True);s['quest_flags']['67']=True
    run.surface_exit=exit_;run.static_path=path;run.precise=precise;run.command=command
    run.state=run.safe_state=lambda:deepcopy(s)
    run.wait_for=lambda pred,label,*args:assert_predicate(pred(s))
    run.observe_clip=lambda label:label
    run.action=lambda *args:calls.append(('action',args[0]))
    monkeypatch.setattr(route,'read',lambda *args:bytes((0x02,))) # f62 is set by original movement callback
    assert route.DragonRun.obtain_dagger(run,'fresh')=='dagger-carried'
    assert [x for x in calls if x[0] in ('path','precise-y')]==[
        ('path',150,110),('path',120,110),('precise-y',114)]
    assert [x for x in calls if x[0]=='command']==[('command','push rock'),('command','get dagger')]
    # Final origin is inside both source rectangles, above the hazardous lower
    # push rectangle and above the original actor's y=133 baseline.
    x,y=120,114
    assert 115<=x<=133 and 114<=y<=133 and 112<=x<=134 and 108<=y<=133 and y<133


def assert_predicate(value):
    assert value


def test_room5_north_exit_uses_source_horizon_and_original_transition():
    from examples.agi import verify_dragon_mirror as route
    calls=[];state={'bucket_carried':False,'quest_flags':{'81':False,'176':False},'score':7}
    run=SimpleNamespace(inputs=[],messages=[])
    run.surface_exit=lambda key,room:calls.append(('exit',key,room))
    run.static_path=lambda x,y:calls.append(('path',x,y))
    run.move=lambda key,room:calls.append(('move',key,room))
    def command(text):
        calls.append(('command',text));state.update(bucket_carried=True,score=9);state['quest_flags'].update({'81':True,'176':True})
    run.command=command;run.wait_for=lambda pred,label:assert_predicate(pred(state))
    run.checkpoint=lambda name:None
    run.observe_clip=lambda label:label;run.action=lambda *args:calls.append(('action',args[0]))
    assert route.DragonRun.detach_bucket(run,'dagger-carried')=='bucket-carried'
    assert calls[:4]==[('exit','left',4),('exit','left',5),('path',40,56),('move','up',12)]
    assert 56==55+1  # first valid row below L5's source horizon


def test_rope_mount_requires_settled_top_before_ordinary_down():
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    state={'room':12,'score':9,'ego':{'x':39,'y':132,'direction':0,'drawn':True},
           'ego_view':143,'quest_flags':{'179':True,'180':True},'player_control':1,
           'window':0,'initializing':False}
    calls=[];run=SimpleNamespace(inputs=[],messages=[],report={},in_well=False)
    run.static_path=lambda x,y:calls.append(('path',x,y))
    run.command=lambda text:calls.append(('command',text))
    def wait_for(predicate,label,*args):
        calls.append(('wait',label))
        if label=='top rope readiness':
            bad=deepcopy(state);bad['ego']['y']=131;assert not predicate(bad)
            bad=deepcopy(state);bad['player_control']=0;assert not predicate(bad)
        assert predicate(state)
    run.wait_for=wait_for;run.state=lambda:deepcopy(state)
    def press(key,*args,**kwargs):
        calls.append(('press',key));state.update(room=49,score=10,ego_view=74)
    run.press=press;run.ready=lambda:None;run.observe_clip=lambda label:label
    run.action=lambda *args:calls.append(('action',args[0]))
    assert route.DragonRun.descend_well(run,'bucket-carried')=='well-ready'
    assert calls.index(('wait','top rope readiness'))<calls.index(('press','down'))<calls.index(('wait','original well entry'))
    assert run.report['top_rope_state']['ego']['y']==132 and run.in_well is True


def test_dragon_approach_guard_stops_before_known_contact_and_near_follower():
    from copy import deepcopy
    from examples.agi.verify_dragon_mirror import dragon_approach_safe
    s={'room':51,'quest_variables':{'75':0},'quest_flags':{'20':False},
       'ego':{'x':133,'y':136},'ego_width':6,
       'dragon_actor':{'x':40,'y':120,'width':37,'drawn':True}}
    assert dragon_approach_safe(s)
    close=deepcopy(s);close['dragon_actor']['x']=100
    assert not dragon_approach_safe(close)
    signaled=deepcopy(s);signaled['quest_flags']['20']=True
    assert not dragon_approach_safe(signaled)
    retreated=deepcopy(signaled);retreated['quest_variables']['75']=2
    assert dragon_approach_safe(retreated)


@pytest.mark.parametrize('observed',[True,False])
@pytest.mark.parametrize('start_x',[131,133])
def test_pretyped_water_follows_safe_east_legs_once_without_replay(tmp_path,monkeypatch,observed,start_x):
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    state={'room':51,'score':15,'ego':{'x':start_x,'y':136,'direction':0,'drawn':True},'water_carried':True,
           'player_control':1,'ignore_blocks':True,
           'quest_flags':{'20':False,'21':False,'22':False,'23':False,'88':True},
           'quest_variables':{'75':0},'dragon_actor':{'drawn':True}}
    calls=[];run=SimpleNamespace(inputs=[],messages=[],report={},root=tmp_path,guest_elapsed=0,clip_actions=[],clip_observations={})
    run.safe_state=lambda:deepcopy(state)
    run.type_text=lambda text:calls.append(('type',text))
    def precise(**kwargs):state['ego'].update(kwargs);calls.append(('precise',tuple(kwargs.items())))
    run.precise=precise
    def observe(name):
        run.clip_observations[name]={'state':deepcopy(state),'guest_ms':run.guest_elapsed};return name
    run.observe_clip=observe
    class Probe:
        def __init__(self,owner):self.owner=owner;self.active=False;self.failed=False;self.proof={}
        def start(self):self.active=True;calls.append(('arm',))
        def _fail(self,error,phase):self.failed=True
    monkeypatch.setattr(route,'DragonWaterProbe',Probe)
    def press(key,*args,**kwargs):
        calls.append(('press',key))
        if observed:
            run.water_probe.active=False;run.water_probe.proof={'complete':True,'status':'verified'}
            state.update(score=20,water_carried=False);state['quest_variables']['75']=2;state['dragon_actor']['drawn']=False
            run.messages.append({'logic':51,'source_offset':0x45e,'status':'completed'})
    run.press=press;run.wait_for=lambda pred,label,*args:assert_predicate(pred(state))
    run.advance=lambda ms:setattr(run,'guest_elapsed',run.guest_elapsed+1000)
    def action(*args):run.clip_actions.append({'id':args[0]})
    run.action=action;(tmp_path/'dragon-water-pickup.private.json').write_bytes(b'authored proof')
    if observed:assert route.DragonRun.douse_dragon(run,'dragon-before')=='dragon-retreated'
    else:
        with pytest.raises(RuntimeError,match='without replay'):route.DragonRun.douse_dragon(run,'dragon-before')
        assert run.water_probe.failed
    assert calls==[('type','throw water'),('precise',(('x',135),)),('precise',(('y',131),)),
                   ('precise',(('x',146),)),('arm',),('press','enter')]
    assert run.water_before['state']['ego']['x']==146 and run.water_before['state']['ego']['y']==131


def test_optional_checkpoint_is_save_only_and_failure_latches(tmp_path):
    from examples.agi.verify_dragon_mirror import DragonRun
    content=b'authored private checkpoint';calls=[];run=SimpleNamespace(capture_checkpoints=True,
        watch=None,trace_active=False,root=tmp_path,report={},guest_elapsed=12,execution_blocked=False)
    run._idle=lambda:True
    run.d=SimpleNamespace(save_state=lambda name:(calls.append(('save',name)) or
                          {'artifact':'authored','sha256':sha256(content).hexdigest()}))
    run.p=SimpleNamespace(debug_export=lambda artifact,path:(calls.append(('export',artifact)) or path.write_bytes(content)))
    DragonRun.checkpoint(run,'bucket-carried')
    assert calls==[('save','bucket-carried.sav'),('export','authored')]
    assert run.report['private_checkpoints']==[{'path':'bucket-carried.sav','sha256':sha256(content).hexdigest(),
                                                'guest_ms':12,'loaded':False}]
    run._idle=lambda:False
    with pytest.raises(RuntimeError,match='settled input'):DragonRun.checkpoint(run,'dragon-before')
    assert run.execution_blocked and run.report['checkpoint_failure']['name']=='dragon-before'
    assert len(calls)==2


def test_exit_routes_below_source_boulder_before_original_room_transition():
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    state={'room':51,'score':28,'ego':{'x':45,'y':115,'direction':0},'quest_variables':{'75':2},
           'dragon_actor':{'drawn':False},'mirror_carried':True,'water_carried':False,'ignore_blocks':True}
    calls=[];run=SimpleNamespace(inputs=[],messages=[])
    run.safe_state=lambda:deepcopy(state)
    def precise(**kwargs):state['ego'].update(kwargs);calls.append(('precise',tuple(kwargs.items())))
    def move(key,*,room=None,axis=None,target=None):
        if axis:
            calls.append(('move-axis',key,axis,target));state['ego'][axis]=target+1
        else:
            calls.append(('move',key,room));state['room']=room
    def exit_(key,room):calls.append(('exit',key,room));state['room']=room
    run.precise=precise;run.move=move;run.surface_exit=exit_
    run.observe_clip=lambda name:name;run.action=lambda *args:calls.append(('action',args[0]))
    assert route.DragonRun.leave_cave(run,'mirror-taken')=='surface-return'
    assert calls==[('move-axis','left','x',38),('move-axis','down','y',134),('move','left',50),
                   ('exit','left',22),('action','leave-cave')]
    assert 35>3+27 and 136>127  # stay outside source VIEW35 rock until below its baseline


@pytest.mark.parametrize('settled_y,allowed',[(133,True),(137,True),(139,True),(140,False)])
def test_exit_corridor_checks_settled_original_position_before_left(settled_y,allowed):
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    state={'room':51,'score':28,'ego':{'x':45,'y':115,'direction':0},'quest_variables':{'75':2},
           'dragon_actor':{'drawn':False},'mirror_carried':True,'water_carried':False,'ignore_blocks':True}
    calls=[];run=SimpleNamespace(inputs=[],messages=[]);run.safe_state=lambda:deepcopy(state)
    run.precise=lambda **kwargs:state['ego'].update(kwargs)
    def move(key,*,room=None,axis=None,target=None):
        calls.append((key,room,axis,target))
        if axis:state['ego'][axis]=38 if axis=='x' else settled_y
        else:state['room']=room
    run.move=move
    def exit_(key,room):calls.append((key,room,None,None));state['room']=room
    run.surface_exit=exit_;run.observe_clip=lambda name:name;run.action=lambda *args:None
    if allowed:assert route.DragonRun.leave_cave(run,'mirror-taken')=='surface-return'
    else:
        with pytest.raises(RuntimeError,match='qualified corridor'):route.DragonRun.leave_cave(run,'mirror-taken')
    assert any(x[0]=='left' and x[1]==50 for x in calls) is allowed


@pytest.mark.parametrize('settled_x,allowed',[(34,False),(35,True),(40,True),(41,False)])
def test_exit_checks_right_of_boulder_before_down(settled_x,allowed):
    from copy import deepcopy
    from examples.agi import verify_dragon_mirror as route
    state={'room':51,'score':28,'ego':{'x':45,'y':115,'direction':0},'quest_variables':{'75':2},
           'dragon_actor':{'drawn':False},'mirror_carried':True,'water_carried':False,'ignore_blocks':True}
    calls=[];run=SimpleNamespace(inputs=[],messages=[]);run.safe_state=lambda:deepcopy(state)
    def move(key,*,room=None,axis=None,target=None):
        calls.append((key,room,axis,target))
        if axis=='x':state['ego']['x']=settled_x
        elif axis=='y':state['ego']['y']=136
        else:state['room']=room
    run.move=move
    def exit_(key,room):state['room']=room
    run.surface_exit=exit_;run.observe_clip=lambda name:name;run.action=lambda *args:None
    if allowed:assert route.DragonRun.leave_cave(run,'mirror-taken')=='surface-return'
    else:
        with pytest.raises(RuntimeError,match='right of the actor'):route.DragonRun.leave_cave(run,'mirror-taken')
    assert any(x[0]=='down' for x in calls) is allowed
