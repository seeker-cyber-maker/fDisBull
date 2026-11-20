"""Five opt-in raw-vCPU witnesses, admitted by a separately owned gate.

Use the reviewed outer controller and owner plugin described in
docs/QEMU_STEP_COUNT_GATE.md. This module does not qualify DOS process returns,
protected source lifetimes, step-over or guest instruction retirement.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from test_qemu_dos_native import create_boot_project, enter_loop, selected_qemu


@pytest.fixture(scope='module', autouse=True)
def require_owned_gate(request):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_STEP_COUNT') != '1':
        pytest.skip('Requires the separately admitted, bounded QEMU step-count owner gate')
    assert getattr(request.config, '_fdisbull_step_count_owned_gate', None) == 'fdisbull-step-count-owned-gate-1', (
        'Required native step-count run lacks its reviewed ownership plugin')
    assert request.config.option.maxfail == 1, 'The native gate must stop at its first failure'
    assert not getattr(request.config.option, 'numprocesses', None), 'Native owners must be sequential'


@contextmanager
def owner(tmp_path):
    executable, options = selected_qemu()
    path, symbols, project = create_boot_project(tmp_path)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    with project:
        with project.debugger(executable, tmp_path, boot_timeout_ms=30000, **options) as debug:
            enter_loop(debug, symbols)
            process = debug.vm.process
            calls = []
            remote = debug.vm.gdb
            execute = remote.execute
            def observed(command, timeout_ms, **kwargs):
                row = dict(command=command, timeout_ms=timeout_ms)
                calls.append(row)
                reply, timed_out = execute(command, timeout_ms, **kwargs)
                row.update(native_reply=reply.decode('ascii'), timed_out=timed_out)
                return reply, timed_out
            remote.execute = observed
            try:
                yield debug, symbols, calls
            finally:
                primary = sys.exception()
                remote.execute = execute
                # Original receipts, including partial attempts, survive a
                # failed assertion. The ownership plugin retains native logs.
                try:
                    (tmp_path/'step-dispatches.json').write_text(json.dumps(calls, indent=2)+'\n')
                    if primary is not None and getattr(primary, 'result', None) is not None:
                        retain(tmp_path, primary.result, name='step-error.json')
                except BaseException as retention:
                    if primary is None:raise
                    primary.add_note('Step evidence retention failed: '+repr(retention))
        assert process.poll() is not None, 'Native owner was not reaped'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original


def retain(tmp_path, result, *, name='step-sequence.json'):
    with (tmp_path/name).open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


@pytest.mark.parametrize('route', ['python', 'json', 'script'])
def test_native_counted_steps_public_routes(tmp_path, route):
    with owner(tmp_path) as (debug, symbols, calls):
        if route == 'python':
            result = debug.step(count=3, timeout_ms=5000)
        elif route == 'json':
            workspace = DebugWorkspace()
            workspace.sessions[debug.run_id] = debug
            try:
                reply = respond(dict(id=1, method='debug-step', params=dict(
                    project=str(debug.project.path), run=debug.run_id, count=3, timeout_ms=5000)),
                    debugger=workspace)
                retain(tmp_path, reply, name='step-json-response.json')
                assert reply['ok'], reply
                result = reply['result']
            finally:
                workspace.sessions.clear()
        else:
            report = debug.script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='step', count=3, timeout_ms=5000, **{'as': 'batch'}),
                dict(op='assert', value='$batch.completed_count', equals=3),
            ]), timeout_ms=10000)
            retain(tmp_path, report, name='step-script-report.json')
            assert report['ok'], report
            result = report['steps'][0]['result']
        retain(tmp_path, result)
        assert result['complete'] and result['completed_count'] == result['requested_count'] == 3
        assert result['instruction_completed'] is None
        assert [int(row['registers']['linear_pc'], 16) for row in result['steps']] == [
            symbols['loop']+4, symbols['loop']+5, symbols['loop']]
        assert debug.memory(symbols['counter'], length=2)['hex'] == '0800'
        assert [row['command'] for row in calls] == ['s', 's', 's']


def test_native_counted_steps_stop_at_first_user_breakpoint(tmp_path):
    with owner(tmp_path) as (debug, symbols, calls):
        point = debug.breakpoint(symbols['loop']+5)
        result = debug.step(count=3, timeout_ms=5000)
        retain(tmp_path, result)
        assert not result['complete'] and result['completed_count'] == 1
        assert result['attempted_count'] == 2 and result['outcome'] == 'breakpoint'
        assert point['breakpoint_id'] in result['terminal_stop']['breakpoints']
        assert int(debug.registers()['linear_pc'], 16) == symbols['loop']+5
        assert debug.memory(symbols['counter'], length=2)['hex'] == '0800'
        assert [row['command'] for row in calls] == ['s', 's']
        debug.delete_breakpoint(point['breakpoint_id'])


def test_native_counted_steps_stop_at_first_write_watchpoint(tmp_path):
    with owner(tmp_path) as (debug, symbols, calls):
        point = debug.breakpoint(symbols['counter'], access='w', length=2)
        result = debug.step(count=3, timeout_ms=5000)
        retain(tmp_path, result)
        assert not result['complete'] and result['completed_count'] == 0
        assert result['attempted_count'] == 1 and result['outcome'] == 'watchpoint'
        assert point['breakpoint_id'] in result['terminal_stop']['breakpoints']
        # Existing native watchpoint contract leaves access stage unknown.
        # This row proves first-stop ownership, not completion of the INC.
        assert debug.memory(symbols['counter'], length=2)['hex'] in ('0700', '0800')
        assert [row['command'] for row in calls] == ['s']
        debug.delete_breakpoint(point['breakpoint_id'])
