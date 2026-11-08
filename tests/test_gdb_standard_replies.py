"""Standard RSP errors cannot swallow QEMU's valid ENABLE bit inventory."""
import threading

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.gdb_rpc import GDBRemote


def packet(payload):
    return b'$' + payload + b'#' + f'{sum(payload) % 256:02x}'.encode()


class Transcript:
    def __init__(self, replies):
        self.replies, self.requests, self.buffer = list(replies), [], b''
        self.closed = False

    def settimeout(self, value):
        assert value > 0

    def sendall(self, data):
        if data != b'+':
            self.requests.append(data)
            self.buffer += self.replies.pop(0)

    def recv(self, size):
        if not self.buffer:
            raise TimeoutError('Missing peer reply')
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def close(self):
        self.closed = True


def remote_with(*replies):
    remote = GDBRemote.__new__(GDBRemote)
    remote.socket = wire = Transcript(replies)
    remote.lock, remote.console = threading.RLock(), []
    remote._buffer, remote._cursor, remote._packet_state = b'', 0, None
    remote.operation_deadline = None
    return remote, wire


def test_enable_inventory_is_data_and_leaves_channel_usable():
    inventory = b'ENABLE=1,NOIRQ=2,NOTIMER=4'
    remote, wire = remote_with(packet(inventory), packet(b'0x7'))
    assert remote.request('qqemu.sstepbits') == inventory
    assert remote.socket is wire and not wire.closed
    assert remote.request('qqemu.sstep') == b'0x7'
    assert len(wire.requests) == 2


@pytest.mark.parametrize('reply', [b'E01', b'E22', b'Eaf', b'E.Failed to read memory'])
def test_standard_error_still_closes_without_retry(reply):
    remote, wire = remote_with(packet(reply))
    with pytest.raises(DebuggerError, match='QEMU GDB operation failed'):
        remote.request('qqemu.sstepbits')
    assert remote.socket is None and wire.closed and len(wire.requests) == 1


@pytest.mark.parametrize('reply,error', [(b'$ENABLE=1#00', DebuggerError), (b'', TimeoutError)])
def test_transport_failure_still_closes_without_retry(reply, error):
    remote, wire = remote_with(reply)
    with pytest.raises(error):
        remote.request('qqemu.sstepbits')
    assert remote.socket is None and wire.closed and len(wire.requests) == 1
