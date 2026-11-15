"""Persistent QEMU history contracts over real project artifacts and a fake VM.

These host-only tests do not assert native QEMU checkpoint behavior.
"""
from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from fdisbull.qemu_dos_checkpoint import _preflight as real_checkpoint_preflight


@pytest.fixture
def project(tmp_path):
    source = tmp_path / 'history.com'
    source.write_bytes(bytes.fromhex('90ebfd'))
    with Project.create(tmp_path / 'history.fdb', source, image='com') as instance:
        yield instance


def _run(project, run_id):
    version = project.version()
    metadata = dict(source_sha256=project.meta['source_sha256'], version_sha256=version['sha256'])
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (run_id,version['id'],'authored',None,'stopped',json.dumps(metadata)))
    return version, metadata


def _artifact_rows(project, kind):
    return project.db.execute('SELECT id, data, sha256, metadata FROM debug_artifacts WHERE kind=? ORDER BY rowid',
                              (kind,)).fetchall()


class Harness:
    """Fake stopped checkpoint peer; artifacts and history are real SQLite data."""
    def __init__(self, project, run_id='run-1'):
        from fdisbull.qemu_dos_history import QemuDOSHistoryMixin
        self.__class__ = type('HistoryHarness', (Harness, QemuDOSHistoryMixin), {})
        from fdisbull.qemu_dos_checkpoint import COMMAND
        self.project = project
        self.version, self.metadata = _run(project, run_id)
        self.metadata['backend'] = 'qemu-dos'
        self.run_id = run_id
        checkpoint_disk = project.path.parent / (run_id + '-authored-private.qcow2')
        checkpoint_disk.write_bytes(b'authored-private-disk')
        self.vm = SimpleNamespace(lock=threading.RLock(), operation_deadline=None, qmp=None, gdb=None,
            checkpoint_disk=checkpoint_disk, qmp_commands={COMMAND},
            process=SimpleNamespace(poll=lambda: None))
        self._checkpoint_launch = {'checkpoint_tool':'fake-qemu-img'}
        self._process = {'state':'active','machine_closed':False}
        self.guest_profile = {'schema':1,'profile_sha256':'1'*64}
        self._tail = b''; self._helper = b'authored-helper'; self.closed = False
        self.pc = 0; self.calls = []; self.events = []; self.fault = None
        self._history_bind()

    def _stopped(self): return None
    def _input_schedule_bound(self):
        state = getattr(self.vm, '_physical_input', {})
        return bool((state.get('schedule') or {}).get('bound'))
    def registers(self):
        return {'general':{'eax':hex(self.pc)},'segments':{'cs':'0x100'},
                'instruction_pointer':hex(self.pc),'flags':'0x2','cpu_mode':'real',
                'address_state':{'machine_vcpus':1}}
    def _event(self,name,value): self.events.append((name,deepcopy(value)))
    def close(self): self.closed = True
    def save_state(self,name,*,max_bytes=None):
        from fdisbull.qemu_dos_checkpoint import FORMAT
        self.calls.append(('save',self.pc))
        if self.fault == 'save': raise TimeoutError('lost save reply')
        payload = json.dumps({'pc':self.pc}).encode()
        if max_bytes is not None and len(payload) > max_bytes: raise ValueError('size limit')
        return self.project._debug_artifact(self.run_id,name,'state',payload,
                                            {'format':FORMAT,'host_files_restored':False,
                                             'source_sha256':self.metadata['source_sha256'],
                                             'version_sha256':self.metadata['version_sha256']})
    def load_state(self,artifact,*,timeout_ms=60000):
        self.calls.append(('load',artifact))
        if self.fault == 'load': raise TimeoutError('lost restore reply')
        row = self.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        self.pc = json.loads(bytes(row['data']))['pc']
        old = self.vm
        self.vm = SimpleNamespace(**vars(old))
        self.vm.history_operation_guard = None
        self._history_bind()
        return {'source_binding_restored':True}
    def step(self,*,timeout_ms=60000):
        self.calls.append(('step',self.pc)); self.pc += 1
        if self.fault == 'step': raise TimeoutError('lost step reply')
        return {'outcome':'step','timed_out':False,'session':{'state':'stopped',
                 'stop_reason':{'kind':'step','breakpoint_ids':[]}}}


