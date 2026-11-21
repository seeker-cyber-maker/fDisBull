"""Voluntary host spatial policy, independent of native execution authority."""
from contextlib import contextmanager
import threading
import time

from .operation_budget import request_deadline
from .spatial import SpatialSessionMixin, validate_mode


_setup = threading.Lock()
_STATES = frozenset({('physical', False), ('assisted', False), ('story', False), ('physical', True)})


def initial_policy(mode=None, fair_play=False):
    mode = ('physical' if fair_play else 'assisted') if mode is None else mode
    validate_mode(mode, fair_play)
    return mode, fair_play


def _selected(state, mode=None, fair_play=None):
    current, locked = state
    mode = current if mode is None else mode
    fair_play = locked if fair_play is None else fair_play
    if locked and (not fair_play or mode != 'physical'):
        raise ValueError('Fair play cannot be disabled within this session')
    validate_mode(mode, fair_play)
    return mode, fair_play


def _reference(value):
    return isinstance(value, str) and value.startswith('$')


def validate_policy_parameters(mode=None, *, fair_play=None, allow_references=False):
    if mode is not None and not (allow_references and _reference(mode)):
        validate_mode(mode, False)
    if fair_play is not None and not (allow_references and _reference(fair_play)) and type(fair_play) is not bool:
        raise ValueError('fair_play must be Boolean or omitted')
    if (mode is not None and fair_play is not None
            and not (allow_references and (_reference(mode) or _reference(fair_play)))):
        validate_mode(mode, fair_play)


def _deadline(session):
    vm = getattr(session, 'vm', None)
    limits = [request_deadline(session, 10000), getattr(session, '_deadline', None),
              getattr(vm, 'operation_deadline', None),
              *(getattr(channel, 'operation_deadline', None) for channel in
                (getattr(vm, 'qmp', None), getattr(vm, 'gdb', None)) if channel is not None)]
    return min(value for value in limits if value is not None)


@contextmanager
def _policy_scope(session):
    deadline = _deadline(session)
    with _setup:
        if not hasattr(session, '_qemu_spatial_policy_lock'):
            session._qemu_spatial_policy_lock = threading.RLock()
        lock = session._qemu_spatial_policy_lock
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not lock.acquire(timeout=min(10, remaining)):
        raise TimeoutError('Spatial policy host deadline expired before admission')
    try:
        if time.monotonic() >= deadline:
            raise TimeoutError('Spatial policy host deadline expired before admission')
        yield deadline
    finally:
        lock.release()


def _state(session):
    return getattr(session, '_spatial_mode', 'assisted'), getattr(session, '_fair_play', False)


def _context(session):
    project, run, selected = session.project, session.run_id, session.version
    version = project.version(selected['id'])
    row = project.db.execute('SELECT version FROM debug_runs WHERE id=?', (run,)).fetchone()
    if (row is None or row['version'] != version['id'] or selected['sha256'] != version['sha256']
            or session.metadata.get('source_sha256') != project.meta['source_sha256']
            or session.metadata.get('version_sha256') != version['sha256']):
        raise ValueError('Spatial policy requires its exact project, source, version and debugger run')


def validate_policy_script(steps, *, session=None):
    """Check all known transitions, including an earlier irreversible latch.

    Unknown result values retain every possibly valid state. Fully resolved
    calls are checked again by the public method; admission performs no I/O.
    """
    selected = [step for step in steps if step['op'] == 'spatial-policy']
    if not selected:
        return
    if session is None:
        states = _STATES
    else:
        with _policy_scope(session):
            _context(session)
            states = {_state(session)}
    for step in selected:
        params = {key: value for key, value in step.items() if key not in ('op', 'as', 'expect')}
        validate_policy_parameters(**params, allow_references=True)
        mode, fair = params.get('mode'), params.get('fair_play')
        modes = (None, 'physical', 'assisted', 'story') if _reference(mode) else (mode,)
        fairs = (None, False, True) if _reference(fair) else (fair,)
        following = set()
        for state in states:
            for choice in modes:
                for locked in fairs:
                    try: following.add(_selected(state, choice, locked))
                    except ValueError: pass
        if not following:
            raise ValueError('Spatial policy script has no valid transition; fair play cannot be disabled')
        states = following


class QemuSpatialPolicyMixin:
    def spatial_policy(self, mode=None, *, fair_play=None):
        validate_policy_parameters(mode, fair_play=fair_play)
        with _policy_scope(self) as deadline:
            _context(self)
            _selected(_state(self), mode, fair_play)
            if time.monotonic() >= deadline:
                raise TimeoutError('Spatial policy host deadline expired before selection')
            # Reuse the complete existing mode/latch/event contract. The latch
            # remains set even if evidence publication or the return deadline
            # fails; a failure cannot silently weaken an accepted restriction.
            if mode is not None or fair_play is not None:
                from .qemu_session_revision import session_revision
                session_revision(self.vm).effect()
            result = SpatialSessionMixin.spatial_policy(self, mode, fair_play=fair_play)
            if time.monotonic() >= deadline:
                error = TimeoutError('Spatial policy exceeded its host deadline')
                error.result = result
                raise error
            return result
