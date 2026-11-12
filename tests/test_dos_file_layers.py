"""Host-only content-retaining workspace generation contracts."""
import os
import hashlib
from copy import deepcopy
from pathlib import Path
import pytest
from fdisbull.dos_file_layers import WorkspaceStore,capture_directory,CHUNK_KIND
from test_qemu_dos_history import project,session


@pytest.fixture
def store(session):
    session._artifact=lambda *args:session.project._debug_artifact(session.run_id,*args)
    return WorkspaceStore(session)


def test_directory_inventory_aliases_depth_and_symlink_refusal(tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'Long file name.txt').write_bytes(b'alpha')
    (root/'LONGFI~1.TXT').write_bytes(b'other');(root/'SUB').mkdir();(root/'SUB'/'child.bin').write_bytes(b'\x00\xff')
    result=capture_directory(root)
    paths=[x['dos_path'] for x in result['entries']]
    assert len(paths)==len(set(paths)) and 'LONGFI~1.TXT' in paths and 'SUB\\CHILD.BIN' in paths
    assert result['total_bytes']==12 and 'ABA' in result['consistency']
    (root/'link').symlink_to(root/'SUB',target_is_directory=True)
    with pytest.raises(ValueError,match='symlinks'): capture_directory(root)


def test_capture_bounds_and_unstable_double_scan(tmp_path,monkeypatch):
    root=tmp_path/'input';root.mkdir();(root/'A.TXT').write_bytes(b'123')
    with pytest.raises(ValueError,match='bytes'): capture_directory(root,max_bytes=2)
    import fdisbull.dos_file_layers as module
    original=module._scan;calls=[]
    def changed(*args,**kwargs):
        result=original(*args,**kwargs);calls.append(1)
        if len(calls)==1: (root/'B.TXT').write_bytes(b'x')
        return result
    monkeypatch.setattr(module,'_scan',changed)
    with pytest.raises(ValueError,match='changed'): capture_directory(root)


def test_generations_share_chunks_and_preserve_branches(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'A.DAT').write_bytes(b'A'*65536+b'B')
    capture=capture_directory(root)
    initial=store.seal(capture['entries'],source_root=root,source_identity=capture['root_identity'])
    first=store.load(initial['artifact']);modified=deepcopy(first['entries']);modified[0]['data']=b'A'*65536+b'C'
    child=store.seal(modified,parent=initial['artifact'])
    branch=store.seal(first['entries'],parent=initial['artifact'])
    assert store.load(child['artifact'])['entries'][0]['data']==b'A'*65536+b'C'
    assert store.load(branch['artifact'])['entries'][0]['data']==b'A'*65536+b'B'
    assert store.load(child['artifact'])['manifest']['base']==initial['artifact']
    rows=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',(CHUNK_KIND,)).fetchone()[0]
    assert rows==3
    assert store.inspect(child['artifact'])['difference']
    assert (root/'A.DAT').read_bytes()==b'A'*65536+b'B'


def test_new_keep_exclusive_tombstones_and_original_identity(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'GAME.COM').write_bytes(b'original')
    capture=capture_directory(root)
    initial=store.seal(capture['entries'],source_root=root,source_identity=capture['root_identity'])
    deleted=store.delete_file(initial['artifact'],'GAME.COM')
    assert store.load(deleted['artifact'])['manifest']['tombstones']==['GAME.COM']
    with pytest.raises(ValueError,match='original'):
        store.create_file(deleted['artifact'],'GAME.COM',b'replacement')
    output=store.create_file(deleted['artifact'],'SAVE.DAT',b'save')
    dest=root/'SAVE.DAT';receipt=store.keep(output['artifact'],'SAVE.DAT',dest)
    assert receipt['durable'] and dest.read_bytes()==b'save'
    assert not any(e['dos_path']=='SAVE.DAT' for e in store.load(initial['artifact'])['entries'])
    with pytest.raises(FileExistsError):store.keep(output['artifact'],'SAVE.DAT',dest)
    renamed=store.rename_file(initial['artifact'],'GAME.COM','OTHER.COM')
    with pytest.raises(ValueError,match='witnessed new'):
        store.keep(renamed['artifact'],'OTHER.COM',tmp_path/'output.com')


def test_unproven_raw_snapshot_is_not_keepable_and_symlink_destination_refused(store,tmp_path):
    root=tmp_path/'input';root.mkdir();capture=capture_directory(root)
    initial=store.seal([],source_root=root,source_identity=capture['root_identity'])
    entries=[dict(path='SAVE.DAT',dos_path='SAVE.DAT',type='file',data=b'x',attributes=0x20,dos_date=0,dos_time=0)]
    raw=store.seal(entries,parent=initial['artifact'])
    with pytest.raises(ValueError,match='witnessed new'):store.keep(raw['artifact'],'SAVE.DAT',tmp_path/'bad')
    proven=store.create_file(initial['artifact'],'SAVE.DAT',b'x')
    external=tmp_path/'outside';external.mkdir();(tmp_path/'link').symlink_to(external,target_is_directory=True)
    with pytest.raises(OSError):store.keep(proven['artifact'],'SAVE.DAT',tmp_path/'link'/'save.dat')
    assert not (external/'save.dat').exists()


