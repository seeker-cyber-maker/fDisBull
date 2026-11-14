import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'scripts/ci/production_held_reconcile.py'
spec = importlib.util.spec_from_file_location('held_reconcile_test_module', MODULE_PATH)
held = importlib.util.module_from_spec(spec)
spec.loader.exec_module(held)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_collected(monkeypatch, *, matching=False):
    source_sha = sha(MODULE_PATH.read_bytes())
    calls = []

    def fetch(path):
        calls.append(path)
        if path == '/user':
            data = {'login': held.EXPECTED_LOGIN, 'id': 314}
        else:
            rows = ([{'id': 93, 'workflow_id': held.WORKFLOW_ID,
                      'head_sha': sha(held.ACTION_KEY.encode())}] if matching else [])
            data = {'total_count': len(rows), 'workflow_runs': rows}
        return {'http_status': 200, 'data': data}

    result = held.collect_canonical_runs(fetch, collector_source_sha256=source_sha)
    assert len(calls) == 3
    budget_calls = []
    for index, request in enumerate(result['requests']):
        budget_calls.append({'path': request['path'], 'page': held._path_page(request['path']),
                             'status': 'complete', 'started_at': 1000 + index * 2,
                             'completed_at': 1001 + index * 2, 'http_status': 200,
                             'response_sha256': request['response_sha256']})
    result.update(mirror_pre=mirror_pre(), mirror_post=mirror_post(3, result['read_budget_sha256'] if 'read_budget_sha256' in result else '0' * 64),
                  read_budget_sha256='1' * 64, read_count=3, read_budget_calls=budget_calls)
    result['mirror_post'] = mirror_post(3, result['read_budget_sha256'])
    result['canonical_result_sha256'] = held._canonical_sha({k: v for k, v in result.items()
                                                              if k != 'canonical_result_sha256'})
    return result, source_sha


def action_file(key):
    return held.bridge_record_filename(key)


def mirror_pre():
    actions = {action_file(held.ACTION_KEY): held.ACTION_RECEIPT_SHA256,
               action_file(held.transport.BATCH_PREFIX + 'github'): held.BATCH_RECEIPT_SHA256}
    return {'anchor_sha256': held.ANCHOR_SHA256, 'sequence': 3,
            'action_sha256': held.ACTION_RECEIPT_SHA256, 'action_status': 'unknown',
            'action_request_sha256': held.REQUEST_SHA256, 'batch_sha256': held.BATCH_RECEIPT_SHA256,
            'batch_remaining': 99, 'provider_state_sha256': held.STATUS_SHA256,
            'provider_stop_reason': held.PROVIDER_STOP_REASON, 'provider_owner': held.transport.OWNER,
            'next_allowed_at': held.PROVIDER_STOP_EPOCH + 300,
            'installation_sha256': held.INSTALLATION_SHA256, 'action_count': 2, 'actions': actions}


def mirror_post(read_count, budget_sha):
    result = mirror_pre()
    read_key = held.READ_RECORD_PREFIX + sha(held.ACTION_KEY.encode())
    result['actions'] = {**result['actions'], action_file(read_key): budget_sha}
    result.update(sequence=3 + 2 * read_count + 2, action_count=3,
                  anchor_sha256='a' * 64)
    return result


def make_facts(monkeypatch):
    monkeypatch.setattr(held, '_decode_prestate', lambda _: {
        'document_sha256': held.PRESTATE_SHA256, 'action_sha256': held.ACTION_RECEIPT_SHA256,
        'batch_sha256': held.BATCH_RECEIPT_SHA256, 'provider_state_sha256': held.STATUS_SHA256})
    return {'schema': 'fdisbull-held-no-send-facts-1', 'prestate_sha256': held.PRESTATE_SHA256,
            'prestate_receipt': {'sealed_fixture': True},
            'genesis': {'readback_sha256': held.GENESIS_READBACK_SHA256,
                        'control_sha': held.GENESIS_CONTROL_SHA, 'all25modules_verified': True,
                        'provider_history_sequence': 0, 'provider_actions_before_live_check': 0,
                        'source_activation_sha256': held.SOURCE_ACTIVATION_SHA256,
                        'v0341_unchanged_sha256': held.V0341_UNCHANGED_SHA256},
            'native_invocation': {'invocation_id': held.NATIVE_INVOCATION_ID,
                                  'pid': held.NATIVE_INVOCATION_PID,
                                  'started_epoch': held.NATIVE_STARTED_EPOCH,
                                  'finished_epoch': held.NATIVE_FINISHED_EPOCH,
                                  'exit_code': held.NATIVE_EXIT_CODE, 'action_key': held.ACTION_KEY,
                                  'request_sha256': held.REQUEST_SHA256,
                                  'host_intent_sha256': held.HOST_INTENT_SHA256,
                                  'host_intent_epoch': 1794633633.228689,
                                  'service_error_sha256': held.SERVICE_ERROR_SHA256,
                                  'service_error_epoch': 1794633634.9547014,
                                  'deployed_bridge_sha256': held.DEPLOYED_BRIDGE_SHA256}}


