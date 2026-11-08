"""Explicit QEMU instruction progress, separate from guest elapsed time.

Stock QMP exposes ``query-replay.icount`` with plain ``-icount``. Its value
does not include the virtual-clock advances QEMU can make while CPUs sleep;
converting it with the fixed shift would therefore invent guest elapsed time.
This module never changes a clock, executes the guest, or enables replay.
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


def machine_clock_configuration(profile, cpus):
    """Return the immutable launch contract for an explicitly selected profile."""
    if profile not in ('standard', 'instruction'):
        raise ValueError('QEMU clock profile must be standard or instruction')
    if type(cpus) is not int or not 1 <= cpus <= 8:
        raise ValueError('QEMU clock profile requires 1..8 machine CPUs')
    if profile == 'instruction' and cpus != 1:
        raise ValueError('QEMU instruction clock profile requires exactly one machine CPU')
    instruction = profile == 'instruction'
    return dict(profile=profile, vcpus=cpus,
                tcg_thread='single' if instruction else 'multi',
                shift=7 if instruction else None,
                sleep=False if instruction else None,
                align=False if instruction else None,
                read_source='query-replay.icount' if instruction else None,
                virtual_ns_supported=False, guest_ms_supported=False,
                exact_instruction_budget=False, limits=list(_LIMITS))


def machine_clock_arguments(profile):
    """Select TCG and optional fixed instruction counting, without recording."""
    machine_clock_configuration(profile, 1)
    if profile == 'instruction':
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
        if profile['profile'] == 'instruction':
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
                      counter=counter, virtual_ns=None, guest_ms=None,
                      host_monotonic_ns=time.monotonic_ns())
        if project is not None:
            self._event('machine-clock-observe', result)
        return result
