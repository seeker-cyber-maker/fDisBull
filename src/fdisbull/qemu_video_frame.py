"""Owned VGA source rasters sampled on the native guest scanline schedule.

This stream is separate from synchronous renderer publications. Its explicit
sampling phase and DAC adapter do not establish DOSBox phase equivalence,
application drawing completion, or atomic frame/CPU-state correspondence.
"""
from copy import deepcopy
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from .dosbox_rpc import DebuggerError


VIDEO_FRAME_COMMANDS = frozenset({
    'x-fdisbull-start-video-frame', 'x-fdisbull-query-video-frame',
    'x-fdisbull-stop-video-frame', 'x-fdisbull-export-video-frame',
    'x-fdisbull-probe-video-frame',
})
VIDEO_FRAME_SCRIPT_OPERATIONS = {
    'video-frame-start': 'video_frame_start',
    'video-frame-observe': 'video_frame_observe',
    'video-frame-stop': 'video_frame_stop',
    'video-frame-probe': 'video_frame_probe',
    'capture-video-frame': 'capture_video_frame',
    'video-frame-advance': 'video_frame_advance',
}
MAX_VIDEO_FRAME_POINTS = 4096
_NATIVE_PROBE_POINTS = 256
_NATIVE_REPLY_BYTES = 128 * 1024
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_HEADER = b'P6\n320 200\n255\n'
_PIXEL_BYTES = 320 * 200 * 3


def _reference(value, allowed):
    return allowed and isinstance(value, str) and value.startswith('$')


def validate_video_frame_parameters(*, timeout_ms=1000, stream=None, frame_id=None,
                                    allow_references=False):
    if not _reference(timeout_ms, allow_references) and (
            type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000):
        raise ValueError('Video frame timeout_ms must be an integer in 1..600000')
    if (stream is None) != (frame_id is None):
        raise ValueError('Video frame stream and frame_id must be supplied together')
    if stream is not None and not _reference(stream, allow_references):
        if type(stream) is not str or not 1 <= len(stream.encode('utf-8')) <= 128 or '\0' in stream:
            raise ValueError('Video frame stream must be a nonempty token of at most 128 bytes')
    if frame_id is not None and not _reference(frame_id, allow_references):
        if type(frame_id) is not int or not 1 <= frame_id < 1 << 64:
            raise ValueError('Video frame frame_id must be a positive uint64')


def validate_video_frame_probe(points, *, stream=None, frame_id=None, timeout_ms=1000,
                               allow_references=False):
    validate_video_frame_parameters(timeout_ms=timeout_ms, stream=stream, frame_id=frame_id,
                                    allow_references=allow_references)
    if _reference(points, allow_references):
        return
    if type(points) is not list or len(points) > MAX_VIDEO_FRAME_POINTS:
        raise ValueError('Video frame probe requires a list of at most 4096 source points')
    for point in points:
        if _reference(point, allow_references):
            continue
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('Video frame probe points require exactly two source coordinates')
        if isinstance(point, tuple) and any(_reference(value, allow_references) for value in point):
            raise ValueError('Script video frame probe references require list points')
        for coordinate, extent in zip(point, (320, 200), strict=True):
            if not _reference(coordinate, allow_references) and (
                    type(coordinate) is not int or not 0 <= coordinate < extent):
                raise ValueError('Video frame probe points must be integer source coordinates within 320x200')


def validate_video_frame_capture(name='video-frame.png', *, stream=None, frame_id=None,
                                 max_bytes=None, timeout_ms=1000, allow_references=False):
    from .debugger import _file_name
    if not _reference(name, allow_references):
        _file_name(name)
    validate_video_frame_parameters(timeout_ms=timeout_ms, stream=stream, frame_id=frame_id,
                                    allow_references=allow_references)
    if max_bytes is not None and not _reference(max_bytes, allow_references) and (
            type(max_bytes) is not int or not 1 <= max_bytes <= 16 * 1024**2):
        raise ValueError('Video frame PNG max_bytes must be an integer in 1..16777216')


