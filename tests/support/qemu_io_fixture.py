"""Small authored guests for independent input, clock and display witnesses.

These programs record what the guest actually consumed. They contain no QMP,
debugger or event-search code, and their draw boundaries are deliberately
separate from input consumption. Source, listing and binaries are assembled in
the caller's private directory; no DOS or vendor payload belongs in this file.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


def _symbols(code, names):
    size = 4 + 2 * len(names)
    if code[-size:-size + 4] != b"IOW1":
        raise ValueError("Authored input witness symbol footer is missing")
    return dict(zip(names, struct.unpack_from("<" + "H" * len(names), code,
                                               len(code) - size + 4), strict=True))


_PALETTE = r"""
    mov ax,13h
    int 10h
    ; Define exact RGB values instead of depending on a firmware palette.
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    mov si,palette
    mov cx,12
palette_loop:
    lodsb
    out dx,al
    loop palette_loop
"""


def bios_keyboard_display(directory, nasm):
    """COM: INT 16h consumption, BIOS ticks, then a separately stopped draw.

    The first consumed key colors pixel (10, 10) red; the second colors it
    green. VGA mode 13h may be presented by QEMU as a doubled 640x400 surface.
    All returned ``*_ip`` values are COM offsets, including its 0x100 origin.
    """
    code = assemble(directory, "bios-keyboard-display", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    cld
""" + _PALETTE + r"""
    mov ax,40h
    mov es,ax
    mov eax,[es:6ch]
    mov [ready_ticks],eax
ready:
    nop
    mov eax,[es:6ch]
    mov [last_ticks],eax
    inc dword [loop_count]
    mov ah,1
    int 16h
    jz ready
    xor ah,ah
    int 16h
    mov [last_key],ax
    inc word [key_count]
    mov eax,[es:6ch]
    mov [consumed_ticks],eax
before_draw:
    nop
    push es
    mov ax,0a000h
    mov es,ax
    mov al,[key_count]
    and al,3
    mov [es:3210],al
    pop es
    inc word [draw_count]
after_draw:
    nop
    jmp ready
palette:
    db 0,0,0, 63,0,0, 0,63,0, 0,0,63
report:
    db 'BIOS'
key_count: dw 0
draw_count: dw 0
last_key: dw 0
ready_ticks: dd 0
last_ticks: dd 0
consumed_ticks: dd 0
loop_count: dd 0
report_end:
    db 'IOW1'
    dw ready,before_draw,after_draw,report,report_end
    dw key_count,draw_count,last_key,ready_ticks,last_ticks,consumed_ticks,loop_count
""", nasm)
    symbols = _symbols(code, ("ready_ip", "before_draw_ip", "after_draw_ip",
        "report_ip", "report_end_ip", "key_count_ip", "draw_count_ip",
        "last_key_ip", "ready_ticks_ip", "last_ticks_ip", "consumed_ticks_ip",
        "loop_count_ip"))
    symbols["report_size"] = symbols["report_end_ip"] - symbols["report_ip"]
    return code, symbols


