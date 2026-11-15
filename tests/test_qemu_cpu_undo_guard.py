"""Frozen native projection state permits inspection and certified recovery."""
from types import SimpleNamespace
import json
import threading
import time
import pytest

from fdisbull.qemu_cpu_undo_guard import before_operation, full_load
from fdisbull import qemu_cpu_undo_guard as guard


def owner(*,frozen=True):
    h=dict(id='projection',valid=not frozen,frozen=frozen,invalid_reason=None)
    s=SimpleNamespace(_qemu_cpu_delta_history=h,events=[],completed=0)
    s._event=lambda name,data:s.events.append((name,data))
    def complete():
        s.completed+=1
        h.update(valid=False,frozen=False)
    s._cpu_delta_full_restore_complete=complete
    return s


@pytest.mark.parametrize('name',['run','step','trace','write_memory','write_registers',
    'save_state','capture_surface','capture_display','frame_inputs','cpu_delta_start',
    'cpu_delta_record','cpu_delta_rewind','memory_snapshot','memory_rule_run',
    'save_experiment','compare_experiment'])
def test_frozen_projection_refuses_mutation_before_dispatch(name):
    s=owner()
    with pytest.raises(ValueError,match='frozen'):before_operation(s,name)
    assert s._qemu_cpu_delta_history['frozen'] and not s.events


@pytest.mark.parametrize('name',['registers','memory','code','keyboard_state',
    'dos_task_context','dos_task_memory','cpu_delta_status','clock_observe',
    'timeline_image','timeline_status','cpu_delta_recover','rewind','timeline_rewind',
    'controls','restore_experiment'])
def test_frozen_projection_allows_read_or_full_recovery_entry(name):
    s=owner();before_operation(s,name)
    assert s._qemu_cpu_delta_history['frozen'] and not s.events


def test_layer_query_allowed_but_new_stack_refuses():
    s=owner();before_operation(s,'dos_task_layers',kwargs={'active':None})
    with pytest.raises(ValueError):before_operation(s,'dos_task_layers',kwargs={'active':[]})


def test_unrecorded_mutation_invalidates_selected_history():
    s=owner(frozen=False);before_operation(s,'frame_inputs')
    assert not s._qemu_cpu_delta_history['valid'] and len(s.events)==1


def test_selected_operation_invalidates_live_frame_edge_only():
    s=owner(frozen=False);s._qemu_history_live=dict(valid=True,cursor='retained')
    before_operation(s,'cpu_delta_status');assert s._qemu_history_live['valid']
    before_operation(s,'cpu_delta_start')
    assert not s._qemu_history_live['valid'] and s._qemu_history_live['cursor'] is None


@pytest.mark.parametrize('result',[None,{},dict(source_binding_restored=False)])
def test_unverified_full_load_does_not_thaw(result):
    s=owner()
    @full_load
    def load(session):
        before_operation(session,'load_state')
        return result
    load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s._qemu_cpu_delta_full_load_depth==0


def test_only_successful_full_loader_clears_freeze_and_rebinds():
    s=owner()
    @full_load
    def load(session):
        before_operation(session,'load_state')
        session.vm=SimpleNamespace(epoch='new')
        return dict(source_binding_restored=True)
    load(s)
    assert not s._qemu_cpu_delta_history['frozen'] and s.completed==1
    assert s._qemu_cpu_delta_full_load_depth==0


def test_failed_full_loader_preserves_freeze_and_depth():
    s=owner()
    @full_load
    def load(session):
        raise ValueError('corrupt native anchor')
    with pytest.raises(ValueError):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and not s.completed
    assert s._qemu_cpu_delta_full_load_depth==0


def machine_vm(deadline,lock=None):
    return SimpleNamespace(process=SimpleNamespace(poll=lambda:None),
        qmp=SimpleNamespace(operation_deadline=deadline),gdb=None,
        operation_deadline=deadline,lock=threading.RLock() if lock is None else lock)


@pytest.fixture
def machine_owner(monkeypatch):
    clock=SimpleNamespace(now=100.)
    monkeypatch.setattr(time,'monotonic',lambda:clock.now)
    s=owner()
    s.project=object();s.run_id='owned-run';s.version={'id':'version','sha256':'b'*64}
    s.metadata={'source_sha256':'c'*64,'version_sha256':'b'*64}
    s._runtime_epoch='owned-run:1';s._checkpoint_epoch=1;s.closed=False
    s._deadline=110.;s._rpc_deadline=None;s.vm=machine_vm(110.)
    s.close_calls=0
    def close():
        s.close_calls+=1;s.closed=True
    s.close=close
    return s,clock


