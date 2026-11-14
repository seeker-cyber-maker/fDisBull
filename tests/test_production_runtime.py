import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/ci'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('production_runtime',SCRIPTS/'production_runtime.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
spec2=importlib.util.spec_from_file_location('evidence_fixtures',Path(__file__).with_name('test_production_evidence.py'))
fixtures=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(fixtures)


def hashes():
    result={}
    for name in r.MODULES:
        path=SCRIPTS/name
        if name=='ci_status.py' and not path.exists():path=SCRIPTS.parent/name
        result[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_runtime_transfers_production_sized_closed_junit_to_source_validator(tmp_path, monkeypatch):
    recovery = tmp_path / 'recovery'; recovery.mkdir()
    export = tmp_path / 'results'; export.mkdir()
    monkeypatch.setattr(r, 'RECOVERY', recovery); monkeypatch.setattr(r, 'EXPORT', export)
    target = {'provider': 'github', 'repository': r.REPO, 'run_id': '11', 'run_attempt': '1',
              'job_id': '22', 'source_sha': 'a' * 40, 'job_name': 'qualification', 'runner_id': '21',
              'ref': 'codex/production-ci-recovery-20261113', 'control_sha': 'b' * 40}
    rows = ['<testcase classname="tests.test_bulk_export_compatibility_long_module_name_with_production_metadata" '
            f'name="test_case_{i:05d}" time="0.000000" />' for i in range(14179)]
    rows.append('<testcase classname="tests.test_example" name="test_value"><failure>assertion failed</failure></testcase>')
    junit = ('<testsuite tests="14180" failures="1" errors="0">' + ''.join(rows) + '</testsuite>').encode()
    assert len(junit) > 1700000
    folder = export / 'github/11/1/qualification/22'; (folder / 'exported/artifacts/ordinary').mkdir(parents=True)
    (folder / 'exported/artifacts/ordinary/tests.xml').write_bytes(junit)
    job = {'schema': 'fdisbull-production-job-export-1', **{k: v for k, v in target.items() if k != 'provider'},
           'job_status': 'failed', 'export_success': True}
    fixtures.write(folder / 'job.json', job)
    fixtures.write(folder / 'inventory.json', [{'path': r.source_module.JUNIT, 'size': len(junit),
                                               'sha256': hashlib.sha256(junit).hexdigest()}])
    receipt = recovery / 'evidence.json'
    fixtures.write(receipt, {'schema': 'fdisbull-production-evidence-1', 'target': target, 'job_status': 'failed',
                            'export_job_sha256': hashlib.sha256((folder / 'job.json').read_bytes()).hexdigest(),
                            'inventory_sha256': hashlib.sha256((folder / 'inventory.json').read_bytes()).hexdigest()})
    receipt.chmod(0o600)
    evidence = {'status': 'export-verified', 'job_status': 'failed', 'target': target, 'receipt_path': str(receipt),
                'host_export_verified': True, 'closed_inventory_verified': True,
                'source_postcheck_verified': True, 'provider_trace_verified': True}
    bundle, binding = object.__new__(r.Runtime)._source_bundle(target, evidence)
    # Files stay in the isolated fixture; the wire identity represents the
    # fixed VPS installation path expected by the independent Mac receiver.
    bundle = {**bundle, 'evidence_receipt_path': '/var/lib/fdisbull-ci/control/recovery/production/fixture/evidence.json'}
    actual_target, actual_junit, event = r.source_module.validate_bundle(bundle)
    assert actual_target == target and actual_junit == junit and len(event) == 64
    assert len(binding) == 64
    assert r.source_module.select_node(actual_junit, ['tests/test_example.py']) == 'tests/test_example.py::test_value'


def make_export(root,target,status,policy_sha):
    folder=root/'github'/target['run_id']/target['run_attempt']/'qualification'/target['job_id'];exported=folder/'exported';exported.mkdir(parents=True)
    if status=='success':fixtures.ordinary(exported,target)
    else:fixtures.write(exported/'artifacts/recovery/diagnostic.json',{'kind':'infrastructure','reason':'missing_ci_owned_input',
         'input_key':'qualification-policy','expected_sha256':policy_sha,'target':target})
    identity={k:v for k,v in target.items() if k!='provider'}
    fixtures.write(folder/'candidate-start.json',{'schema':'fdisbull-github-candidate-start-1',**identity,
          'candidate_head':target['source_sha'],'control_head':target['control_sha'],'nonce':'verified'})
    fixtures.write(folder/'caller-health.json',{'target':identity})
    fixtures.write(folder/'source-postcheck.json',{'source_commit':target['source_sha'],'expected_source_commit':target['source_sha'],
          'tracked_worktree_dirty':False,'export_success':True})
    fixtures.write(folder/'qualification.log',b'private qualifier log')
    fixtures.write(folder/'system-preparation.log',b'system prepared' if status=='success' else b'')
    fixtures.write(folder/'system-preparation.json',{'status':'passed' if status=='success' else 'skipped',
          'steps':[{'name':'update','passed':True}] if status=='success' else [],'capture_limit_bytes':4*1024*1024})
    inventory=[fixtures.ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()]
    fixtures.write(folder/'inventory.json',inventory)
    meta={'schema':'fdisbull-production-job-export-1',**identity,'job_status':status,'qualification_exit_code':int(status!='success'),
          'export_success':True,'files':len(inventory),'project_directory':'/candidate','finished_at':'2026-11-14T00:00:00+00:00',
          'log':{'total_bytes':21,'retained_bytes':21,'truncated':False},
          'qualification_stage':'ordinary-tests' if status=='success' else 'policy-preflight'}
    for name in ('candidate-start.json','caller-health.json','source-postcheck.json','inventory.json','qualification.log',
                 'system-preparation.json','system-preparation.log'):
        x=fixtures.ident(folder/name,folder);meta[name]={'size':x['size'],'sha256':x['sha256']}
    fixtures.write(folder/'job.json',meta)


class FakeProvider:
    def __init__(self,target,active,clock=time.time):self.target=target;self.active=active;self.clock=clock;self.attempt=1;self.posts=0;self.proofs={};self.reservations=0
    def reserve(self):self.reservations+=1;return {'allowed':True,'reason':'reserved','next_refresh_at':self.clock()+300}
    def receipt(self,key):return {'receipt':self.proofs.get(key)}
    def for_action(self,key):
        def send(method,path,payload):
            assert self.active.is_file() and self.posts==0
            self.posts+=1;self.attempt=2
            return {'http_status':201,'data':None,'request_id':None}
        return send
    def request(self,method,path,payload=None):
        n=2 if '/attempts/2' in path or path.endswith('/jobs/23') else 1
        if path.endswith('/runs/11'):n=self.attempt
        run={'id':11,'run_attempt':n,'head_sha':self.target['control_sha'],'head_branch':self.target['ref'],
             'repository':{'full_name':r.REPO}}
        job={'id':22 if n==1 else 23,'run_id':11,'name':'qualification','head_sha':self.target['control_sha'],
             'runner_id':21,'status':'completed','conclusion':'failure' if n==1 else 'success'}
        if '/jobs?' in path:data={'total_count':1,'jobs':[job]}
        elif path.endswith('/jobs/22') or path.endswith('/jobs/23'):data=job
        elif '/runs/11' in path:data=run
        else:raise AssertionError(path)
        return {'http_status':200,'data':data,'request_id':None}


def test_full_recovery_composes_real_evidence_policy_and_controller(tmp_path,monkeypatch,capsys):
    recovery=tmp_path/'recovery';root=recovery/'production';root.mkdir(parents=True,mode=0o700);root.chmod(0o700)
    export=tmp_path/'results';export.mkdir();lock=tmp_path/'ci.lock';lock.touch()
    monkeypatch.setattr(r,'RECOVERY',recovery);monkeypatch.setattr(r,'EXPORT',export);monkeypatch.setattr(r,'LOCK',lock)
    policy_dir=tmp_path/'policy';policy_dir.mkdir(mode=0o700);canonical=policy_dir/'qualification-policy.canonical.json'
    policy_bytes=b'{"authorized":true}\n';canonical.write_bytes(policy_bytes);canonical.chmod(0o400)
    inputs=policy_dir/'job-inputs';inputs.mkdir(mode=0o700);active=inputs/'qualification-policy.json'
    monkeypatch.setattr(r.policy_module,'CANONICAL_POLICY',canonical);monkeypatch.setattr(r.policy_module,'ACTIVE_POLICY',active)
    monkeypatch.setattr(r.policy_module,'ACTIVE_ROOT',inputs)
    monkeypatch.setattr(r.policy_module,'EXPECTED_SHA256',hashlib.sha256(policy_bytes).hexdigest())
    target={'provider':'github','repository':r.REPO,'run_id':'11','run_attempt':'1','job_id':'22','runner_id':'21',
            'job_name':'qualification','source_sha':'a'*40,'control_sha':'b'*40,'ref':'codex/production-ci-recovery-20261113'}
    make_export(export,target,'failed',r.policy_module.EXPECTED_SHA256)
    second={**target,'run_attempt':'2','job_id':'23'};make_export(export,second,'success',r.policy_module.EXPECTED_SHA256)
    now=[time.time()];clock=lambda:now[0]
    provider=FakeProvider(target,active,clock);events=[];secret_trace=b'private trace do not display'
    def trace(t,tr):return {'encoding':'base64','data':base64.b64encode(secret_trace).decode(),
                            'size':len(secret_trace),'sha256':hashlib.sha256(secret_trace).hexdigest()}
    class Host:
        def __init__(self,config,state,tr,*args,**kwargs):self.tr=tr;self.state=Path(state)
        def source_binding(self,t,run,job):
            start=json.loads((export/'github'/t['run_id']/t['run_attempt']/'qualification'/t['job_id']/'candidate-start.json').read_text())
            assert start['candidate_head']==t['source_sha'] and str(job['id'])==t['job_id']
            return {'verified':True,'target':t,'receipt_path':'candidate-start'}
        def capture_provider(self,o):
            t={k:o[k] for k in r.production.SCHEMAS['github']};base='/repos/'+r.REPO+'/actions'
            run=self.tr.request('GET',base+'/runs/'+t['run_id']+'/attempts/'+t['run_attempt'])['data']
            job=self.tr.request('GET',base+'/jobs/'+t['job_id'])['data']
            return {'verified':True,'target':t,'job_status':o['status'],'metadata':{'run':run,'job':job},'trace':trace(t,self.tr)}
        def after_acceptance(self,*args):assert active.read_bytes()==policy_bytes
        def resolve_dispatch(self,*args):return None
    cfg={'bridge_path':r.BRIDGE,'state_dir':str(root),'export_root':str(export),'executor_lock':str(lock),
         'github':{'repository':r.REPO,'workflow_id':417757453,'runner_id':21,'actor':'seeker-cyber-maker',
                   'control_sha':target['control_sha'],'ref':target['ref'],'profile':'ordinary',
                   'sole_executor_authority':True,'export_root':str(export)},'module_sha256':hashes(),'incident_test':True,'max_incident_seconds':600}
    def health(path):path.write_text('{}');return {'continue':True}
    def journal(argv,**kw):events.append(json.loads(kw['input']));return SimpleNamespace(returncode=0)
    runtime=r.Runtime(cfg,root,{'fd':1,'owner_pid':1,'device':1,'inode':1},uid=lambda:0,lease_check=lambda:True,
        transport_factory=lambda p:provider,host_factory=Host,health_capture=health,incident_runner=journal,clock=clock)
    cfg.update(schema='fdisbull-production-ci-config-1',enabled=True,installation_id='fixture',activated_epoch=1,max_incident_seconds=600)
    r.control_module.write_json(root/'installation.json',{'schema':'fdisbull-production-state-1','installation_id':'fixture'},exclusive=True)
    with r.control_module.FailureInbox(root/'failure-inbox.sqlite'):pass
    service=r.control_module.ProductionService(cfg,lambda config,state,lease:runtime,clock=clock,sleeper=lambda seconds:now.__setitem__(0,now[0]+seconds))
    final=service.run()
    assert final['status']=='complete' and final['target']==second and provider.posts==1
    assert active.read_bytes()==policy_bytes
    assert [e['phase'] for e in events]==['down','recovered'] and all(e['test'] for e in events)
    assert secret_trace.decode() not in json.dumps(events) and secret_trace.decode() not in capsys.readouterr().out
    assert len(list((root/'incidents').glob('*/evidence/*.trace')))==2


def test_reservation_reused_then_renewed_after_long_listener():
    now=[1000.0]
    class Raw:
        def __init__(self):self.reservations=0;self.gets=0
        def reserve(self):self.reservations+=1;return {'allowed':True,'reason':'reserved','next_refresh_at':now[0]+300}
        def request(self,*args):self.gets+=1;return {'http_status':200,'data':{}}
    raw=Raw();gate=r._GatedTransport(raw,lambda:None,lambda:now[0],'github')
    assert gate.prepare()['allowed'] and gate.prepare()['reason']=='active_batch'
    assert gate.request('GET','/x')['http_status']==200 and raw.reservations==1
    now[0]=1301
    assert gate.request('GET','/x')['http_status']==200 and raw.reservations==2


def test_unknown_cleanup_latches_before_controller_can_reconcile():
    runtime=object.__new__(r.Runtime);runtime._cleanup_unknown=False
    class Host:
        def after_acceptance(self,*args):raise r.host_module.CleanupUnknown('cleanup unknown')
    with pytest.raises(r.host_module.CleanupUnknown):runtime._after_acceptance(Host(),'retry_job','key',{}, {})
    assert runtime.cleanup_blocked() is True


def test_gate_denies_exhausted_batch_without_post():
    class Raw:
        def reserve(self):return {'allowed':True,'reason':'reserved','next_refresh_at':1300}
        def for_action(self,key):raise AssertionError('must not send')
    gate=r._GatedTransport(Raw(),lambda:None,lambda:1000,'gitlab')
    gate.prepare();gate.remaining=1
    with pytest.raises(RuntimeError):gate.for_action('action')('POST','/x',{})


def test_cleanup_hold_requires_marker_removal_and_fresh_proof(tmp_path,monkeypatch):
    marker=tmp_path/'blocked';marker.write_text('operator attention')
    monkeypatch.setattr(r,'CLEANUP_BLOCKER',marker)
    runtime=object.__new__(r.Runtime);runtime._cleanup_unknown=True;runtime._last_incident=None
    runtime._cleanup_key='key';runtime.root=tmp_path
    checks=[];runtime._verify_cleanup=lambda:checks.append('checked') or True
    def operator_action(seconds):
        assert seconds==60 and marker.exists()
        marker.unlink()
    runtime._sleep=operator_action
    runtime.hold_cleanup()
    assert checks==['checked','checked'] and runtime.cleanup_blocked() is False


def test_cleanup_verifier_checks_exact_owned_labels_and_listener_exit(tmp_path,monkeypatch):
    runtime=object.__new__(r.Runtime);runtime._cleanup_key='key'
    runtime.config={'github':{'control_sha':'b'*40}}
    class Host:
        control_root=tmp_path
        def _path(self,key,name):return tmp_path/(name+'.json')
    runtime._github_host=lambda:Host()
    nonce=hashlib.sha256(b'key').hexdigest()
    intent={'action_key':'key','run_id':'11','run_attempt':'2','source_sha':'a'*40,'control_sha':'b'*40,'nonce':nonce}
    (tmp_path/'listener-intent.json').write_text(json.dumps(intent))
    (tmp_path/'listener-started.json').write_text(json.dumps({'action_key':'key','run_id':'11','run_attempt':'2','pid':123456}))
    started=tmp_path/'github-bootstrap-20261113'/nonce/'started.json';started.parent.mkdir(parents=True)
    started.write_text(json.dumps({'pid':123457,'runner_id':21,'stage':'listener-started'}))
    def gone(pid,signal):raise ProcessLookupError()
    monkeypatch.setattr(r.os,'kill',gone);monkeypatch.setattr(r.os,'killpg',gone)
    cid='c'*64;labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':'11','fdisbull.ci.run_attempt':'2',
        'fdisbull.ci.control_sha':'b'*40}
    calls=[]
    def runner(argv,**kw):
        calls.append(argv)
        payload=cid.encode()+b'\n' if argv[1]=='ps' else json.dumps([{'Id':cid,'Config':{'Labels':labels},'State':{'Running':False}}]).encode()
        return {'returncode':0,'stdout':payload,'stderr':b'','timed_out':False,'overflow':False}
    runtime._cleanup_runner=runner
    assert runtime._verify_cleanup() is True and [x[1] for x in calls]==['ps','inspect','ps']


