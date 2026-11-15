"""Native fail-closed guards on guest-authored nested PIC/IRET misuse."""
from contextlib import contextmanager
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_dos_cascade_fixture import ANCHOR, MONITOR_UUID, cascade_fixture
from test_qemu_dos_cascade_preemption_native import _open, _outstanding, _queue_pair, _status
from test_qemu_dos_irq_preemption_native import _native_context, _number
from test_qemu_dos_modes_checkpoint_native import _inputs


@contextmanager
def _at_nested_entry(tmp_path, fault):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
                                config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = cascade_fixture(tmp_path, runtime['NASM'], fault=fault)
    source = tmp_path / 'BADPIC.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'badpic.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        with _open(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('scratch', 'outer_count', 'inner_count', 'key_count', 'key_bytes',
                     'outer_return', 'inner_return', 'observed_data', 'rtc_regc', 'inner_hook')
            addresses = [base + marker[name] for name in names]
            addresses.extend((base + marker['key_bytes'] + 3,
                              base + marker['outer_return'] + 3, base + marker['inner_return'] + 3))
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addresses.extend((base + marker[name] - 96, base + marker[name] - 1))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            debug.dos_task_scheduler()
            flags_b = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags_b)
            debug.dos_task_preemption(irq=8, quantum=1, enabled=True)
            wait = debug.breakpoint(base + marker['outer_wait'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(wait['breakpoint_id'])
            _outstanding(_status(debug), [(8, 0x28, 2, 0, 3, 0, 0xa1)])
            point = debug.breakpoint(base + marker['inner_hook'])
            _queue_pair(debug)
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            state = debug.keyboard_state()
            assert state['pending_edges'] == 0 and not state['leases']
            _outstanding(_status(debug), [(8, 0x28, 2, 0, 3, 0, 0xa1),
                                         (1, 0x21, 1, None, 1, 0, 0xa1)])
            yield debug, a, b
    assert source.read_bytes() == data and digest(boot) == boot_hash


def _raw_scheduler(debug):
    return debug.vm.qmp.call('x-fdisbull-task-scheduler-observe')


def _slot(status, cookie):
    return next(item for item in status['tasks'] if item['cookie'] == cookie)


def _raw_continue_to_fault(debug):
    # The production host closes on native fault by design. This diagnostic
    # reads the GDB stop and QMP receipt directly before invoking that wrapper.
    reply, timed_out = debug.vm.debugger().execute('c', 45000)
    assert not timed_out and reply[:1] in (b'T', b'S')
    assert debug.vm.qmp.call('query-status')['running'] is False
    status = _raw_scheduler(debug)
    assert status.get('fault'), status
    return status


def test_nested_iret_without_master_eoi_refuses_before_popping_frame(tmp_path):
    with _at_nested_entry(tmp_path, 'inner-no-eoi') as (debug, _, _):
        before = _raw_scheduler(debug)
        cpu_before = _native_context(debug, 0xa1, 1)
        assert cpu_before['interrupt-depth'] == 2
        frame = cpu_before['frames'][-1]
        status = _raw_continue_to_fault(debug)
        cpu_after = _native_context(debug, 0xa1, 1)
        assert status['preemption']['preemption-count'] == before['preemption']['preemption-count'] == 0
        assert status['selected-cookie'] != 0xb2
        assert cpu_after['interrupt-depth'] == 2 and cpu_after['frames'] == cpu_before['frames']
        # Fault revokes scheduler selection: QMP then returns the saved slot,
        # not the stopped live CPU. Raw GDB ESP proves IRET did not pop.
        assert cpu_after['live'] is False
        registers = debug.vm.debugger().registers()
        assert _number(registers['rsp']) & frame['frame-sp-mask'] == frame['frame-sp']
        assert _slot(status, 0xa1)['frame-sha256'] == _slot(before, 0xa1)['frame-sha256']
        assert status['preemption']['pic-isr'] & 0x06 == 0x06
        assert status['preemption']['slave-isr'] & 1


def test_master_cascade_eoi_before_slave_faults_without_switch(tmp_path):
    with _at_nested_entry(tmp_path, 'master-before-slave') as (debug, _, _):
        before = _raw_scheduler(debug)
        status = _raw_continue_to_fault(debug)
        assert status['preemption']['preemption-count'] == before['preemption']['preemption-count'] == 0
        assert status['selected-cookie'] != 0xb2
        cpu = _native_context(debug, 0xa1, 1)
        assert cpu['interrupt-depth'] == 1 and cpu['frames'][0]['vector'] == 0x28
        assert not any(item['cookie'] == 0xb2 and item['context-valid'] is False
                       for item in status['tasks'])
