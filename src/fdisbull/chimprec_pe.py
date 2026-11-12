"""Bounded PE32/PE32+ import-directory reconstruction for captured images.

This module writes analysis reconstructions.  It does not attach to a process,
recover missing exports or reproduce the exact pre-packer file.  All import
identities and thunk decisions are supplied by the caller or by CHimpREC's
qualified recovery result.
"""

from __future__ import annotations

import struct

_MAX_PE = 512 * 1024 * 1024
_MAX_SECTIONS = 4096
_MAX_IMPORTS = 1_000_000


def _align(value, alignment):
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("PE alignment must be a positive power of two")
    return (value + alignment - 1) & ~(alignment - 1)


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def parse_pe_layout(data: bytes) -> dict:
    """Parse the PE fields needed by the reconstruction writer."""
    if not isinstance(data, (bytes, bytearray)) or not 0x100 <= len(data) <= _MAX_PE:
        raise ValueError("PE image must be 256 bytes to 512 MiB")
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ValueError("captured image is not an MZ/PE image")
    pe = _u32(data, 0x3C)
    if pe < 0x40 or pe + 24 > len(data) or data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("captured image has no valid PE signature")
    coff = pe + 4
    machine, section_count = struct.unpack_from("<HH", data, coff)
    optional_size = _u16(data, coff + 16)
    characteristics = _u16(data, coff + 18)
    optional = coff + 20
    if section_count > _MAX_SECTIONS or optional + optional_size > len(data):
        raise ValueError("PE section or optional-header bounds are invalid")
    magic = _u16(data, optional)
    if magic == 0x10B:
        bits, minimum, imagebase_offset, directory_offset, count_offset = (
            32,
            96,
            28,
            96,
            92,
        )
    elif magic == 0x20B:
        bits, minimum, imagebase_offset, directory_offset, count_offset = (
            64,
            112,
            24,
            112,
            108,
        )
    else:
        raise ValueError("PE optional-header magic must be PE32 or PE32+")
    if optional_size < minimum:
        raise ValueError("PE optional header is too small")
    image_base = (
        _u64(data, optional + imagebase_offset)
        if bits == 64
        else _u32(data, optional + imagebase_offset)
    )
    entry_rva = _u32(data, optional + 16)
    section_alignment = _u32(data, optional + 32)
    file_alignment = _u32(data, optional + 36)
    size_image = _u32(data, optional + 56)
    size_headers = _u32(data, optional + 60)
    checksum_offset = optional + 64
    dll_characteristics_offset = optional + 70
    number_directories = min(
        _u32(data, optional + count_offset),
        max(0, (optional_size - directory_offset) // 8),
    )
    section_table = optional + optional_size
    if section_table + section_count * 40 > len(data):
        raise ValueError("PE section table is truncated")
    sections = []
    previous_va = 0
    for index in range(section_count):
        offset = section_table + index * 40
        raw_name = bytes(data[offset : offset + 8])
        name = raw_name.split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        section_characteristics = _u32(data, offset + 36)
        if virtual_address < previous_va:
            raise ValueError("PE sections are not ordered by virtual address")
        previous_va = virtual_address
        sections.append(
            {
                "index": index,
                "name": name,
                "header_offset": offset,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
                "characteristics": section_characteristics,
            }
        )
    return {
        "pe_offset": pe,
        "coff_offset": coff,
        "machine": machine,
        "characteristics": characteristics,
        "section_count": section_count,
        "optional_offset": optional,
        "optional_size": optional_size,
        "bits": bits,
        "image_base": image_base,
        "entry_rva": entry_rva,
        "section_alignment": section_alignment,
        "file_alignment": file_alignment,
        "size_image": size_image,
        "size_headers": size_headers,
        "checksum_offset": checksum_offset,
        "dll_characteristics_offset": dll_characteristics_offset,
        "directory_offset": optional + directory_offset,
        "directory_count": number_directories,
        "section_table": section_table,
        "sections": sections,
    }


def _directory(layout, data, index):
    if index >= layout["directory_count"]:
        return (0, 0)
    return struct.unpack_from("<II", data, layout["directory_offset"] + index * 8)


def _set_directory(buffer, layout, index, rva, size):
    if index < layout["directory_count"]:
        struct.pack_into(
            "<II", buffer, layout["directory_offset"] + index * 8, rva, size
        )


def _rva_to_file(layout, rva, size=1):
    if rva < layout["size_headers"] and rva + size <= layout["size_headers"]:
        return rva
    for section in layout["sections"]:
        extent = max(section["virtual_size"], section["raw_size"])
        if (
            section["virtual_address"] <= rva
            and rva + size <= section["virtual_address"] + extent
        ):
            delta = rva - section["virtual_address"]
            if delta + size > section["raw_size"]:
                return None
            return section["raw_offset"] + delta
    return None


def pe_checksum(data: bytes, checksum_offset: int) -> int:
    """Compute the PE checksum with the checksum field treated as zero."""
    total = 0
    length = len(data)
    for offset in range(0, length, 2):
        if checksum_offset <= offset < checksum_offset + 4:
            word = 0
        elif offset + 1 < length:
            word = data[offset] | data[offset + 1] << 8
        else:
            word = data[offset]
        total = (total + word) & 0xFFFFFFFF
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + length) & 0xFFFFFFFF


