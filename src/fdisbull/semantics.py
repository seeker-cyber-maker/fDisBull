"""Small, conservative CPU-to-IR adapters for static data-flow analysis.

Expressions and transfers are JSON values. Every assignment and stored value
reads the instruction's pre-state. Unsupported writes clobber their aliases;
unsupported instructions never acquire guessed mathematical semantics. This is
an analysis vocabulary, not an instruction emulator or a decompiler.
"""
from __future__ import annotations

from functools import lru_cache

import capstone as cap
import iced_x86 as ix

from .memory import instruction_memory_accesses

_NAMES = {value: name.lower() for name, value in vars(ix.Register).items()
          if name.isupper() and isinstance(value, int)}
_WRITE = {ix.OpAccess.WRITE, ix.OpAccess.COND_WRITE, ix.OpAccess.READ_WRITE, ix.OpAccess.READ_COND_WRITE}
_IMMEDIATES = {getattr(ix.OpKind, name) for name in dir(ix.OpKind) if name.startswith('IMMEDIATE')}
_FAMILIES = {}
for _register, _name in _NAMES.items():
    if ix.RegisterExt.is_gpr(_register):
        _FAMILIES.setdefault(ix.RegisterExt.full_register(_register), []).append(_name)


def const(value):
    return {'op': 'const', 'value': int(value)}


def reg(name):
    return {'op': 'reg', 'name': name}


def unknown(reason):
    return {'op': 'unknown', 'reason': reason}


def operation(op, left, right):
    """Construct a compact binary expression without interpreting CPU state."""
    if left.get('op') == right.get('op') == 'const':
        a, b = left['value'], right['value']
        if op == 'add':
            return const(a + b)
        if op == 'sub':
            return const(a - b)
        if op == 'mul':
            return const(a * b)
        if op == 'and':
            return const(a & b)
        if op == 'shl' and 0 <= b <= 4096:
            return const(a << b)
    if right == const(0) and op in ('add', 'sub', 'shl'):
        return left
    if left == const(0) and op == 'add':
        return right
    if right == const(1) and op == 'mul':
        return left
    if left == const(1) and op == 'mul':
        return right
    if op == 'mul' and (left == const(0) or right == const(0)):
        return const(0)
    return {'op': op, 'args': [left, right]}


def load(address, width, signed=False, stack_address=None):
    result = {'op': 'load', 'address': address, 'width': width, 'signed': bool(signed)}
    if stack_address is not None:
        result['stack_address'] = stack_address
    return result


def _read_memory(record, signed=False, width=None):
    return load(record['address'], width or record['width'], signed, record.get('stack_address'))


def _signed(value, bits):
    # The difference between the low bits and the sign bit is ordinary signed
    # extension, expressed using only generic arithmetic and bitwise AND.
    return operation('sub', operation('and', value, const((1 << (bits - 1)) - 1)),
                     operation('and', value, const(1 << (bits - 1))))


def _canonical(register, bits):
    if not ix.RegisterExt.is_gpr(register):
        return _NAMES.get(register, f'register_{register}')
    family = _FAMILIES[ix.RegisterExt.full_register(register)]
    width = ix.RegisterExt.size(register) * 8
    desired = max(bits, width)
    return next((name for name in family if ix.RegisterExt.size(getattr(ix.Register, name.upper())) * 8 == desired), _NAMES[register])


def _xreg(register, bits):
    name = _NAMES.get(register, f'register_{register}')
    if name in ('ah', 'bh', 'ch', 'dh'):
        return unknown('high-byte register extraction is outside this IR slice')
    canonical = _canonical(register, bits)
    value = reg(canonical)
    if ix.RegisterExt.is_gpr(register) and ix.RegisterExt.size(register) * 8 < bits:
        value = operation('and', value, const((1 << (ix.RegisterExt.size(register) * 8)) - 1))
    return value


def _alias_names(register):
    return _FAMILIES.get(ix.RegisterExt.full_register(register), [_NAMES.get(register)]) if ix.RegisterExt.is_gpr(register) else [_NAMES.get(register)]


