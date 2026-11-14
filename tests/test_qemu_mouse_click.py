"""Finite physical mouse clicks at the production host/QMP boundary.

The deterministic peer qualifies protocol, ownership and deadline handling.
Separate native IRQ12 witnesses qualify callbacks in their authored guest.
"""
from copy import deepcopy
from inspect import signature
import json

import pytest

from fdisbull import qemu_mouse_click
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS
from fdisbull.qemu_input import QemuPhysicalInputMixin
from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
from test_qemu_input_schedule import InputWire, scheduled
from test_qemu_io_deadlines import observation
from test_qemu_keyboard_press import change, run_with_stop
from test_qemu_keyboard_type import TextWire, enable_retrace


ARM = 'x-fdisbull-arm-mouse-click'
MS = 1_000_000


class ClickWire(InputWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.reject_arm = False
        self.running = False

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command == 'query-status' and self.running:
            self.calls.append((command, args))
            self.budgets.append(self.timeout)
            self.buffer.extend(json.dumps({'id': request['id'], 'return': {
                'running': True, 'status': 'running'}}).encode() + b'\n')
            self.delay = self.latency
            return
        if command != ARM:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        now = self.receipt['virtual-ns']
        steps = [
            dict(button=args['button'], down=True,
                 **{'delay-ns': 2 * MS, 'deadline-ns': now + 2 * MS}),
            dict(button=args['button'], down=False, **{'delay-ns': args['hold-ms'] * MS}),
        ]
        self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed', 'virtual-ns': now,
            'token': args['token'], 'start-ns': now, 'deadline-ns': now + 2 * MS,
            'event-count': 2, 'click': dict(button=args['button'], steps=steps,
                **{'hold-ms': args['hold-ms'], 'dispatched-count': 0})}
        answer = ({'error': {'class': 'GenericError', 'desc': 'Mouse handler lost ownership'}}
                  if self.reject_arm else {'return': self.mutate(deepcopy(self.input))})
        self.buffer.extend(json.dumps(dict(id=request['id'], **answer)).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)

    def stop_after(self, count, *, lateness=0, stopped_ns=None, reason='machine-stop'):
        if 'click' not in self.input:
            return super().stop_after(count, lateness=lateness, stopped_ns=stopped_ns, reason=reason)
        click = self.input['click']
        steps = click['steps']
        for index in range(click['dispatched-count'], count):
            extra = lateness[index] if isinstance(lateness, (tuple, list)) else lateness
            actual = steps[index]['deadline-ns'] + extra
            steps[index]['dispatch-ns'] = actual
            self.receipt['virtual-ns'] = actual
            click['dispatched-count'] = index + 1
            if index + 1 < len(steps):
                steps[index + 1]['deadline-ns'] = actual + steps[index + 1]['delay-ns']
        terminal = self.receipt['virtual-ns'] if stopped_ns is None else stopped_ns
        if count == 2:
            self.input.update(state='dispatched', reason='dispatch-complete',
                **{'dispatch-ns': steps[-1]['dispatch-ns'], 'terminal-ns': steps[-1]['dispatch-ns']})
        else:
            self.input.update(state='cancelled', reason=reason, **{'terminal-ns': terminal})
        self.receipt['virtual-ns'] = terminal


@pytest.fixture
def click(scheduled):
    o = scheduled
    o.wire = ClickWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= {ARM}
    o.session.capabilities['virtual_mouse_click'] = True
    return o


def test_timed_click_host_signature_is_narrow_and_defaults_to_left():
    method = QemuPhysicalInputMixin.mouse_button_click
    assert str(signature(method)) == "(self, button='left', *, hold_ms=80)"


