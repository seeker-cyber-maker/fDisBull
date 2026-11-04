"""Visible-mode launch contracts; fake transport is not a GUI acceptance test."""
import json
import os
from pathlib import Path
import sys

import pytest

from fdisbull.cli import main, parser
from fdisbull.dosbox_rpc import DOSBoxRPC, DebuggerError
from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.fixture
def transport(tmp_path, monkeypatch):
    executable = tmp_path / 'agent'
    executable.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ['FAKE_REPORT']).write_text(json.dumps({{'args': args, 'env': dict(os.environ)}}))
config = Path(args[args.index('--agent-config') + 1]).read_text()
endpoint = next(line.split('=', 1)[1] for line in config.splitlines() if line.startswith('endpoint='))
_, source, sink = endpoint.split(':')
with os.fdopen(int(source), 'r') as reader, os.fdopen(int(sink), 'w') as writer:
    for line in reader:
        request = json.loads(line)
        video = json.loads(os.environ.get('FAKE_VIDEO', '{{"headless": true}}'))
        writer.write(json.dumps({{'jsonrpc': '2.0', 'id': request['id'], 'result': {{'video': video}}}}) + '\\n')
        writer.flush()
''')
    executable.chmod(0o755)
    report = tmp_path / 'report.json'
    monkeypatch.setenv('FAKE_REPORT', str(report))
    return executable, report


def test_default_is_headless_and_silences_host_audio(transport, tmp_path, monkeypatch):
    executable, report = transport
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'coreaudio')
    monkeypatch.setenv('DOSBOX_SECRET', 'discard')
    rpc = DOSBoxRPC(executable, tmp_path)
    try:
        result = json.loads(report.read_text())
        assert '-agent-window' not in result['args'] and '--agent-window' not in result['args']
        assert result['env']['SDL_VIDEODRIVER'] == 'dummy'
        assert result['env']['SDL_AUDIODRIVER'] == 'dummy'
        assert result['args'].count('dosbox quit warning=false') == 1
        assert result['args'][result['args'].index('dosbox quit warning=false') - 1] == '-set'
        assert 'mixer nosound=true' in result['args']
        assert 'midi mididevice=none' in result['args']
        assert 'DOSBOX_SECRET' not in result['env']
        assert rpc.capabilities['video']['headless'] is True
    finally:
        rpc.close()


def test_window_option_reaches_the_same_agent_and_keeps_display_env(transport, tmp_path, monkeypatch):
    executable, report = transport
    monkeypatch.delenv('SDL_VIDEODRIVER', raising=False)
    monkeypatch.setenv('DISPLAY', ':77')
    monkeypatch.setenv('FAKE_VIDEO', '{"headless": false, "controlled_window": true}')
    rpc = DOSBoxRPC(executable, tmp_path, window=True)
    try:
        result = json.loads(report.read_text())
        assert any(arg in ('-agent-window', '--agent-window') for arg in result['args'])
        assert '--agent-config' in result['args']
        assert 'dosbox quit warning=false' not in result['args']
        assert result['env']['DISPLAY'] == ':77'
        assert 'SDL_VIDEODRIVER' not in result['env']
        assert rpc.capabilities['video']['headless'] is False
    finally:
        rpc.close()
    assert rpc.process.poll() is not None


@pytest.mark.parametrize('video', ['{}', '{"headless": true, "controlled_window": true}', '{"headless": "false", "controlled_window": true}', '{"headless": false}', '{"headless": false, "controlled_window": false}', '{"headless": false, "controlled_window": 1}'])
def test_window_rejects_backend_that_does_not_acknowledge_window(transport, tmp_path, monkeypatch, video):
    executable, report = transport
    monkeypatch.delenv('SDL_VIDEODRIVER', raising=False)
    monkeypatch.setenv('DISPLAY', ':77')
    monkeypatch.setenv('FAKE_VIDEO', video)
    with pytest.raises((ValueError, DebuggerError)):
        DOSBoxRPC(executable, tmp_path, window=True)
    assert report.exists()


@pytest.mark.parametrize('driver', ['dummy', 'offscreen', 'x11,dummy', 'wayland,offscreen'])
def test_window_does_not_silently_use_invisible_sdl_driver(transport, tmp_path, monkeypatch, driver):
    executable, report = transport
    monkeypatch.setenv('DISPLAY', ':77')
    monkeypatch.setenv('SDL_VIDEODRIVER', driver)
    with pytest.raises((ValueError, DebuggerError)):
        DOSBoxRPC(executable, tmp_path, window=True)
    assert not report.exists()


def test_cli_option_is_opt_in_and_forwarded(monkeypatch):
    assert not parser().parse_args(['debug', 'project', '--executable', 'agent', '--game-dir', 'game']).window
    observed = {}
    monkeypatch.setattr('fdisbull.cli.serve', lambda project, options: observed.update(project=project, options=options))
    main(['debug', 'project', '--executable', 'agent', '--game-dir', 'game', '--window'])
    assert observed['project'] == 'project'
    assert observed['options']['window'] is True


@pytest.mark.parametrize('backend', ['qemu-machine', 'dosbox-qemu', 'wine-qemu', 'ida-wine-qemu'])
def test_unsupported_backends_reject_window_before_spawn(tmp_path, backend):
    binary = tmp_path / 'GAME.EXE'
    binary.write_bytes(mz_file())
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        with pytest.raises(ValueError, match='(?i)window'):
            project.debugger('/does/not/exist', tmp_path, backend=backend, window=True)
        assert project.debug_runs(version=1)['runs'] == []


def test_window_keeps_source_hash_and_original_version_guards(tmp_path):
    binary = tmp_path / 'GAME.EXE'
    binary.write_bytes(mz_file())
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        binary.write_bytes(binary.read_bytes() + b'changed')
        with pytest.raises(ValueError, match='source hash'):
            project.debugger('/does/not/exist', tmp_path, window=True)
        child = project.patch('1000:0000', '90')['version']
        with pytest.raises(ValueError, match='unpatched'):
            project.debugger('/does/not/exist', tmp_path, version=child, window=True)
        assert project.debug_runs(version=1)['runs'] == []


def test_window_requires_display_on_linux_when_no_driver_is_selected(transport, tmp_path, monkeypatch):
    if not sys.platform.startswith('linux'):
        pytest.skip('Linux display environment guard')
    executable, report = transport
    monkeypatch.delenv('SDL_VIDEODRIVER', raising=False)
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    with pytest.raises((ValueError, DebuggerError), match='(?i)display'):
        DOSBoxRPC(executable, tmp_path, window=True)
    assert not report.exists()


@pytest.mark.parametrize('invalid', [None, 0, 1, 'true', [], {}])
def test_window_requires_boolean(tmp_path, invalid):
    binary = tmp_path / 'GAME.EXE'
    binary.write_bytes(mz_file())
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        with pytest.raises(ValueError, match='(?i)window'):
            project.debugger('/does/not/exist', tmp_path, window=invalid)


@pytest.mark.parametrize('window', [False, True])
def test_project_records_window_request_without_changing_paused_entry_contract(tmp_path, monkeypatch, window):
    binary = tmp_path / 'GAME.EXE'
    original = mz_file()
    binary.write_bytes(original)
    executable = tmp_path / 'backend'
    executable.write_bytes(b'not executed')
    calls = []

    class Process:
        pid = 123
        def poll(self): return 0

    class FakeRPC:
        process = Process()
        capabilities = {'video': {'headless': not window, 'controlled_window': window}}
        def __init__(self, executable, game_dir, *, on_spawn=None, window=False):
            calls.append(('open', window))
        def call(self, method, params=None):
            calls.append((method, params))
            if method == 'session.start': return {'session_id': 'test', 'state': 'stopped'}
            if method == 'state.get_registers':
                return {'cpu_mode': 'real', 'segments': {'cs': '1000'}, 'instruction_pointer': '0000'}
            if method == 'session.stop': return {'operation_id': 'stop'}
            if method == 'execution.wait': return {'state': 'stopped', 'running': False}
            raise AssertionError(method)
        def close(self): pass

    monkeypatch.setattr('fdisbull.debugger.DOSBoxRPC', FakeRPC)
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        with project.debugger(executable, tmp_path, window=window) as debug:
            assert debug.metadata['window_requested'] is window
            assert ('open', window) in calls
            start = next(params for method, params in calls if method == 'session.start')
            assert start['break_at'] == 'entry'
        assert project.debug_runs(version=1)['runs'][0]['metadata']['window_requested'] is window
    assert binary.read_bytes() == original


def test_real_existing_backend_default_still_launches_stopped(tmp_path):
    executable = os.environ.get('FDISBULL_DOSBOX')
    if not executable:
        pytest.skip('Set FDISBULL_DOSBOX for real native default regression')
    binary = tmp_path / 'GAME.EXE'
    original = mz_file(bytes.fromhex('b83412ebfe') + bytes(128), ss=0, sp=128)
    binary.write_bytes(original)
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        with project.debugger(executable, tmp_path) as debug:
            assert debug.metadata['window_requested'] is False
            assert debug.rpc.capabilities['video']['headless'] is True
            assert debug.status()['state'] == 'stopped'
            assert int(debug.registers()['instruction_pointer'], 16) == 0
        assert project.debug_runs(version=1)['runs'][0]['metadata']['window_requested'] is False
    assert binary.read_bytes() == original


def test_dos_endpoint_passes_window_only_for_native_backend(tmp_path):
    from fdisbull.ida_dosbox import Endpoint
    project = tmp_path / 'project'; project.write_bytes(b'')
    executable = tmp_path / 'backend'; executable.write_bytes(b'')
    endpoint = Endpoint(project, executable, tmp_path, window=True)
    try:
        assert endpoint.debug_options['window'] is True
        assert endpoint.debug_options['backend'] == 'dosbox'
    finally:
        endpoint.listener.close()
    with pytest.raises(ValueError, match='(?i)window'):
        Endpoint(project, executable, tmp_path, backend='dosbox-qemu', window=True)


def test_fork_state_forwards_window_to_owned_session(tmp_path, monkeypatch):
    binary = tmp_path / 'GAME.EXE'; binary.write_bytes(mz_file())
    seen = {}
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def load_state(self, artifact): seen['loaded'] = artifact
        def save_state(self, name): return {'name': name}
    monkeypatch.setattr('fdisbull.debug_state.apply_edits', lambda *args: {'registers': [], 'memory': []})
    with Project.create(tmp_path / 'game.fdb', binary) as project:
        monkeypatch.setattr(project, 'debug_state_info', lambda artifact: {'version': 1, 'sha256': 'fake', 'metadata': {}})
        def debugger(executable, game_dir, **options):
            seen.update(options)
            return Session()
        monkeypatch.setattr(project, 'debugger', debugger)
        result = project.debug_fork_state('old', 'agent', tmp_path, window=True,
                                          registers={'eax': {'expected': 0, 'value': 1}})
    assert seen['window'] is True and seen['loaded'] == 'old'
    assert result == {'name': 'derived.sav'}
    args = parser().parse_args(['debug-fork-state', 'p', 'a', '--executable', 'agent', '--game-dir', 'game', '--window'])
    assert args.window is True


def test_startup_pipe_failure_preserves_error_and_reaps_child(tmp_path):
    executable = tmp_path / 'early-close'
    executable.write_text(f'''#!{sys.executable}
import os, sys, time
from pathlib import Path
args = sys.argv[1:]
config = Path(args[args.index('--agent-config') + 1]).read_text()
endpoint = next(line.split('=', 1)[1] for line in config.splitlines() if line.startswith('endpoint='))
_, source, sink = endpoint.split(':')
os.close(int(source)); os.close(int(sink))
time.sleep(30)
''')
    executable.chmod(0o755)
    spawned = []
    with pytest.raises(OSError) as error:
        DOSBoxRPC(executable, tmp_path, on_spawn=spawned.append)
    assert error.value.errno != 9  # EBADF from a double-close must not mask the actual failure.
    assert spawned and spawned[0].poll() is not None

def test_dot_mode_cli_alias_preserves_window_contract():
    from fdisbull.cli import parser
    for command in ('debug',):
        base=[command,'example.fdb','--executable','dosbox','--game-dir','.']
        dot=vars(parser().parse_args(base+['--dot-mode']))
        old=vars(parser().parse_args(base+['--window']))
        assert dot==old and dot['window'] is True
