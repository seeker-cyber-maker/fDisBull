"""Authored YM3812 note/gates and combined OPL/SB16 checkpoint frontier."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from support.qemu_sb16_ring_fixture import sb16_ring


OPL_CLOCK = 3579545
OPL_FNUM = 580
OPL_BLOCK = 4
PENDING_ADDRESS = 4


def note_frequency(block=OPL_BLOCK):
    """Yamaha YM3812 application manual, section3-1-8, multiplier1.

https://www.xentax.org/images/LSI-2438124-Yamaha-YM3812-OPL2-Application-Manual.pdf
This gives an independent pitch expectation, not bit-exact hardware PCM.
"""
    return OPL_FNUM * (OPL_CLOCK / 72) * 2 ** (block - 1) / 2 ** 19


def opl_program(directory, nasm):
    """Compose the existing authored mutable-ring guest with FM guest I/O.

Initially only the FM note plays. Physical2 selects its octave, K keys it
off, and C selects slow attack/LFO plus rhythm noise and starts SB16 DMA.
PhysicalP parks immediately after arming both legacy AdLib timers, with
register04 selected. The next instruction sequence writes DATA-only00,
observes both forced-expiry flags, clears them and resumes the busy loop.
All audio, register and keyboard operations are performed by the guest.
"""
    _, base_offsets = sb16_ring(directory, nasm)
    source = (directory / 'sb16-mutable-ring.asm').read_text()
    marker = 'ready:\n    nop\n'
    if source.count(marker) != 1:
        raise ValueError('Authored ring ready frontier changed')
    source = source.replace(marker, r'''
    call opl_init_tone
    mov word [opl_stage],1
opl_tone_loop:
    nop
    inc dword [busy_count]
    call opl_keyboard
    cmp al,'2'
    je opl_octave
    cmp al,'k'
    je opl_keyoff
    cmp al,'c'
    je opl_combined
    cmp al,'q'
    je ring_shutdown
    jmp opl_tone_loop
opl_octave:
    mov ax,36b0h
    call opl_write
    mov word [opl_stage],2
    jmp opl_tone_loop
opl_keyoff:
    mov ax,16b0h
    call opl_write
    mov word [opl_stage],3
    jmp opl_tone_loop
opl_combined:
    call opl_complex
    mov word [opl_stage],4
ready:
    nop
''')
    marker = "    cmp al,'q'\n    jne busy\n"
    if source.count(marker) != 1:
        raise ValueError('Authored ring keyboard frontier changed')
    source = source.replace(marker, "    cmp al,'p'\n    je opl_prepare_checkpoint\n" + marker +
                            'ring_shutdown:\n    call opl_quiet\n')
    marker = 'report:\n'
    if source.count(marker) != 1:
        raise ValueError('Authored ring report frontier changed')
    additions = r'''
; AX contains data in AH and register index in AL. The conservative delay
; reads port80, not the OPL status port: it cannot expire an armed timer.
opl_write:
    push ax
    push bx
    push cx
    push dx
    xor bx,bx
    mov bl,al
    mov [opl_registers+bx],ah
    mov dx,388h
    out dx,al
    mov dx,80h
    mov cx,64
opl_address_delay:
    in al,dx
    loop opl_address_delay
    mov dx,389h
    mov al,ah
    out dx,al
    mov dx,80h
    mov cx,128
opl_data_delay:
    in al,dx
    loop opl_data_delay
    pop dx
    pop cx
    pop bx
    pop ax
    ret
opl_status:
    push dx
    mov dx,388h
    in al,dx
    pop dx
    ret
opl_keyboard:
    mov bx,[fs:1ah]
    cmp bx,[fs:1ch]
    je opl_no_key
    mov ax,[fs:bx]
    add bx,2
    cmp bx,3eh
    jb opl_head
    mov bx,1eh
opl_head:
    mov [fs:1ah],bx
    ret
opl_no_key:
    xor al,al
    ret
opl_init_tone:
    ; Explicitly clear the entire DATA image, including reserved addresses,
    ; so the guest shadow has a complete independent initial identity.
    xor bx,bx
opl_clear:
    xor ax,ax
    mov al,bl
    call opl_write
    inc bl
    jnz opl_clear
    ; Legacy QEMU timer/status contract: each armed timer expires on the
    ; NEXT actual OPL port access. This is not an elapsed-time oracle.
    mov ax,8004h
    call opl_write
    mov ax,0fe02h
    call opl_write
    mov ax,0104h
    call opl_write
    call opl_status
    mov [opl_timer1_status],al
    mov ax,0004h
    call opl_write
    mov ax,8004h
    call opl_write
    mov ax,0fe03h
    call opl_write
    mov ax,0204h
    call opl_write
    call opl_status
    mov [opl_timer2_status],al
    mov ax,0004h
    call opl_write
    mov ax,8004h
    call opl_write
    call opl_status
    mov [opl_timer_reset_status],al
    ; Channel0 serial connection, silent modulator (AR0), one sine carrier,
    ; multiplier1, fast attack/constant sustain, no feedback/AM/vibrato.
    mov ax,0120h
    call opl_write
    mov ax,2123h
    call opl_write
    mov ax,3f40h
    call opl_write
    mov ax,1843h
    call opl_write
    mov ax,0060h
    call opl_write
    mov ax,0f063h
    call opl_write
    mov ax,0080h
    call opl_write
    mov ax,0f83h
    call opl_write
    mov ax,00c0h
    call opl_write
    mov ax,44a0h
    call opl_write
    mov ax,32b0h
    call opl_write
    ret
opl_complex:
    ; Keep channel0 in a slow attack while its AM/vibrato oscillators move.
    mov ax,12b0h
    call opl_write
    mov ax,0e123h
    call opl_write
    mov ax,4463h
    call opl_write
    mov ax,4483h
    call opl_write
    mov ax,32b0h
    call opl_write
    ; Program the six operators used by the five rhythm instruments.
    xor bx,bx
opl_rhythm_ops:
    mov al,[opl_rhythm_slots+bx]
    add al,20h
    mov ah,0e1h
    call opl_write
    add al,20h
    mov ah,18h
    call opl_write
    add al,20h
    mov ah,0f3h
    call opl_write
    add al,20h
    mov ah,46h
    call opl_write
    inc bx
    cmp bx,6
    jb opl_rhythm_ops
    mov ax,98a6h
    call opl_write
    mov ax,11b6h
    call opl_write
    mov ax,54a7h
    call opl_write
    mov ax,11b7h
    call opl_write
    mov ax,74a8h
    call opl_write
    mov ax,12b8h
    call opl_write
    mov ax,0ffbdh
    call opl_write
    ret
opl_prepare_checkpoint:
    mov word [opl_stage],5
    mov ax,8004h
    call opl_write
    mov ax,0fe02h
    call opl_write
    mov ax,0fe03h
    call opl_write
    mov ax,0304h
    call opl_write
opl_pending_data:
    nop
    ; No ADDRESS write here: restored register04 selection is necessary.
    mov dx,389h
    xor al,al
    out dx,al
    mov byte [opl_registers+4],0
    call opl_status
    mov [opl_resume_status],al
    mov ax,8004h
    call opl_write
    call opl_status
    mov [opl_resume_reset_status],al
    mov word [opl_stage],6
    jmp busy
opl_quiet:
    xor bx,bx
opl_quiet_channel:
    xor ax,ax
    mov al,bl
    add al,0b0h
    call opl_write
    inc bx
    cmp bx,9
    jb opl_quiet_channel
    mov ax,00bdh
    call opl_write
    mov ax,0004h
    call opl_write
    mov ax,8004h
    call opl_write
    ret
opl_rhythm_slots: db 10h,13h,11h,14h,12h,15h
opl_report:
    db 'OPL1'
opl_stage: dw 0
opl_timer1_status: db 0
opl_timer2_status: db 0
opl_timer_reset_status: db 0
opl_resume_status: db 0
opl_resume_reset_status: db 0
opl_registers: times 256 db 0
opl_report_end:
'''
    source = source.replace(marker, additions + '\n' + marker)
    names = [name for name in base_offsets if name != 'report_size'] + [
        'opl_tone_loop', 'opl_pending_data', 'opl_report', 'opl_report_end',
        'opl_stage', 'opl_timer1_status', 'opl_timer2_status', 'opl_timer_reset_status',
        'opl_resume_status', 'opl_resume_reset_status', 'opl_registers']
    source += "\n    db 'OPLF'\n    dw " + ','.join(names) + '\n'
    code = assemble(directory, 'opl-combined', source, nasm)
    footer = 4 + 2 * len(names)
    if code[-footer:-footer + 4] != b'OPLF':
        raise ValueError('Authored OPL fixture footer missing')
    offsets = dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                       len(code) - footer + 4), strict=True))
    offsets['report_size'] = offsets['report_end'] - offsets['report']
    offsets['opl_report_size'] = offsets['opl_report_end'] - offsets['opl_report']
    return code, offsets
