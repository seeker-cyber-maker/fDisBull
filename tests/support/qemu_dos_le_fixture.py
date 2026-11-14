"""A tiny authored DOS loader for an explicit MZ/BW/MZ/LE carrier.

DOS executes the outer stub. It opens its own pathname from the standard DOS
PSP environment trailer and reads the complete carrier through INT21h. Its
actual protected-mode loader copies and relocates the two declared LE objects;
no host-side register or memory writes prepare the protected program.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from fdisbull.dos import load_mz
from fdisbull.le import load_runtime_le_carrier
from support.dos_process_fixture import assemble

CODE_BASE = 0x120000
DATA_BASE = 0x130000
OUTSIDE_BASE = 0x140000
COUNTER_OFFSET = 128
BUFFER_OFFSET = 0x1000


def build_fixture(directory, nasm):
    """Write authored source/listings and return the actual executable layout."""
    from test_le_loader import le_file
    from test_le_runtime_carrier import bound_le

    directory = Path(directory)
    # Eight distinct offset32 sites establish the initialized data placement.
    # The ninth site is an executed absolute store to a separate mutable cell.
    prefix = b''.join(b'\xb8'+bytes(4)+b'\x90'*3 for _ in range(8))
    body = bytes.fromhex('31c0 40 a300000000 83f803 75f5 ba') + struct.pack('<I', OUTSIDE_BASE) + b'\xff\xe2'
    code = prefix + body + bytes((i*73+19) % 256 for i in range(160))
    data = bytearray((i*37+11) % 256 for i in range(256))
    data[COUNTER_OFFSET:COUNTER_OFFSET+4] = bytes(4)
    sites = [(i*8+1, i) for i in range(8)] + [(68, COUNTER_OFFSET)]
    fixups = b''.join(struct.pack('<BBhBH', 7, 0, site, 2, target) for site, target in sites)
    carrier = bytearray(bound_le(le_file(code=code, data=bytes(data), fixups=[fixups, b''],
        object_sizes=(len(code), len(data)), object_bases=(0x10000, 0x20000))))
    parsed = load_runtime_le_carrier(bytes(carrier))
    fragments = parsed.metadata['file_mappings']
    code_file = next(row['file_offset'] for row in fragments if row['virtual_address']==0x10000)
    data_file = next(row['file_offset'] for row in fragments if row['virtual_address']==0x20000)
    patches = '\n'.join(f'    mov dword [{CODE_BASE+site:#x}],{DATA_BASE+target:#x}' for site, target in sites)
    source = f'''
bits 16
org 0
start:
    push cs
    pop ds
    mov ax,cs
    sub ax,0x10
    mov es,ax
    mov ax,[es:0x2c]
    test ax,ax
    jz failed
    mov es,ax
    xor di,di
    xor ax,ax
    cld
next_environment:
    mov cx,0x7fff
    repne scasb
    jne failed
    cmp byte [es:di],0
    jne next_environment
    inc di
    cmp word [es:di],1
    jb failed
    add di,2
    push ds
    push es
    pop ds
    mov dx,di
    mov ax,0x3d00
    int 0x21
    pop ds
    jc failed
    mov bx,ax
    mov dx,{BUFFER_OFFSET:#x}
    mov cx,{len(carrier)}
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,{len(carrier)}
    jne failed
    mov ah,0x3e
    int 0x21
    cli
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    xor ebp,ebp
    mov bp,cs
    shl ebp,4
    lea eax,[ebp+gdt]
    mov [gdtr+2],eax
    lea eax,[ebp+protected_entry]
    mov [protected_jump],eax
    lgdt [gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp dword far [protected_jump]
failed:
    mov ax,0x4c7f
    int 0x21
bits 32
protected_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov esp,0x180000
    cld
    lea esi,[ebp+{BUFFER_OFFSET+code_file:#x}]
    mov edi,{CODE_BASE:#x}
    mov ecx,{len(code)}
    rep movsb
    lea esi,[ebp+{BUFFER_OFFSET+data_file:#x}]
    mov edi,{DATA_BASE:#x}
    mov ecx,{len(data)}
    rep movsb
{patches}
    mov dword [{OUTSIDE_BASE:#x}],0x90feeb90
    mov eax,{CODE_BASE:#x}
    jmp eax
align 8
gdt:
    dq 0
    dq 0x00cf9a000000ffff
    dq 0x00cf92000000ffff
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
protected_jump:
    dd 0
    dw 8
'''
    bootstrap = assemble(directory, 'le-dos-bootstrap', source, nasm)
    if len(bootstrap)>448:
        raise ValueError('Authored DOS bootstrap exceeds the outer MZ module')
    carrier[64:512] = bootstrap.ljust(448, b'\0')
    # Outer declared end stays512: the runtime parser must find BW exactly there.
    # The additional allocation holds the self-read buffer and original stack.
    struct.pack_into('<H', carrier, 0x0a, (65536-448)//16)
    struct.pack_into('<H', carrier, 0x10, 0xfffe)
    target = directory/'LETRACE.EXE'
    target.write_bytes(carrier)
    classic = load_mz(bytes(carrier))
    runtime = load_runtime_le_carrier(bytes(carrier))
    if classic.metadata['dos'].get('secondary_format') is not None:
        raise ValueError('Authored carrier changed the classic MZ launch gate')
    if runtime.metadata['le']['carrier']['application_offset'] != 1024:
        raise ValueError('Authored carrier lost its declared BW linkage')
    assert runtime.regions[0].data[68:72] == struct.pack('<I', 0x20000+COUNTER_OFFSET)
    return dict(path=target, sha256=hashlib.sha256(carrier).hexdigest(), size=len(carrier),
        bootstrap_size=len(bootstrap), code_base=CODE_BASE, data_base=DATA_BASE,
        outside_base=OUTSIDE_BASE, counter_address=DATA_BASE+COUNTER_OFFSET,
        entry_offset=0, increment_offset=66, store_offset=67, outside_jump_offset=82,
        code_file_offset=code_file, data_file_offset=data_file,
        code_size=len(code), data_size=len(data), offset32_sites=sites,
        source_view='embedded-le', carrier='mz-bw-mz-le')
