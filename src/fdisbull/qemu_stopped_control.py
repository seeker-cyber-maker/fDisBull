"""Explicit, one-shot native stopped-control admission for a retained raster.

This identity covers reviewed debugger control admission only. It is neither
a native machine-state revision nor an atomic device/AIO snapshot. The default
source-state observer remains the separate cooperative Python contract.
"""
from copy import deepcopy
import hashlib
import re
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_observation_authority import _channel_live, _state
from .qemu_video_frame import validate_video_frame_parameters


ARM = 'x-fdisbull-arm-stopped-control'
QUERY = 'x-fdisbull-query-stopped-control'
STOPPED_CONTROL_COMMANDS = frozenset({ARM, QUERY})
SCOPE = 'stopped-native-control-admission-v1'
FORMAT = 'fdisbull-qemu-stopped-control-1'
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
_REQUIRED = frozenset({'api-version', 'model', 'process-id', 'token',
                       'generation', 'epoch', 'state', 'busy'})
_REPLY_BYTES = 128 * 1024
_RGB_BYTES = 320 * 200 * 3


def validate_native_control_token(value, *, allow_references=False):
    if value is None or allow_references and type(value) is str and value.startswith('$'):
        return
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError('Native stopped-control token must be 32 lowercase hexadecimal characters')


def validate_stopped_control_parameters(*, timeout_ms=1000, allow_references=False):
    validate_video_frame_parameters(timeout_ms=timeout_ms, allow_references=allow_references)


def validate_stopped_control_receipt(value, *, token, epoch, process_id=None,
                                     minimum_generation=None):
    """Validate an already retained raw reply; never repair or replace identity."""
    if (type(value) is not dict or not _REQUIRED <= value.keys()
            or set(value) - _REQUIRED - {'reason'}
            or type(value.get('api-version')) is not int or value['api-version'] != 1
            or value.get('model') != 'qemu-stopped-control-v1'
            or type(value.get('process-id')) is not str
            or _UUID.fullmatch(value['process-id']) is None
            or type(value.get('token')) is not str or value['token'] != token
            or _TOKEN.fullmatch(value['token']) is None
            or type(value.get('generation')) is not int or not 0 <= value['generation'] < 1 << 64
            or type(value.get('epoch')) is not int or not 0 <= value['epoch'] < 1 << 64
            or value['epoch'] != epoch
            or type(value.get('busy')) is not bool
            or value.get('state') not in ('armed', 'retired')):
        raise DebuggerError('Invalid native stopped-control receipt')
    if ('reason' in value and (value['state'] != 'retired' or type(value['reason']) is not str
                              or not 1 <= len(value['reason']) <= 256)):
        raise DebuggerError('Invalid native stopped-control retirement reason')
    if value['state'] != 'armed' or value['busy']:
        raise DebuggerError('Native stopped-control scope is retired or busy')
    if (process_id is not None and value['process-id'] != process_id
            or minimum_generation is not None and value['generation'] < minimum_generation):
        raise DebuggerError('Native stopped-control identity changed or generation regressed')
    return value


def control_record():
    return dict(scope=SCOPE, complete=False, before=None, after=None,
        atomic=False, whole_machine_state_revision=None,
        coverage=dict(reviewed_qmp_gdb_hmp_admission=True,
                      stopped_physical_ordinary_ram_write_admission=True,
                      unsupported_control_retirement=True),
        exclusions=['device and AIO mutation', 'DMA and backing storage',
                    'whole-machine state equality', 'application frame completion'])


def _cached_rgb(vm, source=None):
    from .qemu_video_frame_state import VideoFrameStateRefusal
    native = getattr(vm, '_video_frame_last', None) if source is None else source
    pixels = getattr(vm, '_video_frame_owned_rgb', None)
    if (type(native) is not dict or type(native.get('frame')) is not dict
            or type(pixels) is not bytes or len(pixels) != _RGB_BYTES
            or hashlib.sha256(pixels).hexdigest() != native['frame'].get('pixel-sha256')):
        raise VideoFrameStateRefusal('native_control_cached_rgb_required',
            'Native stopped-control requires cached immutable RGB from a verified retained raster export')
    return pixels