def test_native_retry_gate_rejects_wrong_canonical_job(tmp_path):
    target={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':'a'*40,
            'job_name':'native-debugger-stable','runner_id':'58990209','ref':'main'}
    class Transport:
        def request(self,method,path):
            if '/pipelines/' in path:return {'http_status':200,'data':[{'id':70,'name':'native-qualification','status':'success'}]}
            return {'http_status':200,'data':{'id':71,'name':'native-qualification','status':'success','ref':'main',
                'commit':{'id':'a'*40},'pipeline':{'id':10,'project_id':88349936}}}
    runtime=object.__new__(r.Runtime);runtime.transports={'gitlab':Transport()};runtime.root=tmp_path
    with pytest.raises(ValueError,match='gate identity'):runtime._gitlab_gate(target,{**target,'status':'failed'})


def test_cleanup_unknown_without_ownership_proof_never_returns(tmp_path,monkeypatch):
    marker=tmp_path/'blocked';marker.write_text('attention');monkeypatch.setattr(r,'CLEANUP_BLOCKER',marker)
    runtime=object.__new__(r.Runtime);runtime._cleanup_unknown=True;runtime._last_incident=None
    runtime._cleanup_key='key';runtime.root=tmp_path;runtime._verify_cleanup=lambda:False
    calls=[]
    def timeout(seconds):calls.append(seconds);raise TimeoutError('test stop only')
    runtime._sleep=timeout
    with pytest.raises(TimeoutError):runtime.hold_cleanup()
    assert calls==[60] and runtime.cleanup_blocked() and (tmp_path/'cleanup-attention').is_dir()


