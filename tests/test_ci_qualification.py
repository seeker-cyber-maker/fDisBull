"""Release qualification must retain absent/failed/wrong-source evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('qualification', Path(__file__).parents[1] / 'scripts/check_ci_qualification.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = 'a' * 40


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def qualified(tmp_path):
    for index, (profile, job) in enumerate(gate.JOBS.items(), 1):
        for name in gate.JUNIT[profile]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            skipped = '1' if profile == 'ordinary' else '0'
            p.write_text(f'<testsuites><testsuite tests="2" failures="0" errors="0" skipped="{skipped}"/></testsuites>')
        artifact = tmp_path / f'backend-{profile}'
        artifact.write_bytes(b'authored fixture')
        receipt = {'status': 'passed', 'source_commit': SHA, 'pipeline_id': '123', 'job_id': str(index),
                   'job_name': job, 'profile': profile, 'python_version': '3.13.5' if profile == 'layers' else '3.12.12',
                   'test_results': [gate.identity(tmp_path, name) for name in gate.JUNIT[profile]],
                   'artifacts': [gate.identity(tmp_path, artifact.name)], 'backend_identity': {'source_commit': SHA}}
        if profile == 'unified':
            receipt['artifacts'] = [gate.identity(tmp_path, 'dist/fdisbull.whl')]
        if profile == 'ordinary':
            receipt['artifacts'] = []
            packages = {}
            for kind, name in [('core', 'fdisbull.whl'), ('player', 'player.whl'), ('sdist', 'source.tar.gz'), ('tool', 'tool.zip')]:
                dest = tmp_path / 'dist' / name
                dest.parent.mkdir(exist_ok=True)
                dest.write_bytes(kind.encode())
                item = gate.identity(tmp_path, 'dist/' + name)
                receipt['artifacts'].append(item)
                packages[kind] = {'name': name, 'sha256': item['sha256'], 'size_bytes': item['size']}
            write(tmp_path, 'artifacts/receipts/package-payloads.json', {'source_commit': SHA, 'tracked_worktree_dirty': False, 'artifacts': packages})
        filename = 'ordinary' if profile == 'ordinary' else 'native-' + profile
        write(tmp_path, f'artifacts/receipts/{filename}.json', receipt)
    return tmp_path


def test_complete_same_pipeline_and_source_qualifies_without_authorizing_release(qualified):
    result = gate.validate(qualified, SHA, '123')
    assert result['status'] == 'qualified'
    assert set(result['required_jobs']) == set(gate.JOBS.values())
    assert result['release_authorized'] is False


@pytest.mark.parametrize('field,value', [('status', 'manual'), ('status', 'skipped'), ('status', 'failed'),
                                        ('source_commit', 'b' * 40), ('pipeline_id', '999'),
                                        ('python_version', '3.12.12'), ('job_name', 'other')])
def test_partial_or_different_run_never_qualifies(qualified, field, value):
    path = qualified / 'artifacts/receipts/native-layers.json'
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        gate.validate(qualified, SHA, '123')


def test_missing_job_capture_is_incomplete(qualified):
    (qualified / 'artifacts/receipts/native-stable.json').rename(qualified / 'not-a-receipt.json')
    with pytest.raises(ValueError, match='Missing'):
        gate.validate(qualified, SHA, '123')


def test_changed_package_and_dirty_inventory_are_rejected(qualified):
    path = qualified / 'artifacts/receipts/package-payloads.json'
    receipt = json.loads(path.read_text())
    receipt['tracked_worktree_dirty'] = True
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='dirty'):
        gate.validate(qualified, SHA, '123')
    receipt['tracked_worktree_dirty'] = False
    path.write_text(json.dumps(receipt))
    (qualified / 'dist/fdisbull.whl').write_bytes(b'replaced')
    with pytest.raises(ValueError, match='identity mismatch'):
        gate.validate(qualified, SHA, '123')


def test_empty_or_failed_junit_cannot_be_rescued_by_success_status(qualified):
    path = qualified / 'native-evidence/stable/tests.xml'
    receipt_path = qualified / 'artifacts/receipts/native-stable.json'
    for attrs in ['tests="0"', 'tests="2" skipped="2"', 'tests="2" errors="1"', 'tests="2" skipped="1"']:
        path.write_text(f'<testsuites><testsuite {attrs}/></testsuites>')
        receipt = json.loads(receipt_path.read_text())
        receipt['test_results'] = [gate.identity(qualified, 'native-evidence/stable/tests.xml')]
        receipt_path.write_text(json.dumps(receipt))
        with pytest.raises(ValueError, match='skipped tests'):
            gate.validate(qualified, SHA, '123')


def test_artifact_path_cannot_escape_the_qualified_workspace(qualified):
    with pytest.raises(ValueError, match='Unsafe'):
        gate.local_path(qualified, '../unrelated')


def test_duplicate_pe_capture_cannot_stand_in_for_boot_acceptance(qualified):
    p = qualified / 'artifacts/receipts/native-unified.json'
    receipt = json.loads(p.read_text())
    receipt['test_results'][1] = receipt['test_results'][0]
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='captures absent'):
        gate.validate(qualified, SHA, '123')
