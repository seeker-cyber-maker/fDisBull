"""Cooperative, fixed-rate alignment of native virtual and host monotonic time.

Only an explicit step may execute the guest or wait on the host. Each step
freezes one target and performs at most one correction. Anchors survive helper
work and subsequent calls; neither drift nor early stops authorize a replay.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import time
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_clock import (VIRTUAL_CLOCK_COMMANDS, clock_timer_stop_is_ordinary,
                         machine_clock_configuration)


FORMAT = 'fdisbull-clock-sync-1'
_MAX_NS = (1 << 63) - 1
_MAX_DELTA_NS = 60_000_000_000
_LIMITS = (
    'A fixed 1:1 mapping relates QEMU_CLOCK_VIRTUAL to time.monotonic_ns; '
    'it does not change either clock or the native icount configuration.',
    'Each explicit step makes at most one bounded continue or one host-only wait; '
    'there is no background execution, moving-target loop or automatic replay.',
    'Python/helper work and control overhead remain in the original mapping. '
    'Residual drift is measured at the final observation, not promised zero at return.',
    'Stop cancels future corrections between calls, not an in-flight operation. '
    'Native execution retains its existing deadline and terminal-close policy.',
    'Retrace, renderer publication, audio duration, input consumption and completed '
    'guest frames remain separate evidence; no live restoration is provided.',
)


def validate_clock_sync_options(*, tolerance_ns=1_000_000,
                                max_lag_ns=250_000_000,
                                max_wait_ns=250_000_000, timeout_ms=1000):
    """Validate literal options without touching a machine or starting a clock."""
    values = dict(tolerance_ns=tolerance_ns, max_lag_ns=max_lag_ns,
                  max_wait_ns=max_wait_ns, timeout_ms=timeout_ms)
    for key, value in values.items():
        minimum = 0 if key == 'tolerance_ns' else 1
        maximum = 600000 if key == 'timeout_ms' else _MAX_DELTA_NS
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f'{key} must be an integer in {minimum}..{maximum}')
    return values


def _integer(value, maximum=_MAX_NS):
    return type(value) is int and 0 <= value <= maximum


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Host clock synchronization requires a bounded owned operation')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Host clock synchronization deadline expired')
    return remaining


def _require_project(owner):
    if owner.project is None or owner.project.db.in_transaction:
        raise ValueError('Host clock synchronization requires a project outside a caller-owned transaction')


def _prepare(owner):
    vm = owner.vm
    configuration = getattr(vm, 'machine_configuration', {})
    profile = configuration.get('clock_profile') if type(configuration) is dict else None
    if type(profile) is not dict or profile.get('profile') != 'virtual':
        if getattr(vm, '_clock_sync', None) is not None:
            vm.close()
            raise DebuggerError('Owned-machine host clock synchronization profile changed')
        raise ValueError('Host clock synchronization requires the explicit native virtual clock profile')
    expected = machine_clock_configuration('virtual', 1)
    try:
        exact = (type(configuration.get('cpus')) is int and configuration['cpus'] == 1
                 and json.dumps(profile, sort_keys=True, allow_nan=False)
                 == json.dumps(expected, sort_keys=True))
    except (TypeError, ValueError):
        exact = False
    if not exact:
        vm.close()
        raise DebuggerError('Owned-machine virtual clock configuration changed')
    if not VIRTUAL_CLOCK_COMMANDS <= getattr(vm, 'qmp_commands', frozenset()):
        if getattr(vm, '_clock_sync', None) is not None:
            vm.close()
            raise DebuggerError('Owned-machine native clock synchronization commands disappeared')
        raise ValueError('Host clock synchronization requires native clock extension API 1')
    _remaining(owner)
    return deepcopy(profile)


def _host_ns():
    value = time.monotonic_ns()
    if not _integer(value):
        raise DebuggerError('Host monotonic clock is outside signed nanoseconds')
    return value


def _sample(owner, mapping=None, *, result=None, position='before'):
    _remaining(owner)
    try:
        clock = owner._clock_snapshot()
    except BaseException:
        # A lost native read cannot be converted into a host-time estimate.
        owner.vm.close()
        raise
    if result is not None:
        result[position] = deepcopy(clock)
    host = _host_ns()  # Deliberately after the stopped native observation.
    if result is not None:
        result['host_' + position + '_ns'] = host
    native = clock.get('virtual_clock', {}).get('native', {})
    if (clock.get('run') != owner.run_id or not isinstance(owner.run_id, str) or not owner.run_id
            or not isinstance(clock.get('epoch'), str)
            or not re.fullmatch(r'[0-9a-f]{32}', clock['epoch'])
            or not _integer(clock.get('virtual_ns'))
            or not _integer(native.get('epoch'), (1 << 64) - 1) or not native['epoch']
            or not _integer(clock.get('sequence')) or not clock['sequence']
            or not _integer(clock.get('host_monotonic_ns')) or host < clock['host_monotonic_ns']):
        raise DebuggerError('Invalid stopped native/host clock sample for synchronization')
    if mapping is not None:
        if (clock['run'] != mapping['run'] or clock['epoch'] != mapping['epoch']
                or native['epoch'] != mapping['native_epoch']
                or clock['clock_profile'] != mapping['clock_profile']):
            raise DebuggerError('Host clock synchronization ownership or profile changed')
        if (host < mapping['last_host_ns'] or clock['virtual_ns'] < mapping['last_virtual_ns']
                or clock['sequence'] <= mapping['last_sequence']):
            raise DebuggerError('Host clock synchronization clock or sequence regressed')
        mapping.update(last_host_ns=host, last_virtual_ns=clock['virtual_ns'],
                       last_sequence=clock['sequence'])
    return clock, host


def _target(mapping, host):
    elapsed = host - mapping['anchors']['host_ns']
    virtual = mapping['anchors']['virtual_ns']
    if elapsed < 0 or elapsed > _MAX_NS - virtual:
        raise DebuggerError('Host clock synchronization target regressed or overflowed')
    return virtual + elapsed


def _receipt(owner, operation, mapping=None):
    return dict(format=FORMAT, context='machine', operation=operation,
        state=mapping['state'] if mapping else 'idle', token=mapping['token'] if mapping else None,
        run=mapping['run'] if mapping else owner.run_id,
        epoch=mapping['epoch'] if mapping else None,
        native_epoch=mapping['native_epoch'] if mapping else None,
        clock_domain='QEMU_CLOCK_VIRTUAL', host_clock_domain='time.monotonic_ns',
        rate=dict(virtual_ns=1, host_ns=1),
        anchors=deepcopy(mapping['anchors']) if mapping else None,
        config=deepcopy(mapping['config']) if mapping else None,
        before=None, after=None, host_before_ns=None, host_after_ns=None,
        target_ns=None, drift_before_ns=None, drift_after_ns=None, within_tolerance=None,
        action='none', outcome=None, reason=mapping.get('reason') if mapping else None,
        requested_wait_ns=0, actual_wait_ns=0, wait_deadline_host_ns=None,
        execution=None, limits=list(_LIMITS),
        host_sample_order='Host monotonic timestamp sampled after the stopped native clock observation')


def _before(result, mapping, clock, host):
    result.update(before=deepcopy(clock), host_before_ns=host)
    result['target_ns'] = _target(mapping, host)
    result['drift_before_ns'] = clock['virtual_ns'] - result['target_ns']


def _after(result, mapping, clock, host):
    result.update(after=deepcopy(clock), host_after_ns=host)
    result['drift_after_ns'] = clock['virtual_ns'] - _target(mapping, host)
    result['within_tolerance'] = abs(result['drift_after_ns']) <= mapping['config']['tolerance_ns']


def _latch(mapping, state, reason):
    if mapping is not None:
        mapping.update(state=state, reason=reason)


def _error(mapping, result, error):
    # Preserve a nested clock/DOS error's original stop before attaching the
    # larger synchronization context. Never reconstruct it by executing again.
    prior = getattr(error, 'result', None)
    if prior is not None and prior is not result:
        if result['execution'] is None:
            result['execution'] = deepcopy(prior)
        elif prior != result['execution']:
            result['error_evidence'] = deepcopy(prior)
    state = 'invalidated' if isinstance(error, DebuggerError) else 'interrupted'
    _latch(mapping, state, str(error))
    result.update(state=mapping['state'] if mapping else state,
                  outcome='error', reason=str(error))
    if mapping is not None:
        mapping['last_receipt'] = deepcopy(result)
    error.result = result


def _persist(owner, mapping, result):
    result['state'] = mapping['state'] if mapping else 'idle'
    result['reason'] = mapping.get('reason') if mapping else None
    _remaining(owner)
    owner._event('machine-clock-sync-' + result['operation'], result)
    _remaining(owner)
    if mapping is not None:
        mapping['last_receipt'] = deepcopy(result)
    return result


def _join_execution(owner, mapping, result):
    """Join the terminal budget to the after sample, never merely order them.

    All reads share the outer machine lock. Native time cannot advance between
    the observed clock-budget stop and the final stopped sample. Keeping both
    observations on a mismatch preserves the original stop and the contradiction.
    """
    execution = result['execution']
    budget = execution.get('clock_budget', {}) if type(execution) is dict else {}
    terminal = budget.get('native', {})
    observed = result['after']['virtual_clock']['native']
    keys = ('epoch', 'virtual-ns', 'budget-state', 'budget-token', 'budget-start-ns',
            'budget-deadline-ns', 'budget-fired-ns', 'budget-stopped-ns')
    if (type(terminal) is not dict or budget.get('clock_domain') != 'QEMU_CLOCK_VIRTUAL'
            or budget.get('epoch') != mapping['epoch']
            or terminal.get('epoch') != mapping['native_epoch']
            or any(not _integer(budget.get(key)) for key in ('start_ns', 'deadline_ns', 'stopped_ns'))
            or budget['start_ns'] != result['before']['virtual_ns']
            or budget['deadline_ns'] != result['target_ns']
            or budget['stopped_ns'] != result['after']['virtual_ns']
            or budget.get('token') != terminal.get('budget-token')
            or any(terminal.get(key) != observed.get(key) for key in keys)):
        owner.vm.close()
        raise DebuggerError('Native stopped clock sample differs from the owned synchronization budget')


class QemuClockSyncMixin:
    def _clock_sync_outer_expired(self, result, error):
        """Latch a final wrapper expiry after the module's last deadline read."""
        mapping = getattr(self.vm, '_clock_sync', None)
        if (mapping is not None and type(result) is dict and result.get('format') == FORMAT
                and result.get('token') == mapping['token']):
            _error(mapping, result, error)

    def clock_sync_start(self, *, tolerance_ns=1_000_000, max_lag_ns=250_000_000,
                         max_wait_ns=250_000_000, timeout_ms=1000):
        options = validate_clock_sync_options(tolerance_ns=tolerance_ns,
            max_lag_ns=max_lag_ns, max_wait_ns=max_wait_ns, timeout_ms=timeout_ms)
        _require_project(self)
        prior = getattr(self.vm, '_clock_sync', None)
        if prior is not None and prior['state'] != 'stopped':
            raise ValueError('Stop the existing host clock synchronization mapping before starting another')
        profile = _prepare(self)
        result = _receipt(self, 'start')
        mapping = None
        try:
            clock, host = _sample(self, prior, result=result)
            mapping = dict(state='active', reason=None, token=uuid.uuid4().hex,
                run=self.run_id, epoch=clock['epoch'], native_epoch=clock['virtual_clock']['native']['epoch'],
                clock_profile=profile, anchors=dict(virtual_ns=clock['virtual_ns'], host_ns=host),
                config={key: options[key] for key in ('tolerance_ns', 'max_lag_ns', 'max_wait_ns')},
                last_host_ns=host, last_virtual_ns=clock['virtual_ns'], last_sequence=clock['sequence'])
            # Publish ownership before persistence: a failed journal cannot
            # silently permit new anchors on the next start attempt.
            self.vm._clock_sync = mapping
            result = _receipt(self, 'start', mapping)
            _before(result, mapping, clock, host)
            _after(result, mapping, clock, host)
            result['outcome'] = 'started'
            return _persist(self, mapping, result)
        except BaseException as error:
            _error(mapping, result, error)
            raise

    def clock_sync_observe(self, *, timeout_ms=1000):
        validate_clock_sync_options(timeout_ms=timeout_ms)
        _require_project(self)
        mapping = getattr(self.vm, '_clock_sync', None)
        if mapping is None:
            raise ValueError('Start a host clock synchronization mapping before observing it')
        result = _receipt(self, 'observe', mapping)
        try:
            _prepare(self)
            clock, host = _sample(self, mapping, result=result)
            _before(result, mapping, clock, host)
            _after(result, mapping, clock, host)
            result['outcome'] = 'observed'
            return _persist(self, mapping, result)
        except BaseException as error:
            _error(mapping, result, error)
            raise

    def clock_sync_step(self, *, timeout_ms=1000):
        validate_clock_sync_options(timeout_ms=timeout_ms)
        _require_project(self)
        mapping = getattr(self.vm, '_clock_sync', None)
        if mapping is None or mapping['state'] != 'active':
            raise ValueError('Host clock synchronization step requires an active mapping; stop and explicitly restart a latched mapping')
        result = _receipt(self, 'step', mapping)
        try:
            _prepare(self)
            before, host = _sample(self, mapping, result=result)
            _before(result, mapping, before, host)
            drift = result['drift_before_ns']
            options = mapping['config']
            if abs(drift) <= options['tolerance_ns']:
                result['outcome'] = 'within-tolerance'
            elif drift < 0:
                if -drift > options['max_lag_ns']:
                    _latch(mapping, 'desynchronized', 'lag-limit')
                    result['outcome'] = 'lag-limit'
                else:
                    result['action'] = 'advance'
                    _remaining(self)
                    execution = self.clock_advance(-drift, timeout_ms=timeout_ms)
                    result['execution'] = execution
                    if (not clock_timer_stop_is_ordinary(execution)
                            or execution.get('clock_budget', {}).get('deadline_reached') is not True):
                        _latch(mapping, 'interrupted', 'native-stop')
                        result['outcome'] = 'interrupted'
                    else:
                        result['outcome'] = 'advanced'
            elif drift > options['max_wait_ns']:
                _latch(mapping, 'desynchronized', 'wait-limit')
                result['outcome'] = 'wait-limit'
            else:
                wait_deadline = mapping['anchors']['host_ns'] + before['virtual_ns'] - mapping['anchors']['virtual_ns']
                if not _integer(wait_deadline):
                    raise DebuggerError('Host clock synchronization wait target overflowed')
                result.update(action='wait', requested_wait_ns=drift,
                              wait_deadline_host_ns=wait_deadline)
                wait_start = _host_ns()
                if wait_start < host:
                    raise DebuggerError('Host monotonic clock regressed before synchronization wait')
                remaining_ns = max(0, wait_deadline - wait_start)
                allowance = _remaining(self)
                # One host wait, bounded by the original request. A late or
                # short sleep is measured afterward, never corrected in a loop.
                try:
                    if remaining_ns:
                        time.sleep(min(remaining_ns / 1_000_000_000, allowance))
                finally:
                    wait_end = _host_ns()
                    if wait_end < wait_start:
                        raise DebuggerError('Host monotonic clock regressed during synchronization wait')
                    result['actual_wait_ns'] = wait_end - wait_start
                    # The after sample must follow every checked host reading,
                    # including this wait endpoint, not just the before sample.
                    mapping['last_host_ns'] = wait_end
                _remaining(self)
                result['outcome'] = 'waited'
            after, host_after = _sample(self, mapping, result=result, position='after')
            _after(result, mapping, after, host_after)
            if result['action'] != 'advance' and (after['virtual_ns'] != before['virtual_ns']
                                                  or after['counter'] != before['counter']):
                self.vm.close()
                raise DebuggerError('Native machine advanced during a host-only synchronization step')
            if result['action'] == 'advance':
                _join_execution(self, mapping, result)
            return _persist(self, mapping, result)
        except BaseException as error:
            _error(mapping, result, error)
            raise

    def clock_sync_stop(self, *, timeout_ms=1000):
        validate_clock_sync_options(timeout_ms=timeout_ms)
        _require_project(self)
        mapping = getattr(self.vm, '_clock_sync', None)
        result = _receipt(self, 'stop', mapping)
        try:
            _prepare(self)
            if mapping is None:
                result['outcome'] = 'idle'
            else:
                clock, host = _sample(self, mapping, result=result)
                _before(result, mapping, clock, host)
                _after(result, mapping, clock, host)
                _latch(mapping, 'stopped', 'caller')
                result['outcome'] = 'stopped'
            return _persist(self, mapping, result)
        except BaseException as error:
            _error(mapping, result, error)
            raise
