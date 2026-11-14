"""Authored object-mode conformance; these fixtures contain no original bytes."""
import hashlib
import json
import struct
import os
from pathlib import Path
import subprocess
from dataclasses import replace

import pytest

from fdisbull.le import load_le
from fdisbull.project import Project, LE_MODE_SCHEMA
from test_le_loader import le_file
from test_le_mixed_loader import bound_le
from test_le_workflow import command


BASE = 0x61230  # Deliberately neither 64KiB aligned nor its own local offset.


def program(bridge=b'\xb8\x34\x12\xc3', *, code=b'\xb8\x78\x56\x34\x12\xc3',
            base=BASE, adjacent=False):
    first_size = len(code) if adjacent else len(code) + 16
    return le_file(code=code, data=bridge, fixups=[b'', b''],
                   object_sizes=(first_size, len(bridge)),
                   object_bases=(0x10000, 0x10000 + first_size if adjacent else base),
                   object_flags=(0x2045, 0x45))


def create(tmp_path, data, **options):
    source = tmp_path / 'authored.exe'
    source.write_bytes(data)
    return source, Project.create(tmp_path / 'mixed.fdb', source, **options)


def test_normal_import_analyze_restart_and_patch_keep_each_object_mode(tmp_path):
    bridge = b'\xb8\x34\x12\x8b\x1e\x34\x12\x83\xc0\x01' + b'\x90' * 14 + b'\xc3'
    assert len(bridge) == 25
    original = bound_le(program(bridge))
    source, project = create(tmp_path, original)
    with project:
        assert project.bits == 32 and project.context == 'x86:32:little'
        result = project.analyze(max_instructions=100)
        assert result['stable'] and result['decoded'] == 20
        rows = project.disassembly(lines=100)['instructions']
        wide, narrow = [r for r in rows if int(r['address'],16) < BASE], [r for r in rows if int(r['address'],16) >= BASE]
        assert [r['size'] for r in wide] == [5, 1]
        assert sum(r['size'] for r in narrow) == 25
        assert {r['decoder_bits'] for r in wide} == {32}
        assert {r['decoder_context'] for r in narrow} == {'x86:16:little'}
        assert narrow[0]['operands'] == 'ax,1234h'
        assert narrow[1]['size'] == 4 and 'bx' in narrow[1]['operands']
        assert project.decode_bits(BASE, 1) == 16
        assert project.source_info(1)['identity']['sha256'] == hashlib.sha256(original).hexdigest()
        child = project.patch(BASE + 1, '7856')['version']
        assert project.analyze(version=child,max_instructions=100)['stable']
        assert project.disassembly(version=1,lines=100)['instructions'] == rows
        patched = project.disassembly(BASE,version=child)['instructions'][0]
        assert patched['bytes'] == 'b87856' and patched['decoder_bits'] == 16
        assert project.decode_regions(1) == project.decode_regions(child)
        assert all(bytes(r[0]) == original for r in project.db.execute('SELECT source_bytes FROM binary_info'))
        path = project.path
    assert source.read_bytes() == original
    source.unlink()
    with Project(path) as reopened:
        assert reopened.decode_bits(BASE,child) == 16
        assert reopened.disassembly(BASE,version=child)['instructions'][0]['bytes'] == 'b87856'
        assert reopened.analyze(version=child,max_instructions=100)['stable']
        assert reopened.refresh_facts(child)['instructions_indexed'] == 20
        assert reopened.function_patterns(version=child)['items'] is not None
    fresh = command('disasm',path,'--address',hex(BASE),'--version',child)
    assert fresh['instructions'][0]['bytes'] == 'b87856'
    assert fresh['instructions'][0]['decoder_context'] == 'x86:16:little'


def test_16bit_near_branch_is_object_local_even_with_unaligned_preferred_base(tmp_path):
    source, project = create(tmp_path, program(b'\xeb\x02\x90\x90\xb8\x34\x12\xc3'))
    with project:
        assert project.analyze(max_instructions=50)['stable']
        jump = project.disassembly(BASE)['instructions'][0]
        assert jump['target'] == hex(BASE + 4) and jump['flow'] == 'jump'
        refs = project.xrefs(BASE + 4, 'to')
        assert any(r['source'] == hex(BASE) and r['kind'] == 'branch' for r in refs)
        assert not project.db.execute('SELECT 1 FROM instructions WHERE address=?',(f'{4:016x}',)).fetchone()


