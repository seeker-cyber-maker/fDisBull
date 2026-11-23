"""One authored banked VBE stride and palette program shared by both engines."""

import struct

from support.paired_vbe_flip import BANK_BYTES, HEIGHT, WIDTH


PITCH = 648
FIRST_COLOR = 1
COM_SHA = '2cc2c92b0478a8ca2a74462ba6be1a8817e4c3d54615257d1efd3096eb1d9aaf'
DAC6 = bytes([57, 25, 39, 0xCC, 13, 61, 3, 0xDD])
DAC8 = bytes([173, 82, 201, 0xAA, 55, 249, 23, 0xBB, 91, 12, 231, 0xCC,
              27, 183, 67, 0xDD, 239, 107, 9, 0xEE])
TIMED = bytes([79, 183, 14, 0xAB, 202, 30, 167, 0xCD])
REQUEST = struct.Struct('<BBHHHH')
RESULT = struct.Struct('<6H2B')
BUFFER_BYTES = 256 * 4
DIRECT, RETRACE_HIGH, ACTIVE_RASTER, RETRACE_LOW = range(4)
SYMBOLS = ('palette_go', 'palette_bios', 'palette_return', 'palette_done',
           'palette_result', 'palette_buffer', 'palette_fault')

_PROBE = r'''
palette_probe_init:
    ; Program the independent free-running PIT channel 2 once per mode entry.
    in al,61h
    and al,0fch
    out 61h,al
    mov al,0b4h
    out 43h,al
    xor al,al
    out 42h,al
    out 42h,al
    in al,61h
    or al,1
    out 61h,al
    ret

palette_request:
    push cs
    pop ds
    mov dx,3dah
    cmp byte [palette_gate],0
    je .issue
    mov ecx,1000000
.wait_low:
    in al,dx
    test al,8
    a32 loopne .wait_low
    jnz palette_fault
.wait_high:
    in al,dx
    test al,8
    a32 loope .wait_high
    jz palette_fault
    cmp byte [palette_gate],1
    je .issue
.wait_falling:
    in al,dx
    test al,8
    a32 loopne .wait_falling
    jnz palette_fault
    cmp byte [palette_gate],3
    je .issue
    call palette_read_pit
    mov bx,ax
.wait_active:
    call palette_read_pit
    neg ax
    add ax,bx
    cmp ax,1000
    jae .issue
    a32 loop .wait_active
    jmp palette_fault
.issue:
    call palette_read_pit
    mov [palette_pit_before],ax
    in al,dx
    and al,9
    mov [palette_status_before],al
    push cs
    pop es
    mov di,palette_buffer
    mov ax,[palette_ax]
    mov bx,[palette_bx]
    mov cx,[palette_cx]
    mov dx,[palette_dx]
palette_bios:
    int 10h
palette_return:
    push cs
    pop ds
    mov [palette_ax_out],ax
    mov [palette_bx_out],bx
    mov [palette_cx_out],cx
    mov [palette_dx_out],dx
    call palette_read_pit
    mov [palette_pit_after],ax
    mov dx,3dah
    in al,dx
    and al,9
    mov [palette_status_after],al
    mov byte [palette_go],0
palette_done:
    cmp byte [palette_go],1
    je palette_request
    cmp byte [advance],3
    jne palette_done
    jmp banked

palette_fault:
    jmp palette_fault

palette_read_pit:
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
    ret

palette_go: db 0
palette_gate: db 0
palette_ax: dw 0
palette_bx: dw 0
palette_cx: dw 0
palette_dx: dw 0
palette_result:
palette_ax_out: dw 0
palette_bx_out: dw 0
palette_cx_out: dw 0
palette_dx_out: dw 0
palette_pit_before: dw 0
palette_pit_after: dw 0
palette_status_before: db 0
palette_status_after: db 0
palette_buffer: times 1024 db 0
db 'VP13'
dw palette_go,palette_bios,palette_return,palette_done,palette_result,palette_buffer,palette_fault
'''


def source_with_palette_probe(original):
    replacements = {
        'banked:\n    cmp byte [advance],3': ('banked:\n    cmp byte [palette_go],1\n'
                                              '    je palette_request\n    cmp byte [advance],3'),
        '    cmp word [bank],4\n    jne .fill\n    mov cx,(640*480-4*65536)/2\n.fill:\n': '',
        '    cmp word [bank],5\n    jb .window\n    ret': (
            '    cmp word [bank],5\n    jb .window\n    call palette_probe_init\n    ret'
        ),
        "db 'VGA3'\n": _PROBE + "db 'VGA3'\n",
    }
    for before, after in replacements.items():
        assert original.count(before) == 1
        original = original.replace(before, after)
    return original


def symbols(code):
    pages = len(code) - 62
    footer = pages - 4 - 2 * len(SYMBOLS)
    assert code[pages:pages + 4] == b'VGA3'
    assert code[footer:footer + 4] == b'VP13'
    labels = struct.unpack('<5H', code[pages + 4:pages + 14])
    offsets = dict(zip(SYMBOLS, struct.unpack('<7H', code[footer + 4:pages]), strict=True))
    assert offsets['palette_return'] == offsets['palette_bios'] + 2
    site = offsets['palette_bios'] - 0x100
    assert code[site:site + 2] == b'\xcd\x10'
    return labels, offsets


def event(data):
    fields = dict(zip(('ax', 'bx', 'cx', 'dx', 'pit_before', 'pit_after',
                       'status_before', 'status_after'), RESULT.unpack(data), strict=True))
    fields['elapsed_pit_ticks'] = (fields['pit_before'] - fields['pit_after']) & 0xFFFF
    assert fields['elapsed_pit_ticks'] < 32768
    assert all(fields[name] in (0, 1, 9) for name in ('status_before', 'status_after'))
    return fields


def updated_palette(palette, first, bgrx, dac_bits):
    assert len(bgrx) % 4 == 0
    assert dac_bits in (6, 8)
    result = list(palette)
    for entry in range(len(bgrx) // 4):
        blue, green, red = bgrx[entry * 4:entry * 4 + 3]
        rgb = bytes((value << 2) | (value >> 4) for value in (red, green, blue)) if dac_bits == 6 else (
            bytes([red, green, blue])
        )
        result[first + entry] = rgb
    return result


def expected_rgb(pitch, palette):
    assert WIDTH <= pitch and pitch * HEIGHT <= 5 * BANK_BYTES
    backing = b''.join(color * BANK_BYTES for color in palette[1:6])
    return b''.join(backing[row * pitch * 3:(row * pitch + WIDTH) * 3] for row in range(HEIGHT))