@pytest.fixture
def session(project, monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._compatibility',lambda session: {'runtime':'authored'})
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight',lambda session: None)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._serial_idle',lambda session: None)
    return Harness(project)


def test_history_lineage_persists_and_branches_without_deleting_nodes(session):
    start = session.rewind_start(max_steps=5,max_bytes=65536)
    assert start['retained_nodes'] == 1 and start['host_files_restored'] is False
    root = start['cursor']
    first = session.rewind_record(count=2)
    assert first['recorded_count'] == 2 and session.pc == 2
    old_head = first['cursor']; previous_manifest = first['history']
    rewind = session.rewind(count=1)
    assert session.pc == 1 and rewind['cursor'] != old_head
    branch = session.rewind_record(count=1)
    assert branch['retained_nodes'] == 4 and old_head in branch['node_ids']
    assert branch['nodes'][-1]['parent'] == rewind['cursor']
    old_row = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                         (previous_manifest,)).fetchone()
    old = json.loads(bytes(old_row['data']))
    assert len(old['nodes']) == 3 and old_head in [node['id'] for node in old['nodes']]
    assert len(_artifact_rows(session.project,'state')) == 4
    assert len(_artifact_rows(session.project,'rewind-history')) > 4
    assert all(n['edge'].get('completed_instruction') is not True for n in branch['nodes'])


def test_unrecorded_mutation_invalidates_live_cursor_but_capture_is_explicit(session):
    initial = session.rewind_start(max_steps=4,max_bytes=65536)
    session.vm.history_operation_guard('write_memory',(),{})
    status = session.rewind_status()
    assert status['valid'] is False and status['cursor'] is None
    with pytest.raises(ValueError): session.rewind_record()
    session.pc = 9
    result = session.rewind_record(advance='capture')
    assert result['nodes'][-1]['edge']['kind'] == 'capture'
    assert result['nodes'][-1]['parent'] == initial['cursor']
    assert not any(call[0]=='step' for call in session.calls)


def test_saved_history_can_be_attached_and_restored_in_another_session(project,session):
    first = session.rewind_start(max_steps=4,max_bytes=65536)
    latest = session.rewind_record()
    second = Harness(project,'run-2')
    attached = second.rewind_start(history=latest['history'])
    assert not attached['valid'] and attached['cursor'] is None
    restored = second.rewind(history=latest['history'],node=first['cursor'])
    assert restored['cursor'] == first['cursor'] and second.pc == 0
    assert second.vm.history_operation_guard is not None
    second.vm.history_operation_guard('write_memory',(),{})
    assert second.rewind_status()['valid'] is False


def test_corrupt_or_missing_checkpoint_refused_before_native_restore(session):
    start = session.rewind_start(max_steps=3,max_bytes=65536)
    node = start['nodes'][0]; artifact = node['checkpoint']['artifact']
    with session.project.transaction(True):
        session.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'corrupt',artifact))
    with pytest.raises(ValueError,match='corrupt|missing'):
        session.rewind(history=start['history'],node=start['cursor'])
    assert not any(call[0]=='load' for call in session.calls) and not session.closed


def test_capture_budget_preserves_previous_nodes_before_any_guest_execution(session):
    start = session.rewind_start(max_steps=1,max_bytes=65536)
    with pytest.raises(ValueError,match='budget'):
        session.rewind_record(count=1)
    assert not any(call[0]=='step' for call in session.calls)
    assert session.rewind_status()['node_ids'] == start['node_ids']


def test_lost_step_reply_keeps_pending_and_refuses_replay(session):
    session.rewind_start(max_steps=4,max_bytes=65536)
    session.fault = 'step'
    with pytest.raises(TimeoutError): session.rewind_record()
    assert session.closed
    manifests = _artifact_rows(session.project,'rewind-history')
    assert json.loads(bytes(manifests[-1]['data']))['pending']['kind'] == 'step'
    assert len([call for call in session.calls if call[0]=='step']) == 1


def test_lost_restore_reply_keeps_pending_and_closes_owner(session):
    root = session.rewind_start(max_steps=4,max_bytes=65536)
    session.rewind_record()
    session.fault = 'load'
    with pytest.raises(TimeoutError): session.rewind(node=root['cursor'])
    assert session.closed
    manifests = _artifact_rows(session.project,'rewind-history')
    assert json.loads(bytes(manifests[-1]['data']))['pending']['kind'] == 'restore'
    assert len([call for call in session.calls if call[0]=='load']) == 1


