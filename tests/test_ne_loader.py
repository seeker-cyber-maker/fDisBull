"""Authored Win16 NE containers; no historical executable bytes in fixtures."""
import struct

import pytest

from fdisbull.ne import load_ne, parse_address
from fdisbull.ne_processor import NEProcessor
from fdisbull.processor import Location, decode_instruction


def fixup(kind, offset, target1, target2, flags=0):
    return struct.pack('<BBHHH', kind, flags, offset, target1, target2)


def ne_file(*, code=None, fixups=None, entry_offset=0, movable=False, description=False, resource_payload=None):
    """Three ordinary segments: two code, one data with declared heap/stack.

    The default code calls a fixed internal far target, a near function, two
    symbolic imports, and an unfixed far operand whose selector happens to be2.
    That last number must never be mistaken for logical segment index2.
    """
    if code is None:
        code = bytes.fromhex('9affff0000 e80300 eb03 90 90c3 9affff0000 9affff0000 9a00000200 c3')
    if fixups is None:
        fixups = [fixup(3, 1, 2, 0), fixup(3, 14, 1, 42, 1), fixup(3, 19, 1, 7, 2)]
    pascal = lambda text: bytes([len(text)]) + text
    resident = pascal(b'PILOT') + b'\0\0' + pascal(b'FarExport') + b'\1\0\0'
    imports = pascal(b'KERNEL') + pascal(b'BEEP')
    entries = b'\1\xff\1\xcd\x3f\2\0\0\0' if movable else b'\1\2\1\0\0\0'
    h, segtab, resource = 0x80, 0x40, 0x58
    resource_bytes = (struct.pack('<HHHI', 0, 0x800a, 1, 0) + struct.pack('<6H', 0, len(resource_payload), 0, 0x8001, 0, 0) + b'\0\0'
                      if resource_payload is not None else bytes(4))
    names = resource + len(resource_bytes)
    refs = names + len(resident)
    import_names = refs + 2
    entry_table = import_names + len(imports)
    image = bytearray(0x200)
    image[:2] = b'MZ'
    for offset, value in {4: 1, 8: 4, 12: 0xffff, 24: 0x40}.items():
        struct.pack_into('<H', image, offset, value)
    struct.pack_into('<I', image, 60, h)
    image[64] = 0xc3
    image[h:h + 2] = b'NE'
    for offset, value in {4: entry_table, 6: len(entries), 14: 3, 16: 8, 18: 16,
                          20: entry_offset, 22: 1, 26: 3, 28: 3, 30: 1,
                          34: segtab, 36: resource, 38: names, 40: refs, 42: import_names,
                          48: int(movable), 50: 4}.items():
        struct.pack_into('<H', image, h + offset, value)
    image[h + 54] = 2
    image[h + resource:h + resource + len(resource_bytes)] = resource_bytes
    image[h + names:h + names + len(resident)] = resident
    image[h + import_names:h + import_names + len(imports)] = imports
    image[h + entry_table:h + entry_table + len(entries)] = entries
    for index, (payload, minimum) in enumerate(((code, len(code)), (b'\xb8\7\0\xcb', 4), (b'fixture data\0', 48))):
        image.extend(bytes((-len(image)) % 16))
        offset = len(image)
        flags = 1 if index == 2 else 0
        if index == 0 and fixups:
            flags |= 0x100
        struct.pack_into('<4H', image, h + segtab + 8 * index,
                         offset >> 4, len(payload) & 0xffff, flags, minimum & 0xffff)
        image.extend(payload)
        if index == 0 and fixups:
            image.extend(struct.pack('<H', len(fixups)) + b''.join(fixups))
    if resource_payload is not None:
        struct.pack_into('<H', image, h + resource + 10, len(image))
        image.extend(resource_payload)
    if description:
        text = pascal(b'Authored module description') + b'\xe1\0\0'
        struct.pack_into('<H', image, h + 32, len(text))
        struct.pack_into('<I', image, h + 44, len(image))
        image.extend(text)
    return bytes(image)


