"""Authored boot code for independent native step-boundary witnesses.

The CPU code is deliberately separate from trace normalization. The DIV case
uses an actual zero divisor and records its fault IP on the CPU-created stack.
The REP case has three source bytes and a distinct zeroed destination, so a
partially advanced operation is observable independently of the trace labels.
"""
from __future__ import annotations

import struct


def fault_and_rep_boot():
    base = 0x7c00
    code = bytearray()
    symbols = {}
    fixups = []

    def emit(value):
        code.extend(bytes.fromhex(value))

    def label(name):
        symbols[name] = base + len(code)

    def word(name):
        fixups.append((len(code), name))
        code.extend(b'\0\0')

    emit('ea'); word('setup'); emit('0000')  # Normalize CS to zero.
    label('setup')
    emit('fa fc 31c0 8ed8 8ec0 8ed0 bc0070')
    # CLI; CLD; AX=0; DS=ES=SS=0; SP=7000. Install real vector zero.
    emit('c7060000'); word('fault_handler')
    emit('c70602000000 31db b83412')  # Vector CS=0; BL=0; AX=1234.
    label('fault_at')
    emit('f6f3')                    # DIV BL must fault, with AX unchanged.
    label('after_fault')
    emit('b90300 be'); word('source')
    emit('bf'); word('destination')
    label('rep_at')
    emit('f3a4')                    # REP MOVSB, CX initially three.
    label('done')
    emit('ebfe')                    # Stop or time out in an owned idle loop.
    label('fault_handler')
    emit('89e5 3683460002 cf')       # Skip DIV in the saved fault frame; IRET.
    label('source')
    emit('414243')
    label('destination')
    emit('000000')
    for offset, name in fixups:
        struct.pack_into('<H', code, offset, symbols[name])
    sector = bytes(code).ljust(510, b'\0') + b'\x55\xaa'
    return sector.ljust(1440 * 1024, b'\0'), symbols
