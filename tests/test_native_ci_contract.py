"""Offline checks for the native CI success-evidence boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / 'scripts/ci/native-receipt.py'


def run_receipt(tmp_path, monkeypatch, source='candidate'):
    monkeypatch.setenv('CI_COMMIT_SHA', source)
    monkeypatch.setenv('CI_PIPELINE_ID', '23')
    monkeypatch.setenv('CI_JOB_ID', '42')
    monkeypatch.setenv('CI_JOB_NAME', 'native-debugger-stable')
    monkeypatch.setenv('FDISBULL_DOSBOX', str(tmp_path / 'backend'))
    return subprocess.run([sys.executable, str(RECEIPT), 'stable'], cwd=tmp_path,
                          env=os.environ.copy(), capture_output=True, text=True)


def test_native_success_receipt_binds_source_backend_and_junit(tmp_path, monkeypatch):
    evidence = tmp_path / 'native-evidence/stable'
    evidence.mkdir(parents=True)
    (evidence / 'backend-identity.json').write_text(json.dumps({'source_commit': 'candidate'}))
    (evidence / 'tests.xml').write_text('<testsuites><testsuite tests="1" failures="0" errors="0"/></testsuites>')
    (tmp_path / 'backend').write_bytes(b'backend')
    result = run_receipt(tmp_path, monkeypatch)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((tmp_path / 'artifacts/receipts/native-stable.json').read_text())
    assert receipt['status'] == 'passed'
    assert receipt['source_commit'] == 'candidate'
    assert receipt['artifacts'][0]['size'] == 7
    assert receipt['artifacts'][0]['path'] == 'backend'
    assert receipt['test_results'][0]['path'] == 'native-evidence/stable/tests.xml'
    assert len(receipt['test_results'][0]['sha256']) == 64


def test_native_receipt_rejects_wrong_sha_and_missing_junit(tmp_path, monkeypatch):
    evidence = tmp_path / 'native-evidence/stable'
    evidence.mkdir(parents=True)
    (evidence / 'backend-identity.json').write_text(json.dumps({'source_commit': 'other'}))
    (tmp_path / 'backend').write_bytes(b'backend')
    assert run_receipt(tmp_path, monkeypatch).returncode != 0
    (evidence / 'backend-identity.json').write_text(json.dumps({'source_commit': 'candidate'}))
    assert run_receipt(tmp_path, monkeypatch).returncode != 0
    assert not (tmp_path / 'artifacts/receipts/native-stable.json').exists()


def test_native_suites_reference_existing_tests():
    for name in ('stable', 'layers', 'shared'):
        tests = (ROOT / f'scripts/ci/native-{name}-tests.txt').read_text().splitlines()
        assert tests
        assert all((ROOT / test).is_file() for test in tests)


def test_native_receipt_rejects_failed_or_all_skipped_suite(tmp_path, monkeypatch):
    evidence = tmp_path / 'native-evidence/stable'
    evidence.mkdir(parents=True)
    (evidence / 'backend-identity.json').write_text(json.dumps({'source_commit': 'candidate'}))
    (tmp_path / 'backend').write_bytes(b'backend')
    for attrs in ('tests="1" failures="1"', 'tests="1" skipped="1"', 'tests="2" skipped="1"', 'tests="0"'):
        (evidence / 'tests.xml').write_text(f'<testsuites><testsuite {attrs}/></testsuites>')
        assert run_receipt(tmp_path, monkeypatch).returncode != 0
    assert not (tmp_path / 'artifacts/receipts/native-stable.json').exists()
