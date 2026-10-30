import copy
import hashlib
import json

import iced_x86 as ix
import pytest

from fdisbull.code_layout import compile_code_backings
from fdisbull.decoder import decode

ASSUMPTIONS = {name: True for name in ('no_code_reads', 'no_code_writes', 'no_computed_entries', 'address_identity_unobserved', 'timing_unobserved')}
SOURCE = {'arch': 'x86', 'bits': 16, 'version': 1, 'source_sha256': 'a'*64, 'version_sha256': 'b'*64}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def block(ident, address, raw, edges=(), bits=16):
    data = bytes.fromhex(raw); facts = decode(data, address, 'x86', bits); ctx = f'x86:{bits}:little'
    return {'id': ident, 'address': hex(address), 'context': ctx, 'bytes': raw,
            'sha256': hashlib.sha256(data).hexdigest(), 'flow': facts['flow'],
            'instruction': {k: facts[k] for k in ('mnemonic', 'operands', 'size')},
            'exits': [{'kind': k, 'target': v, 'evidence': 'authored', 'provenance': {}} for k, v in edges],
            'references': facts['references'], 'provenance': {'address': hex(address), 'size': len(data),
              'source_sha256': SOURCE['source_sha256'], 'version_sha256': SOURCE['version_sha256'], 'context': ctx}}


def doc(blocks, entries, bits=16):
    d = {'format': 'fdisbull-code-backings-1', 'source': {**SOURCE, 'bits': bits}, 'entries': entries,
         'blocks': blocks, 'complete': True, 'unresolved': []}; d['sha256'] = digest(d); return d


def reseal(d):
    d['sha256'] = digest({k:v for k,v in d.items() if k != 'sha256'}); return d


def overlap():
    return doc([block('A',0x1000,'a8aa',[('fallthrough','J')]),
                block('B',0x1001,'aa',[('fallthrough','J')]), block('J',0x1002,'c3')],['A','B'])


def test_overlap_reordered_with_explicit_flag_neutral_glue_and_ports():
    d=overlap(); r=compile_code_backings(d, order=['B','A','J'], assumptions=ASSUMPTIONS,
        entry_references=[{'id':'table','kind':'table','target':'B','width':2}], base=0x200)
    b=bytes.fromhex(r['bytes']); assert r['entries']=={'A':0x204,'B':0x200}
    assert b[:1]==b'\xaa' and b[4:6]==b'\xa8\xaa'
    assert b[1]==b[6]==0xe9 and r['entry_references'][0]['bytes']=='0002'
    dec=ix.Decoder(16,b,ip=0x200); steps=list(dec)
    assert [x.flow_control for x in steps] == [ix.FlowControl.NEXT,ix.FlowControl.UNCONDITIONAL_BRANCH,ix.FlowControl.NEXT,ix.FlowControl.UNCONDITIONAL_BRANCH,ix.FlowControl.RETURN]
    assert steps[1].near_branch_target == steps[3].near_branch_target == 0x209
    assert steps[1].rflags_written == steps[3].rflags_written == 0
    assert r['qualification']=='structural_only' and len(r['occurrences'])==3
    assert r['source_coverage_bytes']==3 and sum(o['source_size'] for o in r['occurrences'])==4
    assert {o['source_address'] for o in r['occurrences']} == {'0x1000','0x1001','0x1002'}


def test_conditional_widen_and_target_fixups_across_short_range():
    blocks=[block('C',0x1000,'7402',[('branch','T'),('fallthrough','F')]),
            block('F',0x1002,'90',[('fallthrough','I')]),block('I',0x1003,'90',[('fallthrough','T')]),block('T',0x1004,'c3')]
    # Extra graph nodes need not be reachable from C but each next has an explicit exit.
    for i in range(45): blocks.append(block(f'X{i}',0x2000+i,'c3'))
    d=doc(blocks,['C','T']);order=['C','F','I']+[f'X{i}' for i in range(45)]+['T']
    # Three-byte RET imm16 creates 135 filler bytes without an implicit exit.
    for i in range(45): blocks[4+i]=block(f'X{i}',0x2000+i*3,'c20000')
    d=doc(blocks,['C','T']);r=compile_code_backings(d,order=order,assumptions=ASSUMPTIONS)
    out=bytes.fromhex(r['bytes']);assert out[:2]==b'\x0f\x84'; ins=ix.Decoder(16,out,ip=0).decode()
    assert ins.near_branch_target==r['entries']['T'] and ins.near_branch_target>127
    assert out[4]==0xe9


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(complete=False), lambda d:d.update(unresolved=['unknown']),
    lambda d:d['blocks'][0].update(bytes='a8'), lambda d:d['blocks'][0].update(flow='return'),
    lambda d:d['blocks'][0]['exits'][0].update(target='B'), lambda d:d['blocks'][1]['exits'][0].update(target='missing'),
    lambda d:d['blocks'][1].update(context='x86:32:little'), lambda d:d['blocks'][1].update(bits=32),
    lambda d:d['blocks'][1].update(sha256='0'*64),
])
def test_invalid_graph_is_rejected(mutate):
    d=overlap(); mutate(d)
    with pytest.raises(ValueError): compile_code_backings(reseal(d),assumptions=ASSUMPTIONS)


