"""Bounded Win16 NE loading with logical segment identities and symbolic fixups.

No selector allocation or relocation is applied to bytes. The packed SQLite key
is ``segment_index << 16 | offset``; it is never a real-mode linear address.
Format references: Open Watcom ``bld/watcom/h/exeos2.h`` and Wine 10.0
``dlls/krnl386.exe16/ne_segment.c`` / ``include/wine/winbase16.h``.
"""
from __future__ import annotations

import struct
import hashlib

from .model import Image, Region, Seed

MAX_SOURCE = 64 * 1024 * 1024
MAX_SEGMENTS = 4096
MAX_FIXUPS = 65536
MAX_SITES = 262144
MAX_NAMES = 65536
_WIDTHS = {0: 1, 2: 2, 3: 4, 5: 2}
_KINDS = {0: 'low_byte', 2: 'selector16', 3: 'pointer16:16', 5: 'offset16'}


def logical_location(address: int) -> dict:
    segment, offset = address >> 16, address & 0xffff
    return dict(space='ne.segment', segment_index=segment, offset=offset,
                address=f'ne:{segment}:{offset:#06x}', key=hex(address), runtime_selector=None)


def parse_address(value) -> int:
    if isinstance(value, str) and ':' in value:
        fields = value.split(':')
        if len(fields) != 3 or fields[0].lower() != 'ne':
            raise ValueError('NE addresses require ne:SEGMENT_INDEX:0xOFFSET; DOS segment:offset is not an NE identity')
        try:
            segment, offset = (int(part, 0) for part in fields[1:])
        except ValueError as exc:
            raise ValueError('NE segment index and offset require decimal or explicit 0x hexadecimal integers') from exc
        if not 1 <= segment <= 0xffff or not 0 <= offset <= 0xffff:
            raise ValueError('NE segment index/offset is outside the 16-bit logical range')
        return segment << 16 | offset
    from .project import number
    address = number(value)
    if not 0x10000 <= address <= 0xffffffff:
        raise ValueError('NE numeric addresses must be packed nonzero segment-index/16-bit-offset keys')
    return address


def following(address: int, size: int) -> int:
    return (address & ~0xffff) | ((address + size) & 0xffff)


def _range(data, offset, size, label):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f'NE {label} exceeds source bounds')
    return data[offset:offset + size]


