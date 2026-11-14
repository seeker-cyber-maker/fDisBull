"""Guest-originated task-view faults and direct native admission guards."""
from contextlib import contextmanager
from pathlib import Path
import struct
import time

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_alias_task_fixture import ANCHOR, BANK_A, MONITOR_UUID, alias_task_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


LOG = 0x150200


@contextmanager
def _case(tmp_path, *, commit='valid', start='ready'):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source_bytes, marker = alias_task_fixture(tmp_path, runtime['NASM'], commit=commit)
    source = tmp_path / 'GUARD.COM'
    source.write_bytes(source_bytes)
    with Project.create(tmp_path / 'guard.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = int(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker[start])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            region = ((base - 0x100) & ~4095) - 4096
            scratch = BANK_A + base + marker['scratch'] - region
            fetch = BANK_A + base + marker['fetch'] - region
            pages = sorted({scratch & ~4095, fetch & ~4095})
            task = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            assert task == binding['task_id']
            data = debug.dos_task_layer_patch('private-guard-data', scratch,
                expected_hex='0000', data_hex='3412', kind='ram', task=task, activate=False)['layer']
            code = debug.dos_task_layer_patch('private-guard-fetch', fetch,
                expected_hex='90', data_hex='f8', kind='execute', task=task, activate=False)['layer']
            debug.dos_task_layers([data, code], task=task)
            yield debug, task, scratch, pages
    assert source.read_bytes() == source_bytes and digest(boot) == boot_hash


def _native_args(cookie=0xa1, incarnation=1):
    return {'uuid': MONITOR_UUID, 'cookie': cookie, 'incarnation': incarnation}


def _run_to_fault(debug):
    # No hook is installed. The guest itself publishes its transition and
    # executes the doorbell. Never modify the task anchor from the host.
    before = bytes.fromhex(debug.memory(LOG, length=8, space='physical')['hex'])
    result = debug.run(timeout_ms=15000)
    assert result['outcome'] not in ('guest_exit', 'guest_tsr', 'exited', 'timeout'), result
    assert result.get('timed_out') is not True
    assert debug.vm.qmp.call('query-status')['running'] is False
    # Call QMP directly: the higher-level owner deliberately rejects a native
    # fault and may close the VM before the underlying receipt can be checked.
    raw = debug.vm.qmp.call('x-fdisbull-task-layer-observe', _native_args())
    assert raw.get('fault'), raw
    assert raw['selected-cookie'] == 0
    log = bytes.fromhex(debug.memory(LOG, length=8, space='physical')['hex'])
    assert struct.unpack_from('<HH', log) == (0x1234, 0)
    assert log[4:8] == before[4:8], 'Foreign task executed its body'


def test_retired_lifetime_reuse_does_not_restore_old_task_view(tmp_path):
    with _case(tmp_path) as (debug, _, _, pages):
        old = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
        assert debug.dos_task_retire(old)['retired'] is True
        new = debug.dos_task_register(cookie=0xb2, incarnation=3, pages=pages)['task_id']
        assert new != old
        with pytest.raises(ValueError, match='retired'):
            debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)
        with pytest.raises(DebuggerError, match='PRECONDITION'):
            debug.vm.qmp.call('x-fdisbull-task-register', {
                **_native_args(0xb2, 2), 'pages': [{'address': page} for page in pages],
            })
        # The guest is authored to publish old B2; B3's existence must not
        # permit the retired B2 to regain either task's view.
        _run_to_fault(debug)


@pytest.mark.parametrize('commit', ['odd', 'unknown'])
def test_invalid_guest_commit_revokes_current_view(tmp_path, commit):
    with _case(tmp_path, commit=commit) as (debug, _, _, pages):
        debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)
        _run_to_fault(debug)


def test_native_registration_rejects_mmio_and_page_table_atomically(tmp_path):
    with _case(tmp_path) as (debug, task, scratch, pages):
        current = debug.registers()
        control = current['address_state']['control']['CR3']
        cr3 = (int(control, 16) if isinstance(control, str) else control) & ~4095
        assert cr3 not in pages and cr3 != 0xa0000
        before_status = debug.vm.qmp.call('x-fdisbull-task-layer-observe', _native_args())
        before_ram = debug.dos_task_memory(scratch, length=2, task=task, view='ram')
        before_base = debug.dos_task_memory(scratch, length=2, task=task, view='base')
        assert before_ram['hex'] == '3412' and before_base['hex'] == '0000'
        for cookie, invalid_pages in ((0xe1, [0xa0000]), (0xe2, [cr3]),
                                      (0xe3, [pages[0], 0xa0000])):
            with pytest.raises(DebuggerError, match='PRECONDITION'):
                debug.vm.qmp.call('x-fdisbull-task-register', {
                    **_native_args(cookie, 1), 'pages': [{'address': page} for page in invalid_pages],
                })
            assert debug.vm.qmp.call('x-fdisbull-task-layer-observe', _native_args()) == before_status
            assert debug.dos_task_memory(scratch, length=2, task=task, view='ram')['sha256'] == before_ram['sha256']
            assert debug.dos_task_memory(scratch, length=2, task=task, view='base')['sha256'] == before_base['sha256']
            assert debug.registers() == current


