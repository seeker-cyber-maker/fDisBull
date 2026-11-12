"""Focused tests for the private library Drive-sync worker."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/drive_library_sync.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("drive_library_sync", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync)


def _library(root: Path) -> dict:
    return {
        "root": str(root),
        "include_dirs": sorted(
            entry.name for entry in root.iterdir()
            if entry.is_dir() and not entry.is_symlink()
        ),
        "include_files": [],
    }


def test_scan_library_is_confined_to_explicit_roots_and_records_symlinks(tmp_path):
    root = tmp_path / "intake"
    (root / "targets/game").mkdir(parents=True)
    (root / "receipts").mkdir()
    (root / "notes").mkdir()
    (root / "targets/game/PROGRAM.COM").write_bytes(b"program")
    (root / "receipts/receipt.json").write_text("{}", encoding="utf-8")
    (root / "notes/private.txt").write_text("excluded", encoding="utf-8")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"must not be followed")
    (root / "targets/game/linked.bin").symlink_to(outside)
    (root / "README.md").write_text("intake", encoding="utf-8")

    rows = sync.scan_library({
        "root": str(root),
        "include_dirs": ["targets", "receipts"],
        "include_files": ["README.md"],
    })

    assert set(rows) == {
        "targets/game/PROGRAM.COM",
        "targets/game/linked.bin",
        "receipts/receipt.json",
        "README.md",
    }
    assert rows["targets/game/PROGRAM.COM"]["kind"] == "file"
    assert rows["targets/game/PROGRAM.COM"]["size"] == 7
    link = rows["targets/game/linked.bin"]
    assert link["kind"] == "symlink"
    assert Path(link["path"]).is_symlink()
    assert "outside.bin" not in rows


def test_scan_library_keeps_external_source_link_as_link_not_payload(tmp_path):
    root = tmp_path / "intake"
    (root / "sources").mkdir(parents=True)
    outside = tmp_path / "installer.exe"
    outside.write_bytes(b"installer bytes")
    (root / "sources/installer.exe").symlink_to(outside)

    rows = sync.scan_library({
        "root": str(root),
        "include_dirs": ["sources"],
        "include_files": [],
    })

    assert list(rows) == ["sources/installer.exe"]
    assert rows["sources/installer.exe"]["kind"] == "symlink"
    assert rows["sources/installer.exe"]["size"] == len(os.readlink(root / "sources/installer.exe"))


@pytest.mark.parametrize('selection', ['', '.', '..', '/'])
def test_scan_refuses_selection_that_escapes_or_widens_to_root(tmp_path, selection):
    with pytest.raises(ValueError, match='relative path'):
        sync.scan_library({'root':str(tmp_path),'include_dirs':[selection]})


def test_stable_copy_reports_hashes_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "copy.bin"
    payload = b"immutable intake bytes\x00\xff"
    source.write_bytes(payload)

    receipt = sync.stable_copy(source, destination)

    assert destination.read_bytes() == payload
    assert receipt == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        "size": len(payload),
    }
    with pytest.raises((FileExistsError, ValueError)):
        sync.stable_copy(source, destination)
    assert destination.read_bytes() == payload


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.remote = {}
        self.fail_next = False

    def verify_files(self,remote_path,expected):
        stored=self.remote.get(remote_path,{})
        for path,proof in expected.items():
            data=stored.get(path)
            if data is None or len(data)!=proof['size'] or hashlib.md5(data).hexdigest()!=proof['md5']:
                raise ValueError('Remote file absent or changed')
        return {'verified':True,'files':len(expected)}

    def put_tree(self, source_dir, remote_path, backup_suffix):
        source_dir = Path(source_dir)
        submitted = {}
        for path in source_dir.rglob("*"):
            if path.is_symlink():
                raise AssertionError("worker passed a symlink to the transport")
            if path.is_file():
                submitted[path.relative_to(source_dir).as_posix()] = path.read_bytes()
        self.calls.append((remote_path, backup_suffix, dict(submitted)))
        if self.fail_next:
            self.fail_next = False
            return {"verified": False, "files": len(submitted)}
        destination = self.remote.setdefault(remote_path, {})
        destination.update(submitted)
        return {"verified": True, "files": len(submitted)}


def _config(tmp_path, library_root, fdb_root):
    return {
        "format": sync.FORMAT,
        "enabled": True,
        "state_dir": str(tmp_path / "state"),
        "library": _library(library_root),
        "fdb_repository": {
            "root": str(fdb_root),
            "objects_roots": [str(fdb_root / "objects")],
        },
        "transport": {"config": "unused-by-injected-transport", "remote": "drive:", "root_id": "test-root"},
        "snapshot_timeout_seconds": 10,
    }


def _make_fdb_root(root):
    (root / "projects").mkdir(parents=True)
    (root / "objects").mkdir()


def test_run_once_uploads_initial_and_changed_files_but_never_deletes_remote(tmp_path):
    root = tmp_path / "library"
    (root / "targets/game").mkdir(parents=True)
    (root / "receipts").mkdir()
    (root / "targets/game/KEEP.COM").write_bytes(b"original")
    (root / "targets/game/CHANGE.COM").write_bytes(b"before")
    external = tmp_path / "outside.bin"
    external.write_bytes(b"never upload linked payload")
    (root / "targets/game/linked.bin").symlink_to(external)
    fdb_root = tmp_path / "fdb"
    _make_fdb_root(fdb_root)
    transport = FakeTransport()
    config = _config(tmp_path, root, fdb_root)

    first = sync.run_once(config, transport=transport)
    assert first["status"] == "complete"
    assert first["deletions_propagated"] is False
    assert transport.remote["library/files"]["targets/game/KEEP.COM"] == b"original"
    assert "targets/game/linked.bin" not in transport.remote["library/files"]
    initial_call_count = len(transport.calls)

    unchanged = sync.run_once(config, transport=transport)
    assert unchanged["status"] == "complete"
    assert len(transport.remote["library/files"]) == 2
    assert len(transport.calls) == initial_call_count + 1  # empty delta check; no manifest rewrite

    (root / "targets/game/CHANGE.COM").write_bytes(b"after")
    (root / "targets/game/KEEP.COM").unlink()
    changed = sync.run_once(config, transport=transport)
    assert changed["status"] == "complete"
    assert transport.remote["library/files"]["targets/game/CHANGE.COM"] == b"after"
    assert transport.remote["library/files"]["targets/game/KEEP.COM"] == b"original"
    assert changed["deletions_propagated"] is False
    changed_uploads = [call for call in transport.calls[initial_call_count + 1:]
                       if call[0] == "library/files"]
    assert len(changed_uploads) == 1
    assert set(changed_uploads[0][2]) == {"targets/game/CHANGE.COM"}


def test_unavailable_library_root_never_causes_remote_deletion_or_sync_advance(tmp_path):
    root = tmp_path / "library"
    (root / "targets").mkdir(parents=True)
    (root / "targets/one.com").write_bytes(b"one")
    fdb_root = tmp_path / "fdb"
    _make_fdb_root(fdb_root)
    transport = FakeTransport()
    config = _config(tmp_path, root, fdb_root)
    sync.run_once(config, transport=transport)
    retained = dict(transport.remote["library/files"])
    calls_before = len(transport.calls)

    config["library"]["root"] = str(tmp_path / "unmounted-library")
    with pytest.raises(ValueError, match="unavailable|changed"):
        sync.run_once(config, transport=transport)

    assert transport.remote["library/files"] == retained
    assert len(transport.calls) == calls_before


def test_failed_transfer_does_not_mark_source_as_synced(tmp_path):
    root = tmp_path / "library"
    (root / "targets").mkdir(parents=True)
    (root / "targets/new.com").write_bytes(b"new bytes")
    fdb_root = tmp_path / "fdb"
    _make_fdb_root(fdb_root)
    transport = FakeTransport()
    transport.fail_next = True
    config = _config(tmp_path, root, fdb_root)

    with pytest.raises(ValueError, match="did not certify"):
        sync.run_once(config, transport=transport)
    assert "library/files" not in transport.remote

    result = sync.run_once(config, transport=transport)
    assert result["status"] == "complete"
    assert transport.remote["library/files"]["targets/new.com"] == b"new bytes"
    assert [call for call in transport.calls if call[0] == "library/files"][-1][2] == {
        "targets/new.com": b"new bytes"
    }


def test_fdb_upload_uses_consistent_snapshot_and_preserves_new_generations(tmp_path):
    library_root = tmp_path / "library"
    (library_root / "targets").mkdir(parents=True)
    fdb_root = tmp_path / "fdb"
    _make_fdb_root(fdb_root)
    database = fdb_root / "projects/analysis.fdb"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE facts(value TEXT)")
        db.execute("INSERT INTO facts VALUES ('first')")
    transport = FakeTransport()
    config = _config(tmp_path, library_root, fdb_root)

    first = sync.run_once(config, transport=transport)
    assert first["status"] == "complete"
    assert len(first["projects"]) == 1
    first_generation = first["projects"][0]["generation"]
    first_path = f"fdb/projects/{first['projects'][0]['id']}/{first_generation}"
    assert transport.remote[first_path]["project.fdb"]
    assert "manifest.json" in transport.remote[first_path]

    same = sync.run_once(config, transport=transport)
    assert same["projects"] == []

    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO facts VALUES ('second')")
    later = sync.run_once(config, transport=transport)
    assert len(later["projects"]) == 1
    second_generation = later["projects"][0]["generation"]
    assert second_generation != first_generation
    second_path = f"fdb/projects/{later['projects'][0]['id']}/{second_generation}"
    assert transport.remote[first_path]["project.fdb"]
    assert transport.remote[second_path]["project.fdb"]


def test_failed_library_manifest_keeps_source_pending_for_retry(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'a.com').write_bytes(b'authored')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    class FailManifest(FakeTransport):
        fail_manifest=True
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path.startswith('library/manifests/') and self.fail_manifest:
                self.fail_manifest=False
                return {'verified':False,'files':0}
            return super().put_tree(source_dir,remote_path,backup_suffix)
    transport=FailManifest();config=_config(tmp_path,root,repository)
    with pytest.raises(ValueError,match='manifest remote verification'):
        sync.run_once(config,transport)
    assert sync.run_once(config,transport)['status']=='complete'
    assert any(p.startswith('library/manifests/') for p in transport.remote)


def test_fdb_completion_manifest_is_sent_only_after_payload_verifies(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    with sqlite3.connect(repository/'projects'/'a.fdb') as db:
        db.execute('CREATE TABLE facts(v TEXT)')
    class FailPayload(FakeTransport):
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path.startswith('fdb/projects/'):
                names=[p.name for p in Path(source_dir).rglob('*') if p.is_file()]
                assert 'manifest.json' not in names
                self.calls.append((remote_path,backup_suffix,dict.fromkeys(names)))
                return {'verified':False,'files':0}
            return super().put_tree(source_dir,remote_path,backup_suffix)
    transport=FailPayload()
    result=sync.run_once(_config(tmp_path,root,repository),transport)
    assert result['status']=='partial' and result['projects']==[]
    assert not any('manifest.json' in files for path,_run,files in transport.calls
                   if path.startswith('fdb/projects/'))


def test_unchanged_source_cannot_certify_a_missing_remote_file(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'a.com').write_bytes(b'authored')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    config=_config(tmp_path,root,repository);transport=FakeTransport()
    sync.run_once(config,transport)
    del transport.remote['library/files']['targets/a.com']
    with pytest.raises(ValueError,match='Remote file absent or changed'):
        sync.run_once(config,transport)


def test_scope_change_requires_a_separate_state_directory(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'extra').mkdir();repository=tmp_path/'fdb';_make_fdb_root(repository)
    config=_config(tmp_path,root,repository);transport=FakeTransport()
    sync.run_once(config,transport)
    config['library']['include_dirs']=['targets']
    with pytest.raises(ValueError,match='source/destination changed'):
        sync.run_once(config,transport)


def test_inventory_change_during_transfer_does_not_publish_completion(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'a.com').write_bytes(b'authored')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    class ConcurrentWriter(FakeTransport):
        def put_tree(self,source_dir,remote_path,backup_suffix):
            result=super().put_tree(source_dir,remote_path,backup_suffix)
            if remote_path=='library/files':(root/'targets'/'b.com').write_bytes(b'new addition')
            return result
    transport=ConcurrentWriter()
    with pytest.raises(ValueError,match='Library changed during transfer'):
        sync.run_once(_config(tmp_path,root,repository),transport)
    assert not any(p.startswith('library/manifests/') for p in transport.remote)
