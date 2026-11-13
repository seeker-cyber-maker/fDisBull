import hashlib
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_gitlab', root / 'scripts/ci/recovery_gitlab.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = 'a' * 40
TARGET = dict(pipeline_id='1', job_id='10', source_sha=SHA, job_name='ci-recovery-rehearsal', runner_id='58990209')


class Provider:
    def __init__(self):
        self.calls = []
        self.responses = []
    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        value = self.responses.pop(0)
        if isinstance(value, Exception): raise value
        return value


class Transport:
    def __init__(self): self.responses = []; self.calls = []
    def __call__(self, code, payload):
        self.calls.append(payload)
        return self.responses.pop(0)


def config(tmp_path):
    marker = '{"ready":true}\n'
    return dict(repo_root=str(root), state_dir=str(tmp_path), provider_state_dir=str(tmp_path / 'shared-provider'), incident_id='incident', project_id=88349936,
                runner_id=58990209, ref='codex/repair', owner_id='owner',
                ssh_prefix=['ssh', '-oBatchMode=yes', 'ubuntu@127.0.0.1'], marker_bytes=marker,
                marker_sha256=hashlib.sha256(marker.encode()).hexdigest(),
                expected_boot_id='12345678-1234-1234-1234-123456789abc', deadline_epoch=time.time()+300)


def make(tmp_path):
    provider, transport = Provider(), Transport()
    backend = module.GitLabRecoveryBackend(config(tmp_path), SimpleNamespace(), lambda *a: None,
                                            transport=transport, provider=provider)
    return backend, provider, transport


def provider_job(job_id='10', status='failed', runner=58990209):
    return {'id': int(job_id), 'name': TARGET['job_name'], 'status': status,
            'pipeline': {'id': 1}, 'commit': {'id': SHA},
            'runner': {'id': runner} if runner else None, 'failure_reason': 'script_failure'}


def test_observation_binds_full_identity_and_runner(tmp_path):
    backend, provider, _ = make(tmp_path)
    provider.responses = [{'id': 1, 'project_id': 88349936, 'sha': SHA}, provider_job()]
    assert backend.prepare_step(None)
    result = backend.observe(TARGET)
    assert result['status'] == 'failed' and result['runner_verified'] is True
    assert result['failure_reason'] == 'script_failure'


def test_queued_runner_is_not_asserted_and_wrong_terminal_is_rejected(tmp_path):
    backend, provider, _ = make(tmp_path)
    backend.prepared = True
    pipe = {'id': 1, 'project_id': 88349936, 'sha': SHA}
    provider.responses = [pipe, provider_job(status='pending', runner=None), pipe, provider_job(runner=12)]
    assert backend.observe(TARGET)['runner_verified'] is False
    with pytest.raises(ValueError): backend.observe(TARGET)


def test_health_unknown_for_stale_or_incomplete_snapshot(tmp_path):
    backend, _, transport = make(tmp_path)
    now = int(time.time())
    check = {'state': 'healthy', 'checked_epoch': now, 'fresh': True}
    snapshot = {'observed_epoch': now, 'read_only': True, 'model_required': False,
                'boot_id': backend.config['expected_boot_id'], 'doctor_observation': check,
                'n8n_readiness': check, 'health_checks': {k: check for k in module.CHECKS},
                'websites': {k: check for k in module.WEBSITES},
                'disk': {'state': 'known', 'free_bytes': 21_000_000_000, 'checked_epoch': now}}
    transport.responses = [{'snapshot': snapshot, 'receipt_path': '/ci/health'},
                           {'snapshot': dict(snapshot, observed_epoch=now-500), 'receipt_path': '/ci/stale'},
                           {'snapshot': dict(snapshot, boot_id=None), 'receipt_path': '/ci/unknown'}]
    assert backend.health()['state'] == 'healthy'
    assert backend.health()['state'] == 'unknown'
    assert backend.health()['state'] == 'unknown'


def test_ambiguous_retry_reconciles_without_posting_again(tmp_path):
    backend, provider, transport = make(tmp_path)
    backend.prepared = True; backend._lease_held = True
    payload = {'project': '88349936', 'target': TARGET}
    provider.responses = [TimeoutError(), [dict(provider_job(job_id='11', status='pending', runner=None),
                                              created_at='2099-01-01T00:00:00Z')]]
    with pytest.raises(TimeoutError): backend.perform('retry_job', 'key', payload)
    transport.responses = [{'receipt_path': '/var/lib/fdisbull-ci/control/recovery/incident/action.json'}]
    result = backend.reconcile_action('retry_job', 'key', payload)
    assert result['target']['job_id'] == '11'
    assert [call[0] for call in provider.calls] == ['POST', 'GET']
    with pytest.raises(RuntimeError): backend.perform('retry_job', 'key', payload)
    assert [call[0] for call in provider.calls] == ['POST', 'GET']


def test_scope_and_classification_fail_closed(tmp_path):
    backend, _, _ = make(tmp_path)
    result = backend.classify({}, {'diagnostic': {'kind': 'source', 'reason': 'invented'}})
    assert result['kind'] == 'blocked'
    with pytest.raises(RuntimeError): backend.perform('retry_job', 'key', {'target': TARGET})
    bad = config(tmp_path)
    bad['marker_sha256'] = 'f' * 64
    with pytest.raises(ValueError): module.GitLabRecoveryBackend(bad, SimpleNamespace(), None, provider=Provider())


