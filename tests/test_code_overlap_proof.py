"""Bounded authored-ISA model checks; not a target or native equivalence proof."""
from functools import reduce

import iced_x86 as ix
import pytest
import z3

from fdisbull.code_layout import compile_code_backings
from fdisbull.project import Project
from fdisbull.udl_blocks import lift_asm_block

ASSUMPTIONS = {key: True for key in ('no_code_reads', 'no_code_writes', 'no_computed_entries',
                                   'address_identity_unobserved', 'timing_unobserved')}


def symbols():
    return {'al': z3.BitVec('al', 8), 'di': z3.BitVec('edi', 32), 'df': z3.Bool('df'),
            'memory': z3.Array('memory', z3.BitVecSort(32), z3.BitVecSort(8)),
            **{n:z3.Bool(n) for n in ('cf','of','sf','zf','pf')}}


def run_model(code, base, entry, bits, state):
    """Execute only TEST AL,imm8 / STOSB / near JMP / RET until boundary.

    Byte-addressed memory abstracts a fixed permitted segment/base; its keys are
    EDI or zero-extended DI. Valid memory/no-alias, successful store, unchanged
    DF and fixed mode are assumptions. No timing, exceptions, AF or environment.
    """
    out=dict(state); pc=entry; steps=0
    while steps < 16:
        offset=pc-base
        assert 0 <= offset < len(code)
        native=ix.Decoder(bits, code[offset:], ip=pc).decode()
        assert not native.is_invalid and native.len > 0
        raw=code[offset:offset+native.len]; steps+=1
        if raw == b'\xa8\xaa':
            v=out['al'] & z3.BitVecVal(0xaa,8)
            parity=reduce(z3.Xor, (z3.Extract(i,i,v)==1 for i in range(8)))
            out.update(cf=z3.BoolVal(False),of=z3.BoolVal(False),sf=z3.Extract(7,7,v)==1,
                       zf=v==0,pf=z3.Not(parity))
        elif raw in (b'\xaa',b'\x67\xaa'):
            addr_bits=bits if len(raw)==1 else (32 if bits==16 else 16)
            before=out['di']; addr=before if addr_bits==32 else z3.ZeroExt(16,z3.Extract(15,0,before))
            out['memory']=z3.Store(out['memory'],addr,out['al'])
            if addr_bits==32:
                out['di']=z3.If(out['df'], before-z3.BitVecVal(1,32), before+z3.BitVecVal(1,32))
            else:
                low=z3.Extract(15,0,before);nxt=z3.If(out['df'],low-z3.BitVecVal(1,16),low+z3.BitVecVal(1,16))
                out['di']=z3.Concat(z3.Extract(31,16,before),nxt)
        elif raw[0]==0xe9 and native.flow_control==ix.FlowControl.UNCONDITIONAL_BRANCH:
            pc=native.near_branch_target;continue
        elif raw==b'\xc3':
            return out
        else:
            raise AssertionError('unmodelled emitted instruction: '+raw.hex())
        pc+=native.len
    raise AssertionError('instruction budget exceeded')


def differs(left,right):
    return z3.Or(*(left[key]!=right[key] for key in ('al','di','df','memory','cf','of','sf','zf','pf')))


@pytest.mark.parametrize('bits',[16,32])
def test_authored_overlap_and_address_override_are_equivalent_at_ret(tmp_path,bits):
    # A and B share AA; the separate O entry supplies 67 STOSB coverage.
    source=tmp_path/'fixture.bin';source.write_bytes(bytes.fromhex('a8aac367aac3'))
    with Project.create(tmp_path/'fixture.fdb',source,arch='x86',bits=bits,base=0x1000) as project:
        for address in (0x1000,0x1001,0x1003):project.analyze(start=address)
        captured=project.code_backings([0x1000,0x1001,0x1003])
        assert captured['complete'] and captured['qualification']=='native_backings_only'
        assert captured['coverage']['shared_occurrence_bytes']==1
        layout=compile_code_backings(captured,base=0x200,assumptions=ASSUMPTIONS)
        assert layout['qualification']=='structural_only'
        nodes={int(b['address'],16):b['id'] for b in captured['blocks']}
        emitted=bytes.fromhex(layout['bytes']); original=source.read_bytes()
        for entry in (0x1000,0x1001,0x1003):
            initial=symbols(); old=run_model(original,0x1000,entry,bits,initial)
            new=run_model(emitted,0x200,layout['entries'][nodes[entry]],bits,initial)
            solver=z3.Solver();solver.set(timeout=5000);solver.add(differs(old,new))
            assert solver.check()==z3.unsat, f'model mismatch for {bits}-bit entry {entry:#x}'
        # Existing UIL lift has no support for flags or memory; don't upgrade it.
        with pytest.raises(ValueError):lift_asm_block(b'\xa8\xaa',{'ax':'$a'},inputs=['ax'],outputs=['ax'],flags='observed')


@pytest.mark.parametrize('bits',[16,32])
def test_naive_concatenation_has_a_symbolic_counterexample(bits):
    initial=symbols()
    correct=run_model(bytes.fromhex('a8aac3'),0x1000,0x1000,bits,initial)
    naive=run_model(bytes.fromhex('a8aaaac3'),0x2000,0x2000,bits,initial)
    solver=z3.Solver();solver.set(timeout=5000);solver.add(differs(correct,naive))
    assert solver.check()==z3.sat
    # The extra store also changes the destination index for both DF values.
    for df in (False,True):
        solver.push();solver.add(initial['df']==df,correct['di']==naive['di']);assert solver.check()==z3.unsat;solver.pop()
