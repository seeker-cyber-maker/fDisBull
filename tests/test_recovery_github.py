import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('recovery_github', Path(__file__).parents[1] / 'scripts/ci/recovery_github.py')
github = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github)

CONTROL, SOURCE = 'a' * 40, 'b' * 40
TARGET = {'provider': 'github', 'repository': 'org/repo', 'run_id': '10', 'run_attempt': '1',
          'job_id': '20', 'source_sha': SOURCE, 'job_name': 'native', 'runner_id': '21',
          'ref': 'codex/control', 'control_sha': CONTROL}


class Fixture:
    def __init__(self):
        self.calls = []; self.proofs = {}; self.responses = {}; self.claimed = set()
        self.run = {'id': 10, 'run_attempt': 1, 'head_sha': CONTROL, 'repository': {'full_name': 'org/repo'}, 'head_branch': 'codex/control'}
        self.job = {'id': 20, 'run_id': 10, 'name': 'native', 'head_sha': CONTROL,
                    'runner_id': 21, 'status': 'completed', 'conclusion': 'failure'}
        self.source_ok = True; self.evidence = None
    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if (method, path) in self.responses:
            value = self.responses[method, path]
            if isinstance(value, Exception): raise value
            return copy.deepcopy(value) if method == 'POST' else {'http_status': 200, 'data': copy.deepcopy(value), 'request_id': None}
        if path.endswith('/runs/10'):
            value = {**self.run, 'run_attempt': 2} if self.proofs else self.run
            return {'http_status': 200, 'data': copy.deepcopy(value), 'request_id': None}
        if path.endswith('/attempts/1'): return {'http_status': 200, 'data': copy.deepcopy(self.run), 'request_id': None}
        if path.endswith('/attempts/1/jobs?per_page=100&page=1'):
            return {'http_status': 200, 'data': {'total_count': 1, 'jobs': [copy.deepcopy(self.job)]}, 'request_id': None}
        if path.endswith('/jobs/20'): return {'http_status': 200, 'data': copy.deepcopy(self.job), 'request_id': None}
        raise ValueError('fixture path missing')
    def for_action(self, key):
        return self.request
    def receipt(self, key):
        return {'receipt': None}
    def source(self, target, run, job):
        return {'verified': self.source_ok, 'target': target, 'receipt_path': 'candidate.json'}
    def save(self, key, proof):
        self.proofs[key] = {'proof': proof, 'receipt_path': 'accepted.json'}
        return 'accepted.json'
    def claim(self, action, key, payload):
        new = key not in self.claimed
        self.claimed.add(key)
        return {'durable': True, 'new': new}
    def backend(self, **kwargs):
        options = dict(repository='org/repo', control_sha=CONTROL, transport=self, source_binding=self.source,
            retain=lambda obs, required: self.evidence, classify=lambda obs, evidence: None,
            health=lambda: {'state': 'healthy', 'receipt_path': 'health.json'},
            emit=lambda phase, state: {'phase': phase}, claim_action=self.claim, save_acceptance=self.save,
            load_acceptance=lambda key: self.proofs.get(key), repair_infrastructure=lambda k, p: None,
            repair_source=lambda k, p: None, resolve_dispatch=lambda k, proof, payload: None,
            reconcile_other=lambda a, k, p: None, lease=lambda: True, required_artifacts=['qualification'], workflow_id=123)
        options.update(kwargs)
        return github.GitHubRecoveryBackend(**options)


def test_observe_binds_canonical_attempt_job_and_independent_candidate():
    f = Fixture(); result = f.backend().observe(TARGET)
    assert result['status'] == 'failed' and result['source_sha'] == SOURCE
    assert result['control_sha'] == CONTROL and result['source_binding_receipt'] == 'candidate.json'


@pytest.mark.parametrize('mutation', ['repository', 'control', 'attempt', 'job', 'runner', 'source'])
def test_observe_refuses_identity_mismatch(mutation):
    f = Fixture()
    if mutation == 'repository': f.run['repository']['full_name'] = 'other/repo'
    if mutation == 'control': f.run['head_sha'] = SOURCE
    if mutation == 'attempt': f.run['run_attempt'] = 2
    if mutation == 'job': f.job['run_id'] = 11
    if mutation == 'runner': f.job['runner_id'] = 22
    if mutation == 'source': f.source_ok = False
    with pytest.raises(ValueError): f.backend().observe(TARGET)