def validate_video_frame_script_parameters(operation, params, *, allow_references=False):
    """Check every literal, then every resolved value, before route dispatch."""
    if operation == 'video-frame-probe':
        validate_video_frame_probe(**params, allow_references=allow_references)
    elif operation == 'capture-video-frame':
        validate_video_frame_capture(**params, allow_references=allow_references)
    elif operation == 'video-frame-advance':
        from .qemu_video_control import validate_video_frame_advance
        defaults = {'timeout_ms': 5000, 'stop_on_hook': True}
        checked = {key: (defaults[key] if _reference(value, allow_references) else value)
                   for key, value in params.items()}
        validate_video_frame_advance(**checked)
    elif operation in VIDEO_FRAME_SCRIPT_OPERATIONS:
        validate_video_frame_parameters(**params, allow_references=allow_references)
    else:
        raise ValueError('Unknown source video frame operation')


def _probe_points_snapshot(points):
    """Bound the copy even if caller-owned lists grew during lock admission."""
    if type(points) is not list:
        raise ValueError('Video frame probe requires a list of at most 4096 source points')
    snapshot = []
    for point in points[:MAX_VIDEO_FRAME_POINTS + 1]:
        if isinstance(point, list):
            point = tuple(list.__getitem__(point, slice(0, 3)))
        elif isinstance(point, tuple):
            point = tuple.__getitem__(point, slice(0, 3))
        snapshot.append(point)
    return snapshot


def _invalid(vm, message):
    vm.close()
    raise DebuggerError(message)


def _integer(value, *, positive=False, maximum=(1 << 63) - 1):
    return type(value) is int and int(positive) <= value <= maximum


def _frame_valid(frame, native):
    if type(frame) is not dict:
        return False
    for key in ('frame-id', 'stream-generation', 'epoch', 'configuration-generation', 'timing-generation'):
        if not _integer(frame.get(key), positive=True, maximum=(1 << 64) - 1):
            return False
    if (frame['frame-id'] != native['frame-sequence']
            or frame['stream-generation'] != native['stream-generation']
            or frame['epoch'] != native['epoch']
            or type(frame.get('dac-8bit')) is not bool
            or any(type(frame.get(k)) is not int for k in ('width', 'height', 'stride'))
            or frame.get('width') != 320 or frame.get('height') != 200 or frame.get('stride') != 960
            or frame.get('pixel-format') != 'RGB888'
            or frame.get('dac-conversion') != 'replicate-6-to-8-v1'
            or type(frame.get('pixel-sha256')) is not str or not _SHA.fullmatch(frame['pixel-sha256'])):
        return False
    for key in ('frame-start-ns', 'period-ns', 'line-period-ns', 'first-sample-ns',
                'last-sample-ns', 'completed-ns'):
        if not _integer(frame.get(key), positive=key in ('period-ns', 'line-period-ns')):
            return False
    start, period, line = (frame[key] for key in ('frame-start-ns', 'period-ns', 'line-period-ns'))
    rows = frame.get('rows')
    if (line < 4 or start <= native['start-ns'] or start % period or period < 400 * line or period % line
            or type(rows) is not list or len(rows) != 200):
        return False
    for number, row in enumerate(rows):
        if (type(row) is not dict or type(row.get('row')) is not int or row['row'] != number
                or not _integer(row.get('intended-ns')) or not _integer(row.get('actual-ns'))
                or row['intended-ns'] != start + line // 4 + 2 * number * line
                or not row['intended-ns'] <= row['actual-ns'] < row['intended-ns'] + line):
            return False
    return (frame['first-sample-ns'] == rows[0]['actual-ns']
            and frame['last-sample-ns'] == rows[-1]['actual-ns'] == frame['completed-ns']
            and frame['completed-ns'] <= native.get('stop-ns', native['virtual-ns']))


