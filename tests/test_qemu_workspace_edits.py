"""Host-only staged workspace edit contracts."""
from copy import deepcopy
import hashlib
import pytest
from fdisbull.qemu_workspace import QemuDOSWorkspaceMixin
from fdisbull.dos_file_layers import WorkspaceStore, capture_directory
from fdisbull.qemu_workspace import init_state
from fdisbull import dos_workspace_fat as fat
from test_dos_workspace_fat import _floppy
from test_qemu_workspace import session, _configure, _disk, _init


def prepared(session):
    disk=_disk();_configure(session,disk);_init(session,disk)
    session.__class__=type('EditHarness',(QemuDOSWorkspaceMixin,session.__class__),{})
    return session


def test_staged_create_write_resize_rename_delete_preserves_active(session):
    s=prepared(session);before=deepcopy(s._dos_workspace)
    base=before['generation']['artifact']
    result=s.workspace_edit(base,'create',path='D:\\SAVE.DAT',data=b'abc')
    assert result['active'] is False and not result['guest_create_provenance']
    generation=result['generation']['artifact']
    digest=lambda value:hashlib.sha256(value).hexdigest()
    changed=s.workspace_edit(generation,'write-range',path='SAVE.DAT',data=b'Z',offset=1,expected_sha256=digest(b'abc'))
    resized=s.workspace_edit(changed['generation']['artifact'],'resize',path='SAVE.DAT',size=2,expected_sha256=digest(b'aZc'))
    renamed=s.workspace_edit(resized['generation']['artifact'],'rename',path='SAVE.DAT',destination='SAVED.DAT')
    deleted=s.workspace_edit(renamed['generation']['artifact'],'delete',path='SAVED.DAT')
    assert s._dos_workspace==before
    store=WorkspaceStore(s)
    assert next(x for x in store.load(resized['generation']['artifact'])['entries'] if x['dos_path']=='SAVE.DAT')['data']==b'aZ'
    assert 'SAVED.DAT' in store.load(deleted['generation']['artifact'])['manifest']['tombstones']
    assert not any(x['dos_path']=='SAVE.DAT' for x in store.load(base)['entries'])


def test_validation_and_stale_write_do_not_stage(session):
    s=prepared(session);base=s._dos_workspace['generation']['artifact']
    before=s.project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
    for kwargs in [dict(operation='delete',path='GAME.COM',data=b'x'),dict(operation='write',path='GAME.COM',data=b'x',expected_sha256='bad'),dict(operation='refresh',path='GAME.COM')]:
        with pytest.raises(ValueError): s.workspace_edit(base,**kwargs)
    assert s.project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==before
    with pytest.raises(ValueError,match='changed before write'):
        s.workspace_edit(base,'write',path='GAME.COM',data=b'x',expected_sha256='0'*64)
    assert s._dos_workspace['generation']['artifact']==base


def test_rejects_cross_workspace_generation_and_refresh_without_root(session):
    s=prepared(session);store=WorkspaceStore(s);base=s._dos_workspace['generation']['artifact']
    foreign=store.seal([])['artifact']
    with pytest.raises(ValueError,match='different base'):
        s.workspace_edit(foreign,'create',path='SAVE.DAT',data=b'x')
    with pytest.raises(ValueError,match='admitted source root'):
        s.workspace_edit(base,'refresh')
    assert s._dos_workspace['generation']['artifact']==base
    for call in (lambda: s.workspace_files(foreign),
                 lambda: s.workspace_read('GAME.COM',foreign),
                 lambda: s.workspace_export('GAME.COM','/unused',foreign),
                 lambda: s.workspace_keep('GAME.COM','/unused',foreign)):
        with pytest.raises(ValueError,match='different base'): call()
    for call in (lambda: s.workspace_read('C:\\GAME.COM'),
                 lambda: s.workspace_edit(base,'delete',path='C:\\GAME.COM')):
        with pytest.raises(ValueError,match='relative to D'): call()


def prepared_host(session, tmp_path):
    root=tmp_path/'host';root.mkdir()
    source=bytes.fromhex('90ebfd')
    (root/'GAME.COM').write_bytes(source)
    (root/'DATA.TXT').write_bytes(b'old')
    captured=capture_directory(root)
    entries={item['dos_path']:{k:v for k,v in item.items()
             if k in ('type','data','attributes','dos_date','dos_time')}
             for item in captured['entries']}
    disk,layout=fat.build_composite(_floppy(),fat.build_volume(entries))
    _configure(session,disk)
    init_state(session,captured,{'freedos':'pinned-fixture-v1'},layout,'GAME.COM','checkpointed')
    session.__class__=type('HostEditHarness',(QemuDOSWorkspaceMixin,session.__class__),{})
    return session,root


def test_checkpointed_refresh_stages_host_revision_preserving_active(session,tmp_path):
    s,root=prepared_host(session,tmp_path);before=deepcopy(s._dos_workspace)
    base=before['generation']['artifact']
    (root/'DATA.TXT').write_bytes(b'host revision')
    (root/'NEW.DAT').write_bytes(b'new host file')
    refreshed=s.workspace_edit(base,'refresh')
    assert refreshed['active'] is False
    assert refreshed['activation']=='cold launch only; running guest unchanged'
    assert refreshed['capture_consistency'].startswith('two stable no-follow passes')
    assert s._dos_workspace==before
    child=refreshed['generation']['artifact']
    assert s.workspace_read('DATA.TXT',child)['data']==b'host revision'
    assert s.workspace_read('DATA.TXT',base)['data']==b'old'
    assert s.workspace_read('DATA.TXT')['data']==b'old'
    assert s.workspace_read('NEW.DAT',child)['data']==b'new host file'


@pytest.mark.parametrize('change',['replace','delete','rename'])
def test_checkpointed_refresh_refuses_changed_source_before_publication(session,tmp_path,change):
    s,root=prepared_host(session,tmp_path);before=deepcopy(s._dos_workspace)
    base=before['generation']['artifact']
    if change=='replace':(root/'GAME.COM').write_bytes(b'changed source')
    elif change=='delete':(root/'GAME.COM').unlink()
    else:(root/'GAME.COM').rename(root/'RENAMED.COM')
    count=s.project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
    with pytest.raises(ValueError,match='source'):
        s.workspace_edit(base,'refresh')
    assert s.project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==count
    assert s._dos_workspace==before


def test_seal_accepts_workspace_process_checkpoint_format(session,monkeypatch):
    import json
    import fdisbull.qemu_dos_checkpoint as cp
    import fdisbull.qemu_workspace as workspace
    s=prepared(session);s._dos_workspace_enabled=True
    saved=s._artifact('test.qcow2','state',b'payload',{'format':cp.WORKSPACE_FORMAT})
    monkeypatch.setattr(s,'save_state',lambda *args,**kwargs: saved)
    monkeypatch.setattr(cp,'_unarchive',lambda data:(b'disk',{'workspace':{'fixture':True}}))
    monkeypatch.setattr(workspace,'restore_workspace',lambda owner,record:{'restored':record})
    assert s.workspace_seal()['status']=={'restored':{'fixture':True}}
