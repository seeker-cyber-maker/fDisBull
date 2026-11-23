"""Legacy-shaped frame controls over the declared native source-raster fence.

The existing source controller owns execution, stop attribution and evidence.
This adapter never starts a stream, changes its sampling phase, or substitutes
a synchronous renderer publication for an accepted source raster.
"""
from copy import deepcopy
from functools import wraps
import inspect
import time

from .dosbox_rpc import DebuggerError
from .qemu_frame_contract import (FRAME_CLOCK, FRAME_SOURCE,
                                   frame_contract_metadata)
from .qemu_session_revision import session_revision
from .qemu_video_checkpoint import video_model
from .qemu_video_frame import _remaining


FORMAT = 'fdisbull-frame-timeline-1'
STEP_FORMAT = 'fdisbull-qemu-frame-step-1'
UNIT = 'accepted source raster followed by an owned safe CPU stop'


def validate_frame_step(*, timeout_ms=5000):
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Frame step timeout_ms must be an integer in 1..600000')


def validate_source_frame_advance(frames=1, timeout_ms=10000):
    if type(frames) is not int or not 1 <= frames <= 128:
        raise ValueError('frames must be an integer in 1..128')
    validate_frame_step(timeout_ms=timeout_ms)


def source_frame_advance_route(renderer_operation):
    """Keep old renderer timelines separate from an advertised source step."""
    signature = inspect.signature(renderer_operation)
    @wraps(renderer_operation)
    def invoke(self, *args, **kwargs):
        if getattr(self, 'capabilities', {}).get('frame_step'):
            # Dispatch before the renderer operation's checkpoint admission.
            # A missing/invalid source stream must refuse, never fall back.
            arguments = signature.bind(self, *args, **kwargs)
            arguments.apply_defaults()
            return self._advance_source_frames(**{key: value for key, value in arguments.arguments.items()
                                                   if key != 'self'})
        return renderer_operation(self, *args, **kwargs)
    return invoke


def _close_original(vm, error):
    try:
        vm.close()
    except BaseException as cleanup:
        error.frame_step_cleanup_error = type(cleanup).__name__


