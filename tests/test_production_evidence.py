import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec=importlib.util.spec_from_file_location('production_evidence',Path(__file__).resolve().parents[1]/'scripts/ci/production_evidence.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SHA='a'*40
GH={'provider':'github','repository':'seeker-cyber-maker/fDisBull','run_id':'11','run_attempt':'1','job_id':'22',
    'runner_id':'21','job_name':'qualification','source_sha':SHA,'control_sha':'b'*40,'ref':'main'}
GL={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':SHA,
    'job_name':'test-and-package','runner_id':'58990209','ref':'main'}
REQ=sorted(m.ORDINARY)


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else (json.dumps(data,sort_keys=True)+'\n').encode())


def ident(path,root):
    data=path.read_bytes();return {'path':path.relative_to(root).as_posix(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def ordinary(root,target):
    tests=['artifacts/ordinary/tests.xml','artifacts/ordinary/required-contracts.xml']
    for path in tests:
        count=26 if path.endswith('required-contracts.xml') else 1
        write(root/path,('<testsuite tests="%s" failures="0" errors="0" skipped="0">'%count + '<testcase name="ok"/>'*count + '</testsuite>').encode())
    items={}
    for kind,name in [('core','core.whl'),('player','player.whl'),('sdist','source.tar.gz'),('tool','tool.zip')]:
        write(root/'dist'/name,kind.encode());item=ident(root/'dist'/name,root)
        items[kind]={'name':name,'sha256':item['sha256'],'size_bytes':item['size']}
    write(root/'artifacts/receipts/package-payloads.json',{'source_commit':target['source_sha'],'tracked_worktree_dirty':False,'artifacts':items})
    receipt={'status':'passed','profile':'ordinary','source_commit':target['source_sha'],'job_name':target['job_name'],
             'test_results':[ident(root/x,root) for x in tests], 'artifacts':[ident(root/'dist'/v['name'],root) for v in items.values()]}
    if target['provider']=='github':
        receipt.update({k:target[k] for k in ('repository','run_id','run_attempt','job_id','runner_id','ref','control_sha')})
        receipt['execution_origin']='github'
    else:receipt.update(pipeline_id=target['pipeline_id'],job_id=target['job_id'])
    write(root/'artifacts/receipts/ordinary.json',receipt)


def capture(obs):
    target={k:obs[k] for k in m.production.SCHEMAS[obs['provider']]}
    status=obs['status']
    if target['provider']=='github':
        metadata={'run':{'id':target['run_id'],'run_attempt':target['run_attempt'],'head_sha':target['control_sha'],
                    'head_branch':target['ref'],'repository':{'full_name':target['repository']}},
                  'job':{'id':target['job_id'],'run_id':target['run_id'],'name':target['job_name'],
                    'head_sha':target['control_sha'],'runner_id':target['runner_id'],'status':'completed',
                    'conclusion':'success' if status=='success' else 'failure'}}
    else:
        metadata={'pipeline':{'id':target['pipeline_id'],'project_id':target['project_id'],'sha':target['source_sha'],'ref':target['ref']},
                  'job':{'id':target['job_id'],'name':target['job_name'],'status':status,'ref':target['ref'],
                    'commit':{'id':target['source_sha']},'runner':{'id':target['runner_id']},
                    'pipeline':{'id':target['pipeline_id'],'project_id':target['project_id'],'sha':target['source_sha'],'ref':target['ref']}}}
    return {'verified':True,'target':target,'job_status':status,'metadata':metadata,'trace':b'original trace'}


def gh_export(tmp_path,status='success'):
    root=tmp_path/'exports';folder=root/'11/1/qualification/22';exported=folder/'exported';exported.mkdir(parents=True)
    if status=='success':ordinary(exported,GH)
    else:write(exported/'artifacts/recovery/diagnostic.json',{'kind':'infrastructure','reason':'missing_ci_owned_input',
        'input_key':'qualification-policy','expected_sha256':'c'*64,'target':GH})
    target={k:v for k,v in GH.items() if k!='provider'}
    write(folder/'candidate-start.json',{'schema':'fdisbull-github-candidate-start-1',**target,'candidate_head':SHA,'control_head':GH['control_sha'],'nonce':'incident-1'})
    write(folder/'caller-health.json',{'target':target})
    write(folder/'source-postcheck.json',{'source_commit':SHA,'expected_source_commit':SHA,'tracked_worktree_dirty':False,'export_success':True})
    write(folder/'qualification.log',b'qualifier output')
    write(folder/'system-preparation.log',b'system prepared' if status=='success' else b'')
    write(folder/'system-preparation.json',{'status':'passed' if status=='success' else 'skipped',
          'steps':[{'name':'update','passed':True}] if status=='success' else [],'capture_limit_bytes':4*1024*1024})
    inv=[ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()]
    write(folder/'inventory.json',inv)
    meta={'schema':'fdisbull-production-job-export-1',**target,'job_status':status,'qualification_exit_code':0 if status=='success' else 1,
          'export_success':True,'files':len(inv),'project_directory':'/candidate',
          'log':{'total_bytes':16,'retained_bytes':16,'truncated':False},
          'qualification_stage':'ordinary-tests' if status=='success' else 'policy-preflight'}
    for name in ('candidate-start.json','caller-health.json','source-postcheck.json','inventory.json','qualification.log',
                 'system-preparation.json','system-preparation.log'):
        item=ident(folder/name,folder);meta[name]={'size':item['size'],'sha256':item['sha256']}
    write(folder/'job.json',meta)
    return root,folder


def test_github_success_binds_real_artifacts_and_private_trace(tmp_path):
    root,folder=gh_export(tmp_path);observation={**GH,'status':'success'}
    result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)(observation,REQ)
    assert set(result['verified_artifacts'])==set(REQ) and result['candidate_checkout']['source_sha']==SHA
    receipt=Path(result['receipt_path']);assert receipt.stat().st_mode&0o777==0o600
    assert len(list((tmp_path/'private').glob('*.trace')))==1
    assert m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)(observation,REQ)==result


