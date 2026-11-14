"""Bounded local CI runner checks; no container service or image is started."""
import importlib.util
import json
from types import SimpleNamespace
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('local_linux_ci', ROOT / 'scripts/ci/local-linux.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def image_fixture():
    return [{'configuration': {'name': 'docker.io/library/python:3.12-bookworm',
                               'descriptor': {'digest': 'sha256:' + 'a' * 64},
                               'environment': ['SENSITIVE=do-not-return']},
             'variants': [{'platform': {'architecture': 'amd64', 'os': 'linux'},
                           'digest': 'sha256:' + 'b' * 64}]}]


def test_image_identity_selects_only_expected_fields():
    result = runner.image_identity(image_fixture())
    assert result == {'image_digest': 'sha256:' + 'b' * 64,
                      'image_index_digest': 'sha256:' + 'a' * 64,
                      'image_reference': 'docker.io/library/python@sha256:' + 'a' * 64}
    assert 'SENSITIVE' not in str(result)


@pytest.mark.parametrize('defect', ['missing', 'multiple', 'bad-index', 'bad-variant'])
def test_image_identity_rejects_ambiguous_or_invalid_identity(defect):
    data = image_fixture()
    if defect == 'missing':
        data[0]['variants'][0]['platform']['architecture'] = 'arm64'
    elif defect == 'multiple':
        data[0]['variants'].append(data[0]['variants'][0].copy())
    elif defect == 'bad-index':
        data[0]['configuration']['descriptor']['digest'] = 'sha256:bad'
    else:
        data[0]['variants'][0]['digest'] = 'sha256:bad'
    with pytest.raises(ValueError):
        runner.image_identity(data)


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def test_clone_binds_clean_exact_commit_and_generated_outputs(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    git(source, 'init', '-b', 'fixture')
    git(source, 'config', 'user.name', 'CI fixture')
    git(source, 'config', 'user.email', 'fixture@example.invalid')
    (source / 'tracked.txt').write_text('first\n')
    git(source, 'add', 'tracked.txt')
    git(source, 'commit', '-m', 'first')
    (source / 'tracked.txt').write_text('second\n')
    git(source, 'commit', '-am', 'second')
    sha, branch = runner.source_identity(source)
    dest = tmp_path / 'clone'
    runner.clone_source(source, dest, sha, branch)
    assert git(dest, 'rev-parse', 'HEAD') == sha
    assert git(dest, 'rev-parse', '--is-shallow-repository') == 'true'
    assert (dest / 'tracked.txt').read_text() == 'second\n'
    (dest / 'generated-output').write_text('generated')
    with pytest.raises(ValueError):
        runner.source_identity(dest)
    assert runner.source_identity(dest, generated_outputs=True) == (sha, branch)
    (dest / 'tracked.txt').write_text('modified')
    with pytest.raises(ValueError):
        runner.source_identity(dest, generated_outputs=True)


def test_collect_retains_identical_outputs_and_rejects_conflicts(tmp_path):
    work, output = tmp_path / 'work', tmp_path / 'output'
    (work / 'dist').mkdir(parents=True)
    (work / 'dist/package.whl').write_bytes(b'expected')
    runner.collect(work, output)
    runner.collect(work, output)
    assert (output / 'dist/package.whl').read_bytes() == b'expected'
    (work / 'dist/package.whl').write_bytes(b'different')
    with pytest.raises(ValueError, match='Conflicting outputs'):
        runner.collect(work, output)
    assert (output / 'dist/package.whl').read_bytes() == b'expected'


@pytest.mark.parametrize('interrupt', [False, True], ids=['timeout', 'interrupt'])
def test_interrupted_process_stops_only_its_own_named_container(tmp_path, monkeypatch, interrupt):
    stop_log = tmp_path / 'stops'
    cli = tmp_path / 'fake-container'
    cli.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$STOP_LOG"\n'
                   'if [ "$1" = inspect ]; then printf \'[{"status":{"state":"stopped"}}]\\n\'; fi\n')
    cli.chmod(0o755)
    monkeypatch.setattr(runner, 'CLI', cli)
    monkeypatch.setenv('STOP_LOG', str(stop_log))
    real_popen = subprocess.Popen
    if interrupt:
        first_process = True
        def interrupt_once(*args, **kwargs):
            nonlocal first_process
            process = real_popen(*args, **kwargs)
            if not first_process:
                return process
            first_process = False
            original_wait = process.wait
            first = True
            def wait(*a, **kw):
                nonlocal first
                if first:
                    first = False
                    raise KeyboardInterrupt
                return original_wait(*a, **kw)
            process.wait = wait
            return process
        monkeypatch.setattr(runner.subprocess, 'Popen', interrupt_once)
    code, termination, _, _, state = runner.run_container(
        [sys.executable, '-c', 'import time; time.sleep(10)'],
        tmp_path / 'job.log', 0.05, 'owned-job')
    assert code != 0
    assert termination == 'timeout-or-interrupted'
    assert state == 'stopped'
    assert stop_log.read_text().splitlines() == ['stop owned-job', 'inspect owned-job']


def test_separate_container_store_storage_is_observed_without_reserve_refusal(tmp_path, monkeypatch):
    output = tmp_path / 'codex'
    output.mkdir()
    store = Path('/Volumes/CACHE/AppleContainer')
    real_stat = runner.os.stat
    def stat(path, *args, **kwargs):
        if Path(path) == store:
            return SimpleNamespace(st_dev=987654)
        return real_stat(path, *args, **kwargs)
    calls = []
    def observe(path, expected, reserve):
        calls.append((path, expected, reserve))
        return {'free_bytes': 1, 'expected_bytes': expected, 'reserve_bytes': reserve,
                'storage_status': 'observed', 'reserve_enforced': False}
    monkeypatch.setattr(runner.os, 'stat', stat)
    monkeypatch.setattr(runner.shutil, 'disk_usage', lambda path: SimpleNamespace(free=1))
    monkeypatch.setattr(runner, 'storage_observation', observe)
    results = runner.observe_destinations(output, 123, 456)
    assert calls == [(output, 123, 456), (store, 123, 456)]
    assert set(results) == {'output', 'container_store'}


def test_resume_rejects_process_receipt_without_completed_marker(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    run = tmp_path / 'run'
    run.mkdir()
    sha = 'a' * 40
    (run / 'run.json').write_text(json.dumps({'source_commit': sha, 'source': str(source.resolve()),
                                              'local_run_id': 'example-run'}))
    (run / 'ordinary').mkdir()
    receipts = run / 'qualification/artifacts/receipts'
    receipts.mkdir(parents=True)
    (receipts / 'local-process-ordinary.json').write_text(json.dumps({'exit_code': 0, 'local_job_id': 'job'}))
    real_relative = Path.is_relative_to
    def permitted_relative(path, *others):
        if path == run and others == (Path('/Volumes/CACHE'),):
            return True
        return real_relative(path, *others)
    monkeypatch.setattr(Path, 'is_relative_to', permitted_relative)
    monkeypatch.setattr(runner, 'source_identity', lambda path: (sha, 'fixture'))
    monkeypatch.setattr(runner, 'observe_destinations', lambda *args: {})
    args = SimpleNamespace(source=source, output=run, expected_bytes=1,
                           reserve_bytes=20_000_000_000, profile='ordinary', timeout=1)
    with pytest.raises(ValueError, match='Failed attempt retained'):
        runner.execute(args)
    assert not (run / 'ordinary/completed.json').exists()


def test_same_pool_storage_is_observed_once(tmp_path, monkeypatch):
    output = tmp_path / 'cache-output'
    output.mkdir()
    store = Path('/Volumes/CACHE/AppleContainer')
    real_stat = runner.os.stat
    output_device = real_stat(output).st_dev
    def stat(path, *args, **kwargs):
        if Path(path) == store:
            return SimpleNamespace(st_dev=output_device)
        return real_stat(path, *args, **kwargs)
    calls = []
    monkeypatch.setattr(runner.os, 'stat', stat)
    monkeypatch.setattr(runner, 'storage_observation', lambda path, expected, reserve: calls.append(path) or {'storage_status': 'observed'})
    assert set(runner.observe_destinations(output, 123, 456)) == {'output'}
    assert calls == [output]


def test_storage_observation_rejects_missing_or_symlink_destination(tmp_path):
    with pytest.raises(ValueError, match='destination unavailable'):
        runner.storage_observation(tmp_path / 'missing', 0, 0)
    link = tmp_path / 'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='destination unavailable'):
        runner.storage_observation(link, 0, 0)


def test_local_unified_preparation_precedes_direct_acceptance():
    assert runner.profiles_for('unified') == ['unified-prepare', 'unified']
    assert runner.profiles_for('all') == ['ordinary', 'stable', 'layers', 'unified-prepare', 'unified']
    assert runner.profiles_for('qualify') == []
    sha = 'a' * 40
    run = '27680f97-aaad-4846-a2fd-4a48b7bad36b'
    job = 'd0c36dcb-43d6-457c-889e-c97a0e82d6dd'
    build = runner.job_environment('unified-prepare', sha, run, job)
    direct = runner.job_environment('unified', sha, run, job)
    assert build['CI_JOB_NAME'] == 'native-unified-prepare'
    assert build['FDISBULL_UNIFIED_PREPARE_ONLY'] == '1'
    assert direct['CI_JOB_NAME'] == 'native-unified'
    assert direct['FDISBULL_UNIFIED_PREPARED'] == '1'
    assert 'DOCKER_HOST' not in direct and 'FDISBULL_LOCAL_DOCKER' not in direct
    assert 'unified-acceptance.sh' in runner.job_command('unified')
    assert 'native-unified.sh' not in runner.job_command('unified')
    assert 'native-receipt.py' not in runner.job_command('unified-prepare')
    assert runner.expected_bytes(SimpleNamespace(expected_bytes=None), 'unified-prepare') == 35_000_000_000
    assert runner.expected_bytes(SimpleNamespace(expected_bytes=None), 'unified') == 8_000_000_000


def test_collect_retains_every_prepared_runtime_input(tmp_path):
    work, output = tmp_path / 'work', tmp_path / 'output'
    for index, name in enumerate(runner.UNIFIED_INPUTS):
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([index]))
    runner.collect(work, output)
    for index, name in enumerate(runner.UNIFIED_INPUTS):
        assert (output / name).read_bytes() == bytes([index])


def test_collect_rejects_symlinked_runtime_parent(tmp_path):
    work, output, external = tmp_path / 'work', tmp_path / 'output', tmp_path / 'external'
    (work / '.native').mkdir(parents=True)
    external.mkdir()
    (external / 'linux-amd64').write_bytes(b'synthetic kernel fixture')
    (work / '.native/pe').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        runner.collect(work, output)
    assert not (output / '.native/pe/linux-amd64').exists()


@pytest.mark.parametrize('defect', ['failed', 'wrong-source', 'wrong-run', 'wrong-job',
                                  'unstopped', 'wrong-runtime', 'boolean-exit'])
def test_prepared_stage_rejects_uncompleted_or_foreign_build_before_staging(tmp_path, defect):
    run = tmp_path / 'run'
    phase = run / 'unified-prepare'
    phase.mkdir(parents=True)
    sha = 'a' * 40
    run_id = '27680f97-aaad-4846-a2fd-4a48b7bad36b'
    job = 'd0c36dcb-43d6-457c-889e-c97a0e82d6dd'
    process = {'execution_origin': 'local-linux', 'source_commit': sha,
               'local_run_id': run_id, 'local_job_id': job,
               'job_name': 'native-unified-prepare', 'exit_code': 0,
               'termination': 'exited', 'container_state_after_stop': 'stopped',
               'runtime': {'system': 'linux', 'machine': 'x86_64', 'python': '3.12.16'}}
    if defect == 'failed': process['exit_code'] = 1
    elif defect == 'wrong-source': process['source_commit'] = 'b' * 40
    elif defect == 'wrong-run': process['local_run_id'] = '01cfab60-1368-46d3-88b7-d45878385f74'
    elif defect == 'wrong-job': process['job_name'] = 'native-unified'
    elif defect == 'unstopped': process['container_state_after_stop'] = 'running'
    elif defect == 'wrong-runtime': process['runtime']['machine'] = 'arm64'
    elif defect == 'boolean-exit': process['exit_code'] = False
    (phase / 'process.json').write_text(json.dumps(process))
    (phase / 'completed.json').write_text(json.dumps({'source_commit': sha, 'local_job_id': job}))
    with pytest.raises(ValueError, match='did not complete'):
        runner.prepared_unified_stage(tmp_path / 'source', run, tmp_path / 'output', sha, run_id)


def test_readback_qualification_does_not_request_bulk_storage_or_start_workers(tmp_path, monkeypatch):
    source, run = tmp_path / 'source', tmp_path / 'run'
    source.mkdir()
    run.mkdir()
    sha = 'a' * 40
    run_id = '27680f97-aaad-4846-a2fd-4a48b7bad36b'
    (run / 'run.json').write_text(json.dumps({'source_commit': sha, 'source': str(source),
                                             'local_run_id': run_id}))
    original_relative = Path.is_relative_to
    monkeypatch.setattr(Path, 'is_relative_to', lambda path, *other:
                        True if path == run and other == (Path('/Volumes/CACHE'),)
                        else original_relative(path, *other))
    monkeypatch.setattr(runner, 'source_identity', lambda path: (sha, 'fixture'))
    monkeypatch.setattr(runner, 'observe_destinations', lambda *a: pytest.fail('Readback requested bulk allocation'))
    commands = []
    monkeypatch.setattr(runner.subprocess, 'run', lambda command, **kwargs: commands.append(command))
    runner.execute(SimpleNamespace(source=source, output=run, profile='qualify',
                                   expected_bytes=None, reserve_bytes=40_000_000_000, timeout=1))
    assert commands == [[sys.executable, str(run / 'ordinary/work/scripts/check_ci_qualification.py'),
                         '--root', str(run / 'qualification'), '--source-commit', sha,
                         '--local-run-id', run_id, '--output', str(run / 'qualification/qualification.json')]]
