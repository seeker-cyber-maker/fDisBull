import copy
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('gitlab_prod',Path(__file__).resolve().parents[1]/'scripts/ci/recovery_gitlab_production.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
SHA='a'*40; NEW='b'*40
TARGET={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':SHA,'job_name':'ordinary','runner_id':'58990209','ref':'main'}


class Fixture:
    def __init__(self):
        self.calls=[];self.saved={};self.claims=set();self.stops=[];self.responses={};self.bridge_receipts={}
        self.pipeline={'id':10,'project_id':88349936,'sha':SHA,'ref':'main','status':'failed'}
        self.job={'id':20,'name':'ordinary','status':'failed','ref':'main','commit':{'id':SHA},
                  'pipeline':{'id':10,'project_id':88349936,'sha':SHA,'ref':'main'},'runner':{'id':58990209}}
        self.evidence=None
    def request(self,method,path,payload=None):
        self.calls.append((method,path,payload))
        val=self.responses.get((method,path))
        if isinstance(val,Exception):raise val
        if val is not None:return copy.deepcopy(val)
        if method=='GET' and path.endswith('/pipelines/10'):data=self.pipeline
        elif method=='GET' and path.endswith('/jobs/20'):data=self.job
        else:raise ValueError('unexpected request')
        return {'http_status':200,'data':copy.deepcopy(data),'request_id':None}
    def for_action(self,key):
        return lambda method,path,payload=None:self.request(method,path,payload)
    def receipt(self,key):return {'receipt':self.bridge_receipts.get(key)}
    def claim(self,action,key,payload):
        new=key not in self.claims;self.claims.add(key);return {'durable':True,'new':new}
    def save(self,key,proof):
        self.saved[key]={'proof':proof,'receipt_path':'accepted.json'};return 'accepted.json'
    def backend(self,**kwargs):
        opts=dict(transport=self,retain=lambda o,r:self.evidence,classify=lambda o,e:None,
          health=lambda:{'state':'healthy','receipt_path':'health'},emit=lambda p,s:{'phase':p},
          claim_action=self.claim,save_acceptance=self.save,load_acceptance=lambda k:self.saved.get(k),
          repair_infrastructure=lambda k,p:None,repair_source=lambda k,p:None,reconcile_other=lambda a,k,p:None,
          lease=lambda:True,required_artifacts=['junit'],candidate_readback=lambda r,s:None,
          dispatch_policy=lambda t,p:None,retry_policy=lambda t,o:{'verified':True,'allowed':True,'native':False,'receipt_path':'policy','target':t},provider_stop=self.stops.append)
        opts.update(kwargs);return module.GitLabRecoveryBackend(**opts)


def envelope(data,status=200):return {'http_status':status,'data':data,'request_id':'req-1'}


def test_observe_identity_and_closed_failed_export():
    f=Fixture();b=f.backend();obs=b.observe(TARGET)
    assert obs['status']=='failed'
    f.evidence={'status':'export-verified','job_status':'failed','target':TARGET,'receipt_path':'export',
        'host_export_verified':True,'closed_inventory_verified':True,'source_postcheck_verified':True,'provider_trace_verified':True}
    assert b.retain(obs)==f.evidence
    for field in ('closed_inventory_verified','provider_trace_verified','source_postcheck_verified'):
        f.evidence[field]=False
        with pytest.raises(ValueError):b.retain(obs)
        f.evidence[field]=True


def test_success_requires_exact_artifacts():
    f=Fixture();f.job['status']='success';b=f.backend();obs=b.observe(TARGET)
    f.evidence={'status':'export-verified','job_status':'success','target':TARGET,'receipt_path':'export',
      'host_export_verified':True,'closed_inventory_verified':True,'source_postcheck_verified':True,'provider_trace_verified':True,
      'required_artifacts_verified':True,'required_artifacts_receipt':'artifact','verified_artifacts':['junit','extra']}
    with pytest.raises(ValueError):b.retain(obs)


def test_retry_durable_accepted_then_runner_assignment_pending():
    f=Fixture();b=f.backend();path=b.base+'/jobs/20/retry';new={**f.job,'id':21,'status':'pending','runner':None}
    f.responses['POST',path]=envelope({'id':21},201);f.responses['GET',b.base+'/jobs/21']=envelope(new)
    result=b.perform('retry_job','key',{'target':TARGET})
    assert result['status']=='pending' and result['origin_proof']['action_key']=='key'
    assert len(f.saved)==1 and len([x for x in f.calls if x[0]=='POST'])==1
    new['runner']={'id':58990209};f.responses['GET',b.base+'/jobs/21']=envelope(new)
    assert b.reconcile_action('retry_job','key',{'target':TARGET})['target']=={**TARGET,'job_id':'21'}
    assert len([x for x in f.calls if x[0]=='POST'])==1


def test_lost_post_never_replayed():
    f=Fixture();b=f.backend();f.responses['POST',b.base+'/jobs/20/retry']=TimeoutError()
    with pytest.raises(TimeoutError):b.perform('retry_job','key',{'target':TARGET})
    assert b.reconcile_action('retry_job','key',{'target':TARGET}) is None
    with pytest.raises(RuntimeError):b.perform('retry_job','key',{'target':TARGET})
    assert len([x for x in f.calls if x[0]=='POST'])==1


@pytest.mark.parametrize('code',[401,403,429])
def test_restriction_stops_without_fallback(code):
    f=Fixture();b=f.backend();f.responses['GET',b.base+'/pipelines/10']=envelope(None,code)
    with pytest.raises(RuntimeError):b.observe(TARGET)
    assert f.stops==[code] and all(call[0]!='POST' for call in f.calls)


def test_source_dispatch_blocked_until_candidate_and_non_native_gate():
    f=Fixture();b=f.backend();payload={'target':TARGET,'source_sha':NEW,'candidate_ref':'codex/repair'}
    with pytest.raises(ValueError):b.perform('start_pipeline','key',payload)
    assert not f.claims and all(call[0]!='POST' for call in f.calls)


def test_new_source_multi_job_pipeline_uses_accepted_pipeline_id():
    f=Fixture();b=f.backend(candidate_readback=lambda ref,sha:{'verified':True,'ref':ref,'source_sha':sha,'receipt_path':'ref'},
        dispatch_policy=lambda t,p:{'verified':True,'allowed':True,'native':False,'receipt_path':'policy','target':t,'candidate_ref':p['candidate_ref'],'source_sha':p['source_sha']})
    payload={'target':TARGET,'source_sha':NEW,'candidate_ref':'codex/repair'}
    pipeline={'id':11,'project_id':88349936,'sha':NEW,'ref':'codex/repair','status':'running'}
    job={'id':31,'name':'ordinary','status':'pending','ref':'codex/repair','commit':{'id':NEW},'pipeline':pipeline,'runner':None}
    f.responses['POST',b.base+'/pipeline']=envelope({'id':11},201)
    f.responses['GET',b.base+'/pipelines/11']=envelope(pipeline)
    f.responses['GET',b.base+'/pipelines/11/jobs?per_page=100&page=1']=envelope([{'id':32,'name':'other'},job])
    f.responses['GET',b.base+'/jobs/31']=envelope(job)
    assert b.perform('start_pipeline','key',payload)['status']=='pending'
    job['runner']={'id':58990209};f.responses['GET',b.base+'/jobs/31']=envelope(job)
    result=b.reconcile_action('start_pipeline','key',payload)
    assert result['target']=={**TARGET,'pipeline_id':'11','job_id':'31','source_sha':NEW,'ref':'codex/repair'}
    assert result['candidate_ref']=='codex/repair'


def test_native_retry_requires_qualified_original_gate():
    f=Fixture();b=f.backend(retry_policy=lambda t,o:{'verified':True,'allowed':True,'native':True,'receipt_path':'policy','target':t})
    with pytest.raises(ValueError):b.perform('retry_job','key',{'target':TARGET})
    assert not f.claims and all(call[0]!='POST' for call in f.calls)


@pytest.mark.parametrize('field', ['sha','ref','runner','project'])
def test_canonical_mismatch_refuses_target(field):
    f=Fixture()
    if field=='sha': f.pipeline['sha']=NEW
    elif field=='ref': f.job['ref']='other'
    elif field=='runner': f.job['runner']={'id':1}
    else: f.job['pipeline']['project_id']=1
    with pytest.raises(ValueError): f.backend().observe(TARGET)


def test_controller_reconciles_pending_retry_without_second_post(tmp_path):
    import time
    spec=importlib.util.spec_from_file_location('controller_gitlab',Path(__file__).resolve().parents[1]/'scripts/ci/recovery.py')
    controller_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller_module)
    f=Fixture();f.evidence={'status':'export-verified','job_status':'failed','target':TARGET,'receipt_path':'export',
        'host_export_verified':True,'closed_inventory_verified':True,'source_postcheck_verified':True,'provider_trace_verified':True}
    b=f.backend(classify=lambda o,e:{'verified':True,'eligible_for_repair':True,'kind':'infrastructure','reason':'runner','fingerprint':'f'},
        repair_infrastructure=lambda k,p:{'status':'completed','receipt_path':'repair'})
    new={**f.job,'id':21,'status':'pending','runner':None}
    f.responses['POST',b.base+'/jobs/20/retry']=envelope({'id':21},201)
    f.responses['GET',b.base+'/jobs/21']=envelope(new)
    manifest={'incident_id':'one','project':'88349936','initial_target':TARGET,'deadline_epoch':time.time()+60,
              'max_infrastructure_repairs':1,'max_source_repairs':1,'required_artifacts':['junit']}
    c=controller_module.RecoveryController(tmp_path/'state',manifest,b)
    assert c.step()['phase']=='dispatch_retry'
    assert c.step()['phase']=='action_pending'
    assert c.step()['phase']=='action_pending'
    new['runner']={'id':58990209};f.responses['GET',b.base+'/jobs/21']=envelope(new)
    state=c.step()
    assert state['phase']=='observe' and state['target']['job_id']=='21'
    assert len([x for x in f.calls if x[0]=='POST'])==1


def test_bridge_accepted_receipt_recovers_local_save_loss_without_post():
    f=Fixture();b=f.backend();payload={'target':TARGET};path=b.base+'/jobs/20/retry'
    calls=[]
    def post(key):
        def send(method,request_path,body):
            calls.append((method,request_path,body))
            f.bridge_receipts[key]={'action_key':key,'request_sha256':module._transport.request_digest('gitlab',method,request_path,body),
                'status':'accepted','envelope':envelope({'id':21},201)}
            raise TimeoutError('lost SSH response')
        return send
    f.for_action=post
    with pytest.raises(TimeoutError): b.perform('retry_job','key',payload)
    f.responses['GET',b.base+'/jobs/21']=envelope({**f.job,'id':21,'status':'pending','runner':None})
    result=b.reconcile_action('retry_job','key',payload)
    assert result['status']=='pending' and result['origin_proof']['action_key']=='key'
    assert f.saved['key']['proof']['envelope']==envelope({'id':21},201)
    assert len(calls)==1
    assert b.reconcile_action('retry_job','key',payload)['status']=='pending'
    assert len(calls)==1


@pytest.mark.parametrize('mutation',['unknown','wrong_key','wrong_digest','invalid_envelope'])
def test_bridge_receipt_never_infers_acceptance(mutation):
    f=Fixture();b=f.backend();path=b.base+'/jobs/20/retry'
    receipt={'action_key':'key','request_sha256':module._transport.request_digest('gitlab','POST',path,{}),
             'status':'accepted','envelope':envelope({'id':21},201)}
    if mutation=='unknown': receipt={'action_key':'key','request_sha256':receipt['request_sha256'],'status':'unknown'}
    elif mutation=='wrong_key':receipt['action_key']='other'
    elif mutation=='wrong_digest':receipt['request_sha256']='a'*64
    else:receipt['envelope']=envelope({'id':21,'secret':'unsafe'},201)
    f.bridge_receipts['key']=receipt
    assert b.reconcile_action('retry_job','key',{'target':TARGET}) is None
    assert not f.saved and all(call[0]!='POST' for call in f.calls)


def test_adapter_save_interruption_recovers_bridge_acceptance():
    f=Fixture();payload={'target':TARGET};saved=f.save;fail=[True]
    def save(key,proof):
        if fail[0]:fail[0]=False;raise OSError('local storage temporarily unavailable')
        return saved(key,proof)
    b=f.backend(save_acceptance=save)
    def post(key):
        def send(method,path,body):
            result=envelope({'id':21},201)
            f.calls.append((method,path,body))
            f.bridge_receipts[key]={'action_key':key,'request_sha256':module._transport.request_digest('gitlab',method,path,body),
                                    'status':'accepted','envelope':result}
            return result
        return send
    f.for_action=post
    with pytest.raises(OSError):b.perform('retry_job','key',payload)
    f.responses['GET',b.base+'/jobs/21']=envelope({**f.job,'id':21,'status':'pending','runner':None})
    assert b.reconcile_action('retry_job','key',payload)['status']=='pending'
    assert len([x for x in f.calls if x[0]=='POST'])==1
