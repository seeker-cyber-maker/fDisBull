"""Bounded large-file workspace admission and durable host-side recovery.

All bytes are authored. The checkpoint test verifies the workspace sidecar and
FAT payload, not a running VM or native CPU/device restoration.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from fdisbull.dos_file_layers import WorkspaceStore, capture_directory
from fdisbull.dos_workspace_launch import prepare_workspace
from fdisbull import dos_workspace_fat as fat
from fdisbull.qemu_workspace import (
    checkpoint_workspace, init_state, restore_workspace, validate_workspace,
    validate_workspace_image,
)
from test_dos_workspace_launch import _boot, _session
from test_qemu_dos_history import Harness
from test_qemu_workspace import _configure


POLICY_BYTES = 24 * 1024 * 1024
PROGRAM = b'\x90\xc3'


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _inputs(tmp_path, total_bytes):
    root = tmp_path / 'game'
    root.mkdir()
    (root / 'GAME.COM').write_bytes(PROGRAM)
    size = total_bytes - len(PROGRAM)
    seed = bytes(range(256)) + b'authored workspace asset'
    payload = (seed * ((size + len(seed) - 1) // len(seed)))[:size]
    (root / 'ASSET.DAT').write_bytes(payload)
    return root, payload


def _count(project):
    return project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]


def test_large_generation_capture_mutation_reopen_and_cold_directory_launch(tmp_path):
    root, payload = _inputs(tmp_path, 20 * 1024 * 1024)
    database = tmp_path / 'project.fdb'
    boot = _boot(tmp_path)
    with Project.create(database, root / 'GAME.COM', image='com') as project:
        store = WorkspaceStore(_session(project))
        capture = capture_directory(root)
        assert capture['total_bytes'] == 20 * 1024 * 1024
        base = store.seal(capture['entries'], source_root=root,
                          source_identity=capture['root_identity'])
        offset = 17 * 1024 * 1024 + 7
        changed = store.write_range(base['artifact'], 'ASSET.DAT', offset, b'changed',
                                    expected_sha256=_digest(payload))
        expected = payload[:offset] + b'changed' + payload[offset + 7:]
        grown = store.resize_file(changed['artifact'], 'ASSET.DAT', len(expected) + 33,
                                  expected_sha256=_digest(expected))
        expected += bytes(33)
        assert next(i['data'] for i in store.load(base['artifact'])['entries']
                    if i['dos_path'] == 'ASSET.DAT') == payload
        assert (root / 'ASSET.DAT').read_bytes() == payload

    root.rename(tmp_path / 'moved-original')
    with Project(database) as project:
        staging = tmp_path / 'stage'
        staging.mkdir()
        prepared = prepare_workspace(project, root, None, None, None, boot, staging,
                                     generation=grown['artifact'], version_id=project.version()['id'])
        assert not root.exists()
        disk = Path(prepared['image']).read_bytes()
        layout = fat.volume_layout(disk)
        d = layout['D']
        assert d['size'] == 32 * 1024 * 1024 and len(disk) < 64 * 1024 * 1024
        files = fat.parse_volume(disk[d['offset']:d['offset'] + d['size']])
        assert files['ASSET.DAT']['data'] == expected
        assert files['GAME.COM']['data'] == PROGRAM


def test_exact_budget_fits_existing_fat_and_aggregate_plus_one_refuses_before_vm(tmp_path, monkeypatch):
    root, payload = _inputs(tmp_path, POLICY_BYTES)
    capture = capture_directory(root)
    assert capture['total_bytes'] == POLICY_BYTES
    database = tmp_path / 'project.fdb'
    boot = _boot(tmp_path)
    staging = tmp_path / 'stage'
    staging.mkdir()
    with Project.create(database, root / 'GAME.COM', image='com') as project:
        prepared = prepare_workspace(project, root, root, 'checkpointed', None, boot, staging)
        disk = Path(prepared['image']).read_bytes()
        d = fat.volume_layout(disk)['D']
        assert d['size'] == 32 * 1024 * 1024
        assert fat.parse_volume(disk[d['offset']:d['offset'] + d['size']])['ASSET.DAT']['data'] == payload
        (root / 'EXTRA.DAT').write_bytes(b'x')
        before = _count(project)
        calls = []
        def unexpected_vm(*args, **kwargs):
            calls.append(1)
            pytest.fail('Oversized workspace reached native construction')
        monkeypatch.setattr('fdisbull.qemu_dos_process.QemuMachine', unexpected_vm)
        with pytest.raises(ValueError, match='Workspace file bytes exceed the capture bound'):
            project.debugger('unused-qemu', root, backend='qemu-dos',
                dos_directory=root, dos_boot_image=boot, dos_mcopy='unused-mcopy')
        assert not calls and _count(project) == before
        assert (root / 'ASSET.DAT').read_bytes() == payload


def test_aggregate_and_per_file_mutation_refusals_publish_nothing(tmp_path):
    root, payload = _inputs(tmp_path, POLICY_BYTES)
    with Project.create(tmp_path / 'project.fdb', root / 'GAME.COM', image='com') as project:
        store = WorkspaceStore(_session(project))
        capture = capture_directory(root)
        saved = store.seal(capture['entries'], source_root=root,
                           source_identity=capture['root_identity'])
        before = _count(project)
        for change in (
            lambda: store.write_range(saved['artifact'], 'ASSET.DAT', len(payload), b'x',
                                      expected_sha256=_digest(payload)),
            lambda: store.resize_file(saved['artifact'], 'ASSET.DAT', len(payload) + 1,
                                      expected_sha256=_digest(payload)),
        ):
            with pytest.raises(ValueError, match='Workspace file bytes exceed the generation bound'):
                change()
            assert _count(project) == before
        with pytest.raises(ValueError, match='Workspace write range exceeds its bound'):
            store.write_range(saved['artifact'], 'ASSET.DAT', POLICY_BYTES, b'x',
                              expected_sha256=_digest(payload))
        with pytest.raises(ValueError, match='Workspace file size exceeds its bound'):
            store.resize_file(saved['artifact'], 'ASSET.DAT', POLICY_BYTES + 1,
                              expected_sha256=_digest(payload))
        assert _count(project) == before
        assert next(i['data'] for i in store.load(saved['artifact'])['entries']
                    if i['dos_path'] == 'ASSET.DAT') == payload


def test_large_checkpoint_workspace_record_reopens_and_restores_exact_fat_bytes(tmp_path, monkeypatch):
    root, payload = _inputs(tmp_path, 20 * 1024 * 1024)
    database = tmp_path / 'project.fdb'
    boot = _boot(tmp_path)
    with Project.create(database, root / 'GAME.COM', image='com') as project:
        session = Harness(project)
        capture = capture_directory(root)
        entries = {item['dos_path']: {key: value for key, value in item.items()
                   if key in ('type', 'data', 'attributes', 'dos_date', 'dos_time')}
                   for item in capture['entries']}
        disk, layout = fat.build_composite(boot.read_bytes(), fat.build_volume(entries))
        _configure(session, disk)
        init_state(session, capture, {'freedos': 'authored-test'}, layout,
                   'GAME.COM', 'checkpointed')
        monkeypatch.setattr('fdisbull.qemu_workspace._convert_qcow_to_raw', lambda owner, data: disk)
        saved = checkpoint_workspace(session, b'authored-host-checkpoint-payload')
        identity = dict(inputs=deepcopy(session.vm.inputs),
                        machine_configuration=deepcopy(session.vm.machine_configuration))
        metadata, profile, version = deepcopy(session.metadata), deepcopy(session.guest_profile), session.version

    with Project(database) as project:
        checked = validate_workspace(project, saved, version['id'])
        assert validate_workspace_image(checked, disk)['valid'] is True
        recovered = SimpleNamespace(project=project, version=version, metadata=metadata,
            guest_profile=profile, vm=SimpleNamespace(**identity), closed=False, run_id='cold-owner')
        status = restore_workspace(recovered, saved)
        assert status['active'] is True
        restored = WorkspaceStore(recovered).load(saved['generation']['artifact'])
        assert next(i['data'] for i in restored['entries'] if i['dos_path'] == 'ASSET.DAT') == payload
        assert recovered._dos_workspace['base_generation'] == saved['base_generation']
