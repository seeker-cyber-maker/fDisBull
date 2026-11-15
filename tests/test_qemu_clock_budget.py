"""Admission, single execution and uncertain native-clock cleanup boundaries.

The QMP peer uses the production envelope/timeout code. Actual timer and guest
behavior is established separately by test_qemu_clock_budget_native.py.
"""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from fdisbull.debug_script import validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import (VIRTUAL_CLOCK_COMMANDS, admit_virtual_clock,
                                machine_clock_configuration, machine_clock_arguments)
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_machine import MachineContext


class HostClock:
    now = 100.0

    def __call__(self):
        return self.now


class NativeWire:
    def __init__(self, clock):
        self.clock, self.timeout, self.delay = clock, None, 0
        self.socket_closed = False
        self.buffer = bytearray()
        self.calls, self.budgets = [], []
        self.latency = 0
        self.counter = 41
        self.change_arm = self.change_final = lambda value: value
        self.receipt = {'api-version': 1, 'epoch': 1, 'virtual-ns': 1000,
                        'running': False, 'status': 'paused', 'pending-stop': False,
                        'budget-supported': True, 'budget-state': 'idle'}

    def settimeout(self, seconds):
        assert seconds > 0
        self.timeout = seconds

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        if command == 'query-status':
            value = dict(running=False, status='paused')
        elif command == 'query-replay':
            value = dict(mode='none', icount=self.counter)
        elif command == 'x-fdisbull-query-clock':
            value = self.receipt
        elif command == 'x-fdisbull-arm-clock-budget':
            start = self.receipt['virtual-ns']
            self.receipt.update({'budget-state': 'armed', 'budget-token': args['token'],
                                 'budget-start-ns': start,
                                 'budget-deadline-ns': start + args['delta-ns']})
            self.receipt.pop('budget-fired-ns', None)
            self.receipt.pop('budget-stopped-ns', None)
            value = self.change_arm(deepcopy(self.receipt))
        elif command == 'x-fdisbull-cancel-clock-budget':
            assert args['token'] == self.receipt['budget-token']
            self.receipt['budget-state'] = 'cancelled'
            value = self.change_final(deepcopy(self.receipt))
        else:
            pytest.fail('Unexpected QMP operation: ' + command)
        self.buffer.extend(json.dumps({'id': request['id'], 'return': value}).encode() + b'\n')
        self.delay = self.latency

    def recv(self, count):
        if self.delay >= self.timeout:
            self.clock.now += self.timeout
            self.delay -= self.timeout
            raise TimeoutError('Native reply exceeded the remaining host budget')
        self.clock.now += self.delay
        self.delay = 0
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value

    def close(self):
        self.socket_closed = True


@pytest.fixture
def owned(monkeypatch):
    clock = HostClock()
    monkeypatch.setattr('time.monotonic', clock)
    wire = NativeWire(clock)
    qmp = QemuControl.__new__(QemuControl)
    qmp.socket, qmp.buffer, qmp.sequence = wire, bytearray(), 0
    qmp.lock, qmp.operation_deadline = threading.Lock(), None
    remote = SimpleNamespace(socket=object(), operation_deadline=None)
    vm = SimpleNamespace(qmp=qmp, gdb=remote, lock=threading.RLock(), closed=False,
                         operation_deadline=None, qmp_commands=VIRTUAL_CLOCK_COMMANDS,
                         machine_configuration=dict(cpus=1,
                             clock_profile=machine_clock_configuration('virtual', 1)))
    vm.debugger = lambda: remote
    context = MachineContext(vm)
    context.registers = lambda: dict(linear_pc='0x7c00', cpu_mode='real', registers={})
    state = SimpleNamespace(context=context, vm=vm, wire=wire, qmp=qmp, remote=remote,
                            clock=clock, executions=[], early=False, execution_latency=0)

    def close():
        vm.closed = True
        qmp.close()
        remote.socket = None
        vm.qmp = vm.gdb = None

    def execute(command, timeout_ms):
        state.executions.append((command, timeout_ms, remote.operation_deadline))
        clock.now += state.execution_latency
        end = (wire.receipt['budget-start-ns'] + 128 if state.early
               else wire.receipt['budget-deadline-ns'] + 64)
        wire.receipt.update({'budget-state': 'stopped', 'budget-stopped-ns': end,
                             'virtual-ns': end})
        if not state.early:
            wire.receipt['budget-fired-ns'] = end
        wire.counter += 1
        return (b'T05thread:1;' if state.early else b'T02thread:1;'), clock.now >= remote.operation_deadline

    vm.close, remote.execute = close, execute
    return state


