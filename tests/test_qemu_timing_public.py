"""Public routing, whole-script admission and budgets for timing controls."""
from copy import deepcopy
import time

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineContext
from test_qemu_io_public import raw_project, stopped_session


ROUTES = {
    'retrace-wait': ('retrace_wait', {'edge': 'exit', 'timeout_ms': 150}),
    'clock-sync-start': ('clock_sync_start', {'max_lag_ns': 20_000_000, 'timeout_ms': 150}),
    'clock-sync-observe': ('clock_sync_observe', {'timeout_ms': 150}),
    'clock-sync-step': ('clock_sync_step', {'timeout_ms': 150}),
    'clock-sync-stop': ('clock_sync_stop', {'timeout_ms': 150}),
}


def script(*steps):
    return dict(format='fdisbull-script-1', backend='qemu-machine', steps=list(steps))


def test_timing_controls_are_exposed_through_public_catalogs():
    for operation, (method, _) in ROUTES.items():
        assert 'debug-' + operation in METHODS
        assert OPERATIONS[operation] == method
        assert callable(getattr(MachineContext, method))


@pytest.mark.parametrize('operation', ROUTES)
def test_json_routes_preserve_explicit_timing_arguments(raw_project, tmp_path, operation):
    session, peer = stopped_session(raw_project, tmp_path)
    method, options = ROUTES[operation]
    calls = []
    def invoke(**parameters):
        calls.append(parameters)
        return dict(route=operation, observed=True)
    setattr(session, method, invoke)
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    try:
        response = respond(dict(id=19, method='debug-' + operation,
            params=dict(project=str(raw_project.path), run=session.run_id,
                        context='machine', **options)), debugger=workspace)
        assert response['ok'], response
        assert response['result'] == dict(route=operation, observed=True)
        assert calls == [options] and peer.calls == []
    finally:
        workspace.sessions.clear()
        session.close()


@pytest.mark.parametrize('operation', ROUTES)
def test_unselected_timing_capability_refuses_script_before_earlier_write(
        raw_project, tmp_path, operation):
    session, peer = stopped_session(raw_project, tmp_path)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    with pytest.raises(ValueError, match='(retrace|clock).*profile'):
        execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                       dict(op=operation)))
    assert not writes and not peer.calls


@pytest.mark.parametrize('operation,options', [
    ('retrace-wait', {'edge': 'vblank'}),
    ('retrace-wait', {'edge': True}),
    ('retrace-wait', {'timeout_ms': 0}),
    ('clock-sync-start', {'tolerance_ns': -1}),
    ('clock-sync-start', {'max_lag_ns': True}),
    ('clock-sync-start', {'max_wait_ns': 60_000_000_001}),
    ('clock-sync-start', {'tolerance_ns': '$saved.value', 'max_lag_ns': 0}),
    ('clock-sync-observe', {'timeout_ms': False}),
    ('clock-sync-step', {'timeout_ms': 600001}),
    ('clock-sync-stop', {'timeout_ms': 1.5}),
])
def test_malformed_literal_refuses_whole_script_before_execution(
        raw_project, tmp_path, operation, options):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities.update(retrace_wait=True, host_clock_sync=True)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    route = script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                   dict(op=operation, **options))
    with pytest.raises((ValueError, TypeError)):
        validate_script(route)
    with pytest.raises((ValueError, TypeError)):
        execute_script(session, route)
    assert not writes and not peer.calls


@pytest.mark.parametrize('operation', ROUTES)
def test_timing_script_refuses_caller_transaction_before_an_earlier_write(
        raw_project, tmp_path, operation):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities.update(retrace_wait=True, host_clock_sync=True)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    raw_project.db.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='transaction'):
            execute_script(session, script(dict(op='write-memory', address=0x7c00, data_hex='90'),
                                           dict(op=operation)))
        assert not writes and not peer.calls
    finally:
        raw_project.db.rollback()


def test_sync_start_and_step_share_one_script_budget(raw_project, tmp_path, monkeypatch):
    session, peer = stopped_session(raw_project, tmp_path)
    session.capabilities['host_clock_sync'] = True
    now, calls = [100.0], []
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    def start(**options):
        calls.append(('start', options))
        now[0] += .030
        return dict(token='owned-token', state='active')
    def step(**options):
        calls.append(('step', options))
        return dict(token='owned-token', state='active')
    session.clock_sync_start, session.clock_sync_step = start, step
    result = execute_script(session, script(dict(op='clock-sync-start', timeout_ms=1000),
                                           dict(op='clock-sync-step', timeout_ms=1000)),
                            timeout_ms=100)
    assert result['ok'], result
    assert [name for name, _ in calls] == ['start', 'step']
    assert 99 <= calls[0][1]['timeout_ms'] <= 100
    assert 69 <= calls[1][1]['timeout_ms'] <= 70
    assert not peer.calls


def test_standard_profile_capabilities_do_not_claim_timing_control(raw_project, tmp_path):
    session, _ = stopped_session(raw_project, tmp_path)
    assert session.capabilities['host_clock_sync'] is False
    assert session.capabilities['retrace_wait'] is False
    assert session.capabilities['completed_guest_frames'] is False
    assert session.capabilities['timed_input'] is False


@pytest.mark.parametrize('change', [
    {'outcome': 'breakpoint'}, {'timed_out': True}, {'process': {'state': 'exited'}},
    {'clock_budget': {'deadline_reached': False}},
    {'stop': {'trigger': 'guest_tsr', 'context': 'dos-process'}},
    {'reason': {'kind': 'watchpoint'}}, {'reason': {'breakpoint_ids': ['owned-bp']}},
    {'reason': {'classification_complete': False}},
    {'reason': {'native_reply': 'T02watch:1234;thread:1;'}},
    {'reason': {'native_reply': 'T02thread:1;swbreak:;'}},
    {'reason': {'native_reply': 'T05thread:1;'}},
])
def test_fired_timer_does_not_override_another_stop_cause(change):
    from fdisbull.qemu_clock import clock_timer_stop_is_ordinary
    ordinary = dict(outcome='stopped', timed_out=False, clock_budget=dict(deadline_reached=True),
                    session=dict(state='stopped', stop_reason=dict(kind='stopped', breakpoint_ids=[],
                                                                   native_reply='T02thread:1;')))
    assert clock_timer_stop_is_ordinary(ordinary)
    altered = deepcopy(ordinary)
    if 'reason' in change:
        altered['session']['stop_reason'].update(change['reason'])
    else:
        altered.update(change)
    assert not clock_timer_stop_is_ordinary(altered)
    assert clock_timer_stop_is_ordinary(ordinary), 'Classification mutated the original receipt'


def test_active_dos_process_does_not_hide_an_ordinary_timer_stop():
    from fdisbull.qemu_clock import clock_timer_stop_is_ordinary
    execution = dict(outcome='stopped', timed_out=False,
        clock_budget=dict(deadline_reached=True),
        session=dict(state='stopped', stop_reason=dict(kind='stopped', breakpoint_ids=[],
                                                      native_reply='T02thread:1;')),
        process=dict(state='active', termination=None))
    assert clock_timer_stop_is_ordinary(execution)
    execution['process']['termination'] = dict(kind='normal-exit')
    assert not clock_timer_stop_is_ordinary(execution)
