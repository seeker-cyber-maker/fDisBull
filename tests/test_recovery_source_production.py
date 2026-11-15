import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec=importlib.util.spec_from_file_location('production_source',Path(__file__).resolve().parents[1]/'scripts/ci/recovery_source_production.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL,text=True).strip()


@pytest.fixture
def workspace(tmp_path):
    repo=tmp_path/'work';repo.mkdir()
    git(repo,'init','-q');git(repo,'config','user.name','Fixture');git(repo,'config','user.email','fixture@example.invalid')
    (repo/'src/fdisbull').mkdir(parents=True);(repo/'tests').mkdir()
    (repo/'src/fdisbull/example.py').write_text('VALUE = 0\n')
    test=repo/'tests/test_example.py'
    test.write_text("from pathlib import Path\ndef test_value():\n    assert Path('src/fdisbull/example.py').read_text() == 'VALUE = 1\\n'\n")
    git(repo,'add','.');git(repo,'commit','-qm','fixture');git(repo,'checkout','-qb','codex/repair')
    sha=git(repo,'rev-parse','HEAD')
    policy={'source_sha':sha,'candidate_ref':'codex/repair','allowed_paths':['src/fdisbull/example.py'],
        'test_hashes':{'tests/test_example.py':hashlib.sha256(test.read_bytes()).hexdigest()},
        'reproducer_argv':['python','-m','pytest','-q','tests/test_example.py::test_value'], 'max_diff_bytes':4096}
    return repo,tmp_path/'state',policy


def make(workspace, change='valid'):
    repo,state,policy=workspace
    def runner(argv,**kwargs):
        if argv[0] == module.CODEX:
            if change=='unknown':
                return {'returncode':None,'stdout':b'', 'stderr':b'', 'timed_out':True,'overflow':False}
            (repo/'src/fdisbull/example.py').write_text('VALUE = 1\n')
            if change=='outside': (repo/'outside').write_text('bad')
            if change=='test': (repo/'tests/test_example.py').write_text('def test_value(): pass\n')
            return {'returncode':0,'stdout':b'{"type":"turn.completed"}\n','stderr':b'', 'timed_out':False,'overflow':False}
        return module._legacy.run_command(argv,**kwargs)
    return module.ProductionSourceRepair(repo,state,policy,runner=runner,admission=lambda path,p:True)


def test_success_commits_one_candidate_and_reconciles(workspace):
    repo,_,policy=workspace;worker=make(workspace);payload={'target':{'source_sha':policy['source_sha']}}
    result=worker('incident:repair',payload)
    assert result['source_sha'] != policy['source_sha'] and result['publication']=='unpublished'
    assert result['candidate_ref']=='codex/repair'
    assert 'Recovery-Action-Key: incident:repair' in git(repo,'log','-1','--format=%B')
    assert worker.reconcile('incident:repair',payload)==result
    with pytest.raises(FileExistsError): worker('incident:repair',payload)


@pytest.mark.parametrize('change',['outside','test','unknown'])
def test_untrusted_worker_cannot_commit_and_is_not_replayed(workspace,change):
    repo,_,policy=workspace;worker=make(workspace,change);payload={'target':{'source_sha':policy['source_sha']}}
    with pytest.raises(RuntimeError):worker('action',payload)
    assert git(repo,'rev-parse','HEAD')==policy['source_sha']
    assert worker.reconcile('action',payload) is None
    with pytest.raises(FileExistsError):worker('action',payload)


def test_passing_baseline_refuses_worker(workspace):
    repo,_,policy=workspace
    (repo/'src/fdisbull/example.py').write_text('VALUE = 1\n')
    git(repo,'add','.');git(repo,'commit','-qm','already fixed')
    policy['source_sha']=git(repo,'rev-parse','HEAD')
    worker=make(workspace)
    with pytest.raises(RuntimeError,match='baseline'):worker('action',{'target':{'source_sha':policy['source_sha']}})


def test_rejects_broad_or_mutable_reproducer(workspace):
    repo,state,policy=workspace
    policy['reproducer_argv']=['python','-m','pytest','-q','tests/test_example.py']
    with pytest.raises(ValueError):module.ProductionSourceRepair(repo,state,policy)


def test_reproducer_and_git_commands_receive_no_inherited_credentials(workspace, monkeypatch):
    repo, state, policy = workspace
    for name in ('GH_TOKEN', 'GITLAB_TOKEN', 'OPENAI_API_KEY', 'CUSTOM_PASSWORD', 'AWS_SECRET_ACCESS_KEY', 'SERVICE_CREDENTIAL'):
        monkeypatch.setenv(name, 'private-test-value')
    observed = []
    def runner(argv, **kwargs):
        env = kwargs['env']
        assert all(not any(marker in key.upper() for marker in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')) for key in env)
        observed.append(argv)
        return module._legacy.run_command(argv, **kwargs)
    worker = module.ProductionSourceRepair(repo, state, policy, runner=runner)
    worker._identity(policy['source_sha'])
    assert worker._check() == 1
    assert any(argv[0] == 'git' for argv in observed)
    assert any('-m' in argv and 'pytest' in argv for argv in observed)
