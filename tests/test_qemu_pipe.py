"""Owned pipe transport and real protocol-boundary regressions (no sockets)."""
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote
from fdisbull.qemu_control import QemuControl
from fdisbull.qemu_transport import PipeChannel, create_fifo_pair, open_fifo_pair


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Private POSIX pipe transport')


def channel_pair():
    server_read, client_write = os.pipe()
    client_read, server_write = os.pipe()
    return PipeChannel(client_read, client_write), PipeChannel(server_read, server_write)


def read_packet(channel):
    data = bytearray()
    while b'#' not in data or len(data) < data.index(b'#') + 3:
        value = channel.recv(1)
        if not value:
            raise EOFError('Peer closed before a complete packet')
        data.extend(value)
    return bytes(data)


def packet(payload):
    return b'$' + payload + b'#' + f'{sum(payload) % 256:02x}'.encode()


def remote(channel):
    # Test the production protocol, supplying a real pipe peer rather than
    # implementing QEMU's unrelated register-description handshake here.
    result = GDBRemote.__new__(GDBRemote)
    result.socket = channel
    result.lock = threading.RLock()
    result.console = []
    result._buffer = b''
    result._cursor = 0
    return result


def test_pipe_deadline_and_close_are_bounded():
    client, server = channel_pair()
    try:
        client.settimeout(.02)
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='deadline'):
            client.recv(1)
        assert time.monotonic() - started < 1
        # A blocked writer has the same total budget even after partial writes.
        started = time.monotonic()
        with pytest.raises(TimeoutError, match='deadline'):
            client.sendall(b'x' * (4 * 1024 * 1024))
        assert time.monotonic() - started < 1
        client.close()
        client.close()
        with pytest.raises(OSError, match='closed'):
            client.recv(1)
    finally:
        client.close()
        server.close()


def test_fifo_permissions_and_process_exit_do_not_wait_for_deadline(tmp_path):
    base = tmp_path / 'gdb'
    create_fifo_pair(base)
    assert all(Path(str(base) + suffix).stat().st_mode & 0o777 == 0o600 for suffix in ('.in', '.out'))
    channel = open_fifo_pair(base, SimpleNamespace(poll=lambda: 1))
    try:
        channel.settimeout(30)
        with pytest.raises(BrokenPipeError, match='process exited'):
            channel.recv(1)
    finally:
        channel.close()


@pytest.mark.parametrize('cut', [1, 5, -1])
def test_gdb_timeout_preserves_a_fragmented_stop_reply_and_does_not_replay(cut):
    client, server = channel_pair()
    server.settimeout(2)
    gdb = remote(client)
    stop = b'T05thread:01;'
    wire = packet(stop)
    received = []
    failures = []

    def peer():
        try:
            received.append(read_packet(server))
            server.sendall(b'+' + wire[:cut])
            # A deterministic boundary: complete the reply only after the
            # production client interrupts its timed-out execution request.
            received.append(server.recv(1))
            server.sendall(wire[cut:])
            assert server.recv(1) == b'+'
            received.append(read_packet(server))
            server.sendall(b'+' + packet(b'1234'))
            assert server.recv(1) == b'+'
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        reply, timed_out = gdb.execute('c', 30)
        assert reply == stop and timed_out
        assert gdb.request('g') == b'1234'
    finally:
        gdb.close()
        worker.join(3)
    assert not failures and not worker.is_alive()
    assert received == [packet(b'c'), b'\x03', packet(b'g')]


def test_gdb_invalid_checksum_closes_pipe_without_replaying_request():
    client, server = channel_pair()
    gdb = remote(client)
    server.sendall(b'+$OK#00')
    with pytest.raises(DebuggerError, match='checksum'):
        gdb.request('M100,1:90')
    assert gdb.socket is None
    assert server.recv(4096) == packet(b'M100,1:90')
    assert server.recv(1) == b''
    server.close()


