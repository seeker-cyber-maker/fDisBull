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


def test_separate_container_store_gets_own_storage_admission(tmp_path, monkeypatch):
    output = tmp_path / 'codex'
    output.mkdir()
    store = Path('/Volumes/CACHE/AppleContainer')
    real_stat = runner.os.stat
    def stat(path, *args, **kwargs):
        if Path(path) == store:
            return SimpleNamespace(st_dev=987654)
        return real_stat(path, *args, **kwargs)
    calls = []
    def admit(path, expected, reserve):
        calls.append((path, expected, reserve))
        return {'admitted': True}
    monkeypatch.setattr(runner.os, 'stat', stat)
    monkeypatch.setattr(runner, 'admit', admit)
    results = runner.admit_destinations(output, 123, 456)
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
    monkeypatch.setattr(runner, 'admit_destinations', lambda *args: {})
    args = SimpleNamespace(source=source, output=run, expected_bytes=1,
                           reserve_bytes=20_000_000_000, profile='ordinary', timeout=1)
    with pytest.raises(ValueError, match='Failed attempt retained'):
        runner.execute(args)
    assert not (run / 'ordinary/completed.json').exists()


def test_same_pool_storage_is_admitted_once(tmp_path, monkeypatch):
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
    monkeypatch.setattr(runner, 'admit', lambda path, expected, reserve: calls.append(path) or {'admitted': True})
    assert set(runner.admit_destinations(output, 123, 456)) == {'output'}
    assert calls == [output]
