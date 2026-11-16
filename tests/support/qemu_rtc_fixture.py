"""Authored guest CMOS reader; the host never writes its calendar or registers."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


def rtc_calendar(directory, nasm):
    """Read two coherent calendar tuples around a stopped capture frontier.

Each tuple is seconds/minutes/hours/day/month/year/century/register B. The
reader retries on UIP or a changed seconds byte and preserves guest IF. It
does not derive an expected date from the host clock or alter RTC settings.
"""
    text = r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    push cs
    pop es
    cld
    mov di,baseline
    call calendar
    mov word [stage],1
ready:
    nop
    mov di,later
    call calendar
    mov word [stage],2
sampled:
    nop
    mov ah,1
    int 16h
    jz sampled
    xor ah,ah
    int 16h
    cmp al,'q'
    jne sampled
    mov ax,4c2ah
    int 21h
failed:
    mov word [stage],0ffffh
    jmp failed
calendar:
    pushf
    cli
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov bx,di
    mov cx,0ffffh
retry:
    mov al,0ah
    call cmos
    test al,80h
    jnz retry_next
    mov di,bx
    mov si,indices
    mov dx,8
read_fields:
    lodsb
    call cmos
    stosb
    dec dx
    jnz read_fields
    xor al,al
    call cmos
    cmp al,[bx]
    jne retry_next
    mov al,0ah
    call cmos
    test al,80h
    jz coherent
retry_next:
    loop retry
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    popf
    jmp failed
coherent:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    popf
    ret
cmos:
    push dx
    mov dx,70h
    out dx,al
    inc dx
    in al,dx
    pop dx
    ret
indices: db 0,2,4,7,8,9,32h,0bh
report:
    db 'RTC1'
baseline: times 8 db 0
later: times 8 db 0
stage: dw 0
report_end:
    db 'RTCF'
    dw ready,sampled,failed,report,baseline,later,stage,report_end
'''
    code = assemble(directory, 'rtc-calendar', text, nasm)
    names = ('ready', 'sampled', 'failed', 'report', 'baseline', 'later', 'stage', 'report_end')
    footer = 4 + 2 * len(names)
    assert code[-footer:-footer + 4] == b'RTCF'
    offsets = dict(zip(names, struct.unpack_from('<8H', code, len(code) - footer + 4), strict=True))
    offsets['report_size'] = offsets['report_end'] - offsets['report']
    return code, offsets
