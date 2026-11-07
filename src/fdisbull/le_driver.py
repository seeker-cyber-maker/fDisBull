"""Bounded, source-bound LE module inspection and object-local code views.

Unlike the flat executable loader in :mod:`fdisbull.le`, this reader accepts
library/driver flags, absent startup entries and mixed 16/32-bit objects. It
never applies a relocation, chooses runtime selectors, creates an Image/CFG,
or executes a loader. Unsupported fixup layouts block code views of the affected
object; valid selector, far-pointer and imported fixups remain symbolic.

The common object/fixup encodings are documented in IBM's Linear Executable
specification, sections 2.4 and 2.12 (archived primary documentation):
https://komh.github.io/os2books/os2tk45/lxref.htm
LE's four-byte page map and last-physical-page length follow the existing LE
reader; they are deliberately not LX's eight-byte map/page-offset shift.
LE physical page counts and logical object-map extents are distinct. The
Windows loader's LE interpretation is independently documented by original
reverse-engineering research (appendix, not native execution qualification):
https://www.geoffchappell.com/notes/windows/archive/vxdldr.htm
Microsoft's Windows 3.0 DDK, section 17.1.4, documents INT 20h plus a DWORD:
https://www.pcjs.org/documents/books/mspl13/win/w3ddkvxd/
"""
from __future__ import annotations

from bisect import bisect_left
import hashlib
import struct

from .le import HEADER_SIZE, MAX_IMAGE_SIZE, MAX_OBJECTS, MAX_PAGES, PAGE_SIZE, _HEADER_FIELDS

MAX_FIXUPS = 100000
MAX_FIXUP_SOURCES = 200000
MAX_INSTRUCTIONS = 4096
_SOURCE_TYPES = {
    0: ('byte', 1), 2: ('selector16', 2), 3: ('pointer16:16', 4),
    5: ('offset16', 2), 6: ('pointer16:32', 6),
    7: ('offset32', 4), 8: ('relative32', 4),
}
_PAGE_TYPES = {0: 'enumerated', 1: 'iterated', 2: 'invalid', 3: 'zero_fill', 4: 'range'}


def _range(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f'LE driver {label} exceeds source bounds')
    return data[offset:offset + size]


def _integer(value: int, lower: int, upper: int, label: str) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{label} must be an integer in {lower}..{upper}')


def _page(report: dict, obj: dict, offset: int) -> dict | None:
    local = offset // PAGE_SIZE
    if local >= obj['page_count']:
        return None
    logical = obj['first_page'] + local
    if not 1 <= logical <= len(report['pages']):
        return None
    page = report['pages'][logical - 1]
    return page if page['object'] == obj['index'] else None


def _fragments(report: dict, obj: dict, offset: int, size: int) -> list[dict]:
    """Return only actual source bytes; holes and zero fill have no fragments."""
    result = []
    end = offset + size
    while offset < end:
        page = _page(report, obj, offset)
        within = offset % PAGE_SIZE
        take = min(end - offset, PAGE_SIZE - within)
        if page is not None and page['file_offset'] is not None and within < page['file_size']:
            backed = min(take, page['file_size'] - within)
            result.append(dict(object_offset=offset, file_offset=page['file_offset'] + within, size=backed))
        offset += take
    return result


def _window(data: bytes, report: dict, obj: dict, offset: int, limit: int) -> tuple[bytes, list[dict], str | None]:
    """Read a contiguous *object* interval without filling missing file bytes."""
    end = min(obj['virtual_size'], offset + limit)
    chunks, fragments = [], []
    cursor = offset
    while cursor < end:
        page = _page(report, obj, cursor)
        if page is None:
            return b''.join(chunks), fragments, 'non_file_backed'
        if page['encoding'] not in ('enumerated', 'zero_fill'):
            return b''.join(chunks), fragments, 'unsupported_page_encoding'
        within = cursor % PAGE_SIZE
        if page['file_offset'] is None or within >= page['file_size']:
            return b''.join(chunks), fragments, 'non_file_backed'
        take = min(end - cursor, page['file_size'] - within, PAGE_SIZE - within)
        source = page['file_offset'] + within
        chunks.append(data[source:source + take])
        fragments.append(dict(object_offset=cursor, file_offset=source, size=take))
        cursor += take
    reason = 'object_end' if end == obj['virtual_size'] else None
    return b''.join(chunks), fragments, reason


