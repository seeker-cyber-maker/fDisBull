"""Real DOS VM86 remapping and task-scoped control checkpoint witness.

Requires the explicitly enabled native QEMU layers lane and caller-owned DOS
boot media. The monitor and executable are authored test inputs, not QEMM or
DESQview compatibility claims. No task page banks are copied during a switch.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_dos_task_fixture import ANCHOR, MONITOR_UUID, BANK_A, BANK_B, BANK_PAGES, task_fixture, task_mz
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


def _physical(debug, address, length=2):
    return debug.memory(address, length=length, space='physical')['hex']


def _translated(debug, address):
    result = debug.memory_translation(address, length=2)
    assert result['status'] == 'mapped' and result['page_size'] == 4096
    return int(result['physical_address'], 16)


def _child_restore(path):
    control = json.loads(Path(path).read_text())
    runtime = _inputs()
    with Project(control['database']) as project:
        with _launch(project, runtime, Path(control['directory']), {'image': Path(control['disk'])},
                     **control['profile_options']) as debug:
            result = debug.load_state(control['artifact'])
            assert result['task_identity']['task_id'] == control['task_id']
            observed = debug.dos_task_observe()
            assert observed['matches_binding'] and observed['native_epoch'] > control['native_epoch']
            assert debug.layers()['active'] == [result['controls']['layers'][control['fetch']],
                                                result['controls']['layers'][control['ram']]]
            assert _physical(debug, BANK_A + control['offset']) == '3412'
            assert _physical(debug, BANK_B + control['offset']) == '0000'
            if control['profile_options']:
                assert debug.clock_observe()['virtual_ns'] == control['virtual_ns']
                assert debug.retrace_observe()['observed_ns'] == control['virtual_ns']
            point = debug.breakpoint(control['ready'])
            assert debug.run(timeout_ms=15000, stop_on_hook=True)['outcome'] == 'breakpoint'
            assert debug.dos_task_observe()['matches_binding'] is False
            debug.delete_breakpoint(point['breakpoint_id'])
            stopped = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert stopped['outcome'] == 'task-switch'
            assert debug.hooks()['hooks'][0]['hits'] == 1
            point = debug.breakpoint(control['ready'])
            assert debug.run(timeout_ms=15000, stop_on_hook=True)['outcome'] == 'breakpoint'
            assert debug.dos_task_observe()['task_id'] == control['task_id']
            debug.delete_breakpoint(point['breakpoint_id'])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 2
            assert hit['hook_hits'][0]['hook'] == control['hook']
    print(json.dumps({'passed': True, 'pid': os.getpid()}))


@pytest.mark.parametrize('profile', ['standard', 'virtual-precise'])
def test_remapped_task_checkpoint_rebinds_only_original_context(tmp_path, profile):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk_options = {'config': b'SWITCHES=/F\r\n' + BASELINE_CONFIG} if profile == 'virtual-precise' else {}
    profile_options = dict(clock_profile='virtual', retrace='precise') if profile == 'virtual-precise' else {}
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'], **disk_options)
    data, marker = task_fixture(tmp_path, runtime['NASM'])
    source = tmp_path / 'TASK.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'tasks.fdb'

    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        fetch = project.debug_layer('task-a-fetch', kind='execute', patches=[dict(
            address=hex(static + marker['fetch']), expected_hex='90', data_hex='f8')])['layer']
        with _launch(project, runtime, tmp_path, disk, **profile_options) as debug:
            info = debug.dos_process_info()
            base = int(info['source_mapping']['runtime_base'])
            region = ((base - 0x100) & ~4095) - 4096
            offset = base + marker['scratch'] - region
            fetch_offset = base + marker['fetch'] - region
            flags_offset = base + marker['flags'] - region
            assert 0 <= offset < BANK_PAGES * 4096
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            registers_a = debug.registers()
            assert registers_a['cpu_mode'] == 'v86' and registers_a['address_state']['paging']
            assert _translated(debug, base + marker['scratch']) == BANK_A + offset
            assert _physical(debug, BANK_A + offset) == _physical(debug, BANK_B + offset) == '0000'
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            assert binding['task_id']
            observed_a = debug.dos_task_observe()
            anchor_a = bytes.fromhex(_physical(debug, ANCHOR, 56))
            assert anchor_a[:8] == b'FDBTASK1' and anchor_a[8:24].hex() == MONITOR_UUID
            assert struct.unpack_from('<QQQII', anchor_a, 24) == (0, 0xa1, 1, 1, 0)
            ram = debug.layer_patch('task-a-data', BANK_A + offset,
                expected_hex='0000', data_hex='3412', space='physical', activate=False)['layer']
            debug.layers([fetch, ram])
            # The authored carry probe writes AX=0 in A after its CLC fetch
            # overlay. B writes AX=1 and must never dispatch this guard.
            value = int(debug.registers()['registers']['rax'], 16) & ~0xffff
            hook = debug.hook(hex(static + marker['hook']), space='source', once=False, max_hits=3,
                actions=[dict(op='registers', registers={'rax': dict(expected=value, value=value)})])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 1
            assert _physical(debug, BANK_A + offset) == '3412'
            assert _physical(debug, BANK_B + offset) == '0000'
            assert _physical(debug, BANK_A + flags_offset) == '0000'
            assert _physical(debug, BANK_B + flags_offset) == 'ffff'
            assert _physical(debug, BANK_A + fetch_offset, 1) == '90'
            assert _physical(debug, BANK_B + fetch_offset, 1) == '90'
            assert debug.code(hex(static + marker['fetch']), length=1, space='source', view='execute')['hex'] == 'f8'
            saved_registers = debug.registers()
            saved_epoch = info['capture_epoch']
            virtual_ns = debug.clock_observe()['virtual_ns'] if profile_options else None
            if profile_options:
                retrace_before = debug.retrace_observe()
                assert retrace_before['observed_ns'] == virtual_ns
            artifact = debug.save_state()['artifact']
            old_vm = debug.vm.process
        assert old_vm.poll() is not None

    control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
        artifact=artifact, task_id=binding['task_id'], native_epoch=observed_a['native_epoch'],
        fetch=fetch, ram=ram, offset=offset, ready=base + marker['ready'], hook=hook['hook'],
        profile_options=profile_options, virtual_ns=virtual_ns)
    control_path = tmp_path / 'task-host-restore.json'
    control_path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                           capture_output=True, text=True, timeout=180)
    assert child.returncode == 0, child.stderr[-4000:]
    assert json.loads(child.stdout)['passed'] is True

    # Reopen the persisted project in a separate Python Project/session and VM.
    with Project(db) as project:
        with _launch(project, runtime, tmp_path, disk, **profile_options) as debug:
            fresh_vm = debug.vm.process
            fresh_epoch = debug.dos_process_info()['capture_epoch']
            restored = debug.load_state(artifact)
            assert fresh_vm.poll() is not None and debug.vm.process is not old_vm
            info = debug.dos_process_info()
            assert restored['source_binding_restored'] and info['capture_epoch'] not in (saved_epoch, fresh_epoch)
            assert debug.registers()['address_state'] == saved_registers['address_state']
            if profile_options:
                assert debug.clock_observe()['virtual_ns'] == virtual_ns
                retrace_after = debug.retrace_observe()
                for field in ('observed_ns', 'raw', 'phase', 'timing'):
                    assert retrace_after[field] == retrace_before[field]
            assert _translated(debug, base + marker['scratch']) == BANK_A + offset
            fetch = restored['controls']['layers'][fetch]
            restored_ram = restored['controls']['layers'][ram]
            assert restored_ram != ram
            ram = restored_ram
            assert debug.layers()['active'] == [fetch, ram]
            assert _physical(debug, BANK_A + offset) == '3412'
            assert _physical(debug, BANK_B + offset) == '0000'
            assert debug.hooks()['hooks'][0]['hits'] == 1
            observed = debug.dos_task_observe()
            assert observed['matches_binding'] is True
            assert observed['task_id'] == binding['task_id']
            assert observed['native_epoch'] > observed_a['native_epoch']
            assert observed['context_generation'] > observed_a['context_generation']
            assert bytes.fromhex(_physical(debug, ANCHOR, 56)) == anchor_a

            # The same linear address now identifies task B. No source-bound
            # hook action or layer may accidentally attach to that task.
            point = debug.breakpoint(base + marker['ready'])
            stop = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert stop['outcome'] == 'breakpoint', stop
            state_b = debug.registers()['address_state']
            assert state_b != saved_registers['address_state']
            assert _translated(debug, base + marker['scratch']) == BANK_B + offset
            assert _physical(debug, BANK_A + offset) == '3512'
            assert _physical(debug, BANK_B + offset) == '0000'
            assert _physical(debug, BANK_B + fetch_offset, 1) == '90'
            assert debug.hooks()['hooks'][0]['hits'] == 1
            observed_b = debug.dos_task_observe()
            assert observed_b['matches_binding'] is False
            assert observed_b['task_id'] != binding['task_id']
            assert observed_b['context_generation'] > observed['context_generation']
            anchor_b = bytes.fromhex(_physical(debug, ANCHOR, 56))
            assert struct.unpack_from('<QQQII', anchor_b, 24) == (2, 0xb2, 2, 1, 0)
            debug.delete_breakpoint(point['breakpoint_id'])
            # A linear execution breakpoint for A is encountered in B; the
            # engine reports the switch, retains the hook and applies no action.
            stop = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert stop['outcome'] == 'task-switch', stop
            assert debug.hooks()['hooks'][0]['hits'] == 1
            point = debug.breakpoint(base + marker['ready'])
            stop = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert stop['outcome'] == 'breakpoint', stop
            returned = debug.dos_task_observe()
            assert returned['matches_binding'] is True and returned['task_id'] == binding['task_id']
            assert returned['context_generation'] > observed_b['context_generation']
            anchor_a_again = bytes.fromhex(_physical(debug, ANCHOR, 56))
            assert struct.unpack_from('<QQQII', anchor_a_again, 24) == (4, 0xa1, 1, 1, 0)
            assert _translated(debug, base + marker['scratch']) == BANK_A + offset
            assert _physical(debug, BANK_B + offset) == '0100'
            assert _physical(debug, BANK_B + flags_offset) == '0100'
            assert debug.hooks()['hooks'][0]['hits'] == 1
            debug.delete_breakpoint(point['breakpoint_id'])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 2
            assert hit['hook_hits'][0]['hook'] == hook['hook']
            debug.delete_hook(hook['hook'])
            debug.layers([], conflict='keep_changed')
            done = debug.run(timeout_ms=15000)
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert digest(boot) == boot_hash
    assert digest(disk['image']) == disk['prepared_sha256']


@pytest.mark.parametrize('case', ['com', 'mz'])
def test_remapped_protected_checkpoint_preserves_descriptors_and_future_task_hook(tmp_path, case):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = task_fixture(tmp_path, runtime['NASM'])
    if case == 'mz':
        data, marker = task_mz(data, marker)
    source = tmp_path / ('TASK.EXE' if case == 'mz' else 'TASK.COM')
    source.write_bytes(data)
    options = {} if case == 'mz' else {'image': 'com'}
    with Project.create(tmp_path / 'protected-task.fdb', source, **options) as project:
        static = project.regions(1)[0].start
        fetch = project.debug_layer('protected-fetch', kind='execute', patches=[dict(
            address=hex(static + marker['fetch']), expected_hex='90', data_hex='f8')])['layer']
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            region = ((base if case == 'mz' else base - 0x100) & ~4095) - 4096
            offset = base + marker['scratch'] - region
            point = debug.breakpoint(base + marker['pm'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            before = debug.registers()
            assert before['cpu_mode'] == 'protected' and before['address_state']['paging']
            assert before['address_state']['code_bits'] == before['address_state']['stack_bits'] == 32
            assert _translated(debug, base + marker['scratch']) == BANK_A + offset
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            ram = debug.layer_patch('protected-data', BANK_A + offset,
                expected_hex='0000', data_hex='3412', space='physical', activate=False)['layer']
            debug.layers([fetch, ram])
            hook = debug.hook(hex(static + marker['hook']), space='source', once=False,
                max_hits=3, actions=[dict(op='layers', layers=[fetch, ram])])
            artifact = debug.save_state()['artifact']
            restored = debug.load_state(artifact)
            assert restored['task_identity']['task_id'] == binding['task_id']
            after = debug.registers()
            for field in ('registers', 'address_state', 'cpu_mode'):
                assert after[field] == before[field]
            assert debug.hooks()['hooks'][0]['hits'] == 0
            assert _translated(debug, base + marker['scratch']) == BANK_A + offset
            assert _physical(debug, BANK_A + offset) == '3412'
            assert _physical(debug, BANK_B + offset) == '0000'
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 1
            assert hit['hook_hits'][0]['hook'] == hook['hook']
            assert debug.registers()['cpu_mode'] == 'v86'
            assert debug.dos_task_observe()['matches_binding'] is True
            debug.delete_hook(hook['hook'])
            debug.layers([], conflict='keep_changed')
            done = debug.run(timeout_ms=15000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42
    assert source.read_bytes() == data and digest(boot) == boot_hash


if __name__ == '__main__':
    _child_restore(sys.argv[1])
