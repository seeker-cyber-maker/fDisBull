"""Synthetic unit-test captures; no native execution or original game content."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest
from examples.agi import build_leprechaun_scene as exporter
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'player'))
from fdisbull_player import Player


def fixture(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'AGI').write_bytes(b'authored engine')
    decoded=bytearray(0x140);decoded[:2]=(81).to_bytes(2,'little');decoded[3+63:3+65]=(0x11e).to_bytes(2,'little');decoded[3+0x11e:3+0x11e+7]=b'shield\0'
    object_bytes=bytes(value ^ b'Avis Durgan'[i%11] for i,value in enumerate(decoded));(source/'OBJECT').write_bytes(object_bytes)
    monkeypatch.setattr(exporter,'OBJECT_SHA',sha256(object_bytes).hexdigest())
    codes={n:bytearray(0xf00 if n==0 else 0x500 if n in (75,77) else 0x60 if n==36 else 1) for n in (0,36,48,73,74,75,76,77,78)}
    sites={0:{0xe4c:bytes([101,79]),0xe4e:bytes.fromhex('5c0f'),0xe50:bytes.fromhex('5e10'),0xe52:bytes.fromhex('050303'),
               0x878:bytes([101,11]),0x880:bytes.fromhex('5e18'),0x888:bytes.fromhex('070301'),0x892:bytes.fromhex('050303')},
           75:{0x1ed:bytes([101,21]),0x1f5:bytes.fromhex('5e0f'),0x1fb:bytes.fromhex('070306')},
           77:{0x3d2:bytes([101,25]),0x3d7:bytes([101,24]),0x3dd:bytes.fromhex('5c15'),0x3df:bytes.fromhex('050308')},
           36:{0x2f:bytes.fromhex('050301'),0x55:bytes.fromhex('290000'),0x58:bytes([101,13]),0x5a:bytes.fromhex('0d78')}}
    for n,items in sites.items():
        for off,data in items.items():codes[n][off:off+len(data)]=data
    text=b'Authored dialogue\0';key=b'Avis Durgan';encoded=bytes(x^key[i%len(key)] for i,x in enumerate(text))
    directory=bytearray(b'\xff\xff\xff'*79);volume=bytearray()
    for n,code in sorted(codes.items()):
        count=79;off=2+2*count;messages=bytes([count])+(off+len(text)).to_bytes(2,'little')+off.to_bytes(2,'little')*count+encoded
        payload=len(code).to_bytes(2,'little')+code+messages;directory[n*3:n*3+3]=len(volume).to_bytes(3,'big')
        volume+=b'\x12\x34\0'+len(payload).to_bytes(2,'little')+payload
    (source/'LOGDIR').write_bytes(directory);(source/'VOL.0').write_bytes(volume)
    hashes={str(n):load_logic(source/'LOGDIR',source,n,profile='2.917').resource_sha256 for n in codes}
    artifacts={}
    def frame(n):
        path=f'frame{n}';raw=path.encode();artifacts[path]=raw
        return {'path':path,'sha256':sha256(raw).hexdigest(),'metadata':{'frame_id':n,'mode_id':5,'width':320,'height':200,'source':'last_completed_guest_frame'}}
    states=[]
    anchors=((48,81,130),(73,90,139),(73,90,139),(75,149,115),
             (75,82,115),(77,87,70),(77,133,135),(36,88,131))
    for i,((room,x,y),score) in enumerate(zip(anchors,exporter.SCORES)):
        states.append({'room':room,'score':score,'ego':{'x':x,'y':y,'direction':0,'drawn':True},'ego_width':6,'ego_view':0,'step_size':1,'swimming':0,
            'in_water':False,'dead':False,'clover_carried':True,'clover_active':True,'bag_carried':i<2,'diamonds_carried':2<=i<4,
            'mushroom_carried':i<7,'mushroom_available':i<7,'shield_carried':i>=6,'small':False,'rat_removed':i>=4})
    observations={f'o{i}':{'state':s,'frame':frame(i*10+1)} for i,s in enumerate(states)}
    inp={'kind':'keyboard','key':'press:up','delivered':True,'complete':True,'delivery':{'accepted':True}}
    actions=[{'id':name,'before':f'o{i}','after':f'o{i+1}','complete':True,'messages_complete':True,'inputs':[deepcopy(inp)],'messages':[]} for i,name in enumerate(exporter.ACTION_IDS)]
    for i,n,off,num in ((1,0,0xe4c,79),(3,75,0x1ed,21),(5,77,0x3d2,25),(6,0,0x878,11),(6,36,0x58,13)):
        actions[i]['messages'].append({'logic':n,'source_offset':off,'message_id':num,'status':'completed','mode':'blocking',
            **{k:True for k in ('native_execution','native_execution_attempted','input_attempted','handler_return_observed','input_settled','window_closed')},
            'identity':{'resource_sha256':hashes[str(n)]},'message':{'resource_sha256':hashes[str(n)],'message_id':num,'text_sha256':sha256(text[:-1]).hexdigest(),'length':len(text)-1},
            'input':{'accepted':True},'keyboard_after':{'keyboard':{'pending_events':0,'owned_keys':0,'queued_guest_ms':0}},'frame':frame(i*10+5+len(actions[i]['messages']))})
    trace={'format':'fdisbull-agi-shield-trace-1','complete':True,'maximum_count':128,'events':[{'step':1}],'runs':[{'outcome':'breakpoint'}]}
    trace_raw=json.dumps(trace).encode();artifacts['shield-trace']=trace_raw
    proof={'format':'fdisbull-agi-shield-pickup-1','status':'verified','complete':True,'native_execution':True,
           'source_logic':77,'source_logic_sha256':hashes['77'],'item_source_offset':0x3dd,'score_source_offset':0x3df,
           'before':{'score':3,'item_location':0},'after':{'score':11,'item_location':255},'known_effects':{'score':11,'item_location':255},
           'item_writer':{'cause_offset':0x7482,'resume_offset':0x7486,'di_offset':0x403f},
           'score_writer':{'cause_offset':0x72da,'resume_offset':0x72de,'bx':3,'al':8},
           'handler_return':{'offset':0x2fa,'observed':True,'source_cursor_offset':0x3df,'stack_verified':True},
           'inventory_binding':{'source_sha256':exporter.OBJECT_SHA,'item':24,'stride':3,'name_offset':0x133,'carried_value':255,
                'base':0x4000,'end':0x4051,'location_linear':0x2404a,
                'records':{'21':{'record_offset':63,'name_offset':0x11e,'location_offset':65,'name_sha256':sha256(b'shield\0').hexdigest()}}},
           'trace':{'path':'shield-trace','sha256':sha256(trace_raw).hexdigest(),'event_count':1,'maximum_count':128}}
    proof_raw=json.dumps(proof).encode();artifacts['shield-proof']=proof_raw
    actions[5]['native_pickup']={'path':'shield-proof','sha256':sha256(proof_raw).hexdigest()}
    capture={'format':'fdisbull-agi-leprechaun-capture-1','source':{'agi_sha256':sha256(b'authored engine').hexdigest(),'object_sha256':exporter.OBJECT_SHA,'resources':hashes},
             'runtime':{'policy':'physical','fresh_game':True,'interventions':[]},'observations':observations,'actions':actions}
    return source,capture,lambda path:artifacts[path],artifacts


def test_seven_edges_separate_player_guards_checkpoint_and_privacy(tmp_path,monkeypatch):
    source,capture,loader,_=fixture(tmp_path,monkeypatch);scene,evidence=exporter.build(source,capture,loader)
    backend=ILSceneBackend(scene);player=Player(backend)
    assert 'partial' in player.execute('look').lower()
    def inventory(expected):
        assert {x['label'] for x in backend.observe()['inventory']} == set(expected)
        text=player.execute('inventory').lower()
        assert all(item in text for item in expected)
    inventory(['clover','bag','mushroom'])
    assert player.execute_result('use clover')['action_sent'] is False
    assert player.execute_result('use bag')['action_sent'] is False
    assert 'no action sent' in player.execute('use rat').lower()
    assert player.execute('use hole').startswith('Success:')
    inventory(['clover','bag','mushroom'])
    assert backend.save('hole')['status']=='saved';token=backend.observe()['context']['token']
    assert player.execute('use bag').startswith('Success:')
    inventory(['clover','diamonds','mushroom'])
    assert backend.act({'verb':'use','target':'bag','item':None,'context_token':token})['status']=='rejected'
    assert player.execute('use tunnel').startswith('Success:')
    inventory(['clover','diamonds','mushroom'])
    assert player.execute('use rat').startswith('Success:')
    inventory(['clover','mushroom'])
    assert player.execute('use throne').startswith('Success:')
    inventory(['clover','mushroom'])
    assert player.execute('take shield').startswith('Success:')
    inventory(['clover','mushroom','shield'])
    assert player.execute('take shield') == 'Rejected: Action refused.'
    assert player.execute('use exit').startswith('Success:')
    assert backend.state['$score']==14 and backend.state['$shield_carried'] and not backend.state['$mushroom_carried']
    inventory(['clover','shield'])
    assert 'shield' in player.execute('inventory')
    assert 'no action sent' in player.execute('use exit').lower()
    assert backend.load('hole')['status']=='restored'
    inventory(['clover','bag','mushroom'])
    assert player.execute('use bag').startswith('Success:')
    assert ILSceneBackend(scene).load('hole')['status']=='missing'
    assert 'Authored dialogue' not in str(scene) and 'Authored dialogue' not in str(evidence)


@pytest.mark.parametrize('fault',['extra_observation','missing_observation','disconnected','action_order','intervention','wrong_room','score','bag','rat','shield','mushroom','small','final_view','input','missing_message','message','frame','frame_order','source'])
def test_missing_or_contradictory_capture_refused(tmp_path,monkeypatch,fault):
    source,capture,loader,artifacts=fixture(tmp_path,monkeypatch)
    if fault=='extra_observation':capture['observations']['extra']=deepcopy(capture['observations']['o0'])
    if fault=='missing_observation':del capture['observations']['o1']
    if fault=='disconnected':capture['actions'][1]['before']='o0'
    if fault=='action_order':capture['actions'][1]['id']='pay-rat'
    if fault=='intervention':capture['runtime']['interventions']=['edit']
    if fault=='wrong_room':capture['observations']['o4']['state']['room']=76
    if fault=='score':capture['observations']['o6']['state']['score']=10
    if fault=='bag':capture['observations']['o2']['state']['bag_carried']=True
    if fault=='rat':capture['observations']['o4']['state']['rat_removed']=False
    if fault=='shield':capture['observations']['o6']['state']['shield_carried']=False
    if fault=='mushroom':capture['observations']['o7']['state']['mushroom_carried']=True
    if fault=='small':capture['observations']['o7']['state']['small']=True
    if fault=='final_view':capture['observations']['o7']['state']['ego_view']=1
    if fault=='input':capture['actions'][1]['inputs'][0]['delivery']['accepted']=False
    if fault=='missing_message':capture['actions'][1]['messages']=[]
    if fault=='message':capture['actions'][1]['messages'][0]['handler_return_observed']=False
    if fault=='frame':capture['observations']['o0']['frame']['sha256']='0'*64
    if fault=='frame_order':capture['observations']['o1']['frame']['metadata']['frame_id']=1
    if fault=='source':capture['source']['resources']['77']='0'*64
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('observation',range(8))
@pytest.mark.parametrize('axis',['x','y'])
def test_each_changed_boundary_coordinate_is_refused(tmp_path,monkeypatch,observation,axis):
    source,capture,loader,_=fixture(tmp_path,monkeypatch)
    capture['observations'][f'o{observation}']['state']['ego'][axis] += 1
    with pytest.raises(ValueError,match='route anchor differs'):
        exporter.build(source,capture,loader)


@pytest.mark.parametrize('logic,offset',[(0,0xe4e),(0,0xe50),(0,0xe52),(0,0x880),(0,0x888),(0,0x892),
                                           (75,0x1f5),(75,0x1fb),(77,0x3dd),(77,0x3df),(36,0x2f),(36,0x55),(36,0x58),(36,0x5a)])
def test_changed_source_effect_cannot_be_relabelled_with_new_resource_hash(tmp_path,monkeypatch,logic,offset):
    source,capture,loader,_=fixture(tmp_path,monkeypatch)
    directory=(source/'LOGDIR').read_bytes();address=int.from_bytes(directory[logic*3:logic*3+3],'big') & 0xfffff
    volume=bytearray((source/'VOL.0').read_bytes());volume[address+7+offset]=0;(source/'VOL.0').write_bytes(volume)
    capture['source']['resources'][str(logic)]=load_logic(source/'LOGDIR',source,logic,profile='2.917').resource_sha256
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('index,field,value',[(1,'status','incomplete'),(1,'mode','timed'),(1,'native_execution',False),
    (1,'input_attempted',False),(1,'handler_return_observed',False),(1,'window_closed',False),(1,'input_settled',False),
    (1,'source_offset',0xe4d),(1,'message_id',78),(1,'logic',75),(3,'cleanup_errors',[{'error':'lost'}])])
def test_message_completion_source_and_cleanup_guards(tmp_path,monkeypatch,index,field,value):
    source,capture,loader,_=fixture(tmp_path,monkeypatch);capture['actions'][index]['messages'][0][field]=value
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


def test_missing_and_changed_message_frame_keyboard_or_source_text_refused(tmp_path,monkeypatch):
    source,capture,loader,artifacts=fixture(tmp_path,monkeypatch);msg=capture['actions'][1]['messages'][0]
    for path,value in [('source','wrong'),('mode_id',True),('frame_id',11)]:
        original=msg['frame']['metadata'][path];msg['frame']['metadata'][path]=value
        with pytest.raises(ValueError):exporter.build(source,capture,loader)
        msg['frame']['metadata'][path]=original
    msg['keyboard_after']['keyboard']['pending_events']=1
    with pytest.raises(ValueError):exporter.build(source,capture,loader)
    msg['keyboard_after']['keyboard']['pending_events']=0;msg['message']['text_sha256']='0'*64
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('observation,field,value',[(0,'direction',1),(1,'drawn',False),(2,'ego_width',7),
    (3,'step_size',0),(4,'swimming',1),(5,'in_water',True),(6,'dead',True)])
def test_nonsettled_or_unsafe_boundary_refused(tmp_path,monkeypatch,observation,field,value):
    source,capture,loader,_=fixture(tmp_path,monkeypatch);state=capture['observations'][f'o{observation}']['state']
    (state['ego'] if field in ('direction','drawn') else state)[field]=value
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('target',['checkout','source','artifacts'])
def test_cli_refuses_output_inside_protected_tree(tmp_path,monkeypatch,target):
    source,capture,loader,_=fixture(tmp_path,monkeypatch);root=tmp_path/'artifacts';root.mkdir()
    checkout=Path(exporter.__file__).resolve().parents[2]
    output={'checkout':checkout/'disallowed-leprechaun-test','source':source/'out','artifacts':root/'out'}[target]
    monkeypatch.setattr(sys,'argv',['build_leprechaun_scene','--source',str(source),'--capture',str(tmp_path/'absent'),
                                   '--artifacts',str(root),'--output',str(output)])
    with pytest.raises(ValueError,match='fresh private directory'):exporter.main()
    assert not output.exists()


def test_leave_cave_requires_distinct_original_regrowth_message(tmp_path,monkeypatch):
    source,capture,loader,_=fixture(tmp_path,monkeypatch)
    capture['actions'][6]['messages']=[capture['actions'][6]['messages'][0]]
    with pytest.raises(ValueError,match='missing source-bound action message'):
        exporter.build(source,capture,loader)


@pytest.mark.parametrize('part,field,value', [
    (None,'format','other'),(None,'status','incomplete'),(None,'complete',False),(None,'native_execution',False),
    (None,'source_logic',75),(None,'source_logic_sha256','0'*64),(None,'item_source_offset',0x3de),(None,'score_source_offset',0x3e0),
    ('before','score',4),('before','item_location',255),('after','score',10),('after','item_location',0),
    ('known_effects','score',3),('known_effects','item_location',0),('item_writer','cause_offset',0x7483),
    ('item_writer','resume_offset',0x7487),('item_writer','di_offset',0x403e),('score_writer','cause_offset',0x72db),
    ('score_writer','resume_offset',0x72df),('score_writer','bx',2),('score_writer','al',7),
    ('handler_return','offset',0x2fb),('handler_return','observed',False),('handler_return','source_cursor_offset',0x3e0),
    ('handler_return','stack_verified',False),('inventory_binding','source_sha256','0'*64),('inventory_binding','base',0),
    ('inventory_binding','end',0x4050),('inventory_binding','stride',4),('inventory_binding','item',21),
    ('inventory_binding','name_offset',0x132),('inventory_binding','location_linear',0x2404b),('inventory_binding','carried_value',0),
    ('trace','event_count',0),('trace','event_count',128),('trace','maximum_count',127),('trace','sha256','0'*64)])
def test_shield_native_proof_fields_fail_closed(tmp_path,monkeypatch,part,field,value):
    source,capture,loader,artifacts=fixture(tmp_path,monkeypatch)
    proof=json.loads(artifacts['shield-proof']);target=proof if part is None else proof[part];target[field]=value
    raw=json.dumps(proof).encode();artifacts['shield-proof']=raw;capture['actions'][5]['native_pickup']['sha256']=sha256(raw).hexdigest()
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('field,value',[('record_offset',62),('name_offset',0x11d),('location_offset',64),('name_sha256','0'*64)])
def test_shield_name_record_is_source_bound(tmp_path,monkeypatch,field,value):
    source,capture,loader,artifacts=fixture(tmp_path,monkeypatch);proof=json.loads(artifacts['shield-proof'])
    proof['inventory_binding']['records']['21'][field]=value
    raw=json.dumps(proof).encode();artifacts['shield-proof']=raw;capture['actions'][5]['native_pickup']['sha256']=sha256(raw).hexdigest()
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('fault',['missing','proof_hash','trace_hash','trace_format','trace_incomplete','trace_empty','trace_runs','trace_count'])
def test_shield_requires_unmodified_complete_trace(tmp_path,monkeypatch,fault):
    source,capture,loader,artifacts=fixture(tmp_path,monkeypatch)
    if fault=='missing':del capture['actions'][5]['native_pickup']
    elif fault=='proof_hash':capture['actions'][5]['native_pickup']['sha256']='0'*64
    else:
        proof=json.loads(artifacts['shield-proof']);trace=json.loads(artifacts['shield-trace'])
        if fault=='trace_hash':artifacts['shield-trace']+=b' '
        if fault=='trace_format':trace['format']='other'
        if fault=='trace_incomplete':trace['complete']=False
        if fault=='trace_empty':trace['events']=[]
        if fault=='trace_runs':trace['runs']=[]
        if fault=='trace_count':proof['trace']['event_count']=2
        if fault not in ('trace_hash','trace_count'):
            raw=json.dumps(trace).encode();artifacts['shield-trace']=raw;proof['trace']['sha256']=sha256(raw).hexdigest()
        raw=json.dumps(proof).encode();artifacts['shield-proof']=raw;capture['actions'][5]['native_pickup']['sha256']=sha256(raw).hexdigest()
    with pytest.raises(ValueError):exporter.build(source,capture,loader)
