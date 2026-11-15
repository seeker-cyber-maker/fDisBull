import importlib.util
import hashlib
import json
import os
import re
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


def test_ovh_storage_reports_low_space_without_reserve_admission(monkeypatch, tmp_path):
    monkeypatch.setattr(admission.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1_000_000))
    result = admission.observe(tmp_path, 10_000_000_000, 0)
    assert result == {'free_bytes': 1_000_000, 'expected_bytes': 10_000_000_000,
                      'reserve_bytes': 0, 'storage_status': 'observed', 'reserve_enforced': False}
    with pytest.raises(ValueError, match='Invalid allocation estimate'):
        admission.observe(tmp_path, -1)


def test_runner_admission_rejects_unapproved_runner(monkeypatch):
    monkeypatch.setenv('CI_RUNNER_TAGS', '["other"]')
    with pytest.raises(ValueError, match='dedicated OVH'):
        admission.main()


def git(work, *args):
    return subprocess.check_output(['git', '-C', str(work), *args], text=True).strip()


@pytest.fixture
def exports(tmp_path, request):
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
        document = {'job_id': str(job)}
        if name == 'native-unified':
            paths = ['.native/pe/qemu-9.2.4/build/qemu-system-x86_64', '.native/pe/linux-amd64',
                     '.native/pe/runtime.cpio.gz', '.native/pe/oracle.exe',
                     '.native/backends/layers/dosbox-x', '.native/pe/dos-runtime.cpio.gz']
            inputs = {}
            for index, relative in enumerate(paths):
                path = work / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                data = f'authored runtime {index}'.encode()
                path.write_bytes(data)
                reference = str(path)
                if index == 0 and getattr(request, 'param', None) == 'outside':
                    reference = str(tmp_path / 'outside')
                if index == 0 and getattr(request, 'param', None) == 'missing':
                    reference = str(work / '.native/pe/missing')
                inputs[str(index)] = {'path': reference, 'sha256': hashlib.sha256(data).hexdigest()}
            document['backend_identity'] = {'inputs': inputs}
        (receipts / receipt).write_text(json.dumps(document))
        env = {'CI_COMMIT_SHA': sha, 'CI_PIPELINE_ID': '50', 'CI_JOB_ID': str(job), 'CI_JOB_NAME': name, 'CI_JOB_STATUS': 'success'}
        exporter.export(work, root, env)
    return work, root, {'CI_COMMIT_SHA': sha, 'CI_PIPELINE_ID': '50'}


def test_actual_git_export_verifies(exports):
    work, root, env = exports
    exporter.verify(work, root, env)
    assert json.loads((root / '50/101/source-postcheck.json').read_text())['tracked_worktree_dirty'] is False
    assert json.loads((root / '50/104/job.json').read_text())['project_directory'] == str(work.resolve())


@pytest.fixture
def failed_export(exports):
    work, root, env = exports
    capture = work / 'artifacts/ordinary/failure.txt'
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text('controlled failure evidence\n')
    job_env = {**env, 'CI_JOB_ID': '105', 'CI_JOB_NAME': 'demo', 'CI_JOB_STATUS': 'failed'}
    exporter.export(work, root, job_env)
    return work, root, job_env


def test_failed_export_verified_without_claiming_job_success(failed_export):
    _, root, env = failed_export
    result = exporter.verify_job_export(root, '50', '105', env['CI_COMMIT_SHA'], 'demo',
                                        expected_job_status='failed')
    assert result['status'] == 'export-verified'
    assert result['job_status'] == 'failed'


@pytest.mark.parametrize('damage', ['tampered', 'missing', 'extra', 'wrong_status', 'wrong_name', 'wrong_sha', 'dirty'])
def test_failed_export_rejects_damaged_or_mismatched_evidence(failed_export, damage):
    _, root, env = failed_export
    target = root / '50/105'
    capture = target / 'exported/artifacts/ordinary/failure.txt'
    status, name, sha = 'failed', 'demo', env['CI_COMMIT_SHA']
    if damage == 'tampered':
        capture.write_text('changed')
    elif damage == 'missing':
        capture.unlink()
    elif damage == 'extra':
        (capture.parent / 'extra').write_text('unlisted')
    elif damage == 'wrong_status':
        status = 'success'
    elif damage == 'wrong_name':
        name = 'other'
    elif damage == 'wrong_sha':
        sha = 'a' * 40
    else:
        post = target / 'source-postcheck.json'
        record = json.loads(post.read_text())
        record['tracked_worktree_dirty'] = True
        post.write_text(json.dumps(record))
    with pytest.raises((ValueError, OSError)):
        exporter.verify_job_export(root, '50', '105', sha, name, expected_job_status=status)


def test_full_qualification_rejects_failed_export(exports):
    work, root, env = exports
    path = root / '50/101/job.json'
    meta = json.loads(path.read_text())
    meta['job_status'] = 'failed'
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError):
        exporter.verify(work, root, env)


@pytest.mark.parametrize('exports', ['outside', 'missing'], indirect=True)
def test_nested_runtime_references_reject_outside_or_missing(exports):
    work, root, env = exports
    with pytest.raises(ValueError):
        exporter.verify(work, root, env)


def test_nested_runtime_reference_rejects_corruption(exports):
    work, root, env = exports
    (root / '50/104/exported/.native/pe/linux-amd64').write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        exporter.verify(work, root, env)


@pytest.mark.parametrize('reference', ['../escape', 'a/../b', '/elsewhere/file', './relative'])
def test_reference_path_rejects_escape_and_noncanonical(reference):
    with pytest.raises(ValueError):
        exporter.reference_path(reference, '/ci/project')


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
    assert config.count('expire_in: never') == 5
    assert '--legacy-dos-only' in config
    assert 'ovh-export.py verify' in config
    # Ordinary CI compiles the actual PNG/zstd encoders in the source patches.
    ordinary = config.split('test-and-package:', 1)[1].split('# A deliberate', 1)[0]
    assert all(dependency in ordinary for dependency in ('pkg-config', 'zlib1g-dev', 'libzstd-dev'))
    for job in ('test-and-package', 'native-debugger-stable', 'native-debugger-layers', 'native-unified'):
        assert job + ':' in config


def test_unified_timeout_reserves_export_and_upload_time():
    config = (ROOT / '.gitlab-ci.yml').read_text()
    section = config.split('\nnative-unified:\n', 1)[1].split('\nqualify-candidate:', 1)[0]

    def seconds(value):
        parts = re.findall(r'(\d+)([hms])', value)
        assert parts and ''.join(n + unit for n, unit in parts) == value
        scale = {'h': 3600, 'm': 60, 's': 1}
        return sum(int(n) * scale[unit] for n, unit in parts)

    job = seconds(re.search(r'^  timeout: (\S+)$', section, re.M).group(1))
    script = seconds(re.search(r'RUNNER_SCRIPT_TIMEOUT: "([^"]+)"', section).group(1))
    export = seconds(re.search(r'RUNNER_AFTER_SCRIPT_TIMEOUT: "([^"]+)"', section).group(1))
    assert script > 0 and export >= 300
    assert script + export + 600 <= job <= 3 * 3600


@pytest.mark.parametrize('job', ['native-qualification', 'qualify-candidate'])
def test_control_jobs_use_git_capable_image_for_export(job):
    config = (ROOT / '.gitlab-ci.yml').read_text()
    section = config.split(f'\n{job}:\n', 1)[1].split('\n\n', 1)[0]
    assert '\n  image: python:3.12-bookworm\n' in section
    assert 'ovh-export.py export' in config


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
