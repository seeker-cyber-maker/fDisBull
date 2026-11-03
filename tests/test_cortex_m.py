"""Authored Thumb encodings and public persistent Cortex-M contracts (PM0056)."""
import json
import sqlite3
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull.cli import invoke
from fdisbull.decoder import decode
from fdisbull.loader import load_image
from fdisbull.memory import instruction_memory_accesses
from fdisbull.project import Project

BASE = 0x08000000


@pytest.fixture(autouse=True)
def private_target_store(tmp_path,monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'target-objects'))


def firmware(tmp_path, code='0148804701480047', interrupt=True):
    data = bytearray(128)
    struct.pack_into('<II',data,0,0x20001000,BASE+65)
    if interrupt:
        struct.pack_into('<I',data,8,BASE+97)
    body=bytes.fromhex(code)
    data[64:64+len(body)]=body
    struct.pack_into('<II',data,72,BASE+97,BASE+101)
    data[96:98]=bytes.fromhex('7047')
    path=tmp_path/'firmware.bin'
    path.write_bytes(data)
    return path


def create(tmp_path, **options):
    return Project.create(tmp_path/'analysis.fdb',firmware(tmp_path),
                          profile='cortex-m',base=BASE,vector_count=16,**options)


@pytest.mark.parametrize('raw,size,flow,target',[
    ('0120',2,'next',None), ('00f000f8',4,'call',0x1004),
    ('00d0',2,'conditional',0x1004), ('fee7',2,'jump',0x1000),
    ('8047',2,'indirect_call',None), ('0047',2,'indirect_jump',None),
    ('7047',2,'return',None), ('00bd',2,'return',None),
    ('dfe800f0',4,'indirect_jump',None), ('00df',2,'stop',None),
])
def test_native_widths_and_control(raw,size,flow,target):
    row=decode(bytes.fromhex(raw),0x1000,'thumb',32)
    assert (row['size'],row['flow'],row['target'])==(size,flow,target)
    assert row['bytes']==raw


def test_literal_alignment_invalid_and_truncated_encodings():
    # PC-relative LDR aligns address+4 down to a word before adding 4.
    row=decode(bytes.fromhex('0148'),0x1002,'thumb',32)
    assert row['data_refs']==[0x1008]
    assert row['references'][0]['width']==4
    for raw,address in [('00',0x1000),('00f0',0x1000),('ffff',0x1000),('7047',0x1001)]:
        assert decode(bytes.fromhex(raw),address,'thumb',32) is None
    with pytest.raises(ValueError,match='32 bits'):
        decode(bytes.fromhex('7047'),0x1000,'thumb',64)


def test_profile_seeds_reset_first_preserves_vectors_and_literal_data(tmp_path):
    with create(tmp_path) as p:
        assert p.status()['entry']==hex(BASE+64)
        assert [r.executable for r in p.regions(1)]==[False,True]
        small=p.analyze(max_instructions=1)
        assert not small['stable'] and small['budget_exhausted']
        assert [r['address'] for r in p.disassembly()['instructions']]==[hex(BASE+64)]
        assert p.analyze(max_instructions=128)['stable']
        rows=p.disassembly(lines=20)['instructions']
        assert [r['address'] for r in rows]==[hex(BASE+x) for x in (64,66,68,70,96)]
        assert all(not BASE<=int(r['address'],16)<BASE+64 for r in rows)
        info=p.information()['cortex_m']
        assert info['vectors'][0]['raw']==BASE+65
        assert info['vectors'][0]['address']==BASE+64 and info['initial_sp']==0x20001000
        assert all(f['status']=='candidate' for f in p.functions())
        assert any(x['kind']=='vector' for x in p.xrefs(BASE+64))
        assert any(x['kind']=='data' for x in p.xrefs(BASE+72))
        assert p.issues()  # Unknown indirect/exception return state remains visible.
        with pytest.raises(ValueError,match='derived semantics'):
            p.auto_analyze()


