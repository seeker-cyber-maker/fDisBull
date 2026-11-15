"""Bounded native checkpoint history across real IRQ task switches.

The authored FreeDOS fixture uses a real PIT/PIC IRQ and a native scheduler;
no vendor image, software yield, or host-selected task stands in for an IRQ.
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
from test_qemu_dos_irq_preemption_native import _hit, _irq_frame, _number, _preemption


def _task_bytes(debug, task, address, length, view='ram'):
    return debug.dos_task_memory(address, length=length, task=task, view=view)['hex']


def _state(debug, control, *, task, cookie, count):
    frame = _irq_frame(debug, task, cookie, control['irq_count'], control['return_ip'],
                       live=True, count=count)
    status = _preemption(debug)
    assert status['inflight'] and status['inflight-cookie'] == cookie and status['pic-isr'] & 1
    assert debug.dos_task_observe()['task_id'] == task
    a, b, scratch, fetch = (control[k] for k in ('a', 'b', 'scratch', 'fetch'))
    return dict(registers=debug.registers()['registers'],
        pc=debug.registers()['linear_pc'], clock_ns=debug.clock_observe()['virtual_ns'],
        preemption=status, frame=frame['frames'],
        hooks={h['hook']: h['hits'] for h in debug.hooks()['hooks']},
        ram_a=_task_bytes(debug, a, scratch, 2), ram_b=_task_bytes(debug, b, scratch, 2),
        code_a=_task_bytes(debug, a, fetch, 1, 'execute'),
        code_b=_task_bytes(debug, b, fetch, 1, 'execute'),
        base_ram=debug.memory(scratch, length=2, space='physical')['hex'],
        base_code=debug.memory(fetch, length=1, space='physical')['hex'])


def _assert_state(debug, control, expected, *, task, cookie, count):
    actual = _state(debug, control, task=task, cookie=cookie, count=count)
    assert actual == expected
    assert (actual['ram_a'], actual['ram_b'], actual['code_a'], actual['code_b'],
            actual['base_ram'], actual['base_code']) == ('3412', '7856', 'f8', 'f9', '0000', '90')


def _cold_child(control):
    runtime = _inputs()
    with Project(control['database']) as project:
        with _launch(project, runtime, control['directory'], {'image': control['disk']}, clock_profile='virtual') as debug:
            fresh_process = debug.vm.process
            before_epoch = debug.dos_process_info()['capture_epoch']
            restored = debug.rewind(history=control['history'], node=control['h0'], timeout_ms=60000)
            assert fresh_process.poll() is not None
            assert debug.dos_process_info()['capture_epoch'] != before_epoch
            _assert_state(debug, control, control['state_h0'], task=control['a'], cookie=0xa1, count=2)
            _hit(debug, control['hook_b'], 2, 0xb22b, 0x2222, 1, True)
            assert debug.dos_task_observe()['task_id'] == control['b']
            assert _preemption(debug)['preemption-count'] > control['state_h0']['preemption']['preemption-count']
    return {'passed': True}


def test_native_irq_checkpoint_history_rewinds_branches_and_cold_restores(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path, runtime['NASM'], fpu=True)
    source = tmp_path / 'IRQ.COM'
    source.write_bytes(data)
    source_hash = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'history.fdb'
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
            for task, ram_hex, code_hex in ((a, '3412', 'f8'), (b, '7856', 'f9')):
                ram = debug.dos_task_layer_patch('history-ram-' + task[-8:], scratch,
                    expected_hex='0000', data_hex=ram_hex, kind='ram', task=task, activate=False)['layer']
                code = debug.dos_task_layer_patch('history-fetch-' + task[-8:], fetch,
                    expected_hex='90', data_hex=code_hex, kind='execute', task=task, activate=False)['layer']
                debug.dos_task_layers([ram, code], task=task)
            debug.dos_task_scheduler()
            flags = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b, entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'], eflags=flags)
            debug.dos_task_preemption(irq=0, quantum=1, enabled=True)
            upper_bx = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['irq_hook']), task=a, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xa11a, value=upper_bx | 0xa11a)})])['hook']
            _hit(debug, hook_a, 1, 0xa11a, 0x1111, 0, False)
            point = debug.breakpoint(base + marker['b_entry'])
            assert debug.run(timeout_ms=45000, stop_on_hook=True)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            hook_b = debug.hook(hex(static + marker['irq_hook']), task=b, space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={
                    'rbx': dict(expected=upper_bx | 0xb22b, value=upper_bx | 0xb22b)})])['hook']
            _hit(debug, hook_b, 1, 0xb22b, 0x2222, 1, True)
            _hit(debug, hook_a, 2, 0xa11a, 0x1111, 0, False)
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                a=a, b=b, hook_a=hook_a, hook_b=hook_b, scratch=scratch, fetch=fetch,
                irq_count=base + marker['irq_count'], return_ip=base + marker['return_ip'])
            h0_state = _state(debug, control, task=a, cookie=0xa1, count=2)
            started = debug.rewind_start(max_steps=16, max_bytes=512*1024*1024, timeout_ms=60000)
            h0 = started['cursor']
            _hit(debug, hook_b, 2, 0xb22b, 0x2222, 1, True)
            h1_state = _state(debug, control, task=b, cookie=0xb2, count=2)
            h1 = debug.rewind_record(advance='capture', count=1, timeout_ms=60000)['cursor']
            _hit(debug, hook_a, 3, 0xa11a, 0x1111, 0, False)
            h2 = debug.rewind_record(advance='capture', count=1, timeout_ms=60000)['cursor']
            old = debug.vm.process
            debug.rewind(count=2, timeout_ms=60000)
            assert old.poll() is not None
            _assert_state(debug, control, h0_state, task=a, cookie=0xa1, count=2)
            _hit(debug, hook_b, 2, 0xb22b, 0x2222, 1, True)
            branch_state = _state(debug, control, task=b, cookie=0xb2, count=2)
            assert (branch_state['ram_a'], branch_state['ram_b'], branch_state['code_a'],
                    branch_state['code_b'], branch_state['base_ram'], branch_state['base_code']) == (
                    '3412', '7856', 'f8', 'f9', '0000', '90')
            assert branch_state['hooks'] == h1_state['hooks']
            branch = debug.rewind_record(advance='capture', count=1, timeout_ms=60000)
            h1_prime = branch['cursor']
            assert len({h0, h1, h2, h1_prime}) == 4
            history = branch['history']
            status = debug.rewind_status(history=history)
            assert set((h0, h1, h2, h1_prime)) <= set(status['node_ids'])
            row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (history,)).fetchone()
            nodes = {node['id']: node for node in json.loads(bytes(row['data']))['nodes']}
            assert nodes[h1]['parent'] == nodes[h1_prime]['parent'] == h0
            assert nodes[h2]['parent'] == h1
            assert status['cursor'] == h1_prime
            assert status['captures_used'] == 4 and status['state_bytes_used'] <= 512*1024*1024
            control.update(history=history, h0=h0, state_h0=h0_state)
            old_vm = debug.vm.process
        assert old_vm.poll() is not None
    path = tmp_path / 'history-control.json'
    path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
        capture_output=True, text=True, timeout=240, env=os.environ.copy())
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout)['passed'] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_cold_child(json.loads(Path(sys.argv[1]).read_text()))))


@pytest.mark.parametrize('route', ['python', 'json', 'script'])
def test_native_history_default_single_step_and_rewind_routes(tmp_path, route):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    from fdisbull.debug_script import execute_script
    from test_qemu_memory_rules_native import _case

    with _case(tmp_path) as (project, debug, marker, base, _, _):
        workspace = DebugWorkspace()
        workspace.sessions[debug.run_id] = debug
        def invoke(operation, **options):
            if route == 'python':
                return getattr(debug, operation.replace('-', '_'))(**options)
            if route == 'json':
                reply = respond(dict(method='debug-' + operation, params=dict(
                    project=str(project.path), run=debug.run_id, context='machine', **options)), debugger=workspace)
                assert reply['ok'], reply
                return reply['result']
            report = execute_script(debug, dict(format='fdisbull-script-1', backend='qemu-dos',
                steps=[dict(op=operation, **options)]), timeout_ms=60000)
            assert report['ok'] and report['completed_steps'] == 1, report
            return report['steps'][0]['result']
        try:
            before = debug.registers()['linear_pc']
            assert _number(before) == base + marker['ready']
            invoke('rewind-start', max_steps=4, max_bytes=512*1024*1024, timeout_ms=60000)
            invoke('rewind-record', count=1, timeout_ms=60000)
            after = debug.registers()['linear_pc']
            assert _number(after) == base + marker['loop'] and after != before
            previous_vm = debug.vm.process
            invoke('rewind', count=1, timeout_ms=60000)
            assert previous_vm.poll() is not None
            assert debug.registers()['linear_pc'] == before
        finally:
            workspace.sessions.clear()


def test_native_history_input_refusals_preserve_owned_guest_and_history(tmp_path):
    from test_qemu_memory_rules_native import _case

    with _case(tmp_path) as (project, debug, _, _, _, _):
        root = debug.rewind_start(max_steps=4, timeout_ms=60000)
        debug.keyboard_key_down('shift')
        before_input = debug.input_state()
        before_registers = debug.registers()
        query = "SELECT id FROM debug_artifacts WHERE kind IN ('state','rewind-history') ORDER BY rowid"
        before_rows = project.db.execute(query).fetchall()
        operations = (
            lambda: debug.rewind_start(max_steps=4, timeout_ms=60000),
            lambda: debug.rewind_record(advance='capture', timeout_ms=60000),
            lambda: debug.rewind(history=root['history'], node=root['cursor'], timeout_ms=60000),
        )
        for operation in operations:
            with pytest.raises(ValueError, match='released machine input'):
                operation()
            assert not debug.closed and debug.vm.process.poll() is None
            assert debug.input_state() == before_input
            assert debug.registers() == before_registers
            assert project.db.execute(query).fetchall() == before_rows
