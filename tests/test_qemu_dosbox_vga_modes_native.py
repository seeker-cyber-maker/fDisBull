"""Same-byte text, planar VGA and banked VBE transitions on both renderers."""
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
    call banked_page
banked:
    cmp byte [advance],3
    jne banked
    call text_page
last:
    jmp last

banked_page:
    push ds
    pop es
    mov di,vbe_info
    mov ax,4f01h
    mov cx,101h
    int 10h
    cmp ax,4fh
    jne .fault
    push cs
    pop ds
    cmp word [vbe_info+6],64
    jne .fault
    cmp word [vbe_info+8],0a000h
    jne .fault
    cmp word [vbe_info+16],640
    jne .fault
    cmp word [vbe_info+18],640
    jne .fault
    cmp word [vbe_info+20],480
    jne .fault
    cmp byte [vbe_info+25],8
    jne .fault
    cmp word [vbe_info+4],0
    je .fault
    mov ax,64
    xor dx,dx
    div word [vbe_info+4]
    test dx,dx
    jnz .fault
    mov [bank_step],ax
    mov ax,4f02h
    mov bx,101h
    int 10h
    cmp ax,4fh
    jne .fault
    call palette
    mov word [bank],0
.window:
    mov ax,[bank]
    mul word [bank_step]
    mov dx,ax
    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,4fh
    jne .fault
    push cs
    pop ds
    mov ax,0a000h
    mov es,ax
    xor di,di
    mov al,[bank]
    inc al
    mov ah,al
    mov cx,32768
    cmp word [bank],4
    jne .fill
    mov cx,(640*480-4*65536)/2
.fill:
    rep stosw
    inc word [bank]
    cmp word [bank],5
    jb .window
    ret
.fault:
    mov ax,4c01h
    int 21h

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
bank_step: dw 0
bank: dw 0
vbe_info: times 256 db 0
db 'VGA3'
dw first,planar,banked,last,advance
'''

_PAGES = ('first', 'planar', 'banked', 'last')


def _points(size):
    width, height = size
    return [[0, 0], [255, 102], [256, 102], [0, height // 2], [width - 1, height - 1]]


def _samples(image):
    rgb = image.convert('RGB')
    return [dict(x=x, y=y, rgb=list(rgb.getpixel((x, y)))) for x, y in _points(rgb.size)]


def _check_pixels(image, page):
    rgb = image.convert('RGB')
    width, height = rgb.size
    if page == 'planar':
        assert (width, height) == (640, 480)
        up = b''.join(_RGB[index] for index in range(8, 16)) * 80
        down = b''.join(_RGB[index] for index in range(7, -1, -1)) * 80
        end = (_RGB[9] + _RGB[10]) * 320
        expected = up * 239 + down * 240 + end
    elif page == 'banked':
        assert (width, height) == (640, 480)
        expected = (b''.join(_RGB[index] * 65536 for index in range(1, 5))
                    + _RGB[5] * (640 * 480 - 4 * 65536))
    else:
        assert width in (640, 720) and height == 400
        shift = 0 if page == 'first' else 3
        line = b''.join(_RGB[(column + shift) & 7] * (width // 80) for column in range(80))
        expected = line * 400
    actual = rgb.tobytes()
    assert actual == expected, dict(page=page, size=rgb.size, expected=sha256(expected).hexdigest(),
                                    actual=sha256(actual).hexdigest())
    return dict(size=list(rgb.size), sha256=sha256(actual).hexdigest(), samples=_samples(rgb))


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
        for index, page in enumerate(_PAGES):
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
            identity = {key: frame[key] for key in ('frame_id', 'mode_id')}
            probe = call('video.probe', points=_points(result[page]['size']))
            assert all(probe[key] == value for key, value in identity.items())
            assert probe['samples'] == result[page]['samples']
            if page != 'last':
                call('memory.write', address=address(labels[-1]),
                     expected_sha256=sha256(bytes([index])).hexdigest(),
                     data_base64=b64encode(bytes([index + 1])).decode('ascii'))
    assert owner.poll() == 0
    return result


def test_paired_text_planar_and_vbe_rendering_survive_mode_changes(
        tmp_path, clock_runtime, clock_disk):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VGA_MODES') != '1':
        pytest.skip('Select the paired native VGA and VBE fixture')
    dosbox = Path(os.environ['FDISBULL_DOSBOX']).resolve(strict=True)
    assert digest(dosbox) == os.environ['FDISBULL_DOSBOX_VGA_MODES_SHA256']
    assert digest(clock_runtime['executable']) == os.environ['FDISBULL_QEMU_VGA_LATCH_SHA256']
    code = assemble(tmp_path, 'vga-modes', _SOURCE + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), clock_runtime['nasm'])
    marker = len(code) - 62
    assert code[marker:marker + 4] == b'VGA3'
    labels = struct.unpack('<5H', code[marker + 4:marker + 14])
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

                def capture(page, artifact):
                    path = tmp_path / (page + '.png')
                    project.debug_export(artifact['artifact'], path)
                    with Image.open(path) as image:
                        return _check_pixels(image, page.removeprefix('restored-'))

                previous = None

                def retained(page, expected):
                    nonlocal previous
                    debug.display_start(period_ns=1_000_000)
                    assert debug.clock_advance(2_000_000, timeout_ms=5000)['clock_budget']['deadline_reached']
                    update = debug.display_stop()
                    assert update['completed_renderer_update'] and update['guest_frame_id'] is None
                    identity = {key: update[key] for key in ('window', 'update_id')}
                    if previous is not None:
                        with pytest.raises(ValueError, match='different retained publication'):
                            debug.display_probe([], **previous)
                    stopped = debug.clock_observe()['virtual_ns']
                    probe = debug.display_probe(_points(expected['size']), **identity)
                    assert all(probe[key] == value for key, value in identity.items())
                    assert probe['pixels'] == expected['samples'] and probe['guest_frame_id'] is None
                    export_name = page + '-retained.png'
                    export = debug.capture_display(export_name)
                    path = tmp_path / export_name
                    project.debug_export(export['artifact'], path)
                    with Image.open(path) as image:
                        assert _check_pixels(image, page.removeprefix('restored-')) == expected
                    assert debug.clock_observe()['virtual_ns'] == stopped
                    previous = identity

                checkpoints = {}
                for index, page in enumerate(_PAGES):
                    park(debug, positions[index])
                    with pytest.raises(DebuggerError) as refused:
                        debug.video_frame_start()
                    assert refused.value.result['verified_refusal']
                    assert debug.vm.process is process and process.poll() is None
                    qemu[page] = capture(page, debug.screenshot(page + '.png'))
                    retained(page, qemu[page])
                    if page in ('planar', 'banked'):
                        checkpoints[page] = debug.save_state(page)['artifact']
                    if page != 'last':
                        debug.write_memory(positions[-1], f'{index + 1:02x}', expected_hex=f'{index:02x}')
                for page, artifact in checkpoints.items():
                    debug.load_state(artifact, timeout_ms=60000)
                    assert debug.vm.process is not process and process.poll() == 0
                    process = debug.vm.process
                    restored = 'restored-' + page
                    assert capture(restored, debug.screenshot(restored + '.png')) == qemu[page]
                    retained(restored, qemu[page])
            assert process.poll() == 0
        assert qemu == results['dosbox']
    finally:
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path / 'vga-mode-pair.json').write_text(json.dumps(results, indent=2) + '\n')