@pytest.mark.parametrize('options,match',[
    ({'profile':'cortex-m','vector_count':16},'explicit base'),
    ({'profile':'cortex-m','base':BASE},'vector_count'),
    ({'profile':'cortex-m','base':BASE+2,'vector_count':16},'aligned'),
    ({'profile':'cortex-m','base':BASE,'vector_count':True},'16..256'),
    ({'profile':'cortex-m','base':BASE,'vector_count':257},'16..256'),
    ({'profile':'cortex-m','base':BASE,'vector_count':16,'entry':BASE+66},'derived'),
    ({'vector_count':16},'requires profile'),
    ({'arch':'thumb','bits':64},'32 bits'),
    ({'arch':'thumb','base':1},'alignment'),
    ({'arch':'thumb','entry':1},'halfword'),
])
def test_invalid_profile_options_fail_before_database_creation(tmp_path,options,match):
    path=firmware(tmp_path)
    with pytest.raises(ValueError,match=match):
        Project.create(tmp_path/'bad.fdb',path,**options)
    assert not (tmp_path/'bad.fdb').exists()


@pytest.mark.parametrize('offset,value,match',[(0,0x1000,'SP'),(0,0x20001001,'SP'),(4,BASE+64,'reset'),(4,BASE+129,'reset')])
def test_invalid_vector_words(tmp_path,offset,value,match):
    path=firmware(tmp_path);data=bytearray(path.read_bytes());struct.pack_into('<I',data,offset,value);path.write_bytes(data)
    with pytest.raises(ValueError,match=match):
        load_image(path,profile='cortex-m',base=BASE,vector_count=16)


def test_it_return_keeps_conditional_continuation_and_does_not_leak_decoder_state(tmp_path):
    path=firmware(tmp_path,'08bf704701207047',interrupt=False)
    with Project.create(tmp_path/'it.fdb',path,profile='cortex-m',base=BASE,vector_count=16) as p:
        p.analyze()
        rows=p.disassembly()['instructions']
        assert [r['flow'] for r in rows]==['next','conditional','next','return']
        assert rows[1]['operands']=='lr' and rows[1]['predicate']['origins']==[hex(BASE+64)]
        assert 'lexical IT' in rows[1]['display_operands']
        assert not p.advanced_status()['supported'] and p.advanced_status()['stable'] is None
        assert any(x['kind']=='fallthrough' for x in p.xrefs(BASE+68))
        child=p.patch(BASE+64,'00bf')['version']
        p.analyze(version=child)
        assert [r['flow'] for r in p.disassembly(version=child)['instructions']]==['next','return']
    assert decode(bytes.fromhex('7047'),0x1000,'thumb',32)['flow']=='return'


def test_vector_patch_rebuilds_entry_and_parent_isolation(tmp_path):
    with create(tmp_path) as p:
        p.analyze()
        child=p.patch(BASE+4,struct.pack('<I',BASE+97).hex())['version']
        p.analyze(version=child)
        assert p.status(version=child)['entry']==hex(BASE+96)
        assert p.disassembly(version=child)['instructions'][0]['address']==hex(BASE+96)
        assert p.status(version=1)['entry']==hex(BASE+64)
        assert p.information(version=1)['cortex_m']['vectors'][0]['raw']==BASE+65
        assert not p.xrefs(BASE+64,version=child)
        bad=p.patch(BASE+4,'00000000',version=1)['version']
        assert p.status(version=bad)['entry'] is None
        with pytest.raises(ValueError,match='Invalid Cortex-M vectors'):
            p.analyze(version=bad)
        with pytest.raises(ValueError,match='no valid entry'):
            p.source_candidate(tmp_path/'firmware.bin',version=bad)


def test_literal_memory_facts_and_unknown_register_memory():
    fact=instruction_memory_accesses(bytes.fromhex('0148'),0x1002,'thumb',32)[0]
    assert fact['concrete_target']==0x1008 and fact['width']==4
    fact=instruction_memory_accesses(bytes.fromhex('0868'),0x1000,'thumb',32)[0]
    assert fact['concrete_target'] is None and fact['unresolved_reasons']


def test_late_it_discovery_preserves_continuation_from_another_entry(tmp_path):
    source=tmp_path/'late.bin'
    # BEQ reaches BX LR before its enclosing lexical IT is decoded on the
    # not-taken path. Discovering IT must revisit the stored flow facts.
    source.write_bytes(bytes.fromhex('02d000bf00bf08bf704701207047'))
    with Project.create(tmp_path/'late.fdb',source,arch='thumb',base=0x1000) as p:
        assert p.analyze()['stable']
        rows={r['address']:r for r in p.disassembly()['instructions']}
        assert rows['0x1008']['flow']=='conditional'
        assert rows['0x100a']['mnemonic']=='movs'
        assert any(r['kind']=='fallthrough' for r in p.xrefs(0x100a))


