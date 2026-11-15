"""Authored VGA port operations with explicit, independently observed fences.

The guest records its timing registers and status-port reads. It does not read
host clocks, infer renderer completion, or wait for a guest application frame.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


RAW_FIELDS = ('msr', 'sr1', 'cr00', 'cr04', 'cr05', 'cr06', 'cr07',
              'cr10', 'cr11', 'vbe-enable')


def retrace_ports(directory, nasm):
    code = assemble(directory, 'retrace-ports', r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    call snapshot_timing
    mov al,[timing_raw+7]
    mov [original_cr10],al
ready:
    nop
dispatch:
    mov al,[command]
    cmp al,1
    je status_loop
    cmp al,2
    je attribute_probe
    cmp al,3
    je change_cr10
    cmp al,4
    je restore_cr10
    cmp al,5
    je aba_cr10
    cmp al,6
    je enable_vbe
    cmp al,7
    je disable_vbe
    cmp al,8
    je reenter_mode13
    cmp al,9
    je noop_cr10
    cmp al,10
    je invalid_cr10
    jmp dispatch

status_loop:
    mov dx,3dah
sample_status:
    in al,dx
    mov [sampled_status],al
status_done:
    nop
    cmp byte [command],1
    je sample_status
    jmp dispatch

attribute_probe:
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    mov al,32h                 ; index 12h, keep display-enable bit set
    out dx,al
    xor al,al
    out dx,al                  ; own the old plane-enable value: zero
    mov al,32h
    out dx,al                  ; leave attribute controller awaiting data
attribute_pending:
    nop
    mov al,0fh
    out dx,al
    mov al,32h
    out dx,al
    inc dx
    in al,dx
    mov [attribute_result],al
    mov dx,3dah
    in al,dx                   ; restore index phase after the witness
    mov byte [command],0
attribute_done:
    nop
    jmp dispatch

change_cr10:
    mov al,[original_cr10]
    xor al,4
    call write_cr10
    call snapshot_timing
    mov byte [command],0
cr10_changed:
    nop
    jmp dispatch

restore_cr10:
    mov al,[original_cr10]
    call write_cr10
    call snapshot_timing
    mov byte [command],0
cr10_restored:
    nop
    jmp dispatch

aba_cr10:
    mov al,[original_cr10]
    xor al,4
    call write_cr10
    mov al,[original_cr10]
    call write_cr10
    call snapshot_timing
    mov byte [command],0
cr10_aba_done:
    nop
    jmp dispatch

noop_cr10:
    mov al,[original_cr10]
    call write_cr10
    call snapshot_timing
    mov byte [command],0
cr10_noop_done:
    nop
    jmp dispatch

invalid_cr10:
    mov al,0ffh                ; beyond the mode-13 vertical total
    call write_cr10
    call snapshot_timing
    mov byte [command],0
cr10_invalid_done:
    nop
    jmp dispatch

%macro write_vbe 2
    mov dx,1ceh
    mov ax,%1
    out dx,ax
    inc dx
    mov ax,%2
    out dx,ax
%endmacro

enable_vbe:
    write_vbe 1,320
    write_vbe 2,200
    write_vbe 3,8
    write_vbe 4,81h            ; enable, preserve VRAM
    call snapshot_timing
    mov byte [command],0
vbe_enabled:
    nop
    jmp dispatch

disable_vbe:
    write_vbe 4,0
    call snapshot_timing
    mov byte [command],0
vbe_disabled:
    nop
    jmp dispatch

reenter_mode13:
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    call snapshot_timing
    mov byte [command],0
mode13_reentered:
    nop
    jmp dispatch

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
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    ret

crtc_indices: db 0,4,5,6,7,10h,11h
command: db 0
sampled_status: db 0
attribute_result: db 0
original_cr10: db 0
timing_raw: times 11 db 0
    db 'RTR1'
    dw ready,dispatch,sample_status,status_done,attribute_pending,attribute_done
    dw cr10_changed,cr10_restored,cr10_aba_done,cr10_noop_done,cr10_invalid_done
    dw vbe_enabled,vbe_disabled,mode13_reentered
    dw command,sampled_status,attribute_result,timing_raw
''', nasm)
    names = ('ready_ip', 'dispatch_ip', 'sample_status_ip', 'status_done_ip',
             'attribute_pending_ip', 'attribute_done_ip', 'cr10_changed_ip',
             'cr10_restored_ip', 'cr10_aba_done_ip', 'cr10_noop_done_ip',
             'cr10_invalid_done_ip', 'vbe_enabled_ip', 'vbe_disabled_ip',
             'mode13_reentered_ip', 'command_ip', 'sampled_status_ip',
             'attribute_result_ip', 'timing_raw_ip')
    size = 4 + 2 * len(names)
    assert code[-size:-size + 4] == b'RTR1'
    offsets = struct.unpack('<' + 'H' * len(names), code[-2 * len(names):])
    return code, dict(zip(names, offsets, strict=True))


def guest_timing(raw_bytes):
    """Decode independently guest-read registers; SR1 is port-visible SR1.

    The native model uses an internal effective SR1 while VBE is enabled.
    Therefore this guest dump is a model oracle only in legacy VGA mode.
    """
    return dict(zip(RAW_FIELDS, struct.unpack('<9BH', raw_bytes), strict=True))


def precise_timing(raw):
    """QEMU 10.0.13 integer model, not a physical VGA timing specification."""
    dot_hz = (25_175_000, 28_322_000, 25_175_000, 25_175_000)[(raw['msr'] >> 2) & 3]
    dots = 8 if raw['msr'] & 1 else 9
    ticks = 1_000_000_000 // (dot_hz // dots)
    horizontal = (raw['cr00'] + 5) << ((raw['sr1'] >> 3) & 1)
    vertical = (raw['cr06'] | (((raw['cr07'] & 1) | ((raw['cr07'] >> 4) & 2)) << 8)) + 2
    hstart = raw['cr04'] + ((raw['cr05'] >> 5) & 3)
    vstart = raw['cr10'] | ((((raw['cr07'] >> 2) & 1) | ((raw['cr07'] >> 6) & 2)) << 8)
    return {'ticks-per-char': ticks, 'total-chars': horizontal * vertical,
            'htotal': horizontal, 'hstart': hstart, 'hend': hstart + (raw['cr05'] & 31) + 1,
            'vstart': vstart, 'vend': vstart + (raw['cr11'] & 15) + 1, 'freq': 0}


def precise_phase(timing, virtual_ns):
    period = timing['ticks-per-char'] * timing['total-chars']
    phase = virtual_ns % period
    character = phase // timing['ticks-per-char']
    line, column = divmod(character, timing['htotal'])
    vertical = timing['vstart'] <= line <= timing['vend']
    horizontal = timing['hstart'] <= column <= timing['hend']
    return {'period-ns': period, 'phase-ns': phase, 'character': character,
            'line': line, 'line-character': column, 'vertical-retrace': vertical,
            'horizontal-retrace': horizontal,
            'status1-timing-bits': (8 if vertical else 0) | (1 if vertical or horizontal else 0)}