def test_contended_history_lock_obeys_deadline_without_effect(session):
    acquired, release = threading.Event(), threading.Event()
    def holder():
        with session.vm.lock:
            acquired.set(); release.wait(2)
    worker = threading.Thread(target=holder); worker.start(); assert acquired.wait(1)
    start = time.monotonic()
    try:
        with pytest.raises(TimeoutError): session.rewind_start(timeout_ms=30)
        assert time.monotonic()-start < .5 and session.calls == []
        assert not _artifact_rows(session.project,'rewind-history')
    finally:
        release.set(); worker.join()


def test_pending_hook_refuses_step_without_touching_checkpoint_or_guest(session):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    session._qemu_hook_pending = 'hook-A'
    before = list(session.calls)
    with pytest.raises(ValueError,match='pending hook'):
        session.rewind_record()
    assert session.calls == before and session.rewind_status()['cursor'] == start['cursor']


def test_unsupported_checkpoint_mode_refuses_without_artifacts_or_guest(session):
    session.vm.qmp_commands.clear()
    with pytest.raises(ValueError,match='checkpoint'):
        session.rewind_start()
    assert not _artifact_rows(session.project,'state')
    assert not _artifact_rows(session.project,'rewind-history')
    assert session.calls == [] and not session.closed


def test_stale_manifest_or_source_identity_refused_before_restore(session):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    old_source = session.metadata['source_sha256']
    session.metadata['source_sha256'] = '0'*64
    with pytest.raises(ValueError,match='identity|source'):
        session.rewind(history=start['history'],node=start['cursor'])
    session.metadata['source_sha256'] = old_source
    assert not any(call[0]=='load' for call in session.calls) and not session.closed


def test_restore_manifest_hash_tamper_refused_before_target_io(session):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    with session.project.transaction(True):
        session.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',
                                   (b'{"wrong":true}',start['history']))
    with pytest.raises(ValueError,match='hash|corrupt'):
        session.rewind(history=start['history'],node=start['cursor'])
    assert not any(call[0]=='load' for call in session.calls) and not session.closed


def test_lost_capture_completion_preserves_pending_and_forbids_retry(session,monkeypatch):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    publish = session._history_publish
    def fail_completion(manifest, *, reason):
        if manifest.get('pending') is None:
            raise OSError('authored completion journal failure')
        return publish(manifest,reason=reason)
    monkeypatch.setattr(session,'_history_publish',fail_completion)
    with pytest.raises(OSError): session.rewind_record(advance='capture')
    assert session.closed
    manifests = _artifact_rows(session.project,'rewind-history')
    assert json.loads(bytes(manifests[-1]['data']))['pending']['kind'] == 'capture'
    assert len([call for call in session.calls if call[0]=='save']) == 2
    assert start['cursor'] is not None


def test_nonordinary_stop_is_recorded_without_instruction_completion_claim(session):
    session.rewind_start(max_steps=4,max_bytes=65536)
    session.step = lambda **kwargs: {'outcome':'breakpoint','timed_out':False,
        'session':{'state':'stopped','stop_reason':{'kind':'breakpoint','breakpoint_ids':['b']}}}
    result = session.rewind_record()
    edge = result['nodes'][-1]['edge']
    assert edge['kind'] == 'stopped' and edge['outcome'] == 'breakpoint'
    assert edge.get('completed_instruction') is not True
    assert result['recorded_count'] == 1


def test_history_survives_project_close_and_reopen(tmp_path,monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._compatibility',lambda session: {'runtime':'authored'})
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight',lambda session: None)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._serial_idle',lambda session: None)
    source = tmp_path / 'restart.com'; source.write_bytes(bytes.fromhex('90ebfd'))
    db = tmp_path / 'restart.fdb'
    with Project.create(db,source,image='com') as project:
        first = Harness(project,'before-reopen')
        root = first.rewind_start(max_steps=4,max_bytes=65536)
        later = first.rewind_record()
        saved_history, root_node = later['history'],root['cursor']
    with Project(db) as reopened:
        second = Harness(reopened,'after-reopen')
        attached = second.rewind_start(history=saved_history)
        assert attached['retained_nodes'] == 2 and not attached['valid']
        restored = second.rewind(history=saved_history,node=root_node)
        assert restored['cursor'] == root_node and second.pc == 0


