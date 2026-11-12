"""Checkpoint-bound QEMU DOS workspace generation contracts (host only)."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fdisbull.project import Project

from fdisbull import dos_workspace_fat as fat
from fdisbull.dos_file_layers import WorkspaceStore, capture_directory
from fdisbull.qemu_workspace import (
    FORMAT, QemuDOSWorkspaceMixin, checkpoint_workspace, init_state, restore_workspace,
    validate_workspace, validate_workspace_image,
)
from test_dos_workspace_fat import _floppy
from test_qemu_dos_history import Harness


@pytest.fixture
def session(tmp_path, monkeypatch):
    source = tmp_path / 'workspace.com'
    source.write_bytes(bytes.fromhex('90ebfd'))
    project = Project.create(tmp_path / 'workspace.fdb', source, image='com')
    harness = Harness(project)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._compatibility', lambda owner: {'runtime': 'workspace-test'})
    yield harness


def _disk():
    volume = fat.build_volume({
        'GAME.COM': {'type': 'file', 'data': b'game', 'dos_date': 0x5821, 'dos_time': 0},
        'DOCS': {'type': 'directory', 'dos_date': 0x5821, 'dos_time': 0},
        'DOCS\\HELLO.TXT': {'type': 'file', 'data': b'HELLO', 'dos_date': 0x5821, 'dos_time': 0},
        'EMPTY.DAT': {'type': 'file', 'data': b'', 'dos_date': 0x5821, 'dos_time': 0},
    })
    return fat.build_composite(_floppy(), volume)[0]


def _configure(session, disk):
    session._artifact = lambda *args: session.project._debug_artifact(session.run_id, *args)
    session.vm.inputs = {
        'qemu': {'sha256': '1' * 64, 'version': 'QEMU test'},
        'checkpoint_tool': {'sha256': '2' * 64},
        'boot_image': {'sha256': '3' * 64},
    }
    session.vm.machine_configuration = {'disk': 'private-standalone-qcow2', 'cpus': 1}
    session.vm.checkpoint_virtual_size = len(disk)
    session.vm.checkpoint_disk = session.project.path.parent / 'runtime.qcow2'
    session.vm.checkpoint_disk.write_bytes(b'placeholder')
    session.guest_profile = {'profile_sha256': '4' * 64}
    return session


def _init(session, disk):
    layout = fat.volume_layout(disk)
    d = layout['D']
    entries = fat.parse_volume(disk[d['offset']:d['offset'] + d['size']])
    return init_state(session, entries, {'freedos': 'pinned-fixture-v1'}, layout,
                      'C:\\GAME.COM', 'checkpointed')


def test_checkpoint_record_pins_d_generation_and_exact_qcow_payload(session, monkeypatch):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw',
                        lambda owner, data: disk)
    record = checkpoint_workspace(session, b'authored-qcow-bytes')

    assert record['format'] == FORMAT
    assert record['qcow_sha256']
    assert record['raw_sha256']
    assert record['workspace_volume_sha256']
    assert record['source_dospath'] == 'C:\\GAME.COM'
    assert record['generation']['artifact'] != record['base_generation']['artifact']
    assert session._dos_workspace['generation']['artifact'] == record['generation']['artifact']
    checked = validate_workspace(session.project, record, session.version['id'])
    image = validate_workspace_image(checked, disk)
    assert image['valid'] is True
    assert image['generation'] == record['generation']['artifact']
    store = WorkspaceStore(session)
    inventory = store.load(record['generation']['artifact'])
    assert next(row for row in inventory['entries'] if row['dos_path'] == 'DOCS\\HELLO.TXT')['data'] == b'HELLO'
    assert inventory['manifest']['base'] == record['base_generation']['artifact']


def test_checkpoint_capture_preserves_original_long_host_paths_and_empty_diff(session, tmp_path, monkeypatch):
    root = tmp_path / 'host-workspace'
    root.mkdir()
    (root / 'GAME.COM').write_bytes(b'game')
    (root / 'Long report name.txt').write_bytes(b'unchanged')
    capture = capture_directory(root)
    volume_entries = {
        item['dos_path']: {key: value for key, value in item.items()
                           if key in ('type', 'data', 'attributes', 'dos_date', 'dos_time')}
        for item in capture['entries']
    }
    volume = fat.build_volume(volume_entries)
    disk, receipt = fat.build_composite(_floppy(), volume)
    _configure(session, disk)
    init_state(session, capture, {'freedos': 'pinned-fixture-v1'}, receipt,
               'C:\\GAME.COM', 'checkpointed')
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: disk)

    record = checkpoint_workspace(session, b'unchanged-disk-qcow')

    store = WorkspaceStore(session)
    before = store.load(record['base_generation']['artifact'])['entries']
    after = store.load(record['generation']['artifact'])['entries']
    long_name = next(item['dos_path'] for item in capture['entries']
                     if item['path'] == 'Long report name.txt')
    original = next(item for item in before if item['dos_path'] == long_name)
    retained = next(item for item in after if item['dos_path'] == original['dos_path'])
    assert retained['path'] == 'Long report name.txt'
    assert retained['path'] == original['path']
    assert {key: retained[key] for key in ('type', 'attributes', 'dos_date', 'dos_time', 'size', 'sha256', 'origin')} == {
        key: original[key] for key in ('type', 'attributes', 'dos_date', 'dos_time', 'size', 'sha256', 'origin')}
    assert store.inspect(record['generation']['artifact'],
                         base=record['base_generation']['artifact'])['difference'] == []


def test_restore_adopts_only_after_call_and_retains_lineage_across_session(session, monkeypatch):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: disk)
    record = checkpoint_workspace(session, b'q1')

    restored_vm = SimpleNamespace(inputs=deepcopy(session.vm.inputs),
        machine_configuration=deepcopy(session.vm.machine_configuration))
    restored = SimpleNamespace(project=session.project, version=session.version,
        metadata=deepcopy(session.metadata), vm=restored_vm,
        guest_profile=deepcopy(session.guest_profile), closed=False, run_id='new-owner')
    status = restore_workspace(restored, record)
    assert status['active'] is True
    assert restored._dos_workspace['generation']['artifact'] == record['generation']['artifact']
    assert restored._dos_workspace['base_generation']['artifact'] == record['base_generation']['artifact']


def test_checkpoint_refuses_wrong_disk_layout_without_advancing_generation(session, monkeypatch):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    before = session._dos_workspace['generation']['artifact']
    other = fat.build_composite(_floppy(), fat.build_volume({}, size_bytes=16 * 1024 * 1024))[0]
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: other)
    with pytest.raises(ValueError, match='layout'):
        checkpoint_workspace(session, b'q2')
    assert session._dos_workspace['generation']['artifact'] == before


def test_workspace_record_and_generation_tampering_are_refused(session, monkeypatch):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: disk)
    record = checkpoint_workspace(session, b'q3')
    altered = deepcopy(record)
    altered['source_dospath'] = 'C:\\OTHER.COM'
    with pytest.raises(ValueError, match='payload hash'):
        validate_workspace(session.project, altered, session.version['id'])

    generation = record['generation']['artifact']
    row = session.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (generation,)).fetchone()
    with session.project.transaction(True):
        session.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?', (bytes(row['data']) + b'!', generation))
    with pytest.raises(ValueError, match='hash'):
        validate_workspace(session.project, record, session.version['id'])


def test_failed_record_publication_does_not_advance_session_generation(session, monkeypatch):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    before = session._dos_workspace['generation']['artifact']
    monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: disk)
    monkeypatch.setattr('fdisbull.qemu_workspace._publish_record',
                        lambda *_args: (_ for _ in ()).throw(OSError('publication failure')))
    with pytest.raises(OSError, match='publication'):
        checkpoint_workspace(session, b'q4')
    assert session._dos_workspace['generation']['artifact'] == before


def test_public_reads_are_limited_to_sealed_generation(session):
    disk = _disk()
    _configure(session, disk)
    _init(session, disk)
    session.__class__ = type('WorkspaceHarness', (QemuDOSWorkspaceMixin, session.__class__), {})

    status = session.workspace_status()
    files = session.workspace_files(view='effective')
    base = session.workspace_files(view='base')
    changed = session.workspace_files(view='diff')
    read = session.workspace_read('D:\\DOCS\\HELLO.TXT')

    assert status['live_guest_visibility'] is False
    assert status['generation']['artifact'] == status['base_generation']['artifact']
    assert files['entries'] == base['entries']
    assert changed['entries'] == []
    assert read['data'] == b'HELLO'
    assert read['dos_path'] == 'DOCS\\HELLO.TXT'

