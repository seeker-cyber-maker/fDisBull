"""One-shot physical-input dispatch on the admitted QEMU virtual clock.

Arming never executes the guest. The next bounded continue owns the attempt;
an early stop cancels its timer and requires an explicit reschedule or cancel.
A native dispatch receipt describes PS/2 callbacks and their final sync, not
device FIFO acceptance, guest consumption, or a completed application frame.
"""
from __future__ import annotations

from copy import deepcopy
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_input import MAX_PENDING_EDGES


INPUT_SCHEDULE_COMMANDS = frozenset({
    'x-fdisbull-arm-input', 'x-fdisbull-query-input', 'x-fdisbull-cancel-input',
})
MAX_INPUT_DELAY_NS = 60_000_000_000
FORMAT = 'fdisbull-qemu-scheduled-input-1'


def validate_input_delay(delta_ns):
    if type(delta_ns) is not int or not 1 <= delta_ns <= MAX_INPUT_DELAY_NS:
        raise ValueError('Input delta_ns must be an integer in 1..60000000000')


def _invalid(owner, message):
    owner._input_invalidate(message)
    owner.vm.close()
    raise DebuggerError(message)


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
        if expected is not None or value['event-count'] or any(key in value for key in optional):
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
    if (after_stop and expected['bound'] and value['state'] == 'cancelled'
            and value['terminal-ns'] != value['virtual-ns']):
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
        return dict(format=FORMAT, context='machine', run=self.run_id,
                    session_id=self._input_storage()['session_id'], epoch=clock['epoch'],
                    token=native.get('token'), state=native['state'],
                    clock_domain='QEMU_CLOCK_VIRTUAL', observed_ns=native['virtual-ns'],
                    start_ns=native.get('start-ns'), deadline_ns=native.get('deadline-ns'),
                    terminal_ns=native.get('terminal-ns'), dispatch_ns=dispatched,
                    lateness_ns=(dispatched - native['deadline-ns'] if dispatched is not None else None),
                    reason=native.get('reason'), edge_count=native['event-count'],
                    sequences=[record['sequence'] for record in schedule['records']] if schedule else [],
                    requires_resolution=bool(schedule and schedule['bound'] and native['state'] == 'cancelled'),
                    guest_consumed=None, device_queue_accepted=None,
                    clock=deepcopy(clock), native=deepcopy(native),
                    claim='Native PS/2 callbacks and final sync only; device acceptance, guest consumption, frame completion and host-time synchronization are not established.')

    def _input_schedule_read(self, clock, *, owned_budget=None, after_stop=False):
        state = self._input_storage()
        schedule = state.get('schedule')
        try:
            native = _native_schedule(self, self.vm.qmp.call('x-fdisbull-query-input'), clock, schedule,
                                      owned_budget=owned_budget, after_stop=after_stop)
            if schedule is not None:
                self._input_schedule_accept(native, clock)
            return native
        except BaseException:
            self._input_invalidate('Native input observation failed; schedule must not be replayed')
            self.vm.close()
            raise

    def _input_schedule_accept(self, native, clock):
        state = self._input_storage()
        schedule = state['schedule']
        if schedule['bound']:
            if state['pending'] != schedule['records']:
                _invalid(self, 'Owned pending input changed beneath its native schedule')
            if native['state'] == 'dispatched':
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
            if state['pending'] != schedule['records']:
                _invalid(self, 'Owned pending input changed beneath its native schedule')
            if schedule['native']['state'] != 'armed':
                raise ValueError('Interrupted scheduled input requires explicit reschedule or cancel before another run')

    def _input_schedule_after_stop(self):
        clock = self._input_schedule_context()
        native = self._input_schedule_read(clock,
            owned_budget=getattr(self.vm, '_active_clock_budget', None), after_stop=True)
        if native['state'] not in ('dispatched', 'cancelled'):
            _invalid(self, 'Native input timer survived the owned execution stop')
        result = self._input_storage()['schedule_receipt']
        self._input_persist('input.schedule-result', result)
        return deepcopy(result)

    def input_schedule(self, delta_ns):
        """Arm the current pending batch; the caller explicitly runs the VM."""
        validate_input_delay(delta_ns)
        state = self._input_storage()
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

    def input_schedule_observe(self):
        clock = self._input_schedule_context()
        native = self._input_schedule_read(clock)
        result = self._input_schedule_receipt(native, clock, self._input_storage().get('schedule'))
        self._input_persist('input.schedule-observe', result)
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
            try:
                native = _native_schedule(self, self.vm.qmp.call('x-fdisbull-cancel-input',
                    {'token': schedule['token']}), clock, schedule)
                if native['state'] != 'cancelled' or native['terminal-ns'] != clock['virtual_ns']:
                    _invalid(self, 'Native input cancellation did not establish an undispatched terminal batch')
                self._input_schedule_accept(native, clock)
            except BaseException:
                self._input_invalidate('Native input cancellation is uncertain; close without replay')
                self.vm.close()
                raise
        return deepcopy(state['schedule_receipt'])
