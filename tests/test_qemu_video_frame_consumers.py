"""Bounded source consumers at the real QMP transport and public Python seam.

The peer supplies hostile protocol input, not guest cadence evidence. Pixel
expectations below are authored bytes, independent of the adapter's conversion.
"""
from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.screenshot_codecs import RGBAFrame
from test_qemu_video_frame import audio, observation, video


def prepared(o):
    o.session.video_frame_start()
    o.wire.publish()
    return o.session.video_frame_observe()


def pixel_calls(o):
    return [args for command, args in o.wire.calls if command == 'x-fdisbull-probe-video-frame']


@pytest.mark.parametrize('count,chunk_lengths', [
    (0, []), (1, [1]), (256, [256]), (257, [256, 1]), (4096, [256] * 16),
])
def test_source_probe_aggregates_one_identity_in_caller_order(video, count, chunk_lengths):
    o = video
    seen = prepared(o)
    points = [[number % 320, number // 320] for number in range(count)]
    if count > 256:
        points[256] = points[0][:]
        points[-1] = [319, 199]
    result = o.session.video_frame_probe(points, stream=seen['stream'], frame_id=seen['frame_id'])
    assert result['format'] == 'fdisbull-video-frame-probe-1'
    assert result['samples'] == [dict(x=x, y=y, rgb=[4, 85, 170]) for x, y in points]
    assert result['native'] == seen['native'] and result['frame'] == seen['frame']
    calls = pixel_calls(o)
    assert [len(call['points']) for call in calls] == chunk_lengths
    assert [[point['x'], point['y']] for call in calls for point in call['points']] == points
    assert all(call['token'] == seen['stream'] and call['frame-id'] == seen['frame_id'] for call in calls)
    assert len(getattr(o.vm, '_video_frame_probe_samples', {})) <= 256
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation="
                               "'machine-video-frame-probe'").fetchone()[0] == 1
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    assert not any(command in ('cont', 'screendump', 'x-fdisbull-export-video-frame')
                   for command, _ in o.wire.calls)


def test_zero_points_require_a_complete_raster_and_preserve_existing_pixel_knowledge(video):
    o = video
    o.session.video_frame_start()
    with pytest.raises(ValueError, match='No completed source raster'):
        o.session.video_frame_probe([])
    assert not pixel_calls(o)
    o.wire.publish()
    o.session.video_frame_probe([[7, 9]])
    known = deepcopy(o.vm._video_frame_probe_samples)
    count = len(pixel_calls(o))
    result = o.session.video_frame_probe([])
    assert result['samples'] == [] and result['completed_source_raster'] is True
    assert len(pixel_calls(o)) == count and o.vm._video_frame_probe_samples == known


@pytest.mark.parametrize('mutation', ['outer-growth', 'point-growth', 'coordinate-change'])
def test_caller_mutation_during_admission_refuses_before_any_native_read(video, mutation):
    o = video
    points = [[0, 0] for _ in range(4096)] if mutation == 'outer-growth' else [[0, 0]]
    def mutate(name):
        assert name == 'video_frame_probe'
        if mutation == 'outer-growth':
            points.append([0, 0])
        elif mutation == 'point-growth':
            points[0].append(1)
        else:
            points[0][1] = 200
    o.vm.operation_guard = mutate
    try:
        with pytest.raises(ValueError):
            o.session.video_frame_probe(points)
        assert not o.wire.calls and not o.vm.closed
    finally:
        del o.vm.operation_guard


def test_transport_callback_cannot_change_the_owned_probe_request(video):
    o = video
    prepared(o)
    points = [[0, 0], [7, 9]]
    def mutate():
        points[0][:] = [319, 199]
        points.append([320, 200])
    o.wire.after_video = mutate
    result = o.session.video_frame_probe(points)
    assert result['samples'] == [dict(x=0, y=0, rgb=[4, 85, 170]),
                                 dict(x=7, y=9, rgb=[4, 85, 170])]
    assert pixel_calls(o) == [dict(token=result['stream'], **{'frame-id': result['frame_id']},
                                   points=[dict(x=0, y=0), dict(x=7, y=9)])]


@pytest.mark.parametrize('last_chunk', [2, 16])
@pytest.mark.parametrize('change', ['pixel', 'frame'])
def test_cross_chunk_contradictions_keep_the_received_prefix_without_publication(video, last_chunk, change):
    o = video
    prepared(o)
    points = [[0, 0] for _ in range(last_chunk * 256)]
    points[0] = points[-1] = [7, 9]
    calls = 0
    def corrupt(value):
        nonlocal calls
        calls += 1
        if calls == last_chunk:
            if change == 'pixel':
                value['pixels'][-1]['r'] = 1
            else:
                value['info']['frame']['configuration-generation'] += 1
        return value
    o.wire.change_probe = corrupt
    with pytest.raises(DebuggerError) as raised:
        o.session.video_frame_probe(points)
    evidence = raised.value.result
    assert o.vm.closed and evidence['stage'] == 'probe' and evidence['result'] is None
    assert len(evidence['probe_chunks']) == last_chunk == len(pixel_calls(o))
    assert evidence['native'] == evidence['probe_chunks'][-1]
    assert evidence['probe_chunks'][0]['pixels'][0] == dict(x=7, y=9, r=4, g=85, b=170)
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation="
                               "'machine-video-frame-probe'").fetchone()[0] == 0


