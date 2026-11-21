"""One owned native scheduler witness for ordinary source-state refusal.

The separately admitted controller supplies the producer pin and prebuilt
COM/baseline. This case neither assembles a guest nor prepares DOS media.
One native arm and explicit cancellation leave genuine Python input bookkeeping
empty; the ordinary observer must retain and refuse both actual receipts.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import struct
import time
import uuid

import pytest

from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
from fdisbull.qemu_video_frame_state import (
    FORMAT, INPUT_PROFILE, VIDEO_FRAME_STATE_COMMANDS, VideoFrameStateRefusal,
)
from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_video_frame_native import _assert_frame, _query, _timing
from test_qemu_video_frame_state_native import (
    COM_SHA256, FOOTER_NAMES, FOOTER_VALUES, MAX_NATIVE_CALLS, MAX_VIDEO_CALLS,
    OUTPUT_BYTES, SUPERVISOR_SECONDS, _sha, _digest, _clock, _counts, _owner,
    _current, _identity, _deadline, _record_calls, _host_neutral,
    _keyboard_neutral, _observation, _close_original,
)


WORK_SECONDS, CLEANUP_SECONDS = 60, 10
RECEIPT_BYTES = 2 * 1024**2
INPUT_DELAY_NS = 1_000_000_000
BASELINE_SHA256 = '7943e405080eafdab19c32164e8c4a90946e2b4e95ca60bb3950d09b73572daf'
NATIVE_FORMAT = 'fdisbull-native-input-schedule-observation-1'
ARM_INPUT = 'x-fdisbull-arm-input'
CANCEL_INPUT = 'x-fdisbull-cancel-input'
QUERY_INPUT = 'x-fdisbull-query-input'
QUERY_KEYS = 'x-fdisbull-query-frame-keys'
QUERY_VIDEO = 'x-fdisbull-query-video-frame'
EXPORT = 'x-fdisbull-export-video-frame'
REFUSAL_COMMANDS = ['query-status', 'query-status', 'query-replay',
                    'x-fdisbull-query-clock', QUERY_INPUT]
HEALTH_COMMANDS = ['query-status', QUERY_INPUT, QUERY_KEYS,
                   'x-fdisbull-query-clock', 'query-replay',
                   'human-monitor-command', QUERY_VIDEO]


def _inputs(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_INPUT_SCHEDULE_OBSERVATION') != '1':
        pytest.skip('Native scheduler observation requires its separately admitted owner controller')
    config = request.config
    assert getattr(config, '_fdisbull_input_schedule_observation_owned_gate', None) == (
        'fdisbull-input-schedule-observation-owned-gate-1')
    assert callable(getattr(config, '_fdisbull_input_schedule_observation_post_setup', None))
    producer_sha = getattr(config, '_fdisbull_input_schedule_observation_producer_sha256', None)
    assert type(producer_sha) is str and re.fullmatch('[0-9a-f]{64}', producer_sha)
    names = dict(executable='FDISBULL_QEMU_CLOCK', firmware='FDISBULL_QEMU_CLOCK_FIRMWARE',
        mcopy='FDISBULL_QEMU_DOS_MCOPY', com='FDISBULL_INPUT_SCHEDULE_OBSERVATION_COM',
        baseline='FDISBULL_INPUT_SCHEDULE_OBSERVATION_BASELINE')
    assert all(os.environ.get(name) for name in names.values())
    paths = {}
    for key, name in names.items():
        path = Path(os.environ[name]).expanduser()
        # The mtools multicall executable must retain its mcopy invocation name.
        paths[key] = path.absolute() if key == 'mcopy' else path.resolve(strict=True)
    assert paths['firmware'].is_dir()
    for key in ('executable', 'mcopy', 'com', 'baseline'):
        assert paths[key].is_file() and paths[key].stat().st_size <= 64 * 1024**2
    assert all(os.access(paths[key], os.X_OK) for key in ('executable', 'mcopy'))
    code = paths['com'].read_bytes()
    assert len(code) == 503 and _sha(code) == COM_SHA256 and code[-34:-30] == b'VFR1'
    offsets = struct.unpack('<15H', code[-30:])
    assert offsets == FOOTER_VALUES
    assert paths['baseline'].stat().st_size == 1474560
    assert _digest(paths['baseline']) == BASELINE_SHA256
    assert _digest(paths['executable']) == producer_sha
    pins = {key: dict(path=str(path), bytes=path.stat().st_size, sha256=_digest(path))
            for key, path in paths.items() if key != 'firmware'}
    pins['firmware'] = dict(path=str(paths['firmware']), controller_manifest_required=True)
    runtime = {key: paths[key] for key in ('executable', 'mcopy')}
    runtime['firmware'] = str(paths['firmware'])
    disk = dict(image=paths['baseline'], prepared_sha256=BASELINE_SHA256)
    return paths, runtime, disk, code, dict(zip(FOOTER_NAMES, offsets, strict=True)), pins


def test_native_input_schedule_refuses_armed_and_cancelled_source_state_observation(
        tmp_path, request, monkeypatch, record_property):
    started_at = time.monotonic()
    paths, runtime, disk, code, offsets, pins = _inputs(request)
    expected = expected_rgb()
    pixel_sha = _sha(expected)
    assert len(expected) == WIDTH * HEIGHT * 3
    directory = tmp_path / 'input-schedule-observation'
    directory.mkdir()
    assert not any((parent / '.git').exists() for parent in (directory, *directory.parents))
    receipt_path = tmp_path / 'native-input-schedule-observation.json'
    evidence = dict(format=NATIVE_FORMAT, success=False, inputs=pins, setup={},
        observations=[], transitions={}, refusals=[], health=[],
        native_calls=dict(scope='post-setup; controller journal also covers bootstrap', records=[]),
        post_setup_execution=[], owner_reaped=False,
        limits=dict(work_seconds=WORK_SECONDS, cleanup_seconds=CLEANUP_SECONDS,
            supervisor_seconds=SUPERVISOR_SECONDS, private_output_bytes=OUTPUT_BYTES,
            receipt_bytes=RECEIPT_BYTES, max_native_calls=MAX_NATIVE_CALLS,
            max_video_calls=MAX_VIDEO_CALLS, owners=1, streams=1, completed_rasters=1,
            successful_observations=1, refused_observations=2, post_setup_continues=1,
            exports=1, native_schedule_arms=1, native_schedule_cancels=1,
            scheduled_events=1, dispatched_events=0, guest_write_bytes=0,
            native_control_arms=0, raw_packets=0, health_blocks=2,
            health_qmp_reads_per_block=7, health_register_reads_per_block=1,
            health_ram_bytes_per_block=2),
        unknown=dict(atomic=False, native_mutation_revision=None,
            whole_machine_revision=None, completed_guest_frames=False,
            legacy_phase_equivalence=None, application_frame_complete=None,
            guest_input_consumed=None, all_devices_neutral=None,
            raw_handles_covered=False, independent_controllers_covered=False))
    debug = owner = project = binary = None
    primary = None
    body_complete = False
    try:
        binary, project = create_project(directory, code)
        debug = project.debugger(runtime['executable'], directory,
            **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise'))
        owner = _owner(debug)
        vm, qmp, remote = owner['vm'], owner['qmp'], owner['gdb']
        authority = vm.observation_authority
        assert remote is not None and remote.register_description
        assert VIDEO_FRAME_STATE_COMMANDS | INPUT_SCHEDULE_COMMANDS <= set(vm.qmp_commands)
        assert debug.capabilities['virtual_input_schedule'] is True
        assert debug.capabilities['completed_guest_frames'] is False
        with _deadline(debug, owner, started_at + WORK_SECONDS):
            info = process_record(debug)
            symbols = {name: com_address(info, offset) for name, offset in offsets.items()}
            baseline_breakpoints = deepcopy(debug.breakpoints)
            return_breakpoint = debug._return_breakpoint
            parked = park(debug, symbols['ready'])
            assert debug.breakpoints == baseline_breakpoints
            assert debug._return_breakpoint == return_breakpoint
            with _record_calls(debug, owner, monkeypatch, evidence) as calls:
                request.config._fdisbull_input_schedule_observation_post_setup(vm)
                evidence['owner_start'] = _identity(debug, owner)
                evidence['setup'].update(process=info, symbols=symbols, parked=parked,
                    breakpoints=baseline_breakpoints, return_breakpoint=return_breakpoint,
                    prebuilt_com=True, baseline_prepared_before_case=True,
                    oracle=dict(pixel_sha256=pixel_sha, rgb_bytes=len(expected),
                        method='authored VGA indices/DAC6 bit replication plus guest-read timing'))
                timing = _timing(debug, symbols)
                before = debug.clock_observe()
                schedule = frame_schedule(timing, before['virtual_ns'])
                stream = debug.video_frame_start(timeout_ms=1000)
                advance = debug.video_frame_advance(timeout_ms=5000)
                native = _query(debug)
                frame = _assert_frame(native, schedule, expected)
                evidence['setup'].update(schedule=schedule, stream=stream, advance=advance,
                    source=native)
                assert advance['advance_completed'] is advance['completed_source_raster'] is True
                assert advance['stop_consumed'] is True and advance['outcome'] == 'stopped'
                assert advance['stream'] == stream['stream'] == native['token']
                assert advance['stream_generation'] == stream['stream_generation']
                assert advance['baseline_frame_sequence'] == stream['frame_sequence']
                assert advance['frame'] == frame
                assert native['frame-sequence'] == stream['frame_sequence'] + 1
                assert advance['fence']['released']['released'] is True
                packet, = [row for row in calls if row['protocol'] == 'gdb.execute']
                raw_stop = bytes.fromhex(packet['result_hex']).decode('ascii')
                assert packet['command'] == 'c' and packet['timed_out'] is False
                stop = advance['native_result']['session']['stop_reason']
                assert stop['native_reply'] == raw_stop and raw_stop.startswith(('T02', 'S02'))
                assert stop['breakpoint_ids'] == []
                stopped_ns = advance['clocks']['after']['virtual_ns']
                assert frame['completed-ns'] <= stopped_ns < (
                    schedule['boundary'] + schedule['period_ns'] + schedule['line_ns'] // 4)
                assert read_bytes(debug, symbols['command'], 1) == b'\0'
                assert read_bytes(debug, symbols['mutation_count'], 1) == b'\0'
                address = symbols['page_before']
                assert symbols['page_after'] == address + 1
                options = dict(ram_ranges=[dict(address=address, length=2)],
                    stream=stream['stream'], frame_id=frame['frame-id'], timeout_ms=2000)
                counts, baseline_begin = _counts(project), len(calls)
                first = debug.video_frame_state_observe(**options)
                evidence['observations'].append(first)
                _observation(first, native, address, b'\0\0', pixel_sha)
                assert 'native_control' not in first
                assert _counts(project) == counts
                assert not list(Path(owner['temporary'].name).glob('video-frame-*.ppm'))
                assert sum(row['protocol'] == 'qmp' and row['command'] == EXPORT
                           for row in calls[baseline_begin:]) == 1
                evidence['setup']['baseline_calls'] = dict(begin=baseline_begin, end=len(calls))

                # Capture the existing bookkeeping without creating, clearing,
                # replacing or reconciling it with the out-of-band native arm.
                host_present = hasattr(vm, '_physical_input')
                host_storage = getattr(vm, '_physical_input', None)
                host_snapshot = deepcopy(host_storage)
                evidence['setup']['host_input'] = dict(present=host_present,
                    object_id=id(host_storage) if host_storage is not None else None,
                    state=deepcopy(host_snapshot), frame_key_owner=None)

                def host_unchanged():
                    assert hasattr(vm, '_physical_input') == host_present
                    assert getattr(vm, '_physical_input', None) is host_storage
                    assert host_storage == host_snapshot
                    if host_storage is not None:
                        assert host_storage['valid'] is True
                        assert host_storage['pending'] == [] and host_storage['leases'] == {}
                        assert host_storage.get('schedule') is host_storage.get('schedule_receipt') is None
                        assert host_storage.get('last_delivery') is None
                        assert host_storage['sequence'] == 0
                    assert getattr(vm, '_frame_key_owner', None) is None
                    assert not getattr(vm, '_physical_input_closed', False)
                    assert not getattr(vm, '_fdisbull_control_quarantine', None)

                def healthy_owner():
                    _current(debug, owner)
                    host_unchanged()
                    assert authority._active is None and authority._cleanup_owner is None
                    assert not authority._stack
                    assert debug.breakpoints == baseline_breakpoints
                    assert debug._return_breakpoint == return_breakpoint
                    assert _identity(debug, owner) == evidence['owner_start']

                def refuse(expected_schedule):
                    healthy_owner()
                    begin = len(calls)
                    with pytest.raises(VideoFrameStateRefusal) as caught:
                        debug.video_frame_state_observe(**options)
                    end = len(calls)
                    error = caught.value
                    refusal = getattr(error, 'video_frame_state_evidence', None)
                    if refusal is None:
                        refusal = error.result
                    evidence['refusals'].append(dict(code=error.code, evidence=deepcopy(refusal),
                        native_call_begin=begin, native_call_end=end))
                    assert error.code == 'native_schedule_not_initial'
                    assert refusal['format'] == FORMAT and refusal['complete'] is False
                    assert refusal['stage'] == 'input-before' and len(refusal['issues']) == 1
                    assert refusal['issues'][0]['code'] == error.code
                    assert refusal['issues'][0]['stage'] == 'input-before'
                    assert refusal['source'] is None and refusal['state_before'] == refusal['state_after'] == {}
                    assert 'native_control' not in refusal and refusal['atomic'] is False
                    assert all(refusal[key] is None for key in ('native_mutation_revision',
                        'application_frame_complete', 'frame_state_equivalence', 'legacy_phase_equivalence'))
                    assert refusal['input']['profile'] == INPUT_PROFILE
                    assert set(refusal['input']['before']) == {'host', 'schedule'}
                    assert refusal['input']['before']['schedule'] == expected_schedule
                    assert refusal['input']['before']['host'] == first['input']['before']['host']
                    _host_neutral(refusal['input']['before']['host'])
                    assert refusal['input']['after'] == {} and refusal['clocks']['after'] is None
                    assert all(refusal['input'][key] is None for key in
                               ('mouse_state', 'all_devices_neutral', 'guest_consumed'))
                    assert _clock(refusal['clocks']['before']) == _clock(first['clocks']['before'])
                    assert refusal['status_before'] == first['status_before']
                    observed_authority = refusal['authority']
                    assert observed_authority['valid'] is True and observed_authority['complete'] is False
                    assert observed_authority['invalidation_reason'] is None
                    assert observed_authority['events'] == []
                    assert observed_authority['control_generation_before'] == observed_authority['control_generation_after']
                    refused_calls = calls[begin:end]
                    assert all(row['protocol'] == 'qmp' for row in refused_calls)
                    assert [row['command'] for row in refused_calls] == REFUSAL_COMMANDS
                    assert all('error' not in row for row in refused_calls)
                    assert _counts(project) == counts
                    assert not list(Path(owner['temporary'].name).glob('video-frame-*.ppm'))
                    healthy_owner()

                def health(expected_schedule):
                    healthy_owner()
                    begin = len(calls)
                    with owner['lock']:
                        status = qmp.call('query-status')
                        input_state = qmp.call(QUERY_INPUT)
                        keyboard = qmp.call(QUERY_KEYS)
                        clock = qmp.call('x-fdisbull-query-clock')
                        counter = qmp.call('query-replay')
                        registers = remote.registers()
                        ram = remote.memory(address, 2, space='physical')
                        monitor = qmp.call('human-monitor-command', {'command-line': 'info registers'})
                        source = qmp.call(QUERY_VIDEO)
                    evidence['health'].append(dict(schedule=input_state, keyboard=keyboard,
                        status=status, clock=clock, counter=counter, registers=registers,
                        ram=dict(address=address, length=2, space='physical', data_hex=ram.hex(),
                                 sha256=_sha(ram)), monitor=monitor, source=source,
                        native_call_begin=begin, native_call_end=len(calls),
                        owner=_identity(debug, owner)))
                    assert status == first['status_before'] and status['running'] is False
                    assert input_state == expected_schedule and 'dispatch-ns' not in input_state
                    assert keyboard == first['input']['before']['keyboard']
                    _keyboard_neutral(keyboard)
                    assert clock == first['clocks']['before']['virtual_clock']['native']
                    assert counter == first['clocks']['before']['counter']['native']
                    assert registers == first['state_before']['registers']
                    assert evidence['health'][-1]['ram'] == first['state_before']['ram'][0]
                    assert monitor == first['state_before']['monitor']
                    assert source == native
                    rows = calls[begin:]
                    assert [row['command'] for row in rows if row['protocol'] == 'qmp'] == HEALTH_COMMANDS
                    assert all(row['protocol'] in ('qmp', 'gdb.request') for row in rows)
                    gdb_rows = [row for row in rows if row['protocol'] == 'gdb.request']
                    assert gdb_rows[1]['command'] == 'qqemu.PhyMemMode'
                    original_mode = bytes.fromhex(gdb_rows[1]['result_hex'])
                    assert original_mode in (b'0', b'1')
                    expected_gdb = ['g', 'qqemu.PhyMemMode']
                    if original_mode == b'0':
                        expected_gdb.append('Qqemu.PhyMemMode:1')
                    expected_gdb.append(f'm{address:x},2')
                    if original_mode == b'0':
                        expected_gdb.append('Qqemu.PhyMemMode:0')
                    assert [row['command'] for row in gdb_rows] == expected_gdb
                    assert all('error' not in row for row in rows)
                    assert _counts(project) == counts
                    healthy_owner()

                healthy_owner()
                token = uuid.uuid4().hex
                assert token != stream['stream']
                arguments = {'token': token, 'delta-ns': INPUT_DELAY_NS,
                    'events': [{'type': 'key', 'data': {
                        'key': {'type': 'qcode', 'data': 'a'}, 'down': True}}]}
                arm_begin = len(calls)
                with owner['lock']:
                    armed = qmp.call(ARM_INPUT, arguments)
                evidence['transitions']['arm'] = dict(arguments=deepcopy(arguments),
                    native=deepcopy(armed), native_call_begin=arm_begin, native_call_end=len(calls))
                assert len(calls) == arm_begin + 1
                assert armed == {'api-version': 1,
                    'epoch': first['clocks']['before']['virtual_clock']['native']['epoch'],
                    'state': 'armed', 'virtual-ns': stopped_ns, 'event-count': 1,
                    'token': token, 'start-ns': stopped_ns,
                    'deadline-ns': stopped_ns + INPUT_DELAY_NS}
                host_unchanged()
                refuse(armed)
                health(armed)

                cancel_arguments = {'token': token}
                cancel_begin = len(calls)
                with owner['lock']:
                    cancelled = qmp.call(CANCEL_INPUT, cancel_arguments)
                evidence['transitions']['cancel'] = dict(arguments=cancel_arguments,
                    native=deepcopy(cancelled), native_call_begin=cancel_begin, native_call_end=len(calls))
                assert len(calls) == cancel_begin + 1
                assert cancelled == dict(armed, state='cancelled', reason='caller',
                                         **{'terminal-ns': stopped_ns})
                host_unchanged()
                refuse(cancelled)
                health(cancelled)

                assert len(evidence['observations']) == 1 and len(evidence['refusals']) == 2
                assert len(evidence['health']) == 2
                segments = [evidence['transitions']['arm'], evidence['refusals'][0],
                    evidence['health'][0], evidence['transitions']['cancel'],
                    evidence['refusals'][1], evidence['health'][1]]
                assert all(left['native_call_end'] == right['native_call_begin']
                           for left, right in zip(segments, segments[1:]))
                assert segments[-1]['native_call_end'] == len(calls)
                for command, count in ((ARM_INPUT, 1), (CANCEL_INPUT, 1), (EXPORT, 1),
                        ('x-fdisbull-start-video-frame', 1), ('input-send-event', 0),
                        ('x-fdisbull-apply-frame-key-edges', 0),
                        ('x-fdisbull-arm-stopped-control', 0),
                        ('x-fdisbull-query-stopped-control', 0), ('cont', 0)):
                    assert sum(row['protocol'] == 'qmp' and row['command'] == command
                               for row in calls) == count
                assert not any(row['protocol'] == 'qmp' and row['command'] == EXPORT
                               for row in calls[arm_begin:])
                assert sum(row['protocol'] == 'gdb.execute' for row in calls) == 1
                assert not any(row['protocol'] == 'gdb.request' and row['command'].startswith('M')
                               for row in calls)
                assert all('error' not in row for row in calls)
                assert _counts(project) == counts
                evidence['owner_end'] = _identity(debug, owner)
                assert evidence['owner_start'] == evidence['owner_end']
        body_complete = True
    except BaseException as error:
        primary = error
        evidence['error'] = dict(type=type(error).__name__, message=str(error)[:4096])
        raise
    finally:
        cleanup_started = time.monotonic()
        errors = []
        if owner is not None:
            try:
                _close_original(debug, owner)
            except BaseException as error:
                errors.append(error)
            evidence['owner_reaped'] = owner['process'].poll() is not None
            evidence['owner_returncode'] = owner['process'].returncode
        if project is not None:
            try:
                project.db.close()
            except BaseException as error:
                errors.append(error)
        try:
            assert _digest(paths['com']) == COM_SHA256
            assert _digest(paths['baseline']) == BASELINE_SHA256
            assert _digest(paths['executable']) == pins['executable']['sha256']
            if binary is not None:
                assert binary.read_bytes() == code
            evidence['inputs_unchanged'] = True
            assert time.monotonic() - cleanup_started <= CLEANUP_SECONDS
        except BaseException as error:
            errors.append(error)
        evidence['elapsed_seconds'] = time.monotonic() - started_at
        evidence['cleanup_seconds'] = time.monotonic() - cleanup_started
        evidence['cleanup_errors'] = [dict(type=type(error).__name__, message=str(error)[:4096])
                                      for error in errors]
        evidence['success'] = body_complete and not errors and evidence['owner_reaped']
        raw = json.dumps(evidence, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
        if len(raw) > RECEIPT_BYTES:
            receipt_path.write_text(json.dumps(dict(format=NATIVE_FORMAT, success=False,
                error=dict(type='ReceiptOverflow', bytes=len(raw), sha256=_sha(raw)),
                owner_reaped=evidence['owner_reaped'], limits=evidence['limits'],
                raw_evidence='Retained by the independently bounded controller journal'),
                sort_keys=True), encoding='utf-8')
            errors.append(AssertionError('Native scheduler-observation receipt exceeded 2 MiB'))
        else:
            receipt_path.write_bytes(raw)
        record_property('native_input_schedule_observation_receipt', str(receipt_path))
        record_property('owners_reaped', int(evidence['owner_reaped']))
        if errors:
            if primary is not None:
                primary.add_note('Original-owner cleanup/receipt check: ' +
                                 '; '.join(type(error).__name__ for error in errors))
            else:
                raise errors[0]