def test_segments_source_bytes_and_symbolic_fixup_operands():
    original = ne_file()
    image = load_ne(original)
    metadata = image.metadata['ne']
    assert (image.format, image.arch, image.bits, image.entry) == ('NE', 'x86', 16, 0x10000)
    assert image.source_bytes == original
    assert metadata['segments'][2]['allocation_size'] == 72
    assert metadata['segments'][2]['zero_fill_size'] == 59
    assert [(row['module'], row['name'], row['ordinal'], row['address']) for row in metadata['imports']] == [('KERNEL', None, 42, None), ('KERNEL', 'BEEP', None, None)]
    assert metadata['fixup_count'] == metadata['fixup_source_count'] == 3
    assert metadata['fixups'][0]['sources'][0]['original_bytes'] == 'ffff0000'
    assert all(not row['applied'] and row['runtime_selector'] is None for row in metadata['fixups'])
    assert metadata['file_mappings'][2]['file_size'] == 13
    assert image.regions[-1].data == bytes(59) and not image.regions[-1].executable


def test_native_near_targets_and_qualified_far_targets_preserve_operands():
    image = load_ne(ne_file()); processor = NEProcessor(image.metadata['ne'])
    code = image.regions[0].data
    decode = lambda offset: decode_instruction(processor, code[offset:], Location('ne.segment', 0x10000 | offset)).facts
    assert decode(0)['target'] == 0x20000
    assert decode(0)['bytes'] == '9affff0000'
    assert 'FFFF' in decode(0)['operands'].upper()
    assert decode(5)['target'] == 0x1000b
    assert decode(8)['target'] == 0x1000d
    assert decode(13)['target'] is None and decode(13)['flow'] == 'indirect_call'
    assert decode(13)['ne_fixups'][0]['import_ordinal'] == 42
    assert decode(18)['ne_fixups'][0]['import_name'] == 'BEEP'
    assert decode(23)['target'] is None and decode(23)['ne_fixups'] == []
    patched = decode_instruction(processor, bytes.fromhex('9a10000000'), Location('ne.segment', 0x10000)).facts
    assert patched['target'] is None and not patched['ne_fixups'][0]['operand_bytes_unchanged']


def test_chained_fixups_and_movable_entry_ordinal_resolution():
    code = bytes.fromhex('9a06000000 c3 ffff0000')
    image = load_ne(ne_file(code=code, fixups=[fixup(3, 1, 255, 1)], movable=True))
    row = image.metadata['ne']['fixups'][0]
    assert row['target_ordinal'] == 1 and row['logical_target'] == 0x20000
    assert [source['offset'] for source in row['sources']] == [1, 6]
    assert row['sources'][0]['original_bytes'] == '06000000'
    assert row['sources'][1]['original_bytes'] == 'ffff0000'


@pytest.mark.parametrize('record,code,target', [
    (fixup(3, 1, 2, 1, 4), bytes.fromhex('9a01000000 c3'), 0x20002),
    (fixup(2, 3, 2, 0, 4), bytes.fromhex('9a01000000 c3'), 0x20001),
    (fixup(2, 3, 2, 0, 0), bytes.fromhex('9a0100ffff c3'), 0x20001),
])
def test_additive_far_and_selector_fixups_are_declarations(record, code, target):
    image = load_ne(ne_file(code=code, fixups=[record])); p = NEProcessor(image.metadata['ne'])
    decoded = p.decode(code, Location('ne.segment', 0x10000)).facts
    assert decoded['target'] == target and decoded['bytes'] == code[:5].hex()
    assert not image.metadata['ne']['fixups'][0]['applied']


def test_nonresident_description_is_not_an_export_ordinal():
    assert len(load_ne(ne_file(description=True)).metadata['ne']['exports']) == 1