def test_github_failed_export_needs_no_success_artifacts(tmp_path):
    root,_=gh_export(tmp_path,'failed');result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'failed'},REQ)
    assert result['status']=='export-verified' and result['failed_log_verified'] is True
    assert 'required_artifacts_verified' not in result


@pytest.mark.parametrize('damage',['changed_bytes','extra_file','wrong_target','dirty','candidate','failed_junit'])
def test_github_rejects_tampering_or_wrong_binding(tmp_path,damage):
    root,folder=gh_export(tmp_path);observation={**GH,'status':'success'}
    if damage=='changed_bytes':(folder/'exported/dist/core.whl').write_bytes(b'tampered')
    elif damage=='extra_file':write(folder/'exported/dist/unlisted',b'extra')
    elif damage=='wrong_target':observation['job_id']='23'
    elif damage=='dirty':
        p=folder/'source-postcheck.json';value=json.loads(p.read_text());value['tracked_worktree_dirty']=True;write(p,value)
    elif damage=='candidate':
        p=folder/'candidate-start.json';value=json.loads(p.read_text());value['candidate_head']='c'*40;write(p,value)
    else:(folder/'exported/artifacts/ordinary/tests.xml').write_bytes(b'<testsuite failures="1"/>')
    with pytest.raises((ValueError,OSError)):m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)(observation,REQ)


