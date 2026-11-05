"""Bounded PE32/PE32+ import-directory reconstruction for captured images.

The writer consumes a source PE container, a coherent mapped-memory capture,
and a reviewed :mod:`fdisbull.chimprec_plan` document.  It preserves the
caller-selected import slots, restores their thunk cells, appends a deterministic
import section, and writes an unsigned analysis reconstruction.  It does not
attach to a process, discover modules, recover missing exports, or claim that a
structurally valid image starts on Windows.
"""

from __future__ import annotations

import struct

from .chimprec_pe_image import (
    _MAX_FILE,
    _MAX_IMAGE,
    _align,
    _normalize_capture,
    _sha256,
    map_pe_file,
    parse_pe,
)
from .chimprec_pe_imports import (
    _checksum,
    _normalize_plan,
    parse_imports,
)

_IMAGE_FILE_RELOCS_STRIPPED = 0x0001
_IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE = 0x0040
_IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
_IMAGE_SCN_MEM_READ = 0x40000000
_DIR_IMPORT = 1
_DIR_SECURITY = 4
_DIR_BASERELOC = 5
_DIR_BOUND_IMPORT = 11
_DIR_IAT = 12


def _set_directory(
    buffer: bytearray, pe: dict, index: int, rva: int, size: int
) -> None:
    if index >= pe["directory_count"]:
        return
    offset = pe["optional_offset"] + pe["directory_offset"] + index * 8
    struct.pack_into("<II", buffer, offset, rva, size)


