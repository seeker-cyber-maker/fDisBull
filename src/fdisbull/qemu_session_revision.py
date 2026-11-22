"""Stable session-control identity for passive QEMU frame consumers.

This counter is independent of ObservationAuthority's deliberately conservative
admission generation. It covers cooperating public controls and bound QMP/GDB
dispatch, including attempted writes of unchanged bytes. It is not a native
machine revision, and cannot detect raw handles, other controllers, or devices.
"""
from pathlib import Path
import re
import threading
import uuid


REVISION_SCOPE = 'cooperative-session-control-v1'
_PASSIVE_PUBLIC = frozenset({
    'status', 'tracking_status', 'registers', 'memory', 'memory_translation',
    'clock_observe', 'keyboard_state', 'input_state', 'input_schedule_observe',
    'frame_probe', 'frame_rgba', '_frame_screenshot', 'capture_video_frame',
    'video_frame_observe', 'video_frame_probe', 'video_frame_rgba',
    'video_frame_state_observe', 'display_observe', 'display_probe',
    'vga_configuration_observe', 'retrace_observe', 'clock_sync_observe',
    'audio_observe', 'mixer_observe', 'capture_audio', 'capture_display',
    'screenshot', 'capture_surface', 'hooks', 'code', 'capture_code',
    'dos_process_info', 'runtime_memory', 'dos_source_binding',
    'rewind_status', 'cpu_delta_status', 'timeline_status', 'le_rewind_status',
})
# Exact schemas, not a query-* naming convention. Unknown commands count as
# effects even when their names look observational.
_EMPTY_QMP_READS = frozenset({
    'query-status', 'query-replay', 'query-commands',
    'x-fdisbull-query-clock', 'x-fdisbull-query-video-frame',
    'x-fdisbull-query-input', 'x-fdisbull-query-frame-keys', 'x-fdisbull-query-frame-key-repeat',
    'x-fdisbull-query-retrace', 'x-fdisbull-query-vga-configuration',
    'x-fdisbull-query-display', 'x-fdisbull-query-audio',
    'x-fdisbull-query-mixer', 'x-fdisbull-query-task-context',
})
_EXPORT_NAME = re.compile(r'video-frame-[0-9a-f]{32}\.ppm\Z')
_MEMORY_READ = re.compile(rb'm([0-9a-fA-F]{1,16}),([0-9a-fA-F]{1,5})\Z')
_REGISTER_READ = re.compile(rb'p([0-9a-fA-F]{1,3})\Z')


def _token(value):
    if type(value) is not str or not 1 <= len(value) <= 128 or '\0' in value:
        return False
    try:
        return len(value.encode('utf-8')) <= 128
    except UnicodeError:
        return False


def _selector(arguments, fields):
    return (type(arguments) is dict and set(arguments) == fields
            and _token(arguments.get('token'))
            and type(arguments.get('frame-id')) is int
            and 1 <= arguments['frame-id'] < 1 << 64)


def _memory(arguments):
    if type(arguments) not in (tuple, list) or len(arguments) != 4:
        return False
    address, length, space, write = arguments
    return (type(address) is int and type(length) is int
            and 0 <= address < address + length <= 1 << 64
            and 1 <= length <= 65536 and space in ('physical', 'virtual')
            and write is False)


