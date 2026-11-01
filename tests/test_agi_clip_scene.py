"""Authored capture/source fixtures; no original game bytes or native play."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

from examples.agi import build_clip_scene as exporter
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player


def fixture(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'AGI').write_bytes(b'authored engine identity')
    code = bytearray(0x420)
    # Authored IF/OR encoding with a separate first rectangle and the required
    # second position test. The false edge skips four authored return bytes.
    code[0x408:0x41a] = bytes.fromhex('fffc0b00010203040b0048544857fcff0400')
    final_code = bytearray(178); final_code[175:177] = bytes((101, 1))
    text = b'Authored final-room notice.\0'; key = b'Avis Durgan'
    encrypted = bytes(value ^ key[index % len(key)] for index, value in enumerate(text))
    payloads = {39: len(code).to_bytes(2, 'little') + code + b'\0\x02\0',
                40: len(final_code).to_bytes(2, 'little') + final_code +
                    b'\x01' + (4+len(text)).to_bytes(2, 'little') + b'\x04\0' + encrypted}
    directory = bytearray(b'\xff\xff\xff' * 41); volume = bytearray()
    for number, payload in payloads.items():
        directory[3*number:3*number+3] = len(volume).to_bytes(3, 'big')
        volume += b'\x12\x34\0' + len(payload).to_bytes(2, 'little') + payload
    (source / 'LOGDIR').write_bytes(directory)
    picture = b'\xff'
    picdir = bytearray(b'\xff\xff\xff' * 40)
    picdir[3*39:3*39+3] = len(volume).to_bytes(3, 'big')
    volume += b'\x12\x34\0' + len(picture).to_bytes(2, 'little') + picture
    (source / 'PICDIR').write_bytes(picdir); (source / 'VOL.0').write_bytes(volume)
    resources = {str(number): load_logic(source / 'LOGDIR', source, number, profile='2.917').resource_sha256
                 for number in (39, 40)}
    artifacts = {}
    def frame(index):
        path = f'frame-{index}'; raw = f'authored frame {index}'.encode(); artifacts[path] = raw
        return {'path': path, 'sha256': sha256(raw).hexdigest(), 'metadata': {
            'frame_id': index+1, 'mode_id': 5, 'width': 320, 'height': 200, 'source': 'last_completed_guest_frame'}}
    states = []
    for room, x, y in ((39, 85, 100), (39, 72, 88), (39, 10, 87), (40, 151, 87)):
        states.append({'room': room, 'score': 0, 'ego': {'x': x, 'y': y, 'direction': 0, 'drawn': True},
            'ego_width': 6, 'ego_view': 0, 'step_size': 1, 'in_water': False, 'swimming': 0,
            'dead': False, 'bridge_active': False, 'troll_removed': False, 'troll_paid': False})
    observations = {f'o{index}': {'state': state, 'frame': frame(index)} for index, state in enumerate(states)}
    observations['o3']['frame']['metadata']['frame_id'] = 6
    inputs = [{'kind': 'keyboard', 'key': 'press:left', 'delivered': True, 'complete': True,
               'delivery': {'accepted': True, 'delivery': 'queued'}}]
    actions = [{'id': name, 'before': f'o{index}', 'after': f'o{index+1}', 'complete': True,
                'messages_complete': True, 'inputs': deepcopy(inputs), 'messages': []}
               for index, name in enumerate(('approach-corner', 'cross-gap', 'leave-bridge'))]
    actions[-1]['messages'] = [{'logic': 40, 'source_offset': 175, 'message_id': 1, 'status': 'completed',
        'mode': 'blocking', 'native_execution': True, 'native_execution_attempted': True, 'input_attempted': True,
        'handler_return_observed': True, 'input_settled': True, 'window_closed': True,
        'identity': {'resource_sha256': resources['40']},
        'message': {'resource_sha256': resources['40'], 'message_id': 1,
                    'text_sha256': sha256(text[:-1]).hexdigest(), 'length': len(text)-1},
        'input': {'accepted': True}, 'keyboard_after': {'keyboard': {'pending_events': 0, 'owned_keys': 0, 'queued_guest_ms': 0}},
        'frame': frame(4)}]
    trace = {'format': 'fdisbull-agi-posn-trace-1', 'maximum_count': 128,
             'runs': [{'outcome': 'breakpoint', 'guest_elapsed_ms': 0}],
             'events': [{'sequence': index+1, 'instruction_completed': None} for index in range(52)], 'complete': True}
    proof = {'format': 'fdisbull-agi-posn-observation-1', 'status': 'verified', 'complete': True,
             'native_execution': True, 'source_logic': 39, 'source_logic_sha256': resources['39'],
             'condition_offset': 0x410, 'arguments': [0, 72, 84, 72, 87], 'result': False,
             'input_position': {'x': 72, 'y': 88, 'width': 6}, 'handler_entry_offset': 0x8c6,
             'return_offset': 0x7fb, 'call_frame_verified': True, 'handler_return_observed': True,
             'false_continuation_observed': True, 'continuation_source_offset': 0x41e}
    capture = {'format': 'fdisbull-agi-bridge-clip-capture-1',
               'source': {'agi_sha256': sha256((source / 'AGI').read_bytes()).hexdigest(), 'resources': resources},
               'picture': {'room': 39, 'sha256': sha256(picture).hexdigest()},
               'runtime': {'policy': 'physical', 'fresh_game': True, 'interventions': []},
               'observations': observations, 'actions': actions}
    def loader():
        trace_raw = json.dumps(trace).encode(); artifacts['trace.json'] = trace_raw
        proof['trace'] = {'path': 'trace.json', 'sha256': sha256(trace_raw).hexdigest(),
                          'event_count': 52, 'maximum_count': 128}
        proof_raw = json.dumps(proof).encode(); artifacts['proof.json'] = proof_raw
        actions[1]['native_predicate'] = {'path': 'proof.json', 'sha256': sha256(proof_raw).hexdigest()}
        return lambda path: artifacts[path]
    return source, capture, proof, trace, loader, artifacts


def test_clip_player_route_and_in_memory_checkpoint(tmp_path):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    scene, evidence = exporter.build(source, capture, loader())
    backend = ILSceneBackend(scene); player = Player(backend)
    assert 'partial' in player.execute('look').lower()
    assert 'no action sent' in player.execute('use gap').lower()
    assert player.execute('use corner').startswith('Success:')
    before = backend.observe()['context']['token']
    assert backend.save('corner')['status'] == 'saved'
    assert player.execute('use gap').startswith('Success:')
    assert backend.state['$x'] == 10 and backend.state['$y'] == 87
    assert backend.act({'verb': 'use', 'target': 'gap', 'item': None, 'context_token': before})['status'] == 'rejected'
    assert 'no action sent' in player.execute('use gap').lower()
    assert backend.load('corner')['status'] == 'restored'
    assert backend.observe()['context']['token'] != before
    assert backend.act({'verb': 'use', 'target': 'gap', 'item': None, 'context_token': before})['status'] == 'rejected'
    assert player.execute('use gap').startswith('Success:')
    assert player.execute('use route').startswith('Success:')
    assert backend.state['$phase'] == 3 and backend.state['$room'] == 40 and backend.state['$x'] == 151
    assert backend.state['$score'] == 0 and not backend.state['$in_water'] and not backend.state['$troll_removed']
    assert 'no action sent' in player.execute('use route').lower()
    assert ILSceneBackend(scene).load('corner')['status'] == 'missing'
    assert evidence['edges'][1]['native_predicate']['trace']['event_count'] == 52
    assert evidence['edges'][2]['messages'][0]['resource_sha256'] == capture['source']['resources']['40']
    assert 'Authored final-room notice.' not in str(scene) and 'Authored final-room notice.' not in str(evidence)
    assert all('path' not in item for item in evidence['observations'].values())


def test_layout_notice_discovers_dry_bottom_seam_without_changing_actions(tmp_path):
    source, capture, _, _, loader, _ = fixture(tmp_path)
    baseline, _ = exporter.build(source, capture, loader())
    # Authored priority-only water stripe at y166; y167 remains ordinary dry.
    picture = bytes((0xf2, 3, 0xf6, 5, 166, 91, 166, 0xff))
    volume = source/'VOL.0'; offset = volume.stat().st_size
    with volume.open('ab') as stream:
        stream.write(b'\x12\x34\0'+len(picture).to_bytes(2, 'little')+picture)
    directory = bytearray((source/'PICDIR').read_bytes())
    directory[39*3:39*3+3] = offset.to_bytes(3, 'big')
    (source/'PICDIR').write_bytes(directory)
    capture['picture']['sha256'] = sha256(picture).hexdigest()
    scene, evidence = exporter.build(source, capture, loader())
    assert scene['programs'] == baseline['programs']
    assert len(scene['objects']) == len(baseline['objects']) == 3
    bottom = [value for value in evidence['edge_seams']['candidates'] if value['edge'] == 'bottom']
    assert len(bottom) == 82 and {value['y'] for value in bottom} == {167}
    assert {value['x'] for value in bottom} == set(range(5, 87))
    assert 'walking routes remain unqualified' in scene['contexts'][1]['description']
    assert 'walking routes remain unqualified' in scene['objects'][1]['description']
    assert evidence['coordinate_domains']['objects'][0]['render'] is None
    collision = next(value for value in evidence['layout_audit']['relations']
                     if value['part'] == 'collision' and value['domain'] == 'room')
    assert collision['relation'] == 'contained' and collision['absolute_bounds'] == [85, 100, 91, 101]


@pytest.mark.parametrize('observation', ['o0', 'o1', 'o2', 'o3'])
@pytest.mark.parametrize('field, value', [('score', 1), ('ego_width', 3), ('ego_view', 93), ('step_size', 2),
    ('in_water', True), ('swimming', 1), ('dead', True), ('bridge_active', True), ('troll_removed', True), ('troll_paid', True)])
def test_unsafe_or_changed_state_refuses(tmp_path, observation, field, value):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    capture['observations'][observation]['state'][field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('observation', ['o0', 'o1', 'o2', 'o3'])
def test_snapshot_direction_must_be_neutral(tmp_path, observation):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    capture['observations'][observation]['state']['ego']['direction'] = 1
    with pytest.raises(ValueError, match='geometry or direction'): exporter.build(source, capture, loader())


@pytest.mark.parametrize('observation, field, value', [('o0', 'x', 84), ('o0', 'y', 99), ('o1', 'x', 73),
    ('o1', 'y', 87), ('o2', 'x', 11), ('o2', 'y', 88), ('o3', 'x', 148), ('o3', 'x', 155)])
def test_exact_waypoints_and_exit_range_are_qualified(tmp_path, observation, field, value):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    capture['observations'][observation]['state']['ego'][field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('field, value', [('format', 'other'), ('status', 'incomplete'), ('complete', False),
    ('native_execution', False), ('source_logic', 40), ('source_logic_sha256', '0'*64), ('condition_offset', 0x411),
    ('arguments', [0, 72, 84, 72, 88]), ('result', True), ('handler_entry_offset', 0x8c7), ('return_offset', 0x7fc),
    ('call_frame_verified', False), ('handler_return_observed', False), ('false_continuation_observed', False),
    ('continuation_source_offset', 0x41a), ('input_position', {'x': 72, 'y': 87, 'width': 6})])
def test_predicate_requires_original_site_and_observed_false_continuation(tmp_path, field, value):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    proof[field] = value
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['format', 'complete', 'maximum', 'empty', 'count', 'exhausted', 'runs'])
def test_raw_trace_must_be_complete_and_match_actual_count_within_limit(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    if fault == 'format': trace['format'] = 'other'
    if fault == 'complete': trace['complete'] = False
    if fault == 'maximum': trace['maximum_count'] = 127
    if fault == 'empty': trace['events'] = []
    if fault == 'count': trace['events'].pop()
    if fault == 'exhausted': trace['events'] *= 3
    if fault == 'runs': trace['runs'] = []
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('index, count', [(0, 1), (1, 1), (2, 0), (2, 2)])
def test_only_one_original_final_room_message_is_admitted(tmp_path, index, count):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    message = capture['actions'][2]['messages'][0]
    capture['actions'][index]['messages'] = [deepcopy(message) for _ in range(count)]
    with pytest.raises(ValueError, match='dialogue count'): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['logic', 'offset', 'id', 'return', 'input', 'window', 'cleanup', 'frame'])
def test_final_room_message_must_be_source_bound_and_complete(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    message = capture['actions'][2]['messages'][0]
    if fault == 'logic': message['logic'] = 39
    if fault == 'offset': message['source_offset'] = 176
    if fault == 'id': message['message_id'] = 2
    if fault == 'return': message['handler_return_observed'] = False
    if fault == 'input': message['input_settled'] = False
    if fault == 'window': message['window_closed'] = False
    if fault == 'cleanup': message['cleanup_errors'] = [{'error': 'authored cleanup failure'}]
    if fault == 'frame': message['frame']['sha256'] = '0'*64
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['engine', 'missing39', 'missing40', 'logic-hash', 'picture-room', 'picture-hash', 'picture-bytes'])
def test_source_and_full_picture_identities_are_required(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    if fault == 'engine': (source / 'AGI').write_bytes(b'changed authored engine')
    if fault == 'missing39': del capture['source']['resources']['39']
    if fault == 'missing40': del capture['source']['resources']['40']
    if fault == 'logic-hash': capture['source']['resources']['39'] = '0'*64
    if fault == 'picture-room': capture['picture']['room'] = 40
    if fault == 'picture-hash': capture['picture']['sha256'] = '0'*64
    if fault == 'picture-bytes':
        raw = bytearray((source / 'VOL.0').read_bytes()); raw[-1] = 0xf0; (source / 'VOL.0').write_bytes(raw)
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


def replace_code(source, number, code):
    resource = load_logic(source / 'LOGDIR', source, number, profile='2.917')
    assert len(code) == len(resource.code)
    raw = bytearray((source / 'VOL.0').read_bytes())
    raw[resource.code_offset:resource.code_offset+len(code)] = code
    (source / 'VOL.0').write_bytes(raw)
    return load_logic(source / 'LOGDIR', source, number, profile='2.917').resource_sha256


@pytest.mark.parametrize('fault', ['arguments', 'not-condition', 'negated', 'false-successor'])
def test_posn_bytes_must_be_a_regular_condition_with_the_declared_false_edge(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    code = bytearray(load_logic(source / 'LOGDIR', source, 39, profile='2.917').code)
    if fault == 'arguments': code[0x415] = 88
    if fault == 'not-condition':
        code = bytearray(len(code)); code[0x410:0x416] = bytes.fromhex('0b0048544857')
    if fault == 'negated':
        code = bytearray(len(code)); code[0x40e:0x419] = bytes.fromhex('fffd0b0048544857ff0000')
    if fault == 'false-successor': code[0x418] = 5
    identity = replace_code(source, 39, code)
    capture['source']['resources']['39'] = identity; proof['source_logic_sha256'] = identity
    with pytest.raises(ValueError, match='source condition witness|source false successor'):
        exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['instruction', 'source-message'])
def test_final_message_identity_does_not_replace_source_instruction_and_text_binding(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    resource = load_logic(source / 'LOGDIR', source, 40, profile='2.917')
    if fault == 'instruction':
        code = bytearray(resource.code); code[175] = 100
        identity = replace_code(source, 40, code)
    else:
        raw = bytearray((source / 'VOL.0').read_bytes())
        raw[resource.code_offset+len(resource.code)] = 0
        (source / 'VOL.0').write_bytes(raw)
        identity = load_logic(source / 'LOGDIR', source, 40, profile='2.917').resource_sha256
    capture['source']['resources']['40'] = identity
    with pytest.raises(ValueError, match='print source|source message'): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['policy', 'fresh', 'intervention', 'order', 'disconnected', 'action-incomplete',
    'messages-incomplete', 'input-kind', 'input-delivered', 'input-complete', 'input-accepted', 'input-receipt'])
def test_runtime_continuity_and_input_boundaries_are_required(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    if fault == 'policy': capture['runtime']['policy'] = 'assisted'
    if fault == 'fresh': capture['runtime']['fresh_game'] = False
    if fault == 'intervention': capture['runtime']['interventions'] = ['authored placement']
    if fault == 'order': capture['actions'].reverse()
    if fault == 'disconnected': capture['actions'][1]['before'] = 'o0'
    if fault == 'action-incomplete': capture['actions'][0]['complete'] = False
    if fault == 'messages-incomplete': capture['actions'][0]['messages_complete'] = False
    item = capture['actions'][0]['inputs'][0]
    if fault == 'input-kind': item['kind'] = 'mouse'
    if fault == 'input-delivered': item['delivered'] = False
    if fault == 'input-complete': item['complete'] = False
    if fault == 'input-accepted': item['delivery']['accepted'] = False
    if fault == 'input-receipt': del item['delivery']
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['frame-hash', 'frame-source', 'frame-mode', 'frame-dimensions', 'proof-hash', 'trace-hash',
                                  'trace-count-zero', 'trace-count-limit', 'trace-limit', 'argument-type'])
def test_artifact_and_metadata_contradictions_refuse(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    load = loader()
    frame = capture['observations']['o1']['frame']
    if fault == 'frame-hash': frame['sha256'] = '0'*64
    if fault == 'frame-source': frame['metadata']['source'] = 'unqualified frame'
    if fault == 'frame-mode': frame['metadata']['mode_id'] = True
    if fault == 'frame-dimensions': frame['metadata']['width'] = 0
    if fault == 'proof-hash': capture['actions'][1]['native_predicate']['sha256'] = '0'*64
    if fault == 'trace-hash': proof['trace']['sha256'] = '0'*64
    if fault == 'trace-count-zero': proof['trace']['event_count'] = 0
    if fault == 'trace-count-limit': proof['trace']['event_count'] = 128
    if fault == 'trace-limit': proof['trace']['maximum_count'] = 127
    if fault == 'argument-type': proof['arguments'][0] = False
    if fault in ('trace-hash', 'trace-count-zero', 'trace-count-limit', 'trace-limit', 'argument-type'):
        raw = json.dumps(proof).encode(); artifacts['proof.json'] = raw
        capture['actions'][1]['native_predicate']['sha256'] = sha256(raw).hexdigest()
    with pytest.raises(ValueError): exporter.build(source, capture, load)


def cli_fixture(tmp_path):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    loader()
    root = tmp_path / 'artifacts'; root.mkdir()
    for path, raw in artifacts.items(): (root / path).write_bytes(raw)
    capture_path = tmp_path / 'capture.json'; capture_path.write_text(json.dumps(capture))
    return source, root, capture_path


def test_cli_exports_only_authored_scene_and_hash_bound_provenance(tmp_path, monkeypatch, capsys):
    source, root, capture_path = cli_fixture(tmp_path); output = tmp_path / 'export'
    monkeypatch.setattr(sys, 'argv', ['build_clip_scene', '--source', str(source), '--capture', str(capture_path),
        '--artifacts', str(root), '--output', str(output)])
    exporter.main()
    result = json.loads(capsys.readouterr().out)
    scene_raw = (output / 'scene.json').read_bytes()
    assert result['scene'] == str(output / 'scene.json')
    assert json.loads((output / 'provenance.json').read_bytes())['scene_sha256'] == sha256(scene_raw).hexdigest()
    assert b'Authored final-room notice.' not in scene_raw


@pytest.mark.parametrize('destination', ['source', 'artifacts', 'existing'])
def test_cli_refuses_nonprivate_or_existing_output_without_changing_inputs(tmp_path, monkeypatch, destination):
    source, root, capture_path = cli_fixture(tmp_path)
    previous = tmp_path / 'existing'; previous.mkdir(); (previous / 'sealed').write_bytes(b'preserve this authored receipt')
    output = {'source': source / 'new', 'artifacts': root / 'new', 'existing': previous}[destination]
    before = {str(path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    monkeypatch.setattr(sys, 'argv', ['build_clip_scene', '--source', str(source), '--capture', str(capture_path),
        '--artifacts', str(root), '--output', str(output)])
    with pytest.raises(ValueError, match='fresh private'): exporter.main()
    assert {str(path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_cli_confines_artifact_reads_to_the_supplied_private_root(tmp_path, monkeypatch):
    source, root, capture_path = cli_fixture(tmp_path)
    capture = json.loads(capture_path.read_text())
    outside = tmp_path / 'outside-frame'; outside.write_bytes(b'outside authored artifact')
    capture['observations']['o0']['frame'].update(path='../outside-frame', sha256=sha256(outside.read_bytes()).hexdigest())
    capture_path.write_text(json.dumps(capture)); output = tmp_path / 'export'
    monkeypatch.setattr(sys, 'argv', ['build_clip_scene', '--source', str(source), '--capture', str(capture_path),
        '--artifacts', str(root), '--output', str(output)])
    with pytest.raises(ValueError, match='artifact path outside'): exporter.main()
    assert not output.exists()


@pytest.mark.parametrize('field', ['native_execution', 'native_execution_attempted', 'input_attempted', 'identity',
                                  'message', 'input', 'keyboard_after'])
def test_final_print_requires_native_execution_identity_and_input_receipts(tmp_path, field):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    del capture['actions'][2]['messages'][0][field]
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('fault', ['execution', 'execution-attempt', 'identity-hash', 'message-hash',
    'message-id', 'text-hash', 'text-length', 'accepted', 'pending', 'owned', 'queued', 'counter-type'])
def test_final_print_native_metadata_and_physical_input_must_be_consistent(tmp_path, fault):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    message = capture['actions'][2]['messages'][0]
    if fault == 'execution': message['native_execution'] = False
    if fault == 'execution-attempt': message['native_execution_attempted'] = False
    if fault == 'identity-hash': message['identity']['resource_sha256'] = '0'*64
    if fault == 'message-hash': message['message']['resource_sha256'] = '0'*64
    if fault == 'message-id': message['message']['message_id'] = 2
    if fault == 'text-hash': message['message']['text_sha256'] = '0'*64
    if fault == 'text-length': message['message']['length'] += 1
    if fault == 'accepted': message['input']['accepted'] = False
    if fault == 'pending': message['keyboard_after']['keyboard']['pending_events'] = 1
    if fault == 'owned': message['keyboard_after']['keyboard']['owned_keys'] = 1
    if fault == 'queued': message['keyboard_after']['keyboard']['queued_guest_ms'] = 1
    if fault == 'counter-type': message['keyboard_after']['keyboard']['owned_keys'] = False
    with pytest.raises(ValueError): exporter.build(source, capture, loader())


@pytest.mark.parametrize('observation, frame_id', [('o1', 1), ('o2', 1), ('o3', 3)])
def test_completed_observation_frames_must_follow_route_order(tmp_path, observation, frame_id):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    capture['observations'][observation]['frame']['metadata']['frame_id'] = frame_id
    with pytest.raises(ValueError, match='frames are not ordered'): exporter.build(source, capture, loader())


@pytest.mark.parametrize('frame_id', [3, 6])
def test_final_print_frame_must_be_between_its_before_and_after_snapshots(tmp_path, frame_id):
    source, capture, proof, trace, loader, artifacts = fixture(tmp_path)
    capture['actions'][2]['messages'][0]['frame']['metadata']['frame_id'] = frame_id
    with pytest.raises(ValueError, match='message frame lies outside'): exporter.build(source, capture, loader())
