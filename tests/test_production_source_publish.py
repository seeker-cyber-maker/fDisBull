import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('source_publish',Path(__file__).parents[1]/'scripts/ci/production_source_publish.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


@pytest.fixture
def fixture(tmp_path):
    event='d'*64;key='incident:repair';base='a'*40;new='b'*40;ref='codex/ci-repair-'+event
    state=tmp_path/'state';state.mkdir();worktrees=tmp_path/'worktrees';worktrees.mkdir()
    work=worktrees/('ci-repair-'+event);work.mkdir();eventdir=state/event;eventdir.mkdir()
    action=eventdir/('source-'+hashlib.sha256(key.encode()).hexdigest());action.mkdir()
    blobs={'src/fdisbull/foo.py':b'old source','tests/test_foo.py':b'protected test',
           'scripts/check_ci_qualification.py':b'protected verifier',
           'scripts/ci/execution_identity.py':b'protected identity','pyproject.toml':b'protected config'}
    for path in ('tests/test_foo.py','scripts/check_ci_qualification.py','scripts/ci/execution_identity.py','pyproject.toml'):
        item=work/path;item.parent.mkdir(parents=True,exist_ok=True);item.write_bytes(blobs[path])
    digest=lambda path:hashlib.sha256(blobs[path]).hexdigest()
    policy={'source_sha':base,'candidate_ref':ref,'allowed_paths':['src/fdisbull/foo.py'],
            'source_hashes':{'src/fdisbull/foo.py':digest('src/fdisbull/foo.py')},
            'test_hashes':{'tests/test_foo.py':digest('tests/test_foo.py')},
            'verifier_hashes':{x:digest(x) for x in ('scripts/check_ci_qualification.py','scripts/ci/execution_identity.py','pyproject.toml')},
            'reproducer_argv':['python','-m','pytest','-q','tests/test_foo.py::test_bad'], 'max_diff_bytes':65536}
    (eventdir/'prepared.json').write_text(json.dumps({'schema':'fdisbull-source-reproducer-1','selection_profile':'single-failure-direct-imports-1',
                                                     'event_key':event,'status':'verified_reproducer','target':{'source_sha':base},
                                                     'node':'tests/test_foo.py::test_bad','worktree':str(work),'policy':policy,
                                                     'baseline_interpreter':dict(p.PINNED_INTERPRETER)}))
    local={'status':'completed','source_sha':new,'base_sha':base,'candidate_ref':ref,
           'receipt_path':str(action/'final.json'),'publication':'unpublished'}
    for name,value in [('intent.json',{'key':key,'source_sha':base,'candidate_ref':ref}),
                       ('baseline.json',{'exit_code':1,'test_hashes':policy['test_hashes']}),
                       ('worker.json',{'status':'completed'}),('local.json',local)]:
        (action/name).write_text(json.dumps(value))
    calls=[];remote={'github':None,'gitlab':None};flags={'wrong':False,'timeout':False,'timeout_provider':None,'timeout_after_push':False,'rewrite':False,'wrong_gitlab':False,'stops':[], 'http_status':None, 'empty_token':False}
    def runner(argv,**kwargs):
        calls.append((list(argv),dict(kwargs['env'])))
        assert all('secret-gh' not in x and 'secret-gl' not in x for x in argv)
        ret=0;out=b'';timed=False
        if argv[0] == p.sys.executable and argv[1:4]==['-m','pytest','-q']:
            assert kwargs['env']['PYTEST_DISABLE_PLUGIN_AUTOLOAD']=='1';out=b'1 passed in 0.01s'
        elif argv[0]==p.GH_BIN and argv[1:3]==['auth','token']:out=b'' if flags['empty_token'] else b'secret-gh\n'
        elif argv[0]==p.GLAB_BIN and argv[1:4]==['config','get','token']:out=b'secret-gl\n'
        elif argv[0]==p.GH_BIN:
            assert kwargs['env']['GH_TOKEN']=='secret-gh'
            status=flags['http_status'] or 200
            out=('HTTP/2 '+str(status)+' OK\r\n\r\n').encode()+json.dumps({'login':'wrong' if flags['wrong'] else 'seeker-cyber-maker'}).encode()
        elif argv[0]==p.GLAB_BIN:
            assert kwargs['env']['GITLAB_TOKEN']=='secret-gl'
            out=b'HTTP/2 200 OK\r\n\r\n'+json.dumps({'id':43957127,'username':'other' if flags['wrong_gitlab'] else 'TiGa-RCE'}).encode()
        elif argv[0]==p.GIT_BIN:
            cmd=argv[3:];actionname=cmd[0]
            if actionname=='config':ret=0 if flags['rewrite'] else 1;out=b'rewrite' if flags['rewrite'] else b''
            elif actionname=='rev-parse':out=(new if cmd[1]=='HEAD' else base).encode()
            elif actionname=='branch':out=ref.encode()
            elif actionname=='status':out=b''
            elif actionname=='rev-list':out=(new+' '+base).encode()
            elif actionname=='log':out=('Recovery-Action-Key: '+key).encode()
            elif actionname=='diff-tree':out=b'src/fdisbull/foo.py'
            elif actionname=='diff':out=b'diff fixture'
            elif actionname=='show':out=blobs[cmd[1].split(':',1)[1]]
            elif actionname in ('ls-remote','push'):
                provider='github' if any('github.com' in part for part in cmd) else 'gitlab'
                values=' '.join(kwargs['env'].values())
                assert 'Authorization: Basic' in values and kwargs['env']['GIT_CONFIG_GLOBAL']=='/dev/null'
                if actionname=='ls-remote':
                    out=((remote[provider]+'\trefs/heads/'+ref+'\n').encode() if remote[provider] else b'')
                elif flags['timeout'] or flags['timeout_provider']==provider:
                    if flags['timeout_after_push']:remote[provider]=new
                    timed=True
                else:remote[provider]=new
            else:raise AssertionError(cmd)
        else:raise AssertionError(argv)
        return {'returncode':ret,'timed_out':timed,'overflow':False,'stdout':out,'stderr':b''}
    def stop(name,reason):
        flags['stops'].append((name,reason));return True
    pub=p.CandidateRefPublisher(worktrees,state,guard=lambda:None,runner=runner,
                                provider_admit=lambda name:not flags['stops'],provider_stop=stop)
    return pub,key,local,calls,remote,flags,action


def test_exact_candidate_pushes_only_dedicated_refs_and_readbacks(fixture):
    pub,key,local,calls,remote,flags,action=fixture
    result=pub(key,local)
    assert result['verified'] and all(result[x]['verified'] for x in ('github','gitlab'))
    assert pub.readback(key,{**local,'publication':result})['verified']
    pushes=[args for args,env in calls if args[0]==p.GIT_BIN and args[3]=='push']
    assert len(pushes)==2 and all('--force' not in args for args in pushes)
    assert all(args[-1].endswith(':refs/heads/'+local['candidate_ref']) for args in pushes)
    gh=next(args for args in pushes if any('github.com' in x for x in args))
    gl=next(args for args in pushes if any('gitlab.com' in x for x in args))
    assert '--push-option=ci.skip' in gl and not any(x.startswith('--push-option') for x in gh)
    for file in action.glob('publish-*-intent.json'):
        assert 'secret-' not in file.read_text()


def test_wrong_principal_and_rewrite_refuse_before_mutation(fixture):
    pub,key,local,calls,remote,flags,action=fixture
    flags['wrong']=True
    with pytest.raises(RuntimeError,match='account mismatch'):pub(key,local)
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)
    assert flags['stops']==[('github','provider_account_mismatch')]
    with pytest.raises(RuntimeError,match='status stopped'):pub(key,local)
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)


