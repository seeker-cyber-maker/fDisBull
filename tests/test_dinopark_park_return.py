"""Return to the original park without replaying an uncertain navigation."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge
from fdisbull.scenes import SceneError


def held_return(tmp_path, monkeypatch):
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    calls = []
    text = SimpleNamespace(current='street', street='street-r0', park='park-r0', mart=None,
        park_opened=True, vegasaurus_extinct=False, describe=lambda: 'The original park.',
        debug=SimpleNamespace(run_id='run', registers=lambda: {'state_revision': 8888},
            call=lambda method: calls.append(method) or {'state': 'stopped'}))
    service.ready(text)
    service.pending = {'command': 'go park', 'session_token': service.session_token,
        'action': {'verb': 'go', 'target': 'route-park', 'item': None, 'context_token': 'before'},
        'events': [], 'messages': []}
    failure = dict(complete=False, status='observation-failed', run='run',
        scene_revision='street-r0', action_name='street.park', before_observation='before',
        input={'accepted': True, 'delivery': 'queued', 'state_revision': 8888})
    assert service.action_error(SceneError(failure))
    def qualify(selected):
        calls.append('qualify-park')
        selected.current, selected.park = 'park', 'park-r1'
        return {'frame': 'original-frame', 'view': 'park'}
    monkeypatch.setattr(bridge, 'load_scenes', lambda: SimpleNamespace(qualify_park=qualify,
        atomic_json=lambda p, d: p.write_text(json.dumps(d))))
    return service, text, calls


def test_queued_return_reconciles_read_only_and_is_idempotent(tmp_path, monkeypatch):
    service, text, calls = held_return(tmp_path, monkeypatch)
    root = service.held_action['id']
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    result = service.reconcile(root)
    assert result['complete'] and result['read_only'] and result['effects'] == 'applied-confirmed'
    assert result['action'] == {'verb': 'go', 'target': 'route-park', 'item': None}
    assert result['witness']['context_id'] == text.current == 'park'
    assert calls == ['session.status', 'session.status', 'qualify-park']
    assert not service.recovery_required and service.held_action is None
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic
    assert service.reconcile(root)['status'] == 'not-needed'


@pytest.mark.parametrize('bad', ['root', 'run', 'scene', 'control', 'input', 'session', 'before'])
def test_return_reconciliation_refuses_unbound_receipts(tmp_path, monkeypatch, bad):
    service, text, calls = held_return(tmp_path, monkeypatch)
    root = service.held_action['id']
    failure = service.held_action['scene_failure']
    if bad == 'root': root = 'wrong-root'
    elif bad == 'run': failure['run'] = 'wrong-run'
    elif bad == 'scene': failure['scene_revision'] = 'wrong-street'
    elif bad == 'control': failure['action_name'] = 'street.office'
    elif bad == 'input': failure['input']['delivery'] = 'unknown'
    elif bad == 'session': service.held_action['session_token'] = 'wrong-session'
    else: failure['before_observation'] = None
    assert not service.reconcile(root)['complete']
    assert service.recovery_required and text.current == 'street' and 'qualify-park' not in calls


def test_return_budget_starts_before_z_observation(tmp_path, monkeypatch):
    service, text, calls = held_return(tmp_path, monkeypatch)
    service.pending = service.held_action = None
    service.recovery_required = False
    observation = service.observe()
    original = service.observe
    def observe(**kw):
        assert text.debug._rpc_deadline is not None
        return original(**kw)
    monkeypatch.setattr(service, 'observe', observe)
    action = dict(verb='go', target='route-park', item=None,
                  context_token=observation['context']['token'])
    service.reader = io.StringIO(json.dumps({'op': 'act', 'action': action})+'\n')
    assert service.command() == 'go park'
    service._end_action_budget()
    assert text.debug._rpc_deadline is None


def return_text(monkeypatch, *, run_fails=False, notice=None):
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.current, text.street, text.park = 'street', 'street-r0', 'park-r0'
    text.park_opened = True
    text.events, calls = [], []
    text.event = text.events.append
    text.observe_park_status = lambda label: ({'balances': {}}, 'status')
    text.describe = lambda: 'The park.'
    text.patterns = {k: k for k in ('quarter_popup', 'parking_hint', 'park_view', 'street_view')}
    text.project = object()
    ticket = {'accepted': True, 'delivery': 'queued', 'state_revision': 8888}
    def click(point, ms, label, *, hold_ms):
        calls.append(('click', point, ms, hold_ms))
        assert ms is None, 'retain the queued input before waiting for the destination'
        return ticket
    text.shop_click = click
    def run(**kw):
        assert text.debug._rpc_deadline is not None
        assert kw == dict(guest_ms=8000, timeout_ms=40000, fast_forward=True)
        calls.append(('run', kw))
        if run_fails:
            raise TimeoutError('original instrumented return exceeded allowance')
        return {'outcome': 'guest_time'}
    text.debug = SimpleNamespace(run_id='run', run=run,
        scene_assert=lambda *a, **kw: {'observation': 'before'})
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **kw: ('frame', 'image'))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: pattern == notice)
    monkeypatch.setattr(scenes, 'park_snapshot', lambda debug: {'balances': {}})
    def qualify(selected):
        selected.current, selected.park = 'park', 'park-r1'
        return {'frame': 'park-frame', 'view': 'park'}
    monkeypatch.setattr(scenes, 'qualify_park', qualify, raising=False)
    return text, calls, ticket


@pytest.mark.parametrize('run_fails', [True, False])
def test_return_keeps_one_original_input_and_long_loading_budget(monkeypatch, run_fails):
    text, calls, ticket = return_text(monkeypatch, run_fails=run_fails)
    if run_fails:
        with pytest.raises(TimeoutError): text.revisit_park()
    else:
        assert text.revisit_park() == 'The park.'
    assert calls[0] == ('click', (201, 187), None, 80) and len(calls) == 2
    results = [e['result'] for e in text.events if e['phase'] == 'navigation_input_result']
    assert len(results) == 1
    assert results[0]['input'] == ticket and results[0]['before_observation'] == 'before'
    assert results[0]['scene_revision'] == 'street-r0' and results[0]['action_name'] == 'street.park'
    assert results[0]['complete'] is (not run_fails)


@pytest.mark.parametrize('notice', ['quarter_popup', 'parking_hint'])
def test_return_preserves_recognized_notice_continuations(monkeypatch, notice):
    text, calls, ticket = return_text(monkeypatch, notice=notice)
    assert 'acknowledge notice' in text.revisit_park()
    assert text.pending_park_entry and text.current == 'street'
    assert any(e['phase'] == 'interrupted' and e['notices'] == [notice] for e in text.events)
    assert len(calls) == 2


def test_actual_return_run_error_retains_provider_and_uses_its_original_ticket(tmp_path, monkeypatch):
    text, calls, ticket = return_text(monkeypatch, run_fails=True)
    text.mart, text.vegasaurus_extinct = None, False
    text.debug.call = lambda method: {'state': 'stopped'}
    text.debug.registers = lambda: {'state_revision': 8888}
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    service.ready(text)
    text.event = service.event
    service.pending = {'command': 'go park', 'session_token': service.session_token,
        'action': {'verb': 'go', 'target': 'route-park', 'item': None, 'context_token': 'before'},
        'events': [], 'messages': []}
    with pytest.raises(TimeoutError) as error:
        text.revisit_park()
    assert service.action_error(error.value)
    held = deepcopy(service.held_action)
    assert held['scene_failure']['input'] == ticket
    assert held['scene_failure']['before_observation'] == 'before'
    assert held['effects'] == 'unknown' and service.recovery_required
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    assert service.reconcile(held['id'])['complete']
    assert len(calls) == 2  # Only the original press and failed run, no replay.
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic


@pytest.mark.parametrize('view', ['park', 'quarter_popup', 'parking_hint', 'unknown'])
def test_park_qualifier_is_read_only_and_uses_committed_head(monkeypatch, view):
    head, docs, captures = ['park-r0'], [], []
    def info(key, **kw):
        assert kw == {'version': 1}
        return {'id': head[0] if key == 'park' else key, 'scene': 'park-root', 'name': 'park'}
    def save(name, doc, *, parent, version):
        assert (name, parent, version) == ('park', head[0], 1)
        docs.append(doc)
        head[0] = 'next-' + head[0]
        if len(docs) == 1: raise RuntimeError('publication committed, readback failed')
        return {'id': head[0]}
    text = SimpleNamespace(current='street', park='park-r0', pending_park_entry=False,
        patterns={k: k for k in ('park_view', 'street_view', 'quarter_popup', 'parking_hint')},
        debug=SimpleNamespace(version={'id': 1}, memory=lambda *a, **kw: {'hex': '3412'}),
        project=SimpleNamespace(debug_scene_info=info, debug_save_scene=save))
    def capture(*a, **kw):
        assert kw == {'hooks': False}
        captures.append(True)
        return {'artifact': 'frame', 'metadata': {'mode_id': 'mode'}}, 'image'
    monkeypatch.setattr(scenes, 'take_frame', capture)
    monkeypatch.setattr(scenes, 'matches', lambda image, p: p == view or p == 'park_view' and view == 'park')
    monkeypatch.setattr(scenes, 'pixel_predicate', lambda p: {'constant': True})
    if view != 'park':
        with pytest.raises(RuntimeError, match='Park destination'): scenes.qualify_park(text)
        assert not docs and text.current == 'street'
        return
    # A committed publication whose return readback failed is read again by name.
    with pytest.raises(RuntimeError, match='publication committed'): scenes.qualify_park(text)
    result = scenes.qualify_park(text)
    assert result['scene']['id'] == text.park == head[0] == 'next-next-park-r0'
    assert text.current == 'park' and docs[-1]['objects'][0]['ready']['memory']['hex'] == '3412'


def test_return_witness_failure_can_retry_after_park_publication(tmp_path, monkeypatch):
    service, text, calls = held_return(tmp_path, monkeypatch)
    module = bridge.load_scenes()
    def qualify(selected):
        assert selected.park in ('park-r0', 'park-r1')
        selected.current, selected.park = 'park', 'park-r1'
        return {'frame': 'frame', 'view': 'park'}
    module.qualify_park = qualify
    count = [0]
    def registers():
        count[0] += 1
        if count[0] == 1: raise RuntimeError('post-publication witness unavailable')
        return {'state_revision': 8888}
    text.debug.registers = registers
    root, held = service.held_action['id'], deepcopy(service.held_action)
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    assert not service.reconcile(root)['complete']
    assert service.held_action == held and text.current == 'street' and text.park == 'park-r1'
    assert service.reconcile(root)['complete']
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic


@pytest.mark.parametrize('publication_readback_fails', [False, True])
def test_loaded_native_park_can_publish_its_first_scene_and_retry(monkeypatch, publication_readback_fails):
    # Native save loading restores qualifications, not scene IDs from another project.
    head, parents = [None], []
    def info(key, **kw):
        assert key is not None, 'A loaded park has no prior scene revision'
        return {'id': head[0], 'scene': 'park-root', 'name': 'park'}
    def listing(**kw):
        assert kw == {'version': 1}
        return {'scenes': [] if head[0] is None else [info('park')]}
    def save(name, doc, *, parent, version):
        assert (name, parent, version) == ('park', head[0], 1)
        parents.append(parent)
        head[0] = 'park-r1' if head[0] is None else 'park-r2'
        if publication_readback_fails and len(parents) == 1:
            raise RuntimeError('first scene committed, return readback failed')
        return {'id': head[0]}
    text = SimpleNamespace(current='street', park=None, pending_park_entry=False,
        patterns={k: k for k in ('park_view','street_view','quarter_popup','parking_hint')},
        debug=SimpleNamespace(version={'id': 1}, memory=lambda *a, **kw: {'hex': '3412'}),
        project=SimpleNamespace(debug_scene_info=info, debug_scenes=listing, debug_save_scene=save))
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **kw: (
        {'artifact': 'frame', 'metadata': {'mode_id': 'mode'}}, 'image'))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: pattern == 'park_view')
    monkeypatch.setattr(scenes, 'pixel_predicate', lambda *a: {'constant': True})
    if publication_readback_fails:
        with pytest.raises(RuntimeError, match='first scene committed'): scenes.qualify_park(text)
        assert text.park is None and text.current == 'street'
    result = scenes.qualify_park(text)
    assert result['scene']['id'] == text.park == head[0] and text.current == 'park'
    assert parents == ([None, 'park-r1'] if publication_readback_fails else [None])
