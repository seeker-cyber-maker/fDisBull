import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import pytest

spec = importlib.util.spec_from_file_location('github_host', Path(__file__).parents[1]/'scripts/ci/production_github_host.py')
host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)


class Transport:
    def __init__(self): self.calls=[]; self.receipts={}; self.rows=[]; self.docs={}; self.unknown=False
    def for_action(self, key):
        def post(method, path, payload):
            self.calls.append((method,path,payload))
            digest = host.transport_contract.request_digest('github', method, path, payload)
            if self.unknown: raise TimeoutError('response unknown')
            envelope={'http_status':204,'data':None,'request_id':None}
            self.receipts[key]={'action_key':key,'status':'accepted','request_sha256':digest,'envelope':envelope}
            return envelope
        return post
    def receipt(self,key): return {'receipt':self.receipts.get(key)}
    def request(self,method,path,payload=None):
        self.calls.append((method,path,payload))
        if '/workflows/' in path: data={'workflow_runs':self.rows}
        else: data=self.docs[path]
        return {'http_status':200,'data':data,'request_id':None}


@pytest.fixture
def setup(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700);exports=tmp_path/'results';exports.mkdir()
    source='b'*40; control='a'*40; key='initial';nonce=hashlib.sha256(key.encode()).hexdigest()
    now=time.time(); created=datetime.fromtimestamp(now,timezone.utc).isoformat()
    config={'sole_executor_authority':True,'repository':host.REPOSITORY,'workflow_id':host.WORKFLOW,
            'runner_id':21,'profile':'ordinary','control_sha':control,'ref':'codex/control',
            'actor':'seeker-cyber-maker','export_root':str(exports)}
    run={'id':42,'run_attempt':1,'display_title':'OVH qualification '+nonce,'event':'workflow_dispatch',
         'workflow_id':int(host.WORKFLOW),'status':'queued','head_sha':control,'head_branch':'codex/control',
         'repository':{'full_name':host.REPOSITORY},'actor':{'login':'seeker-cyber-maker'},'created_at':created}
    job={'id':30,'run_id':42,'name':'qualification','head_sha':control,'runner_id':21,
         'status':'completed','conclusion':'failure'}
    t=Transport();t.rows=[run]
    t.docs[host.BASE+'/runs/42/attempts/1']=run
    t.docs[host.BASE+'/runs/42/attempts/1/jobs?per_page=100&page=1']={'total_count':1,'jobs':[job]}
    t.docs[host.BASE+'/jobs/30']=job
    target={'provider':'github','repository':host.REPOSITORY,'run_id':'42','run_attempt':'1','job_id':'30',
            'source_sha':source,'job_name':'qualification','runner_id':'21','ref':'codex/control','control_sha':control}
    started=[]; control_root=tmp_path/'control-root'; control_root.mkdir()
    class Process:
        pid=1234
        def wait(self,timeout):
            assert timeout <= 60
            listener_nonce = started[-1][0][started[-1][0].index('--nonce')+1]
            run_id = started[-1][0][started[-1][0].index('--run-id')+1]
            attempt = started[-1][0][started[-1][0].index('--run-attempt')+1]
            receipt = control_root/'github-bootstrap-20261113'/listener_nonce/'cleanup.json'
            receipt.parent.mkdir(parents=True, exist_ok=True)
            labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':run_id,'fdisbull.ci.run_attempt':attempt,
                    'fdisbull.ci.control_sha':control}
            receipt.write_text(json.dumps({'status':'clean','labels':labels,'containers':[]}))
            folder=exports/'github/42/1/qualification/30';folder.mkdir(parents=True,exist_ok=True)
            start={**{k:v for k,v in target.items() if k!='provider'},'schema':'fdisbull-github-candidate-start-1',
                   'candidate_head':source,'control_head':control,'nonce':nonce}
            (folder/'candidate-start.json').write_text(json.dumps(start))
            return 0
    def popen(args, **kw):
        started.append((args,kw));assert kw['pass_fds']==(7,);return Process()
    trace=b'failed log'
    def capture(_):return {'encoding':'base64','data':base64.b64encode(trace).decode(),
                           'size':len(trace),'sha256':hashlib.sha256(trace).hexdigest()}
    obj=host.GitHubHost(config,state,t,7,9,10,11,lease_check=lambda *a:True,listener_runner=popen,
                        trace_capture=capture,action_started=lambda _:now,clock=lambda:now,control_root=control_root)
    return obj,t,target,config,started,key,now


