"""Bounded immutable VIEW catalog for the experimental native binding profile.

The file contains geometry and exact payload digests, not game resource bytes.
Availability in this catalog does not mean the guest executed ``load.view``.
"""
from hashlib import sha256

from fdisbull_core.agi_view import describe_view


MAGIC = b"FDBAGIV1"
PROFILE = "agi-2917-view-binding-pilot-1"
MAX_BYTES = 65536
MAX_LOOPS = 1024
MAX_CELS = 4096


def encode_catalog(views, *, horizon):
    """Validate complete VIEW payloads and serialize deterministic metadata.

    ``views`` maps byte-sized IDs to uncompressed payload bytes. The caller
    explicitly supplies horizon (0..167); reset state is otherwise specified by
    the native profile. No loads, scene actions or original-game state are inferred.
    """
    if type(views) is not dict or not 1 <= len(views) <= 256:
        raise ValueError("A catalog requires 1..256 VIEW resources")
    if type(horizon) is not int or not 0 <= horizon <= 167:
        raise ValueError("horizon must be an integer in 0..167")
    if any(type(key) is not int or not 0 <= key <= 255 for key in views):
        raise ValueError("VIEW IDs must be integers in 0..255")
    data = bytearray(MAGIC + bytes([horizon, 0]) + len(views).to_bytes(2, "little"))
    total_loops = total_cels = 0
    for number, payload in sorted(views.items()):
        metadata = describe_view(payload)
        total_loops += len(metadata["loops"])
        total_cels += metadata["cel_references"]
        if total_loops > MAX_LOOPS or total_cels > MAX_CELS:
            raise ValueError("Catalog topology budget exceeded")
        data.extend(bytes([number, len(metadata["loops"])]))
        data.extend(bytes.fromhex(metadata["source_sha256"]))
        for loop in metadata["loops"]:
            data.append(len(loop["cels"]))
            for cel in loop["cels"]:
                data.extend(bytes([cel["width"], cel["height"]]))
        if len(data) > MAX_BYTES:
            raise ValueError("Catalog file budget exceeded")
    return bytes(data)


def decode_catalog(data):
    """Read the exact native format with the same structural admission bounds.

    This validates the catalog, not the referenced payloads. ``encode_catalog``
    performs payload validation before encoding. A matching SHA is a recorded
    identity, not publisher authenticity or original-interpreter parity.
    """
    if type(data) is not bytes or not 12 <= len(data) <= MAX_BYTES:
        raise ValueError("Catalog requires 12..65536 bytes")
    if data[:8] != MAGIC or data[9] != 0 or data[8] > 167:
        raise ValueError("Invalid catalog header")
    count = int.from_bytes(data[10:12], "little")
    if not 1 <= count <= 256:
        raise ValueError("Invalid catalog resource count")
    cursor, last, loops, cels = 12, -1, 0, 0

    def take(length):
        nonlocal cursor
        if cursor + length > len(data):
            raise ValueError("Truncated catalog")
        result = data[cursor:cursor + length]
        cursor += length
        return result

    views = {}
    for _ in range(count):
        number, loop_count = take(2)
        if number <= last or not loop_count:
            raise ValueError("Catalog IDs must ascend and each VIEW must have loops")
        last = number
        digest = take(32).hex()
        loops += loop_count
        if loops > MAX_LOOPS:
            raise ValueError("Catalog loop budget exceeded")
        topology, references = [], 0
        for _ in range(loop_count):
            cel_count = take(1)[0]
            references += cel_count
            cels += cel_count
            if references > 1024 or cels > MAX_CELS:
                raise ValueError("Catalog cel budget exceeded")
            row = []
            for _ in range(cel_count):
                width, height = take(2)
                if not 1 <= width <= 160 or not 1 <= height <= 168:
                    raise ValueError("Invalid catalog cel dimensions")
                row.append({"width": width, "height": height})
            topology.append(row)
        views[number] = {"sha256": digest, "loops": topology}
    if cursor != len(data):
        raise ValueError("Trailing catalog bytes")
    return {"profile": PROFILE, "sha256": sha256(data).hexdigest(),
            "horizon": data[8], "views": views}
