"""Authored unit-test resources and captures; no original game bytes or text."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from examples.agi import build_gnome_giant_scene as exporter
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player, ProcessBackend


ACTIONS = ('reach-gnome', 'wrong-names', 'take-key', 'reach-tree', 'unlock-tree',
           'climb-to-clouds', 'wait-for-sleep', 'take-chest')
COMMANDS = ('use trail', 'use gnome', 'take key', 'use tree', 'use door',
            'use stairs', 'use giant', 'take chest')
ROOMS = (36, 40, 40, 40, 19, 19, 58, 58, 58)
SCORES = (14, 14, 14, 17, 17, 19, 19, 26, 34)
ITEMS = {'chest': 2, 'key': 5, 'clover': 8, 'diamonds': 15,
         'bag': 16, 'shield': 21, 'mushroom': 24}
REQUIRED_PRINTS = {1: [(40, 0x113, 5), (40, 0x1e0, 19), (40, 0x1ff, 20),
                      (40, 0x201, 21), (40, 0x22f, 22)],
                   2: [(40, 0x2cc, 12)], 4: [(19, 0x194, 6)],
                   6: [(58, 0x450, 29)], 7: [(58, 0x254, 10)]}


@pytest.fixture
def case(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'AGI').write_bytes(b'authored unit engine, not a native executable')
    monkeypatch.setattr(exporter, 'DISTANCE_AGI_SHA', sha256((source/'AGI').read_bytes()).hexdigest())
    decoded = bytearray(0x300)
    decoded[:2] = (81).to_bytes(2, 'little')
    for item in ITEMS.values():
        offset = 0x80 + item * 16
        name = f'unit-item-{item}'.encode() + b'\0'
        decoded[3+3*item:5+3*item] = offset.to_bytes(2, 'little')
        decoded[3+offset:3+offset+len(name)] = name
    object_bytes = bytes(x ^ b'Avis Durgan'[i % 11] for i, x in enumerate(decoded))
    (source / 'OBJECT').write_bytes(object_bytes)
    monkeypatch.setattr(exporter, 'OBJECT_SHA', sha256(object_bytes).hexdigest())
    codes = {n: bytearray(0x500) for n in (0, 19, 36, 40, 58)}
    for messages in REQUIRED_PRINTS.values():
        for logic, offset, message in messages:
            codes[logic][offset:offset+2] = bytes((101, message))
    for logic, offset, instruction in [(40, 0x2d6, bytes((92, 5))),
                                       (40, 0x2db, bytes((5, 3, 3))),
                                       (58, 0x234, bytes((69, 0, 1, 70))),
                                       (58, 0x25a, bytes((5, 3, 8))),
                                       (58, 0x25d, bytes((92, 2)))]:
        codes[logic][offset:offset+len(instruction)] = instruction
    # Extra source-bound messages remain legal; their completion is not ignored.
    codes[0][0x20:0x22] = bytes((101, 1))
    text = b'Unit-test-only dialogue\0'
    encoded = bytes(x ^ b'Avis Durgan'[i % 11] for i, x in enumerate(text))
    directory = bytearray(b'\xff\xff\xff' * 59)
    volume = bytearray()
    for n, code in sorted(codes.items()):
        count, offset = 29, 2 + 2*29
        messages = bytes((count,)) + (offset+len(text)).to_bytes(2, 'little')
        messages += offset.to_bytes(2, 'little')*count + encoded
        payload = len(code).to_bytes(2, 'little') + code + messages
        directory[n*3:n*3+3] = len(volume).to_bytes(3, 'big')
        volume += b'\x12\x34\0' + len(payload).to_bytes(2, 'little') + payload
    (source / 'LOGDIR').write_bytes(directory)
    (source / 'VOL.0').write_bytes(volume)
    resources = {str(n): load_logic(source/'LOGDIR', source, n, profile='2.917').resource_sha256
                 for n in codes}
    artifacts = {}

    def frame(number):
        path = f'unit-frame-{number}'
        raw = path.encode()
        artifacts[path] = raw
        return {'path': path, 'sha256': sha256(raw).hexdigest(),
                'metadata': {'frame_id': number, 'mode_id': 5, 'width': 320,
                             'height': 200, 'source': 'last_completed_guest_frame'}}

    def state(index):
        carried = {name: name in ('clover', 'shield') or name == 'key' and index >= 3
                   or name == 'chest' and index == 8 for name in ITEMS}
        anchor = exporter.ROUTE_CONTRACT['anchors'][index]
        x, y = (30 if anchor[1] is None else anchor[1]), (120 if anchor[2] is None else anchor[2])
        result = {'room': ROOMS[index], 'score': SCORES[index],
                'ego': {'x': x, 'y': y, 'direction': 0, 'drawn': True},
                'ego_width': 6, 'ego_view': 0, 'step_size': 1, 'swimming': 0,
                'in_water': False, 'dead': False, 'player_control': 1,
                'ignore_blocks': False,
                **{name+'_carried': value for name, value in carried.items()},
                'inventory_locations': {str(item): 255 if carried[name] else 0
                                        for name, item in ITEMS.items()},
                'quest_variables': {'84': 0 if index < 2 else 3,
                                    '66': 0 if index < 5 else 1 if index == 5 else 2,
                                    '86': 0 if index < 7 else 1 if index == 7 else 3,
                                    '70': 24 if index == 8 else 0},
                'quest_flags': {'21': index == 2, '22': False, '84': index >= 3,
                                '85': index >= 5, '102': True, '104': index == 8,
                                '169': index == 8, '205': index >= 7}}
        if index >= 7:
            result['quest_actors'] = {'1': {'view': 52, 'drawn': True, 'motion_bit': False,
                                          'motion': 0, 'direction': 0,
                                          'x': x-12, 'y': y-24, 'width': 30, 'height': 15}}
        return result

    observations = {f'o{i}': {'state': state(i), 'frame': frame(i*100+1),
                              'guest_ms': 1000+i*100} for i in range(9)}
    delivered = {'kind': 'keyboard', 'key': 'press:up', 'delivered': True,
                 'complete': True, 'delivery': {'accepted': True}}
    actions = [{'id': name, 'before': f'o{i}', 'after': f'o{i+1}',
                'complete': True, 'messages_complete': True,
                'inputs': [] if i == 6 else [deepcopy(delivered)], 'messages': []}
               for i, name in enumerate(ACTIONS)]
    actions[7]['inputs'] = [{**deepcopy(delivered), 'key': key}
                            for key in ('type:get chest', 'press:enter')]

    def message(logic, offset, number, number_frame, guest_ms):
        return {'format': 'fdisbull-agi-print-observation-1',
                'logic': logic, 'source_offset': offset, 'message_id': number,
                'status': 'completed', 'mode': 'blocking', 'guest_ms': guest_ms,
                **{k: True for k in ('native_execution', 'native_execution_attempted',
                                     'input_attempted', 'handler_return_observed',
                                     'input_settled', 'window_closed')},
                'identity': {'format': 'fdisbull-agi-print-observer-1',
                             'session_id': 'unit-session',
                             'cs': 0x1000, 'ds': 0x2000, 'record': 0x3000,
                             'state_revision': number_frame, 'epoch': 'unit-'+str(number_frame),
                             'resource_sha256': resources[str(logic)]},
                'message': {'resource_sha256': resources[str(logic)], 'message_id': number,
                            'text_sha256': sha256(text[:-1]).hexdigest(), 'length': len(text)-1},
                'input': {'accepted': True},
                'keyboard_after': {'keyboard': {'pending_events': 0, 'owned_keys': 0,
                                               'queued_guest_ms': 0}},
                'frame': frame(number_frame)}

    for i, specs in REQUIRED_PRINTS.items():
        for j, spec in enumerate(specs):
            delta = (10, 20, 40, 50, 70)[j] if i == 1 else 20
            actions[i]['messages'].append(message(*spec, i*100+1+delta, 1000+i*100+delta))
    guesses = []
    for stage, delta in [(1, 30), (2, 60), (3, 80)]:
        s = deepcopy(observations['o2']['state'])
        s['quest_variables']['84'] = stage
        s['quest_flags']['21'] = stage == 3
        s['quest_flags']['22'] = stage < 3
        guesses.append({'stage': stage, 'state': s, 'frame': frame(101+delta),
                        'guest_ms': 1100+delta})
    door_state = deepcopy(observations['o5']['state'])
    door_state['quest_variables']['66'] = 2
    door_state['ignore_blocks'] = True
    door_state['quest_actors'] = {'1': {'view': 20, 'cel': 3, 'drawn': True}}
    door = {'state': door_state, 'frame': frame(551), 'guest_ms': 1550}

    def proof(name, logic, item, item_offset, score_offset, delta, before, order):
        rec, name_offset = 3*item, 0x80+16*item
        raw_name = f'unit-item-{item}'.encode() + b'\0'
        trace = {'format': 'fdisbull-agi-quest-trace-1', 'name': name, 'complete': True,
                 'maximum_count': 128, 'events': [{'unit_fetch': i} for i in range(3)],
                 'runs': [{'outcome': 'breakpoint'}]}
        raw = json.dumps(trace).encode()
        artifacts[name+'-trace'] = raw
        p = {'format': 'fdisbull-agi-quest-pickup-1', 'name': name, 'status': 'verified',
             'complete': True, 'native_execution': True, 'source_logic': logic,
             'source_logic_sha256': resources[str(logic)], 'item': item,
             'item_source_offset': item_offset, 'score_source_offset': score_offset,
             'score_delta': delta, 'order': list(order),
             'before': {'score': before, 'item_location': 0},
             'known_effects': {'score': before+delta, 'item_location': 255},
             'after': {'score': before+delta, 'item_location': 255},
             'item_writer': {'cause_offset': 0x7482, 'resume_offset': 0x7486,
                             'di_offset': 0x4000+rec},
             'score_writer': {'cause_offset': 0x72da, 'resume_offset': 0x72de,
                              'bx': 3, 'al': delta},
             'handler_return': {'offset': 0x2fa, 'observed': True,
                                'source_cursor_offset': item_offset+2, 'stack_verified': True},
             'inventory_binding': {'source_sha256': exporter.OBJECT_SHA,
                 'base': 0x4000, 'end': 0x4051, 'stride': 3, 'item': item,
                 'record_offset': rec, 'name_offset': name_offset,
                 'location_offset': rec+2, 'location_linear': 0x24000+rec+2,
                 'carried_value': 255, 'name_sha256': sha256(raw_name).hexdigest()},
             'trace': {'path': name+'-trace', 'sha256': sha256(raw).hexdigest(),
                       'event_count': 3, 'maximum_count': 128}}
        raw = json.dumps(p).encode()
        artifacts[name+'-proof'] = raw
        return {'path': name+'-proof', 'sha256': sha256(raw).hexdigest()}

    actions[2]['native_pickup'] = proof('key', 40, 5, 0x2d6, 0x2db, 3, 14,
                                       ('item', 'return', 'score'))
    actions[7]['native_pickup'] = proof('chest', 58, 2, 0x25d, 0x25a, 8, 26,
                                       ('score', 'item', 'return'))
    pose = distance_pose(observations['o7']['state'])
    distance = {'format': 'fdisbull-agi-chest-distance-1', 'status': 'verified',
        'complete': True, 'native_execution': True, 'source_logic': 58,
        'source_logic_sha256': resources['58'], 'source_offset': 0x234,
        'source_cursor_offset': 0x238, 'arguments': [0, 1, 70], 'actor_table': 0x5000,
        'identity': {'session_id': 'unit-session', 'cs': 0x1000, 'ds': 0x2000,
                     'agi_sha256': sha256((source/'AGI').read_bytes()).hexdigest(),
                     'handler_sha256': exporter.DISTANCE_HANDLER_SHA},
        'before': {**deepcopy(pose), 'v70': 0, 'expected_distance': 24},
        'after': {**deepcopy(pose), 'v70': 24}, 'known_result': 24,
        'distance_writer': {'cause_offset': 0x48a2, 'resume_offset': 0x48a6, 'bx': 70,
            'ax': 24, 'si': 0x5000, 'di': 0x502b, 'bp': 0x8000, 'sp': 0x7ffc, 'ss': 0x3000},
        'handler_return': {'offset': 0x2fa, 'observed': True, 'source_cursor_offset': 0x238,
            'stack_verified': True, 'ss': 0x3000, 'writer_bp': 0x8000, 'sp': 0x8008,
            'ax': 0x6238, 'si': 0x6235}}
    raw = json.dumps(distance).encode(); artifacts['giant-distance-proof'] = raw
    actions[7]['native_distance'] = {'path': 'giant-distance-proof', 'sha256': sha256(raw).hexdigest()}
    capture = {'format': 'fdisbull-agi-gnome-giant-capture-1',
               'fixture_scope': 'synthetic-unit-test-only; not native evidence',
               'runtime': {'policy': 'physical', 'fresh_game': True, 'interventions': [],
                           'session_id': 'unit-session'},
               'source': {'agi_sha256': sha256((source/'AGI').read_bytes()).hexdigest(),
                          'object_sha256': exporter.OBJECT_SHA, 'resources': resources},
               'observations': observations, 'actions': actions,
               'guess_observations': guesses, 'door_observation': door}
    return source, capture, lambda path: artifacts[path], artifacts, message


def distance_pose(state):
    """Authored unit fixture in DistanceProbe's public receipt schema."""
    actor = state['quest_actors']['1']
    return {'room': 58, 'score': 26,
        'ego': {'x': state['ego']['x'], 'y': state['ego']['y'], 'width': 6, 'view': 0,
                'direction': 0, 'drawn': True},
        'giant': {key: actor[key] for key in
            ('x', 'y', 'width', 'height', 'view', 'direction', 'motion', 'drawn')},
        'sleep_state': 1, 'sleep_scored': True, 'chest_taken_flag': False, 'shield_flag': True,
        'key_location': 255, 'shield_location': 255, 'chest_location': 0}


