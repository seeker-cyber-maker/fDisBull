"""Agent-authored, audited Python UDC lowering rules.

These are the manual/sweding component of the experiment, not recovered UIL
semantics or validated universal CHIP-8 contracts. The deterministic generator
substitutes only integer operands from the existing strict decoder.

The generated artifact is guarded by both PC and fetched instruction bytes.
Anything not in this *allowlist* is handled by the existing Machine.step().
"""
from __future__ import annotations

# Python source templates for body statements only. Required PC advance,
# family/step bookkeeping and source-word identity guard are generated centrally.
# For scalar rules, these imitate *the pilot's authored VM*, not historical COSMAC.
SWEDES = {
    'CLS': "m.frame[:] = bytes(len(m.frame))",
    'JP': "m.pc = {nnn}",
    # Agent-authored second-round swedes: checked against VM trap semantics.
    'CALL': "if len(m.stack) >= 16: raise Trap('stack_overflow', pc, fetched)\nm.stack.append(m.pc)\nm.pc = {nnn}",
    'RET': "if not m.stack: raise Trap('stack_underflow', pc, fetched)\nm.pc = m.stack.pop()",
    'SE_VX_KK': "if m.v[{x}] == {kk}: m.pc += 2",
    'SNE_VX_KK': "if m.v[{x}] != {kk}: m.pc += 2",
    'SE_VX_VY': "if m.v[{x}] == m.v[{y}]: m.pc += 2",
    'SNE_VX_VY': "if m.v[{x}] != m.v[{y}]: m.pc += 2",
    'LD_VX_KK': "m.v[{x}] = {kk}",
    'ADD_VX_KK': "m.v[{x}] = (m.v[{x}] + {kk}) & 255",
    'LD_VX_VY': "m.v[{x}] = m.v[{y}]",
    'LD_I': "m.i = {nnn}",
    'LD_VX_DT': "m.v[{x}] = m.delay",
    'LD_DT_VX': "m.delay = m.v[{x}]",
    'LD_ST_VX': "m.sound = m.v[{x}]",
    'ADD_I_VX': "m.i = (m.i + m.v[{x}]) & 65535",
    'SKP': "if m.v[{x}] in m.keys: m.pc += 2",
    'SKNP': "if m.v[{x}] not in m.keys: m.pc += 2",
    'FONT': "m.i = 0x50 + 5 * (m.v[{x}] & 15)",
    'RND': "m.v[{x}] = m.rng.randrange(256) & {kk}",
    # Third-round swede: stateful display XOR. Based on the pilot VM's declared
    # sprite/clipping rules, not historical emulator or vblank qualification.
    'DRW': "m.mem_range(m.i, {n}, pc, fetched)\n"
           "px, py = m.v[{x}] % 64, m.v[{y}] % 32\n"
           "collision = 0\n"
           "for row in range({n}):\n"
           "    bits = m.memory[m.i + row]\n"
           "    for col in range(8):\n"
           "        if bits & (128 >> col):\n"
           "            xx, yy = px + col, py + row\n"
           "            if m.quirks.clip_sprites and (xx >= 64 or yy >= 32): continue\n"
           "            pixel = (yy % 32) * 64 + (xx % 64)\n"
           "            if m.frame[pixel]: collision = 1\n"
           "            m.frame[pixel] ^= 1\n"
           "m.v[15] = collision",
    # These need special attention to VF semantics when x/y equals 0xF.
    'ADD_VX_VY': "z = m.v[{x}] + m.v[{y}]\nm.v[{x}] = z & 255\nm.v[15] = int(z > 255)",
    # BCD, SAVE, LOAD, WAIT_KEY, shifts, etc. are delegated
    # to the pilot VM until explicitly sweded and tested.
}


def body_for(decoded, allowed: set[str] | None = None) -> str | None:
    """Return a substitution in a trusted authored template or None."""
    if allowed is not None and decoded.family not in allowed: return None
    template = SWEDES.get(decoded.family)
    if template is None or decoded.tier != 'classic':
        return None
    return template.format(x=decoded.x, y=decoded.y, kk=decoded.kk,
                           nnn=decoded.nnn, n=decoded.n)