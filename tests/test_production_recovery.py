import copy
import importlib.util
from pathlib import Path
import time

import pytest

spec=importlib.util.spec_from_file_location('controller',Path(__file__).resolve().parents[1]/'scripts/ci/recovery.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
production=module.production
SHA='a'*40; NEW='b'*40
TARGETS=[
 {'provider':'gitlab','project_id':'123','pipeline_id':'42','job_id':'11','source_sha':SHA,'job_name':'test','runner_id':'9','ref':'main'},
 {'provider':'github','repository':'owner/repo','run_id':'44','run_attempt':'1','job_id':'21','source_sha':SHA,'job_name':'test','runner_id':'9','ref':'main','control_sha':'c'*40},
 {'provider':'ovh-local','run_id':'owned-run','attempt':'1','source_sha':SHA,'job_name':'test','host_id':'ovh','container_id':'a'*64},
]


def retry(t):
    t=dict(t)
    if t['provider']=='gitlab':t['job_id']='12'
    elif t['provider']=='github':t.update(run_attempt='2',job_id='22')
    else:t.update(attempt='2',container_id='b'*64)
    return t


def changed(t):
    t=dict(t,source_sha=NEW)
    if t['provider']=='gitlab':t.update(pipeline_id='43',job_id='13',ref='repair')
    elif t['provider']=='github':t.update(run_id='45',run_attempt='1',job_id='23')
    else:t.update(run_id='owned-next',attempt='1',container_id='c'*64)
    return t


def manifest(t):
    project={'gitlab':t.get('project_id'),'github':t.get('repository'),'ovh-local':'local'}[t['provider']]
    return {'incident_id':'incident','project':project,'initial_target':t,'deadline_epoch':time.time()+100,
            'max_infrastructure_repairs':1,'max_source_repairs':1,'required_artifacts':['junit','export']}


class Backend:
    def __init__(self,t):
        self.statuses=['failed','success'];self.target=t;self.perform_calls=[];self.reconcile_calls=[]
        self.artifacts=True;self.indeterminate=False;self.reconcile=None
    def observe(self,t):return dict(t,status=self.statuses.pop(0))
    def retain(self,o):
        result={'status':'export-verified','job_status':o['status'],'receipt_path':'evidence',
            'required_artifacts_verified':self.artifacts,'required_artifacts_receipt':'artifacts' if self.artifacts else None,
            'verified_artifacts':['junit','export'] if self.artifacts else []}
        if o['provider']=='github':
            result['candidate_checkout']={k:o[k] for k in ('source_sha','control_sha','run_id','run_attempt','job_id')}
            result['candidate_checkout'].update(verified=True,receipt_path='checkout')
        return result
    def classify(self,o,e):return {'kind':'infrastructure','reason':'runner','fingerprint':'bounded'}
    def health(self):return {'state':'healthy','receipt_path':'health'}
    def emit(self,*args):return {'journaled':True}
    def perform(self,action,key,payload):
        self.perform_calls.append((action,key))
        if self.indeterminate: raise TimeoutError()
        result={'status':'completed','receipt_path':'action'}
        if action=='retry_job':result['target']=retry(payload['target'])
        return result
    def reconcile_action(self,action,key,payload):self.reconcile_calls.append((action,key));return self.reconcile


def test_cleanup_unknown_escapes_controller_without_losing_action_intent(tmp_path):
    import json
    class CleanupUnknown(RuntimeError):
        requires_executor_hold = True
    backend = Backend(TARGETS[1])
    def unsafe(*args): raise CleanupUnknown('must retain lease')
    backend.perform = unsafe
    path = tmp_path / 'state'
    controller = module.RecoveryController(path, manifest(TARGETS[1]), backend)
    with pytest.raises(CleanupUnknown): controller.step()
    state = json.loads(path.read_text())
    assert state['phase'] == 'action_pending'
    assert len(state['actions']) == 1 and state['actions'][0]['result'] is None
    backend.reconcile_action = unsafe
    with pytest.raises(CleanupUnknown): controller.step()
    assert json.loads(path.read_text())['reason'] == 'executor-cleanup-unknown'


def test_failure_notification_follows_retention_before_classification(tmp_path):
    backend = Backend(TARGETS[0]); order = []
    old_retain, old_classify = backend.retain, backend.classify
    def retain(observation): order.append('retain'); return old_retain(observation)
    def classify(observation, evidence): order.append('classify'); return old_classify(observation, evidence)
    def emit(phase, state): order.append(phase); return {'journaled': True}
    backend.retain, backend.classify, backend.emit = retain, classify, emit
    module.RecoveryController(tmp_path / 'state', manifest(TARGETS[0]), backend).step()
    assert order.index('retain') < order.index('down') < order.index('classify')


@pytest.mark.parametrize('t',TARGETS)
def test_real_provider_retry_then_verified_success(tmp_path,t):
    backend=Backend(t);m=manifest(t);controller=module.RecoveryController(tmp_path/'state',m,backend)
    assert controller.step()['phase']=='dispatch_retry'
    assert controller.step()['target']==retry(t)
    state=controller.step()
    assert state['status']=='complete' and state['target']==retry(t)
    assert state['evidence'][-1]['required_artifacts_verified'] is True


@pytest.mark.parametrize('t',TARGETS)
def test_missing_required_success_artifacts_never_completes(tmp_path,t):
    backend=Backend(t);backend.statuses=['success'];backend.artifacts=False
    state=module.RecoveryController(tmp_path/'state',manifest(t),backend).step()
    assert state['status']=='attention' and state['reason']=='required-artifacts-unverified'
    assert not backend.perform_calls


@pytest.mark.parametrize('t',TARGETS)
def test_uncertain_action_with_only_candidate_is_attention_no_replay(tmp_path,t):
    backend=Backend(t);backend.indeterminate=True
    c=module.RecoveryController(tmp_path/'state',manifest(t),backend)
    assert c.step()['phase']=='action_pending'
    backend.reconcile={'status':'completed','receipt_path':'action'}
    state=c.step()
    assert state['status']=='attention' and state['reason']=='action-origin-unverified'
    c.step()
    assert len(backend.perform_calls)==1 and len(backend.reconcile_calls)==1


def test_durable_canonical_proof_allows_reconcile_not_second_dispatch(tmp_path):
    t=TARGETS[0]; backend=Backend(t); backend.indeterminate=True
    c=module.RecoveryController(tmp_path/'state',manifest(t),backend);state=c.step()
    key=state['actions'][-1]['key']
    backend.reconcile={'status':'completed','receipt_path':'action','origin_proof':{
        'verified':True,'kind':'canonical-origin','action_key':key,'receipt_path':'provider-certificate'}}
    state=c.step()
    assert state['phase']=='dispatch_retry' and len(backend.perform_calls)==1


def test_accepted_provider_action_waits_for_real_target_without_reissuing(tmp_path):
    target=TARGETS[1];backend=Backend(target)
    original=backend.perform
    def perform(action,key,payload):
        if action!='retry_job':return original(action,key,payload)
        backend.perform_calls.append((action,key))
        return {'status':'pending','receipt_path':'accepted-response','origin_proof':{
            'verified':True,'kind':'durable-accepted-action','action_key':key,'receipt_path':'accepted-response'}}
    backend.perform=perform
    controller=module.RecoveryController(tmp_path/'state',manifest(target),backend)
    assert controller.step()['phase']=='dispatch_retry'
    state=controller.step();key=state['actions'][-1]['key']
    assert state['phase']=='action_pending' and state['status']=='pending'
    backend.reconcile=state['actions'][-1]['result']
    assert controller.step()['phase']=='action_pending'
    backend.reconcile={'status':'completed','target':retry(target),'receipt_path':'canonical-job',
        'origin_proof':{'verified':True,'kind':'durable-accepted-action','action_key':key,'receipt_path':'accepted-response'}}
    assert controller.step()['target']==retry(target)
    assert [action for action,_ in backend.perform_calls]==['repair_infrastructure','retry_job']


def test_pending_without_durable_acceptance_is_attention(tmp_path):
    target=TARGETS[0];backend=Backend(target)
    backend.perform=lambda *args:{'status':'pending','receipt_path':'unproved'}
    state=module.RecoveryController(tmp_path/'state',manifest(target),backend).step()
    assert state['status']=='attention' and state['reason']=='pending-action-origin-unverified'


@pytest.mark.parametrize('t',TARGETS)
def test_target_identity_and_retry_linkage_reject_mismatches(t):
    assert production.target(t)==t
    bad=dict(t,extra='unrelated')
    with pytest.raises(ValueError):production.target(bad)
    with pytest.raises(ValueError):production.transition(t,dict(retry(t),provider='other'),'retry_job')
    with pytest.raises(ValueError):production.transition(t,dict(retry(t),source_sha=NEW),'retry_job')
    assert production.transition(t,retry(t),'retry_job')==retry(t)
    assert production.transition(t,changed(t),'start_pipeline',NEW,'repair')==changed(t)
    with pytest.raises(ValueError):production.transition(t,dict(changed(t),source_sha=SHA),'start_pipeline',NEW)


def test_github_requires_exact_next_attempt():
    t=TARGETS[1]
    with pytest.raises(ValueError):production.transition(t,dict(retry(t),run_attempt='3'),'retry_job')
    with pytest.raises(ValueError):production.transition(t,dict(retry(t),run_id='99'),'retry_job')


def test_observation_mismatch_stops_before_mutation(tmp_path):
    t=TARGETS[1]; backend=Backend(t)
    backend.observe=lambda target:dict(target,repository='wrong/repository',status='failed')
    state=module.RecoveryController(tmp_path/'state',manifest(t),backend).step()
    assert state['status']=='attention' and not backend.perform_calls

@pytest.mark.parametrize('t', TARGETS)
def test_source_repair_requires_baseline_then_new_identity(tmp_path, t):
    backend=Backend(t)
    backend.classify=lambda o,e:{'kind':'source','reason':'regression','fingerprint':'source',
        'reproducer':{'verified':True,'source_sha':SHA,'baseline':'failed','receipt_path':'repro'}}
    def perform(action,key,payload):
        backend.perform_calls.append((action,key))
        result={'status':'completed','receipt_path':'action'}
        if action=='repair_source': result.update(source_sha=NEW, candidate_ref='repair')
        if action=='start_pipeline': result.update(target=changed(t), candidate_ref='repair')
        return result
    backend.perform=perform
    controller=module.RecoveryController(tmp_path/'state',manifest(t),backend)
    assert controller.step()['phase']=='dispatch_pipeline'
    assert controller.step()['target']==changed(t)
    assert controller.step()['status']=='complete'
    assert [x[0] for x in backend.perform_calls]==['repair_source','start_pipeline']


def test_unverified_reproducer_blocks_source_worker(tmp_path):
    t=TARGETS[0];backend=Backend(t)
    backend.classify=lambda o,e:{'kind':'source','reason':'unknown','fingerprint':'x',
        'reproducer':{'verified':True,'source_sha':NEW,'baseline':'failed','receipt_path':'r'}}
    state=module.RecoveryController(tmp_path/'state',manifest(t),backend).step()
    assert state['reason']=='source-reproducer-unverified' and not backend.perform_calls


def test_github_checkout_receipt_must_bind_candidate_and_control(tmp_path):
    t=TARGETS[1]; backend=Backend(t); retain=backend.retain
    def wrong(o):
        evidence=retain(o);evidence['candidate_checkout']['source_sha']=NEW
        return evidence
    backend.retain=wrong
    state=module.RecoveryController(tmp_path/'state',manifest(t),backend).step()
    assert state['reason']=='export-evidence-unknown' and not backend.perform_calls


def test_hosted_ref_and_github_control_linkage():
    gitlab,github=TARGETS[:2]
    with pytest.raises(ValueError): production.transition(gitlab,dict(retry(gitlab),ref='other'),'retry_job')
    with pytest.raises(ValueError): production.transition(gitlab,changed(gitlab),'start_pipeline',NEW,'other')
    with pytest.raises(ValueError): production.transition(github,dict(retry(github),control_sha='d'*40),'retry_job')
    with pytest.raises(ValueError): production.transition(github,dict(changed(github),ref='repair'),'start_pipeline',NEW,'repair')


def test_provider_stop_blocks_before_evidence_or_action(tmp_path):
    t=TARGETS[0];backend=Backend(t)
    backend.observe=lambda target:dict(target,status='failed',provider_stop='permission-denied')
    state=module.RecoveryController(tmp_path/'state',manifest(t),backend).step()
    assert state['reason']=='provider-stopped' and not backend.perform_calls and not state['evidence']
