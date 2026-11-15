; Authored fDisBull DOS process loader, assembled as an ordinary .COM file.
;
; This helper asks the running DOS kernel to build and load the child process.
; It does not synthesize a PSP, relocate the target itself, patch target bytes,
; or require an emulator-specific instruction.  The host supplies the target,
; command tail and nonce by patching only the three fixed data fields below.
;
; Build for the source/template consistency check:
;     nasm -f bin process_loader.asm -o /private/process-loader.com
;
; Optional FDB_TARGET, FDB_COMMAND_TAIL and FDB_NONCE_BYTES definitions let the
; tests assemble the requested data independently of the Python patcher.
;
; Report layout (all words little-endian; offsets relative to report):
;   00 magic[4]       04 version:u8       05 type:u8       06 size:u16
;   08 nonce[16]      24 helper segment   26 child PSP     28 entry CS
;   30 entry IP       32 startup SS       34 startup SP    36 startup AX
;   38 control off   40 ready park IP    42 exit park IP  44 report off
;   46 DOS result    48 DOS version AX   50 DOS OEM       52 helper PSP
;   54 EXEC flags    56 raw load-only SP 58 target off    60 command tail off
;   62 helper paras  64 initial FLAGS    66 first MCB     68 list-of-lists off
;   70 list-of-lists segment             72 failure stage
;   74..95 reserved zero
;
; Types: 1 ready, 2 DOS/preparation error, 3 terminated.  DOS result is the
; failed DOS call's AX for type 2, or the single AH=4Dh result for type 3.
; Failure stages: 0 none, 1 resize, 2 select drive, 3 parent directory, 4 EXEC.

bits 16
org 100h

REPORT_SIZE equ 96
COM2        equ 02f8h

        jmp near start
        db 0                            ; report has the fixed COM offset 104h

report:
        db 'FDBP', 2
report_type:                    db 0
        dw REPORT_SIZE
report_nonce:
%ifdef FDB_NONCE_BYTES
        db FDB_NONCE_BYTES
%else
        times 16 db 0
%endif
%if ($ - report_nonce) != 16
        %error "FDB_NONCE_BYTES must contain exactly sixteen bytes"
%endif
report_helper_segment:          dw 0
report_child_psp:               dw 0
report_entry_cs:                dw 0
report_entry_ip:                dw 0
report_stack_ss:                dw 0
report_stack_sp:                dw 0
report_initial_ax:              dw 0
        dw control, ready_wait, exit_wait, report
report_dos_result:              dw 0
report_dos_version:             dw 0
report_dos_oem:                 dw 0
report_helper_psp:              dw 0
report_exec_flags:              dw 0
report_raw_stack_sp:            dw 0
        dw target_path, command_tail, HELPER_PARAGRAPHS, 0202h
report_first_mcb:               dw 0
report_list_of_lists_offset:    dw 0
report_list_of_lists_segment:   dw 0
report_failure_stage:           dw 0
        times REPORT_SIZE - ($ - report) db 0

control:                        db 0    ; host changes 0 to 1 after admission

target_path:
%ifdef FDB_TARGET
        db FDB_TARGET
%endif
        times 128 - ($ - target_path) db 0 ; absolute drive and 8.3 path

command_tail:
        db command_tail_end - command_tail_text
command_tail_text:
%ifdef FDB_COMMAND_TAIL
        db FDB_COMMAND_TAIL
%endif
command_tail_end:
        db 13
        times 128 - ($ - command_tail) db 0

parent_directory:
%ifdef FDB_PARENT
        db FDB_PARENT
%endif
        times 128 - ($ - parent_directory) db 0

; Standard unopened FCBs.  DOS AH=29h supplies the two names from the tail.
fcb_one:        db 0
                times 11 db ' '
                times 25 db 0
fcb_two:        db 0
                times 11 db ' '
                times 25 db 0

exec_parameters:
        dw 0                            ; inherit the helper's DOS environment
        dw command_tail, 0
        dw fcb_one, 0
        dw fcb_two, 0
exec_return_stack:              dw 0, 0  ; raw SP, SS returned by AX=4B01h
exec_return_entry:              dw 0, 0  ; IP, CS returned by AX=4B01h

