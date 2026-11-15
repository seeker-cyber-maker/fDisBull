"""Authored source/task/process contracts; not original DESQview evidence."""
from copy import deepcopy
import hashlib

import pytest

from fdisbull.project import Project
from fdisbull.runtime_tracking import AutomaticRuntimeTracker
from test_runtime_tracking import setup, Provider


class ContainedProvider(Provider):
    def __init__(self):
        super().__init__();self.handle=0x2222;self.next_event=None
    def current_identity(self):
        value=super().current_identity();value['handle']=self.handle
        value['process_membership']=self.membership(self.handle);return value
    def interpret_event(self,registers):
        assert self.next_event is not None
        return deepcopy(self.next_event)


def process(key,segment):
    return dict(key=key,record=dict(segment=segment,offset=0x100,linear=segment*16+0x100),
                mapping_context=segment,qualification='authored source-qualified relationship model only')


def event(provider,kind,owner=None,handle=None):
    owner=deepcopy(owner or provider.process);handle=handle or provider.handle
    return dict(kind=kind,handle=handle,process_identity=owner,containment_qualified=True,
        source_identity=deepcopy(provider.source_identity),
        target_relation=dict(qualified=True,kind='task-process-membership',task_handle=handle,
            task_record=dict(segment=handle,offset=0,linear=handle*16),
            owner_mapping_context=owner['mapping_context'],owner_process_record=deepcopy(owner['record']),
            method='original-dv2.8-task-owner-crosscheck'))


@pytest.fixture
def contained(setup,monkeypatch):
    p,s,match=setup;s.vm=object();s.metadata['capabilities']['lifecycle']['dos_guest_exit']=False
    provider=ContainedProvider();provider.process=process('authored-MS-process',0x6000)
    monkeypatch.setattr('fdisbull.runtime_desqview.discover',lambda _:provider)
    tracker=AutomaticRuntimeTracker(s);tracker.after_stop('authored MS source stop')
    assert tracker.status()['state']=='qualified-stopped-bindings'
    return p,s,match,provider,tracker


def stop(tracker,provider,value,collision=False):
    provider.next_event=value
    ids=list(tracker.internal_breakpoints)
    if collision:ids.append('authored-user-collision')
    return tracker.internal_stop(dict(breakpoints=ids))


def current(tracker):return tracker.status()['sources'][0]


def test_known_unrelated_process_end_preserves_ms_episode_and_physical_history(contained):
    p,s,match,provider,t=contained;old=current(t)['task'];at=p.runtime_mappings(old)['at']
    original_process=current(t)['identity']['process_episode']['incarnation']
    t.before_execution('machine-gdb-run')
    unrelated=process('authored-BigDOS-process',0x7000)
    assert stop(t,provider,event(provider,'process-end',unrelated,0x7777)) is True
    assert p._mapping_task(old)['ended'] is None
    s.physical=0x970000;t.after_stop('return to original MS')
    assert current(t)['task']==old and current(t)['identity']['process_episode']['incarnation']==original_process
    assert not p.runtime_resolve(old,0x870ff0,space='physical')['matches']
    assert p.runtime_resolve(old,0x970ff0,space='physical')['matches']
    assert p.runtime_resolve(old,0x870ff0,space='physical',at=at)['matches']


def test_process_end_closes_all_matching_source_aliases_only(contained):
    p,s,match,provider,t=contained;first=current(t)['task'];owner=deepcopy(provider.process)
    t.before_execution('machine-gdb-run');provider.handle=0x3333;t.after_stop('second task same process')
    second=current(t)['task'];assert second!=first
    t.before_execution('machine-gdb-run');provider.process=process('other-process',0x7000)
    t.after_stop('other source task');other=current(t)['task']
    assert stop(t,provider,event(provider,'process-end',owner,0x2222)) is True
    assert all(p._mapping_task(task)['ended'] is not None for task in [first,second])
    assert p._mapping_task(other)['ended'] is None
    assert t.status()['process_episodes'][0]['task_aliases']==[]
    assert t.status()['process_episodes'][0]['lifetime_state']=='end-observed-awaiting-later-source'
    t.after_stop('same other process');assert current(t)['task']==other