def _native_video(vm, value, clock, *, token, new_stream=False):
    """Validate native identity and completeness before publishing any result."""
    required = {'api-version', 'model', 'state', 'epoch', 'virtual-ns', 'stream-generation',
                'frame-sequence', 'aborted-frames', 'in-progress', 'rows-sampled'}
    if (type(value) is not dict or not required <= value.keys()
            or type(value['api-version']) is not int or value['api-version'] != 1
            or value['model'] != 'qemu-vga-chain4-scanline-v1'
            or value['state'] not in ('idle', 'observing', 'stopped', 'invalidated')
            or not _integer(value['epoch'], positive=True, maximum=(1 << 64) - 1)
            or value['epoch'] != clock['virtual_clock']['native']['epoch']
            or not _integer(value['virtual-ns']) or value['virtual-ns'] != clock['virtual_ns']
            or any(not _integer(value[k], maximum=(1 << 64) - 1)
                   for k in ('stream-generation', 'frame-sequence', 'aborted-frames'))
            or type(value['in-progress']) is not bool
            or not _integer(value['rows-sampled'], maximum=199)):
        _invalid(vm, 'Invalid native video frame stream receipt')
    state = value['state']
    if state == 'idle':
        if (token is not None or value['stream-generation'] or value['frame-sequence']
                or value['in-progress'] or value['rows-sampled']
                or any(k in value for k in ('token', 'start-ns', 'stop-ns', 'frame', 'next-deadline-ns'))):
            _invalid(vm, 'Idle video frame stream retains an unexpected identity')
    else:
        if (not value['stream-generation'] or type(token) is not str or value.get('token') != token
                or not _integer(value.get('start-ns')) or value['start-ns'] > value['virtual-ns']
                or type(value.get('device')) is not str or not value['device']
                or (state == 'stopped') != ('stop-ns' in value)
                or 'stop-ns' in value and (not _integer(value['stop-ns'])
                    or not value['start-ns'] <= value['stop-ns'] <= value['virtual-ns'])):
            _invalid(vm, 'Native video frame stream identity or interval is invalid')
        if (state != 'observing' and (value['in-progress'] or value['rows-sampled']
                                     or 'next-deadline-ns' in value)
                or not value['in-progress'] and value['rows-sampled']
                or state == 'observing' and not _integer(value.get('next-deadline-ns'))
                or state == 'invalidated' and (type(value.get('reason')) is not str or not value['reason']
                                              or 'frame' in value)):
            _invalid(vm, 'Native video frame stream progress or invalidation is incoherent')
        if 'frame' in value and not _frame_valid(value['frame'], value):
            _invalid(vm, 'Native video frame has incomplete rows, timing or identity')
    prior = getattr(vm, '_video_frame_last', None)
    if prior is not None:
        if (value['stream-generation'] < prior['stream-generation']
                or value['frame-sequence'] < prior['frame-sequence']):
            _invalid(vm, 'Native video frame sequence regressed')
        if (not new_stream and state != 'invalidated' and 'frame' not in value
                and value['frame-sequence'] != prior['frame-sequence']):
            _invalid(vm, 'Native video frame sequence advanced without a completed raster')
        if new_stream:
            if (value['stream-generation'] != prior['stream-generation'] + 1
                    or value['frame-sequence'] != prior['frame-sequence']
                    or value.get('token') == prior.get('token') or 'frame' in value):
                _invalid(vm, 'New video frame stream reused or invented an identity')
        elif value['stream-generation'] != prior['stream-generation']:
            _invalid(vm, 'Native video frame stream changed without an owned start')
        else:
            for key in ('token', 'start-ns', 'device'):
                if value.get(key) != prior.get(key):
                    _invalid(vm, 'Native video frame stream owner changed')
            previous_frame, frame = prior.get('frame'), value.get('frame')
            if (previous_frame is not None and state != 'invalidated'
                    and (frame is None or frame['frame-id'] == previous_frame['frame-id'] and frame != previous_frame)):
                _invalid(vm, 'Native completed video frame changed under the same identity')
            if prior['state'] == 'stopped' and state == 'invalidated':
                if value['frame-sequence'] != prior['frame-sequence']:
                    _invalid(vm, 'Stopped video stream invalidation invented a completed frame')
            elif prior['state'] in ('stopped', 'invalidated'):
                expected = dict(prior, **{'virtual-ns': value['virtual-ns']})
                if state == 'invalidated':
                    expected['epoch'] = value['epoch']
                if value != expected:
                    _invalid(vm, 'Native inactive video stream changed without a new start')
            if state != 'invalidated' and value['epoch'] != prior['epoch']:
                _invalid(vm, 'Native video frame producing epoch changed')
    if prior is None or _identity(value) != _identity(prior) or 'frame' not in value:
        for key in ('_video_frame_probe_samples', '_video_frame_owned_rgb'):
            if hasattr(vm, key):
                delattr(vm, key)
    vm._video_frame_last = deepcopy(value)
    return deepcopy(value)


