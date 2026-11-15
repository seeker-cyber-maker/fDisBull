"""Public observation waits on measured native virtual time, without a VM.

The existing production QMP/clock envelope runs against its bounded wire peer;
only execution and selected memory are supplied at the native boundary. Real
project/event persistence and public routing are retained.
"""
import json
import uuid

import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace, stamp
from test_qemu_clock_budget import owned
from test_qemu_io_public import raw_project


OBS = {'counter': {'kind': 'memory', 'address': '0x7c00', 'length': 2}}
UNTIL = {'observation': 'counter', 'equals': '0100'}


@pytest.fixture
def waiting(owned, raw_project):
    o = owned
    s = o.context
    s.project, s.run_id = raw_project, uuid.uuid4().hex
    s.version, s.metadata = raw_project.version(), {'backend': 'qemu-dos'}
    s.closed = False
    s.memory = lambda address, length=16, space='physical': dict(
        context='machine', address=hex(int(address, 0) if isinstance(address, str) else address),
        space=space, length=length, hex=(1 if o.executions else 0).to_bytes(length, 'little').hex())
    with raw_project.transaction(True):
        raw_project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (s.run_id, s.version['id'], stamp(), None, 'stopped', json.dumps(s.metadata)))
    yield o


def test_public_wait_reaches_observed_value_and_persists_native_time(waiting):
    o = waiting
    workspace = DebugWorkspace()
    workspace.sessions[o.context.run_id] = o.context
    try:
        reply = respond(dict(method='debug-wait', params=dict(project=str(o.context.project.path),
            run=o.context.run_id, observations=OBS, until=UNTIL, guest_ms=10,
            slice_ms=1, timeout_ms=100, timeout_screenshot=None)), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert reply['ok'], reply
    result = reply['result']
    assert result['complete'] and result['matched'] and result['outcome'] == 'predicate'
    assert result['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert result['guest_elapsed_ns'] == 1_000_064
    assert result['guest_elapsed_ms'] == 1.000064
    assert result['clock_progress_complete']
    assert result['final_clock']['virtual_ns'] - result['initial_clock']['virtual_ns'] == result['guest_elapsed_ns']
    assert len(o.executions) == 1
    row = o.context.project.db.execute("SELECT evidence FROM debug_events WHERE operation='wait'").fetchone()
    assert json.loads(row[0])['guest_elapsed_ns'] == 1_000_064


def options(**changes):
    return dict(observations=OBS, until=UNTIL, guest_ms=10, slice_ms=1,
                timeout_ms=100, timeout_screenshot=None, **changes)


def route(parameters):
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-memory', address=0x7c00, data_hex='90', expected_hex='00'),
        dict(op='wait', **parameters)])


def test_true_initial_predicate_is_observational(waiting):
    o = waiting
    result = o.context.wait(**dict(options(), until={'observation': 'counter', 'equals': '0000'}))
    assert result['complete'] and result['matched'] and result['guest_elapsed_ns'] == 0
    assert not o.executions


def test_overshoot_cannot_satisfy_predicate_beyond_requested_budget(waiting):
    o = waiting
    result = o.context.wait(**dict(options(), guest_ms=1))
    assert result['outcome'] == 'guest_budget' and not result['complete']
    assert result['last_observation']['counter'] == '0100'
    assert result['guest_elapsed_ns'] == 1_000_064 and result['guest_budget_overshoot_ms'] > 0
    assert len(o.executions) == 1


def test_poll_budget_does_not_execute_an_extra_slice(waiting):
    o = waiting
    result = o.context.wait(**dict(options(), max_polls=1))
    assert result['outcome'] == 'poll_budget' and len(result['polls']) == 1
    assert not o.executions


