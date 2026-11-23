"""A guest VGA mode exit cancels the pending origin and retires its raster stream."""

import json
import os
import struct
from pathlib import Path

import pytest
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_flip import FLIP_Y, source_with_flip_probe, symbols
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _SOURCE
from test_qemu_vbe_flip_native import (
    EDGE,
    LINE,
    PERIOD,
    PROFILE,
    A,
    B,
    display,
    flip_rom_hash,
    frame,
    launch,
    read_memory,
    register,
    request,
    returned,
    source,
)

from fdisbull.project import Project

_MODE_EXIT = r'''
mode_leave:
    mov dx,3cch
    in al,dx
    mov dx,3c2h
    mov ah,al
    and al,0feh
mode_leave_out:
    out dx,al
mode_left:
    cmp byte [mode_command],2
    jne mode_left
    mov al,ah
mode_enter_out:
    out dx,al
mode_entered:
    jmp mode_entered

mode_command: db 0
db 'FEX1'
dw mode_command,mode_leave_out,mode_enter_out
'''


def mode_exit_source():
    original = source_with_flip_probe(_SOURCE)
    hold = 'flip_done:\n    cmp byte [flip_go],1'
    footer = "db 'VP10'\n"
    assert original.count(hold) == original.count(footer) == 1
    return original.replace(
        hold,
        'flip_done:\n    cmp byte [mode_command],1\n    je mode_leave\n    cmp byte [flip_go],1',
    ).replace(footer, _MODE_EXIT + footer)


def mode_symbols(code):
    assert code.count(b'FEX1') == 1
    footer = code.index(b'FEX1') + 4
    return dict(
        zip(
            ('mode_command', 'leave', 'enter'),
            struct.unpack_from('<3H', code, footer),
            strict=True,
        )
    )


def execute_out(debug, site, port, value):
    park(debug, site)
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == site
    assert read_memory(debug, site, 1) == b'\xee'
    assert register(cpu, 'dx') & 0xFFFF == port and register(cpu, 'ax') & 0xFF == value
    stepped = debug.step(count=1, timeout_ms=5000)
    assert stepped['outcome'] == 'step' and not stepped['timed_out'], stepped
    assert int(debug.registers()['linear_pc'], 0) == site + 1
    return {'pc': site, 'port': port, 'value': value}


@pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_FLIP_MODE_EXIT') != '1',
    reason='Select the native VBE mode-exit regression with exact executable and ROM',
)
def test_pending_flip_is_retired_by_guest_vga_mode_exit(tmp_path, clock_runtime, clock_disk):
    executable = clock_runtime['executable']
    tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
    assert digest(executable) == os.environ['FDISBULL_QEMU_VBE_FLIP_SHA256']
    assert digest(tool) == os.environ['FDISBULL_QEMU_VBE_FLIP_IMG_SHA256']
    assert flip_rom_hash(clock_runtime) == os.environ['FDISBULL_QEMU_VBE_FLIP_ROM_SHA256']
    code = assemble(
        tmp_path,
        'vbe-flip-mode-exit',
        mode_exit_source() + '\ncolors: db ' + ','.join(str(value) for color in _DAC for value in color),
        clock_runtime['nasm'],
    )
    page_labels, flip_labels = symbols(code)
    binary = tmp_path / 'EXIT.COM'
    binary.write_bytes(code)
    receipt = {'completed': False, 'profile': PROFILE, 'authored_variant_sha256': digest(binary)}
    owner = None

    try:
        with Project.create(tmp_path / 'mode-exit.fdb', binary, image='com') as project:
            with launch(project, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owner = debug.vm.process
                process = process_record(debug)
                first, planar, held, _, advance = (com_address(process, value) for value in page_labels)
                labels = {name: com_address(process, value) for name, value in flip_labels.items()}
                mutation = {name: com_address(process, value) for name, value in mode_symbols(code).items()}
                park(debug, first)
                debug.write_memory(advance, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(advance, '02', expected_hex='01')
                park(debug, held)
                original_stream = debug.video_frame_start()['native']
                old_raster = receipt['old_raster'] = frame(debug, A)
                start = old_raster['frame-start-ns'] + PERIOD
                deadline = start + EDGE
                entry = request(
                    debug,
                    labels,
                    subfunction=0,
                    y=FLIP_Y,
                    old=A,
                    start=start,
                    phase=120 * LINE + LINE // 2,
                )
                receipt['guest_flip'] = returned(
                    debug, labels, entry=entry, new=B, active=A, pending=deadline
                )
                pending = receipt['pending'] = display(debug, B, A, deadline)
                byte = pending['raw']['misc-output']
                assert byte & 1

                debug.write_memory(mutation['mode_command'], '01', expected_hex='00')
                receipt['leave_out'] = execute_out(debug, mutation['leave'], 0x3C2, byte & ~1)
                unsupported = receipt['unsupported'] = debug.retrace_observe()['native']
                assert unsupported['virtual-ns'] < deadline
                assert (
                    not unsupported['phase-supported'] and unsupported['unsupported-reason'] == 'vbe-enabled'
                )
                assert 'vbe101-timing' not in unsupported and 'vbe101-display-start' not in unsupported
                raw = debug.vga_configuration_observe()['current']['raw']
                assert raw['misc-output'] == byte & ~1 and raw['vbe-start-address'] * 4 == B
                invalidated = receipt['invalidated'] = source(debug)
                assert invalidated['token'] == original_stream['token']
                assert invalidated['state'] == 'invalidated' and invalidated['reason'] == 'timing-changed'
                assert 'frame' not in invalidated

                debug.write_memory(mutation['mode_command'], '02', expected_hex='01')
                receipt['reenter_out'] = execute_out(debug, mutation['enter'], 0x3C2, byte)
                reentered = receipt['reentered'] = display(debug, B, B)
                assert reentered['virtual_ns'] < deadline and reentered['raw']['misc-output'] == byte
                assert source(debug)['state'] == 'invalidated'
                new_stream = debug.video_frame_start()['native']
                assert new_stream['token'] != original_stream['token']
                assert new_stream['stream-generation'] > invalidated['stream-generation']
                receipt['new_raster'] = frame(debug, B)
        assert owner.poll() == 0
        receipt['completed'] = True
    finally:
        if owner is not None:
            receipt['owner'] = {'pid': owner.pid, 'returncode': owner.poll()}
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vbe-mode-exit.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