def test_initial_dispatch_accepted_pending_without_second_post(tmp_path):
    runtime=object.__new__(r.Runtime);runtime._guard=lambda **kw:None;runtime.health=lambda:{'state':'healthy'}
    runtime.config={'github':{'ref':'codex/production-ci-recovery-20261113'}};runtime._cleanup_unknown=False
    calls=[]
    class Host:
        def _path(self,key,kind):return tmp_path/(kind+'.json')
        def initial_dispatch(self,key,sha):calls.append('post');self._path(key,'dispatch-intent').write_text('{}');return None
        def reconcile_initial(self,key,sha):calls.append('reconcile');return {'status':'running'}
        def _accept(self,key,path,body,status):return '/private/accepted.json'
    runtime._github_host=lambda:Host();request={'key':'initial','source_sha':'a'*40}
    assert runtime.initial_dispatch(request)=={'status':'pending','verified':True,'receipt_path':'/private/accepted.json'}
    assert runtime.initial_dispatch(request)['status']=='pending' and calls==['post','reconcile']


def test_finish_batch_prevents_reuse_before_cooldown():
    class Raw:
        def reserve(self):return {'allowed':True,'reason':'reserved','next_refresh_at':1300}
    runtime=object.__new__(r.Runtime);gate=r._GatedTransport(Raw(),lambda:None,lambda:1000,'github')
    runtime.transports={'github':gate};manifest={'initial_target':{'provider':'github'}}
    assert gate.prepare()['allowed'] is True
    runtime.finish_batch(manifest)
    assert gate.prepare()['reason']=='cooldown' and gate.remaining==0


