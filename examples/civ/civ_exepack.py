"""Decode a Microsoft EXEPACK DOS root while preserving trailing overlays.

The decoder is intentionally format-scoped. It does not execute a stub, infer
runtime memory, or rewrite overlay bytes. The output is a new MZ root with the
EXEPACK relocation buckets expanded into ordinary relocation records, followed
by the original overlay tail when present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

DOS_SIGNATURE = 0x5A4D
EXEPACK_SIGNATURE = 0x4252  # ``RB``
PACKED_ERROR = b"Packed file is corrupt"
DOS_HEADER = struct.Struct("<14H")
EXEPACK_HEADER = struct.Struct("<9H")


class ExepackError(ValueError):
    """The input is not a bounded, internally consistent EXEPACK image."""


def _u16(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ExepackError(f"{label} exceeds input bounds")
    return struct.unpack_from("<H", data, offset)[0]


def _declared_file_size(header: tuple[int, ...], actual: int) -> int:
    pages = header[2]
    last_page = header[1]
    if pages == 0:
        raise ExepackError("MZ page count is zero")
    declared = (pages - 1) * 512 + (last_page or 512)
    if declared < header[4] * 16 or declared > actual:
        raise ExepackError("MZ declared file size is outside the input")
    return declared


def _decode_payload(reversed_stream: bytes, expected_size: int) -> bytes:
    cursor = 0
    while cursor < len(reversed_stream) and reversed_stream[cursor] == 0xFF:
        cursor += 1
    output = bytearray()
    terminated = False
    while cursor < len(reversed_stream):
        if cursor + 3 > len(reversed_stream):
            raise ExepackError("truncated EXEPACK command")
        opcode = reversed_stream[cursor]
        count = int.from_bytes(reversed_stream[cursor + 1 : cursor + 3], "big")
        cursor += 3
        if (opcode & 0xFE) == 0xB0:
            if cursor >= len(reversed_stream):
                raise ExepackError("truncated EXEPACK fill command")
            output.extend(bytes([reversed_stream[cursor]]) * count)
            cursor += 1
        elif (opcode & 0xFE) == 0xB2:
            end = cursor + count
            if end > len(reversed_stream):
                raise ExepackError("truncated EXEPACK literal command")
            output.extend(reversed_stream[cursor:end])
            cursor = end
        else:
            raise ExepackError(f"unknown EXEPACK opcode 0x{opcode:02x}")
        if len(output) > expected_size:
            raise ExepackError("EXEPACK output exceeds declared destination size")
        if opcode & 1:
            terminated = True
            break
    if not terminated and cursor < len(reversed_stream):
        raise ExepackError("EXEPACK command stream has no terminator")
    if cursor < len(reversed_stream):
        remainder = reversed_stream[cursor:]
        if len(output) + len(remainder) > expected_size:
            raise ExepackError("EXEPACK remainder exceeds destination size")
        output.extend(remainder)
    if len(output) != expected_size:
        raise ExepackError(
            f"EXEPACK output size {len(output)} does not match declared {expected_size}"
        )
    return bytes(reversed(output))


def _relocations(data: bytes, exepack_offset: int, exepack_size: int) -> bytes:
    end = exepack_offset + exepack_size
    marker = data.find(PACKED_ERROR, exepack_offset, min(end, len(data)))
    if marker < 0:
        raise ExepackError('EXEPACK marker "Packed file is corrupt" is missing')
    cursor = marker + len(PACKED_ERROR)
    relocations = bytearray()
    for segment in range(16):
        count = _u16(data, cursor, "EXEPACK relocation count")
        cursor += 2
        for _ in range(count):
            entry = _u16(data, cursor, "EXEPACK relocation entry")
            cursor += 2
            relocations.extend(struct.pack("<HH", entry, segment * 0x1000))
    if cursor > end:
        raise ExepackError("EXEPACK relocation table exceeds its declared extent")
    return bytes(relocations)


def unpack_exepack(data: bytes, *, preserve_overlay: bool = True) -> bytes:
    """Return an unpacked MZ image for one EXEPACK-packed input.

    ``preserve_overlay`` appends every byte after the original MZ declared file
    size. Civ's 23 overlay records live there and are not part of the packed
    root payload. The rebuilt MZ size fields describe the root load module, as
    the original overlay manager expects; the physical overlay bytes remain
    after that declared boundary.

    The minimum-allocation field is adjusted by the paragraph growth from the
    packed image plus EXEPACK stub to the decoded destination image.
    """
    if not isinstance(data, bytes) or len(data) < DOS_HEADER.size:
        raise ExepackError("input is shorter than an MZ header")
    header = DOS_HEADER.unpack_from(data)
    if header[0] != DOS_SIGNATURE:
        raise ExepackError("input does not have an MZ signature")
    header_size = header[4] * 16
    declared_size = _declared_file_size(header, len(data))
    exepack_offset = (header[4] + header[11]) * 16
    if (
        exepack_offset < header_size
        or exepack_offset + EXEPACK_HEADER.size > declared_size
    ):
        raise ExepackError("EXEPACK header lies outside the MZ load module")
    packed = EXEPACK_HEADER.unpack_from(data, exepack_offset)
    if packed[7] != EXEPACK_SIGNATURE and packed[8] != EXEPACK_SIGNATURE:
        raise ExepackError("input does not have an EXEPACK RB signature")
    exepack_size = packed[3]
    if (
        exepack_size < EXEPACK_HEADER.size
        or exepack_offset + exepack_size > declared_size
    ):
        raise ExepackError("EXEPACK extent is outside the MZ load module")
    payload = data[header_size:exepack_offset]
    if not payload:
        raise ExepackError("EXEPACK payload is empty")
    unpacked = _decode_payload(payload[::-1], packed[6] * 16)
    relocations = _relocations(data, exepack_offset, exepack_size)

    new_header_size = DOS_HEADER.size + len(relocations)
    paragraphs = (new_header_size + 15) // 16
    padding = paragraphs * 16 - new_header_size
    root_size = paragraphs * 16 + len(unpacked)
    original_image_bytes = (exepack_offset - header_size) + exepack_size
    original_image_paragraphs = original_image_bytes // 16
    minimum_allocation = max(0, header[5] + original_image_paragraphs - packed[6])
    tail = data[declared_size:] if preserve_overlay else b""
    new_header = DOS_HEADER.pack(
        DOS_SIGNATURE,
        root_size % 512,
        (root_size + 511) // 512,
        len(relocations) // 4,
        paragraphs,
        minimum_allocation,
        0xFFFF,
        packed[5],
        packed[4],
        0,
        packed[0],
        packed[1],
        DOS_HEADER.size,
        0,
    )
    return new_header + relocations + bytes(padding) + unpacked + tail


def unpack_file(
    source: Path, destination: Path, *, preserve_overlay: bool = True
) -> dict:
    original = source.read_bytes()
    unpacked = unpack_exepack(original, preserve_overlay=preserve_overlay)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(unpacked)
    return {
        "source": str(source),
        "destination": str(destination),
        "source_bytes": len(original),
        "destination_bytes": len(unpacked),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "destination_sha256": hashlib.sha256(unpacked).hexdigest(),
        "preserved_overlay": preserve_overlay,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--drop-overlay",
        action="store_true",
        help="omit bytes after the packed MZ root",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            unpack_file(
                args.source, args.destination, preserve_overlay=not args.drop_overlay
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
