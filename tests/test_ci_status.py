"""Finite CI observations enforce a shared budget without contacting GitHub/GitLab."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ci_status.py'
SPEC = importlib.util.spec_from_file_location('ci_status', SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
SHA = 'a' * 40
OTHER = 'b' * 40
REPO = 'example/project'
GITLAB_REPO = 'brewster-jennings-group/fdisbull'


def response(sha=SHA, count=1, total=None):
    return dict(total_count=count if total is None else total, workflow_runs=[
        dict(id=100+i, workflow_id=20, name='Tests', event='push', status='completed',
             conclusion='success', run_attempt=1, head_sha=sha) for i in range(count)])


def gitlab_response(sha=SHA, count=1, status='success', source='merge_request_event'):
    return [
        dict(id=3000+i, iid=40+i, sha=sha, ref='main', status=status, source=source)
        for i in range(count)
    ]


def check(tmp_path, *, now=1000, sha=SHA, refresh=True, owner='coordinator', fetch=None, **options):
    return gate.check_status(repo=REPO, sha=sha, state_dir=tmp_path, refresh=refresh,
                             owner=owner, clock=lambda: now, fetch=fetch, **options)


def forbidden(*args):
    pytest.fail('A provider request was not permitted')


def reserve(tmp_path, *, now=1000, owner='coordinator', **options):
    return gate.reserve_refresh(repo=REPO, host='github.com', owner=owner,
                                state_dir=tmp_path, clock=lambda: now, **options)


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    """A real child process receives exactly the CLI request the helper makes."""
    binary = tmp_path / 'bin'
    binary.mkdir()
    command = binary / 'gh'
    command.write_text(f'#!{sys.executable}\n' + '''
import json, os, sys, time
with open(os.environ['CI_TEST_CALLS'], 'a') as stream:
    time.sleep(float(os.environ.get('CI_TEST_PRE_WRITE_DELAY','0')))
    stream.write(json.dumps(sys.argv[1:])+'\\n')
time.sleep(float(os.environ.get('CI_TEST_DELAY','0')))
print(os.environ.get('CI_TEST_RESPONSE','{}'))
print(os.environ.get('CI_TEST_ERROR',''),file=sys.stderr)
raise SystemExit(int(os.environ.get('CI_TEST_EXIT','0')))
''')
    command.chmod(0o755)
    glab_cmd = binary / 'glab'
    glab_cmd.write_text(f'#!{sys.executable}\n' + '''
import json, os, sys, time
with open(os.environ['CI_TEST_CALLS'], 'a') as stream:
    time.sleep(float(os.environ.get('CI_TEST_PRE_WRITE_DELAY','0')))
    stream.write(json.dumps(['glab'] + sys.argv[1:])+'\\n')
time.sleep(float(os.environ.get('CI_TEST_DELAY','0')))
print(os.environ.get('CI_TEST_RESPONSE','[]'))
print(os.environ.get('CI_TEST_ERROR',''),file=sys.stderr)
raise SystemExit(int(os.environ.get('CI_TEST_EXIT','0')))
''')
    glab_cmd.chmod(0o755)
    calls = tmp_path / 'calls.jsonl'
    monkeypatch.setenv('PATH', str(binary) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('CI_TEST_CALLS', str(calls))
    monkeypatch.setenv('CI_TEST_RESPONSE', json.dumps(response()))
    return calls


def test_default_is_cache_only_and_refresh_requires_owner(tmp_path):
    row = check(tmp_path, refresh=False, owner=None, fetch=forbidden)
    assert row['status'] == 'missing' and row['source'] == 'none'
    assert row['refresh_reason'] == 'cache_only' and not row['refresh_performed']
    with pytest.raises(gate.StatusError, match='owner'):
        check(tmp_path, owner=None, fetch=forbidden)


def test_one_cli_read_is_exact_and_later_agents_use_the_same_cache(tmp_path, fake_gh):
    row = check(tmp_path)
    assert row['status'] == 'fresh' and row['qualification'] == 'observation_only'
    assert row['sha'] == SHA and row['owner'] == 'coordinator'
    assert row['observed_at'] == 1000 and row['next_refresh_at'] == 1300
    assert not any(k in row for k in ('passed', 'ready', 'qualified'))
    command = json.loads(fake_gh.read_text())
    assert command == ['api', '--hostname', 'github.com', '--method', 'GET',
                       f'repos/{REPO}/actions/runs?head_sha={SHA}&per_page=100']
    cached = check(tmp_path, now=1100, refresh=False, owner=None, fetch=forbidden)
    assert cached['status'] == 'cached' and cached['cache_age_seconds'] == 100
    assert cached['observed_at'] == 1000 and cached['runs'] == row['runs']
    throttled = check(tmp_path, now=1299, fetch=forbidden)
    assert throttled['refresh_reason'] == 'cooldown' and not throttled['refresh_performed']


def test_gitlab_host_uses_glab_api_and_normalizes_pipelines(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_RESPONSE', json.dumps(gitlab_response(SHA, count=1, status='success')))
    row = gate.check_status(repo=GITLAB_REPO, sha=SHA, host='gitlab.com', state_dir=tmp_path,
                            refresh=True, owner='coordinator', clock=lambda: 1000)
    assert row['status'] == 'fresh' and row['host'] == 'gitlab.com' and row['repo'] == GITLAB_REPO
    assert len(row['runs']) == 1
    assert row['runs'][0]['status'] == 'completed' and row['runs'][0]['conclusion'] == 'success'
    assert row['runs'][0]['head_sha'] == SHA
    command = json.loads(fake_gh.read_text())
    assert command == ['glab', 'api', '--hostname', 'gitlab.com', '--method', 'GET',
                       f'projects/brewster-jennings-group%2Ffdisbull/pipelines?sha={SHA}&per_page=100']


def test_retired_github_repository_blocks_before_spawning_gh(tmp_path, fake_gh):
    row = gate.check_status(repo='seeker-cyber-maker/fDisBull', sha=SHA, host='github.com',
                            state_dir=tmp_path, refresh=True, owner='coordinator', clock=lambda: 1000)
    assert row['status'] == 'error' and row['error'] == 'provider_retired_repository'
    assert row['provider_stop'] == {'reason': 'provider_retired_repository', 'observed_at': 1000}
    assert not fake_gh.exists()


def test_different_sha_cannot_bypass_repository_gate_or_read_other_sha_cache(tmp_path):
    check(tmp_path, fetch=lambda *_: response())
    row = check(tmp_path, sha=OTHER, now=1100, fetch=forbidden)
    assert row['sha'] == OTHER and row['status'] == 'missing' and row['runs'] == []
    assert row['refresh_reason'] == 'cooldown' and row['next_refresh_at'] == 1300
    row = check(tmp_path, sha=OTHER, now=1300, fetch=lambda *_: response(OTHER))
    assert row['status'] == 'fresh' and row['runs'][0]['head_sha'] == OTHER
    old = check(tmp_path, refresh=False, owner=None, fetch=forbidden)
    assert old['sha'] == SHA and old['runs'][0]['head_sha'] == SHA


def test_repository_owner_cannot_be_silently_replaced_after_cooldown(tmp_path):
    check(tmp_path, fetch=lambda *_: response())
    denied = check(tmp_path, now=1400, owner='other-agent', fetch=forbidden)
    assert denied['refresh_reason'] == 'owner_conflict' and denied['owner'] == 'coordinator'
    assert not denied['refresh_performed']
    resumed = check(tmp_path, now=1400, fetch=lambda *_: response())
    assert resumed['refresh_performed'] and resumed['next_refresh_at'] == 1700


def test_reserved_window_blocks_status_refresh_and_other_sha(tmp_path):
    reservation = reserve(tmp_path)
    assert reservation == {'allowed': True, 'reason': 'reserved',
                           'next_refresh_at': 1300, 'owner': 'coordinator'}
    same = check(tmp_path, fetch=forbidden)
    other = check(tmp_path, sha=OTHER, fetch=forbidden)
    assert same['refresh_reason'] == other['refresh_reason'] == 'cooldown'
    assert same['next_refresh_at'] == other['next_refresh_at'] == 1300


def test_status_refresh_reservation_blocks_batch_reservation(tmp_path):
    check(tmp_path, fetch=lambda *_: response())
    reservation = reserve(tmp_path, now=1100)
    assert reservation == {'allowed': False, 'reason': 'cooldown',
                           'next_refresh_at': 1300, 'owner': 'coordinator'}


def test_reservation_rejects_different_owner(tmp_path):
    reserve(tmp_path)
    denied = reserve(tmp_path, now=1400, owner='other-agent')
    assert denied == {'allowed': False, 'reason': 'owner_conflict',
                      'next_refresh_at': 1300, 'owner': 'coordinator'}


def test_provider_stop_is_persisted_for_owner_and_first_stop_is_preserved(tmp_path):
    reserve(tmp_path)
    recorded = gate.record_provider_stop(repo=REPO, host='github.com', owner='coordinator',
                                         reason='provider_http_429', state_dir=tmp_path,
                                         clock=lambda: 1050)
    assert recorded == {'recorded': True, 'reason': 'provider_stopped', 'owner': 'coordinator',
                        'provider_stop': {'reason': 'provider_http_429', 'observed_at': 1050}}
    preserved = gate.record_provider_stop(repo=REPO, host='github.com', owner='coordinator',
                                          reason='provider_restriction', state_dir=tmp_path,
                                          clock=lambda: 1060)
    assert not preserved['recorded'] and preserved['provider_stop'] == recorded['provider_stop']
    assert reserve(tmp_path, now=5000)['reason'] == 'provider_stopped'


def test_reservation_busy_and_invalid_clock_fail_closed(tmp_path):
    directory = gate._directory(tmp_path, 'github.com', REPO)
    with gate._locked(directory) as acquired:
        assert acquired
        denied = reserve(tmp_path)
    assert denied == {'allowed': False, 'reason': 'busy',
                      'next_refresh_at': None, 'owner': None}
    for invalid in (-1, float('nan'), float('inf'), True, '1000'):
        with pytest.raises(gate.StatusError, match='clock'):
            gate.reserve_refresh(repo=REPO, host='github.com', owner='coordinator',
                                 state_dir=tmp_path, clock=lambda value=invalid: value)


def test_provider_stop_requires_reserved_owner_and_never_replaces_other_owner(tmp_path):
    denied = gate.record_provider_stop(repo=REPO, host='github.com', owner='other-agent',
                                       reason='provider_restriction', state_dir=tmp_path,
                                       clock=lambda: 1000)
    assert denied['reason'] == 'owner_conflict' and not denied['recorded']
    reserve(tmp_path)
    denied = gate.record_provider_stop(repo=REPO, host='github.com', owner='other-agent',
                                       reason='provider_restriction', state_dir=tmp_path,
                                       clock=lambda: 1000)
    assert denied['reason'] == 'owner_conflict' and not denied['recorded']
    assert denied['provider_stop'] is None


@pytest.mark.parametrize('status', [401, 403, 429])
def test_http_stop_survives_new_process_and_new_sha(tmp_path, fake_gh, monkeypatch, status):
    monkeypatch.setenv('CI_TEST_EXIT', '1')
    monkeypatch.setenv('CI_TEST_ERROR', f'gh: access unavailable (HTTP {status})')
    row = check(tmp_path)
    assert row['status'] == 'error' and row['error'] == f'provider_http_{status}'
    assert row['provider_stop']['reason'] == f'provider_http_{status}'
    # Reopening state after the interval must not probe even another head.
    row = check(tmp_path, now=5000, sha=OTHER, fetch=forbidden)
    assert row['refresh_reason'] == 'provider_stopped' and not row['refresh_performed']
    reopened = subprocess.run(cli(tmp_path, OTHER, '--refresh', '--owner', 'coordinator'),
                              capture_output=True, text=True)
    assert reopened.returncode == 1
    assert json.loads(reopened.stdout)['refresh_reason'] == 'provider_stopped'
    assert len(fake_gh.read_text().splitlines()) == 1


def test_confirmed_account_restriction_stops_without_raw_error_disclosure(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_EXIT', '1')
    monkeypatch.setenv('CI_TEST_ERROR', 'This account has been flagged. secret-value-must-not-escape')
    row = check(tmp_path)
    assert row['error'] == 'provider_restriction' and row['provider_stop']
    assert 'secret-value' not in json.dumps(row)
    check(tmp_path, now=2000, fetch=forbidden)


@pytest.mark.parametrize('phrase', ['owner marked spammy', 'Actions has been disabled for this user.'])
@pytest.mark.parametrize('channel', ['stderr', 'success_body'])
def test_observed_provider_restrictions_stop_even_without_401_403_or_429(tmp_path, fake_gh, monkeypatch, phrase, channel):
    if channel == 'stderr':
        monkeypatch.setenv('CI_TEST_EXIT', '1')
        monkeypatch.setenv('CI_TEST_ERROR', phrase + ' (HTTP 422)')
    else:
        monkeypatch.setenv('CI_TEST_RESPONSE', json.dumps({'message': phrase}))
    row = check(tmp_path)
    assert row['error'] == 'provider_restriction' and row['provider_stop']
    assert check(tmp_path, now=5000, fetch=forbidden)['refresh_reason'] == 'provider_stopped'
    assert len(fake_gh.read_text().splitlines()) == 1


def test_missing_authentication_stops_without_an_authentication_probe(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_EXIT', '4')
    monkeypatch.setenv('CI_TEST_ERROR', 'To get started with GitHub CLI, please run: gh auth login')
    row = check(tmp_path)
    assert row['error'] == 'provider_authentication_required' and row['provider_stop']
    assert check(tmp_path, now=2000, fetch=forbidden)['refresh_reason'] == 'provider_stopped'
    assert len(fake_gh.read_text().splitlines()) == 1


def test_bad_json_and_transient_command_failure_do_not_retry(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_RESPONSE', '{bad json')
    row = check(tmp_path)
    assert row['status'] == 'error' and row['error'] == 'invalid_provider_json'
    assert check(tmp_path, now=1100, fetch=forbidden)['refresh_reason'] == 'cooldown'
    monkeypatch.setenv('CI_TEST_EXIT', '1')
    monkeypatch.setenv('CI_TEST_ERROR', 'Upstream request failed (HTTP 500) private-unneeded-response')
    row = check(tmp_path, now=1300)
    assert row['error'] == 'provider_request_failed' and row['provider_stop'] is None
    assert 'private-unneeded' not in json.dumps(row)
    assert check(tmp_path, now=1400, fetch=forbidden)['refresh_reason'] == 'cooldown'
    assert len(fake_gh.read_text().splitlines()) == 2


def test_timeout_uses_fixed_bound_and_consumes_reservation(tmp_path, monkeypatch):
    calls = []
    def timeout(args, **options):
        calls.append((args, options))
        assert options['timeout'] == 30
        raise subprocess.TimeoutExpired(args, 30)
    monkeypatch.setattr(gate.subprocess, 'run', timeout)
    row = check(tmp_path)
    assert row['status'] == 'error' and row['error'] == 'provider_timeout'
    assert row['provider_stop'] is None and row['next_refresh_at'] == 1300
    assert check(tmp_path, now=1100, fetch=forbidden)['refresh_reason'] == 'cooldown'
    assert len(calls) == 1
    assert check(tmp_path, now=1300, fetch=lambda *_: response())['status'] == 'fresh'


def test_unexpected_crash_after_reservation_does_not_allow_immediate_retry(tmp_path):
    class Interrupted(BaseException):
        pass
    def crash(*args):
        state = json.loads(next(tmp_path.glob('*/state.json')).read_text())
        assert state['next_allowed_at'] == 1300 and state['owner'] == 'coordinator'
        raise Interrupted()
    with pytest.raises(Interrupted):
        check(tmp_path, fetch=crash)
    row = check(tmp_path, now=1100, fetch=forbidden)
    assert row['refresh_reason'] == 'cooldown' and row['status'] == 'missing'


@pytest.mark.parametrize('document,error', [
    ({}, 'invalid_provider_shape'),
    ({'workflow_runs': [], 'total_count': True}, 'invalid_provider_count'),
    (response(OTHER), 'provider_sha_mismatch'),
    (dict(total_count=2, workflow_runs=response(count=1)['workflow_runs']*2), 'invalid_provider_run_identity'),
])
def test_bad_provider_data_is_an_error_with_identity_and_cooldown(tmp_path, document, error):
    row = check(tmp_path, fetch=lambda *_: document)
    assert row['status'] == 'error' and row['error'] == error
    assert (row['host'], row['repo'], row['sha']) == ('github.com', REPO, SHA)
    assert row['runs'] == [] and row['next_refresh_at'] == 1300
    assert check(tmp_path, now=1100, fetch=forbidden)['refresh_reason'] == 'cooldown'


def test_page_limit_and_empty_result_remain_explicit(tmp_path):
    row = check(tmp_path, fetch=lambda *_: response(count=100, total=101))
    assert row['status'] == 'truncated' and row['total_count'] == 101 and len(row['runs']) == 100
    assert check(tmp_path, now=1100, refresh=False, owner=None)['status'] == 'truncated'
    row = check(tmp_path, now=1300, fetch=lambda *_: response(count=0))
    assert row['status'] == 'missing' and row['source'] == 'fresh' and row['total_count'] == 0
    assert check(tmp_path, now=1400, refresh=False, owner=None)['source'] == 'cache'


def test_cache_identity_and_cooldown_corruption_fail_closed(tmp_path):
    check(tmp_path, fetch=lambda *_: response())
    file = next(tmp_path.glob('*/' + SHA + '.json'))
    cache = json.loads(file.read_text()); cache['sha'] = OTHER
    file.write_text(json.dumps(cache))
    with pytest.raises(gate.StatusError, match='identity'):
        check(tmp_path, now=1400, fetch=forbidden)
    cache['sha'] = SHA; cache['runs'][0]['head_sha'] = OTHER
    file.write_text(json.dumps(cache))
    with pytest.raises(gate.StatusError, match='shape mismatch'):
        check(tmp_path, now=1400, fetch=forbidden)
    file.unlink()
    state = next(tmp_path.glob('*/state.json'))
    state.write_text('{broken')
    with pytest.raises(gate.StatusError, match='unreadable'):
        check(tmp_path, now=1400, fetch=forbidden)
    state.write_text('{}')
    with pytest.raises(gate.StatusError, match='identity mismatch'):
        check(tmp_path, now=1400, fetch=forbidden)


def test_clock_rollback_preserves_gate_and_marks_cache_age_uncertain(tmp_path):
    check(tmp_path, fetch=lambda *_: response())
    row = check(tmp_path, now=900, fetch=forbidden)
    assert row['refresh_reason'] == 'cooldown' and row['next_refresh_at'] == 1300
    assert row['clock_skew_detected'] and row['cache_age_seconds'] == 0


@pytest.mark.parametrize('options', [dict(sha='abc'), dict(sha='z'*40), dict(repo='owner/repo/extra'),
                                    dict(host='https://github.com'), dict(owner='')])
def test_invalid_selectors_make_no_provider_call(tmp_path, options):
    values = dict(repo=REPO, sha=SHA, owner='owner', refresh=True, state_dir=tmp_path, fetch=forbidden)
    values.update(options)
    with pytest.raises(gate.StatusError):
        gate.check_status(**values)


def test_cli_validation_error_keeps_requested_identity_and_never_runs_gh(tmp_path, fake_gh):
    result = subprocess.run(cli(tmp_path, 'short', '--refresh', '--owner', 'coordinator'),
                            capture_output=True, text=True)
    row = json.loads(result.stdout)
    assert result.returncode == 1 and row['status'] == 'error'
    assert (row['host'], row['repo'], row['sha']) == ('github.com', REPO, 'short')
    assert not row['refresh_performed'] and not fake_gh.exists()


def test_git_common_directory_is_shared_by_gitfile_checkouts(tmp_path):
    repository = tmp_path / 'repository'; repository.mkdir()
    subprocess.run(['git', 'init', '-q', str(repository)], check=True)
    other = tmp_path / 'other-checkout'; other.mkdir()
    # No commits are created: a gitfile points to this disposable unborn repo.
    (other / '.git').write_text('gitdir: ' + str(repository / '.git') + '\n')
    assert gate.default_state_dir(repository) == gate.default_state_dir(other)
    assert gate.default_state_dir(repository) == repository / '.git/fdisbull-ci-status'


def cli(state, sha=SHA, *extra):
    return [sys.executable, str(SCRIPT), '--repo', REPO, '--sha', sha,
            '--state-dir', str(state), *extra]


def test_concurrent_processes_share_one_refresh_and_sequential_calls_stay_cached(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_DELAY', '.25')
    state = tmp_path / 'shared-state'
    processes = [subprocess.Popen(cli(state, SHA, '--refresh', '--owner', 'coordinator'),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
    receipts = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        receipts.append(json.loads(stdout))
    assert sum(r['refresh_performed'] for r in receipts) == 1
    again = subprocess.run(cli(state, SHA, '--refresh', '--owner', 'coordinator'),
                           capture_output=True, text=True, check=True)
    assert json.loads(again.stdout)['refresh_reason'] == 'cooldown'
    assert len(fake_gh.read_text().splitlines()) == 1


def test_process_death_releases_lock_but_preserves_pre_io_reservation(tmp_path, fake_gh, monkeypatch):
    monkeypatch.setenv('CI_TEST_DELAY', '10')
    # Exercise the observed schedule where creation precedes the flushed entry.
    monkeypatch.setenv('CI_TEST_PRE_WRITE_DELAY', '.2')
    state = tmp_path / 'crash-state'
    process = subprocess.Popen(cli(state, SHA, '--refresh', '--owner', 'coordinator'),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if fake_gh.exists() and fake_gh.read_text().endswith('\n'):
                break
            time.sleep(.01)
        assert fake_gh.exists() and fake_gh.read_text().endswith('\n'), (
            'The fake provider must have recorded a complete invocation after state was reserved')
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        again = subprocess.run(cli(state, OTHER, '--refresh', '--owner', 'coordinator'),
                               capture_output=True, text=True, check=True)
        row = json.loads(again.stdout)
        assert row['status'] == 'missing' and row['refresh_reason'] == 'cooldown'
        assert not row['refresh_performed'] and len(fake_gh.read_text().splitlines()) == 1
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
