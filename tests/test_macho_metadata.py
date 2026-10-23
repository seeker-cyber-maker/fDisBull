"""Mach-O metadata identifies dyld slots, code aliases and export provenance."""
import json
import struct

import lief
import pytest

from fdisbull.macho_metadata import inspect_macho
from fixtures_macho import (CODE_ADDRESS, DATA_ADDRESS, LAZY_SLOT, LIBRARIES,
                            NONLAZY_SLOT, STUB_ADDRESS, macho_fixture)


def _inspect(data=None, arch='x86_64', **options):
    data = macho_fixture(arch) if data is None else bytes(data)
    parsed = lief.MachO.parse(list(data))
    assert parsed is not None and parsed.size == 1
    return inspect_macho(parsed.at(0), data, **options)


def _by_name(records):
    return {record['name']: record for record in records}


def _sources(record):
    return json.dumps({key: record.get(key) for key in ('source', 'evidence', 'provenance')}, sort_keys=True)


def _replace_classic_trie(data, payload):
    result = bytearray(data)
    assert len(payload) < 0x80  # Keep the fixture's separate symbol table intact.
    result[0x3080:0x3100] = payload.ljust(0x80, b'\0')
    position = 32
    for _ in range(struct.unpack_from('<I', result, 16)[0]):
        command, size = struct.unpack_from('<II', result, position)
        if command == 0x80000022:
            struct.pack_into('<I', result, position + 44, len(payload))
            return bytes(result)
        position += size
    raise AssertionError('authored fixture is missing dyld-info command')


def _single_export(name, payload):
    label = name.encode() + b'\0'
    offset = 2 + len(label) + 1
    assert offset < 128 and len(payload) < 128
    return bytes([0, 1]) + label + bytes([offset, len(payload)]) + payload + b'\0'


def _assert_bindings(result):
    assert len(result['imports']) == 2
    imports = _by_name(result['imports'])
    nonlazy, call = imports['_fixture_nonlazy'], imports['_fixture_call']
    assert nonlazy['address'] == NONLAZY_SLOT and nonlazy['module'] == LIBRARIES[0]
    assert call['address'] == LAZY_SLOT and call['module'] == LIBRARIES[1]
    assert nonlazy['library_ordinal'] == 1 and call['library_ordinal'] == 2
    assert nonlazy['stub_addresses'] == [] and call['stub_addresses'] == [STUB_ADDRESS]
    for item in imports.values():
        assert item['kind'] == 'dyld_pointer' and item['target'] is None
        assert item['binding_state'] == 'runtime_unresolved' and item['pointer_width'] == 8
        assert item['ordinal'] is None
        assert item['binding_class'] is not None
        assert 'dyld_bind' in _sources(item)
    # The image's own LC_ID_DYLIB is not import-library ordinal one.
    assert [item['ordinal'] for item in result['libraries']] == [1, 2]
    assert [item['name'] for item in result['libraries']] == list(LIBRARIES)
    assert not any('libConsumer' in item['name'] for item in result['libraries'])


def test_x86_64_native_bindings_join_slots_to_stubs_by_indirect_symbol_index():
    result = _inspect()
    _assert_bindings(result)
    assert result['availability']
    assert not result['truncated']['imports']
    json.dumps(result)


def test_arm64_native_bindings_use_the_same_metadata_contract():
    result = _inspect(arch='arm64')
    _assert_bindings(result)


def _assert_exports(result):
    assert len(result['exports']) == 3
    exported = _by_name(result['exports'])
    code, data, reexport = exported['_fixture_export'], exported['_fixture_data'], exported['_fixture_reexport']
    assert code['address'] == CODE_ADDRESS and code['kind'] == 'code' and code['is_code']
    assert data['address'] == DATA_ADDRESS and data['kind'] == 'data' and not data['is_code']
    assert code['forwarder'] is None and data['forwarder'] is None
    assert reexport['address'] is None and reexport['kind'] == 'reexport' and not reexport['is_code']
    assert reexport['reexport']['module'] == LIBRARIES[1]
    assert reexport['reexport']['name'] == '_other_export'
    assert reexport['reexport']['library_ordinal'] == 2
    assert reexport['forwarder']


def test_classic_export_trie_retains_reexports_omitted_by_native_exported_symbols():
    _assert_exports(_inspect())
    for flags, expected_kind in ((2, 'absolute'), (1, 'thread_local')):
        data = bytearray(macho_fixture())
        # The authored code leaf is terminal-size3, flags0, ULEB(0x600), no children.
        leaf = data.index(bytes.fromhex('0300800c00'), 0x3080, 0x3100)
        data[leaf + 1] = flags
        exported = _by_name(_inspect(data)['exports'])['_fixture_export']
        assert exported['kind'] == expected_kind and not exported['is_code']
        if expected_kind == 'absolute':
            assert exported['address'] == 0x600


def test_modern_export_command_preserves_code_data_and_true_reexport_alias():
    _assert_exports(_inspect(macho_fixture('arm64', modern_exports=True)))


