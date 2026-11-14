"""Native backing blocks retain each object's decoder width and source version."""
from copy import deepcopy
import pytest
from fdisbull.project import Project
from fdisbull.code_backings import digest, validate_source
from test_le_mixed_loader import mixed_le, bound_le


def test_bridge_backings_keep_16bit_encodings_and_reject_relabeling(tmp_path):
    source=tmp_path/'original.exe'; source.write_bytes(bound_le(mixed_le()))
    with Project.create(tmp_path/'mixed.fdb', source) as project:
        project.analyze(max_instructions=100)
        capsule=project.code_backings([0x60000])
        assert capsule['blocks']
        assert {b['bits'] for b in capsule['blocks']} == {16}
        assert not capsule['complete']
        assert any(p['kind']=='unresolved_relocation' for p in capsule['unresolved'])
        affected=next(b for b in capsule['blocks'] if b['bytes'].startswith('b8'))
        assert affected['effects']['status']=='unresolved_native_relocation'
        assert affected['provenance']['le_fixups'][0]['applied'] is False
        assert capsule['blocks'][0]['provenance']['decoder_context'] == 'x86:16:little'
        assert validate_source(project,capsule)['status'] == 'source_valid'
        tampered=deepcopy(capsule)
        block=next(b for b in tampered['blocks'] if b['bytes']=='c3')
        block['bits']=32
        block['backing_revision']=digest({k:v for k,v in block.items() if k!='backing_revision'})
        tampered['sha256']=digest({k:v for k,v in tampered.items() if k!='sha256'})
        with pytest.raises(ValueError,match='decoder width'):validate_source(project,tampered)


def test_fixed_width_advanced_abi_analysis_refuses_before_publishing_effects(tmp_path):
    source=tmp_path/'original.exe'; source.write_bytes(mixed_le())
    with Project.create(tmp_path/'mixed.fdb', source) as project:
        with pytest.raises(ValueError,match='uniform-width'):
            project.auto_analyze(max_instructions=10)
        assert project.db.execute("SELECT count(*) FROM metadata WHERE key LIKE 'advanced_enabled_%'").fetchone()[0] == 0
        assert project.analyze(max_instructions=100)['attempted'] > 0


def test_uniform32_symbolic_operand_cannot_enter_concrete_derived_semantics(tmp_path):
    import struct
    from test_le_loader import le_file
    record=struct.pack('<BBhBH',5,0,2,1,0)
    source=tmp_path/'symbolic32.exe'
    source.write_bytes(le_file(code=b'\x66\xb8\0\0\xc3',fixups=[record,b'']))
    with Project.create(tmp_path/'symbolic32.fdb',source) as project:
        assert {r['bits'] for r in project.decode_regions(1)}=={32}
        with pytest.raises(ValueError,match='resolved LE operand relocations'):
            project.auto_analyze(max_instructions=10)
        assert project.db.execute("SELECT count(*) FROM metadata WHERE key LIKE 'advanced_enabled_%'").fetchone()[0]==0
        assert project.analyze(max_instructions=50)['decoded']>0