def test_retention_requires_host_export_failed_log_and_required_artifact():
    f = Fixture(); b = f.backend(); obs = b.observe(TARGET)
    f.evidence = {'status': 'export-verified', 'job_status': 'failed', 'target': TARGET,
                  'receipt_path': 'export.json', 'host_export_verified': True,
                  'failed_log_verified': True, 'verified_artifacts': ['qualification']}
    assert b.retain(obs) == f.evidence
    for field in ('host_export_verified', 'failed_log_verified'):
        old = f.evidence[field]; f.evidence[field] = [] if field == 'verified_artifacts' else False
        with pytest.raises(ValueError): b.retain(obs)
        f.evidence[field] = old


def test_classification_requires_verified_callback():
    f = Fixture(); b = f.backend(classify=lambda o, e: {'kind': 'source', 'reason': 'x', 'fingerprint': 'x'})
    assert b.classify({}, {})['kind'] == 'blocked'


def test_retry_accepted_and_canonical_attempt_required():
    f = Fixture(); b = f.backend()
    newer = {**f.job, 'id': 22, 'status': 'in_progress', 'conclusion': None}
    f.responses['POST', b.base + '/jobs/20/rerun'] = {'http_status': 201, 'data': None, 'request_id': 'ABC:123'}
    f.responses['GET', b.base + '/runs/10/attempts/2'] = {**f.run, 'run_attempt': 2}
    f.responses['GET', b.base + '/runs/10/attempts/2/jobs?per_page=100&page=1'] = {'total_count': 1, 'jobs': [newer]}
    f.responses['GET', b.base + '/jobs/22'] = newer
    outcome = b.perform('retry_job', 'incident:1', {'target': TARGET})
    assert outcome['target'] == {**TARGET, 'job_id': '22', 'run_attempt': '2'}
    assert f.proofs['incident:1']['proof']['envelope']['http_status'] == 201
    assert outcome['origin_proof']['kind'] == 'durable-accepted-action'
    assert sum(method == 'POST' for method, _, _ in f.calls) == 1


def test_unknown_response_cannot_be_reconciled_or_reissued():
    f = Fixture(); b = f.backend()
    f.responses['POST', b.base + '/jobs/20/rerun'] = TimeoutError('unknown')
    with pytest.raises(TimeoutError): b.perform('retry_job', 'one', {'target': TARGET})
    assert b.reconcile_action('retry_job', 'one', {'target': TARGET}) is None
    with pytest.raises(RuntimeError, match='reconcile only'):
        b.perform('retry_job', 'one', {'target': TARGET})
    assert sum(method == 'POST' for method, _, _ in f.calls) == 1


def test_accepted_retry_without_unique_canonical_attempt_stops():
    f = Fixture(); b = f.backend()
    f.responses['POST', b.base + '/jobs/20/rerun'] = {'http_status': 201, 'data': None, 'request_id': None}
    f.responses['GET', b.base + '/runs/10/attempts/2'] = {**f.run, 'run_attempt': 2}
    newer = {**f.job, 'id': 22}
    f.responses['GET', b.base + '/runs/10/attempts/2/jobs?per_page=100&page=1'] = {
        'total_count': 2, 'jobs': [newer, {**newer, 'id': 23}]}
    assert b.perform('retry_job', 'one', {'target': TARGET}) is None
    assert b.reconcile_action('retry_job', 'one', {'target': TARGET}) is None
    assert len([x for x in f.calls if x[0] == 'POST']) == 1


def test_transport_status_must_be_accepted_and_saved_before_reads():
    f = Fixture(); b = f.backend()
    f.responses['POST', b.base + '/jobs/20/rerun'] = {'http_status': 403, 'data': None, 'request_id': None}
    with pytest.raises(RuntimeError, match='response unknown'):
        b.perform('retry_job', 'one', {'target': TARGET})
    assert b.reconcile_action('retry_job', 'one', {'target': TARGET}) is None
    assert not any('/attempts/2' in path for method, path, _ in f.calls)


def test_extra_artifact_does_not_match_exact_manifest():
    f = Fixture(); f.job['conclusion'] = 'success'; b = f.backend(); obs = b.observe(TARGET)
    f.evidence = {'status': 'export-verified', 'job_status': 'success', 'target': TARGET,
                  'receipt_path': 'export.json', 'host_export_verified': True,
                  'failed_log_verified': True, 'verified_artifacts': ['qualification', 'extra']}
    with pytest.raises(ValueError): b.retain(obs)