def _identity(native):
    frame = native.get('frame')
    return (native.get('token'), native['stream-generation'],
            frame['epoch'] if frame else None, frame['frame-id'] if frame else None)


def _remaining(vm):
    deadline = getattr(vm, 'operation_deadline', None)
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Video frame operation host deadline expired')


def _failed(vm, error, stage, *, clock=None, native=None, result=None, artifact=None,
            probe_chunks=None):
    evidence = dict(format='fdisbull-video-frame-error-1', stage=stage,
                    clock=deepcopy(clock), native=deepcopy(native), result=deepcopy(result),
                    artifact=deepcopy(artifact))
    if probe_chunks is not None:
        evidence['probe_chunks'] = deepcopy(probe_chunks)
    if getattr(error, 'result', None) is None:
        error.result = evidence
    else:
        error.video_frame_evidence = evidence
    try:
        vm.close()
    except BaseException as cleanup:
        error.video_frame_cleanup_error = type(cleanup).__name__


def _read_rgb(path):
    """Bound both type validation and byte reads to one non-following fd."""
    expected = len(_HEADER) + _PIXEL_BYTES
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
            raise DebuggerError('Native video frame export is not an exact bounded regular file')
        raw = stream.read(expected + 1)
    if len(raw) != expected or not raw.startswith(_HEADER):
        raise DebuggerError('Native video frame export has the wrong header or byte count')
    return raw[len(_HEADER):]


