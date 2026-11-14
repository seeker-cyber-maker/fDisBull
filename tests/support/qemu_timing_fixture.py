"""Authored halted VGA and DOS-return witnesses for bounded timing controls."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble, com_exit


def halted_retrace(directory, nasm):
    """Record legacy VGA timing, then halt without accepting hardware IRQs.

    A virtual retrace target can be reached without instruction-count progress.
    The counter after HLT independently exposes any unexpected guest wake.
    """
    code = assemble(directory, 'timing-halted-vga', r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    mov di,timing_raw
    mov dx,3cch
    in al,dx
    mov [di],al
    inc di
    mov dx,3c4h
    mov al,1
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    mov si,crtc_indices
    mov cx,7
read_crtc:
    mov dx,3d4h
    lodsb
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    loop read_crtc
    mov dx,1ceh
    mov ax,4
    out dx,ax
    inc dx
    in ax,dx
    mov [di],ax
ready:
    nop
halt:
    hlt
    inc dword [unexpected_wakes]
    jmp halt
crtc_indices: db 0,4,5,6,7,10h,11h
unexpected_wakes: dd 0
timing_raw: times 11 db 0
    db 'HTR1'
    dw ready,unexpected_wakes,timing_raw
''', nasm)
    assert code[-10:-6] == b'HTR1'
    names = ('ready_ip', 'unexpected_wakes_ip', 'timing_raw_ip')
    return code, dict(zip(names, struct.unpack('<3H', code[-6:]), strict=True))


def terminating_clock(directory, nasm):
    """Park after the initial NOP, then genuinely terminate through DOS."""
    return com_exit(37), {'ready_ip': 0x101}