def test_classification_needs_explicit_repair_eligibility():
    f = Fixture()
    classification = {'verified': True, 'kind': 'infrastructure', 'reason': 'restricted', 'fingerprint': 'x'}
    b = f.backend(classify=lambda o, e: classification)
    assert b.classify({}, {})['kind'] == 'blocked'
    classification['eligible_for_repair'] = True
    assert b.classify({}, {})['kind'] == 'infrastructure'


def test_adapter_integrates_with_production_controller_success(tmp_path):
    import time
    core_spec = importlib.util.spec_from_file_location('recovery_core_fixture', Path(__file__).parents[1] / 'scripts/ci/recovery.py')
    core = importlib.util.module_from_spec(core_spec); core_spec.loader.exec_module(core)
    f = Fixture(); f.job['conclusion'] = 'success'
    checkout = {k: TARGET[k] for k in ('source_sha', 'control_sha', 'run_id', 'run_attempt', 'job_id')}
    checkout.update(verified=True, receipt_path='checkout.json')
    f.evidence = {'status': 'export-verified', 'job_status': 'success', 'target': TARGET,
                  'receipt_path': 'export.json', 'host_export_verified': True,
                  'required_artifacts_verified': True, 'required_artifacts_receipt': 'artifact.json',
                  'candidate_checkout': checkout, 'verified_artifacts': ['qualification']}
    manifest = {'incident_id': 'incident', 'project': 'org/repo', 'initial_target': TARGET,
                'deadline_epoch': time.time() + 100, 'max_infrastructure_repairs': 1,
                'max_source_repairs': 1, 'required_artifacts': ['qualification']}
    state = core.RecoveryController(tmp_path / 'state.json', manifest, f.backend()).step()
    assert state['status'] == 'complete'
    assert state['evidence'][0]['candidate_checkout'] == checkout


def test_new_source_dispatch_requires_204_and_verified_nonce_link():
    f = Fixture(); new_sha = 'c' * 40
    new_target = {**TARGET, 'run_id': '11', 'job_id': '23', 'source_sha': new_sha}
    def resolve(key, proof, payload):
        return {'verified': True, 'target': new_target,
                'nonce': proof['request']['payload']['inputs']['nonce'], 'receipt_path': 'origin.json'}
    b = f.backend(resolve_dispatch=resolve)
    path = b.base + '/workflows/123/dispatches'
    f.responses['POST', path] = {'http_status': 204, 'data': None, 'request_id': None}
    f.responses['GET', b.base + '/runs/11/attempts/1'] = {**f.run, 'id': 11}
    job = {**f.job, 'id': 23, 'run_id': 11, 'status': 'in_progress', 'conclusion': None}
    f.responses['GET', b.base + '/jobs/23'] = job
    f.responses['GET', b.base + '/runs/11/attempts/1/jobs?per_page=100&page=1'] = {'total_count': 1, 'jobs': [job]}
    payload = {'target': TARGET, 'source_sha': new_sha, 'candidate_ref': 'codex/repair'}
    result = b.perform('start_pipeline', 'dispatch-key', payload)
    assert result['target'] == new_target and result['candidate_ref'] == 'codex/repair'
    assert result['origin_proof']['action_key'] == 'dispatch-key'
    request = next(x for x in f.calls if x[0] == 'POST')
    assert request[2]['inputs']['candidate_sha'] == new_sha and len(request[2]['inputs']['nonce']) == 64


def test_new_source_unknown_origin_never_completes_or_reissues():
    f = Fixture(); b = f.backend()
    f.responses['POST', b.base + '/workflows/123/dispatches'] = {'http_status': 204, 'data': None, 'request_id': None}
    payload = {'target': TARGET, 'source_sha': 'c' * 40, 'candidate_ref': 'codex/repair'}
    assert b.perform('start_pipeline', 'one', payload)['status'] == 'pending'
    assert b.reconcile_action('start_pipeline', 'one', payload)['status'] == 'pending'
    with pytest.raises(RuntimeError, match='reconcile only'):
        b.perform('start_pipeline', 'one', payload)
    assert len([x for x in f.calls if x[0] == 'POST']) == 1


