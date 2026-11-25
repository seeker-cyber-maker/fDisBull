"""Authored protected-mode COM fixtures for atomic and null-DS #GP retry."""
from __future__ import annotations

from pathlib import Path
from struct import unpack_from

from support.dos_process_fixture import assemble

LOCK_OFFSET = 0xFFFE
LOCK_EXPECTED = 0x13579BDF
LOCK_REPLACEMENT = 0x2468ACE0
NULL_VALUE = 0x78563412
FAULT_EAX = 0xDEADBEEF
FAULT_MARKER_VALUE = 0x46504741
COMPLETION_MARKER_VALUE = 0x44454C41

_SOURCE = r"""
bits 16
%define PSP_PARAGRAPHS 0200h
%define BUFFER_PARAGRAPHS 01002h
%define LOCK_OFFSET 0FFFEh
%define LOCK_EXPECTED 13579BDFh
%define LOCK_REPLACEMENT 2468ACE0h
%define NULL_VALUE 78563412h
%define FAULT_EAX 0DEADBEEFh
%define FAULT_MARKER_VALUE 46504741h
%define COMPLETION_MARKER_VALUE 44454C41h
%define CASE_LOCK 1
org 100h
start:
    push cs
    pop ds
    mov ax,cs
    mov ss,ax
    mov sp,1800h
    mov es,ax
    mov bx,PSP_PARAGRAPHS
    mov ah,4ah
    int 21h
    jc allocation_failure
    mov bx,BUFFER_PARAGRAPHS
    mov ah,48h
    int 21h
    jc allocation_failure
    push cs
    pop ds
    mov [buffer_segment],ax
    movzx eax,ax
    shl eax,4
    mov [buffer_base],eax
    mov ax,cs
    movzx eax,ax
    shl eax,4
    mov [psp_base],eax
    mov eax,[psp_base]
    mov [gdt_code+2],ax
    shr eax,16
    mov [gdt_code+4],al
    mov [gdt_code+7],ah
    mov eax,[psp_base]
    mov [gdt_meta+2],ax
    shr eax,16
    mov [gdt_meta+4],al
    mov [gdt_meta+7],ah
    mov eax,[buffer_base]
    mov [gdt_buffer_wide+2],ax
    shr eax,16
    mov [gdt_buffer_wide+4],al
    mov [gdt_buffer_wide+7],ah
    mov eax,[buffer_base]
    mov [gdt_buffer_limited+2],ax
    shr eax,16
    mov [gdt_buffer_limited+4],al
    mov [gdt_buffer_limited+7],ah
    mov eax,[psp_base]
    add eax,gdt
    mov [gdtr+2],eax
    mov eax,[psp_base]
    add eax,idt
    mov [idtr+2],eax
    mov eax,gp_handler
    mov [idt+13*8],ax
    shr eax,16
    mov [idt+13*8+6],ax
    mov word [idt+13*8+2],8
    mov word [idt+13*8+4],8e00h
    mov dword [pm_jump],pm_entry
    cli
    lgdt [gdtr]
    mov eax,cr0
    or eax,1
    mov cr0,eax
    jmp dword far [pm_jump]

allocation_failure:
    jmp allocation_failure

bits 32
pm_entry:
    mov ax,10h
    mov ds,ax
    mov fs,ax
    mov ss,ax
    lea esp,[stack_top]
    lidt [idtr]
    mov ax,18h
    mov es,ax
%if CASE_LOCK
    mov dword [es:LOCK_OFFSET],LOCK_EXPECTED
%else
    mov dword [es:0],NULL_VALUE
%endif
    mov dword [fs:fault_marker],0
    mov dword [fs:completion_marker],0
pm_ready:
    nop
%if CASE_LOCK
    mov ax,20h
    mov ds,ax
    mov eax,LOCK_EXPECTED
    mov ebx,LOCK_REPLACEMENT
fault_ip:
    lock cmpxchg dword [LOCK_OFFSET],ebx
%else
    xor eax,eax
    mov ds,ax
    mov eax,FAULT_EAX
fault_ip:
    mov eax,[0]
%endif
fault_complete:
    mov [fs:final_eax],eax
    mov [fs:final_ebx],ebx
    pushfd
    pop edx
    mov [fs:final_eflags],edx
%if CASE_LOCK
    mov eax,[es:LOCK_OFFSET]
%else
    mov eax,[es:0]
%endif
    mov [fs:final_memory],eax
    mov ax,ds
    movzx eax,ax
    mov [fs:final_ds],eax
    mov dword [fs:completion_marker],COMPLETION_MARKER_VALUE
completion_stop:
    jmp completion_stop

gp_handler:
    cli
    mov [fs:fault_eax],eax
    mov [fs:fault_ebx],ebx
    mov eax,[esp]
    mov [fs:fault_error],eax
    mov eax,[esp+4]
    mov [fs:fault_eip],eax
    mov eax,[esp+8]
    mov [fs:fault_cs],eax
    mov eax,[esp+12]
    mov [fs:fault_eflags],eax
%if CASE_LOCK
    mov eax,[es:LOCK_OFFSET]
%else
    mov eax,[es:0]
%endif
    mov [fs:fault_memory],eax
    mov dword [fs:fault_marker],FAULT_MARKER_VALUE
    mov eax,[fs:fault_eax]
    mov dx,18h
    mov ds,dx
    add esp,4
    iretd

align 8
gdt:
    dq 0
gdt_code:
    dw 0ffffh,0
    db 0,09ah,040h,0
gdt_meta:
    dw 0ffffh,0
    db 0,092h,0cfh,0
gdt_buffer_wide:
    dw 0ffffh,0
    db 0,092h,0cfh,0
gdt_buffer_limited:
    dw 0ffffh,0
    db 0,092h,040h,0
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
pm_jump:
    dd 0
    dw 8
idtr:
    dw 14*8-1
    dd 0
idt:
    times 14*8 db 0
align 16
stack_space:
    times 512 db 0
stack_top:
psp_base:            dd 0
buffer_segment:      dw 0
buffer_base:         dd 0
fault_eax:           dd 0
fault_ebx:           dd 0
fault_error:         dd 0
fault_eip:           dd 0
fault_cs:            dd 0
fault_eflags:        dd 0
fault_memory:        dd 0
fault_marker:        dd 0
final_eax:           dd 0
final_ebx:           dd 0
final_eflags:        dd 0
final_memory:        dd 0
final_ds:            dd 0
completion_marker:   dd 0
 db 'ALF1'
 dw pm_ready, fault_ip, gp_handler, completion_stop
 dw buffer_base, fault_eax, fault_ebx, fault_error, fault_eip, fault_cs
 dw fault_eflags, fault_memory, fault_marker, final_eax, final_ebx
 dw final_eflags, final_memory, final_ds, completion_marker
"""

SYMBOLS = (
    "pm_ready", "fault_ip", "gp_handler", "completion_stop", "buffer_base",
    "fault_eax", "fault_ebx", "fault_error", "fault_eip", "fault_cs",
    "fault_eflags", "fault_memory", "fault_marker", "final_eax", "final_ebx",
    "final_eflags", "final_memory", "final_ds", "completion_marker",
)


def labels(code: bytes) -> dict[str, int]:
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    if code[footer:footer + 4] != b"ALF1":
        raise ValueError("Atomic limit fixture offset table is missing")
    return dict(zip(SYMBOLS, unpack_from(f"<{len(SYMBOLS)}H", code, footer + 4), strict=True))


def build(directory, nasm, *, case: str):
    if case not in ("lock", "null"):
        raise ValueError("case must be 'lock' or 'null'")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = _SOURCE.replace("%define CASE_LOCK 1", f"%define CASE_LOCK {int(case == 'lock')}", 1)
    code = assemble(directory, f"atomic-limit-{case}", source, nasm)
    return code, labels(code)
