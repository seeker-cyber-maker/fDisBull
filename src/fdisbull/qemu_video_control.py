"""One accepted source raster, with independent native stop attribution.

This controls the declared QEMU scanline stream. It does not change legacy
frame routes, the sampling phase, input ownership, or checkpoint semantics.

A proven exit of the original, reaped VM has no post-exit observation. Its
interrupted envelope uses null completed_source_raster, stop_consumed, frame,
source.after, clocks.after and fence.observed/released. The exact native result,
original owner, arm and last pre-exit fence observation remain explicit.
"""
from copy import deepcopy
import time
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_video_frame import _frame_valid, _integer, _remaining


VIDEO_FRAME_CONTROL_COMMANDS = frozenset({
    'x-fdisbull-arm-video-frame', 'x-fdisbull-query-video-frame-fence',
    'x-fdisbull-cancel-video-frame-fence',
})
FORMAT = 'fdisbull-video-frame-advance-1'
_FROZEN = ('token', 'stream-token', 'stream-generation', 'epoch',
           'configuration-generation', 'timing-generation',
           'baseline-frame-sequence', 'baseline-rows-sampled', 'armed-ns')
_FIELDS = frozenset(('api-version', 'model', 'state', 'released',
                     'stop-pending', 'stop-consumed', *_FROZEN))


def validate_video_frame_advance(*, timeout_ms=5000, stop_on_hook=True):
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Video frame timeout_ms must be an integer in 1..600000')
    if type(stop_on_hook) is not bool:
        raise ValueError('Video frame stop_on_hook must be boolean')


def require_no_video_frame_fence(vm, operation):
    if getattr(vm, '_active_video_frame_fence', None) is not None:
        raise ValueError('Resolve the native source-frame fence before ' + operation)


def _fail(vm, message):
    error = DebuggerError(message)
    try:
        vm.close()
    except BaseException as cleanup:
        error.video_frame_cleanup_error = type(cleanup).__name__
    raise error


def _milliseconds(vm):
    _remaining(vm)
    remaining = int((vm.operation_deadline - time.monotonic()) * 1000)
    if remaining < 1:
        raise TimeoutError('Video frame advance host deadline expired before execution')
    return remaining


def _fence(raw, context, clock, *, phase):
    """Validate stopped receipts against independently captured ownership."""
    vm, source = context['vm'], context['source']
    state = raw.get('state') if type(raw) is dict else None
    optional = ({'completed-frame', 'stop-ns'} if state == 'completed' else
                {'reason', 'stop-ns'} if state == 'aborted' else set())
    if (type(raw) is not dict or set(raw) != _FIELDS | optional
            or type(raw['api-version']) is not int or raw['api-version'] != 1
            or raw['model'] != 'qemu-video-frame-fence-v1'
            or state not in ('armed', 'completed', 'aborted', 'cancelled')
            or any(type(raw[k]) is not bool for k in ('released', 'stop-pending', 'stop-consumed'))
            or raw['stop-pending']
            or raw['token'] != context['owner']['token']
            or raw['stream-token'] != source['token']
            or any(not _integer(raw[k], positive=True, maximum=(1 << 64) - 1)
                   for k in ('stream-generation', 'epoch', 'configuration-generation', 'timing-generation'))
            or raw['stream-generation'] != source['stream-generation']
            or raw['epoch'] != source['epoch']
            or raw['epoch'] != clock['virtual_clock']['native']['epoch']
            or not _integer(raw['baseline-frame-sequence'], maximum=(1 << 64) - 2)
            or raw['baseline-frame-sequence'] != source['frame-sequence']
            or not _integer(raw['baseline-rows-sampled'], maximum=199)
            or raw['baseline-rows-sampled'] != source['rows-sampled']
            or not _integer(raw['armed-ns'])
            or raw['armed-ns'] != context['clock']['virtual_ns']
            or clock['virtual_ns'] < raw['armed-ns']):
        _fail(vm, 'Invalid native source-frame fence ownership or stopped receipt')
    previous_frame = source.get('frame')
    if previous_frame is not None and any(raw[k] != previous_frame[k]
                                         for k in ('configuration-generation', 'timing-generation')):
        _fail(vm, 'Source-frame arm changed the retained source configuration')
    armed = context.get('arm')
    if armed is not None and any(raw[k] != armed[k] for k in _FROZEN):
        _fail(vm, 'Native source-frame fence changed its frozen arm identity')
    if state in ('completed', 'aborted'):
        if (not _integer(raw['stop-ns']) or raw['stop-ns'] != clock['virtual_ns']
                or raw['stop-ns'] < raw['armed-ns']):
            _fail(vm, 'Native source-frame fence did not retain the actual stopped time')
    elif raw['stop-consumed']:
        _fail(vm, 'An incomplete source-frame fence claimed an owned stop')
    if state == 'completed':
        frame = raw['completed-frame']
        target = dict(source, **{'frame-sequence': source['frame-sequence'] + 1,
                                 'virtual-ns': clock['virtual_ns']})
        if (not _frame_valid(frame, target)
                or any(frame[k] != raw[k] for k in
                       ('stream-generation', 'epoch', 'configuration-generation', 'timing-generation'))
                or frame['completed-ns'] < raw['armed-ns']):
            _fail(vm, 'Native source-frame fence did not retain its exact complete next raster')
    elif state == 'aborted' and (type(raw['reason']) is not str
                                or not 1 <= len(raw['reason']) <= 1024):
        _fail(vm, 'Native source-frame abort lacks a bounded failure reason')
    if phase == 'arm':
        if state != 'armed' or raw['released'] or raw['stop-consumed']:
            _fail(vm, 'Native source-frame fence was not cleanly armed')
    elif phase == 'observe':
        if state == 'cancelled' or raw['released']:
            _fail(vm, 'Native source-frame fence was released by another owner')
        previous = context.get('observed')
        if previous is not None and previous['state'] != 'armed' and raw != previous:
            _fail(vm, 'Native source-frame terminal receipt changed')
    elif phase == 'release':
        previous = context['observed']
        expected = dict(previous, released=True)
        if previous['state'] == 'armed':
            expected['state'] = 'cancelled'
        if raw != expected:
            _fail(vm, 'Native source-frame release changed its terminal evidence')
    else:
        raise ValueError('Unknown source-frame receipt validation phase')
    return deepcopy(raw)


