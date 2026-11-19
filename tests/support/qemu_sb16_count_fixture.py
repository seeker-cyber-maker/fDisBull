"""Finite authored Bx/Cx output count oracle; DMA capacity exceeds both models."""
from __future__ import annotations

from support.dos_process_fixture import assemble

SAMPLES = 1024
DMA_UNITS = 4096
FIELDS = (
    ('bits', 1), ('channels', 1), ('fifo', 1), ('phase', 1),
    ('reset_byte', 1), ('major', 1), ('minor', 1), ('old_mask', 1),
    ('restored_mask', 1), ('irq_status', 1), ('irq_count', 2),
    ('buffer_physical', 4), ('initial_address', 2), ('initial_count', 2),
    ('irq_address', 2), ('irq_dma_count', 2), ('final_address', 2),
    ('final_count', 2), ('start_ticks', 4), ('end_ticks', 4), ('failure', 2),
)
REPORT_SIZE = 4 + sum(width for _, width in FIELDS)


def parse_report(raw):
    if len(raw) != REPORT_SIZE or raw[:4] != b'SCN1':
        raise ValueError('Invalid SB16 count report')
    report, offset = {}, 4
    for name, width in FIELDS:
        report[name] = int.from_bytes(raw[offset:offset + width], 'little')
        offset += width
    return report


