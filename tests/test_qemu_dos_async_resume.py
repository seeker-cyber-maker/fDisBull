"""Public DOS asynchronous controls against authored native-boundary peers.

The project, process observation, helper protocol and persistence are real.
QMP, GDB and UART are the replaced boundaries. Authored tracker callbacks
exercise nested public controls; these tests do not qualify native QEMU
timing or DOS execution.
"""
from copy import deepcopy
import json
import struct
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull import dos_process_helper as helper
from fdisbull.debugger import stamp
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull.qemu_machine import MachineContext


class NativePeer:
    architecture = 'i386'

    def __init__(self):
        self.socket = object()
        self.operation_deadline = None
        self.running, self.runstate = False, 'paused'
        self.cs, self.ip, self.ss, self.sp = 0x2000, 0x100, 0x2000, 0xfffe
        self.ram = bytearray(0x100000)
        self.commands, self.requests, self.reads = [], [], []
        self.points = set()
        self.closed = 0
        self.on_continue = self.on_query = self.on_memory = self.on_monitor = None

    def call(self, command, arguments=None, **kwargs):
        self.commands.append((command, deepcopy(arguments), self.operation_deadline))
        if command == 'cont':
            self.running, self.runstate = True, 'running'
            if self.on_continue:
                self.on_continue()
            return {}
        if command == 'stop':
            self.running, self.runstate = False, 'paused'
            return {}
        if command == 'query-status':
            if self.on_query:
                self.on_query()
            return dict(running=self.running, status=self.runstate, singlestep=False)
        assert command == 'human-monitor-command'
        assert arguments == {'command-line': 'info registers'}
        if self.on_monitor:
            self.on_monitor()
        return (f'EIP={self.ip:08x} EFL=00000202 A20=1\n'
                f'CS ={self.cs:04x} {self.cs*16:08x} 0000ffff 00009b00\n'
                f'SS ={self.ss:04x} {self.ss*16:08x} 0000ffff 00009300\n'
                'CR0=00000000 CR2=00000000 CR3=00000000 CR4=00000000 EFER=00000000\n'
                'GDT= 00000000 00000000\n')

    def registers(self):
        assert not self.running, 'A running vCPU was inspected'
        return dict(cs=hex(self.cs), eip=hex(self.ip), ss=hex(self.ss), esp=hex(self.sp),
                    eax='0x0', ebx='0x0', eflags='0x202')

    def memory(self, address, length, *, space='virtual', timeout_ms=5000):
        assert not self.running and space in ('physical', 'virtual')
        assert 0 < timeout_ms <= 30000
        self.reads.append((address, length, space, self.operation_deadline))
        data = bytes(self.ram[address:address+length])
        if self.on_memory:
            self.on_memory(address, length)
        return data

    def request(self, command, **kwargs):
        self.requests.append(command)
        assert command[:1] in ('Z', 'z'), 'Unexpected GDB query or execution: ' + command
        point = tuple(int(value, 16) for value in command[1:].split(','))
        if command.startswith('Z'):
            self.points.add(point)
        else:
            assert point in self.points
            self.points.remove(point)
        return b'OK'

    def execute(self, *args, **kwargs):
        pytest.fail('Asynchronous control attempted GDB run/step')

    def close(self):
        self.closed += 1
        self.socket = None
        self.points.clear()


class SerialPeer:
    def __init__(self):
        self.data = bytearray()
        self.timeouts, self.reads = [], 0

    def settimeout(self, timeout):
        assert 0 < timeout <= 30
        self.timeouts.append(timeout)

    def recv(self, length):
        self.reads += 1
        if not self.data:
            raise TimeoutError('Authored missing UART termination report')
        data = bytes(self.data[:length])
        del self.data[:length]
        return data


