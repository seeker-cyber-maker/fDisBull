"""Authored real PIT/PIC IRQ0 V86 witness for native CPU preemption.

The guest remaps the existing PC PIC to 20h/28h, leaves the DOS PIT cadence
untouched, and restores the PIC masks/BIOS vector layout before DOS exit. Its
IRQ0 handler acknowledges the real PIC and returns through IRETD; it never
selects another task, writes a scheduler anchor after bootstrap, or copies a
CPU/interrupt frame. INT62 is used only after each task returns from 3 IRQs.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from test_qemu_dos_modes_checkpoint_native import _SOURCE as _BASE

ANCHOR = 0x150000
MONITOR_UUID = '00112233445566778899aabbccddeeff'


def _replace(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('DOS mode fixture changed; IRQ fixture needs review')
    return source.replace(old, new, 1)


def irq_fixture(directory, nasm, *, fpu=False, guard="none", irq=0):
    if guard not in ("none", "if", "mask", "chain-shadow"):
        raise ValueError("Unknown IRQ deferral guard")
    if irq not in (0, 1) or irq == 1 and guard != "none":
        raise ValueError("Unsupported IRQ fixture configuration")
    source = _BASE
    source = _replace(source, "db 'FMOD'", "db 'FIRQ'")
    source = _replace(source,
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$',
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$, b_entry - $$, irq_hook - $$, irq_count - $$, b_stack_top - $$, irq_fetch - $$, irq_after_eoi - $$, irq_return_ip - $$, irq_carry - $$, ring0_stack_top - $$, vm_stack_top - $$, fp_result - $$, loop_count - $$, irq_data - $$, guard_release - $$, guard_after - $$, guard_progress - $$, guard_marker - $$, irq_scancode - $$, guard_after_movss - $$')
    source = _replace(source, '''    mov eax,edx
    add eax,ring0_stack_top''', '''    ; The real PIT or keyboard IRQ uses the remapped master PIC.
    mov eax,edx
    add eax,irq0_handler
    mov [idt+(0x20+IRQ_LINE)*8],ax
    shr eax,16
    mov [idt+(0x20+IRQ_LINE)*8+6],ax
    mov word [idt+(0x20+IRQ_LINE)*8+2],8
    mov word [idt+(0x20+IRQ_LINE)*8+4],0x8e00
    mov eax,edx
    add eax,ring0_stack_top''')
    source = _replace(source, 'idtr: dw 14*8-1', 'idtr: dw (0x21+IRQ_LINE)*8-1')
    source = _replace(source, 'idt: times 14*8 db 0', 'idt: times (0x21+IRQ_LINE)*8 db 0')
    source = _replace(source, '''pm_ready:
    movzx edx,word [ebp+real_jump+4]''', '''pm_ready:
    ; Enable A20 without reset; permit x87 if this fixture uses it.
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
%if IRQ_FPU
    mov eax,cr0
    and eax,0xfffffff3
    mov cr0,eax
%endif
    ; One bootstrap identity: native scheduler owns subsequent transitions.
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
    ; Preserve DOS PIC masks, remap both controllers and mask all IRQs.
    in al,0x21
    mov [ebp+saved_master_mask],al
    in al,0xa1
    mov [ebp+saved_slave_mask],al
    mov al,0x11
    out 0x20,al
    out 0xa0,al
    mov al,0x20
    out 0x21,al
    mov al,0x28
    out 0xa1,al
    mov al,0x04
    out 0x21,al
    mov al,0x02
    out 0xa1,al
    mov al,0x01
    out 0x21,al
    out 0xa1,al
    mov al,0xff
    out 0x21,al
    out 0xa1,al
    movzx edx,word [ebp+real_jump+4]''')
    source = _replace(source, 'push dword 0x23002        ; VM=1, IOPL=3, IF=0',
                      'push dword 0x23202        ; VM=1, IOPL=3, IF=1')
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
%if IRQ_FPU
    fninit
    fld1
%endif
    mov bx,0xa11a
    mov si,0x1111
    cld
%if IRQ_FPU
    fst qword [cs:fp_result]
%endif
%if IRQ_GUARD
    ; Keep A active long enough for the real PIT edge while delivery is
    ; disabled. The host stops at guard_release and inspects actual PIC IRR.
%if IRQ_GUARD != 2
    cli
    mov al,0xfe
    out 0x21,al            ; IRQ0 unmasked, CPU IF=0
%endif
    xor cx,cx
 guard_wait:
    inc dword [cs:guard_progress]
    nop
    nop
    nop
    nop
    nop
    loop guard_wait
 guard_release:
%if IRQ_GUARD = 2
    mov al,0xfe
    out 0x21,al            ; IF=1, remove PIC mask after observed pending IRR
    inc byte [cs:guard_marker]
%elif IRQ_GUARD = 3
    mov ax,ss
    sti
    mov ss,ax              ; chained delaying instructions need not compose
 guard_after_movss:
    inc byte [cs:guard_marker]
%else
    sti
    inc byte [cs:guard_marker]
%endif
 guard_after:
%else
    ; Only A unmasks the configured IRQ after host scheduler setup.
%if IRQ_LINE = 1
    mov al,0xfd
%else
    mov al,0xfe
%endif
    out 0x21,al
%endif
 a_loop:
%if IRQ_FPU
    fst qword [cs:fp_result]
%endif
    inc dword [cs:loop_count]
    cmp word [cs:irq_count],3
    jb a_loop
    int 0x62               ; completion only, after IRQ handler returned
    mov eax,cr0            ; after scheduler disable: #GP restores DOS
    jmp short $
 b_entry:
    nop
%if IRQ_FPU
    fninit
    fldz
%endif
    mov bx,0xb22b
    mov si,0x2222
    std
%if IRQ_FPU
    fst qword [cs:fp_result]
%endif
    sti                    ; B initializes with IF=0; then permits IRQ0
 b_loop:
%if IRQ_FPU
    fst qword [cs:fp_result]
%endif
    inc dword [cs:loop_count]
    cmp word [cs:irq_count],3
    jb b_loop
    int 0x62
    mov eax,cr0
    jmp short $
%if MODE_V86
    mov eax,cr0            ; unreachable template exit''')
    source = _replace(source, '''gp_handler:
    cli
%if MODE_PAGING''', '''gp_handler:
    cli
    cld
    ; Restore PC BIOS PIC vector layout and the exact saved masks.
    mov al,0x11
    out 0x20,al
    out 0xa0,al
    mov al,0x08
    out 0x21,al
    mov al,0x70
    out 0xa1,al
    mov al,0x04
    out 0x21,al
    mov al,0x02
    out 0xa1,al
    mov al,0x01
    out 0x21,al
    out 0xa1,al
    mov al,[ebp+saved_master_mask]
    out 0x21,al
    mov al,[ebp+saved_slave_mask]
    out 0xa1,al
%if MODE_PAGING''')
    source = _replace(source, '''bits 16
pm16_entry:''', '''irq0_handler:
    push eax
    push edx
    mov eax,[ss:esp+8]          ; EIP in real CPU-created interrupt frame
    mov [ss:ebp+irq_return_ip],eax
    inc word [ss:ebp+irq_count]
    mov ax,[ss:ebp+scratch]
    mov [ss:ebp+irq_data],ax    ; real guest read of task-private layer
%if IRQ_LINE = 1
    in al,0x60                 ; actual i8042 data, before PIC EOI
    mov [ss:ebp+irq_scancode],al
%endif
    stc
 irq_fetch:
    nop                        ; A CLC / B STC private fetch overlays
 irq_hook:
    nop                        ; common source hook before actual PIC EOI
    pushfd
    pop eax
    and eax,1
    mov [ss:ebp+irq_carry],ax
    mov al,0x20
    out 0x20,al                ; ordinary non-specific master EOI
 irq_after_eoi:
    pop edx
    pop eax
    iretd
bits 16
pm16_entry:''')
    source = _replace(source, 'scratch: dw 0', '''scratch: dw 0
irq_count: dw 0
loop_count: dd 0
guard_progress: dd 0
guard_marker: db 0
irq_return_ip: dd 0
irq_carry: dw 0
irq_data: dw 0
irq_scancode: db 0
saved_master_mask: db 0
saved_slave_mask: db 0
fp_result: dq 0
b_stack: times 512 db 0
b_stack_top:''')
    if guard == 'none':
        source += '\nguard_release equ 0\nguard_after equ 0\n'
    if guard != 'chain-shadow':
        source += '\nguard_after_movss equ 0\n'
    # The template's markers refer to the old site names; alias them for
    # backwards-sized header fields while keeping new IRQ-specific entries.
    source = source.replace('dw mode_ready - $$, hook_site - $$, fetch_site - $$, scratch - $$',
                            'dw mode_ready - $$, irq_hook - $$, irq_fetch - $$, scratch - $$')
    data = assemble(directory, 'irq-preempt', '%define MODE_V86 1\n%define MODE_PAGING 1\n' +
                    f'%define IRQ_LINE {irq}\n%define IRQ_FPU {int(fpu)}\n%define IRQ_GUARD {dict(none=0, if_=1, mask=2, **{"chain-shadow": 3})["if_" if guard == "if" else guard]}\n' + source, nasm)
    offset = data.index(b'FIRQ')
    fields = struct.unpack_from('<27H', data, offset + 4)
    names = ('ready', 'hook', 'fetch', 'scratch', 'gp', 'ret', 'pm', 'pt',
             'b_entry', 'irq_hook', 'irq_count', 'b_stack', 'irq_fetch', 'after_eoi',
             'return_ip', 'carry', 'ring0_stack', 'vm_stack', 'fp_result', 'loop_count', 'irq_data', 'guard_release', 'guard_after', 'guard_progress', 'guard_marker', 'irq_scancode', 'guard_after_movss')
    result = dict(zip(names, fields))
    assert result['hook'] == result['irq_hook'] and result['fetch'] == result['irq_fetch']
    return data, result
