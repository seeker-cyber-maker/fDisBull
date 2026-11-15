"""Bounded DinoPark ABT sample expansion.

This is the consumer-specific byte codec recovered from the supplied DOS game's
sample expander. ABT has no global magic. Callers must select this profile using
game/consumer evidence; a filename extension alone does not identify the format.
The decoder produces an unsigned-eight-bit sample sequence without playing it.
Rate/channel interpretation and original-game use are separate qualifications.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import struct

MAX_SOURCE_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 65535
MAX_WORK_UNITS = 2_000_000


@dataclass(frozen=True)
class ABTAudio:
    """Expanded bytes and opaque source fields; only report() is serializable."""

    pcm_u8: bytes
    declared_samples: int
    rate_field: int
    block_samples: int
    opaque_header: bytes
    consumed_bytes: int
    encoded_bytes: int
    source_sha256: str
    work_units: int
    branches: tuple[tuple[str, int], ...]

    def report(self):
        """Return metadata and hashes, never encoded or decoded sample bytes."""
        return dict(
            format='fdisbull-dinopark-abt-decoding-1', adapter='dinopark-abt',
            source=dict(bytes=self.encoded_bytes, sha256=self.source_sha256),
            decoded=dict(bytes=len(self.pcm_u8), sha256=hashlib.sha256(self.pcm_u8).hexdigest(),
                         sample_representation='unsigned-8-bit sequence',
                         declared_samples=self.declared_samples),
            rate_field=self.rate_field, rate_hz=None, channels=None,
            block_samples=self.block_samples, opaque_header_bytes=len(self.opaque_header),
            opaque_header_sha256=hashlib.sha256(self.opaque_header).hexdigest(),
            compressed_bytes_consumed=self.consumed_bytes,
            trailing_bytes=self.encoded_bytes - self.consumed_bytes,
            work_units=self.work_units, branches=dict(self.branches),
            full_decode=True, input_executed=False, source_modified=False,
            native_runtime_tested=False, qualification='complete-bounded-sample-expansion',
            limitations=[
                'Explicit DinoPark ABT consumer profile; there is no global magic signature.',
                'The rate field and three opaque header bytes are preserved without guessed playback semantics.',
                'Native sample-expander agreement, file use, playback rate/channels, timing and audible output require separate evidence.',
            ],
        )


def decode_abt(data, *, max_output_bytes=MAX_OUTPUT_BYTES,
               max_work_units=MAX_WORK_UNITS):
    """Expand one complete supported ABT into immutable unsigned sample bytes.

    The nine-byte header stores decoded length, a raw rate field, helper block
    size, three opaque bytes and the first sample. Literals store seven bits
    shifted left; repeats retain the preceding sample; packed delta helpers
    use MSB-first codes, a zero-skipping signed-byte table and saturation.

    Source/output/work limits are admitted before reads or allocations. A zero
    repeat still consumes an input byte and work. Unsupported block alignment,
    overrun, truncated packets and unexplained trailers refuse explicitly.
    """
    if not isinstance(data, bytes) or not 9 <= len(data) <= MAX_SOURCE_BYTES:
        raise ValueError('ABT requires immutable bytes with a complete header within its source budget')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('ABT max_output_bytes must be 1..65535')
    if type(max_work_units) is not int or not 1 <= max_work_units <= MAX_WORK_UNITS:
        raise ValueError('ABT max_work_units exceeds its supported work budget')
    declared, rate = struct.unpack_from('<HH', data)
    block = data[4]
    if not declared or not block:
        raise ValueError('ABT declared sample length and block size must be positive')
    if declared > max_output_bytes:
        raise ValueError('ABT decoded sample budget exceeded before allocation')
    work = 0

    def spend(amount=1):
        nonlocal work
        if work + amount > max_work_units:
            raise ValueError('ABT decoder work budget exceeded')
        work += amount

    spend(1)
    output = bytearray(declared)
    output[0] = data[8]
    produced, position = 1, 9
    branches = Counter()

    def octet():
        nonlocal position
        if position >= len(data):
            raise ValueError('Truncated ABT compressed sample stream')
        spend()
        value = data[position]
        position += 1
        return value

    def admit(count):
        if produced + count > declared:
            raise ValueError('ABT decoded samples exceed the declared length')
        spend(count)

    while produced < declared:
        tag = octet()
        if tag & 0x80:
            admit(1)
            output[produced] = (tag << 1) & 255
            produced += 1
            branches['literal_samples'] += 1
        elif tag & 0x40:
            count = tag & 63
            admit(count)
            output[produced:produced + count] = bytes([output[produced - 1]]) * count
            produced += count
            branches['repeat_tokens'] += 1
            branches['repeat_samples'] += count
            if not count:
                branches['zero_repeat_tokens'] += 1
        else:
            kind, step = tag >> 4, (tag & 15) + 1
            bits = 1 if kind == 1 else 2 if kind == 2 else 4
            codes_per_byte = 8 // bits
            if block % codes_per_byte:
                raise ValueError('ABT delta block is not aligned to its helper packing')
            admit(block)
            size = 1 << bits
            spend(size)
            table, value = [], (-size // 2 * step) & 255
            for _ in range(size):
                table.append(value - 256 if value >= 128 else value)
                value = (value + step) & 255
                if value == 0:
                    value = step
            for _ in range(block // codes_per_byte):
                packed = octet()
                for shift in range(8 - bits, -1, -bits):
                    delta = table[(packed >> shift) & (size - 1)]
                    output[produced] = max(0, min(255, output[produced - 1] + delta))
                    produced += 1
            branches[f'delta{bits}_samples'] += block
    if position != len(data):
        raise ValueError('ABT profile refuses unexplained trailing bytes')
    return ABTAudio(bytes(output), declared, rate, block, data[5:8], position,
                    len(data), hashlib.sha256(data).hexdigest(), work,
                    tuple(sorted(branches.items())))


def inspect_abt(path, *, max_output_bytes=MAX_OUTPUT_BYTES,
                max_work_units=MAX_WORK_UNITS):
    """Read a bounded regular source and return only decoded metadata/hashes."""
    from .media import _snapshot
    return decode_abt(_snapshot(path, MAX_SOURCE_BYTES),
                      max_output_bytes=max_output_bytes,
                      max_work_units=max_work_units).report()