def test_corrupt_chunk_is_refused_without_mutation(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'A').write_bytes(b'content')
    capture=capture_directory(root)
    state=store.seal(capture['entries'],source_root=root,source_identity=capture['root_identity'])
    chunk=state['manifest']['entries'][0]['chunks'][0]['artifact']
    with store.project.transaction(True):store.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',chunk))
    with pytest.raises(ValueError,match='hash'):store.load(state['artifact'])
    assert (root/'A').read_bytes()==b'content'


def test_deleted_base_payload_still_required_for_child_and_original_host_alias_protected(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'Long original.txt').write_bytes(b'unique-original')
    capture=capture_directory(root)
    base=store.seal(capture['entries'],source_root=root,source_identity=capture['root_identity'])
    original=store.load(base['artifact'])['entries'][0]
    child=store.delete_file(base['artifact'],original['dos_path'])
    with pytest.raises(ValueError,match='original host path'):
        store.create_file(child['artifact'],'OTHER.TXT',b'new',path='Long original.txt')
    chunk=base['manifest']['entries'][0]['chunks'][0]['artifact']
    with store.project.transaction(True):store.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',chunk))
    with pytest.raises(ValueError,match='hash'):
        store.load(child['artifact'])


def test_witnessed_write_resize_compare_and_branch_retention(store,tmp_path):
    root=tmp_path/'input';root.mkdir();cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    created=store.create_file(base['artifact'],'SAVE.DAT',b'ab')
    digest=lambda data:hashlib.sha256(data).hexdigest()
    written=store.write_range(created['artifact'],'SAVE.DAT',4,b'X',expected_sha256=digest(b'ab'))
    assert store.load(written['artifact'])['entries'][0]['data']==b'ab\0\0X'
    resized=store.resize_file(written['artifact'],'SAVE.DAT',3,expected_sha256=digest(b'ab\0\0X'))
    assert store.keep(resized['artifact'],'SAVE.DAT',root/'SAVE.DAT')['durable']
    assert (root/'SAVE.DAT').read_bytes()==b'ab\0'
    assert store.load(created['artifact'])['entries'][0]['data']==b'ab'
    with pytest.raises(ValueError,match='changed before write'):
        store.write_file(created['artifact'],'SAVE.DAT',b'bad',expected_sha256=digest(b'stale'))


def test_live_refresh_pins_identity_and_rejects_private_conflicts(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'A.TXT').write_bytes(b'old')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'],mode='live')
    (root/'A.TXT').write_bytes(b'changed');(root/'B.TXT').write_bytes(b'host')
    refreshed=store.refresh(base['artifact'])
    assert store.load(base['artifact'])['entries'][0]['data']==b'old'
    assert [x['data'] for x in store.load(refreshed['artifact'])['entries']]==[b'changed',b'host']
    deleted=store.delete_file(refreshed['artifact'],'B.TXT')
    with pytest.raises(ValueError,match='original'):
        store.create_file(deleted['artifact'],'B.TXT',b'replaced')
    with pytest.raises(ValueError,match='conflict'):
        store.refresh(deleted['artifact'])
    root.rename(tmp_path/'old-root');root.mkdir()
    with pytest.raises(ValueError,match='identity changed'):
        store.refresh(refreshed['artifact'])


def test_checkpointed_refresh_stages_changes_and_preserves_generations(store,tmp_path):
    root=tmp_path/'input';root.mkdir()
    (root/'GAME.COM').write_bytes(b'program')
    (root/'A.TXT').write_bytes(b'old')
    (root/'DELETE.TXT').write_bytes(b'remove')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    base_entries=store.load(base['artifact'])['entries']
    source=next(item for item in base_entries if item['dos_path']=='GAME.COM')

    (root/'A.TXT').write_bytes(b'new')
    (root/'DELETE.TXT').unlink()
    (root/'ADDED.TXT').write_bytes(b'host addition')
    first=store.refresh(base['artifact'],source_dospath='GAME.COM',
                        expected_source_sha256=source['sha256'])
    first_loaded=store.load(first['artifact'])
    assert first_loaded['manifest']['mode']=='checkpointed'
    assert first_loaded['manifest']['parent']==base['artifact']
    assert {item['dos_path']:item.get('data') for item in first_loaded['entries']} == {
        'GAME.COM':b'program','A.TXT':b'new','ADDED.TXT':b'host addition'}
    assert 'DELETE.TXT' in first_loaded['manifest']['tombstones']
    assert store.load(base['artifact'])['entries']==base_entries
    assert set(base['manifest']['protected_dos_paths']) <= set(first_loaded['manifest']['protected_dos_paths'])
    assert 'ADDED.TXT' in first_loaded['manifest']['protected_dos_paths']

    (root/'ADDED.TXT').write_bytes(b'host changed again')
    (root/'NEXT.TXT').write_bytes(b'next')
    second=store.refresh(first['artifact'],source_dospath='GAME.COM',
                         expected_source_sha256=source['sha256'])
    second_loaded=store.load(second['artifact'])
    assert second_loaded['manifest']['parent']==first['artifact']
    assert {item['dos_path']:item.get('data') for item in second_loaded['entries']} == {
        'GAME.COM':b'program','A.TXT':b'new','ADDED.TXT':b'host changed again','NEXT.TXT':b'next'}
    assert store.load(first['artifact'])['entries']==first_loaded['entries']
    assert set(first_loaded['manifest']['protected_dos_paths']) <= set(second_loaded['manifest']['protected_dos_paths'])


