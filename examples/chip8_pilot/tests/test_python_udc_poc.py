"""Proof-of-concept gates: program identity, same-VM differential, fallback.

Neither this suite nor the source oracle verifies historical COSMAC/Octo parity.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import random
from pathlib import Path
import pytest
from chip8lab.vm import Machine, Quirks, Trap
from chip8_udc.compiler import compile_rom, write_module
from chip8_udc.swedes import SWEDES
from chip8_udc.verify import import_generated, drive

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'results/observations.sqlite'
CORPUS=ROOT/'corpus'
MANIFEST=json.loads((CORPUS/'manifest.json').read_text())
CLASSIC=[p for p in MANIFEST['programs'] if p['platform']=='chip8']


def make_module(tmp_path, rom:bytes, name='test_udc', index=None,steps=1600):
    source, manifest = compile_rom(rom,module_name=name,index_path=index,steps=steps)
    directory=tmp_path/name
    write_module(directory,source,manifest)
    return import_generated(directory/(name+'.py')),manifest,directory


@pytest.mark.parametrize('entry',CLASSIC,ids=lambda e:e['key'])
def test_six_pinned_roms_match_original_pilot_vm(tmp_path,entry):
    path=CORPUS/(entry['key']+'.ch8')
    if not path.is_file():pytest.skip('explicitly fetched CC0 program not available')
    rom=path.read_bytes()
    assert hashlib.sha256(rom).hexdigest()==entry['sha256']
    module,manifest,_=make_module(tmp_path,rom,name='gen_'+entry['key'],index=INDEX if INDEX.is_file() else None)
    assert manifest['specialized_site_count'] > 0
    assert manifest['source_sha256']==entry['sha256']
    assert manifest['intermediate'].endswith('(NOT canonical UIL)')
    result=drive(module,rom,budget=1600)
    assert result['completed_attempts']>0
    assert result['specialized_steps']>0
    assert result['fallback_steps']>=0
    assert result['specialized_steps']+result['fallback_steps']==result['completed_attempts']


def test_no_rom_bytes_embedded_and_hash_rejects_wrong_program(tmp_path):
    rom=bytes.fromhex('6001 7001 1200')
    m,manifest,out=make_module(tmp_path,rom,steps=10)
    src=(out/'test_udc.py').read_text()
    assert 'ROM_HEX' not in src and 'load_rom(rom)' in src
    with pytest.raises(ValueError,match='does not match'):
        m.create_machine(rom[:-1]+b'\x01')
    assert drive(m,rom,budget=45)['specialized_steps']>0


def test_fallback_on_modified_opcode(tmp_path):
    rom=bytes.fromhex('6001 7001 1200')
    module,manifest,out=make_module(tmp_path,rom,steps=10)
    fast=module.create_machine(rom)
    normal=Machine(seed=42);normal.load_rom(rom)
    # Replace previously specialized word with a different valid instruction;
    # PC remains unchanged. The identity guard must use the reference VM.
    fast.memory[0x200:0x202]=bytes.fromhex('6108')
    normal.memory[0x200:0x202]=bytes.fromhex('6108')
    counts={}
    assert module.step(fast,counts)==normal.step()
    assert counts=={'fallback':1}
    assert fast.state_digest()==normal.state_digest()
    assert fast.last_family==normal.last_family


def test_unsupported_family_delegates_instead_of_sweding_it(tmp_path):
    rom=bytes.fromhex('a300 f165 1200')
    m,manifest,_=make_module(tmp_path,rom,steps=20)
    assert 'LOAD' in manifest['fallback_family_count']
    result=drive(m,rom,budget=60)
    assert result['fallback_steps'] > 0
    assert 'LOAD' in result['family_executions']


@pytest.mark.parametrize('word',[
    0x00e0,0x1123,0x3001,0x4f11,0x5010,0x9010,
    0x6fff,0x7f88,0x8ff0,0xaaff,0xf007,0xf015,0xf018,
    0xf01e,0xe19e,0xe1a1,0xf129,0xc3f7,0x8ff4,
])
def test_manually_sweded_rules_match_machine_for_varied_states(tmp_path,word):
    from chip8lab.decoder import decode_table
    d=decode_table(word)
    if d.family not in SWEDES:pytest.skip('no swede rule')
    rom=word.to_bytes(2,'big')
    module,manifest,_=make_module(tmp_path,rom,name='w_'+format(word,'04x'),steps=1)
    assert manifest['specialized_site_count']==1
    for idx in range(40):
        rng=random.Random((word<<6)+idx)
        m=module.create_machine(rom,seed=idx)
        ref=Machine(seed=idx);ref.load_rom(rom)
        for machine in (m,ref):
            machine.v=[rng.randrange(256) for _ in range(16)] if machine is m else m.v.copy()
            machine.pc=0x200
            machine.i=0x300
            machine.delay=idx%31;machine.sound=idx%29
            machine.keys=set([idx%16]) if idx%3==0 else set()
        assert m.state_digest()==ref.state_digest()
        stats={}
        assert module.step(m,stats)==ref.step()
        assert stats=={'specialized':1}
        assert m.state_digest()==ref.state_digest()
        assert m.last_family==ref.last_family


def test_unobserved_address_uses_reference_vm(tmp_path):
    rom=bytes.fromhex('6001 7002 1200')
    module,_,_=make_module(tmp_path,rom,steps=1)
    m=module.create_machine(rom)
    ref=Machine(seed=42);ref.load_rom(rom)
    m.pc=ref.pc=0x202
    counts={}
    assert module.step(m,counts)==ref.step()
    assert counts=={'fallback':1}
    assert m.state_digest()==ref.state_digest()


def test_nonclassic_database_record_is_refused(tmp_path):
    rom=(CORPUS/'dodge.ch8')
    if not rom.exists() or not INDEX.exists():pytest.skip('pilot corpus unavailable')
    with pytest.raises(ValueError, match='(profile|chip8|classic)'):
        compile_rom(rom.read_bytes(),module_name='not_classic',index_path=INDEX)


def test_rule_catalog_persists_and_records_incremental_swede(tmp_path):
    from chip8_udc.catalog import RuleCatalog
    from chip8_udc.compiler import compile_rom
    rom=bytes.fromhex('2208 6004 1200 00ee 00ee')
    cat=tmp_path/'private_rules.sqlite'
    with RuleCatalog(cat,create=True) as db:
        for family in sorted(SWEDES):
            if family not in ('CALL','RET'):db.register(family)
        assert db.register('JP') is False
        initial=db.summary()
        assert 'CALL' not in initial['registered_families']
    before, before_metadata=compile_rom(rom,module_name='before',steps=25,catalog_path=cat)
    assert 'CALL' in before_metadata['fallback_family_count']
    with RuleCatalog(cat) as db:
        db.register('CALL');db.register('RET')
        after=db.summary()
        assert len(after['registered_families'])==len(initial['registered_families'])+2
        assert initial['catalog_sha256']!=after['catalog_sha256']
    updated, updated_metadata=compile_rom(rom,module_name='after',steps=25,catalog_path=cat)
    assert updated_metadata['specialized_site_count']>before_metadata['specialized_site_count']
    assert 'CALL' not in updated_metadata['fallback_family_count']
    assert updated_metadata['rule_catalog_sha256']==after['catalog_sha256']


def test_catalog_refuses_unreviewed_rules_and_tampering(tmp_path):
    from chip8_udc.catalog import RuleCatalog
    cat=tmp_path/'rules.sqlite'
    with RuleCatalog(cat,create=True) as db:
        with pytest.raises(ValueError,match='manual swede'):
            db.register('MAGIC_UNIMPLEMENTED')
        db.register('LD_VX_KK')
        db.db.execute("UPDATE rules SET template_sha256=? WHERE family='LD_VX_KK'",('0'*64,))
        db.db.commit()
        with pytest.raises(ValueError, match='mismatched'):
            db.available()


@pytest.mark.parametrize('pc,word,stack,reason',[
    (0x200,0x2208,[0x444]*16,'stack_overflow'),
    (0x208,0x00EE,[],'stack_underflow'),
])
def test_sweded_control_stack_traps_match_original_vm(tmp_path,pc,word,stack,reason):
    # A normal observation scan records successful operations only; deliberately
    # include an observed CALL/RET chain, then inject the adversarial stack state.
    rom=bytes.fromhex('2208 6004 1200 6001 00ee')
    module,manifest,_=make_module(tmp_path,rom,steps=5)
    a=module.create_machine(rom);b=Machine(seed=42);b.load_rom(rom)
    a.pc=b.pc=pc
    a.stack=stack.copy();b.stack=stack.copy()
    x=y=None
    try:module.step(a)
    except Trap as e:x=(e.code,e.address,e.word)
    try:b.step()
    except Trap as e:y=(e.code,e.address,e.word)
    assert x==y==(reason,pc,word)
    assert a.state_digest()==b.state_digest()
    assert a.last_family==b.last_family


def test_generated_output_directory_is_refused_inside_git(tmp_path):
    from chip8_udc.compiler import write_module
    import subprocess
    root=tmp_path/'checkout';root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    with pytest.raises(ValueError,match='outside a Git checkout'):
        write_module(root/'compiled','print(1)',{'module_name':'x'})


@pytest.mark.parametrize('clip,initial_vf,at_edge',[(True,0,False),(True,1,True),(False,0,True),(False,1,True)])
def test_sweded_display_draw_matches_pixel_collision_and_clip(tmp_path,clip,initial_vf,at_edge):
    rom=bytes.fromhex('d121 1200')
    module,_,_=make_module(tmp_path,rom,steps=1)
    a=module.create_machine(rom,quirks=Quirks(clip_sprites=clip))
    b=Machine(seed=42,quirks=Quirks(clip_sprites=clip));b.load_rom(rom)
    for machine in (a,b):
        machine.i=0x300
        machine.memory[0x300]=0xFF
        machine.v[1]=62 if at_edge else 8
        machine.v[2]=31 if at_edge else 10
        machine.v[15]=initial_vf
        if initial_vf:
            machine.frame[(machine.v[2] % 32)*64 + (machine.v[1] % 64)]=1
    assert module.step(a)==b.step()
    assert a.state_digest()==b.state_digest()
    assert a.last_family==b.last_family


def test_display_draw_memory_bounds_trap_parity(tmp_path):
    rom=bytes.fromhex('d125 1200')
    module,_,_=make_module(tmp_path,rom,steps=1)
    a=module.create_machine(rom);b=Machine(seed=42);b.load_rom(rom)
    a.i=b.i=4095
    x=y=None
    try:module.step(a)
    except Trap as e:x=(e.code,e.address,e.word)
    try:b.step()
    except Trap as e:y=(e.code,e.address,e.word)
    assert x==y==('memory_oob',0x200,0xD125)
    assert a.state_digest()==b.state_digest()


def test_published_cc0_generated_example_matches_manifest():
    example=ROOT/'udc_example'
    info=json.loads((example/'manifest.json').read_text())
    source=(example/'udc_snek.py').read_bytes()
    snek=next(p for p in MANIFEST['programs'] if p['key']=='snek')
    assert info['source_sha256']==snek['sha256']
    assert hashlib.sha256(source).hexdigest()==info['generated_source_sha256']
    assert info['specialized_site_count']==17
    assert info['execution_authorized_by_registry'] is False
