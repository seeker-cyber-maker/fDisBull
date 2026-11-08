"""Native trace control, preflight and persistence boundaries.

The native cases launch an actual authored DOS process. Fault injection is at
the dispatched GDB reply or actual SQLite INSERT, never at trace results.
"""
from __future__ import annotations

import json
import struct
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.execution_trace import ExecutionTraceError
from fdisbull.project import Project
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from test_qemu_dos_process_native import (
    create_project, launch_options, live_word, number, process_disk,
    process_record, process_runtime,
)


# MOV AX,1; INC AX; INC AX; JMP back to the first INC. There is no DOS
# service, external input or self-modification in this authored loop.
LOOP = bytes.fromhex('b80100 40 40 ebfc')
AX_TWO = {'kind': 'register', 'register': 'ax', 'equals': 2}


def unopened_session():
    session = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
    session.metadata = {'backend': 'qemu-dos'}
    session.vm = SimpleNamespace(lock=threading.RLock(), gdb=None, qmp=None)
    session._stopped = lambda: pytest.fail('Preflight reached native control')
    session._artifact = lambda *a, **kw: pytest.fail('Preflight persisted an artifact')
    session.write_registers = lambda registers: pytest.fail('Earlier register write ran')
    return session


@pytest.mark.parametrize('action', [
    {'op': 'click', 'x': 1, 'y': 2},
    {'op': 'keyboard.press', 'key': 'a'},
])
def test_queued_actions_refuse_before_native_control_or_earlier_script_write(action):
    session = unopened_session()
    with pytest.raises(ValueError, match='clock/input'):
        session.trace_until(AX_TWO, action=action)
    route = {'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': [
        {'op': 'write-registers', 'registers': {'rax': {'expected': 0, 'value': 1}}},
        {'op': 'trace-until', 'until': AX_TWO, 'action': action},
    ]}
    # Admission also works without a live VM, and fails before an earlier
    # operation can mutate state when the route is executed against a session.
    with pytest.raises(ValueError, match='clock/input'):
        validate_script(route)
    with pytest.raises(ValueError, match='clock/input'):
        execute_script(session, route)


@pytest.mark.parametrize('options,message', [
    ({'until': {'kind': 'register', 'register': 'invented', 'equals': 1}}, 'register'),
    ({'until': AX_TWO, 'max_steps': True}, 'max_steps'),
    ({'until': AX_TWO, 'label': '$earlier.result'}, 'literal'),
])
def test_invalid_later_trace_descriptor_refuses_before_earlier_script_write(options, message):
    route = {'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': [
        {'op': 'write-registers', 'registers': {'rax': {'expected': 0, 'value': 1}}},
        {'op': 'trace-until', **options},
    ]}
    with pytest.raises(ValueError, match=message):
        execute_script(unopened_session(), route)


def document(project, artifact, tmp_path):
    path = tmp_path / 'saved-boundaries.json'
    path.unlink(missing_ok=True)
    project.debug_export(artifact, path)
    return json.loads(path.read_text())


def test_native_public_saved_script_stops_at_register_match_and_reopens(
        tmp_path, process_runtime, process_disk):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace

    binary, project = create_project(tmp_path, LOOP)
    with project:
        pass
    database = tmp_path / 'program.fdb'
    workspace = DebugWorkspace()

    def invoke(method, **params):
        reply = respond({'method': method, 'params': {'project': str(database), **params}},
                        debugger=workspace)
        assert reply['ok'], reply
        return reply['result']

    try:
        started = invoke('debug-launch', executable=str(process_runtime['executable']),
                         game_dir=str(tmp_path), **launch_options(process_runtime, process_disk))
        run = started['run']
        active = invoke('debug-dos-process', run=run)
        result = invoke('debug-script', run=run, timeout_ms=5000, script={
            'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': [
                {'op': 'trace-until', 'until': AX_TWO, 'max_steps': 4,
                 'timeout_ms': 3000, 'name': 'script-match.json', 'as': 'matched'},
                {'op': 'assert', 'value': '$matched.exact_stop', 'equals': True},
            ],
        })
        assert result['ok'] and result['completed_steps'] == 2, result
        match = result['steps'][0]['result']
        assert match['matched'] and match['complete'] and match['exact_stop']
        assert match['steps'] == match['attempted_steps'] == 2
        registers = invoke('debug-registers', run=run)
        assert live_word(registers, 'rax', 'eax', 'ax') == 2
        assert number(registers['linear_pc']) == number(active['source_mapping']['runtime_base']) + 4
        assert invoke('debug-stop', run=run)['process_reaped']
    finally:
        workspace.close()
    assert binary.read_bytes() == LOOP
    with Project(database) as reopened:
        saved = document(reopened, match['trace_artifact'], tmp_path)
        assert saved['collector']['outcome'] == 'predicate'
        assert saved['window']['closed'] is True
        assert [event['observation']['instruction_completed'] for event in saved['events']] == [None, None, False]
        rows = reopened.db.execute('SELECT kind FROM debug_artifacts WHERE run=?', (run,))
        assert {'script', 'script-result', 'trace'} <= {row['kind'] for row in rows}


