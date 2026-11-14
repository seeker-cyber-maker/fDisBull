import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('source_transport',Path(__file__).parents[1]/'scripts/ci/production_source_transport.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def enc(data):return base64.b64encode(data).decode()
def sha(data):return hashlib.sha256(data).hexdigest()
def raw(doc):return json.dumps(doc,sort_keys=True,separators=(',',':')).encode()


def make_bundle():
    target={'provider':'github','repository':'seeker-cyber-maker/fDisBull','run_id':'42','run_attempt':'1',
            'job_id':'30','source_sha':'a'*40,'job_name':'qualification','runner_id':'21','ref':'control','control_sha':'b'*40}
    junit=b'<testsuites><testsuite tests="1" failures="1" errors="0"><testcase classname="tests.test_foo" name="test_bad"><failure>SECRET TRACE</failure></testcase></testsuite></testsuites>'
    inventory=raw([{'path':s.JUNIT,'size':len(junit),'sha256':sha(junit)}])
    job=raw({'schema':'fdisbull-production-job-export-1','job_status':'failed','export_success':True,
             **{k:v for k,v in target.items() if k!='provider'}})
    receipt=raw({'schema':'fdisbull-production-evidence-1','target':target,'job_status':'failed',
                 'export_job_sha256':sha(job),'inventory_sha256':sha(inventory)})
    bundle={'target':target,'evidence_receipt_path':'/var/lib/fdisbull-ci/control/production/evidence.json',
            'evidence_receipt_sha256':sha(receipt),'evidence_receipt_base64':enc(receipt),'job_base64':enc(job),
            'inventory_base64':enc(inventory),'junit_path':s.JUNIT,'junit_base64':enc(junit)}
    return bundle


def test_bundle_binds_junit_to_verified_receipt_and_target():
    bundle=make_bundle();target,junit,event=s.validate_bundle(bundle)
    assert target==bundle['target'] and len(event)==64
    assert s.select_node(junit,['tests/test_foo.py'])=='tests/test_foo.py::test_bad'
    bad=dict(bundle,junit_base64=enc(junit+b'changed'))
    with pytest.raises(ValueError,match='JUnit'):s.validate_bundle(bad)
    bad=dict(bundle,evidence_receipt_sha256='0'*64)
    with pytest.raises(ValueError,match='receipt hash'):s.validate_bundle(bad)


@pytest.mark.parametrize('junit',[
    b'<testsuites><testcase classname="tests.test_foo" name="test_bad[x]"><failure/></testcase></testsuites>',
    b'<testsuites><testcase classname="tests.test_foo" name="test_bad"><error/></testcase></testsuites>',
    b'<testsuites><testcase classname="tests.test_foo" name="test_bad"><failure/></testcase><testcase classname="tests.test_foo" name="test_other"><failure/></testcase></testsuites>',
    b'<!DOCTYPE x><testsuites/>'
])
def test_unsupported_junit_fails_closed(junit):
    with pytest.raises(ValueError):s.select_node(junit,['tests/test_foo.py'])


def test_direct_imports_are_narrow_and_ambiguous_mapping_refused():
    assert s.direct_modules(b'from fdisbull.foo import bar\nimport fdisbull.baz\n',
         ['src/fdisbull/foo.py','src/fdisbull/baz.py']) == ['src/fdisbull/baz.py','src/fdisbull/foo.py']
    with pytest.raises(ValueError):s.direct_modules(b'import os\n',['src/fdisbull/foo.py'])
    with pytest.raises(ValueError):s.select_node(b'<testsuites><testsuite tests="1" failures="1" errors="0"><testcase classname="tests.test_foo" name="test_x"><failure/></testcase></testsuite></testsuites>',
                                                 ['tests/test_foo.py','tests/tests/test_foo.py'])
    with pytest.raises(ValueError):s.direct_modules(b'import fdisbull.a, fdisbull.b, fdisbull.c, fdisbull.d',
                                                     ['src/fdisbull/'+x+'.py' for x in 'abcd'])


def test_selection_and_worker_disabled_without_approval_or_publisher(tmp_path):
    server=s.SourceServer(repo=tmp_path,worktrees=tmp_path,state=tmp_path,guard=lambda:None)
    bundle=make_bundle()
    with pytest.raises(RuntimeError,match='not approved'):server.prepare(bundle['target'],bundle)
    server.approved=True
    with pytest.raises(RuntimeError,match='publisher unavailable'):server.repair('key',{'target':bundle['target']})


def test_fixed_ssh_route_and_structured_input_only():
    calls=[]
    def runner(argv,**kwargs):
        calls.append((argv,kwargs))
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':b'{"result":null}','stderr':b''}
    client=s.SSHSourceTransport(runner=runner);bundle=make_bundle()
    assert client.prepare(bundle['target'],bundle) is None
    argv,params=calls[0]
    assert argv==['/usr/bin/tailscale','ssh','tiga@100.76.103.43',s.SOURCE_PYTHON,s.HELPER]
    assert b'SECRET TRACE' not in params['input_bytes']  # JUnit is encoded, never a model prompt.
    assert json.loads(params['input_bytes'])['operation']=='prepare'
    with pytest.raises(ValueError):s.handle(object(),{'operation':'repair','key':'k','payload':{'cmd':'arbitrary'}})


def test_prepare_records_one_local_failure_after_admission_without_model(tmp_path,monkeypatch):
    bundle=make_bundle();cmds=[];worker_calls=[]
    repo=tmp_path/'repo';repo.mkdir();worktrees=tmp_path/'worktrees';worktrees.mkdir()
    state=tmp_path/'state';state.mkdir()
    test_bytes=b'from fdisbull.foo import run\ndef test_bad():\n    assert run()==1\n'
    source_bytes=b'def run(): return 0\n'
    def runner(argv,**kwargs):
        cmds.append(argv)
        assert not any('TOKEN' in k or 'PASSWORD' in k for k in kwargs['env'])
        out=b''
        if argv[:4]==['git','ls-tree','-r','--name-only']:out=b'tests/test_foo.py\nsrc/fdisbull/foo.py\nscripts/check_ci_qualification.py\nscripts/ci/execution_identity.py\npyproject.toml\n'
        if argv[:2]==['git','show']:
            out=test_bytes if argv[2].endswith(':tests/test_foo.py') else source_bytes
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':out,'stderr':b''}
    class Worker:
        def __init__(self,worktree,directory,policy,**kwargs):
            worker_calls.append((str(worktree),policy))
        def _identity(self,sha):assert sha=='a'*40
        def _tests(self):pass
        def _check(self):return 1
    monkeypatch.setenv('SECRET_TOKEN','sensitive')
    server=s.SourceServer(repo=repo,worktrees=worktrees,state=state,runner=runner,guard=lambda:None,
                          selection_policy_approved=True,worker_class=Worker,interpreter_check=lambda:dict(s.PINNED_INTERPRETER))
    result=server.prepare(bundle['target'],bundle)
    assert result['status']=='verified_reproducer' and result['linux_parity'] is False
    assert result['policy']['source_hashes']=={'src/fdisbull/foo.py':sha(source_bytes)}
    assert result['policy']['test_hashes']=={'tests/test_foo.py':sha(test_bytes)}
    assert result['policy']['reproducer_argv']==['python','-m','pytest','-q','tests/test_foo.py::test_bad']
    storage=next(i for i,c in enumerate(cmds) if s.STORAGE in c)
    create=next(i for i,c in enumerate(cmds) if c[:5]==['git','-c','core.hooksPath=/dev/null','worktree','add'])
    assert storage<create and cmds[storage][-1]=='200000000'
    assert server.reconcile_prepare(bundle['target'],bundle)['event_key']==result['event_key']
    with pytest.raises(FileExistsError):server.prepare(bundle['target'],bundle)
    assert len([c for c in cmds if c[:5]==['git','-c','core.hooksPath=/dev/null','worktree','add']])==1


def test_no_baseline_result_means_no_preparation_receipt(tmp_path):
    bundle=make_bundle();repo=tmp_path/'repo';repo.mkdir();worktrees=tmp_path/'worktrees';worktrees.mkdir();state=tmp_path/'state';state.mkdir()
    def runner(argv,**kwargs):
        out=b''
        if argv[:4]==['git','ls-tree','-r','--name-only']:out=b'tests/test_foo.py\nsrc/fdisbull/foo.py\nscripts/check_ci_qualification.py\nscripts/ci/execution_identity.py\npyproject.toml\n'
        if argv[:2]==['git','show']:out=b'from fdisbull.foo import run' if 'tests/test_foo.py' in argv[2] else b'pass'
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':out,'stderr':b''}
    class Worker:
        def __init__(self,*a,**k):pass
        def _identity(self,*a):pass
        def _tests(self):pass
        def _check(self):return 0
    server=s.SourceServer(repo=repo,worktrees=worktrees,state=state,runner=runner,guard=lambda:None,
                          selection_policy_approved=True,worker_class=Worker,interpreter_check=lambda:dict(s.PINNED_INTERPRETER))
    with pytest.raises(RuntimeError,match='did not reproduce'):server.prepare(bundle['target'],bundle)
    assert server.reconcile_prepare(bundle['target'],bundle) is None


def test_reconciliation_of_unknown_publication_only_reads_both_refs(tmp_path):
    key='incident:repair';sha0='a'*40;sha1='c'*40;branch='codex/ci-repair-'+'d'*64
    work=tmp_path/'work';work.mkdir();action=tmp_path/'action';action.mkdir()
    local={'status':'completed','base_sha':sha0,'source_sha':sha1,'candidate_ref':branch,
           'receipt_path':str(action/'final.json'),'publication':'unpublished'}
    (action/'local.json').write_text(json.dumps(local))
    calls=[]
    class Publisher:
        def __call__(self,*args):calls.append('PUSH');raise AssertionError('reconcile must not publish')
        def readback(self,k,value):
            calls.append('READ')
            return {'verified':True,'source_sha':sha1,'candidate_ref':branch,'receipt_path':'dual.json',
                    'github':{'verified':True,'source_sha':sha1,'candidate_ref':branch},
                    'gitlab':{'verified':True,'source_sha':sha1,'candidate_ref':branch}}
    class Worker:
        def __init__(self,*args,**kwargs):pass
        def reconcile(self,*args):return None
        def _directory(self,k):return action
        def _identity(self,sha):assert sha==sha1
        def _tests(self):pass
        def _git(self,*args):
            if args[0]=='rev-parse':return sha0
            if args[0]=='log':return 'Recovery-Action-Key: '+key
            if args[0]=='diff-tree':return 'src/fdisbull/foo.py'
            raise AssertionError(args)
    record={'worktree':str(work),'policy':{'source_sha':sha0,'candidate_ref':branch,
                                          'allowed_paths':['src/fdisbull/foo.py']}}
    server=s.SourceServer(repo=work,worktrees=work,state=tmp_path,guard=lambda:None,
                          selection_policy_approved=True,publisher=Publisher(),worker_class=Worker,
                          interpreter_check=lambda:dict(s.PINNED_INTERPRETER))
    server._prepared=lambda payload:(tmp_path,record)
    result=server.reconcile(key,{'target':{}})
    assert result['publication']['verified'] and calls==['READ']
    assert (action/'final.json').is_file()


def test_partial_provider_readback_cannot_complete_publication(tmp_path):
    class Publisher:
        def __call__(self,*args):return {}
        def readback(self,*args):return {'verified':True,'source_sha':'c'*40,'candidate_ref':'codex/x',
                                        'receipt_path':'r','github':{'verified':True,'source_sha':'c'*40,'candidate_ref':'codex/x'}}
    server=s.SourceServer(repo=tmp_path,worktrees=tmp_path,state=tmp_path,guard=lambda:None,
                          selection_policy_approved=True,publisher=Publisher())
    with pytest.raises(RuntimeError,match='dual-provider'):server._publisher_readback_only('k',{'source_sha':'c'*40,'candidate_ref':'codex/x'})


def test_activation_factory_is_disabled_until_private_config_and_exact_manifest(tmp_path):
    module_root=tmp_path/'modules';module_root.mkdir()
    hashes={}
    for name in s.ACTIVATION_MODULES:
        payload=('fixture '+name).encode();(module_root/name).write_bytes(payload);hashes[name]=sha(payload)
    private=tmp_path/'private';private.mkdir(mode=0o700)
    config_path=private/'source-activation.json'
    assert not s.server_factory(config_path=config_path,module_root=module_root,bridge_guard=lambda:None).approved
    config={'schema':'fdisbull-source-activation-1','approved':True,
            'selection_profile':'single-failure-direct-imports-1','publisher':'candidate-ref-v1','module_sha256':hashes,
            'source_interpreter':dict(s.PINNED_INTERPRETER)}
    config_path.write_text(json.dumps(config));config_path.chmod(0o600)
    class Publisher:
        def __call__(self,*args):pass
        def readback(self,*args):pass
        def admit(self):return True
    ready=s.server_factory(config_path=config_path,module_root=module_root,bridge_guard=lambda:None,
                           publisher_factory=lambda server:Publisher(),interpreter_probe=lambda:dict(s.PINNED_INTERPRETER))
    assert ready.approved and isinstance(ready.publisher,Publisher)
    without_publisher=s.server_factory(config_path=config_path,module_root=module_root,bridge_guard=lambda:None,
                                       publisher_factory=lambda server:None,interpreter_probe=lambda:dict(s.PINNED_INTERPRETER))
    assert not without_publisher.approved
    (module_root/'production_source_publish.py').write_bytes(b'changed')
    assert not s.server_factory(config_path=config_path,module_root=module_root,bridge_guard=lambda:None,
                                publisher_factory=lambda server:Publisher(),interpreter_probe=lambda:dict(s.PINNED_INTERPRETER)).approved
    assert s.HELPER=='/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/production_source_transport.py'


def test_activation_does_not_accept_insecure_or_unapproved_config(tmp_path):
    private=tmp_path/'private';private.mkdir(mode=0o700);config=private/'source-activation.json'
    config.write_text('{}');config.chmod(0o644)
    assert not s.server_factory(config_path=config,module_root=tmp_path,bridge_guard=lambda:None).approved


def test_stopped_shared_provider_prevents_future_worker_start(tmp_path):
    class Publisher:
        def __call__(self,*args):raise AssertionError('publish must not run')
        def readback(self,*args):raise AssertionError('readback must not run')
        def admit(self):return False
    def worker(*args,**kwargs):raise AssertionError('worker must not start')
    server=s.SourceServer(repo=tmp_path,worktrees=tmp_path,state=tmp_path,guard=lambda:None,
                          selection_policy_approved=True,publisher=Publisher(),worker_class=worker,
                          interpreter_check=lambda:dict(s.PINNED_INTERPRETER))
    with pytest.raises(RuntimeError,match='provider status unavailable'):
        server.repair('key',{'target':{},'source_prepare':{'event_key':'a'*64}})


def bundle_with_junit(junit):
    bundle=make_bundle()
    inventory=raw([{'path':s.JUNIT,'size':len(junit),'sha256':sha(junit)}])
    receipt=json.loads(base64.b64decode(bundle['evidence_receipt_base64']))
    receipt['inventory_sha256']=sha(inventory);receipt=raw(receipt)
    bundle.update(inventory_base64=enc(inventory),junit_base64=enc(junit),
                  evidence_receipt_base64=enc(receipt),evidence_receipt_sha256=sha(receipt))
    return bundle


def test_retained_size_junit_validates_selects_and_reaches_ssh_stdin():
    cases=[('<testcase classname="tests.test_foo" name="test_case_%05d" time="0.001">'
            '<system-out>%s</system-out></testcase>' % (i,'x'*55)).encode() for i in range(14179)]
    cases.append(b'<testcase classname="tests.test_foo" name="test_bad"><failure>PRIVATE TRACE</failure></testcase>')
    junit=(b'<testsuites><testsuite tests="14180" failures="1" errors="0">'
           +b''.join(cases)+b'</testsuite></testsuites>')
    assert 1700000 < len(junit) < s.MAX_JUNIT
    bundle=bundle_with_junit(junit);target,validated,_=s.validate_bundle(bundle)
    assert s.select_node(validated,['tests/test_foo.py'])=='tests/test_foo.py::test_bad'
    captured=[]
    def runner(argv,**kwargs):
        captured.append(kwargs['input_bytes'])
        return {'returncode':0,'timed_out':False,'overflow':False,'stdout':b'{"result":null}','stderr':b''}
    assert s.SSHSourceTransport(runner=runner).prepare(target,bundle) is None
    envelope=json.loads(captured[0]);assert base64.b64decode(envelope['evidence']['junit_base64'])==junit
    assert b'PRIVATE TRACE' not in captured[0]


def test_oversized_junit_and_document_refuse_before_ssh():
    calls=[]
    def runner(*args,**kwargs):calls.append(args);raise AssertionError('must not execute')
    client=s.SSHSourceTransport(runner=runner);bundle=make_bundle()
    bundle['junit_base64']=enc(b'x'*(s.MAX_JUNIT+1))
    with pytest.raises(ValueError,match='bound|size'):client.prepare(bundle['target'],bundle)
    with pytest.raises(ValueError,match='exceeds bound'):client._call({'oversized':'x'*(s.MAX_DOC+1)})
    assert not calls


@pytest.mark.parametrize('signal_name',['SIGTERM','SIGHUP'])
def test_helper_disconnect_terminates_only_its_owned_child(tmp_path,signal_name):
    import os
    import signal
    import subprocess
    import sys
    import time
    signum=getattr(signal,signal_name,None)
    if signum is None:pytest.skip('signal unavailable')
    pidfile=tmp_path/'owned-child.pid'
    script=r'''
import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('source_helper',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def fixture_handle(server,doc):
    child="import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
    return m.legacy.run_command([sys.executable,'-c',child,sys.argv[2]],cwd='/',timeout=50)
m.server_factory=lambda:None
m.handle=fixture_handle
raise SystemExit(m.main())
'''
    owned_pid=None
    child=subprocess.Popen([sys.executable,'-c',script,str(Path(s.__file__).resolve()),str(pidfile)],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        child.stdin.write(b'{}');child.stdin.close()
        deadline=time.monotonic()+5
        while not pidfile.exists() and time.monotonic()<deadline:
            if child.poll() is not None:break
            time.sleep(0.01)
        assert pidfile.exists(), 'owned fixture child never started'
        owned_pid=int(pidfile.read_text())
        os.kill(child.pid,signum)
        assert child.wait(timeout=5)==1
        assert child.stdout.read()==b'{"error":"source_operation_unavailable"}\n'
        with pytest.raises(ProcessLookupError):os.kill(owned_pid,0)
    finally:
        if child.poll() is None:
            if owned_pid is not None:
                try:os.killpg(owned_pid,signal.SIGKILL)
                except ProcessLookupError:pass
            child.kill();child.wait(timeout=5)


def test_server_rejects_oversized_input_before_factory(monkeypatch,capsys):
    import io
    from types import SimpleNamespace
    monkeypatch.setattr(s,'MAX_DOC',64)
    monkeypatch.setattr(s.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(b'x'*65)))
    monkeypatch.setattr(s,'server_factory',lambda:pytest.fail('factory must not run'))
    assert s.main()==1
    assert capsys.readouterr().out=='{"error":"source_operation_unavailable"}\n'
