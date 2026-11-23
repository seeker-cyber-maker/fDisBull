"""Opt-in stopped-source witness with independently authored VGA planes."""
from base64 import b64decode
from hashlib import sha256
import os
import struct

import pytest

from fdisbull import qemu_machine
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_raster_proof_native import passive, unavailable

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_UNCHAINED_PROBE') != '1',
    reason='Select an exact native QEMU with the stopped unchained VGA probe',
)

COMMAND = 'x-fdisbull-probe-unchained-vga-rows'
RENDER_PROOF = 'x-fdisbull-render-raster-proof'
BODY = r'''
bits 16
org 100h
    nop
    mov ax,13h
    int 10h
chain4:
    nop
    push cs
    pop ds
    cld
    mov ax,0a000h
    mov es,ax
    mov ax,0604h
    call sequencer
    mov ax,0014h
    call crtc
    mov ax,0e317h
    call crtc
    mov ax,2813h
    call crtc

    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    xor bx,bx
    mov cx,17
.palette:
    mov al,bl
    out dx,al
    add al,bl
    out dx,al
    add al,bl
    out dx,al
    inc bl
    loop .palette

    xor bx,bx
.fill_plane:
    mov cx,bx
    mov ah,1
    shl ah,cl
    mov al,2
    call sequencer
    mov di,4000h
    mov al,bl
    inc al
    mov cx,16000
    rep stosb
    add al,8
    mov di,4000h+199*80
    mov cx,80
    rep stosb

    mov di,8000h
    mov al,bl
    add al,5
    mov cx,16000
    rep stosb
    add al,8
    mov di,8000h+199*80
    mov cx,80
    rep stosb
    inc bx
    cmp bx,4
    jb .fill_plane

    mov ax,0802h
    call sequencer
    mov ax,400ch
    call crtc
    mov ax,000dh
    call crtc
page_a:
    nop
    mov ax,800ch
    call crtc
page_b:
    nop
    mov ax,0c20ch
    call crtc
wrapping:
    nop
    mov ax,800ch
    call crtc
restored_page:
    nop
    jmp restored_page

sequencer:
    mov dx,3c4h
    jmp write_index_data
crtc:
    mov dx,3d4h
write_index_data:
    out dx,al
    inc dx
    mov al,ah
    out dx,al
    ret

    db 'UVGA'
    dw chain4,page_a,page_b,wrapping,restored_page
'''


def _indices_rgb(first):
    # Mode X plane p contributes logical pixels p, p+4, p+8, ...
    result = bytearray()
    for color in range(first, first + 4):
        for dac in (color, 2 * color, 3 * color):
            result.append((dac << 2) | (dac >> 4))
    return bytes(result) * 80


def _render_page(project, debug, first, origin):
    regs, clock = debug.registers(), debug.clock_observe()['virtual_ns']
    proof = debug.vm.qmp.call(RENDER_PROOF)
    assert proof['outcome'] == 'updated' and proof['current-configuration-matches'], proof
    assert passive(project, debug) == proof
    assert (debug.registers(), debug.clock_observe()['virtual_ns']) == (regs, clock)
    assert proof['attempt-ns'] == proof['virtual-ns']
    source = proof['source']
    assert source['profile'] == 'qemu-vga-unchained-320x200-raster-v1'
    assert source['start-address'] == origin and source['line-offset'] == 320
    assert source['rows-considered'] == source['rows-redrawn'] == 400
    expected = (bytes(range(first, first + 4)) * (199 * 80)
                + bytes(range(first + 8, first + 12)) * 80)
    assert source['source-index-sha256'] == sha256(expected).hexdigest()
    # Stock QEMU VGA duplicates the low bit of 6-bit color in its renderer.
    def surface_row(first_color):
        unit = b''
        for color in range(first_color, first_color + 4):
            rgb = bytes((dac << 2) | (3 if dac & 1 else 0)
                        for dac in (color, 2 * color, 3 * color))
            unit += rgb * 2
        return unit * 80
    surface = surface_row(first) * (2 * 199) + surface_row(first + 8) * 2
    assert source['surface-rgb-sha256'] == sha256(surface).hexdigest()


