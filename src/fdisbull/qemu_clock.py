"""Explicit QEMU clock domains and an optional native virtual timer budget.

Stock QMP exposes ``query-replay.icount`` with plain ``-icount``. Its value
does not include the virtual-clock advances QEMU can make while CPUs sleep;
converting it with the fixed shift would therefore invent guest elapsed time.
The virtual profile requires the versioned fDisBull native QMP extension.
Its timer participates in normal execution; it never sets the clock or
enables replay. Earlier native stops remain visible to the caller.
"""
from __future__ import annotations

from copy import deepcopy
import time
import uuid

from .dosbox_rpc import DebuggerError


_LIMITS = (
    'The counter covers the whole machine, including firmware and interrupt handlers; '
    'it is not a DOS process or operating-system thread clock.',
    'QEMU instruction counting does not establish retired instructions or cycle-accurate timing.',
    'Idle timer advances are separate from instruction counting; '
    'instruction count converted with the fixed shift is not elapsed guest time.',
    'Generic guest milliseconds, QEMU virtual nanoseconds, and exact live instruction '
    'or guest-time budgets are unsupported by this observation.',
    'The host monotonic timestamp identifies the observation and is not guest time.',
)

VIRTUAL_CLOCK_COMMANDS = frozenset({
    'x-fdisbull-query-clock', 'x-fdisbull-arm-clock-budget',
    'x-fdisbull-cancel-clock-budget',
})
MAX_CLOCK_BUDGET_NS = 60_000_000_000
_VIRTUAL_LIMITS = (
    'QEMU_CLOCK_VIRTUAL covers the whole machine, including halted-CPU timer advances.',
    'Fixed icount is an execution model, not cycle-accurate physical hardware timing.',
    'A native virtual timer requests a stop; requested, fired and stopped times are distinct.',
    'Earlier debugger or process stops end the operation; there is no automatic continue.',
    'This clock does not establish a completed guest frame, audio boundary or input consumption.',
    'The host deadline is independent of virtual nanoseconds; reset and restore invalidate the epoch.',
)


def machine_clock_configuration(profile, cpus):
    """Return the immutable launch contract for an explicitly selected profile."""
    if profile not in ('standard', 'instruction', 'virtual'):
        raise ValueError('QEMU clock profile must be standard, instruction or virtual')
    if type(cpus) is not int or not 1 <= cpus <= 8:
        raise ValueError('QEMU clock profile requires 1..8 machine CPUs')
    if profile in ('instruction', 'virtual') and cpus != 1:
        raise ValueError('QEMU counted clock profiles require exactly one machine CPU')
    instruction = profile in ('instruction', 'virtual')
    virtual = profile == 'virtual'
    return dict(profile=profile, vcpus=cpus,
                tcg_thread='single' if instruction else 'multi',
                shift=7 if instruction else None,
                sleep=False if instruction else None,
                align=False if instruction else None,
                read_source='query-replay.icount' if instruction else None,
                virtual_ns_supported=virtual, guest_ms_supported=False,
                exact_instruction_budget=False,
                limits=list(_VIRTUAL_LIMITS if virtual else _LIMITS))


def machine_clock_arguments(profile):
    """Select TCG and optional fixed instruction counting, without recording."""
    machine_clock_configuration(profile, 1)
    if profile in ('instruction', 'virtual'):
        return ['-accel', 'tcg,thread=single',
                '-icount', 'shift=7,align=off,sleep=off']
    return ['-accel', 'tcg,thread=multi']


def _invalid(vm, message):
    vm.close()
    raise DebuggerError(message)


def _configuration(vm):
    configuration = getattr(vm, 'machine_configuration', {})
    stored = configuration.get('clock_profile')
    cpus = configuration.get('cpus', 1)
    # Machines created before this profile existed retain standard semantics.
    # Absence of an explicit profile never opts a machine into icount.
    if stored is None:
        return machine_clock_configuration('standard', cpus)
    try:
        if not isinstance(stored, dict):
            raise ValueError('Expected clock descriptor')
        expected = machine_clock_configuration(stored.get('profile'), cpus)
        if stored != expected:
            raise ValueError('Clock descriptor differs from the admitted profile')
    except (TypeError, ValueError):
        _invalid(vm, 'Invalid owned-machine clock profile')
    return deepcopy(stored)


def validate_clock_budget(delta_ns, timeout_ms):
    if type(delta_ns) is not int or not 1 <= delta_ns <= MAX_CLOCK_BUDGET_NS:
        raise ValueError('delta_ns must be an integer in 1..60000000000')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Clock host timeout must be 1..600000 ms')