helper_dta:                     dw 0, 0
saved_exec_ax:                  dw 0
requested_drive:                db 0

start:
        ; Establish our own stack before returning the large COM allocation.
        cli
        mov ax, cs
        mov ss, ax
        mov sp, helper_stack_top
        mov ds, ax
        mov es, ax
        cld
        sti
        mov [report_helper_segment], ax

        mov ah, 62h
        int 21h
        mov [report_helper_psp], bx

        mov ax, 3000h
        int 21h
        mov [report_dos_version], ax
        mov al, bh
        xor ah, ah
        mov [report_dos_oem], ax

        ; Capture actual DOS-owned roots before loading the selected process.
        mov ah, 52h
        int 21h
        mov [report_list_of_lists_offset], bx
        mov [report_list_of_lists_segment], es
        mov ax, [es:bx-2]
        mov [report_first_mcb], ax

        mov ah, 2fh
        int 21h
        mov [helper_dta], bx
        mov [helper_dta+2], es
        push cs
        pop es

        call uart_initialize

        mov word [report_failure_stage], 1
        mov bx, HELPER_PARAGRAPHS
        mov ah, 4ah
        int 21h
        jc dos_error

        ; The absolute workspace path selects its drive and target parent.
        ; Relative opens therefore resolve beside the selected executable.
        mov word [report_failure_stage], 2
        cmp byte [target_path+1], ':'
        jne set_root_directory
        mov dl, [target_path]
        and dl, 0dfh
        sub dl, 'A'
        mov [requested_drive], dl
        mov ah, 0eh
        int 21h
        mov ah, 19h
        int 21h
        cmp al, [requested_drive]
        je set_root_directory
        mov ax, 15                      ; DOS invalid-drive error
        stc
        jmp dos_error

set_root_directory:
        mov word [report_failure_stage], 3
        mov dx, parent_directory
        mov ah, 3bh
        int 21h
        jc dos_error

        ; Use DOS's default-FCB parser, including its ordinary filename rules.
        mov si, command_tail_text
        mov di, fcb_one
        mov ax, 2901h
        int 21h
        mov di, fcb_two
        mov ax, 2901h
        int 21h

        mov ax, cs
        mov [exec_parameters+4], ax
        mov [exec_parameters+8], ax
        mov [exec_parameters+12], ax
        mov es, ax
        mov dx, target_path
        mov bx, exec_parameters
        mov word [report_failure_stage], 4
        mov ax, 4b01h
        int 21h

        ; EXEC may alter the caller's registers, including SS:SP on old DOS.
        ; MOV SS inhibits interrupts through the immediately following MOV SP.
        ; None of these MOV instructions changes the returned carry flag.
        mov [cs:saved_exec_ax], ax
        mov ax, cs
        mov ss, ax
        mov sp, helper_stack_top
        mov ds, ax
        mov es, ax
        pushf
        pop word [report_exec_flags]
        sti
        test word [report_exec_flags], 1
        jz child_loaded
        mov ax, [saved_exec_ax]
        mov [report_dos_result], ax
        jmp report_error

child_loaded:
        ; AX=4B01h leaves an extra initial-AX word on the returned child stack.
        ; Remove only that word; a COM program's original zero return word stays.
        les bx, [exec_return_stack]
        mov [report_stack_ss], es
        mov [report_raw_stack_sp], bx
        mov ax, [es:bx]
        mov [report_initial_ax], ax
        add bx, 2
        mov [report_stack_sp], bx
        mov ax, [exec_return_entry]
        mov [report_entry_ip], ax
        mov ax, [exec_return_entry+2]
        mov [report_entry_cs], ax

        mov ah, 62h
        int 21h
        mov [report_child_psp], bx

        ; Use the helper's process identity for its own DOS housekeeping.
        mov bx, [report_helper_psp]
        mov ah, 50h
        int 21h
        lds dx, [cs:helper_dta]
        mov ah, 1ah
        int 21h
        push cs
        pop ds
        mov dx, termination_callback
        mov ax, 2522h
        int 21h

        ; DOS restores this pointer on normal and resident termination.  A
        ; nested EXEC child receives its own return pointer from DOS instead.
        mov es, [report_child_psp]
        mov word [es:0ah], termination_callback
        mov ax, cs
        mov [es:0ch], ax
        mov es, ax

        ; Leave the DOS return frame on the first stack untouched.  UART calls,
        ; the READY loop, and the final context switch use a separate stack.
        cli
        mov ss, ax
        mov sp, report_stack_top
        sti
        mov word [report_failure_stage], 0
        mov byte [report_type], 1
        call send_report