def test_initial_dispatch_receipt_run_binding_and_listener_is_single(setup):
    obj,t,target,config,started,key,now=setup
    result=obj.initial_dispatch(key,target['source_sha'])
    assert result['target']==target and result['status']=='failed' and Path(result['receipt_path']).is_file()
    assert len(started)==1 and '--run-id' in started[0][0]
    assert obj.reconcile_initial(key,target['source_sha'])['target']==target
    assert len(started)==1 and len([x for x in t.calls if x[0]=='POST'])==1
    capture=obj.capture_provider({**target,'status':'failed'})
    assert capture['verified'] and capture['metadata']['job']['id']==30 and capture['trace']['size']>0


def test_unknown_dispatch_never_reissues_or_starts_listener(setup):
    obj,t,target,config,started,key,now=setup;t.unknown=True
    with pytest.raises(TimeoutError):obj.initial_dispatch(key,target['source_sha'])
    assert obj.reconcile_initial(key,target['source_sha']) is None
    with pytest.raises(RuntimeError,match='reconcile only'):obj.initial_dispatch(key,target['source_sha'])
    assert len([x for x in t.calls if x[0]=='POST'])==1 and not started


def test_ambiguous_matching_runs_do_not_start_listener(setup):
    obj,t,target,config,started,key,now=setup;t.rows.append(dict(t.rows[0],id=43))
    assert obj.initial_dispatch(key,target['source_sha']) is None
    assert not started


def test_wrong_actor_or_source_is_never_bound(setup):
    obj,t,target,config,started,key,now=setup;t.rows[0]['actor']={'login':'other'}
    assert obj.initial_dispatch(key,target['source_sha']) is None and not started


def test_sole_executor_authority_required(setup,tmp_path):
    obj,t,target,config,started,key,now=setup;config['sole_executor_authority']=False
    with pytest.raises(ValueError):
        host.GitHubHost(config,obj.state,t,7,9,10,11,lease_check=lambda *a:True,trace_capture=lambda _:None)


def test_ambiguous_nonce_even_with_untrusted_actor_stops(setup):
    obj,t,target,config,started,key,now=setup
    t.rows.append({**t.rows[0], 'id':43, 'actor':{'login':'other'}})
    assert obj.initial_dispatch(key,target['source_sha']) is None
    assert not started


def test_retry_hook_starts_one_listener_without_reissuing_post(setup):
    obj,t,target,config,started,key,now=setup
    run = {**t.rows[0], 'run_attempt':2}
    t.docs[host.BASE+'/runs/42'] = run
    t.docs[host.BASE+'/runs/42/attempts/2'] = run
    payload={'target':target}
    proof={'action':'retry_job'}
    assert obj.after_acceptance('retry_job','retry-key',payload,proof)==0
    assert obj.after_acceptance('retry_job','retry-key',payload,proof) is None
    assert len(started)==1 and not [call for call in t.calls if call[0]=='POST']


def test_stale_nonce_run_is_not_selected(setup):
    obj,t,target,config,started,key,now=setup
    t.rows[0]['created_at']=datetime.fromtimestamp(now-60,timezone.utc).isoformat()
    assert obj.initial_dispatch(key,target['source_sha']) is None
    assert not started


def test_modified_source_binding_is_rejected(setup):
    obj,t,target,config,started,key,now=setup
    obj.initial_dispatch(key,target['source_sha'])
    path=obj.export_root/'42/1/qualification/30/candidate-start.json'
    doc=json.loads(path.read_text());doc['source_sha']='c'*40;path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='binding mismatch'):
        obj.source_binding(target,t.rows[0],t.docs[host.BASE+'/jobs/30'])


def test_corrupt_provider_trace_rejected(setup):
    obj,t,target,config,started,key,now=setup
    obj.initial_dispatch(key,target['source_sha'])
    obj.trace_capture=lambda _: {'encoding':'base64','data':'YmFk','size':3,'sha256':'0'*64}
    with pytest.raises(ValueError,match='log invalid'):
        obj.capture_provider({**target,'status':'failed'})


