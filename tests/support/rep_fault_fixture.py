"""Authored real-mode COM that faults partway through protected-mode REP MOVSB.

The program creates same-base wide and 64 KiB data descriptors. REP MOVSB
copies two bytes at ESI=FFFEh through the limited DS selector, then raises #GP
at ESI=10000h. The handler records the CPU frame, live registers and copied
prefix, loads the wide DS selector, and IRETD to retry the REP instruction.
After the remaining two bytes copy, the program writes a completion marker and
parks in protected mode for an external debugger.
"""
from __future__ import annotations

from pathlib import Path
from struct import unpack_from

from support.dos_process_fixture import assemble


SOURCE_BYTES = b"ABCD"
DESTINATION_OFFSET = 0x2000
INITIAL_ECX = 4
CODE_SELECTOR = 0x08
WIDE_DATA_SELECTOR = 0x18
LIMITED_DATA_SELECTOR = 0x20
METADATA_SELECTOR = 0x10
PSP_PARAGRAPHS = 0x0200
BUFFER_PARAGRAPHS = 0x1002
FAULT_ECX = 2
FAULT_ESI = 0x10000
FAULT_EDI = DESTINATION_OFFSET + 2
COMPLETED_ECX = 0
COMPLETED_ESI = 0x10002
COMPLETED_EDI = DESTINATION_OFFSET + 4
FAULT_PREFIX_DWORD = int.from_bytes(b"AB\0\0", "little")
FAULT_MARKER_VALUE = 0x46504752  # "RGPF" in little-endian memory
COMPLETION_MARKER_VALUE = 0x44455052  # "RPED" in little-endian memory


_SOURCE = r"""
bits 16
%define DESTINATION_OFFSET 2000h
%ifndef CHECKPOINT_PSP_BUFFER
%define PSP_PARAGRAPHS 0200h
%define BUFFER_PARAGRAPHS 01002h
%endif
%define INITIAL_ECX 4
%define FAULT_MARKER_VALUE 46504752h
%define COMPLETION_MARKER_VALUE 44455052h
org 100h
start:
    push cs
    pop ds
    mov ax,cs
    mov ss,ax
    mov sp,1800h

%ifdef CHECKPOINT_PSP_BUFFER
    ; Checkpoint-safe variant: keep the DOS EXEC-owned PSP MCB unchanged and
    ; use its existing allocation as the source/destination buffer base.
    mov [buffer_segment],ax
    movzx eax,ax
    shl eax,4
    mov [buffer_base],eax
%else
    ; Keep the COM code, GDT, IDT, metadata and stack in an 8 KiB PSP block.
    mov es,ax
    mov bx,PSP_PARAGRAPHS
    mov ah,4ah
    int 21h
    jc allocation_failure

    ; A distinct DOS-owned buffer covers offsets FFFE through 10001h.
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
%endif

    mov ax,cs
    movzx eax,ax
    shl eax,4
    mov [psp_base],eax

    ; Code and metadata/stack descriptors use the PSP base.
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

    ; Wide and limited descriptors share the selected buffer base.
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
    mov ax,10h                 ; PSP-based metadata and stack
    mov ds,ax
    mov fs,ax
    mov ss,ax
    lea esp,[stack_top]
    lidt [idtr]

    mov ax,18h                 ; buffer with wide data limit
    mov es,ax
    mov dword [es:0fffeh],44434241h
    mov dword [es:DESTINATION_OFFSET],0
    mov dword [fs:fault_marker],0
    mov dword [fs:completion_marker],0

pm_ready:
    nop
    cld
    mov ax,20h                 ; same allocated base, exact FFFFh limit
    mov ds,ax
    mov esi,0fffeh
    mov edi,DESTINATION_OFFSET
    mov ecx,INITIAL_ECX
rep_ip:
    rep movsb

rep_complete:
    mov [fs:final_ecx],ecx
    mov [fs:final_esi],esi
    mov [fs:final_edi],edi
    mov dword [fs:completion_marker],COMPLETION_MARKER_VALUE
completion_stop:
    jmp completion_stop

; #GP pushes error code, EIP, CS and EFLAGS for this ring-0 interrupt gate.
gp_handler:
    cli
    mov eax,[esp]
    mov [fs:fault_error],eax
    mov eax,[esp+4]
    mov [fs:fault_eip],eax
    mov eax,[esp+8]
    mov [fs:fault_cs],eax
    mov eax,[esp+12]
    mov [fs:fault_eflags],eax
    mov [fs:fault_ecx],ecx
    mov [fs:fault_esi],esi
    mov [fs:fault_edi],edi
    mov eax,[es:DESTINATION_OFFSET]
    mov [fs:fault_destination],eax
    mov dword [fs:fault_marker],FAULT_MARKER_VALUE

    mov ax,18h                 ; widen DS without changing ESI
    mov ds,ax
    add esp,4                  ; discard the 32-bit #GP error code
    iretd                      ; retry at the saved REP EIP

align 8
gdt:
    dq 0
gdt_code:
    dw 0ffffh,0
    db 0,09ah,040h,0          ; PSP base, 32-bit code, exact FFFFh limit
gdt_meta:
    dw 0ffffh,0
    db 0,092h,0cfh,0          ; PSP base, wide data/stack/metadata
gdt_buffer_wide:
    dw 0ffffh,0
    db 0,092h,0cfh,0          ; buffer base, wide data
gdt_buffer_limited:
    dw 0ffffh,0
    db 0,092h,040h,0          ; buffer base, exact FFFFh limit, D/B=1
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
fault_error:         dd 0
fault_eip:           dd 0
fault_cs:            dd 0
fault_eflags:        dd 0
fault_ecx:           dd 0
fault_esi:           dd 0
fault_edi:           dd 0
fault_destination:   dd 0
fault_marker:        dd 0
final_ecx:           dd 0
final_esi:           dd 0
final_edi:           dd 0
completion_marker:   dd 0

 db 'RPF1'
 dw rep_ip, rep_complete, gp_handler, completion_stop, pm_ready, allocation_failure
 dw fault_error, fault_eip, fault_cs, fault_eflags
 dw fault_ecx, fault_esi, fault_edi, fault_destination, fault_marker
 dw final_ecx, final_esi, final_edi, completion_marker, buffer_segment, buffer_base
 dw DESTINATION_OFFSET
"""

