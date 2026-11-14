"""Focused tests for the private library Drive-sync worker."""
from __future__ import annotations

import hashlib
import importlib.util
import json
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


def _sha_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _latest_library_manifest(transport, run):
    path = f"library/manifests/{run}"
    return json.loads(transport.remote[path]["manifest.json"])


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
    assert transport.remote["library/objects"][_sha_payload(b"original")] == b"original"
    assert _sha_payload(b"never upload linked payload") not in transport.remote["library/objects"]
    first_manifest = _latest_library_manifest(transport, first["run"])
    assert first_manifest["entries"]["targets/game/KEEP.COM"]["content"]["remote_path"] == (
        "library/objects/" + _sha_payload(b"original")
    )
    initial_call_count = len(transport.calls)

    unchanged = sync.run_once(config, transport=transport)
    assert unchanged["status"] == "complete"
    assert len(transport.remote["library/objects"]) == 2
    unchanged_calls = transport.calls[initial_call_count:]
    assert all(not call[2] for call in unchanged_calls)
    assert not any(call[0].startswith("library/manifests/") for call in unchanged_calls)
    before_changed_call_count = len(transport.calls)

    (root / "targets/game/CHANGE.COM").write_bytes(b"after")
    (root / "targets/game/KEEP.COM").unlink()
    changed = sync.run_once(config, transport=transport)
    assert changed["status"] == "complete"
    assert transport.remote["library/objects"][_sha_payload(b"after")] == b"after"
    assert transport.remote["library/objects"][_sha_payload(b"before")] == b"before"
    assert transport.remote["library/objects"][_sha_payload(b"original")] == b"original"
    assert changed["deletions_propagated"] is False
    changed_uploads = [call for call in transport.calls[before_changed_call_count:]
                       if call[0] == "library/objects"]
    assert len(changed_uploads) == 1
    assert set(changed_uploads[0][2]) == {_sha_payload(b"after")}
    latest = _latest_library_manifest(transport, changed["run"])
    assert "targets/game/KEEP.COM" not in latest["entries"]
    assert latest["entries"]["targets/game/CHANGE.COM"]["content"]["remote_path"] == (
        "library/objects/" + _sha_payload(b"after")
    )


