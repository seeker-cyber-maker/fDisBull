"""Host policy tests for paused CHIP-8 hooks; native execution is separate."""
from contextlib import contextmanager
from copy import deepcopy
import threading
import time
from types import SimpleNamespace
import pytest
from fdisbull.chip8_hooks import Chip8HookMixin


class Session(Chip8HookMixin):
    def __init__(self):
        self.vm=SimpleNamespace(lock=threading.RLock());self.version={'id':4};self.capabilities={'hooks':True}
        self.project=SimpleNamespace(db=SimpleNamespace(in_transaction=False),debug_layer_info=self.layer_info)
        self.breakpoints={};self.next_bp=1;self.pc=0x200;self.value=0;self.closed=False
        self.results=[];self.calls=[];self.events=[];self.active=[];self._reset_chip8_hooks()
    def layer_info(self,identifier):
        if identifier!='layer':raise ValueError('unknown layer')
        return {'version':4,'address_model':'chip8-flat-4k','chip8_profile':'chip8-classic-pilot-default-v1'}
    @contextmanager
    def _budget(self,owner,deadline):
        with owner.lock:yield
    def _event(self,operation,value):self.events.append((operation,deepcopy(value)))
    def close(self):self.closed=True
    def breakpoint(self,address,*,access='x',length=1):
        if address in self.breakpoints.values():raise ValueError('occupied')
        ident=self.next_bp;self.next_bp+=1;self.breakpoints[ident]=address
        return {'breakpoint_id':ident}
    def delete_breakpoint(self,identifier):
        if self._chip8_hook_owns_breakpoint(identifier) and not self._chip8_hook_deleting:
            raise ValueError('Hook-owned')
        del self.breakpoints[identifier]
        return {'deleted':True}
    def registers(self):return {'linear_pc':hex(self.pc)}
    def write_registers(self,edits):
        item=edits['v0']
        if item['expected']!=self.value:raise ValueError('guard differs')
        self.value=item['value'];return {'v0':self.value}
    def layers(self,ids):self.active=list(ids);return {'active':list(ids)}
    def _execute(self,command,timeout_ms):
        self.calls.append(command)
        result=self.results.pop(0)
        if result.get('new_pc') is not None:self.pc=result.pop('new_pc')
        if result.get('inc'):self.value+=1;result.pop('inc')
        result.setdefault('registers',{'linear_pc':hex(self.pc)})
        return result


def stop(outcome='breakpoint', bp=1, pc=0x200, native='T05'):
    return {'outcome':outcome,'registers':{'linear_pc':hex(pc)},
            'session':{'stop_reason':{'breakpoint_ids':[bp], 'native_reply':native}}}


def test_registration_collision_preflight_and_owned_delete():
    d=Session();d.breakpoint(0x200)
    with pytest.raises(ValueError,match='occupies'):d.hook(0x200,actions=[{'op':'layers','layers':[]}])
    assert d.breakpoints=={1:0x200}
    for address in (0x201,0xfff,0x1000):
        with pytest.raises(ValueError):d.hook(address,actions=[{'op':'layers','layers':[]}])
    with pytest.raises(ValueError):d.hook(0x202,actions=[{'op':'registers','registers':{'pc':{'expected':0,'value':2}}}])
    item=d.hook(0x202,actions=[{'op':'layers','layers':['layer']}])
    with pytest.raises(ValueError,match='Hook-owned'):d.delete_breakpoint(item['breakpoint_id'])
    assert d.delete_hook(item['hook'])['deleted'] and d.breakpoints=={1:0x200}


def test_repeat_hit_pending_displacement_and_exhaustion():
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':['layer']}],once=False,max_hits=2)
    bp=item['breakpoint_id'];d.results=[stop(bp=bp)]
    first=d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert first['outcome']=='hook' and first['hook_hits'][0]['hit']==1 and d.active==['layer']
    assert d._chip8_hook_pending==item['hook'] and d.calls==['c']
    # One displaced instruction, then the next real visit. The rearmed ID is new.
    d.results=[{'outcome':'step','new_pc':0x202,'inc':True},stop(bp=2,pc=0x200)]
    second=d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert second['outcome']=='hook' and second['hook_hits'][0]['hit']==2
    assert d.value==1 and d.calls==['c','s','c'] and d.hooks()['hooks']==[]


def test_non_hook_stop_and_competing_breakpoints_never_dispatch():
    for outcome in ('exception','key_wait','timeout','layer_conflict'):
        d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':['layer']}])
        d.results=[stop(outcome=outcome,bp=item['breakpoint_id'])]
        result=d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
        assert result['outcome']==outcome and result['hook_hits']==[] and not d.active
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':['layer']}])
    d.results=[stop(bp=item['breakpoint_id'],native='T02')]
    assert d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)['hook_hits']==[]


