"""Atomic publication and failure boundaries for DOS workspace exports."""
import hashlib
import os
from pathlib import Path

import pytest

import fdisbull.dos_file_layers as file_layers
from fdisbull.dos_file_layers import WorkspaceStore, capture_directory
from test_qemu_dos_history import project, session


@pytest.fixture
def store(session):
    session._artifact=lambda *args:session.project._debug_artifact(session.run_id,*args)
    return WorkspaceStore(session)


def _generation(store,tmp_path):
    root=tmp_path/'input';root.mkdir()
    (root/'SAVE.DAT').write_bytes(b'workspace-save-bytes')
    captured=capture_directory(root)
    generation=store.seal(captured['entries'],source_root=root,
                          source_identity=captured['root_identity'])
    return generation['artifact']


def _staged_names(directory):
    return sorted(path.name for path in directory.iterdir()
                  if path.name.startswith('.fdisbull-export-'))


def test_partial_staging_failure_never_publishes_destination(store,tmp_path,monkeypatch):
    generation=_generation(store,tmp_path)
    destination=tmp_path/'exported.dat'
    original_write=os.write
    calls=[]

    def interrupted_write(fd,data):
        calls.append(None)
        if len(calls)==1:
            return original_write(fd,data[:3])
        raise OSError('injected partial-write failure')

    monkeypatch.setattr(file_layers.os,'write',interrupted_write)
    with pytest.raises(OSError,match='partial-write'):
        store.export_file(generation,'SAVE.DAT',destination)
    assert not destination.exists()
    assert _staged_names(tmp_path)==[]


def test_final_name_collision_racing_publication_preserves_existing_bytes(store,tmp_path,monkeypatch):
    generation=_generation(store,tmp_path)
    destination=tmp_path/'exported.dat'
    original_link=os.link
    injected=[]

    def racing_link(src,dst,*,src_dir_fd=None,dst_dir_fd=None,follow_symlinks=True):
        if not injected:
            injected.append(None)
            fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=dst_dir_fd)
            try:
                os.write(fd,b'concurrent-owner')
            finally:
                os.close(fd)
        return original_link(src,dst,src_dir_fd=src_dir_fd,dst_dir_fd=dst_dir_fd,
                             follow_symlinks=follow_symlinks)

    monkeypatch.setattr(file_layers.os,'link',racing_link)
    with pytest.raises(FileExistsError):
        store.export_file(generation,'SAVE.DAT',destination)
    assert destination.read_bytes()==b'concurrent-owner'
    assert _staged_names(tmp_path)==[]


def test_receipt_failure_keeps_durable_published_file_and_reports_no_replay(store,tmp_path,monkeypatch):
    generation=_generation(store,tmp_path)
    destination=tmp_path/'exported.dat'
    original_artifact=store.session._artifact

    def reject_receipt(name,kind,data,metadata):
        if kind=='workspace-export-receipt':
            raise OSError('injected receipt persistence failure')
        return original_artifact(name,kind,data,metadata)

    monkeypatch.setattr(store.session,'_artifact',reject_receipt)
    with pytest.raises(OSError,match='receipt persistence') as caught:
        store.export_file(generation,'SAVE.DAT',destination)
    assert destination.read_bytes()==b'workspace-save-bytes'
    assert caught.value.result['durable'] is True
    assert caught.value.result['receipt_persisted'] is False
    assert caught.value.result['publication']=='uncertain; do not replay'
    assert _staged_names(tmp_path)==[]


def test_successful_publication_preserves_receipt_shape_and_private_mode(store,tmp_path):
    generation=_generation(store,tmp_path)
    destination=tmp_path/'exported.dat'
    receipt=store.export_file(generation,'SAVE.DAT',destination)
    assert receipt['generation']==generation
    assert receipt['destination']==str(destination)
    assert receipt['size']==len(b'workspace-save-bytes')
    assert receipt['sha256']==hashlib.sha256(b'workspace-save-bytes').hexdigest()
    assert receipt['durable'] is True and isinstance(receipt['artifact'],str)
    assert destination.read_bytes()==b'workspace-save-bytes'
    assert destination.stat().st_mode & 0o777==0o600
    assert _staged_names(tmp_path)==[]
