from pathlib import Path
import pytest
from fdisbull.agi import inspect_logic
from fdisbull.cli import respond


def fixture(tmp_path, code, *, entry=b'\x00\x00\x03', header_volume=0):
    log=tmp_path/'LOGDIR';log.write_bytes(entry)
    payload=len(code).to_bytes(2,'little')+code+b'\x00\x00\x00'
    (tmp_path/'VOL.0').write_bytes(b'abc'+b'\x12\x34'+bytes([header_volume])+len(payload).to_bytes(2,'little')+payload)
    return log

def inspect(tmp_path,code,**kw):
    log=fixture(tmp_path,code)
    return inspect_logic(log,tmp_path,0,profile='2.917',**kw)

def test_resource_and_conditional_branch_through_processor(tmp_path):
    # if equaln(v1,2), true returns; false skips to a separate return.
    result=inspect(tmp_path,bytes.fromhex('ff010102ff01000000'))
    assert result['resource_offset']==3 and result['code_offset']==10
    assert result['complete'] and result['code_length']==9
    first=result['instructions'][0]
    assert first['mnemonic']=='if' and [(e['kind'],e['offset']) for e in first['successors']]==[('true',7),('false',8)]
    assert [i['mnemonic'] for i in result['instructions']]==['if','return','return']

def test_goto_signed_and_unknown_stop_and_budget(tmp_path):
    result=inspect(tmp_path,bytes.fromhex('030101fefaff'))
    assert [i['mnemonic'] for i in result['instructions']]==['assignn','goto']
    assert result['instructions'][1]['successors'][0]['offset']==0
    assert result['complete']
    result=inspect(tmp_path,bytes.fromhex('03010100'),max_instructions=1)
    assert result['budget_reached'] and not result['complete']
    result=inspect(tmp_path,b'\xaa\x00')
    assert result['instructions'][0]['mnemonic']=='unsupported' and not result['complete']

def test_said_operands_and_bad_target(tmp_path):
    result=inspect(tmp_path,bytes.fromhex('ff0e0201000227ff000000'))
    assert result['instructions'][0]['conditions'][0]['operands']==[2,1,0,2,39]
    result=inspect(tmp_path,bytes.fromhex('feff7f'))
    assert result['instructions'][0]['successors'][0]['offset'] is None and not result['complete']

@pytest.mark.parametrize('code',['ff0101','fffcff0000','fe01'])
def test_truncated_or_malformed_never_guessed(tmp_path,code):
    result=inspect(tmp_path,bytes.fromhex(code))
    assert result['errors'] and not result['complete']

def test_directory_and_header_errors(tmp_path):
    log=fixture(tmp_path,b'\x00',entry=b'\xff\xff\xff')
    with pytest.raises(ValueError,match='absent'): inspect_logic(log,tmp_path,0,profile='2.917')
    log=fixture(tmp_path,b'\x00',header_volume=1)
    with pytest.raises(ValueError,match='number mismatch'): inspect_logic(log,tmp_path,0,profile='2.917')
    log.write_bytes(b'\x00')
    with pytest.raises(ValueError,match='LOGDIR'): inspect_logic(log,tmp_path,0,profile='2.917')

def test_public_method_and_explicit_profile(tmp_path):
    log=fixture(tmp_path,b'\x00')
    params={'logdir':str(log),'volume_dir':str(tmp_path),'logic':0,'profile':'2.917'}
    assert respond({'method':'agi-logic','params':params},default_project='unused')['ok']
    params['profile']='2.936'
    assert not respond({'method':'agi-logic','params':params})['ok']

def test_overlapping_branches_are_not_complete(tmp_path):
    # True goes to assignn; false enters its second byte.
    result=inspect(tmp_path,bytes.fromhex('ff0701ff010003010000'))
    assert result['overlapping_instructions'] and not result['complete']

def test_mixed_case_volume_is_accepted(tmp_path):
    log=fixture(tmp_path,b'\x00')
    (tmp_path/'VOL.0').rename(tmp_path/'Vol.0')
    assert inspect_logic(log,tmp_path,0,profile='2.917')['complete']

def test_duplicate_case_volume_is_rejected(tmp_path):
    log=fixture(tmp_path,b'\x00')
    (tmp_path/'VOL.0').rename(tmp_path/'Vol.0')
    (tmp_path/'vol.0').write_bytes((tmp_path/'Vol.0').read_bytes())
    if (tmp_path/'vol.0').samefile(tmp_path/'Vol.0'):
        pytest.skip('duplicate-case fixture requires a case-sensitive filesystem')
    with pytest.raises(ValueError,match='exactly one'): inspect_logic(log,tmp_path,0,profile='2.917')

