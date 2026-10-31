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