def _ordinary_stop(result, *, stop_on_hook):
    """Recognize the actual final stop without deleting earlier hook history."""
    if (type(result) is not dict or result.get('outcome') != 'stopped'
            or result.get('timed_out') is not False
            or any(key in result for key in ('native_machine_stop', 'guest_exit', 'guest_tsr'))
            or result.get('layer_conflict') or result.get('save_boundary_conflict')):
        return False
    hits = result.get('hook_hits', [])
    if type(hits) is not list or stop_on_hook and hits:
        return False
    process = result.get('process')
    if process is not None and (type(process) is not dict or process.get('state') != 'active'
                                or process.get('termination') is not None
                                or process.get('machine_closed', False) is not False):
        return False
    session = result.get('session')
    if type(session) is not dict or session.get('state') != 'stopped':
        return False
    stop = session.get('stop_reason')
    if (type(stop) is not dict or stop.get('kind') != 'stopped'
            or stop.get('breakpoint_ids') != [] or stop.get('classification_complete', True) is not True):
        return False
    reply = stop.get('native_reply')
    if type(reply) is not str or reply[:3] not in ('T02', 'S02'):
        return False
    if reply.startswith('S') and len(reply) != 3:
        return False
    fields = {item.split(':', 1)[0] for item in reply[3:].split(';') if item}
    return not fields.intersection({'watch', 'rwatch', 'awatch', 'swbreak', 'hwbreak'})


def _known_owner_exit(vm, result):
    """Use an actual exit plus reaped original process, never a failed query."""
    if type(result) is not dict or type(result.get('session')) is not dict:
        return False
    outcome, session = result.get('outcome'), result['session']
    reason = session.get('stop_reason', {})
    if outcome == 'exited':
        reply = reason.get('native_reply') if type(reason) is dict else None
        if (session.get('state') != 'exited' or reason.get('kind') != 'exited'
                or type(reply) is not str or len(reply) < 3 or reply[0] not in 'WX'
                or any(c not in '0123456789abcdefABCDEF' for c in reply[1:3])):
            return False
        # The native machine exit is already observed. Complete the existing
        # owner's cleanup without attempting another QMP frame/clock request.
        vm.close()
    elif outcome in ('guest_exit', 'guest_tsr'):
        process = result.get('process')
        if (type(process) is not dict or process.get('state') !=
                ('exited' if outcome == 'guest_exit' else 'resident')
                or type(process.get('termination')) is not dict
                or type(result.get('native_machine_stop')) is not dict):
            return False
        # A live resident/returned DOS owner remains usable. Only an already
        # closed original VM can use this unavailable-post-exit result path.
    else:
        return False
    process = getattr(vm, 'process', None)
    poll = getattr(process, 'poll', None)
    reaped = (getattr(vm, 'qmp', None) is None and getattr(vm, 'gdb', None) is None
              and callable(poll) and type(poll()) is int)
    if outcome == 'exited' and not reaped:
        raise DebuggerError('Native exit did not establish a reaped original machine owner')
    return reaped