@pytest.fixture
def owned(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'SMALL.COM'
    source.write_bytes(bytes.fromhex('90b8254ccd21'))
    with Project.create(tmp_path / 'small.fdb', source, image='com') as project:
        s = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
        p, uart = NativePeer(), SerialPeer()
        closed = []
        vm = SimpleNamespace(lock=threading.RLock(), qmp=p, gdb=p,
            transport='unix', machine_stopped=True, operation_deadline=None,
            machine_configuration=dict(memory_mib=16, cpus=1),
            process=SimpleNamespace(poll=lambda: 0 if closed else None),
            debugger=lambda: p)
        def close():
            closed.append(True)
            vm.qmp = vm.gdb = None
            if s.vm is vm:
                s._on_machine_closed()
        vm.close = close
        MachineContext.__init__(s, vm)
        vm.context = s
        s.rpc, s.project, s.version, s.run_id = vm, project, project.version(), 'async-run'
        s.closed, s._launching, s._deadline = False, False, None
        s._staging, s._dos_workspace_enabled = None, False
        s._nonce = b'async-nonce-0001'
        s._helper = helper.build_loader('SMALL.COM', b'', s._nonce)
        raw = bytearray(s._helper[4:4+helper.REPORT_SIZE])
        raw[5] = helper.READY
        fields = dict(helper_segment=0x1800, helper_psp=0x1800, child_psp=0x2000,
            entry_cs=0x2000, entry_ip=0x100, stack_ss=0x2000, stack_sp=0xfffe,
            raw_stack_sp=0xfffc, first_mcb_segment=0x1000, dos_version=7)
        for key, value in fields.items():
            struct.pack_into('<H', raw, helper.REPORT_FIELDS[key], value)
        s._ready_bytes = bytes(raw)
        s._ready = helper.parse_report(s._ready_bytes, s._nonce)
        s._channel, s._serial_buffer = uart, bytearray()
        s._runtime_epoch, s._epoch_number = 'async-run:process:1', 1
        s._checkpoint_entry_clean, s._published = True, True
        s._owned_machine_restored = False
        s._process = dict(state='active', psp_segment=0x2000, parent_psp_segment=0x1800,
            capture_epoch=s._runtime_epoch, termination=None,
            source_mapping=dict(live=True, status='initial-load-verified', runtime_base=0x20100,
                static_base=project.regions(1)[0].start, module_size=source.stat().st_size,
                live_ranges=[dict(runtime_address=0x20100, project_address=project.regions(1)[0].start,
                                  length=source.stat().st_size)]))
        s.metadata = dict(backend='qemu-dos', source_sha256=project.meta['source_sha256'],
            version_sha256=s.version['sha256'], process=deepcopy(s._process))
        s._vectors_before = bytes(1024)
        p.ram[0x18100:0x18100+len(s._helper)] = s._helper
        report_address = 0x18000+s._ready['report_offset']
        p.ram[report_address:report_address+helper.REPORT_SIZE] = s._ready_bytes
        # One valid, coalesced free block proves no child allocation remains.
        struct.pack_into('<BHH', p.ram, 0x10000, ord('Z'), 0, 0x7000)
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (s.run_id, s.version['id'], stamp(), None, 'stopped', json.dumps(s.metadata)))
        s._return_breakpoint = MachineContext.breakpoint(
            s, 0x18000+s._ready['exit_wait_ip'])['breakpoint_id']
        def finish(*, code=37, category=0, serial=True):
            terminated = bytearray(s._ready_bytes)
            terminated[5] = helper.TERMINATED
            struct.pack_into('<H', terminated, helper.REPORT_FIELDS['dos_result'], code | category << 8)
            p.ram[report_address:report_address+helper.REPORT_SIZE] = terminated
            if serial:
                uart.data.extend(terminated)
            p.cs, p.ip = 0x1800, s._ready['exit_wait_ip']
            p.running, p.runstate = False, 'debug'
        p.commands.clear(); p.requests.clear(); p.reads.clear()
        yield SimpleNamespace(session=s, peer=p, serial=uart, project=project,
                              vm=vm, closed=closed, finish=finish, report_address=report_address)


def dispatches(peer):
    return [command for command, _, _ in peer.commands if command in ('cont', 'stop')]


