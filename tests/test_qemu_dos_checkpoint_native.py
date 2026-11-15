"""Real DOS EXEC entry checkpoint and cold rebind witnesses.

All input executables are authored test fixtures. These tests require the
caller's private DOS boot image and explicit QEMU, firmware, mcopy and qemu-img.
"""
import hashlib
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import com_exit, mz_exit, prepare_dos_baseline, resident_com


def _inputs():
    keys = ('FDISBULL_QEMU_DOS', 'FDISBULL_QEMU_DOS_BOOT_IMAGE', 'FDISBULL_QEMU_DOS_MCOPY',
            'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')
    result = {key: os.environ.get(key) for key in keys}
    missing = [key for key, value in result.items() if not value]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Missing process checkpoint inputs: ' + ', '.join(missing))
        pytest.skip('Supply process checkpoint inputs: ' + ', '.join(missing))
    return result


@pytest.mark.parametrize('case', ['com', 'mz', 'tsr'])
def test_native_process_entry_checkpoint_rebind_and_exit(tmp_path, case):
    runtime = _inputs()
    boot_source = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = hashlib.sha256(boot_source.read_bytes()).hexdigest()
    disk = prepare_dos_baseline(boot_source, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    if case == 'mz':
        source, _ = mz_exit(); filename = 'TARGET.EXE'; expected = 'guest_exit'; code = 42
    elif case == 'tsr':
        source, _ = resident_com(); filename = 'TARGET.COM'; expected = 'guest_tsr'; code = 37
    else:
        source = com_exit(37); filename = 'TARGET.COM'; expected = 'guest_exit'; code = 37
    binary = tmp_path / filename
    binary.write_bytes(source)
    options = {} if case == 'mz' else {'image': 'com'}
    with Project.create(tmp_path / 'program.fdb', binary, **options) as project:
        with project.debugger(runtime['FDISBULL_QEMU_DOS'], tmp_path, backend='qemu-dos',
                dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
                dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
                qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
                qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000) as debug:
            assert debug.capabilities['save_states'] is True
            before = debug.dos_process_info()
            assert before['state'] == 'active'
            saved = debug.save_state()
            assert saved['metadata']['format'] in (
                'fdisbull-qemu-dos-entry-qcow2-v1', 'fdisbull-qemu-dos-process-qcow2-v2')
            assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
            original = debug.run(timeout_ms=5000)
            assert original['outcome'] == expected
            old_process = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert old_process.poll() is not None
            assert restored['source_binding_restored'] is True
            assert restored['capture_epoch'] != before['capture_epoch']
            assert debug.dos_process_info()['state'] == 'active'
            assert debug.status()['state'] == 'stopped'
            again = debug.run(timeout_ms=5000)
            assert again['outcome'] == expected
            assert again['process']['termination']['code'] == code
    assert binary.read_bytes() == source
    assert hashlib.sha256(boot_source.read_bytes()).hexdigest() == boot_hash


def test_native_process_checkpoint_refuses_after_entry_execution(tmp_path):
    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'], tmp_path / 'baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'])
    binary = tmp_path / 'TARGET.COM'; binary.write_bytes(com_exit())
    with Project.create(tmp_path / 'program.fdb', binary, image='com') as project:
        with project.debugger(runtime['FDISBULL_QEMU_DOS'], tmp_path, backend='qemu-dos',
                dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
                dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
                qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
                qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000) as debug:
            debug.step(timeout_ms=5000)
            if 'x-fdisbull-dos-checkpoint-status' in debug.vm.qmp_commands:
                saved = debug.save_state()
                assert saved['metadata']['format'] == 'fdisbull-qemu-dos-process-qcow2-v2'
                pc = debug.registers()['linear_pc']
                debug.load_state(saved['artifact'])
                assert debug.registers()['linear_pc'] == pc
            else:
                with pytest.raises(ValueError, match='original verified entry'):
                    debug.save_state()
            assert debug.status()['state'] == 'stopped'
