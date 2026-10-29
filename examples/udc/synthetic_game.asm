# Authored COM fixture: original real-mode DOS code and no external data.
.code16
.intel_syntax noprefix
.global _start, effect_begin, effect_end, result_written
_start:
    push cs
    pop ds
    mov dx, 0x0140
    mov ah, 9
    int 0x21
    xor ah, ah
    int 0x16
    mov ax, 10
effect_begin:
    add ax, 200
    dec ax
effect_end:
    mov word ptr [0x0180], ax
result_written:
    mov dx, 0x0150
    mov ah, 9
    int 0x21
halt:
    jmp halt
.org 0x40
.ascii "Press a key.$"
.org 0x50
.ascii "Score committed.$"
.org 0x80
.word 0
