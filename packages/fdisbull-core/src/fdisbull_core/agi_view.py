"""Bounded, independently implemented DOS AGI 2.917 EGA VIEW cel decoding.

Format and effective-loop mirroring reference:
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/view.cpp

This reads an uncompressed VIEW payload, without its volume header. It returns
indexed source pixels, not visible actors or a rendered scene. Other platform
layouts, early loop-header mirroring and AGI256 are outside this profile.
"""
from hashlib import sha256


_MAX_PAYLOAD = 65535
_MAX_CEL_REFERENCES = 1024
_MAX_WIDTH = 160
_MAX_HEIGHT = 168


def decode_view_cel(payload: bytes, *, loop: int, cel: int) -> dict:
    """Decode one effective cel, retaining payload-relative source boundaries.

    Validate every referenced directory, cel header and unique cel RLE stream.
    Exact shared loop/cel pointers are admitted; overlapping distinct structures
    and rows extending into another structure are rejected. Unused padding is
    allowed, as are empty unselected loops. At most 1024 cel-directory references
    and 65535 payload bytes are examined; only the selected cel's array is allocated.

    Each row requires a zero terminator; omitted trailing pixels have the cel's
    transparent color. Bit 7 enables mirroring when the stored original-loop
    field (bits 4..6) differs from the requested loop. Mirroring reverses the
    complete row, including that transparent remainder. Invalid inputs raise
    ValueError; neither input bytes nor external state are changed.
    """
    if type(loop) is not int or not 0 <= loop <= 255:
        raise ValueError("loop must be an integer in 0..255")
    if type(cel) is not int or not 0 <= cel <= 255:
        raise ValueError("cel must be an integer in 0..255")
    return _read_view(payload, loop, cel)


def describe_view(payload: bytes) -> dict:
    """Validate a complete VIEW and return its effective cel geometry/topology.

    This uses the same bounded directory/RLE validation as ``decode_view_cel``
    and allocates no pixel arrays. Empty loops remain explicit. Every effective
    loop/cel reference retains its source offset and mirroring metadata; exact
    shared pointers are described independently without decoding them twice.
    The resource digest binds this metadata to the complete input payload.
    """
    return _read_view(payload, None, None)


def _read_view(payload, loop, cel):
    if type(payload) is not bytes or not 5 <= len(payload) <= _MAX_PAYLOAD:
        raise ValueError("Expected a 5..65535-byte uncompressed VIEW payload")

    def word(offset):
        if not 0 <= offset <= len(payload) - 2:
            raise ValueError("Truncated VIEW offset")
        return int.from_bytes(payload[offset:offset + 2], "little")

    loop_count = payload[2]
    header_end = 5 + 2 * loop_count
    if not loop_count or header_end > len(payload):
        raise ValueError("Invalid VIEW loop directory")
    if loop is not None and loop >= loop_count:
        raise ValueError("Requested loop is absent")

    spans = {(0, header_end, "VIEW header")}
    description = word(3)
    if description:
        if not header_end <= description < len(payload):
            raise ValueError("Invalid VIEW description offset")
        terminator = payload.find(b"\0", description)
        if terminator < 0:
            raise ValueError("Unterminated VIEW description")
        spans.add((description, terminator + 1, "description"))

    loops = []
    references = 0
    for index in range(loop_count):
        start = word(5 + 2 * index)
        if not header_end <= start < len(payload):
            raise ValueError("Invalid VIEW loop offset")
        count = payload[start]
        end = start + 1 + 2 * count
        if end > len(payload):
            raise ValueError("Invalid VIEW cel directory")
        references += count
        if references > _MAX_CEL_REFERENCES:
            raise ValueError("VIEW cel-reference budget exceeded")
        loops.append((start, count, end))
        spans.add((start, end, "loop directory"))
    if loop is not None and cel >= loops[loop][1]:
        raise ValueError("Requested cel is absent")

    headers = {}
    cel_offsets = []
    selected = None
    for index, (start, count, end) in enumerate(loops):
        offsets = []
        for number in range(count):
            offset = start + word(start + 1 + 2 * number)
            if offset < end or offset + 3 > len(payload):
                raise ValueError("Invalid VIEW cel offset")
            width, height, flags = payload[offset:offset + 3]
            if not 1 <= width <= _MAX_WIDTH or not 1 <= height <= _MAX_HEIGHT:
                raise ValueError("Invalid VIEW cel dimensions")
            headers[offset] = (width, height, flags)
            offsets.append(offset)
            spans.add((offset, offset + 3, "cel header"))
            if index == loop and number == cel:
                selected = offset
        cel_offsets.append(offsets)

    ordered = sorted(spans)
    previous_end = 0
    for start, end, _ in ordered:
        if start < previous_end:
            raise ValueError("Overlapping VIEW structures")
        previous_end = end
    limits = {span[0]: (ordered[index + 1][0]
                         if index + 1 < len(ordered) else len(payload))
              for index, span in enumerate(ordered)}

    selected_pixels = None
    selected_end = None
    data_ends = {}
    for offset, (width, height, flags) in sorted(headers.items()):
        cursor = offset + 3
        limit = limits[offset]
        pixels = bytearray([flags & 15]) * (width * height) if offset == selected else None
        for row in range(height):
            drawn = 0
            while True:
                if cursor >= limit:
                    raise ValueError("Truncated VIEW row or row overlaps another structure")
                run = payload[cursor]
                cursor += 1
                if run == 0:
                    break
                length = run & 15
                if not length or drawn + length > width:
                    raise ValueError("Invalid VIEW run length")
                if pixels is not None:
                    begin = row * width + drawn
                    pixels[begin:begin + length] = bytes([run >> 4]) * length
                drawn += length
        if offset == selected:
            selected_pixels, selected_end = pixels, cursor
        data_ends[offset] = cursor

    if loop is None:
        topology = []
        for index, offsets in enumerate(cel_offsets):
            cels = []
            for number, offset in enumerate(offsets):
                width, height, flags = headers[offset]
                mirror_enabled = bool(flags & 128)
                original_loop = (flags >> 4) & 7 if mirror_enabled else None
                cels.append({"cel": number, "width": width, "height": height,
                             "transparent_color": flags & 15,
                             "mirror_enabled": mirror_enabled,
                             "stored_original_loop": original_loop,
                             "mirrored": mirror_enabled and original_loop != index,
                             "cel_offset": offset, "data_offset": offset + 3,
                             "data_end": data_ends[offset]})
            topology.append({"loop": index, "cels": cels})
        return {"source_sha256": sha256(payload).hexdigest(),
                "payload_bytes": len(payload), "cel_references": references,
                "loops": topology}

    width, height, flags = headers[selected]
    mirror_enabled = bool(flags & 128)
    original_loop = (flags >> 4) & 7 if mirror_enabled else None
    mirrored = mirror_enabled and original_loop != loop
    if mirrored:
        for row in range(height):
            begin = row * width
            selected_pixels[begin:begin + width] = selected_pixels[begin:begin + width][::-1]
    return {"source_sha256": sha256(payload).hexdigest(), "loop": loop, "cel": cel,
            "width": width, "height": height, "transparent_color": flags & 15,
            "mirror_enabled": mirror_enabled, "stored_original_loop": original_loop,
            "mirrored": mirrored, "pixels": bytes(selected_pixels),
            "cel_offset": selected, "data_offset": selected + 3, "data_end": selected_end}