def test_collector_reads_fixed_account_and_complete_stable_empty_run_list():
    calls = []

    def fetch(path):
        calls.append(path)
        data = {'login': held.EXPECTED_LOGIN, 'id': 10} if path == '/user' else {
            'total_count': 0, 'workflow_runs': []}
        return {'http_status': 200, 'data': data}

    result = held.collect_canonical_runs(fetch, collector_source_sha256='a' * 64)
    assert result['complete'] and result['stable'] and result['matching_run_ids'] == []
    assert calls == ['/user',
                     f'/repos/{held.REPOSITORY}/actions/workflows/{held.WORKFLOW_ID}/runs?per_page=100&page=1',
                     f'/repos/{held.REPOSITORY}/actions/workflows/{held.WORKFLOW_ID}/runs?per_page=100&page=1']


@pytest.mark.parametrize('mutator,reason', [
    (lambda response: response.update(data={'login': 'other', 'id': 10}), 'canonical_account_mismatch'),
    (lambda response: response.update(http_status=403), 'canonical_provider_non_200'),
])
def test_collector_fails_closed_on_identity_or_http_failure(mutator, reason):
    def fetch(path):
        response = {'http_status': 200, 'data': {'login': held.EXPECTED_LOGIN, 'id': 10}}
        mutator(response)
        return response

    with pytest.raises(held.ReconciliationUnknown, match=reason):
        held.collect_canonical_runs(fetch, collector_source_sha256='a' * 64)


def test_collector_rejects_page_change_and_duplicate_ids():
    n = 0

    def changing(path):
        nonlocal n
        n += 1
        if path == '/user':
            return {'http_status': 200, 'data': {'login': held.EXPECTED_LOGIN, 'id': 10}}
        return {'http_status': 200, 'data': {'total_count': 0 if n == 2 else 1,
                                              'workflow_runs': [] if n == 2 else [
                                                  {'id': 7, 'workflow_id': held.WORKFLOW_ID}]}}

    with pytest.raises(held.ReconciliationUnknown, match='canonical_snapshot_changed'):
        held.collect_canonical_runs(changing, collector_source_sha256='a' * 64)

    def duplicated(path):
        if path == '/user':
            return {'http_status': 200, 'data': {'login': held.EXPECTED_LOGIN, 'id': 10}}
        row = {'id': 7, 'workflow_id': held.WORKFLOW_ID}
        return {'http_status': 200, 'data': {'total_count': 2, 'workflow_runs': [row, row]}}

    with pytest.raises(held.ReconciliationUnknown, match='canonical_run_id_duplicate'):
        held.collect_canonical_runs(duplicated, collector_source_sha256='a' * 64)


def test_stable_matching_existing_run_is_collected_then_certificate_refuses(monkeypatch):
    canonical, source_sha = make_collected(monkeypatch, matching=True)
    assert canonical['stable'] and canonical['matching_run_ids'] == ['93']
    with pytest.raises(held.ReconciliationUnknown, match='canonical_run_set_or_nonce_match'):
        held.verify_no_send_certificate(make_facts(monkeypatch), canonical,
                                        expected_collector_sha256=source_sha)


def test_closed_certificate_binds_no_send_inference_and_mirror(monkeypatch):
    canonical, source_sha = make_collected(monkeypatch)
    facts = make_facts(monkeypatch)
    certificate = held.verify_no_send_certificate(facts, canonical,
                                                  expected_collector_sha256=source_sha)
    assert certificate['schema'] == 'fdisbull-held-no-send-certificate-1'
    assert certificate['verified'] is True
    assert certificate['no_api_process_started_source_bound'] is True
    assert certificate['no_api_process_started_basis'].startswith('inference_from_')
    assert certificate['mirror_post'] == canonical['mirror_post']
    assert certificate['certificate_sha256'] == held._canonical_sha(
        {k: v for k, v in certificate.items() if k != 'certificate_sha256'})


@pytest.mark.parametrize('mutate_facts,mutate_canonical', [
    (lambda f: f.update(prestate_sha256='0' * 64), lambda c: None),
    (lambda f: f['native_invocation'].update(finished_epoch=held.NATIVE_STARTED_EPOCH - 1), lambda c: None),
    (lambda f: None, lambda c: c['mirror_post']['actions'].update({'unexpected.json': 'f' * 64})),
    (lambda f: None, lambda c: c['read_budget_calls'][0].update(response_sha256='0' * 64)),
])
def test_certificate_rejects_changed_provenance_or_read_receipt(monkeypatch, mutate_facts, mutate_canonical):
    canonical, source_sha = make_collected(monkeypatch)
    facts = make_facts(monkeypatch)
    mutate_facts(facts); mutate_canonical(canonical)
    canonical['canonical_result_sha256'] = held._canonical_sha(
        {k: v for k, v in canonical.items() if k != 'canonical_result_sha256'})
    with pytest.raises(held.ReconciliationUnknown):
        held.verify_no_send_certificate(facts, canonical, expected_collector_sha256=source_sha)


def test_fixed_request_rejects_other_operation_without_prestate_io(monkeypatch):
    monkeypatch.setattr(held, 'load_prestate', lambda: pytest.fail('should not read prestate'))
    with pytest.raises(held.ReconciliationUnknown, match='fixed_canonical_read_request_required'):
        held.canonical_read({'operation': 'dispatch', 'action_key': held.ACTION_KEY,
                             'request_sha256': held.REQUEST_SHA256,
                             'prestate_sha256': held.PRESTATE_SHA256})
