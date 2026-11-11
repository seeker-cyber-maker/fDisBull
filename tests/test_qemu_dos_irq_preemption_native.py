"""Real PIT/PIC IRQ0 preemption with dormant hardware frames and cold restore.

The guest ISR sends its real PIC EOI and returns with IRETD. It never yields,
selects another task, writes a switching doorbell or copies an interrupt frame.
The caller must supply the explicitly enabled patched native QEMU and FreeDOS.
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
from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch
from test_qemu_instrumented_checkpoint_native import _open_instrumented, _pcm


def _number(value):
    return int(value, 16) if isinstance(value, str) else value


def _open(project, runtime, directory, disk, profile):
    if profile == 'instrumented':
        return _open_instrumented(project, runtime, directory, disk)
    return _launch(project, runtime, directory, disk,
                   clock_profile='virtual' if profile == 'virtual-x87' else None)


def _instrumented_snapshot(project, debug, label):
    clock = debug.clock_observe()
    audio = debug.audio_observe()
    retrace = debug.retrace_observe()
    config = debug.vga_configuration_observe()
    assert audio['state'] == 'capturing' and audio['dropped_frames'] == 0
    assert audio['observed_ns'] == retrace['observed_ns'] == clock['virtual_ns']
    pcm = _pcm(project, debug.capture_audio(label + '.wav')) if audio['frames'] else b''
    assert len(pcm) == audio['frames']
    return dict(virtual_ns=clock['virtual_ns'],
        native_epoch=clock['virtual_clock']['native']['epoch'],
        audio_window=audio['window'], frames=audio['frames'],
        dropped_frames=audio['dropped_frames'],
        pcm_sha256=hashlib.sha256(pcm).hexdigest() if audio['frames'] else None,
        retrace_raw=retrace['raw'], retrace_phase=retrace['phase'],
        retrace_timing=retrace['timing'], vga_raw=config['current']['raw'])


def _assert_instrumented_restore(project, debug, result, saved, label):
    current = _instrumented_snapshot(project, debug, label)
    assert current['virtual_ns'] == saved['virtual_ns']
    assert current['native_epoch'] != saved['native_epoch']
    assert result['instrumentation']['windows']['audio'] == {
        'old': saved['audio_window'], 'new': current['audio_window']}
    assert current['audio_window'] != saved['audio_window']
    for field in ('frames', 'dropped_frames', 'pcm_sha256', 'retrace_raw',
                  'retrace_phase', 'retrace_timing', 'vga_raw'):
        assert current[field] == saved[field]
    # A zero-frame window proves observer/token continuity only. Even when
    # samples exist, this comparison is not an audible playback assertion.


def _private(debug, task, address, length):
    return bytes.fromhex(debug.dos_task_memory(address, length=length, task=task, view='ram')['hex'])


def _preemption(debug):
    native = debug.dos_task_scheduler_observe()
    value = native['preemption']
    assert native['api-version'] in (2, 3)
    assert value['model'] == ('qemu-pc-pic-preemption-v2' if native['api-version'] == 3
                               else 'qemu-pc-pic-preemption-v1')
    assert value['enabled'] is True and value['irq'] == 0 and value['quantum'] == 1
    assert value['quantum-progress'] < value['quantum']
    assert value['pic-irq-base'] == 0x20 and value['pic-mask'] & 1 == 0
    return value


def _native_context(debug, cookie, incarnation):
    return debug.vm.qmp.call('x-fdisbull-task-context-read',
                             {'uuid': MONITOR_UUID, 'cookie': cookie, 'incarnation': incarnation})


def _irq_frame(debug, task, cookie, count_address, ip_address, *, live, count):
    context = _native_context(debug, cookie, 1 if cookie == 0xa1 else 2)
    assert context['live'] is live and context['interrupt-depth'] == 1
    frame = context['frames'][0]
    assert frame['vector'] == 0x20 and frame['kind'] == 'hardware'
    assert int.from_bytes(_private(debug, task, count_address, 2), 'little') == count
    assert int.from_bytes(_private(debug, task, ip_address, 4), 'little') == frame['pre-eip']
    return context


def _hit(debug, hook, count, bx, si, carry, direction):
    result = debug.run(timeout_ms=45000, stop_on_hook=True)
    assert result['outcome'] == 'hook', result
    event = result['hook_hits'][0]
    assert event['hook'] == hook and event['hit'] == count
    registers = debug.registers()
    assert registers['cpu_mode'] == 'protected'
    values = registers['registers']
    assert _number(values['rbx']) & 0xffff == bx
    assert _number(values['rsi']) & 0xffff == si
    flags = values.get('eflags', values.get('rflags'))
    assert flags is not None and _number(flags) & 1 == carry
    assert bool(_number(flags) & 0x400) is direction
    return registers


def _last_transition(status, from_cookie, to_cookie):
    assert status['last-valid'] is True
    assert status['last-irq'] == 0 and status['last-vector'] == 0x20
    assert status['last-from-cookie'] == from_cookie and status['last-to-cookie'] == to_cookie
    assert status['last-from-uuid'] == status['last-to-uuid'] == MONITOR_UUID


def _child(control):
    runtime = _inputs()
    disk = {'image': control['disk']}
    with Project(control['database']) as project:
        # First restore stops in A's actual IRQ0 handler before PIC EOI. Its
        # in-service PIC bit and frame must survive before we allow any run.
        with _open(project, runtime, control['directory'], disk, control['profile']) as debug:
            fresh = debug.vm.process
            result = debug.load_state(control['before_eoi_artifact'])
            assert fresh.poll() is not None and result['source_binding_restored']
            if control['profile'] == 'instrumented':
                _assert_instrumented_restore(project, debug, result, control['before_eoi_instrumentation'],
                                             'irq-before-restored')
            assert debug.dos_task_observe()['task_id'] == control['a']
            assert _preemption(debug) == control['before_eoi_status']
            frame = _irq_frame(debug, control['a'], 0xa1, control['irq_count'],
                               control['return_ip'], live=True, count=1)
            assert frame['frames'] == control['before_eoi_frame']
            assert _private(debug, control['a'], control['irq_data'], 2).hex() == '3412'
            point = debug.breakpoint(control['b_entry'])
            stop = debug.run(timeout_ms=45000, stop_on_hook=True)
            assert stop['outcome'] == 'breakpoint', stop
            debug.delete_breakpoint(point['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == control['b']
            status = _preemption(debug)
            assert status['eoi-count'] >= 1 and status['preemption-count'] >= 1
            assert status['pic-isr'] & 1 == 0
            _last_transition(status, 0xa1, 0xb2)
            dormant = _irq_frame(debug, control['a'], 0xa1, control['irq_count'],
                                 control['return_ip'], live=False, count=1)
            assert dormant['eip'] == control['after_eoi']

        # The second independent restore begins just after A's EOI selected B;
        # A is dormant inside its original hardware IRQ frame and both task
        # hooks have been registered before the checkpoint.
        with _open(project, runtime, control['directory'], disk, control['profile']) as debug:
            fresh = debug.vm.process
            result = debug.load_state(control['after_eoi_artifact'])
            assert fresh.poll() is not None and result['source_binding_restored']
            if control['profile'] == 'instrumented':
                _assert_instrumented_restore(project, debug, result, control['after_eoi_instrumentation'],
                                             'irq-after-restored')
            assert debug.dos_task_observe()['task_id'] == control['b']
            assert _preemption(debug) == control['after_eoi_status']
            dormant = _irq_frame(debug, control['a'], 0xa1, control['irq_count'],
                                 control['return_ip'], live=False, count=1)
            assert dormant['eip'] == control['after_eoi']
            assert dormant['frames'] == control['after_eoi_frame']
            saved_frame = dormant['frames'][0]
            assert saved_frame['width'] == 32 and not saved_frame['error-code-present']
            frame_address = saved_frame['frame-ss-base'] + saved_frame['frame-sp']
            saved_flags = int.from_bytes(_private(debug, control['a'], frame_address + 8, 4), 'little')
            return_pc = (saved_frame['pre-cs'] << 4) + saved_frame['pre-eip']
            hooks = {row['hook']: row for row in debug.hooks()['hooks']}
            assert hooks[control['hook_a']]['hits'] == 1
            assert hooks[control['hook_b']]['hits'] == 0
            loop_counts = {control['a']: control['initial_a_loop']}
            for task, hook, count, bx, si, carry, direction, cookie in (
                (control['b'], control['hook_b'], 1, 0xb22b, 0x2222, 1, True, 0xb2),
                (control['a'], control['hook_a'], 2, 0xa11a, 0x1111, 0, False, 0xa1),
                (control['b'], control['hook_b'], 2, 0xb22b, 0x2222, 1, True, 0xb2),
                (control['a'], control['hook_a'], 3, 0xa11a, 0x1111, 0, False, 0xa1),
                (control['b'], control['hook_b'], 3, 0xb22b, 0x2222, 1, True, 0xb2),
            ):
                _hit(debug, hook, count, bx, si, carry, direction)
                assert debug.dos_task_observe()['task_id'] == task
                _irq_frame(debug, task, cookie, control['irq_count'], control['return_ip'],
                           live=True, count=count)
                assert _private(debug, task, control['irq_data'], 2).hex() == ('3412' if cookie == 0xa1 else '7856')
                loop_now = int.from_bytes(_private(debug, task, control['loop_count'], 4), 'little')
                if task in loop_counts:
                    assert loop_now != loop_counts[task], 'Task loop did not progress between IRQs'
                loop_counts[task] = loop_now
                status = _preemption(debug)
                assert status['inflight'] is True and status['pic-isr'] & 1
                if control['profile'] in ('virtual-x87', 'instrumented'):
                    want = '000000000000f03f' if cookie == 0xa1 else '0000000000000000'
                    assert _private(debug, task, control['fp_result'], 8).hex() == want
                if cookie == 0xb2 and count == 1:
                    # B's real EOI selects A, whose original IRQ frame must
                    # IRETD to its saved V86 PC/SP/flags before A runs on.
                    point = debug.breakpoint(return_pc)
                    resumed = debug.run(timeout_ms=45000, stop_on_hook=True)
                    assert resumed['outcome'] == 'breakpoint', resumed
                    debug.delete_breakpoint(point['breakpoint_id'])
                    registers = debug.registers()
                    assert registers['cpu_mode'] == 'v86'
                    assert _number(registers['linear_pc']) == return_pc
                    assert _number(registers['registers']['rsp']) & 0xffff == saved_frame['pre-sp'] & 0xffff
                    actual_flags = registers['registers'].get('eflags', registers['registers'].get('rflags'))
                    assert actual_flags is not None
                    assert _number(actual_flags) & 0xed5 == saved_flags & 0xed5
                    assert debug.dos_task_observe()['task_id'] == control['a']
            status = _preemption(debug)
            assert status['preemption-count'] >= 5 and status['ack-count'] >= 6
            idle = debug.run(timeout_ms=45000)
            assert idle['outcome'] == 'scheduler-idle', idle
            assert _preemption(debug)['inflight'] is False
            for hook in list(debug.hooks()['hooks']):
                debug.delete_hook(hook['hook'])
            debug.dos_task_preemption(enabled=False)
            debug.dos_task_scheduler_disable()
            done = debug.run(timeout_ms=45000)
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42
    return {'passed': True, 'pid': os.getpid()}


@pytest.mark.parametrize('profile', ['standard', 'virtual-x87', 'instrumented'])
def test_native_real_irq0_preemption_cold_frame_and_pic_restore(tmp_path, profile):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    opts = {'config': b'SWITCHES=/F\r\n' + BASELINE_CONFIG} if profile in ('virtual-x87', 'instrumented') else {}
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'], **opts)
    data, marker = irq_fixture(tmp_path, runtime['NASM'], fpu=profile in ('virtual-x87', 'instrumented'))
    source = tmp_path / 'IRQ.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'irq.fdb'
    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        with _open(project, runtime, tmp_path, disk, profile) as debug:
            if profile == 'instrumented':
                audio_started = debug.audio_start(max_frames=32000)
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('scratch', 'irq_count', 'return_ip', 'carry', 'irq_data', 'irq_fetch', 'fp_result', 'loop_count')
            addresses = [base + marker[name] for name in names]
            for name in ('b_stack', 'ring0_stack', 'vm_stack'):
                addresses.extend((base + marker[name] - 64, base + marker[name] - 1))
            addresses.extend((base + marker['return_ip'] + 3, base + marker['loop_count'] + 3, base + marker['fp_result'] + 7))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            fetch = base + marker['irq_fetch']
            for task, replacement, data_hex in ((a, 'f8', '3412'), (b, 'f9', '7856')):
                data_layer = debug.dos_task_layer_patch('irq-data-' + task[-8:], base + marker['scratch'],
                    expected_hex='0000', data_hex=data_hex, task=task, kind='ram', activate=False)['layer']
                code = debug.dos_task_layer_patch('irq-fetch-' + task[-8:], fetch,
                    expected_hex='90', data_hex=replacement, task=task, kind='execute', activate=False)['layer']
                debug.dos_task_layers([data_layer, code], task=task)
            assert debug.memory(base + marker['scratch'], length=2, space='physical')['hex'] == '0000'
            debug.dos_task_scheduler()
            # B enables IF only after initializing its private CPU/x87 state.
            flags = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags)
            debug.dos_task_preemption(irq=0, quantum=1, enabled=True)
            upper_bx = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['irq_hook']), task=a, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            _hit(debug, hook_a, 1, 0xa11a, 0x1111, 0, False)
            pre = _preemption(debug)
            assert pre['inflight'] and pre['inflight-irq'] == 0 and pre['inflight-vector'] == 0x20
            assert pre['inflight-cookie'] == 0xa1 and pre['pic-isr'] & 1
            assert pre['ack-count'] >= 1 and pre['eoi-count'] == 0 and pre['preemption-count'] == 0
            assert _private(debug, a, base + marker['irq_data'], 2).hex() == '3412'
            frame = _irq_frame(debug, a, 0xa1, base + marker['irq_count'],
                               base + marker['return_ip'], live=True, count=1)
            before_eoi_instrumentation = None
            if profile == 'instrumented':
                before_eoi_instrumentation = _instrumented_snapshot(project, debug, 'irq-before-eoi')
                assert before_eoi_instrumentation['audio_window'] == audio_started['window']
            before_eoi = debug.save_state()['artifact']
            if profile == 'standard':
                # Stop immediately before the authored PIC EOI. One GDB step
                # must execute EOI and the native switch as one boundary.
                assert data[marker['after_eoi'] - 2:marker['after_eoi']] == b'\xe6\x20'
                eoi_pc = base + marker['after_eoi'] - 2
                point = debug.breakpoint(eoi_pc)
                stop = debug.run(timeout_ms=45000, stop_on_hook=True)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
                assert _number(debug.registers()['linear_pc']) == eoi_pc
                assert debug.dos_task_observe()['task_id'] == a
                stepped = debug.step(timeout_ms=45000)
                assert stepped['outcome'] in ('step', 'stopped'), stepped
                assert stepped.get('timed_out') is not True
                assert debug.dos_task_observe()['task_id'] == b
                selected = debug.registers()
                assert selected['cpu_mode'] == 'v86'
                assert _number(selected['linear_pc']) == base + marker['b_entry']
            else:
                point = debug.breakpoint(base + marker['b_entry'])
                stop = debug.run(timeout_ms=45000, stop_on_hook=True)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
                assert debug.dos_task_observe()['task_id'] == b
            post = _preemption(debug)
            assert post['preemption-count'] >= 1 and post['eoi-count'] >= 1
            if profile == 'standard':
                assert post['preemption-count'] == 1 and post['eoi-count'] == 1
            assert post['pic-isr'] & 1 == 0 and post['inflight'] is False
            _last_transition(post, 0xa1, 0xb2)
            dormant = _irq_frame(debug, a, 0xa1, base + marker['irq_count'],
                                 base + marker['return_ip'], live=False, count=1)
            assert dormant['eip'] == base + marker['after_eoi']
            hook_b = debug.hook(hex(static + marker['irq_hook']), task=b, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xb22b, value=upper_bx | 0xb22b)})])['hook']
            after_eoi_instrumentation = None
            if profile == 'instrumented':
                after_eoi_instrumentation = _instrumented_snapshot(project, debug, 'irq-after-eoi')
                assert after_eoi_instrumentation['audio_window'] == audio_started['window']
            after_eoi = debug.save_state()['artifact']
            if profile == 'standard':
                # No guest instruction runs between the stepped EOI and this
                # continuation. B1 must be the next stop, not a phantom DEBUG.
                _hit(debug, hook_b, 1, 0xb22b, 0x2222, 1, True)
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']), profile=profile,
                a=a, b=b, hook_a=hook_a, hook_b=hook_b, before_eoi_artifact=before_eoi,
                after_eoi_artifact=after_eoi, before_eoi_status=pre, after_eoi_status=post,
                before_eoi_instrumentation=before_eoi_instrumentation,
                after_eoi_instrumentation=after_eoi_instrumentation,
                before_eoi_frame=frame['frames'], after_eoi_frame=dormant['frames'],
                b_entry=base + marker['b_entry'], after_eoi=base + marker['after_eoi'],
                irq_count=base + marker['irq_count'], return_ip=base + marker['return_ip'],
                irq_data=base + marker['irq_data'], loop_count=base + marker['loop_count'],
                initial_a_loop=int.from_bytes(_private(debug, a, base + marker['loop_count'], 4), 'little'),
                fp_result=base + marker['fp_result'])
            old = debug.vm.process
        assert old.poll() is not None
    path = tmp_path / 'irq-cold-control.json'
    path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
                           capture_output=True, text=True, timeout=360, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[-5000:]
    result = json.loads(child.stdout)
    assert result['passed'] and result['pid'] != os.getpid()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash and digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_child(json.loads(Path(sys.argv[1]).read_text()))))
