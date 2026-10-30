"""Native UDC source retention and opt-in structural relayout."""
import copy
import json

import pytest

from fdisbull.native_udc import capture_native_definition, native_definition_info, compile_native_definition
from fdisbull.project import Project

ASSUMPTIONS=dict.fromkeys(('no_code_reads','no_code_writes','no_computed_entries',
                           'address_identity_unobserved','timing_unobserved'),True)


def project_at(tmp_path, code='7401a8aac3'):
    path=tmp_path/'authored.bin';path.write_bytes(bytes.fromhex(code))
    p=Project.create(tmp_path/'project.fdb',path,arch='x86',bits=16,base=0x1000)
    p.analyze();return p


def test_capture_reopen_without_original_exact_file_and_relayout(tmp_path):
    with project_at(tmp_path) as p:
        info=capture_native_definition(p,'overlap',[0x1002,0x1003])
        assert info['original_layout_available'] and info['graph_complete']
        assert 'document' not in info and info['qualification']=='native_backings_only'
        full=native_definition_info(p,info['id'],include_blocks=True)['document']
        assert full['capsule']['coverage']['physical_bytes']==3
        assert full['capsule']['coverage']['encoding_bytes']==4
        for b in full['plan']['blocks']:
            assert 'uil' not in b
        output=compile_native_definition(p,info['id'])
        assert output['format']=='fdisbull-native-udc-compilation-1'
        assert output['bytes']=='7401a8aac3' and output['filename']=='authored.bin'
        assert output['qualification']=='original_bytes_only' and output['byte_identity'] is True
        assert output['source_layout_modified'] is False and output['original_file_offsets_preserved'] is True
        assert output['native_execution'] is False
        assert output['graph_complete'] is True and output['semantic_qualification']=='unverified'
        layout=compile_native_definition(p,info['id'],mode='relayout',base=0x200,assumptions=ASSUMPTIONS)
        assert layout['bytes']=='a8aae90400aae90000c3' and not layout['byte_identity']
        assert layout['layout']['qualification']=='structural_only' and not layout['container_writer']
        assert not layout['original_file_offsets_preserved'] and layout['layout_sha256']==layout['layout']['sha256']
        full['plan']['blocks'].clear();assert native_definition_info(p,info['id'])['block_count']>0
    (tmp_path/'authored.bin').unlink()
    with Project(tmp_path/'project.fdb') as p:
        assert compile_native_definition(p,info['id'])['bytes']=='7401a8aac3'
        assert compile_native_definition(p,info['id'],mode='relayout',base=0x200,assumptions=ASSUMPTIONS)['bytes']==layout['bytes']


def test_incomplete_capture_can_passthrough_but_never_relayout(tmp_path):
    with project_at(tmp_path,'9090c3') as p:
        info=capture_native_definition(p,'partial',[0x1000],max_instructions=1)
        assert info['graph_complete'] is False and info['graph_validation']=='verified'
        exact=compile_native_definition(p,info['id']);assert exact['bytes']=='9090c3' and not exact['graph_complete']
        with pytest.raises(ValueError,match='complete'):compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS)


def test_parent_and_patched_version_are_explicit(tmp_path):
    with project_at(tmp_path) as p:
        first=capture_native_definition(p,'overlap',[0x1002,0x1003])
        with pytest.raises(ValueError,match='parent'):capture_native_definition(p,'overlap',[0x1002],parent='wrong')
        with pytest.raises(ValueError,match='parent'):capture_native_definition(p,'other',[0x1002],parent=first['id'])
        child=p.patch(0x1003,'90')['version'];p.analyze(version=child)
        second=capture_native_definition(p,'overlap',[0x1002,0x1003],parent=first['id'])
        assert second['version']==child and second['parent']==first['id'] and not second['original_layout_available']
        with pytest.raises(ValueError,match='unavailable'):compile_native_definition(p,second['id'])
        # Old definition remains pinned to source version 1 even when latest is patched.
        assert compile_native_definition(p,first['id'])['bytes']=='7401a8aac3'
        assert compile_native_definition(p,first['id'],mode='relayout',assumptions=ASSUMPTIONS)['version']==1
        assert compile_native_definition(p,second['id'],mode='relayout',assumptions=ASSUMPTIONS)['version']==child


