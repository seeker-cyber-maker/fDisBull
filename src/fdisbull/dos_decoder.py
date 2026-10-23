"""16-bit real-mode decoding with explicit CS and bounded constant propagation.

This is a static transfer function, not an emulator. Unknown effective addresses
remain unknown; known segment:offset pairs are reported as real-mode linear sums.
A20 wrapping and descriptor/protected-mode semantics are outside this interface.
"""
from __future__ import annotations

import iced_x86 as ix

_GP = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp')
_SEG = ('ds', 'es', 'ss', 'fs', 'gs')
_BYTE = {'al': ('ax', 0), 'ah': ('ax', 8), 'bl': ('bx', 0), 'bh': ('bx', 8),
         'cl': ('cx', 0), 'ch': ('cx', 8), 'dl': ('dx', 0), 'dh': ('dx', 8)}
_REG_NAMES = {getattr(ix.Register, name.upper()): name for name in (*_GP, *_SEG, *_BYTE, 'cs')}
_IMMEDIATES = {getattr(ix.OpKind, name) for name in dir(ix.OpKind) if name.startswith('IMMEDIATE')}
_WRITE_ACCESS = {ix.OpAccess.WRITE, ix.OpAccess.COND_WRITE, ix.OpAccess.READ_WRITE, ix.OpAccess.READ_COND_WRITE}
_FULL_NAMES = {}
for _name in _GP:
    _full = ix.RegisterExt.full_register(getattr(ix.Register, _name.upper()))
    _FULL_NAMES[_full] = _name


def _state(registers: dict[str, int] | None) -> dict[str, int]:
    if registers is None:
        return {}
    if not isinstance(registers, dict):
        raise ValueError('register state must be a dictionary')
    result = {}
    for name, value in registers.items():
        if name not in (*_GP, *_SEG, *_BYTE):
            continue
        width = 8 if name in _BYTE else 16
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << width:
            raise ValueError(f'{name} must be a known unsigned {width}-bit value')
        result[name] = value
    return result


def _read(register: int, state: dict[str, int], cs: int) -> int | None:
    name = _REG_NAMES.get(register)
    if name == 'cs':
        return cs
    if name in _BYTE:
        parent, shift = _BYTE[name]
        if parent in state:
            return (state[parent] >> shift) & 0xff
    return state.get(name)


def _invalidate(register: int, state: dict[str, int]) -> None:
    name = _REG_NAMES.get(register)
    if name in _BYTE:
        state.pop(_BYTE[name][0], None)
        state.pop(name, None)
    elif name in _GP:
        state.pop(name, None)
        for byte_name, (parent, _) in _BYTE.items():
            if parent == name:
                state.pop(byte_name, None)
    elif name in _SEG:
        state.pop(name, None)
    elif ix.RegisterExt.is_gpr(register):
        parent = _FULL_NAMES.get(ix.RegisterExt.full_register(register))
        if parent:
            _invalidate(getattr(ix.Register, parent.upper()), state)


def _write(register: int, value: int | None, state: dict[str, int], before: dict[str, int]) -> None:
    if value is None:
        return
    name = _REG_NAMES.get(register)
    if name in _BYTE:
        parent, shift = _BYTE[name]
        state[name] = value & 0xff
        if parent in before:
            state[parent] = (before[parent] & ~(0xff << shift)) | ((value & 0xff) << shift)
    elif name in (*_GP, *_SEG):
        state[name] = value & 0xffff


def _offset(instruction, state, cs, unresolved):
    offset = int(instruction.memory_displacement)
    for register, scale in [(instruction.memory_base, 1), (instruction.memory_index, instruction.memory_index_scale)]:
        if register == ix.Register.NONE:
            continue
        if not ix.RegisterExt.is_gpr16(register):
            unresolved.append('32-bit effective-address register is not tracked in the 16-bit register state')
            return None
        value = _read(register, state, cs)
        if value is None:
            unresolved.append(f'unknown effective-address register {_REG_NAMES.get(register, register)}')
            return None
        offset += value * scale
    if instruction.memory_base == ix.Register.NONE and instruction.memory_index == ix.Register.NONE and offset > 0xffff:
        unresolved.append('absolute effective offset exceeds the supported 16-bit segment range')
        return None
    return offset & 0xffff