@pytest.mark.parametrize('renderer', [
    False,
    pytest.param(True, marks=pytest.mark.skipif(
        os.environ.get('FDISBULL_REQUIRE_QEMU_UNCHAINED_RENDER_PROOF') != '1',
        reason='Select a QEMU with unchained renderer-source proof')),
])
def test_native_unchained_probe_selects_programmed_page_and_interleaved_planes(
        tmp_path, clock_runtime, clock_disk, monkeypatch, renderer):
    if renderer:
        original = qemu_machine.machine_retrace_arguments
        monkeypatch.setattr(qemu_machine, 'machine_retrace_arguments',
            lambda profile: original(profile) + ['-global', 'VGA.x-fdisbull-raster-proof=on'])
    code = assemble(tmp_path, 'unchained-pages', BODY, clock_runtime['nasm'])
    assert code[-14:-10] == b'UVGA'
    symbols = dict(zip(('chain4', 'page_a', 'page_b', 'wrapping', 'restored_page'),
                       struct.unpack('<5H', code[-10:]), strict=True))
    source = tmp_path / 'PLANES.COM'
    source.write_bytes(code)
    with Project.create(tmp_path / 'planes.fdb', source, image='com') as project:
        with project.debugger(clock_runtime['executable'], tmp_path,
                **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                                 qemu_retrace='precise')) as debug:
            owner = debug.vm.process
            info = process_record(debug)
            address = {name: com_address(info, offset) for name, offset in symbols.items()}
            assert COMMAND in debug.vm.qmp_commands
            park(debug, address['chain4'])
            with pytest.raises(DebuggerError, match='unsupported-unchained-pixel-interpretation'):
                debug.vm.qmp.call(COMMAND, {'rows': [0]})

            def probe(first, origin):
                before = debug.registers(), debug.clock_observe()['virtual_ns']
                raw = debug.vga_configuration_observe()['current']
                assert raw['raw']['sequencer'][2] == 0x08
                assert raw['raw']['crtc'][12] * 1024 == origin
                selected = [199, 0, 100]
                result = debug.vm.qmp.call(COMMAND, {'rows': selected})
                assert result['model'] == 'qemu-vga-unchained-320x200-probe-v1'
                assert result['origin-bytes'] == origin and result['pitch-bytes'] == 320
                assert result['dac-8bit'] is False and result['virtual-ns'] == before[1]
                assert result['configuration-generation'] == raw['configuration_generation']
                assert [row['row'] for row in result['rows']] == selected
                expected = [_indices_rgb(first + 8), _indices_rgb(first), _indices_rgb(first)]
                assert [b64decode(row['rgb-base64'], validate=True) for row in result['rows']] == expected
                assert debug.vm.qmp.call(COMMAND, {'rows': selected}) == result
                assert (debug.registers(), debug.clock_observe()['virtual_ns']) == before
                return result

            park(debug, address['page_a'])
            page_a = probe(1, 0x10000)
            if renderer:
                _render_page(project, debug, 1, 0x10000)
            with pytest.raises(DebuggerError, match='unsupported-pixel-interpretation'):
                debug.video_frame_start()
            assert debug.vm.process is owner and owner.poll() is None
            for rows in ([], [0, 0], [200], list(range(17))):
                with pytest.raises(DebuggerError, match='one to 16 unique'):
                    debug.vm.qmp.call(COMMAND, {'rows': rows})
            park(debug, address['page_b'])
            page_b = probe(5, 0x20000)
            assert page_b['configuration-generation'] > page_a['configuration-generation']
            if renderer:
                assert passive(project, debug)['current-configuration-matches'] is False
                _render_page(project, debug, 5, 0x20000)
            park(debug, address['wrapping'])
            with pytest.raises(DebuggerError, match='incomplete-or-wrapping-source-storage'):
                debug.vm.qmp.call(COMMAND, {'rows': [199]})
            if renderer:
                proof = debug.vm.qmp.call(RENDER_PROOF)
                unavailable(proof, attempted=True)
                assert proof['reason'] == 'incomplete-or-wrapping-source-storage'
            park(debug, address['restored_page'])
            restored = probe(5, 0x20000)
            assert restored['rows'] == page_b['rows']
            assert restored['configuration-generation'] > page_b['configuration-generation']
            if renderer:
                _render_page(project, debug, 5, 0x20000)
    assert owner.poll() is not None and source.read_bytes() == code
    assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
