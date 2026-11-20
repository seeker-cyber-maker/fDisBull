"""Bounded scene-2 RAM waits on one owned QEMU virtual clock.

The scene profile remains passive RAM predicates. This operation may execute
the guest to observe them later; it supplies no frame, geometry or action
authority, and never continues beyond the first nonordinary native stop.
"""
from contextlib import contextmanager
from copy import deepcopy
import time

from .operation_budget import request_deadline
from .qemu_clock import clock_timer_stop_is_ordinary
from .qemu_wait import _input_plan, validate_qemu_wait_session
from .runtime_scenes import (validate_parameters as validate_selection,
                             select, companions, observation_result, store)
from .scene_values import compact_result
from .scenes import SceneError, encoded


MAX_POLLS = 1000
MAX_EVIDENCE_BYTES = 8 * 1024**2


def validate_parameters(scene, *, object=None, guest_ms=5000, timeout_ms=5000,
                        slice_ms=100, compact=False, allow_references=False):
    validate_selection(scene, object=object, compact=compact, allow_references=allow_references)
    for name, value, maximum in (('guest_ms', guest_ms, 120000),
                                  ('timeout_ms', timeout_ms, 60000),
                                  ('slice_ms', slice_ms, 1000)):
        if allow_references and isinstance(value, str) and value.startswith('$'):
            continue
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f'Scene wait {name} must be an integer in 1..{maximum}')


def preflight(session, scene, *, object=None, guest_ms=5000, timeout_ms=5000,
              slice_ms=100, compact=False, allow_references=False):
    from .qemu_scenes import preflight as scene_preflight
    validate_parameters(scene, object=object, guest_ms=guest_ms, timeout_ms=timeout_ms,
                        slice_ms=slice_ms, compact=compact, allow_references=allow_references)
    scene_preflight(session, scene, object=object, compact=compact, allow_references=allow_references)
    reference = lambda value: allow_references and isinstance(value, str) and value.startswith('$')
    # Unknown reference values defer only their own constraints. One millisecond
    # is the smallest possible poll tail; actual resolved admission is repeated.
    validate_qemu_wait_session(session, guest_ms=None if reference(guest_ms) else guest_ms,
                               slice_ms=1 if reference(slice_ms) else slice_ms)


@contextmanager
def _scope(session, owner, seed, deadline, args, kwargs):
    from .qemu_machine import _machine_operation_guard
    from .qemu_scenes import _identity
    def bounds():
        return [deadline, getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                getattr(owner, 'operation_deadline', None),
                *(getattr(channel, 'operation_deadline', None) for channel in
                  (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None)]
    deadline = min(value for value in bounds() if value is not None)
    remaining = min(10.0, deadline - time.monotonic())
    if remaining <= 0 or not owner.lock.acquire(timeout=remaining):
        raise TimeoutError('Scene wait could not acquire its machine before the deadline')
    previous = None
    try:
        if session.vm is not owner or _identity(session) != seed:
            raise ValueError('Scene wait owner/source/restore epoch changed during admission')
        deadline = min(value for value in bounds() if value is not None)
        if time.monotonic() >= deadline:
            raise TimeoutError('Scene wait host deadline expired before admission')
        channels = [(channel, getattr(channel, 'operation_deadline', None)) for channel in
                    (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None]
        previous = (getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                    getattr(owner, 'operation_deadline', None), channels)
        session._rpc_deadline = session._deadline = owner.operation_deadline = deadline
        for channel, _ in channels:
            channel.operation_deadline = deadline
        _machine_operation_guard(owner, 'scene_wait', args, kwargs)
        yield deadline
    finally:
        if previous is not None:
            session._rpc_deadline, session._deadline, owner.operation_deadline, channels = previous
            for channel, bound in channels:
                channel.operation_deadline = bound
            for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)):
                if channel is not None and not any(channel is original for original, _ in channels):
                    channel.operation_deadline = previous[2]
        owner.lock.release()


