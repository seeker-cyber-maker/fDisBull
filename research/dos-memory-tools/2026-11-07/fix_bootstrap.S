/* Authored verification wrapper. Execute an unmodified GW_FIX.EXE in the
 * private current directory. The experiment explicitly starts with DF=0.
 * Child AL is observed, never assumed to be a reliable success indicator.
 */
.intel_syntax noprefix
.code16
.section .text
.global _start, finished, failed
_start:
    cld
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
    mov dx, offset child_name
    mov bx, offset parameters
    mov ax, 0x4b00
    int 0x21
    jc failed
    mov ah, 0x4d
    int 0x21
finished:
    jmp finished
failed:
    jmp failed
parameters:
    .word 0
    .word command_tail, 0
    .word 0x5c, 0
    .word 0x6c, 0
child_name:
    .asciz "GW_FIX.EXE"
command_tail:
    .byte 0, 13
