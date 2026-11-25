"""Authored protected-mode COM probe for a read-only DS store fault."""
from __future__ import annotations

from pathlib import Path
from struct import unpack_from

from support.dos_process_fixture import assemble

STORE_OFFSET = 0x100
INITIAL_VALUE = 0x13579BDF
STORE_VALUE = 0x2468ACE0
FAULT_EAX = 0xDEADBEEF
FAULT_MARKER_VALUE = 0x46504752
COMPLETION_MARKER_VALUE = 0x44454C52

_SOURCE = r"""
bits 16
%define PSP_PARAGRAPHS 0200h
%define BUFFER_PARAGRAPHS 01002h
%define STORE_OFFSET 0100h
%define INITIAL_VALUE 13579BDFh
%define STORE_VALUE 2468ACE0h
%define FAULT_EAX 0DEADBEEFh
%define FAULT_MARKER_VALUE 46504752h
%define COMPLETION_MARKER_VALUE 44454C52h
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
    mov [gdt_buffer_readonly+2],ax
    shr eax,16
    mov [gdt_buffer_readonly+4],al
    mov [gdt_buffer_readonly+7],ah
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
    mov dword [es:STORE_OFFSET],INITIAL_VALUE
    mov dword [fs:fault_marker],0
    mov dword [fs:completion_marker],0
pm_ready:
    nop
    mov ax,20h
    mov ds,ax
    mov eax,FAULT_EAX
store_ip:
    mov dword [STORE_OFFSET],STORE_VALUE
store_complete:
    mov dword [fs:final_value],STORE_VALUE
    mov eax,[es:STORE_OFFSET]
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
    mov eax,[esp]
    mov [fs:fault_error],eax
    mov eax,[esp+4]
    mov [fs:fault_eip],eax
    mov eax,[esp+8]
    mov [fs:fault_cs],eax
    mov eax,[esp+12]
    mov [fs:fault_eflags],eax
    mov eax,[es:STORE_OFFSET]
    mov [fs:fault_memory],eax
    mov ax,ds
    movzx eax,ax
    mov [fs:fault_ds],eax
    mov dword [fs:fault_marker],FAULT_MARKER_VALUE
    mov ax,18h
    mov ds,ax
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
gdt_buffer_readonly:
    dw 0ffffh,0
    db 0,090h,040h,0
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
fault_error:         dd 0
fault_eip:           dd 0
fault_cs:            dd 0
fault_eflags:        dd 0
fault_memory:        dd 0
fault_ds:            dd 0
fault_marker:        dd 0
final_value:         dd 0
final_memory:        dd 0
final_ds:            dd 0
completion_marker:   dd 0
 db 'SRF1'
 dw pm_ready, store_ip, gp_handler, completion_stop
 dw buffer_base, fault_eax, fault_error, fault_eip, fault_cs, fault_eflags
 dw fault_memory, fault_ds, fault_marker, final_value, final_memory, final_ds
 dw completion_marker
"""

SYMBOLS = (
    "pm_ready", "store_ip", "gp_handler", "completion_stop", "buffer_base",
    "fault_eax", "fault_error", "fault_eip", "fault_cs", "fault_eflags",
    "fault_memory", "fault_ds", "fault_marker", "final_value", "final_memory",
    "final_ds", "completion_marker",
)


def labels(code: bytes) -> dict[str, int]:
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    if code[footer:footer + 4] != b"SRF1":
        raise ValueError("Segment-rights fixture offset table is missing")
    return dict(zip(SYMBOLS, unpack_from(f"<{len(SYMBOLS)}H", code, footer + 4), strict=True))


def build(directory, nasm):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    code = assemble(directory, "segment-rights-ro-ds-write", _SOURCE, nasm)
    return code, labels(code)
