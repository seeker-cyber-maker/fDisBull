; Relocating boot sector for a private C:FAT12 + D:FAT16 composite disk.
;
; Build the 440-byte MBR code body with:
;   nasm -f bin -D C_START_LBA=2048 workspace_mbr.asm -o workspace-mbr.bin
;
; The Python builder emits the same fixed instruction bytes, fills the MBR
; partition table and disk signature, and verifies the C/D extents. BIOS DL is
; preserved as 0x80 when control transfers to the C volume boot record.
bits 16
org 0

%ifndef C_START_LBA
%define C_START_LBA 2048
%endif

start:
        cli
        xor ax, ax
        mov ds, ax
        mov es, ax
        mov si, 0x7c00
        mov di, 0x0600
        mov cx, 0x0100
        cld
        rep movsw
        jmp 0x0060:relocated_start

relocated_start:
        xor ax, ax
        mov ss, ax
        mov sp, 0x7c00
        mov ax, cs
        mov ds, ax
        sti
        mov [boot_drive], dl
        mov si, dap
        mov ah, 0x42
        int 0x13
        push cs
        pop ds
        jc read_failed
        mov dl, [boot_drive]
        jmp 0x0000:0x7c00

read_failed:
        int 0x18
halt:
        hlt
        jmp $

boot_drive:
        db 0
align 2, db 0

dap:
        db 0x10, 0
        dw 1
        dw 0x7c00
        dw 0
        dq C_START_LBA

times 440 - ($ - $$) db 0
