"""Acceptance checks for recursive discovery and shared address identity."""
import json
import sqlite3
import struct
from pathlib import Path

import pytest
from fdisbull.project import Project
from fdisbull.cli import respond
from test_inspection import pe_import_fixture


def raw_image():
    data=bytearray(0x60)
    data[:0x15]=bytes.fromhex('488d3d19000000488d352a000000ff151c000000c3')
    data[0x20:0x2a]=b'Dinosaurs\0'
    struct.pack_into('<Q',data,0x30,0x1040)
    struct.pack_into('<Q',data,0x38,0x1050)
    data[0x40:0x46]=bytes.fromhex('b82a000000c3')
    data[0x50:0x56]=bytes.fromhex('b863000000c3')
    return bytes(data)

@pytest.fixture
def discovered(tmp_path):
    binary=tmp_path/'references.bin'
    binary.write_bytes(raw_image())
    with Project.create(tmp_path/'analysis.fdb',binary,arch='x86',base=0x1000) as p:
        yield p


def test_entry_sweep_then_referenced_memory_and_corroborated_indirect_call(discovered):
    first=discovered.analyze(max_instructions=1)
    assert first['decoded']==1 and not first['stable']
    assert discovered.items()==[]
    result=discovered.analyze()
    assert result['stable'] and result['pending']==0
    rows=discovered.disassembly()['instructions']
    addresses={r['address'] for r in rows}
    assert '0x1040' in addresses
    assert '0x1050' not in addresses
    items={r['address']:r for r in discovered.items()}
    assert items['0x1020']['representation']=='ascii'
    assert items['0x1038']['representation']=='pointer_candidate'
    assert items['0x1038']['value']['target']=='0x1050'
    assert any(r['kind']=='resolved_call' for r in discovered.xrefs('0x1040'))
    again=discovered.analyze()
    assert again['stable'] and again['new_facts']==again['decoded']==again['attempted']==0


def test_budget_resume_never_claims_stable_before_all_rules_exhausted(discovered):
    for _ in range(40):
        r=discovered.analyze(max_instructions=1)
        if r['stable']:
            break
        assert r['pending']>0 and r['budget_exhausted']
    else:
        pytest.fail('queue did not converge')
    assert discovered.analyze()['new_facts']==0


def test_target_rename_propagates_without_rewriting_instruction_rows(discovered,tmp_path):
    discovered.analyze()
    before=[tuple(r) for r in discovered.db.execute('SELECT * FROM instructions ORDER BY address')]
    discovered.annotate('0x1020','park_name',kind='name',author='TiGa')
    rows=discovered.disassembly()['instructions']
    first=next(r for r in rows if r['address']=='0x1000')
    assert first['references'][0]['name']=='park_name'
    assert 'park_name' in first['display_operands']
    assert [tuple(r) for r in discovered.db.execute('SELECT * FROM instructions ORDER BY address')]==before
    with Project(discovered.path) as reopened:
        assert reopened.xrefs('0x1020')[0]['target_name']=='park_name'
        output=tmp_path/'listing.svg'
        r=respond({'method':'render','params':{'project':str(reopened.path),'output':str(output)}})
        assert r['ok'] and 'park_name' in output.read_text()


def test_representing_pointer_as_number_retracts_derived_call_then_restores(discovered):
    discovered.analyze()
    assert discovered.disassembly('0x1040')['instructions']
    result=discovered.represent('0x1030','qword')
    assert result['analysis']['stable']
    assert '0x1040' not in {r['address'] for r in discovered.disassembly()['instructions']}
    assert not any(r['kind']=='resolved_call' for r in discovered.xrefs('0x1040'))
    source=next(r for r in discovered.disassembly()['instructions'] if r['address']=='0x100e')
    assert source['references'][0]['representation']=='qword'
    assert '<qword>' in source['display_operands']
    restored=discovered.represent('0x1030','pointer')
    assert restored['analysis']['stable']
    assert '0x1040' in {r['address'] for r in discovered.disassembly()['instructions']}


def test_patch_recomputes_child_pointer_graph_parent_unchanged(discovered):
    discovered.analyze()
    discovered.patch('0x1030',struct.pack('<Q',0x1050).hex())
    result=discovered.analyze()
    assert result['stable']
    child={r['address'] for r in discovered.disassembly()['instructions']}
    parent={r['address'] for r in discovered.disassembly(version=1)['instructions']}
    assert '0x1050' in child and '0x1040' not in child
    assert '0x1040' in parent and '0x1050' not in parent


