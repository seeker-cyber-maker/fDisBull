"""Host tests of bounded periodic QEMU rule ownership and interruption."""
from copy import deepcopy
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull import memory_rules
from fdisbull.memory_rules import MemoryRuleSessionMixin
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from fdisbull.qemu_memory_rules import admit_native_rule_run


class Session(MemoryRuleSessionMixin):
    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock(), qmp=SimpleNamespace(), gdb=None,
            qmp_commands=set(VIRTUAL_CLOCK_COMMANDS), operation_deadline=None,
            machine_configuration={'cpus':1,'clock_profile':machine_clock_configuration('virtual',1)})
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
        self.run_id = 'run'; self.metadata = {}; self.version = {'id':1,'sha256':'v'}
        self.calls = []; self.ticks = 0; self.clock_result = ordinary()
        self.closed = False
        self.configuration = {'origin_context':{'region':{'start':3,'length':1},
            'address_space':'physical','task_evidence':'physical address identity','task_id':'physical-machine'},
            'max_ticks':20,'max_applications':20}
        self.progress = {'format':'fdisbull-memory-rule-progress-1','rule_artifact':'rule',
            'run_id':'run','sequence':0,'status':'active','phase':'created','reason':None,
            'ticks':0,'attempts':0,'applications':0,'last':{}}
    def _clock_snapshot(self):
        self.calls.append('clock-observe')
        return {'virtual_clock':{'native':{'budget-state':'idle'}}}
    def memory_rule_tick(self, rule):
        self.calls.append('tick'); self.ticks += 1
        self.progress = dict(self.progress,ticks=self.ticks,sequence=self.progress['sequence']+1,
                             phase='observed',last={'applied':False})
        return {'tick_executed':True,'status':'active','applied':False,'progress_artifact':'tick'}
    def clock_advance(self, delta_ns, *, timeout_ms):
        self.calls.append(('advance',delta_ns,timeout_ms))
        assert self._rpc_deadline == self._deadline == self.vm.operation_deadline
        if isinstance(self.clock_result,Exception): raise self.clock_result
        return deepcopy(self.clock_result)
    def _clock_advance_with_hooks(self, delta_ns, *, timeout_ms):
        return self.clock_advance(delta_ns, timeout_ms=timeout_ms)
    def _event(self,*args,**kwargs): pass
    def close(self): self.closed = True


def ordinary():
    return {'outcome':'stopped','timed_out':False,
            'session':{'state':'stopped','stop_reason':{'kind':'stopped','breakpoint_ids':[],
                       'native_reply':'T02'}},
            'clock_budget':{'deadline_reached':True}}


@pytest.fixture
def session(monkeypatch):
    value = Session()
    monkeypatch.setattr(memory_rules,'_rule',lambda project, rule: ({'run':'run'},value.configuration))
    monkeypatch.setattr(memory_rules,'_progress',lambda *args: ('progress',deepcopy(value.progress)))
    def save(project, identifier, run, previous, progress, **kwargs):
        value.calls.append(('journal',progress['phase']))
        value.progress = deepcopy(progress)
        return 'progress',deepcopy(progress)
    monkeypatch.setattr(memory_rules,'_save',save)
    monkeypatch.setattr('fdisbull.qemu_memory_rules._capture',lambda *args:
                        (b'x',deepcopy(value.configuration['origin_context']),{}))
    return value


def test_ordinary_native_intervals_are_fresh_and_journaled(session):
    result = session.memory_rule_run('rule',ticks=3,interval_ms=10,timeout_ms=1000)
    assert result['complete'] and result['clock_domain'] == 'qemu-virtual-ns'
    assert session.ticks == 3
    assert [call[:2] for call in session.calls if isinstance(call,tuple) and call[0]=='advance'] == [
        ('advance',10_000_000),('advance',10_000_000)]
    assert [call for call in session.calls if isinstance(call,tuple) and call[0]=='journal'] == [
        ('journal','execution-pending'),('journal','execution-complete')]*2
    assert session._rpc_deadline is None and session.vm.operation_deadline is None


