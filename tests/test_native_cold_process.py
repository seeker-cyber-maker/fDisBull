"""New recovery helper tests; retained real children plus explicit error controls."""
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from support.native_cold_process import run_owned_cold
from support import native_cold_process as cold


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Explicit POSIX process-group contract')


CHILD = r'''
import json,signal,subprocess,sys,time
from pathlib import Path
p=Path(sys.argv[1])
grandchild=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
def stop(signum, frame):
    grandchild.terminate()
    grandchild.wait(timeout=2)
    (p/'grandchild-reaped.json').write_text(json.dumps({'pid':grandchild.pid,'reaped':grandchild.poll() is not None}))
    raise SystemExit(143)
signal.signal(signal.SIGTERM,stop)
(p/'grandchild-ready.json').write_text(json.dumps({'pid':grandchild.pid}))
print('authored cold child and grandchild ready',flush=True)
while True: time.sleep(.05)
'''


def _child(tmp_path):
    script = tmp_path / 'cold_child.py'
    script.write_text(CHILD)
    return [sys.executable, str(script), str(tmp_path)]


def _assert_clean(tmp_path):
    receipt = json.loads((tmp_path / 'cold-process.json').read_text())
    assert receipt['leader_reaped'] and receipt['group_gone'] and not receipt['cleanup_error']
    assert receipt['signals'] == ['TERM', 'KILL'] and not receipt['passed']
    grandchild = json.loads((tmp_path / 'grandchild-reaped.json').read_text())
    assert grandchild['reaped'] and grandchild['pid'] != receipt['pid']
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild['pid'], 0)
    return receipt


def test_timeout_reaps_real_child_and_its_grandchild_and_retains_log(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        run_owned_cold(_child(tmp_path), cwd=tmp_path, env=os.environ.copy(),
            log_path=tmp_path/'cold.log', receipt_path=tmp_path/'cold-process.json', timeout=.7, grace=.5)
    receipt = _assert_clean(tmp_path)
    assert receipt['timed_out'] and receipt['interrupted'] is None
    assert 'authored cold child and grandchild ready' in (tmp_path/'cold.log').read_text()


def test_outer_term_reaches_the_separately_owned_cold_group(tmp_path):
    _child(tmp_path)
    supervisor = tmp_path / 'supervisor.py'
    supervisor.write_text('''import os,sys\nfrom support.native_cold_process import run_owned_cold\nfrom pathlib import Path\np=Path(sys.argv[1])\nrun_owned_cold([sys.executable,str(p/'cold_child.py'),str(p)],cwd=p,env=os.environ.copy(),log_path=p/'cold.log',receipt_path=p/'cold-process.json',timeout=30,grace=.5)\n''')
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).parent), 'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, str(supervisor), str(tmp_path)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        end = time.monotonic() + 5
        while not (tmp_path/'grandchild-ready.json').exists():
            assert process.poll() is None and time.monotonic() < end
            time.sleep(.01)
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=5)
        assert process.returncode == 143, out + err
        receipt = _assert_clean(tmp_path)
        assert receipt['interrupted'] == 'SystemExit' and not receipt['timed_out']
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        # Do not signal a group identifier recovered from a receipt after its
        # supervisor has exited. The helper owns that group's cleanup/reap;
        # a failed cleanup stays failed instead of risking a reused PID/PGID.


def test_success_reaps_leader_after_the_final_owned_group_guard(tmp_path):
    result, receipt = run_owned_cold([sys.executable, '-c', 'print("cold success")'],
        cwd=tmp_path, env=os.environ.copy(), log_path=tmp_path/'cold.log',
        receipt_path=tmp_path/'cold-process.json', timeout=2, grace=.5)
    assert result.returncode == 0 and result.stdout.strip() == 'cold success'
    assert receipt['passed'] and receipt['leader_reaped'] and receipt['group_gone']
    assert receipt['signals'] == ['KILL'] and receipt['observed_exit_status'] == 0


def test_term_during_popen_return_cannot_lose_the_created_group(tmp_path):
    supervisor = tmp_path/'spawn_window.py'
    supervisor.write_text('''import json,os,signal,subprocess,sys\nfrom pathlib import Path\nfrom support import native_cold_process as cold\np=Path(sys.argv[1]);created=[];original=subprocess.Popen\ndef spawn(*args,**kwargs):\n child=original(*args,**kwargs);created.append(child)\n os.kill(os.getpid(),signal.SIGTERM)\n return child\ncold.subprocess.Popen=spawn\ntry:\n cold.run_owned_cold([sys.executable,'-c','import time;time.sleep(120)'],cwd=p,env=os.environ.copy(),log_path=p/'cold.log',receipt_path=p/'cold-process.json',timeout=5,grace=.5)\nfinally:\n fallback=False\n for child in created:\n  if child.poll() is None:\n   fallback=True;os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)\n (p/'fixture-fallback.json').write_text(json.dumps({'used':fallback,'all_reaped':all(c.poll() is not None for c in created)}))\n''')
    env = {**os.environ, 'PYTHONPATH':str(Path(__file__).parent),'PYTHONDONTWRITEBYTECODE':'1'}
    child = subprocess.run([sys.executable,str(supervisor),str(tmp_path)],env=env,
        capture_output=True,text=True,timeout=5)
    assert child.returncode==143,child.stdout+child.stderr
    fallback=json.loads((tmp_path/'fixture-fallback.json').read_text())
    assert fallback['all_reaped']
    receipt=json.loads((tmp_path/'cold-process.json').read_text())
    assert receipt['leader_reaped'] and receipt['group_gone']
    assert receipt['interrupted']=='SystemExit' and not fallback['used']