def _pins(info, others):
    return (info['id'], info['sha256'], sorted((item['id'], item['sha256']) for item in others))


def _publication_identity(session, seed, stop):
    """Permit only a recorded DOS return's narrow lifetime transition.

    The DOS return adapter advances the capture epoch and may close the same
    machine after classifying exit/TSR. Its retained process and termination
    receipts must describe that exact current endpoint. A terminal stop alone
    cannot excuse a changed checkpoint, PSP, projection, owner or source.
    """
    from .qemu_scenes import _identity
    current = _identity(session)
    if current == seed:
        return True
    if not isinstance(stop, dict) or stop.get('outcome') not in ('guest_exit', 'guest_tsr'):
        return False
    process = stop.get('process')
    if not isinstance(process, dict) or process != getattr(session, '_process', None):
        return False
    resident = stop['outcome'] == 'guest_tsr'
    termination = process.get('termination')
    reason = stop.get('session', {}).get('stop_reason', {})
    epoch = process.get('capture_epoch')
    if (process.get('state') != ('resident' if resident else 'exited')
            or not isinstance(termination, dict) or termination.get('resident') is not resident
            or termination.get('psp_segment') != seed[-1]['psp_segment']
            or reason.get('kind') != stop['outcome'] or reason.get('guest_exit') != termination
            or not isinstance(epoch, str) or epoch == seed[4] or current[4] != epoch
            or current[-1]['epoch'] != epoch or current[-1]['process_epoch'] != epoch):
        return False
    normalized = list(current)
    normalized[4] = seed[4]
    normalized[-1] = dict(current[-1])
    for key in ('epoch', 'process_epoch', 'process_state', 'machine_closed'):
        normalized[-1][key] = seed[-1][key]
    return tuple(normalized) == seed


