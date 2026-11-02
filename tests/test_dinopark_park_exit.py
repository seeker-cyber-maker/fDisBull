"""Original park exit: delayed loading and input-free destination reconciliation."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge
from fdisbull.scenes import SceneError, SceneHandle


def test_park_exit_allows_a_delayed_destination_without_a_second_press(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('fdisbull.scenes.time.monotonic', lambda: clock[0])
    reference = {'artifact': 'frame', 'metadata': {'mode_id': 'mode'}}
    doc = scenes.definition(reference, 'park', {}, {}, 'park.back', [173, 187], {})
    obj = dict(doc['objects'][0], id='park-exit')
    h = SceneHandle.__new__(SceneHandle)
    h.revision = 'park-revision'
    presses = []
    h.session = SimpleNamespace(run_id='run', version={'id': 1}, project=SimpleNamespace(
        debug_scene_info=lambda *a, **k: {'definition': doc}))
    h._object = lambda name: obj
    h._store = lambda result, **kw: dict(result, observation='stored')
    def observe(target=None, extra=None, baseline=None):
        return dict(status='matched' if target else 'mismatch', initial_outcome=False,
                    predicate_matched=clock[0] >= 13, frame={}, baseline={})
    h._observe = observe
    h._input = lambda *a: presses.append(a) or {'accepted': True, 'delivery': 'queued'}
    def run(**kw):
        clock[0] += 1
        return {'outcome': 'guest_time', 'guest_elapsed_ms': kw['guest_ms']}
    h.session.run = run
    result = h.act('park.back')
    assert result['complete'] and result['status'] == 'matched'
    assert clock[0] == 13 and len(presses) == 1


def parked_service(tmp_path, monkeypatch, *, qualify=True):
    output = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), output)
    calls = []
    def call(method):
        assert method == 'session.status'
        calls.append(method)
        return {'state': 'stopped'}
    text = SimpleNamespace(current='park', park='park-revision', street='old-street',
        mart=None, debug=SimpleNamespace(call=call, run_id='original-run',
                                        registers=lambda: {'state_revision': 7916}),
        describe=lambda: 'The original street.', vegasaurus_extinct=False)
    service.ready(text)
    service.pending = {'command': 'go street', 'session_token': service.session_token,
        'action': {'verb': 'go', 'target': 'route-street', 'item': None,
                   'context_token': 'original-park-context'}, 'events': [], 'messages': []}
    failure = dict(status='observation-failed', complete=False, run='original-run',
        scene_revision='park-revision', action_name='park.back',
        before_observation='before-click', input={'accepted': True, 'delivery': 'queued',
                                                'state_revision': 7916})
    assert service.action_error(SceneError(failure))
    def read_street(selected):
        assert selected is text
        calls.append('read-street')
        if not qualify:
            text.street = 'unqualified-revision'
            raise RuntimeError('Street not ready')
        text.current, text.street = 'street', 'fresh-street'
        return {'frame': 'original-street-frame', 'view': 'street'}
    monkeypatch.setattr(bridge, 'load_scenes', lambda: SimpleNamespace(
        qualify_street=read_street, atomic_json=lambda p, d: p.write_text(json.dumps(d))))
    return service, text, calls


def test_original_queued_park_exit_reconciles_without_execution_or_input(tmp_path, monkeypatch):
    service, text, calls = parked_service(tmp_path, monkeypatch)
    root = service.held_action['id']
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    reply = service.reconcile(root)
    assert reply['complete'] and reply['read_only'] and reply['effects'] == 'applied-confirmed'
    assert reply['action'] == {'verb': 'go', 'target': 'route-street', 'item': None}
    assert reply['witness']['context_id'] == 'street'
    assert calls == ['session.status', 'session.status', 'read-street']
    assert not service.recovery_required and service.held_action is None
    assert text.current == 'street' and text.street == 'fresh-street'
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic
    assert service.reconcile(root)['status'] == 'not-needed'


@pytest.mark.parametrize('bad', ['wrong-root', 'wrong-run', 'wrong-scene', 'wrong-control', 'not-queued'])
def test_park_reconciliation_refuses_unbound_receipts(tmp_path, monkeypatch, bad):
    service, text, calls = parked_service(tmp_path, monkeypatch)
    root = service.held_action['id']
    failure = service.held_action['scene_failure']
    if bad == 'wrong-root': root = 'another-root'
    elif bad == 'wrong-run': failure['run'] = 'another-run'
    elif bad == 'wrong-scene': failure['scene_revision'] = 'another-park'
    elif bad == 'wrong-control': failure['action_name'] = 'office.street'
    else: failure['input']['delivery'] = 'unknown'
    reply = service.reconcile(root)
    assert not reply['complete'] and reply['effects'] == 'unknown'
    assert service.recovery_required and text.current == 'park' and 'read-street' not in calls


def test_repeated_failed_readback_preserves_root_diagnostic_and_scene_binding(tmp_path, monkeypatch):
    service, text, calls = parked_service(tmp_path, monkeypatch, qualify=False)
    held = deepcopy(service.held_action)
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    for _ in range(2):
        result = service.reconcile(held['id'])
        assert not result['complete'] and result['read_only']
        assert service.held_action == held and text.current == 'park' and text.street == 'old-street'
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic
    assert calls.count('read-street') == 2


@pytest.mark.parametrize('visible', [True, False])
def test_street_qualification_is_read_only_and_refreshes_control_selectors(monkeypatch, visible):
    calls, saved = [], []
    def memory(address, *, length):
        assert (address, length) == ('4020:3c5c', 2)
        calls.append('memory')
        return {'hex': '3412'}
    def store(name, doc, *, parent, **kw):
        assert name == 'street' and parent == 'old-street'
        saved.append(doc)
        return {'id': 'fresh-street'}
    text = SimpleNamespace(street='old-street', office='office', current='park',
        debug=SimpleNamespace(memory=memory, version={'id': 1}), patterns={'shop_street': {}},
        project=SimpleNamespace(debug_save_scene=store,
            debug_scene_info=lambda scene, **kw: {'id': 'old-street', 'name': 'street',
                'scene': 'street-root', 'definition': {'match': {'constant': True}}}))
    frame = {'artifact': 'fresh-frame', 'metadata': {'mode_id': 'current-mode'}}
    def capture(project, debug, name, *, hooks):
        assert hooks is False
        calls.append('frame')
        return frame, 'captured-original'
    monkeypatch.setattr(scenes, 'take_frame', capture)
    monkeypatch.setattr(scenes, 'matches', lambda *a: visible)
    monkeypatch.setattr(scenes, 'pixel_predicate', lambda p: {'constant': True})
    for _, _, views in scenes.BUSINESS_ENTRIES.values():
        text.patterns.update({v: {} for v in views})
    if not visible:
        with pytest.raises(RuntimeError, match='Street destination'):
            scenes.qualify_street(text)
        assert calls == ['frame'] and not saved and text.current == 'park'
        return
    result = scenes.qualify_street(text)
    assert result['frame'] is frame and text.current == 'street' and text.street == 'fresh-street'
    assert calls == ['frame', 'memory'] and len(saved) == 1
    assert len(saved[0]['objects']) == 5
    assert all(o['ready'] == o['enabled'] == {
        'memory': {'address': '4020:3c5c', 'length': 2, 'hex': '3412'}} for o in saved[0]['objects'])


def test_failed_navigation_records_authoritative_queued_input_before_reraising():
    failure = SceneError({'status': 'observation-failed', 'complete': False,
        'input': {'accepted': True, 'delivery': 'queued', 'state_revision': 7916}})
    def click(*a): raise failure
    events = []
    text = SimpleNamespace(debug=SimpleNamespace(scene_click=click, run_id='run'), event=events.append)
    with pytest.raises(SceneError) as caught:
        scenes.click_business(text, 'go street', 'park-revision', 'park.back')
    assert caught.value is failure and len(events) == 1
    result = events[0]['result']
    assert result['input']['state_revision'] == 7916 and result['action_name'] == 'park.back'
    assert result['scene_revision'] == 'park-revision' and result['run'] == 'run'


@pytest.mark.parametrize('target,command', [('route-street', 'go street'),
                                         ('route-employment', 'go employment')])
def test_park_and_composed_business_routes_share_a_budget_before_observation(
        tmp_path, monkeypatch, target, command):
    service, text, calls = parked_service(tmp_path, monkeypatch)
    service.pending = service.held_action = None
    service.recovery_required = False
    observation = service.observe()
    original = service.observe
    def observe(**kw):
        assert text.debug._rpc_deadline is not None
        return original(**kw)
    monkeypatch.setattr(service, 'observe', observe)
    action = {'verb': 'go', 'target': target, 'item': None,
              'context_token': observation['context']['token']}
    service.reader = io.StringIO(json.dumps({'op': 'act', 'action': action})+'\n')
    assert service.command() == command
    deadline = text.debug._rpc_deadline
    text.current, text.street = 'street', 'fresh-street'
    assert text.debug._rpc_deadline == deadline
    service._end_action_budget()
    assert text.debug._rpc_deadline is None


def test_post_publication_witness_failure_can_reconcile_again_without_stale_parent(
        tmp_path, monkeypatch):
    service, text, calls = parked_service(tmp_path, monkeypatch)
    head = ['old-street']
    def qualify(selected):
        assert selected.street == head[0], 'Scene revision changed during save'
        head[0] = 'next-' + head[0]
        selected.street, selected.current = head[0], 'street'
        return {'frame': 'fresh-frame', 'view': 'street'}
    module = bridge.load_scenes()
    module.qualify_street = qualify
    monkeypatch.setattr(bridge, 'load_scenes', lambda: module)
    reads = [0]
    def registers():
        reads[0] += 1
        if reads[0] == 1:
            raise RuntimeError('witness unavailable after street revision publication')
        return {'state_revision': 7916}
    text.debug.registers = registers
    root = service.held_action['id']
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    assert not service.reconcile(root)['complete']
    assert service.held_action['id'] == root and text.current == 'park'
    assert service.reconcile(root)['complete']
    assert text.street == head[0] and (tmp_path/'z-failure.json').read_bytes() == diagnostic


def test_street_publisher_commit_then_readback_failure_uses_committed_head_on_retry(monkeypatch):
    head = ['street-r0']
    def info(key, **kw):
        return {'id': head[0] if key == 'street' else key, 'scene': 'street-root',
                'name': 'street', 'definition': {'match': {'constant': True}}}
    def save(name, doc, *, parent, **kw):
        assert parent == head[0], 'Scene revision changed during save'
        head[0] = 'next-' + head[0]
        if head[0] == 'next-street-r0':
            raise RuntimeError('scene publication committed; return readback failed')
        return {'id': head[0]}
    text = SimpleNamespace(current='park', street='street-r0', office='office',
        patterns={'shop_street': {}}, debug=SimpleNamespace(version={'id': 1},
            memory=lambda *a, **kw: {'hex': '3412'}),
        project=SimpleNamespace(debug_scene_info=info, debug_save_scene=save))
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **kw: (
        {'artifact': 'frame', 'metadata': {'mode_id': 'mode'}}, 'image'))
    monkeypatch.setattr(scenes, 'matches', lambda *a: True)
    monkeypatch.setattr(scenes, 'pixel_predicate', lambda *a: {'constant': True})
    for _, _, views in scenes.BUSINESS_ENTRIES.values():
        text.patterns.update({v: {} for v in views})
    with pytest.raises(RuntimeError, match='publication committed'):
        scenes.qualify_street(text)
    assert text.current == 'park' and text.street == 'street-r0'
    assert scenes.qualify_street(text)['scene']['id'] == head[0]
    assert text.current == 'street' and head[0] == 'next-next-street-r0'
