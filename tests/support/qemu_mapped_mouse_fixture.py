"""Authored PS/2 packet, application displacement and drawing witnesses.

The disposable COM owns IRQ12 and implements its own relative pointer policy:
two VGA pixels per horizontal count, three per vertical count. Its main loop
commits complete packets and draws only when independently released gates allow
it. These are application-specific observations, with no DOS mouse driver or
INT33, generic cursor, packet-acceptance or frame-completion contract.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


COMMANDS = {'page': 1, 'page_aba': 2, 'excluded': 3}


def mapped_mouse_probe(directory, nasm):
    """Build a fresh three-byte stream device and an independently gated app.

    The setup retains a polled zero-motion packet separately from the IRQ log.
    Tests verify that precondition; a reset command alone is not assumed to
    erase arbitrary outstanding controller motion. Logs and polling are bounded.
    """
    code = assemble(directory, 'mapped-mouse', r'''
bits 16
org 100h
    nop
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
    ; Explicit black, red and green DAC entries. The application starts at
    ; (100,80); this guest fact is not an API-supplied pointer origin.
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
    mov byte [es:80*320+100],4

    ; Establish protected CR0 and retain independent port-visible values.
    mov dx,3d4h
    mov al,11h
    out dx,al
    inc dx
    in al,dx
    mov ah,al
    or ah,80h
    mov al,11h
    dec dx
    out dx,ax
    call read_configuration
    mov al,[page_read]
    mov [original_page],al
    mov al,[cr0_read]
    mov [original_cr0],al

    xor ax,ax
    mov es,ax
    mov word [es:74h*4],mouse_irq
    mov ax,cs
    mov [es:74h*4+2],ax
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
    mov bl,0ffh
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
    mov bl,0f6h
    call mouse_command
    jc setup_failed
    mov bl,0eah
    call mouse_command
    jc setup_failed
    mov bl,0ebh
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
    mov al,0fbh
    out 21h,al
    mov al,0efh
    out 0a1h,al
    sti
ready:
    nop
main_loop:
    call configuration_command
    cmp byte [commit_gate],0
    je maybe_draw
    mov bx,[application_sequence]
    cmp bx,[mouse_packet_count]
    jae maybe_draw
    cmp bx,32
    jae maybe_draw
    imul bx,bx,3
    mov cl,[mouse_bytes+bx]
    ; Decode the actual PS/2 sign bits, then apply this application's gains.
    xor ax,ax
    mov al,[mouse_bytes+bx+1]
    test cl,10h
    jz positive_x
    sub ax,256
positive_x:
    add ax,ax
    add [pointer_x],ax
    xor ax,ax
    mov al,[mouse_bytes+bx+2]
    test cl,20h
    jz positive_y
    sub ax,256
positive_y:
    imul ax,ax,3
    sub [pointer_y],ax       ; Application coordinates have +y downward.
    inc word [application_sequence]
after_commit:
    nop                     ; Position committed; drawing has not started.
maybe_draw:
    cmp byte [draw_gate],0
    je main_loop
    mov ax,[application_sequence]
    cmp ax,[draw_sequence]
    je main_loop
    ; Out-of-range positions are retained as application state; drawing is
    ; bounded independently instead of treating a relative request as a target.
    cmp word [pointer_x],319
    ja draw_outside
    cmp word [pointer_y],199
    ja draw_outside
    mov ax,0a000h
    mov es,ax
    mov di,[drawn_y]
    imul di,di,320
    add di,[drawn_x]
    mov byte [es:di],0
    mov di,[pointer_y]
    imul di,di,320
    add di,[pointer_x]
    mov byte [es:di],4
    mov ax,[pointer_x]
    mov [drawn_x],ax
    mov ax,[pointer_y]
    mov [drawn_y],ax
    mov ax,[application_sequence]
    mov [draw_sequence],ax
after_draw:
    nop                     ; Both VRAM stores and the draw sequence completed.
    jmp main_loop
draw_outside:
    inc word [outside_draws]
    jmp main_loop

configuration_command:
    mov al,[command]
    test al,al
    jz configuration_done
    mov [last_command],al
    mov byte [command],0
    cmp al,1
    je .page
    cmp al,2
    je .aba
    cmp al,3
    je .excluded
    ret
.page:
    mov dx,3d4h
    mov al,0dh
    mov ah,[original_page]
    xor ah,20h
    out dx,ax
    inc word [configuration_writes]
    jmp .completed
.aba:
    mov dx,3d4h
    mov al,0dh
    mov ah,[original_page]
    xor ah,20h
    out dx,ax
    mov ah,[original_page]
    out dx,ax
    add word [configuration_writes],2
    jmp .completed
.excluded:
    ; A no-op, a protected write and selectors do not change configuration.
    mov dx,3d4h
    mov al,0dh
    mov ah,[original_page]
    out dx,ax
    xor al,al
    mov ah,[original_cr0]
    xor ah,1
    out dx,ax
    mov dx,3c4h
    mov al,7
    out dx,al
    mov dx,3ceh
    mov al,0fh
    out dx,al
    mov dx,3d4h
    mov al,69h
    out dx,al
    mov dx,1ceh
    mov ax,9
    out dx,ax
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,39h
    out dx,al
    mov dx,3dah
    in al,dx
    ; Excluded palette and VRAM changes alter the actual raster independently.
    mov dx,3c8h
    mov al,4
    out dx,al
    inc dx
    xor al,al
    out dx,al
    out dx,al
    mov al,63
    out dx,al
    mov ax,0a000h
    mov es,ax
    mov byte [es:20*320+20],2
.completed:
    call read_configuration
    inc word [commands_completed]
after_configuration:
    nop
    ret
configuration_done:
    ret

read_configuration:
    mov dx,3d4h
    xor al,al
    out dx,al
    inc dx
    in al,dx
    mov [cr0_read],al
    dec dx
    mov al,0dh
    out dx,al
    inc dx
    in al,dx
    mov [page_read],al
    ret

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
    nop                     ; Only the ISR has handled this complete packet.
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
mouse_bytes: times 96 db 0
commit_gate: db 0
draw_gate: db 0
application_sequence: dw 0
draw_sequence: dw 0
pointer_x: dw 100
pointer_y: dw 80
drawn_x: dw 100
drawn_y: dw 80
outside_draws: dw 0
command: db 0
last_command: db 0
commands_completed: dw 0
configuration_writes: dw 0
original_page: db 0
original_cr0: db 0
page_read: db 0
cr0_read: db 0
    db 'MMF1'
    dw ready,main_loop,after_packet,after_commit,after_draw,after_configuration
    dw setup_status,setup_ack,initial_packet,mouse_byte_count,mouse_packet_count
    dw mouse_phase,last_mouse_packet,mouse_bytes,dropped_bytes,commit_gate,draw_gate
    dw application_sequence,draw_sequence,pointer_x,pointer_y,drawn_x,drawn_y,outside_draws
    dw command,last_command,commands_completed,configuration_writes
    dw original_page,original_cr0,page_read,cr0_read
''', nasm)
    names = (
        'ready', 'main_loop', 'after_packet', 'after_commit', 'after_draw', 'after_configuration',
        'setup_status', 'setup_ack', 'initial_packet', 'mouse_byte_count', 'mouse_packet_count',
        'mouse_phase', 'last_mouse_packet', 'mouse_bytes', 'dropped_bytes', 'commit_gate', 'draw_gate',
        'application_sequence', 'draw_sequence', 'pointer_x', 'pointer_y', 'drawn_x', 'drawn_y',
        'outside_draws', 'command', 'last_command', 'commands_completed', 'configuration_writes',
        'original_page', 'original_cr0', 'page_read', 'cr0_read',
    )
    size = 4 + 2 * len(names)
    assert code[-size:-size + 4] == b'MMF1'
    offsets = struct.unpack_from('<' + 'H' * len(names), code, len(code) - size + 4)
    return code, {name + '_ip': offset for name, offset in zip(names, offsets, strict=True)}
