"""Authored VGA mutations and independent guest register reads.

The COM program runs from a caller-supplied FreeDOS disk. It records port-visible
register bytes, discovers the actual PCI VGA register BAR, and uses a private
flat FS descriptor for guest MMIO writes. It never consumes a host configuration
receipt. Distinct fences distinguish each completed mutation from dispatch.
"""
from __future__ import annotations

import struct

from support.dos_process_fixture import assemble


COMMANDS = {
    'page': (1, 'page_done_ip'),
    'pitch': (2, 'pitch_done_ip'),
    'panning': (3, 'panning_done_ip'),
    'line_compare': (4, 'line_compare_done_ip'),
    'page_aba': (5, 'page_aba_done_ip'),
    'noop': (6, 'noop_done_ip'),
    'protected_cr0': (7, 'protected_cr0_done_ip'),
    'protected_cr7': (8, 'protected_cr7_done_ip'),
    'selectors': (9, 'selectors_done_ip'),
    'disable_display': (10, 'display_disabled_ip'),
    'enable_display': (11, 'display_enabled_done_ip'),
    'palette_vram': (12, 'palette_vram_done_ip'),
    'vbe8': (13, 'vbe8_done_ip'),
    'vbe32': (14, 'vbe32_done_ip'),
    'vbe_offsets': (15, 'vbe_offsets_done_ip'),
    'vbe_bank': (16, 'vbe_bank_done_ip'),
    'vbe_dac': (17, 'vbe_dac_done_ip'),
    'qext_big': (18, 'qext_big_done_ip'),
    'qext_noop': (19, 'qext_noop_done_ip'),
    'qext_invalid': (20, 'qext_invalid_done_ip'),
    'qext_little': (21, 'qext_little_done_ip'),
    'mmio_aliases': (22, 'mmio_aliases_done_ip'),
    'invalid_text': (23, 'invalid_text_done_ip'),
    'attribute_pending': (24, 'attribute_pending_ip'),
    'mono_alias': (25, 'mono_alias_done_ip'),
}


