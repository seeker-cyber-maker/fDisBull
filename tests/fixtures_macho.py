"""Small authored Mach-O command fixtures, parsed as data and never executed.

These are constructed format records, not output attributed to an unavailable
Apple SDK/toolchain. Both CPU variants use the same dyld/symbol/linkage records.
"""
from __future__ import annotations

import struct


IMAGE_BASE = 0x100000000
CODE_ADDRESS = IMAGE_BASE + 0x600
STUB_ADDRESS = IMAGE_BASE + 0x620
NONLAZY_SLOT = IMAGE_BASE + 0x1000
LAZY_SLOT = IMAGE_BASE + 0x2000
DATA_ADDRESS = IMAGE_BASE + 0x2010
LIBRARIES = ('/usr/lib/libFixture.dylib', '/usr/lib/libOther.dylib')


def _uleb(number):
    result = bytearray()
    while True:
        value = number & 127
        number >>= 7
        result.append(value | (128 if number else 0))
        if not number:
            return bytes(result)


def _export_trie():
    records = [('_fixture_export', b'\0' + _uleb(0x600)),
               ('_fixture_data', b'\0' + _uleb(0x2010)),
               ('_fixture_reexport', b'\x08\x02_other_export\0')]
    leaves = [_uleb(len(payload)) + payload + b'\0' for _, payload in records]
    offsets = [0] * len(records)
    while True:
        root = b'\0' + bytes([len(records)]) + b''.join(name.encode() + b'\0' + _uleb(offset)
                                                     for (name, _), offset in zip(records, offsets))
        cursor, new_offsets = len(root), []
        for leaf in leaves:
            new_offsets.append(cursor)
            cursor += len(leaf)
        if new_offsets == offsets:
            return root + b''.join(leaves)
        offsets = new_offsets


def _section(name, segment, address, size, offset, flags=0, reserved1=0, reserved2=0,
             relocations_offset=0, relocation_count=0):
    return struct.pack('<16s16sQQIIIIIIII', name.encode(), segment.encode(), address,
                       size, offset, 2, relocations_offset, relocation_count,
                       flags, reserved1, reserved2, 0)


def _segment(name, address, virtual_size, file_offset, file_size, protection, sections):
    return struct.pack('<II16sQQQQiiII', 0x19, 72 + 80 * len(sections), name.encode(),
                       address, virtual_size, file_offset, file_size, protection,
                       protection, len(sections), 0) + b''.join(sections)


def _dylib(command, name):
    string = name.encode() + b'\0'
    size = (24 + len(string) + 7) & ~7
    return struct.pack('<6I', command, size, 24, 0, 0x10000, 0x10000) + string.ljust(size - 24, b'\0')


def _bind(ordinal, symbol, segment):
    # Lazy records use the loader's implicit pointer type. LIEF 1.0 diagnoses
    # SET_TYPE_IMM in a lazy stream even though ordinary streams accept it.
    type_opcode = b'\x51' if segment == 1 else b''
    return bytes([0x10 | ordinal, 0x40]) + symbol.encode() + b'\0' + type_opcode + bytes([0x70 | segment, 0, 0x90, 0])


