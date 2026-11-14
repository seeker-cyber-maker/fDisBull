"""Native-owned cooperative VM86 task contexts and hardware INT61 frames.

The guest supplies entry code and a real protected-mode interrupt gate; the
native scheduler alone chooses the next task, saves CPU contexts and publishes
identity. No guest code copies an interrupt frame or selects a successor.
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
from support.qemu_dos_scheduler_fixture import ANCHOR, MONITOR_UUID, scheduler_fixture
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch
from test_qemu_instrumented_checkpoint_native import _open_instrumented, _pcm


def _number(value):
    return int(value, 16) if isinstance(value, str) else value


def _hit(debug, hook, count, bx, si, carry, direction):
    result = debug.run(timeout_ms=15000, stop_on_hook=True)
    assert result['outcome'] == 'hook', result
    event = result['hook_hits'][0]
    assert event['hook'] == hook and event['hit'] == count
    registers = debug.registers()
    values = registers['registers']
    assert _number(values['rbx']) & 0xffff == bx
    assert _number(values['rsi']) & 0xffff == si
    flags = values.get('eflags', values.get('rflags'))
    assert flags is not None and _number(flags) & 1 == carry
    assert bool(_number(flags) & 0x400) is direction
    assert registers['cpu_mode'] == 'v86'
    return registers


def _ram(debug, task, address):
    return debug.dos_task_memory(address, length=2, task=task, view='ram')['hex']


def _native_context(debug, cookie, incarnation):
    return debug.vm.qmp.call('x-fdisbull-task-context-read',
        {'uuid': MONITOR_UUID, 'cookie': cookie, 'incarnation': incarnation})


def _fpu_view(debug, task, address, expected):
    actual = debug.dos_task_memory(address, length=8, task=task, view='ram')['hex']
    assert actual == expected


def _round_view(debug, task, address, expected):
    actual = debug.dos_task_memory(address, length=2, task=task, view='ram')['hex']
    assert int.from_bytes(bytes.fromhex(actual), 'little') == expected


def _watchpoint(debug, task, count_address, ip_address, expected_count, expected_ip):
    count = int.from_bytes(bytes.fromhex(debug.dos_task_memory(
        count_address, length=4, task=task, view='ram')['hex']), 'little')
    ip = int.from_bytes(bytes.fromhex(debug.dos_task_memory(
        ip_address, length=4, task=task, view='ram')['hex']), 'little')
    assert count == expected_count
    assert ip == expected_ip


def _resume(control):
    runtime = _inputs()
    with Project(control['database']) as project:
        opener = _open_instrumented if control['profile'] == 'instrumented' else _launch
        with opener(project, runtime, control['directory'], {'image': control['disk']}) as debug:
            fresh = debug.vm.process
            restored = debug.load_state(control['artifact'])
            assert fresh.poll() is not None and restored['source_binding_restored']
            a, b = control['a'], control['b']
            assert set(restored['task_views']['tasks']) == {a, b}
            assert debug.dos_task_observe()['task_id'] == a
            if control['profile'] == 'instrumented':
                expected = control['instrumentation']
                clock = debug.clock_observe()
                audio = debug.audio_observe()
                retrace = debug.retrace_observe()
                config = debug.vga_configuration_observe()
                assert clock['virtual_ns'] == expected['virtual_ns']
                assert clock['virtual_clock']['native']['epoch'] != expected['native_epoch']
                assert audio['state'] == 'capturing' and audio['frames'] == expected['frames']
                assert audio['dropped_frames'] == expected['dropped_frames']
                assert restored['instrumentation']['windows']['audio'] == {
                    'old': expected['audio_window'], 'new': audio['window']}
                assert audio['window'] != expected['audio_window']
                assert audio['observed_ns'] == retrace['observed_ns'] == clock['virtual_ns']
                assert retrace['raw'] == expected['retrace_raw']
                assert retrace['phase'] == expected['retrace_phase']
                assert retrace['timing'] == expected['retrace_timing']
                assert config['current']['raw'] == expected['vga_raw']
                if expected['frames']:
                    pcm = _pcm(project, debug.capture_audio('scheduler-restored.wav'))
                    assert len(pcm) == expected['frames']
                    assert hashlib.sha256(pcm).hexdigest() == expected['pcm_sha256']
                # A zero-frame observer verifies token/state continuity only;
                # it is not evidence of audible output or sample playback.
            # B is dormant inside its hardware-created protected interrupt
            # frame; the native context receipt remains available cold.
            context_b = debug.dos_task_context(task=b)
            assert context_b
            native_b = _native_context(debug, 0xb2, 2)
            assert native_b['live'] is False and native_b['interrupt-depth'] == 1
            assert native_b['context-sha256'] == control['dormant_b']['context-sha256']
            assert native_b['frames'] == control['dormant_b']['frames']
            assert native_b['registers'] == control['dormant_b']['registers']
            assert native_b['eip'] == control['dormant_b']['eip']
            if control['profile'] in ('x87', 'instrumented'):
                native_a = _native_context(debug, 0xa1, 1)
                assert native_a['xstate-sha256'] == control['xstate_a']
                assert native_b['xstate-sha256'] == control['xstate_b']
                assert native_a['xstate-sha256'] != native_b['xstate-sha256']
                _fpu_view(debug, a, control['fpu_observed'], '000000000000f03f')
                _round_view(debug, a, control['round_result'], 1)
                _fpu_view(debug, b, control['fpu_observed'], '0000000000000000')
                _round_view(debug, b, control['round_result'], 2)
            assert _ram(debug, a, control['scratch']) == '3612'
            assert _ram(debug, b, control['scratch']) == '7956'
            hooks = {row['hook']: row for row in debug.hooks()['hooks']}
            assert hooks[control['hook_a']]['hits'] == 2
            assert hooks[control['hook_b']]['hits'] == 1
            rb2 = _hit(debug, control['hook_b'], 2, 0xb22b, 0x2222, 1, control['df_b'])
            assert _number(rb2['registers']['rsp']) == control['sp_b']
            if control['profile'] == 'debug-watchpoints':
                _watchpoint(debug, b, control['watch_count'], control['watch_ip'], 2, control['watch_b_ip'])
            if control['profile'] in ('x87', 'instrumented'):
                _fpu_view(debug, b, control['fpu_observed'], '0000000000000000')
                _round_view(debug, b, control['round_result'], 2)
            ra3 = _hit(debug, control['hook_a'], 3, 0xa11a, 0x1111, 0, control['df_a'])
            assert _number(ra3['registers']['rsp']) == control['sp_a']
            if control['profile'] == 'debug-watchpoints':
                _watchpoint(debug, a, control['watch_count'], control['watch_ip'], 3, control['watch_a_ip'])
            if control['profile'] in ('x87', 'instrumented'):
                _fpu_view(debug, a, control['fpu_observed'], '000000000000f03f')
                _round_view(debug, a, control['round_result'], 1)
            rb3 = _hit(debug, control['hook_b'], 3, 0xb22b, 0x2222, 1, control['df_b'])
            assert _number(rb3['registers']['rsp']) == control['sp_b']
            if control['profile'] == 'debug-watchpoints':
                _watchpoint(debug, b, control['watch_count'], control['watch_ip'], 3, control['watch_b_ip'])
            if control['profile'] in ('x87', 'instrumented'):
                _fpu_view(debug, b, control['fpu_observed'], '0000000000000000')
                _round_view(debug, b, control['round_result'], 2)
            assert _ram(debug, a, control['scratch']) == '3712'
            assert _ram(debug, b, control['scratch']) == '7b56'
            idle = debug.run(timeout_ms=15000)
            assert idle['outcome'] == 'scheduler-idle', idle
            if control['profile'] == 'frames':
                last = debug.dos_task_observe()['task_id']
                context = debug.dos_task_context(task=last)
                saved_idle = debug.save_state()
                owner = debug.vm.process
                idle_restore = debug.load_state(saved_idle['artifact'])
                assert owner.poll() is not None
                assert idle_restore['scheduler']['enabled'] is True
                assert not any(row['runnable'] for row in idle_restore['scheduler']['tasks'])
                assert debug.dos_task_context(task=last) == context
            debug.dos_task_scheduler_disable()
            if control['profile'] == 'frames':
                saved_disabled = debug.save_state()
                owner = debug.vm.process
                disabled_restore = debug.load_state(saved_disabled['artifact'])
                assert owner.poll() is not None
                assert disabled_restore['scheduler']['enabled'] is False
                assert len(disabled_restore['scheduler']['tasks']) == 2
            done = debug.run(timeout_ms=15000)
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42
    return {'passed': True, 'pid': os.getpid()}


@pytest.mark.parametrize('profile', ['frames', 'x87', 'instrumented', 'debug-watchpoints'])
def test_native_scheduler_owns_v86_interrupt_frames_and_cold_restore(tmp_path, profile):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk_options = {'config': b'SWITCHES=/F\r\n' + BASELINE_CONFIG} if profile == 'instrumented' else {}
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'], **disk_options)
    data, marker = scheduler_fixture(tmp_path, runtime['NASM'], fpu=profile in ('x87', 'instrumented'),
                                     debug_watchpoints=profile == 'debug-watchpoints')
    source = tmp_path / 'SCHED.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'scheduler.fdb'
    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        opener = _open_instrumented if profile == 'instrumented' else _launch
        with opener(project, runtime, tmp_path, disk) as debug:
            if profile == 'instrumented':
                audio_started = debug.audio_start(max_frames=32000)
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            info = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            scratch = base + marker['scratch']
            fetch = base + marker['fetch']
            # Initial fixture uses identity page tables. Include each stack
            # page so task contexts do not share either hardware return frame.
            fpu_observed = base + marker['fpu_observed']
            round_result = base + marker['round_result']
            fork_flags_address = base + marker['fork_flags']
            addresses = [scratch, fetch, fpu_observed, fpu_observed + 7,
                         round_result, round_result + 1, fork_flags_address, fork_flags_address + 3]
            if profile == 'debug-watchpoints':
                for name, size in (('watch_a', 1), ('watch_b', 1), ('watch_count', 4), ('last_watch_ip', 4)):
                    addresses.extend((base + marker[name], base + marker[name] + size - 1))
            for stack_top in ('b_stack', 'ring0_stack', 'vm_stack'):
                addresses.extend((base + marker[stack_top] - 64, base + marker[stack_top] - 1))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == info['task_id'] and a != b
            for task, initial, replacement in ((a, '3412', 'f8'), (b, '7856', 'f9')):
                ram = debug.dos_task_layer_patch('sched-ram-' + task[-8:], scratch,
                    expected_hex='0000', data_hex=initial, task=task, kind='ram', activate=False)['layer']
                code = debug.dos_task_layer_patch('sched-fetch-' + task[-8:], fetch,
                    expected_hex='90', data_hex=replacement, task=task, kind='execute', activate=False)['layer']
                debug.dos_task_layers([ram, code], task=task)
            debug.dos_task_scheduler()
            before_fork = debug.dos_task_scheduler_observe()
            # These invalid requests must leave the live runqueue unchanged.
            with pytest.raises(ValueError):
                debug.dos_task_fork(task=b, entry=hex(static + len(data) + 1),
                                    stack=base + marker['b_stack'], registers={})
            assert debug.dos_task_scheduler_observe() == before_fork
            with pytest.raises(ValueError):
                debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                    stack=0, registers={})
            assert debug.dos_task_scheduler_observe() == before_fork
            initial_flags = debug.dos_task_context(task=a)['eflags']
            fork_flags = initial_flags ^ (0x001 | 0x040 | 0x400)  # CF, ZF, DF
            forked = debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                stack=base + marker['b_stack'], registers={}, eflags=fork_flags)
            assert forked['context']['eflags'] == fork_flags
            assert debug.dos_task_context(task=b)['eflags'] == fork_flags
            df_a, df_b = bool(initial_flags & 0x400), bool(fork_flags & 0x400)
            assert df_a != df_b
            regs = debug.registers()['registers']
            upper_bx = _number(regs['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['hook']), task=a, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            ra1 = _hit(debug, hook_a, 1, 0xa11a, 0x1111, 0, df_a)
            sp_a = _number(ra1['registers']['rsp'])
            if profile == 'debug-watchpoints':
                _watchpoint(debug, a, base + marker['watch_count'], base + marker['last_watch_ip'],
                            1, 0x100 + marker['after_watch_a'])
            if profile in ('x87', 'instrumented'):
                _fpu_view(debug, a, fpu_observed, '000000000000f03f')
                _round_view(debug, a, round_result, 1)
            if profile == 'frames':
                # Stop before A's native yield inside the real INT61 handler.
                # A single step must switch to B's first instruction, with no
                # B instruction executed and no duplicate pending debug trap.
                point = debug.breakpoint(base + marker['yield_site'])
                stop = debug.run(timeout_ms=15000, stop_on_hook=True)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
                assert debug.registers()['cpu_mode'] == 'protected'
                assert debug.dos_task_observe()['task_id'] == a
                stepped = debug.step(timeout_ms=15000)
                assert stepped['outcome'] in ('step', 'stopped'), stepped
                assert stepped.get('timed_out') is not True
                assert debug.dos_task_observe()['task_id'] == b
                selected = debug.registers()
                assert selected['cpu_mode'] == 'v86'
                assert _number(selected['linear_pc']) == base + marker['b_entry']
                native_b_initial = _native_context(debug, 0xb2, 2)
                assert native_b_initial['registers'] == forked['context']['registers']
                assert native_b_initial['eflags'] == forked['context']['eflags']
                assert native_b_initial['eip'] == forked['context']['eip']
            else:
                point = debug.breakpoint(base + marker['b_entry'])
                stop = debug.run(timeout_ms=15000, stop_on_hook=True)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
                assert debug.dos_task_observe()['task_id'] == b
            hook_b = debug.hook(hex(static + marker['hook']), task=b, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xb22b, value=upper_bx | 0xb22b)})])['hook']
            rb1 = _hit(debug, hook_b, 1, 0xb22b, 0x2222, 1, df_b)
            sp_b = _number(rb1['registers']['rsp'])
            if profile == 'debug-watchpoints':
                _watchpoint(debug, b, base + marker['watch_count'], base + marker['last_watch_ip'],
                            1, 0x100 + marker['b_after_watch_b'])
            observed_flags = int.from_bytes(bytes.fromhex(debug.dos_task_memory(
                fork_flags_address, length=4, task=b, view='ram')['hex']), 'little')
            assert observed_flags & 0x441 == fork_flags & 0x441
            if profile in ('x87', 'instrumented'):
                _fpu_view(debug, a, fpu_observed, '000000000000f03f')
                _round_view(debug, a, round_result, 1)
                _fpu_view(debug, b, fpu_observed, '0000000000000000')
                _round_view(debug, b, round_result, 2)
            assert sp_a != sp_b and ra1['linear_pc'] == rb1['linear_pc']
            ra2 = _hit(debug, hook_a, 2, 0xa11a, 0x1111, 0, df_a)
            assert _number(ra2['registers']['rsp']) == sp_a
            if profile == 'debug-watchpoints':
                _watchpoint(debug, a, base + marker['watch_count'], base + marker['last_watch_ip'],
                            2, 0x100 + marker['after_watch_a'])
            if profile in ('x87', 'instrumented'):
                _fpu_view(debug, a, fpu_observed, '000000000000f03f')
                _round_view(debug, a, round_result, 1)
                _fpu_view(debug, b, fpu_observed, '0000000000000000')
                _round_view(debug, b, round_result, 2)
            assert _ram(debug, a, scratch) == '3612' and _ram(debug, b, scratch) == '7956'
            dormant_b = debug.dos_task_context(task=b)
            assert dormant_b
            native_b = _native_context(debug, 0xb2, 2)
            assert native_b['live'] is False and native_b['interrupt-depth'] == 1
            assert len(native_b['frames']) == 1
            frame = native_b['frames'][0]
            assert frame['vector'] == 0x61 and frame['pre-eip'] == 0x100 + marker['after_b']
            assert native_b['registers'][3] & 0xffff == 0xb22b
            assert native_b['registers'][6] & 0xffff == 0x2222
            native_a = _native_context(debug, 0xa1, 1)
            if profile in ('x87', 'instrumented'):
                assert native_a['xstate-sha256'] != native_b['xstate-sha256']
            instrumentation = None
            if profile == 'instrumented':
                clock = debug.clock_observe()
                audio = debug.audio_observe()
                retrace = debug.retrace_observe()
                config = debug.vga_configuration_observe()
                assert audio['state'] == 'capturing' and audio['window'] == audio_started['window']
                assert audio['dropped_frames'] == 0
                assert audio['observed_ns'] == retrace['observed_ns'] == clock['virtual_ns']
                pcm = _pcm(project, debug.capture_audio('scheduler-before.wav')) if audio['frames'] else b''
                assert len(pcm) == audio['frames']
                instrumentation = dict(virtual_ns=clock['virtual_ns'],
                    native_epoch=clock['virtual_clock']['native']['epoch'],
                    audio_window=audio['window'], frames=audio['frames'],
                    dropped_frames=audio['dropped_frames'],
                    pcm_sha256=hashlib.sha256(pcm).hexdigest() if audio['frames'] else None,
                    retrace_raw=retrace['raw'], retrace_phase=retrace['phase'],
                    retrace_timing=retrace['timing'], vga_raw=config['current']['raw'])
            saved = debug.save_state()
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                artifact=saved['artifact'], a=a, b=b, scratch=scratch, hook_a=hook_a,
                hook_b=hook_b, sp_a=sp_a, sp_b=sp_b, dormant_b=native_b,
                profile=profile, instrumentation=instrumentation, fpu_observed=fpu_observed,
                round_result=round_result,
                df_a=df_a, df_b=df_b,
                watch_count=base + marker['watch_count'], watch_ip=base + marker['last_watch_ip'],
                watch_a_ip=0x100 + marker['after_watch_a'], watch_b_ip=0x100 + marker['b_after_watch_b'],
                xstate_a=native_a['xstate-sha256'], xstate_b=native_b['xstate-sha256'])
            old = debug.vm.process
        assert old.poll() is not None
    control_path = tmp_path / 'scheduler-restore.json'
    control_path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                           capture_output=True, text=True, timeout=180, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[:5000] + child.stderr[-1000:]
    child_result = json.loads(child.stdout)
    assert child_result['passed'] is True and child_result['pid'] != os.getpid()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash and digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_resume(json.loads(Path(sys.argv[1]).read_text()))))
