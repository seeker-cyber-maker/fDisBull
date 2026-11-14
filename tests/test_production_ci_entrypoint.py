import importlib.util
import json
import hashlib
import os
import signal
import subprocess
import time
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts' / 'ci'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('production_ci_entrypoint', SCRIPTS / 'production-ci.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def test_status_returns_only_compact_contract_without_runtime_start(monkeypatch, capsys):
    monkeypatch.setattr(entry, 'installation_config', lambda: {'enabled': True})
    def no_factory(*args): raise AssertionError('runtime started during GET')
    monkeypatch.setattr(entry, 'runtime_factory', no_factory)
    class Service:
        def status(self): return {'schema_version': 1, 'pending_work': True}
    monkeypatch.setattr(entry, 'service_factory', lambda config: Service())
    assert entry.main(['status']) == 0
    assert json.loads(capsys.readouterr().out) == {'schema_version': 1, 'pending_work': True}


def test_status_failure_stays_unknown_without_secret_or_write(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(entry, 'STATE', tmp_path)
    def unavailable(): raise ValueError('private-token-content')
    monkeypatch.setattr(entry, 'installation_config', unavailable)
    assert entry.main(['status']) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'schema_version': 1, 'state': 'unknown'}
    assert 'private-token-content' not in output.out + output.err
    assert list(tmp_path.iterdir()) == []


def test_run_failure_is_durable_and_does_not_disclose_exception(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(entry, 'STATE', tmp_path)
    monkeypatch.setattr(entry, 'installation_config', lambda: {'enabled': True})
    class Service:
        def run(self): raise RuntimeError('untrusted-private-trace-value')
    monkeypatch.setattr(entry, 'service_factory', lambda config: Service())
    assert entry.main(['run']) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'status': 'attention', 'error_type': 'RuntimeError'}
    assert 'untrusted-private-trace-value' not in output.out + output.err
    blocker = json.loads((tmp_path / 'blocked.json').read_text())
    receipt = Path(blocker['receipt_path'])
    assert receipt.is_file() and receipt.stat().st_mode & 0o077 == 0
    assert 'untrusted-private-trace-value' not in receipt.read_text()


def test_cli_does_not_accept_or_echo_arbitrary_config_command_or_job(monkeypatch, capsys):
    def no_config(): raise AssertionError('arguments escaped fixed command')
    monkeypatch.setattr(entry, 'installation_config', no_config)
    for args in [['--config', '/arbitrary', 'run'], ['exec', 'shell'], ['run', '--token', 'SYNTHETIC-SECRET-SENTINEL']]:
        with pytest.raises(SystemExit) as result: entry.main(args)
        assert result.value.code == 2
    captured = capsys.readouterr()
    assert 'SYNTHETIC-SECRET-SENTINEL' not in captured.err + captured.out
    assert '/arbitrary' not in captured.err + captured.out


def test_service_unit_keeps_one_owner_and_has_no_automatic_restart():
    unit = (SCRIPTS / 'fdisbull-ci-production.service').read_text()
    assert 'ExecStart=/usr/bin/python3 /usr/local/libexec/fdisbull-ci-production.py run' in unit
    assert 'Restart=no' in unit and 'KillMode=process' in unit
    assert 'TimeoutStartSec=infinity' in unit  # Cleanup attention hold retains its lease.
    assert 'TimeoutStopSec=infinity' in unit and 'SendSIGKILL=no' in unit
    assert 'User=root' in unit and 'UMask=0077' in unit


def test_status_source_manifest_cannot_omit_control_or_native_entrypoint(tmp_path):
    manifest = tmp_path / 'production_manifest.py'
    manifest.write_text("MODULES = frozenset({'production_manifest.py', 'production-ci.py', 'production_control.py'})\n")
    copied_entry = tmp_path / 'production-ci.py'; copied_entry.write_bytes(Path(entry.__file__).read_bytes())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (manifest, copied_entry)}
    config = {'module_sha256': hashes, 'entrypoint_sha256': hashes['production-ci.py']}
    with pytest.raises(ValueError, match='manifest incomplete'):
        entry.verify_sources(config, tmp_path, os.getuid())
    source = tmp_path / 'production_control.py'; source.write_text('# authenticated control fixture\n')
    hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    entry.verify_sources(config, tmp_path, os.getuid())
    config['entrypoint_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='entrypoint differs'):
        entry.verify_sources(config, tmp_path, os.getuid())


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix service signal and flock contract')
def test_managed_sigterm_does_not_release_live_executor_lease(tmp_path):
    script = r'''
import importlib.util, pathlib, sys, time
scripts, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('native_entry', scripts/'production-ci.py')
entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
from production_control import executor_lease
entry.installation_config = lambda: {'enabled': True}
class Service:
    def run(self):
        with executor_lease(root/'executor.lock'):
            (root/'ready').write_text('lease held')
            while not (root/'finish').exists(): time.sleep(0.01)
        return {'status':'complete'}
entry.service_factory = lambda config: Service()
raise SystemExit(entry.main(['run']))
'''
    lock = tmp_path / 'executor.lock'; lock.touch()
    proc = subprocess.Popen([sys.executable, '-c', script, str(SCRIPTS), str(tmp_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / 'ready').exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / 'ready').exists()
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.05)
        assert proc.poll() is None
        import production_control
        with pytest.raises(BlockingIOError):
            with production_control.executor_lease(lock): pass
        (tmp_path / 'finish').write_text('owned work and cleanup verified')
        out, err = proc.communicate(timeout=5)
        assert proc.returncode == 0 and json.loads(out)['status'] == 'complete'
    finally:
        if proc.poll() is None: proc.kill(); proc.communicate(timeout=5)
