"""Bounded inspection of KINT6 .KE images, without allocating guest memory.

The initialized CODE segment includes the header, instructions, and data. The
format does not mark a separate instruction-only region. File offsets and guest
byte offsets coincide in CODE; the other segments exist only at runtime.

Format facts were checked against Kaser's KINT6 development documentation and
6.3.0 kit. This is an independently authored reader, not an interpreter port.
Later runtime revisions and reserved header extensions remain unqualified.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any


MAX_KE_BYTES = 64 * 1024 * 1024
KE_HEADER_BYTES = 0x200
KE_ENTRY_OFFSET = KE_HEADER_BYTES
MAX_GUEST_ADDRESS = 0xFFFFFFFF
_SENTINEL = 0x0123456789ABCDEF


def read_ke(path: str | Path) -> bytes:
    """Capture at most one bounded file snapshot; never follow runtime assets."""
    # Share the media seam's regular-file, no-symlink, race-checked capture.
    # Keep this import lazy because media's adapters also use this parser.
    from .media import _snapshot
    return _snapshot(path, MAX_KE_BYTES)


def inspect_ke_bytes(data: bytes) -> dict[str, Any]:
    """Validate a raw initialized image and describe declared guest segments.

Length fields occupy eight bytes in the header, but the documented interpreter
uses 32-bit guest addresses. Reject unsupported sizes instead of truncating the
upper halves or materializing a potentially enormous ZERO/STACK/HEAP allocation.
There is no checksum in this format: SHA-256 records identity, not authenticity.
"""
    if not isinstance(data, bytes):
        raise ValueError('KINT6 inspection requires immutable bytes')
    if len(data) > MAX_KE_BYTES:
        raise ValueError(f'KINT6 image exceeds the {MAX_KE_BYTES}-byte input limit')
    if len(data) < KE_HEADER_BYTES + 4:
        raise ValueError('KINT6 image is truncated: header and event instruction required')
    if data[0xD0:0xD6] != b'KINT6\0':
        raise ValueError('Not a KINT6 .KE image: missing header marker')
    if int.from_bytes(data[:8], 'little') != _SENTINEL:
        raise ValueError('Unsupported KINT6 null-pointer sentinel or byte order')

    sizes = [int.from_bytes(data[at:at + 8], 'little')
             for at in (0xE0, 0xE8, 0xF0, 0xF8)]
    code_bytes, zero_bytes, stack_bytes, heap_bytes = sizes
    if code_bytes != len(data):
        raise ValueError('KINT6 declared CODE size does not match the complete file')
    if any(size > MAX_GUEST_ADDRESS for size in sizes) or sum(sizes) > MAX_GUEST_ADDRESS:
        raise ValueError('KINT6 declared memory exceeds the supported 32-bit guest address range')

    sections = []
    guest_offset = 0
    for name, size in zip(('CODE', 'ZERO', 'STACK', 'HEAP'), sizes):
        file_backed = name == 'CODE'
        sections.append({
            'name': name,
            'file_offset': 0 if file_backed else None,
            'guest_offset': guest_offset,
            'size_bytes': size,
            'file_backed': file_backed,
            'contents': ('header_and_intermixed_instructions_and_initialized_data'
                         if file_backed else 'runtime_only'),
        })
        guest_offset += size

    return {
        'format': 'kint6-ke',
        'sha256': sha256(data).hexdigest(),
        'size_bytes': len(data),
        'header_bytes': KE_HEADER_BYTES,
        'byte_order': 'little',
        'guest_address_bits': 32,
        'entry_offset': KE_ENTRY_OFFSET,
        'entry_kind': 'event_dispatch_candidate',
        'declared_file_bytes': code_bytes,
        'zero_bytes': zero_bytes,
        'stack_bytes': stack_bytes,
        'heap_bytes': heap_bytes,
        'memory_bytes': sum(sizes),
        'sections': sections,
        'build': {
            'year': int.from_bytes(data[0xD6:0xD8], 'little'),
            'month': data[0xD8],
            'day': data[0xD9],
            'number': int.from_bytes(data[0xDC:0xE0], 'little'),
        },
        'header_revision': {'major': data[0xDA], 'minor': data[0xDB]},
        'minimum_runtime_version': None,
        'runtime_version_status': 'not_established_by_supported_header_contract',
        'reserved_extension_0x110': data[0x110:0x118].hex(),
        'qualification': {
            'reference_kit': '6.3.0',
            'later_runtime_extensions': 'unknown',
            'instruction_data_partition': 'not_present_in_format',
            'runtime_execution': False,
            'checksum': 'not_present_in_format',
        },
    }