def rewrite_distance(capture, artifacts, mutation):
    ref = capture['actions'][7]['native_distance']
    proof = json.loads(artifacts[ref['path']]); mutation(proof)
    raw = json.dumps(proof).encode(); artifacts[ref['path']] = raw
    ref['sha256'] = sha256(raw).hexdigest()


def test_eight_actions_inventory_guards_checkpoint_and_privacy(case):
    source, capture, loader, _, _ = case
    scene, evidence = exporter.build(source, capture, loader)
    assert scene['partial'] is True
    assert evidence['route_contract'] == exporter.ROUTE_CONTRACT
    backend = ILSceneBackend(scene)
    player = Player(backend)
    assert 'partial' in player.execute('look').lower()
    assert {x['label'] for x in backend.observe()['inventory']} == {'clover', 'shield'}
    assert player.execute_result('take chest')['action_sent'] is False
    for i, command in enumerate(COMMANDS):
        assert player.execute(command).startswith('Success:'), command
        if i == 1:
            assert backend.save('key-ready')['status'] == 'saved'
            token = backend.observe()['context']['token']
        if i == 2:
            assert player.execute('take key') == 'Rejected: Action refused.'
            assert backend.act({'verb': 'take', 'target': 'key', 'item': None,
                                'context_token': token})['status'] == 'rejected'
    assert backend.state['$phase'] == 8 and backend.state['$score'] == 34
    assert backend.state['$key_carried'] and backend.state['$chest_carried']
    assert not backend.state['$gnome_key_ready']
    assert {x['label'] for x in backend.observe()['inventory']} == {'clover', 'shield', 'key', 'chest'}
    assert player.execute('take chest') == 'Rejected: Action refused.'
    stale = backend.observe()['context']['token']
    assert backend.load('key-ready')['status'] == 'restored'
    assert backend.act({'verb': 'take', 'target': 'key', 'item': None,
                        'context_token': stale})['status'] == 'rejected'
    assert player.execute('take key').startswith('Success:')
    assert ILSceneBackend(scene).load('key-ready')['status'] == 'missing'
    assert 'Unit-test-only dialogue' not in str(scene) + str(evidence)
    assert 'unit-item-' not in str(scene) + str(evidence)