@pytest.mark.parametrize('button', ['left', 'middle', 'right'])
@pytest.mark.parametrize('hold_ms', [1, 80, 1000])
def test_click_arms_two_passive_edges_with_one_paired_mouse_lease(click, button, hold_ms):
    o = click
    result = o.session.mouse_button_click(button, hold_ms=hold_ms)
    assert result['state'] == 'armed' and result['edge_count'] == 2
    assert result['click']['format'] == 'fdisbull-mouse-click-1'
    assert result['click']['button'] == button and result['click']['hold_ms'] == hold_ms
    assert result['click']['dispatched_count'] == 0 and result['click']['undispatched_count'] == 2
    assert result['lateness_ns'] is result['dispatch_ns'] is result['terminal_ns'] is None
    assert result['native']['click']['steps'] == [
        dict(button=button, down=True, **{'delay-ns': 2 * MS, 'deadline-ns': 2 * MS + 1000}),
        dict(button=button, down=False, **{'delay-ns': hold_ms * MS}),
    ]
    state = o.session.input_state()
    assert state['pending_edges'] == 2 and len(state['leases']) == 1
    lease = next(iter(state['leases']))
    assert state['leases'][lease] == dict(device='mouse', button=button,
                                        make='python_pending', release='python_pending')
    assert [step['lease'] for step in result['click']['steps']] == [lease, lease]
    assert [step['sequence'] for step in result['click']['steps']] == result['sequences']
    assert all(step['dispatch_ns'] is step['lateness_ns'] is None for step in result['click']['steps'])
    assert all(record['event']['type'] == 'btn' for record in state['pending'])
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-arm-clock-budget')
                   for name, _ in o.wire.calls)
    assert o.session.input_schedule_observe()['click'] == result['click']


def test_default_click_is_left_for_80ms_without_a_coordinate_contract(click):
    result = click.session.mouse_button_click()
    assert result['click']['button'] == 'left' and result['click']['hold_ms'] == 80
    assert 'no requested movement' in result['click']['claim']
    assert 'pre-existing native motion' in result['click']['claim']
    assert result['guest_consumed'] is result['device_queue_accepted'] is None


def test_full_click_uses_actual_down_callback_as_release_origin_and_has_no_tail(click):
    o = click
    armed = o.session.mouse_button_click('right', hold_ms=23)
    run_with_stop(o, lambda: o.wire.stop_after(2, lateness=[123, 456]))
    result = o.session.run(timeout_ms=1000)
    delivered = result['input_delivery']
    down, up = delivered['click']['steps']
    assert delivered['state'] == 'dispatched' and delivered['lateness_ns'] is None
    assert down['deadline_ns'] == armed['start_ns'] + 2 * MS
    assert up['deadline_ns'] == down['dispatch_ns'] + 23 * MS
    assert [down['lateness_ns'], up['lateness_ns']] == [123, 456]
    assert delivered['dispatch_ns'] == delivered['terminal_ns'] == up['dispatch_ns']
    assert delivered['terminal_ns'] == armed['start_ns'] + 25 * MS + 579
    assert delivered['click']['dispatched_count'] == 2 and delivered['click']['undispatched_count'] == 0
    assert not delivered['requires_resolution']
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert o.session.input_schedule_observe()['native'] == delivered['native']
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    following = o.session.mouse_button_click('middle')
    assert following['token'] != armed['token'] and following['sequences'] == [3, 4]


class ButtonString(str):
    pass


class HoldInteger(int):
    pass


@pytest.mark.parametrize('options', [
    {'button': 'LEFT'}, {'button': ''}, {'button': 'wheel-up'}, {'button': 'side'},
    {'button': 1}, {'button': True}, {'button': None}, {'button': []},
    {'button': ButtonString('left')}, {'hold_ms': True}, {'hold_ms': False},
    {'hold_ms': 0}, {'hold_ms': -1}, {'hold_ms': 1001}, {'hold_ms': 1.5},
    {'hold_ms': '80'}, {'hold_ms': None}, {'hold_ms': HoldInteger(80)},
])
def test_invalid_click_is_atomic_before_native_admission(click, options):
    o = click
    before = o.session.input_state()
    with pytest.raises(ValueError):
        o.session.mouse_button_click(**options)
    assert o.wire.calls == [] and o.session.input_state() == before and not o.vm.closed