def _annotate_dos_devices(data: bytes, report: dict) -> None:
    """Recognize file-backed device headers without assigning DOS segments.

    LE module entry fields sometimes identify a device header rather than an
    instruction. Reuse the conservative SYS structural probe on at most one
    common-segment window, preserving the LE page map as the source authority.
    Unapplied fixups in header fields prevent this annotation.
    """
    from .dos_driver import probe_sys

    relocated = {}
    for fixup in report['fixups']:
        for source in fixup['sources']:
            relocated.setdefault(source['object'], []).append(
                (source['offset'], source['offset'] + fixup['source_width']))
    for obj in report['objects']:
        if (obj['bits'] != 16 or not obj['mapping_complete']
                or not obj['fixups_complete'] or not obj['page_encodings_supported']):
            continue
        prefix, _, _ = _window(data, report, obj, 0, 0x10000)
        candidate = probe_sys(prefix)
        if candidate is None or candidate['container'] != 'flat':
            continue
        sites = sorted(relocated.get(obj['index'], []))
        offsets = [start for start, _ in sites]
        headers = candidate['headers']
        affected = False
        for header in headers:
            start, end = header['module_offset'], header['module_offset'] + header['size']
            at = bisect_left(offsets, start - 5)
            while at < len(sites) and sites[at][0] < end:
                if sites[at][1] > start:
                    affected = True
                    break
                at += 1
            if affected:
                break
        if affected:
            report['diagnostics'].append(dict(code='dos_device_header_has_fixups', object=obj['index'],
                message='encoded device-header fields overlap unapplied fixups; no driver roots are inferred'))
            continue
        annotation = dict(address_space='le.object', object=obj['index'], headers=[], entry_roots=[],
            header_count=len(headers), reconstructed_prefix_size=len(prefix),
            recognition=candidate['recognition'],
            validation_scope='unrelocated device-header fields and file-backed object-relative roots; not runtime code or ABI validation',
            runtime_selectors='unknown', runtime_execution=False)
        for header in headers:
            start = header['module_offset']
            fragments = _fragments(report, obj, start, header['size'])
            contiguous = all(a['file_offset'] + a['size'] == b['file_offset']
                             for a, b in zip(fragments, fragments[1:]))
            item = {key: value for key, value in header.items() if key not in ('module_offset', 'file_offset')}
            item.update(object=obj['index'], offset=start, address_space='le.object',
                        file_fragments=fragments,
                        file_offset=fragments[0]['file_offset'] if contiguous else None)
            annotation['headers'].append(item)
            for role in ('strategy', 'interrupt'):
                offset = header[role + '_offset']
                fragments = _fragments(report, obj, offset, 1)
                annotation['entry_roots'].append(dict(object=obj['index'], offset=offset,
                    address_space='le.object', role=role, header_index=header['index'],
                    source='validated DOS device-header offset field',
                    file_offset=fragments[0]['file_offset'], file_fragments=fragments,
                    code_view_available=obj['executable'], initial_registers={},
                    caller_state='registers, stack and request packet are unobserved'))
        obj['dos_device'] = annotation


