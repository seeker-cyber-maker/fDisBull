"""Real thin Mach-O headers remain byte-identical inside universal containers."""
import hashlib
import struct

import pytest

from fdisbull.macho_slices import macho_slices, select_macho_slice
from fixtures_formats import macho_arm64


def _x86_64(subtype=3):
    data = bytearray(macho_arm64())
    struct.pack_into('<II', data, 4, 0x01000007, subtype)
    data[0x100:0x10C] = b'\xc3' + b'\x90' * 11
    return bytes(data)


def _x86():
    data = bytearray(4096)
    struct.pack_into('<7I', data, 0, 0xFEEDFACE, 7, 3, 2, 2, 80, 0)
    struct.pack_into('<II16s8I', data, 28, 1, 56, b'__TEXT', 0x1000, 4096, 0, 4096, 5, 5, 0, 0)
    struct.pack_into('<IIQQ', data, 84, 0x80000028, 24, 0x100, 0)
    data[0x100] = 0xC3
    return bytes(data)


def _fat(slices=None, *, bits=32, endian='big'):
    slices = slices or [(7, 3, _x86()), (0x01000007, 3, _x86_64()), (0x0100000C, 0, macho_arm64())]
    stride = 32 if bits == 64 else 20
    prefix = '<' if endian == 'little' else '>'
    header_end = 8 + stride * len(slices)
    position = (header_end + 4095) // 4096 * 4096
    offsets = []
    for _, _, thin in slices:
        offsets.append(position)
        position = (position + len(thin) + 4095) // 4096 * 4096
    data = bytearray(position)
    struct.pack_into(prefix + 'II', data, 0, 0xCAFEBABF if bits == 64 else 0xCAFEBABE, len(slices))
    for index, ((cpu, subtype, thin), offset) in enumerate(zip(slices, offsets)):
        values = (cpu, subtype, offset, len(thin), 12, 0) if bits == 64 else (cpu, subtype, offset, len(thin), 12)
        struct.pack_into(prefix + ('IIQQII' if bits == 64 else '5I'), data, 8 + index * stride, *values)
        data[offset:offset + len(thin)] = thin
    return bytes(data)


@pytest.mark.parametrize('bits', [32, 64])
@pytest.mark.parametrize('endian', ['big', 'little'])
def test_real_universal_inventory_and_exact_selection_for_every_table_encoding(bits, endian):
    data = _fat(bits=bits, endian=endian)
    inventory = macho_slices(data)
    assert [(item['selector'], item['arch'], item['bits']) for item in inventory] == [
        ('x86', 'x86', 32), ('x86_64', 'x86', 64), ('arm64', 'arm64', 64)]
    assert all(item['container_bits'] == bits and item['container_endian'] == endian for item in inventory)
    assert all(item['alignment'] == 12 and item['alignment_bytes'] == 4096 and item['supported'] for item in inventory)
    assert [item['offset'] for item in inventory] == [4096, 8192, 12288]
    for selector, expected in [('x86', _x86()), ('x86_64', _x86_64()), ('arm64', macho_arm64())]:
        thin, selection = select_macho_slice(data, selector)
        assert thin == expected
        assert selection['architecture'] == selector and selection['is_fat']
        assert selection['slice_offset'] == inventory[selection['slice_index']]['offset']
        assert selection['slice_size'] == len(expected) and selection['source_size'] == len(data)
        assert selection['source_sha256'] == hashlib.sha256(data).hexdigest()
        assert selection['slice_sha256'] == hashlib.sha256(expected).hexdigest()
        assert selection['slices'] == inventory


@pytest.mark.parametrize('thin,selector,wrong', [(_x86(), 'x86', 'x86_64'), (_x86_64(), 'x86_64', 'x86'),
                                               (macho_arm64(), 'arm64', 'x86_64')])
def test_thin_input_optional_selector_still_requires_matching_cpu_and_bitness(thin, selector, wrong):
    for choice in (None, selector):
        selected, metadata = select_macho_slice(thin, choice)
        assert selected == thin and not metadata['is_fat']
        assert metadata['slice_offset'] == 0 and metadata['architecture'] == selector
    with pytest.raises(ValueError, match='absent or unsupported'):
        select_macho_slice(thin, wrong)


def test_even_single_slice_universal_requires_explicit_selection_and_subtypes_are_ambiguous():
    single = _fat([(0x0100000C, 0, macho_arm64())])
    with pytest.raises(ValueError, match='explicit'):
        select_macho_slice(single)
    two = _fat([(0x01000007, 3, _x86_64(3)), (0x01000007, 8, _x86_64(8))])
    assert [item['cpu_subtype'] for item in macho_slices(two)] == [3, 8]
    with pytest.raises(ValueError, match='ambiguous'):
        select_macho_slice(two, 'x86_64')


