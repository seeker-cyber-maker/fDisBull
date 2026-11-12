import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts/ci' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admission = load('ovh-admission')
exporter = load('ovh-export')


def test_storage_admission_rejects_reserve_and_negative(monkeypatch, tmp_path):
    monkeypatch.setattr(admission.shutil, 'disk_usage', lambda _: SimpleNamespace(free=30_000_000_000))
    assert admission.admit(tmp_path, 10_000_000_000)['admitted']
    for expected, reserve in [(10_000_000_001, 20_000_000_000), (-1, 20_000_000_000), (0, 19_999_999_999)]:
        with pytest.raises(ValueError):
            admission.admit(tmp_path, expected, reserve)


def test_runner_admission_rejects_unapproved_runner(monkeypatch):
    monkeypatch.setenv('CI_RUNNER_TAGS', '["other"]')
    with pytest.raises(ValueError, match='dedicated OVH'):
        admission.main()


def git(work, *args):
    return subprocess.check_output(['git', '-C', str(work), *args], text=True).strip()


@pytest.fixture
def exports(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    git(work, 'init', '-q')
    git(work, 'config', 'user.email', 'test@example.invalid')
    git(work, 'config', 'user.name', 'CI Test')
    (work / 'authored.txt').write_text('authored source\n')
    git(work, 'add', 'authored.txt')
    git(work, 'commit', '-qm', 'authored source')
    sha = git(work, 'rev-parse', 'HEAD')
    receipts = work / 'artifacts/receipts'
    receipts.mkdir(parents=True)
    root = tmp_path / 'results'
    for job, (name, receipt) in enumerate(exporter.RECEIPTS.items(), 101):
        (receipts / receipt).write_text(json.dumps({'job_id': str(job)}))
        env = {'CI_COMMIT_SHA': sha, 'CI_PIPELINE_ID': '50', 'CI_JOB_ID': str(job), 'CI_JOB_NAME': name, 'CI_JOB_STATUS': 'success'}
        exporter.export(work, root, env)
    return work, root, {'CI_COMMIT_SHA': sha, 'CI_PIPELINE_ID': '50'}


def test_actual_git_export_verifies(exports):
    work, root, env = exports
    exporter.verify(work, root, env)
    assert json.loads((root / '50/101/source-postcheck.json').read_text())['tracked_worktree_dirty'] is False


@pytest.mark.parametrize('damage', ['corrupt', 'missing', 'different_sha'])
def test_export_verification_rejects_damaged_evidence(exports, damage):
    work, root, env = exports
    target = root / '50/101'
    inventory = json.loads((target / 'inventory.json').read_text())
    if damage == 'corrupt':
        (target / 'exported' / inventory[0]['path']).write_text('corrupted')
    elif damage == 'missing':
        (target / 'inventory.json').unlink()
    else:
        env['CI_COMMIT_SHA'] = 'a' * 40
    with pytest.raises((ValueError, OSError)):
        exporter.verify(work, root, env)


def test_ci_resource_serial_retention_and_legacy_contract():
    config = (ROOT / '.gitlab-ci.yml').read_text()
    assert 'resource_group: fdisbull-ovh-ci' in config
    assert 'fdisbull-ovh-ca' in config
    assert 'FDISBULL_EXPECTED_BYTES: "35000000000"' in config
    assert 'expire_in: 7 days' not in config and 'expire_in: 30 days' not in config
    assert config.count('expire_in: never') == 4
    assert '--legacy-dos-only' in config
    assert 'ovh-export.py verify' in config
    for job in ('test-and-package', 'native-debugger-stable', 'native-debugger-layers', 'native-unified'):
        assert job + ':' in config


@pytest.mark.parametrize('damage', ['omitted_inventory_entry', 'omitted_canonical_receipt', 'dirty_postcheck'])
def test_preservation_requires_complete_inventory_and_own_receipt(exports, damage):
    work, root, env = exports
    target = root / '50/104'
    inventory = json.loads((target / 'inventory.json').read_text())
    meta = json.loads((target / 'job.json').read_text())
    if damage == 'dirty_postcheck':
        path = target / 'source-postcheck.json'
        record = json.loads(path.read_text())
        record['tracked_worktree_dirty'] = True
        path.write_text(json.dumps(record))
    else:
        selected = next(item for item in inventory if item['path'] == 'artifacts/receipts/native-unified.json')
        inventory.remove(selected)
        if damage == 'omitted_canonical_receipt':
            (target / 'exported' / selected['path']).unlink()
        meta['files'] = len(inventory)
        (target / 'job.json').write_text(json.dumps(meta))
        (target / 'inventory.json').write_text(json.dumps(inventory))
    with pytest.raises(ValueError):
        exporter.verify(work, root, env)
