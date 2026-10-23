"""Classic DOS MZ loading with explicit real-mode segmentation and relocation.

The source file stays immutable. A separate runtime image receives DOS segment
fixups and a deterministic zero-filled minimum allocation. This is a static
loader, not a DOS process/PSP emulator; the executable mapping marks possible
code, not a declaration that every mapped byte is an instruction.

Header/page definitions: https://delorie.com/djgpp/doc/exe/ and Ralf Brown's
.EXE header record at https://delorie.com/djgpp/doc/rbinter/it/94/15.html.
"""
from __future__ import annotations

import hashlib
import struct

from .model import Image, Region, Seed

_REAL_MODE_LIMIT = 0x100000
_MAX_SOURCE = 64 * 1024 * 1024
_HEADER_NAMES = (
    "e_magic", "e_cblp", "e_cp", "e_crlc", "e_cparhdr", "e_minalloc",
    "e_maxalloc", "e_ss", "e_sp", "e_csum", "e_ip", "e_cs", "e_lfarlc", "e_ovno",
)


def load_mz(data: bytes, *, load_segment: int = 0x1000, entry: int | None = None,
            allow_secondary: bool = False) -> Image:
    """Load a classic MZ module at a chosen DOS load segment.

    Canonical addresses are ``segment * 16 + offset``; addresses requiring A20
    wrapping are rejected. Allocation is the paragraph-rounded module plus
    ``e_minalloc`` paragraphs, not the larger/variable ``e_maxalloc`` request.
    The preceding PSP is described but not fabricated or mapped.

    Relocations must address complete file-backed words. ``original_value`` is
    the word immediately before each fixup (so duplicate records apply twice,
    as a DOS relocation loop would). A relocated word is only evidence of a
    segment value: its role as data segment, immediate or far-pointer segment
    is not inferred here. Only the declared/overridden entry becomes a seed.

    ``entry`` is an optional canonical linear override. Header CS:IP remains in
    metadata. ``selected_entry`` and ``selected_entry_cs/ip`` record the actual
    analysis entry and its deterministic candidate-based context.
    An explicit ``allow_secondary=True`` selects the declared DOS load image
    even when the retained file also has a PE/NE/LE/LX secondary header. Default
    loading still rejects that ambiguity; all MZ validation remains unchanged.
    """
    if not isinstance(allow_secondary, bool):
        raise ValueError("allow_secondary must be a boolean")
    if not isinstance(data, bytes):
        raise ValueError("MZ source must be immutable bytes")
    if len(data) < 28:
        raise ValueError("Truncated MZ header: at least 28 bytes are required")
    if len(data) > _MAX_SOURCE:
        raise ValueError("MZ source exceeds the 64 MiB limit")
    if data[:2] != b"MZ":
        raise ValueError("classic MZ signature required")
    if isinstance(load_segment, bool) or not isinstance(load_segment, int) or not 0x10 <= load_segment <= 0xFFFF:
        raise ValueError("load_segment must be a 16-bit segment at least 0x10 to leave room for the PSP")
    header = dict(zip(_HEADER_NAMES, struct.unpack_from("<14H", data)))
    if header["e_cp"] == 0:
        raise ValueError("MZ page count must be nonzero")
    if header["e_cblp"] > 511:
        raise ValueError("MZ last-page byte count must be between 0 and 511")
    declared_size = header["e_cp"] * 512
    if header["e_cblp"]:
        declared_size -= 512 - header["e_cblp"]
    if declared_size > len(data):
        raise ValueError(f"Truncated MZ image: header declares {declared_size} bytes, source has {len(data)}")
    header_size = header["e_cparhdr"] * 16
    if header_size < 28 or header_size >= declared_size:
        raise ValueError("MZ header size must cover the fixed header and leave a nonempty module")
    relocation_offset, relocation_count = header["e_lfarlc"], header["e_crlc"]
    relocation_end = relocation_offset + relocation_count * 4
    if relocation_count and (relocation_offset < 28 or relocation_end > header_size):
        raise ValueError("MZ relocation table must fit wholly inside the header after its fixed fields")

    # e_lfanew was added after the original MZ format. Legacy relocation words
    # may overlap these bytes, and arbitrary nonzero values are not evidence
    # of a newer executable. Only an actual recognizable secondary signature,
    # referenced by an independent header field, causes explicit rejection.
    from .image_views import secondary_header
    secondary=secondary_header(data) if header_size>=64 else None
    if secondary is not None and not allow_secondary:
        raise ValueError(f"{secondary['format']} secondary executable header is not a classic DOS MZ image")

    module_size = declared_size - header_size
    paragraph_size = (module_size + 15) & ~15
    allocation_size = paragraph_size + header["e_minalloc"] * 16
    image_base = load_segment * 16
    if image_base + allocation_size > _REAL_MODE_LIMIT:
        raise ValueError("MZ minimum allocation exceeds the supported 1 MiB real-mode address space; A20 wrapping is not supported")
    image = bytearray(data[header_size:declared_size])
    image.extend(bytes(allocation_size - module_size))
    relocations = []
    for index in range(relocation_count):
        offset, segment = struct.unpack_from("<HH", data, relocation_offset + index * 4)
        image_offset = segment * 16 + offset
        if image_offset + 2 > module_size:
            raise ValueError(f"MZ relocation target {index} is not a complete file-backed module word")
        original_value = struct.unpack_from("<H", image, image_offset)[0]
        relocated_value = (original_value + load_segment) & 0xFFFF
        struct.pack_into("<H", image, image_offset, relocated_value)
        relocations.append({"offset": offset, "segment": segment,
                            "linear_address": image_base + image_offset,
                            "file_offset": header_size + image_offset,
                            "original_value": original_value, "relocated_value": relocated_value})
    entry_cs = (load_segment + header["e_cs"]) & 0xFFFF
    stack_ss = (load_segment + header["e_ss"]) & 0xFFFF
    header_entry = entry_cs * 16 + header["e_ip"]
    stack_linear = stack_ss * 16 + header["e_sp"]
    if header_entry >= _REAL_MODE_LIMIT or stack_linear > _REAL_MODE_LIMIT:
        raise ValueError("MZ register state exceeds the supported 1 MiB address space; A20 wrapping is not supported")
    selected_entry = header_entry if entry is None else entry
    if (isinstance(selected_entry, bool) or not isinstance(selected_entry, int)
            or not image_base <= selected_entry < image_base + allocation_size):
        raise ValueError("MZ entry must be a canonical linear address inside the loaded image")

    candidate_map = {}

    def candidate(segment, evidence):
        record = candidate_map.setdefault(segment, {"segment": segment, "linear_base": segment * 16,
                                                    "status": "candidate", "sources": []})
        record["sources"].append(evidence)

    candidate(entry_cs, {"kind": "header_entry_cs"})
    candidate(stack_ss, {"kind": "header_stack_ss"})
    for relocation in relocations:
        candidate(relocation["relocated_value"], {"kind": "relocated_word", "linear_address": relocation["linear_address"],
                                                "role": "unknown; not assumed to be code or a far pointer"})
    # Preserve the header's actual startup registers independently of a user
    # analysis-entry override. Reuse a supported segment candidate; a physical
    # address alone cannot establish an arbitrary new code segment.
    if 0 <= selected_entry - entry_cs * 16 <= 0xFFFF:
        selected_entry_cs = entry_cs
        selected_entry_cs_source = "header CS window"
    else:
        compatible = [segment for segment in candidate_map if 0 <= selected_entry - segment * 16 <= 0xFFFF]
        if not compatible:
            raise ValueError("MZ entry override has no available candidate CS context")
        selected_entry_cs = max(compatible)
        selected_entry_cs_source = "highest compatible existing segment candidate; static analysis assumption"
    candidate(selected_entry_cs, {"kind": "selected_entry_cs", "source": selected_entry_cs_source})
    dos = {
        "selected_image": "mz",
        "secondary_format": secondary['format'] if secondary else None,
        "secondary_header_offset": secondary['header_offset'] if secondary else None,
        "load_segment": load_segment, "image_base": image_base,
        "module_size": module_size, "allocation_size": allocation_size,
        "entry_cs": entry_cs, "entry_ip": header["e_ip"], "header_entry": header_entry,
        "selected_entry": selected_entry, "selected_entry_cs": selected_entry_cs,
        "selected_entry_ip": selected_entry - selected_entry_cs * 16,
        "selected_entry_cs_source": selected_entry_cs_source,
        "stack_ss": stack_ss, "sp": header["e_sp"],
        "stack_linear": stack_linear, "psp_segment": load_segment - 0x10,
        "relocations": relocations,
        "segment_candidates": [candidate_map[value] for value in sorted(candidate_map)],
        "overlay_offset": declared_size, "overlay_size": len(data) - declared_size,
        "declared_file_size": declared_size, "header_size": header_size,
        "header_fields": header,
        "allocation_policy": "paragraph-rounded module plus minimum extra paragraphs; no DOS allocator emulation",
        "permissions": "possible executable/writable DOS memory; not a code classification",
        "a20_wrap": False,
    }
    metadata = {
        "selected_image": "mz",
        "secondary_format": secondary['format'] if secondary else None,
        "secondary_header_offset": secondary['header_offset'] if secondary else None,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "mapping": "DOS relocated real-mode linear addresses (segment*16+offset); no A20 wrap",
        "file_mappings": [{"virtual_address": image_base, "file_offset": header_size, "file_size": module_size}],
        "dos": dos,
    }
    return Image("MZ", "x86", 16, selected_entry,
                 [Region("loaded_image", image_base, bytes(image), True, True)],
                 [Seed(selected_entry, "entry", "mz_header_entry" if entry is None else "explicit_entry")],
                 metadata, source_bytes=data)
