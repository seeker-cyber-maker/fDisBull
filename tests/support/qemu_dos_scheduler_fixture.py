"""Authored DOS V86 interrupt-frame scheduler witness, not a guest scheduler.

The DOS program creates one initial FDBTASK1 anchor and a DPL3 INT 61 gate.
The gate's entire handler is INT 60 (native scheduler yield), IRETD; it does
not choose a task, modify anchors, or copy hardware interrupt frames.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from test_qemu_dos_modes_checkpoint_native import _SOURCE as _BASE

ANCHOR = 0x150000
MONITOR_UUID = '00112233445566778899aabbccddeeff'


def _replace(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('DOS mode fixture changed; scheduler witness needs review')
    return source.replace(old, new, 1)


def scheduler_fixture(directory, nasm, *, fpu=False, isolate_ring0=False, iret16=False, gp_fault=False, debug_watchpoints=False):
    source = _BASE
    source = _replace(source, "db 'FMOD'", "db 'FSCH'")
    source = _replace(source,
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$',
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$, b_entry - $$, shared_hook - $$, scratch - $$, b_stack_top - $$, fetch_site - $$, after_a - $$, after_b - $$, counter - $$, ring0_stack_top - $$, vm_stack_top - $$, fpu_observed - $$, fork_flags - $$, yield_handler - $$, watch_a - $$, watch_b - $$, watch_count - $$, last_watch_ip - $$, after_watch_a - $$, after_watch_b - $$, b_after_watch_b - $$, round_result - $$')
    source = _replace(source, '''    mov eax,edx
    add eax,ring0_stack_top''', '''    ; Install one DPL3 32-bit gate. Native INT 60 switches tasks;
    ; CPU INT 61 and IRETD own the actual VM86 hardware frame.
    mov eax,edx
    add eax,yield_handler
    mov [idt+0x61*8],ax
    shr eax,16
    mov [idt+0x61*8+6],ax
    mov word [idt+0x61*8+2],8
    mov word [idt+0x61*8+4],0xee00
%if SCHED_DEBUG_WATCHPOINTS
    mov eax,edx
    add eax,debug_exception_handler
    mov [idt+1*8],ax
    shr eax,16
    mov [idt+1*8+6],ax
    mov word [idt+1*8+2],8
    mov word [idt+1*8+4],0x8e00
    mov eax,edx
    add eax,watch_setup_handler
    mov [idt+0x63*8],ax
    shr eax,16
    mov [idt+0x63*8+6],ax
    mov word [idt+0x63*8+2],8
    mov word [idt+0x63*8+4],0xee00
%endif
    mov eax,edx
    add eax,ring0_stack_top''')
    source = _replace(source, 'idtr: dw 14*8-1', '%if SCHED_DEBUG_WATCHPOINTS\nidtr: dw 0x64*8-1\n%else\nidtr: dw 0x62*8-1\n%endif')
    source = _replace(source, 'idt: times 14*8 db 0', '%if SCHED_DEBUG_WATCHPOINTS\nidt: times 0x64*8 db 0\n%else\nidt: times 0x62*8 db 0\n%endif')
    source = _replace(source, '''pm_ready:
    movzx edx,word [ebp+real_jump+4]''', '''pm_ready:
    ; Explicit fast A20 gate, without asserting the reset bit.
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
%if SCHED_FPU
    ; Permit 486 x87 use in both cloned contexts.
    mov eax,cr0
    and eax,0xfffffff3
    mov cr0,eax
%endif
    ; One bootstrap anchor only. The native scheduler owns later changes.
    mov dword [0x150000],0x54424446
    mov dword [0x150004],0x314b5341
    mov dword [0x150008],0x33221100
    mov dword [0x15000c],0x77665544
    mov dword [0x150010],0xbbaa9988
    mov dword [0x150014],0xffeeddcc
    mov dword [0x150018],0
    mov dword [0x15001c],0
    mov dword [0x150020],0xa1
    mov dword [0x150024],0
    mov dword [0x150028],1
    mov dword [0x15002c],0
    mov dword [0x150030],1
    mov dword [0x150034],0
    movzx edx,word [ebp+real_jump+4]''')
    source = _replace(source, '''mode_ready:
    nop
fetch_site:
    nop
    mov cx,2
hook_site:
    nop
    inc word [cs:scratch]
    loop hook_site
%if MODE_V86
    mov eax,cr0               ; VM86 #GP enters authored monitor below''', '''mode_ready:
    nop
%if SCHED_FPU
    fninit
    fldcw [cs:round_down]
    fld1
%endif
%if SCHED_DEBUG_WATCHPOINTS
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,watch_a
    int 0x63                  ; guest programs DR0/DR7 once, in ring 0
%endif
    mov bx,0xa11a
    mov si,0x1111
 a_loop:
%if SCHED_FPU
    fst qword [cs:fpu_observed]
    fld qword [cs:round_input]
    fistp word [cs:round_result]
%endif
    inc word [cs:counter]
    inc word [cs:scratch]
%if SCHED_DEBUG_WATCHPOINTS
    mov byte [cs:watch_a],1
 after_watch_a:
    mov byte [cs:watch_b],1
 after_watch_b:
%endif
    stc
    call shared_hook
    int 0x61
 after_a:
    cmp word [cs:counter],3
    jb a_loop
    int 0x62                    ; native block, no task choice
    cld                         ; return to DOS with its expected direction
    mov eax,cr0                 ; after scheduler disable, exit through #GP
    jmp short $
 b_entry:
    pushfd                      ; capture forked flags before modifying any
    pop dword [cs:fork_flags]
%if SCHED_FPU
    fninit
    fldcw [cs:round_up]
    fldz
%endif
%if SCHED_DEBUG_WATCHPOINTS
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,watch_b
    int 0x63
%endif
    mov bx,0xb22b
    mov si,0x2222
 b_loop:
%if SCHED_FPU
    fst qword [cs:fpu_observed]
    fld qword [cs:round_input]
    fistp word [cs:round_result]
%endif
    inc word [cs:counter]
    inc word [cs:scratch]
%if SCHED_DEBUG_WATCHPOINTS
    mov byte [cs:watch_a],1
    mov byte [cs:watch_b],1
 b_after_watch_b:
%endif
    clc
    call shared_hook
    int 0x61
 after_b:
    cmp word [cs:counter],3
    jb b_loop
    int 0x62
    cld
    mov eax,cr0
    jmp short $
 shared_hook:
 fetch_site:
    nop
 hook_site:
    nop
    ret
%if MODE_V86
    mov eax,cr0               ; unreachable template exit''')
    source = _replace(source, '''bits 16
pm16_entry:''', '''yield_handler:
    int 0x60
    iretd
%if SCHED_DEBUG_WATCHPOINTS
watch_setup_handler:
    mov dr0,eax
    mov eax,0x10401
    mov dr7,eax
    iretd

debug_exception_handler:
    push eax
    mov eax,[ss:esp+4]         ; saved 32-bit exception return EIP
    mov [ss:ebp+last_watch_ip],eax
    inc dword [ss:ebp+watch_count]
    mov eax,dr6
    and eax,0xfffffffe         ; clear B0
    mov dr6,eax
    pop eax
    iretd
%endif
bits 16
pm16_entry:''')
    if iret16:
        source = _replace(source, 'yield_handler:\n    int 0x60\n    iretd',
                          'yield_handler:\n    int 0x60\n    iretw')
    if gp_fault:
        source = _replace(source, '    int 0x61\n after_a:',
                          '    mov eax,cr0\n after_a:')
    source = _replace(source, 'scratch: dw 0', 'scratch: dw 0\ncounter: dw 0\nfpu_observed: dq 0\nround_input: dq 1.5\nround_down: dw 0x077f\nround_up: dw 0x0b7f\nround_result: dw 0\nfork_flags: dd 0\nwatch_a: db 0\nwatch_b: db 0\nwatch_count: dd 0\nlast_watch_ip: dd 0\nb_stack: times 512 db 0\nb_stack_top:')
    if debug_watchpoints:
        source = _replace(source, 'gp_handler:\n    cli',
                          'gp_handler:\n    cli\n    xor eax,eax\n    mov dr7,eax')
    else:
        # Keep the public symbol table stable when the profile is disabled.
        source += '\nafter_watch_a equ 0\nafter_watch_b equ 0\nb_after_watch_b equ 0\n'
    if isolate_ring0:
        # A COM image's load segment need not be page aligned. Allocate enough
        # room for an actual aligned private-page exclusion at runtime.
        source = _replace(source, 'ring0_stack: times 256 db 0\nring0_stack_top:',
                          'ring0_effective: dd 0\nring0_stack: times 8192 db 0\nring0_stack_top:')
        source = _replace(source, '    add eax,ring0_stack_top\n    mov [tss+4],eax',
                          '    add eax,ring0_stack+4095\n    and eax,0xfffff000\n'
                          '    add eax,4096\n    mov [ring0_effective],eax\n    mov [tss+4],eax')
        source = _replace(source, '    lea esp,[ebp+ring0_stack_top]',
                          '    mov esp,[ebp+ring0_effective]')
    data = assemble(directory, 'scheduler', '%define MODE_V86 1\n%define MODE_PAGING 1\n' + f'%define SCHED_FPU {int(fpu)}\n%define SCHED_DEBUG_WATCHPOINTS {int(debug_watchpoints)}\n' + source, nasm)
    marker = data.index(b'FSCH')
    ready, hook, fetch, scratch, gp, ret, pm, pt, b_entry, shared, scratch2, b_stack, fetch2, after_a, after_b, counter, ring0_stack, vm_stack, fpu_observed, fork_flags, yield_site, watch_a, watch_b, watch_count, last_watch_ip, after_watch_a, after_watch_b, b_after_watch_b, round_result = struct.unpack_from('<29H', data, marker + 4)
    assert scratch == scratch2 and fetch == fetch2 and hook == shared + 1
    return data, dict(ready=ready, hook=hook, fetch=fetch, scratch=scratch, gp=gp,
                      ret=ret, pm=pm, pt=pt, b_entry=b_entry, shared=shared,
                      b_stack=b_stack, after_a=after_a, after_b=after_b, counter=counter, ring0_stack=ring0_stack, vm_stack=vm_stack, fpu_observed=fpu_observed, fork_flags=fork_flags, yield_site=yield_site, watch_a=watch_a, watch_b=watch_b, watch_count=watch_count, last_watch_ip=last_watch_ip, after_watch_a=after_watch_a, after_watch_b=after_watch_b, b_after_watch_b=b_after_watch_b, round_result=round_result)
