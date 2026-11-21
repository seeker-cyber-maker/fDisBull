"""Authored MZ aliases: segment-register relocation is not A20 wrapping.

Only the process transport is replaced. These fixtures contain no game bytes
and do not qualify execution by a real DOS loader.
"""

import base64
from copy import deepcopy
import hashlib
import struct
from types import SimpleNamespace

import pytest

from dotbox.inspection import inspect_identity
from dotbox.native_rpc import DebuggerError
from dotbox.native_session import NativeSession, _image


def _module():
    body = bytearray(range(80))
    struct.pack_into('<H', body, 4, 0x1234)
    return bytes(body)


def _mz(*, cs, ip, relocations=()):
    """A 64-byte DOS header and an 80-byte wholly authored load module."""
    header = bytearray(64)
    size = len(header) + len(_module())
    struct.pack_into('<14H', header, 0, 0x5a4d, size, 1,
                     len(relocations), 4, 0, 0xffff, 0, 0x40, 0,
                     ip, cs, 28, 0)
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + _module()


@pytest.mark.parametrize('cs, ip', [(0xfff0, 0x0100), (0xffef, 0x0131)])
def test_parser_accepts_wrapped_segment_alias_into_file(cs, ip):
    image = _image(_mz(cs=cs, ip=ip), 'WRAP.EXE')
    assert image['entry_cs'] == cs and image['entry_ip'] == ip
    assert image['module'] == _module()
    assert image['module_size'] == image['allocation_size'] == 80


@pytest.mark.parametrize('cs, ip, file_offset', [
    (0xfff0, 0x0100, 64),       # (load - 16):0100 names module byte zero.
    (0xffef, 0x0131, 64 + 33),  # (load - 17):0131 names module byte 33.
])
def test_offline_identity_reports_wrapped_alias_file_offset(tmp_path, cs, ip, file_offset):
    source = tmp_path / 'WRAP.EXE'
    original = _mz(cs=cs, ip=ip)
    source.write_bytes(original)
    result = inspect_identity(source)
    assert result['image']['entry'] == {
        'relative_cs': cs, 'ip': ip, 'file_offset': file_offset, 'file_backed': True,
    }
    assert source.read_bytes() == original


@pytest.mark.parametrize('cs, ip', [
    (0xfff0, 0x0150),  # Normalized offset 80 is exactly outside allocation.
    (0xfff0, 0x0000),  # At ordinary load 2000 this names PSP byte zero.
    (0xffff, 0x000f),  # One byte before the module is not module-owned.
])
def test_parser_rejects_alias_outside_module_allocation(cs, ip):
    with pytest.raises(ValueError, match='entry'):
        _image(_mz(cs=cs, ip=ip), 'WRAP.EXE')


def _peer(monkeypatch, tmp_path, original, *, cs, ip, load=0x2000, relocate=False):
    """Supply explicit DOS-loader observations, never an emulated loader."""
    game = tmp_path / 'game'
    game.mkdir()
    program = game / 'WRAP.EXE'
    program.write_bytes(original)
    executable = tmp_path / 'never-executed-dosbox'
    executable.write_bytes(b'authored transport stand-in')
    executable.chmod(0o700)
    memory = bytearray(_module())
    if relocate:
        # Authored word 1234 relocated by the independently selected load 2000.
        assert load == 0x2000
        struct.pack_into('<H', memory, 4, 0x3234)
    calls, peers = [], []

    class RPC:
        def __init__(self, selected, directory, *, window):
            self.process = SimpleNamespace(pid=1, poll=lambda: 0)
            self.capabilities = {'video': {'headless': True}}
            self.closed = False
            peers.append(self)

        def call(self, method, params=None, **options):
            calls.append((method, deepcopy(params)))
            if method == 'session.start':
                return {'session_id': 'authored-wrapped-entry', 'state': 'stopped'}
            if method == 'state.get_registers':
                return {'cpu_mode': 'real',
                        'segments': {'cs': cs, 'ds': f'{load - 16:04X}',
                                     'es': f'{load - 16:04X}', 'ss': f'{load:04X}'},
                        'instruction_pointer': ip}
            if method == 'memory.read':
                offset = int(params['address']['offset'], 16) - load * 16
                length = params['length']
                assert 0 <= offset < len(memory)
                assert 0 < length <= len(memory) - offset
                return {'data_base64': base64.b64encode(memory[offset:offset + length]).decode()}
            if method == 'session.stop':
                return {'operation_id': 'authored-stop'}
            if method == 'execution.wait':
                return {'state': 'exited', 'running': False}
            raise AssertionError(f'Unexpected native request: {method}')

        def close(self):
            self.closed = True
            return {'process_reaped': True, 'process_returncode': 0}

    monkeypatch.setattr('dotbox.native_session.DOSBoxRPC', RPC)
    return executable, game, program, memory, calls, peers


@pytest.mark.parametrize('header_cs, entry_ip, runtime_cs, offsets', [
    (0xfff0, 0x0100, '1FF0', [0]),
    (0xffef, 0x0131, '1FEF', [0, 33]),
])
def test_native_attestation_recovers_load_after_segment_rollover(
        monkeypatch, tmp_path, header_cs, entry_ip, runtime_cs, offsets):
    original = _mz(cs=header_cs, ip=entry_ip, relocations=(4,))
    executable, game, program, memory, calls, peers = _peer(
        monkeypatch, tmp_path, original, cs=runtime_cs, ip=f'{entry_ip:04X}', relocate=True)
    with NativeSession(executable, game, program, window=False) as session:
        assert session.metadata['runtime_load_segment'] == 0x2000
        assert session.metadata['runtime_base'] == 0x20000
        samples = session.metadata['attestation']['samples']
        assert [(row['module_offset'], row['runtime_address'], row['length']) for row in samples] == [
            (offset, 0x20000 + offset, 16) for offset in offsets
        ]
        assert [row['sha256'] for row in samples] == [
            hashlib.sha256(memory[offset:offset + 16]).hexdigest() for offset in offsets
        ]
        assert session.metadata['entry_bytes_verified'] == 16 * len(offsets)
    assert peers[0].closed
    assert program.read_bytes() == original
    assert sum(method == 'session.stop' for method, _ in calls) == 1


def test_native_attestation_rejects_actual_a20_crossing_before_memory_reads(monkeypatch, tmp_path):
    # The header has a valid module-relative alias. At load 0010, CS addition
    # does not roll over: FFFF:0131 is physical 100121, not module byte 33 at 0121.
    original = _mz(cs=0xffef, ip=0x0131)
    executable, game, program, _, calls, peers = _peer(
        monkeypatch, tmp_path, original, cs='FFFF', ip='0131', load=0x10)
    with pytest.raises(DebuggerError):
        NativeSession(executable, game, program, window=False)
    assert not any(method == 'memory.read' for method, _ in calls)
    assert peers[0].closed


@pytest.mark.parametrize('cs, ip', [('10000', '0000'), ('2000', '10000')])
def test_native_attestation_rejects_non_16_bit_entry_registers(monkeypatch, tmp_path, cs, ip):
    original = _mz(cs=0, ip=0)
    executable, game, program, _, calls, peers = _peer(
        monkeypatch, tmp_path, original, cs=cs, ip=ip)
    with pytest.raises(DebuggerError):
        NativeSession(executable, game, program, window=False)
    assert not any(method == 'memory.read' for method, _ in calls)
    assert peers[0].closed
