import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import time

from test_offline_qualification import record
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('production_qualification', ROOT / 'scripts/ci/production-qualification.py')
q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)


def git(path, *args): return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def fake_system_prepare(env, path):
    assert 'GITHUB_TOKEN' not in env and 'OTHER_SECRET' not in env
    path.write_bytes(b'prepared in fixture')
    return {'status':'passed','steps':[], 'capture_limit_bytes':q.MAX_LOG}


def repo(path):
    path.mkdir(); git(path, 'init', '-q'); git(path, 'config', 'user.name', 'Test'); git(path, 'config', 'user.email', 'test@example.invalid')
    (path / 'x').write_text('source'); git(path, 'add', '.'); git(path, 'commit', '-qm', 'fixture')
    return git(path, 'rev-parse', 'HEAD')


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    candidate, control, host = tmp_path/'candidate', tmp_path/'control', tmp_path/'host'
    sha, control_sha = repo(candidate), repo(control); (host/'42/1').mkdir(parents=True)
    env = {'GITHUB_REPOSITORY': q.REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_JOB': 'qualification',
           'RUNNER_NAME': 'fdisbull-ovh-ca-gh1', 'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_SHA': control_sha, 'GITHUB_REF_NAME': 'control', 'GITHUB_TOKEN': 'secret', 'OTHER_SECRET': 'secret'}
    run = {'id': 42, 'run_attempt': 1, 'head_sha': control_sha, 'head_branch': 'control', 'repository': {'full_name': q.REPO}}
    job = {'id': 30, 'run_id': 42, 'name': 'qualification', 'head_sha': control_sha, 'runner_id': 21, 'status': 'in_progress'}
    def request(path):
        if path.endswith('/attempts/1'): return run
        if '/attempts/1/jobs?' in path: return {'total_count': 1, 'jobs': [job]}
        if path.endswith('/jobs/30'): return job
        raise AssertionError(path)
    monkeypatch.setattr(q.platform, 'system', lambda: 'Linux'); monkeypatch.setattr(q.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(q.shutil, 'disk_usage', lambda p: SimpleNamespace(free=50_000_000_000))
    monkeypatch.setattr(q.bootstrap, '_atomic_publish', lambda src, dst: src.rename(dst))
    healthy = record(); healthy['observed_epoch'] = time.time()
    capsule = {'schema': 'fdisbull-host-health-capsule-1', 'run_id': '42', 'run_attempt': '1',
               'source_sha': sha, 'control_sha': control_sha, 'ref': 'control',
               'host_health': {'helper_sha256': q.health.HELPER_SHA256, 'record': healthy, 'failure': None}}
    health_dir = tmp_path/'ci-control/production/health/42'; health_dir.mkdir(parents=True)
    (health_dir/'1.json').write_text(json.dumps(capsule))
    policy = {'schema': 'fdisbull-ci-qualification-policy-1', 'profile': 'ordinary', 'repository': q.REPO,
              'runner_id': 21, 'cpus': 2, 'memory_mib': 9216, 'additional_swap': False,
              'required_artifacts': list(q.REQUIRED_ARTIFACTS)}
    policy_path = tmp_path/'policy.json'; policy_path.write_text(json.dumps(policy))
    return tmp_path, candidate, control, host, sha, env, job, request


def test_failure_export_binds_identity_and_strips_credentials(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    def runner(work, child_env, log):
        assert child_env['FDISBULL_GITHUB_JOB_ID'] == '30' and child_env['CI_COMMIT_SHA'] == sha
        assert 'GITHUB_TOKEN' not in child_env and 'OTHER_SECRET' not in child_env and 'CI_PIPELINE_ID' not in child_env
        log.write_bytes(b'failure diagnostic')
        return 1, {'total_bytes': 18, 'retained_bytes': 18, 'truncated': False}
    meta = q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request, runner=runner, system_preparer=fake_system_prepare,
                     host_root=host, control=control, mounted=lambda _: True, policy_path=tmp/'policy.json', control_root=tmp/'ci-control',
                     policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())
    saved = host/'42/1/qualification/30'
    assert meta['job_status'] == 'failed' and meta['qualification_exit_code'] == 1
    assert json.loads((saved/'job.json').read_text())['job_id'] == '30'
    assert json.loads((saved/'source-postcheck.json').read_text())['tracked_worktree_dirty'] is False
    assert json.loads((saved/'candidate-start.json').read_text())['source_sha'] == sha
    assert 'secret' not in (saved/'job.json').read_text()


def test_wrong_runner_refused_before_process(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    job['runner_id'] = 22
    with pytest.raises(ValueError):
        q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request,
                  runner=lambda *args: pytest.fail('must not execute'), system_preparer=fake_system_prepare, host_root=host,
                  control=control, mounted=lambda _: True, policy_path=tmp/'policy.json', control_root=tmp/'ci-control',
                  policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())


def test_missing_policy_retains_structured_failure_without_starting_tests(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    expected = 'a' * 64
    meta = q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request,
                     runner=lambda *args: pytest.fail('must not execute'), system_preparer=fake_system_prepare, host_root=host,
                     control=control, mounted=lambda _: True, policy_path=tmp/'absent', policy_sha=expected, control_root=tmp/'ci-control')
    assert meta['job_status'] == 'failed'
    diagnostic = json.loads((host/'42/1/qualification/30/exported/artifacts/recovery/diagnostic.json').read_text())
    assert (diagnostic['reason'], diagnostic['input_key'], diagnostic['expected_sha256']) == (
        'missing_ci_owned_input', 'qualification-policy', expected)
    assert diagnostic['target']['source_sha'] == sha and diagnostic['target']['job_id'] == '30'


def test_stale_or_mismatched_host_health_refuses_before_process(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    path = tmp/'ci-control/production/health/42/1.json'
    data = json.loads(path.read_text()); data['host_health']['record']['observed_epoch'] = time.time() - 121
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='stale'):
        q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request,
                  runner=lambda *args: pytest.fail('must not execute'), system_preparer=fake_system_prepare, host_root=host, control=control,
                  mounted=lambda _: True, policy_path=tmp/'policy.json', control_root=tmp/'ci-control',
                  policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())
    assert not list((host/'42/1').iterdir())