def replace_machine(s):
    s.vm=machine_vm(110.,s.vm.lock);s._runtime_epoch='owned-run:2';s._checkpoint_epoch=2
    return dict(artifact='machine-state',sha256='a'*64,machine_state_restored=True,
        source_binding_restored=False,host_files_restored=False,
        capture_epoch=s._runtime_epoch,checkpoint_epoch=s._checkpoint_epoch,
        registers={'eax':'0x1'})


def test_attested_machine_restore_thaws_without_claiming_source(machine_owner):
    s,_=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        return result
    result=load(s)
    assert not s._qemu_cpu_delta_history['frozen'] and not s._qemu_cpu_delta_history['valid']
    assert s.completed==1 and result['source_binding_restored'] is False
    assert json.loads(json.dumps(result))==result
    assert s._qemu_cpu_delta_full_load_depth==0
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


def test_bare_machine_boolean_and_fresh_owner_cannot_thaw(machine_owner):
    s,_=machine_owner
    @full_load
    def load(session):return replace_machine(session)
    result=load(s)
    assert result['machine_state_restored'] and s._qemu_cpu_delta_history['frozen']
    assert s.completed==0 and s._qemu_cpu_delta_full_load_depth==0


def test_machine_attestation_cannot_be_requested_outside_loader(machine_owner):
    s,_=machine_owner
    with pytest.raises(ValueError,match='full loader'):
        guard.attest_machine_restore(s,replace_machine(s))
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0


@pytest.mark.parametrize('fault',['owner','lock','project','run','version','epoch','checkpoint',
    'closed','process','qmp','quarantine','receipt_epoch','receipt_checkpoint','machine_flag','source_flag'])
def test_machine_attestation_refuses_unverified_transition(machine_owner,fault):
    s,_=machine_owner;original=s.vm
    @full_load
    def load(session):
        result=replace_machine(session)
        if fault=='owner':session.vm=original
        elif fault=='lock':session.vm.lock=threading.RLock()
        elif fault=='project':session.project=object()
        elif fault=='run':session.run_id='foreign'
        elif fault=='version':session.version['id']='foreign'
        elif fault=='epoch':session._runtime_epoch='owned-run:1'
        elif fault=='checkpoint':session._checkpoint_epoch=1
        elif fault=='closed':session.closed=True
        elif fault=='process':session.vm.process.poll=lambda:0
        elif fault=='qmp':session.vm.qmp=None
        elif fault=='quarantine':session.vm._fdisbull_control_quarantine='uncertain'
        elif fault=='receipt_epoch':result['capture_epoch']='foreign'
        elif fault=='receipt_checkpoint':result['checkpoint_epoch']=True
        elif fault=='machine_flag':result['machine_state_restored']=1
        else:result['source_binding_restored']=True
        guard.attest_machine_restore(session,result)
        return result
    with pytest.raises(ValueError):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s._qemu_cpu_delta_full_load_depth==0
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


@pytest.mark.parametrize('fault',['copy','content','source_flag','owner','lock','process','project','run','version',
                                 'epoch','checkpoint','closed'])
def test_machine_attestation_is_bound_through_loader_return(machine_owner,fault):
    s,_=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        if fault=='copy':return dict(result)
        if fault=='content':result['registers']['eax']='0x2'
        elif fault=='source_flag':result['source_binding_restored']=True
        elif fault=='owner':session.vm=machine_vm(110.)
        elif fault=='lock':session.vm.lock=threading.RLock()
        elif fault=='process':session.vm.process=SimpleNamespace(poll=lambda:None)
        elif fault=='project':session.project=object()
        elif fault=='run':session.run_id='foreign'
        elif fault=='version':session.version['sha256']='d'*64
        elif fault=='epoch':session._runtime_epoch='owned-run:3'
        elif fault=='checkpoint':session._checkpoint_epoch=3
        elif fault=='closed':session.closed=True
        return result
    with pytest.raises(ValueError):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s._qemu_cpu_delta_full_load_depth==0
    assert s.vm._fdisbull_control_quarantine and s.close_calls==1


def test_machine_attestation_cannot_outlive_deadline_restoration(machine_owner):
    s,clock=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        session._deadline=None;session.vm.operation_deadline=None
        session.vm.qmp.operation_deadline=None;clock.now=111.
        return result
    with pytest.raises(TimeoutError):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s.vm._fdisbull_control_quarantine and s.close_calls==1