def _native_clock(vm, value):
    """Validate an in-band receipt before trusting its clock or stop state."""
    def integer(item, maximum=(1 << 63) - 1):
        return type(item) is int and 0 <= item <= maximum

    if (not isinstance(value, dict) or type(value.get('api-version')) is not int
            or value['api-version'] != 1 or not integer(value.get('virtual-ns'))
            or type(value.get('running')) is not bool
            or value.get('status') not in ('prelaunch', 'paused', 'debug')
            or type(value.get('pending-stop')) is not bool
            or value.get('budget-supported') is not True
            or not integer(value.get('epoch'), (1 << 64) - 1) or value['epoch'] == 0
            or value.get('budget-state') not in
                ('idle', 'armed', 'fired', 'stopped', 'cancelled', 'invalidated')):
        _invalid(vm, 'Invalid native QEMU virtual clock receipt')
    if value['running'] or value['pending-stop'] or value['budget-state'] == 'invalidated':
        _invalid(vm, 'Native virtual clock is not in a stable stopped state')
    prior_epoch = getattr(vm, '_native_clock_epoch', value['epoch'])
    prior_time = getattr(vm, '_native_clock_last_ns', value['virtual-ns'])
    if value['epoch'] != prior_epoch or value['virtual-ns'] < prior_time:
        _invalid(vm, 'Native virtual clock epoch changed or time regressed')
    if value['budget-state'] != 'idle':
        token = value.get('budget-token')
        start, end = value.get('budget-start-ns'), value.get('budget-deadline-ns')
        fired, stopped = value.get('budget-fired-ns'), value.get('budget-stopped-ns')
        if (not isinstance(token, str) or not 1 <= len(token) <= 128
                or not integer(start) or not integer(end) or not start < end
                or start > value['virtual-ns']
                or fired is not None and (not integer(fired) or fired < end)
                or stopped is not None and (not integer(stopped) or stopped < start
                    or stopped > value['virtual-ns'] or fired is not None and stopped < fired)
                or value['budget-state'] in ('stopped', 'cancelled') and stopped is None):
            _invalid(vm, 'Invalid native virtual clock budget receipt')
    elif any(key in value for key in ('budget-token', 'budget-start-ns', 'budget-deadline-ns',
                                     'budget-fired-ns', 'budget-stopped-ns')):
        _invalid(vm, 'Idle native virtual clock unexpectedly retains a budget')
    vm._native_clock_epoch = value['epoch']
    vm._native_clock_last_ns = value['virtual-ns']
    return deepcopy(value)


def admit_virtual_clock(vm):
    """Refuse an incompatible executable while the newly owned VM is paused."""
    if not VIRTUAL_CLOCK_COMMANDS <= getattr(vm, 'qmp_commands', frozenset()):
        raise ValueError('QEMU virtual clock profile requires the fDisBull clock extension API 1')
    receipt = _native_clock(vm, vm.qmp.call('x-fdisbull-query-clock'))
    if receipt['budget-state'] != 'idle':
        _invalid(vm, 'New QEMU virtual clock already has a native budget')
    vm.native_clock_admission = receipt
    return receipt


