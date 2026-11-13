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


def test_live_input_callback_preserves_the_original_watchpoint_stop():
    remote, wire = remote_with(b'+' + packet(b'T05watch:1234;thread:p01.01;'))
    calls = []

    def input_callback(deadline):
        assert wire.requests == [packet(b'c')]
        calls.append(deadline)

    reply, expired = remote.execute('c', 1000, after_send=input_callback)
    assert reply == b'T05watch:1234;thread:p01.01;' and not expired
    assert len(calls) == 1 and wire.requests == [packet(b'c')]
    assert not wire.closed


def test_uncertain_live_input_callback_closes_without_replaying_continue():
    remote, wire = remote_with(packet(b'T05thread:01;'))

    def unknown_delivery(deadline):
        raise TimeoutError('QMP acknowledgement lost after input dispatch')

    with pytest.raises(TimeoutError, match='acknowledgement lost'):
        remote.execute('c', 1000, after_send=unknown_delivery)
    assert remote.socket is None and wire.closed
    assert wire.requests == [packet(b'c')]


def test_live_input_callback_is_rejected_for_single_step_before_dispatch():
    remote, wire = remote_with()
    with pytest.raises(ValueError, match='continue'):
        remote.execute('s', 1000, after_send=lambda deadline: None)
    assert wire.requests == [] and not wire.closed


@pytest.mark.parametrize('entrypoint', ['execute', 'request'])
@pytest.mark.parametrize('failure', [TimeoutError, BrokenPipeError])
def test_uncertain_stop_ack_closes_without_interrupt_or_replay(entrypoint, failure):
    remote, wire = remote_with(packet(b'T05thread:01;'))
    sent, acknowledgements = wire.sendall, []

    def fail_ack(data):
        if data == b'+':
            acknowledgements.append(data)
            raise failure('authored uncertain ACK write')
        return sent(data)

    wire.sendall = fail_ack
    with pytest.raises(DebuggerError, match='acknowledgement failed'):
        if entrypoint == 'execute':
            remote.execute('c', 1000)
        else:
            remote.request('?')
    assert acknowledgements == [b'+']
    assert wire.requests == [packet(b'c' if entrypoint == 'execute' else b'?')]
    assert remote.socket is None and wire.closed