def test_policy_hash_mismatch_is_not_missing_input(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    meta = q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request,
                     runner=lambda *args: pytest.fail('must not execute'), system_preparer=fake_system_prepare, host_root=host, control=control,
                     mounted=lambda _: True, policy_path=tmp/'policy.json', control_root=tmp/'ci-control',
                     policy_sha='a'*64)
    assert meta['job_status'] == 'failed'
    diagnostic = json.loads((host/'42/1/qualification/30/exported/artifacts/recovery/diagnostic.json').read_text())
    assert diagnostic['reason'] == 'qualification_policy_invalid'


def test_success_requires_closed_declared_inventory(fixture):
    tmp, candidate, control, host, sha, env, job, request = fixture
    def runner(work, child_env, log):
        for name in q.REQUIRED_ARTIFACTS:
            item = work/name; item.parent.mkdir(parents=True, exist_ok=True); item.write_bytes(b'fixture output')
        log.write_bytes(b'fixture execution')
        return 0, {'total_bytes': 17, 'retained_bytes': 17, 'truncated': False}
    meta = q.execute(candidate, sha, 'nonce', tmp/'output', env=env, request=request, runner=runner, system_preparer=fake_system_prepare,
                     host_root=host, control=control, mounted=lambda _: True, policy_path=tmp/'policy.json',
                     control_root=tmp/'ci-control', policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())
    saved = host/'42/1/qualification/30'
    inventory = json.loads((saved/'inventory.json').read_text())
    assert meta['job_status'] == 'success' and meta['export_success'] is True
    assert {x['path'] for x in inventory} == set(q.REQUIRED_ARTIFACTS)
    for entry in inventory:
        data = (saved/'exported'/entry['path']).read_bytes()
        assert entry['size'] == len(data) and entry['sha256'] == hashlib.sha256(data).hexdigest()


def test_fixed_system_preparation_matches_gitlab_and_is_bounded(tmp_path):
    commands=[]
    def fake(argv,**kwargs):
        commands.append((argv,kwargs))
        assert kwargs['timeout']==300 and kwargs['env']['DEBIAN_FRONTEND']=='noninteractive'
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':b'ok\n','stderr':b''}
    result=q.run_system_prepare({'PATH':'/usr/bin'},tmp_path/'prep.log',runner=fake)
    assert result['status']=='passed' and len(commands)==2
    assert commands[0][0]==['/usr/bin/apt-get','update']
    assert commands[1][0]==['/usr/bin/apt-get','install','-y','--no-install-recommends',*q.SYSTEM_PACKAGES]
    assert (tmp_path/'prep.log').read_bytes()==b'ok\nok\n'


def test_system_preparation_failure_exports_stage_and_does_not_run_tests(fixture):
    tmp,candidate,control,host,sha,env,job,request=fixture
    def fail(env,path):
        assert 'GITHUB_TOKEN' not in env
        path.write_bytes(b'apt could not prepare dependencies\n')
        return {'status':'failed','steps':[{'name':'update','passed':False,'exit_code':100,
                                             'timed_out':False,'overflow':False}], 'capture_limit_bytes':q.MAX_LOG}
    meta=q.execute(candidate,sha,'nonce',tmp/'output',env=env,request=request,
                   runner=lambda *a:pytest.fail('tests must not run'),system_preparer=fail,
                   host_root=host,control=control,mounted=lambda _:True,policy_path=tmp/'policy.json',
                   control_root=tmp/'ci-control',policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())
    saved=host/'42/1/qualification/30'
    assert meta['job_status']=='failed' and meta['qualification_stage']=='system-preparation'
    assert json.loads((saved/'system-preparation.json').read_text())['steps'][0]['exit_code']==100
    assert (saved/'qualification.log').read_bytes()==b'apt could not prepare dependencies\n'
    assert meta['system-preparation.log']['sha256']==hashlib.sha256((saved/'system-preparation.log').read_bytes()).hexdigest()


def test_failed_apt_update_is_bounded_and_prevents_install(tmp_path):
    calls=[]
    def fake(argv,**kwargs):
        calls.append(argv)
        return {'returncode':100,'timed_out':False,'overflow':False,'stdout':b'', 'stderr':b'update failed'}
    result=q.run_system_prepare({},tmp_path/'prepare.log',runner=fake)
    assert result['status']=='failed' and len(calls)==1 and calls[0]==['/usr/bin/apt-get','update']
    assert (tmp_path/'prepare.log').read_bytes()==b'update failed'


def test_rejects_mount_at_parent_instead_of_owned_run_attempt(fixture):
    tmp,candidate,control,host,sha,env,job,request=fixture
    inspected=[]
    def mounted(path):
        inspected.append(path)
        return path==host
    with pytest.raises(ValueError,match='host results mount unavailable'):
        q.execute(candidate,sha,'nonce',tmp/'output',env=env,request=request,
                  runner=lambda *a:pytest.fail('must not run'),system_preparer=fake_system_prepare,
                  host_root=host,control=control,mounted=mounted,policy_path=tmp/'policy.json',
                  control_root=tmp/'ci-control',policy_sha=hashlib.sha256((tmp/'policy.json').read_bytes()).hexdigest())
    assert inspected==[host/'42/1'] and not list((host/'42/1').iterdir())