def test_unavailable_library_root_never_causes_remote_deletion_or_sync_advance(tmp_path):
    root = tmp_path / "library"
    (root / "targets").mkdir(parents=True)
    (root / "targets/one.com").write_bytes(b"one")
    fdb_root = tmp_path / "fdb"
    _make_fdb_root(fdb_root)
    transport = FakeTransport()
    config = _config(tmp_path, root, fdb_root)
    sync.run_once(config, transport=transport)
    retained = dict(transport.remote["library/objects"])
    calls_before = len(transport.calls)

    config["library"]["root"] = str(tmp_path / "unmounted-library")
    with pytest.raises(ValueError, match="unavailable|changed"):
        sync.run_once(config, transport=transport)

    assert transport.remote["library/objects"] == retained
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

    failed = sync.run_once(config, transport=transport)
    assert failed["status"] == "partial"
    assert "library/objects" not in transport.remote

    result = sync.run_once(config, transport=transport)
    assert result["status"] == "complete"
    assert transport.remote["library/objects"][_sha_payload(b"new bytes")] == b"new bytes"
    assert [call for call in transport.calls if call[0] == "library/objects"][-1][2] == {
        _sha_payload(b"new bytes"): b"new bytes"
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


def test_legacy_fdb_proof_without_source_recaptures_once_then_reuses(tmp_path):
    library_root=tmp_path/'library';(library_root/'targets').mkdir(parents=True)
    fdb_root=tmp_path/'fdb';_make_fdb_root(fdb_root)
    database=fdb_root/'projects'/'analysis.fdb'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE facts(value TEXT)')
        db.execute("INSERT INTO facts VALUES ('preserve this generation')")
    config=_config(tmp_path,library_root,fdb_root);transport=FakeTransport()

    first=sync.run_once(config,transport)
    assert first['status']=='complete' and len(first['projects'])==1
    first_project=first['projects'][0]
    first_path=f"fdb/projects/{first_project['id']}/{first_project['generation']}"
    first_bytes=dict(transport.remote[first_path])

    # Simulate an existing completion receipt written before source identity
    # was part of the remote-generation proof.
    metadata_name='project:'+str(database)
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        row=db.execute('SELECT value FROM metadata WHERE name=?',(metadata_name,)).fetchone()
        proof=json.loads(row[0]);proof.pop('source',None)
        db.execute('UPDATE metadata SET value=? WHERE name=?',
                   (json.dumps(proof,sort_keys=True,indent=2)+'\n',metadata_name))

    legacy=sync.run_once(config,transport)
    assert legacy['status']=='complete' and len(legacy['projects'])==1
    replacement=legacy['projects'][0]
    assert replacement['generation']!=first_project['generation']
    replacement_path=f"fdb/projects/{replacement['id']}/{replacement['generation']}"
    assert transport.remote[first_path]==first_bytes
    assert transport.remote[replacement_path]['project.fdb']
    assert 'manifest.json' in transport.remote[replacement_path]
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        current=json.loads(db.execute('SELECT value FROM metadata WHERE name=?',
                                      (metadata_name,)).fetchone()[0])
    assert current['source']=={
        'path':str(database.absolute()),
        'name':database.name,
        'project_id':hashlib.sha256(str(database.absolute()).encode()).hexdigest()[:20],
    }

    fdb_calls_before=[call for call in transport.calls if call[0].startswith('fdb/projects/')]
    unchanged=sync.run_once(config,transport)
    assert unchanged['status']=='complete' and unchanged['projects']==[]
    assert [call for call in transport.calls if call[0].startswith('fdb/projects/')]==fdb_calls_before
    assert transport.remote[first_path]==first_bytes


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
    failed=sync.run_once(config,transport)
    assert failed['status']=='partial'
    assert not any(p.startswith('library/manifests/') for p in transport.remote)
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
    del transport.remote['library/objects'][_sha_payload(b'authored')]
    result=sync.run_once(config,transport)
    assert result['status']=='partial'
    assert any(error['phase']=='library' for error in result['errors'])


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
            if remote_path=='library/objects':(root/'targets'/'b.com').write_bytes(b'new addition')
            return result
    transport=ConcurrentWriter()
    result=sync.run_once(_config(tmp_path,root,repository),transport)
    assert result['status']=='partial'
    assert not any(p.startswith('library/manifests/') for p in transport.remote)


def test_manifest_failure_preserves_previous_content_addressed_generation(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    original=b'first immutable version'
    changed=b'second immutable version'
    (root/'targets'/'program.com').write_bytes(original)
    repository=tmp_path/'fdb';_make_fdb_root(repository)

    class FailNextManifest(FakeTransport):
        fail_manifest=False
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path.startswith('library/manifests/') and self.fail_manifest:
                self.fail_manifest=False
                self.calls.append((remote_path,backup_suffix,{}))
                return {'verified':False,'files':0}
            return super().put_tree(source_dir,remote_path,backup_suffix)

    transport=FailNextManifest();config=_config(tmp_path,root,repository)
    first=sync.run_once(config,transport)
    first_manifest_path=f"library/manifests/{first['run']}"
    first_manifest_bytes=transport.remote[first_manifest_path]['manifest.json']
    first_manifest=json.loads(first_manifest_bytes)
    old_remote_path=first_manifest['entries']['targets/program.com']['content']['remote_path']
    old_hash=old_remote_path.rsplit('/',1)[-1]
    assert old_remote_path==f'library/objects/{_sha_payload(original)}'

    (root/'targets'/'program.com').write_bytes(changed)
    transport.fail_manifest=True
    failed=sync.run_once(config,transport)

    assert failed['status']=='partial'
    assert transport.remote[first_manifest_path]['manifest.json']==first_manifest_bytes
    assert transport.remote['library/objects'][old_hash]==original
    assert transport.remote['library/objects'][_sha_payload(changed)]==changed
    assert first_manifest['entries']['targets/program.com']['content']['remote_path']==old_remote_path


def test_identical_files_share_one_content_addressed_remote_object(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    payload=b'duplicate bytes'
    (root/'targets'/'one.com').write_bytes(payload)
    (root/'targets'/'two.com').write_bytes(payload)
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    transport=FakeTransport()

    result=sync.run_once(_config(tmp_path,root,repository),transport)

    digest=_sha_payload(payload)
    assert result['status']=='complete'
    assert transport.remote['library/objects']=={digest:payload}
    manifest=_latest_library_manifest(transport,result['run'])
    first=manifest['entries']['targets/one.com']['content']['remote_path']
    second=manifest['entries']['targets/two.com']['content']['remote_path']
    assert first==second==f'library/objects/{digest}'


def test_legacy_cached_receipt_stays_readonly_while_changed_file_moves_to_objects(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    original=b'legacy stored bytes'
    relative='targets/legacy.com'
    (root/relative).write_bytes(original)
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    transport=FakeTransport();config=_config(tmp_path,root,repository)
    first=sync.run_once(config,transport)

    # Model a completed schema from before SHA-keyed library objects: its file
    # receipt has a stable SHA/MD5 but only the original path-based remote key.
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        db.execute('UPDATE files SET receipt=? WHERE path=?',(
            json.dumps({'kind':'file','size':len(original),'md5':hashlib.md5(original).hexdigest(),
                        'sha256':_sha_payload(original)}), relative))
    transport.remote.setdefault('library/files',{})[relative]=original

    unchanged=sync.run_once(config,transport)
    assert unchanged['status']=='complete'
    legacy_manifest=_latest_library_manifest(transport,unchanged['run'])
    legacy_path=legacy_manifest['entries'][relative]['content']['remote_path']
    assert legacy_path==f'library/files/{relative}'
    assert transport.remote['library/files'][relative]==original
    object_calls=[call for call in transport.calls if call[0]=='library/objects']
    assert object_calls[-1][2]=={}

    changed=b'new content-addressed bytes'
    (root/relative).write_bytes(changed)
    result=sync.run_once(config,transport)
    assert result['status']=='complete'
    manifest=_latest_library_manifest(transport,result['run'])
    new_path=manifest['entries'][relative]['content']['remote_path']
    assert new_path==f'library/objects/{_sha_payload(changed)}'
    assert transport.remote['library/objects'][_sha_payload(changed)]==changed
    assert transport.remote['library/files'][relative]==original
    assert first['status']=='complete'


def test_fdb_backup_completes_when_library_payload_transfer_fails(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'payload.com').write_bytes(b'intake')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    with sqlite3.connect(repository/'projects'/'a.fdb') as db:
        db.execute('CREATE TABLE facts(v TEXT)')
        db.execute("INSERT INTO facts VALUES ('durable')")

    class FailLibraryObjects(FakeTransport):
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path=='library/objects':
                submitted={p.relative_to(source_dir).as_posix():p.read_bytes()
                           for p in Path(source_dir).rglob('*') if p.is_file()}
                self.calls.append((remote_path,backup_suffix,submitted))
                return {'verified':False,'files':len(submitted)}
            return super().put_tree(source_dir,remote_path,backup_suffix)

    transport=FailLibraryObjects()
    result=sync.run_once(_config(tmp_path,root,repository),transport)

    assert result['status']=='partial'
    assert len(result['projects'])==1
    project=result['projects'][0]
    generation=f"fdb/projects/{project['id']}/{project['generation']}"
    assert 'project.fdb' in transport.remote[generation]
    assert 'manifest.json' in transport.remote[generation]
    assert any(error['phase']=='library' for error in result['errors'])
    assert not any(path.startswith('library/manifests/') for path in transport.remote)


def test_fdb_backup_completes_when_library_rescan_detects_churn(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'initial.com').write_bytes(b'initial')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    with sqlite3.connect(repository/'projects'/'a.fdb') as db:
        db.execute('CREATE TABLE facts(v TEXT)')
        db.execute("INSERT INTO facts VALUES ('durable')")

    class AddDuringLibraryTransfer(FakeTransport):
        did_add=False
        def put_tree(self,source_dir,remote_path,backup_suffix):
            result=super().put_tree(source_dir,remote_path,backup_suffix)
            if remote_path=='library/objects' and not self.did_add:
                self.did_add=True
                (root/'targets'/'concurrent.com').write_bytes(b'appeared during copy')
            return result

    transport=AddDuringLibraryTransfer()
    result=sync.run_once(_config(tmp_path,root,repository),transport)

    assert result['status']=='partial'
    assert len(result['projects'])==1
    project=result['projects'][0]
    generation=f"fdb/projects/{project['id']}/{project['generation']}"
    assert 'project.fdb' in transport.remote[generation]
    assert 'manifest.json' in transport.remote[generation]
    assert any(error['phase']=='library' for error in result['errors'])
    assert not any(path.startswith('library/manifests/') for path in transport.remote)


def test_failed_fdb_state_pair_is_rolled_back_before_library_commit(tmp_path, monkeypatch):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    (root/'targets'/'payload.com').write_bytes(b'intake continues')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    source=repository/'projects'/'a.fdb'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE facts(v TEXT)')
        db.execute("INSERT INTO facts VALUES ('durable')")

    original_state=sync._state
    fail_metadata=[True]
    class FailProjectMetadataOnce:
        def __init__(self, connection):
            self.connection=connection
        def execute(self, statement, parameters=()):
            if (fail_metadata[0] and 'INSERT OR REPLACE INTO metadata' in statement
                    and parameters and parameters[0]=='project:'+str(source)):
                fail_metadata[0]=False
                raise sqlite3.OperationalError('injected project metadata write failure')
            return self.connection.execute(statement, parameters)
        def commit(self):
            return self.connection.commit()
        def rollback(self):
            return self.connection.rollback()
        def close(self):
            return self.connection.close()

    monkeypatch.setattr(sync, '_state', lambda path: FailProjectMetadataOnce(original_state(path)))
    config=_config(tmp_path,root,repository)
    transport=FakeTransport()
    result=sync.run_once(config,transport)

    assert result['status']=='partial'
    assert len(result['projects'])==0
    assert any(error['source']==str(source) for error in result['errors'])
    assert any(path.startswith('library/manifests/') for path in transport.remote)
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        assert db.execute('SELECT path FROM projects').fetchall()==[]
        assert db.execute("SELECT name FROM metadata WHERE name=?",('project:'+str(source),)).fetchall()==[]
        assert db.execute("SELECT value FROM metadata WHERE name='namespace'").fetchone() is not None

    # The following pass must retry and commit the complete pair after the
    # injected failure has been consumed.
    retry=sync.run_once(config,transport)
    assert retry['status']=='complete'
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        assert db.execute('SELECT path FROM projects').fetchall()==[(str(source),)]
        assert db.execute("SELECT name FROM metadata WHERE name=?",('project:'+str(source),)).fetchall()==[
            ('project:'+str(source),)
        ]


def test_failed_library_transfer_reuses_verified_local_capture_on_retry(tmp_path, monkeypatch):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    payload=b'large immutable intake payload'
    source=root/'targets'/'payload.com';source.write_bytes(payload)
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    config=_config(tmp_path,root,repository)

    original_copy=sync.stable_copy
    copy_calls=[]
    def counted_copy(*args,**kwargs):
        copy_calls.append((args[0],args[1]))
        return original_copy(*args,**kwargs)
    monkeypatch.setattr(sync,'stable_copy',counted_copy)

    class FailFirstLibraryTransfer(FakeTransport):
        failed=False
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path=='library/objects' and not self.failed:
                self.failed=True
                submitted={p.relative_to(source_dir).as_posix():p.read_bytes()
                           for p in Path(source_dir).rglob('*') if p.is_file()}
                self.calls.append((remote_path,backup_suffix,submitted))
                return {'verified':False,'files':len(submitted)}
            return super().put_tree(source_dir,remote_path,backup_suffix)

    transport=FailFirstLibraryTransfer()
    first=sync.run_once(config,transport)
    assert first['status']=='partial'
    assert not any(path.startswith('library/manifests/') for path in transport.remote)
    assert len(copy_calls)==1

    retry=sync.run_once(config,transport)
    assert retry['status']=='complete'
    assert len(copy_calls)==1
    assert transport.remote['library/objects'][_sha_payload(payload)]==payload
    manifest=_latest_library_manifest(transport,retry['run'])
    assert manifest['entries']['targets/payload.com']['content']['remote_path']==(
        'library/objects/'+_sha_payload(payload)
    )


def test_tampered_cached_library_capture_is_refused_before_upload(tmp_path):
    root=tmp_path/'library';(root/'targets').mkdir(parents=True)
    source=root/'targets'/'payload.com';source.write_bytes(b'original stable bytes')
    repository=tmp_path/'fdb';_make_fdb_root(repository)
    config=_config(tmp_path,root,repository)

    class FailFirstLibraryTransfer(FakeTransport):
        failed=False
        def put_tree(self,source_dir,remote_path,backup_suffix):
            if remote_path=='library/objects' and not self.failed:
                self.failed=True
                submitted={p.relative_to(source_dir).as_posix():p.read_bytes()
                           for p in Path(source_dir).rglob('*') if p.is_file()}
                self.calls.append((remote_path,backup_suffix,submitted))
                return {'verified':False,'files':len(submitted)}
            return super().put_tree(source_dir,remote_path,backup_suffix)

    transport=FailFirstLibraryTransfer()
    first=sync.run_once(config,transport)
    assert first['status']=='partial'
    with sqlite3.connect(Path(config['state_dir'])/'state.sqlite') as db:
        cached=db.execute('SELECT payload FROM captures WHERE path=?',
                           ('targets/payload.com',)).fetchone()
    assert cached is not None
    Path(cached[0]).write_bytes(b'tampered cached bytes')

    retry=sync.run_once(config,transport)
    assert retry['status']=='partial'
    assert not transport.remote.get('library/objects')
    assert not any(path.startswith('library/manifests/') for path in transport.remote)
    assert any('Cached library capture differs' in error['message'] for error in retry['errors'])