class QemuVideoControlMixin:
    def _video_frame_control_owner(self, context):
        vm = context['vm']
        if (self.vm is not vm or getattr(self, '_video_frame_fence_context', None) is not context
                or getattr(vm, '_active_video_frame_fence', None) != context['owner']):
            _fail(vm, 'Source-frame execution owner changed')
        _remaining(vm)
        return vm

    def _video_frame_control_observe(self, context):
        vm = self._video_frame_control_owner(context)
        clock = self._clock_snapshot()
        raw = vm.qmp.call('x-fdisbull-query-video-frame-fence', {'token': context['owner']['token']})
        context['received'] = deepcopy(raw)
        receipt = _fence(raw, context, clock, phase='observe')
        self._video_frame_stable(vm, clock)
        context['observed'] = receipt
        return receipt

    def _video_frame_control_terminal(self):
        context = getattr(self, '_video_frame_fence_context', None)
        owner = getattr(self.vm, '_active_video_frame_fence', None)
        if context is None and owner is None:
            return False
        if context is None:
            _fail(self.vm, 'Source-frame execution lacks its session owner')
        return self._video_frame_control_observe(context)['state'] != 'armed'

    def video_frame_advance(self, *, timeout_ms=5000, stop_on_hook=True):
        """Run to one accepted raster, preserving every actual earlier stop."""
        from .qemu_input import require_released_machine_input
        vm = self.vm
        require_no_video_frame_fence(vm, 'another source-frame advance')
        from .qemu_step_over import require_no_step_over
        require_no_step_over(vm, 'another source-frame advance')
        if not VIDEO_FRAME_CONTROL_COMMANDS <= getattr(vm, 'qmp_commands', frozenset()):
            raise ValueError('Video frame advance requires the native source-frame fence')
        if getattr(self, '_video_frame_fence_context', None) is not None:
            _fail(vm, 'An unresolved source-frame session owner remains')
        if getattr(vm, '_active_frame_fence', None) is not None:
            raise ValueError('Resolve the renderer-frame fence before source-frame advance')
        if getattr(vm, '_active_clock_budget', None) is not None:
            raise ValueError('Resolve the clock budget before source-frame advance')
        sync = getattr(vm, '_clock_sync', None)
        if sync is not None and sync.get('state') != 'stopped':
            raise ValueError('Stop host clock synchronization before source-frame advance')
        require_released_machine_input(vm)
        if self._input_schedule_bound():
            raise ValueError('Resolve scheduled input before source-frame advance')
        before = self._video_frame_context()
        if before['virtual_clock']['native']['budget-state'] in ('armed', 'fired'):
            raise ValueError('Resolve the native clock budget before source-frame advance')
        source = self._video_frame_read(vm, before)
        if source['state'] != 'observing':
            raise ValueError('Video frame advance requires an explicitly started observing stream')
        if source['frame-sequence'] == (1 << 64) - 1:
            raise ValueError('Source-frame sequence has no space for another accepted raster')
        # Complete execution policy admission before persisting or arming.
        self._execution_preflight('c', _milliseconds(vm))
        self._video_frame_stable(vm, before)
        token = uuid.uuid4().hex
        owner = dict(kind='video-source', token=token, stream=source['token'],
                     stream_generation=source['stream-generation'], epoch=source['epoch'],
                     baseline_frame_sequence=source['frame-sequence'], run=self.run_id,
                     runtime_epoch=getattr(self, '_runtime_epoch', self.run_id),
                     clock_epoch=before['epoch'])
        context = dict(vm=vm, owner=owner, source=source, clock=before,
                       arm=None, observed=None, received=None)
        intent = dict(format=FORMAT, run=self.run_id, stream=source['token'],
                      stream_generation=source['stream-generation'],
                      baseline_frame_sequence=source['frame-sequence'], token=token,
                      stop_on_hook=stop_on_hook, source=deepcopy(source), clock=deepcopy(before))
        stage, native_result, after, source_after, released, output = 'intent', None, None, None, None, None
        try:
            self._video_frame_publish(vm, 'machine-video-frame-advance-intent', intent)
            self._video_frame_fence_context = context
            vm._active_video_frame_fence = deepcopy(owner)
            stage = 'arm'
            raw = vm.qmp.call('x-fdisbull-arm-video-frame', {
                'token': token, 'stream-token': source['token'],
                'expected-stream-generation': source['stream-generation'],
                'expected-frame-sequence': source['frame-sequence'],
                'expected-epoch': source['epoch']})
            context['received'] = deepcopy(raw)
            context['arm'] = _fence(raw, context, before, phase='arm')
            self._video_frame_control_owner(context)
            if self._video_frame_read(vm, before) != source:
                _fail(vm, 'Arming the source-frame fence changed the stopped stream')
            self._video_frame_stable(vm, before)
            stage = 'execute'
            dispatcher = getattr(self, '_run_with_hooks', None)
            native_result = (dispatcher(timeout_ms=_milliseconds(vm), stop_on_hook=stop_on_hook)
                             if dispatcher is not None else self._execute('c', _milliseconds(vm)))
            self._video_frame_control_owner(context)
            stage = 'exit-cleanup'
            if _known_owner_exit(vm, native_result):
                output = dict(format=FORMAT, context='machine', run=self.run_id,
                    outcome=native_result['outcome'], advance_completed=False,
                    completed_source_raster=None, stop_consumed=None, frame=None,
                    stream=source['token'], stream_generation=source['stream-generation'],
                    baseline_frame_sequence=source['frame-sequence'], owner=deepcopy(owner),
                    native_result=deepcopy(native_result), owner_exited=True,
                    fence=dict(arm=deepcopy(context['arm']), observed=None, released=None),
                    last_observed_fence=deepcopy(context['observed']),
                    source=dict(before=deepcopy(source), after=None),
                    clocks=dict(before=deepcopy(before), after=None),
                    unavailable='Original machine owner exited and was reaped; no post-exit frame, fence release or clock observation exists.',
                    legacy_phase_equivalence=None, application_frame_complete=None,
                    frame_state_equivalence=None)
                stage = 'publication'
                self._video_frame_publish(vm, 'machine-video-frame-advance', output)
                self._video_frame_control_owner(context)
                vm._active_video_frame_fence = None
                self._video_frame_fence_context = None
                return output
            stage = 'observe'
            self._stopped()
            observed = self._video_frame_control_observe(context)
            after = self._clock_snapshot()
            source_after = self._video_frame_read(vm, after)
            if observed['state'] == 'completed':
                if (source_after['state'] != 'observing'
                        or source_after.get('frame') != observed['completed-frame']
                        or source_after['frame-sequence'] != source['frame-sequence'] + 1):
                    _fail(vm, 'Completed source-frame fence differs from the retained raster')
            elif observed['state'] == 'aborted':
                if (source_after['state'] != 'invalidated' or 'frame' in source_after
                        or source_after.get('reason') != observed['reason']
                        or source_after['frame-sequence'] != source['frame-sequence']):
                    _fail(vm, 'Source-frame abort differs from the invalidated stream')
            elif (source_after['state'] != 'observing'
                    or source_after['frame-sequence'] != source['frame-sequence']
                    or source_after.get('frame') != source.get('frame')):
                _fail(vm, 'Incomplete source-frame fence changed the accepted raster')
            self._video_frame_stable(vm, after)
            stage = 'release'
            raw = vm.qmp.call('x-fdisbull-cancel-video-frame-fence', {'token': token})
            context['received'] = deepcopy(raw)
            released = _fence(raw, context, after, phase='release')
            if self._video_frame_read(vm, after) != source_after:
                _fail(vm, 'Source-frame release changed the retained stream')
            self._video_frame_stable(vm, after)
            self._video_frame_control_owner(context)
            accepted = observed['state'] == 'completed'
            output = dict(format=FORMAT, context='machine', run=self.run_id,
                outcome=native_result.get('outcome'),
                advance_completed=(accepted and observed['stop-consumed']
                                   and _ordinary_stop(native_result, stop_on_hook=stop_on_hook)),
                completed_source_raster=accepted, stop_consumed=observed['stop-consumed'],
                frame=deepcopy(observed.get('completed-frame')),
                stream=source['token'], stream_generation=source['stream-generation'],
                baseline_frame_sequence=source['frame-sequence'], owner=deepcopy(owner),
                native_result=deepcopy(native_result),
                fence=dict(arm=deepcopy(context['arm']), observed=deepcopy(observed), released=deepcopy(released)),
                source=dict(before=deepcopy(source), after=deepcopy(source_after)),
                clocks=dict(before=deepcopy(before), after=deepcopy(after)),
                legacy_phase_equivalence=None, application_frame_complete=None,
                frame_state_equivalence=None)
            stage = 'publication'
            self._video_frame_publish(vm, 'machine-video-frame-advance', output)
            self._video_frame_control_owner(context)
            vm._active_video_frame_fence = None
            self._video_frame_fence_context = None
            return output
        except BaseException as error:
            if native_result is None:
                native_result = getattr(error, 'result', None)
            evidence = dict(format=FORMAT, stage=stage, intent=deepcopy(intent),
                owner=deepcopy(owner),
                native_result=deepcopy(native_result), result=deepcopy(output),
                fence=dict(arm=deepcopy(context['arm']), observed=deepcopy(context['observed']),
                           received=deepcopy(context['received']), released=deepcopy(released)),
                source=dict(before=deepcopy(source), after=deepcopy(source_after)),
                clocks=dict(before=deepcopy(before), after=deepcopy(after)))
            error.video_frame_advance_evidence = evidence
            if getattr(error, 'result', None) is None:
                error.result = deepcopy(output) if output is not None else evidence
            try:
                vm.close()
            except BaseException as cleanup:
                error.video_frame_cleanup_error = type(cleanup).__name__
            raise
