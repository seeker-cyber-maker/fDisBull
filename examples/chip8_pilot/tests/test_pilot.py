import hashlib
import json
from pathlib import Path

import pytest
import os

from chip8lab.decoder import decode_table, decode_branches, validate_rules, PROFILES
from chip8lab.vm import Machine, Quirks, Trap
from chip8lab.registry import build_index,inspect_index
from chip8lab.gaps import run_gap_probes
from chip8lab.pilot import (CORPUS_DIR,scan_space, execute_single_word_scan, check_variant_probes, fuzz_short_programs,
                            corpus_metrics, ddmin, mutation_sanity, instruction_candidate,run_rom,PROJECT)


def one(word, v=None, i=0x300, memory=None, quirks=None, stack=None, keys=None):
    machine=Machine(quirks=quirks or Quirks())
    machine.memory[0x200:0x202]=word.to_bytes(2,'big')
    machine.v[:]=[0]*16
    if v:
        for k,val in v.items():machine.v[k]=val
    machine.i=i
    if memory is not None:machine.memory[i:i+len(memory)]=memory
    if stack: machine.stack=list(stack)
    machine.keys=set(keys or ())
    return machine


def test_decoder_exhaustive_16bit_and_patterns():
    validate_rules()
    result=scan_space()
    assert set(result)==set(PROFILES)
    assert all(data['words']==65536 and not data['decoder_disagreements'] for data in result.values())
    assert result['chip8']['tier_counts']=={'classic':43954,'invalid':17488,'legacy':4094}
    for opcode,family in [(0x00e0,'CLS'),(0x00ee,'RET'),(0x00ff,'SYS'),(0x5010,'SE_VX_VY'),
                          (0x5011,'INVALID'),(0x9120,'SNE_VX_VY'),(0x9121,'INVALID'),
                          (0x8f2e,'SHL'),(0x8f28,'INVALID'),(0xe09e,'SKP'),(0xe09f,'INVALID'),
                          (0xf033,'BCD')]:
        assert decode_table(opcode).family==family
        assert decode_table(opcode)==decode_branches(opcode)
    assert decode_table(0xf000,'xo').family=='LONG_I'
    assert decode_table(0xf000,'xo').size==4
    assert decode_table(0x00ff,'schip').family=='HIGH_RES'
    assert decode_table(0x00ff,'chip8').tier=='legacy'


def test_all_word_single_step_and_wait():
    r=execute_single_word_scan()
    assert r['words']==65536
    assert sum(r['status_counts'].values())==65536
    assert r['status_counts'].get('waiting')==16  # FX0A across all registers
    assert r['unexpected_runtime_traps']==[]
    assert r['status_counts']['executed']==43938


def test_directed_quirks_are_marked_not_false_anomalies():
    r=check_variant_probes()
    assert len(r)==5 and all(p['diverges'] for p in r)
    assert {p['status'] for p in r}=={'intentional_profile_difference'}


def test_scalar_arithmetic_flags_order_and_overflow():
    m=one(0x8124,v={1:255,2:2});m.step()
    assert m.v[1]==1 and m.v[15]==1
    m=one(0x8f24,v={15:10,2:255});m.step() # VX=VF must hold flag, not result
    assert m.v[15]==1
    m=one(0x8125,v={1:2,2:3});m.step()
    assert m.v[1]==255 and m.v[15]==0
    m=one(0x8127,v={1:2,2:3});m.step()
    assert m.v[1]==1 and m.v[15]==1
    m=one(0x71ff,v={1:2});m.step()
    assert m.v[1]==1


def test_control_flow_and_memory_and_readback():
    m=one(0x2208);m.memory[0x208:0x20a]=bytes.fromhex('00ee');m.step();assert m.pc==0x208 and m.stack==[0x202]
    m.step();assert m.pc==0x202 and m.stack==[]
    m=one(0xf255,v={0:21,1:34,2:55},i=0x320)
    m.step();assert m.i==0x323 and m.memory[0x320:0x323]==bytes([21,34,55])
    m.memory[0x200:0x202]=bytes.fromhex('f265');m.pc=0x200;m.i=0x320;m.v[:3]=[0,0,0];m.step()
    assert m.v[:3]==[21,34,55]
    m=one(0xf133,v={1:237},i=0x301);m.step();assert m.memory[0x301:0x304]==bytes([2,3,7])
    m=one(0x3007,v={0:7});m.step();assert m.pc==0x204
    m=one(0xf10a);assert m.step()=='waiting' and m.pc==0x200
    m.keys.add(7);assert m.step()=='executed' and m.v[1]==7


