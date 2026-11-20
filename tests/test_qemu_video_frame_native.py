"""Independent authored acceptance for the opt-in source-row video stream.

FDISBULL_QEMU_CLOCK selects the candidate native producer; existing clock-lane
skip/required-input rules apply. The guest supplies timing registers and pixel
stimulus. Expected row deadlines/RGB never come from the candidate frame.
The declared fixed phase policy is not a DOSBox phase-equivalence assertion.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
from pathlib import Path
import uuid

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from support.dos_process_fixture import digest
from support.qemu_video_frame_fixture import (
    COMMANDS, HEIGHT, WIDTH, expected_rgb, frame_schedule, guest_video_timing,
    video_frame_program,
)
from test_qemu_clock_budget_native import (
    budget_receipt, clock_disk, clock_runtime, park,
)
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)


START = 'x-fdisbull-start-video-frame'
QUERY = 'x-fdisbull-query-video-frame'
STOP = 'x-fdisbull-stop-video-frame'
EXPORT = 'x-fdisbull-export-video-frame'
PROBE = 'x-fdisbull-probe-video-frame'
COMMAND_SET = {START, QUERY, STOP, EXPORT, PROBE}
MODEL = 'qemu-vga-chain4-scanline-v1'


@pytest.fixture
def video_witness(tmp_path, clock_runtime, clock_disk, record_property):
    serial = 0

    @contextmanager
    def launch(*, checkpoints=False, precise=True):
        nonlocal serial
        serial += 1
        directory = tmp_path / f'video-frame-{serial}'
        directory.mkdir()
        code, offsets = video_frame_program(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        record_property('authored_com_sha256', hashlib.sha256(code).hexdigest())
        record_property('video_oracle', 'guest-read VGA timing; row-owned DAC6 bit replication')
        record_property('legacy_phase_equivalence', 'not qualified by this native source-stream test')
        debug, owners = None, []
        extra = {'qemu_checkpoint_tool': str(_checkpoint_tool())} if checkpoints else {}
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                qemu_clock='virtual',
                                qemu_retrace='precise' if precise else 'standard',
                                **extra)) as debug:
                        owners.append(debug.vm.process)
                        assert COMMAND_SET <= set(debug.vm.qmp_commands)
                        info = process_record(debug)
                        symbols = {name: com_address(info, offset)
                                   for name, offset in offsets.items()}
                        park(debug, symbols['ready'])
                        yield project, debug, symbols, owners
                finally:
                    if debug is not None:
                        owners.append(debug.vm.process)
                        assert all(owner.poll() is not None for owner in owners)
                        record_property('owners_reaped', len({id(owner) for owner in owners}))
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def _query(debug):
    info = debug.vm.qmp.call(QUERY)
    assert info['api-version'] == 1 and info['model'] == MODEL
    assert info['state'] in ('idle', 'observing', 'stopped', 'invalidated')
    for name in ('epoch', 'virtual-ns', 'stream-generation', 'frame-sequence',
                 'aborted-frames', 'rows-sampled'):
        assert type(info[name]) is int and info[name] >= 0, (name, info)
    assert type(info['in-progress']) is bool
    return info


def _timing(debug, symbols):
    return guest_video_timing(read_bytes(debug, symbols['timing_raw'], 11))


def _start(debug, symbols):
    timing = _timing(debug, symbols)
    before = debug.clock_observe()
    token = uuid.uuid4().hex
    native = debug.vm.qmp.call(START, {'token': token})
    assert native['state'] == 'observing' and native['token'] == token
    assert native.get('frame') is None and native['rows-sampled'] == 0
    assert native['virtual-ns'] == native['start-ns'] == before['virtual_ns']
    return native, frame_schedule(timing, before['virtual_ns'])


def _advance_to(debug, target_ns):
    before = debug.clock_observe()
    delta = target_ns - before['virtual_ns']
    assert delta > 0, (target_ns, before)
    budget_receipt(debug.clock_advance(delta, timeout_ms=5000), delta, before=before)
    return debug.clock_observe()


def _complete(debug, schedule):
    # A half physical line after the final source-row deadline is still well
    # before the next raster. No candidate completion timestamp drives the run.
    _advance_to(debug, schedule['rows'][-1] + schedule['line_ns'] // 2)
    return _query(debug)


def _later(schedule, count=1):
    delta = count * schedule['period_ns']
    return dict(schedule, boundary=schedule['boundary'] + delta,
                rows=tuple(value + delta for value in schedule['rows']))


def _command(debug, symbols, name):
    value, fence = COMMANDS[name]
    assert read_bytes(debug, symbols['command'], 1) == b'\x00'
    before = debug.clock_observe()
    debug.write_memory(symbols['command'], bytes([value]).hex(), expected_hex='00')
    park(debug, symbols[fence])
    assert read_bytes(debug, symbols['command'], 1) == b'\x00'
    after = debug.clock_observe()
    return before, after


def _assert_frame(info, schedule, expected):
    frame = info['frame']
    assert frame['frame-id'] == info['frame-sequence'] > 0
    assert frame['epoch'] == info['epoch']
    assert frame['stream-generation'] == info['stream-generation']
    assert frame['configuration-generation'] > 0 and frame['timing-generation'] > 0
    assert (frame['width'], frame['height'], frame['stride']) == (WIDTH, HEIGHT, WIDTH * 3)
    assert frame['pixel-format'] == 'RGB888'
    assert frame['dac-conversion'] == 'replicate-6-to-8-v1' and frame['dac-8bit'] is False
    assert frame['frame-start-ns'] == schedule['boundary']
    assert frame['period-ns'] == schedule['period_ns']
    assert frame['line-period-ns'] == schedule['line_ns']
    assert frame['pixel-sha256'] == hashlib.sha256(expected).hexdigest()
    assert len(frame['rows']) == HEIGHT
    for row, (sample, deadline) in enumerate(zip(frame['rows'], schedule['rows'], strict=True)):
        assert sample['row'] == row and sample['intended-ns'] == deadline
        assert deadline <= sample['actual-ns'] < deadline + schedule['line_ns']
    assert frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
    assert frame['last-sample-ns'] == frame['rows'][-1]['actual-ns']
    assert frame['last-sample-ns'] <= frame['completed-ns'] <= info['virtual-ns']
    return frame


def _clock_equal(before, after):
    assert all(before[name] == after[name]
               for name in ('run', 'epoch', 'virtual_ns', 'counter'))


def _export(debug, info, *, token=None, frame_id=None):
    path = Path(debug.vm.temporary.name) / ('video-oracle-' + uuid.uuid4().hex + '.ppm')
    selected = info['frame']
    try:
        returned = debug.vm.qmp.call(EXPORT, {
            'token': info['token'] if token is None else token,
            'frame-id': selected['frame-id'] if frame_id is None else frame_id,
            'filename': str(path),
        })
        assert returned == info
        raw = path.read_bytes()
        header = f'P6\n{WIDTH} {HEIGHT}\n255\n'.encode('ascii')
        assert raw.startswith(header) and len(raw) == len(header) + WIDTH * HEIGHT * 3
        return raw[len(header):]
    finally:
        path.unlink(missing_ok=True)


def _passive(project, debug, expected):
    before, registers = debug.clock_observe(), debug.registers()
    artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    info = _query(debug)
    assert _query(debug) == info
    assert _export(debug, info) == _export(debug, info) == expected
    points = [(319, 199), (0, 0), (1, 99), (1, 100), (1, 199), (1, 100)]
    probe = debug.vm.qmp.call(PROBE, {
        'token': info['token'], 'frame-id': info['frame']['frame-id'],
        'points': [dict(x=x, y=y) for x, y in points],
    })
    assert probe['info'] == info
    assert len(probe['pixels']) == len(points)
    for (x, y), sample in zip(points, probe['pixels'], strict=True):
        offset = (y * WIDTH + x) * 3
        assert sample == dict(x=x, y=y, r=expected[offset],
                              g=expected[offset + 1], b=expected[offset + 2])
    assert _query(debug) == info
    _clock_equal(before, debug.clock_observe())
    assert debug.registers() == registers
    assert artifacts == project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    return info


def _refuses_export(debug, token, frame_id):
    path = Path(debug.vm.temporary.name) / ('refused-video-' + uuid.uuid4().hex + '.ppm')
    try:
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(EXPORT, dict(token=token, **{'frame-id': frame_id}, filename=str(path)))
        assert not path.exists(), 'A refused frame identity created a destination'
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(PROBE, dict(token=token, **{'frame-id': frame_id}, points=[]))
    finally:
        path.unlink(missing_ok=True)


def test_authored_video_oracle_discriminates_dac_and_final_snapshot():
    old, mixed = expected_rgb(), expected_rgb(split_row=100, changed_vram=True)
    assert old[3:6] == bytes((4, 85, 170))
    assert mixed[(100 * WIDTH + 1) * 3:(100 * WIDTH + 2) * 3] == bytes((170, 85, 4))
    assert mixed != expected_rgb(split_row=0, changed_vram=True)
    assert mixed != expected_rgb(split_row=100, changed_vram=True, wrong_qemu_dac=True)
    assert mixed != expected_rgb(split_row=99, changed_vram=True)
    assert mixed != expected_rgb(split_row=101, changed_vram=True)


def test_native_unchanged_rasters_advance_and_stopped_readback_is_passive(video_witness):
    with video_witness() as (project, debug, symbols, _):
        initial = _query(debug)
        assert initial['state'] == 'idle' and initial.get('frame') is None
        started, schedule = _start(debug, symbols)
        first = _complete(debug, schedule)
        _assert_frame(first, schedule, expected_rgb())
        assert first['frame-sequence'] == started['frame-sequence'] + 1
        _passive(project, debug, expected_rgb())
        second_schedule = _later(schedule)
        second = _complete(debug, second_schedule)
        _assert_frame(second, second_schedule, expected_rgb())
        assert second['frame-sequence'] == first['frame-sequence'] + 1
        assert second['frame']['pixel-sha256'] == first['frame']['pixel-sha256']
        _passive(project, debug, expected_rgb())
        before = debug.clock_observe()
        _refuses_export(debug, first['token'], first['frame']['frame-id'])
        _refuses_export(debug, uuid.uuid4().hex, second['frame']['frame-id'])
        _clock_equal(before, debug.clock_observe())


def test_native_row_time_palette_and_vram_defeat_final_snapshot(video_witness):
    with video_witness() as (project, debug, symbols, _):
        _, schedule = _start(debug, symbols)
        split = 100
        previous, following = schedule['rows'][split - 1:split + 1]
        _advance_to(debug, following - schedule['line_ns'] // 2)
        partial = _query(debug)
        assert partial['in-progress'] and partial['rows-sampled'] == split
        before, after = _command(debug, symbols, 'mutate')
        assert previous < before['virtual_ns'] <= after['virtual_ns'] < following, (before, after, schedule)
        assert read_bytes(debug, symbols['mutation_count'], 1) == b'\x01'
        assert _query(debug)['rows-sampled'] == split
        expected = expected_rgb(split_row=split, changed_vram=True)
        completed = _complete(debug, schedule)
        _assert_frame(completed, schedule, expected)
        actual = _export(debug, completed)
        assert actual == expected
        assert actual != expected_rgb(split_row=0, changed_vram=True), 'End-of-frame VRAM/DAC snapshot accepted'
        assert actual != expected_rgb(split_row=split, changed_vram=True, wrong_qemu_dac=True)
        _passive(project, debug, expected)
        next_schedule = _later(schedule)
        later = _complete(debug, next_schedule)
        _assert_frame(later, next_schedule, expected_rgb(split_row=0, changed_vram=True))


def test_native_partial_geometry_blank_panning_and_aba_are_refused(video_witness):
    with video_witness() as (project, debug, symbols, _):
        cases = [('invalid_text', 'restore'), ('blank', 'enable'),
                 ('panning', 'unpan'), ('page_aba', None)]
        prior_generation = 0
        for mutation, recovery in cases:
            started, schedule = _start(debug, symbols)
            assert started['stream-generation'] > prior_generation
            prior_generation = started['stream-generation']
            baseline = _complete(debug, schedule)
            next_schedule = _later(schedule)
            _advance_to(debug, next_schedule['rows'][100] - schedule['line_ns'] // 2)
            partial = _query(debug)
            assert partial['in-progress'] and partial['rows-sampled'] == 100
            _command(debug, symbols, mutation)
            # Mutations are guest instructions; give the next native row one
            # bounded opportunity to notice incompatible or ABA configuration.
            now = debug.clock_observe()['virtual_ns']
            _advance_to(debug, now + schedule['line_ns'] * 3)
            invalid = _query(debug)
            assert invalid['state'] == 'invalidated' and invalid['reason']
            assert invalid.get('frame') is None and not invalid['in-progress']
            assert invalid['frame-sequence'] == baseline['frame-sequence']
            assert invalid['aborted-frames'] > partial['aborted-frames']
            _refuses_export(debug, baseline['token'], baseline['frame']['frame-id'])
            if mutation == 'page_aba':
                assert read_bytes(debug, symbols['page_before'], 1) == read_bytes(debug, symbols['page_after'], 1)
            if recovery is not None:
                _command(debug, symbols, recovery)
            restarted, recovery_schedule = _start(debug, symbols)
            assert restarted['token'] != started['token']
            assert restarted['stream-generation'] > prior_generation
            prior_generation = restarted['stream-generation']
            recovered = _complete(debug, recovery_schedule)
            _assert_frame(recovered, recovery_schedule, expected_rgb())
            _passive(project, debug, expected_rgb())
            debug.vm.qmp.call(STOP, {'token': restarted['token']})


def test_native_stop_discards_partial_and_restart_cannot_borrow_identity(video_witness):
    with video_witness() as (project, debug, symbols, _):
        started, schedule = _start(debug, symbols)
        baseline = _complete(debug, schedule)
        next_schedule = _later(schedule)
        _advance_to(debug, next_schedule['rows'][50] - schedule['line_ns'] // 2)
        partial = _query(debug)
        assert partial['in-progress'] and partial['rows-sampled'] == 50
        stopped = debug.vm.qmp.call(STOP, {'token': started['token']})
        assert stopped['state'] == 'stopped' and not stopped['in-progress']
        assert stopped['frame'] == baseline['frame']
        _passive(project, debug, expected_rgb())
        _advance_to(debug, debug.clock_observe()['virtual_ns'] + schedule['period_ns'] * 2)
        later = _query(debug)
        assert later['state'] == 'stopped' and later['frame'] == baseline['frame']
        assert later['frame-sequence'] == baseline['frame-sequence']
        restarted, fresh_schedule = _start(debug, symbols)
        assert restarted['stream-generation'] > started['stream-generation']
        assert restarted['token'] != started['token'] and restarted.get('frame') is None
        _refuses_export(debug, started['token'], baseline['frame']['frame-id'])
        fresh = _complete(debug, fresh_schedule)
        assert fresh['frame-sequence'] == baseline['frame-sequence'] + 1
        _assert_frame(fresh, fresh_schedule, expected_rgb())


def test_native_machine_restore_invalidates_old_live_stream(video_witness):
    with video_witness(checkpoints=True) as (project, debug, symbols, owners):
        started, schedule = _start(debug, symbols)
        baseline = _complete(debug, schedule)
        saved = debug.save_machine_state()
        _command(debug, symbols, 'mutate')
        assert read_bytes(debug, symbols['mutation_count'], 1) == b'\x01'
        owner = debug.vm
        restored = debug.load_machine_state(saved['artifact'])
        owners.append(debug.vm.process)
        assert restored['machine_state_restored'] and debug.vm is not owner
        assert owner.process.poll() is not None
        assert read_bytes(debug, symbols['mutation_count'], 1) == b'\x00'
        empty = _query(debug)
        assert empty['epoch'] != baseline['epoch'] and empty.get('frame') is None
        assert empty['state'] in ('idle', 'invalidated') and not empty['in-progress']
        _refuses_export(debug, started['token'], baseline['frame']['frame-id'])
        _, fresh_schedule = _start(debug, symbols)
        fresh = _complete(debug, fresh_schedule)
        _assert_frame(fresh, fresh_schedule, expected_rgb())
        _passive(project, debug, expected_rgb())


def test_native_public_video_frame_probe_and_capture_match_source_rgb(video_witness):
    with video_witness() as (project, debug, symbols, _):
        timing = _timing(debug, symbols)
        before = debug.clock_observe()
        started = debug.video_frame_start(timeout_ms=1000)
        assert started['format'] == 'fdisbull-video-frame-stream-1'
        assert started['state'] == 'observing' and started['frame_id'] is None
        schedule = frame_schedule(timing, before['virtual_ns'])
        native = _complete(debug, schedule)
        frame = _assert_frame(native, schedule, expected_rgb())
        observed = debug.video_frame_observe(timeout_ms=1000)
        assert observed['frame'] == frame and observed['native'] == native
        assert observed['completed_source_raster'] is True
        assert observed['legacy_phase_equivalence'] is None
        assert observed['application_frame_complete'] is None
        stream, frame_id = observed['stream'], observed['frame_id']
        points = [[0, 0], [1, 100], [319, 199], [1, 100]]
        probe = debug.video_frame_probe(points, stream=stream, frame_id=frame_id, timeout_ms=1000)
        expected = expected_rgb()
        assert probe['format'] == 'fdisbull-video-frame-probe-1' and probe['frame_id'] == frame_id
        assert probe['samples'] == [dict(x=x, y=y, rgb=list(expected[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3]))
                                    for x, y in points]
        before_capture, registers = debug.clock_observe(), debug.registers()
        artifact = debug.capture_video_frame('source-rows.png', stream=stream, frame_id=frame_id, timeout_ms=1000)
        row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',
                                 (artifact['artifact'],)).fetchone()
        raw = bytes(row['data'])
        assert hashlib.sha256(raw).hexdigest() == row['sha256'] == artifact['sha256']
        with Image.open(io.BytesIO(raw)) as image:
            assert image.format == 'PNG' and image.size == (WIDTH, HEIGHT)
            assert image.convert('RGB').tobytes() == expected
        metadata = artifact['metadata']
        assert metadata['source'] == 'qemu_completed_source_raster'
        assert metadata['pixel_sha256'] == hashlib.sha256(expected).hexdigest()
        assert metadata['stream'] == stream and metadata['frame_id'] == frame_id
        assert metadata['frame'] == frame and metadata['stopped'] is True
        _clock_equal(before_capture, debug.clock_observe())
        assert debug.registers() == registers
        assert debug.video_frame_stop(timeout_ms=1000)['state'] == 'stopped'


def test_native_video_start_requires_explicit_precise_retrace(video_witness):
    with video_witness(precise=False) as (_, debug, _, _):
        before = debug.clock_observe()
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(START, {'token': uuid.uuid4().hex})
        _clock_equal(before, debug.clock_observe())