def _selected_imports(plan, bits, image_base):
    if not isinstance(plan, list) or len(plan) > _MAX_IMPORTS:
        raise ValueError(
            "import plan must be a list within the one-million-entry limit"
        )
    width = bits // 8
    normalized = []
    for group in plan:
        if not isinstance(group, dict):
            raise ValueError("import plan groups must be dictionaries")
        module = group.get("module")
        entries = group.get("entries")
        if (
            not isinstance(module, str)
            or not module
            or len(module) > 4096
            or "\x00" in module
        ):
            raise ValueError("import module name is invalid")
        if not isinstance(entries, list) or not entries:
            raise ValueError("import group must contain entries")
        normalized_entries, previous = [], None
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("import entries must be dictionaries")
            address = entry.get("address")
            if (
                isinstance(address, bool)
                or not isinstance(address, int)
                or address < image_base
            ):
                raise ValueError("import IAT address is invalid")
            if previous is not None and address != previous + width:
                raise ValueError("each import group must occupy contiguous IAT cells")
            previous = address
            name, ordinal = entry.get("name"), entry.get("ordinal")
            if name is None and ordinal is None:
                raise ValueError("import must have a name or ordinal")
            if name is not None and (
                not isinstance(name, str)
                or not name
                or len(name) > 65535
                or "\x00" in name
            ):
                raise ValueError("import name is invalid")
            if ordinal is not None and (
                isinstance(ordinal, bool)
                or not isinstance(ordinal, int)
                or not 0 <= ordinal <= 0xFFFF
            ):
                raise ValueError("import ordinal is invalid")
            normalized_entries.append(
                {
                    "address": address,
                    "name": name,
                    "ordinal": ordinal,
                    "forwarder": entry.get("forwarder"),
                }
            )
        normalized.append({"module": module, "entries": normalized_entries})
    if sum(len(group["entries"]) for group in normalized) > _MAX_IMPORTS:
        raise ValueError("import plan exceeds the one-million-entry limit")
    return normalized


def _build_import_section(plan, bits, image_base, section_rva):
    width = bits // 8
    ordinal_flag = 1 << (bits - 1)
    descriptor_size = (len(plan) + 1) * 20
    content = bytearray(descriptor_size)
    cursor = descriptor_size

    def allocate(payload, alignment=1):
        nonlocal cursor
        cursor = _align(cursor, alignment)
        start = cursor
        content.extend(b"\0" * max(0, start + len(payload) - len(content)))
        content[start : start + len(payload)] = payload
        cursor = start + len(payload)
        return section_rva + start

    modules = []
    for group in plan:
        name_rva = allocate(group["module"].encode("ascii", "strict") + b"\0")
        thunk_values = []
        for entry in group["entries"]:
            if entry["name"] is not None:
                import_rva = allocate(
                    b"\0\0" + entry["name"].encode("ascii", "strict") + b"\0", 2
                )
                thunk_values.append(import_rva)
            else:
                thunk_values.append(ordinal_flag | entry["ordinal"])
        encoded = b"".join(
            value.to_bytes(width, "little") for value in [*thunk_values, 0]
        )
        ilt_rva = allocate(encoded, width)
        first_thunk = group["entries"][0]["address"] - image_base
        modules.append(
            {
                "module": group["module"],
                "name_rva": name_rva,
                "ilt_rva": ilt_rva,
                "first_thunk": first_thunk,
                "thunks": thunk_values,
                "entries": group["entries"],
            }
        )
    for index, module in enumerate(modules):
        struct.pack_into(
            "<IIIII",
            content,
            index * 20,
            module["ilt_rva"],
            0,
            0,
            module["name_rva"],
            module["first_thunk"],
        )
    return bytes(content[:cursor]), modules, descriptor_size


