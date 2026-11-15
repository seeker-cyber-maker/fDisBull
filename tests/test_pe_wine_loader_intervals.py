"""Typed-step regressions and qualified immutable native caller intervals.

FDISBULL_WINE_LOADER_INTERVAL_PACKETS points to private reviewed packet paths;
no Wine binaries or private native receipts are checked into this repository.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import capstone
import pytest

z=pytest.importorskip('z3')
pytest.importorskip('lief')

from fdisbull._wine_loader_step import typed_loader_step
from fdisbull.pe_wine_loader_intervals import (
    build_wine_loader_interval_contract, expand_wine_loader_interval,
    validate_wine_loader_interval)


@pytest.mark.parametrize('code,expected',[
    ('b8ffffffff',0xffffffff),             # EAX clears the old high half.
    ('66b8ffff',0x112233445566ffff),       # AX preserves the other bits.
    ('b4ff',0x112233445566ff88),           # AH changes only bits8..15.
])
def test_shared_typed_register_views_keep_architectural_width(code,expected):
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    ins=next(decoder.disasm(bytes.fromhex(code),0x1000));regs={'rax':z.BitVecVal(0x1122334455667788,64)}
    def forbidden(*args):raise AssertionError('This instruction has no memory/control/opaque effects')
    flags,undefined,pc=typed_loader_step(ins,z=z,registers=regs,flags=z.BitVecVal(0x202,32),undefined=0,
        teb=0,access=forbidden,simplify=z.simplify,fresh_af=forbidden,opaque_store=forbidden,
        on_call=forbidden,on_return=forbidden,on_branch=forbidden,native_flags=0x202)
    assert z.simplify(regs['rax']).as_long()==expected
    assert flags.as_long()==0x202 and undefined==0 and pc==0x1000+len(ins.bytes)


def test_caller_profile_refuses_floating_stores_before_memory_effects():
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    ins=next(decoder.disasm(bytes.fromhex('0f29742420'),0x1000)) # MOVAPS[rsp+20],xmm6
    def reject_opaque(width):raise ValueError('Caller intervals do not admit FP/vector stores')
    def forbidden(*args):raise AssertionError('No opaque memory store may occur')
    with pytest.raises(ValueError,match='FP/vector'):
        typed_loader_step(ins,z=z,registers={'rsp':z.BitVecVal(0x2000,64)},flags=z.BitVecVal(0x202,32),
            undefined=0,teb=0,access=forbidden,simplify=z.simplify,fresh_af=forbidden,
            opaque_store=reject_opaque,on_call=forbidden,on_return=forbidden,on_branch=forbidden,native_flags=0x202)


def test_shared_word_compare_uses_sixteen_bit_sign_and_carry():
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    ins=next(decoder.disasm(bytes.fromhex('6683f800'),0x1000)) # CMP AX,0
    value=z.BitVec('arbitrary_upper_rax',64);regs={'rax':value}
    def forbidden(*args):raise AssertionError('CMP has no memory/control/opaque effects')
    flags,undefined,_=typed_loader_step(ins,z=z,registers=regs,flags=z.BitVecVal(0x202,32),undefined=0,
        teb=0,access=forbidden,simplify=z.simplify,fresh_af=lambda:z.Bool('unused_cmp_af'),
        opaque_store=forbidden,on_call=forbidden,on_return=forbidden,on_branch=forbidden,native_flags=0x202)
    solver=z.Solver();solver.add(z.Extract(15,0,value)==0xffff)
    # FFFF-0 is negative at width16, with even low-byte parity, no carry or
    # overflow, no zero, and no auxiliary borrow. High48 bits are irrelevant.
    expected=(0x202&~0x8d5)|0x84
    solver.add(z.Or(regs['rax']!=value,flags!=expected))
    assert solver.check()==z.unsat and undefined==0


@pytest.fixture(scope='module')
def packets():
    configured=os.environ.get('FDISBULL_WINE_LOADER_INTERVAL_PACKETS')
    if not configured:pytest.skip('Qualified immutable native Wine caller interval packets are not configured')
    rows=json.loads(Path(configured).read_text());result={}
    for row in rows:
        raw=Path(row['interval_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['interval_sha256']
        loader=Path(row['loader_source_path']).read_bytes();subject=Path(row['subject_source_path']).read_bytes()
        interval=json.loads(raw)
        contract=(json.loads(Path(row['contract_path']).read_text())if row.get('contract_path')else
                  build_wine_loader_interval_contract(interval,loader_source=loader,subject_source=subject))
        result[row['role']]={'interval':interval,'contract':contract,'loader':loader,'subject':subject}
    assert set(result)=={'attach_success_tail','detach_selection_prefix'}
    return result


@pytest.mark.parametrize('role',['attach_success_tail','detach_selection_prefix'])
def test_actual_source_bound_caller_fragment_proves_full_transfer(packets,role):
    p=packets[role];interval,contract=p['interval'],p['contract'];frozen=deepcopy((interval,contract))
    proof=validate_wine_loader_interval(interval,contract=contract,loader_source=p['loader'],timeout_ms=30000)
    assert proof['status']=='proved_for_observed_wine_loader_interval',proof
    assert proof['checks']['path_cover']=='complete'
    assert proof['checks']['instructions']==len(interval['steps'])
    assert len(proof['transfer']['protected_memory'])>=381
    assert bool(proof['transfer']['pending_call'])==(role=='detach_selection_prefix')
    assert expand_wine_loader_interval(proof,interval,contract)=={'interval':interval,'contract':contract}
    assert (interval,contract)==frozen
    assert build_wine_loader_interval_contract(interval,loader_source=p['loader'],subject_source=p['subject'])==contract


def _replace_byte(rows,address,value):
    for row in rows:
        start=int(row['address'],16);raw=bytearray.fromhex(row['hex'])
        if start<=address<start+len(raw):
            raw[address-start]=value;row['hex']=raw.hex();return
    raise AssertionError('Mutation must affect a retained native byte')


@pytest.mark.parametrize('problem',['source','overlay','read','context','link','metadata','epoch','alias','teb'])
def test_actual_caller_receipt_and_source_mutations_fail_closed(packets,problem):
    p=packets['detach_selection_prefix'];interval,contract=deepcopy((p['interval'],p['contract']));loader=p['loader']
    if problem=='source':loader=bytes([loader[0]^1])+loader[1:]
    elif problem=='overlay':
        loader+=b'nonexecuted overlay changed';contract['loader_source_sha256']=hashlib.sha256(loader).hexdigest()
    elif problem=='read':
        step=next(s for s in interval['steps']if any(a['kind']=='read'for a in s['accesses']))
        step['accesses'].pop(next(i for i,a in enumerate(step['accesses'])if a['kind']=='read'))
    elif problem=='context':interval['steps'][2]['event']['registers']['general']['r11']='0x1234'
    elif problem=='link':
        a=int(contract['addresses']['init_order_head'],16)+8
        _replace_byte(interval['entry_memory'],a,0)
    elif problem=='metadata':
        a=int(contract['addresses']['modref'],16)+0x6a
        original=next(bytes.fromhex(r['hex'])[a-int(r['address'],16)]for r in interval['entry_memory']if int(r['address'],16)<=a<int(r['address'],16)+len(r['hex'])//2)
        _replace_byte(interval['entry_memory'],a,original&~8) # clear PROCESS_ATTACHED
    elif problem=='epoch':interval['code_versions']=[]
    elif problem=='alias':
        # Protect a real stack write destination. Matching old/final samples
        # can never substitute for the required universal disjoint frame.
        a=int(interval['entry']['general']['rsp'],16)-8
        interval['protected_ranges'].append({'role':'sample-equal-stack-data','address':hex(a),'length':8})
        memory={int(r['address'],16)+i:b for r in interval['entry_memory']for i,b in enumerate(bytes.fromhex(r['hex']))}
        for step in interval['steps']:
            step['protected_before'].append({'role':'sample-equal-stack-data','address':hex(a),
                'hex':bytes(memory[a+i]for i in range(8)).hex()})
            for row in step['accesses']:
                for i,b in enumerate(bytes.fromhex(row['after_hex'])):memory[int(row['address'],16)+i]=b
            step['protected_after'].append({'role':'sample-equal-stack-data','address':hex(a),
                'hex':bytes(memory[a+i]for i in range(8)).hex()})
    elif problem=='teb':interval['segment_binding']['teb']='0x12340000'
    proof=validate_wine_loader_interval(interval,contract=contract,loader_source=loader,timeout_ms=30000)
    assert proof['status']=='unknown',proof


def test_builder_refuses_source_overlay_or_truncated_coff(packets):
    p=packets['attach_success_tail']
    with pytest.raises(ValueError):
        build_wine_loader_interval_contract(p['interval'],loader_source=p['loader']+b'overlay',subject_source=p['subject'])
    with pytest.raises(ValueError):
        build_wine_loader_interval_contract(p['interval'],loader_source=b'MZ',subject_source=p['subject'])
