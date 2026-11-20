"""Authored source-row stimulus and an independent legacy RGB oracle.

No candidate frame/proof values generate expected pixels. The guest owns its
indices, DAC and port-readable timing snapshot. Tests control when one short
mutation runs, and prove that its whole execution stayed in a sampled-row gap.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from support.qemu_retrace_fixture import guest_timing, precise_timing


WIDTH, HEIGHT = 320, 200
COMMANDS = {
    'mutate': (1, 'mutated'),
    'invalid_text': (2, 'invalid'),
    'restore': (3, 'restored'),
    'blank': (4, 'blanked'),
    'enable': (5, 'enabled'),
    'panning': (6, 'panned'),
    'unpan': (7, 'unpanned'),
    'page_aba': (8, 'aba'),
}


def video_frame_program(directory, nasm):
    code = assemble(directory, 'video-frame-rows', r'''
bits 16
org 100h
    nop
    call setup
ready:
    nop
dispatch:
    mov al,[command]
    cmp al,1
    je mutate
    cmp al,2
    je invalid_text
    cmp al,3
    je restore
    cmp al,4
    je blank
    cmp al,5
    je enable
    cmp al,6
    je panning
    cmp al,7
    je unpan
    cmp al,8
    je page_aba
    jmp dispatch
%macro finish 1
    mov byte [command],0
%1:
    nop
    jmp dispatch
%endmacro
mutate:
    ; Deliberately short: the test proves all writes fit before source row100.
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
invalid_text:
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
    finish invalid
restore:
    call setup
    finish restored
blank:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    xor al,al
    out dx,al
    finish blanked
enable:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,20h
    out dx,al
    finish enabled
panning:
    mov ah,1
    call set_pan
    finish panned
unpan:
    xor ah,ah
    call set_pan
    finish unpanned
page_aba:
    mov al,0dh
    call read_cr
    mov [page_before],ah
    xor ah,20h
    call write_cr
    mov ah,[page_before]
    call write_cr
    call read_cr
    mov [page_after],ah
    finish aba
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
    ; Nonendpoint components distinguish DOSBox bit replication from QEMU.
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
    mov byte [mutation_count],0
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
mutation_count: db 0
page_before: db 0
page_after: db 0
timing_raw: times 11 db 0
    db 'VFR1'
    dw ready,dispatch,mutated,invalid,restored,blanked,enabled,panned,unpanned,aba
    dw command,mutation_count,page_before,page_after,timing_raw
''', nasm)
    names = ('ready', 'dispatch', 'mutated', 'invalid', 'restored', 'blanked',
             'enabled', 'panned', 'unpanned', 'aba', 'command', 'mutation_count',
             'page_before', 'page_after', 'timing_raw')
    size = 4 + len(names) * 2
    assert code[-size:-size + 4] == b'VFR1'
    values = struct.unpack('<' + 'H' * len(names), code[-len(names) * 2:])
    return code, dict(zip(names, values, strict=True))


def expected_rgb(*, split_row=HEIGHT, changed_vram=False, wrong_qemu_dac=False):
    """Rows before split use the old DAC; later rows use the guest mutation.

    The wrong conversion is a negative control, never a permissible tolerance.
    A split of zero describes the deliberately wrong final-VRAM/DAC snapshot.
    """
    assert type(split_row) is int and 0 <= split_row <= HEIGHT
    expand = (lambda value: (value << 2) | ((value & 1) * 3)) if wrong_qemu_dac else (
        lambda value: (value << 2) | (value >> 4))
    old = bytes(expand(value) for value in (1, 21, 42))
    new = bytes(expand(value) for value in (42, 21, 1))
    rows = [((old if y < split_row else new) * WIDTH) for y in range(HEIGHT)]
    rgb = bytearray(b''.join(rows))
    rgb[0:3] = b'\xff\x00\x00'
    rgb[-3:] = b'\x00\xff\x00'
    if changed_vram:
        offset = (199 * WIDTH + 1) * 3
        rgb[offset:offset + 3] = b'\xff\x00\x00'
    return bytes(rgb)


def guest_video_timing(raw_bytes):
    """Programmed native precise timing from guest port reads, not frame info.

    This intentionally reuses the existing independent VGA timing oracle. It
    does not assert physical hardware cycle accuracy or DOSBox phase equality.
    """
    raw = guest_timing(raw_bytes)
    assert raw['vbe-enable'] == 0
    timing = precise_timing(raw)
    horizontal_ns = timing['ticks-per-char'] * timing['htotal']
    period_ns = timing['ticks-per-char'] * timing['total-chars']
    assert horizontal_ns > 0 and period_ns > horizontal_ns * HEIGHT * 2
    return dict(raw=raw, line_ns=horizontal_ns, period_ns=period_ns)


def frame_schedule(timing, started_ns):
    """Declared fixed phase policy, computed before reading a candidate frame."""
    line, period = timing['line_ns'], timing['period_ns']
    boundary = (started_ns // period + 1) * period
    deadlines = tuple(boundary + line // 4 + 2 * row * line for row in range(HEIGHT))
    return dict(boundary=boundary, rows=deadlines, line_ns=line, period_ns=period)
