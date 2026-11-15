"""Finite native text at the production host/QMP boundary.

The peer derives US physical-key plans from a separate literal layout table.
These tests qualify admission, protocol and ownership; native IRQ witnesses
separately establish actual callbacks and consumption in their authored guest.
"""
from copy import deepcopy
import json

import pytest

from fdisbull import qemu_keyboard_type
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_input import MAX_LEASES, MAX_PENDING_EDGES
from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration
from test_qemu_input_schedule import scheduled
from test_qemu_io_deadlines import observation
from test_qemu_keyboard_press import PressRetraceWire, change, run_with_stop


ARM = 'x-fdisbull-arm-keyboard-type'
MS = 1_000_000
# Physical US key pairs, deliberately independent of the production mapping.
KEY_PAIRS = (
    ('1', '!', '1'), ('2', '@', '2'), ('3', '#', '3'), ('4', '$', '4'),
    ('5', '%', '5'), ('6', '^', '6'), ('7', '&', '7'), ('8', '*', '8'),
    ('9', '(', '9'), ('0', ')', '0'), ('-', '_', 'minus'), ('=', '+', 'equal'),
    ('[', '{', 'bracket_left'), (']', '}', 'bracket_right'),
    ('\\', '|', 'backslash'), (';', ':', 'semicolon'), ("'", '"', 'apostrophe'),
    (',', '<', 'comma'), ('.', '>', 'dot'), ('/', '?', 'slash'), ('`', '~', 'grave_accent'),
)


def physical_character(char):
    if 'a' <= char <= 'z':
        return char, False
    if 'A' <= char <= 'Z':
        return chr(ord(char) + 32), True
    if char in ' \r\n\t':
        return {' ': 'spc', '\r': 'ret', '\n': 'ret', '\t': 'tab'}[char], False
    for unshifted, shifted, qcode in KEY_PAIRS:
        if char in (unshifted, shifted):
            return qcode, char == shifted
    raise AssertionError('Unsupported character supplied to authored peer')


def expected_steps(text, hold_ms, gap_ms):
    result = []
    for index, char in enumerate(text):
        key, shifted = physical_character(char)
        first = (2 + (gap_ms if index else 0)) * MS
        if shifted:
            result += [dict(key='shift', down=True, **{'delay-ns': first})]
            first = 2 * MS
        result += [dict(key=key, down=True, **{'delay-ns': first}),
                   dict(key=key, down=False, **{'delay-ns': hold_ms * MS})]
        if shifted:
            result += [dict(key='shift', down=False, **{'delay-ns': 2 * MS})]
    return result


class TextWire(PressRetraceWire):
    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command != ARM:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        steps = expected_steps(args['text'], args['hold-ms'], args['gap-ms'])
        now = self.receipt['virtual-ns']
        steps[0]['deadline-ns'] = now + 2 * MS
        self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed', 'virtual-ns': now,
            'token': args['token'], 'start-ns': now, 'deadline-ns': now + 2 * MS,
            'event-count': len(steps), 'typing': dict(text=args['text'], steps=steps,
                **{'hold-ms': args['hold-ms'], 'gap-ms': args['gap-ms'], 'dispatched-count': 0})}
        answer = ({'error': {'class': 'GenericError', 'desc': 'Keyboard handler lost ownership'}}
                  if self.reject_arm else {'return': self.mutate(deepcopy(self.input))})
        self.buffer.extend(json.dumps(dict(id=request['id'], **answer)).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)

    def stop_after(self, count, *, lateness=0, stopped_ns=None, reason='machine-stop'):
        descriptor = self.input.get('typing', self.input.get('press'))
        steps = descriptor['steps']
        for index in range(descriptor['dispatched-count'], count):
            extra = lateness[index] if isinstance(lateness, (tuple, list)) else lateness
            actual = steps[index]['deadline-ns'] + extra
            steps[index]['dispatch-ns'] = actual
            self.receipt['virtual-ns'] = actual
            descriptor['dispatched-count'] = index + 1
            if index + 1 < len(steps):
                steps[index + 1]['deadline-ns'] = actual + steps[index + 1]['delay-ns']
        terminal = self.receipt['virtual-ns'] if stopped_ns is None else stopped_ns
        if count == len(steps):
            self.input.update(state='dispatched', reason='dispatch-complete',
                **{'dispatch-ns': steps[-1]['dispatch-ns'], 'terminal-ns': steps[-1]['dispatch-ns']})
        else:
            self.input.update(state='cancelled', reason=reason, **{'terminal-ns': terminal})
        self.receipt['virtual-ns'] = terminal


