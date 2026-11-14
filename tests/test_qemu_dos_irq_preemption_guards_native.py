"""Real PIC pending-IRQ deferral and x86 interrupt-shadow native guards."""
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
from test_qemu_dos_irq_preemption_native import _native_context, _number, _private
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


@pytest.mark.parametrize('guard', ['if', 'mask', 'chain-shadow'])
def test_real_irq0_defers_until_eligible_and_obeys_cpu_shadow(tmp_path, guard):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
                                config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path, runtime['NASM'], guard=guard)
    source = tmp_path / 'IRQGUARD.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'guard.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk, clock_profile='virtual') as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            bound = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            addrs = [base + marker[name] for name in
                     ('guard_progress', 'guard_marker', 'irq_count', 'irq_hook', 'return_ip')]
            addrs.extend((base + marker['guard_progress'] + 3, base + marker['return_ip'] + 3))
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addrs.extend((base + marker[name] - 64, base + marker[name] - 1))
            pages = sorted({address & ~4095 for address in addrs})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert bound['task_id'] == a
            debug.dos_task_scheduler()
            flags_b = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags_b)
            debug.dos_task_preemption(irq=0, quantum=1, enabled=True)
            release = debug.breakpoint(base + marker['guard_release'])
            handler = debug.breakpoint(base + marker['irq_hook'])
            result = debug.run(timeout_ms=45000)
            assert result['outcome'] == 'breakpoint', result
            assert _number(debug.registers()['linear_pc']) == base + marker['guard_release']
            debug.delete_breakpoint(release['breakpoint_id'])
            status = debug.dos_task_scheduler_observe()['preemption']
            assert status['enabled'] and status['irq'] == 0
            assert status['pic-irq-base'] == 0x20
            assert status['pic-irr'] & 1, 'Require an observed, latched IRQ0, not elapsed time'
            assert status['pic-isr'] & 1 == 0
            assert status['ack-count'] == status['eoi-count'] == status['preemption-count'] == 0
            assert debug.dos_task_observe()['task_id'] == a
            progress = int.from_bytes(_private(debug, a, base + marker['guard_progress'], 4), 'little')
            assert progress == 65536
            assert _private(debug, a, base + marker['irq_count'], 2) == b'\0\0'
            assert _private(debug, a, base + marker['guard_marker'], 1) == b'\0'
            flags = debug.registers()['registers'].get('eflags')
            assert flags is not None
            assert bool(_number(flags) & 0x200) is (guard == 'mask')
            assert bool(status['pic-mask'] & 1) is (guard == 'mask')

            # The guest now releases IF/mask itself; a user breakpoint stops
            # inside the real hardware IRQ handler, still before its EOI.
            result = debug.run(timeout_ms=45000)
            assert result['outcome'] == 'breakpoint', result
            assert _number(debug.registers()['linear_pc']) == base + marker['irq_hook']
            debug.delete_breakpoint(handler['breakpoint_id'])
            status = debug.dos_task_scheduler_observe()['preemption']
            assert status['ack-count'] == 1 and status['eoi-count'] == 0
            assert status['preemption-count'] == 0 and status['pic-isr'] & 1
            assert status['inflight'] and status['inflight-cookie'] == 0xa1
            frame = _native_context(debug, 0xa1, 1)['frames'][0]
            assert frame['kind'] == 'hardware' and frame['vector'] == 0x20
            assert _private(debug, a, base + marker['irq_count'], 2) == b'\x01\x00'
            if guard == 'if':
                # The instruction immediately following STI must retire.
                assert _private(debug, a, base + marker['guard_marker'], 1) == b'\x01'
                assert frame['pre-eip'] == 0x100 + marker['guard_after']
            elif guard == 'chain-shadow':
                # STI protects MOV SS itself; chained interrupt-delaying
                # instructions need not extend that protection to the INC.
                before_inc = 0x100 + marker['guard_after_movss']
                after_inc = 0x100 + marker['guard_after']
                assert frame['pre-eip'] in (before_inc, after_inc)
                expected_marker = b'\x00' if frame['pre-eip'] == before_inc else b'\x01'
                assert _private(debug, a, base + marker['guard_marker'], 1) == expected_marker
    assert source.read_bytes() == data and digest(boot) == boot_hash
