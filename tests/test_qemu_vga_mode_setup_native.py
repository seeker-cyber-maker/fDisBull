"""Opt-in standard-VGA BIOS mode setup witness on a pinned native producer."""
from pathlib import Path
import os
import re
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_SETUP') != '1',
    reason='Select the pinned native VGA mode-setup witness',
)

QEMU = '91321d463ad4b06e183f46cc1ab356dc4b2a23dd831531761b7f39845a835fe9'
VGA_BIOS = '651513519f9e0d5b99d3b051a8f5c68db69e987339b59a441d371068c34c146b'
QEMU_IMG = '9c186cd24d95835b21a17f97b3f2ec09b139914b27146f663ae36761fd07623f'
BODY = r'''
bits 16
org 100h
    nop
    mov ax,3
    int 10h
ready:
    nop
    mov ax,13h
    int 10h
first:
    nop
    push cs
    pop ds
wait_command:
    sti
    cmp byte [go],0
    jne reapply
    hlt
    jmp wait_command
reapply:
    mov ax,13h
    int 10h
second:
    nop
    mov dx,3c4h
    xor al,al
    out dx,al
    inc dx
    in al,dx
    out dx,al
noop:
    nop
    jmp noop
go: db 0
    db 'VGA1'
    dw ready,first,second,noop,go
'''


def _packed_writes(port, values):
    for index, value in enumerate(values):
        yield (port, index)
        yield (port + 1, value)


def _mode_setup_suffix(raw):
    # SeaBIOS stdvga_set_mode programs entire banks, unlocks CRTC0..7,
    # then writes miscellaneous output and reenables the display.
    return [
        *_packed_writes(0x3c4, raw['sequencer'][:5]),
        *_packed_writes(0x3ce, raw['graphics'][:9]),
        (0x3d4, 0x11), (0x3d5, 0),
        *_packed_writes(0x3d4, raw['crtc'][:25]),
        (0x3c2, raw['misc-output']), (0x3c0, 0x20),
    ]


def test_native_mode13_setup_and_reapply_are_distinct_from_warm_stream_attach(
        tmp_path, clock_runtime, clock_disk):
    assert digest(clock_runtime['executable']) == QEMU
    firmware = clock_runtime['firmware']
    assert firmware and digest(Path(firmware) / 'vgabios-stdvga.bin') == VGA_BIOS
    tool = os.environ.get('FDISBULL_QEMU_IMG')
    assert tool and digest(Path(tool)) == QEMU_IMG
    code = assemble(tmp_path, 'vga-mode-setup', BODY, clock_runtime['nasm'])
    assert code[-14:-10] == b'VGA1'
    offsets = dict(zip(('ready', 'first', 'second', 'noop', 'go'),
                       struct.unpack('<5H', code[-10:]), strict=True))
    source = tmp_path / 'CHANGEM.COM'
    source.write_bytes(code)
    with Project.create(tmp_path / 'mode.fdb', source, image='com') as project:
        with project.debugger(clock_runtime['executable'], tmp_path,
                **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                                 qemu_retrace='precise', qemu_checkpoint_tool=tool)) as debug:
            owner = debug.vm.process
            info = process_record(debug)
            address = {name: com_address(info, offset) for name, offset in offsets.items()}
            park(debug, address['ready'])
            log = Path(debug.vm.temporary.name) / 'qemu.log'
            offset = log.stat().st_size

            def mark():
                nonlocal offset
                current = debug.vga_configuration_observe()['current']
                assert log.stat().st_size <= (128 * 1024)
                contents = log.read_bytes()
                writes = [
                    (int(port, 16), int(value, 16))
                    for port, value in re.findall(rb'vga_std_write_io addr (0x[0-9a-f]+), val (0x[0-9a-f]+)',
                                                  contents[offset:])
                ]
                offset = len(contents)
                return current, writes

            assert debug.vm.qmp.call('human-monitor-command',
                                     {'command-line': 'log trace:vga_std_write_io'}) == ''
            try:
                text, empty = mark()
                assert not empty and text['raw']['graphics'][6] & 1 == 0
                park(debug, address['first'])
                entered, setup = mark()
                raw = entered['raw']
                assert raw['display-enabled'] and raw['misc-output'] == 0x63
                assert raw['sequencer'][:5] == [3, 1, 15, 0, 14]
                assert raw['graphics'][5:7] == [0x40, 5]
                assert raw['crtc'][6:10] == [0xbf, 0x1f, 0, 0x41]
                suffix = _mode_setup_suffix(raw)
                assert setup[-len(suffix):] == suffix
                assert entered['configuration_generation'] > text['configuration_generation']

                budget_receipt(debug.clock_advance(45_000_000, timeout_ms=5000), 45_000_000)
                warm, empty = mark()
                assert not empty and warm['raw'] == raw
                assert warm['configuration_generation'] == entered['configuration_generation']
                assert debug.video_frame_start()['state'] == 'observing'
                assert mark() == (warm, [])
                debug.video_frame_stop()
                assert mark() == (warm, [])

                debug.write_memory(address['go'], '01', expected_hex='00', space='physical')
                park(debug, address['second'])
                reapplied, writes = mark()
                assert reapplied['raw'] == raw
                assert reapplied['configuration_generation'] > warm['configuration_generation']
                assert writes == setup
                park(debug, address['noop'])
                noop, writes = mark()
                assert noop['raw'] == raw
                assert noop['configuration_generation'] == reapplied['configuration_generation']
                assert writes == [(0x3c4, 0), (0x3c5, 3)]
            finally:
                debug.vm.qmp.call('human-monitor-command', {'command-line': 'log none'})
    assert owner.poll() is not None and source.read_bytes() == code
    assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
