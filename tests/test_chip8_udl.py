"""Independent typed-port and edge fixtures; no semantic execution claim."""
from copy import deepcopy
import pytest

from fdisbull.chip8 import decode
from fdisbull.chip8_udl import describe,validate


def row(word,pc=0x200):return describe(decode(bytes.fromhex(word),pc))
def ports(record,key):return {p['name']:p['type'] for p in record[key]}


@pytest.mark.parametrize('word',[
 '00e0','00ee','1200','2200','3001','4001','5010','6001','7001','8010',
 '8011','8012','8013','8014','8015','8016','8017','801e','9010','a300',
 'b200','c0ff','d015','e09e','e0a1','f007','f00a','f015','f018','f01e',
 'f029','f033','f055','f065'])
def test_each_classic_family_has_typed_unqualified_source_candidate(word):
    fact=decode(bytes.fromhex(word),0x200);record=describe(fact)
    assert record['qualification']=='static-candidate' and record['family']==fact['mnemonic'].upper()
    assert ports(record,'reads')['pc']=='u16' and ports(record,'writes')['pc']=='u16'
    assert validate(fact,record)==record and 'no G3/G4' in record['scope']


def test_vf_alias_order_and_shift_reads_prestate_vy_only():
    logical=row('8f11');assert ports(logical,'reads')['vf']=='u8'
    assert logical['write_order']==['vf','vf','pc']
    shifted=row('82fe');assert ports(shifted,'reads')['vf']=='u8' and 'v2' not in ports(shifted,'reads')
    assert shifted['write_order']==['v2','vf','pc']
    copied=row('8f10');assert copied['write_order']==['vf','pc']
    assert copied['operands']==[{'role':'x','kind':'register','name':'vf','type':'u8'},
                                 {'role':'y','kind':'register','name':'v1','type':'u8'}]
    assert row('afff')['operands']==[{'role':'nnn','kind':'immediate','value':4095,'type':'u12'}]


def test_call_and_return_stack_width_order_and_cleared_popped_slot():
    call=row('2208');ret=row('00ee')
    assert ports(call,'reads')['sp']=='u8' and ports(call,'writes')['stack']=='u16[16]'
    assert call['write_order']==['stack','sp','pc'] and call['effects'][0]['return_pc']==0x202
    assert ret['effects'][0]['clear_popped_slot'] is True
    assert ret['write_order']==['sp','stack','pc'] and 'stack-underflow' in ret['fault']['possible']


def test_memory_widths_fault_guards_self_modification_and_index_updates():
    for word,length in [('f355',4),('ff65',16),('f033',3),('d015',5),('d010',0)]:
        record=row(word);memory=record['memory'][0]
        assert memory['byte_length']==length and memory['base']=='i' and memory['base_type']=='u16'
        assert 'i + byte_length <= 4096' in memory['guard']
        assert 'data-out-of-bounds' in record['fault']['possible']
        assert memory['may_modify_source']==(word in ('f355','f033'))
    assert 'i' in ports(row('f355'),'writes') and 'i' not in ports(row('f033'),'writes')
    assert 'framebuffer' not in ports(row('d010'),'writes') and 'vf' in ports(row('d010'),'writes')


def test_rng_zero_mask_key_zero_wait_and_timer_effects_remain_explicit():
    rng=row('cf00');assert rng['effects'][0]['zero_mask_consumes_draw'] is True
    assert ports(rng,'reads')['rng_state']=='u32' and ports(rng,'writes')['rng_draws']=='u64'
    wait=row('f00a');assert ports(wait,'reads')['key_mask']=='u16'
    assert wait['effects'][0]['outcomes'][0]['retired'] is False
    assert wait['effects'][0]['selection']=='lowest held key including zero'
    assert ports(row('f007'),'reads')['delay_timer']=='u8'
    assert ports(row('f018'),'writes')['sound_timer']=='u8'


def test_skip_keeps_out_of_ram_successors_and_indirect_is_unresolved():
    record=row('3001',0xffe);assert record['control']['successors']==[0x1000,0x1002]
    jump=row('bfff');assert jump['control']['target'] is None and jump['control']['base']==0xfff
    assert ports(jump,'reads')['v0']=='u8'
    assert record['control']['predicate']=={'op':'eq','left':{'state':'v0','type':'u8'},
                                          'right':{'value':1,'type':'u8'}}
    for item in (record,jump,row('1201'),row('00ee')):
        fetch=item['fault']['successor_fetch']
        assert {x['fault'] for x in fetch['conditions']}=={'odd-pc','fetch-out-of-bounds'}
        assert 'already committed' in fetch['preserves']


def test_tampered_word_family_control_or_candidate_is_refused():
    fact=decode(bytes.fromhex('6001'),0x200);record=describe(fact)
    changed=deepcopy(record);changed['writes'][0]['type']='u16'
    with pytest.raises(ValueError):validate(fact,changed)
    for field,value in [('bytes','1200'),('address',0x201),('flow','call'),('size',True)]:
        altered=deepcopy(fact);altered[field]=value
        with pytest.raises(ValueError):describe(altered)


@pytest.mark.parametrize('field,value',[
 ('operands','v0, 0xff'),('text','pretend'),('references',[{'target':0x222}]),
 ('immediates',[{'operand_index':1,'value':False}]),('data_refs',[1]),('extra','untrusted')])
def test_all_cached_decoder_fields_are_checked_without_decoder_calls(field,value,monkeypatch):
    import fdisbull.chip8 as module
    fact=decode(bytes.fromhex('6000'),0x200);record=describe(fact)
    monkeypatch.setattr(module,'decode',lambda *a,**k:(_ for _ in ()).throw(AssertionError('no decoder call')))
    assert validate(fact,record)==record
    changed=deepcopy(fact);changed[field]=value
    with pytest.raises(ValueError):validate(changed,record)
