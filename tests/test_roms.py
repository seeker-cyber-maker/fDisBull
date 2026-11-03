"""Public console inspection preserves bytes, offsets and parsing-only scope."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.inspection import identify_header, inspect_binary
from fdisbull.rom_disc import parse_sega_disc, parse_iso_primary, parse_disc_volume
from fdisbull.roms import inspect_rom, inspect_rom_path


def saturn(raw=False):
    data = bytearray(2352 if raw else 2048)
    offset = 16 if raw else 0
    if raw:
        data[:12] = b'\x00' + b'\xff' * 10 + b'\x00'
        data[15] = 1
    data[offset:offset + 16] = b'SEGA SEGASATURN '
    data[offset + 0x20:offset + 0x2a] = b'T-TEST    '
    data[offset + 0x60:offset + 0x68] = b'ROM TEST'
    return bytes(data)


def test_nes_public_routes_keep_file_offsets_and_no_cpu_addresses():
    data = b'NES\x1a' + bytes([1, 0]) + bytes(10) + b'Fixture text\x00' + bytes(16371)
    original = hashlib.sha256(data).hexdigest()
    header = identify_header(data)
    assert header['family'] == 'console ROM' and header['valid']
    assert header['loadable'] is False
    result = inspect_binary(data)
    assert result['sections'] == result['imports'] == result['exports'] == []
    assert all(x['address'] is None for x in result['strings'])
    rom = result['rom']
    assert rom['source_sha256'] == original
    assert rom['regions'][1]['file_offset'] == 16
    assert rom['regions'][1]['file_size'] == 16384


def test_disc_descriptor_formats_and_physical_offsets():
    for raw in (False, True):
        result = inspect_rom(saturn(raw))
        assert result['valid'] and result['platform'] == 'Sega Saturn'
        assert result['metadata']['product'] == 'T-TEST'
        assert result['metadata']['title'] == 'ROM TEST'
        assert result['regions'][0]['file_offset'] == (16 if raw else 0)
        assert result['loadable'] is False
    data = bytearray(2048)
    data[:16] = b'SEGADISCSYSTEM  '
    assert inspect_rom(bytes(data))['platform'] == 'Sega CD / Mega-CD'
    assert not parse_sega_disc(saturn()[:256])['valid']
    assert not parse_sega_disc(saturn() + b'x')['valid']
    # Signature at 16 without a raw-sector sync/header is not track evidence.
    assert parse_sega_disc(bytes(16) + saturn()) is None


def test_large_disc_path_reads_prefix_only_and_cli_json(tmp_path):
    path = tmp_path / 'track.bin'
    data = saturn(True)
    with path.open('wb') as stream:
        stream.write(data)
        stream.truncate(2352 * 40000)
        stream.seek(2352 * 16)
        stream.write(data[:16] + bytes(2352 - 16))
    result = inspect_rom_path(path)
    assert result['valid'] and result['source_size'] == 94080000
    assert result['source_sha256'] is None
    assert result['prefix_size'] == 4096
    with path.open('rb') as stream:
        assert result['prefix_sha256'] == hashlib.sha256(stream.read(4096)).hexdigest()
    proc = subprocess.run([sys.executable, '-m', 'fdisbull', 'rom-inspect', str(path)],
                          check=True, capture_output=True, text=True,
                          env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1] / 'src')})
    cli = json.loads(proc.stdout)
    # CLI output envelopes are shared with ordinary standalone methods.
    payload = cli.get('result', cli)
    assert payload['format'] == 'Sega Saturn disc'
    assert payload['source_sha256'] is None


def test_unknown_and_limits_fail_without_extension_guess(tmp_path):
    path = tmp_path / 'claimed.nes'
    path.write_bytes(b'not a ROM')
    assert inspect_rom_path(path)['format'] == 'unknown'
    assert inspect_rom(b'')['valid'] is False
    with pytest.raises(ValueError):
        inspect_rom(bytearray())
    with path.open('wb') as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='disc reader'):
        inspect_rom_path(path)


def test_primary_volume_extent_and_endian_disagreement():
    block = bytearray(2048)
    block[:7] = b'\x01CD001\x01'
    block[40:44] = b'TEST'
    for pos, size, value in ((80, 4, 100), (128, 2, 2048),
                              (158, 4, 20), (166, 4, 2048)):
        block[pos:pos + size] = value.to_bytes(size, 'little')
        block[pos + size:pos + 2 * size] = value.to_bytes(size, 'big')
    block[156] = 34
    block[181] = 2
    block[188:190] = b'\x01\x00'
    assert parse_iso_primary(bytes(block), physical_sectors=100)['valid']
    shorter = parse_iso_primary(bytes(block), physical_sectors=90)
    assert not shorter['valid'] and shorter['volume_id'].startswith('TEST')
    assert 'individual file completeness is unknown' in shorter['warnings'][0]
    block[84] = 1
    assert not parse_iso_primary(bytes(block), physical_sectors=100)['valid']
    raw = bytearray(2352)
    raw[16:2064] = block
    assert not parse_disc_volume(bytes(raw), sector_size=2352, physical_sectors=100)['valid']
    mode2 = bytearray(saturn(True))
    mode2[15] = 2
    mode2[16:32] = bytes(16)
    mode2[24:40] = b'SEGA SEGASATURN '
    assert parse_sega_disc(bytes(mode2)) is None
