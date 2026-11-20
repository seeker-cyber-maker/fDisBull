"""Authored VGA/IRQ instruction witnesses for a next-source-raster fence.

The old source-row fixture supplies only independent timing/RGB formulae.
This guest adds real stop sites, bounded IRQ1 journals and a halting CPU; it
does not consume any candidate frame/fence field to create expected pixels.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


FENCE_COMMANDS = {
    'enable_irq': (1, 'irq_enabled'),
    'disable_irq': (2, 'irq_disabled'),
    'mutate': (3, 'mutated'),
    'page_aba': (4, 'aba_done'),
    'blank': (5, 'blank_done'),
    'enable_video': (6, 'video_enabled'),
    'halt': (7, 'halt_site'),
}


def fence_program(directory, nasm):
    data = assemble(directory, 'video-frame-fence', r'''
bits 16
org 100h
    nop
    call setup
ready:
    nop
loop_start:
    inc dword [iterations]
hook_site:
    nop
    mov al,[command]
    cmp al,1
    je enable_irq
    cmp al,2
    je disable_irq
    cmp al,3
    je mutate
    cmp al,4
    je page_aba
    cmp al,5
    je blank
    cmp al,6
    je enable_video
    cmp al,7
    je halt
    jmp loop_start
%macro finish 1
    mov byte [command],0
%1:
    nop
    jmp loop_start
%endmacro
enable_irq:
    sti
    finish irq_enabled
disable_irq:
    cli
    finish irq_disabled
mutate:
    mov dx,3c8h
    mov al,1
    out dx,al
    inc dx
    mov al,42
    out dx,al
    mov al,21
    out dx,al
    mov al,1
    out dx,al
    mov byte [es:199*320+1],3
    inc byte [mutation_count]
    finish mutated
page_aba:
    mov al,0dh
    call read_cr
    mov [page_before],ah
    xor ah,20h
aba_out:
    call write_cr
    mov ah,[page_before]
    call write_cr
    call read_cr
    mov [page_after],ah
    finish aba_done
blank:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    xor al,al
abort_site:
    out dx,al
abort_after:
    inc byte [after_abort]
    finish blank_done
enable_video:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,20h
    out dx,al
    finish video_enabled
halt:
    cli
    mov byte [command],0
halt_site:
    hlt
    inc byte [halt_wakes]
    jmp halt_site
read_cr:
    mov dx,3d4h
    out dx,al
    push ax
    inc dx
    in al,dx
    mov ah,al
    pop bx
    mov al,bl
    ret
write_cr:
    mov dx,3d4h
    out dx,ax
    ret
irq1:
    push ax
    push bx
    push dx
    in al,60h
    xor bx,bx
    mov bl,[cs:scan_count]
    cmp bl,32
    jae .overflow
    mov [cs:scan_codes+bx],al
    inc byte [cs:scan_count]
    jmp .ack
.overflow:
    mov byte [cs:scan_overflow],1
.ack:
    in al,61h
    mov ah,al
    or al,80h
    out 61h,al
    mov al,ah
    out 61h,al
    mov al,20h
    out 20h,al
    pop dx
    pop bx
    pop ax
    iret
setup:
    mov ax,13h
    int 10h
    cli
    push cs
    pop ds
    cld
    mov ax,0a000h
    mov es,ax
    xor di,di
    mov ax,0101h
    mov cx,32000
    rep stosw
    mov byte [es:0],3
    mov byte [es:63999],2
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    mov cx,768
.zero_palette:
    out dx,al
    loop .zero_palette
    dec dx
    mov al,1
    out dx,al
    inc dx
    mov al,1
    out dx,al
    mov al,21
    out dx,al
    mov al,42
    out dx,al
    xor al,al
    out dx,al
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    out dx,al
    push ds
    xor ax,ax
    mov ds,ax
    mov word [9*4],irq1
    mov [9*4+2],cs
    pop ds
    in al,21h
    and al,0fdh
    out 21h,al
    call snapshot_timing
    ret
snapshot_timing:
    pusha
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
.crtc:
    mov dx,3d4h
    lodsb
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    loop .crtc
    mov dx,1ceh
    mov ax,4
    out dx,ax
    inc dx
    in ax,dx
    mov [di],ax
    popa
    ret
crtc_indices: db 0,4,5,6,7,10h,11h
command: db 0
iterations: dd 0
mutation_count: db 0
page_before: db 0
page_after: db 0
after_abort: db 0
halt_wakes: db 0
scan_count: db 0
scan_overflow: db 0
scan_codes: times 32 db 0
timing_raw: times 11 db 0
    db 'VFC1'
    dw ready,loop_start,hook_site,irq_enabled,irq_disabled,mutated,aba_done
    dw blank_done,video_enabled,halt_site,aba_out,abort_site,abort_after
    dw command,iterations,mutation_count,page_before,page_after,after_abort,halt_wakes
    dw scan_count,scan_overflow,scan_codes,timing_raw
''', nasm)
    names = ('ready', 'loop_start', 'hook_site', 'irq_enabled', 'irq_disabled',
             'mutated', 'aba_done', 'blank_done', 'video_enabled', 'halt_site',
             'aba_out', 'abort_site', 'abort_after', 'command', 'iterations',
             'mutation_count', 'page_before', 'page_after', 'after_abort',
             'halt_wakes', 'scan_count', 'scan_overflow', 'scan_codes', 'timing_raw')
    count = len(names)
    assert data[-4 - count * 2:-count * 2] == b'VFC1'
    return data, dict(zip(names, struct.unpack('<' + 'H' * count, data[-count * 2:]), strict=True))
