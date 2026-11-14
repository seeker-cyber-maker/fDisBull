"""Bounded LE object loading for mixed 16/32-bit x86 static analysis.

This module maps the executable's preferred object addresses, applies supported
internal offset32 fixups to a separate byte image, and retains the exact original
container. It does not create DOS/4GW selectors, execute a DOS extender, or map
the real-mode bootstrap into the protected-mode address space.

Encoding reference: Open Watcom's ``exeflat.h`` and LE page writer in
``bld/wl/c/loadflat.c`` at commit 5474be3542af05eee71be05fafc31bbe11f1415b.
https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h
Internal target offsets and offset16 source type: IBM Linear Executable
specification 2.12.1 (the common LE/LX fixup record, not LX page layout).
https://komh.github.io/os2books/os2tk45/lxref.htm

The supported profile deliberately excludes LX, imports, selector/far-pointer
fixups, fixup lists/chains/addends and iterated/compressed pages. Offset16 records
remain explicitly symbolic: their runtime operand binding is loader-dependent.
Unsupported encodings fail explicitly instead of leaving unrelocated pointers
in an apparently valid analysis image.
"""
from __future__ import annotations

import hashlib
import struct

from .model import Image, Region, Seed

MAX_IMAGE_SIZE = 64 * 1024 * 1024
MAX_OBJECTS = 4096
MAX_PAGES = 16384
MAX_FIXUPS = 100000
PAGE_SIZE = 4096
HEADER_SIZE = 196

_HEADER_FIELDS = (
    "version", "flags", "num_pages", "start_obj", "eip", "stack_obj", "esp",
    "page_size", "last_page_size", "fixup_size", "fixup_checksum", "loader_size",
    "loader_checksum", "object_table_offset", "object_count", "page_map_offset",
    "iterated_map_offset", "resource_table_offset", "resource_count",
    "resident_names_offset", "entry_table_offset", "module_directives_offset",
    "module_directives_count", "fixup_page_table_offset", "fixup_record_table_offset",
    "import_modules_offset", "import_module_count", "import_procedures_offset",
    "page_checksum_offset", "data_pages_offset", "preload_page_count",
    "nonresident_names_offset", "nonresident_names_size", "nonresident_names_checksum",
    "automatic_data_object", "debug_offset", "debug_size", "instance_preload_count",
    "instance_demand_count", "heap_size", "stack_size",
)


def _range(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"LE {label} exceeds source bounds")
    return data[offset:offset + size]


def _header_offset(data: bytes) -> int:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_IMAGE_SIZE:
        raise ValueError("LE source must contain 1..64 MiB immutable bytes")
    if data.startswith(b"LE"):
        return 0
    from .image_views import secondary_header
    secondary = secondary_header(data)
    if secondary is None or secondary["format"] != "LE":
        raise ValueError("LE signature or independent MZ secondary LE header required")
    return secondary["header_offset"]


