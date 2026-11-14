import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

spec=importlib.util.spec_from_file_location('production_evidence',Path(__file__).resolve().parents[1]/'scripts/ci/production_evidence.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SHA='a'*40
GH={'provider':'github','repository':'seeker-cyber-maker/fDisBull','run_id':'11','run_attempt':'1','job_id':'22',
    'runner_id':'21','job_name':'qualification','source_sha':SHA,'control_sha':'b'*40,'ref':'main'}
GL={'provider':'gitlab','project_id':'88349936','pipeline_id':'10','job_id':'20','source_sha':SHA,
    'job_name':'test-and-package','runner_id':'58990209','ref':'main'}
REQ=sorted(m.ORDINARY)


@pytest.fixture(scope='module')
def genuine_subtest_report(tmp_path_factory):
    if importlib.util.find_spec('_pytest.subtests') is None:
        pytest.skip('genuine built-in subtest serialization requires pytest 9')
    root=tmp_path_factory.mktemp('genuine-pytest-subtest-junit')
    source=root/'test_subtest_fixture.py'
    source.write_text('''import pytest

def test_parent(subtests):
    for value in range(3):
        with subtests.test(value=value):
            assert value >= 0

@pytest.mark.skip(reason="serializer fixture")
def test_skipped():
    pass
''')
    config=root/'pytest.ini';config.write_text('[pytest]\n')
    xml=root/'tests.xml';log=root/'tests.log'
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':''}
    env.pop('PYTEST_PLUGINS',None)
    result=subprocess.run([sys.executable,'-m','pytest','-q','--color=no','-c',str(config),
                           '-p','no:cacheprovider','--junitxml='+str(xml),str(source)],
                          cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,check=True)
    log.write_bytes(result.stdout)
    tree=m.ET.parse(xml).getroot();suite=tree.find('testsuite')
    assert suite is not None and int(suite.get('tests'))==5
    assert len(tree.findall('.//testcase'))==2 and len(tree.findall('.//skipped'))==1
    assert b'1 passed, 1 skipped, 3 subtests passed' in result.stdout
    return xml.read_bytes(),log.read_bytes()


def rebind_success_export(folder):
    exported=folder/'exported';receipt=exported/'artifacts/receipts/ordinary.json'
    document=json.loads(receipt.read_text())
    document['test_results']=[ident(exported/ref['path'],exported) for ref in document['test_results']]
    write(receipt,document)
    inventory=[ident(p,exported) for p in sorted(exported.rglob('*')) if p.is_file()]
    write(folder/'inventory.json',inventory)
    meta=json.loads((folder/'job.json').read_text());meta['files']=len(inventory)
    item=ident(folder/'inventory.json',folder);meta['inventory.json']={'size':item['size'],'sha256':item['sha256']}
    write(folder/'job.json',meta)


def test_genuine_pytest_passed_subtests_need_inventory_bound_terminal_summary(tmp_path,genuine_subtest_report):
    root,folder=gh_export(tmp_path);exported=folder/'exported';xml,log=genuine_subtest_report
    write(exported/'artifacts/ordinary/tests.xml',xml)
    write(exported/'artifacts/ordinary/tests.log',log)
    rebind_success_export(folder)
    result=m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)
    assert result['required_artifacts_verified'] is True
    assert set(result['verified_artifacts'])==set(REQ)


SUBTEST_XML=(b'<testsuites><testsuite tests="5" failures="0" errors="0" skipped="1">'
             b'<testcase name="parent"/><testcase name="skipped"><skipped/></testcase></testsuite></testsuites>')
SUBTEST_SUMMARY=b'1 passed, 1 skipped, 3 subtests passed in 0.01s\n'


@pytest.mark.parametrize('damage',[
    'no-log','missing-parent','missing-skip','extra-skip','orphan-skip','nested-skip','nested-suite','wrong-skip-total','wrong-test-total',
    'failure-node','error-node','failed-summary','error-summary','xfail-summary','missing-subtests',
    'wrong-subtests','wrong-parents','partial-summary','missing-newline','ambiguous-summary',
    'trailing-output','missing-summary','truncated-xml','missing-cases',
])
def test_subtest_reconciliation_rejects_missing_or_contradictory_proof(tmp_path,damage):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    tree=m.ET.fromstring(SUBTEST_XML);suite=tree.find('testsuite');cases=suite.findall('testcase')
    log=SUBTEST_SUMMARY
    if damage=='missing-parent':suite.remove(cases[0])
    elif damage=='missing-skip':cases[1].remove(cases[1].find('skipped'))
    elif damage=='extra-skip':m.ET.SubElement(cases[1],'skipped')
    elif damage in ('orphan-skip','nested-skip'):
        skipped=cases[1].find('skipped');cases[1].remove(skipped)
        parent=suite if damage=='orphan-skip' else m.ET.SubElement(cases[1],'system-out')
        parent.append(skipped)
    elif damage=='nested-suite':m.ET.SubElement(suite,'testsuite',tests='1',failures='1',errors='0',skipped='0')
    elif damage=='wrong-skip-total':suite.set('skipped','0')
    elif damage=='wrong-test-total':suite.set('tests','6')
    elif damage=='failure-node':m.ET.SubElement(cases[0],'failure')
    elif damage=='error-node':m.ET.SubElement(cases[0],'error')
    elif damage=='failed-summary':log=b'1 passed, 1 failed, 3 subtests passed in 0.01s\n'
    elif damage=='error-summary':log=b'1 passed, 1 error, 3 subtests passed in 0.01s\n'
    elif damage=='xfail-summary':log=b'1 passed, 1 xfailed, 3 subtests passed in 0.01s\n'
    elif damage=='missing-subtests':log=b'1 passed, 1 skipped in 0.01s\n'
    elif damage=='wrong-subtests':log=b'1 passed, 1 skipped, 2 subtests passed in 0.01s\n'
    elif damage=='wrong-parents':log=b'2 passed, 1 skipped, 2 subtests passed in 0.01s\n'
    elif damage=='partial-summary':log=b'1 passed, 1 skipped, 3 subtests passed in\n'
    elif damage=='missing-newline':log=log[:-1]
    elif damage=='ambiguous-summary':log+=SUBTEST_SUMMARY
    elif damage=='trailing-output':log+=b'capture ended unexpectedly\n'
    elif damage=='missing-summary':log=b'.....................................\n'
    elif damage=='missing-cases':
        for case in cases:suite.remove(case)
    xml=m.ET.tostring(tree)
    if damage=='truncated-xml':xml=xml[:-10]
    write(exported/'artifacts/ordinary/tests.xml',xml)
    if damage!='no-log':write(exported/'artifacts/ordinary/tests.log',log)
    rebind_success_export(folder)
    with pytest.raises((ValueError,m.ET.ParseError)):
        m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)