def test_pe_metadata_and_entry_before_disconnected_export(tmp_path):
    data=bytearray(pe_import_fixture())
    data[0x200:0x207]=bytes.fromhex('ff15ca010000c3')
    binary=tmp_path/'imports.exe'
    binary.write_bytes(data)
    with Project.create(tmp_path/'pe.fdb',binary) as p:
        assert p.information('header')['header']['format']=='PE32+'
        section=p.information('sections')['items'][0]
        assert section['virtual_address']=='0x140001000' and section['file_offset']==0x200
        first=p.analyze(max_instructions=1)
        assert not first['entry_complete']
        assert [r['address'] for r in p.disassembly()['instructions']]==['0x140001000']
        assert p.analyze()['stable']
        assert '0x140001010' in {r['address'] for r in p.disassembly()['instructions']}
        imported=p.information('imports')['items'][0]
        assert imported['name']=='KERNEL32.dll!Sleep' and imported['original_name']=='Sleep'
        row=p.disassembly()['instructions'][0]
        assert 'KERNEL32.dll!Sleep' in row['display_operands']
        p.annotate('0x1400011d0','sleep_for_ms',kind='name')
        assert p.information('imports')['items'][0]['name']=='sleep_for_ms'
        assert 'sleep_for_ms' in p.disassembly()['instructions'][0]['display_operands']


def test_header_identifier_works_without_project_on_actual_dinopark():
    path=Path(__file__).parents[2]/'dino-check'/'DINOPARK.EXE'
    if not path.exists():
        pytest.skip('external original DinoPark fixture not present')
    r=respond({'method':'identify','params':{'path':str(path)}})
    assert r['ok'] and r['result']['format']=='DOS MZ'
    assert r['result']['valid']


def test_v1_database_upgrade_preserves_original_analysis(discovered):
    discovered.analyze()
    discovered.annotate('0x1020','old_name',kind='name')
    count=discovered.status()['counts']['instructions']
    # Produce an actual prior schema shape, retaining original byte/version tables.
    with discovered.transaction(True):
        for table in ('binary_info','symbols','data_items','definitions','investigations','operand_refs','analysis_state','recoveries'):
            discovered.db.execute(f'DROP TABLE {table}')
        discovered.db.execute("UPDATE metadata SET value='1' WHERE key='schema'")
    with Project(discovered.path) as migrated:
        assert migrated.status()['counts']['instructions']==count
        assert migrated._label(1,0x1020)=='old_name'
        assert 'unavailable' in migrated.information()['warnings'][0]
        assert migrated.analyze()['stable']


def test_offline_recovery_integrates_symbols_and_preserves_aliases(discovered):
    discovered.analyze()
    recovered=discovered.recover_imports(module_exports=[
        {'address':'0x1040','module':'test.dll','name':'A'},
        {'address':'0x1040','module':'test.dll','name':'AliasA'}],candidate_slots=['0x1030'],max_slots=2)
    match=next(e for e in recovered['entries'] if e['address']==0x1030)
    assert match['resolved'] and match['ambiguous'] and len(match['alternatives'])==2
    row=next(r for r in discovered.disassembly()['instructions'] if r['address']=='0x100e')
    assert 'test.dll!A|AliasA' in row['display_operands']
    assert discovered.information('imports')['recovery']['source']['runtime_attachment'] is False


def test_recovery_replaces_previous_catalog_without_stale_symbol(discovered):
    discovered.analyze()
    for name in ('AAA','ZZZ'):
        discovered.recover_imports(module_exports=[{'address':'0x1040','module':'test.dll','name':name}],candidate_slots=['0x1030'],max_slots=1)
    assert discovered._label(1,0x1030)=='test.dll!ZZZ'
    assert 'AAA' not in next(r for r in discovered.disassembly()['instructions'] if r['address']=='0x100e')['display_operands']


def test_v1_migration_backfills_references_and_data_queue(discovered):
    # Emulate v1's decoder-only analysis (no pointer discovery or structured refs).
    discovered.analyze(max_instructions=4)
    with discovered.transaction(True):
        for table in ('binary_info','symbols','data_items','definitions','investigations','operand_refs','analysis_state','recoveries'):
            discovered.db.execute(f'DROP TABLE {table}')
        discovered.db.execute("UPDATE metadata SET value='1' WHERE key='schema'")
    with Project(discovered.path) as migrated:
        assert migrated.analyze()['stable']
        first=migrated.disassembly()['instructions'][0]
        assert first['references'][0]['target']=='0x1020'
        assert '0x1040' in {r['address'] for r in migrated.disassembly()['instructions']}
        assert migrated.items()


def test_string_source_extent_survives_presentation_changes(discovered):
    before=next(s for s in discovered.information('strings')['items'] if s['text']=='Dinosaurs')
    assert before['size']==9
    assert before['representation_size'] is None
    discovered.represent('0x1020','dword')
    after=next(s for s in discovered.information('strings')['items'] if s['text']=='Dinosaurs')
    assert after['size']==9 and after['representation_size']==4


