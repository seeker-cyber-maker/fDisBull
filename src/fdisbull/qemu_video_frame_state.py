"""Bounded selected-state evidence around one retained QEMU source raster.

Completion covers the declared cooperative owner/transport bracket only. It is
not a native mutation revision, an atomic snapshot, whole-machine equality,
application drawing completion or a legacy completed guest frame.
"""
from copy import deepcopy
import hashlib
import json

from .dosbox_rpc import DebuggerError
from .dos_memory import machine_address_state
from .qemu_clock import MachineClockMixin, VIRTUAL_CLOCK_COMMANDS
from .qemu_frame_keys import validate_frame_key_state
from .qemu_video_frame import (QemuVideoFrameMixin, VIDEO_FRAME_COMMANDS,
                               validate_video_frame_parameters)


FORMAT = 'fdisbull-source-raster-state-observation-1'
INPUT_PROFILE = 'owned-empty-queue-initial-schedule-inactive-ps2-keyboard-v1'
VIDEO_FRAME_STATE_COMMANDS = VIDEO_FRAME_COMMANDS | VIRTUAL_CLOCK_COMMANDS | frozenset({
    'query-status', 'query-replay', 'human-monitor-command',
    'x-fdisbull-query-frame-keys', 'x-fdisbull-query-input',
})
MAX_RAM_RANGES = 16
MAX_RAM_RANGE_BYTES = 4096
MAX_RAM_BYTES = 16384
_REPLY_BYTES = 128 * 1024
_RECORD_BYTES = 1024 * 1024


