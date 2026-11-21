"""One retained-raster native witness for cooperative stopped-state observation.

This lane requires its separately reviewed owner controller and explicit,
hash-pinned prebuilt COM/baseline inputs. It never assembles or prepares media.
The controller owns bootstrap-inclusive deadlines, call/output limits and the
original process journal. This test records the actual post-setup exchanges.
Native/whole-machine revision, atomicity and legacy frame parity stay unknown.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import uuid

import pytest

from fdisbull.qemu_video_frame_state import (
    FORMAT, INPUT_PROFILE, VIDEO_FRAME_STATE_COMMANDS, VideoFrameStateRefusal,
)
from support.qemu_video_frame_fixture import HEIGHT, WIDTH, expected_rgb, frame_schedule
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record, read_bytes,
)
from test_qemu_video_frame_native import _assert_frame, _query, _timing


WORK_SECONDS, CLEANUP_SECONDS, SUPERVISOR_SECONDS = 60, 10, 180
OUTPUT_BYTES, RECEIPT_BYTES = 64 * 1024**2, 2 * 1024**2
MAX_NATIVE_CALLS, MAX_VIDEO_CALLS = 2048, 32
COM_SHA256 = '9cc1774468b3655ca49deee1b74f027935186bccd65fd9be0b18dc04bda18e9d'
BASELINE_SHA256 = '193be968235ba458bef8881d93deb43ce6bfcadc8995c01d079dfdabb6dca991'
PRODUCER_SHA256 = 'b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af'
FOOTER_NAMES = ('ready', 'dispatch', 'mutated', 'invalid', 'restored', 'blanked',
                'enabled', 'panned', 'unpanned', 'aba', 'command',
                'mutation_count', 'page_before', 'page_after', 'timing_raw')
FOOTER_VALUES = (260, 261, 341, 407, 419, 438, 457, 471, 485, 523,
                 710, 711, 712, 713, 714)
CLOCK_FIELDS = ('context', 'run', 'epoch', 'session', 'native_state',
                'clock_profile', 'counter', 'virtual_ns', 'virtual_clock')
QUERY_KEYS = 'x-fdisbull-query-frame-keys'
APPLY_KEYS = 'x-fdisbull-apply-frame-key-edges'
QUERY_INPUT = 'x-fdisbull-query-input'
EXPORT = 'x-fdisbull-export-video-frame'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(128 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _inputs(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_SOURCE_STATE') != '1':
        pytest.skip('The source-state native lane requires explicit owned-controller admission')
    assert getattr(request.config, '_fdisbull_source_state_owned_gate', None) == (
        'fdisbull-source-state-owned-gate-1'), 'Missing reviewed source-state owner gate'
    assert callable(getattr(request.config, '_fdisbull_source_state_post_setup', None))
    variables = dict(executable='FDISBULL_QEMU_CLOCK', firmware='FDISBULL_QEMU_CLOCK_FIRMWARE',
        mcopy='FDISBULL_QEMU_DOS_MCOPY', com='FDISBULL_SOURCE_STATE_COM',
        baseline='FDISBULL_SOURCE_STATE_BASELINE')
    missing = [name for name in variables.values() if not os.environ.get(name)]
    assert not missing, 'Required prebuilt native inputs are absent: ' + ', '.join(missing)
    paths = {}
    for name, variable in variables.items():
        path = Path(os.environ[variable]).expanduser()
        # Preserve the multicall mcopy invocation name instead of resolving it.
        paths[name] = path.absolute() if name == 'mcopy' else path.resolve(strict=True)
    assert paths['firmware'].is_dir()
    for name in ('executable', 'mcopy', 'com', 'baseline'):
        assert paths[name].is_file() and paths[name].stat().st_size <= 64 * 1024**2
    assert all(os.access(paths[name], os.X_OK) for name in ('executable', 'mcopy'))
    code = paths['com'].read_bytes()
    assert len(code) == 503 and _sha(code) == COM_SHA256
    assert code[-34:-30] == b'VFR1'
    values = struct.unpack('<15H', code[-30:])
    assert values == FOOTER_VALUES
    assert paths['baseline'].stat().st_size == 1474560
    assert _digest(paths['baseline']) == BASELINE_SHA256
    assert _digest(paths['executable']) == PRODUCER_SHA256
    pins = {name: dict(path=str(path), bytes=path.stat().st_size, sha256=_digest(path))
            for name, path in paths.items() if name != 'firmware'}
    pins['firmware'] = dict(path=str(paths['firmware']), controller_manifest_required=True)
    runtime = {name: paths[name] for name in ('executable', 'firmware', 'mcopy')}
    runtime['firmware'] = str(runtime['firmware'])
    disk = dict(image=paths['baseline'], prepared_sha256=BASELINE_SHA256)
    return paths, runtime, disk, code, dict(zip(FOOTER_NAMES, values, strict=True)), pins


def _clock(clock):
    # Passive read sequence/host timestamps are not guest-state identities.
    return {name: deepcopy(clock[name]) for name in CLOCK_FIELDS}


def _counts(project):
    return {table: project.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            for table in ('debug_artifacts', 'debug_events')}


def _owner(debug):
    vm = debug.vm
    return dict(vm=vm, process=vm.process, qmp=vm.qmp, gdb=vm.gdb,
                qmp_socket=vm.qmp.socket, gdb_socket=vm.gdb.socket,
                temporary=vm.temporary, lock=vm.lock)


def _current(debug, owner):
    vm = owner['vm']
    assert debug.vm is vm and vm.lock is owner['lock']
    assert all(getattr(vm, name) is owner[name] for name in ('process', 'qmp', 'gdb'))
    assert owner['qmp'].socket is owner['qmp_socket']
    assert owner['gdb'].socket is owner['gdb_socket']
    assert owner['process'].poll() is None


def _identity(debug, owner):
    _current(debug, owner)
    process = owner['process']
    # PID plus Linux birth ticks disambiguates reuse; object/channel IDs bind
    # this receipt to the exact Python owner and its independently logged pipe.
    stat = Path(f'/proc/{process.pid}/stat').read_bytes()
    assert len(stat) <= 65536
    ticks = int(stat.rsplit(b')', 1)[1].split()[19])
    return dict(pid=process.pid, process_start_ticks=ticks, run=debug.run_id,
                runtime_epoch=getattr(debug, '_runtime_epoch', None),
                checkpoint_epoch=getattr(debug, '_checkpoint_epoch', None),
                authority_lifetime=owner['vm'].observation_authority.lifetime,
                objects={name: id(value) for name, value in owner.items()})


@contextmanager
def _deadline(debug, owner, end):
    fields = [(debug, '_rpc_deadline'), (debug, '_deadline'),
              (owner['vm'], 'operation_deadline'),
              (owner['qmp'], 'operation_deadline'), (owner['gdb'], 'operation_deadline')]
    previous = [(obj, field, getattr(obj, field, None)) for obj, field in fields]
    end = min([end, *[value for _, _, value in previous if value is not None]])
    assert time.monotonic() < end
    for obj, field, _ in previous:
        setattr(obj, field, end)
    try:
        yield end
        _current(debug, owner)
        assert time.monotonic() < end, 'Native source-state work deadline expired'
    finally:
        for obj, field, value in reversed(previous):
            setattr(obj, field, value)


@contextmanager
def _record_calls(debug, owner, monkeypatch, evidence):
    """Delegate each actual call once; retain its exact arguments and reply."""
    qmp, remote = owner['qmp'], owner['gdb']
    qmp_call, request, execute = qmp.call, remote.request, remote.execute
    rows = evidence['native_calls']['records']

    def begin(protocol, command, arguments=None, timeout_ms=None):
        _current(debug, owner)
        assert len(rows) < MAX_NATIVE_CALLS
        row = dict(index=len(rows), protocol=protocol, command=command,
                   arguments=deepcopy(arguments), timeout_ms=timeout_ms)
        if protocol == 'qmp' and 'video-frame' in command:
            assert sum(item['protocol'] == 'qmp' and 'video-frame' in item['command']
                       for item in rows) < MAX_VIDEO_CALLS
        rows.append(row)
        return row

    def failed(row, error):
        row['error'] = dict(type=type(error).__name__, message=str(error)[:4096])

    @wraps(qmp_call)
    def qmp_observe(method, arguments=None, **kwargs):
        row = begin('qmp', method, arguments)
        row['options'] = deepcopy(kwargs)
        try:
            value = qmp_call(method, arguments, **kwargs)
            row['result'] = deepcopy(value)
            _current(debug, owner)
            return value
        except BaseException as error:
            failed(row, error)
            raise

    @wraps(request)
    def gdb_observe(command, timeout_ms=10000):
        raw = command.encode('ascii') if isinstance(command, str) else bytes(command)
        row = begin('gdb.request', raw.decode('ascii'), timeout_ms=timeout_ms)
        row['command_hex'] = raw.hex()
        try:
            value = request(command, timeout_ms=timeout_ms)
            row['result_hex'] = value.hex()
            _current(debug, owner)
            return value
        except BaseException as error:
            failed(row, error)
            raise

    @wraps(execute)
    def execute_observe(command, timeout_ms, **kwargs):
        raw = command.encode('ascii') if isinstance(command, str) else bytes(command)
        assert sum(row['protocol'] == 'gdb.execute' for row in rows) < 1
        row = begin('gdb.execute', raw.decode('ascii'), timeout_ms=timeout_ms)
        row['command_hex'] = raw.hex()
        row['after_send'] = kwargs.get('after_send') is not None
        try:
            reply, timed_out = execute(command, timeout_ms, **kwargs)
            row.update(result_hex=reply.hex(), timed_out=timed_out)
            _current(debug, owner)
            return reply, timed_out
        except BaseException as error:
            failed(row, error)
            raise

    with monkeypatch.context() as patch:
        patch.setattr(qmp, 'call', qmp_observe)
        patch.setattr(remote, 'request', gdb_observe)
        patch.setattr(remote, 'execute', execute_observe)
        try:
            yield rows
        finally:
            evidence['native_calls'].update(total=len(rows), video=sum(
                row['protocol'] == 'qmp' and 'video-frame' in row['command'] for row in rows))
            evidence['post_setup_execution'] = [deepcopy(row) for row in rows
                                                if row['protocol'] == 'gdb.execute']


def _host_neutral(host):
    assert host['valid'] is True and host['physical_state'] == 'not observed'
    assert host['pending'] == [] and host['leases'] == {}
    assert host['schedule'] is host['schedule_receipt'] is host['frame_key_owner'] is None


def _keyboard_neutral(native):
    assert native['active'] is False and native['valid'] is True
    assert native.get('token') is None and native['held'] == native['foreign-held'] == []
    assert native['modifier-mask'] == native['fifo-count'] == native['controller-pending'] == 0
    assert native['fifo-command-pointer'] == native['write-command'] == -1
    assert native['throttle-deadline-ns'] == -1 and not native['controller-status'] & 1
    assert native['scan-enabled'] is True and not native['controller-mode'] & 0x10


def _observation(value, native, address, data, expected_sha, first=None):
    assert value['format'] == FORMAT and value['complete'] is True
    assert value['stage'] == 'complete' and value['issues'] == []
    assert value['atomic'] is False
    for field in ('native_mutation_revision', 'application_frame_complete',
                  'frame_state_equivalence', 'legacy_phase_equivalence'):
        assert value[field] is None
    authority = value['authority']
    assert authority['scope'] == 'cooperative-owner-control'
    assert authority['valid'] is authority['complete'] is True
    assert authority['control_generation_before'] == authority['control_generation_after']
    assert authority['invalidation_reason'] is None and authority['events'] == []
    assert authority['atomic'] is False
    assert authority['native_state_revision'] is authority['whole_machine_state_revision'] is None
    assert authority['coverage'] == dict(bound_python_protocol_dispatch=True,
        admitted_public_operations=True, raw_handles=False,
        independent_controllers=False, native_device_mutations=False)
    source = value['source']
    assert source['source'] == 'qemu_completed_source_raster' and source['rgb_verified'] is True
    assert source['before'] == source['exported'] == source['after'] == native
    assert source['stream'] == native['token'] and source['frame_id'] == native['frame']['frame-id']
    assert source['pixel_sha256'] == expected_sha and source['rgb_bytes'] == WIDTH * HEIGHT * 3
    assert value['state_before'] == value['state_after']
    assert value['state_before']['ram'] == [dict(address=address, length=2, space='physical',
        data_hex=data.hex(), sha256=_sha(data))]
    assert value['selection']['ram_ranges'] == authority['selected_ram'] == [
        dict(address=address, length=2)]
    assert value['input']['profile'] == INPUT_PROFILE
    assert value['input']['before'] == value['input']['after']
    _host_neutral(value['input']['before']['host'])
    _keyboard_neutral(value['input']['before']['keyboard'])
    assert value['input']['before']['schedule'] == {
        'api-version': 1, 'epoch': value['clocks']['before']['virtual_clock']['native']['epoch'],
        'state': 'idle', 'virtual-ns': value['clocks']['before']['virtual_ns'], 'event-count': 0}
    assert all(value['input'][key] is None for key in
               ('mouse_state', 'all_devices_neutral', 'guest_consumed'))
    assert _clock(value['clocks']['before']) == _clock(value['clocks']['after'])
    assert value['status_before']['running'] is False
    if first is not None:
        assert _clock(value['clocks']['before']) == _clock(first['clocks']['before'])
        for field in ('cpu', 'registers', 'monitor'):
            assert value['state_before'][field] == first['state_before'][field]
        assert value['input'] == first['input'] and value['source'] == first['source']
        assert authority['owner_lifetime'] == first['authority']['owner_lifetime']


def _close_original(debug, owner):
    """Close only captured resources; the controller independently reaps them."""
    errors = []
    vm, process = owner['vm'], owner['process']
    try:
        same = debug.vm is vm and vm.process is process
        same = same and all(getattr(vm, name) is None or getattr(vm, name) is owner[name]
                            for name in ('qmp', 'gdb'))
        same = same and all(owner[name].socket is None or owner[name].socket is owner[name + '_socket']
                            for name in ('qmp', 'gdb'))
        if not same:
            raise AssertionError('Owner changed; refuse cleanup through replacement attributes')
        debug.close()
    except BaseException as error:
        errors.append(error)
    finally:
        # These are original handles, never a lookup through a changed client.
        for channel in (owner['qmp_socket'], owner['gdb_socket']):
            try:
                channel.close()
            except BaseException as error:
                errors.append(error)
        if process.poll() is None:
            errors.append(AssertionError('Production close left the original native owner live'))
            try:
                process.terminate()
                process.wait(timeout=3)
            except BaseException as error:
                errors.append(error)
                try:
                    process.kill()
                    process.wait(timeout=3)
                except BaseException as error:
                    errors.append(error)
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as error:
                    errors.append(error)
    assert process.poll() is not None, 'Original native owner was not reaped'
    if errors:
        raise errors[0]


def test_native_source_state_observation_tracks_stopped_mutation_and_refuses_native_input(
        tmp_path, request, monkeypatch, record_property):
    started_at = time.monotonic()
    paths, runtime, disk, code, offsets, pins = _inputs(request)
    # Compute the independent DAC/index oracle before any candidate raster.
    expected = expected_rgb()
    expected_sha = _sha(expected)
    assert len(expected) == WIDTH * HEIGHT * 3
    directory = tmp_path / 'source-state'
    directory.mkdir()
    assert not any((ancestor / '.git').exists() for ancestor in (directory, *directory.parents))
    receipt_path = tmp_path / 'native-source-state-observation.json'
    evidence = dict(format='fdisbull-native-source-state-observation-1', success=False,
        limits=dict(work_seconds=WORK_SECONDS, cleanup_seconds=CLEANUP_SECONDS,
            supervisor_seconds=SUPERVISOR_SECONDS, private_output_bytes=OUTPUT_BYTES,
            receipt_bytes=RECEIPT_BYTES, max_native_calls=MAX_NATIVE_CALLS,
            max_video_calls=MAX_VIDEO_CALLS, owners=1, streams=1, completed_rasters=1,
            successful_observations=3, native_input_refusals=1, post_setup_continues=1,
            guest_write_bytes=1, native_key_makes=1), inputs=pins, setup={},
        observations=[], mutation={}, native_input_refusal={},
        native_calls=dict(scope='post-setup; controller journal also covers bootstrap', records=[]),
        post_setup_execution=[], owner_reaped=False,
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
        assert owner['gdb'] is not None and owner['gdb'].register_description
        assert VIDEO_FRAME_STATE_COMMANDS | {APPLY_KEYS} <= set(owner['vm'].qmp_commands)
        with _deadline(debug, owner, started_at + WORK_SECONDS):
            info = process_record(debug)
            symbols = {name: com_address(info, offset) for name, offset in offsets.items()}
            baseline_breakpoints = deepcopy(debug.breakpoints)
            return_breakpoint = debug._return_breakpoint
            ready = debug._ready
            assert type(return_breakpoint) is str and return_breakpoint
            assert ready['type'] == 'ready'
            assert info['psp_segment'] == ready['child_psp']
            assert info['parent_psp_segment'] == ready['helper_psp']
            return_address = ready['helper_segment'] * 16 + ready['exit_wait_ip']
            # The DOS constructor reserves this lifecycle control, although
            # its shared machine-registry descriptor uses the tag 'user'.
            assert baseline_breakpoints == {return_breakpoint: dict(
                kind=1, access='x', length=1, owner='user', address=return_address)}
            assert return_address != symbols['ready']
            evidence['setup']['breakpoints'] = dict(baseline=baseline_breakpoints,
                return_breakpoint=return_breakpoint, return_address=return_address,
                helper_segment=ready['helper_segment'], exit_wait_ip=ready['exit_wait_ip'])
            parked = park(debug, symbols['ready'])  # Deletes its setup breakpoint before returning.
            parking_breakpoint, = parked['session']['stop_reason']['breakpoint_ids']
            assert parking_breakpoint not in baseline_breakpoints
            assert parking_breakpoint not in debug.breakpoints
            assert debug._return_breakpoint == return_breakpoint
            assert debug.breakpoints == baseline_breakpoints
            evidence['setup']['breakpoints'].update(parking_breakpoint=parking_breakpoint,
                after_parking=deepcopy(debug.breakpoints))
            with _record_calls(debug, owner, monkeypatch, evidence) as calls:
                request.config._fdisbull_source_state_post_setup(owner['vm'])
                evidence['owner_start'] = _identity(debug, owner)
                evidence['setup'].update(process=info, symbols=symbols, parked=parked,
                    prebuilt_com=True, baseline_prepared_before_case=True,
                    oracle=dict(pixel_sha256=expected_sha, rgb_bytes=len(expected),
                        method='authored VGA indices/DAC6 bit replication plus guest-read timing'))
                assert debug.capabilities['completed_guest_frames'] is False
                timing = _timing(debug, symbols)
                before = debug.clock_observe()
                initial_schedule = owner['qmp'].call(QUERY_INPUT)
                initial_keyboard = owner['qmp'].call(QUERY_KEYS)
                assert initial_schedule == {
                    'api-version': 1, 'epoch': before['virtual_clock']['native']['epoch'],
                    'state': 'idle', 'virtual-ns': before['virtual_ns'], 'event-count': 0}
                _keyboard_neutral(initial_keyboard)
                initial_host = deepcopy(getattr(owner['vm'], '_physical_input', None))
                assert getattr(owner['vm'], '_frame_key_owner', None) is None
                if initial_host is not None:
                    assert initial_host['valid'] is True
                    assert initial_host['pending'] == [] and initial_host['leases'] == {}
                    assert initial_host.get('schedule') is initial_host.get('schedule_receipt') is None
                evidence['setup']['initial_input'] = dict(schedule=initial_schedule,
                    keyboard=initial_keyboard, host=initial_host, host_frame_key_owner=None)
                schedule = frame_schedule(timing, before['virtual_ns'])
                evidence['setup']['schedule'] = deepcopy(schedule)
                stream = debug.video_frame_start(timeout_ms=1000)
                advance = debug.video_frame_advance(timeout_ms=5000)
                native = _query(debug)
                frame = _assert_frame(native, schedule, expected)
                evidence['setup'].update(stream=stream, advance=advance, source=native)
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
                assert read_bytes(debug, symbols['command'], 1) == b'\x00'
                assert read_bytes(debug, symbols['mutation_count'], 1) == b'\x00'
                address = symbols['page_before']
                assert symbols['page_after'] == address + 1
                options = dict(ram_ranges=[dict(address=address, length=2)],
                    stream=stream['stream'], frame_id=frame['frame-id'], timeout_ms=2000)

                def observe(data):
                    counts = _counts(project)
                    begin = len(calls)
                    value = debug.video_frame_state_observe(**options)
                    evidence['observations'].append(value)
                    _observation(value, native, address, data, expected_sha,
                                 evidence['observations'][0])
                    assert _counts(project) == counts
                    assert not list(Path(owner['temporary'].name).glob('video-frame-*.ppm'))
                    exports = [row for row in calls[begin:]
                               if row['protocol'] == 'qmp' and row['command'] == EXPORT]
                    assert len(exports) == 1
                    return value

                first = observe(b'\x00\x00')
                observe(b'\x00\x00')
                remote, authority = owner['gdb'], owner['vm'].observation_authority
                with owner['lock']:
                    _current(debug, owner)
                    assert authority._active is None
                    assert remote.memory(address, 2, space='physical') == b'\x00\x00'
                    begin = len(calls)
                    generation_before = authority.control_generation
                    readback = remote.memory(address, 1, space='physical', data=b'\x5a')
                    generation_after = authority.control_generation
                    # No public operation or extra read lies inside these two samples.
                    evidence['mutation'] = dict(address=address, space='physical',
                        before_hex='00', written_hex='5a', readback_hex=readback.hex(),
                        control_generation_before=generation_before,
                        control_generation_after=generation_after,
                        generation_scope='cooperative control admission; not a native mutation count',
                        native_call_begin=begin, native_call_end=len(calls))
                assert readback == b'\x5a' and generation_after > generation_before
                writes = [row for row in calls[begin:] if row['protocol'] == 'gdb.request'
                          and row['command'].startswith('M')]
                assert len(writes) == 1
                assert writes[0]['command'] == f'M{address:x},1:5a'
                assert writes[0]['result_hex'] == b'OK'.hex()
                third = observe(b'\x5a\x00')
                assert third['authority']['control_generation_before'] >= generation_after
                assert _clock(first['clocks']['before']) == _clock(third['clocks']['after'])

                qmp = owner['qmp']
                idle = qmp.call(QUERY_KEYS)
                _keyboard_neutral(idle)
                assert getattr(owner['vm'], '_frame_key_owner', None) is None
                token = uuid.uuid4().hex
                arguments = {'token': token, 'expected-generation': idle['generation'],
                             'edges': [{'key': 'a', 'pressed': True}]}
                applied = qmp.call(APPLY_KEYS, arguments)
                assert applied['active'] is applied['valid'] is True
                assert applied['token'] == token and applied['epoch'] == idle['epoch']
                assert applied['generation'] == idle['generation'] + 1
                assert applied['accepted-edges'] == idle['accepted-edges'] + 1
                assert applied['held'] == ['a'] and applied['foreign-held'] == []
                assert applied['fifo-count'] or applied['controller-status'] & 1
                assert getattr(owner['vm'], '_frame_key_owner', None) is None
                counts, begin = _counts(project), len(calls)
                with pytest.raises(VideoFrameStateRefusal) as caught:
                    debug.video_frame_state_observe(**options)
                end = len(calls)
                error = caught.value
                refusal = getattr(error, 'video_frame_state_evidence', None)
                if refusal is None:
                    refusal = error.result
                evidence['native_input_refusal'] = dict(code=error.code, evidence=refusal,
                    native_before=idle, arguments=arguments, native_applied=applied,
                    native_call_begin=begin, native_call_end=end)
                assert error.code == 'native_keyboard_owner_active'
                assert refusal['complete'] is False and refusal['stage'] == 'input-before'
                assert refusal['source'] is None and refusal['state_before'] == refusal['state_after'] == {}
                assert refusal['input']['before']['keyboard'] == applied
                assert refusal['input']['before']['schedule'] == first['input']['before']['schedule']
                _host_neutral(refusal['input']['before']['host'])
                assert refusal['authority']['valid'] is True and refusal['authority']['complete'] is False
                assert refusal['authority']['invalidation_reason'] is None
                assert _clock(refusal['clocks']['before']) == _clock(first['clocks']['before'])
                refused_calls = calls[begin:end]
                assert all(row['protocol'] == 'qmp' for row in refused_calls)
                commands = [row['command'] for row in refused_calls]
                assert commands[-2:] == [QUERY_INPUT, QUERY_KEYS]
                assert set(commands) <= {'query-status', 'query-replay',
                                         'x-fdisbull-query-clock', QUERY_INPUT, QUERY_KEYS}
                assert _counts(project) == counts
                assert not list(Path(owner['temporary'].name).glob('video-frame-*.ppm'))
                assert authority._active is None and authority._cleanup_owner is None
                _current(debug, owner)
                after_keys = qmp.call(QUERY_KEYS)
                after_schedule = qmp.call(QUERY_INPUT)
                after_clock = qmp.call('x-fdisbull-query-clock')
                after_counter = qmp.call('query-replay')
                after_registers = remote.registers()
                after_monitor = qmp.call('human-monitor-command', {'command-line': 'info registers'})
                assert after_keys == applied
                assert after_schedule == first['input']['before']['schedule']
                assert after_clock == first['clocks']['before']['virtual_clock']['native']
                assert after_counter == first['clocks']['before']['counter']['native']
                assert after_registers == first['state_before']['registers']
                assert after_monitor == first['state_before']['monitor']
                assert getattr(owner['vm'], '_frame_key_owner', None) is None
                evidence['native_input_refusal'].update(native_after=after_keys,
                    schedule_after=after_schedule, clock_after=after_clock,
                    counter_after=after_counter, registers_after=after_registers,
                    monitor_after=after_monitor, host_owner_after=None)
                assert len(evidence['observations']) == 3
                assert sum(row['protocol'] == 'gdb.request' and row['command'].startswith('M')
                           for row in calls) == 1
                assert sum(row['protocol'] == 'qmp' and row['command'] == APPLY_KEYS
                           for row in calls) == 1
                assert sum(row['protocol'] == 'qmp' and row['command'] == EXPORT
                           for row in calls) == 3
                assert sum(row['protocol'] == 'qmp' and row['command'] == 'x-fdisbull-start-video-frame'
                           for row in calls) == 1
                assert sum(row['protocol'] == 'gdb.execute' for row in calls) == 1
                assert debug._return_breakpoint == return_breakpoint
                assert debug.breakpoints == baseline_breakpoints
                evidence['setup']['breakpoints']['before_close'] = deepcopy(debug.breakpoints)
                evidence['owner_end'] = _identity(debug, owner)
                assert evidence['owner_start'] == evidence['owner_end']
        body_complete = True
    except BaseException as error:
        primary = error
        evidence['error'] = dict(type=type(error).__name__, message=str(error)[:4096])
        raise
    finally:
        cleanup_started = time.monotonic()
        cleanup_errors = []
        if owner is not None:
            try:
                _close_original(debug, owner)
            except BaseException as error:
                cleanup_errors.append(error)
            evidence['owner_reaped'] = owner['process'].poll() is not None
            evidence['owner_returncode'] = owner['process'].returncode
        if project is not None:
            try:
                project.db.close()
            except BaseException as error:
                cleanup_errors.append(error)
        try:
            assert _digest(paths['com']) == COM_SHA256
            assert _digest(paths['baseline']) == BASELINE_SHA256
            if binary is not None:
                assert binary.read_bytes() == code
            evidence['inputs_unchanged'] = True
            assert time.monotonic() - cleanup_started <= CLEANUP_SECONDS
        except BaseException as error:
            cleanup_errors.append(error)
        evidence['elapsed_seconds'] = time.monotonic() - started_at
        evidence['cleanup_seconds'] = time.monotonic() - cleanup_started
        evidence['cleanup_errors'] = [dict(type=type(error).__name__, message=str(error)[:4096])
                                      for error in cleanup_errors]
        evidence['success'] = body_complete and not cleanup_errors and evidence['owner_reaped']
        raw = json.dumps(evidence, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
        if len(raw) > RECEIPT_BYTES:
            overflow = dict(format=evidence['format'], success=False,
                error=dict(type='ReceiptOverflow', bytes=len(raw), sha256=_sha(raw)),
                owner_reaped=evidence['owner_reaped'], limits=evidence['limits'],
                raw_evidence='Retained by the independently bounded controller journal')
            receipt_path.write_text(json.dumps(overflow, sort_keys=True), encoding='utf-8')
            cleanup_errors.append(AssertionError('Native source-state receipt exceeded 2 MiB'))
        else:
            receipt_path.write_bytes(raw)
        record_property('native_source_state_receipt', str(receipt_path))
        record_property('owners_reaped', int(evidence['owner_reaped']))
        if cleanup_errors:
            if primary is not None:
                primary.add_note('Original-owner cleanup/receipt check: ' +
                                 '; '.join(type(error).__name__ for error in cleanup_errors))
            else:
                raise cleanup_errors[0]
