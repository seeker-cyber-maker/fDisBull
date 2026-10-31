/* Authored DOS COM fixture. No game code or resources.
 * Assemble: as --32 -o frame_capture.o frame_capture.S
 * Link: ld -m elf_i386 --oformat binary -Ttext 0x100 -e _start \
 *          -o FRAMEVID.COM frame_capture.o
 *
 * Runtime CS:0600 is a one-byte NOP checkpoint. CS:0601 resumes painting.
 * Runtime CS:0800 is the FVID status block documented in the native test.
 * Phase 0 keeps a static row; phase 1 changes row 0; phase 2 changes all rows.
 * Every animated frame encodes its sequence in eight red/green pixels.
 * Quota is in observed guest vertical retraces, not screenshot frame IDs.
 */
.intel_syntax noprefix
.code16
.section .text
.global _start

_start:
    mov ax, 0x0013
    int 0x10
    push cs
    pop ds
    cld
    mov ax, 0xa000
    mov es, ax
    xor di, di
    xor ax, ax
    mov cx, 32000
    rep stosw

    /* DAC entries 0 black, 1 full red, 2 full green. */
    mov dx, 0x03c8
    xor al, al
    out dx, al
    inc dx
    out dx, al
    out dx, al
    out dx, al
    mov al, 63
    out dx, al
    xor al, al
    out dx, al
    out dx, al
    out dx, al
    mov al, 63
    out dx, al
    xor al, al
    out dx, al
    call paint_pattern

frame_loop:
    /* Always observe a fresh rising edge, including after a checkpoint. */
    mov dx, 0x03da
wait_not_retrace:
    in al, dx
    test al, 8
    jnz wait_not_retrace
wait_retrace:
    in al, dx
    test al, 8
    jz wait_retrace
    mov ax, word ptr [drawn_sequence]
    mov word ptr [completed_sequence], ax
    inc word ptr [retrace_count]
    dec word ptr [remaining]
    jnz paint_next
    inc word ptr [checkpoint_count]
    jmp checkpoint

paint_next:
    /* Host must arm a positive quota while stopped. Fail visibly otherwise. */
    cmp word ptr [remaining], 0
    je invalid_control
    cmp word ptr [phase], 2
    ja invalid_control
    cmp word ptr [phase], 0
    je frame_loop
    inc word ptr [drawn_sequence]
    call paint_pattern
    jmp frame_loop

invalid_control:
    mov word ptr [fault], 1
    jmp checkpoint

paint_pattern:
    push ax
    push bx
    push cx
    push dx
    push di
    push si
    xor di, di
    mov si, 1
    cmp word ptr [phase], 2
    jne paint_row
    mov si, 200
paint_row:
    mov bx, word ptr [drawn_sequence]
    mov cx, 8
paint_pixel:
    mov al, 1
    test bl, 1
    jz store_pixel
    inc al
store_pixel:
    stosb
    shr bl, 1
    loop paint_pixel
    add di, 312
    dec si
    jnz paint_row
    pop si
    pop di
    pop dx
    pop cx
    pop bx
    pop ax
    ret

/* Link base 0100 + file offset 0500 = runtime checkpoint 0600. */
.org 0x500, 0x90
checkpoint:
    nop
    jmp paint_next

/* Link base 0100 + file offset 0700 = runtime status 0800. */
.org 0x700, 0
status:
    .ascii "FVID"
version:             .word 1
phase:               .word 0
drawn_sequence:      .word 0
completed_sequence:  .word 0
retrace_count:       .word 0
remaining:           .word 3
checkpoint_count:    .word 0
fault:               .word 0