def test_extra_positional_argument_is_rejected_before_admission(click):
    with pytest.raises(TypeError):
        click.session.mouse_button_click('left', 80)
    assert not click.wire.calls and not click.vm.closed


@pytest.mark.parametrize('refusal', ['profile', 'transaction', 'pending', 'held', 'armed'])
def test_click_preflight_cannot_take_over_existing_input(click, refusal):
    o = click
    if refusal == 'profile':
        o.vm.machine_configuration['clock_profile']['profile'] = 'standard'
    elif refusal in ('pending', 'held'):
        o.session.mouse_button_down('right')
        if refusal == 'held':
            o.session.input_schedule(1000)
            o.wire.finish()
            o.session.input_schedule_observe()
    elif refusal == 'armed':
        o.session.mouse_button_click('middle')
    calls = list(o.wire.calls)
    before = o.session.input_state()
    if refusal == 'transaction':
        with o.project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                o.session.mouse_button_click()
    else:
        with pytest.raises(ValueError):
            o.session.mouse_button_click()
    assert o.wire.calls == calls and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('command', sorted(
    VIRTUAL_CLOCK_COMMANDS | INPUT_SCHEDULE_COMMANDS | {ARM, 'input-send-event'}))
def test_every_required_command_is_checked_before_any_native_io(click, command):
    o = click
    o.vm.qmp_commands -= {command}
    before = o.session.input_state()
    with pytest.raises(ValueError, match='Timed mouse clicks'):
        o.session.mouse_button_click()
    assert not o.wire.calls and o.session.input_state() == before and not o.vm.closed


def test_running_owner_refuses_before_arming_or_creating_lease(click):
    o = click
    o.wire.running = True
    before = o.session.input_state()
    with pytest.raises(ValueError, match='Pause'):
        o.session.mouse_button_click()
    assert o.wire.calls == [('query-status', {})]
    assert o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('prefix', [0, 1])
def test_stop_cancels_suffix_retains_delivered_hold_and_requires_explicit_recovery(click, prefix):
    o = click
    armed = o.session.mouse_button_click('middle', hold_ms=19)
    run_with_stop(o, lambda: o.wire.stop_after(prefix))
    result = o.session.run(timeout_ms=1000)
    receipt = result['input_delivery']
    assert receipt['state'] == 'cancelled' and receipt['dispatch_ns'] is None
    assert receipt['click']['dispatched_count'] == prefix and receipt['requires_resolution'] is True
    state = o.session.input_state()
    assert state['pending_edges'] == 2 - prefix and len(state['leases']) == 1
    lease = armed['click']['steps'][0]['lease']
    assert state['leases'][lease]['make'] == ('native_dispatched' if prefix else 'python_pending')
    assert o.session.input_schedule_observe()['native'] == receipt['native']
    assert o.session.input_state()['pending'] == state['pending']
    assert o.session.input_state()['leases'] == state['leases']
    with pytest.raises(ValueError, match='reschedule or cancel'):
        o.session._execution_preflight('c', 1000)
    with pytest.raises(ValueError, match='cannot be rescheduled'):
        o.session.input_schedule(1000)
    with pytest.raises(ValueError):
        o.session.mouse_button_click('left')
    calls = list(o.wire.calls)
    cancelled = o.session.input_cancel_pending()
    assert cancelled['cancelled_edges'] == 2 - prefix
    remaining = o.session.input_state()['leases']
    assert set(remaining) == ({lease} if prefix else set())
    assert not any(name == 'x-fdisbull-cancel-input' for name, _ in o.wire.calls[len(calls):])
    if prefix:
        assert remaining[lease] == dict(device='mouse', button='middle', make='native_dispatched', release=None)
        with pytest.raises(ValueError, match='held leases'):
            o.session.mouse_button_click()
        with pytest.raises(ValueError, match='unused physical input lease'):
            o.session.keyboard_key_up(lease)
        o.session.mouse_button_up(lease)
        released = o.session.input_schedule(1000)
        assert 'click' not in released['native']
        o.wire.finish()
        o.session.input_schedule_observe()
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert o.session.mouse_button_click()['state'] == 'armed'
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


