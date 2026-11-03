/* Authored DOS COM probe, no game code/assets. Enter 32-bit protected mode,
 * create private paging with linear page zero remapped away from the physical
 * IVT, and wait for a host-controlled byte. Return to real mode and poll INT33.
 * All interrupts remain disabled while the temporary GDT/page tables are active.
 * Runtime CS:0600 stage (1=protected/paged, 2=real/polled); CS:0601 resume byte;
 * CS:0602/0604/0606 sampled buttons/x/y. CS:0500 is the real-mode checkpoint.
 * GNU as --32; GNU ld -m elf_i386 --oformat binary -Ttext 0; strip first 0x100.
 */
.intel_syntax noprefix
.text
.code16
.org 0x100
.global _start
_start:
 push cs
 pop ds
 cli
 cld
 mov ax, 0x13
 int 0x10
 xor ax, ax
 int 0x33
 cmp ax, 0xffff
 jne failure
 mov ax, 7
 xor cx, cx
 mov dx, 639
 int 0x33
 mov ax, 8
 xor cx, cx
 mov dx, 199
 int 0x33
 mov ax, cs
 movzx ebx, ax
 shl ebx, 4
 mov eax, ebx
 add eax, offset gdt
 mov dword ptr [gdt_pointer+2], eax
 mov eax, ebx
 mov word ptr [code16+2], ax
 shr eax, 16
 mov byte ptr [code16+4], al
 mov word ptr [real_pointer+2], cs
 mov eax, ebx
 add eax, offset pm_entry
 mov dword ptr [pm_pointer], eax
 mov dx, 0x92
 in al, dx
 or al, 2
 out dx, al
 lgdt [gdt_pointer]
 mov eax, cr0
 or eax, 1
 mov cr0, eax
 data32 ljmp [pm_pointer]
failure:
 mov byte ptr [stage], 0xff
 jmp failure
.code32
pm_entry:
 mov ax, 0x10
 mov ds, ax
 mov es, ax
 mov ss, ax
 mov esp, ebx
 add esp, 0xfff0
 // Construct private page directory/table in unused COM allocation, aligned physically.
 mov edi, ebx
 add edi, offset page_storage + 0xfff
 and edi, 0xfffff000
 mov ebp, edi
 xor eax, eax
 mov ecx, 1024
 rep stosd
 mov eax, edi
 or eax, 3
 mov dword ptr [ebp], eax
 mov ecx, 1024
 xor eax, eax
page_entry:
 mov edx, eax
 or edx, 3
 mov dword ptr [edi], edx
 add edi, 4
 add eax, 4096
 loop page_entry
 // Deliberately remap CPU linear page zero: physical IVT identity must still succeed.
 mov dword ptr [ebp+4096], 0x1003
 mov cr3, ebp
 mov eax, cr0
 or eax, 0x80000000
 mov cr0, eax
 mov byte ptr [ebx+stage], 1
pm_wait:
 cmp byte ptr [ebx+control], 0
 je pm_wait
 .byte 0xea
 .long pm16_return
 .word 0x18
.code16
pm16_return:
 mov eax, cr0
 and eax, 0x7ffffffe
 mov cr0, eax
 ljmp cs:[real_pointer]
real_entry:
 mov ax, cs
 mov ds, ax
 mov es, ax
 mov ss, ax
 mov sp, 0xfff0
 mov ax, 3
 int 0x33
 mov [sample_buttons], bx
 mov [sample_x], cx
 mov [sample_y], dx
 mov byte ptr [stage], 2
 jmp checkpoint
.org 0x500
checkpoint:
 nop
 jmp checkpoint
.balign 8, 0
gdt:
 .quad 0
 .word 0xffff,0
 .byte 0,0x9a,0xcf,0
 .word 0xffff,0
 .byte 0,0x92,0xcf,0
code16:
 .word 0xffff,0
 .byte 0,0x9a,0,0
gdt_end:
gdt_pointer:
 .word gdt_end-gdt-1
 .long 0
pm_pointer:
 .long 0
 .word 8
real_pointer:
 .word real_entry,0
.org 0x600
stage: .byte 0
control: .byte 0
sample_buttons: .word 0
sample_x: .word 0
sample_y: .word 0
.org 0x1000
page_storage:
 .space 0x3000
