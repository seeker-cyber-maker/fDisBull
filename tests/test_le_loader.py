"""Authored LE fixtures; no game bytes are distributed with the test suite."""
import hashlib
import struct

import pytest

from fdisbull.le import inspect_le, load_le


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


def test_preferred_objects_internal_fixup_and_original_source_are_separate():
    source = le_file()
    image = load_le(source)
    assert (image.format, image.arch, image.bits, image.entry) == ("LE", "x86", 32, 0x10000)
    assert image.source_bytes == source
    assert image.metadata["source_sha256"] == hashlib.sha256(source).hexdigest()
    code, data = image.regions
    assert code.data[:6] == b"\xb8\x02\x00\x02\x00\xc3"
    assert data.data == b"DATA" + bytes(16)
    assert code.executable and not code.writable and not data.executable and data.writable
    fixup = image.metadata["le"]["fixups"][0]
    assert fixup["original_value"] == 0 and fixup["relocated_value"] == 0x20002
    assert source[fixup["file_offset"]:fixup["file_offset"] + 4] == bytes(4)
    assert image.metadata["selected_image"] == "le"
    assert image.seeds[0].source == "le_entry"
    assert image.metadata["le"]["stack_address"] == 0x20014


def test_inspection_reports_mappings_and_structures_without_embedded_code():
    result = inspect_le(le_file())
    assert result["format"] == "LE" and result["object_count"] == 2
    assert result["fixup_count"] == result["unique_fixup_writes"] == 1
    assert result["sections"][0]["virtual_address"] == 0x10000
    assert result["file_mappings"][1]["virtual_address"] == 0x20000
    assert "data" not in result["sections"][0]


def test_wide_target_offset_and_object_ordinal():
    record = struct.pack("<BBhHI", 7, 0x50, 1, 2, 0x10001)
    source = le_file(fixups=[record, b""], object_sizes=(22, 0x10020))
    image = load_le(source)
    assert image.regions[0].data[1:5] == struct.pack("<I", 0x30001)
    assert image.metadata["le"]["fixups"][0]["target_flags"] == 0x50


def test_cross_page_fixup_duplicate_is_applied_once_and_recorded_twice():
    code = b"\xc3" + bytes(4094) + b"\x11\x22\x33\x44" + bytes(20)
    first = struct.pack("<BBhBH", 7, 0, 4095, 2, 4)
    duplicate = struct.pack("<BBhBH", 7, 0, -1, 2, 4)
    source = le_file(code=code, fixups=[first, duplicate, b""])
    image = load_le(source)
    evidence = image.metadata["le"]
    assert image.regions[0].data[4095:4099] == struct.pack("<I", 0x20004)
    assert evidence["fixup_count"] == 2 and evidence["unique_fixup_writes"] == 1
    assert evidence["fixups"][1]["duplicate_of"] == 0
    assert evidence["fixups"][0]["original_bytes"] == "11223344"
    assert evidence["fixups"][1]["original_bytes"] == "11223344"


def test_fixup_provenance_does_not_claim_contiguous_file_bytes_across_permuted_pages():
    code = b"\xc3" + bytes(4094) + b"\x11\x22\x33\x44" + bytes(20)
    record = struct.pack("<BBhBH", 7, 0, 4095, 2, 4)
    source = bytearray(le_file(code=code, fixups=[record, b"", b""]))
    table = 0x80 + 196 + 48
    source[table + 4:table + 7] = (3).to_bytes(3, "big")
    source[table + 8:table + 11] = (2).to_bytes(3, "big")
    image = load_le(bytes(source))
    fixup = image.metadata["le"]["fixups"][0]
    assert fixup["file_offset"] is None and fixup["zero_filled_bytes"] == 0
    assert [fragment["size"] for fragment in fixup["file_fragments"]] == [1, 3]
    assert fixup["file_fragments"][0]["file_offset"] + 1 != fixup["file_fragments"][1]["file_offset"]
    section = inspect_le(bytes(source))["sections"][0]
    assert section["file_offset"] is None and section["file_size"] is None
    assert len(section["file_fragments"]) == 2


def test_fixup_into_bss_preserves_partial_file_provenance():
    record = struct.pack("<BBhBH", 7, 0, 2, 1, 0)
    image = load_le(le_file(fixups=[b"", record]))
    fixup = image.metadata["le"]["fixups"][0]
    assert image.regions[1].data[2:6] == struct.pack("<I", 0x10000)
    assert fixup["file_offset"] is None and fixup["zero_filled_bytes"] == 2
    assert len(fixup["file_fragments"]) == 1 and fixup["file_fragments"][0]["size"] == 2
    assert fixup["original_bytes"] == "54410000"


