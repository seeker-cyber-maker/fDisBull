"""Shutdown success requires a completed guest stop and a clean owned process."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from fdisbull.debugger import DebugSession, DebugWorkspace
from fdisbull.dosbox_rpc import DOSBoxRPC, DebuggerError
from fdisbull.project import Project


def session(*, stop_error=None, terminal=None, returncode=0, cleanup_error=None):
    events, calls = [], []
    debug = SimpleNamespace(closed=False, close_receipt=None, run_id='owned',
        _frame_timeline={}, _keyboard_leases={}, _launch_alias=None,
        _timeline_lock=threading.RLock())

    def call(method, params=None):
        calls.append(method)
        if stop_error is not None:
            raise stop_error
        return ({'operation_id': 'stop'} if method == 'session.stop' else
                deepcopy(terminal or {'state': 'exited', 'running': False}))

    def close():
        calls.append('rpc.close')
        if cleanup_error is not None:
            raise cleanup_error

    debug.call = call
    debug.rpc = SimpleNamespace(close=close, process=SimpleNamespace(poll=lambda: returncode),
        close_evidence={'native_log': {'tail': 'authored diagnostic', 'truncated': False}})
    debug._invalidate_runtime_bindings = lambda: calls.append('invalidate')
    debug._event = lambda name, result: events.append((name, deepcopy(result)))
    project = SimpleNamespace(path=Path('/private/shutdown-test.fdb'),
        transaction=lambda write: nullcontext(),
        db=SimpleNamespace(execute=lambda *args: calls.append('update')),
        _live_debuggers=[debug], __exit__=lambda *args: calls.append('project.close'))
    debug.project = project
    return debug, calls, events


def test_success_is_retained_and_repeated_close_does_not_send_stop_again():
    debug, calls, events = session()
    result = DebugSession.close(debug)
    assert result['status'] == 'closed' and result['closed'] is True
    assert result['guest_stop_complete'] and result['process_reaped']
    assert result['process_returncode'] == 0 and result['termination_signal'] is None
    assert debug.closed and debug.project._live_debuggers == []
    assert events[-1][1] == result
    previous = list(calls)
    result['state'] = 'caller mutation'
    repeated = DebugSession.close(debug)
    assert repeated['state'] == 'exited' and calls == previous


@pytest.mark.parametrize('returncode', [0, -6, None])
def test_lost_stop_is_never_closed_even_if_the_process_was_reaped(returncode):
    debug, calls, events = session(stop_error=OSError('Emulator closed the RPC channel'), returncode=returncode)
    with pytest.raises(DebuggerError, match='shutdown') as raised:
        DebugSession.close(debug)
    result = debug.close_receipt
    assert raised.value.receipt == result
    assert result['status'] == result['state'] == 'interrupted'
    assert result['closed'] is False and result['guest_stop_complete'] is False
    assert result['process_reaped'] is (returncode is not None)
    assert result['process_returncode'] == returncode
    assert result['termination_signal'] == (6 if returncode == -6 else None)
    assert 'diagnostics' in result
    assert debug.closed and events[-1][1] == result
    previous = list(calls)
    with pytest.raises(DebuggerError) as again:
        DebugSession.close(debug)
    assert again.value.receipt == result and calls == previous


def test_successful_guest_stop_does_not_hide_abnormal_host_exit():
    debug, _, events = session(returncode=-6)
    with pytest.raises(DebuggerError):
        DebugSession.close(debug)
    result = events[-1][1]
    assert result['guest_stop_complete'] is True
    assert result['closed'] is False and result['status'] == 'interrupted'
    assert result['process_returncode'] == -6 and result['termination_signal'] == 6


def test_running_stop_and_cleanup_error_are_not_success():
    debug, _, events = session(terminal={'state': 'running', 'running': True},
                               cleanup_error=RuntimeError('native cleanup failed'))
    with pytest.raises(RuntimeError, match='native cleanup failed'):
        DebugSession.close(debug)
    assert debug.close_receipt['closed'] is False
    assert events[-1][1]['cleanup_errors'][0]['phase'] == 'rpc.close'


@pytest.mark.parametrize('lost', [False, True])
def test_public_debug_stop_returns_actual_receipt_and_drops_terminal_ownership(lost):
    debug, calls, _ = session(stop_error=OSError('stop reply lost') if lost else None)
    debug.close = lambda: DebugSession.close(debug)
    workspace = DebugWorkspace()
    workspace.sessions['owned'] = debug
    result = workspace.invoke('debug-stop', debug.project.path, {'run': 'owned'})
    assert result['closed'] is (not lost)
    assert result['status'] == ('interrupted' if lost else 'closed')
    assert result['receipt'] == debug.close_receipt
    assert workspace.sessions == {} and calls.count('project.close') == 1


def test_project_cleanup_attempts_every_owner_when_an_earlier_close_fails():
    calls = []

    def fail():
        calls.append('first')
        raise RuntimeError('first cleanup failed')

    project = SimpleNamespace(_live_debuggers=[SimpleNamespace(close=fail),
        SimpleNamespace(close=lambda: calls.append('second'))],
        db=SimpleNamespace(close=lambda: calls.append('database')))
    with pytest.raises(RuntimeError, match='first cleanup failed'):
        Project.__exit__(project)
    assert calls == ['first', 'second', 'database']


@pytest.mark.parametrize('prefix', ['authored prefix\n', '\u00ff\ufffd'])
def test_rpc_retains_bounded_log_and_exit_status_before_temporary_cleanup(tmp_path, prefix):
    log = tmp_path/'emulator.log'
    log.write_text(prefix*9000 + 'authored fatal cleanup message\n')
    rpc = object.__new__(DOSBoxRPC)
    rpc.reader = rpc.writer = None
    rpc.process = SimpleNamespace(poll=lambda: -6, wait=lambda **kw: -6)
    rpc.temporary = SimpleNamespace(name=str(tmp_path), cleanup=lambda: log.unlink())
    rpc.close()
    assert not log.exists()
    evidence = rpc.close_evidence
    assert evidence['process_returncode'] == -6 and evidence['process_reaped']
    assert len(evidence['native_log']['tail'].encode()) <= 8192
    assert evidence['native_log']['tail'].endswith('authored fatal cleanup message\n')
    assert evidence['native_log']['truncated'] is True


def test_workspace_close_releases_all_projects_after_a_shutdown_failure():
    workspace = DebugWorkspace()
    failed, calls, _ = session(stop_error=OSError('stop channel lost'))
    failed.close = lambda: DebugSession.close(failed)
    clean, later_calls, _ = session()
    clean.close = lambda: DebugSession.close(clean)
    workspace.sessions = {'failed': failed, 'later': clean}
    with pytest.raises(DebuggerError):
        workspace.close()
    assert workspace.sessions == {}
    assert calls.count('project.close') == later_calls.count('project.close') == 1
    assert clean.close_receipt['closed'] and failed.close_receipt['closed'] is False


def test_context_cleanup_preserves_an_existing_body_exception():
    debug, _, _ = session(stop_error=OSError('stop channel lost'))
    debug.close = lambda: DebugSession.close(debug)
    body_error = RuntimeError('original body failed')
    assert DebugSession.__exit__(debug, RuntimeError, body_error, None) is None
    assert debug.close_receipt['status'] == 'interrupted' and debug.closed