def test_insufficient_known_checkpoint_space_refused_before_step(session):
    start = session.rewind_start(max_steps=4,max_bytes=len(json.dumps({'pc':0}).encode())+1)
    assert start['state_bytes_used'] > 1
    before = list(session.calls)
    with pytest.raises(ValueError):
        session.rewind_record()
    assert session.calls == before and not session.closed
    assert session.rewind_status()['cursor'] == start['cursor']


def test_restoring_using_old_revision_keeps_all_future_nodes_and_charges(session):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    later = session.rewind_record(count=2)
    future = set(later['node_ids'])
    restored = session.rewind(history=start['history'],node=start['cursor'])
    assert set(restored['node_ids']) == future
    assert restored['captures_used'] == 3 and restored['state_bytes_used'] == later['state_bytes_used']
    branch = session.rewind_record()
    assert set(branch['node_ids']) >= future and branch['captures_used'] == 4
    before = list(session.calls)
    with pytest.raises(ValueError,match='budget'):
        session.rewind_record()
    assert session.calls == before


def test_cold_restore_clears_new_owner_inherited_deadline(session):
    root = session.rewind_start(max_steps=4,max_bytes=65536)
    session.rewind_record()
    restored = session.rewind(node=root['cursor'],timeout_ms=1000)
    assert restored['restore']['source_binding_restored']
    assert session.vm.operation_deadline is None
    assert getattr(session,'_deadline',None) is None
    assert getattr(session,'_rpc_deadline',None) is None


@pytest.mark.parametrize('operation', ['dos_task_preemption','dos_task_switching'])
def test_task_scheduler_mutations_invalidate_history_cursor(session,operation):
    session.rewind_start(max_steps=4,max_bytes=65536)
    session.vm.history_operation_guard(operation,(),{})
    assert not session.rewind_status()['valid']
    before = list(session.calls)
    with pytest.raises(ValueError): session.rewind_record()
    assert session.calls == before


def test_late_step_completion_closes_owner_and_returns_evidence(session):
    session.rewind_start(max_steps=4,max_bytes=65536)
    ordinary_step = session.step
    def slow_step(**kwargs):
        result = ordinary_step(**kwargs)
        time.sleep(.04)
        return result
    session.step = slow_step
    with pytest.raises(TimeoutError) as caught:
        session.rewind_record(timeout_ms=25)
    assert session.closed and getattr(caught.value,'result',None) is not None
    assert len([call for call in session.calls if call[0]=='step']) == 1


def test_pending_uncertain_step_cannot_be_replayed_after_project_reopen(tmp_path,monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._compatibility',lambda session: {'runtime':'authored'})
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight',lambda session: None)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._serial_idle',lambda session: None)
    source = tmp_path / 'pending.com'; source.write_bytes(bytes.fromhex('90ebfd'))
    db = tmp_path / 'pending.fdb'
    with Project.create(db,source,image='com') as project:
        first = Harness(project,'pending-original')
        root = first.rewind_start(max_steps=4,max_bytes=65536)
        first.fault = 'step'
        with pytest.raises(TimeoutError): first.rewind_record()
        history, node = root['history'], root['cursor']
    with Project(db) as reopened:
        second = Harness(reopened,'pending-reopened')
        attached = second.rewind_start(history=history)
        assert attached['pending']['kind'] == 'step'
        with pytest.raises(ValueError,match='unresolved|pending'):
            second.rewind(history=history,node=node)
        assert second.calls == [] and not second.closed


def test_uncheckpointable_guest_exit_retains_stop_without_fake_child(session):
    start = session.rewind_start(max_steps=4,max_bytes=65536)
    def stop(**kwargs):
        session.calls.append(('step-exit',session.pc))
        session._process['state'] = 'guest_exit'
        return {'outcome':'guest_exit','process':{'state':'guest_exit'},
                'session':{'state':'stopped','stop_reason':{'kind':'guest_exit','breakpoint_ids':[]}}}
    session.step = stop
    result = session.rewind_record()
    assert result['recorded_count'] == 0 and len(_artifact_rows(session.project,'state')) == 1
    latest = _artifact_rows(session.project,'rewind-history')[-1]
    manifest = json.loads(bytes(latest['data']))
    assert manifest['pending'] is None and manifest['live_cursor_valid'] is False
    assert manifest['last_stop']['outcome'] == 'guest_exit'
    assert result['stop']['outcome'] == 'guest_exit' and start['cursor'] is not None