def load_ne(data: bytes, *, entry: int | None = None, module: bool = False) -> Image:
    """Map ordinary Win16 NE segments, retaining original operands and imports.

    Iterated/32-bit segments, self-loading modules, OS/2 and nonstandard source
    relocation widths are refused. OS floating-point fixups remain symbolic.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_SOURCE:
        raise ValueError('NE source must contain 1..64 MiB immutable bytes')
    from .image_views import secondary_header
    secondary = secondary_header(data)
    if not secondary or secondary['format'] != 'NE':
        raise ValueError('NE requires an independent MZ secondary NE header')
    h = secondary['header_offset']
    raw = _range(data, h, 64, 'header')
    word = lambda offset: struct.unpack_from('<H', raw, offset)[0]
    dword = lambda offset: struct.unpack_from('<I', raw, offset)[0]
    flags, count, alignment = word(12), word(28), word(50)
    if raw[54] != 2:
        raise ValueError('NE static profile supports Windows16 target OS 2 only')
    if flags & (0x10 | 0x800 | 0x2000):
        raise ValueError('NE Win32, self-loading and link-error modules are unsupported')
    if not 1 <= count <= MAX_SEGMENTS or alignment > 15:
        raise ValueError('NE segment count/alignment is outside the supported budget')
    autodata, stack_segment = word(14), word(26)
    if autodata > count or stack_segment > count:
        raise ValueError('NE automatic data/stack segment index is invalid')
    heap_size, stack_size = word(16), word(18)
    table_offsets = [word(offset) for offset in (4, 34, 36, 38, 40, 42) if word(offset)]
    structural = [(h, h + 64)]

    def relative(offset, size, label):
        if offset < 64:
            raise ValueError(f'NE {label} overlaps the fixed header')
        _range(data, h + offset, size, label)
        return h + offset

    table = relative(word(34), count * 8, 'segment table')
    structural.append((table, table + count * 8))
    segments, regions, sections, mappings = [], [], [], []
    total = 0
    for index in range(1, count + 1):
        sector, length, sf, minimum = struct.unpack_from('<4H', data, table + (index - 1) * 8)
        if sf & (8 | 0x2000):
            raise ValueError('NE iterated or 32-bit segments are unsupported')
        # Wine uses minsize when a file-backed segment encodes size zero.
        file_size = (length or minimum or 65536) if sector else 0
        if not sector and length:
            raise ValueError('NE allocation-only segment has a nonzero file length')
        minimum_size = minimum or 65536
        allocation = max(file_size, minimum_size)
        declared_heap = heap_size if index == autodata else 0
        declared_stack = stack_size if index == stack_segment else 0
        allocation += declared_heap + declared_stack
        if allocation > 65536 or total + allocation > MAX_SOURCE:
            raise ValueError('NE segment allocation exceeds the 64 KiB segment or 64 MiB image budget')
        total += allocation
        file_offset = sector << alignment if sector else None
        payload = _range(data, file_offset, file_size, 'segment payload') if sector else b''
        base = index << 16
        executable, writable = not bool(sf & 1), bool(sf & 1) and not bool(sf & 0x80)
        name = f'ne_segment_{index}'
        if payload:
            regions.append(Region(name, base, payload, executable, writable))
        if allocation > file_size:
            # Allocation-only code bytes are not admitted as executable seeds.
            regions.append(Region(name + '.zero_fill', base + file_size,
                                  bytes(allocation - file_size), False, writable))
        record = dict(index=index, logical_base=base, file_offset=file_offset,
                      declared_file_size=length, file_size=file_size,
                      minimum_allocation=minimum_size, allocation_size=allocation,
                      declared_heap_size=declared_heap, declared_stack_size=declared_stack,
                      zero_fill_size=allocation - file_size, flags=sf,
                      executable=executable, writable=writable, runtime_selector=None)
        segments.append(record)
        sections.append(dict(name=name, virtual_address=base, virtual_size=allocation,
                             file_offset=file_offset, file_size=file_size,
                             permissions=('rw-' if writable else 'r-x' if executable else 'r--'),
                             segment_index=index, zero_fill_size=allocation - file_size,
                             runtime_selector=None))
        if file_size:
            mappings.append(dict(file_offset=file_offset, file_size=file_size, virtual_address=base,
                                 segment_index=index))

    first_payload = min((s['file_offset'] for s in segments if s['file_size']), default=len(data))

    def bound(offset):
        candidates = [h + value for value in table_offsets if value > offset]
        candidates += [first_payload, len(data)]
        nonresident = dword(44)
        if nonresident > h + offset:
            candidates.append(nonresident)
        return min(value for value in candidates if value >= h + offset)

    def pascal(offset, end, label):
        if offset >= end:
            raise ValueError(f'NE {label} string exceeds its table bounds')
        length = data[offset]
        if offset + 1 + length > end:
            raise ValueError(f'NE {label} string exceeds its table bounds')
        return data[offset + 1:offset + 1 + length].decode('latin-1'), offset + 1 + length

    def names(offset, end, label):
        rows, cursor = [], offset
        while cursor < end:
            text, cursor = pascal(cursor, end, label)
            if not text:
                return rows, cursor
            if cursor + 2 > end or len(rows) >= MAX_NAMES:
                raise ValueError(f'NE {label} ordinal/count exceeds its table bounds')
            ordinal = struct.unpack_from('<H', data, cursor)[0]
            cursor += 2
            rows.append(dict(name=text, ordinal=ordinal, source=label))
        raise ValueError(f'NE {label} has no terminator within its table bounds')

    name_rows = []
    if word(38):
        offset = relative(word(38), 1, 'resident names')
        rows, end = names(offset, bound(word(38)), 'resident name')
        structural.append((offset, end)); name_rows.extend(rows)
    if word(32):
        offset, length = dword(44), word(32)
        _range(data, offset, length, 'nonresident names')
        rows, end = names(offset, offset + length, 'nonresident name')
        # The first nonresident name is the module description, not an export.
        # Some historical linkers leave a nonzero ordinal in that record.
        if rows:
            rows[0]['module_description'] = True
        structural.append((offset, offset + length)); name_rows.extend(rows)

    modules = []
    module_count = word(30)
    if module_count:
        refs = relative(word(40), module_count * 2, 'module references')
        imports_start = relative(word(42), 1, 'import names')
        imports_end = bound(word(42))
        structural.append((refs, refs + module_count * 2))
        for index in range(module_count):
            at = imports_start + struct.unpack_from('<H', data, refs + index * 2)[0]
            name, _ = pascal(at, imports_end, 'module import')
            if not name:
                raise ValueError('NE imported module name is empty')
            modules.append(name)
        structural.append((imports_start, imports_end))
    else:
        imports_start = relative(word(42), 0, 'import names') if word(42) else 0
        imports_end = bound(word(42)) if word(42) else 0

    def target(segment, offset, *, instruction=False):
        if not 1 <= segment <= count or not 0 <= offset < segments[segment - 1]['allocation_size']:
            raise ValueError('NE target segment/offset is outside declared allocation bounds')
        s = segments[segment - 1]
        if instruction and (not s['executable'] or offset >= s['file_size']):
            raise ValueError('NE entry must name an initialized executable byte')
        return segment << 16 | offset

    entries, ordinal, movable = {}, 1, 0
    if word(6):
        offset, size = relative(word(4), word(6), 'entry table'), word(6)
        end, cursor, terminated = offset + size, offset, False
        structural.append((offset, end))
        while cursor < end:
            bundle_count = data[cursor]; cursor += 1
            if not bundle_count:
                terminated = True; break
            if cursor >= end:
                raise ValueError('NE entry bundle header is truncated')
            segment = data[cursor]; cursor += 1
            if ordinal + bundle_count > MAX_NAMES:
                raise ValueError('NE entry ordinal count exceeds its budget')
            if segment == 0:
                ordinal += bundle_count; continue
            width = 6 if segment == 255 else 3
            if cursor + width * bundle_count > end:
                raise ValueError('NE entry bundle exceeds its declared table')
            for _ in range(bundle_count):
                ef = data[cursor]
                if segment == 255:
                    if data[cursor + 1:cursor + 3] != b'\xcd\x3f':
                        raise ValueError('NE movable entry has an invalid INT 3F marker')
                    seg, off = data[cursor + 3], struct.unpack_from('<H', data, cursor + 4)[0]
                    movable += 1
                else:
                    seg, off = segment, struct.unpack_from('<H', data, cursor + 1)[0]
                address = target(seg, off)
                s = segments[seg - 1]
                entries[ordinal] = dict(ordinal=ordinal, flags=ef, segment_index=seg,
                                        offset=off, address=address, is_code=s['executable'],
                                        code_seed_eligible=s['executable'] and off < s['file_size'])
                cursor += width; ordinal += 1
        if not terminated or any(data[cursor:end]):
            raise ValueError('NE entry table lacks a terminator or has unsupported trailing entries')
        if movable != word(48):
            raise ValueError('NE movable entry count disagrees with its header')
    elif word(48):
        raise ValueError('NE movable entry count has no entry table')

    exports = []
    for row in name_rows:
        if row['ordinal'] and not row.get('module_description') and row['ordinal'] not in entries:
            raise ValueError('NE exported name refers to a missing entry ordinal')
    for ordinal, item in entries.items():
        labels = [r for r in name_rows if r['ordinal'] == ordinal and not r.get('module_description')] or [dict(name=f'ordinal_{ordinal}', source='entry table')]
        exports.extend(dict(item, name=r['name'], source=r['source']) for r in labels)

    resources = []
    # A linker may express an empty resource table as the next table's
    # boundary. In particular Open Watcom uses the resident-name offset.
    if word(36) and word(36) != word(38):
        resource_start = relative(word(36), 2, 'resource table')
        resource_end, cursor = bound(word(36)), resource_start
        shift = struct.unpack_from('<H', data, cursor)[0]; cursor += 2
        if shift > 15:
            raise ValueError('NE resource alignment is unsupported')

        def resource_id(value):
            if value & 0x8000:
                return value & 0x7fff
            text, _ = pascal(resource_start + value, resource_end, 'resource identifier')
            return text

        while True:
            if cursor + 2 > resource_end:
                raise ValueError('NE resource table has no bounded terminator')
            kind = struct.unpack_from('<H', data, cursor)[0]; cursor += 2
            if not kind:
                break
            if cursor + 6 > resource_end:
                raise ValueError('NE resource type record is truncated')
            amount = struct.unpack_from('<H', data, cursor)[0]; cursor += 6
            if cursor + amount * 12 > resource_end or len(resources) + amount > MAX_NAMES:
                raise ValueError('NE resources exceed their table/count budget')
            for _ in range(amount):
                sector, length, rf, identity, reserved1, reserved2 = struct.unpack_from('<6H', data, cursor)
                at, size = sector << shift, length << shift
                _range(data, at, size, 'resource payload')
                resources.append(dict(type=resource_id(kind), id=resource_id(identity), flags=rf,
                                      file_offset=at, file_size=size))
                cursor += 12
        structural.append((resource_start, resource_end))

    fixups, imported, occupied, site_count = [], {}, {}, 0
    spans = list(structural)
    for s in segments:
        if not s['file_size']:
            if s['flags'] & 0x100:
                raise ValueError('NE allocation-only segment cannot contain file fixups')
            continue
        file_end = s['file_offset'] + s['file_size']
        if not s['flags'] & 0x100:
            spans.append((s['file_offset'], file_end)); continue
        _range(data, file_end, 2, 'relocation count')
        amount = struct.unpack_from('<H', data, file_end)[0]
        _range(data, file_end + 2, amount * 8, 'relocation records')
        spans.append((s['file_offset'], file_end + 2 + amount * 8))
        if len(fixups) + amount > MAX_FIXUPS:
            raise ValueError('NE relocation records exceed their budget')
        s['fixup_count'] = amount
        for index in range(amount):
            record_offset = file_end + 2 + index * 8
            source_type, rf, off, t1, t2 = struct.unpack_from('<BBHHH', data, record_offset)
            if source_type not in _WIDTHS or rf & ~7:
                raise ValueError('NE relocation source encoding/flags are unsupported')
            kind, additive, width = rf & 3, bool(rf & 4), _WIDTHS[source_type]
            row = dict(index=len(fixups), record_file_offset=record_offset,
                       raw_record=data[record_offset:record_offset + 8].hex(),
                       source_segment_index=s['index'], source_type=_KINDS[source_type],
                       source_width=width, source_type_code=source_type, flags=rf,
                       additive=additive, raw_target1=t1, raw_target2=t2,
                       applied=False, runtime_selector=None, sources=[])
            if kind == 0:
                if t1 & 0xff == 255:
                    if t2 not in entries:
                        raise ValueError('NE internal movable fixup refers to a missing entry ordinal')
                    seg, target_offset = entries[t2]['segment_index'], entries[t2]['offset']
                    row['target_ordinal'] = t2
                else:
                    seg, target_offset = t1, t2
                if source_type == 2:
                    target(seg, 0)  # A selector-only fixup does not declare an offset.
                    target_offset, logical_target = None, None
                else:
                    logical_target = target(seg, target_offset)
                row.update(target_kind='internal', target_segment_index=seg,
                           target_offset=target_offset, logical_target=logical_target)
            elif kind in (1, 2):
                if not 1 <= t1 <= len(modules):
                    raise ValueError('NE import module index is invalid')
                name, import_ordinal = None, t2 if kind == 1 else None
                if kind == 2:
                    name, _ = pascal(imports_start + t2, imports_end, 'procedure import')
                    if not name:
                        raise ValueError('NE imported procedure name is empty')
                elif not import_ordinal:
                    raise ValueError('NE imported ordinal is zero')
                row.update(target_kind='import_ordinal' if kind == 1 else 'import_name',
                           import_module=modules[t1 - 1], import_name=name, import_ordinal=import_ordinal)
                imported[(modules[t1 - 1], name, import_ordinal)] = dict(module=modules[t1 - 1],
                    name=name, ordinal=import_ordinal, address=None, runtime_selector=None,
                    evidence='symbolic NE import; no external procedure address allocated')
            else:
                row['target_kind'] = 'os_fixup'
            seen = set()
            while True:
                needed = width if additive else max(width, 2)
                if off in seen or off + needed > s['file_size']:
                    raise ValueError('NE relocation source chain cycles or exceeds initialized segment bounds')
                seen.add(off); site_count += 1
                if site_count > MAX_SITES:
                    raise ValueError('NE expanded relocation sources exceed their budget')
                address = s['logical_base'] + off
                for byte in range(address, address + width):
                    if byte in occupied:
                        raise ValueError('NE relocation sources overlap')
                    occupied[byte] = len(fixups)
                at = s['file_offset'] + off
                row['sources'].append(dict(offset=off, address=address, file_offset=at,
                    original_bytes=data[at:at + width].hex()))
                if additive:
                    break
                off = struct.unpack_from('<H', data, at)[0]
                if off == 0xffff:
                    break
            fixups.append(row)
    spans = sorted((a, b) for a, b in spans if b > a)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError('NE structural tables, segment payloads or fixup records overlap')

    selected = target(word(22), word(20), instruction=True) if word(22) else None
    if word(20) and selected is None:
        raise ValueError('NE entry offset has no entry segment')
    if entry is not None:
        entry = parse_address(entry)
        selected = target(entry >> 16, entry & 0xffff, instruction=True)
    if selected is None and not (module or flags & 0x8000):
        raise ValueError('NE executable has no entry; use module mode for an entryless module')
    seeds = [Seed(selected, 'entry', 'entry')] if selected is not None else []
    seen_seeds = {seed.address for seed in seeds}
    for row in exports:
        if row['code_seed_eligible'] and row['address'] not in seen_seeds:
            seeds.append(Seed(row['address'], row['name'], 'NE entry/export table'))
            seen_seeds.add(row['address'])
    ne = dict(header_offset=h, target_os=2, module_flags=flags, is_dll=bool(flags & 0x8000),
              arch='x86', bits=16, endian='little', load_model='NE logical segment indices; no runtime selectors',
              segment_alignment=alignment, automatic_data_segment_index=autodata,
              initial_stack_segment_index=stack_segment, initial_stack_offset=word(24),
              heap_size=heap_size, stack_size=stack_size, entrypoint=selected,
              logical_entry=logical_location(selected) if selected is not None else None,
              segments=segments, entries=list(entries.values()), name_records=name_rows, exports=exports,
              imports=list(imported.values()), libraries=modules, resources=resources,
              fixups=fixups, fixup_count=len(fixups), fixup_source_count=site_count,
              sections=sections, file_mappings=mappings,
              warnings=['Original NE bytes are unrelocated; operands and fixup chains are retained.',
                        'Logical segment indices are not DOS paragraphs or live Windows selectors.',
                        'OS floating-point fixups and imported procedure addresses remain symbolic.'])
    ne['header_fields'] = dict(linker_version=raw[2], linker_revision=raw[3], checksum=dword(8),
        **{name: word(offset) for name, offset in (
            ('entry_table_offset', 4), ('entry_table_size', 6), ('flags', 12),
            ('automatic_data_segment', 14), ('heap_size', 16), ('stack_size', 18),
            ('entry_ip', 20), ('entry_segment', 22), ('stack_sp', 24), ('stack_segment', 26),
            ('segment_count', 28), ('module_reference_count', 30), ('nonresident_names_size', 32),
            ('segment_table_offset', 34), ('resource_table_offset', 36), ('resident_names_offset', 38),
            ('module_reference_table_offset', 40), ('import_names_offset', 42),
            ('movable_entry_count', 48), ('alignment_shift', 50), ('resource_segment_count', 52),
            ('gangload_sector', 56), ('gangload_length', 58), ('minimum_swap_size', 60),
            ('expected_windows_version', 62))}, nonresident_names_offset=dword(44),
        target_os=raw[54], other_flags=raw[55], raw_bytes=raw.hex())
    metadata = dict(selected_image='ne', source_sha256=hashlib.sha256(data).hexdigest(), entrypoint_present=selected is not None,
                    module=selected is None, source_size=len(data), file_mappings=mappings,
                    seed_count=len(seeds), ne=ne,
                    relocations='symbolic NE fixups retained; original operands and source bytes unchanged')
    return Image('NE', 'x86', 16, selected or 0, regions, seeds, metadata, source_bytes=data)


def inspect_ne(data: bytes) -> dict:
    return load_ne(data, module=True).metadata['ne']
