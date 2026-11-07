"""Bounded standalone FAB decompressor. No MADS engine or processor dependency.

Source-assisted format implementation, originally factored from mads_resources.
See docs/MADS_MEDIA_RUNTIME.md for provenance and supported bounds.
"""
from __future__ import annotations
MAX_RESOURCE = 16 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024

def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_int(value, name, low, high):
    require(type(value) is int and low <= value <= high, f'{name} outside {low}..{high}')
    return value


class Cursor:
    def __init__(self, data, start=0, end=None):
        self.data = data
        self.at = start
        self.end = len(data) if end is None else end
        require(0 <= start <= self.end <= len(data), 'invalid MADS cursor range')

    def take(self, count):
        require(0 <= count <= self.end - self.at, f'truncated MADS data at {self.at}')
        result = self.data[self.at:self.at + count]
        self.at += count
        return result

    def u8(self):
        return self.take(1)[0]

    def u16(self):
        return int.from_bytes(self.take(2), 'little')

    def s16(self):
        return int.from_bytes(self.take(2), 'little', signed=True)


def decode_fab(data: bytes, expected_size: int) -> tuple[bytes, int]:
    """Return decoded bytes and consumed input; never silently discard a tail.

    The six-byte prefix carries a 10..13-bit backwards window and the first
    control word. Its last bit prefetches the NEXT control word before the
    command's data bytes. Back-references copy sequentially, including overlap.
    """
    require(type(data) is bytes and 6 <= len(data) <= MAX_RESOURCE, 'invalid FAB input size')
    bounded_int(expected_size, 'FAB output size', 0, MAX_EXPANDED)
    require(data[:3] == b'FAB' and 10 <= data[3] <= 13, 'unsupported FAB header/window')
    reader = Cursor(data, 6)
    control = int.from_bytes(data[4:6], 'little')
    remaining = 16
    shift = 16 - data[3]
    output = bytearray()

    def bit():
        nonlocal control, remaining
        remaining -= 1
        if remaining == 0:
            control = (reader.u16() << 1) | (control & 1)
            remaining = 16
        value = control & 1
        control >>= 1
        return value

    # Every command consumes input bits/data; keep an independent work ceiling.
    for _ in range(8 * len(data) + 1):
        if bit():
            require(len(output) < expected_size, 'FAB literal exceeds declared output')
            output.append(reader.u8())
            continue
        if bit() == 0:
            count = 2 + (bit() << 1) + bit()
            distance = 256 - reader.u8()
        else:
            low, high = reader.u8(), reader.u8()
            distance = (1 << data[3]) - ((high >> shift) * 256 + low)
            count = high & ((1 << shift) - 1)
            if count == 0:
                extended = reader.u8()
                if extended == 0:
                    require(len(output) == expected_size, 'FAB output length mismatch')
                    return bytes(output), reader.at
                if extended == 1:
                    continue
                # Match the source format's byte-sized extended copy count.
                count = (extended + 1) & 0xff
            else:
                count += 2
        require(1 <= distance <= len(output), 'FAB reference precedes decoded output')
        require(len(output) + count <= expected_size, 'FAB copy exceeds declared output')
        if count:
            # Sequential overlapping LZ copies repeat the preceding suffix.
            if count <= distance:
                start = len(output) - distance
                output.extend(output[start:start + count])
            else:
                seed = output[-distance:]
                output.extend((seed * ((count + distance - 1) // distance))[:count])
    raise ValueError('FAB command budget exhausted without terminator')