def test_every_probe_chunk_uses_the_original_absolute_deadline(video):
    o = video
    prepared(o)
    original = o.wire.sendall
    def delayed(data):
        original(data)
        if json.loads(data)['execute'] == 'x-fdisbull-probe-video-frame':
            o.wire.delay = .030
    o.wire.sendall = delayed
    with pytest.raises(TimeoutError) as raised:
        o.session.video_frame_probe([[7, 9]] * 4096, timeout_ms=50)
    assert o.clock.now == pytest.approx(100.050)
    assert len(pixel_calls(o)) == 2 and len(raised.value.result['probe_chunks']) == 1
    budgets = [budget for (command, _), budget in zip(o.wire.calls, o.wire.budgets, strict=True)
               if command == 'x-fdisbull-probe-video-frame']
    assert budgets == pytest.approx([.050, .020])
    assert o.vm.closed and o.wire.socket_closed


def test_replacement_owner_is_never_used_for_a_later_probe_chunk(video):
    o = video
    prepared(o)
    replacement = SimpleNamespace(qmp=SimpleNamespace(operation_deadline=None), closed=False)
    def replace(value):
        o.session.vm = replacement
        return value
    o.wire.change_probe = replace
    try:
        with pytest.raises(DebuggerError, match='owner changed') as raised:
            o.session.video_frame_probe([[7, 9]] * 257)
        assert len(pixel_calls(o)) == 1 and len(raised.value.result['probe_chunks']) == 1
        assert o.vm.closed and not replacement.closed
        assert replacement.qmp.operation_deadline is None
    finally:
        o.session.vm = o.vm


