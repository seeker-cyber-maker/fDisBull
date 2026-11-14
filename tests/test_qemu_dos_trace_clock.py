"""Hostile live-clock receipts and source-trace admission boundaries.

The clock reads use the production QMP envelope against a deterministic peer.
These tests establish host validation and deadline propagation, not native
guest timing or instruction retirement.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull.debug_script import execute_script, validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_dos_trace import (
    QemuDOSSourceTraceMixin, _clock_bracket, _clock_preflight, _clock_sample,
)
from fdisbull.qemu_machine import machine_trace_operation
from test_qemu_clock_budget import owned
from test_qemu_dos_trace_contract import unopened_session


@pytest.fixture
def trace_owner(owned):
    owned.context.run_id = 'authored-trace-run'
    owned.context._deadline = None
    owned.context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    owned.journal = []
    owned.context._event = lambda name, value: owned.journal.append((name, deepcopy(value)))
    return owned


def predicate(sample, **changes):
    value = dict(kind='virtual-time-range', run=sample['run'], epoch=sample['epoch'],
                 native_epoch=sample['native_epoch'], start_ns=0, end_ns=2000)
    value.update(changes)
    return value


def nested(leaf):
    # A Boolean branch that could short-circuit at evaluation must still have
    # every clock identity admitted before any saved-route mutation.
    return {'any': [dict(kind='register', register='ax', equals=0),
                    {'all': [dict(kind='register', register='bx', equals=0), leaf]}]}


def route(until):
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-registers', registers={'rax': {'expected': 0, 'value': 1}}),
        {'op': 'trace-until', 'until': until, 'max_steps': 1},
    ])


def test_internal_samples_share_public_clock_sequence_without_journaling(trace_owner):
    o = trace_owner
    public_before = o.context.clock_observe()
    before = _clock_sample(o.context)
    public_between = o.context.clock_observe()
    after = _clock_sample(o.context)
    bracket = _clock_bracket(o.context, before, after)

    assert [public_before['sequence'], before['sequence'], public_between['sequence'],
            after['sequence']] == [1, 2, 3, 4]
    assert bracket['epoch'] == public_before['epoch'] == public_between['epoch']
    assert bracket['run'] == o.context.run_id
    assert bracket['virtual_ns'] == 1000 and bracket['icount'] == 41
    assert bracket['before']['sequence'] == 2 and bracket['after']['sequence'] == 4
    assert [name for name, _ in o.journal] == ['machine-clock-observe'] * 2
    assert [name for name, _ in o.wire.calls] == [
        'query-status', 'query-replay', 'x-fdisbull-query-clock'] * 4
    before['virtual_ns'] = 99
    assert bracket['before']['virtual_ns'] == 1000
    assert not o.executions and not o.vm.closed


@pytest.mark.parametrize('field', ['virtual_ns', 'icount'])
def test_stopped_clock_bracket_refuses_forward_drift_and_closes(trace_owner, field):
    o = trace_owner
    before = _clock_sample(o.context)
    if field == 'virtual_ns':
        o.wire.receipt['virtual-ns'] += 1
    else:
        o.wire.counter += 1
    after = _clock_sample(o.context)
    # Each sample is individually monotonic. Their stopped bracket is not.
    with pytest.raises(DebuggerError, match='not stable'):
        _clock_bracket(o.context, before, after)
    assert o.vm.closed and not o.executions and not o.journal


@pytest.mark.parametrize('field', ['run', 'epoch'])
def test_stopped_clock_bracket_refuses_changed_host_identity(trace_owner, field):
    o = trace_owner
    before = _clock_sample(o.context)
    if field == 'run':
        o.context.run_id = 'other-run'
    else:
        o.vm._clock_observation_state['epoch'] = 'b' * 32
    after = _clock_sample(o.context)
    with pytest.raises(DebuggerError, match='epoch changed'):
        _clock_bracket(o.context, before, after)
    assert o.vm.closed and not o.journal


def test_native_reset_epoch_cannot_be_rebound_by_a_new_source_sample(trace_owner):
    o = trace_owner
    before = _clock_sample(o.context)
    o.wire.receipt['epoch'] += 1
    with pytest.raises(DebuggerError, match='epoch changed'):
        _clock_sample(o.context)
    assert before['native_epoch'] == 1
    assert o.vm.closed and not o.journal and not o.executions


@pytest.mark.parametrize('change', [
    {'virtual-ns': None}, {'pending-stop': True}, {'budget-state': 'invalidated'},
])
def test_invalid_native_clock_never_returns_a_source_clock(trace_owner, change):
    o = trace_owner
    o.wire.receipt.update(change)
    with pytest.raises(DebuggerError) as caught:
        _clock_sample(o.context)
    assert not hasattr(caught.value, 'result')
    assert not hasattr(o.vm, '_clock_observation_state')
    assert o.vm.closed and not o.journal and not o.executions


def bounds(o):
    return (getattr(o.context, '_rpc_deadline', None), o.context._deadline,
            o.vm.operation_deadline, o.qmp.operation_deadline, o.remote.operation_deadline)


def install_distinct_bounds(o):
    o.context._rpc_deadline, o.context._deadline = 100.8, 100.7
    o.vm.operation_deadline = 100.6
    o.qmp.operation_deadline, o.remote.operation_deadline = 100.5, 100.4


@pytest.mark.parametrize('source', ['request', 'script', 'session', 'vm', 'qmp', 'gdb'])
def test_earliest_trace_bound_limits_lock_admission_without_mutating_channels(trace_owner, source):
    o = trace_owner
    install_distinct_bounds(o)
    targets = dict(script=(o.context, '_rpc_deadline'), session=(o.context, '_deadline'),
                   vm=(o.vm, 'operation_deadline'), qmp=(o.qmp, 'operation_deadline'),
                   gdb=(o.remote, 'operation_deadline'))
    if source != 'request':
        owner, field = targets[source]
        setattr(owner, field, 100.02)
    old = bounds(o)
    waits = []

    class Busy:
        def acquire(self, *, timeout):
            waits.append(timeout)
            return False

    o.vm.lock = Busy()
    with pytest.raises(TimeoutError, match='busy'):
        QemuDOSSourceTraceMixin._trace_clock_preflight(
            o.context, None, timeout_ms=20 if source == 'request' else 1000)
    assert waits == pytest.approx([.02])
    assert bounds(o) == old and not o.wire.calls and not o.vm.closed


def test_expired_trace_bound_refuses_before_attempting_machine_lock(trace_owner):
    o = trace_owner
    o.qmp.operation_deadline = o.clock.now

    class Unavailable:
        def acquire(self, **kwargs):
            pytest.fail('Expired trace attempted machine lock admission')

    o.vm.lock = Unavailable()
    with pytest.raises(TimeoutError, match='before admission'):
        QemuDOSSourceTraceMixin._trace_clock_preflight(o.context, None)
    assert not o.wire.calls and not o.vm.closed


def test_lock_wait_consumes_trace_budget_before_any_native_query(trace_owner):
    o = trace_owner
    released = []

    class Delayed:
        def acquire(self, *, timeout):
            assert timeout == pytest.approx(.02)
            o.clock.now += .03
            return True

        def release(self):
            released.append(True)

    o.vm.lock = Delayed()
    old = bounds(o)
    with pytest.raises(TimeoutError, match='before dispatch'):
        QemuDOSSourceTraceMixin._trace_clock_preflight(o.context, None, timeout_ms=20)
    assert released == [True] and bounds(o) == old
    assert not o.wire.calls and not o.vm.closed


def test_bound_tightened_while_waiting_is_reread_after_lock(trace_owner):
    o = trace_owner
    seen, released = [], []

    class Tightened:
        def acquire(self, *, timeout):
            o.remote.operation_deadline = 100.01
            return True

        def release(self):
            released.append(True)

    @machine_trace_operation
    def observe(self, *, timeout_ms=1000):
        seen.append((self._deadline, self.vm.operation_deadline,
                     self.vm.qmp.operation_deadline, self.vm.gdb.operation_deadline))
        return _clock_sample(self)

    o.vm.lock = Tightened()
    observe(o.context)
    assert seen == [(100.01,) * 4] and released == [True]
    assert o.remote.operation_deadline == 100.01
    assert o.context._deadline is o.vm.operation_deadline is o.qmp.operation_deadline is None


@pytest.mark.parametrize('ending', ['success', 'failure', 'late-return'])
@pytest.mark.parametrize('lazy_gdb', [False, True])
def test_trace_restores_each_old_bound_and_keeps_result_on_late_return(trace_owner, ending, lazy_gdb):
    o = trace_owner
    install_distinct_bounds(o)
    o.context._rpc_deadline = 100.02
    old = bounds(o)
    if lazy_gdb:
        o.vm.gdb = None
    seen = []
    failure = OSError('authored observation failure')
    result = {}

    @machine_trace_operation
    def observe(self, *, timeout_ms=1000):
        if self.vm.gdb is None:
            self.vm.gdb = SimpleNamespace(socket=object(), operation_deadline=self.vm.operation_deadline)
        seen.append((self._deadline, self.vm.operation_deadline,
                     self.vm.qmp.operation_deadline, self.vm.gdb.operation_deadline))
        result.update(sample=_clock_sample(self))
        if ending == 'failure':
            raise failure
        if ending == 'late-return':
            o.clock.now += .03
        return result

    if ending == 'success':
        assert observe(o.context) is result
    elif ending == 'failure':
        with pytest.raises(OSError) as caught:
            observe(o.context)
        assert caught.value is failure
    else:
        with pytest.raises(TimeoutError, match='exceeded') as caught:
            observe(o.context)
        assert caught.value.result is result
    assert seen == [(100.02,) * 4]
    assert bounds(o) == old
    if lazy_gdb:
        assert o.vm.gdb.operation_deadline == old[2]
    assert not o.vm.closed and not o.executions and not o.journal


def test_source_sampling_uses_one_deadline_through_actual_qmp_envelopes(trace_owner):
    o = trace_owner
    install_distinct_bounds(o)
    o.context._rpc_deadline = 100.025
    old = bounds(o)
    o.wire.latency = .01

    @machine_trace_operation
    def observe(self, *, timeout_ms=1000):
        return _clock_sample(self)

    with pytest.raises(TimeoutError):
        observe(o.context)
    assert [name for name, _ in o.wire.calls] == [
        'query-status', 'query-replay', 'x-fdisbull-query-clock']
    assert o.wire.budgets == pytest.approx([.025, .015, .005])
    assert o.clock.now == pytest.approx(100.025)
    assert bounds(o) == old
    assert o.vm.closed and not o.executions and not o.journal


def test_recursive_clock_preflight_checks_all_leaves_with_one_passive_sample(trace_owner):
    o = trace_owner
    before = _clock_sample(o.context)
    until = {'all': [predicate(before), nested(predicate(before, start_ns=1000))]}
    calls = len(o.wire.calls)
    assert _clock_preflight(o.context, until) is None
    assert len(o.wire.calls) == calls + 3
    assert not o.journal and not o.executions and not o.vm.closed


@pytest.mark.parametrize('field,value', [
    ('run', 'other-run'), ('epoch', 'f' * 32), ('native_epoch', 2),
])
def test_foreign_nested_clock_refuses_before_an_earlier_script_write(trace_owner, field, value):
    o = trace_owner
    first = _clock_sample(o.context)
    session = unopened_session()
    session.vm, session.run_id = o.vm, o.context.run_id
    session.project = o.context.project
    session._deadline = None
    until = {'all': [predicate(first), nested(predicate(first, **{field: value}))]}
    script = route(until)
    assert len(validate_script(script, session=session)) == 2
    calls = len(o.wire.calls)
    with pytest.raises(ValueError, match='owned run or clock epoch'):
        execute_script(session, script)
    assert len(o.wire.calls) == calls + 3
    assert session._deadline is None and session._rpc_deadline is None
    assert not o.executions and not o.journal and not o.vm.closed


@pytest.mark.parametrize('profile', ['standard', 'instruction'])
def test_unsupported_clock_profile_refuses_nested_predicate_before_prior_write(profile):
    session = unopened_session()
    session.vm.machine_configuration = dict(cpus=1, clock_profile=machine_clock_configuration(profile, 1))
    until = nested(predicate(dict(run='authored-run', epoch='a' * 32, native_epoch=1)))
    with pytest.raises(ValueError, match='virtual clock profile'):
        execute_script(session, route(until))


@pytest.mark.parametrize('change,message', [
    ({'run': '$earlier.run'}, 'literal'),
    ({'start_ns': True}, 'integer'),
    ({'end_ns': 0}, 'half-open'),
])
def test_invalid_nested_clock_literal_refuses_unopened_script_before_prior_write(change, message):
    until = nested(predicate(dict(run='authored-run', epoch='a' * 32, native_epoch=1), **change))
    with pytest.raises(ValueError, match=message):
        execute_script(unopened_session(), route(until))


@pytest.mark.parametrize('failure_stage', ['registers', 'step-journal', 'tracking-stop', 'tracking-retirement'])
def test_post_reply_failure_retains_the_original_native_stop_without_a_clock(trace_owner, failure_stage):
    o = trace_owner
    attempts = []
    failure = OSError('authored post-stop failure')

    def execute(command, timeout_ms):
        attempts.append(command)
        return b'T05thread:1;', False

    def fail(*args, **kwargs):
        raise failure

    o.remote.execute = execute
    retirements = []
    if failure_stage == 'registers':
        o.context.registers = fail
    elif failure_stage == 'step-journal':
        o.context._event = fail
    else:
        def retire(reason):
            retirements.append(reason)
            if failure_stage == 'tracking-retirement':
                raise ValueError('authored tracking retirement failure')
        o.context._automatic_runtime_tracker = SimpleNamespace(
            before_execution=lambda reason: None, internal_breakpoints=set(),
            after_stop=fail, close=retire)
    with pytest.raises(OSError) as caught:
        o.context.step()
    assert caught.value is failure
    stop = caught.value.result
    assert stop['session']['stop_reason']['native_reply'] == 'T05thread:1;'
    assert stop['session']['state'] == 'stopped' and 'clock' not in stop
    if failure_stage == 'registers':
        assert stop['registers'] is None
        assert stop['session']['stop_reason']['classification_complete'] is False
    else:
        assert stop['outcome'] == 'step'
    assert attempts == ['s'] and o.vm.machine_stopped
    if failure_stage.startswith('tracking'):
        assert retirements == ['machine-post-stop-publication-failed']
        assert o.vm.closed and o.context._automatic_internal_pending is None
        if failure_stage == 'tracking-retirement':
            assert caught.value.tracking_retirement_error == 'ValueError'
