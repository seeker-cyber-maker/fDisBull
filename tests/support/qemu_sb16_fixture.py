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


def linear_pcm(rate):
    """Analytic equal-rate/4x linear waveform, before output quantization.

The 4x interpolator requires a following source sample. Its complete output
therefore contains four samples per adjacent input pair. Native integer mixer
quantization is checked separately with a one-U8-unit tolerance, never a
fitted amplitude/frequency or an arbitrary source-stream offset.
"""
    source = source_pcm()
    if rate == OUTPUT_RATE:
        return source
    if rate != 8000:
        raise ValueError('Authored waveform oracle supports only 8000 and 32000 Hz')
    return bytes(((4 - phase) * left + phase * right) // 4
                 for left, right in zip(source, source[1:]) for phase in range(4))


def sb16_pcm(directory, nasm, *, rate=8000, silence=False):
    """COM uses DSP C0h, unsigned mono DMA1/IRQ7, or DSP80h's timer.

An arena twice the transfer size provides an 8192-byte physically aligned
buffer inside the original COM allocation. That alignment cannot cross an
8237 64-KiB DMA page. No DOS allocation/shrink or host guest-state writes are
needed. IRQ7 is acknowledged through the 8-bit DSP status port and the PIC.
The program continuously records DMA1 registers, and exits only on a physical
Q key after the observed IRQ. DSP80h is an IRQ delay, not generated PCM silence.
"""
    if rate not in (8000, OUTPUT_RATE) or type(silence) is not bool or silence and rate != 8000:
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
    start = r'''
    mov al,0c0h
    call dsp_write
    xor al,al
    call dsp_write
    mov al,0ffh
    call dsp_write
    mov al,1fh
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
    cmp word [irq_count],0
    je inflight
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
    code = assemble(directory, 'sb16-' + ('silence' if silence else str(rate)), text, nasm)
    footer = 4 + 2 * len(names)
    if code[-footer:-footer + 4] != b'SBF1':
        raise ValueError('Authored SB16 fixture footer is missing')
    symbols = dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                                                len(code) - footer + 4), strict=True))
    symbols.update(report_size=symbols['report_end'] - symbols['report'], dma_bytes=DMA_BYTES,
                   rate=rate, silence=silence)
    return code, symbols