def test_summary_companion_must_match_closed_inventory_bytes(tmp_path):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    write(exported/'artifacts/ordinary/tests.xml',SUBTEST_XML)
    log=exported/'artifacts/ordinary/tests.log';write(log,SUBTEST_SUMMARY);rebind_success_export(folder)
    log.write_bytes(b'changed\n'+SUBTEST_SUMMARY)
    with pytest.raises(ValueError,match='inventory byte mismatch'):
        m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)


def test_unlisted_summary_cannot_be_used_as_subtest_proof(tmp_path):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    write(exported/'artifacts/ordinary/tests.xml',SUBTEST_XML);rebind_success_export(folder)
    write(exported/'artifacts/ordinary/tests.log',SUBTEST_SUMMARY)
    with pytest.raises(ValueError,match='inventory not closed'):
        m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)


def test_flat_equal_count_ordinary_report_keeps_optional_log_semantics(tmp_path):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    write(exported/'artifacts/ordinary/tests.log',b'not a terminal summary and no final newline')
    rebind_success_export(folder)
    assert m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)['required_artifacts_verified']


@pytest.mark.parametrize('cases,total',[(26,27),(27,27)])
def test_required_contracts_remain_exactly_26_and_cannot_use_subtest_summary(tmp_path,cases,total):
    root,folder=gh_export(tmp_path);exported=folder/'exported'
    xml=('<testsuite tests="%d" failures="0" errors="0" skipped="0">'%total
         +'<testcase name="contract"/>'*cases+'</testsuite>').encode()
    write(exported/'artifacts/ordinary/required-contracts.xml',xml)
    write(exported/'artifacts/ordinary/tests.log',b'26 passed, 1 subtests passed in 0.01s\n')
    rebind_success_export(folder)
    with pytest.raises(ValueError):
        m.ProductionEvidence(root,tmp_path/'private','ordinary',capture)({**GH,'status':'success'},REQ)


def test_strict_native_junit_cannot_reconcile_passed_subtests(tmp_path):
    xml=tmp_path/'native.xml';log=tmp_path/'native.log'
    write(xml,b'<testsuite tests="4"><testcase name="parent"/></testsuite>')
    write(log,b'1 passed, 3 subtests passed in 0.01s\n')
    with pytest.raises(ValueError,match='independent subtest proof'):m._junit(xml,True,summary_path=log)
    assert m._junit(xml,False,summary_path=log)==4


def test_subtest_only_summary_cannot_establish_missing_parent_cases(tmp_path):
    xml=tmp_path/'tests.xml';log=tmp_path/'tests.log'
    write(xml,b'<testsuite tests="3" failures="0" errors="0" skipped="0"/>')
    write(log,b'3 subtests passed in 0.01s\n')
    with pytest.raises(ValueError,match='independent subtest proof'):m._junit(xml,False,summary_path=log)


def test_actual_retry_summary_totals_reconcile_only_with_all_parent_cases(tmp_path):
    xml=tmp_path/'tests.xml';log=tmp_path/'tests.log'
    write(xml,b'<testsuites><testsuite tests="14795" failures="0" errors="0" skipped="418">'
          +b'<testcase name="passed"/>'*11998+b'<testcase name="skipped"><skipped/></testcase>'*418
          +b'</testsuite></testsuites>')
    write(log,b'11998 passed, 418 skipped, 2379 subtests passed in 674.25s (0:11:14)\n')
    assert m._junit(xml,False,summary_path=log)==14795
    data=xml.read_bytes();xml.write_bytes(data.replace(b'<testcase name="passed"/>',b'',1))
    with pytest.raises(ValueError,match='counts disagree'):m._junit(xml,False,summary_path=log)


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
