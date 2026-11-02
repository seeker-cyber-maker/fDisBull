"""Business navigation receipts survive bounded waits and readback failures."""
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge
from fdisbull.scenes import SceneError


ROUTES = [('employment', 'employment', 'street.employment'),
          ('dinomart', 'dinomart', 'street.mart'),
          ('store', 'general_store', 'street.store'),
          ('diner', 'dino_diner', 'street.diner')]


def boundary(tmp_path, monkeypatch, route='employment', view='employment', obj='street.employment'):
    """Native boundary refuses execution; project enforces immutable revision parents."""
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    reads, heads, saved = [], {}, []
    native = SimpleNamespace(run_id='owned-run')
    def call(method):
        reads.append(method)
        assert method == 'session.status'
        return {'state': 'stopped'}
    native.call = call
    native.memory = lambda *a, **k: {'hex': 'ffff'}
    native.registers = lambda: {'state_revision': 9}
    def save(name, definition, parent=None):
        assert parent == heads.get(name), 'Scene parent must be the current revision'
        heads[name] = name + '-' + str(len(saved))
        saved.append(definition)
        return {'id': heads[name]}
    patterns = {v: {'name': v, 'samples': [{'x': 0, 'y': 0, 'rgb': [0, 0, 0]}],
                    'min_matches': 1, 'tolerance': 0}
                for v in ('employment', 'mart', 'after', 'general_store', 'fence_tab',
                          'fence_selected', 'dino_diner', 'food_menu', 'food_selected')}
    project = SimpleNamespace(debug_save_scene=save, debug_scene_info=lambda *a: {
        'definition': {'match': {'constant': True}}})
    text = SimpleNamespace(current='street', street='street-revision', mart=None, locations={},
                           debug=native, project=project, patterns=patterns, land_bought=True,
                           park_opened=False, event=service.event, vegasaurus_extinct=False)
    text.describe = lambda: 'Qualified ' + text.current
    service.ready(text)
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: image == pattern['name'])
    def frame(*a, **kw):
        assert kw.get('hooks') is False, 'Readback must not run screenshot hooks'
        reads.append('frame')
        return {'artifact': 'stored-frame', 'metadata': {'mode_id': 5}}, 'mart' if view == 'dinomart' else view
    monkeypatch.setattr(scenes, 'take_frame', frame)
    service.pending = {'command': 'go ' + route, 'session_token': service.session_token,
                       'action': {'verb': 'go', 'target': 'route-' + route, 'item': None,
                                  'context_token': 'original-context'}, 'events': [], 'messages': []}
    failure = dict(status='timeout', complete=False, run=native.run_id,
                   scene_revision=text.street, action_name=obj, before_observation='source-witness',
                   input={'accepted': True, 'delivery': 'queued', 'operation_id': 'click-once'})
    return service, failure, reads, heads


@pytest.mark.parametrize('route,view,obj', ROUTES)
def test_business_loading_budget_is_finite_and_below_transport(route, view, obj):
    reference = {'artifact': 'street-frame', 'metadata': {'mode_id': 5}}
    pattern = {'samples': [{'x': 0, 'y': 0, 'rgb': [0, 0, 0]}], 'min_matches': 1, 'tolerance': 0}
    patterns = {key: pattern for key in ('mart', 'after', 'employment', 'general_store',
                                        'fence_tab', 'fence_selected', 'dino_diner',
                                        'food_menu', 'food_selected')}
    item = scenes.business_entry_object(reference, {'constant': True}, {'constant': True}, patterns, view)
    assert item['name'] == obj
    assert item['timeout_ms'] == 40000 < 60000
    assert item['guest_ms'] == 12000


@pytest.mark.parametrize('route,view,obj', ROUTES)
def test_original_business_navigation_reconciles_without_execution(tmp_path, monkeypatch, route, view, obj):
    service, failure, reads, _ = boundary(tmp_path, monkeypatch, route, view, obj)
    assert service.action_error(SceneError(failure))
    original = (tmp_path / 'z-failure.json').read_bytes()
    ident, session = service.held_action['id'], service.session_token
    assert service.observe()['reconciliation_available']
    result = service.reconcile(ident)
    assert result['complete'] and result['status'] == 'success' and result['read_only']
    assert result['action'] == {'verb': 'go', 'target': 'route-' + route, 'item': None}
    assert result['witness']['context_id'] == view and result['witness']['session_token'] == session
    assert not service.recovery_required and service.held_action is None
    assert set(reads) == {'session.status', 'frame'}
    assert (tmp_path / 'z-failure.json').read_bytes() == original


