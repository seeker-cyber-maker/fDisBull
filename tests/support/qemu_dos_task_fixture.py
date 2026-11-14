"""Authored DOS VM86 monitor with two page-table-isolated software tasks.

Both tasks use the same PSP, virtual CS:IP, and stack addresses. Their initial
DOS pages are copied once to distinct extended RAM banks before paging starts;
subsequent task switches copy only the interrupt return frame, never page banks.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from test_qemu_dos_modes_checkpoint_native import _SOURCE as _MODE_SOURCE

BANK_A = 0x110000
BANK_B = 0x130000
BANK_PAGES = 18
ANCHOR = 0x150000
MONITOR_UUID = "00112233445566778899aabbccddeeff"


def task_mz(data, marker):
    """Wrap the ORG-100h authored monitor as a no-relocation DOS MZ.

    Padding preserves the assembled label offsets relative to the load CS;
    the loader supplies a separate PSP and a 64-KiB stack allocation.
    """
    module = bytes(0x100) + data
    header = bytearray(32)
    total = len(header) + len(module)
    struct.pack_into('<14H', header, 0, 0x5a4d, total % 512, (total + 511) // 512,
                     0, 2, 0x1000, 0xffff, 0, 0xfffe, 0, 0x100, 0, 0x1c, 0)
    return bytes(header) + module, {key: value + 0x100 for key, value in marker.items()}


def _replace(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('DOS mode fixture changed; task fixture needs review')
    return source.replace(old, new, 1)


def task_fixture(directory, nasm, *, recreate_a=False):
    source = _MODE_SOURCE
    source = _replace(source, "dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$",
                      "dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$, flags_observed - $$")
    source = _replace(source, "mode_ready:\n    nop\nfetch_site:\n    nop",
                      "mode_ready:\n    nop\n    stc\nfetch_site:\n    nop\n    pushf\n    pop ax\n    and ax,1\n    mov [cs:flags_observed],ax")
    source = _replace(source, "scratch: dw 0", "scratch: dw 0\nflags_observed: dw 0xffff")
    source = _replace(source, '    mov cr3,edi\n    mov eax,cr0', r'''
    ; Enable the fast A20 gate without asserting the reset bit.
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    ; Two independent page directories and 4 MiB identity maps.
    lea ebx,[esi+4096]       ; directory B
    lea edx,[esi+8192]       ; table B
    mov eax,edx
    or eax,7
    mov [ebx],eax
    push edi
    push esi
    mov edi,ebx
    add edi,4
    xor eax,eax
    mov ecx,1023
    rep stosd
    pop esi
    pop edi
    push edi
    push esi
    mov edi,edx
    mov ecx,1024
    rep movsd
    pop esi
    pop edi
    mov [ebp+directory_a],edi
    mov [ebp+directory_b],ebx
    ; Start one page before the PSP page: includes the owning MCB and
    ; covers the entire 64 KiB segment even when the PSP is unaligned.
    mov eax,ebp
    and eax,0xfffff000
    sub eax,4096
    mov [ebp+region_start],eax
    mov ecx,eax
    shr ecx,12
    lea edi,[esi+ecx*4]
    lea edx,[edx+ecx*4]
    mov eax,0x110007
    mov ebx,0x130007
    mov ecx,18
map_banks:
    mov [edi],eax
    mov [edx],ebx
    add eax,4096
    add ebx,4096
    add edi,4
    add edx,4
    loop map_banks
    ; Copy the initial pages once, before either task executes.
    mov esi,[ebp+region_start]
    mov edi,0x110000
    mov ecx,18*1024
    rep movsd
    mov esi,[ebp+region_start]
    mov edi,0x130000
    mov ecx,18*1024
    rep movsd
    ; Global scheduler anchor: FDBTASK1, authored monitor UUID, even
    ; sequence, cookie, incarnation, active state, zero reserved.
    mov dword [0x150000],0x54424446
    mov dword [0x150004],0x314b5341
    mov dword [0x150008],0x33221100
    mov dword [0x15000c],0x77665544
    mov dword [0x150010],0xbbaa9988
    mov dword [0x150014],0xffeeddcc
    mov dword [0x150018],0
    mov dword [0x15001c],0
    mov dword [0x150020],0xa1
    mov dword [0x150024],0
    mov dword [0x150028],1
    mov dword [0x15002c],0
    mov dword [0x150030],1
    mov dword [0x150034],0
    mov dword [0x150040],0
    mov edi,[ebp+directory_a]
    mov cr3,edi
    mov eax,cr0''')
    source = _replace(source, '''    mov cx,2
hook_site:
    nop
    inc word [cs:scratch]
    loop hook_site
%if MODE_V86
    mov eax,cr0               ; VM86 #GP enters authored monitor below''', '''hook_site:
    nop
    inc word [cs:scratch]
%if MODE_V86
    mov eax,cr0               ; #GP switches A -> B -> A, then exits
    jmp mode_ready
%if 0
    mov eax,cr0
%endif''')
    source = _replace(source, '''gp_handler:
    cli
%if MODE_PAGING''', '''gp_handler:
    cli
    pushad
    mov ax,0x10
    mov ds,ax
    mov es,ax
    inc dword [0x150040]
    cmp dword [0x150040],3
    jae task_exit
    ; #GP is a fault: resume after the three-byte MOV EAX,CR0.
    add dword [esp+36],3
    ; Preserve only the CPU's VM86 interrupt frame across the CR3 change.
    mov esi,esp
    mov edi,0x150100
    mov ecx,20
    rep movsd
    inc dword [0x150018]     ; odd while scheduler state changes
    cmp dword [0x150040],1
    jne task_to_a
    mov dword [0x150020],0xb2
    mov dword [0x150028],2
    mov eax,[ebp+directory_b]
    jmp task_switch
 task_to_a:
    mov dword [0x150020],0xa1
    mov dword [0x150028],1
    mov eax,[ebp+directory_a]
 task_switch:
    mov cr3,eax
    inc dword [0x150018]     ; even after selected task is stable
    mov esi,0x150100
    mov edi,esp
    mov ecx,20
    rep movsd
    popad
    add esp,4                 ; discard #GP error code
    iretd
 task_exit:
    popad
%if MODE_PAGING''')
    if recreate_a:
        # Same architectural task context and cookie, but a new lifetime.
        source = _replace(source, " task_to_a:\n    mov dword [0x150020],0xa1\n    mov dword [0x150028],1",
                          " task_to_a:\n    mov dword [0x150020],0xa1\n    mov dword [0x150028],3")
    source = _replace(source, 'page_table_ptr: dd 0', '''page_table_ptr: dd 0
region_start: dd 0
directory_a: dd 0
directory_b: dd 0''')
    source = _replace(source, 'page_buffers: times 12288 db 0',
                      'page_buffers: times 20480 db 0')
    data = assemble(directory, 'task-switch',
                    '%define MODE_V86 1\n%define MODE_PAGING 1\n' + source, nasm)
    marker = data.index(b'FMOD')
    ready, hook, fetch, scratch, gp, ret, pm, pt = struct.unpack_from('<8H', data, marker + 4)
    flags, = struct.unpack_from('<H', data, marker + 20)
    return data, dict(ready=ready, hook=hook, fetch=fetch, scratch=scratch,
                      flags=flags, gp=gp, ret=ret, pm=pm, pt=pt)
