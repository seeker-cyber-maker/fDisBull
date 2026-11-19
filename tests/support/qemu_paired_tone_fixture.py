"""Original authored OPL-only / asymmetric stereo SB16 paired-audio guest."""
from __future__ import annotations

import math
import struct

from support.dos_process_fixture import assemble


SOURCE_RATE = 32000
# Source buffer capacity; this is not the DSP command's scalar-sample count.
SOURCE_FRAMES = 4096
DSP_REQUEST_SAMPLES = 4096
REQUESTED_STEREO_FRAMES = DSP_REQUEST_SAMPLES // 2
SOURCE_BYTES = SOURCE_FRAMES * 2
LEFT_PERIOD, RIGHT_PERIOD = 64, 40
LEFT_AMPLITUDE, RIGHT_AMPLITUDE = 32, 12
OPL_FNUM, OPL_BLOCK, OPL_CLOCK = 580, 4, 3579545
LEFT_TABLE = tuple(round(128 + LEFT_AMPLITUDE * math.sin(2 * math.pi * n / LEFT_PERIOD))
                   for n in range(LEFT_PERIOD))
RIGHT_TABLE = tuple(round(128 + RIGHT_AMPLITUDE * math.sin(2 * math.pi * n / RIGHT_PERIOD))
                    for n in range(RIGHT_PERIOD))


def source_stereo():
    return bytes(value for n in range(SOURCE_FRAMES)
                 for value in (LEFT_TABLE[n % LEFT_PERIOD], RIGHT_TABLE[n % RIGHT_PERIOD]))


def expected_frequencies():
    # Yamaha YM3812 application manual3-1-8, multiplier1. This is a pitch
    # expectation, not bit-accurate chip PCM or a fitted emulator waveform.
    return dict(opl=OPL_FNUM * (OPL_CLOCK / 72) * 2 ** (OPL_BLOCK - 1) / 2 ** 19,
                left=SOURCE_RATE / LEFT_PERIOD, right=SOURCE_RATE / RIGHT_PERIOD)


REPORT_FIELDS = (
    ('mode', 1), ('phase', 1), ('reset_byte', 1), ('major', 1), ('minor', 1),
    ('old_mask', 1), ('restored_mask', 1), ('irq_count', 2), ('source_rate', 2),
    ('source_capacity_frames', 2), ('buffer_physical', 4), ('dma_address', 2),
    ('dma_count', 2), ('start_ticks', 4), ('sound_end_ticks', 4),
    ('done_ticks', 4), ('failure', 2),
)
REPORT_SIZE = 4 + sum(width for _, width in REPORT_FIELDS)


def parse_report(data):
    if len(data) != REPORT_SIZE or data[:4] != b'PTN1':
        raise ValueError('Invalid authored paired-tone report')
    offset, report = 4, {}
    for name, width in REPORT_FIELDS:
        report[name] = int.from_bytes(data[offset:offset + width], 'little')
        offset += width
    return report


def paired_tone(directory, nasm):
    """Same COM accepts O or S in its real DOS command tail.

    The common tone_ready NOP is before key-on/DMA dispatch. tone_done follows
    guest completion, a two-BIOS-tick tail, and restoration of the IRQ7 vector
    and mask. Controllers place native breakpoints only at those boundaries.
    No debugger/host writes are used. IRQ0 and the PIT configuration stay intact.
    The buffer holds4096 stereo frames. C0h requests4096 eight-bit channel
    samples (2048 stereo frames per Creative's documented length unit). The
    frozen pre-correction QEMU multiplier is a separately retained historical
    difference; it is not used as the hardware transfer-size oracle.
    """
    labels = ('tone_ready', 'tone_done', 'failed', 'report', 'arena')
    source = r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    push cs
    pop es
    mov ax,40h
    mov fs,ax
    cld
    in al,61h
    and al,0fch
    out 61h,al
    in al,21h
    mov [old_mask],al
    mov [restored_mask],al
    ; The DOS EXEC API preserves a caller-supplied tail exactly. Accept both
    ; its raw O/S form and the shell's conventional leading spaces.
    xor cx,cx
    mov cl,[80h]
    mov si,81h
argument:
    jcxz bad_argument
    lodsb
    dec cx
    cmp al,' '
    je argument
    mov [mode],al
    cmp al,'O'
    je prepare_opl
    cmp al,'S'
    jne bad_argument
    jmp prepare_sb
bad_argument:
    mov word [failure],1
    jmp failed
prepare_opl:
    ; Serial connection, silent modulator, one sine carrier, multiplier1.
    mov ax,2001h
    call opl_write
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
    mov ax,12b0h
    call opl_write
    jmp prepared
prepare_sb:
    mov dx,226h
    mov al,1
    out dx,al
    mov cx,32
reset_delay:
    in al,80h
    loop reset_delay
    xor al,al
    out dx,al
    call dsp_read
    mov [reset_byte],al
    cmp al,0aah
    jne bad_dsp
    mov al,0e1h
    call dsp_write
    call dsp_read
    mov [major],al
    call dsp_read
    mov [minor],al
    cmp byte [major],4
    jne bad_dsp
    ; Align a static8192-byte region within the COM's original allocation.
    xor eax,eax
    mov ax,ds
    shl eax,4
    mov ebp,eax
    add eax,arena+8191
    and eax,0ffffe000h
    mov [buffer_physical],eax
    mov [dma_offset],ax
    mov edx,eax
    shr edx,16
    mov [dma_page],dl
    sub eax,ebp
    mov di,ax
    xor bx,bx
    xor si,si
    mov cx,4096
