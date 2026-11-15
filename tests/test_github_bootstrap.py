import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('github_bootstrap', ROOT / 'scripts/ci/github-bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def repo(path):
    path.mkdir()
    git(path, 'init', '-q')
    git(path, 'config', 'user.name', 'Test')
    git(path, 'config', 'user.email', 'test@example.invalid')
    (path / 'source.txt').write_text('source\n')
    return path


def commit(path):
    git(path, 'add', '.')
    git(path, 'commit', '-qm', 'fixture')
    return git(path, 'rev-parse', 'HEAD')


@pytest.fixture
def case(tmp_path, monkeypatch):
    control, candidate = repo(tmp_path / 'control'), repo(tmp_path / 'candidate')
    (control / 'scripts/ci').mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/check_ci_qualification.py', control / 'scripts/check_ci_qualification.py')
    shutil.copyfile(ROOT / 'scripts/ci/execution_identity.py', control / 'scripts/ci/execution_identity.py')
    csha, sha = commit(control), commit(candidate)
    host = tmp_path / 'host'; host.mkdir()
    env = {'GITHUB_REPOSITORY': 'seeker-cyber-maker/fDisBull', 'GITHUB_SERVER_URL': 'https://github.com',
           'GITHUB_EVENT_NAME': 'workflow_dispatch', 'RUNNER_NAME': 'fdisbull-ovh-ca-gh1',
           'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': csha, 'GITHUB_JOB': 'bootstrap'}
    monkeypatch.setattr(bootstrap.shutil, 'disk_usage', lambda _: SimpleNamespace(free=45_000_000_000))
    # renameat2 is Linux-only; these tests exercise the surrounding file contract on macOS.
    monkeypatch.setattr(bootstrap, '_atomic_publish', lambda src, dst: src.rename(dst) if not dst.exists() else (_ for _ in ()).throw(FileExistsError()))
    def run(**kwargs):
        options = dict(candidate=candidate, source_sha=sha, nonce='case_1', output=tmp_path / 'artifacts',
                       env=env, host_root=host, control=control, mounted=lambda _: True,
                       system=lambda: 'Linux', machine=lambda: 'x86_64')
        options.update(kwargs)
        return bootstrap.execute(**options)
    return run, candidate, host, env, tmp_path


def test_actual_checker_rejects_empty_receipts_and_exports_closed_evidence(case):
    run, _, host, _, temp = case
    result = run()
    assert result['stage'] == 'completed' and result['release_ready'] is False
    assert result['provider_job_id'] is None
    assert result['qualification_check']['status'] == 'rejected_missing_receipts'
    assert result['qualification_check']['pipeline_id'] is None
    target = host / '42/1/bootstrap'
    assert {p.name for p in target.iterdir()} == {'runtime.json', 'handoff.json', 'inventory.json'}
    inventory = json.loads((target / 'inventory.json').read_text())
    for name, item in inventory['files'].items():
        data = (target / name).read_bytes()
        assert bootstrap.hashlib.sha256(data).hexdigest() == item['sha256'] and len(data) == item['size']
        assert (temp / 'artifacts' / name).read_bytes() == data
    assert (temp / 'artifacts/inventory.json').read_bytes() == (target / 'inventory.json').read_bytes()


@pytest.mark.parametrize('problem', ['wrong_sha', 'wrong_runner', 'missing_run', 'bad_nonce', 'dirty', 'unmounted'])
def test_invalid_observation_stops_before_export(case, monkeypatch, problem):
    run, candidate, host, env, _ = case
    options = {}
    if problem == 'wrong_sha': options['source_sha'] = 'a' * 40
    if problem == 'wrong_runner': env['RUNNER_NAME'] = 'wrong'
    if problem == 'missing_run': del env['GITHUB_RUN_ID']
    if problem == 'bad_nonce': options['nonce'] = 'bad nonce'
    if problem == 'dirty': (candidate / 'source.txt').write_text('changed')
    if problem == 'unmounted': options['mounted'] = lambda _: False
    with pytest.raises(ValueError): run(**options)
    assert not any(host.iterdir())


def test_storage_observation_does_not_enforce_a_fixed_reserve(case, monkeypatch):
    run, _, _, _, _ = case
    monkeypatch.setattr(bootstrap.shutil, 'disk_usage', lambda _: SimpleNamespace(free=32))
    result = run()
    assert result['stage'] == 'completed'
    assert result['storage']['free_bytes'] == 32
    assert result['storage']['reserve_enforced'] is False


def test_no_overwrite_of_existing_export(case):
    run, _, host, _, temp = case
    existing = host / '42/1/bootstrap'; existing.mkdir(parents=True)
    (existing / 'owned').write_text('preserved')
    with pytest.raises(ValueError): run()
    assert (existing / 'owned').read_text() == 'preserved'
    assert not (temp / 'artifacts').exists()


def test_checker_unexpected_failure_cannot_produce_export(case, monkeypatch):
    run, _, host, _, temp = case
    real_run = bootstrap.subprocess.run
    def unexpected(argv, **kwargs):
        if 'check_ci_qualification.py' in str(argv[1]):
            return SimpleNamespace(returncode=2, stderr='unexpected import error', stdout='')
        return real_run(argv, **kwargs)
    monkeypatch.setattr(bootstrap.subprocess, 'run', unexpected)
    with pytest.raises(ValueError): run()
    assert not (host / '42/1/bootstrap').exists()
    assert not (temp / 'artifacts').exists()


def test_retained_workflows_are_exact_and_only_manual_control_active():
    # Immutable bytes from restored main d2acdd66; works in shallow/source archives.
    expected = {'ci.yml': '474e0e575dbb2a4a3c5059f278e88a9356281dcb0c4eb81e456d737adecc9706', 'native-debugger.yml': 'b767044fb9710818d191f090fd74095b0d7e30d054adcc43342c92588a83dc5a'}
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / ".github/retained-workflows" / (name + ".disabled")).read_bytes()).hexdigest() == digest
    workflows = list((ROOT / '.github/workflows').glob('*'))
    assert {p.name for p in workflows} == {'ovh-bootstrap.yml', 'ci.yml', 'native-debugger.yml'}
    for name in ('ci.yml', 'native-debugger.yml'):
        stub = (ROOT / '.github/workflows' / name).read_text()
        assert 'workflow_dispatch:' in stub and 'if: ${{ false }}' in stub
        assert 'pull_request:' not in stub and 'push:' not in stub
        assert 'runs-on: [self-hosted, Linux, X64, fdisbull-ovh-ca-gh1]' in stub
    text = (ROOT / '.github/workflows/ovh-bootstrap.yml').read_text()
    assert 'workflow_dispatch:' in text and 'pull_request:' not in text and 'push:' not in text
    assert 'fdisbull-ovh-ca-gh1' in text and 'cancel-in-progress: false' in text
    assert 'actions/checkout@v4' in text and 'actions/upload-artifact@v4' in text
    assert 'if-no-files-found: error' in text
