"""Retrace-bound input ownership at the production QMP envelope.

The deterministic peer supplies frozen callback observations. Native timer,
device dispatch and guest consumption have separate authored witnesses.
"""
from copy import deepcopy
import json

import pytest

from fdisbull import qemu_input_schedule
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_retrace import (
    RETRACE_COMMANDS, machine_retrace_configuration, validate_retrace_snapshot,
)
from test_qemu_input_schedule import InputWire, scheduled
from test_qemu_io_deadlines import observation
from test_qemu_retrace import RetraceWire, change


ARM = 'x-fdisbull-arm-input-retrace'


class RetraceInputWire(InputWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.video = RetraceWire(clock)
        self.video.receipt = self.receipt
        self.video.initialized()
        self.reject_arm = False

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in (ARM, 'x-fdisbull-query-retrace'):
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-query-retrace':
            value = self.video.value()
        else:
            armed = self.video.value()
            timing = armed['timing']
            tick, horizontal = timing['ticks-per-char'], timing['htotal']
            period = tick * timing['total-chars']
            entry = tick * horizontal * timing['vstart']
            exit_ = tick * horizontal * (timing['vend'] + 1)
            phase = entry if args['edge'] == 'enter' else exit_ % period
            now = self.receipt['virtual-ns']
            target = now + ((phase - now) % period or period)
            width = exit_ - entry if args['edge'] == 'enter' else period - (exit_ - entry)
            self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed',
                'virtual-ns': now, 'token': args['token'], 'start-ns': now,
                'deadline-ns': target, 'event-count': len(args['events']),
                'retrace': {'edge': args['edge'], 'target-ns': target,
                            'window-end-ns': target + width, 'armed': armed}}
            value = self.mutate(deepcopy(self.input))
        answer = ({'error': {'class': 'GenericError', 'desc': 'Retrace owner changed at arm'}}
                  if command == ARM and self.reject_arm else {'return': value})
        self.buffer.extend(json.dumps(dict(id=request['id'], **answer)).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)

    def callback(self, *, reason='dispatch-complete', checked_ns=None, stopped_ns=None):
        checked_ns = self.input['deadline-ns'] if checked_ns is None else checked_ns
        self.receipt['virtual-ns'] = checked_ns
        self.input['retrace']['checked'] = self.video.value()
        self.input.update(state='dispatched' if reason == 'dispatch-complete' else 'cancelled',
                          reason=reason, **{'terminal-ns': checked_ns})
        if reason == 'dispatch-complete':
            self.input['dispatch-ns'] = checked_ns
        self.receipt['virtual-ns'] = checked_ns if stopped_ns is None else stopped_ns


@pytest.fixture
def retrace_input(scheduled):
    o = scheduled
    o.wire = RetraceInputWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= RETRACE_COMMANDS | {ARM}
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    o.vm.native_clock_admission = deepcopy(o.wire.receipt)
    o.vm.native_retrace_admission = deepcopy(o.wire.video.value())
    o.vm._retrace_last = deepcopy(o.wire.video.value())
    o.session.capabilities.update(retrace_observation=True, retrace_input_schedule=True)
    return o


def test_public_retrace_input_arm_is_passive(retrace_input):
    o = retrace_input
    lease = o.session.keyboard_key_down('a')['lease']
    result = o.session.input_schedule_retrace()
    assert result['state'] == 'armed'
    assert result['retrace']['format'] == 'fdisbull-retrace-input-1'
    assert result['retrace']['target_ns'] == 2_536_000
    assert result['retrace']['window_end_ns'] == 2_884_700
    assert result['retrace']['dispatch_phase_verified'] is False
    assert result['retrace']['native_check'] is None
    assert o.session.input_state()['leases'][lease]['make'] == 'python_pending'
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-arm-clock-budget')
                   for name, _ in o.wire.calls)


