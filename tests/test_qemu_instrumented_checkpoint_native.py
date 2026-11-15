"""Native DOS checkpoint with virtual clock, PC speaker and VGA observers.

The test requires the caller's patched QEMU, pinned firmware, qemu-img and
private FreeDOS image. The COM program is authored; no game bytes are used.
"""
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from PIL import Image
import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_audio_fixture import speaker_tone
from test_qemu_clock_budget_native import budget_receipt, park
from test_qemu_dos_checkpoint_sessions_native import _fixture, _inputs, _number, _word


def _open_instrumented(project, runtime, directory, disk):
    return project.debugger(
        runtime['FDISBULL_QEMU_LAYERS'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000,
        qemu_clock='virtual', qemu_audio='pc-speaker', qemu_retrace='precise')


def _open_virtual_only(project, runtime, directory, disk):
    return project.debugger(
        runtime['FDISBULL_QEMU_LAYERS'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000,
        qemu_clock='virtual')


def _artifact_bytes(project, identifier):
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    assert row is not None
    return bytes(row['data'])


def _pcm(project, receipt):
    with wave.open(io.BytesIO(_artifact_bytes(project, receipt['artifact'])), 'rb') as source:
        assert source.getparams()[:3] == (1, 1, 32000)
        return source.readframes(source.getnframes())


def _pixels(project, receipt):
    with Image.open(io.BytesIO(_artifact_bytes(project, receipt['artifact']))) as source:
        image = source.convert('RGB')
        return image.size, image.tobytes()


def _child_restore(control_path):
    """Independently reopen and continue one instrumented checkpoint."""
    control = json.loads(Path(control_path).read_text())
    runtime = _inputs()
    disk = {'image': Path(control['disk']), 'prepared_sha256': control['disk_sha256']}
    with Project(control['db']) as project:
        with _open_instrumented(project, runtime, Path(control['directory']), disk) as debug:
            fresh_vm = debug.vm.process
            assert debug.run_id != control['origin_run']
            restored = debug.load_state(control['artifact'])
            assert fresh_vm.poll() is not None and debug.vm.process is not fresh_vm
            process = debug.dos_process_info()
            assert process['capture_epoch'] != control['origin_epoch']
            clock = debug.clock_observe()
            audio, display = debug.audio_observe(), debug.display_observe()
            retrace = debug.retrace_observe()
            assert clock['virtual_ns'] == control['virtual_ns']
            assert clock['virtual_clock']['native']['epoch'] != control['native_epoch']
            windows = restored['instrumentation']['windows']
            assert windows['audio'] == {'old': control['audio_window'], 'new': audio['window']}
            assert windows['display'] == {'old': control['display_window'], 'new': display['window']}
            assert audio['window'] != control['audio_window'] and display['window'] != control['display_window']
            assert audio['frames'] == control['frames'] and display['updates'] == control['updates']
            assert retrace['raw'] == control['retrace_raw'] and retrace['phase'] == control['retrace_phase']
            pcm = _pcm(project, debug.capture_audio('child-restored.wav'))
            size, pixels = _pixels(project, debug.capture_display('child-restored.png'))
            assert hashlib.sha256(pcm).hexdigest() == control['pcm_sha256']
            assert list(size) == control['image_size'] and hashlib.sha256(pixels).hexdigest() == control['pixels_sha256']
            layer_ids = restored['controls']['layers']
            fetch, ram = layer_ids[control['fetch']], layer_ids[control['ram']]
            assert fetch == control['fetch'] and ram != control['ram']
            assert debug.layers()['active'] == [fetch, ram]
            hooks = debug.hooks()['hooks']
            assert len(hooks) == 1 and hooks[0]['hook'] == control['hook'] and hooks[0]['hits'] == 1
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 2
            debug.delete_hook(control['hook'])
            before = debug.clock_observe()
            budget_receipt(debug.clock_advance(50_000_000, timeout_ms=10000),
                           50_000_000, before=before)
            assert debug.audio_observe()['frames'] > audio['frames']
            assert debug.display_observe()['updates'] > display['updates']
            debug.audio_stop()
            debug.display_stop()
            debug.layers([])
    assert digest(disk['image']) == disk['prepared_sha256']
    print(json.dumps({'passed': True, 'pid': os.getpid(), 'hook_hit': 2}))


def test_native_cross_session_virtual_clock_audio_display_retrace_and_controls(tmp_path):
    runtime = _inputs()
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM is required for the instrumented checkpoint witness')
        pytest.skip('Supply NASM for the instrumented checkpoint witness')
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'instrumented-baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    original, offsets = speaker_tone(tmp_path, nasm)
    # One separate, otherwise unused source word carries the RAM layer.
    code = original + b'\0\0'
    source = tmp_path / 'SPEAKER.COM'
    source.write_bytes(code)
    db = tmp_path / 'instrumented.fdb'

    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        fetch = project.debug_layer('instrumented-fetch', kind='execute', patches=[{
            'address': hex(static), 'expected_hex': '90', 'data_hex': 'f8',
        }])['layer']
        with _open_instrumented(project, runtime, tmp_path, disk) as debug:
            process = debug.dos_process_info()
            base = _number(process['source_mapping']['runtime_base'])
            ram = debug.layer_patch('instrumented-ram', base + len(original),
                                    expected_hex='0000', data_hex='3412', kind='ram',
                                    space='physical', activate=False)['layer']
            debug.layers([fetch, ram])
            park(debug, base + offsets['tone_ready_ip'] - 0x100)
            audio_started = debug.audio_start(max_frames=32000)
            display_started = debug.display_start(period_ns=20_000_000)
            before = debug.clock_observe()
            budget_receipt(debug.clock_advance(150_000_000, timeout_ms=10000),
                           150_000_000, before=before)
            # The loop comparison immediately follows tone_ready's NOP. Its
            # source-bound hook remains active while the checkpoint is saved.
            hook_address = static + offsets['tone_ready_ip'] + 1 - 0x100
            hook = debug.hook(hex(hook_address), space='source', once=False, max_hits=3,
                              actions=[{'op': 'layers', 'layers': [fetch, ram]}])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 1
            audio = debug.audio_observe()
            display = debug.display_observe()
            clock = debug.clock_observe()
            retrace = debug.retrace_observe()
            config = debug.vga_configuration_observe()
            assert audio['state'] == 'capturing' and audio['frames'] > 0 and audio['dropped_frames'] == 0
            assert display['state'] == 'observing' and display['updates'] > 0
            assert audio['window'] == audio_started['window'] and display['window'] == display_started['window']
            assert audio['observed_ns'] == display['observed_ns'] == clock['virtual_ns'] == retrace['observed_ns']
            assert _word(debug, base + len(original)) == 0x1234
            pcm = _pcm(project, debug.capture_audio('before.wav'))
            pixels = _pixels(project, debug.capture_display('before.png'))
            assert len(pcm) == audio['frames'] and len(pcm) > 0
            saved_pc = debug.registers()['linear_pc']
            old_epoch, old_run = process['capture_epoch'], debug.run_id
            saved = debug.save_state()
            original_vm = debug.vm.process
        assert original_vm.poll() is not None

    # A separate Python host, not merely another session object, must be able
    # to rebind the retained native observer contents and resume the guest.
    child_control = dict(db=str(db), directory=str(tmp_path), disk=str(disk['image']),
        disk_sha256=disk['prepared_sha256'], artifact=saved['artifact'], origin_run=old_run,
        origin_epoch=old_epoch, virtual_ns=clock['virtual_ns'],
        native_epoch=clock['virtual_clock']['native']['epoch'], audio_window=audio['window'],
        display_window=display['window'], frames=audio['frames'], updates=display['updates'],
        retrace_raw=retrace['raw'], retrace_phase=retrace['phase'],
        pcm_sha256=hashlib.sha256(pcm).hexdigest(), image_size=list(pixels[0]),
        pixels_sha256=hashlib.sha256(pixels[1]).hexdigest(), fetch=fetch, ram=ram, hook=hook['hook'])
    control_path = tmp_path / 'instrumented-child-control.json'
    control_path.write_text(json.dumps(child_control))
    environment = os.environ.copy()
    source_dir = str(Path(__file__).resolve().parents[1] / 'src')
    environment['PYTHONPATH'] = source_dir + os.pathsep + environment.get('PYTHONPATH', '')
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                           cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                           capture_output=True, text=True, timeout=240)
    assert child.returncode == 0, child.stderr[-3000:]
    child_result = json.loads(child.stdout)
    assert child_result['passed'] is True and child_result['pid'] != os.getpid()
    assert child_result['hook_hit'] == 2

    with Project(db) as project:
        with _open_instrumented(project, runtime, tmp_path, disk) as debug:
            fresh_vm = debug.vm.process
            fresh_epoch = debug.dos_process_info()['capture_epoch']
            assert debug.run_id != old_run
            restored = debug.load_state(saved['artifact'])
            assert fresh_vm.poll() is not None and debug.vm.process is not fresh_vm
            process = debug.dos_process_info()
            assert restored['source_binding_restored'] is True
            assert process['capture_epoch'] not in (old_epoch, fresh_epoch)
            assert debug.registers()['linear_pc'] == saved_pc
            base = _number(process['source_mapping']['runtime_base'])
            layer_ids = restored['controls']['layers']
            fetch_after, ram_after = layer_ids[fetch], layer_ids[ram]
            assert fetch_after == fetch and ram_after != ram
            assert debug.layers()['active'] == [fetch_after, ram_after]
            assert _word(debug, base + len(original)) == 0x1234
            assert debug.code(hex(static), length=1, view='ram', space='source')['hex'] == '90'
            assert debug.code(hex(static), length=1, view='execute', space='source')['hex'] == 'f8'
            hooks = debug.hooks()['hooks']
            assert len(hooks) == 1 and hooks[0]['hook'] == hook['hook'] and hooks[0]['hits'] == 1
            assert hooks[0]['actions'] == [{'op': 'layers', 'layers': [fetch_after, ram_after]}]

            clock2 = debug.clock_observe()
            audio2 = debug.audio_observe()
            display2 = debug.display_observe()
            retrace2 = debug.retrace_observe()
            config2 = debug.vga_configuration_observe()
            assert clock2['virtual_ns'] == clock['virtual_ns']
            assert clock2['virtual_clock']['native']['epoch'] != clock['virtual_clock']['native']['epoch']
            assert audio2['observed_ns'] == display2['observed_ns'] == retrace2['observed_ns'] == clock2['virtual_ns']
            assert audio2['state'] == 'capturing' and audio2['frames'] == audio['frames']
            assert audio2['dropped_frames'] == audio['dropped_frames']
            assert display2['state'] == 'observing' and display2['updates'] == display['updates']
            windows = restored['instrumentation']['windows']
            assert windows['audio'] == {'old': audio['window'], 'new': audio2['window']}
            assert windows['display'] == {'old': display['window'], 'new': display2['window']}
            assert audio2['window'] != audio['window'] and display2['window'] != display['window']
            assert audio2['epoch'] == display2['epoch'] == clock2['epoch']
            assert retrace2['raw'] == retrace['raw'] and retrace2['timing'] == retrace['timing']
            assert retrace2['phase'] == retrace['phase']
            assert config2['current']['raw'] == config['current']['raw']
            assert _pcm(project, debug.capture_audio('after.wav')) == pcm
            assert _pixels(project, debug.capture_display('after.png')) == pixels

            second = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert second['outcome'] == 'hook' and second['hook_hits'][0]['hit'] == 2
            assert second['hook_hits'][0]['hook'] == hook['hook']
            debug.delete_hook(hook['hook'])
            before2 = debug.clock_observe()
            budget_receipt(debug.clock_advance(100_000_000, timeout_ms=10000),
                           100_000_000, before=before2)
            later_audio = debug.audio_observe()
            later_display = debug.display_observe()
            assert later_audio['frames'] > audio2['frames'] and later_audio['dropped_frames'] == 0
            assert later_display['updates'] > display2['updates']
            assert _pcm(project, debug.capture_audio('continued.wav')).startswith(pcm)
            debug.audio_stop()
            debug.display_stop()
            debug.layers([])
    assert source.read_bytes() == code and digest(boot) == boot_hash
    assert digest(disk['image']) == disk['prepared_sha256']


@pytest.mark.parametrize('case', ['com', 'mz'])
def test_native_virtual_only_midprogram_checkpoint_continues_original_dos(tmp_path, case):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'virtual-baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, witness = _fixture(case)
    source = tmp_path / witness['filename']
    source.write_bytes(code)
    db = tmp_path / 'virtual.fdb'
    options = {'image': witness['image']} if witness['image'] else {}
    with Project.create(db, source, **options) as project:
        with _open_virtual_only(project, runtime, tmp_path, disk) as debug:
            process = debug.dos_process_info()
            base = _number(process['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + witness['hook_offset'])
            before = debug.clock_observe()
            stopped = debug.clock_advance(50_000_000, timeout_ms=10000)
            budget_receipt(stopped, 50_000_000, before=before, reached=False)
            assert stopped['outcome'] == 'breakpoint', stopped
            assert point['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids']
            debug.delete_breakpoint(point['breakpoint_id'])
            expected_start = 0x1111 if case == 'com' else 0xbeef
            assert _word(debug, base + witness['data_offset']) == expected_start
            clock = debug.clock_observe()
            epoch, saved_pc = process['capture_epoch'], debug.registers()['linear_pc']
            saved = debug.save_state()
            old_vm = debug.vm.process
        assert old_vm.poll() is not None
    with Project(db) as project:
        with _open_virtual_only(project, runtime, tmp_path, disk) as debug:
            fresh_vm = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert fresh_vm.poll() is not None and debug.vm.process is not fresh_vm
            process = debug.dos_process_info()
            assert process['capture_epoch'] != epoch and restored['source_binding_restored']
            assert debug.registers()['linear_pc'] == saved_pc
            clock2 = debug.clock_observe()
            assert clock2['virtual_ns'] == clock['virtual_ns']
            assert clock2['virtual_clock']['native']['epoch'] != clock['virtual_clock']['native']['epoch']
            assert restored['instrumentation']['windows'] == {}
            base = _number(process['source_mapping']['runtime_base'])
            assert _word(debug, base + witness['data_offset']) == expected_start
            exit_offset = 15 if case == 'com' else 0x35
            point = debug.breakpoint(base + exit_offset)
            result = debug.run(timeout_ms=15000)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            expected_end = 0x1113 if case == 'com' else 0xbef1
            assert _word(debug, base + witness['data_offset']) == expected_end
            done = debug.run(timeout_ms=5000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42
    assert source.read_bytes() == code and digest(boot) == boot_hash
    assert digest(disk['image']) == disk['prepared_sha256']


def test_native_instrumented_checkpoint_refuses_active_host_sync_without_mutation(tmp_path):
    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'sync-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
                                config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    source = tmp_path / 'SYNC.COM'
    source.write_bytes(bytes.fromhex('ebfe'))
    with Project.create(tmp_path / 'sync.fdb', source, image='com') as project:
        with _open_virtual_only(project, runtime, tmp_path, disk) as debug:
            current_vm = debug.vm.process
            current_pc = debug.registers()['linear_pc']
            sync = debug.clock_sync_start()
            assert sync['outcome'] == 'started'
            with pytest.raises(ValueError, match='(?i)clock synchronization'):
                debug.save_state()
            assert debug.vm.process is current_vm and current_vm.poll() is None
            assert debug.status()['state'] == 'stopped' and debug.registers()['linear_pc'] == current_pc
            stopped = debug.clock_sync_stop()
            assert stopped['outcome'] == 'stopped'
            saved = debug.save_state()
            assert saved['metadata']['format'] == 'fdisbull-qemu-dos-process-qcow2-v2'


if __name__ == '__main__':
    _child_restore(sys.argv[1])
