"""Authored AGI fragments with independent finite state expectations."""
from dataclasses import replace

import pytest

from fdisbull.agi import load_logic
from fdisbull.agi_lift import lift_logic
from fdisbull.interaction_il import execute_il
from test_agi import fixture


def loaded(tmp_path, code):
    log = fixture(tmp_path, bytes.fromhex(code))
    return load_logic(log, tmp_path, 0, profile='2.917')


def test_all_u8_inputs_and_flag_values_against_independent_expected_state(tmp_path):
    resource = loaded(tmp_path, '03052a0c070d0700')
    for original in range(256):
        for flag in (False, True):
            before={'$agi_v5':original, '$agi_f7':flag}
            result=lift_logic(resource,initial_state=before)
            expected={'$agi_v5':42, '$agi_f7':False}
            for role in ('udl','uil'):
                execution=execute_il(result[role])
                assert execution['complete'] and execution['state']==expected
                assert execution['visited']==['agi_0000','agi_0003','agi_0005']
            assert result['return_boundary']['offset']==7
            assert result['return_boundary']['continuation']=='unknown'
            assert result['qualification']=='state_projection_only' and not result['runtime_execution']


def test_order_and_source_evidence_and_snapshot(tmp_path):
    resource=loaded(tmp_path,'0301010301020d090c0900')
    result=lift_logic(resource,initial_state={'$agi_v1':255,'$agi_f9':False})
    assert [x['value'] for x in result['uil']['body']]==[1,2,False,True]
    assert execute_il(result['uil'])['state']=={'$agi_v1':2,'$agi_f9':True}
    evidence=result['udl']['evidence']
    assert evidence['agi_0003']['range']==[5,8]  # The hash names the whole payload, including its two-byte code length.
    assert evidence['agi_0003']['code_range']==[3,6]
    assert evidence['agi_0003']['sha256']==resource.resource_sha256
    assert evidence['agi_0003']['volume_offset']==resource.code_offset+3
    assert evidence['agi_000a']['instruction_bytes']=='00'
    assert result['udl']['role']=='udl' and result['uil']['role']=='uil'
    (tmp_path/'VOL.0').write_bytes(b'changed')
    assert execute_il(lift_logic(resource,initial_state={'$agi_v1':0,'$agi_f9':True})['uil'])['state']=={'$agi_v1':2,'$agi_f9':True}


def test_every_encoded_u8_constant_and_overwriting_write(tmp_path):
    for constant in range(256):
        resource = loaded(tmp_path, bytes([3, 4, constant, 0]).hex())
        doc = lift_logic(resource, initial_state={'$agi_v4': 255 - constant})['uil']
        assert execute_il(doc)['state'] == {'$agi_v4': constant}


@pytest.mark.parametrize('code,match', [('aa00','unsupported'),('feff7f','unresolved'),
    ('0301','truncated'),('030101','missing final'),('0000','trailing'),('0c','truncated')])
def test_unsupported_and_incomplete_refused(tmp_path,code,match):
    with pytest.raises(ValueError,match=match): lift_logic(loaded(tmp_path,code),initial_state={})


def test_budget_and_exact_typed_witness_required(tmp_path):
    resource=loaded(tmp_path,'0301ff0c0200')
    with pytest.raises(ValueError,match='budget'):lift_logic(resource,initial_state={},max_instructions=2)
    for state in ({}, {'$agi_v1':0,'$agi_f2':True,'$extra':0},
                  {'$agi_v1':True,'$agi_f2':True}, {'$agi_v1':256,'$agi_f2':True},
                  {'$agi_v1':0,'$agi_f2':1}):
        with pytest.raises(ValueError,match='initial_state'):lift_logic(resource,initial_state=state)
    assert lift_logic(resource,initial_state={'$agi_v1':0,'$agi_f2':False})['uil']['body'][0]['value']==255


def test_tampered_or_forged_snapshot_refused(tmp_path):
    r=loaded(tmp_path,'03010100')
    for changed in (replace(r,code=b'\x00'),replace(r,payload=b'\x00'),
                    replace(r,logic=1),replace(r,resource_sha256='0'*64),
                    replace(r,_volume=r._volume+b'x'),replace(r,space='other'),
                    replace(r,code_offset=r.code_offset+1),replace(r,_directory=b'')):
        with pytest.raises(ValueError):lift_logic(changed,initial_state={'$agi_v1':0})


def test_return_only_accepts_empty_state(tmp_path):
    result=lift_logic(loaded(tmp_path,'00'),initial_state={})
    assert result['uil']['body']==[] and execute_il(result['uil'])['state']=={}


def test_variable_and_flag_indices_are_separate_and_byte_limits_retained(tmp_path):
    result=lift_logic(loaded(tmp_path,'0300000301ff0c000dff00'),
                      initial_state={'$agi_v0':255,'$agi_v1':0,'$agi_f0':False,'$agi_f255':True})
    assert execute_il(result['uil'])['state']=={
        '$agi_v0':0,'$agi_v1':255,'$agi_f0':True,'$agi_f255':False}
    # Independent negative control: reversing repeated writes must change result.
    ordered=lift_logic(loaded(tmp_path,'03010103010200'),initial_state={'$agi_v1':0})['uil']
    reverse=dict(ordered,body=list(reversed(ordered['body'])))
    assert execute_il(ordered)['state'] != execute_il(reverse)['state']
