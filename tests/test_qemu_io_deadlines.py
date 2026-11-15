"""Script I/O must reach the real QMP boundary with its remaining budget."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from types import SimpleNamespace
import uuid

import pytest

from fdisbull.debug_script import execute_script
from fdisbull.debugger import stamp
from fdisbull.project import Project
from fdisbull.qemu_clock import machine_clock_configuration
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_machine import MachineContext, MachineDebugSession


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class QMPWire:
    """Delay actual QMP envelopes, honoring the socket timeout supplied to us."""
    def __init__(self, clock):
        self.clock = clock
        self.latency = 0.0
        self.timeout = None
        self.pending_delay = 0.0
        self.buffer = bytearray()
        self.requests, self.budgets = [], []
        self.closed = False

    def settimeout(self, seconds):
        assert seconds > 0
        self.timeout = seconds

    def sendall(self, data):
        request = json.loads(data)
        command = request['execute']
        self.requests.append(command)
        self.budgets.append(self.timeout)
        if command == 'query-status':
            result = dict(running=False, status='paused')
        elif command == 'query-replay':
            result = dict(mode='none', icount=17)
        elif command == 'screendump':
            Path(request['arguments']['filename']).write_bytes(b'P6\n1 1\n255\n\xff\0\0')
            result = {}
        else:
            pytest.fail('Unexpected native request: ' + command)
        self.buffer.extend(json.dumps(dict(id=request['id'], **{'return': result})).encode() + b'\n')
        self.pending_delay = self.latency

    def recv(self, count):
        if self.pending_delay >= self.timeout:
            self.clock.advance(self.timeout)
            self.pending_delay -= self.timeout
            raise TimeoutError('QMP peer exceeded the remaining observation budget')
        self.clock.advance(self.pending_delay)
        self.pending_delay = 0.0
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def close(self):
        self.closed = True


@pytest.fixture
def observation(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock)
    source = tmp_path / 'authored.img'
    source.write_bytes(bytes.fromhex('fa f4 ebfd').ljust(510, b'\0') + b'\x55\xaa')
    with Project.create(tmp_path / 'authored.fdb', source, arch='x86', bits=16,
                        base=0x7c00, entry=0x7c00) as project:
        wire = QMPWire(clock)
        qmp = QemuControl.__new__(QemuControl)
        qmp.socket, qmp.buffer, qmp.sequence = wire, bytearray(), 0
        qmp.lock, qmp.operation_deadline = threading.Lock(), None
        gdb = SimpleNamespace(socket=object(), operation_deadline=None)
        vm = SimpleNamespace(qmp=qmp, gdb=gdb, lock=threading.RLock(),
                             operation_deadline=None, machine_stopped=True, closed=False,
                             qmp_commands={'screendump', 'input-send-event', 'query-replay'},
                             machine_configuration=dict(cpus=1,
                                 clock_profile=machine_clock_configuration('instruction', 1)),
                             temporary=SimpleNamespace(name=str(tmp_path)))
        session = MachineDebugSession.__new__(MachineDebugSession)
        MachineContext.__init__(session, vm)
        session.project, session.rpc, session.run_id = project, vm, uuid.uuid4().hex
        session.version, session.metadata = project.version(), {'backend': 'qemu-machine'}
        session.guest_profile, session.closed = None, False
        session._stopped = lambda: None
        session.registers = lambda: dict(context='machine', registers={'eip': '0x7c00'},
                                        cpu_mode='real', linear_pc='0x7c00')
        vm.context = session

        def close():
            session._input_on_close()
            qmp.close()
            gdb.socket = None
            vm.qmp = vm.gdb = None
            vm.closed = True

        vm.close = close
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                               (session.run_id, session.version['id'], stamp(), None,
                                'stopped', json.dumps(session.metadata)))
        try:
            yield SimpleNamespace(session=session, project=project, vm=vm, qmp=qmp,
                                  gdb=gdb, wire=wire, clock=clock, directory=tmp_path)
        finally:
            session.close()


def route(operation):
    return dict(format='fdisbull-script-1', backend='qemu-machine', steps=[dict(op=operation)])


def test_clock_script_exhausts_one_budget_at_the_real_qmp_boundary(observation):
    o = observation
    o.wire.latency = .03
    result = execute_script(o.session, route('clock-observe'), timeout_ms=50)
    assert result['ok'] is False
    assert result['error']['type'] == 'TimeoutError'
    assert o.wire.requests == ['query-status', 'query-replay']
    assert o.wire.budgets == pytest.approx([.05, .02])
    assert o.clock.now == pytest.approx(100.05)
    assert o.vm.closed and o.wire.closed and o.session._rpc_deadline is None


@pytest.mark.parametrize('operation', ['capture-surface', 'screenshot'])
def test_surface_does_not_refresh_the_script_budget_between_native_reads(observation, operation):
    o = observation
    o.wire.latency = .02
    result = execute_script(o.session, route(operation), timeout_ms=50)
    assert result['ok'] is False
    assert o.wire.requests == ['query-status', 'query-replay', 'screendump']
    assert o.wire.budgets == pytest.approx([.05, .03, .01])
    assert o.clock.now == pytest.approx(100.05) and o.vm.closed
    assert not list(o.directory.glob('surface-*.ppm'))
    assert o.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0] == 0


def test_queue_admission_timeout_cannot_schedule_an_edge_after_expiry(observation):
    o = observation
    o.wire.latency = .04
    o.session._rpc_deadline = o.clock.now + .01
    with pytest.raises(TimeoutError):
        o.session.keyboard_key_down('a')
    assert o.wire.requests == ['query-status']
    assert o.wire.budgets == pytest.approx([.01])
    assert o.clock.now == pytest.approx(100.01) and o.vm.closed
    o.session._rpc_deadline = None
    state = o.session.input_state()
    assert state['pending_edges'] == 0 and state['leases'] == {} and not state['valid']


@pytest.mark.parametrize('operation', [
    lambda s: s.clock_observe(),
    lambda s: s.capture_surface(),
    lambda s: s.screenshot(),
    lambda s: s.keyboard_key_down('a'),
    lambda s: s.mouse_move_relative(1, 0),
    lambda s: s.input_cancel_pending(),
])
def test_expired_observation_refuses_before_lock_or_native_dispatch(observation, operation):
    o = observation
    o.session._rpc_deadline = o.clock.now
    class UnavailableLock:
        def acquire(self, **kwargs):
            pytest.fail('Expired observation attempted to acquire the machine lock')
    original_lock = o.vm.lock
    o.vm.lock = UnavailableLock()
    try:
        with pytest.raises(TimeoutError):
            operation(o.session)
    finally:
        o.vm.lock = original_lock
    assert o.wire.requests == [] and not o.vm.closed


def test_screenshot_lock_wait_uses_the_remaining_script_budget(observation):
    o = observation
    waits = []

    class BusyLock:
        def acquire(self, *, timeout):
            waits.append(timeout)
            o.clock.advance(timeout)
            return False

    original_lock = o.vm.lock
    o.vm.lock = BusyLock()
    try:
        result = execute_script(o.session, route('screenshot'), timeout_ms=50)
    finally:
        o.vm.lock = original_lock
    assert result['ok'] is False and result['error']['type'] == 'TimeoutError'
    assert waits == pytest.approx([.05])
    assert result['host_elapsed_ms'] == pytest.approx(50)
    assert o.wire.requests == [] and not o.vm.closed


def test_observation_restores_prior_vm_and_channel_deadlines_after_success(observation):
    o = observation
    o.vm.operation_deadline = 100.2
    o.qmp.operation_deadline = 100.15
    o.gdb.operation_deadline = 100.12
    o.session._rpc_deadline = 100.1
    o.wire.latency = .01
    result = o.session.clock_observe()
    assert result['counter']['value'] == 17
    assert o.wire.budgets == pytest.approx([.1, .09])
    assert o.vm.operation_deadline == 100.2
    assert o.qmp.operation_deadline == 100.15 and o.gdb.operation_deadline == 100.12
    assert not o.vm.closed


def test_script_cannot_report_success_after_observation_persistence_exceeds_budget(observation):
    o = observation
    persist = o.session._event
    def slow_persistence(operation, evidence):
        persist(operation, evidence)
        if operation == 'machine-clock-observe':
            o.clock.advance(.04)
    o.session._event = slow_persistence
    result = execute_script(o.session, route('clock-observe'), timeout_ms=10)
    assert result['ok'] is False
    assert 'budget' in result['error']['message'].lower() or 'deadline' in result['error']['message'].lower()
    assert result['host_elapsed_ms'] >= 40
    assert o.wire.requests == ['query-status', 'query-replay']