def test_arm64_negative_displacements_are_unsigned_addresses(tmp_path):
    from fdisbull.decoder import decode
    for instruction in ('ffffff17','e0ffff10','e0ffff58'):
        decoded=decode(bytes.fromhex(instruction),0,'arm64',64)
        targets=([decoded['target']] if decoded['target'] is not None else [])+decoded['data_refs']
        assert targets and all(0<=target<2**64 for target in targets)
    binary=tmp_path/'branch.arm64'
    binary.write_bytes(bytes.fromhex('ffffff17'))
    with Project.create(tmp_path/'arm.fdb',binary,arch='arm64') as p:
        assert p.analyze()['stable']
        assert p.disassembly()['instructions'][0]['target']=='0xfffffffffffffffc'


def test_header_and_recovery_addresses_are_hex_at_json_boundary(discovered):
    discovered.analyze()
    r=respond({'method':'recover-imports','params':{'project':str(discovered.path),'module_exports':[{'address':'0x1040','module':'test.dll','name':'A'}],'candidate_slots':['0x1030'],'max_slots':1}})
    assert r['ok']
    assert r['result']['entries'][0]['address']=='0x1030'
    assert r['result']['entries'][0]['target']=='0x1040'


def test_far_indirect_call_keeps_selector_context_unresolved(tmp_path):
    data=bytearray(0x30)
    data[:7]=bytes.fromhex('ff1d0a000000c3')
    struct.pack_into('<Q',data,0x10,0x1020)
    data[0x20]=0xc3
    binary=tmp_path/'far.bin'
    binary.write_bytes(data)
    with Project.create(tmp_path/'far.fdb',binary,arch='x86',base=0x1000) as p:
        assert p.analyze()['stable']
        assert '0x1020' not in {r['address'] for r in p.disassembly()['instructions']}
        assert not any(r['kind']=='resolved_call' for r in p.xrefs('0x1020'))
        assert p.disassembly()['instructions'][0]['references'][0]['width']==6


def test_header_patch_investigation_reads_child_bytes(tmp_path):
    data=bytearray(pe_import_fixture())
    data[0x40:0x4a]=b'OldHeader\0'
    # LEA RIP-relative backwards into mapped PE headers; do not execute.
    displacement=0x140000040-(0x140001000+7)
    data[0x200:0x208]=b'\x48\x8d\x3d'+struct.pack('<i',displacement)+b'\xc3'
    binary=tmp_path/'header.exe'
    binary.write_bytes(data)
    with Project.create(tmp_path/'header.fdb',binary) as p:
        assert p.analyze()['stable']
        assert next(r for r in p.items() if r['address']=='0x140000040')['value']=='OldHeader'
        p.patch('0x140000040',b'NewHeader'.hex())
        assert p.analyze()['stable']
        assert next(r for r in p.items() if r['address']=='0x140000040')['value']=='NewHeader'
        assert next(r for r in p.items(version=1) if r['address']=='0x140000040')['value']=='OldHeader'
        assert any(s['text']=='NewHeader' for s in p.information('strings')['items'])


def test_standalone_inspection_works_inside_project_bound_session(discovered,tmp_path):
    binary=tmp_path/'header.bin'
    binary.write_bytes(pe_import_fixture())
    for method in ('identify','inspect'):
        r=respond({'method':method,'params':{'path':str(binary)}},str(discovered.path))
        assert r['ok'],r


def test_recovery_defaults_to_recursively_discovered_slots(discovered):
    # No candidate list supplied; it must run recursive analysis and use its refs.
    result=discovered.recover_imports(module_exports=[{'address':'0x1040','module':'test.dll','name':'A'}],max_slots=4)
    assert result['analysis']['stable']
    assert result['source']['candidate_selection']=='recursive decoded memory operands'
    assert any(e['resolved'] and e['address']==0x1030 for e in result['entries'])


def test_shared_labels_update_queue_and_pointed_data_values(discovered):
    discovered.analyze()
    discovered.annotate('0x1050','candidate_routine',kind='name')
    assert next(t for t in discovered.queue() if t['address']=='0x1050')['name']=='candidate_routine'
    assert next(item for item in discovered.items() if item['address']=='0x1038')['value']['target_name']=='candidate_routine'


def test_mapped_immediate_produces_candidate_data_xref_without_code_guess(tmp_path):
    data=bytearray(0x30)
    data[:6]=bytes.fromhex('bf20100000c3')
    data[0x20:0x26]=b'Hello\0'
    binary=tmp_path/'offset.bin'
    binary.write_bytes(data)
    with Project.create(tmp_path/'offset.fdb',binary,arch='x86',base=0x1000) as p:
        assert p.analyze()['stable']
        assert p.xrefs('0x1020')[0]['kind']=='offset_candidate'
        assert p.items()[0]['value']=='Hello'
        assert '0x1020' not in {r['address'] for r in p.disassembly()['instructions']}
        p.annotate('0x1020','greeting',kind='name')
        assert 'greeting' in p.disassembly()['instructions'][0]['display_operands']