def test_unknown_cpu_and_big_endian_thin_headers_can_be_inventoried_without_false_support():
    thin = struct.pack('>8I', 0xFEEDFACF, 0x01000012, 0, 1, 0, 0, 0, 0)
    container = _fat([(0x01000012, 0, thin)])
    item = macho_slices(container)[0]
    assert item['cpu_type'] == 0x01000012 and item['endian'] == 'big' and item['bits'] == 64
    assert item['arch'] is None and item['selector'] is None and not item['supported']
    with pytest.raises(ValueError, match='absent or unsupported'):
        select_macho_slice(container, 'arm64')


@pytest.mark.parametrize('bits', [32, 64])
@pytest.mark.parametrize('mutation,match', [('outside', 'extent'), ('zero_size', 'extent'), ('table_overlap', 'extent'),
                                         ('alignment', 'alignment'), ('huge_alignment', 'alignment'), ('overlap', 'overlap'),
                                         ('cpu', 'CPU'), ('subtype', 'subtype')])
def test_all_slice_headers_are_checked_before_any_selection(bits, mutation, match):
    data = bytearray(_fat(bits=bits))
    stride, word, offset_format = (32, 8, 'Q') if bits == 64 else (20, 4, 'I')
    # Corrupt the last, unselected ARM64 record; x86 selection must also fail.
    record = 8 + 2 * stride
    if mutation == 'outside':
        struct.pack_into('>' + offset_format, data, record + 8, (1 << bits) - 1)
    elif mutation == 'zero_size':
        struct.pack_into('>' + offset_format, data, record + 8 + word, 0)
    elif mutation == 'table_overlap':
        struct.pack_into('>' + offset_format, data, record + 8, 0)
    elif mutation == 'alignment':
        struct.pack_into('>' + offset_format, data, record + 8, 12287)
    elif mutation == 'huge_alignment':
        struct.pack_into('>I', data, record + 8 + 2 * word, bits)
    elif mutation == 'overlap':
        struct.pack_into('>' + offset_format, data, record + 8, 8192)
    elif mutation == 'cpu':
        struct.pack_into('>I', data, record, 7)
    else:
        struct.pack_into('>I', data, record + 4, 2)
    with pytest.raises(ValueError, match=match):
        select_macho_slice(data, 'x86')


@pytest.mark.parametrize('data', [b'', b'ABCD', b'\xca\xfe\xba\xbe', struct.pack('>II', 0xCAFEBABE, 0),
                                 struct.pack('>II', 0xCAFEBABE, 129), struct.pack('>II', 0xCAFEBABF, 1),
                                 b'\xcf\xfa\xed\xfe' + bytes(20)])
def test_malformed_headers_and_bounded_count_fail_cleanly(data):
    with pytest.raises(ValueError):
        macho_slices(data)


def test_fat64_reserved_field_cpu_header_width_and_load_command_limits():
    reserved = bytearray(_fat(bits=64))
    struct.pack_into('>I', reserved, 8 + 28, 1)
    with pytest.raises(ValueError, match='reserved'):
        macho_slices(reserved)
    wrong_bits = bytearray(_x86_64())
    struct.pack_into('<I', wrong_bits, 4, 7)
    with pytest.raises(ValueError, match='bitness'):
        macho_slices(wrong_bits)
    commands = bytearray(_x86_64())
    struct.pack_into('<I', commands, 16, 4097)
    with pytest.raises(ValueError, match='load-command'):
        macho_slices(commands)
    truncated = bytearray(_x86_64())
    struct.pack_into('<I', truncated, 20, len(truncated))
    with pytest.raises(ValueError, match='load-command'):
        macho_slices(truncated)


def test_input_types_selectors_and_input_size_are_bounded_without_mutating_bytes(monkeypatch):
    original = _fat()
    data = bytearray(original)
    select_macho_slice(memoryview(data), 'arm64')
    assert bytes(data) == original
    for selector in ('amd64', 'x64', False, 64):
        with pytest.raises(ValueError, match='selector'):
            select_macho_slice(original, selector)
    with pytest.raises(ValueError, match='bytes'):
        macho_slices('not bytes')
    monkeypatch.setattr('fdisbull.macho_slices.MAX_MACHO_SIZE', 100)
    with pytest.raises(ValueError, match='64 MiB'):
        macho_slices(original)
