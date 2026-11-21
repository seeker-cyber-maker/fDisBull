"""Two serial native owners for an explicitly bounded source-raster comparison.

This is an opt-in proposed gate, not part of ordinary native discovery. Exact
DOSBox/QEMU producer hashes are mandatory. A separately reviewed controller must
own process/log/storage deadlines before execution. No image tunes the pulse.
Quiet functional evidence is saved even when phase timing remains unqualified.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.paired_video_frame_fixture import (
    CONTROL_BYTES, EDGE_BYTES, TRIAL_BYTES, paired_video_program, parse_control,
)
from support.paired_video_frame_oracle import (
    HEIGHT, RAW_FIELDS, SOURCE_PHASE, WIDTH, TimingUnqualified,
    horizontal_interval, parse_calibration, parse_trial, phase_predictions,
    pulse_parameters, rgb_for_rows, vga_geometry,
)
from test_qemu_dos_process_native import com_address


QEMU_SHA256 = 'b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af'
DOSBOX_SHA256 = 'bfdacbed027ae16f48256abc5d0309cc8984569a2946dabea2f4d43907d43e71'
QEMU_IMG_SHA256 = 'b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03'
WORK_SECONDS, CLEANUP_SECONDS = 45, 10
OUTPUT_LIMIT = 128 * 1024**2
LOG_LIMIT = 2 * 1024**2
POINTS = [[0, y] for y in range(HEIGHT)] + [[319, 0], [319, 199]]
PROFILE = ('cpu core=normal', 'cpu cycles=fixed 157600',
           'render frameskip=0', 'render doublescan=false', 'render scaler=none',
           'video scanline render on demand=false',
           'video skip render if nothing changed=false', 'vsync vsyncmode=off')


def _remaining(deadline, maximum=5000):
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise TimeoutError('Paired video owner exhausted its single work deadline')
    return min(remaining, maximum)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def _decode_png(data):
    if len(data) > 2 * 1024**2:
        raise ValueError('Paired native screenshot exceeded its fixed byte cap')
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (WIDTH, HEIGHT)
        image.load()
        rgb = image.convert('RGB').tobytes()
    assert len(rgb) == WIDTH * HEIGHT * 3
    return rgb


def _probe_pixels(samples, rgb):
    assert [(point['x'], point['y']) for point in samples] == [tuple(point) for point in POINTS]
    for point in samples:
        offset = (point['y'] * WIDTH + point['x']) * 3
        assert point['rgb'] == list(rgb[offset:offset + 3])


def _private_output(directory):
    for parent in (directory, *directory.parents):
        assert not (parent / '.git').exists(), 'Paired native output must have no Git ancestor'
    return directory


@pytest.fixture
def paired_video_runtime(tmp_path):
    enabled = os.environ.get('FDISBULL_REQUIRE_PAIRED_VIDEO_FRAME') == '1'
    selected = {
        'qemu': os.environ.get('FDISBULL_PAIRED_VIDEO_QEMU'),
        'dosbox': os.environ.get('FDISBULL_PAIRED_VIDEO_DOSBOX'),
        'boot': os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE'),
        'mcopy': os.environ.get('FDISBULL_QEMU_DOS_MCOPY'),
        'firmware': os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'),
        'qemu_img': os.environ.get('FDISBULL_QEMU_IMG'),
        'nasm': os.environ.get('NASM'),
    }
    missing = [name for name, value in selected.items() if not value]
    if not enabled:
        pytest.skip('Separate paired-video native admission is not enabled')
    if missing:
        pytest.fail('Required paired-video inputs missing: ' + ', '.join(missing))
    _private_output(tmp_path.resolve())
    runtime = {name: Path(value).expanduser().absolute() for name, value in selected.items()}
    for name, path in runtime.items():
        assert path.is_dir() if name == 'firmware' else path.is_file(), (name, path)
        if name not in ('boot', 'firmware'):
            assert os.access(path, os.X_OK)
    for name, expected in (('qemu', QEMU_SHA256), ('dosbox', DOSBOX_SHA256), ('qemu_img', QEMU_IMG_SHA256)):
        assert digest(runtime[name]) == expected, 'Wrong pinned producer: ' + name
    runtime['boot_sha256'] = digest(runtime['boot'])
    runtime['disk'] = prepare_dos_baseline(runtime['boot'], tmp_path / 'paired-video-boot.img',
        runtime['mcopy'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    wrapper = tmp_path / 'paired-video-dosbox-profile'
    arguments = [part for setting in PROFILE for part in ('-set', setting)]
    # Write plain Python literals, preserving the inherited pipe descriptors.
    wrapper.write_text('#!' + sys.executable + '\nimport os, sys\n'
        + f'executable = {str(runtime["dosbox"])!r}\n'
        + f'os.execv(executable, [executable, *sys.argv[1:], *{arguments!r}])\n')
    wrapper.chmod(0o700)
    runtime['wrapper'] = wrapper
    return runtime


class _DosboxOwner:
    def __init__(self, rpc, directory, offsets, deadline):
        self.rpc, self.directory, self.offsets, self.deadline = rpc, directory, offsets, deadline
        started = rpc.call('session.start', {
            'target': {'command': 'PAIRVID.COM', 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(directory)}], 'break_at': 'entry'},
            timeout_ms=_remaining(deadline, 15000))
        self.sid = started['session_id']
        registers = self.call('state.get_registers')
        assert registers['cpu_mode'] == 'real' and int(registers['instruction_pointer'], 16) == 0x100
        self.cs = registers['segments']['cs']
        self.mode_id = None
        self.call('execution.timing', {'fast_forward': False})
        self.fault_breakpoint = self.call('breakpoints.create', {
            'kind': 'execution', 'address': self.address(offsets['fault_stop']), 'once': False})

    def call(self, method, params=None):
        return self.rpc.call(method, {'session_id': self.sid, **(params or {})},
                             timeout_ms=_remaining(self.deadline))

    def address(self, offset):
        return {'space': 'segmented', 'segment': self.cs, 'offset': f'0x{offset:08x}'}

    def read(self, offset, length):
        value = self.call('memory.read', {'address': self.address(offset), 'length': length})
        data = base64.b64decode(value['data_base64'], validate=True)
        assert len(data) == length and _sha(data) == value['sha256']
        return data

    def write(self, name, data):
        offset = self.offsets[name]
        old = self.read(offset, len(data))
        self.call('memory.write', {'address': self.address(offset), 'expected_sha256': _sha(old),
                                  'data_base64': base64.b64encode(data).decode('ascii')})
        assert self.read(offset, len(data)) == data

    def park(self, name):
        point = self.call('breakpoints.create', {'kind': 'execution', 'once': True,
                         'address': self.address(self.offsets[name])})
        operation = self.call('execution.continue')
        # One bounded wait per 250ms, at most180 reads under the owner deadline.
        for _ in range(180):
            value = self.call('execution.wait', {'operation_id': operation['operation_id'],
                                                'timeout_ms': min(250, _remaining(self.deadline))})
            if not value.get('running'):
                break
        assert not value.get('running') and value['state'] == 'stopped'
        assert value['stop_reason']['kind'] == 'breakpoint'
        assert value['stop_reason']['breakpoint_id'] == point['breakpoint_id']
        registers = self.call('state.get_registers')
        assert int(registers['instruction_pointer'], 16) == self.offsets[name]
        return value

    def start(self):
        return None

    def before_frame(self):
        value = self.call('video.probe', {'points': []})
        if self.mode_id is None:
            self.mode_id = value['mode_id']
        assert value['mode_id'] == self.mode_id, 'Legacy capture generation changed during the declared steady profile'
        return value

    def advance(self, baseline):
        result = self.call('frame.step')
        status = self.call('session.status')
        assert result['completed'] is True and result['stop_reason']['kind'] == 'frame'
        assert status['state'] == 'stopped' and status['state_revision'] == result['state_revision']
        assert result['frame_id'] == baseline['frame_id'] + 1
        assert result['mode_id'] == baseline['mode_id'] == self.mode_id
        return result

    def stopped(self):
        return {'registers': self.call('state.get_registers'), 'timing': self.call('execution.timing'),
                'status': self.call('session.status'),
                'control': self.read(self.offsets['control'], CONTROL_BYTES).hex(),
                'trial': self.read(self.offsets['trial'], TRIAL_BYTES).hex()}

    def capture(self, number, advance):
        before = self.stopped()
        probe = self.call('video.probe', {'points': POINTS})
        screenshot = self.call('video.screenshot')
        data = base64.b64decode(screenshot.pop('png_base64'), validate=True)
        assert screenshot['format'] == 'png' and _sha(data) == screenshot['sha256']
        assert probe['source'] == screenshot['source'] == 'last_completed_guest_frame'
        for item in (probe, screenshot):
            assert item['frame_id'] == advance['frame_id'] and item['mode_id'] == advance['mode_id']
            assert (item['width'], item['height'], item['source_bpp']) == (WIDTH, HEIGHT, 32)
            assert item['state_revision'] == advance['state_revision']
        repeated = self.call('video.probe', {'points': POINTS})
        assert repeated == probe and self.stopped() == before
        rgb = _decode_png(data)
        _probe_pixels(probe['samples'], rgb)
        (self.directory / f'frame-{number}.png').write_bytes(data)
        return rgb, {'advance': advance, 'probe': probe, 'image': screenshot,
                     'stopped': before, 'passive_guest_state_equal': True}


class _QemuOwner:
    def __init__(self, project, debug, directory, offsets, deadline):
        self.project, self.debug, self.directory, self.deadline = project, debug, directory, deadline
        self.vm = debug.vm
        self.vm.operation_deadline = deadline
        for channel in (self.vm.qmp, self.vm.gdb):
            existing = getattr(channel, 'operation_deadline', None)
            channel.operation_deadline = deadline if existing is None else min(deadline, existing)
        info = debug.dos_process_info()
        self.offsets = {name: com_address(info, value) for name, value in offsets.items()}
        self.fault_breakpoint = debug.breakpoint(self.offsets['fault_stop'])

    def read(self, offset, length):
        _remaining(self.deadline)
        data = bytes.fromhex(self.debug.memory(offset, length=length, space='physical')['hex'])
        assert len(data) == length
        return data

    def write(self, name, data):
        address = self.offsets[name]
        old = self.read(address, len(data))
        self.debug.write_memory(address, data.hex(), expected_hex=old.hex(), space='physical')
        assert self.read(address, len(data)) == data

    def park(self, name):
        point = self.debug.breakpoint(self.offsets[name])
        try:
            value = self.debug.run(timeout_ms=_remaining(self.deadline))
            assert value['outcome'] == 'breakpoint' and not value['timed_out']
            assert point['breakpoint_id'] in value['session']['stop_reason']['breakpoint_ids']
            return value
        finally:
            self.debug.delete_breakpoint(point['breakpoint_id'])

    def start(self):
        return self.debug.video_frame_start(timeout_ms=_remaining(self.deadline))

    def before_frame(self):
        value = self.debug.video_frame_observe(timeout_ms=_remaining(self.deadline))
        assert value['state'] == 'observing' and value['native']['rows-sampled'] == 0
        return value

    def advance(self, baseline):
        value = self.debug.video_frame_advance(timeout_ms=_remaining(self.deadline))
        assert value['advance_completed'] is True and value['completed_source_raster'] is True
        assert value['stop_consumed'] is True
        assert value['frame']['frame-id'] == baseline['frame_sequence'] + 1
        assert value['frame']['stream-generation'] == baseline['stream_generation']
        assert value['legacy_phase_equivalence'] is None and value['application_frame_complete'] is None
        return value

    def stopped(self):
        clock = self.debug.clock_observe()
        stable_clock = {name: clock[name] for name in (
            'run', 'epoch', 'virtual_ns', 'counter', 'native_state', 'clock_profile', 'virtual_clock')}
        return {'registers': self.debug.registers(), 'clock': stable_clock,
                'control': self.read(self.offsets['control'], CONTROL_BYTES).hex(),
                'trial': self.read(self.offsets['trial'], TRIAL_BYTES).hex()}

    def capture(self, number, advance):
        before = self.stopped()
        probe = self.debug.video_frame_probe(POINTS, timeout_ms=_remaining(self.deadline))
        image = self.debug.capture_video_frame(f'paired-{number}.png', max_bytes=2 * 1024**2,
                                              timeout_ms=_remaining(self.deadline))
        destination = self.directory / f'frame-{number}.png'
        self.project.debug_export(image['artifact'], destination)
        data = destination.read_bytes()
        metadata = image['metadata']
        assert metadata['source'] == 'qemu_completed_source_raster' and metadata['sha256'] == _sha(data)
        assert probe['frame'] == advance['frame'] == metadata['frame']
        repeated = self.debug.video_frame_probe(POINTS, timeout_ms=_remaining(self.deadline))
        for field in ('native', 'frame', 'samples', 'run', 'epoch', 'stream', 'stream_generation', 'frame_id'):
            assert repeated[field] == probe[field]
        assert self.stopped() == before
        rgb = _decode_png(data)
        assert _sha(rgb) == advance['frame']['pixel-sha256']
        _probe_pixels(probe['samples'], rgb)
        return rgb, {'advance': advance, 'probe': probe, 'repeated_probe': repeated, 'image': image,
                     'stopped': before, 'passive_guest_state_equal': True}


def _copy_log_snapshot(path, destination):
    if path.is_file():
        assert path.stat().st_size <= LOG_LIMIT
        with path.open('rb') as source, destination.open('xb') as target:
            shutil.copyfileobj(source, target)
        return {'sha256': digest(destination), 'bytes': destination.stat().st_size,
                'scope': 'before-close snapshot; complete logs require the independent owner controller'}
    return None


@contextmanager
def _owner(backend, directory, code, offsets, runtime, evidence):
    deadline = time.monotonic() + WORK_SECONDS
    source = directory / 'PAIRVID.COM'
    source.write_bytes(code)
    process = None
    cleanup_start = None
    try:
        if backend == 'dosbox':
            rpc = None

            def spawned(owner):
                nonlocal process
                process = owner
                evidence['pid'] = owner.pid

            try:
                rpc = DOSBoxRPC(runtime['wrapper'], directory, on_spawn=spawned)
                evidence['profile'] = list(PROFILE)
                adapter = _DosboxOwner(rpc, directory, offsets, deadline)
                assert adapter.read(0x100, 16) == code[:16]
                yield adapter
            finally:
                cleanup_start = time.monotonic()
                if rpc is not None:
                    try:
                        evidence['log_snapshot'] = _copy_log_snapshot(
                            Path(rpc.temporary.name) / 'emulator.log', directory / 'emulator-before-close.log')
                    finally:
                        rpc.close()
        else:
            with Project.create(directory / 'paired.fdb', source, image='com') as project:
                with project.debugger(runtime['qemu'], directory, backend='qemu-dos',
                        dos_boot_image=str(runtime['disk']['image']), dos_mcopy=str(runtime['mcopy']),
                        qemu_firmware=str(runtime['firmware']), qemu_transport='pipe',
                        qemu_checkpoint_tool=str(runtime['qemu_img']), qemu_clock='virtual',
                        qemu_retrace='precise', boot_timeout_ms=_remaining(deadline, 15000)) as debug:
                    process = debug.vm.process
                    evidence['pid'] = process.pid
                    try:
                        adapter = _QemuOwner(project, debug, directory, offsets, deadline)
                        yield adapter
                    finally:
                        cleanup_start = time.monotonic()
                        if debug.vm.temporary is not None:
                            root = Path(debug.vm.temporary.name)
                            evidence['log_snapshots'] = {name: _copy_log_snapshot(root / name,
                                directory / ('before-close-' + name)) for name in ('qemu.log', 'boot.log')}
    finally:
        if process is not None:
            evidence.update(returncode=process.poll(), reaped=process.poll() is not None,
                            cleanup_seconds=(time.monotonic() - cleanup_start if cleanup_start else None))
            assert evidence['reaped']
            if evidence['cleanup_seconds'] is not None:
                assert evidence['cleanup_seconds'] <= CLEANUP_SECONDS
        assert source.read_bytes() == code


def _calibration(adapter, evidence):
    evidence['calibration_stop'] = adapter.park('calibration_done')
    control_raw = adapter.read(adapter.offsets['control'], CONTROL_BYTES)
    control = parse_control(control_raw)
    timing_raw = adapter.read(adapter.offsets['timing_raw'], len(RAW_FIELDS))
    raw = (adapter.read(adapter.offsets['calibration'], control['calibration_count'] * EDGE_BYTES)
           if control['calibration_count'] else b'')
    evidence['calibration'] = {'control': control, 'control_raw': control_raw.hex(),
                               'timing_raw': timing_raw.hex(), 'edges_raw': raw.hex()}
    try:
        geometry = vga_geometry(timing_raw)
        records = parse_calibration(raw, control['calibration_count'])
        horizontal, receipt = horizontal_interval(records, geometry['horizontal_coarse'])
        parameters = pulse_parameters(geometry, horizontal)
        evidence['calibration'].update(receipt=receipt, parameters=parameters,
            geometry={name: value for name, value in geometry.items() if name != 'horizontal_coarse'})
        return geometry, horizontal, parameters
    except TimingUnqualified as error:
        evidence['phase'] = {'state': 'unqualified', 'reason': str(error), 'image_feedback': False}
        return None


def _exercise(adapter, backend, directory, evidence):
    timing = _calibration(adapter, evidence)
    evidence['stream_start'] = adapter.start()
    evidence['frames'] = []
    # Parameter selection precedes ALL image observations. Never rerun the
    # calibration or choose another pulse after looking at candidate pixels.
    if timing is not None:
        geometry, horizontal, parameters = timing
        adapter.write('delay_ticks', struct.pack('<H', parameters['delay_ticks']))
        adapter.write('width_ticks', struct.pack('<H', parameters['width_ticks']))
    for number in range(1, 5 if timing is not None else 3):
        mode = int(number > 2)
        adapter.write('pulse_mode', bytes([mode]))
        adapter.write('command', b'\x01')
        ready_stop = adapter.park('trial_ready')
        ready_raw = adapter.read(adapter.offsets['trial'], TRIAL_BYTES)
        ready = parse_trial(ready_raw)
        assert (ready['number'], ready['mode']) == (number, mode) and ready['ready_status'] & 8
        before = adapter.before_frame()
        advance = adapter.advance(before)
        frame_stop_trial = parse_trial(adapter.read(adapter.offsets['trial'], TRIAL_BYTES))
        assert frame_stop_trial['post_generation'] == 0, 'Frame control ran beyond the post-display journal'
        rgb, receipt = adapter.capture(number, advance)
        (directory / f'frame-{number}.rgb').write_bytes(rgb)
        record = {'number': number, 'kind': 'pulse' if mode else 'quiet', 'ready_stop': ready_stop,
                  'ready_journal_raw': ready_raw.hex(), 'before': before, 'capture': receipt,
                  'rgb_sha256': _sha(rgb), 'rgb_bytes': len(rgb),
                  'image_captured_before_post_display_continuation': True}
        evidence['frames'].append(record)
        if not mode:
            assert rgb == rgb_for_rows(['A'] * HEIGHT)
            assert rgb != rgb_for_rows(['A'] * HEIGHT, wrong_qemu_dac=True)
            record['full_authored_rgb_equal'] = True
            if number == 2:
                evidence['functional_completed_source_api_qualified'] = True
        # The original image/revision is frozen above. The later stop supplies
        # the SAME frame's independent post-display vertical edge only.
        record['post_display_stop'] = adapter.park('trial_done')
        trial_raw = adapter.read(adapter.offsets['trial'], TRIAL_BYTES)
        trial = parse_trial(trial_raw)
        record['journal_raw'], record['journal'] = trial_raw.hex(), trial
        assert (trial['number'], trial['mode']) == (number, mode)
        assert trial['ready_generation'] == ready['ready_generation']
        assert trial['post_generation'] == ready['ready_generation'] + 1
        control = parse_control(adapter.read(adapter.offsets['control'], CONTROL_BYTES))
        assert control['command'] == 0
        record['control_after_post_display'] = control
        if mode:
            try:
                predictions, windows = phase_predictions(horizontal, geometry, trial)
                record['phase_oracle'] = {'windows': windows,
                    'predictions': {str(phase): dict(value, rgb=_sha(value['rgb']))
                                    for phase, value in predictions.items()}}
                if backend == 'qemu':
                    frame = advance['frame']
                    # Receipt only checks admission to the stricter experiment;
                    # it never chooses an expected color, row or timestamp.
                    if any(8 * (row['actual-ns'] - row['intended-ns']) >= frame['line-period-ns']
                           for row in frame['rows']):
                        raise TimingUnqualified('Valid v1 callback lateness exceeds this phase experiment H/8 gate')
                phase = SOURCE_PHASE[backend]
                if rgb != predictions[phase]['rgb']:
                    record['phase_result'] = {'state': 'mismatch', 'expected_phase': phase,
                        'matches_other_frozen_phase': rgb == predictions[1 - phase]['rgb']}
                else:
                    assert rgb != predictions[1 - phase]['rgb']
                    assert rgb != rgb_for_rows(['C'] * HEIGHT)
                    record['phase_result'] = {'state': 'observed', 'phase': phase,
                        'meaning': 'Full RGB matches the fixed source-derived phase family and rejects its counterfactual',
                        'callback_lateness': ('native receipt checked below H/8' if backend == 'qemu' else
                                              'H/8 is a declared experimental assumption; individual row times are unobserved'),
                        'final_palette_snapshot_rejected': True}
            except TimingUnqualified as error:
                record['phase_result'] = {'state': 'unqualified', 'reason': str(error),
                                         'expected_phase': SOURCE_PHASE[backend]}
    quiet = evidence['frames'][:2]
    evidence['functional_completed_source_api_qualified'] = (
        len(quiet) == 2 and all(frame.get('full_authored_rgb_equal') is True for frame in quiet))
    pulses = evidence['frames'][2:]
    if timing is not None:
        states = [frame['phase_result']['state'] for frame in pulses]
        evidence['phase'] = {'state': 'observed' if states == ['observed', 'observed'] else
                            ('mismatch' if 'mismatch' in states else 'unqualified'),
                            'source_phase': SOURCE_PHASE[backend], 'trial_states': states,
                            'image_feedback': False}


def test_native_paired_mode13_completed_rasters_have_independent_phase_witness(tmp_path, paired_video_runtime, record_property):
    runtime = paired_video_runtime
    code, offsets = paired_video_program(tmp_path, runtime['nasm'])
    result = {'format': 'fdisbull-paired-mode13-source-1', 'success': False,
        'fixture_sha256': _sha(code), 'fixture_bytes': len(code), 'symbols': offsets,
        'producers': {'dosbox': DOSBOX_SHA256, 'qemu': QEMU_SHA256},
        'limits': {'maximum_vm_lifetimes': 2, 'maximum_live_owners': 1,
                   'owner_work_seconds': WORK_SECONDS, 'owner_cleanup_seconds': CLEANUP_SECONDS,
                   'frame_calls_per_owner': 4, 'calibration_edges': 512,
                   'calibration_retraces': 4, 'total_retraces_per_owner': 12,
                   'output_bytes': OUTPUT_LIMIT},
        'same_com_bytes': True, 'guest_control_writes_only': True,
        'no_sampling_policy_change': True, 'image_feedback': False, 'backends': {}}
    record_property('paired_fixture_sha256', _sha(code))
    record_property('native_owner_ceiling', 2)
    try:
        for backend in ('dosbox', 'qemu'):
            if result['backends']:
                assert all(item.get('reaped') is True for item in result['backends'].values())
            directory = tmp_path / backend
            directory.mkdir()
            evidence = result['backends'][backend] = {}
            with _owner(backend, directory, code, offsets, runtime, evidence) as adapter:
                _exercise(adapter, backend, directory, evidence)
        assert all(item['functional_completed_source_api_qualified'] for item in result['backends'].values())
        result['functional_completed_source_api_qualified'] = True
        assert all(result['backends']['dosbox']['frames'][index]['rgb_sha256'] ==
                   result['backends']['qemu']['frames'][index]['rgb_sha256'] for index in (0, 1))
        result['quiet_cross_backend_rgb_equal'] = True
        phase = {backend: evidence['phase'] for backend, evidence in result['backends'].items()}
        result['phase_disposition'] = phase
        assert all(item['state'] == 'observed' for item in phase.values()), (
            'Quiet completed-source/API facts passed; the separate phase gate is not qualified', phase)
        result['backend_source_phase_equal'] = False
        result['exact_dynamic_image_equivalence_claim'] = False
        result['application_frame_complete'] = None
        result['frame_state_equivalence'] = None
        result['success'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        result['boot_input_unchanged'] = digest(runtime['boot']) == runtime['boot_sha256']
        result['private_baseline_unchanged'] = digest(runtime['disk']['image']) == runtime['disk']['prepared_sha256']
        total = sum(path.stat().st_size for path in tmp_path.rglob('*') if path.is_file())
        result['retained_output_bytes_before_receipt'] = total
        if 'functional_completed_source_api_qualified' not in result:
            result['functional_completed_source_api_qualified'] = (
                len(result['backends']) == 2 and all(item.get('functional_completed_source_api_qualified') is True
                                                   for item in result['backends'].values()))
        _write_json(tmp_path / 'paired-video-result.json', result)
        assert result['boot_input_unchanged'] and result['private_baseline_unchanged']
        assert total < OUTPUT_LIMIT
