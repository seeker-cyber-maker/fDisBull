"""Immutable flat CHIP-8 layer definitions and private payload storage."""
import hashlib
import sqlite3
import pytest
from fdisbull.chip8 import PROFILE
from fdisbull.project import Project
from fdisbull.target_storage import reference


def _project(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path/'objects'))
    rom=tmp_path/'authored.ch8';rom.write_bytes(bytes.fromhex('6001 1200'))
    return rom, tmp_path/'project.fdb'


def test_layers_are_version_bound_immutable_flat_definitions(tmp_path, monkeypatch):
    rom,path=_project(tmp_path,monkeypatch);source=rom.read_bytes()
    with Project.create(path,rom,arch='chip8') as project:
        code=project.debug_layer('alternate opcode',kind='execute',patches=[
            {'address':0x201,'expected_hex':'01','data_hex':'02'}])
        ram=project.debug_layer('runtime byte',kind='ram',patches=[
            {'address':'0x300','expected_hex':'00','data_hex':'7a'}])
        assert code['address_model']==ram['address_model']=='chip8-flat-4k'
        assert code['chip8_profile']==ram['chip8_profile']==PROFILE
        assert project.regions(1)[0].data==source
        assert project.debug_layer_info(code['layer'])['sha256']==code['sha256']
        child=project.patch(0x201,'03')['version']
        other=project.debug_layer('child only',kind='execute',version=child,patches=[
            {'address':0x201,'expected_hex':'03','data_hex':'04'}])
        assert other['version']==child and code['version']==1
    with sqlite3.connect(path) as raw:
        assert all(reference(row[0]) for row in raw.execute('SELECT document FROM debug_layers'))
    with Project(path) as project:
        saved=project.debug_layer_info(code['layer'])
        assert saved['patches']==[{'address':'0x201','expected_hex':'01','data_hex':'02'}]
        assert saved['sha256']==code['sha256']
        assert project.regions(1)[0].data==source
    assert rom.read_bytes()==source
    assert hashlib.sha256(source).hexdigest()==project.meta['source_sha256']


@pytest.mark.parametrize('address,data',[(-1,'00'),(0x1000,'00'),(0xfff,'0000'),(True,'00')])
def test_layer_extent_must_fit_exactly_four_kib(tmp_path,monkeypatch,address,data):
    rom,path=_project(tmp_path,monkeypatch)
    with Project.create(path,rom,arch='chip8') as project:
        with pytest.raises(ValueError):
            project.debug_layer('invalid',kind='ram',patches=[
                {'address':address,'expected_hex':data,'data_hex':data}])
        assert project.debug_layers()['layers']==[]


def test_layer_guards_are_equal_length_nonoverlapping_and_flat(tmp_path,monkeypatch):
    rom,path=_project(tmp_path,monkeypatch)
    with Project.create(path,rom,arch='chip8') as project:
        for patches in ([{'address':0x200,'cs':0,'expected_hex':'60','data_hex':'60'}],
                        [{'address':0x200,'expected_hex':'60','data_hex':'6001'}],
                        [{'address':0x200,'expected_hex':'6001','data_hex':'6002'},
                         {'address':0x201,'expected_hex':'01','data_hex':'03'}]):
            with pytest.raises(ValueError):project.debug_layer('invalid',kind='execute',patches=patches)
        assert project.debug_layers()['layers']==[]