def _assignment(register, value, bits):
    """Model full writes and x86-64's zero-extending 32-bit writes only."""
    size = ix.RegisterExt.size(register) * 8
    name = _canonical(register, bits)
    if ix.RegisterExt.is_gpr(register) and size < bits and not (bits == 64 and size == 32):
        return []
    result = [dict(register=name, value=value, bits=bits if bits == 64 and size == 32 else size)]
    if bits == 64 and size == 32:
        result[0]['value'] = operation('and', value, const(0xffffffff))
    # Operand-size overrides can establish a wider value and its mode-sized
    # alias, while a narrow write never establishes an unknown wider value.
    if ix.RegisterExt.is_gpr(register) and size > bits:
        family = _FAMILIES[ix.RegisterExt.full_register(register)]
        smaller = next((n for n in family if ix.RegisterExt.size(getattr(ix.Register, n.upper())) * 8 == bits), None)
        if smaller:
            result.append(dict(register=smaller, value=operation('and', value, const((1 << bits) - 1)), bits=bits))
    return result


def _memory(raw, address, arch, bits, cs):
    records = []
    for fact in instruction_memory_accesses(raw, address, arch, bits, cs=cs):
        displacement = fact['displacement']
        address_bits = fact['address_bits']
        if displacement >= 1 << (address_bits - 1):
            displacement -= 1 << address_bits
        offset = const(displacement)
        if fact.get('ip_relative') and fact.get('concrete_target') is not None:
            offset = const(fact['concrete_target'])
        else:
            for name, scale in ((fact['base_register'], 1), (fact['index_register'], fact['scale'])):
                if not name:
                    continue
                value = _xreg(getattr(ix.Register, name.upper()), bits) if arch == 'x86' and hasattr(ix.Register, name.upper()) else _areg(name) if arch == 'arm64' else reg(name)
                offset = operation('add', offset, operation('mul', value, const(scale)))
        unwrapped = offset
        if arch == 'x86' and address_bits < 64:
            offset = operation('and', offset, const((1 << address_bits) - 1))
        segment = fact['segment_register']
        physical = offset
        if fact['access'] != 'address_only':
            if arch == 'x86' and bits == 16:
                base = const(cs * 16) if segment == 'cs' and cs is not None else operation('mul', reg(segment or 'unknown_segment'), const(16))
                physical = operation('add', base, offset)
            elif arch == 'x86' and segment in ('fs', 'gs'):
                physical = operation('add', reg(segment + '_base'), offset)
        records.append(dict(address=physical, offset=offset, unwrapped_offset=unwrapped,
                            access=fact['access'], width=fact['width'], value=None,
                            segment_register=segment, address_bits=address_bits,
                            operand_index=fact['operand_index'], implicit=fact['implicit'],
                            conditional_read=fact['conditional_read'], conditional_write=fact['conditional_write'],
                            repeat=fact.get('repeat')))
        if (arch == 'x86' and segment == 'ss') or (arch == 'arm64' and fact['base_register'] in ('sp', 'wsp', 'fp', 'x29')):
            records[-1]['stack_address'] = unwrapped
    return records


def _empty(address, arch, bits):
    return dict(valid=False, address=address, arch=arch, bits=bits, size=0, flow='invalid',
                next_address=None, target=None, target_context=None, assignments=[], clobbers=[],
                memory=[], stack_pointer=None, frame_pointer=None, stack_delta=None, return_pop=None,
                return_address_size=None, return_kind=None, far=False, comparison=None,
                flags_clobbered=False, branch_condition=None, indirect_target=None, target_constraints=[], memory_reset=False, unresolved=[])


_JCC = {'je': 'eq', 'jne': 'ne', 'jb': 'lt_u', 'jae': 'ge_u', 'jbe': 'le_u', 'ja': 'gt_u',
        'jl': 'lt_s', 'jge': 'ge_s', 'jle': 'le_s', 'jg': 'gt_s'}


