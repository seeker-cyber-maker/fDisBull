"""Bounded DOS device-header loading; no driver installation or execution.

The DOS device-file contract is described in the Microsoft MS-DOS Encyclopedia,
Section II, article 15 (device headers and general rules):
https://www.pcjs.org/documents/books/mspl13/msdos/encyclopedia/section2/

Only a common-segment on-disk header chain is supported: a next-header offset
with segment zero, ending in FFFF:FFFF. Runtime-resolved pointers are not
guessed. MZ wrappers retain the ordinary validated DOS module/relocation view;
their process CS:IP and PSP/stack assumptions do not become driver entry facts.
"""
from __future__ import annotations

import hashlib
import struct

from .model import Image, Region, Seed

MAX_SOURCE = 64 * 1024 * 1024
MAX_HEADERS = 256
HEADER_SIZE = 18


def execution_boundary(raw: bytes, ip: int) -> str | None:
    """Qualify a decoded SYS instruction that can invalidate real-mode context."""
    import iced_x86 as ix
    instruction = ix.Decoder(16, raw[:15], ip=ip).decode()
    control_write = (instruction.mnemonic == ix.Mnemonic.MOV
                     and instruction.op0_kind == ix.OpKind.REGISTER
                     and instruction.op0_register == ix.Register.CR0)
    if control_write or instruction.mnemonic == ix.Mnemonic.LMSW:
        return 'driver execution-mode control write; subsequent mode, paging and selector interpretation are unknown'
    if instruction.mnemonic in (ix.Mnemonic.SYSENTER, ix.Mnemonic.SYSEXIT,
                                ix.Mnemonic.SYSCALL, ix.Mnemonic.SYSRET, ix.Mnemonic.RSM):
        return 'driver execution-context transition; target mode and selector interpretation are unknown'
    return None


def _module(data: bytes) -> tuple[int, int]:
    if not isinstance(data, bytes) or not HEADER_SIZE <= len(data) <= MAX_SOURCE:
        raise ValueError('DOS SYS source requires 18..64 MiB immutable bytes')
    if not data.startswith(b'MZ'):
        return 0, len(data)
    if len(data) < 28:
        raise ValueError('DOS SYS MZ wrapper has a truncated header')
    last, pages, _, paragraphs = struct.unpack_from('<4H', data, 2)
    if not pages or last > 511:
        raise ValueError('DOS SYS MZ wrapper has invalid page counts')
    start = paragraphs * 16
    end = pages * 512 - (512 - last if last else 0)
    if start < 28 or end > len(data) or start + HEADER_SIZE > end:
        raise ValueError('DOS SYS MZ wrapper has no complete file-backed device header')
    return start, end


def _headers(module: bytes, file_base: int, *, automatic: bool) -> list[dict]:
    headers = []
    offset = 0
    seen = set()
    while True:
        if offset in seen:
            raise ValueError('DOS SYS device-header chain contains a cycle')
        if len(headers) >= MAX_HEADERS:
            raise ValueError('DOS SYS device-header chain exceeds 256 headers')
        if offset + HEADER_SIZE > min(len(module), 0x10000):
            raise ValueError('DOS SYS device header is outside the file-backed common segment')
        if any(offset < h['module_offset'] + HEADER_SIZE and offset + HEADER_SIZE > h['module_offset'] for h in headers):
            raise ValueError('DOS SYS device headers overlap')
        seen.add(offset)
        next_offset, next_segment, attributes, strategy, interrupt = struct.unpack_from('<5H', module, offset)
        final = next_offset == next_segment == 0xffff
        if not final and (next_segment != 0 or next_offset < HEADER_SIZE):
            raise ValueError('DOS SYS next header requires an in-file offset and segment zero, or FFFF:FFFF')
        if any(target < HEADER_SIZE or target >= min(len(module), 0x10000) for target in (strategy, interrupt)):
            raise ValueError('DOS SYS Strategy/Interrupt offsets must name file-backed common-segment bytes')
        raw_name = module[offset + 10:offset + HEADER_SIZE]
        character = bool(attributes & 0x8000)
        if character:
            if automatic and (not all(0x20 <= value <= 0x7e for value in raw_name) or not raw_name.strip()):
                raise ValueError('DOS SYS automatic recognition requires a printable, nonempty character-device name')
            name = raw_name.decode('cp437').rstrip(' \0')
            units = None
        else:
            # These seven reserved bytes are not a device name. Restrict the
            # heuristic, while explicit SYS selection retains unusual values.
            if automatic and (raw_name[1:] != bytes(7) or raw_name[0] == 0):
                raise ValueError('DOS SYS automatic block recognition requires a unit count and zero reserved bytes')
            name, units = None, raw_name[0]
        headers.append(dict(index=len(headers), module_offset=offset,
                            file_offset=file_base + offset, size=HEADER_SIZE,
                            next_offset=next_offset, next_segment=next_segment,
                            final=final, attributes=attributes,
                            device_type='character' if character else 'block',
                            name=name, name_or_units_bytes=raw_name.hex(), unit_count=units,
                            strategy_offset=strategy, interrupt_offset=interrupt))
        if final:
            break
        offset = next_offset
    for header in headers:
        for role in ('strategy', 'interrupt'):
            target = header[role + '_offset']
            if any(h['module_offset'] <= target < h['module_offset'] + HEADER_SIZE for h in headers):
                raise ValueError('DOS SYS Strategy/Interrupt target overlaps a device header')
    return headers


