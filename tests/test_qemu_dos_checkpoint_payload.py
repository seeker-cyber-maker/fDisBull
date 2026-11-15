"""Host-only tests for nonpersistent QEMU checkpoint payload seams."""
import threading
import json
from types import SimpleNamespace

import pytest

from fdisbull import frame_state_codec
from fdisbull.project import Project
from fdisbull import qemu_dos_checkpoint as checkpoint


@pytest.fixture
def project(tmp_path):
    source = tmp_path / 'payload.com'
    source.write_bytes(b'\x90\xeb\xfd')
    with Project.create(tmp_path / 'payload.fdb', source, image='com') as instance:
        version = instance.version()
        run = 'payload-run'
        with instance.transaction(True):
            instance.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (run, version['id'], 'authored', None, 'stopped', '{}'))
        yield instance, version, run


class Session:
    def __init__(self, project, version, run, tmp_path):
        self.project = project
        self.version = version
        self.run_id = run
        self.metadata = {'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64}
        self.vm = SimpleNamespace(lock=threading.RLock(), operation_deadline=None,
            checkpoint_disk=tmp_path / 'checkpoint.qcow2', checkpoint_virtual_size=1024,
            inputs={}, qmp=None, gdb=None, closed=False)
        self.vm.checkpoint_disk.write_bytes(b'old')
        self._checkpoint_launch = {'audio_profile': 'none', 'retrace_profile': 'standard'}
        self._process = {'state': 'active'}
        self._dos_task_binding = None
        self._dos_task_views = {}
        self.closed = False
        self._deadline = None
        self.metadata['backend'] = 'qemu-dos'

    def _artifact(self, name, kind, data, metadata):
        return self.project._debug_artifact(self.run_id, name, kind, data, metadata)

    def _set_deadline(self, deadline):
        self._deadline = deadline

    def close(self):
        self.closed = True


def _capture_mocks(monkeypatch, session):
    monkeypatch.setattr(checkpoint, '_preflight', lambda _session: None)
    monkeypatch.setattr(checkpoint, '_serial_idle', lambda _session: {'tx-idle': True})
    monkeypatch.setattr(checkpoint, '_origin', lambda _session: {'nonce': 'owned'})
    monkeypatch.setattr(checkpoint, '_verify_process',
        lambda *_args, **_kwargs: ({'cpu_mode': 'real'}, {'ram': 'evidence'}, None))
    monkeypatch.setattr(checkpoint, '_compatibility', lambda _session: {'runtime': 'qemu-test'})
    monkeypatch.setattr(checkpoint, 'capture_controls', lambda _session: {'controls': []})
    monkeypatch.setattr('fdisbull.qemu_dos_tasks.capture_task_checkpoint',
                        lambda _session: {'task': None})
    monkeypatch.setattr('fdisbull.qemu_dos_task_views.capture_task_views', lambda _session: None)
    monkeypatch.setattr('fdisbull.qemu_dos_scheduler.capture_scheduler', lambda _session: None)
    monkeypatch.setattr('fdisbull.qemu_instrumented_checkpoint.capture',
                        lambda _session: (None, None))
    monkeypatch.setattr('fdisbull.qemu_instrumented_checkpoint.verify_saved',
                        lambda *_args: None)
    monkeypatch.setattr(checkpoint, 'validate_qcow_header', lambda *_args: None)

    def snapshot(_vm, operation, **_kwargs):
        assert operation == 'save'
        session.vm.checkpoint_disk.write_bytes(b'authored qcow bytes')

    monkeypatch.setattr(checkpoint, 'snapshot_job', snapshot)


def test_capture_returns_full_archive_without_persisting(project, tmp_path, monkeypatch):
    instance, version, run = project
    session = Session(instance, version, run, tmp_path)
    _capture_mocks(monkeypatch, session)

    captured = checkpoint.capture_process_state(session, 'capture.qcow2', max_bytes=1024 * 1024)

    assert captured['name'] == 'capture.qcow2'
    assert captured['kind'] == 'state'
    assert captured['size'] == len(captured['data'])
    assert captured['sha256'] == checkpoint._sha(captured['data'])
    machine, bundle = checkpoint._unarchive(captured['data'])
    assert machine == b'authored qcow bytes'
    assert bundle['runtime'] == {'runtime': 'qemu-test'}
    assert instance.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


def test_public_save_persists_the_unmodified_capture(project, monkeypatch):
    instance, version, run = project
    session = Session(instance, version, run, instance.path.parent)
    data = b'complete checkpoint archive'
    metadata = {'format': checkpoint.FORMAT, 'source_sha256': 'a' * 64}
    expected = dict(name='named.qcow2', kind='state', data=data, metadata=metadata,
                    sha256=checkpoint._sha(data), size=len(data))
    calls = []
    monkeypatch.setattr(checkpoint, 'capture_process_state',
                        lambda _session, **kwargs: calls.append(kwargs) or expected)

    result = checkpoint.save_process_state(session, 'named.qcow2', 4096)

    assert calls == [{'name': 'named.qcow2', 'max_bytes': 4096}]
    row = instance.db.execute('SELECT kind,data,sha256,metadata FROM debug_artifacts WHERE id=?',
                              (result['artifact'],)).fetchone()
    assert row['kind'] == 'state'
    assert bytes(row['data']) == data
    assert row['sha256'] == checkpoint._sha(data)
    assert row['metadata'] == json.dumps(metadata)


def test_public_save_closes_if_artifact_publication_fails(project, monkeypatch):
    instance, version, run = project
    session = Session(instance, version, run, instance.path.parent)
    data = b'complete checkpoint archive'
    captured = dict(name='named.qcow2', kind='state', data=data,
                    metadata={'format': checkpoint.FORMAT},
                    sha256=checkpoint._sha(data), size=len(data))
    monkeypatch.setattr(checkpoint, 'capture_process_state', lambda *_args, **_kwargs: captured)

    def fail_publish(*_args, **_kwargs):
        raise OSError('artifact store unavailable')

    monkeypatch.setattr(session, '_artifact', fail_publish)
    with pytest.raises(OSError, match='artifact store unavailable'):
        checkpoint.save_process_state(session, 'named.qcow2', 4096)
    assert session.closed is True


def test_reconstructed_delta_source_is_validated_without_writing_full_state(
        project, tmp_path, monkeypatch):
    instance, version, run = project
    session = Session(instance, version, run, tmp_path)
    monkeypatch.setattr('fdisbull.qemu_machine._machine_operation_guard',
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(checkpoint, '_preflight', lambda _session: None)
    monkeypatch.setattr(checkpoint, '_serial_idle', lambda *_args, **_kwargs: {'tx-idle': True})
    monkeypatch.setattr(checkpoint, '_compatibility', lambda _session: {'runtime': 'qemu-test'})
    monkeypatch.setattr(checkpoint, '_unarchive', lambda _data: (_ for _ in ()).throw(
        RuntimeError('payload validated and reached shared full-checkpoint decoder')))
    monkeypatch.setattr('fdisbull.operation_budget.request_deadline',
                        lambda _session, _timeout: __import__('time').monotonic() + 30)

    result_bytes = b'\x01' + bytes(4095)
    base = bytes(4096)
    delta = frame_state_codec.encode(base, result_bytes, base_point='parent', depth=1)
    assert delta is not None
    full_metadata = {'format': checkpoint.FORMAT,
                     'source_sha256': session.metadata['source_sha256'],
                     'version_sha256': session.metadata['version_sha256'],
                     'origin_run': 'origin-run'}
    wrapper = {'format': checkpoint.FRAME_STATE_DELTA_REF_FORMAT,
               'history_id': 'history', 'node_id': 'node',
               'full_metadata': full_metadata,
               'descriptor': frame_state_codec.descriptor(delta)}
    stored = instance._debug_artifact(run, 'delta.bin', 'qemu-frame-state-delta',
                                      delta['payload'], wrapper)

    with pytest.raises(RuntimeError, match='shared full-checkpoint decoder'):
        checkpoint.load_process_state_data(session, result_bytes, full_metadata,
            source_id=stored['artifact'], timeout_ms=1000)

    assert instance.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 0
    assert session.closed is False


def test_reconstructed_delta_hash_mismatch_is_rejected_before_restore(
        project, tmp_path, monkeypatch):
    instance, version, run = project
    session = Session(instance, version, run, tmp_path)
    monkeypatch.setattr('fdisbull.qemu_machine._machine_operation_guard',
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(checkpoint, '_preflight', lambda _session: None)
    monkeypatch.setattr(checkpoint, '_serial_idle', lambda *_args, **_kwargs: {'tx-idle': True})
    monkeypatch.setattr('fdisbull.operation_budget.request_deadline',
                        lambda _session, _timeout: __import__('time').monotonic() + 30)
    monkeypatch.setattr(checkpoint, '_unarchive', lambda _data: pytest.fail('restore decoder must not run'))

    correct = b'\x01' + bytes(4095)
    delta = frame_state_codec.encode(bytes(4096), correct, base_point='parent', depth=1)
    metadata = {'format': checkpoint.FORMAT,
                'source_sha256': session.metadata['source_sha256'],
                'version_sha256': session.metadata['version_sha256']}
    wrapper = {'format': checkpoint.FRAME_STATE_DELTA_REF_FORMAT,
               'history_id': 'history', 'node_id': 'node', 'full_metadata': metadata,
               'descriptor': frame_state_codec.descriptor(delta)}
    stored = instance._debug_artifact(run, 'delta.bin', 'qemu-frame-state-delta',
                                      delta['payload'], wrapper)

    with pytest.raises(ValueError, match='Reconstructed checkpoint bytes differ'):
        checkpoint.load_process_state_data(session, b'tampered bytes', metadata,
            source_id=stored['artifact'], timeout_ms=1000)

    assert instance.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0] == 0
    assert session.closed is False
