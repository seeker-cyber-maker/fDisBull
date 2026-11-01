"""An explicit continuation advances only the unfinished original order phases."""
import io
import json

import pytest

from fdisbull import dinopark_purchase as purchase
from fdisbull.dinopark_scenes import dispatch_local_action
from test_dinopark_purchase_reconcile import shop, provider


def held_order(tmp_path, monkeypatch):
    text, native, events = shop(monkeypatch)
    service, writer = provider(tmp_path, text, events)
    now, expired = [0.0], [False]
    monkeypatch.setattr(purchase, '_clock', lambda: now[0])
    event = text.event
    def deliver(value):
        event(value)
        if value.get('purchase_phase') == 'order' and not expired[0]:
            expired[0] = True
            now[0] = 40
    text.event = deliver
    with pytest.raises(TimeoutError) as error: text.buy_dinosaur()
    assert service.action_error(error.value)
    return text, native, service, writer, now


def dispatch_continue(service):
    observed = service.observe()
    action = {'verb':'continue','target':'dinosaur-order','item':None,
              'context_token':observed['context']['token']}
    service.reader = io.StringIO(json.dumps({'op':'act','action':action})+'\n')
    return service.command()


def test_continue_skips_delivered_inputs_and_reconcile_certifies_original_buy(tmp_path, monkeypatch):
    text, native, service, writer, _ = held_order(tmp_path, monkeypatch)
    ident = service.held_action['id']
    diagnostic = (tmp_path/'z-failure.json').read_bytes()
    assert native.clicks == [(160,87),(160,103),(187,187)]
    observation = service.observe()
    assert observation['complete'] and observation['context']['id'] == 'dinomart.order-order'
    assert observation['objects'][0]['verbs'] == ['continue']
    command = dispatch_continue(service)
    assert command == 'continue dinosaur order'
    service.output(dispatch_local_action(text, command))
    service.finish()
    assert service.held_action['id'] == ident and service.recovery_required
    assert native.clicks == [(160,87),(160,103),(187,187),(42,50),(188,187)]
    assert service.observe()['objects'] == []  # Only read-only reconciliation remains.
    before = list(native.clicks), list(native.runs)
    result = service.reconcile(ident)
    assert result['complete'] and result['read_only']
    assert result['action'] == {'verb':'buy','target':'coelophysis','item':None}
    assert result['recovery_id'] == ident and result['effects'] == 'applied-confirmed'
    assert not service.recovery_required and text.dinosaur_bought
    assert before == (native.clicks, native.runs)
    assert (tmp_path/'z-failure.json').read_bytes() == diagnostic


def test_repeated_phase_exhaustion_preserves_root_identity_and_cumulative_budget(tmp_path, monkeypatch):
    text, native, service, _, _ = held_order(tmp_path, monkeypatch)
    ident = service.held_action['id']
    original = service.held_action['pending']
    text.dinosaur_order['wait_guest_ms'] = {'placement':20000}
    clicks, runs = list(native.clicks), list(native.runs)
    for _ in range(2):
        command = dispatch_continue(service)
        with pytest.raises(TimeoutError, match='guest budget') as error: dispatch_local_action(text, command)
        assert service.action_error(error.value)
        assert service.held_action['id'] == ident
        assert service.held_action['pending'] == original
        assert text.dinosaur_order['wait_guest_ms']['placement'] == 20000
    assert native.clicks == clicks and native.runs == runs
    assert not service.reconcile(ident)['complete']


def test_stale_continuation_token_cannot_send_a_dependent_input(tmp_path, monkeypatch):
    _, native, service, writer, _ = held_order(tmp_path, monkeypatch)
    clicks, runs = list(native.clicks), list(native.runs)
    request = {'op':'act','action':{'verb':'continue','target':'dinosaur-order',
                                  'item':None,'context_token':'stale'}}
    service.reader = io.StringIO(json.dumps(request)+'\n')
    with pytest.raises(EOFError): service.command()
    assert json.loads(writer.getvalue().splitlines()[-1])['status'] == 'rejected'
    assert service.recovery_required and native.clicks == clicks and native.runs == runs


def test_committed_effect_can_finish_presentation_without_another_confirmation(tmp_path, monkeypatch):
    text, native, events = shop(monkeypatch)
    service, _ = provider(tmp_path, text, events)
    text.project.debug_save_scene = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('host followup'))
    with pytest.raises(RuntimeError) as error: text.buy_dinosaur()
    assert service.action_error(error.value)
    assert text.dinosaur_order['proof'] and text.dinosaur_order['phase'] == 'confirm'
    native.view = 'placed'
    assert service.observe()['objects'][0]['id'] == 'dinosaur-order'
    text.project.debug_save_scene = lambda *a, **k: {'id':'after-view'}
    native_run = native.run
    def run(**kw):
        result = native_run(**kw)
        native.view = 'after'
        return result
    native.run = run
    clicks = list(native.clicks)
    command = dispatch_continue(service)
    service.output(dispatch_local_action(text, command)); service.finish()
    assert service.reconcile()['complete']
    assert native.clicks == clicks and native.clicks.count((188,187)) == 1


def test_an_unprocessed_continuation_never_acknowledges_progress(tmp_path, monkeypatch):
    _, native, service, writer, _ = held_order(tmp_path, monkeypatch)
    dispatch_continue(service)
    clicks, runs = list(native.clicks), list(native.runs)
    service.output('That action is not available in this scene.')
    service.finish()
    result = json.loads(writer.getvalue().splitlines()[-1])
    assert not result['complete'] and result['status'] == 'incomplete'
    assert service.recovery_required and native.clicks == clicks and native.runs == runs
