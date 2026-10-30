"""Bounded COM16 structural compilation with authored source and data."""
from copy import deepcopy
from hashlib import sha256

import iced_x86 as ix
import pytest

from fdisbull.code_blocks import group_code_backings
from fdisbull.dos_udc_layout import compile_dos_com
from fdisbull.project import Project


ASSUME = dict.fromkeys(('no_code_reads','no_code_writes','no_computed_entries',
                        'address_identity_unobserved','timing_unobserved'), True)


def _input(tmp_path):
    # Wait for fixed byte, compute AX, jump to store and HLT. Table at 182h
    # initially names store port 10dh; all code is authored for this test.
    code = bytes.fromhex('803e80010074f9b80100e90000a28101f4')
    raw = code + bytes(0x80-len(code)) + bytes.fromhex('00000d01')
    path=tmp_path/'authored.com'; path.write_bytes(raw)
    with Project.create(tmp_path/'analysis.fdb',path,image='com') as project:
        project.analyze()
        capsule=project.code_backings(['1000:0100'])
    plan=group_code_backings(capsule)
    data=[{'id':'vars','ip':0x180,'bytes':'00000d01','sha256':sha256(bytes.fromhex('00000d01')).hexdigest()}]
    return capsule,plan,data


def _group(plan, ip):
    return next(b for b in plan['blocks'] if b['entry'].endswith('@'+hex(0x10000+ip)))


def _replacement(group, raw='90b80100'):
    return {'id':'extra-nop','bytes':raw,'sha256':sha256(bytes.fromhex(raw)).hexdigest(),
            'expected_block_revision':group['block_revision'],'qualification':{'status':'unverified'}}


def test_com_replacement_near_transfers_and_table_repair(tmp_path):
    capsule,plan,data=_input(tmp_path)
    compute=_group(plan,0x107); target=_group(plan,0x10d)
    refs=[{'kind':'near-code-pointer','data':'vars','offset':2,'target':target['id'],'expected_hex':'0d01'}]
    result=compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute)},references=refs,assumptions=ASSUME)
    raw=bytes.fromhex(result['bytes']); ports=result['ports']
    assert result['entry_ip']==0x100 and raw[0]==0xe9
    assert ix.Decoder(16,raw[:3],ip=0x100).decode().near_branch_target == ports[result['entry_port']]
    assert raw[0x80:0x82] == bytes(2)
    assert int.from_bytes(raw[0x82:0x84],'little') == ports[target['id']]
    assert result['qualification']=='structural_only' and not result['native_execution']
    assert any(o['implementation']=='extra-nop' for o in result['occurrences'])
    for f in result['fixups']:
        if f['kind'] in ('branch','continuation'):
            b=raw[f['file_offset']:f['file_offset']+len(bytes.fromhex(f['new_hex']))]
            assert ix.Decoder(16,b,ip=f['site_ip']).decode().near_branch_target==f['target_ip']


def test_source_unchanged_and_placement_and_pointer_fail_closed(tmp_path):
    capsule,plan,data=_input(tmp_path); original=deepcopy((capsule,plan,data))
    compute=_group(plan,0x107); target=_group(plan,0x10d)
    ref={'kind':'near-code-pointer','data':'vars','offset':2,'target':target['id'],'expected_hex':'0d01'}
    result=compile_dos_com(capsule,plan,data,references=[ref],assumptions=ASSUME)
    assert (capsule,plan,data)==original
    with pytest.raises(ValueError,match='expected'):compile_dos_com(capsule,plan,data,references=[{**ref,'expected_hex':'0000'}],assumptions=ASSUME)
    with pytest.raises(ValueError,match='overlapping'):compile_dos_com(capsule,plan,data,references=[ref,ref],assumptions=ASSUME)
    with pytest.raises(ValueError,match='code base|collides'):compile_dos_com(capsule,plan,data,code_base=0x180,assumptions=ASSUME)
    with pytest.raises(ValueError,match='revision'):compile_dos_com(capsule,plan,data,replacements={compute['id']:{**_replacement(compute),'expected_block_revision':'0'*64}},assumptions=ASSUME)
    with pytest.raises(ValueError,match='straight-line'):compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,'eb00')},assumptions=ASSUME)
    assert result['data'][0]['file_offset']==0x80


def test_memory_assumptions_and_declared_ranges_fail_closed(tmp_path):
    capsule,plan,data=_input(tmp_path)
    bad=deepcopy(data);bad[0]['ip']=0x190
    with pytest.raises(ValueError,match='not declared fixed data'):compile_dos_com(capsule,plan,bad,assumptions=ASSUME)
    with pytest.raises(ValueError,match='assumptions'):compile_dos_com(capsule,plan,data,assumptions={})
    bad=deepcopy(data);bad[0]['ip']=0x105
    with pytest.raises(ValueError,match='overlaps'):compile_dos_com(capsule,plan,bad,assumptions=ASSUME)