@pytest.mark.parametrize('change', ['breakpoint','watchpoint','exit','timeout','unfired'])
def test_nonordinary_stop_never_executes_another_tick(session,change):
    if change == 'breakpoint': session.clock_result['session']['stop_reason']['breakpoint_ids'] = [1]
    elif change == 'watchpoint': session.clock_result['session']['stop_reason']['native_reply'] = 'T02watch:100;'
    elif change == 'exit': session.clock_result.update(outcome='guest_exit', guest_exit={'code':0})
    elif change == 'timeout': session.clock_result['timed_out'] = True
    else: session.clock_result['clock_budget']['deadline_reached'] = False
    result = session.memory_rule_run('rule',ticks=3,timeout_ms=1000)
    assert result['outcome'] == 'clock_interrupted' and result['completed_ticks'] == 1
    assert result['clock_stop'] == session.clock_result and session.ticks == 1
    assert session.progress['phase'] == 'interrupted'


def test_uncertain_clock_dispatch_is_journaled_and_never_replayed(session):
    session.clock_result = TimeoutError('lost timer reply')
    result = session.memory_rule_run('rule',ticks=3,timeout_ms=1000)
    assert result['outcome'] == 'uncertain' and session.closed
    assert session.progress['status'] == 'uncertain' and session.ticks == 1
    assert len([c for c in session.calls if isinstance(c,tuple) and c[0]=='advance']) == 1


@pytest.mark.parametrize('owner', ['pending','lease','schedule','sync','budget','standard','commands'])
def test_passive_preflight_refuses_conflicts_without_target_effect(session,owner):
    if owner in ('pending','lease','schedule'):
        session.vm._physical_input = {'valid':True,'pending':[], 'leases':{}}
        if owner == 'pending': session.vm._physical_input['pending'] = [1]
        elif owner == 'lease': session.vm._physical_input['leases'] = {'a':1}
        else: session.vm._physical_input['schedule'] = {'bound':True}
    elif owner == 'sync': session.vm._clock_sync = {'state':'active'}
    elif owner == 'budget': session.vm._active_clock_budget = {'x':1}
    elif owner == 'standard': session.vm.machine_configuration['clock_profile'] = machine_clock_configuration('standard',1)
    else: session.vm.qmp_commands.clear()
    before = deepcopy(session.progress)
    with pytest.raises(ValueError): admit_native_rule_run(session)
    with pytest.raises(ValueError): session.memory_rule_run('rule',ticks=2,timeout_ms=1000)
    assert session.calls == [] and session.progress == before and not session.closed


def test_preflight_rejects_changed_epoch_before_first_tick(session,monkeypatch):
    context = deepcopy(session.configuration['origin_context']); context['capture_epoch'] = 'changed'
    monkeypatch.setattr('fdisbull.qemu_memory_rules._capture',lambda *args: (b'x',context,{}))
    with pytest.raises(ValueError,match='mapping or epoch'):
        session.memory_rule_run('rule',ticks=2,timeout_ms=1000)
    assert session.ticks == 0 and session.calls == ['clock-observe']


def test_contended_lock_uses_requested_outer_deadline_without_target_calls(session):
    acquired, release = threading.Event(), threading.Event()
    def holder():
        with session.vm.lock:
            acquired.set(); release.wait(2)
    thread = threading.Thread(target=holder); thread.start(); assert acquired.wait(1)
    start = time.monotonic()
    try:
        with pytest.raises(TimeoutError): session.memory_rule_run('rule',ticks=2,timeout_ms=30)
        assert time.monotonic()-start < .5
        assert session.calls == [] and session.ticks == 0
    finally:
        release.set(); thread.join()


def test_lost_completion_journal_closes_and_preserves_pending_no_replay(session,monkeypatch):
    calls = []
    def save(project, identifier, run, previous, progress, **kwargs):
        calls.append(progress['phase'])
        if progress['phase'] != 'execution-pending':
            raise OSError('private journal unavailable')
        session.progress = deepcopy(progress)
        return 'pending-artifact',deepcopy(progress)
    monkeypatch.setattr(memory_rules,'_save',save)
    result = session.memory_rule_run('rule',ticks=2,timeout_ms=1000)
    assert result['outcome'] == 'uncertain' and session.closed
    assert session.progress['status'] == 'pending' and session.ticks == 1
    assert session._memory_rule_blocked['rule']['progress_persisted'] is False
    assert calls == ['execution-pending','execution-complete','failed']
    assert len([c for c in session.calls if isinstance(c,tuple) and c[0]=='advance']) == 1


