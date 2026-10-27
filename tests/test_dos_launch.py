"""A guest filename is an execution detail, never file-format evidence."""
import hashlib
from pathlib import Path

import pytest

from fdisbull.dos_launch import LaunchAlias, guest_name
from fdisbull.guest_assets import uploads
from fdisbull.project import Project
from test_dos_loader import mz_file


def test_launch_alias_preserves_casefold_collisions_and_changed_output(tmp_path):
    data=mz_file();name=guest_name('AGI',hashlib.sha256(data).hexdigest())
    collision=tmp_path/name.lower();collision.write_bytes(b'existing user data')
    with pytest.raises(ValueError,match='collides'):
        LaunchAlias(tmp_path,name,data)
    assert collision.read_bytes()==b'existing user data'
    collision.unlink()
    alias=LaunchAlias(tmp_path,name,data)
    assert alias.path.read_bytes()==data
    alias.path.write_bytes(b'guest changed this file')
    assert alias.close()['status']=='retained_changed'
    assert alias.path.read_bytes()==b'guest changed this file'


def test_mz_target_suffix_does_not_override_structure_but_private_assets_stay_excluded(tmp_path):
    target=tmp_path/'GAME.SAV';target.write_bytes(mz_file())
    private=tmp_path/'private.sav';private.write_bytes(b'not an executable')
    with Project.create(tmp_path/'analysis.fdb',target) as project:
        assert project.meta['format']=='MZ'
        result=uploads(project,tmp_path,target.name)
        assert result[0]['sha256']==project.meta['source_sha256']
        with pytest.raises(ValueError,match='databases or saved states'):
            uploads(project,tmp_path,target.name,[target.name,private.name])


def test_alias_replacement_between_check_and_cleanup_is_preserved(tmp_path,monkeypatch):
    data=mz_file();alias=LaunchAlias(tmp_path,'TEMP.EXE',data)
    read=Path.read_bytes;replaced=False
    def replace_after_read(path):
        nonlocal replaced
        result=read(path)
        if path==alias.path and not replaced:
            replaced=True
            replacement=tmp_path/'replacement';replacement.write_bytes(b'external user output')
            replacement.replace(alias.path)
        return result
    monkeypatch.setattr(Path,'read_bytes',replace_after_read)
    result=alias.close()
    assert result['status']=='retained_changed'
    assert Path(result['path']).read_bytes()==b'external user output'
