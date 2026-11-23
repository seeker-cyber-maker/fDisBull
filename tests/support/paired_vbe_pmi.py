"""One authored DOS program for the copied VBE 2.0 protected-mode table."""

from struct import Struct, unpack_from


WIDTH = 640
HEIGHT = 480
PITCH = 648
BANK_BYTES = 65536
FIRST_COLOR = 1
ORIGIN = 64 * PITCH + 4
COPY_CAPACITY = 1024
QUERY = Struct('<4H')
TABLE = Struct('<4H')
QUERIES = 5
EXPECTED_BANK = bytes([1, 7, 1, 0x5B, 1])
DAC6 = bytes([57, 25, 39, 0xCC, 13, 61, 3, 0xDD, 14, 19, 11, 0,
              33, 11, 41, 0, 63, 2, 25, 0, 32, 1, 3, 0, 43, 2, 4, 0])
TIMED = bytes([19, 63, 1, 0xA2, 57, 3, 42, 0xB4])
EXPECTED_TIMED_RGB = bytes([1, 63, 19, 42, 3, 57])
SYMBOLS = (
    'pm_ready', 'pm_timed_call', 'pm_palette_return', 'pm_done',
    'pm_display_return', 'pm_flipped', 'pm_timed_start_call',
    'pm_timed_start_return', 'pm_restored', 'rm_done', 'pm_go',
    'pmi_copy', 'pmi_queries', 'pm_result', 'pm_status',
    'pm_palette_capture', 'rm_readback', 'rm_fault', 'pmi_startup',
)

# The copied routines execute with flat, 32-bit CS, DS, SS and ES. Only
# caller-owned 32-bit RAM supplies the entry code, palette and stack. The
# interface is first obtained through INT 10h in real mode.
SOURCE = r'''
bits 16
org 100h
    push cs
    pop ds
    mov ax,4f0ah
    xor bx,bx
    int 10h
    mov [pmi_startup],ax
    mov [pmi_startup+2],cx
    mov [pmi_startup+4],di
    mov [pmi_startup+6],es
    mov ax,4f02h
    mov bx,101h
    int 10h
    cmp ax,004fh
    jne rm_fault

    mov ax,4f06h
    mov bx,2
    mov cx,648
    int 10h
    cmp ax,004fh
    jne rm_fault
    cmp bx,648
    jne rm_fault
    mov ax,4f09h
    xor bx,bx
    mov cx,7
    mov dx,1
    push cs
    pop es
    mov di,initial_colors
    int 10h
    cmp ax,004fh
    jne rm_fault

    mov ax,0a000h
    mov es,ax
.fill_bank:
    mov ax,4f05h
    xor bx,bx
    mov dx,[bank]
    int 10h
    cmp ax,004fh
    jne rm_fault
    mov ax,[bank]
    inc al
    mov ah,al
    xor di,di
    mov cx,8000h
    cld
    rep stosw
    inc word [bank]
    cmp word [bank],7
    jb .fill_bank
    mov ax,4f05h
    xor bx,bx
    xor dx,dx
    int 10h
    cmp ax,004fh
    jne rm_fault

    mov byte [subfunction],0
.query:
    movzx bx,byte [subfunction]
    mov ax,4f0ah
    mov cx,0badh
    mov di,0cafeh
    push cs
    pop es
    int 10h
    movzx si,byte [subfunction]
    shl si,3
    mov [pmi_queries+si],ax
    mov [pmi_queries+si+2],cx
    mov [pmi_queries+si+4],di
    mov [pmi_queries+si+6],es
    inc byte [subfunction]
    cmp byte [subfunction],5
    jb .query

    cmp word [pmi_queries],004fh
    jne rm_fault
    mov cx,[pmi_queries+2]
    cmp cx,8
    jb rm_fault
    cmp cx,1024
    ja rm_fault
    mov si,[pmi_queries+4]
    mov ax,[pmi_queries+6]
    push ds
    mov ds,ax
    push cs
    pop es
    mov di,pmi_copy
    cld
    rep movsb
    pop ds

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

rm_fault:
    mov byte [pm_result],0ffh
    jmp rm_fault

bits 32
pm_entry:
    mov ax,10h
    mov ds,ax
    mov es,ax
    mov ss,ax
    lea esp,[ebp+stack_top]

    lea esi,[ebp+pmi_copy]
    xor ebx,ebx
.resolve:
    movzx eax,word [esi+ebx*2]
    add eax,esi
    mov [ebp+pm_functions+ebx*4],eax
    inc ebx
    cmp ebx,3
    jb .resolve

    ; Window A, bank 6 is outside the raster's sampled backing range.
    xor ebx,ebx
    mov edx,6
    call [ebp+pm_functions]
    mov al,[0a0020h]
    mov [ebp+pm_result+1],al
    mov byte [0a0020h],5bh
    xor ebx,ebx
    xor edx,edx
    call [ebp+pm_functions]
    mov al,[0a0020h]
    mov [ebp+pm_result+2],al
    xor ebx,ebx
    mov edx,6
    call [ebp+pm_functions]
    mov al,[0a0020h]
    mov [ebp+pm_result+3],al
    xor ebx,ebx
    xor edx,edx
    call [ebp+pm_functions]
    mov al,[0a0020h]
    mov [ebp+pm_result+4],al
    mov byte [ebp+pm_result],1

pm_ready:
    cmp byte [ebp+pm_go],1
    jne pm_ready

    mov dx,3dah
    in al,dx
    and al,9
    mov [ebp+pm_status],al
    mov ebx,80h
    mov ecx,2
    mov edx,1
    lea edi,[ebp+timed_colors]
pm_timed_call:
    call [ebp+pm_functions+8]
pm_palette_return:
    mov dx,3dah
    in al,dx
    and al,9
    mov [ebp+pm_status+1],al

    mov dx,3c7h
    mov al,1
    out dx,al
    mov dx,3c9h
    lea edi,[ebp+pm_palette_capture]
    mov ecx,6
.palette_read:
    in al,dx
    stosb
    loop .palette_read

pm_done:
    cmp byte [ebp+pm_go],2
    jne pm_done

    xor ebx,ebx
    mov ecx,(64*648+4)/4
    xor edx,edx
    call [ebp+pm_functions+4]
pm_display_return:
pm_flipped:
    cmp byte [ebp+pm_go],3
    jne pm_flipped

    mov dx,3dah
    in al,dx
    and al,9
    mov [ebp+pm_status+2],al
    mov ebx,80h
    xor ecx,ecx
    xor edx,edx
pm_timed_start_call:
    call [ebp+pm_functions+4]
pm_timed_start_return:
    mov dx,3dah
    in al,dx
    and al,9
    mov [ebp+pm_status+3],al

pm_restored:
    cmp byte [ebp+pm_go],4
    jne pm_restored
    jmp far [ebp+return16]

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
    mov bx,1
    int 10h
    mov [rm_readback],ax
    mov [rm_readback+2],cx
    mov [rm_readback+4],dx
rm_done:
    mov ax,4c00h
    int 21h

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
bank: dw 0
subfunction: db 0
pm_go: db 0
pm_result: times 5 db 0
pm_status: times 4 db 0
pm_palette_capture: times 6 db 0
rm_readback: times 3 dw 0
pmi_queries: times 20 dw 0
pmi_startup: times 4 dw 0
pm_functions: times 3 dd 0
initial_colors: db @INITIAL@
timed_colors: db @TIMED@
align 16
pmi_copy: times 1024 db 0
align 16
stack_space: times 768 db 0
stack_top:
db 'VPMI'
dw pm_ready, pm_timed_call, pm_palette_return, pm_done, pm_display_return, pm_flipped
dw pm_timed_start_call, pm_timed_start_return, pm_restored, rm_done, pm_go
dw pmi_copy, pmi_queries, pm_result, pm_status, pm_palette_capture, rm_readback, rm_fault
dw pmi_startup
'''.replace('@INITIAL@', ','.join(map(str, DAC6))).replace('@TIMED@', ','.join(map(str, TIMED)))


