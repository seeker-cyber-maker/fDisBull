"""Generated experimental Python UDC for a pinned CHIP-8 input.

NOT a canonical UIL compiler, and not proof of historical CHIP-8 equivalence.
The ROM is caller-supplied and SHA-256 checked; no program bytes are embedded.
Specialized paths are guarded by PC + fetched word; all other states use the
existing chip8lab.vm.Machine.step interpreter as a truthful fallback.
"""
from __future__ import annotations
import hashlib
from chip8lab.vm import Machine, Quirks, Trap

SOURCE_SHA256 = '09f67a5ef6f3cd9a65edc1e73786bf31a524e279bc1607e1953c6eb80c33b6ee'
FORMAT = 'fdisbull-chip8-python-udc-study-1'
MODULE_NAME = 'udc_snek'
SPECIALIZED_SITES = 17

def create_machine(rom: bytes, *, seed: int=42, quirks=None):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256:
        raise ValueError('CHIP-8 ROM input does not match pinned source identity')
    m = Machine(seed=seed, quirks=quirks or Quirks())
    m.load_rom(rom)
    return m

def step(m: Machine, stats: dict | None=None):
    pc = m.pc
    if pc < 0 or pc + 1 >= 4096 or (m.waiting and not m.keys):
        if stats is not None: stats['fallback'] = stats.get('fallback', 0) + 1
        return m.step()
    fetched = (m.memory[pc] << 8) | m.memory[pc+1]
    if pc == 512 and fetched == 41528:
        m.last_family = 'LD_I'
        m.pc = pc + 2
        m.i = 568
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 516 and fetched == 224:
        m.last_family = 'CLS'
        m.pc = pc + 2
        m.frame[:] = bytes(len(m.frame))
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 518 and fetched == 65287:
        m.last_family = 'LD_VX_DT'
        m.pc = pc + 2
        m.v[15] = m.delay
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 520 and fetched == 16128:
        m.last_family = 'SE_VX_KK'
        m.pc = pc + 2
        if m.v[15] == 0: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 524 and fetched == 62229:
        m.last_family = 'LD_DT_VX'
        m.pc = pc + 2
        m.delay = m.v[3]
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 526 and fetched == 58529:
        m.last_family = 'SKNP'
        m.pc = pc + 2
        if m.v[4] not in m.keys: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 530 and fetched == 58785:
        m.last_family = 'SKNP'
        m.pc = pc + 2
        if m.v[5] not in m.keys: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 534 and fetched == 59041:
        m.last_family = 'SKNP'
        m.pc = pc + 2
        if m.v[6] not in m.keys: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 538 and fetched == 59297:
        m.last_family = 'SKNP'
        m.pc = pc + 2
        if m.v[7] not in m.keys: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 542 and fetched == 16896:
        m.last_family = 'SNE_VX_KK'
        m.pc = pc + 2
        if m.v[2] != 0: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 544 and fetched == 28673:
        m.last_family = 'ADD_VX_KK'
        m.pc = pc + 2
        m.v[0] = (m.v[0] + 1) & 255
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 546 and fetched == 16897:
        m.last_family = 'SNE_VX_KK'
        m.pc = pc + 2
        if m.v[2] != 1: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 550 and fetched == 16898:
        m.last_family = 'SNE_VX_KK'
        m.pc = pc + 2
        if m.v[2] != 2: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 554 and fetched == 16899:
        m.last_family = 'SNE_VX_KK'
        m.pc = pc + 2
        if m.v[2] != 3: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 558 and fetched == 53265:
        m.last_family = 'DRW'
        m.pc = pc + 2
        m.mem_range(m.i, 1, pc, fetched)
        px, py = m.v[0] % 64, m.v[1] % 32
        collision = 0
        for row in range(1):
            bits = m.memory[m.i + row]
            for col in range(8):
                if bits & (128 >> col):
                    xx, yy = px + col, py + row
                    if m.quirks.clip_sprites and (xx >= 64 or yy >= 32): continue
                    pixel = (yy % 32) * 64 + (xx % 64)
                    if m.frame[pixel]: collision = 1
                    m.frame[pixel] ^= 1
        m.v[15] = collision
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 560 and fetched == 20224:
        m.last_family = 'SNE_VX_KK'
        m.pc = pc + 2
        if m.v[15] != 0: m.pc += 2
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if pc == 562 and fetched == 4614:
        m.last_family = 'JP'
        m.pc = pc + 2
        m.pc = 518
        m.steps += 1
        if stats is not None: stats["specialized"] = stats.get("specialized", 0) + 1
        return "executed"
    if stats is not None: stats['fallback'] = stats.get('fallback', 0) + 1
    return m.step()