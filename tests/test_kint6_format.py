"""Authored .KE envelopes exercise the immutable, bounded loading seam."""
from hashlib import sha256
import os
from pathlib import Path

import pytest

from fdisbull.kint6_format import inspect_ke_bytes, read_ke


def image(*, zero=32, stack=256, heap=4096):
    raw = bytearray(516)
    raw[:8] = bytes.fromhex('efcdab8967452301')
    raw[0xD0:0xD6] = b'KINT6\0'
    raw[0xDA:0xDC] = bytes((9, 7))
    for at, size in ((0xE0, len(raw)), (0xE8, zero), (0xF0, stack), (0xF8, heap)):
        raw[at:at + 8] = size.to_bytes(8, 'little')
    raw[512:] = bytes.fromhex('14020000')  # Authored TERM instruction.
    return bytes(raw)


def test_segments_keep_code_data_combined_and_runtime_ranges_unallocated():
    data = image(heap=2 * 1024 * 1024 * 1024)
    info = inspect_ke_bytes(data)
    assert info['sha256'] == sha256(data).hexdigest()
    assert info['header_bytes'] == info['entry_offset'] == 512
    assert info['declared_file_bytes'] == info['size_bytes'] == 516
    assert info['memory_bytes'] == 516 + 32 + 256 + 2 * 1024 * 1024 * 1024
    assert [(s['name'], s['file_offset'], s['guest_offset'], s['size_bytes'])
            for s in info['sections']] == [
        ('CODE', 0, 0, 516), ('ZERO', None, 516, 32),
        ('STACK', None, 548, 256), ('HEAP', None, 804, 2 * 1024 * 1024 * 1024),
    ]
    assert info['sections'][0]['contents'] == 'header_and_intermixed_instructions_and_initialized_data'
    assert info['qualification']['runtime_execution'] is False
    assert info['qualification']['instruction_data_partition'] == 'not_present_in_format'


def test_reserved_header_extension_does_not_become_an_invented_runtime_version():
    raw = bytearray(image())
    raw[0x110:0x118] = bytes.fromhex('0600630007000000')
    info = inspect_ke_bytes(bytes(raw))
    assert info['reserved_extension_0x110'] == '0600630007000000'
    assert info['header_revision'] == {'major': 9, 'minor': 7}
    assert info['minimum_runtime_version'] is None
    assert info['runtime_version_status'] == 'not_established_by_supported_header_contract'


@pytest.mark.parametrize('data', [None, '', bytearray(image()), memoryview(image())])
def test_only_immutable_source_bytes_are_accepted(data):
    with pytest.raises(ValueError, match='immutable'):
        inspect_ke_bytes(data)


@pytest.mark.parametrize('data', [b'', bytes(511), image()[:512], image()[:515]])
def test_short_header_or_missing_event_instruction_is_rejected(data):
    with pytest.raises(ValueError, match='truncated'):
        inspect_ke_bytes(data)


@pytest.mark.parametrize(('offset', 'value', 'message'), [
    (0xD0, b'KINT5\0', 'marker'),
    (0, bytes(8), 'sentinel'),
    (0xE0, (512).to_bytes(8, 'little'), 'CODE size'),
    (0xE0, (520).to_bytes(8, 'little'), 'CODE size'),
    (0xE8, (1 << 32).to_bytes(8, 'little'), '32-bit'),
    (0xF8, (0xFFFFFFFF).to_bytes(8, 'little'), '32-bit'),
])
def test_invalid_header_fields_are_not_silently_truncated(offset, value, message):
    raw = bytearray(image())
    raw[offset:offset + len(value)] = value
    with pytest.raises(ValueError, match=message):
        inspect_ke_bytes(bytes(raw))


def test_undeclared_trailing_bytes_are_rejected():
    with pytest.raises(ValueError, match='CODE size'):
        inspect_ke_bytes(image() + b'extra')


def test_read_is_one_immutable_snapshot(tmp_path):
    path = tmp_path / 'program.ke'
    path.write_bytes(image())
    captured = read_ke(path)
    path.write_bytes(b'replaced')
    assert captured == image()
    assert isinstance(captured, bytes)


def test_reader_refuses_symlink(tmp_path):
    path = tmp_path / 'program.ke'
    path.write_bytes(image())
    link = tmp_path / 'link.ke'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='symlink'):
        read_ke(link)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFOs are unavailable')
def test_reader_refuses_fifo_without_opening_a_blocking_stream(tmp_path):
    path = tmp_path / 'pipe.ke'
    os.mkfifo(path)
    with pytest.raises(ValueError, match='regular file'):
        read_ke(path)


def test_reader_and_byte_parser_enforce_the_same_size_budget(tmp_path, monkeypatch):
    from fdisbull import kint6_format
    data = image()
    path = tmp_path / 'program.ke'
    path.write_bytes(data)
    monkeypatch.setattr(kint6_format, 'MAX_KE_BYTES', len(data) - 1)
    with pytest.raises(ValueError, match='size limit'):
        read_ke(path)
    with pytest.raises(ValueError, match='input limit'):
        inspect_ke_bytes(data)


def test_reader_detects_file_changed_during_capture(tmp_path, monkeypatch):
    path = tmp_path / 'program.ke'
    path.write_bytes(image())
    real_fstat = os.fstat
    reads = 0

    def change_after_first_stat(fd):
        nonlocal reads
        result = real_fstat(fd)
        reads += 1
        if reads == 1:
            with Path(path).open('ab') as stream:
                stream.write(b'changed')
        return result

    monkeypatch.setattr(os, 'fstat', change_after_first_stat)
    with pytest.raises(ValueError, match='changed'):
        read_ke(path)