@pytest.mark.parametrize('fault', ['missing_main', 'extra_main', 'duplicate_main', 'action_order',
    'disconnected', 'missing_action', 'intervention', 'not_fresh', 'room', 'score',
    'key_flag', 'sleep_flag', 'chest_callback', 'door_variable', 'giant_variable',
    'missing_inventory', 'extra_inventory', 'inventory_bool', 'inventory_byte',
    'missing_guess', 'extra_guess', 'guess_order', 'guess_flag21', 'guess_flag22',
    'guess_stage_variable', 'guess_score', 'guess_key', 'guess_position',
    'missing_door', 'door_view', 'door_cel', 'door_drawn', 'door_blocks', 'door_control'])
def test_missing_or_contradictory_capture_refused(case, fault):
    source, capture, loader, _, _ = case
    obs = capture['observations']
    if fault == 'missing_main': del obs['o3']
    elif fault == 'extra_main': obs['extra'] = deepcopy(obs['o0'])
    elif fault == 'duplicate_main': capture['actions'][0]['after'] = 'o0'
    elif fault == 'action_order': capture['actions'][1]['id'] = 'take-key'
    elif fault == 'disconnected': capture['actions'][2]['before'] = 'o0'
    elif fault == 'missing_action': capture['actions'].pop()
    elif fault == 'intervention': capture['runtime']['interventions'] = ['unit edit']
    elif fault == 'not_fresh': capture['runtime']['fresh_game'] = False
    elif fault == 'room': obs['o7']['state']['room'] = 59
    elif fault == 'score': obs['o8']['state']['score'] = 33
    elif fault == 'key_flag': obs['o3']['state']['quest_flags']['84'] = False
    elif fault == 'sleep_flag': obs['o7']['state']['quest_flags']['205'] = False
    elif fault == 'chest_callback': obs['o8']['state']['quest_flags']['169'] = False
    elif fault == 'door_variable': obs['o5']['state']['quest_variables']['66'] = 2
    elif fault == 'giant_variable': obs['o7']['state']['quest_variables']['86'] = 0
    elif fault == 'missing_inventory': del obs['o0']['state']['inventory_locations']['8']
    elif fault == 'extra_inventory': obs['o0']['state']['inventory_locations']['1'] = 0
    elif fault == 'inventory_bool': obs['o0']['state']['clover_carried'] = False
    elif fault == 'inventory_byte': obs['o0']['state']['inventory_locations']['21'] = 0
    elif fault == 'missing_guess': capture['guess_observations'].pop()
    elif fault == 'extra_guess': capture['guess_observations'].append(deepcopy(capture['guess_observations'][2]))
    elif fault == 'guess_order': capture['guess_observations'][0]['stage'] = 2
    elif fault.startswith('guess_'):
        g = capture['guess_observations'][0]['state']
        if fault == 'guess_flag21': g['quest_flags']['21'] = True
        elif fault == 'guess_flag22': g['quest_flags']['22'] = False
        elif fault == 'guess_stage_variable': g['quest_variables']['84'] = 2
        elif fault == 'guess_score': g['score'] = 15
        elif fault == 'guess_key': g['key_carried'] = True; g['inventory_locations']['5'] = 255
        elif fault == 'guess_position': g['ego']['x'] += 1
    elif fault == 'missing_door': del capture['door_observation']
    else:
        d = capture['door_observation']['state']
        if fault == 'door_view': d['quest_actors']['1']['view'] = 19
        elif fault == 'door_cel': d['quest_actors']['1']['cel'] = 2
        elif fault == 'door_drawn': d['quest_actors']['1']['drawn'] = False
        elif fault == 'door_blocks': d['ignore_blocks'] = False
        elif fault == 'door_control': d['player_control'] = 0
    with pytest.raises(ValueError):
        exporter.build(source, capture, loader)


