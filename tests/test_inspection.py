"""Container recognition and metadata preserve file-offset/VA distinctions."""
import json
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from fdisbull.inspection import identify_header, inspect_binary
from fixtures_formats import pe64, macho_arm64


def pe_import_fixture():
    data = bytearray(pe64())
    struct.pack_into('<H', data, 8, 4)
    # Import directory RVA 0x1180 is file offset 0x380 in .text.
    struct.pack_into('<II', data, 0x98 + 120, 0x1180, 40)
    struct.pack_into('<IIIII', data, 0x380, 0x11c0, 0, 0, 0x11b0, 0x11d0)
    data[0x3b0:0x3bd] = b'KERNEL32.dll\0'
    struct.pack_into('<QQ', data, 0x3c0, 0x11e0, 0)
    struct.pack_into('<QQ', data, 0x3d0, 0x11e0, 0)
    data[0x3e0:0x3e8] = b'\x07\x00Sleep\0'
    return bytes(data)


def test_header_uses_bytes_and_recognizes_pe64_and_thin_arm64():
    pe = identify_header(pe_import_fixture())
    assert pe['format'] == 'PE32+' and pe['valid']
    assert pe['bits'] == 64 and pe['arch'] == 'x86'
    assert pe['entrypoint'] == 0x140001000
    macho = identify_header(macho_arm64())
    assert macho['format'] == 'Mach-O' and macho['valid']
    assert macho['bits'] == 64 and macho['arch'] == 'arm64'


def test_pe_import_export_and_section_addresses_are_preferred_vas():
    metadata = inspect_binary(pe_import_fixture())
    section = metadata['sections'][0]
    assert (section['file_offset'], section['virtual_address']) == (0x200, 0x140001000)
    assert section['permissions'] == 'r-x'
    imported = next(item for item in metadata['imports'] if item['name'] == 'Sleep')
    assert imported['module'] == 'KERNEL32.dll'
    assert imported['address'] == 0x1400011d0
    assert imported['kind'] == 'iat' and imported['hint'] == 7
    exported = next(item for item in metadata['exports'] if item['name'] == 'helper')
    assert exported['address'] == 0x140001010
    assert exported['ordinal'] == 1 and exported['forwarder'] is None
    assert json.loads(json.dumps(metadata))['header']['valid']


def test_strings_use_file_backed_mappings_and_preserve_utf16le():
    data = bytearray(pe_import_fixture())
    data[0x260:0x269] = b'ProofText'
    data[0x280:0x28a] = 'Hello'.encode('utf-16le')
    data.extend(b'\x00OVERLAY_TEXT\x00')
    strings = inspect_binary(bytes(data))['strings']
    ascii_item = next(s for s in strings if s['text'] == 'ProofText')
    assert (ascii_item['file_offset'], ascii_item['address']) == (0x260, 0x140001060)
    wide_item = next(s for s in strings if s['text'] == 'Hello' and s['encoding'] == 'utf-16le')
    assert (wide_item['file_offset'], wide_item['address'], wide_item['size']) == (0x280, 0x140001080, 10)
    assert next(s for s in strings if s['text'] == 'OVERLAY_TEXT')['address'] is None


def test_truncated_recognized_headers_are_not_reported_valid():
    for data in [b'MZ', b'\x7fELF', macho_arm64()[:40], pe_import_fixture()[:0xa0]]:
        identified = identify_header(data)
        assert not identified['valid']
        assert identified['warnings']
        metadata = inspect_binary(data)
        assert not metadata['sections'] and not metadata['imports']
        assert metadata['warnings']


