"""Authored unit-only resources/captures: no original game bytes or dialogue."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

from examples.agi import build_dragon_mirror_scene as exporter
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'player'))
from fdisbull_player import Player, ProcessBackend


COMMANDS = ('take dagger', 'take bucket', 'use rope', 'use water', 'use passage',
            'use dragon', 'take mirror', 'use exit')
NATIVE = {'session_id': 'unit-session', 'cs': 0x1234, 'ds': 0x2345}


@pytest.fixture
def case(tmp_path, monkeypatch):
    """Hand-authored boundary and receipt contract, never a native replay."""
    source = tmp_path/'source'; source.mkdir()
    (source/'AGI').write_bytes(b'authored unit engine; not executable')
    decoded = bytearray(1024); decoded[:2] = (81).to_bytes(2, 'little')
    for item in exporter.ITEMS.values():
        offset = 0x100+20*item
        name = f'unit-item-{item}'.encode()+b'\0'
        decoded[3+3*item:5+3*item] = offset.to_bytes(2, 'little')
        decoded[3+offset:3+offset+len(name)] = name
    object_raw = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(decoded))
    (source/'OBJECT').write_bytes(object_raw)
    monkeypatch.setattr(exporter, 'OBJECT_SHA', sha256(object_raw).hexdigest())
    codes = {n: bytearray(0x1000) for n in (0, 1, 3, 12, 22, 49, 50, 51, 52, 101)}
    instructions = {
        3: {0x102: (101, 13), 0x104: (5, 3, 2), 0x1b8: (101, 8),
            0x1ba: (92, 1), 0x1bc: (5, 3, 5)},
        12: {0x6d6: (92, 11), 0x6d8: (101, 3), 0x6da: (5, 3, 2), 0x774: (101, 25)},
        22: {0x6: (3, 68, 0), 0x9: (3, 69, 0), 0xdd: (37, 0, 142, 83)},
        49: {0x4d: (5, 3, 1), 0x507: (5, 3, 2), 0x50a: (18, 52)},
        52: {0x4d: (92, 26), 0x58: (5, 3, 2)},
        51: {0x4d: (5, 3, 1), 0x37f: (92, 19), 0x381: (101, 24), 0x385: (5, 3, 8),
             0x45e: (101, 34), 0x460: (94, 26), 0x462: (7, 3, 2), 0x465: (5, 3, 7),
             0x427: (13, 88), 0x429: (101, 33), 0x42b: (94, 26), 0x42d: (7, 3, 2),
             0x430: (13, 91), 0x45c: (13, 88), 0x468: (43, 3, 1), 0x46b: (13, 91),
             0x46d: (81, 3, 40, 137, 0, 21),
             0x473: (3, 75, 2), 0x3dd: (101, 7),
             0x32d: (255, 11, 0, 26, 104, 59, 127, 255, 0, 0),
             0x3df: (255, 11, 0, 105, 96, 145, 166, 1, 75, 0, 255, 0x46, 0),
             0x432: (255, 253, 11, 0, 105, 96, 145, 166, 1, 75, 0, 255, 0x6e, 0)},
        0: {0xf0d: (101, 10)},
    }
    for logic, entries in instructions.items():
        for offset, values in entries.items(): codes[logic][offset:offset+len(values)] = bytes(values)
    # Authored scalar/OR action gates paired with the two position parents.
    water_guard = bytes((255, 7, 88, 252, 14, 2, 42, 0, 43, 0,
                         14, 3, 42, 0, 43, 0, 44, 0,
                         14, 2, 45, 0, 44, 0, 252, 255))
    for offset, skip in ((0x40b, 0x0b), (0x440, 0x1a)):
        gate = water_guard+skip.to_bytes(2, 'little')
        codes[51][offset:offset+len(gate)] = gate
    text = b'Authored unit-only response\0'
    encoded = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(text))
    directory = bytearray(b'\xff\xff\xff'*102); volume = bytearray()
    for number, code in sorted(codes.items()):
        count, offset = 34, 2+2*34
        messages = bytes((count,))+(offset+len(text)).to_bytes(2, 'little')
        messages += offset.to_bytes(2, 'little')*count+encoded
        payload = len(code).to_bytes(2, 'little')+code+messages
        directory[3*number:3*number+3] = len(volume).to_bytes(3, 'big')
        volume += b'\x12\x34\0'+len(payload).to_bytes(2, 'little')+payload
    # An authored empty vector picture has a uniform default priority-4 plane.
    picture=b'\xff';picdir=bytearray(b'\xff\xff\xff'*53)
    picdir[52*3:52*3+3]=len(volume).to_bytes(3,'big')
    volume+=b'\x12\x34\0'+len(picture).to_bytes(2,'little')+picture
    # An authored single priority-0 pixel blocks one six-pixel baseline ray.
    dragon_picture=bytes((0xf2, 0, 0xf6, 136, 166, 136, 166, 0xff))
    picdir[51*3:51*3+3]=len(volume).to_bytes(3,'big')
    volume+=b'\x12\x34\0'+len(dragon_picture).to_bytes(2,'little')+dragon_picture
    (source/'PICDIR').write_bytes(picdir)
    (source/'LOGDIR').write_bytes(directory); (source/'VOL.0').write_bytes(volume)
    resources = {str(n): load_logic(source/'LOGDIR', source, n, profile='2.917').resource_sha256
                 for n in codes}
    artifacts = {}

    def frame(number):
        path = f'unit-frame-{number}'; raw = path.encode(); artifacts[path] = raw
        return {'path': path, 'sha256': sha256(raw).hexdigest(), 'metadata': {
            'frame_id': number, 'mode_id': 5, 'width': 320, 'height': 200,
            'source': 'last_completed_guest_frame'}}

    def state(index):
        room, x, y = exporter.ROUTE_CONTRACT['anchors'][index]
        carried = {'dagger': index >= 1, 'bucket': index >= 2,
                   'water': index in (4,5), 'mirror': index >= 7}
        flags = {str(n): False for n in (20,21,22,23,67,81,88,91,100,162,164,165,167,176,177,178,179)}
        flags.update({'67':index>=1, '81':index>=2, '88':index in (4,5), '91':index in (4,5),
                      '100':index>=7, '162':index>=3, '164':index>=4, '165':index>=7,
                      '167':index>=5, '176':index>=2, '177':index>=3, '179':index>=3})
        return {'room':room, 'score':exporter.ROUTE_CONTRACT['scores'][index],
            'ego':{'x':x,'y':y,'direction':0,'drawn':True},
            'ego_view':74 if index==3 else 73 if index==4 else 0,
            'ego_width':8 if index==3 else 11 if index==4 else 6,
            'ego_height':33 if index==3 else 20 if index==4 else 32,
            'step_size':1,'swimming':1 if index==4 else 0,'in_water':False,
            'dead':False,'ignore_blocks':index in (1,3,5,6,7),'player_control':1,
            'control_direction':0,'window':0,'initializing':False,
            'quest_variables':{'68':240 if index==4 else 0,'69':2 if index==4 else 0,
                               '74':int(index>=7),'75':2 if index>=6 else 0,'94':int(index==4)},
            'quest_flags':flags,'dragon_actor':{'drawn':index==5,'x':46,'y':117,'width':23},
            'inventory_locations':{str(item):255 if carried[name] else 0 for name,item in exporter.ITEMS.items()},
            **{name+'_carried':value for name,value in carried.items()}}

    def observed(index, number):
        return {'state':state(index),'frame':frame(number),'guest_ms':number*10}

    def message(logic, offset, number, number_frame):
        resource = resources[str(logic)]
        return {'format':'fdisbull-agi-print-observation-1','status':'completed','mode':'blocking',
            **{k:True for k in ('native_execution','native_execution_attempted','input_attempted',
                                'handler_return_observed','input_settled','window_closed')},
            'logic':logic,'source_offset':offset,'message_id':number,
            'identity':{'format':'fdisbull-agi-print-observer-1',**NATIVE,'resource_sha256':resource,
                        'record':0x600,'state_revision':1,'epoch':'unit-epoch'},
            'message':{'resource_sha256':resource,'message_id':number,
                       'text_sha256':sha256(text[:-1]).hexdigest(),'length':len(text)-1},
            'input':{'accepted':True},'keyboard_after':{'keyboard':{
                'pending_events':0,'owned_keys':0,'queued_guest_ms':0}},
            'frame':frame(number_frame),'guest_ms':number_frame*10}

    def inputs(command):
        return [{'kind':'keyboard','key':key,'delivered':True,'complete':True,'delivery':{'accepted':True}}
                for key in ('type:'+command,'press:enter')]

    observations = {name:observed(i,(i+1)*100) for i,name in enumerate(exporter.OBSERVATION_IDS)}
    actions = []
    for i,name in enumerate(exporter.ACTION_IDS):
        actions.append({'id':name,'before':exporter.OBSERVATION_IDS[i],
            'after':exporter.OBSERVATION_IDS[i+1],'complete':True,'messages_complete':True,
            'inputs':inputs('unit-action'),'messages':[
                message(logic,offset,number,(i+1)*100+50+j*10)
                for j,(logic,offset,number) in enumerate(exporter.REQUIRED_MESSAGES.get(i,()))]})
    records = exporter.object_records(object_raw)

    def artifact(name, data):
        raw=json.dumps(data).encode();artifacts[name]=raw
        return {'path':name,'sha256':sha256(raw).hexdigest()}

    def proof(mirror):
        item=19 if mirror else 26;name='mirror' if mirror else 'dragon-water'
        trace=artifact(name+'-trace',{'format':'fdisbull-agi-quest-trace-1','name':name,
            'complete':True,'maximum_count':128,'events':[{'unit-fetch':1}],'runs':[{'unit-run':True}]})
        trace.update(event_count=1,maximum_count=128)
        record=records[item];base=0x4000
        binding={'source_sha256':exporter.OBJECT_SHA,'base':base,'end':base+81,'stride':3,
            'item':item,**{k:v for k,v in record.items() if k!='name_length'},'carried_value':255,
            'location_linear':NATIVE['ds']*16+base+record['location_offset']}
        before={'score':20 if mirror else 15,'item_location':0 if mirror else 255}
        after={'score':28 if mirror else 20,'item_location':255 if mirror else 0}
        value={'format':'fdisbull-agi-quest-pickup-1' if mirror else 'fdisbull-agi-dragon-water-1',
            'status':'verified','complete':True,'native_execution':True,'source_logic':51,
            'source_logic_sha256':resources['51'],'item':item,'item_source_offset':0x37f if mirror else 0x460,
            'before':before,'after':after,'known_effects':deepcopy(after),'identity':deepcopy(NATIVE),
            'instruction_completed':None,'writer_stop_stage':'after data access; instruction completion unknown',
            'inventory_binding':binding,'trace':trace,'handler_return':{
                'offset':0x2fa,'observed':True,'source_cursor_offset':0x381 if mirror else 0x462,
                'stack_verified':True}}
        if mirror:
            value.update(name=name,score_source_offset=0x385,score_delta=8,order=['item','return','score'],
                item_writer={'cause_offset':0x7482,'resume_offset':0x7486,'di_offset':base+3*item},
                score_writer={'cause_offset':0x72da,'resume_offset':0x72de,'bx':3,'al':8},pre_print_trace=deepcopy(trace))
        else:
            value.update(print_source_offset=0x45e,subtract_source_offset=0x462,add_source_offset=0x465,
                order=['drop','return','subtract','add'],
                drop_writer={'cause_offset':0x74ba,'resume_offset':0x74be,'di_offset':base+3*item},
                subtract_writer={'cause_offset':0x72fa,'resume_offset':0x72fe,'bx':3,'al':2},
                add_writer={'cause_offset':0x72da,'resume_offset':0x72de,'bx':3,'al':7},drop_trace=deepcopy(trace))
        return artifact(name+'-proof',value)

    actions[5]['native_water']=proof(False);actions[6]['native_pickup']=proof(True)
    actions[5]['inputs']=inputs('throw water');actions[6]['inputs']=inputs('get mirror')
    water_before=observed(5,620)
    water_before['state']['ego'].update(observations['dragon-retreated']['state']['ego'])
    mirror_before=observed(6,720)
    mirror_before['state']['ego'].update(observations['mirror-taken']['state']['ego'])
    controls=[]
    for command,number,response in [('get mirror',820,(0,0xf0d,10)),('throw water',850,(51,0x3dd,7))]:
        controls.append({'command':command,'before_observation':observed(7,number),
            'after_observation':observed(7,number+20),'inputs':inputs(command),
            'messages':[message(*response,number+10)]})
    capture={'format':'fdisbull-agi-dragon-mirror-capture-1','fixture_scope':'synthetic-unit-test-only',
        'source':{'agi_sha256':sha256((source/'AGI').read_bytes()).hexdigest(),
                  'object_sha256':exporter.OBJECT_SHA,'resources':resources},
        'runtime':{'policy':'physical','fresh_game':True,'interventions':[],'session_id':NATIVE['session_id']},
        'observations':observations,'actions':actions,'water_before':water_before,
        'pictures':{'52':sha256(picture).hexdigest(),'51':sha256(dragon_picture).hexdigest()},
        'mirror_before':mirror_before,'repeat_controls':controls}
    return source,capture,lambda path:artifacts[path],artifacts


def rewrite_proof(capture, artifacts, mirror, mutate):
    ref=capture['actions'][6 if mirror else 5]['native_pickup' if mirror else 'native_water']
    value=json.loads(artifacts[ref['path']]);mutate(value)
    artifacts[ref['path']]=json.dumps(value).encode();ref['sha256']=sha256(artifacts[ref['path']]).hexdigest()


def test_authored_route_preserves_every_boundary_and_private_source(case):
    source,capture,loader,_=case
    scene,evidence=exporter.build(source,capture,loader)
    backend=ILSceneBackend(scene);player=Player(backend)
    assert evidence['route_contract']['status']=='qualified-fresh-segment'
    assert evidence['prior_native_boundary_witness'] is None
    assert 'Historical DOS diagnostics' not in scene['contexts'][5]['description']
    assert evidence['route_contract']['qualification_witness']['fresh_game'] is True
    assert evidence['route_contract']['qualification_witness']['interventions']==[]
    assert len(evidence['edges'])==8 and len(evidence['observations'])==9
    assert len(evidence['repeat_controls'])==2
    assert evidence['origin']=={'kind':'fresh-original-boot','fresh_game':True,'interventions':[]}
    assert player.execute_result('take mirror')['action_sent'] is False
    for phase,command in enumerate(COMMANDS):
        assert player.execute(command).startswith('Success:'),command
        expected=exporter.project_state(capture['observations'][exporter.OBSERVATION_IDS[phase+1]]['state'])
        assert {k:backend.state['$'+k] for k in exporter.FIELDS}==expected
    assert backend.state['$phase']==8 and backend.state['$score']==28
    assert {x['label'] for x in backend.observe()['inventory']}=={'dagger','bucket','mirror'}
    assert player.execute('take mirror')=='Rejected: Action refused.'
    assert 'Authored unit-only response' not in str(scene)+str(evidence)
    assert 'unit-item-' not in str(scene)+str(evidence)


def test_build_automatically_surfaces_source_band_with_separate_pic_and_pose_limits(case):
    source,capture,loader,_=case
    scene,evidence=exporter.build(source,capture,loader)
    analysis=evidence['spatial_predicate_analysis']
    assert analysis['status']=='source_candidates_only' and analysis['complete'] is True
    assert analysis['source']=={'logic':51,'resource_sha256':capture['source']['resources']['51']}
    assert analysis['origin']==[131,136] and analysis['actor_width']==6
    assert analysis['native_reachability']=='not_established_by_this_capture'
    finding=analysis['findings'][0]
    assert (finding['inside_if_offset'],finding['outside_if_offset'])==(0x3df,0x432)
    assert finding['shared_scalar_context']['matches_supplied_state'] is True
    assert finding['source_picture_sha256']==capture['pictures']['51']
    assert finding['effects_complete'] is True
    contrast=finding['action_contrasts'][0]
    assert contrast['item']==26 and contrast['label']=='water'
    assert [contrast[k]['linear_score_delta'] for k in ('inside','outside')]==[-2,5]
    for side,offset,ident in (('inside',0x429,33),('outside',0x45e,34)):
        prints=[op for op in contrast[side]['operations'] if op['operation']=='print']
        assert [(op['source_offset'],op['arguments']) for op in prints]==[(offset,[ident])]
    record=finding['bands'][0]
    assert record['predicate_band']['row_runs']==[[167,105,146]]
    assert record['predicate_band']['count']==41
    assert record['predicate_band']['reachability']=={'status':'unknown'}
    geometry=record['static_geometry']
    assert geometry['origin_ray']['first_blocked']['origin']==[131,166]
    assert geometry['proposal']['inside']==[130,166]
    assert geometry['proposal']['outside']==[130,167]
    assert geometry['proposal']['ray']['waypoints']==[[131,136],[130,136],[130,167]]
    assert geometry['native_reachability']=='unknown'
    metric=record['geometric_contrast']
    assert [metric[k+'_distance'] for k in ('origin','inside','outside')]==[96,125,126]
    assert 'not a throw-range predicate' in metric['scope']
    for text in (scene['contexts'][5]['description'],scene['objects'][5]['description']):
        assert '41 origins' in text and 'y=167' in text
        assert 'Static proposal: (130, 167)' in text
        assert 'Native reachability' in text
    assert len(exporter.FIELDS)==44 and len(scene['programs'])==8
    assert len(scene['programs']['douse-dragon']['variables'])==45


def test_source_annotation_changes_neither_action_programs_nor_projection_guards(case,monkeypatch):
    source,capture,loader,_=case
    scene,_=exporter.build(source,capture,loader)
    monkeypatch.setattr(exporter,'describe_posn_boundaries',lambda *a,**k:'Authored annotation control.')
    control,_=exporter.build(source,capture,loader)
    assert scene['programs']==control['programs']
    assert scene['contexts'][5]['description']!=control['contexts'][5]['description']
    assert scene['objects'][5]['description']!=control['objects'][5]['description']


@pytest.mark.parametrize('fault',('missing','mismatch','actor_bool','actor_missing'))
def test_automatic_analysis_requires_bound_picture_and_typed_reference_pose(case,fault):
    source,capture,loader,_=case
    if fault=='missing':del capture['pictures']['51']
    elif fault=='mismatch':capture['pictures']['51']='0'*64
    elif fault=='actor_bool':capture['observations']['dragon-before']['state']['dragon_actor']['x']=True
    else:del capture['observations']['dragon-before']['state']['dragon_actor']['width']
    with pytest.raises(ValueError):exporter.build(source,capture,loader)


@pytest.mark.parametrize('phase',range(9))
@pytest.mark.parametrize('coordinate',('x','y'))
def test_each_qualified_route_anchor_is_required(case,phase,coordinate):
    source,c,loader,_=case
    c['observations'][exporter.OBSERVATION_IDS[phase]]['state']['ego'][coordinate]+=1
    with pytest.raises(ValueError,match='route anchor'):
        exporter.build(source,c,loader)


@pytest.mark.parametrize('extra',('water_before','mirror_before'))
def test_transaction_does_not_teleport_between_launch_and_completed_boundary(case,extra):
    source,c,loader,_=case
    c[extra]['state']['ego']['x']+=1
    with pytest.raises(ValueError,match='transaction ego pose'):
        exporter.build(source,c,loader)


@pytest.mark.parametrize('fault', ['missing_action','extra_action','disconnected','extra_observation',
    'missing_observation','duplicate_boundary','restored','intervention','hidden_origin',
    'typed_integer','typed_boolean','water_flag_without_item','water_item_without_flag',
    'rope_footprint','underwater_footprint','underwater_air','unsafe_water_launch','mirror_outside',
    'retreat_actor','retreat_callback','missing_control','control_effect','control_clock',
    'missing_water_before','missing_mirror_before','pending_direction','pending_modal','initializing',
    'repeated_transaction_command','wrong_height','boolean_height','pending_follow_callback','missing_surface_source',
    'wrong_underwater_physical_flag','missing_picture','wrong_picture_hash'])
def test_missing_or_contradictory_contract_refused(case,fault):
    source,c,loader,_=case;obs=c['observations']
    if fault=='missing_action':c['actions'].pop()
    elif fault=='extra_action':c['actions'].append(deepcopy(c['actions'][-1]))
    elif fault=='disconnected':c['actions'][3]['before']='fresh'
    elif fault=='extra_observation':obs['extra']=deepcopy(obs['fresh'])
    elif fault=='missing_observation':del obs['well-ready']
    elif fault=='duplicate_boundary':c['actions'][0]['after']='fresh'
    elif fault=='restored':c['runtime']['fresh_game']=False
    elif fault=='intervention':c['runtime']['interventions']=[{'kind':'unit-edit'}]
    elif fault=='hidden_origin':c['native_origin']={'unit':'unqualified-load'}
    elif fault=='typed_integer':obs['fresh']['state']['score']=False
    elif fault=='typed_boolean':obs['fresh']['state']['dead']=0
    elif fault=='water_flag_without_item':
        obs['water-ready']['state']['inventory_locations']['26']=0
        obs['water-ready']['state']['water_carried']=False
    elif fault=='water_item_without_flag':obs['water-ready']['state']['quest_flags']['88']=False
    elif fault=='rope_footprint':obs['well-ready']['state']['ego_width']=6
    elif fault=='underwater_footprint':obs['water-ready']['state']['ego_view']=0
    elif fault=='underwater_air':obs['water-ready']['state']['quest_variables']['69']=0
    elif fault=='unsafe_water_launch':c['water_before']['state']['ego'].update(x=130,y=130)
    elif fault=='mirror_outside':c['mirror_before']['state']['ego']['x']=60
    elif fault=='retreat_actor':obs['dragon-retreated']['state']['dragon_actor']['drawn']=True
    elif fault=='retreat_callback':obs['dragon-retreated']['state']['quest_flags']['21']=True
    elif fault=='missing_control':c['repeat_controls'].pop()
    elif fault=='control_effect':c['repeat_controls'][0]['after_observation']['state']['score']+=1
    elif fault=='control_clock':c['repeat_controls'][1]['before_observation']['guest_ms']=8000
    elif fault=='missing_water_before':del c['water_before']
    elif fault=='missing_mirror_before':del c['mirror_before']
    elif fault=='pending_direction':obs['fresh']['state']['control_direction']=1
    elif fault=='pending_modal':obs['fresh']['state']['window']=1
    elif fault=='initializing':obs['fresh']['state']['initializing']=True
    elif fault=='repeated_transaction_command':c['actions'][5]['inputs']*=2
    elif fault=='wrong_height':obs['water-ready']['state']['ego_height']=32
    elif fault=='boolean_height':obs['fresh']['state']['ego_height']=True
    elif fault=='pending_follow_callback':c['water_before']['state']['quest_flags']['20']=True
    elif fault=='missing_surface_source':del c['source']['resources']['22']
    elif fault=='wrong_underwater_physical_flag':obs['water-ready']['state']['in_water']=True
    elif fault=='missing_picture':del c['pictures']
    elif fault=='wrong_picture_hash':c['pictures']['52']='0'*64
    with pytest.raises(ValueError):exporter.build(source,c,loader)


@pytest.mark.parametrize('fault',['missing_message','duplicate_message','missing_time','stale_time',
    'incomplete_modal','foreign_session','duplicate_frame','nonfinite_time','frame_hash','unaccepted_input'])
def test_message_input_and_clock_evidence_is_required(case,fault):
    source,c,loader,_=case;m=c['actions'][5]['messages'][0]
    if fault=='missing_message':c['actions'][5]['messages']=[]
    elif fault=='duplicate_message':c['actions'][5]['messages'].append(deepcopy(m))
    elif fault=='missing_time':del m['guest_ms']
    elif fault=='stale_time':m['guest_ms']=c['water_before']['guest_ms']
    elif fault=='incomplete_modal':m['handler_return_observed']=False
    elif fault=='foreign_session':m['identity']['session_id']='other'
    elif fault=='duplicate_frame':c['mirror_before']['frame']=deepcopy(c['water_before']['frame'])
    elif fault=='nonfinite_time':c['mirror_before']['guest_ms']=float('nan')
    elif fault=='frame_hash':c['mirror_before']['frame']['sha256']='0'*64
    elif fault=='unaccepted_input':c['actions'][5]['inputs'][0]['delivery']['accepted']=False
    with pytest.raises(ValueError):exporter.build(source,c,loader)


@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('fault',['missing','partial','raw_without_known_effect','foreign_session',
    'wrong_source','wrong_return','wrong_writer','wrong_named_item','unbounded_trace',
    'incomplete_trace','disagreeing_early_trace','overclaimed_instruction'])
def test_native_transactions_require_qualified_effects_and_returns(case,mirror,fault):
    source,c,loader,artifacts=case
    index,key=(6,'native_pickup') if mirror else (5,'native_water')
    if fault=='missing':del c['actions'][index][key]
    else:
        def mutate(p):
            if fault=='partial':p['complete']=False
            elif fault=='raw_without_known_effect':
                p['last_observation']=deepcopy(p['after']);p['known_effects']['score']=p['before']['score']
            elif fault=='foreign_session':p['identity']['session_id']='other'
            elif fault=='wrong_source':p['source_logic_sha256']='0'*64
            elif fault=='wrong_return':p['handler_return']['source_cursor_offset']+=1
            elif fault=='wrong_writer':p['item_writer' if mirror else 'drop_writer']['cause_offset']+=1
            elif fault=='wrong_named_item':p['inventory_binding']['name_sha256']='0'*64
            elif fault=='unbounded_trace':p['trace']['event_count']=128
            elif fault=='incomplete_trace':
                ref=p['trace'];trace=json.loads(artifacts[ref['path']]);trace['complete']=False
                artifacts[ref['path']]=json.dumps(trace).encode();ref['sha256']=sha256(artifacts[ref['path']]).hexdigest()
                p['pre_print_trace' if mirror else 'drop_trace']=deepcopy(ref)
            elif fault=='disagreeing_early_trace':p['pre_print_trace' if mirror else 'drop_trace']['sha256']='0'*64
            elif fault=='overclaimed_instruction':p['instruction_completed']=True
        rewrite_proof(c,artifacts,mirror,mutate)
    with pytest.raises(ValueError):exporter.build(source,c,loader)


def test_pretyped_water_with_intervening_ordinary_movement_remains_one_command(case):
    source,c,loader,_=case
    inputs=c['actions'][5]['inputs'];move=deepcopy(inputs[1]);move['key']='press:right'
    inputs[1:1]=[deepcopy(move),deepcopy(move)]
    _,evidence=exporter.build(source,c,loader)
    assert evidence['extra_observations']['water_before']['state']['x']==c['observations']['dragon-retreated']['state']['ego']['x']


@pytest.mark.parametrize('width',[11,19])
def test_both_source_underwater_footprints_keep_height_twenty(case,width):
    source,c,loader,_=case
    c['observations']['water-ready']['state'].update(ego_width=width,ego_height=20)
    _,evidence=exporter.build(source,c,loader)
    assert evidence['observations']['water-ready']['state']['ego_width']==width


def test_underwater_provenance_retains_picture_binding_after_extra_observations(case):
    source,c,loader,_=case
    _,evidence=exporter.build(source,c,loader)
    water=evidence['underwater_baseline']
    assert set(water)=={'room','picture_sha256','origin','width','priority_values','in_water','scope'}
    state=c['observations']['water-ready']['state']
    assert water['room']==52 and water['picture_sha256']==c['pictures']['52']
    assert water['origin']==[state['ego']['x'],state['ego']['y']]
    assert water['width']==state['ego_width'] and water['priority_values']==[4]
    assert water['in_water'] is False


def test_direct_player_stale_precondition_and_before_mirror_checkpoint(case):
    source,c,loader,_=case;scene,_=exporter.build(source,c,loader)
    backend=ILSceneBackend(scene);player=Player(backend)
    for command in COMMANDS[:6]:assert player.execute(command).startswith('Success:')
    assert backend.save('before-mirror')['status']=='saved'
    old=backend.observe()['context']['token']
    backend.state['$bucket_carried']=False;before=deepcopy(backend.state)
    assert backend.act({'verb':'take','target':'mirror','item':None,'context_token':old})['status']=='rejected'
    assert backend.state==before
    assert backend.load('before-mirror')['status']=='restored'
    assert backend.act({'verb':'take','target':'mirror','item':None,'context_token':old})['status']=='rejected'
    assert player.execute('take mirror').startswith('Success:')
    assert player.execute('take mirror')=='Rejected: Action refused.'
    assert ILSceneBackend(scene).load('before-mirror')['status']=='missing'


def test_separate_content_process_plays_all_actions_and_checkpoint(case,tmp_path,monkeypatch):
    source,c,loader,_=case;scene,_=exporter.build(source,c,loader)
    path=tmp_path/'unit-scene.json';path.write_text(json.dumps(scene))
    checkout=Path(__file__).resolve().parents[1]
    monkeypatch.setenv('PYTHONPATH',str(checkout/'src')+os.pathsep+str(checkout/'player'))
    service=ProcessBackend([sys.executable,'-m','fdisbull.il_scenes',str(path)])
    try:
        player=Player(service)
        for command in COMMANDS[:6]:assert player.execute(command).startswith('Success:')
        old=service.observe()['context']['token'];assert service.save('mirror')['status']=='saved'
        for command in COMMANDS[6:]:assert player.execute(command).startswith('Success:')
        assert service.observe()['context']['id']=='phase-8'
        assert {o['label'] for o in service.observe()['inventory']}=={'dagger','bucket','mirror'}
        assert service.load('mirror')['status']=='restored'
        assert service.act({'verb':'take','target':'mirror','item':None,'context_token':old})['status']=='rejected'
        assert player.execute('take mirror').startswith('Success:')
    finally:service.close()


@pytest.mark.parametrize('target',['existing','source','checkout','symlink'])
def test_cli_refuses_nonfresh_or_protected_output(case,tmp_path,target):
    source,_,_,_=case;root=tmp_path/'artifacts';root.mkdir()
    existing=tmp_path/'existing';existing.mkdir();link=tmp_path/'link';link.symlink_to(tmp_path/'missing')
    output={'existing':existing,'source':source/'out','checkout':Path(exporter.__file__).parents[2]/'unit-out',
            'symlink':link}[target]
    with pytest.raises(ValueError,match='fresh private directory'):
        exporter.main(['--source',str(source),'--capture',str(tmp_path/'absent'),'--artifacts',str(root),
                       '--output',str(output)])


def test_cli_emits_only_authored_outputs_and_rejects_artifact_escape(case,tmp_path):
    source,c,_,artifacts=case;root=tmp_path/'artifacts';root.mkdir()
    for name,raw in artifacts.items():(root/name).write_bytes(raw)
    cap=root/'capture.json';cap.write_text(json.dumps(c));output=tmp_path/'new-private-scene'
    args=['--source',str(source),'--capture',str(cap),'--artifacts',str(root)]
    exporter.main(args+['--output',str(output)])
    assert {p.name for p in output.iterdir()}=={'scene.json','provenance.json'}
    evidence=json.loads((output/'provenance.json').read_bytes())
    assert evidence['scene_sha256']==sha256((output/'scene.json').read_bytes()).hexdigest()
    f=c['observations']['fresh']['frame'];outside=tmp_path/'outside'
    outside.write_bytes(artifacts[f['path']]);f['path']='../outside';cap.write_text(json.dumps(c))
    refused=tmp_path/'refused'
    with pytest.raises(ValueError,match='artifact path outside'):
        exporter.main(args+['--output',str(refused)])
    assert not refused.exists()
    (root/'frame-link').symlink_to(outside);f['path']='frame-link';cap.write_text(json.dumps(c))
    with pytest.raises(ValueError,match='artifact path outside'):
        exporter.main(args+['--output',str(refused)])
    assert not refused.exists()