def test_remote_accepted_receipt_recovers_local_loss_without_post():
    f = Fixture(); repo = 'seeker-cyber-maker/fDisBull'
    f.run['repository']['full_name'] = repo
    b = f.backend(repository=repo, workflow_id=417757453)
    target = {**TARGET, 'repository': repo}
    path = b.base + '/jobs/20/rerun'
    digest = github._transport.request_digest('github', 'POST', path, {})
    f.receipt = lambda key: {'receipt': {'action_key': key, 'status': 'accepted',
        'request_sha256': digest, 'envelope': {'http_status': 201, 'data': None, 'request_id': None}}}
    f.responses['GET', b.base + '/runs/10/attempts/2'] = {**f.run, 'run_attempt': 2}
    newer = {**f.job, 'id': 22}
    f.responses['GET', b.base + '/runs/10/attempts/2/jobs?per_page=100&page=1'] = {'total_count': 1, 'jobs': [newer]}
    f.responses['GET', b.base + '/jobs/22'] = newer
    outcome = b.reconcile_action('retry_job', 'one', {'target': target})
    assert outcome['status'] == 'completed' and f.proofs['one']['receipt_path'] == 'accepted.json'
    assert not any(method == 'POST' for method, _, _ in f.calls)


def test_accepted_retry_waits_for_next_attempt_without_reissuing():
    f = Fixture(); b = f.backend()
    f.responses['POST', b.base + '/jobs/20/rerun'] = {'http_status': 201, 'data': None, 'request_id': None}
    f.responses['GET', b.base + '/runs/10'] = f.run
    result = b.perform('retry_job', 'one', {'target': TARGET})
    assert result['status'] == 'pending' and result['origin_proof']['verified']
    assert b.reconcile_action('retry_job', 'one', {'target': TARGET})['status'] == 'pending'
    assert len([x for x in f.calls if x[0] == 'POST']) == 1


def test_hook_only_fires_after_durable_acceptance():
    f = Fixture(); calls=[]; b=f.backend(after_acceptance=lambda *args:calls.append(args))
    f.responses['POST', b.base + '/jobs/20/rerun'] = {'http_status':403, 'data':None, 'request_id':None}
    with pytest.raises(RuntimeError): b.perform('retry_job','one',{'target':TARGET})
    assert calls == []


def test_hook_runs_only_after_acceptance_receipt_and_is_reconcilable():
    f = Fixture(); calls=[]
    def hook(action, key, payload, proof):
        assert f.proofs[key]['proof'] == proof
        calls.append((action,key))
    b=f.backend(after_acceptance=hook)
    f.responses['POST', b.base+'/jobs/20/rerun']={'http_status':201,'data':None,'request_id':None}
    f.responses['GET', b.base+'/runs/10']=f.run
    assert b.perform('retry_job','one',{'target':TARGET})['status']=='pending'
    assert b.reconcile_action('retry_job','one',{'target':TARGET})['status']=='pending'
    assert calls == [('retry_job','one'),('retry_job','one')]
    assert len([row for row in f.calls if row[0]=='POST'])==1


def canonical_unknown_fixture():
    f=Fixture();repository='seeker-cyber-maker/fDisBull'
    target={**TARGET,'repository':repository,'job_name':'qualification'}
    key='incident:2:retry_job';payload={'target':target,'project':repository}
    timestamp=1794642705.0
    intent={'action':'retry_job','action_key':key,'payload':payload,'created_epoch':timestamp}
    opts={'repository':repository,'actor':'seeker-cyber-maker','sole_executor_authority':True,
          'load_intent':lambda k:{'intent':copy.deepcopy(intent),'receipt_path':'intent.json'}}
    b=f.backend(**opts);path=b.base+'/jobs/20/rerun'
    digest=github._transport.request_digest('github','POST',path,{})
    f.receipt=lambda k:{'receipt':{'action_key':k,'request_sha256':digest,'status':'unknown'}}
    run={'id':10,'run_attempt':2,'head_sha':CONTROL,'head_branch':'codex/control',
         'repository':{'full_name':repository},'actor':{'login':'seeker-cyber-maker'},
         'triggering_actor':{'login':'seeker-cyber-maker'},'workflow_id':123}
    job={'id':22,'run_id':10,'name':'qualification','head_sha':CONTROL,'created_at':'2026-11-14T07:51:46Z',
         'runner_id':0,'status':'queued','conclusion':None}
    f.responses['GET',b.base+'/runs/10']=run
    f.responses['GET',b.base+'/runs/10/attempts/2']=run
    f.responses['GET',b.base+'/runs/10/attempts/2/jobs?per_page=100&page=1']={'total_count':1,'jobs':[job]}
    f.responses['GET',b.base+'/jobs/22']=job
    return f,b,target,key,payload,intent,run,job


