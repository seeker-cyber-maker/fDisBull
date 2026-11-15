"""Authored IRQ12 packet witness for separately synchronized mouse edges.

The disposable guest owns its controller setup, IRQ12 vector and PIC masks.
It has no DOS mouse driver, cursor-coordinate, QMP or frame-completion oracle.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


def mouse_click_probe(directory, nasm, *, halted=False):
    """Enable stream mode after independently sampling a cleared device state.

    The initial polled packet is retained separately from the IRQ log. Tests
    require it to contain no button or motion, rather than assuming that an
    arbitrary guest has no residual deltas. Polling and log writes are bounded.
    The HLT loop has only IRQ12 unmasked; its wake count is not a packet count.
    """
    assert type(halted) is bool
    code = assemble(directory, 'mouse-click-hlt' if halted else 'mouse-click-busy',
                    f'%define HALTED {int(halted)}\n' + r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    xor ax,ax
    mov es,ax
    mov word [es:74h*4],mouse_irq
    mov ax,cs
    mov [es:74h*4+2],ax

    ; Enable the auxiliary port and its IRQ, preserving unrelated controller
    ; mode bits. IRQ1 and IRQ0 remain masked in the owned PIC configuration.
    call writable
    jc setup_failed
    mov al,0a8h
    out 64h,al
    call writable
    jc setup_failed
    mov al,20h
    out 64h,al
    call readable
    jc setup_failed
    in al,60h
    or al,2
    and al,0dfh
    mov [controller_mode],al
    call writable
    jc setup_failed
    mov al,60h
    out 64h,al
    call writable
    jc setup_failed
    mov al,[controller_mode]
    out 60h,al

    mov bl,0ffh              ; Reset to the three-byte device type.
    call mouse_command
    jc setup_failed
    call read_auxiliary
    jc setup_failed
    cmp al,0aah
    jne setup_failed
    call read_auxiliary
    jc setup_failed
    test al,al
    jnz setup_failed
    mov bl,0f6h              ; Defaults: disabled stream mode.
    call mouse_command
    jc setup_failed
    mov bl,0eah              ; Explicitly select stream mode.
    call mouse_command
    jc setup_failed
    mov bl,0ebh              ; Poll and consume the initial packet while CLI.
    call mouse_command
    jc setup_failed
    call read_auxiliary
    jc setup_failed
    mov [initial_packet],al
    call read_auxiliary
    jc setup_failed
    mov [initial_packet+1],al
    call read_auxiliary
    jc setup_failed
    mov [initial_packet+2],al
    mov bl,0f4h
    call mouse_command
    jc setup_failed
    mov word [setup_status],1
    jmp setup_done
setup_failed:
    mov word [setup_status],0ffffh
setup_done:
    mov al,0fbh              ; Master cascade only.
    out 21h,al
    mov al,0efh              ; Slave IRQ12 only.
    out 0a1h,al
    sti
ready:
    nop
main_loop:
%if HALTED
    hlt
    inc word [wakes]
%else
    inc dword [loop_count]
%endif
    jmp main_loop

writable:
    mov cx,0ffffh
.wait:
    in al,64h
    test al,2
    jz .ok
    loop .wait
    stc
    ret
.ok:
    clc
    ret
readable:
    mov cx,0ffffh
.wait:
    in al,64h
    test al,1
    jnz .ok
    loop .wait
    stc
    ret
.ok:
    clc
    ret
read_auxiliary:
    call readable
    jc .done
    test al,20h
    jz .bad
    in al,60h
    clc
    ret
.bad:
    stc
.done:
    ret
mouse_command:
    call writable
    jc .done
    mov al,0d4h
    out 64h,al
    call writable
    jc .done
    mov al,bl
    out 60h,al
    call read_auxiliary
    jc .done
    mov [setup_ack],al
    cmp al,0fah
    je .ok
    stc
    ret
.ok:
    clc
.done:
    ret

mouse_irq:
    push ax
    push bx
    push ds
    push cs
    pop ds
    in al,64h
    test al,1
    jz mouse_eoi
    test al,20h
    jz mouse_eoi
    in al,60h
    mov bx,[mouse_byte_count]
    cmp bx,96
    jae mouse_log_full
    mov [mouse_bytes+bx],al
    jmp mouse_log_done
mouse_log_full:
    inc word [dropped_bytes]
mouse_log_done:
    inc word [mouse_byte_count]
    xor bx,bx
    mov bl,[mouse_phase]
    mov [last_mouse_packet+bx],al
    inc bl
    cmp bl,3
    jb mouse_partial
    inc word [mouse_packet_count]
    xor bl,bl
    mov [mouse_phase],bl
after_packet:
    nop                     ; A full packet is stored, before EOI/IRET.
    jmp mouse_eoi
mouse_partial:
    mov [mouse_phase],bl
mouse_eoi:
    mov al,20h
    out 0a0h,al
    out 20h,al
    pop ds
    pop bx
    pop ax
    iret

controller_mode: db 0
setup_status: dw 0
setup_ack: db 0
initial_packet: db 0,0,0
mouse_byte_count: dw 0
mouse_packet_count: dw 0
mouse_phase: db 0
last_mouse_packet: db 0,0,0
dropped_bytes: dw 0
wakes: dw 0
loop_count: dd 0
mouse_bytes: times 96 db 0
    db 'MCF1'
    dw ready,main_loop,after_packet,setup_status,setup_ack,initial_packet
    dw mouse_byte_count,mouse_packet_count,mouse_phase,last_mouse_packet
    dw mouse_bytes,dropped_bytes,wakes,loop_count
''', nasm)
    names = ('ready_ip', 'main_loop_ip', 'after_packet_ip', 'setup_status_ip',
             'setup_ack_ip', 'initial_packet_ip', 'mouse_byte_count_ip',
             'mouse_packet_count_ip', 'mouse_phase_ip', 'last_mouse_packet_ip',
             'mouse_bytes_ip', 'dropped_bytes_ip', 'wakes_ip', 'loop_count_ip')
    size = 4 + 2 * len(names)
    assert code[-size:-size + 4] == b'MCF1'
    return code, dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                                                  len(code) - size + 4), strict=True))
