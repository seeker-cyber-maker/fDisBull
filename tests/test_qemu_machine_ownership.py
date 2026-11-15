"""Startup budget and owned serial descriptor regressions, without a guest OS."""
import socket
import time
from types import SimpleNamespace

import pytest

from fdisbull import qemu_machine
from fdisbull.dosbox_rpc import DebuggerError


@pytest.mark.parametrize('identity_elapsed', [.4, .6])
def test_identity_probe_and_control_startup_share_one_machine_budget(
        tmp_path, monkeypatch, identity_elapsed):
    executable = tmp_path / 'authored-qemu'
    executable.write_bytes(b'authored identity fixture')
    executable.chmod(0o700)
    image = tmp_path / 'authored-disk.img'
    image.write_bytes(bytes(510) + b'\x55\xaa')
    now, probes, spawned, controls, queries = [100.0], [], [], [], []
    monkeypatch.setattr(qemu_machine.time, 'monotonic', lambda: now[0])

    def identity(command, **options):
        probes.append(options['timeout'])
        now[0] += identity_elapsed
        return 'QEMU emulator version 9.2.4\n'

    class Process:
        stdin = stdout = None

        def __init__(self, *args, **options):
            self.alive = True
            spawned.append(self)

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.alive = False

        def wait(self, *, timeout):
            assert not self.alive
            return 0

    class Control:
        def __init__(self, path, process, deadline):
            controls.append(deadline)
            now[0] += .05

        def call(self, method, *, timeout_ms):
            assert method == 'query-commands'
            queries.append((timeout_ms, self.operation_deadline))
            return []

        def close(self):
            pass

    monkeypatch.setattr(qemu_machine.subprocess, 'check_output', identity)
    monkeypatch.setattr(qemu_machine.subprocess, 'Popen', Process)
    monkeypatch.setattr(qemu_machine, 'QemuControl', Control)
    machine = qemu_machine.QemuMachine.__new__(qemu_machine.QemuMachine)
    if identity_elapsed > .5:
        with pytest.raises(DebuggerError, match='startup deadline'):
            machine.__init__(executable, boot_image=image, timeout_ms=500)
        assert spawned == [] and controls == [] and queries == []
        assert machine.temporary is None
    else:
        machine.__init__(executable, boot_image=image, timeout_ms=500)
        try:
            assert controls == [100.5]
            assert len(queries) == 1 and 49 <= queries[0][0] <= 50
            assert queries[0][1] == 100.5
            assert machine.qmp.operation_deadline is None
        finally:
            machine.close()
        assert spawned[0].poll() == 0 and machine.temporary is None
    assert probes == [.5]


def test_closing_machine_closes_its_unix_serial_client_descriptor(tmp_path, monkeypatch):
    # The socket pair supplies real descriptor/EOF behavior while connect is
    # isolated from hosts that forbid creating a listening Unix socket.
    stream, peer = socket.socketpair()
    paths = []
    endpoint = SimpleNamespace(connect=paths.append, close=stream.close)
    monkeypatch.setattr(qemu_machine.socket, 'socket', lambda *args: endpoint)
    machine = qemu_machine.QemuMachine.__new__(qemu_machine.QemuMachine)
    machine.transport = 'unix'
    machine.rpc_path = tmp_path / 'rpc.sock'
    machine._channels = []
    machine.gdb = machine.qmp = machine.process = machine.temporary = None
    machine.close_observer = None
    peer.settimeout(.5)
    try:
        assert machine.serial(time.monotonic() + 1) is endpoint
        assert paths == [str(machine.rpc_path)]
        stream.sendall(b'owned channel')
        assert peer.recv(13) == b'owned channel'
        machine.close()
        assert stream.fileno() == -1 and peer.recv(1) == b''
        machine.close()  # Closing the owner twice cannot reopen the channel.
    finally:
        stream.close()
        peer.close()
