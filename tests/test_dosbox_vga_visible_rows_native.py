"""Direct DOSBox-X row-clock witness for the paired VGA/VBE fixture."""
from fractions import Fraction
import json
import os
from pathlib import Path
import struct

import pytest

from support.dos_process_fixture import assemble, digest
from test_dosbox_vga_chain4_timing_native import _ns
from test_qemu_dosbox_vga_modes_native import _DAC, _SOURCE, _dosbox_pages


_LAYOUTS = {'planar': 'planar4', 'banked': 'packed8'}
_COM_SHA = 'f3cb52889fb82b2f3fdf44af0c85a4d00b4dde3ba71640981945e79d337d9b8e'
# S3 BIOS uses the 25.175 MHz fixed clock for Mode 12h. The VBE mode
# requests 29.400 MHz at 70 Hz, which the S3 PLL (M=113, N=5, R=3)
# quantizes to 29.403 MHz with its 14.318 MHz reference.
_DOT_CLOCK_HZ = {'planar4': 25_175_000, 'packed8': 29_403_000}
_VISIBLE_ROWS = 480
# The two INT 10h mode tables select 525 vertical lines and 100 character
# clocks of 8 pixels horizontally. Check the event clocks without pixels.
_TOTAL_ROWS = 525


def _lattice(timing, layout):
    assert timing['model'] == 'dosbox-vga-visible-row-timing-v1'
    assert timing['layout'] == layout and timing['latched_crtc_start'] == 0
    first = timing['first_callback_scheduled_ns']
    start = timing['frame_scheduled_ns']
    line = timing['line_period_ns']
    period = timing['frame_period_ns']
    retrace = timing['retrace_scheduled_ns']
    exact_line = Fraction(800 * 10**9, _DOT_CLOCK_HZ[layout])
    assert abs(line - exact_line) <= Fraction(1, 2)
    assert abs(first - start - exact_line / 4) <= 1
    assert abs(period - _TOTAL_ROWS * exact_line) <= Fraction(1, 2)
    assert abs(retrace - start - 490 * exact_line) <= 1
    rows = timing['rows']
    assert [row['physical_line'] for row in rows] == list(range(_VISIBLE_ROWS))
    due = [row['scheduled_ns'] for row in rows]
    assert all(abs(right - left - line) <= 2 for left, right in zip(due, due[1:]))
    assert all(abs(scheduled - first - row * exact_line) <= 3
               for row, scheduled in enumerate(due))
    latency = [_ns(row['actual']) - row['scheduled_ns'] for row in rows]
    assert min(latency) >= -Fraction(1, 2) and max(latency) < Fraction(line, 8)
    assert due[-1] < retrace < start + period
    addresses = [row['draw_address'] for row in rows]
    assert addresses[0] == 0
    stride = 320 if layout == 'planar4' else 640
    assert addresses == list(range(0, stride * _VISIBLE_ROWS, stride))
    assert all(row['address_line'] == 0 for row in rows)


def test_dosbox_vga_visible_rows_are_timed_before_pixel_checks(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VGA_VISIBLE_ROWS') != '1':
        pytest.skip('Select the DOSBox-X visible-row timing producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vga-modes', _SOURCE + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), os.environ['NASM'])
    marker = len(code) - 62
    assert code[marker:marker + 4] == b'VGA3'
    labels = struct.unpack('<5H', code[marker + 4:marker + 14])
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'VGA.COM'
    binary.write_bytes(code)
    assert digest(binary) == _COM_SHA
    record = dict(producer_sha256=producer_sha, authored_com_sha256=_COM_SHA, frames={})

    def observe_rows(call, page, step, frame):
        identity = {key: frame[key] for key in ('frame_id', 'mode_id')}
        timing = call('video.probe', points=[], source_visible_rows=True, **identity)
        assert {key: timing[key] for key in identity} == identity
        assert timing['samples'] == []
        raw = timing.get('source_visible_rows')
        record['frames'].setdefault(page, []).append(dict(identity=identity, timing=raw))
        if page in _LAYOUTS and step > 0:
            assert timing['source_visible_rows_available'] is True, (page, step)
            _lattice(raw, _LAYOUTS[page])
        elif page not in _LAYOUTS:
            assert timing['source_visible_rows_available'] is False
            assert raw is None
        if page == 'last' and step == 2:
            disabled = call('video.probe', points=[], source_visible_rows=False, **identity)
            assert disabled['source_visible_rows_available'] is False
            ordinary = call('video.probe', points=[], **identity)
            assert 'source_visible_rows_available' not in ordinary

    try:
        record['pixels'] = _dosbox_pages(producer, tmp_path, directory, labels, observe_rows=observe_rows)
        for page in _LAYOUTS:
            earlier, later = record['frames'][page][-2:]
            assert later['identity']['frame_id'] == earlier['identity']['frame_id'] + 1
            assert later['identity']['mode_id'] == earlier['identity']['mode_id']
            before, after = earlier['timing'], later['timing']
            assert after['line_period_ns'] == before['line_period_ns']
            assert after['frame_period_ns'] == before['frame_period_ns']
            assert abs(after['frame_scheduled_ns'] - before['frame_scheduled_ns'] -
                       before['frame_period_ns']) <= 2
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vga-visible-row-timing.json').write_text(json.dumps(record, indent=2) + '\n')