@pytest.mark.parametrize('transport', ['unix', 'pipe'])
def test_private_return_control_survives_resume_and_exactly_one_pause(owned, transport):
    s, p = owned.session, owned.peer
    owned.vm.transport = transport
    points, next_id = deepcopy(s.breakpoints), s.next_bp
    assert s.resume()['state'] == 'running'
    assert not s._checkpoint_entry_clean
    assert s.breakpoints == points and s.next_bp == next_id
    assert len(p.points) == 1 and p.closed == 0 and owned.vm.gdb is p
    stopped = s.pause()
    assert stopped['state'] == 'stopped' and stopped['native_state']['status'] == 'paused'
    assert stopped['process']['state'] == 'active' and 'process_stop' not in stopped
    assert s.status() == stopped == s.status()
    assert dispatches(p) == ['cont', 'stop']
    assert not p.requests and not owned.closed


def test_stop_enrichment_returns_current_tracking_and_preserves_callback_controls(owned):
    s, p = owned.session, owned.peer
    payload = bytes.fromhex('90b8254ccd21')
    p.ram[0x20100:0x20100+len(payload)] = payload
    state = dict(state='initial', observations=0, controls=[])
    observations = []
    private = s._return_breakpoint

    def before(reason):
        for identifier in list(state['controls']):
            s.delete_breakpoint(identifier)
        state.update(state='running', controls=[])

    def after(reason):
        assert s.vm is owned.vm and owned.vm.machine_stopped and not p.running
        registers = s.registers()
        memory = s.memory(0x20100, length=len(payload))
        snapshot = s.memory_snapshot(0x20100, length=len(payload), space='physical')
        observations.append((registers, memory, snapshot))
        temporary = s.breakpoint(0x20200)['breakpoint_id']
        assert s.breakpoints[temporary]['owner'] == 'automatic-runtime-tracking'
        s.delete_breakpoint(temporary)
        assert temporary not in s.breakpoints and (1, 0x20200, 1) not in p.points
        retained = s.breakpoint(0x20201)['breakpoint_id']
        assert s.breakpoints[retained]['owner'] == 'automatic-runtime-tracking'
        state.update(state='qualified-stopped', observations=len(observations), controls=[retained])

    s._automatic_runtime_tracker = SimpleNamespace(before_execution=before, after_stop=after,
        status=lambda: deepcopy(state), close=lambda reason: state.update(state='closed'))
    assert s.resume()['automatic_runtime_tracking']['state'] == 'running'
    stopped = s.pause()
    assert stopped['automatic_runtime_tracking'] == state
    assert stopped['automatic_runtime_tracking']['observations'] == 1
    assert stopped == s.status() == s.status()
    registers, memory, snapshot = observations[0]
    assert registers['linear_pc'] == '0x20100' and memory['hex'] == payload.hex()
    stored = owned.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                     (snapshot['artifact'],)).fetchone()
    assert bytes(stored[0]) == payload
    assert private in s.breakpoints and len(p.points) == 2
    retained = state['controls'][0]
    assert s.resume()['state'] == 'running'
    assert retained not in s.breakpoints and len(p.points) == 1
    second = s.pause()
    assert second['automatic_runtime_tracking']['observations'] == 2
    assert second == s.status() and len(observations) == 2
    assert dispatches(p) == ['cont', 'stop', 'cont', 'stop'] and not owned.closed


@pytest.mark.parametrize('operation', ['status', 'pause', 'resume', 'dos_process_info',
                                      'run', 'step', 'write_memory', 'delete-private', 'close'])
def test_stop_enrichment_refuses_recursive_observation_and_execution(owned, operation):
    s, p = owned.session, owned.peer
    observed = []
    actions = dict(status=s.status, pause=s.pause, resume=s.resume, dos_process_info=s.dos_process_info,
        run=lambda: s.run(timeout_ms=100), step=lambda: s.step(timeout_ms=100),
        write_memory=lambda: s.write_memory(0x20100, 'cc', expected_hex='00'), close=s.close)
    actions['delete-private'] = lambda: MachineContext.delete_breakpoint(s, s._return_breakpoint)

    def after(reason):
        before = len(p.commands), len(p.requests), len(p.reads)
        with pytest.raises(ValueError, match='stop enrichment'):
            actions[operation]()
        assert before == (len(p.commands), len(p.requests), len(p.reads))
        observed.append(reason)

    s._automatic_runtime_tracker = SimpleNamespace(before_execution=lambda reason: None, after_stop=after,
        status=lambda: dict(observations=len(observed)), close=lambda reason: None)
    s.resume()
    result = s.pause()
    assert result['automatic_runtime_tracking'] == dict(observations=1)
    assert result == s.status() and len(observed) == 1
    assert dispatches(p) == ['cont', 'stop'] and not owned.closed