def test_timeout_during_pending_step_fails_closed_without_replay():
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':[]}],once=False,max_hits=2)
    d.results=[stop(bp=item['breakpoint_id'])]
    d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    d.results=[stop(outcome='timeout')]
    with pytest.raises(TimeoutError) as error:d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert d.closed and d.calls==['c','s'] and 'do not replay' in error.value.result['disposition']


def test_portable_checkpoint_remaps_traps_and_pending_without_replay():
    original=Session();item=original.hook(0x200,actions=[{'op':'layers','layers':['layer']}],once=False,max_hits=2)
    original.results=[stop(bp=item['breakpoint_id'])]
    original._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    state=original._chip8_hook_state();assert 'breakpoint_id' not in state['hooks'][0]
    fresh=Session();fresh.next_bp=7;mapping=fresh._restore_chip8_hooks(state)
    assert mapping=={item['hook']:7} and fresh._chip8_hook_pending==item['hook']
    fresh.results=[{'outcome':'step','new_pc':0x202,'inc':True}]
    result=fresh._chip8_step_with_hooks(timeout_ms=1000)
    assert result['outcome']=='step' and result['hook_hits']==[] and fresh.value==1
    assert fresh.calls==['s'] and fresh.hooks()['hooks'][0]['hits']==1


def test_bad_checkpoint_refused_before_install_and_action_failure_closes():
    d=Session();bad={'hooks':[],'pending':'0'*32}
    with pytest.raises(ValueError):d._restore_chip8_hooks(bad)
    assert not d.breakpoints
    item=d.hook(0x200,actions=[{'op':'registers','registers':{'v0':{'expected':5,'value':1}}}])
    d.results=[stop(bp=item['breakpoint_id'])]
    with pytest.raises(ValueError) as error:d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert d.closed and error.value.result['hook_hit']['hit']==1
    assert d.calls==['c'] and 'do not replay' in error.value.result['disposition']


def test_old_runtime_rejects_hook_api_before_effects():
    d=Session();d.capabilities['hooks']=False
    for operation in (lambda:d.hook(0x200,actions=[{'op':'layers','layers':[]}]),
                      d.hooks,lambda:d.delete_hook('missing')):
        with pytest.raises(ValueError,match='no hook support'):operation()
    assert not d.breakpoints and not d.events


def test_foreign_layer_identity_refused_before_breakpoint():
    d=Session()
    d.project.debug_layer_info=lambda _: {'version':4,'address_model':'x86','chip8_profile':'chip8-classic-pilot-default-v1'}
    with pytest.raises(ValueError,match='identity'):d.hook(0x200,actions=[{'op':'layers','layers':['foreign']}])
    assert not d.breakpoints and not d.events


def test_key_wait_during_displacement_retains_pending_without_repeat_action():
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':['layer']}],once=False,max_hits=2)
    d.results=[stop(bp=item['breakpoint_id'])]
    d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    d.results=[stop(outcome='key_wait')]
    result=d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert result['outcome']=='key_wait' and d._chip8_hook_pending==item['hook']
    assert d.hooks()['hooks'][0]['hits']==1 and len([e for e in d.events if e[0]=='hook-hit'])==1
    d.results=[{'outcome':'step','new_pc':0x202,'inc':True}]
    assert d._chip8_step_with_hooks(timeout_ms=1000)['outcome']=='step'
    assert d._chip8_hook_pending is None and d.value==1


def test_deadline_after_action_preserves_evidence_and_closes(monkeypatch):
    import fdisbull.chip8_hooks as hooks
    clock=[10.0];monkeypatch.setattr(hooks.time,'monotonic',lambda:clock[0])
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':['layer']}])
    def slow_layers(ids):
        d.active=list(ids);clock[0]=12.0
        return {'active':list(ids)}
    d.layers=slow_layers;d.results=[stop(bp=item['breakpoint_id'])]
    with pytest.raises(TimeoutError) as error:d._chip8_run_with_hooks(timeout_ms=1000,stop_on_hook=True)
    assert d.closed and d.calls==['c'] and d.active==['layer']
    assert error.value.result['hook_hits'][0]['hit']==1
    assert 'do not replay' in error.value.result['disposition']


def test_delete_hook_refuses_caller_transaction_before_live_mutation():
    import sqlite3
    d=Session();item=d.hook(0x200,actions=[{'op':'layers','layers':[]}],once=False,max_hits=2)
    d._chip8_hook_pending=item['hook']
    before_breakpoints=dict(d.breakpoints);before_hooks=deepcopy(d.hooks());before_events=deepcopy(d.events)
    connection=sqlite3.connect(':memory:')
    try:
        d.project.db=connection;connection.execute('BEGIN')
        with pytest.raises(ValueError,match='no caller transaction'):
            d.delete_hook(item['hook'])
        connection.rollback()
        assert d.breakpoints==before_breakpoints and d.hooks()==before_hooks
        assert d.events==before_events and not d.closed
    finally:
        connection.close()
