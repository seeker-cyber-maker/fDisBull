"""Integrity and packaging tests use authored bytes; no game is executed."""
from copy import deepcopy
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import zipfile

import pytest


ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def checker():
    return runpy.run_path(str(ROOT/'scripts/check_freeware_games.py'))


def fixture_corpus(root):
    payloads={
        'README.md':(b'Authored integrity fixture, not recovered game behavior.\n',None,'documentation'),
        'tic-tac-toe/LICENSE':(b'Authored fixture license.\n','tic-tac-toe','license'),
        'five-dice/LICENSE':(b'Authored fixture license.\n','five-dice','license'),
        'snake/LICENSE':(b'Authored fixture license.\n','snake','license'),
        'tic-tac-toe/base.com':(bytes.fromhex('b8004ccd21'),'tic-tac-toe','binary'),
        'tic-tac-toe/variant.com':(bytes.fromhex('b8014ccd21'),'tic-tac-toe','binary'),
        'five-dice/base.com':(bytes.fromhex('cd20'),'five-dice','binary'),
        'snake/index.html':(b'<!doctype html><title>Authored fixture</title>','snake','browser'),
        'snake/app.mjs':(b'export const fixture = true;\n','snake','source'),
    }
    files=[];root.mkdir(parents=True)
    for name,(data,game,category) in payloads.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'game':game,'category':category})
    by_path={record['path']:record for record in files}
    versions=[]
    for identifier,game,name,format_,parent in [
        ('ttt-base','tic-tac-toe','tic-tac-toe/base.com','dos-com',None),
        ('ttt-variant','tic-tac-toe','tic-tac-toe/variant.com','dos-com','ttt-base'),
        ('dice-base','five-dice','five-dice/base.com','dos-com',None),
        ('snake-browser','snake','snake/index.html','browser-bundle',None)]:
        versions.append({'id':identifier,'game':game,'artifact':name,'format':format_,
            'sha256':by_path[name]['sha256'],'parent':parent,'kind':'full-game',
            'behavior':'Authored fixture only.','qualification':'Inventory test; no execution claim.'})
    manifest={'format':'fdisbull-freeware-game-versions-1','games':['tic-tac-toe','five-dice','snake'],
        'files':files,'versions':versions,'licenses':{game:{'path':game+'/LICENSE','identifier':'CC0-1.0'}
            for game in ('tic-tac-toe','five-dice','snake')},
        'provenance':{'scope':'authored bytes'},'coverage':{'scope':'inventory only'}}
    write_manifest(root,manifest);return manifest


def write_manifest(root,manifest):
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


def test_authored_inventory_checks_all_three_games_without_executing(checker,tmp_path):
    root=tmp_path/'corpus';manifest=fixture_corpus(root)
    report=checker['check_corpus'](root)
    assert report['ok'] is True and report['files']==len(manifest['files'])
    assert report['versions']==4 and set(report['games'])=={'tic-tac-toe','five-dice','snake'}


@pytest.mark.parametrize('format_',['dos-com','dos-mz','x86-16-block','python-reference','uil-module',
    'source-reference','pe32','pe64','windows-ne','elf64','macho-arm64','browser-bundle',
    'module-wasm','module-wgsl','archive-zip','archive-tar'])
def test_all_requested_format_labels_are_inventory_metadata_not_decoder_claims(checker,tmp_path,format_):
    root=tmp_path/'corpus';manifest=fixture_corpus(root)
    manifest['versions'][-1].update(format=format_,kind='reference')
    write_manifest(root,manifest);report=checker['check_corpus'](root)
    assert report['ok'] is True and 'no game execution' in report['scope']


@pytest.mark.parametrize('failure',['bad-hash','bad-size','missing','extra','duplicate-path',
    'case-collision','unsafe-path','unknown-game','bad-version-hash','bad-version-owner',
    'missing-parent','cross-game-parent','cycle','missing-license','extra-game',
    'unlisted-artifact','unknown-format','private-state'])
def test_inventory_refuses_broken_identity_membership_or_game_boundary(checker,tmp_path,failure):
    root=tmp_path/'corpus';manifest=fixture_corpus(root)
    record=manifest['files'][0]
    if failure=='bad-hash':record['sha256']='0'*64
    elif failure=='bad-size':record['bytes']+=1
    elif failure=='missing':(root/record['path']).unlink()
    elif failure=='extra':(root/'unlisted.txt').write_text('extra')
    elif failure=='duplicate-path':manifest['files'].append(deepcopy(record))
    elif failure=='case-collision':
        copied=deepcopy(record);copied['path']='readme.md';manifest['files'].append(copied)
    elif failure=='unsafe-path':record['path']='../outside.txt'
    elif failure=='unknown-game':record['game']='colonization'
    elif failure=='bad-version-hash':manifest['versions'][0]['sha256']='0'*64
    elif failure=='bad-version-owner':manifest['versions'][0]['game']='five-dice'
    elif failure=='missing-parent':manifest['versions'][1]['parent']='unknown'
    elif failure=='cross-game-parent':manifest['versions'][1]['parent']='dice-base'
    elif failure=='cycle':manifest['versions'][0]['parent']='ttt-variant'
    elif failure=='missing-license':manifest['licenses']['snake']['path']='missing-license.txt'
    elif failure=='extra-game':manifest['games'].append('colonization')
    elif failure=='unlisted-artifact':manifest['versions'][0]['artifact']='unlisted.com'
    elif failure=='unknown-format':manifest['versions'][0]['format']='guess'
    elif failure=='private-state':
        data=b'private state must stay out';(root/'snake/game.fdb').write_bytes(data)
        manifest['files'].append({'path':'snake/game.fdb','sha256':hashlib.sha256(data).hexdigest(),
            'bytes':len(data),'game':'snake','category':'database'})
    write_manifest(root,manifest)
    with pytest.raises(ValueError):checker['check_corpus'](root)