def test_original_blob_deduplicates_and_tamper_is_detected(tmp_path):
    with project_at(tmp_path) as p:
        first=capture_native_definition(p,'one',[0x1002]);second=capture_native_definition(p,'two',[0x1003])
        assert p.db.execute('SELECT count(*) FROM native_udc_sources').fetchone()[0]==1
        p.db.execute('UPDATE native_udc_sources SET data=?',(b'bad',));p.db.commit()
        for n in (first['id'],second['id']):
            with pytest.raises(ValueError,match='corrupt'):native_definition_info(p,n)


def test_definition_tamper_modes_and_options_refuse(tmp_path):
    with project_at(tmp_path) as p:
        info=capture_native_definition(p,'one',[0x1002,0x1003])
        for kwargs in ({'mode':'bad'}, {'base':1}, {'assumptions':ASSUMPTIONS},
                       {'mode':'relayout'}, {'mode':'relayout','assumptions':{**ASSUMPTIONS,'no_code_reads':False}}):
            with pytest.raises(ValueError):compile_native_definition(p,info['id'],**kwargs)
        row=p.db.execute('SELECT document FROM native_udc_definitions WHERE id=?',(info['id'],)).fetchone()
        value=json.loads(row[0]);value['plan']['blocks'][0]['bytes']='90'
        p.db.execute('UPDATE native_udc_definitions SET document=? WHERE id=?',(json.dumps(value),info['id']));p.db.commit()
        with pytest.raises(ValueError,match='integrity'):compile_native_definition(p,info['id'])


def test_group_plan_revalidation_and_unknown_definition(tmp_path):
    with project_at(tmp_path,'909090c3') as p:
        cap=p.code_backings([0x1000]);split=next(b['id'] for b in cap['blocks'] if b['address']=='0x1002')
        info=capture_native_definition(p,'split',[0x1000],split_at=[split])
        doc=native_definition_info(p,info['id'],include_blocks=True)['document']
        assert len(doc['plan']['blocks'])==2 and doc['plan']['split_at']==[split]
        with pytest.raises(ValueError,match='unknown'):native_definition_info(p,'unknown')
        with pytest.raises(ValueError,match='split_at'):capture_native_definition(p,'bad',[0x1000],split_at=['not-an-id'])


def test_sqlite_disguised_original_rejected(tmp_path):
    with project_at(tmp_path) as p:
        p.db.execute('UPDATE binary_info SET source_bytes=? WHERE version=1',(b'SQLite format 3\x00private',));p.db.commit()
        with pytest.raises(ValueError,match='databases'):capture_native_definition(p,'bad',[0x1002])


def test_graph_facts_drift_blocks_relayout_but_not_exact_source(tmp_path):
    with project_at(tmp_path) as p:
        info=capture_native_definition(p,'overlap',[0x1002,0x1003])
        # Erase a stored decode fact only; the versioned region and original file remain intact.
        p.db.execute('DELETE FROM instructions WHERE version=1 AND address=?', (f'{0x1003:016x}',));p.db.commit()
        exact=compile_native_definition(p,info['id']);assert exact['bytes']=='7401a8aac3'
        assert exact['graph_complete'] is None and exact['graph_validation']=='unverified'
        metadata=native_definition_info(p,info['id']);assert metadata['graph_complete'] is None and metadata['graph_validation']=='unverified'
        with pytest.raises(ValueError,match='capture graph'):
            compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS)