def test_referenced_literal_is_held_unless_code_is_explicit(tmp_path):
    source=tmp_path/'pool.bin';source.write_bytes(bytes.fromhex('004800bf01207047'))
    with Project.create(tmp_path/'pool.fdb',source,arch='thumb',base=0x1000) as p:
        p.analyze()
        assert [r['address'] for r in p.disassembly()['instructions']]==['0x1000','0x1002']
        assert any(r['state']=='blocked' for r in p.issues())
        p.represent(0x1004,'code',size=2)
        assert any(r['address']=='0x1004' for r in p.disassembly()['instructions'])


def test_reserved_vectors_and_canonical_analysis_start(tmp_path):
    source=firmware(tmp_path);data=bytearray(source.read_bytes());struct.pack_into('<I',data,28,BASE+101);source.write_bytes(data)
    with Project.create(tmp_path/'reserved.fdb',source,profile='cortex-m',base=BASE,vector_count=16) as p:
        item=p.information()['cortex_m']['vectors'][6]
        assert item['raw']==BASE+101 and not item['valid'] and item['reason']=='reserved vector'
        with pytest.raises(ValueError,match='halfword'):
            p.analyze(start=BASE+65)


def test_fresh_process_restart_patch_and_stored_exports(tmp_path):
    source=firmware(tmp_path);database=tmp_path/'cli.fdb'
    def call(method,**params):
        reply=subprocess.run([sys.executable,'-m','fdisbull','request',json.dumps(dict(method=method,params=params))],
                             text=True,capture_output=True,check=True)
        result=json.loads(reply.stdout)
        assert result['ok'],result
        return result['result']
    call('import',project=str(database),path=str(source),profile='cortex-m',base=BASE,vector_count=16)
    call('analyze',project=str(database))
    call('rename',project=str(database),address=BASE+64,name='startup',author='test')
    source.rename(tmp_path/'preserved-input.bin')
    parent=call('disasm',project=str(database),version=1)['instructions']
    assert parent[0]['name']=='startup' and parent[0]['bytes']=='0148'
    child=call('patch',project=str(database),address=BASE+64,data='00bf')['version']
    call('analyze',project=str(database),version=child)
    assert call('disasm',project=str(database),version=1)['instructions'][0]['bytes']=='0148'
    assert call('disasm',project=str(database),version=child)['instructions'][0]['bytes']=='00bf'
    call('render',project=str(database),version=1,output=str(tmp_path/'stored.png'),format='png')
    call('render-cfg',project=str(database),version=1,address=BASE+64,output=str(tmp_path/'stored.svg'))
    with Image.open(tmp_path/'stored.png') as image:
        image.load();assert image.width>=1000 and image.height>100
    assert '<svg' in (tmp_path/'stored.svg').read_text()


@pytest.mark.parametrize('raw,width',[
    ('dfe90101',8),  # LDRD r0,r1,[PC,#4]: two words.
    ('9fed010a',4),  # VLDR s0,[PC,#4]: one single-precision register.
    ('9fed010b',8),  # VLDR d0,[PC,#4]: one double-precision register.
])
def test_wide_literal_pool_extent_is_held_across_restart(tmp_path,raw,width):
    source=tmp_path/'wide-pool.bin'
    source.write_bytes(bytes.fromhex(raw+'00bf00bf01200221032204237047'))
    database=tmp_path/'wide-pool.fdb'
    row=decode(source.read_bytes(),0x1002,'thumb',32)
    assert row['references'][0]['target']==0x1008
    assert row['references'][0]['width']==width
    assert row['literals']==[{'address':0x1008,'size':width}]
    access=instruction_memory_accesses(source.read_bytes(),0x1002,'thumb',32)[0]
    assert access['concrete_target']==0x1008 and access['width']==width
    assert access['may_read']
    with Project.create(database,source,arch='thumb',base=0x1000) as p:
        assert p.analyze()['stable']
        assert [r['address'] for r in p.disassembly()['instructions']]==['0x1000','0x1004','0x1006']
    source.unlink()
    with Project(database) as p:
        # Starting at the last halfword of the referenced span must still hold
        # it as data after restart; explicit representation is the override.
        last=0x1008+width-2
        p.analyze(start=last)
        assert hex(last) not in [r['address'] for r in p.disassembly()['instructions']]
        p.represent(last,'code',size=2)
        assert hex(last) in [r['address'] for r in p.disassembly()['instructions']]