class VideoFrameStateRefusal(ValueError):
    """An observed admission/input precondition needs an explicit caller action."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.observation_refusal = True


def _reference(value, enabled):
    return enabled and type(value) is str and value.startswith('$')


def _ordinary_range(address, length, end=0xc0000000):
    return (0 <= address and address + length <= 0xa0000
            or 0x100000 <= address and address + length <= end)


def validate_video_frame_state_parameters(*, ram_ranges, stream=None, frame_id=None,
                                         timeout_ms=1000, allow_references=False):
    """Validate every visible literal before script execution or lock admission."""
    validate_video_frame_parameters(stream=stream, frame_id=frame_id,
        timeout_ms=timeout_ms, allow_references=allow_references)
    if _reference(ram_ranges, allow_references):
        return
    if type(ram_ranges) is not list or not 1 <= len(ram_ranges) <= MAX_RAM_RANGES:
        raise ValueError('Source-state ram_ranges must contain 1..16 physical RAM ranges')
    concrete, total = [], 0
    for item in ram_ranges:
        if _reference(item, allow_references):
            continue
        if type(item) is not dict or len(item) != 2 or set(item) != {'address', 'length'}:
            raise ValueError('Source-state RAM ranges require exactly address and length')
        address, length = item['address'], item['length']
        address_ref = _reference(address, allow_references)
        length_ref = _reference(length, allow_references)
        if not address_ref and (type(address) is not int
                or not 0 <= address < 0xc0000000 or 0xa0000 <= address < 0x100000):
            raise ValueError('Source-state RAM address is outside ordinary physical PC RAM')
        if not length_ref:
            if type(length) is not int or not 1 <= length <= MAX_RAM_RANGE_BYTES:
                raise ValueError('Source-state RAM length must be an integer in 1..4096')
            total += length
        if not address_ref and not length_ref:
            if not _ordinary_range(address, length):
                raise ValueError('Source-state RAM range crosses a firmware or device aperture')
            concrete.append((address, address + length))
    if total > MAX_RAM_BYTES:
        raise ValueError('Source-state selected RAM exceeds 16384 bytes')
    ordered = sorted(concrete)
    if any(right[0] < left[1] for left, right in zip(ordered, ordered[1:])):
        raise ValueError('Source-state RAM ranges must not overlap')


def frozen_video_frame_state_parameters(*, ram_ranges, stream=None, frame_id=None,
                                       timeout_ms=1000):
    """Own bounded caller data before waiting for the shared machine lock."""
    validate_video_frame_state_parameters(ram_ranges=ram_ranges, stream=stream,
                                         frame_id=frame_id, timeout_ms=timeout_ms)
    ranges = []
    for item in list.__getitem__(ram_ranges, slice(0, MAX_RAM_RANGES + 1)):
        if type(item) is not dict or len(item) != 2:
            raise ValueError('Source-state RAM range changed during parameter admission')
        try:
            ranges.append(dict(address=dict.__getitem__(item, 'address'),
                               length=dict.__getitem__(item, 'length')))
        except KeyError as error:
            raise ValueError('Source-state RAM range changed during parameter admission') from error
    result = dict(ram_ranges=ranges, stream=stream, frame_id=frame_id, timeout_ms=timeout_ms)
    validate_video_frame_state_parameters(**result)
    return result


def _copy(value, *, limit=_RECORD_BYTES):
    try:
        raw = json.dumps(value, allow_nan=False, ensure_ascii=False,
                         sort_keys=True, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, RecursionError, UnicodeError) as error:
        raise DebuggerError('Source-state evidence is not finite JSON') from error
    if len(raw) > limit:
        raise DebuggerError('Source-state evidence exceeds its bounded record size')
    return json.loads(raw)


def _refuse(code, message):
    raise VideoFrameStateRefusal(code, message)


def _admit(context, vm, ranges):
    project = getattr(context, 'project', None)
    if project is None or project.db.in_transaction:
        _refuse('project_unavailable', 'Source-state observation requires a project outside a caller-owned transaction')
    configuration = getattr(vm, 'machine_configuration', {})
    if (type(configuration.get('cpus')) is not int or configuration['cpus'] != 1
            or configuration.get('accelerator') != 'tcg'
            or configuration.get('network') != 'none'
            or configuration.get('clock_profile', {}).get('profile') != 'virtual'
            or configuration.get('retrace_profile', {}).get('profile') != 'precise'
            or not VIDEO_FRAME_STATE_COMMANDS <= getattr(vm, 'qmp_commands', frozenset())):
        _refuse('unsupported_profile', 'Source-state observation requires the managed single-vCPU native virtual/precise PC profile and input witnesses')
    memory = configuration.get('memory_mib')
    if type(memory) is not int or not 16 <= memory <= 8192:
        _refuse('unsupported_memory_map', 'Source-state observation requires the managed PC RAM map')
    end = min(memory << 20, 0xc0000000)
    if any(not _ordinary_range(item['address'], item['length'], end) for item in ranges):
        _refuse('unsupported_ram_range', 'Selected physical RAM exceeds the configured ordinary PC RAM map')
    if getattr(vm, '_fdisbull_control_quarantine', None):
        _refuse('control_quarantined', 'Source-state observation cannot clear an existing control quarantine')
    if any(getattr(vm, field, None) is not None for field in (
            '_active_step_over', '_active_frame_fence', '_active_video_frame_fence', '_active_clock_budget')):
        _refuse('outstanding_control', 'Resolve the outstanding native control before source-state observation')
    sync = getattr(vm, '_clock_sync', None)
    if (sync is not None and sync.get('state') != 'stopped'
            or getattr(context, '_video_frame_fence_context', None) is not None):
        _refuse('outstanding_control', 'Stop clock synchronization and resolve source-frame control before observation')
    qmp, remote = getattr(vm, 'qmp', None), getattr(vm, 'gdb', None)
    if (qmp is None or getattr(qmp, 'socket', None) is None
            or remote is None or getattr(remote, 'socket', None) is None
            or not getattr(remote, 'register_description', None)
            or not getattr(remote, 'architecture', None)):
        _refuse('transport_unavailable', 'Source-state observation requires already initialized live QMP/GDB transports')
    authority = getattr(vm, 'observation_authority', None)
    if authority is None:
        _refuse('authority_unavailable', 'Source-state observation requires an admitted cooperative owner authority')
    return qmp, remote, authority


def _host_input(vm):
    """Read owned host bookkeeping without creating or reconciling input state."""
    state = getattr(vm, '_physical_input', None)
    if state is None:
        value = dict(initialized=False, session_id=None,
                     valid=not getattr(vm, '_physical_input_closed', False),
                     invalid_reason=None, sequence=0, pending=[], leases={},
                     schedule=None, schedule_receipt=None, last_delivery=None,
                     invalidated_edges=0, invalidated_leases=0)
    else:
        if (type(state) is not dict or type(state.get('pending')) is not list
                or type(state.get('leases')) is not dict or len(state['pending']) > 256
                or len(state['leases']) > 256 or type(state.get('valid')) is not bool):
            raise DebuggerError('Malformed owned host input state')
        value = {key: state.get(key) for key in (
            'session_id', 'valid', 'invalid_reason', 'sequence', 'pending', 'leases',
            'schedule', 'schedule_receipt', 'last_delivery', 'invalidated_edges', 'invalidated_leases')}
        value['initialized'] = True
    value['frame_key_owner'] = getattr(vm, '_frame_key_owner', None)
    value['physical_state'] = 'not observed'
    return _copy(value, limit=_REPLY_BYTES)


def _neutral_failure(code, message, *, initial):
    if initial:
        _refuse(code, message)
    raise DebuggerError('Input changed during source-state observation: ' + message)


def _read_input(vm, qmp, clock, lease, evidence, *, initial):
    lease.check()
    host = evidence['host'] = _host_input(vm)
    if not host['valid'] or host['pending'] or host['leases']:
        _neutral_failure('host_input_not_neutral', 'Owned host input must be valid with no pending edges or held leases', initial=initial)
    if host['schedule'] is not None or host['schedule_receipt'] is not None:
        _neutral_failure('host_schedule_not_initial', 'The initial source-state profile admits no prior or unresolved input schedule', initial=initial)
    if host['frame_key_owner'] is not None:
        _neutral_failure('host_keyboard_owner_active', 'The initial source-state profile requires an inactive frame-key owner', initial=initial)
    lease.check()
    schedule = qmp.call('x-fdisbull-query-input', max_reply_bytes=_REPLY_BYTES)
    evidence['schedule'] = _copy(schedule, limit=_REPLY_BYTES)
    lease.check()
    required = {'api-version', 'epoch', 'state', 'virtual-ns', 'event-count'}
    if (type(schedule) is not dict or not required <= schedule.keys()
            or type(schedule.get('api-version')) is not int or schedule['api-version'] != 1
            or type(schedule.get('epoch')) is not int
            or schedule['epoch'] != clock['virtual_clock']['native']['epoch']
            or type(schedule.get('virtual-ns')) is not int or schedule['virtual-ns'] != clock['virtual_ns']
            or type(schedule.get('event-count')) is not int or not 0 <= schedule['event-count'] <= 256
            or schedule.get('state') not in ('idle', 'armed', 'dispatched', 'cancelled', 'failed')):
        raise DebuggerError('Invalid native scheduled-input observation')
    if schedule['state'] != 'idle':
        _neutral_failure('native_schedule_not_initial', 'Native input is not in its initial idle state', initial=initial)
    if set(schedule) != required or schedule['event-count'] != 0:
        raise DebuggerError('Initial idle native input unexpectedly retains an owner or events')
    keyboard = qmp.call('x-fdisbull-query-frame-keys', max_reply_bytes=_REPLY_BYTES)
    evidence['keyboard'] = _copy(keyboard, limit=_REPLY_BYTES)
    lease.check()
    keyboard = validate_frame_key_state(keyboard, epoch=clock['virtual_clock']['native']['epoch'])
    if keyboard['active']:
        _neutral_failure('native_keyboard_owner_active',
                         'The initial source-state profile requires an inactive native frame-key owner',
                         initial=initial)
    if (keyboard['held'] or keyboard['foreign-held'] or keyboard['modifier-mask']
            or keyboard['fifo-count'] or keyboard['fifo-command-pointer'] != -1
            or keyboard['write-command'] != -1 or keyboard['controller-status'] & 1
            or keyboard['controller-pending'] or keyboard['throttle-deadline-ns'] != -1):
        _neutral_failure('native_keyboard_not_neutral', 'Selected native PS/2 keyboard/i8042 boundary is not neutral', initial=initial)
    if not keyboard['scan-enabled'] or keyboard['controller-mode'] & 0x10:
        _neutral_failure('unsupported_keyboard_profile', 'Selected native PS/2 keyboard delivery is disabled', initial=initial)


def _read_state(vm, qmp, remote, ranges, lease, evidence):
    lease.check()
    registers = evidence['registers'] = _copy(remote.registers(), limit=_REPLY_BYTES)
    lease.check()
    monitor = qmp.call('human-monitor-command', {'command-line': 'info registers'},
                       max_reply_bytes=_REPLY_BYTES)
    evidence['monitor'] = _copy(monitor, limit=_REPLY_BYTES)
    lease.check()
    if type(monitor) is not str or type(registers) is not dict or not registers:
        raise DebuggerError('Incomplete selected-vCPU register evidence')
    if any(value is None for value in registers.values()):
        raise DebuggerError('Selected-vCPU register evidence contains unavailable values')
    observed = machine_address_state(registers, monitor)
    observed['address_state']['machine_vcpus'] = 1
    if (observed['cpu_mode'] == 'unknown'
            or observed['address_state']['register_context_match'] is not True
            or observed['linear_pc'] is None):
        raise DebuggerError('GDB and HMP did not establish one selected-vCPU address context')
    evidence['cpu'] = dict(context='machine', architecture=remote.architecture,
                           registers=deepcopy(registers), **observed,
                           address_context='selected QEMU vCPU; physical RAM selections only')
    evidence['ram'] = []
    for item in ranges:
        lease.check()
        data = remote.memory(item['address'], item['length'], space='physical')
        selected = dict(address=item['address'], length=item['length'], space='physical',
                        data_hex=data.hex(), sha256=hashlib.sha256(data).hexdigest())
        evidence['ram'].append(selected)
        lease.check()
        if len(data) != item['length']:
            raise DebuggerError('Selected physical RAM read returned an incomplete range')


class _CapturedSource(QemuVideoFrameMixin, MachineClockMixin):
    """Internal source helpers stay on the captured VM, never a replacement."""

    def __init__(self, context, vm, lease):
        self.vm, self.project, self.run_id = vm, context.project, context.run_id
        self.context_id = getattr(context, 'context_id', 'machine')
        self.lease = lease

    def _clock_snapshot(self):
        self.lease.check()
        value = super()._clock_snapshot()
        self.lease.check()
        return value


def _attach_failure(vm, error, record, lease):
    record['complete'] = False
    record['error'] = dict(type=type(error).__name__, message=str(error))
    record['issues'].append(dict(code=getattr(error, 'code', 'observation_failed'),
                                 stage=record['stage'], message=str(error)))
    if lease is not None:
        record['authority'] = lease.receipt()
    native = getattr(error, 'observation_transport_reply', None)
    if native is not None:
        record['transport_reply'] = (dict(encoding='hex', bytes=len(native),
                                         retained_bytes=min(len(native), _REPLY_BYTES),
                                         truncated=len(native) > _REPLY_BYTES,
                                         data_hex=native[:_REPLY_BYTES].hex())
                                     if isinstance(native, bytes) else native)
    if not isinstance(error, VideoFrameStateRefusal):
        try:
            vm.close()
        except BaseException as cleanup:
            error.video_frame_state_cleanup_error = type(cleanup).__name__
    try:
        evidence = _copy(record)
    except DebuggerError as bounded:
        # A malformed or oversized received value must not hide the original
        # failure. Retain bounded actual fields, explicitly naming omissions.
        error.video_frame_state_evidence_error = str(bounded)
        evidence = {key: record[key] for key in (
            'format', 'complete', 'stage', 'error', 'issues', 'atomic',
            'native_mutation_revision', 'application_frame_complete',
            'frame_state_equivalence', 'legacy_phase_equivalence')}
        evidence['omitted_fields'] = []
        for key in ('authority', 'clocks', 'state_before', 'state_after',
                    'source', 'input', 'status_before', 'transport_reply'):
            if key not in record:
                continue
            try:
                evidence = _copy(dict(evidence, **{key: record[key]}))
            except DebuggerError:
                evidence['omitted_fields'].append(key)
    if getattr(error, 'result', None) is None:
        error.result = evidence
    else:
        error.video_frame_state_evidence = evidence


class QemuVideoFrameStateMixin:
    def video_frame_state_observe(self, *, ram_ranges, stream=None, frame_id=None, timeout_ms=1000):
        """Observe a bounded selected projection around one exact source raster."""
        options = frozen_video_frame_state_parameters(ram_ranges=ram_ranges, stream=stream,
                                                       frame_id=frame_id, timeout_ms=timeout_ms)
        ranges = options['ram_ranges']
        vm, lease = self.vm, None
        record = dict(format=FORMAT, context='machine', run=self.run_id,
            complete=False, stage='admission', issues=[], atomic=False,
            native_mutation_revision=None, application_frame_complete=None,
            frame_state_equivalence=None, legacy_phase_equivalence=None,
            selection=dict(cpu='selected-vcpu-registers-and-address-state', ram_ranges=ranges),
            scope='Cooperative owner/transport bracket of selected CPU/RAM and one retained source raster; native/external mutation and whole-machine equality are unobserved',
            source=None, clocks=dict(before=None, after=None),
            input=dict(profile=INPUT_PROFILE, before={}, after={}, mouse_state=None,
                       all_devices_neutral=None, guest_consumed=None),
            state_before={}, state_after={}, authority=None)
        try:
            qmp, remote, authority = _admit(self, vm, ranges)
            with authority.observe(self, deadline=vm.operation_deadline, ram_ranges=ranges) as lease:
                record['authority'] = lease.receipt()
                source = _CapturedSource(self, vm, lease)
                record['stage'] = 'clock-before'
                lease.check()
                status = qmp.call('query-status', max_reply_bytes=_REPLY_BYTES)
                record['status_before'] = _copy(status, limit=_REPLY_BYTES)
                lease.check()
                if (type(status) is not dict or type(status.get('running')) is not bool
                        or type(status.get('status')) is not str):
                    raise DebuggerError('Invalid stopped-state observation')
                if status['running']:
                    _refuse('machine_running', 'Pause the machine explicitly before source-state observation')
                before = record['clocks']['before'] = source._clock_snapshot()
                record['stage'] = 'input-before'
                _read_input(vm, qmp, before, lease, record['input']['before'], initial=True)
                record['stage'] = 'state-before'
                _read_state(vm, qmp, remote, ranges, lease, record['state_before'])
                record['stage'] = 'source-select'
                lease.check()
                prior = source._video_frame_read(vm, before)
                record['source'] = dict(source='qemu_completed_source_raster', before=_copy(prior),
                                        exported=None, after=None, rgb_verified=False)
                if 'frame' not in prior:
                    _refuse('no_completed_source_raster', 'No completed source raster is retained; source-state observation does not advance')
                if stream is not None and (stream != prior['token'] or frame_id != prior['frame']['frame-id']):
                    _refuse('source_identity_not_retained', 'Requested source raster is not the exact retained identity')
                record['stage'] = 'source-export'
                lease.authorize_export(prior['token'], prior['frame']['frame-id'], directory=vm.temporary.name)
                pixels, exported = source._video_frame_selected_rgb(vm, before, prior)
                record['source'].update(exported=_copy(exported), rgb_verified=True,
                    stream=prior['token'], frame_id=prior['frame']['frame-id'],
                    pixel_sha256=hashlib.sha256(pixels).hexdigest(), rgb_bytes=len(pixels))
                lease.check()
                record['stage'] = 'state-after'
                _read_state(vm, qmp, remote, ranges, lease, record['state_after'])
                record['stage'] = 'input-after'
                _read_input(vm, qmp, before, lease, record['input']['after'], initial=False)
                record['stage'] = 'source-after'
                lease.check()
                record['source']['after'] = source._video_frame_read(vm, before)
                record['stage'] = 'clock-after'
                record['clocks']['after'] = source._video_frame_stable(vm, before)
                record['stage'] = 'compare'
                lease.check()
                if record['state_before'] != record['state_after']:
                    raise DebuggerError('Selected stopped CPU/RAM changed across the source raster bracket')
                if record['input']['before'] != record['input']['after']:
                    raise DebuggerError('Input ownership or native keyboard state changed across the source raster bracket')
                if record['source']['before'] != record['source']['after']:
                    raise DebuggerError('Exact retained source raster identity changed across the bracket')
                clock_fields = ('context', 'run', 'epoch', 'session', 'native_state',
                                'clock_profile', 'counter', 'virtual_ns', 'virtual_clock')
                if any(before.get(key) != record['clocks']['after'].get(key) for key in clock_fields):
                    raise DebuggerError('Stopped native clock/profile state changed across the source raster bracket')
                record['authority'] = lease.receipt()
                record.update(complete=True, stage='complete')
                result = _copy(record)
                lease.check()
            result['authority'] = _copy(lease.receipt())
            return result
        except BaseException as error:
            _attach_failure(vm, error, record, lease)
            raise
