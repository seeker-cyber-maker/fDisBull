"""Authored SB16 DSP/DMA/IRQ consumer; no device or debugger mock in the guest."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


DMA_BYTES = 8192
OUTPUT_RATE = 32000
SILENCE_SAMPLES = 800


def source_pcm(length=DMA_BYTES):
    """Specified nonconstant, bounded unsigned waveform, independent of QEMU."""
    return bytes(32 + ((37 * n + 17 * (n >> 5)) % 192) for n in range(length))


def linear_pcm(rate, *, channels=1):
    """Independent expected output of the pinned foreign QEMU mono capture.

QEMU 10.0.13 mixeng_template duplicates mono into L/R and sums them on mono
capture; stereo source bytes instead supply distinct interleaved L/R channels.
Its integer unsigned centre is 127, with native threshold/cast rules
even at negative full scale. rate_template weights by UINT_MAX-t, not 2**32-t.
These laws describe the unmodified upstream mixer, not our checkpoint codec;
gain, rate, source offset and clipping behavior are never fitted to capture.
The 4x interpolator needs a following source sample: four outputs per pair.
"""
    if type(channels) is not int or channels not in (1, 2):
        raise ValueError('Authored waveform supports mono or interleaved stereo')
    source = source_pcm()
    frames = [(value, value) for value in source] if channels == 1 else list(zip(source[::2], source[1::2]))
    def clip(left, right):
        value = left + right
        if value >= 0x7fffffff:
            return 255
        if value < -(1 << 31):
            return 0
        return ((value >> 24) + 127) & 255
    if rate == OUTPUT_RATE:
        return bytes(clip((left - 127) << 24, (right - 127) << 24) for left, right in frames)
    if rate != 8000:
        raise ValueError('Authored waveform oracle supports only 8000 and 32000 Hz')
    def interpolate(first, second, phase):
        first, second = (first - 127) << 24, (second - 127) << 24
        fraction = phase << 30
        return (first * (0xffffffff - fraction) + second * fraction) >> 32
    return bytes(clip(interpolate(first[0], second[0], phase),
                      interpolate(first[1], second[1], phase))
                 for first, second in zip(frames, frames[1:]) for phase in range(4))


def sb16_pcm(directory, nasm, *, rate=8000, silence=False, channels=1,
             guest_dma_service=False):
    """COM uses DSP C0h, unsigned mono/stereo DMA1/IRQ7, or DSP80h's timer.

