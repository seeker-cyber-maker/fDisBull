"""Standalone, bounded PKWARE DCL decoder (not PKZIP method 6).

Altered Python implementation informed by Mark Adler's blast 1.3 format notes
and coding tables (zlib v1.3.1/contrib/blast). It is not the original blast.
Copyright (C) 2003, 2012, 2013 Mark Adler
  version 1.3, 24 Aug 2013

  This software is provided 'as-is', without any express or implied
  warranty.  In no event will the author be held liable for any damages
  arising from the use of this software.

  Permission is granted to anyone to use this software for any purpose,
  including commercial applications, and to alter it and redistribute it
  freely, subject to the following restrictions:

  1. The origin of this software must not be misrepresented; you must not
     claim that you wrote the original software. If you use this software
     in a product, an acknowledgment in the product documentation would be
     appreciated but is not required.
  2. Altered source versions must be plainly marked as such, and must not be
     misrepresented as being the original software.
  3. This notice may not be removed or altered from any source distribution.

  Mark Adler    madler@alumni.caltech.edu

The implementation below is new Python; fixed format tables and the upstream
notice are retained. No MADS/ScummVM/runtime or external executable dependency.
"""
from __future__ import annotations

MAX_INPUT = 16 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
_LITERAL_RUNS = (
    11,124,8,7,28,7,188,13,76,4,10,8,12,10,12,10,8,23,8,9,7,6,7,8,7,6,
    55,8,23,24,12,11,7,9,11,12,6,7,22,5,7,24,6,11,9,6,7,22,7,11,38,7,
    9,8,25,11,8,11,9,12,8,12,5,38,5,38,5,11,7,5,6,21,6,10,53,8,7,24,
    10,27,44,253,253,253,252,252,252,13,12,45,12,45,12,61,12,45,44,173)
_LENGTH_RUNS = (2,35,36,53,38,23)
_DISTANCE_RUNS = (2,20,53,230,247,151,248)
_BASE = (3,2,4,5,6,7,8,9,10,12,16,24,40,72,136,264)
_EXTRA = (0,0,0,0,0,0,0,0,1,2,3,4,5,6,7,8)


def _codes(runs):
    """Build canonical MSB code keys; stored bits are individually inverted."""
    lengths = [v & 15 for v in runs for _ in range((v >> 4) + 1)]
    counts = [lengths.count(n) for n in range(14)]
    next_code = [0] * 14
    code = 0
    for width in range(1, 14):
        code = (code + counts[width - 1]) << 1
        next_code[width] = code
        if code + counts[width] > 1 << width:
            raise ValueError('Oversubscribed DCL code table')
    table = {}
    for symbol, width in enumerate(lengths):
        if width:
            table[width, next_code[width]] = symbol
            next_code[width] += 1
    return table


_LITERALS = _codes(_LITERAL_RUNS)
_LENGTHS = _codes(_LENGTH_RUNS)
_DISTANCES = _codes(_DISTANCE_RUNS)


def decode_dcl(data: bytes, expected_size: int | None = None, *,
               max_output_bytes: int = MAX_OUTPUT) -> tuple[bytes, int]:
    """Return decoded bytes and consumed source bytes, preserving caller's tail.

    Both coded and uncoded literals and all three dictionary sizes are handled.
    An end marker is mandatory, including when expected output length is reached.
    The last consumed byte may contain unused padding bits.
    """
    if type(data) is not bytes or not 2 <= len(data) <= MAX_INPUT:
        raise ValueError('DCL input must be 2..16777216 immutable bytes')
    if type(max_output_bytes) is not int or not 0 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('Invalid DCL output limit')
    if expected_size is not None and (type(expected_size) is not int or
                                     not 0 <= expected_size <= max_output_bytes):
        raise ValueError('Invalid DCL expected size')
    literal_mode, distance_bits = data[:2]
    if literal_mode not in (0, 1) or distance_bits not in (4, 5, 6):
        raise ValueError('Unsupported DCL literal/dictionary header')
    position = 16
    limit = max_output_bytes if expected_size is None else expected_size
    out = bytearray()

    def bits(width):
        nonlocal position
        if position + width > len(data) * 8:
            raise ValueError('Truncated DCL bitstream')
        value = 0
        for shift in range(width):
            value |= ((data[position >> 3] >> (position & 7)) & 1) << shift
            position += 1
        return value

    def symbol(table):
        code = 0
        for width in range(1, 14):
            code = (code << 1) | (bits(1) ^ 1)
            result = table.get((width, code))
            if result is not None:
                return result
        raise ValueError('Invalid DCL Huffman code')

    # Every token consumes bits; every nonterminal token emits at least a byte.
    while True:
        if bits(1) == 0:
            value = symbol(_LITERALS) if literal_mode else bits(8)
            if len(out) >= limit:
                raise ValueError('DCL output exceeds budget/declared length')
            out.append(value)
            continue
        code = symbol(_LENGTHS)
        length = _BASE[code] + bits(_EXTRA[code])
        if length == 519:
            if expected_size is not None and len(out) != expected_size:
                raise ValueError('DCL decoded length mismatch')
            return bytes(out), (position + 7) // 8
        extra = 2 if length == 2 else distance_bits
        distance = (symbol(_DISTANCES) << extra) + bits(extra) + 1
        if distance > len(out):
            raise ValueError('DCL back-reference precedes decoded output')
        if len(out) + length > limit:
            raise ValueError('DCL output exceeds budget/declared length')
        for _ in range(length):
            out.append(out[-distance])
