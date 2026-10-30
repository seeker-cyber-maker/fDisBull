"""Bounded LE object loading for flat 32-bit x86 static analysis.

This module maps the executable's preferred object addresses, applies supported
internal offset fixups to a separate byte image, and retains the exact original
container. It does not create DOS/4GW selectors, execute a DOS extender, or map
the real-mode bootstrap into the protected-mode address space.

Encoding reference: Open Watcom's ``exeflat.h`` and LE page writer in
``bld/wl/c/loadflat.c`` at commit 5474be3542af05eee71be05fafc31bbe11f1415b.
https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h

The supported profile deliberately excludes LX, imports, selector/far-pointer
fixups, fixup lists/chains/addends, iterated/compressed pages and 16-bit objects.
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


def load_le(data: bytes, *, entry: int | None = None) -> Image:
    """Load a bounded little-endian i386/486 LE executable, preserving its source.

    Only internal 32-bit offset fixups are supported. Their target offsets may
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
        if not flags & 0x2000 or flags & (0x8 | 0x80 | 0x1000 | 0x4000 | 0x8000):
            raise ValueError("LE object requires unsupported 16-bit, resource, invalid, alias or privileged semantics")
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
                            flags=flags, executable=bool(flags & 4), writable=bool(flags & 2),
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
    writes: dict[tuple[int, int], tuple[int, int]] = {}
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
            if source_flags != 7 or target_flags & ~(0x10 | 0x40):
                raise ValueError(f"LE unsupported fixup encoding source={source_flags:#x} target={target_flags:#x}")
            source_offset = int.from_bytes(read(2), "little", signed=True)
            if not -3 <= source_offset < PAGE_SIZE:
                raise ValueError("LE 32-bit fixup source must intersect its logical page")
            target_object = int.from_bytes(read(2 if target_flags & 0x40 else 1), "little")
            target_offset = int.from_bytes(read(4 if target_flags & 0x10 else 2), "little")
            if not 1 <= target_object <= object_count:
                raise ValueError("LE fixup target object is out of bounds")
            target = objects[target_object - 1]
            if target_offset > target["virtual_size"]:
                raise ValueError("LE fixup target offset exceeds its object")
            relocated = target["virtual_address"] + target_offset
            if relocated >= 1 << 32:
                raise ValueError("LE fixup value exceeds 32 bits")
            source = local_page * PAGE_SIZE + source_offset
            if source < 0 or source + 4 > obj["virtual_size"]:
                raise ValueError("LE fixup source exceeds its object")
            duplicate_of = None
            for neighbor in range(source - 3, source + 4):
                previous = writes.get((owner, neighbor))
                if previous is not None:
                    if neighbor != source or previous[0] != relocated:
                        raise ValueError("LE overlapping fixup writes disagree")
                    duplicate_of = previous[1]
            original = original_images[owner][source:source + 4]
            # A word may span noncontiguous physical pages or end in BSS.
            # Claim one file offset only when all four bytes are contiguous
            # in the original file. Keep partial fragments explicit otherwise.
            fragments = []
            for byte_index in range(4):
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
            source_file_offset = fragments[0]["file_offset"] if len(fragments) == 1 and fragments[0]["size"] == 4 else None
            record = dict(index=len(fixups), page=logical_page + 1,
                          record_file_offset=record_offset, source_type="offset32",
                          source_flags=source_flags, target_flags=target_flags,
                          source_object=owner + 1, source_offset=source,
                          page_source_offset=source_offset,
                          address=obj["virtual_address"] + source,
                          linear_address=obj["virtual_address"] + source,
                          file_offset=source_file_offset, file_fragments=fragments,
                          zero_filled_bytes=4 - sum(part["size"] for part in fragments), width=4,
                          target_object=target_object, target_offset=target_offset,
                          target_address=relocated, original_bytes=original.hex(),
                          original_value=int.from_bytes(original, "little"),
                          relocated_value=relocated, applied=True, duplicate_of=duplicate_of)
            if duplicate_of is None:
                writes[(owner, source)] = (relocated, len(fixups))
                buffers[owner][source:source + 4] = relocated.to_bytes(4, "little")
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
    load_model = "Preferred LE object addresses with internal offset32 fixups; no runtime selectors or DOS extender execution"
    le = dict(header_offset=header_offset, header_fields=fields, cpu_type=cpu,
              operating_system=operating_system, byte_order="little", word_order="little",
              entrypoint=selected, declared_entrypoint=declared_entry,
              entry_object=start_object, entry_offset=fields["eip"],
              entrypoint_present=True, stack_object=stack_object, stack_address=stack_address,
              page_size=PAGE_SIZE, page_count=page_count, object_count=object_count,
              objects=objects, pages=pages, fixups=fixups, fixup_count=len(fixups),
              unique_fixup_writes=len(writes), file_backed_size=sum(obj["file_backed_size"] for obj in objects),
              mapped_size=total_size, zero_filled_size=sum(obj["zero_filled_size"] for obj in objects),
              load_model=load_model,
              fixup_original_value_model="Pre-fixup mapped bytes, including declared zero fill; file_fragments identify actual source bytes",
              warnings=[])
    metadata = dict(selected_image="le", mapping=load_model, source_sha256=hashlib.sha256(data).hexdigest(),
                    entrypoint_present=True, declared_entrypoint=declared_entry,
                    file_mappings=file_mappings, le=le)
    seed_source = "le_entry" if entry is None else "explicit_entry"
    return Image("LE", "x86", 32, selected, regions, [Seed(selected, "entry", seed_source)], metadata, source_bytes=data)


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
                             file_offset=mappings[0]["file_offset"] if contiguous else None,
                             file_size=sum(mapping["file_size"] for mapping in mappings) if contiguous else (0 if not mappings else None),
                             file_fragments=mappings, executable=obj["executable"], writable=obj["writable"]))
    result.update(format="LE", arch="x86", bits=32, file_mappings=image.metadata["file_mappings"], sections=sections)
    return result