def test_unknown_push_is_never_repeated(fixture):
    pub,key,local,calls,remote,flags,action=fixture;flags['timeout']=True
    with pytest.raises(RuntimeError,match='unknown'):pub(key,local)
    assert (action/'publish-github-intent.json').is_file()
    flags['timeout']=False
    with pytest.raises(RuntimeError,match='reconcile only'):pub(key,local)
    assert len([args for args,env in calls if args[0]==p.GIT_BIN and args[3]=='push'])==1
    with pytest.raises(ValueError):pub.readback(key,local)


def test_divergent_candidate_ref_never_overwritten(fixture):
    pub,key,local,calls,remote,flags,action=fixture;remote['github']='f'*40
    with pytest.raises(RuntimeError,match='differs'):pub(key,local)
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)


def test_unknown_gitlab_response_recovers_only_by_both_readbacks(fixture):
    pub,key,local,calls,remote,flags,action=fixture
    flags['timeout_provider']='gitlab';flags['timeout_after_push']=True
    with pytest.raises(RuntimeError,match='unknown'):pub(key,local)
    assert remote['github']==remote['gitlab']==local['source_sha']
    assert (action/'publish-github-intent.json').is_file() and (action/'publish-gitlab-intent.json').is_file()
    assert pub.readback(key,local)['verified']
    assert len([args for args,env in calls if args[0]==p.GIT_BIN and args[3]=='push'])==2