def macho_fixture(arch='x86_64', *, modern_exports=False, chained=False, consumer=False):
    """Return a thin 64-bit dylib fixture with genuine dyld/linkedit structures.

    ``chained`` replaces the nonlazy bind opcode with a one-import real
    DYLD_CHAINED_PTR_64 fixup. The lazy bind remains independently represented.
    ``modern_exports`` selects LC_DYLD_EXPORTS_TRIE over the older dyld-info field.
    ``consumer`` makes the exported code call its declared import stub, then
    return. Those authored instructions are decoded as data, never executed.
    """
    if arch not in ('x86_64', 'arm64'):
        raise ValueError('fixture arch must be x86_64 or arm64')
    cpu, subtype = (0x1000007, 3) if arch == 'x86_64' else (0x100000C, 0)
    stub_size = 6 if arch == 'x86_64' else 12
    code = (bytes.fromhex('e81b000000c3') if arch == 'x86_64' else bytes.fromhex('08000094c0035fd6')) if consumer else (bytes.fromhex('c3909090') if arch == 'x86_64' else bytes.fromhex('c0035fd6'))
    text = [_section('__text', '__TEXT', CODE_ADDRESS, len(code), 0x600, 0x80000400),
            _section('__stubs', '__TEXT', STUB_ADDRESS, stub_size, 0x620, 0x80000408, 0, stub_size),
            _section('__const', '__TEXT', IMAGE_BASE + 0x640, 8, 0x640)]
    got = [_section('__got', '__DATA_CONST', NONLAZY_SLOT, 8, 0x1000, 6, 1)]
    data_sections = [_section('__la_symbol_ptr', '__DATA', LAZY_SLOT, 8, 0x2000, 7, 2),
                     _section('__data', '__DATA', DATA_ADDRESS, 8, 0x2010,
                              relocations_offset=0x3300, relocation_count=1)]
    bind = b'' if chained else _bind(1, '_fixture_nonlazy', 1)
    lazy = _bind(2, '_fixture_call', 2)
    exports = _export_trie()
    commands = [_segment('__TEXT', IMAGE_BASE, 0x1000, 0, 0x1000, 5, text),
                _segment('__DATA_CONST', IMAGE_BASE + 0x1000, 0x1000, 0x1000, 0x1000, 3, got),
                _segment('__DATA', IMAGE_BASE + 0x2000, 0x1000, 0x2000, 0x1000, 3, data_sections),
                _segment('__LINKEDIT', IMAGE_BASE + 0x3000, 0x1000, 0x3000, 0x500, 1, []),
                _dylib(0xD, '@rpath/libConsumer.dylib'),
                _dylib(0xC, LIBRARIES[0]),
                _dylib(0x8000001F, LIBRARIES[1])]
    commands.append(struct.pack('<12I', 0x80000022, 48, 0, 0,
                                0x3000 if bind else 0, len(bind), 0, 0,
                                0x3040, len(lazy), 0 if modern_exports else 0x3080,
                                0 if modern_exports else len(exports)))
    names = ['_fixture_export', '_fixture_data', '_fixture_nonlazy', '_fixture_call']
    strings = bytearray(b'\0')
    indexes = []
    for name in names:
        indexes.append(len(strings))
        strings += name.encode() + b'\0'
    commands.append(struct.pack('<6I', 2, 24, 0x3100, 4, 0x3180, len(strings)))
    dynamic = [0xB, 80, 0, 0, 0, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0x3200, 3, 0, 0, 0, 0]
    commands.append(struct.pack('<20I', *dynamic))
    if modern_exports:
        commands.append(struct.pack('<4I', 0x80000033, 16, 0x3080, len(exports)))
    if chained:
        commands.append(struct.pack('<4I', 0x80000034, 16, 0x3400, 72 + 4 + len(b'_fixture_nonlazy\0')))
    load_commands = b''.join(commands)
    assert 32 + len(load_commands) <= 0x600
    result = bytearray(0x3500)
    result[:32] = struct.pack('<8I', 0xFEEDFACF, cpu, subtype, 6, len(commands), len(load_commands), 0x85, 0)
    result[32:32 + len(load_commands)] = load_commands
    result[0x600:0x600 + len(code)] = code
    result[0x620:0x620 + stub_size] = bytes.fromhex('ff25da190000') if arch == 'x86_64' else bytes.fromhex('100000d0100240f900021fd6')
    result[0x640:0x648] = b'CONST123'
    result[0x2010:0x2018] = struct.pack('<Q', 42)
    result[0x3000:0x3000 + len(bind)] = bind
    result[0x3040:0x3040 + len(lazy)] = lazy
    result[0x3080:0x3080 + len(exports)] = exports
    for index, (name_offset, symbol_type, section, description, value) in enumerate([
            (indexes[0], 0xF, 1, 0, CODE_ADDRESS), (indexes[1], 0xF, 6, 0, DATA_ADDRESS),
            (indexes[2], 1, 0, 1 << 8, 0), (indexes[3], 1, 0, 2 << 8, 0)]):
        result[0x3100 + index * 16:0x3110 + index * 16] = struct.pack('<IBBHQ', name_offset, symbol_type, section, description, value)
    result[0x3180:0x3180 + len(strings)] = strings
    result[0x3200:0x320C] = struct.pack('<3I', 3, 2, 3)
    # One unsigned external eight-byte relocation against _fixture_nonlazy.
    result[0x3300:0x3308] = struct.pack('<iI', 0, 2 | (3 << 25) | (1 << 27))
    if chained:
        # dyld_chained_fixups_header, starts_in_image and one starts_in_segment.
        fixups = struct.pack('<7I', 0, 28, 72, 76, 1, 1, 0)
        fixups += struct.pack('<5I', 4, 0, 20, 0, 0)
        fixups += struct.pack('<IHHQIHH', 24, 0x1000, 2, 0x1000, 0, 1, 0)
        fixups += struct.pack('<I', 1) + b'_fixture_nonlazy\0'
        assert len(fixups) == 72 + 4 + len(b'_fixture_nonlazy\0')
        result[0x3400:0x3400 + len(fixups)] = fixups
        result[0x1000:0x1008] = struct.pack('<Q', 1 << 63)
    return bytes(result)
