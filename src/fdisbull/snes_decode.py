"""Bounded LoROM address translation and single-instruction 65816 facts.

Caller supplies the observed accumulator/index widths at every instruction.
Neither this module nor a successful header probe establishes a cartridge map.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path

_M_IMMEDIATE = frozenset((0x09, 0x29, 0x49, 0x69, 0x89, 0xA9, 0xC9, 0xE9))
_X_IMMEDIATE = frozenset((0xA0, 0xA2, 0xC0, 0xE0))


def lorom_offset(cpu_address: int, rom_size: int, *, copier_header: int = 0) -> int:
    """Map a qualified low-bank, upper-half LoROM address to a file offset.

    Refuse low halves, WRAM and high-bank mirrors; the caller must independently
    establish this mapping for the cartridge and provide its actual extent.
    """
    if (type(cpu_address) is not int or type(rom_size) is not int or
            type(copier_header) is not int or rom_size <= 0 or
            copier_header not in (0, 512) or not 0 <= cpu_address <= 0xFFFFFF):
        raise ValueError('invalid address or ROM extent')
    bank, address = cpu_address >> 16, cpu_address & 0xFFFF
    if bank > 0x7D or address < 0x8000:
        raise ValueError('outside qualified LoROM window')
    offset = (bank << 15) | (address & 0x7FFF)
    if offset >= rom_size:
        raise ValueError('outside supplied ROM extent')
    return copier_header + offset


def decoder_identity() -> dict:
    import capstone
    native = Path(capstone._cs._name)
    return {'distribution': version('capstone'), 'binding': capstone.__version__,
            'native_version': list(capstone.cs_version()),
            'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest()}


def decode_one(data: bytes, cpu_address: int, *, m8: bool, x8: bool) -> dict:
    """Decode one instruction at known 65816 M/X widths, without advancing state.

    For short/short, Capstone builds may reject their documented mode. Since M
    and X affect different immediate opcodes, select the working 16-bit opposite
    width for that *one* instruction. Reject unknown configurations rather than
    falling back to a 6502 decoder. Callers must obtain fresh M/X after status
    changes and resolve branches and banks separately.
    """
    import capstone as cs
    if (not isinstance(data, bytes) or not data or type(m8) is not bool or
            type(x8) is not bool or type(cpu_address) is not int or
            not 0 <= cpu_address <= 0xFFFFFF):
        raise ValueError('instruction bytes, address and exact widths required')
    if m8 and x8:
        mode = (cs.CS_MODE_MOS65XX_65816_LONG_M if data[0] in _X_IMMEDIATE
                else cs.CS_MODE_MOS65XX_65816_LONG_X)
    elif m8:
        mode = cs.CS_MODE_MOS65XX_65816_LONG_X
    elif x8:
        mode = cs.CS_MODE_MOS65XX_65816_LONG_M
    else:
        mode = cs.CS_MODE_MOS65XX_65816_LONG_MX
    try:
        decoder = cs.Cs(cs.CS_ARCH_MOS65XX, mode)
        instruction = next(iter(decoder.disasm(data[:4], cpu_address, count=1)), None)
    except cs.CsError as exc:
        raise ValueError('65816 decoder mode unavailable') from exc
    if instruction is None:
        raise ValueError('incomplete or unsupported instruction')
    if (cpu_address & 0xFFFF) + instruction.size > 0x10000:
        raise ValueError('instruction crosses unqualified program-bank boundary')
    if data[0] in _M_IMMEDIATE and instruction.size != (2 if m8 else 3):
        raise ValueError('decoder returned unexpected accumulator width')
    if data[0] in _X_IMMEDIATE and instruction.size != (2 if x8 else 3):
        raise ValueError('decoder returned unexpected index width')
    return {'address': cpu_address, 'size': instruction.size,
            'mnemonic': instruction.mnemonic, 'operands': instruction.op_str,
            'm8': m8, 'x8': x8}
