"""Same-byte text and planar VGA transitions on both native renderers."""
from base64 import b64encode
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import sys

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC, DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_video_checkpoint import LATCH_PROFILE
from fdisbull.screenshot_codecs import decode_screenshot
from support.dos_process_fixture import assemble, digest
from test_paired_video_frame_native import PROFILE
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record


_DAC = [((0, 14, 49, 63)[(index & 1) + (2 if index & 8 else 0)],
         63 if index & 2 else 0, 63 if index & 4 else 0) for index in range(16)]
_RGB = [bytes((value << 2) | (value >> 4) for value in color) for color in _DAC]
_SOURCE = r'''
bits 16
org 100h
    call text_page
first:
    cmp byte [advance],1
    jne first
    mov ax,12h
    int 10h
    call palette
    mov ax,0a000h
    mov es,ax
    xor bx,bx
.plane:
    mov dx,3c4h
    mov al,2
    out dx,al
    inc dx
    mov cx,bx
    mov al,1
    shl al,cl
    out dx,al
    xor di,di
    mov al,[pattern+bx]
    mov cx,239*80
    rep stosb
    not al
    mov cx,240*80
    rep stosb
    mov al,[last_row+bx]
    mov cx,80
    rep stosb
    inc bx
    cmp bx,4
    jb .plane
planar:
    cmp byte [advance],2
    jne planar
    call text_page
last:
    jmp last

text_page:
    mov ax,3
    int 10h
    mov ax,100h
    mov cx,2000h
    int 10h
    call palette
    mov ax,0b800h
    mov es,ax
    xor di,di
    xor bx,bx
    mov bl,[advance]
    mov cx,2000
.cell:
    mov al,20h
    mov ah,bl
    and ah,7
    shl ah,4
    stosw
    inc bl
    loop .cell
    ret

palette:
    push cs
    pop ds
    cld
    mov dx,3dah
    in al,dx
    mov dx,3c0h
    xor bx,bx
.attribute:
    mov al,bl
    out dx,al
    out dx,al
    inc bl
    cmp bl,16
    jb .attribute
    mov al,14h
    out dx,al
    xor al,al
    out dx,al
    mov al,20h
    out dx,al
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    mov si,colors
    mov cx,48
    rep outsb
    ret

pattern: db 55h,33h,0fh,0ffh
last_row: db 0aah,55h,0,0ffh
advance: db 0
db 'VGA3'
dw first,planar,last,advance
'''


