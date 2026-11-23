"""Real VBE 4F07h calls and independently observed DOSBox-X scanout latches."""
from base64 import b64decode, b64encode
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import struct

from PIL import Image
import pytest

from fdisbull.screenshot_codecs import decode_screenshot
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_flip import (
    AFTER_LEADING_RETRACE, COM_SHA, DIRECT, FLIP_ORIGIN, FLIP_Y, RESULT,
    SUBFUNCTION_SET, SUBFUNCTION_WAIT, check_pixels, event, source_with_flip_probe, symbols,
)
from support.paired_vbe_status import FRAME_LINES, LINE_TICKS, RETRACE_END, RETRACE_START
from test_dosbox_vga_visible_rows_native import _lattice
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE, _dosbox_pages


def _frame_identity(packet):
    return {name: packet[name] for name in ('frame_id', 'mode_id')}


def _origin_frame(call, origin):
    stream = call('video.probe', points=[], source_visible_rows=True)
    assert stream['source_visible_rows_available'] is True
    timing = stream['source_visible_rows']
    assert timing['latched_crtc_start'] * 4 == origin
    assert timing['rows'][0]['draw_address'] == origin
    _lattice(dict(timing, latched_crtc_start=0,
                  rows=[dict(row, draw_address=row['draw_address'] - origin)
                        for row in timing['rows']]), 'packed8')
    payload, info = decode_screenshot(call('video.screenshot'))
    assert _frame_identity(info) == _frame_identity(stream)
    with Image.open(BytesIO(payload)) as image:
        pixels = check_pixels(image, origin, _RGB)
    return dict(_frame_identity(stream), origin=origin, pixel_sha256=pixels, source_rows=timing)


def _request(call, address, offsets, subfunction, sync, y):
    def read(offset, length):
        packet = call('memory.read', address=address(offset), length=length)
        return b64decode(packet['data_base64'], validate=True)

    def park(offset):
        point = call('breakpoints.create', kind='execution', once=True, address=address(offset))
        operation = call('execution.continue')['operation_id']
        for _ in range(24):
            state = call('execution.wait', operation_id=operation, timeout_ms=250)
            if not state.get('running'):
                break
        assert not state.get('running') and state['stop_reason']['kind'] == 'breakpoint', state
        assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id'], state
        registers = call('state.get_registers')
        assert int(registers['instruction_pointer'], 16) == offset
        return registers['general']

    control = struct.pack('<BBBH', 1, subfunction, sync, y)
    previous = read(offsets['flip_go'], len(control))
    assert previous[0] == 0
    call('memory.write', address=address(offsets['flip_go']),
         expected_sha256=sha256(previous).hexdigest(),
         data_base64=b64encode(control).decode('ascii'))
    before = park(offsets['bios_set'])
    assert read(offsets['bios_set'], 2) == b'\xcd\x10'
    assert [int(before[name], 16) & 0xffff for name in ('eax', 'ebx', 'ecx', 'edx')] == [
        0x4f07, subfunction, 0, y]
    after = park(offsets['post_bios'])
    assert int(after['eax'], 16) & 0xffff == 0x004f
    get = park(offsets['bios_get'])
    assert read(offsets['bios_get'], 2) == b'\xcd\x10'
    assert [int(get[name], 16) & 0xffff for name in ('eax', 'ebx')] == [0x4f07, 1]
    park(offsets['flip_done'])
    fields = event(read(offsets['flip_result'], RESULT.size))
    assert (fields['x'], fields['y']) == (0, y)
    assert read(offsets['flip_go'], 1) == b'\0'
    return fields


def _completed(call, origin, previous):
    stepped = call('frame.step')
    assert stepped['completed'] is True, stepped
    result = _origin_frame(call, origin)
    assert _frame_identity(stepped) == _frame_identity(result)
    assert result['mode_id'] == previous['mode_id']
    assert result['frame_id'] == previous['frame_id'] + 1
    return result


def _port_delay(packet, high_before, high_after):
    assert bool(packet['status_before'] & 8) is high_before
    assert bool(packet['status_after'] & 8) is high_after
    return packet['elapsed_pit_ticks']


def _flips(call, address, offsets, evidence):
    def request(name, subfunction, sync, y):
        trial = evidence[name] = {'subfunction': subfunction, 'sync': sync, 'y': y}
        trial['guest'] = _request(call, address, offsets, subfunction, sync, y)
        return trial

    initial = evidence['initial'] = _origin_frame(call, 0)
    retrace_width = (RETRACE_END - RETRACE_START) * LINE_TICKS

    before = request('before_leading', SUBFUNCTION_SET, DIRECT, FLIP_Y)
    assert _port_delay(before['guest'], False, False) < retrace_width
    before['retained'] = _origin_frame(call, 0)
    assert before['retained'] == initial
    before['following'] = _completed(call, FLIP_ORIGIN, initial)

    after = request('after_leading', SUBFUNCTION_SET, AFTER_LEADING_RETRACE, 0)
    assert _port_delay(after['guest'], True, True) < retrace_width
    after['retained'] = _origin_frame(call, FLIP_ORIGIN)
    assert after['retained'] == before['following']
    after['following'] = _completed(call, FLIP_ORIGIN, after['retained'])
    after['next'] = _completed(call, 0, after['following'])

    wait = request('wait_from_high', SUBFUNCTION_WAIT, AFTER_LEADING_RETRACE, FLIP_Y)
    period_error = abs(_port_delay(wait['guest'], True, True) - FRAME_LINES * LINE_TICKS)
    assert period_error < retrace_width
    wait['retained'] = _origin_frame(call, 0)
    assert wait['retained']['frame_id'] == after['next']['frame_id'] + 1
    assert wait['retained']['mode_id'] == initial['mode_id']
    wait['following'] = _completed(call, FLIP_ORIGIN, wait['retained'])

    wait_low = request('wait_from_low', SUBFUNCTION_WAIT, DIRECT, 0)
    assert 8 * LINE_TICKS <= _port_delay(wait_low['guest'], False, True) <= 12 * LINE_TICKS
    wait_low['retained'] = _origin_frame(call, FLIP_ORIGIN)
    assert wait_low['retained'] == wait['following']
    wait_low['following'] = _completed(call, 0, wait_low['retained'])


def test_dosbox_vbe_page_flip_latches_at_retrace(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_FLIP') != '1':
        pytest.skip('Select the DOSBox-X VBE page flip reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-flip', source_with_flip_probe(_SOURCE) + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), os.environ['NASM'])
    labels, offsets = symbols(code)
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'VGA.COM'
    binary.write_bytes(code)
    assert digest(binary) == COM_SHA
    record = dict(producer_sha256=producer_sha, authored_com_sha256=COM_SHA, trials={})

    def arm_rows(call, page, step, frame):
        call('video.probe', points=[], source_visible_rows=True, **_frame_identity(frame))

    def observe(call, page, address):
        if page == 'banked':
            _flips(call, address, offsets, record['trials'])

    try:
        record['pixels'] = _dosbox_pages(producer, tmp_path, directory, labels,
                                         observe_rows=arm_rows, operate_page=observe)
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-flip.json').write_text(json.dumps(record, indent=2) + '\n')