def _import_section(
    groups: list[dict], bits: int, section_rva: int, ordinal_flag: int
) -> tuple[bytes, list[dict], int]:
    """Build descriptors plus their ILT and name payloads.

    The descriptor area is reserved first so every descriptor has a stable
    offset in the new section.  All payloads are appended after it in a
    deterministic module/entry order.
    """
    width = bits // 8
    descriptor_size = (len(groups) + 1) * 20
    content = bytearray(descriptor_size)
    modules = []

    def allocate(payload: bytes, alignment: int = 1) -> int:
        while len(content) % alignment:
            content.append(0)
        rva = section_rva + len(content)
        content.extend(payload)
        return rva

    for group in groups:
        module = group["module"]
        name_rva = allocate(module.encode("ascii") + b"\0")
        thunks = []
        for entry in group["entries"]:
            if entry["name"] is not None:
                thunks.append(
                    allocate(b"\0\0" + entry["name"].encode("ascii") + b"\0", 2)
                )
            else:
                thunks.append(ordinal_flag | entry["ordinal"])
        ilt = b"".join(thunk.to_bytes(width, "little") for thunk in [*thunks, 0])
        ilt_rva = allocate(ilt, width)
        modules.append(
            {
                "module": module,
                "name_rva": name_rva,
                "ilt_rva": ilt_rva,
                "first_thunk": group["entries"][0]["slot_rva"],
                "thunks": thunks,
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
    return bytes(content), modules, descriptor_size


def _output_file_offset(sections: list[dict], rva: int, size: int) -> int:
    for section in sections:
        if section["rva"] <= rva and rva + size <= section["rva"] + section["raw_size"]:
            return section["raw_offset"] + (rva - section["rva"])
    raise ValueError(f"IAT slot RVA {rva:#x} is not file-backed in the rebuilt image")


def rebuild_pe_image(
    source: bytes,
    capture: bytes,
    document: dict,
    *,
    entry_rva: int,
    section_name: str = ".reimp",
    fixed_base: bool = True,
    capture_metadata: dict | None = None,
) -> tuple[bytes, dict]:
    """Rebuild a captured PE around a reviewed import plan.

    ``source`` supplies the PE headers and section layout.  ``capture`` is the
    coherent mapped image: section virtual addresses are also its byte offsets.
    ``entry_rva`` is the qualified original entry point relative to the image
    base.  The returned bytes use ordinary file-layout section offsets.
    """
    if not isinstance(source, (bytes, bytearray)) or len(source) > _MAX_FILE:
        raise ValueError("source PE must be bytes no larger than 512 MiB")
    if not isinstance(capture, (bytes, bytearray)) or len(capture) > _MAX_IMAGE:
        raise ValueError("captured image must be bytes no larger than 512 MiB")
    pe = parse_pe(bytes(source))
    image = _normalize_capture(bytes(capture), pe)
    if isinstance(entry_rva, bool) or not isinstance(entry_rva, int):
        raise ValueError("entry RVA must be an integer")
    if not 0 <= entry_rva < pe["size_of_image"]:
        raise ValueError("entry RVA must lie inside the source SizeOfImage")
    if (
        not isinstance(section_name, str)
        or not section_name
        or len(section_name.encode("ascii", "strict")) > 8
    ):
        raise ValueError("PE section name must be 1..8 ASCII bytes")
    groups, flat = _normalize_plan(document, pe)
    if not groups:
        raise ValueError("at least one qualified import group is required")
    if not flat:
        raise ValueError("at least one qualified import is required")
    if pe["file_alignment"] <= 0 or pe["file_alignment"] & (pe["file_alignment"] - 1):
        raise ValueError("FileAlignment must be a power of two")
    if pe["section_alignment"] <= 0 or pe["section_alignment"] & (
        pe["section_alignment"] - 1
    ):
        raise ValueError("SectionAlignment must be a power of two")

    new_section_rva = _align(
        max(
            (
                section["rva"] + max(section["virtual_size"], section["raw_size"])
                for section in pe["sections"]
            ),
            default=pe["size_of_headers"],
        ),
        pe["section_alignment"],
    )
    import_content, modules, import_directory_size = _import_section(
        groups, pe["bits"], new_section_rva, pe["ordinal_flag"]
    )
    new_header_end = pe["section_table"] + (len(pe["sections"]) + 1) * 40
    new_size_headers = _align(
        max(pe["size_of_headers"], new_header_end), pe["file_alignment"]
    )
    if new_size_headers > len(source):
        # Headers may have grown, but the source header bytes remain the only
        # legitimate prefix.  The new section table area is zero-filled.
        pass
    output = bytearray(new_size_headers)
    header_copy = min(len(source), pe["size_of_headers"], new_size_headers)
    output[:header_copy] = source[:header_copy]

    rebuilt_sections = []
    raw_cursor = new_size_headers
    for section in pe["sections"]:
        content_size = max(section["virtual_size"], section["raw_size"])
        if section["rva"] + content_size > len(image):
            raise ValueError(
                f"captured section {section['name']!r} exceeds mapped image"
            )
        content = image[section["rva"] : section["rva"] + content_size]
        raw_size = _align(content_size, pe["file_alignment"]) if content_size else 0
        raw_offset = raw_cursor if raw_size else 0
        if raw_size:
            output.extend(b"\0" * raw_size)
            output[raw_offset : raw_offset + content_size] = content
            raw_cursor += raw_size
        rebuilt_sections.append(
            {**section, "raw_offset": raw_offset, "raw_size": raw_size}
        )

    new_raw_size = _align(len(import_content), pe["file_alignment"])
    new_raw_offset = raw_cursor
    output.extend(b"\0" * new_raw_size)
    output[new_raw_offset : new_raw_offset + len(import_content)] = import_content
    rebuilt_sections.append(
        {
            "index": len(pe["sections"]),
            "name": section_name,
            "virtual_size": len(import_content),
            "rva": new_section_rva,
            "raw_size": new_raw_size,
            "raw_offset": new_raw_offset,
            "mapped_size": len(import_content),
            "characteristics": _IMAGE_SCN_CNT_INITIALIZED_DATA | _IMAGE_SCN_MEM_READ,
        }
    )

    for index, section in enumerate(rebuilt_sections):
        offset = pe["section_table"] + index * 40
        output[offset : offset + 8] = (
            section["name"].encode("ascii")[:8].ljust(8, b"\0")
        )
        struct.pack_into(
            "<IIIIIIHHI",
            output,
            offset + 8,
            section["virtual_size"],
            section["rva"],
            section["raw_size"],
            section["raw_offset"],
            0,
            0,
            0,
            0,
            section["characteristics"],
        )
    struct.pack_into("<H", output, pe["pe_offset"] + 6, len(rebuilt_sections))
    characteristics = pe["coff_characteristics"]
    if fixed_base:
        characteristics |= _IMAGE_FILE_RELOCS_STRIPPED
    struct.pack_into("<H", output, pe["pe_offset"] + 22, characteristics)
    struct.pack_into("<I", output, pe["optional_offset"] + 16, entry_rva)
    initialized = struct.unpack_from("<I", output, pe["optional_offset"] + 8)[0]
    if initialized + new_raw_size > 0xFFFFFFFF:
        raise ValueError("rebuilt initialized-data size overflows PE32 fields")
    struct.pack_into(
        "<I", output, pe["optional_offset"] + 8, initialized + new_raw_size
    )
    struct.pack_into(
        "<I",
        output,
        pe["optional_offset"] + 56,
        _align(new_section_rva + len(import_content), pe["section_alignment"]),
    )
    struct.pack_into("<I", output, pe["optional_offset"] + 60, new_size_headers)
    if fixed_base:
        dll_offset = pe["optional_offset"] + 70
        dll_characteristics = struct.unpack_from("<H", output, dll_offset)[0]
        struct.pack_into(
            "<H",
            output,
            dll_offset,
            dll_characteristics & ~_IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE,
        )
        _set_directory(output, pe, _DIR_BASERELOC, 0, 0)
    _set_directory(output, pe, _DIR_IMPORT, new_section_rva, import_directory_size)
    _set_directory(output, pe, _DIR_SECURITY, 0, 0)
    _set_directory(output, pe, _DIR_BOUND_IMPORT, 0, 0)

    width = pe["bits"] // 8
    iat_rvas = []
    for module in modules:
        for entry, thunk in zip(module["entries"], module["thunks"]):
            offset = _output_file_offset(rebuilt_sections, entry["slot_rva"], width)
            output[offset : offset + width] = thunk.to_bytes(width, "little")
            iat_rvas.append(entry["slot_rva"])
    if iat_rvas:
        _set_directory(
            output,
            pe,
            _DIR_IAT,
            min(iat_rvas),
            max(iat_rvas) - min(iat_rvas) + width,
        )

    checksum_offset = pe["optional_offset"] + 64
    struct.pack_into("<I", output, checksum_offset, 0)
    checksum = _checksum(bytes(output), checksum_offset)
    struct.pack_into("<I", output, checksum_offset, checksum)
    final = bytes(output)

    final_pe = parse_pe(final)
    if final_pe["entry_rva"] != entry_rva:
        raise ValueError("rebuilt PE entry RVA did not round-trip")
    mapped_final, final_pe = map_pe_file(final)
    parsed = parse_imports(mapped_final, final_pe)
    if len(parsed["entries"]) != len(flat):
        raise ValueError("rebuilt PE import validation count mismatch")
    receipt = {
        "format": "fdisbull-chimprec-pe-rebuild-1",
        "bits": pe["bits"],
        "image_base": pe["image_base"],
        "entry_rva": entry_rva,
        "oep": pe["image_base"] + entry_rva,
        "section": section_name,
        "source_sha256": _sha256(bytes(source)),
        "capture_sha256": _sha256(bytes(capture)),
        "output_sha256": _sha256(final),
        "source_size": len(source),
        "capture_size": len(capture),
        "output_size": len(final),
        "import_groups": len(groups),
        "import_count": len(flat),
        "import_directory_rva": new_section_rva,
        "import_directory_size": import_directory_size,
        "checksum": checksum,
        "fixed_base": bool(fixed_base),
        "capture_metadata": capture_metadata or {},
        "security_directory_cleared": True,
        "bound_imports_cleared": True,
        "relocations_cleared": bool(fixed_base),
        "exact_prepacker_reconstruction": False,
    }
    return final, receipt
