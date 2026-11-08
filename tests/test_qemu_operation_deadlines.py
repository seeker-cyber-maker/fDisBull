"""Shared operation budgets at the actual QMP/GDB protocol boundaries."""
import json
import threading

import pytest

from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_control import QemuControl


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def packet(payload):
    return b'$' + payload + b'#' + f'{sum(payload) % 256:02x}'.encode()


class Wire:
    """A protocol peer whose response delay consumes the supplied I/O budget."""
    def __init__(self, clock, protocol, latency=0):
        self.clock, self.protocol, self.latency = clock, protocol, latency
        self.buffer = bytearray()
        self.pending_delay = 0
        self.requests, self.budgets, self.interrupts = [], [], []
        self.timeout = None
        self.closed = False
        self.mode = b'0'
        self.recover_stop = True
        self.on_ack = None

    def settimeout(self, seconds):
        assert seconds > 0
        self.timeout = seconds

    def sendall(self, data):
        if data == b'+':
            if self.on_ack is not None:
                self.on_ack()
            return
        if data == b'\x03':
            self.interrupts.append(self.timeout)
            if self.recover_stop:
                self.buffer.extend(packet(b'T05thread:01;'))
            return
        self.budgets.append(self.timeout)
        if self.protocol == 'qmp':
            request = json.loads(data)
            self.requests.append(request['execute'])
            reply = {} if request['execute'] == 'qmp_capabilities' else {'running': False}
            self.buffer.extend(json.dumps({'return': reply, 'id': request['id']}).encode() + b'\n')
        else:
            assert data.startswith(b'$') and data[-3:-2] == b'#'
            request = data[1:-3]
            self.requests.append(request)
            if request.startswith(b'qSupported:'):
                reply = b'PacketSize=1000;qXfer:features:read+'
            elif request.startswith(b'qXfer:features:read:target.xml:'):
                reply = (b'l<target><architecture>i386</architecture><feature name="core">'
                         b'<reg name="eax" bitsize="32"/></feature></target>')
            elif request == b'qqemu.PhyMemMode':
                reply = self.mode
            elif request.startswith(b'Qqemu.PhyMemMode:'):
                self.mode = request[-1:]
                reply = b'OK'
            elif request.startswith(b'm'):
                reply = b'00' * int(request.split(b',')[1], 16)
            elif request == b'c':
                return  # Execution stops only after the client's interrupt.
            else:
                reply = b'00000000'
            self.buffer.extend(packet(reply))
        self.pending_delay = self.latency

    def recv(self, count):
        if not self.buffer or self.pending_delay >= self.timeout:
            self.clock.advance(self.timeout)
            self.pending_delay = max(0, self.pending_delay - self.timeout)
            raise TimeoutError('Peer response exceeded its supplied I/O deadline')
        self.clock.advance(self.pending_delay)
        self.pending_delay = 0
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def close(self):
        self.closed = True


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr('time.monotonic', clock)
    return clock


def client(protocol, clock, latency=0):
    wire = Wire(clock, protocol, latency)
    if protocol == 'qmp':
        remote = QemuControl.__new__(QemuControl)
        remote.buffer, remote.sequence, remote.lock = bytearray(), 0, threading.Lock()
    else:
        remote = GDBRemote.__new__(GDBRemote)
        remote.lock, remote.console = threading.RLock(), []
        remote._buffer, remote._cursor, remote._packet_state = b'', 0, None
    remote.socket, remote.operation_deadline = wire, None
    return remote, wire


def operation(remote, name, timeout_ms=2000):
    if name == 'call':
        return remote.call('query-status', timeout_ms=timeout_ms)
    if name == 'request':
        return remote.request('g', timeout_ms=timeout_ms)
    if name == 'execute':
        return remote.execute('c', timeout_ms)
    return remote.memory(0x2000, 2, data=b'\x90\x90', timeout_ms=timeout_ms)


@pytest.mark.parametrize('name', ['call', 'request', 'execute', 'memory'])
def test_expired_operation_does_not_dispatch_even_a_memory_mode_query(clock, name):
    remote, wire = client('qmp' if name == 'call' else 'gdb', clock)
    remote.operation_deadline = clock.now
    with pytest.raises(TimeoutError, match='deadline'):
        operation(remote, name)
    assert wire.requests == [] and wire.interrupts == []
    assert remote.socket is wire


@pytest.mark.parametrize('name', ['call', 'request', 'execute'])
def test_expiry_while_waiting_for_the_lock_cannot_dispatch_late(clock, name):
    remote, wire = client('qmp' if name == 'call' else 'gdb', clock)
    remote.operation_deadline = clock.now + .25
    budgets = []

    class ContendedLock:
        def acquire(self, *, timeout):
            budgets.append(timeout)
            clock.advance(timeout + .01)
            return True

        def release(self):
            pass

    remote.lock = ContendedLock()
    with pytest.raises(TimeoutError, match='deadline'):
        operation(remote, name)
    assert budgets == pytest.approx([.25])
    assert wire.requests == [] and wire.interrupts == []


