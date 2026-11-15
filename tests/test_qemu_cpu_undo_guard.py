"""Frozen native projection state permits inspection and certified recovery."""
from types import SimpleNamespace
import pytest

from fdisbull.qemu_cpu_undo_guard import before_operation, full_load


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
