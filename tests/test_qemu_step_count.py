"""Bounded public step sequences through authored host peers, never a VM.

Native instruction effects and debugger policy require a separate native gate.
These checks exercise the production execution, routing and script controllers.
"""
import json
from types import SimpleNamespace

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from test_late_tracking_stop import Clock, Machine, owned
from test_qemu_io_public import raw_project, stopped_session


@pytest.fixture
def stopped(monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock.monotonic)
    machine = Machine(clock)
    machine.vm.closed = False
    machine.vm.close = lambda: setattr(machine.vm, 'closed', True)
    return machine, clock


def stops(machine, *rows):
    machine.remote.stops = [(pc, False, 0, b'T05') if isinstance(pc, int) else pc for pc in rows]


def test_counted_step_retains_each_native_stop_and_one_requested_count(stopped):
    machine, _ = stopped
    stops(machine, 0x20101, 0x20102, 0x20103)
    result = machine.step(count=3, timeout_ms=100)
    assert result['format'] == 'fdisbull-machine-step-sequence-1'
    assert result['requested_count'] == result['completed_count'] == result['attempted_count'] == 3
    assert result['complete'] is True and result['timed_out'] is False
    assert result['outcome'] == 'step'
    assert [s['registers']['linear_pc'] for s in result['steps']] == ['0x20101', '0x20102', '0x20103']
    assert result['terminal_stop'] == result['steps'][-1]
    assert result['instruction_completed'] is None
    assert machine.remote.calls == ['s', 's', 's']
    assert not machine.vm.closed


def test_default_and_explicit_single_step_keep_the_original_receipt(stopped):
    machine, _ = stopped
    stops(machine, 0x20101, 0x20101)
    ordinary = machine.step(timeout_ms=100)
    explicit = machine.step(count=1, timeout_ms=100)
    assert ordinary == explicit
    assert ordinary['outcome'] == 'step'
    assert 'format' not in ordinary and 'steps' not in ordinary


@pytest.mark.parametrize('count', [True, False, 0, -1, 10001, 1.5, '2', None])
def test_bad_count_refuses_before_lock_guard_or_execution(stopped, count):
    machine, _ = stopped
    machine.vm.operation_guard = lambda name: pytest.fail('Invalid count reached a control guard')
    with pytest.raises(ValueError, match='count'):
        machine.step(count=count)
    assert not machine.remote.calls and not machine.vm.closed


@pytest.mark.parametrize('timeout', [True, 0, -1, 600001, 1.5, '20', None])
def test_bad_sequence_timeout_refuses_before_control_guard(stopped, timeout):
    machine, _ = stopped
    machine.vm.operation_guard = lambda name: pytest.fail('Invalid timeout reached a control guard')
    with pytest.raises(ValueError, match='timeout'):
        machine.step(count=2, timeout_ms=timeout)
    assert not machine.remote.calls


@pytest.mark.parametrize('schedule', [False, True])
def test_pending_input_or_bound_schedule_refuses_before_any_control(stopped, schedule):
    machine, _ = stopped
    machine.vm._physical_input = dict(valid=True, pending=[] if schedule else [{}],
                                     schedule={'bound': True} if schedule else None)
    machine.vm.operation_guard = lambda name: pytest.fail('Input refusal reached a control guard')
    with pytest.raises(ValueError, match='input'):
        machine.step(count=2)
    assert not machine.remote.calls and not machine.vm.closed


@pytest.mark.parametrize('reply,timed_out,outcome', [
    (b'T05thread:01;watch:300;', False, 'watchpoint'),
    (b'T0b', False, 'exception'),
    (b'S02', False, 'stopped'),
    (b'W00', False, 'exited'),
    (b'T05', True, 'timeout'),
])
def test_first_non_step_receipt_stops_without_replay(stopped, reply, timed_out, outcome):
    machine, _ = stopped
    stops(machine, 0x20101, (0x20102, timed_out, 0, reply), 0x20103)
    result = machine.step(count=3, timeout_ms=100)
    assert result['completed_count'] == 1 and result['attempted_count'] == 2
    assert result['complete'] is False and result['outcome'] == outcome
    assert result['terminal_stop']['session']['stop_reason']['native_reply'] == reply.decode()
    assert len(result['steps']) == 1 and machine.remote.calls == ['s', 's']


