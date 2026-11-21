"""One owned native witness for explicit source-frame consumers and routes.

The unchanged authored VGA guest supplies expected pixels and port-read timing.
Three sequential streams share one VM: JSON consumers, script consumers, then
an earlier real breakpoint that must suppress the next script write/capture.
FDISBULL_QEMU_CLOCK and the existing required-input policy opt into execution.
This module is not a legacy raster-phase or atomic CPU/image qualification.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import time

from PIL import Image
import pytest

from fdisbull.cli import METHODS, public_addresses, respond
from fdisbull.debug_script import OPERATIONS, execute_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.screenshot_codecs import RGBAFrame
from support.dos_process_fixture import digest
from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from test_qemu_clock_budget_native import clock_disk, clock_runtime
from test_qemu_dos_process_native import read_bytes
from test_qemu_video_frame_native import _assert_frame, _query, _timing, video_witness


WORK_SECONDS, CLEANUP_SECONDS = 60, 10
SUPERVISOR_SECONDS, OUTPUT_BYTES = 180, 256 * 1024**2
RECEIPT_BYTES, MAX_VIDEO_CALLS = 8 * 1024**2, 192
NATIVE_PROBE = 'x-fdisbull-probe-video-frame'
NATIVE_EXPORT = 'x-fdisbull-export-video-frame'
ROUTES = (
    ('video-frame-start', 'video_frame_start'),
    ('video-frame-advance', 'video_frame_advance'),
    ('video-frame-observe', 'video_frame_observe'),
    ('video-frame-probe', 'video_frame_probe'),
    ('capture-video-frame', 'capture_video_frame'),
    ('video-frame-stop', 'video_frame_stop'),
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _points():
    # All sixteen chunks contain independently chosen coordinates. Repeated
    # corner/background positions cross each chunk boundary and recur at the
    # far end; their actual coordinate order is part of the expected result.
    result = [[(number * 73 + 11) % WIDTH, (number * 37 + 3) % HEIGHT]
              for number in range(4096)]
    for chunk in range(16):
        start = chunk * 256
        result[start] = [319, 199]
        result[start + 1] = [0, 0]
        result[start + 255] = [1, 100]
    result[-1] = [0, 0]
    return result


def _samples(points, rgb):
    return [dict(x=x, y=y, rgb=list(rgb[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3]))
            for x, y in points]


def _guest_clock(clock):
    # Host observation sequence and wall timestamps are intentionally absent;
    # each exact original receipt is retained separately in the private log.
    return {name: deepcopy(clock[name]) for name in
            ('run', 'epoch', 'clock_profile', 'virtual_ns', 'counter', 'virtual_clock')}


def _stopped(debug, symbols):
    return dict(clock=_guest_clock(debug.clock_observe()), registers=debug.registers(),
                source=_query(debug), command=read_bytes(debug, symbols['command'], 1).hex(),
                mutation_count=read_bytes(debug, symbols['mutation_count'], 1).hex())


def _counts(project):
    return tuple(project.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                 for table in ('debug_artifacts', 'debug_events'))


def _screenshots(project):
    return project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0]


@contextmanager
def _owner_deadline(debug, absolute):
    vm = debug.vm
    previous = [(debug, '_rpc_deadline', getattr(debug, '_rpc_deadline', None)),
                (debug, '_deadline', getattr(debug, '_deadline', None)),
                (vm, 'operation_deadline', getattr(vm, 'operation_deadline', None))]
    previous.extend((channel, 'operation_deadline', getattr(channel, 'operation_deadline', None))
                    for channel in (vm.qmp, vm.gdb))
    bound = min([absolute, *[value for _, _, value in previous if value is not None]])
    assert time.monotonic() < bound
    for owner, field, _ in previous:
        setattr(owner, field, bound)
    try:
        yield bound
        assert debug.vm is vm and time.monotonic() < bound
    finally:
        for owner, field, value in reversed(previous):
            setattr(owner, field, value)


@contextmanager
def _observe_calls(debug, monkeypatch, evidence):
    """Observe actual calls/replies once; never supply a native result."""
    vm, qmp, remote = debug.vm, debug.vm.qmp, debug.vm.gdb
    qmp_call, execute = qmp.call, remote.execute
    video_calls, packets, delegated, writes = [], [], [], []
    evidence.update(native_video_calls=video_calls, native_execution=packets,
                    delegated_python_results=delegated, guest_write_calls=writes)

    @wraps(qmp_call)
    def query(*args, **kwargs):
        command = args[0] if args else kwargs['method']
        row = None
        if command.startswith('x-fdisbull-') and 'video-frame' in command:
            assert len(video_calls) < MAX_VIDEO_CALLS
            arguments = args[1] if len(args) > 1 else kwargs.get('arguments')
            row = dict(command=command, arguments=deepcopy(arguments),
                       max_reply_bytes=kwargs.get('max_reply_bytes'))
            video_calls.append(row)
        try:
            value = qmp_call(*args, **kwargs)
        except BaseException as error:
            if row is not None:
                row['error'] = dict(type=type(error).__name__, message=str(error))
            raise
        if row is not None:
            row['reply'] = deepcopy(value)
        return value

    @wraps(execute)
    def run(command, timeout_ms, **kwargs):
        assert len(packets) < 3, 'Unexpected guest continuation in the three-stream witness'
        row = dict(command=command, timeout_ms=timeout_ms)
        packets.append(row)
        reply, timed_out = execute(command, timeout_ms, **kwargs)
        row.update(reply=reply.decode('ascii'), timed_out=timed_out)
        return reply, timed_out

    def recorder(name):
        original = getattr(debug, name)

        @wraps(original)
        def invoke(*args, **kwargs):
            value = original(*args, **kwargs)
            delegated.append(dict(method=name, result=deepcopy(value)))
            return value

        return invoke

    original_write = debug.write_memory

    @wraps(original_write)
    def write(*args, **kwargs):
        writes.append(dict(args=list(args), kwargs=deepcopy(kwargs)))
        return original_write(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(qmp, 'call', query)
        patch.setattr(remote, 'execute', run)
        patch.setattr(debug, 'write_memory', write)
        for _, name in ROUTES:
            patch.setattr(debug, name, recorder(name))
        yield video_calls, packets, delegated, writes
        assert debug.vm is vm and vm.process.poll() is None


def _completed(debug, started, advance, schedule, expected, packet):
    assert advance['format'] == 'fdisbull-video-frame-advance-1'
    assert advance['advance_completed'] is advance['completed_source_raster'] is True
    assert advance['stop_consumed'] is True and advance['outcome'] == 'stopped'
    assert advance['baseline_frame_sequence'] == started['frame_sequence']
    assert advance['stream'] == started['stream']
    assert advance['stream_generation'] == started['stream_generation']
    native = _query(debug)
    frame = _assert_frame(native, schedule, expected)
    assert advance['frame'] == frame and native['frame-sequence'] == started['frame_sequence'] + 1
    assert packet['command'] == 'c' and packet['timed_out'] is False
    actual_stop = advance['native_result']['session']['stop_reason']
    assert actual_stop['native_reply'] == packet['reply']
    assert packet['reply'].startswith(('T02', 'S02')) and actual_stop['breakpoint_ids'] == []
    stopped_ns = advance['clocks']['after']['virtual_ns']
    assert frame['completed-ns'] <= stopped_ns < schedule['boundary'] + schedule['period_ns'] + schedule['line_ns'] // 4
    assert advance['fence']['released']['released'] is True
    assert advance['legacy_phase_equivalence'] is advance['application_frame_complete'] is advance['frame_state_equivalence'] is None
    return frame


def _probe_receipts(rows, points, observed, expected):
    chunks = [row for row in rows if row['command'] == NATIVE_PROBE]
    assert len(chunks) == 16
    sent = []
    for index, row in enumerate(chunks):
        requested = row['arguments']
        selected = points[index * 256:(index + 1) * 256]
        assert len(requested['points']) == 256
        assert requested['token'] == observed['stream'] and requested['frame-id'] == observed['frame_id']
        assert requested['points'] == [dict(x=x, y=y) for x, y in selected]
        assert row['max_reply_bytes'] == 128 * 1024
        assert row['reply']['info'] == observed['native']
        actual = row['reply']['pixels']
        assert actual == [dict(x=item['x'], y=item['y'], r=item['rgb'][0],
                               g=item['rgb'][1], b=item['rgb'][2])
                          for item in _samples(selected, expected)]
        sent.extend(requested['points'])
    assert sent == [dict(x=x, y=y) for x, y in points]


def _probe_result(result, observed, points, expected):
    assert result['format'] == 'fdisbull-video-frame-probe-1'
    assert result['completed_source_raster'] is True
    assert result['samples'] == _samples(points, expected)
    for field in ('stream', 'stream_generation', 'frame_sequence', 'frame_id',
                  'width', 'height', 'frame', 'native', 'observed_ns'):
        assert result[field] == observed[field]
    assert _guest_clock(result['clock']) == _guest_clock(observed['clock'])
    assert result['clock']['sequence'] > observed['clock']['sequence']


def _png(project, artifact, expected, frame):
    row = project.db.execute('SELECT data,sha256,kind FROM debug_artifacts WHERE id=?',
                             (artifact['artifact'],)).fetchone()
    encoded = bytes(row['data'])
    assert row['kind'] == 'screenshot' and len(encoded) <= 2 * 1024**2
    assert _sha(encoded) == row['sha256'] == artifact['sha256'] == artifact['metadata']['sha256']
    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == 'PNG' and image.mode == 'RGB' and image.size == (WIDTH, HEIGHT)
        assert image.tobytes() == expected
    metadata = artifact['metadata']
    assert metadata['source'] == 'qemu_completed_source_raster' and metadata['stopped'] is True
    assert metadata['frame'] == frame and metadata['pixel_sha256'] == _sha(expected)
    return artifact['sha256']


def _json(workspace, project, debug, delegated, operation, **params):
    before = len(delegated)
    response = respond(dict(id=before + 1, method='debug-' + operation,
        params=dict(project=str(project.path), run=debug.run_id, **params)), debugger=workspace)
    assert response['ok'] is True and len(delegated) == before + 1, response
    # Use this exact delegated invocation, never a second clock observation.
    # The established JSON projection hex-encodes DOS allocation addresses;
    # it does not change any source-frame pixel, timing or stop expectation.
    assert response['result'] == public_addresses(delegated[-1]['result'])
    if operation != 'capture-video-frame':
        suffix = {'video-frame-advance': 'advance', 'video-frame-probe': 'probe'}.get(operation, 'stream')
        assert response['result']['format'] == 'fdisbull-video-frame-' + suffix + '-1'
    assert json.loads(json.dumps(response)) == response
    return response['result']


def test_native_source_consumers_preserve_order_pixels_routes_and_first_stop(
        tmp_path, video_witness, clock_runtime, monkeypatch, record_property):
    expected, points = expected_rgb(), _points()
    assert len(points) == 4096 and len({tuple(point) for point in points}) > 256
    assert expected != expected_rgb(wrong_qemu_dac=True)
    rgba_expected = b''.join(expected[index:index + 3] + b'\xff'
                             for index in range(0, len(expected), 3))
    evidence = dict(format='fdisbull-native-source-consumers-1', success=False,
        producer_sha256=digest(clock_runtime['executable']),
        limits=dict(vm_lifetimes=1, live_owners=1, streams=3, accepted_rasters=2,
                    native_execution_calls=3, work_seconds=WORK_SECONDS,
                    cleanup_seconds=CLEANUP_SECONDS, supervisor_seconds=SUPERVISOR_SECONDS,
                    private_output_bytes=OUTPUT_BYTES, receipt_bytes=RECEIPT_BYTES),
        oracle=dict(rgb_sha256=_sha(expected), rgba_sha256=_sha(rgba_expected),
                    source='unchanged authored VGA indices/DAC and guest-read timing',
                    legacy_phase_equivalence=None, application_frame_complete=None,
                    frame_state_equivalence=None))
    workspace = DebugWorkspace()
    original_vm = process = None
    work_deadline = time.monotonic() + WORK_SECONDS
    record_property('native_owner_ceiling', 1)
    record_property('native_source_stream_ceiling', 3)
    record_property('native_consumer_producer_sha256', evidence['producer_sha256'])
    try:
        with video_witness() as (project, debug, symbols, _):
            original_vm, process = debug.vm, debug.vm.process
            evidence['native_pid'] = process.pid
            workspace.sessions[debug.run_id] = debug
            with _owner_deadline(debug, work_deadline), _observe_calls(debug, monkeypatch, evidence) as observed_calls:
                video_calls, packets, delegated, writes = observed_calls
                with output_policy_context(OutputPolicy(1024 * 1024, artifact_dir=tmp_path / 'json-output')):
                    timing = _timing(debug, symbols)
                    evidence['guest_timing'] = timing
                    before = debug.clock_observe()
                    schedule = frame_schedule(timing, before['virtual_ns'])
                    started = _json(workspace, project, debug, delegated, 'video-frame-start', timeout_ms=1000)
                    assert started['frame_id'] is None and started['state'] == 'observing'
                    assert started['observed_ns'] == before['virtual_ns']
                    advance = _json(workspace, project, debug, delegated, 'video-frame-advance', timeout_ms=5000)
                    frame = _completed(debug, started, advance, schedule, expected, packets[-1])
                    seen = _json(workspace, project, debug, delegated, 'video-frame-observe', timeout_ms=1000)
                    identity = dict(stream=seen['stream'], frame_id=seen['frame_id'])
                    assert seen['frame'] == frame and seen['completed_source_raster'] is True
                    passive = _stopped(debug, symbols)
                    mark = len(video_calls)
                    probe = _json(workspace, project, debug, delegated, 'video-frame-probe',
                                  points=points, **identity, timeout_ms=1000)
                    _probe_result(probe, seen, points, expected)
                    _probe_receipts(video_calls[mark:], points, seen, expected)
                    assert len(original_vm._video_frame_probe_samples) <= 256
                    known = deepcopy(original_vm._video_frame_probe_samples)
                    mark = len(video_calls)
                    empty = debug.video_frame_probe([], **identity, timeout_ms=1000)
                    _probe_result(empty, seen, [], expected)
                    assert not any(row['command'] == NATIVE_PROBE for row in video_calls[mark:])
                    assert original_vm._video_frame_probe_samples == known
                    counts = _counts(project)
                    rgba = debug.video_frame_rgba(**identity, timeout_ms=1000)
                    assert isinstance(rgba, RGBAFrame) and type(rgba.pixels) is bytes
                    assert (rgba.width, rgba.height, rgba.stride) == (WIDTH, HEIGHT, WIDTH * 4)
                    assert rgba.pixels == rgba_expected and rgba.pixels[3::4] == b'\xff' * (WIDTH * HEIGHT)
                    assert rgba.sha256 == rgba.metadata['sha256'] == rgba.metadata['raw_sha256'] == _sha(rgba_expected)
                    assert rgba.metadata['source'] == 'qemu_completed_source_raster' and rgba.metadata['stopped'] is True
                    assert (rgba.metadata['format'], rgba.metadata['encoding'], rgba.metadata['pixel_format']) == ('rgba', 'rgba', 'RGBA8')
                    assert rgba.metadata['stride'] == WIDTH * 4 and rgba.metadata['uncompressed_bytes'] == len(rgba_expected)
                    assert rgba.metadata['pixel_sha256'] == _sha(expected)
                    assert rgba.metadata['transport']['sha256'] == _sha(b'P6\n320 200\n255\n' + expected)
                    assert rgba.metadata['native'] == seen['native'] and rgba.metadata['frame'] == frame
                    assert _guest_clock(rgba.metadata['clocks']['before']) == _guest_clock(rgba.metadata['clocks']['after']) == passive['clock']
                    assert _counts(project) == counts and not list(Path(original_vm.temporary.name).glob('video-frame-*.ppm'))
                    assert _stopped(debug, symbols) == passive
                    with pytest.raises(AttributeError):
                        rgba.pixels = b''
                    artifact = _json(workspace, project, debug, delegated, 'capture-video-frame',
                        name='native-json-source.png', **identity, max_bytes=2 * 1024**2, timeout_ms=1000)
                    png_sha = _png(project, artifact, expected, frame)
                    assert len({rgba.sha256, _sha(expected), rgba.metadata['transport']['sha256'], png_sha}) == 4
                    assert _stopped(debug, symbols) == passive
                    stopped = _json(workspace, project, debug, delegated, 'video-frame-stop', timeout_ms=1000)
                    assert stopped['state'] == 'stopped' and stopped['frame'] == frame
                    assert _guest_clock(stopped['clock']) == passive['clock']
                    evidence['json'] = dict(schedule=schedule, observed=seen, empty_probe=empty,
                        rgba_metadata=rgba.metadata, png_artifact=artifact,
                        stopped=stopped, passive_guest_state=passive,
                        rgba_added_artifacts=0, rgba_added_events=0)

                    before_script = debug.clock_observe()
                    script_schedule = frame_schedule(timing, before_script['virtual_ns'])
                    route = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                        dict(op='video-frame-start', **{'as': 'started'}),
                        dict(op='video-frame-advance', **{'as': 'advance'}),
                        dict(op='video-frame-observe', **{'as': 'seen'}),
                        dict(op='video-frame-probe', points=points,
                             stream='$seen.stream', frame_id='$seen.frame_id'),
                        dict(op='capture-video-frame', name='native-script-source.png',
                             stream='$seen.stream', frame_id='$seen.frame_id', max_bytes=2 * 1024**2),
                        dict(op='video-frame-stop'),
                    ])
                    mark, public_mark = len(video_calls), len(delegated)
                    report = execute_script(debug, route, timeout_ms=20000)
                    evidence['script'] = dict(schedule=script_schedule, report=report)
                    assert report['ok'] is True and report['completed_steps'] == report['requested_steps'] == 6
                    values = [item['result'] for item in report['steps']]
                    assert [row['method'] for row in delegated[public_mark:]] == [name for _, name in ROUTES]
                    assert values == [row['result'] for row in delegated[public_mark:]]
                    assert all(type(value) is dict for value in values) and json.loads(json.dumps(report)) == report
                    script_started, script_advance, script_seen, script_probe, script_png, script_stop = values
                    assert all(value['format'] == 'fdisbull-video-frame-stream-1'
                               for value in (script_started, script_seen, script_stop))
                    assert script_started['observed_ns'] == before_script['virtual_ns'] and script_started['frame_id'] is None
                    second = _completed(debug, script_started, script_advance, script_schedule, expected, packets[-1])
                    assert second['frame-id'] == frame['frame-id'] + 1
                    assert script_seen['frame'] == script_stop['frame'] == second and script_stop['state'] == 'stopped'
                    assert script_seen['stream'] != seen['stream'] and script_seen['stream_generation'] == seen['stream_generation'] + 1
                    _probe_result(script_probe, script_seen, points, expected)
                    _probe_receipts(video_calls[mark:], points, script_seen, expected)
                    _png(project, script_png, expected, second)

                    stale_before, stale_counts = _stopped(debug, symbols), _counts(project)
                    mark = len(video_calls)
                    for action in (
                        lambda: debug.video_frame_probe(points[:1], **identity, timeout_ms=1000),
                        lambda: debug.video_frame_rgba(**identity, timeout_ms=1000),
                        lambda: debug.capture_video_frame('stale-source.png', **identity, timeout_ms=1000),
                    ):
                        with pytest.raises(ValueError, match='identity'):
                            action()
                    assert not any(row['command'] in (NATIVE_PROBE, NATIVE_EXPORT) for row in video_calls[mark:])
                    assert _counts(project) == stale_counts and _stopped(debug, symbols) == stale_before
                    evidence['stale_identity'] = dict(identity=identity, current_stream=script_seen['stream'],
                        refused_consumers=['probe', 'rgba', 'capture'], stopped_state=stale_before)

                    before_early = debug.clock_observe()
                    early_schedule = frame_schedule(timing, before_early['virtual_ns'])
                    third = debug.video_frame_start(timeout_ms=1000)
                    assert third['frame_id'] is None and third['frame_sequence'] == second['frame-id']
                    assert third['stream'] not in (seen['stream'], script_seen['stream'])
                    assert third['observed_ns'] == before_early['virtual_ns']
                    point = debug.breakpoint(symbols['dispatch'])
                    try:
                        assert read_bytes(debug, symbols['command'], 1) == b'\x00'
                        screenshots, public_mark, mark = _screenshots(project), len(delegated), len(video_calls)
                        failed = execute_script(debug, dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                            dict(op='video-frame-advance'),
                            dict(op='write-memory', address=symbols['command'], data_hex='01', expected_hex='00', space='physical'),
                            dict(op='capture-video-frame', name='must-not-exist.png'),
                        ]), timeout_ms=10000)
                        evidence['earlier_stop'] = dict(schedule=early_schedule, stream=third, report=failed,
                            breakpoint=point, actual_packet=deepcopy(packets[-1]))
                        assert failed['ok'] is False and failed['completed_steps'] == 0 and failed['requested_steps'] == 3
                        assert len(failed['steps']) == 1 and failed['steps'][0]['op'] == 'video-frame-advance'
                        interrupted = failed['steps'][0]['result']
                        assert delegated[public_mark:] == [dict(method='video_frame_advance', result=interrupted)]
                        assert interrupted['advance_completed'] is interrupted['completed_source_raster'] is interrupted['stop_consumed'] is False
                        assert interrupted['frame'] is None and interrupted['outcome'] == 'breakpoint'
                        native = interrupted['native_result']
                        assert native['session']['stop_reason']['native_reply'] == packets[-1]['reply']
                        assert packets[-1]['reply'].startswith(('T05', 'S05')) and packets[-1]['timed_out'] is False
                        assert native['session']['stop_reason']['breakpoint_ids'] == [point['breakpoint_id']]
                        assert int(native['registers']['linear_pc'], 16) == symbols['dispatch']
                        assert before_early['virtual_ns'] <= interrupted['clocks']['after']['virtual_ns'] < early_schedule['rows'][0]
                        assert interrupted['fence']['released']['state'] == 'cancelled' and interrupted['fence']['released']['released'] is True
                        assert read_bytes(debug, symbols['command'], 1) == b'\x00' and not writes
                        assert _screenshots(project) == screenshots
                        assert not any(row['command'] == NATIVE_EXPORT for row in video_calls[mark:])
                    finally:
                        debug.delete_breakpoint(point['breakpoint_id'])
                    final = debug.video_frame_stop(timeout_ms=1000)
                    assert final['frame_id'] is None and final['frame_sequence'] == second['frame-id']
                    assert [packet['command'] for packet in packets] == ['c', 'c', 'c']
                    assert debug.vm is original_vm and process.poll() is None
                    assert 'debug-video-frame-rgba' not in METHODS and 'video-frame-rgba' not in OPERATIONS
                    evidence.update(final_stream=final,
                                    completed_source_rasters=2, native_owners=1)
        evidence['success'] = True
    except BaseException as error:
        evidence['success'] = False
        evidence['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        workspace.sessions.clear()
        evidence['owner_reaped'] = None if process is None else process.poll() is not None
        encoded = json.dumps(evidence, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        assert len(encoded) <= RECEIPT_BYTES
        (tmp_path / 'native-source-consumers.json').write_bytes(encoded)
        if process is not None:
            assert evidence['owner_reaped']
