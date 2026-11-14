import importlib.util
import json
import hashlib
import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts' / 'ci'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('production_ci_entrypoint', SCRIPTS / 'production-ci.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class FakeStopJournal:
    """A temporary native-append protocol fixture; no notification sender."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE events (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        self.payloads = []
        self.lose_first_ack = False

    @staticmethod
    def reply(payload, already_present=False):
        event = json.loads(payload)
        native = 'ci_' + hashlib.sha256(event['dedupe_key'].encode()).hexdigest()[:40]
        return {'stage': 'journaled', 'phase': 'attention', 'incident_id': native,
                'event_id': 'conn_' + native + '_attention', 'execution_performed': False,
                'already_present': already_present, 'delivery_status': 'not_observed_here'}

    def __call__(self, argv, **kwargs):
        assert argv[-2:] == ['/usr/local/libexec/ci_incident.py', 'append']
        assert kwargs['timeout'] == 30 and kwargs['check'] is False
        payload = kwargs['input']; self.payloads.append(payload)
        event = json.loads(payload)
        assert set(event) == {'dedupe_key', 'phase', 'reason', 'test', 'context'}
        assert event['phase'] == 'attention' and event['reason'] == 'ci_executor_unavailable'
        assert set(event['context']) == {'provider', 'project', 'run_id', 'job_id', 'commit_sha', 'job_name', 'receipt_path'}
        reply = self.reply(payload)
        old = self.db.execute('SELECT payload FROM events WHERE id=?', (reply['event_id'],)).fetchone()
        if old:
            assert old[0] == payload
        else:
            self.db.execute('INSERT INTO events VALUES (?,?)', (reply['event_id'], payload))
            self.db.commit()
        if self.lose_first_ack and len(self.payloads) == 1:
            return SimpleNamespace(returncode=1, stdout=b'', stderr=b'')
        return SimpleNamespace(returncode=0, stdout=json.dumps(self.reply(payload, old is not None)).encode(), stderr=b'')


@pytest.fixture
def stop_journal(tmp_path, monkeypatch):
    root = tmp_path / 'production'; root.mkdir(mode=0o700)
    monkeypatch.setattr(entry, 'STATE', root)
    journal = FakeStopJournal(tmp_path / 'fake-native-journal.sqlite')
    yield root, journal
    journal.db.close()


def append_stop(root, journal, **kwargs):
    return entry.append_controller_stop(root, 'fixture-request', 'bootstrap', 'RuntimeError',
                                        deadline_epoch=1700000000, test=True, proof={'kind': 'local-test'},
                                        runner=journal, **kwargs)


def test_controller_stop_uses_domain_separated_native_identity_and_neutral_context(stop_journal):
    root, journal = stop_journal
    result = append_stop(root, journal)
    stop_id = hashlib.sha256(b'controller-stop:bootstrap:fixture-request').hexdigest()
    snapshot = root / 'incidents' / stop_id / 'controller-attention-state.json'
    event = json.loads(journal.payloads[0]); context = event['context']
    assert event['dedupe_key'] == 'controller-attention:' + stop_id
    assert event['test'] is True and context['receipt_path'] == str(snapshot)
    assert context == {'provider': 'github', 'project': 'seeker-cyber-maker/fDisBull',
                       'run_id': 'controller', 'job_id': 'bootstrap', 'job_name': 'CI controller bootstrap',
                       'commit_sha': hashlib.sha256(Path(entry.__file__).read_bytes()).hexdigest(),
                       'receipt_path': str(snapshot)}
    data = json.loads(snapshot.read_text())
    assert data['status'] == 'attention' and data['stage'] == 'bootstrap' and data['error_type'] == 'RuntimeError'
    assert data['context_identity'] == 'controller-code-fingerprint'
    assert data['controller_code_sha256'] == context['commit_sha']
    assert data['deadline_epoch'] == 1700000000
    assert snapshot.stat().st_mode & 0o777 == 0o400
    assert result['stage'] == 'journaled' and result['phase'] == 'attention'
    assert result['execution_performed'] is False and result['delivery_status'] == 'not_observed_here'
    assert result['snapshot_sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_controller_stop_reentry_preserves_snapshot_and_deduplicates_native_event(stop_journal):
    root, journal = stop_journal
    first = append_stop(root, journal)
    snapshot = Path(first['receipt_path']); original = snapshot.read_bytes(); info = snapshot.stat()
    second = append_stop(root, journal)
    assert second == first and snapshot.read_bytes() == original
    assert snapshot.stat().st_ino == info.st_ino and snapshot.stat().st_mtime_ns == info.st_mtime_ns
    assert len(set(journal.payloads)) == 1
    assert journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1


def test_controller_stop_ack_loss_retries_only_same_local_append(stop_journal):
    root, journal = stop_journal; journal.lose_first_ack = True
    result = append_stop(root, journal)
    assert result['stage'] == 'journaled'
    assert len(journal.payloads) == 2 and journal.payloads[0] == journal.payloads[1]
    assert journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1


@pytest.mark.parametrize('field,value', [('stage', 'delivered'), ('phase', 'recovered'),
    ('incident_id', 'ci_' + '0' * 40), ('event_id', 'wrong'), ('execution_performed', True),
    ('already_present', 0), ('delivery_status', 'delivered')])
def test_controller_stop_structured_native_reply_mismatch_fails_without_retry(stop_journal, field, value):
    root, journal = stop_journal; calls = []
    def bad_reply(argv, **kwargs):
        calls.append(kwargs['input']); reply = journal.reply(kwargs['input']); reply[field] = value
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode(), stderr=b'')
    with pytest.raises(RuntimeError): append_stop(root, bad_reply)
    assert len(calls) == 1 and journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['exception', 'unstructured', 'structured'])
def test_controller_stop_unavailable_append_has_bounded_idempotent_attempts(stop_journal, failure):
    root, journal = stop_journal; calls = []
    def failed(argv, **kwargs):
        calls.append(kwargs['input'])
        if failure == 'exception': raise OSError('fixture unavailable')
        return SimpleNamespace(returncode=1, stdout=b'{"stage":"rejected"}' if failure == 'structured' else b'unknown', stderr=b'')
    with pytest.raises(RuntimeError): append_stop(root, failed)
    assert len(calls) == (1 if failure == 'structured' else 2) and len(set(calls)) == 1
    event = json.loads(calls[0]); snapshot = Path(event['context']['receipt_path'])
    unresolved = snapshot.with_name('controller-stop-notification-unresolved.json')
    original = unresolved.read_bytes(); info = unresolved.stat()
    notice = json.loads(original)
    assert notice['status'] == 'attention' and notice['execution_performed'] is False
    assert notice['delivery_status'] == 'not_observed_here'
    assert notice['snapshot_sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert info.st_mode & 0o777 == 0o400
    calls.clear()
    with pytest.raises(RuntimeError): append_stop(root, failed)
    assert unresolved.read_bytes() == original and unresolved.stat().st_ino == info.st_ino
    assert unresolved.stat().st_mtime_ns == info.st_mtime_ns
    assert len(calls) == (1 if failure == 'structured' else 2) and len(set(calls)) == 1


@pytest.mark.parametrize('damage', ['snapshot-bytes', 'binding-bytes', 'snapshot-mode',
                                  'snapshot-writable', 'binding-writable', 'snapshot-link', 'directory-link'])
def test_controller_stop_rejects_changed_or_unsafe_snapshot(stop_journal, damage):
    root, journal = stop_journal
    result = append_stop(root, journal); snapshot = Path(result['receipt_path'])
    journal.payloads.clear()
    if damage == 'binding-bytes':
        bindings = list(snapshot.parent.glob('*binding*.json')); assert len(bindings) == 1
        path = bindings[0]; path.chmod(0o600); path.write_bytes(path.read_bytes() + b' ')
    elif damage == 'snapshot-bytes':
        snapshot.chmod(0o600); snapshot.write_bytes(snapshot.read_bytes() + b' ')
    elif damage == 'snapshot-mode': snapshot.chmod(0o644)
    elif damage == 'snapshot-writable': snapshot.chmod(0o600)
    elif damage == 'binding-writable': snapshot.with_name('controller-attention-binding.json').chmod(0o600)
    elif damage == 'snapshot-link':
        saved = snapshot.with_name('original.json'); snapshot.rename(saved); snapshot.symlink_to(saved)
    else:
        directory = snapshot.parent; saved = directory.with_name('original'); directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
    with pytest.raises((ValueError, OSError)): append_stop(root, journal)
    assert not journal.payloads


@pytest.mark.parametrize('changed', ['error', 'proof', 'test', 'deadline'])
def test_controller_stop_reentry_refuses_conflicting_identity_or_claim(stop_journal, changed):
    root, journal = stop_journal; append_stop(root, journal); journal.payloads.clear()
    values = {'deadline_epoch': 1700000000, 'test': True, 'proof': {'kind': 'local-test'}}
    error = 'RuntimeError'
    if changed == 'error': error = 'ValueError'
    elif changed == 'proof': values['proof'] = {'kind': 'different'}
    elif changed == 'test': values['test'] = False
    else: values['deadline_epoch'] += 1
    with pytest.raises(ValueError):
        entry.append_controller_stop(root, 'fixture-request', 'bootstrap', error, runner=journal, **values)
    assert not journal.payloads


def test_controller_stop_requires_fixed_private_root_and_owned_files(stop_journal, monkeypatch):
    root, journal = stop_journal; root.chmod(0o755)
    with pytest.raises(ValueError): append_stop(root, journal)
    root.chmod(0o700)
    with monkeypatch.context() as patch:
        patch.setattr(entry.os, 'geteuid', lambda: root.stat().st_uid + 1)
        with pytest.raises(ValueError): append_stop(root, journal)
    other = root.with_name('other'); other.mkdir(mode=0o700)
    with pytest.raises(ValueError): append_stop(other, journal)
    assert not journal.payloads


def test_bootstrap_failure_reuses_original_blocked_error_and_native_event(stop_journal):
    root, journal = stop_journal
    blocked = root / 'blocked.json'; original = b'{"status":"attention","error_type":"RuntimeError","observed_epoch":1}\n'
    blocked.write_bytes(original); blocked.chmod(0o600)
    entry.record_failure('ValueError', runner=journal)
    entry.record_failure('TypeError', runner=journal)
    assert blocked.read_bytes() == original
    assert len(set(journal.payloads)) == 1 and journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1
    event = json.loads(journal.payloads[0]); snapshot = json.loads(Path(event['context']['receipt_path']).read_text())
    assert snapshot['error_type'] == 'RuntimeError'
    assert 'ValueError' not in json.dumps(snapshot) and 'TypeError' not in json.dumps(snapshot)


@pytest.mark.parametrize('schema',['fdisbull-one-module-maintenance-block-1','fdisbull-control-components-maintenance-block-1'])
def test_planned_module_maintenance_does_not_emit_bootstrap_failure(stop_journal,monkeypatch,schema):
    root, journal = stop_journal
    case=root/'maintenance'/'fixture-upgrade';case.mkdir(parents=True,mode=0o700)
    monkeypatch.setattr(entry,'MAINTENANCE',case.parent)
    blocked = root / 'blocked.json'
    marker={'schema':schema,'case':str(case),'component_commit':'a'*40,'old_config_sha256':'b'*64,
            'old_state_sha256':'c'*64,'history_before_sha256':'d'*64}
    if schema=='fdisbull-control-components-maintenance-block-1':
        marker['component_sha256']={'production-ci.py':'e'*64,'production_runtime.py':'f'*64}
    original=json.dumps(marker).encode()+b'\n'
    blocked.write_bytes(original); blocked.chmod(0o600)
    before = set(root.iterdir())
    assert entry.record_failure('ValueError', runner=journal)=={'stage':'maintenance-suppressed'}
    assert not journal.payloads and blocked.read_bytes() == original and set(root.iterdir()) == before


def test_maintenance_schema_without_explicit_metadata_fails_closed(stop_journal):
    root,journal=stop_journal;blocked=root/'blocked.json'
    blocked.write_text(json.dumps({'schema':'fdisbull-control-components-maintenance-block-1'}));blocked.chmod(0o600)
    with pytest.raises(ValueError,match='maintenance metadata'):entry.record_failure('ValueError',runner=journal)
    assert not journal.payloads


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


def test_run_failure_is_durable_and_does_not_disclose_exception(monkeypatch, capsys, tmp_path, stop_journal):
    _, journal = stop_journal
    monkeypatch.setattr(entry, 'STATE', tmp_path)
    monkeypatch.setattr(entry.subprocess, 'run', journal)
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
