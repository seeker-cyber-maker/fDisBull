"""Authored chain-4 raster, nontrivial DAC, invalid-mode and ABA controls."""
import struct

from support.dos_process_fixture import assemble


COMMANDS = {
    'palette': (1, 'palette_done'), 'vram': (2, 'vram_done'),
    'invalid_text': (3, 'invalid_done'), 'restore': (4, 'restore_done'),
    'blank': (5, 'blank_done'), 'enable': (6, 'enable_done'),
    'panning': (7, 'panning_done'), 'unpan': (8, 'unpan_done'),
    'page_aba': (9, 'aba_done'),
}


def raster_program(directory, nasm):
    code = assemble(directory, 'raster-proof', r'''
bits 16
org 100h
    nop
    call setup
ready:
    nop
poll_command:
    mov al,[command]
    cmp al,1
    je palette
    cmp al,2
    je vram
    cmp al,3
    je invalid
    cmp al,4
    je restore
    cmp al,5
    je blank
    cmp al,6
    je enable
    cmp al,7
    je panning
    cmp al,8
    je unpan
    cmp al,9
    je aba
    jmp poll_command
%macro finish 1
    mov byte [command],0
%1:
    nop
    jmp poll_command
%endmacro
palette:
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
    finish palette_done
vram:
    mov byte [es:199*320+1],3
    finish vram_done
invalid:
    mov al,11h
    call read_cr
    and ah,7fh
    call write_cr
    mov al,1
    xor ah,ah
    call write_cr
    mov al,12h
    xor ah,ah
    call write_cr
    mov al,7
    call read_cr
    and ah,0bdh
    call write_cr
    mov al,9
    call read_cr
    and ah,0e0h
    call write_cr
    mov dx,3ceh
    mov al,6
    out dx,al
    inc dx
    in al,dx
    and al,0feh
    out dx,al
    finish invalid_done
restore:
    call setup
    finish restore_done
blank:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    xor al,al
    out dx,al
    finish blank_done
enable:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,20h
    out dx,al
    finish enable_done
panning:
    mov ah,1
    call set_pan
    finish panning_done
unpan:
    xor ah,ah
    call set_pan
    finish unpan_done
aba:
    mov al,0dh
    mov ah,20h
    call write_cr
    xor ah,ah
    call write_cr
    finish aba_done
set_pan:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,13h
    out dx,al
    mov al,ah
    out dx,al
    mov al,20h
    out dx,al
    ret
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
setup:
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,32000
    rep stosw
    mov byte [es:0],1
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
    ret
command: db 0
    db 'RPF1'
    dw ready,palette_done,vram_done,invalid_done,restore_done
    dw blank_done,enable_done,panning_done,unpan_done,aba_done,command
''', nasm)
    names = ('ready', 'palette_done', 'vram_done', 'invalid_done', 'restore_done',
             'blank_done', 'enable_done', 'panning_done', 'unpan_done',
             'aba_done', 'command')
    assert code[-26:-22] == b'RPF1'
    return code, dict(zip(names, struct.unpack('<11H', code[-22:]), strict=True))


def oracle(*, changed_palette=False, changed_vram=False):
    """Expected authored bytes and QEMU's declared DAC expansion, independent
    of the proof and the renderer image. Nontrivial entries exercise c6_to_8.
    """
    palette = bytearray(256 * 3)
    palette[3:6] = bytes((168, 87, 7) if changed_palette else (7, 87, 168))
    palette[6:9] = bytes((0, 255, 0))
    palette[9:12] = bytes((255, 0, 0))
    indices = bytearray(64000)
    indices[0], indices[-1] = 1, 2
    if changed_vram:
        indices[199 * 320 + 1] = 3
    rgb = b''.join(bytes(palette[index * 3:index * 3 + 3]) for index in indices)
    return bytes(indices), bytes(palette), rgb
