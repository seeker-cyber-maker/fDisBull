"""Explicit runtime-source carrier parsing, separate from strict static import."""
import hashlib
import struct

import pytest

from fdisbull.le import load_le, load_runtime_le_carrier
from test_le_loader import le_file


def bound_le(application):
    prefix = bytearray(1024)
    struct.pack_into('<14H', prefix, 0, 0x5a4d, 0, 1, 0, 4, 0, 0xffff,
                     0, 32, 0, 0, 0, 64, 0)
    prefix[64] = 0xc3
    prefix[512:514] = b'BW'
    struct.pack_into('<I', prefix, 512 + 28, 1024)
    return bytes(prefix) + application


def mixed_le():
    return le_file(data=b'\xb8\0\0\xc3',
                   fixups=[struct.pack('<BBhBH', 7, 0, 1, 1, 0),
                           struct.pack('<BBhBH', 5, 0, 1, 2, 3)],
                   object_bases=(0x10000, 0x60000), object_flags=(0x2045, 0x1045))


def test_runtime_opt_in_retains_complete_bound_carrier_and_file_coordinates():
    application = mixed_le()
    source = bound_le(application)
    parsed = load_runtime_le_carrier(source)
    direct = load_runtime_le_carrier(application)
    assert parsed.source_bytes == source
    assert parsed.metadata['source_sha256'] == hashlib.sha256(source).hexdigest()
    assert parsed.metadata['le']['application_source_sha256'] == hashlib.sha256(application).hexdigest()
    assert parsed.metadata['le']['carrier']['application_offset'] == 1024
    assert parsed.metadata['le']['header_offset'] == 1024 + 0x80
    assert parsed.regions == direct.regions
    for inner, outer in zip(direct.metadata['file_mappings'], parsed.metadata['file_mappings']):
        assert outer['file_offset'] == inner['file_offset'] + 1024
    for inner, outer in zip(direct.metadata['le']['fixups'], parsed.metadata['le']['fixups']):
        assert outer['record_file_offset'] == inner['record_file_offset'] + 1024
        assert source[outer['file_offset']:outer['file_offset'] + outer['width']].hex() == outer['original_bytes']


def test_symbolic_offset16_and_object_widths_are_not_concrete_runtime_bindings():
    image = load_runtime_le_carrier(mixed_le())
    assert [(o['bits'], o['runtime_selector']) for o in image.metadata['le']['objects']] == [(32, None), (16, None)]
    fixup = image.metadata['le']['fixups'][1]
    assert (fixup['source_type'], fixup['width'], fixup['relocated_value']) == ('offset16', 2, None)
    assert not fixup['applied'] and not fixup['runtime_applied'] and fixup['unresolved_reason']
    assert image.regions[1].data[:4] == b'\xb8\0\0\xc3'
    assert image.metadata['le']['symbolic_fixup_count'] == 1


@pytest.mark.parametrize('source', [mixed_le(), bound_le(le_file()),
                                  le_file(fixups=[struct.pack('<BBhBH', 5, 0, 1, 2, 2), b''])])
def test_new_runtime_cases_do_not_broaden_ordinary_static_admission(source):
    with pytest.raises(ValueError):
        load_le(source)
    assert load_runtime_le_carrier(source).format == 'LE'


def test_strict_flat_profile_keeps_its_metadata_schema():
    image = load_le(le_file())
    assert 'decode_regions' not in image.metadata
    assert 'runtime_source_profile' not in image.metadata['le']
    assert 'bits' not in image.metadata['le']['objects'][0]
    assert 'runtime_applied' not in image.metadata['le']['fixups'][0]
    assert image.metadata['le']['load_model'] == 'Preferred LE object addresses with internal offset32 fixups; no runtime selectors or DOS extender execution'


@pytest.mark.parametrize('kind', ['inner-backward', 'inner-overlap', 'inner-missing', 'secondary-overlap', 'outer-size'])
def test_declared_carrier_errors_refuse_without_searching_for_other_signatures(kind):
    source = bytearray(bound_le(le_file()))
    if kind == 'inner-backward': struct.pack_into('<I', source, 512 + 28, 512)
    elif kind == 'inner-overlap': struct.pack_into('<I', source, 512 + 28, 600)
    elif kind == 'inner-missing': source[1024:1026] = b'NO'
    elif kind == 'secondary-overlap': struct.pack_into('<I', source, 1024 + 60, 32)
    else: struct.pack_into('<H', source, 4, 0)
    with pytest.raises(ValueError):
        load_runtime_le_carrier(bytes(source))


def test_cross_page_symbolic_fixup_keeps_width_and_original_fragments():
    source = le_file(code=b'\xc3' + bytes(4094) + b'\x11\x22' + bytes(5),
                     fixups=[struct.pack('<BBhBH', 5, 0, 4095, 1, 2),
                             struct.pack('<BBhBH', 5, 0, -1, 1, 2), b''],
                     object_flags=(0x1045, 0x2043))
    image = load_runtime_le_carrier(source)
    first, duplicate = image.metadata['le']['fixups']
    assert first['width'] == duplicate['width'] == 2
    assert first['original_bytes'] == duplicate['original_bytes'] == '1122'
    assert duplicate['duplicate_of'] == 0 and not duplicate['applied']
    assert image.regions[0].data[4095:4097] == b'\x11\x22'