def test_explicit_cancel_before_down_disarms_and_discards_the_paired_lease(click):
    o = click
    armed = o.session.mouse_button_click()
    result = o.session.input_cancel_pending()
    assert result['cancelled_edges'] == 2
    assert result['cancelled_leases'] == [armed['click']['steps'][0]['lease']]
    assert not result['retained_dispatched_holds']
    assert o.wire.input['state'] == 'cancelled' and o.wire.input['click']['dispatched-count'] == 0
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-cancel-input') == 1
    assert not o.session.input_state()['leases'] and not o.vm.closed


@pytest.mark.parametrize(('path', 'replacement'), [
    (('click', 'button'), 'right'), (('click', 'hold-ms'), True),
    (('click', 'hold-ms'), 81), (('click', 'dispatched-count'), True),
    (('click', 'dispatched-count'), -1), (('click', 'dispatched-count'), 3),
    (('click', 'steps', 0, 'button'), 'middle'), (('click', 'steps', 1, 'down'), True),
    (('click', 'steps', 0, 'down'), 1), (('click', 'steps', 0, 'delay-ns'), 1),
    (('click', 'steps', 0, 'deadline-ns'), 2 * MS + 1001),
    (('click', 'steps', 1, 'deadline-ns'), 82 * MS + 1000),
    (('click', 'steps', 0, 'dispatch-ns'), 2 * MS + 1000),
    (('click', 'steps'), []), (('click', 'extra'), 1), (('extra',), 1),
    (('press',), {}), (('typing',), {}), (('retrace',), {}),
])
def test_malformed_arm_cannot_publish_candidate_mouse_ownership(click, path, replacement):
    o = click
    o.wire.mutate = lambda value: change(value, path, replacement) if 'click' in value else value
    with pytest.raises(DebuggerError) as raised:
        o.session.mouse_button_click()
    assert o.vm.closed and not o.session.input_state()['valid']
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert o.vm._physical_input['sequence'] == 0
    assert raised.value.result['native']['click']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


@pytest.mark.parametrize('fault', [
    'missing-dispatch', 'missing-next-deadline', 'premature-release-dispatch',
    'absolute-next-deadline', 'early-dispatch', 'future-dispatch', 'late-terminal',
    'count-mismatch', 'top-dispatch-on-cancel', 'completed-cancel', 'short-completion',
])
def test_malformed_callback_prefix_is_rejected_before_host_lease_commit(click, fault, monkeypatch):
    o = click
    armed = o.session.mouse_button_click()
    o.wire.stop_after(1, lateness=123)
    value = o.wire.input
    steps = value['click']['steps']
    if fault == 'missing-dispatch':
        del steps[0]['dispatch-ns']
    elif fault == 'missing-next-deadline':
        del steps[1]['deadline-ns']
    elif fault == 'premature-release-dispatch':
        steps[1]['dispatch-ns'] = steps[1]['deadline-ns']
    elif fault == 'absolute-next-deadline':
        steps[1]['deadline-ns'] -= 123
    elif fault == 'early-dispatch':
        steps[0]['dispatch-ns'] = steps[0]['deadline-ns'] - 1
    elif fault == 'future-dispatch':
        steps[0]['dispatch-ns'] = o.wire.receipt['virtual-ns'] + 1
    elif fault == 'late-terminal':
        value['terminal-ns'] = steps[0]['dispatch-ns'] - 1
    elif fault == 'count-mismatch':
        value['click']['dispatched-count'] = 0
    elif fault == 'top-dispatch-on-cancel':
        value['dispatch-ns'] = steps[0]['dispatch-ns']
    elif fault == 'completed-cancel':
        o.wire.stop_after(2)
        value.update(state='cancelled', reason='machine-stop')
        del value['dispatch-ns']
    elif fault == 'short-completion':
        value.update(state='dispatched', reason='dispatch-complete', **{'dispatch-ns': steps[0]['dispatch-ns']})
    committed = []
    monkeypatch.setattr(o.session, '_input_mark_click_prefix_dispatched', lambda *args: committed.append(args))
    with pytest.raises(DebuggerError) as raised:
        o.session.input_schedule_observe()
    assert not committed and o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['native']['token'] == armed['token']


