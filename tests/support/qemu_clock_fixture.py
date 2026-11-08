"""Authored DOS witnesses for a native QEMU virtual-clock deadline.

The programs contain no debugger or host-clock logic. Their counters expose
busy execution, a CPU halted with interrupts disabled, and independently
programmed PIT interrupts that wake an interrupt-enabled CPU. Only their text
belongs in the repository; assembly products stay in the caller's test dir.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


PIT_INPUT_HZ = 1_193_182
PIT_DIVISOR = 1193


def _symbols(code, names):
    size = 4 + 2 * len(names)
    if code[-size:-size + 4] != b"CLK1":
        raise ValueError("Authored clock witness symbol footer is missing")
    return dict(zip(names, struct.unpack_from("<" + "H" * len(names), code,
                                               len(code) - size + 4), strict=True))


def busy_clock(directory, nasm):
    """CLI busy loop with an early write and a later independent loop fence.

    Reaching the late fence executes over 196,000 guest instructions. With the
    admitted fixed shift of seven this passes a cancelled one-millisecond
    timer by a wide margin, without relying on a host sleep or wall watchdog.
    """
    code = assemble(directory, "clock-busy", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
ready:
    nop
first_write:
    inc dword [loop_count]
    cmp dword [loop_count],65536
    jb first_write
late_boundary:
    nop
steady:
    inc dword [loop_count]
    jmp steady
loop_count: dd 0
    db 'CLK1'
    dw ready,first_write,late_boundary,loop_count
""", nasm)
    return code, _symbols(code, ("ready_ip", "first_write_ip",
                                 "late_boundary_ip", "loop_count_ip"))


def halted_clock(directory, nasm):
    """CLI+HLT: virtual device time can advance while guest execution cannot."""
    code = assemble(directory, "clock-halted", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
ready:
    nop
halt:
    hlt
    inc dword [unexpected_wakes]
    jmp halt
unexpected_wakes: dd 0
    db 'CLK1'
    dw ready,unexpected_wakes
""", nasm)
    return code, _symbols(code, ("ready_ip", "unexpected_wakes_ip"))


def pit_clock(directory, nasm):
    """Own IRQ0 and count PIT interrupts separately from HLT return paths.

    Channel zero runs in mode two with a divisor of 1193, approximately one
    millisecond. All other PIC IRQ lines are masked. This private fixture must
    be terminated by its owner; it deliberately does not restore DOS vectors.
    """
    code = assemble(directory, "clock-pit", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
    xor ax,ax
    mov es,ax
    mov word [es:8*4],pit_irq
    mov ax,cs
    mov [es:8*4+2],ax
    mov al,0feh
    out 21h,al
    mov al,0ffh
    out 0a1h,al
    mov al,34h
    out 43h,al
    mov ax,""" + str(PIT_DIVISOR) + r"""
    out 40h,al
    mov al,ah
    out 40h,al
ready:
    nop
sleep:
    sti
    hlt
    inc dword [wake_count]
    jmp sleep
pit_irq:
    push ax
    inc dword [cs:irq_count]
    mov al,20h
    out 20h,al
    pop ax
    iret
irq_count: dd 0
wake_count: dd 0
    db 'CLK1'
    dw ready,irq_count,wake_count
""", nasm)
    return code, _symbols(code, ("ready_ip", "irq_count_ip", "wake_count_ip"))