@pytest.mark.parametrize('protocol,name', [('qmp', 'call'), ('gdb', 'request')])
def test_successive_commands_consume_one_shared_budget(clock, protocol, name):
    remote, wire = client(protocol, clock, latency=.2)
    remote.operation_deadline = clock.now + .5
    operation(remote, name)
    operation(remote, name)
    assert wire.budgets == pytest.approx([.5, .3])
    clock.advance(.11)
    with pytest.raises(TimeoutError, match='deadline'):
        operation(remote, name)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('protocol,name', [('qmp', 'call'), ('gdb', 'request')])
def test_shorter_local_budget_still_closes_an_uncertain_dispatched_channel(clock, protocol, name):
    remote, wire = client(protocol, clock, latency=.2)
    remote.operation_deadline = clock.now + 1
    with pytest.raises(TimeoutError):
        operation(remote, name, timeout_ms=50)
    assert wire.budgets == pytest.approx([.05])
    assert len(wire.requests) == 1 and remote.socket is None and wire.closed
    assert clock.now == pytest.approx(100.05)


@pytest.mark.parametrize('protocol,constructor', [('qmp', QemuControl), ('gdb', GDBRemote)])
def test_initialization_uses_its_budget_without_expiring_later_unscoped_calls(clock, protocol, constructor):
    wire = Wire(clock, protocol, latency=.2)
    if protocol == 'qmp':
        wire.buffer.extend(b'{"QMP":{}}\n')
    remote = constructor(None, None, clock.now + .5, channel=wire)
    assert remote.operation_deadline is None
    # Register discovery converts its remaining budget to integer milliseconds.
    assert wire.budgets == pytest.approx([.5] if protocol == 'qmp' else [.5, .3], abs=.0011)
    clock.advance(1)
    operation(remote, 'call' if protocol == 'qmp' else 'request')
    remote.close()


@pytest.mark.parametrize('protocol,constructor', [('qmp', QemuControl), ('gdb', GDBRemote)])
def test_expired_initialization_closes_without_sending_a_handshake(clock, protocol, constructor):
    wire = Wire(clock, protocol)
    wire.buffer.extend(b'{"QMP":{}}\n')
    with pytest.raises(TimeoutError, match='deadline'):
        constructor(None, None, clock.now, channel=wire)
    assert wire.closed and not wire.requests


def test_chunked_memory_cannot_refresh_an_inherited_operation_budget(clock):
    remote, wire = client('gdb', clock, latency=.02)
    wire.mode, remote.packet_size = b'1', 64
    remote.operation_deadline = clock.now + .07
    with pytest.raises(TimeoutError):
        remote.memory(0x2000, 120, timeout_ms=2000)
    assert wire.requests[0] == b'qqemu.PhyMemMode'
    assert sum(request.startswith(b'm') for request in wire.requests) == 3
    assert all(later < earlier for earlier, later in zip(wire.budgets, wire.budgets[1:]))
    assert 100.06 < clock.now <= 100.071
    assert remote.socket is None and wire.closed


def test_expired_memory_mode_recovery_closes_instead_of_dispatching_after_budget(clock):
    remote, wire = client('gdb', clock)
    remote.operation_deadline = clock.now + .5

    def after_read_ack():
        if wire.requests[-1].startswith(b'm'):
            clock.advance(1)

    wire.on_ack = after_read_ack
    with pytest.raises(TimeoutError, match='deadline'):
        remote.memory(0x2000, 2)
    assert wire.requests == [b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:1', b'm2000,2']
    assert wire.mode == b'1' and remote.socket is None and wire.closed


@pytest.mark.parametrize('recover_stop', [True, False])
def test_execution_has_one_extra_recovery_window_but_never_replays(clock, recover_stop):
    remote, wire = client('gdb', clock)
    remote.operation_deadline = clock.now + .04
    wire.recover_stop = recover_stop
    if recover_stop:
        reply, expired = remote.execute('c', 2000)
        assert reply == b'T05thread:01;' and expired
        with pytest.raises(TimeoutError, match='deadline'):
            remote.request('g')
        assert clock.now == pytest.approx(100.04)
    else:
        with pytest.raises(TimeoutError):
            remote.execute('c', 2000)
        assert clock.now == pytest.approx(105.04)
        assert remote.socket is None and wire.closed
    assert wire.requests == [b'c'] and wire.interrupts == [5]
