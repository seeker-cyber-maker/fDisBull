"""Same authored two-axis VBE viewport witness for DOSBox-X and QEMU."""
from hashlib import sha256

from support.paired_vbe_flip import BANK_BYTES, HEIGHT, WIDTH
from support.paired_vbe_pan import PAN_X, PITCH, SETUP_RESULT, source_with_pan_probe, symbols


PAN_Y = 64
BACKING_HEIGHT = HEIGHT + PAN_Y
BACKING_BYTES = PITCH * BACKING_HEIGHT
PAN_ORIGIN = PAN_Y * PITCH + PAN_X
COM_SHA = 'f4d593ea95b410273f2eef68622d7ddc89acb453f3ce8b932f74a17608d65b45'


def source_with_xy_probe(original):
    source = source_with_pan_probe(original)
    replacements = {
        '    cmp dx,480\n    jb flip_fault': '    cmp dx,544\n    jb flip_fault',
        '    mov word [pan_bank],0\n    cld': (
            '    mov word [pan_bank],0\n    xor si,si\n    xor bp,bp\n    cld'),
        """    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,004fh""": """    push si
    push bp
    mov ax,4f05h
    xor bx,bx
    int 10h
    pop bp
    pop si
    cmp ax,004fh""",
        """    cmp word [pan_bank],4
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
    jb .bank""": """    cmp word [pan_bank],5
    jne .pixel
    mov cx,648*544-5*65536
.pixel:
    ; Row BP and column SI persist across the 64 KiB CPU aperture switches.
    mov ax,si
    mov bx,si
    shr bx,4
    xor ax,bx
    shr bx,3
    xor ax,bx
    mov bx,bp
    xor ax,bx
    shr bx,3
    xor ax,bx
    shr bx,3
    xor ax,bx
    and al,7
    inc al
    stosb
    inc si
    cmp si,648
    jb .same_row
    xor si,si
    inc bp
.same_row:
    cmp di,cx
    jne .pixel
    inc word [pan_bank]
    cmp word [pan_bank],6
    jb .bank
    cmp bp,544
    jne flip_fault
    test si,si
    jnz flip_fault""",
    }
    for before, after in replacements.items():
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    return source


def expected_rgb(origin, palette):
    y, x = divmod(origin, PITCH)
    assert 0 <= y <= PAN_Y and x + WIDTH <= PITCH
    columns = [col ^ (col >> 4) ^ (col >> 7) for col in range(x, x + WIDTH)]
    return b''.join(palette[1 + ((row ^ (row >> 3) ^ (row >> 6) ^ col) & 7)]
                    for row in range(y, y + HEIGHT) for col in columns)


def bank_seams(origin):
    """Physical 64 KiB boundaries strictly inside the visible span of a row."""
    result = []
    for row in range(HEIGHT):
        start = origin + row * PITCH
        boundary = (start // BANK_BYTES + 1) * BANK_BYTES
        if boundary < start + WIDTH:
            result.append((row, boundary - start))
    return result


def check_pixels(image, origin, palette):
    assert image.size == (WIDTH, HEIGHT)
    actual = image.convert('RGB').tobytes()
    assert actual == expected_rgb(origin, palette)
    return sha256(actual).hexdigest()