def test_unknown_retry_reconciles_canonical_queued_then_assigned_without_post():
    f,b,target,key,payload,intent,run,job=canonical_unknown_fixture();callbacks=[]
    b.after_acceptance=lambda action,key,payload,proof:callbacks.append(proof)
    result=b.reconcile_action('retry_job',key,payload)
    assert result['status']=='pending' and result['origin_proof']['kind']=='canonical-origin'
    origin=f.proofs[key]['proof']['canonical_origin']
    assert 'envelope' not in f.proofs[key]['proof'] and callbacks[0]['canonical_origin']['job_id']=='22'
    assert set(origin['observation_sha256'])=={'latest_run','attempt','job_list_pages','job'}
    def sha(value):return github.hashlib.sha256(github.json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    assert origin['observation_sha256']=={'latest_run':sha(run),'attempt':sha(run),
        'job_list_pages':sha([{'total_count':1,'jobs':[job]}]),'job':sha(job)}
    assert not any(method=='POST' for method,_,_ in f.calls)
    job['runner_id']=21
    result=b.reconcile_action('retry_job',key,payload)
    assert result['status']=='completed' and result['target']=={**target,'job_id':'22','run_attempt':'2'}
    assert result['origin_proof']['kind']=='canonical-origin'
    assert not any(method=='POST' for method,_,_ in f.calls)


@pytest.mark.parametrize('damage',['authority','intent','actor','triggering_actor','workflow_id','ref','ambiguous','time','missing_time','job_mismatch','remote'])
def test_unknown_retry_canonical_origin_requires_every_binding(damage):
    f,b,target,key,payload,intent,run,job=canonical_unknown_fixture()
    if damage=='authority':b.sole_executor_authority=False
    if damage=='intent':intent['payload']={'target':target}
    if damage=='actor':run['actor']={'login':'other'}
    if damage=='triggering_actor':run['triggering_actor']={'login':'other'}
    if damage=='workflow_id':run['workflow_id']=456
    if damage=='ref':run['head_branch']='wrong'
    if damage=='ambiguous':
        f.responses['GET',b.base+'/runs/10/attempts/2/jobs?per_page=100&page=1']={'total_count':2,'jobs':[job,{**job,'id':23}]}
    if damage=='time':job['created_at']='2026-11-14T07:51:44Z'
    if damage=='missing_time':job.pop('created_at')
    if damage=='job_mismatch':f.responses['GET',b.base+'/jobs/22']={**job,'head_sha':'c'*40}
    if damage=='remote':f.receipt=lambda k:{'receipt':{'action_key':k,'request_sha256':'f'*64,'status':'unknown'}}
    assert b.reconcile_action('retry_job',key,payload) is None
    assert not f.proofs and not any(method=='POST' for method,_,_ in f.calls)


def test_canonical_retry_acceptance_does_not_switch_successor_job():
    f,b,target,key,payload,intent,run,job=canonical_unknown_fixture()
    assert b.reconcile_action('retry_job',key,payload)['status']=='pending'
    changed={**job,'id':23,'runner_id':21}
    f.responses['GET',b.base+'/runs/10/attempts/2/jobs?per_page=100&page=1']={'total_count':1,'jobs':[changed]}
    assert b.reconcile_action('retry_job',key,payload) is None
    assert not any(method=='POST' for method,_,_ in f.calls)


@pytest.mark.parametrize('which,field',[('latest','triggering_actor'),('attempt','triggering_actor'),('latest','workflow_id'),('attempt','workflow_id')])
def test_canonical_retry_checks_each_run_observation_independently(which,field):
    f,b,target,key,payload,intent,run,job=canonical_unknown_fixture()
    path=b.base+('/runs/10' if which=='latest' else '/runs/10/attempts/2')
    altered=copy.deepcopy(run)
    altered[field]={'login':'other'} if field=='triggering_actor' else 999
    f.responses['GET',path]=altered
    assert b.reconcile_action('retry_job',key,payload) is None
    assert not f.proofs and not any(method=='POST' for method,_,_ in f.calls)
