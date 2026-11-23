"""Scanline stream host boundaries at the production QMP wire interface.

These deliberately hostile protocol peers test transport, ownership and
validation only. Guest cadence/RGB evidence belongs to the native authored
fixture; no peer receipt is a renderer or legacy-equivalence oracle.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_video_frame import VIDEO_FRAME_COMMANDS
from test_qemu_audio import audio
from test_qemu_clock_budget import NativeWire
from test_qemu_io_deadlines import observation


class VideoWire(NativeWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.video = {'api-version': 1, 'model': 'qemu-vga-chain4-scanline-v1',
            'state': 'idle', 'epoch': 1, 'virtual-ns': 1000, 'stream-generation': 0,
            'frame-sequence': 0, 'aborted-frames': 0, 'in-progress': False, 'rows-sampled': 0}
        self.rgb = bytes([4, 85, 170]) * (320 * 200)
        self.change_video = lambda value: value
        self.change_probe = lambda value: value
        self.after_video = lambda: None
        self.bad_export = False
        self.start_refusal = None

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command not in VIDEO_FRAME_COMMANDS:
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'x-fdisbull-start-video-frame':
            if self.start_refusal is not None:
                self.start_refusal()
                error = {'class': 'GenericError', 'desc': 'Video frame source is unsupported'}
                self.buffer.extend(json.dumps({'id': request['id'], 'error': error}).encode() + b'\n')
                return
            self.video['stream-generation'] += 1
            self.video.update(state='observing', token=args['token'], device='/machine/vga',
                **{'start-ns': self.receipt['virtual-ns'],
                   'next-deadline-ns': (self.receipt['virtual-ns'] // 32000 + 1) * 32000 + 8})
            for key in ('stop-ns', 'frame', 'reason'):
                self.video.pop(key, None)
        elif command == 'x-fdisbull-stop-video-frame':
            self.video.update(state='stopped', **{'stop-ns': self.video.get('stop-ns', self.receipt['virtual-ns'])})
            self.video.pop('next-deadline-ns', None)
        elif command == 'x-fdisbull-export-video-frame':
            rgb = bytes([7, 87, 168]) * (320 * 200) if self.bad_export else self.rgb
            Path(args['filename']).write_bytes(b'P6\n320 200\n255\n' + rgb)
        self.video['virtual-ns'] = self.receipt['virtual-ns']
        value = self.change_video(deepcopy(self.video))
        if command == 'x-fdisbull-probe-video-frame':
            values = []
            for point in args['points']:
                offset = (point['y'] * 320 + point['x']) * 3
                r, g, b = self.rgb[offset:offset + 3]
                values.append(dict(**point, r=r, g=g, b=b))
            value = self.change_probe(dict(info=value, pixels=values))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency
        self.after_video()

    def publish(self):
        number = self.video['frame-sequence'] + 1
        start = (self.receipt['virtual-ns'] // 32000 + 1) * 32000
        rows = [dict(row=r, **{'intended-ns': start + 8 + 64 * r,
                               'actual-ns': start + 8 + 64 * r}) for r in range(200)]
        self.video['frame-sequence'] = number
        self.video['frame'] = {'frame-id': number, 'stream-generation': self.video['stream-generation'],
            'epoch': 1, 'configuration-generation': 7, 'timing-generation': 4,
            'width': 320, 'height': 200, 'stride': 960, 'pixel-format': 'RGB888',
            'dac-conversion': 'replicate-6-to-8-v1', 'dac-8bit': False,
            'frame-start-ns': start, 'period-ns': 32000, 'line-period-ns': 32,
            'first-sample-ns': rows[0]['actual-ns'], 'last-sample-ns': rows[-1]['actual-ns'],
            'completed-ns': rows[-1]['actual-ns'], 'rows': rows,
            'pixel-sha256': hashlib.sha256(self.rgb).hexdigest()}
        self.receipt['virtual-ns'] = start + 15000
        self.video['next-deadline-ns'] = start + 32000 + 8


@pytest.fixture
def video(audio):
    o = audio
    o.wire = VideoWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= VIDEO_FRAME_COMMANDS
    o.vm.machine_configuration['retrace_profile'] = {'profile': 'precise'}
    o.session.capabilities['video_frame_capture'] = True
    return o


def test_public_stream_probe_and_capture_share_exact_owned_pixels(video):
    o = video
    started = o.session.video_frame_start()
    assert not started['completed_source_raster'] and started['frame_id'] is None
    with pytest.raises(ValueError, match='No completed source raster'):
        o.session.video_frame_probe([])
    assert not o.vm.closed
    o.wire.publish()
    seen = o.session.video_frame_observe()
    identity = dict(stream=seen['stream'], frame_id=seen['frame_id'])
    points = [[319, 199], [0, 0], [319, 199]]
    probe = o.session.video_frame_probe(points, **identity)
    assert probe['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170]) for x, y in points]
    assert probe['native'] == seen['native']
    captured = o.session.capture_video_frame(**identity)
    metadata = captured['metadata']
    assert metadata['source'] == 'qemu_completed_source_raster'
    assert metadata['frame_id'] == seen['frame_id']
    assert metadata['pixel_sha256'] == hashlib.sha256(o.wire.rgb).hexdigest()
    assert metadata['legacy_phase_equivalence'] is metadata['application_frame_complete'] is None
    assert o.session.capabilities['completed_guest_frames'] is False
    record = o.project.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (captured['artifact'],)).fetchone()
    with Image.open(io.BytesIO(bytes(record['data']))) as image:
        assert image.size == (320, 200) and image.convert('RGB').tobytes() == o.wire.rgb
    assert not list(o.directory.glob('video-frame-*.ppm'))
    assert all(c not in ('cont', 'screendump', 'human-monitor-command') for c, _ in o.wire.calls)


def test_same_pixels_still_have_new_native_ordinal_and_stop_keeps_last_frame(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    first = o.session.video_frame_observe()
    o.wire.publish()
    second = o.session.video_frame_observe()
    assert second['frame_id'] == first['frame_id'] + 1
    assert second['frame']['pixel-sha256'] == first['frame']['pixel-sha256']
    stopped = o.session.video_frame_stop()
    assert stopped['frame'] == second['frame']
    assert o.session.video_frame_probe([])['samples'] == []
    restarted = o.session.video_frame_start()
    assert restarted['stream'] != stopped['stream']
    assert restarted['stream_generation'] == stopped['stream_generation'] + 1
    assert restarted['frame_id'] is None and restarted['frame_sequence'] == second['frame_id']


@pytest.mark.parametrize('change', [
    {'api-version': True}, {'epoch': 2}, {'virtual-ns': 999}, {'stream-generation': True},
    {'frame-sequence': True}, {'token': 'foreign'}, {'state': 'unexpected'},
    {'in-progress': 1}, {'rows-sampled': 200}, {'start-ns': -1},
    {'stop-ns': 1000}, {'device': ''},
])
def test_malformed_or_foreign_stream_closes_original_owner(video, change):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.wire.change_video = lambda value: dict(value, **change)
    with pytest.raises(DebuggerError):
        o.session.video_frame_observe()
    assert o.vm.closed


@pytest.mark.parametrize('change', [
    {'frame-id': 0}, {'epoch': 2}, {'stream-generation': 2}, {'configuration-generation': False},
    {'timing-generation': 0}, {'width': 640}, {'width': 320.0}, {'stride': 1280}, {'pixel-format': 'RGBA'},
    {'dac-conversion': 'qemu-c6-to-8'}, {'dac-8bit': 1}, {'pixel-sha256': 'x' * 64},
    {'frame-start-ns': 32001}, {'period-ns': 1}, {'first-sample-ns': 32000},
    {'completed-ns': 50000}, {'rows': []},
])
def test_incomplete_or_incoherent_frame_is_not_published(video, change):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    def mutate(value):
        value['frame'].update(change)
        return value
    o.wire.change_video = mutate
    with pytest.raises(DebuggerError):
        o.session.video_frame_observe()
    assert o.vm.closed


@pytest.mark.parametrize('field,delta', [('row', 1), ('intended-ns', 1), ('actual-ns', -1), ('actual-ns', 32)])
def test_missing_row_order_or_late_sampling_is_rejected(video, field, delta):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    def mutate(value):
        value['frame']['rows'][100][field] += delta
        return value
    o.wire.change_video = mutate
    with pytest.raises(DebuggerError):
        o.session.video_frame_observe()
    assert o.vm.closed


def test_reused_frame_identity_cannot_change_its_frozen_bytes(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.session.video_frame_observe()
    o.wire.video['frame']['pixel-sha256'] = '0' * 64
    with pytest.raises(DebuggerError, match='same identity'):
        o.session.video_frame_observe()
    assert o.vm.closed


def test_sequence_cannot_advance_without_completed_source_rows(video):
    o = video
    o.session.video_frame_start()
    o.wire.video['frame-sequence'] = 1
    with pytest.raises(DebuggerError, match='without a completed raster'):
        o.session.video_frame_observe()
    assert o.vm.closed


def test_invalidated_stream_has_no_current_frame_and_can_be_restarted(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.session.video_frame_observe()
    o.wire.video.update(state='invalidated', reason='configuration-changed')
    o.wire.video.pop('frame')
    o.wire.video.pop('next-deadline-ns')
    invalid = o.session.video_frame_observe()
    assert invalid['frame_id'] is None and not invalid['completed_source_raster']
    with pytest.raises(ValueError, match='No completed source raster'):
        o.session.capture_video_frame()
    restarted = o.session.video_frame_start()
    assert restarted['stream_generation'] == 2 and not o.vm.closed


@pytest.mark.parametrize('change', ['same', 'stream', 'clock'])
def test_native_start_refusal_requires_unchanged_stream_and_clock(video, change):
    o = video

    def refusal():
        if change == 'stream':
            o.wire.video['stream-generation'] += 1
        elif change == 'clock':
            o.wire.receipt['virtual-ns'] += 1

    o.wire.start_refusal = refusal
    with pytest.raises(DebuggerError) as caught:
        o.session.video_frame_start()
    if change == 'same':
        assert caught.value.result['verified_refusal'] is True
        assert not o.vm.closed
        assert o.session.video_frame_observe()['state'] == 'idle'
        o.wire.start_refusal = None
        assert o.session.video_frame_start()['stream_generation'] == 1
    else:
        assert o.vm.closed


def test_explicit_stale_guard_has_no_probe_or_export_side_effect(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    for operation in (lambda: o.session.video_frame_probe([], stream='old', frame_id=1),
                      lambda: o.session.capture_video_frame(stream='old', frame_id=1)):
        with pytest.raises(ValueError, match='identity'):
            operation()
    assert not o.vm.closed
    assert not any(c in ('x-fdisbull-probe-video-frame', 'x-fdisbull-export-video-frame') for c, _ in o.wire.calls)


@pytest.mark.parametrize('invoke', [
    lambda s: s.video_frame_start(timeout_ms=True),
    lambda s: s.video_frame_probe([[320, 0]]),
    lambda s: s.video_frame_probe([[0, 200]]),
    lambda s: s.video_frame_probe([[True, 0]]),
    lambda s: s.video_frame_probe([[0, 0]] * 4097),
    lambda s: s.video_frame_probe([], stream='unpaired'),
    lambda s: s.capture_video_frame('../escape.png'),
    lambda s: s.capture_video_frame(max_bytes=True),
])
def test_bad_arguments_refuse_before_native_io(video, invoke):
    with pytest.raises(ValueError):
        invoke(video.session)
    assert not video.wire.calls and not video.vm.closed


def test_png_byte_cap_is_checked_before_artifact_publication(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    with pytest.raises(ValueError, match='image byte budget'):
        o.session.capture_video_frame(max_bytes=1)
    assert not o.vm.closed and not list(o.directory.glob('video-frame-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_native_export_hash_mismatch_cannot_become_an_artifact(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.wire.bad_export = True
    with pytest.raises(DebuggerError, match='raster hash'):
        o.session.capture_video_frame()
    assert o.vm.closed and not list(o.directory.glob('video-frame-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_probe_preserves_duplicate_point_order_and_rejects_bad_reply(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.wire.change_probe = lambda value: dict(value, pixels=list(reversed(value['pixels'])))
    with pytest.raises(DebuggerError, match='reordered'):
        o.session.video_frame_probe([[0, 0], [319, 199]])
    assert o.vm.closed


def test_clock_drift_during_passive_read_closes_owner(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    def drift():
        o.wire.counter += 1
    o.wire.after_video = drift
    with pytest.raises(DebuggerError, match='clock changed'):
        o.session.video_frame_observe()
    assert o.vm.closed


def test_one_deadline_reaches_the_actual_qmp_wire(video):
    o = video
    o.wire.latency = .03
    with pytest.raises(TimeoutError):
        o.session.video_frame_start(timeout_ms=50)
    assert o.clock.now == pytest.approx(100.05)
    assert [c for c, _ in o.wire.calls] == ['query-status', 'query-replay']
    assert o.wire.budgets == pytest.approx([.05, .02])
    assert o.vm.closed and o.wire.socket_closed


def test_precise_profile_is_required_without_starting_any_producer(video):
    o = video
    o.vm.machine_configuration['retrace_profile'] = {'profile': 'off'}
    with pytest.raises(ValueError, match='virtual/precise'):
        o.session.video_frame_start()
    assert not o.wire.calls and not o.vm.closed


def _bad_pixel(value):
    value['pixels'][-1].update(r=1, g=2, b=3)
    return value


@pytest.mark.parametrize('sequence', ['duplicate', 'overlap', 'export-first'])
def test_pixel_contradictions_cannot_share_one_frame_identity(video, sequence):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    if sequence == 'overlap':
        o.session.video_frame_probe([[7, 9]])
    elif sequence == 'export-first':
        o.session.capture_video_frame()
    o.wire.change_probe = _bad_pixel
    points = [[7, 9], [7, 9]] if sequence == 'duplicate' else [[7, 9]]
    with pytest.raises(DebuggerError, match='contradict') as raised:
        o.session.video_frame_probe(points)
    assert o.vm.closed and raised.value.result['stage'] == 'probe'
    assert raised.value.result['native']['pixels'][-1]['r'] == 1


def test_export_detects_a_previous_wrong_probe(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.wire.change_probe = _bad_pixel
    o.session.video_frame_probe([[7, 9]])
    with pytest.raises(DebuggerError, match='earlier pixel probe'):
        o.session.capture_video_frame()
    assert o.vm.closed
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_new_frame_clears_previous_pixel_cache(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.session.video_frame_probe([[7, 9]])
    o.session.capture_video_frame()
    o.wire.rgb = bytes([100, 101, 102]) * (320 * 200)
    o.wire.publish()
    assert o.session.video_frame_probe([[7, 9]])['samples'][0]['rgb'] == [100, 101, 102]
    assert not hasattr(o.vm, '_video_frame_owned_rgb')
    assert len(o.vm._video_frame_probe_samples) == 1


def test_stopped_frame_can_be_invalidated_without_resurrecting_pixels(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    o.session.video_frame_probe([[7, 9]])
    o.session.video_frame_stop()
    o.wire.video.update(state='invalidated', reason='configuration-changed')
    o.wire.video.pop('stop-ns')
    o.wire.video.pop('frame')
    observed = o.session.video_frame_observe()
    assert observed['state'] == 'invalidated' and observed['frame_id'] is None
    assert not hasattr(o.vm, '_video_frame_probe_samples')
    assert not o.vm.closed
    assert o.session.video_frame_start()['stream_generation'] == 2


def test_deferred_due_row_is_a_pending_timer_not_a_fabricated_frame(video):
    o = video
    o.session.video_frame_start()
    o.wire.video['next-deadline-ns'] = o.wire.receipt['virtual-ns'] - 1
    seen = o.session.video_frame_observe()
    assert not seen['completed_source_raster'] and not o.vm.closed


def test_exactly_four_hundred_physical_lines_is_an_admitted_extent(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    frame = o.wire.video['frame']
    frame['period-ns'] = 400 * 32
    frame['frame-start-ns'] = 25600
    for row in frame['rows']:
        row['intended-ns'] -= 6400
        row['actual-ns'] -= 6400
    for key in ('first-sample-ns', 'last-sample-ns', 'completed-ns'):
        frame[key] -= 6400
    assert o.session.video_frame_observe()['completed_source_raster']


@pytest.mark.parametrize('line', [1, 2, 3])
def test_line_period_cannot_be_shorter_than_the_native_sampling_quantum(video, line):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    frame = o.wire.video['frame']
    frame['line-period-ns'] = line
    frame['period-ns'] = 12000
    frame['frame-start-ns'] = 24000
    for row in frame['rows']:
        row['intended-ns'] = row['actual-ns'] = 24000 + 2 * line * row['row']
    frame['first-sample-ns'] = frame['rows'][0]['actual-ns']
    frame['last-sample-ns'] = frame['completed-ns'] = frame['rows'][-1]['actual-ns']
    with pytest.raises(DebuggerError, match='timing or identity'):
        o.session.video_frame_observe()


def test_stream_start_on_phase_zero_cannot_own_the_already_started_period(video):
    o = video
    o.wire.receipt['virtual-ns'] = 32000
    o.session.video_frame_start()
    o.wire.publish()
    frame = o.wire.video['frame']
    frame['frame-start-ns'] -= 32000
    for row in frame['rows']:
        row['intended-ns'] -= 32000
        row['actual-ns'] -= 32000
    for key in ('first-sample-ns', 'last-sample-ns', 'completed-ns'):
        frame[key] -= 32000
    with pytest.raises(DebuggerError, match='timing or identity'):
        o.session.video_frame_observe()


def test_lock_admission_refuses_owner_replaced_while_request_waited(video):
    o = video
    replacement = SimpleNamespace(qmp=SimpleNamespace(operation_deadline=None), closed=False)
    original_lock = o.vm.lock
    released = []
    class SwapLock:
        def acquire(self, timeout):
            o.session.vm = replacement
            return True
        def release(self):
            released.append(True)
    o.vm.lock = SwapLock()
    try:
        with pytest.raises(DebuggerError, match='owner changed while waiting'):
            o.session.video_frame_start()
        assert not o.wire.calls and not replacement.closed
        assert replacement.qmp.operation_deadline is None and released == [True]
    finally:
        o.session.vm = o.vm
        o.vm.lock = original_lock


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'directory', 'truncated', 'appended'])
def test_non_regular_or_wrong_length_export_is_refused(video, kind):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    original = o.wire.sendall
    def substituted(data):
        request = json.loads(data)
        original(data)
        if request['execute'] != 'x-fdisbull-export-video-frame':
            return
        path = Path(request['arguments']['filename'])
        raw = path.read_bytes()
        path.unlink()
        if kind == 'symlink':
            target = o.directory / 'substituted.ppm'
            target.write_bytes(raw)
            path.symlink_to(target)
        elif kind == 'fifo':
            os.mkfifo(path)
        elif kind == 'directory':
            path.mkdir()
        else:
            path.write_bytes(raw[:-1] if kind == 'truncated' else raw + b'x')
    o.wire.sendall = substituted
    with pytest.raises((DebuggerError, OSError)):
        o.session.capture_video_frame()
    assert o.vm.closed
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_png_encoding_expiry_prevents_artifact_publication(video, monkeypatch):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    original = Image.Image.save
    def slow(image, *args, **kwargs):
        result = original(image, *args, **kwargs)
        o.clock.now += .051
        return result
    monkeypatch.setattr(Image.Image, 'save', slow)
    with pytest.raises(TimeoutError) as raised:
        o.session.capture_video_frame(timeout_ms=50)
    assert o.vm.closed and raised.value.result['stage'] == 'encode'
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['observe', 'probe', 'capture'])
def test_persistence_failure_retains_received_evidence_and_committed_artifact(video, operation):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    def broken(*args, **kwargs):
        raise OSError('authored event persistence failure')
    o.session._event = broken
    invoke = {'observe': o.session.video_frame_observe,
              'probe': lambda: o.session.video_frame_probe([[7, 9]]),
              'capture': o.session.capture_video_frame}[operation]
    with pytest.raises(OSError, match='persistence failure') as raised:
        invoke()
    evidence = raised.value.result
    assert o.vm.closed and evidence['native'] is not None
    if operation == 'capture':
        assert evidence['stage'] == 'event-publication'
        identifier = evidence['artifact']['artifact']
        assert o.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()[0] == 1
    else:
        assert evidence['result']['frame_id'] == 1


def test_late_artifact_return_preserves_commit_without_starting_event_write(video):
    o = video
    o.session.video_frame_start()
    o.wire.publish()
    original = o.session._artifact
    events = []
    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        o.clock.now += .051
        return result
    o.session._artifact = slow
    o.session._event = lambda *args: events.append(args)
    with pytest.raises(TimeoutError) as raised:
        o.session.capture_video_frame(timeout_ms=50)
    assert raised.value.result['artifact']['artifact']
    assert not events and o.vm.closed
