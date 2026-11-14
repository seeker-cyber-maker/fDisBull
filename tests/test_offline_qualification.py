"""No service is contacted; subprocess and helper bytes are test fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('offline_qualification', Path(__file__).parents[1] / 'scripts/ci/offline-qualification.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def helper(tmp_path):
    path = tmp_path / 'helper.py'
    path.write_bytes(b'fixture helper')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def record(healthy=True, durable=True):
    receipt = {'journal': '/var/lib/operations-health/decisions.sqlite', 'sequence': 1,
               'sha256': 'a' * 64, 'durable': True} if durable else {
                   'durable': False, 'reason': 'diagnostic_persistence_unavailable'}
    names = ('doctor', 'n8n_readiness', 'n8n_service', 'n8n_mcp', 'n8n_monitor_workflow',
             'n8n_assistant_key', 'https://www.brewsterjennings.ca/',
             'https://release.brewsterjennings.ca/')
    item = {'state': 'healthy', 'reason': 'http_ok', 'checked_epoch': 1,
            'age_seconds': 0, 'fresh': True, 'requires_source_freshness': True, 'failures': []}
    return {'schema_version': 1, 'healthy': healthy, 'observed_epoch': 1,
            'free_bytes': None, 'snapshot_observed_epoch': 1, 'snapshot_age_seconds': 0,
            'read_only': True, 'model_required': False, 'components': {n: dict(item) for n in names},
            'disk': {'state': 'known', 'free_bytes': 30000000000,
                     'minimum_free_bytes': 20100000000, 'failures': []},
            'failures': [], 'receipt': receipt}


def invoke(tmp_path, helper, output, *, code=0, name='receipt.json'):
    def run(args, **kwargs):
        assert args == ['/usr/bin/python3', str(helper[0])]
        assert kwargs['timeout'] >= 50
        if isinstance(output, Exception):
            raise output
        return subprocess.CompletedProcess(args, code, output, b'SECRET STDERR')
    path = tmp_path / name
    result = gate.capture_health(path, helper=helper[0], expected_sha256=helper[1], runner=run)
    return result, path


@pytest.mark.parametrize('healthy,durable,expected', [(True, True, True), (False, True, False),
                                                        (True, False, False), (False, False, False)])
def test_gate_requires_both_flags_and_retains_full_record(tmp_path, helper, healthy, durable, expected):
    payload = record(healthy, durable)
    result, path = invoke(tmp_path, helper, json.dumps(payload).encode())
    assert result['continue'] is expected
    assert json.loads(path.read_text())['record'] == payload
    assert 'SECRET' not in path.read_text()


@pytest.mark.parametrize('output,code,reason', [
    (b'SECRET invalid', 0, 'helper_json_invalid'),
    (b'{"healthy":true,"extra":"SECRET"}', 0, 'helper_schema_invalid'),
    (b'SECRET', 1, 'helper_process_failed'),
    (subprocess.TimeoutExpired('SECRET', 55, output=b'SECRET'), 0, 'helper_timeout'),
    (OSError('SECRET'), 0, 'helper_unavailable'),
    (b'x' * (gate.MAX_RECORD_BYTES + 1), 0, 'helper_output_invalid'),
])
def test_failure_receipts_do_not_store_raw_process_data(tmp_path, helper, output, code, reason):
    result, path = invoke(tmp_path, helper, output, code=code)
    receipt = json.loads(path.read_text())
    assert not result['continue'] and result['reason'] == reason
    assert receipt['failure'] == reason and receipt['record'] is None
    assert 'SECRET' not in path.read_text()


def test_hash_mismatch_does_not_execute_helper(tmp_path, helper):
    result = gate.capture_health(tmp_path / 'r', helper=helper[0], expected_sha256='0' * 64,
                                 runner=lambda *a, **k: pytest.fail('must not execute'))
    assert result == {'continue': False, 'reason': 'helper_hash_mismatch'}


def test_existing_or_unwritable_receipt_fails_closed(tmp_path, helper):
    existing = tmp_path / 'receipt.json'
    existing.write_text('untouched')
    result, _ = invoke(tmp_path, helper, json.dumps(record()).encode())
    assert result == {'continue': False, 'reason': 'caller_receipt_unavailable'}
    assert existing.read_text() == 'untouched'
    result = gate.capture_health(tmp_path / 'missing' / 'r', helper=helper[0], expected_sha256=helper[1],
        runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(record()).encode(), b''))
    assert result['reason'] == 'caller_receipt_unavailable'


def test_unknown_nested_field_is_never_retained(tmp_path, helper):
    payload = record(); payload['receipt']['stdout'] = 'SECRET'
    result, path = invoke(tmp_path, helper, json.dumps(payload).encode())
    assert result['reason'] == 'helper_schema_invalid'
    assert 'SECRET' not in path.read_text()


def test_empty_inventory_may_only_describe_a_failed_capture(tmp_path, helper):
    payload = {'schema_version': 1, 'healthy': False, 'observed_epoch': 1,
               'read_only': True, 'model_required': False, 'components': {},
               'failures': [{'component': 'snapshot', 'reason': 'snapshot_timeout'}],
               'receipt': record()['receipt']}
    result, path = invoke(tmp_path, helper, json.dumps(payload).encode())
    assert result['reason'] == 'unhealthy'
    assert json.loads(path.read_text())['record'] == payload
    payload['healthy'] = True
    result, path = invoke(tmp_path, helper, json.dumps(payload).encode(), name='other.json')
    assert result['reason'] == 'helper_schema_invalid'
    assert json.loads(path.read_text())['record'] is None
