"""Authored palette-only mutation, independent of retained renderer sampling."""
import struct

from support.dos_process_fixture import assemble


def palette_display(directory, nasm):
    code = assemble(directory, 'display-palette', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    mov ax,13h
    int 10h
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
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,32000
    cld
    rep stosw
    mov byte [es:10*320+10],4
    cli
ready:
    nop
wait_palette:
    cmp byte [phase],0
    je wait_palette
    ; Change only the palette entry. The pixel index and mode stay the same.
    mov dx,3c8h
    mov al,4
    out dx,al
    inc dx
    xor al,al
    out dx,al
    out dx,al
    mov al,63
    out dx,al
palette_ready:
    nop
forever:
    jmp forever
phase: db 0
    db 'DPP1'
    dw ready,palette_ready,phase
''', nasm)
    assert code[-10:-6] == b'DPP1'
    return code, dict(zip(('ready_ip', 'palette_ready_ip', 'phase_ip'),
                         struct.unpack('<3H', code[-6:]), strict=True))
