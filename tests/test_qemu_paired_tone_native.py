"""Same authored OPL / stereo SB guest and complete raw audio on both engines.

Set FDISBULL_QEMU_MIXER, FDISBULL_DOSBOX_GAME_PARITY (or FDISBULL_DOSBOX),
FDISBULL_QEMU_DOS_BOOT_IMAGE, FDISBULL_QEMU_DOS_MCOPY,
FDISBULL_QEMU_DOS_FIRMWARE, FDISBULL_QEMU_IMG and NASM.
FDISBULL_REQUIRE_QEMU_MIXER=1 or FDISBULL_REQUIRE_QEMU_PAIRED_TONE=1 makes
missing prerequisites fail. Only the native owner runs these opt-in tests.
The legacy comparison keeps the default U8 mono QEMU capture. The separate
S16 stereo case requires audio_stereo_capture and never substitutes mono.
No cross-engine waveform/gain/CPU/timing identity or hardware fidelity claim.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import struct
import time
import wave

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_paired_tone_fixture import (
    DSP_REQUEST_SAMPLES, REQUESTED_STEREO_FRAMES, SOURCE_BYTES, SOURCE_FRAMES,
    SOURCE_RATE, expected_frequencies,
    paired_tone, parse_report, source_stereo,
)
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import assert_completion, com_address


def _required():
    return any(os.environ.get(key) == '1' for key in
        ('FDISBULL_REQUIRE_QEMU_MIXER', 'FDISBULL_REQUIRE_QEMU_PAIRED_TONE'))


@pytest.fixture
def paired_tone_runtime(tmp_path):
    configured = dict(qemu=os.environ.get('FDISBULL_QEMU_MIXER'),
        dosbox=os.environ.get('FDISBULL_DOSBOX_GAME_PARITY') or os.environ.get('FDISBULL_DOSBOX'),
        boot=os.environ.get('FDISBULL_QEMU_DOS_BOOT_IMAGE'),
        mcopy=os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy'),
        firmware=os.environ.get('FDISBULL_QEMU_DOS_FIRMWARE'),
        qemu_img=os.environ.get('FDISBULL_QEMU_IMG'), nasm=os.environ.get('NASM') or shutil.which('nasm'))
    missing = [key for key, value in configured.items() if not value]
    if missing:
        message = 'Paired native tone inputs missing: ' + ', '.join(missing)
        if _required():
            pytest.fail(message)
        pytest.skip(message)
    runtime = {key: Path(value).expanduser().absolute() for key, value in configured.items()}
    for key, path in runtime.items():
        assert path.is_dir() if key == 'firmware' else path.is_file(), (key, path)
        if key not in ('firmware', 'boot'):
            assert os.access(path, os.X_OK), (key, path)
    runtime['boot_sha256'] = digest(runtime['boot'])
    runtime['disk'] = prepare_dos_baseline(runtime['boot'], tmp_path / 'paired-tone-boot.img',
        runtime['mcopy'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    # Exact proven shell alias; no mixer command or configuration override.
    wrapper = tmp_path / 'dosbox-capture-wave'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(runtime['dosbox']))
        + ' "$@" -c "ALIAS CAPW=DX-CAPTURE /A /-D"\n')
    wrapper.chmod(0o700)
    runtime['wrapper'] = wrapper
    return runtime


def _pin(path):
    path = Path(path)
    return dict(path=str(path), size=path.stat().st_size, sha256=digest(path))


def _strength(values, rate, frequency):
    """Fixed-frequency whole-record Fourier projection; no time/gain fit."""
    angle = 2 * math.pi * frequency / rate
    step_cos, step_sin = math.cos(angle), math.sin(angle)
    cosine, sine, real, imaginary = 1.0, 0.0, 0.0, 0.0
    for value in values:
        real += value * cosine
        imaginary += value * sine
        cosine, sine = (cosine * step_cos - sine * step_sin,
                        sine * step_cos + cosine * step_sin)
    return 2 * math.hypot(real, imaginary) / len(values)


def _frequency(values, rate, expected):
    candidates = range(math.floor(expected * .96), math.ceil(expected * 1.04) + 1)
    scores = [(frequency, _strength(values, rate, frequency)) for frequency in candidates]
    frequency, strength = max(scores, key=lambda item: item[1])
    return dict(expected_hz=expected, measured_hz=frequency, strength=strength,
                relative_error=abs(frequency / expected - 1), search_step_hz=1)


def analyze_wav(path, mode, backend, *, capture_format=None):
    """Keep DC-inclusive levels, rails, channels and pitch as separate facts."""
    assert capture_format in (None, 'u8-mono', 's16-stereo')
    with wave.open(str(path), 'rb') as stream:
        channels, width, rate, frames = stream.getparams()[:4]
        raw = stream.readframes(frames)
    assert width in (1, 2) and channels in (1, 2)
    if capture_format == 's16-stereo':
        assert (channels, width) == (2, 2), 'Requested S16 stereo capture geometry was not retained'
        if backend == 'qemu':
            assert rate == 32000
    elif capture_format == 'u8-mono':
        assert (rate, channels, width) == (32000, 1, 1)
    assert len(raw) == frames * width * channels and frames >= rate // 10
    codes = list(raw) if width == 1 else list(struct.unpack('<' + 'h' * (len(raw) // 2), raw))
    centre, scale, lower, upper = (128, 128, 0, 255) if width == 1 else (0, 32768, -32768, 32767)
    facts, signals = [], []
    for channel in range(channels):
        values = codes[channel::channels]
        normalized = [(value - centre) / scale for value in values]
        mean = sum(normalized) / len(normalized)
        centered = [value - mean for value in normalized]
        ac_rms = math.sqrt(sum(value * value for value in centered) / len(centered))
        assert min(values) < max(values) and ac_rms > .0001
        signals.append(centered)
        facts.append(dict(dc_mean=mean,
            rms_including_dc=math.sqrt(sum(value * value for value in normalized) / len(normalized)),
            ac_rms=ac_rms, minimum_code=min(values), maximum_code=max(values),
            lower_rail_samples=values.count(lower), upper_rail_samples=values.count(upper)))
    frequencies = expected_frequencies()
    if mode == 'O':
        observed = [_frequency(values, rate, frequencies['opl']) for values in signals]
        assert all(item['relative_error'] < .015
                   and item['strength'] > max(.0001, facts[index]['ac_rms'] * .2)
                   for index, item in enumerate(observed))
    else:
        observed = [dict(left=_frequency(values, rate, frequencies['left']),
                         right=_frequency(values, rate, frequencies['right'])) for values in signals]
        if backend == 'qemu' and capture_format != 's16-stereo':
            assert channels == 1
            for name in ('left', 'right'):
                assert observed[0][name]['relative_error'] < .03
                assert observed[0][name]['strength'] > max(.0001, facts[0]['ac_rms'] * .08)
        else:
            assert channels == 2
            assert observed[0]['left']['relative_error'] < .03
            assert observed[1]['right']['relative_error'] < .03
            assert observed[0]['left']['strength'] > 3 * observed[0]['right']['strength']
            assert observed[1]['right']['strength'] > 3 * observed[1]['left']['strength']
            if capture_format == 's16-stereo':
                for index, name in enumerate(('left', 'right')):
                    assert observed[index][name]['strength'] > max(.0001, facts[index]['ac_rms'] * .2)
    return dict(rate=rate, channels=channels, width=width, frames=frames,
        pcm_bytes=len(raw), pcm_encoding='u8' if width == 1 else 's16le',
        channel_order=['mono'] if channels == 1 else ['left', 'right'],
        sample_duration_seconds=frames / rate, guest_elapsed_seconds=None,
        pcm_sha256=hashlib.sha256(raw).hexdigest(), channels_analysis=facts,
        frequencies=observed, whole_record_untrimmed=True,
        frequency_analysis_dc_removed_only=True, gain_or_time_fit=False,
        silent_intervals_synthesized=False, cross_engine_pcm_equal_claim=False)


def _report_checks(report, mode, phase):
    assert report['mode'] == ord(mode) and report['phase'] == phase and report['failure'] == 0
    if mode == 'S':
        assert (report['reset_byte'], report['major'], report['minor']) == (0xaa, 4, 5)
        assert (report['source_rate'], report['source_capacity_frames']) == (SOURCE_RATE, SOURCE_FRAMES)
        assert report['buffer_physical'] % SOURCE_BYTES == 0
        assert report['buffer_physical'] & 0xffff <= 0xe000
        assert report['irq_count'] == (1 if phase == 3 else 0)
    else:
        assert report['irq_count'] == 0 and report['buffer_physical'] == 0
    if phase == 3:
        assert report['old_mask'] == report['restored_mask']
        assert report['done_ticks'] - report['sound_end_ticks'] >= 2
        if mode == 'O':
            assert report['sound_end_ticks'] - report['start_ticks'] >= 6


def _mixer(debug):
    method = getattr(debug, 'mixer_observe', None)
    available = debug.capabilities.get('mixer_gain_readback') is True and callable(method)
    if _required():
        assert available, 'Required passive QEMU mixer readback is unavailable'
    if not available:
        return dict(supported=False, reason='Passive mixer readback unavailable; no fallback writes')
    before_cpu, before_clock = debug.registers(), debug.clock_observe()
    value = method()
    assert isinstance(value, dict)
    after_cpu, after_clock = debug.registers(), debug.clock_observe()
    assert before_cpu == after_cpu
    assert before_clock['virtual_ns'] == after_clock['virtual_ns']
    assert before_clock['counter']['value'] == after_clock['counter']['value']
    return dict(supported=True, value=value, stopped_cpu_clock_unchanged=True)


def _qemu(directory, source, code, offsets, mode, runtime, result, *, capture_format=None):
    with Project.create(directory / 'tone.fdb', source, image='com') as project:
        with project.debugger(runtime['qemu'], directory, backend='qemu-dos',
            dos_boot_image=str(runtime['disk']['image']), dos_mcopy=str(runtime['mcopy']),
            qemu_firmware=str(runtime['firmware']), qemu_transport='pipe',
            qemu_checkpoint_tool=str(runtime['qemu_img']), qemu_clock='virtual',
            qemu_audio='sb16-opl', dos_arguments=mode, boot_timeout_ms=30000) as debug:
            result['owner_pid'] = debug.vm.process.pid
            process = debug.dos_process_info()
            symbols = {name: com_address(process, value) for name, value in offsets.items()
                       if name != 'report_size'}
            def read(address, length):
                return bytes.fromhex(debug.memory(address, length=length, space='physical')['hex'])
            original_vector = read(0x3c, 4)
            result['tone_ready_stop'] = park(debug, symbols['tone_ready'])
            result['ready'] = parse_report(read(symbols['report'], offsets['report_size']))
            _report_checks(result['ready'], mode, 1)
            result['mixer_ready'] = _mixer(debug)
            if mode == 'S':
                assert read(result['ready']['buffer_physical'], SOURCE_BYTES) == source_stereo()
            audio_options = dict(max_frames=100000)
            if capture_format is not None:
                assert capture_format == 's16-stereo'
                assert debug.capabilities.get('audio_stereo_capture') is True
                audio_options['capture_format'] = capture_format
            result['audio_start'] = debug.audio_start(**audio_options)
            if capture_format == 's16-stereo':
                assert result['audio_start']['sample_format'] == dict(
                    rate=32000, channels=2, sample_format='s16', bytes_per_frame=4)
            # Exactly one native continuation spans the actual tone and its tail.
            result['tone_done_stop'] = park(debug, symbols['tone_done'])
            assert result['tone_done_stop']['timed_out'] is False
            result['done'] = parse_report(read(symbols['report'], offsets['report_size']))
            _report_checks(result['done'], mode, 3)
            assert read(0x3c, 4) == original_vector
            result['irq_vector_restored'] = True
            result['mixer_done'] = _mixer(debug)
            result['exit'] = debug.run(timeout_ms=5000)
            assert_completion(debug, result['exit'], exit_code=42)
            result['audio_stop'] = debug.audio_stop()
            artifact = debug.capture_audio('paired-tone.wav')
            project.debug_export(artifact['artifact'], directory / 'audio.wav')
            result['audio_artifact'] = artifact
            result['audio'] = debug.audio_observe()
            assert result['audio']['dropped_frames'] == 0 and result['audio']['state'] == 'stopped'
            if capture_format == 's16-stereo':
                assert result['audio']['sample_format'] == result['audio_start']['sample_format']
            owner = debug.vm.process
        result['native_returncode'], result['reaped'] = owner.returncode, owner.poll() is not None
    assert result['reaped'] and result['native_returncode'] == 0
    assert source.read_bytes() == code


def _dosbox(directory, source, code, offsets, mode, runtime, result):
    rpc = None
    deadline = time.monotonic() + 60
    try:
        rpc = DOSBoxRPC(runtime['wrapper'], directory)
        result['owner_pid'] = rpc.process.pid
        result['capture_route'] = dict(alias='DX-CAPTURE /A /-D', host_audio='dummy/nosound=true')
        result['start'] = rpc.call('session.start', dict(target=dict(command='CAPW', arguments=[source.name, mode]),
            mounts=[dict(drive='C', host_path=str(directory))], break_at='entry'))
        sid = result['start']['session_id']
        def call(method, parameters=None):
            assert time.monotonic() < deadline, 'Finite paired DOSBox phase expired'
            return rpc.call(method, dict(session_id=sid, **(parameters or {})))
        regs = call('state.get_registers')
        cs = int(regs['segments']['cs'], 16)
        assert regs['cpu_mode'] == 'real' and int(regs['instruction_pointer'], 16) == 0x100
        def read(address, length):
            value = call('memory.read', dict(address=dict(space='linear', offset=f'0x{address:08x}'), length=length))
            return base64.b64decode(value['data_base64'], validate=True)
        assert read(cs * 16 + 0x100, 16) == code[:16]
        original_vector = read(0x3c, 4)
        result['timing'] = call('execution.timing', dict(fast_forward=True))
        def run_to(name):
            point = call('breakpoints.create', dict(kind='execution', once=True,
                address=dict(space='segmented', segment=f'0x{cs:04x}', offset=f'0x{offsets[name]:08x}')))
            state = continue_once()
            assert state['state'] == 'stopped' and state['stop_reason']['kind'] == 'breakpoint', state
            assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id']
            return state
        def continue_once():
            op = call('execution.continue')
            while True:
                state = call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=250))
                if not state.get('running', False):
                    return state
        result['tone_ready_stop'] = run_to('tone_ready')
        result['ready'] = parse_report(read(cs * 16 + offsets['report'], offsets['report_size']))
        _report_checks(result['ready'], mode, 1)
        result['mixer_ready'] = dict(supported=False, reason='Native DOSBox RPC has no passive mixer readback; MIXER not invoked')
        if mode == 'S':
            assert read(result['ready']['buffer_physical'], SOURCE_BYTES) == source_stereo()
        result['tone_done_stop'] = run_to('tone_done')
        result['done'] = parse_report(read(cs * 16 + offsets['report'], offsets['report_size']))
        _report_checks(result['done'], mode, 3)
        if mode == 'S':
            initial_address = result['ready']['buffer_physical'] & 0xffff
            assert result['done']['dma_address'] == (initial_address + DSP_REQUEST_SAMPLES) & 0xffff
            assert result['done']['dma_count'] == SOURCE_BYTES - DSP_REQUEST_SAMPLES - 1
            result['documented_dma_progress'] = dict(initial_address=initial_address,
                completed_bytes=DSP_REQUEST_SAMPLES, remaining_bytes=SOURCE_BYTES - DSP_REQUEST_SAMPLES,
                final_address=result['done']['dma_address'], final_count=result['done']['dma_count'])
        assert read(0x3c, 4) == original_vector
        result['irq_vector_restored'] = True
        result['exit'] = continue_once()
        assert result['exit']['state'] == 'exited' and result['exit']['stop_reason']['kind'] == 'guest_exit'
        ended = result['exit']['stop_reason']['guest_exit']
        assert ended['requested_exit_code'] == 42 and ended['resident'] is False
        assert ended['source'] == 'DOS_Terminate' and ended['stage'] == 'after-process-cleanup'
        assert int(ended['psp'], 16) == cs
        capture = Path(rpc.temporary.name) / 'capture'
        prior = None
        while True:
            assert time.monotonic() < deadline, 'Completed native WAV did not finalize'
            files = sorted(capture.glob('*.wav')) if capture.exists() else []
            ready = []
            for path in files:
                data = path.read_bytes()
                if len(data) > 44 and data[:4] == b'RIFF' and data[8:12] == b'WAVE' and struct.unpack_from('<I', data, 4)[0] + 8 == len(data):
                    ready.append(_pin(path))
            if len(files) == len(ready) == 1 and ready == prior:
                break
            prior = ready
            time.sleep(.05)
        shutil.copy2(files[0], directory / 'audio.wav')
        result['native_file_finalized_before_close'] = True
    finally:
        if rpc is not None:
            log = Path(rpc.temporary.name) / 'emulator.log'
            if log.exists():
                shutil.copy2(log, directory / 'emulator.log')
            rpc.close()
            result['native_returncode'], result['reaped'] = rpc.process.returncode, rpc.process.poll() is not None
    assert result['reaped'] and result['native_returncode'] == 0
    assert source.read_bytes() == code


@pytest.mark.parametrize('mode', ['O', 'S'], ids=['opl-only', 'sb16-asymmetric-stereo'])
def test_native_same_authored_tone_program_has_paired_guest_completion_and_independent_audio(tmp_path, paired_tone_runtime, mode):
    _paired_tone_comparison(tmp_path, paired_tone_runtime, mode)


def test_native_explicit_s16_capture_preserves_asymmetric_stereo_on_both_engines(tmp_path, paired_tone_runtime):
    _paired_tone_comparison(tmp_path, paired_tone_runtime, 'S', capture_format='s16-stereo')


def _paired_tone_comparison(tmp_path, runtime, mode, *, capture_format=None):
    code, offsets = paired_tone(tmp_path, runtime['nasm'])
    result = dict(format='fdisbull-paired-authored-tone-native-1', success=False, mode=mode,
        requested_qemu_capture_format=capture_format or 'legacy-default',
        source_sha256=hashlib.sha256(code).hexdigest(), source_bytes=len(code), offsets=offsets,
        expected_frequencies=expected_frequencies(), backends={}, no_guest_memory_or_register_writes=True,
        dma_request=(dict(command='0xc0', mode='0x20', length_word=DSP_REQUEST_SAMPLES - 1,
            unit='eight-bit channel samples', requested_samples=DSP_REQUEST_SAMPLES,
            documented_transfer_bytes=DSP_REQUEST_SAMPLES,
            documented_stereo_frames=REQUESTED_STEREO_FRAMES,
            source_capacity_frames=SOURCE_FRAMES, source_capacity_bytes=SOURCE_BYTES,
            existing_qemu_single_cycle_stereo_compatibility_multiplier=2,
            equal_transfer_extent_or_duration_claim=False) if mode == 'S' else None),
        single_continuous_tone_run_per_backend=True, capture_restart=False,
        no_cross_engine_cpu_timing_pcm_or_gain_equality_claim=True)
    try:
        for backend, run in [('qemu', _qemu), ('dosbox', _dosbox)]:
            directory = tmp_path / backend
            directory.mkdir()
            source = directory / 'PAIR.COM'
            source.write_bytes(code)
            evidence = result['backends'][backend] = dict(source=_pin(source))
            if backend == 'qemu':
                run(directory, source, code, offsets, mode, runtime, evidence,
                    capture_format=capture_format)
            else:
                run(directory, source, code, offsets, mode, runtime, evidence)
            evidence['wav'] = _pin(directory / 'audio.wav')
            evidence['analysis'] = analyze_wav(directory / 'audio.wav', mode, backend,
                capture_format=capture_format)
            actual = evidence['analysis']
            expected = ((32000, 2, 2) if capture_format == 's16-stereo' else (32000, 1, 1))
            assert (actual['rate'], actual['channels'], actual['width']) == (
                expected if backend == 'qemu' else (48000, 2, 2))
            if backend == 'qemu':
                assert actual['frames'] == evidence['audio']['frames']
        if mode == 'S':
            assert result['backends']['qemu']['analysis']['channels'] == (
                2 if capture_format == 's16-stereo' else 1)
            assert result['backends']['dosbox']['analysis']['channels'] == 2
            result['stereo_information_loss_observed'] = capture_format != 's16-stereo'
        result['success'] = True
    except BaseException as error:
        result['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        result['original_boot_unchanged'] = digest(runtime['boot']) == runtime['boot_sha256']
        result['private_boot_input_unchanged'] = digest(runtime['disk']['image']) == runtime['disk']['prepared_sha256']
        (tmp_path / 'paired-tone-result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        assert result['original_boot_unchanged'] and result['private_boot_input_unchanged']