@pytest.fixture
def typing(scheduled):
    o = scheduled
    o.wire = TextWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= {ARM, 'x-fdisbull-arm-keyboard-press'}
    o.session.capabilities.update(virtual_keyboard_type=True, virtual_keyboard_press=True)
    return o


def enable_retrace(o):
    o.vm.qmp_commands |= RETRACE_COMMANDS | {'x-fdisbull-arm-input-retrace'}
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    o.vm.native_clock_admission = deepcopy(o.wire.receipt)
    o.vm.native_retrace_admission = deepcopy(o.wire.video.value())
    o.vm._retrace_last = deepcopy(o.wire.video.value())


def test_complete_us_ascii_plan_matches_literal_physical_layout():
    alphabet = ''.join(chr(n) for n in range(32, 127)) + '\r\n\t'
    assert len(alphabet) == 98
    for char in alphabet:
        qemu_keyboard_type.validate_keyboard_type_parameters(char, hold_ms=7, gap_ms=11)
        plan = qemu_keyboard_type._plan(char, 7, 11)
        assert plan['steps'] == expected_steps(char, 7, 11), repr(char)
        assert plan['character_indices'] == [0] * len(plan['steps'])


def test_existing_type_facade_arms_complete_mixed_text_passively(typing):
    o = typing
    result = o.session.keyboard.type('aA!\r\n\t ', hold_ms=7, gap_ms=13)
    assert result['state'] == 'armed' and result['lateness_ns'] is None
    assert result['typing']['format'] == 'fdisbull-keyboard-type-1'
    steps = result['typing']['steps']
    assert [(step['qcode'], step['down']) for step in steps] == [
        ('a', True), ('a', False),
        ('shift', True), ('a', True), ('a', False), ('shift', False),
        ('shift', True), ('1', True), ('1', False), ('shift', False),
        ('ret', True), ('ret', False), ('ret', True), ('ret', False),
        ('tab', True), ('tab', False), ('spc', True), ('spc', False)]
    assert [step['character_index'] for step in steps] == [0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    assert [steps[index]['delay_ns'] for index in (0, 2, 6, 10, 12, 14, 16)] == [2 * MS] + [15 * MS] * 6
    assert steps[0]['deadline_ns'] == result['start_ns'] + 2 * MS
    assert all(step['deadline_ns'] is None for step in steps[1:])
    assert all(step['dispatch_ns'] is step['lateness_ns'] is None for step in steps)
    state = o.session.input_state()
    assert state['pending_edges'] == 18 and state['leases'] == {}
    assert len(o.vm._physical_input['schedule']['lease_reservations']) == 9
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-arm-clock-budget') for name, _ in o.wire.calls)
    assert o.session.input_schedule_observe()['typing'] == result['typing']


def test_actual_callback_relative_gap_and_hold_have_no_trailing_timer(typing):
    o = typing
    armed = o.session.keyboard_type('Aa', hold_ms=7, gap_ms=1000)
    lateness = [101, 202, 303, 404, 505, 606]
    run_with_stop(o, lambda: o.wire.stop_after(6, lateness=lateness))
    result = o.session.run(timeout_ms=1000)
    delivered = result['input_delivery']
    steps = delivered['typing']['steps']
    assert delivered['state'] == 'dispatched' and delivered['lateness_ns'] is None
    assert [step['delay_ns'] for step in steps] == [2 * MS, 2 * MS, 7 * MS, 2 * MS, 1002 * MS, 7 * MS]
    assert [step['lateness_ns'] for step in steps] == lateness
    for previous, step in zip(steps, steps[1:]):
        assert step['deadline_ns'] == previous['dispatch_ns'] + step['delay_ns']
    assert delivered['dispatch_ns'] == delivered['terminal_ns'] == steps[-1]['dispatch_ns']
    assert delivered['terminal_ns'] == armed['start_ns'] + 1022 * MS + sum(lateness)
    assert delivered['typing']['dispatched_count'] == 6 and delivered['typing']['undispatched_count'] == 0
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert not o.vm._physical_input['schedule']['lease_reservations']
    assert o.session.input_schedule_observe()['native'] == delivered['native']
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'


def test_64_shifted_characters_reserve128_lifetimes_without_active_lease_growth(typing):
    o = typing
    armed = o.session.keyboard_type('A' * 64, hold_ms=1, gap_ms=1)
    steps = armed['typing']['steps']
    assert MAX_PENDING_EDGES == 256 and MAX_LEASES == 64
    assert len(steps) == 256 and len({step['lease'] for step in steps}) == 128
    assert len(o.vm._physical_input['schedule']['lease_reservations']) == 128
    assert o.session.input_state()['leases'] == {}
    for index in range(64):
        shift_down, main_down, main_up, shift_up = steps[index * 4:index * 4 + 4]
        assert shift_down['lease'] == shift_up['lease']
        assert main_down['lease'] == main_up['lease']
        assert shift_down['lease'] != main_down['lease']
        assert {step['character_index'] for step in (shift_down, main_down, main_up, shift_up)} == {index}
    run_with_stop(o, lambda: o.wire.stop_after(256))
    delivered = o.session.run(timeout_ms=1000)['input_delivery']
    assert delivered['typing']['dispatched_count'] == 256
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert not o.vm._physical_input['schedule']['lease_reservations']


def test_legal_long_text_is_admitted_without_hidden_execution_splitting(typing):
    o = typing
    result = o.session.keyboard_type('A' * 64, hold_ms=1000, gap_ms=1000)
    assert sum(step['delay_ns'] for step in result['typing']['steps']) == 127_384 * MS
    assert result['state'] == 'armed' and len(o.wire.calls) < 10
    assert not any(name in ('cont', 'x-fdisbull-arm-clock-budget') for name, _ in o.wire.calls)


@pytest.mark.parametrize('options', [
    {'text': ''}, {'text': 'A' * 65}, {'text': None}, {'text': True}, {'text': ['a']}, {'text': b'a'},
    {'text': 'valid\0'}, {'text': 'valid\x7f'}, {'text': 'valid\x08'}, {'text': 'valid\x1b'},
    {'text': 'valid\u00e9'}, {'text': 'valid\ud800'}, {'text': 'valid\u2603'},
    {'hold_ms': True}, {'hold_ms': 0}, {'hold_ms': 1001}, {'hold_ms': 1.5},
    {'gap_ms': False}, {'gap_ms': 0}, {'gap_ms': 1001}, {'gap_ms': '1'},
])
def test_invalid_text_is_atomic_before_native_admission(typing, options):
    o = typing
    before = o.session.input_state()
    parameters = dict(text='a')
    parameters.update(options)
    with pytest.raises(ValueError):
        o.session.keyboard_type(**parameters)
    assert not o.wire.calls and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('refusal', ['profile', 'command', 'physical-command', 'transaction', 'pending', 'held', 'armed-text', 'armed-press'])
def test_text_admission_preserves_existing_owner(typing, refusal):
    o = typing
    if refusal == 'profile':
        o.vm.machine_configuration['clock_profile']['profile'] = 'standard'
    elif refusal == 'command':
        o.vm.qmp_commands -= {ARM}
    elif refusal == 'physical-command':
        o.vm.qmp_commands -= {'input-send-event'}
    elif refusal in ('pending', 'held'):
        o.session.keyboard_key_down('b')
        if refusal == 'held':
            o.session.input_schedule(1000)
            o.wire.finish()
            o.session.input_schedule_observe()
    elif refusal == 'armed-text':
        o.session.keyboard_type('b')
    elif refusal == 'armed-press':
        o.session.keyboard_press('b')
    calls, before = list(o.wire.calls), o.session.input_state()
    if refusal == 'transaction':
        with o.project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                o.session.keyboard_type('a')
    else:
        with pytest.raises(ValueError):
            o.session.keyboard_type('a')
    assert o.wire.calls == calls and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('prefix', range(8))
def test_interruption_retains_exact_holds_and_discards_only_future_reservations(typing, prefix):
    o = typing
    enable_retrace(o)
    armed = o.session.keyboard_type('AA', hold_ms=7, gap_ms=11)
    run_with_stop(o, lambda: o.wire.stop_after(prefix))
    result = o.session.run(timeout_ms=1000)
    receipt, steps = result['input_delivery'], armed['typing']['steps']
    assert receipt['state'] == 'cancelled' and receipt['dispatch_ns'] is None
    assert receipt['typing']['dispatched_count'] == prefix and receipt['requires_resolution']
    expected = {}
    for step in steps[:prefix]:
        if step['down']:
            expected[step['lease']] = step['key']
        else:
            del expected[step['lease']]
    state = o.session.input_state()
    assert state['pending_edges'] == 8 - prefix
    assert {token: lease['key'] for token, lease in state['leases'].items()} == expected
    assert len(state['leases']) <= 2
    future = {step['lease'] for step in steps[prefix:] if step['down']}
    assert set(o.vm._physical_input['schedule']['lease_reservations']) == future
    assert o.session.input_schedule_observe()['native'] == receipt['native']
    assert o.session.input_state()['leases'] == state['leases']
    with pytest.raises(ValueError, match='reschedule or cancel'):
        o.session._execution_preflight('c', 1000)
    for schedule in (lambda: o.session.input_schedule(1000), o.session.input_schedule_retrace):
        with pytest.raises(ValueError, match='cannot be rescheduled'):
            schedule()
    with pytest.raises(ValueError):
        o.session.keyboard_type('b')
    with pytest.raises(ValueError):
        o.session.keyboard_press('b')
    calls = len(o.wire.calls)
    cancelled = o.session.input_cancel_pending()
    assert cancelled['cancelled_edges'] == 8 - prefix
    assert set(cancelled['cancelled_reserved_leases']) == future
    assert cancelled['cancelled_leases'] == []
    assert not o.vm._physical_input['schedule']['lease_reservations']
    assert not any(name == 'x-fdisbull-cancel-input' for name, _ in o.wire.calls[calls:])
    holds = o.session.input_state()['leases']
    assert set(holds) == set(expected)
    assert all(lease['make'] == 'native_dispatched' and lease['release'] is None for lease in holds.values())
    if holds:
        for token in holds:
            o.session.keyboard_key_up(token)
        release = o.session.input_schedule(1000)
        assert 'typing' not in release['native']
        o.wire.finish()
        o.session.input_schedule_observe()
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert o.session.keyboard_type('b')['state'] == 'armed'


def test_explicit_cancel_before_make_disarms_and_cancels_reserved_lifetimes(typing):
    o = typing
    o.session.keyboard_type('AA')
    result = o.session.input_cancel_pending()
    assert result['cancelled_edges'] == 8 and len(result['cancelled_reserved_leases']) == 4
    assert result['cancelled_leases'] == result['retained_dispatched_holds'] == []
    assert o.wire.input['state'] == 'cancelled'
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-cancel-input') == 1
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert not o.vm._physical_input['schedule']['lease_reservations'] and not o.vm.closed


@pytest.mark.parametrize(('path', 'replacement'), [
    (('typing', 'text'), 'AA'), (('typing', 'text'), True),
    (('typing', 'hold-ms'), True), (('typing', 'gap-ms'), False),
    (('typing', 'dispatched-count'), True), (('typing', 'dispatched-count'), 7),
    (('typing', 'steps', 0, 'key'), 'a'), (('typing', 'steps', 0, 'down'), 1),
    (('typing', 'steps', 0, 'delay-ns'), 1), (('typing', 'steps', 0, 'deadline-ns'), 2_001_001),
    (('typing', 'steps', 1, 'deadline-ns'), 4_001_000),
    (('typing', 'steps', 0, 'dispatch-ns'), 2_001_000),
    (('typing', 'steps', 4, 'delay-ns'), 2_000_000),
    (('typing', 'extra'), 1), (('extra',), 1), (('retrace',), {}), (('press',), {}),
])
def test_bad_native_arm_cannot_publish_a_text_queue(typing, path, replacement):
    o = typing
    o.wire.mutate = lambda value: change(value, path, replacement) if 'typing' in value else value
    with pytest.raises(DebuggerError) as raised:
        o.session.keyboard_type('Aa')
    assert o.vm.closed and not o.session.input_state()['valid']
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert raised.value.result['native']['typing']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


@pytest.mark.parametrize('fault', [
    'missing-dispatch', 'missing-next-deadline', 'invented-later-deadline',
    'fixed-gap-origin', 'early-dispatch', 'future-dispatch', 'early-terminal',
    'count-mismatch', 'top-dispatch-on-cancel', 'completed-cancel', 'short-completion',
])
def test_bad_callback_prefix_is_rejected_before_any_lease_commit(typing, fault, monkeypatch):
    o = typing
    armed = o.session.keyboard_type('Aa', hold_ms=7, gap_ms=11)
    o.wire.stop_after(4, lateness=123)
    value, steps = o.wire.input, o.wire.input['typing']['steps']
    if fault == 'missing-dispatch':
        del steps[0]['dispatch-ns']
    elif fault == 'missing-next-deadline':
        del steps[4]['deadline-ns']
    elif fault == 'invented-later-deadline':
        steps[5]['deadline-ns'] = 100_000_000
    elif fault == 'fixed-gap-origin':
        steps[4]['deadline-ns'] -= 123
    elif fault == 'early-dispatch':
        steps[3]['dispatch-ns'] = steps[3]['deadline-ns'] - 1
    elif fault == 'future-dispatch':
        steps[3]['dispatch-ns'] = o.wire.receipt['virtual-ns'] + 1
    elif fault == 'early-terminal':
        value['terminal-ns'] = steps[3]['dispatch-ns'] - 1
    elif fault == 'count-mismatch':
        value['typing']['dispatched-count'] = 3
    elif fault == 'top-dispatch-on-cancel':
        value['dispatch-ns'] = steps[3]['dispatch-ns']
    elif fault == 'completed-cancel':
        o.wire.stop_after(6)
        value.update(state='cancelled', reason='machine-stop')
        del value['dispatch-ns']
    elif fault == 'short-completion':
        value.update(state='dispatched', reason='dispatch-complete', **{'dispatch-ns': steps[3]['dispatch-ns']})
    commits = []
    monkeypatch.setattr(o.session, '_input_mark_text_prefix_dispatched', lambda *args: commits.append(args))
    with pytest.raises(DebuggerError) as raised:
        o.session.input_schedule_observe()
    assert not commits and o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['native']['token'] == armed['token']


def test_reconciliation_failure_leaves_entire_candidate_prefix_uncommitted(typing):
    o = typing
    o.session.keyboard_type('AA')
    state = o.vm._physical_input
    schedule = state['schedule']
    # The fifth edge would activate a different Shift lifetime. Corrupt only
    # that future reservation, after a whole valid first character in the prefix.
    fifth = schedule['records'][4]
    schedule['lease_reservations'][fifth['lease']]['key'] = 'ctrl'
    before = deepcopy(state)
    with pytest.raises(DebuggerError, match='reserved lifetime'):
        o.session._input_mark_text_prefix_dispatched(state, schedule, schedule['records'][:5], 'native_dispatched')
    assert state == before


@pytest.mark.parametrize('change_kind', ['grow', 'regress', 'rewrite'])
def test_terminal_prefix_cannot_grow_regress_or_rewrite(typing, change_kind):
    o = typing
    o.session.keyboard_type('AA')
    o.wire.stop_after(4)
    o.session.input_schedule_observe()
    if change_kind == 'grow':
        o.wire.stop_after(5)
    elif change_kind == 'regress':
        o.wire.input['typing']['dispatched-count'] = 3
    else:
        o.wire.input['typing']['steps'][0]['dispatch-ns'] += 1
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed


@pytest.mark.parametrize('fault', ['native-failed', 'malformed', 'persistence'])
def test_failed_prefix_retains_original_stop_and_raw_native_evidence(typing, monkeypatch, fault):
    o = typing
    armed = o.session.keyboard_type('Aa')
    def callback():
        o.wire.stop_after(2)
        if fault == 'native-failed':
            o.wire.input.update(state='failed', reason='Selected keyboard handler changed')
        elif fault == 'malformed':
            o.wire.input['typing']['steps'][0]['key'] = 'ctrl'
    if fault == 'persistence':
        original = o.session._event
        def event(name, value):
            if name == 'input.schedule-result':
                raise OSError('Authored text result persistence failure')
            return original(name, value)
        monkeypatch.setattr(o.session, '_event', event)
    run_with_stop(o, callback)
    with pytest.raises(OSError if fault == 'persistence' else DebuggerError) as raised:
        o.session.run(timeout_ms=1000)
    result = raised.value.result
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['input_schedule_native']['token'] == armed['token']
    assert result['input_schedule_native']['typing'] == o.wire.input['typing']
    assert o.vm.closed and not o.session.input_state()['valid']


@pytest.mark.parametrize(('cutoff_ms', 'before'), [(9, 1), (22, 2)])
@pytest.mark.parametrize('at_cutoff', [False, True])
def test_owned_budget_checks_release_and_next_character_make(typing, cutoff_ms, before, at_cutoff):
    o = typing
    o.session.keyboard_type('aa', hold_ms=7, gap_ms=11)
    def callback():
        cutoff = o.wire.receipt['budget-deadline-ns']
        o.wire.stop_after(before + at_cutoff, stopped_ns=cutoff, reason='budget-deadline')
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-fired-ns': cutoff,
                              'budget-stopped-ns': cutoff})
    run_with_stop(o, callback, reply=b'T02thread:1;')
    if at_cutoff:
        with pytest.raises(DebuggerError, match='budget cutoff') as raised:
            o.session.clock_advance(cutoff_ms * MS, timeout_ms=1000)
        assert raised.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert o.vm.closed
    else:
        result = o.session.clock_advance(cutoff_ms * MS, timeout_ms=1000)
        assert result['input_delivery']['typing']['dispatched_count'] == before
        assert result['input_delivery']['requires_resolution'] is True
        assert len(o.session.input_state()['leases']) == (1 if before == 1 else 0)