class _FrameOwner:
    def __init__(self, session):
        self.vm = session.vm
        # Bind any initial lazy debugger before retaining its original channel.
        session._stopped()
        if session.vm is not self.vm:
            error = DebuggerError('Frame step owner changed during stopped admission')
            _close_original(self.vm, error)
            raise error
        _, identity = session._frame_contract_begin()
        (self.authority, self.revision, self.lock, _, _,
         self.runtime, self.checkpoint, self.before) = identity
        self.run = session.run_id
        self.frame_profile = video_model(getattr(self.vm, 'machine_configuration', {}))
        self.process = getattr(self.vm, 'process', None)
        self.channels = tuple((name, getattr(self.vm, name),
                               getattr(getattr(self.vm, name), 'socket', None))
                              for name in ('qmp', 'gdb'))
        for name, client, channel in self.channels:
            if client is None or channel is None:
                raise DebuggerError('Frame step requires the original bound debugger channels')
            self.authority._current_client(client, name)
        self.cleanup_owner = dict(process=self.process,
            stdin=getattr(self.process, 'stdin', None), stdout=getattr(self.process, 'stdout', None),
            channels=tuple(getattr(self.vm, '_channels', ())),
            temporary=getattr(self.vm, 'temporary', None),
            qemu_image_proof=getattr(self.vm, '_qemu_image_proof', None),
            admission_guest_pidfd=getattr(self.vm, '_admission_guest_pidfd', None),
            close_observer=getattr(self.vm, 'close_observer', None), context=session,
            context_process=getattr(getattr(self.vm, 'context', None), '_process', None), closed=False)
        for name, client, channel in self.channels:
            self.cleanup_owner[name] = client
            self.cleanup_owner[name + '_socket'] = channel

    def resources_match(self):
        vm, saved = self.vm, self.cleanup_owner
        if (getattr(vm, 'observation_authority', None) is not self.authority
                or getattr(vm, 'session_revision', None) is not self.revision
                or vm.lock is not self.lock):
            return False
        for name, client, channel in self.channels:
            if (getattr(vm, name, None) is not client
                    or getattr(client, 'socket', None) is not channel):
                return False
        for attribute, key in (('process', 'process'), ('temporary', 'temporary'),
                ('_qemu_image_proof', 'qemu_image_proof'), ('close_observer', 'close_observer')):
            if getattr(vm, attribute, None) is not saved[key]:
                return False
        current = tuple(getattr(vm, '_channels', ()))
        return (len(current) == len(saved['channels'])
            and all(left is right for left, right in zip(current, saved['channels']))
            and getattr(vm, '_admission_guest_pidfd', None) == saved['admission_guest_pidfd']
            and getattr(self.process, 'stdin', None) is saved['stdin']
            and getattr(self.process, 'stdout', None) is saved['stdout'])

    def close(self, error):
        if self.resources_match():
            return _close_original(self.vm, error)
        # Replacements on the same VM object must never become cleanup targets.
        # Retain the snapshot on the existing authority so later close/error
        # handlers also keep selecting the failed original resource lifetime.
        from .qemu_machine import _close_observation_owner
        captured = getattr(self.authority, '_cleanup_owner', None)
        if captured is not None and all(captured.get(key) is self.cleanup_owner[key]
                for key in ('process', 'qmp', 'gdb', 'qmp_socket', 'gdb_socket')):
            self.cleanup_owner = captured
        self.authority._cleanup_owner = self.cleanup_owner
        self.authority.invalidate('frame step original resource changed')
        self.revision.effect()
        try:
            _close_observation_owner(self.vm, self.cleanup_owner)
        except BaseException as cleanup:
            error.frame_step_cleanup_error = type(cleanup).__name__

    def check(self, session, *, exited=False, process_terminal=False):
        vm = self.vm
        _remaining(vm)
        if (session.vm is not vm or session.run_id != self.run
                or getattr(vm, 'process', None) is not self.process
                or getattr(vm, 'observation_authority', None) is not self.authority
                or session_revision(vm) is not self.revision or vm.lock is not self.lock
                or self.revision.session_id != self.before['session_id']):
            raise DebuggerError('Frame step original owner or session lifetime changed')
        if exited:
            poll = getattr(self.process, 'poll', None)
            if (getattr(vm, 'qmp', None) is not None
                    or getattr(vm, 'gdb', None) is not None
                    or not callable(poll) or type(poll()) is not int):
                raise DebuggerError('Frame step exit lacks a reaped original owner')
        else:
            if (getattr(vm, 'closed', False)
                    or getattr(session, '_checkpoint_epoch', None) != self.checkpoint
                    or not process_terminal and getattr(session, '_runtime_epoch', None) != self.runtime):
                raise DebuggerError('Frame step owner or capture epoch changed')
            for name, client, channel in self.channels:
                if getattr(vm, name, None) is not client or client.socket is not channel:
                    raise DebuggerError('Frame step original debugger channel changed')
                self.authority._current_client(client, name)
        return self.revision.snapshot()


def _milliseconds(vm):
    _remaining(vm)
    remaining = int((vm.operation_deadline - time.monotonic()) * 1000)
    if remaining < 1:
        raise TimeoutError('Frame advancement host deadline expired before the next step')
    return remaining


