"""Banked Mode 101h stride, 6/8-bit DAC, and retrace reference on DOSBox-X."""

from base64 import b64decode, b64encode
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.screenshot_codecs import decode_screenshot
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_palette import (
    ACTIVE_RASTER, COM_SHA, DAC6, DAC8, DIRECT, FIRST_COLOR, HEIGHT, PITCH,
    REQUEST, RESULT, RETRACE_HIGH, TIMED, WIDTH, event, expected_rgb,
    source_with_palette_probe, symbols, updated_palette,
)
from support.paired_vbe_status import FRAME_LINES, LINE_TICKS, RETRACE_END, RETRACE_START
from test_paired_video_frame_native import PROFILE
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE


VRAM = 16 * 1024**2
MAX_PITCH = 0x3FF * 8
PROFILE_VBE = tuple(setting for setting in PROFILE if setting != 'video enable 8-bit dac=false') + (
    'video enable 8-bit dac=true', 'video vmemsize=16',
)


def _observe(rpc, directory, labels, offsets, record):
    sid = rpc.call('session.start', {
        'target': {'command': 'VGA.COM', 'arguments': []},
        'mounts': [{'drive': 'C', 'host_path': str(directory)}],
        'break_at': 'entry',
    })['session_id']

    def call(method, **options):
        return rpc.call(method, {'session_id': sid, **options}, timeout_ms=5000)

    cs = call('state.get_registers')['segments']['cs']

    def address(offset):
        return {'space': 'segmented', 'segment': cs, 'offset': f'0x{offset:08x}'}

    def read(offset, length):
        packet = call('memory.read', address=address(offset), length=length)
        return b64decode(packet['data_base64'], validate=True)

    def write(offset, data):
        call('memory.write', address=address(offset), expected_sha256=sha256(read(offset, len(data))).hexdigest(),
             data_base64=b64encode(data).decode('ascii'))

    def park(offset):
        bp = call('breakpoints.create', kind='execution', once=True, address=address(offset))['breakpoint_id']
        operation = call('execution.continue')['operation_id']
        for _ in range(24):
            stop = call('execution.wait', operation_id=operation, timeout_ms=250)
            if not stop.get('running'):
                break
        assert not stop.get('running') and stop['stop_reason']['breakpoint_id'] == bp, stop
        regs = call('state.get_registers')
        assert int(regs['instruction_pointer'], 16) == offset
        return tuple(int(regs['general'][name], 16) & 0xFFFF for name in ('eax', 'ebx', 'ecx', 'edx'))

    def request(name, ax, bx, cx=0, dx=0, *, gate=DIRECT, payload=b''):
        control = offsets['palette_go']
        assert read(control, 1) == b'\0'
        if payload:
            write(offsets['palette_buffer'], payload)
        write(control, REQUEST.pack(1, gate, ax, bx, cx, dx))
        assert park(offsets['palette_bios']) == (ax, bx, cx, dx)
        returned = park(offsets['palette_return'])
        park(offsets['palette_done'])
        result = record['trials'][name] = event(read(offsets['palette_result'], RESULT.size))
        assert tuple(result[reg] for reg in ('ax', 'bx', 'cx', 'dx')) == returned
        assert read(control, 1) == b'\0'
        if payload:
            result['buffer'] = read(offsets['palette_buffer'], len(payload)).hex()
        return returned, result

    def screenshot(palette):
        payload, info = decode_screenshot(call('video.screenshot'))
        with Image.open(BytesIO(payload)) as image:
            assert image.size == (WIDTH, HEIGHT)
            rgb = image.convert('RGB').tobytes()
        assert rgb == expected_rgb(PITCH, palette)
        return {key: info[key] for key in ('frame_id', 'mode_id')} | {'pixel_sha256': sha256(rgb).hexdigest()}

    def frame(name, palette, *, settle=False):
        if settle:
            # An immediate BIOS call may return during a frame started with
            # the old palette. Record the first full frame with the new state.
            step = call('frame.step')
            assert step['completed'] is True, step
        step = call('frame.step')
        assert step['completed'] is True, step
        result = record['frames'][name] = screenshot(palette)
        assert {key: step[key] for key in ('frame_id', 'mode_id')} == {
            key: result[key] for key in ('frame_id', 'mode_id')
        }
        return result

    call('execution.timing', fast_forward=False)
    park(labels[0])
    write(labels[-1], b'\1')
    park(labels[1])
    write(labels[-1], b'\2')
    park(labels[2])

    def stride(name, subcall, value, expected):
        got, _ = request(name, 0x4F06, subcall, value)
        assert got == (0x004F, expected, expected, min(0xFFFF, VRAM // expected))

    stride('current_stride', 1, 0, WIDTH)
    stride('pixel_stride', 0, 641, PITCH)
    stride('byte_stride', 2, 647, PITCH)
    stride('max_stride', 3, 0, MAX_PITCH)
    stride('after_max_stride', 1, 0, PITCH)
    stride('small_positive_stride', 2, 1, 8)
    stride('huge_stride', 2, 65535, MAX_PITCH)
    assert request('zero_stride', 0x4F06, 2)[0][0] == 0x024F
    stride('after_zero_stride', 1, 0, MAX_PITCH)
    stride('reset_stride', 2, PITCH, PITCH)

    assert request('width_6', 0x4F08, 1)[0][:2] == (0x004F, 0x0601)
    assert request('set_dac6', 0x4F09, 0, 2, FIRST_COLOR, payload=DAC6)[0][0] == 0x004F
    sentinel = bytes([0xF1, 0xE2, 0xD3, 0xC4, 0xB5, 0xA6, 0x97, 0x88])

    def palette_read(name, colors):
        got, observed = request(name, 0x4F09, 1, 2, FIRST_COLOR, payload=sentinel)
        assert got[0] == 0x004F
        assert bytes.fromhex(observed['buffer']) == colors[:3] + sentinel[3:4] + colors[4:7] + sentinel[7:]

    palette_read('get_dac6', DAC6)
    palette6 = updated_palette(_RGB, FIRST_COLOR, DAC6, 6)
    frame('dac6', palette6, settle=True)

    assert request('set_width_8', 0x4F08, 0x0800)[0][:2] == (0x004F, 0x0800)
    assert request('width_8', 0x4F08, 1)[0][:2] == (0x004F, 0x0801)
    assert request('set_dac8', 0x4F09, 0, 5, FIRST_COLOR, payload=DAC8)[0][0] == 0x004F
    palette_read('get_dac8', DAC8)
    palette8 = updated_palette(_RGB, FIRST_COLOR, DAC8, 8)
    frame('dac8', palette8, settle=True)

    (bad, invalid) = request('invalid_range', 0x4F09, 0x80, 2, 255, gate=ACTIVE_RASTER, payload=TIMED)
    assert bad[0] == 0x014F, invalid
    assert invalid['status_before'] & 8 == invalid['status_after'] & 8 == 0
    assert invalid['elapsed_pit_ticks'] < 5 * LINE_TICKS
    palette_read('after_invalid_range', DAC8)

    def timed(name, gate, payload, old_palette, next_palette, before_high):
        got, elapsed = request(name, 0x4F09, 0x80, 2, FIRST_COLOR, gate=gate, payload=payload)
        assert got[0] == 0x004F
        assert bool(elapsed['status_before'] & 8) is before_high and elapsed['status_after'] & 8
        fraction = (RETRACE_END - RETRACE_START) * LINE_TICKS
        if before_high:
            assert abs(elapsed['elapsed_pit_ticks'] - FRAME_LINES * LINE_TICKS) < fraction
        else:
            expect = FRAME_LINES * LINE_TICKS - fraction - 1000
            assert abs(elapsed['elapsed_pit_ticks'] - expect) < fraction
        record['frames'][f'{name}_retained'] = screenshot(old_palette)
        frame(name, next_palette)

    timed_palette = updated_palette(palette8, FIRST_COLOR, TIMED, 8)
    timed('timed_low', ACTIVE_RASTER, TIMED, palette8, timed_palette, False)
    palette_read('get_timed_dac8', TIMED)
    timed('timed_high', RETRACE_HIGH, DAC8[:8], timed_palette, palette8, True)
    palette_read('get_after_high', DAC8)

    assert request('reset_width_6', 0x4F08, 0x0600)[0][:2] == (0x004F, 0x0600)
    assert request('restored_width_6', 0x4F08, 1)[0][:2] == (0x004F, 0x0601)


def test_dosbox_vbe_stride_and_retrace_palette(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_PALETTE') != '1':
        pytest.skip('Select the DOSBox-X VBE stride and palette reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-palette', source_with_palette_probe(_SOURCE) + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), os.environ['NASM'])
    labels, offsets = symbols(code)
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'VGA.COM'
    binary.write_bytes(code)
    assert digest(binary) == COM_SHA
    wrapper = tmp_path / 'dosbox-vbe-palette'
    args = [part for setting in PROFILE_VBE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
                       "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
                       f'os.execv({str(producer)!r}, [{str(producer)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    result = dict(producer_sha256=producer_sha, authored_com_sha256=COM_SHA,
                  trials={}, frames={}, profile=PROFILE_VBE)
    try:
        with closing(DOSBoxRPC(wrapper, directory)) as rpc:
            owner = rpc.process
            _observe(rpc, directory, labels, offsets, result)
        assert owner.poll() == 0
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-palette.json').write_text(json.dumps(result, indent=2) + '\n')