def test_digest_assumptions_order_bounds_and_reference_rejections():
    d=overlap();d['entries'].append('J')
    with pytest.raises(ValueError,match='digest'): compile_code_backings(d,assumptions=ASSUMPTIONS)
    d=overlap()
    for kwargs in ({}, {'assumptions':{**ASSUMPTIONS,'no_code_reads':False}}, {'assumptions':ASSUMPTIONS,'order':['A','A','J']}, {'assumptions':ASSUMPTIONS,'base':65534}, {'assumptions':ASSUMPTIONS,'entry_references':[{'id':'p','kind':'pointer','target':'unknown','width':2}]}):
        with pytest.raises(ValueError): compile_code_backings(d,**kwargs)


def test_unsupported_call_loop_and_code_as_data():
    for b in [block('x',0x1000,'e80000'),block('x',0x1000,'e2fe',[('branch','x'),('fallthrough','x')]),block('x',0x1000,'a10010',[('fallthrough','r')])]:
        d=doc([b,block('r',0x1003,'c3')],['x'])
        with pytest.raises(ValueError):compile_code_backings(d,assumptions=ASSUMPTIONS)


def test_32bit_short_jump_widens_and_pointer_width_checks():
    d=doc([block('A',0x1000,'eb01',[('branch','T')],bits=32),
           block('T',0x1003,'c3',bits=32)],['A','T'],bits=32)
    r=compile_code_backings(d,base=0x10000,order=['T','A'],assumptions=ASSUMPTIONS,
          entry_references=[{'id':'pointer','kind':'pointer','target':'T','width':4}])
    assert bytes.fromhex(r['bytes'])[1] == 0xe9
    assert r['entry_references'][0]['bytes']=='00000100'
    with pytest.raises(ValueError,match='reference'):
        compile_code_backings(d,base=0x10000,assumptions=ASSUMPTIONS,
          entry_references=[{'id':'pointer','kind':'pointer','target':'T','width':2}])


def test_real_mode_context_uses_ip_not_physical_low_bits():
    ctx='x86:16:little:cs=1234';segment=0x12340
    def dos_block(name,ip,code,edges=()):
        b=block(name,ip,code,edges);b['address']=hex(segment+ip);b['context']=ctx
        b['provenance'].update(address=hex(segment+ip),context=ctx);return b
    d=doc([dos_block('A',0x100,'eb01',[('branch','J')]),dos_block('J',0x103,'c3')],['A','J'])
    r=compile_code_backings(d,assumptions=ASSUMPTIONS);assert bytes.fromhex(r['bytes'])[0]==0xe9
    d['blocks'][0]['exits'][0]['target']='A'
    with pytest.raises(ValueError,match='edge target'):compile_code_backings(reseal(d),assumptions=ASSUMPTIONS)


def test_reject_absolute_reference_overlapping_any_source_byte():
    b=block('M',0x2000,'a1ff0f',[('fallthrough','R')]);r=block('R',0x2003,'c3')
    # A separate entry has a byte at 0x1000, the second byte of the word load.
    d=doc([b,r,block('S',0x1000,'c3')],['M','S'])
    with pytest.raises(ValueError,match='aliases source code'):compile_code_backings(d,assumptions=ASSUMPTIONS)


def test_real_project_capture_compiles_overlap_and_detects_tampered_exit(tmp_path):
    from fdisbull.project import Project
    source=tmp_path/'fixture.bin';source.write_bytes(bytes.fromhex('7401a8aac3'))
    with Project.create(tmp_path/'fixture.fdb',source,arch='x86',bits=32,base=0x1000) as project:
        project.analyze()
        captured=project.code_backings([0x1000,0x1002,0x1003])
        assert captured['complete'] and captured['coverage']['shared_occurrence_bytes']==1
        result=compile_code_backings(captured,assumptions=ASSUMPTIONS)
        assert result['qualification']=='structural_only' and result['source_coverage_bytes']==5
        assert len(result['entries'])==3
        changed=copy.deepcopy(captured)
        branch=next(b for b in changed['blocks'] if b['flow']=='conditional')
        branch['exits'][0]['target']=branch['exits'][1]['target']
        with pytest.raises(ValueError):compile_code_backings(reseal(changed),assumptions=ASSUMPTIONS)


def test_actual_16bit_project_capture_carries_backing_revisions_and_glue(tmp_path):
    from fdisbull.project import Project
    source=tmp_path/'fixture16.bin';source.write_bytes(bytes.fromhex('7401a8aac3'))
    with Project.create(tmp_path/'fixture16.fdb',source,arch='x86',bits=16,base=0x1000) as project:
        project.analyze()
        captured=project.code_backings([0x1002,0x1003])
        result=compile_code_backings(captured,base=0x200,assumptions=ASSUMPTIONS)
        assert result['bytes']=='a8aae90400aae90000c3'
        assert [g['address'] for g in result['glue']]==['0x202','0x206']
        assert [g['target_address'] for g in result['glue']]==['0x209','0x209']
        assert {o['backing_revision'] for o in result['occurrences']}=={b['backing_revision'] for b in captured['blocks']}


def test_output_provenance_is_a_snapshot_when_caller_mutates_input():
    source=overlap()
    source['blocks'][0]['provenance']['byte_roles']=['opcode','immediate']
    reseal(source)
    result=compile_code_backings(source,assumptions=ASSUMPTIONS)
    before=copy.deepcopy(result)
    source['blocks'][0]['provenance']['byte_roles'][1]='changed'
    assert result==before
    assert result['sha256']==digest({k:v for k,v in result.items() if k!='sha256'})
