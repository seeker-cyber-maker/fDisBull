"""Compile the exact pinned source-row helper, without a QEMU build or guest.

These are arithmetic/owned-byte probes. They do not qualify timer callbacks,
QMP, native source admission, persistence, or DOSBox sampling equivalence.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


PACKAGE = Path(__file__).resolve().parents[1] / 'native/qemu-video-frame'
HEADER = 'include/hw/display/fdisbull-video-frame.h'
LIMIT = (1 << 63) - 1
LINE = 31_700
PERIOD = 14_233_300  # Declared 449-line vector; independent of helper output.
BYTE = ctypes.c_uint8
PTR = ctypes.POINTER(BYTE)
I64 = ctypes.c_int64


def extracted_header():
    manifest = json.loads((PACKAGE / 'source-manifest.json').read_text())
    patch = (PACKAGE / manifest['patch']).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == manifest['patch_sha256']
    marker = f'diff --git a/{HEADER} b/{HEADER}\n'
    lines = patch.decode().split(marker, 1)[1].split('diff --git ', 1)[0].splitlines()
    data = ('\n'.join(line[1:] for line in lines
                      if line.startswith('+') and not line.startswith('+++')) + '\n').encode()
    record = next(item for item in manifest['files'] if item['path'] == HEADER)
    assert record['base_sha256'] is None
    assert hashlib.sha256(data).hexdigest() == record['patched_sha256']
    return data


@pytest.fixture(scope='module')
def helper(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C compiler is required for exact source helper probes')
    directory = tmp_path_factory.mktemp('video-frame-source')
    (directory / 'video.h').write_bytes(extracted_header())
    source = directory / 'probe.c'
    source.write_text('''
#include "video.h"
int timing(int64_t h, int64_t p) { return fdisbull_video_timing_valid(h, p); }
int next(int64_t n, int64_t p, int64_t *b) { return fdisbull_video_next_start(n, p, b); }
int deadline(int64_t b, int64_t h, unsigned r, int64_t *d) {
    return fdisbull_video_row_deadline(b, h, r, d);
}
int timely(int64_t d, int64_t a, int64_t h) {
    return fdisbull_video_row_timely(d, a, h);
}
unsigned dac(unsigned v, int eight) { return fdisbull_video_dac(v, eight); }
int row(const uint8_t *i, size_t ni, const uint8_t *p, size_t np,
        int eight, uint8_t *o, size_t no) {
    return fdisbull_video_copy_row(i, ni, p, np, eight, o, no);
}
''')
    library = directory / 'probe.so'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fPIC', '-shared', str(source), '-o', str(library)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    lib = ctypes.CDLL(str(library))
    signatures = {
        'timing': [I64, I64],
        'next': [I64, I64, ctypes.POINTER(I64)],
        'deadline': [I64, I64, ctypes.c_uint, ctypes.POINTER(I64)],
        'timely': [I64, I64, I64],
        'dac': [ctypes.c_uint, ctypes.c_int],
        'row': [PTR, ctypes.c_size_t, PTR, ctypes.c_size_t,
                ctypes.c_int, PTR, ctypes.c_size_t],
    }
    for name, args in signatures.items():
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = ctypes.c_int
    return lib


@pytest.mark.parametrize('line,period,expected', [
    (LINE, PERIOD, True), (4, 1600, True), (4, 1596, False),
    (LINE, PERIOD + 1, False), (3, 1800, False), (0, 0, False),
    (-4, 1800, False), (LIMIT, LIMIT, False),
])
def test_timing_admits_only_bounded_complete_line_vectors(helper, line, period, expected):
    assert bool(helper.timing(line, period)) is expected


@pytest.mark.parametrize('now,expected', [
    (0, 14_233_300), (14_233_299, 14_233_300),
    (14_233_300, 28_466_600), (14_233_301, 28_466_600),
])
def test_first_boundary_is_strictly_future(helper, now, expected):
    output = I64(-123)
    assert helper.next(now, PERIOD, ctypes.byref(output))
    assert output.value == expected and output.value > now


@pytest.mark.parametrize('now,period', [(-1, PERIOD), (0, 0), (0, -1),
                                        (LIMIT, 1), (LIMIT - 1, 2)])
def test_next_boundary_overflow_or_invalid_does_not_publish(helper, now, period):
    output = I64(-123)
    assert not helper.next(now, period, ctypes.byref(output))
    assert output.value == -123
    assert not helper.next(0, PERIOD, None)


@pytest.mark.parametrize('row,expected', [(0, 28_474_525), (1, 28_537_925),
                                        (100, 34_814_525), (199, 41_091_125)])
def test_known_scanline_phase_and_last_row_deadline(helper, row, expected):
    output = I64(-123)
    assert helper.deadline(28_466_600, LINE, row, ctypes.byref(output))
    assert output.value == expected


@pytest.mark.parametrize('start,line,row', [(-1, LINE, 0), (0, 3, 0),
                                          (0, LINE, 200), (LIMIT, LINE, 0),
                                          (0, LIMIT, 199), (0, LINE, (1 << 32) - 1)])
def test_invalid_or_overflowing_row_deadline_never_advances(helper, start, line, row):
    output = I64(-123)
    assert not helper.deadline(start, line, row, ctypes.byref(output))
    assert output.value == -123
    assert not helper.deadline(0, LINE, 0, None)


def test_late_row_boundary_is_exact_and_no_catchup_is_admitted(helper):
    assert helper.timely(100_000, 100_000, LINE)
    assert helper.timely(100_000, 131_699, LINE)
    assert not helper.timely(100_000, 131_700, LINE)
    assert not helper.timely(100_000, 99_999, LINE)
    assert not helper.timely(-1, 0, LINE)
    assert not helper.timely(100_000, 100_000, 0)


def test_dac_adapter_has_independent_nonendpoint_oracle(helper):
    values = (0, 1, 2, 3, 21, 42, 63, 64, 255)
    expected = (0, 4, 8, 12, 85, 170, 255, 0, 255)
    assert tuple(helper.dac(value, 0) for value in values) == expected
    assert tuple(helper.dac(value, 1) for value in values) == values
    assert tuple(helper.dac(value, 0) for value in (1, 21, 42)) != (7, 87, 168)


def _buffer(data):
    return (BYTE * len(data)).from_buffer_copy(data)


def test_full_row_owns_first_middle_last_pixels_and_palette_time(helper):
    indices = bytearray(320)
    indices[0], indices[160], indices[-1] = 1, 2, 255
    palette = bytearray(768)
    palette[3:6] = bytes((1, 21, 42))
    palette[6:9] = bytes((63, 0, 63))
    palette[-3:] = bytes((63, 1, 42))
    row = (BYTE * 960)()
    assert helper.row(_buffer(indices), 320, _buffer(palette), 768, 0, row, 960)
    expected = bytearray(960)
    expected[0:3] = bytes((4, 85, 170))
    expected[480:483] = bytes((255, 0, 255))
    expected[-3:] = bytes((255, 4, 170))
    assert bytes(row) == expected
    palette[3:6] = bytes((42, 21, 1))
    later = (BYTE * 960)()
    assert helper.row(_buffer(indices), 320, _buffer(palette), 768, 0, later, 960)
    assert bytes(row) == expected  # Later palette cannot recolor an owned row.
    expected[0:3] = bytes((170, 85, 4))
    assert bytes(later) == expected
    eight = (BYTE * 960)()
    assert helper.row(_buffer(indices), 320, _buffer(palette), 768, 1, eight, 960)
    assert bytes(eight)[:3] == bytes((42, 21, 1))
    assert bytes(eight)[-3:] == bytes((63, 1, 42))


@pytest.mark.parametrize('ni,np,no,null', [(319, 768, 960, None), (321, 768, 960, None),
                                         (320, 767, 960, None), (320, 769, 960, None),
                                         (320, 768, 959, None), (320, 768, 961, None),
                                         (320, 768, 960, 'indices'),
                                         (320, 768, 960, 'palette'),
                                         (320, 768, 960, 'output')])
def test_invalid_buffers_refuse_before_any_output_write(helper, ni, np, no, null):
    indices = _buffer(bytes(320))
    palette = _buffer(bytes(768))
    output = _buffer(bytes([0xAA]) * 960)
    assert not helper.row(None if null == 'indices' else indices, ni,
                          None if null == 'palette' else palette, np, 0,
                          None if null == 'output' else output, no)
    assert bytes(output) == bytes([0xAA]) * 960
