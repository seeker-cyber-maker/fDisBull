"""Storage admission must precede cache creation, transfer and ref publication."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import pytest

from test_mirror_sync_service import ROOT, branch, mirrors, oid, publish, worker


def checker(m):
    return Path(json.loads(m['config'].read_text())['storage']['checker'])


@pytest.mark.parametrize('response', [
    "print('not JSON')",
    "print('{}')",
    "print('x'*65537)",
])
def test_invalid_admission_never_initializes_cache(mirrors, response):
    m = mirrors
    checker(m).write_text(response + '\n')
    result = worker(m, initialize=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)['status'] == 'storage-held'
    assert not m['cache'].exists()
    assert oid(m, 'hub', 'refs/heads/main') == m['base']
    assert oid(m, 'remote', 'refs/heads/main') == m['base']


def test_denied_admission_preserves_existing_baseline_and_refs(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    before = (m['state']/'refs.json').read_bytes()
    commit = branch(m, m['base'], 'held for capacity')
    publish(m, 'hub', commit, 'refs/heads/storage-held')
    source = checker(m).read_text().replace('admitted=True', 'admitted=False')
    checker(m).write_text(source + '\nraise SystemExit(2)\n')
    result = worker(m)
    report = json.loads(result.stdout)
    assert result.returncode == 2 and report['status'] == 'storage-held'
    assert report['storage']['phase'] == 'before-cache'
    assert (m['state']/'refs.json').read_bytes() == before
    assert oid(m, 'remote', 'refs/heads/storage-held') is None


@pytest.mark.parametrize('change', [
    ('reasons=[]', "reasons=['contradictory positive receipt']"),
    ('cache_receipt=dict(', 'omitted_cache_receipt=dict('),
    ('after_expected_bytes=a.destination_reserve_bytes', 'after_expected_bytes=1'),
])
def test_incoherent_positive_admission_is_rejected(mirrors, change):
    m = mirrors
    source = checker(m).read_text()
    assert change[0] in source
    checker(m).write_text(source.replace(*change))
    result = worker(m, initialize=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)['status'] == 'storage-held'
    assert not m['cache'].exists()


def test_capacity_rechecked_after_fetch_before_next_transfer(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'capacity falls after fetch')
    publish(m, 'hub', commit, 'refs/heads/no-publish')
    counter = m['root']/'admission-count'
    original = checker(m).read_text()
    injected = ("counter=pathlib.Path(" + repr(str(counter)) + ")\n"
                "n=int(counter.read_text())+1 if counter.exists() else 1\n"
                "counter.write_text(str(n))\n")
    # Calls: before-cache, before hub fetch, after hub fetch.
    checker(m).write_text(original.replace('print(json.dumps', injected+'print(json.dumps')
                         .replace('admitted=True', 'admitted=n<3') +
                         '\nraise SystemExit(0 if n<3 else 2)\n')
    result = worker(m)
    report = json.loads(result.stdout)
    assert result.returncode == 2 and report['status'] == 'storage-held'
    assert report['storage']['phase'] == 'after-fetch'
    assert oid(m, 'remote', 'refs/heads/no-publish') is None


def test_capacity_rechecked_before_outbound_push(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'capacity falls after snapshots')
    publish(m, 'hub', commit, 'refs/heads/no-push')
    counter = m['root']/'admission-count'
    original = checker(m).read_text()
    injected = ("counter=pathlib.Path(" + repr(str(counter)) + ")\n"
                "n=int(counter.read_text())+1 if counter.exists() else 1\n"
                "counter.write_text(str(n))\n")
    # First five checks admit cache and the two completed fetches.
    checker(m).write_text(original.replace('print(json.dumps', injected+'print(json.dumps')
                         .replace('admitted=True', 'admitted=n<6') +
                         '\nraise SystemExit(0 if n<6 else 2)\n')
    result = worker(m)
    report = json.loads(result.stdout)
    assert result.returncode == 2 and report['status'] == 'storage-held'
    assert report['storage']['phase'] == 'before-push-gitlab'
    assert oid(m, 'remote', 'refs/heads/no-push') is None
    state = json.loads((m['state']/'refs.json').read_text())
    assert 'refs/heads/no-push' not in state['seen']['gitlab']


def test_admission_timeout_is_a_hold(mirrors, monkeypatch):
    m = mirrors
    spec = importlib.util.spec_from_file_location('storage_worker_test', ROOT/'scripts/mirror_sync_service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cfg = module._load_config(m['config'])
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('fixture admission', 1)
    monkeypatch.setattr(module.subprocess, 'run', timeout)
    with pytest.raises(module.StorageHeld):
        module._admit_storage(cfg, time.monotonic()+10, 'before-cache')
    assert not m['cache'].exists()


@pytest.mark.parametrize('field,value', [('expected_bytes',0),('expected_bytes',True),
                                        ('reserve_bytes',20_000_000_000)])
def test_invalid_storage_bounds_refuse_before_cache(mirrors, field, value):
    m = mirrors
    cfg = json.loads(m['config'].read_text())
    cfg['storage'][field] = value
    m['config'].write_text(json.dumps(cfg))
    result = worker(m, initialize=True)
    assert result.returncode == 2 and not m['cache'].exists()


@pytest.mark.parametrize('url', ['https://github.com/fixture/inactive.git',
                               'ssh://ssh.github.com/fixture/inactive.git'])
def test_github_destination_refused_before_any_contact(mirrors, url):
    m = mirrors
    cfg = json.loads(m['config'].read_text())
    cfg['gitlab'] = url
    m['config'].write_text(json.dumps(cfg))
    result = worker(m, initialize=True)
    assert result.returncode == 2 and 'GitHub mirror is inactive' in result.stdout
    assert not m['cache'].exists()
