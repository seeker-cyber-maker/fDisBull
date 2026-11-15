"""Task-private periodic rules with real IRQ preemption and cold checkpoints.

Uses authored FreeDOS COM and native IRQ0/task fixtures; no vendor media.
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
from test_qemu_dos_irq_preemption_native import _hit, _irq_frame, _last_transition, _number, _preemption


def _view(debug, task, address, *, view='ram', length=2):
    return debug.dos_task_memory(address, length=length, task=task, view=view)['hex']


def _rule(project, debug, task, address, value):
    # This rule intentionally survives real/V86/protected task transitions;
    # its domain is the registered physical private page, not a linear map.
    snap = debug.memory_snapshot(address, length=2, space='physical',
                                 task_id=task, view='ram')['artifact']
    search = project.memory_search_start(snap, width=2, stride=2, mode='unknown')['artifact']
    return project.memory_rule_create(search, offset=0, value=value,
        max_applications=10, max_ticks=10)['artifact']


def _views(debug, c):
    return dict(a=_view(debug, c['a'], c['scratch']),
        b=_view(debug, c['b'], c['scratch']),
        code_a=_view(debug, c['a'], c['fetch'], view='execute', length=1),
        code_b=_view(debug, c['b'], c['fetch'], view='execute', length=1),
        base=debug.memory(c['scratch'], length=2, space='physical')['hex'],
        base_code=debug.memory(c['fetch'], length=1, space='physical')['hex'])


def _stale_child(c):
    runtime = _inputs()
    with Project(c['database']) as project:
        with _launch(project, runtime, c['directory'], {'image': c['disk']}, clock_profile='virtual') as debug:
            fresh_vm = debug.vm.process
            restored = debug.load_state(c['checkpoint'])
            assert fresh_vm.poll() is not None and restored['source_binding_restored']
            assert debug.dos_task_observe()['task_id'] == c['a']
            assert _preemption(debug) == c['preemption']
            frame = _irq_frame(debug, c['a'], 0xa1, c['irq_count'], c['return_ip'], live=True, count=2)
            assert frame['frames'] == c['frame']
            hooks = {row['hook']: row['hits'] for row in debug.hooks()['hooks']}
            assert hooks[c['hook_a']] == 2 and hooks[c['hook_b']] == 1
            before_views = _views(debug, c)
            assert before_views == c['views']
            before_progress = project.memory_rule_info(c['rule'])
            before_regs = debug.registers()['registers']
            with pytest.raises(ValueError, match='run|epoch|stale|context'):
                debug.memory_rule_run(c['rule'], ticks=1, interval_ms=10, timeout_ms=15000)
            assert project.memory_rule_info(c['rule']) == before_progress
            assert debug.registers()['registers'] == before_regs
            assert _views(debug, c) == before_views
            assert {row['hook']: row['hits'] for row in debug.hooks()['hooks']} == hooks
            new_rule = _rule(project, debug, c['a'], c['scratch'], 0x4321)
            result = debug.memory_rule_run(new_rule, ticks=1, interval_ms=10, timeout_ms=15000)
            assert result['complete'] and result['completed_ticks'] == 1
            assert project.memory_rule_info(new_rule)['progress']['applications'] == 1
            after = _views(debug, c)
            assert after == dict(before_views, a='2143')
    return {'passed': True}


def test_private_rule_irq_hooks_and_cold_restore(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path, runtime['NASM'], fpu=True, mutate_scratch=True)
    source = tmp_path / 'IRQ.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'private-rule.fdb'
    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk, clock_profile='virtual') as debug:
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
            addresses.extend((base + marker['return_ip'] + 3, base + marker['loop_count'] + 3,
                              base + marker['fp_result'] + 7))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1, incarnation=1, pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2, incarnation=2, pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            scratch, fetch = base + marker['scratch'], base + marker['irq_fetch']
            for task, fetch_byte, data_hex in ((a, 'f8', '3412'), (b, 'f9', '7856')):
                ram = debug.dos_task_layer_patch('rule-test-ram-' + task[-8:], scratch,
                    expected_hex='0000', data_hex=data_hex, task=task, kind='ram', activate=False)['layer']
                code = debug.dos_task_layer_patch('rule-test-code-' + task[-8:], fetch,
                    expected_hex='90', data_hex=fetch_byte, task=task, kind='execute', activate=False)['layer']
                debug.dos_task_layers([ram, code], task=task)
            debug.dos_task_scheduler()
            flags = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags)
            debug.dos_task_preemption(irq=0, quantum=1, enabled=True)
            c = dict(a=a, b=b, scratch=scratch, fetch=fetch)
            assert _views(debug, c) == dict(a='3412', b='7856', code_a='f8', code_b='f9',
                                           base='0000', base_code='90')
            upper_bx = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['irq_hook']), task=a, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            rule = _rule(project, debug, a, scratch, 0x1235)
            result = debug.memory_rule_run(rule, ticks=2, interval_ms=100, timeout_ms=45000)
            assert result['outcome'] == 'clock_interrupted' and result['completed_ticks'] == 1
            stop = result['clock_stop']
            assert stop['outcome'] == 'hook' and stop['hook_hits'][0]['hook'] == hook_a
            assert stop['hook_hits'][0]['hit'] == 1 and stop['clock_budget']['token']
            assert project.memory_rule_info(rule)['progress']['applications'] == 1
            changed_a = _view(debug, a, scratch)
            assert changed_a != '3512'  # actual guest writes after the first rule tick
            assert _views(debug, c) == dict(a=changed_a, b='7856', code_a='f8', code_b='f9',
                                           base='0000', base_code='90')
            assert _view(debug, a, base + marker['irq_data']) == changed_a
            pre = _preemption(debug)
            assert pre['inflight'] and pre['inflight-cookie'] == 0xa1 and pre['pic-isr'] & 1
            _irq_frame(debug, a, 0xa1, base + marker['irq_count'], base + marker['return_ip'], live=True, count=1)
            point = debug.breakpoint(base + marker['b_entry'])
            assert debug.run(timeout_ms=45000, stop_on_hook=True)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            assert debug.dos_task_observe()['task_id'] == b
            _last_transition(_preemption(debug), 0xa1, 0xb2)
            before_views = _views(debug, c)
            before_progress = project.memory_rule_info(rule)
            before_regs = debug.registers()['registers']
            with pytest.raises(ValueError, match='task|selected|identity'):
                debug.memory_rule_run(rule, ticks=1, interval_ms=10, timeout_ms=15000)
            assert project.memory_rule_info(rule) == before_progress
            assert debug.registers()['registers'] == before_regs and _views(debug, c) == before_views
            hook_b = debug.hook(hex(static + marker['irq_hook']), task=b, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xb22b, value=upper_bx | 0xb22b)})])['hook']
            _hit(debug, hook_b, 1, 0xb22b, 0x2222, 1, True)
            _hit(debug, hook_a, 2, 0xa11a, 0x1111, 0, False)
            assert debug.dos_task_observe()['task_id'] == a
            resumed = debug.memory_rule_run(rule, ticks=1, interval_ms=10, timeout_ms=15000)
            assert resumed['complete'] and resumed['completed_ticks'] == 1
            progress = project.memory_rule_info(rule)['progress']
            assert (progress['ticks'], progress['applications']) == (2, 2)
            assert _view(debug, a, scratch) == '3512'
            frame = _irq_frame(debug, a, 0xa1, base + marker['irq_count'], base + marker['return_ip'], live=True, count=2)
            c.update(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                rule=rule, hook_a=hook_a, hook_b=hook_b, irq_count=base + marker['irq_count'],
                return_ip=base + marker['return_ip'], preemption=_preemption(debug), frame=frame['frames'],
                views=_views(debug, c), checkpoint=debug.save_state()['artifact'])
            assert c['preemption']['inflight'] and c['preemption']['pic-isr'] & 1
            old_vm = debug.vm.process
        assert old_vm.poll() is not None
    control = tmp_path / 'private-rule-control.json'
    control.write_text(json.dumps(c))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control)],
        capture_output=True, text=True, timeout=180, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout)['passed'] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_stale_child(json.loads(Path(sys.argv[1]).read_text()))))
