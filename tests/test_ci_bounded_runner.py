import hashlib
import importlib.util
from pathlib import Path
import sys
import time


spec = importlib.util.spec_from_file_location('bounded_ci_runner', Path(__file__).resolve().parents[1] / 'scripts/ci/recovery_source.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def test_blocked_stdin_is_inside_the_command_deadline(tmp_path):
    started = time.monotonic()
    result = runner.run_command([sys.executable, '-c', 'import time;time.sleep(3)'],
        cwd=tmp_path, input_bytes=b'x' * (2 * 1024 * 1024), timeout=0.1)
    assert result['timed_out'] is True and result['returncode'] != 0
    assert time.monotonic() - started < 1.5
    assert result['overflow'] is False


def test_input_and_both_output_streams_make_progress_together(tmp_path):
    payload = b'finite-payload' * 150000
    script = "import sys,hashlib;sys.stdout.buffer.write(b'x'*100000);sys.stdout.flush();sys.stderr.buffer.write(b'y'*100000);sys.stderr.flush();data=sys.stdin.buffer.read();print(hashlib.sha256(data).hexdigest())"
    result = runner.run_command([sys.executable, '-c', script], cwd=tmp_path, input_bytes=payload, timeout=5)
    assert result['returncode'] == 0 and result['timed_out'] is False and result['overflow'] is False
    assert result['stdout'] == b'x' * 100000 + hashlib.sha256(payload).hexdigest().encode() + b'\n'
    assert result['stderr'] == b'y' * 100000


def test_output_overflow_stops_only_the_owned_command_and_caps_bytes(tmp_path):
    script = "import sys,time;sys.stdout.buffer.write(b'x'*(2*1024*1024+65536));sys.stdout.flush();time.sleep(3)"
    result = runner.run_command([sys.executable, '-c', script], cwd=tmp_path, timeout=5)
    assert result['overflow'] is True and result['returncode'] != 0
    assert result['stdout'] == b'x' * runner.LIMIT
    assert result['timed_out'] is False


def test_timeout_still_applies_after_all_standard_streams_close(tmp_path):
    script = 'import os,time;os.close(1);os.close(2);time.sleep(3)'
    started = time.monotonic()
    result = runner.run_command([sys.executable, '-c', script], cwd=tmp_path, timeout=0.1)
    assert result['timed_out'] is True and result['returncode'] != 0
    assert time.monotonic() - started < 1.5
