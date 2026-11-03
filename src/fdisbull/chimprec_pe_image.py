"""Bounded CHimpREC PE dump reconstruction from reviewed captured memory.

The writer accepts an original PE container, a mapped-memory image captured at
one coherent boundary, an explicit OEP RVA and a reviewed import plan from
:func:`fdisbull.chimprec.build_import_plan`.  It writes a new import-directory
section, restores the captured IAT cells to loader thunks and emits an unsigned,
fixed-base PE32 or PE32+ analysis image.

It deliberately does *not* attach to a process, discover DLL mappings, bypass
anti-debugging, run a target or claim that a structurally valid dump starts on
Windows.  Those are separate evidence stages.  The writer refuses unexplained
layout changes rather than silently manufacturing a convenient executable.
"""
from __future__ import annotations

import hashlib
import struct

_MAX_FILE = 512 * 1024 * 1024
_MAX_IMAGE = 512 * 1024 * 1024
_MAX_IMPORTS = 1_000_000
_IMAGE_FILE_RELOCS_STRIPPED = 0x0001
_IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA = 0x0020
_IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE = 0x0040
_IMAGE_SCN_CNT_CODE = 0x00000020
_IMAGE_SCN_CNT_INITIALIZED_DATA = 0x00000040
_IMAGE_SCN_CNT_UNINITIALIZED_DATA = 0x00000080
_IMAGE_SCN_MEM_EXECUTE = 0x20000000
_IMAGE_SCN_MEM_READ = 0x40000000
_IMAGE_SCN_MEM_WRITE = 0x80000000


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _align(value: int, alignment: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("alignment input must be a nonnegative integer")
    if not isinstance(alignment, int) or alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    return (value + alignment - 1) & -alignment


def _bounded(data: bytes | bytearray, offset: int, size: int, label: str) -> memoryview:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} lies outside the supplied bytes")
    return memoryview(data)[offset:offset + size]


def parse_pe(data: bytes) -> dict:
    """Parse the PE fields needed by the bounded dump writer."""
    if not isinstance(data, (bytes, bytearray)) or len(data) > _MAX_FILE:
        raise ValueError("PE input must be bytes no larger than 512 MiB")
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("missing DOS MZ header")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    machine, section_count = struct.unpack_from("<HH", data, pe + 4)
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    section_table = optional + optional_size
    if section_count < 1 or section_count > 4096:
        raise ValueError("invalid PE section count")
    _bounded(data, section_table, section_count * 40, "section table")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x10B:
        bits, pointer_width, image_base_offset = 32, 4, 28
        directory_count_offset, directory_offset = 92, 96
        ordinal_flag = 0x80000000
    elif magic == 0x20B:
        bits, pointer_width, image_base_offset = 64, 8, 24
        directory_count_offset, directory_offset = 108, 112
        ordinal_flag = 0x8000000000000000
    else:
        raise ValueError("CHimpREC reconstruction supports PE32 and PE32+ only")
    minimum = directory_offset
    if optional_size < minimum:
        raise ValueError("truncated PE optional header")
    image_base = (struct.unpack_from("<I", data, optional + image_base_offset)[0]
                  if bits == 32 else struct.unpack_from("<Q", data, optional + image_base_offset)[0])
    section_alignment, file_alignment = struct.unpack_from("<II", data, optional + 32)
    size_of_image, size_of_headers = struct.unpack_from("<II", data, optional + 56)
    if not 0 < size_of_image <= _MAX_IMAGE:
        raise ValueError("invalid SizeOfImage")
    if not 0 < size_of_headers <= len(data):
        raise ValueError("invalid SizeOfHeaders")
    if section_alignment <= 0 or section_alignment & (section_alignment - 1):
        raise ValueError("SectionAlignment must be a power of two")
    if file_alignment <= 0 or file_alignment & (file_alignment - 1):
        raise ValueError("FileAlignment must be a power of two")
    directory_count = struct.unpack_from("<I", data, optional + directory_count_offset)[0]
    available_dirs = max(0, (optional_size - directory_offset) // 8)
    directory_count = min(directory_count, available_dirs)
    directories = []
    for index in range(directory_count):
        rva, size = struct.unpack_from("<II", data, optional + directory_offset + index * 8)
        directories.append({"index": index, "rva": rva, "size": size})
    sections = []
    occupied = []
    for index in range(section_count):
        at = section_table + 40 * index
        name = bytes(data[at:at + 8]).split(b"\0", 1)[0].decode("ascii", errors="replace")
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, at + 8)
        characteristics = struct.unpack_from("<I", data, at + 36)[0]
        mapped_size = max(virtual_size, raw_size)
        if rva + mapped_size > size_of_image:
            raise ValueError(f"section {name!r} exceeds SizeOfImage")
        if raw_size and raw_offset + raw_size > len(data):
            raise ValueError(f"section {name!r} exceeds file bytes")
        if mapped_size:
            if any(max(a, rva) < min(b, rva + mapped_size) for a, b in occupied):
                raise ValueError("overlapping PE virtual sections")
            occupied.append((rva, rva + mapped_size))
        sections.append({"index": index, "name": name, "virtual_size": virtual_size,
                         "rva": rva, "raw_size": raw_size, "raw_offset": raw_offset,
                         "mapped_size": mapped_size, "characteristics": characteristics,
                         "header_offset": at})
    return {"pe_offset": pe, "optional_offset": optional, "optional_size": optional_size,
            "section_table": section_table, "machine": machine, "bits": bits,
            "pointer_width": pointer_width, "ordinal_flag": ordinal_flag,
            "image_base": image_base, "entry_rva": struct.unpack_from("<I", data, optional + 16)[0],
            "section_alignment": section_alignment, "file_alignment": file_alignment,
            "size_of_image": size_of_image, "size_of_headers": size_of_headers,
            "directory_count": directory_count, "directory_offset": directory_offset,
            "directories": directories, "sections": sections,
            "coff_characteristics": struct.unpack_from("<H", data, pe + 22)[0],
            "dll_characteristics": struct.unpack_from("<H", data, optional + 70)[0]}