def le_carrier_origin(data: bytes) -> dict | None:
    """Find a declared direct or MZ/BW/MZ LE carrier, without signature scans.

    BW ``next_header_pos`` is an absolute original-file offset, as documented
    by Open Watcom ``bld/watcom/h/exe16m.h`` at the pinned commit above. LE page
    offsets then use the inner MZ origin. A recognized malformed BW chain is a
    refusal, not permission to fall back to a guessed suffix.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_IMAGE_SIZE:
        raise ValueError("LE source must contain 1..64 MiB immutable bytes")
    if data.startswith(b"LE"):
        return dict(kind="direct-le", application_offset=0, header_offset=0,
                    application_header_offset=0, chain=[])
    from .image_views import secondary_header
    secondary = secondary_header(data)
    if secondary is not None:
        if secondary["format"] != "LE":
            return None
        return dict(kind="mz-le", application_offset=0,
                    header_offset=secondary["header_offset"],
                    application_header_offset=secondary["header_offset"], chain=[])
    if not data.startswith(b"MZ") or len(data) < 64:
        return None

    def mz(at: int, label: str) -> dict:
        raw = _range(data, at, 64, label)
        if raw[:2] != b"MZ":
            raise ValueError(f"LE BW {label} does not declare an MZ image")
        last, pages, count, paragraphs = struct.unpack_from("<4H", raw, 2)
        size = (pages - 1) * 512 + last if last else pages * 512
        header_size = paragraphs * 16
        relocations = struct.unpack_from("<H", raw, 24)[0]
        if not pages or last > 511 or not 28 <= header_size <= size <= len(data) - at:
            raise ValueError(f"LE BW {label} has invalid declared extents")
        if count and not 28 <= relocations <= relocations + count * 4 <= header_size:
            raise ValueError(f"LE BW {label} relocation table exceeds its header")
        return dict(format="MZ", original_offset=at, declared_bytes=size,
                    header_bytes=header_size, relocation_count=count,
                    relocation_table_offset=relocations)

    # Probe only the declared outer end. Unrelated trailing signatures are not
    # executable identities. Full validation becomes mandatory if BW is there.
    last, pages = struct.unpack_from("<2H", data, 2)
    end = (pages - 1) * 512 + last if last else pages * 512
    if not pages or last > 511 or not 64 <= end <= len(data) - 2 or data[end:end + 2] != b"BW":
        return None
    outer = mz(0, "outer MZ")
    _range(data, end, 176, "BW header")
    inner = struct.unpack_from("<I", data, end + 28)[0]
    if not end + 176 <= inner <= len(data) - 64:
        raise ValueError("LE BW next_header_pos is outside the forward bounded carrier")
    nested = mz(inner, "inner MZ")
    if nested["header_bytes"] < 64:
        raise ValueError("LE BW inner MZ header does not contain an independent e_lfanew field")
    secondary = secondary_header(data[inner:])
    if secondary is None or secondary["format"] != "LE":
        raise ValueError("LE BW inner MZ requires an independent secondary LE header")
    if secondary["header_offset"] < nested["header_bytes"]:
        raise ValueError("LE BW secondary LE header overlaps the declared inner MZ header")
    return dict(kind="mz-bw-mz-le", application_offset=inner,
                header_offset=inner + secondary["header_offset"],
                application_header_offset=secondary["header_offset"],
                chain=[outer, dict(format="BW", original_offset=end,
                                   next_header_pos=inner,
                                   next_header_pos_domain="absolute original-file offset"), nested])


def load_le(data: bytes, *, entry: int | None = None) -> Image:
    """Load the declared LE application, retaining the complete original carrier.

    Source mappings and fixup file evidence use original-file coordinates.
    Header field values remain exactly as declared, with their application-file
    origin explicit. Preferred object keys are not runtime selector bindings.
    """
    origin = le_carrier_origin(data)
    if origin is None:
        raise ValueError("LE signature or declared MZ/BW/MZ secondary LE carrier required")
    base = origin["application_offset"]
    image = _load_le_application(data[base:], entry=entry)

    def rebase(value):
        if isinstance(value, dict):
            return {key: (item + base if item is not None and key in
                          ("file_offset", "record_file_offset", "header_offset") else rebase(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [rebase(item) for item in value]
        return value

    metadata = rebase(image.metadata)
    metadata.update(source_sha256=hashlib.sha256(data).hexdigest())
    metadata["le"].update(carrier=origin,
                          application_source_sha256=hashlib.sha256(data[base:]).hexdigest(),
                          header_field_file_offset_origin=base,
                          file_offset_domain="original complete source carrier")
    return Image(image.format, image.arch, image.bits, image.entry, image.regions,
                 image.seeds, metadata, source_bytes=data)


def _load_le_application(data: bytes, *, entry: int | None = None) -> Image:
    """Load a bounded little-endian i386/486 LE executable, preserving its source.

    Internal offset32 fixups are applied in the preferred static projection;
    offset16 records retain original operand bytes and an unresolved binding.
    Target offsets may
    occupy either two or four bytes, and object ordinals either one or two.
    Negative source offsets describe a fixup spanning the previous page; the
    duplicate record on that page must agree. Object-end target pointers are
    allowed, but entry points must name an actual executable, file-backed byte.
    """
    header_offset = _header_offset(data)
    raw_header = _range(data, header_offset, HEADER_SIZE, "header")
    if raw_header[2:4] != b"\0\0" or struct.unpack_from("<I", raw_header, 4)[0] != 0:
        raise ValueError("LE requires little-endian byte/word order and format level zero")
    cpu, operating_system = struct.unpack_from("<HH", raw_header, 8)
    if cpu not in (2, 3):
        raise ValueError("LE static profile requires an i386/486 CPU")
    fields = dict(zip(_HEADER_FIELDS, struct.unpack_from("<41I", raw_header, 12)))
    if fields["flags"] & (0x2000 | 0x8000 | 0x10000 | 0x20000):
        raise ValueError("LE DLL, driver or link-error modules are unsupported")
    if fields["import_module_count"]:
        raise ValueError("LE imported modules require unsupported external fixups")
    page_count, object_count = fields["num_pages"], fields["object_count"]
    if not 1 <= object_count <= MAX_OBJECTS or not 1 <= page_count <= MAX_PAGES:
        raise ValueError("LE object/page count is outside the supported budget")
    if fields["page_size"] != PAGE_SIZE:
        raise ValueError("LE static profile requires 4096-byte pages")
    last_page_size = fields["last_page_size"]
    if not 1 <= last_page_size <= PAGE_SIZE:
        raise ValueError("LE last-page size must be between 1 and 4096")

    def relative(offset: int, size: int, label: str) -> int:
        if offset < HEADER_SIZE:
            raise ValueError(f"LE {label} overlaps the fixed header")
        absolute = header_offset + offset
        _range(data, absolute, size, label)
        return absolute

    object_table = relative(fields["object_table_offset"], object_count * 24, "object table")
    page_table = relative(fields["page_map_offset"], page_count * 4, "page map")
    fixup_page_table = relative(fields["fixup_page_table_offset"], (page_count + 1) * 4, "fixup page table")
    fixup_records = relative(fields["fixup_record_table_offset"], 0, "fixup record table")
    fixup_end = fixup_page_table + fields["fixup_size"]
    _range(data, fixup_page_table, fields["fixup_size"], "fixup section")
    if fixup_records < fixup_page_table + (page_count + 1) * 4 or fixup_records > fixup_end:
        raise ValueError("LE fixup record table is outside its fixup section")
    fixed_tables = [
        (header_offset, header_offset + HEADER_SIZE),
        (object_table, object_table + object_count * 24),
        (page_table, page_table + page_count * 4),
        (fixup_page_table, fixup_end),
    ]
    fixed_tables.sort()
    if any(left[1] > right[0] for left, right in zip(fixed_tables, fixed_tables[1:])):
        raise ValueError("LE structural tables overlap")
    data_pages = fields["data_pages_offset"]  # Absolute file offset, unlike the tables.
    if data_pages < max(end for _, end in fixed_tables):
        raise ValueError("LE data pages overlap structural tables")

    objects: list[dict] = []
    buffers: list[bytearray] = []
    owners: dict[int, tuple[int, int]] = {}
    total_size = 0
    for index in range(object_count):
        size, base, flags, first_page, pages, reserved = struct.unpack_from("<6I", data, object_table + index * 24)
        if not size or size > MAX_IMAGE_SIZE or total_size + size > MAX_IMAGE_SIZE:
            raise ValueError("LE mapped objects exceed the nonempty 64 MiB budget")
        if base + size > 1 << 32:
            raise ValueError("LE object exceeds the 32-bit address space")
        object_bits = 32 if flags & 0x2000 else 16
        if flags & (0x8 | 0x80 | 0x4000 | 0x8000):
            raise ValueError("LE object requires unsupported resource, invalid or privileged semantics")
        if object_bits == 16 and size > 65536:
            raise ValueError("LE 16-bit object exceeds its 64 KiB offset space")
        if pages > (size + PAGE_SIZE - 1) // PAGE_SIZE:
            raise ValueError("LE object page count exceeds its virtual size")
        if first_page < 1 or first_page + pages - 1 > page_count or first_page > page_count + 1:
            raise ValueError("LE object page map range is out of bounds")
        for local_page in range(pages):
            logical_page = first_page - 1 + local_page
            if logical_page in owners:
                raise ValueError("LE page map entries are shared by multiple objects")
            owners[logical_page] = (index, local_page)
        objects.append(dict(index=index + 1, virtual_address=base, virtual_size=size,
                            flags=flags, bits=object_bits, runtime_selector=None,
                            alias_required=bool(flags & 0x1000),
                            executable=bool(flags & 4), writable=bool(flags & 2),
                            page_map_index=first_page, page_count=pages, reserved=reserved,
                            file_backed_size=0, zero_filled_size=size))
        buffers.append(bytearray(size))
        total_size += size
    by_address = sorted(objects, key=lambda item: item["virtual_address"])
    if any(a["virtual_address"] + a["virtual_size"] > b["virtual_address"]
           for a, b in zip(by_address, by_address[1:])):
        raise ValueError("LE preferred object ranges overlap")
    if len(owners) != page_count:
        raise ValueError("LE page map contains unowned entries")

    pages: list[dict] = []
    file_mappings: list[dict] = []
    source_locations: dict[tuple[int, int], tuple[int, int]] = {}
    # Logical zero-fill pages have no stored page. The short last-page field
    # describes the final enumerated physical page, not its logical map slot.
    last_physical_page = max(
        (int.from_bytes(data[page_table + i * 4:page_table + i * 4 + 3], "big")
         for i in range(page_count) if data[page_table + i * 4 + 3] == 0),
        default=0,
    )
    for logical_page in range(page_count):
        owner, local_page = owners[logical_page]
        obj = objects[owner]
        raw_page = data[page_table + logical_page * 4:page_table + logical_page * 4 + 4]
        physical_page = int.from_bytes(raw_page[:3], "big")
        flags = raw_page[3]
        object_offset = local_page * PAGE_SIZE
        capacity = min(PAGE_SIZE, obj["virtual_size"] - object_offset)
        file_offset = None
        file_size = 0
        if flags == 0:
            if not 1 <= physical_page <= page_count:
                raise ValueError("LE physical page index is out of bounds")
            physical_size = last_page_size if physical_page == last_physical_page else PAGE_SIZE
            file_offset = data_pages + (physical_page - 1) * PAGE_SIZE
            payload = _range(data, file_offset, physical_size, "enumerated page")
            file_size = min(capacity, physical_size)
            buffers[owner][object_offset:object_offset + file_size] = payload[:file_size]
            file_mappings.append(dict(virtual_address=obj["virtual_address"] + object_offset,
                                      file_offset=file_offset, file_size=file_size))
            source_locations[(owner, local_page)] = (file_offset, file_size)
            obj["file_backed_size"] += file_size
            obj["zero_filled_size"] -= file_size
        elif flags == 3:
            if physical_page:
                raise ValueError("LE zero-fill page must have physical index zero")
        else:
            raise ValueError(f"LE page encoding {flags} is unsupported (requires valid or zero-fill)")
        pages.append(dict(index=logical_page + 1, object=owner + 1, object_offset=object_offset,
                          physical_page=physical_page, flags=flags, file_offset=file_offset,
                          file_size=file_size, mapped_size=capacity))

    original_images = [bytes(buffer) for buffer in buffers]
    fixup_offsets = struct.unpack_from("<" + "I" * (page_count + 1), data, fixup_page_table)
    if fixup_offsets[0] != 0 or any(a > b for a, b in zip(fixup_offsets, fixup_offsets[1:])):
        raise ValueError("LE fixup page offsets must start at zero and be monotonic")
    if fixup_records + fixup_offsets[-1] > fixup_end:
        raise ValueError("LE fixup records exceed their section")
    fixups: list[dict] = []
    writes: dict[tuple[int, int], tuple[tuple, int, int]] = {}
    for logical_page in range(page_count):
        owner, local_page = owners[logical_page]
        obj = objects[owner]
        position = fixup_records + fixup_offsets[logical_page]
        end = fixup_records + fixup_offsets[logical_page + 1]
        while position < end:
            if len(fixups) >= MAX_FIXUPS:
                raise ValueError("LE fixup count exceeds the 100000-record budget")
            record_offset = position

            def read(size: int) -> bytes:
                nonlocal position
                if position + size > end:
                    raise ValueError("LE fixup record crosses its page-table boundary")
                value = data[position:position + size]
                position += size
                return value

            source_flags, target_flags = read(2)
            if source_flags not in (5, 7) or target_flags & ~(0x10 | 0x40):
                raise ValueError(f"LE unsupported fixup encoding source={source_flags:#x} target={target_flags:#x}")
            width = 2 if source_flags == 5 else 4
            source_offset = int.from_bytes(read(2), "little", signed=True)
            if not -(width - 1) <= source_offset < PAGE_SIZE:
                raise ValueError("LE fixup source must intersect its logical page")
            target_object = int.from_bytes(read(2 if target_flags & 0x40 else 1), "little")
            target_offset = int.from_bytes(read(4 if target_flags & 0x10 else 2), "little")
            if not 1 <= target_object <= object_count:
                raise ValueError("LE fixup target object is out of bounds")
            target = objects[target_object - 1]
            if target_offset > target["virtual_size"]:
                raise ValueError("LE fixup target offset exceeds its object")
            target_address = target["virtual_address"] + target_offset
            if width == 2:
                # The record names an object and target offset, but that alone
                # does not establish the runtime operand domain. DOS/4GW native
                # evidence differs from DOS/32A's fix_16off implementation.
                # Preserve this known field and its unknown binding, rather
                # than choosing a local offset or a truncated linear address.
                relocated, encoding_domain = None, "symbolic-offset16"
            else:
                relocated, encoding_domain = target_address, "preferred-linear"
                if relocated >= 1 << 32:
                    raise ValueError("LE fixup value exceeds 32 bits")
            source = local_page * PAGE_SIZE + source_offset
            if source < 0 or source + width > obj["virtual_size"]:
                raise ValueError("LE fixup source exceeds its object")
            duplicate_of = None
            signature = (source_flags, target_object, target_offset, relocated, encoding_domain)
            for neighbor in range(source - 3, source + width):
                previous = writes.get((owner, neighbor))
                if previous is not None and neighbor + previous[2] > source:
                    if neighbor != source or previous[0] != signature or previous[2] != width:
                        raise ValueError("LE overlapping fixup writes disagree")
                    duplicate_of = previous[1]
            original = original_images[owner][source:source + width]
            # A word may span noncontiguous physical pages or end in BSS.
            # Claim one file offset only when all bytes are contiguous
            # in the original file. Keep partial fragments explicit otherwise.
            fragments = []
            for byte_index in range(width):
                byte_offset = source + byte_index
                source_location = source_locations.get((owner, byte_offset // PAGE_SIZE))
                if source_location is None or byte_offset % PAGE_SIZE >= source_location[1]:
                    continue
                file_byte = source_location[0] + byte_offset % PAGE_SIZE
                if (fragments and fragments[-1]["word_offset"] + fragments[-1]["size"] == byte_index
                        and fragments[-1]["file_offset"] + fragments[-1]["size"] == file_byte):
                    fragments[-1]["size"] += 1
                else:
                    fragments.append(dict(word_offset=byte_index, file_offset=file_byte, size=1))
            source_file_offset = fragments[0]["file_offset"] if len(fragments) == 1 and fragments[0]["size"] == width else None
            record = dict(index=len(fixups), page=logical_page + 1,
                          record_file_offset=record_offset, record_size=position - record_offset,
                          source_type="offset16" if width == 2 else "offset32",
                          source_flags=source_flags, target_flags=target_flags,
                          source_object=owner + 1, source_offset=source,
                          page_source_offset=source_offset,
                          address=obj["virtual_address"] + source,
                          linear_address=obj["virtual_address"] + source,
                          file_offset=source_file_offset, file_fragments=fragments,
                          zero_filled_bytes=width - sum(part["size"] for part in fragments), width=width,
                          target_object=target_object, target_offset=target_offset,
                          target_address=target_address, encoding_domain=encoding_domain,
                          runtime_selector=None, original_bytes=original.hex(),
                          original_value=int.from_bytes(original, "little"),
                          relocated_value=relocated, applied=relocated is not None,
                          applied_to="static_analysis_image" if relocated is not None else None,
                          runtime_applied=False,
                          unresolved_reason=("offset16 runtime operand binding depends on loader/selector semantics"
                                             if relocated is None else None),
                          duplicate_of=duplicate_of)
            if duplicate_of is None:
                writes[(owner, source)] = (signature, len(fixups), width)
                if relocated is not None:
                    buffers[owner][source:source + width] = relocated.to_bytes(width, "little")
            fixups.append(record)

    start_object = fields["start_obj"]
    if not 1 <= start_object <= object_count:
        raise ValueError("LE entry object is out of bounds")
    start = objects[start_object - 1]
    if fields["eip"] >= start["virtual_size"]:
        raise ValueError("LE entry offset exceeds its object")
    declared_entry = start["virtual_address"] + fields["eip"]
    selected = declared_entry if entry is None else entry
    if isinstance(selected, bool) or not isinstance(selected, int) or not 0 <= selected < 1 << 32:
        raise ValueError("LE analysis entry must be a 32-bit address")
    if not any(obj["executable"] and obj["virtual_address"] <= selected < obj["virtual_address"] + obj["virtual_size"] for obj in objects):
        raise ValueError("LE analysis entry must be in an executable object")
    if not any(mapping["virtual_address"] <= selected < mapping["virtual_address"] + mapping["file_size"] for mapping in file_mappings):
        raise ValueError("LE analysis entry must be file-backed, not zero-filled")
    stack_object = fields["stack_obj"]
    if stack_object > object_count:
        raise ValueError("LE stack object is out of bounds")
    stack_address = None
    if stack_object:
        stack = objects[stack_object - 1]
        if fields["esp"] > stack["virtual_size"]:
            raise ValueError("LE stack offset exceeds its object")
        stack_address = stack["virtual_address"] + fields["esp"]

    regions = [Region(f"object_{obj['index']}", obj["virtual_address"], bytes(buffer),
                      obj["executable"], obj["writable"])
               for obj, buffer in zip(objects, buffers)]
    regions.sort(key=lambda region: region.start)
    load_model = "Preferred LE object keys with static offset32 fixups and symbolic/unapplied offset16 records; per-object 16/32-bit decoding; no runtime selectors or DOS extender execution"
    symbolic_count = sum(not fixup['applied'] for fixup in fixups)
    le = dict(header_offset=header_offset, header_fields=fields, cpu_type=cpu,
              operating_system=operating_system, byte_order="little", word_order="little",
              entrypoint=selected, declared_entrypoint=declared_entry,
              entry_object=start_object, entry_offset=fields["eip"],
              entrypoint_present=True, stack_object=stack_object, stack_address=stack_address,
              page_size=PAGE_SIZE, page_count=page_count, object_count=object_count,
              objects=objects, mixed_bits=len({obj['bits'] for obj in objects}) > 1,
              pages=pages, fixups=fixups, fixup_count=len(fixups),
              unique_fixup_writes=sum(fixup['applied'] and fixup['duplicate_of'] is None for fixup in fixups),
              unique_fixup_sites=len(writes), symbolic_fixup_count=symbolic_count,
              runtime_selectors='unknown',
              file_backed_size=sum(obj["file_backed_size"] for obj in objects),
              mapped_size=total_size, zero_filled_size=sum(obj["zero_filled_size"] for obj in objects),
              load_model=load_model,
              fixup_original_value_model="Pre-fixup mapped bytes, including declared zero fill; file_fragments identify actual source bytes",
              warnings=(["offset16 operands retain source bytes: runtime loader/selector binding is unresolved"]
                        if symbolic_count else []))
    metadata = dict(selected_image="le", mapping=load_model, source_sha256=hashlib.sha256(data).hexdigest(),
                    entrypoint_present=True, declared_entrypoint=declared_entry,
                    file_mappings=file_mappings,
                    decode_regions=[dict(start=obj['virtual_address'],
                                         end=obj['virtual_address'] + obj['virtual_size'],
                                         bits=obj['bits'], object_index=obj['index'], object_offset=0)
                                    for obj in objects], le=le)
    seed_source = "le_entry" if entry is None else "explicit_entry"
    seeds = [Seed(selected, "entry", seed_source)]
    for obj in objects:
        if (obj['bits'] == 16 and obj['executable'] and obj['virtual_address'] != selected and
                any(mapping['virtual_address'] == obj['virtual_address'] and mapping['file_size']
                    for mapping in file_mappings)):
            seeds.append(Seed(obj['virtual_address'], f"le_object_{obj['index']}_entry_candidate",
                              'LE executable object boundary candidate'))
    selected_object = next(obj for obj in objects
                           if obj['virtual_address'] <= selected < obj['virtual_address'] + obj['virtual_size'])
    return Image("LE", "x86", selected_object['bits'], selected, regions, seeds, metadata, source_bytes=data)


def inspect_le(data: bytes) -> dict:
    """Return validated LE structure and fixup evidence without retained code bytes."""
    image = load_le(data)
    result = dict(image.metadata["le"])
    sections = []
    for obj in image.metadata["le"]["objects"]:
        mappings = [mapping for mapping in image.metadata["file_mappings"]
                    if obj["virtual_address"] <= mapping["virtual_address"] < obj["virtual_address"] + obj["virtual_size"]]
        contiguous = bool(mappings) and mappings[0]["virtual_address"] == obj["virtual_address"]
        if contiguous:
            contiguous = all(a["file_offset"] + a["file_size"] == b["file_offset"]
                             and a["virtual_address"] + a["file_size"] == b["virtual_address"]
                             for a, b in zip(mappings, mappings[1:]))
        permissions = ("r" if obj["flags"] & 1 else "-") + ("w" if obj["writable"] else "-") + ("x" if obj["executable"] else "-")
        sections.append(dict(name=f"object_{obj['index']}", virtual_address=obj["virtual_address"],
                             virtual_size=obj["virtual_size"], permissions=permissions,
                             bits=obj['bits'], runtime_selector=None,
                             file_offset=mappings[0]["file_offset"] if contiguous else None,
                             file_size=sum(mapping["file_size"] for mapping in mappings) if contiguous else (0 if not mappings else None),
                             file_fragments=mappings, executable=obj["executable"], writable=obj["writable"]))
    result.update(format="LE", arch="x86", bits=image.bits,
                  decode_regions=image.metadata['decode_regions'],
                  file_mappings=image.metadata["file_mappings"], sections=sections)
    return result
