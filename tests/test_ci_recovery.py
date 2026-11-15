import importlib.util
import time
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ci_recovery', Path(__file__).resolve().parents[1] / 'scripts/ci/recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

SHA1, SHA2 = 'a' * 40, 'b' * 40
T1 = dict(pipeline_id='1', job_id='10', source_sha=SHA1, job_name='test', runner_id='7')
T2 = dict(T1, job_id='11')
T3 = dict(T1, pipeline_id='2', job_id='20', source_sha=SHA2)


def manifest():
    return dict(incident_id='incident', project='project', initial_target=T1,
                deadline_epoch=time.time() + 3600, max_infrastructure_repairs=1, max_source_repairs=1)


class Backend:
    def __init__(self):
        self.observations = []
        self.classifications = []
        self.results = []
        self.performed = []
        self.reconciled = []
        self.reconcile_result = None
        self.health_state = 'healthy'
        self.evidence_status = 'export-verified'
        self.events = []

    def observe(self, target):
        return self.observations.pop(0)

    def retain(self, observation):
        return dict(status=self.evidence_status, job_status=observation['status'], receipt_path='export.json')

    def classify(self, observation, evidence):
        return self.classifications.pop(0)

    def health(self):
        return dict(state=self.health_state, receipt_path='health.json')

    def perform(self, action, key, payload):
        self.performed.append((action, key, payload))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def reconcile_action(self, action, key, payload):
        self.reconciled.append((action, key, payload))
        return self.reconcile_result

    def emit(self, phase, state):
        self.events.append(phase)
        return {'journal': phase}


def obs(target, status):
    return dict(target, status=status)


def classification(kind, fingerprint):
    return dict(kind=kind, fingerprint=fingerprint, reason='observed failure')


def completed(**kwargs):
    return dict(status='completed', receipt_path='action.json', **kwargs)


def controller(tmp_path, backend, m=None):
    return recovery.RecoveryController(tmp_path / 'state.json', m or manifest(), backend)


def test_infrastructure_then_source_repair_and_new_sha_success(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed'), obs(T2, 'failed'), obs(T3, 'success')]
    b.classifications = [classification('infrastructure', 'disk'), classification('source', 'assertion')]
    b.results = [completed(), completed(target=T2), completed(source_sha=SHA2), completed(target=T3)]
    m = manifest()
    c = controller(tmp_path, b, m)
    for _ in range(5):
        state = c.step()
        c = controller(tmp_path, b, m)  # Every transition survives reopening.
    assert state['status'] == 'complete'
    assert [a[0] for a in b.performed] == ['repair_infrastructure', 'retry_job', 'repair_source', 'start_pipeline']
    assert [o['status'] for o in state['observations']] == ['failed', 'failed', 'success']
    assert [e['job_status'] for e in state['evidence']] == ['failed', 'failed', 'success']
    assert state['target'] == T3
    assert state['notifications'][-1]['phase'] == 'complete'


def test_repeated_failure_stops_before_second_repair(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed'), obs(T2, 'failed')]
    b.classifications = [classification('infrastructure', 'same'), classification('source', 'same')]
    b.results = [completed(), completed(target=T2)]
    c = controller(tmp_path, b)
    c.step(); c.step()
    state = c.step()
    assert state['status'] == 'attention' and state['reason'] == 'repeated-failure'
    assert len(b.performed) == 2
    assert len(state['evidence']) == 2


@pytest.mark.parametrize('problem', ['identity', 'evidence', 'health'])
def test_unsafe_observation_evidence_or_health_stops(tmp_path, problem):
    b = Backend()
    b.observations = [obs(dict(T1, job_id='999') if problem == 'identity' else T1, 'failed')]
    b.classifications = [classification('infrastructure', 'disk')]
    if problem == 'evidence':
        b.evidence_status = 'unknown'
    if problem == 'health':
        b.health_state = 'unknown'
    state = controller(tmp_path, b).step()
    assert state['status'] == 'attention'
    assert not b.performed
    assert state['reason'] in ('observation-unknown-or-mismatch', 'export-evidence-unknown', 'health-unknown')


def test_uncertain_action_only_reconciles_after_restart(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed')]
    b.classifications = [classification('infrastructure', 'disk')]
    b.results = [TimeoutError()]
    m = manifest()
    c = controller(tmp_path, b, m)
    state = c.step()
    assert state['phase'] == 'action_pending'
    b.reconcile_result = completed()
    state = controller(tmp_path, b, m).step()
    assert state['phase'] == 'dispatch_retry'
    assert len(b.performed) == len(b.reconciled) == 1
    assert b.performed[0][1] == b.reconciled[0][1]


def test_unresolved_action_never_repeats(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed')]
    b.classifications = [classification('infrastructure', 'disk')]
    b.results = [TimeoutError()]
    c = controller(tmp_path, b)
    c.step()
    state = c.step()
    assert state['status'] == 'attention' and state['reason'] == 'action-uncertain'
    c.step()
    assert len(b.performed) == 1 and len(b.reconciled) == 1


def test_running_is_pending_and_success_requires_healthy_receipt(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'running'), obs(T1, 'success')]
    c = controller(tmp_path, b)
    assert c.step()['status'] == 'pending'
    b.health_state = 'unknown'
    state = c.step()
    assert state['status'] == 'attention' and state['reason'] == 'health-unknown'
    assert state['evidence'][0]['job_status'] == 'success'


def test_exhausted_budget_stops_on_distinct_failure(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed'), obs(T2, 'failed')]
    b.classifications = [classification('infrastructure', 'first'), classification('infrastructure', 'second')]
    b.results = [completed(), completed(target=T2)]
    c = controller(tmp_path, b)
    c.step(); c.step()
    state = c.step()
    assert state['reason'] == 'infrastructure-budget-exhausted'
    assert len(b.performed) == 2


def test_action_completion_requires_receipt_and_notification_is_not_execution(tmp_path):
    b = Backend()
    b.observations = [obs(T1, 'failed')]
    b.classifications = [classification('source', 'bug')]
    b.results = [{'status': 'completed', 'source_sha': SHA2}]
    state = controller(tmp_path, b).step()
    assert state['status'] == 'attention'
    assert state['reason'] == 'action-failed-or-receipt-unknown'
    assert state['notifications'][-1]['phase'] == 'attention'
    assert [action for action, _, _ in b.performed] == ['repair_source']