def probe_sys(data: bytes) -> dict | None:
    """Conservative structural recognition; a suffix is never consulted.

    A successful probe recognizes header/entry structure, not executable code,
    MZ allocation validity, or compatibility with any installed DOS version.
    """
    try:
        start, end = _module(data)
        headers = _headers(data[start:end], start, automatic=True)
    except ValueError:
        return None
    return dict(container='mz' if start else 'flat', header_size=start,
                declared_file_size=end, module_size=end - start, headers=headers,
                header_count=len(headers), recognition='validated device-header chain and file-backed entry offsets')


def embedded_le_inventory(data: bytes) -> dict | None:
    """Inspect bounded embedded LE headers/objects, without loading their code.

    Object width is a descriptor fact. It is not a claim that the ordinary
    x86-32 LE loader can analyze these objects or bind their runtime selectors.
    Page payloads, imports and relocation records are deliberately unvalidated.
    """
    from .image_views import secondary_header
    secondary = secondary_header(data)
    if secondary is None or secondary['format'] != 'LE':
        return None
    start = secondary['header_offset']
    result = dict(format='LE', header_offset=start, metadata_valid=False,
                  analysis_available=False, objects=[], unsupported_features=[],
                  validation_scope='fixed LE header and object-table extents only; no page/fixup validation or execution')
    try:
        if start + 196 > len(data):
            raise ValueError('truncated embedded LE fixed header')
        if data[start + 2:start + 4] != b'\0\0' or struct.unpack_from('<I', data, start + 4)[0]:
            raise ValueError('embedded LE inventory requires little-endian format level zero')
        word = lambda at: struct.unpack_from('<I', data, start + at)[0]
        count, table, pages = word(0x44), word(0x40), word(0x14)
        if not 1 <= count <= 4096 or not 0 <= pages <= 16384:
            raise ValueError('embedded LE object/page count exceeds inventory budget')
        if table < 196 or start + table + count * 24 > len(data):
            raise ValueError('embedded LE object table is outside its source')
        objects = []
        total = 0
        for index in range(count):
            size, base, flags, first, number, reserved = struct.unpack_from('<6I', data, start + table + index * 24)
            total += size
            if not size or total > MAX_SOURCE or base + size > 1 << 32:
                raise ValueError('embedded LE object sizes exceed the inventory address/size budget')
            objects.append(dict(index=index + 1, preferred_address=base, virtual_size=size,
                                flags=flags, default_bits=32 if flags & 0x2000 else 16,
                                executable=bool(flags & 4), writable=bool(flags & 2),
                                alias16=bool(flags & 0x1000), page_map_index=first,
                                page_count=number, logical_page_end=first + number - 1 if number else None,
                                reserved=reserved))
        flags = word(0x10)
        unsupported = ['page contents and fixup records are not validated by this inventory',
                       'runtime selectors, mode transitions and driver services are not modeled']
        if flags & (0x8000 | 0x10000 | 0x20000):
            unsupported.append('DLL/device-driver module flags are outside the ordinary flat LE executable profile')
        if any(obj['default_bits'] == 16 for obj in objects):
            unsupported.append('16-bit objects require object-specific decoding, not global x86-32 analysis')
        if any(obj['alias16'] for obj in objects):
            unsupported.append('16-bit alias selector semantics remain unresolved')
        if word(0x74):
            unsupported.append('imported modules require external fixup resolution')
        if not word(0x18):
            unsupported.append('no declared module entry; an entry at zero must not be invented')
        result.update(metadata_valid=True, cpu_type=struct.unpack_from('<H', data, start + 8)[0],
                      operating_system=struct.unpack_from('<H', data, start + 10)[0],
                      module_flags=flags, object_count=count, page_count=pages,
                      entry_object=word(0x18), entry_offset=word(0x1c),
                      import_module_count=word(0x74), objects=objects,
                      default_widths=sorted({obj['default_bits'] for obj in objects}),
                      logical_page_extent=max((obj['logical_page_end'] or 0 for obj in objects),default=0),
                      page_count_relationship='unvalidated; object page indices are logical and may include zero-fill pages absent from the header physical count',
                      unsupported_features=unsupported)
    except ValueError as error:
        result['error'] = str(error)
    return result


