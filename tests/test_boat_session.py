import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boat_session', ROOT / 'scripts/ci/boat-session.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)

WORKER = 'bx_test'
START = '2026-11-05T12:00:00+00:00'


def vm(state='running', **overrides):
    return {'sandbox': {'id': WORKER, 'snapshots': True, 'dataExpiredAt': None,
        'state': state, 'snapshotAvailable': True, 'lastSnapshotStatus': 'completed',
        'snapshotCompletedAt': '2026-11-05T12:01:00+00:00',
        'snapshotVerifiedAt': '2026-11-05T12:01:01+00:00', **overrides}}


def retention(**overrides):
    return {'enabled': False, 'snapshotsOff': False, **overrides}


def args(tmp_path):
    return SimpleNamespace(boat='boat', worker=WORKER, source='/home/user/src',
        output='/home/user/results', worker_receipt='/home/user/worker.json',
        commit='a' * 40, notify_script='/home/user/notify.py',
        notify_config='/home/user/config.json', timeout=1, ci_args=[],
        stop_timeout=1, receipt=tmp_path / 'receipt.json')


@pytest.mark.parametrize('info,settings', [
    (vm(snapshots=False), retention()), (vm(snapshots=None), retention()),
    (vm(id='bx_other'), retention()), (vm(dataExpiredAt='expired'), retention()),
    (vm(), retention(enabled=True)), (vm(), retention(snapshotsOff=True)),
    (vm(), {}),
])
def test_guard_rejects_unsafe_or_unknown(info, settings):
    with pytest.raises(ValueError):
        session.preservation_guard(info, settings, WORKER)


def test_stop_only_normal_then_verify(monkeypatch):
    calls = []
    states = iter([vm(), vm('stopping'), vm('stopped')])
    def cli(_boat, *command, **kwargs):
        calls.append(command)
        if command[0] == 'info': return next(states)
        if command[:2] == ('data-retention', 'status'): return retention()
        assert command == ('stop', WORKER)
        return {}
    monkeypatch.setattr(session, 'cli', cli)
    monkeypatch.setattr(session.time, 'sleep', lambda _: None)
    result = session.stop_and_verify('boat', WORKER, START)
    assert result['state'] == 'stopped'
    assert [c for c in calls if c[0] == 'stop'] == [('stop', WORKER)]
    assert not any(c[0] in ('resume', 'delete') or '--force' in c for c in calls)


def test_already_stopped_never_resumes_or_stops(monkeypatch):
    calls = []
    def cli(_boat, *command, **kwargs):
        calls.append(command)
        return retention() if command[0] == 'data-retention' else vm('stopped')
    monkeypatch.setattr(session, 'cli', cli)
    assert session.stop_and_verify('boat', WORKER, START)['state'] == 'stopped'
    assert all(c[0] not in ('stop', 'resume', 'delete') for c in calls)


@pytest.mark.parametrize('changes', [
    {'snapshotAvailable': False}, {'lastSnapshotStatus': 'failed'},
    {'snapshotVerifiedAt': None}, {'snapshotCompletedAt': '2026-11-05T11:59:00+00:00'},
    {'snapshotVerifiedAt': '2026-11-05T12:00:59+00:00'},
])
def test_stopped_requires_fresh_complete_snapshot(monkeypatch, changes):
    def cli(_boat, *command, **kwargs):
        return retention() if command[0] == 'data-retention' else vm('stopped', **changes)
    monkeypatch.setattr(session, 'cli', cli)
    with pytest.raises(ValueError):
        session.stop_and_verify('boat', WORKER, START)


@pytest.mark.parametrize('run_outcome,status,exit_code', [
    ('passed', 'passed', 0), ('failed', 'failed', 2),
    (RuntimeError('connection lost'), 'unconfirmed', 2),
    (KeyboardInterrupt(), 'unconfirmed', 2),
])
def test_whole_session_finalizes_and_stops_on_all_outcomes(monkeypatch, tmp_path, run_outcome, status, exit_code):
    calls = []
    a = args(tmp_path)
    def cli(_boat, *command, **kwargs):
        return retention() if command[0] == 'data-retention' else vm()
    def remote(_boat, _worker, config, action, timeout):
        calls.append(action)
        if action == 'check': return {'persistent_results': True, 'no_running_containers': True}
        if action == 'run':
            if isinstance(run_outcome, BaseException): raise run_outcome
            return {'ci_status': run_outcome}
        return {'result': {'ci_status': status}, 'persistent_results_flushed': True}
    def stop(*_args, **_kwargs):
        calls.append('stop')
        return {'state': 'stopped'}
    monkeypatch.setattr(session, 'cli', cli)
    monkeypatch.setattr(session, 'remote', remote)
    monkeypatch.setattr(session, 'stop_and_verify', stop)
    assert session.run_session(a) == exit_code
    receipt = json.loads(a.receipt.read_text())
    assert calls == ['check', 'run', 'finish', 'stop']
    assert receipt['ci_status'] == status
    assert receipt['stop_status'] == 'stopped-snapshot-verified'


def test_unsafe_retention_refuses_before_remote_work(monkeypatch, tmp_path):
    calls = []
    def cli(_boat, *command, **kwargs):
        calls.append(command)
        return retention(enabled=True) if command[0] == 'data-retention' else vm()
    monkeypatch.setattr(session, 'cli', cli)
    monkeypatch.setattr(session, 'remote', lambda *_a, **_k: pytest.fail('remote work attempted'))
    with pytest.raises(ValueError): session.run_session(args(tmp_path))
    assert not any(c[0] in ('stop', 'resume', 'delete') for c in calls)


