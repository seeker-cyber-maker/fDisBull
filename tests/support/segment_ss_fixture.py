"""Authored protected-mode COM probes for SS-limit #SS and an in-range control."""
from __future__ import annotations

from pathlib import Path
from struct import unpack_from

from support.dos_process_fixture import assemble

SS_LIMIT = 0x1FFF
STACK_POINTER = 0x1800
FAULT_OFFSET = 0x2100
CONTROL_OFFSET = 0x1000
TARGET_VALUE = 0x5AA51234
FAULT_MARKER_VALUE = 0x46535346
COMPLETION_MARKER_VALUE = 0x44435346
INITIAL_REGISTERS = {
    "eax": 0x11223344,
    "ebx": 0x22334455,
    "ecx": 0x33445566,
    "edx": 0x44556677,
    "esi": 0x55667788,
    "edi": 0x66778899,
}

_SOURCE = r"""
bits 16
%define PSP_PARAGRAPHS 0200h
%define BUFFER_PARAGRAPHS 01002h
%define SS_LIMIT 01fffh
%define STACK_POINTER 01800h
%define FAULT_OFFSET 02100h
%define CONTROL_OFFSET 01000h
%define TARGET_VALUE 5aa51234h
%define FAULT_MARKER_VALUE 46535346h
%define COMPLETION_MARKER_VALUE 44435346h
%define FAULTING 1
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
    mov [gdt_data+2],ax
    shr eax,16
    mov [gdt_data+4],al
    mov [gdt_data+7],ah
    mov eax,[psp_base]
    mov [gdt_small_stack+2],ax
    shr eax,16
    mov [gdt_small_stack+4],al
    mov [gdt_small_stack+7],ah
    mov eax,[psp_base]
    add eax,gdt
    mov [gdtr+2],eax
    mov eax,[psp_base]
    add eax,idt
    mov [idtr+2],eax
    mov eax,ss_handler
    mov [idt+12*8],ax
    shr eax,16
    mov [idt+12*8+6],ax
    mov word [idt+12*8+2],8
    mov word [idt+12*8+4],8e00h
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
    mov es,ax
    mov ss,ax
    mov esp,STACK_POINTER
    lidt [idtr]
%if FAULTING
    mov dword [ds:FAULT_OFFSET],TARGET_VALUE
    mov ebp,FAULT_OFFSET
%else
    mov dword [ds:CONTROL_OFFSET],TARGET_VALUE
    mov ebp,CONTROL_OFFSET
%endif
    mov dword [fs:fault_marker],0
    mov dword [fs:completion_marker],0
    mov ax,18h
    mov ss,ax
    mov eax,11223344h
    mov ebx,22334455h
    mov ecx,33445566h
    mov edx,44556677h
    mov esi,55667788h
    mov edi,66778899h
    mov [fs:pre_eax],eax
    mov [fs:pre_ebx],ebx
    mov [fs:pre_ecx],ecx
    mov [fs:pre_edx],edx
    mov [fs:pre_esi],esi
    mov [fs:pre_edi],edi
    mov [fs:pre_ebp],ebp
    mov [fs:pre_esp],esp
    push 0003h
    popfd
    pushfd
    pop dword [fs:pre_eflags]
ss_ready:
    nop
arm_stop:
    nop
fault_ip:
    mov eax,[ebp]
read_complete:
    mov [fs:final_eax],eax
    mov [fs:final_ebx],ebx
    mov [fs:final_ecx],ecx
    mov [fs:final_edx],edx
    mov [fs:final_esi],esi
    mov [fs:final_edi],edi
    mov [fs:final_ebp],ebp
    mov [fs:final_esp],esp
    pushfd
    pop dword [fs:final_eflags]
%if FAULTING
    mov eax,[ds:FAULT_OFFSET]
%else
    mov eax,[ds:CONTROL_OFFSET]
%endif
    mov [fs:final_memory],eax
    mov ax,ss
    movzx eax,ax
    mov [fs:final_ss],eax
    mov dword [fs:completion_marker],COMPLETION_MARKER_VALUE
completion_stop:
    jmp completion_stop

ss_handler:
    cli
    mov [fs:fault_eax],eax
    mov [fs:fault_ebx],ebx
    mov [fs:fault_ecx],ecx
    mov [fs:fault_edx],edx
    mov [fs:fault_esi],esi
    mov [fs:fault_edi],edi
    mov [fs:fault_ebp],ebp
    lea eax,[esp+16]
    mov [fs:fault_esp],eax
    mov eax,[esp]
    mov [fs:fault_error],eax
    mov eax,[esp+4]
    mov [fs:fault_eip],eax
    mov eax,[esp+8]
    mov [fs:fault_cs],eax
    mov eax,[esp+12]
    mov [fs:fault_eflags],eax
%if FAULTING
    mov eax,[ds:FAULT_OFFSET]
%else
    mov eax,[ds:CONTROL_OFFSET]
%endif
    mov [fs:fault_memory],eax
    mov ax,ss
    movzx eax,ax
    mov [fs:fault_ss],eax
    mov dword [fs:fault_marker],FAULT_MARKER_VALUE
    mov ax,10h
    mov ss,ax
    mov eax,[fs:pre_eax]
    mov ebx,[fs:pre_ebx]
    mov ecx,[fs:pre_ecx]
    mov edx,[fs:pre_edx]
    mov esi,[fs:pre_esi]
    mov edi,[fs:pre_edi]
    mov ebp,[fs:pre_ebp]
    add esp,4
    iretd

align 8
gdt:
    dq 0
gdt_code:
    dw 0ffffh,0
    db 0,09ah,040h,0
gdt_data:
    dw 0ffffh,0
    db 0,092h,0cfh,0
gdt_small_stack:
    dw SS_LIMIT,0
    db 0,092h,040h,0
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
pm_jump:
    dd 0
    dw 8
idtr:
    dw 13*8-1
    dd 0
idt:
    times 13*8 db 0
align 16
psp_base:            dd 0
buffer_segment:      dw 0
buffer_base:         dd 0
pre_eax:             dd 0
pre_ebx:             dd 0
pre_ecx:             dd 0
pre_edx:             dd 0
pre_esi:             dd 0
pre_edi:             dd 0
pre_ebp:             dd 0
pre_esp:             dd 0
pre_eflags:          dd 0
fault_eax:           dd 0
fault_ebx:           dd 0
fault_ecx:           dd 0
fault_edx:           dd 0
fault_esi:           dd 0
fault_edi:           dd 0
fault_ebp:           dd 0
fault_esp:           dd 0
fault_error:         dd 0
fault_eip:           dd 0
fault_cs:            dd 0
fault_eflags:        dd 0
fault_memory:        dd 0
fault_ss:            dd 0
fault_marker:        dd 0
final_eax:           dd 0
final_ebx:           dd 0
final_ecx:           dd 0
final_edx:           dd 0
final_esi:           dd 0
final_edi:           dd 0
final_ebp:           dd 0
final_esp:           dd 0
final_eflags:        dd 0
final_memory:        dd 0
final_ss:            dd 0
completion_marker:   dd 0
 db 'SSF1'
 dw ss_ready, arm_stop, fault_ip, read_complete, ss_handler, completion_stop
 dw buffer_base
 dw pre_eax, pre_ebx, pre_ecx, pre_edx, pre_esi, pre_edi, pre_ebp, pre_esp, pre_eflags
 dw fault_eax, fault_ebx, fault_ecx, fault_edx, fault_esi, fault_edi, fault_ebp
 dw fault_esp, fault_error, fault_eip, fault_cs, fault_eflags, fault_memory, fault_ss, fault_marker
 dw final_eax, final_ebx, final_ecx, final_edx, final_esi, final_edi, final_ebp, final_esp
 dw final_eflags, final_memory, final_ss, completion_marker
"""

