"""Private FDB online backup and recursive object closure."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import pytest
from fdisbull.project import Project
from fdisbull.target_storage import PREFIX, TargetStore

spec=importlib.util.spec_from_file_location('fdb_backup',Path(__file__).resolve().parents[1]/'scripts/fdb_backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)



@pytest.mark.usefixtures('require_descriptor_alias')
def test_online_snapshot_includes_committed_wal_and_nested_closure(tmp_path):
    source=tmp_path/'source';source.mkdir();store=tmp_path/'store';objects=TargetStore(store)
    leaf=objects.put(b'payload\x00');nested=objects.put(json.dumps({'nested':leaf}))
    db=source/'test.fdb';conn=sqlite3.connect(db)
    conn.execute('PRAGMA journal_mode=WAL');conn.execute('CREATE TABLE "odd table"(x TEXT)')
    conn.execute('INSERT INTO "odd table" VALUES(?)',(json.dumps({'inner':nested}),));conn.commit()
    output=tmp_path/'backups'/'one';output.parent.mkdir()
    source_bytes=db.read_bytes();wal_bytes=Path(str(db)+'-wal').read_bytes()
    manifest=backup.capture_fdb(db,[store],output,20)
    assert len(manifest['objects'])==2 and (output/'manifest.json').is_file()
    assert sqlite3.connect(output/'project.fdb').execute('SELECT count(*) FROM "odd table"').fetchone()==(1,)
    assert all(hashlib.sha256((output/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in manifest['objects'])
    assert db.read_bytes()==source_bytes and Path(str(db)+'-wal').read_bytes()==wal_bytes
    conn.close()


@pytest.mark.usefixtures('require_descriptor_alias')
def test_snapshot_retains_original_project_identity_in_opaque_output(tmp_path):
    source_dir=tmp_path/'source';source_dir.mkdir()
    database=source_dir/'meaningful-project.fdb'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE authored(value TEXT)')
        connection.execute('INSERT INTO authored VALUES(?)',('preserved',))
    output=tmp_path/'opaque-id'/'opaque-generation';output.parent.mkdir()
    manifest=backup.capture_fdb(database,[],output,20)
    original=str(database.expanduser().absolute())
    expected={'path':original,'name':'meaningful-project.fdb',
              'project_id':hashlib.sha256(original.encode('utf-8')).hexdigest()[:20]}
    assert manifest['source']==expected
    assert json.loads((output/'manifest.json').read_text())['source']==expected
    with sqlite3.connect(output/'project.fdb') as restored:
        assert restored.execute('PRAGMA integrity_check').fetchone()==('ok',)
        assert restored.execute('SELECT value FROM authored').fetchone()==('preserved',)


@pytest.mark.usefixtures('require_descriptor_alias')
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


@pytest.mark.usefixtures('require_descriptor_alias')
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


@pytest.mark.usefixtures('require_descriptor_alias')
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


@pytest.mark.usefixtures('require_descriptor_alias')
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
@pytest.mark.usefixtures('require_descriptor_alias')
def test_legacy_embedded_database_needs_no_object_store(tmp_path,roots):
    source=tmp_path/'source';source.mkdir();db=source/'embedded.fdb'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE data(v BLOB)');c.execute('INSERT INTO data VALUES(?)',(b'authored',))
    result=backup.capture_fdb(db,[tmp_path/x for x in roots],tmp_path/'result',10)
    assert result['objects']==[]
    assert sqlite3.connect(tmp_path/'result'/'project.fdb').execute('SELECT v FROM data').fetchone()==(b'authored',)


@pytest.mark.parametrize('roots',[[],['missing']])
@pytest.mark.usefixtures('require_descriptor_alias')
def test_referenced_object_without_available_root_fails(tmp_path,roots):
    source=tmp_path/'source';source.mkdir();db=source/'external.fdb'
    ref={'size':4,'sha256':hashlib.sha256(b'data').hexdigest(),'encoding':'bytes'}
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE data(v TEXT)');c.execute('INSERT INTO data VALUES(?)',(PREFIX+json.dumps(ref),))
    with pytest.raises(ValueError,match='missing'):
        backup.capture_fdb(db,[tmp_path/x for x in roots],tmp_path/'result',10)
    assert not (tmp_path/'result'/'manifest.json').exists()


def _authored_database(path, value):
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE authored(value TEXT)')
        connection.execute('INSERT INTO authored VALUES(?)', (value,))


@pytest.mark.usefixtures('require_descriptor_alias')
def test_snapshot_publication_never_opens_substituted_output_database(tmp_path, monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'source.fdb';_authored_database(source,'selected')
    unrelated=tmp_path/'unrelated.fdb';_authored_database(unrelated,'keep')
    source_before=source.read_bytes(); unrelated_before=unrelated.read_bytes()
    output=tmp_path/'backup';worker=backup._sqlite_backup
    def substituted(*args,**kwargs):
        (output/'project.fdb').symlink_to(unrelated)
        return worker(*args,**kwargs)
    monkeypatch.setattr(backup,'_sqlite_backup',substituted)
    with pytest.raises((FileExistsError,ValueError)):
        backup.capture_fdb(source,[],output,20)
    assert source.read_bytes()==source_before
    assert unrelated.read_bytes()==unrelated_before
    assert not (output/'manifest.json').exists()
    assert (output/'project.fdb').is_symlink()


@pytest.mark.usefixtures('require_descriptor_alias')
def test_directory_replacement_preserves_both_owned_and_unrelated_output(tmp_path, monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'source.fdb';_authored_database(source,'selected')
    unrelated=tmp_path/'unrelated.fdb';_authored_database(unrelated,'keep')
    original=unrelated.read_bytes(); source_before=source.read_bytes()
    output=tmp_path/'backup';moved=tmp_path/'owned-moved';worker=backup._sqlite_backup
    def replaced(*args,**kwargs):
        output.rename(moved);output.mkdir()
        (output/'project.fdb').write_bytes(original)
        return worker(*args,**kwargs)
    monkeypatch.setattr(backup,'_sqlite_backup',replaced)
    with pytest.raises(ValueError,match='directory identity'):
        backup.capture_fdb(source,[],output,20)
    assert (output/'project.fdb').read_bytes()==original
    assert source.read_bytes()==source_before and unrelated.read_bytes()==original
    assert moved.is_dir()
    assert not (output/'manifest.json').exists() and not (moved/'manifest.json').exists()


def test_sqlite_resolved_source_is_bound_even_when_namespace_is_restored(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'source.fdb';_authored_database(source,'selected')
    other=tmp_path/'other.fdb';_authored_database(other,'outside-selection')
    before=source.read_bytes();other_before=other.read_bytes()
    _connect_substitution(monkeypatch, source, other, symlink=True)
    with pytest.raises(ValueError,match='database identity'):
        backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert source.read_bytes()==before and other.read_bytes()==other_before
    assert not (tmp_path/'backup'/'manifest.json').exists()


@pytest.mark.usefixtures('require_descriptor_alias')
def test_manifest_publication_does_not_replace_or_delete_an_existing_name(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'source.fdb';_authored_database(source,'selected')
    output=tmp_path/'backup';link=backup.os.link
    def occupied(src,dst,*args,**kwargs):
        if dst=='manifest.json':
            (output/'manifest.json').write_bytes(b'keep unrelated metadata')
        return link(src,dst,*args,**kwargs)
    monkeypatch.setattr(backup.os,'link',occupied)
    with pytest.raises(FileExistsError):backup.capture_fdb(source,[],output,20)
    assert (output/'manifest.json').read_bytes()==b'keep unrelated metadata'


@pytest.mark.usefixtures('require_descriptor_alias')
def test_admitted_source_and_parent_inode_must_match_before_sqlite_reads(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    file_stat=source.stat();parent_stat=source_dir.stat()
    identity={'device':file_stat.st_dev,'inode':file_stat.st_ino,
              'parent_device':parent_stat.st_dev,'parent_inode':parent_stat.st_ino}
    output=tmp_path/'backup'
    result=backup.capture_fdb(source,[],output,20,expected_source_identity=identity)
    assert result['source']['name']=='selected.fdb'
    def forbidden(*args,**kwargs):raise AssertionError('mismatched selection must not reach SQLite')
    monkeypatch.setattr(backup,'_sqlite_backup',forbidden)
    for field in identity:
        different=dict(identity);different[field]+=1
        with pytest.raises(ValueError,match='source identity changed'):
            backup.capture_fdb(source,[],tmp_path/('wrong-'+field),20,expected_source_identity=different)
        assert not (tmp_path/('wrong-'+field)/'manifest.json').exists()


def _connect_substitution(monkeypatch, source, other, *, symlink=False, destination=False, enabled=True):
    run = backup.subprocess.run
    code = r'''import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("worker",sys.argv[1])
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
connect=worker._connect if DESTINATION else worker.sqlite3.connect
selected=Path(SOURCE);other=Path(OTHER)
def swapped(database,*args,**kwargs):
    if not ENABLED: return connect(database,*args,**kwargs)
    readonly=kwargs["readonly"] if DESTINATION else "?mode=ro" in str(database)
    if readonly != (not DESTINATION): return connect(database,*args,**kwargs)
    current=Path(database) if DESTINATION else selected
    saved=current.with_name(current.name+".held")
    current.rename(saved)
    if SYMLINK: current.symlink_to(other)
    else: other.rename(current)
    try: return connect(database,*args,**kwargs)
    finally:
        if SYMLINK: current.unlink()
        else: current.rename(other)
        saved.rename(current)
if DESTINATION: worker._connect=swapped
else: worker.sqlite3.connect=swapped
raise SystemExit(worker.main(sys.argv[2:]))
'''
    code=code.replace('SOURCE',repr(str(source))).replace('OTHER',repr(str(other))).replace('DESTINATION',repr(destination)).replace('SYMLINK',repr(symlink)).replace('ENABLED',repr(enabled))
    def invoke(command, **kwargs):
        assert command[1:4] == ['-I','-S','-B']
        return run([command[0],'-I','-S','-B','-c',code,command[4],*command[5:]], **kwargs)
    monkeypatch.setattr(backup.subprocess,'run',invoke)


def test_regular_source_aba_is_rejected_by_actual_open_descriptor(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';other=tmp_path/'other.fdb'
    _authored_database(source,'selected');_authored_database(other,'outside-selection')
    selected_bytes=source.read_bytes();other_bytes=other.read_bytes()
    _connect_substitution(monkeypatch,source,other)
    with pytest.raises(ValueError,match='database identity'):
        backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert source.read_bytes()==selected_bytes and other.read_bytes()==other_bytes
    assert not (tmp_path/'backup/manifest.json').exists()


@pytest.mark.usefixtures('require_descriptor_alias')
def test_regular_destination_aba_never_writes_the_other_database(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';other=tmp_path/'other.fdb'
    _authored_database(source,'selected');_authored_database(other,'keep')
    selected_bytes=source.read_bytes();other_bytes=other.read_bytes()
    _connect_substitution(monkeypatch,source,other,destination=True)
    backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert source.read_bytes()==selected_bytes and other.read_bytes()==other_bytes
    with sqlite3.connect(tmp_path/'backup/project.fdb') as result:
        assert result.execute('SELECT * FROM authored').fetchall()==[('selected',)]


@pytest.mark.parametrize('replace_inode',[True,False])
@pytest.mark.usefixtures('require_descriptor_alias')
def test_partial_manifest_substitution_cannot_return_completion(tmp_path,monkeypatch,replace_inode):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    output=tmp_path/'backup';link=backup.os.link
    def replaced(src,dst,*args,**kwargs):
        if dst=='manifest.json':
            partial=output/'.manifest.partial'
            if replace_inode: partial.rename(output/'retained-original.partial')
            partial.write_bytes(b'keep unrelated metadata')
        return link(src,dst,*args,**kwargs)
    monkeypatch.setattr(backup.os,'link',replaced)
    with pytest.raises(ValueError,match='Published backup file'):
        backup.capture_fdb(source,[],output,20)
    assert (output/'.manifest.partial').read_bytes()==b'keep unrelated metadata'
    assert (output/'manifest.json').read_bytes()==b'keep unrelated metadata'


@pytest.mark.usefixtures('require_descriptor_alias')
def test_success_retains_staging_without_any_pathname_cleanup(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    before=source.read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError('no mutable-name cleanup is permitted')
    monkeypatch.setattr(backup.os,'unlink',forbidden)
    monkeypatch.setattr(backup.os,'rmdir',forbidden)
    output=tmp_path/'backup';manifest=backup.capture_fdb(source,[],output,20)
    stage=next(tmp_path.glob('.fdb-stage-*'))
    assert (stage/'snapshot.sqlite').stat().st_ino==(output/'project.fdb').stat().st_ino
    assert (output/'.manifest.partial').stat().st_ino==(output/'manifest.json').stat().st_ino
    assert (stage/'snapshot.sqlite').stat().st_size==manifest['database']['size']
    assert source.read_bytes()==before


def test_worker_refuses_if_actual_open_handles_cannot_be_established(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    run=backup.subprocess.run
    code='import importlib.util,sys; s=importlib.util.spec_from_file_location("w",sys.argv[1]); w=importlib.util.module_from_spec(s); s.loader.exec_module(w); w._regular_descriptors=lambda:{}; raise SystemExit(w.main(sys.argv[2:]))'
    def invoke(command, **kwargs):
        return run([command[0],'-I','-S','-B','-c',code,command[4],*command[5:]], **kwargs)
    monkeypatch.setattr(backup.subprocess,'run',invoke)
    with pytest.raises(ValueError,match='database identity'):
        backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert not (tmp_path/'backup/manifest.json').exists()


@pytest.mark.usefixtures('require_descriptor_alias')
def test_real_child_connect_harness_also_accepts_valid_selected_source(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';other=tmp_path/'other.fdb'
    _authored_database(source,'selected');_authored_database(other,'outside-selection')
    _connect_substitution(monkeypatch,source,other,enabled=False)
    result=backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert result['source']['name']=='selected.fdb'
    with sqlite3.connect(tmp_path/'backup/project.fdb') as restored:
        assert restored.execute('SELECT value FROM authored').fetchone()==('selected',)


def test_fresh_worker_deadline_is_fail_closed(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    before=source.read_bytes();run=backup.subprocess.run
    code='import importlib.util,sys,time; s=importlib.util.spec_from_file_location("w",sys.argv[1]); w=importlib.util.module_from_spec(s); s.loader.exec_module(w); time.sleep(1); raise SystemExit(w.main(sys.argv[2:]))'
    def invoke(command, **kwargs):
        return run([command[0],'-I','-S','-B','-c',code,command[4],*command[5:]], **kwargs)
    monkeypatch.setattr(backup.subprocess,'run',invoke)
    with pytest.raises(TimeoutError):
        backup.capture_fdb(source,[],tmp_path/'backup',.1)
    assert not (tmp_path/'backup/manifest.json').exists()
    assert source.read_bytes()==before


@pytest.mark.parametrize('destination',[False,True])
def test_parent_aba_cannot_mix_source_wal_or_modify_foreign_sidecars(tmp_path,monkeypatch,destination,request):
    if destination: request.getfixturevalue('require_descriptor_alias')
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';outside=tmp_path/'outside';outside.mkdir()
    selected=sqlite3.connect(source)
    selected.execute('PRAGMA journal_mode=WAL')
    selected.execute('CREATE TABLE facts(v TEXT)');selected.commit()
    selected.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    foreign=outside/('snapshot.sqlite' if destination else source.name)
    foreign.write_bytes(source.read_bytes())
    other=sqlite3.connect(foreign)
    other.execute("INSERT INTO facts VALUES ('outside-WAL')");other.commit()
    selected.execute("INSERT INTO facts VALUES ('selected-WAL')");selected.commit()
    paths=[Path(str(database)+suffix) for database in (source,foreign) for suffix in ('','-wal','-shm')]
    before={path:path.read_bytes() for path in paths}
    run=backup.subprocess.run
    code=r'''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('w',sys.argv[1]);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
connect=w._connect;swaps=[]
def swap(path,*args,**kwargs):
    result=connect(path,*args,**kwargs)
    if kwargs['readonly'] == (not DESTINATION) and not kwargs.get('immutable',False):
        parent=Path(path).parent;held=parent.with_name(parent.name+'.held')
        parent.rename(held);parent.symlink_to(Path(OUTSIDE),target_is_directory=True);swaps.append((parent,held))
    return result
w._connect=swap
try: result=w.main(sys.argv[2:])
finally:
    for parent,held in swaps: parent.unlink();held.rename(parent)
raise SystemExit(result)
'''.replace('DESTINATION',repr(destination)).replace('OUTSIDE',repr(str(outside)))
    def invoke(command,**kwargs):
        return run([command[0],'-I','-S','-B','-c',code,command[4],*command[5:]],**kwargs)
    monkeypatch.setattr(backup.subprocess,'run',invoke)
    try:
        output=tmp_path/'backup'
        if destination:
            backup.capture_fdb(source,[],output,20)
            result=sqlite3.connect('file:'+str(output/'project.fdb')+'?mode=ro&immutable=1',uri=True)
            try: assert result.execute('SELECT * FROM facts').fetchall()==[('selected-WAL',)]
            finally: result.close()
        else:
            with pytest.raises(ValueError,match='WAL/SHM'):
                backup.capture_fdb(source,[],output,20)
            assert not (output/'manifest.json').exists()
        # SQLite read transactions may update SHM read marks; SHM is an
        # ephemeral WAL index, not committed database content. Neither source
        # nor unrelated main/WAL bytes may change or disappear.
        assert {path:path.read_bytes() for path in paths if not str(path).endswith('-shm')} == {path:data for path,data in before.items() if not str(path).endswith('-shm')}
    finally:
        selected.close();other.close()


def test_canonicalizing_sqlite_alias_is_rejected_before_writable_queries(tmp_path,monkeypatch):
    source_dir=tmp_path/'source';source_dir.mkdir()
    source=source_dir/'selected.fdb';_authored_database(source,'selected')
    run=backup.subprocess.run
    code=r'''import importlib.util,sys
spec=importlib.util.spec_from_file_location('w',sys.argv[1]);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
connect=w.sqlite3.connect
snapshot=sys.argv[sys.argv.index('--snapshot')+1]
def canonicalized(database,*args,**kwargs):
    if '?mode=rw' in str(database): raise AssertionError('unsupported host must not open writable SQLite')
    if '&immutable=1' in str(database): database='file:'+snapshot+'?mode=ro&immutable=1'
    return connect(database,*args,**kwargs)
w.sqlite3.connect=canonicalized
raise SystemExit(w.main(sys.argv[2:]))
'''
    def invoke(command,**kwargs):
        return run([command[0],'-I','-S','-B','-c',code,command[4],*command[5:]],**kwargs)
    monkeypatch.setattr(backup.subprocess,'run',invoke)
    with pytest.raises(ValueError,match='descriptor-alias namespace'):
        backup.capture_fdb(source,[],tmp_path/'backup',20)
    stage=next(tmp_path.glob('.fdb-stage-*'))
    assert (stage/'snapshot.sqlite').stat().st_size==0
    assert not (tmp_path/'backup/manifest.json').exists()


def test_unsupported_descriptor_alias_host_refuses_without_mutating_source(tmp_path,descriptor_alias_supported):
    if descriptor_alias_supported: pytest.skip('Host retains descriptor aliases; canonicalization refusal has a separate simulated regression')
    source_dir=tmp_path/'source';source_dir.mkdir();source=source_dir/'selected.fdb'
    _authored_database(source,'selected');before=source.read_bytes()
    with pytest.raises(ValueError,match='descriptor-alias namespace'):
        backup.capture_fdb(source,[],tmp_path/'backup',20)
    assert source.read_bytes()==before
    assert not (tmp_path/'backup/manifest.json').exists()
    stage=next(tmp_path.glob('.fdb-stage-*'))
    assert (stage/'snapshot.sqlite').stat().st_size==0
