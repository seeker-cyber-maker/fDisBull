"""Little-endian M-class Thumb instruction facts, without execution/state guesses."""
import capstone as cs
from capstone import arm


def decoder():
    engine = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_THUMB | cs.CS_MODE_MCLASS | cs.CS_MODE_LITTLE_ENDIAN)
    engine.detail = True
    return engine


def native(data, address):
    if address & 1 or not 0 <= address < 1 << 32 or len(data) < 2:
        return None
    return next(decoder().disasm(data[:4], address, count=1), None)


def memory_width(ins):
    """Known transfer width from native operands, without a CPU/state claim."""
    op = ins.mnemonic.split('.')[0]
    widths = {'ldrb':1, 'ldrsb':1, 'strb':1, 'tbb':1,
              'ldrh':2, 'ldrsh':2, 'strh':2, 'tbh':2,
              'ldr':4, 'str':4, 'ldrd':8, 'strd':8}
    if op in ('vldr','vstr') and ins.operands and ins.operands[0].type == arm.ARM_OP_REG:
        return {'s':4, 'd':8}.get(ins.reg_name(ins.operands[0].reg)[:1])
    return widths.get(op)


def decode_thumb(data, address):
    ins = native(data, address)
    if ins is None or address + ins.size > 1 << 32:
        return None
    operands = ins.operands
    op = ins.mnemonic.split('.')[0]
    flow, target, refs, immediates, literals = 'next', None, [], [], []
    conditional = ins.cc not in (arm.ARM_CC_INVALID, arm.ARM_CC_AL)
    if ins.id in (arm.ARM_INS_B, arm.ARM_INS_CBZ, arm.ARM_INS_CBNZ, arm.ARM_INS_BL):
        flow = 'call' if ins.id == arm.ARM_INS_BL else 'conditional' if conditional or ins.id in (arm.ARM_INS_CBZ, arm.ARM_INS_CBNZ) else 'jump'
        index = next((i for i in range(len(operands)-1, -1, -1) if operands[i].type == arm.ARM_OP_IMM), None)
        if index is not None:
            target = operands[index].imm & 0xffffffff
            refs.append(dict(operand_index=index, role='code', target=target, width=4))
    elif ins.id == arm.ARM_INS_BLX:
        # Immediate BLX changes to ARM state, which Cortex-M cannot execute.
        flow = 'stop' if any(o.type == arm.ARM_OP_IMM for o in operands) else 'indirect_call'
    elif ins.id == arm.ARM_INS_BX:
        flow = 'return' if operands and operands[0].type == arm.ARM_OP_REG and operands[0].reg == arm.ARM_REG_LR else 'indirect_jump'
    elif ins.id in (arm.ARM_INS_TBB, arm.ARM_INS_TBH):
        flow = 'indirect_jump'
    elif ins.id in (arm.ARM_INS_UDF, arm.ARM_INS_BKPT, arm.ARM_INS_SVC):
        # Exception handlers/returns require runtime state; no invented edge.
        flow = 'stop'
    else:
        try:
            _, writes = ins.regs_access()
        except cs.CsError:
            writes = []
        if arm.ARM_REG_PC in writes:
            flow = 'return' if ins.id == arm.ARM_INS_POP else 'indirect_jump'
    if conditional and flow in ('jump', 'return', 'indirect_jump', 'stop'):
        flow = 'conditional'
    for index, operand in enumerate(operands):
        if operand.type == arm.ARM_OP_IMM and not (target is not None and operand.imm & 0xffffffff == target):
            immediates.append(dict(operand_index=index, value=operand.imm & 0xffffffff))
        if operand.type == arm.ARM_OP_MEM and operand.mem.base == arm.ARM_REG_PC and not operand.mem.index:
            literal = (((address + 4) & ~3) + operand.mem.disp) & 0xffffffff
            width = memory_width(ins) if op.startswith('ld') or op == 'vldr' else None
            refs.append(dict(operand_index=index, role='memory', target=literal, width=width))
            if width:
                literals.append(dict(address=literal, size=width))
        if ins.id == arm.ARM_INS_ADR and operand.type == arm.ARM_OP_IMM:
            value = (((address + 4) & ~3) + operand.imm) & 0xffffffff
            refs.append(dict(operand_index=index, role='address', target=value, width=4))
        elif (op in ('addw','subw') and index == 2
              and operands[1].type == arm.ARM_OP_REG and operands[1].reg == arm.ARM_REG_PC
              and operand.type == arm.ARM_OP_IMM):
            # Capstone retains the ADDW/SUBW spelling of the ADR.W alias,
            # while some engine versions use the ordinary ADD/SUB IDs.
            delta = -operand.imm if op == 'subw' else operand.imm
            value = (((address + 4) & ~3) + delta) & 0xffffffff
            refs.append(dict(operand_index=index, role='address', target=value, width=4))
    # IT is decoded alone; later predicates are tracked by the project, not by
    # Capstone's mutable disassembly-stream IT state.
    it_slots = len(ins.mnemonic) - 1 if ins.id == arm.ARM_INS_IT else 0
    return dict(address=address, size=ins.size, bytes=bytes(ins.bytes).hex(),
                mnemonic=ins.mnemonic, operands=ins.op_str, text=ins.mnemonic+' '+ins.op_str,
                flow=flow, target=target, data_refs=[r['target'] for r in refs if r['role'] != 'code'],
                references=refs, immediates=immediates, literals=literals, it_slots=it_slots)