def test_legacy_mz_ne_and_fat_are_identified_without_inventing_analysis():
    mz = bytearray(256)
    mz[:2] = b'MZ'
    struct.pack_into('<H', mz, 8, 4)
    assert identify_header(bytes(mz))['format'] == 'DOS MZ'
    struct.pack_into('<I', mz, 0x3c, 0x80)
    mz[0x80:0x82] = b'NE'
    metadata = inspect_binary(bytes(mz))
    assert metadata['header']['format'] == 'NE' and metadata['header']['valid']
    assert metadata['sections'] == metadata['imports'] == metadata['exports'] == []
    fat = struct.pack('>IIIIIII', 0xcafebabe, 1, 0x100000c, 0, 28, 4, 0) + b'ABCD'
    assert identify_header(fat)['format'] == 'Mach-O fat'
    assert identify_header(fat)['valid']
    assert not identify_header(fat[:-1])['valid']


def test_raw_strings_have_no_guessed_addresses_and_scan_is_bounded():
    metadata = inspect_binary(b'ordinary raw text\x00' + b'A' * 5000)
    assert metadata['header']['format'] == 'unknown'
    assert all(s['address'] is None for s in metadata['strings'])
    large = next(s for s in metadata['strings'] if s['size'] == 5000)
    assert large['truncated'] and len(large['text']) == 4096
    assert metadata['warnings']
    with pytest.raises(ValueError, match='64 MiB'):
        identify_header(b'\x00' * (64 * 1024 * 1024 + 1))


def test_actual_elf_exports_and_unresolved_imports_are_honest(tmp_path):
    gcc = shutil.which('gcc')
    if not gcc:
        pytest.skip('gcc unavailable for ELF metadata fixture')
    source = tmp_path / 'fixture.c'
    source.write_text('#include <stdio.h>\nint helper(void){return puts("EvidenceString");}\nint main(void){return helper();}\n')
    binary = tmp_path / 'fixture'
    subprocess.run([gcc, '-rdynamic', '-o', str(binary), str(source)], check=True, capture_output=True)
    metadata = inspect_binary(binary.read_bytes())
    assert metadata['header']['format'] == 'ELF' and metadata['header']['valid']
    assert any(s['name'] == '.text' and 'x' in s['permissions'] for s in metadata['sections'])
    assert any(s['name'] == 'helper' and s['address'] > 0 for s in metadata['exports'])
    puts = next(s for s in metadata['imports'] if s['name'] == 'puts')
    assert puts['address'] is None and puts['module'] is None
    evidence = next(s for s in metadata['strings'] if s['text'] == 'EvidenceString')
    assert evidence['address'] is not None
    assert any('unresolved' in warning for warning in metadata['warnings'])


def test_import_by_ordinal_does_not_invent_a_function_name():
    data = bytearray(pe_import_fixture())
    struct.pack_into('<QQ', data, 0x3c0, (1 << 63) | 123, 0)
    struct.pack_into('<QQ', data, 0x3d0, (1 << 63) | 123, 0)
    imported = inspect_binary(bytes(data))['imports'][0]
    assert imported['name'] is None and imported['ordinal'] == 123
    assert imported['address'] == 0x1400011d0


def test_pe32_layout_and_legacy_linear_headers_are_distinguished():
    data = bytearray(pe64())
    struct.pack_into('<H', data, 0x84, 0x14c)
    struct.pack_into('<H', data, 0x98, 0x10b)
    struct.pack_into('<I', data, 0x98 + 28, 0x400000)
    header = identify_header(bytes(data))
    assert header['format'] == 'PE32' and header['bits'] == 32 and header['valid']
    assert header['imagebase'] == 0x400000 and header['entrypoint'] == 0x401000
    for signature in [b'LE', b'LX']:
        legacy = bytearray(64 + 196)
        legacy[:2] = b'MZ'
        struct.pack_into('<H', legacy, 8, 4)
        struct.pack_into('<I', legacy, 0x3c, 64)
        legacy[64:66] = signature
        assert identify_header(bytes(legacy))['format'] == signature.decode()
        assert identify_header(bytes(legacy))['valid']
        assert not identify_header(bytes(legacy[:-1]))['valid']