class QemuFrameStepMixin:
    def frame_step(self, *, timeout_ms=5000):
        """Advance one existing source stream, retaining the actual first stop."""
        owner = _FrameOwner(self)
        try:
            advance = self.video_frame_advance(timeout_ms=_milliseconds(owner.vm), stop_on_hook=True)
        except BaseException as error:
            # The source controller retains its own failure evidence and owns
            # effectful failure cleanup. Admission refusals remain reusable.
            if self.vm is not owner.vm or not owner.resources_match():
                owner.close(error)
            raise
        result = None
        try:
            if (type(advance) is not dict or advance.get('format') != 'fdisbull-video-frame-advance-1'
                    or type(advance.get('advance_completed')) is not bool
                    or type(advance.get('native_result')) is not dict
                    or type(advance['native_result'].get('session')) is not dict):
                raise DebuggerError('Source controller returned an invalid frame-step envelope')
            native = advance['native_result']
            exited = advance.get('owner_exited') is True
            terminal = native.get('outcome') in ('guest_exit', 'guest_tsr')
            revision = owner.check(self, exited=exited, process_terminal=terminal)
            completed = advance['advance_completed']
            stop = deepcopy(native['session'].get('stop_reason'))
            if completed:
                if type(stop) is not dict:
                    raise DebuggerError('Completed source frame lacks its actual stop reason')
                stop = dict(stop, kind='frame')
            after = advance['clocks']['after']
            result = dict(format=STEP_FORMAT, run=self.run_id, **revision,
                state='exited' if exited else native['session'].get('state'),
                completed=completed, stop_reason=stop,
                registers=deepcopy(native.get('registers')), owner_exited=exited,
                source=FRAME_SOURCE, frame_profile=owner.frame_profile,
                frame_id=None, mode_id=None, frame_identity=None,
                captured_ns=None, captured_ticks=None, captured_ticks_clock=FRAME_CLOCK,
                guest_ticks=None if after is None else after['virtual_ns'] // 1_000_000,
                guest_ticks_clock=FRAME_CLOCK,
                baseline_rows_sampled=advance['fence']['arm']['baseline-rows-sampled'],
                completed_source_raster=advance['completed_source_raster'],
                stop_consumed=advance['stop_consumed'],
                boundary='accepted_source_raster_then_owned_safe_stop' if completed else None,
                atomic=False, frame_state_equivalence=None, application_frame_complete=None,
                legacy_phase_equivalence=None, native_advance=deepcopy(advance))
            if advance['frame'] is not None:
                source = advance['source']['after']
                if source is None or source.get('frame') != advance['frame'] or after is None:
                    raise DebuggerError('Frame step accepted raster differs from the retained source')
                result.update(frame_contract_metadata(self, source, after, revision))
            owner.check(self, exited=exited, process_terminal=terminal)
            return result
        except BaseException as error:
            error.frame_step_evidence = dict(native_advance=deepcopy(advance), result=deepcopy(result))
            if getattr(error, 'result', None) is None:
                error.result = error.frame_step_evidence
            owner.close(error)
            raise

    def advance_frames(self, frames=1, timeout_ms=10000):
        """Advance a bounded prefix using one original owner and outer deadline."""
        owner = _FrameOwner(self)
        completed = []
        def receipt(outcome, **fields):
            return dict(format=FORMAT, run=owner.run, outcome=outcome,
                requested_frames=frames, completed_frames=len(completed), frames=deepcopy(completed),
                unit=UNIT, source=FRAME_SOURCE, frame_profile=owner.frame_profile,
                completed_guest_frame=None, **owner.revision.snapshot(), **fields)
        try:
            for _ in range(frames):
                owner.check(self)
                step = self.frame_step(timeout_ms=_milliseconds(owner.vm))
                if step['completed']:
                    completed.append(step)
                terminal = step['native_advance']['native_result'].get('outcome') in ('guest_exit', 'guest_tsr')
                owner.check(self, exited=step['owner_exited'], process_terminal=terminal)
                if not step['completed']:
                    return receipt('interrupted', interrupted_frame=deepcopy(step),
                        stop=deepcopy(step['native_advance']['native_result']))
            return receipt('completed')
        except BaseException as error:
            failure = deepcopy(getattr(error, 'result', None))
            evidence = receipt('failed', failure=failure)
            error.frame_advance_evidence = evidence
            error.result = evidence
            if self.vm is not owner.vm or isinstance(error, (TimeoutError, DebuggerError)):
                owner.close(error)
            raise
