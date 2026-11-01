"""Real debugger dispatch under a shared deadline, without a native process."""
from types import SimpleNamespace

import pytest

from fdisbull import debugger, dinopark_purchase as purchase
from fdisbull.dinopark_scenes import BankInputSession


def native_with_slow_rpc(monkeypatch):
    now, calls, closed = [0.0], [], []
    monkeypatch.setattr(debugger.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(purchase, '_clock', lambda: now[0])
    session = debugger.DebugSession.__new__(debugger.DebugSession)
    session.closed, session.session_id = False, 'owned-native'
    running = [False]
    def call(method, params=None, timeout_ms=15000):
        # Each reply fits its individual allowance; aggregate time still matters.
        assert timeout_ms >= 3000
        now[0] += 3
        calls.append((method, timeout_ms))
        if method == 'execution.continue':
            running[0] = True
            return {'operation_id': 'run'}
        if method == 'execution.pause':
            running[0] = False
            return {'operation_id': 'pause'}
        if method == 'execution.wait':
            return ({'running': True} if running[0] else
                    {'running': False, 'state': 'stopped', 'stop_reason': {'kind': 'pause'}})
        if method == 'execution.timing': return {'guest_ticks': 0, 'fast_forward': False}
        return {}
    session.rpc = SimpleNamespace(call=call, capabilities={'timing': {'fast_forward': True}})
    session.close = lambda: closed.append(True)
    return session, now, calls, closed, running


def test_forwarding_wrapper_binds_the_real_native_rpc_deadline(monkeypatch):
    native, now, calls, _, _ = native_with_slow_rpc(monkeypatch)
    wrapper = BankInputSession(native, lambda value: None)
    with purchase.PurchaseBudget().bind(wrapper):
        with pytest.raises(TimeoutError, match='before RPC dispatch'):
            for _ in range(30): wrapper.call('memory.read')
        assert native._rpc_deadline == 40
        assert '_rpc_deadline' not in vars(wrapper)
        assert now[0] == 36 and len(calls) == 12
        assert all(timeout == 5000 for _, timeout in calls)
    assert native._rpc_deadline is None and native._rpc_admission_ms is None


def test_expired_operation_can_pause_within_reserved_cleanup_window(monkeypatch):
    native, now, calls, closed, running = native_with_slow_rpc(monkeypatch)
    with purchase.PurchaseBudget().bind(BankInputSession(native, lambda value: None)):
        with pytest.raises(TimeoutError, match='before RPC dispatch'):
            native.run(timeout_ms=600000, fast_forward=True)
        assert not running[0] and not closed
        assert [method for method, _ in calls[-3:]] == [
            'execution.pause', 'execution.wait', 'execution.timing']
        assert all(timeout <= 3000 for _, timeout in calls[-3:])
        assert now[0] <= 45
        assert native._rpc_deadline == 40 and native._rpc_admission_ms == 5000
    assert native._rpc_deadline is None


def test_nested_purchase_uses_the_earlier_request_deadline(monkeypatch):
    native, now, calls, _, _ = native_with_slow_rpc(monkeypatch)
    with purchase.PurchaseBudget().bind(native):
        now[0] = 10
        nested = purchase.PurchaseBudget()
        with nested.bind(BankInputSession(native, lambda value: None)):
            assert nested.deadline == native._rpc_deadline == 40
            now[0] = 36
            with pytest.raises(TimeoutError): nested.timeout()
    assert not calls


@pytest.mark.parametrize('dispatched', [False, True])
def test_press_preserves_ticket_only_when_dispatch_was_definitely_refused(monkeypatch, dispatched):
    from copy import deepcopy
    from fdisbull.dinopark_scenes import TextScene
    native, now, calls, _, _ = native_with_slow_rpc(monkeypatch)
    previous = {'phase':'order', 'last_input_phase':'order',
                'last_input':{'accepted':True,'delivery':'queued','operation_id':'original-order'}}
    text = SimpleNamespace(debug=native, dinosaur_order={'id':'same-order', **deepcopy(previous)})
    def event(value):
        if value['phase'] == 'shop_input_intent': now[0] = 36
    text.event = event
    text.shop_click = lambda point, ms, name: TextScene.shop_click(text, point, ms, name)
    if dispatched:
        def uncertain_rpc(*a, **k):
            calls.append('input.mouse.click')
            raise TimeoutError('Transport failed after dispatch')
        native.rpc.call = uncertain_rpc
        text.event = lambda value: None
    with purchase.PurchaseBudget().bind(native) as _:
        with pytest.raises(TimeoutError):
            purchase._press(text, purchase.PurchaseBudget(), 'place', (42,50), 'place')
    if dispatched:
        assert calls == ['input.mouse.click']
        assert text.dinosaur_order['phase'] == 'place' and text.dinosaur_order['last_input'] is None
    else:
        assert not calls
        assert {key:text.dinosaur_order[key] for key in previous} == previous
@pytest.mark.parametrize('outer,timeout,expected',[(None,15000,15),(40,15000,15),(4,15000,4)])
def test_composed_request_deadline_never_widens_incoming_or_outer_allowance(monkeypatch,outer,timeout,expected):
    from types import SimpleNamespace
    from fdisbull import operation_budget
    monkeypatch.setattr(operation_budget.time,'monotonic',lambda:0)
    session=SimpleNamespace(_rpc_deadline=outer)
    assert operation_budget.request_deadline(session,timeout)==expected
    assert session._rpc_deadline==outer


@pytest.mark.parametrize('timeout',[True,0,600001])
def test_composed_request_deadline_rejects_invalid_allowance(timeout):
    from types import SimpleNamespace
    from fdisbull.operation_budget import request_deadline
    with pytest.raises(ValueError):request_deadline(SimpleNamespace(),timeout)