def configuration_ports(directory, nasm):
    code = assemble(directory, 'vga-configuration', r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
    push cs
    pop ds
    cli
    cld
    mov ax,0a000h
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,32000
    rep stosw
    ; Own black, red and green DAC entries and two marker locations.
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    out dx,al
    out dx,al
    out dx,al
    dec dx
    mov al,4
    out dx,al
    inc dx
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    out dx,al
    dec dx
    mov al,2
    out dx,al
    inc dx
    xor al,al
    out dx,al
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    mov byte [es:10*320+10],4
    call snapshot
    ; Establish the CR0..7 protection condition explicitly.
    mov al,11h
    mov ah,[crtc+11h]
    or ah,80h
    call write_cr
    call snapshot
    mov al,[crtc+0dh]
    mov [original_page],al
    mov al,[crtc+13h]
    mov [original_pitch],al
    mov al,[crtc+18h]
    mov [original_line],al
    mov al,[attribute_controls+3]
    mov [original_panning],al
    call discover_mmio
ready:
    nop
dispatch:
    mov al,[command]
    cmp al,1
    je change_page
    cmp al,2
    je change_pitch
    cmp al,3
    je change_panning
    cmp al,4
    je change_line_compare
    cmp al,5
    je page_aba
    cmp al,6
    je noop
    cmp al,7
    je protected_cr0
    cmp al,8
    je protected_cr7
    cmp al,9
    je selectors
    cmp al,10
    je disable_display
    cmp al,11
    je enable_display
    cmp al,12
    je palette_vram
    cmp al,13
    je vbe8
    cmp al,14
    je vbe32
    cmp al,15
    je vbe_offsets
    cmp al,16
    je vbe_bank
    cmp al,17
    je vbe_dac
    cmp al,18
    je qext_big
    cmp al,19
    je qext_noop
    cmp al,20
    je qext_invalid
    cmp al,21
    je qext_little
    cmp al,22
    je mmio_aliases
    cmp al,23
    je invalid_text
    cmp al,24
    je attribute_pending_setup
    cmp al,25
    je mono_alias
    jmp dispatch

%macro finish 1
    call snapshot
    mov byte [command],0
%1:
    nop
    jmp dispatch
%endmacro

%macro write_vbe 2
    mov dx,1ceh
    mov ax,%1
    out dx,ax
    inc dx
    mov ax,%2
    out dx,ax
%endmacro

change_page:
    mov al,0dh
    mov ah,[original_page]
    xor ah,20h
    call write_cr
    finish page_done

change_pitch:
    mov al,13h
    mov ah,[original_pitch]
    xor ah,1
    call write_cr
    finish pitch_done

change_panning:
    mov al,13h
    mov ah,[original_panning]
    xor ah,1
    call write_attribute
    finish panning_done

change_line_compare:
    mov al,18h
    mov ah,[original_line]
    xor ah,1
    call write_cr
    finish line_compare_done

page_aba:
    mov al,0dh
    mov ah,[original_page]
    xor ah,20h
    call write_cr
    mov al,0dh
    mov ah,[original_page]
    call write_cr
    finish page_aba_done

noop:
    mov al,0dh
    mov ah,[crtc+0dh]
    call write_cr
    finish noop_done

protected_cr0:
    mov al,0
    mov ah,[crtc]
    xor ah,1
    call write_cr
    finish protected_cr0_done

protected_cr7:
    mov al,7
    mov ah,[crtc+7]
    xor ah,11h                ; bit 0 protected; bit 4 remains writable
    call write_cr
    finish protected_cr7_done

selectors:
    mov dx,3c4h
    mov al,7
    out dx,al
    mov dx,3ceh
    mov al,0fh
    out dx,al
    mov dx,[crtc_port]
    mov al,69h
    out dx,al
    mov dx,1ceh
    mov ax,9
    out dx,ax
    mov dx,[status_port]
    in al,dx
    mov dx,3c0h
    mov al,39h                ; selector only, display stays enabled
    out dx,al
    finish selectors_done

disable_display:
    mov dx,[status_port]
    in al,dx
    mov dx,3c0h
    xor al,al
    out dx,al
    finish display_disabled

enable_display:
    mov dx,[status_port]
    in al,dx
    mov dx,3c0h
    mov al,20h
    out dx,al
    finish display_enabled_done

palette_vram:
    mov dx,3c8h
    mov al,4
    out dx,al
    inc dx
    xor al,al
    out dx,al
    out dx,al
    mov al,63
    out dx,al
    mov al,0
    mov ah,1                  ; excluded AR00 palette entry
    call write_attribute
    mov byte [es:10*320+20],2
    finish palette_vram_done

vbe8:
    write_vbe 1,320
    write_vbe 2,200
    write_vbe 3,8
    write_vbe 4,81h           ; enabled, preserve VRAM
    finish vbe8_done

vbe32:
    write_vbe 3,32
    finish vbe32_done

vbe_offsets:
    write_vbe 6,328
    write_vbe 8,4
    write_vbe 9,2
    finish vbe_offsets_done

vbe_bank:
    write_vbe 5,3
    finish vbe_bank_done

vbe_dac:
    write_vbe 4,0a1h          ; enabled + preserve + eight-bit DAC
    finish vbe_dac_done

qext_big:
    mov edi,[mmio_bar]
    mov dword [fs:edi+604h],0bebebebeh
    mov eax,[fs:edi+604h]
    mov [qext_readback],eax
    finish qext_big_done

qext_noop:
    mov edi,[mmio_bar]
    mov dword [fs:edi+604h],0bebebebeh
    mov eax,[fs:edi+604h]
    mov [qext_readback],eax
    finish qext_noop_done

qext_invalid:
    mov edi,[mmio_bar]
    mov dword [fs:edi+604h],0deadbeefh
    mov eax,[fs:edi+604h]
    mov [qext_readback],eax
    finish qext_invalid_done

qext_little:
    mov edi,[mmio_bar]
    mov dword [fs:edi+604h],01e1e1e1eh
    mov eax,[fs:edi+604h]
    mov [qext_readback],eax
    finish qext_little_done

mmio_aliases:
    mov edi,[mmio_bar]
    mov al,13h
    mov ah,[original_pitch]
    xor ah,1
    mov [fs:edi+414h],ax       ; VGA index/data word alias
    mov word [fs:edi+50ah],2   ; Bochs VBE BANK register alias
    finish mmio_aliases_done

invalid_text:
    ; Construct a one-cell text configuration. QEMU's text renderer rejects
    ; height*width <= 1 before resizing and leaves the previous surface.
    mov al,11h
    mov ah,[crtc+11h]
    and ah,7fh
    call write_cr
    mov al,1
    xor ah,ah
    call write_cr
    mov al,12h
    xor ah,ah
    call write_cr
    mov al,7
    mov ah,[crtc+7]
    and ah,0bdh               ; clear vertical display-end bits 8 and 9
    call write_cr
    mov al,9
    mov ah,[crtc+9]
    and ah,0e0h               ; character height = one scanline
    call write_cr
    mov dx,3ceh
    mov al,6
    out dx,al
    inc dx
    mov al,[graphics+6]
    and al,0feh               ; switch graphics/text interpretation last
    out dx,al
    finish invalid_text_done

attribute_pending_setup:
    mov al,12h
    xor ah,ah
    call write_attribute
    mov dx,[status_port]
    in al,dx
    mov dx,3c0h
    mov al,32h
    out dx,al                 ; leave attribute controller awaiting data
attribute_pending:
    nop
    mov al,0fh
    out dx,al
    finish attribute_done

mono_alias:
    mov dx,3c2h
    mov al,[misc_output]
    and al,0feh
    out dx,al
    mov word [crtc_port],3b4h
    mov word [status_port],3bah
    mov al,0dh
    mov ah,[original_page]
    xor ah,20h
    call write_cr
    mov dx,3d4h               ; old color-port alias is now ignored
    mov al,0dh
    out dx,al
    inc dx
    mov al,[original_page]
    xor al,40h
    out dx,al
    finish mono_alias_done

write_cr:
    mov dx,[crtc_port]
    out dx,al
    inc dx
    mov al,ah
    out dx,al
    ret

write_attribute:
    push ax
    mov dx,[status_port]
    in al,dx
    pop ax
    or al,[attribute_display_mask]
    mov dx,3c0h
    out dx,al
    mov al,ah
    out dx,al
    ret

snapshot:
    pusha
    mov dx,3cch
    in al,dx
    mov [misc_output],al
    mov word [crtc_port],3d4h
    mov word [status_port],3dah
    test al,1
    jnz .ports_selected
    mov word [crtc_port],3b4h
    mov word [status_port],3bah
.ports_selected:
    mov dx,3cah
    in al,dx
    mov [feature_control],al
    xor bx,bx
.sequencer:
    mov dx,3c4h
    mov al,bl
    out dx,al
    inc dx
    in al,dx
    mov [sequencer+bx],al
    inc bx
    cmp bx,8
    jb .sequencer
    xor bx,bx
.graphics:
    mov dx,3ceh
    mov al,bl
    out dx,al
    inc dx
    in al,dx
    mov [graphics+bx],al
    inc bx
    cmp bx,16
    jb .graphics
    xor bx,bx
.crtc:
    mov dx,[crtc_port]
    mov al,bl
    out dx,al
    inc dx
    in al,dx
    mov [crtc+bx],al
    inc bx
    cmp bx,256
    jb .crtc
    mov dx,[status_port]
    in al,dx                  ; index phase, without changing display enable
    mov dx,3c0h
    in al,dx
    and al,20h
    mov [attribute_display_mask],al
    mov [display_enabled],al
    xor bx,bx
.attributes:
    mov dx,[status_port]
    in al,dx
    mov dx,3c0h
    mov al,bl
    add al,10h
    or al,[attribute_display_mask]
    out dx,al
    inc dx
    in al,dx
    mov [attribute_controls+bx],al
    inc bx
    cmp bx,5
    jb .attributes
    mov dx,[status_port]
    in al,dx
    xor bx,bx
.vbe:
    mov dx,1ceh
    mov ax,bx
    out dx,ax
    inc dx
    in ax,dx
    mov si,bx
    shl si,1
    mov [vbe+si],ax
    inc bx
    cmp bx,10
    jb .vbe
    popa
    ret

discover_mmio:
    ; Read the real PCI identity and BAR. No host-derived address is injected.
    mov ebx,80000000h
    mov cx,256                ; bus zero, every device/function
.scan:
    mov dx,0cf8h
    mov eax,ebx
    out dx,eax
    mov dx,0cfch
    in eax,dx
    cmp eax,11111234h         ; exact QEMU standard PCI VGA device
    je .found
    add ebx,100h
    loop .scan
    ret
.found:
    mov [pci_identity],eax
    mov [pci_address],ebx
    mov dx,0cf8h
    mov eax,ebx
    or eax,4
    out dx,eax
    mov dx,0cfch
    in ax,dx
    mov [pci_command],ax
    test ax,2
    jz .failed
    mov dx,0cf8h
    mov eax,ebx
    or eax,18h                ; BAR2 contains QEMU VGA register aliases
    out dx,eax
    mov dx,0cfch
    in eax,dx
    and eax,0fffffff0h
    mov [mmio_bar],eax
    test eax,eax
    jz .failed
    cmp eax,0fffffff0h
    je .failed
    ; Establish a flat FS cache, then return immediately to real mode. The
    ; authored program never executes a BIOS interrupt after this setup.
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,gdt
    mov [gdtr+2],eax
    lgdt [gdtr]
    mov eax,cr0
    or eax,1
    mov cr0,eax
    jmp short .protected
.protected:
    mov ax,8
    mov fs,ax
    mov eax,cr0
    and eax,0fffffffeh
    mov cr0,eax
    jmp short .real
.real:
    mov edi,[mmio_bar]
    mov eax,[fs:edi+600h]
    mov [qext_size],eax
    cmp eax,8
    jne .failed
    mov eax,[fs:edi+604h]
    mov [qext_readback],eax
    mov byte [pci_status],1
.failed:
    ret

align 8
gdt:
    dq 0
    dq 00cf92000000ffffh      ; writable data, base zero, four-GiB limit
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
crtc_port: dw 3d4h
status_port: dw 3dah
command: db 0
original_page: db 0
original_pitch: db 0
original_line: db 0
original_panning: db 0
attribute_display_mask: db 20h
pci_status: db 0
pci_identity: dd 0
pci_address: dd 0
pci_command: dw 0
mmio_bar: dd 0
qext_size: dd 0
qext_readback: dd 0
misc_output: db 0
feature_control: db 0
display_enabled: db 0
sequencer: times 8 db 0
graphics: times 16 db 0
crtc: times 256 db 0
attribute_controls: times 5 db 0
vbe: times 10 dw 0
    db 'VCF1'
    dw ready,dispatch,command
    dw page_done,pitch_done,panning_done,line_compare_done,page_aba_done
    dw noop_done,protected_cr0_done,protected_cr7_done,selectors_done
    dw display_disabled,display_enabled_done,palette_vram_done
    dw vbe8_done,vbe32_done,vbe_offsets_done,vbe_bank_done,vbe_dac_done
    dw qext_big_done,qext_noop_done,qext_invalid_done,qext_little_done
    dw mmio_aliases_done,invalid_text_done,attribute_pending,attribute_done
    dw mono_alias_done
    dw pci_status,pci_identity,pci_address,pci_command,mmio_bar
    dw qext_size,qext_readback,misc_output,feature_control,display_enabled
    dw sequencer,graphics,crtc,attribute_controls,vbe
''', nasm)
    names = (
        'ready_ip', 'dispatch_ip', 'command_ip',
        'page_done_ip', 'pitch_done_ip', 'panning_done_ip', 'line_compare_done_ip',
        'page_aba_done_ip', 'noop_done_ip', 'protected_cr0_done_ip',
        'protected_cr7_done_ip', 'selectors_done_ip', 'display_disabled_ip',
        'display_enabled_done_ip', 'palette_vram_done_ip', 'vbe8_done_ip',
        'vbe32_done_ip', 'vbe_offsets_done_ip', 'vbe_bank_done_ip',
        'vbe_dac_done_ip', 'qext_big_done_ip', 'qext_noop_done_ip',
        'qext_invalid_done_ip', 'qext_little_done_ip', 'mmio_aliases_done_ip',
        'invalid_text_done_ip', 'attribute_pending_ip', 'attribute_done_ip',
        'mono_alias_done_ip', 'pci_status_ip', 'pci_identity_ip', 'pci_address_ip',
        'pci_command_ip', 'mmio_bar_ip', 'qext_size_ip', 'qext_readback_ip',
        'misc_output_ip', 'feature_control_ip', 'display_enabled_ip',
        'sequencer_ip', 'graphics_ip', 'crtc_ip', 'attribute_controls_ip', 'vbe_ip',
    )
    size = 4 + 2 * len(names)
    assert code[-size:-size + 4] == b'VCF1'
    offsets = struct.unpack('<' + 'H' * len(names), code[-2 * len(names):])
    return code, dict(zip(names, offsets, strict=True))