def test_virtual_profile_requires_single_cpu_and_keeps_fixed_icount_arguments():
    assert machine_clock_arguments('virtual') == machine_clock_arguments('instruction')
    assert machine_clock_configuration('virtual', 1)['virtual_ns_supported'] is True
    with pytest.raises(ValueError):
        machine_clock_configuration('virtual', 2)


def test_stock_executable_is_rejected_before_virtual_profile_execution(owned):
    owned.vm.qmp_commands = {'query-replay'}
    with pytest.raises(ValueError, match='extension API 1'):
        admit_virtual_clock(owned.vm)
    assert owned.wire.calls == [] and owned.executions == []


def test_native_budget_runs_once_and_retains_original_stop_and_final_receipt(owned):
    o = owned
    result = o.context.clock_advance(1000, timeout_ms=250)
    assert result['session']['stop_reason']['native_reply'] == 'T02thread:1;'
    assert result['outcome'] == 'stopped' and result['timed_out'] is False
    budget = result['clock_budget']
    assert budget['start_ns'] == 1000 and budget['deadline_ns'] == 2000
    assert budget['elapsed_ns'] == 1064 and budget['overshoot_ns'] == 64
    assert budget['deadline_reached'] is True and budget['native']['pending-stop'] is False
    assert [command for command, _, _ in o.executions] == ['c']
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-arm-clock-budget') == 1
    assert [name for name, _ in o.wire.calls].count('x-fdisbull-cancel-clock-budget') == 1
    assert o.vm.operation_deadline is o.remote.operation_deadline is o.qmp.operation_deadline is None


def test_early_stop_is_returned_without_automatic_continuation(owned):
    o = owned
    o.early = True
    o.context.breakpoints[7] = dict(address=0x7c00, access='x', kind=1, length=1)
    result = o.context.clock_advance(1000)
    assert result['outcome'] == 'breakpoint'
    assert result['session']['stop_reason']['breakpoint_ids'] == [7]
    assert result['clock_budget']['deadline_reached'] is False
    assert result['clock_budget']['fired_ns'] is result['clock_budget']['overshoot_ns'] is None
    assert len(o.executions) == 1 and not o.vm.closed


def test_timer_at_breakpoint_address_does_not_fabricate_a_debugger_trap(owned):
    o = owned
    o.context.breakpoints[7] = dict(address=0x7c00, access='x', kind=1, length=1)
    result = o.context.clock_advance(1000)
    assert result['outcome'] == 'stopped'
    assert result['session']['stop_reason']['breakpoint_ids'] == []
    assert result['clock_budget']['deadline_reached'] is True


@pytest.mark.parametrize('change', [
    lambda v: dict(v, **{'budget-token': 'someone-else'}),
    lambda v: dict(v, **{'epoch': 2}),
    lambda v: dict(v, **{'pending-stop': True}),
    lambda v: dict(v, **{'running': True}),
    lambda v: dict(v, **{'budget-state': 'armed'}),
    lambda v: dict(v, **{'budget-fired-ns': v['budget-deadline-ns'] - 1}),
    lambda v: dict(v, **{'budget-stopped-ns': v['virtual-ns'] - 1}),
])
def test_uncertain_terminal_receipt_closes_owner_without_replay(owned, change):
    o = owned
    o.wire.change_final = change
    with pytest.raises(DebuggerError):
        o.context.clock_advance(1000)
    assert o.vm.closed and o.wire.socket_closed and len(o.executions) == 1


def test_malformed_arm_closes_owner_before_any_continue(owned):
    o = owned
    o.wire.change_arm = lambda value: dict(value, **{'budget-deadline-ns': 7777})
    with pytest.raises(DebuggerError, match='arm differs'):
        o.context.clock_advance(1000)
    assert o.vm.closed and not o.executions


def test_one_host_deadline_reaches_real_qmp_without_refresh(owned):
    o = owned
    o.wire.latency = .01
    with pytest.raises(TimeoutError):
        o.context.clock_advance(1000, timeout_ms=45)
    assert [command for command, _ in o.wire.calls] == [
        'query-status', 'query-status', 'query-replay', 'x-fdisbull-query-clock',
        'x-fdisbull-arm-clock-budget']
    assert o.wire.budgets == pytest.approx([.045, .035, .025, .015, .005])
    assert o.clock.now == pytest.approx(100.045)
    assert o.vm.closed and not o.executions