@pytest.mark.parametrize('operation,command', [
    ('probe', 'x-fdisbull-query-video-frame'),
    ('probe', 'x-fdisbull-probe-video-frame'),
    ('rgba', 'x-fdisbull-export-video-frame'),
])
def test_reply_cap_counts_received_json_whitespace_not_a_reserialized_object(video, operation, command):
    o = video
    prepared(o)
    original = o.wire.sendall
    def padded(data):
        original(data)
        if json.loads(data)['execute'] == command:
            # This is still valid JSON and deserializes to the small original
            # object. A json.dumps-based after-the-fact budget would miss it.
            o.wire.buffer[:0] = b' ' * (128 * 1024)
    o.wire.sendall = padded
    with pytest.raises(DebuggerError, match='reply exceeds budget'):
        if operation == 'probe':
            o.session.video_frame_probe([[0, 0]])
        else:
            o.session.video_frame_rgba()
    assert o.vm.closed and o.wire.socket_closed
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_aggregate_cache_remains_bounded_and_metadata_reads_do_not_expand_it(video):
    o = video
    prepared(o)
    points = [[number % 320, number // 320] for number in range(4096)]
    o.session.video_frame_probe(points)
    assert len(o.vm._video_frame_probe_samples) == 256
    assert o.vm._video_frame_probe_samples[(255, 12)] == bytes([4, 85, 170])
    assert not hasattr(o.vm, '_video_frame_owned_rgb')
    known = deepcopy(o.vm._video_frame_probe_samples)
    o.session.video_frame_probe([])
    assert o.vm._video_frame_probe_samples == known


def authored_rgb():
    return bytes([1, 2, 3]) + bytes([4, 85, 170]) * 63998 + bytes([255, 0, 128])


def authored_rgba():
    return bytes([1, 2, 3, 255]) + bytes([4, 85, 170, 255]) * 63998 + bytes([255, 0, 128, 255])


def test_rgba_is_immutable_artifact_free_and_has_separate_pixel_and_transport_hashes(video, monkeypatch):
    o = video
    o.wire.rgb = authored_rgb()
    seen = prepared(o)
    def forbidden(*args, **kwargs):
        pytest.fail('RGBA observation must not encode PNG, invoke hooks, or publish artifacts/events')
    monkeypatch.setattr(Image, 'frombytes', forbidden)
    monkeypatch.setattr(Image.Image, 'save', forbidden)
    o.session._artifact = o.session._event = forbidden
    o.session._screenshot_hook_after = forbidden
    result = o.session.video_frame_rgba(stream=seen['stream'], frame_id=seen['frame_id'])
    assert isinstance(result, RGBAFrame) and type(result.pixels) is bytes
    assert (result.width, result.height, result.stride) == (320, 200, 1280)
    assert result.pixels == authored_rgba()
    assert result.pixel(0, 0) == (1, 2, 3, 255)
    assert result.pixel(319, 199) == (255, 0, 128, 255)
    assert result.sha256 == result.metadata['raw_sha256'] == hashlib.sha256(authored_rgba()).hexdigest()
    assert result.metadata['pixel_sha256'] == hashlib.sha256(authored_rgb()).hexdigest()
    assert result.metadata['transport']['sha256'] == hashlib.sha256(b'P6\n320 200\n255\n' + authored_rgb()).hexdigest()
    assert len({result.sha256, result.metadata['pixel_sha256'], result.metadata['transport']['sha256']}) == 3
    assert result.metadata['frame'] == seen['frame'] and result.metadata['native'] == seen['native']
    assert result.metadata['legacy_phase_equivalence'] is result.metadata['application_frame_complete'] is None
    before, after = (result.metadata['clocks'][key] for key in ('before', 'after'))
    for field in ('run', 'epoch', 'virtual_ns', 'counter', 'virtual_clock'):
        assert before[field] == after[field]
    assert not list(o.directory.glob('video-frame-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    result.metadata['native']['frame']['pixel-sha256'] = '0' * 64
    assert o.vm._video_frame_last['frame']['pixel-sha256'] == hashlib.sha256(authored_rgb()).hexdigest()
    with pytest.raises(AttributeError):
        result.pixels = b''


def test_rgba_and_png_share_the_selected_rgb_without_sharing_encoding_hashes(video):
    o = video
    o.wire.rgb = authored_rgb()
    prepared(o)
    rgba = o.session.video_frame_rgba()
    capture = o.session.capture_video_frame()
    row = o.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (capture['artifact'],)).fetchone()
    data = bytes(row['data'])
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == 'RGB' and image.size == (320, 200)
        assert image.tobytes() == authored_rgb()
        assert image.convert('RGBA').tobytes() == rgba.pixels
    assert capture['metadata']['sha256'] == hashlib.sha256(data).hexdigest()
    assert capture['metadata']['pixel_sha256'] == rgba.metadata['pixel_sha256']
    assert len({rgba.sha256, rgba.metadata['pixel_sha256'], capture['metadata']['sha256']}) == 3
    assert capture['metadata']['frame'] == rgba.metadata['frame']


def test_rgba_rejects_native_rgb_mismatch_without_a_persisted_artifact(video):
    o = video
    prepared(o)
    o.wire.bad_export = True
    with pytest.raises(DebuggerError, match='raster hash') as raised:
        o.session.video_frame_rgba()
    assert raised.value.result['stage'] == 'export' and o.vm.closed
    assert not list(o.directory.glob('video-frame-*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('options', [dict(stream='unpaired'), dict(frame_id=1),
                                    dict(timeout_ms=True), dict(timeout_ms=0)])
def test_rgba_rejects_bad_declarations_before_lock_or_wire(video, options):
    attempts = []
    class Busy:
        def acquire(self, *, timeout):
            attempts.append(timeout)
            return False
    original = video.vm.lock
    video.vm.lock = Busy()
    try:
        with pytest.raises(ValueError):
            video.session.video_frame_rgba(**options)
        assert not attempts and not video.wire.calls
    finally:
        video.vm.lock = original
