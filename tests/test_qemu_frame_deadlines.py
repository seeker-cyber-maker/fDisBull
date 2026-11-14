"""A late mutating frame response must not leave a retryable live guest."""
import threading
from types import SimpleNamespace

import pytest

from fdisbull.qemu_dos_history import _history_operation


@pytest.mark.parametrize('operation',['save_experiment','restore_experiment','compare_experiment'])
def test_experiment_invalidates_live_frame_edge_inside_outer_history_lock(operation):
    from types import SimpleNamespace
    from fdisbull.qemu_dos_history import QemuDOSHistoryMixin
    live=dict(valid=True,cursor='retained-point')
    session=SimpleNamespace(_history_busy=True,_qemu_history_live=live)
    QemuDOSHistoryMixin._history_before_operation(session,operation)
    assert live['valid'] is False and live['cursor'] is None
    assert live['invalid_reason']=='unrecorded operation: '+operation


@pytest.mark.parametrize('operation',[
    'timeline_start','timeline_advance','timeline_rewind','advance_frames','frame_inputs',
    'cpu_delta_start','cpu_delta_record','cpu_delta_rewind','cpu_delta_recover',
    'save_experiment','restore_experiment','compare_experiment'])
def test_late_frame_completion_closes_owner_and_retains_the_actual_receipt(monkeypatch,operation):
    now = [100.0]
    monkeypatch.setattr('fdisbull.qemu_dos_history.time.monotonic',lambda:now[0])
    owner = SimpleNamespace(vm=SimpleNamespace(lock=threading.RLock(),qmp=None,gdb=None,
        operation_deadline=None),closed=False,dispatches=0)
    owner.close = lambda:setattr(owner,'closed',True)
    receipt = {'completed_frames':1,'point':'durably-recorded-frame'}
    def complete(self,timeout_ms=1000):
        self.dispatches += 1
        now[0] += 2
        return receipt
    complete.__name__ = operation
    invoke = _history_operation(complete)
    with pytest.raises(TimeoutError,match='outer deadline') as caught:
        invoke(owner,timeout_ms=1000)
    assert owner.closed and owner.dispatches == 1
    assert caught.value.result == receipt
    assert owner.vm.operation_deadline is None
    assert owner._deadline is owner._rpc_deadline is None
