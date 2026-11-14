"""Authored VGA/IRQ1 witnesses for a retrace-constrained input callback.

The guest records its timing ports and actual keyboard bytes/status reads.
It has no host clock, QMP receipt, renderer or application-frame oracle.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


ABA = 1
ENABLE_VBE = 2
REENTER_MODE13 = 3


def retrace_keyboard(directory, nasm, *, halted=False, capacity=16):
    """Own IRQ1 and all PIC masks inside a disposable mode-13h machine.

    Commands run only after the explicit continue. An IRQ fence follows the
    actual scancode/status stores, before EOI and IRET. The halted variant has
    no unmasked timer interrupt; only a keyboard IRQ can advance its wake count.
    """
    assert type(capacity) is int and 1 <= capacity <= 256
    code = assemble(directory, 'retrace-input-hlt' if halted else 'retrace-input-busy',
                    f'%define HALTED {int(halted)}\n%define CAPACITY {capacity}\n' + r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    call snapshot_timing
    mov al,[timing_raw+7]
    mov [original_cr10],al
    xor ax,ax
    mov es,ax
    mov word [es:9*4],keyboard_irq
    mov ax,cs
    mov [es:9*4+2],ax
    mov al,0fdh
    out 21h,al
    mov al,0ffh
    out 0a1h,al
    sti
ready:
    nop
main_loop:
    mov al,[command]
    cmp al,1
    je aba_cr10
    cmp al,2
    je enable_vbe
    cmp al,3
    je reenter_mode13
%if HALTED
    hlt
    inc word [wakes]
%endif
    jmp main_loop

aba_cr10:
    cli
    mov al,[original_cr10]
    xor al,4
    call write_cr10
    mov al,[original_cr10]
    call write_cr10
    jmp finish_command

%macro write_vbe 2
    mov dx,1ceh
    mov ax,%1
    out dx,ax
    inc dx
    mov ax,%2
    out dx,ax
%endmacro

enable_vbe:
    cli
    write_vbe 1,320
    write_vbe 2,200
    write_vbe 3,8
    write_vbe 4,81h
    jmp finish_command

reenter_mode13:
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
finish_command:
    call snapshot_timing
    mov byte [command],0
    sti
command_done:
    nop
    jmp main_loop

write_cr10:
    mov ah,al
    mov dx,3d4h
    mov al,10h
    out dx,al
    inc dx
    mov al,ah
    out dx,al
    ret

snapshot_timing:
    push ax
    push cx
    push dx
    push si
    push di
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
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    ret

keyboard_irq:
    push ax
    push bx
    push dx
    push ds
    push cs
    pop ds
    in al,64h
    test al,1
    jz keyboard_eoi
    test al,20h
    jnz keyboard_eoi
    in al,60h
    mov bx,[key_count]
    cmp bx,CAPACITY
    jae keyboard_full
    mov [key_bytes+bx],al
    mov dx,3dah
sample_status:
    in al,dx
    mov [status_bytes+bx],al
    inc word [key_count]
input_seen:
    nop
keyboard_eoi:
    mov al,20h
    out 20h,al
    pop ds
    pop dx
    pop bx
    pop ax
    iret
keyboard_full:
    inc word [dropped_keys]
    jmp keyboard_eoi

crtc_indices: db 0,4,5,6,7,10h,11h
original_cr10: db 0
command: db 0
timing_raw: times 11 db 0
key_count: dw 0
key_bytes: times CAPACITY db 0
status_bytes: times CAPACITY db 0
wakes: dw 0
dropped_keys: dw 0
    db 'RIN1'
    dw ready,main_loop,sample_status,input_seen,command_done,command
    dw timing_raw,key_count,key_bytes,status_bytes,wakes,dropped_keys
''', nasm)
    names = ('ready_ip', 'main_loop_ip', 'sample_status_ip', 'input_seen_ip',
             'command_done_ip', 'command_ip', 'timing_raw_ip', 'key_count_ip',
             'key_bytes_ip', 'status_bytes_ip', 'wakes_ip', 'dropped_keys_ip')
    size = 4 + 2 * len(names)
    assert code[-size:-size + 4] == b'RIN1'
    offsets = struct.unpack('<' + 'H' * len(names), code[-2 * len(names):])
    return code, dict(zip(names, offsets, strict=True))
