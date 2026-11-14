"""Host-only hook-aware timer ownership and interrupted step-over checks."""
import pytest

from fdisbull.qemu_clock import clock_timer_stop_is_ordinary
from test_qemu_clock_budget import owned
from test_qemu_hooks import Harness, _stop


@pytest.mark.parametrize('fired', [False, True])
def test_hook_aware_timer_arms_once_and_retains_hook_when_timer_coincides(owned, fired):
    o = owned
    calls = []
    def dispatch(*,timeout_ms,stop_on_hook):
        calls.append((timeout_ms,stop_on_hook,o.vm._active_clock_budget['budget-token']))
        end = o.wire.receipt['budget-deadline-ns'] if fired else o.wire.receipt['budget-start-ns']+2
        o.wire.receipt.update({'budget-state':'stopped','budget-stopped-ns':end,'virtual-ns':end})
        if fired: o.wire.receipt['budget-fired-ns'] = end
        return {'outcome':'hook','timed_out':False,'hook_hits':[{'hook':'owned','hit':1}],
                'session':{'state':'stopped','stop_reason':{'kind':'breakpoint',
                           'breakpoint_ids':['bp'],'native_reply':'T05'}}}
    o.context._run_with_hooks = dispatch
    result = o.context._clock_advance_with_hooks(1000,timeout_ms=250)
    assert len(calls) == 1 and calls[0][1] is True
    assert result['outcome'] == 'hook' and result['hook_hits'][0]['hit'] == 1
    assert result['clock_budget']['deadline_reached'] is fired
    assert not clock_timer_stop_is_ordinary(result)
    assert [name for name,_ in o.wire.calls].count('x-fdisbull-arm-clock-budget') == 1
    assert [name for name,_ in o.wire.calls].count('x-fdisbull-cancel-clock-budget') == 1
    assert not o.vm.closed and o.vm._active_clock_budget is None


def test_interrupted_step_over_retains_pending_without_duplicate_action():
    session = Harness()
    hook = session.hook(0x1000, actions=[{'op':'layers','layers':[]}],once=False,max_hits=3)
    session.queue = [_stop('breakpoint',hook['breakpoint_id'])]
    assert session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)['outcome'] == 'hook'
    assert len([x for x in session.calls if x[0]=='layers']) == 1
    session.queue = [_stop('stopped')]
    result = session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert result['outcome'] == 'stopped'
    assert session._qemu_hook_pending == hook['hook']
    assert len([x for x in session.calls if x[0]=='layers']) == 1
    session.queue = [_stop('step'), _stop('guest_exit')]
    result = session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert result['outcome'] == 'guest_exit'
    assert len([x for x in session.calls if x[0]=='layers']) == 1
    assert session._qemu_hook_pending is None


def test_interrupted_hook_step_during_continuing_run_preserves_pending():
    session = Harness()
    hook = session.hook(0x1000,actions=[{'op':'layers','layers':[]}],once=False,max_hits=3)
    session.queue = [_stop('breakpoint',hook['breakpoint_id']), _stop('stopped')]
    result = session._run_with_hooks(timeout_ms=1000,stop_on_hook=False)
    assert result['outcome'] == 'stopped' and len(result['hook_hits']) == 1
    assert session._qemu_hook_pending == hook['hook']
    assert len([x for x in session.calls if x[0]=='layers']) == 1


def test_timer_drives_real_hook_dispatch_and_preserves_hit(owned):
    from types import SimpleNamespace
    o = owned
    ctx = o.context
    from fdisbull.qemu_hooks import QemuHookSessionMixin
    from fdisbull.qemu_machine import MachineContext
    ctx.__class__ = type('HookClockContext', (QemuHookSessionMixin, MachineContext), {})
    ctx.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False),
                                  debug_layer_info=lambda _: {'version':1})
    ctx.version = {'id':1}; ctx.run_id = 'run'
    ctx._event = lambda *args, **kwargs: None
    ctx._layer_epoch = lambda: 1
    ctx._layer_spans = lambda address,length,space,cs=None: (address,address,[(address,length)],{'cpu_mode':'real'})
    ctx.capabilities = {'code_layers':True}
    points = {}
    def breakpoint(address, *, access='x',length=1):
        points['bp'] = address
        return {'breakpoint_id':'bp'}
    ctx.breakpoint = breakpoint
    ctx.delete_breakpoint = lambda key: points.pop(key)
    actions = []
    ctx.layers = lambda ids: actions.append(ids) or {'active':ids}
    control = ctx.hook(0x7c00,actions=[{'op':'layers','layers':[]}],once=False,max_hits=2)
    def execute(command, timeout_ms):
        assert command == 'c'
        end = o.wire.receipt['budget-deadline-ns']
        o.wire.receipt.update({'budget-state':'stopped','budget-stopped-ns':end,
                               'virtual-ns':end,'budget-fired-ns':end})
        return {'outcome':'breakpoint','timed_out':False,'session':{'state':'stopped',
                'stop_reason':{'kind':'breakpoint','breakpoint_ids':['bp'],'native_reply':'T05'}}}
    ctx._execute = execute
    result = ctx._clock_advance_with_hooks(1000,timeout_ms=250)
    assert result['outcome'] == 'hook' and result['clock_budget']['deadline_reached']
    assert result['hook_hits'][0]['hook'] == control['hook'] and actions == [[]]
    assert ctx._qemu_hook_pending == control['hook'] and points == {'bp':0x7c00}
    assert not clock_timer_stop_is_ordinary(result)


def test_interrupted_step_preserves_task_scope_for_shared_trap(monkeypatch):
    from test_qemu_hooks import _task_harness
    session,a,b,_ = _task_harness(monkeypatch)
    first = session.hook(0x1000,task=a['task_id'],actions=[{'op':'task-layers','layers':[]}],once=False,max_hits=3)
    session.selected = b
    second = session.hook(0x1000,task=b['task_id'],actions=[{'op':'task-layers','layers':[]}],once=False,max_hits=3)
    session.selected = a
    session.queue = [_stop('breakpoint',first['breakpoint_id'])]
    assert session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)['hook_hits'][0]['hook'] == first['hook']
    def interrupted(command, timeout_ms):
        assert command == 's'
        session.selected = b
        return _stop('stopped')
    session._execute = interrupted
    assert session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)['outcome'] == 'stopped'
    assert session._qemu_hook_pending == first['hook'] and session._qemu_hook_pending_task == a['task_id']
    result = session._run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert result['hook_hits'][0]['hook'] == second['hook']
    assert [row['hits'] for row in session.hooks()['hooks']] == [1,1]
