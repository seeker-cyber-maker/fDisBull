"""Authored mixed LE and bound-carrier fixtures; no original game bytes."""
import hashlib
import struct

import pytest

from fdisbull.le import load_le
from fdisbull.loader import load_image
from test_le_loader import le_file


def mixed_le(bridge_base=0x60000):
    flat = struct.pack('<BBhBH', 7, 0, 1, 1, 0)
    local16 = struct.pack('<BBhBH', 5, 0, 1, 2, 3)
    return le_file(data=b'\xb8\0\0\xc3', fixups=[flat, local16],
                   object_bases=(0x10000, bridge_base), object_flags=(0x2045, 0x1045))


def bound_le(application):
    """A declared 512-byte MZ, BW header, then an exact inner MZ at 1024."""
    prefix = bytearray(1024)
    struct.pack_into('<14H', prefix, 0, 0x5a4d, 0, 1, 0, 4, 0, 0xffff,
                     0, 32, 0, 0, 0, 64, 0)
    prefix[64] = 0xc3
    prefix[512:514] = b'BW'
    struct.pack_into('<I', prefix, 512 + 28, 1024)
    return bytes(prefix) + application


def test_mixed_objects_keep_widths_and_offset16_binding_explicitly_symbolic():
    source = mixed_le()
    image = load_le(source)
    assert image.source_bytes == source
    assert image.bits == 32
    assert image.metadata['le']['mixed_bits'] is True
    assert [(r['bits'], r['object_index']) for r in image.metadata['decode_regions']] == [(32, 1), (16, 2)]
    assert [(o['bits'], o['runtime_selector']) for o in image.metadata['le']['objects']] == [(32, None), (16, None)]
    assert image.regions[1].data[:4] == b'\xb8\0\0\xc3'
    local = image.metadata['le']['fixups'][1]
    assert (local['width'], local['source_type'], local['relocated_value']) == (2, 'offset16', None)
    assert local['target_address'] == 0x60003
    assert local['encoding_domain'] == 'symbolic-offset16'
    assert local['applied'] is False and local['applied_to'] is None
    assert local['runtime_applied'] is False and local['unresolved_reason']
    assert image.metadata['le']['symbolic_fixup_count'] == 1
    assert image.metadata['le']['unique_fixup_writes'] == 1
    assert image.metadata['le']['warnings']
    assert source[local['file_offset']:local['file_offset'] + 2] == b'\0\0'


def test_offset16_retains_source_without_guessing_local_or_unaligned_linear_value():
    image = load_le(mixed_le(bridge_base=0x61230))
    fixup = image.metadata['le']['fixups'][1]
    assert fixup['target_address'] == 0x61233
    assert fixup['target_offset'] == 3
    assert fixup['relocated_value'] is None
    assert image.regions[1].data[1:3] == b'\0\0'
    assert fixup['target_address'] & 0xffff == 0x1233
    assert fixup['original_bytes'] == '0000'
    assert any(s.address == 0x61230 and s.source == 'LE executable object boundary candidate'
               for s in image.seeds)


def test_cross_page_offset16_duplicate_uses_two_byte_extent_and_original_fragments():
    code = b'\xc3' + bytes(4094) + b'\x11\x22' + bytes(5)
    first = struct.pack('<BBhBH', 5, 0, 4095, 1, 2)
    duplicate = struct.pack('<BBhBH', 5, 0, -1, 1, 2)
    image = load_le(le_file(code=code, fixups=[first, duplicate, b''],
                            object_flags=(0x1045, 0x2043)))
    assert image.regions[0].data[4095:4097] == b'\x11\x22'
    a, b = image.metadata['le']['fixups']
    assert a['original_bytes'] == b['original_bytes'] == '1122'
    assert a['width'] == b['width'] == 2 and b['duplicate_of'] == 0
    assert image.metadata['le']['unique_fixup_writes'] == 0
    assert image.metadata['le']['unique_fixup_sites'] == 1


