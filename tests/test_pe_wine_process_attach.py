"""Exact integer SIMD transfer and qualified complete Wine attach proofs."""
import capstone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import pytest

z=pytest.importorskip('z3')

from fdisbull._wine_loader_step import typed_loader_step
from fdisbull.pe_wine_process_attach import (build_wine_process_attach_contract,
    expand_wine_process_attach,validate_wine_process_attach)


def test_integer_simd_constructs_both_list_pointers_without_opaque_values():
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    # MOVQ xmm0,rax; MOVQ xmm1,r8; PUNPCKLQDQ xmm0,xmm1;
    # MOVUPS [rdx],xmm0. Sources and previous full XMM values are arbitrary.
    code=bytes.fromhex('66480f6ec066490f6ec8660f6cc10f1102')
    a,b=z.BitVecs('list_head old_tail',64);old0,old1=z.BitVecs('initial_xmm0 initial_xmm1',128)
    regs={'rax':a,'r8':b,'rdx':z.BitVecVal(0x2000,64)};vectors={'xmm0':old0,'xmm1':old1};writes=[]
    flags=z.BitVec('entry_flags',32)
    def access(kind,address,width,value=None):
        assert kind=='write'and width==16;writes.append((address,value));return z.BitVecVal(0,128)
    def forbidden(*args):raise AssertionError('Pointer construction has no opaque/control effects')
    for ins in decoder.disasm(code,0x1000):
        output,undefined,_=typed_loader_step(ins,z=z,registers=regs,flags=flags,undefined=0,teb=0,
            access=access,simplify=z.simplify,fresh_af=forbidden,opaque_store=forbidden,
            on_call=forbidden,on_return=forbidden,on_branch=forbidden,native_flags=0x202,vectors=vectors)
        assert output.eq(flags)and undefined==0
    assert len(writes)==1
    solver=z.Solver();solver.add(z.Or(vectors['xmm0']!=z.Concat(b,a),vectors['xmm1']!=z.ZeroExt(64,b),
                                     writes[0][0]!=0x2000,writes[0][1]!=z.Concat(b,a)))
    assert solver.check()==z.unsat


def test_exact_simd_profile_never_falls_back_to_opaque_unknown_xmm():
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    ins=next(decoder.disasm(bytes.fromhex('0f1112'),0x1000)) # MOVUPS[rdx],xmm2
    def forbidden(*args):raise AssertionError('An unknown SIMD source must fail before writing')
    with pytest.raises(ValueError,match='XMM'):
        typed_loader_step(ins,z=z,registers={'rdx':z.BitVecVal(0x2000,64)},flags=z.BitVecVal(0x202,32),
            undefined=0,teb=0,access=forbidden,simplify=z.simplify,fresh_af=forbidden,opaque_store=forbidden,
            on_call=forbidden,on_return=forbidden,on_branch=forbidden,native_flags=0x202,
            vectors={'xmm0':z.BitVec('xmm0',128),'xmm1':z.BitVec('xmm1',128)})


