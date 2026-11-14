import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'production_policy', Path(__file__).resolve().parents[1] / 'scripts/ci/production_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

TARGET = {
    'provider': 'github', 'repository': 'seeker-cyber-maker/fDisBull', 'run_id': '100',
    'run_attempt': '1', 'job_id': '200', 'source_sha': 'a' * 40, 'job_name': 'qualification',
    'runner_id': '21', 'ref': 'codex/recovery', 'control_sha': 'b' * 40,
}
POLICY_BYTES = b'{"authorized":true}\n'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    control = tmp_path / 'control' / 'production'
    control.mkdir(parents=True)
    control.chmod(0o700)
    canonical = control / 'qualification-policy.canonical.json'
    canonical.write_bytes(POLICY_BYTES)
    canonical.chmod(0o400)
    active_root = control / 'job-inputs'
    active_root.mkdir(mode=0o700)
    active_root.chmod(0o700)
    active = active_root / 'qualification-policy.json'
    monkeypatch.setattr(policy, 'CONTROL_ROOT', control)
    monkeypatch.setattr(policy, 'CANONICAL_POLICY', canonical)
    monkeypatch.setattr(policy, 'ACTIVE_ROOT', active_root)
    monkeypatch.setattr(policy, 'ACTIVE_POLICY', active)
    monkeypatch.setattr(policy, 'EXPECTED_SHA256', hashlib.sha256(POLICY_BYTES).hexdigest())
    private = tmp_path / 'private-incidents'
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    repair = policy.KnownInputRepair(private, ensure_lease=lambda: True)
    return {'control': control, 'canonical': canonical, 'active': active, 'private': private, 'repair': repair}


def evidence(target=TARGET, *, diagnostic=None, diagnostic_sha256='c' * 64, **flags):
    diagnostic = diagnostic or {
        'kind': 'infrastructure', 'reason': 'missing_ci_owned_input',
        'input_key': 'qualification-policy', 'expected_sha256': policy.EXPECTED_SHA256,
        'target': dict(target),
    }
    result = {
        'status': 'export-verified', 'job_status': 'failed', 'target': dict(target),
        'receipt_path': '/private/evidence.json', 'host_export_verified': True,
        'closed_inventory_verified': True, 'source_postcheck_verified': True,
        'provider_trace_verified': True, 'diagnostic': diagnostic,
        'diagnostic_sha256': diagnostic_sha256,
    }
    result.update(flags)
    return result


def observation(target=TARGET):
    return {**target, 'status': 'failed'}


def payload(target=TARGET, *, obs=None, ev=None):
    obs = observation(target) if obs is None else obs
    ev = evidence(target) if ev is None else ev
    return {'project': target['repository'], 'target': dict(target), 'observation': obs,
            'evidence': ev, 'classification': policy.classify(obs, ev)}


def test_classifier_requires_exact_hash_bound_diagnostic_and_closed_identity():
    good = policy.classify(observation(), evidence())
    assert good['eligible_for_repair'] is True
    assert good['kind'] == 'infrastructure'
    assert good['expected_sha256'] == policy.EXPECTED_SHA256

    wrong = evidence(diagnostic_sha256='not-a-sha')
    assert policy.classify(observation(), wrong)['kind'] == 'blocked'
    for change in (
        {'reason': 'other'}, {'input_key': 'another-input'}, {'expected_sha256': '0' * 64},
        {'target': {**TARGET, 'job_id': '201'}}, {'extra': 'field'},
    ):
        diag = {**evidence()['diagnostic'], **change}
        assert policy.classify(observation(), evidence(diagnostic=diag))['kind'] == 'blocked'
    assert policy.classify(observation(), evidence(closed_inventory_verified=False))['kind'] == 'blocked'
    assert policy.classify(observation(), evidence(receipt_path=''))['kind'] == 'blocked'
    assert policy.classify({**observation(), 'status': 'success'}, evidence())['kind'] == 'blocked'


def test_wrong_or_incomplete_target_is_blocked():
    assert policy.classify(observation({**TARGET, 'runner_id': '22'}), evidence({**TARGET, 'runner_id': '22'}))['kind'] == 'blocked'
    assert policy.classify(observation({**TARGET, 'repository': 'other/repo'}), evidence({**TARGET, 'repository': 'other/repo'}))['kind'] == 'blocked'
    bad = dict(TARGET); bad.pop('control_sha')
    assert policy.classify(observation(bad), evidence(bad))['kind'] == 'blocked'


