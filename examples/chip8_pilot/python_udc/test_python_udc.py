"""Bounded proof-of-concept checks against authored fixtures and CC0 local inputs."""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from chip8lab.vm import Machine
from chip8lab.decoder import decode_table
from .generator import compile_rom, compile_file
from .trial import check, import_generated
from .swedes import SWEDED_FAMILIES, emit

HERE=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('word', [
    0x00e0,0x00ee,0x1004,0x2206,0x3001,0x40ff,0x5000,0x6f80,
    0x7001,0x8010,0x8014,0x9000,0xa555,0xf007,0xf015,0xf018,
    0xe09e,0xe0a1,0xf01e,0xf029,
])
def test_every_swede_emits_only_known_instruction(word):
    d=decode_table(word)
    assert d.family in SWEDED_FAMILIES
    assert emit(d)


def test_does_not_swede_unknown_or_extension():
    with pytest.raises(ValueError,match='no admitted'):
        emit(decode_table(0xd125))
    with pytest.raises(ValueError,match='no admitted'):
        emit(decode_table(0x00ff,'schip'))


def test_sample_generated_module_matches_entire_state_each_step(tmp_path):
    # 200: LD V0, 0; 202: ADD V0, 1; 204: SE V0, 3;
    # 206: JP 202; 208: CLS; 20a: JP 202.
    rom=bytes.fromhex('600070013003120200e01202')
    r=tmp_path/'authored.ch8';r.write_bytes(rom)
    source, receipt=compile_rom(rom,seeds=(0,),max_steps=75,tick_period=2)
    assert receipt['observed_pc_count']>=4
    out=tmp_path/'generated.py';out.write_text(source)
    result=check(r,out,steps=200,tick_period=2)
    assert result['status']=='passed',result
    assert result['specialized_steps']>0
    assert result['original_backed_steps']==0


def test_compiled_path_is_not_a_vm_step_wrapper(tmp_path, monkeypatch):
    rom=bytes.fromhex('60011200')
    r=tmp_path/'authored.ch8';r.write_bytes(rom)
    source, receipt=compile_rom(rom,seeds=(0,),max_steps=10)
    out=tmp_path/'generated.py';out.write_text(source)
    gen=import_generated(out)
    m=gen.build_machine(r)
    assert gen.can_run_specialized(m)
    def fail(*args,**kw): raise AssertionError('reference VM step called on specialized path')
    monkeypatch.setattr(Machine,'step',fail)
    assert gen.step(m)=='executed'
    assert m.v[0]==1 and m.pc==0x202


def test_stale_rom_rejected_and_modified_code_falls_back(tmp_path):
    r=tmp_path/'one.ch8';r.write_bytes(bytes.fromhex('60011200'))
    src,_=compile_rom(r.read_bytes(),seeds=(0,),max_steps=10)
    out=tmp_path/'generated.py';out.write_text(src)
    gen=import_generated(out)
    m=gen.build_machine(r)
    m.memory[0x201]=2  # self-modification invalidates previously specialized word
    assert gen.can_run_specialized(m) is False
    assert gen.step(m)=='executed' and m.v[0]==2
    r.write_bytes(bytes.fromhex('60021200'))
    with pytest.raises(ValueError,match='ROM identity mismatch'):
        gen.build_machine(r)


@pytest.mark.parametrize('name',['snek','ghostEscape','1dcell'])
def test_real_cc0_programs_against_existing_pilot(tmp_path,name):
    rom=HERE/'corpus'/f'{name}.ch8'
    if not rom.exists(): pytest.skip('local CC0 corpus not fetched')
    target=tmp_path/f'{name}_module.py'
    _,receipt=compile_file(rom,target,tick_period=11,max_steps=1000)
    result=check(rom,target,seeds=(0,1),steps=650,tick_period=11)
    assert result['status']=='passed',result
    assert result['compared_steps']>0
    assert result['specialized_steps']>0
    assert result['source_sha256']==hashlib.sha256(rom.read_bytes()).hexdigest()


def test_missing_family_receives_explicit_original_backed_fallback():
    # Draw reads sprite RAM and updates pixels; deliberately not sweded yet.
    src,receipt=compile_rom(bytes.fromhex('a200d0111202'),seeds=(0,),max_steps=10)
    assert 'DRW' in {f['family'] for f in receipt['original_backed_fallbacks']}
    assert 'agent-authored-python-swede' in {f['implementation'] for f in receipt['specializations']}