class QemuVideoFrameMixin:
    def _video_frame_context(self):
        from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Video frames require a project outside a caller-owned transaction')
        configuration = self.vm.machine_configuration
        if (configuration.get('clock_profile', {}).get('profile') != 'virtual'
                or configuration.get('retrace_profile', {}).get('profile') != 'precise'
                or not VIDEO_FRAME_COMMANDS | VIRTUAL_CLOCK_COMMANDS <= self.vm.qmp_commands):
            raise ValueError('Video frames require the native scanline extension and explicit virtual/precise profiles')
        self._stopped()
        return self._clock_snapshot()

    def _video_frame_read(self, vm, clock):
        if self.vm is not vm:
            _invalid(vm, 'Video frame owner changed before native observation')
        return _native_video(vm, vm.qmp.call('x-fdisbull-query-video-frame',
                             max_reply_bytes=_NATIVE_REPLY_BYTES), clock,
                             token=getattr(vm, '_video_frame_token', None))

    def _video_frame_stable(self, vm, before):
        if self.vm is not vm:
            _invalid(vm, 'Video frame owner changed across a stopped operation')
        after = self._clock_snapshot()
        if (any(before[k] != after[k] for k in ('run', 'epoch', 'virtual_ns', 'counter'))
                or before['virtual_clock']['native']['epoch'] != after['virtual_clock']['native']['epoch']):
            _invalid(vm, 'Machine clock changed across a stopped video frame operation')
        return after

    def _video_frame_publish(self, vm, operation, result):
        _remaining(vm)
        self._event(operation, result)
        _remaining(vm)

    def _video_frame_result(self, native, clock):
        frame = native.get('frame')
        return dict(format='fdisbull-video-frame-stream-1', context='machine', run=self.run_id,
                    epoch=clock['epoch'], stream=native.get('token'), state=native['state'],
                    stream_generation=native['stream-generation'], frame_sequence=native['frame-sequence'],
                    frame_id=frame['frame-id'] if frame else None, observed_ns=native['virtual-ns'],
                    width=frame['width'] if frame else None, height=frame['height'] if frame else None,
                    completed_source_raster=frame is not None, legacy_phase_equivalence=None,
                    application_frame_complete=None, frame=deepcopy(frame), native=deepcopy(native),
                    clock=deepcopy(clock), scope=('Completed owned 320x200 VGA source raster sampled row by row '
                        'at the declared native phase with legacy DAC bit replication. No DOSBox phase '
                        'equivalence, application drawing completion, input consumption or atomic CPU/frame claim.'))

    def video_frame_observe(self, *, timeout_ms=1000):
        vm = self.vm
        before = self._video_frame_context()
        native = result = None
        try:
            native = self._video_frame_read(vm, before)
            self._video_frame_stable(vm, before)
            result = self._video_frame_result(native, before)
            self._video_frame_publish(vm, 'machine-video-frame-observe', result)
            return result
        except BaseException as error:
            _failed(vm, error, 'observe', clock=before, native=native, result=result)
            raise

    def video_frame_start(self, *, timeout_ms=1000):
        from .qemu_video_control import require_no_video_frame_fence
        require_no_video_frame_fence(self.vm, 'source-stream start')
        vm = self.vm
        before = self._video_frame_context()
        prior = self._video_frame_read(vm, before)
        if prior['state'] == 'observing':
            raise ValueError('Stop the current video frame stream before starting another')
        token = uuid.uuid4().hex
        native = result = None
        try:
            native = _native_video(vm, vm.qmp.call('x-fdisbull-start-video-frame', {'token': token},
                                   max_reply_bytes=_NATIVE_REPLY_BYTES),
                                   before, token=token, new_stream=True)
            if native['state'] != 'observing' or native['start-ns'] != before['virtual_ns']:
                _invalid(vm, 'Video frame start did not establish the requested stream')
            self._video_frame_stable(vm, before)
            vm._video_frame_token = token
            result = self._video_frame_result(native, before)
            self._video_frame_publish(vm, 'machine-video-frame-start', result)
            return result
        except BaseException as error:
            _failed(vm, error, 'start', clock=before, native=native, result=result)
            raise

    def video_frame_stop(self, *, timeout_ms=1000):
        from .qemu_video_control import require_no_video_frame_fence
        require_no_video_frame_fence(self.vm, 'source-stream stop')
        vm = self.vm
        before = self._video_frame_context()
        prior = self._video_frame_read(vm, before)
        if prior['state'] not in ('observing', 'stopped'):
            raise ValueError('No valid owned video frame stream is available to stop')
        native = result = None
        try:
            native = _native_video(vm, vm.qmp.call('x-fdisbull-stop-video-frame', {'token': prior['token']},
                                   max_reply_bytes=_NATIVE_REPLY_BYTES),
                                   before, token=prior['token'])
            if (native['state'] != 'stopped' or native.get('frame') != prior.get('frame')
                    or native['frame-sequence'] != prior['frame-sequence']
                    or native['stop-ns'] != prior.get('stop-ns', before['virtual_ns'])):
                _invalid(vm, 'Video frame stop changed the completed raster')
            self._video_frame_stable(vm, before)
            result = self._video_frame_result(native, before)
            self._video_frame_publish(vm, 'machine-video-frame-stop', result)
            return result
        except BaseException as error:
            _failed(vm, error, 'stop', clock=before, native=native, result=result)
            raise

    def _video_frame_select(self, vm, clock, stream, frame_id):
        native = self._video_frame_read(vm, clock)
        if 'frame' not in native:
            raise ValueError('No completed source raster is retained; advance or restart the stream explicitly')
        if stream is not None and (stream != native['token'] or frame_id != native['frame']['frame-id']):
            raise ValueError('Requested video frame identity is not the retained raster')
        return native

    def video_frame_probe(self, points, *, stream=None, frame_id=None, timeout_ms=1000):
        # Public preflight precedes lock admission. Validate a bounded owned
        # copy as well, because a caller/guard may have mutated its lists while
        # we waited. All later callbacks see only this immutable point data.
        points = _probe_points_snapshot(points)
        validate_video_frame_probe(points, stream=stream, frame_id=frame_id, timeout_ms=timeout_ms)
        vm = self.vm
        before = self._video_frame_context()
        prior = self._video_frame_select(vm, before, stream, frame_id)
        raw = result = None
        chunks = []
        try:
            known = getattr(vm, '_video_frame_probe_samples', {})
            rgb_bytes = getattr(vm, '_video_frame_owned_rgb', None)
            samples, observed = [], {}
            for start in range(0, len(points), _NATIVE_PROBE_POINTS):
                _remaining(vm)
                if self.vm is not vm:
                    _invalid(vm, 'Video frame owner changed before a probe chunk')
                selected = points[start:start + _NATIVE_PROBE_POINTS]
                raw = vm.qmp.call('x-fdisbull-probe-video-frame', dict(token=prior['token'],
                    **{'frame-id': prior['frame']['frame-id']},
                    points=[dict(x=x, y=y) for x, y in selected]),
                    max_reply_bytes=_NATIVE_REPLY_BYTES)
                # At most sixteen wire-bounded replies are retained only until
                # success, or attached as received evidence on a failed probe.
                chunks.append(raw)
                if type(raw) is not dict or set(raw) != {'info', 'pixels'}:
                    _invalid(vm, 'Invalid native video frame probe receipt')
                native = _native_video(vm, raw['info'], before, token=prior['token'])
                pixels = raw['pixels']
                if native != prior or type(pixels) is not list or len(pixels) != len(selected):
                    _invalid(vm, 'Native video frame probe changed identity or point count')
                for point, pixel in zip(selected, pixels, strict=True):
                    if (type(pixel) is not dict or set(pixel) != {'x', 'y', 'r', 'g', 'b'}
                            or any(type(pixel[k]) is not int for k in pixel)
                            or [pixel['x'], pixel['y']] != list(point)
                            or any(not 0 <= pixel[k] <= 255 for k in ('r', 'g', 'b'))):
                        _invalid(vm, 'Native video frame probe reordered points or returned invalid RGB')
                    rgb = bytes(pixel[k] for k in ('r', 'g', 'b'))
                    offset = (point[1] * 320 + point[0]) * 3
                    if (point in observed and observed[point] != rgb
                            or point in known and known[point] != rgb
                            or rgb_bytes is not None and rgb_bytes[offset:offset + 3] != rgb):
                        _invalid(vm, 'Native video frame probe pixels contradict the retained raster')
                    observed[point] = rgb
                    samples.append(dict(x=point[0], y=point[1], rgb=list(rgb)))
            self._video_frame_stable(vm, before)
            result = self._video_frame_result(prior, before)
            result.update(format='fdisbull-video-frame-probe-1', samples=samples)
            self._video_frame_publish(vm, 'machine-video-frame-probe', result)
            # The 4096-coordinate consistency map is temporary. Keep the prior
            # sparse-cache bound, and do not erase it for a metadata-only read.
            if observed:
                vm._video_frame_probe_samples = dict(list(observed.items())[-_NATIVE_PROBE_POINTS:])
            return result
        except BaseException as error:
            _failed(vm, error, 'probe', clock=before, native=raw, result=result,
                    probe_chunks=chunks)
            raise

    def _video_frame_selected_rgb(self, vm, before, prior):
        """Read one exact source raster without an image/artifact side effect."""
        path = Path(vm.temporary.name) / ('video-frame-' + uuid.uuid4().hex + '.ppm')
        native = None
        try:
            _remaining(vm)
            if self.vm is not vm:
                _invalid(vm, 'Video frame owner changed before source export')
            native = _native_video(vm, vm.qmp.call('x-fdisbull-export-video-frame',
                {'token': prior['token'], 'frame-id': prior['frame']['frame-id'], 'filename': str(path)},
                max_reply_bytes=_NATIVE_REPLY_BYTES),
                before, token=prior['token'])
            if native != prior:
                _invalid(vm, 'Native video frame export changed identity')
            _remaining(vm)
            pixels = _read_rgb(path)
            if hashlib.sha256(pixels).hexdigest() != native['frame']['pixel-sha256']:
                _invalid(vm, 'Native video frame export differs from its owned raster hash')
            for (x, y), rgb in getattr(vm, '_video_frame_probe_samples', {}).items():
                offset = (y * 320 + x) * 3
                if pixels[offset:offset + 3] != rgb:
                    _invalid(vm, 'Native video frame export contradicts an earlier pixel probe')
            _remaining(vm)
            self._video_frame_stable(vm, before)
            _remaining(vm)
            vm._video_frame_owned_rgb = pixels
        except BaseException as error:
            _failed(vm, error, 'export', clock=before, native=native)
            raise
        finally:
            # An unexpected directory is evidence, not permission to recurse.
            active = sys.exc_info()[1]
            try:
                if path.is_symlink() or not path.is_dir():
                    path.unlink(missing_ok=True)
            except OSError as cleanup:
                if active is not None:
                    active.video_frame_file_cleanup_error = type(cleanup).__name__
                else:
                    _failed(vm, cleanup, 'export-cleanup', clock=before, native=native)
                    raise
        return pixels, native

    def video_frame_rgba(self, *, stream=None, frame_id=None, timeout_ms=1000):
        """Return immutable RGBA bytes; never encode PNG or publish an artifact."""
        from .screenshot_codecs import RGBAFrame
        vm = self.vm
        before = self._video_frame_context()
        prior = self._video_frame_select(vm, before, stream, frame_id)
        pixels, native = self._video_frame_selected_rgb(vm, before, prior)
        metadata = None
        try:
            _remaining(vm)
            rgba = bytearray(320 * 200 * 4)
            rgba[0::4], rgba[1::4], rgba[2::4] = pixels[0::3], pixels[1::3], pixels[2::3]
            rgba[3::4] = b'\xff' * (320 * 200)
            rgba = bytes(rgba)
            digest = hashlib.sha256(rgba).hexdigest()
            _remaining(vm)
            after = self._video_frame_stable(vm, before)
            metadata = self._video_frame_result(native, before)
            metadata.update(format='rgba', encoding='rgba', pixel_format='RGBA8', stride=1280,
                uncompressed_bytes=len(rgba), sha256=digest, raw_sha256=digest,
                source='qemu_completed_source_raster', pixel_sha256=native['frame']['pixel-sha256'],
                stopped=True, clocks=dict(before=deepcopy(before), after=deepcopy(after)),
                transport=dict(format='ppm', encoding='ppm', pixel_format='RGB888', stride=960,
                    uncompressed_bytes=len(pixels), bytes=len(_HEADER) + len(pixels),
                    sha256=hashlib.sha256(_HEADER + pixels).hexdigest(),
                    pixel_sha256=native['frame']['pixel-sha256']))
            _remaining(vm)
            return RGBAFrame(320, 200, rgba, digest, metadata)
        except BaseException as error:
            _failed(vm, error, 'rgba', clock=before, native=native, result=metadata)
            raise

    def capture_video_frame(self, name='video-frame.png', *, stream=None, frame_id=None,
                            max_bytes=None, timeout_ms=1000):
        from PIL import Image
        vm = self.vm
        before = self._video_frame_context()
        prior = self._video_frame_select(vm, before, stream, frame_id)
        pixels, native = self._video_frame_selected_rgb(vm, before, prior)
        metadata = artifact = None
        try:
            _remaining(vm)
            output = io.BytesIO()
            with Image.frombytes('RGB', (320, 200), pixels) as image:
                image.save(output, format='PNG')
            _remaining(vm)
            after = self._video_frame_stable(vm, before)
            _remaining(vm)
        except BaseException as error:
            _failed(vm, error, 'encode', clock=before, native=native)
            raise
        data = output.getvalue()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('Video frame PNG exceeds its image byte budget before artifact publication')
        metadata = self._video_frame_result(native, before)
        metadata.update(source='qemu_completed_source_raster', pixel_sha256=native['frame']['pixel-sha256'],
                        stopped=True, clocks=dict(before=before, after=after), sha256=hashlib.sha256(data).hexdigest())
        try:
            _remaining(vm)
            stage = 'artifact-publication'
            artifact = self._artifact(name, 'screenshot', data, metadata)
            stage = 'event-publication'
            self._video_frame_publish(vm, 'machine-capture-video-frame', dict(artifact=artifact['artifact'],
                        stream=native['token'], frame_id=native['frame']['frame-id'], sha256=metadata['sha256']))
            return artifact
        except BaseException as error:
            _failed(vm, error, stage, clock=before, native=native, result=metadata, artifact=artifact)
            raise