def test_unconfirmed_listener_cleanup_blocks_and_never_respawns(setup):
    obj,t,target,config,started,key,now=setup
    class Vanished:
        pid=222
        def wait(self,timeout):return -9
    obj.listener_runner=lambda *a,**k: Vanished()
    with pytest.raises(host.CleanupUnknown,match='retain executor lease'):
        obj.initial_dispatch(key,target['source_sha'])
    assert obj.blocker.is_file()
    assert json.loads(obj.blocker.read_text())['status']=='unknown'
    posts=len([call for call in t.calls if call[0]=='POST'])
    with pytest.raises(host.CleanupUnknown):obj.reconcile_initial(key,target['source_sha'])
    assert len([call for call in t.calls if call[0]=='POST'])==posts


def test_old_listener_intent_without_cleanup_never_respawns(setup):
    obj,t,target,config,started,key,now=setup
    nonce=hashlib.sha256(key.encode()).hexdigest()
    intent={'action_key':key,'nonce':nonce,'run_id':'42','run_attempt':'1',
            'source_sha':target['source_sha'],'control_sha':target['control_sha'],'ref':target['ref']}
    host._write(obj._path(key,'listener-intent'),intent)
    with pytest.raises(host.CleanupUnknown):obj.run_listener(key,nonce,'42','1',target['source_sha'])
    assert not started and obj.blocker.is_file()


@pytest.mark.parametrize('status', ['queued','in_progress','waiting','requested','pending'])
def test_other_active_workflow_run_blocks_listener(setup,status):
    obj,t,target,config,started,key,now=setup
    t.rows.append({**t.rows[0], 'id': 99, 'display_title': 'other', 'status': status})
    with pytest.raises(RuntimeError,match='another workflow run'):
        obj.initial_dispatch(key,target['source_sha'])
    assert not started


def test_completed_selected_run_never_starts_listener(setup):
    obj,t,target,config,started,key,now=setup
    t.rows[0]['status']='completed'
    with pytest.raises(ValueError, match='receipt unavailable'):
        obj.initial_dispatch(key,target['source_sha'])
    assert not started


def test_only_exact_certified_historical_dispatch_can_resume_once(setup,monkeypatch):
    obj,t,target,config,started,key,now=setup;t.unknown=True
    with pytest.raises(TimeoutError):obj.initial_dispatch(key,target['source_sha'])
    body={'ref':config['ref'],'inputs':{'nonce':hashlib.sha256(key.encode()).hexdigest(),'candidate_sha':target['source_sha']}}
    digest=host.transport_contract.request_digest('github','POST',host.BASE+'/workflows/'+host.WORKFLOW+'/dispatches',body)
    monkeypatch.setattr(host.transport_contract,'HELD_ACTION_KEY',key)
    monkeypatch.setattr(host.transport_contract,'HELD_REQUEST_SHA256',digest)
    monkeypatch.setattr(host.transport_contract,'HELD_RECORD_SHA256','d'*64)
    t.receipts[key]={'action_key':key,'status':'certified_not_sent','request_sha256':digest,
                     'old_record_sha256':'d'*64,'verifier_cert_sha256':'e'*64}
    t.unknown=False
    assert obj.reconcile_initial(key,target['source_sha'])['target']==target
    assert len([x for x in t.calls if x[0]=='POST'])==2
    assert obj.reconcile_initial(key,target['source_sha'])['target']==target
    assert len([x for x in t.calls if x[0]=='POST'])==2


def test_certificate_mismatch_never_resumes_dispatch(setup,monkeypatch):
    obj,t,target,config,started,key,now=setup;t.unknown=True
    with pytest.raises(TimeoutError):obj.initial_dispatch(key,target['source_sha'])
    monkeypatch.setattr(host.transport_contract,'HELD_ACTION_KEY',key)
    t.receipts[key]={'action_key':key,'status':'certified_not_sent','request_sha256':'0'*64,
                     'old_record_sha256':'d'*64,'verifier_cert_sha256':'e'*64}
    t.unknown=False
    assert obj.reconcile_initial(key,target['source_sha']) is None
    assert len([x for x in t.calls if x[0]=='POST'])==1 and not started
