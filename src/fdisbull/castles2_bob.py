"""Castles II 8-bit indexed BOB bitmap, not every format named .BOB.

The selected CD-edition resource layout is two u16le dimensions,
256 RGB888 triplets, followed by width*height row-major byte indices.
No magic byte identifies the format. Do not use suffix-only identification.
"""
from __future__ import annotations

import struct
from .mads_media import IndexedImage

HEADER_SIZE = 4
PALETTE_BYTES = 256 * 3
PIXEL_OFFSET = HEADER_SIZE + PALETTE_BYTES
MAX_PIXELS = 4 * 1024 * 1024
MAX_DIMENSION = 4096


def decode_bob(data: bytes) -> IndexedImage:
    """Return original pixel indices and palette without guessed transparency.

    No in-game rendering, animation, sequencing, or timing is inferred.
    """
    if type(data) is not bytes or not PIXEL_OFFSET < len(data) <= PIXEL_OFFSET + MAX_PIXELS:
        raise ValueError('BOB requires bounded nonempty immutable input')
    width, height = struct.unpack_from('<HH', data, 0)
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION
            and width * height <= MAX_PIXELS):
        raise ValueError('BOB geometry invalid or outside pixel budget')
    if len(data) != PIXEL_OFFSET + width * height:
        raise ValueError('BOB length does not equal 772 + width * height')
    palette = tuple(tuple(data[pos:pos+3]) for pos in range(4, PIXEL_OFFSET, 3))
    return IndexedImage(width=width, height=height,
                        pixels=data[PIXEL_OFFSET:], palette=palette,
                        transparent=None)
