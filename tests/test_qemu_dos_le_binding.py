"""Public source handles and lifecycle fences with real FDB/artifact storage."""
from copy import deepcopy
import json

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import _tracking, _machine_operation_guard
from test_qemu_dos_source_admission import owned
from test_qemu_dos_le_trace import active_le


def test_bind_installs_recipe_without_replacing_mz_and_cold_export(owned, tmp_path):
    s, p = owned.session, owned.project
    before = deepcopy(s._process)
    bound = s.dos_source_bind(expected_source_sha256=p.meta['source_sha256'])
    assert bound['live'] and bound['state']=='qualified-stopped'
    assert bound['continuity'].endswith('not OS/task/allocation lifetime')
    assert s._process==before and s._le_source_bound()
    s.dos_source_binding(refresh=True)
    state = s._le_source
    assert state['recipe']['source_view']=='embedded-le'
    assert state['material']['gdt_hex']==owned.peer.table.hex()
    data = tmp_path/'binding.json'
    p.debug_export(bound['artifact']['artifact'],data)
    document = json.loads(data.read_bytes())
    assert document['recipe']==state['recipe']
    assert document['admission']['artifact']!=bound['artifact']['artifact']
    source = document['recipe']['initial_admission']
    assert source['lifetime_qualified'] is False and source['live_mapping_installed'] is False
    event, _ = s._le_source_refresh()
    assert event['source_qualification']['qualified']
    assert event['project_address'] is None and event['task_id'] is None
    assert event['identity']['source_location']['object_id']=='le:1'
    assert event['mapping_id']==bound['binding_id']
    assert 'gdt_hex' not in event['le_source_witness']
    assert event['le_source_witness']['gdt_sha256']==source['gdt']['sha256']
    assert event['observation']['instruction_completed'] is False
    database = p.path
    expected = data.read_bytes()
    p.__exit__()
    from fdisbull.project import Project
    with Project(database) as cold:
        cold.debug_export(bound['artifact']['artifact'],tmp_path/'cold.json')
        assert (tmp_path/'cold.json').read_bytes()==expected


def test_source_handle_revalidates_owned_stop_without_claiming_running_authority(owned):
    s = owned.session
    bound = s.dos_source_bind()
    _tracking(s,'before_execution','machine-gdb-step')
    assert s.dos_source_binding()['state']=='pending-owned-execution'
    assert not s.dos_source_binding()['live']
    _tracking(s,'after_stop','machine-step')
    after = s.dos_source_binding()
    assert after['live'] and after['binding_id']==bound['binding_id']
    assert after['generation']==bound['generation']
    _tracking(s,'before_execution','machine-gdb-run')
    assert not s.dos_source_binding()['live']
    _tracking(s,'after_stop','machine-breakpoint')
    after = s.dos_source_binding()
    assert after['live'] and after['generation']>bound['generation']
    assert after['execution_coverage']=='stopped-endpoints'


@pytest.mark.parametrize('reason',['machine-resume','machine-write-memory','machine-write-registers','machine-layer-write'])
def test_mutations_and_unobserved_resume_retire_before_guest_control(owned,reason):
    s = owned.session;s.dos_source_bind()
    _tracking(s,'before_execution',reason)
    assert s.dos_source_binding()['state']=='retired'
    with pytest.raises(ValueError,match='dos_source_bind'):s._le_source_trace_binding()


@pytest.mark.parametrize('operation',['load_state','rewind','timeline_rewind','restore_experiment','cpu_delta_rewind'])
def test_recovery_guards_retire_even_inside_internal_history_scope(owned,operation):
    s = owned.session;s.dos_source_bind();s.vm.context=s
    s._history_busy=True
    _machine_operation_guard(s.vm,operation)
    assert s.dos_source_binding()['state']=='retired'


