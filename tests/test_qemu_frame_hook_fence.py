"""A frame publication cannot be lost during a pending hook's step-over."""
import time
from types import SimpleNamespace

import pytest

from fdisbull.qemu_hooks import QemuHookSessionMixin


class PendingHook(QemuHookSessionMixin):
    def __init__(self, completed):
        self.completed = completed
        self.vm = SimpleNamespace(operation_deadline=time.monotonic()+10)
        self._qemu_hook_pending = 'hook'
        self._qemu_hook_pending_task = None
        self._qemu_hooks = {'hook':dict(hook='hook',breakpoint_id='old',access='x',
            runtime_address=0x1000,length=1)}
        self.pc, self.calls, self.closed = 0x1000, [], False

    def registers(self): return dict(linear_pc=hex(self.pc))
    def _delete_hook_breakpoint(self, point): pass
    def breakpoint(self, address, **kwargs): return dict(breakpoint_id='replacement')
    def _hook_reindex(self, controls): self._qemu_hooks = {x['hook']:x for x in controls}
    def _dispatch_qemu_hook(self, result): return None
    def close(self): self.closed = True

    def _execute(self, command, timeout_ms):
        self.calls.append(command)
        self.pc += 1
        return dict(outcome='step' if command=='s' else 'stopped',timed_out=False,
            session=dict(state='stopped',stop_reason=dict(kind='step' if command=='s' else 'stopped',
                native_reply='T05' if command=='s' else 'T02',breakpoint_ids=[])))

    def _frame_stop_after_step(self):
        if isinstance(self.completed,Exception): raise self.completed
        return self.completed


@pytest.mark.parametrize('completed',[False,True])
def test_pending_hook_preserves_a_coincident_frame_stop_without_another_continue(completed):
    debug = PendingHook(completed)
    result = debug._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert debug.calls == (['s'] if completed else ['s','c'])
    assert result['outcome'] == ('step' if completed else 'stopped')
    assert debug._qemu_hook_pending == ('hook' if completed else None)
    assert debug._qemu_hooks['hook']['breakpoint_id'] == 'replacement'
    assert not debug.closed


def test_uncertain_frame_fence_during_step_over_closes_without_continuation():
    debug = PendingHook(TimeoutError('lost fence query'))
    with pytest.raises(TimeoutError,match='lost fence query'):
        debug._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert debug.calls == ['s'] and debug.closed