def test_provider_stop_persisted_and_reservation_blocks(tmp_path):
    backend, provider, _ = make(tmp_path)
    assert backend.prepare_step(None)
    provider.responses = [RuntimeError('GitLab GET returned HTTP 429')]
    with pytest.raises(RuntimeError): backend._request('GET', '/test')
    assert backend.prepare_step(None) is False


def test_retain_requires_legacy_trace_and_verified_remote_diagnostic(tmp_path):
    backend, _, transport = make(tmp_path)
    state = {'saved_jobs': {}}
    def save_trace(provider, job, saved):
        saved['saved_jobs'][str(job['id'])] = {'trace_available': True}
    backend.legacy = SimpleNamespace(REMOTE_PUT='root="old"\n', load_state=lambda: state,
                                     save_trace=save_trace)
    backend.jobs['10'] = provider_job()
    observation = dict(TARGET, status='failed', failure_reason='script_failure')
    diagnostic = {'kind': 'infrastructure', 'reason': 'missing_ci_owned_input',
                  'input_sha256': backend.config['marker_sha256']}
    transport.responses = [{'path': '/helper'},
                           {'receipt_path': '/var/lib/fdisbull-ci/control/recovery/incident/export.json',
                            'result': {'status': 'export-verified', 'job_status': 'failed', 'diagnostic': diagnostic}},
                           {'stage': 'journaled', 'execution_performed': False}]
    evidence = backend.retain(observation)
    assert backend.classify(observation, evidence)['kind'] == 'infrastructure'
    assert [p['op'] for p in transport.calls] == ['install_verifier', 'verify', 'emit']
    assert transport.calls[-1]['event']['phase'] == 'down'


def test_repair_reconciliation_does_not_reserve_provider_refresh(tmp_path):
    backend, _, _ = make(tmp_path)
    assert backend.prepare_step({'phase': 'action_pending', 'actions': [{'action': 'repair_infrastructure'}]})
    assert backend.next_refresh_at is None


def test_down_phase_reuses_immutable_first_identity_after_restart(tmp_path):
    backend, _, transport = make(tmp_path)
    first = dict(TARGET, status='failed')
    path = tmp_path / 'down-incident.json'
    path.write_text(json.dumps({'observation': first, 'receipt_path': '/var/lib/fdisbull-ci/control/recovery/incident/first.json'}))
    state = {'saved_jobs': {}}
    def save_trace(provider, job, saved):
        saved['saved_jobs'][str(job['id'])] = {'trace_available': True}
    backend.legacy = SimpleNamespace(REMOTE_PUT='root="old"\n', load_state=lambda: state, save_trace=save_trace)
    backend.jobs['11'] = provider_job(job_id='11')
    transport.responses = [{'path': '/helper'}, {'receipt_path': '/var/lib/fdisbull-ci/control/recovery/incident/second.json',
                           'result': {'status': 'export-verified', 'job_status': 'failed', 'diagnostic': {}}},
                           {'stage': 'journaled'}]
    backend.retain(dict(first, job_id='11'))
    event = transport.calls[-1]['event']
    assert event['context']['job_id'] == '10'
    assert event['context']['receipt_path'].endswith('/first.json')


def test_incidents_share_provider_reservation_and_stop(tmp_path):
    backend, provider, _ = make(tmp_path)
    second_config = config(tmp_path / 'another')
    second_config['incident_id'] = 'other'
    second_config['provider_state_dir'] = str(tmp_path / 'shared-provider')
    second = module.GitLabRecoveryBackend(second_config, SimpleNamespace(), None, provider=Provider())
    assert backend.prepare_step(None)
    assert not second.prepare_step(None)
    provider.responses = [RuntimeError('GitLab GET returned HTTP 403')]
    with pytest.raises(RuntimeError): backend._request('GET', '/test')
    assert not second.prepare_step(None)


def test_default_provider_state_uses_git_common_directory(tmp_path):
    values = config(tmp_path)
    del values['provider_state_dir']
    backend = module.GitLabRecoveryBackend(values, SimpleNamespace(), None, provider=Provider())
    assert backend.provider_state_dir == module.CI_STATUS.default_state_dir(root)


def test_bootstrap_pipeline_accepts_planned_placeholder(tmp_path):
    backend, provider, transport = make(tmp_path)
    backend.prepared = True
    backend._lease_held = True
    placeholder = dict(TARGET, pipeline_id='0', job_id='0')
    payload = {'project': '88349936', 'target': placeholder, 'source_sha': SHA}
    provider.responses = [{'commit': {'id': SHA}}, {'id': 2},
                          {'id': 2, 'project_id': 88349936, 'sha': SHA, 'ref': 'codex/repair'},
                          [dict(provider_job(job_id='20', status='pending', runner=None), pipeline={'id': 2})]]
    transport.responses = [{'receipt_path': '/var/lib/fdisbull-ci/control/recovery/incident/bootstrap.json'}]
    result = backend.perform('start_pipeline', 'incident:bootstrap', payload)
    assert result['target']['pipeline_id'] == '2' and result['target']['job_id'] == '20'
    assert [x[0] for x in provider.calls] == ['GET', 'POST', 'GET', 'GET']
