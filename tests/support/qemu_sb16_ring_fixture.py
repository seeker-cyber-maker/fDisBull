"""Authored mutable SB16 auto-init ring; only the guest produces its PCM."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


RING_BYTES = 4096
BLOCK_BYTES = 256
BLOCKS = RING_BYTES // BLOCK_BYTES
RATE = 11025
CHANNELS = 2


def block_pcm(block, generation):
    """Guest producer specification, independently evaluated by the host."""
    if not 0 <= block < BLOCKS or not 0 <= generation <= 0xffff:
        raise ValueError('Invalid authored ring block/generation')
    return bytes((32 + 29 * block + 37 * generation + 17 * i) & 255
                 for i in range(BLOCK_BYTES))


def ring_pcm(generations):
    if len(generations) != BLOCKS:
        raise ValueError('Expected one generation for each ring block')
    return b''.join(block_pcm(i, generation) for i, generation in enumerate(generations))


def sb16_ring(directory, nasm):
    """DSP C6h stereo U8, DMA1 auto-init, and IRQ7 producer refills.

The 4096-byte ring is physically aligned inside an 8192-byte static arena,
so it cannot cross an 8237 64-KiB page. Every 128 stereo frames (256 bytes)
the real guest IRQ handler rewrites the next consumed block with a new
generation. A main busy loop counts work and consumes a physical Q from the
BIOS keyboard ring; it never rewrites audio from a host command.
"""
    names = ('ready', 'started', 'busy', 'failed', 'report', 'report_end',
             'irq_count', 'busy_count', 'produced_bytes', 'stage', 'next_block',
             'refill_active', 'refill_generation', 'buffer_physical',
             'buffer_offset', 'dma_offset', 'dma_page', 'reset_byte', 'major',
             'minor', 'generations', 'arena', 'irq7', 'fill_block')
    text = r'''
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
    xor eax,eax
    mov ax,ds
    shl eax,4
    mov ebp,eax
    add eax,arena+4095
    and eax,0fffff000h
    mov [buffer_physical],eax
    mov [dma_offset],ax
    mov edx,eax
    shr edx,16
    mov [dma_page],dl
    sub eax,ebp
    mov [buffer_offset],ax
    xor bx,bx
initial_fill:
    xor ax,ax
    call fill_block
    inc bx
    cmp bx,16
    jb initial_fill
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
    mov al,2bh
    call dsp_write
    mov al,11h
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
    mov ax,4095
    out 3,al
    mov al,ah
    out 3,al
    mov al,[dma_page]
    out 83h,al
    ; Single memory-to-device mode plus DMA auto-initialize, channel1.
    mov al,59h
    out 0bh,al
    mov al,1
    out 0ah,al
ready:
    nop
    ; Auto-init 8-bit output: 256 channel samples =128 stereo frames per IRQ.
    mov al,0c6h
    call dsp_write
    mov al,20h
    call dsp_write
    mov al,255
    call dsp_write
    xor al,al
    call dsp_write
    mov word [stage],1
started:
    nop
busy:
    nop
    inc dword [busy_count]
    mov bx,[fs:1ah]
    cmp bx,[fs:1ch]
    je busy
    mov ax,[fs:bx]
    add bx,2
    cmp bx,3eh
    jb keyboard_head
    mov bx,1eh
keyboard_head:
    mov [fs:1ah],bx
    cmp al,'q'
    jne busy
    ; Quiesce our actual device before restoring the prior DOS IRQ owner.
    cli
    mov al,5
    out 0ah,al
    mov al,0d0h
    call dsp_write
    mov al,0d3h
    call dsp_write
    mov dx,22eh
    in al,dx
    mov al,20h
    out 20h,al
    xor ax,ax
    mov es,ax
    mov eax,[old_vector]
    mov [es:0fh*4],eax
    mov al,[old_mask]
    out 21h,al
    mov word [stage],2
    sti
    mov ax,4c2ah
    int 21h
failed:
    mov word [stage],0ffffh
    jmp failed

; BX=block, AX=generation. Byte n is
; (32+29*block+37*generation+17*n) mod256.
fill_block:
    mov di,bx
    shl di,8
    add di,[buffer_offset]
    imul ax,ax,37
    mov dx,bx
    imul dx,dx,29
    add ax,dx
    add al,32
    mov cx,256
fill_byte:
    stosb
    add al,17
    loop fill_byte
    ret

irq7:
    pushad
    push ds
    push es
    push cs
    pop ds
    push cs
    pop es
    cld
    mov bx,[next_block]
    lea ax,[bx+1]
    mov [refill_active],ax
    mov si,bx
    shl si,1
    mov ax,[generations+si]
    inc ax
    mov [refill_generation],ax
    call fill_block
    mov ax,[refill_generation]
    mov [generations+si],ax
    mov word [refill_active],0
    inc word [next_block]
    and word [next_block],15
    inc dword [irq_count]
    add dword [produced_bytes],256
    mov dx,22eh
    in al,dx
    mov al,20h
    out 20h,al
    pop es
    pop ds
    popad
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
    db 'SBR1'
irq_count: dd 0
busy_count: dd 0
produced_bytes: dd 0
stage: dw 0
next_block: dw 0
refill_active: dw 0
refill_generation: dw 0
buffer_physical: dd 0
buffer_offset: dw 0
dma_offset: dw 0
dma_page: db 0
reset_byte: db 0
major: db 0
minor: db 0
generations: times 16 dw 0
report_end:
old_vector: dd 0
old_mask: db 0
    align 16,db 0
arena:
    times 8192 db 0
    db 'SBRF'
    dw ready,started,busy,failed,report,report_end
    dw irq_count,busy_count,produced_bytes,stage,next_block
    dw refill_active,refill_generation,buffer_physical
    dw buffer_offset,dma_offset,dma_page,reset_byte,major,minor
    dw generations,arena,irq7,fill_block
'''
    code = assemble(directory, 'sb16-mutable-ring', text, nasm)
    footer = 4 + 2 * len(names)
    if code[-footer:-footer + 4] != b'SBRF':
        raise ValueError('Authored mutable ring footer missing')
    offsets = dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                       len(code) - footer + 4), strict=True))
    offsets['report_size'] = offsets['report_end'] - offsets['report']
    return code, offsets
