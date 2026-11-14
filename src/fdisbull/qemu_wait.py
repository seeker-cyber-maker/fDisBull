"""Bounded observation waits on QEMU_CLOCK_VIRTUAL, not host elapsed time.

The retained guest_ms/slice_ms argument names denote milliseconds in this
explicit native clock domain. They do not enable DOSBox timing, fast-forward,
input consumption, completed frames or source/task lifetime claims.
"""
from copy import deepcopy
import json
import re
import time

from .qemu_clock import VIRTUAL_CLOCK_COMMANDS, MAX_CLOCK_BUDGET_NS, clock_timer_stop_is_ordinary


_MAX_EVIDENCE = 8 * 1024**2


def _address(value):
    if type(value) is str and re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)', value):
        value = int(value, 16 if value.startswith('0x') else 10)
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('QEMU wait memory requires an explicit 32-bit machine address')
    return value


def validate_qemu_wait_parameters(observations, until, *, guest_ms, slice_ms=50,
        timeout_ms=10000, fast_forward=False, max_polls=1000,
        timeout_screenshot='wait-timeout.png'):
    """Validate literals before lock admission, native reads or script effects."""
    from .debug_wait import validate_wait
    if fast_forward is not False:
        raise ValueError('QEMU waits do not support DOS fast_forward; select the explicit virtual clock')
    if not isinstance(observations, dict):
        raise ValueError('wait requires named observations')
    legacy = deepcopy(observations)
    for name, spec in observations.items():
        if isinstance(spec, dict) and spec.get('kind') == 'memory':
            if 'cs' in spec:
                raise ValueError('QEMU wait memory does not accept segmented CS addresses')
            if spec.get('space', 'physical') not in ('physical', 'virtual'):
                raise ValueError('QEMU wait memory space must be physical or virtual')
            address = _address(spec.get('address'))
            length = spec.get('length')
            if type(length) is int and address + length > 1 << 32:
                raise ValueError('QEMU wait memory extent exceeds 32-bit machine addresses')
            legacy[name].pop('space', None)
    validate_wait(legacy, until, guest_ms=guest_ms, slice_ms=slice_ms,
        timeout_ms=timeout_ms, fast_forward=False, max_polls=max_polls,
        timeout_screenshot=timeout_screenshot)


def _input_plan(session, *, guest_ms=None, slice_ms=50, now=None):
    """Use only a verified, wholly undelivered owned arm; never repair input.

    A native stop cancels its remaining suffix. Avoid choosing a clock cutoff
    already known to split a fixed plan. One requested poll tail allows callback
    lateness, without promising a universal completion bound or spending beyond
    the caller's total budget. Unexpected lateness still ends at the first stop.
    """
    state = getattr(session.vm, '_physical_input', None)
    if state is None:
        return None
    if state.get('valid') is not True:
        raise ValueError('QEMU wait refuses uncertain input ownership; explicit input recovery is required')
    schedule = state.get('schedule')
    if schedule is None or not schedule.get('bound'):
        return None
    native = schedule.get('native', {})
    if native.get('state') != 'armed' or schedule.get('applied_count', 0) != 0:
        raise ValueError('QEMU wait refuses interrupted or partial input; explicit recovery is required')
    kinds = [kind for kind in ('press', 'typing', 'click', 'retrace', 'motion') if kind in schedule]
    if len(kinds) > 1 or any(kind in ('retrace', 'motion') for kind in kinds):
        raise ValueError('QEMU wait cannot coalesce this input plan; execute or resolve it explicitly')
    kind = kinds[0] if kinds else 'batch'
    if native.get('token') != schedule.get('token') or native.get('start-ns') != schedule.get('start_ns'):
        raise ValueError('QEMU wait owned input identity differs from its verified arm')
    records = schedule.get('records')
    if (type(records) is not list or not records or state.get('pending') != records or
            native.get('event-count') != len(records)):
        raise ValueError('QEMU wait pending input differs from its complete undelivered arm')
    start = schedule.get('start_ns')
    current = native.get('virtual-ns') if now is None else now
    if kind != 'batch':
        steps = schedule[kind].get('steps')
        if (type(steps) is not list or len(steps) != len(records) or
                native.get(kind, {}).get('dispatched-count') != 0 or
                any(type(step.get('delay-ns')) is not int or step['delay-ns'] <= 0 for step in steps)):
            raise ValueError('QEMU wait requires known fixed input delays and an undelivered prefix')
        nominal_span = sum(step['delay-ns'] for step in steps)
    else:
        deadline = schedule.get('deadline_ns')
        if type(start) is not int or type(deadline) is not int or deadline <= start:
            raise ValueError('QEMU wait input batch has no valid fixed deadline')
        nominal_span = deadline - start
    if type(start) is not int or type(current) is not int or not start <= current < start + nominal_span:
        raise ValueError('QEMU wait input plan is not a current undelivered arm')
    tail = slice_ms * 1_000_000
    nominal_remaining = start + nominal_span - current
    effective = nominal_remaining + tail
    if effective > MAX_CLOCK_BUDGET_NS or guest_ms is not None and effective >= guest_ms * 1_000_000:
        raise ValueError('QEMU wait input plan plus one poll tail exceeds its total virtual budget; input is unchanged')
    return dict(token=schedule['token'], kind=kind, start_ns=start,
        nominal_span_ns=nominal_span, nominal_remaining_ns=nominal_remaining,
        requested_slice_ns=tail, poll_tail_ns=tail, effective_first_slice_ns=effective,
        first_slice_attempted=False, first_slice_result_observed=False,
        replay=False, cancel=False, release=False,
        scope='First slice coalesces the already armed fixed plan plus one requested poll tail; '
              'callback lateness may still interrupt it; no consumption, completion or replay is inferred')


