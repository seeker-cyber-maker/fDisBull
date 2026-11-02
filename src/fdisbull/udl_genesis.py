"""Bounded source-byte lifting of explicitly selected 68000 logic to UIL.

``lift`` retains the generated-function profile. ``lift_native`` handles a
separate small native memory/branch profile. Both require exact ranges and
explicit bindings; those are assumptions, not recovered symbols or RAM facts.
"""
from __future__ import annotations

import hashlib
import struct

from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs


class GenesisLiftError(ValueError):
    """The source or a declared assumption lies outside the supported subset."""


def lift(rom: bytes, *, logic_offset: int, logic_length: int, layout: dict) -> dict:
    """Lift exactly one straight-line generated function, including its RTS."""
    if (not isinstance(rom, bytes) or type(logic_offset) is not int or
            type(logic_length) is not int or logic_offset < 0x200 or
            logic_offset % 2 or logic_length < 2 or logic_length % 2 or
            logic_offset + logic_length > len(rom)):
        raise GenesisLiftError('invalid source function range')
    by_address = {}
    variables = {}
    used = set()
    for name, binding in layout.items():
        if not isinstance(name, str) or not isinstance(binding, dict):
            raise GenesisLiftError('invalid variable binding')
        address, width, initial = (binding.get(k) for k in ('address', 'width', 'initial'))
        if (type(address) is not int or width not in (8, 16) or type(initial) is not int or
                not 0xff0000 <= address <= 0xffffef or
                address + width // 8 - 1 > 0xffffef or
                (width == 16 and address % 2) or not 0 <= initial < 1 << width):
            raise GenesisLiftError('invalid variable binding')
        covered = set(range(address, address + width // 8))
        if covered & used:
            raise GenesisLiftError('overlapping variable bindings')
        used |= covered
        by_address[(address, width)] = name
        variables[name] = {'type': f'u{width}', 'initial': initial}

    source = rom[logic_offset:logic_offset + logic_length]
    decoder = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    instructions = list(decoder.disasm(source, logic_offset))
    if not instructions or sum(i.size for i in instructions) != len(source):
        raise GenesisLiftError('source contains undecodable or uncovered bytes')
    cursor = 0

    def current():
        if cursor >= len(instructions):
            raise GenesisLiftError('incomplete logic function')
        return instructions[cursor]

    def take(expected, size):
        nonlocal cursor
        insn = current()
        if insn.mnemonic != expected or insn.size != size:
            raise GenesisLiftError(f'unsupported instruction at {insn.address:#x}')
        cursor += 1
        return bytes(insn.bytes)

    def read_value(reg):
        insn = current()
        raw = bytes(insn.bytes)
        if len(raw) < 2:
            raise GenesisLiftError('truncated instruction')
        opcode = int.from_bytes(raw[:2], 'big')
        for width, immediate, absolute in ((8, 0x103c, 0x1039), (16, 0x303c, 0x3039)):
            if opcode == immediate | (reg << 9):
                data = take('move.b' if width == 8 else 'move.w', 4)
                value = int.from_bytes(data[2:], 'big')
                if width == 8 and value > 255:
                    raise GenesisLiftError('noncanonical immediate')
                return width, value
            if opcode == absolute | (reg << 9):
                data = take('move.b' if width == 8 else 'move.w', 6)
                address = int.from_bytes(data[2:], 'big')
                name = by_address.get((address, width))
                if name is None:
                    raise GenesisLiftError(f'unbound source address {address:#x}')
                return width, {'var': name}
        raise GenesisLiftError(f'unsupported value instruction at {insn.address:#x}')

    body = []
    while True:
        insn = current()
        if bytes(insn.bytes) == b'\x4e\x75':
            take('rts', 2)
            if cursor != len(instructions):
                raise GenesisLiftError('bytes after function return')
            break
        width, first = read_value(0)
        insn = current()
        raw = bytes(insn.bytes)
        opcode = int.from_bytes(raw[:2], 'big')
        if opcode == (0x13c0 if width == 8 else 0x33c0):
            op, value, previous = 'set', first, None
        else:
            if not isinstance(first, dict):
                raise GenesisLiftError('arithmetic destination must be a bound variable')
            value_width, value = read_value(1)
            if value_width != width:
                raise GenesisLiftError('arithmetic width mismatch')
            insn = current()
            raw = bytes(insn.bytes)
            opcodes = {0xd001 if width == 8 else 0xd041: 'add',
                       0x9001 if width == 8 else 0x9041: 'subtract'}
            opcode = int.from_bytes(raw[:2], 'big')
            if opcode not in opcodes:
                raise GenesisLiftError(f'unsupported arithmetic at {insn.address:#x}')
            op = opcodes[opcode]
            mnemonic = 'sub' if op == 'subtract' else op
            take(f'{mnemonic}.b' if width == 8 else f'{mnemonic}.w', 2)
            previous = first['var']
        store = take('move.b' if width == 8 else 'move.w', 6)
        if int.from_bytes(store[:2], 'big') != (0x13c0 if width == 8 else 0x33c0):
            raise GenesisLiftError('unsupported destination instruction')
        address = int.from_bytes(store[2:], 'big')
        dest = by_address.get((address, width))
        if dest is None or (previous is not None and dest != previous):
            raise GenesisLiftError(f'unbound or mismatched destination {address:#x}')
        body.append({'id': f'lifted_{len(body):04d}', 'op': op, 'var': dest, 'value': value})

    from .interaction_il import validate_il
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
               'resources': {}, 'body': body}
    validate_il(program)
    return {
        'program': program,
        'provenance': {'source_sha256': hashlib.sha256(rom).hexdigest(),
                       'logic_sha256': hashlib.sha256(source).hexdigest(),
                       'logic_offset': logic_offset, 'logic_length': logic_length,
                       'bindings': layout, 'scope': 'straight-line generated 68000 logic'},
    }


def lift_native(rom: bytes, *, logic_offset: int, logic_length: int,
                layout: dict, address_registers: dict) -> dict:
    """Lift a bounded native RAM function under explicit address assumptions.

    The flat cartridge is mapped at CPU address zero. Supported instructions
    are byte/word ADDQ, SUBQ, CLR and TST on bound RAM; forward BRA/BEQ/BNE;
    and RTS. Addressing is (An), d16(An), absolute word or absolute long.
    Incoming CCR, loops, calls, other CPU registers and peripherals are not
    modeled. RTS return-stack mechanics are excluded from the UIL boundary.
    """
    if (not isinstance(rom, bytes) or type(logic_offset) is not int or
            type(logic_length) is not int or logic_offset < 0x200 or
            logic_offset % 2 or not 2 <= logic_length <= 256 or
            logic_length % 2 or logic_offset + logic_length > len(rom)):
        raise GenesisLiftError('invalid native function range')
    if not isinstance(layout, dict) or not 1 <= len(layout) <= 32:
        raise GenesisLiftError('native profile requires 1..32 RAM bindings')
    if not isinstance(address_registers, dict):
        raise GenesisLiftError('invalid address register assumptions')
    registers = {}
    for name, value in address_registers.items():
        if (not isinstance(name, str) or name.upper() not in
                {f'A{i}' for i in range(7)} or name.upper() in registers or
                type(value) is not int or not 0 <= value <= 0xffffff):
            raise GenesisLiftError('invalid address register assumption')
        registers[name.upper()] = value
    variables, by_address, used = {}, {}, set()
    for name, binding in layout.items():
        if not isinstance(binding, dict):
            raise GenesisLiftError('invalid native RAM binding')
        address, width, initial = (binding.get(k) for k in ('address', 'width', 'initial'))
        if (type(address) is not int or type(width) is not int or width not in (8, 16)
                or type(initial) is not int or not 0xff0000 <= address <= 0xffffef
                or address + width // 8 - 1 > 0xffffef or
                (width == 16 and address % 2) or not 0 <= initial < 1 << width):
            raise GenesisLiftError('invalid native RAM binding')
        covered = set(range(address, address + width // 8))
        if covered & used:
            raise GenesisLiftError('overlapping native RAM bindings')
        used |= covered
        variables[name] = {'type': f'u{width}', 'initial': initial}
        by_address[(address, width)] = name

    source = rom[logic_offset:logic_offset + logic_length]
    decoder = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    instructions = list(decoder.disasm(source, logic_offset))
    if (not instructions or len(instructions) > 32 or
            sum(i.size for i in instructions) != len(source)):
        raise GenesisLiftError('native source exceeds instruction budget or has uncovered bytes')
    lowered = {}

    def memory(raw, width):
        opcode = int.from_bytes(raw[:2], 'big')
        mode, reg = (opcode >> 3) & 7, opcode & 7
        if mode == 2 and len(raw) == 2:
            base = registers.get(f'A{reg}')
            if base is None:
                raise GenesisLiftError('unbound address register')
            address = base
        elif mode == 5 and len(raw) == 4:
            base = registers.get(f'A{reg}')
            if base is None:
                raise GenesisLiftError('unbound address register')
            address = (base + int.from_bytes(raw[2:], 'big', signed=True)) & 0xffffff
        elif mode == 7 and reg == 0 and len(raw) == 4:
            address = int.from_bytes(raw[2:], 'big', signed=True) & 0xffffff
        elif mode == 7 and reg == 1 and len(raw) == 6:
            absolute = int.from_bytes(raw[2:], 'big')
            if absolute > 0xffffff:
                raise GenesisLiftError('noncanonical absolute address')
            address = absolute
        else:
            raise GenesisLiftError('unsupported native memory addressing')
        name = by_address.get((address, width))
        if name is None:
            raise GenesisLiftError(f'unbound native RAM access {address:#x}')
        return name

    for insn in instructions:
        raw = bytes(insn.bytes)
        opcode = int.from_bytes(raw[:2], 'big')
        after = insn.address + insn.size
        size = (opcode >> 6) & 3
        if opcode == 0x4e75 and insn.mnemonic == 'rts' and len(raw) == 2:
            item = {'kind': 'return'}
        elif opcode & 0xf000 == 0x5000 and size in (0, 1):
            width = 8 if size == 0 else 16
            op = 'subtract' if opcode & 0x100 else 'add'
            mnemonic = 'subq' if op == 'subtract' else 'addq'
            if insn.mnemonic != f'{mnemonic}.{"b" if width == 8 else "w"}':
                raise GenesisLiftError('native quick instruction disagrees with decoder')
            item = {'kind': 'write', 'op': op, 'var': memory(raw, width),
                    'value': (opcode >> 9) & 7 or 8, 'next': after}
        elif opcode & 0xff00 in (0x4200, 0x4a00) and size in (0, 1):
            width = 8 if size == 0 else 16
            clear = opcode & 0xff00 == 0x4200
            if insn.mnemonic != f'{"clr" if clear else "tst"}.{"b" if width == 8 else "w"}':
                raise GenesisLiftError('native flag instruction disagrees with decoder')
            item = {'kind': 'write' if clear else 'test', 'op': 'set',
                    'var': memory(raw, width), 'value': 0, 'next': after}
        elif opcode & 0xff00 in (0x6000, 0x6600, 0x6700):
            if raw[1] == 0 and len(raw) == 4:
                displacement = int.from_bytes(raw[2:], 'big', signed=True)
            elif raw[1] and len(raw) == 2:
                displacement = int.from_bytes(raw[1:], 'big', signed=True)
            else:
                raise GenesisLiftError('unsupported native branch encoding')
            target = insn.address + 2 + displacement
            if target <= insn.address:
                raise GenesisLiftError('native loops or backward branches are unsupported')
            condition = {0x6000: None, 0x6600: False, 0x6700: True}[opcode & 0xff00]
            item = {'kind': 'branch', 'zero': condition, 'target': target, 'next': after}
        else:
            raise GenesisLiftError(f'unsupported native instruction at {insn.address:#x}')
        lowered[insn.address] = item

    reachable, nodes = set(), 0

    def walk(pc, zero=None, depth=0):
        nonlocal nodes
        if depth > 32 or pc not in lowered:
            raise GenesisLiftError('native control flow leaves exact instruction range')
        reachable.add(pc)
        item = lowered[pc]
        kind = item['kind']
        if kind == 'return':
            return []
        if kind in ('write', 'test'):
            z = {'op': 'eq', 'left': {'var': item['var']}, 'right': 0}
            statement = []
            if kind == 'write':
                nodes += 1
                if nodes > 256:
                    raise GenesisLiftError('native lowering node budget exceeded')
                statement = [{'id': f'native_{nodes:04d}', 'op': item['op'],
                              'var': item['var'], 'value': item['value']}]
            return statement + walk(item['next'], z, depth + 1)
        if item['zero'] is None:
            return walk(item['target'], zero, depth + 1)
        if zero is None:
            raise GenesisLiftError('native branch depends on incoming CCR')
        condition = zero if item['zero'] else {'op': 'not', 'condition': zero}
        nodes += 1
        if nodes > 256:
            raise GenesisLiftError('native lowering node budget exceeded')
        identifier = f'native_{nodes:04d}'
        taken = walk(item['target'], zero, depth + 1)
        fallthrough = walk(item['next'], zero, depth + 1)
        return [{'id': identifier, 'op': 'if', 'condition': condition,
                 'then': taken, 'else': fallthrough}]

    body = walk(logic_offset)
    if reachable != set(lowered):
        raise GenesisLiftError('native exact range contains unreachable instructions')
    program = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
               'resources': {}, 'body': body}
    from .console_udc import validate_console_program
    try:
        validate_console_program(program)
    except ValueError as exc:
        raise GenesisLiftError(f'native result exceeds console UIL profile: {exc}') from exc
    return {'program': program, 'provenance': {
        'profile': 'm68000-native-memory-1', 'source_sha256': hashlib.sha256(rom).hexdigest(),
        'logic_sha256': hashlib.sha256(source).hexdigest(), 'logic_offset': logic_offset,
        'logic_length': logic_length, 'cartridge_base': 0, 'bindings': layout,
        'address_registers': registers, 'instruction_count': len(instructions),
        'instructions': [{'address': i.address, 'size': i.size,
                          'mnemonic': i.mnemonic, 'operands': i.op_str}
                         for i in instructions],
        'scope': 'declared RAM effects of bounded native function',
        'excluded': ['CCR output', 'RTS stack/control mechanics', 'natural game reachability',
                     'peripherals', 'timing', 'unbound CPU state']}}