def test_bound_carrier_normal_dispatch_preserves_full_source_and_file_coordinates(tmp_path):
    application = mixed_le()
    source = bound_le(application)
    path = tmp_path / 'bound.exe'; path.write_bytes(source)
    image = load_image(path)
    assert image.format == 'LE'
    assert image.source_bytes == source and path.read_bytes() == source
    assert image.metadata['source_sha256'] == hashlib.sha256(source).hexdigest()
    assert image.metadata['le']['header_offset'] == 1024 + 0x80
    assert image.metadata['le']['carrier']['application_offset'] == 1024
    assert image.metadata['le']['carrier']['kind'] == 'mz-bw-mz-le'
    plain = load_le(application)
    assert image.regions == plain.regions
    for a, b in zip(plain.metadata['file_mappings'], image.metadata['file_mappings']):
        assert b['file_offset'] == a['file_offset'] + 1024
    for f, original in zip(image.metadata['le']['fixups'], plain.metadata['le']['fixups']):
        assert f['record_file_offset'] == original['record_file_offset'] + 1024
        assert source[f['file_offset']:f['file_offset'] + f['width']].hex() == f['original_bytes']
    assert load_image(path, image='mz').format == 'MZ'
    assert load_image(path, image='le').regions == image.regions


def test_explicit_bridge_entry_uses_16bit_default_without_changing_address_keys():
    image = load_le(mixed_le(), entry=0x60000)
    assert image.bits == 16 and image.entry == 0x60000
    assert image.metadata['decode_regions'][1]['start'] == 0x60000


@pytest.mark.parametrize('pointer', [0, 512, 600, 999999])
def test_bound_chain_invalid_forward_pointer_fails(pointer):
    source = bytearray(bound_le(mixed_le()))
    struct.pack_into('<I', source, 512 + 28, pointer)
    with pytest.raises(ValueError, match='BW'):
        load_le(bytes(source))


def test_unindexed_le_signature_does_not_select_an_application():
    source = bytearray(bound_le(mixed_le()))
    source[512:514] = b'XX'
    with pytest.raises(ValueError, match='LE signature'):
        load_le(bytes(source))


@pytest.mark.parametrize('header_bytes', [32, 48, 144])
def test_bound_inner_secondary_field_is_inside_header_and_le_does_not_overlap_it(header_bytes):
    source = bytearray(bound_le(mixed_le()))
    struct.pack_into('<H', source, 1024 + 8, header_bytes // 16)
    if header_bytes > 128:
        struct.pack_into('<H', source, 1024 + 2, 256)
    with pytest.raises(ValueError, match='BW.*header'):
        load_le(bytes(source))


@pytest.mark.parametrize('source_object_flags,target_object_flags,target_object', [
    (0x2045, 0x1045, 2),  # a 32-bit source does not establish a 16-bit segment
    (0x1045, 0x1045, 2),  # a different object has no selected runtime segment
])
def test_cross_object_offset16_records_are_symbolic_without_inventing_a_segment(source_object_flags, target_object_flags, target_object):
    record = struct.pack('<BBhBH', 5, 0, 1, target_object, 2)
    source = le_file(fixups=[record, b''], object_flags=(source_object_flags, target_object_flags))
    image = load_le(source)
    fixup = image.metadata['le']['fixups'][0]
    assert fixup['source_object'] == 1 and fixup['target_object'] == 2
    assert fixup['runtime_selector'] is None and not fixup['applied']
    assert image.regions[0].data[:6] == b'\xb8\0\0\0\0\xc3'


def test_16bit_object_extent_and_ambiguous_selector_semantics_fail():
    with pytest.raises(ValueError, match='16-bit'):
        load_le(le_file(object_flags=(0x45, 0x2043), object_sizes=(65537, 20)))
    record = struct.pack('<BBhBH', 2, 0, 1, 2, 0)
    with pytest.raises(ValueError, match='unsupported fixup'):
        load_le(le_file(fixups=[record, b'']))