SYMBOLS = (
    "rep_ip", "rep_complete", "gp_handler", "completion_stop", "pm_ready", "allocation_failure",
    "fault_error", "fault_eip", "fault_cs", "fault_eflags",
    "fault_ecx", "fault_esi", "fault_edi", "fault_destination", "fault_marker",
    "final_ecx", "final_esi", "final_edi", "completion_marker",
    "buffer_segment", "buffer_base", "destination_offset",
)


def labels(code: bytes) -> dict[str, int]:
    """Read the authored offset table appended to the COM fixture."""
    footer = len(code) - 4 - 2 * len(SYMBOLS)
    if code[footer:footer + 4] != b"RPF1":
        raise ValueError("REP fault fixture offset table is missing")
    return dict(zip(SYMBOLS, unpack_from(f"<{len(SYMBOLS)}H", code, footer + 4), strict=True))


def build(directory, nasm, *, checkpoint_safe=False):
    """Assemble the authored COM and return bytes plus COM offsets.

    The default paired fixture retains its private DOS allocation strategy.
    ``checkpoint_safe`` uses the EXEC-owned PSP allocation without resizing
    its MCB or allocating another block, as required by process checkpoints.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = "%define CHECKPOINT_PSP_BUFFER 1\n" + _SOURCE if checkpoint_safe else _SOURCE
    name = "rep-fault-checkpoint" if checkpoint_safe else "rep-fault-retry"
    code = assemble(directory, name, source, nasm)
    layout = labels(code)
    if layout["destination_offset"] != DESTINATION_OFFSET:
        raise AssertionError("Fixture destination offset changed unexpectedly")
    return code, layout
