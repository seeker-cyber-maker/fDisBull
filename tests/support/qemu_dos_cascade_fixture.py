"""Authored real RTC IRQ8 with nested i8042 IRQ1, not a guest scheduler.

The guest remaps PIC vectors to 20h/28h and enables RTC periodic IRQ8. Its
outer handler reads RTC register C, then permits the higher-priority real IRQ1.
The keyboard handler drains the i8042 FIFO and sends the master EOI; the outer
handler subsequently sends slave then master EOIs and executes IRETD. No guest
instruction chooses the next task or fabricates an interrupt.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble
from test_qemu_dos_modes_checkpoint_native import _SOURCE as _BASE

ANCHOR = 0x150000
MONITOR_UUID = '00112233445566778899aabbccddeeff'


def _replace(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('DOS mode fixture changed; cascade fixture needs review')
    return source.replace(old, new, 1)


def cascade_fixture(directory, nasm, *, fault='none'):
    if fault not in ('none', 'inner-no-eoi', 'master-before-slave'):
        raise ValueError('Unknown cascade fault variant')
    source = _BASE
    source = _replace(source, "db 'FMOD'", "db 'FCAS'")
    source = _replace(source,
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$',
        'dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$, b_entry - $$, outer_wait - $$, inner_hook - $$, after_slave - $$, after_master - $$, outer_count - $$, inner_count - $$, key_count - $$, key_bytes - $$, outer_return - $$, inner_return - $$, scratch - $$, observed_data - $$, outer_fetch - $$, ring0_stack_top - $$, vm_stack_top - $$, b_stack_top - $$, rtc_regc - $$, empty_irq_count - $$')
    source = _replace(source, '''    mov eax,edx
    add eax,ring0_stack_top''', '''    ; Remapped master IRQ1 and slave IRQ8 gates.
    mov eax,edx
    add eax,keyboard_handler
    mov [idt+0x21*8],ax
    shr eax,16
    mov [idt+0x21*8+6],ax
    mov word [idt+0x21*8+2],8
    mov word [idt+0x21*8+4],0x8e00
    mov eax,edx
    add eax,rtc_handler
    mov [idt+0x28*8],ax
    shr eax,16
    mov [idt+0x28*8+6],ax
    mov word [idt+0x28*8+2],8
    mov word [idt+0x28*8+4],0x8e00
    mov eax,edx
    add eax,ring0_stack_top''')
    source = _replace(source, 'idtr: dw 14*8-1', 'idtr: dw 0x29*8-1')
    source = _replace(source, 'idt: times 14*8 db 0', 'idt: times 0x29*8 db 0')
    source = _replace(source, '''pm_ready:
    movzx edx,word [ebp+real_jump+4]''', '''pm_ready:
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    ; Bootstrap identity only; the native scheduler owns all later changes.
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
    ; Preserve RTC A/B, set a bounded periodic rate, keep PIE disabled until
    ; A starts. Reading register C clears any previously latched RTC event.
    mov al,0x0a
    out 0x70,al
    in al,0x71
    mov [ebp+saved_rtc_a],al
    and al,0xf0
    or al,0x0a
    out 0x71,al
    mov al,0x0b
    out 0x70,al
    in al,0x71
    mov [ebp+saved_rtc_b],al
    and al,0x8f                ; disable periodic, alarm and update IRQs
    out 0x71,al
    mov al,0x0c
    out 0x70,al
    in al,0x71
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
    mov bx,0xa11a
    mov si,0x1111
    cld
    mov al,0xfe                 ; slave IRQ0 = RTC IRQ8
    out 0xa1,al
    mov al,0xf9                 ; master IRQ1 keyboard and IRQ2 cascade
    out 0x21,al
    call enable_rtc
 a_loop:
    inc dword [cs:loop_count]
    jmp a_loop
 b_entry:
    nop
    mov bx,0xb22b
    mov si,0x2222
    std
    call enable_rtc
    sti                         ; B is forked with IF=0
 b_loop:
    inc dword [cs:loop_count]
    jmp b_loop
 enable_rtc:
    mov al,0x0c
    out 0x70,al
    in al,0x71
    mov al,0x0b
    out 0x70,al
    in al,0x71
    or al,0x40
    out 0x71,al
    ret
%if MODE_V86
    mov eax,cr0                 ; unreachable; no software scheduler yield''')
    source = _replace(source, '''gp_handler:
    cli
%if MODE_PAGING''', '''gp_handler:
    cli
    cld
    ; Available to callers that explicitly elect a DOS cleanup path.
    mov al,0x0b
    out 0x70,al
    mov al,[ebp+saved_rtc_b]
    out 0x71,al
    mov al,0x0a
    out 0x70,al
    mov al,[ebp+saved_rtc_a]
    out 0x71,al
    mov al,0x0c
    out 0x70,al
    in al,0x71
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
pm16_entry:''', '''rtc_handler:
    push eax
    push ecx
    push edx
    mov eax,[ss:esp+12]
    mov [ss:ebp+outer_return],eax
    inc word [ss:ebp+outer_count]
    mov ax,[ss:ebp+scratch]
    mov [ss:ebp+observed_data],ax
    ; Clear RTC IRQ assertion then temporarily disable PIE until B starts.
    mov al,0x0c
    out 0x70,al
    in al,0x71
    mov [ss:ebp+rtc_regc],al  ; actual RTC IRQF/PF device evidence
    mov al,0x0b
    out 0x70,al
    in al,0x71
    and al,0xbf
    out 0x71,al
    stc
 outer_fetch:
    nop
    sti                         ; allow higher-priority real master IRQ1
 outer_wait:
    cmp byte [ss:ebp+key_count],2
    jb outer_wait
    cli
    mov al,0x20
    out 0xa0,al                ; actual slave EOI for IRQ8
 after_slave:
    nop                        ; checkpoint before master cascade EOI
    out 0x20,al
 after_master:
    pop edx
    pop ecx
    pop eax
    iretd

keyboard_handler:
    push eax
    push ecx
    push edx
    inc word [ss:ebp+inner_count]
    xor ecx,ecx
 key_drain:
    in al,0x64
    test al,1
    jz key_done
    in al,0x60
    mov [ss:ebp+key_bytes+ecx],al
    inc ecx
    cmp ecx,4
    jb key_drain
 key_done:
    test ecx,ecx
    jz key_empty
    mov eax,[ss:esp+12]
    mov [ss:ebp+inner_return],eax
    mov [ss:ebp+key_count],cl
 inner_hook:
    nop                        ; checkpoint with outer+inner before either EOI
    jmp short key_eoi
 key_empty:
    ; A second real PIC edge may remain latched after draining both bytes.
    ; Service it without inventing input or destroying the captured pair.
    inc word [ss:ebp+empty_irq_count]
 key_eoi:
    mov al,0x20
    out 0x20,al                ; actual master EOI for nested IRQ1
    pop edx
    pop ecx
    pop eax
    iretd
bits 16
pm16_entry:''')
    source = _replace(source, 'scratch: dw 0', '''scratch: dw 0
outer_count: dw 0
inner_count: dw 0
loop_count: dd 0
key_count: db 0
empty_irq_count: dw 0
key_bytes: times 4 db 0
outer_return: dd 0
inner_return: dd 0
observed_data: dw 0
rtc_regc: db 0
saved_master_mask: db 0
saved_slave_mask: db 0
saved_rtc_a: db 0
saved_rtc_b: db 0
b_stack: times 512 db 0
b_stack_top:''')
    if fault == 'inner-no-eoi':
        source = _replace(source,
            '    mov al,0x20\n    out 0x20,al                ; actual master EOI for nested IRQ1\n',
            '    ; Deliberately try IRETD with nested IRQ1 still un-EOIed.\n')
    elif fault == 'master-before-slave':
        source = _replace(source,
            '    out 0xa0,al                ; actual slave EOI for IRQ8',
            '    out 0x20,al                ; invalid master cascade EOI before slave')
    source = source.replace('dw mode_ready - $$, hook_site - $$, fetch_site - $$, scratch - $$',
                            'dw mode_ready - $$, inner_hook - $$, outer_fetch - $$, scratch - $$')
    data = assemble(directory, 'cascade', '%define MODE_V86 1\n%define MODE_PAGING 1\n' + source, nasm)
    offset = data.index(b'FCAS')
    fields = struct.unpack_from('<27H', data, offset + 4)
    names = ('ready', 'hook', 'fetch', 'scratch', 'gp', 'ret', 'pm', 'pt',
             'b_entry', 'outer_wait', 'inner_hook', 'after_slave', 'after_master',
             'outer_count', 'inner_count', 'key_count', 'key_bytes', 'outer_return',
             'inner_return', 'scratch2', 'observed_data', 'outer_fetch', 'ring0_stack',
             'vm_stack', 'b_stack', 'rtc_regc', 'empty_irq_count')
    result = dict(zip(names, fields))
    assert result['hook'] == result['inner_hook'] and result['scratch'] == result['scratch2']
    return data, result