def test_native_watchpoint_is_foreign_stop_and_does_not_claim_retirement(
        tmp_path, process_runtime, process_disk):
    # MOV byte [0109],42; idle loop; independent data byte at offset 0109.
    code = bytes.fromhex('c606090142 ebfe 000000')
    _, project = create_project(tmp_path, code)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        active = process_record(debug)
        base = number(active['source_mapping']['runtime_base'])
        point = debug.breakpoint(base + 9, access='w', length=1)
        result = debug.trace_until(AX_TWO, max_steps=4, timeout_ms=3000)
        assert result['outcome'] == 'foreign_stop', result
        assert result['foreign_stop']['outcome'] == 'watchpoint'
        assert result['matched'] is False and result['exact_stop'] is False
        assert result['source_window_closed'] is False
        assert result['attempted_steps'] == 1 and result['steps'] == 0
        assert point['breakpoint_id'] in debug.breakpoints
        saved = document(project, result['trace_artifact'], tmp_path)
        assert len(saved['events']) == 1
        assert saved['events'][0]['observation']['instruction_completed'] is None
        assert saved['window']['closed'] is False
        assert debug.status()['state'] == 'stopped'


def test_native_external_pc_predicate_can_match_without_source_projection(
        tmp_path, process_runtime, process_disk):
    # MOV AH,30; INT 21; idle. The vector is read from this actual DOS boot;
    # no assumption about a particular kernel segment or handler is needed.
    _, project = create_project(tmp_path, bytes.fromhex('b430 cd21 ebfe'))
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        process_record(debug)
        vector = bytes.fromhex(debug.memory(0x21 * 4, length=4, space='physical')['hex'])
        offset, segment = struct.unpack('<HH', vector)
        target = segment * 16 + offset
        result = debug.trace_until({'kind': 'pc-range', 'space': 'linear',
                                   'start': target, 'end': target + 1},
                                  max_steps=4, timeout_ms=3000)
        assert result['outcome'] == 'predicate', result
        assert result['matched'] and result['exact_stop'] and result['complete']
        assert result['steps'] == 2 and result['source_window_closed'] is False
        assert number(debug.registers()['linear_pc']) == target
        assert result['matched_event']['site'] is None
        assert result['matched_event']['pc']['project'] is None
        saved = document(project, result['trace_artifact'], tmp_path)
        assert saved['window']['closed'] is False
        final = saved['events'][-1]
        assert final['project_address'] is None
        assert final['source_qualification']['qualified'] is False
        assert final['observation']['instruction_completed'] is False


def test_native_deadline_is_incomplete_and_leaves_owned_machine_stopped_or_reaped(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, LOOP)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        active = process_record(debug)
        static = number(active['source_mapping']['static_base'])
        started = time.monotonic()
        result = debug.trace_until({'kind': 'pc-range', 'space': 'project',
                                   'start': static + 1000, 'end': static + 1001},
                                  max_steps=9999, timeout_ms=150)
        elapsed = time.monotonic() - started
        assert result['outcome'] == 'timeout', result
        assert not result['matched'] and not result['exact_stop'] and not result['complete']
        assert result['source_window_closed'] is False
        assert elapsed < 6, 'A trace deadline must not become an unbounded native wait'
        assert debug._deadline is None and debug.vm.operation_deadline is None
        if debug.vm.process.poll() is None:
            assert debug.status()['state'] == 'stopped'
            assert debug.vm.gdb.operation_deadline is None
            assert debug.vm.qmp.operation_deadline is None
        else:
            assert debug.dos_process_info()['source_mapping']['live'] is False
        saved = document(project, result['trace_artifact'], tmp_path)
        assert saved['collector']['outcome'] == 'timeout'
        assert saved['window']['closed'] is False
        assert all(event['observation']['instruction_completed'] is not True for event in saved['events'])