@pytest.mark.parametrize('field,value', [('direction', 1), ('drawn', False), ('ego_width', 4),
    ('ego_view', 60), ('step_size', 2), ('swimming', 1), ('in_water', True), ('dead', True),
    ('player_control', 0), ('score', True), ('x', 160), ('y', 168)])
def test_normal_neutral_typed_boundaries_required(case, field, value):
    source, capture, loader, _, _ = case
    state = capture['observations']['o0']['state']
    (state['ego'] if field in ('x', 'y', 'direction', 'drawn') else state)[field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


def test_room_local_callback_never_becomes_global_key_state(case):
    source, capture, loader, _, _ = case
    capture['observations']['o0']['state']['quest_flags']['21'] = True
    scene, _ = exporter.build(source, capture, loader)
    backend = ILSceneBackend(scene)
    assert backend.state['$room_callback'] is True
    assert backend.state['$gnome_key_ready'] is False and not backend.state['$key_carried']
    capture['observations']['o0']['state']['gnome_key_ready'] = True
    with pytest.raises(ValueError, match='key readiness'): exporter.build(source, capture, loader)


@pytest.mark.parametrize('fault', ['main_frame', 'main_time', 'guess_frame', 'guess_time',
    'door_frame', 'door_time', 'message_frame', 'message_time', 'modal_stage',
    'duplicate_frame', 'nonfinite_time', 'boolean_time', 'frame_hash', 'frame_geometry'])
def test_frame_guest_time_and_stage_modal_order(case, fault):
    source, capture, loader, _, _ = case
    if fault == 'main_frame': capture['observations']['o1']['frame']['metadata']['frame_id'] = 1
    elif fault == 'main_time': capture['observations']['o1']['guest_ms'] = 1000
    elif fault == 'guess_frame': capture['guess_observations'][0]['frame']['metadata']['frame_id'] = 201
    elif fault == 'guess_time': capture['guess_observations'][0]['guest_ms'] = 1200
    elif fault == 'door_frame': capture['door_observation']['frame']['metadata']['frame_id'] = 601
    elif fault == 'door_time': capture['door_observation']['guest_ms'] = 1500
    elif fault == 'message_frame': capture['actions'][1]['messages'][0]['frame']['metadata']['frame_id'] = 101
    elif fault == 'message_time': capture['actions'][1]['messages'][0]['guest_ms'] = 1100
    elif fault == 'modal_stage': capture['actions'][1]['messages'][1]['guest_ms'] = 1131
    elif fault == 'duplicate_frame': capture['guess_observations'][0]['frame']['metadata']['frame_id'] = 121
    elif fault == 'nonfinite_time': capture['observations']['o0']['guest_ms'] = float('nan')
    elif fault == 'boolean_time': capture['observations']['o0']['guest_ms'] = True
    elif fault == 'frame_hash': capture['observations']['o0']['frame']['sha256'] = '0'*64
    elif fault == 'frame_geometry': capture['guess_observations'][0]['frame']['metadata']['mode_id'] = 6
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('action,required', [(i, j) for i, rows in REQUIRED_PRINTS.items() for j in range(len(rows))])
def test_each_required_original_print_is_required(case, action, required):
    source, capture, loader, _, _ = case
    capture['actions'][action]['messages'].pop(required)
    with pytest.raises(ValueError, match='message sequence'): exporter.build(source, capture, loader)


@pytest.mark.parametrize('field,value', [('format', 'other'), ('status', 'incomplete'), ('mode', 'timed'),
    ('native_execution', False), ('native_execution_attempted', False), ('input_attempted', False),
    ('handler_return_observed', False), ('input_settled', False), ('window_closed', False),
    ('cleanup_errors', [{'error': 'unit failure'}]), ('source_offset', 0x114), ('message_id', 6)])
def test_message_completion_and_source_guards(case, field, value):
    source, capture, loader, _, _ = case
    capture['actions'][1]['messages'][0][field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('fault', ['identity_format', 'session', 'text_hash', 'message_hash',
    'length', 'input', 'keyboard', 'empty_required_inputs', 'incomplete_delivery'])
def test_message_and_keyboard_identities(case, fault):
    source, capture, loader, _, _ = case
    m = capture['actions'][1]['messages'][0]
    if fault == 'identity_format': m['identity']['format'] = 'other'
    elif fault == 'session': m['identity']['session_id'] = 'another-session'
    elif fault == 'text_hash': m['message']['text_sha256'] = '0'*64
    elif fault == 'message_hash': m['message']['resource_sha256'] = '0'*64
    elif fault == 'length': m['message']['length'] += 1
    elif fault == 'input': m['input']['accepted'] = False
    elif fault == 'keyboard': m['keyboard_after']['keyboard']['queued_guest_ms'] = 1
    elif fault == 'empty_required_inputs': capture['actions'][2]['inputs'] = []
    elif fault == 'incomplete_delivery': capture['actions'][2]['inputs'][0]['complete'] = False
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


def test_extra_messages_are_validated_and_not_silently_discarded(case):
    source, capture, loader, _, message = case
    extra = message(0, 0x20, 1, 21, 1020)
    capture['actions'][0]['messages'].append(extra)
    _, evidence = exporter.build(source, capture, loader)
    assert evidence['edges'][0]['messages'][0]['source_offset'] == 0x20
    extra['handler_return_observed'] = False
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


def rewrite_artifact(capture, artifacts, action, mutation):
    ref = capture['actions'][action]['native_pickup']
    proof = json.loads(artifacts[ref['path']])
    mutation(proof)
    raw = json.dumps(proof).encode()
    artifacts[ref['path']] = raw
    ref['sha256'] = sha256(raw).hexdigest()


@pytest.mark.parametrize('action', [2, 7])
@pytest.mark.parametrize('part,field,value', [
    (None, 'format', 'other'), (None, 'name', 'other'), (None, 'status', 'incomplete'),
    (None, 'complete', False), (None, 'native_execution', False), (None, 'item', 1),
    (None, 'source_logic_sha256', '0'*64), (None, 'item_source_offset', 0),
    (None, 'score_source_offset', 0), (None, 'order', ['item', 'score', 'return']),
    ('before', 'item_location', 255), ('after', 'score', 0), ('known_effects', 'item_location', 0),
    ('item_writer', 'cause_offset', 0x7483), ('item_writer', 'resume_offset', 0x7487),
    ('item_writer', 'di_offset', 0), ('score_writer', 'cause_offset', 0x72db),
    ('score_writer', 'resume_offset', 0x72df), ('score_writer', 'bx', 2), ('score_writer', 'al', 1),
    ('handler_return', 'offset', 0), ('handler_return', 'source_cursor_offset', 0),
    ('handler_return', 'stack_verified', False), ('handler_return', 'observed', False),
    ('inventory_binding', 'source_sha256', '0'*64), ('inventory_binding', 'base', 0),
    ('inventory_binding', 'end', 0x4050), ('inventory_binding', 'stride', 4),
    ('inventory_binding', 'name_offset', 1), ('inventory_binding', 'name_sha256', '0'*64),
    ('inventory_binding', 'location_linear', 0x24001), ('inventory_binding', 'record_offset', 1),
    ('inventory_binding', 'location_offset', 1), ('inventory_binding', 'carried_value', 0),
    ('trace', 'event_count', 0), ('trace', 'event_count', 128), ('trace', 'maximum_count', 127),
    ('trace', 'sha256', '0'*64)])
def test_each_pickup_proof_field_fails_closed(case, action, part, field, value):
    source, capture, loader, artifacts, _ = case
    def mutate(proof):
        (proof if part is None else proof[part])[field] = value
    rewrite_artifact(capture, artifacts, action, mutate)
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('action', [2, 7])
@pytest.mark.parametrize('fault', ['missing', 'proof_hash', 'trace_hash', 'trace_format', 'trace_name',
    'trace_incomplete', 'trace_events', 'trace_runs', 'trace_count', 'trace_cursor'])
def test_complete_hash_bound_bounded_traces_required(case, action, fault):
    source, capture, loader, artifacts, _ = case
    ref = capture['actions'][action]['native_pickup']
    if fault == 'missing': del capture['actions'][action]['native_pickup']
    elif fault == 'proof_hash': ref['sha256'] = '0'*64
    else:
        proof = json.loads(artifacts[ref['path']])
        trace_ref = proof['trace']; trace = json.loads(artifacts[trace_ref['path']])
        if fault == 'trace_hash': artifacts[trace_ref['path']] += b' '
        elif fault == 'trace_format': trace['format'] = 'other'
        elif fault == 'trace_name': trace['name'] = 'other'
        elif fault == 'trace_incomplete': trace['complete'] = False
        elif fault == 'trace_events': trace['events'] = []
        elif fault == 'trace_runs': trace['runs'] = []
        elif fault == 'trace_count': trace_ref['event_count'] += 1
        elif fault == 'trace_cursor': trace['next_cursor'] = 'more'
        if fault not in ('trace_hash', 'trace_count'):
            raw = json.dumps(trace).encode(); artifacts[trace_ref['path']] = raw
            trace_ref['sha256'] = sha256(raw).hexdigest()
        raw = json.dumps(proof).encode(); artifacts[ref['path']] = raw
        ref['sha256'] = sha256(raw).hexdigest()
    before_capture, before_artifacts = deepcopy(capture), deepcopy(artifacts)
    with pytest.raises(ValueError): exporter.build(source, capture, loader)
    assert capture == before_capture and artifacts == before_artifacts


@pytest.mark.parametrize('logic,offset', [(40, 0x2d6), (40, 0x2db), (58, 0x234), (58, 0x25a), (58, 0x25d)])
def test_changed_pickup_opcode_cannot_be_relabelled_with_new_hash(case, logic, offset):
    source, capture, loader, _, _ = case
    directory = (source/'LOGDIR').read_bytes()
    address = int.from_bytes(directory[logic*3:logic*3+3], 'big') & 0xfffff
    raw = bytearray((source/'VOL.0').read_bytes()); raw[address+7+offset] = 0
    (source/'VOL.0').write_bytes(raw)
    capture['source']['resources'][str(logic)] = load_logic(source/'LOGDIR', source, logic, profile='2.917').resource_sha256
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('field', exporter.FIELDS + ('phase',))
def test_every_projected_precondition_is_guarded(case, field):
    source, capture, loader, _, _ = case
    scene, _ = exporter.build(source, capture, loader)
    backend = ILSceneBackend(scene)
    key = '$'+field
    old = backend.state[key]
    backend.state[key] = not old if type(old) is bool else (old+1) % 256
    before = deepcopy(backend.state)
    out = backend.act({'verb': 'use', 'target': 'trail', 'item': None,
                       'context_token': backend.observe()['context']['token']})
    assert out['status'] == 'rejected' and backend.state == before


def test_separate_content_process_player_and_checkpoint(case, tmp_path, monkeypatch):
    source, capture, loader, _, _ = case
    scene, _ = exporter.build(source, capture, loader)
    path = tmp_path/'unit-scene.json'; path.write_text(json.dumps(scene))
    checkout = Path(__file__).resolve().parents[1]
    monkeypatch.setenv('PYTHONPATH', str(checkout/'src') + os.pathsep + str(checkout/'player'))
    service = ProcessBackend([sys.executable, '-m', 'fdisbull.il_scenes', str(path)])
    try:
        player = Player(service)
        for command in COMMANDS[:2]: assert player.execute(command).startswith('Success:')
        old = service.observe()['context']['token']
        assert service.save('ready')['status'] == 'saved'
        for command in COMMANDS[2:]: assert player.execute(command).startswith('Success:')
        assert service.observe()['context']['id'] == 'phase-8'
        assert {o['label'] for o in service.observe()['inventory']} == {'clover', 'shield', 'key', 'chest'}
        assert player.execute('take chest') == 'Rejected: Action refused.'
        assert service.load('ready')['status'] == 'restored'
        assert service.act({'verb': 'take', 'target': 'key', 'item': None,
                            'context_token': old})['status'] == 'rejected'
        assert player.execute('take key').startswith('Success:')
    finally: service.close()
    service = ProcessBackend([sys.executable, '-m', 'fdisbull.il_scenes', str(path)])
    try: assert service.load('ready')['status'] == 'missing'
    finally: service.close()


@pytest.mark.parametrize('target', ['checkout', 'source', 'artifacts', 'existing', 'symlink'])
def test_cli_refuses_nonfresh_or_protected_output(case, tmp_path, target):
    source, _, _, _, _ = case
    root = tmp_path/'artifacts'; root.mkdir()
    checkout = Path(exporter.__file__).resolve().parents[2]
    existing = tmp_path/'existing'; existing.mkdir()
    symlink = tmp_path/'link'; symlink.symlink_to(tmp_path/'absent')
    output = {'checkout': checkout/'unit-disallowed-gnome-output', 'source': source/'out',
              'artifacts': root/'out', 'existing': existing, 'symlink': symlink}[target]
    with pytest.raises(ValueError, match='fresh private directory'):
        exporter.main(['--source', str(source), '--capture', str(tmp_path/'absent-capture'),
                       '--artifacts', str(root), '--output', str(output)])


@pytest.mark.parametrize('field,value', [('view', 53), ('drawn', False),
    ('motion', 1), ('motion', 2), ('motion', True), ('motion', False), ('motion', 0.0),
    ('direction', 1), ('direction', 8), ('direction', True), ('direction', False), ('direction', 0.0),
    ('x', True), ('y', 120.0), ('width', True), ('width', 0)])
def test_native_chest_actor_predicate_refuses_wrong_or_moving_actor(case, field, value):
    source, capture, loader, _, _ = case
    capture['observations']['o7']['state']['quest_actors']['1'][field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('field', ['motion', 'direction'])
def test_native_chest_actor_requires_explicit_stationary_fields(case, field):
    source, capture, loader, _, _ = case
    del capture['observations']['o7']['state']['quest_actors']['1'][field]
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('motion_bit', [False, True])
def test_stationary_giant_accepts_either_opaque_motion_bit(case, motion_bit):
    source, capture, loader, _, _ = case
    actor = capture['observations']['o7']['state']['quest_actors']['1']
    actor['motion_bit'] = motion_bit
    _, evidence = exporter.build(source, capture, loader)
    condition = evidence['giant_pickup_condition']
    assert condition['motion'] == 0 and type(condition['motion']) is int
    assert condition['direction'] == 0 and type(condition['direction']) is int
    assert condition['motion_bit'] is motion_bit
    assert 'motion_enabled' not in condition


@pytest.mark.parametrize('value', [None, 0, 1, 'false'])
def test_opaque_motion_bit_keeps_boolean_schema(case, value):
    source, capture, loader, _, _ = case
    capture['observations']['o7']['state']['quest_actors']['1']['motion_bit'] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('field,value', [('motion', 1), ('motion', 2), ('direction', 1)])
def test_legacy_motion_enabled_alias_cannot_prove_stationary(case, field, value):
    source, capture, loader, _, _ = case
    actor = capture['observations']['o7']['state']['quest_actors']['1']
    actor.update(motion_enabled=False)
    actor[field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


def test_pre_get_v70_is_stale_until_command_computes_native_distance(case):
    _, capture, _, _, _ = case
    state = capture['observations']['o7']['state']
    state['quest_variables']['70'] = 0
    condition = exporter.giant_pickup_condition(state)
    assert condition['derived_distance'] == 24
    assert condition['captured_v70'] == 0
    assert condition['captured_v70_used_as_distance_witness'] is False


@pytest.mark.parametrize('distance', [True, False, 0.0, -1, 256, None])
def test_pre_get_v70_keeps_byte_schema_without_claiming_freshness(case, distance):
    source, capture, loader, _, _ = case
    capture['observations']['o7']['state']['quest_variables']['70'] = distance
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('stale', [0, 1, 31, 255])
def test_stale_pre_get_byte_accepts_later_native_distance_24(case, stale):
    source, capture, loader, _, _ = case
    capture['observations']['o7']['state']['quest_variables']['70'] = stale
    _, evidence = exporter.build(source, capture, loader)
    assert evidence['giant_pickup_condition']['captured_v70'] == stale
    assert evidence['giant_pickup_condition']['derived_distance'] == 24
    assert evidence['native_distance']['derived_expected_distance'] == 24
    assert evidence['native_distance']['native_result'] == 24


def test_derived_host_distance_still_requires_close_enough_actor(case):
    _, capture, _, _, _ = case
    state = capture['observations']['o7']['state']
    state['quest_actors']['1']['y'] = state['ego']['y']-31
    state['quest_variables']['70'] = 0
    with pytest.raises(ValueError, match='derived sleeping giant distance'):
        exporter.giant_pickup_condition(state)


@pytest.mark.parametrize('part,field,value', [
    (None, 'format', 'other'), (None, 'status', 'incomplete'), (None, 'complete', False),
    (None, 'native_execution', False), (None, 'source_logic', 40),
    (None, 'source_logic_sha256', '0'*64), (None, 'source_offset', 0x235),
    (None, 'source_cursor_offset', 0x239), (None, 'arguments', [0, 1, 71]),
    (None, 'arguments', [False, 1, 70]), (None, 'known_result', 0),
    (None, 'known_result', True), (None, 'actor_table', 0x5001),
    (None, 'actor_table', True), (None, 'actor_table', 65500),
    (None, 'failure', {'phase': 'return'}), (None, 'cleanup_errors', ['failed']),
    ('identity', 'session_id', 'other'), ('identity', 'cs', 0x1001),
    ('identity', 'ds', 0x2001), ('identity', 'agi_sha256', '0'*64),
    ('identity', 'handler_sha256', '0'*64), ('before', 'expected_distance', 0),
    ('before', 'v70', True), ('before', 'score', 19), ('before', 'key_location', 0),
    ('after', 'v70', 0), ('after', 'chest_location', 255), ('after', 'shield_flag', False),
    ('distance_writer', 'cause_offset', 0x48a1), ('distance_writer', 'resume_offset', 0x48a7),
    ('distance_writer', 'bx', 69), ('distance_writer', 'ax', 0),
    ('distance_writer', 'si', 0x5001), ('distance_writer', 'di', 0x502c),
    ('distance_writer', 'bp', True), ('distance_writer', 'bp', 65526),
    ('distance_writer', 'sp', 0x7ffd), ('distance_writer', 'ss', 0x3001),
    ('handler_return', 'offset', 0x2fb), ('handler_return', 'observed', False),
    ('handler_return', 'source_cursor_offset', 0x239), ('handler_return', 'stack_verified', False),
    ('handler_return', 'ss', 0x3001), ('handler_return', 'writer_bp', 0x8001),
    ('handler_return', 'sp', 0x8007), ('handler_return', 'ax', 0),
    ('handler_return', 'si', 0x6236), ('handler_return', 'ax', True)])
def test_native_distance_receipt_rejects_partial_stale_or_mismatched_fields(case, part, field, value):
    source, capture, loader, artifacts, _ = case
    rewrite_distance(capture, artifacts, lambda proof: (proof if part is None else proof[part]).update({field: value}))
    before_capture, before_artifacts = deepcopy(capture), deepcopy(artifacts)
    with pytest.raises(ValueError): exporter.build(source, capture, loader)
    assert capture == before_capture and artifacts == before_artifacts


@pytest.mark.parametrize('part', [None, 'identity', 'before', 'after', 'distance_writer', 'handler_return'])
def test_native_distance_requires_complete_receipt(case, part):
    source, capture, loader, artifacts, _ = case
    if part is None: del capture['actions'][7]['native_distance']
    else: rewrite_distance(capture, artifacts, lambda proof: proof.pop(part))
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('part', ['before', 'after'])
@pytest.mark.parametrize('actor,field,value', [
    ('ego', 'x', 31), ('ego', 'direction', False), ('ego', 'drawn', 1),
    ('giant', 'x', 19), ('giant', 'height', 16), ('giant', 'motion', False),
    ('giant', 'direction', False), ('giant', 'drawn', 1)])
def test_native_distance_must_use_same_typed_ego_and_giant_pose(case, part, actor, field, value):
    source, capture, loader, artifacts, _ = case
    rewrite_distance(capture, artifacts, lambda proof: proof[part][actor].update({field: value}))
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


def test_native_distance_artifact_hash_is_required(case):
    source, capture, loader, _, _ = case
    capture['actions'][7]['native_distance']['sha256'] = '0'*64
    with pytest.raises(ValueError): exporter.build(source, capture, loader)


@pytest.mark.parametrize('keys', [
    ['press:up'], ['type:get chest'], ['type:get chest', 'press:enter', 'press:f3', 'press:enter'],
    ['type:get chest', 'press:enter', 'type:get chest', 'press:enter'],
    ['press:enter', 'type:get chest'], ['type:get key', 'press:enter']])
def test_distance_and_pickup_belong_to_one_get_chest_input(case, keys):
    source, capture, loader, _, _ = case
    accepted = capture['actions'][7]['inputs'][0]
    capture['actions'][7]['inputs'] = [{**deepcopy(accepted), 'key': key} for key in keys]
    with pytest.raises(ValueError, match='one original GET CHEST'): exporter.build(source, capture, loader)


def test_different_engine_cannot_relabel_distance_abi(case):
    source, capture, loader, artifacts, _ = case
    (source/'AGI').write_bytes(b'different authored unit engine')
    altered = sha256((source/'AGI').read_bytes()).hexdigest()
    capture['source']['agi_sha256'] = altered
    rewrite_distance(capture, artifacts, lambda proof: proof['identity'].update(agi_sha256=altered))
    with pytest.raises(ValueError, match='distance engine'): exporter.build(source, capture, loader)


def test_original_distance_operand_cannot_be_relabelled(case):
    source, capture, loader, _, _ = case
    directory = (source/'LOGDIR').read_bytes()
    address = int.from_bytes(directory[58*3:58*3+3], 'big') & 0xfffff
    raw = bytearray((source/'VOL.0').read_bytes()); raw[address+7+0x237] = 71
    (source/'VOL.0').write_bytes(raw)
    capture['source']['resources']['58'] = load_logic(source/'LOGDIR', source, 58, profile='2.917').resource_sha256
    with pytest.raises(ValueError, match='distance source operation'): exporter.build(source, capture, loader)


def test_distance_actor_and_source_tables_can_use_other_valid_offsets(case):
    source, capture, loader, artifacts, _ = case
    def relocate(proof):
        proof['actor_table'] = 0x5100
        proof['distance_writer'].update(si=0x5100, di=0x512b)
        proof['handler_return'].update(ax=0x6438, si=0x6435)
        proof['before']['v70'] = 255
    rewrite_distance(capture, artifacts, relocate)
    _, evidence = exporter.build(source, capture, loader)
    assert evidence['native_distance']['native_result'] == 24
    assert evidence['native_distance']['actor_table'] == 0x5100


@pytest.mark.parametrize('dx,dy', [(-10, 0), (0, -10), (10, 5)])
def test_sleeping_giant_accepts_nonfixed_source_distance_pose(case, dx, dy):
    source, capture, loader, artifacts, _ = case
    s = capture['observations']['o7']['state']
    x, y = s['ego']['x']+dx, s['ego']['y']+dy
    s['quest_actors']['1'].update(x=x, y=y)
    expected = abs(s['ego']['x']+s['ego_width']//2-x-15)+abs(s['ego']['y']-y)
    def update(proof):
        pose = distance_pose(s)
        proof['before'] = {**deepcopy(pose), 'v70': 0, 'expected_distance': expected}
        proof['after'] = {**deepcopy(pose), 'v70': expected}
        proof['known_result'] = expected; proof['distance_writer']['ax'] = expected
    rewrite_distance(capture, artifacts, update)
    _, evidence = exporter.build(source, capture, loader)
    assert evidence['giant_pickup_condition']['derived_distance'] == expected
    assert evidence['native_distance']['native_result'] == expected


def test_pending_room_contract_can_tighten_a_single_anchor(case, monkeypatch):
    source, capture, loader, _, _ = case
    contract = deepcopy(exporter.ROUTE_CONTRACT)
    contract['anchors'] = list(contract['anchors'])
    p = capture['observations']['o0']['state']['ego']
    contract['anchors'][0] = (36, p['x'], p['y'])
    monkeypatch.setattr(exporter, 'ROUTE_CONTRACT', contract)
    exporter.build(source, capture, loader)
    p['x'] += 1
    with pytest.raises(ValueError, match='route anchor'): exporter.build(source, capture, loader)


def test_cli_writes_private_scene_and_artifact_escape_is_refused(case, tmp_path):
    source, capture, _, artifacts, _ = case
    root = tmp_path/'private-artifacts'; root.mkdir()
    for path, raw in artifacts.items(): (root/path).write_bytes(raw)
    cap = root/'capture.json'; cap.write_text(json.dumps(capture))
    output = tmp_path/'new-private-scene'
    args = ['--source', str(source), '--capture', str(cap), '--artifacts', str(root)]
    exporter.main(args+['--output', str(output)])
    scene = json.loads((output/'scene.json').read_text())
    evidence = json.loads((output/'provenance.json').read_text())
    assert evidence['scene_sha256'] == sha256((output/'scene.json').read_bytes()).hexdigest()
    assert ILSceneBackend(scene).observe()['context']['id'] == 'phase-0'
    frame = capture['observations']['o0']['frame']
    outside = tmp_path/'outside-frame'; outside.write_bytes(artifacts[frame['path']])
    frame['path'] = '../outside-frame'
    cap.write_text(json.dumps(capture))
    refused = tmp_path/'no-output-on-escape'
    with pytest.raises(ValueError, match='artifact path outside'):
        exporter.main(args+['--output', str(refused)])
    assert not refused.exists()


def test_artifact_symlink_cannot_escape_private_directory(case, tmp_path):
    source, capture, _, artifacts, _ = case
    root = tmp_path/'private-artifacts'; root.mkdir()
    for path, raw in artifacts.items(): (root/path).write_bytes(raw)
    first = capture['observations']['o0']['frame']
    target = root/first['path']; target.unlink()
    outside = tmp_path/'external-frame'; outside.write_bytes(artifacts[first['path']])
    target.symlink_to(outside)
    cap = root/'capture.json'; cap.write_text(json.dumps(capture))
    output = tmp_path/'refused-output'
    with pytest.raises(ValueError, match='artifact path outside'):
        exporter.main(['--source', str(source), '--capture', str(cap), '--artifacts', str(root),
                       '--output', str(output)])
    assert not output.exists()


def test_separate_player_cli_runs_eight_actions_and_checkpoints_turns(case, tmp_path):
    source, capture, loader, _, _ = case
    scene, _ = exporter.build(source, capture, loader)
    path = tmp_path/'unit scene with spaces.json'; path.write_text(json.dumps(scene))
    checkout = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(checkout/'src')+os.pathsep+str(checkout/'player'))
    service = shlex.join([sys.executable, '-m', 'fdisbull.il_scenes', str(path)])
    turns = [json.dumps({'commands': list(COMMANDS)}),
             json.dumps({'commands': ['take chest', 'inventory']})]
    result = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', service,
                             '--live', '--backend-timeout', '5'],
                            input='\n'.join(turns)+'\n', capture_output=True, text=True,
                            env=env, timeout=15)
    assert result.returncode == 0, result.stderr
    first, second = [json.loads(line) for line in result.stdout.splitlines()]
    assert first['status'] == second['status'] == 'complete'
    assert len(first['outcomes']) == 8
    assert all(outcome['outcome'].startswith('Success:') for outcome in first['outcomes'])
    assert first['checkpoint']['status'] == second['checkpoint']['status'] == 'saved'
    # Live turns share one content process; restore describes initial admission.
    # Explicit checkpoint load and token invalidation are checked above.
    assert first['restore']['status'] == second['restore']['status'] == 'missing'
    assert second['outcomes'][0]['outcome'] == 'Rejected: Action refused.'
    assert all(name in second['outcomes'][1]['outcome'] for name in ('clover', 'shield', 'key', 'chest'))


def test_dynamic_chest_pickup_keeps_the_qualified_ego_pose(case):
    source, capture, loader, _, _ = case
    capture['observations']['o8']['state']['ego']['x'] += 1
    with pytest.raises(ValueError, match='dynamic pickup pose'):
        exporter.build(source, capture, loader)


def test_completed_print_may_share_its_snapshot_guest_time(case):
    source, capture, loader, _, _ = case
    capture['actions'][1]['messages'][1]['guest_ms'] = capture['guess_observations'][0]['guest_ms']
    exporter.build(source, capture, loader)


def test_flag169_before_chest_is_captured_not_assumed_false(case):
    source, capture, loader, _, _ = case
    capture['observations']['o7']['state']['quest_flags']['169'] = True
    scene, _ = exporter.build(source, capture, loader)
    backend = ILSceneBackend(scene)
    player = Player(backend)
    for command in COMMANDS[:7]: assert player.execute(command).startswith('Success:')
    assert backend.state['$chest_callback'] is True
