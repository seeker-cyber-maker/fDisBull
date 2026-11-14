"""Native guards for the authored DOS software-task lifetime protocol.

The monitor is an authored fixture; these tests do not claim QEMM/DESQview
compatibility. Odd-anchor edits and reset are explicitly host-assisted probes.
"""
from contextlib import contextmanager
from pathlib import Path
import struct
import time

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_dos_tasks import COMMAND
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_task_fixture import ANCHOR, MONITOR_UUID, BANK_A, task_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


@contextmanager
def task_case(tmp_path, *, recreate_a=False):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = task_fixture(tmp_path, runtime['NASM'], recreate_a=recreate_a)
    source = tmp_path / 'TASK.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'task.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = int(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            yield project, debug, base, marker
    assert source.read_bytes() == data and digest(boot) == boot_hash


def _anchor(debug):
    return bytes.fromhex(debug.memory(ANCHOR, length=56, space='physical')['hex'])


def test_native_recreated_lifetime_cannot_dispatch_old_hook(tmp_path):
    with task_case(tmp_path, recreate_a=True) as (project, debug, base, marker):
        static = project.regions(1)[0].start
        binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
        original = debug.dos_task_observe()
        assert original['matches_binding'] and original['incarnation'] == 1
        original_context = original['context']
        expected = (int(debug.registers()['registers']['rax'], 16) & ~0xffff) | 1
        modified = expected ^ 0x8000
        hook = debug.hook(hex(static + marker['hook']), space='source', once=False, max_hits=3,
            actions=[dict(op='registers', registers={'rax': dict(expected=expected, value=modified)})])
        first = debug.run(timeout_ms=15000, stop_on_hook=True)
        assert first['outcome'] == 'hook' and first['hook_hits'][0]['hit'] == 1
        assert int(debug.registers()['registers']['rax'], 16) == modified

        point = debug.breakpoint(base + marker['ready'])
        assert debug.run(timeout_ms=15000, stop_on_hook=True)['outcome'] == 'breakpoint'
        debug.delete_breakpoint(point['breakpoint_id'])
        observed_b = debug.dos_task_observe()
        assert observed_b['matches_binding'] is False and observed_b['cookie'] == 0xb2
        stop_b = debug.run(timeout_ms=15000, stop_on_hook=True)
        assert stop_b['outcome'] == 'task-switch', stop_b
        assert debug.hooks()['hooks'][0]['hits'] == 1
        assert int(debug.registers()['registers']['rax'], 16) & 0xffff == 1

        point = debug.breakpoint(base + marker['ready'])
        assert debug.run(timeout_ms=15000, stop_on_hook=True)['outcome'] == 'breakpoint'
        debug.delete_breakpoint(point['breakpoint_id'])
        new_a = debug.dos_task_observe()
        assert new_a['matches_binding'] is False
        assert new_a['cookie'] == binding['cookie'] == 0xa1
        assert (binding['incarnation'], new_a['incarnation']) == (1, 3)
        assert new_a['task_id'] != binding['task_id']
        assert new_a['context_generation'] > observed_b['context_generation'] > original['context_generation']
        for field in ('cr3', 'tr-selector', 'tr-base', 'cs-selector', 'eip', 'esp'):
            assert new_a['context'][field] == original_context[field]
        anchor = _anchor(debug)
        assert struct.unpack_from('<QQQII', anchor, 24) == (4, 0xa1, 3, 1, 0)
        region = ((base - 0x100) & ~4095) - 4096
        translated = debug.memory_translation(base + marker['scratch'], length=2)
        assert int(translated['physical_address'], 16) == BANK_A + base + marker['scratch'] - region
        stop_new_a = debug.run(timeout_ms=15000, stop_on_hook=True)
        assert stop_new_a['outcome'] == 'task-switch', stop_new_a
        assert debug.hooks()['hooks'][0]['hits'] == 1
        assert int(debug.registers()['registers']['rax'], 16) & 0xffff == 1
        debug.delete_hook(hook['hook'])
        done = debug.run(timeout_ms=15000)
        assert done['outcome'] == 'guest_exit', done
        assert done['process']['termination']['code'] == 42


def test_native_task_query_rejects_mmio_without_changing_stopped_pc(tmp_path):
    with task_case(tmp_path) as (_, debug, _, _):
        before = debug.registers()
        assert COMMAND in debug.vm.qmp_commands
        # Deliberately bypass the public Python RAM-range check: this tests the
        # native QMP implementation's own refusal of the VGA MMIO aperture.
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call(COMMAND, {'anchor-address': 0xa0000})
        assert debug.registers() == before
        assert debug.vm.qmp.call('query-status')['running'] is False


def test_native_binding_rejects_wrong_uuid_and_odd_anchor_before_ownership(tmp_path):
    with task_case(tmp_path) as (_, debug, _, _):
        before = _anchor(debug)
        registers = debug.registers()
        with pytest.raises(ValueError, match='monitor'):
            debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor='ff' * 16)
        assert getattr(debug, '_dos_task_binding', None) is None
        assert _anchor(debug) == before and debug.registers() == registers
        # Host-assisted fault injection: place the scheduler sequence in an odd
        # in-progress state, test refusal, and restore the exact initial bytes.
        debug.write_memory(ANCHOR + 24, '0100000000000000', expected_hex=before[24:32].hex())
        with pytest.raises(ValueError, match='transition|stable'):
            debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
        assert getattr(debug, '_dos_task_binding', None) is None
        debug.write_memory(ANCHOR + 24, before[24:32].hex(), expected_hex='0100000000000000')
        assert _anchor(debug) == before and debug.registers() == registers
        binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
        assert binding['incarnation'] == 1 and debug.dos_task_observe()['matches_binding']


def test_native_reset_preserves_anchor_but_invalidates_task_epoch(tmp_path):
    with task_case(tmp_path) as (_, debug, _, _):
        debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
        observed = debug.dos_task_observe()
        anchor = _anchor(debug)
        # Explicit host-assisted reset; this is not ordinary DOS lifecycle.
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while True:
            native = debug.vm.qmp.call(COMMAND, {'anchor-address': ANCHOR})
            if native['epoch'] > observed['native_epoch']:
                break
            assert time.monotonic() < deadline, 'Reset did not advance native task epoch'
        assert bytes.fromhex(native['anchor-hex']) == anchor
        with pytest.raises(DebuggerError, match='epoch changed|regressed'):
            debug.dos_task_observe()
        assert debug.vm.process.poll() is not None
