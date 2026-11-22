"""Read selected stationary INT 33h state from one verified CuteMouse build."""
import hashlib
import os
from pathlib import Path
import stat
import struct

from .dosbox_rpc import DebuggerError
from .qemm_runtime import _FATVolume
from .qemu_video_frame_state import _admit, _CapturedSource, _read_state, _refuse


_DRIVER_SHA256 = '822cf550c9e19a22785722d2306aa08ede10ff20bfe931d5a81a15f77c5f363e'
_DRIVER_SIZE = 5829
_MAX_BOOT_IMAGE = 2880 * 1024
_IVT = 0x33 * 4
_BIOS_VIDEO_MODE = 0x449
_HANDLER_ENTRY = 0xb5e
# Segment-relative offsets in CTMouse 2.1b4. The resident origin is 0x100
# and these source windows are unrelocated in the pinned MZ executable.
_HEADER_SIZE = 32
_CODE = (
    ('dispatcher', 0xb1a, 0x5e),
    ('position_and_buttons', 0x952, 0x15),
    ('coordinate_ranges', 0x9f2, 0x1d),
    ('mickey_ratio', 0xae4, 0x0f),
    ('motion_conversion', 0x39b, 0x75),
    ('motion_and_button_dispatch', 0x327, 0x46),
    ('button_edge_position', 0x410, 0x24),
    ('button_history_queries', 0x967, 0x3d),
)
_DATA = ((0x4e, 8), (0xa4, 0x24), (0xce, 36), (0x15a, 2), (0x37a, 1))
_CLOCK_FIELDS = ('run', 'epoch', 'session', 'native_state', 'clock_profile',
                 'counter', 'virtual_ns', 'virtual_clock')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _driver_source(context, vm):
    expected = context._checkpoint_launch['boot_image_sha256']
    if (vm.machine_configuration['boot_device'] != 'floppy'
            or vm.inputs.get('boot_image', {}).get('sha256') != expected):
        _refuse('unsupported_boot_image', 'INT33 observation requires the admitted FAT12 floppy boot image')
    path = Path(vm.temporary.name) / 'boot-image.raw'
    try:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX_BOOT_IMAGE:
                raise ValueError('Expected a bounded regular boot image')
            raw = stream.read(_MAX_BOOT_IMAGE + 1)
        if len(raw) != info.st_size or _sha(raw) != expected:
            raise ValueError('Owned boot copy does not match its recorded SHA-256')
        volume = _FATVolume(raw)
        if volume.boot_device != 'floppy':
            raise ValueError('Expected a FAT12 floppy')
        driver = volume.read(r'\CTMOUSE.EXE', maximum=_DRIVER_SIZE)
    except (OSError, ValueError) as error:
        _refuse('driver_source_unavailable', f'INT33 driver source unavailable: {error}')
    if (len(driver) != _DRIVER_SIZE or _sha(driver) != _DRIVER_SHA256
            or driver[:2] != b'MZ'
            or struct.unpack_from('<2H', driver, 6) != (0, _HEADER_SIZE // 16)):
        _refuse('unsupported_driver_source', 'INT33 observation requires the pinned unrelocated CuteMouse 2.1b4')
    return driver, expected


def _resident_ranges(vector):
    entry, segment = struct.unpack('<HH', vector)
    base = segment << 4
    if (entry != _HANDLER_ENTRY or base < 0x500
            or base + max(offset + size for _, offset, size in _CODE) > 0xa0000):
        _refuse('unsupported_int33_vector', 'Live INT33 vector does not select the supported conventional RAM handler')
    return base, entry, segment, [
        dict(address=address, length=size) for address, size in (
            (_IVT, 4), (_BIOS_VIDEO_MODE, 1),
            *((base + offset, size) for _, offset, size in _CODE),
            *((base + offset, size) for offset, size in _DATA),
        )
    ]


def _decode(driver, base, selected):
    if selected[_BIOS_VIDEO_MODE] != b'\x13':
        _refuse('unsupported_video_mode', 'INT33 observation requires BIOS video mode 13h')
    spans = []
    for purpose, offset, size in _CODE:
        file_offset = _HEADER_SIZE + offset - 0x100
        wanted = driver[file_offset:file_offset + size]
        if wanted != selected[base + offset]:
            _refuse('resident_source_mismatch', f'INT33 resident {purpose} bytes differ from the pinned driver')
        spans.append(dict(purpose=purpose, address=base + offset, file_offset=file_offset,
                          length=size, sha256=_sha(wanted)))

    coordinates = selected[base + 0xa4]
    maximum = struct.unpack_from('<hh', coordinates)
    raw = struct.unpack_from('<hh', coordinates, 0xb0 - 0xa4)
    position = struct.unpack_from('<hh', coordinates, 0xb4 - 0xa4)
    minimum = struct.unpack_from('<hh', coordinates, 0xc4 - 0xa4)
    ratio_x, ratio_y, sensitivity_x, sensitivity_y = struct.unpack('<hhHH', selected[base + 0x4e])
    rounding = struct.unpack_from('<hh', coordinates, 0xc0 - 0xa4)
    buttons = selected[base + 0x37a][0] & 7
    if (selected[base + 0x15a] != b'\xfe\xff'
            or position != (raw[0] & ~1, raw[1]) or min(ratio_x, ratio_y) <= 0
            or not 0 <= minimum[0] <= raw[0] <= maximum[0] < 640
            or not 0 <= minimum[1] <= raw[1] <= maximum[1] < 200):
        _refuse('unsupported_coordinate_state', 'INT33 state is outside the qualified mode 13h coordinate profile')
    # Press and release each retain a count and captured position per button.
    # AX=5/6 clear their count but keep the previous position until another edge.
    records = struct.iter_unpack('<Hhh', selected[base + 0xce])
    edges = {}
    for phase in ('press', 'release'):
        edges[phase] = {}
        for button in ('left', 'right', 'middle'):
            count, y, x = next(records)
            edges[phase][button] = dict(count=count, last_position=[x, y])
    return dict(position=list(position), raw_position=list(raw),
                minimum=list(minimum), maximum=list(maximum), buttons=buttons, button_edges=edges,
                mickeys_per_eight_units=[ratio_x, ratio_y],
                sensitivity_coefficients=[sensitivity_x, sensitivity_y],
                position_remainders=list(rounding), matching_source_spans=spans)


def _same_clock(before, after):
    if any(before[key] != after[key] for key in _CLOCK_FIELDS):
        raise DebuggerError('Stopped clock changed across the INT33 observation')


def observe_int33_mouse(self, *, stream=None, frame_id=None, timeout_ms=1000):
    """Observe the live driver beside a retained mode 13h raster while stopped."""
    vm = self.vm
    qmp, remote, authority = _admit(self, vm, [])
    driver, boot_hash = _driver_source(self, vm)
    try:
        with authority.observe(self, deadline=vm.operation_deadline,
                               ram_ranges=[(_IVT, 4)]) as vector_lease:
            source = _CapturedSource(self, vm, vector_lease)
            status = qmp.call('query-status')
            if type(status) is not dict or type(status.get('running')) is not bool:
                raise DebuggerError('Invalid stopped-state observation for INT33')
            if status['running']:
                _refuse('machine_running', 'Pause the machine before reading INT33 state')
            entry_clock = source._clock_snapshot()
            raster = source._video_frame_read(vm, entry_clock)
            if raster['state'] != 'observing' or 'frame' not in raster:
                _refuse('no_completed_source_raster', 'INT33 observation requires an active retained source raster')
            frame = raster['frame']
            if stream is not None and (stream != raster['token'] or frame_id != frame['frame-id']):
                _refuse('source_identity_not_retained', 'Requested INT33 source raster is no longer retained')
            vector = remote.memory(_IVT, 4, space='physical')
            if len(vector) != 4:
                raise DebuggerError('Incomplete physical INT33 vector')
            base, entry, segment, ranges = _resident_ranges(vector)

        with authority.observe(self, deadline=vm.operation_deadline, ram_ranges=ranges) as lease:
            source = _CapturedSource(self, vm, lease)
            before, after = {}, {}
            _same_clock(entry_clock, source._clock_snapshot())
            _read_state(vm, qmp, remote, ranges, lease, before)
            if before['cpu']['cpu_mode'] != 'real':
                _refuse('unsupported_cpu_mode', 'INT33 observation requires the selected real-mode vCPU')
            selected = {item['address']: bytes.fromhex(item['data_hex']) for item in before['ram']}
            if selected[_IVT] != vector:
                raise DebuggerError('INT33 vector changed across the stopped read')
            state = _decode(driver, base, selected)
            _read_state(vm, qmp, remote, ranges, lease, after)
            if before != after or source._video_frame_read(vm, entry_clock) != raster:
                raise DebuggerError('Selected stopped state or retained raster changed during INT33 observation')
            _same_clock(entry_clock, source._clock_snapshot())
    except BaseException as error:
        if getattr(error, 'observation_refusal', False) is not True:
            try:
                vm.close()
            except BaseException as cleanup:
                error.int33_observation_cleanup_error = type(cleanup).__name__
        raise

    return dict(format='fdisbull-qemu-int33-mouse-observation-1', complete=True, run=self.run_id,
                runtime_epoch=self._runtime_epoch, checkpoint_epoch=self._checkpoint_epoch,
                scope='Selected live CuteMouse state beside a retained source raster at one cooperative stopped boundary',
                driver=dict(name='CuteMouse 2.1b4', sha256=_DRIVER_SHA256, boot_image_sha256=boot_hash,
                            vector=dict(segment=segment, offset=entry), bios_video_mode=0x13),
                raster=dict(stream=raster['token'], frame_id=frame['frame-id'], epoch=frame['epoch'],
                            configuration_generation=frame['configuration-generation'],
                            completed_ns=frame['completed-ns'], native_pixel_sha256=frame['pixel-sha256']),
                clock=dict(epoch=entry_clock['epoch'], virtual_ns=entry_clock['virtual_ns'],
                           instruction_count=entry_clock['counter']['value']),
                vector_authority=vector_lease.receipt(), authority=lease.receipt(), **state)