def test_caller_owned_real_project_transaction_refused_before_rule_or_target_io(tmp_path):
    from fdisbull.project import Project
    binary = tmp_path / 'authored.com'
    binary.write_bytes(bytes.fromhex('90ebfd'))
    with Project.create(tmp_path / 'authored.fdb',binary,image='com') as project:
        session = Session(); session.project = project
        before = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
        project.db.execute('BEGIN')
        try:
            with pytest.raises(ValueError,match='caller-owned transaction'):
                session.memory_rule_run('unknown-rule',ticks=2,timeout_ms=1000)
            assert project.db.in_transaction
            assert project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before
            assert session.calls == [] and session.ticks == 0 and not session.closed
        finally:
            project.db.rollback()


@pytest.mark.parametrize('active,execution', [(['authored-ram-layer'],{}),
                                                (['authored-fetch-layer'],{0x100:0x90}),
                                                ([],{0x100:0x90})])
def test_base_origin_active_or_stale_native_layers_refuse_before_target_io(session,active,execution):
    session._layer_active = deepcopy(active)
    session._layer_exec = deepcopy(execution)
    before = deepcopy(session.progress)
    with pytest.raises(ValueError,match='explicit RAM view'):
        session.memory_rule_run('rule',ticks=2,timeout_ms=1000)
    assert session._layer_active == active and session._layer_exec == execution
    assert session.progress == before and session.calls == [] and session.ticks == 0
    assert not session.closed


@pytest.mark.parametrize('owner', ['views', 'binding', 'monitor', 'scheduler'])
def test_base_origin_tasks_refuse_before_target_io(session, owner):
    attr = {'views':'_dos_task_views', 'binding':'_dos_task_binding',
            'monitor':'_dos_task_monitor', 'scheduler':'_dos_scheduler'}[owner]
    setattr(session, attr, {'present': True})
    admit_native_rule_run(session)
    before = deepcopy(session.progress)
    with pytest.raises(ValueError, match='explicit RAM view'):
        session.memory_rule_run('rule', ticks=2, timeout_ms=1000)
    assert session.calls == [] and session.progress == before and session.ticks == 0


def test_hooks_alone_admit_and_preserve_periodic_run(session):
    session._qemu_hooks = {'h': {'active': True}}
    admit_native_rule_run(session)
    result = session.memory_rule_run('rule', ticks=2, timeout_ms=1000)
    assert result['complete'] and result['completed_ticks'] == 2


def test_rule_view_progress_accepts_only_owned_generation_changes(session):
    context = dict(session.configuration['origin_context'], qemu_memory_view={
        'view':'ram', 'scope':'task-private', 'task_identity':{'task_id':'a'},
        'task_generation':1, 'active_layers':['authored'], 'active_layers_sha256':'h1'})
    config = dict(session.configuration, origin_context=context)
    next_context = deepcopy(context)
    next_context['qemu_memory_view'].update(task_generation=2,
        active_layers=['authored','rule-overlay'], active_layers_sha256='h2')
    progress = {'view_context':next_context, 'view_overlay':'rule-overlay'}
    assert memory_rules._current_context(config, progress) == next_context
    wrong = deepcopy(progress)
    wrong['view_context']['qemu_memory_view']['task_identity']['task_id'] = 'b'
    with pytest.raises(ValueError, match='view identity'):
        memory_rules._current_context(config, wrong)
    without_overlay = dict(progress, view_overlay=None)
    with pytest.raises(ValueError, match='view identity'):
        memory_rules._current_context(config, without_overlay)


def test_task_change_after_interval_stops_without_second_tick(session):
    tick = session.memory_rule_tick
    def selected_task_tick(rule):
        if session.ticks:
            raise ValueError('selected task differs from A')
        return tick(rule)
    session.memory_rule_tick = selected_task_tick
    result = session.memory_rule_run('rule', ticks=3, interval_ms=10, timeout_ms=1000)
    assert result['outcome'] == 'context_changed' and result['completed_ticks'] == 1
    assert session.ticks == 1 and session.progress['ticks'] == 1
    assert len([c for c in session.calls if isinstance(c,tuple) and c[0]=='advance']) == 1


def test_wrong_selected_task_refuses_before_tick_journal(session, monkeypatch):
    session.configuration['origin_context']['qemu_memory_view'] = {
        'view':'ram', 'scope':'task-private', 'task_identity':{'task_id':'a'}}
    before = deepcopy(session.progress)
    def wrong_task(*args):
        raise ValueError('selected task B differs from rule task A')
    monkeypatch.setattr(memory_rules, '_check_rule_context', wrong_task)
    with pytest.raises(ValueError, match='selected task B'):
        MemoryRuleSessionMixin.memory_rule_tick(session, 'rule')
    assert session.progress == before and session.calls == [] and not session.closed
