"""Bounded reconstruction of the CreateInstall decoder in this supplied installer.

Derived from the original W32GWIZ.EXE x86 routines at VA 401050..401542.
This is authored Python, contains no original program payload, and never
executes an input executable. It is an investigation helper, not a production
format decoder. The stream endpoint and output bounds are always explicit.
"""
from __future__ import annotations

from dataclasses import dataclass


DISTANCE_BITS = (4, 6, 8, 10, 12, 14)
SYMBOL_COUNT = 257 + 6 * 62
LEAF_BASE = SYMBOL_COUNT
LAST_INTERNAL = SYMBOL_COUNT - 1
LAST_NODE = SYMBOL_COUNT * 2 - 1


@dataclass(frozen=True)
class Decoded:
    data: bytes
    consumed_bytes: int
    consumed_bits: int
    symbols: int


def decode(stream: bytes, *, output_limit: int = 16 * 1024 * 1024) -> Decoded:
    """Decode one EOS-terminated stream with hard input/output budgets.

    Incoming bytes supply bits most-significant-bit first. Match-distance
    fields assemble those bits least-significant-bit first. Symbols0..255 are
    literals,256 ends the stream, and257..628 encode six distance classes
    times62 possible lengths (3..64). Frequencies and tree links reproduce the
    adaptive updates in the original stub. The ring is initially zero-filled,
    matching the original VirtualAlloc allocation.
    """
    if output_limit < 0:
        raise ValueError("Negative output limit")
    parent = [0] * (LAST_NODE + 1)
    freq = [0] + [0] + [1] * (LAST_NODE - 1)
    left = [0] * (LAST_INTERNAL + 1)
    right = [0] * (LAST_INTERNAL + 1)
    for node in range(2, LAST_NODE + 1):
        parent[node] = node // 2
    for node in range(1, LAST_INTERNAL + 1):
        left[node], right[node] = node * 2, node * 2 + 1

    distance_base = []
    total = 0
    for width in DISTANCE_BITS:
        distance_base.append(total)
        total += 1 << width
    ring_size = total - 1 + 64
    ring = bytearray(ring_size)
    write_position = 0
    bit_position = 0
    result = bytearray()
    symbols = 0

    def bit() -> int:
        nonlocal bit_position
        if bit_position >= len(stream) * 8:
            raise ValueError("Compressed input ended before EOS")
        value = (stream[bit_position // 8] >> (7 - bit_position % 8)) & 1
        bit_position += 1
        return value

    def update_sums(a: int, b: int) -> None:
        while True:
            p = parent[a]
            freq[p] = freq[a] + freq[b]
            a = p
            if a == 1:
                break
            p = parent[a]
            b = right[p] if left[p] == a else left[p]
        if freq[1] == 2000:
            for node in range(1, LAST_NODE + 1):
                freq[node] //= 2

    def update_tree(symbol: int) -> None:
        a = symbol + LEAF_BASE
        freq[a] += 1
        p = parent[a]
        if p == 1:
            return
        sibling = right[p] if left[p] == a else left[p]
        update_sums(a, sibling)
        while True:
            grandparent = parent[p]
            uncle = right[grandparent] if left[grandparent] == p else left[grandparent]
            if freq[a] > freq[uncle]:
                if left[grandparent] == p:
                    right[grandparent] = a
                else:
                    left[grandparent] = a
                sibling = left[p]
                if sibling == a:
                    sibling = right[p]
                    left[p] = uncle
                else:
                    right[p] = uncle
                parent[uncle] = p
                parent[a] = grandparent
                update_sums(uncle, sibling)
                a = uncle
            a = parent[a]
            p = parent[a]
            if p == 1:
                break

    def emit(value: int) -> None:
        nonlocal write_position
        if len(result) >= output_limit:
            raise ValueError("Decoded output budget exceeded")
        result.append(value)
        ring[write_position] = value
        write_position = (write_position + 1) % ring_size

    while True:
        node = 1
        while node <= LAST_INTERNAL:
            node = right[node] if bit() else left[node]
        symbol = node - LEAF_BASE
        update_tree(symbol)
        symbols += 1
        if symbol == 256:
            return Decoded(bytes(result), (bit_position + 7) // 8, bit_position, symbols)
        if symbol < 256:
            emit(symbol)
            continue
        group, length_index = divmod(symbol - 257, 62)
        length = length_index + 3
        distance_extra = sum(bit() << shift for shift in range(DISTANCE_BITS[group]))
        distance = distance_base[group] + distance_extra + length
        source = (write_position - distance) % ring_size
        for _ in range(length):
            emit(ring[source])
            source = (source + 1) % ring_size