@pytest.mark.parametrize('fault', ['lost-arm', 'rejected-arm', 'persistence', 'persistence-overrun', 'final-copy'])
def test_uncertain_or_late_text_arm_closes_without_replay(typing, monkeypatch, fault):
    o = typing
    o.session._rpc_deadline = o.clock.now + .05
    if fault == 'lost-arm':
        o.wire.extra_latency[ARM] = 1
    elif fault == 'rejected-arm':
        o.wire.reject_arm = True
    elif fault == 'final-copy':
        original = qemu_keyboard_type.deepcopy
        def copy(value):
            result = original(value)
            if isinstance(value, dict) and value.get('format') == 'fdisbull-qemu-scheduled-input-1':
                o.clock.advance(.05)
            return result
        monkeypatch.setattr(qemu_keyboard_type, 'deepcopy', copy)
    else:
        original = o.session._event
        def event(name, value):
            if name == 'input.schedule-arm':
                if fault == 'persistence':
                    raise OSError('Authored text evidence failure')
                o.clock.advance(.05)
            return original(name, value)
        monkeypatch.setattr(o.session, '_event', event)
    expected = DebuggerError if fault == 'rejected-arm' else OSError if fault == 'persistence' else TimeoutError
    with pytest.raises(expected) as raised:
        o.session.keyboard_type('Aa')
    assert raised.value.result
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    assert o.vm.closed and not o.vm._physical_input['valid']
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)
    assert o.vm.operation_deadline is None and o.qmp.operation_deadline is None


