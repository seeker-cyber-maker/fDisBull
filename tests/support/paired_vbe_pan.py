"""Same authored banked VBE 101h horizontal-panning probe for both engines."""
from hashlib import sha256
import struct

from support.paired_vbe_flip import BANK_BYTES, HEIGHT, WIDTH, source_with_flip_probe


PITCH = 648
PAN_X = 5
BACKING_BYTES = PITCH * HEIGHT
SETUP_RESULT = struct.Struct('<4H')
SYMBOLS = ('flip_go', 'flip_subfunction', 'flip_sync', 'flip_y', 'flip_x',
           'bios_set', 'post_bios', 'bios_get', 'flip_done', 'flip_result', 'flip_fault',
           'pan_setup_go', 'pan_ready', 'pan_setup_result')
COM_SHA = 'ce492b9d3cccfacd8ac4bec84eb98fa3d9299a45d797ef5e8f506069daca33ab'

_PAN_SETUP = r'''
pan_setup:
    mov ax,4f06h
    xor bx,bx
    mov cx,648
    int 10h
    push cs
    pop ds
    mov [pan_setup_result],ax
    mov [pan_setup_result+2],bx
    mov [pan_setup_result+4],cx
    mov [pan_setup_result+6],dx
    cmp ax,004fh
    jne flip_fault
    cmp bx,648
    jne flip_fault
    cmp cx,648
    jne flip_fault
    cmp dx,480
    jb flip_fault
    mov word [pan_bank],0
    cld
.bank:
    mov ax,[pan_bank]
    mul word [bank_step]
    mov dx,ax
    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,004fh
    jne flip_fault
    push cs
    pop ds
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor cx,cx
    cmp word [pan_bank],4
    jne .pixel
    mov cx,648*480-4*65536
.pixel:
    ; i is the 16-bit window byte and pan_bank supplies the upper bits.
    mov ax,di
    mov bx,di
    shr bx,5
    xor ax,bx
    mov bx,di
    shr bx,9
    xor ax,bx
    xor ax,[pan_bank]
    and al,7
    inc al
    stosb
    cmp di,cx
    jne .pixel
    inc word [pan_bank]
    cmp word [pan_bank],5
    jb .bank
    mov byte [pan_setup_go],2
pan_ready:
    cmp byte [flip_go],1
    je flip_request
    cmp byte [advance],3
    jne pan_ready
    jmp banked

pan_setup_go: db 0
pan_setup_result: times 4 dw 0
pan_bank: dw 0
db 'VP11'
dw flip_go,flip_subfunction,flip_sync,flip_y,flip_x,bios_set,post_bios,bios_get,flip_done,flip_result,flip_fault,pan_setup_go,pan_ready,pan_setup_result
'''


def source_with_pan_probe(original):
    source = source_with_flip_probe(original)
    replacements = {
        'banked:\n    cmp byte [flip_go],1': (
            'banked:\n    cmp byte [pan_setup_go],1\n    je pan_setup\n    cmp byte [flip_go],1'),
        '    xor cx,cx\n    mov dx,[flip_y]': '    mov cx,[flip_x]\n    mov dx,[flip_y]',
        'flip_y: dw 0\nflip_result:': 'flip_y: dw 0\nflip_x: dw 0\nflip_result:',
        "db 'VP10'\ndw flip_go,flip_subfunction,flip_sync,flip_y,bios_set,post_bios,bios_get,flip_done,flip_result,flip_fault\n":
            _PAN_SETUP,
    }
    for before, after in replacements.items():
        assert source.count(before) == 1
        source = source.replace(before, after)
    return source


def symbols(code):
    pages = len(code) - 62
    footer = pages - 4 - 2 * len(SYMBOLS)
    assert code[pages:pages + 4] == b'VGA3'
    assert code[footer:footer + 4] == b'VP11'
    labels = struct.unpack('<5H', code[pages + 4:pages + 14])
    fields = struct.unpack(f'<{len(SYMBOLS)}H', code[footer + 4:pages])
    offsets = dict(zip(SYMBOLS, fields, strict=True))
    assert offsets['post_bios'] == offsets['bios_set'] + 2
    for name in ('bios_set', 'bios_get'):
        at = offsets[name] - 0x100
        assert code[at:at + 2] == b'\xcd\x10'
    return labels, offsets


def expected_rgb(origin, palette):
    assert 0 <= origin <= PAN_X
    backing = [palette[((i ^ ((i & (BANK_BYTES - 1)) >> 5) ^
                         ((i & (BANK_BYTES - 1)) >> 9) ^ (i >> 16)) & 7) + 1]
               for i in range(BACKING_BYTES)]
    return b''.join(pixel for row in range(HEIGHT)
                    for pixel in backing[row * PITCH + origin:row * PITCH + origin + WIDTH])


def check_pixels(image, origin, palette):
    assert image.size == (WIDTH, HEIGHT)
    actual = image.convert('RGB').tobytes()
    assert actual == expected_rgb(origin, palette)
    return sha256(actual).hexdigest()
