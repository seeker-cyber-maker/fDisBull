"""Real RTC IRQ8 with nested i8042 IRQ1, PIC cascade EOIs and cold restore.

The authored guest reads RTC register C and actual i8042 bytes, sends normal
PIC EOIs and executes IRETD. It does not choose another task, fabricate an IRQ,
issue a software scheduler yield or copy interrupt frames.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_dos_cascade_fixture import ANCHOR, MONITOR_UUID, cascade_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch
from test_qemu_dos_irq_preemption_native import _native_context, _number, _private


def _open(project, runtime, directory, disk):
    return _launch(project, runtime, directory, disk, clock_profile='virtual')


def _status(debug, policy_irq=8):
    value = debug.dos_task_scheduler_observe()['preemption']
    assert value['model'] == 'qemu-pc-pic-preemption-v2'
    assert value['enabled'] and value['irq'] == policy_irq and value['quantum'] == 1
    assert value['pic-irq-base'] == 0x20 and value['slave-irq-base'] == 0x28
    assert value['pic-mask'] & 0x06 == 0 and value['slave-mask'] & 1 == 0
    assert value['outstanding-count'] == len(value['outstanding-frames'])
    assert value['ack-count'] - value['eoi-count'] == value['outstanding-count']
    return value


def _outstanding(status, expected):
    frames = status['outstanding-frames']
    assert len(frames) == len(expected)
    for frame, (irq, vector, master, slave, required, seen, cookie) in zip(frames, expected, strict=True):
        assert (frame['irq'], frame['vector'], frame['master-irq']) == (irq, vector, master)
        assert frame['slave-valid'] is (slave is not None)
        if slave is not None:
            assert frame['slave-irq'] == slave
        assert (frame['required-eoi-mask'], frame['seen-eoi-mask']) == (required, seen)
        assert frame['uuid'] == MONITOR_UUID and frame['cookie'] == cookie
        assert frame['incarnation'] == (1 if cookie == 0xa1 else 2)
        assert frame['ack-sequence'] > 0 and frame['frame-sequence'] > 0


def _frames(debug, cookie, task, control, vectors):
    context = _native_context(debug, cookie, 1 if cookie == 0xa1 else 2)
    frames = context['frames']
    assert context['interrupt-depth'] == len(vectors) == len(frames)
    assert [(row['kind'], row['vector']) for row in frames] == [('hardware', vector) for vector in vectors]
    for frame, vector in zip(frames, vectors, strict=True):
        assert frame['pic-irq-valid'] and frame['pic-vector'] == vector
        assert frame['pic-irq'] == (8 if vector == 0x28 else 1)
        assert frame['pic-controller'] == (1 if vector == 0x28 else 0)
        assert frame['pic-slave-valid'] is (vector == 0x28)
    if frames:
        assert int.from_bytes(_private(debug, task, control['outer_return'], 4), 'little') == frames[0]['pre-eip']
    if len(frames) > 1:
        assert int.from_bytes(_private(debug, task, control['inner_return'], 4), 'little') == frames[1]['pre-eip']
    return context


def _queue_pair(debug):
    lease = debug.keyboard_key_down('a')['lease']
    debug.keyboard_key_up(lease)


def _keys_consumed(debug, task, control):
    assert _private(debug, task, control['key_count'], 1) == b'\x02'
    assert _private(debug, task, control['key_bytes'], 2) == b'\x1e\x9e'
    state = debug.keyboard_state()
    assert state['pending_edges'] == 0 and not state['leases']


def _nested_before_eoi(debug, task, cookie, control):
    status = _status(debug, control.get('policy_irq', 8))
    assert status['pending'] is False
    _outstanding(status, [(8, 0x28, 2, 0, 3, 0, cookie),
                          (1, 0x21, 1, None, 1, 0, cookie)])
    assert status['pic-isr'] & 0x06 == 0x06 and status['slave-isr'] & 1
    if cookie == 0xa1:
        assert status['preemption-count'] == 0
    else:
        assert status['preemption-count'] >= 1
    _frames(debug, cookie, task, control, [0x28, 0x21])
    _keys_consumed(debug, task, control)
    return status


def _partial_outer(debug, task, cookie, control):
    status = _status(debug, control.get('policy_irq', 8))
    assert status['pending'] is (control.get('policy_irq', 8) == 1)
    _outstanding(status, [(8, 0x28, 2, 0, 3, 2, cookie)])
    assert status['pic-isr'] & 0x06 == 0x04
    assert status['slave-isr'] & 1 == 0
    _frames(debug, cookie, task, control, [0x28])
    return status


def _child(control):
    runtime = _inputs()
    disk = {'image': control['disk']}
    with Project(control['database']) as project:
        # Restore A's two hardware frames before either guest EOI. Execute
        # IRQ1's EOI/IRETD and the slave EOI, but do not permit a task switch.
        with _open(project, runtime, control['directory'], disk) as debug:
            fresh = debug.vm.process
            restored = debug.load_state(control['nested_artifact'])
            assert fresh.poll() is not None and restored['source_binding_restored']
            assert debug.dos_task_observe()['task_id'] == control['a']
            assert _nested_before_eoi(debug, control['a'], 0xa1, control) == control['nested_status']
            nested_frames = _frames(debug, 0xa1, control['a'], control, [0x28, 0x21])['frames']
            assert nested_frames == control['nested_frames']
            # Observe inner IRETD returning to A's interrupted ring-0 handler.
            assert nested_frames[1]['pre-cs'] == 8  # authored flat GDT code
            inner_return_pc = nested_frames[1]['pre-eip']
            point = debug.breakpoint(inner_return_pc)
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            registers = debug.registers()
            assert registers['cpu_mode'] == 'protected'
            assert _number(registers['linear_pc']) == inner_return_pc
            assert _number(registers['registers']['rsp']) & 0xffffffff == nested_frames[1]['pre-sp'] & 0xffffffff
            still_outer = _status(debug, control['policy_irq'])
            assert still_outer['pending'] is (control['policy_irq'] == 1)
            _outstanding(still_outer, [(8, 0x28, 2, 0, 3, 0, 0xa1)])
            assert still_outer['preemption-count'] == 0
            assert _frames(debug, 0xa1, control['a'], control, [0x28])['interrupt-depth'] == 1
            point = debug.breakpoint(control['after_slave'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            partial = _partial_outer(debug, control['a'], 0xa1, control)
            assert partial['preemption-count'] == 0
            assert debug.dos_task_observe()['task_id'] == control['a']

        # The second artifact was saved after slave EOI but before the outer
        # master EOI. Only the latter may allow A->B, with A's frame dormant.
        with _open(project, runtime, control['directory'], disk) as debug:
            fresh = debug.vm.process
            restored = debug.load_state(control['partial_artifact'])
            assert fresh.poll() is not None and restored['source_binding_restored']
            assert _partial_outer(debug, control['a'], 0xa1, control) == control['partial_status']
            assert debug.dos_task_observe()['task_id'] == control['a']
            hooks = {row['hook']: row for row in debug.hooks()['hooks']}
            assert hooks[control['hook_a']]['hits'] == 1
            point = debug.breakpoint(control['b_entry'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == control['b']
            status = _status(debug, control['policy_irq'])
            assert status['outstanding-count'] == 0 and status['preemption-count'] == 1
            assert status['last-irq'] == control['policy_irq']
            assert status['last-vector'] == (0x21 if control['policy_irq'] == 1 else 0x28)
            assert status['last-from-cookie'] == 0xa1 and status['last-to-cookie'] == 0xb2
            dormant = _frames(debug, 0xa1, control['a'], control, [0x28])
            assert not dormant['live'] and dormant['eip'] == control['after_master']
            saved_frame = dormant['frames'][0]
            assert saved_frame['width'] == 32 and not saved_frame['error-code-present']
            frame_address = saved_frame['frame-ss-base'] + saved_frame['frame-sp']
            saved_flags = int.from_bytes(_private(debug, control['a'], frame_address + 8, 4), 'little')
            return_pc = (saved_frame['pre-cs'] << 4) + saved_frame['pre-eip']
            # Register B's peer on the same nested ISR address while B is
            # selected, then wait for B's second real RTC IRQ8.
            hook_b = debug.hook(control['inner_source'], task=control['b'], space='source',
                once=False, max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=control['upper_bx'] | 0xb22b,
                                value=control['upper_bx'] | 0xb22b)})])['hook']
            wait = debug.breakpoint(control['outer_wait'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(wait['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == control['b']
            status = _status(debug, control['policy_irq'])
            _outstanding(status, [(8, 0x28, 2, 0, 3, 0, 0xb2)])
            assert status['pic-isr'] & 4 and status['slave-isr'] & 1
            assert _private(debug, control['b'], control['observed_data'], 2).hex() == '7856'
            assert _private(debug, control['b'], control['rtc_regc'], 1)[0] & 0xc0 == 0xc0
            registers = debug.registers()['registers']
            flags = registers.get('eflags', registers.get('rflags'))
            assert flags is not None and _number(flags) & 1 == 1
            assert _number(flags) & 0x400 and _number(registers['rbx']) & 0xffff == 0xb22b
            assert _number(registers['rsi']) & 0xffff == 0x2222
            _queue_pair(debug)
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'hook', result
            assert result['hook_hits'][0]['hook'] == hook_b and result['hook_hits'][0]['hit'] == 1
            _nested_before_eoi(debug, control['b'], 0xb2, control)
            point = debug.breakpoint(control['after_slave'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            partial = _partial_outer(debug, control['b'], 0xb2, control)
            assert partial['preemption-count'] == 1
            # B's final outer EOI selects A. A executes its own saved outer
            # IRETD and must reach its exact pre-interrupt V86 PC/SP/flags.
            point = debug.breakpoint(return_pc)
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            registers = debug.registers()
            assert registers['cpu_mode'] == 'v86' and _number(registers['linear_pc']) == return_pc
            assert _number(registers['registers']['rsp']) & 0xffff == saved_frame['pre-sp'] & 0xffff
            flags = registers['registers'].get('eflags', registers['registers'].get('rflags'))
            assert flags is not None and _number(flags) & 0xed5 == saved_flags & 0xed5
            assert debug.dos_task_observe()['task_id'] == control['a']
            status = _status(debug, control['policy_irq'])
            assert status['preemption-count'] == 2 and status['outstanding-count'] == 0
            assert status['last-irq'] == control['policy_irq']
            assert status['last-vector'] == (0x21 if control['policy_irq'] == 1 else 0x28)
            assert status['last-from-cookie'] == 0xb2 and status['last-to-cookie'] == 0xa1
            assert _frames(debug, 0xa1, control['a'], control, [])['interrupt-depth'] == 0
    return {'passed': True, 'pid': os.getpid()}


@pytest.mark.parametrize('policy_irq', [8, 1])
def test_native_rtc_cascade_and_nested_keyboard_cold_restore(tmp_path, policy_irq):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
                                config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = cascade_fixture(tmp_path, runtime['NASM'])
    source = tmp_path / 'CASCADE.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'cascade.fdb'
    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        with _open(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            bound = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('scratch', 'outer_count', 'inner_count', 'key_count', 'key_bytes',
                     'outer_return', 'inner_return', 'observed_data', 'rtc_regc', 'empty_irq_count', 'outer_fetch', 'inner_hook')
            addresses = [base + marker[name] for name in names]
            addresses += [base + marker[name] + 3 for name in ('key_bytes','outer_return','inner_return')]
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addresses.extend((base + marker[name] - 96, base + marker[name] - 1))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert bound['task_id'] == a and a != b
            for task, value, instruction in ((a, '3412', 'f8'), (b, '7856', 'f9')):
                ram = debug.dos_task_layer_patch('cascade-data-' + task[-8:], base + marker['scratch'],
                    expected_hex='0000', data_hex=value, task=task, kind='ram', activate=False)['layer']
                code = debug.dos_task_layer_patch('cascade-code-' + task[-8:], base + marker['outer_fetch'],
                    expected_hex='90', data_hex=instruction, task=task, kind='execute', activate=False)['layer']
                debug.dos_task_layers([ram, code], task=task)
            assert debug.memory(base + marker['scratch'], length=2, space='physical')['hex'] == '0000'
            debug.dos_task_scheduler()
            flags_b = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags_b)
            debug.dos_task_preemption(irq=policy_irq, quantum=1, enabled=True)
            upper_bx = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['inner_hook']), task=a, space='source',
                once=False, max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            wait = debug.breakpoint(base + marker['outer_wait'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(wait['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == a
            status = _status(debug, policy_irq)
            _outstanding(status, [(8, 0x28, 2, 0, 3, 0, 0xa1)])
            assert status['pic-isr'] & 4 and status['slave-isr'] & 1
            assert _private(debug, a, base + marker['observed_data'], 2).hex() == '3412'
            assert _private(debug, a, base + marker['rtc_regc'], 1)[0] & 0xc0 == 0xc0
            values = debug.registers()['registers']
            flags = values.get('eflags', values.get('rflags'))
            assert flags is not None and _number(flags) & 1 == 0
            assert not _number(flags) & 0x400
            assert _number(values['rbx']) & 0xffff == 0xa11a and _number(values['rsi']) & 0xffff == 0x1111
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                policy_irq=policy_irq,
                a=a, b=b, hook_a=hook_a, upper_bx=upper_bx,
                inner_source=hex(static + marker['inner_hook']), b_entry=base + marker['b_entry'],
                outer_wait=base + marker['outer_wait'], after_slave=base + marker['after_slave'],
                after_master=base + marker['after_master'], outer_return=base + marker['outer_return'],
                inner_return=base + marker['inner_return'], observed_data=base + marker['observed_data'],
                rtc_regc=base + marker['rtc_regc'], empty_irq_count=base + marker['empty_irq_count'],
                key_count=base + marker['key_count'], key_bytes=base + marker['key_bytes'])
            _queue_pair(debug)
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'hook', result
            assert result['hook_hits'][0]['hook'] == hook_a and result['hook_hits'][0]['hit'] == 1
            nested = _nested_before_eoi(debug, a, 0xa1, control)
            assert nested['ack-count'] == 2 and nested['eoi-count'] == 0
            nested_context = _frames(debug, 0xa1, a, control, [0x28, 0x21])
            nested_artifact = debug.save_state()['artifact']
            point = debug.breakpoint(base + marker['after_slave'])
            result = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint', result
            debug.delete_breakpoint(point['breakpoint_id'])
            partial = _partial_outer(debug, a, 0xa1, control)
            # A second real IRQ1 can remain latched after both keyboard
            # bytes were drained. The guest records each empty entry and
            # issues its normal EOI without erasing the first-frame evidence.
            empty_irqs = int.from_bytes(_private(debug, a, control['empty_irq_count'], 2), 'little')
            assert partial['ack-count'] == 2 + empty_irqs
            assert partial['eoi-count'] == 1 + empty_irqs
            assert partial['preemption-count'] == 0
            partial_artifact = debug.save_state()['artifact']
            control.update(nested_artifact=nested_artifact, partial_artifact=partial_artifact,
                           nested_status=nested, partial_status=partial,
                           nested_frames=nested_context['frames'])
            old = debug.vm.process
        assert old.poll() is not None
    path = tmp_path / 'cascade-control.json'
    path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
                           capture_output=True, text=True, timeout=360, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[-5000:]
    result = json.loads(child.stdout)
    assert result['passed'] and result['pid'] != os.getpid()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash and digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_child(json.loads(Path(sys.argv[1]).read_text()))))
