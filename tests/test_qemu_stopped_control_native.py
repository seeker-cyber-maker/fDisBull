"""One explicitly admitted native stopped-control witness on one owned QEMU.

The controller supplies and journals the bounded raw GDB peer below Python
protocol admission. No guard is removed, no second client is created, and no
test assembles a guest, prepares DOS media, or builds its own producer.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import struct
import time

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_stopped_control import ARM, QUERY, SCOPE, STOPPED_CONTROL_COMMANDS
from fdisbull.qemu_video_frame_state import FORMAT, VIDEO_FRAME_STATE_COMMANDS
from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import com_address, create_project, launch_options, process_record, read_bytes
from test_qemu_video_frame_native import _assert_frame, _query, _timing
from test_qemu_video_frame_state_native import (
    COM_SHA256, FOOTER_NAMES, FOOTER_VALUES, _sha, _digest, _clock, _counts,
    _owner, _current, _identity, _deadline, _record_calls, _host_neutral,
    _keyboard_neutral, _close_original,
)


WORK_SECONDS = 60
CLEANUP_SECONDS = 10
RECEIPT_BYTES = 2 * 1024**2
BASELINE_SHA256 = '7943e405080eafdab19c32164e8c4a90946e2b4e95ca60bb3950d09b73572daf'
NATIVE_FORMAT = 'fdisbull-native-stopped-control-observation-1'


def _inputs(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_STOPPED_CONTROL') != '1':
        pytest.skip('Native stopped-control requires its separately admitted owner controller')
    config = request.config
    assert getattr(config, '_fdisbull_stopped_control_owned_gate', None) == 'fdisbull-stopped-control-owned-gate-1'
    assert callable(getattr(config, '_fdisbull_stopped_control_post_setup', None))
    assert callable(getattr(config, '_fdisbull_stopped_control_raw_request', None))
    producer_sha = getattr(config, '_fdisbull_stopped_control_producer_sha256', None)
    assert type(producer_sha) is str and re.fullmatch('[0-9a-f]{64}', producer_sha)
    names = dict(executable='FDISBULL_QEMU_CLOCK', firmware='FDISBULL_QEMU_CLOCK_FIRMWARE',
        mcopy='FDISBULL_QEMU_DOS_MCOPY', com='FDISBULL_STOPPED_CONTROL_COM',
        baseline='FDISBULL_STOPPED_CONTROL_BASELINE')
    assert all(os.environ.get(name) for name in names.values())
    paths = {key: (Path(os.environ[name]).absolute() if key == 'mcopy'
                   else Path(os.environ[name]).resolve(strict=True)) for key, name in names.items()}
    assert paths['firmware'].is_dir()
    for key in ('executable', 'mcopy', 'com', 'baseline'):
        assert paths[key].is_file() and paths[key].stat().st_size <= 64 * 1024**2
    assert all(os.access(paths[key], os.X_OK) for key in ('executable', 'mcopy'))
    code = paths['com'].read_bytes()
    assert len(code) == 503 and _sha(code) == COM_SHA256 and code[-34:-30] == b'VFR1'
    offsets = struct.unpack('<15H', code[-30:])
    assert offsets == FOOTER_VALUES
    assert paths['baseline'].stat().st_size == 1474560 and _digest(paths['baseline']) == BASELINE_SHA256
    assert _digest(paths['executable']) == producer_sha
    pins = {key: dict(path=str(path), bytes=path.stat().st_size, sha256=_digest(path))
            for key, path in paths.items() if key != 'firmware'}
    pins['firmware'] = dict(path=str(paths['firmware']), controller_manifest_required=True)
    runtime = {key: paths[key] for key in ('executable', 'mcopy')}
    runtime['firmware'] = str(paths['firmware'])
    return paths, runtime, dict(image=paths['baseline'], prepared_sha256=BASELINE_SHA256), code, dict(zip(FOOTER_NAMES, offsets, strict=True)), pins


def _scoped(value, native, address, pixel_sha, generation):
    assert value['format'] == FORMAT and value['complete'] is True and value['issues'] == []
    assert value['atomic'] is False
    assert all(value[key] is None for key in ('native_mutation_revision', 'application_frame_complete',
                                             'frame_state_equivalence', 'legacy_phase_equivalence'))
    control = value['native_control']
    assert control['scope'] == SCOPE and control['complete'] is True
    assert control['before'] == control['after'] and control['before']['generation'] == generation
    assert control['before']['state'] == 'armed' and control['before']['busy'] is False
    assert value['state_before'] == value['state_after']
    assert value['state_before']['ram'] == [dict(address=address, length=2, space='physical',
        data_hex='0000', sha256=_sha(b'\0\0'))]
    source = value['source']
    assert source['before'] == source['after'] == native
    assert source['exported'] is None and source['rgb_verified'] is True
    assert source['rgb_origin'] == 'previously-verified-immutable-export'
    assert source['pixel_sha256'] == pixel_sha and source['rgb_bytes'] == WIDTH * HEIGHT * 3
    assert value['input']['before'] == value['input']['after']
    _host_neutral(value['input']['before']['host'])
    _keyboard_neutral(value['input']['before']['keyboard'])
    assert all(value['input'][key] is None for key in ('mouse_state', 'all_devices_neutral', 'guest_consumed'))
    assert _clock(value['clocks']['before']) == _clock(value['clocks']['after'])
    authority = value['authority']
    assert authority['valid'] is authority['complete'] is True
    assert authority['control_generation_before'] == authority['control_generation_after']
    assert authority['coverage']['raw_handles'] is False
    assert authority['native_state_revision'] is authority['whole_machine_state_revision'] is None


def _bracket_calls(rows):
    qmp = [row for row in rows if row['protocol'] == 'qmp']
    assert qmp[0]['command'] == qmp[-1]['command'] == QUERY
    assert sum(row['command'] == QUERY for row in qmp) == 2
    assert not any(row['command'] == 'x-fdisbull-export-video-frame' for row in qmp)


def test_native_stopped_control_detects_raw_same_byte_and_aba_writes(tmp_path, request, monkeypatch, record_property):
    started = time.monotonic()
    end = started + WORK_SECONDS
    paths, runtime, disk, code, offsets, pins = _inputs(request)
    expected = expected_rgb()
    pixel_sha = _sha(expected)
    assert len(expected) == WIDTH * HEIGHT * 3
    directory = tmp_path / 'stopped-control'
    directory.mkdir()
    assert not any((parent / '.git').exists() for parent in (directory, *directory.parents))
    receipt_path = tmp_path / 'native-stopped-control-observation.json'
    evidence = dict(format=NATIVE_FORMAT, success=False, inputs=pins, setup={}, arm=None,
        observations=[], mutation={}, refusal=None, native_calls=dict(records=[]),
        post_setup_execution=[], owner_reaped=False,
        limits=dict(work_seconds=WORK_SECONDS, cleanup_seconds=CLEANUP_SECONDS,
            owners=1, streams=1, completed_rasters=1, successful_observations=2,
            refused_observations=1, post_setup_continues=1, exports_before_arm=1,
            exports_after_arm=0, raw_packets=12, raw_writes=3, raw_write_bytes=3),
        unknown=dict(atomic=False, native_mutation_revision=None, whole_machine_revision=None,
            application_frame_complete=None, legacy_phase_equivalence=None,
            completed_guest_frames=False, all_devices_neutral=None, guest_input_consumed=None,
            uninstrumented_device_aio_mutation=None))
    debug = owner = project = binary = None
    primary = None
    body_complete = False
    try:
        binary, project = create_project(directory, code)
        debug = project.debugger(runtime['executable'], directory,
            **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise'))
        owner = _owner(debug)
        vm, remote, authority = owner['vm'], owner['gdb'], owner['vm'].observation_authority
        assert VIDEO_FRAME_STATE_COMMANDS | STOPPED_CONTROL_COMMANDS <= set(vm.qmp_commands)
        assert debug.capabilities['native_stopped_control'] is True
        assert debug.capabilities['completed_guest_frames'] is False
        info = process_record(debug)
        symbols = {name: com_address(info, offset) for name, offset in offsets.items()}
        baseline_breakpoints = deepcopy(debug.breakpoints)
        return_breakpoint = debug._return_breakpoint
        parked = park(debug, symbols['ready'])
        assert debug.breakpoints == baseline_breakpoints and debug._return_breakpoint == return_breakpoint
        with _record_calls(debug, owner, monkeypatch, evidence) as calls:
            request.config._fdisbull_stopped_control_post_setup(vm)
            evidence['owner_start'] = _identity(debug, owner)
            evidence['setup'].update(process=info, symbols=symbols, parked=parked,
                breakpoints=baseline_breakpoints, return_breakpoint=return_breakpoint,
                prebuilt_com=True, baseline_prepared_before_case=True,
                oracle=dict(pixel_sha256=pixel_sha, rgb_bytes=len(expected)))
            # An expected refusal exits the captured deadline context before
            # its ordinary successful-return live-owner assertion.
            with pytest.raises(DebuggerError, match='Native stopped-control identity changed') as caught:
                with _deadline(debug, owner, end):
                    timing = _timing(debug, symbols)
                    before = debug.clock_observe()
                    schedule = frame_schedule(timing, before['virtual_ns'])
                    stream = debug.video_frame_start(timeout_ms=1000)
                    advance = debug.video_frame_advance(timeout_ms=5000)
                    native = _query(debug)
                    frame = _assert_frame(native, schedule, expected)
                    assert advance['advance_completed'] is advance['completed_source_raster'] is True
                    assert advance['stop_consumed'] is True and advance['fence']['released']['released'] is True
                    assert advance['frame'] == frame and native['token'] == stream['stream']
                    assert read_bytes(debug, symbols['command'], 1) == b'\0'
                    assert read_bytes(debug, symbols['mutation_count'], 1) == b'\0'
                    address = symbols['page_before']
                    assert symbols['page_after'] == address + 1
                    options = dict(ram_ranges=[dict(address=address, length=2)],
                        stream=stream['stream'], frame_id=frame['frame-id'], timeout_ms=2000)
                    counts = _counts(project)
                    rgba = debug.video_frame_rgba(stream=stream['stream'], frame_id=frame['frame-id'])
                    assert vm._video_frame_owned_rgb == expected and type(vm._video_frame_owned_rgb) is bytes
                    assert _counts(project) == counts
                    evidence['setup'].update(schedule=schedule, stream=stream, advance=advance,
                        source=native, verified_cache=dict(rgb_sha256=pixel_sha, rgb_bytes=len(expected),
                            rgba_sha256=rgba.sha256))
                    del rgba
                    armed = evidence['arm'] = debug.stopped_control_arm(timeout_ms=2000)
                    assert armed['complete'] and armed['native']['state'] == 'armed' and not armed['native']['busy']
                    generation = armed['native']['generation']
                    assert armed['native']['epoch'] == before['virtual_clock']['native']['epoch']
                    options['native_control_token'] = armed['token']
                    arm_end = len(calls)

                    def observe(expected_generation):
                        begin = len(calls)
                        value = debug.video_frame_state_observe(**options)
                        evidence['observations'].append(value)
                        _scoped(value, native, address, pixel_sha, expected_generation)
                        _bracket_calls(calls[begin:])
                        assert _counts(project) == counts
                        return value

                    def raw_transaction(label, values):
                        _current(debug, owner)
                        start_generation = authority.control_generation
                        deadline = min(end, vm.operation_deadline, time.monotonic() + 1)
                        rows = []

                        def raw(command):
                            reply = request.config._fdisbull_stopped_control_raw_request(vm, command, deadline)
                            rows.append(dict(command_hex=command.hex(), reply_hex=reply.hex()))
                            return reply

                        mode = raw(b'qqemu.PhyMemMode')
                        assert mode in (b'0', b'1')
                        if mode == b'0':
                            assert raw(b'Qqemu.PhyMemMode:1') == b'OK'
                        for value in values:
                            assert raw(f'M{address:x},1:{value:02x}'.encode()) == b'OK'
                            assert raw(f'm{address:x},1'.encode()) == f'{value:02x}'.encode()
                        if mode == b'0':
                            assert raw(b'Qqemu.PhyMemMode:0') == b'OK'
                        _current(debug, owner)
                        evidence['mutation'][label] = dict(address=address, space='physical',
                            values=list(values), original_mode=mode.decode(), records=rows,
                            control_generation_before=start_generation,
                            control_generation_after=authority.control_generation)
                        assert authority.control_generation == start_generation

                    first = observe(generation)
                    raw_transaction('same_byte', [0])
                    second = observe(generation + 1)
                    assert first['state_before'] == second['state_before']
                    assert _clock(first['clocks']['before']) == _clock(second['clocks']['after'])
                    evidence['owner_before_refusal'] = _identity(debug, owner)
                    assert evidence['owner_before_refusal'] == evidence['owner_start']
                    actual_memory = remote.memory
                    injected = []

                    def memory_then_aba(location, length, **kwargs):
                        value = actual_memory(location, length, **kwargs)
                        if (not injected and location == address and length == 2
                                and kwargs.get('space') == 'physical' and kwargs.get('data') is None
                                and authority._active is not None):
                            assert value == b'\0\0' and not authority._stack
                            injected.append(True)
                            raw_transaction('aba', [0x5a, 0])
                        return value

                    monkeypatch.setattr(remote, 'memory', memory_then_aba)
                    refusal_begin = len(calls)
                    debug.video_frame_state_observe(**options)
                    pytest.fail('A native ABA mutation was accepted')
            error = caught.value
            refusal = getattr(error, 'video_frame_state_evidence', None) or error.result
            evidence['refusal'] = deepcopy(refusal)
            assert len(injected) == 1 and len(evidence['observations']) == 2
            assert refusal['complete'] is False and refusal['native_control']['complete'] is False
            assert refusal['stage'] == 'native-control-after'
            assert refusal['state_before'] == refusal['state_after'] == first['state_before']
            assert refusal['native_control']['before']['generation'] == generation + 1
            assert refusal['native_control']['after']['generation'] == generation + 3
            assert refusal['native_control']['before']['process-id'] == armed['native']['process-id']
            assert refusal['native_control']['after']['token'] == armed['token']
            assert _clock(refusal['clocks']['before']) == _clock(refusal['clocks']['after'])
            assert refusal['source']['exported'] is None and refusal['source']['pixel_sha256'] == pixel_sha
            assert refusal['atomic'] is False and refusal['native_mutation_revision'] is None
            _bracket_calls(calls[refusal_begin:])
            assert not any(row['protocol'] == 'qmp' and row['command'] == 'x-fdisbull-export-video-frame'
                           for row in calls[arm_end:])
            assert sum(row['protocol'] == 'qmp' and row['command'] == ARM for row in calls) == 1
            assert sum(row['protocol'] == 'qmp' and row['command'] == QUERY for row in calls) == 6
            assert sum(row['protocol'] == 'gdb.execute' for row in calls) == 1
            assert not any(row['protocol'] == 'gdb.request' and row['command'].startswith('M') for row in calls)
            assert sum(len(value['records']) for value in evidence['mutation'].values()) <= 12
            assert _counts(project) == counts
            assert owner['process'].poll() is not None
            assert owner['qmp_socket'].closed and owner['gdb_socket'].closed
            assert debug.breakpoints == baseline_breakpoints and debug._return_breakpoint == return_breakpoint
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
            assert _digest(paths['com']) == COM_SHA256 and _digest(paths['baseline']) == BASELINE_SHA256
            assert _digest(paths['executable']) == pins['executable']['sha256']
            if binary is not None:
                assert binary.read_bytes() == code
            assert time.monotonic() - cleanup_started <= CLEANUP_SECONDS
            evidence['inputs_unchanged'] = True
        except BaseException as error:
            errors.append(error)
        evidence['elapsed_seconds'] = time.monotonic() - started
        evidence['cleanup_seconds'] = time.monotonic() - cleanup_started
        evidence['cleanup_errors'] = [dict(type=type(error).__name__, message=str(error)[:4096]) for error in errors]
        evidence['success'] = body_complete and not errors and evidence['owner_reaped']
        raw = json.dumps(evidence, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
        if len(raw) > RECEIPT_BYTES:
            receipt_path.write_text(json.dumps(dict(format=NATIVE_FORMAT, success=False,
                error=dict(type='ReceiptOverflow', bytes=len(raw), sha256=_sha(raw)),
                owner_reaped=evidence['owner_reaped'], raw_evidence='Independent bounded controller journal')))
            errors.append(AssertionError('Native stopped-control receipt exceeds2MiB'))
        else:
            receipt_path.write_bytes(raw)
        record_property('native_stopped_control_receipt', str(receipt_path))
        record_property('owners_reaped', int(evidence['owner_reaped']))
        if errors:
            if primary is not None:
                primary.add_note('Original-owner cleanup/receipt check: ' + '; '.join(type(error).__name__ for error in errors))
            else:
                raise errors[0]
