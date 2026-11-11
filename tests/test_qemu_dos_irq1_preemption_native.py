"""Real i8042 keyboard IRQ1 preempts native DOS tasks without guest yields.

This witness deliberately stops after the two guest-consumed keyboard edges;
closing the private session is not a DOS cleanup or keyboard-parity claim.
"""
from pathlib import Path

from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
from test_qemu_dos_irq_preemption_native import _native_context, _number, _private
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


def _status(debug):
    result = debug.dos_task_scheduler_observe()['preemption']
    assert result['model'] == 'qemu-pc-pic-preemption-v1'
    assert result['enabled'] and result['irq'] == 1 and result['quantum'] == 1
    assert result['pic-irq-base'] == 0x20
    assert result['pic-mask'] & 1 and not result['pic-mask'] & 2
    return result


def _frame(debug, task, cookie, irq_count, return_ip, *, live):
    context = _native_context(debug, cookie, 1 if cookie == 0xa1 else 2)
    assert context['live'] is live and context['interrupt-depth'] == 1
    frame = context['frames'][0]
    assert frame['kind'] == 'hardware' and frame['vector'] == 0x21
    assert int.from_bytes(_private(debug, task, irq_count, 2), 'little') == 1
    assert int.from_bytes(_private(debug, task, return_ip, 4), 'little') == frame['pre-eip']
    return frame


def test_real_i8042_irq1_preempts_two_native_tasks(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = irq_fixture(tmp_path, runtime['NASM'], irq=1)
    source = tmp_path / 'IRQKEY.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'irq1.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('irq_count', 'return_ip', 'irq_scancode', 'irq_hook', 'irq_fetch')
            addrs = [base + marker[name] for name in names]
            addrs.append(base + marker['return_ip'] + 3)
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addrs.extend((base + marker[name] - 64, base + marker[name] - 1))
            pages = sorted({address & ~4095 for address in addrs})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            debug.dos_task_scheduler()
            flags_b = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags_b)
            debug.dos_task_preemption(irq=1, quantum=1, enabled=True)
            hook = debug.breakpoint(base + marker['irq_hook'])
            lease = debug.keyboard_key_down('a')['lease']
            first = debug.run(timeout_ms=45000)
            assert first['outcome'] == 'breakpoint', first
            debug.delete_breakpoint(hook['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == a
            first_status = _status(debug)
            assert first_status['inflight'] and first_status['inflight-irq'] == 1
            assert first_status['inflight-vector'] == 0x21 and first_status['pic-isr'] & 2
            assert first_status['ack-count'] == 1 and first_status['eoi-count'] == 0
            assert first_status['preemption-count'] == 0
            a_frame = _frame(debug, a, 0xa1, base + marker['irq_count'],
                             base + marker['return_ip'], live=True)
            assert _private(debug, a, base + marker['irq_scancode'], 1) == b'\x1e'

            # EOI from A must be what advances the native scheduler to B.
            b_entry = debug.breakpoint(base + marker['b_entry'])
            switched = debug.run(timeout_ms=45000)
            assert switched['outcome'] == 'breakpoint', switched
            debug.delete_breakpoint(b_entry['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == b
            after_a = _status(debug)
            assert after_a['eoi-count'] == 1 and after_a['preemption-count'] == 1
            assert after_a['last-valid'] and after_a['last-irq'] == 1 and after_a['last-vector'] == 0x21
            assert after_a['last-from-cookie'] == 0xa1 and after_a['last-to-cookie'] == 0xb2
            assert not after_a['pic-isr'] & 2
            _frame(debug, a, 0xa1, base + marker['irq_count'], base + marker['return_ip'], live=False)

            # Release is queued while B is stopped, dispatched by the next
            # continue, then read by the guest itself from i8042 port 60h.
            hook = debug.breakpoint(base + marker['irq_hook'])
            debug.keyboard_key_up(lease)
            second = debug.run(timeout_ms=45000)
            assert second['outcome'] == 'breakpoint', second
            debug.delete_breakpoint(hook['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == b
            second_status = _status(debug)
            assert second_status['inflight'] and second_status['inflight-irq'] == 1
            assert second_status['pic-isr'] & 2
            assert second_status['ack-count'] == 2 and second_status['eoi-count'] == 1
            assert second_status['preemption-count'] == 1
            _frame(debug, b, 0xb2, base + marker['irq_count'], base + marker['return_ip'], live=True)
            assert _private(debug, b, base + marker['irq_scancode'], 1) == b'\x9e'

            return_pc = (a_frame['pre-cs'] << 4) + a_frame['pre-eip']
            resumed_point = debug.breakpoint(return_pc)
            resumed = debug.run(timeout_ms=45000)
            assert resumed['outcome'] == 'breakpoint', resumed
            debug.delete_breakpoint(resumed_point['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == a
            assert debug.registers()['cpu_mode'] == 'v86'
            assert _number(debug.registers()['linear_pc']) == return_pc
            after_b = _status(debug)
            assert after_b['eoi-count'] == 2 and after_b['preemption-count'] == 2
            assert after_b['last-irq'] == 1 and after_b['last-vector'] == 0x21
            assert after_b['last-from-cookie'] == 0xb2 and after_b['last-to-cookie'] == 0xa1
            assert not after_b['pic-isr'] & 2
    assert source.read_bytes() == data and digest(boot) == boot_hash