def _parse_fixups(data: bytes, report: dict, relative) -> None:
    header, objects, pages = report['header'], report['objects'], report['pages']
    size = header['fixup_size']
    if not size:
        if any(header[name] for name in ('fixup_page_table_offset', 'fixup_record_table_offset',
                                        'import_modules_offset', 'import_module_count', 'import_procedures_offset')):
            raise ValueError('LE driver fixup tables require a declared fixup section')
        return
    first = relative(header['fixup_page_table_offset'], size, 'fixup section')
    end = first + size
    physical_count = header['num_pages']
    table_size = (physical_count + 1) * 4
    if table_size > size:
        raise ValueError('LE driver fixup page table exceeds its section')
    records = relative(header['fixup_record_table_offset'], 0, 'fixup records')
    if not first + table_size <= records <= end:
        raise ValueError('LE driver fixup record table is outside its section')
    offsets = struct.unpack_from('<' + 'I' * (physical_count + 1), data, first)
    if offsets[0] != 0 or any(a > b for a, b in zip(offsets, offsets[1:])):
        raise ValueError('LE driver fixup page offsets must start at zero and be monotonic')
    record_end = records + offsets[-1]
    if record_end > end:
        raise ValueError('LE driver fixup records exceed their section')
    report['fixup_section'] = dict(file_offset=first, size=size, record_file_offset=records,
                                   record_size=offsets[-1], page_offsets=list(offsets),
                                   index_domain='physical_page')
    module_count = header['import_module_count']
    if module_count > MAX_OBJECTS:
        raise ValueError('LE driver import module count exceeds the budget')
    procedure_start = None
    if header['import_procedures_offset']:
        procedure_start = relative(header['import_procedures_offset'], 0, 'import procedures')
        if not record_end <= procedure_start <= end:
            raise ValueError('LE driver import procedures overlap records or exceed the fixup section')

    def name_at(position: int, boundary: int, label: str) -> tuple[str, int]:
        if not record_end <= position < boundary:
            raise ValueError(f'LE driver {label} is outside its table')
        length = data[position]
        if position + 1 + length > boundary:
            raise ValueError(f'LE driver {label} exceeds its table')
        return data[position + 1:position + 1 + length].decode('latin1'), position + 1 + length

    if module_count:
        module_start = relative(header['import_modules_offset'], 0, 'import modules')
        module_end = procedure_start if procedure_start is not None else end
        position = module_start
        for number in range(1, module_count + 1):
            name, after = name_at(position, module_end, 'import module name')
            report['imports'].append(dict(index=number, name=name, file_offset=position))
            position = after
    elif header['import_modules_offset']:
        position = relative(header['import_modules_offset'], 0, 'empty import modules')
        if not record_end <= position <= end:
            raise ValueError('LE driver empty import table is outside its section')

    writes = {}
    source_count = 0
    interpreted_physical_pages = set()
    for page in pages:
        number = page['index']
        physical = page['physical_page']
        if page['object'] is None or page['encoding'] == 'zero_fill':
            page['fixup_record_range'] = None
            continue
        obj = objects[page['object'] - 1]
        if page['encoding'] != 'enumerated':
            page['fixup_record_range'] = None
            page['fixups_complete'] = obj['fixups_complete'] = False
            continue
        # LE's fenceposts refer to physical file pages, not to the logical
        # object-map slot. Zero-fill pages have no fencepost, and two logical
        # aliases can share the same physical records with different origins.
        interpreted_physical_pages.add(physical)
        position = records + offsets[physical - 1]
        boundary = records + offsets[physical]
        page['fixup_record_range'] = dict(file_offset=position, size=boundary - position)
        while position < boundary:
            if len(report['fixups']) >= MAX_FIXUPS:
                raise ValueError('LE driver fixup record budget exceeded')
            record_start = position

            def read(length: int) -> bytes:
                nonlocal position
                if position + length > boundary:
                    raise ValueError('LE driver fixup record crosses its page-table boundary')
                value = data[position:position + length]
                position += length
                return value

            source_flags, target_flags = read(2)
            kind = source_flags & 0xf
            target_kind = target_flags & 3
            unsupported = None
            if kind not in _SOURCE_TYPES or source_flags & 0xc0:
                unsupported = 'unsupported source fixup encoding'
            elif source_flags & 0x10 and kind not in (2, 3, 6):
                unsupported = 'alias flag on an unsupported source type'
            elif target_flags & 8:
                unsupported = 'internal-chain fixups are not expanded'
            elif target_kind == 0 and target_flags & (4 | 0x20 | 0x80):
                unsupported = 'unsupported internal fixup target flags'
            elif target_kind in (2, 3) and target_flags & 0x80:
                unsupported = 'ordinal-width flag on a non-ordinal target'
            if unsupported is not None:
                # Record the bounded opaque remainder, never guess its next
                # record boundary or assume its unknown sites are harmless.
                report['fixups'].append(dict(index=len(report['fixups']), page=number, physical_page=physical,
                    source_object=obj['index'], source_flags=source_flags, target_flags=target_flags,
                    source_type='opaque', source_width=None, sources=[], target=None, applied=False,
                    record_file_offset=record_start, record_size=boundary - record_start,
                    record_sha256=hashlib.sha256(data[record_start:boundary]).hexdigest(),
                    unsupported_reason=unsupported))
                page['fixups_complete'] = obj['fixups_complete'] = False
                report['diagnostics'].append(dict(code='unsupported_fixups', object=obj['index'],
                                                  page=number, message=unsupported))
                break
            source_type, width = _SOURCE_TYPES[kind]
            is_list = bool(source_flags & 0x20)
            if is_list:
                count = read(1)[0]
                if not count:
                    raise ValueError('LE driver source-list fixup has no sources')
                source_offsets = []
            else:
                count = 1
                source_offsets = [int.from_bytes(read(2), 'little', signed=True)]
            if source_count + count > MAX_FIXUP_SOURCES:
                raise ValueError('LE driver fixup source budget exceeded')
            ordinal_width = 2 if target_flags & 0x40 else 1
            target_ordinal = int.from_bytes(read(ordinal_width), 'little')
            target = dict(kind=('internal', 'import_ordinal', 'import_name', 'internal_entry')[target_kind],
                          selector=None)
            if target_kind == 0:
                if not 1 <= target_ordinal <= len(objects):
                    raise ValueError('LE driver fixup target object is out of bounds')
                target_offset = None if kind == 2 else int.from_bytes(read(4 if target_flags & 0x10 else 2), 'little')
                within = None if target_offset is None else target_offset <= objects[target_ordinal - 1]['virtual_size']
                target.update(object=target_ordinal, offset=target_offset, offset_within_object=within)
                if within is False:
                    # An encoded target expression can be outside the object's
                    # storage (e.g. FFFFFFFFh). Preserve it, without assuming
                    # signed arithmetic, wrapping, a valid pointer, or an edge.
                    report['diagnostics'].append(dict(code='fixup_target_outside_object',
                        record_file_offset=record_start, target_object=target_ordinal,
                        target_offset=target_offset,
                        message='target expression is outside the declared extent; no target address is resolved'))
            elif target_kind in (1, 2):
                if not 1 <= target_ordinal <= module_count:
                    raise ValueError('LE driver fixup import module is out of bounds')
                target.update(module=target_ordinal, module_name=report['imports'][target_ordinal - 1]['name'])
                if target_kind == 1:
                    ordinal_size = 1 if target_flags & 0x80 else 4 if target_flags & 0x10 else 2
                    target['ordinal'] = int.from_bytes(read(ordinal_size), 'little')
                else:
                    name_offset = int.from_bytes(read(4 if target_flags & 0x10 else 2), 'little')
                    if procedure_start is None:
                        raise ValueError('LE driver imported name requires a procedure table')
                    name, _ = name_at(procedure_start + name_offset, end, 'import procedure name')
                    target.update(name_offset=name_offset, name=name)
            else:
                target.update(entry_ordinal=target_ordinal, resolution='entry_table_not_interpreted')
            addend = int.from_bytes(read(4 if target_flags & 0x20 else 2), 'little') if target_flags & 4 else None
            if is_list:
                source_offsets = [int.from_bytes(read(2), 'little', signed=True) for _ in range(count)]
            fixup = dict(index=len(report['fixups']), page=number, physical_page=physical,
                         source_object=obj['index'],
                         source_type=source_type, source_type_code=kind, source_width=width,
                         source_flags=source_flags, target_flags=target_flags,
                         fixup_to_alias=bool(source_flags & 0x10), source_list=is_list,
                         target=target, addend=addend, applied=False, sources=[],
                         record_file_offset=record_start, record_size=position - record_start)
            signature = (kind, bool(source_flags & 0x10), tuple(sorted(target.items())), addend)
            for relative_offset in source_offsets:
                if not -(width - 1) <= relative_offset < PAGE_SIZE:
                    raise ValueError('LE driver fixup source must intersect its logical page')
                offset = page['object_offset'] + relative_offset
                if offset < 0 or offset + width > obj['virtual_size']:
                    raise ValueError(f"LE driver fixup source exceeds object {obj['index']} "
                                     f"(page {number}, offset {offset}, width {width}, "
                                     f"virtual size {obj['virtual_size']}, record {record_start})")
                duplicate = None
                for neighbor in range(offset - 5, offset + width):
                    previous = writes.get((obj['index'], neighbor))
                    if previous is None or neighbor + previous[0] <= offset:
                        continue
                    if neighbor != offset or previous[0] != width or previous[1] != signature:
                        raise ValueError('LE driver overlapping fixups disagree')
                    duplicate = dict(fixup=previous[2], source=previous[3])
                source = dict(object=obj['index'], offset=offset, page_offset=relative_offset,
                              width=width, file_fragments=_fragments(report, obj, offset, width),
                              duplicate_of=duplicate)
                source['file_backed_size'] = sum(f['size'] for f in source['file_fragments'])
                if duplicate is None:
                    writes[(obj['index'], offset)] = (width, signature, fixup['index'], len(fixup['sources']))
                fixup['sources'].append(source)
            report['fixups'].append(fixup)
            source_count += count
    report['fixup_source_count'] = source_count
    report['unassigned_fixup_pages'] = [dict(physical_page=p, file_offset=records + offsets[p - 1],
                                             size=offsets[p] - offsets[p - 1])
        for p in range(1, physical_count + 1)
        if p not in interpreted_physical_pages and offsets[p] != offsets[p - 1]]
    if report['unassigned_fixup_pages']:
        report['diagnostics'].append(dict(code='unassigned_physical_fixups',
            message='physical fixup records without an interpreted object mapping remain unparsed'))