SYMBOLS = (
    "ss_ready", "arm_stop", "fault_ip", "read_complete", "ss_handler", "completion_stop",
    "buffer_base", "pre_eax", "pre_ebx", "pre_ecx", "pre_edx", "pre_esi", "pre_edi",
    "pre_ebp", "pre_esp", "pre_eflags", "fault_eax", "fault_ebx", "fault_ecx",
    "fault_edx", "fault_esi", "fault_edi", "fault_ebp", "fault_esp", "fault_error",
    "fault_eip", "fault_cs", "fault_eflags", "fault_memory", "fault_ss", "fault_marker",
    "final_eax", "final_ebx", "final_ecx", "final_edx", "final_esi", "final_edi",
    "final_ebp", "final_esp", "final_eflags", "final_memory", "final_ss",
    "completion_marker",
)


def labels(code: bytes) -> dict[str, int]:
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    if code[footer:footer + 4] != b"SSF1":
        raise ValueError("SS-limit fixture offset table is missing")
    return dict(zip(SYMBOLS, unpack_from(f"<{len(SYMBOLS)}H", code, footer + 4), strict=True))


def build(directory, nasm, *, faulting: bool):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = _SOURCE.replace("%define FAULTING 1", f"%define FAULTING {int(faulting)}", 1)
    code = assemble(directory, f"segment-ss-{'fault' if faulting else 'control'}", source, nasm)
    return code, labels(code)
