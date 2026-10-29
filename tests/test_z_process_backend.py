"""Local Z content services have bounded exchange and owned-process cleanup."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
from fixtures_z_scenes import scene_definition, write_scene, quiet_player

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player, ProcessBackend

ROOT = Path(__file__).resolve().parents[1]


def test_shared_scene_works_over_real_process_protocol(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHONPATH', str(ROOT / 'src'))
    backend = ProcessBackend([sys.executable, '-u', str(ROOT / 'src/fdisbull/il_scenes.py'),
                              str(write_scene(tmp_path/'scene.json'))], timeout=3)
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


def test_normal_close_delivers_eof_and_waits_for_receipt(tmp_path):
    receipt = tmp_path/'closed.json'
    code = ('import sys,time,pathlib; '
            'sys.stdin.readline(); print("{}",flush=True); '
            'sys.stdin.read(); time.sleep(.1); '
            'pathlib.Path(sys.argv[1]).write_text("clean EOF")')
    backend = ProcessBackend([sys.executable,'-u','-c',code,str(receipt)],timeout=2)
    backend.observe()
    backend.close()
    assert receipt.read_text() == 'clean EOF'
    assert backend.worker.process.returncode == 0
    backend.close()  # Finalization is idempotent.


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX owned process group')
def test_crashed_worker_does_not_leave_its_child_holding_the_pipe(tmp_path):
    import os,signal
    pidfile=tmp_path/'child.pid'
    code = ('import subprocess,sys,pathlib; '
            'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
            'pathlib.Path(sys.argv[1]).write_text(str(p.pid)); '
            'sys.stdin.readline(); print("{}",flush=True); sys.stdin.read()')
    backend=ProcessBackend([sys.executable,'-u','-c',code,str(pidfile)],timeout=2)
    backend.observe()
    child=int(pidfile.read_text())
    pipe=os.dup(backend.worker.process.stdout.fileno())
    os.kill(backend.worker.process.pid,signal.SIGKILL)
    backend.worker.process.wait(timeout=2)
    try:
        backend.close()
        # An inherited pipe closes only after every writer in the owned group stops.
        import selectors
        with selectors.DefaultSelector() as ready:
            ready.register(pipe,selectors.EVENT_READ)
            assert ready.select(.5)
            assert os.read(pipe,1) == b''
    finally:
        os.close(pipe)
        try: os.kill(child,signal.SIGKILL)
        except ProcessLookupError: pass


@pytest.mark.parametrize('value', [float('inf'), float('nan'), 0, -1, True, 61])
def test_bad_deadlines_rejected_before_launch(value):
    with pytest.raises(ValueError): ProcessBackend(['not-started'], timeout=value)


def test_cli_uses_content_service_without_a_debugger(monkeypatch, tmp_path):
    import os, shlex
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src') + ':' + str(ROOT/'player'))
    command = shlex.join([sys.executable, '-u', '-m', 'fdisbull.il_scenes', str(write_scene(tmp_path/'scene.json'))])
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
    content = scene_definition()
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
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        result = quiet_player(sys.executable, Path(folder), 'candidate', player_path=ROOT/'player')
    assert result == {'outer_timeout': False, 'exit_code': 1}


def test_quiet_model_protocol_keeps_full_transcript_out_of_stdout(tmp_path):
    import os, shlex
    driver = tmp_path/'driver.py'
    driver.write_text('import json,sys\nfor line in sys.stdin:\n print(json.dumps({"commands":["take key","use key on gate","n","look"],"narration":"private transcript text","done":True}),flush=True)\n')
    transcript = tmp_path/'turns.json'
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src') + ':' + str(ROOT/'player'))
    command = shlex.join([sys.executable, '-u', '-m', 'fdisbull.il_scenes', str(write_scene(tmp_path/'scene.json'))])
    process = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', command,
        '--backend-timeout', '3', '--live', '--agent-command', shlex.join([sys.executable, str(driver)]),
        '--max-turns', '1', '--transcript', str(transcript), '--quiet'],
        env=env, text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert process.stdout == 'Session status: agent_done\n'
    saved = json.loads(transcript.read_text())
    assert saved['turns'][0]['narration'] == 'private transcript text'
    assert 'Garden' in saved['turns'][0]['outcomes'][-1]['outcome']