@pytest.mark.parametrize(('operation', 'boundary'), [('registers', 'before-read'),
    ('memory', 'before-read'), ('clock_observe', 'before-read'),
    ('registers', 'native-reply'), ('memory', 'native-reply')])
def test_stop_enrichment_owner_change_cannot_touch_replacement(owned, operation, boundary):
    s, p = owned.session, owned.peer
    replacement_peer = NativePeer()
    replacement_locks, replacement_closed, delivered = [], [], []
    replacement = SimpleNamespace(qmp=replacement_peer, gdb=replacement_peer,
        operation_deadline=123, machine_configuration=dict(memory_mib=16, cpus=1),
        lock=SimpleNamespace(acquire=lambda **kw: replacement_locks.append('acquire') or True,
                             release=lambda: replacement_locks.append('release')),
        close=lambda: replacement_closed.append(True))
    actions = dict(registers=s.registers, memory=lambda: s.memory(0x20100, length=1),
                   clock_observe=s.clock_observe)

    def replace(*args):
        s.vm = replacement

    def after(reason):
        if boundary == 'before-read':
            replace()
        elif operation == 'registers':
            p.on_monitor = replace
        else:
            p.on_memory = replace
        delivered.append(actions[operation]())

    s._automatic_runtime_tracker = SimpleNamespace(before_execution=lambda reason: None, after_stop=after,
        status=lambda: dict(observations=len(delivered)), close=lambda reason: None)
    s.resume()
    with pytest.raises(DebuggerError, match='owner') as failure:
        s.pause()
    assert not delivered and not replacement_locks and not replacement_closed
    assert not replacement_peer.commands and not replacement_peer.requests and not replacement_peer.reads
    assert replacement.qmp is replacement_peer and replacement.gdb is replacement_peer
    assert replacement.operation_deadline == 123 and replacement_peer.operation_deadline is None
    assert not replacement_peer.closed and len(owned.closed) == 1 and owned.vm.qmp is None
    assert failure.value.result['native_state']['running'] is False
    assert dispatches(p) == ['cont', 'stop']


def test_ordinary_machine_has_no_private_breakpoint_exemption(owned):
    machine = MachineContext(owned.vm)
    machine.breakpoints = deepcopy(owned.session.breakpoints)
    owned.vm.context = machine
    with pytest.raises(ValueError, match='Remove machine breakpoints'):
        machine.resume()
    assert dispatches(owned.peer) == [] and not owned.closed


@pytest.mark.parametrize('kind', ['extra', 'kind', 'address', 'length', 'access', 'owner',
                                  'missing', 'identifier', 'ready', 'nonce', 'park-code', 'hook'])
def test_only_the_exact_verified_private_control_is_admitted(owned, kind):
    s, p = owned.session, owned.peer
    identifier = s._return_breakpoint
    if kind == 'extra':
        s.breakpoint(0x20200)
    elif kind in ('kind', 'address', 'length', 'access', 'owner'):
        s.breakpoints[identifier][kind] = dict(kind=0, address=0x20200, length=2,
                                             access='w', owner='not-the-launch-control')[kind]
    elif kind == 'missing':
        del s.breakpoints[identifier]
    elif kind == 'identifier':
        s._return_breakpoint = 'another-control'
    elif kind == 'ready':
        s._ready['helper_psp'] += 1
    elif kind == 'nonce':
        s._nonce = bytes(16)
    elif kind == 'park-code':
        p.ram[s.breakpoints[identifier]['address']] ^= 1
    else:
        s._qemu_hooks = {'same-point': {'breakpoint_id': identifier}}
    points, next_id = deepcopy(s.breakpoints), s.next_bp
    with pytest.raises((ValueError, DebuggerError)):
        s.resume()
    assert dispatches(p) == [] and s.breakpoints == points and s.next_bp == next_id
    assert not owned.closed and s._checkpoint_entry_clean


