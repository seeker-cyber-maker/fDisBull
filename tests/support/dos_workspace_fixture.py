"""Authored DOS INT 21h workspace probe; no vendor or target bytes."""
from __future__ import annotations

import struct
from .dos_process_fixture import assemble


def workspace_probe(directory, nasm):
    """Return a COM and offsets for open-handle and completed-operation stops.

    The admitted directory supplies EXIST.BIN and GONE.BIN. At ``open_ready``
    EXIST.BIN is open after a two-byte read and a seek to absolute offset two.
    ``done`` follows read/close, create/write/close, rename and deletion. Each
    four-byte result entry holds the returned AX and FLAGS, in that order.
    """
    image = assemble(directory, 'workspace-probe', r'''
bits 16
org 100h
    push cs
    pop ds
    mov dx, existing
    mov ax, 3d00h
    int 21h
    mov [results], ax
    pushf
    pop word [results+2]
    jc failed
    mov [handle], ax
    mov bx, ax
    mov dx, first_read
    mov cx, 2
    mov ah, 3fh
    int 21h
    mov [results+4], ax
    pushf
    pop word [results+6]
    jc failed
    mov bx, [handle]
    xor cx, cx
    mov dx, 2
    mov ax, 4200h
    int 21h
    mov [results+8], ax
    pushf
    pop word [results+10]
    jc failed
open_ready:
    nop
    mov bx, [handle]
    mov dx, second_read
    mov cx, 2
    mov ah, 3fh
    int 21h
    mov [results+12], ax
    pushf
    pop word [results+14]
    jc failed
    mov bx, [handle]
    mov ah, 3eh
    int 21h
    mov [results+16], ax
    pushf
    pop word [results+18]
    jc failed
    mov dx, created
    xor cx, cx
    mov ah, 3ch
    int 21h
    mov [results+20], ax
    pushf
    pop word [results+22]
    jc failed
    mov bx, ax
    mov [handle], ax
    mov dx, payload
    mov cx, 4
    mov ah, 40h
    int 21h
    mov [results+24], ax
    pushf
    pop word [results+26]
    jc failed
    mov bx, [handle]
    mov ah, 3eh
    int 21h
    mov [results+28], ax
    pushf
    pop word [results+30]
    jc failed
    push ds
    pop es
    mov dx, created
    mov di, renamed
    mov ah, 56h
    int 21h
    mov [results+32], ax
    pushf
    pop word [results+34]
    jc failed
    mov dx, removed
    mov ah, 41h
    int 21h
    mov [results+36], ax
    pushf
    pop word [results+38]
    jc failed
    mov ah, 0dh
    int 21h
    mov word [status], 0beefh
    jmp short done
failed:
    mov word [status], 0deadh
done:
    nop
    mov ax, 4c2ah
    int 21h
handle: dw 0
status: dw 0
results: times 40 db 0
first_read: times 2 db 0
second_read: times 2 db 0
existing: db 'EXIST.BIN',0
created: db 'NEW.DAT',0
renamed: db 'RENAMED.DAT',0
removed: db 'GONE.BIN',0
payload: db 10h,00h,0ffh,41h
    db 'FWSP'
    dw open_ready-100h,done-100h,status-100h,results-100h,first_read-100h,second_read-100h
''', nasm)
    if image[-16:-12] != b'FWSP':
        raise ValueError('Workspace-probe footer is missing')
    values = struct.unpack_from('<6H', image, len(image)-12)
    return image, dict(zip(('open_ready','done','status','results','first_read','second_read'), values))