@pytest.mark.parametrize('name',['README.md','snake','manifest.json'])
def test_inventory_rejects_symlink_files_directories_and_manifest(checker,tmp_path,name):
    root=tmp_path/'corpus';fixture_corpus(root);source=root/name;outside=tmp_path/'outside'
    source.rename(outside);source.symlink_to(outside,target_is_directory=outside.is_dir())
    with pytest.raises(ValueError,match='symlink'):checker['check_corpus'](root)


def test_duplicate_manifest_keys_are_rejected(checker,tmp_path):
    root=tmp_path/'corpus';fixture_corpus(root)
    data=(root/'manifest.json').read_text();(root/'manifest.json').write_text(data.replace('"format":','"games":[], "format":',1))
    with pytest.raises(ValueError,match='duplicate'):checker['check_corpus'](root)


@pytest.mark.parametrize('failure',[None,'missing-source','bad-hash','wrong-owner','missing-license','duplicate','omitted-notice'])
def test_font_notice_binds_license_source_asset_and_snake_ownership(checker,tmp_path,failure):
    root=tmp_path/'corpus';manifest=fixture_corpus(root)
    for name,data in [('snake/runtime-font/COPYING-GPL-2.0.txt',b'Authored license fixture'),
                      ('snake/runtime-font/int10_font_08-source.h',b'Authored source fixture'),
                      ('snake/runtime-font/int10_font_08.bin',bytes(range(256)))]:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        manifest['files'].append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'game':'snake','category':'font-notice-fixture'})
    notice={'id':'dosbox-x-font-8x8','game':'snake','path':'snake/runtime-font/COPYING-GPL-2.0.txt',
        'identifier':'GPL-2.0-or-later','source':'snake/runtime-font/int10_font_08-source.h',
        'asset':'snake/runtime-font/int10_font_08.bin','sha256':hashlib.sha256(bytes(range(256))).hexdigest(),
        'scope':'Authored integrity fixture, not an actual DOSBox font.'}
    manifest['additional_notices']=[notice]
    if failure=='missing-source':notice['source']='missing.h'
    elif failure=='bad-hash':notice['sha256']='0'*64
    elif failure=='wrong-owner':next(r for r in manifest['files'] if r['path']==notice['asset'])['game']='five-dice'
    elif failure=='missing-license':notice['path']='missing-license'
    elif failure=='duplicate':manifest['additional_notices'].append(deepcopy(notice))
    elif failure=='omitted-notice':del manifest['additional_notices']
    write_manifest(root,manifest)
    if failure is None:assert checker['check_corpus'](root)['ok'] is True
    else:
        with pytest.raises(ValueError):checker['check_corpus'](root)


def test_archive_is_deterministic_and_exactly_contains_catalogued_bytes(checker,tmp_path):
    root=tmp_path/'corpus';manifest=fixture_corpus(root);first=tmp_path/'first.zip';second=tmp_path/'second.zip'
    checker['write_archive'](root,first);checker['write_archive'](root,second)
    assert first.read_bytes()==second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist())=={'freeware-games/manifest.json',*('freeware-games/'+r['path'] for r in manifest['files'])}
        assert archive.read('freeware-games/tic-tac-toe/base.com')==bytes.fromhex('b8004ccd21')
    assert checker['check_archive'](root,first)['ok'] is True
    checker['write_archive'](root,first)
    assert first.read_bytes()==second.read_bytes()