def test_user_breakpoint_is_the_terminal_stop(stopped):
    machine, _ = stopped
    bp = machine.breakpoint(0x20102)['breakpoint_id']
    stops(machine, 0x20101, 0x20102, 0x20103)
    result = machine.step(count=3)
    assert result['completed_count'] == 1 and result['outcome'] == 'breakpoint'
    assert result['terminal_stop']['breakpoints'] == [bp]
    assert machine.remote.calls == ['s', 's']


def test_internal_lifecycle_hook_is_not_hidden_by_another_step(stopped):
    machine, _ = stopped
    bp = owned(machine, 0x20102)
    stops(machine, 0x20101, 0x20102, 0x20103)
    result = machine.step(count=3)
    assert result['completed_count'] == 1 and result['outcome'] == 'breakpoint'
    assert result['terminal_stop']['automatic_breakpoints'] == [bp]
    assert machine._automatic_internal_pending['pc'] == '0x20102'
    assert machine.remote.calls == ['s', 's']


def test_budget_expiry_between_stops_preserves_completed_prefix(stopped):
    machine, clock = stopped
    stops(machine, (0x20101, False, .0995, b'T05'), 0x20102)
    result = machine.step(count=2, timeout_ms=100)
    assert result['complete'] is False and result['outcome'] == 'timeout'
    assert result['completed_count'] == result['attempted_count'] == 1
    assert result['terminal_stop']['outcome'] == 'step'
    assert machine.remote.calls == ['s']
    assert clock.now < .1 and not machine.vm.closed


def test_one_deadline_intersects_existing_bounds_and_is_restored(stopped):
    machine, clock = stopped
    machine._deadline = .08
    machine._rpc_deadline = .07
    machine.vm.operation_deadline = .09
    machine.remote.operation_deadline = .06
    machine.vm.qmp.operation_deadline = .075
    real_execute = machine.remote.execute
    budgets = []
    def execute(command, timeout_ms, **options):
        budgets.append((timeout_ms, machine._deadline, machine.vm.operation_deadline,
                        machine.remote.operation_deadline, machine.vm.qmp.operation_deadline))
        return real_execute(command, timeout_ms, **options)
    machine.remote.execute = execute
    stops(machine, (0x20101, False, .02, b'T05'), (0x20102, False, .02, b'T05'))
    result = machine.step(count=2, timeout_ms=100)
    assert result['complete'] is True
    assert budgets[0][0] > budgets[1][0] > 0
    assert all(row[1:] == (.06, .06, .06, .06) for row in budgets)
    assert (machine._deadline, machine._rpc_deadline, machine.vm.operation_deadline,
            machine.remote.operation_deadline, machine.vm.qmp.operation_deadline) == (.08, .07, .09, .06, .075)


def test_expired_lock_admission_cannot_dispatch(stopped):
    machine, clock = stopped
    class Lock:
        def acquire(self, *, timeout):
            clock.now += timeout + .001
            return True
        def release(self):
            pass
    machine.vm.lock = Lock()
    with pytest.raises(TimeoutError, match='deadline'):
        machine.step(count=2, timeout_ms=20)
    assert not machine.remote.calls


def test_input_changed_during_lock_wait_refuses_before_guard_io(stopped):
    machine, _ = stopped
    class Lock:
        def acquire(self, *, timeout):
            machine.vm._physical_input = dict(valid=True, pending=[{}], schedule=None)
            return True
        def release(self):
            pass
    machine.vm.lock = Lock()
    machine.vm.operation_guard = lambda name: pytest.fail('Changed input reached a native guard')
    with pytest.raises(ValueError, match='input'):
        machine.step(count=2)
    assert not machine.remote.calls


