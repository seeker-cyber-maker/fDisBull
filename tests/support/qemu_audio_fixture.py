"""Authored DOS PIT speaker witness; no host or debugger code in the guest."""
import struct

from support.dos_process_fixture import assemble

PIT_INPUT_HZ = 1_193_182
SPEAKER_DIVISOR = 1193


def speaker_tone(directory, nasm):
    code = assemble(directory, 'audio-speaker', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    cli
ready:
    nop
    mov al,0b6h
    out 43h,al
    mov ax,''' + str(SPEAKER_DIVISOR) + r'''
    out 42h,al
    mov al,ah
    out 42h,al
    in al,61h
    or al,3
    out 61h,al
tone_ready:
    nop
tone_loop:
    cmp byte [phase],0
    je tone_loop
    in al,61h
    and al,0fch
    out 61h,al
quiet_ready:
    nop
quiet_loop:
    jmp quiet_loop
phase: db 0
    db 'AUD1'
    dw ready,tone_ready,quiet_ready,phase
''', nasm)
    assert code[-12:-8] == b'AUD1'
    return code, dict(zip(('ready_ip', 'tone_ready_ip', 'quiet_ready_ip', 'phase_ip'),
                         struct.unpack('<4H', code[-8:]), strict=True))