def passive_dispatch(vm, admission, stack):
    """Recognize a bounded read without relaxing the stronger observation fence."""
    protocol, operation, arguments = admission.protocol, admission.operation, admission.arguments
    if protocol == 'qmp':
        if type(operation) is not str:
            return False
        if operation == 'x-fdisbull-take-pending-events':
            return (operation in getattr(vm, 'qmp_commands', ())
                    and (arguments is None or type(arguments) is dict and not arguments))
        if operation in _EMPTY_QMP_READS:
            return arguments is None or type(arguments) is dict and not arguments
        if operation == 'x-fdisbull-plan-frame-key-batch':
            from .qemu_frame_key_batch import strict_plan_request
            return strict_plan_request(arguments)
        if operation == 'human-monitor-command':
            return (type(arguments) is dict and set(arguments) == {'command-line'}
                    and arguments['command-line'] == 'info registers')
        if operation == 'x-fdisbull-layer-observe':
            if arguments is None or type(arguments) is dict and not arguments:
                return True
            return (type(arguments) is dict and set(arguments) == {'address', 'length'}
                    and _memory((arguments['address'], arguments['length'], 'physical', False))
                    and arguments['length'] <= 65535
                    and arguments['address'] + arguments['length'] <= 1 << 32)
        if operation == 'x-fdisbull-query-stopped-control':
            return (type(arguments) is dict and set(arguments) == {'token'}
                    and _token(arguments['token']))
        if operation == 'x-fdisbull-probe-video-frame':
            if not _selector(arguments, {'token', 'frame-id', 'points'}):
                return False
            points = arguments['points']
            return (type(points) is list and len(points) <= 256
                    and all(type(point) is dict and set(point) == {'x', 'y'}
                        and type(point['x']) is int and 0 <= point['x'] < 320
                        and type(point['y']) is int and 0 <= point['y'] < 200 for point in points))
        if operation == 'x-fdisbull-export-video-frame':
            if not _selector(arguments, {'token', 'frame-id', 'filename'}):
                return False
            filename = arguments['filename']
            directory = getattr(getattr(vm, 'temporary', None), 'name', None)
            if type(filename) is not str or type(directory) is not str:
                return False
            path, owned = Path(filename), Path(directory)
            return (path.is_absolute() and path.parent == owned and owned.is_absolute()
                    and _EXPORT_NAME.fullmatch(path.name) is not None
                    and not owned.is_symlink() and owned.is_dir()
                    and not path.exists() and not path.is_symlink())
        return False
    if protocol == 'gdb-memory':
        return operation == 'memory' and _memory(arguments)
    if protocol != 'gdb-request' or type(operation) is not bytes:
        return False
    # A bounded GDB memory read temporarily changes the protocol address-space
    # selector and restores it. Those internal exchanges do not change guest
    # state. An unpaired raw selector command still counts as a control effect.
    parent = stack[-2] if len(stack) >= 2 and stack[-1] is admission else None
    if (parent is not None and parent.protocol == 'gdb-memory'
            and parent.client is admission.client and parent.expected == operation
            and _memory(parent.arguments)
            and operation in (b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:0', b'Qqemu.PhyMemMode:1')):
        return True
    if operation in (b'g', b'?', b'qC', b'qAttached', b'qfThreadInfo', b'qsThreadInfo', b'qqemu.PhyMemMode'):
        return True
    match = _REGISTER_READ.fullmatch(operation)
    if match is not None:
        return int(match[1], 16) < 1024
    match = _MEMORY_READ.fullmatch(operation)
    if match is not None:
        address, length = (int(value, 16) for value in match.groups())
        return _memory((address, length, 'virtual', False))
    return False


class SessionRevision:
    def __init__(self):
        self.session_id = uuid.uuid4().hex
        self.revision = 0
        self._mode_key = None
        self._mode_id = 0
        self._lock = threading.RLock()

    def effect(self):
        with self._lock:
            self.revision += 1

    def public_operation(self, name, args=(), kwargs=None):
        kwargs = kwargs or {}
        if name in _PASSIVE_PUBLIC:
            return
        if name == 'layers' and (not args or len(args) == 1 and args[0] is None) and kwargs.get('active') is None:
            return
        self.effect()

    def snapshot(self):
        with self._lock:
            return dict(session_id=self.session_id, state_revision=self.revision,
                        state_revision_scope=REVISION_SCOPE,
                        native_state_revision=None, whole_machine_state_revision=None)

    def mode(self, key):
        """Project a full source generation into a session-local legacy mode ID."""
        with self._lock:
            if key != self._mode_key:
                self._mode_key = key
                self._mode_id += 1
            return self._mode_id


def session_revision(vm):
    """One revision authority per VM owner, shared by its execution contexts."""
    value = getattr(vm, 'session_revision', None)
    if value is None:
        value = vm.session_revision = SessionRevision()
    return value