def test_replacement_immediate_pointer_field_validation(tmp_path):
    capsule,plan,data=_input(tmp_path)
    compute=_group(plan,0x107); target=_group(plan,0x10d)
    replacement=_replacement(compute, 'bb0d01')
    replacement['references']=[{'kind':'code-immediate','field_offset':1,
                                'target':target['id'],'expected_hex':'0d01'}]
    result=compile_dos_com(capsule,plan,data,replacements={compute['id']:replacement},assumptions=ASSUME)
    occurrence=next(o for o in result['occurrences'] if o['implementation']=='extra-nop')
    assert int.from_bytes(bytes.fromhex(occurrence['bytes'])[1:3], 'little') == result['ports'][target['id']]
    replacement['references'][0]['field_offset']=0
    with pytest.raises(ValueError,match='native immediate'):
        compile_dos_com(capsule,plan,data,replacements={compute['id']:replacement},assumptions=ASSUME)


def test_large_replacement_uses_near_widened_continuation(tmp_path):
    capsule,plan,data=_input(tmp_path)
    start=_group(plan,0x100);compute=_group(plan,0x107);target=_group(plan,0x10d)
    replacement=_replacement(compute, '90'*140 + 'b80100')
    result=compile_dos_com(capsule,plan,data,replacements={compute['id']:replacement},
                           block_order=[start['id'], target['id'], compute['id']],assumptions=ASSUME)
    f=next(f for f in result['fixups'] if f['kind']=='continuation' and f['target_port']==target['id'])
    assert f['new_hex'].startswith('e9') and abs(f['target_ip']-(f['site_ip']+3))>127
    assert ix.Decoder(16,bytes.fromhex(f['new_hex']),ip=f['site_ip']).decode().near_branch_target == f['target_ip']


@pytest.mark.parametrize('code,reason', [
    ('cd21', 'interrupt'), ('bc0010', 'stack-pointer'), ('8ed8', 'segment'),
    ('a00001', 'fixed data'), ('67a180010000', '32-bit absolute'),
    ('8d1e0001', 'fixed data'),
])
def test_unsupported_replacements_are_refused(tmp_path, code, reason):
    capsule,plan,data=_input(tmp_path); compute=_group(plan,0x107)
    with pytest.raises(ValueError, match=reason):
        compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,code)},assumptions=ASSUME)


def test_register_memory_requires_declared_obligation(tmp_path):
    capsule,plan,data=_input(tmp_path); compute=_group(plan,0x107)
    with pytest.raises(ValueError,match='register memory'):
        compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,'aa')},assumptions=ASSUME)
    result=compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,'aa')},
                           assumptions={**ASSUME,'register_memory_targets_fixed_data':True})
    assert result['register_memory_obligation'] is True


def test_bootstrap_rejects_out_of_range_near_target(tmp_path):
    capsule,plan,data=_input(tmp_path)
    with pytest.raises(ValueError,match='displacement'):
        compile_dos_com(capsule,plan,data,code_base=0x9000,assumptions=ASSUME)


def test_source_instruction_immediate_code_and_data_fixups(tmp_path):
    # Two MOV pointers, a direct jump, then terminal HLT; variables at 180h.
    code=bytes.fromhex('bb8001b80a01eb02 9090 f4')
    source=tmp_path/'pointer.com';source.write_bytes(code+bytes(0x80-len(code))+b'\x55')
    with Project.create(tmp_path/'pointer.fdb',source,image='com') as project:
        project.analyze(); capsule=project.code_backings(['1000:0100'])
    plan=group_code_backings(capsule)
    target=_group(plan,0x10a)
    data=[{'id':'var','ip':0x180,'bytes':'55','sha256':sha256(b'\x55').hexdigest()}]
    atoms={a['address']:a['id'] for a in capsule['blocks']}
    refs=[{'kind':'data-immediate','instruction':atoms['0x10100'],'field_offset':1,
           'target':'var','expected_hex':'8001'},
          {'kind':'code-immediate','instruction':atoms['0x10103'],'field_offset':1,
           'target':target['id'],'expected_hex':'0a01'}]
    result=compile_dos_com(capsule,plan,data,references=refs,assumptions=ASSUME)
    assert [f['kind'] for f in result['fixups']][-2:]==['data-immediate','code-immediate']
    code_fixup=result['fixups'][-1]
    assert int.from_bytes(bytes.fromhex(code_fixup['new_hex']),'little')==result['ports'][target['id']]