def raw_keyboard_mouse(directory, nasm):
    """COM: own IRQ1/IRQ12 logs prove PS/2 make/break and mouse packets.

    This private witness installs guest handlers and enables the PS/2 mouse
    directly. It needs no DOS mouse driver. The main loop colors (10, 10)
    red for a keyboard make, blue for a break, and (20, 10) green while the
    most recently consumed mouse packet has its left-button bit set.

    Setup polling and log writes are bounded. ``setup_status`` is 1 on
    success, 0xffff on a controller/ACK failure. The owner must terminate
    this private VM after inspection; this fixture does not exit to DOS.
    """
    code = assemble(directory, "raw-keyboard-mouse", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    cld
""" + _PALETTE + r"""
    cli
    xor ax,ax
    mov es,ax
    mov word [es:9*4],keyboard_irq
    mov ax,cs
    mov [es:9*4+2],ax
    mov word [es:74h*4],mouse_irq
    mov [es:74h*4+2],ax
    ; Enable the auxiliary port, then retain the existing controller mode
    ; while enabling both IRQ lines and clearing both clock-disable bits.
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
    or al,3
    and al,0cfh
    mov [controller_mode],al
    call writable
    jc setup_failed
    mov al,60h
    out 64h,al
    call writable
    jc setup_failed
    mov al,[controller_mode]
    out 60h,al
    mov bl,0f6h
    call mouse_command
    jc setup_failed
    mov bl,0f4h
    call mouse_command
    jc setup_failed
    in al,21h
    and al,0f9h
    out 21h,al
    in al,0a1h
    and al,0efh
    out 0a1h,al
    mov word [setup_status],1
    jmp setup_done
setup_failed:
    mov word [setup_status],0ffffh
setup_done:
    mov ax,40h
    mov es,ax
    mov eax,[es:6ch]
    mov [ready_ticks],eax
    sti
ready:
    nop
    mov eax,[es:6ch]
    mov [last_ticks],eax
    inc dword [loop_count]
before_draw:
    nop
    push es
    mov ax,0a000h
    mov es,ax
    xor al,al
    cmp word [keyboard_count],0
    je draw_key
    mov al,1
    test byte [last_key],80h
    jz draw_key
    mov al,3
draw_key:
    mov [es:3210],al
    xor al,al
    test byte [last_mouse_packet],1
    jz draw_mouse
    mov al,2
draw_mouse:
    mov [es:3220],al
    pop es
after_draw:
    nop
    jmp ready

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
mouse_command:
    call writable
    jc .done
    mov al,0d4h
    out 64h,al
    call writable
    jc .done
    mov al,bl
    out 60h,al
    call readable
    jc .done
    in al,60h
    mov [setup_ack],al
    cmp al,0fah
    je .ok
    stc
    ret
.ok:
    clc
.done:
    ret

keyboard_irq:
    push ax
    push bx
    push ds
    push cs
    pop ds
    in al,64h
    test al,1
    jz .eoi
    test al,20h
    jnz .eoi
    in al,60h
    mov [last_key],al
    mov bx,[keyboard_count]
    cmp bx,64
    jae .full
    mov [keyboard_bytes+bx],al
.full:
    inc word [keyboard_count]
.eoi:
    mov al,20h
    out 20h,al
    pop ds
    pop bx
    pop ax
    iret
mouse_irq:
    push ax
    push bx
    push ds
    push cs
    pop ds
    in al,64h
    test al,1
    jz .eoi
    test al,20h
    jz .eoi
    in al,60h
    mov bx,[mouse_byte_count]
    cmp bx,96
    jae .full
    mov [mouse_bytes+bx],al
.full:
    inc word [mouse_byte_count]
    xor bx,bx
    mov bl,[mouse_phase]
    mov [last_mouse_packet+bx],al
    inc bl
    cmp bl,3
    jb .partial
    inc word [mouse_packet_count]
    xor bl,bl
.partial:
    mov [mouse_phase],bl
.eoi:
    mov al,20h
    out 0a0h,al
    out 20h,al
    pop ds
    pop bx
    pop ax
    iret

palette:
    db 0,0,0, 63,0,0, 0,63,0, 0,0,63
controller_mode: db 0
report:
    db 'PS2!'
setup_status: dw 0
keyboard_count: dw 0
mouse_byte_count: dw 0
mouse_packet_count: dw 0
last_key: db 0
mouse_phase: db 0
last_mouse_packet: db 0,0,0
setup_ack: db 0
ready_ticks: dd 0
last_ticks: dd 0
loop_count: dd 0
keyboard_bytes: times 64 db 0
mouse_bytes: times 96 db 0
report_end:
    db 'IOW1'
    dw ready,before_draw,after_draw,report,report_end,setup_status
    dw keyboard_count,mouse_byte_count,mouse_packet_count,last_key
    dw mouse_phase,last_mouse_packet,setup_ack,ready_ticks,last_ticks,loop_count
    dw keyboard_bytes,mouse_bytes
""", nasm)
    symbols = _symbols(code, ("ready_ip", "before_draw_ip", "after_draw_ip",
        "report_ip", "report_end_ip", "setup_status_ip", "keyboard_count_ip",
        "mouse_byte_count_ip", "mouse_packet_count_ip", "last_key_ip",
        "mouse_phase_ip", "last_mouse_packet_ip", "setup_ack_ip",
        "ready_ticks_ip", "last_ticks_ip", "loop_count_ip",
        "keyboard_bytes_ip", "mouse_bytes_ip"))
    symbols["report_size"] = symbols["report_end_ip"] - symbols["report_ip"]
    return code, symbols
