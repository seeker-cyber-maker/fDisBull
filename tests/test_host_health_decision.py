"""The deployed CI health policy keeps storage observations without a reserve."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load('host_health_policy', ROOT / 'scripts/ci/health_decision.py')
adapter = load('host_health_adapter', ROOT / 'scripts/ci/offline-qualification.py')
NOW = 1_800_000_000


def snapshot():
    def item():
        return dict(state='healthy', reason='http_ok', checked_epoch=NOW - 1,
                    fresh=True)
    return dict(observed_epoch=NOW - 1, read_only=True, model_required=False,
                doctor_observation=item(), n8n_readiness=item(),
                health_checks={key: item() for key in policy.N8N},
                websites={key: item() for key in policy.SITES},
                disk=dict(state='known', free_bytes=1, checked_epoch=NOW - 1))


@pytest.mark.parametrize('free_bytes', [0, 1, 19_000_000_000, 20_100_000_000])
def test_known_low_disk_is_telemetry_not_a_health_failure(free_bytes):
    value = snapshot()
    value['disk']['free_bytes'] = free_bytes
    result = policy.evaluate(value, NOW)
    assert result['healthy'] is True
    assert result['failures'] == []
    assert result['disk'] == dict(state='known', free_bytes=free_bytes,
                                  minimum_free_bytes=None, failures=[])


@pytest.mark.parametrize('free_bytes', [None, -1, True, '100', float('inf'), float('nan')])
def test_invalid_disk_observations_remain_failures(free_bytes):
    value = snapshot()
    value['disk']['free_bytes'] = free_bytes
    result = policy.evaluate(value, NOW)
    assert result['healthy'] is False
    assert {'component': 'disk', 'reason': 'disk_free_missing_or_invalid'} in result['failures']


def test_missing_disk_observation_remains_a_failure():
    value = snapshot()
    del value['disk']
    result = policy.evaluate(value, NOW)
    assert result['healthy'] is False
    assert {'component': 'disk', 'reason': 'disk_state_not_known'} in result['failures']


@pytest.mark.parametrize('name', ['doctor', 'n8n_readiness', *policy.N8N, *policy.SITES])
def test_each_service_failure_still_blocks_ci(name):
    value = snapshot()
    item = (value['doctor_observation'] if name == 'doctor' else
            value['n8n_readiness'] if name == 'n8n_readiness' else
            value['health_checks'].get(name, value['websites'].get(name)))
    item.update(state='unhealthy', reason='probe_unavailable')
    result = policy.evaluate(value, NOW)
    assert result['healthy'] is False
    assert {'component': name, 'reason': 'state_not_healthy'} in result['failures']


def test_actual_journal_io_failure_cannot_be_adopted(tmp_path, monkeypatch):
    def fail_persist(*args):
        raise OSError('private-error-must-not-escape')
    monkeypatch.setattr(policy, 'persist', fail_persist)
    result = policy.capture(
        runner=lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(snapshot())),
        clock=lambda: NOW)
    assert result['healthy'] is True
    assert result['receipt']['durable'] is False
    assert 'private-error' not in json.dumps(result)
    adopted = adapter.capture_health(
        tmp_path / 'receipt.json', helper=ROOT / 'scripts/ci/health_decision.py',
        expected_sha256=hashlib.sha256((ROOT / 'scripts/ci/health_decision.py').read_bytes()).hexdigest(),
        runner=lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(result).encode()))
    assert adopted == {'continue': False, 'reason': 'helper_receipt_not_durable'}


def test_adapter_pin_matches_maintained_helper_source():
    assert adapter.HELPER_SHA256 == hashlib.sha256(
        (ROOT / 'scripts/ci/health_decision.py').read_bytes()).hexdigest()
