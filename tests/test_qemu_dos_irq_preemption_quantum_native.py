"""Real IRQ0 quantum-three phase survives a cold QEMU replacement.

The authored guest sends its normal PIC EOI; it does not select a task or
issue a software yield. This bounded witness ends at B's entry and makes no
DOS cleanup or compatibility claim.
"""
from pathlib import Path

from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
from test_qemu_dos_irq_preemption_native import _hit, _irq_frame, _number
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


def _status(debug):
    native = debug.dos_task_scheduler_observe()
    status = native['preemption']
    assert native['api-version'] in (2, 3)
    assert status['model'] == ('qemu-pc-pic-preemption-v2' if native['api-version'] == 3
                               else 'qemu-pc-pic-preemption-v1')
    assert status['enabled'] and status['irq'] == 0 and status['quantum'] == 3
    assert status['pic-irq-base'] == 0x20 and not status['pic-mask'] & 1
    return status


def test_irq0_quantum_three_cold_restore_preserves_inflight_phase(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = irq_fixture(tmp_path, runtime['NASM'])
    source = tmp_path / 'IRQQUANT.COM'
    source.write_bytes(data)
    with Project.create(tmp_path / 'quantum.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('irq_hook', 'irq_fetch', 'irq_count', 'return_ip', 'irq_data', 'scratch', 'loop_count')
            addresses = [base + marker[name] for name in names]
            addresses.extend((base + marker['return_ip'] + 3, base + marker['loop_count'] + 3))
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addresses.extend((base + marker[name] - 64, base + marker[name] - 1))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            debug.dos_task_scheduler()
            flags_b = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags_b)
            debug.dos_task_preemption(irq=0, quantum=3, enabled=True)
            upper_bx = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook = debug.hook(hex(static + marker['irq_hook']), task=a, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            _hit(debug, hook, 1, 0xa11a, 0x1111, 1, False)
            first = _status(debug)
            assert first['ack-count'] == 1 and first['eoi-count'] == 0
            assert first['quantum-progress'] == 0 and first['preemption-count'] == 0
            assert first['inflight'] and first['inflight-cookie'] == 0xa1 and first['pic-isr'] & 1
            assert debug.dos_task_observe()['task_id'] == a
            _hit(debug, hook, 2, 0xa11a, 0x1111, 1, False)
            second = _status(debug)
            assert second['ack-count'] == 2 and second['eoi-count'] == 1
            assert second['quantum-progress'] == 1 and second['preemption-count'] == 0
            assert second['inflight'] and second['inflight-cookie'] == 0xa1 and second['pic-isr'] & 1
            context = _irq_frame(debug, a, 0xa1, base + marker['irq_count'],
                                 base + marker['return_ip'], live=True, count=2)
            saved = debug.save_state()
            old_vm = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert old_vm.poll() is not None and debug.vm.process is not old_vm
            assert restored['source_binding_restored'] is True
            assert set(restored['task_views']['tasks']) == {a, b}
            assert _status(debug) == second
            assert debug.dos_task_observe()['task_id'] == a
            same = _irq_frame(debug, a, 0xa1, base + marker['irq_count'],
                              base + marker['return_ip'], live=True, count=2)
            assert same['frames'] == context['frames']
            assert debug.hooks()['hooks'][0]['hook'] == hook
            assert debug.hooks()['hooks'][0]['hits'] == 2
            _hit(debug, hook, 3, 0xa11a, 0x1111, 1, False)
            third = _status(debug)
            assert third['ack-count'] == 3 and third['eoi-count'] == 2
            assert third['quantum-progress'] == 2 and third['preemption-count'] == 0
            assert third['inflight'] and third['inflight-cookie'] == 0xa1 and third['pic-isr'] & 1
            entry = debug.breakpoint(base + marker['b_entry'])
            stop = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert stop['outcome'] == 'breakpoint', stop
            debug.delete_breakpoint(entry['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == b
            switched = _status(debug)
            assert switched['ack-count'] == 3 and switched['eoi-count'] == 3
            assert switched['quantum-progress'] == 0 and switched['preemption-count'] == 1
            assert switched['last-valid'] and switched['last-irq'] == 0
            assert switched['last-vector'] == 0x20
            assert switched['last-from-uuid'] == switched['last-to-uuid'] == MONITOR_UUID
            assert switched['last-from-cookie'] == 0xa1 and switched['last-from-incarnation'] == 1
            assert switched['last-to-cookie'] == 0xb2 and switched['last-to-incarnation'] == 2
            assert not switched['pic-isr'] & 1
    assert source.read_bytes() == data and digest(boot) == boot_hash
