"""Scheduled-input ownership at the production QMP envelope.

These deterministic peers exercise protocol, deadlines and public routing.
Actual timer dispatch and guest consumption have independent native witnesses.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from test_qemu_clock_budget import NativeWire
from test_qemu_io_deadlines import observation


COMMANDS = frozenset(('x-fdisbull-arm-input', 'x-fdisbull-query-input',
                      'x-fdisbull-cancel-input'))


class InputWire(NativeWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.input = {'api-version': 1, 'epoch': 1, 'state': 'idle',
                      'virtual-ns': 1000, 'event-count': 0}
        self.mutate = lambda value: value
        self.extra_latency = {}

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in COMMANDS:
            super().sendall(data)
            self.delay += self.extra_latency.get(command, 0)
            return
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-arm-input':
            now = self.receipt['virtual-ns']
            self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed',
                          'virtual-ns': now, 'token': args['token'],
                          'start-ns': now, 'deadline-ns': now + args['delta-ns'],
                          'event-count': len(args['events'])}
        elif command == 'x-fdisbull-cancel-input' and self.input['state'] == 'armed':
            assert args['token'] == self.input['token']
            self.input.update(state='cancelled', reason='caller',
                              **{'terminal-ns': self.receipt['virtual-ns']})
        self.input['virtual-ns'] = self.receipt['virtual-ns']
        value = self.mutate(deepcopy(self.input))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)

    def finish(self, state='dispatched', *, now=None):
        now = self.input['deadline-ns'] if now is None else now
        self.receipt['virtual-ns'] = now
        self.input.update(state=state, reason='dispatch-complete' if state == 'dispatched' else 'machine-stop',
                          **{'terminal-ns': now})
        if state == 'dispatched':
            self.input['dispatch-ns'] = now


@pytest.fixture
def scheduled(observation):
    o = observation
    o.wire = InputWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    o.vm.qmp_commands = COMMANDS | VIRTUAL_CLOCK_COMMANDS | {'input-send-event'}
    o.session.capabilities.update(virtual_input_schedule=True, virtual_clock_budget=True)
    return o


def test_arm_is_passive_and_cancel_disarms_before_forgetting_unsent_edges(scheduled):
    o = scheduled
    lease = o.session.keyboard_key_down('a')['lease']
    started = o.session.input_schedule(2_000_000)
    assert started['state'] == 'armed' and started['guest_consumed'] is None
    assert started['deadline_ns'] == started['start_ns'] + 2_000_000
    assert o.session.input_state()['pending_edges'] == 1
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)
    result = o.session.input_cancel_pending()
    assert o.wire.input['state'] == 'cancelled'
    assert result['cancelled_leases'] == [lease]
    assert o.session.input_state()['pending_edges'] == 0
    assert not o.vm.closed


def test_dispatch_applies_held_lease_once_and_never_replays_the_batch(scheduled):
    o = scheduled
    lease = o.session.keyboard_key_down('a')['lease']
    started = o.session.input_schedule(1000)
    o.wire.finish()
    delivered = o.session.input_schedule_observe()
    assert delivered['state'] == 'dispatched' and delivered['token'] == started['token']
    assert o.session.input_state()['pending_edges'] == 0
    assert o.session.input_state()['leases'][lease]['make'] == 'native_dispatched'
    assert o.session.input_schedule_observe()['native'] == delivered['native']
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


def test_early_stop_requires_explicit_reschedule_or_cancel(scheduled):
    o = scheduled
    lease = o.session.keyboard_key_down('a')['lease']
    first = o.session.input_schedule(2_000_000)
    o.wire.finish('cancelled', now=1100)
    observed = o.session.input_schedule_observe()
    assert observed['requires_resolution'] is True
    with pytest.raises(ValueError, match='reschedule or cancel'):
        o.session._execution_preflight('c', 1000)
    with pytest.raises(ValueError, match='scheduled'):
        o.session.keyboard_key_up(lease)
    again = o.session.input_schedule(3_000_000)
    assert again['token'] != first['token'] and again['start_ns'] == 1100
    o.session._execution_preflight('c', 1000)
    o.session.input_cancel_pending()
    o.session._execution_preflight('c', 1000)


@pytest.mark.parametrize('delta', [True, 0, -1, 60_000_000_001, 1.5])
def test_invalid_schedule_delay_does_not_touch_qmp(scheduled, delta):
    o = scheduled
    with pytest.raises(ValueError, match='delta_ns'):
        o.session.input_schedule(delta)
    assert o.wire.calls == []


def test_whole_script_preflights_schedule_before_earlier_input(scheduled):
    o = scheduled
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='keyboard.key-down', key='a'), dict(op='input-schedule', delta_ns=0)])
    with pytest.raises(ValueError, match='delta_ns'):
        validate_script(script, session=o.session)
    assert o.wire.calls == []


@pytest.mark.parametrize('mutation', [
    {'api-version': True}, {'epoch': 2}, {'virtual-ns': 999}, {'event-count': True},
    {'state': 'invalidated'}, {'token': 'unowned'}, {'event-count': 1},
])
def test_malformed_idle_receipt_closes_owner(scheduled, mutation):
    o = scheduled
    o.wire.mutate = lambda value: dict(value, **mutation)
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed and not o.session.input_state()['valid']


@pytest.mark.parametrize('mutation', [
    {'token': 'another-owner'}, {'start-ns': 999}, {'deadline-ns': 2001},
    {'event-count': 2}, {'terminal-ns': 1000}, {'dispatch-ns': 1000},
    {'state': 'dispatched', 'terminal-ns': 1000, 'dispatch-ns': 1000, 'reason': 'early'},
    {'state': 'cancelled', 'terminal-ns': 1000},
])
def test_malformed_owned_schedule_cannot_change_lease_delivery(scheduled, mutation):
    o = scheduled
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    o.wire.mutate = lambda value: dict(value, **mutation)
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed and not o.session.input_state()['valid']


def test_unsolicited_native_schedule_is_not_adopted(scheduled):
    o = scheduled
    o.wire.input.update(state='armed', token='unowned', **{
        'start-ns': 1000, 'deadline-ns': 2000, 'event-count': 1})
    with pytest.raises(DebuggerError, match='identity'):
        o.session.input_schedule_observe()
    assert o.vm.closed


def test_terminal_receipt_cannot_change_reason_or_dispatch_time(scheduled):
    o = scheduled
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    o.wire.finish()
    o.session.input_schedule_observe()
    o.wire.input['reason'] = 'different'
    with pytest.raises(DebuggerError, match='Terminal'):
        o.session.input_schedule_observe()
    assert o.vm.closed


def test_native_callback_failure_closes_without_requeue(scheduled):
    o = scheduled
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    o.wire.finish('failed')
    o.wire.input['reason'] = 'selected handler changed'
    with pytest.raises(DebuggerError, match='dispatch failed'):
        o.session.input_schedule_observe()
    assert o.vm.closed and o.session.input_state()['pending_edges'] == 0


@pytest.mark.parametrize('command', ['x-fdisbull-arm-input', 'x-fdisbull-cancel-input'])
def test_lost_mutation_reply_closes_without_replay(scheduled, command):
    o = scheduled
    o.session.keyboard_key_down('a')
    if command.endswith('cancel-input'):
        o.session.input_schedule(1000)
    o.wire.extra_latency[command] = 1000
    with pytest.raises(TimeoutError):
        if command.endswith('arm-input'):
            o.session.input_schedule(1000)
        else:
            o.session.input_cancel_pending()
    assert o.vm.closed and o.wire.socket_closed
    assert [name for name, _ in o.wire.calls].count(command) == 1
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


def test_one_script_deadline_is_preserved_across_schedule_admission(scheduled):
    o = scheduled
    o.session.keyboard_key_down('a')
    o.wire.calls.clear()
    o.wire.budgets.clear()
    o.wire.latency = .03
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='input-schedule', delta_ns=1000)])
    result = execute_script(o.session, script, timeout_ms=50)
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    assert o.wire.budgets == pytest.approx([.05, .02])
    assert not any(name == 'x-fdisbull-arm-input' for name, _ in o.wire.calls)
    assert o.vm.closed


@pytest.mark.parametrize('failure', ['raise', 'overrun'])
def test_evidence_failure_after_arm_cannot_leave_live_unreported_timer(scheduled, monkeypatch, failure):
    o = scheduled
    o.session.keyboard_key_down('a')
    event = o.session._event
    def record(operation, value):
        if operation == 'input.schedule-arm':
            if failure == 'raise':
                raise OSError('authored persistence failure')
            o.clock.advance(.1)
        return event(operation, value)
    monkeypatch.setattr(o.session, '_event', record)
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='input-schedule', delta_ns=1000)])
    result = execute_script(o.session, script, timeout_ms=50)
    assert result['ok'] is False
    assert o.wire.input['state'] == 'armed' and o.vm.closed


def test_mutating_or_duplicate_mouse_batch_is_refused_before_native_arm(scheduled):
    o = scheduled
    lease = o.session.mouse_button_down('left')['lease']
    o.session.mouse_button_up(lease)
    calls = list(o.wire.calls)
    with pytest.raises(ValueError, match='one edge per mouse button'):
        o.session.input_schedule(1000)
    assert o.wire.calls == calls
    o.session.input_cancel_pending()
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    with pytest.raises(ValueError, match='scheduled'):
        o.session.mouse_move_relative(1, 0)
    assert o.session.input_state()['pending_edges'] == 1


def test_missing_capability_and_transaction_preflight_preserve_pending_batch(scheduled):
    o = scheduled
    o.session.keyboard_key_down('a')
    calls = list(o.wire.calls)
    with o.project.transaction(True):
        for method in (lambda: o.session.input_schedule(1000), o.session.input_schedule_observe,
                       o.session.input_cancel_pending):
            with pytest.raises(ValueError, match='transaction'):
                method()
    assert o.wire.calls == calls
    o.session.capabilities['virtual_input_schedule'] = False
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='keyboard.key-up', lease='arbitrary'), dict(op='input-schedule', delta_ns=1000)])
    with pytest.raises(ValueError, match='native input extension'):
        validate_script(script, session=o.session)
    assert o.wire.calls == calls and o.session.input_state()['pending_edges'] == 1


def test_execution_keeps_original_stop_and_uses_only_native_scheduled_dispatch(scheduled):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    executions = []
    def execute(command, timeout_ms, **kwargs):
        executions.append((command, kwargs))
        o.wire.finish()
        return b'T05thread:1;', False
    o.gdb.execute = execute
    o.session.breakpoints['owned-breakpoint'] = dict(address=0x7c00, access='x', kind=1, length=1)
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    result = o.session.run(timeout_ms=1000)
    assert result['outcome'] == 'breakpoint'
    assert result['session']['stop_reason']['breakpoint_ids'] == ['owned-breakpoint']
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['input_delivery']['state'] == 'dispatched'
    assert executions == [('c', {})]
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


@pytest.mark.parametrize('command', ['query-status', 'x-fdisbull-query-input'])
def test_scheduled_run_bounds_post_stop_reconciliation_and_retains_native_stop(scheduled, command):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(native_command, timeout_ms):
        o.clock.advance(.04)
        o.wire.finish()
        o.wire.extra_latency[command] = .02
        return b'T05thread:1;', False
    o.gdb.execute = execute
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    o.session._rpc_deadline = o.clock.now + .05
    with pytest.raises(TimeoutError) as raised:
        o.session.run(timeout_ms=1000)
    assert o.clock.now == pytest.approx(100.05)
    assert o.vm.closed
    assert raised.value.result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert raised.value.result['timed_out'] is False
    assert o.vm.operation_deadline is None and o.qmp.operation_deadline is None


@pytest.mark.parametrize('overshoot', [0, 128])
def test_dispatch_at_owned_clock_cutoff_cannot_commit_a_lease(scheduled, overshoot):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        end = o.wire.receipt['budget-deadline-ns']
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-stopped-ns': end + overshoot,
                              'budget-fired-ns': end, 'virtual-ns': end + overshoot})
        o.wire.finish(now=end + overshoot)  # Deliberately contradict native budget priority.
        return b'T02thread:1;', False
    o.gdb.execute = execute
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    with pytest.raises(DebuggerError, match='budget') as raised:
        o.session.clock_advance(1000, timeout_ms=1000)
    assert o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert getattr(o.vm, '_active_clock_budget', None) is None


def test_owned_input_execution_rejects_another_clock_budget_token(scheduled):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-stopped-ns': 2000,
                              'budget-token': 'foreign-budget'})
        o.wire.finish(now=2000)
        return b'T02thread:1;', False
    o.gdb.execute = execute
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    with pytest.raises(DebuggerError, match='owned clock budget'):
        o.session.clock_advance(5000, timeout_ms=1000)
    assert o.vm.closed and not o.session.input_state()['valid']


def test_ordinary_scheduled_run_does_not_reuse_a_historical_budget_cutoff(scheduled):
    o = scheduled
    o.wire.receipt.update({'budget-state': 'stopped', 'budget-token': 'completed-budget',
                          'budget-start-ns': 0, 'budget-deadline-ns': 500,
                          'budget-fired-ns': 500, 'budget-stopped-ns': 500})
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.wire.finish()
        return b'T02thread:1;', False
    o.gdb.execute = execute
    lease = o.session.keyboard_key_down('a')['lease']
    o.session.input_schedule(1000)
    result = o.session.run(timeout_ms=1000)
    assert result['input_delivery']['dispatch_ns'] == 2000
    assert o.session.input_state()['leases'][lease]['make'] == 'native_dispatched'
    assert not o.vm.closed


def test_first_owned_stop_rejects_a_cancelled_timer_with_an_older_terminal_time(scheduled):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.wire.finish('cancelled', now=1000)
        o.wire.receipt['virtual-ns'] = 2000
        return b'T05thread:1;', False
    o.gdb.execute = execute
    o.session.keyboard_key_down('a')
    o.session.input_schedule(5000)
    with pytest.raises(DebuggerError, match='first owned stop') as raised:
        o.session.run(timeout_ms=1000)
    assert o.vm.closed
    assert raised.value.result['session']['stop_reason']['native_reply'] == 'T05thread:1;'


def test_register_failure_retains_the_original_stop_before_input_reconciliation(scheduled):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.wire.finish()
        return b'T02thread:1;', True
    def registers():
        raise TimeoutError('Register read failed after native stop')
    o.gdb.execute = execute
    o.session.registers = registers
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    with pytest.raises(TimeoutError) as raised:
        o.session.run(timeout_ms=1000)
    assert o.vm.closed and raised.value.result['timed_out'] is True
    stop = raised.value.result['session']['stop_reason']
    assert stop['native_reply'] == 'T02thread:1;' and not stop['classification_complete']


def test_unscheduled_run_retains_existing_bounded_timeout_recovery(scheduled):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.clock.advance(.3)  # Execution timeout plus the existing stop recovery.
        return b'T02thread:1;', True
    o.gdb.execute = execute
    result = o.session.run(timeout_ms=250)
    assert result['outcome'] == 'timeout' and result['timed_out'] is True
    assert not o.vm.closed and o.vm.operation_deadline is None


@pytest.mark.parametrize('failure', ['cancel-receipt', 'cancel-timeout', 'persistence', 'persistence-overrun'])
def test_outer_clock_cleanup_failure_retains_dispatched_input_and_native_stop(scheduled, failure):
    o = scheduled
    o.session._stopped = lambda: o.gdb
    def execute(command, timeout_ms):
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-stopped-ns': 2000})
        o.wire.finish(now=2000)
        return b'T05thread:1;', False
    o.gdb.execute = execute
    if failure == 'cancel-receipt':
        o.wire.change_final = lambda value: dict(value, **{'budget-token': 'foreign-owner'})
    elif failure == 'cancel-timeout':
        o.wire.extra_latency['x-fdisbull-cancel-clock-budget'] = 2
    else:
        original_event = o.session._event
        def event(operation, value):
            if operation == 'machine-clock-advance' and failure == 'persistence':
                raise OSError('Clock evidence store full after dispatch')
            result = original_event(operation, value)
            if operation == 'machine-clock-advance' and failure == 'persistence-overrun':
                o.clock.advance(1)
            return result
        o.session._event = event
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule(1000)
    expected_error = {'cancel-receipt': DebuggerError, 'cancel-timeout': TimeoutError,
                      'persistence': OSError, 'persistence-overrun': TimeoutError}[failure]
    with pytest.raises(expected_error) as raised:
        o.session.clock_advance(5000, timeout_ms=1000)
    assert o.vm.closed and getattr(o.vm, '_active_clock_budget', None) is None
    result = raised.value.result
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['input_delivery']['state'] == 'dispatched'
    assert result['input_delivery']['token'] == armed['token']


def test_failed_script_cannot_leave_its_newly_armed_preexisting_input_live(scheduled):
    o = scheduled
    o.session.keyboard_key_down('a')
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='input-schedule', delta_ns=1000),
        dict(op='assert', value=1, equals=2)])
    result = execute_script(o.session, script, timeout_ms=1000)
    assert result['ok'] is False and result['completed_steps'] == 1
    assert result['input_cleanup']['closed'] is True
    assert o.vm.closed and not o.session.input_state()['valid']
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


@pytest.mark.parametrize('reason', ['é' * 129, '\ud800'])
def test_terminal_reason_is_bounded_valid_utf8(scheduled, reason):
    o = scheduled
    o.session.keyboard_key_down('a')
    o.session.input_schedule(1000)
    o.wire.finish('cancelled', now=1000)
    o.wire.input['reason'] = reason
    with pytest.raises(DebuggerError, match='reason'):
        o.session.input_schedule_observe()
    assert o.vm.closed