def test_cleanup_marker_refuses_provider_and_source_admission(tmp_path,monkeypatch):
    marker=tmp_path/'blocker';marker.write_text('blocked');monkeypatch.setattr(r,'CLEANUP_BLOCKER',marker)
    runtime=object.__new__(r.Runtime);runtime._cleanup_unknown=False
    with pytest.raises(r.host_module.CleanupUnknown):runtime._guard()
    assert runtime._cleanup_unknown is True


def test_source_repair_requalifies_new_sha_with_real_controller_and_evidence(tmp_path,monkeypatch):
    recovery=tmp_path/'recovery';root=recovery/'production';root.mkdir(parents=True,mode=0o700)
    export=tmp_path/'results';export.mkdir();lock=tmp_path/'ci.lock';lock.touch()
    monkeypatch.setattr(r,'RECOVERY',recovery);monkeypatch.setattr(r,'EXPORT',export);monkeypatch.setattr(r,'LOCK',lock)
    target={'provider':'github','repository':r.REPO,'run_id':'11','run_attempt':'1','job_id':'22','runner_id':'21',
            'job_name':'qualification','source_sha':'a'*40,'control_sha':'b'*40,'ref':'codex/production-ci-recovery-20261113'}
    make_export(export,target,'failed','c'*64)
    folder=export/'github/11/1/qualification/22';exported=folder/'exported'
    (exported/'artifacts/recovery/diagnostic.json').unlink()
    junit=b'<testsuite tests="1" failures="1" errors="0"><testcase classname="tests.test_demo" name="test_bug"><failure/></testcase></testsuite>'
    fixtures.write(exported/'artifacts/ordinary/tests.xml',junit)
    inv=[fixtures.ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()];fixtures.write(folder/'inventory.json',inv)
    meta=json.loads((folder/'job.json').read_text());meta['files']=len(inv);meta['qualification_stage']='ordinary-tests'
    fixtures.write(folder/'system-preparation.json',{'status':'passed','steps':[{'name':'update','passed':True}], 'capture_limit_bytes':4*1024*1024})
    prep=fixtures.ident(folder/'system-preparation.json',folder);meta['system-preparation.json']={'size':prep['size'],'sha256':prep['sha256']}
    identity=fixtures.ident(folder/'inventory.json',folder)
    meta['inventory.json']={'size':identity['size'],'sha256':identity['sha256']};fixtures.write(folder/'job.json',meta)
    second={**target,'run_id':'12','run_attempt':'1','job_id':'24','source_sha':'d'*40}
    make_export(export,second,'success','c'*64)
    now=[time.time()];clock=lambda:now[0]
    class Source:
        def __init__(self):self.prepares=0;self.repairs=0;self.readbacks=0;self.result=None
        def prepare(self,t,bundle):
            self.prepares+=1
            assert base64.b64decode(bundle['junit_base64'])==junit and 'trace' not in json.dumps(bundle)
            h=lambda b:hashlib.sha256(b).hexdigest()
            event=h(json.dumps({'target':t,'receipt_sha256':bundle['evidence_receipt_sha256'],'junit_sha256':h(junit)},sort_keys=True,separators=(',',':')).encode())
            self.event=event
            return {'schema':'fdisbull-source-reproducer-1','status':'verified_reproducer','selection_profile':'single-failure-direct-imports-1',
                'event_key':event,'target':t,'baseline':'failed','linux_parity':False,'requires_linux_requalification':True,'receipt_path':'/mac/prepared'}
        def reconcile_prepare(self,*args):raise AssertionError('no repeated preparation')
        def repair(self,key,payload):
            self.repairs+=1;assert payload['source_prepare']=={'event_key':self.event}
            ref='codex/ci-repair-'+self.event;sha=second['source_sha'];entry={'verified':True,'source_sha':sha,'candidate_ref':ref}
            self.result={'status':'completed','base_sha':target['source_sha'],'source_sha':sha,'candidate_ref':ref,'receipt_path':'/mac/final',
                'publication':{**entry,'receipt_path':'/mac/readback','github':dict(entry),'gitlab':dict(entry)}}
            return self.result
        def reconcile(self,key,payload):self.readbacks+=1;return self.result
    source=Source()
    class Provider:
        def __init__(self):self.posts=0
        def reserve(self):return {'allowed':True,'reason':'reserved','next_refresh_at':clock()+300}
        def for_action(self,key):
            def send(method,path,payload):
                self.posts+=1;assert payload['inputs']['candidate_sha']==second['source_sha']
                return {'http_status':204,'data':None,'request_id':None}
            return send
        def receipt(self,key):return {'receipt':None}
        def request(self,method,path,payload=None):
            is_new='/runs/12' in path or '/jobs/24' in path
            run={'id':12 if is_new else 11,'run_attempt':1,'head_sha':target['control_sha'],'head_branch':target['ref'],'repository':{'full_name':r.REPO}}
            job={'id':24 if is_new else 22,'run_id':12 if is_new else 11,'name':'qualification','head_sha':target['control_sha'],
                 'runner_id':21,'status':'completed','conclusion':'success' if is_new else 'failure'}
            data={'total_count':1,'jobs':[job]} if '/jobs?' in path else job if '/jobs/' in path else run
            return {'http_status':200,'data':data,'request_id':None}
    provider=Provider();secret=b'private original log'
    def trace(t,tr):return {'encoding':'base64','data':base64.b64encode(secret).decode(),'size':len(secret),'sha256':hashlib.sha256(secret).hexdigest()}
    class Host:
        def __init__(self,config,state,tr,*args,**kwargs):self.tr=tr
        def source_binding(self,t,run,job):return {'verified':True,'target':t,'receipt_path':'candidate-start'}
        def after_acceptance(self,*args):pass
        def resolve_dispatch(self,key,proof,payload):
            return {'verified':True,'target':second,'nonce':hashlib.sha256(key.encode()).hexdigest(),'receipt_path':'nonce-proof'}
        def capture_provider(self,o):
            t={k:o[k] for k in r.production.SCHEMAS['github']};base='/repos/'+r.REPO+'/actions'
            run=self.tr.request('GET',base+'/runs/'+t['run_id']+'/attempts/'+t['run_attempt'])['data']
            job=self.tr.request('GET',base+'/jobs/'+t['job_id'])['data']
            return {'verified':True,'target':t,'job_status':o['status'],'metadata':{'run':run,'job':job},'trace':trace(t,self.tr)}
    cfg={'bridge_path':r.BRIDGE,'state_dir':str(root),'export_root':str(export),'executor_lock':str(lock),'max_incident_seconds':3600,
         'github':{'repository':r.REPO,'workflow_id':417757453,'runner_id':21,'actor':'seeker-cyber-maker','control_sha':target['control_sha'],
                   'ref':target['ref'],'profile':'ordinary','sole_executor_authority':True,'export_root':str(export)},'module_sha256':hashes()}
    def health(path):path.write_text('{}');return {'continue':True}
    events=[]
    runtime=r.Runtime(cfg,root,{'fd':1,'owner_pid':1,'device':1,'inode':1},uid=lambda:0,lease_check=lambda:True,clock=clock,
        transport_factory=lambda p:provider,host_factory=Host,health_capture=health,source_transport=source,
        incident_runner=lambda argv,**kw:events.append(json.loads(kw['input'])) or SimpleNamespace(returncode=0))
    key='e'*64;incident=root/'incidents'/key;incident.mkdir(parents=True,mode=0o700)
    manifest={'incident_id':key,'project':r.REPO,'initial_target':target,'required_artifacts':sorted(r.evidence_module.ORDINARY),
              'deadline_epoch':clock()+3600,'max_infrastructure_repairs':1,'max_source_repairs':1}
    controller=r.control_module.RecoveryController(incident/'state.json',manifest,runtime.backend(manifest,incident))
    state=controller.step()
    assert state['phase']=='dispatch_pipeline' and source.prepares==1 and source.repairs==1
    assert controller.step()['target']==second
    state=controller.step()
    assert state['status']=='complete' and provider.posts==1 and source.readbacks>=1
    assert state['target']['source_sha']==second['source_sha'] and [e['phase'] for e in events]==['down','recovered']