@pytest.mark.parametrize('fault', ['grow', 'regress', 'rewrite'])
def test_cancelled_callback_prefix_and_known_times_are_frozen(click, fault):
    o = click
    o.session.mouse_button_click()
    o.wire.stop_after(1)
    o.session.input_schedule_observe()
    if fault == 'grow':
        o.wire.stop_after(2)
    elif fault == 'regress':
        o.wire.input['click']['dispatched-count'] = 0
        del o.wire.input['click']['steps'][0]['dispatch-ns']
        del o.wire.input['click']['steps'][1]['deadline-ns']
    else:
        o.wire.input['click']['steps'][0]['dispatch-ns'] += 1
        o.wire.input['click']['steps'][1]['deadline-ns'] += 1
        o.wire.input['terminal-ns'] += 1
        o.wire.receipt['virtual-ns'] += 1
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed and not o.session.input_state()['leases']


@pytest.mark.parametrize('fault', ['wrong-device', 'wrong-button', 'release-lost', 'second-edge-corrupt'])
def test_click_ledger_reconciliation_is_atomic_and_mouse_specific(click, fault):
    o = click
    o.session.mouse_button_click()
    state = deepcopy(o.vm._physical_input)
    records = deepcopy(state['pending'])
    lease = next(iter(state['leases']))
    if fault == 'wrong-device':
        state['leases'][lease]['device'] = 'keyboard'
    elif fault == 'wrong-button':
        state['leases'][lease]['button'] = 'right'
    elif fault == 'release-lost':
        state['leases'][lease]['release'] = None
    else:
        records[1]['event']['data']['button'] = 'right'
        state['pending'] = deepcopy(records)
    before = deepcopy(state)
    with pytest.raises(DebuggerError):
        o.session._input_mark_click_prefix_dispatched(state, records, 'native_dispatched')
    assert state == before


def test_keyboard_prefix_guard_still_rejects_mouse_lease(click):
    o = click
    o.session.mouse_button_click()
    state = deepcopy(o.vm._physical_input)
    before = deepcopy(state)
    with pytest.raises(DebuggerError, match='keyboard lease'):
        o.session._input_mark_prefix_dispatched(state, state['pending'][:1], 'native_dispatched')
    assert state == before


@pytest.mark.parametrize('fault', ['native-failed', 'malformed', 'persistence'])
def test_prefix_failure_keeps_original_stop_and_raw_native_receipt(click, monkeypatch, fault):
    o = click
    armed = o.session.mouse_button_click()

    def callback():
        o.wire.stop_after(1)
        if fault == 'native-failed':
            o.wire.input.update(state='failed', reason='Selected mouse handler changed')
        elif fault == 'malformed':
            o.wire.input['click']['steps'][0]['button'] = 'right'

    if fault == 'persistence':
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-result':
                raise OSError('Authored mouse click result persistence failure')
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    run_with_stop(o, callback)
    with pytest.raises(OSError if fault == 'persistence' else DebuggerError) as raised:
        o.session.run(timeout_ms=1000)
    result = raised.value.result
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['timed_out'] is False
    assert result['input_schedule_native']['token'] == armed['token']
    assert result['input_schedule_native']['click'] == o.wire.input['click']
    assert o.vm.closed and not o.session.input_state()['valid']


