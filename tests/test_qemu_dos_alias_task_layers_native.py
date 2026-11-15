"""Same-physical-page task-private layers with real DOS and cold restore.

The software scheduler changes only a cooperating anchor and emits the native
commit doorbell. Guest code, CR3, TSS and physical pages are shared; the guest
writes a separate unlayered audit log. This is an authored witness, not vendor
QEMM or DESQview qualification.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_dos_alias_task_fixture import ANCHOR, BANK_A, MONITOR_UUID, alias_task_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


LOG = 0x150200


def _view(debug, task, address, view, length):
    result = debug.dos_task_memory(address, length=length, task=task, view=view)
    assert result['task_id'] == task and result['view'] == view
    return result['hex']


def _logs(debug, count):
    data = bytes.fromhex(debug.memory(LOG, length=4 * count, space='physical')['hex'])
    return [struct.unpack_from('<HH', data, i * 4) for i in range(count)]


def _hit(debug, hook_id, count):
    result = debug.run(timeout_ms=15000, stop_on_hook=True)
    assert result['outcome'] == 'hook', result
    assert result['hook_hits'][0]['hook'] == hook_id
    assert result['hook_hits'][0]['hit'] == count
    return result


def _resume_from_cold(control):
    runtime = _inputs()
    with Project(control['database']) as project:
        with _launch(project, runtime, control['directory'], {'image': control['disk']},
                     **control['profile_options']) as debug:
            fresh = debug.vm.process
            restored = debug.load_state(control['artifact'])
            assert fresh.poll() is not None and restored['source_binding_restored']
            current = debug.dos_task_observe()
            assert current['matches_binding'] is True and current['task_id'] == control['task_a']
            assert current['native_epoch'] > control['saved_native_epoch']
            if control['profile_options']:
                assert debug.clock_observe()['virtual_ns'] == control['virtual_ns']
                retrace = debug.retrace_observe()
                for key in ('observed_ns','raw','phase','timing'):
                    assert retrace[key] == control['retrace'][key]
            a, b = control['task_a'], control['task_b']
            scratch, fetch = control['scratch'], control['fetch']
            assert _view(debug, a, scratch, 'ram', 2) == '3512'
            assert _view(debug, b, scratch, 'ram', 2) == '7956'
            assert _view(debug, a, scratch, 'base', 2) == '0000'
            assert _view(debug, b, scratch, 'base', 2) == '0000'
            assert _view(debug, a, fetch, 'execute', 1) == 'f8'
            assert _view(debug, b, fetch, 'execute', 1) == 'f9'
            assert _view(debug, a, fetch, 'base', 1) == '90'
            assert _logs(debug, 2) == [(0x1234, 0), (0x5678, 1)]
            hooks = {x['hook']: x for x in debug.hooks()['hooks']}
            assert hooks[control['hook_a']]['hits'] == 2
            assert hooks[control['hook_b']]['hits'] == 1
            assert debug.dos_task_layers(task=a)['active']
            assert debug.dos_task_layers(task=b)['active']

            _hit(debug, control['hook_b'], 2)
            assert _logs(debug, 3) == [(0x1234, 0), (0x5678, 1), (0x1235, 0)]
            _hit(debug, control['hook_a'], 3)
            assert _logs(debug, 4) == [(0x1234, 0), (0x5678, 1), (0x1235, 0), (0x5679, 1)]
            assert _view(debug, a, scratch, 'ram', 2) == '3612'
            assert _view(debug, b, scratch, 'ram', 2) == '7a56'
            assert _view(debug, a, scratch, 'base', 2) == '0000'
            # This breakpoint is after the guest records its fifth data/fetch
            # observation and before its monitor exits to DOS.
            point = debug.breakpoint(control['logged'])
            stop = debug.run(timeout_ms=15000)
            assert stop['outcome'] == 'breakpoint', stop
            assert _logs(debug, 5) == [(0x1234, 0), (0x5678, 1), (0x1235, 0), (0x5679, 1), (0x1236, 0)]
            debug.delete_breakpoint(point['breakpoint_id'])
            for hook in list(debug.hooks()['hooks']):
                debug.delete_hook(hook['hook'])
            done = debug.run(timeout_ms=15000)
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42
    return {'passed': True}


@pytest.mark.parametrize('profile', ['standard','virtual-precise'])
def test_native_aliased_task_layers_cold_restore(tmp_path, profile):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    options = {'config': b'SWITCHES=/F\r\n' + BASELINE_CONFIG} if profile == 'virtual-precise' else {}
    profile_options = dict(clock_profile='virtual',retrace='precise') if profile == 'virtual-precise' else {}
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],**options)
    source_bytes, marker = alias_task_fixture(tmp_path, runtime['NASM'])
    source = tmp_path / 'ALIAS.COM'
    source.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    db = tmp_path / 'alias.fdb'

    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk,**profile_options) as debug:
            base = int(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            initial = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            switching = debug.dos_task_switching()
            assert switching['enabled'] is True and switching['task']['task_id'] == initial['task_id']
            region = ((base - 0x100) & ~4095) - 4096
            scratch = BANK_A + base + marker['scratch'] - region
            fetch = BANK_A + base + marker['fetch'] - region
            pages = sorted({scratch & ~4095, fetch & ~4095})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == initial['task_id'] and b != a
            for task, ram_hex, instruction in ((a, '3412', 'f8'), (b, '7856', 'f9')):
                ram = debug.dos_task_layer_patch('private-data-' + task[-8:], scratch,
                    expected_hex='0000', data_hex=ram_hex, kind='ram', task=task, activate=False)['layer']
                code = debug.dos_task_layer_patch('private-fetch-' + task[-8:], fetch,
                    expected_hex='90', data_hex=instruction, kind='execute', task=task, activate=False)['layer']
                debug.dos_task_layers([ram, code], task=task)
                assert _view(debug, task, scratch, 'ram', 2) == ram_hex
                assert _view(debug, task, fetch, 'execute', 1) == instruction
                assert _view(debug, task, scratch, 'base', 2) == '0000'
                assert _view(debug, task, fetch, 'base', 1) == '90'
            # Real GDB memory is always the underlying shared page, never a
            # side-effecting switch to the currently selected private view.
            assert debug.memory(scratch, length=2, space='physical')['hex'] == '0000'
            upper = int(debug.registers()['registers']['rax'], 16) & ~0xffff
            hook_a = debug.hook(hex(static + marker['hook']), space='source', task=a,
                once=False, max_hits=3, actions=[dict(op='registers', registers={
                    'rax': dict(expected=upper, value=upper)})])['hook']
            _hit(debug, hook_a, 1)
            ctx_a = debug.dos_task_observe()
            # Register B's hook only after the native monitor selects B.
            point = debug.breakpoint(base + marker['ready'])
            stop = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert stop['outcome'] == 'breakpoint', stop
            debug.delete_breakpoint(point['breakpoint_id'])
            selected_b = debug.dos_task_observe()
            assert selected_b['task_id'] == b and selected_b['matches_binding'] is False
            hook_b = debug.hook(hex(static + marker['hook']), space='source', task=b,
                once=False, max_hits=3, actions=[dict(op='registers', registers={
                    'rax': dict(expected=upper | 1, value=upper | 1)})])['hook']
            _hit(debug, hook_b, 1)
            ctx_b = debug.dos_task_observe()
            assert ctx_b['task_id'] == b and ctx_b['matches_binding'] is False
            for field in ('cr3', 'tr-selector', 'tr-base', 'cs-selector', 'eip', 'esp'):
                assert ctx_a['context'][field] == ctx_b['context'][field]
            _hit(debug, hook_a, 2)
            observed = debug.dos_task_observe()
            assert observed['task_id'] == a and observed['matches_binding'] is True
            assert _logs(debug, 2) == [(0x1234, 0), (0x5678, 1)]
            assert _view(debug, a, scratch, 'ram', 2) == '3512'
            assert _view(debug, b, scratch, 'ram', 2) == '7956'
            virtual_ns = debug.clock_observe()['virtual_ns'] if profile_options else None
            retrace = debug.retrace_observe() if profile_options else None
            if profile_options: assert retrace['observed_ns'] == virtual_ns
            saved = debug.save_state()
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                artifact=saved['artifact'], task_a=a, task_b=b, scratch=scratch, fetch=fetch,
                hook_a=hook_a, hook_b=hook_b, logged=base + marker['logged'],
                saved_native_epoch=observed['native_epoch'],profile_options=profile_options,
                virtual_ns=virtual_ns,retrace=retrace)
            old_vm = debug.vm.process
        assert old_vm.poll() is not None
    control_path = tmp_path / 'alias-restore.json'
    control_path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                           capture_output=True, text=True, timeout=180, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[-4000:]
    assert json.loads(child.stdout)['passed'] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_resume_from_cold(json.loads(Path(sys.argv[1]).read_text()))))