def expected_progress(report):
    """Documented channel-sample count, independently applied to guest registers."""
    if report['bits'] not in (8, 16) or report['channels'] not in (1, 2):
        raise ValueError('Unsupported reported sample geometry')
    initial = report['initial_address']
    if report['initial_count'] != DMA_UNITS - 1 or initial + 2 * SAMPLES >= 65536:
        raise ValueError('Count oracle may wrap or has a different DMA capacity')
    return dict(address=initial + SAMPLES, count=DMA_UNITS - SAMPLES - 1,
                bytes=SAMPLES * (report['bits'] // 8), irq_status=1 if report['bits'] == 8 else 2)


def sb16_count(directory, nasm, *, bits, channels, fifo):
    if type(bits) is not int or bits not in (8, 16) or type(channels) is not int or channels not in (1, 2) or type(fifo) is not bool:
        raise ValueError('Unsupported authored SB16 count profile')
    labels = ('ready', 'started', 'done', 'failed', 'report', 'arena')
    source = f'%define BITS {bits}\n%define CHANNELS {channels}\n%define FIFO {int(fifo)}\n' + r'''
bits 16
org 100h
%if BITS = 16
%define ADDR_PORT 0c4h
%define COUNT_PORT 0c6h
%define MASK_PORT 0d4h
%define MODE_PORT 0d6h
%define CLEAR_PORT 0d8h
%define PAGE_PORT 08bh
%define ACK_PORT 022fh
%define COMMAND (0b0h | (FIFO << 1))
%define DSP_MODE (10h | ((CHANNELS-1) << 5))
%else
%define ADDR_PORT 2
%define COUNT_PORT 3
%define MASK_PORT 0ah
%define MODE_PORT 0bh
%define CLEAR_PORT 0ch
%define PAGE_PORT 83h
%define ACK_PORT 022eh
%define COMMAND (0c0h | (FIFO << 1))
%define DSP_MODE ((CHANNELS-1) << 5)
%endif
    nop
    push cs
    pop ds
    push cs
    pop es
    mov ax,40h
    mov fs,ax
    cld
    in al,21h
    mov [old_mask],al
    mov [restored_mask],al
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
    ; An 8-KiB-aligned arena never crosses a 64-KiB physical page.
    xor eax,eax
    mov ax,ds
    shl eax,4
    mov ebp,eax
    add eax,arena+8191
    and eax,0ffffe000h
    mov [buffer_physical],eax
    mov edx,eax
    shr edx,16
    mov [dma_page],dl
%if BITS = 16
    shr eax,1
%endif
    mov [initial_address],ax
    mov eax,[buffer_physical]
    sub eax,ebp
    mov di,ax
    mov cx,4096
%if BITS = 16
    mov ax,2800h
fill:
    stosw
    neg ax
%else
    mov al,96
fill:
    stosb
    xor al,192
%endif
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
    mov al,1fh
    call dsp_write
    mov al,40h
    call dsp_write
    mov al,0d1h
    call dsp_write
    mov al,5
    out MASK_PORT,al
    xor al,al
    out CLEAR_PORT,al
    mov ax,[initial_address]
    out ADDR_PORT,al
    mov al,ah
    out ADDR_PORT,al
    xor al,al
    out CLEAR_PORT,al
    mov ax,4095
    out COUNT_PORT,al
    mov al,ah
    out COUNT_PORT,al
    mov al,[dma_page]
    out PAGE_PORT,al
    mov al,49h
    out MODE_PORT,al
    mov al,1
    out MASK_PORT,al
    call read_dma
    mov [initial_address],bx
    mov [initial_count],ax
    mov byte [phase],1
ready:
    nop
    mov eax,[fs:6ch]
    mov [start_ticks],eax
    mov al,COMMAND
    call dsp_write
    mov al,DSP_MODE
    call dsp_write
    mov al,0ffh
    call dsp_write
    mov al,3
    call dsp_write
    mov byte [phase],2
started:
    nop
wait_irq:
    cmp word [irq_count],0
    jne completed
    mov eax,[fs:6ch]
    sub eax,[start_ticks]
    cmp eax,36
    jb wait_irq
    mov word [failure],3
    jmp failed
completed:
    mov ebx,[fs:6ch]
tail:
    mov eax,[fs:6ch]
    sub eax,ebx
    cmp eax,2
    jb tail
    call read_dma
    mov [final_address],bx
    mov [final_count],ax
    mov eax,[fs:6ch]
    mov [end_ticks],eax
    mov al,5
    out MASK_PORT,al
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
    in al,21h
    mov [restored_mask],al
    mov byte [phase],3
done:
    nop
    mov ax,4c2ah
    int 21h
bad_dsp:
    mov word [failure],2
failed:
    mov byte [phase],0ffh
    jmp failed
read_dma:
    xor al,al
    out CLEAR_PORT,al
    in al,ADDR_PORT
    mov ah,al
    in al,ADDR_PORT
    xchg al,ah
    mov bx,ax
    xor al,al
    out CLEAR_PORT,al
    in al,COUNT_PORT
    mov ah,al
    in al,COUNT_PORT
    xchg al,ah
    ret
irq7:
    push ax
    push bx
    push dx
    push ds
    push cs
    pop ds
    inc word [irq_count]
    mov dx,224h
    mov al,82h
    out dx,al
    inc dx
    in al,dx
    or [irq_status],al
    call read_dma
    mov [irq_address],bx
    mov [irq_dma_count],ax
    mov dx,ACK_PORT
    in al,dx
    mov al,20h
    out 20h,al
    pop ds
    pop dx
    pop bx
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
report: db 'SCN1'
    db BITS,CHANNELS,FIFO
phase: db 0
reset_byte: db 0
major: db 0
minor: db 0
old_mask: db 0
restored_mask: db 0
irq_status: db 0
irq_count: dw 0
buffer_physical: dd 0
initial_address: dw 0
initial_count: dw 4095
irq_address: dw 0
irq_dma_count: dw 0
final_address: dw 0
final_count: dw 0
start_ticks: dd 0
end_ticks: dd 0
failure: dw 0
old_vector: dd 0
dma_page: db 0
arena: times 16384 db 0
directory: db 'SCND'
    dw ready,started,done,failed,report,arena
'''
    import struct
    code = assemble(directory, f'sb16-count-{bits}-{channels}-{int(fifo)}', source, nasm)
    marker = code.rindex(b'SCND') + 4
    offsets = dict(zip(labels, struct.unpack_from('<6H', code, marker)))
    offsets['report_size'] = REPORT_SIZE
    return code, offsets