def test_nonordinary_stop_with_lost_checkpoint_receipt_remains_uncertain(session):
    session.rewind_start(max_steps=4,max_bytes=65536)
    session.step = lambda **kwargs: {'outcome':'breakpoint','timed_out':False,
        'session':{'state':'stopped','stop_reason':{'kind':'breakpoint','breakpoint_ids':['b']}}}
    save = session.save_state
    def lost_receipt(*args,**kwargs):
        save(*args,**kwargs)
        raise ValueError('authored lost receipt after saved artifact')
    session.save_state = lost_receipt
    with pytest.raises(ValueError,match='lost receipt'):
        session.rewind_record()
    assert session.closed
    assert len(_artifact_rows(session.project,'state')) == 2
    latest = json.loads(bytes(_artifact_rows(session.project,'rewind-history')[-1]['data']))
    assert latest['pending']['kind'] == 'stopped-checkpoint'
    assert latest['pending']['receipt']['outcome'] == 'breakpoint'


def test_partial_batch_reports_committed_prefix_when_later_step_exits(session):
    session.rewind_start(max_steps=5,max_bytes=65536)
    step = session.step
    def step_then_exit(**kwargs):
        if session.pc == 0:
            return step(**kwargs)
        session._process['state'] = 'guest_exit'
        return {'outcome':'guest_exit','process':{'state':'guest_exit'},
                'session':{'state':'stopped','stop_reason':{'kind':'guest_exit','breakpoint_ids':[]}}}
    session.step = step_then_exit
    result = session.rewind_record(count=2)
    assert result['recorded_count'] == 1 and len(result['records']) == 1
    assert result['retained_nodes'] == 2 and result['stop']['outcome'] == 'guest_exit'


def test_status_does_not_advertise_stale_epoch_or_closed_owner(session):
    session._runtime_epoch = 'epoch-1'
    session.rewind_start(max_steps=4,max_bytes=65536)
    session._runtime_epoch = 'epoch-2'
    assert session.rewind_status()['valid'] is False
    session._runtime_epoch = 'epoch-1'
    session.closed = True
    status = session.rewind_status()
    assert status['active'] is False and status['valid'] is False


@pytest.mark.parametrize('terminal',[False,True])
def test_post_step_stop_receipt_journal_failure_closes_and_retains_pending(session,monkeypatch,terminal):
    session.rewind_start(max_steps=4,max_bytes=65536)
    def stop(**kwargs):
        outcome = 'guest_exit' if terminal else 'breakpoint'
        return {'outcome':outcome,'timed_out':False,'session':{'state':'stopped',
            'stop_reason':{'kind':outcome,'breakpoint_ids':[]}}}
    session.step = stop
    publish = session._history_publish
    def fail_stop(manifest,*,reason):
        pending = manifest.get('pending') or {}
        if pending.get('kind') == 'stopped-checkpoint' or (terminal and manifest.get('last_stop')):
            raise OSError('stop receipt journal failure')
        return publish(manifest,reason=reason)
    monkeypatch.setattr(session,'_history_publish',fail_stop)
    with pytest.raises(OSError,match='stop receipt journal failure'):
        session.rewind_record()
    assert session.closed
    latest = json.loads(bytes(_artifact_rows(session.project,'rewind-history')[-1]['data']))
    assert latest['pending']['kind'] == 'step'


def test_owner_swap_with_nulled_old_channels_restores_deadline_guards(session):
    root = session.rewind_start(max_steps=4,max_bytes=65536)
    session.rewind_record()
    old = session.vm
    qmp = SimpleNamespace(operation_deadline=None)
    gdb = SimpleNamespace(operation_deadline=None)
    old.qmp, old.gdb = qmp,gdb
    def swap(artifact,*,timeout_ms):
        row = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        session.pc = json.loads(bytes(row['data']))['pc']
        old.qmp = old.gdb = None
        session.vm = SimpleNamespace(**vars(old))
        session.vm.qmp = SimpleNamespace(operation_deadline=session._deadline)
        session.vm.gdb = SimpleNamespace(operation_deadline=session._deadline)
        session.vm.history_operation_guard = None
        session._history_bind()
        return {'source_binding_restored':True}
    session.load_state = swap
    restored = session.rewind(node=root['cursor'])
    assert restored['restore']['source_binding_restored']
    assert qmp.operation_deadline is None and gdb.operation_deadline is None
    assert session.vm.operation_deadline is None
    assert session.vm.qmp.operation_deadline is None and session.vm.gdb.operation_deadline is None