def inspect_le_driver(data: bytes) -> dict:
    """Inspect immutable LE bytes without applying fixups or guessing an ABI.

    Inputs are bounded to 64 MiB, 4096 objects and 16384 logical pages. Known
    corrupt/truncated structures raise ValueError. Unsupported page encodings
    and fixup layouts are retained as diagnostics, with unavailable code views.
    Entry tables, resources, debug data and checksums are not interpreted.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_IMAGE_SIZE:
        raise ValueError('LE driver source must contain 1..64 MiB immutable bytes')
    if data.startswith(b'LE'):
        header_offset = 0
    else:
        from .image_views import secondary_header
        secondary = secondary_header(data)
        if secondary is None or secondary['format'] != 'LE':
            raise ValueError('LE driver requires LE or an independent MZ secondary LE header')
        header_offset = secondary['header_offset']
    raw = _range(data, header_offset, HEADER_SIZE, 'header')
    if raw[2:4] != b'\0\0' or struct.unpack_from('<I', raw, 4)[0] != 0:
        raise ValueError('LE driver requires little-endian byte/word order and format level zero')
    cpu, os_type = struct.unpack_from('<HH', raw, 8)
    if cpu not in (1, 2, 3):
        raise ValueError('LE driver code view requires an x86 286/386/486 CPU type')
    fields = dict(zip(_HEADER_FIELDS, struct.unpack_from('<41I', raw, 12)))
    count, page_count = fields['object_count'], fields['num_pages']
    if not 1 <= count <= MAX_OBJECTS or not 0 <= page_count <= MAX_PAGES:
        raise ValueError('LE driver object/page count exceeds the supported budget')
    if fields['page_size'] != PAGE_SIZE:
        raise ValueError('LE driver profile requires 4096-byte pages')
    if not 0 <= fields['last_page_size'] <= PAGE_SIZE:
        raise ValueError('LE driver last-page size exceeds 4096')

    def relative(offset: int, size: int, label: str) -> int:
        if offset < HEADER_SIZE:
            raise ValueError(f'LE driver {label} overlaps the fixed header')
        absolute = header_offset + offset
        _range(data, absolute, size, label)
        return absolute

    object_table = relative(fields['object_table_offset'], count * 24, 'object table')
    structural = [(header_offset, header_offset + HEADER_SIZE), (object_table, object_table + count * 24)]
    if fields['fixup_size']:
        fixups = relative(fields['fixup_page_table_offset'], fields['fixup_size'], 'fixup section')
        structural.append((fixups, fixups + fields['fixup_size']))
    report = dict(schema='fdisbull-le-driver-inspect-1', format='LE', arch='x86', bits=None,
                  abi='unknown', header_offset=header_offset, source_size=len(data),
                  source_sha256=hashlib.sha256(data).hexdigest(),
                  header=dict(fields, cpu_type=cpu, os_type=os_type), entrypoint=None,
                  objects=[], pages=[], fixups=[], imports=[], diagnostics=[],
                  fixup_source_count=0, fixup_section=None, unassigned_fixup_pages=[])
    objects, owners = report['objects'], {}
    total_size = 0
    logical_count = 0
    for index in range(count):
        size, base, flags, first_page, pages, reserved = struct.unpack_from('<6I', data, object_table + index * 24)
        total_size += size
        if total_size > MAX_IMAGE_SIZE or base + size > 1 << 32:
            raise ValueError('LE driver object virtual extent exceeds the budget/address space')
        if pages > (size + PAGE_SIZE - 1) // PAGE_SIZE:
            raise ValueError('LE driver page count exceeds its object virtual size')
        if pages and first_page:
            logical_count = max(logical_count, first_page + pages - 1)
        objects.append(dict(index=index + 1, virtual_size=size, relocation_base=base, flags=flags,
                            bits=32 if flags & 0x2000 else 16, executable=bool(flags & 4),
                            readable=bool(flags & 1), writable=bool(flags & 2),
                            discardable=bool(flags & 0x10), alias_required=bool(flags & 0x1000),
                            first_page=first_page, page_count=pages, reserved=reserved,
                            file_backed_size=0, mapping_complete=True, fixups_complete=True,
                            page_encodings_supported=True,
                            table_file_offset=object_table + index * 24))
    bitness = {obj['bits'] for obj in objects}
    report['bits'] = next(iter(bitness)) if len(bitness) == 1 else None
    if cpu == 1 and 32 in bitness:
        raise ValueError('LE driver 286 CPU type conflicts with a 32-bit object')
    available_count = 0
    page_table = None
    if logical_count:
        page_table = relative(fields['page_map_offset'], 0, 'page map')
        if any(start <= page_table < end for start, end in structural):
            raise ValueError('LE driver page map begins inside another structural table')
        # Its entry count comes from the objects. Bound those declarations by
        # actual source/table extents, not by the number of physical file pages.
        limits = [len(data)]
        for field in ('object_table_offset', 'resource_table_offset', 'resident_names_offset',
                      'entry_table_offset', 'module_directives_offset', 'fixup_page_table_offset',
                      'fixup_record_table_offset', 'import_modules_offset', 'import_procedures_offset',
                      'page_checksum_offset'):
            absolute = header_offset + fields[field]
            if fields[field] and absolute >= page_table:
                limits.append(absolute)
        if fields['loader_size'] and object_table + fields['loader_size'] >= page_table:
            limits.append(object_table + fields['loader_size'])
        if fields['data_pages_offset'] >= page_table:
            limits.append(fields['data_pages_offset'])
        available_count = min(logical_count, MAX_PAGES, max(0, (min(limits) - page_table) // 4))
        _range(data, page_table, available_count * 4, 'logical page map')
        structural.append((page_table, page_table + available_count * 4))
    structural.sort()
    if any(a[1] > b[0] for a, b in zip(structural, structural[1:])):
        raise ValueError('LE driver structural tables overlap')
    for obj in objects:
        first_page, pages = obj['first_page'], obj['page_count']
        complete = not pages or (first_page >= 1 and first_page + pages - 1 <= available_count)
        obj['mapping_complete'] = obj['fixups_complete'] = complete
        if not complete:
            report['diagnostics'].append(dict(code='object_page_range_outside_available_table',
                object=obj['index'], declared_first_page=first_page, declared_page_count=pages,
                available_logical_entries=available_count,
                message='object page range exceeds bounded table bytes; object code view is unavailable'))
        for local in range(pages):
            logical = first_page + local
            if first_page < 1 or not 1 <= logical <= available_count:
                continue
            if logical in owners:
                raise ValueError('LE driver logical page belongs to multiple objects')
            owners[logical] = (obj['index'] - 1, local)
    raw_pages = [_range(data, page_table + i * 4, 4, 'page map entry') for i in range(available_count)]
    if page_count and fields['last_page_size'] == 0:
        raise ValueError('LE driver enumerated last page requires an explicit nonzero length')
    data_start = fields['data_pages_offset']
    if page_count:
        physical_size = (page_count - 1) * PAGE_SIZE + fields['last_page_size']
        _range(data, data_start, physical_size, 'physical page data')
        if any(data_start < end and data_start + physical_size > start for start, end in structural):
            raise ValueError('LE driver physical pages overlap structural tables')
    for index, raw_page in enumerate(raw_pages):
        assignment = owners.get(index + 1)
        owner, local = assignment if assignment is not None else (None, None)
        obj = objects[owner] if owner is not None else None
        physical, flags = int.from_bytes(raw_page[:3], 'big'), raw_page[3]
        offset, file_offset, file_size = local * PAGE_SIZE if local is not None else None, None, 0
        capacity = min(PAGE_SIZE, obj['virtual_size'] - offset) if obj is not None else PAGE_SIZE
        if flags == 0:
            if not 1 <= physical <= page_count:
                raise ValueError('LE driver physical page index is out of bounds')
            physical_size = fields['last_page_size'] if physical == page_count else PAGE_SIZE
            file_offset = data_start + (physical - 1) * PAGE_SIZE
            _range(data, file_offset, physical_size, 'enumerated page')
            if any(file_offset < end and file_offset + physical_size > start for start, end in structural):
                raise ValueError('LE driver enumerated page overlaps structural tables')
            file_size = min(capacity, physical_size)
            if obj is not None:
                obj['file_backed_size'] += file_size
        elif flags == 3:
            if physical:
                raise ValueError('LE driver zero-fill page has a physical page index')
        else:
            report['diagnostics'].append(dict(code='unsupported_page_encoding', page=index + 1,
                                              object=obj['index'] if obj is not None else None, flags=flags,
                                              message='page bytes require an unsupported encoding'))
            if obj is not None:
                obj['page_encodings_supported'] = False
        report['pages'].append(dict(index=index + 1, object=obj['index'] if obj is not None else None, object_offset=offset,
                                    physical_page=physical, flags=flags,
                                    encoding=_PAGE_TYPES.get(flags, 'unknown'), file_offset=file_offset,
                                    file_size=file_size, mapped_size=capacity, fixups_complete=True))
    _parse_fixups(data, report, relative)
    _annotate_dos_devices(data, report)
    start_obj = fields['start_obj']
    if not 0 <= start_obj <= count:
        raise ValueError('LE driver entry object is out of bounds')
    if start_obj:
        obj = objects[start_obj - 1]
        entry_offset = fields['eip']
        if entry_offset >= obj['virtual_size']:
            raise ValueError('LE driver entry offset exceeds its object')
        file_backed = bool(_fragments(report, obj, entry_offset, 1))
        report['entrypoint'] = dict(object=start_obj, offset=entry_offset, bits=obj['bits'],
                                   file_backed=file_backed, executable=obj['executable'],
                                   code_view_available=file_backed and obj['executable'] and obj['fixups_complete']
                                   and obj['mapping_complete'] and entry_offset < 1 << obj['bits'])
        for header in obj.get('dos_device', {}).get('headers', []):
            if header['offset'] <= entry_offset < header['offset'] + header['size']:
                report['entrypoint'].update(classification='dos_device_header', code_view_available=False,
                    code_view_unavailable_reason='declared LE entry points into device-header data',
                    header_index=header['index'])
                report['diagnostics'].append(dict(code='declared_entry_is_device_header', object=start_obj,
                    offset=entry_offset, message='declared LE entry is retained as data; see object DOS Strategy/Interrupt roots'))
                break
    elif fields['eip']:
        report['diagnostics'].append(dict(code='entry_offset_without_object',
                                          message='start_obj is zero; no startup entry is invented'))
    report.update(object_count=count, page_count=len(report['pages']), logical_page_count=logical_count,
                  physical_page_count=page_count, fixup_count=len(report['fixups']),
                  unique_fixup_record_count=len({f['record_file_offset'] for f in report['fixups']}),
                  mapped_size=total_size, file_backed_size=sum(o['file_backed_size'] for o in objects),
                  coverage=dict(fixups_complete=all(o['fixups_complete'] for o in objects)
                                and not report['unassigned_fixup_pages'],
                                object_mappings_complete=all(o['mapping_complete'] for o in objects),
                                checksum_validation='not_performed',
                                ancillary_tables='not_interpreted', runtime_selectors='unknown',
                                fixups_applied=False, runtime_execution=False),
                  load_model='source bytes in separate LE object coordinates; relocations remain symbolic')
    return report


def disassemble_le_driver(data: bytes, object_number: int, offset: int = 0,
                          max_instructions: int = 32, abi: str = 'unknown') -> dict:
    """Return a bounded sequential code view, never a CFG or runtime image.

    Calls/conditional branches may have an explicitly assumed continuation;
    unconditional transfers, returns and ABI boundaries stop the view. Explicit
    windows-vxd interprets INT20+DWORD only in a 32-bit object, then stops at the
    service boundary rather than assuming a particular service returns. With an
    unknown ABI INT20 stays ambiguous and its following bytes are not decoded.
    """
    _integer(max_instructions, 1, MAX_INSTRUCTIONS, 'max_instructions')
    if abi not in ('unknown', 'windows-vxd'):
        raise ValueError('abi must be unknown or windows-vxd')
    report = inspect_le_driver(data)
    _integer(object_number, 1, len(report['objects']), 'object_number')
    obj = report['objects'][object_number - 1]
    _integer(offset, 0, obj['virtual_size'], 'offset')
    result = dict(schema='fdisbull-le-driver-disassembly-1', format='LE', arch='x86',
                  source_sha256=report['source_sha256'], source_size=len(data),
                  object=object_number, offset=offset, bits=obj['bits'], abi=abi,
                  address_space='le.object', max_instructions=max_instructions, instructions=[],
                  stop_reason=None, next_offset=offset, budget_exhausted=False,
                  diagnostics=report['diagnostics'], runtime_selectors='unknown',
                  fixups_applied=False, traversal='bounded sequential view; no CFG')
    headers = obj.get('dos_device', {}).get('headers', [])
    if headers:
        result['dos_device'] = obj['dos_device']
    if not obj['executable']:
        result['stop_reason'] = 'non_executable_object'
        return result
    if not obj['mapping_complete']:
        result['stop_reason'] = 'unsupported_object_mapping'
        return result
    if not obj['page_encodings_supported']:
        result['stop_reason'] = 'unsupported_page_encoding'
        return result
    if not obj['fixups_complete']:
        result['stop_reason'] = 'unsupported_fixups'
        return result
    if offset >= 1 << obj['bits']:
        result['stop_reason'] = 'object_offset_exceeds_code_width'
        return result
    sites = sorted((s['offset'], f['index'], i) for f in report['fixups']
                   for i, s in enumerate(f['sources']) if s['object'] == object_number)
    site_offsets = [s[0] for s in sites]
    from .decoder import decode
    import iced_x86 as ix
    cursor = offset
    for _ in range(max_instructions):
        if any(h['offset'] <= cursor < h['offset'] + h['size'] for h in headers):
            result['stop_reason'] = 'dos_device_header'
            break
        if cursor >= obj['virtual_size']:
            result['stop_reason'] = 'object_end'
            break
        if cursor >= 1 << obj['bits']:
            result['stop_reason'] = 'object_offset_exceeds_code_width'
            break
        raw, _, boundary_reason = _window(data, report, obj, cursor, min(15, (1 << obj['bits']) - cursor))
        if not raw:
            result['stop_reason'] = boundary_reason or 'non_file_backed'
            break
        facts = decode(raw, cursor, 'x86', obj['bits'])
        if facts is None:
            result['stop_reason'] = boundary_reason or 'invalid_instruction'
            break
        if any(cursor < h['offset'] + h['size'] and cursor + facts['size'] > h['offset'] for h in headers):
            result['stop_reason'] = 'instruction_overlaps_device_header'
            break
        native = ix.Decoder(obj['bits'], raw, ip=cursor)
        instruction = native.decode()
        constants = native.get_constant_offsets(instruction)
        operand_bytes = set()
        for begin, size in ((constants.displacement_offset, constants.displacement_size),
                            (constants.immediate_offset, constants.immediate_size),
                            (constants.immediate_offset2, constants.immediate_size2)):
            operand_bytes.update(range(begin, begin + size))
        int20 = instruction.mnemonic == ix.Mnemonic.INT and instruction.immediate8 == 0x20
        vxd = int20 and abi == 'windows-vxd' and obj['bits'] == 32 and facts['bytes'] == 'cd20'
        if vxd:
            raw, _, boundary_reason = _window(data, report, obj, cursor, 6)
            if len(raw) < 6:
                result['stop_reason'] = 'truncated_vxd_service'
                break
            facts.update(size=6, bytes=raw.hex(), mnemonic='vxd_service', flow='service')
            operand_bytes = {2, 3, 4, 5}
        elif int20:
            # The interrupt-number byte is semantic structure here, not a
            # safely relocatable numeric operand used to select this ABI.
            operand_bytes = set()
        attached = []
        index = bisect_left(site_offsets, cursor - 5)
        blocked = False
        while index < len(sites) and sites[index][0] < cursor + facts['size']:
            source_offset, fixup_index, source_index = sites[index]
            fixup = report['fixups'][fixup_index]
            source = fixup['sources'][source_index]
            index += 1
            end = source_offset + fixup['source_width']
            if end <= cursor:
                continue
            overlap = set(range(max(0, source_offset - cursor), min(facts['size'], end - cursor)))
            if source_offset < cursor or end > cursor + facts['size'] or overlap - operand_bytes:
                result.update(stop_reason='fixup_overlaps_instruction_structure',
                              blocked_fixup=fixup_index)
                blocked = True
                break
            attached.append(dict((k, v) for k, v in fixup.items() if k != 'sources') | {'source': source})
        if blocked:
            break
        _, fragments, _ = _window(data, report, obj, cursor, facts['size'])
        contiguous = bool(fragments) and all(a['file_offset'] + a['size'] == b['file_offset']
                                            for a, b in zip(fragments, fragments[1:]))
        encoded_target = facts['target']
        target = None
        if not attached and encoded_target is not None and 0 <= encoded_target < obj['virtual_size']:
            target = dict(object=object_number, offset=encoded_target, address_space='le.object')
        facts.update(offset=cursor, location=dict(object=object_number, offset=cursor, address_space='le.object'),
                     bits=obj['bits'], file_offset=fragments[0]['file_offset'] if contiguous else None,
                     file_fragments=fragments, encoding_text=facts['text'], encoded_target=encoded_target,
                     target=None, target_location=target, references=[], data_refs=[],
                     encoded_immediates=facts.pop('immediates'), immediates=[],
                     fixups=attached, symbolic_targets=[f['target'] for f in attached],
                     operand_status='symbolic_fixups' if attached else 'unrelocated_encoding',
                     runtime_selectors='unknown')
        if attached:
            facts['unresolved_reason'] = 'loader fixups are symbolic; encoded operand values are not runtime bindings'
        if vxd:
            identifier = None if attached else int.from_bytes(raw[2:6], 'little')
            facts['vxd_service'] = dict(identifier=identifier,
                encoded_identifier=int.from_bytes(raw[2:6], 'little'),
                device_id=None if identifier is None else identifier >> 16,
                ordinal_raw=None if identifier is None else identifier & 0xffff,
                runtime_binding='unknown', abi_assumption='explicit windows-vxd on a 32-bit object')
            facts['operands'] = 'symbolic service identifier' if identifier is None else f'0x{identifier:08x}'
            facts['text'] = 'vxd_service ' + facts['operands']
        elif int20:
            facts.update(flow='abi_unknown', unresolved_reason='INT20 ABI is unknown for this code view')
        elif instruction.flow_control == ix.FlowControl.INTERRUPT:
            facts['unresolved_reason'] = 'interrupt service behavior is outside this code view'
        elif facts['flow'] in ('call', 'indirect_call', 'conditional'):
            facts['continuation_assumption'] = 'sequential fallthrough only; no target traversal or return guarantee'
        result['instructions'].append(facts)
        cursor += facts['size']
        result['next_offset'] = cursor
        if vxd:
            result['stop_reason'] = 'external_service'
            break
        if int20:
            result['stop_reason'] = 'ambiguous_int20'
            break
        if instruction.flow_control == ix.FlowControl.INTERRUPT:
            result['stop_reason'] = 'unmodeled_interrupt'
            break
        if facts['flow'] in ('return', 'jump', 'indirect_jump', 'stop'):
            result['stop_reason'] = facts['flow']
            break
    else:
        result.update(stop_reason='instruction_budget', budget_exhausted=True)
    return result