def test_gitlab_real_exporter_failure_and_wrong_trace(tmp_path):
    work=tmp_path/'work';work.mkdir();subprocess.run(['git','init','-q',str(work)],check=True)
    subprocess.run(['git','-C',str(work),'config','user.name','test'],check=True)
    subprocess.run(['git','-C',str(work),'config','user.email','test@example.invalid'],check=True)
    write(work/'tracked',b'one');subprocess.run(['git','-C',str(work),'add','tracked'],check=True)
    subprocess.run(['git','-C',str(work),'commit','-qm','base'],check=True)
    sha=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD'],text=True).strip()
    target={**GL,'source_sha':sha};write(work/'artifacts/ordinary/tests.log',b'failed test')
    root=tmp_path/'exports';env={'CI_PIPELINE_ID':'10','CI_JOB_ID':'20','CI_JOB_NAME':'test-and-package','CI_JOB_STATUS':'failed','CI_COMMIT_SHA':sha}
    m.ovh.export(work,root,env)
    result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**target,'status':'failed'},REQ)
    assert result['job_status']=='failed' and result['provider_trace_verified'] is True
    with pytest.raises(ValueError):
        m.ProductionEvidence(root,tmp_path/'private2','ordinary',lambda o:{**capture(o),'trace':b''})({**target,'status':'failed'},REQ)


def test_trace_base64_digest_must_match(tmp_path):
    root,_=gh_export(tmp_path,'failed')
    def bad(o):return {**capture(o),'trace':{'encoding':'base64','data':base64.b64encode(b'x').decode(),'size':1,'sha256':'0'*64}}
    with pytest.raises(ValueError):m.ProductionEvidence(root,tmp_path/'private','ordinary',bad)({**GH,'status':'failed'},REQ)


def test_junit_failure_rejected_even_when_all_inventory_and_receipt_hashes_match(tmp_path):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    test=exported/'artifacts/ordinary/tests.xml'
    test.write_bytes(b'<testsuite tests="1" failures="1"><testcase name="broken"><failure/></testcase></testsuite>')
    receipt=exported/'artifacts/receipts/ordinary.json';doc=json.loads(receipt.read_text())
    doc['test_results'][0]=ident(test,exported);write(receipt,doc)
    inv=[ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()];write(folder/'inventory.json',inv)
    meta=json.loads((folder/'job.json').read_text());record=ident(folder/'inventory.json',folder)
    meta['inventory.json']={'size':record['size'],'sha256':record['sha256']};write(folder/'job.json',meta)
    with pytest.raises(ValueError,match='junit'):m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)


def test_failed_export_without_qualifier_capture_is_rejected(tmp_path):
    root,folder=gh_export(tmp_path,'failed')
    (folder/'qualification.log').write_bytes(b'')
    meta=json.loads((folder/'job.json').read_text());record=ident(folder/'qualification.log',folder)
    meta['qualification.log']={'size':record['size'],'sha256':record['sha256']}
    meta['log']={'total_bytes':0,'retained_bytes':0,'truncated':False};write(folder/'job.json',meta)
    with pytest.raises(ValueError,match='failed log'):m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'failed'},REQ)


def test_provider_metadata_binding_is_required(tmp_path):
    root,_=gh_export(tmp_path,'failed')
    def wrong(obs):return {**capture(obs),'target':{**GH,'runner_id':'99'}}
    with pytest.raises(ValueError,match='provider'):m.ProductionEvidence(root,tmp_path/'private','ordinary',wrong)({**GH,'status':'failed'},REQ)


