import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('github_once', Path(__file__).parents[1]/'scripts/ci/github-once.py')
once = importlib.util.module_from_spec(spec); spec.loader.exec_module(once)


def test_lease_requires_matching_exclusive_flock_and_owner():
    device = os.makedev(8, 5)
    line = '42: FLOCK ADVISORY WRITE 123 08:05:77 0 EOF\n'
    assert once._has_flock(line, 123, device, 77)
    assert not once._has_flock(line, 124, device, 77)
    assert not once._has_flock(line.replace('WRITE', 'READ'), 123, device, 77)
    assert not once._has_flock(line, 123, device, 78)


def test_invalid_inherited_fd_binding_never_accepted(monkeypatch, tmp_path):
    lock = tmp_path/'lock'; lock.write_text('')
    monkeypatch.setattr(once, 'LOCK', lock)
    monkeypatch.setattr(once.os, 'fstat', lambda fd: SimpleNamespace(st_dev=1, st_ino=2))
    monkeypatch.setattr(once.os, 'getppid', lambda: 123)
    assert once.verify_lease(5, 999, 1, 2) is False


def test_workflow_routes_to_ordinary_wrapper_with_fixed_policy_and_limits():
    import hashlib
    root = Path(__file__).parents[1]
    workflow = (root/'.github/workflows/ovh-bootstrap.yml').read_text()
    policy_hash = hashlib.sha256((root/'scripts/ci/qualification-policy.json').read_bytes()).hexdigest()
    assert '--policy-sha ' + policy_hash in workflow
    assert 'production-qualification.py' in workflow and 'github-bootstrap.py' not in workflow
    assert '--cpus=2 --memory=9g --memory-swap=9g' in workflow
    assert '/ci-control/production:ro' in workflow and 'actions: read' in workflow


def test_cleanup_stops_only_exact_inspected_labeled_container():
    import json
    labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':'42','fdisbull.ci.run_attempt':'1',
            'fdisbull.ci.control_sha':'a'*40}
    cid='c'*64; calls=[]; running=[True]
    def run(args, **kwargs):
        calls.append(args)
        if args[1]=='ps':
            assert all('label='+k+'='+v in args for k,v in labels.items())
            out=cid+'\n'
        elif args[1]=='inspect':
            assert args[2]==cid
            out=json.dumps([{'Id':cid,'Config':{'Labels':labels},'State':{'Running':running[0]}}])
        elif args[1]=='stop':
            assert args[-1]==cid;running[0]=False;out=cid
        return SimpleNamespace(returncode=0,stdout=out)
    result=once.cleanup_owned(labels,runner=run,sleeper=lambda _:None)
    assert result['status']=='clean' and result['containers'][0]['final_running'] is False
    assert len([x for x in calls if x[1]=='stop'])==1


def test_cleanup_refuses_mismatched_labels_without_stopping():
    import json
    labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':'42','fdisbull.ci.run_attempt':'1',
            'fdisbull.ci.control_sha':'a'*40}
    cid='c'*64;calls=[]
    def run(args, **kwargs):
        calls.append(args)
        out=cid if args[1]=='ps' else json.dumps([{'Id':cid,'Config':{'Labels':{}},'State':{'Running':True}}])
        return SimpleNamespace(returncode=0,stdout=out)
    assert once.cleanup_owned(labels,runner=run,sleeper=lambda _:None)['status']=='unknown'
    assert not any(x[1]=='stop' for x in calls)


def test_cleanup_unknown_if_docker_unavailable_or_inventory_changes():
    import subprocess
    labels={'fdisbull.ci.provider':'github','fdisbull.ci.run_id':'42','fdisbull.ci.run_attempt':'1',
            'fdisbull.ci.control_sha':'a'*40}
    def fail(*args,**kwargs):raise subprocess.TimeoutExpired('docker',35)
    assert once.cleanup_owned(labels,runner=fail,sleeper=lambda _:None)['status']=='unknown'
    calls=[]
    def changing(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='' if len(calls)==1 else 'c'*64)
    assert once.cleanup_owned(labels,runner=changing,sleeper=lambda _:None)['status']=='unknown'


def test_existing_capsule_matches_without_overwrite_and_stale_fails(tmp_path):
    import json
    import time
    import pytest
    from test_offline_qualification import record
    health = importlib.util.spec_from_file_location('health_fixture', Path(__file__).parents[1]/'scripts/ci/offline-qualification.py')
    module = importlib.util.module_from_spec(health); health.loader.exec_module(module)
    item=record();item['observed_epoch']=1000.0
    expected={'schema':'fdisbull-host-health-capsule-1','run_id':'42','run_attempt':'1',
              'source_sha':'b'*40,'control_sha':'a'*40,'ref':'control'}
    capsule={**expected,'host_health':{'helper_sha256':module.HELPER_SHA256,'failure':None,'record':item}}
    path=tmp_path/'capsule.json';path.write_text(json.dumps(capsule));before=path.read_bytes()
    assert once.existing_capsule(path,expected,now=1100)==capsule
    assert path.read_bytes()==before
    with pytest.raises(ValueError,match='stale'):once.existing_capsule(path,expected,now=1121)
    assert path.read_bytes()==before


def test_workflow_container_options_do_not_interpolate_dispatch_inputs():
    workflow=(Path(__file__).parents[1]/'.github/workflows/ovh-bootstrap.yml').read_text()
    options=next(line for line in workflow.splitlines() if line.lstrip().startswith('options:'))
    assert 'inputs.' not in options and 'source_sha=' not in options
    for label in ('fdisbull.ci.provider=github','fdisbull.ci.run_id=${{ github.run_id }}',
                  'fdisbull.ci.run_attempt=${{ github.run_attempt }}','fdisbull.ci.control_sha=${{ github.sha }}'):
        assert label in options


def test_only_run_results_and_safe_job_inputs_are_mounted(monkeypatch,tmp_path):
    workflow=(Path(__file__).parents[1]/'.github/workflows/ovh-bootstrap.yml').read_text()
    options=next(line for line in workflow.splitlines() if line.lstrip().startswith('options:'))
    assert '--volume /var/lib/fdisbull-ci/control/production/job-inputs:/ci-control/production:ro' in options
    assert '--volume /var/lib/fdisbull-ci/control:/ci-control' not in options
    assert ('--volume /var/lib/fdisbull-ci/results/github/${{ github.run_id }}/${{ github.run_attempt }}:'
            '/ci-host-results/${{ github.run_id }}/${{ github.run_attempt }}') in options
    assert '--volume /var/lib/fdisbull-ci/results/github:/ci-host-results' not in options
    monkeypatch.setattr(once,'LOCK',tmp_path/'ci-executor.lock')
    assert once.capsule_path('42','2')==tmp_path/'production/job-inputs/health/42/2.json'


def test_job_inputs_must_be_preinstalled_private_and_not_symlink(tmp_path):
    import pytest
    path=tmp_path/'job-inputs'
    with pytest.raises(ValueError,match='unavailable'):once.verify_job_inputs(path)
    path.mkdir(mode=0o700)
    assert once.verify_job_inputs(path)==path
    path.chmod(0o755)
    with pytest.raises(ValueError,match='unavailable'):once.verify_job_inputs(path)
    alias=tmp_path/'alias';alias.symlink_to(path, target_is_directory=True)
    with pytest.raises(ValueError,match='unavailable'):once.verify_job_inputs(alias)
