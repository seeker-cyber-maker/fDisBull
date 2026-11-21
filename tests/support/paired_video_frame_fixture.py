"""One authored COM for both paired source-raster owners; no game input.

Assembly is deferred to the explicitly admitted native test. The guest journals
linear channel-2 PIT counts around real VGA status observations and whole DAC
triples. A bounded journal can fail qualification; no image controls its timing.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


CONTROL_BYTES = 28
TRIAL_BYTES = 28
EDGE_BYTES = 6
MAX_EDGES = 512
MAX_POLLS = 200000
SYMBOL_NAMES = ('calibration_done', 'trial_ready', 'trial_done', 'fault_stop',
                'control', 'command', 'pulse_mode', 'delay_ticks', 'width_ticks',
                'timing_raw', 'trial', 'calibration')


ASSEMBLY = r'''
bits 16
org 100h
%macro latch_pit2 0
    ; Preserve every register except AX. Inline at witness endpoints to keep
    ; PIT-helper CALL/RET out of the latch-to-device-observation paths.
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
%endmacro
    nop
    call setup
    call sample_status
.calibration_loop:
    call sample_status
    mov al,[previous_status]
    test al,1
    jnz .not_horizontal_rise
    mov al,[current_status]
    test al,8
    jnz .not_horizontal_rise
    test al,1
    jz .not_horizontal_rise
    mov ax,[calibration_count]
    imul di,ax,6
    add di,calibration
    mov ax,[previous_before]
    mov [di],ax
    mov ax,[current_after]
    mov [di+2],ax
    mov ax,[vertical_edges]
    mov [di+4],ax
    inc word [calibration_count]
    cmp word [calibration_count],512
    je calibration_done
.not_horizontal_rise:
    cmp word [vertical_edges],4
    jb .calibration_loop
    mov byte [calibration_limited],1
calibration_done:
    nop
dispatch:
    cmp byte [command],0
    je dispatch
    cmp byte [command],1
    jne bad_command
    mov byte [command],0
    cmp byte [pulse_mode],1
    ja bad_command
    inc word [trial_number]
    cmp word [trial_number],4
    ja bad_command
    xor ax,ax
    mov al,[pulse_mode]
    mov [trial_mode],ax
    mov word [b_before],0
    mov word [b_after],0
    mov word [c_before],0
    mov word [c_after],0
    mov word [post_lo],0
    mov word [post_hi],0
    mov word [post_status],0
    mov word [post_generation],0
    call palette_a
    call new_vsync
    mov ax,[previous_before]
    mov [ready_lo],ax
    mov ax,[current_after]
    mov [ready_hi],ax
    xor ax,ax
    mov al,[current_status]
    mov [ready_status],ax
    mov ax,[vertical_edges]
    mov [ready_generation],ax
trial_ready:
    nop
    cmp word [trial_mode],0
    je .after_pulse
    mov bx,[delay_ticks]
    cmp bx,0
    je bad_command
    call wait_offset
    mov dx,3c8h
    mov al,1
    out dx,al
    inc dx
    latch_pit2
    mov si,ax
    mov al,42
    out dx,al
    mov al,21
    out dx,al
    mov al,1
    out dx,al
    latch_pit2
    mov [b_before],si
    mov [b_after],ax
    mov bx,[delay_ticks]
    add bx,[width_ticks]
    jc bad_command
    cmp bx,32768
    jae bad_command
    cmp word [width_ticks],0
    je bad_command
    call wait_offset
    mov dx,3c8h
    mov al,1
    out dx,al
    inc dx
    latch_pit2
    mov si,ax
    mov al,21
    out dx,al
    mov al,42
    out dx,al
    mov al,1
    out dx,al
    latch_pit2
    mov [c_before],si
    mov [c_after],ax
.after_pulse:
    ; This marker is reached by an explicit continuation AFTER the host has
    ; captured the completed raster. Its later CPU revision stays separate.
    call new_vsync
    mov ax,[previous_before]
    mov [post_lo],ax
    mov ax,[current_after]
    mov [post_hi],ax
    xor ax,ax
    mov al,[current_status]
    mov [post_status],ax
    mov ax,[vertical_edges]
    mov [post_generation],ax
trial_done:
    nop
    jmp dispatch

new_vsync:
    ; Hold the last completed observation until return or fault. Load BOTH
    ; previous/current fields so a refused first poll cannot rotate them.
    ; EBX bits16..23 retain status_valid; bit24 means a fresh low was seen;
    ; bit25 selects the fault exit. BH/BL still hold complete status bytes.
    mov ebp,[poll_count]
    mov cx,[previous_before]
    mov si,[current_before]
    mov di,[current_after]
    xor ebx,ebx
    mov bl,[status_valid]
    shl ebx,16
    mov bh,[previous_status]
    mov bl,[current_status]
    mov dx,3dah
.poll:
    ; Admission precedes state rotation and every device observation.
    inc ebp
    cmp ebp,200000
    ja .fault
    mov cx,si
    mov bh,bl
    latch_pit2
    mov si,ax
    in al,dx
    mov bl,al
    xor al,bh
    and al,bl
    test al,8
    jz .completed
    latch_pit2
    mov di,ax
    test ebx,0ff0000h
    jz .completed
    ; A valid entry-low/first-high still counts while seeking a fresh low.
    ; The actual upper is retained before the generation increment/cap.
    inc word [vertical_edges]
    cmp word [vertical_edges],12
    ja .fault
.completed:
    test ebx,0ff0000h
    jnz .valid
    or ebx,10000h
.valid:
    test bl,8
    jz .saw_low
    test ebx,1000000h
    jz .poll
    jmp .commit
.saw_low:
    or ebx,1000000h
    jmp .poll
.fault:
    or ebx,2000000h
.commit:
    ; Normal return and both finite faults expose the completed observation.
    ; A poll fault retains the preceding sample; a retrace fault retains the
    ; just-bracketed thirteenth rise. No pending fields are filled from time.
    mov [current_after],di
    mov [previous_before],cx
    mov [current_before],si
    mov [previous_status],bh
    mov [current_status],bl
    mov [poll_count],ebp
    mov eax,ebx
    shr eax,16
    mov [status_valid],al
    test ebx,2000000h
    jnz timing_fault
    ret

wait_offset:
    ; BX is an absolute elapsed count from the ready upper-latch timestamp.
    ; Two fixed targets prevent first-write logging from widening the pulse.
.again:
    call poll_budget
    call pit_read
    mov dx,[ready_hi]
    sub dx,ax
    cmp dx,32768
    jae timing_fault
    cmp dx,bx
    jb .again
    ret

sample_status:
    call poll_budget
    ; CX/BH retain the preceding observation; SI/BL retain this one. Neither
    ; lower latch is replaced by a timestamp taken AFTER its status read.
    mov cx,[current_before]
    mov bh,[current_status]
    mov dx,3dah
    latch_pit2
    mov si,ax
    in al,dx
    mov bl,al
    xor al,bh
    and al,bl
    test al,9
    jz .no_upper
    ; Only a bit-0 or bit-3 rise can be consumed by calibration/new_vsync.
    ; The upper latch stays AFTER the first observed high status. A first
    ; sample may also latch, but status_valid prevents a fake vertical edge.
    latch_pit2
    mov [current_after],ax
.no_upper:
    mov [previous_before],cx
    mov [current_before],si
    mov [previous_status],bh
    mov [current_status],bl
    cmp byte [status_valid],0
    je .first
    test bh,8
    jnz .done
    test bl,8
    jz .done
    inc word [vertical_edges]
    cmp word [vertical_edges],12
    ja timing_fault
.done:
    ret
.first:
    mov byte [status_valid],1
    ret

poll_budget:
    inc dword [poll_count]
    cmp dword [poll_count],200000
    ja timing_fault
    ret

pit_read:
    ; Channel2 is explicitly mode2/divisor65536 with gate high. This is not
    ; the BIOS channel0 mode3 counter, whose raw count is not a linear clock.
    latch_pit2
    ret

palette_a:
    mov dx,3c8h
    mov al,1
    out dx,al
    inc dx
    mov al,1
    out dx,al
    mov al,21
    out dx,al
    mov al,42
    out dx,al
    ret

setup:
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    mov ax,0a000h
    mov es,ax
    xor di,di
    mov ax,0101h
    mov cx,32000
    rep stosw
    mov byte [es:0],2
    mov byte [es:319],3
    mov byte [es:199*320],4
    mov byte [es:63999],5
    call palette_a
    mov dx,3c8h
    mov al,2
    out dx,al
    inc dx
    mov si,sentinel_palette
    mov cx,12
.sentinels:
    lodsb
    out dx,al
    loop .sentinels
    call snapshot_vga
    in al,61h
    mov [original_61],al
    and al,0fch
    out 61h,al
    mov al,0b4h
    out 43h,al
    xor al,al
    out 42h,al
    out 42h,al
    mov al,[original_61]
    and al,0fch
    or al,1
    mov [programmed_61],al
    out 61h,al
    ret

snapshot_vga:
    mov di,timing_raw
    mov dx,3cch
    in al,dx
    mov [di],al
    inc di
    mov dx,3c4h
    mov al,1
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    mov si,crtc_indices
    mov cx,10
.next:
    mov dx,3d4h
    lodsb
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    loop .next
    ret

bad_command:
    mov word [fault],1
    jmp fault_stop
timing_fault:
    mov word [fault],2
fault_stop:
    nop
    jmp fault_stop

sentinel_palette: db 63,0,0, 0,63,0, 0,0,63, 63,63,63
crtc_indices: db 0,6,7,9,10h,11h,12h,15h,16h,17h
current_before: dw 0
current_after: dw 0
previous_before: dw 0
current_status: db 0
previous_status: db 0
status_valid: db 0

control:
    db 'PVF1'
    dw 1
fault: dw 0
command: db 0
pulse_mode: db 0
calibration_count: dw 0
vertical_edges: dw 0
poll_count: dd 0
delay_ticks: dw 0
width_ticks: dw 0
pit_command: db 0b4h
original_61: db 0
programmed_61: db 0
calibration_limited: db 0
    dw 0
timing_raw: times 12 db 0
trial:
trial_number: dw 0
trial_mode: dw 0
ready_lo: dw 0
ready_hi: dw 0
b_before: dw 0
b_after: dw 0
c_before: dw 0
c_after: dw 0
post_lo: dw 0
post_hi: dw 0
ready_status: dw 0
post_status: dw 0
ready_generation: dw 0
post_generation: dw 0
calibration: times 512*6 db 0
    db 'PVFS'
    dw calibration_done,trial_ready,trial_done,fault_stop
    dw control,command,pulse_mode,delay_ticks,width_ticks,timing_raw,trial,calibration
'''


def paired_video_program(directory, nasm):
    code = assemble(directory, 'paired-mode13-source', ASSEMBLY, nasm)
    footer = 4 + 2 * len(SYMBOL_NAMES)
    if code[-footer:-footer + 4] != b'PVFS' or len(code) > 16384:
        raise ValueError('Unexpected authored paired fixture layout')
    values = struct.unpack('<' + 'H' * len(SYMBOL_NAMES), code[-2 * len(SYMBOL_NAMES):])
    offsets = dict(zip(SYMBOL_NAMES, values, strict=True))
    if any(not 0x100 <= value < 0x100 + len(code) - footer for value in values):
        raise ValueError('Authored fixture symbol escaped its COM')
    if offsets['timing_raw'] - offsets['control'] != CONTROL_BYTES or offsets['calibration'] - offsets['trial'] != TRIAL_BYTES:
        raise ValueError('Authored journal layout disagrees with its decoder')
    return code, offsets


def parse_control(data):
    if not isinstance(data, bytes) or len(data) != CONTROL_BYTES:
        raise ValueError('Expected the complete authored control journal')
    names = ('magic', 'version', 'fault', 'command', 'pulse_mode', 'calibration_count',
             'vertical_edges', 'poll_count', 'delay_ticks', 'width_ticks',
             'pit_command', 'original_61', 'programmed_61', 'calibration_limited', 'reserved')
    result = dict(zip(names, struct.unpack('<4sHHBBHHIHHBBBBH', data), strict=True))
    if (result.pop('magic') != b'PVF1' or result['version'] != 1 or result['reserved'] != 0 or
            result['fault'] or not 0 <= result['calibration_count'] <= MAX_EDGES or
            not 0 <= result['vertical_edges'] <= 12 or not 0 < result['poll_count'] <= MAX_POLLS or
            result['pit_command'] != 0xb4 or result['programmed_61'] & 3 != 1):
        raise ValueError('Authored fixture fault, poll cap or PIT programming mismatch')
    return result