def test_failed_witness_keeps_published_scene_head_for_later_read_only_retry(tmp_path, monkeypatch):
    service, failure, _, heads = boundary(tmp_path, monkeypatch)
    service.action_error(SceneError(failure))
    native = service.text.debug
    count = 0
    def registers():
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError('temporary readback failure after scene publication')
        return {'state_revision': 9}
    native.registers = registers
    ident = service.held_action['id']
    assert not service.reconcile(ident)['complete']
    assert service.held_action['id'] == ident and service.text.current == 'street'
    assert service.text.locations['employment'] == heads['employment']
    assert service.reconcile(ident)['complete']


@pytest.mark.parametrize('field,value', [('run', 'another-run'),
                                       ('scene_revision', 'another-street'),
                                       ('action_name', 'street.diner')])
def test_employment_hold_never_crosses_another_input_context(tmp_path, monkeypatch, field, value):
    service, failure, reads, _ = boundary(tmp_path, monkeypatch)
    failure[field] = value
    service.action_error(SceneError(failure))
    assert not service.reconcile()['complete']
    assert service.recovery_required and 'frame' not in reads


def test_late_navigation_error_retains_receipt_after_destination_publication(tmp_path, monkeypatch):
    service, failure, reads, _ = boundary(tmp_path, monkeypatch)
    clicks = []
    def click(scene, obj):
        clicks.append((scene, obj))
        return {**{k: v for k, v in failure.items() if k not in ('scene_revision', 'action_name', 'run')},
                'status': 'matched', 'complete': True}
    service.text.debug.scene_click = click
    scenes.click_business(service.text, 'go employment', service.text.street, 'street.employment')
    scenes.qualify_business(service.text, 'employment')
    assert service.text.current == 'employment'
    assert service.action_error(RuntimeError('host failure after real qualifier'))
    assert service.observe()['reconciliation_available']
    assert service.reconcile()['complete']
    assert clicks == [('street-revision', 'street.employment')]


def test_employment_budget_reaches_native_before_request_observation(tmp_path, monkeypatch):
    service, failure, _, _ = boundary(tmp_path, monkeypatch)
    service.pending = None
    observation = service.observe()
    action = {'verb': 'go', 'target': 'route-employment', 'item': None,
              'context_token': observation['context']['token']}
    service.reader = io.StringIO(json.dumps({'op': 'act', 'action': action}) + '\n')
    assert service.command() == 'go employment'
    native = service.text.debug
    assert native._rpc_deadline is not None and native._rpc_timeout_cap_ms == 5000
    service.action_error(SceneError(failure))
    assert native._rpc_deadline is None


@pytest.mark.parametrize('route,view,obj', ROUTES)
def test_normal_final_witness_failure_retains_original_action_for_reconciliation(
        tmp_path, monkeypatch, route, view, obj):
    service, failure, _, _ = boundary(tmp_path, monkeypatch, route, view, obj)
    native = service.text.debug
    native.scene_click = lambda *a: {**failure, 'status': 'matched', 'complete': True}
    scenes.click_business(service.text, 'go ' + route, service.text.street, obj)
    scenes.qualify_business(service.text, view)
    service.event({'phase': 'result', 'command': 'go ' + route, 'scene': view})
    native.registers = lambda: (_ for _ in ()).throw(TimeoutError('final witness unavailable'))
    service.finish()
    response = json.loads(service.writer.getvalue().splitlines()[-1])
    assert not response['complete'] and response['recovery_required']
    assert response['effects'] == 'applied-confirmed'
    assert service.held_action['pending']['action']['target'] == 'route-' + route
    assert service.held_action['scene_failure']['input']['operation_id'] == 'click-once'
    native.registers = lambda: {'state_revision': 9}
    assert service.reconcile(service.held_action['id'])['complete']


@pytest.mark.parametrize('field,value', [('run', 'another-run'),
                                       ('scene_revision', 'another-revision'),
                                       ('action_name', 'street.diner')])
def test_success_receipt_keeps_raw_identity_and_cannot_confirm_a_different_context(
        tmp_path, monkeypatch, field, value):
    service, failure, _, _ = boundary(tmp_path, monkeypatch)
    raw = {**failure, 'status': 'matched', 'complete': True, field: value}
    service.text.debug.scene_click = lambda *a: raw
    scenes.click_business(service.text, 'go employment', service.text.street, 'street.employment')
    assert service.pending['events'][-1]['result'][field] == value
    service.action_error(RuntimeError('later host failure'))
    assert service.held_action['effects'] == 'unknown'
    assert not service.reconcile()['complete']