@pytest.mark.parametrize('failure',['extra','missing','changed','duplicate','traversal','symlink','manifest'])
def test_archive_rejects_membership_data_and_link_tampering(checker,tmp_path,failure):
    root=tmp_path/'corpus';fixture_corpus(root);original=tmp_path/'good.zip';bad=tmp_path/'bad.zip'
    checker['write_archive'](root,original)
    with zipfile.ZipFile(original) as archive:entries=[(deepcopy(info),archive.read(info)) for info in archive.infolist()]
    if failure=='extra':entries.append((zipfile.ZipInfo('freeware-games/extra'),b'extra'))
    elif failure=='missing':entries=entries[:-1]
    elif failure=='changed':entries=[(info,bytes(byte^1 for byte in data) if info.filename.endswith('base.com') else data) for info,data in entries]
    elif failure=='duplicate':entries.append(entries[0])
    elif failure=='traversal':entries.append((zipfile.ZipInfo('freeware-games/../outside'),b'extra'))
    elif failure=='manifest':entries=[(info,data+b' ' if info.filename.endswith('manifest.json') else data) for info,data in entries]
    warning=pytest.warns(UserWarning,match='Duplicate name') if failure=='duplicate' else nullcontext()
    with warning, zipfile.ZipFile(bad,'w') as archive:
        for info,data in entries:
            info=deepcopy(info)
            if failure=='symlink' and info.filename.endswith('README.md'):info.external_attr=0o120777<<16
            archive.writestr(info,data)
    with pytest.raises(ValueError):checker['check_archive'](root,bad)


def test_archive_checks_crc_without_trusting_reported_size(checker,tmp_path):
    root=tmp_path/'corpus';fixture_corpus(root);archive=tmp_path/'crc.zip';checker['write_archive'](root,archive)
    with zipfile.ZipFile(archive) as source:info=next(i for i in source.infolist() if i.filename.endswith('base.com'))
    data=bytearray(archive.read_bytes());offset=info.header_offset
    filename,extra=struct.unpack_from('<HH',data,offset+26);at=offset+30+filename+extra
    data[at]^=0xff;archive.write_bytes(data)
    with pytest.raises(ValueError):checker['check_archive'](root,archive)


def test_archive_permissions_are_pinned_for_native_artifacts_and_explicit_launchers(checker,tmp_path):
    root=tmp_path/'corpus';manifest=fixture_corpus(root)
    manifest['versions'][-1]['format']='macho-arm64'
    next(record for record in manifest['files'] if record['path']=='snake/app.mjs')['executable']=True
    write_manifest(root,manifest);archive=tmp_path/'delivery.zip';checker['write_archive'](root,archive)
    with zipfile.ZipFile(archive) as source:
        assert (source.getinfo('freeware-games/snake/index.html').external_attr>>16)&0o777==0o755
        assert (source.getinfo('freeware-games/snake/app.mjs').external_attr>>16)&0o777==0o755
        assert (source.getinfo('freeware-games/README.md').external_attr>>16)&0o777==0o644
        entries=[(deepcopy(info),source.read(info)) for info in source.infolist()]
    with zipfile.ZipFile(archive,'w') as target:
        for info,data in entries:
            if info.filename.endswith('snake/index.html'):info.external_attr=0o100644<<16
            target.writestr(info,data)
    with pytest.raises(ValueError,match='permissions'):checker['check_archive'](root,archive)


def test_companion_archive_cannot_hide_trailing_unlisted_bytes(checker,tmp_path):
    root=tmp_path/'corpus';fixture_corpus(root);archive=tmp_path/'delivery.zip';checker['write_archive'](root,archive)
    with archive.open('ab') as stream:stream.write(b'unlisted trailing payload')
    with pytest.raises(ValueError,match='trailing'):checker['check_archive'](root,archive)


@pytest.mark.parametrize('kind',['inside','symlink','hardlink'])
def test_archive_writer_cannot_overwrite_linked_or_corpus_inputs(checker,tmp_path,kind):
    root=tmp_path/'corpus';fixture_corpus(root);original=tmp_path/'original.zip';original.write_bytes(b'preserve')
    destination=tmp_path/'output.zip'
    if kind=='inside':destination=root/'archive.zip'
    elif kind=='symlink':destination.symlink_to(original)
    else:os.link(original,destination)
    with pytest.raises(ValueError):checker['write_archive'](root,destination)
    assert original.read_bytes()==b'preserve'


def test_cli_prints_compact_json_and_writes_verified_archive(tmp_path):
    root=tmp_path/'corpus';fixture_corpus(root);archive=tmp_path/'delivery.zip'
    ran=subprocess.run([sys.executable,str(ROOT/'scripts/check_freeware_games.py'),'--root',str(root),
        '--write-archive',str(archive),'--archive',str(archive)],capture_output=True,text=True,timeout=30)
    assert ran.returncode==0,ran.stdout+ran.stderr
    assert len(ran.stdout.splitlines())==1 and json.loads(ran.stdout)['ok'] is True


def test_repository_corpus_when_present_is_valid(checker):
    root=ROOT/'fixtures/freeware-games'
    if not (root/'manifest.json').is_file():pytest.skip('review corpus intentionally omitted from tool-only distributions')
    assert checker['check_corpus'](root)['ok'] is True
    archive=ROOT/'fixtures/freeware-games.zip'
    assert archive.is_file(), 'rebuild the maintained freeware companion archive'
    assert checker['check_archive'](root,archive)['ok'] is True
