"""Reproduce the v0.26 optional-LE-extent inspection probe entirely in memory.
Run with the selected fDisBull environment Python, e.g. python -I fixture-probe.py.
The authored fixture builder is from tests/test_le_loader.py of the reviewed repo.
No input files, projects or game bytes are created or modified.
"""
import json, struct, importlib.metadata
from fdisbull.le import load_le
from fdisbull.inspection import inspect_binary

def le_file(*, code=b"\xb8\0\0\0\0\xc3", data=b"DATA", fixups=None,
            object_sizes=None, page_flags=None, entry_offset=0,
            object_bases=(0x10000, 0x20000), object_flags=(0x2045, 0x2043)):
    """Two authored flat objects, one physical page each by default.

    The default fixup changes the immediate in `mov eax, 0` to object 2's
    base plus two. Explicit `fixups` are raw per-logical-page byte streams.
    Larger code can occupy several pages so signed cross-page fixups are real.
    """
    payloads = (code, data)
    counts = [max(1, (len(payload) + 4095) // 4096) for payload in payloads]
    total_pages = sum(counts)
    if object_sizes is None:
        object_sizes = tuple(len(payload) + 16 for payload in payloads)
    if fixups is None:
        fixups = [struct.pack("<BBhBH", 7, 0, 1, 2, 2)] + [b""] * (total_pages - 1)
    if page_flags is None:
        page_flags = [0] * total_pages
    assert len(fixups) == len(page_flags) == total_pages
    header_offset = 0x80
    object_table = 196
    page_table = object_table + 48
    fixup_page_table = page_table + total_pages * 4
    fixup_record_table = fixup_page_table + (total_pages + 1) * 4
    record_bytes = b"".join(fixups)
    data_pages = (header_offset + fixup_record_table + len(record_bytes) + 15) & ~15
    physical_pages = []
    page_map = bytearray()
    logical_page = 0
    for payload, count in zip(payloads, counts):
        for local_page in range(count):
            part = payload[local_page * 4096:(local_page + 1) * 4096]
            flags = page_flags[logical_page]
            logical_page += 1
            if flags == 3:
                page_map += b"\0\0\0\x03"
            else:
                physical_pages.append(part)
                page_map += len(physical_pages).to_bytes(3, "big") + bytes([flags])
    last_size = len(physical_pages[-1]) or 4096
    image = bytearray(data_pages)
    # A valid small classic DOS stub plus an independent secondary header.
    struct.pack_into("<14H", image, 0, 0x5A4D, 128, 1, 0, 4, 0, 0xFFFF, 0, 32, 0, 0, 0, 64, 0)
    struct.pack_into("<I", image, 60, header_offset)
    image[64] = 0xC3
    image[header_offset:header_offset + 2] = b"LE"
    struct.pack_into("<HH", image, header_offset + 8, 2, 1)
    for offset, value in {
        0x10: 0x200, 0x14: total_pages, 0x18: 1, 0x1C: entry_offset,
        0x20: 2, 0x24: object_sizes[1], 0x28: 4096, 0x2C: last_size,
        0x30: (total_pages + 1) * 4 + len(record_bytes),
        0x40: object_table, 0x44: 2, 0x48: page_table,
        0x68: fixup_page_table, 0x6C: fixup_record_table, 0x80: data_pages,
    }.items():
        struct.pack_into("<I", image, header_offset + offset, value)
    first = 1
    for index, (size, base, flags, count) in enumerate(zip(object_sizes, object_bases, object_flags, counts)):
        struct.pack_into("<6I", image, header_offset + object_table + 24 * index,
                         size, base, flags, first, count, 0)
        first += count
    image[header_offset + page_table:header_offset + page_table + len(page_map)] = page_map
    offset = 0
    for index, records in enumerate([*fixups, b""]):
        struct.pack_into("<I", image, header_offset + fixup_page_table + 4 * index, offset)
        offset += len(records)
    image[header_offset + fixup_record_table:header_offset + fixup_record_table + len(record_bytes)] = record_bytes
    for index, payload in enumerate(physical_pages):
        size = last_size if index == len(physical_pages) - 1 else 4096
        image += payload.ljust(size, b"\0")
    return bytes(image)

mutations = {'resident_names_outside_file': {88: 4294967280}, 'entry_table_outside_file': {92: 4294967280}, 'resource_table_outside_file': {80: 4294967280, 84: 1}, 'directive_table_outside_file': {96: 4294967280, 100: 1}, 'debug_outside_file': {152: 4294967280, 156: 16}, 'nonresident_names_outside_file': {136: 4294967280, 140: 16}, 'loader_extent_outside_file': {56: 4294967280}, 'page_checksums_outside_file': {124: 4294967280}}
fixture=le_file()
results=[]
for name,fields in mutations.items():
    source=bytearray(fixture)
    for offset,value in fields.items():
        struct.pack_into('<I',source,0x80+offset,value)
    try:
        image=load_le(bytes(source)); inspected=inspect_binary(bytes(source))
        results.append({'case':name,'load_accepted':True,'le_warnings':image.metadata['le']['warnings'],'inspect_warnings':inspected['warnings'],'exports':inspected['exports']})
    except Exception as error:
        results.append({'case':name,'load_accepted':False,'error':str(error)})
print(json.dumps({'version':importlib.metadata.version('fdisbull'),'fixture_bytes':len(fixture),'results':results},indent=2))
