"""Bounded Castles II SLB directories and an explicit original-DOS sound profile.

SLB has no global magic. Callers must select the game context. Parsing a directory
is distinct from interpreting its opaque sample payloads. The explicit playback
profile binds the two corpus-observed footer selectors to the original player's
Sound Blaster time constants; the footer is not a literal sample rate in kHz.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import struct

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SLOTS = 65536
PLAYBACK_PROFILE = 'castles2-ail-sb-mono-v1'
# Original C2CDTOOL's selector branches, not a fitted conversion from footer Hz.
_TIME_CONSTANTS = {11: 166, 22: 211}


def _uint(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be a bounded unsigned integer')
    return value


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _ratio(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


@dataclass(frozen=True)
class SLBSlot:
    slot: int
    key: int
    offset: int
    length: int

    @property
    def occupied(self):
        return self.key != 0


@dataclass(frozen=True)
class SLBLibrary:
    footer_selector: int
    table_offset: int
    slots: tuple[SLBSlot, ...]
    source_sha256: str
    _source: bytes = field(repr=False, compare=False)

    def _slot(self, slot):
        _uint(slot, 'slot', len(self.slots) - 1)
        row = self.slots[slot]
        if not row.occupied:
            raise ValueError('Selected SLB directory slot is empty')
        return row

    def sample(self, slot):
        """Return one opaque payload by original directory slot, with no RNG choice."""
        row = self._slot(slot)
        return self._source[row.offset:row.offset + row.length]

    def lookup_slots(self, key):
        """Return matching slots in native hash/probe order; do not select a variant.

        The qualified positive-key domain avoids guessing the old signed long
        remainder behavior after multiplication overflow. Traversal is bounded
        even when a structurally admitted table has no empty terminating slot.
        """
        _uint(key, 'key', 0x7fffffff // 73)
        if not key:
            raise ValueError('Zero is the empty-slot key')
        start = key * 73 % len(self.slots)
        matches = []
        for step in range(len(self.slots)):
            row = self.slots[(start + step) % len(self.slots)]
            if not row.occupied:
                return tuple(matches)
            if row.key == key:
                matches.append(row.slot)
        raise ValueError('SLB lookup has no empty-slot terminator in one table cycle')

    def report(self):
        counts = Counter(row.key for row in self.slots if row.occupied)
        return {
            'format': 'fdisbull-castles2-slb-inspection-1',
            'adapter': 'castles2-slb',
            'source': {'bytes': len(self._source), 'sha256': self.source_sha256},
            'context_required': 'Castles II SLB; there is no global signature',
            'footer_selector': self.footer_selector,
            'footer_offset': len(self._source) - 12,
            'directory_offset': self.table_offset,
            'directory_slot_count': len(self.slots),
            'occupied_slots': sum(row.occupied for row in self.slots),
            'empty_slots': sum(not row.occupied for row in self.slots),
            'payload_bytes': self.table_offset,
            'payload_partition_exact': True,
            'duplicate_keys': [{'key': key, 'variants': count}
                               for key, count in sorted(counts.items()) if count > 1],
            'variant_selection': 'Original consumer chooses rand() % matching count; caller must select a slot explicitly.',
            'slots': [{'slot': row.slot, 'key': row.key, 'offset': row.offset,
                       'length': row.length, 'occupied': row.occupied,
                       'sha256': _sha(self.sample(row.slot)) if row.occupied else None}
                      for row in self.slots],
            'qualification': 'complete bounded directory and payload-extent checks; payload interpretation requires an explicit playback profile',
            'input_executed': False, 'native_runtime_tested': False,
            'full_audio_decode': False, 'rewrite_supported': False,
        }


def decode_slb(data, *, max_source_bytes=MAX_SOURCE_BYTES, max_slots=MAX_SLOTS):
    """Validate the recovered footer/table profile while preserving slot identity."""
    _uint(max_source_bytes, 'max_source_bytes', MAX_SOURCE_BYTES)
    _uint(max_slots, 'max_slots', MAX_SLOTS)
    if not max_source_bytes or not max_slots:
        raise ValueError('SLB limits must be positive')
    if type(data) is not bytes:
        raise ValueError('SLB input must be immutable bytes')
    if len(data) > max_source_bytes:
        raise ValueError('SLB source byte budget exceeded')
    if len(data) < 24:
        raise ValueError('SLB requires a footer and at least one directory slot')
    selector, count, table = struct.unpack_from('<III', data, len(data) - 12)
    if not 1 <= count <= max_slots:
        raise ValueError('SLB directory slot budget exceeded or empty table')
    if table + count * 12 + 12 != len(data):
        raise ValueError('SLB directory/footer extent mismatch')
    slots = []
    occupied = []
    for slot in range(count):
        key, offset, length = struct.unpack_from('<III', data, table + slot * 12)
        row = SLBSlot(slot, key, offset, length)
        if not key and not offset and not length:
            slots.append(row)
            continue
        if not key or not length or offset + length > table:
            raise ValueError('SLB occupied slot has invalid key, size or payload extent')
        slots.append(row)
        occupied.append(row)
    if not occupied:
        raise ValueError('SLB contains no occupied sample slots')
    position = 0
    for row in sorted(occupied, key=lambda row: row.offset):
        if row.offset != position:
            raise ValueError('SLB payload extents overlap or leave an unexplained gap')
        position += row.length
    if position != table:
        raise ValueError('SLB payload does not end at its directory')
    return SLBLibrary(selector, table, tuple(slots), _sha(data), data)


def inspect_slb(data, **limits):
    return decode_slb(data, **limits).report()


@dataclass(frozen=True)
class SLBPlayback:
    library: SLBLibrary
    profile: str
    time_constant: int

    @property
    def ideal_device_rate(self):
        return Fraction(1_000_000, 256 - self.time_constant)

    @property
    def wave_sample_rate(self):
        return 1_000_000 // (256 - self.time_constant)

    def report(self):
        return {
            'format': 'fdisbull-castles2-slb-playback-1',
            'adapter': 'castles2-slb-playback', 'profile': self.profile,
            'source_sha256': self.library.source_sha256,
            'footer_selector': self.library.footer_selector,
            'encoding': 'pcm_u8', 'bits': 8, 'channels': 1,
            'time_constant': self.time_constant,
            'ideal_device_rate': _ratio(self.ideal_device_rate),
            'wave_sample_rate': self.wave_sample_rate,
            'wave_rate_policy': 'floor(1000000 / (256 - time_constant)); an integer WAV adapter, not exact hardware timing',
            'playback_buffer_bytes': 15000,
            'duration_scope': 'Ideal payload duration excludes setup, double-buffer refill, DMA drain and caller polling/cleanup latency; actual completion requires a separate native observation.',
            'driver_scope': 'Supplied original SBDIG.ADV unsigned 8-bit mono path; other drivers, stereo, loops and interruption behavior remain unqualified.',
            'variant_selection': 'explicit original directory slot; native randomized key selection is not evaluated',
            'qualification': 'explicit original-DOS AIL/Sound Blaster mono profile; actual current-input playback remains separately qualified',
            'input_executed': False, 'native_runtime_tested': False,
        }

    def sample_report(self, slot):
        row = self.library._slot(slot)
        value = self.report()
        value.update(slot=slot, key=row.key, source_offset=row.offset,
                     samples=row.length, pcm_bytes=row.length,
                     pcm_sha256=_sha(self.library.sample(slot)),
                     ideal_device_duration_seconds=_ratio(Fraction(row.length, 1) / self.ideal_device_rate),
                     wave_duration_seconds=_ratio(Fraction(row.length, self.wave_sample_rate)))
        return value


def bind_slb_playback(library, *, profile=PLAYBACK_PROFILE):
    """Bind only corpus-observed selectors to this explicitly selected consumer."""
    if type(library) is not SLBLibrary:
        raise ValueError('Expected a decoded SLBLibrary')
    if profile != PLAYBACK_PROFILE:
        raise ValueError('Unsupported Castles II SLB playback profile')
    if library.footer_selector not in _TIME_CONSTANTS:
        raise ValueError('SLB footer selector is outside the qualified 11/22 playback profile')
    return SLBPlayback(library, profile, _TIME_CONSTANTS[library.footer_selector])
