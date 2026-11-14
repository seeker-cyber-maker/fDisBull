"""Persistence and qualification for explicit native COM implementations."""
import json

import pytest

from fdisbull.dos_udc import (define_dos_udc, dos_udc_info, register_dos_implementation,
                              dos_implementation_info, compile_dos_udc)
from fdisbull.native_udc import capture_native_definition, native_definition_info
from fdisbull.project import Project

PROJECTION={'bindings':{'ax':'$x'},'inputs':[],'outputs':['ax']}


def setup_project(path):
    source=path/'GAME.COM'
    # MOV AX,1; JMP to HLT. Padding and a near-code-pointer table follow.
    source.write_bytes(bytes.fromhex('b80100eb0190f4')+bytes(9)+bytes.fromhex('0601'))
    project=Project.create(path/'project.fdb',source,image='com');project.analyze()
    native=capture_native_definition(project,'source',['1000:0100'])
    groups=native_definition_info(project,native['id'],include_blocks=True)['document']['plan']['blocks']
    block=next(b for b in groups if b['bytes']=='b80100eb01')
    terminal=next(b for b in groups if b['bytes']=='f4')
    return project,source,native,block,terminal


def definition(p,native,terminal):
    return define_dos_udc(p,'standard',native['id'],data=[{'id':'table','ip':0x110,'size':2}],
        references=[{'kind':'near-code-pointer','data':'table','offset':0,'target':terminal['id'],'expected_hex':'0601'}])


def test_definition_and_candidates_persist_reopen_without_source(tmp_path):
    p,source,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal);info=dos_udc_info(p,d['id'],include_blocks=True)
        assert info['data_regions']==1 and info['references']==1 and info['semantic_qualification']=='unverified'
        assert info['document']['data'][0]['bytes']=='0601'
        same=register_dos_implementation(p,d['id'],block['id'],'b801004048',expected_block_revision=block['block_revision'],
            purpose='register-equivalence',projection=PROJECTION)
        assert same['qualification']['status']=='equivalent_under_assumptions'
        assert 'flags, memory' in same['qualification']['scope']
        changed=register_dos_implementation(p,d['id'],block['id'],'b80200',expected_block_revision=block['block_revision'],parent=same['id'])
        assert changed['qualification']['status']=='unverified' and changed['purpose']=='experiment'
        assert same['candidate_sha256']!=changed['candidate_sha256']
    source.unlink()
    with Project(tmp_path/'project.fdb') as p:
        assert dos_udc_info(p,d['id'])['sha256']==d['sha256']
        assert dos_implementation_info(p,same['id'])['qualification']['status']=='equivalent_under_assumptions'
        assert dos_implementation_info(p,changed['id'])['parent']==same['id']


def test_register_equivalence_rejects_counterexample_and_unavailable(tmp_path,monkeypatch):
    import fdisbull.dos_udc as module
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        kwargs=dict(expected_block_revision=block['block_revision'],purpose='register-equivalence',projection=PROJECTION)
        with pytest.raises(ValueError,match='counterexample'):register_dos_implementation(p,d['id'],block['id'],'b80200',**kwargs)
        monkeypatch.setattr(module,'verify_block',lambda *args:{'status':'unavailable'})
        with pytest.raises(ValueError,match='unavailable'):register_dos_implementation(p,d['id'],block['id'],'b80100',**kwargs)
        assert p.db.execute('SELECT count(*) FROM dos_udc_implementations').fetchone()[0]==0