def test_zero_fill_page_has_no_file_mapping_and_short_physical_page_is_retained():
    source = le_file(fixups=[b"", b""], page_flags=[0, 3])
    image = load_le(source)
    assert image.regions[0].data[:6] == b"\xb8\0\0\0\0\xc3"
    assert image.regions[1].data == bytes(20)
    assert len(image.metadata["file_mappings"]) == 1
    assert image.metadata["le"]["pages"][1]["file_offset"] is None


def test_zero_page_count_object_is_allocated_as_bss():
    source = bytearray(le_file(fixups=[b"", b""]))
    # Redirect object 2's existing map entry to object 1, then make object 2 BSS.
    h = 0x80
    struct.pack_into("<I", source, h + 196, 8192)
    struct.pack_into("<I", source, h + 196 + 16, 2)
    struct.pack_into("<II", source, h + 196 + 24 + 12, 3, 0)
    image = load_le(bytes(source))
    assert image.regions[1].data == bytes(20)
    assert image.metadata["le"]["objects"][1]["file_backed_size"] == 0


def test_explicit_entry_is_an_executable_file_byte():
    source = le_file()
    assert load_le(source, entry=0x10005).seeds[0].source == "explicit_entry"
    for entry in (True, -1, 1 << 32, 0x20000, 0x1FFFF):
        with pytest.raises(ValueError, match="entry"):
            load_le(source, entry=entry)
    with pytest.raises(ValueError, match="file-backed"):
        load_le(le_file(object_sizes=(8192, 20)), entry=0x11000)


@pytest.mark.parametrize("source_flags,target_flags", [(2, 0), (6, 0), (8, 0), (0x27, 0), (7, 1), (7, 4), (7, 8), (7, 0x80)])
def test_unmodeled_fixup_encodings_fail_instead_of_leaving_raw_pointers(source_flags, target_flags):
    record = struct.pack("<BBhBH", source_flags, target_flags, 1, 2, 2)
    with pytest.raises(ValueError, match="unsupported fixup"):
        load_le(le_file(fixups=[record, b""]))


@pytest.mark.parametrize("offset,value,error", [
    (0x14, 0x100000, "budget"), (0x44, 0x100000, "budget"),
    (0x28, 8192, "4096"), (0x2C, 4097, "last-page"),
    (0x40, 0xFFFFFFF0, "bounds"), (0x74, 1, "imported"),
    (0x18, 3, "entry object"), (0x1C, 0x10000, "entry offset"),
    (0x24, 0x10000, "stack offset"), (0x20, 3, "stack object"),
])
def test_header_bounds_and_unsupported_profile_are_explicit(offset, value, error):
    source = bytearray(le_file())
    struct.pack_into("<I", source, 0x80 + offset, value)
    with pytest.raises(ValueError, match=error):
        load_le(bytes(source))


def test_source_and_target_fixups_must_fit_objects():
    for record, message in [
        (struct.pack("<BBhBH", 7, 0, -1, 2, 0), "source exceeds"),
        (struct.pack("<BBhBH", 7, 0, 1, 3, 0), "target object"),
        (struct.pack("<BBhBH", 7, 0, 1, 2, 21), "target offset"),
    ]:
        with pytest.raises(ValueError, match=message):
            load_le(le_file(fixups=[record, b""]))


def test_record_boundary_and_conflicting_writes_are_rejected():
    with pytest.raises(ValueError, match="page-table boundary"):
        load_le(le_file(fixups=[b"\x07\x00\x01", b""]))
    a = struct.pack("<BBhBH", 7, 0, 1, 2, 2)
    b = struct.pack("<BBhBH", 7, 0, 2, 2, 2)
    with pytest.raises(ValueError, match="overlapping fixup"):
        load_le(le_file(fixups=[a + b, b""]))


def test_truncated_page_and_overlapping_objects_fail():
    with pytest.raises(ValueError, match="enumerated page"):
        load_le(le_file()[:-1])
    with pytest.raises(ValueError, match="ranges overlap"):
        load_le(le_file(object_bases=(0x10000, 0x10010)))
    with pytest.raises(ValueError, match="16-bit"):
        load_le(le_file(object_flags=(0x45, 0x2043)))


def test_malformed_signatures_and_unsupported_page_encoding_fail():
    for source in (b"MZ", b"LX" + bytes(300), bytearray(le_file())):
        with pytest.raises(ValueError):
            load_le(source)
    with pytest.raises(ValueError, match="page encoding"):
        load_le(le_file(page_flags=[1, 0]))


def test_nonmonotonic_fixup_page_offsets_fail():
    source = bytearray(le_file())
    table = 0x80 + 196 + 48 + 8
    struct.pack_into("<I", source, table + 4, 0xFFFFFFFE)
    with pytest.raises(ValueError, match="monotonic"):
        load_le(bytes(source))