@pytest.mark.parametrize('field', ['_automatic_internal_pending', '_qemu_hook_pending'])
def test_pending_native_stop_is_not_discarded_by_resume(owned, field):
    pending = {'native_reply': 'T05', 'unresolved': True}
    setattr(owned.session, field, pending)
    with pytest.raises(ValueError, match='pending native stop'):
        owned.session.resume()
    assert getattr(owned.session, field) is pending
    assert not dispatches(owned.peer) and not owned.closed


def test_preparation_cannot_add_an_unexamined_public_control(owned):
    s = owned.session
    s._layer_exec = {0x20100: 0x90}
    s._layer_before_execution = lambda: s.breakpoints.update(
        extra=dict(kind=1, access='x', length=1, address=0x20200, owner='user'))
    with pytest.raises(ValueError, match='Remove machine breakpoints'):
        s.resume()
    assert not dispatches(owned.peer) and not owned.closed


@pytest.mark.parametrize('observer', ['status', 'pause', 'resume', 'dos_process_info'])
def test_arrived_return_is_observed_once_without_another_execution(owned, observer):
    s, p = owned.session, owned.peer
    s.resume()
    owned.finish()
    result = getattr(s, observer)()
    process = result if observer == 'dos_process_info' else result['process']
    assert process['state'] == 'exited' and process['termination']['code'] == 37
    assert process['source_mapping']['live'] is False
    status = s.status()
    stopped = status['process_stop']
    assert stopped['outcome'] == 'guest_exit'
    assert stopped['native_machine_stop']['kind'] == 'stopped'
    assert stopped['native_machine_stop']['native_reply'] is None
    assert stopped['native_machine_stop']['classification_complete'] is False
    assert stopped['native_machine_stop']['breakpoint_ids'] == []
    assert stopped['native_machine_stop']['native_state']['status'] == 'debug'
    assert status == s.status()
    assert dispatches(p) == ['cont'] and not owned.closed
    assert s._return_breakpoint is None and s.breakpoints == {} and not p.points
    assert owned.serial.reads == 1
    assert len(list(owned.project.db.execute(
        "SELECT 1 FROM debug_events WHERE operation='dos-process-return'"))) == 1
    stored = json.loads(owned.project.db.execute('SELECT metadata FROM debug_runs').fetchone()[0])
    assert stored['process'] == process


def test_return_before_resume_acknowledgement_is_reported_as_stopped(owned):
    owned.peer.on_continue = owned.finish
    result = owned.session.resume()
    assert result['state'] == 'stopped' and result['process_stop']['outcome'] == 'guest_exit'
    assert dispatches(owned.peer) == ['cont'] and not owned.closed


@pytest.mark.parametrize('method', ['registers', 'memory', 'run', 'step', 'breakpoint',
                                    'save_state', 'write_registers'])
def test_unobserved_async_stop_fences_other_public_controls(owned, method):
    s, p = owned.session, owned.peer
    s.resume(); owned.finish()
    counts = len(p.commands), len(p.requests), len(p.reads)
    arguments = {'registers': ((), {}), 'memory': ((0x20100,), {'length': 1}),
        'run': ((), {'timeout_ms': 100}), 'step': ((), {'timeout_ms': 100}),
        'breakpoint': ((0x20200,), {}), 'save_state': (('unobserved',), {}),
        'write_registers': (({'eax': {'value': '0x0', 'expected': '0x0'}},), {})}
    args, kwargs = arguments[method]
    with pytest.raises(ValueError, match='pending DOS asynchronous run'):
        getattr(s, method)(*args, **kwargs)
    assert counts == (len(p.commands), len(p.requests), len(p.reads))
    assert s.status()['process']['state'] == 'exited' and not owned.closed


def test_repeated_resume_while_running_cannot_dispatch_again(owned):
    owned.session.resume()
    with pytest.raises(ValueError, match='pending DOS asynchronous run'):
        owned.session.resume()
    assert dispatches(owned.peer) == ['cont'] and not owned.closed
    assert owned.session.pause()['state'] == 'stopped'


