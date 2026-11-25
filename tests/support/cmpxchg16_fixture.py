"""DOS-launched, guest-owned long-mode CMPXCHG16B and page-fault witness."""

import hashlib
from pathlib import Path
import struct

from support.dos_process_fixture import assemble

CODE = 0x120000
TARGET = 0x130000
REPORT = 0x131000
PML4 = 0x140000
PTE = 0x143000 + (TARGET >> 12) * 8
IDT = 0x144000
STACK = 0x14FF00
INITIAL = "08070605040302011817161514131211"
CHANGED = "11223344556677888070605040302010"
FIELDS = ("entry", "cmp_failed", "failed_after", "cmp_changed",
          "changed_after", "cmp_same", "same_after", "done", "handler")


def build(directory, nasm, *, locked=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = "lock " if locked else ""
    table = "\n".join(f"    dd {CODE:#x}+{label}-payload" for label in FIELDS)
    source = f"""
bits 16
org 0
    jmp start
    db 'CX16META'
{table}
start:
    cli
    push cs
    pop ds
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
    or eax,1
    mov cr0,eax
    jmp dword far [protected_jump]
bits 32
protected_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov esp,{STACK:#x}
    cld
    lea esi,[ebp+payload]
    mov edi,{CODE:#x}
    mov ecx,payload_end-payload
    rep movsb
    mov edi,{PML4:#x}
    xor eax,eax
    mov ecx,4096
    rep stosd
    mov dword [{PML4:#x}],{PML4+0x1000|3:#x}
    mov dword [{PML4+0x1000:#x}],{PML4+0x2000|3:#x}
    mov dword [{PML4+0x2000:#x}],{PML4+0x3000|3:#x}
    mov edi,{PML4+0x3000:#x}
    mov eax,3
    mov ecx,512
map_page:
    stosd
    add edi,4
    add eax,0x1000
    loop map_page
    mov edi,{REPORT:#x}
    xor eax,eax
    mov ecx,1024
    rep stosd
    mov byte [{REPORT+0x200:#x}],0x90
    mov dword [{TARGET:#x}],0x05060708
    mov dword [{TARGET+4:#x}],0x01020304
    mov dword [{TARGET+8:#x}],0x15161718
    mov dword [{TARGET+12:#x}],0x11121314
    and dword [{PTE:#x}],~2
    mov edi,{IDT:#x}
    xor eax,eax
    mov ecx,1024
    rep stosd
    mov eax,{CODE:#x}+handler-payload
    mov word [{IDT+14*16:#x}],ax
    mov word [{IDT+14*16+2:#x}],0x18
    mov byte [{IDT+14*16+5:#x}],0x8e
    shr eax,16
    mov word [{IDT+14*16+6:#x}],ax
    mov dword [{IDT+14*16+8:#x}],0
    lidt [ebp+idtr]
    mov eax,{PML4:#x}
    mov cr3,eax
    mov eax,cr4
    or eax,1<<5
    mov cr4,eax
    mov ecx,0xc0000080
    rdmsr
    or eax,1<<8
    wrmsr
    mov eax,cr0
    or eax,0x80010001
    mov cr0,eax
    jmp 0x18:{CODE:#x}+long_entry-payload
align 8
gdt:
    dq 0,0x00cf9a000000ffff,0x00cf92000000ffff,0x00af9a000000ffff
gdt_end:
gdtr: dw gdt_end-gdt-1
      dd 0
protected_jump: dd 0
                dw 8
idtr: dw 4095
      dd {IDT:#x}
payload:
bits 64
long_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov rsp,{STACK:#x}
    lidt [rel long_idtr]
    xor eax,eax
    xor edx,edx
    mov rbx,0x8877665544332211
    mov rcx,0x1020304050607080
entry:
cmp_failed:
    {prefix}cmpxchg16b [abs {TARGET:#x}]
failed_after:
    pushfq
    pop r11
    mov [abs {REPORT+0x100:#x}],r11
    mov [abs {REPORT+0x120:#x}],rax
    mov [abs {REPORT+0x140:#x}],rdx
    and qword [abs {PTE:#x}],~2
    invlpg [abs {TARGET:#x}]
    mov rax,0x0102030405060708
    mov rdx,0x1112131415161718
    mov rbx,0x8877665544332211
    mov rcx,0x1020304050607080
cmp_changed:
    {prefix}cmpxchg16b [abs {TARGET:#x}]
changed_after:
    pushfq
    pop r11
    mov [abs {REPORT+0x108:#x}],r11
    mov [abs {REPORT+0x128:#x}],rax
    mov [abs {REPORT+0x148:#x}],rdx
    and qword [abs {PTE:#x}],~2
    invlpg [abs {TARGET:#x}]
    mov rax,0x8877665544332211
    mov rdx,0x1020304050607080
    mov rbx,rax
    mov rcx,rdx
cmp_same:
    {prefix}cmpxchg16b [abs {TARGET:#x}]
same_after:
    pushfq
    pop r11
    mov [abs {REPORT+0x110:#x}],r11
    mov [abs {REPORT+0x130:#x}],rax
    mov [abs {REPORT+0x150:#x}],rdx
    mov byte [abs {REPORT+0x200:#x}],0x5a
done:
    hlt
    jmp done
handler:
    push rax
    push rbx
    push rcx
    push rdx
    push r10
    push r11
    mov r10,[abs {REPORT:#x}]
    cmp r10,3
    jae failed_handler
    shl r10,6
    add r10,{REPORT+0x10:#x}
    mov rax,[rsp+48]
    mov [r10],rax
    mov rax,cr2
    mov [r10+8],rax
    mov rax,[rsp+56]
    mov [r10+16],rax
    mov rax,[rsp+40]
    mov [r10+24],rax
    mov rax,[rsp+16]
    mov [r10+32],rax
    mov rax,[abs {TARGET:#x}]
    mov [r10+40],rax
    mov rax,[abs {TARGET+8:#x}]
    mov [r10+48],rax
    or qword [abs {PTE:#x}],2
    invlpg [abs {TARGET:#x}]
    inc qword [abs {REPORT:#x}]
    pop r11
    pop r10
    pop rdx
    pop rcx
    pop rbx
    pop rax
    add rsp,8
    iretq
failed_handler:
    hlt
    jmp failed_handler
align 8
long_idtr: dw 4095
           dq {IDT:#x}
payload_end:
"""
    module = assemble(directory, "cmpxchg16-mz", source, nasm)
    pos = module.index(b"CX16META") + 8
    addresses = struct.unpack_from("<" + "I"*len(FIELDS), module, pos)
    header = bytearray(64)
    total = len(module) + len(header)
    struct.pack_into("<14H", header, 0, 0x5A4D, total % 512, (total+511)//512,
                     0, 4, 0x1000, 0x1000, 0, 0xFFFE, 0, 0, 0, 0x1C, 0)
    path = directory / "REMAP.EXE"
    path.write_bytes(bytes(header) + module)
    return dict(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                locked=locked, target=TARGET, report=REPORT, sentinel=REPORT+0x200,
                pte=PTE, code=CODE, stack=STACK, **dict(zip(FIELDS, addresses)))
