"""Real BIOS VBE 101h panning and independently timed DOSBox-X draw rows."""
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
    AFTER_LEADING_RETRACE, DIRECT, RESULT, SUBFUNCTION_SET, SUBFUNCTION_WAIT, event,
)
from support.paired_vbe_pan import COM_SHA, PAN_X, PITCH, SETUP_RESULT, check_pixels, source_with_pan_probe, symbols
from support.paired_vbe_status import FRAME_LINES, LINE_TICKS, RETRACE_END, RETRACE_START
from test_dosbox_vbe_flip_native import _frame_identity, _port_delay
from test_dosbox_vga_visible_rows_native import _lattice
from test_qemu_dosbox_vga_modes_native import _DAC, _RGB, _SOURCE, _dosbox_pages


def _observe(call, origin):
    stream = call('video.probe', points=[], source_visible_rows=True)
    assert stream['source_visible_rows_available'] is True
    timing = stream['source_visible_rows']
    assert timing['latched_crtc_start'] == origin // 4
    rows = timing['rows']
    assert [row['draw_address'] for row in rows] == [origin + PITCH * row for row in range(480)]
    _lattice(dict(timing, latched_crtc_start=0,
                  rows=[dict(row, draw_address=row['draw_address'] - origin - index * (PITCH - 640))
                        for index, row in enumerate(rows)]), 'packed8')
    payload, info = decode_screenshot(call('video.screenshot'))
    assert _frame_identity(info) == _frame_identity(stream)
    with Image.open(BytesIO(payload)) as image:
        pixels = check_pixels(image, origin, _RGB)
    return dict(_frame_identity(stream), origin=origin, pixel_sha256=pixels, source_rows=timing)


def _pan_trials(call, address, offsets, evidence):
    def read(offset, length):
        packet = call('memory.read', address=address(offset), length=length)
        return b64decode(packet['data_base64'], validate=True)

    def write(offset, data):
        previous = read(offset, len(data))
        assert previous[0] == 0
        call('memory.write', address=address(offset), expected_sha256=sha256(previous).hexdigest(),
             data_base64=b64encode(data).decode('ascii'))

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

    def request(name, subfunction, sync, x):
        trial = evidence[name] = dict(subfunction=subfunction, sync=sync, x=x)
        write(offsets['flip_go'], struct.pack('<BBBHH', 1, subfunction, sync, 0, x))
        before = park(offsets['bios_set'])
        assert read(offsets['bios_set'], 2) == b'\xcd\x10'
        assert [int(before[name], 16) & 0xffff for name in ('eax', 'ebx', 'ecx', 'edx')] == [
            0x4f07, subfunction, x, 0,
        ]
        after = park(offsets['post_bios'])
        assert int(after['eax'], 16) & 0xffff == 0x004f
        get = park(offsets['bios_get'])
        assert read(offsets['bios_get'], 2) == b'\xcd\x10'
        assert [int(get[name], 16) & 0xffff for name in ('eax', 'ebx')] == [0x4f07, 1]
        park(offsets['flip_done'])
        result = trial['guest'] = event(read(offsets['flip_result'], RESULT.size))
        assert (result['x'], result['y']) == (x, 0)
        assert read(offsets['flip_go'], 1) == b'\0'
        return trial

    def completed(origin, previous=None):
        frame = call('frame.step')
        assert frame['completed'] is True, frame
        result = _observe(call, origin)
        assert _frame_identity(frame) == _frame_identity(result)
        if previous is not None:
            assert result['mode_id'] == previous['mode_id']
            assert result['frame_id'] == previous['frame_id'] + 1
        return result

    write(offsets['pan_setup_go'], b'\1')
    park(offsets['pan_ready'])
    assert read(offsets['pan_setup_go'], 1) == b'\2'
    setup = SETUP_RESULT.unpack(read(offsets['pan_setup_result'], SETUP_RESULT.size))
    evidence['bios_pitch'] = list(setup)
    assert setup[:3] == (0x004f, PITCH, PITCH) and setup[3] >= 480
    assert call('frame.step')['completed'] is True
    initial = evidence['initial'] = completed(0)
    retrace_width = (RETRACE_END - RETRACE_START) * LINE_TICKS

    before = request('before_leading', SUBFUNCTION_SET, DIRECT, PAN_X)
    assert _port_delay(before['guest'], False, False) < retrace_width
    assert _observe(call, 0) == initial
    before['following'] = completed(PAN_X, initial)

    between = request('between_latches', SUBFUNCTION_SET, AFTER_LEADING_RETRACE, 0)
    assert _port_delay(between['guest'], True, True) < retrace_width
    assert _observe(call, PAN_X) == before['following']
    between['mixed'] = completed(4, before['following'])
    between['following'] = completed(0, between['mixed'])

    wait_high = request('wait_from_high', SUBFUNCTION_WAIT, AFTER_LEADING_RETRACE, PAN_X)
    assert abs(_port_delay(wait_high['guest'], True, True) - FRAME_LINES * LINE_TICKS) < retrace_width
    wait_high['retained_mixed'] = _observe(call, 1)
    assert wait_high['retained_mixed']['frame_id'] == between['following']['frame_id'] + 1
    assert wait_high['retained_mixed']['mode_id'] == initial['mode_id']
    wait_high['following'] = completed(PAN_X, wait_high['retained_mixed'])

    wait_low = request('wait_from_low', SUBFUNCTION_WAIT, DIRECT, 0)
    assert 8 * LINE_TICKS <= _port_delay(wait_low['guest'], False, True) <= 12 * LINE_TICKS
    assert _observe(call, PAN_X) == wait_high['following']
    wait_low['following'] = completed(0, wait_high['following'])


def test_dosbox_vbe_pan_latches_coarse_and_fine_at_separate_edges(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_PAN') != '1':
        pytest.skip('Select the DOSBox-X VBE horizontal-panning reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-pan', source_with_pan_probe(_SOURCE) + '\ncolors: db '
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
            _pan_trials(call, address, offsets, record['trials'])

    try:
        record['base_pixels'] = _dosbox_pages(producer, tmp_path, directory, labels,
                                              observe_rows=arm_rows, operate_page=observe)
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-pan.json').write_text(json.dumps(record, indent=2) + '\n')
