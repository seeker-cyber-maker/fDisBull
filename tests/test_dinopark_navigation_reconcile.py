"""Held original navigation: evidence retention, read-only recovery, no replay."""
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_z as bridge
from fdisbull.scenes import SceneError, SceneHandle
from fdisbull_player import Player


def test_scene_timeout_retains_the_original_queued_input_and_before_witness():
    handle = SceneHandle.__new__(SceneHandle)
    handle.revision = 'street-revision'
    obj = dict(id='object-id', name='street.mart', action={'kind': 'click'},
               point=[160, 66], guest_ms=12000, timeout_ms=40000,
               outcome={'constant': False})
    handle.session = SimpleNamespace(project=SimpleNamespace(
        debug_scene_info=lambda *a, **k: {'definition': {}}), version={'id': 1}, run_id='run')
    handle._object = lambda name: obj
    handle._observe = lambda *a: {'status': 'matched', 'initial_outcome': False,
                                 'frame': {}, 'baseline': {}}
    handle._store = lambda result, **kw: dict(result, observation='before-or-failure')
    inputs = []
    def queue(*args):
        inputs.append(args)
        return {'accepted': True, 'delivery': 'queued', 'operation_id': 'input-once'}
    handle._input = queue
    def timeout(*a, **kw):
        raise SceneError({'status': 'timeout', 'complete': False, 'run': 'run'})
    handle._wait_outcome = timeout
    with pytest.raises(SceneError) as caught:
        handle.act('street.mart')
    result = caught.value.result
    assert result['input']['operation_id'] == 'input-once'
    assert result['before_observation'] == 'before-or-failure'
    assert result['action_name'] == 'street.mart' and result['scene_revision'] == handle.revision
    assert len(inputs) == 1


@pytest.mark.parametrize('error', [TimeoutError('RPC admission expired'),
                                  RuntimeError('destination readback failed')])
def test_native_readback_exception_retains_queued_scene_input(error):
    handle = SceneHandle.__new__(SceneHandle)
    handle.revision = 'street-revision'
    handle.session = SimpleNamespace(project=SimpleNamespace(
        debug_scene_info=lambda *a, **k: {'definition': {}}), version={'id': 1}, run_id='run')
    handle._object = lambda name: dict(id='employment-object', name=name,
        action={'kind': 'click'}, point=[270, 66], guest_ms=12000, timeout_ms=40000,
        outcome={'constant': False})
    handle._observe = lambda *a: {'status': 'matched', 'initial_outcome': False,
                                 'frame': {}, 'baseline': {}}
    handle._store = lambda result, **kw: dict(result, observation='stored-observation')
    inputs = []
    def queue(*args):
        inputs.append(args)
        return {'accepted': True, 'delivery': 'queued', 'operation_id': 'only-click'}
    handle._input = queue
    def failed(*a, **kw): raise error
    handle._wait_outcome = failed
    with pytest.raises(SceneError) as caught:
        handle.act('street.employment')
    assert caught.value.result['input']['operation_id'] == 'only-click'
    assert caught.value.result['action_name'] == 'street.employment'
    assert caught.value.result['before_observation'] == 'stored-observation'
    assert caught.value.result['complete'] is False and len(inputs) == 1


def held_service(tmp_path, monkeypatch, *, destination=True, command='go dinomart', ticket=True, confirmed=False):
    writer = io.StringIO(); service = bridge.ZService(tmp_path, io.StringIO(), writer)
    calls = []
    def call(operation):
        calls.append(operation)
        assert operation == 'session.status'  # No input/execution/state restore is allowed.
        return {'state': 'stopped'}
    text = SimpleNamespace(current='street', street='street-revision', mart='old-mart',
                           debug=SimpleNamespace(call=call, registers=lambda: {'state_revision': 7}),
                           vegasaurus_extinct=False, describe=lambda: 'Qualified catalogue.')
    service.ready(text)
    service.pending = {'command': command, 'session_token': service.session_token,
                       'action': {'verb': 'go', 'target': 'route-dinomart', 'item': None,
                                  'context_token': 'original-context'}, 'messages': [],
                       'events': [{'phase':'food_purchase_committed'}] if confirmed else []}
    result = dict(status='timeout', complete=False, run='run', scene_revision=text.street,
                  action_name='street.mart', before_observation='original-source',
                  input={'accepted': True, 'delivery': 'queued', 'operation_id': 'input-once'})
    if not ticket: result.pop('input')
    assert service.action_error(SceneError(result))
    def qualify(selected):
        assert selected is text
        calls.append('read-target-frame')
        if not destination: raise ValueError('Still loading, destination not qualified')
        text.current = 'dinomart'; text.mart = 'fresh-mart'
        return {'frame': 'target-frame', 'view': 'mart'}
    monkeypatch.setattr(bridge, 'load_scenes', lambda: SimpleNamespace(
        qualify_dinomart=qualify,
        atomic_json=lambda p, v: p.write_text(json.dumps(v))))
    return service, writer, calls