def test_one_incoming_host_deadline_covers_admission_and_arm_reply(typing):
    o = typing
    o.session._rpc_deadline = o.clock.now + .05
    o.wire.latency = .006
    o.wire.extra_latency[ARM] = .03
    with pytest.raises(TimeoutError):
        o.session.keyboard_type('Aa')
    assert o.clock.now == pytest.approx(100.05)
    assert o.wire.calls[-1][0] == ARM and o.wire.budgets[-1] < .03
    assert o.wire.budgets == sorted(o.wire.budgets, reverse=True)
    assert o.vm.closed


def test_expired_admission_does_not_invalidate_a_valid_stopped_owner(typing):
    o = typing
    before = deepcopy(o.session._input_storage())
    o.session._rpc_deadline = o.clock.now
    with pytest.raises(TimeoutError, match='before admission'):
        o.session.keyboard_type('Aa')
    assert not o.wire.calls and not o.vm.closed and o.vm._physical_input == before


def test_nominal_horizon_overflow_precedes_arm_and_reservation_commit(typing):
    o = typing
    o.wire.receipt['virtual-ns'] = (1 << 63) - 10 * MS
    with pytest.raises(ValueError, match='horizon'):
        o.session.keyboard_type('Aa')
    assert not any(name == ARM for name, _ in o.wire.calls)
    assert not o.session.input_state()['pending'] and not o.session.input_state()['leases']
    assert not o.vm.closed


