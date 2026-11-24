"""One authored DOS program for ordinary VBE controller, mode, bank and DAC calls."""

from struct import unpack_from


NAMES = (
    'legacy', 'vbe2', 'mode', 'set_mode', 'set_bank', 'get_bank',
    'bank_before', 'reject_bank', 'get_bank_after', 'bank_after',
    'set_palette', 'get_palette', 'secondary_set', 'secondary_get',
)
SYMBOLS = (
    'done', 'legacy_info', 'legacy_guard', 'vbe2_info', 'vbe2_guard',
    'mode_info', 'mode_guard', 'results', 'colors', 'returned_colors',
    'colors_guard',
)
SOURCE = r'''
bits 16
org 100h
    push cs
    pop ds
    push cs
    pop es
    mov ax,4f00h
    mov di,legacy_info
    int 10h
    mov [results+0],ax

    push cs
    pop es
    mov ax,4f00h
    mov di,vbe2_info
    int 10h
    mov [results+2],ax

    push cs
    pop es
    mov ax,4f01h
    mov cx,101h
    mov di,mode_info
    int 10h
    mov [results+4],ax

    mov ax,4f02h
    mov bx,101h
    int 10h
    mov [results+6],ax

    mov ax,4f05h
    xor bx,bx
    mov dx,2
    int 10h
    mov [results+8],ax
    mov ax,4f05h
    mov bx,0100h
    int 10h
    mov [results+10],ax
    mov [results+12],dx

    ; Bank 256 lies beyond the advertised 16 MiB bank range.
    mov ax,4f05h
    xor bx,bx
    mov dx,100h
    int 10h
    mov [results+14],ax
    mov ax,4f05h
    mov bx,0100h
    int 10h
    mov [results+16],ax
    mov [results+18],dx

    push cs
    pop es
    mov ax,4f09h
    xor bx,bx
    mov cx,2
    mov dx,3
    mov di,colors
    int 10h
    mov [results+20],ax
    mov ax,4f09h
    mov bx,1
    mov cx,2
    mov dx,3
    mov di,returned_colors
    int 10h
    mov [results+22],ax

    mov ax,4f09h
    mov bx,2
    xor cx,cx
    xor dx,dx
    mov di,colors
    int 10h
    mov [results+24],ax
    mov ax,4f09h
    mov bx,3
    xor cx,cx
    xor dx,dx
    mov di,returned_colors
    int 10h
    mov [results+26],ax
done:
    jmp short done

legacy_info: db 'VESA'
             times 252 db 0a5h
legacy_guard: times 16 db 05ah
vbe2_info: db 'VBE2'
           times 508 db 0a5h
vbe2_guard: times 16 db 05ah
mode_info: times 256 db 0a5h
mode_guard: times 16 db 05ah
results: times 14 dw 0ffffh
colors: db 3,15,31,055h,44,5,60,0aah
returned_colors: times 8 db 0cch
colors_guard: times 16 db 05ah
db 'VCOM'
dw done,legacy_info,legacy_guard,vbe2_info,vbe2_guard
dw mode_info,mode_guard,results,colors,returned_colors,colors_guard
'''


def labels(code):
    start = len(code) - 4 - 2 * len(SYMBOLS)
    assert code[start:start + 4] == b'VCOM'
    offsets = unpack_from(f'<{len(SYMBOLS)}H', code, start + 4)
    return dict(zip(SYMBOLS, offsets, strict=True))


def results(raw):
    assert len(raw) == 2 * len(NAMES)
    return dict(zip(NAMES, unpack_from(f'<{len(NAMES)}H', raw), strict=True))


def controller(raw):
    assert len(raw) in (256, 512) and raw[:4] == b'VESA'
    return {
        'version': unpack_from('<H', raw, 4)[0],
        'memory_blocks': unpack_from('<H', raw, 18)[0],
        'software_revision': unpack_from('<H', raw, 20)[0],
    }


def mode(raw):
    assert len(raw) == 256
    return {
        'attributes': unpack_from('<H', raw, 0)[0],
        'pitch': unpack_from('<H', raw, 16)[0],
        'width': unpack_from('<H', raw, 18)[0],
        'height': unpack_from('<H', raw, 20)[0],
        'bpp': raw[25],
        'pages': raw[29],
        'physical_base': unpack_from('<I', raw, 40)[0],
        'linear_pitch': unpack_from('<H', raw, 50)[0],
        'bank_pages': raw[52],
        'linear_pages': raw[53],
    }