def test_parent_block_and_revision_guards(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        with pytest.raises(ValueError,match='parent'):define_dos_udc(p,'standard',native['id'])
        d2=define_dos_udc(p,'standard',native['id'],parent=d['id']);assert d2['parent']==d['id']
        with pytest.raises(ValueError,match='parent'):define_dos_udc(p,'other',native['id'],parent=d2['id'])
        with pytest.raises(ValueError,match='revision'):register_dos_implementation(p,d['id'],block['id'],'90',expected_block_revision='0'*64)
        first=register_dos_implementation(p,d['id'],block['id'],'90',expected_block_revision=block['block_revision'])
        with pytest.raises(ValueError,match='parent'):register_dos_implementation(p,d['id'],block['id'],'90',expected_block_revision=block['block_revision'])
        with pytest.raises(ValueError,match='successor'):register_dos_implementation(p,d['id'],terminal['id'],'90',expected_block_revision=terminal['block_revision'])
        with pytest.raises(ValueError,match='parent'):register_dos_implementation(p,d2['id'],block['id'],'90',expected_block_revision=block['block_revision'],parent=first['id'])


@pytest.mark.parametrize('code',['','90c3','eb00','f4','cd10','ff','B80100','0g'])
def test_candidate_rejects_unsupported_or_malformed_bytes(tmp_path,code):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        with pytest.raises(ValueError):register_dos_implementation(p,d['id'],block['id'],code,expected_block_revision=block['block_revision'])


def test_data_ranges_and_references_fail_closed(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        for data in ([{'id':'bad','ip':0x100,'size':1}],[{'id':'bad','ip':0xff,'size':1}],
                     [{'id':'bad','ip':0x111,'size':2}],[{'id':'a','ip':0x110,'size':2},{'id':'b','ip':0x111,'size':1}]):
            with pytest.raises(ValueError):define_dos_udc(p,'bad',native['id'],data=data)
        bad={'kind':'near-code-pointer','data':'table','offset':0,'target':terminal['id'],'expected_hex':'ffff'}
        with pytest.raises(ValueError,match='expected bytes'):define_dos_udc(p,'bad',native['id'],data=[{'id':'table','ip':0x110,'size':2}],references=[bad])
        d=definition(p,native,terminal)
        ref={'kind':'data-immediate','field_offset':1,'target':'table','expected_hex':'0200'}
        with pytest.raises(ValueError,match='expected bytes'):register_dos_implementation(p,d['id'],block['id'],'b80100',expected_block_revision=block['block_revision'],references=[ref])


def test_tamper_source_data_definition_and_implementation_refuse(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal);impl=register_dos_implementation(p,d['id'],block['id'],'90',expected_block_revision=block['block_revision'])
        row=p.db.execute('SELECT document FROM dos_udc_implementations WHERE id=?',(impl['id'],)).fetchone()
        value=json.loads(row[0]);value['bytes']='40';p.db.execute('UPDATE dos_udc_implementations SET document=? WHERE id=?',(json.dumps(value),impl['id']));p.db.commit()
        with pytest.raises(ValueError,match='integrity'):dos_implementation_info(p,impl['id'])
        p.db.execute('UPDATE dos_udc_definitions SET document=? WHERE id=?',('{}',d['id']));p.db.commit()
        with pytest.raises(ValueError,match='integrity'):dos_udc_info(p,d['id'])


def test_requires_complete_version_one_com_not_mz_or_patched(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        child=p.patch('1000:0101','02')['version'];p.analyze(version=child)
        later=capture_native_definition(p,'patched',['1000:0100'],version=child)
        with pytest.raises(ValueError,match='version-1'):define_dos_udc(p,'bad',later['id'])
        incomplete=capture_native_definition(p,'partial',['1000:0100'],version=1,max_instructions=1)
        with pytest.raises(ValueError,match='complete'):define_dos_udc(p,'bad',incomplete['id'])


def test_compile_retains_definition_identity_and_rechecks_projection(tmp_path,monkeypatch):
    import fdisbull.dos_udc as module
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        eq=register_dos_implementation(p,d['id'],block['id'],'b801004048',expected_block_revision=block['block_revision'],purpose='register-equivalence',projection=PROJECTION)
        changed=register_dos_implementation(p,d['id'],block['id'],'b80200',expected_block_revision=block['block_revision'],parent=eq['id'])
        assumptions=dict.fromkeys(('no_code_reads','no_code_writes','no_computed_entries','address_identity_unobserved','timing_unobserved'),True)
        a=compile_dos_udc(p,d['id'],implementations={block['id']:eq['id']},assumptions=assumptions)
        b=compile_dos_udc(p,d['id'],implementations={block['id']:changed['id']},assumptions=assumptions)
        assert a['qualification']==b['qualification']=='structural_only'
        assert a['definition_sha256']==b['definition_sha256']==d['sha256']
        assert a['implementations'][block['id']]['qualification']['status']=='equivalent_under_assumptions'
        assert b['implementations'][block['id']]['qualification']['status']=='unverified'
        assert a['sha256']!=b['sha256'] and not a['native_execution']
        monkeypatch.setattr(module,'verify_block',lambda *args:{'status':'unknown'})
        with pytest.raises(ValueError,match='unknown'):compile_dos_udc(p,d['id'],implementations={block['id']:eq['id']},assumptions=assumptions)


def test_projection_rejects_candidate_pointer_fixups_that_could_change_outputs(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        ref={'kind':'code-immediate','field_offset':1,'target':terminal['id'],'expected_hex':'0601'}
        with pytest.raises(ValueError,match='rewritten candidate references'):
            register_dos_implementation(p,d['id'],block['id'],'b80601',expected_block_revision=block['block_revision'],
                                        references=[ref],purpose='register-equivalence',projection=PROJECTION)


def test_data_rejects_stored_code_outside_selected_graph(tmp_path):
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        # The source JMP skips this NOP; a separate explicit entry makes it known code.
        assert all(b['address']!='0x10105' for b in native_definition_info(p,native['id'],include_blocks=True)['document']['capsule']['blocks'])
        p.analyze(start='1000:0105')
        refreshed=capture_native_definition(p,'source',['1000:0100'],parent=native['id'])
        assert all(b['address']!='0x10105' for b in native_definition_info(p,refreshed['id'],include_blocks=True)['document']['capsule']['blocks'])
        with pytest.raises(ValueError,match='overlaps code'):
            define_dos_udc(p,'bad',refreshed['id'],data=[{'id':'not-data','ip':0x105,'size':1}])


def test_resealed_false_proof_is_recomputed_before_info_or_compile(tmp_path):
    from fdisbull.dos_udc import _implementation_digest
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        impl=register_dos_implementation(p,d['id'],block['id'],'b80200',expected_block_revision=block['block_revision'])
        row=p.db.execute('SELECT * FROM dos_udc_implementations WHERE id=?',(impl['id'],)).fetchone()
        body=json.loads(row['document']);body.update(purpose='register-equivalence',projection=PROJECTION,
                                                      qualification={'status':'equivalent_under_assumptions'})
        checksum=_implementation_digest(row['definition'],row['block'],row['parent'],row['author'],body)
        p.db.execute('UPDATE dos_udc_implementations SET document=?,sha256=? WHERE id=?',(json.dumps(body),checksum,impl['id']));p.db.commit()
        with pytest.raises(ValueError,match='counterexample'):dos_implementation_info(p,impl['id'])
        with pytest.raises(ValueError,match='counterexample'):compile_dos_udc(p,d['id'],implementations={block['id']:impl['id']})


def test_resealed_forged_data_identity_is_checked_against_source(tmp_path):
    from fdisbull.dos_udc import _definition_digest, _sha
    p,_,native,block,terminal=setup_project(tmp_path)
    with p:
        d=definition(p,native,terminal)
        row=p.db.execute('SELECT * FROM dos_udc_definitions WHERE id=?',(d['id'],)).fetchone()
        body=json.loads(row['document']);body['data'][0]['bytes']='ffff';body['data'][0]['sha256']=_sha(bytes.fromhex('ffff'))
        checksum=_definition_digest(row['version'],row['native_definition'],row['name'],row['parent'],row['author'],body)
        p.db.execute('UPDATE dos_udc_definitions SET document=?,sha256=? WHERE id=?',(json.dumps(body),checksum,d['id']));p.db.commit()
        with pytest.raises(ValueError,match='integrity'):dos_udc_info(p,d['id'])


def test_projection_rejects_source_immediate_fixup_even_without_candidate_fixup(tmp_path):
    source=tmp_path/'PTR.COM';source.write_bytes(bytes.fromhex('b80601eb0190f4'))
    with Project.create(tmp_path/'pointer.fdb',source,image='com') as p:
        p.analyze();native=capture_native_definition(p,'native',['1000:0100'])
        detail=native_definition_info(p,native['id'],include_blocks=True)['document']
        group=next(g for g in detail['plan']['blocks'] if g['bytes']=='b80601eb01')
        terminal=next(g for g in detail['plan']['blocks'] if g['bytes']=='f4')
        atom=next(a['id'] for a in detail['capsule']['blocks'] if a['bytes']=='b80601')
        ref={'kind':'code-immediate','instruction':atom,'field_offset':1,'target':terminal['id'],'expected_hex':'0601'}
        d=define_dos_udc(p,'source-fixup',native['id'],references=[ref])
        with pytest.raises(ValueError,match='source immediate fixups'):
            register_dos_implementation(p,d['id'],group['id'],'b80601',expected_block_revision=group['block_revision'],
                                        purpose='register-equivalence',projection=PROJECTION)
        experiment=register_dos_implementation(p,d['id'],group['id'],'b80601',expected_block_revision=group['block_revision'])
        assert experiment['qualification']['status']=='unverified'


def test_rejects_mz_even_when_source_graph_is_complete(tmp_path):
    import struct
    module=bytes.fromhex('b80100eb0190f4');header=bytearray(64);size=64+len(module)
    struct.pack_into('<14H',header,0,0x5a4d,size%512,(size+511)//512,0,4,0,0xffff,0,0,0,0,0,28,0)
    source=tmp_path/'source.exe';source.write_bytes(bytes(header)+module)
    with Project.create(tmp_path/'mz.fdb',source) as p:
        p.analyze();native=capture_native_definition(p,'native',['1000:0000'])
        assert native['graph_complete']
        with pytest.raises(ValueError,match='COM'):define_dos_udc(p,'wrong-profile',native['id'])
