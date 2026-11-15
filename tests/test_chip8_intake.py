"""Pinned corpus intake; authored source and no native execution."""
import hashlib
import json
from pathlib import Path

import pytest

from fdisbull.chip8 import PROFILE
from fdisbull.chip8_intake import create_intake,inspect_project
from fdisbull.project import Project


def _blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


@pytest.fixture
def inputs(tmp_path,monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'objects'))
    data=bytes.fromhex('6001 1200')+b'\xff';rom=tmp_path/'game.ch8';rom.write_bytes(data)
    member={'key':'authored','title':'Authored ROM','author':'Tester','platform':'chip8',
            'git_blob_sha':_blob(data),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    doc={'source_repo':'https://example.org/author/corpus','source_commit':'1'*40,
         'source_metadata_blob_sha':'2'*40,'source_license':'author-attributed test notice','programs':[member]}
    manifest=tmp_path/'manifest.json'
    def put(value=doc):
        raw=json.dumps(value,ensure_ascii=False).encode();manifest.write_bytes(raw);return hashlib.sha256(raw).hexdigest()
    return tmp_path,rom,data,doc,manifest,put


def test_identity_aliases_cold_reopen_and_no_raw_receipt(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put();alias=root/'alias.ch8';alias.write_bytes(data)
    with create_intake(root/'one.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as one:
        first=inspect_project(one,expected_manifest_sha256=pin)
        assert first['status']=='exact-identity-verified' and first['gate']=='G0'
        assert first['source']['sha256']==hashlib.sha256(data).hexdigest()
        assert first['source']['member_path']=='roms/authored.ch8' and first['provenance']['edition'] is None
        assert first['claims']['g1_g8']=='not run' and first['profile']['id']==PROFILE
        assert 'private content-addressed source object' in first['claims']['storage']
        assert data.hex() not in json.dumps(first)
    with create_intake(root/'two.fdb',alias,manifest_path=manifest,manifest_sha256=pin,member='authored') as two:
        second=inspect_project(two)
        assert second['intake_sha256']==first['intake_sha256'] and second['project']['id']!=first['project']['id']
    with Project(root/'one.fdb') as reopened:
        again=inspect_project(reopened,expected_intake_sha256=first['intake_sha256'])
        assert again==first
        with pytest.raises(ValueError,match='expected intake'):inspect_project(reopened,expected_intake_sha256='0'*64)
        with pytest.raises(ValueError,match='expected manifest'):inspect_project(reopened,expected_manifest_sha256='0'*64)


@pytest.mark.parametrize('change',['size','sha256','git_blob_sha','platform','member','profile','manifest_pin','duplicate','unknown'])
def test_bad_pins_and_manifest_refuse_before_project_or_store(inputs,change):
    root,rom,data,doc,manifest,put=inputs;member='authored';profile=PROFILE
    if change=='size':doc['programs'][0]['size']+=1
    if change=='sha256':doc['programs'][0]['sha256']='0'*64
    if change=='git_blob_sha':doc['programs'][0]['git_blob_sha']='0'*40
    if change=='platform':doc['programs'][0]['platform']='schip'
    if change=='member':member='missing'
    if change=='profile':profile='xo-chip'
    if change=='duplicate':doc['programs'].append(dict(doc['programs'][0]))
    if change=='unknown':doc['programs'][0]['payload']=data.hex()
    pin=put()
    if change=='manifest_pin':pin='0'*64
    with pytest.raises(ValueError):create_intake(root/'bad.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member=member,profile=profile)
    assert not (root/'bad.fdb').exists() and not (root/'objects').exists()


@pytest.mark.parametrize('raw',[b'{"source_repo":1,"source_repo":2}',b'{"x":NaN}',b'\xff'])
def test_invalid_manifest_encoding_duplicate_or_nonfinite_is_refused(inputs,raw):
    root,rom,data,doc,manifest,put=inputs;manifest.write_bytes(raw)
    with pytest.raises(ValueError):create_intake(root/'bad.fdb',rom,manifest_path=manifest,manifest_sha256=hashlib.sha256(raw).hexdigest(),member='authored')
    assert not (root/'bad.fdb').exists() and not (root/'objects').exists()


def test_symlink_manifest_and_same_filename_changed_bytes_refuse(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put();link=root/'link.json';link.symlink_to(manifest)
    with pytest.raises(ValueError):create_intake(root/'link.fdb',rom,manifest_path=link,manifest_sha256=pin,member='authored')
    rom.write_bytes(b'other')
    with pytest.raises(ValueError):create_intake(root/'wrong.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored')
    assert not (root/'link.fdb').exists() and not (root/'wrong.fdb').exists() and not (root/'objects').exists()


def test_source_snapshot_not_reread_after_validation(inputs,monkeypatch):
    import fdisbull.chip8_intake as intake
    root,rom,data,doc,manifest,put=inputs;pin=put();original=intake.load_image
    def changing(path,**kwargs):
        image=original(path,**kwargs);Path(path).write_bytes(b'other');return image
    monkeypatch.setattr(intake,'load_image',changing)
    with create_intake(root/'stable.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        assert inspect_project(project)['source']['sha256']==hashlib.sha256(data).hexdigest()
        assert project.regions(1)[0].data==data
    assert rom.read_bytes()==b'other'


def test_tamper_unavailable_object_patched_version_and_transaction(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'case.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        with project.transaction(True):
            with pytest.raises(ValueError,match='transaction'):inspect_project(project)
        stored=project.meta['loader_metadata']['chip8_conversion_intake'];stored['receipt']['source']['size']+=1
        with pytest.raises(ValueError,match='receipt|metadata'):inspect_project(project)
        stored['receipt']['source']['size']-=1
        patched=project.patch(0x201,'02')['version']
        with pytest.raises(ValueError,match='original'):inspect_project(project,version=patched)
        object_path=root/'objects'/hashlib.sha256(data).hexdigest();object_path.write_bytes(b'wrong')
        with pytest.raises(ValueError,match='object|identity'):inspect_project(project,version=1)


@pytest.mark.parametrize('repo',['http://example.org/a','https://user@example.org/a','https://example.org/a?x=1','https://example.org/a#part'])
def test_invalid_repository_declarations_do_not_create_project(inputs,repo):
    root,rom,data,doc,manifest,put=inputs;doc['source_repo']=repo;pin=put()
    with pytest.raises(ValueError,match='repository'):create_intake(root/'bad.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored')
    assert not (root/'bad.fdb').exists() and not (root/'objects').exists()


def test_source_loader_metadata_change_and_missing_object_refuse(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'case.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        row=project.db.execute('SELECT document FROM target_sources WHERE version=1').fetchone()
        source=json.loads(row['document']);source['loader_options']['arch']='x86'
        with project.transaction(True):project.db.execute('UPDATE target_sources SET document=? WHERE version=1',(json.dumps(source),))
        with pytest.raises(ValueError,match='loader'):inspect_project(project)
        source['loader_options']['arch']='chip8'
        with project.transaction(True):project.db.execute('UPDATE target_sources SET document=? WHERE version=1',(json.dumps(source),))
        (root/'objects'/hashlib.sha256(data).hexdigest()).unlink()
        with pytest.raises(ValueError,match='missing|unavailable'):inspect_project(project)


def test_unselected_nonclassic_member_can_be_larger_than_classic_ram(inputs):
    root,rom,data,doc,manifest,put=inputs
    doc['programs'].append({'key':'other','title':'Other','author':'Tester','platform':'xo',
        'git_blob_sha':'0'*40,'size':4096,'sha256':'0'*64})
    pin=put()
    with create_intake(root/'valid.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        assert inspect_project(project)['source']['member']=='authored'


def test_fifo_manifest_is_rejected_without_waiting_for_writer(inputs):
    import os
    root,rom,data,doc,manifest,put=inputs;fifo=root/'manifest.fifo';os.mkfifo(fifo)
    with pytest.raises(ValueError,match='regular file'):
        create_intake(root/'fifo.fdb',rom,manifest_path=fifo,manifest_sha256='0'*64,member='authored')
    assert not (root/'fifo.fdb').exists() and not (root/'objects').exists()
