"""One separately admitted native witness for retained-frame SDK consumers.

The controller supplies the producer pin, prebuilt 503-byte COM and prepared
baseline, and independently journals the original native owner. This case
creates one source raster, then performs no more guest execution. Host codecs
and a cooperative session revision do not establish DOSBox sampling-phase,
application-frame, atomic-state or raw-native-mutation equivalence.
"""
import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import re
import struct
import time
import uuid

import pytest
from PIL import Image

from fdisbull.native_controller import BoundedNativeController
from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
from fdisbull.qemu_video_control import VIDEO_FRAME_CONTROL_COMMANDS
from fdisbull.screenshot_codecs import RGBAFrame
from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_video_frame_native import _assert_frame, _query, _timing
from test_qemu_video_frame_state_native import (
    COM_SHA256, FOOTER_NAMES, FOOTER_VALUES, MAX_NATIVE_CALLS, MAX_VIDEO_CALLS,
    OUTPUT_BYTES, SUPERVISOR_SECONDS, _sha, _digest, _clock, _counts, _owner,
    _current, _identity, _deadline, _record_calls, _close_original,
)


WORK_SECONDS, CLEANUP_SECONDS = 60, 10
RECEIPT_BYTES = 2 * 1024**2
CODEC_BYTES = WIDTH * HEIGHT * 4 + 8192
INPUT_DELAY_NS = 1_000_000_000
BASELINE_SHA256 = '7943e405080eafdab19c32164e8c4a90946e2b4e95ca60bb3950d09b73572daf'
NATIVE_FORMAT = 'fdisbull-native-frame-contract-1'
SOURCE, PROFILE = 'qemu_completed_source_raster', 'qemu-vga-chain4-scanline-v1'
REVISION_SCOPE = 'cooperative-session-control-v1'
TICKS_CLOCK = 'QEMU_CLOCK_VIRTUAL_milliseconds'
PPM_HEADER = b'P6\n320 200\n255\n'
POINTS = [[319, 199], [0, 0], [319, 199], [160, 100], [0, 0]]
CLOCK_COMMANDS = ['query-status', 'query-replay', 'x-fdisbull-query-clock']
QUERY_VIDEO, PROBE_VIDEO, EXPORT_VIDEO = (
    'x-fdisbull-query-video-frame', 'x-fdisbull-probe-video-frame',
    'x-fdisbull-export-video-frame',
)
ARM_INPUT, CANCEL_INPUT = 'x-fdisbull-arm-input', 'x-fdisbull-cancel-input'
READ_COMMANDS = CLOCK_COMMANDS + [QUERY_VIDEO, EXPORT_VIDEO] + CLOCK_COMMANDS * 2
EMPTY_PROBE_COMMANDS = CLOCK_COMMANDS + [QUERY_VIDEO] + CLOCK_COMMANDS
SPARSE_PROBE_COMMANDS = CLOCK_COMMANDS + [QUERY_VIDEO, PROBE_VIDEO] + CLOCK_COMMANDS


