"""MANUALLY authored Python UDC primitives for a bounded CHIP-8 study.

Each accepted family emits Python state transitions with exact operand binding.
The instruction decoder and finite-trace search come from fDisBull's CHIP-8
pilot; this module is the missing realization binding sweded by the agent.

No claim of a new common-UIL opcode or a complete emulator is made.
"""
from __future__ import annotations

from chip8lab.decoder import Instruction

# Explicitly qualify each family in a differential test before admitting it.
# Every emitter below is human/agent-written glue, NOT a generated discovery.
SWEDED_FAMILIES = frozenset({
    'CLS', 'RET', 'JP', 'CALL', 'SE_VX_KK', 'SNE_VX_KK', 'SE_VX_VY',
    'LD_VX_KK', 'ADD_VX_KK', 'LD_VX_VY', 'ADD_VX_VY', 'SNE_VX_VY',
    'LD_I', 'LD_VX_DT', 'LD_DT_VX', 'LD_ST_VX', 'SKP', 'SKNP',
    'ADD_I_VX', 'FONT',
})


def emit(d: Instruction) -> list[str]:
    """Produce trusted snippets from a decoded classic-family instruction only.

    Input is a parsed integer instruction; never accept free-form source text.
    The wrapping, argument order and trap conditions replicate the pilot VM.
    """
    if d.family not in SWEDED_FAMILIES or d.tier != 'classic':
        raise ValueError(f'no admitted Python swede for {d.family}/{d.tier}')
    x, y, kk, nnn, w = d.x, d.y, d.kk, d.nnn, d.word
    family = d.family
    if family == 'CLS': return ['m.frame[:] = bytes(len(m.frame))']
    if family == 'RET': return [
        f"if not m.stack: raise Trap('stack_underflow', pc0, {w})",
        'm.pc = m.stack.pop()',
    ]
    if family == 'JP': return [f'm.pc = {nnn}']
    if family == 'CALL': return [
        f"if len(m.stack) >= 16: raise Trap('stack_overflow', pc0, {w})",
        'm.stack.append(m.pc)',
        f'm.pc = {nnn}',
    ]
    if family == 'SE_VX_KK': return [f'if m.v[{x}] == {kk}: m.pc += 2']
    if family == 'SNE_VX_KK': return [f'if m.v[{x}] != {kk}: m.pc += 2']
    if family == 'SE_VX_VY': return [f'if m.v[{x}] == m.v[{y}]: m.pc += 2']
    if family == 'LD_VX_KK': return [f'm.v[{x}] = {kk}']
    if family == 'ADD_VX_KK': return [f'm.v[{x}] = (m.v[{x}] + {kk}) & 255']
    if family == 'LD_VX_VY': return [f'm.v[{x}] = m.v[{y}]']
    if family == 'ADD_VX_VY': return [
        f'z = m.v[{x}] + m.v[{y}]',
        f'm.v[{x}] = z & 255',
        'm.v[15] = int(z > 255)',
    ]
    if family == 'SNE_VX_VY': return [f'if m.v[{x}] != m.v[{y}]: m.pc += 2']
    if family == 'LD_I': return [f'm.i = {nnn}']
    if family == 'LD_VX_DT': return [f'm.v[{x}] = m.delay']
    if family == 'LD_DT_VX': return [f'm.delay = m.v[{x}]']
    if family == 'LD_ST_VX': return [f'm.sound = m.v[{x}]']
    if family == 'SKP': return [f'if m.v[{x}] in m.keys: m.pc += 2']
    if family == 'SKNP': return [f'if m.v[{x}] not in m.keys: m.pc += 2']
    if family == 'ADD_I_VX': return [f'm.i = (m.i + m.v[{x}]) & 65535']
    if family == 'FONT': return [f'm.i = 0x50 + 5 * (m.v[{x}] & 15)']
    raise AssertionError('swede family has no emitter')