def test_near_transfer_does_not_invent_a_code_selector_mode_change(tmp_path):
    displacement = BASE - (0x10000 + 5)
    source, project = create(tmp_path, program(code=b'\xe8' + struct.pack('<i',displacement) + b'\xc3'))
    with project:
        assert project.analyze(max_instructions=50)['stable']
        call = project.disassembly()['instructions'][0]
        assert call['flow'] == 'indirect_call' and call['target'] is None
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE source=? AND target=? AND kind='call'",(f'{0x10000:016x}',f'{BASE:016x}')).fetchone()
        assert project.db.execute('SELECT detail FROM work WHERE address=?',(f'{0x10000:016x}',)).fetchone()[0].startswith('LE near transfer')


def test_far_selector_stays_symbolic_and_no_fallthrough_crosses_adjacent_object(tmp_path):
    source, project = create(tmp_path, program(b'\x9a\x34\x12\xef\xbe\xc3', code=b'\x90', adjacent=True))
    with project:
        assert project.analyze(max_instructions=50)['stable']
        bridge = 0x10001
        rows = project.disassembly(bridge)['instructions']
        assert rows[0]['flow'] == 'indirect_call' and rows[0]['target'] is None and rows[0]['size'] == 5
        assert rows[1]['mnemonic'] == 'ret'
        for phase in (0,1):
            if phase: project.refresh_facts()
            assert not project.db.execute("SELECT 1 FROM xrefs WHERE source=? AND target=?",(f'{0x10000:016x}',f'{bridge:016x}')).fetchone()
            assert not project.db.execute('SELECT 1 FROM xrefs WHERE target=?',(f'{0xbeef0+0x1234:016x}',)).fetchone()


def test_same_mode_direct_cross_object_relative_call_uses_declared_preferred_keys(tmp_path):
    base = 0x60000
    code = b'\xe8' + struct.pack('<i',base-(0x10000+5)) + b'\xc3'
    original = le_file(code=code,data=b'\xc3',fixups=[b'',b''],object_bases=(0x10000,base),object_flags=(0x2045,0x2045))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(max_instructions=50)['stable']
        call = project.disassembly()['instructions'][0]
        assert call['target'] == hex(base) and call['flow'] == 'call'
        target = project.disassembly(base)['instructions'][0]
        assert target['mnemonic'] == 'ret' and target['decoder_bits'] == 32


def test_selected_16bit_entry_does_not_make_32bit_object_decode_as16(tmp_path):
    source, project = create(tmp_path,program(),entry=BASE)
    with project:
        assert project.bits == 16
        assert project.analyze(start=0x10000,max_instructions=50)['stable']
        assert project.disassembly(0x10000)['instructions'][0]['size'] == 5
        assert project.disassembly(0x10000)['instructions'][0]['decoder_bits'] == 32


def test_object_mode_schema_is_durable_but_ordinary_and_legacy_projects_stay9(tmp_path):
    source, project = create(tmp_path,program())
    with project:
        path = project.path
        assert project.schema == LE_MODE_SCHEMA == 10
        assert project.storage_info()['schema'] == 10
        assert project.source_info()['schema'] == 10
        child = project.patch(BASE+1,'7856')['version']
        assert project.source_info(child)['schema'] == 10
    with Project(path) as reopened:
        assert reopened.schema == 10 and reopened.decode_bits(BASE,child) == 16
    raw = tmp_path/'raw.bin';raw.write_bytes(b'\xc3')
    with Project.create(tmp_path/'raw.fdb',raw,arch='x86',bits=32,base=0x1000) as ordinary:
        assert ordinary.schema == ordinary.storage_info()['schema'] == 9
    uniform = load_le(le_file())
    metadata = dict(uniform.metadata);metadata.pop('decode_regions')
    legacy = tmp_path/'legacy-uniform.fdb'
    with Project._create_image(legacy,'authored.exe',replace(uniform,metadata=metadata)) as old:
        assert old.schema == 9 and old.analyze()['stable']
    with Project(legacy) as reopened:
        assert reopened.schema == 9 and reopened.decode_regions() == []


def test_schema9_mode_prototype_refuses_without_automatic_relabel_or_writes(tmp_path):
    source, project = create(tmp_path,program())
    with project:
        path = project.path
        project.db.execute("UPDATE metadata SET value='9' WHERE key='schema'")
        project.db.commit()
    before = path.read_bytes()
    with pytest.raises(ValueError,match='guarded project schema10'):
        Project(path)
    assert path.read_bytes() == before