def test_chained_fixups_binding_is_enumerated_separately_from_classic_dyld_bindings():
    for arch in ('x86_64', 'arm64'):
        result = _inspect(macho_fixture(arch, modern_exports=True, chained=True))
        imports = _by_name(result['imports'])
        assert len(imports) == 2
        chained = imports['_fixture_nonlazy']
        assert chained['address'] == NONLAZY_SLOT and chained['module'] == LIBRARIES[0]
        assert chained['library_ordinal'] == 1 and chained['target'] is None
        assert 'dyld_chained_fixups' in _sources(chained)
        assert imports['_fixture_call']['stub_addresses'] == [STUB_ADDRESS]


def test_permissions_come_from_segments_and_code_classification_retains_section_flags():
    result = _inspect()
    sections = {item['full_name']: item for item in result['sections']}
    assert result['section_permissions']['__TEXT:__text'] == 'r-x'
    assert result['section_permissions']['__TEXT:__const'] == 'r-x'
    assert result['section_permissions']['__DATA_CONST:__got'] == 'rw-'
    assert result['section_permissions']['__DATA:__data'] == 'rw-'
    assert sections['__TEXT:__text']['is_code'] and sections['__TEXT:__stubs']['is_code']
    assert not sections['__TEXT:__const']['is_code']
    assert not sections['__DATA:__data']['is_code']
    assert all(item['permissions'] == result['section_permissions'][item['full_name']] for item in sections.values())


def test_relocation_address_and_width_use_actual_section_relocation_record():
    result = _inspect()
    assert len(result['relocations']) == 1
    relocation = result['relocations'][0]
    assert relocation['address'] == DATA_ADDRESS
    assert relocation['width'] == 8
    assert relocation['symbol'] == '_fixture_nonlazy'
    assert relocation['target'] is None and relocation['source']


@pytest.mark.parametrize('arch', ['x86_64', 'arm64'])
def test_negative_64bit_relocation_offset_is_not_a_scattered_in_section_record(arch):
    data = macho_fixture(arch)
    parsed = lief.MachO.parse(list(data)).at(0)
    malformed = bytearray(data)
    struct.pack_into('<II', malformed, 0x3300, 0x80000000, 0)
    result = inspect_macho(parsed, bytes(malformed))
    assert not result['relocations']
    assert 'relocations' in result['availability']['partial_categories']
    assert any('relocation offset' in warning for warning in result['warnings'])


@pytest.mark.parametrize('indirect_index', [0x80000000, 0x40000000, 0x7FFFFFFF])
def test_local_absolute_or_out_of_range_indirect_entries_do_not_invent_stub_aliases(indirect_index):
    data = bytearray(macho_fixture())
    struct.pack_into('<I', data, 0x3200, indirect_index)
    result = _inspect(data)
    assert len(result['imports']) == 2
    assert not any(STUB_ADDRESS in item['stub_addresses'] for item in result['imports'])
    assert {item['address'] for item in result['imports']} == {NONLAZY_SLOT, LAZY_SLOT}


def test_item_caps_are_explicit_and_do_not_silently_claim_full_metadata():
    result = _inspect(max_items=1)
    assert len(result['imports']) == len(result['exports']) == 1
    assert result['truncated']['imports'] and result['truncated']['exports']
    assert result['warnings']
    assert result['availability']
    assert len(result['relocations']) == 1 and not result['truncated']['relocations']


def test_export_and_resolver_preferred_addresses_cannot_overflow_the_header_width():
    base = macho_fixture()
    parsed = lief.MachO.parse(list(base)).at(0)
    maximum_uleb = b'\xff' * 9 + b'\x01'
    for terminal in (b'\0' + maximum_uleb, b'\x10\x80\x0c' + maximum_uleb):
        # Use an already-parsed matching header/sections; only corrupt the raw
        # trie being checked, avoiding reliance on native malformed-trie policy.
        data = _replace_classic_trie(base, _single_export('_overflow', terminal))
        result = inspect_macho(parsed, data)
        assert result['warnings']
        assert 'exports' in result['availability']['partial_categories']
        for exported in result['exports']:
            assert exported['address'] is None or 0 <= exported['address'] < 1 << 64
            resolver = exported.get('resolver_address')
            assert resolver is None or 0 <= resolver < 1 << 64


def test_cyclic_or_malformed_raw_export_tries_are_explicitly_partial():
    base = macho_fixture()
    parsed = lief.MachO.parse(list(base)).at(0)
    for payload in (b'\0\x01cycle\0\0', b'\xff' * 11):
        result = inspect_macho(parsed, _replace_classic_trie(base, payload))
        assert result['warnings']
        assert 'exports' in result['availability']['partial_categories']
        assert not result['exports']


def test_invalid_bounds_and_truncated_raw_command_tables_are_rejected():
    data = macho_fixture()
    parsed = lief.MachO.parse(list(data)).at(0)
    for maximum in (0, -1, True, 1.5, '1', None):
        with pytest.raises(ValueError):
            inspect_macho(parsed, data, max_items=maximum)
    malformed = [data[:20], data[:100]]
    short_command = bytearray(data)
    struct.pack_into('<I', short_command, 36, 4)
    malformed.append(short_command)
    impossible_commands = bytearray(data)
    struct.pack_into('<I', impossible_commands, 20, 0xFFFFFFFF)
    malformed.append(impossible_commands)
    for raw in malformed:
        with pytest.raises(ValueError):
            inspect_macho(parsed, bytes(raw))