def test_held_navigation_reconciles_in_same_provider_without_replaying_input(tmp_path, monkeypatch):
    service, writer, calls = held_service(tmp_path, monkeypatch)
    original_diagnostic = (tmp_path/'z-failure.json').read_bytes()
    session = service.session_token
    assert service.observe()['reconciliation_available'] is True
    reply = service.reconcile()
    assert reply['complete'] and reply['status'] == 'success'
    assert reply['read_only'] is True and reply['effects'] == 'applied-confirmed'
    assert reply['action'] == {'verb': 'go', 'target': 'route-dinomart', 'item': None}
    assert reply['witness']['session_token'] == session
    assert reply['witness']['context_id'] == 'dinomart'
    assert service.session_token == session and not service.recovery_required
    assert service.observe()['complete'] and service.text.current == 'dinomart'
    assert calls == ['session.status', 'session.status', 'read-target-frame']
    assert (tmp_path/'z-failure.json').read_bytes() == original_diagnostic
    assert service.reconcile()['status'] == 'not-needed'


@pytest.mark.parametrize('command,ticket,destination', [
    ('go dinomart', True, False), ('buy coelophysis', True, True),
    ('go dinomart', False, True)])
def test_unqualified_holds_remain_alive_and_never_gain_action_authorization(
        tmp_path, monkeypatch, command, ticket, destination):
    service, writer, calls = held_service(tmp_path, monkeypatch, command=command,
                                          ticket=ticket, destination=destination)
    result = service.reconcile()
    assert not result['complete'] and result['read_only'] is True
    assert result['effects'] == 'unknown' and service.recovery_required
    assert service.text.current == 'street' and service.pending is None
    if command != 'go dinomart' or not ticket:
        assert 'read-target-frame' not in calls
    service.reader = io.StringIO(json.dumps({'op': 'act', 'action': {}})+'\n')
    with pytest.raises(EOFError): service.command()
    assert json.loads(writer.getvalue().splitlines()[-1])['status'] == 'rejected'


def test_reconcile_does_not_clear_a_hold_after_a_guest_change(tmp_path, monkeypatch):
    service, _, calls = held_service(tmp_path, monkeypatch)
    service.session_token = 'different-original-guest'
    result = service.reconcile()
    assert result['complete'] is False and service.recovery_required
    assert 'read-target-frame' not in calls


def test_reconciliation_identity_does_not_select_a_different_original_attempt(tmp_path, monkeypatch):
    service, _, calls = held_service(tmp_path, monkeypatch)
    assert not service.reconcile('another-attempt')['complete']
    assert service.recovery_required and 'read-target-frame' not in calls
    ident = service.held_action['id']
    result = service.reconcile(ident)
    assert result['complete'] and result['recovery_id'] == ident


def test_read_only_query_preserves_known_purchase_commit_without_clearing_followup_hold(tmp_path, monkeypatch):
    service, _, calls = held_service(tmp_path, monkeypatch, command='buy 20 small feeders', confirmed=True)
    result = service.reconcile()
    assert not result['complete'] and result['effects'] == 'applied-confirmed'
    assert service.recovery_required and 'read-target-frame' not in calls


def test_text_reconcile_can_reach_held_provider_without_act_or_normal_observation():
    class Backend:
        def observe(self): raise AssertionError('Ordinary observation cannot bypass the hold')
        def act(self, request): raise AssertionError('Never replay the action')
        def reconcile(self):
            return {'complete': True, 'status': 'success', 'read_only': True,
                    'effects': 'applied-confirmed', 'message': 'Original destination verified.',
                    'action': {'verb': 'go', 'target': 'route-dinomart', 'item': None}}
    result = Player(Backend()).execute_result('reconcile')
    assert result['complete'] and result['status'] == 'success'
    assert result['read_only'] and result['action_sent'] is False


def test_player_does_not_trust_a_reconciliation_that_is_not_read_only():
    class Backend:
        def observe(self): raise AssertionError('No normal observation')
        def reconcile(self): return {'complete': True, 'status': 'success', 'effects': 'applied-confirmed'}
    result = Player(Backend()).execute_result('reconcile')
    assert not result['complete'] and result['effects'] == 'unknown'