def test_pending_lifecycle_step_preserves_late_stop_and_control_repair(stopped):
    machine, _ = stopped
    owned(machine, 0x20200)
    stops(machine, 0x20200)
    first = machine.step(timeout_ms=100)
    assert first['outcome'] == 'breakpoint' and machine._automatic_internal_pending is not None
    stops(machine, (0x20201, True, .11, b'T05'), 0x20202)
    with pytest.raises(TimeoutError) as error:
        machine.step(count=3, timeout_ms=100)
    result = error.value.result
    assert result['completed_count'] == 0 and result['attempted_count'] == 1
    assert result['terminal_stop']['outcome'] == 'timeout'
    repair = result['terminal_stop']['tracking_control_repair']
    assert repair['grace_used'] is True and repair['complete'] is True
    assert machine.remote.calls == ['s', 's']
    assert machine.remote.request_budgets[-1] == 1000
    assert machine._automatic_internal_pending is None and not machine.vm.closed


def test_post_stop_failure_preserves_primary_error_prefix_and_native_stop(stopped):
    machine, _ = stopped
    original = RuntimeError('authored post-stop observation failure')
    old_after = machine._automatic_runtime_tracker.after_stop
    def after(reason):
        if machine.pc == 0x20102:
            raise original
        old_after(reason)
    machine._automatic_runtime_tracker.after_stop = after
    stops(machine, 0x20101, 0x20102, 0x20103)
    with pytest.raises(RuntimeError) as error:
        machine.step(count=3)
    assert error.value is original
    result = error.value.result
    assert result['complete'] is False and result['completed_count'] == 1
    assert result['attempted_count'] == 2 and result['outcome'] == 'error'
    assert result['terminal_stop']['registers']['linear_pc'] == '0x20102'
    assert machine.remote.calls == ['s', 's'] and machine.vm.closed


@pytest.mark.parametrize('damage', ['registers', 'session', 'reason', 'native_reply'])
def test_uncertain_step_receipt_cannot_authorize_a_later_dispatch(stopped, damage):
    machine, _ = stopped
    calls = []
    incomplete = dict(outcome='step', timed_out=False, registers={}, breakpoints=[],
                      session=dict(state='stopped', stop_reason=dict(kind='step', native_reply='T05')))
    if damage == 'registers':incomplete['registers'] = None
    elif damage == 'session':incomplete['session'] = []
    elif damage == 'reason':incomplete['session']['stop_reason'] = []
    else:incomplete['session']['stop_reason']['native_reply'] = None
    machine._execute = lambda command, timeout_ms: calls.append(command) or incomplete
    with pytest.raises(DebuggerError, match='incomplete') as error:
        machine.step(count=2)
    assert error.value.result['terminal_stop'] == incomplete
    assert error.value.result['completed_count'] == 0
    assert calls == ['s'] and machine.vm.closed


@pytest.fixture
def public_machine(raw_project, tmp_path):
    session, _ = stopped_session(raw_project, tmp_path)
    remote = SimpleNamespace(socket=object(), operation_deadline=None, calls=[], replies=[], pc=0x7c00)
    def execute(command, timeout_ms, **options):
        remote.calls.append(command)
        remote.pc += 1
        return remote.replies.pop(0) if remote.replies else (b'T05thread:01;', False)
    remote.execute = execute
    session.vm.gdb = remote
    session._stopped = lambda: remote
    session.registers = lambda: dict(context='machine', registers={'eip': hex(remote.pc)},
                                    cpu_mode='real', linear_pc=hex(remote.pc))
    try:
        yield session, remote
    finally:
        session.close()


def test_json_count_uses_real_adapter_and_persists_each_native_stop(public_machine):
    session, remote = public_machine
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    reply = respond(dict(id=1, method='debug-step', params=dict(
        project=str(session.project.path), run=session.run_id, count=3, timeout_ms=1000)), debugger=workspace)
    workspace.sessions.clear()
    assert reply['ok'] is True and reply['result']['complete'] is True
    assert reply['result']['completed_count'] == 3 and remote.calls == ['s']*3
    rows = session.project.db.execute("SELECT evidence FROM debug_events WHERE operation='machine-step' ORDER BY sequence").fetchall()
    assert [json.loads(row['evidence'])['registers']['linear_pc'] for row in rows] == ['0x7c01', '0x7c02', '0x7c03']


