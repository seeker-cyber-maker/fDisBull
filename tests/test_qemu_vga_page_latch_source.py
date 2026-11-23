"""Compile the exact patched page latch arithmetic without starting QEMU."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_qemu_video_frame_source import HEADER, extracted_header


NATIVE = Path(__file__).resolve().parents[1] / 'native'


def test_pinned_page_latch_geometry_keeps_deadline_before_the_next_row(tmp_path):
    cc = shutil.which('cc')
    git = shutil.which('git')
    if not cc or not git:
        pytest.skip('Exact patched C arithmetic requires the C compiler and git')
    header = tmp_path / HEADER
    header.parent.mkdir(parents=True)
    header.write_bytes(extracted_header())
    for package in ('qemu-video-mode13-phase', 'qemu-vga-unchained-latch'):
        directory = NATIVE / package
        manifest = json.loads((directory / 'source-manifest.json').read_bytes())
        entry = next(item for item in manifest['files'] if item['path'] == HEADER)
        patch = directory / manifest['patch']
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest['patch_sha256']
        assert hashlib.sha256(header.read_bytes()).hexdigest() == entry['base_sha256']
        subprocess.run([git, 'apply', f'--include={HEADER}', str(patch)],
                       cwd=tmp_path, check=True, capture_output=True, timeout=15)
        assert hashlib.sha256(header.read_bytes()).hexdigest() == entry['patched_sha256']

    source = tmp_path / 'probe.c'
    source.write_text(f'''
#include "{HEADER}"
#include <assert.h>

int main(void)
{{
    const int64_t line = 31700;
    const int64_t period = 14233300;
    const int64_t offset = 13060400;
    int64_t latch = -1, row = -1;
    assert(fdisbull_video_page_offset_valid(offset, line, period));
    assert(!fdisbull_video_page_offset_valid(offset + 1, line, period));
    assert(!fdisbull_video_page_offset_valid(399 * line, line, period));
    assert(!fdisbull_video_page_offset_valid(period, line, period));
    assert(!fdisbull_video_page_offset_valid(0, INT64_MAX, INT64_MAX));
    assert(fdisbull_video_page_deadline(period * 2, period, offset, &latch));
    assert(latch == 27293700);
    assert(fdisbull_video_row_deadline(period * 2, line, 0, &row));
    assert(row == 28474525 && latch + line < row);
    assert(!fdisbull_video_page_deadline(period - 1, period, offset, &latch));
    assert(!fdisbull_video_page_deadline(period * 2 + 1, period, offset, &latch));
    assert(latch == 27293700);
    assert(fdisbull_video_page_origin_valid(0x10000));
    assert(fdisbull_video_page_origin_valid(0x20000));
    assert(fdisbull_video_page_origin_valid(198144));
    assert(!fdisbull_video_page_origin_valid(198145));
    assert(!fdisbull_video_page_origin_valid(198148));
    assert(!fdisbull_video_page_origin_valid(UINT64_MAX));
    return 0;
}}
''')
    executable = tmp_path / 'page-latch-arithmetic'
    subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', str(source),
                    '-o', str(executable)], check=True, capture_output=True, timeout=15)
    subprocess.run([str(executable)], check=True, capture_output=True, timeout=15)