def _x86(raw, address, bits, cs):
    ip = address - cs * 16 if cs is not None else address
    ins = ix.Decoder(bits, raw[:15], ip=ip).decode()
    result = _empty(address, 'x86', bits)
    if ins.is_invalid or (cs is not None and ip + ins.len > 0x10000):
        return result
    formatter = ix.Formatter(ix.FormatterSyntax.NASM)
    text = formatter.format(ins)
    mnemonic = text.split(' ')[0]
    info = ix.InstructionInfoFactory().info(ins)
    flow = {ix.FlowControl.NEXT: 'next', ix.FlowControl.UNCONDITIONAL_BRANCH: 'jump',
            ix.FlowControl.INDIRECT_BRANCH: 'indirect_jump', ix.FlowControl.CONDITIONAL_BRANCH: 'conditional',
            ix.FlowControl.CALL: 'call', ix.FlowControl.INDIRECT_CALL: 'indirect_call',
            ix.FlowControl.RETURN: 'return', ix.FlowControl.INTERRUPT: 'next',
            ix.FlowControl.EXCEPTION: 'stop', ix.FlowControl.XBEGIN_XABORT_XEND: 'conditional'}.get(ins.flow_control, 'stop')
    if ins.mnemonic in (ix.Mnemonic.HLT, ix.Mnemonic.INT3, ix.Mnemonic.XABORT):
        flow = 'stop'
    sp, bp = {16: ('sp', 'bp'), 32: ('esp', 'ebp'), 64: ('rsp', 'rbp')}[bits]
    result.update(valid=True, size=ins.len, flow=flow, next_address=(cs * 16 + ((ip + ins.len) & 0xffff)) if cs is not None else ins.next_ip,
                  mnemonic=mnemonic, text=text, stack_pointer=sp, frame_pointer=bp,
                  stack_delta=ins.stack_pointer_increment, memory=_memory(raw[:ins.len], address, 'x86', bits, cs),
                  flags_clobbered=bool(ins.rflags_written | ins.rflags_cleared | ins.rflags_set | ins.rflags_undefined))
    clobbers = set()
    for used in info.used_registers():
        if used.access in _WRITE:
            clobbers.update(n for n in _alias_names(used.register) if n)
    result['clobbers'] = sorted(clobbers)
    if 'ss' in clobbers:
        result['memory_reset'] = True
        result['unresolved'].append('stack address-space register changes invalidate prior abstract stack storage')
    explicit = next((m for m in result['memory'] if not m['implicit']), None)

    def operand(index, signed=False):
        kind = ins.op_kind(index)
        if kind == ix.OpKind.REGISTER:
            return _xreg(ins.op_register(index), bits)
        if kind in _IMMEDIATES:
            value = ins.immediate(index)
            if kind in (ix.OpKind.IMMEDIATE8TO16, ix.OpKind.IMMEDIATE8TO32, ix.OpKind.IMMEDIATE8TO64, ix.OpKind.IMMEDIATE32TO64):
                width = {ix.OpKind.IMMEDIATE8TO16: 16, ix.OpKind.IMMEDIATE8TO32: 32,
                         ix.OpKind.IMMEDIATE8TO64: 64, ix.OpKind.IMMEDIATE32TO64: 64}[kind]
                if value & (1 << (width - 1)):
                    value -= 1 << width
            return const(value)
        if kind == ix.OpKind.MEMORY and explicit:
            return _read_memory(explicit, signed)
        return unknown('unsupported operand expression')

    def assign(index, value):
        if ins.op_kind(index) == ix.OpKind.REGISTER:
            result['assignments'].extend(_assignment(ins.op_register(index), value, bits))
        elif ins.op_kind(index) == ix.OpKind.MEMORY and explicit:
            explicit['value'] = value

    destination = ins.op0_register if ins.op_count and ins.op0_kind == ix.OpKind.REGISTER else None
    destination_bits = ix.RegisterExt.size(destination) * 8 if destination is not None else ((explicit['width'] or bits // 8) * 8 if explicit else bits)
    if ins.mnemonic in (ix.Mnemonic.MOV, ix.Mnemonic.MOVZX) and ins.op_count == 2:
        assign(0, operand(1))
    elif ins.mnemonic in (ix.Mnemonic.MOVSX, ix.Mnemonic.MOVSXD) and ins.op_count == 2:
        assign(0, operand(1, signed=True) if ins.op1_kind == ix.OpKind.MEMORY else _signed(operand(1), ix.RegisterExt.size(ins.op1_register) * 8) if ins.op1_kind == ix.OpKind.REGISTER else unknown('unsupported sign extension source'))
    elif ins.mnemonic == ix.Mnemonic.LEA and explicit:
        assign(0, explicit['offset'])
    elif ins.mnemonic in (ix.Mnemonic.ADD, ix.Mnemonic.SUB, ix.Mnemonic.AND, ix.Mnemonic.SHL, ix.Mnemonic.SAL, ix.Mnemonic.IMUL):
        op = {ix.Mnemonic.ADD: 'add', ix.Mnemonic.SUB: 'sub', ix.Mnemonic.AND: 'and',
              ix.Mnemonic.SHL: 'shl', ix.Mnemonic.SAL: 'shl', ix.Mnemonic.IMUL: 'mul'}[ins.mnemonic]
        if ins.op_count == 3 and ins.mnemonic == ix.Mnemonic.IMUL:
            assign(0, operation(op, operand(1), operand(2)))
        elif ins.op_count == 2:
            right = operand(1)
            if op == 'shl':
                right = operation('and', right, const(63 if destination_bits == 64 else 31))
            assign(0, operation(op, operand(0), right))
    elif ins.mnemonic == ix.Mnemonic.XOR and ins.op_count == 2 and ins.op0_kind == ins.op1_kind == ix.OpKind.REGISTER and ins.op0_register == ins.op1_register:
        assign(0, const(0))
    elif ins.mnemonic in (ix.Mnemonic.INC, ix.Mnemonic.DEC, ix.Mnemonic.NEG) and ins.op_count == 1:
        value = operation('sub', const(0), operand(0)) if ins.mnemonic == ix.Mnemonic.NEG else operation('add' if ins.mnemonic == ix.Mnemonic.INC else 'sub', operand(0), const(1))
        assign(0, value)
    elif ins.mnemonic in (ix.Mnemonic.CMP, ix.Mnemonic.TEST) and ins.op_count == 2:
        left, right = operand(0), operand(1)
        if ins.mnemonic == ix.Mnemonic.TEST:
            left, right = operation('and', left, right), const(0)
        result['comparison'] = dict(left=left, right=right, bits=destination_bits)
    elif ins.mnemonic == ix.Mnemonic.PUSH and ins.op_count == 1:
        stores = [m for m in result['memory'] if m['access'] in ('write', 'conditional_write') and m['implicit']]
        if len(stores) == 1:
            stores[0]['value'] = operand(0)
    elif ins.mnemonic == ix.Mnemonic.POP and ins.op_count == 1:
        reads = [m for m in result['memory'] if m['access'] == 'read' and m['implicit']]
        if len(reads) == 1:
            assign(0, _read_memory(reads[0]))
    elif ins.mnemonic == ix.Mnemonic.LEAVE:
        width = 2 if ins.code == ix.Code.LEAVEW else 4 if ins.code == ix.Code.LEAVED else 8
        stack_address = reg(bp)
        if bits == 16:
            stack_address = operation('add', operation('mul', reg('ss'), const(16)), operation('and', stack_address, const(0xffff)))
        result['assignments'] += [dict(register=sp, value=operation('add', reg(bp), const(width)), bits=bits),
                                  dict(register=bp, value=load(stack_address, width, stack_address=reg(bp)), bits=bits)]
        result['stack_delta'] = None

    # Stack changes are explicit assignments. Do not overwrite POP SP/LEAVE's
    # stronger destination transfer, and do not call an arbitrary SP write zero.
    if ins.stack_pointer_increment and not any(a['register'] == sp for a in result['assignments']):
        result['assignments'].append(dict(register=sp, value=operation('add', reg(sp), const(ins.stack_pointer_increment)), bits=bits))
    elif sp in clobbers and not any(a['register'] == sp for a in result['assignments']):
        result['stack_delta'] = None
    if any(a['register'] == sp for a in result['assignments']) and not ins.stack_pointer_increment and ins.mnemonic != ix.Mnemonic.LEAVE:
        value = next(a['value'] for a in result['assignments'] if a['register'] == sp)
        result['stack_delta'] = None
        if value.get('op') in ('add', 'sub') and value['args'][0] == reg(sp) and value['args'][1].get('op') == 'const':
            result['stack_delta'] = value['args'][1]['value'] * (1 if value['op'] == 'add' else -1)
    if ins.mnemonic == ix.Mnemonic.POP and destination is not None and _canonical(destination, bits) == sp:
        result['stack_delta'] = None

    near_kinds = (ix.OpKind.NEAR_BRANCH16, ix.OpKind.NEAR_BRANCH32, ix.OpKind.NEAR_BRANCH64)
    if any(ins.op_kind(i) in near_kinds for i in range(ins.op_count)):
        target = ins.near_branch_target
        result['target'] = cs * 16 + target if cs is not None and target <= 0xffff else target if cs is None else None
    if cs is not None and flow in ('call', 'jump', 'conditional', 'indirect_call', 'indirect_jump', 'return'):
        result['target_context'] = f'x86:16:little:cs={cs:04x}'
    if flow in ('indirect_call', 'indirect_jump') and ins.op_count:
        target = operand(0)
        far = ins.code in (ix.Code.CALL_M1616, ix.Code.CALL_M1632, ix.Code.JMP_M1616, ix.Code.JMP_M1632)
        result['far'] = far
        if far and explicit:
            width = 4 if ins.code in (ix.Code.CALL_M1632, ix.Code.JMP_M1632) else 2
            selector = load(operation('add', explicit['address'], const(width)), 2)
            offset = load(explicit['address'], width)
            target = operation('add', operation('mul', selector, const(16)), offset) if bits == 16 else unknown('protected-mode far target needs descriptor state')
            if bits == 16 and width == 4:
                result['target_constraints'].append(dict(expression=offset, min=0, max=0xffff))
            result['target_context'] = dict(template='x86:16:little:cs={segment:04x}', values={'segment': selector}) if bits == 16 else None
        elif cs is not None:
            width = ix.RegisterExt.size(ins.op0_register) if ins.op0_kind == ix.OpKind.REGISTER else explicit['width'] if explicit else 0
            if width == 4:
                result['target_constraints'].append(dict(expression=target, min=0, max=0xffff))
            target = operation('add', const(cs * 16), target)
        result['indirect_target'] = target
    if ins.op_count and ins.op0_kind in (ix.OpKind.FAR_BRANCH16, ix.OpKind.FAR_BRANCH32):
        offset = ins.far_branch16 if ins.op0_kind == ix.OpKind.FAR_BRANCH16 else ins.far_branch32
        result['far'] = True
        if bits == 16 and offset <= 0xffff:
            result['target'] = ins.far_branch_selector * 16 + offset
            result['target_context'] = f'x86:16:little:cs={ins.far_branch_selector:04x}'
        else:
            result['indirect_target'] = unknown('far target requires unsupported descriptor or offset state')
    if flow == 'conditional':
        if mnemonic in _JCC:
            result['branch_condition'] = dict(predicate=_JCC[mnemonic], source='comparison')
        elif mnemonic in ('jcxz', 'jecxz', 'jrcxz'):
            name = {'jcxz': 'cx', 'jecxz': 'ecx', 'jrcxz': 'rcx'}[mnemonic]
            result['branch_condition'] = dict(predicate='eq', left=_xreg(getattr(ix.Register, name.upper()), bits), right=const(0), bits=ix.RegisterExt.size(getattr(ix.Register, name.upper())) * 8)
    if flow == 'return':
        far = ins.mnemonic in (ix.Mnemonic.RETF, ix.Mnemonic.IRET, ix.Mnemonic.IRETD, ix.Mnemonic.IRETQ)
        interrupt = ins.mnemonic in (ix.Mnemonic.IRET, ix.Mnemonic.IRETD, ix.Mnemonic.IRETQ)
        cleanup = ins.immediate(0) if ins.op_count and ins.op0_kind in _IMMEDIATES else 0
        result.update(return_pop=cleanup, return_address_size=ins.stack_pointer_increment-cleanup,
                      return_kind='interrupt' if interrupt else 'far' if far else 'near', far=far)
        reads = [m for m in result['memory'] if m['access'] == 'read']
        if reads:
            width = reads[0]['width'] or bits // 8
            target = _read_memory(reads[0], width=width)
            if cs is not None and not far:
                target = operation('add', const(cs * 16), target)
            elif far:
                target = unknown('far/interrupt return target needs a multi-field stack record')
                result['target_context'] = None
            result['indirect_target'] = target
    if flow in ('call', 'indirect_call'):
        result['return_address_size'] = -ins.stack_pointer_increment
        stores = [m for m in result['memory'] if m['access'] in ('write', 'conditional_write')]
        if len(stores) == 1 and not result['far']:
            stores[0]['value'] = const(ins.next_ip)
    return result


@lru_cache(maxsize=1)
def _arm_decoder():
    decoder = cap.Cs(cap.CS_ARCH_ARM64, cap.CS_MODE_LITTLE_ENDIAN)
    decoder.detail = True
    return decoder


def _areg(name):
    name = {'fp': 'x29', 'lr': 'x30'}.get(name, name)
    if name in ('xzr', 'wzr'):
        return const(0)
    if name and name.startswith('w') and name[1:].isdigit():
        return operation('and', reg('x' + name[1:]), const(0xffffffff))
    if name == 'wsp':
        return operation('and', reg('sp'), const(0xffffffff))
    if name and len(name) > 1 and name[0] in 'bhsdqv' and name[1:].isdigit():
        value = reg('v' + name[1:])
        width = {'b': 8, 'h': 16, 's': 32, 'd': 64}.get(name[0])
        return operation('and', value, const((1 << width) - 1)) if width else value
    return reg(name)


def _arm(raw, address):
    result = _empty(address, 'arm64', 64)
    if len(raw) < 4 or address % 4:
        return result
    ins = next(_arm_decoder().disasm(raw[:4], address, count=1), None)
    if ins is None:
        return result
    mnemonic = ins.mnemonic
    auth_call = mnemonic in ('blraa', 'blrab', 'blraaz', 'blrabz')
    auth_jump = mnemonic in ('braa', 'brab', 'braaz', 'brabz')
    auth_return = mnemonic in ('retaa', 'retab', 'eretaa', 'eretab')
    exception_return = mnemonic in ('eret', 'eretaa', 'eretab')
    flow = 'call' if mnemonic == 'bl' else 'jump' if mnemonic == 'b' else 'indirect_call' if mnemonic == 'blr' or auth_call else 'indirect_jump' if mnemonic == 'br' or auth_jump else 'return' if mnemonic == 'ret' or auth_return or exception_return else 'conditional' if mnemonic.startswith('b.') or mnemonic in ('cbz', 'cbnz', 'tbz', 'tbnz') else 'stop' if mnemonic in ('brk', 'hlt', 'udf') else 'next'
    result.update(valid=True, size=4, mnemonic=mnemonic, text=mnemonic + (' ' + ins.op_str if ins.op_str else ''),
                  flow=flow, next_address=address+4, stack_pointer='sp', frame_pointer='x29', stack_delta=0,
                  memory=_memory(raw[:4], address, 'arm64', 64, None), flags_clobbered=bool(ins.update_flags))
    operands = ins.operands
    _, written = ins.regs_access()
    clobbers = set()
    for register in written:
        name = {'fp': 'x29', 'lr': 'x30'}.get(ins.reg_name(register), ins.reg_name(register))
        if name and name.startswith('w') and name[1:].isdigit():
            name = 'x' + name[1:]
        if name == 'wsp':
            name = 'sp'
        if name and len(name) > 1 and name[0] in 'bhsdqv' and name[1:].isdigit():
            name = 'v' + name[1:]
        clobbers.add(name)
    if mnemonic in ('cmp', 'cmn', 'tst'):
        # Capstone's register-access metadata treats some alias source operands
        # as written. Comparisons change flags and never their input registers.
        clobbers = {'nzcv'}
    result['clobbers'] = sorted(n for n in clobbers if n)
    result['flags_clobbered'] = result['flags_clobbered'] or 'nzcv' in clobbers
    memories = result['memory']

    def operand(index):
        op = operands[index]
        if op.type == cap.arm64.ARM64_OP_REG:
            value = _areg(ins.reg_name(op.reg))
        elif op.type == cap.arm64.ARM64_OP_IMM:
            value = const(op.imm)
        else:
            return unknown('unsupported ARM64 value operand')
        if op.ext:
            if op.ext == cap.arm64.ARM64_EXT_UXTW:
                value = operation('and', value, const(0xffffffff))
            elif op.ext in (cap.arm64.ARM64_EXT_SXTB, cap.arm64.ARM64_EXT_SXTH, cap.arm64.ARM64_EXT_SXTW):
                value = _signed(value, {cap.arm64.ARM64_EXT_SXTB: 8, cap.arm64.ARM64_EXT_SXTH: 16, cap.arm64.ARM64_EXT_SXTW: 32}[op.ext])
            elif op.ext in (cap.arm64.ARM64_EXT_UXTB, cap.arm64.ARM64_EXT_UXTH):
                value = operation('and', value, const(0xff if op.ext == cap.arm64.ARM64_EXT_UXTB else 0xffff))
            elif op.ext not in (cap.arm64.ARM64_EXT_UXTX,):
                return unknown('signed/narrow ARM64 register extension is not modeled')
        if op.shift.type:
            if op.shift.type != cap.arm64.ARM64_SFT_LSL:
                return unknown('unsupported ARM64 shifted operand')
            value = operation('shl', value, const(op.shift.value))
        return value

    def assign(index, value):
        if operands[index].type != cap.arm64.ARM64_OP_REG:
            return
        name = {'fp': 'x29', 'lr': 'x30'}.get(ins.reg_name(operands[index].reg), ins.reg_name(operands[index].reg))
        if name in ('xzr', 'wzr'):
            return
        if name and len(name) > 1 and name[0] in 'bhsdqv' and name[1:].isdigit():
            return  # SIMD partial-register/FP semantics remain clobbered.
        width = 32 if name.startswith('w') else 64
        canonical = 'sp' if name == 'wsp' else 'x' + name[1:] if name.startswith('w') and name[1:].isdigit() else name
        if width == 32:
            value = operation('and', value, const(0xffffffff))
        result['assignments'].append(dict(register=canonical, value=value, bits=64 if width == 32 else width))

    if mnemonic in ('mov', 'movz') and len(operands) >= 2:
        assign(0, operand(1))
    elif mnemonic == 'movn' and len(operands) >= 2 and operands[1].type == cap.arm64.ARM64_OP_IMM:
        width = 32 if ins.reg_name(operands[0].reg).startswith('w') else 64
        value = operand(1)
        if value['op'] == 'const':
            assign(0, const((~value['value']) & ((1 << width) - 1)))
    elif mnemonic in ('adr', 'adrp') and len(operands) == 2:
        assign(0, const(operands[1].imm))
    elif mnemonic in ('add', 'adds', 'sub', 'subs', 'and', 'ands', 'lsl', 'mul') and len(operands) >= 3:
        op = {'add': 'add', 'adds': 'add', 'sub': 'sub', 'subs': 'sub', 'and': 'and', 'ands': 'and', 'lsl': 'shl', 'mul': 'mul'}[mnemonic]
        right = operand(2)
        if op == 'shl':
            right = operation('and', right, const(31 if ins.reg_name(operands[0].reg).startswith('w') else 63))
        assign(0, operation(op, operand(1), right))
    elif mnemonic in ('cmp', 'cmn', 'tst') and len(operands) == 2:
        left, right = operand(0), operand(1)
        if mnemonic == 'tst':
            left, right = operation('and', left, right), const(0)
        width = 32 if ins.reg_name(operands[0].reg).startswith('w') else 64
        if mnemonic == 'cmn':
            result['unresolved'].append('CMN carry/overflow flags are not a subtraction comparison')
        else:
            result['comparison'] = dict(left=left, right=right, bits=width)

    memory_index = next((i for i, op in enumerate(operands) if op.type == cap.arm64.ARM64_OP_MEM), None)
    if memories and memory_index is not None:
        native = operands[memory_index]
        offset = _areg(ins.reg_name(native.mem.base))
        if native.mem.index:
            index = _areg(ins.reg_name(native.mem.index))
            if native.ext == cap.arm64.ARM64_EXT_SXTW:
                index = _signed(index, 32)
            elif native.ext == cap.arm64.ARM64_EXT_UXTW:
                index = operation('and', index, const(0xffffffff))
            elif native.ext not in (0, cap.arm64.ARM64_EXT_UXTX, cap.arm64.ARM64_EXT_SXTX):
                index = unknown('unsupported ARM64 address extension')
            if native.shift.type in (0, cap.arm64.ARM64_SFT_LSL):
                index = operation('mul', index, const(1 << native.shift.value))
            else:
                index = unknown('unsupported ARM64 address shift')
            offset = operation('add', offset, index)
        offset = operation('add', offset, const(native.mem.disp))
        memories[0].update(address=offset, offset=offset, unwrapped_offset=offset)
        if 'stack_address' in memories[0]:
            memories[0]['stack_address'] = offset
    paired = mnemonic in ('ldp', 'ldnp', 'ldpsw', 'stp', 'stnp')
    simple_load = mnemonic in ('ldr', 'ldrb', 'ldrh', 'ldrsb', 'ldrsh', 'ldrsw', 'ldur', 'ldurb', 'ldurh', 'ldursb', 'ldursh', 'ldursw', 'ldar', 'ldarb', 'ldarh', 'ldtr', 'ldtrb', 'ldtrh', 'ldtrsb', 'ldtrsh', 'ldtrsw')
    simple_store = mnemonic in ('str', 'strb', 'strh', 'stur', 'sturb', 'sturh', 'stlr', 'stlrb', 'stlrh', 'sttr', 'sttrb', 'sttrh')
    if memories and (simple_load or simple_store or paired):
        memory = memories[0]
        signed = mnemonic in ('ldrsb', 'ldrsh', 'ldrsw', 'ldursb', 'ldursh', 'ldursw', 'ldtrsb', 'ldtrsh', 'ldtrsw', 'ldpsw')
        if paired and memory['width']:
            width = memory['width'] // 2
            original = memory
            memories[:] = []
            for i in range(2):
                element = dict(original, address=operation('add', original['address'], const(i * width)),
                               offset=operation('add', original['offset'], const(i * width)),
                               unwrapped_offset=operation('add', original['unwrapped_offset'], const(i * width)), width=width)
                if 'stack_address' in original:
                    element['stack_address'] = operation('add', original['stack_address'], const(i * width))
                memories.append(element)
                if mnemonic.startswith('ld'):
                    assign(i, _read_memory(element, signed))
                else:
                    element['value'] = operand(i)
        elif simple_load:
            assign(0, _read_memory(memory, signed))
        elif simple_store:
            memory['value'] = operand(0)
    if ins.writeback and memory_index is not None:
        memory_operand = operands[memory_index]
        base = {'fp': 'x29', 'lr': 'x30'}.get(ins.reg_name(memory_operand.mem.base), ins.reg_name(memory_operand.mem.base))
        following = memory_index + 1
        update = operand(following) if following < len(operands) else const(memory_operand.mem.disp)
        value = operation('add', _areg(base), update)
        result['assignments'].append(dict(register=base, value=value, bits=64))
        if base == 'sp':
            result['stack_delta'] = update['value'] if update.get('op') == 'const' else None
    if any(a['register'] == 'sp' for a in result['assignments']) and not ins.writeback:
        value = next(a['value'] for a in result['assignments'] if a['register'] == 'sp')
        result['stack_delta'] = None
        if value.get('op') in ('add', 'sub') and value['args'][0] == reg('sp') and value['args'][1].get('op') == 'const':
            result['stack_delta'] = value['args'][1]['value'] * (1 if value['op'] == 'add' else -1)
    elif 'sp' in clobbers and not any(a['register'] == 'sp' for a in result['assignments']):
        result['stack_delta'] = None
    if flow in ('call', 'jump', 'conditional'):
        immediate = [op.imm for op in operands if op.type == cap.arm64.ARM64_OP_IMM]
        result['target'] = immediate[-1] if immediate else None
    if flow in ('call', 'indirect_call'):
        result['assignments'].append(dict(register='x30', value=const(address+4), bits=64))
        result['return_address_size'] = 0
    if flow in ('indirect_call', 'indirect_jump'):
        result['indirect_target'] = unknown('authenticated pointer requires runtime key/context') if auth_call or auth_jump else operand(0)
    if flow == 'return':
        result.update(return_pop=0, return_address_size=0, return_kind='link_register',
                      indirect_target=operand(0) if operands else reg('x30'))
        if auth_return or exception_return:
            result['return_kind'] = 'exception' if exception_return else 'authenticated_link_register'
            result['indirect_target'] = unknown('exception/authenticated return requires runtime system/key state')
    if flow == 'conditional':
        if mnemonic in ('cbz', 'cbnz'):
            result['branch_condition'] = dict(predicate='eq' if mnemonic == 'cbz' else 'ne', left=operand(0), right=const(0), bits=32 if ins.reg_name(operands[0].reg).startswith('w') else 64)
        elif mnemonic in ('tbz', 'tbnz'):
            bit = operands[1].imm
            result['branch_condition'] = dict(predicate='eq' if mnemonic == 'tbz' else 'ne',
                                             left=operation('and', operand(0), const(1 << bit)), right=const(0), bits=64)
        else:
            predicates = {'eq': 'eq', 'ne': 'ne', 'lo': 'lt_u', 'cc': 'lt_u', 'hs': 'ge_u', 'cs': 'ge_u',
                          'ls': 'le_u', 'hi': 'gt_u', 'lt': 'lt_s', 'ge': 'ge_s', 'le': 'le_s', 'gt': 'gt_s'}
            predicate = predicates.get(mnemonic.split('.', 1)[1])
            if predicate:
                result['branch_condition'] = dict(predicate=predicate, source='comparison')
    return result


def instruction_semantics(raw: bytes, address: int, arch: str, bits: int, cs=None):
    """Normalize one x86/ARM64 instruction without running imported code.

    Invalid/truncated bytes return ``valid=False`` and no transfers. All byte
    widths are bytes; assignment/comparison widths are bits. ``return_pop`` is
    the explicit RET-immediate cleanup, separate from ``return_address_size``.
    """
    if not isinstance(raw, bytes):
        raise ValueError('instruction bytes must be bytes')
    if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < 1 << 64:
        raise ValueError('instruction address must be an unsigned 64-bit integer')
    if arch not in ('x86', 'arm64') or bits not in ((16, 32, 64) if arch == 'x86' else (64,)):
        raise ValueError('semantics support x86 16/32/64 and ARM64')
    if cs is not None and (isinstance(cs, bool) or not isinstance(cs, int) or not 0 <= cs <= 0xffff or arch != 'x86' or bits != 16 or not 0 <= address - cs * 16 <= 0xffff):
        raise ValueError('CS requires a 16-bit instruction inside its real-mode window')
    if not raw:
        return _empty(address, arch, bits)
    return _x86(raw, address, bits, cs) if arch == 'x86' else _arm(raw, address)