ready_wait:
        sti                             ; IRQs remain active while parked
        cmp byte [cs:control], 1
        je enter_child
        hlt
        jmp ready_wait

enter_child:
        mov bx, [cs:report_child_psp]
        mov ah, 50h
        int 21h
        mov ds, [cs:report_child_psp]
        mov dx, 80h                     ; ordinary child default DTA
        mov ah, 1ah
        int 21h

        ; DOS specifies the initial segment registers, stack and AX.  Other
        ; general registers are initialized to zero here, not represented as
        ; observations of a normal EXEC=00h loader's unspecified registers.
        cli
        xor ax, ax
        mov bx, ax
        mov cx, ax
        mov dx, ax
        mov si, ax
        mov di, ax
        mov bp, ax
        push word 0002h                 ; clear DF/TF and condition flags
        popf
        mov ax, [cs:report_child_psp]
        mov ds, ax
        mov es, ax
        mov ax, [cs:report_stack_ss]
        mov ss, ax
        mov sp, [cs:report_stack_sp]
        mov ax, [cs:report_initial_ax]
        sti
        jmp far [cs:exec_return_entry]   ; no extra words left on child stack

termination_callback:
        ; INT22 is a termination transfer, not a callback that returns by IRET.
        cli
        mov ax, cs
        mov ss, ax
        mov sp, helper_stack_top
        mov ds, ax
        mov es, ax
        cld
        sti
        mov bx, [report_helper_psp]
        mov ah, 50h
        int 21h
        mov ah, 4dh                     ; read the child result exactly once
        int 21h
        mov [report_dos_result], ax
        mov byte [report_type], 3
        call send_report
        jmp exit_wait

dos_error:
        mov [cs:report_dos_result], ax
        pushf
        pop word [cs:report_exec_flags]
report_error:
        push cs
        pop ds
        mov byte [report_type], 2
        call send_report

exit_wait:
        sti                             ; resident IRQ handlers may still run
        hlt
        jmp exit_wait

uart_initialize:
        mov dx, COM2+1
        xor al, al
        out dx, al                      ; disable UART-generated interrupts
        mov dx, COM2+3
        mov al, 80h
        out dx, al                      ; expose the baud divisor
        mov dx, COM2
        mov al, 1
        out dx, al                      ; 115200 baud
        inc dx
        xor al, al
        out dx, al
        mov dx, COM2+3
        mov al, 3
        out dx, al                      ; 8 data bits, no parity, 1 stop bit
        mov dx, COM2+2
        mov al, 7
        out dx, al                      ; enable/reset the UART FIFOs
        mov dx, COM2+4
        mov al, 0bh
        out dx, al
        ret

send_report:
        push ax
        push cx
        push dx
        push si
        push ds
        push cs
        pop ds
        cld
        mov si, report
        mov cx, REPORT_SIZE
.next_byte:
        lodsb
        mov ah, al
        mov dx, COM2+5
.wait_transmitter:
        in al, dx
        test al, 20h
        jz .wait_transmitter
        mov al, ah
        mov dx, COM2
        out dx, al
        loop .next_byte
        pop ds
        pop si
        pop dx
        pop cx
        pop ax
        ret

        align 2, db 0
helper_stack:
        times 512 db 0
helper_stack_top:
report_stack:
        times 512 db 0
report_stack_top:
program_end:

HELPER_PARAGRAPHS equ (program_end - $$ + 100h + 15) / 16

; These fixed data offsets are the public builder's only patch locations.
%if report - $$ != 4 || control - $$ != 100 || target_path - $$ != 101
        %error "The host patch locations no longer match the COM template"
%endif
%if command_tail - $$ != 229
        %error "The command-tail patch location no longer matches the template"
%endif
