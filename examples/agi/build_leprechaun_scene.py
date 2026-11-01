"""Build an authored partial cave scene from supplied physical observations.

Hashes bind inputs, not their authenticity. Original game text stays private.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from fdisbull.agi import load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend
from examples.agi.build_clip_scene import frame_evidence, json_artifact, require

OBJECT_SHA = '2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985'
ACTION_IDS = ('enter-hole','open-bag','follow-tunnel','pay-rat','enter-throne','take-shield','leave-cave')
ROUTE_ANCHORS = ((48,81,130),(73,90,139),(73,90,139),(75,149,115),
                 (75,82,115),(77,87,70),(77,133,135),(36,88,131))
SCORES = (6,6,9,9,3,3,11,14)
BYTE_FIELDS = ('room','score','x','y','direction','ego_width','ego_view','step_size','swimming')
BOOL_FIELDS = ('drawn','in_water','dead','clover_carried','bag_carried','diamonds_carried',
               'mushroom_carried','shield_carried','clover_active','mushroom_available','small','rat_removed')
FIELDS = BYTE_FIELDS + BOOL_FIELDS


def digest(data):return sha256(data).hexdigest()


def route_coordinates(states):
    """Match the declared route boundaries; capture evidence remains required."""
    return len(states)==len(ROUTE_ANCHORS) and all(
        (s['room'],s['x'],s['y']) == anchor for s,anchor in zip(states,ROUTE_ANCHORS))


def project_state(raw):
    require(isinstance(raw, dict) and isinstance(raw.get('ego'), dict), 'missing state')
    ego = raw['ego']
    s = {k: ego.get(k) if k in ('x','y','direction','drawn') else raw.get(k) for k in FIELDS}
    require(all(type(s[k]) is int and 0 <= s[k] <= 255 for k in BYTE_FIELDS) and
            all(type(s[k]) is bool for k in BOOL_FIELDS), 'invalid typed state')
    require(s['x'] < 160 and s['y'] < 168 and s['direction'] == 0 and s['drawn'] and
            s['ego_width'] == 6 and s['step_size'] == 1 and s['swimming'] == 0 and
            not s['in_water'] and not s['dead'], 'unsettled or unsafe boundary')
    return s


def source_check(resources):
    # Bind selected items and score changes, not a claim about complete scripts.
    sites = {0:{0xe4e:bytes.fromhex('5c0f'),0xe50:bytes.fromhex('5e10'),0xe52:bytes.fromhex('050303'),
                0x880:bytes.fromhex('5e18'),0x888:bytes.fromhex('070301'),0x892:bytes.fromhex('050303')},
             75:{0x1f5:bytes.fromhex('5e0f'),0x1fb:bytes.fromhex('070306')},
             77:{0x3dd:bytes.fromhex('5c15'),0x3df:bytes.fromhex('050308')},
             36:{0x2f:bytes.fromhex('050301'),0x55:bytes.fromhex('290000'),
                 0x58:bytes.fromhex('650d'),0x5a:bytes.fromhex('0d78')}}
    for n, checks in sites.items():
        require(n in resources, 'missing source logic')
        resource = resources[n]; starts = set(logic_layout(resource.payload)['instructions'])
        require(all(offset+2 in starts and resource.code[offset:offset+len(code)] == code for offset,code in checks.items()), 'source effect binding differs')


def shield_pickup_evidence(reference, loader, resource, object_bytes):
    proof=json_artifact(reference,loader,'shield pickup')
    def exact(mapping, expected):
        return isinstance(mapping,dict) and all(type(mapping.get(k)) is type(v) and mapping[k]==v for k,v in expected.items())
    require(proof.get('format')=='fdisbull-agi-shield-pickup-1' and proof.get('status')=='verified' and
            proof.get('complete') is True and proof.get('native_execution') is True and
            proof.get('cleanup_errors',[])==[] and type(proof.get('source_logic')) is int and proof['source_logic']==77 and
            proof.get('source_logic_sha256')==resource.resource_sha256 and type(proof.get('item_source_offset')) is int and
            proof['item_source_offset']==0x3dd and type(proof.get('score_source_offset')) is int and proof['score_source_offset']==0x3df,
            'shield pickup source or completion differs')
    require(exact(proof.get('before'),{'score':3,'item_location':0}) and
            exact(proof.get('after'),{'score':11,'item_location':255}) and
            exact(proof.get('known_effects'),{'score':11,'item_location':255}), 'shield pickup state differs')
    require(exact(proof.get('item_writer'),{'cause_offset':0x7482,'resume_offset':0x7486}) and
            exact(proof.get('score_writer'),{'cause_offset':0x72da,'resume_offset':0x72de,'bx':3,'al':8}) and
            exact(proof.get('handler_return'),{'offset':0x2fa,'observed':True,'source_cursor_offset':0x3df,'stack_verified':True}),
            'shield writer or return differs')
    binding=proof.get('inventory_binding');writer=proof['item_writer']
    require(exact(binding,{'source_sha256':OBJECT_SHA,'item':24,'stride':3,'name_offset':0x133,'carried_value':255}) and
            type(binding.get('base')) is int and type(binding.get('end')) is int and
            0 < binding['base'] < binding['end'] <= 65536 and binding['end']-binding['base']==81 and
            type(binding.get('location_linear')) is int and binding['base']+74 <= binding['location_linear'] <= 0xfffff and
            (binding['location_linear']-binding['base']-74)%16==0 and
            type(writer.get('di_offset')) is int and writer['di_offset']==binding['base']+63, 'shield inventory bounds differ')
    decoded=bytes(value ^ b'Avis Durgan'[i%11] for i,value in enumerate(object_bytes))
    require(len(decoded)>3+0x11e and int.from_bytes(decoded[:2],'little')==81 and
            int.from_bytes(decoded[3+63:3+65],'little')==0x11e,'shield object source differs')
    name_end=decoded.find(b'\0',3+0x11e)
    require(3+0x11e < name_end < len(decoded) and name_end-(3+0x11e)<=64,'shield name bounds differ')
    name_hash=digest(decoded[3+0x11e:name_end+1]);records=binding.get('records')
    require(isinstance(records,dict) and exact(records.get('21'),{'record_offset':63,'name_offset':0x11e,
            'location_offset':65,'name_sha256':name_hash}), 'shield name record differs')
    trace=proof.get('trace')
    require(isinstance(trace,dict) and type(trace.get('event_count')) is int and 1<=trace['event_count']<128 and
            type(trace.get('maximum_count')) is int and trace['maximum_count']==128, 'shield trace bounds differ')
    raw=json_artifact(trace,loader,'shield trace')
    require(raw.get('format')=='fdisbull-agi-shield-trace-1' and raw.get('complete') is True and
            type(raw.get('maximum_count')) is int and raw['maximum_count']==128 and
            isinstance(raw.get('events'),list) and len(raw['events'])==trace['event_count'] and
            all(isinstance(x,dict) for x in raw['events']) and isinstance(raw.get('runs'),list) and bool(raw['runs']) and
            all(isinstance(x,dict) for x in raw['runs']), 'shield trace incomplete')
    return {'sha256':reference['sha256'],'source_logic':77,'source_logic_sha256':resource.resource_sha256,
            'item_source_offset':0x3dd,'score_source_offset':0x3df,'item':21,'shield_name_sha256':name_hash,
            'handler_return':deepcopy(proof['handler_return']),
            'trace':{k:trace[k] for k in ('sha256','event_count','maximum_count')}}


def build(source,capture,artifact_loader):
    source=Path(source)
    require(isinstance(capture,dict) and capture.get('format') == 'fdisbull-agi-leprechaun-capture-1','invalid capture')
    runtime=capture.get('runtime')
    require(isinstance(runtime,dict) and runtime.get('policy') == 'physical' and runtime.get('fresh_game') is True and runtime.get('interventions') == [],'unqualified runtime')
    identity=capture.get('source')
    require(isinstance(identity,dict) and identity.get('agi_sha256') == digest((source/'AGI').read_bytes()) and
            identity.get('object_sha256') == OBJECT_SHA and digest((source/'OBJECT').read_bytes()) == OBJECT_SHA,'source identity mismatch')
    expected=identity.get('resources')
    require(isinstance(expected,dict) and all(str(n) in expected for n in (0,36,48,73,74,75,76,77,78)) and len(expected)<=256,'missing source identities')
    resources={}
    for key,value in expected.items():
        require(isinstance(key,str) and re.fullmatch(r'0|[1-9][0-9]{0,2}',key) is not None and int(key)<=255,'invalid source logic')
        resource=load_logic(source/'LOGDIR',source,int(key),profile='2.917')
        require(resource.resource_sha256 == value,'source logic mismatch');resources[int(key)]=resource
    source_check(resources)
    observations,actions=capture.get('observations'),capture.get('actions')
    require(isinstance(observations,dict) and isinstance(actions,list) and len(actions)==7 and
            all(isinstance(a,dict) and a.get('id') == k for a,k in zip(actions,ACTION_IDS)), 'expected seven ordered actions')
    require(all(actions[i].get('before') == actions[i-1].get('after') for i in range(1,7)), 'actions not contiguous')
    ids=[actions[0].get('before')]+[a.get('after') for a in actions]
    require(all(isinstance(x,str) and bool(x) for x in ids) and len(set(ids))==8 and set(observations)==set(ids),'missing, duplicate or extra observations')
    checked={}
    for ident in ids:
        value=observations[ident];require(isinstance(value,dict),'invalid observation')
        checked[ident]={'state':project_state(value.get('state')),'frame':frame_evidence(value.get('frame'),artifact_loader)}
    states=[checked[ident]['state'] for ident in ids]
    require(route_coordinates(states),'route anchor differs')
    for i,s in enumerate(states):
        require(s['score']==SCORES[i] and s['clover_carried'] and s['clover_active'] and
                s['bag_carried']==(i<2) and s['diamonds_carried']==(2<=i<4) and
                s['shield_carried']==(i>=6) and s['mushroom_carried']==(i<7) and
                s['mushroom_available']==(i<7) and s['rat_removed']==(i>=4) and
                (i!=7 or (not s['small'] and s['ego_view']==0)), 'inventory, flags or score transition differs')
    frame_ids=[checked[ident]['frame']['metadata']['frame_id'] for ident in ids]
    require(all(b>a for a,b in zip(frame_ids,frame_ids[1:])), 'observation frames out of order')
    shield_proof=shield_pickup_evidence(actions[5].get('native_pickup'),artifact_loader,resources[77],(source/'OBJECT').read_bytes())
    message_evidence=[]
    for i,action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True,'incomplete action')
        inputs=action.get('inputs')
        require(isinstance(inputs,list) and bool(inputs) and all(isinstance(x,dict) and x.get('kind')=='keyboard' and
            isinstance(x.get('key'),str) and bool(x['key']) and x.get('delivered') is True and x.get('complete') is True and
            isinstance(x.get('delivery'),dict) and x['delivery'].get('accepted') is True for x in inputs),'unqualified physical input')
        messages=action.get('messages');require(isinstance(messages,list),'missing messages')
        bindings=[];last_frame=frame_ids[i]
        for msg in messages:
            require(isinstance(msg,dict) and msg.get('status')=='completed' and msg.get('mode')=='blocking' and
                all(msg.get(k) is True for k in ('native_execution','native_execution_attempted','input_attempted','handler_return_observed','input_settled','window_closed')) and
                msg.get('cleanup_errors',[])==[],'unqualified message completion')
            logic,off,num=msg.get('logic'),msg.get('source_offset'),msg.get('message_id')
            require(type(logic) is int and logic in resources and type(off) is int and off>=0 and type(num) is int and 1<=num<=255,'invalid message source')
            r=resources[logic];require(off+2 in logic_layout(r.payload)['instructions'] and r.code[off:off+2]==bytes((101,num)),'message instruction mismatch')
            value=logic_messages(r)[r.resource_sha256].get(str(num));require(isinstance(value,str) and bool(value),'missing source message')
            encoded=value.encode('cp437');ni,nm=msg.get('identity'),msg.get('message')
            require(isinstance(ni,dict) and ni.get('resource_sha256')==r.resource_sha256 and isinstance(nm,dict) and
                    nm.get('resource_sha256')==r.resource_sha256 and type(nm.get('message_id')) is int and nm['message_id']==num and
                    nm.get('text_sha256')==digest(encoded) and type(nm.get('length')) is int and nm['length']==len(encoded),'message binding differs')
            key,keyboard=msg.get('input'),msg.get('keyboard_after')
            require(isinstance(key,dict) and key.get('accepted') is True and isinstance(keyboard,dict) and
                    isinstance(keyboard.get('keyboard'),dict) and all(type(keyboard['keyboard'].get(k)) is int and keyboard['keyboard'][k]==0
                        for k in ('pending_events','owned_keys','queued_guest_ms')),'message input not settled')
            frame=frame_evidence(msg.get('frame'),artifact_loader);current=frame['metadata']['frame_id']
            require(last_frame<current<frame_ids[i+1], 'message frame out of order');last_frame=current
            bindings.append({'logic':logic,'source_offset':off,'message_id':num,'resource_sha256':r.resource_sha256,'text_sha256':digest(encoded),'frame':frame})
        required = {1: [{(0,0xe4c,79)}], 3: [{(75,0x1ed,21)}],
                    5: [{(77,0x3d2,25),(77,0x3d7,24)}], 6: [{(0,0x878,11)},{(36,0x58,13)}]}
        for alternatives in required.get(i, []):
            require(any((m['logic'],m['source_offset'],m['message_id']) in alternatives for m in bindings),
                    'missing source-bound action message')
        message_evidence.append(bindings)
    variables={'$phase':{'type':'u8','initial':0},**{'$'+k:{'type':'bool' if k in BOOL_FIELDS else 'u8','initial':states[0][k]} for k in FIELDS}}
    authored=('The recorded route enters the hole.','The recorded action opens the bag.','The recorded route reaches the rat.',
              'The recorded payment clears the rat.','The recorded route reaches the throne room.',
              'The recorded action takes the shield.','The recorded route exits the cave.')
    programs={}
    for i,name in enumerate(ACTION_IDS):
        before,after=states[i:i+2]
        body=[{'id':'phase','op':'require','condition':{'op':'eq','left':{'var':'$phase'},'right':i}}]
        body += [{'id':'guard-'+k,'op':'require','condition':{'op':'eq','left':{'var':'$'+k},'right':before[k]}} for k in FIELDS]
        body += [{'id':'set-'+k,'op':'set','var':'$'+k,'value':after[k]} for k in FIELDS if before[k]!=after[k]]
        body += [{'id':'set-phase','op':'set','var':'$phase','value':i+1},{'id':'message','op':'text','resource':'message'}]
        programs[name]={'format':'fdisbull-il-1','role':'uil','variables':variables,'resources':{'message':{'kind':'text','text':authored[i]}},'body':body}
    targets=('hole','bag','tunnel','rat','throne','shield','exit')
    objects=[{'id':name,'context':'phase-'+str(i),'label':name,'aliases':[], 'description':'The next recorded action.',
              'bindings':[{'verb':'take' if name=='shield' else 'use','program':ACTION_IDS[i]}],
              **({'inventory_when':{'op':'eq','left':{'var':'$shield_carried'},'right':True}} if name=='shield' else
                 {'inventory_when':{'op':'and','conditions':[{'op':'eq','left':{'var':'$phase'},'right':1},
                                                        {'op':'eq','left':{'var':'$bag_carried'},'right':True}]}} if name=='bag' else {})} for i,name in enumerate(targets)]
    for name,variable in (('clover','clover_carried'),('diamonds','diamonds_carried'),('mushroom','mushroom_carried')):
        objects.append({'id':'inventory-'+name,'context':'phase-0','label':name,'aliases':[],
                        'description':'A recorded carried item.','bindings':[],
                        'visible_when':{'op':'eq','left':False,'right':True},
                        'inventory_when':{'op':'eq','left':{'var':'$'+variable},'right':True}})
    objects.append({'id':'inventory-bag-before','context':'phase-0','label':'bag','aliases':[],
                    'description':'A recorded carried item.','bindings':[],
                    'visible_when':{'op':'eq','left':False,'right':True},
                    'inventory_when':{'op':'and','conditions':[{'op':'eq','left':{'var':'$phase'},'right':0},
                                                               {'op':'eq','left':{'var':'$bag_carried'},'right':True}]}})
    scene={'format':'fdisbull-il-scene-1','programs':programs,'partial':True,'objects':objects,
           'contexts':[{'id':'phase-'+str(i),'title':'Observed cave route','description':'A partial reconstruction of supplied physical-play observations.',
                        'when':{'op':'eq','left':{'var':'$phase'},'right':i}} for i in range(8)]}
    ILSceneBackend(scene)
    evidence={'format':'fdisbull-agi-leprechaun-z-evidence-1','source':deepcopy(identity),'object_sha256':OBJECT_SHA,
              'capture_sha256':digest(json.dumps(capture,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),
              'observations':checked,'shield_pickup':shield_proof,'edges':[{'id':a['id'],'before':a['before'],'after':a['after'],'messages':message_evidence[i]} for i,a in enumerate(actions)],
              'scope':'Supplied observations and hash-bound source/artifacts are not authenticated execution, complete gameplay, autonomous timing, or durable saves.'}
    return scene,evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','capture','artifacts','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();source,root,output=args.source.resolve(),args.artifacts.resolve(),args.output.resolve()
    checkout=Path(__file__).resolve().parents[2]
    require(not output.exists() and not args.output.is_symlink() and output != checkout and checkout not in output.parents and
            all(output != p and p not in output.parents and output not in p.parents for p in (source,root)), 'output must be a fresh private directory')
    def load(path):
        target=(root/path).resolve();require(root in target.parents and target.is_file(),'artifact path outside private directory');return target.read_bytes()
    scene,evidence=build(source,json.loads(args.capture.read_bytes()),load)
    raw=(json.dumps(scene,ensure_ascii=False,indent=2)+'\n').encode();evidence['scene_sha256']=digest(raw)
    output.mkdir(parents=True,exist_ok=False)
    (output/'scene.json').write_bytes(raw);(output/'provenance.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'scene':str(output/'scene.json'),'provenance':str(output/'provenance.json')}))


if __name__=='__main__':main()