def test_resealed_forged_plan_and_source_version_fail_readback(tmp_path):
    from fdisbull.native_udc import _definition_digest
    with project_at(tmp_path) as p:
        info=capture_native_definition(p,'overlap',[0x1002,0x1003])
        row=p.db.execute('SELECT * FROM native_udc_definitions WHERE id=?',(info['id'],)).fetchone()
        doc=json.loads(row['document']);doc['plan']['blocks'][0]['bytes']='90'
        checksum=_definition_digest(row['version'],row['name'],row['parent'],row['author'],doc)
        p.db.execute('UPDATE native_udc_definitions SET document=?,sha256=? WHERE id=?',(json.dumps(doc),checksum,info['id']));p.db.commit()
        with pytest.raises(ValueError,match='plan integrity'):native_definition_info(p,info['id'])


def test_missing_original_bytes_is_inspectable_without_claiming_passthrough(tmp_path):
    with project_at(tmp_path) as p:
        p.db.execute('UPDATE binary_info SET source_bytes=NULL WHERE version=1');p.db.commit()
        info=capture_native_definition(p,'no-original',[0x1002])
        assert not info['original_layout_available']
        with pytest.raises(ValueError,match='unavailable'):compile_native_definition(p,info['id'])
        assert compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS)['qualification']=='structural_only'


def test_dos_com_exact_file_then_separate_native_relayout(tmp_path):
    source=tmp_path/'OVL.COM';source.write_bytes(bytes.fromhex('7401a8aac3'))
    with Project.create(tmp_path/'dos.fdb',source,image='com') as project:
        project.analyze()
        info=capture_native_definition(project,'dos-overlap',[0x10102,0x10103])
        exact=compile_native_definition(project,info['id'])
        assert exact['filename']=='OVL.COM' and exact['bytes']==source.read_bytes().hex()
        assert exact['qualification']=='original_bytes_only' and exact['source_layout_modified'] is False
        emitted=compile_native_definition(project,info['id'],mode='relayout',base=0x200,assumptions=ASSUMPTIONS)
        assert emitted['bytes']=='a8aae90400aae90000c3'
        assert sorted(emitted['layout']['entries'].values())==[0x200,0x205]
        assert emitted['qualification']=='structural_only' and emitted['container_writer'] is False


def test_grouped_placement_reorders_stably_without_changing_source_or_definition(tmp_path):
    with project_at(tmp_path,'909090c3') as p:
        atoms=p.code_backings([0x1000]);split=next(b['id'] for b in atoms['blocks'] if b['address']=='0x1002')
        info=capture_native_definition(p,'grouped',[0x1000],split_at=[split])
        before=native_definition_info(p,info['id'],include_blocks=True)
        groups=before['document']['plan']['blocks'];ids=[b['id'] for b in groups]
        first=compile_native_definition(p,info['id'],mode='relayout',base=0x200,assumptions=ASSUMPTIONS)
        second=compile_native_definition(p,info['id'],mode='relayout',base=0x200,block_order=list(reversed(ids)),assumptions=ASSUMPTIONS)
        assert first['layout']['placement']['block_order']==ids
        assert second['layout']['placement']['block_order']==list(reversed(ids))
        assert first['layout_sha256']!=second['layout_sha256']
        assert first['definition_sha256']==second['definition_sha256']==info['sha256']
        assert first['capsule_sha256']==second['capsule_sha256']==info['capsule_sha256']
        for group in groups:
            one=first['layout']['logical_blocks'][group['id']];two=second['layout']['logical_blocks'][group['id']]
            assert one['block_revision']==two['block_revision']==group['block_revision']
            assert [o['node'] for o in one['instruction_occurrences']]==group['instructions']
            assert [o['node'] for o in two['instruction_occurrences']]==group['instructions']
        for result in (first,second):
            actual=result['layout']['placement']['instruction_order']
            wanted=[a for group_id in result['layout']['placement']['block_order'] for a in next(g for g in groups if g['id']==group_id)['instructions']]
            assert actual==wanted
        after=native_definition_info(p,info['id'],include_blocks=True)
        assert after==before
        with pytest.raises(ValueError,match='mutually exclusive'):
            compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS,order=first['layout']['placement']['instruction_order'],block_order=ids)
        for bad in ([],ids+[ids[0]],[ids[0],ids[0]],['unknown']):
            with pytest.raises(ValueError,match='block_order'):compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS,block_order=bad)
        for kwargs in ({'order':[]},{'block_order':[]},{'base':1},{'base':True},{'assumptions':{}},{'entry_references':[]}):
            with pytest.raises(ValueError,match='layout options'):compile_native_definition(p,info['id'],**kwargs)