def test_earlier_native_stop_wins_without_reading_post_stop_match(waiting):
    o = waiting
    o.early = True
    result = o.context.wait(**options())
    assert not result['complete'] and not result['matched']
    assert result['stop']['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert result['guest_elapsed_ns'] == 128
    assert result['last_observation']['counter'] == '0000' and len(result['polls']) == 1
    assert len(o.executions) == 1


def test_coincident_hook_and_timer_preserve_hook_and_exact_stop(waiting):
    o = waiting
    native = o.context._execute
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        result.update(outcome='hook', hook_hits=[{'hook': 'test'}])
        return result
    o.context._execute = execute
    result = o.context.wait(**options())
    assert result['outcome'] == 'hook' and not result['matched']
    assert result['stop']['clock_budget']['deadline_reached'] is True
    assert result['stop']['hook_hits'] == [{'hook': 'test'}]
    assert len(result['polls']) == len(o.executions) == 1


@pytest.mark.parametrize('stop', ['guest_exit', 'guest_tsr', 'exited', 'timeout', 'watchpoint'])
def test_nonordinary_stop_is_not_replaced_by_a_later_observation(waiting, stop):
    o = waiting
    native = o.context._execute
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        result['outcome'] = stop
        return result
    o.context._execute = execute
    result = o.context.wait(**options())
    assert result['outcome'] == stop and not result['matched'] and not result['complete']
    assert result['stop']['outcome'] == stop and len(result['polls']) == len(o.executions) == 1


@pytest.mark.parametrize('change', [
    {'fast_forward': True}, {'fast_forward': 0}, {'guest_ms': 0}, {'slice_ms': 0},
    {'max_polls': 0}, {'timeout_ms': False},
    {'observations': {'m': {'kind': 'memory', 'address': True, 'length': 1}}},
    {'observations': {'m': {'kind': 'memory', 'address': -1, 'length': 1}}},
    {'observations': {'m': {'kind': 'memory', 'address': '0x100000000', 'length': 1}}},
    {'observations': {'m': {'kind': 'memory', 'address': 0xffffffff, 'length': 2}}},
    {'observations': {'m': {'kind': 'memory', 'address': 1.5, 'length': 1}}},
    {'observations': {'m': {'kind': 'memory', 'address': '0x100', 'cs': 0x123, 'length': 1}}},
    {'observations': {'m': {'kind': 'memory', 'address': '0x100', 'space': 'linear', 'length': 1}}},
])
def test_invalid_options_refuse_direct_and_entire_script_before_effects(waiting, change):
    o = waiting
    writes = []
    o.context.write_memory = lambda *args, **kw: writes.append((args, kw))
    value = dict(options(), **change)
    for operation in (lambda: o.context.wait(**value), lambda: validate_script(route(value)),
                      lambda: execute_script(o.context, route(value))):
        with pytest.raises((ValueError, TypeError)):
            operation()
    assert not writes and not o.wire.calls and not o.executions


@pytest.mark.parametrize('profile', ['standard', 'instruction'])
def test_unsupported_clock_refuses_before_any_native_io_or_script_write(waiting, profile):
    o = waiting
    o.vm.machine_configuration['clock_profile']['profile'] = profile
    writes = []
    o.context.write_memory = lambda *a, **kw: writes.append(a)
    with pytest.raises(ValueError, match='virtual clock profile'):
        o.context.wait(**options())
    with pytest.raises(ValueError, match='virtual clock profile'):
        execute_script(o.context, route(options()))
    assert not o.wire.calls and not o.executions and not writes


def test_script_refuses_active_caller_transaction_before_earlier_write(waiting):
    o = waiting
    writes = []
    o.context.write_memory = lambda *a, **kw: writes.append(a)
    o.context.project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(o.context, route(options()))
    finally:
        o.context.project.db.rollback()
    assert not writes and not o.wire.calls and not o.executions


def test_supported_saved_script_uses_same_wait_and_stops_on_incomplete(waiting):
    o = waiting
    route = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='wait', **options(), **{'as': 'ready'}),
        dict(op='assert', value='$ready.guest_elapsed_ns', equals=1_000_064)])
    result = execute_script(o.context, route)
    assert result['ok'], result
    assert len(o.executions) == 1


def test_missing_observation_stops_before_execution_even_with_any_predicate(waiting):
    o = waiting
    result = o.context.wait(**dict(options(), observations=dict(OBS, missing={
        'kind': 'register', 'path': 'registers.unavailable'}),
        until={'any': [{'observation': 'counter', 'equals': '0000'}, UNTIL]}))
    assert result['outcome'] == 'incomplete' and not result['complete']
    assert 'unavailable' in result['error']['message'] and not o.executions


def test_register_and_status_numeric_predicates_share_one_poll(waiting):
    o = waiting
    o.context.registers = lambda: dict(linear_pc='0x7c00', cpu_mode='real', registers={'eax': hex(len(o.executions))})
    o.context.status = lambda: dict(counter=len(o.executions))
    result = o.context.wait(**dict(options(), observations={
        'ax': {'kind': 'register', 'path': 'registers.eax'},
        'status': {'kind': 'status', 'path': 'counter'}}, until={'all': [
            {'observation': 'ax', 'equals': 1, 'mask': 0xffff},
            {'observation': 'status', 'greater_than_initial': True}]}))
    assert result['matched'] and result['last_observation'] == {'ax': 1, 'status': 1}


def test_restore_epoch_change_withdraws_wait_before_a_matching_poll(waiting):
    o = waiting
    native = o.context._execute
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        o.context._runtime_epoch = 'new-restore-epoch'
        return result
    o.context._execute = execute
    result = o.context.wait(**options())
    assert result['outcome'] == 'incomplete' and not result['matched']
    assert 'epoch changed' in result['error']['message']
    assert len(result['polls']) == len(o.executions) == 1