@pytest.mark.parametrize('fault', ['ready-only', 'serial-missing', 'serial-mismatch', 'identity', 'park-code'])
def test_pc_alone_never_qualifies_dos_return(owned, fault):
    s, p = owned.session, owned.peer
    s.resume()
    if fault == 'ready-only':
        p.cs, p.ip = 0x1800, s._ready['exit_wait_ip']
        p.running, p.runstate = False, 'debug'
        owned.serial.data.extend(s._ready_bytes)
    else:
        owned.finish(serial=fault != 'serial-missing')
        if fault == 'serial-mismatch':
            owned.serial.data[helper.REPORT_FIELDS['dos_result']] ^= 1
        elif fault == 'identity':
            offset = helper.REPORT_FIELDS['child_psp']
            p.ram[owned.report_address+offset] ^= 1
            owned.serial.data[offset] ^= 1
        elif fault == 'park-code':
            p.ram[0x18000+s._ready['exit_wait_ip']] ^= 1
    with pytest.raises((DebuggerError, ValueError, TimeoutError)):
        s.status()
    assert dispatches(p) == ['cont'] and len(owned.closed) == 1
    assert s._process['termination'] is None and not s._process['source_mapping']['live']
    assert not list(owned.project.db.execute(
        "SELECT 1 FROM debug_events WHERE operation='dos-process-return'"))


def test_uncertain_continue_closes_original_owner_without_retry(owned):
    def lost_reply():
        raise TimeoutError('Authored cont acknowledgement loss')
    owned.peer.on_continue = lost_reply
    with pytest.raises(TimeoutError, match='acknowledgement loss'):
        owned.session.resume()
    assert dispatches(owned.peer) == ['cont'] and len(owned.closed) == 1
    assert owned.session._process['state'] == 'observation_failed'


@pytest.mark.parametrize('boundary', ['admission', 'continue', 'stop-observation'])
def test_owner_change_never_operates_or_closes_the_replacement(owned, boundary):
    s, original = owned.session, owned.vm
    replacement_closed = []
    replacement = SimpleNamespace(qmp=SimpleNamespace(call=lambda *a, **k: pytest.fail('Replacement QMP used')),
        gdb=None, operation_deadline=123, close=lambda: replacement_closed.append(True))
    def replace():
        s.vm = replacement
    if boundary == 'admission':
        s._layer_exec = {0x20100: 0x90}
        s._layer_before_execution = replace
    elif boundary == 'continue':
        owned.peer.on_continue = replace
    else:
        s.resume(); owned.finish()
        owned.peer.on_monitor = replace
    with pytest.raises(DebuggerError, match='owner'):
        s.status() if boundary == 'stop-observation' else s.resume()
    assert not replacement_closed and replacement.operation_deadline == 123
    assert len(owned.closed) == 1 and original.qmp is None
    assert dispatches(owned.peer) == ([] if boundary == 'admission' else ['cont'])


def test_expired_incoming_deadline_refuses_before_any_native_io(owned):
    s, p = owned.session, owned.peer
    s._rpc_deadline = time.monotonic()-1
    with pytest.raises(TimeoutError, match='deadline'):
        s.resume()
    assert not p.commands and not p.reads and not owned.closed


def test_existing_deadlines_are_intersected_and_restored(owned):
    s, p, vm = owned.session, owned.peer, owned.vm
    now = time.monotonic()
    s._rpc_deadline, s._deadline = now+10, now+9
    vm.operation_deadline, p.operation_deadline = now+8, now+7
    result = s.resume()
    assert result['state'] == 'running'
    assert all(bound <= now+7 for _, _, bound in p.commands)
    assert all(bound <= now+7 for _, _, _, bound in p.reads)
    assert s._deadline == now+9 and vm.operation_deadline == now+8 and p.operation_deadline == now+7
    s.pause()


def test_deadline_loss_after_continue_closes_without_another_dispatch(owned, monkeypatch):
    clock = [100.0]
    controlled = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr('fdisbull.qemu_machine.time', controlled)
    monkeypatch.setattr('fdisbull.qemu_dos_process.time', controlled)
    monkeypatch.setattr('fdisbull.operation_budget.time', controlled)
    owned.session._deadline = 101.0
    owned.peer.on_continue = lambda: clock.__setitem__(0, 102.0)
    with pytest.raises(TimeoutError, match='deadline'):
        owned.session.resume()
    assert dispatches(owned.peer) == ['cont'] and len(owned.closed) == 1

