"""Authored VBE 101h fixture using the BIOS-advertised linear aperture."""

from struct import Struct, unpack_from


WIDTH = 640
HEIGHT = 480
PITCH = 648
BANK_BYTES = 65536
BACKING_BYTES = 7 * BANK_BYTES
ORIGIN = 64 * PITCH + 5
MODE_INFO_BYTES = 256
MODE_FIELDS = (
    'info_ax', 'linear_set_ax', 'linear_get_ax', 'linear_mode',
    'stride_ax', 'pitch_bytes', 'pitch_pixels', 'pitch_lines',
    'linear_window_ax', 'linear_window_dx', 'pan_set_ax', 'pan_get_ax',
    'pan_x', 'pan_y', 'banked_set_ax', 'banked_get_ax', 'banked_mode',
)
MODE_RESULTS = Struct(f'<{len(MODE_FIELDS)}H')
MUTATIONS = ((BANK_BYTES - 9, 26, 8), (2 * BANK_BYTES - 5, 24, 9))
PROBE_OFFSETS = (0, 65526, 65535, 65536, 65553, 131066, 131071, 131072, 131091, 458751)
RESULT_BYTES = 3 * len(PROBE_OFFSETS) + 4
VARIANTS = ('baseline', 'half', 'updated')
DAC6 = (
    (57, 25, 39), (13, 61, 3), (14, 19, 11), (33, 11, 41), (63, 2, 25),
    (32, 1, 3), (43, 2, 4), (19, 63, 1), (57, 3, 42),
)
SYMBOLS = (
    'pm_ready', 'pm_update_cut', 'pm_updated', 'rm_pan_call', 'rm_panned',
    'rm_banked', 'rm_fault', 'pm_go', 'mode_info', 'mode_results', 'lfb_base', 'results',
)


SOURCE = rf'''
bits 16
org 100h
    push cs
    pop ds
    push cs
    pop es
    mov ax,4f01h
    mov cx,101h
    mov di,mode_info
    int 10h
    mov [mode_results],ax
    cmp ax,004fh
    jne rm_fault
    test byte [mode_info],80h
    jz rm_fault
    mov eax,[mode_info+28h]
    cmp eax,01000000h
    jb rm_fault
    mov [lfb_base],eax

    mov ax,4f02h
    mov bx,4101h
    int 10h
    mov [mode_results+2],ax
    cmp ax,004fh
    jne rm_fault
    mov ax,4f03h
    int 10h
    mov [mode_results+4],ax
    mov [mode_results+6],bx
    mov ax,4f06h
    mov bx,2
    mov cx,{PITCH}
    int 10h
    mov [mode_results+8],ax
    mov [mode_results+10],bx
    mov [mode_results+12],cx
    mov [mode_results+14],dx
    cmp ax,004fh
    jne rm_fault
    cmp bx,{PITCH}
    jne rm_fault
    mov ax,4f05h
    mov bx,0100h
    mov dx,0beefh
    int 10h
    mov [mode_results+16],ax
    mov [mode_results+18],dx
    call load_palette

    mov [saved_ss],ss
    mov [saved_sp],sp
    mov ax,cs
    movzx ebp,ax
    shl ebp,4
    mov [rm_jump+2],ax
    lea eax,[ebp+gdt]
    mov [gdtr+2],eax
    lea eax,[ebp+pm_entry]
    mov [pm_jump],eax
    mov eax,ebp
    mov [cs16+2],ax
    shr eax,16
    mov [cs16+4],al
    mov [cs16+7],ah
    cli
    lgdt [gdtr]
    mov eax,cr0
    or eax,1
    mov cr0,eax
    jmp dword far [pm_jump]

load_palette:
    mov ax,4f09h
    xor bx,bx
    mov cx,{len(DAC6)}
    mov dx,1
    push cs
    pop es
    mov di,colors
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

rm_fault:
    jmp rm_fault

bits 32
pm_entry:
    mov ax,10h
    mov ds,ax
    mov es,ax
    mov ss,ax
    lea esp,[ebp+stack_top]
    mov ebx,[ebp+lfb_base]
    cld
    mov edi,ebx
    mov eax,01010101h
.fill:
    mov ecx,65536/4
    rep stosd
    add eax,01010101h
    cmp eax,08080808h
    jb .fill
    lea edi,[ebp+results]
    call probe_lfb

pm_ready:
    cmp byte [ebp+pm_go],1
    jne pm_ready
    lea edi,[ebx+{MUTATIONS[0][0]}]
    mov al,{MUTATIONS[0][2]}
    mov ecx,{MUTATIONS[0][1]}
    rep stosb
    lea edi,[ebp+results+{len(PROBE_OFFSETS)}]
    call probe_lfb
pm_update_cut:
    cmp byte [ebp+pm_go],2
    jne pm_update_cut
    lea edi,[ebx+{MUTATIONS[1][0]}]
    mov al,{MUTATIONS[1][2]}
    mov ecx,{MUTATIONS[1][1]}
    rep stosb
    lea edi,[ebp+results+2*{len(PROBE_OFFSETS)}]
    call probe_lfb
pm_updated:
    cmp byte [ebp+pm_go],3
    jne pm_updated
    jmp far [ebp+return16]

probe_lfb:
    lea esi,[ebp+probe_offsets]
    mov ecx,{len(PROBE_OFFSETS)}
.next:
    lodsd
    mov al,[ebx+eax]
    stosb
    loop .next
    ret

bits 16
pm16_return:
    mov ax,20h
    mov ss,ax
    mov ds,ax
    mov es,ax
    mov eax,cr0
    and eax,0fffffffeh
    mov cr0,eax
    jmp far [cs:rm_jump]

rm_entry:
    mov ax,cs
    mov ds,ax
    mov es,ax
    mov ss,[saved_ss]
    movzx esp,word [saved_sp]
    sti
    mov ax,4f07h
    mov bx,80h
    mov cx,5
    mov dx,64
rm_pan_call:
    int 10h
    mov [mode_results+20],ax
    mov ax,4f07h
    mov bx,1
    int 10h
    mov [mode_results+22],ax
    mov [mode_results+24],cx
    mov [mode_results+26],dx
rm_panned:
    cmp byte [pm_go],4
    jne rm_panned
    mov ax,4f02h
    mov bx,8101h
    int 10h
    mov [mode_results+28],ax
    cmp ax,004fh
    jne rm_fault
    mov ax,4f03h
    int 10h
    mov [mode_results+30],ax
    mov [mode_results+32],bx
    mov ax,4f06h
    mov bx,2
    mov cx,{PITCH}
    int 10h
    cmp ax,004fh
    jne rm_fault
    call load_palette
    mov ax,0a000h
    mov es,ax
    xor dx,dx
    call select_bank
    mov al,[es:0ffffh]
    mov [results+3*{len(PROBE_OFFSETS)}],al
    mov dx,1
    call select_bank
    mov al,[es:0]
    mov [results+3*{len(PROBE_OFFSETS)}+1],al
    mov al,[es:0ffffh]
    mov [results+3*{len(PROBE_OFFSETS)}+2],al
    mov dx,2
    call select_bank
    mov al,[es:0]
    mov [results+3*{len(PROBE_OFFSETS)}+3],al
    xor dx,dx
    call select_bank
rm_banked:
    cmp byte [pm_go],5
    jne rm_banked
    mov ax,4c00h
    int 21h

select_bank:
    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,004fh
    jne rm_fault
    ret

align 8
gdt:
    dq 0
    dq 00cf9a000000ffffh
    dq 00cf92000000ffffh
cs16:
    dq 00009a000000ffffh
    dq 000092000000ffffh
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
pm_jump:
    dd 0
    dw 8
return16:
    dd pm16_return
    dw 18h
rm_jump:
    dw rm_entry,0
saved_ss: dw 0
saved_sp: dw 0
lfb_base: dd 0
pm_go: db 0
mode_info: times 256 db 0
mode_results: times 17 dw 0
results: times {RESULT_BYTES} db 0
colors: db {','.join(str(value) for color in DAC6 for value in (*color, 0))}
probe_offsets: dd {','.join(map(str, PROBE_OFFSETS))}
align 16
stack_space: times 768 db 0
stack_top:
db 'VLFB'
dw pm_ready, pm_update_cut, pm_updated, rm_pan_call, rm_panned
dw rm_banked, rm_fault, pm_go, mode_info, mode_results, lfb_base, results
'''