def wait(session, scene, *, object=None, guest_ms=5000, timeout_ms=5000,
         slice_ms=100, compact=False):
    from .qemu_scenes import _identity, _observe
    validate_parameters(scene, object=object, guest_ms=guest_ms, timeout_ms=timeout_ms,
                        slice_ms=slice_ms, compact=compact)
    started = time.monotonic()
    deadline = request_deadline(session, timeout_ms)
    owner, seed, project = session.vm, _identity(session), session.project
    preflight(session, scene, object=object, guest_ms=guest_ms, timeout_ms=timeout_ms,
              slice_ms=slice_ms, compact=compact)
    info, selected = select(project, scene, session.version['id'], object)
    pinned = _pins(info, companions(project, info, session.version['id']))
    result = observation_result(session, info, selected)
    journal = dict(format='fdisbull-scene-wait-1', clock_domain='QEMU_CLOCK_VIRTUAL',
        requested_guest_ms=guest_ms, requested_virtual_ns=guest_ms * 1_000_000,
        guest_elapsed_ns=0, guest_elapsed_ms=0, clock_progress_complete=True,
        outcome='incomplete', polls=[], runs=[], input_plan=None,
        evidence_bytes=0, evidence_limit_bytes=MAX_EVIDENCE_BYTES,
        scope='Declared scene-2 RAM predicates at stopped boundaries; no frame, action or input-consumption claim.')
    touched = False
    receipt_bytes = dict(polls=0, runs=0)

    def evidence(kind=None, value=None, *, final=False):
        if kind is not None:
            journal[kind].append(value)
            receipt_bytes[kind] += len(encoded(value))
        # Account for the exact canonical stored document, including duplicate
        # last-poll/stop fields and metadata, without reserializing the growing
        # immutable receipt lists on every iteration. The byte count includes
        # itself, so settle its short decimal representation before comparing.
        while True:
            if final:
                # Verify the actual final encoding as well; publication must
                # not rely on the incremental receipt-size assumption.
                size = len(encoded(dict(result, wait=journal)))
            else:
                without_receipts = dict(journal, polls=[], runs=[])
                size = len(encoded(dict(result, wait=without_receipts)))
                size += sum(receipt_bytes[key] + max(0, len(journal[key]) - 1)
                            for key in receipt_bytes)
            if size == journal['evidence_bytes']:
                break
            journal['evidence_bytes'] = size
        if size > MAX_EVIDENCE_BYTES:
            raise ValueError('Scene wait exceeds its 8 MiB persisted evidence budget')

    def failed(error):
        partial = dict(result, status='unavailable', complete=False, wait=dict(journal, outcome='error'))
        if 'observation' in partial:
            partial['retained_observation'] = partial.pop('observation')
        partial['wait']['error'] = dict(type=type(error).__name__, message=str(error))
        error.scene_wait_result = partial
        if getattr(error, 'result', None) is None:
            error.result = partial
        poisoned = any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
                       for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)))
        if touched or poisoned:
            owner._fdisbull_control_quarantine = (getattr(owner, '_fdisbull_control_quarantine', None)
                                                 or 'failed scene wait observation/publication')
            try:
                if session.vm is owner:
                    session.close()
                else:
                    owner.close()
            except BaseException as cleanup_error:
                error.scene_wait_cleanup_error = type(cleanup_error).__name__
                try: owner.close()
                except BaseException as owner_error:
                    error.scene_wait_owner_cleanup_error = type(owner_error).__name__

    try:
        with _scope(session, owner, seed, deadline, (scene,), dict(object=object, guest_ms=guest_ms,
                timeout_ms=timeout_ms, slice_ms=slice_ms, compact=compact)) as deadline:
            def remaining():
                value = int((deadline - time.monotonic()) * 1000)
                if value <= 0:
                    raise TimeoutError('Scene wait host deadline expired')
                return value

            def stable():
                remaining()
                if session.vm is not owner or _identity(session) != seed:
                    raise ValueError('Scene wait owner/source/restore epoch changed')
                preflight(session, scene, object=object, guest_ms=guest_ms, timeout_ms=timeout_ms,
                          slice_ms=slice_ms, compact=compact)
                fresh, _ = select(project, scene, session.version['id'], object)
                if _pins(fresh, companions(project, fresh, session.version['id'])) != pinned:
                    raise ValueError('Scene wait selected or companion manifest changed')

            stable()
            plan = _input_plan(session, guest_ms=guest_ms, slice_ms=slice_ms)
            journal['input_plan'] = plan
            if plan is not None:
                observed = session.input_schedule_observe()
                stable()
                current = _input_plan(session, guest_ms=guest_ms, slice_ms=slice_ms,
                                      now=observed['observed_ns'])
                if current != plan:
                    raise ValueError('Scene wait owned input arm changed before execution')
                plan['observed_input'] = observed
            evidence()
            clock = session.clock_observe()
            stable()
            initial_ns, clock_epoch = clock['virtual_ns'], clock['epoch']
            journal['initial_clock'] = deepcopy(clock)
            evidence()
            while True:
                stable()
                if (getattr(session, '_automatic_internal_pending', None) is not None
                        or clock.get('virtual_clock', {}).get('native', {}).get('pending-stop')):
                    result.update(status='stopped', complete=False)
                    journal['outcome'] = 'pending_stop'
                    break
                observed = _observe(session, info['id'], object=object, _publish=False)
                stable()
                context = observed.get('observation_context', {}).get('clock', {})
                result = dict(observed)
                context_matches = (context.get('epoch') == clock_epoch
                                   and context.get('virtual_ns') == clock['virtual_ns'])
                if context_matches:
                    journal['final_clock'] = dict(domain='QEMU_CLOCK_VIRTUAL', epoch=clock_epoch,
                        virtual_ns=context['virtual_ns'], source='stopped-scene-observation')
                evidence('polls', observed)
                if observed['status'] not in ('matched', 'mismatch'):
                    result['complete'] = False
                    journal['outcome'] = observed['status']
                    break
                if not context_matches or not observed.get('capture_context_verified'):
                    raise ValueError('Scene wait observation clock differs from the owned stopped interval')
                if journal['guest_elapsed_ns'] > journal['requested_virtual_ns']:
                    result.update(status='timeout', complete=False)
                    journal['outcome'] = 'guest_budget'
                    break
                if observed['status'] == 'matched':
                    journal['outcome'] = 'predicate'
                    break
                if journal['guest_elapsed_ns'] >= journal['requested_virtual_ns']:
                    result.update(status='timeout', complete=False)
                    journal['outcome'] = 'guest_budget'
                    break
                if len(journal['polls']) >= MAX_POLLS:
                    result.update(status='timeout', complete=False)
                    journal['outcome'] = 'poll_budget'
                    break
                delta = min(slice_ms * 1_000_000, journal['requested_virtual_ns'] - journal['guest_elapsed_ns'])
                if plan is not None and not journal['runs']:
                    delta = plan['effective_first_slice_ns']
                    plan['first_slice_attempted'] = True
                evidence()
                remaining()
                touched = True
                try:
                    run = session._clock_advance_with_hooks(delta, timeout_ms=remaining())
                except BaseException:
                    journal['clock_progress_complete'] = False
                    raise
                if plan is not None and not journal['runs']:
                    plan['first_slice_result_observed'] = True
                ordinary = not run.get('hook_hits') and clock_timer_stop_is_ordinary(run)
                if not ordinary:
                    result.update(status='stopped', complete=False)
                    journal.update(outcome='hook' if run.get('hook_hits') else run.get('outcome', 'incomplete'), stop=run)
                budget = run.get('clock_budget', {})
                measured = (budget.get('epoch') == clock_epoch and budget.get('start_ns') == clock['virtual_ns']
                    and type(budget.get('stopped_ns')) is int and budget['stopped_ns'] >= budget['start_ns'])
                if measured:
                    journal['guest_elapsed_ns'] = budget['stopped_ns'] - initial_ns
                    journal['guest_elapsed_ms'] = journal['guest_elapsed_ns'] / 1_000_000
                    journal['final_clock'] = dict(domain='QEMU_CLOCK_VIRTUAL', epoch=clock_epoch,
                        virtual_ns=budget['stopped_ns'], source='native-clock-budget', native=budget.get('native'))
                else:
                    journal['clock_progress_complete'] = False
                evidence('runs', run)
                if not ordinary:
                    break
                if not measured or budget['stopped_ns'] <= budget['start_ns']:
                    raise ValueError('Scene wait lacks measured forward native clock progress')
                delivery = run.get('input_delivery')
                if delivery is not None and (delivery.get('requires_resolution') or
                        delivery.get('delivery') == 'not_dispatched' or delivery.get('state') in ('cancelled', 'failed')):
                    result.update(status='stopped', complete=False)
                    journal.update(outcome='input_interrupted', stop=run, input_interrupted=delivery)
                    break
                if plan is not None and len(journal['runs']) == 1 and (
                        delivery is None or delivery.get('token') != plan['token'] or delivery.get('state') != 'dispatched'):
                    raise ValueError('Scene wait lacks complete delivery of its admitted input plan')
                clock = dict(clock, virtual_ns=budget['stopped_ns'])
                clock['virtual_clock'] = dict(clock.get('virtual_clock', {}), native=budget.get('native', {}))

            remaining()
            # Keep the original owner/source/checkpoint identity even when the
            # DOS return adapter records a new terminal process capture epoch.
            # Validation here is local; do not probe an ended native process.
            if (session.vm is not owner or session.project is not project or
                    not _publication_identity(session, seed, journal.get('stop'))):
                raise ValueError('Scene wait journal owner/source/restore epoch changed')
            journal.update(host_elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                           guest_budget_overshoot_ms=max(0, journal['guest_elapsed_ms'] - guest_ms))
            evidence(final=True)
            result['wait'] = journal
            remaining()
            result = store(session, result)
            remaining()
            if compact:
                result = compact_result(result)
    except BaseException as error:
        failed(error)
        raise
    if result['status'] != 'matched' or not result['complete']:
        raise SceneError(result)
    return result
