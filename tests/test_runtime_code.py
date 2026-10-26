"""Observed code becomes a new interpretation, never replacement history."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.fixture
def backend():
    path=os.environ.get('FDISBULL_DOSBOX')
    if not path:
        pytest.skip('Set FDISBULL_DOSBOX to the native layers backend')
    return str(Path(path).resolve(strict=True))


def test_known_loader_words_normalize_without_fabricating_modified_pointers(tmp_path):
    binary=tmp_path/'FIXUP.EXE';binary.write_bytes(mz_file(bytes.fromhex('b80000c3')+bytes(28),relocations=[(1,0)]))
    with Project.create(tmp_path/'fixup.fdb',binary) as p:
        data,proof=p._runtime_normalize(1,0x10000,bytes.fromhex('b82408c3'),-0x7dc0)
        assert data==bytes.fromhex('b80010c3') and proof[0]['address']=='0x10001'
        with pytest.raises(ValueError,match='cuts through'):
            p._runtime_normalize(1,0x10002,b'\x08',-0x7dc0)
        with pytest.raises(ValueError,match='Modified runtime relocation'):
            p._runtime_normalize(1,0x10000,bytes.fromhex('b89909c3'),-0x7dc0)


def test_explicit_flat_analysis_seed_is_attempted_within_its_budget(tmp_path):
    binary=tmp_path/'seed.raw';binary.write_bytes(b'\xeb\xfe'+bytes(30)+b'\xc3')
    with Project.create(tmp_path/'seed.fdb',binary,arch='x86',bits=64,base=0x1000) as p:
        result=p.analyze(start=0x1020,max_instructions=1)
        assert p.disassembly(0x1020,lines=1)['instructions'][0]['bytes']=='c3'
        assert result['stable'] is False


def test_native_capture_normalizes_fixups_and_rejects_partial_or_corrupt_observations(tmp_path,backend):
    binary=tmp_path/'RELOC.EXE';binary.write_bytes(mz_file(bytes.fromhex('b80000ebfe')+bytes(507),relocations=[(1,0)],ss=0,sp=0x200))
    with Project.create(tmp_path/'reloc.fdb',binary) as p:
        with p.debugger(backend,binary.parent) as d:
            full=d.capture_code('1000:0000',length=5)
            partial=d.capture_code('1000:0002',length=1)
        promoted=p.debug_promote_code(full['artifact'],max_instructions=1)
        v=promoted['version']
        assert promoted['analysis']['stable'] is False
        assert p.disassembly('1000:0000',version=v,lines=1)['instructions'][0]['bytes']=='b80010'
        assert p.runtime_version_info(v)['relocations'][0]['project_hex']=='0010'
        before=len(p.versions())
        with pytest.raises(ValueError,match='cuts through'):
            p.debug_promote_code(partial['artifact'])
        assert len(p.versions())==before
        with p.transaction(True):p.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'corrupt',full['artifact']))
        with pytest.raises(ValueError,match='snapshot hash mismatch'):
            p.debug_promote_code(full['artifact'])
        assert len(p.versions())==before


def test_native_capture_promotes_offline_with_new_edges_and_preserved_parent(tmp_path,backend):
    binary=tmp_path/'VERSION.EXE'
    code=bytes.fromhex('0e1fb8010083f8017405b81111eb03b82222ebfe')
    binary.write_bytes(mz_file(code+bytes(512-len(code)),ss=0,sp=0x200))
    original=hashlib.sha256(binary.read_bytes()).hexdigest();database=tmp_path/'versions.fdb'
    with Project.create(database,binary) as p:
        p.analyze(max_instructions=64)
        p.annotate('1000:000f','original_arm',kind='name',author='analyst')
        with p.debugger(backend,binary.parent) as d:
            bp=d.breakpoint('1000:0008')
            assert d.run(timeout_ms=3000)['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id'])
            ram=d.capture_code('1000:0008',length=12,view='ram')
            d.layer_patch('redirect arm','1000:0008',expected_hex='7405',data_hex='eb00',kind='execute')
            executed=d.capture_code('1000:0008',length=12)
            assert d.memory('1000:0008',length=2)['hex']=='7405'
            trace=d.trace('redirect.json',count=3,timeout_ms=3000)
    with Project(database) as p:
        first=p.debug_promote_code(ram['artifact'],label='observed RAM',max_instructions=64)
        changed=p.debug_promote_code(executed['artifact'],label='observed fetch overlay',max_instructions=64)
        v=changed['version']
        assert first['version']!=v and changed['parent']==1
        assert p.debug_promote_code(executed['artifact'])['version']==v
        assert len(p.versions())==3
        view=p.debug_trace_view(trace['artifact'],version=v)
        assert view['events'][0]['bytes_match'] and view['events'][0]['analysis_match']
        assert view['events'][0]['identity']['context']=='real:1000'
        assert view['events'][-1]['observation']['instruction_completed'] is False
        assert p.disassembly('1000:0008',cs=0x1000,version=1,lines=1)['instructions'][0]['bytes']=='7405'
        row=p.disassembly('1000:0008',cs=0x1000,version=v,lines=1)['instructions'][0]
        assert row['bytes']=='eb00' and row['byte_provenance']['kind']=='runtime-capture'
        refs=p.xrefs('1000:0008',direction='from',version=v,cs=0x1000)
        assert any(r['target']=='0x1000a' and r['kind']=='branch' for r in refs)
        assert not any(r['target']=='0x1000f' and r['kind']=='branch' for r in refs)
        cfg=p.cfg('1000:0008',version=v,cs=0x1000)
        assert '0x1000a' in {n['address'] for n in cfg['nodes']}
        assert '0x1000f' not in {n['address'] for n in cfg['nodes']}
        assert cfg['temporal']['artifact']==executed['artifact']
        child=p.patch('1000:000a','b8cdab',version=v)['version']
        p.analyze(start='1000:0008',version=child,max_instructions=64)
        assert p.disassembly('1000:000a',version=child,cs=0x1000,lines=1)['instructions'][0]['byte_provenance']['kind']=='authored-edit'
        assert p.runtime_version_info(v)['artifact']==executed['artifact']
        assert p.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(v,)).fetchone()[0] is None
    with Project(database) as p:
        from fdisbull.render import render_snapshot
        from fdisbull.cfg_render import render_cfg
        render_snapshot(p.disassembly('1000:0008',version=v,cs=0x1000,lines=6),tmp_path/'temporal.png')
        render_cfg(p.cfg('1000:0008',version=v,cs=0x1000),tmp_path/'temporal.svg')
        assert (tmp_path/'temporal.png').read_bytes().startswith(b'\x89PNG')
        assert 'runtime-capture' in (tmp_path/'temporal.svg').read_text()
        p.debug_export(executed['artifact'],tmp_path/'raw-capture.json')
        assert json.loads((tmp_path/'raw-capture.json').read_text())['hex'].startswith('eb00')
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==original