class _Binding:
    def __init__(self, context, vm, lease, source, clock, token):
        self.context, self.vm, self.authority = context, vm, lease.authority
        self.identities, self.state = lease.identities, deepcopy(lease.state)
        self.cleanup_owner = lease.cleanup_owner
        self.close_callback = vm.close
        self.source, self.rgb = deepcopy(source), _cached_rgb(vm, source)
        self.token = token
        self.epoch = clock['virtual_clock']['native']['epoch']
        self.native = None
        self.last_generation = None

    def _fail(self, message):
        # Never let cleanup adopt a replacement process or transport.
        self.authority._cleanup_owner = self.cleanup_owner
        self.authority.invalidate(message)
        raise DebuggerError(message)

    def check(self, context):
        vm, authority = self.vm, self.authority
        current = (getattr(vm, 'lock', None), getattr(vm, 'process', None),
            getattr(vm, 'qmp', None), getattr(vm, 'gdb', None),
            getattr(getattr(vm, 'qmp', None), 'socket', None),
            getattr(getattr(vm, 'gdb', None), 'socket', None),
            getattr(context, 'project', None))
        if (context is not self.context or getattr(context, 'vm', None) is not vm
                or any(left is not right for left, right in zip(current, self.identities))
                or getattr(vm, 'observation_authority', None) is not authority):
            self._fail('Native stopped-control original owner or transport identity changed')
        if (authority._qmp is not vm.qmp or authority._gdb is not vm.gdb
                or authority._qmp_socket is not vm.qmp.socket
                or authority._gdb_socket is not vm.gdb.socket
                or getattr(vm.qmp, '_observation_authority', None) is not authority
                or getattr(vm.gdb, '_observation_authority', None) is not authority
                or getattr(context, '_closed', False) or getattr(vm, 'closed', False)
                or getattr(vm, '_fdisbull_control_quarantine', None)
                or vm.process.poll() is not None or not _channel_live(vm.qmp.socket)
                or not _channel_live(vm.gdb.socket) or _state(context, vm) != self.state):
            self._fail('Native stopped-control original binding or session lifetime changed')
        return self

    def cached_rgb(self, source=None):
        pixels = _cached_rgb(self.vm, source)
        native = getattr(self.vm, '_video_frame_last', None) if source is None else source
        if native != self.source or pixels != self.rgb:
            self._fail('Native stopped-control cached source identity changed')
        return pixels

    def validate(self, value):
        return validate_stopped_control_receipt(value, token=self.token, epoch=self.epoch,
            process_id=self.native['process-id'], minimum_generation=self.last_generation)

    def close_original(self):
        self.authority._cleanup_owner = self.cleanup_owner
        if getattr(self.vm, 'observation_authority', None) is self.authority:
            self.close_callback()
        else:
            # A replacement authority must never select the cleanup targets.
            from .qemu_machine import _close_observation_owner
            _close_observation_owner(self.vm, self.cleanup_owner)


def bound_stopped_control(context, token):
    """Resolve before transport access, including the outer deadline wrapper."""
    from .qemu_video_frame_state import VideoFrameStateRefusal
    binding = getattr(context, '_native_stopped_control_binding', None)
    if binding is None or binding.token != token:
        raise VideoFrameStateRefusal('native_control_scope_unavailable',
            'Requested native stopped-control scope is not armed on this original owner')
    return binding.check(context)


def preflight_stopped_control_binding(context, token):
    """Protect wrapper channel/deadline setup from adopting a replacement owner."""
    from .qemu_video_frame_state import FORMAT as OBSERVER_FORMAT, VideoFrameStateRefusal
    try:
        return bound_stopped_control(context, token)
    except VideoFrameStateRefusal:
        raise
    except BaseException as error:
        error.native_stopped_control_binding_failure = True
        binding = getattr(context, '_native_stopped_control_binding', None)
        if binding is not None:
            try:
                binding.close_original()
            except BaseException as cleanup:
                error.native_stopped_control_cleanup_error = type(cleanup).__name__
        error.result = dict(format=OBSERVER_FORMAT, complete=False, stage='original-owner-binding',
            atomic=False, native_mutation_revision=None, native_control=control_record(),
            application_frame_complete=None, frame_state_equivalence=None,
            legacy_phase_equivalence=None,
            error=dict(type=type(error).__name__, message=str(error)))
        raise


