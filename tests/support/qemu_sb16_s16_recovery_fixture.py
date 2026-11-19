"""New 2026-11-19 S16 recovery oracle; not the lost 1ecf4b5 fixture.

All playback, DMA setup, IRQ acknowledgement and mutable-ring writes below
are authored guest instructions. Host code only assembles and observes them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import struct

from support.dos_process_fixture import assemble


PROFILE = 'fdisbull-sb16-s16-recovery-20261119-1'
RING_BYTES = 8192
BLOCK_BYTES = 256
BLOCKS = RING_BYTES // BLOCK_BYTES
SINGLE_BYTES = 4096
FUTURE_NS = 600_000_000
FRONTIERS = ('running', 'masked', 'irq16', 'irq-both', 'halted',
             'future-rate', 'absent', 'inactive')
ENCODINGS = ('s16', 'u16', 's8')
GEOMETRIES = ('normal', 'decrement', 'partial-block', 'partial-ring')
FIELDS = (
    ('bits', 1), ('channels', 1), ('fifo', 1), ('auto', 1),
    ('frontier', 1), ('geometry', 1), ('encoding', 1), ('reserved', 1),
    ('rate', 2), ('future_rate', 2), ('block_bytes', 2), ('dma_bytes', 2),
    ('stage', 2), ('failure', 2), ('irq_count', 4), ('busy_count', 4),
    ('produced_bytes', 4), ('next_block', 2), ('refill_active', 2),
    ('refill_generation', 2), ('buffer_physical', 4), ('buffer_offset', 2),
    ('initial_address', 2), ('initial_count', 2),
    ('selected_address', 2), ('selected_count', 2),
    ('reset_byte', 1), ('major', 1), ('minor', 1), ('old_mask', 1),
    ('irq_status', 1), ('selected_irq_status', 1),
)
REPORT_SIZE = 4 + sum(width for _, width in FIELDS) + 2 * BLOCKS


@dataclass(frozen=True)
class VoiceCase:
    name: str
    channels: int = 1
    auto: bool = False
    fifo: bool = False
    rate: int = 8000
    frontier: str = 'running'
    encoding: str = 's16'
    geometry: str = 'normal'
    capture_format: str = 'u8-mono'

    def validate(self):
        if (not isinstance(self.name, str) or not self.name
                or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in self.name)
                or type(self.channels) is not int or self.channels not in (1, 2)
                or type(self.auto) is not bool or type(self.fifo) is not bool
                or type(self.rate) is not int or not 5000 <= self.rate <= 45000
                or self.frontier not in FRONTIERS or self.encoding not in ENCODINGS
                or self.geometry not in GEOMETRIES
                or self.capture_format not in ('u8-mono', 's16-stereo')):
            raise ValueError('Unsupported authored S16 recovery case')
        if self.frontier in ('future-rate', 'inactive') and self.auto:
            raise ValueError('Future-rate/inactive witness requires a single-cycle voice')
        if self.geometry in ('partial-block', 'partial-ring') and self.channels != 2:
            raise ValueError('The partial-frame witness requires stereo')
        if self.geometry != 'normal' and self.frontier != 'running':
            raise ValueError('Unsafe geometry uses only the ordinary capture frontier')
        return self

    @property
    def bits(self):
        return 8 if self.encoding == 's8' else 16

    @property
    def block_bytes(self):
        value = BLOCK_BYTES if self.auto else SINGLE_BYTES
        return value + 2 if self.geometry == 'partial-block' else value

    @property
    def dma_bytes(self):
        return RING_BYTES - 2 if self.geometry == 'partial-ring' else RING_BYTES

    def record(self):
        self.validate()
        return asdict(self)


POSITIVE_CASES = tuple(
    VoiceCase(f'{mode}-c{channels}-fifo{int(fifo)}', channels=channels,
              auto=mode == 'auto', fifo=fifo,
              rate=11025 if mode == 'auto' else (8000 if channels == 1 else 32000))
    for mode in ('single', 'auto') for channels in (1, 2) for fifo in (False, True)
) + (
    VoiceCase('minimum-rate', auto=True, rate=5000),
    VoiceCase('maximum-rate', auto=True, channels=2, rate=45000),
    VoiceCase('masked-dreq', auto=True, channels=2, rate=11025, frontier='masked'),
    VoiceCase('pending-high-irq', auto=True, channels=2, rate=11025, frontier='irq16'),
    VoiceCase('pending-low-and-high-irq', auto=True, rate=11025, frontier='irq-both'),
    VoiceCase('halted-resume', auto=True, channels=2, rate=11025, frontier='halted'),
    VoiceCase('future-rate', frontier='future-rate'),
    VoiceCase('combined-s16-capture', auto=True, channels=2, rate=11025,
              capture_format='s16-stereo'),
    VoiceCase('absent-voice', frontier='absent'),
    VoiceCase('inactive-voice', frontier='inactive'),
)
UNSAFE_CASES = (
    VoiceCase('unsigned16', encoding='u16'),
    VoiceCase('signed8', encoding='s8'),
    VoiceCase('decrement-dma', geometry='decrement'),
    VoiceCase('partial-stereo-block', channels=2, geometry='partial-block'),
    VoiceCase('partial-stereo-ring', channels=2, geometry='partial-ring'),
)


def parse_report(raw):
    if not isinstance(raw, bytes) or len(raw) != REPORT_SIZE or raw[:4] != b'S16R':
        raise ValueError('Invalid authored S16 recovery report')
    result, offset = {}, 4
    for name, width in FIELDS:
        result[name] = int.from_bytes(raw[offset:offset + width], 'little')
        offset += width
    result['generations'] = list(struct.unpack_from('<' + 'H' * BLOCKS, raw, offset))
    return result


def block_pcm(block, generation, *, bits=16):
    """Independent integer description of the guest's complete block writes."""
    if (type(block) is not int or not 0 <= block < BLOCKS
            or type(generation) is not int or not 0 <= generation <= 65535
            or type(bits) is not int or bits not in (8, 16)):
        raise ValueError('Invalid authored block/generation/width')
    first = 0x1357 + 0x101 * block + 0x151 * generation
    if bits == 8:
        return bytes((first + 0x4f31 * n) & 255 for n in range(BLOCK_BYTES))
    return b''.join(struct.pack('<H', (first + 0x4f31 * n) & 65535)
                    for n in range(BLOCK_BYTES // 2))


def ring_pcm(generations, *, bits=16):
    if not isinstance(generations, (list, tuple)) or len(generations) != BLOCKS:
        raise ValueError('Expected all authored ring generations')
    return b''.join(block_pcm(block, value, bits=bits)
                    for block, value in enumerate(generations))


def expected_dma_progress(initial_address, current_address, *, bits=16):
    """Controller addresses are transfer units; the observed byte delta is explicit."""
    if (type(bits) is not int or bits not in (8, 16)
            or type(initial_address) is not int or type(current_address) is not int
            or not 0 <= initial_address <= current_address <= 65535):
        raise ValueError('DMA progress is unsupported or wraps')
    units = current_address - initial_address
    return dict(units=units, bytes=units * (bits // 8))


def assembly(case):
    case.validate()
    header = (
        f'%define BITS {case.bits}\n%define CHANNELS {case.channels}\n'
        f'%define AUTO {int(case.auto)}\n%define FIFO {int(case.fifo)}\n'
        f'%define RATE {case.rate}\n%define FRONTIER {FRONTIERS.index(case.frontier)}\n'
        f'%define GEOMETRY {GEOMETRIES.index(case.geometry)}\n'
        f'%define ENCODING {ENCODINGS.index(case.encoding)}\n'
        f'%define BLOCK_LENGTH {case.block_bytes}\n%define DMA_LENGTH {case.dma_bytes}\n'
    )
    return header + r'''
bits 16
org 100h
%if BITS = 16
%define ADDR_PORT 0c4h
%define COUNT_PORT 0c6h
%define MASK_PORT 0d4h
%define MODE_PORT 0d6h
%define CLEAR_PORT 0d8h
%define PAGE_PORT 08bh
%define COMMAND (0b0h | (AUTO << 2) | (FIFO << 1))
%else
%define ADDR_PORT 2
%define COUNT_PORT 3
%define MASK_PORT 0ah
%define MODE_PORT 0bh
%define CLEAR_PORT 0ch
%define PAGE_PORT 83h
%define COMMAND (0c0h | (AUTO << 2) | (FIFO << 1))
%endif
%define DSP_MODE (((ENCODING != 1) << 4) | ((CHANNELS - 1) << 5))
    nop
    push cs
    pop ds
    push cs
    pop es
    mov ax,40h
    mov fs,ax
    cld
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
    jne bad_reset
    mov al,0e1h
    call dsp_write
    call dsp_read
    mov [major],al
    call dsp_read
    mov [minor],al
    cmp byte [major],4
    jne bad_reset
    cmp byte [minor],5
    jne bad_reset
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
    sub eax,ebp
    mov [buffer_offset],ax
    xor bx,bx
initial_fill:
    xor ax,ax
    call fill_block
    inc bx
    cmp bx,32
    jb initial_fill
    cli
    xor ax,ax
    mov es,ax
    mov eax,[es:3ch]
    mov [old_vector],eax
    mov word [es:3ch],irq7
    mov ax,cs
    mov [es:3eh],ax
    in al,21h
    mov [old_mask],al
    and al,7fh
    out 21h,al
    push cs
    pop es
    sti
    mov al,41h
    call dsp_write
    mov al,(RATE >> 8)
    call dsp_write
    mov al,(RATE & 255)
    call dsp_write
    mov al,0d1h
    call dsp_write
    call program_dma
    call read_dma
    mov [initial_address],bx
    mov [initial_count],ax
    mov word [stage],1
ready:
    nop
%if FRONTIER = 2 || FRONTIER = 3
    cli
%endif
%if FRONTIER = 3
    ; Actual DSP command F2 raises the older low-DMA interrupt source.
    mov al,0f2h
    call dsp_write
%endif
    call start_voice
    mov word [stage],2
started:
    nop
%if FRONTIER = 1
    mov al,5
    out MASK_PORT,al
%elif FRONTIER = 2 || FRONTIER = 3
    mov ecx,5000000
wait_pending:
    call read_irq_status
%if FRONTIER = 3
    and al,3
    cmp al,3
    je pending_ready
%else
    test al,2
    jnz pending_ready
%endif
    dec ecx
    jnz wait_pending
    jmp bad_wait
pending_ready:
%elif FRONTIER = 7
    mov ecx,5000000
wait_inactive:
    cmp dword [irq_count],0
    jne inactive_ready
    dec ecx
    jnz wait_inactive
    jmp bad_wait
inactive_ready:
%else
    mov ecx,5000000
wait_progress:
    call read_dma
    cmp bx,[initial_address]
    jne progress_ready
    dec ecx
    jnz wait_progress
    jmp bad_wait
progress_ready:
%endif
%if FRONTIER = 4
    mov al,0d5h
    call dsp_write
%endif
%if FRONTIER = 5
    ; Future DSP rate changes, while the extant voice retains RATE.
    mov al,41h
    call dsp_write
    mov al,56h
    call dsp_write
    mov al,22h
    call dsp_write
%endif
    call read_dma
    mov [selected_address],bx
    mov [selected_count],ax
    call read_irq_status
    mov [selected_irq_status],al
selected:
    nop
%if FRONTIER = 1
    mov al,1
    out MASK_PORT,al
%endif
%if FRONTIER = 4
    mov al,0d6h
    call dsp_write
%endif
    sti
%if FRONTIER = 5 || FRONTIER = 7
    mov ecx,5000000
wait_first_completion:
    cmp dword [irq_count],0
    jne restart_single
    dec ecx
    jnz wait_first_completion
    jmp bad_wait
restart_single:
    cli
    call program_dma
    call start_voice
    sti
%endif
    mov word [stage],3
busy:
    nop
    inc dword [busy_count]
    jmp busy
bad_reset:
    mov word [failure],1
    jmp failed
bad_wait:
    mov word [failure],2
failed:
    mov word [stage],0ffffh
    jmp failed

program_dma:
    mov al,5
    out MASK_PORT,al
    xor al,al
    out CLEAR_PORT,al
    mov eax,[buffer_physical]
%if BITS = 16
    shr eax,1
%endif
    out ADDR_PORT,al
    mov al,ah
    out ADDR_PORT,al
    xor al,al
    out CLEAR_PORT,al
    mov ax,(DMA_LENGTH / (BITS / 8)) - 1
    out COUNT_PORT,al
    mov al,ah
    out COUNT_PORT,al
    mov al,[dma_page]
    out PAGE_PORT,al
    mov al,(49h | (AUTO << 4) | ((GEOMETRY = 1) << 5))
    out MODE_PORT,al
    mov al,1
    out MASK_PORT,al
    ret
start_voice:
    mov al,COMMAND
    call dsp_write
    mov al,DSP_MODE
    call dsp_write
    mov al,((BLOCK_LENGTH / (BITS / 8)) - 1) & 255
    call dsp_write
    mov al,((BLOCK_LENGTH / (BITS / 8)) - 1) >> 8
    call dsp_write
    ret
; BX identifies a block. AX is its independently recorded generation.
fill_block:
    mov di,bx
    shl di,8
    add di,[buffer_offset]
    imul ax,ax,0151h
    mov dx,bx
    imul dx,dx,0101h
    add ax,dx
    add ax,01357h
    mov cx,256 / (BITS / 8)
fill_sample:
%if BITS = 16
    stosw
%else
    stosb
%endif
    add ax,4f31h
    loop fill_sample
    ret
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
read_irq_status:
    mov dx,224h
    mov al,82h
    out dx,al
    inc dx
    in al,dx
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
    call read_irq_status
    or [irq_status],al
%if AUTO
    test al,2
    jz ack_irqs
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
    and word [next_block],31
    add dword [produced_bytes],256
%endif
ack_irqs:
    inc dword [irq_count]
    ; Read both real acknowledge ports; no host device writes are involved.
    mov dx,22eh
    in al,dx
    inc dx
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
    mov word [failure],3
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
    mov word [failure],4
    jmp failed
read_ready:
    mov dx,22ah
    in al,dx
    pop dx
    pop cx
    ret
report:
    db 'S16R',BITS,CHANNELS,FIFO,AUTO,FRONTIER,GEOMETRY,ENCODING,0
    dw RATE,22050,BLOCK_LENGTH,DMA_LENGTH
stage: dw 0
failure: dw 0
irq_count: dd 0
busy_count: dd 0
produced_bytes: dd 0
next_block: dw 0
refill_active: dw 0
refill_generation: dw 0
buffer_physical: dd 0
buffer_offset: dw 0
initial_address: dw 0
initial_count: dw 0
selected_address: dw 0
selected_count: dw 0
reset_byte: db 0
major: db 0
minor: db 0
old_mask: db 0
irq_status: db 0
selected_irq_status: db 0
generations: times 32 dw 0
report_end:
old_vector: dd 0
dma_page: db 0
    align 16,db 0
arena: times 16384 db 0
    db 'SRD1'
    dw ready,started,selected,busy,failed,report,report_end,arena
    dw start_voice,program_dma,fill_block,irq7,ack_irqs
'''


LABELS = ('ready', 'started', 'selected', 'busy', 'failed', 'report', 'report_end',
          'arena', 'start_voice', 'program_dma', 'fill_block', 'irq7', 'ack_irqs')


def build_fixture(directory, nasm, case):
    code = assemble(directory, 's16-recovery-' + case.name, assembly(case), nasm)
    footer = 4 + 2 * len(LABELS)
    if len(code) >= 0xff00 or code[-footer:-footer + 4] != b'SRD1':
        raise ValueError('Authored S16 recovery footer/extent is invalid')
    offsets = dict(zip(LABELS, struct.unpack_from('<' + 'H' * len(LABELS),
                       code, len(code) - footer + 4), strict=True))
    if offsets['report_end'] - offsets['report'] != REPORT_SIZE:
        raise ValueError('Authored report layout disagrees with its independent decoder')
    if offsets['arena'] + 16384 > len(code) + 256:
        raise ValueError('Authored static DMA allocation is incomplete')
    offsets['report_size'] = REPORT_SIZE
    return code, offsets
