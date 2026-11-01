"""Authored stop-protocol tests; no original resources or native execution."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from examples.agi import inventory_probe as module
from examples.agi.verify_mushroom import MushroomRun
sys.path.insert(0, str(Path(__file__).parent))
from test_agi_mushroom_route import AuthoredSession, memory_read, word


@pytest.fixture(params=[('key',40,5,0x2d6,0x2db,3,14,('item','return','score')),
                        ('chest',58,2,0x25d,0x25a,8,26,('score','item','return'))])
def case(request, tmp_path, monkeypatch):
    name,logic,item,item_off,score_off,delta,before,order=request.param
    monkeypatch.setattr(module,'read',memory_read)
    o=object.__new__(MushroomRun);o.d=AuthoredSession();o.root=tmp_path;o.source=tmp_path
    o.cs,o.ds=0x1000,0x20000;o.inventory={'base':0x1000,'end':0x1051};o.report={}
    o.watch,o.watch_kind=None,None;o.trace_active=False;o.trace_receipt=None;o.journal=[]
    data=bytearray(0x150);data[:2]=(81).to_bytes(2,'little');name_offset=0x90
    data[3+3*item:3+3*item+2]=name_offset.to_bytes(2,'little');data[3+name_offset:3+name_offset+len(name)+1]=name.encode()+b'\0'
    raw=bytes(x^b'Avis Durgan'[i%11] for i,x in enumerate(data));(tmp_path/'OBJECT').write_bytes(raw)
    monkeypatch.setattr(module,'OBJECT_SHA256',sha256(raw).hexdigest())
    code=bytearray(max(item_off+2,score_off+3)+1);code[item_off:item_off+2]=bytes((92,item));code[score_off:score_off+3]=bytes((5,3,delta))
    payload=len(code).to_bytes(2,'little')+code;o.resources={logic:SimpleNamespace(code=bytes(code),payload=payload,resource_sha256=sha256(payload).hexdigest())}
    o.d.memory[o.cs*16+0x7471:o.cs*16+0x7471+len(module.GET_HANDLER)]=module.GET_HANDLER
    o.d.memory[o.cs*16+0x72d4:o.cs*16+0x72d4+len(module.SCORE_WRITER)]=module.SCORE_WRITER
    word(o.d,o.ds+0x78d,0x7471);word(o.d,o.ds+0x969,0x1000);word(o.d,o.ds+0x96b,0x1051)
    word(o.d,o.ds+0x1000+3*item,name_offset);o.d.memory[o.ds+0x1000+name_offset:o.ds+0x1000+name_offset+len(name)+1]=name.encode()+b'\0'
    word(o.d,o.ds+0x979,0x3000);o.d.memory[o.ds+0x3002]=logic;word(o.d,o.ds+0x3004,0x4000)
    o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code;o.d.memory[o.ds+12]=before
    probe=module.PickupProbe(o,name=name,logic=logic,item=item,item_offset=item_off,score_offset=score_off,
                             score_delta=delta,before_score=before,order=order)
    probe.start()
    return o,probe


def stop_for(o,p,stage):
    effects=p.proof['known_effects'];score=effects['score'];item=effects['item_location']
    if stage=='score':score=p.before_score+p.score_delta
    if stage=='item':item=255
    o.d.memory[o.ds+12]=score;o.d.memory[p.location]=item
    cursor=0x4000+p.item_offset+2
    o.d.register_state={'segments':{'cs':'0x1000','ds':'0x2000','ss':'0x4000'},
        'instruction_pointer':hex({'item':0x7486,'score':0x72de,'return':0x2fa}[stage]),
        'general':{'eax':hex(cursor if stage=='return' else p.score_delta),'ebx':'0x3',
                   'esi':hex(0x4000+p.score_offset+3),'edi':hex(0x1000+p.item*3),
                   'ebp':'0x100','esp':hex(0x108 if stage=='return' else 0x100)}}
    word(o.d,0x40106,0x2fa);word(o.d,0x40108,cursor)
    reason={'breakpoint_id':o.watch}
    if stage!='return':reason['data_access']={'access':'w','instruction':{'space':'segmented','segment':'0x1000','offset':hex(0x72da if stage=='score' else 0x7482)}}
    return {'outcome':'breakpoint','session':{'stop_reason':reason}}


def test_both_original_orders_and_complete_trace(case):
    o,p=case
    for stage in p.order:
        o.journal.append({'result':{'outcome':'breakpoint'}})
        p.handle_stop(stop_for(o,p,stage))
    assert p.proof['complete'] is True and p.proof['status']=='verified' and not p.active
    assert p.proof['after']=={'score':p.before_score+p.score_delta,'item_location':255}
    assert p.proof['order']==list(p.order) and p.proof['trace']['event_count']==12
    assert json.loads((o.root/f'{p.name}-pickup.private.json').read_text())==p.proof
    assert json.loads((o.root/f'{p.name}-trace.private.json').read_text())['complete'] is True
    assert not o.trace_active and not o.d.runs


@pytest.mark.parametrize('fault',['foreign','outcome','cs','ds','code','operation','record','access','cause','resume','operands'])
def test_first_writer_rejected_without_resuming(case,fault):
    o,p=case;stage=p.order[0];out=stop_for(o,p,stage);reg=o.d.register_state
    if fault=='foreign':out['session']['stop_reason']['breakpoint_id']='foreign'
    if fault=='outcome':out['outcome']='guest_time'
    if fault=='cs':reg['segments']['cs']='0x1001'
    if fault=='ds':reg['segments']['ds']='0x2001'
    if fault=='code':o.d.memory[o.ds+0x4000]^=1
    if fault=='operation':
        code=bytearray(o.resources[p.logic].code);code[p.item_offset+1]^=1
        o.resources[p.logic].code=bytes(code);o.resources[p.logic].payload=len(code).to_bytes(2,'little')+code
        o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code
    if fault=='record':word(o.d,o.ds+0x1000+3*p.item,0x91)
    if fault=='access':out['session']['stop_reason']['data_access']['access']='r'
    if fault=='cause':out['session']['stop_reason']['data_access']['instruction']['offset']='0x1'
    if fault=='resume':reg['instruction_pointer']='0x1'
    if fault=='operands':reg['general']['edi' if stage=='item' else 'ebx']='0x9999'
    before=len(o.d.calls)
    with pytest.raises((RuntimeError,ValueError)):p.handle_stop(out)
    assert p.failed and not p.proof['complete'] and len(o.d.calls)==before and not o.d.runs
    with pytest.raises(RuntimeError):p.handle_stop(out)


@pytest.mark.parametrize('fault',['ss','sp','ax','stack','access'])
def test_real_return_guards(case,fault):
    o,p=case
    while p.order[p.index]!='return':p.handle_stop(stop_for(o,p,p.order[p.index]))
    out=stop_for(o,p,'return');r=o.d.register_state
    if fault=='ss':r['segments']['ss']='0x4001'
    if fault=='sp':r['general']['esp']='0x10a'
    if fault=='ax':r['general']['eax']='0x1'
    if fault=='stack':word(o.d,0x40108,0)
    if fault=='access':out['session']['stop_reason']['data_access']={'access':'w'}
    with pytest.raises(RuntimeError):p.handle_stop(out)
    assert p.failed and 'handler_return' not in p.proof and not o.d.runs


@pytest.mark.parametrize('mode',['saturated','cursor','lost'])
def test_trace_failure_retains_known_writes_and_received_events(case,mode):
    o,p=case
    while p.index<len(p.order)-1:p.handle_stop(stop_for(o,p,p.order[p.index]))
    stop=stop_for(o,p,p.order[p.index]);original=o.d.call
    def call(method,params=None):
        if method=='trace.read':
            if mode=='lost':raise OSError('lost reply')
            return {'events':[{'index':i} for i in range(128 if mode=='saturated' else 3)],'next_cursor':'next' if mode=='cursor' else None}
        return original(method,params)
    o.d.call=call
    with pytest.raises((RuntimeError,OSError)):p.handle_stop(stop)
    assert p.failed and not p.proof['complete'] and p.proof['known_effects']=={'score':p.before_score+p.score_delta,'item_location':255}
    assert len(o.trace_receipt['events'])==({'saturated':128,'cursor':3,'lost':0}[mode])
    assert not o.trace_receipt['complete'] and not o.d.runs
    assert json.loads((o.root/f'{p.name}-pickup.private.json').read_text())['known_effects']==p.proof['known_effects']


def test_partial_trace_persistence_and_conflicting_prefix(case):
    o,p=case
    p.handle_stop(stop_for(o,p,p.order[0]))
    known=[{'index':1},{'index':2}];o.trace_receipt['events']=deepcopy(known)
    while p.index<len(p.order)-1:p.handle_stop(stop_for(o,p,p.order[p.index]))
    original=o.d.call
    def call(method,params=None):
        if method=='trace.read':return {'events':[{'index':1},{'index':99}],'next_cursor':None}
        return original(method,params)
    o.d.call=call
    with pytest.raises(RuntimeError,match='retained prefix'):p.handle_stop(stop_for(o,p,p.order[p.index]))
    assert o.trace_receipt['events']==known and not o.trace_receipt['complete']
    ref=p.persist_partial_trace();data=(o.root/ref['path']).read_bytes()
    assert ref['sha256']==sha256(data).hexdigest() and json.loads(data)['events']==known
    assert json.loads((o.root/f'{p.name}-pickup.private.json').read_text())['partial_trace']==ref


def test_lost_trace_start_preserves_first_write_and_never_replays(case):
    o,p=case;stage=p.order[0];out=stop_for(o,p,stage);original=o.d.call
    def call(method,params=None):
        if method=='trace.start':raise OSError('lost start response')
        return original(method,params)
    o.d.call=call
    with pytest.raises(OSError,match='lost start'):p.handle_stop(out)
    expected={'score':p.before_score,'item_location':0}
    expected['score' if stage=='score' else 'item_location']=p.before_score+p.score_delta if stage=='score' else 255
    assert p.failed and p.proof['known_effects']==expected and o.trace_active and not o.d.runs
    with pytest.raises(RuntimeError):p.handle_stop(out)


def test_item_frame_requires_real_original_return_and_cursor(case):
    o,p=case
    while p.order[p.index]!='item':p.handle_stop(stop_for(o,p,p.order[p.index]))
    out=stop_for(o,p,'item');word(o.d,0x40106,0x2fb)
    with pytest.raises(RuntimeError,match='frame'):p.handle_stop(out)
    assert 'item_writer' not in p.proof and p.failed and not o.d.runs


def test_secondary_persistence_failure_never_masks_original_stop(case,monkeypatch):
    o,p=case;out=stop_for(o,p,p.order[0]);out['session']['stop_reason']['breakpoint_id']='foreign'
    def fail_persist():raise OSError('authored secondary save failure')
    monkeypatch.setattr(p,'persist',fail_persist)
    with pytest.raises(RuntimeError,match='Foreign stop preserved'):
        p.handle_stop(out)
    assert p.failed and o.execution_blocked and not o.d.runs
    assert o.report['quest_pickup_failure']=={
        'phase':'stop','type':'RuntimeError','message':'Foreign stop preserved',
        'persistence_error':{'type':'OSError','message':'authored secondary save failure'}}
    assert p.proof['failure']==o.report['quest_pickup_failure'] and not p.proof['complete']


def test_lost_watch_creation_latches_owner_and_prevents_advance(case):
    from examples.agi.verify_leprechaun import CaveRun
    o,p=case;p.active=False;p.failed=False;p.index=0;p.proof=None;o.watch=None;o.watch_kind=None
    o.execution_blocked=False;o.d.calls.clear();original=o.d.call
    def lose_response(method,params=None):
        if method=='breakpoints.create':
            o.d.calls.append((method,deepcopy(params)))
            raise OSError('authored unknown breakpoint creation')
        return original(method,params)
    o.d.call=lose_response
    with pytest.raises(OSError,match='unknown breakpoint creation'):p.start()
    assert p.failed and p.active and o.execution_blocked and o.watch is None
    assert o.report['quest_pickup_failure']['phase']=='setup' and not o.d.runs
    calls=list(o.d.calls)
    with pytest.raises(RuntimeError,match='Earlier execution/observation failed'):
        CaveRun.advance(o,50)
    assert o.d.calls==calls and not o.d.runs


def test_setup_failure_preserves_primary_when_diagnostic_save_also_fails(case,monkeypatch):
    o,p=case;p.active=False;p.failed=False;p.index=0;p.proof=None;o.watch=None;o.watch_kind=None
    original=p.persist;count=[]
    def persist():
        count.append(1)
        if len(count)>1:raise OSError('authored diagnostic write failure')
        return original()
    monkeypatch.setattr(p,'persist',persist)
    def arm(*args,**kwargs):raise RuntimeError('authored unknown setup')
    monkeypatch.setattr(o,'arm',arm)
    with pytest.raises(RuntimeError,match='unknown setup'):p.start()
    assert o.execution_blocked and p.failed and not o.d.runs
    assert o.report['quest_pickup_failure']['persistence_error']['message']=='authored diagnostic write failure'