class _OwnedProcess:
    pid = 87654321

    def __init__(self):
        self.returncode = None
        self.killed = False

    def wait(self, timeout):
        self.returncode = -9 if self.killed else 0
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True


def test_absent_group_signal_still_reaps_its_owned_leader(tmp_path, monkeypatch):
    process = _OwnedProcess()
    monkeypatch.setattr(cold, '_exit_status', lambda process, timeout: 0)
    def absent(pgid, sig):
        assert pgid == process.pid
        if sig:
            assert process.returncode is None
        raise ProcessLookupError(errno.ESRCH, 'authored absent group')
    monkeypatch.setattr(cold.os, 'killpg', absent)
    receipt = dict(signals=[], leader_reaped=False, group_gone=False, cleanup_error=None)
    cold._cleanup(process, .1, receipt)
    assert receipt['leader_reaped'] and receipt['group_gone']
    assert receipt['group_signals'] == [dict(signal='KILL', outcome='absent')]
    assert not receipt['cleanup_error']


@pytest.mark.parametrize('error_number', [errno.EPERM, errno.EACCES, errno.EIO])
def test_group_signal_never_turns_other_errors_into_absence(monkeypatch, error_number):
    process = _OwnedProcess()
    def refused(pgid, sig):
        raise OSError(error_number, 'authored signal refusal')
    monkeypatch.setattr(cold.os, 'killpg', refused)
    receipt = dict(signals=[])
    with pytest.raises(OSError) as error:
        cold._signal_owned_group(process, 'KILL', receipt)
    assert error.value.errno == error_number
    assert receipt['signals'] == [] and 'group_signals' not in receipt


def test_permission_denied_group_observation_is_not_gone(monkeypatch):
    def refused(pgid, sig):
        assert sig == 0
        raise PermissionError(errno.EPERM, 'authored observation refusal')
    monkeypatch.setattr(cold.os, 'killpg', refused)
    with pytest.raises(PermissionError):
        cold._exists(87654321)


def test_cleanup_permission_error_keeps_primary_timeout_and_failed_receipt(tmp_path, monkeypatch):
    process = _OwnedProcess()
    monkeypatch.setattr(cold.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(cold, '_exit_status', lambda process, timeout: None)
    def refused(pgid, sig):
        raise PermissionError(errno.EPERM, 'authored cleanup refusal')
    monkeypatch.setattr(cold.os, 'killpg', refused)
    with pytest.raises(subprocess.TimeoutExpired):
        run_owned_cold(['authored-fake-child'], cwd=tmp_path, env={},
            log_path=tmp_path/'cold.log', receipt_path=tmp_path/'cold-process.json',
            timeout=.1, grace=.1)
    receipt = json.loads((tmp_path/'cold-process.json').read_text())
    assert receipt['timed_out'] and receipt['leader_reaped']
    assert not receipt['passed'] and not receipt['group_gone']
    assert 'PermissionError' in receipt['cleanup_error'] and process.killed


@pytest.mark.parametrize('failure_mode', ['initial-and-final', 'timeout-final', 'success-final'])
def test_receipt_failure_preserves_primary_and_reaps_real_owned_child(tmp_path, monkeypatch, failure_mode):
    receipt_path = tmp_path/'cold-process.json'
    original_write = Path.write_text
    initial_failure = OSError(errno.ENOSPC, 'authored initial receipt failure')
    final_failure = OSError(errno.EIO, 'authored final receipt failure')
    writes = []
    def write(path, text, *args, **kwargs):
        if path != receipt_path:
            return original_write(path, text, *args, **kwargs)
        value = json.loads(text)
        writes.append(value)
        if value['state'] == 'running' and failure_mode == 'initial-and-final':
            raise initial_failure
        if value['state'] == 'finished':
            raise final_failure
        return original_write(path, text, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    command = [sys.executable, '-c', 'pass' if failure_mode == 'success-final' else
               'import time; time.sleep(120)']
    expected = subprocess.TimeoutExpired if failure_mode == 'timeout-final' else OSError
    previous_handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(expected) as caught:
        run_owned_cold(command, cwd=tmp_path, env=os.environ.copy(),
            log_path=tmp_path/'cold.log', receipt_path=receipt_path, timeout=.3, grace=.5)
    if failure_mode == 'initial-and-final':
        assert caught.value is initial_failure
    elif failure_mode == 'success-final':
        assert caught.value is final_failure
    else:
        assert caught.value.timeout == .3
    receipt = caught.value.cold_process_receipt
    assert receipt['leader_reaped'] and receipt['group_gone'] and not receipt['passed']
    assert receipt['state'] == 'finished' and 'authored final receipt failure' in receipt['receipt_error']
    assert not receipt['cleanup_error'] and signal.getsignal(signal.SIGTERM) == previous_handler
    assert [record['state'] for record in writes] == ['running', 'finished']
    if failure_mode != 'success-final':
        assert any('receipt persistence failed' in note for note in caught.value.__notes__)
    with pytest.raises(ProcessLookupError):
        os.kill(receipt['pid'], 0)


@pytest.mark.parametrize('timeout,grace', [
    (True, .1), (float('nan'), .1), (float('inf'), .1), (0, .1), (151, .1),
    (1, True), (1, float('nan')), (1, 0), (1, 3),
])
def test_invalid_budget_refuses_before_spawn(tmp_path, monkeypatch, timeout, grace):
    def unexpected(*args, **kwargs):
        raise AssertionError('Invalid budget spawned a child')
    monkeypatch.setattr(cold.subprocess, 'Popen', unexpected)
    with pytest.raises(ValueError):
        run_owned_cold(['unused'], cwd=tmp_path, env={},
            log_path=tmp_path/'cold.log', receipt_path=tmp_path/'cold-process.json',
            timeout=timeout, grace=grace)
    assert list(tmp_path.iterdir()) == []