def test_final_wrapper_expiry_closes_an_already_armed_owner(retrace_input, monkeypatch):
    o = retrace_input
    o.session.keyboard_key_down('a')
    original = qemu_input_schedule.deepcopy

    def copy_after_last_module_check(value):
        copied = original(value)
        if (isinstance(value, dict) and value.get('format') == qemu_input_schedule.FORMAT
                and value.get('state') == 'armed' and 'retrace' in value):
            # The returned receipt copy follows the controller's final check;
            # the public wrapper still owns the same absolute deadline.
            o.clock.advance(.05)
        return copied

    monkeypatch.setattr(qemu_input_schedule, 'deepcopy', copy_after_last_module_check)
    with pytest.raises(TimeoutError) as raised:
        o.session.input_schedule_retrace(timeout_ms=50)
    assert raised.value.result['state'] == 'armed'
    assert raised.value.result['native']['token'] == o.wire.input['token']
    assert o.vm.closed and not o.session.input_state()['valid']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


def run_with_callback(o, callback, *, reply=b'T05thread:1;'):
    o.session._stopped = lambda: o.gdb

    def execute(command, timeout_ms):
        assert command == 'c'
        callback()
        return reply, False

    o.gdb.execute = execute


@pytest.mark.parametrize(('edge', 'now', 'target', 'window_end'), [
    ('enter', 1000, 2_536_000, 2_884_700),
    ('enter', 2_536_000, 5_706_000, 6_054_700),
    ('exit', 1000, 2_884_700, 5_706_000),
    ('exit', 2_884_700, 6_054_700, 8_876_000),
])
def test_arm_binds_exact_observation_and_strictly_next_occurrence(retrace_input, edge, now, target, window_end):
    o = retrace_input
    o.wire.receipt['virtual-ns'] = now
    o.session.keyboard_key_down('a')
    result = o.session.input_schedule_retrace(edge=edge)
    descriptor = result['retrace']
    assert (result['deadline_ns'], descriptor['target_ns'], descriptor['window_end_ns']) == (target, target, window_end)
    before = descriptor['before']
    assert descriptor['native_arm'] == before['native']
    calls = [arguments for name, arguments in o.wire.calls if name == ARM]
    assert calls == [dict(token=result['token'], events=[dict(type='key', data=dict(down=True, key=dict(type='qcode', data='a')))],
                          edge=edge, **{'expected-epoch': before['native_epoch'],
                          'expected-device': before['device'], 'expected-model': before['model'],
                          'expected-generation': before['timing_generation'], 'expected-virtual-ns': now})]


@pytest.mark.parametrize(('edge', 'vstart', 'vend', 'window_end'), [
    ('enter', 0, 10, 3_518_700),
    ('exit', 89, 99, 5_991_300),
])
def test_real_transition_at_period_wrap_qualifies_one_original_window(retrace_input, edge, vstart, vend, window_end):
    o = retrace_input
    video = o.wire.video.retrace
    video['raw']['cr10'] = vstart
    video['timing'].update(vstart=vstart, vend=vend)
    video['timing-generation'] += 1
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace(edge=edge)
    assert armed['deadline_ns'] == 3_170_000
    assert armed['retrace']['window_end_ns'] == window_end
    o.wire.callback()
    delivered = o.session.input_schedule_observe()
    assert delivered['retrace']['dispatch_phase_verified'] is True
    assert delivered['retrace']['native_check']['phase']['vertical-retrace'] is (edge == 'enter')


