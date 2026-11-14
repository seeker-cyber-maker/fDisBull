"""Authored contracts for automatic mapping; native qualification is separate."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from fdisbull.runtime_tracking import AutomaticRuntimeTracker
from test_runtime_mapping_snapshots import capture


class Session:
    def __init__(self, project, owned=True):
        self.project=project; self.version=project.version(); self.run_id='authored-run'
        self.session_id='owned-native-fixture'; self._runtime_epoch='incarnation-1'
        self.metadata=dict(source_sha256=project.source_sha256(),
            capabilities=dict(lifecycle=dict(dos_guest_exit=owned)))
        self.physical=0x870000; self.corrupt=False
        self.memory=project.regions(1)[0].data[:32]
        self.snapshots=[]
        self.breakpoints={}
        self.next_breakpoint=1

    def registers(self):return dict(authored_stopped_cpu=True)

    def breakpoint(self,address):
        identifier='authored-bp-'+str(self.next_breakpoint);self.next_breakpoint+=1
        self.breakpoints[identifier]=dict(address=address,access='x',length=1)
        return dict(breakpoint_id=identifier)

    def delete_breakpoint(self,identifier):self.breakpoints.pop(identifier)

    def _artifact(self,*args):return self.project._debug_artifact(self.run_id,*args)

    def memory_snapshot(self,address,*,length,task_id,name):
        pages=[dict(linear='0x123000',physical=hex(self.physical),entries=[]),
               dict(linear='0x124000',physical=hex(self.physical+0x3000),entries=[])]
        raw=bytearray(self.memory)
        if self.corrupt:raw[-1]^=1
        identifier=capture(self.project,bytes(raw),start=address,task=task_id,pages=pages)
        self.snapshots.append(identifier)
        return dict(artifact=identifier)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    target=tmp_path/'fixture.bin';target.write_bytes(bytes(range(256))*32)
    with Project.create(tmp_path/'fixture.fdb',target,arch='x86',bits=32) as p:
        with p.transaction(True):p.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            ('authored-run',1,'authored',None,'stopped','{}'))
        session=Session(p)
        match=dict(source_identity=dict(sha256=p.source_sha256()),identity_evidence=dict(lifetime_qualified=False),
            source_spans=[dict(name='code',address=0x123ff0,length=32,object_id='region:0',object_offset=0)])
        monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _: [deepcopy(match)])
        yield p,session,match


def test_automatic_pages_remap_under_same_owned_launch_and_persist(setup):
    p,s,_=setup;t=AutomaticRuntimeTracker(s)
    t.after_stop('entry');status=t.status();assert status['state']=='qualified-stopped-bindings'
    task=status['sources'][0]['task'];first=p.runtime_mappings(task)['bindings']
    assert [b['length'] for b in first]==[16,16]
    assert [b['physical_start'] for b in first]==[0x870ff0,0x873000]
    assert p.runtime_resolve(task,0x870ff0,space='physical')['matches']
    at=p.runtime_mapping_events(task)['events'][-1]['sequence']
    t.before_execution('execution.continue')
    assert p.runtime_mappings(task)['bindings']==[]
    s.physical=0x970000;t.after_stop('timeout')
    assert t.status()['sources'][0]['task']==task
    assert not p.runtime_resolve(task,0x870ff0,space='physical')['matches']
    assert p.runtime_resolve(task,0x970ff0,space='physical')['matches']
    assert p.runtime_resolve(task,0x870ff0,space='physical',at=at)['matches']
    t.close('normal session closed')
    assert t.status()['closed'] and not p.runtime_mappings(task)['bindings']
    with Project(p.path) as reopened:
        assert reopened.runtime_tasks()['tasks'][0]['ended'] is not None
        assert reopened.runtime_resolve(task,0x870ff0,space='physical',at=at)['matches']


def test_source_match_without_native_lifetime_never_joins_execution_gap(setup):
    p,s,_=setup;s.metadata['capabilities']['lifecycle']['dos_guest_exit']=False
    t=AutomaticRuntimeTracker(s);t.after_stop('entry');first=t.status()['sources'][0]['task']
    t.before_execution('execution.continue');t.after_stop('timeout')
    assert t.status()['sources'][0]['task']!=first
    assert p._mapping_task(first)['ended'] is not None
    assert t.status()['lifetime_qualification']=='one-stop-only'


@pytest.mark.parametrize('reason',['state.load','restore checkpoint','resume','memory.write','parent execution'])
def test_restore_write_and_unmonitored_resume_close_identity(setup,reason):
    p,s,_=setup;t=AutomaticRuntimeTracker(s);t.after_stop('entry');old=t.status()['sources'][0]['task']
    t.before_execution(reason);t.after_stop('fresh stop')
    assert t.status()['sources'][0]['task']!=old
    assert p._mapping_task(old)['ended'] is not None


def test_failed_comparison_closes_partial_publication_without_replaying(setup):
    p,s,_=setup;t=AutomaticRuntimeTracker(s);s.corrupt=True;t.after_stop('performed operation')
    assert t.status()['state']=='unqualified'
    assert 'do not match' in t.status()['error']
    tasks=p.runtime_tasks()['tasks'];assert len(tasks)==1
    assert p.runtime_mappings(tasks[0]['id'])['bindings']==[]


def test_invalidation_failure_propagates_before_dispatch(setup,monkeypatch):
    p,s,_=setup;t=AutomaticRuntimeTracker(s);t.after_stop('entry')
    def fail(*args,**kwargs):raise OSError('journal unavailable')
    monkeypatch.setattr(p,'runtime_unmap',fail)
    with pytest.raises(OSError,match='journal unavailable'):t.before_execution('execution.continue')


def test_no_match_and_unsupported_preserve_unknown(setup,monkeypatch):
    _,s,_=setup;t=AutomaticRuntimeTracker(s)
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[])
    t.after_stop('ordinary BIOS stop');assert t.status()['state']=='no-source-match'
    def fail(_):raise ValueError('unqualified CPU state')
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover',fail)
    t.after_stop('unsupported stop');assert t.status()['state']=='unqualified'
    assert t.status()['current_bindings']==0


class Provider:
    """Explicit native-provider double; no vendor calls or guest execution."""
    hook_address=0x5000
    source_identity=dict(provider='authored-test-provider', source_sha256='ab'*32)
    catalog=dict(hook='authored lifecycle point')
    def __init__(self):self.failure=False;self.supervisor=False;self.fingerprint_failure=False;self.event=dict(kind='end',handle=0x2222)
    def validate_coverage(self):
        if self.failure or self.fingerprint_failure:raise ValueError('authored manager fingerprint changed')
        return dict(coverage_qualified=True,task_identity_qualified=False)
    def current_identity(self):
        if self.failure:raise ValueError('authored manager source no longer matches')
        if self.supervisor:raise ValueError('current protected supervisor is not a DOS task context')
        return dict(handle=0x2222,qualification='authored stopped identity, not native evidence')
    def interpret_event(self,registers):return deepcopy(self.event)


def provider_tracker(setup,monkeypatch):
    p,s,match=setup;s.vm=SimpleNamespace();s.metadata['capabilities']['lifecycle']['dos_guest_exit']=False
    provider=Provider();monkeypatch.setattr('fdisbull.runtime_desqview.discover',lambda _:provider)
    tracker=AutomaticRuntimeTracker(s);tracker.after_stop('first manager/source observation')
    assert tracker.status()['state']=='qualified-stopped-bindings'
    return p,s,match,provider,tracker


def test_end_only_reuse_is_a_new_incarnation_without_claiming_creation(setup,monkeypatch):
    p,s,_,provider,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task']
    assert t.status()['sources'][0]['identity']['creation_observed'] is False
    provider.event=dict(kind='end',handle=0x2222)
    assert t.internal_stop(dict(breakpoints=list(t.internal_breakpoints))) is True
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    t.after_stop('same handle after observed end')
    now=t.status()['sources'][0]
    assert now['task']!=old and now['identity']['generation']==1
    assert now['identity']['creation_observed'] is False


@pytest.mark.parametrize('alteration',['missing','address','access','length'])
def test_missing_or_changed_owned_hook_retires_before_execution(setup,monkeypatch,alteration):
    p,s,_,_,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task'];owned=next(iter(t.internal_breakpoints))
    s.breakpoints['unrelated-user']=dict(address=0x9000,access='x',length=1)
    if alteration=='missing':s.breakpoints.pop(owned)
    else:s.breakpoints[owned][alteration]={'address':0x5001,'access':'w','length':2}[alteration]
    t.before_execution('machine-gdb-run')
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    assert 'unrelated-user' in s.breakpoints
    t.after_stop('fresh reattachment')
    assert t.status()['sources'][0]['task']!=old


@pytest.mark.parametrize('failure',['source','provider'])
def test_failed_observation_retires_lifetime_and_cannot_inherit_later(setup,monkeypatch,failure):
    p,s,match,provider,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task'];snapshots=len(s.snapshots)
    if failure=='provider':provider.failure=True
    else:
        def corrupt(_):raise ValueError('authored executable source mismatch')
        monkeypatch.setattr('fdisbull.runtime_source_matching.discover',corrupt)
    t.after_stop('one completed action, failed enrichment')
    assert t.status()['state']=='unqualified' and t.status()['current_bindings']==0
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    assert len(s.snapshots)==snapshots  # Failure did not replay or capture a replacement action.
    provider.failure=False;monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[deepcopy(match)])
    t.after_stop('new independently qualified observation')
    assert t.status()['sources'][0]['task']!=old
    assert 'error' not in t.status()


def test_colliding_user_breakpoint_keeps_stop_visible_but_records_creation(setup,monkeypatch):
    p,s,_,provider,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task'];owned=next(iter(t.internal_breakpoints))
    s.breakpoints['user-at-callout']=dict(address=provider.hook_address,access='x',length=1)
    provider.event=dict(kind='create',handle=0x2222)
    assert t.internal_stop(dict(breakpoints=[owned,'user-at-callout'])) is False
    assert 'user-at-callout' in s.breakpoints
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    t.after_stop('user-visible lifecycle stop')
    now=t.status()['sources'][0]
    assert now['task']!=old and now['identity']['creation_observed'] is True
    assert now['identity']['generation']==1


def test_unrelated_protected_stop_preserves_monitored_task_on_ordinary_return(setup,monkeypatch):
    p,s,match,provider,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task'];provider.supervisor=True
    # The CPU is now in a protected manager handler. It supplies no current
    # application source match or task identity, but the original lifecycle
    # callout and its owned breakpoint remain qualified and monitored.
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[])
    t.after_stop('ordinary protected supervisor pause')
    assert t.status()['state']=='no-source-match' and not p.runtime_mappings(old)['bindings']
    t.before_execution('machine-gdb-run')
    assert p._mapping_task(old)['ended'] is None
    provider.supervisor=False;monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[deepcopy(match)])
    t.after_stop('ordinary return to same DOS task')
    assert t.status()['sources'][0]['task']==old
    assert t.status()['sources'][0]['identity']['creation_observed'] is False


def test_failed_manager_fingerprint_at_protected_stop_still_retires_task(setup,monkeypatch):
    p,s,match,provider,t=provider_tracker(setup,monkeypatch);old=t.status()['sources'][0]['task'];provider.supervisor=True
    monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[])
    t.after_stop('protected handler pause');provider.fingerprint_failure=True
    t.before_execution('machine-gdb-run')
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    provider.supervisor=provider.fingerprint_failure=False;monkeypatch.setattr('fdisbull.runtime_source_matching.discover',lambda _:[deepcopy(match)])
    t.after_stop('new independently qualified DOS stop')
    assert t.status()['sources'][0]['task']!=old