def test_successful_attestation_survives_restoring_prior_deadline_fields(machine_owner):
    s,clock=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        session._deadline=None;session.vm.operation_deadline=None
        session.vm.qmp.operation_deadline=None;clock.now=101.
        return result
    load(s)
    assert not s._qemu_cpu_delta_history['frozen'] and s.completed==1 and s.close_calls==0


def test_late_attestation_failure_quarantines_even_without_selected_history(machine_owner):
    s,clock=machine_owner;s._qemu_cpu_delta_history=None
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        clock.now=111.
        return result
    with pytest.raises(TimeoutError):load(s)
    assert s.completed==0 and s.vm._fdisbull_control_quarantine and s.close_calls==1


def test_attestation_failure_preserves_primary_error_if_close_fails(machine_owner):
    s,_=machine_owner
    def fail_close():raise RuntimeError('cleanup failure')
    s.close=fail_close
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        result['registers']['eax']='0x2'
        return result
    with pytest.raises(ValueError,match='attestation changed') as caught:load(s)
    assert caught.value.machine_restore_cleanup_error=='RuntimeError'
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s.vm._fdisbull_control_quarantine


def test_failure_after_machine_attestation_does_not_thaw(machine_owner):
    s,_=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        raise RuntimeError('late publication failure')
    with pytest.raises(RuntimeError,match='late publication'):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s._qemu_cpu_delta_full_load_depth==0