def test_bounded_inputs_and_empty_bytecode_rejected(tmp_path):
    log=fixture(tmp_path,b'')
    with pytest.raises(ValueError,match='empty logic'): inspect_logic(log,tmp_path,0,profile='2.917')
    log.write_bytes(b'\0'*769)
    with pytest.raises(ValueError,match='LOGDIR size'): inspect_logic(log,tmp_path,0,profile='2.917')
    log=fixture(tmp_path,b'\x00')
    (tmp_path/'VOL.0').write_bytes(b'\0'*(2*1024*1024+1))
    with pytest.raises(ValueError,match='volume exceeds'): inspect_logic(log,tmp_path,0,profile='2.917')


def test_loaded_resource_is_immutable_and_typed_facts_keep_encoding(tmp_path):
    from dataclasses import FrozenInstanceError
    from hashlib import sha256
    from fdisbull.agi import load_logic
    log=fixture(tmp_path, bytes.fromhex('0305f00c070d0700'))
    resource=load_logic(log,tmp_path,0,profile='2.917')
    assert resource.code == bytes.fromhex('0305f00c070d0700')
    assert resource.resource_sha256 == sha256(resource.payload).hexdigest()
    assert resource.code_offset == 10 and resource.resource_offset == 3
    with pytest.raises(FrozenInstanceError): resource.code=b'\0'
    before=resource.provenance();before['logic']=99
    assert resource.provenance()['logic']==0
    rows=inspect_logic(log,tmp_path,0,profile='2.917')['instructions']
    assert rows[0]['bytes']=='0305f0' and rows[0]['operands']==[
        {'kind':'variable','index':5},{'kind':'u8','value':240}]
    assert rows[1]['operands']==[{'kind':'flag','index':7}]
    (tmp_path/'VOL.0').write_bytes(b'changed')
    assert resource.code == bytes.fromhex('0305f00c070d0700')


@pytest.mark.parametrize('opcode,name,second_kind', [(1,'equaln','u8'),(2,'equalv','variable'),
    (3,'lessn','u8'),(4,'lessv','variable'),(5,'greatern','u8'),(6,'greaterv','variable')])
def test_scalar_condition_facts_preserve_raw_and_typed_operands(tmp_path,opcode,name,second_kind):
    result=inspect(tmp_path,bytes([255,opcode,4,9,255,0,0,0]))
    condition=result['instructions'][0]['conditions'][0]
    assert condition['mnemonic']==name and condition['operands']==[4,9]
    assert condition['bytes']==bytes([opcode,4,9]).hex()
    assert condition['typed_operands']==[{'kind':'variable','index':4},
        {'kind':'u8','value':9} if second_kind=='u8' else {'kind':'variable','index':9}]


def test_condition_flags_and_markers_remain_explicit(tmp_path):
    result=inspect(tmp_path,bytes.fromhex('fffc0702fd010103fcff000000'))
    conditions=result['instructions'][0]['conditions']
    assert [x.get('marker') for x in conditions]==['or',None,'not',None,'or']
    assert conditions[1]['mnemonic']=='isset' and conditions[1]['typed_operands']==[{'kind':'flag','index':2}]
    assert conditions[1]['bytes']=='0702'


@pytest.mark.parametrize('code',['fffdfd0701ff000000','fffdff000000','fffc0701ff000000','fffdfc0701fcff000000'])
def test_malformed_boolean_markers_refused(tmp_path,code):
    result=inspect(tmp_path,bytes.fromhex(code))
    assert result['errors'] and not result['complete']


@pytest.mark.parametrize('opcode,name,kind', [(22,'call','logic'),(23,'call.v','variable')])
def test_call_retains_fallthrough_and_unresolved_cross_resource_edge(tmp_path,opcode,name,kind):
    result=inspect(tmp_path,bytes([opcode,5,0]))
    call=result['instructions'][0]
    assert call['mnemonic']==name and call['bytes']==bytes([opcode,5]).hex()
    assert call['operands']==[{'kind':kind,'index':5}]
    assert [(x['kind'],x['offset']) for x in call['successors']]==[('call',None),('fallthrough',2)]
    assert 'binding' in call['successors'][0]['evidence'] and not result['complete']