def labels(code):
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    assert code[footer:footer + 4] == b'VLFB'
    offsets = unpack_from(f'<{len(SYMBOLS)}H', code, footer + 4)
    return dict(zip(SYMBOLS, offsets, strict=True))


def mode_info(raw):
    assert len(raw) == MODE_INFO_BYTES
    pitch, width, height = unpack_from('<3H', raw, 0x10)
    return dict(attributes=unpack_from('<H', raw)[0], width=width, height=height,
                bits_per_pixel=raw[0x19], default_pitch=pitch,
                physical_base=unpack_from('<I', raw, 0x28)[0])


def mode_results(raw):
    return dict(zip(MODE_FIELDS, MODE_RESULTS.unpack(raw), strict=True))


def results(raw):
    assert len(raw) == RESULT_BYTES
    n = len(PROBE_OFFSETS)
    return dict(baseline=raw[:n], half=raw[n:2 * n], updated=raw[2 * n:3 * n], banked=raw[3 * n:])


def expected_vram(variant='baseline'):
    if variant not in VARIANTS:
        raise ValueError(f'Unknown linear framebuffer variant {variant}')
    backing = bytearray(b''.join(bytes([i]) * BANK_BYTES for i in range(1, 8)))
    assert len(backing) == BACKING_BYTES
    for offset, length, color in MUTATIONS[:VARIANTS.index(variant)]:
        backing[offset:offset + length] = bytes([color]) * length
    return bytes(backing)


def expected_rgb(variant='baseline', origin=0):
    backing = expected_vram(variant)
    assert 0 <= origin and origin + (HEIGHT - 1) * PITCH + WIDTH <= len(backing)
    channels = tuple(bytes([0, *(color[c] << 2 | color[c] >> 4 for color in DAC6)])
                     for c in (2, 1, 0))
    indices = b''.join(backing[pos:pos + WIDTH] for pos in range(origin, origin + HEIGHT * PITCH, PITCH))
    rgb = bytearray(len(indices) * 3)
    for c, lane in enumerate(channels):
        rgb[c::3] = indices.translate(lane.ljust(256, b'\0'))
    return bytes(rgb)
