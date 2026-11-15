"""Qualified immutable native-evidence checks; no VM is launched here.

Set FDISBULL_WINE_LOADER_CONTRACT_PACKETS to a reviewed external packets.json.
Wine DLLs, private captures and original program payloads stay outside Git.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

pytest.importorskip('z3')
pytest.importorskip('lief')

from fdisbull.pe_wine_loader_contracts import (
    build_wine_loader_contract, expand_wine_loader_contract, validate_wine_loader_capsule)


@pytest.fixture(scope='module')
def packets():
    configured=os.environ.get('FDISBULL_WINE_LOADER_CONTRACT_PACKETS')
    if not configured:
        pytest.skip('Qualified immutable native Wine loader packet inputs are not configured')
    path=Path(configured)
    rows=json.loads(path.read_text())
    assert {row['phase'] for row in rows}=={'attach','detach'}
    result={}
    for row in rows:
        raw=Path(row['capsule_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['capsule_sha256']
        contract=json.loads(Path(row['contract_path']).read_text())
        loader=Path(row['loader_source_path']).read_bytes()
        assert hashlib.sha256(loader).hexdigest()==contract['loader_source_sha256']
        result[row['phase']]={'capsule':json.loads(raw),'contract':contract,'loader':loader,
                             'subject':Path(row['subject_source_path']).read_bytes()}
    return result


@pytest.mark.parametrize('phase',['attach','detach'])
def test_actual_complete_loader_path_proves_generic_dispatch_and_memory_frame(packets,phase):
    inputs=packets[phase];capsule,contract=inputs['capsule'],inputs['contract']
    frozen=deepcopy((capsule,contract))
    proof=validate_wine_loader_capsule(capsule,contract=contract,loader_source=inputs['loader'],timeout_ms=30000)
    assert proof['status']=='proved_for_observed_wine_loader_capsule',proof
    assert proof['checks']['instructions']==len(capsule['steps'])
    assert proof['checks']['path_cover']=='complete'
    assert proof['checks']['directory_getter'].startswith('Actual complete')
    assert proof['code_versions']==capsule['code_versions']
    assert [p['phase'] for p in proof['callback_contracts']]==['tls-'+phase,'dll-'+phase]
    assert expand_wine_loader_contract(proof,capsule,contract)=={'capsule':capsule,'contract':contract}
    assert (capsule,contract)==frozen


def test_builder_requires_an_explicit_proved_detach_predecessor(packets):
    inputs=packets['detach']
    with pytest.raises(ValueError,match='previously proved'):
        build_wine_loader_contract(inputs['capsule'],loader_source=inputs['loader'],subject_source=inputs['subject'])
    contract=inputs['contract']
    rebuilt=build_wine_loader_contract(inputs['capsule'],loader_source=inputs['loader'],subject_source=inputs['subject'],
        entry_code=contract['entry_code'],entry_globals=contract['entry_globals'])
    assert rebuilt==contract


@pytest.mark.parametrize('problem',['source_bytes','source_overlay','target','order','argument','missing_rmw',
                                   'stale_epoch','protected_write_restore','context','teb_owner','gs_binding','code_role'])
def test_actual_native_evidence_mutations_fail_closed(packets,problem):
    inputs=packets['attach'];capsule,contract=deepcopy((inputs['capsule'],inputs['contract']));loader=inputs['loader']
    if problem=='source_bytes':
        loader=bytes([loader[0]^1])+loader[1:]
    elif problem=='source_overlay':
        loader+=b'changed nonexecuted source overlay'
        contract['loader_source_sha256']=hashlib.sha256(loader).hexdigest()
    elif problem=='target':
        row=contract['callback_array'];raw=bytearray.fromhex(row['hex'])
        raw[:8]=int(contract['subject_symbols']['dll_entry'],16).to_bytes(8,'little')
        row['hex']=raw.hex();row['sha256']=hashlib.sha256(raw).hexdigest()
    elif problem=='order':
        capsule['callback_spans'].reverse();capsule['callbacks'].reverse()
    elif problem=='argument':
        first=capsule['callback_spans'][0]['first_step']
        capsule['steps'][first-1]['after']['general']['rcx']='0x1234'
    elif problem=='missing_rmw':
        step=next(s for s in capsule['steps'] if any(a['kind']=='read' and any(b['kind']=='write' and
            a['address']==b['address'] for b in s['accesses']) for a in s['accesses']))
        step['accesses'].pop(next(i for i,a in enumerate(step['accesses']) if a['kind']=='read'))
    elif problem=='stale_epoch':
        assert len(capsule['code_versions'])==3
        capsule['code_versions'].pop(1)
    elif problem=='protected_write_restore':
        # Actual Wine writes and restores the TEB exception-chain word. A
        # final sample equal to its entry value must not imply noninterference.
        teb=int(capsule['thread_info']['teb'],16)
        cells=lambda rows:{int(r['address'],16)+k:b for r in rows for k,b in enumerate(bytes.fromhex(r['hex']))}
        before,after=cells(capsule['entry_memory']),cells(capsule['exit_memory'])
        assert all(before[teb+k]==after[teb+k] for k in range(8))
        assert any(a['kind']=='write' and int(a['address'],16)==teb for s in capsule['steps'] for a in s['accesses'])
        capsule['protected_ranges'].append({'role':'transient-chain-data','address':hex(teb),'length':8})
        capsule['steps'][0]['protected_before'].append({'role':'transient-chain-data','address':hex(teb),
            'hex':bytes(before[teb+k] for k in range(8)).hex()})
    elif problem=='context':
        capsule['steps'][10]['event']['registers']['general']['r11']='0xdeadbeef'
    elif problem=='teb_owner':
        capsule['thread_info']['thread']+=1
    elif problem=='gs_binding':
        capsule['segment_binding']['teb']='0x12340000'
    elif problem=='code_role':
        for row in capsule['protected_ranges']:
            if row['role']=='dll-code':row['role']='dll-bytes'
        for step in capsule['steps']:
            for field in ('protected_before','protected_after'):
                for row in step[field]:
                    if row['role']=='dll-code':row['role']='dll-bytes'
    proof=validate_wine_loader_capsule(capsule,contract=contract,loader_source=loader,timeout_ms=30000)
    assert proof['status']=='unknown',proof


def test_builder_rejects_changed_source_overlay_and_truncated_pe_metadata(packets):
    inputs=packets['attach']
    with pytest.raises(ValueError,match='frozen source identity'):
        build_wine_loader_contract(inputs['capsule'],loader_source=inputs['loader']+b'overlay',subject_source=inputs['subject'])
    with pytest.raises(ValueError):
        build_wine_loader_contract(inputs['capsule'],loader_source=b'MZ',subject_source=inputs['subject'])
