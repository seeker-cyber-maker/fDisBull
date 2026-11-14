"""Opt-in LLVM IR emitter for a *closed scalar* IL-v1 subset.

This does not lift TCG, decompile arbitrary x86, or turn effects into no-ops.
It demonstrates real, independently executable native code from shared IL.
"""
from __future__ import annotations

import hashlib
import json
import re

from .interaction_il import validate_il


class LLVMScalarError(ValueError):
    """The requested program is outside the verified scalar subset."""


class _Builder:
    def __init__(self, slots):
        self.slots = {name: i for i, name in enumerate(slots)}
        self.lines = []
        self.index = 0

    def emit(self, line):
        self.lines.append('  ' + line)

    def tmp(self):
        self.index += 1
        return '%v' + str(self.index)

    def label(self, stem):
        self.index += 1
        return stem + str(self.index)

    def value(self, value):
        if type(value) is bool:
            return '1' if value else '0'
        if type(value) is int:
            if not 0 <= value <= 255:
                raise LLVMScalarError('Only unsigned byte constants are admitted')
            return str(value)
        if not isinstance(value, dict) or set(value) != {'var'}:
            raise LLVMScalarError('Unsupported operand')
        ptr = self.tmp()
        self.emit(f'{ptr} = getelementptr i8, ptr %state, i64 {self.slots[value["var"]]}')
        out = self.tmp()
        self.emit(f'{out} = load i8, ptr {ptr}')
        return out

    def condition(self, cond):
        op = cond['op']
        if op in ('eq', 'lt'):
            lhs, rhs = self.value(cond['left']), self.value(cond['right'])
            out = self.tmp()
            pred = 'eq' if op == 'eq' else 'ult'
            self.emit(f'{out} = icmp {pred} i8 {lhs}, {rhs}')
            return out
        if op == 'bit_test':
            src = self.value(cond['value'])
            if cond['bit'] >= 8:
                return 'false'
            tmp = self.tmp()
            self.emit(f'{tmp} = and i8 {src}, {1 << cond["bit"]}')
            out = self.tmp()
            self.emit(f'{out} = icmp ne i8 {tmp}, 0')
            return out
        if op == 'not':
            src = self.condition(cond['condition'])
            out = self.tmp()
            self.emit(f'{out} = xor i1 {src}, true')
            return out
        if op == 'and':
            vals = [self.condition(part) for part in cond['conditions']]
            acc = vals[0]
            for val in vals[1:]:
                out = self.tmp()
                self.emit(f'{out} = and i1 {acc}, {val}')
                acc = out
            return acc
        raise LLVMScalarError('Unsupported condition')

    def blocks(self, blocks):
        for block in blocks:
            op = block['op']
            if op == 'if':
                branch = self.condition(block['condition'])
                yes, no, end = (self.label(prefix) for prefix in ('yes', 'no', 'join'))
                self.emit(f'br i1 {branch}, label %{yes}, label %{no}')
                self.lines.append(yes + ':')
                self.blocks(block['then'])
                self.emit(f'br label %{end}')
                self.lines.append(no + ':')
                self.blocks(block['else'])
                self.emit(f'br label %{end}')
                self.lines.append(end + ':')
            elif op in ('set', 'add', 'subtract'):
                rhs = self.value(block['value'])
                index = self.slots[block['var']]
                ptr = self.tmp()
                self.emit(f'{ptr} = getelementptr i8, ptr %state, i64 {index}')
                if op != 'set':
                    old = self.tmp()
                    self.emit(f'{old} = load i8, ptr {ptr}')
                    result = self.tmp()
                    instr = 'add' if op == 'add' else 'sub'
                    self.emit(f'{result} = {instr} i8 {old}, {rhs}')
                    rhs = result
                self.emit(f'store i8 {rhs}, ptr {ptr}')
            else:
                raise LLVMScalarError(f'Unsupported side effect or control operator: {op}')


def emit_llvm_scalar_v1(document, *, symbol='fdisbull_scalar'):
    """Return LLVM IR and stable byte-slot ABI for closed u8/bool programs.

    Caller must provide all state bytes; bool inputs must be canonical 0 or 1.
    Numeric operations use 8-bit modular arithmetic. No I/O or host effects.
    """
    validate_il(document)
    if document.get('format') != 'fdisbull-il-1':
        raise LLVMScalarError('Only IL v1 is admitted')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}', symbol):
        raise LLVMScalarError('Invalid LLVM symbol')
    if document['resources'] or document.get('tables'):
        raise LLVMScalarError('Resource/lookup effects require a runtime and are refused')
    if len(document['variables']) > 128 or not document['variables']:
        raise LLVMScalarError('One to 128 state slots required')
    if any(decl['type'] not in ('u8', 'bool') for decl in document['variables'].values()):
        raise LLVMScalarError('Only u8 and bool state supported (no silent truncation)')
    slots = sorted(document['variables'])
    builder = _Builder(slots)
    builder.lines.extend([f'define void @{symbol}(ptr %state) {{', 'entry:'])
    builder.blocks(document['body'])
    builder.emit('ret void')
    builder.lines.append('}')
    digest = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'format': 'fdisbull-llvm-scalar-pilot-1', 'source_sha256': digest,
            'state_slots': slots, 'symbol': symbol, 'llvm_ir': '\n'.join(builder.lines) + '\n',
            'qualification': 'closed scalar IL only; no original game or host-effect parity'}
