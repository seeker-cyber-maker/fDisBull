"""One authored COM: IRQ1 make/break and BIOS timer ticks, with no video oracle."""
import struct

from support.dos_process_fixture import assemble


def movement_guest(directory, nasm):
    code = assemble(directory, 'observed-movement', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
    xor ax,ax
    mov es,ax
    mov word [es:9*4],keyboard_irq
    mov ax,cs
    mov [es:9*4+2],ax
    mov ax,40h
    mov es,ax
    mov ax,[es:6ch]
    mov [last_tick],ax
    mov al,0fch
    out 21h,al
    mov al,0ffh
    out 0a1h,al
    sti
ready:
    nop
main:
    cli
    mov ax,[es:6ch]
    cmp ax,[last_tick]
    je idle
    mov [last_tick],ax
    inc word [ticks]
    cmp byte [held],0
    je quiet_tick
    inc word [position]
    mov byte [quiet],0
    mov byte [settled],0
    jmp idle
quiet_tick:
    cmp byte [quiet],2
    jae is_settled
    inc byte [quiet]
    cmp byte [quiet],2
    jb idle
is_settled:
    mov byte [settled],1
idle:
    sti
    hlt
    jmp main
keyboard_irq:
    push ax
    push bx
    push ds
    push cs
    pop ds
    in al,64h
    test al,1
    jz eoi
    test al,20h
    jnz eoi
    in al,60h
    xor bx,bx
    mov bl,[edge_count]
    cmp bl,16
    jae classify
    mov [edges+bx],al
    inc byte [edge_count]
classify:
    cmp al,1eh
    jne break_key
    inc byte [makes]
    mov byte [held],1
    mov byte [settled],0
    mov byte [quiet],0
    jmp irq_fence
break_key:
    cmp al,9eh
    jne irq_fence
    inc byte [breaks]
    mov byte [held],0
    mov byte [settled],0
    mov byte [quiet],0
irq_fence:
    nop
eoi:
    mov al,20h
    out 20h,al
    pop ds
    pop bx
    pop ax
    iret
state:
    db 'MV01'
position: dw 0
ticks: dw 0
held: db 0
settled: db 1
makes: db 0
breaks: db 0
edge_count: db 0
edges: times 16 db 0
quiet: db 2
last_tick: dw 0
    db 'MVS1'
    dw ready,irq_fence,state,position,ticks,held,settled,makes,breaks,edge_count,edges
''', nasm)
    assert code[-26:-22] == b'MVS1'
    names = ('ready', 'irq_fence', 'state', 'position', 'ticks', 'held', 'settled',
             'makes', 'breaks', 'edge_count', 'edges')
    return code, dict(zip(names, struct.unpack_from('<11H', code, len(code)-22), strict=True))
