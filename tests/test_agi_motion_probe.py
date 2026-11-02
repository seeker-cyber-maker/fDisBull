"""Authored watch and keyboard fixtures; no native guest or original files."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from examples.agi import motion_probe as module
from examples.agi.verify_leprechaun import CaveRun
from test_agi_mushroom_route import AuthoredSession, memory_read, word


def setflag(o,n,value=True):
    a=o.ds+0x109+n//8;mask=0x80>>(n%8)
    o.d.memory[a]=(o.d.memory[a]|mask) if value else (o.d.memory[a]&~mask)


def actor_word(o,offset,value):word(o.d,o.ds+0x1000+offset,value)


@pytest.fixture(params=[('x',12,'right'),('y',98,'up')])
def case(request,monkeypatch):
    monkeypatch.setattr(module,'read',memory_read)
    o=object.__new__(CaveRun);o.d=AuthoredSession();o.cs,o.ds=0x1000,0x20000
    o.inventory={'base':0x4000};o.report={};o.inputs=[];o.journal=[]
    o.watch=None;o.watch_kind=None;o.trace_active=False;o.quest_probe=None;o.execution_blocked=False
    o.keyboard_idle=True;o._idle=lambda:o.keyboard_idle;o.d.keys=[]
    def press(key,**kw):o.d.keys.append((key,kw));return {'accepted':True}
    o.d.keyboard_press=press
    o.d.memory[o.ds+9]=67;o.d.memory[o.ds+12]=19;word(o.d,o.ds+0x139,1)
    word(o.d,o.ds+0x963,0x1000);word(o.d,o.ds+0x969,0x4000);o.d.memory[o.ds+0x4000+65]=255
    actor_word(o,3,10);actor_word(o,5,100);actor_word(o,26,6)
    o.d.memory[o.ds+0x1000+30]=1;o.d.memory[o.ds+0x1000+37]=1;setflag(o,102)
    o.d.register_state={'segments':{'cs':'0x1000','ds':'0x2000'}}
    axis,target,key=request.param
    p=module.MotionProbe(o,axis=axis,target=target,key=key)
    return o,p


def watchstop(o):
    return {'outcome':'breakpoint','session':{'stop_reason':{'breakpoint_id':o.watch,
        'data_access':{'access':'w','instruction':{'space':'segmented','segment':'0x1000','offset':'0x4567'}}}}}


def coord(o,p,value):actor_word(o,3 if p.axis=='x' else 5,value)


def set_moving(o,p):
    direction={'up':1,'right':3,'down':5,'left':7}[p.key]
    o.d.memory[o.ds+0x1000+33]=direction;o.d.memory[o.ds+15]=direction


def settle(o):o.d.memory[o.ds+0x1000+33]=0;o.d.memory[o.ds+15]=0


def test_goal_write_queues_one_stop_then_requires_idle_and_neutral(case):
    o,p=case;r=p.start();assert len(o.d.keys)==1 and r['watch']==o.watch
    middle=11 if p.axis=='x' else 99;coord(o,p,middle);set_moving(o,p);p.handle_stop(watchstop(o))
    assert not p.stopping and len(o.d.keys)==1 and len(r['writes'])==1
    coord(o,p,p.target);p.handle_stop(watchstop(o))
    assert p.stopping and o.watch is None and len(o.d.keys)==2 and o.d.keys[0]==o.d.keys[1]
    assert all(k[1]=={'hold_ms':1,'gap_ms':1} for k in o.d.keys)
    assert r['initial_input']['complete'] is True and r['stop_input']['complete'] is False
    assert p.poll() is False
    settle(o);o.keyboard_idle=False;assert p.poll() is False
    o.keyboard_idle=True;assert p.poll() is True
    assert not p.active and r['complete'] is True and r['status']=='verified' and r['final'][p.axis]==p.target
    assert r['stop_input']['complete'] and len(o.inputs)==2 and len(o.journal)==2 and not o.d.runs


@pytest.mark.parametrize('fault',['room','score','shield','shield_flag','water','trigger','dead','initializing','control','window','width','view','step','direction','control_dir','keyboard','busy','trace'])
def test_unsafe_start_never_arms_or_sends_key(case,fault):
    o,p=case
    if fault=='room':o.d.memory[o.ds+9]=70
    if fault=='score':o.d.memory[o.ds+12]=18
    if fault=='shield':o.d.memory[o.ds+0x4000+65]=0
    if fault=='shield_flag':setflag(o,102,False)
    if fault=='water':setflag(o,0)
    if fault=='trigger':setflag(o,3)
    if fault=='dead':setflag(o,63)
    if fault=='initializing':setflag(o,5)
    if fault=='control':word(o.d,o.ds+0x139,0)
    if fault=='window':word(o.d,o.ds+0xd15,1)
    if fault=='width':actor_word(o,26,5)
    if fault=='view':o.d.memory[o.ds+0x1000+7]=1
    if fault=='step':o.d.memory[o.ds+0x1000+30]=2
    if fault=='direction':o.d.memory[o.ds+0x1000+33]=3
    if fault=='control_dir':o.d.memory[o.ds+15]=3
    if fault=='keyboard':o.keyboard_idle=False
    if fault=='busy':o.quest_probe=SimpleNamespace(active=True)
    if fault=='trace':o.trace_active=True
    with pytest.raises(RuntimeError):p.start()
    assert not o.d.keys and not o.d.calls and not p.active and not o.d.runs


@pytest.mark.parametrize('fault',['foreign','outcome','read','writer_cs','current_cs','current_ds','table','room','trigger','overshoot','other_axis','pending'])
def test_unqualified_write_or_unsettled_first_key_blocks_without_extra_input(case,fault):
    o,p=case;p.start();coord(o,p,p.target);set_moving(o,p);out=watchstop(o)
    if fault=='foreign':out['session']['stop_reason']['breakpoint_id']='not-owned'
    if fault=='outcome':out['outcome']='guest_time'
    if fault=='read':out['session']['stop_reason']['data_access']['access']='r'
    if fault=='writer_cs':out['session']['stop_reason']['data_access']['instruction']['segment']='0x1001'
    if fault=='current_cs':o.d.register_state['segments']['cs']='0x1001'
    if fault=='current_ds':o.d.register_state['segments']['ds']='0x2001'
    if fault=='table':word(o.d,o.ds+0x963,0x1100)
    if fault=='room':o.d.memory[o.ds+9]=68
    if fault=='trigger':setflag(o,3)
    if fault=='overshoot':coord(o,p,p.target+p.sign)
    if fault=='other_axis':actor_word(o,5 if p.axis=='x' else 3,40)
    if fault=='pending':o.keyboard_idle=False
    with pytest.raises(RuntimeError):p.handle_stop(out)
    assert p.failed and o.execution_blocked and len(o.d.keys)==1 and not p.record['complete'] and not o.d.runs


def test_unknown_watch_setup_latches_and_prevents_owner_advance(case):
    o,p=case;old=o.d.call
    def lost(method,params=None):
        if method=='breakpoints.create':raise OSError('unknown create result')
        return old(method,params)
    o.d.call=lost
    with pytest.raises(OSError,match='unknown create'):p.start()
    assert p.failed and o.execution_blocked and not o.d.keys
    with pytest.raises(RuntimeError,match='Earlier execution/observation failed'):CaveRun.advance(o,10)
    assert not o.d.runs


def test_unknown_stop_key_delivery_retains_both_attempts_and_latches(case):
    o,p=case;p.start();coord(o,p,p.target);set_moving(o,p)
    def lost(key,**kw):o.d.keys.append((key,kw));raise OSError('unknown stop key')
    o.d.keyboard_press=lost
    with pytest.raises(OSError,match='unknown stop'):p.handle_stop(watchstop(o))
    assert p.failed and o.execution_blocked and len(o.d.keys)==2
    assert p.record['initial_input']['complete'] is True and p.record['stop_input']['delivered'] is None
    assert len(o.inputs)==2 and not o.inputs[-1]['complete'] and not o.d.runs


@pytest.mark.parametrize('fault',['overshoot','trigger','dead','room','score','shield','control'])
def test_final_poll_rejects_tentative_target_or_safety_loss(case,fault):
    o,p=case;p.start();coord(o,p,p.target);set_moving(o,p);p.handle_stop(watchstop(o));settle(o)
    if fault=='overshoot':coord(o,p,p.target+p.sign)
    if fault=='trigger':setflag(o,3)
    if fault=='dead':setflag(o,63)
    if fault=='room':o.d.memory[o.ds+9]=68
    if fault=='score':o.d.memory[o.ds+12]=18
    if fault=='shield':o.d.memory[o.ds+0x4000+65]=0
    if fault=='control':word(o.d,o.ds+0x139,0)
    with pytest.raises(RuntimeError):p.poll()
    assert p.failed and o.execution_blocked and not p.record['complete'] and len(o.d.keys)==2


def test_coordinate_write_budget_fails_closed(case,monkeypatch):
    o,p=case;monkeypatch.setattr(p,'MAX_WRITES',2);p.start();coord(o,p,11 if p.axis=='x' else 99)
    p.handle_stop(watchstop(o));p.handle_stop(watchstop(o))
    with pytest.raises(RuntimeError,match='budget'):p.handle_stop(watchstop(o))
    assert len(p.record['writes'])==2 and p.failed and o.execution_blocked and len(o.d.keys)==1


@pytest.mark.parametrize('fault',['swimming','x_bounds','y_bounds','trigger','overshoot'])
def test_failed_stop_retains_actual_observed_unsafe_state(case,fault):
    o,p=case;p.start();coord(o,p,p.target);set_moving(o,p)
    if fault=='swimming':o.d.memory[o.ds+9+94]=1
    if fault=='x_bounds':actor_word(o,3,155)
    if fault=='y_bounds':actor_word(o,5,168)
    if fault=='trigger':setflag(o,3)
    if fault=='overshoot':coord(o,p,p.target+p.sign)
    with pytest.raises(RuntimeError):p.handle_stop(watchstop(o))
    observed=p.record['last_observation']
    assert p.record['last_actor_table']==0x1000 and p.failed and o.execution_blocked
    assert not p.record['complete'] and len(o.d.keys)==1
    if fault=='swimming':assert observed['swimming']==1
    if fault=='x_bounds':assert observed['x']==155
    if fault=='y_bounds':assert observed['y']==168
    if fault=='trigger':assert observed['trigger'] is True
    if fault=='overshoot':assert observed[p.axis]==p.target+p.sign


def test_bad_table_pointer_retained_even_when_actor_cannot_be_read(case):
    o,p=case;p.start();word(o.d,o.ds+0x963,0xfffe)
    with pytest.raises(RuntimeError,match='table changed'):p.handle_stop(watchstop(o))
    assert p.record['last_actor_table']==0xfffe and p.failed and o.execution_blocked and len(o.d.keys)==1


def test_fresh_room_one_profile_uses_actual_unmodified_state(case):
    o,prior=case;o.d.memory[o.ds+9]=1;o.d.memory[o.ds+12]=0
    setflag(o,102,False);o.d.memory[o.ds+0x4000+65]=0
    p=module.MotionProbe(o,axis=prior.axis,target=prior.target,key=prior.key,profile='fresh-room1')
    rec=p.start()
    assert rec['profile']=='fresh-room1' and rec['initial']['room']==1 and rec['initial']['score']==0
    assert rec['initial']['shield_flag'] is False and rec['initial']['shield_location']==0
    coord(o,p,p.target);set_moving(o,p);p.handle_stop(watchstop(o));settle(o)
    assert p.poll() is True and rec['final']['room']==1 and rec['final']['shield_location']==0


@pytest.mark.parametrize('fault',['stairs_rejects_fresh','fresh_rejects_stairs','fresh_shield_flag','fresh_shield_item','fresh_score','bad_profile'])
def test_motion_profile_is_strict(case,fault):
    o,prior=case
    if fault=='bad_profile':
        with pytest.raises(RuntimeError):module.MotionProbe(o,axis=prior.axis,target=prior.target,key=prior.key,profile='other')
        return
    if fault!='fresh_rejects_stairs':
        o.d.memory[o.ds+9]=1;o.d.memory[o.ds+12]=0;setflag(o,102,False);o.d.memory[o.ds+0x4000+65]=0
    if fault=='fresh_shield_flag':setflag(o,102)
    if fault=='fresh_shield_item':o.d.memory[o.ds+0x4000+65]=255
    if fault=='fresh_score':o.d.memory[o.ds+12]=1
    profile='stairs' if fault=='stairs_rejects_fresh' else 'fresh-room1'
    p=module.MotionProbe(o,axis=prior.axis,target=prior.target,key=prior.key,profile=profile)
    with pytest.raises(RuntimeError):p.start()
    assert not o.d.keys and not o.d.calls and not p.active
