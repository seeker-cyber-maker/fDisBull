"""Synthetic observations only: no original game or native execution."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest
from examples.agi import build_mushroom_scene as exporter
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player


def fixture(tmp_path, monkeypatch):
    source = tmp_path / 'source';source.mkdir()
    (source/'AGI').write_bytes(b'authored engine');(source/'OBJECT').write_bytes(b'authored objects')
    monkeypatch.setattr(exporter, 'OBJECT_SHA', sha256(b'authored objects').hexdigest())
    code = bytearray(0x19b)
    code[0x162:0x16b] = bytes.fromhex('ff0e0205006100ff0000')
    code[0x183:0x18d] = bytes.fromhex('ff0b004a465e5aff0000')
    code[0x18f:0x191] = bytes([101,9]);code[0x195:0x19a] = bytes.fromhex('0503015c18')
    plain = b'fixture message\0';key=b'Avis Durgan';encrypted=bytes(b^key[i%len(key)] for i,b in enumerate(plain))
    messages = b'\x09' + (20+len(plain)).to_bytes(2,'little') + b'\0\0'*8 + (20).to_bytes(2,'little') + encrypted
    payload = len(code).to_bytes(2,'little') + code + messages
    directory = bytearray(b'\xff\xff\xff'*48);directory[47*3:47*3+3]=b'\0\0\0'
    (source/'LOGDIR').write_bytes(directory);(source/'VOL.0').write_bytes(b'\x12\x34\0'+len(payload).to_bytes(2,'little')+payload)
    res=load_logic(source/'LOGDIR',source,47,profile='2.917')
    pic=b'\xff';monkeypatch.setattr(exporter,'extract_v2_resource',lambda *args,**kwargs:{'payload':pic,'sha256':sha256(pic).hexdigest()})
    artifacts={}
    def frame(n):
        path=f'f{n}';raw=path.encode();artifacts[path]=raw
        return {'path':path,'sha256':sha256(raw).hexdigest(),'metadata':{'frame_id':n,'mode_id':5,'width':320,'height':200,'source':'last_completed_guest_frame'}}
    states=[]
    for i,(room,x,y) in enumerate(((33,154,87),(48,129,140),(47,94,90),(47,94,90),(33,154,55))):
        states.append({'room':room,'score':int(i==3),'ego':{'x':x,'y':y,'direction':0,'drawn':True},'ego_width':6,'ego_view':0,'step_size':1,'swimming':0,
                       **{k:False for k in ('in_water','dead','bridge_active','troll_removed','troll_paid')},
                       **{k:i==3 for k in ('mushroom_carried','mushroom_taken','mushroom_scored')}})
    frame_ids=[1,3,4,6,2];obs={f'o{i}':{'state':s,'frame':frame(frame_ids[i])} for i,s in enumerate(states)};obs['mushroom-midwater']=obs.pop('o4')
    inp=[{'kind':'keyboard','key':'press:up','delivered':True,'complete':True,'delivery':{'accepted':True}}]
    actions=[{'id':name,'before':f'o{i}','after':f'o{i+1}','complete':True,'messages_complete':True,'inputs':deepcopy(inp),'messages':[]} for i,name in enumerate(exporter.IDS)]
    msg={'logic':47,'source_offset':0x18f,'message_id':9,'status':'completed','mode':'blocking',
         **{k:True for k in ('native_execution','native_execution_attempted','input_attempted','handler_return_observed','input_settled','window_closed')},
         'identity':{'resource_sha256':res.resource_sha256},'message':{'resource_sha256':res.resource_sha256,'message_id':9,'text_sha256':sha256(plain[:-1]).hexdigest(),'length':len(plain)-1},
         'input':{'accepted':True},'keyboard_after':{'keyboard':{'pending_events':0,'owned_keys':0,'queued_guest_ms':0}},'frame':frame(5)}
    actions[2]['messages']=[msg]
    trace={'format':'fdisbull-agi-mushroom-trace-1','complete':True,'maximum_count':128,'events':[{'step':1}],'runs':[{'outcome':'breakpoint'}]}
    proof={'format':'fdisbull-agi-mushroom-pickup-1','status':'verified','complete':True,'native_execution':True,'source_logic':47,'source_logic_sha256':res.resource_sha256,
           'score_source_offset':0x195,'item_source_offset':0x198,'before':{'score':0,'item_location':0},'after':{'score':1,'item_location':255},
           'score_writer':{'cause_offset':0x72da,'resume_offset':0x72de,'bx':3,'al':1},'item_writer':{'cause_offset':0x7482,'resume_offset':0x7486,'di_offset':0x4048},
           'handler_return':{'offset':0x2fa,'observed':True,'source_cursor_offset':0x19a,'stack_verified':True},
           'inventory_binding':{'source_sha256':exporter.OBJECT_SHA,'item':24,'stride':3,'name_offset':0x133,'base':0x4000,'end':0x4051,'location_linear':0x2404a,'carried_value':255}}
    capture={'format':'fdisbull-agi-mushroom-capture-1','source':{'agi_sha256':sha256(b'authored engine').hexdigest(),'resources':{'47':res.resource_sha256}},
             'runtime':{'policy':'physical','fresh_game':True,'interventions':[]},'pictures':{str(n):sha256(pic).hexdigest() for n in (33,47,48)},
             'observations':obs,'actions':actions,'crossing_observation':'mushroom-midwater'}
    def loader():
        raw=json.dumps(trace).encode();artifacts['trace']=raw;proof['trace']={'path':'trace','sha256':sha256(raw).hexdigest(),'event_count':len(trace['events']),'maximum_count':128}
        raw=json.dumps(proof).encode();artifacts['proof']=raw;actions[2]['native_pickup']={'path':'proof','sha256':sha256(raw).hexdigest()}
        return lambda p:artifacts[p]
    return source,capture,proof,trace,loader,artifacts


def test_player_route_checkpoint_and_hash_only_provenance(tmp_path,monkeypatch):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    scene,evidence=exporter.build(source,capture,loader());backend=ILSceneBackend(scene);player=Player(backend)
    assert 'partial' in player.execute('look').lower()
    assert player.execute('use crossing').startswith('Success:')
    assert backend.save('crossing')['status']=='saved'
    token=backend.observe()['context']['token']
    assert player.execute('use trail').startswith('Success:')
    assert backend.act({'verb':'use','target':'trail','item':None,'context_token':token})['status']=='rejected'
    assert player.execute('take mushroom').startswith('Success:')
    assert backend.state['$score']==1 and backend.state['$mushroom_carried'] is True
    assert 'mushroom' in player.execute('inventory')
    assert player.execute('take mushroom') == 'Rejected: Action refused.'
    assert backend.load('crossing')['status']=='restored'
    assert player.execute('use trail').startswith('Success:') and player.execute('take mushroom').startswith('Success:')
    assert 'fixture message' not in str(scene) and 'fixture message' not in str(evidence)
    assert evidence['native_pickup']['trace']['event_count']==1
    assert ILSceneBackend(scene).load('crossing')['status']=='missing'
    stale=ILSceneBackend(scene,state={**{k:v['initial'] for k,v in scene['programs']['cross-to-island']['variables'].items()},'$score':1})
    assert Player(stale).execute('use crossing')=='Rejected: Action refused.'


@pytest.mark.parametrize('fault', ['intervention','source','picture','frame','midpoint','ordered','score','carried','input','message','key','trace','proof','item','writer','stack','bounds','location'])
def test_invalid_or_missing_evidence_is_rejected(tmp_path,monkeypatch,fault):
    source,capture,proof,trace,loader,artifacts=fixture(tmp_path,monkeypatch)
    if fault=='intervention':capture['runtime']['interventions']=['edit']
    if fault=='source':capture['source']['resources']['47']='0'*64
    if fault=='picture':capture['pictures']['47']='0'*64
    if fault=='frame':capture['observations']['o0']['frame']['sha256']='0'*64
    if fault=='midpoint':capture['observations']['mushroom-midwater']['state']['ego']['y']=54
    if fault=='ordered':capture['observations']['o1']['frame']['metadata']['frame_id']=1
    if fault=='score':capture['observations']['o3']['state']['score']=2
    if fault=='carried':capture['observations']['o3']['state']['mushroom_carried']=False
    if fault=='input':capture['actions'][0]['inputs'][0]['delivery']['accepted']=False
    if fault=='message':capture['actions'][2]['messages'][0]['handler_return_observed']=False
    if fault=='key':capture['actions'][2]['messages'][0]['input']['accepted']=False
    if fault=='trace':trace['events']=[]
    if fault=='proof':proof['status']='incomplete'
    if fault=='item':proof['inventory_binding']['item']=23
    if fault=='writer':proof['item_writer']['di_offset']+=1
    if fault=='stack':proof['handler_return']['stack_verified']=False
    if fault=='bounds':proof['inventory_binding']['end']+=1
    if fault=='location':proof['inventory_binding']['location_linear']+=1
    with pytest.raises(ValueError):exporter.build(source,capture,loader())


@pytest.mark.parametrize('field,value', [('status','incomplete'),('complete',False),('native_execution',False),
    ('source_logic',48),('source_logic_sha256','0'*64),('score_source_offset',0x196),('item_source_offset',0x199),
    ('cleanup_errors',[{'error':'lost'}])])
def test_native_pickup_identity_and_completion_are_required(tmp_path,monkeypatch,field,value):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    proof[field]=value
    with pytest.raises(ValueError): exporter.build(source,capture,loader())


@pytest.mark.parametrize('part,field,value', [
    ('before','score',1),('before','item_location',255),('after','score',0),('after','item_location',0),
    ('score_writer','cause_offset',0x72db),('score_writer','resume_offset',0x72df),('score_writer','bx',4),('score_writer','al',2),
    ('item_writer','cause_offset',0x7483),('item_writer','resume_offset',0x7487),('item_writer','di_offset',0x4049),
    ('handler_return','offset',0x2fb),('handler_return','observed',False),('handler_return','source_cursor_offset',0x199),
    ('handler_return','stack_verified',False),('inventory_binding','source_sha256','0'*64),('inventory_binding','stride',4),
    ('inventory_binding','name_offset',0x132),('inventory_binding','carried_value',0),('inventory_binding','base',0),
])
def test_pickup_effect_and_original_return_binding_required(tmp_path,monkeypatch,part,field,value):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    proof[part][field]=value
    with pytest.raises(ValueError): exporter.build(source,capture,loader())


@pytest.mark.parametrize('fault', ['format','incomplete','max','empty','runs','wronghash','count','exhausted'])
def test_trace_artifact_is_bound_and_bounded(tmp_path,monkeypatch,fault):
    source,capture,proof,trace,loader,artifacts=fixture(tmp_path,monkeypatch)
    if fault=='format':trace['format']='wrong'
    if fault=='incomplete':trace['complete']=False
    if fault=='max':trace['maximum_count']=127
    if fault=='empty':trace['events']=[]
    if fault=='runs':trace['runs']=[]
    if fault=='exhausted':trace['events']=[{}]*128
    load=loader()
    if fault in ('wronghash','count'):
        if fault=='wronghash':artifacts['trace']+=b' '
        else:
            proof['trace']['event_count']+=1
            raw=json.dumps(proof).encode();artifacts['proof']=raw;capture['actions'][2]['native_pickup']['sha256']=sha256(raw).hexdigest()
    with pytest.raises(ValueError):exporter.build(source,capture,load)


@pytest.mark.parametrize('action,index,field,value', [
    (0,0,'source','unknown'),(1,0,'mode_id',True),(2,0,'frame_id',None),
    (0,0,'width',0),(1,0,'height',0),
])
def test_observation_frames_have_explicit_usable_metadata(tmp_path,monkeypatch,action,index,field,value):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    ident=capture['actions'][action]['before'];capture['observations'][ident]['frame']['metadata'][field]=value
    with pytest.raises(ValueError):exporter.build(source,capture,loader())


@pytest.mark.parametrize('field,value', [('mode','nonblocking'),('status','incomplete'),('native_execution',False),
    ('input_attempted',False),('handler_return_observed',False),('window_closed',False),('input_settled',False),
    ('source_offset',0x18e),('message_id',8),('logic',46),('cleanup_errors',[{'error':'lost'}])])
def test_message_requires_original_return_and_qualified_input(tmp_path,monkeypatch,field,value):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    capture['actions'][2]['messages'][0][field]=value
    with pytest.raises(ValueError):exporter.build(source,capture,loader())


def test_changed_message_bytes_or_unsettled_keyboard_are_rejected(tmp_path,monkeypatch):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    msg=capture['actions'][2]['messages'][0]
    msg['message']['text_sha256']='0'*64
    with pytest.raises(ValueError):exporter.build(source,capture,loader())
    msg['message']['text_sha256']=sha256(b'fixture message').hexdigest()
    msg['keyboard_after']['keyboard']['pending_events']=1
    with pytest.raises(ValueError):exporter.build(source,capture,loader())


@pytest.mark.parametrize('offset,wrong',[(0x162,0),(0x183,0),(0x18f,0),(0x195,0),(0x198,0)])
def test_changed_source_instruction_refused_even_if_resource_hash_is_updated(tmp_path,monkeypatch,offset,wrong):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    volume=bytearray((source/'VOL.0').read_bytes());volume[7+offset]=wrong;(source/'VOL.0').write_bytes(volume)
    resource=load_logic(source/'LOGDIR',source,47,profile='2.917')
    capture['source']['resources']['47']=resource.resource_sha256
    with pytest.raises(ValueError):exporter.build(source,capture,loader())


@pytest.mark.parametrize('out', ['checkout','source','artifact'])
def test_cli_refuses_output_in_source_or_artifact_trees(tmp_path,monkeypatch,out):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    artifacts=tmp_path/'artifacts';artifacts.mkdir()
    checkout=Path(exporter.__file__).resolve().parents[2]
    output={'checkout':checkout/'disallowed-mushroom-test','source':source/'out','artifact':artifacts/'out'}[out]
    monkeypatch.setattr(sys,'argv',['build_mushroom_scene','--source',str(source),'--capture',str(tmp_path/'absent.json'),
                                  '--artifacts',str(artifacts),'--output',str(output)])
    with pytest.raises(ValueError,match='fresh private directory'):exporter.main()
    assert not output.exists()


def test_old_provisional_landing_is_rejected(tmp_path,monkeypatch):
    source,capture,proof,trace,loader,_=fixture(tmp_path,monkeypatch)
    capture['observations']['o1']['state']['ego'].update(x=151,y=164)
    with pytest.raises(ValueError,match='route waypoint differs'):
        exporter.build(source,capture,loader())