def test_source_drift_refuses_before_dispatch_and_retains_evidence(owned):
    s = owned.session;s.dos_source_bind();count=owned.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    s.metadata['version_sha256']='a'*64
    with pytest.raises(ValueError,match='identity differs'):
        _tracking(s,'before_execution','machine-gdb-step')
    assert s.dos_source_binding()['state']=='retired'
    assert owned.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==count
    assert not owned.closed


def test_mode_or_gdt_boundary_withdraws_current_source_without_ending_process(owned):
    s = owned.session;s.dos_source_bind();old=deepcopy(s._process)
    owned.peer.mode='real'
    _tracking(s,'after_stop','machine-step')
    assert s.dos_source_binding()['state']=='out-of-scope'
    assert not s.dos_source_binding()['live'] and s._process==old
    event, _ = s._le_source_refresh()
    assert not event['source_qualification']['qualified']
    assert event['identity']['source_location'] is None


def test_binding_public_workspace_and_frozen_undo_remain_observational(owned):
    s,p=owned.session,owned.project
    s._qemu_cpu_delta_history={'frozen':True,'valid':False}
    from fdisbull.qemu_cpu_undo_guard import before_operation
    for name in ('dos_source_bind','dos_source_binding','dos_source_unbind','_le_source_refresh'):
        before_operation(s,name)
    bound=s.dos_source_bind()
    workspace=DebugWorkspace();workspace.sessions[s.run_id]=s
    reply=respond({'id':1,'method':'debug-dos-source-binding','params':{'project':str(p.path),'run':s.run_id}},debugger=workspace)
    assert reply['result']['binding_id']==bound['binding_id']
    s.dos_source_unbind()
    assert not s._le_source_bound() and s.dos_source_binding()['state']=='unbound'
    assert s._qemu_cpu_delta_history['frozen']


def test_binding_publication_failure_leaves_no_active_handle(owned):
    s,p=owned.session,owned.project
    original=s._event
    def fail(operation,value):
        if operation=='dos-source-bind':raise OSError('authored binding journal failure')
        return original(operation,value)
    s._event=fail
    with pytest.raises(OSError,match='binding journal'):s.dos_source_bind()
    assert not s._le_source_bound()
    assert p.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='dos-source-binding'").fetchone()[0]==0
    assert p.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='dos-source-admission'").fetchone()[0]==1


def test_failed_refresh_withdraws_old_authority_before_any_read(owned):
    s=owned.session;s.dos_source_bind()
    def broken(*args):raise OSError('authored source read failure')
    owned.peer.on_memory=broken
    with pytest.raises(OSError,match='source read'):s.dos_source_binding(refresh=True)
    assert not s.dos_source_binding()['live']
    assert 'OSError' in s.dos_source_binding()['reason']
    owned.peer.on_memory=None
    assert s.dos_source_binding(refresh=True)['live']


def test_owner_replaced_during_final_read_cannot_publish_live_relation(owned):
    from types import SimpleNamespace
    s=owned.session;s.dos_source_bind()
    before=owned.peer.register_reads
    def replace(peer):
        if peer.register_reads>=before+2:
            s.vm.process=SimpleNamespace(poll=lambda:0)
    owned.peer.on_registers=replace
    with pytest.raises(ValueError,match='changed during observation'):s.dos_source_binding(refresh=True)
    assert s.dos_source_binding()['state']=='retired'
    assert not s.dos_source_binding()['live']


def test_actual_read_timeout_after_arrived_step_keeps_stop_and_quarantines(active_le):
    o,s=active_le,active_le.session
    def after(_):
        def timeout(*args):raise TimeoutError('authored native read timeout')
        o.peer.on_memory=timeout
    o.after_step=after
    with pytest.raises(TimeoutError,match='native read timeout') as error:s.step(timeout_ms=1000)
    assert error.value.result['session']['stop_reason']['native_reply']=='T05'
    assert len(o.intervals)==1 and o.closed
    assert s.vm._fdisbull_control_quarantine=='failed native stop publication'
    assert not s.dos_source_binding()['live']