def test_selector_fixup_does_not_claim_its_unused_target2_is_an_offset():
    original = ne_file(code=bytes.fromhex('9a0100ffff c3'), fixups=[fixup(2, 3, 2, 0xffff)])
    image = load_ne(original)
    record = image.metadata['ne']['fixups'][0]
    assert record['raw_target2'] == 0xffff
    assert record['target_segment_index'] == 2
    assert record['logical_target'] is record['target_offset'] is None
    assert NEProcessor(image.metadata['ne']).decode(image.regions[0].data, Location('ne.segment', 0x10000)).facts['target'] == 0x20001


def test_separate_far_offset_and_selector_fixups_require_both_fields():
    code = bytes.fromhex('9affffffff c3')
    image = load_ne(ne_file(code=code, fixups=[fixup(5, 1, 2, 1), fixup(2, 3, 2, 0)]))
    processor = NEProcessor(image.metadata['ne'])
    assert processor.decode(code, Location('ne.segment', 0x10000)).facts['target'] == 0x20001
    changed = bytes.fromhex('9a0200ffff c3')
    assert processor.decode(changed, Location('ne.segment', 0x10000)).facts['target'] is None


def test_unrelocated_near_operand_does_not_become_a_false_branch():
    code = bytes.fromhex('e8ffff c3')
    image = load_ne(ne_file(code=code, fixups=[fixup(5, 1, 1, 3)]))
    assert NEProcessor(image.metadata['ne']).decode(code, Location('ne.segment', 0x10000)).facts['target'] is None


@pytest.mark.parametrize('changes,match', [
    ([(0x80 + 54, b'\1')], 'Windows16'),
    ([(0x80 + 12, b'\0\x08')], 'self-loading'),
    ([(0x80 + 50, b'\x10\0')], 'alignment'),
    ([(0x80 + 0x40 + 4, b'\x08\0')], 'iterated'),
    ([(0x80 + 0x40 + 4, b'\0\x20')], '32-bit'),
    ([(0x80 + 0x40, b'\xff\xff')], 'bounds'),
    ([(0x80 + 22, b'\x04\0')], 'target'),
    ([(0x80 + 6, b'\1\0')], 'bundle'),
    ([(0x80 + 40, b'\x40\0')], 'overlap|import'),
])
def test_rejects_unsupported_and_malformed_layouts(changes, match):
    data = bytearray(ne_file())
    for offset, replacement in changes:
        data[offset:offset + len(replacement)] = replacement
    with pytest.raises(ValueError, match=match):
        load_ne(bytes(data))


@pytest.mark.parametrize('record,code,match', [
    (fixup(3, 1, 2, 0), bytes.fromhex('9a01000000 c3'), 'cycles'),
    (fixup(3, 5, 2, 0), bytes.fromhex('9affff0000 c3'), 'bounds'),
    (fixup(3, 1, 4, 0), bytes.fromhex('9affff0000 c3'), 'target'),
    (fixup(3, 1, 255, 99), bytes.fromhex('9affff0000 c3'), 'ordinal'),
    (fixup(3, 1, 2, 1, 1), bytes.fromhex('9affff0000 c3'), 'module index'),
    (fixup(3, 1, 1, 0xffff, 2), bytes.fromhex('9affff0000 c3'), 'string'),
    (fixup(11, 1, 2, 0), bytes.fromhex('9affff0000 c3'), 'encoding'),
])
def test_rejects_bad_fixup_chains_imports_and_targets(record, code, match):
    with pytest.raises(ValueError, match=match):
        load_ne(ne_file(code=code, fixups=[record]))


@pytest.mark.parametrize('value', ['20:0122', 'ne:20:0122', 'ne:0:0', 'ne:1:0x10000', 'ne:x:0'])
def test_ambiguous_or_invalid_segment_addresses_refused(value):
    with pytest.raises(ValueError):parse_address(value)


def test_segment_index_is_not_a_real_mode_selector():
    assert parse_address('ne:20:0x0122') == parse_address('ne:0x14:290') == 0x140122