def map_pe_file(data: bytes) -> tuple[bytes, dict]:
    """Map file-backed PE bytes into a zero-filled preferred-address image."""
    pe = parse_pe(data)
    mapped = bytearray(pe["size_of_image"])
    mapped[:pe["size_of_headers"]] = data[:pe["size_of_headers"]]
    for section in pe["sections"]:
        if not section["raw_size"]:
            continue
        start = section["rva"]
        mapped[start:start + section["raw_size"]] = data[
            section["raw_offset"]:section["raw_offset"] + section["raw_size"]
        ]
    return bytes(mapped), pe


def _normalize_capture(capture: bytes, pe: dict) -> bytearray:
    if not isinstance(capture, (bytes, bytearray)) or len(capture) > _MAX_IMAGE:
        raise ValueError("captured image must be bytes no larger than 512 MiB")
    if len(capture) > pe["size_of_image"]:
        raise ValueError("captured image exceeds source SizeOfImage")
    image = bytearray(pe["size_of_image"])
    image[:len(capture)] = capture
    return image

def find_oep_transfers(events: list[dict], sections: list[dict], *,
                       packed_sections: list[str] | None = None,
                       application_sections: list[str] | None = None) -> list[dict]:
    """Find executed inter-section transfers that can support an OEP candidate.

    Events are consecutive pre-instruction observations with an ``address`` and
    optional decoded ``instruction``.  A candidate is retained only when the
    next observed address lies in a different section and the source instruction
    is a direct/indirect call or branch.  This supports historical JMP and
    ``call rax`` OEP patterns.  Section names are filtering hints, not proof that
    the destination is original application code.
    """
    if not isinstance(events, list) or len(events) > 10_000_000:
        raise ValueError("events must be a bounded list")
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    normalized = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("section records must be dictionaries")
        start = section.get("start", section.get("virtual_address", section.get("rva")))
        size = section.get("size", section.get("virtual_size"))
        if not isinstance(start, int) or not isinstance(size, int) or size <= 0:
            raise ValueError("section needs integer start and positive size")
        normalized.append((start, start + size, section.get("name", "")))
    packed = {name.casefold() for name in packed_sections or []}
    application = {name.casefold() for name in application_sections or []}

    def location(address):
        return next(((a, b, name) for a, b, name in normalized if a <= address < b), None)

    candidates = []
    for index in range(len(events) - 1):
        current, following = events[index], events[index + 1]
        address, next_address = current.get("address"), following.get("address")
        if not isinstance(address, int) or not isinstance(next_address, int):
            continue
        source, target = location(address), location(next_address)
        if source is None or target is None or source == target:
            continue
        instruction = current.get("instruction") or {}
        flow = instruction.get("flow")
        mnemonic = str(instruction.get("mnemonic", "")).lower()
        if flow not in ("call", "indirect_call", "branch", "conditional", "indirect_jump") and mnemonic not in ("call", "jmp"):
            continue
        if packed and source[2].casefold() not in packed:
            continue
        if application and target[2].casefold() not in application:
            continue
        candidates.append({"event_index": index, "source": address, "destination": next_address,
                           "source_section": source[2], "destination_section": target[2],
                           "flow": flow, "mnemonic": mnemonic or None,
                           "evidence": "consecutive executed observations cross sections after a control transfer"})
    return candidates