def test_uncertain_source_prepare_only_reconciles_without_recreation(tmp_path):
    runtime=object.__new__(r.Runtime);runtime._guard=lambda **kw:None;runtime.health=lambda:{'state':'healthy'};runtime.clock=lambda:1000
    target={'provider':'github','repository':r.REPO,'run_id':'11','run_attempt':'1','job_id':'22','runner_id':'21',
            'job_name':'qualification','source_sha':'a'*40,'control_sha':'b'*40,'ref':'codex/production-ci-recovery-20261113'}
    event='c'*64;bundle={'junit_base64':base64.b64encode(b'junit').decode(),'evidence_receipt_sha256':'d'*64}
    runtime._source_bundle=lambda t,e:(bundle,event)
    calls=[]
    class Source:
        def prepare(self,t,b):calls.append('prepare');raise TimeoutError()
        def reconcile_prepare(self,t,b):calls.append('reconcile');return None
    runtime.source=Source();obs={**target,'status':'failed'}
    assert runtime._classify(obs,{},tmp_path,3000)['kind']=='blocked'
    assert runtime._classify(obs,{},tmp_path,3000)['kind']=='blocked'
    assert calls==['prepare','reconcile'] and (tmp_path/('source-prepare-'+event+'.json')).is_file()


def test_source_classification_requires_time_and_healthy_host(tmp_path):
    runtime=object.__new__(r.Runtime);runtime._guard=lambda **kw:None;runtime.clock=lambda:1000
    runtime.health=lambda:{'state':'unknown'}
    target={'provider':'github','repository':r.REPO,'run_id':'11','run_attempt':'1','job_id':'22','runner_id':'21',
            'job_name':'qualification','source_sha':'a'*40,'control_sha':'b'*40,'ref':'codex/production-ci-recovery-20261113'}
    bundle={'junit_base64':base64.b64encode(b'junit').decode(),'evidence_receipt_sha256':'d'*64}
    runtime._source_bundle=lambda t,e:(bundle,'c'*64)
    runtime.source=SimpleNamespace(prepare=lambda *args:pytest.fail('must not prepare'))
    assert runtime._classify({**target,'status':'failed'},{},tmp_path,3000)['kind']=='blocked'
    runtime.health=lambda:pytest.fail('deadline check must run first')
    assert runtime._classify({**target,'status':'failed'},{},tmp_path,1500)['kind']=='blocked'


