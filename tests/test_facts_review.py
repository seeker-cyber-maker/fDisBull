"""Index completeness must survive old-project seeds and DOS state resets."""
from fdisbull.project import Project
from fdisbull.memory import instruction_memory_accesses
from test_dos_loader import mz_file
import pytest


def _dos_writer(tmp_path):
    module=bytearray(128)
    # mov ax,relocated1004; mov ds,ax; mov [0],ax; ret
    module[:9]=bytes.fromhex('b804008ed8a30000c3')
    module[16]=0xc3
    binary=tmp_path/'writer.exe'
    binary.write_bytes(mz_file(bytes(module),relocations=[(1,0)]))
    return Project.create(tmp_path/'writer.fdb',binary)


def test_new_dos_cs_does_not_certify_incomplete_migrated_memory_index(tmp_path):
    with _dos_writer(tmp_path) as p:
        assert p.analyze()['stable']
        parent_bytes=p.regions(1)[0].data
        p.annotate('1000:0005','original_writer',kind='name')
        with p.transaction(True):
            p.db.execute('DROP TABLE memory_refs')
            p.db.execute('DROP TABLE analysis_facts_revision')
            p.db.execute("UPDATE metadata SET value='3' WHERE key='schema'")
        path=p.path
    with Project(path) as p:
        before=p.memory_accesses('1004:0000',access='write',include_unresolved=False)
        assert before['facts_source']=='decoded_stored_instructions'
        assert before['address_matches']==1
        assert p.analyze(start='1001:0000')['stable']
        # Merely indexing a new alias/callee does not backfill old instructions.
        changes=p.db.total_changes
        after=p.memory_accesses('1004:0000',access='write',include_unresolved=False)
        assert p.db.total_changes==changes
        assert after['facts_source']=='decoded_stored_instructions'
        assert after['address_matches']==1
        assert after['items'][0]['source']=='0x10005'
        assert p.regions(1)[0].data==parent_bytes
        assert p.disassembly('1000:0005',lines=1)['instructions'][0]['name']=='original_writer'
        p.refresh_facts()
        refreshed=p.memory_accesses('1004:0000',access='write',include_unresolved=False)
        assert refreshed['facts_source']=='persisted'
        assert refreshed['address_matches']==1


def test_dos_representation_reset_certifies_empty_then_rebuilt_memory_index(tmp_path):
    with _dos_writer(tmp_path) as p:
        assert p.analyze()['stable']
        original=p.regions(1)[0].data
        assert p.memory_accesses('1004:0000',access='write',include_unresolved=False)['address_matches']==1
        result=p.represent('1000:0005','byte',defer=True)
        assert result['analysis'] is None
        assert p.analysis_status()['stable'] is False
        empty=p.memory_accesses('1004:0000',access='write',include_unresolved=False)
        assert empty['facts_source']=='persisted'
        assert empty['address_matches']==0
        assert p.analyze()['stable']
        assert p.memory_accesses('1004:0000',access='write',include_unresolved=False)['address_matches']==0
        p.represent('1000:0005','code',defer=True)
        assert p.analyze()['stable']
        restored=p.memory_accesses('1004:0000',access='write')
        assert restored['facts_source']=='persisted'
        # The explicit code seed may conservatively join an unknown DS state.
        assert any(item['source']=='0x10005' and item['may_write'] for item in restored['items'])
        p.analyze(start='1000:0005',ds=0x1004)
        resolved=p.memory_accesses('1004:0000',access='write',include_unresolved=False)
        assert resolved['facts_source']=='persisted'
        assert resolved['address_matches']==1
        assert p.regions(1)[0].data==original


@pytest.mark.parametrize(('raw','registers','explicit_access','explicit_target','stack_access','stack_target'),[
    ('ff1500000000',{'rsp':0x8000},'read',0x1006,'write',0x7ff8),
    ('ff30',{'rax':0x4000,'rsp':0x8000},'read',0x4000,'write',0x7ff8),
    ('8f0424',{'rsp':0x8000},'write',0x8008,'read',0x8000),
    ('ff7424f8',{'rsp':0x8000},'read',0x7ff8,'write',0x7ff8),
])
def test_explicit_stack_address_operands_remain_distinct_from_implicit_stack_effects(
    raw,registers,explicit_access,explicit_target,stack_access,stack_target,
):
    facts=instruction_memory_accesses(bytes.fromhex(raw),0x1000,'x86',64,registers=registers)
    assert len(facts)==2
    explicit=next(f for f in facts if f['access']==explicit_access)
    implicit=next(f for f in facts if f['access']==stack_access)
    assert explicit['implicit'] is False and explicit['operand_index']==0
    assert explicit['concrete_target']==explicit_target
    assert implicit['implicit'] is True and implicit['operand_index'] is None
    assert implicit['concrete_target']==stack_target
    assert implicit['base_register']=='rsp'
    assert implicit['displacement']==(-8 if stack_access=='write' else 0)
    assert explicit['width']==implicit['width']==8
