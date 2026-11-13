#!/usr/bin/env python3
"""Seeded, authored full-width x86-64 rewrites of a small Win64 contract.

The emitted LLVM/GAS Intel-syntax source targets COFF/PE64. It has no imports,
prologue, calls, stack stores or hidden image state. This is a calibration
corpus generator, not a general obfuscator or an equivalence certificate.
"""
from __future__ import annotations

import hashlib


FORMAT = 'fdisbull-reachable-rewrites-1'
MAX_LEVEL = 8
VOLATILE_SCRATCH = ('rax', 'r9', 'r10', 'r11')


def generate_assembly(seed: str, level: int = 1, mutation: bool = False) -> str:
    """Return deterministic COFF assembly for the declared bounded operation.

    Inputs are Win64 RCX=x, RDX=limit, R8=out. The normal guard permits one
    eight-byte store iff unsigned x <= limit, storing ((x XOR 90) + 7) mod 2**64.
    Mutation changes only that boundary to x < limit. Nonvolatile GPRs and RSP
    are untouched before RET; volatile GPRs and arithmetic FLAGS are dead.

    Level 0 is the canonical reference. Level 1 adds reachable register/guard
    rewrites and cancelling operations. Levels 2..8 replace the meaningful XOR
    with (x OR 90) - (x AND 90), and increase bounded cancellation depth. No
    transformation depends on the incoming value of a scratch register.
    """
    if not isinstance(seed, str) or len(seed) > 4096:
        raise ValueError('seed must be a string of at most 4096 characters')
    try:
        seed_bytes = seed.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError('seed must be valid UTF-8 text') from error
    if type(level) is not int or not 0 <= level <= MAX_LEVEL:
        raise ValueError(f'level must be an integer from 0 through {MAX_LEVEL}')
    if type(mutation) is not bool:
        raise ValueError('mutation must be a boolean')
    seed_digest = hashlib.sha256(seed_bytes).hexdigest()
    material = b'fdisbull-reachable-rewrites-1\0' + bytes([level]) + seed_bytes

    def word(label: str) -> int:
        return int.from_bytes(hashlib.sha256(material + b'\0' + label.encode('ascii')).digest()[:8], 'little')

    lines = [
        '# SPDX-License-Identifier: MIT',
        f'# {FORMAT}; seed_sha256={seed_digest}; level={level}; mutation={int(mutation)}',
        '# Win64: RCX=x, RDX=limit, R8=out; unsigned guard; QWORD output only.',
        '# Live: nonvolatile GPRs, RSP and ordered output writes. Dead: volatile GPRs and FLAGS.',
        '.intel_syntax noprefix',
        '.text',
        '.globl bounded_core',
        'bounded_core:',
    ]

    def emit(text: str) -> None:
        lines.append('    ' + text)

    if level == 0:
        emit('cmp rcx, rdx')
        emit(('jae' if mutation else 'ja') + ' .Lreturn')
        emit('mov rax, rcx')
        emit('xor rax, 90')
        emit('add rax, 7')
        emit('mov qword ptr [r8], rax')
    else:
        registers = list(VOLATILE_SCRATCH)
        for index in range(len(registers) - 1, 0, -1):
            other = word(f'register-{index}') % (index + 1)
            registers[index], registers[other] = registers[other], registers[index]
        result, auxiliary, dead, guard = registers
        # These execute on both outcomes. The guard copy is live until consumed;
        # the other writes affect a declared dead register, never an output.
        emit(f'mov {guard}, rcx')
        emit(f'mov {dead}, 0x{word("entry-dead"):016x}')
        emit(f'xor {dead}, {dead}')
        for _ in range(1 + word('entry-nops') % 3):
            emit('nop')
        reversed_guard = bool(word('guard-order') & 1)
        if reversed_guard:
            emit(f'cmp rdx, {guard}')
            emit(('jbe' if mutation else 'jb') + ' .Lreturn')
        else:
            emit(f'cmp {guard}, rdx')
            emit(('jae' if mutation else 'ja') + ' .Lreturn')
        # A redundant, reversed-operand accepted-domain guard. This creates real
        # reachable control edges without admitting another input domain.
        emit(f'cmp rdx, {guard}')
        emit(('ja' if mutation else 'jae') + ' .Lbody')
        emit('jmp .Lreturn')
        lines.append('.Lbody:')
        emit(f'mov {result}, {guard}')
        # Every pair cancels in the u64 modular ring, including wrapping ADD/SUB.
        # Constants use MOV r64, imm64 then register arithmetic: no imm64 ALU
        # encoding is assumed and no 32-bit zero-extension aliases are emitted.
        for index in range(max(1, level - 1)):
            emit(f'mov {dead}, 0x{word(f"xor-{index}"):016x}')
            emit(f'xor {result}, {dead}')
            emit(f'xor {result}, {dead}')
            emit(f'mov {dead}, 0x{word(f"add-{index}"):016x}')
            emit(f'add {result}, {dead}')
            emit(f'sub {result}, {dead}')
        if level >= 2:
            emit(f'mov {auxiliary}, {result}')
            emit(f'or {result}, 90')
            emit(f'and {auxiliary}, 90')
            emit(f'sub {result}, {auxiliary}')
        else:
            emit(f'xor {result}, 90')
        # Split the +7 across seeded, possibly negative small immediates. Both
        # values are exactly representable sign-extended ALU immediates.
        first = int(word('add-seven-split') % 255) - 127
        emit(f'add {result}, {first}')
        emit(f'add {result}, {7 - first}')
        emit(f'mov {dead}, {result}')
        emit(f'and {dead}, 255')
        emit(f'or {dead}, {1 + word("dead-or") % 127}')
        emit(f'mov qword ptr [r8], {result}')
    lines += [
        '.Lreturn:',
        '    ret',
        '.globl bounded_update',
        'bounded_update:',
        '    jmp bounded_core',
        '.section .drectve,"yn"',
        '    .ascii " /EXPORT:bounded_core /EXPORT:bounded_update"',
    ]
    return '\n'.join(lines) + '\n'
