"""Build a private partial mushroom route from supplied native observations.

Checks bind source and artifacts; they do not authenticate supplied assertions.
No original messages or frames are embedded in the authored scene.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from fdisbull.agi import load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture, extract_v2_resource
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend
from examples.agi.build_clip_scene import artifact, frame_evidence, json_artifact, require

OBJECT_SHA = '2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985'
IDS = ('cross-to-island', 'reach-mushroom', 'take-mushroom')
BYTE_FIELDS = ('room', 'score', 'x', 'y', 'direction', 'ego_width', 'ego_view', 'step_size', 'swimming')
BOOL_FIELDS = ('drawn', 'in_water', 'dead', 'bridge_active', 'troll_removed', 'troll_paid',
               'mushroom_carried', 'mushroom_taken', 'mushroom_scored')
FIELDS = BYTE_FIELDS + BOOL_FIELDS


def digest(data):
    return sha256(data).hexdigest()


def project_state(value):
    require(isinstance(value, dict) and isinstance(value.get('ego'), dict), 'missing observed state')
    ego = value['ego']
    state = {key: ego.get(key) if key in ('x', 'y', 'direction', 'drawn') else value.get(key) for key in FIELDS}
    require(all(type(state[k]) is int and 0 <= state[k] <= 255 for k in BYTE_FIELDS) and
            all(type(state[k]) is bool for k in BOOL_FIELDS), 'invalid observed state')
    require(state['x'] < 160 and state['y'] < 168 and state['direction'] == 0 and state['drawn'] and
            state['ego_width'] == 6 and state['ego_view'] == 0 and state['step_size'] == 1 and
            state['swimming'] == 0 and not any(state[k] for k in
                ('in_water', 'dead', 'bridge_active', 'troll_removed', 'troll_paid')), 'unqualified walking state')
    return state


def pickup_evidence(ref, loader, resource, object_sha):
    proof = json_artifact(ref, loader, 'pickup')
    require(proof.get('format') == 'fdisbull-agi-mushroom-pickup-1' and proof.get('status') == 'verified' and
            proof.get('complete') is True and proof.get('native_execution') is True and
            proof.get('cleanup_errors', []) == [] and
            type(proof.get('source_logic')) is int and proof['source_logic'] == 47 and
            proof.get('source_logic_sha256') == resource.resource_sha256 and
            type(proof.get('score_source_offset')) is int and proof['score_source_offset'] == 0x195 and
            type(proof.get('item_source_offset')) is int and proof['item_source_offset'] == 0x198, 'pickup source not qualified')
    def exact(mapping, expected):
        return isinstance(mapping, dict) and all(type(mapping.get(k)) is type(v) and mapping[k] == v for k,v in expected.items())
    require(exact(proof.get('before'), {'score': 0, 'item_location': 0}) and
            exact(proof.get('after'), {'score': 1, 'item_location': 255}), 'pickup state mismatch')
    require(exact(proof.get('score_writer'), {'cause_offset': 0x72da, 'resume_offset': 0x72de, 'bx': 3, 'al': 1}) and
            exact(proof.get('item_writer'), {'cause_offset': 0x7482, 'resume_offset': 0x7486}) and
            exact(proof.get('handler_return'), {'offset': 0x2fa, 'observed': True,
                                               'source_cursor_offset': 0x19a, 'stack_verified': True}), 'pickup native boundary mismatch')
    binding = proof.get('inventory_binding'); writer = proof['item_writer']
    require(exact(binding, {'source_sha256': object_sha, 'item': 24, 'stride': 3,
                            'name_offset': 0x133, 'carried_value': 255}) and
            type(binding.get('base')) is int and type(binding.get('end')) is int and
            0 < binding['base'] < binding['end'] <= 65536 and binding['end'] - binding['base'] == 81 and
            type(writer.get('di_offset')) is int and writer['di_offset'] == binding['base'] + 72 and
            type(binding.get('location_linear')) is int and binding['base'] + 74 <= binding['location_linear'] <= 0xfffff and
            (binding['location_linear'] - binding['base'] - 74) % 16 == 0,
            'inventory record binding mismatch')
    trace = proof.get('trace')
    require(isinstance(trace, dict) and type(trace.get('event_count')) is int and 1 <= trace['event_count'] < 128 and
            type(trace.get('maximum_count')) is int and trace['maximum_count'] == 128, 'invalid trace bounds')
    raw = json_artifact(trace, loader, 'pickup trace')
    require(raw.get('format') == 'fdisbull-agi-mushroom-trace-1' and raw.get('complete') is True and
            type(raw.get('maximum_count')) is int and raw['maximum_count'] == 128 and
            isinstance(raw.get('events'), list) and len(raw['events']) == trace['event_count'] and
            all(isinstance(item, dict) for item in raw['events']) and
            isinstance(raw.get('runs'), list) and bool(raw['runs']) and all(isinstance(item, dict) for item in raw['runs']),
            'pickup trace incomplete')
    return {'sha256': ref['sha256'], 'source_logic': 47, 'source_logic_sha256': resource.resource_sha256,
            'score_source_offset': 0x195, 'item_source_offset': 0x198, 'item': 24,
            'handler_return': deepcopy(proof['handler_return']),
            'trace': {key: trace[key] for key in ('sha256', 'event_count', 'maximum_count')}}


def build(source, capture, artifact_loader):
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-mushroom-capture-1', 'invalid capture')
    rt = capture.get('runtime')
    require(isinstance(rt, dict) and rt.get('policy') == 'physical' and rt.get('fresh_game') is True and rt.get('interventions') == [], 'unqualified physical runtime')
    identity = capture.get('source')
    require(isinstance(identity, dict) and digest((source / 'AGI').read_bytes()) == identity.get('agi_sha256'), 'AGI identity mismatch')
    object_sha = digest((source / 'OBJECT').read_bytes())
    require(object_sha == OBJECT_SHA, 'OBJECT identity mismatch')
    expected = identity.get('resources')
    require(isinstance(expected, dict) and '47' in expected and len(expected) <= 256, 'missing logic 47')
    resources = {}
    for key, value in expected.items():
        require(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', key) is not None and int(key) <= 255, 'invalid logic ID')
        item = load_logic(source / 'LOGDIR', source, int(key), profile='2.917')
        require(item.resource_sha256 == value, 'logic identity mismatch')
        resources[int(key)] = item
    logic = resources[47]; layout = logic_layout(logic.payload)
    require(layout['conditions'].get(0x165) == {'opcode': 14, 'end': 0x16b, 'negated': False} and
            layout['conditions'].get(0x186) == {'opcode': 11, 'end': 0x18c, 'negated': False} and
            all(offset + 2 in layout['instructions'] for offset in (0x162, 0x183, 0x18f, 0x195, 0x198)) and
            logic.code[0x162:0x169] == bytes.fromhex('ff0e0205006100') and
            logic.code[0x183:0x189] == bytes.fromhex('ff0b004a465e') and logic.code[0x189] == 90 and
            logic.code[0x18f:0x191] == bytes((101, 9)) and logic.code[0x195:0x19a] == bytes.fromhex('0503015c18'), 'pickup source instructions differ')
    pictures = capture.get('pictures'); require(isinstance(pictures, dict), 'missing pictures')
    picture_evidence = {}
    for room in (33, 47, 48):
        picture = extract_v2_resource(source / 'PICDIR', source, room)
        pic_hash = digest(picture['payload'])
        require(pic_hash == picture['sha256'] == pictures.get(str(room)), 'picture identity mismatch')
        decode_picture(picture['payload']);picture_evidence[str(room)] = pic_hash
    observations, actions = capture.get('observations'), capture.get('actions')
    require(isinstance(observations, dict) and isinstance(actions, list) and len(actions) == 3 and
            all(isinstance(a, dict) and a.get('id') == ident for a, ident in zip(actions, IDS)) and
            all(actions[i]['before'] == actions[i-1]['after'] for i in (1, 2)), 'expected contiguous route')
    used = {}
    def observation(ident):
        require(isinstance(ident, str) and ident in observations, 'missing route observation')
        if ident not in used:
            item = observations[ident]; require(isinstance(item, dict), 'invalid observation')
            used[ident] = {'state': project_state(item.get('state')), 'frame': frame_evidence(item.get('frame'), artifact_loader)}
        return used[ident]['state']
    states = [observation(actions[0].get('before'))] + [observation(a.get('after')) for a in actions]
    mid_id = capture.get('crossing_observation');require(mid_id == 'mushroom-midwater', 'missing crossing observation')
    middle = observation(mid_id)
    points = [(s['room'], s['x'], s['y']) for s in states]
    require(points[0] == (33,154,87) and points[1] == (48,129,140) and
            points[2] == (47,94,90) and points[3] == (47,94,90) and
            (middle['room'], middle['x'], middle['y']) == (33,154,55), 'route waypoint differs')
    for i, state in enumerate(states):
        require(state['score'] == (1 if i == 3 else 0) and all(state[k] == (i == 3) for k in
            ('mushroom_carried','mushroom_taken','mushroom_scored')), 'pickup state differs')
    require(middle['score'] == 0 and not any(middle[k] for k in ('mushroom_carried','mushroom_taken','mushroom_scored')), 'midwater state differs')
    ids = [actions[0]['before']] + [a['after'] for a in actions]
    frame_ids = [used[x]['frame']['metadata']['frame_id'] for x in ids]
    mid_frame = used[mid_id]['frame']['metadata']['frame_id']
    require(all(b > a for a,b in zip(frame_ids, frame_ids[1:])) and frame_ids[0] < mid_frame < frame_ids[1], 'frames out of order')
    msg_evidence = None
    for i, action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True, 'incomplete action')
        inputs = action.get('inputs');require(isinstance(inputs, list) and bool(inputs) and all(isinstance(x, dict) and
            x.get('kind') == 'keyboard' and isinstance(x.get('key'), str) and bool(x['key']) and x.get('delivered') is True and
            x.get('complete') is True and isinstance(x.get('delivery'), dict) and x['delivery'].get('accepted') is True for x in inputs), 'unqualified keyboard input')
        messages = action.get('messages');require(isinstance(messages, list) and len(messages) == (1 if i == 2 else 0), 'unexpected message count')
        if i == 2:
            msg = messages[0]
            require(isinstance(msg, dict) and msg.get('status') == 'completed' and msg.get('mode') == 'blocking' and
                    all(msg.get(k) is True for k in ('native_execution','native_execution_attempted','input_attempted','handler_return_observed','input_settled','window_closed')) and
                    msg.get('cleanup_errors', []) == [] and all(type(msg.get(k)) is int and msg[k] == v for k,v in
                    (('logic',47),('source_offset',0x18f),('message_id',9))), 'message not qualified')
            text = logic_messages(logic)[logic.resource_sha256].get('9');require(isinstance(text,str) and bool(text), 'missing source message')
            encoded = text.encode('cp437'); native_identity = msg.get('identity'); native_message = msg.get('message')
            require(isinstance(native_identity,dict) and native_identity.get('resource_sha256') == logic.resource_sha256 and
                    isinstance(native_message,dict) and native_message.get('resource_sha256') == logic.resource_sha256 and
                    type(native_message.get('message_id')) is int and native_message['message_id'] == 9 and
                    native_message.get('text_sha256') == digest(encoded) and type(native_message.get('length')) is int and native_message['length'] == len(encoded), 'message source binding mismatch')
            key = msg.get('input');keyboard = msg.get('keyboard_after')
            require(isinstance(key,dict) and key.get('accepted') is True and isinstance(keyboard,dict) and
                    isinstance(keyboard.get('keyboard'),dict) and all(type(keyboard['keyboard'].get(k)) is int and keyboard['keyboard'][k] == 0 for k in ('pending_events','owned_keys','queued_guest_ms')), 'message input unsettled')
            fm = frame_evidence(msg.get('frame'),artifact_loader);require(frame_ids[2] < fm['metadata']['frame_id'] < frame_ids[3], 'message frame out of order')
            msg_evidence = {'logic':47,'source_offset':0x18f,'message_id':9,'resource_sha256':logic.resource_sha256,
                            'text_sha256':digest(encoded),'frame':fm}
    proof = pickup_evidence(actions[2].get('native_pickup'), artifact_loader, logic, object_sha)
    variables = {'$phase': {'type':'u8','initial':0}, **{'$'+k: {'type':'bool' if k in BOOL_FIELDS else 'u8','initial':states[0][k]} for k in FIELDS}}
    texts = ('The recorded crossing reaches the island.', 'The recorded trail reaches the mushroom.', 'The recorded pickup adds the mushroom and one point.')
    programs = {}
    for i, name in enumerate(IDS):
        before, after = states[i:i+2]
        body = [{'id':'guard-phase','op':'require','condition':{'op':'eq','left':{'var':'$phase'},'right':i}}]
        body += [{'id':'guard-'+k,'op':'require','condition':{'op':'eq','left':{'var':'$'+k},'right':before[k]}} for k in FIELDS]
        body += [{'id':'set-'+k,'op':'set','var':'$'+k,'value':after[k]} for k in FIELDS if before[k] != after[k]]
        body += [{'id':'set-phase','op':'set','var':'$phase','value':i+1},{'id':'message','op':'text','resource':'message'}]
        programs[name] = {'format':'fdisbull-il-1','role':'uil','variables':variables,'resources':{'message':{'kind':'text','text':texts[i]}},'body':body}
    targets = ('crossing','trail','mushroom')
    objects = [{'id':name,'context':'phase-'+str(i),'label':name,'aliases':[], 'description':'The next recorded action.',
                'bindings':[{'verb':'take' if i == 2 else 'use','program':IDS[i]}],
                **({'inventory_when':{'op':'eq','left':{'var':'$mushroom_carried'},'right':True}} if i == 2 else {})} for i,name in enumerate(targets)]
    scene = {'format':'fdisbull-il-scene-1','programs':programs,'partial':True,'objects':objects,
             'contexts':[{'id':'phase-'+str(i),'title':'Observed mushroom route','description':'A partial reconstruction of supplied route observations.',
                          'when':{'op':'eq','left':{'var':'$phase'},'right':i}} for i in range(4)]}
    ILSceneBackend(scene)
    provenance = {'format':'fdisbull-agi-mushroom-z-evidence-1','source':deepcopy(identity),'object_sha256':object_sha,
                  'capture_sha256':digest(json.dumps(capture,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),
                  'pictures':picture_evidence,'observations':used,'message':msg_evidence,'native_pickup':proof,
                  'scope':'Supplied observations and hash-bound artifacts; not authenticated execution, general gameplay, full-engine proof, or durable saves.'}
    return scene, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source','capture','artifacts','output'):parser.add_argument('--'+name,required=True,type=Path)
    args = parser.parse_args();source,root,output = args.source.resolve(),args.artifacts.resolve(),args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not output.exists() and not args.output.is_symlink() and output != checkout and checkout not in output.parents and
            all(output != p and p not in output.parents and output not in p.parents for p in (source,root)), 'output must be a fresh private directory')
    def load(path):
        target = (root / path).resolve();require(root in target.parents and target.is_file(), 'artifact path outside private directory')
        return target.read_bytes()
    scene,evidence = build(source,json.loads(args.capture.read_bytes()),load)
    raw=(json.dumps(scene,ensure_ascii=False,indent=2)+'\n').encode();evidence['scene_sha256']=digest(raw)
    output.mkdir(parents=True,exist_ok=False)
    (output/'scene.json').write_bytes(raw);(output/'provenance.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'scene':str(output/'scene.json'),'provenance':str(output/'provenance.json')}))


if __name__ == '__main__':main()