def test_task_handle_alias_in_other_process_is_not_retired(contained):
    p,s,match,provider,t=contained;first=current(t)['task'];owner=deepcopy(provider.process)
    t.before_execution('machine-gdb-run');provider.process=process('other-process',0x7000)
    t.after_stop('same numeric handle in other native process');other=current(t)['task'];assert other!=first
    assert stop(t,provider,event(provider,'end',owner,provider.handle)) is True
    assert p._mapping_task(first)['ended'] is not None and p._mapping_task(other)['ended'] is None
    t.after_stop('other alias remains');assert current(t)['task']==other
    assert current(t)['identity']['generation']==0


@pytest.mark.parametrize('kind',['process-end','process-create'])
def test_process_record_reuse_gets_new_episode_and_creation_attribution(contained,kind):
    p,s,match,provider,t=contained;first=current(t);old=first['task']
    assert stop(t,provider,event(provider,kind)) is True
    t.after_stop('same opaque process key after native lifetime boundary');new=current(t)
    assert new['task']!=old and p._mapping_task(old)['ended'] is not None
    assert new['identity']['process_episode']['incarnation']!=first['identity']['process_episode']['incarnation']
    assert new['identity']['process_episode']['generation']==1
    assert new['identity']['process_episode']['creation_observed'] is (kind=='process-create')
    assert new['identity']['creation_observed'] is False


def test_task_reuse_advances_only_that_task_generation_inside_process(contained):
    p,s,match,provider,t=contained;first=current(t);old=first['task']
    assert stop(t,provider,event(provider,'free')) is True
    t.after_stop('same handle after native free');new=current(t)
    assert new['task']!=old and new['identity']['generation']==1
    assert new['identity']['process_episode']['incarnation']==first['identity']['process_episode']['incarnation']
    assert new['identity']['creation_observed'] is False


@pytest.mark.parametrize('damage',['unknown','process-missing','unqualified','relation-owner','relation-task','record','provider-source','kind'])
def test_unknown_or_malformed_target_retires_continuity_and_keeps_stop_visible(contained,damage):
    p,s,match,provider,t=contained;old=current(t)['task'];native=event(provider,'process-end')
    if damage=='unknown':native['containment_qualified']=False
    if damage=='process-missing':native.pop('process_identity')
    if damage=='unqualified':native['target_relation']['qualified']=False
    if damage=='relation-owner':native['target_relation']['owner_mapping_context']^=1
    if damage=='relation-task':native['target_relation']['task_handle']^=1
    if damage=='record':native['process_identity']['record']['linear']^=1
    if damage=='provider-source':native['source_identity']['source_sha256']='cd'*32
    if damage=='kind':native['kind']='unknown-native-event'
    assert stop(t,provider,native) is False
    assert p._mapping_task(old)['ended'] is not None and not p.runtime_mappings(old)['bindings']
    assert t.provider is None and t.status()['state']=='unqualified'
    assert t.status()['current_bindings']==0 and not t.status()['process_episodes']


def test_event_affected_process_never_falls_back_to_current_process(contained):
    p,s,match,provider,t=contained;ms=current(t)['task']
    native=event(provider,'process-end',process('other',0x7000),0x7777)
    native['current_identity']=provider.current_identity()
    assert stop(t,provider,native) is True
    assert p._mapping_task(ms)['ended'] is None


def test_unknown_current_process_cannot_publish_a_source_binding(contained):
    p,s,match,provider,t=contained;old=current(t)['task'];provider.process.pop('qualification')
    count=len(s.snapshots);t.after_stop('source matched but ownership unknown')
    assert t.status()['state']=='unqualified' and t.status()['current_bindings']==0
    assert len(s.snapshots)==count and p._mapping_task(old)['ended'] is not None


def test_user_collision_scopes_process_end_but_leaves_user_stop_visible(contained):
    p,s,match,provider,t=contained;ms=current(t)['task']
    assert stop(t,provider,event(provider,'process-end',process('other',0x7000),0x7777),collision=True) is False
    assert p._mapping_task(ms)['ended'] is None


