"""Offline checks for the native CI success-evidence boundary."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / 'scripts/ci/native-receipt.py'


def ci_section(name):
    """Read one canonical top-level block; GitLab itself validates YAML syntax."""
    text = (ROOT / '.gitlab-ci.yml').read_text()
    match = re.search(r'^' + re.escape(name) + r':\n(.*?)(?=^[^\s#]|\Z)', text, re.M | re.S)
    assert match, f'Required CI section absent: {name}'
    return match.group(1)


def test_ci_wiring_cannot_drop_manual_full_qualification_during_a_merge():
    gate = ci_section('native-qualification')
    assert 'when: manual' in gate and 'allow_failure: false' in gate
    for name in ('native-qualification', '.native_qualification_rules'):
        conditions = [line.strip() for line in ci_section(name).splitlines() if line.strip().startswith('- if:')]
        assert conditions == ['- if: \'$CI_PIPELINE_SOURCE == "api" || $CI_PIPELINE_SOURCE == "web"\'']
        assert 'when: never' in ci_section(name)
    assert 'extends: .native_qualification_rules' in ci_section('.native_debugger_template')
    for name in ('native-debugger-stable', 'native-debugger-layers'):
        assert 'extends: .native_debugger_template' in ci_section(name)
    assert 'extends: .native_qualification_rules' in ci_section('native-unified')
    summary = ci_section('qualify-candidate')
    assert 'extends: .native_qualification_rules' in summary
    for name in ('test-and-package', 'native-debugger-stable', 'native-debugger-layers', 'native-unified'):
        assert f'    - {name}\n' in summary
    assert 'python scripts/check_ci_qualification.py --output' in summary
    assert 'bash scripts/ci/test-and-package.sh' in ci_section('test-and-package')
    for name in ('native-qualification', '.native_qualification_rules', '.native_debugger_template', 'native-unified', 'qualify-candidate'):
        assert 'allow_failure: true' not in ci_section(name)


def test_ordinary_job_requires_inventory_and_isolated_install_receipts():
    script = (ROOT / 'scripts/ci/test-and-package.sh').read_text()
    smoke = (ROOT / 'scripts/ci/package-smoke.sh').read_text()
    for operation in ('check_dist.py', 'check_package_payloads.py', 'bash scripts/ci/package-smoke.sh', '--write-ordinary'):
        assert operation in script
    assert script.index('bash scripts/ci/package-smoke.sh') < script.index('python -m pytest')
    assert script.index('check_package_payloads.py') < script.index('--write-ordinary')
    for operation in ('check_agent_skill.py', '-I -m fdisbull_player', '--output "$smoke_root/agent-skill.json"', '--output "$smoke_root/guide-skill.json"'):
        assert operation in smoke
    assert 'mktemp -d "$CI_BUILDS_DIR/' in smoke
    assert '--output artifacts/' not in smoke
    offline = (ROOT / 'scripts/ci/native-offline.sh').read_text()
    assert '--output "$kit_install_parent/agent-skill.json"' in offline
    assert '--output "$kit_install_parent/guide-skill.json"' in offline


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
