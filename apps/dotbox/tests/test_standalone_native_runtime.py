"""Standalone native boundary contracts; authored pipe peers are not DOSBox QA."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from dotbox.dos_launch_profile import bind_start, prepare_launch_options
from dotbox.native_rpc import DOSBoxRPC, DebuggerError, DebuggerShutdownError
from dotbox.native_session import NativeSession
from dotbox.operation_budget import RpcAdmissionTimeout, deadline_scope
from dotbox.screenshot_codecs import decode_screenshot


def mz(module=b'\x90\x90\xeb\xfe' + bytes(28), *, relocations=(), cs=0, ip=0):
    header = bytearray(64)
    size = len(header) + len(module)
    struct.pack_into('<14H', header, 0, 0x5a4d, size % 512, (size + 511) // 512,
                     len(relocations), 4, 0, 0xffff, 0, 32, 0, ip, cs, 28, 0)
    for index, (offset, segment) in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, segment)
    return bytes(header) + module


@pytest.fixture
def native(tmp_path, monkeypatch):
    """Replace only the process transport seam; exercise real session logic."""
    game_dir = tmp_path / 'game'
    game_dir.mkdir()
    program = game_dir / 'PLAY.COM'
    program.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    executable = tmp_path / 'dosbox'
    executable.write_bytes(b'authored stand-in, never executed')
    executable.chmod(0o700)
    transports = []

    class RPC:
        def __init__(self, selected, directory, *, window):
            self.calls = []
            self.directory = directory
            self.window = window
            self.source = None
            self.capabilities = {'video': {'headless': not window, 'controlled_window': window}}
            self.process = SimpleNamespace(pid=123, poll=lambda: 0)
            self.close_evidence = {'process_reaped': True, 'process_returncode': 0}
            self.fail = None
            self.corrupt = False
            self.closed = False
            transports.append(self)

        def call(self, method, params=None, **options):
            self.calls.append((method, deepcopy(params), options))
            if self.fail == method:
                raise TimeoutError('acknowledgement lost after dispatch')
            if method == 'session.start':
                self.source = (self.directory / params['target']['command']).read_bytes()
                return {'session_id': 'original-session', 'state': 'stopped'}
            if method == 'state.get_registers':
                cs, ip = 0, 0x100
                if self.source.startswith(b'MZ'):
                    ip, cs = struct.unpack_from('<HH', self.source, 20)
                return {'cpu_mode': 'real', 'segments': {'cs': f'{0x2000 + cs:04X}',
                        'ds': '2000', 'es': '2000', 'ss': '2000'},
                        'instruction_pointer': f'{ip:04X}'}
            if method == 'memory.read':
                payload = self.source
                base = 0x20100
                if payload.startswith(b'MZ'):
                    header = struct.unpack_from('<14H', payload)
                    payload = bytearray(payload[header[4] * 16:])
                    for index in range(header[3]):
                        offset, segment = struct.unpack_from('<HH', self.source, header[12] + index * 4)
                        position = segment * 16 + offset
                        old = struct.unpack_from('<H', payload, position)[0]
                        struct.pack_into('<H', payload, position, (old + 0x2000) & 0xffff)
                    base = 0x20000
                offset = int(params['address']['offset'], 16) - base
                data = payload[offset:offset + params['length']]
                if self.corrupt:
                    data = bytes([data[0] ^ 1]) + data[1:]
                return {'data_base64': base64.b64encode(data).decode()}
            if method == 'session.stop':
                return {'operation_id': 'original-stop'}
            if method == 'execution.wait':
                return {'state': 'exited', 'running': False, 'stop_reason': {'kind': 'exit'}}
            if method == 'session.status':
                return {'state': 'stopped', 'frame_id': 3}
            return {'accepted': True}

        def close(self):
            self.closed = True
            return deepcopy(self.close_evidence)

    monkeypatch.setattr('dotbox.native_session.DOSBoxRPC', RPC)
    return executable, game_dir, program, transports, RPC


def test_com_start_retains_native_request_and_source_identity_without_project(native):
    executable, game_dir, program, transports, _ = native
    digest = hashlib.sha256(program.read_bytes()).hexdigest()
    session = NativeSession(executable, game_dir, program, source_sha256=digest)
    transport = transports[0]
    assert transport.window is True
    assert transport.calls[0] == ('session.start', {
        'target': {'command': 'PLAY.COM', 'arguments': []},
        'mounts': [{'drive': 'C', 'host_path': str(game_dir)}], 'break_at': 'entry'}, {})
    assert session.metadata['source_sha256'] == digest
    assert session.metadata['image_format'] == 'COM'
    assert session.metadata['entry_bytes_verified'] == len(program.read_bytes())
    assert session.metadata['attestation']['samples'][0]['runtime_address'] == 0x20100
    assert session.call('session.status') == {'state': 'stopped', 'frame_id': 3}
    assert transport.calls[-1][1]['session_id'] == 'original-session'
    assert not hasattr(session, 'project')
    receipt = session.close()
    assert receipt['closed'] is True and receipt['guest_stop_complete'] is True
    assert receipt['process_reaped'] is True and transport.closed
    before = deepcopy(transport.calls)
    receipt['state'] = 'caller mutation'
    assert session.close()['state'] == 'exited' and transport.calls == before
    with pytest.raises(DebuggerError, match='closed'):
        session.call('session.status')


@pytest.mark.parametrize('window_scale', [2, 3, 4, 5])
def test_session_passes_explicit_window_scale_and_records_request(native, monkeypatch, window_scale):
    executable, game_dir, program, transports, RPC = native
    requested = []

    class ScaledRPC(RPC):
        def __init__(self, selected, directory, *, window, window_scale):
            requested.append(window_scale)
            super().__init__(selected, directory, window=window)

    monkeypatch.setattr('dotbox.native_session.DOSBoxRPC', ScaledRPC)
    with NativeSession(executable, game_dir, program, window_scale=window_scale) as session:
        assert requested == [window_scale]
        assert transports[0].window is True
        assert session.metadata['window_scale_requested'] == window_scale
    assert transports[0].closed


@pytest.mark.parametrize('factory', [DOSBoxRPC, NativeSession])
@pytest.mark.parametrize('window, window_scale', [
    (True, True), (True, False), (True, 1), (True, 6), (True, '4'), (True, 4.0),
    (False, 4),
])
def test_window_scale_rejected_before_process_or_source_access(tmp_path, monkeypatch, factory, window, window_scale):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid display scale reached process launch')

    monkeypatch.setattr('dotbox.native_rpc.subprocess.Popen', forbidden)
    args = [tmp_path / 'absent-dosbox', tmp_path / 'absent-game']
    if factory is NativeSession:
        args.append(tmp_path / 'absent-game/PLAY.COM')
    with pytest.raises(ValueError, match='window_scale'):
        factory(*args, window=window, window_scale=window_scale)


def test_mz_attests_relocated_prefix_and_distinct_file_backed_entry(native):
    executable, game_dir, _, transports, _ = native
    program = game_dir / 'GAME.EXE'
    payload = bytearray(80)
    struct.pack_into('<H', payload, 4, 0x1234)
    payload[33:37] = b'\x90\x90\xeb\xfe'
    original = mz(bytes(payload), relocations=[(4, 0), (4, 0)], cs=2, ip=1)
    program.write_bytes(original)
    with NativeSession(executable, game_dir, program, window=False) as session:
        assert session.metadata['image_format'] == 'MZ'
        assert session.metadata['runtime_load_segment'] == 0x2000
        samples = session.metadata['attestation']['samples']
        assert [(sample['module_offset'], sample['length']) for sample in samples] == [(0, 16), (33, 16)]
        assert transports[0].window is False
    assert program.read_bytes() == original


def test_source_mismatch_and_invalid_image_never_open_transport(native):
    executable, game_dir, program, transports, _ = native
    with pytest.raises(ValueError, match='source hash'):
        NativeSession(executable, game_dir, program, source_sha256='0' * 64)
    program.write_bytes(b'MZ')
    with pytest.raises(ValueError, match='MZ header'):
        NativeSession(executable, game_dir, program)
    assert not transports


@pytest.mark.parametrize('data', [b'ZM\x90', b'\x90' * 65281])
def test_com_cannot_hide_mz_signature_or_exceed_segment(native, data):
    executable, game_dir, program, transports, _ = native
    program.write_bytes(data)
    with pytest.raises(ValueError, match='COM source'):
        NativeSession(executable, game_dir, program)
    assert not transports


def test_source_changed_during_capabilities_is_refused_and_child_closed(native):
    executable, game_dir, program, transports, RPC = native
    original_init = RPC.__init__

    def changed(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        program.write_bytes(b'\xeb\xfe')

    RPC.__init__ = changed
    with pytest.raises(ValueError, match='changed before session start') as raised:
        NativeSession(executable, game_dir, program)
    assert transports[0].closed and transports[0].calls == []
    assert raised.value.launch_cleanup_receipt['guest_stop_complete'] is False


def test_bad_runtime_bytes_fail_launch_and_stop_owned_child(native):
    executable, game_dir, program, transports, RPC = native
    original_init = RPC.__init__

    def corrupted(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.corrupt = True

    RPC.__init__ = corrupted
    with pytest.raises(DebuggerError, match='entry bytes differ') as raised:
        NativeSession(executable, game_dir, program)
    assert transports[0].closed
    assert [call[0] for call in transports[0].calls].count('session.stop') == 1
    assert raised.value.launch_cleanup_receipt['closed'] is True


def test_long_name_alias_is_owned_and_removed_without_touching_source(native):
    executable, game_dir, program, _, _ = native
    renamed = game_dir / 'My original long game.com'
    program.rename(renamed)
    original = renamed.read_bytes()
    with NativeSession(executable, game_dir, renamed) as session:
        target = game_dir / session.metadata['target']
        assert target != renamed and target.read_bytes() == original
    assert renamed.read_bytes() == original and not target.exists()
    assert session.close_receipt['launch_alias_cleanup']['status'] == 'removed'


def test_changed_alias_is_preserved_as_evidence(native):
    executable, game_dir, program, _, _ = native
    renamed = game_dir / 'long original game.com'
    program.rename(renamed)
    session = NativeSession(executable, game_dir, renamed)
    target = game_dir / session.metadata['target']
    target.write_bytes(b'guest modification')
    receipt = session.close()
    assert receipt['launch_alias_cleanup']['status'] == 'retained_changed'
    assert target.read_bytes() == b'guest modification'


def test_session_cannot_dispatch_to_another_guest(native):
    executable, game_dir, program, transports, _ = native
    with NativeSession(executable, game_dir, program) as session:
        before = len(transports[0].calls)
        with pytest.raises(ValueError, match='different native session'):
            session.call('input.keyboard.press', {'session_id': 'other'})
        assert len(transports[0].calls) == before


def test_nested_deadlines_shrink_across_calls_and_expire_before_dispatch(native, monkeypatch):
    executable, game_dir, program, transports, _ = native
    session = NativeSession(executable, game_dir, program)
    now = [100.0]
    monkeypatch.setattr('dotbox.native_session.time.monotonic', lambda: now[0])
    with deadline_scope(session, 104, rpc_ms=4000, admission_ms=0):
        session.call('input.keyboard.press')
        assert transports[0].calls[-1][2]['timeout_ms'] == 4000
        now[0] += 3.25
        with deadline_scope(session, 110, rpc_ms=2000, admission_ms=0):
            session.call('session.status')
            assert transports[0].calls[-1][2]['timeout_ms'] == 750
        now[0] = 104.001
        before = len(transports[0].calls)
        with pytest.raises(RpcAdmissionTimeout):
            session.call('execution.continue')
        assert len(transports[0].calls) == before
    session.close()


def test_nested_one_second_coordination_deadline_cannot_refresh(native, monkeypatch):
    executable, game_dir, program, transports, _ = native
    session = NativeSession(executable, game_dir, program)
    now = [100.0]
    monkeypatch.setattr('dotbox.native_session.time.monotonic', lambda: now[0])
    with deadline_scope(session, 104, rpc_ms=2000, admission_ms=0):
        with deadline_scope(session, 101, rpc_ms=1000, admission_ms=0):
            now[0] += .8
            with deadline_scope(session, 103, rpc_ms=2000, admission_ms=0):
                session.call('execution.wait')
                assert 199 <= transports[0].calls[-1][2]['timeout_ms'] <= 200
        session.call('session.status')
        assert transports[0].calls[-1][2]['timeout_ms'] == 2000
    session.close()


def test_lost_stop_receipt_is_terminal_and_never_replayed(native):
    executable, game_dir, program, transports, _ = native
    session = NativeSession(executable, game_dir, program)
    transports[0].fail = 'session.stop'
    with pytest.raises(DebuggerShutdownError) as raised:
        session.close()
    receipt = raised.value.receipt
    assert receipt['guest_stop_complete'] is False and receipt['process_reaped'] is True
    assert receipt['closed'] is False and receipt['session_terminal'] is True
    assert transports[0].closed
    before = deepcopy(transports[0].calls)
    with pytest.raises(DebuggerShutdownError) as repeated:
        session.close()
    assert repeated.value.receipt == receipt and transports[0].calls == before


def test_abnormal_exit_cannot_become_a_successful_shutdown(native):
    executable, game_dir, program, transports, _ = native
    session = NativeSession(executable, game_dir, program)
    transports[0].process.poll = lambda: -6
    with pytest.raises(DebuggerShutdownError) as raised:
        session.close()
    assert raised.value.receipt['guest_stop_complete'] is True
    assert raised.value.receipt['closed'] is False
    assert raised.value.receipt['termination_signal'] == 6


def test_launch_tail_copy_and_unsupported_cd_fail_before_start():
    profile = prepare_launch_options(['/safe', 'level=2'])
    request = {'target': {'command': 'GAME.EXE', 'arguments': []}}
    bound = bind_start(request, profile)
    assert request['target']['arguments'] == []
    assert bound['target']['arguments'] == ['/safe', 'level=2']
    with pytest.raises(ValueError, match='Conflicting'):
        bind_start({'target': {'arguments': ['/other']}}, profile)
    with pytest.raises(ValueError, match='not supported'):
        prepare_launch_options(cd_image='/private/game.iso')
    with pytest.raises(ValueError, match='ASCII tokens'):
        prepare_launch_options(['& execute'])


def test_proven_screenshot_codec_preserves_frame_metadata_and_checks_hash():
    output = io.BytesIO()
    Image.new('RGB', (2, 3), (12, 34, 56)).save(output, format='PNG')
    png = output.getvalue()
    reply = {'format': 'png', 'width': 2, 'height': 3, 'frame_id': 7, 'mode_id': 4,
             'state_revision': 9, 'png_base64': base64.b64encode(png).decode(),
             'sha256': hashlib.sha256(png).hexdigest()}
    data, metadata = decode_screenshot(reply)
    assert data == png and metadata['frame_id'] == 7 and metadata['state_revision'] == 9
    assert 'png_base64' not in metadata
    with pytest.raises(DebuggerError, match='hash mismatch'):
        decode_screenshot({**reply, 'sha256': '0' * 64})
    with pytest.raises(DebuggerError, match='dimensions differ'):
        decode_screenshot({**reply, 'width': 3})


@pytest.fixture
def pipe_peer(tmp_path):
    """An authored executable peer exercises real inherited pipe ownership."""
    executable = tmp_path / 'pipe-peer'
    executable.write_text(f'''#!{sys.executable}
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
config = Path(args[args.index('--agent-config') + 1]).read_text()
endpoint = next(line.split('=', 1)[1] for line in config.splitlines() if line.startswith('endpoint='))
_, source, sink = endpoint.split(':')
with os.fdopen(int(source), 'r') as reader, os.fdopen(int(sink), 'w') as writer:
    for line in reader:
        request = json.loads(line)
        method = request['method']
        if method == 'agent.capabilities':
            result = {{'video': {{'headless': '-agent-window' not in args, 'controlled_window': '-agent-window' in args}}}}
        elif method == 'test.argv':
            result = {{'argv': args}}
        elif method == 'test.never-reply':
            time.sleep(30)
        elif method == 'test.error':
            writer.write(json.dumps({{'jsonrpc': '2.0', 'id': request['id'], 'error': {{'code': -1, 'message': 'authored refusal', 'data': {{'reason': 'REFUSED'}}}}}}) + '\\n')
            writer.flush()
            continue
        else:
            result = {{'method': method, 'params': request['params']}}
        writer.write(json.dumps({{'jsonrpc': '2.0', 'id': request['id'], 'result': result}}) + '\\n')
        writer.flush()
''')
    executable.chmod(0o700)
    return executable


def test_owned_pipe_transport_preserves_native_errors_and_reaps_child(pipe_peer, tmp_path):
    rpc = DOSBoxRPC(pipe_peer, tmp_path)
    temporary = Path(rpc.temporary.name)
    assert rpc.capabilities['video']['headless'] is True
    assert rpc.call('test.echo', {'authored': True})['params'] == {'authored': True}
    with pytest.raises(DebuggerError, match=r'authored refusal \(REFUSED\)'):
        rpc.call('test.error')
    assert rpc.call('test.after-refusal')['method'] == 'test.after-refusal'
    receipt = rpc.close()
    assert receipt['process_reaped'] is True and rpc.process.poll() is not None
    assert not temporary.exists()


@pytest.mark.parametrize('window, window_scale', [
    (False, None), (True, None), (True, 2), (True, 3), (True, 4), (True, 5),
])
def test_window_scale_changes_only_visible_scaler_argv(pipe_peer, tmp_path, monkeypatch, window, window_scale):
    # The authored peer never opens SDL; this selects the visible preflight path.
    monkeypatch.setenv('SDL_VIDEODRIVER', 'x11')
    rpc = DOSBoxRPC(pipe_peer, tmp_path, window=window, window_scale=window_scale)
    try:
        expected = ['--defaultconf', '--noautoexec', '--noconfig',
                    '-set', 'dosbox quit warning=false', '-set', 'render doublescan=false',
                    '-set', 'cpu core=normal', '--agent-config', str(Path(rpc.temporary.name) / 'agent.env')]
        if window:
            expected += ['-agent-window']
            if window_scale is not None:
                expected += ['-set', f'render scaler=normal{window_scale}x']
        else:
            expected += ['--nogui', '--nomenu', '--noconsole', '--fastlaunch',
                         '-set', 'sdl videodriver=dummy', '-set', 'sdl output=surface',
                         '-set', 'sdl showmenu=false', '-set', 'sdl usesystemcursor=false',
                         '-set', 'mixer nosound=true', '-set', 'midi mididevice=none']
        assert rpc.call('test.argv')['argv'] == expected
    finally:
        assert rpc.close()['process_reaped'] is True


def test_uncertain_pipe_timeout_closes_channel_without_replaying(pipe_peer, tmp_path):
    rpc = DOSBoxRPC(pipe_peer, tmp_path)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match='without replay'):
        rpc.call('test.never-reply', timeout_ms=50)
    assert time.monotonic() - started < 1
    assert rpc.reader is None and rpc.writer is None
    with pytest.raises(DebuggerError, match='channel is closed'):
        rpc.call('test.never-reply', timeout_ms=50)
    assert rpc.close()['process_reaped'] is True


def test_standalone_runtime_has_no_fdisbull_imports():
    directory = Path(__file__).resolve().parents[1] / 'src' / 'dotbox'
    for name in ('native_rpc.py', 'native_session.py', 'dos_launch_profile.py',
                 'operation_budget.py', 'screenshot_codecs.py'):
        code = (directory / name).read_text()
        assert 'from fdisbull' not in code and 'import fdisbull' not in code
