"""Real SB16 DSP/DMA/IRQ and in-flight native checkpoint continuation.

Supply FDISBULL_QEMU_SB16, FDISBULL_QEMU_DOS_BOOT_IMAGE,
FDISBULL_QEMU_DOS_MCOPY, FDISBULL_QEMU_DOS_FIRMWARE, FDISBULL_QEMU_IMG and
NASM. FDISBULL_REQUIRE_QEMU_SB16=1 refuses missing inputs. Root alone runs
native guests. Source/boot/runtime identities and generated artifacts stay in
the caller's private external output directory. No host guest-RAM/CPU writes.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_sb16_fixture import DMA_BYTES, OUTPUT_RATE, linear_pcm, sb16_pcm, source_pcm
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_process_native import assert_completion, com_address, read_bytes


def _runtime():
    selected = {key: os.environ.get(key) for key in ('FDISBULL_QEMU_SB16',
        'FDISBULL_QEMU_DOS_BOOT_IMAGE', 'FDISBULL_QEMU_DOS_MCOPY',
        'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')}
    selected['NASM'] = os.environ.get('NASM') or shutil.which('nasm')
    missing = [key for key, value in selected.items() if not value]
    if missing:
        message = 'Native SB16 inputs missing: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_QEMU_SB16') == '1':
            pytest.fail(message)
        pytest.skip(message)
    for key, value in selected.items():
        path = Path(value).expanduser()
        assert path.is_dir() if key == 'FDISBULL_QEMU_DOS_FIRMWARE' else path.is_file(), key
    return selected


def _launch(project, runtime, directory, disk):
    return project.debugger(runtime['FDISBULL_QEMU_SB16'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'], qemu_transport='pipe',
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], qemu_clock='virtual',
        qemu_audio='sb16', boot_timeout_ms=30000)


def _symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    excluded = ('report_size', 'dma_bytes', 'rate', 'silence')
    return {key: com_address(info, value) for key, value in offsets.items() if key not in excluded}


def _word(debug, symbols, name):
    return int.from_bytes(read_bytes(debug, symbols[name], 2), 'little')


def _device(debug):
    state = debug.vm.qmp.call('x-fdisbull-query-sb16')
    assert state['api-version'] == 1
    assert (state['iobase'], state['irq'], state['dma'], state['dma16'], state['version']) == (
        0x220, 7, 1, 5, 0x0405)
    assert state['audiodev-id'] == 'fdisbull-sb16'
    assert type(state['voice-present']) is type(state['dma-active']) is bool
    return state


def _pcm(project, debug, name):
    artifact = debug.capture_audio(name)
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact['artifact'],)).fetchone()
    with wave.open(io.BytesIO(bytes(row['data'])), 'rb') as stream:
        assert stream.getparams()[:3] == (1, 1, OUTPUT_RATE)
        samples = stream.readframes(stream.getnframes())
    assert len(samples) == artifact['metadata']['frames']
    info = debug.audio_observe()
    assert info['dropped_frames'] == 0 and info['state'] != 'overflow'
    return samples, artifact, deepcopy(info['native']['chunks'])


def _known_wave(samples, rate):
    expected = linear_pcm(rate)
    # Fixed rate, unity gain and zero source offset. Only a bounded leading
    # mixer-silence frontier is allowed; it cannot hide skipped source PCM.
    candidates = []
    for start in range(min(1024, len(samples)) + 1):
        if any(abs(value - 128) > 1 for value in samples[:start]):
            break
        if len(samples) >= start + 128 and all(abs(a - b) <= 1 for a, b in
                zip(samples[start:start + 128], expected[:128])):
            candidates.append(start)
    assert len(candidates) == 1, 'Known source onset was missing or ambiguous'
    start = candidates[0]
    assert len(samples) >= start + len(expected), 'Complete authored PCM sequence was not rendered'
    actual = samples[start:start + len(expected)]
    assert all(abs(a - b) <= 1 for a, b in zip(actual, expected)), 'Known DSP/DMA waveform differs'
    tail = samples[start + len(expected):]
    assert len(tail) <= 2048 and all(abs(value - 128) <= 1 for value in tail), 'Unexpected output after the source tail'
    return dict(source_rate=rate, output_rate=OUTPUT_RATE, source_frames=DMA_BYTES,
        expected_frames=len(expected), leading_silence_frames=start, trailing_silence_frames=len(tail),
        source_sha256=hashlib.sha256(source_pcm()).hexdigest(), quantization_tolerance=1,
        no_fitted_gain_rate_or_source_offset=True)


def _sample(project, debug, symbols, offsets, label):
    report = read_bytes(debug, symbols['report'], offsets['report_size'])
    physical = int.from_bytes(read_bytes(debug, symbols['buffer_physical'], 4), 'little')
    buffer = read_bytes(debug, physical, DMA_BYTES)
    assert buffer == source_pcm()
    assert physical % DMA_BYTES == 0 and physical & 0xffff <= 0xe000
    pcm, artifact, chunks = _pcm(project, debug, label + '.wav')
    return dict(cpu=debug.registers(), device=_device(debug), report_hex=report.hex(),
        buffer_sha256=hashlib.sha256(buffer).hexdigest(), buffer_physical=physical,
        pcm_hex=pcm.hex(), pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        audio_artifact=artifact, chunks=chunks, clock=debug.clock_observe())


def _continue(project, debug, symbols, offsets, control, label):
    if offsets['silence']:
        first, second = control['deltas']
        budget_receipt(debug.clock_advance(first, timeout_ms=10000), first)
        assert _word(debug, symbols, 'irq_count') == 0
        assert _device(debug)['aux-timer-pending'] is True
        budget_receipt(debug.clock_advance(second, timeout_ms=10000), second)
    else:
        delta = control['deltas'][0]
        budget_receipt(debug.clock_advance(delta, timeout_ms=15000), delta)
    park(debug, symbols['finished'])
    assert _word(debug, symbols, 'irq_count') == 1 and _word(debug, symbols, 'stage') == 2
    state = _sample(project, debug, symbols, offsets, label)
    assert state['device']['dma-active'] is False
    assert state['device']['aux-timer-pending'] is False
    samples = bytes.fromhex(state['pcm_hex'])
    state['oracle'] = {'silence_command_is_irq_delay_not_pcm': True} if offsets['silence'] else _known_wave(samples, offsets['rate'])
    if offsets['silence']:
        assert samples == b''
    return state


def _assert_future(actual, expected):
    for key in ('device', 'buffer_sha256', 'report_hex', 'pcm_sha256', 'chunks', 'oracle'):
        assert actual[key] == expected[key], key
    # The observer token/epoch is newly owned; timestamped callback contents
    # and PCM are compared as retained output, not token reuse.
    assert actual['audio_artifact']['metadata']['window'] != expected['audio_artifact']['metadata']['window']


def _load(project, debug, offsets, control, label):
    old, epoch = debug.vm.process, debug.dos_process_info()['capture_epoch']
    restored = debug.load_state(control['saved']['artifact'])
    assert old.poll() is not None and debug.vm.process is not old and debug.vm.process.poll() is None
    info = debug.dos_process_info()
    assert restored['source_binding_restored'] is True and info['state'] == 'active'
    assert info['capture_epoch'] not in (epoch, control['origin_epoch'])
    symbols = _symbols(debug, offsets)
    state = _sample(project, debug, symbols, offsets, label + '-restored')
    captured = control['captured']
    for key in ('cpu', 'device', 'report_hex', 'buffer_sha256', 'pcm_sha256', 'chunks'):
        assert state[key] == captured[key], key
    assert state['audio_artifact']['metadata']['window'] != captured['audio_artifact']['metadata']['window']
    assert state['clock']['virtual_ns'] == captured['clock']['virtual_ns']
    return symbols, restored, state


def _child_restore(path):
    control = json.loads(Path(path).read_text())
    runtime, directory = _runtime(), Path(control['directory'])
    disk = {'image': Path(control['disk'])}
    assert digest(disk['image']) == control['disk_sha256']
    assert digest(directory / 'SB16.COM') == control['source_sha256']
    result = dict(passed=False, pid=os.getpid())
    try:
        with Project(control['db']) as project:
            assert project.debug_state_info(control['saved']['artifact'])['sha256'] == control['saved']['sha256']
            exported = directory / 'child-checkpoint.state'
            project.debug_export(control['saved']['artifact'], exported)
            assert digest(exported) == control['saved']['sha256']
            with _launch(project, runtime, directory, disk) as debug:
                assert debug.run_id != control['origin_run']
                symbols, restored, initial = _load(project, debug, control['offsets'], control, 'child')
                future = _continue(project, debug, symbols, control['offsets'], control, 'child-future')
                _assert_future(future, control['future'])
                result.update(restored=restored, initial=initial, future=future)
                down = debug.keyboard_key_down('q')['lease']
                debug.keyboard_key_up(down)
                assert_completion(debug, debug.run(timeout_ms=5000), exit_code=42)
                owner = debug.vm.process
            assert owner.poll() is not None
        result['passed'] = True
    finally:
        result['disk_unchanged'] = digest(disk['image']) == control['disk_sha256']
        (directory / 'child-result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'pid': os.getpid()}))


@pytest.mark.parametrize(('rate', 'silence'), [(8000, False), (32000, False), (8000, True)],
                         ids=['dma-8000', 'dma-32000', 'aux-silence-timer'])
def test_native_sb16_known_pcm_and_inflight_checkpoint_hot_separate_process_cold(tmp_path, rate, silence):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'sb16-boot.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
                                config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = sb16_pcm(tmp_path, runtime['NASM'], rate=rate, silence=silence)
    source = tmp_path / 'SB16.COM'
    source.write_bytes(code)
    db = tmp_path / 'sb16.fdb'
    control = dict(directory=str(tmp_path), db=str(db), disk=str(disk['image']),
        disk_sha256=disk['prepared_sha256'], source_sha256=digest(source), offsets=offsets)
    report = dict(format='fdisbull-authored-sb16-native-1', success=False, rate=rate, silence=silence)
    try:
        with Project.create(db, source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['ready'])
                assert read_bytes(debug, symbols['reset_byte'], 3) == b'\xaa\x04\x05'
                debug.audio_start(max_frames=80000)
                park(debug, symbols['started'])
                before = debug.clock_observe()
                if silence:
                    # DSP80h receives 800 samples at an explicitly programmed
                    # 8000 Hz: a 100-ms IRQ delay. The source stop follows the
                    # command by a few instructions; do not derive the oracle
                    # duration from the native timer field under test.
                    delay = _device(debug)['aux-timer-deadline'] - before['virtual_ns']
                    assert 99_000_000 < delay <= 100_000_000
                delta = 25_000_000 if silence else 30_000_000
                budget_receipt(debug.clock_advance(delta, timeout_ms=10000), delta, before=before)
                park(debug, symbols['inflight'])
                assert _word(debug, symbols, 'irq_count') == 0
                device = _device(debug)
                if silence:
                    assert device['dma-active'] is False and device['aux-timer-pending'] is True
                    remaining = device['aux-timer-deadline'] - debug.clock_observe()['virtual_ns']
                    assert 60_000_000 < remaining < 100_000_000
                    control['deltas'] = [60_000_000, 30_000_000]
                else:
                    assert device['dma-active'] is True and 0 < device['left-till-irq'] < DMA_BYTES
                    assert device['dma-length'] == DMA_BYTES and 0 < device['dma-position'] < DMA_BYTES
                    assert 0 < _word(debug, symbols, 'dma_count') < DMA_BYTES - 1
                    control['deltas'] = [1_200_000_000]
                # A pending first mixer callback is legitimate: zero captured
                # frames here does not negate independent DMA progress.
                captured = _sample(project, debug, symbols, offsets, 'captured')
                saved = debug.save_state('sb16-inflight.state')
                control.update(saved=saved, captured=captured, origin_run=debug.run_id,
                               origin_epoch=debug.dos_process_info()['capture_epoch'])
                future = _continue(project, debug, symbols, offsets, control, 'original-future')
                control['future'] = future
                symbols, restored, initial = _load(project, debug, offsets, control, 'hot')
                hot = _continue(project, debug, symbols, offsets, control, 'hot-future')
                _assert_future(hot, future)
                report.update(captured=captured, saved=saved, original_future=future,
                              hot_restore=restored, hot_initial=initial, hot_future=hot)
                owner = debug.vm.process
            assert owner.poll() is not None

        control_path = tmp_path / 'child-control.json'
        control_path.write_text(json.dumps(control, indent=2, sort_keys=True) + '\n')
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child-restore', str(control_path)],
            check=False, capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        (tmp_path / 'child.log').write_text(child.stdout + child.stderr)
        assert child.returncode == 0, child.stdout + child.stderr
        child_result = json.loads((tmp_path / 'child-result.json').read_text())
        assert child_result['passed'] and child_result['disk_unchanged'] and child_result['pid'] != os.getpid()
        report.update(child=child_result, success=True)
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash and digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-sb16.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--child-restore':
        raise SystemExit('Use pytest, or the explicit child-restore route')
    _child_restore(sys.argv[2])
