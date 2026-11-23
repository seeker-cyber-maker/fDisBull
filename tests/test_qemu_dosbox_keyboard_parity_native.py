"""Same-byte DOS guest oracle for BIOS text and explicit held-key delivery.

Uses the native clock inputs plus FDISBULL_DOSBOX. Set
FDISBULL_REQUIRE_QEMU_PAIRED_KEYBOARD=1 and FDISBULL_REQUIRE_QEMU_CLOCK=1
to require both native lanes.
"""
import json
import os
from pathlib import Path
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime
from test_qemu_dos_process_native import com_address, launch_options
from test_qemu_dosbox_parity_native import _exit_code, _owned_process


_TEXT = 'aA1! ?~z'
_EXPECTED_SCANS = [0x1e, 0x1e, 0x02, 0x02, 0x39, 0x35, 0x29, 0x2c]
_ASSEMBLY = r'''
bits 16
org 100h
    push cs
    pop ds

drain_boot_keys:
    mov ah,1
    int 16h
    jz ready
    xor ah,ah
    int 16h
    jmp drain_boot_keys

ready:
    nop
    mov si,keys
read_key:
    push si
    xor ah,ah
    int 16h
    pop si
    mov [si],ax
    add si,2
    cmp si,keys_end
    jb read_key
    mov ah,2
    int 16h
    and al,3
    mov [typed_shift],al
    mov byte [typed],1

wait_shift:
    mov ah,2
    int 16h
    and al,3
    jz wait_shift
    mov [shift_down],al
held:
    nop
wait_release:
    mov ah,2
    int 16h
    and al,3
    jnz wait_release
    mov [shift_up],al
released:
    nop
    mov ax,4c2ah
    int 21h

keys:
    times 8 dw 0
keys_end:
typed: db 0
typed_shift: db 0ffh
shift_down: db 0ffh
shift_up: db 0ffh
db 'KEY1'
dw ready,held,released,keys,typed,typed_shift,shift_down,shift_up
'''


def _park(debug, address, *, qemu):
    point = debug.breakpoint(address)
    try:
        options = {} if qemu else {'fast_forward': True}
        result = debug.run(timeout_ms=5000, **options)
        assert result['outcome'] == 'breakpoint', result
        stop = result['session']['stop_reason']
        if qemu:
            assert point['breakpoint_id'] in stop['breakpoint_ids'], result
        else:
            assert point['breakpoint_id'] == stop['breakpoint_id'], result
        return result
    finally:
        debug.delete_breakpoint(point['breakpoint_id'])


def _window(debug, milliseconds, *, qemu):
    if qemu:
        result = debug.clock_advance(milliseconds * 1_000_000, timeout_ms=5000)
        budget_receipt(result, milliseconds * 1_000_000)
        assert result['outcome'] == 'stopped', result
    else:
        result = debug.run(guest_ms=milliseconds, fast_forward=True, timeout_ms=5000)
        assert result['outcome'] == 'guest_time', result
    return result


def _observe(debug, offsets, samples, *, qemu):
    if qemu:
        info = debug.dos_process_info()
        assert info['state'] == 'active', info
        locations = {name: com_address(info, offset) for name, offset in offsets.items()}
    else:
        locations = {name: debug.static_base + offset - 0x100 for name, offset in offsets.items()}

    def read(name, length=1):
        alignment = {'space': 'physical'} if qemu else {}
        return bytes.fromhex(debug.memory(locations[name], length=length, **alignment)['hex'])

    _park(debug, locations['ready'], qemu=qemu)
    assert read('typed') == b'\0'
    assert read('keys', 2 * len(_TEXT)) == bytes(2 * len(_TEXT))
    armed = debug.keyboard.type(_TEXT, hold_ms=20, gap_ms=20)
    assert read('typed') == b'\0'
    timed = _window(debug, 1000, qemu=qemu)
    if qemu:
        assert timed['input_delivery']['state'] == 'dispatched', timed
    else:
        assert armed['delivery'] == 'queued', armed
    assert read('typed') == b'\1'
    raw = read('keys', 2 * len(_TEXT))
    samples.update(ascii_hex=raw[::2].hex(), ascii=raw[::2].decode('ascii', 'backslashreplace'),
                   scan_codes=list(raw[1::2]), shift_after_text=read('typed_shift')[0])
    assert read('shift_down') == read('shift_up') == b'\xff'

    lease = debug.keyboard.key_down('shift')['lease']
    _park(debug, locations['held'], qemu=qemu)
    samples['shift_held'] = read('shift_down')[0]
    _window(debug, 20, qemu=qemu)
    assert read('shift_up') == b'\xff'
    debug.keyboard.key_up(lease)
    _park(debug, locations['released'], qemu=qemu)
    samples['shift_released'] = read('shift_up')[0]
    options = {} if qemu else {'fast_forward': True}
    samples['exit_code'] = _exit_code(debug.run(timeout_ms=5000, **options), qemu=qemu)


def test_native_paired_bios_keyboard_consumes_mixed_text_and_owned_shift(
        tmp_path, clock_runtime, clock_disk):
    configured = os.environ.get('FDISBULL_DOSBOX')
    if not configured:
        message = 'Native paired keyboard requires FDISBULL_DOSBOX'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_PAIRED_KEYBOARD') == '1':
            pytest.fail(message)
        pytest.skip(message)
    dosbox = Path(configured).expanduser().resolve(strict=True)
    assert dosbox.is_file() and os.access(dosbox, os.X_OK)
    code = assemble(tmp_path, 'bios-keyboard-pair', _ASSEMBLY, clock_runtime['nasm'])
    symbols = ('ready', 'held', 'released', 'keys', 'typed', 'typed_shift', 'shift_down', 'shift_up')
    assert code[-20:-16] == b'KEY1'
    offsets = dict(zip(symbols, struct.unpack('<8H', code[-16:]), strict=True))
    binary = tmp_path / 'PAIRKEY.COM'
    binary.write_bytes(code)
    receipt = dict(source_sha256=digest(binary), dosbox_sha256=digest(dosbox),
                   qemu_sha256=digest(clock_runtime['executable']),
                   boot_sha256=clock_disk['prepared_sha256'], samples={})
    try:
        with Project.create(tmp_path / 'keyboard-pair.fdb', binary, image='com') as project:
            project.analyze(max_instructions=512)
            for qemu in (False, True):
                options = launch_options(clock_runtime, clock_disk, qemu_clock='virtual') if qemu else {}
                executable = clock_runtime['executable'] if qemu else dosbox
                row = receipt['samples']['qemu' if qemu else 'dosbox'] = {}
                with project.debugger(str(executable), tmp_path, **options) as debug:
                    owner = _owned_process(debug, qemu=qemu)
                    _observe(debug, offsets, row, qemu=qemu)
                assert owner.poll() == 0
                row['owner_reaped'] = True
    finally:
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'keyboard-pair-receipt.json').write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    expected = dict(ascii_hex=_TEXT.encode('ascii').hex(), ascii=_TEXT,
                    scan_codes=_EXPECTED_SCANS, shift_after_text=0,
                    shift_held=2, shift_released=0, exit_code=42, owner_reaped=True)
    assert receipt['samples'] == {'dosbox': expected, 'qemu': expected}