@pytest.mark.parametrize('budget', [256, 4096])
def test_gdb_large_memory_transfer_obeys_peer_packet_budget_and_restores_mode(budget):
    client, server = channel_pair()
    server.settimeout(3)
    gdb = remote(client)
    gdb.packet_size = budget
    base = 0xb8000
    expected = bytes(range(256)) * 15 + bytes(range(160))
    memory = bytearray(len(expected))
    requests = []
    failures = []

    def peer():
        try:
            while True:
                wire = read_packet(server)
                command = wire[1:wire.index(b'#')]
                requests.append(command)
                assert len(command) <= budget
                if command == b'qqemu.PhyMemMode':
                    reply = b'0'
                elif command.startswith(b'Qqemu.PhyMemMode:'):
                    reply = b'OK'
                elif command.startswith(b'M'):
                    header, data = command[1:].split(b':')
                    address, length = (int(part, 16) for part in header.split(b','))
                    decoded = bytes.fromhex(data.decode())
                    assert len(decoded) == length
                    memory[address - base:address - base + length] = decoded
                    reply = b'OK'
                else:
                    assert command.startswith(b'm')
                    address, length = (int(part, 16) for part in command[1:].split(b','))
                    reply = memory[address - base:address - base + length].hex().encode()
                    assert len(reply) <= budget
                server.sendall(b'+' + packet(reply))
                assert server.recv(1) == b'+'
                if command == b'Qqemu.PhyMemMode:0':
                    break
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        assert gdb.memory(base, len(expected), space='physical', data=expected) == expected
    finally:
        gdb.close()
        worker.join(4)
    assert not failures and not worker.is_alive()
    assert memory == expected
    assert requests[0:2] == [b'qqemu.PhyMemMode', b'Qqemu.PhyMemMode:1']
    assert requests[-1] == b'Qqemu.PhyMemMode:0'
    assert sum(item.startswith(b'M') for item in requests) > 1
    assert sum(item.startswith(b'm') for item in requests) > 1


@pytest.mark.parametrize('rejection', [b'E22', b''])
def test_partly_applied_machine_write_closes_vm_without_retry_or_rollback(rejection):
    from fdisbull.qemu_machine import MachineContext

    client, server = channel_pair()
    server.settimeout(3)
    gdb = remote(client)
    gdb.packet_size = 256
    base = 0x2000
    expected = b'\xa5' * 400
    memory = bytearray(len(expected))
    writes = []
    failures = []
    vm = SimpleNamespace(lock=threading.RLock(), gdb=gdb, closed=False,
                         qmp=SimpleNamespace(call=lambda method: {'running': False}),
                         debugger=lambda: gdb)

    def close_vm():
        vm.closed = True
        gdb.close()

    vm.close = close_vm

    def peer():
        try:
            mode = b'0'
            while True:
                wire = read_packet(server)
                command = wire[1:wire.index(b'#')]
                if command == b'qqemu.PhyMemMode':
                    reply = mode
                elif command.startswith(b'Qqemu.PhyMemMode:'):
                    mode = command[-1:]
                    reply = b'OK'
                elif command.startswith(b'M'):
                    writes.append(command)
                    if len(writes) == 2:
                        server.sendall(b'+' + packet(rejection))
                        assert server.recv(1) == b'+'
                        assert server.recv(1) == b''
                        break
                    header, data = command[1:].split(b':')
                    address, length = (int(part, 16) for part in header.split(b','))
                    memory[address - base:address - base + length] = bytes.fromhex(data.decode())
                    reply = b'OK'
                else:
                    assert command.startswith(b'm')
                    address, length = (int(part, 16) for part in command[1:].split(b','))
                    reply = memory[address - base:address - base + length].hex().encode()
                server.sendall(b'+' + packet(reply))
                assert server.recv(1) == b'+'
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        with pytest.raises(DebuggerError, match='(operation failed|write rejected)'):
            MachineContext(vm).write_memory(base, expected.hex(), expected_hex=bytes(len(expected)).hex())
    finally:
        gdb.close()
        worker.join(4)
    assert not failures and not worker.is_alive()
    assert vm.closed and gdb.socket is None
    assert len(writes) == 2 and memory != bytes(len(expected)) and memory != expected


def test_chunked_memory_transfer_has_one_total_deadline():
    client, server = channel_pair()
    server.settimeout(2)
    gdb = remote(client)
    gdb.packet_size = 128
    requests = []
    failures = []

    def peer():
        try:
            while True:
                wire = read_packet(server)
                command = wire[1:wire.index(b'#')]
                requests.append(command)
                if command == b'qqemu.PhyMemMode':
                    reply = b'1'
                else:
                    assert command.startswith(b'm')
                    length = int(command.split(b',')[1], 16)
                    time.sleep(.04)
                    reply = b'00' * length
                server.sendall(b'+' + packet(reply))
                if server.recv(1) == b'':
                    break
        except (BrokenPipeError, EOFError):
            pass  # The failed transfer closes its uncertain in-flight channel.
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            gdb.memory(0x2000, 1024, timeout_ms=100)
        assert time.monotonic() - started < 1
        assert gdb.socket is None
    finally:
        gdb.close()
        worker.join(3)
    assert not failures and not worker.is_alive()
    assert any(item.startswith(b'm') for item in requests)