def validate_qemu_wait_session(session, *, guest_ms=None, slice_ms=50):
    """Passive profile/ownership admission, also used before earlier script steps."""
    vm = session.vm
    if (not getattr(session, 'capabilities', {}).get('virtual_clock_budget') or
            vm.machine_configuration.get('clock_profile', {}).get('profile') != 'virtual' or
            vm.machine_configuration.get('cpus') != 1 or
            not VIRTUAL_CLOCK_COMMANDS <= getattr(vm, 'qmp_commands', frozenset())):
        raise ValueError('Observation waits require the explicit QEMU virtual clock profile and extension')
    if getattr(session, 'project', None) is None or session.project.db.in_transaction:
        raise ValueError('QEMU observation waits require a project outside a caller-owned transaction')
    if getattr(session, 'closed', False) or vm.qmp is None:
        raise ValueError('QEMU observation wait requires its live owned machine')
    if getattr(vm, '_active_clock_budget', None) is not None:
        raise ValueError('QEMU wait cannot nest an active native clock budget')
    process = getattr(session, '_process', None)
    if process is not None and (process.get('state') != 'active' or process.get('machine_closed')):
        raise ValueError('QEMU wait requires the selected DOS process to remain active')
    _input_plan(session, guest_ms=guest_ms, slice_ms=slice_ms)


class _Boundary(ValueError):
    pass


def _identity(session):
    return (id(session.vm), getattr(session, 'run_id', None),
            getattr(session, '_runtime_epoch', getattr(session, 'run_id', None)),
            deepcopy(getattr(session, 'metadata', {}).get('source_sha256')),
            deepcopy(getattr(session, 'version', None)))


def _virtual_context(cpu):
    state = cpu.get('address_state', {})
    if (state.get('machine_vcpus') != 1 or state.get('register_context_match') is not True or
            state.get('cpu_mode') not in ('real', 'protected', 'v86') or
            state.get('paging_mode') not in ('disabled', 'legacy-32') or
            type(state.get('a20')) is not bool):
        raise _Boundary('QEMU wait virtual memory requires an observed single-vCPU 32-bit address context')
    return {key: deepcopy(state.get(key)) for key in
            ('cpu_mode', 'paging', 'paging_mode', 'a20', 'control')}


