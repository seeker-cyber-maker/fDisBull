"""One-shot physical-input dispatch on the admitted QEMU virtual clock.

Arming never executes the guest. The next bounded continue owns the attempt;
an early stop cancels its timer and requires an explicit reschedule or cancel.
A native dispatch receipt describes PS/2 callbacks and their final sync, not
device FIFO acceptance, guest consumption, or a completed application frame.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
from .qemu_input import MAX_PENDING_EDGES
from .qemu_keyboard_press import press_receipt, validate_native_press
from .qemu_keyboard_type import typing_receipt, validate_native_typing
from .qemu_mouse_click import click_receipt, validate_native_click
from .qemu_mapped_mouse import motion_receipt, validate_native_motion
from .qemu_retrace import RETRACE_COMMANDS, validate_retrace_snapshot


INPUT_SCHEDULE_COMMANDS = frozenset({
    'x-fdisbull-arm-input', 'x-fdisbull-query-input', 'x-fdisbull-cancel-input',
})
INPUT_RETRACE_COMMANDS = frozenset({'x-fdisbull-arm-input-retrace'})
MAX_INPUT_DELAY_NS = 60_000_000_000
FORMAT = 'fdisbull-qemu-scheduled-input-1'
_RETRACE_CANCELLATIONS = frozenset({'retrace-timing-changed', 'retrace-missed-window'})


def validate_input_delay(delta_ns):
    if type(delta_ns) is not int or not 1 <= delta_ns <= MAX_INPUT_DELAY_NS:
        raise ValueError('Input delta_ns must be an integer in 1..60000000000')


def validate_retrace_input_parameters(*, edge='enter', timeout_ms=1000):
    """Validate literals before touching a native timer or pending lease."""
    if type(edge) is not str or edge not in ('enter', 'exit'):
        raise ValueError('Retrace input edge must be enter or exit')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Retrace input timeout_ms must be an integer in 1..600000')


def _retrace_input_window(armed, edge):
    if not armed['phase-supported']:
        raise ValueError('Retrace input phase is unsupported: ' + armed['unsupported-reason'])
    timing = armed['timing']
    tick, horizontal = timing['ticks-per-char'], timing['htotal']
    period = tick * timing['total-chars']
    entry = tick * horizontal * timing['vstart']
    exit_ = tick * horizontal * (timing['vend'] + 1)
    if entry == 0 and exit_ == period:
        raise ValueError('Retrace input requires a real transition, not a whole-period interval')
    now = armed['virtual-ns']
    phase = entry if edge == 'enter' else exit_ % period
    delta = (phase - now) % period or period
    validate_input_delay(delta)
    width = exit_ - entry if edge == 'enter' else period - (exit_ - entry)
    target = now + delta
    if target > (1 << 63) - 1 or target + width > (1 << 63) - 1:
        raise ValueError('Retrace input target or window would overflow signed nanoseconds')
    return target, target + width


def _retrace_input_remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Retrace input scheduling requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError('Retrace input scheduling host deadline expired')


def _invalid(owner, message):
    owner._input_invalidate(message)
    owner.vm.close()
    raise DebuggerError(message)


def _timed_mode(schedule):
    return next((mode for mode in ('press', 'typing', 'click') if schedule and mode in schedule), None)


def _timed_label(schedule):
    mode = _timed_mode(schedule)
    return 'mouse click' if mode == 'click' else 'keyboard text' if mode == 'typing' else 'keyboard press'


def _pending_records(schedule):
    return (schedule['records'][schedule['applied_count']:]
            if _timed_mode(schedule) else schedule['records'])


def _native_retrace_schedule(owner, value, expected):
    """Validate frozen arm/callback evidence without advancing live retrace state.

    Only validated callback cancellations may precede the final owned VM stop.
    A later current VGA observation cannot validate or relabel that callback.
    """
    planned = expected.get('retrace') if expected is not None else None
    if planned is None:
        if 'retrace' in value or value.get('reason') in _RETRACE_CANCELLATIONS:
            _invalid(owner, 'Ordinary native input invented retrace scheduling evidence')
        return False
    descriptor = value.get('retrace')
    try:
        keys = {'edge', 'target-ns', 'window-end-ns', 'armed'}
        if (type(descriptor) is not dict or not keys <= descriptor.keys()
                or set(descriptor) - keys - {'checked'}
                or type(descriptor['edge']) is not str or descriptor['edge'] != planned['edge']
                or any(type(descriptor[key]) is not int or not 0 <= descriptor[key] < 1 << 63
                       for key in ('target-ns', 'window-end-ns'))):
            raise ValueError('Invalid native retrace-input descriptor fields')
        armed = validate_retrace_snapshot(descriptor['armed'], epoch=value['epoch'],
            virtual_ns=value['start-ns'], previous=planned['before']['native'])
        if armed != planned['before']['native']:
            raise ValueError('Native retrace-input arm differs from its exact stopped observation')
        target, end = _retrace_input_window(armed, descriptor['edge'])
        if (descriptor['target-ns'] != target or descriptor['window-end-ns'] != end
                or target != planned['target_ns'] or end != planned['window_end_ns']
                or value['deadline-ns'] != target):
            raise ValueError('Native retrace-input target or window differs from its owned occurrence')
        if value.get('reason') in _RETRACE_CANCELLATIONS and value['state'] != 'cancelled':
            raise ValueError('Native retrace-input cancellation reason contradicts its state')
        semantic_cancel = (value['state'] == 'cancelled'
                           and value.get('reason') in _RETRACE_CANCELLATIONS)
        needs_check = value['state'] == 'dispatched' or semantic_cancel
        if value['state'] != 'failed' and ('checked' in descriptor) != needs_check:
            raise ValueError('Native retrace-input callback snapshot presence is invalid')
        checked = None
        if 'checked' in descriptor:
            checked = validate_retrace_snapshot(descriptor['checked'], epoch=value['epoch'],
                virtual_ns=value['terminal-ns'], previous=armed)
        if needs_check:
            if checked['virtual-ns'] < target:
                raise ValueError('Native retrace-input callback preceded its target')
            same_generation = checked['timing-generation'] == armed['timing-generation']
            if value['state'] == 'dispatched':
                if (not same_generation or not checked['phase-supported']
                        or checked['virtual-ns'] != value['dispatch-ns']
                        or not target <= value['dispatch-ns'] < end):
                    raise ValueError('Native input dispatch lacks its original retrace-window boundary')
            elif value['reason'] == 'retrace-timing-changed':
                if checked['timing-generation'] <= armed['timing-generation']:
                    raise ValueError('Native retrace timing-change cancellation has no newer generation')
            elif not same_generation or checked['virtual-ns'] < end:
                raise ValueError('Native retrace missed-window cancellation has no matching missed occurrence')
        return semantic_cancel
    except (ValueError, KeyError, TypeError) as error:
        _invalid(owner, str(error))


def _native_schedule(owner, value, clock, expected, *, owned_budget=None, after_stop=False):
    def integer(item, maximum=(1 << 63) - 1):
        return type(item) is int and 0 <= item <= maximum

    required = {'api-version', 'epoch', 'state', 'virtual-ns', 'event-count'}
    if (not isinstance(value, dict) or not required <= value.keys()
            or type(value['api-version']) is not int or value['api-version'] != 1
            or not integer(value['epoch'], (1 << 64) - 1)
            or value['epoch'] != clock['virtual_clock']['native']['epoch']
            or not integer(value['virtual-ns']) or value['virtual-ns'] != clock['virtual_ns']
            or not integer(value['event-count'], MAX_PENDING_EDGES)
            or value['state'] not in ('idle', 'armed', 'dispatched', 'cancelled', 'failed')):
        _invalid(owner, 'Invalid native scheduled-input receipt')
    optional = ('token', 'start-ns', 'deadline-ns', 'terminal-ns', 'dispatch-ns', 'reason')
    if value['state'] == 'idle':
        if (expected is not None or value['event-count'] or 'retrace' in value or 'motion' in value or _timed_mode(value)
                or any(key in value for key in optional)):
            _invalid(owner, 'Idle native input unexpectedly owns a schedule')
        return deepcopy(value)
    if (expected is None or value.get('token') != expected['token']
            or not integer(value.get('start-ns')) or value['start-ns'] != expected['start_ns']
            or not integer(value.get('deadline-ns')) or value['deadline-ns'] != expected['deadline_ns']
            or value['start-ns'] > value['virtual-ns']
            or value['event-count'] != len(expected['records'])):
        _invalid(owner, 'Native input schedule identity differs from its owned batch')
    terminal = value['state'] != 'armed'
    if terminal:
        try:
            reason_bytes = value['reason'].encode('utf-8') if type(value.get('reason')) is str else b''
        except UnicodeEncodeError:
            reason_bytes = b''
        if (not integer(value.get('terminal-ns'))
                or not value['start-ns'] <= value['terminal-ns'] <= value['virtual-ns']
                or not 1 <= len(reason_bytes) <= 256):
            _invalid(owner, 'Native input terminal time or reason is invalid')
    elif (any(key in value for key in ('terminal-ns', 'dispatch-ns', 'reason'))
          or value['virtual-ns'] >= value['deadline-ns']):
        _invalid(owner, 'Armed native input has an impossible terminal boundary')
    if value['state'] == 'dispatched':
        if (not integer(value.get('dispatch-ns'))
                or not value['deadline-ns'] <= value['dispatch-ns'] == value['terminal-ns']):
            _invalid(owner, 'Native input dispatch preceded its requested deadline')
    elif 'dispatch-ns' in value:
        _invalid(owner, 'Undispatched native input invented a dispatch time')
    try:
        if sum(mode in value for mode in ('press', 'typing', 'click', 'retrace', 'motion')) > 1:
            raise ValueError('Native input receipt mixes mutually exclusive plan descriptors')
        validate_native_press(value, expected)
        validate_native_typing(value, expected)
        validate_native_click(value, expected)
        motion_cancel = validate_native_motion(value, expected, vm=owner.vm)
    except (ValueError, KeyError, TypeError) as error:
        _invalid(owner, str(error))
    semantic_cancel = _native_retrace_schedule(owner, value, expected) or motion_cancel
    timed_mode = _timed_mode(expected)
    if expected.get('retrace') is not None or expected.get('motion') is not None or timed_mode:
        mode = timed_mode or ('motion' if expected.get('motion') is not None else 'retrace')
        exact = required | {'token', 'start-ns', 'deadline-ns', mode}
        if terminal:
            exact |= {'terminal-ns', 'reason'}
        if value['state'] == 'dispatched':
            exact.add('dispatch-ns')
        if set(value) != exact:
            _invalid(owner, 'Native retrace-input receipt has unexpected fields' if mode == 'retrace'
                     else 'Native mapped-motion receipt has unexpected fields' if mode == 'motion'
                     else 'Native timed mouse receipt has unexpected fields' if mode == 'click'
                     else 'Native timed keyboard receipt has unexpected fields')
    # This is the budget owned by this execution, never a retained historical
    # receipt from an earlier run. Check it before any lease transition.
    if owned_budget is not None:
        observed_budget = clock['virtual_clock']['native']
        if (observed_budget['budget-state'] != 'stopped'
                or observed_budget.get('budget-stopped-ns') != value['virtual-ns']
                or any(observed_budget.get(key) != owned_budget.get(key) for key in
                       ('epoch', 'budget-token', 'budget-start-ns', 'budget-deadline-ns'))):
            _invalid(owner, 'Scheduled input lost its owned clock budget at the stop')
        if (value['state'] == 'dispatched'
                and value['dispatch-ns'] >= owned_budget['budget-deadline-ns']):
            _invalid(owner, 'Native input dispatch reached the owned clock budget cutoff')
        if semantic_cancel and value['terminal-ns'] >= owned_budget['budget-deadline-ns']:
            _invalid(owner, 'Native guarded input callback reached the owned clock budget cutoff')
        if timed_mode and any(step.get('dispatch-ns', -1) >= owned_budget['budget-deadline-ns']
                              for step in value[timed_mode]['steps']):
            _invalid(owner, 'Native timed mouse edge reached the owned clock budget cutoff' if timed_mode == 'click'
                     else 'Native timed keyboard edge reached the owned clock budget cutoff')
    if (after_stop and expected['bound'] and value['state'] == 'cancelled'
            and not semantic_cancel and value['terminal-ns'] != value['virtual-ns']):
        _invalid(owner, 'Native input cancellation differs from its first owned stop time')
    prior = expected.get('native')
    if prior is not None:
        if value['virtual-ns'] < prior['virtual-ns']:
            _invalid(owner, 'Native input observation time regressed')
        if prior['state'] != 'armed':
            frozen = lambda item: {key: data for key, data in item.items() if key != 'virtual-ns'}
            if frozen(value) != frozen(prior):
                _invalid(owner, 'Terminal native input changed after its one-shot attempt')
    if value['state'] == 'failed':
        _invalid(owner, 'Native input dispatch failed: ' + value['reason'])
    return deepcopy(value)


class QemuScheduledInputMixin:
    def _input_schedule_context(self):
        self._input_no_transaction()
        if (self.vm.machine_configuration.get('clock_profile', {}).get('profile') != 'virtual'
                or not INPUT_SCHEDULE_COMMANDS <= getattr(self.vm, 'qmp_commands', frozenset())):
            raise ValueError('Input scheduling requires the virtual clock and native input extension API 1')
        self._input_prepare(allow_schedule=True)
        return self.clock_observe()

    def _input_schedule_receipt(self, native, clock, schedule):
        dispatched = native.get('dispatch-ns')
        result = dict(format=FORMAT, context='machine', run=self.run_id,
                    session_id=self._input_storage()['session_id'], epoch=clock['epoch'],
                    token=native.get('token'), state=native['state'],
                    clock_domain='QEMU_CLOCK_VIRTUAL', observed_ns=native['virtual-ns'],
                    start_ns=native.get('start-ns'), deadline_ns=native.get('deadline-ns'),
                    terminal_ns=native.get('terminal-ns'), dispatch_ns=dispatched,
                    lateness_ns=(dispatched - native['deadline-ns']
                                 if dispatched is not None and not _timed_mode(schedule) else None),
                    reason=native.get('reason'), edge_count=native['event-count'],
                    sequences=[record['sequence'] for record in schedule['records']] if schedule else [],
                    requires_resolution=bool(schedule and schedule['bound'] and native['state'] == 'cancelled'),
                    guest_consumed=None, device_queue_accepted=None,
                    clock=deepcopy(clock), native=deepcopy(native),
                    claim='Native PS/2 callbacks and final sync only; device acceptance, guest consumption, frame completion and host-time synchronization are not established.')
        if schedule is not None and schedule.get('retrace') is not None:
            planned = schedule['retrace']
            descriptor = native['retrace']
            result['retrace'] = dict(format='fdisbull-retrace-input-1', edge=planned['edge'],
                target_ns=planned['target_ns'], window_end_ns=planned['window_end_ns'],
                before=deepcopy(planned['before']), native_arm=deepcopy(descriptor['armed']),
                native_check=deepcopy(descriptor.get('checked')),
                dispatch_phase_verified=native['state'] == 'dispatched',
                claim='Native modeled-phase PS/2 callbacks and final sync only; device acceptance, '
                      'guest consumption, guest-frame completion and the full VBlank interval remain unknown.')
        if schedule is not None and schedule.get('press') is not None:
            result['press'] = press_receipt(native, schedule)
        if schedule is not None and schedule.get('typing') is not None:
            result['typing'] = typing_receipt(native, schedule)
        if schedule is not None and schedule.get('click') is not None:
            result['click'] = click_receipt(native, schedule)
        if schedule is not None and schedule.get('motion') is not None:
            result['motion'] = motion_receipt(native, schedule)
        return result

    def _input_schedule_read(self, clock, *, owned_budget=None, after_stop=False):
        state = self._input_storage()
        schedule = state.get('schedule')
        received = None
        try:
            received = self.vm.qmp.call('x-fdisbull-query-input')
            native = _native_schedule(self, received, clock, schedule,
                                      owned_budget=owned_budget, after_stop=after_stop)
            if schedule is not None:
                self._input_schedule_accept(native, clock)
            return native
        except BaseException as error:
            planned = schedule.get('retrace') if schedule is not None else None
            motion = schedule.get('motion') if schedule is not None else None
            mode = _timed_mode(schedule)
            if (planned is not None or motion is not None or mode
                    or type(received) is dict and ('retrace' in received or 'motion' in received or _timed_mode(received))):
                error.input_schedule_native = deepcopy(received)
                if planned is not None:
                    error.input_schedule_retrace_before = deepcopy(planned['before'])
                if motion is not None:
                    error.input_schedule_motion_before = deepcopy(motion['before'])
                # The execution owner will join these attributes to its already
                # observed GDB stop. Do not replace that stop's error.result here.
                if not after_stop and getattr(error, 'result', None) is None:
                    error.result = dict(native=deepcopy(received), validation_failed=True)
                    if planned is not None:
                        error.result['retrace_before'] = deepcopy(planned['before'])
                    if mode:
                        error.result[mode + '_plan'] = deepcopy(schedule[mode])
                    if motion is not None:
                        error.result['motion_plan'] = deepcopy(motion)
            self._input_invalidate('Native input observation failed; schedule must not be replayed')
            self.vm.close()
            raise

    def _input_schedule_accept(self, native, clock):
        state = self._input_storage()
        schedule = state['schedule']
        if schedule['bound']:
            if state['pending'] != _pending_records(schedule):
                _invalid(self, 'Owned pending input changed beneath its native schedule')
            mode = _timed_mode(schedule)
            if mode:
                count = native[mode]['dispatched-count']
                if count < schedule['applied_count']:
                    _invalid(self, 'Owned timed mouse applied prefix regressed' if mode == 'click'
                             else 'Owned timed keyboard applied prefix regressed')
                records = schedule['records'][schedule['applied_count']:count]
                if mode == 'typing':
                    self._input_mark_text_prefix_dispatched(state, schedule, records, 'native_dispatched')
                elif mode == 'click':
                    self._input_mark_click_prefix_dispatched(state, records, 'native_dispatched')
                else:
                    self._input_mark_prefix_dispatched(state, records, 'native_dispatched')
                schedule['applied_count'] = count
                if native['state'] == 'dispatched':
                    schedule['bound'] = False
            elif native['state'] == 'dispatched':
                self._input_mark_dispatched(state, schedule['records'], 'native_dispatched')
                schedule['bound'] = False
        schedule['native'] = deepcopy(native)
        result = self._input_schedule_receipt(native, clock, schedule)
        state['schedule_receipt'] = result
        if native['state'] in ('dispatched', 'cancelled'):
            state['last_delivery'] = deepcopy(result)
        return result

    def _input_schedule_preflight(self):
        state = self._input_storage()
        schedule = state.get('schedule')
        if schedule is not None and schedule['bound']:
            if state['pending'] != _pending_records(schedule):
                _invalid(self, 'Owned pending input changed beneath its native schedule')
            if schedule['native']['state'] != 'armed':
                if 'motion' in schedule:
                    raise ValueError('Interrupted mapped mouse motion requires explicit input_cancel_pending before another run')
                raise ValueError('Interrupted scheduled input requires explicit reschedule or cancel before another run')

    def _input_schedule_after_stop(self):
        clock = self._input_schedule_context()
        native = self._input_schedule_read(clock,
            owned_budget=getattr(self.vm, '_active_clock_budget', None), after_stop=True)
        result = self._input_storage()['schedule_receipt']
        try:
            if native['state'] not in ('dispatched', 'cancelled'):
                _invalid(self, 'Native input timer survived the owned execution stop')
            self._input_persist('input.schedule-result', result)
        except BaseException as error:
            if 'retrace' in result or 'motion' in result or _timed_mode(result):
                # The native callback is already validated even if journaling
                # fails. Preserve it beside the execution owner's actual stop.
                error.input_schedule_native = deepcopy(native)
                if 'retrace' in result:
                    error.input_schedule_retrace_before = deepcopy(result['retrace']['before'])
                if 'motion' in result:
                    error.input_schedule_motion_before = deepcopy(result['motion']['before'])
            raise
        return deepcopy(result)

    def input_schedule(self, delta_ns):
        """Arm the current pending batch; the caller explicitly runs the VM."""
        validate_input_delay(delta_ns)
        state = self._input_storage()
        if self._input_schedule_bound() and 'motion' in state['schedule']:
            raise ValueError('Mapped mouse motion requires explicit input_cancel_pending; its binding cannot be rescheduled')
        if self._input_schedule_bound() and _timed_mode(state['schedule']):
            raise ValueError('Timed ' + _timed_label(state['schedule']) +
                             ' requires explicit input_cancel_pending; its suffix cannot be rescheduled')
        if not state['pending']:
            raise ValueError('Queue physical input before scheduling a native batch')
        # One mouse sync represents its final button state, so two transitions
        # of the same button cannot be represented faithfully in one batch.
        buttons = [record['event']['data']['button'] for record in state['pending']
                   if record['event']['type'] == 'btn']
        if len(buttons) != len(set(buttons)):
            raise ValueError('Schedule at most one edge per mouse button in a batch')
        clock = self._input_schedule_context()
        prior = self._input_schedule_read(clock)
        if prior['state'] == 'armed':
            raise ValueError('Cancel the current native input schedule before arming another')
        if not state['pending']:
            raise ValueError('The prior scheduled batch was already dispatched; queue new physical input')
        if clock['virtual_ns'] > (1 << 63) - 1 - delta_ns:
            raise ValueError('Native input deadline would overflow signed nanoseconds')
        schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'],
                        deadline_ns=clock['virtual_ns'] + delta_ns,
                        records=deepcopy(state['pending']), bound=True)
        try:
            native = _native_schedule(self, self.vm.qmp.call('x-fdisbull-arm-input', {
                'token': schedule['token'], 'delta-ns': delta_ns,
                'events': [record['event'] for record in schedule['records']]}), clock, schedule)
            if native['state'] != 'armed':
                _invalid(self, 'Native input arm did not leave a passive scheduled batch')
            state['schedule'] = schedule
            result = self._input_schedule_accept(native, clock)
            self._input_persist('input.schedule-arm', result)
            return deepcopy(result)
        except BaseException:
            self._input_invalidate('Native input arm outcome is uncertain; batch must not be replayed')
            self.vm.close()
            raise

    def input_schedule_retrace(self, *, edge='enter', timeout_ms=1000):
        """Passively arm one pending batch for one declared retrace occurrence."""
        validate_retrace_input_parameters(edge=edge, timeout_ms=timeout_ms)
        self._input_no_transaction()
        configuration = self.vm.machine_configuration
        commands = INPUT_SCHEDULE_COMMANDS | INPUT_RETRACE_COMMANDS | RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
        if (configuration.get('clock_profile', {}).get('profile') != 'virtual'
                or configuration.get('retrace_profile', {}).get('profile') != 'precise'
                or not commands <= getattr(self.vm, 'qmp_commands', frozenset())):
            raise ValueError('Retrace input scheduling requires the native input/retrace extensions and explicit virtual/precise profiles')
        state = self._input_storage()
        if self._input_schedule_bound() and 'motion' in state['schedule']:
            raise ValueError('Mapped mouse motion requires explicit input_cancel_pending; its binding cannot be rescheduled')
        if self._input_schedule_bound() and _timed_mode(state['schedule']):
            raise ValueError('Timed ' + _timed_label(state['schedule']) +
                             ' requires explicit input_cancel_pending; its suffix cannot be rescheduled')
        if not state['pending']:
            raise ValueError('Queue physical input before scheduling a retrace batch')
        buttons = [record['event']['data']['button'] for record in state['pending']
                   if record['event']['type'] == 'btn']
        if len(buttons) != len(set(buttons)):
            raise ValueError('Schedule at most one edge per mouse button in a batch')
        _retrace_input_remaining(self)
        clock = self._input_schedule_context()
        prior = self._input_schedule_read(clock)
        if prior['state'] == 'armed':
            raise ValueError('Cancel the current native input schedule before arming another')
        if not state['pending']:
            raise ValueError('The prior scheduled batch was already dispatched; queue new physical input')
        before = self.retrace_observe(timeout_ms=timeout_ms)
        try:
            target, window_end = _retrace_input_window(before['native'], edge)
        except ValueError as error:
            # Supported observations can still contain a full-period interval.
            # This known refusal has not touched the native timer or the queue.
            error.result = dict(edge=edge, before=deepcopy(before), armed=False)
            raise
        clock = before['clocks']['after']
        schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'], deadline_ns=target,
            records=deepcopy(state['pending']), bound=True,
            retrace=dict(edge=edge, target_ns=target, window_end_ns=window_end,
                         before=deepcopy(before)))
        received = result = None
        # Once the arm is sent, a lost/late reply or failed evidence write is
        # uncertain ownership. Close without replaying or synthesizing releases.
        try:
            _retrace_input_remaining(self)
            received = self.vm.qmp.call('x-fdisbull-arm-input-retrace', {
                'token': schedule['token'], 'events': [record['event'] for record in schedule['records']],
                'edge': edge, 'expected-epoch': before['native_epoch'],
                'expected-device': before['device'], 'expected-model': before['model'],
                'expected-generation': before['timing_generation'],
                'expected-virtual-ns': before['observed_ns']})
            native = _native_schedule(self, received, clock, schedule)
            if native['state'] != 'armed':
                _invalid(self, 'Native retrace-input arm did not leave a passive scheduled batch')
            state['schedule'] = schedule
            result = self._input_schedule_accept(native, clock)
            _retrace_input_remaining(self)
            self._input_persist('input.schedule-arm', result)
            _retrace_input_remaining(self)
            return deepcopy(result)
        except BaseException as error:
            if getattr(error, 'result', None) is None:
                error.result = (deepcopy(result) if result is not None else
                    dict(edge=edge, before=deepcopy(before), native=deepcopy(received), armed=None))
            self._input_invalidate('Native retrace-input arm outcome is uncertain; batch must not be replayed')
            self.vm.close()
            raise

    def input_schedule_observe(self):
        clock = self._input_schedule_context()
        native = self._input_schedule_read(clock)
        result = self._input_schedule_receipt(native, clock, self._input_storage().get('schedule'))
        try:
            self._input_persist('input.schedule-observe', result)
        except BaseException as error:
            if ('retrace' in result or 'motion' in result or _timed_mode(result)) and getattr(error, 'result', None) is None:
                error.result = deepcopy(result)
            raise
        return result

    def _input_schedule_before_cancel(self):
        """Prove native disarm before Python can forget any unsent edge."""
        state = self._input_storage()
        schedule = state.get('schedule')
        if schedule is None or not schedule['bound']:
            return None
        clock = self._input_schedule_context()
        native = self._input_schedule_read(clock)
        if native['state'] == 'armed':
            received = None
            try:
                received = self.vm.qmp.call('x-fdisbull-cancel-input', {'token': schedule['token']})
                native = _native_schedule(self, received, clock, schedule)
                if native['state'] != 'cancelled' or native['terminal-ns'] != clock['virtual_ns']:
                    _invalid(self, 'Native input cancellation did not establish an undispatched terminal batch')
                self._input_schedule_accept(native, clock)
            except BaseException as error:
                mode = _timed_mode(schedule)
                if mode and getattr(error, 'result', None) is None:
                    error.result = dict(native=deepcopy(received), validation_failed=True,
                                        **{mode + '_plan': deepcopy(schedule[mode])})
                if 'motion' in schedule and getattr(error, 'result', None) is None:
                    error.result = dict(native=deepcopy(received), validation_failed=True,
                                        motion_plan=deepcopy(schedule['motion']))
                self._input_invalidate('Native input cancellation is uncertain; close without replay')
                self.vm.close()
                raise
        return deepcopy(state['schedule_receipt'])