def labels(code):
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    assert code[footer:footer + 4] == b'VPMI'
    offsets = unpack_from(f'<{len(SYMBOLS)}H', code, footer + 4)
    return dict(zip(SYMBOLS, offsets, strict=True))


def query_records(raw, copied, startup=None):
    reports = tuple(QUERY.iter_unpack(raw))
    assert len(reports) == QUERIES
    status, length, pointer, segment = reports[0]
    assert status == 0x004F and len(copied) == length and segment and pointer
    window, start, palette, ports = TABLE.unpack_from(copied)
    assert 8 <= window < start < palette < length <= COPY_CAPACITY
    assert ports == 0 or 8 <= ports < window or palette < ports < length
    end = ports if ports > palette else length
    for record, entry, finish in zip(reports[1:4], (window, start, palette), (start, palette, end),
                                     strict=True):
        assert record == (0x004F, finish - entry, pointer + entry, segment)
    assert reports[4][0] == 0x014F
    if startup is not None:
        assert QUERY.unpack(startup) == reports[0]
    return dict(status=status, length=length, rom_segment=segment, rom_offset=pointer, window=window,
                start=start, palette=palette, ports=ports, entries=[record[0] for record in reports])


def expected_rgb(origin=0, changed=False):
    palette = list(DAC6)
    if changed:
        palette[:len(TIMED)] = TIMED

    def expand(value):
        return (value << 2) | (value >> 4)

    backing = b''.join(bytes(expand(channel) for channel in reversed(palette[i:i + 3])) * BANK_BYTES
                       for i in range(0, len(palette), 4))
    assert 0 <= origin and origin + (HEIGHT - 1) * PITCH + WIDTH <= len(backing) // 3
    return b''.join(backing[pos * 3:(pos + WIDTH) * 3]
                    for pos in range(origin, origin + HEIGHT * PITCH, PITCH))