An arena twice the transfer size provides an 8192-byte physically aligned
buffer inside the original COM allocation. That alignment cannot cross an
8237 64-KiB DMA page. No DOS allocation/shrink or host guest-state writes are
needed. IRQ7 is acknowledged through the 8-bit DSP status port and the PIC.
The program continuously records DMA1 registers, and exits only on a physical
Q key after the observed IRQ. DSP80h is an IRQ delay, not generated PCM silence.
The opt-in guest DMA service is only for the draining-frontier witness: an
ordinary channel-unmask port write queues PCM between audio callbacks.
"""
    if (rate not in (8000, OUTPUT_RATE) or type(silence) is not bool
            or type(channels) is not int or channels not in (1, 2)
            or type(guest_dma_service) is not bool
            or silence and (rate != 8000 or channels != 1 or guest_dma_service)):
        raise ValueError('Unsupported authored SB16 profile')
    names = ('ready', 'started', 'inflight', 'finished', 'failed', 'report', 'report_end',
             'reset_byte', 'major', 'minor', 'irq_count', 'stage', 'dma_offset', 'dma_page',
             'dma_address', 'dma_count', 'buffer_offset', 'buffer_physical', 'arena')
    setup = r'''
    ; Mask channel1, reset its flip-flop, program address/count/page, then use
    ; single memory-to-device transfer mode (49h) and unmask channel1.
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
''' if not silence else ''
    mode = '    xor al,al\n' if channels == 1 else '    mov al,20h\n'
    length = DMA_BYTES // channels - 1
    start = r'''
    mov al,0c0h
    call dsp_write
''' + mode + r'''
    call dsp_write
    mov al,''' + str(length & 255) + r'''
    call dsp_write
    mov al,''' + str(length >> 8) + r'''
    call dsp_write
''' if not silence else r'''
    mov al,80h
    call dsp_write
    mov al,1fh
    call dsp_write
    mov al,3
    call dsp_write
'''
    text = r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    push cs
    pop es
    cld
    ; Silence the PC speaker so only the explicitly selected SB16 graph is
    ; relevant. These are ordinary guest I/O operations.
    in al,61h
    and al,0fch
    out 61h,al
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
    jne failed
    mov al,0e1h
    call dsp_write
    call dsp_read
    mov [major],al
    call dsp_read
    mov [minor],al
    cmp byte [major],4
    jne failed
    cmp byte [minor],5
    jne failed
    ; Select an 8192-aligned physical region from our static COM arena.
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
    mov [buffer_offset],ax
    mov di,ax
    xor bx,bx
fill:
    movzx eax,bx
    imul eax,37
    movzx edx,bx
    shr edx,5
    imul edx,17
    add eax,edx
    xor edx,edx
    mov ebp,192
    div ebp
    lea eax,[edx+32]
    stosb
    inc bx
    cmp bx,8192
    jb fill
    ; Own the genuine guest IRQ7 vector, keeping the original for DOS exit.
    cli
    xor ax,ax
    mov es,ax
    mov eax,[es:0fh*4]
    mov [old_vector],eax
    mov word [es:0fh*4],irq7
    mov ax,cs
    mov [es:0fh*4+2],ax
    in al,21h
    mov [old_mask],al
    and al,7fh
    out 21h,al
    push cs
    pop es
    sti
    mov al,41h
    call dsp_write
    mov al,''' + str(rate >> 8) + r'''
    call dsp_write
    mov al,''' + str(rate & 255) + r'''
    call dsp_write
    mov al,0d1h
    call dsp_write
''' + setup + r'''
ready:
    nop
''' + start + r'''
    mov word [stage],1
started:
    nop
inflight:
    nop
    call sample_dma
''' + (r'''
    ; The sampled controller count is remaining bytes minus one. Queue only
    ; the final <=80-byte remainder between callbacks; do not busy-service
    ; the entire stream. The normal guest-I/O path honors available credit.
    cmp word [dma_count],80
    jae guest_service_done
    mov al,1
    out 0ah,al
guest_service_done:
''' if guest_dma_service else '') + r'''
    cmp word [irq_count],0
    je inflight
    ; The ISR proves the single transfer completed. Sample once more while
    ; DREQ is cleared: active two-byte counter reads may straddle completion.
    call sample_dma
    mov word [stage],2
finished:
    nop
    mov ah,1
    int 16h
    jz finished
    xor ah,ah
    int 16h
    cmp al,'q'
    jne finished
    mov al,0d0h
    call dsp_write
    cli
    xor ax,ax
    mov es,ax
    mov eax,[old_vector]
    mov [es:0fh*4],eax
    mov al,[old_mask]
    out 21h,al
    sti
    mov ax,4c2ah
    int 21h
failed:
    mov word [stage],0ffffh
    jmp failed
sample_dma:
    push ax
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
    pop ax
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
    jmp failed
read_ready:
    mov dx,22ah
    in al,dx
    pop dx
    pop cx
    ret
report:
    db 'SBD1'
reset_byte: db 0
major: db 0
minor: db 0
old_mask: db 0
old_vector: dd 0
irq_count: dw 0
stage: dw 0
dma_offset: dw 0
dma_page: db 0
    db 0
dma_address: dw 0
dma_count: dw 0
buffer_offset: dw 0
buffer_physical: dd 0
report_end:
    align 16,db 0
arena:
    times 16384 db 0
    db 'SBF1'
    dw ready,started,inflight,finished,failed,report,report_end
    dw reset_byte,major,minor,irq_count,stage,dma_offset,dma_page
    dw dma_address,dma_count,buffer_offset,buffer_physical,arena
'''
    name = 'silence' if silence else str(rate) + ('-stereo' if channels == 2 else '')
    code = assemble(directory, 'sb16-' + name, text, nasm)
    footer = 4 + 2 * len(names)
    if code[-footer:-footer + 4] != b'SBF1':
        raise ValueError('Authored SB16 fixture footer is missing')
    symbols = dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                                                len(code) - footer + 4), strict=True))
    symbols.update(report_size=symbols['report_end'] - symbols['report'], dma_bytes=DMA_BYTES,
                   rate=rate, silence=silence, channels=channels)
    return code, symbols
