"""Host-only outer-run and hook stop ownership contracts."""
from types import SimpleNamespace
import sys
import threading
import time
import pytest
from fdisbull.qemu_machine import machine_run_operation
from fdisbull.debug_script import _suppress_automatic_keeps
from test_qemu_hooks import Harness as HookHarness, _stop


class RunHarness:
    def __init__(self):
        self.vm=SimpleNamespace(lock=threading.RLock(),qmp=SimpleNamespace(operation_deadline=None),
            gdb=SimpleNamespace(operation_deadline=None),operation_deadline=None,closed=False)
        self.vm.close=lambda:setattr(self.vm,'closed',True)
        self._qemu_hooks={};self.enabled=True;self.executions=[]
    def _input_schedule_bound(self):return False
    @machine_run_operation
    def run(self,*,timeout_ms=10000,stop_on_hook=False):
        self.executions.append(('execute',self.vm.operation_deadline))
        return {'outcome':'save_boundary'}


def controller(monkeypatch, *, exit_error=False):
    class Scope:
        def __init__(self,session):self.session=session
        def __enter__(self):self.session.executions.append(('enter',self.session.vm.operation_deadline));return self
        def finish(self,result):
            self.session.executions.append(('finish',self.session.vm.operation_deadline))
            return dict(result,save_keep={'kept':True})
        def __exit__(self,*args):
            self.session.executions.append(('exit',self.session.vm.operation_deadline))
            if exit_error:raise OSError('scope cleanup failed')
    def suppress(fn):
        def invoke(session,*args,**kwargs):
            session.depth+=1
            try:return fn(session,*args,**kwargs)
            finally:session.depth-=1
        return invoke
    fake=SimpleNamespace(safe_stop_enabled=lambda s:s.enabled,SaveRunScope=Scope,no_automatic_keeps=suppress)
    monkeypatch.setitem(sys.modules,'fdisbull.qemu_save_stop',fake)


def test_safe_run_installs_deadline_around_execution_finish_and_cleanup(monkeypatch):
    controller(monkeypatch);s=RunHarness();result=s.run(timeout_ms=1000)
    assert result['save_keep']=={'kept':True}
    assert [x[0] for x in s.executions]==['enter','execute','finish','exit']
    assert all(isinstance(x[1],float) for x in s.executions)
    assert s.vm.operation_deadline is None and s.vm.qmp.operation_deadline is None


def test_disabled_fast_path_remains_unchanged(monkeypatch):
    controller(monkeypatch);s=RunHarness();s.enabled=False
    assert s.run()['outcome']=='save_boundary'
    assert s.executions==[('execute',None)]


def test_scope_cleanup_failure_preserves_known_result(monkeypatch):
    controller(monkeypatch,exit_error=True);s=RunHarness()
    with pytest.raises(OSError,match='cleanup') as error:s.run()
    assert error.value.result['save_keep']=={'kept':True}
    assert s.vm.operation_deadline is None


def test_script_suppression_covers_success_and_failure(monkeypatch):
    controller(monkeypatch);s=SimpleNamespace(depth=0)
    @_suppress_automatic_keeps
    def run(session,fail=False):
        assert session.depth==1
        if fail:raise ValueError('script failure')
        return 'ok'
    assert run(s)=='ok' and s.depth==0
    with pytest.raises(ValueError):run(s,True)
    assert s.depth==0


def test_hook_collision_dispatches_once_and_does_not_continue():
    s=HookHarness();hook=s.hook(0x1000,actions=[{'op':'layers','layers':[]}],once=False,max_hits=2)
    collision=dict(_stop('breakpoint',hook['breakpoint_id']),save_boundary_conflict=True)
    s.queue=[collision]
    result=s._run_with_hooks(timeout_ms=1000,stop_on_hook=False)
    assert result['outcome']=='hook' and result['save_boundary_conflict']
    assert result['hook_hits'][0]['hit']==1 and s._qemu_hook_pending==hook['hook']
    assert [x for x in s.calls if x[0]=='execute']==[('execute','c')]


def test_step_over_collision_preserved_even_if_step_outcome():
    s=HookHarness();hook=s.hook(0x1000,actions=[{'op':'layers','layers':[]}],once=False,max_hits=2)
    s.queue=[_stop('breakpoint',hook['breakpoint_id'])]
    s._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    s.queue=[dict(_stop('step'),save_boundary_conflict=True)]
    result=s._run_with_hooks(timeout_ms=1000,stop_on_hook=False)
    assert result['outcome']=='step' and result['save_boundary_conflict']
    assert s._qemu_hook_pending==hook['hook']
    assert s.calls[-1]==('execute','s')
