"""Bounded source-byte lift of straight-line 68000 logic to console UIL.

This recognizes only the native instruction patterns emitted by udc_genesis.
The caller supplies the exact function range and explicit variable bindings;
those bindings are assumptions, not recovered symbols or initial RAM evidence.
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