def test_restart_recovers_cleanup_key_only_from_unique_exact_run(tmp_path,monkeypatch):
    marker=tmp_path/'blocker';monkeypatch.setattr(r,'CLEANUP_BLOCKER',marker)
    runtime=object.__new__(r.Runtime);runtime._cleanup_key=None
    class Host:
        state=tmp_path
        def _path(self,key,kind):return tmp_path/(hashlib.sha256(key.encode()).hexdigest()+'.'+kind+'.json')
    host=Host();runtime._github_host=lambda:host
    labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':'11','fdisbull.ci.run_attempt':'2','fdisbull.ci.control_sha':'b'*40}
    marker.write_text(json.dumps({'status':'unknown','labels':labels}))
    host._path('action','listener-intent').write_text(json.dumps({'action_key':'action','run_id':'11','run_attempt':'2','control_sha':'b'*40}))
    runtime._recover_cleanup_key()
    assert runtime._cleanup_key=='action'
    runtime._cleanup_key=None
    host._path('other','listener-intent').write_text(json.dumps({'action_key':'other','run_id':'11','run_attempt':'2','control_sha':'b'*40}))
    runtime._recover_cleanup_key()
    assert runtime._cleanup_key is None


def test_source_dispatch_needs_both_provider_readbacks():
    target={'source_sha':'a'*40};event='c'*64;sha='b'*40;ref='codex/ci-repair-'+event
    one={'verified':True,'source_sha':sha,'candidate_ref':ref}
    result={'status':'completed','base_sha':'a'*40,'source_sha':sha,'candidate_ref':ref,'receipt_path':'/mac/final',
            'publication':{**one,'receipt_path':'/mac/readback','github':dict(one)}}
    assert r.Runtime._valid_publication(result,target,event) is False
    result['publication']['gitlab']=dict(one)
    assert r.Runtime._valid_publication(result,target,event) is True
    result['publication']['gitlab']['source_sha']='d'*40
    assert r.Runtime._valid_publication(result,target,event) is False


def test_initial_pending_without_acceptance_is_never_success(tmp_path):
    runtime=object.__new__(r.Runtime);runtime._guard=lambda **kw:None;runtime.health=lambda:{'state':'healthy'}
    runtime.config={'github':{'ref':'codex/production-ci-recovery-20261113'}};runtime._cleanup_unknown=False
    class Host:
        def _path(self,key,kind):return tmp_path/'intent'
        def initial_dispatch(self,key,sha):return None
        def _accept(self,*args):return None
    runtime._github_host=lambda:Host()
    with pytest.raises(RuntimeError,match='acceptance unknown'):
        runtime.initial_dispatch({'key':'initial','source_sha':'a'*40})
