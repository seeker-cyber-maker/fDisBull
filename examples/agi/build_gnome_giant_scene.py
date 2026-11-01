"""Build an authored partial Z scene from supplied gnome/giant observations.

ROUTE_CONTRACT records qualification scope. Hashes and structural checks bind
the supplied evidence; they do not authenticate execution or recover whole KQ1.
Original game text and frame bytes are never emitted in the scene.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from examples.agi.build_clip_scene import frame_evidence, json_artifact, require
from fdisbull.agi import load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend


OBJECT_SHA = '2d1b7a75bb443b4a340cb8d9a2842ff5c834d7d597ea2a1365b6a7a2dfb57985'
DISTANCE_AGI_SHA = '5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74'
DISTANCE_HANDLER_SHA = '1948a0f4a7f843c374a0a80216cc781e9fbf73cf97de2cf42d0d4ada2d422bc9'
ACTION_IDS = ('reach-gnome', 'wrong-names', 'take-key', 'reach-tree', 'unlock-tree',
              'climb-to-clouds', 'wait-for-sleep', 'take-chest')
# Only this contract supplies route coordinates. Tighten its None coordinates
# from a final native receipt; the room-only form is not a native route claim.
ROUTE_CONTRACT = {
    'status': 'pending-native-qualification',
    'anchors': ((36, None, None), (40, None, None), (40, None, None),
                (40, None, None), (19, None, None), (19, None, None),
                (58, None, None), (58, None, None), (58, None, None)),
    'scores': (14, 14, 14, 17, 17, 19, 19, 26, 34),
    'dynamic_source_predicate_anchors': (7, 8),
    'same_ego_pairs': ((7, 8),),
    'dynamic_witness': 'Phase 7 derived sleeping-actor distance, command-time original distance write/return, and phase 8 complete native chest pickup proof.',
}
ITEMS = {'chest': 2, 'key': 5, 'clover': 8, 'diamonds': 15,
         'bag': 16, 'shield': 21, 'mushroom': 24}
QUEST_VARIABLES = {'wrong_stage': '84', 'door_state': '66', 'giant_state': '86'}
QUEST_FLAGS = {'room_callback': '21', 'room_name_prompt': '22', 'key_taken': '84',
               'door_scored': '85', 'shield_active': '102', 'chest_taken': '104',
               'chest_callback': '169', 'sleep_scored': '205'}
BYTE_FIELDS = ('room', 'score', 'x', 'y', 'direction', 'ego_width', 'ego_view',
               'step_size', 'swimming', 'player_control') + tuple(QUEST_VARIABLES)
BYTE_FIELDS += tuple('inventory_'+str(item) for item in ITEMS.values())
BOOL_FIELDS = ('drawn', 'in_water', 'dead', 'ignore_blocks', 'gnome_key_ready')
BOOL_FIELDS += tuple(name+'_carried' for name in ITEMS) + tuple(QUEST_FLAGS)
FIELDS = BYTE_FIELDS + BOOL_FIELDS
REQUIRED_MESSAGES = {
    1: ((40, 0x113, 5), (40, 0x1e0, 19), (40, 0x1ff, 20),
        (40, 0x201, 21), (40, 0x22f, 22)),
    2: ((40, 0x2cc, 12),), 4: ((19, 0x194, 6),),
    6: ((58, 0x450, 29),), 7: ((58, 0x254, 10),),
}
PICKUPS = {
    'key': {'logic': 40, 'item': 5, 'item_offset': 0x2d6, 'score_offset': 0x2db,
            'delta': 3, 'order': ['item', 'return', 'score']},
    'chest': {'logic': 58, 'item': 2, 'item_offset': 0x25d, 'score_offset': 0x25a,
              'delta': 8, 'order': ['score', 'item', 'return']},
}


def digest(raw):
    return sha256(raw).hexdigest()


def exact(mapping, values):
    return isinstance(mapping, dict) and all(
        type(mapping.get(key)) is type(value) and mapping[key] == value
        for key, value in values.items())


def clock(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'missing or invalid guest time')
    return value


def project_state(raw):
    require(isinstance(raw, dict) and isinstance(raw.get('ego'), dict), 'missing state')
    ego = raw['ego']
    state = {key: ego.get(key) if key in ('x', 'y', 'direction', 'drawn') else raw.get(key)
             for key in BYTE_FIELDS[:10] + ('drawn', 'in_water', 'dead', 'ignore_blocks')}
    variables, flags = raw.get('quest_variables'), raw.get('quest_flags')
    require(isinstance(variables, dict) and isinstance(flags, dict), 'missing quest state')
    state.update({name: variables.get(number) for name, number in QUEST_VARIABLES.items()})
    state.update({name: flags.get(number) for name, number in QUEST_FLAGS.items()})
    locations = raw.get('inventory_locations')
    require(isinstance(locations, dict) and set(locations) == {str(n) for n in ITEMS.values()},
            'inventory location set differs')
    for name, item in ITEMS.items():
        state[name+'_carried'] = raw.get(name+'_carried')
        state['inventory_'+str(item)] = locations[str(item)]
    # f21 is reused by room scripts. It is never a global key-possession bit.
    state['gnome_key_ready'] = state['room'] == 40 and state['room_callback'] is True
    if 'gnome_key_ready' in raw:
        require(type(raw['gnome_key_ready']) is bool and
                raw['gnome_key_ready'] == state['gnome_key_ready'], 'contradictory key readiness')
    require(all(type(state[key]) is int and 0 <= state[key] <= 255 for key in BYTE_FIELDS)
            and all(type(state[key]) is bool for key in BOOL_FIELDS), 'invalid typed state')
    require(state['x'] < 160 and state['y'] < 168 and state['direction'] == 0 and state['drawn']
            and state['ego_width'] == 6 and state['ego_view'] == 0 and state['step_size'] == 1
            and state['player_control'] == 1 and state['swimming'] == 0
            and not state['in_water'] and not state['dead'], 'unsettled or unsafe boundary')
    require(state['shield_carried'] and state['shield_active'] and state['clover_carried'],
            'required carried protection differs')
    for name, item in ITEMS.items():
        require(state[name+'_carried'] == (state['inventory_'+str(item)] == 255),
                'inventory byte and carried state differ')
    return state


def object_records(raw):
    require(digest(raw) == OBJECT_SHA, 'OBJECT identity differs')
    decoded = bytes(value ^ b'Avis Durgan'[i % 11] for i, value in enumerate(raw))
    require(len(decoded) >= 84 and int.from_bytes(decoded[:2], 'little') == 81,
            'expected 27 three-byte inventory records')
    records = {}
    for item in ITEMS.values():
        rec = item*3
        name = int.from_bytes(decoded[3+rec:5+rec], 'little')
        end = decoded.find(b'\0', 3+name)
        require(81 <= name and 3+name < end < len(decoded) and end-3-name <= 64,
                'inventory name bounds differ')
        records[item] = {'record_offset': rec, 'location_offset': rec+2,
                         'name_offset': name, 'name_sha256': digest(decoded[3+name:end+1]),
                         'name_length': end-(3+name)+1}
    return records


def source_check(resources):
    distance = resources[58]
    starts = set(logic_layout(distance.payload)['instructions'])
    require({0x236, 0x23a}.issubset(starts)
            and distance.code[0x234:0x238] == bytes((69, 0, 1, 70)),
            'chest distance source operation differs')
    for spec in PICKUPS.values():
        resource = resources[spec['logic']]
        starts = set(logic_layout(resource.payload)['instructions'])
        for offset, instruction in (
            (spec['item_offset'], bytes((92, spec['item']))),
            (spec['score_offset'], bytes((5, 3, spec['delta']))),
        ):
            require(offset+2 in starts and resource.code[offset:offset+len(instruction)] == instruction,
                    'pickup source operation differs')


def observation(value, loader, geometry):
    require(isinstance(value, dict), 'invalid observation')
    frame = frame_evidence(value.get('frame'), loader)
    metadata = frame['metadata']
    shape = tuple(metadata[key] for key in ('mode_id', 'width', 'height'))
    require(geometry is None or shape == geometry, 'frame geometry changed')
    # Keep only the declared frame identity, not arbitrary metadata or paths.
    frame['metadata'] = {key: metadata[key] for key in
                         ('frame_id', 'mode_id', 'width', 'height', 'source')}
    return {'state': project_state(value.get('state')), 'frame': frame,
            'guest_ms': clock(value.get('guest_ms'))}


def message_evidence(message, loader, resources, before, after, geometry, session_id):
    require(isinstance(message, dict) and message.get('format') == 'fdisbull-agi-print-observation-1'
            and message.get('status') == 'completed'
            and message.get('mode') == 'blocking'
            and all(message.get(key) is True for key in
                    ('native_execution', 'native_execution_attempted', 'input_attempted',
                     'handler_return_observed', 'input_settled', 'window_closed'))
            and message.get('cleanup_errors', []) == [], 'unqualified message completion')
    logic, offset, number = (message.get(key) for key in ('logic', 'source_offset', 'message_id'))
    require(type(logic) is int and logic in resources and type(offset) is int and offset >= 0
            and type(number) is int and 1 <= number <= 255, 'invalid message source')
    resource = resources[logic]
    require(offset+2 in logic_layout(resource.payload)['instructions'] and
            resource.code[offset:offset+2] == bytes((101, number)), 'message source instruction differs')
    text = logic_messages(resource)[resource.resource_sha256].get(str(number))
    require(isinstance(text, str) and bool(text), 'missing source message')
    encoded = text.encode('cp437')
    identity, recorded = message.get('identity'), message.get('message')
    require(exact(identity, {'format': 'fdisbull-agi-print-observer-1',
                             'session_id': session_id, 'resource_sha256': resource.resource_sha256})
            and all(type(identity.get(key)) is int and 0 <= identity[key] <= 65535 for key in ('cs', 'ds'))
            and type(identity.get('record')) is int and 0 < identity['record'] <= 65526
            and type(identity.get('state_revision')) is int and identity['state_revision'] >= 0
            and isinstance(identity.get('epoch'), str) and bool(identity['epoch'])
            and exact(recorded, {'resource_sha256': resource.resource_sha256,
                                 'message_id': number, 'text_sha256': digest(encoded),
                                 'length': len(encoded)}), 'message identity differs')
    keyboard = message.get('keyboard_after')
    require(isinstance(message.get('input'), dict) and message['input'].get('accepted') is True
            and isinstance(keyboard, dict) and exact(keyboard.get('keyboard'),
                {'pending_events': 0, 'owned_keys': 0, 'queued_guest_ms': 0}),
            'message keyboard input not settled')
    frame = frame_evidence(message.get('frame'), loader)
    metadata = frame['metadata']
    require(tuple(metadata[key] for key in ('mode_id', 'width', 'height')) == geometry,
            'message frame geometry changed')
    when = clock(message.get('guest_ms'))
    require(before['frame']['metadata']['frame_id'] < metadata['frame_id']
            < after['frame']['metadata']['frame_id'] and before['guest_ms'] < when <= after['guest_ms'],
            'message outside action frame or guest-time bounds')
    frame['metadata'] = {key: metadata[key] for key in
                         ('frame_id', 'mode_id', 'width', 'height', 'source')}
    return {'logic': logic, 'source_offset': offset, 'message_id': number,
            'resource_sha256': resource.resource_sha256, 'text_sha256': digest(encoded),
            'length': len(encoded), 'guest_ms': when, 'frame': frame,
            'native_binding': {key: identity[key] for key in ('session_id', 'cs', 'ds')}}


def pickup_evidence(reference, loader, name, resource, records, before, after, native_ds):
    proof = json_artifact(reference, loader, name+' pickup')
    spec = PICKUPS[name]
    require(exact(proof, {'format': 'fdisbull-agi-quest-pickup-1', 'name': name,
                         'status': 'verified', 'complete': True, 'native_execution': True,
                         'source_logic': spec['logic'], 'source_logic_sha256': resource.resource_sha256,
                         'item': spec['item'], 'item_source_offset': spec['item_offset'],
                         'score_source_offset': spec['score_offset'], 'score_delta': spec['delta']})
            and proof.get('order') == spec['order'] and proof.get('cleanup_errors', []) == [],
            'pickup source, order or completion differs')
    before_values = {'score': before['score'], 'item_location': before['inventory_'+str(spec['item'])]}
    after_values = {'score': after['score'], 'item_location': after['inventory_'+str(spec['item'])]}
    require(before_values['item_location'] == 0 and after_values['item_location'] == 255
            and after_values['score'] == before_values['score']+spec['delta']
            and exact(proof.get('before'), before_values) and exact(proof.get('after'), after_values)
            and exact(proof.get('known_effects'), after_values), 'pickup committed effects differ')
    require(exact(proof.get('item_writer'), {'cause_offset': 0x7482, 'resume_offset': 0x7486})
            and exact(proof.get('score_writer'), {'cause_offset': 0x72da, 'resume_offset': 0x72de,
                                                 'bx': 3, 'al': spec['delta']})
            and exact(proof.get('handler_return'), {'offset': 0x2fa, 'observed': True,
                         'source_cursor_offset': spec['item_offset']+2, 'stack_verified': True}),
            'pickup original writer or handler return differs')
    binding = proof.get('inventory_binding')
    record = records[spec['item']]
    require(exact(binding, {'source_sha256': OBJECT_SHA, 'stride': 3, 'item': spec['item'],
                           'record_offset': record['record_offset'], 'location_offset': record['location_offset'],
                           'name_offset': record['name_offset'], 'name_sha256': record['name_sha256'],
                           'carried_value': 255}), 'pickup named OBJECT record differs')
    base, end, location = (binding.get(key) for key in ('base', 'end', 'location_linear'))
    require(all(type(value) is int for value in (base, end, location)) and 0 < base < end <= 65536
            and end-base == 81 and base+record['name_offset']+record['name_length'] <= 65536,
            'pickup inventory bounds differ')
    ds_linear = location-base-record['location_offset']
    require(ds_linear == native_ds*16
            and exact(proof['item_writer'], {'di_offset': base+record['record_offset']}),
            'pickup live inventory address differs')
    trace = proof.get('trace')
    require(isinstance(trace, dict) and type(trace.get('event_count')) is int
            and 0 < trace['event_count'] < 128 and type(trace.get('maximum_count')) is int
            and trace['maximum_count'] == 128, 'pickup trace bounds differ')
    recorded = json_artifact(trace, loader, name+' trace')
    require(exact(recorded, {'format': 'fdisbull-agi-quest-trace-1', 'name': name,
                            'complete': True, 'maximum_count': 128})
            and isinstance(recorded.get('events'), list) and len(recorded['events']) == trace['event_count']
            and all(isinstance(event, dict) for event in recorded['events'])
            and isinstance(recorded.get('runs'), list) and bool(recorded['runs'])
            and all(isinstance(run, dict) for run in recorded['runs']) and not recorded.get('next_cursor'),
            'pickup trace incomplete or contradictory')
    return {'sha256': reference['sha256'], 'name': name, 'item': spec['item'],
            'source_logic': spec['logic'], 'source_logic_sha256': resource.resource_sha256,
            'item_source_offset': spec['item_offset'], 'score_source_offset': spec['score_offset'],
            'order': list(spec['order']), 'inventory_name_sha256': record['name_sha256'],
            'before': before_values, 'after': after_values,
            'inventory_binding': {key: binding[key] for key in
                ('base', 'end', 'stride', 'item', 'record_offset', 'location_offset',
                 'location_linear', 'name_offset', 'name_sha256')},
            'handler_return': deepcopy(proof['handler_return']),
            'trace': {key: trace[key] for key in ('sha256', 'event_count', 'maximum_count')}}


def route_states(states):
    anchors, scores = ROUTE_CONTRACT['anchors'], ROUTE_CONTRACT['scores']
    require(len(states) == len(anchors) == len(scores) == 9, 'route contract differs')
    for i, (state, (room, x, y), score) in enumerate(zip(states, anchors, scores)):
        require(state['room'] == room and (x is None or state['x'] == x)
                and (y is None or state['y'] == y), 'route anchor differs')
        require(state['score'] == score and state['key_carried'] == (i >= 3)
                and state['chest_carried'] == (i == 8)
                and state['key_taken'] == (i >= 3) and state['door_scored'] == (i >= 5)
                and state['chest_taken'] == (i == 8) and (i != 8 or state['chest_callback'])
                and state['sleep_scored'] == (i >= 7)
                and state['door_state'] == (0 if i < 5 else 1 if i == 5 else 2)
                and state['giant_state'] == (0 if i < 7 else 1 if i == 7 else 3),
                'route score, inventory or quest transition differs')
        require(all(not state[name+'_carried'] and state['inventory_'+str(ITEMS[name])] == 0
                    for name in ('bag', 'diamonds', 'mushroom')), 'preceding cave inventory differs')
        if state['room'] == 40:
            require(state['wrong_stage'] == (0 if i == 1 else 3) and not state['room_name_prompt']
                    and (i != 1 or not state['gnome_key_ready'])
                    and (i != 2 or state['gnome_key_ready']), 'gnome main boundary differs')
    for before, after in ROUTE_CONTRACT['same_ego_pairs']:
        require(all(states[before][key] == states[after][key] for key in ('x', 'y')),
                'dynamic pickup pose changed')


def giant_pickup_condition(raw):
    """Derive a close-enough pose; pre-command v70 need not be fresh."""
    actors = raw.get('quest_actors')
    require(isinstance(actors, dict) and isinstance(actors.get('1'), dict),
            'missing sleeping giant actor')
    actor = actors['1']
    # stop.motion selects normal motion (0) and direction 0. The raw flags'
    # bit 7 is opaque motion_bit, not an enabled/stopped movement indicator.
    require(exact(actor, {'view': 52, 'drawn': True, 'motion': 0, 'direction': 0})
            and type(actor.get('motion_bit')) is bool
            and all(type(actor.get(key)) is int and -32768 <= actor[key] <= 32767
                    for key in ('x', 'y'))
            and all(type(actor.get(key)) is int and 0 < actor[key] <= 65535
                    for key in ('width', 'height')),
            'sleeping giant pose or motion differs')
    distance = raw['quest_variables'].get('70')
    ego = raw['ego']
    measured = abs(ego['x']+raw['ego_width']//2-actor['x']-actor['width']//2)
    measured += abs(ego['y']-actor['y'])
    require(type(distance) is int and 0 <= distance <= 255, 'invalid captured pre-command v70')
    require(measured <= 30, 'derived sleeping giant distance is out of range')
    return {'actor': 1, 'view': 52, 'drawn': True, 'motion': 0, 'direction': 0,
            'motion_bit': actor['motion_bit'],
            'actor_position': {key: actor[key] for key in ('x', 'y', 'width', 'height')},
            'ego_position': {'x': ego['x'], 'y': ego['y'], 'width': raw['ego_width']},
            'derived_distance': measured, 'maximum_distance': 30,
            'captured_v70': distance, 'captured_v70_used_as_distance_witness': False,
            'scope': 'Host-derived pre-command distance only; original v70 is computed inside GET CHEST. motion_bit is opaque, and actor motion and timers are not projected.'}


def distance_evidence(reference, loader, resource, raw, condition, binding, agi_sha):
    """Bind the command-time original distance write and real handler return."""
    proof = json_artifact(reference, loader, 'giant distance')
    expected = condition['derived_distance']
    require(exact(proof, {'format': 'fdisbull-agi-chest-distance-1', 'status': 'verified',
                         'complete': True, 'native_execution': True, 'source_logic': 58,
                         'source_logic_sha256': resource.resource_sha256,
                         'source_offset': 0x234, 'source_cursor_offset': 0x238,
                         'known_result': expected})
            and proof.get('cleanup_errors', []) == [] and not proof.get('failure')
            and isinstance(proof.get('arguments'), list) and proof['arguments'] == [0, 1, 70]
            and all(type(value) is int for value in proof['arguments']),
            'original distance completion, source or native result differs')
    identity = {**binding, 'agi_sha256': agi_sha, 'handler_sha256': DISTANCE_HANDLER_SHA}
    require(agi_sha == DISTANCE_AGI_SHA and exact(proof.get('identity'), identity),
            'distance engine or session identity differs')
    actor = raw['quest_actors']['1']
    ego = {'x': raw['ego']['x'], 'y': raw['ego']['y'], 'width': raw['ego_width'],
           'view': raw['ego_view'], 'direction': raw['ego']['direction'], 'drawn': raw['ego']['drawn']}
    giant = {key: actor[key] for key in ('x', 'y', 'width', 'height', 'view', 'direction', 'motion', 'drawn')}
    require(exact(giant, {'width': 30, 'height': 15}), 'distance original VIEW 52 dimensions differ')
    state = {'room': raw['room'], 'score': raw['score'], 'sleep_state': raw['quest_variables']['86'],
             'sleep_scored': raw['quest_flags']['205'], 'chest_taken_flag': raw['quest_flags']['104'],
             'shield_flag': raw['quest_flags']['102'],
             **{name+'_location': raw['inventory_locations'][str(item)]
                for name, item in (('key', 5), ('shield', 21), ('chest', 2))}}
    for name in ('before', 'after'):
        observed = proof.get(name)
        require(exact(observed, state) and exact(observed.get('ego'), ego)
                and exact(observed.get('giant'), giant), 'distance pose or quest state differs')
    before_v70 = proof['before'].get('v70')
    require(type(before_v70) is int and 0 <= before_v70 <= 255
            and exact(proof['before'], {'expected_distance': expected})
            and exact(proof['after'], {'v70': expected}), 'distance calculated value differs')
    table, writer, returned = proof.get('actor_table'), proof.get('distance_writer'), proof.get('handler_return')
    require(type(table) is int and 0 < table and table+86 <= 65536
            and exact(writer, {'cause_offset': 0x48a2, 'resume_offset': 0x48a6,
                               'bx': 70, 'ax': expected, 'si': table, 'di': table+43})
            and all(type(writer.get(key)) is int and 0 <= writer[key] <= 65535
                    for key in ('bp', 'sp', 'ss')) and 4 <= writer['bp'] <= 65525
            and writer['sp'] == writer['bp']-4, 'distance original writer or call frame differs')
    require(exact(returned, {'offset': 0x2fa, 'observed': True, 'source_cursor_offset': 0x238,
                            'stack_verified': True, 'ss': writer['ss'], 'writer_bp': writer['bp'],
                            'sp': writer['bp']+8})
            and all(type(returned.get(key)) is int and 0 <= returned[key] <= 65535 for key in ('ax', 'si')),
            'distance original handler return differs')
    code = returned['ax']-0x238
    require(0 <= code and code+len(resource.code) <= 65536 and returned['si'] == code+0x235,
            'distance original return source cursor differs')
    return {'sha256': reference['sha256'], 'source_logic': 58,
            'source_logic_sha256': resource.resource_sha256, 'source_offset': 0x234,
            'source_cursor_offset': 0x238, 'arguments': [0, 1, 70], 'identity': identity,
            'derived_expected_distance': expected, 'native_result': proof['known_result'],
            'before_v70': before_v70, 'actor_table': table,
            'distance_writer': {key: writer[key] for key in
                ('cause_offset', 'resume_offset', 'bx', 'ax', 'si', 'di', 'bp', 'sp', 'ss')},
            'handler_return': {key: returned[key] for key in
                ('offset', 'observed', 'source_cursor_offset', 'stack_verified', 'ss', 'writer_bp', 'sp', 'ax', 'si')},
            'scope': 'Supplied command-time native distance write and real return, bound to the captured sleeping pose; not independent authentication.'}


def build(source, capture, artifact_loader):
    """Validate supplied captures and emit no native operations or game text."""
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-gnome-giant-capture-1',
            'invalid quest capture')
    runtime = capture.get('runtime')
    require(isinstance(runtime, dict) and runtime.get('policy') == 'physical'
            and runtime.get('fresh_game') is True and runtime.get('interventions') == []
            and isinstance(runtime.get('session_id'), str) and bool(runtime['session_id']),
            'unqualified runtime')
    identity = capture.get('source')
    require(isinstance(identity, dict) and identity.get('agi_sha256') == digest((source/'AGI').read_bytes())
            and identity.get('object_sha256') == OBJECT_SHA, 'source identity differs')
    records = object_records((source/'OBJECT').read_bytes())
    expected = identity.get('resources')
    require(isinstance(expected, dict) and 5 <= len(expected) <= 256
            and all(str(n) in expected for n in (0, 19, 36, 40, 58)), 'missing source identities')
    resources = {}
    for key, value in expected.items():
        require(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', key) is not None
                and int(key) <= 255 and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
                'invalid source identity')
        resource = load_logic(source/'LOGDIR', source, int(key), profile='2.917')
        require(resource.resource_sha256 == value, 'source logic hash differs')
        resources[int(key)] = resource
    source_check(resources)
    observations, actions = capture.get('observations'), capture.get('actions')
    require(isinstance(observations, dict) and isinstance(actions, list) and len(actions) == 8
            and all(isinstance(action, dict) and action.get('id') == name
                    for action, name in zip(actions, ACTION_IDS)), 'expected eight ordered actions')
    require(all(actions[i].get('before') == actions[i-1].get('after') for i in range(1, 8)),
            'actions are not contiguous')
    ids = [actions[0].get('before')] + [action.get('after') for action in actions]
    require(all(isinstance(ident, str) and bool(ident) for ident in ids)
            and len(set(ids)) == 9 and set(observations) == set(ids),
            'missing, duplicate or extra main observations')
    checked, geometry = {}, None
    for ident in ids:
        checked[ident] = observation(observations[ident], artifact_loader, geometry)
        if geometry is None:
            geometry = tuple(checked[ident]['frame']['metadata'][key]
                             for key in ('mode_id', 'width', 'height'))
    ordered = [checked[ident] for ident in ids]
    require(all(a['frame']['metadata']['frame_id'] < b['frame']['metadata']['frame_id']
                and a['guest_ms'] < b['guest_ms'] for a, b in zip(ordered, ordered[1:])),
            'main frame or guest-time order differs')
    states = [value['state'] for value in ordered]
    route_states(states)
    giant_condition = giant_pickup_condition(observations[ids[7]]['state'])
    messages = []
    for i, action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True,
                'incomplete action')
        inputs = action.get('inputs')
        require(isinstance(inputs, list) and (bool(inputs) or i == 6)
                and all(isinstance(item, dict) and item.get('kind') == 'keyboard'
                        and isinstance(item.get('key'), str) and bool(item['key'])
                        and item.get('delivered') is True and item.get('complete') is True
                        and isinstance(item.get('delivery'), dict) and item['delivery'].get('accepted') is True
                        for item in inputs), 'unqualified physical input')
        if i == 7:
            require([item['key'].strip().lower() for item in inputs] ==
                    ['type:get chest', 'press:enter'], 'expected one original GET CHEST command')
        raw_messages = action.get('messages')
        require(isinstance(raw_messages, list), 'missing action messages')
        bindings = [message_evidence(message, artifact_loader, resources, ordered[i], ordered[i+1],
                                    geometry, runtime['session_id'])
                    for message in raw_messages]
        require(all(a['frame']['metadata']['frame_id'] < b['frame']['metadata']['frame_id']
                    and a['guest_ms'] < b['guest_ms'] for a, b in zip(bindings, bindings[1:])),
                'message frame or guest-time order differs')
        required = REQUIRED_MESSAGES.get(i, ())
        selected = [binding for binding in bindings if
                    (binding['logic'], binding['source_offset'], binding['message_id']) in required]
        require([(m['logic'], m['source_offset'], m['message_id']) for m in selected] == list(required),
                'required original message sequence differs')
        messages.append(bindings)
    guesses = capture.get('guess_observations')
    require(isinstance(guesses, list) and len(guesses) == 3, 'expected exactly three guess observations')
    checked_guesses, previous = [], ordered[1]
    partitions = (REQUIRED_MESSAGES[1][:2], REQUIRED_MESSAGES[1][2:4], REQUIRED_MESSAGES[1][4:])
    for stage, value in enumerate(guesses, 1):
        require(isinstance(value, dict) and type(value.get('stage')) is int and value['stage'] == stage,
                'guess stage order differs')
        current = observation(value, artifact_loader, geometry)
        state = current['state']
        require(state['room'] == 40 and state['score'] == 14 and not state['key_carried']
                and state['wrong_stage'] == stage and state['room_name_prompt'] == (stage < 3)
                and state['gnome_key_ready'] == (stage == 3), 'guess state differs')
        require(all(state[key] == states[2][key] for key in FIELDS
                    if key not in ('wrong_stage', 'room_callback', 'room_name_prompt', 'gnome_key_ready')),
                'guess observation contradicts final wrong-name state')
        require(previous['frame']['metadata']['frame_id'] < current['frame']['metadata']['frame_id']
                < ordered[2]['frame']['metadata']['frame_id']
                and previous['guest_ms'] < current['guest_ms'] < ordered[2]['guest_ms'],
                'guess outside wrong-name frame or guest-time bounds')
        for required in partitions[stage-1]:
            binding = next(m for m in messages[1] if (m['logic'], m['source_offset'], m['message_id']) == required)
            require(previous['frame']['metadata']['frame_id'] < binding['frame']['metadata']['frame_id']
                    < current['frame']['metadata']['frame_id']
                    and previous['guest_ms'] < binding['guest_ms'] <= current['guest_ms'],
                    'required modal not completed before its guess snapshot')
        checked_guesses.append({'stage': stage, **current})
        previous = current
    require(checked_guesses[-1]['state'] == states[2], 'third guess and main after-state differ')
    door = observation(capture.get('door_observation'), artifact_loader, geometry)
    door_state = door['state']
    actors = capture['door_observation']['state'].get('quest_actors')
    require(isinstance(actors, dict), 'missing original door actor')
    actor = actors.get('1')
    require(door_state['room'] == 19 and door_state['score'] == 19 and door_state['door_state'] == 2
            and door_state['ignore_blocks'] and door_state['key_carried'] and door_state['door_scored']
            and exact(actor, {'view': 20, 'cel': 3, 'drawn': True}), 'original open-door actor state differs')
    require(all(door_state[key] == states[5][key] for key in FIELDS
                if key not in ('x', 'y', 'door_state', 'ignore_blocks', 'room_callback', 'room_name_prompt')),
            'open-door observation contradicts route state')
    require(ordered[5]['frame']['metadata']['frame_id'] < door['frame']['metadata']['frame_id']
            < ordered[6]['frame']['metadata']['frame_id']
            and ordered[5]['guest_ms'] < door['guest_ms'] < ordered[6]['guest_ms'],
            'door observation outside climb bounds')
    door['actor_1'] = {key: actor[key] for key in ('view', 'cel', 'drawn')}
    all_records = ordered + checked_guesses + [door] + [m for group in messages for m in group]
    frame_ids = [value['frame']['metadata']['frame_id'] for value in all_records]
    require(len(set(frame_ids)) == len(frame_ids), 'duplicate frame identity across observations')
    chronological = sorted(all_records, key=lambda value: value['frame']['metadata']['frame_id'])
    require(all(a['guest_ms'] <= b['guest_ms'] for a, b in zip(chronological, chronological[1:])),
            'frame and guest clocks contradict')
    native_binding = messages[1][0]['native_binding']
    require(all(message['native_binding'] == native_binding for group in messages for message in group),
            'message native session or segment binding differs')
    native_distance = distance_evidence(actions[7].get('native_distance'), artifact_loader, resources[58],
                                       observations[ids[7]]['state'], giant_condition, native_binding,
                                       identity['agi_sha256'])
    pickups = {name: pickup_evidence(actions[index].get('native_pickup'), artifact_loader, name,
                resources[PICKUPS[name]['logic']], records, states[index], states[index+1], native_binding['ds'])
               for name, index in (('key', 2), ('chest', 7))}
    require(all(pickups['key']['inventory_binding'][key] == pickups['chest']['inventory_binding'][key]
                for key in ('base', 'end', 'stride')), 'pickup inventory table changed')
    variables = {'$phase': {'type': 'u8', 'initial': 0},
                 **{'$'+key: {'type': 'bool' if key in BOOL_FIELDS else 'u8', 'initial': states[0][key]}
                    for key in FIELDS}}
    replies = ('The supplied route reaches the gnome.', 'The supplied guesses reveal the key.',
               'The supplied action takes the key.', 'The supplied route reaches the tree.',
               'The supplied action unlocks the door.', 'The supplied route reaches the clouds.',
               'The supplied wait reaches the sleeping giant.', 'The supplied action takes the chest.')
    programs = {}
    for i, name in enumerate(ACTION_IDS):
        before, after = states[i:i+2]
        body = [{'id': 'phase', 'op': 'require', 'condition':
                 {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}}]
        body += [{'id': 'guard-'+key, 'op': 'require', 'condition':
                  {'op': 'eq', 'left': {'var': '$'+key}, 'right': before[key]}} for key in FIELDS]
        body += [{'id': 'set-'+key, 'op': 'set', 'var': '$'+key, 'value': after[key]}
                 for key in FIELDS if before[key] != after[key]]
        body += [{'id': 'set-phase', 'op': 'set', 'var': '$phase', 'value': i+1},
                 {'id': 'message', 'op': 'text', 'resource': 'message'}]
        programs[name] = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                          'resources': {'message': {'kind': 'text', 'text': replies[i]}}, 'body': body}
    targets = ('trail', 'gnome', 'key', 'tree', 'door', 'stairs', 'giant', 'chest')
    objects = []
    for i, target in enumerate(targets):
        item = {'id': target, 'context': 'phase-'+str(i), 'label': target, 'aliases': [],
                'description': 'The next supplied route action.',
                'bindings': [{'verb': 'take' if target in ('key', 'chest') else 'use', 'program': ACTION_IDS[i]}]}
        if target in ('key', 'chest'):
            item['inventory_when'] = {'op': 'eq', 'left': {'var': '$'+target+'_carried'}, 'right': True}
        objects.append(item)
    for name in ITEMS:
        if name in ('key', 'chest'):
            continue
        objects.append({'id': 'inventory-'+name, 'context': 'phase-0', 'label': name, 'aliases': [],
                        'description': 'A projected inventory item.', 'bindings': [],
                        'visible_when': {'op': 'eq', 'left': False, 'right': True},
                        'inventory_when': {'op': 'eq', 'left': {'var': '$'+name+'_carried'}, 'right': True}})
    scene = {'format': 'fdisbull-il-scene-1', 'partial': True, 'programs': programs, 'objects': objects,
             'contexts': [{'id': 'phase-'+str(i), 'title': 'Partial gnome and giant route',
                           'description': 'An authored partial projection of supplied observations; accompanying provenance records qualification scope.',
                           'when': {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}} for i in range(9)]}
    ILSceneBackend(scene)
    evidence = {'format': 'fdisbull-agi-gnome-giant-z-evidence-1',
                'source': {'agi_sha256': identity['agi_sha256'], 'object_sha256': OBJECT_SHA,
                           'resources': deepcopy(expected)}, 'route_contract': deepcopy(ROUTE_CONTRACT),
                'capture_sha256': digest(json.dumps(capture, sort_keys=True, separators=(',', ':'),
                                                    ensure_ascii=False, allow_nan=False).encode()),
                'projection_fields': list(FIELDS), 'observations': checked,
                'guess_observations': checked_guesses, 'door_observation': door, 'pickups': pickups,
                'giant_pickup_condition': giant_condition,
                'native_distance': native_distance,
                'edges': [{'id': action['id'], 'before': action['before'], 'after': action['after'],
                           'messages': messages[i]} for i, action in enumerate(actions)],
                'scope': 'Supplied consistency and hashes do not authenticate execution, recover all AGI behavior, provide autonomous timing, or create durable saves.'}
    return scene, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'capture', 'artifacts', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args(argv)
    source, root, output = args.source.resolve(), args.artifacts.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not args.output.is_symlink() and not output.exists() and output != checkout
            and checkout not in output.parents and all(output != p and p not in output.parents
                and output not in p.parents for p in (source, root)), 'output must be a fresh private directory')

    def load(path):
        require(isinstance(path, str) and not Path(path).is_absolute(), 'artifact path outside private directory')
        target = (root/path).resolve()
        require(root in target.parents and target.is_file(), 'artifact path outside private directory')
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