def test_bad_reproducer_prevents_authentication_and_push(fixture):
    pub,key,local,calls,remote,flags,action=fixture
    original=pub.runner
    def fail_pytest(argv,**kwargs):
        if argv[0]==p.sys.executable:return {'returncode':1,'timed_out':False,'overflow':False,'stdout':b'1 failed','stderr':b''}
        return original(argv,**kwargs)
    pub.runner=fail_pytest
    with pytest.raises(RuntimeError,match='reproducer'):pub(key,local)
    assert not any(args[0] in (p.GH_BIN,p.GLAB_BIN) for args,env in calls)


def test_wrong_gitlab_principal_refuses_before_either_push(fixture):
    pub,key,local,calls,remote,flags,action=fixture;flags['wrong_gitlab']=True
    with pytest.raises(RuntimeError,match='account mismatch'):pub(key,local)
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)
    assert not (action/'publication-intent.json').exists()
    assert flags['stops']==[('gitlab','provider_account_mismatch')]


def test_git_rewrite_refuses_before_auth_or_push(fixture):
    pub,key,local,calls,remote,flags,action=fixture;flags['rewrite']=True
    with pytest.raises(RuntimeError,match='unsafe'):pub(key,local)
    assert not any(args[0] in (p.GH_BIN,p.GLAB_BIN) for args,env in calls)


@pytest.mark.parametrize('status',[401,403,429])
def test_provider_http_restrictions_persist_shared_stop(fixture,status):
    pub,key,local,calls,remote,flags,action=fixture;flags['http_status']=status
    with pytest.raises(RuntimeError,match='provider stopped'):pub(key,local)
    assert flags['stops']==[('github','provider_http_'+str(status))]
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)


def test_missing_token_persists_shared_stop(fixture):
    pub,key,local,calls,remote,flags,action=fixture;flags['empty_token']=True
    with pytest.raises(RuntimeError,match='provider stopped'):pub(key,local)
    assert flags['stops']==[('github','provider_authentication_required')]
    assert not any(args[0]==p.GIT_BIN and args[3]=='push' for args,env in calls)


def test_push_403_persists_stop_and_never_replays(fixture):
    pub,key,local,calls,remote,flags,action=fixture;original=pub.runner
    def deny(argv,**kwargs):
        if argv[0]==p.GIT_BIN and argv[3]=='push':
            calls.append((list(argv),dict(kwargs['env'])))
            return {'returncode':128,'timed_out':False,'overflow':False,'stdout':b'',
                    'stderr':b'fatal: requested URL returned error: 403'}
        return original(argv,**kwargs)
    pub.runner=deny
    with pytest.raises(RuntimeError,match='provider stopped'):pub(key,local)
    assert flags['stops']==[('github','provider_http_403')]
    assert (action/'publish-github-intent.json').exists()
    with pytest.raises(RuntimeError,match='status stopped'):pub(key,local)
    assert len([args for args,env in calls if args[0]==p.GIT_BIN and args[3]=='push'])==1