def test_checkpointed_refresh_ignores_inventory_order_when_comparing_host_reference(store,tmp_path):
    root=tmp_path/'input';root.mkdir()
    (root/'GAME.COM').write_bytes(b'program')
    (root/'a b.txt').write_bytes(b'space')
    (root/'a-b.txt').write_bytes(b'hyphen')
    captured=capture_directory(root)
    base=store.seal(captured['entries'],source_root=root,
                    source_identity=captured['root_identity'])
    base_entries=store.load(base['artifact'])['entries']
    # A checkpoint inventory can be ordered by FAT alias rather than the
    # original host path traversal; all semantic entry data stays identical.
    reordered=store.seal(list(reversed(base_entries)),parent=base['artifact'],
                         reason='checkpointed-qcow2-capture')
    (root/'a b.txt').write_bytes(b'host updated')
    refreshed=store.refresh(reordered['artifact'])
    entries={item['dos_path']:item for item in store.load(refreshed['artifact'])['entries']}
    assert entries['A_B~1.TXT']['data']==b'host updated'
    assert entries['A-B.TXT']['data']==b'hyphen'


@pytest.mark.parametrize('change', ['modified','deleted','aliased-away'])
def test_refresh_source_guard_refuses_before_generation_publication(store,tmp_path,change):
    root=tmp_path/'input';root.mkdir()
    (root/'GAME.COM').write_bytes(b'program')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    source=store.load(base['artifact'])['entries'][0]
    if change=='modified':
        (root/'GAME.COM').write_bytes(b'edited program')
    elif change=='deleted':
        (root/'GAME.COM').unlink()
    else:
        (root/'GAME.COM').rename(root/'OTHER.COM')
    before=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                    ("workspace-generation",)).fetchone()[0]
    with pytest.raises(ValueError,match='source changed|source differs'):
        store.refresh(base['artifact'],source_dospath='GAME.COM',
                      expected_source_sha256=source['sha256'])
    after=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                   ("workspace-generation",)).fetchone()[0]
    assert after==before


def test_refresh_requires_source_guard_pair_and_rejects_private_conflicts(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'GAME.COM').write_bytes(b'program')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    source=store.load(base['artifact'])['entries'][0]
    with pytest.raises(ValueError,match='supplied together'):
        store.refresh(base['artifact'],source_dospath='GAME.COM')
    staged=store.create_file(base['artifact'],'SAVE.DAT',b'save')
    (root/'HOST.TXT').write_bytes(b'new host data')
    before=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                    ("workspace-generation",)).fetchone()[0]
    with pytest.raises(ValueError,match='conflict'):
        store.refresh(staged['artifact'],source_dospath='GAME.COM',
                      expected_source_sha256=source['sha256'])
    after=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                   ("workspace-generation",)).fetchone()[0]
    assert after==before


@pytest.mark.parametrize('mutation', ['symlink','unstable'])
def test_checkpointed_refresh_capture_failures_publish_nothing(store,tmp_path,monkeypatch,mutation):
    root=tmp_path/'input';root.mkdir();(root/'GAME.COM').write_bytes(b'program')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    if mutation=='symlink':
        (root/'LINK').symlink_to(root/'GAME.COM')
    else:
        import fdisbull.dos_file_layers as module
        original=module._scan
        calls=[]
        def unstable(*args,**kwargs):
            result=original(*args,**kwargs)
            calls.append(None)
            if len(calls)==1:
                (root/'LATE.TXT').write_bytes(b'changed between scans')
            return result
        monkeypatch.setattr(module,'_scan',unstable)
    before=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                    ("workspace-generation",)).fetchone()[0]
    with pytest.raises(ValueError):
        store.refresh(base['artifact'])
    after=store.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                   ("workspace-generation",)).fetchone()[0]
    assert after==before


def test_general_export_preserves_original_and_refuses_overwrite(store,tmp_path):
    root=tmp_path/'input';root.mkdir();(root/'A.TXT').write_bytes(b'original')
    cap=capture_directory(root)
    base=store.seal(cap['entries'],source_root=root,source_identity=cap['root_identity'])
    dest=tmp_path/'export.txt'
    assert store.export_file(base['artifact'],'A.TXT',dest)['durable']
    assert dest.read_bytes()==b'original'
    with pytest.raises(FileExistsError): store.export_file(base['artifact'],'A.TXT',dest)
    with pytest.raises(ValueError,match='original path'):
        store.export_file(base['artifact'],'A.TXT',root/'A.TXT')
    assert (root/'A.TXT').read_bytes()==b'original'