class QemuWaitMixin:
    def wait(self, observations, until, *, guest_ms, slice_ms=50, timeout_ms=10000,
             fast_forward=False, max_polls=1000, timeout_screenshot='wait-timeout.png'):
        from .debug_wait import _integer, _matches
        validate_qemu_wait_parameters(observations, until, guest_ms=guest_ms,
            slice_ms=slice_ms, timeout_ms=timeout_ms, fast_forward=fast_forward,
            max_polls=max_polls, timeout_screenshot=timeout_screenshot)
        validate_qemu_wait_session(self, guest_ms=guest_ms, slice_ms=slice_ms)
        input_plan = _input_plan(self, guest_ms=guest_ms, slice_ms=slice_ms)
        if input_plan is not None:
            # Fresh public observation validates the native token, epoch, plan,
            # prefix and lease ledger under the operation's inherited lock.
            observed_input = self.input_schedule_observe()
            refreshed = _input_plan(self, guest_ms=guest_ms, slice_ms=slice_ms,
                                    now=observed_input['observed_ns'])
            if refreshed is None or refreshed != input_plan:
                raise ValueError('QEMU wait input arm changed before execution; explicit recovery is required')
            input_plan['observed_input'] = observed_input
        owner, seed, project = self.vm, _identity(self), self.project
        started = time.monotonic()
        result = dict(format='fdisbull-wait-result-1', complete=False, matched=False,
            outcome='incomplete', clock_domain='QEMU_CLOCK_VIRTUAL', requested_guest_ms=guest_ms,
            requested_virtual_ns=guest_ms * 1_000_000, guest_elapsed_ns=0, guest_elapsed_ms=0,
            clock_progress_complete=True,
            polls=[], runs=[], initial_observation=None, last_observation=None,
            diagnostic_frame=None, error=None,
            input_plan=input_plan,
            run=seed[1], capture_epoch=seed[2], source_sha256=seed[3], version=deepcopy(seed[4]),
            address_scope='explicit machine physical/selected-vCPU virtual addresses; no source/task lifetime claim')

        def remaining():
            bound = getattr(owner, 'operation_deadline', None)
            value = None if bound is None else int((bound - time.monotonic()) * 1000)
            if value is None or value <= 0:
                raise TimeoutError('QEMU observation wait host deadline expired')
            return min(value, 600000)

        def stable():
            remaining()
            if self.vm is not owner or _identity(self) != seed or getattr(self, 'closed', False) or owner.qmp is None:
                raise _Boundary('QEMU wait owner/source/restore epoch changed')

        evidence_bytes, virtual_context = 0, None
        has_virtual = any(spec.get('space') == 'virtual' for spec in observations.values())
        try:
            remaining()
            clock = self.clock_observe()
            result['initial_clock'] = deepcopy(clock)
            initial_ns, clock_epoch = clock['virtual_ns'], clock['epoch']
            while True:
                stable()
                if getattr(self, '_automatic_internal_pending', None) is not None or clock.get('virtual_clock', {}).get('native', {}).get('pending-stop'):
                    result['outcome'] = 'pending_stop'
                    break
                cpu = self.registers() if has_virtual or any(s['kind'] == 'register' for s in observations.values()) else None
                if has_virtual:
                    current = _virtual_context(cpu)
                    if virtual_context is None:
                        virtual_context = current
                    elif current != virtual_context:
                        raise _Boundary('QEMU wait selected virtual address context changed')
                values, captures, status = {}, {}, None
                for name, spec in observations.items():
                    stable()
                    if spec['kind'] == 'memory':
                        capture = self.memory(_address(spec['address']), length=spec['length'], space=spec.get('space', 'physical'))
                        value = capture['hex']
                        if len(bytes.fromhex(value)) != spec['length']:
                            raise _Boundary('Required memory observation is incomplete: ' + name)
                    else:
                        if spec['kind'] == 'status' and status is None:
                            status = self.status()
                        capture = cpu if spec['kind'] == 'register' else status
                        value = capture
                        try:
                            for part in spec['path'].split('.'):
                                value = value[part]
                            value = _integer(value)
                        except (KeyError, TypeError, ValueError) as error:
                            raise _Boundary('Required numeric observation is unavailable: ' + name) from error
                    values[name], captures[name] = value, capture
                after = self.clock_observe()
                stable()
                if after['epoch'] != clock_epoch or after['virtual_ns'] != clock['virtual_ns']:
                    raise _Boundary('QEMU wait clock changed across stopped observations')
                poll = dict(values=values, captures=captures, clock=after,
                            guest_elapsed_ns=result['guest_elapsed_ns'], guest_elapsed_ms=result['guest_elapsed_ms'])
                evidence_bytes += len(json.dumps(poll, allow_nan=False))
                if evidence_bytes > _MAX_EVIDENCE:
                    raise _Boundary('QEMU wait exceeds its bounded observation evidence')
                result['polls'].append(poll)
                result['last_observation'] = values
                if result['initial_observation'] is None:
                    result['initial_observation'] = deepcopy(values)
                result['last_observation_clock'] = after
                result['final_clock'] = dict(domain='QEMU_CLOCK_VIRTUAL', epoch=clock_epoch,
                    virtual_ns=after['virtual_ns'], source='stopped-observation')
                if result['guest_elapsed_ns'] > result['requested_virtual_ns']:
                    result['outcome'] = 'guest_budget'
                    break
                if _matches(until, values, result['initial_observation'], observations):
                    result.update(complete=True, matched=True, outcome='predicate')
                    break
                if result['guest_elapsed_ns'] >= result['requested_virtual_ns']:
                    result['outcome'] = 'guest_budget'
                    break
                if len(result['polls']) >= max_polls:
                    result['outcome'] = 'poll_budget'
                    break
                delta = min(slice_ms * 1_000_000, result['requested_virtual_ns'] - result['guest_elapsed_ns'])
                if input_plan is not None and not result['runs']:
                    delta = input_plan['effective_first_slice_ns']
                    input_plan['first_slice_attempted'] = True
                try:
                    run = self._clock_advance_with_hooks(delta, timeout_ms=remaining())
                except BaseException:
                    # An arrived exit/uncertain stop can prevent the timer's
                    # terminal readback. Retain earlier measured progress only.
                    result['clock_progress_complete'] = False
                    raise
                result['runs'].append(run)
                if input_plan is not None and len(result['runs']) == 1:
                    input_plan['first_slice_result_observed'] = True
                evidence_bytes += len(json.dumps(run, allow_nan=False))
                if evidence_bytes > _MAX_EVIDENCE:
                    raise _Boundary('QEMU wait exceeds its bounded execution evidence')
                budget = run.get('clock_budget', {})
                if (budget.get('epoch') != clock_epoch or budget.get('start_ns') != after['virtual_ns'] or
                        type(budget.get('stopped_ns')) is not int or budget['stopped_ns'] < budget['start_ns']):
                    raise _Boundary('QEMU wait native clock interval or epoch differs')
                result['guest_elapsed_ns'] = budget['stopped_ns'] - initial_ns
                result['guest_elapsed_ms'] = result['guest_elapsed_ns'] / 1_000_000
                result['final_clock'] = dict(domain='QEMU_CLOCK_VIRTUAL', epoch=clock_epoch,
                    virtual_ns=budget['stopped_ns'], source='native-clock-budget', native=budget['native'])
                # Preserve the exact original stop before any new observation.
                if run.get('hook_hits') or not clock_timer_stop_is_ordinary(run):
                    result['outcome'] = 'hook' if run.get('hook_hits') else run.get('outcome', 'incomplete')
                    result['stop'] = run
                    break
                delivery = run.get('input_delivery')
                if delivery is not None and (delivery.get('requires_resolution') or
                        delivery.get('state') in ('cancelled', 'failed')):
                    result.update(outcome='input_interrupted', stop=run, input_interrupted=delivery)
                    break
                if input_plan is not None and len(result['runs']) == 1 and (
                        delivery is None or delivery.get('token') != input_plan['token'] or
                        delivery.get('state') != 'dispatched'):
                    raise _Boundary('QEMU wait lacks the complete delivery of its admitted input plan')
                if budget['stopped_ns'] <= budget['start_ns']:
                    raise _Boundary('QEMU wait made no measured native virtual progress')
                clock = dict(after, virtual_ns=budget['stopped_ns'])
                clock['virtual_clock'] = dict(after.get('virtual_clock', {}), native=budget['native'])
        except _Boundary as error:
            result.update(complete=False, matched=False, outcome='incomplete',
                          error=dict(type=type(error).__name__, message=str(error)))
        except BaseException as error:
            self._wait_failure(error, result, owner)
            raise
        try:
            remaining()
            if (not result['complete'] and timeout_screenshot is not None and _identity(self) == seed
                    and result['outcome'] not in ('exited', 'guest_exit', 'guest_tsr')):
                try:
                    result['diagnostic_frame'] = self.screenshot(timeout_screenshot)
                except Exception as error:
                    result['capture_error'] = dict(type=type(error).__name__, message=str(error))
            result['host_elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
            result['last_observed_guest_ms'] = result['polls'][-1]['guest_elapsed_ms'] if result['polls'] else None
            result['guest_budget_overshoot_ms'] = max(0, result['guest_elapsed_ms'] - guest_ms)
            remaining()
            if self.project is not project or getattr(self, 'run_id', None) != seed[1]:
                raise ValueError('QEMU wait journal owner changed; original observation retained')
            self._event('wait', result)
            remaining()
            return result
        except BaseException as error:
            self._wait_failure(error, result, owner)
            raise

    def _wait_failure(self, error, result, owner):
        """Do not replace an arrived native stop or primary publication failure."""
        error.wait_result = result
        if getattr(error, 'result', None) is None:
            error.result = result
        owner._fdisbull_control_quarantine = getattr(owner, '_fdisbull_control_quarantine', None) or 'failed observation wait'
        try:
            owner.close()
        except BaseException as cleanup_error:
            error.wait_cleanup_error = type(cleanup_error).__name__