@pytest.mark.parametrize('raw,address,target',[
    ('0ff20800',0x1000,0x100c), ('0ff20800',0x1002,0x100c),
    ('aff20800',0x1000,0xffc), ('aff20800',0x1002,0xffc),
    ('aff20800',0,0xfffffffc),
])
def test_wide_adr_aliases_keep_exact_address_references(raw,address,target):
    row=decode(bytes.fromhex(raw),address,'thumb',32)
    assert row['references']==[{'operand_index':2,'role':'address','target':target,'width':4}]
    assert row['data_refs']==[target] and row['literals']==[]
    assert row['bytes']==raw and row['flow']=='next'


def test_cortex_profile_declares_supported_vector_layout(tmp_path):
    with create(tmp_path) as p:
        info=p.information()['cortex_m']
        assert info['vector_layout']=='armv7-m'
        assert any('Armv7-M' in a for a in info['assumptions'])


@pytest.mark.parametrize('raw,width',[('80ed000a',4),('80ed000b',8)])
def test_vfp_store_width_keeps_unknown_register_address(raw,width):
    fact=instruction_memory_accesses(bytes.fromhex(raw),0x1000,'thumb',32)[0]
    assert fact['width']==width and fact['may_write'] and not fact['may_read']
    assert fact['concrete_target'] is None and fact['unresolved_reasons']


def test_external_storage_keeps_cortex_payloads_outside_sqlite(tmp_path):
    from fdisbull.target_storage import reference
    with create(tmp_path) as p:
        p.analyze()
        assert p.storage_info()['embedded_payload_columns']==[]
        database=p.path
    with sqlite3.connect(database) as raw:
        assert reference(raw.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])
        assert all(reference(r[0]) for r in raw.execute('SELECT data FROM regions'))
        assert all(reference(r[0]) for r in raw.execute('SELECT bytes FROM instructions'))


def test_missing_store_readback_and_exact_reset_child_rebinding(tmp_path,monkeypatch):
    source=firmware(tmp_path,'08bf704701207047')
    original=source.read_bytes();database=tmp_path/'binding.fdb'
    with Project.create(database,source,profile='cortex-m',base=BASE,vector_count=16,entry=BASE+64) as p:
        p.analyze();p.annotate(BASE+64,'retained_startup',kind='name',author='test')
        assert 'entry' not in p.source_info()['loader_options']
        child=p.patch(BASE+4,struct.pack('<I',BASE+97).hex())['version'];p.analyze(version=child)
    source.rename(tmp_path/'parent-exact.bin')
    patched=bytearray(original);struct.pack_into('<I',patched,4,BASE+97)
    child_source=tmp_path/'child-exact.bin';child_source.write_bytes(patched)
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'restored-objects'))
    with Project(database) as p:
        assert p.status(version=child)['entry']==hex(BASE+96)
        rows=p.disassembly(version=1)
        assert not rows['byte_cache_available'] and rows['instructions'][0]['name']=='retained_startup'
        assert rows['instructions'][1]['predicate']
        for operation in (lambda:p.analyze(version=1),lambda:p.patch(BASE+64,'00bf',version=1)):
            with pytest.raises(ValueError,match='[Oo]bject|[Ss]ource|[Pp]rivate'):
                operation()
        invoke('render',dict(project=str(database),output=str(tmp_path/'missing-store.png'),version=1,format='png'))
        assert p.source_candidate(tmp_path/'parent-exact.bin',version=1)['exact_match']
        assert p.bind_source(tmp_path/'parent-exact.bin',version=1)['attached']
        assert p.source_candidate(child_source,version=child)['exact_match']
        assert p.bind_source(child_source,version=child)['attached']
        assert p.source_info(version=1)['verified'] and p.source_info(version=child)['verified']
    with Project(database) as p:
        assert p.disassembly(version=1)['instructions'][0]['bytes']=='08bf'
        assert p.disassembly(version=child)['instructions'][0]['bytes']=='7047'
        assert p.status(version=1)['entry']==hex(BASE+64)
        assert p.status(version=child)['entry']==hex(BASE+96)