@pytest.mark.parametrize('error_type', [ValueError, RuntimeError])
def test_json_failure_retains_prefix_and_original_terminal_receipt(public_machine, error_type):
    session, remote = public_machine
    original_event = session._event
    def event(operation, value):
        if remote.pc == 0x7c02:
            raise error_type('authored publication failure')
        return original_event(operation, value)
    session._event = event
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    reply = respond(dict(id=1, method='debug-step', params=dict(
        project=str(session.project.path), run=session.run_id, count=3, timeout_ms=1000)), debugger=workspace)
    workspace.sessions.clear()
    assert reply['ok'] is False and reply['error']['type'] == error_type.__name__
    assert reply['error']['message'] == 'authored publication failure'
    result = reply['error']['result']
    assert result['completed_count'] == 1 and result['attempted_count'] == 2
    assert result['terminal_stop']['registers']['linear_pc'] == '0x7c02'
    assert remote.calls == ['s', 's'] and session.vm.qmp is None


def test_single_step_json_keeps_existing_unhandled_error_behavior(public_machine):
    session, remote = public_machine
    def event(operation, value):
        raise RuntimeError('unhandled single-step callback')
    session._event = event
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        with pytest.raises(RuntimeError, match='unhandled single-step callback'):
            respond(dict(id=1, method='debug-step', params=dict(
                project=str(session.project.path), run=session.run_id, timeout_ms=1000)), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert remote.calls == ['s']


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_saved_counted_step_grammar_is_available_without_a_live_owner(backend):
    route = dict(format='fdisbull-script-1', backend=backend,
                 steps=[dict(op='step', count=3, timeout_ms=1000)])
    assert validate_script(route) == route['steps']


def test_script_counted_step_and_result_reference_use_observed_count(public_machine):
    session, remote = public_machine
    result = execute_script(session, dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='step', count=3, timeout_ms=1000, **{'as': 'batch'}),
        dict(op='assert', value='$batch.completed_count', equals=3),
    ]))
    assert result['ok'] and result['completed_steps'] == 2
    assert result['steps'][0]['result']['complete'] is True
    assert remote.calls == ['s']*3


def test_script_non_step_terminal_prevents_later_route_execution(public_machine):
    session, remote = public_machine
    remote.replies = [(b'T05thread:01;', False), (b'S02', False)]
    result = execute_script(session, dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='step', count=3, timeout_ms=1000), dict(op='step'),
    ]))
    assert not result['ok'] and len(result['steps']) == 1
    assert result['steps'][0]['result']['completed_count'] == 1
    assert result['steps'][0]['result']['terminal_stop']['outcome'] == 'stopped'
    assert remote.calls == ['s', 's']


@pytest.mark.parametrize('parameter,value', [('count', 10001), ('count', True), ('count', None),
                                          ('timeout_ms', 600001), ('timeout_ms', None)])
def test_script_invalid_later_literal_refuses_before_earlier_execution(public_machine, parameter, value):
    session, remote = public_machine
    with pytest.raises(ValueError):
        execute_script(session, dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
            dict(op='step'), {'op': 'step', 'count': 2, parameter: value},
        ]))
    assert not remote.calls


@pytest.mark.parametrize('parameter,value', [('count', 10001), ('count', True), ('timeout_ms', 600001), ('timeout_ms', True)])
def test_script_invalid_resolved_parameter_cannot_be_repaired_by_clamping(public_machine, parameter, value):
    session, remote = public_machine
    result = execute_script(session, dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        {'op': 'step', 'count': 2, parameter: '$bad'},
    ]), bindings={'bad': value})
    assert result['ok'] is False and result['completed_steps'] == 0
    assert not remote.calls
