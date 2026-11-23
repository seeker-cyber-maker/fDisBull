"""Authored VBE 101h display-state save and restore fixture."""

from struct import Struct, unpack_from


WIDTH = 640
HEIGHT = 480
BANK_BYTES = 65536
STATE_BYTES = 4096
STATE_FILL = 0xA5
PITCH = 648
MUTATED_PITCH = 656
ORIGIN = 64 * PITCH + 5
VRAM_OFFSET = 0x1234
VRAM_MUTATION = 9
SIZE_MASKS = (0, 1, 2, 4, 7, 8, 15)
SIZE_RESULT = Struct('<HH')
PHASE_FIELDS = ('mode_ax', 'mode', 'stride_ax', 'pitch', 'pixels', 'lines',
                'pan_ax', 'x', 'y', 'bank_ax', 'bank', 'dac_ax', 'dac_width',
                'palette_ax', 'probe')
PHASE_RESULT = Struct('<15H4s')
DAC_FIELDS = ('set_ax', 'save_ax', 'restore_ax', 'get_ax', 'width', 'palette_ax')
DAC_RESULT = Struct('<6H4s')
PALETTE = (
    (57, 25, 39), (13, 61, 3), (14, 19, 11), (33, 11, 41),
    (63, 2, 25), (32, 1, 3), (43, 2, 4),
)
MUTATED_COLOR = (19, 63, 1)
DAC8_COLOR = (213, 182, 199)
PHASES = ('initial', 'mutated', 'restored')
SYMBOLS = (
    'rm_ready', 'rm_save_call', 'rm_saved', 'rm_mutated', 'rm_restore_call',
    'rm_restored', 'rm_dac_done', 'rm_fault', 'rm_go', 'phase_results',
    'size_results', 'statuses', 'state_guard', 'state_buffer', 'dac_results',
)


def _palette_bytes(colors):
    return ','.join(str(channel) for r, g, b in colors for channel in (b, g, r, 0))