def test_resource_ranges_are_retained_without_becoming_mapped_segments():
    data = ne_file(resource_payload=b'ICON')
    image = load_ne(data); metadata = image.metadata['ne']
    resource = metadata['resources'][0]
    assert resource['type'] == 10 and resource['id'] == 1
    assert data[resource['file_offset']:resource['file_offset'] + resource['file_size']] == b'ICON'
    assert all(resource['file_offset'] >= m['file_offset'] + m['file_size'] for m in metadata['file_mappings'])
    from fdisbull.inspection import inspect_binary
    assert next(row for row in inspect_binary(data)['strings'] if row['text'] == 'ICON')['address'] is None


def test_every_truncation_refuses_cleanly_and_budgets_are_enforced(monkeypatch):
    data = ne_file()
    for length in range(len(data)):
        with pytest.raises(ValueError):load_ne(data[:length])
    import fdisbull.ne as ne
    monkeypatch.setattr(ne, 'MAX_FIXUPS', 2)
    with pytest.raises(ValueError, match='records exceed'):load_ne(data)
    monkeypatch.setattr(ne, 'MAX_FIXUPS', 65536)
    monkeypatch.setattr(ne, 'MAX_SITES', 2)
    with pytest.raises(ValueError, match='sources exceed'):load_ne(data)


def test_entryless_module_explicit_and_dll_mode():
    data = bytearray(ne_file()); struct.pack_into('<H', data, 0x80 + 22, 0)
    with pytest.raises(ValueError, match='no entry'):load_ne(bytes(data))
    assert load_ne(bytes(data), module=True).metadata['entrypoint_present'] is False
    struct.pack_into('<H', data, 0x80 + 12, 0x8000)
    assert load_ne(bytes(data)).metadata['ne']['is_dll']


def test_opcode_inside_an_earlier_fixup_is_not_decoded_from_unrelocated_bytes():
    # Independent review repro: 00e8 +0100 changes the entry opcode E8 to E9.
    # Its relocation starts one byte before the requested entry instruction.
    code = bytearray(300); code[2:6] = bytes.fromhex('e80000c3')
    image = load_ne(ne_file(code=bytes(code), fixups=[fixup(5, 1, 1, 0x100, 4)], entry_offset=2))
    assert NEProcessor(image.metadata['ne']).decode(bytes(code[2:]), Location('ne.segment', 0x10002)) is None


def test_truncated_instruction_cannot_fetch_from_the_next_logical_segment():
    code = b'\xc3' + bytes(65534) + b'\xe8'
    image = load_ne(ne_file(code=code, fixups=[], entry_offset=65535))
    assert NEProcessor(image.metadata['ne']).decode(b'\xe8' + b'\0' * 10, Location('ne.segment', 0x1ffff)) is None


@pytest.mark.parametrize('encoded,record', [
    ('66b800000000c3', fixup(5, 0, 1, 0x100, 4)),
    ('8b060000c3', fixup(0, 1, 1, 1, 4)),
    ('678b042500000000c3', fixup(0, 3, 1, 1, 4)),
])
def test_structural_prefix_modrm_and_sib_fixups_cannot_drive_native_successors(encoded, record):
    code = bytes.fromhex(encoded) + bytes(300)
    image = load_ne(ne_file(code=code, fixups=[record]))
    processor = NEProcessor(image.metadata['ne'])
    assert processor.decode(code, Location('ne.segment', 0x10000)) is None
    assert 'instruction structure' in processor.last_failure


@pytest.mark.parametrize('offset', [1, 2])
def test_partial_lowbyte_far_offset_fixup_cannot_hide_behind_a_selector(offset):
    code = bytes.fromhex('9a00000000c3')
    records = [fixup(0, offset, 2, 1, 4), fixup(2, 3, 2, 0, 4)]
    image = load_ne(ne_file(code=code, fixups=records))
    result = NEProcessor(image.metadata['ne']).decode(code, Location('ne.segment', 0x10000))
    assert result.facts['target'] is None and result.facts['flow'] == 'indirect_call'
    assert all(edge.target is None or edge.kind == 'fallthrough' for edge in result.successors)
    assert len(result.facts['ne_fixups']) == 2