@pytest.mark.parametrize('start', ['ready', 'pm'])
def test_registered_unconfigured_task_survives_cold_vm_restore(tmp_path, start):
    with _case(tmp_path, start=start) as (debug, task_a, scratch, pages):
        assert debug.registers()['cpu_mode'] == ('protected' if start == 'pm' else 'v86')
        task_b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
        assert task_b != task_a
        b_before = debug.dos_task_layers(task=task_b)
        assert b_before['generation'] == 0 and b_before['active'] == []
        assert b_before['native']['task-generation'] == 0
        assert debug.dos_task_memory(scratch, length=2, task=task_a, view='ram')['hex'] == '3412'
        assert debug.dos_task_memory(scratch, length=2, task=task_b, view='ram')['hex'] == '0000'
        assert debug.dos_task_memory(scratch, length=2, task=task_a, view='base')['hex'] == '0000'
        assert debug.hooks()['hooks'] == []
        saved = debug.save_state()
        prior_vm = debug.vm.process
        restored = debug.load_state(saved['artifact'])
        assert prior_vm.poll() is not None and debug.vm.process is not prior_vm
        assert restored['source_binding_restored'] is True
        assert set(restored['task_views']['tasks']) == {task_a, task_b}
        assert restored['native_task']['native_epoch'] > restored['native_task']['source_epoch']
        observed = debug.dos_task_observe()
        assert observed['matches_binding'] is True and observed['task_id'] == task_a
        b_after = debug.dos_task_layers(task=task_b)
        assert b_after['generation'] == 0 and b_after['active'] == []
        assert b_after['native']['task-generation'] == 0
        assert debug.dos_task_memory(scratch, length=2, task=task_a, view='ram')['hex'] == '3412'
        assert debug.dos_task_memory(scratch, length=2, task=task_b, view='ram')['hex'] == '0000'
        assert debug.dos_task_memory(scratch, length=2, task=task_a, view='base')['hex'] == '0000'
        assert debug.hooks()['hooks'] == []
        done = debug.run(timeout_ms=15000)
        assert done['outcome'] == 'guest_exit', done
        assert done['process']['termination']['code'] == 42


def test_monitor_commit_single_step_and_checkpoint_of_selected_b(tmp_path):
    with _case(tmp_path) as (debug, task_a, scratch, pages):
        task_b = debug.dos_task_register(cookie=0xb2,incarnation=2,pages=pages)['task_id']
        data = debug._checkpoint_source.read_bytes()
        marker = data.index(b'FMOD')
        commit, = struct.unpack_from('<H',data,marker+26)
        base = debug.dos_process_info()['source_mapping']['runtime_base']
        point = debug.breakpoint(base+commit)
        assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
        debug.delete_breakpoint(point['breakpoint_id'])
        # The monitor has published B, but has not executed OUTW yet. Raw
        # stepping can finish the commit; source attribution cannot adopt B.
        native = debug.vm.qmp.call('x-fdisbull-task-layer-observe',_native_args())
        assert native['selected-cookie'] == 0xa1 and native['sequence'] == 0
        with pytest.raises(ValueError,match='not committed'):
            debug.dos_task_bind(anchor_address=ANCHOR,expected_monitor=MONITOR_UUID)
        assert debug.step(timeout_ms=15000)['outcome'] == 'step'
        native = debug.vm.qmp.call('x-fdisbull-task-layer-observe',_native_args())
        assert native['selected-cookie'] == 0xb2 and native['sequence'] == 2
        assert native['pending'] is False and not native.get('fault')
        assert debug.dos_task_bind(anchor_address=ANCHOR,expected_monitor=MONITOR_UUID)['task_id'] == task_b
        saved = debug.save_state()
        restored = debug.load_state(saved['artifact'])
        assert restored['task_identity']['task_id'] == task_b
        assert debug.dos_task_observe()['matches_binding'] is True
        assert debug.dos_task_memory(scratch,length=2,task=task_a)['hex'] == '3512'
        assert debug.dos_task_memory(scratch,length=2,task=task_b)['hex'] == '0000'
        done = debug.run(timeout_ms=15000)
        assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42


def test_reset_revokes_private_view_and_invalidates_host_owner(tmp_path):
    with _case(tmp_path) as (debug, task, _, _):
        before = debug.vm.qmp.call('x-fdisbull-task-layer-observe',_native_args())
        debug.vm.qmp.call('set-action',{'reboot':'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic()+2
        while True:
            after = debug.vm.qmp.call('x-fdisbull-task-layer-observe',_native_args())
            if after['epoch'] > before['epoch']: break
            assert time.monotonic() < deadline
        assert after['selected-cookie'] == 0 and after['pending'] is False
        with pytest.raises(DebuggerError,match='epoch changed'):
            debug.dos_task_layers(task=task)
        assert debug.vm.process.poll() is not None