SOURCE = rf'''
bits 16
org 100h
    push cs
    pop ds
    mov ax,4f02h
    mov bx,101h
    int 10h
    cmp ax,004fh
    jne rm_fault

    xor si,si
.query_size:
    movzx cx,byte [size_masks+si]
    xor dx,dx
    mov bx,0beefh
    mov ax,4f04h
    int 10h
    mov di,si
    shl di,2
    mov [size_results+di],ax
    mov [size_results+di+2],bx
    inc si
    cmp si,{len(SIZE_MASKS)}
    jb .query_size
    cmp word [size_results+{4*(len(SIZE_MASKS)-1)}],004fh
    jne rm_fault
    cmp word [size_results+{4*(len(SIZE_MASKS)-1)+2}],{STATE_BYTES//64}
    ja rm_fault

    mov cx,{PITCH}
    call set_stride
    mov di,initial_colors
    mov cx,{len(PALETTE)}
    call set_palette

    mov ax,0a000h
    mov es,ax
.fill_bank:
    mov dx,[bank]
    call set_bank
    mov ax,[bank]
    inc al
    mov ah,al
    xor di,di
    mov cx,8000h
    cld
    rep stosw
    inc word [bank]
    cmp word [bank],{len(PALETTE)}
    jb .fill_bank
    mov dx,2
    call set_bank
    mov cx,5
    mov dx,64
    call set_pan
    mov si,phase_results
    call read_phase

rm_ready:
    cmp byte [rm_go],1
    jne rm_ready
    push cs
    pop es
    mov bx,state_buffer
    mov cx,15
    mov dx,1
    mov ax,4f04h
rm_save_call:
    int 10h
    mov [statuses],ax
    cmp ax,004fh
    jne rm_fault
rm_saved:
    cmp byte [rm_go],2
    jne rm_saved

    xor cx,cx
    xor dx,dx
    call set_pan
    mov cx,{MUTATED_PITCH}
    call set_stride
    mov di,mutated_color
    mov cx,1
    call set_palette
    mov dx,6
    call set_bank
    mov ax,0a000h
    mov es,ax
    mov byte [es:{VRAM_OFFSET}],{VRAM_MUTATION}
    mov dx,3
    call set_bank
    mov si,phase_results+{PHASE_RESULT.size}
    call read_phase

rm_mutated:
    cmp byte [rm_go],3
    jne rm_mutated
    push cs
    pop es
    mov bx,state_buffer
    mov cx,15
    mov dx,2
    mov ax,4f04h
rm_restore_call:
    int 10h
    mov [statuses+2],ax
    cmp ax,004fh
    jne rm_fault
    mov si,phase_results+{2*PHASE_RESULT.size}
    call read_phase

rm_restored:
    cmp byte [rm_go],4
    jne rm_restored
    mov bx,0800h
    mov ax,4f08h
    int 10h
    mov [dac_results],ax
    cmp ax,004fh
    jne rm_dac_done
    cmp bh,8
    jne rm_dac_done
    mov di,dac8_color
    mov cx,1
    call set_palette
    push cs
    pop es
    mov bx,dac_buffer
    mov cx,15
    mov dx,1
    mov ax,4f04h
    int 10h
    mov [dac_results+2],ax
    mov bx,0600h
    mov ax,4f08h
    int 10h
    mov di,mutated_color
    mov cx,1
    call set_palette
    push cs
    pop es
    mov bx,dac_buffer
    mov cx,15
    mov dx,2
    mov ax,4f04h
    int 10h
    mov [dac_results+4],ax
    mov bx,1
    mov ax,4f08h
    int 10h
    mov [dac_results+6],ax
    movzx bx,bh
    mov [dac_results+8],bx
    push cs
    pop es
    mov di,dac_results+12
    mov byte [di+3],0ccH
    mov cx,1
    mov dx,1
    mov bx,1
    mov ax,4f09h
    int 10h
    mov [dac_results+10],ax
rm_dac_done:
    cmp byte [rm_go],5
    jne rm_dac_done
    mov ax,4c00h
    int 21h

set_stride:
    mov ax,4f06h
    mov bx,2
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

set_palette:
    push cs
    pop es
    mov ax,4f09h
    xor bx,bx
    mov dx,1
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

set_bank:
    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

set_pan:
    mov ax,4f07h
    mov bx,80h
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

read_phase:
    mov ax,4f03h
    int 10h
    mov [si],ax
    mov [si+2],bx
    mov ax,4f06h
    mov bx,1
    int 10h
    mov [si+4],ax
    mov [si+6],bx
    mov [si+8],cx
    mov [si+10],dx
    mov ax,4f07h
    mov bx,1
    int 10h
    mov [si+12],ax
    mov [si+14],cx
    mov [si+16],dx
    mov ax,4f05h
    mov bx,100h
    int 10h
    mov [si+18],ax
    mov [si+20],dx
    mov ax,4f08h
    mov bx,1
    int 10h
    mov [si+22],ax
    movzx bx,bh
    mov [si+24],bx
    push cs
    pop es
    lea di,[si+30]
    mov byte [di+3],0ccH
    mov ax,4f09h
    mov bx,1
    mov cx,1
    mov dx,1
    int 10h
    mov [si+26],ax
    mov dx,6
    call set_bank
    mov ax,0a000h
    mov es,ax
    movzx ax,byte [es:{VRAM_OFFSET}]
    mov [si+28],ax
    mov dx,[si+20]
    call set_bank
    ret

rm_fault:
    jmp rm_fault

rm_go: db 0
bank: dw 0
size_masks: db {','.join(str(value) for value in SIZE_MASKS)}
size_results: times {SIZE_RESULT.size * len(SIZE_MASKS)} db 0
statuses: dw 0,0
phase_results: times {PHASE_RESULT.size * len(PHASES)} db 0
dac_results: times {DAC_RESULT.size} db 0
initial_colors: db {_palette_bytes(PALETTE)}
mutated_color: db {_palette_bytes((MUTATED_COLOR,))}
dac8_color: db {_palette_bytes((DAC8_COLOR,))}
state_guard: times 16 db {STATE_FILL}
state_buffer: times {STATE_BYTES} db {STATE_FILL}
state_end_guard: times 16 db {STATE_FILL}
dac_buffer: times {STATE_BYTES} db {STATE_FILL}
db 'FDB4F04STATE'
dw {','.join(SYMBOLS)}
'''


def labels(code):
    marker = b'FDB4F04STATE'
    start = code.index(marker) + len(marker)
    assert len(code) == start + 2 * len(SYMBOLS)
    return dict(zip(SYMBOLS, unpack_from(f'<{len(SYMBOLS)}H', code, start), strict=True))


def sizes(data):
    return dict(zip(SIZE_MASKS, SIZE_RESULT.iter_unpack(data), strict=True))


def _fields(fields, values):
    return dict(zip((*fields, 'color'), (*values[:-1], values[-1].hex()), strict=True))


def phases(data):
    return {name: _fields(PHASE_FIELDS, values) for name, values in
            zip(PHASES, PHASE_RESULT.iter_unpack(data), strict=True)}


def dac_probe(data):
    return _fields(DAC_FIELDS, DAC_RESULT.unpack(data))


def expected_rgb(variant):
    start, pitch = {
        'initial': (ORIGIN, PITCH), 'mutated': (0, MUTATED_PITCH), 'restored': (ORIGIN, PITCH),
        'dosbox-restored': (1, WIDTH),
    }[variant]
    colors = (MUTATED_COLOR, *PALETTE[1:]) if variant == 'mutated' else PALETTE
    rgb = tuple(bytes((component << 2) | (component >> 4) for component in color) for color in colors)
    rows = bytearray()
    for row in range(HEIGHT):
        absolute = start + row * pitch
        first = min(WIDTH, BANK_BYTES - absolute % BANK_BYTES)
        bank = absolute // BANK_BYTES
        rows.extend(rgb[bank] * first)
        if first < WIDTH:
            rows.extend(rgb[bank + 1] * (WIDTH - first))
    return bytes(rows)