def test_virtual_address_context_change_does_not_match_new_mapping(waiting):
    o = waiting
    o.context.registers = lambda: dict(linear_pc='0x7c00', cpu_mode='protected', registers={}, address_state=dict(machine_vcpus=1,
        register_context_match=True, cpu_mode='protected', paging=True,
        paging_mode='legacy-32', a20=True, control={'CR3': hex(0x1000 * len(o.executions))}))
    result = o.context.wait(**dict(options(), observations={'counter': dict(OBS['counter'], space='virtual')}))
    assert result['outcome'] == 'incomplete' and not result['matched']
    assert 'virtual address context changed' in result['error']['message'] and len(o.executions) == 1


def test_publication_failure_preserves_arrived_stop_and_secondary_cleanup(waiting):
    o = waiting
    event = o.context._event
    primary = OSError('wait journal refused')
    def fail(operation, value):
        if operation == 'wait':
            raise primary
        return event(operation, value)
    o.context._event = fail
    o.vm.close = lambda: (_ for _ in ()).throw(RuntimeError('owned cleanup failed'))
    with pytest.raises(OSError) as caught:
        o.context.wait(**options())
    assert caught.value is primary and primary.result is primary.wait_result
    assert primary.result['runs'][0]['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert primary.wait_cleanup_error == 'RuntimeError' and o.vm._fdisbull_control_quarantine
    count = len(o.executions)
    with pytest.raises(Exception, match='quarantined'):
        o.context.run(timeout_ms=10)
    assert len(o.executions) == count


def test_native_failure_keeps_existing_error_result(waiting):
    o = waiting
    arrived = dict(outcome='stopped', native_reply='T05')
    primary = OSError('native reply read failed')
    primary.result = arrived
    def fail(*args, **kwargs):
        raise primary
    o.context._clock_advance_with_hooks = fail
    with pytest.raises(OSError) as caught:
        o.context.wait(**options())
    assert caught.value is primary and primary.result is arrived
    assert primary.wait_result['polls'] and not primary.wait_result['complete']
    assert o.vm.closed


def test_expired_inherited_deadline_refuses_before_native_dispatch(waiting):
    o = waiting
    o.context._rpc_deadline = o.clock.now
    with pytest.raises(TimeoutError, match='deadline'):
        o.context.wait(**options())
    assert not o.wire.calls and not o.executions


def test_inherited_transport_deadlines_never_widen_and_are_restored(waiting):
    o = waiting
    original = (o.clock.now + .08, o.clock.now + .07, o.clock.now + .06)
    o.vm.operation_deadline, o.qmp.operation_deadline, o.remote.operation_deadline = original
    result = o.context.wait(**dict(options(), timeout_ms=1000))
    assert result['complete'] and o.executions[0][2] == original[-1]
    assert (o.vm.operation_deadline, o.qmp.operation_deadline, o.remote.operation_deadline) == original


def test_mid_poll_deadline_closes_without_execution_or_false_success(waiting):
    o = waiting
    o.wire.latency = .04
    with pytest.raises(TimeoutError) as caught:
        o.context.wait(**options())
    assert not o.executions and o.vm.closed
    assert caught.value.wait_result['complete'] is False


def test_pending_internal_stop_is_not_ignored_by_a_true_initial_predicate(waiting):
    o = waiting
    o.context._automatic_internal_pending = {'result': {'outcome': 'tracking-budget'}}
    result = o.context.wait(**dict(options(), until={'observation': 'counter', 'equals': '0000'}))
    assert result['outcome'] == 'pending_stop' and not result['matched']
    assert not result['polls'] and not o.executions


def test_clock_final_read_failure_preserves_actual_closed_native_exit(waiting):
    o = waiting
    native = o.context._execute
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        result.update(outcome='guest_exit', process={'state': 'exited', 'termination': {'code': 0}})
        o.vm.close()
        return result
    o.context._execute = execute
    with pytest.raises(Exception, match='closed before its native clock budget') as caught:
        o.context.wait(**options())
    assert caught.value.result['outcome'] == 'guest_exit'
    assert caught.value.result['process']['termination']['code'] == 0
    assert caught.value.wait_result['complete'] is False and len(o.executions) == 1
    assert caught.value.wait_result['clock_progress_complete'] is False


def test_epoch_boundary_does_not_capture_a_diagnostic_from_replacement_context(waiting):
    o = waiting
    native = o.context._execute
    diagnostics = []
    o.context.screenshot = lambda *a, **kw: diagnostics.append(a)
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        o.context._runtime_epoch = 'replacement'
        return result
    o.context._execute = execute
    result = o.context.wait(**dict(options(), timeout_screenshot='wait-timeout.png'))
    assert result['outcome'] == 'incomplete' and not diagnostics
    assert result['capture_epoch'] == o.context.run_id and not result['matched']