def test_stopped_session_is_never_resumed(monkeypatch, tmp_path):
    def cli(_boat, *command, **kwargs):
        assert command[0] not in ('resume', 'stop', 'delete')
        return retention() if command[0] == 'data-retention' else vm('stopped')
    monkeypatch.setattr(session, 'cli', cli)
    monkeypatch.setattr(session, 'remote', lambda *_a, **_k: pytest.fail('remote work attempted'))
    with pytest.raises(ValueError): session.run_session(args(tmp_path))


def test_guest_runs_one_all_profile():
    assert "'--profile', 'all'" in session.GUEST
    assert "'--force'" not in session.GUEST


@pytest.mark.parametrize('finish', [RuntimeError('finalizer disconnected'),
                                   {'persistent_results_flushed': False,
                                    'result': {'ci_status': 'failed'}}])
def test_unconfirmed_preservation_blocks_stop_and_alerts(monkeypatch, tmp_path, finish):
    calls = []
    a = args(tmp_path)
    monkeypatch.setattr(session, 'cli', lambda _b, *c, **kw:
                        retention() if c[0] == 'data-retention' else vm())
    def remote(_boat, _worker, config, action, timeout):
        calls.append(action)
        if action == 'finish':
            if isinstance(finish, Exception): raise finish
            return finish
        if action == 'alert': return {'accepted_by_relay': True}
        return {'ci_status': 'failed'}
    monkeypatch.setattr(session, 'remote', remote)
    monkeypatch.setattr(session, 'stop_and_verify', lambda *_a, **_k: pytest.fail('unsafe stop'))
    assert session.run_session(a) == 2
    result = json.loads(a.receipt.read_text())
    assert calls == ['check', 'run', 'finish', 'alert']
    assert result['stop_status'] == 'blocked-results-not-finalized'
    assert result['shutdown_alert']['accepted_by_relay'] is True


def test_stop_failure_preserves_ci_result_and_alerts(monkeypatch, tmp_path):
    a = args(tmp_path)
    calls = []
    monkeypatch.setattr(session, 'cli', lambda _b, *c, **kw:
                        retention() if c[0] == 'data-retention' else vm())
    def remote(_boat, _worker, config, action, timeout):
        calls.append(action)
        if action == 'finish':
            return {'result': {'ci_status': 'passed', 'ci_exit_code': 0},
                    'persistent_results_flushed': True}
        if action == 'alert': return {'accepted_by_relay': True}
        return {'ci_status': 'passed'}
    monkeypatch.setattr(session, 'remote', remote)
    def stop(*a, **kw): raise TimeoutError('snapshot pending')
    monkeypatch.setattr(session, 'stop_and_verify', stop)
    assert session.run_session(a) == 2
    result = json.loads(a.receipt.read_text())
    assert result['ci_status'] == 'passed'
    assert result['stop_status'] == 'unconfirmed'
    assert result['ci_result']['ci_exit_code'] == 0
    assert calls[-1] == 'alert'


def test_stop_response_failure_is_read_back_without_replay(monkeypatch):
    calls = []
    states = iter([vm(), vm('stopped')])
    def cli(_boat, *command, **kwargs):
        calls.append(command)
        if command[0] == 'info': return next(states)
        if command[0] == 'data-retention': return retention()
        raise RuntimeError('response lost')
    monkeypatch.setattr(session, 'cli', cli)
    assert session.stop_and_verify('boat', WORKER, START)['state'] == 'stopped'
    assert [c for c in calls if c[0] == 'stop'] == [('stop', WORKER)]


def test_snapshot_between_start_and_finalization_does_not_qualify(monkeypatch):
    def cli(_boat, *command, **kwargs):
        return retention() if command[0] == 'data-retention' else vm('stopped')
    monkeypatch.setattr(session, 'cli', cli)
    with pytest.raises(ValueError, match='fresh resumable snapshot'):
        session.stop_and_verify('boat', WORKER, '2026-11-05T12:02:00+00:00')


def test_guest_code_compiles_and_cli_rejects_single_phase_before_boat(tmp_path):
    import subprocess
    import sys
    compile(session.GUEST, '<boat-guest>', 'exec')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/ci/boat-session.py'),
        '--worker', WORKER, '--source', '/home/user/src', '--output', '/home/user/results',
        '--worker-receipt', '/home/user/worker.json', '--commit', 'a'*40,
        '--receipt', str(tmp_path / 'unused.json'), '--', '--profile', 'ordinary'],
        capture_output=True, text=True)
    assert result.returncode == 2
    assert 'profile is always all' in result.stderr
    assert not (tmp_path / 'unused.json').exists()


def test_low_level_whole_run_requires_lifecycle_controller(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('boat_low_level', ROOT / 'scripts/ci/boat-linux.py')
    low = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(low)
    monkeypatch.delenv('FDISBULL_BOAT_SESSION_ID', raising=False)
    monkeypatch.setattr('sys.argv', ['boat-linux.py', '--source', str(tmp_path),
        '--output', str(tmp_path / 'out'), '--worker-receipt', str(tmp_path / 'worker.json'),
        '--profile', 'all'])
    monkeypatch.setattr(low, 'execute', lambda *_: pytest.fail('unprotected CI launch'))
    with pytest.raises(SystemExit) as exc:
        low.main()
    assert exc.value.code == 2
