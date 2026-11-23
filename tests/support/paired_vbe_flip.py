"""Same authored VBE 101h page-flip program for DOSBox-X and QEMU."""
from hashlib import sha256
import struct


WIDTH, HEIGHT = 640, 480
FLIP_Y = 256
BANK_BYTES = 65536
FLIP_ORIGIN = WIDTH * FLIP_Y
WINDOW_BYTES = WIDTH * HEIGHT
VRAM_BYTES = FLIP_ORIGIN + WINDOW_BYTES
SUBFUNCTION_SET, SUBFUNCTION_WAIT = 0, 0x80
DIRECT, AFTER_LEADING_RETRACE = 0, 1
COM_SHA = 'd9104b681918860b345e430f79cbba408b34fe25862b8054881080a22841f974'
SYMBOLS = ('flip_go', 'flip_subfunction', 'flip_sync', 'flip_y', 'bios_set',
           'post_bios', 'bios_get', 'flip_done', 'flip_result', 'flip_fault')
RESULT = struct.Struct('<6H2B')
_RESULT_FIELDS = ('set_ax', 'get_ax', 'x', 'y', 'pit_before', 'pit_after',
                  'status_before', 'status_after')

_PROBE = r'''
vbe_flip_init:
    mov ax,4f06h
    mov bx,1
    int 10h
    cmp ax,4fh
    jne flip_fault
    push cs
    pop ds
    cmp bx,640
    jne flip_fault
    cmp cx,640
    jne flip_fault
    cmp dx,736
    jb flip_fault

    ; Free-running independent PIT channel 2. No data ports touch its clock.
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

flip_request:
    push cs
    pop ds
    mov dx,3dah
    cmp byte [flip_sync],0
    je .issue
    mov ecx,1000000
.clear:
    in al,dx
    test al,8
    jz .set
    dec ecx
    jnz .clear
    jmp flip_fault
.set:
    in al,dx
    test al,8
    jnz .issue
    dec ecx
    jnz .set
    jmp flip_fault
.issue:
    call flip_read_pit
    mov [pit_before],ax
    in al,dx
    and al,9
    mov [status_before],al
    mov ax,4f07h
    xor bx,bx
    mov bl,[flip_subfunction]
    xor cx,cx
    mov dx,[flip_y]
bios_set:
    int 10h
post_bios:
    push cs
    pop ds
    mov [set_ax],ax
    call flip_read_pit
    mov [pit_after],ax
    mov dx,3dah
    in al,dx
    and al,9
    mov [status_after],al
    mov ax,4f07h
    mov bx,1
bios_get:
    int 10h
    push cs
    pop ds
    mov [get_ax],ax
    mov [get_x],cx
    mov [get_y],dx
    mov byte [flip_go],0
flip_done:
    cmp byte [flip_go],1
    je flip_request
    cmp byte [advance],3
    jne flip_done
    jmp banked

flip_fault:
    jmp flip_fault

flip_read_pit:
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
    ret

flip_go: db 0
flip_subfunction: db 0
flip_sync: db 0
flip_y: dw 0
flip_result:
set_ax: dw 0
get_ax: dw 0
get_x: dw 0
get_y: dw 0
pit_before: dw 0
pit_after: dw 0
status_before: db 0
status_after: db 0
db 'VP10'
dw flip_go,flip_subfunction,flip_sync,flip_y,bios_set,post_bios,bios_get,flip_done,flip_result,flip_fault
'''


def source_with_flip_probe(original):
    replacements = {
        'banked:\n    cmp byte [advance],3': ('banked:\n    cmp byte [flip_go],1\n'
                                              '    je flip_request\n    cmp byte [advance],3'),
        'cmp word [bank],4\n    jne .fill\n    mov cx,(640*480-4*65536)/2':
            'cmp word [bank],7\n    jne .fill\n    mov cx,(640*736-7*65536)/2',
        'cmp word [bank],5\n    jb .window\n    ret':
            'cmp word [bank],8\n    jb .window\n    call vbe_flip_init\n    ret',
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
    assert code[footer:footer + 4] == b'VP10'
    labels = struct.unpack('<5H', code[pages + 4:pages + 14])
    offsets = dict(zip(SYMBOLS, struct.unpack('<10H', code[footer + 4:pages]), strict=True))
    assert offsets['post_bios'] == offsets['bios_set'] + 2
    for name in ('bios_set', 'bios_get'):
        at = offsets[name] - 0x100
        assert code[at:at + 2] == b'\xcd\x10'
    return labels, offsets


def event(data):
    fields = dict(zip(_RESULT_FIELDS, RESULT.unpack(data), strict=True))
    assert fields['set_ax'] == fields['get_ax'] == 0x004f
    fields['elapsed_pit_ticks'] = (fields['pit_before'] - fields['pit_after']) & 0xffff
    assert fields['elapsed_pit_ticks'] < 32768
    assert all(fields[n] in (0, 1, 9) for n in ('status_before', 'status_after'))
    return fields


def expected_rgb(origin, palette):
    assert origin in (0, FLIP_ORIGIN)
    banked = b''.join(rgb * min(BANK_BYTES, VRAM_BYTES - bank * BANK_BYTES)
                      for bank, rgb in enumerate(palette[1:9]))
    assert len(banked) == VRAM_BYTES * 3
    return banked[origin * 3:(origin + WINDOW_BYTES) * 3]


def check_pixels(image, origin, palette):
    assert image.size == (WIDTH, HEIGHT)
    actual = image.convert('RGB').tobytes()
    expected = expected_rgb(origin, palette)
    assert actual == expected
    return sha256(actual).hexdigest()
