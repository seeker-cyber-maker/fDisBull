/* Private experiment only: present the controlled C: directory as DOS A:.
 * The original vendor updater is executed unmodified. This is a directory
 * alias, not evidence of floppy-controller or disk-copy-protection fidelity.
 */
.intel_syntax noprefix
.code16
.section .text
.global _start
_start:
    push cs
    pop ds
    push cs
    pop es
    mov sp, 0x0ffe
    mov bx, 0x0100
    mov ah, 0x4a
    int 0x21
    jc failed

    mov ax, cs
    mov word ptr [parameters + 4], ax
    mov word ptr [parameters + 8], ax
    mov word ptr [parameters + 12], ax
    mov dx, offset command_name
    mov bx, offset parameters
    mov ax, 0x4b00
    int 0x21
    jc failed

    push cs
    pop ds
    push cs
    pop es
    mov word ptr [parameters + 2], offset patch_tail
    mov dx, offset patch_name
    mov bx, offset parameters
    mov ax, 0x4b00
    int 0x21
    jc failed
    /* Preserve the child's actual DOS exit status, then remain observable. */
    mov ah, 0x4d
    int 0x21
finished:
    jmp finished

failed:
    push cs
    pop ds
    mov dx, offset error_message
    mov ah, 9
    int 0x21
    mov ax, 0x4c7f
    int 0x21

parameters:
    .word 0
    .word command_tail, 0
    .word 0x5c, 0
    .word 0x6c, 0
command_name:
    .asciz "Z:\\COMMAND.COM"
patch_name:
    .asciz "GW_PATCH.EXE"
command_tail:
    .byte command_end - command_start
command_start:
    .ascii " /C SUBST A: C:\\"
command_end:
    .byte 13
patch_tail:
    .byte 0, 13
error_message:
    .ascii "Experiment bootstrap EXEC or allocation failed.\r\n$"