class QemuStoppedControlMixin:
    def stopped_control_arm(self, *, timeout_ms=1000):
        """Arm once, after a verified export, without advancing or exporting."""
        from .qemu_video_frame_state import (VideoFrameStateRefusal, _CapturedSource,
            _admit, _copy, _read_input, _refuse)
        validate_stopped_control_parameters(timeout_ms=timeout_ms)
        vm, lease, binding = self.vm, None, None
        record = dict(format=FORMAT, scope=SCOPE, complete=False, stage='admission',
            token=None, native=None, source=None, input={}, atomic=False,
            native_mutation_revision=None, whole_machine_state_revision=None)
        try:
            if getattr(self, '_native_stopped_control_arm_attempted', False):
                _refuse('native_control_already_armed', 'Native stopped-control scope was already armed or attempted')
            qmp, _, authority = _admit(self, vm, [])
            if not STOPPED_CONTROL_COMMANDS <= getattr(vm, 'qmp_commands', frozenset()):
                _refuse('native_control_unavailable', 'This QEMU producer has no native stopped-control scope')
            _cached_rgb(vm)
            with authority.observe(self, deadline=vm.operation_deadline) as lease:
                source = _CapturedSource(self, vm, lease)
                record['stage'] = 'stopped-preflight'
                status = record['status'] = _copy(qmp.call('query-status', max_reply_bytes=_REPLY_BYTES))
                lease.check()
                if (type(status) is not dict or type(status.get('running')) is not bool
                        or type(status.get('status')) is not str):
                    raise DebuggerError('Invalid native stopped-control stopped-state observation')
                if status['running']:
                    _refuse('machine_running', 'Pause the machine explicitly before arming native stopped-control')
                before = record['clock'] = source._clock_snapshot()
                _read_input(vm, qmp, before, lease, record['input'], initial=True)
                prior = source._video_frame_read(vm, before)
                _cached_rgb(vm, prior)
                source._video_frame_stable(vm, before)
                token = record['token'] = uuid.uuid4().hex
                binding = _Binding(self, vm, lease, prior, before, token)
                record['source'] = dict(stream=prior['token'], frame_id=prior['frame']['frame-id'],
                    pixel_sha256=prior['frame']['pixel-sha256'], rgb_bytes=len(binding.rgb),
                    rgb_origin='previously-verified-immutable-export')
                lease.check()
            # The effectful ARM is intentionally outside the passive lease;
            # the public operation still holds its original machine lock.
            binding.check(self)
            authority._cleanup_owner = binding.cleanup_owner
            self._native_stopped_control_arm_attempted = True
            record['stage'] = 'native-arm'
            record['native'] = _copy(qmp.call(ARM, {'token': token}, max_reply_bytes=_REPLY_BYTES),
                                     limit=_REPLY_BYTES)
            binding.check(self)
            validate_stopped_control_receipt(record['native'], token=token, epoch=binding.epoch)
            binding.native = deepcopy(record['native'])
            binding.last_generation = record['native']['generation']
            self._native_stopped_control_binding = binding
            authority._cleanup_owner = None
            record.update(complete=True, stage='complete')
            return _copy(record)
        except BaseException as error:
            record['error'] = dict(type=type(error).__name__, message=str(error))
            if not isinstance(error, VideoFrameStateRefusal):
                try:
                    if binding is None:
                        vm.close()
                    else:
                        binding.close_original()
                except BaseException as cleanup:
                    error.native_stopped_control_cleanup_error = type(cleanup).__name__
            try:
                retained = _copy(record)
            except DebuggerError:
                retained = dict(format=FORMAT, complete=False, stage=record['stage'],
                    error=record['error'], native=None, omitted_fields=['native'])
            if getattr(error, 'result', None) is None:
                error.result = retained
            else:
                error.native_stopped_control_evidence = retained
            raise
