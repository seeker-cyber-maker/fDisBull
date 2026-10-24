"""Classify a real before-access guard exception using native instruction facts."""
from __future__ import annotations

from iced_x86 import Decoder, InstructionInfoFactory, MemorySizeExt, OpAccess, Register, RegisterExt, CodeSize


NAMES={value:name.lower() for name,value in vars(Register).items() if name.isupper() and isinstance(value,int)}
READS={OpAccess.READ,OpAccess.COND_READ,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE}
WRITES={OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE}


def access_facts(raw, registers, fault_address, access_code):
    """Preserve the native fault address; infer scalar operand width/access explicitly."""
    instruction=Decoder(64,raw,ip=int(registers['rip'],16)).decode()
    if instruction.is_invalid:
        raise ValueError('Cannot classify the guard exception: invalid instruction')
    if access_code==8:return {'instruction':str(instruction),'fetch':True,'ranges':[]}
    operands=list(InstructionInfoFactory().info(instruction).used_memory())
    if len(operands)!=1 or instruction.has_rep_prefix or instruction.has_repne_prefix:
        raise ValueError('Guard watchpoints require one non-repeated scalar memory operand; stopped before access')
    accesses=[]
    for memory in operands:
        size=MemorySizeExt.info(memory.memory_size).size
        if not size or memory.vsib_size or memory.segment in (Register.FS,Register.GS):
            continue
        address=memory.displacement
        for reg,scale in ((memory.base,1),(memory.index,memory.scale)):
            if reg==Register.NONE:continue
            full=NAMES.get(RegisterExt.full_register(reg))
            if full not in registers['general']:break
            value=int(registers['general'][full],16)
            if RegisterExt.is_gpr32(reg):value&=0xffffffff
            address+=value*scale
        else:
            address&=0xffffffff if memory.address_size==CodeSize.CODE32 else 0xffffffffffffffff
            if address<=fault_address<address+size:
                # The native write bit is authoritative for conditional writes.
                read=memory.access in READS
                write=access_code==1 and memory.access in WRITES
                if access_code==0 and not read:continue
                if access_code==1 and not write:continue
                accesses.append({'address':address,'length':size,'read':read,'write':write})
    if not accesses:
        raise ValueError('Guard access cannot be classified exactly; stopped without guessing its range')
    return {'instruction':str(instruction),'fetch':False,'ranges':accesses}


def check_fetch_watch_alias(raw, registers, fault_address, watches):
    """Do not silently lose a data watch when fetching clears the same guard page."""
    page=fault_address&~0xfff
    if not any(low<page+4096 and page<high for low,high in watches):return
    instruction=Decoder(64,raw,ip=int(registers['rip'],16)).decode()
    if instruction.is_invalid:raise ValueError('Cannot classify instruction on a watched code page')
    operands=list(InstructionInfoFactory().info(instruction).used_memory())
    if not operands:return
    # A fetch is not a data-access observation. Reject this mixed-page case
    # rather than inventing a hit or executing with its data guard cleared.
    for memory in operands:
        if memory.vsib_size or memory.segment in (Register.FS,Register.GS):
            raise ValueError('Data watch on fetched code page has an unresolved memory operand')
        size=MemorySizeExt.info(memory.memory_size).size
        if not size:raise ValueError('Data watch on fetched code page has an unknown operand width')
        address=memory.displacement
        for reg,scale in ((memory.base,1),(memory.index,memory.scale)):
            if reg==Register.NONE:continue
            full=NAMES.get(RegisterExt.full_register(reg))
            if full not in registers['general']:raise ValueError('Unresolved watched code-page operand')
            value=int(registers['general'][full],16)
            if RegisterExt.is_gpr32(reg):value&=0xffffffff
            address+=value*scale
        address&=0xffffffff if memory.address_size==CodeSize.CODE32 else 0xffffffffffffffff
        if address<page+4096 and page<address+size:
            raise ValueError('Data operand shares the fetched guard page; stop and remove this watch before continuing')