@pytest.mark.parametrize('mode', ['idle', 'ordinary', 'retrace', 'press'])
def test_text_descriptor_is_refused_on_other_schedule_modes(typing, mode):
    o = typing
    if mode == 'retrace':
        enable_retrace(o)
    if mode == 'press':
        o.session.keyboard_press('a')
    elif mode != 'idle':
        o.session.keyboard_key_down('a')
        if mode == 'ordinary':
            o.session.input_schedule(1000)
        else:
            o.session.input_schedule_retrace()
    o.wire.input['typing'] = {}
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed


def test_text_press_retrace_and_ordinary_arms_clear_each_others_descriptors(typing):
    o = typing
    enable_retrace(o)
    o.session.keyboard_type('Aa')
    o.wire.stop_after(1)
    o.session.input_schedule_observe()
    o.session.input_cancel_pending()
    token = next(iter(o.session.input_state()['leases']))
    o.session.keyboard_key_up(token)
    retrace = o.session.input_schedule_retrace()
    assert 'retrace' in retrace['native'] and 'typing' not in retrace['native']
    o.wire.callback()
    o.session.input_schedule_observe()
    press = o.session.keyboard_press('b')
    assert 'press' in press['native'] and 'typing' not in press['native'] and 'retrace' not in press['native']
    o.session.input_cancel_pending()
    typed = o.session.keyboard_type('b')
    assert 'typing' in typed['native'] and 'press' not in typed['native'] and 'retrace' not in typed['native']
    o.session.input_cancel_pending()
    o.session.keyboard_key_down('c')
    ordinary = o.session.input_schedule(1000)
    assert not {'typing', 'press', 'retrace'} & ordinary['native'].keys()