class MachineClockMixin:
    """The public machine context wraps this method in ``machine_operation``."""

    def clock_observe(self):
        project = getattr(self, 'project', None)
        if project is not None and project.db.in_transaction:
            raise ValueError('Machine clock observation requires a project outside a caller-owned transaction')
        vm = self.vm
        if vm.qmp is None:
            raise DebuggerError('Machine clock observation requires a live owned QEMU machine')
        profile = _configuration(vm)
        prior = getattr(vm, '_clock_observation_state', None)
        if prior is not None and prior['profile'] != profile:
            _invalid(vm, 'Owned-machine clock profile changed within the observation epoch')
        native_state = vm.qmp.call('query-status')
        if (not isinstance(native_state, dict)
                or type(native_state.get('running')) is not bool
                or not isinstance(native_state.get('status'), str)):
            _invalid(vm, 'Invalid native state for machine clock observation')
        if native_state['running']:
            raise ValueError('Pause the machine context before observing its clock')
        vm.machine_stopped = True
        counter = dict(state='unsupported', value=None, unit='instructions',
                       source=None, native=None)
        if profile['profile'] in ('instruction', 'virtual'):
            native_counter = vm.qmp.call('query-replay')
            if (not isinstance(native_counter, dict)
                    or native_counter.get('mode') != 'none'
                    or type(native_counter.get('icount')) is not int
                    or not 0 <= native_counter['icount'] < 1 << 64):
                _invalid(vm, 'Invalid native QEMU instruction counter for the admitted profile')
            current = native_counter['icount']
            if prior is not None and current < prior['last_icount']:
                _invalid(vm, 'Native QEMU instruction counter regressed within the owned-machine epoch')
            counter.update(state='observed', value=current,
                           source='query-replay.icount', native=deepcopy(native_counter))
        native_clock = None
        if profile['profile'] == 'virtual':
            native_clock = _native_clock(vm, vm.qmp.call('x-fdisbull-query-clock'))
            if native_clock['budget-state'] in ('armed', 'fired'):
                _invalid(vm, 'An outstanding native clock budget prevents passive observation')
        if prior is None:
            prior = dict(epoch=uuid.uuid4().hex, sequence=0,
                         profile=deepcopy(profile), last_icount=None)
            vm._clock_observation_state = prior
        prior['sequence'] += 1
        prior['last_icount'] = counter['value']
        result = dict(format='fdisbull-machine-clock-1',
                      context=getattr(self, 'context_id', 'machine'),
                      run=getattr(self, 'run_id', None),
                      epoch=prior['epoch'], sequence=prior['sequence'],
                      session=dict(state='stopped', scope='all machine vCPUs'),
                      native_state=deepcopy(native_state), clock_profile=profile,
                      counter=counter,
                      virtual_ns=native_clock['virtual-ns'] if native_clock else None,
                      guest_ms=None,
                      host_monotonic_ns=time.monotonic_ns())
        if native_clock is not None:
            result.update(virtual_clock=dict(domain='QEMU_CLOCK_VIRTUAL',
                source='x-fdisbull-query-clock.virtual-ns', native=native_clock))
        if project is not None:
            self._event('machine-clock-observe', result)
        return result

    def clock_advance(self, delta_ns, *, timeout_ms=1000):
        """Continue once with a native virtual timer; preserve any earlier stop.

        The public context supplies one absolute host deadline before lock
        acquisition. An uncertain arm, execution, cleanup or persistence closes
        the owned VM. No elapsed-time estimate substitutes for a native receipt.
        """
        validate_clock_budget(delta_ns, timeout_ms)
        if self.project is not None and self.project.db.in_transaction:
            raise ValueError('Native clock execution requires a project outside a caller-owned transaction')
        vm = self.vm
        if _configuration(vm)['profile'] != 'virtual':
            raise ValueError('clock_advance requires the explicit QEMU virtual clock profile')
        self._execution_preflight('c', timeout_ms)
        self._stopped()
        before = self.clock_observe()
        if before['virtual_ns'] > (1 << 63) - 1 - delta_ns:
            raise ValueError('Native virtual clock deadline would overflow signed nanoseconds')
        token = uuid.uuid4().hex
        previous_budget = getattr(vm, '_active_clock_budget', None)
        result = None
        try:
            armed = _native_clock(vm, vm.qmp.call('x-fdisbull-arm-clock-budget',
                                                {'delta-ns': delta_ns, 'token': token}))
            if (armed['budget-state'] != 'armed' or armed.get('budget-token') != token
                    or armed.get('budget-start-ns') != before['virtual_ns']
                    or armed.get('budget-deadline-ns') != before['virtual_ns'] + delta_ns
                    or armed.get('budget-fired-ns') is not None
                    or armed.get('budget-stopped-ns') is not None):
                _invalid(vm, 'Native clock arm differs from the requested budget')
            vm._active_clock_budget = deepcopy(armed)
            # Dynamic dispatch retains DOS exit/TSR and physical input semantics.
            result = self._execute('c', timeout_ms)
            if vm.qmp is None:
                error = DebuggerError('Machine closed before its native clock budget could be observed')
                error.result = result
                raise error
            final = _native_clock(vm, vm.qmp.call('x-fdisbull-cancel-clock-budget',
                                                {'token': token}))
            if (final['budget-state'] not in ('stopped', 'cancelled')
                    or any(final.get(key) != armed.get(key) for key in
                           ('epoch', 'budget-token', 'budget-start-ns', 'budget-deadline-ns'))
                    or final['budget-stopped-ns'] != final['virtual-ns']):
                _invalid(vm, 'Native clock cleanup did not establish the owned terminal budget')
            fired = final.get('budget-fired-ns')
            stopped = final['budget-stopped-ns']
            budget = dict(format='fdisbull-clock-budget-1', token=token,
                clock_domain='QEMU_CLOCK_VIRTUAL', epoch=before['epoch'],
                requested_delta_ns=delta_ns, start_ns=armed['budget-start-ns'],
                deadline_ns=armed['budget-deadline-ns'], fired_ns=fired, stopped_ns=stopped,
                elapsed_ns=stopped - armed['budget-start-ns'],
                deadline_reached=fired is not None,
                overshoot_ns=stopped - armed['budget-deadline-ns'] if fired is not None else None,
                native=final, native_arm=armed, host_timeout_ms=timeout_ms,
                stop_attribution='Original native stop retained; timer firing may coexist with another stop cause')
            result['clock_budget'] = budget
            if self.project is not None:
                self._event('machine-clock-advance', result)
            return result
        except BaseException as error:
            # Arm may have been accepted even when its reply was lost. Closing
            # is the only safe alternative to a positively identified disarm.
            if result is not None and getattr(error, 'result', None) is None:
                error.result = result
            vm.close()
            raise
        finally:
            vm._active_clock_budget = previous_budget