def test_cross_session_identity_accepts_nonce_only_helper_change_but_not_program_change(project,session):
    from fdisbull.dos_process_helper import build_loader
    session._nonce = b'A'*16
    session._helper = build_loader('C:\\TARGET.COM',b'',session._nonce)
    root = session.rewind_start(max_steps=4,max_bytes=65536)
    second = Harness(project,'different-nonce')
    second._nonce = b'B'*16
    second._helper = build_loader('C:\\TARGET.COM',b'',second._nonce)
    attached = second.rewind_start(history=root['history'])
    assert attached['history_id'] == root['history_id'] and not attached['valid']
    second._helper = build_loader('C:\\OTHER.COM',b'',second._nonce)
    with pytest.raises(ValueError,match='identity|target|helper'):
        second.rewind_start(history=root['history'])


@pytest.mark.parametrize('route',['start','step','capture','restore'])
@pytest.mark.parametrize('conflict',['pending','lease'])
def test_real_checkpoint_input_preflight_preserves_owner_and_history(session,monkeypatch,route,conflict):
    root = None if route == 'start' else session.rewind_start(max_steps=4,max_bytes=65536)
    state = {'valid':True,'pending':[],'leases':{}}
    if conflict == 'pending': state['pending'] = [{'edge':'authored'}]
    else: state['leases'] = {'held-key':{'make':'native_dispatched'}}
    session.vm._physical_input = state
    owner = session.vm
    before = list(session.calls)
    artifacts = len(_artifact_rows(session.project,'state'))
    manifests = len(_artifact_rows(session.project,'rewind-history'))
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight',real_checkpoint_preflight)
    with pytest.raises(ValueError,match='released machine input|empty physical queue'):
        if route == 'start': session.rewind_start(max_steps=4,max_bytes=65536)
        elif route == 'step': session.rewind_record()
        elif route == 'capture': session.rewind_record(advance='capture')
        else: session.rewind(node=root['cursor'])
    assert not session.closed and session.calls == before and session.vm is owner
    assert len(_artifact_rows(session.project,'state')) == artifacts
    assert len(_artifact_rows(session.project,'rewind-history')) == manifests
    assert session.vm._physical_input == state
    if root:
        status = session.rewind_status()
        assert status['pending'] is None and status['cursor'] == root['cursor']


@pytest.mark.parametrize('conflict',['schedule','sync'])
def test_real_controller_preflight_refuses_before_history_or_guest_mutation(session,monkeypatch,conflict):
    root = session.rewind_start(max_steps=4,max_bytes=65536)
    if conflict == 'schedule':
        session.vm._physical_input = {'valid':True,'pending':[],'leases':{},'schedule':{'bound':True}}
    else:
        session.vm._clock_sync = {'state':'active'}
    before = list(session.calls)
    manifests = len(_artifact_rows(session.project,'rewind-history'))
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._preflight',real_checkpoint_preflight)
    with pytest.raises(ValueError,match='schedule|synchronization'):
        session.rewind_record(advance='capture')
    assert not session.closed and session.calls == before
    assert len(_artifact_rows(session.project,'rewind-history')) == manifests
    assert session.rewind_status()['cursor'] == root['cursor']


def test_capture_count_greater_than_one_refused_without_effect(session):
    root = session.rewind_start(max_steps=5,max_bytes=65536)
    before = list(session.calls)
    count = len(_artifact_rows(session.project,'rewind-history'))
    with pytest.raises(ValueError,match='one|count'):
        session.rewind_record(count=2,advance='capture')
    assert session.calls == before and not session.closed
    assert len(_artifact_rows(session.project,'rewind-history')) == count
    assert session.rewind_status()['cursor'] == root['cursor']
