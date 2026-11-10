"""Bare-metal 486 paging witness; no DOS, QEMM, or vendor payloads."""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


def paging_aba_boot(directory, nasm):
    """Return a boot image and addresses for three stopped A/B/A observations.

    The guest independently writes two different physical sentinels, installs
    a real 386 page directory/table, and changes one PTE with INVLPG. Each
    marker follows a load through the remapped linear address and stores that
    result into identity-mapped RAM. The physical sentinels are never changed
    after initialization. Marker addresses are linear and physical because
    the boot code remains identity mapped.
    """
    sector = assemble(directory, 'paging-aba-boot', r'''
bits 16
org 0x7c00
    jmp short start
    nop
    db 'PABA'
    dd marker_a, marker_b, marker_a_again

start:
    cli
    xor ax,ax
    mov ds,ax
    mov ss,ax
    mov sp,0x7c00
    ; Enable the fast A20 gate before touching RAM above one MiB.
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    lgdt [gdtr]
    mov eax,cr0
    or eax,1
    mov cr0,eax
    jmp 0x08:protected

bits 32
protected:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov esp,0x9000
    cld
    ; Clear page directory and table at 0x10000 and 0x11000.
    xor eax,eax
    mov edi,0x10000
    mov ecx,2048
    rep stosd
    mov dword [0x10000],0x11003
    mov edi,0x11000
    mov eax,3
    mov ecx,1024
.identity:
    stosd
    add eax,0x1000
    loop .identity
    mov dword [0x200000],0x13579bdf
    mov dword [0x201000],0x2468ace0
    ; Linear 0x300000 is page-table index 768, at PTE 0x11c00.
    mov dword [0x11c00],0x200003
    mov eax,0x10000
    mov cr3,eax
    mov eax,cr0
    or eax,0x80000000
    mov cr0,eax
    jmp short .paging
.paging:
    mov eax,[0x300000]
    mov [0x6000],eax
marker_a:
    nop
    mov dword [0x11c00],0x201003
    invlpg [0x300000]
    mov eax,[0x300000]
    mov [0x6004],eax
marker_b:
    nop
    mov dword [0x11c00],0x200003
    invlpg [0x300000]
    mov eax,[0x300000]
    mov [0x6008],eax
marker_a_again:
    nop
.done:
    jmp .done

align 8
gdt:
    dq 0
    dq 0x00cf9a000000ffff
    dq 0x00cf92000000ffff
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd gdt
times 510-($-$$) db 0
dw 0xaa55
''', nasm)
    if len(sector) != 512 or sector[3:7] != b'PABA' or sector[-2:] != b'\x55\xaa':
        raise ValueError('Invalid authored paging witness boot sector')
    markers = struct.unpack_from('<III', sector, 7)
    if not all(0x7c00 <= value < 0x7e00 for value in markers):
        raise ValueError('Paging witness marker outside boot sector')
    return sector.ljust(1440 * 1024, b'\0'), {
        'markers': markers,
        'linear_address': 0x300000,
        'page_directory': 0x10000,
        'pte_address': 0x11c00,
        'backing_a': 0x200000,
        'backing_b': 0x201000,
        'sentinel_a': 0x13579bdf,
        'sentinel_b': 0x2468ace0,
        'observation_addresses': (0x6000, 0x6004, 0x6008),
    }