def decode_dos(data: bytes, address: int, cs: int,
               registers: dict[str, int] | None = None) -> dict | None:
    """Decode one instruction at ``CS:(address-CS*16)`` and transfer constants.

    CS is an actual relocated real-mode segment, not a paragraph-relative file
    coordinate. ``registers`` contains only known constants. Unknown writes
    invalidate aliases. CALL leaves register policy to the graph analyzer.
    Memory reads are not fabricated; LDS/LES and indirect memory branches expose
    descriptors for a caller that owns the mapped bytes.
    """
    if isinstance(cs, bool) or not isinstance(cs, int) or not 0 <= cs <= 0xffff:
        raise ValueError('CS must be an unsigned 16-bit segment')
    if isinstance(address, bool) or not isinstance(address, int):
        raise ValueError('instruction address must be an integer')
    ip = address - (cs << 4)
    if not 0 <= ip <= 0xffff:
        raise ValueError('instruction address is outside the supplied CS segment')
    if not isinstance(data, bytes):
        raise ValueError('instruction bytes must be bytes')
    if not data:
        return None
    instruction = ix.Decoder(16, data[:15], ip=ip).decode()
    if instruction.is_invalid or ip + instruction.len > 0x10000:
        return None
    before = _state(registers)
    after = dict(before)
    unresolved = []
    formatter = ix.Formatter(ix.FormatterSyntax.NASM)
    text = formatter.format(instruction)
    mnemonic, _, operands = text.partition(' ')
    flow = {
        ix.FlowControl.NEXT: 'next', ix.FlowControl.UNCONDITIONAL_BRANCH: 'jump',
        ix.FlowControl.INDIRECT_BRANCH: 'indirect_jump', ix.FlowControl.CONDITIONAL_BRANCH: 'conditional',
        ix.FlowControl.RETURN: 'return', ix.FlowControl.CALL: 'call',
        ix.FlowControl.INDIRECT_CALL: 'indirect_call', ix.FlowControl.INTERRUPT: 'next',
        ix.FlowControl.EXCEPTION: 'stop', ix.FlowControl.XBEGIN_XABORT_XEND: 'conditional',
    }.get(instruction.flow_control, 'stop')
    if instruction.mnemonic in (ix.Mnemonic.HLT, ix.Mnemonic.INT3, ix.Mnemonic.XABORT):
        flow = 'stop'
    elif instruction.mnemonic == ix.Mnemonic.XEND:
        flow = 'next'
    references, data_refs, immediates = [], [], []
    target = target_cs = None
    far = instruction.op_count > 0 and instruction.op0_kind in (ix.OpKind.FAR_BRANCH16, ix.OpKind.FAR_BRANCH32)
    far = far or instruction.code in (ix.Code.CALL_M1616, ix.Code.CALL_M1632, ix.Code.JMP_M1616, ix.Code.JMP_M1632)
    far = far or instruction.mnemonic in (ix.Mnemonic.RETF, ix.Mnemonic.IRET, ix.Mnemonic.IRETD)
    for index in range(instruction.op_count):
        kind = instruction.op_kind(index)
        if kind in _IMMEDIATES:
            immediates.append(dict(operand_index=index, value=instruction.immediate(index) & ((1 << 64) - 1)))
        if kind in (ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32):
            offset = instruction.near_branch_target
            if offset <= 0xffff:
                target_cs, target = cs, (cs << 4) + offset
            else:
                unresolved.append('near branch offset exceeds the supported 16-bit CS range')
        elif kind in (ix.OpKind.FAR_BRANCH16, ix.OpKind.FAR_BRANCH32):
            offset = instruction.far_branch16 if kind == ix.OpKind.FAR_BRANCH16 else instruction.far_branch32
            if offset <= 0xffff:
                target_cs = instruction.far_branch_selector
                target = (target_cs << 4) + offset
            else:
                unresolved.append('far32 branch offset exceeds the supported 16-bit target segment range')
        if target is not None and kind in (ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32, ix.OpKind.FAR_BRANCH16, ix.OpKind.FAR_BRANCH32):
            references.append(dict(operand_index=index, role='code', target=target,
                                   width=4 if kind in (ix.OpKind.FAR_BRANCH16, ix.OpKind.NEAR_BRANCH32) else 6 if kind == ix.OpKind.FAR_BRANCH32 else 2))
    memory_indices = [index for index in range(instruction.op_count) if instruction.op_kind(index) == ix.OpKind.MEMORY]
    effective_offset = pointer_address = None
    if memory_indices:
        effective_offset = _offset(instruction, before, cs, unresolved)
        segment = _read(instruction.memory_segment, before, cs)
        if segment is None:
            unresolved.append(f'unknown memory segment {_REG_NAMES.get(instruction.memory_segment, instruction.memory_segment)}')
        if effective_offset is not None and segment is not None:
            pointer_address = (segment << 4) + effective_offset
            width = ix.MemorySizeExt.size(instruction.memory_size) or None
            role = 'address' if instruction.mnemonic == ix.Mnemonic.LEA else 'memory'
            references.append(dict(operand_index=memory_indices[0], role=role, target=pointer_address, width=width))
            data_refs.append(pointer_address)
    if any(instruction.op_kind(i) not in (ix.OpKind.REGISTER, ix.OpKind.MEMORY, *_IMMEDIATES,
               ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32, ix.OpKind.FAR_BRANCH16, ix.OpKind.FAR_BRANCH32)
           for i in range(instruction.op_count)):
        unresolved.append('implicit string-memory addresses are not resolved by this transfer function')

    result = dict(address=address, size=instruction.len, bytes=data[:instruction.len].hex(),
                  mnemonic=mnemonic, operands=operands, text=text, flow=flow, target=target,
                  target_cs=target_cs, data_refs=data_refs, references=references, immediates=immediates,
                  cs=cs, ip=ip, next_address=(cs << 4) + ((ip + instruction.len) & 0xffff),
                  next_registers=after, unresolved=unresolved, far=bool(far))
    if flow in ('indirect_call', 'indirect_jump'):
        if memory_indices:
            offset_size = 4 if instruction.code in (ix.Code.CALL_M1632, ix.Code.JMP_M1632, ix.Code.CALL_RM32, ix.Code.JMP_RM32) else 2
            result['indirect'] = dict(pointer_address=pointer_address, offset_size=offset_size,
                                      far=bool(far), kind='call' if flow == 'indirect_call' else 'jump')
            if pointer_address is None:
                unresolved.append('indirect branch pointer address is unknown')
            else:
                unresolved.append('indirect branch target requires mapped pointer bytes from the caller')
        elif instruction.op_count and instruction.op0_kind == ix.OpKind.REGISTER:
            value = _read(instruction.op0_register, before, cs)
            if value is not None:
                result['target_cs'], result['target'] = cs, (cs << 4) + value
                references.append(dict(operand_index=0, role='code', target=result['target'], width=2))
            else:
                unresolved.append('indirect branch register value is unknown')

    information = ix.InstructionInfoFactory().info(instruction)
    if flow in ('call', 'indirect_call'):
        # Operand-size prefixes affect the actual stack slots, not merely the
        # far-pointer encoding width. Keep iced's signed architectural effect.
        result['call_stack_adjust'] = instruction.stack_pointer_increment

    # Generic writes first invalidate every affected tracked alias. Modeled
    # operations then add only the constants they can establish independently.
    if flow not in ('call', 'indirect_call'):
        for used in information.used_registers():
            if used.access in _WRITE_ACCESS:
                _invalidate(used.register, after)
    if instruction.op_count and instruction.op0_kind == ix.OpKind.REGISTER:
        destination = instruction.op0_register
        value = None
        if instruction.mnemonic == ix.Mnemonic.MOV and instruction.op_count == 2:
            if instruction.op1_kind in _IMMEDIATES:
                value = instruction.immediate(1)
            elif instruction.op1_kind == ix.OpKind.REGISTER:
                value = _read(instruction.op1_register, before, cs)
        elif instruction.mnemonic == ix.Mnemonic.XOR and instruction.op_count == 2 and instruction.op1_kind == ix.OpKind.REGISTER and instruction.op1_register == destination:
            value = 0
        elif instruction.mnemonic in (ix.Mnemonic.ADD, ix.Mnemonic.SUB) and instruction.op_count == 2 and instruction.op1_kind in _IMMEDIATES:
            original = _read(destination, before, cs)
            if original is not None:
                value = original + instruction.immediate(1) * (1 if instruction.mnemonic == ix.Mnemonic.ADD else -1)
        elif instruction.mnemonic == ix.Mnemonic.LEA:
            value = effective_offset
        _write(destination, value, after, before)
    if instruction.mnemonic in (ix.Mnemonic.LDS, ix.Mnemonic.LES) and instruction.op_count == 2:
        segment_name = 'ds' if instruction.mnemonic == ix.Mnemonic.LDS else 'es'
        _invalidate(getattr(ix.Register, segment_name.upper()), after)
        offset_size = 4 if ix.RegisterExt.size(instruction.op0_register) == 4 else 2
        result['load_far'] = dict(linear=pointer_address, width=offset_size + 2,
                                  register=_REG_NAMES.get(instruction.op0_register),
                                  segment_register=segment_name, offset_size=offset_size)
        unresolved.append('far-pointer load requires mapped bytes from the caller')
    if instruction.mnemonic == ix.Mnemonic.PUSH:
        value = None
        if instruction.op0_kind == ix.OpKind.REGISTER:
            value = _read(instruction.op0_register, before, cs)
        elif instruction.op0_kind in _IMMEDIATES:
            value = instruction.immediate(0) & 0xffff
        result['push_value'] = value if abs(instruction.stack_pointer_increment) == 2 else None
        result['push_width'] = abs(instruction.stack_pointer_increment)
        if result['push_width'] != 2:
            unresolved.append('32-bit stack value is not tracked in the 16-bit abstract stack')
    elif instruction.mnemonic == ix.Mnemonic.POP and instruction.op0_kind == ix.OpKind.REGISTER:
        result['pop_register'] = _REG_NAMES.get(instruction.op0_register)
        result['pop_width'] = abs(instruction.stack_pointer_increment)
    if instruction.mnemonic in (ix.Mnemonic.PUSH, ix.Mnemonic.POP) and 'sp' in before:
        overwrites_sp = instruction.mnemonic == ix.Mnemonic.POP and instruction.op0_kind == ix.OpKind.REGISTER and ix.RegisterExt.full_register(instruction.op0_register) == ix.RegisterExt.full_register(ix.Register.SP)
        if not overwrites_sp:
            after['sp'] = (before['sp'] + instruction.stack_pointer_increment) & 0xffff
    if instruction.mnemonic == ix.Mnemonic.INT:
        vector = instruction.immediate8
        ah = _read(ix.Register.AH, before, cs)
        if vector == 0x21 and ah == 0x30:
            for name in ('ax', 'bx', 'cx'):
                _invalidate(getattr(ix.Register, name.upper()), after)
        else:
            for name in _GP:
                _invalidate(getattr(ix.Register, name.upper()), after)
            result['stack_reset'] = True
            unresolved.append('interrupt GP results unknown; retained segment constants use the conventional DOS preservation assumption')
        if vector == 0x20 or (vector == 0x21 and ah in (0, 0x31, 0x4c)):
            result['flow'] = 'stop'
    # The graph analyzer owns its bounded abstract value stack. Tell it when
    # architectural changes make those saved values unsafe to reuse. Native
    # register tracking alone cannot invalidate a separate Python stack list.
    modeled_push = instruction.mnemonic == ix.Mnemonic.PUSH and abs(instruction.stack_pointer_increment) == 2
    modeled_pop = (instruction.mnemonic == ix.Mnemonic.POP and instruction.op0_kind == ix.OpKind.REGISTER
                   and abs(instruction.stack_pointer_increment) == 2
                   and _REG_NAMES.get(instruction.op0_register) in (*_GP, *_SEG)
                   and instruction.op0_register not in (ix.Register.SP, ix.Register.SS))
    reasons = []
    for used in information.used_registers():
        if used.access not in _WRITE_ACCESS:
            continue
        stack_register = (used.register == ix.Register.SS or
                          (ix.RegisterExt.is_gpr(used.register) and
                           ix.RegisterExt.full_register(used.register) == ix.RegisterExt.full_register(ix.Register.SP)))
        if stack_register and not (modeled_push or modeled_pop):
            reasons.append('unmodeled SP/SS write')
            break
    if not modeled_push:
        stack_segment = before.get('ss')
        for memory in information.used_memory():
            if memory.access not in _WRITE_ACCESS:
                continue
            possible_alias = True
            if memory.segment != ix.Register.SS and stack_segment is not None:
                stack_base = stack_segment << 4
                if pointer_address is not None and memory_indices and memory.segment == instruction.memory_segment:
                    width = ix.MemorySizeExt.size(memory.memory_size)
                    possible_alias = not width or pointer_address < stack_base + 0x10000 and pointer_address + width > stack_base
                else:
                    memory_segment = _read(memory.segment, before, cs)
                    if memory_segment is not None:
                        memory_base = memory_segment << 4
                        possible_alias = memory_base < stack_base + 0x10000 and memory_base + 0x10000 > stack_base
            if possible_alias:
                reasons.append('memory write may alias stack storage')
                break
    if result.get('stack_reset'):
        reasons.append('unknown interrupt stack-pointer result')
    result['stack_reset'] = bool(reasons)
    if reasons:
        unresolved.append('abstract stack invalidated: ' + '; '.join(reasons))
    return result