def _check_pixels(image, page):
    rgb = image.convert('RGB')
    width, height = rgb.size
    if page == 'planar':
        assert (width, height) == (640, 480)
        up = b''.join(_RGB[index] for index in range(8, 16)) * 80
        down = b''.join(_RGB[index] for index in range(7, -1, -1)) * 80
        end = (_RGB[9] + _RGB[10]) * 320
        expected = up * 239 + down * 240 + end
    else:
        assert width in (640, 720) and height == 400
        shift = 0 if page == 'first' else 2
        line = b''.join(_RGB[(column + shift) & 7] * (width // 80) for column in range(80))
        expected = line * 400
    actual = rgb.tobytes()
    assert actual == expected, dict(page=page, size=rgb.size, expected=sha256(expected).hexdigest(),
                                    actual=sha256(actual).hexdigest())
    return dict(size=list(rgb.size), sha256=sha256(actual).hexdigest())


def _dosbox_pages(executable, tmp_path, directory, labels):
    wrapper = tmp_path / 'dosbox-vga'
    args = [part for setting in PROFILE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
        "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
        f'os.execv({str(executable)!r}, [{str(executable)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    result = {}
    with closing(DOSBoxRPC(wrapper, directory)) as rpc:
        owner = rpc.process
        sid = rpc.call('session.start', {'target': {'command':'VGA.COM', 'arguments':[]},
            'mounts':[{'drive':'C','host_path':str(directory)}], 'break_at':'entry'})['session_id']

        def call(method, **options):
            return rpc.call(method, {'session_id':sid, **options}, timeout_ms=5000)

        cs = call('state.get_registers')['segments']['cs']

        def address(offset):
            return dict(space='segmented', segment=cs, offset=f'0x{offset:08x}')

        call('execution.timing', fast_forward=False)
        for index, page in enumerate(('first', 'planar', 'last')):
            bp = call('breakpoints.create', kind='execution', once=True,
                      address=address(labels[index]))['breakpoint_id']
            operation = call('execution.continue')['operation_id']
            for _ in range(24):
                stop = call('execution.wait', operation_id=operation, timeout_ms=250)
                if not stop.get('running'):
                    break
            assert stop['stop_reason']['breakpoint_id'] == bp, stop
            for _ in range(2):
                frame = call('frame.step')
                assert frame['completed'] is True, frame
            payload, info = decode_screenshot(call('video.screenshot'))
            assert info['frame_id'] == frame['frame_id'] and info['mode_id'] == frame['mode_id']
            with Image.open(BytesIO(payload)) as image:
                result[page] = _check_pixels(image, page)
            if index < 2:
                call('memory.write', address=address(labels[3]),
                     expected_sha256=sha256(bytes([index])).hexdigest(),
                     data_base64=b64encode(bytes([index + 1])).decode('ascii'))
    assert owner.poll() == 0
    return result


def test_paired_text_and_planar_rendering_survive_mode_changes(
        tmp_path, clock_runtime, clock_disk):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VGA_MODES') != '1':
        pytest.skip('Select the paired native text and planar VGA fixture')
    dosbox = Path(os.environ['FDISBULL_DOSBOX']).resolve(strict=True)
    assert digest(dosbox) == os.environ['FDISBULL_DOSBOX_VGA_MODES_SHA256']
    assert digest(clock_runtime['executable']) == os.environ['FDISBULL_QEMU_VGA_LATCH_SHA256']
    code = assemble(tmp_path, 'vga-modes', _SOURCE + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), clock_runtime['nasm'])
    marker = len(code) - 60
    assert code[marker:marker + 4] == b'VGA3'
    labels = struct.unpack('<4H', code[marker + 4:marker + 12])
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'VGA.COM'
    binary.write_bytes(code)
    results = dict(authored_com_sha256=digest(binary))
    try:
        results['dosbox'] = _dosbox_pages(dosbox, tmp_path, directory, labels)
        results['qemu'] = qemu = {}
        with Project.create(tmp_path / 'modes.fdb', binary, image='com') as project:
            with project.debugger(clock_runtime['executable'], directory,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual', qemu_retrace='precise',
                        qemu_video_source_profile=LATCH_PROFILE, qemu_checkpoint_tool=os.environ['FDISBULL_QEMU_IMG'])) as debug:
                process = debug.vm.process
                info = process_record(debug)
                positions = tuple(com_address(info, label) for label in labels)

                def capture(page):
                    artifact = debug.screenshot(page + '.png')
                    path = tmp_path / (page + '.png')
                    project.debug_export(artifact['artifact'], path)
                    with Image.open(path) as image:
                        return _check_pixels(image, page.removeprefix('restored-'))

                for index, page in enumerate(('first', 'planar', 'last')):
                    park(debug, positions[index])
                    with pytest.raises(DebuggerError) as refused:
                        debug.video_frame_start()
                    assert refused.value.result['verified_refusal']
                    assert debug.vm.process is process and process.poll() is None
                    qemu[page] = capture(page)
                    if page == 'planar':
                        checkpoint = debug.save_state('planar')
                    if index < 2:
                        debug.write_memory(positions[3], f'{index + 1:02x}', expected_hex=f'{index:02x}')
                debug.load_state(checkpoint['artifact'], timeout_ms=60000)
                restored_process = debug.vm.process
                assert restored_process is not process and process.poll() == 0
                assert capture('restored-planar') == qemu['planar']
            assert restored_process.poll() == 0
        assert qemu == results['dosbox']
    finally:
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vga-mode-pair.json').write_text(json.dumps(results, indent=2) + '\n')