def test_resealed_partial_capsule_cannot_claim_graph_completeness(tmp_path):
    from fdisbull.code_backings import digest
    from fdisbull.code_blocks import group_code_backings
    from fdisbull.native_udc import _definition_digest
    with project_at(tmp_path,'c3ebfe') as p:
        p.analyze(start=0x1001)
        info=capture_native_definition(p,'partial',[0x1000,0x1001],max_instructions=1)
        assert info['graph_complete'] is False and info['graph_validation']=='verified'
        row=p.db.execute('SELECT * FROM native_udc_definitions WHERE id=?',(info['id'],)).fetchone()
        doc=json.loads(row['document']);cap=doc['capsule']
        cap['complete']=True;cap['unresolved']=[]
        cap['sha256']=digest({k:v for k,v in cap.items() if k!='sha256'})
        doc['plan']=group_code_backings(cap)
        assert doc['plan']['complete'] is True
        checksum=_definition_digest(row['version'],row['name'],row['parent'],row['author'],doc)
        p.db.execute('UPDATE native_udc_definitions SET document=?,sha256=? WHERE id=?',(json.dumps(doc),checksum,info['id']));p.db.commit()
        result=native_definition_info(p,info['id'])
        assert result['graph_complete'] is None and result['graph_validation']=='unverified'
        exact=compile_native_definition(p,info['id'])
        assert exact['bytes']=='c3ebfe' and exact['graph_complete'] is None and exact['graph_validation']=='unverified'
        with pytest.raises(ValueError,match='capture graph'):
            compile_native_definition(p,info['id'],mode='relayout',assumptions=ASSUMPTIONS)


def test_mz_original_layout_preserves_header_relocation_and_unrelocated_word(tmp_path):
    import struct

    # Relocation at module offset 8 is outside the overlapping five-byte code.
    module=bytearray(bytes.fromhex('7401a8aac3') + b'\x00'*3 + bytes.fromhex('3412') + b'\x00'*6)
    size=64+len(module);header=bytearray(64)
    struct.pack_into('<14H',header,0,0x5a4d,size%512,(size+511)//512,1,4,0,0xffff,0,0,0,0,0,28,0)
    struct.pack_into('<HH',header,28,8,0)
    original=bytes(header)+bytes(module)
    source=tmp_path/'OVERLAP.EXE';source.write_bytes(original)
    with Project.create(tmp_path/'mz.fdb',source) as project:
        project.analyze()
        # This is a meaningful loader relocation, not just an untouched fixture.
        address=0x10000+8
        region=next(r for r in project.regions(1) if r.start <= address < r.start+len(r.data))
        relocated=region.data[address-region.start:address-region.start+2]
        assert relocated==bytes.fromhex('3422') and original[64+8:64+10]==bytes.fromhex('3412')
        info=capture_native_definition(project,'mz-overlap',['1000:0002','1000:0003'])
        capsule=native_definition_info(project,info['id'],include_blocks=True)['document']['capsule']
        assert capsule['coverage']['physical_bytes']==3 and capsule['coverage']['encoding_bytes']==4
        exact=compile_native_definition(project,info['id'])
        assert exact['filename']=='OVERLAP.EXE' and bytes.fromhex(exact['bytes'])==original
        assert bytes.fromhex(exact['bytes'])[28:32]==struct.pack('<HH',8,0)
        assert bytes.fromhex(exact['bytes'])[66:69]==bytes.fromhex('a8aac3')
        assert bytes.fromhex(exact['bytes'])[72:74]==bytes.fromhex('3412')
        assert exact['qualification']=='original_bytes_only' and exact['original_file_offsets_preserved'] is True