def rebuild_pe_imports(
    captured_image: bytes,
    import_plan: list[dict],
    *,
    oep: int,
    source_layout: str = "mapped",
    section_name: str = ".reimp",
    fixed_base: bool = True,
    preserve_overlay: bool = False,
) -> dict:
    """Rebuild a PE import directory around caller-qualified imports.

    ``captured_image`` may be a mapped module image (sections at their RVAs) or a
    file-layout PE. The original IAT addresses are preserved; a new import lookup
    table and descriptors are written to a new section.  The result is an
    unsigned analysis reconstruction, not an exact pre-packer original.
    """
    layout = parse_pe_layout(captured_image)
    if source_layout not in ("mapped", "file"):
        raise ValueError("source_layout must be mapped or file")
    if (
        not isinstance(section_name, str)
        or not section_name
        or len(section_name.encode("ascii", "strict")) > 8
    ):
        raise ValueError("PE section name must be 1..8 ASCII bytes")
    if isinstance(oep, bool) or not isinstance(oep, int):
        raise ValueError("OEP must be an integer virtual address")
    if not layout["image_base"] <= oep < layout["image_base"] + layout["size_image"]:
        raise ValueError("OEP must lie inside the captured PE image")
    plan = _selected_imports(import_plan, layout["bits"], layout["image_base"])
    if not plan:
        raise ValueError("at least one qualified import group is required")
    file_alignment, section_alignment = (
        layout["file_alignment"],
        layout["section_alignment"],
    )
    if not 0x200 <= file_alignment <= 0x10000 or file_alignment & (file_alignment - 1):
        raise ValueError("unsupported PE file alignment")
    if not section_alignment or section_alignment & (section_alignment - 1):
        raise ValueError("unsupported PE section alignment")

    new_section_va = _align(
        max(
            (
                section["virtual_address"]
                + max(section["virtual_size"], section["raw_size"])
                for section in layout["sections"]
            ),
            default=layout["size_headers"],
        ),
        section_alignment,
    )
    import_content, modules, import_directory_size = _build_import_section(
        plan, layout["bits"], layout["image_base"], new_section_va
    )
    new_header_end = layout["section_table"] + (layout["section_count"] + 1) * 40
    new_size_headers = _align(
        max(layout["size_headers"], new_header_end), file_alignment
    )
    output = bytearray(new_size_headers)
    header_copy = min(len(captured_image), layout["size_headers"], new_size_headers)
    output[:header_copy] = captured_image[:header_copy]

    rebuilt_sections = []
    raw_cursor = new_size_headers
    original_raw_end = 0
    for section in layout["sections"]:
        if source_layout == "mapped":
            source_offset = section["virtual_address"]
            content_size = max(section["virtual_size"], section["raw_size"])
        else:
            source_offset = section["raw_offset"]
            content_size = section["raw_size"]
            original_raw_end = max(
                original_raw_end, section["raw_offset"] + section["raw_size"]
            )
        if source_offset + content_size > len(captured_image):
            raise ValueError(
                f"captured section {section['name']!r} exceeds supplied image bytes"
            )
        raw_size = _align(content_size, file_alignment) if content_size else 0
        raw_offset = raw_cursor if raw_size else 0
        if raw_size:
            output.extend(b"\0" * raw_size)
            output[raw_offset : raw_offset + content_size] = captured_image[
                source_offset : source_offset + content_size
            ]
            raw_cursor += raw_size
        rebuilt_sections.append(
            {**section, "raw_offset": raw_offset, "raw_size": raw_size}
        )

    new_raw_size = _align(len(import_content), file_alignment)
    new_raw_offset = raw_cursor
    output.extend(b"\0" * new_raw_size)
    output[new_raw_offset : new_raw_offset + len(import_content)] = import_content
    raw_cursor += new_raw_size
    rebuilt_sections.append(
        {
            "index": layout["section_count"],
            "name": section_name,
            "virtual_size": len(import_content),
            "virtual_address": new_section_va,
            "raw_size": new_raw_size,
            "raw_offset": new_raw_offset,
            "characteristics": 0x40000040,
        }
    )

    if preserve_overlay and source_layout == "file":
        overlay_start = max(original_raw_end, layout["size_headers"])
        if overlay_start < len(captured_image):
            output.extend(captured_image[overlay_start:])

    # Rewrite all section headers because raw data was laid out afresh.
    for index, section in enumerate(rebuilt_sections):
        offset = layout["section_table"] + index * 40
        name = section["name"].encode("ascii", "strict")[:8].ljust(8, b"\0")
        output[offset : offset + 8] = name
        struct.pack_into(
            "<IIIIIIHHI",
            output,
            offset + 8,
            section["virtual_size"],
            section["virtual_address"],
            section["raw_size"],
            section["raw_offset"],
            0,
            0,
            0,
            0,
            section["characteristics"],
        )
    struct.pack_into("<H", output, layout["coff_offset"] + 2, len(rebuilt_sections))
    characteristics = layout["characteristics"]
    if fixed_base:
        characteristics |= 0x0001  # IMAGE_FILE_RELOCS_STRIPPED
    struct.pack_into("<H", output, layout["coff_offset"] + 18, characteristics)
    struct.pack_into(
        "<I", output, layout["optional_offset"] + 16, oep - layout["image_base"]
    )
    initialized = _u32(output, layout["optional_offset"] + 8)
    if initialized + new_raw_size > 0xFFFFFFFF:
        raise ValueError("rebuilt initialized-data size overflows PE32 fields")
    struct.pack_into(
        "<I", output, layout["optional_offset"] + 8, initialized + new_raw_size
    )
    struct.pack_into(
        "<I",
        output,
        layout["optional_offset"] + 56,
        _align(new_section_va + len(import_content), section_alignment),
    )
    struct.pack_into("<I", output, layout["optional_offset"] + 60, new_size_headers)
    if fixed_base:
        dll_characteristics = (
            _u16(output, layout["dll_characteristics_offset"]) & ~0x0040
        )
        struct.pack_into(
            "<H", output, layout["dll_characteristics_offset"], dll_characteristics
        )
        _set_directory(output, layout, 5, 0, 0)  # relocations
    _set_directory(output, layout, 1, new_section_va, import_directory_size)
    _set_directory(
        output, layout, 4, 0, 0
    )  # Authenticode certificate is invalid after rebuilding.
    _set_directory(output, layout, 11, 0, 0)  # Bound imports are stale.

    # Patch original IAT cells to names/ordinals using the new output mapping.
    output_layout = parse_pe_layout(bytes(output))
    iat_rvas = []
    for module in modules:
        for entry, thunk in zip(module["entries"], module["thunks"]):
            rva = entry["address"] - layout["image_base"]
            file_offset = _rva_to_file(output_layout, rva, layout["bits"] // 8)
            if file_offset is None:
                raise ValueError(
                    f"qualified IAT cell {entry['address']:#x} is not file-backed"
                )
            output[file_offset : file_offset + layout["bits"] // 8] = thunk.to_bytes(
                layout["bits"] // 8, "little"
            )
            iat_rvas.append(rva)
    if iat_rvas:
        _set_directory(
            output,
            layout,
            12,
            min(iat_rvas),
            max(iat_rvas) - min(iat_rvas) + layout["bits"] // 8,
        )
    struct.pack_into("<I", output, layout["checksum_offset"], 0)
    checksum = pe_checksum(bytes(output), layout["checksum_offset"])
    struct.pack_into("<I", output, layout["checksum_offset"], checksum)

    final = bytes(output)
    final_layout = parse_pe_layout(final)
    imports = inspect_pe_imports(final)
    expected_count = sum(len(group["entries"]) for group in plan)
    if len(imports) != expected_count:
        raise ValueError("rebuilt PE import validation count mismatch")
    receipt = {
        "format": "fdisbull-chimprec-pe-rebuild-1",
        "bits": layout["bits"],
        "image_base": layout["image_base"],
        "oep": oep,
        "source_layout": source_layout,
        "fixed_base": bool(fixed_base),
        "section": section_name,
        "import_groups": len(plan),
        "import_count": expected_count,
        "output_size": len(final),
        "checksum": checksum,
        "security_directory_cleared": True,
        "bound_imports_cleared": True,
        "relocations_cleared": bool(fixed_base),
        "exact_prepacker_reconstruction": False,
    }
    return {"image": final, "receipt": receipt, "imports": imports}


def inspect_pe_imports(data: bytes) -> list[dict]:
    """Read a bounded PE import directory for validation and tests."""
    layout = parse_pe_layout(data)
    import_rva, import_size = _directory(layout, data, 1)
    if not import_rva or not import_size:
        return []
    descriptor = _rva_to_file(layout, import_rva, 20)
    if descriptor is None:
        raise ValueError("PE import directory is not file-backed")
    width = layout["bits"] // 8
    ordinal_flag = 1 << (layout["bits"] - 1)
    records = []
    for descriptor_index in range(min(_MAX_SECTIONS * 16, import_size // 20 + 1)):
        offset = descriptor + descriptor_index * 20
        if offset + 20 > len(data):
            raise ValueError("PE import descriptors are truncated")
        oft, _, _, name_rva, first_thunk = struct.unpack_from("<IIIII", data, offset)
        if not any((oft, name_rva, first_thunk)):
            return records
        name_offset = _rva_to_file(layout, name_rva, 1)
        if name_offset is None:
            raise ValueError("PE import DLL name is not file-backed")
        end = data.find(b"\0", name_offset, min(len(data), name_offset + 4097))
        if end < 0:
            raise ValueError("PE import DLL name is unterminated")
        module = data[name_offset:end].decode("ascii", "strict")
        lookup_rva = oft or first_thunk
        for index in range(_MAX_IMPORTS):
            lookup_offset = _rva_to_file(layout, lookup_rva + index * width, width)
            if lookup_offset is None:
                raise ValueError("PE import lookup table is not file-backed")
            value = int.from_bytes(
                data[lookup_offset : lookup_offset + width], "little"
            )
            if not value:
                break
            record = {
                "module": module,
                "iat_rva": first_thunk + index * width,
                "name": None,
                "ordinal": None,
            }
            if value & ordinal_flag:
                record["ordinal"] = value & 0xFFFF
            else:
                name_entry = _rva_to_file(layout, value, 3)
                if name_entry is None:
                    raise ValueError("PE import-by-name record is not file-backed")
                string_start = name_entry + 2
                string_end = data.find(
                    b"\0", string_start, min(len(data), string_start + 65536)
                )
                if string_end < 0:
                    raise ValueError("PE import name is unterminated")
                record["name"] = data[string_start:string_end].decode("ascii", "strict")
            records.append(record)
        else:
            raise ValueError("PE import table exceeds the one-million-entry limit")
    raise ValueError(
        "PE import descriptors lack a terminator within their declared size"
    )


def regions_from_mapped_pe(data: bytes):
    """Create Region records from a mapped PE image without classifying all bytes as code."""
    from .model import Region

    layout = parse_pe_layout(data)
    regions = []
    header_size = min(layout["size_headers"], len(data))
    regions.append(
        Region(
            "PE headers", layout["image_base"], bytes(data[:header_size]), False, False
        )
    )
    for section in layout["sections"]:
        size = max(section["virtual_size"], section["raw_size"])
        start = section["virtual_address"]
        if start + size > len(data):
            raise ValueError(f"mapped section {section['name']!r} exceeds capture")
        flags = section["characteristics"]
        regions.append(
            Region(
                section["name"],
                layout["image_base"] + start,
                bytes(data[start : start + size]),
                bool(flags & 0x20000000),
                bool(flags & 0x80000000),
            )
        )
    return layout, regions


def rebuild_pe_file(
    source,
    capture,
    plan,
    output,
    *,
    entry_rva: int,
    section_name: str = ".reimp",
    fixed_base: bool = True,
) -> dict:
    """Rebuild a captured PE from a reviewed ``chimprec-import-plan-1`` file.

    This plan-file entry point is backed by the bounded modular writer.  It is
    additive to :func:`rebuild_captured_pe`; it refuses to overwrite output and
    writes the receipt beside the rebuilt image.
    """
    import json
    from pathlib import Path
    from .chimprec_pe_writer import rebuild_pe_image

    source, capture, plan, output = map(Path, (source, capture, plan, output))
    if output.exists():
        raise FileExistsError(output)
    document = json.loads(plan.read_text(encoding="utf-8"))
    rebuilt, receipt = rebuild_pe_image(
        source.read_bytes(),
        capture.read_bytes(),
        document,
        entry_rva=entry_rva,
        section_name=section_name,
        fixed_base=fixed_base,
        capture_metadata=document.get("capture_metadata"),
    )
    output.write_bytes(rebuilt)
    receipt_path = output.with_suffix(output.suffix + ".chimprec.json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {**receipt, "output": str(output), "receipt": str(receipt_path)}


def _main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original packed PE container")
    parser.add_argument("capture", type=Path, help="coherent mapped image bytes, RVA zero at file offset zero")
    parser.add_argument("plan", type=Path, help="reviewed chimprec-import-plan-1 JSON")
    parser.add_argument("output", type=Path, help="new output path; must not exist")
    parser.add_argument("--entry-rva", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--section-name", default=".reimp")
    args = parser.parse_args(argv)
    result = rebuild_pe_file(args.source, args.capture, args.plan, args.output,
                             entry_rva=args.entry_rva, section_name=args.section_name)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