def test_repair_creates_only_fixed_active_file_and_durable_receipt(setup):
    item = setup
    result = item['repair'].repair('incident-1:repair-1', payload())
    assert result['status'] == 'completed'
    assert item['active'].read_bytes() == POLICY_BYTES
    assert item['active'].stat().st_mode & 0o777 == 0o644
    receipt = json.loads(Path(result['receipt_path']).read_text())
    assert receipt['origin'] == 'exclusive-create'
    assert receipt['active_sha256'] == policy.EXPECTED_SHA256
    assert item['repair'].reconcile('incident-1:repair-1', payload()) == result


def test_identical_existing_file_is_receipted_without_replacement(setup):
    item = setup
    item['active'].write_bytes(POLICY_BYTES)
    item['active'].chmod(0o644)
    before = item['active'].stat()
    result = item['repair'].repair('incident-1:existing', payload())
    after = item['active'].stat()
    assert result['status'] == 'completed'
    assert (after.st_dev, after.st_ino, after.st_mtime_ns) == (before.st_dev, before.st_ino, before.st_mtime_ns)
    assert json.loads(Path(result['receipt_path']).read_text())['origin'] == 'existing-identical'
    assert item['repair'].reconcile('incident-1:existing', payload()) == result


def test_nonidentical_or_symlink_active_input_refuses_without_overwrite(setup, tmp_path):
    item = setup
    item['active'].write_bytes(b'old-policy')
    item['active'].chmod(0o644)
    with pytest.raises(RuntimeError, match='conflict'):
        item['repair'].repair('incident-1:conflict', payload())
    assert item['active'].read_bytes() == b'old-policy'
    assert item['repair'].reconcile('incident-1:conflict', payload()) is None

    item['active'].unlink()
    outside = tmp_path / 'outside'
    outside.write_bytes(POLICY_BYTES)
    item['active'].symlink_to(outside)
    with pytest.raises((OSError, ValueError, RuntimeError)):
        item['repair'].repair('incident-1:symlink', payload())
    assert outside.read_bytes() == POLICY_BYTES


def test_job_input_directory_must_be_preinstalled_private(setup):
    item = setup
    active_root = item['active'].parent
    active_root.chmod(0o755)
    with pytest.raises(RuntimeError, match='active policy parent unsafe'):
        item['repair'].repair('incident-1:wide-dir', payload())
    assert not item['active'].exists()
    assert not list(item['private'].glob('*.intent.json'))

    active_root.chmod(0o700)
    active_root.rmdir()
    with pytest.raises(RuntimeError, match='active policy parent unsafe'):
        item['repair'].repair('incident-1:missing-dir', payload())
    assert not active_root.exists()


def test_wrong_action_payload_and_missing_lease_never_mutate(setup):
    item = setup
    wrong = payload()
    wrong['classification']['target'] = {**TARGET, 'job_id': '201'}
    with pytest.raises(ValueError):
        item['repair'].repair('incident-1:wrong', wrong)
    assert not item['active'].exists()

    item['repair'].ensure_lease = lambda: False
    with pytest.raises(RuntimeError, match='lease'):
        item['repair'].repair('incident-1:no-lease', payload())
    assert not item['active'].exists()


def test_reconcile_needs_exclusive_creation_proof_for_missing_receipt(setup):
    item = setup
    key = 'incident-1:interrupted'
    target = policy.classify(observation(), evidence())['target']
    root, intent_path, created_path, receipt_path = item['repair']._paths(key)
    intent = {'schema': 'fdisbull-known-input-intent-1', 'key': key, 'target': target,
              'input_key': 'qualification-policy', 'expected_sha256': policy.EXPECTED_SHA256,
              'status': 'prepared'}
    intent_path.write_bytes(policy._json_bytes(intent)); intent_path.chmod(0o600)
    item['active'].write_bytes(POLICY_BYTES); item['active'].chmod(0o644)
    assert item['repair'].reconcile(key, payload()) is None

    st = item['active'].stat()
    created = {'schema': 'fdisbull-known-input-created-1', 'key': key, 'target': target,
               'expected_sha256': policy.EXPECTED_SHA256, 'active_dev': st.st_dev,
               'active_ino': st.st_ino, 'active_sha256': policy.EXPECTED_SHA256}
    created_path.write_bytes(policy._json_bytes(created)); created_path.chmod(0o600)
    result = item['repair'].reconcile(key, payload())
    assert result['status'] == 'completed'
    assert json.loads(receipt_path.read_text())['origin'] == 'exclusive-create'


def test_repeated_repair_and_canonical_drift_fail_closed(setup):
    item = setup
    key = 'incident-1:once'
    first = item['repair'].repair(key, payload())
    with pytest.raises(RuntimeError, match='reconcile only'):
        item['repair'].repair(key, payload())
    item['canonical'].chmod(0o600)
    item['canonical'].write_bytes(b'changed')
    assert item['repair'].reconcile(key, payload()) is None
    assert item['active'].read_bytes() == POLICY_BYTES