def test_host_expiry_after_continue_cannot_return_timer_success(owned):
    o = owned
    o.execution_latency = .05
    with pytest.raises(TimeoutError):
        o.context.clock_advance(1000, timeout_ms=40)
    assert o.vm.closed and len(o.executions) == 1
    assert 'x-fdisbull-cancel-clock-budget' not in [name for name, _ in o.wire.calls]


def test_clock_lock_admission_uses_script_remainder_without_mutating_channels(owned):
    o = owned
    waits = []
    class Busy:
        def acquire(self, *, timeout):
            waits.append(timeout)
            return False
    o.vm.lock = Busy()
    o.context._rpc_deadline = 100.02
    with pytest.raises(TimeoutError, match='busy'):
        o.context.clock_advance(1000, timeout_ms=1000)
    assert waits == pytest.approx([.02]) and not o.wire.calls and not o.vm.closed
    assert o.vm.operation_deadline is o.qmp.operation_deadline is None


def test_native_channel_deadline_also_bounds_clock_lock_admission(owned):
    o = owned
    waits = []
    class Busy:
        def acquire(self, *, timeout):
            waits.append(timeout)
            return False
    o.vm.lock = Busy()
    o.remote.operation_deadline = 100.01
    with pytest.raises(TimeoutError, match='busy'):
        o.context.clock_advance(1000, timeout_ms=1000)
    assert waits == pytest.approx([.01])
    assert not o.wire.calls and o.remote.operation_deadline == 100.01


def test_native_clock_preserves_prior_deadlines_after_success(owned):
    o = owned
    o.vm.operation_deadline, o.qmp.operation_deadline, o.remote.operation_deadline = 100.5, 100.4, 100.3
    o.context._rpc_deadline = 100.2
    o.context.clock_advance(1000, timeout_ms=1000)
    assert o.executions[0][2] == 100.2
    assert (o.vm.operation_deadline, o.qmp.operation_deadline, o.remote.operation_deadline) == (100.5, 100.4, 100.3)


def test_budget_persistence_failure_closes_the_executed_owner(owned):
    o = owned
    o.context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    def event(operation, value):
        if operation == 'machine-clock-advance':
            raise OSError('evidence store full')
    o.context._event = event
    with pytest.raises(OSError, match='evidence store full'):
        o.context.clock_advance(1000)
    assert o.vm.closed and len(o.executions) == 1


@pytest.mark.parametrize('delta', [None, False, 0, -1, 1.5, 60_000_000_001])
def test_invalid_later_clock_budget_refuses_whole_script_before_dispatch(owned, delta):
    o = owned
    o.context.metadata = {'backend': 'qemu-machine'}
    with pytest.raises(ValueError):
        validate_script({'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
            'steps': [{'op': 'step'}, {'op': 'clock-advance', 'delta_ns': delta}]}, session=o.context)
    assert not o.wire.calls and not o.executions


def test_passive_native_clock_epoch_change_invalidates_observations(owned):
    o = owned
    first = o.context.clock_observe()
    assert first['virtual_ns'] == 1000
    o.wire.receipt['epoch'] = 2
    with pytest.raises(DebuggerError, match='epoch changed'):
        o.context.clock_observe()
    assert o.vm.closed


def test_unsupported_clock_profile_refuses_whole_script_before_an_earlier_step(owned):
    o = owned
    o.context.metadata = {'backend': 'qemu-machine'}
    o.context.capabilities['virtual_clock_budget'] = False
    with pytest.raises(ValueError, match='virtual clock profile'):
        validate_script({'format': 'fdisbull-script-1', 'backend': 'qemu-machine',
            'steps': [{'op': 'step'}, {'op': 'clock-advance', 'delta_ns': 1000}]}, session=o.context)
    assert not o.wire.calls and not o.executions


def test_caller_transaction_refuses_clock_before_native_reads(owned):
    o = owned
    o.context.project = SimpleNamespace(db=SimpleNamespace(in_transaction=True))
    with pytest.raises(ValueError, match='caller-owned transaction'):
        o.context.clock_advance(1000)
    assert not o.wire.calls and not o.executions and not o.vm.closed


def test_expired_clock_budget_never_attempts_machine_lock(owned):
    o = owned
    class Unavailable:
        def acquire(self, **kwargs):
            pytest.fail('Expired clock budget tried to acquire the machine lock')
    o.vm.lock = Unavailable()
    o.context._rpc_deadline = o.clock.now
    with pytest.raises(TimeoutError, match='before admission'):
        o.context.clock_advance(1000)
    assert not o.wire.calls and not o.executions and not o.vm.closed