def test_display_xor_collision_and_timer_control():
    m=one(0xd121,v={1:4,2:5},memory=b'\xf0');m.step()
    assert sum(m.frame)==4 and m.v[15]==0
    m.pc=0x200;m.step();assert sum(m.frame)==0 and m.v[15]==1
    m=one(0xf115,v={1:4});m.step();assert m.delay==4
    m.tick_60hz(2);assert m.delay==2
    m=one(0xf118,v={1:3});m.step();assert m.sound==3


def test_traps_are_not_false_unknown_opcodes():
    with pytest.raises(Trap,match='invalid_opcode'):
        one(0x5011).step()
    with pytest.raises(Trap,match='legacy_system_call_unimplemented'):
        one(0x0011).step()
    with pytest.raises(Trap,match='stack_underflow'):
        one(0x00ee).step()
    with pytest.raises(Trap,match='memory_oob'):
        one(0xf233,i=0xffe).step()
    with pytest.raises(Trap,match='fetch_oob'):
        m=one(0x6001);m.pc=0xfff;m.step()


def test_sandsifter_mutant_detected_and_minimized():
    x=mutation_sanity()
    assert x['anomalous_words']==256 and x['minimized_words']==['5011']
    assert ddmin([1,2,3,4,5],lambda seq:3 in seq)==[3]


def test_real_cc0_corpus_identity_and_coverage():
    if not (CORPUS_DIR/'snek.ch8').exists():
        pytest.skip('separate CC0 ROM corpus not fetched; use corpus/fetch_archive.py --dest outside Git')
    manifest=json.loads((PROJECT/'corpus/manifest.json').read_text())
    assert len(manifest['programs'])==9
    for p in manifest['programs']:
        content=(CORPUS_DIR/(p['key']+'.ch8')).read_bytes()
        assert len(content)==p['size']
        assert hashlib.sha256(content).hexdigest()==p['sha256']
        blob=b'blob '+str(len(content)).encode()+b'\0'+content
        assert hashlib.sha1(blob).hexdigest()==p['git_blob_sha']
    r=corpus_metrics(1000)
    assert r['executed_classic_count']==6
    assert r['executed_family_count']==26
    assert r['classic_family_denominator']==34
    assert r['unique_adjacent_pairs']>100 and r['unique_trigrams']>200
    assert r['curve'][-1]['unique_families']==26
    assert all(row['word_scan']['warning'].startswith('Linear') for row in r['roms'])
    assert any(row['dynamic']['status']=='key_wait' for row in r['roms'])


def test_study_candidate_is_not_accepted_common_uil():
    r=instruction_candidate(0x200,0x6123)
    assert r['udl']['instruction_bytes']=='6123'
    assert r['uil_intent_candidate']=='state.assign'
    assert r['behavioral_qualification']=='not_proved_against_original_runtime'
    assert r['format']=='fdisbull-chip8-udl-uil-candidate-1'


def test_coverage_gaps_have_bounded_authored_probes():
    if not (CORPUS_DIR/'snek.ch8').exists():
        pytest.skip('CC0 corpus unavailable')
    x=corpus_metrics(1000)
    found=run_gap_probes(x['unseen_classic_families'])
    assert len(found)==8
    assert {r['status'] for r in found}=={'pass'}
    assert all(r['scope'].startswith('authored') for r in found)


def test_local_candidate_registry_roundtrip(tmp_path):
    if not (CORPUS_DIR/'snek.ch8').exists():
        pytest.skip('CC0 corpus unavailable')
    report={'receipt_sha256':'a'*64,'source_commit':'761e3ffc63f43e6a849e80714122feff2afca208',
            'corpus':corpus_metrics(30)}
    path=tmp_path/'sample.sqlite';built=build_index(report,path)
    assert built==inspect_index(path)
    assert built['sources']==9 and built['candidate_rows']>0
    assert all(row['observations']>=1 for row in built['families'])
    with pytest.raises(FileExistsError):build_index(report,path)


def test_short_sequence_repeatability():
    result=fuzz_short_programs(rounds=200,seed=12345)
    assert result['rounds_observed']==200
    assert result['word_pool']==43954
    assert result['repeatability_disagreements']==0
    assert sum(result['stop_counts'].values())==200
    result2=fuzz_short_programs(rounds=200,seed=12345,straightline=True)
    assert result2['repeatability_disagreements']==0
    assert result2['stop_counts'].get('bounded_complete',0)>175


def test_fetch_identity_checks_without_network():
    from corpus.fetch_archive import verify
    raw=bytes.fromhex('6012 7001 1200')
    entry={'key':'authored','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'git_blob_sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    verify(raw,entry)
    with pytest.raises(ValueError,match='identity mismatch'):
        verify(raw+b'\0',entry)