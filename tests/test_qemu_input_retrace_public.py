"""Public admission and script ownership for retrace-bound physical input."""
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineContext
from test_qemu_io_public import raw_project, stopped_session


OPERATION = 'input-schedule-retrace'


def script(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-machine', steps=list(steps))


def test_retrace_input_exposes_one_public_owned_operation():
    assert 'debug-' + OPERATION in METHODS
    assert OPERATIONS[OPERATION] == 'input_schedule_retrace'
    assert callable(getattr(MachineContext, 'input_schedule_retrace', None))


def test_retrace_input_json_keeps_explicit_edge_and_deadline(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    calls = []

    def arm(**parameters):
        calls.append(parameters)
        return dict(state='armed', token='owned-retrace-input')

    session.input_schedule_retrace = arm
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        value = respond(dict(id=27, method='debug-' + OPERATION,
            params=dict(project=str(raw_project.path), run=session.run_id,
                        context='machine', edge='exit', timeout_ms=75)), debugger=workspace)
        assert value['ok'], value
        assert value['result'] == dict(state='armed', token='owned-retrace-input')
        assert calls == [dict(edge='exit', timeout_ms=75)] and not peer.calls
    finally:
        workspace.sessions.clear()
        session.close()


def test_retrace_input_capability_refuses_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with pytest.raises(ValueError, match='retrace|precise'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                       dict(op=OPERATION)))
    assert not writes and not peer.calls


@pytest.mark.parametrize('options', [
    {'edge': 'vblank'}, {'edge': True}, {'edge': 1}, {'edge': None},
    {'timeout_ms': True}, {'timeout_ms': 0}, {'timeout_ms': 600001},
    {'timeout_ms': 1.5}, {'edge': '$selection.edge', 'timeout_ms': -1},
    {'edge': 'enter', 'timeout_ms': '$selection.timeout', 'unexpected': 3},
])
def test_retrace_input_literals_refuse_whole_script_before_mutation(
        raw_project, tmp_path, options):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['retrace_input_schedule'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    route = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op=OPERATION, **options))
    with pytest.raises((ValueError, TypeError)):
        validate_script(route)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, route)
    assert not writes and not peer.calls


def test_retrace_input_caller_transaction_refuses_before_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['retrace_input_schedule'] = True
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    raw_project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                           dict(op=OPERATION)))
        assert not writes and not peer.calls
    finally:
        raw_project.db.rollback()


def test_retrace_input_uses_the_remaining_script_deadline(raw_project, tmp_path, monkeypatch):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['retrace_input_schedule'] = True
    now, calls = [100.0], []
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])

    def write_memory(address, data_hex):
        now[0] += .030
        return dict(written=1)

    def arm(*, edge='enter', timeout_ms=1000):
        calls.append(dict(edge=edge, timeout_ms=timeout_ms))
        return dict(state='armed')

    session.write_memory = write_memory
    session.input_schedule_retrace = arm
    result = execute_script(session, script(
        dict(op='write-memory', address=0x7c00, data_hex='90'),
        dict(op=OPERATION, edge='exit', timeout_ms=500)), timeout_ms=100)
    assert result['ok'], result
    assert len(calls) == 1 and calls[0]['edge'] == 'exit'
    assert 1 <= calls[0]['timeout_ms'] <= 70
    assert not peer.calls


@pytest.mark.parametrize('timeout', [None, True, 0, 600001, 500.5])
def test_retrace_input_referenced_timeout_is_validated_before_clamping(
        raw_project, tmp_path, timeout):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['retrace_input_schedule'] = True
    calls = []

    def arm(*, edge='enter', timeout_ms=1000):
        calls.append(dict(edge=edge, timeout_ms=timeout_ms))
        return dict(state='armed')

    session.input_schedule_retrace = arm
    result = execute_script(session, script(dict(op=OPERATION,
        timeout_ms='$selection.timeout')), bindings={'selection': {'timeout': timeout}}, timeout_ms=100)
    assert not result['ok']
    assert not calls and not peer.calls


def test_failed_script_cleans_up_an_arm_of_a_preexisting_batch(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['retrace_input_schedule'] = True
    calls = []

    def arm(*, edge='enter', timeout_ms=1000):
        calls.append(('arm', edge))
        return dict(state='armed', token='preexisting-batch')

    # This public script witness isolates routing of ownership cleanup. Native
    # tests independently require disarm/closure and absence of later delivery.
    session.input_schedule_retrace = arm
    session.close = lambda: calls.append(('close',))
    result = execute_script(session, script(
        dict(op=OPERATION), dict(op='assert', value=False, equals=True)))
    assert not result['ok'] and result['completed_steps'] == 1
    assert calls[0] == ('arm', 'enter')
    assert calls == [('arm', 'enter'), ('close',)]
    assert result['input_cleanup']['closed'] is True
    assert not peer.calls


def test_retrace_input_capability_requires_every_native_seam(raw_project, tmp_path):
    from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
    from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
    from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration

    session, peer = stopped_session(raw_project, tmp_path)
    vm = session.vm
    commands = VIRTUAL_CLOCK_COMMANDS | INPUT_SCHEDULE_COMMANDS | RETRACE_COMMANDS | {
        'x-fdisbull-arm-input-retrace'}
    vm.machine_configuration['clock_profile'] = machine_clock_configuration('virtual', 1)
    vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    for missing in sorted(commands):
        vm.qmp_commands = commands - {missing}
        context = MachineContext(vm)
        assert context.capabilities['retrace_input_schedule'] is False, missing
    vm.qmp_commands = commands
    context = MachineContext(vm)
    assert context.capabilities['retrace_input_schedule'] is True
    assert context.capabilities['timed_input'] is False
    assert context.capabilities['completed_guest_frames'] is False
    vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('standard', 'virtual')
    assert MachineContext(vm).capabilities['retrace_input_schedule'] is False
    assert not peer.calls
