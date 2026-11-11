"""Authored DOS protected/V86 checkpoint and layer/hook witnesses."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, assemble, prepare_dos_baseline


def _inputs():
    keys = ('FDISBULL_QEMU_LAYERS', 'FDISBULL_QEMU_DOS_BOOT_IMAGE',
            'FDISBULL_QEMU_DOS_MCOPY', 'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')
    values = {key: os.environ.get(key) for key in keys}
    values['NASM'] = os.environ.get('NASM') or shutil.which('nasm')
    missing = [key for key, value in values.items() if not value]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('Missing DOS mode checkpoint inputs: ' + ', '.join(missing))
        pytest.skip('Supply DOS mode checkpoint inputs: ' + ', '.join(missing))
    return values


_SOURCE = r'''
bits 16
org 100h
    jmp start
    db 'FMOD'
    dw mode_ready - $$, hook_site - $$, fetch_site - $$, scratch - $$
%if MODE_V86
    dw gp_handler - $$, real_return - $$, pm_ready - $$, page_table_ptr - $$
%else
    dw 0, real_return - $$, 0, 0
%endif
start:
    push cs
    pop ds
    mov [saved_ss], ss
    mov [saved_sp], sp
%if MODE_V86
    sidt [saved_idtr]
    xor eax,eax
    mov ax,cs
    shl eax,4
    mov ebp,eax
    mov edx,eax
    mov [gdt_code16+2],ax
    shr eax,16
    mov [gdt_code16+4],al
    mov [gdt_code16+7],ah
    mov eax,edx
    add eax,gdt
    mov [gdtr+2],eax
    mov eax,edx
    add eax,pm_entry
    mov [pm_jump],eax
    mov eax,edx
    add eax,tss
    mov [gdt_tss+2],ax
    shr eax,16
    mov [gdt_tss+4],al
    mov [gdt_tss+7],ah
    mov eax,edx
    add eax,idt
    mov [idtr+2],eax
    mov eax,edx
    add eax,gp_handler
    mov [idt+13*8],ax
    shr eax,16
    mov [idt+13*8+6],ax
    mov word [idt+13*8+2],8
    mov word [idt+13*8+4],0x8e00
    mov eax,edx
    add eax,ring0_stack_top
    mov [tss+4],eax
    mov word [tss+8],0x10
    mov ax,cs
    mov [real_jump+4],ax
    mov [real_jump16+2],ax
    lgdt [gdtr]
    cli
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp dword far [pm_jump]
bits 32
pm_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    lea esp,[ebp+ring0_stack_top]
    mov ax,0x18
    ltr ax
    lidt [ebp+idtr]
%if MODE_PAGING
    lea edi,[ebp+page_buffers+4095]
    and edi,0xfffff000
    lea esi,[edi+4096]
    mov [ebp+page_table_ptr],esi
    mov eax,esi
    or eax,7
    mov [edi],eax
    lea edx,[edi+4]
    xor eax,eax
    mov ecx,1023
clear_directory:
    mov [edx],eax
    add edx,4
    loop clear_directory
    mov edx,esi
    mov eax,7
    mov ecx,1024
fill_table:
    mov [edx],eax
    add eax,4096
    add edx,4
    loop fill_table
    mov cr3,edi
    mov eax,cr0
    or eax,0x80000000
    mov cr0,eax
%endif
pm_ready:
    movzx edx,word [ebp+real_jump+4]
    push edx                  ; GS, FS, DS, ES, SS
    push edx
    push edx
    push edx
    push edx
    push dword vm_stack_top
    push dword 0x23002        ; VM=1, IOPL=3, IF=0
    push edx                  ; VM86 CS
    push dword v86_start
    iretd
bits 16
v86_start:
%else
    cli
    mov eax,cr0
    or al,1
    mov cr0,eax
%endif
mode_ready:
    nop
fetch_site:
    nop
    mov cx,2
hook_site:
    nop
    inc word [cs:scratch]
    loop hook_site
%if MODE_V86
    mov eax,cr0               ; VM86 #GP enters authored monitor below
    jmp short $
bits 32
gp_handler:
    cli
%if MODE_PAGING
    mov eax,cr0
    and eax,0x7fffffff
    mov cr0,eax
%endif
    mov ax,0x10
    mov ds,ax
    jmp far [ebp+pm16_jump]
bits 16
pm16_entry:
    mov ax,0x28
    mov ss,ax
    mov ds,ax
    mov es,ax
    mov eax,cr0
    and al,0xfe
    mov cr0,eax
    jmp far [cs:real_jump16]
%else
    mov eax,cr0
    and al,0xfe
    mov cr0,eax
    jmp short real_return
%endif
real_return:
%if MODE_V86
    lidt [cs:saved_idtr]
%endif
    mov ax,[cs:saved_ss]
    mov ss,ax
    mov sp,[cs:saved_sp]
    push cs
    pop ds
    push cs
    pop es
    sti
    mov ax,0x4c2a
    int 0x21
saved_ss: dw 0
saved_sp: dw 0
scratch: dw 0
%if MODE_V86
align 8
gdt:
    dq 0
    dq 0x00cf9a000000ffff     ; flat 32-bit code
    dq 0x00cf92000000ffff     ; flat 32-bit data
gdt_tss:
    dw 103,0
    db 0,0x89,0,0
gdt_code16:
    dw 0xffff,0
    db 0,0x9a,0,0
    dq 0x000092000000ffff     ; 16-bit data cache for real-mode return
gdt_end:
gdtr: dw gdt_end-gdt-1
    dd 0
pm_jump: dd 0
    dw 8
real_jump: dd real_return
    dw 0
pm16_jump: dd pm16_entry
    dw 0x20
real_jump16: dw real_return
    dw 0
idtr: dw 14*8-1
    dd 0
saved_idtr: times 6 db 0
idt: times 14*8 db 0
tss: times 104 db 0
ring0_stack: times 256 db 0
ring0_stack_top:
vm_stack: times 256 db 0
vm_stack_top:
page_table_ptr: dd 0
%if MODE_PAGING
page_buffers: times 12288 db 0
%endif
%endif
'''


def _fixture(directory, nasm, mode):
    source = assemble(directory, 'mode-' + mode,
                      '%define MODE_V86 ' + ('1\n' if mode in ('v86', 'paged') else '0\n')
                      + '%define MODE_PAGING ' + ('1\n' if mode == 'paged' else '0\n') + _SOURCE, nasm)
    marker = source.index(b'FMOD')
    ready, hook, fetch, scratch, gp, ret, pm, pt = struct.unpack_from('<8H', source, marker+4)
    return source, dict(ready=ready, hook=hook, fetch=fetch, scratch=scratch, gp=gp, ret=ret, pm=pm, pt=pt)


def _launch(project, runtime, directory, disk, *, clock_profile=None, retrace=None):
    options = {}
    if clock_profile is not None:
        options['qemu_clock'] = clock_profile
    if retrace is not None:
        options['qemu_retrace'] = retrace
    return project.debugger(runtime['FDISBULL_QEMU_LAYERS'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000, **options)


@pytest.mark.parametrize(('mode', 'profile'), [
    ('protected', 'standard'), ('v86', 'standard'),
    ('paged', 'standard'), ('paged', 'virtual-precise'),
])
def test_native_mode_checkpoint_restores_source_layers_and_repeat_hook(tmp_path, mode, profile):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_sha = hashlib.sha256(boot.read_bytes()).hexdigest()
    options = {'config': b'SWITCHES=/F\r\n' + BASELINE_CONFIG} if profile == 'virtual-precise' else {}
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'], **options)
    data, marker = _fixture(tmp_path, runtime['NASM'], mode)
    source = tmp_path / 'MODE.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'mode.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        fetch = project.debug_layer('mode-fetch', kind='execute', patches=[dict(
            address=hex(static+marker['fetch']), expected_hex='90', data_hex='f8')])['layer']
        ram = project.debug_layer('mode-ram', kind='ram', patches=[dict(
            address=hex(static+marker['scratch']), expected_hex='0000', data_hex='3412')])['layer']
        with _launch(project, runtime, tmp_path, disk,
                     clock_profile='virtual' if profile == 'virtual-precise' else None,
                     retrace='precise' if profile == 'virtual-precise' else None) as debug:
            process = debug.dos_process_info(); base = process['source_mapping']['runtime_base']
            debug.layers([fetch, ram])
            ready = debug.breakpoint(base+marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            registers = debug.registers()
            expected_mode = 'v86' if mode == 'paged' else mode
            assert registers['cpu_mode'] == expected_mode
            assert registers['address_state']['paging'] is (mode == 'paged')
            name = 'rax' if 'rax' in registers['registers'] else 'eax'
            value = int(registers['registers'][name], 16)
            hook = debug.hook(hex(static+marker['hook']), space='source', once=False,
                max_hits=3, actions=[dict(op='registers', registers={name: dict(expected=value, value=value)})])
            first = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert first['outcome'] == 'hook' and first['hook_hits'][0]['hit'] == 1
            before = debug.registers()
            if profile == 'virtual-precise':
                clock = debug.clock_observe()
                retrace_before = debug.retrace_observe()
                assert retrace_before['observed_ns'] == clock['virtual_ns']
            saved = debug.save_state()
            old = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert old.poll() is not None and restored['source_binding_restored']
            after = debug.registers()
            assert after['cpu_mode'] == expected_mode and after['address_state'] == before['address_state']
            assert after['registers'] == before['registers']
            if profile == 'virtual-precise':
                restored_clock = debug.clock_observe()
                retrace_after = debug.retrace_observe()
                assert restored_clock['virtual_ns'] == clock['virtual_ns']
                assert retrace_after['observed_ns'] == restored_clock['virtual_ns']
                assert (retrace_after['raw'], retrace_after['phase'], retrace_after['timing']) == (
                    retrace_before['raw'], retrace_before['phase'], retrace_before['timing'])
            assert debug.code(hex(static+marker['fetch']), length=1, space='source')['hex'] == 'f8'
            assert debug.memory(base+marker['scratch'], length=2, space='physical')['hex'] == '3412'
            second = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert second['outcome'] == 'hook' and second['hook_hits'][0]['hit'] == 2
            assert second['hook_hits'][0]['hook'] == hook['hook']
            debug.delete_hook(hook['hook'])
            debug.layers([], conflict='keep_changed')
            if mode in ('v86', 'paged'):
                point = debug.breakpoint(base+marker['gp'])
                stop = debug.run(timeout_ms=5000)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
                point = debug.breakpoint(base+marker['ret'])
                stop = debug.run(timeout_ms=5000)
                assert stop['outcome'] == 'breakpoint', stop
                debug.delete_breakpoint(point['breakpoint_id'])
            done = debug.run(timeout_ms=15000)
            if done['outcome'] != 'guest_exit':
                (tmp_path / 'mode-failure.json').write_text(json.dumps(done, indent=2))
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42
    assert source.read_bytes() == data and hashlib.sha256(boot.read_bytes()).hexdigest() == boot_sha


@pytest.mark.parametrize('mode', ['v86', 'paged'])
def test_native_protected_loaded_descriptors_checkpoint_and_return(tmp_path, mode):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    data, marker = _fixture(tmp_path, runtime['NASM'], mode)
    source = tmp_path / 'MODE.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'mode.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk) as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['pm'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            before = debug.registers()
            assert before['cpu_mode'] == 'protected'
            state = before['address_state']
            assert state['code_bits'] == 32 and state['stack_bits'] == 32
            assert state['paging'] is (mode == 'paged')
            assert [int(state['segments'][s]['selector'], 16) for s in ('cs', 'ds', 'ss')] == [8, 16, 16]
            if mode == 'paged':
                table = int.from_bytes(bytes.fromhex(debug.memory(base + marker['pt'], length=4)['hex']), 'little')
                entry = debug.memory(table, length=4)['hex']
                debug.write_memory(table, '07000900', expected_hex=entry)
                with pytest.raises(ValueError, match='identity-mapped'):
                    debug.save_state()
                debug.write_memory(table, entry, expected_hex='07000900')
            saved = debug.save_state()
            debug.load_state(saved['artifact'])
            after = debug.registers()
            assert after['address_state'] == before['address_state']
            assert after['registers'] == before['registers']
            done = debug.run(timeout_ms=15000)
            assert done['outcome'] == 'guest_exit', done
            assert done['process']['termination']['code'] == 42
