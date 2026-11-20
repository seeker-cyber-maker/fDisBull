"""One consumed named keyboard action on one owned native virtual clock.

A stored declaration is a plan, never a reusable live input capability. The
invocation observes readiness afresh, arms once, and observes only its declared
RAM outcome after complete native delivery. A first stop is never crossed.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import time
import uuid

from .qemu_clock import clock_timer_stop_is_ordinary
from .qemu_keyboard_press import KEYBOARD_PRESS_COMMANDS, _plan
from .qemu_scene_wait import MAX_EVIDENCE_BYTES, MAX_POLLS, _pins, _publication_identity, _scope
from .qemu_wait import _input_plan, validate_qemu_wait_session
from .runtime_scene_actions import is_action_scene, select
from .runtime_scenes import companions, store, validate_parameters as validate_selection
from .scene_values import compact_result
from .scenes import SceneError, encoded


FORMAT = 'fdisbull-scene-action-1'


def validate_parameters(scene, object, *, handle_popups=False, timeout_ms=None,
                        slice_ms=100, compact=False, guest_ms=None,
                        allow_references=False):
    reference = lambda value: allow_references and isinstance(value, str) and value.startswith('$')
    validate_selection(scene, object=object, compact=compact, allow_references=allow_references)
    if not isinstance(object, str) or not object:
        raise ValueError('A named keyboard action requires an explicit object')
    if not reference(handle_popups) and handle_popups is not False:
        raise ValueError('QEMU scene actions require handle_popups=False')
    for name, value, maximum in (('guest_ms', guest_ms, 120000),
                                  ('timeout_ms', timeout_ms, 60000),
                                  ('slice_ms', slice_ms, 1000)):
        if reference(value) or value is None and name != 'slice_ms':
            continue
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f'Scene action {name} must be an integer in 1..{maximum}')


def _budget(selected, guest_ms, timeout_ms):
    return (min(selected['guest_ms'], guest_ms) if guest_ms is not None else selected['guest_ms'],
            min(selected['timeout_ms'], timeout_ms) if timeout_ms is not None else selected['timeout_ms'])


def _fits(selected, guest_ms, slice_ms):
    press = {key: value for key, value in selected['action'].items() if key != 'kind'}
    span = sum(step['delay-ns'] for step in _plan(**press)['steps'])
    if span + slice_ms * 1_000_000 >= guest_ms * 1_000_000:
        raise ValueError('Scene action fixed press plus one poll tail must fit strictly inside its guest budget')


def preflight(session, scene, object, *, handle_popups=False, timeout_ms=None,
              slice_ms=100, compact=False, guest_ms=None, allow_references=False):
    from .qemu_scenes import _admit
    from .runtime_scenes import select as select_runtime
    validate_parameters(scene, object, handle_popups=handle_popups, timeout_ms=timeout_ms,
        slice_ms=slice_ms, compact=compact, guest_ms=guest_ms, allow_references=allow_references)
    reference = lambda value: allow_references and isinstance(value, str) and value.startswith('$')
    if not reference(scene):
        info, selected = select_runtime(session.project, scene, session.version['id'],
                                        None if reference(object) else object)
        if not is_action_scene(info['definition']):
            raise ValueError('QEMU named keyboard actions require the explicit scene-3 action profile')
        companions(session.project, info, session.version['id'])
        if selected is not None:
            budget, _ = _budget(selected, None if reference(guest_ms) else guest_ms,
                                None if reference(timeout_ms) else timeout_ms)
            _fits(selected, budget, 1 if reference(slice_ms) else slice_ms)
    _admit(session)
    validate_qemu_wait_session(session)
    if (not session.capabilities.get('virtual_keyboard_press')
            or not KEYBOARD_PRESS_COMMANDS <= session.vm.qmp_commands):
        raise ValueError('Named scene actions require the native QEMU virtual keyboard press extension')
    _clear_input(session, session.vm, initialize=False)


@contextmanager
def _admission(session, owner, seed, deadline, scene, object, options):
    from .debug_timeline import FrameTimelineSessionMixin
    gate = FrameTimelineSessionMixin._timeline_gate(session)
    wait = min(10., deadline - time.monotonic())
    if wait <= 0 or not gate.acquire(timeout=wait):
        raise TimeoutError('Scene action deadline expired waiting for its timeline gate')
    try:
        with _scope(session, owner, seed, deadline, (scene, object), options,
                    operation='scene_act') as bound:
            yield bound
    finally:
        gate.release()


def _clear_input(session, owner, *, initialize=True):
    if getattr(owner, '_frame_key_owner', None) is not None:
        raise ValueError('Scene action refuses a frame-key owner; explicit ownership resolution is required')
    state = session._input_storage() if initialize else getattr(owner, '_physical_input', None)
    if state is None:
        return None
    if (state.get('valid') is not True or state.get('pending') or state.get('leases')
            or (state.get('schedule') or {}).get('bound')):
        raise ValueError('Scene action requires valid empty physical input with no held leases or bound schedule')
    return state


def _native_input(session):
    """Validate a passive input/clock bracket without refreshing host receipts."""
    from .qemu_input_schedule import _native_schedule
    owner = session.vm
    clock = session._input_schedule_context()
    if session.vm is not owner:
        raise ValueError('Scene action input owner changed during its clock context')
    received = owner.qmp.call('x-fdisbull-query-input')
    if session.vm is not owner:
        raise ValueError('Scene action input owner changed during its passive query')
    native = _native_schedule(session, received, clock,
                              session._input_storage().get('schedule'))
    if native['state'] == 'armed':
        raise ValueError('Scene action refuses an existing native input arm')
    return clock, native


def _same_clock(before, after):
    return (before['epoch'] == after['epoch'] and before['virtual_ns'] == after['virtual_ns']
            and before.get('counter') == after.get('counter'))


def _quarantine(session, owner, error):
    owner._fdisbull_control_quarantine = (getattr(owner, '_fdisbull_control_quarantine', None)
                                         or 'uncertain named keyboard action; do not replay')
    try:
        if session.vm is owner:
            session.close()
        else:
            owner.close()
    except BaseException as cleanup:
        error.scene_act_cleanup_error = type(cleanup).__name__
        try:
            owner.close()
        except BaseException as cleanup:
            error.scene_act_owner_cleanup_error = type(cleanup).__name__


def act(session, scene, object, *, handle_popups=False, timeout_ms=None,
        slice_ms=100, compact=False, guest_ms=None):
    from .qemu_scenes import _admit, _identity, _observe
    started = time.monotonic()
    owner, seed, project = session.vm, _identity(session), session.project
    options = dict(handle_popups=handle_popups, timeout_ms=timeout_ms,
                   slice_ms=slice_ms, compact=compact, guest_ms=guest_ms)
    validate_parameters(scene, object, **options)
    deadline = min(value for value in (
        started + (60000 if timeout_ms is None else timeout_ms) / 1000,
        getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
        getattr(owner, 'operation_deadline', None),
        *(getattr(channel, 'operation_deadline', None) for channel in
          (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None))
        if value is not None)
    if time.monotonic() >= deadline:
        raise TimeoutError('Scene action host deadline expired before preflight')
    preflight(session, scene, object, **options)
    if session.vm is not owner or _identity(session) != seed:
        raise ValueError('Scene action owner/source/restore epoch changed during preflight')
    info, selected = select(project, scene, session.version['id'], object)
    guest_ms, timeout_ms = _budget(selected, guest_ms, timeout_ms)
    deadline = min(deadline, started + timeout_ms / 1000)
    pinned = _pins(info, companions(project, info, session.version['id']))
    attempt = uuid.uuid4().hex
    plan = dict(format='fdisbull-scene-action-plan-1', scene_revision=info['id'],
        manifest_sha256=info['sha256'], object_id=selected['id'],
        action_sha256=hashlib.sha256(encoded(selected['action'])).hexdigest(),
        source_identity=deepcopy(info['definition']['source_identity']),
        press=deepcopy(selected['action']), guest_ms=guest_ms, timeout_ms=timeout_ms)
    plan['sha256'] = hashlib.sha256(encoded(plan)).hexdigest()
    journal = dict(clock_domain='QEMU_CLOCK_VIRTUAL', requested_guest_ms=guest_ms,
        requested_virtual_ns=guest_ms * 1_000_000, guest_elapsed_ns=0, guest_elapsed_ms=0,
        clock_progress_complete=True, polls=[], runs=[], stop=None, input_plan=None,
        guest_budget_overshoot_ms=0, host_elapsed_ms=0, evidence_bytes=0,
        evidence_limit_bytes=MAX_EVIDENCE_BYTES)
    result = dict(format=FORMAT, scene_revision=info['id'], manifest_sha256=info['sha256'],
        object_id=selected['id'], run=session.run_id, source_identity=deepcopy(plan['source_identity']),
        status='incomplete', complete=False, attempt_id=attempt, plan=plan,
        intention=dict(id=attempt, consumed=False, replay=False,
                       scope='one invocation; historical receipt only'), before=None,
        input=dict(attempted=False, accepted=False, completed=False,
                   device_queue_accepted=None, guest_consumed=None, arm=None, delivery=None),
        effect=dict(matched=None, phase=selected['outcome_phase'], observation=None,
                    scope='declared RAM postcondition; causal attribution unknown'), action_wait=journal)
    uncertain = False

    def remaining():
        value = int((deadline - time.monotonic()) * 1000)
        if value <= 0:
            raise TimeoutError('Scene action host deadline expired')
        return value

    def evidence():
        while True:
            size = len(encoded(result))
            if size == journal['evidence_bytes']:
                break
            journal['evidence_bytes'] = size
        if size > MAX_EVIDENCE_BYTES:
            raise ValueError('Scene action exceeds its 8 MiB persisted evidence budget')

    def stable():
        remaining()
        if session.vm is not owner or _identity(session) != seed:
            raise ValueError('Scene action owner/source/restore epoch changed')
        _admit(session)
        fresh, target = select(project, scene, session.version['id'], object)
        if (_pins(fresh, companions(project, fresh, session.version['id'])) != pinned
                or target != selected):
            raise ValueError('Scene action selected or companion manifest changed')

    def publication_stable():
        remaining()
        if (session.vm is not owner or session.project is not project
                or not _publication_identity(session, seed, journal['stop'])):
            raise ValueError('Scene action journal owner/source/restore epoch changed')
        fresh, target = select(project, scene, session.version['id'], object)
        if _pins(fresh, companions(project, fresh, session.version['id'])) != pinned or target != selected:
            raise ValueError('Scene action manifest changed before publication')

    def bound_failure(error):
        """Retain a bounded observed prefix, explicitly naming omitted evidence."""
        result.update(status='unavailable', complete=False)
        journal.update(host_elapsed_ms=round((time.monotonic() - started) * 1000, 3),
            guest_budget_overshoot_ms=max(0, journal['guest_elapsed_ms'] - guest_ms))
        if 'observation' in result:
            result['retained_observation'] = result.pop('observation')
        result['error'] = dict(type=type(error).__name__, message=str(error)[:4096])
        # A rejected oversized observation cannot silently masquerade as the
        # complete prefix. Preserve its size/hash and all earlier bounded data.
        omissions = result.setdefault('evidence_omissions', [])
        for container, key in ((result['effect'], 'observation'), (journal, 'stop'),
                                (journal, 'polls'), (journal, 'runs'), (result, 'before'),
                                (result['input'], 'arm'), (result['input'], 'delivery'),
                                (journal, 'input_plan'), (journal, 'initial_clock'),
                                (journal, 'final_clock')):
            if len(encoded(result)) <= MAX_EVIDENCE_BYTES:
                break
            value = container.get(key)
            if value is None or value == []:
                continue
            raw = encoded(value)
            omissions.append(dict(field=key, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            container[key] = [] if isinstance(value, list) else None
        if not omissions:
            result.pop('evidence_omissions')
        evidence()
        return result

    try:
        with _admission(session, owner, seed, deadline, scene, object, options) as deadline:
            if getattr(owner, '_scene_act_intention', None) is not None:
                raise ValueError('A named scene action intention is already in progress')
            owner._scene_act_intention = attempt
            result['intention']['consumed'] = True
            try:
                stable()
                state = _clear_input(session, owner)
                before_state = deepcopy(state)
                state_id = id(state)
                uncertain = True
                clock, native = _native_input(session)
                stable()
                initial_ns, epoch = clock['virtual_ns'], clock['epoch']
                journal['initial_clock'] = deepcopy(clock)
                result['before'] = _observe(session, info['id'], object=selected['id'], _publish=False)
                stable()
                before = result['before']
                uncertain = False
                if before['status'] != 'matched' or before.get('initial_outcome') is not False:
                    result['status'] = ('outcome-already-matched' if before.get('initial_outcome') is True
                                        else before['status'] if before['status'] != 'matched' else 'unavailable')
                elif (getattr(session, '_automatic_internal_pending', None) is not None
                        or clock.get('virtual_clock', {}).get('native', {}).get('pending-stop')):
                    result['status'] = 'stopped'
                else:
                    observed_clock = before.get('observation_context', {}).get('clock', {})
                    if (not before.get('capture_context_verified') or observed_clock.get('epoch') != epoch
                            or observed_clock.get('virtual_ns') != initial_ns):
                        raise ValueError('Scene action readiness lacks the owned stopped clock context')
                    current_state = _clear_input(session, owner)
                    if id(current_state) != state_id or current_state != before_state:
                        raise ValueError('Scene action physical input ownership changed during readiness')
                    final_clock, final_native = _native_input(session)
                    stable()
                    _clear_input(session, owner)
                    if (not _same_clock(clock, final_clock) or final_native != native
                            or id(session._input_storage()) != state_id
                            or session._input_storage() != before_state):
                        raise ValueError('Scene action physical input/clock authority changed before arm')
                    _fits(selected, guest_ms, slice_ms)
                    result['input'].update(attempted=True, accepted=None, completed=None)
                    uncertain = True
                    arm = session.keyboard_press(**{key: deepcopy(value) for key, value in plan['press'].items()
                                                   if key != 'kind'})
                    result['input']['arm'] = deepcopy(arm)
                    stable()
                    input_plan = _input_plan(session, guest_ms=guest_ms, slice_ms=slice_ms)
                    expected = _plan(**{key: value for key, value in plan['press'].items() if key != 'kind'})
                    armed_state = session._input_storage()
                    if (input_plan is None or input_plan['kind'] != 'press'
                            or input_plan['token'] != arm.get('token') or arm.get('state') != 'armed'
                            or arm.get('session_id') != before_state['session_id']
                            or arm.get('epoch') != epoch or arm.get('start_ns') != initial_ns
                            or id(armed_state) != state_id or armed_state.get('schedule', {}).get('press') != expected
                            or getattr(owner, '_frame_key_owner', None) is not None):
                        raise ValueError('Scene action arm differs from its immutable input/owner plan')
                    result['input'].update(accepted=True, completed=False)
                    journal['input_plan'] = input_plan
                    evidence()
                    while True:
                        stable()
                        delta = min(slice_ms * 1_000_000, journal['requested_virtual_ns'] - journal['guest_elapsed_ns'])
                        if not journal['runs']:
                            delta = input_plan['effective_first_slice_ns']
                            input_plan['first_slice_attempted'] = True
                        remaining()
                        try:
                            run = session._clock_advance_with_hooks(delta, timeout_ms=remaining())
                        except BaseException:
                            journal['clock_progress_complete'] = False
                            if result['input']['completed'] is not True:
                                result['input']['completed'] = None
                            raise
                        input_plan['first_slice_result_observed'] = True
                        journal['runs'].append(run)
                        ordinary = not run.get('hook_hits') and clock_timer_stop_is_ordinary(run)
                        if not ordinary:
                            result.update(status='stopped', complete=False)
                            journal['stop'] = run
                        budget = run.get('clock_budget', {})
                        measured = (budget.get('epoch') == epoch and budget.get('start_ns') == clock['virtual_ns']
                            and type(budget.get('stopped_ns')) is int and budget['stopped_ns'] >= budget['start_ns'])
                        if measured:
                            journal['guest_elapsed_ns'] = budget['stopped_ns'] - initial_ns
                            journal['guest_elapsed_ms'] = journal['guest_elapsed_ns'] / 1_000_000
                            journal['final_clock'] = dict(epoch=epoch, virtual_ns=budget['stopped_ns'],
                                                        source='native-clock-budget')
                        else:
                            journal['clock_progress_complete'] = False
                        delivery = run.get('input_delivery')
                        if delivery is not None:
                            result['input']['delivery'] = deepcopy(delivery)
                            if delivery.get('token') != input_plan['token']:
                                raise ValueError('Scene action native delivery belongs to another input plan')
                            completed = (delivery.get('state') == 'dispatched'
                                and delivery.get('press', {}).get('undispatched_count') == 0)
                            if result['input']['completed'] is True and not completed:
                                raise ValueError('Scene action native delivery regressed after completion')
                            result['input']['completed'] = completed
                            if (delivery.get('requires_resolution') or delivery.get('state') in ('cancelled', 'failed')
                                    or delivery.get('delivery') == 'not_dispatched'):
                                ordinary = False
                                result.update(status='stopped', complete=False)
                                journal['stop'] = run
                                journal['input_interrupted'] = True
                        elif len(journal['runs']) == 1:
                            result['input']['completed'] = None
                        evidence()
                        if not ordinary:
                            uncertain = False
                            break
                        if not measured or budget['stopped_ns'] <= budget['start_ns']:
                            raise ValueError('Scene action lacks measured forward native clock progress')
                        if result['input']['completed'] is not True:
                            raise ValueError('Scene action lacks complete native delivery of its single press')
                        clock = dict(clock, virtual_ns=budget['stopped_ns'])
                        stable()
                        observed = _observe(session, info['id'], object=selected['id'],
                                            _publish=False, _outcome_only=True)
                        journal['polls'].append(observed)
                        result['effect'].update(matched=observed.get('outcome'), observation=observed)
                        stable()
                        context = observed.get('observation_context', {}).get('clock', {})
                        if (observed['status'] not in ('matched', 'mismatch')
                                or not observed.get('capture_context_verified')
                                or context.get('epoch') != epoch or context.get('virtual_ns') != clock['virtual_ns']):
                            raise ValueError('Scene action destination observation is unavailable in its stopped clock context')
                        evidence()
                        if journal['guest_elapsed_ns'] > journal['requested_virtual_ns']:
                            result['status'] = 'timeout'
                            uncertain = False
                            break
                        if observed.get('outcome') is True:
                            result.update(status='matched', complete=True)
                            uncertain = False
                            break
                        if (journal['guest_elapsed_ns'] >= journal['requested_virtual_ns']
                                or len(journal['polls']) >= MAX_POLLS):
                            result['status'] = 'timeout'
                            uncertain = False
                            break
                publication_stable()
                journal.update(host_elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                    guest_budget_overshoot_ms=max(0, journal['guest_elapsed_ms'] - guest_ms))
                evidence()
                remaining()
                result = store(session, result)
                publication_stable()
            finally:
                if getattr(owner, '_scene_act_intention', None) == attempt:
                    del owner._scene_act_intention
    except BaseException as error:
        try:
            # A completed store or native observer may retain this very object.
            # Error shaping must not rewrite an already observed receipt.
            result = deepcopy(result)
            journal = result['action_wait']
            partial = bound_failure(error)
        except BaseException as shaping:
            error.scene_act_evidence_error = type(shaping).__name__
            partial = dict(format=FORMAT, attempt_id=attempt, status='unavailable', complete=False,
                scene_revision=info['id'], manifest_sha256=info['sha256'], object_id=selected['id'],
                intention=deepcopy(result['intention']), evidence_available=False,
                error=dict(type=type(error).__name__, message='Original exception retained; evidence could not be bounded'))
        error.scene_act_result = partial
        if getattr(error, 'result', None) is None:
            error.result = partial
        poisoned = any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
                       for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)))
        if uncertain or result['input']['attempted'] or poisoned:
            _quarantine(session, owner, error)
        raise
    if compact:
        result = compact_result(result)
    if result['status'] != 'matched' or not result['complete']:
        raise SceneError(result)
    return result
