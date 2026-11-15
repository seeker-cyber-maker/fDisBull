"""Independent actual-QEMU goldens for the remaining classic CHIP-8 words."""
from contextlib import contextmanager
import os
import pytest
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_CLASSIC_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_CLASSIC_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_CLASSIC')=='1':
            pytest.fail('Classic CHIP-8 QEMU and qemu-img are required')
        pytest.skip('Set FDISBULL_CHIP8_CLASSIC_QEMU and FDISBULL_CHIP8_CLASSIC_QEMU_IMG')
    return binary,tool


@contextmanager
def _machine(tmp_path,words):
    binary,tool=_inputs();rom=tmp_path/'classic.ch8';source=bytes.fromhex(words);rom.write_bytes(source)
    with Project.create(tmp_path/'project.fdb',rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield d
    assert rom.read_bytes()==source


def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def _step(d,pc,**values):
    result=d.step(timeout_ms=5000);assert result['outcome']=='step',result
    regs=_regs(d);assert regs['pc']==pc
    for key,value in values.items():assert regs[key]==value,(key,regs)
    return result


def _fault(result,code,pc,opcode):
    assert result['outcome']=='exception',result
    fault=result['fault'];assert fault['faulted']
    assert (fault['fault-code'],fault['fault-pc'],fault['fault-opcode'])==(code,pc,opcode)


def test_indexed_jump_uses_v0_without_wrapping_and_faults_next_fetch(tmp_path):
    with _machine(tmp_path,'6002 bffe') as d:
        _step(d,0x202,v0=2);_step(d,0x1000,v0=2)
        before=_regs(d);_fault(d.step(timeout_ms=5000),2,0x1000,0)
        assert _regs(d)==before
    odd=tmp_path/'odd';odd.mkdir()
    with _machine(odd,'6001 b200') as d:
        _step(d,0x202,v0=1);_step(d,0x201,v0=1)
        before=_regs(d);_fault(d.step(timeout_ms=5000),6,0x201,0)
        assert _regs(d)==before


def test_add_i_uses_16bit_wrap_and_preserves_vf_including_alias(tmp_path):
    with _machine(tmp_path,'6f03 ff1e') as d:
        _step(d,0x202,vf=3)
        d.write_registers({'i':{'expected':0,'value':0xffff}})
        _step(d,0x204,i=2,vf=3)


@pytest.mark.parametrize('number,decimal',[(0,'000000'),(9,'000009'),(10,'000100'),
                                           (99,'000909'),(100,'010000'),(255,'020505')])
def test_bcd_exact_values_at_last_three_ram_bytes(tmp_path,number,decimal):
    with _machine(tmp_path,'affd f033') as d:
        d.write_registers({'v0':{'expected':0,'value':number}})
        _step(d,0x202,i=0xffd,v0=number)
        _step(d,0x204,i=0xffd,v0=number)
        assert d.memory(0xffd,length=3)['hex']==decimal


@pytest.mark.parametrize('start',[0xffe,0xfff])
def test_bcd_out_of_bounds_fault_is_atomic(tmp_path,start):
    with _machine(tmp_path,'60ff f033') as d:
        _step(d,0x202,v0=255)
        d.write_registers({'i':{'expected':0,'value':start}})
        registers=_regs(d);memory=d.memory(0xffd,length=3)['hex'];env=d.chip8_environment()
        _fault(d.step(timeout_ms=5000),3,0x202,0xf033)
        assert _regs(d)==registers and d.memory(0xffd,length=3)['hex']==memory
        after=d.chip8_environment()
        for key in ('pixels-hex','key-mask','key-wait','delay-timer','sound-timer',
                    'rng-seed','rng-state','rng-draws'):
            assert after[key]==env[key],key


def test_rng_seeded_fixed_vectors_masks_and_vf_alias(tmp_path):
    # Independent fixed LCG vectors: seed 0 gives high bytes 3c,47,d1,aa.
    with _machine(tmp_path,'c0ff c100 c2f0 cfff') as d:
        initial=d.chip8_seed_rng(0)
        assert initial['rng-model']=='fdisbull-lcg32-high8-v1'
        assert initial['rng-seed']==initial['rng-state']==0
        draws=initial['rng-draws']
        d.write_registers({'vf':{'expected':0,'value':0xab}})
        _step(d,0x202,v0=0x3c,vf=0xab);s1=d.chip8_environment()
        assert s1['rng-state']==0x3c6ef35f and s1['rng-draws']==draws+1
        _step(d,0x204,v1=0,vf=0xab);s2=d.chip8_environment()
        assert s2['rng-state']==0x47502932 and s2['rng-draws']==draws+2
        _step(d,0x206,v2=0xd0,vf=0xab);s3=d.chip8_environment()
        assert s3['rng-state']==0xd1ccf6e9 and s3['rng-draws']==draws+3
        _step(d,0x208,vf=0xaa);s4=d.chip8_environment()
        assert s4['rng-state']==0xaaf95334 and s4['rng-draws']==draws+4


def test_rng_seed_repeat_and_distinct_seed_vectors(tmp_path):
    with _machine(tmp_path,'c0ff c1ff') as d:
        for seed,second,state in ((0,0x47,0x47502932),(1,0x5e,0x5e8885db),
                                  (0,0x47,0x47502932)):
            current=_regs(d)['pc']
            if current!=0x200:d.write_registers({'pc':{'expected':current,'value':0x200}})
            receipt=d.chip8_seed_rng(seed)
            assert (receipt['rng-seed'],receipt['rng-state'],receipt['rng-draws'])==(seed,seed,0)
            _step(d,0x202,v0=0x3c);_step(d,0x204,v1=second)
            after=d.chip8_environment()
            assert (after['rng-state'],after['rng-draws'])==(state,2)


def test_rng_future_replays_after_fresh_process_and_fdb_reopen(tmp_path):
    binary,tool=_inputs();source=bytes.fromhex('c0ff c1ff c2f0 cfff')
    rom=tmp_path/'saved.ch8';rom.write_bytes(source);db=tmp_path/'project.fdb'
    with Project.create(db,rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.chip8_seed_rng(0);d.chip8_keypad([0,15]);d.write_memory(0x300,'7a',expected_hex='00')
            _step(d,0x202,v0=0x3c)
            checkpoint=d.save_state(timeout_ms=30000)['artifact']
            _step(d,0x204,v1=0x47);_step(d,0x206,v2=0xd0);_step(d,0x208,vf=0xaa)
            expected_regs=_regs(d);expected=d.chip8_environment()
            assert expected['rng-state']==0xaaf95334 and expected['rng-draws']==4
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000)
            assert old.poll() is not None and d.memory(0x300,length=1)['hex']=='7a'
            restored=d.chip8_environment()
            assert (restored['rng-seed'],restored['rng-state'],restored['rng-draws'])==(0,0x3c6ef35f,1)
            assert restored['key-mask']==0x8001
            _step(d,0x204,v1=0x47);_step(d,0x206,v2=0xd0);_step(d,0x208,vf=0xaa)
            actual=d.chip8_environment()
            assert _regs(d)==expected_regs
            for key in ('rng-model','rng-seed','rng-state','rng-draws','key-mask','pixels-hex'):
                assert actual[key]==expected[key],key
    assert rom.read_bytes()==source


def test_add_immediate_wraps_and_preserves_vf(tmp_path):
    with _machine(tmp_path,'70ff') as d:
        d.write_registers({'v0':{'expected':0,'value':2},
                           'vf':{'expected':0,'value':0xab}})
        _step(d,0x202,v0=1,vf=0xab)


@pytest.mark.parametrize('word,left,right,result,flag',[
    ('8010',0x55,0xa3,0xa3,0x5a),  # LD V0,V1 leaves VF alone.
    ('8012',0x5a,0x3c,0x18,0),     # AND clears VF.
    ('8013',0x5a,0x3c,0x66,0),     # XOR clears VF.
    ('8015',0x05,0x07,0xfe,0),    # SUB borrow.
    ('8015',0x07,0x05,0x02,1),    # SUB no borrow.
    ('8017',0x05,0x07,0x02,1),    # SUBN no borrow.
    ('8017',0x07,0x05,0xfe,0),    # SUBN borrow.
])
def test_register_load_logic_and_subtract_golden(tmp_path,word,left,right,result,flag):
    with _machine(tmp_path,word) as d:
        d.write_registers({'v0':{'expected':0,'value':left},
                           'v1':{'expected':0,'value':right},
                           'vf':{'expected':0,'value':0x5a}})
        _step(d,0x202,v0=result,v1=right,vf=flag)


@pytest.mark.parametrize('word,left,right,expected_pc',[
    ('4002',2,0,0x202),('4002',3,0,0x204),  # SNE V0, 2
    ('5010',4,4,0x204),('5010',4,5,0x202),  # SE V0, V1
    ('9010',4,5,0x204),('9010',4,4,0x202),  # SNE V0, V1
])
def test_comparison_skip_taken_and_fallthrough(tmp_path,word,left,right,expected_pc):
    with _machine(tmp_path,word) as d:
        d.write_registers({'v0':{'expected':0,'value':left},
                           'v1':{'expected':0,'value':right}})
        _step(d,expected_pc,v0=left,v1=right)


def test_cls_clears_lit_pixel_and_preserves_other_device_state(tmp_path):
    with _machine(tmp_path,'6000 6100 a300 d011 00e0') as d:
        d.chip8_seed_rng(0x12345678);d.chip8_keypad([0,15])
        d.write_memory(0x300,'80',expected_hex='00')
        _step(d,0x202);_step(d,0x204);_step(d,0x206);_step(d,0x208,vf=0)
        before=d.chip8_environment()
        assert bytes.fromhex(before['pixels-hex'])==b'\x01'+bytes(2047)
        _step(d,0x20a)
        after=d.chip8_environment()
        assert bytes.fromhex(after['pixels-hex'])==bytes(2048)
        for key in ('rng-model','rng-seed','rng-state','rng-draws','key-mask',
                    'delay-timer','sound-timer','sound-active'):
            assert after[key]==before[key],key


# Executed-word witness map; file stems name the native test modules. This is
# evidence navigation, not a claim of independently qualified historical ISA.
FAMILY_WITNESSES = {
    'CLS': ('classic_semantics', '00e0'),
    'RET': ('qemu_semantics', '00ee'),
    'JP': ('qemu_semantics', '1200'),
    'CALL': ('qemu_semantics', '220e'),
    'SE_VX_KK': ('qemu_semantics', '3001'),
    'SNE_VX_KK': ('classic_semantics', '4002'),
    'SE_VX_VY': ('classic_semantics', '5010'),
    'LD_VX_KK': ('qemu_semantics', '60ff'),
    'ADD_VX_KK': ('classic_semantics', '70ff'),
    'LD_VX_VY': ('classic_semantics', '8010'),
    'OR': ('qemu_semantics', '8011'),
    'AND': ('classic_semantics', '8012'),
    'XOR': ('classic_semantics', '8013'),
    'ADD_VX_VY': ('qemu_semantics', '8014'),
    'SUB': ('classic_semantics', '8015'),
    'SHR': ('qemu_semantics', '8436'),
    'SUBN': ('classic_semantics', '8017'),
    'SHL': ('qemu_semantics', '843e'),
    'SNE_VX_VY': ('classic_semantics', '9010'),
    'LD_I': ('qemu_semantics', 'a300'),
    'JP_V0': ('classic_semantics', 'bffe'),
    'RND': ('classic_semantics', 'c0ff'),
    'DRW': ('devices_semantics', 'd012'),
    'SKP': ('devices_semantics', 'e09e'),
    'SKNP': ('devices_semantics', 'e1a1'),
    'LD_VX_DT': ('devices_semantics', 'f107'),
    'WAIT_KEY': ('devices_semantics', 'f00a'),
    'LD_DT_VX': ('devices_semantics', 'f015'),
    'LD_ST_VX': ('devices_semantics', 'f018'),
    'ADD_I_VX': ('classic_semantics', 'ff1e'),
    'FONT': ('devices_semantics', 'f129'),
    'BCD': ('classic_semantics', 'f033'),
    'SAVE': ('qemu_semantics', 'f155'),
    'LOAD': ('qemu_semantics', 'f165'),
}


def test_witness_map_covers_classic_family_names():
    from fdisbull.chip8 import decode
    assert len(FAMILY_WITNESSES)==34
    for family,(_,word) in FAMILY_WITNESSES.items():
        assert decode(bytes.fromhex(word),0x200)['mnemonic']==family.lower()