@pytest.mark.parametrize(('count', 'budget_ns', 'accepted'), [
    (1, 2 * MS, False), (2, 9 * MS, False), (1, 4 * MS, True),
])
def test_owned_budget_cutoff_validates_down_and_release_before_lease_commit(click, count, budget_ns, accepted):
    o = click
    o.session.mouse_button_click(hold_ms=7)

    def callback():
        cutoff = o.wire.receipt['budget-deadline-ns']
        o.wire.stop_after(count, stopped_ns=cutoff, reason='budget-deadline')
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-fired-ns': cutoff,
                              'budget-stopped-ns': cutoff})

    run_with_stop(o, callback, reply=b'T02thread:1;')
    if not accepted:
        with pytest.raises(DebuggerError, match='budget cutoff') as raised:
            o.session.clock_advance(budget_ns, timeout_ms=1000)
        assert raised.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert o.vm.closed and not o.session.input_state()['valid']
    else:
        result = o.session.clock_advance(budget_ns, timeout_ms=1000)
        assert result['input_delivery']['click']['dispatched_count'] == 1
        assert result['input_delivery']['state'] == 'cancelled'
        state = o.session.input_state()
        assert [lease['make'] for lease in state['leases'].values()] == ['native_dispatched']
        assert result['input_delivery']['requires_resolution'] is True and not o.vm.closed


@pytest.mark.parametrize('fault', ['lost-arm', 'rejected-arm', 'persistence', 'persistence-overrun', 'final-copy'])
def test_uncertain_or_late_arm_closes_without_replay(click, monkeypatch, fault):
    o = click
    o.session._rpc_deadline = o.clock.now + .05
    if fault == 'lost-arm':
        o.wire.extra_latency[ARM] = 1
    elif fault == 'rejected-arm':
        o.wire.reject_arm = True
    elif fault == 'final-copy':
        original = qemu_mouse_click.deepcopy

        def copy(value):
            result = original(value)
            if isinstance(value, dict) and value.get('format') == 'fdisbull-qemu-scheduled-input-1':
                o.clock.advance(.05)
            return result

        monkeypatch.setattr(qemu_mouse_click, 'deepcopy', copy)
    else:
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-arm':
                if fault == 'persistence':
                    raise OSError('Authored click evidence failure')
                o.clock.advance(.05)
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    expected = (DebuggerError if fault == 'rejected-arm' else OSError if fault == 'persistence' else TimeoutError)
    with pytest.raises(expected) as raised:
        o.session.mouse_button_click()
    assert raised.value.result
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert o.vm.closed and not o.vm._physical_input['valid']
    assert not o.vm._physical_input['leases'] and not o.vm._physical_input['pending']
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)
    assert o.vm.operation_deadline is None and o.qmp.operation_deadline is None


def test_one_deadline_spans_admission_and_native_arm_reply(click):
    o = click
    o.session._rpc_deadline = o.clock.now + .05
    o.wire.latency = .006
    o.wire.extra_latency[ARM] = .03
    with pytest.raises(TimeoutError):
        o.session.mouse_button_click()
    assert o.clock.now == pytest.approx(100.05)
    assert o.wire.calls[-1][0] == ARM and o.wire.budgets[-1] < .03
    assert o.wire.budgets == sorted(o.wire.budgets, reverse=True)
    assert o.vm.closed


def test_direct_click_uses_1000ms_host_bound_and_restores_tighter_incoming_limits(click):
    o = click
    o.wire.latency = .001
    o.vm.operation_deadline = o.clock.now + .4
    o.qmp.operation_deadline = o.clock.now + .3
    o.gdb.operation_deadline = o.clock.now + .2
    o.session.mouse_button_click()
    assert o.wire.budgets[0] == pytest.approx(.2)
    assert max(o.wire.budgets) <= .2 + 1e-12
    assert o.vm.operation_deadline == pytest.approx(100.4)
    assert o.qmp.operation_deadline == pytest.approx(100.3)
    assert o.gdb.operation_deadline == pytest.approx(100.2)


