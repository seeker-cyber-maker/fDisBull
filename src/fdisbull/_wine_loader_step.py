"""Typed instruction transfer shared by the bounded Wine loader verifiers.

Admission, source ownership, access receipts, path obligations and frame policy
belong to the callers. This helper supplies instruction semantics only.
"""
from capstone import x86_const as X
from iced_x86 import Decoder

from .pe_guard_model import FLAG_BITS, condition_name, decision
from .pe_region_equivalence import _arithmetic_flags, _condition


_R32 = dict(zip(('eax','ebx','ecx','edx','esi','edi','ebp','esp'),
               ('rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp'))) | {f'r{i}d':f'r{i}' for i in range(8,16)}
_R16 = dict(zip(('ax','bx','cx','dx','si','di','bp','sp'),
               ('rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp'))) | {f'r{i}w':f'r{i}' for i in range(8,16)}
_R8 = dict(zip(('al','bl','cl','dl','sil','dil','bpl','spl'),
              ('rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp'))) | {f'r{i}b':f'r{i}' for i in range(8,16)}


def typed_loader_step(ins, *, z, registers, flags, undefined, teb, access,
                      simplify, fresh_af, opaque_store, on_call, on_return,
                      on_branch, native_flags):
    """Apply one exact decoded instruction and return FLAGS and concrete PC.

    Memory callbacks must prove address safety under preceding guards, and
    control callbacks must prove every target and return-frame obligation.
    Native branch choices select the path, never justify earlier effects.
    """
    regs=registers;address=ins.address;raw=bytes(ins.bytes);seq=address+len(raw)
    expected_pc=seq
    def reg(op):
        n=ins.reg_name(op.reg)
        if n in regs and op.size==8:return n,64,0
        table={4:_R32,2:_R16,1:_R8}.get(op.size,{})
        if n in table:return table[n],op.size*8,0
        if n in ('ah','bh','ch','dh') and op.size==1:return {'ah':'rax','bh':'rbx','ch':'rcx','dh':'rdx'}[n],8,8
        raise ValueError('Unmodeled loader register view')
    def reg_read(op):
        n,w,shift=reg(op);return regs[n] if w==64 else z.Extract(shift+w-1,shift,regs[n])
    def reg_write(op,value):
        n,w,shift=reg(op)
        if value.size()!=w:raise ValueError('Loader register operand width differs')
        if w==64:regs[n]=value
        elif w==32:regs[n]=z.ZeroExt(32,value)
        else:
            keep=((1<<64)-1)^(((1<<w)-1)<<shift)
            regs[n]=(regs[n]&keep)|(z.ZeroExt(64-w,value)<<shift)
    def loc(op):
        value=z.BitVecVal(op.mem.disp%(1<<64),64)
        for r,scale in ((op.mem.base,1),(op.mem.index,op.mem.scale)):
            if r:
                n=ins.reg_name(r);term=z.BitVecVal(seq,64) if n=='rip' else regs.get(n)
                if term is None:raise ValueError('Unknown loader address register')
                value+=term*scale
        if op.mem.segment:
            if ins.reg_name(op.mem.segment)!='gs':raise ValueError('Unknown loader segment binding')
            value+=teb
        return simplify(value),op.size
    def read_op(op):
        if op.type==X.X86_OP_REG:return reg_read(op)
        if op.type==X.X86_OP_IMM:return z.BitVecVal(op.imm%(1<<(8*op.size)),8*op.size)
        if op.type==X.X86_OP_MEM:return access('read',*loc(op))
        raise ValueError('Unknown loader operand')
    def write_op(op,value):
        if op.type==X.X86_OP_REG:reg_write(op,value)
        elif op.type==X.X86_OP_MEM:
            p,w=loc(op)
            value=z.SignExt(w*8-value.size(),value) if value.size()<w*8 else z.Extract(w*8-1,0,value)
            access('write',p,w,value)
        else:raise ValueError('Unknown loader destination')
    ops=ins.operands;mn=ins.mnemonic
    if raw==b'\xf3\x0f\x1e\xfa' or mn=='nop':pass
    elif mn=='push' and len(ops)==1:
        value=read_op(ops[0]);value=z.SignExt(64-value.size(),value) if value.size()<64 else value
        regs['rsp']-=8;access('write',regs['rsp'],8,value)
    elif mn=='pop' and len(ops)==1:
        value=access('read',regs['rsp'],8);regs['rsp']+=8;write_op(ops[0],value)
    elif mn=='call' and len(ops)==1:
        target=read_op(ops[0]);target=z.ZeroExt(64-target.size(),target) if target.size()<64 else target
        regs['rsp']-=8;access('write',regs['rsp'],8,z.BitVecVal(seq,64))
        expected_pc=on_call(target,seq,regs['rsp'])
    elif mn=='ret' and raw==b'\xc3':
        target=access('read',regs['rsp'],8)
        expected_pc=on_return(target,regs['rsp']);regs['rsp']+=8
    elif mn in ('mov','movabs') and len(ops)==2:write_op(ops[0],read_op(ops[1]))
    elif mn=='movzx' and len(ops)==2:
        value=read_op(ops[1]);dest_width=reg(ops[0])[1];write_op(ops[0],z.ZeroExt(dest_width-value.size(),value))
    elif mn=='lea' and len(ops)==2:
        if ops[1].mem.segment:raise ValueError('Segment-prefixed LEA remains unsupported')
        write_op(ops[0],loc(ops[1])[0])
    elif mn in ('cmp','test','add','sub','and','or','xor') and len(ops)==2:
        a,b=read_op(ops[0]),read_op(ops[1])
        if a.size()!=b.size():b=z.SignExt(a.size()-b.size(),b)
        value=a-b if mn in ('cmp','sub') else a+b if mn=='add' else a|b if mn=='or' else a^b if mn=='xor' else a&b
        flags=_arithmetic_flags(z,'and' if mn=='test' else mn,a,b,value,flags,fresh_af())
        undefined=1<<FLAG_BITS['af'] if mn in ('test','and','or','xor') else 0
        if mn not in ('cmp','test'):write_op(ops[0],value)
    elif mn.startswith('cmov') and len(ops)==2:
        value=read_op(ops[1]);old=read_op(ops[0]);condition=_condition(z,mn[4:],flags)
        write_op(ops[0],z.If(condition,value,old))
    elif mn in ('stmxcsr','fnstcw','movdqa','movups','movaps'):
        if not ops or ops[0].type!=X.X86_OP_MEM:raise ValueError('Only context-save floating stores are supported')
        pointer,width=loc(ops[0]);access('write',pointer,width,opaque_store(width))
    else:
        iced=Decoder(64,raw,ip=address).decode()
        if iced.is_jcc_short_or_near or iced.is_jmp_short_or_near:
            cond=condition_name(iced);taken=decision(cond,native_flags);pred=_condition(z,cond,flags)
            on_branch(pred if taken else z.Not(pred))
            expected_pc=iced.near_branch_target if taken else seq
        else:raise ValueError('Unsupported native loader instruction: '+mn)
    return flags,undefined,expected_pc