def test_armed_batch_cannot_be_silently_replaced(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()
    pending = o.session.input_state()['pending']
    with pytest.raises(ValueError, match='Cancel the current native input schedule'):
        o.session.input_schedule_retrace(edge='exit')
    assert o.session.input_state()['pending'] == pending
    assert o.wire.input['token'] == armed['token']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert not o.vm.closed


@pytest.mark.parametrize('options', [
    {'edge': True}, {'edge': 'ENTER'}, {'edge': ''}, {'edge': None},
    {'timeout_ms': True}, {'timeout_ms': 0}, {'timeout_ms': -1},
    {'timeout_ms': 600001}, {'timeout_ms': 1.5},
])
def test_invalid_options_do_not_touch_qmp_or_pending_ownership(retrace_input, options):
    o = retrace_input
    o.session.keyboard_key_down('a')
    pending = o.session.input_state()
    calls = list(o.wire.calls)
    with pytest.raises(ValueError):
        o.session.input_schedule_retrace(**options)
    assert o.wire.calls == calls and o.session.input_state() == pending
    assert not o.vm.closed


@pytest.mark.parametrize('refusal', ['clock', 'retrace', 'command', 'transaction', 'duplicate-button'])
def test_preflight_refusal_keeps_existing_pending_batch(retrace_input, refusal):
    o = retrace_input
    if refusal == 'duplicate-button':
        lease = o.session.mouse_button_down('left')['lease']
        o.session.mouse_button_up(lease)
    else:
        o.session.keyboard_key_down('a')
    calls = list(o.wire.calls)
    pending = o.session.input_state()
    if refusal == 'clock':
        o.vm.machine_configuration['clock_profile']['profile'] = 'standard'
    elif refusal == 'retrace':
        o.vm.machine_configuration['retrace_profile']['profile'] = 'standard'
    elif refusal == 'command':
        o.vm.qmp_commands -= {ARM}
    if refusal == 'transaction':
        with o.project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                o.session.input_schedule_retrace()
    else:
        with pytest.raises(ValueError):
            o.session.input_schedule_retrace()
    assert o.wire.calls == calls and o.session.input_state() == pending
    assert not o.vm.closed


def make_unsupported(o, reason):
    video = o.wire.video.retrace
    video['timing-generation'] += 1
    video.update({'phase-supported': False, 'unsupported-reason': reason})
    if reason == 'uninitialized':
        video['timing'] = {key: 0 for key in video['timing']}
    elif reason == 'vbe-enabled':
        video['raw']['vbe-enable'] = 1
    else:
        video['raw']['cr10'] = 120
        video['timing'].update(vstart=120, vend=130)


@pytest.mark.parametrize('refusal', ['uninitialized', 'vbe-enabled', 'invalid-timing', 'no-transition', 'overflow'])
def test_known_phase_refusal_retains_observation_without_arm(retrace_input, refusal):
    o = retrace_input
    o.session.keyboard_key_down('a')
    pending = o.session.input_state()
    if refusal in ('uninitialized', 'vbe-enabled', 'invalid-timing'):
        make_unsupported(o, refusal)
    elif refusal == 'no-transition':
        video = o.wire.video.retrace
        video['timing-generation'] += 1
        video['raw'].update(cr06=9, cr10=0)
        video['timing'].update(**{'total-chars': 1100, 'vstart': 0, 'vend': 10})
    else:
        o.wire.receipt['virtual-ns'] = (1 << 63) - 1
    with pytest.raises(ValueError) as raised:
        o.session.input_schedule_retrace()
    assert raised.value.result['armed'] is False
    assert raised.value.result['before']['native'] == o.wire.video.value()
    assert not any(name == ARM for name, _ in o.wire.calls)
    assert o.session.input_state() == pending and not o.vm.closed


@pytest.mark.parametrize('edge', ['enter', 'exit'])
def test_dispatch_uses_frozen_callback_and_changes_held_lease_once(retrace_input, edge):
    o = retrace_input
    lease = o.session.keyboard_key_down('a')['lease']
    armed = o.session.input_schedule_retrace(edge=edge)
    callback_ns = armed['deadline_ns'] + 1
    stopped_ns = callback_ns + 1000
    run_with_callback(o, lambda: o.wire.callback(checked_ns=callback_ns, stopped_ns=stopped_ns))
    result = o.session.run(timeout_ms=1000)
    delivery = result['input_delivery']
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert delivery['dispatch_ns'] == delivery['terminal_ns'] == callback_ns
    assert delivery['observed_ns'] == stopped_ns
    assert delivery['retrace']['dispatch_phase_verified'] is True
    assert delivery['retrace']['native_check']['phase']['vertical-retrace'] is (edge == 'enter')
    assert delivery['guest_consumed'] is delivery['device_queue_accepted'] is None
    state = o.session.input_state()
    assert state['pending_edges'] == 0 and state['leases'][lease]['make'] == 'native_dispatched'
    again = o.session.input_schedule_observe()
    assert again['native'] == delivery['native']
    assert o.session.input_state()['leases'] == state['leases']
    assert o.session.input_state()['pending'] == state['pending']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


def test_later_live_observation_does_not_revalidate_or_relabel_historical_callback(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()
    callback_ns = armed['deadline_ns']
    o.wire.callback(checked_ns=callback_ns, stopped_ns=callback_ns + 1000)
    frozen = deepcopy(o.wire.input['retrace']['checked'])
    o.wire.video.retrace['timing-generation'] += 2  # ABA after the already completed callback.
    current = o.session.retrace_observe()
    frontier = deepcopy(o.vm._retrace_last)
    assert current['native']['virtual-ns'] > frozen['virtual-ns']
    assert current['timing_generation'] > frozen['timing-generation']
    result = o.session.input_schedule_observe()
    assert result['retrace']['native_check'] == frozen
    assert result['retrace']['native_arm'] == armed['retrace']['native_arm']
    assert o.vm._retrace_last == frontier and result['retrace']['dispatch_phase_verified'] is True
    copied = validate_retrace_snapshot(frozen, epoch=1, virtual_ns=callback_ns,
                                      previous=armed['retrace']['native_arm'])
    copied['raw']['msr'] ^= 1
    assert frozen == result['retrace']['native_check']  # No alias back into retained evidence.


@pytest.mark.parametrize('reason', ['retrace-timing-changed', 'newly-unsupported', 'retrace-missed-window'])
def test_callback_cancellation_before_final_stop_requires_explicit_resolution(retrace_input, reason):
    o = retrace_input
    lease = o.session.keyboard_key_down('a')['lease']
    armed = o.session.input_schedule_retrace()
    if reason == 'newly-unsupported':
        make_unsupported(o, 'vbe-enabled')
    elif reason == 'retrace-timing-changed':
        o.wire.video.retrace['timing-generation'] += 2  # Same raw tuple after A -> B -> A.
    callback_ns = (armed['retrace']['window_end_ns'] if reason == 'retrace-missed-window'
                   else armed['deadline_ns'])
    native_reason = 'retrace-timing-changed' if reason == 'newly-unsupported' else reason
    run_with_callback(o, lambda: o.wire.callback(reason=native_reason, checked_ns=callback_ns,
                                                stopped_ns=callback_ns + 1000))
    result = o.session.run(timeout_ms=1000)
    delivery = result['input_delivery']
    assert delivery['state'] == 'cancelled' and delivery['requires_resolution'] is True
    assert delivery['terminal_ns'] == callback_ns < delivery['observed_ns']
    assert delivery['retrace']['dispatch_phase_verified'] is False
    assert o.session.input_state()['leases'][lease]['make'] == 'python_pending'
    with pytest.raises(ValueError, match='reschedule or cancel'):
        o.session._execution_preflight('c', 1000)
    with pytest.raises(ValueError, match='scheduled'):
        o.session.keyboard_key_up(lease)
    cancelled = o.session.input_cancel_pending()
    assert cancelled['cancelled_leases'] == [lease]
    assert o.session.input_state()['pending_edges'] == 0 and not o.vm.closed
    assert not any(name in ('x-fdisbull-cancel-input', 'input-send-event') for name, _ in o.wire.calls)
    o.session._execution_preflight('c', 1000)


def test_cancelled_retrace_batch_can_be_explicitly_rescheduled_once(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    first = o.session.input_schedule_retrace()
    o.wire.video.retrace['timing-generation'] += 1
    o.wire.callback(reason='retrace-timing-changed')
    o.session.input_schedule_observe()
    second = o.session.input_schedule_retrace(edge='exit')
    assert second['token'] != first['token']
    assert second['retrace']['native_arm']['timing-generation'] == 3
    assert second['start_ns'] == first['deadline_ns']
    assert second['deadline_ns'] > second['start_ns'] and second['edge_count'] == 1
    assert o.session.input_state()['pending_edges'] == 1
    o.session._execution_preflight('c', 1000)


def test_cancelled_queued_release_preserves_the_previously_dispatched_hold(retrace_input):
    o = retrace_input
    lease = o.session.keyboard_key_down('a')['lease']
    o.session.input_schedule_retrace()
    o.wire.callback()
    o.session.input_schedule_observe()
    o.session.keyboard_key_up(lease)
    o.session.input_schedule_retrace(edge='exit')
    o.wire.video.retrace['timing-generation'] += 1
    o.wire.callback(reason='retrace-timing-changed')
    o.session.input_schedule_observe()
    o.session.input_cancel_pending()
    state = o.session.input_state()
    assert state['pending_edges'] == 0 and state['leases'][lease]['make'] == 'native_dispatched'
    assert state['leases'][lease]['release'] is None
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


@pytest.mark.parametrize(('path', 'replacement'), [
    (('retrace', 'edge'), 'exit'),
    (('retrace', 'target-ns'), 2_536_001),
    (('retrace', 'window-end-ns'), 2_884_701),
    (('retrace', 'window-end-ns'), True),
    (('retrace', 'armed', 'timing-generation'), 3),
    (('retrace', 'armed', 'epoch'), 2),
    (('retrace', 'armed', 'device'), '/machine/foreign-vga'),
    (('retrace', 'armed', 'raw', 'cr10'), 81),
    (('retrace', 'armed', 'phase', 'status1-timing-bits'), 8),
    (('retrace', 'invented'), 'unowned'),
    (('invented',), 'unowned'),
])
def test_malformed_arm_evidence_closes_without_committing_a_lease(retrace_input, path, replacement, monkeypatch):
    o = retrace_input
    o.session.keyboard_key_down('a')
    commits = []
    monkeypatch.setattr(o.session, '_input_mark_dispatched', lambda *args: commits.append(args))
    o.wire.mutate = lambda value: change(value, path, replacement) if 'retrace' in value else value
    with pytest.raises(DebuggerError) as raised:
        o.session.input_schedule_retrace()
    assert not commits and o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['native']['retrace']
    assert raised.value.result['before']['native']['timing-generation'] == 2
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


@pytest.mark.parametrize('corruption', [
    'no-check', 'higher-generation', 'foreign-device', 'foreign-epoch', 'wrong-phase',
    'early', 'outside-window', 'future-terminal', 'changed-without-new-generation',
    'missed-with-new-generation', 'missed-before-window-end', 'ordinary-cancel-with-check',
    'dispatch-with-cancel-reason',
])
def test_invalid_callback_cannot_commit_a_lease(retrace_input, corruption, monkeypatch):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()
    target, window_end = armed['deadline_ns'], armed['retrace']['window_end_ns']
    commits = []
    monkeypatch.setattr(o.session, '_input_mark_dispatched', lambda *args: commits.append(args))
    if corruption in ('higher-generation', 'missed-with-new-generation'):
        o.wire.video.retrace['timing-generation'] += 1
    reason = ('retrace-timing-changed' if corruption == 'changed-without-new-generation' else
              'retrace-missed-window' if corruption.startswith('missed-') else
              'machine-stop' if corruption == 'ordinary-cancel-with-check' else 'dispatch-complete')
    when = (target - 1 if corruption == 'early' else window_end
            if corruption in ('outside-window', 'missed-with-new-generation') else target)
    o.wire.callback(reason=reason, checked_ns=when,
                    stopped_ns=when - 1 if corruption == 'future-terminal' else when + 1000)
    descriptor = o.wire.input['retrace']
    if corruption == 'no-check':
        del descriptor['checked']
    elif corruption == 'foreign-device':
        descriptor['checked']['device'] = '/machine/foreign-vga'
    elif corruption == 'foreign-epoch':
        descriptor['checked']['epoch'] = 2
    elif corruption == 'wrong-phase':
        descriptor['checked']['phase']['status1-timing-bits'] ^= 1
    elif corruption == 'dispatch-with-cancel-reason':
        o.wire.input['reason'] = 'retrace-timing-changed'
    with pytest.raises(DebuggerError) as raised:
        o.session.input_schedule_observe()
    assert not commits and o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['validation_failed'] is True
    assert raised.value.result['native']['token'] == armed['token']
    assert raised.value.result['retrace_before'] == armed['retrace']['before']


@pytest.mark.parametrize('failure', ['malformed', 'failed', 'survived-timer'])
def test_failed_callback_keeps_original_stop_and_raw_native_evidence(retrace_input, failure):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()

    def callback():
        if failure == 'survived-timer':
            o.wire.receipt['virtual-ns'] += 1
            return
        o.wire.callback()
        if failure == 'malformed':
            o.wire.input['retrace']['checked']['device'] = '/machine/foreign-vga'
        else:
            o.wire.input.update(state='failed', reason='Selected PS2 handler changed')
            del o.wire.input['dispatch-ns']

    run_with_callback(o, callback)
    with pytest.raises(DebuggerError) as raised:
        o.session.run(timeout_ms=1000)
    evidence = raised.value.result
    assert evidence['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert evidence['timed_out'] is False
    assert evidence['input_schedule_native']['token'] == armed['token']
    assert evidence['input_schedule_native']['retrace'] == o.wire.input['retrace']
    assert evidence['input_schedule_retrace_before'] == armed['retrace']['before']
    assert 'input_delivery' not in evidence
    assert o.vm.closed and not o.session.input_state()['valid']


@pytest.mark.parametrize('reason', ['machine-stop', 'stop-pending', 'budget-deadline', 'caller'])
def test_noncallback_cancellation_keeps_exact_first_stop_requirement(retrace_input, reason):
    o = retrace_input
    o.session.keyboard_key_down('a')
    o.session.input_schedule_retrace()

    def callback():
        o.wire.finish('cancelled', now=1100)
        o.wire.input['reason'] = reason
        o.wire.receipt['virtual-ns'] = 1200

    run_with_callback(o, callback)
    with pytest.raises(DebuggerError, match='first owned stop') as raised:
        o.session.run(timeout_ms=1000)
    assert raised.value.result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert 'checked' not in raised.value.result['input_schedule_native']['retrace']
    assert o.vm.closed


@pytest.mark.parametrize('terminal', ['dispatch', 'semantic-cancel', 'budget-cancel'])
def test_equal_owned_budget_deadline_wins_over_retrace_callback(retrace_input, terminal):
    o = retrace_input
    lease = o.session.keyboard_key_down('a')['lease']
    armed = o.session.input_schedule_retrace()

    def callback():
        end = o.wire.receipt['budget-deadline-ns']
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-stopped-ns': end,
                              'budget-fired-ns': end})
        if terminal == 'budget-cancel':
            o.wire.finish('cancelled', now=end)
            o.wire.input['reason'] = 'budget-deadline'
        else:
            if terminal == 'semantic-cancel':
                o.wire.video.retrace['timing-generation'] += 1
            o.wire.callback(reason='retrace-timing-changed' if terminal == 'semantic-cancel'
                            else 'dispatch-complete', checked_ns=end)

    run_with_callback(o, callback, reply=b'T02thread:1;')
    delta = armed['deadline_ns'] - armed['start_ns']
    if terminal == 'budget-cancel':
        result = o.session.clock_advance(delta, timeout_ms=1000)
        delivery = result['input_delivery']
        assert delivery['reason'] == 'budget-deadline'
        assert delivery['retrace']['native_check'] is None
        assert delivery['requires_resolution'] is True
        assert o.session.input_state()['leases'][lease]['make'] == 'python_pending'
        assert not o.vm.closed
    else:
        with pytest.raises(DebuggerError, match='budget cutoff') as raised:
            o.session.clock_advance(delta, timeout_ms=1000)
        assert raised.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert o.vm.closed and not o.session.input_state()['valid']


def test_terminal_callback_snapshot_cannot_be_replaced_by_a_later_valid_snapshot(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()
    o.wire.callback()
    o.session.input_schedule_observe()
    o.wire.callback(checked_ns=armed['deadline_ns'] + 1)
    with pytest.raises(DebuggerError, match='Terminal'):
        o.session.input_schedule_observe()
    assert o.vm.closed


@pytest.mark.parametrize('owned', [False, True])
def test_legacy_or_idle_schedule_cannot_invent_retrace_descriptor(retrace_input, owned):
    o = retrace_input
    if owned:
        o.session.keyboard_key_down('a')
        o.session.input_schedule(1000)
    o.wire.input['retrace'] = {'edge': 'enter'}
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed


def test_new_legacy_arm_clears_terminal_retrace_descriptor(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    o.session.input_schedule_retrace()
    o.session.input_cancel_pending()
    o.session.keyboard_key_down('b')
    legacy = o.session.input_schedule(1000)
    assert 'retrace' not in legacy and 'retrace' not in legacy['native']
    o.wire.finish()
    assert o.session.input_schedule_observe()['state'] == 'dispatched'
    assert not o.vm.closed


@pytest.mark.parametrize('failure', ['lost-reply', 'rejected', 'persistence', 'persistence-overrun'])
def test_uncertain_arm_closes_without_replay_and_retains_available_evidence(retrace_input, monkeypatch, failure):
    o = retrace_input
    o.session.keyboard_key_down('a')
    if failure == 'lost-reply':
        o.wire.extra_latency[ARM] = 1
    elif failure == 'rejected':
        o.wire.reject_arm = True
    else:
        original = o.session._event

        def record(operation, value):
            if operation == 'input.schedule-arm':
                if failure == 'persistence':
                    raise OSError('Authored input evidence failure')
                o.clock.advance(.1)
            return original(operation, value)

        monkeypatch.setattr(o.session, '_event', record)
    expected = {'lost-reply': TimeoutError, 'rejected': DebuggerError,
                'persistence': OSError, 'persistence-overrun': TimeoutError}[failure]
    with pytest.raises(expected) as raised:
        o.session.input_schedule_retrace(timeout_ms=50)
    assert raised.value.result
    assert o.vm.closed and not o.session.input_state()['valid']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert not any(name in ('input-send-event', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)
    assert o.vm.operation_deadline is None and o.qmp.operation_deadline is None


def test_one_deadline_spans_initial_observations_and_native_arm(retrace_input):
    o = retrace_input
    o.session.keyboard_key_down('a')
    o.wire.calls.clear()
    o.wire.budgets.clear()
    o.wire.latency = .003
    o.wire.extra_latency[ARM] = .02
    with pytest.raises(TimeoutError):
        o.session.input_schedule_retrace(timeout_ms=50)
    assert o.clock.now == pytest.approx(100.05)
    assert [name for name, _ in o.wire.calls][-1] == ARM
    assert o.wire.budgets[-1] < .02
    assert o.wire.budgets == sorted(o.wire.budgets, reverse=True)
    assert o.vm.closed


@pytest.mark.parametrize('operation', ['run', 'observe'])
def test_callback_journal_failure_preserves_available_native_evidence(retrace_input, monkeypatch, operation):
    o = retrace_input
    o.session.keyboard_key_down('a')
    armed = o.session.input_schedule_retrace()
    original = o.session._event

    def record(name, value):
        if name == ('input.schedule-result' if operation == 'run' else 'input.schedule-observe'):
            raise OSError('Authored callback receipt persistence failure')
        return original(name, value)

    monkeypatch.setattr(o.session, '_event', record)
    if operation == 'run':
        run_with_callback(o, o.wire.callback)
    else:
        o.wire.callback()
    with pytest.raises(OSError) as raised:
        if operation == 'run':
            o.session.run(timeout_ms=1000)
        else:
            o.session.input_schedule_observe()
    evidence = raised.value.result
    if operation == 'run':
        assert evidence['session']['stop_reason']['native_reply'] == 'T05thread:1;'
        native = evidence['input_schedule_native']
        assert evidence['input_schedule_retrace_before'] == armed['retrace']['before']
    else:
        native = evidence['native']
        assert evidence['retrace']['before'] == armed['retrace']['before']
    assert native['state'] == 'dispatched' and native['token'] == armed['token']
    assert native['retrace']['checked'] == o.wire.input['retrace']['checked']
    assert o.vm.closed and not o.session.input_state()['valid']