def load_sys(data: bytes, *, load_segment: int = 0x1000, entry: int | None = None) -> Image:
    """Map a validated flat or MZ-wrapped driver and seed its two DOS interfaces.

    Driver calls have no PSP-based register model. ES:BX at Strategy is an
    unknown caller-owned request pointer, not mapped memory. Interrupt is a
    separate entry and must retrieve the saved pointer itself. The declared
    driver header is data; it never becomes an instruction seed.
    """
    if isinstance(load_segment, bool) or not isinstance(load_segment, int) or not 0 <= load_segment <= 0xffff:
        raise ValueError('DOS SYS load_segment must be a 16-bit segment')
    start, end = _module(data)
    headers = _headers(data[start:end], start, automatic=False)
    base = load_segment * 16
    first = base + headers[0]['strategy_offset']
    selected = first if entry is None else entry
    if (isinstance(selected, bool) or not isinstance(selected, int)
            or not base <= selected < base + min(end - start, 0x10000)):
        raise ValueError('DOS SYS explicit entry must name file-backed bytes in the driver CS window')
    if any(base + h['module_offset'] <= selected < base + h['module_offset'] + HEADER_SIZE for h in headers):
        raise ValueError('DOS SYS entry cannot overlap a device header')
    if start:
        from .dos import load_mz
        image = load_mz(data, load_segment=load_segment, entry=selected, allow_secondary=True, _driver=True)
        dos = dict(image.metadata['dos'])
        regions = image.regions
        mappings = image.metadata['file_mappings']
        # A relocation may not turn an offset, name or attribute into another
        # field while the retained roots still describe the original header.
        for relocation in dos['relocations']:
            relative = relocation['linear_address'] - base
            for header in headers:
                low = header['module_offset']
                if relative < low + HEADER_SIZE and relative + 2 > low:
                    if header['final'] or relative != low + 2:
                        raise ValueError('DOS SYS MZ relocation changes a device-header field')
        candidates = []
        for candidate in dos['segment_candidates']:
            sources = [s for s in candidate['sources'] if s['kind'] == 'relocated_word']
            if sources:
                candidates.append(dict(candidate, sources=sources))
    else:
        if base + len(data) > 0x100000:
            raise ValueError('DOS SYS image exceeds the unwrapped 1 MiB address space')
        regions = [Region('driver_image', base, data, True, True)]
        mappings = [dict(virtual_address=base, file_offset=0, file_size=len(data))]
        candidates = []
        dos = dict(module_size=len(data), allocation_size=len(data), relocations=[],
                   header_fields={}, header_size=0, declared_file_size=len(data),
                   overlay_offset=len(data), overlay_size=0, secondary_format=None,
                   secondary_header_offset=None, a20_wrap=False,
                   allocation_policy='Only flat driver file bytes mapped; no DOS allocation or request packet fabricated')
    candidates.append(dict(segment=load_segment, linear_base=base, status='candidate',
                           sources=[dict(kind='DOS device-header common segment')]))
    roots = []
    for header in headers:
        header.update(address=base + header['module_offset'], segment=load_segment)
        for role, label in (('strategy', 'Strategy'), ('interrupt', 'Interrupt')):
            offset = header[role + '_offset']
            header[role + '_address'] = base + offset
            roots.append(dict(address=base + offset, cs=load_segment, ip=offset,
                              name=f"sys_{header['index']}_{role}", role=role,
                              source=f"DOS SYS header {header['index']} {label}",
                              header_index=header['index'], initial_registers={},
                              field_file_offset=header['file_offset'] + (6 if role == 'strategy' else 8)))
    if entry is not None:
        roots.insert(0, dict(address=selected, cs=load_segment, ip=selected - base,
                             name='explicit_entry', role='explicit', source='explicit SYS entry',
                             initial_registers={}))
    dos.update(selected_image='sys', load_segment=load_segment, image_base=base,
               entry_cs=load_segment, entry_ip=headers[0]['strategy_offset'], header_entry=first,
               selected_entry=selected, selected_entry_cs=load_segment, selected_entry_ip=selected - base,
               selected_entry_cs_source='DOS device-header common segment',
               entry_override=entry, entry_roots=roots, segment_candidates=candidates,
               psp_segment=None, stack_ss=None, sp=None, stack_linear=None,
               permissions='possible executable/writable DOS driver memory; not a code classification',
               startup_model='independent far-call driver entries; caller registers and request storage are unknown')
    description = dict(container='mz' if start else 'flat', header_count=len(headers), headers=headers,
                       request_contract='Strategy receives unknown ES:BX; Interrupt is a separate far-call entry with no implied request-register values',
                       execution='static analysis only; no driver installation, request dispatch or DOS boot performed')
    embedded = embedded_le_inventory(data) if start else None
    if embedded is not None:
        description['embedded_le'] = embedded
    metadata = dict(selected_image='sys', source_sha256=hashlib.sha256(data).hexdigest(),
                    mapping='DOS driver common-segment addresses (segment*16+offset); unknown caller registers',
                    file_mappings=mappings, dos=dos, dos_driver=description,
                    entrypoint_present=True)
    return Image('SYS', 'x86', 16, selected, regions,
                 [Seed(root['address'], root['name'], root['source']) for root in roots], metadata,
                 source_bytes=data)