def test_default_arm_bound_is_one_second(click):
    click.session.mouse_button_click()
    assert click.wire.budgets[0] == pytest.approx(1)
    assert max(click.wire.budgets) <= 1


@pytest.mark.parametrize('expired', [False, True])
def test_lock_admission_expiry_preserves_owner_without_native_io(click, expired):
    o = click
    before = o.session.input_state()
    o.session._rpc_deadline = o.clock.now + (0 if expired else .05)
    waits = []

    class BusyLock:
        def acquire(self, *, timeout):
            assert not expired
            waits.append(timeout)
            o.clock.advance(timeout)
            return False

    original = o.vm.lock
    o.vm.lock = BusyLock()
    try:
        with pytest.raises(TimeoutError):
            o.session.mouse_button_click()
    finally:
        o.vm.lock = original
        o.session._rpc_deadline = None
    assert waits == ([] if expired else pytest.approx([.05]))
    assert not o.wire.calls and o.session.input_state() == before and not o.vm.closed


def test_signed_nominal_horizon_overflow_refuses_before_arm_or_lease(click):
    o = click
    o.wire.receipt['virtual-ns'] = (1 << 63) - 2 * MS
    with pytest.raises(ValueError, match='horizon'):
        o.session.mouse_button_click()
    assert not any(name == ARM for name, _ in o.wire.calls)
    assert not o.session.input_state()['pending'] and not o.session.input_state()['leases']
    assert not o.vm.closed


class AllInputWire(ClickWire, TextWire):
    pass


def enable_all_modes(o):
    o.wire = AllInputWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= {'x-fdisbull-arm-keyboard-press', 'x-fdisbull-arm-keyboard-type'}
    o.session.capabilities.update(virtual_keyboard_press=True, virtual_keyboard_type=True)
    enable_retrace(o)


@pytest.mark.parametrize('mode', ['idle', 'ordinary', 'press', 'typing', 'retrace'])
def test_click_descriptor_is_rejected_on_every_other_schedule_mode(click, mode):
    o = click
    enable_all_modes(o)
    if mode in ('ordinary', 'retrace'):
        o.session.keyboard_key_down('a')
        if mode == 'ordinary':
            o.session.input_schedule(1000)
        else:
            o.session.input_schedule_retrace()
    elif mode == 'press':
        o.session.keyboard_press('a')
    elif mode == 'typing':
        o.session.keyboard_type('a')
    o.wire.input['click'] = {}
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed


def test_other_modes_cannot_convert_click_suffix_and_clear_descriptor_after_recovery(click):
    o = click
    enable_all_modes(o)
    o.session.mouse_button_click()
    o.wire.stop_after(1)
    o.session.input_schedule_observe()
    with pytest.raises(ValueError, match='cannot be rescheduled'):
        o.session.input_schedule_retrace()
    with pytest.raises(ValueError):
        o.session.keyboard_press('a')
    with pytest.raises(ValueError):
        o.session.keyboard_type('a')
    o.session.input_cancel_pending()
    lease = next(iter(o.session.input_state()['leases']))
    o.session.mouse_button_up(lease)
    retrace = o.session.input_schedule_retrace()
    assert 'click' not in retrace['native'] and 'retrace' in retrace['native']
    o.wire.callback()
    o.session.input_schedule_observe()
    assert not o.session.input_state()['leases']
    for arm, mode in ((lambda: o.session.keyboard_press('a'), 'press'),
                      (lambda: o.session.keyboard_type('a'), 'typing'),
                      (lambda: o.session.mouse_button_click(), 'click')):
        result = arm()
        assert {key for key in ('press', 'typing', 'click', 'retrace') if key in result['native']} == {mode}
        o.session.input_cancel_pending()
    o.session.mouse_button_down('right')
    ordinary = o.session.input_schedule(1000)
    assert not any(mode in ordinary['native'] for mode in ('press', 'typing', 'click', 'retrace'))
