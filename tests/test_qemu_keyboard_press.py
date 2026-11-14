"""Finite timed chords at the production host/QMP boundary.

These deterministic peers qualify validation and ownership. Independent native
IRQ1/BIOS witnesses establish actual device callbacks and selected consumption.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull import qemu_keyboard_press
from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration
from test_qemu_input_schedule import InputWire, scheduled
from test_qemu_io_deadlines import observation
from test_qemu_input_retrace import RetraceInputWire


ARM = 'x-fdisbull-arm-keyboard-press'


class PressWire(InputWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.reject_arm = False

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command != ARM:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        steps = [dict(key=key, down=True, **{'delay-ns': 2_000_000})
                 for key in [*args['modifiers'], args['key']]]
        steps.append(dict(key=args['key'], down=False, **{'delay-ns': args['hold-ms'] * 1_000_000}))
        steps.extend(dict(key=key, down=False, **{'delay-ns': 2_000_000})
                     for key in reversed(args['modifiers']))
        now = self.receipt['virtual-ns']
        steps[0]['deadline-ns'] = now + 2_000_000
        self.input = {'api-version': 1, 'epoch': 1, 'state': 'armed', 'virtual-ns': now,
            'token': args['token'], 'start-ns': now, 'deadline-ns': now + 2_000_000,
            'event-count': len(steps), 'press': dict(key=args['key'], modifiers=args['modifiers'],
                steps=steps, **{'hold-ms': args['hold-ms'], 'gap-ms': args['gap-ms'], 'dispatched-count': 0})}
        answer = ({'error': {'class': 'GenericError', 'desc': 'Keyboard handler lost ownership'}}
                  if self.reject_arm else {'return': self.mutate(deepcopy(self.input))})
        self.buffer.extend(json.dumps(dict(id=request['id'], **answer)).encode() + b'\n')
        self.delay = self.latency + self.extra_latency.get(command, 0)

    def stop_after(self, count, *, lateness=0, stopped_ns=None, reason='machine-stop'):
        press = self.input['press']
        steps = press['steps']
        for index in range(press['dispatched-count'], count):
            extra = lateness[index] if isinstance(lateness, (tuple, list)) else lateness
            actual = steps[index]['deadline-ns'] + extra
            steps[index]['dispatch-ns'] = actual
            self.receipt['virtual-ns'] = actual
            press['dispatched-count'] = index + 1
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
def press(scheduled):
    o = scheduled
    o.wire = PressWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= {ARM}
    o.session.capabilities['virtual_keyboard_press'] = True
    return o


def test_existing_press_facade_arms_passively_on_virtual_profile(press):
    o = press
    result = o.session.keyboard.press('a', hold_ms=20, gap_ms=57)
    assert result['state'] == 'armed'
    assert result['press']['format'] == 'fdisbull-keyboard-press-1'
    assert result['lateness_ns'] is None
    assert all(step['lateness_ns'] is None for step in result['press']['steps'])
    assert result['native']['press']['steps'] == [
        {'key': 'a', 'down': True, 'delay-ns': 2_000_000, 'deadline-ns': 2_001_000},
        {'key': 'a', 'down': False, 'delay-ns': 20_000_000},
    ]
    assert o.session.input_state()['pending_edges'] == 2
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-arm-clock-budget')
                   for name, _ in o.wire.calls)


def run_with_stop(o, callback, *, reply=b'T05thread:1;'):
    o.session._stopped = lambda: o.gdb

    def execute(command, timeout_ms):
        assert command == 'c'
        callback()
        return reply, False

    o.gdb.execute = execute


def change(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


def test_caller_modifier_order_actual_relative_delays_and_no_tail_gap(press):
    o = press
    armed = o.session.keyboard_press('a', modifiers=['alt', 'ctrl', 'shift'], hold_ms=23, gap_ms=987)
    plan = armed['native']['press']['steps']
    assert [(s['key'], s['down'], s['delay-ns']) for s in plan] == [
        ('alt', True, 2_000_000), ('ctrl', True, 2_000_000), ('shift', True, 2_000_000),
        ('a', True, 2_000_000), ('a', False, 23_000_000),
        ('shift', False, 2_000_000), ('ctrl', False, 2_000_000), ('alt', False, 2_000_000)]
    lateness = [100, 200, 300, 400, 500, 600, 700, 800]
    run_with_stop(o, lambda: o.wire.stop_after(8, lateness=lateness))
    result = o.session.run(timeout_ms=1000)
    delivered = result['input_delivery']
    steps = delivered['native']['press']['steps']
    assert [step['dispatch-ns'] - step['deadline-ns'] for step in steps] == lateness
    assert delivered['lateness_ns'] is None
    assert [step['lateness_ns'] for step in delivered['press']['steps']] == lateness
    for previous, step in zip(steps, steps[1:]):
        assert step['deadline-ns'] == previous['dispatch-ns'] + step['delay-ns']
    assert steps[4]['dispatch-ns'] - steps[3]['dispatch-ns'] >= 23_000_000
    assert delivered['dispatch_ns'] == delivered['terminal_ns'] == steps[-1]['dispatch-ns']
    assert delivered['terminal_ns'] == armed['start_ns'] + 37_000_000 + sum(lateness)
    assert delivered['press']['gap_ms'] == 987 and delivered['press']['gap_applied'] is False
    assert delivered['press']['dispatched_count'] == 8 and delivered['press']['undispatched_count'] == 0
    assert o.session.input_state()['pending_edges'] == 0 and not o.session.input_state()['leases']
    again = o.session.input_schedule_observe()
    assert again['native'] == delivered['native']
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    new = o.session.keyboard_press('esc')
    assert new['press']['key'] == 'escape' and new['native']['press']['key'] == 'esc'
    assert new['token'] != armed['token']


@pytest.mark.parametrize('options', [
    {'key': 'A'}, {'key': True}, {'key': []}, {'modifiers': ['shift', 'shift']},
    {'key': 'ctrl', 'modifiers': ['ctrl']}, {'modifiers': ['left']}, {'modifiers': 'ctrl'},
    {'modifiers': None}, {'hold_ms': True}, {'hold_ms': 0}, {'hold_ms': 1001},
    {'hold_ms': 1.5}, {'gap_ms': False}, {'gap_ms': 0}, {'gap_ms': 1001}, {'gap_ms': '1'},
])
def test_invalid_press_is_atomic_before_native_admission(press, options):
    o = press
    before = o.session.input_state()
    parameters = dict(key='a')
    parameters.update(options)
    with pytest.raises(ValueError):
        o.session.keyboard_press(**parameters)
    assert o.wire.calls == [] and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('refusal', ['profile', 'command', 'transaction', 'pending', 'held', 'armed'])
def test_press_preflight_cannot_take_over_existing_input(press, refusal):
    o = press
    if refusal == 'profile':
        o.vm.machine_configuration['clock_profile']['profile'] = 'standard'
    elif refusal == 'command':
        o.vm.qmp_commands -= {ARM}
    elif refusal in ('pending', 'held'):
        o.session.keyboard_key_down('b')
        if refusal == 'held':
            o.session.input_schedule(1000)
            o.wire.finish()
            o.session.input_schedule_observe()
    elif refusal == 'armed':
        o.session.keyboard_press('b')
    calls = list(o.wire.calls)
    before = o.session.input_state()
    if refusal == 'transaction':
        with o.project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                o.session.keyboard_press('a')
    else:
        with pytest.raises(ValueError):
            o.session.keyboard_press('a')
    assert o.wire.calls == calls and o.session.input_state() == before and not o.vm.closed


@pytest.mark.parametrize('prefix', range(6))
def test_stop_cancels_suffix_retains_each_held_prefix_and_requires_explicit_recovery(press, prefix):
    o = press
    armed = o.session.keyboard_press('a', modifiers=['ctrl', 'shift'], hold_ms=19)
    run_with_stop(o, lambda: o.wire.stop_after(prefix))
    result = o.session.run(timeout_ms=1000)
    receipt = result['input_delivery']
    assert receipt['state'] == 'cancelled' and receipt['dispatch_ns'] is None
    assert receipt['press']['dispatched_count'] == prefix and receipt['requires_resolution'] is True
    state = o.session.input_state()
    assert state['pending_edges'] == 6 - prefix
    held = set()
    for step in armed['press']['steps'][:prefix]:
        (held.add if step['down'] else held.remove)(step['key'])
    assert {item['key'] for item in state['leases'].values() if item['make'] == 'native_dispatched'} == held
    again = o.session.input_schedule_observe()
    assert again['native'] == receipt['native']
    assert o.session.input_state()['pending'] == state['pending']
    assert o.session.input_state()['leases'] == state['leases']
    with pytest.raises(ValueError, match='reschedule or cancel'):
        o.session._execution_preflight('c', 1000)
    with pytest.raises(ValueError, match='cannot be rescheduled'):
        o.session.input_schedule(1000)
    with pytest.raises(ValueError):
        o.session.keyboard_press('b')
    calls = list(o.wire.calls)
    cancelled = o.session.input_cancel_pending()
    assert cancelled['cancelled_edges'] == 6 - prefix
    remaining = o.session.input_state()['leases']
    assert {item['key'] for item in remaining.values()} == held
    assert all(item['make'] == 'native_dispatched' and item['release'] is None for item in remaining.values())
    assert not any(name == 'x-fdisbull-cancel-input' for name, _ in o.wire.calls[len(calls):])
    if remaining:
        with pytest.raises(ValueError, match='held leases'):
            o.session.keyboard_press('b')
        for lease in remaining:
            o.session.keyboard_key_up(lease)
        released = o.session.input_schedule(1000)
        assert 'press' not in released['native']
        o.wire.finish()
        o.session.input_schedule_observe()
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert o.session.keyboard_press('b')['state'] == 'armed'
    assert not any(name == 'input-send-event' for name, _ in o.wire.calls)


def test_explicit_cancel_before_first_make_disarms_and_discards_all_chord_leases(press):
    o = press
    o.session.keyboard_press('a', modifiers=['shift'])
    result = o.session.input_cancel_pending()
    assert result['cancelled_edges'] == 4 and len(result['cancelled_leases']) == 2
    assert not result['retained_dispatched_holds']
    assert o.wire.input['state'] == 'cancelled' and o.wire.input['press']['dispatched-count'] == 0
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-cancel-input') == 1
    assert not o.session.input_state()['leases'] and not o.vm.closed


@pytest.mark.parametrize(('path', 'replacement'), [
    (('press', 'key'), 'b'), (('press', 'modifiers'), ['alt']),
    (('press', 'hold-ms'), True), (('press', 'gap-ms'), False),
    (('press', 'dispatched-count'), True), (('press', 'dispatched-count'), 5),
    (('press', 'steps', 0, 'key'), 'a'), (('press', 'steps', 0, 'down'), 1),
    (('press', 'steps', 0, 'delay-ns'), 1), (('press', 'steps', 0, 'deadline-ns'), 2_001_001),
    (('press', 'steps', 1, 'deadline-ns'), 4_001_000),
    (('press', 'steps', 0, 'dispatch-ns'), 2_001_000),
    (('press', 'extra'), 1), (('extra',), 1), (('retrace',), {}),
])
def test_malformed_press_arm_cannot_create_owned_leases(press, path, replacement):
    o = press
    o.wire.mutate = lambda value: change(value, path, replacement) if 'press' in value else value
    with pytest.raises(DebuggerError) as raised:
        o.session.keyboard_press('a', modifiers=['shift'])
    assert o.vm.closed and not o.session.input_state()['valid']
    assert not o.session.input_state()['leases'] and not o.session.input_state()['pending']
    assert raised.value.result['native']['press']
    assert [name for name, _ in o.wire.calls].count(ARM) == 1


@pytest.mark.parametrize('fault', [
    'missing-dispatch', 'missing-next-deadline', 'invented-later-deadline',
    'absolute-next-deadline', 'early-dispatch', 'future-dispatch', 'late-terminal',
    'count-mismatch', 'top-dispatch-on-cancel', 'completed-cancel', 'short-completion',
])
def test_malformed_callback_prefix_is_rejected_before_host_lease_commit(press, fault, monkeypatch):
    o = press
    armed = o.session.keyboard_press('a', modifiers=['shift'])
    o.wire.stop_after(1, lateness=123)
    value = o.wire.input
    steps = value['press']['steps']
    if fault == 'missing-dispatch':
        del steps[0]['dispatch-ns']
    elif fault == 'missing-next-deadline':
        del steps[1]['deadline-ns']
    elif fault == 'invented-later-deadline':
        steps[2]['deadline-ns'] = 45_000_000
    elif fault == 'absolute-next-deadline':
        steps[1]['deadline-ns'] -= 123
    elif fault == 'early-dispatch':
        steps[0]['dispatch-ns'] = steps[0]['deadline-ns'] - 1
    elif fault == 'future-dispatch':
        steps[0]['dispatch-ns'] = o.wire.receipt['virtual-ns'] + 1
    elif fault == 'late-terminal':
        value['terminal-ns'] = steps[0]['dispatch-ns'] - 1
    elif fault == 'count-mismatch':
        value['press']['dispatched-count'] = 0
    elif fault == 'top-dispatch-on-cancel':
        value['dispatch-ns'] = steps[0]['dispatch-ns']
    elif fault == 'completed-cancel':
        o.wire.stop_after(4)
        value.update(state='cancelled', reason='machine-stop')
        del value['dispatch-ns']
    elif fault == 'short-completion':
        value.update(state='dispatched', reason='dispatch-complete', **{'dispatch-ns': steps[0]['dispatch-ns']})
    committed = []
    monkeypatch.setattr(o.session, '_input_mark_prefix_dispatched', lambda *args: committed.append(args))
    with pytest.raises(DebuggerError) as raised:
        o.session.input_schedule_observe()
    assert not committed and o.vm.closed and not o.session.input_state()['valid']
    assert raised.value.result['native']['token'] == armed['token']


def test_terminal_partial_prefix_cannot_grow_or_change_after_cancellation(press):
    o = press
    o.session.keyboard_press('a', modifiers=['shift'])
    o.wire.stop_after(1)
    o.session.input_schedule_observe()
    o.wire.stop_after(2)
    with pytest.raises(DebuggerError, match='Terminal'):
        o.session.input_schedule_observe()
    assert o.vm.closed


@pytest.mark.parametrize('fault', ['native-failed', 'malformed', 'persistence'])
def test_prefix_failure_keeps_original_stop_and_raw_native_receipt(press, monkeypatch, fault):
    o = press
    armed = o.session.keyboard_press('a', modifiers=['shift'])

    def callback():
        o.wire.stop_after(1)
        if fault == 'native-failed':
            o.wire.input.update(state='failed', reason='Selected keyboard handler changed')
        elif fault == 'malformed':
            o.wire.input['press']['steps'][0]['key'] = 'ctrl'

    if fault == 'persistence':
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-result':
                raise OSError('Authored timed keyboard result persistence failure')
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    run_with_stop(o, callback)
    with pytest.raises(OSError if fault == 'persistence' else DebuggerError) as raised:
        o.session.run(timeout_ms=1000)
    result = raised.value.result
    assert result['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['timed_out'] is False
    assert result['input_schedule_native']['token'] == armed['token']
    assert result['input_schedule_native']['press'] == o.wire.input['press']
    assert o.vm.closed and not o.session.input_state()['valid']


@pytest.mark.parametrize('fault', ['delivered-at-cutoff', 'cancelled-before-release'])
def test_owned_budget_cutoff_validates_every_edge_of_a_partial_prefix(press, fault):
    o = press
    o.session.keyboard_press('a', modifiers=['shift'], hold_ms=7)

    def callback():
        cutoff = o.wire.receipt['budget-deadline-ns']
        o.wire.stop_after(2 if fault == 'delivered-at-cutoff' else 1,
                          stopped_ns=cutoff, reason='budget-deadline')
        o.wire.receipt.update({'budget-state': 'stopped', 'budget-fired-ns': cutoff,
                              'budget-stopped-ns': cutoff})

    run_with_stop(o, callback, reply=b'T02thread:1;')
    if fault == 'delivered-at-cutoff':
        with pytest.raises(DebuggerError, match='budget cutoff') as raised:
            o.session.clock_advance(4_000_000, timeout_ms=1000)
        assert raised.value.result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
        assert o.vm.closed and not o.session.input_state()['valid']
    else:
        result = o.session.clock_advance(4_000_000, timeout_ms=1000)
        assert result['input_delivery']['press']['dispatched_count'] == 1
        assert result['input_delivery']['state'] == 'cancelled'
        state = o.session.input_state()
        assert {item['key'] for item in state['leases'].values() if item['make'] == 'native_dispatched'} == {'shift'}
        assert result['input_delivery']['requires_resolution'] is True and not o.vm.closed


@pytest.mark.parametrize('fault', ['lost-arm', 'rejected-arm', 'persistence', 'persistence-overrun', 'final-copy'])
def test_uncertain_or_late_arm_closes_without_replay(press, monkeypatch, fault):
    o = press
    o.session._rpc_deadline = o.clock.now + .05
    if fault == 'lost-arm':
        o.wire.extra_latency[ARM] = 1
    elif fault == 'rejected-arm':
        o.wire.reject_arm = True
    elif fault == 'final-copy':
        original = qemu_keyboard_press.deepcopy

        def copy(value):
            result = original(value)
            if isinstance(value, dict) and value.get('format') == 'fdisbull-qemu-scheduled-input-1':
                o.clock.advance(.05)
            return result

        monkeypatch.setattr(qemu_keyboard_press, 'deepcopy', copy)
    else:
        original = o.session._event

        def event(name, value):
            if name == 'input.schedule-arm':
                if fault == 'persistence':
                    raise OSError('Authored press evidence failure')
                o.clock.advance(.05)
            return original(name, value)

        monkeypatch.setattr(o.session, '_event', event)
    expected = (DebuggerError if fault == 'rejected-arm' else OSError if fault == 'persistence' else TimeoutError)
    with pytest.raises(expected) as raised:
        o.session.keyboard_press('a')
    assert raised.value.result
    assert [name for name, _ in o.wire.calls].count(ARM) == 1
    # The manually installed script deadline remains expired. Inspect retained
    # host ownership without issuing another budgeted public operation.
    assert o.vm.closed and not o.vm._physical_input['valid']
    assert not any(name in ('cont', 'input-send-event', 'x-fdisbull-cancel-input') for name, _ in o.wire.calls)
    assert o.vm.operation_deadline is None and o.qmp.operation_deadline is None


def test_arm_uses_one_deadline_through_admission_and_native_reply(press):
    o = press
    o.session._rpc_deadline = o.clock.now + .05
    o.wire.latency = .006
    o.wire.extra_latency[ARM] = .03
    with pytest.raises(TimeoutError):
        o.session.keyboard_press('a')
    assert o.clock.now == pytest.approx(100.05)
    assert o.wire.calls[-1][0] == ARM
    assert o.wire.budgets[-1] < .03
    assert o.wire.budgets == sorted(o.wire.budgets, reverse=True)
    assert o.vm.closed


def test_nominal_horizon_overflow_refuses_before_any_arm_or_lease(press):
    o = press
    o.wire.receipt['virtual-ns'] = (1 << 63) - 2_000_000
    with pytest.raises(ValueError, match='horizon'):
        o.session.keyboard_press('a')
    assert not any(name == ARM for name, _ in o.wire.calls)
    assert not o.session.input_state()['pending'] and not o.session.input_state()['leases']
    assert not o.vm.closed


@pytest.mark.parametrize('old', ['idle', 'ordinary', 'retrace'])
def test_press_descriptor_is_rejected_on_every_other_schedule_mode(press, old):
    o = press
    if old == 'retrace':
        enable_retrace(o)
    if old != 'idle':
        o.session.keyboard_key_down('a')
        if old == 'ordinary':
            o.session.input_schedule(1000)
        else:
            o.session.input_schedule_retrace()
    o.wire.input['press'] = {}
    with pytest.raises(DebuggerError):
        o.session.input_schedule_observe()
    assert o.vm.closed


class PressRetraceWire(PressWire, RetraceInputWire):
    pass


def enable_retrace(o):
    o.wire = PressRetraceWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= RETRACE_COMMANDS | {'x-fdisbull-arm-input-retrace'}
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    o.vm.native_clock_admission = deepcopy(o.wire.receipt)
    o.vm.native_retrace_admission = deepcopy(o.wire.video.value())
    o.vm._retrace_last = deepcopy(o.wire.video.value())


def test_ordinary_and_retrace_modes_clear_press_without_replaying_a_partial_chord(press):
    o = press
    enable_retrace(o)
    o.session.keyboard_press('a', modifiers=['shift'])
    o.wire.stop_after(1)
    o.session.input_schedule_observe()
    with pytest.raises(ValueError, match='cannot be rescheduled'):
        o.session.input_schedule_retrace()
    o.session.input_cancel_pending()
    lease = next(iter(o.session.input_state()['leases']))
    o.session.keyboard_key_up(lease)
    retrace = o.session.input_schedule_retrace()
    assert 'press' not in retrace['native'] and 'retrace' in retrace['native']
    o.wire.callback()
    o.session.input_schedule_observe()
    assert not o.session.input_state()['leases']
    pressed = o.session.keyboard_press('b')
    assert 'press' in pressed['native'] and 'retrace' not in pressed['native']
    o.session.input_cancel_pending()
    o.session.keyboard_key_down('c')
    ordinary = o.session.input_schedule(1000)
    assert 'press' not in ordinary['native'] and 'retrace' not in ordinary['native']


def test_timed_press_does_not_enable_text_or_change_general_timed_input_capability(press):
    o = press
    with pytest.raises(ValueError, match='Timed keyboard text'):
        o.session.keyboard_type('hello')
    assert o.session.capabilities['virtual_keyboard_press'] is True
    assert o.session.capabilities['timed_input'] is False
    assert not o.wire.calls
