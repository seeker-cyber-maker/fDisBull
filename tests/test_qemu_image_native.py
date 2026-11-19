"""Explicit two-producer native identity witness; both runtime paths are opt-in."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from fdisbull.project import Project
from fdisbull import qemu_dos_checkpoint, qemu_machine
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_sb16_count_fixture import sb16_count, parse_report
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import com_address

def runtime():
    names = ('FDISBULL_QEMU_IMAGE_BASELINE', 'FDISBULL_QEMU_SB16',
        'FDISBULL_QEMU_IMAGE_EXPECTED_OLD', 'FDISBULL_QEMU_IMAGE_EXPECTED_NEW',
        'FDISBULL_QEMU_DOS_BOOT_IMAGE', 'FDISBULL_QEMU_DOS_MCOPY', 'NASM',
        'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_IMAGE_IDENTITY') == '1':
            pytest.fail('Missing native image witness inputs: ' + ', '.join(missing))
        pytest.skip('Supply both pinned native QEMU producers for image identity qualification')
    return {name: os.environ[name] for name in names}


def test_old_producer_state_refused_before_new_machine_construction(tmp_path):
    ENV = runtime()
    result = dict(format='fdisbull-qemu-image-producer-rejection-2', success=False,
        fixed_checkpoint_tool=ENV['FDISBULL_QEMU_IMG'], fixed_firmware=ENV['FDISBULL_QEMU_DOS_FIRMWARE'])
    owners = []
    try:
        disk = prepare_dos_baseline(ENV['FDISBULL_QEMU_DOS_BOOT_IMAGE'], tmp_path / 'boot.img',
            ENV['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
        code, offsets = sb16_count(tmp_path, ENV['NASM'], bits=8, channels=1, fifo=False)
        source = tmp_path / 'COUNT.COM'
        source.write_bytes(code)
        result['source_sha256'] = digest(source)
        def launch(project, executable):
            return project.debugger(executable, tmp_path, backend='qemu-dos',
                dos_boot_image=str(disk['image']), dos_mcopy=ENV['FDISBULL_QEMU_DOS_MCOPY'],
                qemu_firmware=ENV['FDISBULL_QEMU_DOS_FIRMWARE'], qemu_transport='pipe',
                qemu_checkpoint_tool=ENV['FDISBULL_QEMU_IMG'], qemu_clock='virtual',
                qemu_audio='sb16', boot_timeout_ms=30000)
        with Project.create(tmp_path / 'producer.fdb', source, image='com') as project:
            with launch(project, ENV['FDISBULL_QEMU_IMAGE_BASELINE']) as debug:
                owners.append(debug.vm.process)
                symbols = {k: com_address(debug.dos_process_info(), v) for k,v in offsets.items() if k != 'report_size'}
                park(debug, symbols['ready'])
                debug.audio_start(max_frames=100000)
                park(debug, symbols['started'])
                result['old_compatibility'] = qemu_dos_checkpoint._compatibility(debug)
                result['old_native_inputs'] = deepcopy(debug.vm.inputs)
                result['old_device'] = debug.vm.qmp.call('x-fdisbull-query-sb16')
                assert result['old_device']['dma-active'] is True and result['old_device']['voice-bits'] == 8
                saved = debug.save_state('old-producer-active-u8.state')
                result['saved'] = saved
                assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
                # A changed relaunch route must be checked on the fresh owner,
                # before the saved native state is imported into it.
                original_launch = debug._checkpoint_launch['executable']
                debug._checkpoint_launch['executable'] = ENV['FDISBULL_QEMU_SB16']
                before_cpu, before_clock = debug.registers(), debug.clock_observe()
                before_device = debug.vm.qmp.call('x-fdisbull-query-sb16')
                old_vm = debug.vm
                fresh_owners = []
                original_factory = qemu_machine.QemuMachine
                def fresh_factory(*args, **kwargs):
                    fresh = original_factory(*args, **kwargs)
                    fresh_owners.append(fresh); owners.append(fresh.process)
                    return fresh
                try:
                    with patch.object(qemu_machine, 'QemuMachine', fresh_factory):
                        with pytest.raises(ValueError, match='Fresh process checkpoint machine producer identity differs') as refusal:
                            debug.load_state(saved['artifact'])
                    assert len(fresh_owners) == 1 and fresh_owners[0].process.poll() == 0
                    assert debug.vm is old_vm and old_vm.process.poll() is None and not debug.closed
                    assert debug.registers() == before_cpu
                    after_clock = debug.clock_observe()
                    assert (after_clock['virtual_ns'],after_clock['counter']['value']) == (before_clock['virtual_ns'],before_clock['counter']['value'])
                    assert debug.vm.qmp.call('x-fdisbull-query-sb16') == before_device
                    result['fresh_destination_refusal'] = str(refusal.value)
                    result['fresh_destination_refusal_preserved_old_owner'] = True
                finally:
                    debug._checkpoint_launch['executable'] = original_launch
            assert owners[-1].poll() is not None and owners[-1].returncode == 0
            with launch(project, ENV['FDISBULL_QEMU_SB16']) as debug:
                owner_vm, owner_process = debug.vm, debug.vm.process
                owners.append(owner_process)
                result['new_compatibility'] = qemu_dos_checkpoint._compatibility(debug)
                result['new_native_inputs'] = deepcopy(debug.vm.inputs)
                old_identity, new_identity = deepcopy(result['old_compatibility']), deepcopy(result['new_compatibility'])
                old_qemu = old_identity['inputs'].pop('qemu_image')
                new_qemu = new_identity['inputs'].pop('qemu_image')
                assert old_identity == new_identity, 'The negative control must change only QEMU producer identity'
                assert old_qemu['version'] == new_qemu['version'] and old_qemu['sha256'] != new_qemu['sha256']
                assert old_qemu['sha256'] == ENV['FDISBULL_QEMU_IMAGE_EXPECTED_OLD']
                assert new_qemu['sha256'] == ENV['FDISBULL_QEMU_IMAGE_EXPECTED_NEW']
                result['only_executed_qemu_producer_identity_differs'] = True
                before_cpu, before_clock = debug.registers(), debug.clock_observe()
                before_device = debug.vm.qmp.call('x-fdisbull-query-sb16')
                before_process = debug.dos_process_info()
                constructed = []
                original = qemu_machine.QemuMachine
                def observe_constructor(*args, **kwargs):
                    constructed.append(True)
                    return original(*args, **kwargs)
                with patch.object(qemu_machine, 'QemuMachine', observe_constructor):
                    with pytest.raises(ValueError, match='Process checkpoint sidecar or runtime identity differs') as refused:
                        debug.load_state(saved['artifact'])
                result['refusal'] = str(refused.value)
                result['restore_constructor_calls'] = len(constructed)
                assert not constructed
                assert debug.vm is owner_vm and debug.vm.process is owner_process and owner_process.poll() is None
                assert debug.registers() == before_cpu
                after_clock = debug.clock_observe()
                assert (after_clock['virtual_ns'], after_clock['counter']['value']) == (before_clock['virtual_ns'], before_clock['counter']['value'])
                assert debug.vm.qmp.call('x-fdisbull-query-sb16') == before_device
                assert debug.dos_process_info() == before_process
                result['stopped_owner_cpu_clock_device_process_preserved'] = True
        result['source_unchanged'] = source.read_bytes() == code
        result['boot_unchanged'] = digest(disk['image']) == disk['prepared_sha256']
        assert result['source_unchanged'] and result['boot_unchanged']
        result['success'] = True
    finally:
        result['owners'] = [dict(pid=p.pid,reaped=p.poll() is not None,returncode=p.returncode) for p in owners]
        result['all_owners_reaped'] = all(p.poll() is not None and p.returncode == 0 for p in owners)
        (tmp_path / 'qemu-image-producer-rejection.json').write_text(json.dumps(result,indent=2,sort_keys=True) + '\n')
    assert result['all_owners_reaped']