def test_native_lost_step_reply_is_not_replayed_and_invalidates_live_process(
        tmp_path, process_runtime, process_disk, monkeypatch):
    _, project = create_project(tmp_path, LOOP)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        active = process_record(debug)
        remote = debug.vm.debugger()
        send, packet = remote._send, remote._packet
        attempts, lost = [], [False]

        def dispatch(command, deadline):
            send(command, deadline)
            if command == 's':
                attempts.append(command)
                lost[0] = True

        def receive(deadline):
            if lost[0]:
                lost[0] = False
                raise OSError('authored loss of a dispatched step reply')
            return packet(deadline)

        monkeypatch.setattr(remote, '_send', dispatch)
        monkeypatch.setattr(remote, '_packet', receive)
        result = debug.trace_until(AX_TWO, max_steps=4, timeout_ms=3000)
        assert result['outcome'] == 'error' and result['error']['type'] == 'OSError'
        assert result['attempted_steps'] == 1 and result['steps'] == 0
        assert attempts == ['s']
        assert not result['matched'] and not result['complete'] and not result['exact_stop']
        assert result['current_stop'] is None, 'The pre-step snapshot is not a verified current stop after reply loss'
        assert remote.socket is None and debug.vm.process.poll() is not None
        failed = debug.dos_process_info()
        assert failed['state'] == 'observation_failed'
        assert failed['source_mapping']['live'] is False
        assert failed['capture_epoch'] != active['capture_epoch']
        assert debug._deadline is None
        saved = document(project, result['trace_artifact'], tmp_path)
        assert len(saved['events']) == 1
        assert saved['events'][0]['observation']['instruction_completed'] is None
        assert saved['window']['closed'] is False


def test_native_caller_transaction_refuses_direct_and_scripted_traces_before_execution(
        tmp_path, process_runtime, process_disk, monkeypatch):
    _, project = create_project(tmp_path, LOOP)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        process_record(debug)
        before = debug.registers()
        remote, dispatched = debug.vm.debugger(), []
        send = remote._send

        def record(command, deadline):
            dispatched.append(command)
            return send(command, deadline)

        monkeypatch.setattr(remote, '_send', record)
        artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
        events = project.db.execute('SELECT count(*) FROM debug_events').fetchone()[0]
        for operation, method, params in (
                ('trace', debug.trace, {'count': 1}),
                ('trace-until', debug.trace_until, {'until': AX_TWO, 'max_steps': 4})):
            with project.transaction(True):
                with pytest.raises(ValueError, match='transaction'):
                    method(**params)
                assert not dispatched, 'Refusal must precede native observation or execution'
                with pytest.raises(ValueError, match='transaction'):
                    debug.script({'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': [
                        {'op': 'step', 'timeout_ms': 1000},
                        {'op': operation, **params},
                    ]})
                assert not dispatched, 'An earlier script step escaped transaction preflight'
                assert project.db.in_transaction
            assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == artifacts
            assert project.db.execute('SELECT count(*) FROM debug_events').fetchone()[0] == events
        after = debug.registers()
        assert before['registers'] == after['registers']
        assert before['linear_pc'] == after['linear_pc']
        assert debug.status()['state'] == 'stopped'


@pytest.mark.parametrize('failure', ['artifact', 'journal'])
def test_native_persistence_failure_retains_observed_stop_without_replaying(
        tmp_path, process_runtime, process_disk, failure):
    _, project = create_project(tmp_path, LOOP)
    with project, project.debugger(process_runtime['executable'], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        active = process_record(debug)
        table, condition = ('debug_artifacts', "NEW.kind = 'trace'") if failure == 'artifact' else (
            'debug_events', "NEW.operation = 'trace-until'")
        with project.transaction(True):
            project.db.execute(f"""
                CREATE TRIGGER reject_trace_publication BEFORE INSERT ON {table}
                WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'authored trace publication failure'); END
            """)
        with pytest.raises(ExecutionTraceError, match='authored trace publication failure') as caught:
            debug.trace_until(AX_TWO, max_steps=4, timeout_ms=3000)
        result = caught.value.result
        assert result['persistence_error']['type'] == 'IntegrityError'
        assert result['outcome'] == 'predicate' and result['matched'] and result['exact_stop']
        assert result['attempted_steps'] == result['steps'] == 2
        assert debug.status()['state'] == 'stopped'
        registers = debug.registers()
        assert live_word(registers, 'rax', 'eax', 'ax') == 2
        assert number(registers['linear_pc']) == number(active['source_mapping']['runtime_base']) + 4
        assert project.db.execute("SELECT count(*) FROM debug_events WHERE run=? AND operation='machine-step'",
                                  (debug.run_id,)).fetchone()[0] == 2
        assert not project.db.in_transaction
        if failure == 'artifact':
            assert 'trace_artifact' not in result
            assert not project.db.execute("SELECT 1 FROM debug_artifacts WHERE run=? AND kind='trace'",
                                          (debug.run_id,)).fetchone()
        else:
            saved = document(project, result['trace_artifact'], tmp_path)
            assert saved['collector']['outcome'] == 'predicate'
            assert saved['events'][-1]['observation']['instruction_completed'] is False
    if failure == 'journal':
        with Project(tmp_path / 'program.fdb') as reopened:
            assert document(reopened, result['trace_artifact'], tmp_path) == saved
