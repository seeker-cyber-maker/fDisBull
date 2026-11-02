"""Synthetic KQ1 distance-handler stop tests; no native or original execution."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json

import pytest
from examples.agi import distance_probe as module
from examples.agi.verify_mushroom import MushroomRun
from test_agi_mushroom_route import AuthoredSession, memory_read, word


def flag(o,n,value=True):
    address=o.ds+0x109+n//8;mask=0x80>>(n%8)
    o.d.memory[address]=(o.d.memory[address]|mask) if value else (o.d.memory[address]&~mask)


def actor(o,n,x,y,width,height,view):
    base=o.ds+0x1000+43*n
    word(o.d,base+3,x);word(o.d,base+5,y);word(o.d,base+26,width);word(o.d,base+28,height)
    o.d.memory[base+7]=view;o.d.memory[base+37]=1


@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'read',memory_read)
    o=object.__new__(MushroomRun);o.d=AuthoredSession();o.d.session_id='authored-session';o.cs=0x1000;o.ds=0x20000
    o.root=o.source=tmp_path;o.inventory={'base':0x1800,'end':0x1851};o.report={};o.watch=None;o.watch_kind=None
    o.trace_active=False;o.quest_probe=None;o.motion_probe=None;o.execution_blocked=False;o._idle=lambda:True
    (tmp_path/'AGI').write_bytes(b'authored engine');monkeypatch.setattr(module,'AGI_SHA256',sha256(b'authored engine').hexdigest())
    handler=bytes([0x5a])*(module.HANDLER_END-module.HANDLER_START)
    o.d.memory[o.cs*16+module.HANDLER_START:o.cs*16+module.HANDLER_END]=handler
    monkeypatch.setattr(module,'HANDLER_SHA256',sha256(handler).hexdigest())
    word(o.d,o.ds+0x61d+69*4,0x47ef);word(o.d,o.ds+0x963,0x1000)
    word(o.d,o.ds+0x969,0x1800);word(o.d,o.ds+0x96b,0x1851)
    o.d.memory[o.ds+0x1800+3*5+2]=255;o.d.memory[o.ds+0x1800+3*21+2]=255
    o.d.memory[o.ds+9]=58;o.d.memory[o.ds+12]=26;o.d.memory[o.ds+9+86]=1
    word(o.d,o.ds+0x139,1);flag(o,102);flag(o,205)
    actor(o,0,83,101,6,32,0);actor(o,1,71,77,30,15,52)
    code=bytearray(0x240);code[0x234:0x238]=bytes((69,0,1,70));payload=len(code).to_bytes(2,'little')+code
    o.resources={58:SimpleNamespace(code=bytes(code),payload=payload,resource_sha256=sha256(payload).hexdigest())}
    monkeypatch.setattr(module,'LOGIC_SHA256',o.resources[58].resource_sha256)
    word(o.d,o.ds+0x979,0x3000);o.d.memory[o.ds+0x3002]=58;word(o.d,o.ds+0x3004,0x4000)
    o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code
    p=module.DistanceProbe(o);p.start();return o,p


def stop_for(o,p,stage):
    cursor=0x4238;word(o.d,0x40104,0x4235);word(o.d,0x40106,0x2fa);word(o.d,0x40108,cursor)
    o.d.memory[o.ds+9+70]=24
    o.d.register_state={'segments':{'cs':'0x1000','ds':'0x2000','ss':'0x4000'},
        'instruction_pointer':hex(0x48a6 if stage=='write' else 0x2fa),
        'general':{'eax':hex(24 if stage=='write' else cursor),'ebx':'0x46',
                   'esi':'0x1000' if stage=='write' else '0x4235','edi':'0x102b','ebp':'0x100',
                   'esp':hex(0xfc if stage=='write' else 0x108)}}
    reason={'breakpoint_id':o.watch}
    if stage=='write':reason['data_access']={'access':'w','instruction':{'space':'segmented','segment':'0x1000','offset':'0x48a2'}}
    return {'outcome':'breakpoint','session':{'stop_reason':reason}}


def test_original_write_then_real_return_binds_pose_and_stale_before_value(case):
    o,p=case;assert p.proof['before']['v70']==0 and p.proof['before']['expected_distance']==24
    assert p.proof['identity']['session_id']=='authored-session' and p.proof['identity']['ds']==0x2000
    p.handle_stop(stop_for(o,p,'write'))
    assert p.proof['known_result']==24 and p.proof['native_execution'] is True and not p.proof['complete']
    assert o.watch_kind=='quest-distance-return' and o.watch is not None
    # A submitted Enter can still have pending key release; stops must not query it.
    o._idle=lambda:(_ for _ in ()).throw(AssertionError('unexpected keyboard query'))
    p.handle_stop(stop_for(o,p,'return'))
    d=json.loads((o.root/'giant-distance.private.json').read_text())
    assert d['complete'] is True and d['status']=='verified' and d['known_result']==24
    assert d['after']['v70']==24 and d['handler_return']['stack_verified'] is True and not p.active
    assert o.watch is None and not o.d.runs


@pytest.mark.parametrize('fault',['foreign','outcome','session','cs','ds','source','op','handler','table_entry',
    'undrawn_sentinel','read','cause','resume','bx','ax','si','di','bp','sp','saved_si','return_slot','cursor','value',
    'giant_move','giant_view','giant_motion','giant_direction','giant_undrawn','ego_move','score','key','shield','chest'])
def test_writer_guards_reject_without_resuming(case,fault):
    o,p=case;out=stop_for(o,p,'write');r=o.d.register_state;access=out['session']['stop_reason']['data_access']
    if fault=='foreign':out['session']['stop_reason']['breakpoint_id']='foreign'
    if fault=='outcome':out['outcome']='guest_time'
    if fault=='session':o.d.session_id='other'
    if fault=='cs':r['segments']['cs']='0x1001'
    if fault=='ds':r['segments']['ds']='0x2001'
    if fault=='source':o.d.memory[o.ds+0x4000]^=1
    if fault=='op':
        code=bytearray(o.resources[58].code);code[0x237]=69
        o.resources[58].code=bytes(code);o.resources[58].payload=len(code).to_bytes(2,'little')+code
        o.resources[58].resource_sha256=sha256(o.resources[58].payload).hexdigest();o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code
    if fault=='handler':o.d.memory[o.cs*16+0x47ef]^=1
    if fault=='table_entry':word(o.d,o.ds+0x61d+69*4,0x47ee)
    if fault=='undrawn_sentinel':access['instruction']['offset']='0x4841';r['instruction_pointer']='0x4846';o.d.memory[o.ds+9+70]=255
    if fault=='read':access['access']='r'
    if fault=='cause':access['instruction']['offset']='0x48a1'
    if fault=='resume':r['instruction_pointer']='0x48a2'
    if fault=='bx':r['general']['ebx']='0x45'
    if fault=='ax':r['general']['eax']='0x19'
    if fault=='si':r['general']['esi']='0x1001'
    if fault=='di':r['general']['edi']='0x102c'
    if fault=='bp':r['general']['ebp']='0x2'
    if fault=='sp':r['general']['esp']='0x100'
    if fault=='saved_si':word(o.d,0x40104,0x4234)
    if fault=='return_slot':word(o.d,0x40106,0x2fb)
    if fault=='cursor':word(o.d,0x40108,0x4237)
    if fault=='value':o.d.memory[o.ds+9+70]=25
    if fault=='giant_move':word(o.d,o.ds+0x1000+43+3,72)
    if fault=='giant_view':o.d.memory[o.ds+0x1000+43+7]=51
    if fault=='giant_motion':o.d.memory[o.ds+0x1000+43+34]=1
    if fault=='giant_direction':o.d.memory[o.ds+0x1000+43+33]=1
    if fault=='giant_undrawn':o.d.memory[o.ds+0x1000+43+37]=0
    if fault=='ego_move':word(o.d,o.ds+0x1000+3,82)
    if fault=='score':o.d.memory[o.ds+12]=25
    if fault=='key':o.d.memory[o.ds+0x1800+17]=0
    if fault=='shield':o.d.memory[o.ds+0x1800+65]=0
    if fault=='chest':o.d.memory[o.ds+0x1800+8]=255
    before=len(o.d.calls)
    with pytest.raises((RuntimeError,ValueError)):p.handle_stop(out)
    assert p.failed and o.execution_blocked and not p.proof['complete'] and 'known_result' not in p.proof
    if fault=='source':assert p.proof['last_observed_v70']==24
    assert len(o.d.calls)==before and not o.d.runs


@pytest.mark.parametrize('fault',['ss','sp','ax','si','stack','access','source','native_value','pose'])
def test_original_return_requires_same_frame_cursor_pose_and_value(case,fault):
    o,p=case;p.handle_stop(stop_for(o,p,'write'));out=stop_for(o,p,'return');r=o.d.register_state
    if fault=='ss':r['segments']['ss']='0x4001'
    if fault=='sp':r['general']['esp']='0x10a'
    if fault=='ax':r['general']['eax']='0x4237'
    if fault=='si':r['general']['esi']='0x4234'
    if fault=='stack':word(o.d,0x40108,0x4237)
    if fault=='access':out['session']['stop_reason']['data_access']={'access':'w'}
    if fault=='source':o.d.memory[o.ds+0x4000]^=1
    if fault=='native_value':o.d.memory[o.ds+9+70]=23
    if fault=='pose':word(o.d,o.ds+0x1000+43+5,78)
    with pytest.raises(RuntimeError):p.handle_stop(out)
    assert p.failed and o.execution_blocked and p.proof['known_result']==24 and not p.proof['complete']
    assert 'handler_return' not in p.proof and not o.d.runs


def test_valid_write_persists_in_memory_and_report_if_canonical_save_fails(case,monkeypatch):
    o,p=case;out=stop_for(o,p,'write')
    def lost():raise OSError('authored proof write failure')
    monkeypatch.setattr(p,'persist',lost)
    with pytest.raises(OSError,match='proof write failure'):p.handle_stop(out)
    assert p.failed and o.execution_blocked and p.proof['known_result']==24 and not p.proof['complete']
    assert o.report['quest_distance'] is p.proof
    assert p.proof['failure']['persistence_error']['type']=='OSError' and not o.d.runs


def test_unknown_breakpoint_creation_latches_without_guest_execution(case,monkeypatch):
    o,p=case;p.active=False;p.failed=False;p.proof=None;o.watch=None;o.watch_kind=None;o.execution_blocked=False
    def lost(*args,**kwargs):raise OSError('unknown watch creation')
    monkeypatch.setattr(o,'arm',lost)
    with pytest.raises(OSError,match='unknown watch'):p.start()
    assert p.failed and o.execution_blocked and not o.d.runs