def test_overlapping_entry_port_is_remapped_independently(tmp_path):
    source=tmp_path/'overlap.com';source.write_bytes(bytes.fromhex('7401a8aac3'))
    with Project.create(tmp_path/'overlap.fdb',source,image='com') as project:
        project.analyze(); capsule=project.code_backings(['1000:0100','1000:0102','1000:0103'])
    plan=group_code_backings(capsule)
    a,b=_group(plan,0x102),_group(plan,0x103)
    data=[{'id':'destination','ip':0x180,'bytes':'00','sha256':sha256(b'\x00').hexdigest()}]
    with pytest.raises(ValueError,match='explicit boot entry'):
        compile_dos_com(capsule,plan,data,assumptions={**ASSUME,'register_memory_targets_fixed_data':True})
    result=compile_dos_com(capsule,plan,data,entry=a['id'],assumptions={**ASSUME,'register_memory_targets_fixed_data':True})
    assert result['ports'][b['id']] != result['ports'][a['id']] + 1
    assert any(f.get('target_port') == b['id'] and f['target_ip'] == result['ports'][b['id']]
               for f in result['fixups'])


def test_known_external_incoming_edge_refuses_closed_world(tmp_path):
    source=tmp_path/'outside.com';source.write_bytes(bytes.fromhex('90c3'))
    with Project.create(tmp_path/'outside.fdb',source,image='com') as project:
        project.analyze(); capsule=project.code_backings(['1000:0101'])
    plan=group_code_backings(capsule)
    assert any(edge['source'].endswith('@0x10100') for edge in plan['blocks'][0]['incoming'])
    with pytest.raises(ValueError,match='incoming control edge'):
        compile_dos_com(capsule,plan,[],assumptions=ASSUME)


def test_known_immediate_code_pointer_requires_declared_fixup(tmp_path):
    source=tmp_path/'evidence.com';source.write_bytes(bytes.fromhex('b80601eb0190f4'))
    with Project.create(tmp_path/'evidence.fdb',source,image='com') as project:
        project.analyze()
        project.db.execute('INSERT INTO operand_refs VALUES (?,?,?,?,?,?,?)',
                           (1,'x86:16:little:cs=1000',f'{0x10100:016x}',1,'address',f'{0x10106:016x}',2))
        project.db.commit()
        capsule=project.code_backings(['1000:0100'])
    plan=group_code_backings(capsule); target=_group(plan,0x106)
    with pytest.raises(ValueError,match='known source pointer'):
        compile_dos_com(capsule,plan,[],assumptions=ASSUME)
    fix={'kind':'code-immediate','instruction':_group(plan,0x100)['entry'],
         'field_offset':1,'target':target['id'],'expected_hex':'0601'}
    result=compile_dos_com(capsule,plan,[],references=[fix],assumptions=ASSUME)
    item=next(f for f in result['fixups'] if f['kind']=='code-immediate')
    assert int.from_bytes(bytes.fromhex(item['new_hex']),'little')==result['ports'][target['id']]


def test_stored_memory_target_must_match_decoded_field(tmp_path):
    from fdisbull.code_backings import digest
    capsule,_,data=_input(tmp_path)
    atom=capsule['blocks'][0]
    assert atom['references'][0]['role']=='memory'
    atom['references'][0]['target']='0x10181'
    atom['backing_revision']=digest({k:v for k,v in atom.items() if k!='backing_revision'})
    capsule['sha256']=digest({k:v for k,v in capsule.items() if k!='sha256'})
    with pytest.raises(ValueError,match='matching fixed-data native field'):
        compile_dos_com(capsule,group_code_backings(capsule),data,assumptions=ASSUME)


@pytest.mark.parametrize('code', ['0f22c0', '0f01368001'])
def test_real_mode_rejects_privileged_state_changes_without_execution(tmp_path, code):
    capsule,plan,data=_input(tmp_path); compute=_group(plan,0x107)
    with pytest.raises(ValueError,match='privileged instruction'):
        compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,code)},assumptions=ASSUME)


@pytest.mark.parametrize('code', ['fc', 'fd'])
def test_real_mode_accepts_nonprivileged_direction_flags(tmp_path, code):
    capsule,plan,data=_input(tmp_path); compute=_group(plan,0x107)
    result=compile_dos_com(capsule,plan,data,replacements={compute['id']:_replacement(compute,code)},assumptions=ASSUME)
    assert any(item['bytes']==code for item in result['occurrences'])
