"""Private FDB online backup and recursive object closure."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest
from fdisbull.project import Project
from fdisbull.target_storage import PREFIX, TargetStore

spec=importlib.util.spec_from_file_location('fdb_backup',Path(__file__).resolve().parents[1]/'scripts/fdb_backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)


def test_online_snapshot_includes_committed_wal_and_nested_closure(tmp_path):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store';objects=TargetStore(store)
    leaf=objects.put(b'payload\x00');nested=objects.put(json.dumps({'nested':leaf}))
    db=source/'test.fdb';conn=sqlite3.connect(db)
    conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE "odd table"(x TEXT)')
    conn.execute('INSERT INTO "odd table" VALUES(?)',(json.dumps({'inner':nested}),));conn.commit()
    output=tmp_path/'backups'/'one';output.parent.mkdir()
    manifest=backup.capture_fdb(db,[store],output,20)
    assert len(manifest['objects'])==2 and (output/'manifest.json').is_file()
    assert sqlite3.connect(output/'project.fdb').execute('SELECT count(*) FROM "odd table"').fetchone()==(1,)
    assert all(hashlib.sha256((output/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in manifest['objects'])
    conn.close()


def test_missing_or_corrupt_object_has_no_completion_manifest(tmp_path):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store';objects=TargetStore(store)
    ref=objects.put(b'valuable');db=source/'test.fdb'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE t(v TEXT)');c.execute('INSERT INTO t VALUES(?)',(ref,))
    digest=hashlib.sha256(b'valuable').hexdigest();(store/digest).write_bytes(b'corrupt')
    out=tmp_path/'backups';out.mkdir()
    with pytest.raises(ValueError,match='size or SHA-256'):
        backup.capture_fdb(db,[store],out/'corrupt',20)
    assert not (out/'corrupt'/'manifest.json').exists()
    (store/digest).unlink()
    with pytest.raises(ValueError,match='missing'):
        backup.capture_fdb(db,[store],out/'missing',20)
    assert not (out/'missing'/'manifest.json').exists()


def test_fdb_restores_with_isolated_store_and_source_bytes(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store'
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(store))
    binary=source/'a.com';binary.write_bytes(bytes.fromhex('b82a4ccd21'))
    database=source/'program.fdb'
    with Project.create(database,binary,image='com') as project:
        project.analyze(); expected=project.regions(1)[0].data
        out=tmp_path/'backup';backup.capture_fdb(database,[store],out,30)
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(out/'objects'))
    with Project(out/'project.fdb') as restored:
        assert restored.regions(1)[0].data==expected
        assert restored.source_info()['verified'] is True


def test_output_inside_store_or_symlink_root_refused(tmp_path):
    source=tmp_path/'source';source.mkdir();db=source/'a.fdb'
    with sqlite3.connect(db) as c:c.execute('CREATE TABLE t(v TEXT)')
    store=tmp_path/'store';store.mkdir()
    with pytest.raises(ValueError,match='inside'):backup.capture_fdb(db,[store],store/'backup',2)
    link=tmp_path/'link';link.symlink_to(store,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):backup.capture_fdb(db,[link],tmp_path/'backup',2)
    assert not (tmp_path/'backup'/'manifest.json').exists()


def test_invalid_nested_envelope_and_timeout_never_publish(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store';store.mkdir();db=source/'a.fdb'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE t(v TEXT)')
        c.execute('INSERT INTO t VALUES(?)',(json.dumps({'wrapper':{'$fdisbull_external_object_1':{'sha256':'bad'}}}),))
    with pytest.raises(ValueError,match='identity'):
        backup.capture_fdb(db,[store],tmp_path/'bad',10)
    assert not (tmp_path/'bad'/'manifest.json').exists()
    times=iter([0,2,2,2,2,2,2,2,2])
    monkeypatch.setattr(backup.time,'monotonic',lambda:next(times,2))
    with pytest.raises(TimeoutError):backup.capture_fdb(db,[store],tmp_path/'expired',1)
    assert not (tmp_path/'expired'/'manifest.json').exists()


def test_object_symlink_and_size_bound_are_rejected(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store';objects=TargetStore(store)
    ref=objects.put(b'payload');db=source/'test.fdb'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE t(v TEXT)');c.execute('INSERT INTO t VALUES(?)',(ref,))
    digest=hashlib.sha256(b'payload').hexdigest();(store/digest).unlink()
    (store/digest).symlink_to(db)
    with pytest.raises(OSError):backup.capture_fdb(db,[store],tmp_path/'symlink',10)
    assert not (tmp_path/'symlink'/'manifest.json').exists()
    (store/digest).unlink();(store/digest).write_bytes(b'payload')
    monkeypatch.setattr(backup,'MAX_OBJECTS_TOTAL',3)
    with pytest.raises(ValueError,match='aggregate bound'):
        backup.capture_fdb(db,[store],tmp_path/'oversized',10)
    assert not (tmp_path/'oversized'/'manifest.json').exists()


@pytest.mark.parametrize('roots',[[],['missing']])
def test_legacy_embedded_database_needs_no_object_store(tmp_path,roots):
    source=tmp_path/'source';source.mkdir();db=source/'embedded.fdb'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE data(v BLOB)');c.execute('INSERT INTO data VALUES(?)',(b'authored',))
    result=backup.capture_fdb(db,[tmp_path/x for x in roots],tmp_path/'result',10)
    assert result['objects']==[]
    assert sqlite3.connect(tmp_path/'result'/'project.fdb').execute('SELECT v FROM data').fetchone()==(b'authored',)


@pytest.mark.parametrize('roots',[[],['missing']])
def test_referenced_object_without_available_root_fails(tmp_path,roots):
    source=tmp_path/'source';source.mkdir();db=source/'external.fdb'
    ref={'size':4,'sha256':hashlib.sha256(b'data').hexdigest(),'encoding':'bytes'}
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE data(v TEXT)');c.execute('INSERT INTO data VALUES(?)',(PREFIX+json.dumps(ref),))
    with pytest.raises(ValueError,match='missing'):
        backup.capture_fdb(db,[tmp_path/x for x in roots],tmp_path/'result',10)
    assert not (tmp_path/'result'/'manifest.json').exists()