def test_machine_attestation_is_consumed_once_and_result_cannot_replay(machine_owner):
    s,_=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        return result
    prior=load(s)
    s._qemu_cpu_delta_history['frozen']=True
    @full_load
    def replay(session):return prior
    replay(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==1


def test_machine_attestation_refuses_second_issue_in_one_invocation(machine_owner):
    s,_=machine_owner
    @full_load
    def load(session):
        result=replace_machine(session)
        guard.attest_machine_restore(session,result)
        guard.attest_machine_restore(session,result)
        return result
    with pytest.raises(ValueError):load(s)
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0


@pytest.mark.parametrize('pause_at',['body-return','completion'])
def test_ordinary_mutation_waits_for_verified_completion(machine_owner,pause_at):
    s,_=machine_owner;lock=s.vm.lock
    paused=threading.Event();finish=threading.Event();probed=threading.Event()
    immediate=[];mutations=[];errors=[]
    complete=s._cpu_delta_full_restore_complete
    if pause_at=='completion':
        def complete_after_pause():
            paused.set();assert finish.wait(2)
            complete()
        s._cpu_delta_full_restore_complete=complete_after_pause
    @full_load
    def load(session):
        with lock:
            result=replace_machine(session)
            guard.attest_machine_restore(session,result)
        if pause_at=='body-return':
            paused.set();assert finish.wait(2)
        return result
    def restore():
        try:load(s)
        except BaseException as error:errors.append(error)
    def mutate():
        acquired=lock.acquire(blocking=False)
        immediate.append(acquired);probed.set()
        if not acquired:acquired=lock.acquire(timeout=2)
        try:
            assert acquired
            before_operation(s,'write_memory')
            mutations.append((s._qemu_cpu_delta_full_load_depth,s._qemu_cpu_delta_history['frozen']))
        except BaseException as error:errors.append(error)
        finally:
            if acquired:lock.release()
    loader=threading.Thread(target=restore);mutation=threading.Thread(target=mutate)
    loader.start()
    try:
        assert paused.wait(2)
        mutation.start();assert probed.wait(2)
        assert immediate==[False]
    finally:
        finish.set();loader.join(2)
        if mutation.ident is not None:mutation.join(2)
    assert not loader.is_alive() and not mutation.is_alive() and not errors
    assert mutations==[(0,False)] and s.completed==1 and s._rpc_deadline is None


class ObservedRLock:
    def __init__(self):self.inner=threading.RLock();self.on_acquire=None
    def acquire(self,*args,**kwargs):
        if self.on_acquire is not None:self.on_acquire()
        return self.inner.acquire(*args,**kwargs)
    def release(self):return self.inner.release()
    def __enter__(self):self.acquire();return self
    def __exit__(self,*_):self.release()


def test_queued_full_loader_cannot_replace_active_scope_or_deadline(machine_owner):
    s,_=machine_owner;lock=ObservedRLock();s.vm.lock=lock
    paused=threading.Event();finish=threading.Event();attempted=threading.Event()
    snapshots=[];errors=[];second_body=[]
    @full_load
    def first(session):
        with lock:
            result=replace_machine(session)
            guard.attest_machine_restore(session,result)
        paused.set();assert finish.wait(2)
        return result
    @full_load
    def second(session):
        with lock:second_body.append(True)
        return dict(source_binding_restored=False)
    def run(operation):
        try:operation(s)
        except BaseException as error:errors.append(error)
    def observe_acquire():
        if threading.current_thread().name=='queued-full-loader':
            snapshots.append((s._qemu_cpu_delta_full_load_depth,
                              getattr(s,'_qemu_cpu_delta_machine_restore_scope',None)))
            attempted.set()
    lock.on_acquire=observe_acquire
    a=threading.Thread(target=run,args=(first,));b=threading.Thread(
        target=run,args=(second,),name='queued-full-loader')
    a.start()
    try:
        assert paused.wait(2)
        active=getattr(s,'_qemu_cpu_delta_machine_restore_scope')
        b.start();assert attempted.wait(2)
        assert snapshots[0]==(1,active) and not second_body
    finally:
        finish.set();a.join(2)
        if b.ident is not None:b.join(2)
    assert not a.is_alive() and not b.is_alive() and not errors
    assert second_body==[True] and s.completed==1 and s._rpc_deadline is None
    assert s._qemu_cpu_delta_full_load_depth==0
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


@pytest.mark.parametrize('failure',['body','proof'])
def test_failed_attested_loader_releases_stable_lock(machine_owner,failure):
    s,_=machine_owner;lock=s.vm.lock
    @full_load
    def load(session):
        with lock:
            result=replace_machine(session)
            guard.attest_machine_restore(session,result)
        if failure=='body':raise RuntimeError('inner cleanup failed')
        return dict(result)
    with pytest.raises((RuntimeError,ValueError)):load(s)
    acquired=[]
    def probe():
        success=lock.acquire(blocking=False);acquired.append(success)
        if success:lock.release()
    worker=threading.Thread(target=probe);worker.start();worker.join(2)
    assert not worker.is_alive() and acquired==[True]
    assert s._qemu_cpu_delta_history['frozen'] and s.completed==0
    assert s._rpc_deadline is None and s._qemu_cpu_delta_full_load_depth==0


def test_full_loader_lock_admission_timeout_does_not_create_scope(machine_owner):
    s,_=machine_owner;locked=threading.Event();finish=threading.Event();called=[]
    def hold():
        with s.vm.lock:locked.set();assert finish.wait(2)
    worker=threading.Thread(target=hold);worker.start();assert locked.wait(2)
    @full_load
    def load(session,*,timeout_ms=5):called.append(True)
    try:
        with pytest.raises(TimeoutError):load(s)
    finally:finish.set();worker.join(2)
    assert not called and s._qemu_cpu_delta_history['frozen'] and s._rpc_deadline is None
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


def test_full_loader_rechecks_owner_after_lock_admission(machine_owner):
    s,_=machine_owner;lock=ObservedRLock();s.vm.lock=lock;called=[]
    lock.on_acquire=lambda:setattr(s,'vm',machine_vm(110.,lock))
    @full_load
    def load(session):called.append(True)
    with pytest.raises(ValueError,match='owner changed'):load(s)
    assert not called and s._rpc_deadline is None and s._qemu_cpu_delta_history['frozen']
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


def test_full_loader_lock_cost_cannot_refresh_body_budget(machine_owner):
    s,clock=machine_owner;lock=ObservedRLock();s.vm.lock=lock;called=[]
    lock.on_acquire=lambda:setattr(clock,'now',101.001)
    @full_load
    def load(session,*,timeout_ms=1000):called.append(True)
    with pytest.raises(TimeoutError,match='before admission'):load(s)
    assert not called and s._rpc_deadline is None and s._qemu_cpu_delta_history['frozen']
    assert not hasattr(s,'_qemu_cpu_delta_machine_restore_scope')


def test_full_loader_restores_absent_rpc_field_exactly(machine_owner):
    s,_=machine_owner;del s._rpc_deadline
    @full_load
    def load(session):
        assert session._rpc_deadline==110.
        return dict(source_binding_restored=False)
    load(s)
    assert not hasattr(s,'_rpc_deadline')
    assert s._qemu_cpu_delta_full_load_depth==0 and s._qemu_cpu_delta_history['frozen']
