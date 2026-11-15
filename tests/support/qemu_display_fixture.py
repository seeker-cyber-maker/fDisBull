"""Authored partial VGA drawing and mode-change witness, with explicit fences."""
import struct

from support.dos_process_fixture import assemble


def partial_display(directory, nasm):
    code = assemble(directory, 'display-partial', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    mov ax,13h
    int 10h
    ; Own the tested DAC entries; do not rely on a firmware color table.
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    out dx,al
    out dx,al
    out dx,al
    dec dx
    mov al,4
    out dx,al
    inc dx
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    out dx,al
    dec dx
    mov al,2
    out dx,al
    inc dx
    xor al,al
    out dx,al
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,32000
    cld
    rep stosw
    cli
ready:
    nop
first_wait:
    cmp byte [phase],0
    je first_wait
    mov byte [es:10*320+10],4
partial_ready:
    nop
second_wait:
    cmp byte [phase],1
    je second_wait
    mov byte [es:10*320+20],2
complete_ready:
    nop
mode_wait:
    cmp byte [phase],2
    je mode_wait
    mov ax,3
    int 10h
text_ready:
    nop
forever:
    jmp forever
phase: db 0
    db 'DSP1'
    dw ready,partial_ready,complete_ready,text_ready,phase
''', nasm)
    assert code[-14:-10] == b'DSP1'
    return code, dict(zip(('ready_ip', 'partial_ready_ip', 'complete_ready_ip',
                          'text_ready_ip', 'phase_ip'), struct.unpack('<5H', code[-10:]), strict=True))
