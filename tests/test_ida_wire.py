"""Wire invariants independent of the DOS and PE engine implementations."""
import socket
import stat
import struct
import threading
import time
import json
from pathlib import Path

import pytest

from fdisbull.ida_wire import Channel, Client, Reader, ProtocolError, dd, dq, ea, string


def test_dos_endpoint_rejects_unauthenticated_peer_before_project_open(tmp_path, monkeypatch):
    from fdisbull import ida_dosbox
    project=tmp_path/'project.fdb';project.touch()
    executable=tmp_path/'dosbox';executable.touch()
    opened=[]
    class FakeProject:
        def __init__(self, path): opened.append(path)
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class FakeSession:
        def __init__(self, *args, **kwargs): self.debug=None
        def close(self): pass
    monkeypatch.setattr(ida_dosbox,'Project',FakeProject)
    monkeypatch.setattr(ida_dosbox,'Session',FakeSession)
    with ida_dosbox.Endpoint(project, executable, tmp_path, idle_timeout=2) as endpoint:
        with socket.create_connection(endpoint.address, timeout=2) as sock:
            channel=Channel(sock); deadline=time.monotonic()+2
            assert channel.receive(deadline)[0]==ida_dosbox.w.OPEN
            channel.send(ida_dosbox.w.OK,dd(1)+string('wrong'),deadline)
            assert sock.recv(1)==b''
        assert opened==[]
        assert stat.S_IMODE(Path(endpoint.password_file).stat().st_mode)==0o600
        assert stat.S_IMODE(Path(endpoint.password_file).parent.stat().st_mode)==0o700
        password=Path(endpoint.password_file).read_text().strip()
        client=Client(socket.create_connection(endpoint.address,timeout=2),debugger_id=10,password=password)
        client.close()
        endpoint.thread.join(2)
    assert opened==[project.resolve()]
    assert not Path(endpoint.password_file).exists()


@pytest.mark.parametrize('value,encoded', [
    (0, '00'), (127, '7f'), (128, '8080'), (16383, 'bfff'),
    (16384, 'c0004000'), (0x1fffffff, 'dfffffff'),
    (0x20000000, 'ff20000000'), (0xffffffff, 'ffffffffff'),
])
def test_integer_boundary_vectors(value, encoded):
    assert dd(value).hex() == encoded
    reader = Reader(bytes.fromhex(encoded))
    assert reader.dd() == value
    reader.finish()


def test_address_sentinel_and_full_width_values():
    assert ea(0xffffffffffffffff) == b'\0\0'
    assert ea(0) == b'\1\0'
    reader = Reader(bytes.fromhex('ff9abcdef0ff12345678'))
    assert reader.dq() == 0x123456789abcdef0
    reader.finish()
    with pytest.raises(ProtocolError):
        dq(1 << 64)
    with pytest.raises(ProtocolError):
        dd(True)


def test_actual_ida94_register_descriptions_not_a_locally_generated_roundtrip():
    from fdisbull.ida_wire import register_set
    vectors=json.loads(Path(__file__).with_name('ida_rpc_vectors.json').read_text())
    for key,count,ip in [('init_reply_hex',52,'eip'),('start_reply_hex',76,'rip')]:
        reader=Reader(bytes.fromhex(vectors[key]))
        assert reader.dd()==1
        if key=='init_reply_hex':assert reader.dq()==0x500000000
        else:assert (reader.dd(),reader.string())==(8,'win32')
        description=register_set(reader);reader.finish()
        registers=description['registers']
        assert len(registers)==count
        assert registers[25]['name']==ip
        assert description['classes'][:2]==['General registers','Segment registers']
    assert [r['name'] for r in registers[17:26]]==['rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','rip']


@pytest.mark.parametrize('data', [b'', b'\x80', b'\xc0\0', b'\xff\0\0\0', b'\xe0'])
def test_malformed_integers_fail_closed(data):
    with pytest.raises(ProtocolError):
        Reader(data).dd()


def test_truncated_and_unterminated_objects():
    with pytest.raises(ProtocolError):
        Reader(b'not terminated').string()
    with pytest.raises(ProtocolError):
        Reader(b'x').raw(2)
    with pytest.raises(ProtocolError):
        Reader(b'x').finish()
    with pytest.raises(ProtocolError):
        string('bad\0string')


def test_fragmented_frame_and_packet_budget():
    left, right = socket.socketpair()
    channel = Channel(left)
    def send():
        for part in (b'\0\0', b'\0\x03\x19a', b'bc'):
            right.sendall(part)
        right.close()
    worker = threading.Thread(target=send)
    worker.start()
    try:
        assert channel.receive(time.monotonic() + 2) == (25, b'abc')
        with pytest.raises(ProtocolError):
            channel.receive(time.monotonic() + 2)
        assert channel.stream is None
    finally:
        channel.close()
        worker.join(2)
    left, right = socket.socketpair()
    right.sendall(struct.pack('!IB', 8 * 1024 * 1024 + 1, 0))
    channel = Channel(left)
    try:
        with pytest.raises(ProtocolError, match='budget'):
            channel.receive(time.monotonic() + 2)
        assert channel.stream is None
    finally:
        channel.close()
        right.close()


def test_mismatched_interface_never_sends_a_debug_request():
    left, right = socket.socketpair()
    packet = dd(30) + dd(0) + dd(8)
    right.sendall(struct.pack('!IB', len(packet), 3) + packet)
    try:
        with pytest.raises(ProtocolError, match='Unsupported IDA interface'):
            Client(left)
        assert right.recv(1) == b''
    finally:
        right.close()


def test_request_handles_interleaved_server_message_and_does_not_replay():
    left, right = socket.socketpair()
    peer = Channel(right)
    errors = []
    def server():
        try:
            deadline = time.monotonic() + 3
            peer.send(3, dd(31) + dd(0) + dd(8), deadline)
            assert peer.receive(deadline) == (0, b'\1\0')
            peer.send(0, b'\1', deadline)
            assert peer.receive(deadline) == (25, b'payload')
            peer.send(53, b'hello\0', deadline)
            assert peer.receive(deadline) == (0, b'')
            peer.close()  # A mutation/request must not be repeated after EOF.
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=server)
    worker.start()
    client = Client(left)
    try:
        with pytest.raises(ProtocolError, match='closed'):
            client.request(25, b'payload')
        assert client.channel.stream is None
        assert client.messages == [{'code': 53, 'message': 'hello'}]
    finally:
        client.close()
        worker.join(4)
    assert not errors


@pytest.mark.parametrize('timeout',[0,True,600001,'120000'])
def test_launch_budget_is_validated_before_any_debugger_request(timeout):
    from fdisbull.ida_remote import RemoteDebugger
    client=RemoteDebugger.__new__(RemoteDebugger);client.pid=None
    client.request=lambda *args,**kwargs:pytest.fail('Invalid timeout reached native target')
    with pytest.raises(ValueError,match='Launch timeout'):client.start('unused',timeout_ms=timeout)