def test_replaced_process_refuses_bound_step_before_native_dispatch(active_le):
    from types import SimpleNamespace
    o,s=active_le,active_le.session
    s.vm.process=SimpleNamespace(poll=lambda:None)
    with pytest.raises(ValueError,match='identity changed before execution'):
        s.step()
    assert not o.intervals and o.closed
    assert s.dos_source_binding()['state']=='retired'


@pytest.mark.parametrize('command',['s','c'])
@pytest.mark.parametrize('late',[False,True])
def test_source_refresh_shares_execution_budget_and_defers_without_fresh_io(active_le,monkeypatch,command,late):
    from fdisbull import qemu_machine, qemu_dos_process, qemu_dos_le_binding, operation_budget
    class Clock:
        now=1000.0
        def monotonic(self):return self.now
    clock=Clock()
    for module in (qemu_machine,qemu_dos_process,qemu_dos_le_binding,operation_budget):
        monkeypatch.setattr(module,'time',clock)
    o,s=active_le,active_le.session
    source_reads=[]
    original=o.peer.memory
    def memory(address,length,**options):
        source_reads.append(options['timeout_ms'])
        return original(address,length,**options)
    o.peer.memory=memory
    def execute(actual,timeout_ms,**kw):
        assert actual==command and 0<timeout_ms<=200
        o.intervals.append((actual,timeout_ms));clock.now+=.25 if late else .05
        o.peer.cpu['ip']+=2
        return b'T05',late
    o.peer.execute=execute
    result = qemu_machine.MachineContext.run(s,timeout_ms=200) if command=='c' else s.step(timeout_ms=200)
    assert len(o.intervals)==1 and not o.closed
    assert s.vm.operation_deadline is None and o.peer.operation_deadline is None
    assert getattr(s,'_le_source_execution_deadline',None) is None
    if late:
        assert result['timed_out'] and not source_reads
        assert not s.dos_source_binding()['live']
        assert 'budget expired' in s.dos_source_binding()['reason']
        assert s.dos_source_binding(refresh=True)['live']
    else:
        assert source_reads and max(source_reads)<=150
        assert s.dos_source_binding()['live']


def test_source_admission_expires_after_arrived_step_without_losing_native_stop(active_le,monkeypatch):
    from fdisbull import qemu_machine, qemu_dos_process, qemu_dos_le_binding, operation_budget

    class Clock:
        now=1000.0
        def monotonic(self):return self.now

    clock=Clock()
    for module in (qemu_machine,qemu_dos_process,operation_budget):
        monkeypatch.setattr(module,'time',clock)

    class AdmissionClock:
        def monotonic(self):
            sampled=clock.now
            # The stop arrived within its allowance, but wrapper admission
            # happens after the final positive millisecond sample expires.
            clock.now=1000.202
            return sampled

    monkeypatch.setattr(qemu_dos_le_binding,'time',AdmissionClock())
    o,s=active_le,active_le.session
    before_reads=len(o.peer.reads)

    def execute(command,timeout_ms,**options):
        assert command=='s' and 0<timeout_ms<=200
        o.intervals.append((command,timeout_ms))
        o.peer.cpu['ip']+=2
        clock.now=1000.1985
        return b'T05',False

    o.peer.execute=execute
    result=s.step(timeout_ms=200)
    assert result['outcome']=='step' and result['timed_out'] is False
    assert result['session']['stop_reason']['native_reply']=='T05'
    assert len(o.intervals)==1 and len(o.peer.reads)==before_reads
    assert not o.closed and not getattr(s.vm,'_fdisbull_control_quarantine',None)
    assert s._deadline is s.vm.operation_deadline is o.peer.operation_deadline is None
    assert s.vm.qmp.operation_deadline is None
    assert getattr(s,'_le_source_execution_deadline',None) is None
    state=s.dos_source_binding()
    assert not state['live'] and 'before source observation I/O' in state['reason']
    assert s.dos_source_binding(refresh=True)['live']
