"""Host protocol witnesses for bounded CALL control; no VM or assembler.

The ten-byte guest is the preserved independent DOSBox CALL/INC/RET witness.
The peer supplies declared native outcomes, not an emulator or retirement
oracle. Assertions cover dispatch ownership, first-stop handling and routing.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import threading

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace, stamp
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_machine import MachineContext, MachineDebugSession
from fdisbull.qemu_step_over import FORMAT
from test_qemu_io_public import raw_project
from test_late_tracking_stop import Recorder, owned


GUEST = bytes.fromhex('31c0e8030090ebfe40c3')
BASE, CALL, RETURN, CALLEE, SLOT = 0x20000, 0x20102, 0x20105, 0x20108, 0x2fffc


class Clock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now


class NativeProcess:
    pid = 4711
    def __init__(self): self.returncode = None
    def poll(self): return self.returncode


class Remote:
    architecture = 'i386'

    def __init__(self, machine):
        self.machine = machine
        self.socket = object()
        self.operation_deadline = None
        self.calls, self.requests, self.reads, self.stops = [], [], [], []
        self.reject = None
        self.on_registers = self.on_memory = self.on_request = None

    def registers(self):
        if self.on_registers is not None:
            self.on_registers()
        state = self.machine.state
        return dict(eax=hex(self.machine.ax), esp=hex(self.machine.sp),
            eip=hex(self.machine.pc - int(state['segments']['cs']['base'], 16)),
            cs=state['segments']['cs']['selector'], ss=state['segments']['ss']['selector'])

    def request(self, command, **kwargs):
        self.requests.append(command)
        if self.on_request is not None:
            self.on_request(command)
        if self.reject is not None and command.startswith(self.reject):
            return b'E22'
        return b'OK'

    def memory(self, address, length, *, space):
        assert space == 'physical'
        self.reads.append((address, length))
        if self.on_memory is not None:
            self.on_memory(address, length)
        return bytes(self.machine.ram[address:address + length])

    def execute(self, command, timeout_ms, **kwargs):
        self.calls.append(command)
        assert self.stops, 'Unexpected native continuation'
        row = self.stops.pop(0)
        assert command == row.get('command', 'c')
        self.machine.pc = row.get('pc', RETURN)
        self.machine.sp = row.get('sp', 0xfffe)
        self.machine.ax = row.get('ax', 1)
        if row.get('return_slot', True):
            self.machine.ram[SLOT:SLOT + 2] = b'\x05\x01'
        self.machine.clock.now += row.get('elapsed', 0)
        if row.get('change') is not None:
            row['change'](self.machine)
        return row.get('reply', b'T05thread:01;'), row.get('timed_out', False)


class QMP:
    def __init__(self, machine):
        self.machine, self.socket, self.operation_deadline = machine, object(), None
        self.calls, self.on_call = [], None

    def call(self, command, arguments=None):
        self.calls.append((command, arguments))
        if self.on_call is not None:
            self.on_call(command)
        if command == 'query-status':
            return {'running': False}
        assert command == 'human-monitor-command' and arguments == {'command-line': 'info registers'}
        state = self.machine.state
        control = {name: int(value, 16) for name, value in state['control'].items()}
        if state['cpu_mode'] != 'real': control['CR0'] |= 1
        if state['paging']: control['CR0'] |= 0x80000000
        if state['cpu_mode'] == 'long': control['EFER'] |= 0x400
        ip = self.machine.pc - int(state['segments']['cs']['base'], 16)
        if not state['register_context_match']: ip += 1
        lines = [f'EIP={ip:08x} EFL={0x20002 if state["cpu_mode"]=="v86" else 2:08x} A20={int(state["a20"])}']
        for name in ('cs', 'ss'):
            row = {key: int(value, 16) for key, value in state['segments'][name].items()}
            if state['code_bits' if name=='cs' else 'stack_bits'] == 32: row['attributes'] |= 0x400000
            if name == 'cs' and state['code_bits'] == 64: row['attributes'] |= 0x200000
            lines.append(f'{name.upper()} ={row["selector"]:04x} {row["base"]:08x} {row["limit"]:08x} {row["attributes"]:08x}')
        lines.append(' '.join(f'{name}={value:08x}' for name, value in control.items()))
        return '\n'.join(lines)


class Machine(MachineDebugSession):
    def __init__(self, clock):
        self.clock, self.pc, self.sp, self.ax = clock, CALL, 0xfffe, 0
        self.ram = bytearray(0xa0000)
        self.ram[BASE + 0x100:BASE + 0x100 + len(GUEST)] = GUEST
        self.state = dict(cpu_mode='real', code_bits=16, stack_bits=16,
            paging=False, register_context_match=True, machine_vcpus=1, a20=True,
            segments={name: dict(selector='0x2000', base=hex(BASE), limit='0xffff',
                                attributes='0x9b00' if name=='cs' else '0x9300')
                      for name in ('cs', 'ss')},
            control={'CR0': '0x10', 'CR2': '0x0', 'CR3': '0x0', 'CR4': '0x0', 'EFER': '0x0'})
        process = NativeProcess()
        qmp = QMP(self)
        vm = SimpleNamespace(lock=threading.RLock(), qmp=qmp, gdb=None,
            process=process, machine_stopped=True, qmp_commands=frozenset(),
            machine_configuration={'cpus': 1, 'memory_mib': 32}, closed=False)
        def close():
            vm.closed = True
            vm.qmp = vm.gdb = None
            process.returncode = 0
        vm.close = close
        MachineContext.__init__(self, vm)
        self.remote = Remote(self)
        vm.gdb, vm.context = self.remote, self
        vm.debugger = lambda: self.remote
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
        self.version, self.run_id = {'id': 1}, 'step-over-run'
        self.metadata, self.guest_profile = {'backend': 'qemu-machine'}, None
        self._runtime_epoch = 'epoch-one'
        self.closed = False
        self.events, self.actions = [], []
        self.fail_event, self.persist = None, False

    def _event(self, operation, value):
        self.events.append((operation, deepcopy(value)))
        if operation == self.fail_event:
            raise RuntimeError('authored publication failure')
        if self.persist:
            MachineContext._event(self, operation, value)

    def _layer_spans(self, address, length, space, cs=None):
        address = int(address, 0) if isinstance(address, str) else address
        return address, address, [(address, length)], {'cpu_mode': 'real'}

    def _layer_epoch(self): return self._runtime_epoch

    def write_registers(self, changes):
        assert changes == {'eax': {'expected': self.ax, 'value': self.ax}}
        self.actions.append(deepcopy(changes))
        return self.registers()

    def close(self):
        self.vm.close()
        self.closed = True


@pytest.fixture
def machine(monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock.monotonic)
    return Machine(clock)


def reply(machine, **fields):
    machine.remote.stops.append(fields)


def hook(machine, address):
    return machine.hook(address, space='linear', once=False, max_hits=3,
        actions=[{'op': 'registers', 'registers': {'eax': {'expected': 0, 'value': 0}}}])


def test_call_return_keeps_canonical_breakpoint_and_independent_stack_evidence(machine):
    reply(machine)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['format'] == FORMAT and result['step_over_completed'] is True
    assert result['outcome'] == result['native_result']['outcome'] == 'breakpoint'
    assert result['native_result']['registers']['linear_pc'] == '0x20105'
    assert result['native_result']['registers']['registers']['eax'] == '0x1'
    assert result['after']['sp'] == 0xfffe and result['after']['cs']['selector'] == 0x2000
    assert result['before']['instruction']['bytes'] == 'e80300'
    assert result['before']['return_slot']['expected_hex'] == '0501'
    assert result['instruction_completed'] is None
    assert machine.remote.calls == ['c']
    assert machine.remote.requests == ['Z1,20105,1', 'z1,20105,1']
    assert result['control']['released'] is True and result['control']['disposition'] == 'native-removed'
    assert result['control']['breakpoint_id'].startswith('machine-call-over-')
    assert machine.next_bp == 1
    assert machine.breakpoints == {} and not machine.vm.closed
    assert machine.vm._active_step_over is None and machine._step_over_context is None
    assert [name for name, _ in machine.events] == ['machine-step-over-intent', 'machine-run', 'machine-step-over']
    assert machine.breakpoint(CALLEE)['breakpoint_id'] == 'machine-bp-1'


def test_noncall_next_has_explicit_envelope_and_one_actual_step(machine):
    machine.pc = BASE + 0x100
    reply(machine, command='s', pc=CALL, ax=0, return_slot=False)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['kind'] == 'native-step' and result['step_over_completed'] is True
    assert result['outcome'] == 'step' and result['control'] is None
    assert result['native_result']['session']['stop_reason']['native_reply'] == 'T05thread:01;'
    assert result['instruction_completed'] is None and machine.remote.calls == ['s']
    assert machine.remote.requests == []


def test_default_and_explicit_into_keep_single_and_counted_receipts(machine):
    reply(machine, command='s', pc=CALLEE, sp=0xfffc)
    first = machine.step(timeout_ms=100)
    machine.pc = CALL
    reply(machine, command='s', pc=CALLEE, sp=0xfffc)
    assert machine.step(mode='into', timeout_ms=100) == first
    assert first['outcome'] == 'step' and 'format' not in first
    reply(machine, command='s', pc=CALLEE + 1)
    reply(machine, command='s', pc=RETURN)
    sequence = machine.step(mode='into', count=2, timeout_ms=100)
    assert sequence['format'] == 'fdisbull-machine-step-sequence-1'
    assert sequence['complete'] and sequence['completed_count'] == 2
    assert machine.remote.requests == [] and machine.remote.calls == ['s'] * 4


@pytest.mark.parametrize('parameters', [
    {'mode': None}, {'mode': True}, {'mode': 'OVER'}, {'mode': 'out'},
    {'mode': 'over', 'count': 2}, {'mode': 'over', 'count': 0},
    {'mode': 'over', 'count': True}, {'mode': 'over', 'timeout_ms': 0},
    {'mode': 'over', 'timeout_ms': True},
])
def test_bad_parameters_refuse_before_lock_guard_or_observation(machine, parameters):
    machine.vm.operation_guard = lambda name: pytest.fail('invalid parameters reached a guard')
    with pytest.raises(ValueError): machine.step(**parameters)
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []
    assert not machine.vm.closed


@pytest.mark.parametrize('code', [
    '9a08010020', 'ffd0', 'ff1e2001', '66e803000000', '2ee80300',
    'ebfe', 'c3', 'cd21', 'cf', 'f3a4', 'f2ae', 'f4', '66' * 15,
    'e80080', 'e8feff', 'e80000',
])
def test_unsupported_decode_or_return_target_refuses_without_dispatch(machine, code):
    raw = bytes.fromhex(code)
    machine.ram[CALL:CALL + len(raw)] = raw
    with pytest.raises(ValueError): machine.step(mode='over', timeout_ms=100)
    assert machine.remote.calls == machine.remote.requests == [] and not machine.vm.closed
    assert machine.vm._active_step_over is None and machine._step_over_context is None
    assert machine.events == []


@pytest.mark.parametrize(('field', 'value'), [
    ('cpu_mode', 'protected'), ('code_bits', 32), ('stack_bits', 32),
    ('paging', True), ('register_context_match', False), ('machine_vcpus', 2),
])
def test_unqualified_cpu_context_refuses_before_arm(machine, field, value):
    machine.state[field] = value
    if field == 'machine_vcpus': machine.vm.machine_configuration['cpus'] = value
    with pytest.raises(ValueError): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


@pytest.mark.parametrize('change', [
    lambda m: setattr(m, 'sp', 1),
    lambda m: setattr(m, 'sp', 0x10000),
    lambda m: m.state['segments']['ss'].update(base='0x40000'),
    lambda m: m.state['segments']['cs'].update(limit='0xffffffff'),
    lambda m: setattr(m, 'pc', BASE + 0xfffe),
])
def test_segment_stack_and_decode_boundaries_refuse_before_arm(machine, change):
    change(machine)
    if machine.pc == BASE + 0xfffe:
        machine.ram[machine.pc:machine.pc + 3] = b'\xe8\x03\x00'
    with pytest.raises(ValueError): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == []


@pytest.mark.parametrize('change', [
    lambda m: setattr(m, 'sp', 0xfffc),
    lambda m: m.state['segments']['ss'].update(selector='0x2100', base='0x21000'),
    lambda m: m.ram.__setitem__(CALL, 0x90),
    lambda m: m.ram.__setitem__(RETURN, 0x91),
    lambda m: m.ram.__setitem__(SLOT, 0),
    lambda m: m.state.update(cpu_mode='protected'),
])
def test_wrong_return_identity_preserves_first_stop_and_never_retries(machine, change):
    reply(machine, change=change)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['step_over_completed'] is False and result['reason']
    assert result['outcome'] == result['native_result']['outcome'] == 'breakpoint'
    assert result['control']['released'] is True and not machine.vm.closed
    assert machine.remote.calls == ['c'] and not machine.breakpoints


def test_changed_source_allocation_at_return_is_incomplete_not_another_run(machine, monkeypatch):
    identity = dict(capture_epoch='epoch-one', allocation={'start': BASE, 'end': BASE + 0x10000},
        source_mapping={'live_ranges': [{'runtime_address': BASE + 0x100, 'length': len(GUEST)}]})
    monkeypatch.setattr('fdisbull.qemu_step_over._source', lambda session, context: deepcopy(identity))
    reply(machine, change=lambda m: identity.update(capture_epoch='retired'))
    result = machine.step(mode='over', timeout_ms=100)
    assert not result['step_over_completed'] and 'source/allocation' in result['reason']
    assert machine.remote.calls == ['c'] and result['control']['released']


@pytest.mark.parametrize('kind', ['breakpoint', 'watchpoint', 'hook'])
def test_first_user_or_hook_stop_wins_and_keeps_its_control(machine, kind):
    if kind == 'hook':
        control = hook(machine, CALLEE)
        identifier = control['breakpoint_id']
    else:
        identifier = machine.breakpoint(CALLEE if kind=='breakpoint' else SLOT,
            access='x' if kind=='breakpoint' else 'w', length=1 if kind=='breakpoint' else 2)['breakpoint_id']
    reply(machine, pc=CALL if kind=='watchpoint' else CALLEE, sp=0xfffc, ax=0,
          reply=b'T05thread:01;watch:2fffc;' if kind=='watchpoint' else b'T05thread:01;')
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == kind and not result['step_over_completed']
    assert result['native_result']['session']['stop_reason']['breakpoint_ids'] == [identifier]
    assert identifier in machine.breakpoints and len(machine.breakpoints) == 1
    assert machine.remote.calls == ['c'] and not machine.vm.closed
    assert len(machine.actions) == (1 if kind=='hook' else 0)


def test_pending_entry_hook_displaces_the_actual_call_then_continues_to_return(machine):
    control = hook(machine, CALL)
    reply(machine, pc=CALL, sp=0xfffe, ax=0, return_slot=False)
    first = machine.run(timeout_ms=100, stop_on_hook=True)
    assert first['outcome'] == 'hook' and machine._qemu_hook_pending == control['hook']
    reply(machine, command='s', pc=CALLEE, sp=0xfffc, ax=0)
    reply(machine)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == 'breakpoint' and result['step_over_completed']
    assert result['native_result']['session']['stop_reason']['native_reply'] == 'T05thread:01;'
    assert result['native_result']['hook_hits'] == []
    assert machine.remote.calls == ['c', 's', 'c'] and len(machine.actions) == 1
    assert len(machine.hooks()['hooks']) == 1 and len(machine.breakpoints) == 1


@pytest.mark.parametrize('kind', ['user', 'hook', 'tracker'])
def test_fallthrough_alias_is_preserved_and_is_not_exclusive_own_completion(machine, kind):
    if kind == 'hook':
        identifier = hook(machine, RETURN)['breakpoint_id']
    elif kind == 'tracker':
        machine._automatic_runtime_tracker = Recorder()
        identifier = owned(machine, RETURN)
    else:
        identifier = machine.breakpoint(RETURN)['breakpoint_id']
    original = deepcopy(machine.breakpoints[identifier])
    reply(machine)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == 'breakpoint' and not result['step_over_completed']
    if kind == 'tracker':
        assert result['native_result']['automatic_breakpoints'] == [identifier]
        assert result['native_result']['session']['stop_reason']['breakpoint_ids'] == [result['control']['breakpoint_id']]
    else:
        assert identifier in result['native_result']['session']['stop_reason']['breakpoint_ids']
    assert machine.breakpoints == {identifier: original}
    assert machine.remote.requests == ['Z1,20105,1']
    assert result['control']['disposition'] == 'alias-preserved'
    assert machine.remote.calls == ['c'] and machine.actions == []


@pytest.mark.parametrize('owner', ['_active_video_frame_fence', '_active_frame_fence', '_active_clock_budget', '_active_step_over'])
def test_existing_execution_owner_refuses_step_over_before_any_io(machine, owner):
    setattr(machine.vm, owner, {'token': 'existing'})
    machine.vm.operation_guard = lambda name: pytest.fail('conflict reached a later guard')
    with pytest.raises(ValueError): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


@pytest.mark.parametrize('scheduled', [False, True])
def test_call_continue_never_consumes_queued_or_scheduled_input(machine, scheduled):
    state = machine._input_storage()
    state['pending'] = [] if scheduled else [{'authored': 'unconsumed-edge'}]
    if scheduled: state['schedule'] = {'bound': True}
    original = deepcopy(state)
    with pytest.raises(ValueError, match='input'): machine.step(mode='over')
    assert state == original and machine.remote.calls == machine.remote.requests == []


def test_selected_undo_freeze_uses_existing_operation_guard(machine):
    from fdisbull.qemu_cpu_undo_guard import before_operation
    machine._qemu_cpu_delta_history = {'valid': False, 'frozen': True}
    machine.vm.history_operation_guard = lambda name, args, kwargs: before_operation(machine, name, args, kwargs)
    with pytest.raises(ValueError, match='frozen'): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


@pytest.mark.parametrize('field', ['_layer_active', '_layer_exec', '_dos_task_binding', '_dos_task_monitor', '_dos_scheduler', '_le_source'])
def test_active_nonordinary_view_refuses_before_observation(machine, field):
    setattr(machine, field, {'authored': 'active'})
    with pytest.raises(ValueError, match='ordinary RAM'): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


def test_active_clock_sync_refuses_before_observation(machine):
    machine.vm._clock_sync = {'state': 'active'}
    with pytest.raises(ValueError, match='synchronization'): machine.step(mode='over')
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


@pytest.mark.parametrize('operation', ['clock', 'clock-sync', 'renderer', 'source', 'source-start', 'source-stop', 'input', 'schedule', 'checkpoint', 'undo', 'step', 'run'])
def test_active_step_over_refuses_other_controller_order_before_dispatch(machine, operation):
    from fdisbull.qemu_cpu_undo_runtime import _admission
    from fdisbull.qemu_dos_frames import QemuDOSFramesMixin
    machine.vm._active_step_over = {'token': 'owned-call'}
    actions = {
        'clock': lambda: machine.clock_advance(1, timeout_ms=100),
        'clock-sync': lambda: machine.clock_sync_start(timeout_ms=100),
        'renderer': lambda: QemuDOSFramesMixin._frame_execute(machine, {}, 'not-armed'),
        'source': lambda: machine.video_frame_advance(timeout_ms=100),
        'source-start': lambda: machine.video_frame_start(timeout_ms=100),
        'source-stop': lambda: machine.video_frame_stop(timeout_ms=100),
        'input': machine._input_prepare,
        'schedule': lambda: machine._input_prepare(allow_schedule=True),
        'checkpoint': machine._checkpoint_preflight,
        'undo': lambda: _admission(machine),
        'step': lambda: machine.step(),
        'run': lambda: machine.run(timeout_ms=100),
    }
    with pytest.raises(ValueError, match='step-over'): actions[operation]()
    assert machine.remote.calls == machine.remote.requests == machine.remote.reads == []


@pytest.mark.parametrize('stage', ['intent', 'arm', 'cleanup', 'publish'])
def test_uncertain_control_or_publication_closes_original_owner_and_keeps_receipt(machine, stage):
    if stage in ('intent', 'publish'):
        machine.fail_event = 'machine-step-over-intent' if stage=='intent' else 'machine-step-over'
    if stage in ('arm', 'cleanup'):
        machine.remote.reject = 'Z' if stage=='arm' else 'z'
    reply(machine)
    original = machine.vm
    with pytest.raises((RuntimeError, DebuggerError)) as caught:
        machine.step(mode='over', timeout_ms=100)
    evidence = caught.value.result
    assert evidence['format'] == FORMAT and evidence['owner']['native_pid'] == 4711
    assert evidence['step_over_completed'] is False and original.closed
    assert original._active_step_over is None
    if stage in ('cleanup', 'publish'):
        assert evidence['native_result']['outcome'] == 'breakpoint'
        assert machine.remote.calls == ['c']
    else:
        assert machine.remote.calls == []


def test_deadline_after_arrived_return_retains_native_stop_without_late_cleanup(machine):
    reply(machine, elapsed=0.101)
    with pytest.raises(TimeoutError) as caught:
        machine.step(mode='over', timeout_ms=100)
    native = caught.value.result['native_result']
    assert native['session']['stop_reason']['native_reply'] == 'T05thread:01;'
    assert native['session']['stop_reason']['classification_complete'] is False
    assert native['registers'] is None
    assert machine.remote.calls == ['c'] and machine.remote.requests == ['Z1,20105,1']
    assert machine.vm.closed


@pytest.mark.parametrize(('pc', 'sp', 'packet'), [
    (CALLEE, 0xfffc, b'T02thread:01;'), (RETURN, 0xfffe, b'S02'),
])
def test_known_early_timeout_keeps_native_timeout_and_releases_control_within_original_budget(machine, pc, sp, packet):
    reply(machine, pc=pc, sp=sp, reply=packet, timed_out=True, elapsed=0.01)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == 'timeout' and result['timed_out'] is True
    assert result['native_result']['session']['stop_reason']['native_reply'] == packet.decode('ascii')
    assert not result['step_over_completed'] and result['control']['released']
    assert not machine.vm.closed and machine.remote.calls == ['c']


@pytest.mark.parametrize('where', ['status', 'registers', 'memory', 'before-execution',
                                   'after-stop', 'internal-stop', 'delete-guard',
                                   'delete-reply', 'native-publication', 'publication'])
def test_callback_owner_swaps_never_read_execute_close_or_unlock_the_replacement(machine, where):
    original = machine.vm
    replacement = Machine(machine.clock)
    replacement_qmp = replacement.vm.qmp
    def swap(): machine.vm = replacement.vm
    if where == 'status':
        original.qmp.on_call = lambda command: swap() if command=='query-status' else None
    elif where == 'registers': machine.remote.on_registers = swap
    elif where == 'memory': machine.remote.on_memory = lambda address, length: swap()
    elif where in ('before-execution', 'after-stop', 'internal-stop'):
        tracker = Recorder()
        machine._automatic_runtime_tracker = tracker
        if where == 'before-execution': tracker.before_execution = lambda reason: swap()
        elif where == 'after-stop': tracker.after_stop = lambda reason: swap()
        else:
            owned(machine, CALLEE)
            tracker.internal_stop = lambda reason: (swap() or True)
    elif where == 'delete-guard':
        original.operation_guard = lambda name: swap() if name=='delete_breakpoint' else None
    elif where == 'delete-reply':
        machine.remote.on_request = lambda command: swap() if command.startswith('z') else None
    else:
        event = machine._event
        target = 'machine-run' if where=='native-publication' else 'machine-step-over'
        def publish(operation, value):
            event(operation, value)
            if operation == target: swap()
        machine._event = publish
    reply(machine, pc=CALLEE if where=='internal-stop' else RETURN)
    with pytest.raises(DebuggerError, match='original owner') as caught:
        machine.step(mode='over', timeout_ms=100)
    result = caught.value.result
    assert result['format'] == FORMAT and result['owner']['native_pid'] == 4711
    assert not result['step_over_completed'] and original.closed
    assert not replacement.vm.closed
    assert replacement.remote.calls == replacement.remote.reads == replacement.remote.requests == []
    assert replacement_qmp.calls == []
    assert original._active_step_over is None and machine._step_over_context is None
    before_dispatch = where in ('status', 'registers', 'memory', 'before-execution')
    assert machine.remote.calls == ([] if before_dispatch else ['c'])
    if not before_dispatch:
        assert result['native_result']['session']['stop_reason']['native_reply'] == 'T05thread:01;'


@pytest.mark.parametrize('where', ['registers', 'memory', 'short-memory'])
def test_initial_transport_uncertainty_keeps_original_identity_and_closes_without_dispatch(machine, where):
    def fail(*args): raise ValueError('authored native observation failure')
    if where == 'registers': machine.remote.on_registers = fail
    elif where == 'memory': machine.remote.on_memory = fail
    else: machine.remote.memory = lambda *args, **kwargs: b''
    with pytest.raises((ValueError, DebuggerError)) as caught:
        machine.step(mode='over', timeout_ms=100)
    result = caught.value.result
    assert result['failure_stage'] == 'admission' and result['native_result'] is None
    assert result['owner']['native_pid'] == 4711 and result['before'] is None
    assert machine.vm.closed and machine.remote.calls == machine.remote.requests == []


def test_runtime_epoch_change_closes_without_retry_and_keeps_actual_stop(machine):
    reply(machine, change=lambda m: setattr(m, '_runtime_epoch', 'new-epoch'))
    with pytest.raises(DebuggerError, match='owner or source epoch') as caught:
        machine.step(mode='over', timeout_ms=100)
    native = caught.value.result['native_result']
    assert native['outcome'] == 'stopped' and native['registers'] is None
    assert native['session']['stop_reason']['classification_complete'] is False
    assert native['session']['stop_reason']['native_reply'] == 'T05thread:01;'
    assert machine.vm.closed and machine.remote.calls == ['c']


def test_shorter_displaced_step_deadline_cannot_grant_call_a_control_repair_grace(machine):
    tracker = Recorder()
    tracker.internal_stop = lambda result: False
    machine._automatic_runtime_tracker = tracker
    owned(machine, CALL)
    reply(machine, pc=CALL, sp=0xfffe, ax=0, return_slot=False)
    first = machine.run(timeout_ms=100)
    assert first['outcome'] == 'breakpoint' and machine._automatic_internal_pending
    event = machine._event
    def publish(operation, value):
        event(operation, value)
        if operation == 'machine-step-over-intent': machine.clock.now = 0.0004
    machine._event = publish
    # The inherited 100 ms deadline still has 1.1 ms. The child run received
    # floor(99.6) ms, so its 99.4 ms deadline has only 0.5 ms: no fresh Z/grace.
    def after_suspend(command):
        if command == 'z1,20102,1': machine.clock.now = 0.0989
    machine.remote.on_request = after_suspend
    with pytest.raises(DebuggerError) as caught:
        machine.step(mode='over', timeout_ms=100)
    result = caught.value.result
    assert result['format'] == FORMAT and not result['step_over_completed']
    assert result['native_result']['session']['stop_reason']['native_reply'] == 'T05thread:01;'
    assert machine.remote.calls == ['c']
    assert machine.remote.requests == ['Z1,20102,1', 'Z1,20105,1', 'z1,20102,1']
    assert machine.vm.closed


def test_post_execute_owner_replacement_never_reads_or_closes_the_replacement(machine):
    original, native = machine.vm, machine._execute
    replacement = SimpleNamespace(qmp=object(), gdb=None, process=NativeProcess(), closed=False)
    replacement.close = lambda: setattr(replacement, 'closed', True)
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        machine.vm = replacement
        return result
    machine._execute = execute
    reply(machine)
    with pytest.raises(DebuggerError, match='owner or source epoch') as caught:
        machine.step(mode='over', timeout_ms=100)
    assert caught.value.result['owner']['native_pid'] == 4711
    assert caught.value.result['native_result']['outcome'] == 'breakpoint'
    assert original.closed and not replacement.closed
    assert machine.remote.calls == ['c']


def test_native_exit_preserves_actual_packet_and_reaps_temporary_control(machine):
    reply(machine, reply=b'W00')
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == 'exited' and result['owner_exited'] is True
    assert not result['step_over_completed'] and result['after'] is None
    assert result['native_result']['session']['stop_reason']['native_reply'] == 'W00'
    assert result['control']['disposition'] == 'owner-reaped'
    assert not machine.breakpoints and machine.vm.closed and machine.remote.calls == ['c']


@pytest.mark.parametrize(('outcome', 'state'), [('guest_exit', 'exited'), ('guest_tsr', 'resident')])
def test_live_dos_return_preserves_canonical_outcome_and_cleans_original_control(machine, outcome, state):
    native = machine._execute
    def execute(command, timeout_ms):
        result = native(command, timeout_ms)
        result['native_machine_stop'] = deepcopy(result['session']['stop_reason'])
        result['outcome'] = outcome
        result['session']['stop_reason'] = {'kind': outcome, 'breakpoint_ids': []}
        result['process'] = {'state': state, 'termination': {'code': 0}}
        machine._runtime_epoch = 'process-ended'
        # The real DOS adapter advances the source epoch after its validated
        # helper report, then performs nested stopped cleanup before returning.
        from fdisbull.qemu_step_over import observe_step_over_guest_return
        observe_step_over_guest_return(machine, result)
        assert machine.registers() == result['registers']
        return result
    machine._execute = execute
    reply(machine, pc=0x20300)
    result = machine.step(mode='over', timeout_ms=100)
    assert result['outcome'] == outcome and result['native_result']['process']['state'] == state
    assert not result['step_over_completed'] and not result['owner_exited']
    assert not machine.vm.closed and result['control']['released']
    assert machine.remote.calls == ['c']


@pytest.fixture
def public_machine(machine, raw_project):
    machine.project, machine.version, machine.persist = raw_project, raw_project.version(), True
    with raw_project.transaction(True):
        raw_project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (machine.run_id, machine.version['id'], stamp(), None, 'stopped', json.dumps(machine.metadata)))
    return machine


def test_json_routes_one_call_and_preserves_public_and_persisted_native_outcome(public_machine):
    machine = public_machine
    workspace = DebugWorkspace()
    workspace.sessions[machine.run_id] = machine
    reply(machine)
    result = respond({'id': 1, 'method': 'debug-step', 'params': {
        'project': str(machine.project.path), 'run': machine.run_id, 'mode': 'over', 'timeout_ms': 100}}, debugger=workspace)
    workspace.sessions.clear()
    assert result['ok'] and result['result']['format'] == FORMAT
    assert result['result']['outcome'] == result['result']['native_result']['outcome'] == 'breakpoint'
    stored = machine.project.db.execute("SELECT evidence FROM debug_events WHERE operation='machine-step-over'").fetchone()
    assert json.loads(stored['evidence'])['step_over_completed'] is True
    assert machine.remote.calls == ['c']


def test_json_late_publication_failure_retains_full_actual_return_and_original_owner(public_machine):
    machine = public_machine
    workspace = DebugWorkspace()
    workspace.sessions[machine.run_id] = machine
    machine.fail_event = 'machine-step-over'
    reply(machine)
    result = respond({'id': 2, 'method': 'debug-step', 'params': {
        'project': str(machine.project.path), 'run': machine.run_id, 'mode': 'over', 'timeout_ms': 100}}, debugger=workspace)
    workspace.sessions.clear()
    assert not result['ok'] and result['error']['type'] == 'RuntimeError'
    retained = result['error']['result']
    assert retained['native_result']['outcome'] == 'breakpoint'
    assert retained['owner']['native_pid'] == 4711 and retained['control']['released']
    assert machine.vm.closed and machine.remote.calls == ['c']


def test_script_accepts_owned_breakpoint_completion_and_result_reference(public_machine):
    machine = public_machine
    reply(machine)
    result = execute_script(machine, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': [
        {'op': 'step', 'mode': 'over', 'timeout_ms': 100, 'as': 'call'},
        {'op': 'assert', 'value': '$call.step_over_completed', 'equals': True},
        {'op': 'assert', 'value': '$call.outcome', 'equals': 'breakpoint'},
    ]})
    assert result['ok'] and result['completed_steps'] == 3 and machine.remote.calls == ['c']


def test_script_keeps_interrupted_native_result_and_does_not_execute_next_step(public_machine):
    machine = public_machine
    point = machine.breakpoint(CALLEE)['breakpoint_id']
    reply(machine, pc=CALLEE)
    result = execute_script(machine, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': [
        {'op': 'step', 'mode': 'over', 'timeout_ms': 100}, {'op': 'step'},
    ]})
    assert not result['ok'] and len(result['steps']) == 1
    assert result['steps'][0]['result']['native_result']['session']['stop_reason']['breakpoint_ids'] == [point]
    assert machine.remote.calls == ['c']


@pytest.mark.parametrize('backend', ['qemu-machine', 'qemu-dos'])
def test_saved_script_rejects_bad_later_mode_count_before_any_execution(backend):
    with pytest.raises(ValueError, match='count=1'):
        validate_script({'format': 'fdisbull-script-1', 'backend': backend, 'steps': [
            {'op': 'step'}, {'op': 'step', 'mode': 'over', 'count': 2},
        ]})


def test_invalid_literal_mode_cannot_hide_behind_a_count_reference(public_machine):
    machine = public_machine
    with pytest.raises(ValueError, match='mode'):
        execute_script(machine, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': [
            {'op': 'step', 'count': 2, 'as': 'previous'},
            {'op': 'step', 'mode': 'invalid', 'count': '$previous.completed_count'},
        ]})
    assert machine.remote.calls == machine.remote.requests == []


def test_explicit_script_into_keeps_the_existing_counted_adapter(public_machine):
    machine = public_machine
    reply(machine, command='s', pc=CALLEE, sp=0xfffc)
    reply(machine, command='s', pc=CALLEE + 1, sp=0xfffc)
    result = execute_script(machine, {'format': 'fdisbull-script-1', 'backend': 'qemu-machine', 'steps': [
        {'op': 'step', 'mode': 'into', 'count': 2, 'timeout_ms': 100},
    ]})
    assert result['ok'] and result['steps'][0]['result']['completed_count'] == 2
    assert machine.remote.calls == ['s', 's'] and machine.remote.requests == []