def test_gitlab_native_success_requires_verified_junit_and_output(tmp_path):
    work=tmp_path/'work';work.mkdir();subprocess.run(['git','init','-q',str(work)],check=True)
    subprocess.run(['git','-C',str(work),'config','user.name','test'],check=True)
    subprocess.run(['git','-C',str(work),'config','user.email','test@example.invalid'],check=True)
    write(work/'tracked',b'one');subprocess.run(['git','-C',str(work),'add','tracked'],check=True)
    subprocess.run(['git','-C',str(work),'commit','-qm','base'],check=True)
    sha=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD'],text=True).strip()
    target={**GL,'source_sha':sha,'job_name':'native-debugger-stable'}
    junit='native-evidence/stable/tests.xml';artifact='dist/native.bin';receipt='artifacts/receipts/native-stable.json'
    write(work/junit,b'<testsuite tests="1"><testcase name="real"/></testsuite>');write(work/artifact,b'native')
    write(work/receipt,{'status':'passed','profile':'stable','source_commit':sha,'job_name':target['job_name'],
        'pipeline_id':'10','job_id':'20','backend_identity':{'source_commit':sha},
        'test_results':[ident(work/junit,work)],'artifacts':[ident(work/artifact,work)]})
    root=tmp_path/'exports';m.ovh.export(work,root,{'CI_PIPELINE_ID':'10','CI_JOB_ID':'20',
        'CI_JOB_NAME':target['job_name'],'CI_JOB_STATUS':'success','CI_COMMIT_SHA':sha})
    result=m.ProductionEvidence(root,tmp_path/'private','stable',capture)({**target,'status':'success'},[receipt,junit,artifact])
    assert result['required_artifacts_verified'] is True
    with pytest.raises(ValueError):m.ProductionEvidence(root,tmp_path/'private2','stable',capture)({**target,'status':'success'},['invented'])


def test_diagnostic_is_inventory_bound_and_exact_target(tmp_path):
    root,folder=gh_export(tmp_path,'failed');obs={**GH,'status':'failed'}
    result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)(obs,REQ)
    diagnostic=folder/'exported/artifacts/recovery/diagnostic.json'
    assert result['diagnostic']['target']==GH and result['diagnostic_sha256']==hashlib.sha256(diagnostic.read_bytes()).hexdigest()
    data=json.loads(diagnostic.read_text());data['target']['runner_id']='99';write(diagnostic,data)
    exported=folder/'exported';inv=[ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()]
    write(folder/'inventory.json',inv);meta=json.loads((folder/'job.json').read_text());item=ident(folder/'inventory.json',folder)
    meta['inventory.json']={'size':item['size'],'sha256':item['sha256']};write(folder/'job.json',meta)
    with pytest.raises(ValueError,match='diagnostic'):m.ProductionEvidence(root,tmp_path/'private2','ordinary',capture)(obs,REQ)


@pytest.mark.parametrize('damage',['missing-preparation-log','tampered-preparation-record','stage-mismatch'])
def test_github_requires_hash_bound_consistent_system_preparation(tmp_path,damage):
    root,folder=gh_export(tmp_path);obs={**GH,'status':'success'}
    if damage=='missing-preparation-log':(folder/'system-preparation.log').unlink()
    elif damage=='tampered-preparation-record':write(folder/'system-preparation.json',{'status':'passed'})
    else:
        meta=json.loads((folder/'job.json').read_text());meta['qualification_stage']='system-preparation';write(folder/'job.json',meta)
    with pytest.raises((ValueError,OSError)):m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)(obs,REQ)


def test_system_preparation_failure_preserves_failed_evidence(tmp_path):
    root,folder=gh_export(tmp_path,'failed');exported=folder/'exported'
    (exported/'artifacts/recovery/diagnostic.json').unlink()
    write(exported/'artifacts/ordinary/tests.log',b'prerequisite failed')
    inv=[ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()];write(folder/'inventory.json',inv)
    write(folder/'system-preparation.log',b'apt unavailable')
    write(folder/'system-preparation.json',{'status':'failed','steps':[{'name':'update','passed':False}],'capture_limit_bytes':4*1024*1024})
    meta=json.loads((folder/'job.json').read_text());meta['files']=len(inv);meta['qualification_stage']='system-preparation'
    for name in ('inventory.json','system-preparation.json','system-preparation.log'):
        item=ident(folder/name,folder);meta[name]={'size':item['size'],'sha256':item['sha256']}
    write(folder/'job.json',meta)
    result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'failed'},REQ)
    assert result['job_status']=='failed' and 'diagnostic' not in result