def test_previous_reader_rejects_new_mode_project_without_changing_it(tmp_path):
    previous = os.environ.get('FDISBULL_PREVIOUS_PYTHON')
    if not previous:
        pytest.skip('Set FDISBULL_PREVIOUS_PYTHON for previous-reader compatibility qualification')
    old_python = Path(previous)
    assert old_python.is_file(), 'Configured previous-reader Python is unavailable'
    source, project = create(tmp_path,program())
    with project:
        path = project.path
        assert project.analyze()['stable']
    before = path.read_bytes()
    environment = dict(os.environ)
    environment.pop('PYTHONPATH',None)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    script = '''import json,sys,fdisbull
from fdisbull.project import Project
try:
    with Project(sys.argv[1]):
        pass
except ValueError as error:
    print(json.dumps(dict(error=str(error),module=fdisbull.__file__,version=fdisbull.__version__)))
else:
    raise SystemExit("old reader incorrectly admitted object-mode project")
'''
    process = subprocess.run([str(old_python),'-c',script,str(path)],cwd=tmp_path,env=environment,
                             capture_output=True,text=True,timeout=30)
    assert process.returncode == 0,process.stdout+process.stderr
    result = json.loads(process.stdout)
    assert result['error'] == 'unsupported project schema'
    assert result['version'] == '0.34.1'
    assert not Path(result['module']).resolve().is_relative_to(Path(__file__).resolve().parents[1]/'src')
    assert path.read_bytes() == before
    with Project(path) as current:
        assert current.schema == 10 and current.decode_bits(BASE) == 16


def test_decoder_window_cannot_read_an_instruction_from_next_object(tmp_path):
    source, project = create(tmp_path,program(b'\xc3',code=b'\xb8',adjacent=True))
    with project:
        assert project.analyze(max_instructions=50)['stable']
        assert not project.db.execute('SELECT 1 FROM instructions WHERE address=?',(f'{0x10000:016x}',)).fetchone()
        assert project.db.execute('SELECT state FROM work WHERE address=?',(f'{0x10000:016x}',)).fetchone()[0] == 'invalid'


def test_backed_page_after_zero_hole_does_not_use_summed_file_size_as_prefix(tmp_path):
    code = bytes(4096) + b'\xb8\x78\x56\x34\x12\xc3'
    original = le_file(code=code,data=b'\xc3',fixups=[b'',b'',b''],page_flags=[3,0,0],
                       entry_offset=4096,object_flags=(0x2045,0x45))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(start=0x10000,max_instructions=50)['stable']
        rows = project.disassembly(0x11000)['instructions']
        assert rows[0]['bytes'] == 'b878563412' and rows[0]['decoder_bits'] == 32
        assert rows[1]['mnemonic'] == 'ret'
        assert not project.db.execute('SELECT 1 FROM instructions WHERE address=?',(f'{0x10000:016x}',)).fetchone()


def test_instruction_cannot_consume_zero_fill_after_backed_page_end(tmp_path):
    code = b'\x90' * 4095 + b'\xb8' + bytes(4096)
    original = le_file(code=code,data=b'\xc3',fixups=[b'',b'',b''],page_flags=[0,3,0],
                       entry_offset=4095,object_flags=(0x2045,0x45))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(max_instructions=50)['stable']
        assert not project.db.execute('SELECT 1 FROM instructions WHERE address=?',(f'{0x10fff:016x}',)).fetchone()
        assert project.db.execute('SELECT state FROM work WHERE address=?',(f'{0x10fff:016x}',)).fetchone()[0] == 'invalid'


def test_16bit_cs_memory_expression_keeps_selector_binding_unknown(tmp_path):
    source, project = create(tmp_path,program(b'\x2e\xa0\x02\x00\xc3'))
    with project:
        assert project.analyze(max_instructions=50)['stable']
        facts = [json.loads(row[0]) for row in project.db.execute('SELECT detail FROM memory_refs WHERE source=?',(f'{BASE:016x}',))]
        assert len(facts) == 1 and facts[0]['width'] == 1
        assert facts[0]['decoder_bits'] == 16 and facts[0]['interval_exact'] is False
        assert facts[0]['concrete_target'] is None
        assert any('LE runtime selector' in reason for reason in facts[0]['unresolved_reasons'])
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE source=? AND kind='data'",(f'{BASE:016x}',)).fetchone()


