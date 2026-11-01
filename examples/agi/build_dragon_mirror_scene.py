"""Validate supplied KQ1 well/dragon observations and build a partial Z scene.

Hashes and structural checks establish supplied-record consistency, not
authentic execution. Original messages, frames and generated scenes stay private.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from examples.agi.build_clip_scene import frame_evidence, json_artifact, require
from examples.agi.build_gnome_giant_scene import clock, exact, message_evidence
from fdisbull.agi import load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture, extract_v2_resource
from fdisbull.il_scenes import ILSceneBackend

OBJECT_SHA = '2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985'
ACTION_IDS = ('obtain-dagger', 'detach-bucket', 'descend-well', 'dive-to-cave',
              'enter-dragon', 'douse-dragon', 'take-mirror', 'leave-cave')
OBSERVATION_IDS = ('fresh', 'dagger-carried', 'bucket-carried', 'well-ready',
                   'water-ready', 'dragon-before', 'dragon-retreated',
                   'mirror-taken', 'surface-return')
ROUTE_CONTRACT = {
    'status': 'qualified-fresh-segment',
    'anchors': ((1, 110, 100), (3, 120, 114), (12, 65, 120),
                (49, 81, 51), (52, 75, 26), (51, 131, 136),
                (51, 146, 131), (51, 45, 115), (22, 140, 83)),
    'scores': (0, 7, 9, 10, 14, 15, 20, 28, 28),
    'qualification_witness': {
        'name': 'Native07',
        'capture_sha256': '2af06b3630806fa1c967740444eaf2f4a69b79ef870506815caae6417051b35f',
        'result_sha256': '9643db84d1b51a01408fa587910c215b18da8e9d2b050bad50f0547d740c9eda',
        'producer': 'examples/agi/verify_dragon_mirror.py',
        'producer_sha256': '797ea3da5092db98f7af3b0eaeec4b537c1c383ccc397fa52f2b34b3dc6b1368',
        'fresh_game': True,
        'interventions': [],
        'actions': 8,
        'main_observations': 9,
        'repeat_controls': 2,
        'water_trace_events': 6,
        'mirror_trace_events': 6,
    },
    'scope': 'One bounded fresh physical eight-action session through surface return. Coordinates identify this completed witness; no arbitrary timing/RNG reliability, full-game or original-interpreter equivalence claim.',
}
ITEMS = {'dagger': 1, 'bucket': 11, 'mirror': 19, 'water': 26}
VARIABLES = {'air_low': '68', 'air_high': '69', 'treasures': '74',
             'dragon_state': '75', 'swim_state': '94'}
FLAGS = {'callback_21': '21', 'callback_22': '22', 'callback_23': '23',
         'dagger_flag': '67', 'bucket_flag': '81', 'water_flag': '88',
         'water_scored': '91', 'mirror_taken': '100', 'well_scored': '162',
         'dive_scored': '164', 'mirror_removed': '165', 'cave_scored': '167',
         'bucket_detached': '176', 'lowered_callback': '177',
         'rope_destroyed': '178', 'rope_lowered': '179'}
BYTE_FIELDS = ('room', 'score', 'x', 'y', 'direction', 'ego_width', 'ego_view',
               'step_size', 'swimming', 'player_control') + tuple(VARIABLES)
BYTE_FIELDS += tuple('inventory_'+str(item) for item in ITEMS.values())
BOOL_FIELDS = ('drawn', 'in_water', 'dead', 'ignore_blocks', 'actor_3_drawn')
BOOL_FIELDS += tuple(FLAGS) + tuple(name+'_carried' for name in ITEMS)
FIELDS = BYTE_FIELDS + BOOL_FIELDS
REQUIRED_MESSAGES = {
    0: ((3, 0x102, 13), (3, 0x1b8, 8)),
    1: ((12, 0x6d8, 3),), 2: ((12, 0x774, 25),),
    5: ((51, 0x45e, 34),), 6: ((51, 0x381, 24),),
}


def digest(raw):
    return sha256(raw).hexdigest()


def project_state(raw):
    require(isinstance(raw, dict) and isinstance(raw.get('ego'), dict), 'missing state')
    require(exact(raw, {'control_direction': 0, 'window': 0, 'initializing': False}),
            'boundary input, modal or initialization not settled')
    state = {key: raw['ego'].get(key) if key in ('x', 'y', 'direction', 'drawn') else raw.get(key)
             for key in BYTE_FIELDS[:10]+('drawn', 'in_water', 'dead', 'ignore_blocks')}
    variables, flags = raw.get('quest_variables'), raw.get('quest_flags')
    require(isinstance(variables, dict) and isinstance(flags, dict), 'missing quest state')
    state.update({key: variables.get(number) for key, number in VARIABLES.items()})
    state.update({key: flags.get(number) for key, number in FLAGS.items()})
    actor = raw.get('dragon_actor')
    require(isinstance(actor, dict), 'missing actor 3 observation')
    state['actor_3_drawn'] = actor.get('drawn')
    locations = raw.get('inventory_locations')
    require(isinstance(locations, dict) and set(locations) == {str(n) for n in ITEMS.values()},
            'inventory location set differs')
    for name, item in ITEMS.items():
        state['inventory_'+str(item)] = locations[str(item)]
        state[name+'_carried'] = raw.get(name+'_carried')
    require(all(type(state[key]) is int and 0 <= state[key] <= 255 for key in BYTE_FIELDS)
            and all(type(state[key]) is bool for key in BOOL_FIELDS), 'invalid typed state')
    require(state['x'] < 160 and state['y'] < 168 and state['ego_width'] > 0
            and state['direction'] == 0 and state['drawn'] and not state['dead']
            and state['player_control'] == 1 and state['step_size'] == 1,
            'unsettled or unsafe boundary')
    require(state['swimming'] == state['swim_state'], 'swimming state disagrees')
    require(type(raw.get('ego_height')) is int
            and raw['ego_height'] == {0: 32, 74: 33, 73: 20}.get(state['ego_view']),
            'source VIEW height differs')
    for name, item in ITEMS.items():
        require(state[name+'_carried'] == (state['inventory_'+str(item)] == 255),
                'inventory byte and carried state differ')
    return state


def route_states(states):
    require(len(states) == 9, 'expected nine route states')
    for i, (state, anchor, score) in enumerate(zip(states, ROUTE_CONTRACT['anchors'], ROUTE_CONTRACT['scores'])):
        room, x, y = anchor
        require(state['room'] == room and (x is None or state['x'] == x)
                and (y is None or state['y'] == y) and state['score'] == score,
                'route anchor or score differs')
        if i == 3:
            require(state['ego_view'] == 74 and state['ego_width'] == 8
                    and state['swimming'] == 0 and not state['in_water'], 'unqualified rope boundary')
        elif i == 4:
            require(state['ego_view'] == 73 and state['ego_width'] in (11, 19)
                    and state['swimming'] in (1, 2)
                    and state['air_high'] > 0, 'unqualified underwater boundary')
        else:
            require(state['ego_view'] == 0 and state['ego_width'] == 6
                    and state['swimming'] == 0 and not state['in_water'], 'unqualified dry boundary')
        require(state['dagger_carried'] == (i >= 1) and state['dagger_flag'] == (i >= 1)
                and state['bucket_carried'] == (i >= 2) and state['bucket_flag'] == (i >= 2)
                and state['bucket_detached'] == (i >= 2)
                and state['water_carried'] == (i in (4, 5)) and state['water_flag'] == (i in (4, 5))
                and state['water_scored'] == (i in (4, 5)) and state['mirror_carried'] == (i >= 7)
                and state['mirror_taken'] == (i >= 7) and state['mirror_removed'] == (i >= 7)
                and state['well_scored'] == (i >= 3) and state['dive_scored'] == (i >= 4)
                and state['cave_scored'] == (i >= 5) and state['dragon_state'] == (0 if i < 6 else 2)
                and state['treasures'] == (0 if i < 7 else 1) and not state['rope_destroyed'],
                'route inventory, flags or quest state differs')
        require(all(state['inventory_'+str(item)] == (255 if state[name+'_carried'] else 0)
                    for name, item in ITEMS.items()), 'unexpected inventory location')
        if i in (6, 7):
            require(not state['actor_3_drawn'] and not any(state['callback_'+str(n)] for n in (21, 22, 23)),
                    'dragon retreat not complete')


def observation(value, loader, geometry=None):
    require(isinstance(value, dict), 'missing observation')
    frame = frame_evidence(value.get('frame'), loader)
    shape = tuple(frame['metadata'][key] for key in ('mode_id', 'width', 'height'))
    require(geometry is None or shape == geometry, 'frame geometry changed')
    frame['metadata'] = {key: frame['metadata'][key] for key in
                         ('frame_id', 'mode_id', 'width', 'height', 'source')}
    return {'state': project_state(value.get('state')), 'frame': frame,
            'guest_ms': clock(value.get('guest_ms'))}


def between(record, before, after):
    require(before['frame']['metadata']['frame_id'] < record['frame']['metadata']['frame_id']
            < after['frame']['metadata']['frame_id']
            and before['guest_ms'] < record['guest_ms'] < after['guest_ms'],
            'extra observation outside action bounds')


def object_records(raw):
    require(digest(raw) == OBJECT_SHA, 'OBJECT identity differs')
    decoded = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(raw))
    require(len(decoded) >= 84 and int.from_bytes(decoded[:2], 'little') == 81,
            'expected 27 inventory records')
    result = {}
    for item in ITEMS.values():
        rec = item*3
        name = int.from_bytes(decoded[3+rec:5+rec], 'little')
        end = decoded.find(b'\0', 3+name)
        require(81 <= name and 3+name < end < len(decoded) and end-3-name <= 64,
                'inventory name bounds differ')
        result[item] = {'record_offset': rec, 'location_offset': rec+2, 'name_offset': name,
                        'name_sha256': digest(decoded[3+name:end+1]), 'name_length': end-3-name+1}
    return result


def source_check(resources):
    operations = {3: ((0x104, (5, 3, 2)), (0x1ba, (92, 1)), (0x1bc, (5, 3, 5))),
                  12: ((0x6d6, (92, 11)), (0x6da, (5, 3, 2))),
                  22: ((0x6, (3, 68, 0)), (0x9, (3, 69, 0)), (0xdd, (37, 0, 142, 83))),
                  49: ((0x4d, (5, 3, 1)), (0x507, (5, 3, 2)), (0x50a, (18, 52))),
                  52: ((0x4d, (92, 26)), (0x58, (5, 3, 2))),
                  51: ((0x4d, (5, 3, 1)), (0x460, (94, 26)), (0x462, (7, 3, 2)),
                       (0x465, (5, 3, 7)), (0x473, (3, 75, 2)),
                       (0x37f, (92, 19)), (0x385, (5, 3, 8)))}
    for logic, checks in operations.items():
        resource = resources[logic]
        starts = set(logic_layout(resource.payload)['instructions'])
        for offset, values in checks:
            require(offset+2 in starts and resource.code[offset:offset+len(values)] == bytes(values),
                    'source operation differs')
    for offset, values in ((0x432, (255, 253, 11, 0, 105, 96, 145, 166, 1, 75, 0, 255)),
                           (0x32d, (255, 11, 0, 26, 104, 59, 127, 255))):
        require(offset+2 in logic_layout(resources[51].payload)['instructions']
                and resources[51].code[offset:offset+len(values)] == bytes(values),
                'source position parent differs')


def underwater_baseline(source, capture, state):
    """Bind physical flag 0 to the settled PIC baseline, not the story location.

    L52 sets flag 0 during initialization. The observed settled baseline is
    priority 4, so that transient assignment is not an enduring water predicate.
    Room, VIEW, v94 and air identify the underwater route separately.
    """
    pictures = capture.get('pictures')
    require(isinstance(pictures, dict) and isinstance(pictures.get('52'), str),
            'missing underwater picture identity')
    picture = extract_v2_resource(source/'PICDIR', source, 52)
    require(picture['sha256'] == pictures['52'], 'underwater picture identity differs')
    plane = decode_picture(picture['payload'])['priority']
    x, y, width = state['x'], state['y'], state['ego_width']
    require(x+width <= 160, 'underwater baseline outside picture')
    baseline = plane[y*160+x:y*160+x+width]
    require(len(baseline) == width and not any(value in (0, 1, 2) for value in baseline)
            and state['in_water'] == all(value == 3 for value in baseline),
            'underwater physical water flag or baseline differs')
    return {'room': 52, 'picture_sha256': picture['sha256'], 'origin': [x, y],
            'width': width, 'priority_values': sorted(set(baseline)), 'in_water': state['in_water'],
            'scope': 'Source PIC baseline and supplied settled physical flag 0; underwater story state uses room/VIEW/v94/air.'}


def inventory_binding(binding, item, records, native):
    record = records[item]
    require(exact(binding, {'source_sha256': OBJECT_SHA, 'stride': 3, 'item': item,
                           'record_offset': record['record_offset'], 'location_offset': record['location_offset'],
                           'name_offset': record['name_offset'], 'name_sha256': record['name_sha256'],
                           'carried_value': 255}), 'named inventory binding differs')
    base, end, location = (binding.get(key) for key in ('base', 'end', 'location_linear'))
    require(all(type(value) is int for value in (base, end, location)) and 0 < base < end <= 65536
            and end-base == 81 and base+record['name_offset']+record['name_length'] <= 65536
            and location == native['ds']*16+base+record['location_offset'], 'live inventory address differs')
    return base


def bounded_trace(reference, loader, name):
    require(isinstance(reference, dict) and type(reference.get('event_count')) is int
            and 0 < reference['event_count'] < 128
            and type(reference.get('maximum_count')) is int and reference['maximum_count'] == 128,
            'trace bounds differ')
    trace = json_artifact(reference, loader, name+' trace')
    require(exact(trace, {'format': 'fdisbull-agi-quest-trace-1', 'name': name,
                          'complete': True, 'maximum_count': 128})
            and isinstance(trace.get('events'), list) and len(trace['events']) == reference['event_count']
            and all(isinstance(event, dict) for event in trace['events'])
            and isinstance(trace.get('runs'), list) and bool(trace['runs'])
            and all(isinstance(run, dict) for run in trace['runs']) and not trace.get('next_cursor'),
            'trace incomplete or contradictory')
    return {key: reference[key] for key in ('sha256', 'event_count', 'maximum_count')}


def native_transaction(reference, loader, kind, resource, records, before, after, native):
    proof = json_artifact(reference, loader, kind+' transaction')
    mirror = kind == 'mirror'
    item, item_offset = (19, 0x37f) if mirror else (26, 0x460)
    require(exact(proof, {'format': 'fdisbull-agi-quest-pickup-1' if mirror else 'fdisbull-agi-dragon-water-1',
                         'status': 'verified', 'complete': True, 'native_execution': True,
                         'source_logic': 51, 'source_logic_sha256': resource.resource_sha256,
                         'item': item, 'item_source_offset': item_offset})
            and exact(proof.get('identity'), native) and proof.get('cleanup_errors', []) == [],
            'transaction source, identity or completion differs')
    require('instruction_completed' in proof and proof['instruction_completed'] is None
            and proof.get('writer_stop_stage') == 'after data access; instruction completion unknown',
            'writer completion claim differs')
    expected_before = {'score': before['score'], 'item_location': before['inventory_'+str(item)]}
    expected_after = {'score': after['score'], 'item_location': after['inventory_'+str(item)]}
    require(exact(proof.get('before'), expected_before) and exact(proof.get('after'), expected_after)
            and exact(proof.get('known_effects'), expected_after), 'transaction known effects differ')
    base = inventory_binding(proof.get('inventory_binding'), item, records, native)
    require(exact(proof.get('handler_return'), {'offset': 0x2fa, 'observed': True,
                         'source_cursor_offset': item_offset+2, 'stack_verified': True}),
            'original handler return differs')
    if mirror:
        require(exact(proof, {'name': 'mirror', 'score_source_offset': 0x385, 'score_delta': 8})
                and proof.get('order') == ['item', 'return', 'score']
                and expected_before == {'score': 20, 'item_location': 0}
                and expected_after == {'score': 28, 'item_location': 255}
                and exact(proof.get('item_writer'), {'cause_offset': 0x7482, 'resume_offset': 0x7486,
                                                    'di_offset': base+3*item})
                and exact(proof.get('score_writer'), {'cause_offset': 0x72da, 'resume_offset': 0x72de,
                                                     'bx': 3, 'al': 8}), 'mirror writer or order differs')
        early = proof.get('pre_print_trace')
    else:
        require(exact(proof, {'print_source_offset': 0x45e, 'subtract_source_offset': 0x462,
                              'add_source_offset': 0x465})
                and proof.get('order') == ['drop', 'return', 'subtract', 'add']
                and expected_before == {'score': 15, 'item_location': 255}
                and expected_after == {'score': 20, 'item_location': 0}
                and exact(proof.get('drop_writer'), {'cause_offset': 0x74ba, 'resume_offset': 0x74be,
                                                    'di_offset': base+3*item})
                and exact(proof.get('subtract_writer'), {'cause_offset': 0x72fa, 'resume_offset': 0x72fe,
                                                        'bx': 3, 'al': 2})
                and exact(proof.get('add_writer'), {'cause_offset': 0x72da, 'resume_offset': 0x72de,
                                                   'bx': 3, 'al': 7}), 'water writer or order differs')
        early = proof.get('drop_trace')
    require(isinstance(early, dict) and early == proof.get('trace'), 'bounded transaction trace differs')
    trace = bounded_trace(proof['trace'], loader, kind if mirror else 'dragon-water')
    return {'sha256': reference['sha256'], 'source_logic': 51,
            'source_logic_sha256': resource.resource_sha256, 'item': item,
            'item_source_offset': item_offset, 'order': list(proof['order']),
            'before': expected_before, 'after': expected_after,
            'inventory_binding': {key: proof['inventory_binding'][key] for key in
                                   ('base', 'end', 'stride', 'item', 'name_sha256')},
            'handler_return': deepcopy(proof['handler_return']), 'trace': trace,
            'writer_stop_scope': 'Observed data effects; the individual writer instruction completion is unknown.'}


def accepted_inputs(inputs):
    require(isinstance(inputs, list) and bool(inputs) and all(
        isinstance(item, dict) and item.get('kind') == 'keyboard'
        and isinstance(item.get('key'), str) and bool(item['key'])
        and item.get('delivered') is True and item.get('complete') is True
        and isinstance(item.get('delivery'), dict) and item['delivery'].get('accepted') is True
        for item in inputs), 'unqualified physical input')


def build(source, capture, artifact_loader):
    """Read original resources and supplied receipts; never operate a guest."""
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-dragon-mirror-capture-1',
            'invalid dragon capture')
    runtime = capture.get('runtime')
    require(isinstance(runtime, dict) and runtime.get('policy') == 'physical'
            and runtime.get('fresh_game') is True and runtime.get('interventions') == []
            and capture.get('native_origin') is None
            and isinstance(runtime.get('session_id'), str) and bool(runtime['session_id']),
            'unqualified fresh origin; restored origin requires a separate qualified contract')
    identity = capture.get('source')
    require(isinstance(identity, dict) and identity.get('agi_sha256') == digest((source/'AGI').read_bytes())
            and identity.get('object_sha256') == OBJECT_SHA, 'source identity differs')
    records = object_records((source/'OBJECT').read_bytes())
    expected = identity.get('resources')
    require(isinstance(expected, dict) and 10 <= len(expected) <= 256
            and all(str(n) in expected for n in (0, 1, 3, 12, 22, 49, 50, 51, 52, 101)),
            'missing source logic identities')
    resources = {}
    for key, value in expected.items():
        require(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', key) and int(key) <= 255
                and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
                'invalid source logic identity')
        resource = load_logic(source/'LOGDIR', source, int(key), profile='2.917')
        require(resource.resource_sha256 == value, 'source logic hash differs')
        resources[int(key)] = resource
    source_check(resources)
    observations, actions = capture.get('observations'), capture.get('actions')
    require(isinstance(observations, dict) and set(observations) == set(OBSERVATION_IDS)
            and isinstance(actions, list) and len(actions) == 8 and all(
                isinstance(action, dict) and action.get('id') == name
                and action.get('before') == OBSERVATION_IDS[i]
                and action.get('after') == OBSERVATION_IDS[i+1]
                for i, (action, name) in enumerate(zip(actions, ACTION_IDS))),
            'expected eight ordered actions and nine contiguous observations')
    ordered, geometry = [], None
    for ident in OBSERVATION_IDS:
        value = observation(observations[ident], artifact_loader, geometry)
        if geometry is None:
            geometry = tuple(value['frame']['metadata'][key] for key in ('mode_id', 'width', 'height'))
        ordered.append(value)
    require(all(a['guest_ms'] < b['guest_ms'] and a['frame']['metadata']['frame_id']
                < b['frame']['metadata']['frame_id'] for a, b in zip(ordered, ordered[1:])),
            'main frame or guest-time order differs')
    states = [value['state'] for value in ordered]
    route_states(states)
    water_baseline = underwater_baseline(source, capture, states[4])
    messages = []
    for i, action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True,
                'incomplete action')
        accepted_inputs(action.get('inputs'))
        if i in (5, 6):
            command = 'throw water' if i == 5 else 'get mirror'
            keys = [item['key'].strip().lower() for item in action['inputs']]
            require([key for key in keys if key.startswith('type:')] == ['type:'+command]
                    and keys.count('press:enter') == 1 and keys[-1] == 'press:enter',
                    'expected one original transaction command')
        raw_messages = action.get('messages')
        require(isinstance(raw_messages, list), 'missing action messages')
        checked = [message_evidence(message, artifact_loader, resources, ordered[i], ordered[i+1],
                                    geometry, runtime['session_id']) for message in raw_messages]
        require(all(a['guest_ms'] < b['guest_ms'] and a['frame']['metadata']['frame_id']
                    < b['frame']['metadata']['frame_id'] for a, b in zip(checked, checked[1:])),
                'message order differs')
        required = REQUIRED_MESSAGES.get(i, ())
        selected = [(m['logic'], m['source_offset'], m['message_id']) for m in checked
                    if (m['logic'], m['source_offset'], m['message_id']) in required]
        require(selected == list(required), 'required original message sequence differs')
        messages.append(checked)
    native = messages[0][0]['native_binding']
    require(all(m['native_binding'] == native for group in messages for m in group),
            'native session or segment binding differs')
    extras = {}
    for key, index in (('water_before', 5), ('mirror_before', 6)):
        extra = observation(capture.get(key), artifact_loader, geometry)
        between(extra, ordered[index], ordered[index+1])
        baseline = states[index]
        require(all(extra['state'][field] == baseline[field] for field in FIELDS
                    if field not in ('x', 'y', 'air_low', 'air_high')), 'extra launch state differs')
        require(all(extra['state'][field] == states[index+1][field] for field in ('x', 'y')),
                'transaction ego pose changed after launch')
        x, y = extra['state']['x'], extra['state']['y']
        if index == 5:
            require(exact(capture[key]['state'].get('quest_flags'), {'20': False}),
                    'pending dragon follow callback at launch')
        require(not (105 <= x <= 145 and 96 <= y <= 166) if index == 5
                else 26 <= x <= 59 and 104 <= y <= 127, 'source interaction position differs')
        require(all(extra['guest_ms'] < m['guest_ms'] and extra['frame']['metadata']['frame_id']
                    < m['frame']['metadata']['frame_id'] for m in messages[index]),
                'source response precedes launch observation')
        extras[key] = extra
    water = native_transaction(actions[5].get('native_water'), artifact_loader, 'water', resources[51],
                               records, states[5], states[6], native)
    mirror = native_transaction(actions[6].get('native_pickup'), artifact_loader, 'mirror', resources[51],
                                records, states[6], states[7], native)
    require(all(water['inventory_binding'][key] == mirror['inventory_binding'][key]
                for key in ('base', 'end', 'stride')), 'inventory table changed')
    controls = capture.get('repeat_controls')
    require(isinstance(controls, list) and len(controls) == 2, 'expected two separate repeat controls')
    checked_controls, previous = [], ordered[7]
    stable = tuple(field for field in FIELDS if field not in ('air_low', 'air_high'))
    for control, command, response in zip(controls, ('get mirror', 'throw water'),
                                         ((0, 0xf0d, 10), (51, 0x3dd, 7))):
        require(isinstance(control, dict) and control.get('command') == command, 'control command differs')
        before = observation(control.get('before_observation'), artifact_loader, geometry)
        after = observation(control.get('after_observation'), artifact_loader, geometry)
        between(before, previous, ordered[8]); between(after, before, ordered[8])
        require(all(before['state'][field] == after['state'][field] == states[7][field]
                    for field in stable), 'repeat control changed projected outcome')
        accepted_inputs(control.get('inputs'))
        require([item['key'].strip().lower() for item in control['inputs']] == ['type:'+command, 'press:enter'],
                'expected one control command')
        raw = control.get('messages')
        require(isinstance(raw, list), 'missing control messages')
        checked = [message_evidence(m, artifact_loader, resources, before, after, geometry, runtime['session_id'])
                   for m in raw]
        require(len(checked) == 1 and (checked[0]['logic'], checked[0]['source_offset'],
                checked[0]['message_id']) == response and checked[0]['native_binding'] == native,
                'control original response differs')
        checked_controls.append({'command': command, 'before': before, 'after': after, 'messages': checked})
        previous = after
    all_records = ordered+list(extras.values())+[m for group in messages for m in group]
    for control in checked_controls:
        all_records += [control['before'], control['after']]+control['messages']
    ids = [r['frame']['metadata']['frame_id'] for r in all_records]
    require(len(ids) == len(set(ids)), 'duplicate frame identity')
    chronological = sorted(all_records, key=lambda r: r['frame']['metadata']['frame_id'])
    require(all(a['guest_ms'] <= b['guest_ms'] for a, b in zip(chronological, chronological[1:])),
            'frame and guest clocks contradict')
    variables = {'$phase': {'type': 'u8', 'initial': 0}, **{
        '$'+key: {'type': 'bool' if key in BOOL_FIELDS else 'u8', 'initial': states[0][key]} for key in FIELDS}}
    programs, objects = {}, []
    targets = ('dagger', 'bucket', 'rope', 'water', 'passage', 'dragon', 'mirror', 'exit')
    replies = ('The supplied route obtains the dagger.', 'The supplied action detaches the bucket.',
               'The supplied route descends the well.', 'The supplied dive reaches the underwater passage with water.',
               'The supplied route enters the dragon chamber.', 'The supplied water action clears the dragon.',
               'The supplied action takes the mirror.', 'The supplied route returns to the surface.')
    for i, (name, target) in enumerate(zip(ACTION_IDS, targets)):
        before, after = states[i:i+2]
        body = [{'id': 'phase', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}}]
        body += [{'id': 'guard-'+key, 'op': 'require', 'condition':
                  {'op': 'eq', 'left': {'var': '$'+key}, 'right': before[key]}} for key in FIELDS]
        body += [{'id': 'set-'+key, 'op': 'set', 'var': '$'+key, 'value': after[key]}
                 for key in FIELDS if before[key] != after[key]]
        body += [{'id': 'set-phase', 'op': 'set', 'var': '$phase', 'value': i+1},
                 {'id': 'message', 'op': 'text', 'resource': 'message'}]
        programs[name] = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                          'resources': {'message': {'kind': 'text', 'text': replies[i]}}, 'body': body}
        obj = {'id': target, 'context': 'phase-'+str(i), 'label': target, 'aliases': [],
               'description': 'The next authored route action.',
               'bindings': [{'verb': 'take' if target in ('dagger', 'bucket', 'mirror') else 'use', 'program': name}]}
        if target in ITEMS:
            obj['inventory_when'] = {'op': 'eq', 'left': {'var': '$'+target+'_carried'}, 'right': True}
        objects.append(obj)
    scene = {'format': 'fdisbull-il-scene-1', 'partial': True, 'programs': programs, 'objects': objects,
             'contexts': [{'id': 'phase-'+str(i), 'title': 'Partial dragon and mirror route',
                           'description': 'Authored projection; qualification scope is recorded separately.',
                           'when': {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}} for i in range(9)]}
    ILSceneBackend(scene)
    evidence = {'format': 'fdisbull-agi-dragon-mirror-z-evidence-1', 'route_contract': deepcopy(ROUTE_CONTRACT),
                'source': {'agi_sha256': identity['agi_sha256'], 'object_sha256': OBJECT_SHA,
                           'resources': deepcopy(expected)},
                'origin': {'kind': 'fresh-original-boot', 'fresh_game': True, 'interventions': []},
                'capture_sha256': digest(json.dumps(capture, sort_keys=True, separators=(',', ':'),
                                                    ensure_ascii=False, allow_nan=False).encode()),
                'projection_fields': list(FIELDS), 'observations': dict(zip(OBSERVATION_IDS, ordered)),
                'extra_observations': extras, 'native_water': water, 'native_mirror': mirror,
                'underwater_baseline': water_baseline,
                'repeat_controls': checked_controls,
                'edges': [{'id': action['id'], 'before': action['before'], 'after': action['after'],
                           'messages': messages[i]} for i, action in enumerate(actions)],
                'scope': 'Source and supplied-record consistency; dagger/bucket use observed effects and completed source prints, water/mirror also require native writers/returns. No authenticity, full-game, autonomous-timing or durable-save claim.'}
    return scene, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'capture', 'artifacts', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args(argv)
    source, root, output = args.source.resolve(), args.artifacts.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not any(p.is_symlink() for p in (args.output, *args.output.parents))
            and not output.exists() and all(output != p and p not in output.parents
                and output not in p.parents for p in (source, root, checkout)),
            'output must be a fresh private directory without symlinks')
    require(not args.artifacts.is_symlink() and root.is_dir() and not args.capture.is_symlink(),
            'private input symlink or directory differs')

    def load(path):
        require(isinstance(path, str) and not Path(path).is_absolute() and '..' not in Path(path).parts,
                'artifact path outside private directory')
        target = root/path
        require(not any(p.is_symlink() for p in (target, *target.parents))
                and root in target.resolve().parents and target.is_file(), 'artifact path outside private directory')
        return target.read_bytes()

    scene, evidence = build(source, json.loads(args.capture.read_bytes()), load)
    raw = (json.dumps(scene, ensure_ascii=False, indent=2)+'\n').encode()
    evidence['scene_sha256'] = digest(raw)
    output.mkdir(parents=True, exist_ok=False)
    (output/'scene.json').write_bytes(raw)
    (output/'provenance.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps({'scene': str(output/'scene.json'), 'provenance': str(output/'provenance.json')}))


if __name__ == '__main__':
    main()