fill:
    mov al,[left_table+bx]
    stosb
    mov al,[right_table+si]
    stosb
    inc bx
    cmp bx,64
    jb left_ok
    xor bx,bx
left_ok:
    inc si
    cmp si,40
    jb right_ok
    xor si,si
right_ok:
    loop fill
    cli
    xor ax,ax
    mov es,ax
    mov eax,[es:0fh*4]
    mov [old_vector],eax
    mov word [es:0fh*4],irq7
    mov ax,cs
    mov [es:0fh*4+2],ax
    mov al,[old_mask]
    and al,7fh
    out 21h,al
    push cs
    pop es
    sti
    mov al,41h
    call dsp_write
    mov al,7dh
    call dsp_write
    xor al,al
    call dsp_write
    mov al,0d1h
    call dsp_write
    mov al,5
    out 0ah,al
    xor al,al
    out 0ch,al
    mov ax,[dma_offset]
    out 2,al
    mov al,ah
    out 2,al
    xor al,al
    out 0ch,al
    mov ax,8191
    out 3,al
    mov al,ah
    out 3,al
    mov al,[dma_page]
    out 83h,al
    mov al,49h
    out 0bh,al
    mov al,1
    out 0ah,al
    mov word [source_rate],32000
    mov word [source_frames],4096
prepared:
    mov byte [phase],1
tone_ready:
    nop
    mov byte [phase],2
    mov eax,[fs:6ch]
    mov [start_ticks],eax
    cmp byte [mode],'S'
    je start_sb
    mov ax,32b0h
    call opl_write
    mov cx,6
    call wait_ticks
    mov ax,12b0h
    call opl_write
    jmp sound_finished
start_sb:
    mov al,0c0h
    call dsp_write
    mov al,20h
    call dsp_write
    mov al,0ffh
    call dsp_write
    mov al,0fh
    call dsp_write
wait_irq:
    cmp word [irq_count],1
    je dma_finished
    mov eax,[fs:6ch]
    sub eax,[start_ticks]
    cmp eax,18
    jb wait_irq
    mov word [failure],3
    jmp failed
dma_finished:
    ; The single-cycle transfer has cleared DREQ: these final reads are stable.
    xor al,al
    out 0ch,al
    in al,2
    mov ah,al
    in al,2
    xchg al,ah
    mov [dma_address],ax
    xor al,al
    out 0ch,al
    in al,3
    mov ah,al
    in al,3
    xchg al,ah
    mov [dma_count],ax
sound_finished:
    mov eax,[fs:6ch]
    mov [sound_end_ticks],eax
    mov cx,2
    call wait_ticks
    cmp byte [mode],'S'
    jne cleaned
    mov al,0d0h
    call dsp_write
    cli
    xor ax,ax
    mov es,ax
    mov eax,[old_vector]
    mov [es:0fh*4],eax
    mov al,[old_mask]
    out 21h,al
    push cs
    pop es
    sti
cleaned:
    in al,21h
    mov [restored_mask],al
    mov eax,[fs:6ch]
    mov [done_ticks],eax
    mov byte [phase],3
tone_done:
    nop
    mov ax,4c2ah
    int 21h
bad_dsp:
    mov word [failure],2
failed:
    mov byte [phase],0ffh
    jmp failed
wait_ticks:
    mov edx,[fs:6ch]
    movzx ecx,cx
tick_loop:
    mov eax,[fs:6ch]
    sub eax,edx
    cmp eax,ecx
    jb tick_loop
    ret
irq7:
    push ax
    push dx
    push ds
    push cs
    pop ds
    inc word [irq_count]
    mov dx,22eh
    in al,dx
    mov al,20h
    out 20h,al
    pop ds
    pop dx
    pop ax
    iret
dsp_write:
    push ax
    push cx
    push dx
    mov ah,al
    mov dx,22ch
    mov cx,0ffffh
write_wait:
    in al,dx
    test al,80h
    jz write_ready
    loop write_wait
    mov word [failure],4
    jmp failed
write_ready:
    mov al,ah
    out dx,al
    pop dx
    pop cx
    pop ax
    ret
dsp_read:
    push cx
    push dx
    mov dx,22eh
    mov cx,0ffffh
read_wait:
    in al,dx
    test al,80h
    jnz read_ready
    loop read_wait
    mov word [failure],5
    jmp failed
read_ready:
    mov dx,22ah
    in al,dx
    pop dx
    pop cx
    ret
opl_write:
    push ax
    push cx
    push dx
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
    pop ax
    ret
report: db 'PTN1'
mode: db 0
phase: db 0
reset_byte: db 0
major: db 0
minor: db 0
old_mask: db 0
restored_mask: db 0
irq_count: dw 0
source_rate: dw 0
source_frames: dw 0
buffer_physical: dd 0
dma_address: dw 0
dma_count: dw 0
start_ticks: dd 0
sound_end_ticks: dd 0
done_ticks: dd 0
failure: dw 0
report_end:
old_vector: dd 0
dma_offset: dw 0
dma_page: db 0
left_table: db LEFT_TABLE
right_table: db RIGHT_TABLE
arena: times 16384 db 0
offset_table:
    dw tone_ready,tone_done,failed,report,arena
'''.replace('LEFT_TABLE', ','.join(map(str, LEFT_TABLE))).replace('RIGHT_TABLE', ','.join(map(str, RIGHT_TABLE)))
    code = assemble(directory, 'paired-tone', source, nasm)
    if len(code) >= 0xff00:
        raise ValueError('Authored paired-tone COM exceeds its source-owned allocation')
    offsets = dict(zip(labels, struct.unpack('<5H', code[-10:])))
    offsets['report_size'] = REPORT_SIZE
    return code, offsets