def test_profile_read_cannot_replace_the_projects_admitted_source(tmp_path, monkeypatch):
    from fdisbull.project import Project
    from fdisbull import qemu_machine
    from fdisbull.qemu_dos import prepare_dos_profile

    image = tmp_path / 'boot.img'
    image.write_bytes(bytes(510) + b'\x55\xaa')
    with Project.create(tmp_path / 'boot.fdb', image, arch='x86', bits=16,
                        base=0x7c00, entry=0x7c00) as project:
        def changed_profile(profile, path):
            current = bytearray(path.read_bytes())
            current[0] = 0x90
            path.write_bytes(current)
            return prepare_dos_profile(path)

        monkeypatch.setattr(qemu_machine.MachineDebugSession, '_admit_guest_profile', staticmethod(changed_profile))
        monkeypatch.setattr(qemu_machine, 'QemuMachine',
                            lambda *args, **options: pytest.fail('VM spawned after source admission changed'))
        with pytest.raises(ValueError, match='admitted project source'):
            qemu_machine.MachineDebugSession(project, '/unused/qemu', boot_image=image, guest_profile='dos')


def test_uncertain_qmp_continue_closes_owned_machine_without_retry():
    from fdisbull.qemu_machine import MachineContext

    class ShortControl(QemuControl):
        def call(self, method, arguments=None, timeout_ms=30000):
            return super().call(method, arguments, timeout_ms=30)

    client, server = channel_pair()
    server.settimeout(2)
    qmp = ShortControl.__new__(ShortControl)
    qmp.socket = client
    qmp.buffer = bytearray()
    qmp.sequence = 0
    qmp.lock = threading.Lock()
    vm = SimpleNamespace(lock=threading.RLock(), gdb=None, qmp=qmp, closed=False, transport='pipe')
    received = []
    failures = []

    def close_vm():
        vm.closed = True
        qmp.close()

    vm.close = close_vm

    def peer():
        try:
            line = bytearray()
            while not line.endswith(b'\n'):
                line.extend(server.recv(1))
            received.append(json.loads(line)['execute'])
            # Treat cont as dispatched but drop its acknowledgement. The
            # owner must terminate rather than accepting another operation.
            assert server.recv(1) == b''
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        with pytest.raises(TimeoutError):
            MachineContext(vm).resume()
    finally:
        qmp.close()
        worker.join(3)
    assert not failures and not worker.is_alive()
    assert received == ['cont'] and vm.closed and qmp.socket is None


def test_qmp_reply_budget_applies_to_each_already_buffered_line():
    qmp = QemuControl.__new__(QemuControl)
    qmp.buffer = bytearray(b'{"n":1}\n{"n":2}\n')
    deadline = time.monotonic() + 2
    assert qmp._read(deadline, max_reply_bytes=7) == {'n': 1}
    assert qmp._read(deadline, max_reply_bytes=7) == {'n': 2}
    qmp.buffer = bytearray(b'{"value":"' + b'x' * 100 + b'"}\n')
    with pytest.raises(DebuggerError, match='reply exceeds budget'):
        qmp._read(deadline, max_reply_bytes=7)


def test_known_qmp_command_rejection_does_not_poison_the_channel():
    client, server = channel_pair()
    server.settimeout(2)
    qmp = QemuControl.__new__(QemuControl)
    qmp.socket = client
    qmp.buffer = bytearray()
    qmp.sequence = 0
    qmp.lock = threading.Lock()
    failures = []

    def peer():
        try:
            for outcome in ({'error': {'class': 'CommandNotFound', 'desc': 'unknown'}},
                            {'return': {'running': False}}):
                line = bytearray()
                while not line.endswith(b'\n'):
                    line.extend(server.recv(1))
                request = json.loads(line)
                server.sendall(json.dumps(dict(outcome, id=request['id'])).encode() + b'\n')
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    try:
        with pytest.raises(DebuggerError, match='CommandNotFound'):
            qmp.call('not-a-command')
        assert qmp.socket is not None
        assert qmp.call('query-status') == {'running': False}
    finally:
        qmp.close()
        worker.join(3)
    assert not failures and not worker.is_alive()


def test_qmp_uses_owned_pipe_and_skips_events_without_losing_reply_identity():
    client, server = channel_pair()
    server.settimeout(2)
    received = []
    failures = []

    def read_line():
        line = bytearray()
        while not line.endswith(b'\n'):
            line.extend(server.recv(1))
        return json.loads(line)

    def peer():
        try:
            server.sendall(b'{"QMP":{"version":{"qemu":{"major":11,"minor":0,"micro":0}}}}\n')
            for result in ({}, {'running': False, 'status': 'paused'}):
                request = read_line()
                received.append(request['execute'])
                server.sendall(b'{"event":"STOP"}\n')
                server.sendall(json.dumps({'return': result, 'id': request['id']}).encode() + b'\n')
        except BaseException as error:
            failures.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=peer)
    worker.start()
    qmp = None
    try:
        qmp = QemuControl(None, None, time.monotonic() + 2, channel=client)
        assert qmp.call('query-status') == {'running': False, 'status': 'paused'}
    finally:
        if qmp is not None:
            qmp.close()
        else:
            client.close()
        worker.join(3)
    assert not failures and not worker.is_alive()
    assert received == ['qmp_capabilities', 'query-status']