def _inputs(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_FRAME_CONTRACT') != '1':
        pytest.skip('Native frame consumers require their separately admitted owner controller')
    config = request.config
    assert getattr(config, '_fdisbull_frame_contract_owned_gate', None) == (
        'fdisbull-frame-contract-owned-gate-1')
    assert callable(getattr(config, '_fdisbull_frame_contract_post_setup', None))
    producer_sha = getattr(config, '_fdisbull_frame_contract_producer_sha256', None)
    assert type(producer_sha) is str and re.fullmatch('[0-9a-f]{64}', producer_sha)
    zstd_mode = os.environ.get('FDISBULL_FRAME_CONTRACT_ZSTD')
    assert zstd_mode in ('0', '1'), 'The reviewed gate must explicitly choose Zstandard mode 0 or 1'
    if zstd_mode == '1':
        # Missing an explicitly admitted optional codec fails this gate.
        import zstandard  # noqa: F401
    names = dict(executable='FDISBULL_QEMU_CLOCK', firmware='FDISBULL_QEMU_CLOCK_FIRMWARE',
        mcopy='FDISBULL_QEMU_DOS_MCOPY', com='FDISBULL_FRAME_CONTRACT_COM',
        baseline='FDISBULL_FRAME_CONTRACT_BASELINE')
    assert all(os.environ.get(name) for name in names.values())
    paths = {}
    for key, name in names.items():
        path = Path(os.environ[name]).expanduser()
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
    return paths, runtime, disk, code, dict(zip(FOOTER_NAMES, offsets, strict=True)), pins, zstd_mode == '1'


def _qmp_sequence(rows, commands):
    assert all(row['protocol'] == 'qmp' and 'error' not in row for row in rows)
    assert [row['command'] for row in rows] == commands
    for row in rows:
        if row['command'] not in (PROBE_VIDEO, EXPORT_VIDEO, ARM_INPUT, CANCEL_INPUT):
            assert row['arguments'] is None


def _memory_sequence(rows, address, *, write=False):
    assert rows and all(row['protocol'] == 'gdb.request' and 'error' not in row for row in rows)
    assert rows[0]['command'] == 'qqemu.PhyMemMode'
    mode = bytes.fromhex(rows[0]['result_hex'])
    assert mode in (b'0', b'1')
    commands = ['qqemu.PhyMemMode']
    replies = [mode]
    if mode == b'0':
        commands.append('Qqemu.PhyMemMode:1'); replies.append(b'OK')
    if write:
        commands.append(f'M{address:x},1:00'); replies.append(b'OK')
    commands.append(f'm{address:x},1'); replies.append(b'00')
    if mode == b'0':
        commands.append('Qqemu.PhyMemMode:0'); replies.append(b'OK')
    assert [row['command'] for row in rows] == commands
    assert [bytes.fromhex(row['result_hex']) for row in rows] == replies
    return mode.decode('ascii')


def _samples(rgb):
    return [dict(x=x, y=y, rgb=list(rgb[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3]))
            for x, y in POINTS]


def _rgba_summary(frame, expected):
    assert isinstance(frame, RGBAFrame)
    assert (frame.width, frame.height, frame.stride) == (WIDTH, HEIGHT, WIDTH * 4)
    assert type(frame.pixels) is bytes and frame.pixels == expected
    assert frame.sha256 == _sha(expected) == frame.metadata['sha256'] == frame.metadata['raw_sha256']
    assert frame.metadata['format'] == frame.metadata['encoding'] == 'rgba'
    assert frame.metadata['pixel_format'] == 'RGBA8'
    assert frame.metadata['uncompressed_bytes'] == len(expected)
    for x, y in POINTS:
        offset = (y * WIDTH + x) * 4
        assert frame.pixel(x, y) == tuple(expected[offset:offset + 4])
    return dict(width=frame.width, height=frame.height, stride=frame.stride,
        pixels_bytes=len(frame.pixels), pixels_sha256=frame.sha256,
        metadata=deepcopy(frame.metadata))


def _wire_summary(result, encoding, expected):
    assert type(result) is dict and result['encoding'] == encoding
    assert result['requested_encoding'] == encoding and 'fallback_reason' not in result
    field = 'data_base64' if encoding == 'rgba-zstd' else 'png_base64'
    assert type(result.get(field)) is str and len(result[field]) <= ((CODEC_BYTES + 2) // 3) * 4
    assert ('png_base64' if field == 'data_base64' else 'data_base64') not in result
    payload = base64.b64decode(result[field], validate=True)
    assert 0 < len(payload) <= CODEC_BYTES and _sha(payload) == result['sha256']
    transport = dict(bytes=len(payload), sha256=_sha(payload), encoding=encoding)
    if encoding == 'rgba-zstd':
        import zstandard
        assert result['format'] == 'rgba-zstd' and result['pixel_format'] == 'RGBA8'
        assert result['stride'] == WIDTH * 4 and result['uncompressed_bytes'] == len(expected)
        parameters = zstandard.get_frame_parameters(payload)
        assert parameters.content_size == len(expected) and parameters.window_size <= len(expected)
        decoded = zstandard.ZstdDecompressor().decompress(
            payload, max_output_size=len(expected), allow_extra_data=False)
        assert result['raw_sha256'] == _sha(expected)
        transport.update(content_size=parameters.content_size, window_size=parameters.window_size)
    else:
        assert result['format'] == 'png' and payload.startswith(b'\x89PNG\r\n\x1a\n')
        with Image.open(io.BytesIO(payload)) as image:
            assert image.format == 'PNG' and image.size == (WIDTH, HEIGHT)
            assert image.mode == ('P' if encoding == 'png-indexed' else 'RGBA')
            decoded = image.convert('RGBA').tobytes()
            transport['image_mode'] = image.mode
        if encoding == 'png-indexed':
            assert result['palette_colors'] == 3
    assert decoded == expected
    # The independent controller sees the actual return payload. Keep bounded
    # identities here instead of duplicating base64 in the native receipt.
    return dict(metadata={key: deepcopy(value) for key, value in result.items() if key != field},
        payload=transport, pixels_bytes=len(decoded), pixels_sha256=_sha(decoded))


def test_native_frame_contract_retains_source_and_refuses_changed_revision(
        tmp_path, request, monkeypatch, record_property):
    started_at = time.monotonic()
    paths, runtime, disk, code, offsets, pins, zstd = _inputs(request)
    rgb = expected_rgb()
    assert len(rgb) == WIDTH * HEIGHT * 3
    rgba = bytearray(WIDTH * HEIGHT * 4)
    rgba[0::4], rgba[1::4], rgba[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
    rgba[3::4] = b'\xff' * (WIDTH * HEIGHT)
    rgba = bytes(rgba)
    assert len({rgb[index:index + 3] for index in range(0, len(rgb), 3)}) == 3
    codecs = ['png', 'png-indexed'] + (['rgba-zstd'] if zstd else [])
    exports, ready_qmp, video_calls = (8, 121, 31) if zstd else (6, 99, 27)
    directory = tmp_path / 'frame-contract'
    directory.mkdir()
    assert not any((parent / '.git').exists() for parent in (directory, *directory.parents))
    receipt_path = tmp_path / 'native-frame-contract.json'
    evidence = dict(format=NATIVE_FORMAT, success=False, inputs=pins, zstd_enabled=zstd,
        codec_matrix=codecs, setup={}, operations=[], transitions={}, coherence_details={},
        native_calls=dict(scope='post-setup; controller journal also covers bootstrap', records=[]),
        post_setup_execution=[], owner_reaped=False, hook_entries=[],
        limits=dict(work_seconds=WORK_SECONDS, cleanup_seconds=CLEANUP_SECONDS,
            supervisor_seconds=SUPERVISOR_SECONDS, private_output_bytes=OUTPUT_BYTES,
            receipt_bytes=RECEIPT_BYTES, codec_bytes=CODEC_BYTES,
            max_native_calls=MAX_NATIVE_CALLS, max_video_calls=MAX_VIDEO_CALLS,
            exact_video_calls=video_calls, owners=1, streams=1, completed_rasters=1,
            source_fence_arms=1, source_fence_cancels=1, source_fence_queries=2,
            post_setup_continues=1, post_ready_qmp_calls=ready_qmp,
            post_ready_gdb_calls_mode_one=7, post_ready_gdb_calls_mode_zero=13,
            public_status_calls=9, public_probe_calls=3, native_probe_chunks=1,
            sampled_points=len(POINTS), wire_screenshots=3 if zstd else 2,
            rgba_reads=4 if zstd else 3, source_captures=1, exports=exports,
            native_schedule_arms=1, native_schedule_cancels=1, scheduled_events=1,
            dispatched_events=0, cooperative_write_bytes=1, selected_ram_reads=2,
            selected_ram_bytes_per_read=1, raw_packets=0, native_control_arms=0,
            post_ready_events=5, post_ready_artifacts=1, hook_entries=0,
            coherence_brackets=1, coherence_refusals=1),
        unknown=dict(atomic=False, frame_state_equivalence=None,
            native_state_revision=None, whole_machine_state_revision=None,
            completed_guest_frames=False, legacy_phase_equivalence=None,
            application_frame_complete=None, guest_input_consumed=None,
            raw_handles_covered=False, independent_controllers_covered=False,
            native_device_mutations_covered=False))
    debug = owner = project = binary = None
    primary = None
    body_complete = False
    try:
        binary, project = create_project(directory, code)
        debug = project.debugger(runtime['executable'], directory,
            **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise'))
        owner = _owner(debug)
        vm, qmp, remote = owner['vm'], owner['qmp'], owner['gdb']
        authority, revision = vm.observation_authority, vm.session_revision
        assert remote is not None and remote.register_description
        assert VIDEO_FRAME_CONTROL_COMMANDS | INPUT_SCHEDULE_COMMANDS <= set(vm.qmp_commands)
        assert debug.capabilities['frame_contract'] is True
        assert debug.capabilities['frame_probe'] is debug.capabilities['frame_rgba'] is True
        assert debug.capabilities['completed_guest_frames'] is False
        assert set(codecs) <= set(debug.capabilities['video']['screenshot_encodings'])
        with _deadline(debug, owner, started_at + WORK_SECONDS) as end:
            info = process_record(debug)
            symbols = {name: com_address(info, offset) for name, offset in offsets.items()}
            breakpoints, return_breakpoint = deepcopy(debug.breakpoints), debug._return_breakpoint
            parked = park(debug, symbols['ready'])
            assert debug.breakpoints == breakpoints and debug._return_breakpoint == return_breakpoint
            assert not getattr(debug, '_qemu_hooks', {})
            with _record_calls(debug, owner, monkeypatch, evidence) as calls:
                request.config._fdisbull_frame_contract_post_setup(vm)
                evidence['owner_start'] = _identity(debug, owner)
                evidence['setup'].update(process=info, symbols=symbols, parked=parked,
                    breakpoints=breakpoints, return_breakpoint=return_breakpoint,
                    prebuilt_com=True, baseline_prepared_before_case=True,
                    oracle=dict(rgb_bytes=len(rgb), rgb_sha256=_sha(rgb),
                        rgba_bytes=len(rgba), rgba_sha256=_sha(rgba),
                        method='authored VGA indices/DAC6 bit replication plus guest-read timing'))
                timing = _timing(debug, symbols)
                before = debug.clock_observe()
                schedule = frame_schedule(timing, before['virtual_ns'])
                stream = debug.video_frame_start(timeout_ms=1000)
                advance = debug.video_frame_advance(timeout_ms=5000)
                native = _query(debug)
                frame = _assert_frame(native, schedule, rgb)
                assert advance['advance_completed'] is advance['completed_source_raster'] is True
                assert advance['stop_consumed'] is True and advance['outcome'] == 'stopped'
                assert advance['frame'] == frame and native['token'] == stream['stream']
                assert advance['stream_generation'] == stream['stream_generation']
                assert advance['baseline_frame_sequence'] == stream['frame_sequence']
                assert native['frame-sequence'] == stream['frame_sequence'] + 1
                assert advance['fence']['released']['released'] is True
                assert advance['native_result'].get('hook_hits', []) == []
                packet, = [row for row in calls if row['protocol'] == 'gdb.execute']
                stop = advance['native_result']['session']['stop_reason']
                raw_stop = bytes.fromhex(packet['result_hex']).decode('ascii')
                assert packet['command'] == 'c' and packet['timed_out'] is False
                assert stop['native_reply'] == raw_stop and raw_stop.startswith(('T02', 'S02'))
                assert stop['breakpoint_ids'] == []
                frozen_clock = advance['clocks']['after']
                stopped_ns = frozen_clock['virtual_ns']
                assert frame['completed-ns'] <= stopped_ns < (
                    schedule['boundary'] + schedule['period_ns'] + schedule['line_ns'] // 4)
                assert read_bytes(debug, symbols['command'], 1) == b'\0'
                assert read_bytes(debug, symbols['mutation_count'], 1) == b'\0'
                address = symbols['page_before']
                assert symbols['page_after'] == address + 1
                evidence['setup'].update(schedule=schedule, stream=stream, advance=advance,
                    source=native, selected_ram=dict(address=address, length=1, space='physical'),
                    ready_call_index=len(calls), ready_counts=_counts(project))
                ready_begin, ready_counts = len(calls), _counts(project)
                host_present = hasattr(vm, '_physical_input')
                host_input = getattr(vm, '_physical_input', None)
                host_snapshot = deepcopy(host_input)
                evidence['setup']['host_input'] = dict(present=host_present,
                    object_id=id(host_input) if host_input is not None else None,
                    state=deepcopy(host_snapshot), frame_key_owner=None)
                native_transport = dict(format='ppm', encoding='ppm', pixel_format='RGB888',
                    stride=WIDTH * 3, uncompressed_bytes=len(rgb), bytes=len(PPM_HEADER) + len(rgb),
                    sha256=_sha(PPM_HEADER + rgb), pixel_sha256=_sha(rgb))

                def healthy():
                    _current(debug, owner)
                    assert vm.observation_authority is authority and vm.session_revision is revision
                    assert authority._active is None and authority._cleanup_owner is None and not authority._stack
                    assert debug.breakpoints == breakpoints and debug._return_breakpoint == return_breakpoint
                    assert not getattr(debug, '_qemu_hooks', {})
                    assert not getattr(debug, '_screenshot_hooks_running', False)
                    assert not getattr(vm, '_fdisbull_control_quarantine', None)
                    assert hasattr(vm, '_physical_input') == host_present
                    assert getattr(vm, '_physical_input', None) is host_input and host_input == host_snapshot
                    if host_input is not None:
                        assert host_input['valid'] is True and host_input['sequence'] == 0
                        assert host_input['pending'] == [] and host_input['leases'] == {}
                        assert host_input.get('schedule') is host_input.get('schedule_receipt') is None
                        assert host_input.get('last_delivery') is None
                    assert getattr(vm, '_frame_key_owner', None) is None
                    assert not getattr(vm, '_physical_input_closed', False)
                    assert not list(Path(owner['temporary'].name).glob('video-frame-*.ppm'))

                def operation(label, kind, callback, *, summarize=deepcopy, commands=None,
                              event_delta=0, artifact_delta=0):
                    healthy()
                    entry = dict(label=label, kind=kind, native_call_begin=len(calls),
                                 counts_before=_counts(project))
                    evidence['operations'].append(entry)
                    try:
                        value = callback()
                        entry['result'] = summarize(value)
                    except BaseException as error:
                        entry['error'] = dict(type=type(error).__name__, message=str(error)[:4096])
                        raise
                    finally:
                        entry.update(native_call_end=len(calls), counts_after=_counts(project))
                    if commands is not None:
                        _qmp_sequence(calls[entry['native_call_begin']:entry['native_call_end']], commands)
                    assert entry['counts_after'] == dict(
                        debug_events=entry['counts_before']['debug_events'] + event_delta,
                        debug_artifacts=entry['counts_before']['debug_artifacts'] + artifact_delta)
                    healthy()
                    return value, entry

                def status(label):
                    value, _ = operation(label, 'status', lambda: debug.call('session.status'),
                                         commands=['query-status'])
                    assert value['state'] == 'stopped' and value['native_state']['running'] is False
                    assert value['session_id'] == debug.session_id == revision.session_id
                    assert value['state_revision_scope'] == REVISION_SCOPE
                    assert type(value['state_revision']) is int and value['state_revision'] >= 0
                    assert value['native_state_revision'] is value['whole_machine_state_revision'] is None
                    return value

                initial = status('initial-status')
                expected_identity = dict(owner_lifetime=initial['session_id'], native_epoch=native['epoch'],
                    clock_epoch=frozen_clock['epoch'], stream=native['token'],
                    stream_generation=native['stream-generation'],
                    configuration_generation=frame['configuration-generation'],
                    timing_generation=frame['timing-generation'], frame_id=frame['frame-id'],
                    runtime_epoch=getattr(debug, '_runtime_epoch', None),
                    checkpoint_epoch=getattr(debug, '_checkpoint_epoch', None))
                expected_mode = None

                def metadata(value, expected_revision, *, codec=False):
                    assert value['session_id'] == initial['session_id']
                    assert value['state_revision'] == expected_revision
                    assert value['state_revision_scope'] == REVISION_SCOPE
                    assert value['native_state_revision'] is value['whole_machine_state_revision'] is None
                    assert value['source'] == SOURCE and value['frame_profile'] == PROFILE
                    assert value['frame_identity'] == expected_identity and value['frame_id'] == frame['frame-id']
                    assert type(value['mode_id']) is int and value['mode_id'] > 0
                    if expected_mode is not None:
                        assert value['mode_id'] == expected_mode
                    assert (value['width'], value['height'], value['source_bpp']) == (WIDTH, HEIGHT, 24)
                    assert value['double_width'] is value['double_height'] is False
                    assert value['captured_ns'] == frame['completed-ns']
                    assert type(value['captured_ticks']) is int
                    assert value['captured_ticks'] == frame['completed-ns'] // 1_000_000
                    assert value['captured_ticks_clock'] == TICKS_CLOCK
                    assert value['atomic'] is False and value['completed_source_raster'] is True
                    assert all(value[key] is None for key in (
                        'frame_state_equivalence', 'application_frame_complete', 'legacy_phase_equivalence'))
                    assert value['native'] == native and value['frame'] == frame
                    assert _clock(value['clock']) == _clock(frozen_clock)
                    if codec:
                        assert value['codec_origin'] == 'host-adapter'
                        assert value['native_transport'] == native_transport

                def unexpected_surface_hook(*args, **kwargs):
                    evidence['hook_entries'].append(dict(entry='screenshot', args_count=len(args),
                                                         keyword_names=sorted(kwargs)))
                    raise AssertionError('Retained-frame consumers entered the surface screenshot/hook path')

                # The QEMU hook entry is screenshot(), not the DOSBox-only
                # _capture_with_hooks helper. A read must never enter that path.
                with monkeypatch.context() as hook_guard:
                    hook_guard.setattr(debug, 'screenshot', unexpected_surface_hook)
                    probe, _ = operation('ordered-probe', 'probe',
                        lambda: debug.frame_probe(deepcopy(POINTS), timeout_ms=1000),
                        commands=SPARSE_PROBE_COMMANDS, event_delta=1)
                    assert probe['format'] == 'rgb-samples' and probe['samples'] == _samples(rgb)
                    assert 'png_base64' not in probe and 'data_base64' not in probe
                    expected_mode = probe['mode_id']
                    metadata(probe, initial['state_revision'])
                    wires = {}
                    for encoding in codecs:
                        wire, entry = operation('wire-' + encoding, 'wire-screenshot',
                            lambda encoding=encoding: debug.call('video.screenshot',
                                dict(encoding=encoding, timeout_ms=1000)),
                            summarize=lambda value, encoding=encoding: _wire_summary(value, encoding, rgba),
                            commands=READ_COMMANDS)
                        metadata(wire, initial['state_revision'], codec=True)
                        wires[encoding] = entry['result']
                        del wire

                    def read_rgba(label, encoding, expected_revision):
                        value, entry = operation(label, 'rgba',
                            lambda: debug.frame_rgba(encoding=encoding, timeout_ms=1000),
                            summarize=lambda value: _rgba_summary(value, rgba), commands=READ_COMMANDS)
                        metadata(value.metadata, expected_revision, codec=True)
                        transport = value.metadata['transport']
                        assert transport['encoding'] == encoding
                        assert transport['sha256'] == wires[encoding]['payload']['sha256']
                        assert transport['compressed_bytes'] == wires[encoding]['payload']['bytes']
                        return entry['result']

                    read_rgba('initial-rgba-png', 'png', initial['state_revision'])
                    if zstd:
                        read_rgba('initial-rgba-zstd', 'rgba-zstd', initial['state_revision'])
                    passive = status('after-passive-status')
                    assert passive['state_revision'] == initial['state_revision']

                    token = uuid.uuid4().hex
                    assert token != stream['stream']
                    arm_arguments = {'token': token, 'delta-ns': INPUT_DELAY_NS,
                        'events': [{'type': 'key', 'data': {
                            'key': {'type': 'qcode', 'data': 'a'}, 'down': True}}]}
                    def transition(label, command, arguments):
                        def send():
                            with owner['lock']:
                                return qmp.call(command, arguments)
                        value, entry = operation(label, 'input-transition', send, commands=[command])
                        evidence['transitions'][label] = dict(arguments=deepcopy(arguments),
                            native=deepcopy(value), native_call_begin=entry['native_call_begin'],
                            native_call_end=entry['native_call_end'])
                        return value
                    armed = transition('arm', ARM_INPUT, arm_arguments)
                    assert armed == {'api-version': 1, 'epoch': frozen_clock['virtual_clock']['native']['epoch'],
                        'state': 'armed', 'virtual-ns': stopped_ns, 'event-count': 1,
                        'token': token, 'start-ns': stopped_ns, 'deadline-ns': stopped_ns + INPUT_DELAY_NS}
                    cancelled = transition('cancel', CANCEL_INPUT, {'token': token})
                    assert cancelled == dict(armed, state='cancelled', reason='caller',
                                             **{'terminal-ns': stopped_ns})
                    assert 'dispatch-ns' not in cancelled
                    terminal = status('terminal-before-status')
                    assert terminal['state_revision'] > passive['state_revision']
                    read_rgba('terminal-rgba-indexed', 'png-indexed', terminal['state_revision'])
                    terminal_after = status('terminal-after-status')
                    assert terminal_after['state_revision'] == terminal['state_revision']

                    details = evidence['coherence_details']
                    details['ram_reads'] = []
                    def selected_ram():
                        assert len(details['ram_reads']) < 2
                        healthy()
                        begin = len(calls)
                        with owner['lock']:
                            value = remote.memory(address, 1, space='physical', timeout_ms=1000)
                        row = dict(address=address, length=1, space='physical', data_hex=value.hex(),
                            sha256=_sha(value), native_call_begin=begin, native_call_end=len(calls))
                        details['ram_reads'].append(row)
                        row['original_mode'] = _memory_sequence(calls[begin:], address)
                        assert value == b'\0'
                        healthy()
                        return {key: row[key] for key in ('address', 'length', 'space', 'data_hex', 'sha256')}

                    def capture_then_same_byte():
                        assert 'capture' not in details and 'write' not in details
                        begin, counts = len(calls), _counts(project)
                        artifact = debug.capture_video_frame('frame-contract-bracket.png', timeout_ms=1000)
                        details['capture'] = dict(result=deepcopy(artifact), native_call_begin=begin,
                            native_call_end=len(calls), counts_before=counts, counts_after=_counts(project))
                        _qmp_sequence(calls[begin:], READ_COMMANDS)
                        metadata(artifact['metadata'], terminal['state_revision'])
                        assert artifact['metadata']['codec_origin'] == 'host-adapter'
                        assert _counts(project) == dict(debug_events=counts['debug_events'] + 2,
                                                      debug_artifacts=counts['debug_artifacts'] + 1)
                        stored = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',
                                                    (artifact['artifact'],)).fetchone()
                        payload = bytes(stored['data'])
                        assert 0 < len(payload) <= CODEC_BYTES
                        assert _sha(payload) == stored['sha256'] == artifact['sha256']
                        with Image.open(io.BytesIO(payload)) as image:
                            assert image.format == 'PNG' and image.size == (WIDTH, HEIGHT) and image.mode == 'RGB'
                            assert image.tobytes() == rgb
                        details['capture']['payload'] = dict(bytes=len(payload), sha256=_sha(payload), image_mode='RGB')
                        healthy()
                        begin = len(calls)
                        prior_revision = revision.snapshot()
                        with owner['lock']:
                            value = remote.memory(address, 1, space='physical', data=b'\0', timeout_ms=1000)
                        after_revision = revision.snapshot()
                        details['write'] = dict(address=address, length=1, space='physical', data_hex='00',
                            readback_hex=value.hex(), before_revision=prior_revision, after_revision=after_revision,
                            native_call_begin=begin, native_call_end=len(calls))
                        details['write']['original_mode'] = _memory_sequence(calls[begin:], address, write=True)
                        assert value == b'\0'
                        assert prior_revision['state_revision'] == terminal['state_revision']
                        assert after_revision['session_id'] == prior_revision['session_id']
                        assert after_revision['state_revision'] > prior_revision['state_revision']
                        healthy()
                        return artifact

                    wall_ms = min(5000, int((end - time.monotonic()) * 1000))
                    assert wall_ms > 0
                    controller = BoundedNativeController(debug, read_state=selected_ram,
                        total_guest_ms=1, total_timeout_ms=wall_ms, admission_check=healthy)
                    bracket, bracket_entry = operation('same-byte-coherence', 'coherence',
                        lambda: controller.capture_frame_state(capture_then_same_byte,
                            require_fresh=False, guest_ms=1, slice_ms=1, max_polls=1),
                        event_delta=4, artifact_delta=1)
                    assert bracket['complete'] is False and bracket['issues'] == ['status state_revision changed']
                    assert bracket['atomic'] is False and bracket['frame_state_equivalence'] is None
                    assert bracket['freshness'] == 'not_requested' and bracket['polls'] == 1
                    assert bracket['guest_elapsed_ms'] == controller.guest_elapsed == 0
                    assert controller.blocked_reason is None and controller.inputs == []
                    assert len(details['ram_reads']) == len(bracket['status_brackets']) == 2
                    assert bracket['state_before'] == bracket['state_after']
                    assert bracket['state_before']['data_hex'] == '00'
                    assert bracket['frame'] == details['capture']['result']
                    before_status, after_status = bracket['status_before'], bracket['status_after']
                    assert before_status['state_revision'] == terminal['state_revision']
                    assert after_status['state_revision'] == details['write']['after_revision']['state_revision']
                    assert {key: value for key, value in before_status.items() if key != 'state_revision'} == {
                        key: value for key, value in after_status.items() if key != 'state_revision'}
                    for block, expected_revision in zip(bracket['status_brackets'],
                            (before_status['state_revision'], after_status['state_revision']), strict=True):
                        assert block['complete'] is True and block['issues'] == []
                        assert block['frame_probe']['samples'] == []
                        metadata(block['frame_probe'], expected_revision)
                        assert block['session_before']['state_revision'] == expected_revision
                        assert block['session_after']['state_revision'] == expected_revision
                    begin, end_call = bracket_entry['native_call_begin'], bracket_entry['native_call_end']
                    block_commands = ['query-status'] + EMPTY_PROBE_COMMANDS + ['query-status']
                    first_ram, last_ram = details['ram_reads']
                    capture, write = details['capture'], details['write']
                    _qmp_sequence(calls[begin:first_ram['native_call_begin']], block_commands)
                    assert first_ram['native_call_end'] == capture['native_call_begin']
                    assert capture['native_call_end'] == write['native_call_begin']
                    assert write['native_call_end'] == last_ram['native_call_begin']
                    _qmp_sequence(calls[last_ram['native_call_end']:end_call], block_commands)
                    evidence['coherence_journal'] = deepcopy(controller.journal)
                    read_rgba('reused-rgba-png', 'png', after_status['state_revision'])
                    reused = status('reused-status')
                    assert reused['state_revision'] == after_status['state_revision'] > terminal['state_revision']

                assert evidence['hook_entries'] == []
                healthy()
                operations = evidence['operations']
                assert operations[0]['native_call_begin'] == ready_begin
                assert all(left['native_call_end'] == right['native_call_begin']
                           for left, right in zip(operations, operations[1:]))
                assert operations[-1]['native_call_end'] == len(calls)
                ready_rows = calls[ready_begin:]
                assert sum(row['protocol'] == 'qmp' for row in ready_rows) == ready_qmp
                modes = [row['original_mode'] for row in details['ram_reads']] + [details['write']['original_mode']]
                assert len(set(modes)) == 1 and modes[0] in ('0', '1')
                assert sum(row['protocol'] == 'gdb.request' for row in ready_rows) == (13 if modes[0] == '0' else 7)
                assert all(row['protocol'] in ('qmp', 'gdb.request') and 'error' not in row for row in ready_rows)
                assert _counts(project) == dict(debug_events=ready_counts['debug_events'] + 5,
                                               debug_artifacts=ready_counts['debug_artifacts'] + 1)
                event_rows = project.db.execute('SELECT operation FROM debug_events ORDER BY sequence').fetchall()
                evidence['post_ready_event_operations'] = [row['operation'] for row in event_rows[ready_counts['debug_events']:]]
                assert evidence['post_ready_event_operations'] == [
                    'frame-probe', 'frame-probe', 'artifact', 'machine-capture-video-frame', 'frame-probe']
                command_counts = {command: sum(row['protocol'] == 'qmp' and row['command'] == command
                                               for row in calls) for command in (
                    QUERY_VIDEO, PROBE_VIDEO, EXPORT_VIDEO, ARM_INPUT, CANCEL_INPUT,
                    'x-fdisbull-start-video-frame', 'x-fdisbull-stop-video-frame',
                    'x-fdisbull-arm-video-frame', 'x-fdisbull-query-video-frame-fence',
                    'x-fdisbull-cancel-video-frame-fence', 'input-send-event',
                    'x-fdisbull-apply-frame-key-edges', 'x-fdisbull-arm-stopped-control',
                    'x-fdisbull-query-stopped-control', 'cont')}
                assert command_counts == {QUERY_VIDEO: 9 + exports, PROBE_VIDEO: 1, EXPORT_VIDEO: exports,
                    ARM_INPUT: 1, CANCEL_INPUT: 1, 'x-fdisbull-start-video-frame': 1,
                    'x-fdisbull-stop-video-frame': 0, 'x-fdisbull-arm-video-frame': 1,
                    'x-fdisbull-query-video-frame-fence': 2, 'x-fdisbull-cancel-video-frame-fence': 1,
                    'input-send-event': 0, 'x-fdisbull-apply-frame-key-edges': 0,
                    'x-fdisbull-arm-stopped-control': 0, 'x-fdisbull-query-stopped-control': 0, 'cont': 0}
                assert sum(row['protocol'] == 'qmp' and 'video-frame' in row['command'] for row in calls) == video_calls
                assert sum(row['protocol'] == 'gdb.execute' for row in calls) == 1
                writes = [row for row in calls if row['protocol'] == 'gdb.request'
                          and row['command'].startswith(('M', 'X'))]
                assert len(writes) == 1 and writes[0]['command'] == f'M{address:x},1:00'
                assert all('error' not in row for row in calls)
                evidence['command_counts'] = command_counts
                evidence['post_ready_counts'] = _counts(project)
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
            errors.append(AssertionError('Native frame-contract receipt exceeded 2 MiB'))
        else:
            receipt_path.write_bytes(raw)
        record_property('native_frame_contract_receipt', str(receipt_path))
        record_property('owners_reaped', int(evidence['owner_reaped']))
        if errors:
            if primary is not None:
                primary.add_note('Original-owner cleanup/receipt check: ' +
                                 '; '.join(type(error).__name__ for error in errors))
            else:
                raise errors[0]
