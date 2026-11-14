"""Authored IRQ1/HLT witness independent of the native scheduling receipt."""
import struct

from support.dos_process_fixture import assemble


def halted_keyboard(directory, nasm):
    """Mask every PIC line except IRQ1, then wait for actual keyboard bytes.

    A default-list virtual input timer must wake this otherwise idle guest.
    The fixture owns its IRQ vector only inside a disposable machine.
    """
    code = assemble(directory, 'scheduled-keyboard-hlt', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
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
halt:
    hlt
    inc word [wakes]
    jmp halt
keyboard_irq:
    push ax
    in al,60h
    mov [cs:last_key],al
    inc word [cs:key_count]
    mov al,20h
    out 20h,al
    pop ax
    iret
key_count: dw 0
last_key: db 0
wakes: dw 0
    db 'SIN1'
    dw ready,key_count,last_key,wakes
''', nasm)
    assert code[-12:-8] == b'SIN1'
    names = ('ready_ip', 'key_count_ip', 'last_key_ip', 'wakes_ip')
    return code, dict(zip(names, struct.unpack_from('<4H', code, len(code) - 8), strict=True))