def test_symbolic_unapplied_memory_operand_survives_disasm_cfg_facts_and_reopen(tmp_path):
    record = struct.pack('<BBhBH',5,0,2,2,2)
    original = le_file(code=b'\xc3',data=b'\x2e\xa0\x02\x00\xc3',fixups=[b'',record],
                       object_bases=(0x10000,BASE),object_flags=(0x2045,0x45))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(max_instructions=50)['stable']
        path = project.path
        for version in [1,project.patch(BASE+2,'3412')['version']]:
            assert project.analyze(version=version,max_instructions=50)['stable']
            row = project.disassembly(BASE,version=version)['instructions'][0]
            assert row['operand_status'] == 'symbolic_unapplied_fixup'
            assert row['le_fixups'][0]['applied'] is False
            assert row['le_fixups'][0]['target_address'] == BASE+2
            graph = project.cfg(BASE,version=version)
            assert graph['nodes'][0]['operand_status'] == 'symbolic_unapplied_fixup'
            assert graph['interpretation_complete'] is False
            assert any(r['kind'] == 'operand' for r in graph['unresolved'])
            for persisted in [True,False]:
                if not persisted:
                    project.db.execute('DELETE FROM analysis_facts_revision WHERE version=?',(version,))
                report = project.memory_accesses(BASE+2,version=version,include_unresolved=True)
                assert report['address_matches'] == 0
                facts = [r for r in report['items'] if r['source'] == hex(BASE)]
                assert facts and facts[0]['operand_status'] == 'symbolic_unapplied_fixup'
                assert facts[0]['le_fixups'][0]['applied'] is False
            project.refresh_facts(version)
    with Project(path) as reopened:
        row = reopened.disassembly(BASE,version=1)['instructions'][0]
        assert row['bytes'] == '2ea00200' and row['operand_status'] == 'symbolic_unapplied_fixup'
    assert source.read_bytes() == original


def test_symbolic_unapplied_branch_operand_cannot_publish_encoded_target(tmp_path):
    record = struct.pack('<BBhBH',5,0,1,2,4)
    original = le_file(code=b'\xc3',data=b'\xe9\x01\x00\x90\xc3',fixups=[b'',record],
                       object_bases=(0x10000,BASE),object_flags=(0x2045,0x45))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(max_instructions=50)['stable']
        row = project.disassembly(BASE)['instructions'][0]
        assert row['operand_status'] == 'symbolic_unapplied_fixup'
        assert row['flow'] == 'indirect_jump' and row['target'] is None
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE source=? AND kind IN ('branch','resolved_branch')",(f'{BASE:016x}',)).fetchone()
        assert project.cfg(BASE)['graph_closed'] is False


def test_symbolic_unapplied_fixup_over_opcode_does_not_decode_source_as_instruction(tmp_path):
    record = struct.pack('<BBhBH',5,0,0,2,2)
    original = le_file(code=b'\xc3',data=b'\xb8\x02\x00\xc3',fixups=[b'',record],
                       object_bases=(0x10000,BASE),object_flags=(0x2045,0x45))
    source, project = create(tmp_path,original)
    with project:
        assert project.analyze(max_instructions=50)['stable']
        assert not project.db.execute('SELECT 1 FROM instructions WHERE address=?',(f'{BASE:016x}',)).fetchone()
        detail = project.db.execute('SELECT detail FROM work WHERE address=?',(f'{BASE:016x}',)).fetchone()[0]
        assert 'symbolic LE fixup overlaps instruction structure' in detail


@pytest.mark.parametrize('change', ['bool','missing','overlap','wrong_index','unknown_index','wrong_bits'])
def test_invalid_object_mode_metadata_refuses_before_project_creation(tmp_path,change):
    image = load_le(program())
    metadata = json.loads(json.dumps(image.metadata))
    if change == 'bool':metadata['decode_regions'][1]['bits'] = True
    if change == 'missing':metadata['decode_regions'].pop()
    if change == 'overlap':metadata['decode_regions'][1]['start'] -= 1
    if change == 'wrong_index':metadata['decode_regions'][1]['object_index'] = 1
    if change == 'unknown_index':metadata['decode_regions'][1]['object_index'] = 99
    if change == 'wrong_bits':metadata['decode_regions'][1]['bits'] = 32
    path = tmp_path/'invalid.fdb'
    with pytest.raises(ValueError,match='decode region'):
        Project._create_image(path,'authored.exe',replace(image,metadata=metadata))
    assert not path.exists()
