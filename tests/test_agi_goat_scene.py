"""Portable, authored capture fixtures; not evidence of original gameplay."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import examples.agi.build_goat_scene as exporter
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player


def fixture(tmp_path, monkeypatch):
    (tmp_path / 'AGI').write_bytes(b'synthetic engine')
    raw = b'authored-frame'
    code = bytearray(460); code[450:452] = bytes([101, 1])
    resource = SimpleNamespace(resource_sha256='a' * 64, code=bytes(code))
    monkeypatch.setattr(exporter, 'load_logic', lambda *args, **kwargs: resource)
    monkeypatch.setattr(exporter, 'logic_messages', lambda r: {r.resource_sha256: {'1': 'Authored fixture message.'}})
    def frame(n):
        return {'path': 'frame', 'sha256': sha256(raw).hexdigest(),
                'metadata': {'frame_id': n, 'mode_id': 5, 'width': 320, 'height': 200, 'source': 'last_completed_guest_frame'}}
    states = [dict(room=11, score=20, carrot=True, following=False, gate_open=True),
              dict(room=11, score=25, carrot=True, following=True, gate_open=True),
              dict(room=12, score=25, carrot=True, following=True, gate_open=True)]
    obs = {f'o{i}': {'state': state, 'goat_visible': True, 'frame': frame(i)} for i, state in enumerate(states)}
    input_record = {'kind': 'keyboard', 'key': 'type:show carrot', 'delivered': True, 'complete': True}
    message = {'logic': 103, 'source_offset': 450, 'message_id': 1, 'status': 'completed',
               'handler_return_observed': True, 'input_settled': True, 'window_closed': True, 'frame': frame(2)}
    actions = [{'id': 'show-carrot', 'label': 'show carrot', 'verb': 'show', 'before': 'o0', 'after': 'o1',
                'complete': True, 'messages_complete': True, 'inputs': [input_record], 'messages': [message]},
               {'id': 'lead-to-water', 'label': 'lead', 'verb': 'go', 'before': 'o1', 'after': 'o2',
                'complete': True, 'messages_complete': True, 'inputs': [input_record], 'messages': []}]
    capture = {'format': 'fdisbull-agi-natural-encounter-1',
               'source': {'agi_sha256': sha256(b'synthetic engine').hexdigest(), 'resources': {'103': 'a' * 64}},
               'runtime': {'policy': 'physical', 'fresh_game': True, 'interventions': []},
               'observations': obs, 'actions': actions}
    return capture, lambda _: raw


def test_player_bounded_route_and_checkpoint(tmp_path, monkeypatch):
    capture, loader = fixture(tmp_path, monkeypatch)
    scene, evidence = exporter.build(tmp_path, capture, loader)
    backend = ILSceneBackend(scene); player = Player(backend)
    old = backend.observe()['context']['token']
    assert 'partial' in player.execute('look').lower()
    assert 'fixture message' in player.execute('use carrot on goat')
    assert backend.state['$score'] == 25 and backend.state['$following'] is True
    assert backend.act({'verb': 'use', 'target': 'goat', 'item': 'carrot', 'context_token': old})['status'] == 'rejected'
    assert 'no action sent' in player.execute('use carrot on goat').lower()
    assert backend.save('first')['status'] == 'saved'
    assert player.execute('use route').startswith('Success:')
    assert backend.state['$room'] == 12
    assert 'no action sent' in player.execute('use route').lower()
    assert backend.load('first')['status'] == 'restored'
    assert player.execute('use route').startswith('Success:')
    assert evidence['edges'][0]['messages'] == [{'logic': 103, 'source_offset': 450, 'message_id': 1}]
    assert 'fixture message' not in str(evidence)


@pytest.mark.parametrize('fault', ['frame', 'state', 'visibility', 'intervention', 'unsettled', 'not_completed',
                                    'input', 'no_message_capture', 'source', 'offset', 'disconnected', 'no_frame_metadata', 'wrong_frame_source'])
def test_missing_or_unqualified_evidence_refuses_export(tmp_path, monkeypatch, fault):
    capture, loader = fixture(tmp_path, monkeypatch)
    if fault == 'frame': capture['observations']['o0']['frame']['sha256'] = '0' * 64
    if fault == 'state': del capture['observations']['o0']['state']['following']
    if fault == 'visibility': capture['observations']['o0']['goat_visible'] = False
    if fault == 'intervention': capture['runtime']['interventions'] = ['state edit']
    if fault == 'unsettled': capture['actions'][0]['messages'][0]['input_settled'] = False
    if fault == 'not_completed': capture['actions'][0]['complete'] = False
    if fault == 'input': capture['actions'][0]['inputs'][0]['delivered'] = False
    if fault == 'no_message_capture': del capture['actions'][0]['messages_complete']
    if fault == 'source': capture['source']['resources']['103'] = '0' * 64
    if fault == 'offset': capture['actions'][0]['messages'][0]['source_offset'] = 451
    if fault == 'disconnected': capture['actions'][1]['before'] = 'o0'
    if fault == 'no_frame_metadata': del capture['observations']['o0']['frame']['metadata']['mode_id']
    if fault == 'wrong_frame_source': capture['observations']['o0']['frame']['metadata']['source'] = 'other'
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, loader)


def test_single_observed_edge_does_not_invent_route(tmp_path, monkeypatch):
    capture, loader = fixture(tmp_path, monkeypatch)
    capture['actions'] = capture['actions'][:1]
    scene, _ = exporter.build(tmp_path, capture, loader)
    backend = ILSceneBackend(scene); player = Player(backend)
    assert player.execute('use carrot on goat').startswith('Success:')
    assert 'no action sent' in player.execute('use route').lower()
    assert backend.observe()['coverage']['partial'] is True


def leave_fixture(tmp_path, monkeypatch):
    capture, frame_loader = fixture(tmp_path, monkeypatch)
    action = capture['actions'][1]
    action['id'] = 'leave-pen'
    trial = {'format': 'fdisbull-agi-original-host-trial-1', 'status': 'verified',
             'complete': True, 'native_execution': True, 'differences': [],
             'identity': {'resource_sha256': 'a' * 64}, 'source_offsets': [452]}
    def bind(t):
        raw = json.dumps(t).encode()
        action['native_invocation'] = {'path': 'invocation.json', 'sha256': sha256(raw).hexdigest()}
        return lambda path: raw if path == 'invocation.json' else frame_loader(path)
    return capture, trial, bind


def test_leave_pen_requires_native_invocation_and_retains_following(tmp_path, monkeypatch):
    capture, trial, bind = leave_fixture(tmp_path, monkeypatch)
    scene, evidence = exporter.build(tmp_path, capture, bind(trial))
    player = Player(ILSceneBackend(scene))
    assert player.execute('use carrot on goat').startswith('Success:')
    assert player.execute('use route').startswith('Success:')
    assert player.backend.state['$room'] == 12
    assert player.backend.state['$following'] is True and player.backend.state['$score'] == 25
    assert evidence['edges'][1]['native_invocation']['sha256'] == capture['actions'][1]['native_invocation']['sha256']
    assert evidence['edges'][1]['native_invocation']['source_offsets'] == [452]


@pytest.mark.parametrize('count',[0,2])
def test_native_print_occurrences_cannot_be_missing_or_duplicated(tmp_path,monkeypatch,count):
    capture,trial,bind=leave_fixture(tmp_path,monkeypatch)
    trial['source_offsets']=[450,452]
    capture['actions'][1]['messages']=[deepcopy(capture['actions'][0]['messages'][0]) for _ in range(count)]
    with pytest.raises(ValueError,match='count or identity'):
        exporter.build(tmp_path,capture,bind(trial))


@pytest.mark.parametrize('fault', ['missing', 'hash', 'format', 'incomplete', 'differences', 'identity', 'no_path', 'call', 'no_return', 'outside', 'lost_follow', 'lost_carrot', 'score'])
def test_leave_pen_rejects_unqualified_native_or_state(tmp_path, monkeypatch, fault):
    capture, trial, bind = leave_fixture(tmp_path, monkeypatch)
    if fault == 'format': trial['format'] = 'other'
    if fault == 'incomplete': trial['complete'] = False
    if fault == 'differences': trial['differences'] = ['difference']
    if fault == 'identity': trial['identity']['resource_sha256'] = 'b' * 64
    if fault == 'no_path': trial['source_offsets'] = []
    if fault == 'no_return': trial['source_offsets'] = [450]
    if fault == 'outside': capture['observations']['o2']['state']['room'] = 10
    if fault == 'lost_follow': capture['observations']['o2']['state']['following'] = False
    if fault == 'lost_carrot': capture['observations']['o2']['state']['carrot'] = False
    if fault == 'score': capture['observations']['o2']['state']['score'] += 1
    if fault == 'call':
        code = bytearray(460); code[10] = 22; code[452] = 0
        resource = SimpleNamespace(resource_sha256='a' * 64, code=bytes(code))
        monkeypatch.setattr(exporter, 'load_logic', lambda *args, **kwargs: resource)
        capture['actions'][0]['messages'] = []
        trial['source_offsets'] = [10, 452]
    loader = bind(trial)
    if fault == 'missing': del capture['actions'][1]['native_invocation']
    if fault == 'hash': capture['actions'][1]['native_invocation']['sha256'] = '0' * 64
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, loader)


def bridge_fixture(tmp_path, monkeypatch):
    capture, trial, bind = leave_fixture(tmp_path, monkeypatch)
    base_loader = bind(trial)
    goat_code = bytearray(460); goat_code[450:452] = bytes([101, 1])
    bridge_code = bytearray(460)
    for offset, number in ((0x14c, 1), (0x16a, 2), (0x19f, 30)):
        bridge_code[offset:offset+2] = bytes([101, number])
    bridge_code[0x1b8:0x1bb] = bytes([5, 3, 4])
    resources = {103: SimpleNamespace(resource_sha256='a' * 64, code=bytes(goat_code)),
                 25: SimpleNamespace(resource_sha256='b' * 64, code=bytes(bridge_code))}
    monkeypatch.setattr(exporter, 'load_logic', lambda _directory, _source, number, **kwargs: resources[number])
    monkeypatch.setattr(exporter, 'logic_messages', lambda r: {r.resource_sha256: {
        '1': 'Authored first message.', '2': 'Authored second message.', '30': 'Authored final message.'}})
    capture['source']['resources']['25'] = 'b' * 64
    for index, observation in enumerate(capture['observations'].values()):
        observation['state'].update(score=2 if index == 0 else 7,
                                    carrot_carried=True, troll_removed=False, troll_paid=False)
    capture['observations']['o2']['state']['room'] = 9
    final = deepcopy(capture['observations']['o2'])
    final['state'].update(room=25, score=11, following=False, troll_removed=True)
    final.update(goat_visible=False, troll_visible=False)
    final['frame']['metadata']['frame_id'] = 6
    # A drawn flag is a separate observation and is not used as frame visibility.
    final['native_state'] = {'goat': {'drawn': False}, 'troll': {'drawn': False}}
    capture['observations']['o3'] = final
    messages = []
    for index, (offset, number) in enumerate(((0x14c, 1), (0x16a, 2), (0x19f, 30))):
        message = deepcopy(capture['actions'][0]['messages'][0])
        message.update(logic=25, source_offset=offset, message_id=number)
        message['frame']['metadata']['frame_id'] = 3 + index
        messages.append(message)
    trace = b'authored native trace fixture\n'
    proof = {'format': 'fdisbull-agi-troll-score-write-1', 'status': 'verified',
             'complete': True, 'native_execution': True, 'source_logic_sha256': 'b' * 64,
             'source_offset': 0x1b8, 'before_score': 7, 'after_score': 11,
             'writer': {'source_offset': 0x72da, 'resume_offset': 0x72de, 'bx': 3, 'al': 4},
             'trace': {'path': 'score.trace', 'sha256': sha256(trace).hexdigest(), 'count': 32}}
    action = {'id': 'troll-bridge', 'label': 'lead the goat to the bridge', 'verb': 'use',
              'before': 'o2', 'after': 'o3', 'complete': True, 'messages_complete': True,
              'inputs': [deepcopy(capture['actions'][1]['inputs'][0])], 'messages': messages}
    capture['actions'].append(action)
    def load(p=proof, t=trace):
        raw = json.dumps(p).encode()
        action['native_score_write'] = {'path': 'score.json', 'sha256': sha256(raw).hexdigest()}
        return lambda path: raw if path == 'score.json' else t if path == 'score.trace' else base_loader(path)
    return capture, proof, load


def test_bridge_player_contiguous_route_and_checkpoint(tmp_path, monkeypatch):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    scene, evidence = exporter.build(tmp_path, capture, load())
    backend = ILSceneBackend(scene); player = Player(backend)
    assert 'no action sent' in player.execute('use bridge').lower()
    assert player.execute('use carrot on goat').startswith('Success:')
    assert player.execute('use route').startswith('Success:')
    old = backend.observe()['context']['token']
    assert backend.save('before-bridge')['status'] == 'saved'
    assert 'Authored final message.' in player.execute('use bridge')
    assert backend.state['$phase'] == 3 and backend.state['$room'] == 25
    assert backend.state['$score'] == 11 and backend.state['$following'] is False
    assert backend.state['$carrot'] is True and backend.state['$carrot_carried'] is True
    assert backend.state['$troll_removed'] is True and backend.state['$troll_paid'] is False
    assert 'bridge cleared' in player.execute('look').lower()
    assert backend.act({'verb': 'use', 'target': 'bridge', 'item': None, 'context_token': old})['status'] == 'rejected'
    assert 'no action sent' in player.execute('use bridge').lower()
    assert backend.load('before-bridge')['status'] == 'restored'
    assert player.execute('use bridge').startswith('Success:')
    assert evidence['edges'][2]['native_score_write']['sha256'] == capture['actions'][2]['native_score_write']['sha256']
    assert evidence['edges'][2]['native_score_write']['trace']['count'] == 32
    assert 'Authored final message.' not in str(evidence)


@pytest.mark.parametrize('count, expected', [
    (1, '7c1c04d438d4d1979d36b2d1f4e26e0743ac39610800b34513b92460667e9f86'),
    (2, '3fe7fe5f51efb22e1b9315d00d6b2ff082463cd9c3f799902b3cffeb28d6adba'),
])
def test_existing_scene_export_bytes_unchanged(tmp_path, monkeypatch, count, expected):
    capture, loader = fixture(tmp_path, monkeypatch)
    capture['actions'] = capture['actions'][:count]
    scene, _ = exporter.build(tmp_path, capture, loader)
    raw = (json.dumps(scene, ensure_ascii=False, indent=2) + '\n').encode()
    assert sha256(raw).hexdigest() == expected


@pytest.mark.parametrize('observation', ['o0', 'o1', 'o2', 'o3'])
@pytest.mark.parametrize('field', ['carrot_carried', 'troll_removed', 'troll_paid'])
def test_bridge_requires_extended_state_on_every_used_observation(tmp_path, monkeypatch, observation, field):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    del capture['observations'][observation]['state'][field]
    with pytest.raises(ValueError, match='bridge observed state'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('observation, field, value', [
    ('o2', 'room', 12), ('o2', 'score', 8), ('o2', 'following', False),
    ('o2', 'carrot', False), ('o2', 'carrot_carried', False),
    ('o2', 'troll_removed', True), ('o2', 'troll_paid', True),
    ('o3', 'room', 9), ('o3', 'score', 12), ('o3', 'following', True),
    ('o3', 'carrot', False), ('o3', 'carrot_carried', False),
    ('o3', 'troll_removed', False), ('o3', 'troll_paid', True),
    ('o0', 'carrot_carried', 1),
])
def test_bridge_refuses_other_state_outcomes(tmp_path, monkeypatch, observation, field, value):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    capture['observations'][observation]['state'][field] = value
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('field, value', [('goat_visible', None), ('goat_visible', True),
                                         ('troll_visible', None), ('troll_visible', True)])
def test_bridge_drawn_flags_do_not_qualify_frame_absence(tmp_path, monkeypatch, field, value):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    capture['observations']['o3'][field] = value
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


def test_bridge_frame_visibility_is_separate_from_later_actor_flags(tmp_path, monkeypatch):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    capture['observations']['o3']['native_state'] = {'goat': {'drawn': True}, 'troll': {'drawn': True}}
    scene, _ = exporter.build(tmp_path, capture, load())
    assert scene['contexts'][-1]['title'] == 'Observed bridge cleared'


@pytest.mark.parametrize('fault', ['disconnected', 'second-action', 'third-action', 'missing-logic', 'extra-action',
                                  'missing-proof', 'proof-hash', 'score-instruction', 'missing-frame'])
def test_bridge_capture_contract_failures(tmp_path, monkeypatch, fault):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    if fault == 'disconnected': capture['actions'][2]['before'] = 'o1'
    if fault == 'second-action': capture['actions'][1]['id'] = 'lead-to-water'
    if fault == 'third-action': capture['actions'][2]['id'] = 'wander-away'
    if fault == 'missing-logic': del capture['source']['resources']['25']
    if fault == 'extra-action': capture['actions'].append(deepcopy(capture['actions'][2]))
    if fault == 'score-instruction':
        original = exporter.load_logic
        def changed(*args, **kwargs):
            resource = original(*args, **kwargs)
            if args[2] != 25: return resource
            code = bytearray(resource.code); code[0x1ba] = 5
            return SimpleNamespace(resource_sha256=resource.resource_sha256, code=bytes(code))
        monkeypatch.setattr(exporter, 'load_logic', changed)
    if fault == 'missing-frame': del capture['actions'][2]['messages'][0]['frame']
    loader = load()
    if fault == 'missing-proof': del capture['actions'][2]['native_score_write']
    if fault == 'proof-hash': capture['actions'][2]['native_score_write']['sha256'] = '0' * 64
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, loader)


@pytest.mark.parametrize('field, value', [('format', 'other'), ('status', 'incomplete'), ('complete', False),
                                        ('native_execution', False), ('source_logic_sha256', 'c' * 64),
                                        ('source_offset', 0x1b9), ('before_score', 6), ('after_score', 12)])
def test_bridge_score_write_must_match_source_and_observed_scores(tmp_path, monkeypatch, field, value):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    proof[field] = value
    with pytest.raises(ValueError, match='score write not qualified'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('field, value', [('source_offset', 0x72db), ('resume_offset', 0x72df),
                                        ('bx', 4), ('al', 5), ('bx', True)])
def test_bridge_native_score_writer_must_match(tmp_path, monkeypatch, field, value):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    proof['writer'][field] = value
    with pytest.raises(ValueError, match='native writer differs'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('fault', ['missing', 'count', 'hash', 'bytes', 'path'])
def test_bridge_score_trace_is_bound_to_supplied_bytes(tmp_path, monkeypatch, fault):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    if fault == 'missing': del proof['trace']
    if fault == 'count': proof['trace']['count'] = 31
    if fault == 'hash': proof['trace']['sha256'] = '0' * 64
    if fault == 'path': del proof['trace']['path']
    loader = load(t=b'changed trace') if fault == 'bytes' else load()
    with pytest.raises(ValueError, match='trace'): exporter.build(tmp_path, capture, loader)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'reordered', 'extra', 'incomplete', 'frame'])
def test_bridge_requires_each_expected_completed_message_once(tmp_path, monkeypatch, fault):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    messages = capture['actions'][2]['messages']
    if fault == 'missing': messages.pop()
    if fault == 'duplicate': messages.append(deepcopy(messages[0]))
    if fault == 'reordered': messages.reverse()
    if fault == 'extra':
        original = exporter.load_logic
        def extra(*args, **kwargs):
            resource = original(*args, **kwargs)
            if args[2] != 25: return resource
            code = bytearray(resource.code); code[0x1a4:0x1a6] = bytes([101, 1])
            return SimpleNamespace(resource_sha256=resource.resource_sha256, code=bytes(code))
        monkeypatch.setattr(exporter, 'load_logic', extra)
        message = deepcopy(messages[0]); message['source_offset'] = 0x1a4; messages.append(message)
    if fault == 'incomplete': messages[0]['handler_return_observed'] = False
    if fault == 'frame': messages[0]['frame']['sha256'] = '0' * 64
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


def test_bridge_additional_messages_from_other_logic_keep_normal_binding(tmp_path, monkeypatch):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    message = deepcopy(capture['actions'][0]['messages'][0])
    capture['actions'][2]['messages'].append(message)
    scene, evidence = exporter.build(tmp_path, capture, load())
    assert evidence['edges'][2]['messages'][-1]['logic'] == 103
    assert scene['partial'] is True
    message['message_id'] = 2
    with pytest.raises(ValueError, match='instruction mismatch'):
        exporter.build(tmp_path, capture, load())


def water_fixture(tmp_path, monkeypatch, departure=True):
    capture, trial, bind = leave_fixture(tmp_path, monkeypatch)
    base_loader = bind(trial)
    goat_code = bytearray(500)
    goat_code[375:377] = bytes([101, 1]); goat_code[381:383] = bytes([84, 13])
    goat_code[450:452] = bytes([101, 1])
    water_code = bytearray(500); water_code[478:480] = bytes([13, 75])
    resources = {103: SimpleNamespace(resource_sha256='a' * 64, code=bytes(goat_code)),
                 8: SimpleNamespace(resource_sha256='c' * 64, code=bytes(water_code))}
    monkeypatch.setattr(exporter, 'load_logic', lambda _directory, _source, number, **kwargs: resources[number])
    monkeypatch.setattr(exporter, 'logic_messages', lambda r: {r.resource_sha256: {'1': 'Authored water refusal.'}})
    capture['source']['resources']['8'] = 'c' * 64
    for index, observation in enumerate(capture['observations'].values()):
        observation['state'].update(score=2 if index == 0 else 7, carrot_carried=True,
                                    water_refused=False, goat_wandering=False, goat_retired=False, water_departure=False)
    capture['observations']['o2']['state']['room'] = 9
    refused = deepcopy(capture['observations']['o2'])
    refused['state'].update(room=8, water_refused=True, goat_wandering=True)
    refused['frame']['metadata']['frame_id'] = 4
    capture['observations']['o3'] = refused
    message = deepcopy(capture['actions'][0]['messages'][0]); message['source_offset'] = 375
    capture['actions'].append({'id': 'lead-to-water', 'label': 'lead the goat to water', 'verb': 'use',
                               'before': 'o2', 'after': 'o3', 'complete': True, 'messages_complete': True,
                               'inputs': [deepcopy(capture['actions'][1]['inputs'][0])], 'messages': [message]})
    specs = [('water-refusal', 103, 'a' * 64, 381, 84, 13, 0x6dcb, 0x6dcf)]
    if departure:
        departed = deepcopy(refused)
        departed['state'].update(room=9, following=False, water_refused=False, goat_retired=True, water_departure=True)
        departed['goat_visible'] = False; departed['frame']['metadata']['frame_id'] = 5
        capture['observations']['o4'] = departed
        capture['actions'].append({'id': 'leave-water', 'label': 'leave the water room', 'verb': 'use',
                                   'before': 'o3', 'after': 'o4', 'complete': True, 'messages_complete': True,
                                   'inputs': [deepcopy(capture['actions'][1]['inputs'][0])], 'messages': []})
        specs.append(('water-departure', 8, 'c' * 64, 478, 13, 75, 0x7432, 0x7434))
    trace = b'authored water branch fetch trace\n'
    proofs = [{'format': 'fdisbull-agi-goat-branch-effect-1', 'branch': branch, 'status': 'verified',
               'complete': True, 'native_execution': True, 'source_logic': logic, 'source_logic_sha256': sha,
               'source_offset': offset, 'opcode': opcode, 'argument': argument,
               'writer': {'offset': writer, 'resume_offset': resume},
               'trace': {'path': branch + '.trace', 'sha256': sha256(trace).hexdigest(), 'count': 32}}
              for branch, logic, sha, offset, opcode, argument, writer, resume in specs]
    def load(trace_raw=trace):
        artifacts = {}
        for action, proof in zip(capture['actions'][2:], proofs):
            name = proof['branch'] + '.json'; raw = json.dumps(proof).encode()
            action['native_branch_effect'] = {'path': name, 'sha256': sha256(raw).hexdigest()}
            artifacts[name] = raw; artifacts[proof['branch'] + '.trace'] = trace_raw
        return lambda path: artifacts[path] if path in artifacts else base_loader(path)
    return capture, proofs, load


@pytest.mark.parametrize('departure', [False, True])
def test_water_player_route_stale_repeat_and_checkpoint(tmp_path, monkeypatch, departure):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch, departure)
    scene, evidence = exporter.build(tmp_path, capture, load())
    backend = ILSceneBackend(scene); player = Player(backend)
    assert 'no action sent' in player.execute('use water').lower()
    assert player.execute('use carrot on goat').startswith('Success:')
    assert player.execute('use route').startswith('Success:')
    stale = backend.observe()['context']['token']
    assert 'Authored water refusal.' in player.execute('use water')
    assert backend.state['$room'] == 8 and backend.state['$score'] == 7 and backend.state['$following'] is True
    assert backend.state['$water_refused'] is True and backend.state['$goat_wandering'] is True
    assert backend.state['$goat_retired'] is False and backend.state['$carrot_carried'] is True
    assert 'Observed water refusal' in player.execute('look')
    assert backend.act({'verb': 'use', 'target': 'water', 'item': None, 'context_token': stale})['status'] == 'rejected'
    assert 'no action sent' in player.execute('use water').lower()
    assert backend.save('refused')['status'] == 'saved'
    if departure:
        assert player.execute('use exit').startswith('Success:')
        assert backend.state['$room'] == 9 and backend.state['$score'] == 7 and backend.state['$following'] is False
        assert backend.state['$water_refused'] is False and backend.state['$water_departure'] is True
        assert backend.state['$goat_retired'] is True and backend.state['$carrot_carried'] is True
        assert 'Observed water departure' in player.execute('look')
        assert 'no action sent' in player.execute('use exit').lower()
        assert backend.load('refused')['status'] == 'restored'
        assert player.execute('use exit').startswith('Success:')
    else:
        assert 'no action sent' in player.execute('use exit').lower()
    assert evidence['edges'][2]['native_branch_effect']['branch'] == 'water-refusal'
    if departure: assert evidence['edges'][3]['native_branch_effect']['branch'] == 'water-departure'
    assert 'Authored water refusal.' not in str(evidence)


def test_existing_bridge_scene_and_provenance_bytes_unchanged(tmp_path, monkeypatch):
    capture, proof, load = bridge_fixture(tmp_path, monkeypatch)
    scene, evidence = exporter.build(tmp_path, capture, load())
    assert sha256((json.dumps(scene, ensure_ascii=False, indent=2) + '\n').encode()).hexdigest() == \
        '10b200a15beebaced97dbf0b2676329783b7d93d305b45725a05f69c622a0b2a'
    assert sha256((json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()).hexdigest() == \
        '7df3f564b8ac43e6171e77cf7bb7b52b8be5dfcd7fb2d52cbd7c19292b8aba2b'


@pytest.mark.parametrize('observation', ['o0', 'o1', 'o2', 'o3', 'o4'])
@pytest.mark.parametrize('field', ['carrot_carried', 'water_refused', 'goat_wandering', 'goat_retired', 'water_departure'])
def test_water_requires_typed_extended_state_everywhere(tmp_path, monkeypatch, observation, field):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    del capture['observations'][observation]['state'][field]
    with pytest.raises(ValueError, match='water observed state'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('observation, field, value', [
    ('o2', 'room', 10), ('o2', 'score', 8), ('o2', 'carrot_carried', False),
    ('o2', 'following', False), ('o2', 'water_refused', True),
    ('o3', 'room', 9), ('o3', 'score', 8), ('o3', 'carrot', False), ('o3', 'carrot_carried', False),
    ('o3', 'following', False), ('o3', 'water_refused', False), ('o3', 'goat_wandering', False), ('o3', 'goat_retired', True),
    ('o4', 'room', 8), ('o4', 'score', 8), ('o4', 'carrot', False), ('o4', 'carrot_carried', False),
    ('o4', 'following', True), ('o4', 'water_refused', True), ('o4', 'goat_retired', False), ('o4', 'water_departure', False),
    ('o0', 'goat_wandering', 1),
])
def test_water_refuses_other_state_outcomes(tmp_path, monkeypatch, observation, field, value):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    capture['observations'][observation]['state'][field] = value
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('visible', [None, True])
def test_water_departure_needs_frame_absence_independent_of_drawn_flag(tmp_path, monkeypatch, visible):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    capture['observations']['o4'].update(goat_visible=visible, native_state={'goat': {'drawn': False}})
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'extra', 'incomplete', 'frame'])
def test_water_refusal_requires_exact_completed_regular_print(tmp_path, monkeypatch, fault):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    messages = capture['actions'][2]['messages']
    if fault == 'missing': messages.clear()
    if fault == 'duplicate': messages.append(deepcopy(messages[0]))
    if fault == 'extra': messages.append(deepcopy(capture['actions'][0]['messages'][0]))
    if fault == 'incomplete': messages[0]['input_settled'] = False
    if fault == 'frame': messages[0]['frame']['sha256'] = '0' * 64
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('field, value', [('format', 'other'), ('branch', 'wander-away'), ('status', 'incomplete'),
                                        ('complete', False), ('native_execution', False), ('source_logic', 25),
                                        ('source_logic_sha256', 'd' * 64), ('source_offset', 0),
                                        ('opcode', 0), ('argument', 0)])
def test_water_branch_proof_must_match_declared_source_occurrence(tmp_path, monkeypatch, index, field, value):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    proofs[index][field] = value
    with pytest.raises(ValueError, match='branch effect not qualified'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('field', ['offset', 'resume_offset'])
def test_water_branch_writer_must_match(tmp_path, monkeypatch, index, field):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    proofs[index]['writer'][field] += 1
    with pytest.raises(ValueError, match='native writer differs'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('fault', ['proof-missing', 'proof-hash', 'trace-missing', 'trace-path', 'trace-hash', 'trace-count', 'trace-bytes'])
def test_water_branch_artifacts_are_required_and_hash_bound(tmp_path, monkeypatch, index, fault):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    if fault == 'trace-missing': del proofs[index]['trace']
    if fault == 'trace-path': del proofs[index]['trace']['path']
    if fault == 'trace-hash': proofs[index]['trace']['sha256'] = '0' * 64
    if fault == 'trace-count': proofs[index]['trace']['count'] = 31
    loader = load(trace_raw=b'changed trace') if fault == 'trace-bytes' else load()
    if fault == 'proof-missing': del capture['actions'][index+2]['native_branch_effect']
    if fault == 'proof-hash': capture['actions'][index+2]['native_branch_effect']['sha256'] = '0' * 64
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, loader)


@pytest.mark.parametrize('logic, offset', [(103, 381), (8, 478)])
def test_water_branch_source_operation_is_checked(tmp_path, monkeypatch, logic, offset):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    original = exporter.load_logic
    def changed(*args, **kwargs):
        resource = original(*args, **kwargs)
        if args[2] != logic: return resource
        code = bytearray(resource.code); code[offset+1] ^= 1
        return SimpleNamespace(resource_sha256=resource.resource_sha256, code=bytes(code))
    monkeypatch.setattr(exporter, 'load_logic', changed)
    with pytest.raises(ValueError, match='source instruction mismatch'):
        exporter.build(tmp_path, capture, load())


@pytest.mark.parametrize('fault', ['third-disconnected', 'fourth-disconnected', 'third-id', 'fourth-id',
                                  'second-id', 'fifth-action', 'missing-logic8'])
def test_water_route_must_be_contiguous_and_declared(tmp_path, monkeypatch, fault):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch)
    if fault == 'third-disconnected': capture['actions'][2]['before'] = 'o1'
    if fault == 'fourth-disconnected': capture['actions'][3]['before'] = 'o2'
    if fault == 'third-id': capture['actions'][2]['id'] = 'wander-away'
    if fault == 'fourth-id': capture['actions'][3]['id'] = 'wander-away'
    if fault == 'second-id': capture['actions'][1]['id'] = 'lead-to-water'
    if fault == 'fifth-action': capture['actions'].append(deepcopy(capture['actions'][3]))
    if fault == 'missing-logic8': del capture['source']['resources']['8']
    with pytest.raises(ValueError): exporter.build(tmp_path, capture, load())


def test_water_refusal_prefix_does_not_require_unobserved_departure_resource(tmp_path, monkeypatch):
    capture, proofs, load = water_fixture(tmp_path, monkeypatch, departure=False)
    del capture['source']['resources']['8']
    scene, _ = exporter.build(tmp_path, capture, load())
    assert set(scene['programs']) == {'show-carrot', 'leave-pen', 'lead-to-water'}
