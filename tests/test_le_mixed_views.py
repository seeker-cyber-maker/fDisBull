"""Bounded carrier discovery uses declared origins, never a marker scan."""
import struct
import pytest
from fdisbull.image_views import image_views, secondary_header
from fdisbull.inspection import inspect_binary, identify_header
from test_le_mixed_loader import mixed_le, bound_le


def test_bound_carrier_has_independent_original_mz_and_mixed_le_views():
    source = bound_le(mixed_le())
    assert secondary_header(source) is None
    mz, le = image_views(source)
    assert mz['image'] == 'mz' and mz['loadable']
    assert le['image'] == 'le' and le['loadable'] and le['mixed_bits']
    assert le['header_offset'] == 1024 + 128
    assert le['application_file_offset'] == 1024
    assert [r['bits'] for r in le['decode_regions']] == [32, 16]
    header = identify_header(source)
    assert header['format'] == 'LE' and header['application_file_offset'] == 1024
    metadata = inspect_binary(source, image='le')
    assert metadata['selected_image'] == 'le'
    assert metadata['header']['mixed_bits']
    assert metadata['file_mappings'][0]['file_offset'] >= 1024
    assert inspect_binary(source, image='mz')['selected_image'] == 'mz'


def test_broken_declared_chain_is_not_recovered_by_scanning_a_valid_suffix():
    source = bytearray(bound_le(mixed_le()))
    struct.pack_into('<I', source, 512 + 28, len(source) + 1)
    views = image_views(bytes(source))
    assert views[0]['image'] == 'mz' and views[0]['loadable']
    assert views[1]['image'] == 'le' and not views[1]['loadable']
    assert 'next_header_pos' in views[1]['error']
    assert identify_header(bytes(source))['format'] == 'DOS MZ'
    with pytest.raises(ValueError, match='requested LE'):
        inspect_binary(bytes(source), image='le')