def test_process_episode_relation_and_closed_history_survive_reopen(contained):
    p,s,match,provider,t=contained;task=current(t)['task'];native=deepcopy(current(t)['identity'])
    source_before=p.source_sha256();assert stop(t,provider,event(provider,'process-end')) is True
    with Project(p.path) as reopened:
        row=reopened._mapping_task(task)
        assert row['automatic_tracking']['identity']==native
        assert row['ended'] is not None and not reopened.runtime_mappings(task)['bindings']
        assert reopened.source_sha256()==source_before


def test_global_manager_end_needs_no_per_task_containment(contained):
    p,s,match,provider,t=contained;task=current(t)['task']
    assert stop(t,provider,dict(kind='dv-end',source_identity=deepcopy(provider.source_identity))) is False
    assert p._mapping_task(task)['ended'] is not None and not p.runtime_mappings(task)['bindings']
    assert t.provider is None and not t.status()['process_episodes']


def test_same_process_key_cannot_change_its_native_owner_record(contained):
    p,s,match,provider,t=contained;task=current(t)['task']
    native=event(provider,'process-end')
    native['process_identity']['record']['segment']+=1
    native['process_identity']['record']['linear']+=16
    native['target_relation']['owner_process_record']=deepcopy(native['process_identity']['record'])
    assert stop(t,provider,native) is False
    assert p._mapping_task(task)['ended'] is not None
    assert t.status()['containment_rejection']['kind']=='recorded'


@pytest.mark.parametrize('field',['task_handle','owner_mapping_context'])
def test_boolean_relation_fields_are_not_integer_identity(contained,field):
    p,s,match,provider,t=contained;task=current(t)['task'];native=event(provider,'process-end')
    native['target_relation'][field]=True
    assert stop(t,provider,native) is False
    assert p._mapping_task(task)['ended'] is not None


@pytest.mark.parametrize('kind',['swap-out','swap-in'])
def test_swap_process_mapping_is_separate_from_emitter_task(contained,kind):
    p,s,match,provider,t=contained;task=current(t)['task'];owner=process('other-swapped-process',0x7000)
    native=event(provider,kind,owner)
    native['target_relation']=dict(qualified=True,kind='process-mapping',
        owner_mapping_context=owner['mapping_context'],owner_process_record=deepcopy(owner['record']),
        method='original-dv2.8-process-mapping-crosscheck')
    native['current_identity']=provider.current_identity()
    assert stop(t,provider,native) is True
    assert p._mapping_task(task)['ended'] is None and t.provider is provider


def test_process_mapping_does_not_qualify_a_task_end(contained):
    p,s,match,provider,t=contained;task=current(t)['task'];native=event(provider,'end')
    native['target_relation']['kind']='process-mapping'
    native['target_relation']['method']='original-dv2.8-process-mapping-crosscheck'
    assert stop(t,provider,native) is False
    assert p._mapping_task(task)['ended'] is not None and t.provider is None


@pytest.mark.parametrize('kind',['other','save','restore'])
def test_recognized_non_lifetime_notification_cannot_establish_target_ownership(contained,kind):
    p,s,match,provider,t=contained;task=current(t)['task']
    native=dict(kind=kind,handle=0x7777,containment_qualified=False,process_identity=None,
                source_identity=deepcopy(provider.source_identity))
    assert stop(t,provider,native) is True
    assert p._mapping_task(task)['ended'] is None and t.provider is provider
    assert len(t.status()['process_episodes'])==1


@pytest.mark.parametrize('damage',['missing','unqualified','handle','mapping','record'])
def test_source_publication_requires_matching_current_membership(contained,damage):
    p,s,match,provider,t=contained;task=current(t)['task'];original=provider.current_identity
    def malformed():
        native=original()
        if damage=='missing':native.pop('process_membership')
        if damage=='unqualified':native['process_membership']['qualified']=False
        if damage=='handle':native['process_membership']['task_handle']^=1
        if damage=='mapping':native['process_membership']['owner_mapping_context']^=1
        if damage=='record':native['process_membership']['owner_process_record']['linear']^=1
        return native
    provider.current_identity=malformed;count=len(s.snapshots)
    t.after_stop('matching bytes without qualified current ownership')
    assert t.status()['state']=='unqualified' and p._mapping_task(task)['ended'] is not None
    assert len(s.snapshots)==count and t.provider is None
