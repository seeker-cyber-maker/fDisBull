"""Local Z content services have bounded exchange and owned-process cleanup."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player, ProcessBackend

ROOT = Path(__file__).resolve().parents[1]


def test_shared_scene_works_over_real_process_protocol(monkeypatch):
    monkeypatch.setenv('PYTHONPATH', str(ROOT / 'src'))
    backend = ProcessBackend([sys.executable, '-u', str(ROOT / 'src/fdisbull/il_scenes.py'),
                              str(ROOT / 'examples/z/key-and-gate.json')], timeout=3)
    try:
        player = Player(backend)
        assert 'Courtyard' in player.execute('l')
        assert player.execute('take key').startswith('Success:')
        assert player.execute('use key on gate').startswith('Success:')
        assert player.execute('n').startswith('Success:')
        assert 'Garden' in player.execute('l')
        assert backend.save('before-return')['status'] == 'saved'
        player.execute('s')
        assert backend.load('before-return')['status'] == 'restored'
        assert 'Garden' in player.execute('l')
    finally:
        backend.close()
    assert backend.worker.process.poll() is not None


@pytest.mark.parametrize('code', [
    'import time; time.sleep(10)',
    'import sys,time; sys.stdout.write("{"); sys.stdout.flush(); time.sleep(10)',
])
def test_silent_or_partial_backend_times_out_and_cannot_be_retried(code):
    backend = ProcessBackend([sys.executable, '-u', '-c', code], timeout=.15)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='outcome may be unknown'):
            backend.act({'verb': 'take', 'target': 'key', 'item': None, 'context_token': 'token'})
        assert time.monotonic() - started < 3
        assert backend.worker.process.poll() is not None
        with pytest.raises(EOFError, match='stopped'):
            backend.observe()
    finally:
        backend.close()


def test_malformed_response_is_private_and_stops_connection():
    backend = ProcessBackend([sys.executable, '-u', '-c', 'print("PRIVATE unstructured error")'], timeout=2)
    try:
        with pytest.raises(ValueError, match='Backend transport failed') as error:
            backend.observe()
        assert 'PRIVATE' not in str(error.value)
    finally:
        backend.close()


@pytest.mark.parametrize('value', [float('inf'), float('nan'), 0, -1, True, 61])
def test_bad_deadlines_rejected_before_launch(value):
    with pytest.raises(ValueError): ProcessBackend(['not-started'], timeout=value)


def test_cli_uses_content_service_without_a_debugger(monkeypatch):
    import os, shlex
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src') + ':' + str(ROOT/'player'))
    command = shlex.join([sys.executable, '-u', '-m', 'fdisbull.il_scenes', str(ROOT/'examples/z/key-and-gate.json')])
    result = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', command],
                            input='take key\nuse key on gate\nn\nl\nquit\n', text=True,
                            capture_output=True, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'Garden' in result.stdout and 'Success: You unlock the gate.' in result.stdout
    assert len(result.stdout) < 4096


def test_interactive_prompt_and_command_size_limit(monkeypatch, capsys):
    import io
    from fdisbull_player.__main__ import run
    from fdisbull.il_scenes import ILSceneBackend
    class Terminal(io.StringIO):
        def isatty(self): return True
    content = json.loads((ROOT/'examples/z/key-and-gate.json').read_text())
    backend = ILSceneBackend(content)
    monkeypatch.setattr(sys, 'stdin', Terminal('look\nquit\n'))
    run(Player(backend))
    assert capsys.readouterr().out.count('> ') == 2
    monkeypatch.setattr(sys, 'stdin', io.StringIO('x' * 4097))
    before = dict(backend.state)
    with pytest.raises(ValueError, match='4096-byte'):
        run(Player(backend))
    assert backend.state == before


def test_socket_peer_without_response_obeys_cli_timeout():
    import runpy
    quiet = runpy.run_path(str(ROOT/'examples/z/verify_release.py'))['quiet_player']
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        result = quiet(sys.executable, Path(folder), 'candidate', player_path=ROOT/'player')
    assert result == {'outer_timeout': False, 'exit_code': 1}


def test_quiet_model_protocol_keeps_full_transcript_out_of_stdout(tmp_path):
    import os, shlex
    driver = tmp_path/'driver.py'
    driver.write_text('import json,sys\nfor line in sys.stdin:\n print(json.dumps({"commands":["take key","use key on gate","n","look"],"narration":"private transcript text","done":True}),flush=True)\n')
    transcript = tmp_path/'turns.json'
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src') + ':' + str(ROOT/'player'))
    command = shlex.join([sys.executable, '-u', '-m', 'fdisbull.il_scenes', str(ROOT/'examples/z/key-and-gate.json')])
    process = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', command,
        '--backend-timeout', '3', '--live', '--agent-command', shlex.join([sys.executable, str(driver)]),
        '--max-turns', '1', '--transcript', str(transcript), '--quiet'],
        env=env, text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert process.stdout == 'Session status: agent_done\n'
    saved = json.loads(transcript.read_text())
    assert saved['turns'][0]['narration'] == 'private transcript text'
    assert 'Garden' in saved['turns'][0]['outcomes'][-1]['outcome']
