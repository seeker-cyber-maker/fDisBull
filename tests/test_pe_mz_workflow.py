"""Public dual-image workflow preserves the chosen entry, source and versions."""
import json
import struct
import subprocess
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.inspection import inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project
from test_image_views import dual_pe_mz
from fixtures_formats import pe64


def test_public_dual_image_imports_analyze_independently_and_restart(tmp_path):
    source=tmp_path/'dual.exe';source.write_bytes(dual_pe_mz())
    paths={}
    for selector,expected_format,expected_bits,entry in [('pe','PE',64,0x140001000),('mz','MZ',16,0x10000)]:
        path=tmp_path/(selector+'.fdb');paths[selector]=path
        created=respond(dict(method='import',params=dict(path=str(source),project=str(path),image=selector)))
        assert created['ok'],created
        with Project(path) as project:
            assert project.meta['format']==expected_format and project.bits==expected_bits
            assert project.meta['entry']==entry
            assert project.analyze()['stable']
            rows=project.disassembly()['instructions']
            assert rows[0]['address']==hex(entry)
            assert rows[0]['bytes']==('e80b000000' if selector=='pe' else 'b80110')
            assert project.meta['loader_metadata']['selected_image']==selector
            assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])==dual_pe_mz()
            header=project.information('header')['header']
            assert header['format']==('PE32+' if selector=='pe' else 'DOS MZ')
            assert header['bits']==expected_bits
    source.unlink()
    for selector,path in paths.items():
        with Project(path) as project:
            assert project.disassembly()['instructions']
            assert project.information('header')['header']['bits']==(64 if selector=='pe' else 16)
        svg=tmp_path/(selector+'.svg')
        rendered=respond(dict(method='render',params=dict(project=str(path),output=str(svg))))
        assert rendered['ok'] and svg.read_text().lstrip().startswith('<svg'),rendered


def test_dual_image_inspection_defaults_to_pe_but_explicit_mz_has_no_pe_exports():
    data=dual_pe_mz()
    native=inspect_binary(data)
    dos=inspect_binary(data,image='mz')
    assert native['selected_image']=='pe' and native['exports'][0]['name']=='helper'
    assert dos['selected_image']=='mz' and dos['header']['bits']==16
    assert dos['container_header']['format']=='PE32+'
    assert dos['imports']==dos['exports']==[]
    assert dos['sections'][0]['file_offset']==0x40 and dos['sections'][0]['file_size']==0x40
    assert [v['image'] for v in native['image_views']]==['mz','pe']
    assert [v['image'] for v in dos['image_views']]==['mz','pe']


def test_mz_selected_patch_reconstructs_only_stub_and_reapplies_relocation(tmp_path):
    source=tmp_path/'dual.exe';original=dual_pe_mz();source.write_bytes(original)
    path=tmp_path/'stub.fdb'
    with Project.create(path,source,image='mz') as project:
        project.analyze()
        parent=project.disassembly()['instructions']
        child=project.patch('1000:0001','0210')['version']
        assert project.regions(child)[0].data[1:3]==bytes.fromhex('0210')
        retained=bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(child,)).fetchone()[0])
        assert len(retained)==len(original)
        assert retained[0x80:]==original[0x80:]
        assert retained[:0x40]==original[:0x40]
        assert retained[0x41:0x43]==bytes.fromhex('0200')
        assert project.disassembly(version=1)['instructions']==parent
        assert project.analyze(version=child)['stable']
        assert project.disassembly(version=child)['instructions'][0]['bytes']=='b80210'
        assert project.information('header',version=child)['header']['format']=='DOS MZ'
        assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])==original
    source.unlink()
    with Project(path) as project:
        assert project.disassembly()['instructions'][0]['bytes']=='b80210'
        assert project.disassembly(version=1)['instructions'][0]['bytes']=='b80110'
        assert project._dos_metadata(child)['secondary_format']=='PE'


def test_invalid_dos_stub_does_not_block_default_or_explicit_pe(tmp_path):
    source=tmp_path/'pe-only.exe';source.write_bytes(pe64())
    for selector in (None,'pe'):
        loaded=load_image(source,image=selector)
        assert loaded.format=='PE' and loaded.bits==64
    with pytest.raises(ValueError,match='page count'):
        load_image(source,image='mz')
    rejected=respond(dict(method='import',params=dict(path=str(source),project=str(tmp_path/'bad.fdb'),image='mz')))
    assert not rejected['ok'] and not (tmp_path/'bad.fdb').exists()


def test_cli_mz_selection_and_conflicts_are_explicit(tmp_path):
    source=tmp_path/'dual.exe';source.write_bytes(dual_pe_mz())
    project=tmp_path/'stub.fdb'
    imported=subprocess.run([sys.executable,'-m','fdisbull','import',str(source),str(project),'--image','mz'],capture_output=True,text=True)
    assert imported.returncode==0 and json.loads(imported.stdout)['ok'],imported.stderr+imported.stdout
    for extra in [dict(arch='x86'),dict(slice_arch='arm64')]:
        result=respond(dict(method='import',params=dict(path=str(source),project=str(tmp_path/'conflict.fdb'),image='mz',**extra)))
        assert not result['ok'] and not (tmp_path/'conflict.fdb').exists()