@pytest.fixture(scope='module')
def packet():
    configured=os.environ.get('FDISBULL_WINE_PROCESS_ATTACH_PACKETS')
    if not configured:pytest.skip('Qualified immutable native full process_attach packets not configured')
    rows=json.loads(Path(configured).read_text());row=rows[0]if isinstance(rows,list)else rows
    raw=Path(row['capsule_path']).read_bytes();module_raw=Path(row['module_capsule_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['capsule_sha256']
    assert hashlib.sha256(module_raw).hexdigest()==row['module_capsule_sha256']
    capsule,module=json.loads(raw),json.loads(module_raw)
    loader=Path(row['loader_source_path']).read_bytes();subject=Path(row['subject_source_path']).read_bytes()
    contract=(json.loads(Path(row['contract_path']).read_text())if row.get('contract_path')else
              build_wine_process_attach_contract(capsule,loader_source=loader,subject_source=subject,module_capsule=module))
    return {'capsule':capsule,'module':module,'contract':contract,'loader':loader,'subject':subject}


def test_actual_full_leaf_proves_integer_simd_list_append_and_original_ret(packet):
    p=packet;frozen=deepcopy((p['capsule'],p['module'],p['contract']))
    proof=validate_wine_process_attach(p['capsule'],contract=p['contract'],loader_source=p['loader'],module_capsule=p['module'],timeout_ms=60000)
    assert proof['status']=='proved_for_observed_wine_process_attach',proof
    assert proof['checks']['path_cover']=='complete'
    assert proof['checks']['instructions']==len(p['capsule']['steps'])
    assert set(proof['transfer']['vectors'])=={'xmm0','xmm1'}
    assert len(proof['transfer']['protected_memory'])==594
    assert proof['module_contract']['status']=='proved_for_observed_wine_loader_capsule'
    assert expand_wine_process_attach(proof,p['capsule'],p['contract'],p['module'])=={
        'capsule':p['capsule'],'contract':p['contract'],'module_capsule':p['module']}
    assert (p['capsule'],p['module'],p['contract'])==frozen
    assert build_wine_process_attach_contract(p['capsule'],loader_source=p['loader'],subject_source=p['subject'],module_capsule=p['module'])==p['contract']


@pytest.mark.parametrize('problem',['source','module_join','context','dependency','neighbor','missing_read','epoch','simd_store',
    'register_stage','flat_context','runtime_pc','active_layer','layer_generation','native_overlay',
    'inner_register_stage','inner_active_layer','inner_native_overlay','source_version_bool'])
def test_actual_full_leaf_source_receipt_and_simd_mutations_fail_closed(packet,problem):
    p=packet;capsule,module,contract=deepcopy((p['capsule'],p['module'],p['contract']));loader=p['loader']
    if problem=='source':loader=bytes([loader[0]^1])+loader[1:]
    elif problem=='module_join':module['steps'][0]['after']['general']['r11']='0x1234'
    elif problem=='context':capsule['steps'][2]['event']['registers']['general']['r11']='0x1234'
    elif problem=='register_stage':capsule['steps'][0]['event']['observation']['registers_stage']='after-instruction'
    elif problem=='flat_context':capsule['steps'][0]['event']['identity']['context']='machine'
    elif problem=='source_version_bool':capsule['steps'][0]['event']['identity']['source_version']=True
    elif problem=='runtime_pc':capsule['steps'][0]['event']['registers']['rip']='0x1234'
    elif problem=='active_layer':capsule['steps'][0]['event']['active_layers']=[99]
    elif problem=='layer_generation':capsule['steps'][0]['event']['layer_generation']=1
    elif problem=='native_overlay':
        capsule['steps'][0]['event']['native_address']='0x1234'
        capsule['steps'][0]['event']['native_bytes']=capsule['steps'][0]['event']['bytes']
    elif problem.startswith('inner_'):
        event=capsule['steps'][capsule['module_span']['first_step']+5]['event']
        if problem=='inner_register_stage':event['observation']['registers_stage']='after-instruction'
        elif problem=='inner_active_layer':event['active_layers']=[99]
        else:event['native_address']='0x1234';event['native_bytes']=event['bytes']
    elif problem=='dependency':contract['addresses']['node']=hex(int(contract['addresses']['modref'],16)-8)
    elif problem=='neighbor':contract['addresses']['old_tail']=contract['addresses']['init_order_head']
    elif problem=='missing_read':
        step=next(s for s in capsule['steps']if any(a['kind']=='read'for a in s['accesses']))
        step['accesses'].pop(next(i for i,a in enumerate(step['accesses'])if a['kind']=='read'))
    elif problem=='epoch':capsule['code_versions'].pop(1)
    elif problem=='simd_store':
        step=next(s for s in capsule['steps']if s['event']['bytes'].startswith('410f11'))
        row=next(a for a in step['accesses']if a['kind']=='write'and a['width']==16)
        raw=bytes.fromhex(row['after_hex']);row['after_hex']=(raw[8:]+raw[:8]).hex()
    proof=validate_wine_process_attach(capsule,contract=contract,loader_source=loader,module_capsule=module,timeout_ms=60000)
    assert proof['status']=='unknown',proof
    if problem in('register_stage','flat_context','runtime_pc','active_layer','layer_generation','native_overlay','source_version_bool')or problem.startswith('inner_'):
        assert 'identity' in proof['reason'],proof
