"""Bounded MADS containers: HAG, MADSPACK 1.0/2.0, FAB and DCL.

Read-only format recovery, not a game engine. ScummVM v2.8.1's MADS readers
were consulted as format references; see docs/MADS_MEDIA_RUNTIME.md for provenance.
Original resources and decompressed bytes are private target data.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import struct

MAX_ARCHIVE = 128 * 1024 * 1024
MAX_RESOURCE = 16 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_int(value, name, low, high):
    require(type(value) is int and low <= value <= high, f'{name} outside {low}..{high}')
    return value


def snapshot(source, limit=MAX_RESOURCE):
    if type(source) is bytes:
        require(len(source) <= limit, 'MADS input exceeds size limit')
        return source
    from .media import _snapshot
    return _snapshot(source, limit)


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


# Compatibility re-export; the codec is reusable without MADS containers.
from .codec_fab import decode_fab


@dataclass(frozen=True)
class PackSection:
    index: int
    compression: int
    priority: int
    offset: int
    stored_size: int
    consumed_size: int
    data: bytes

    def metadata(self):
        return dict(index=self.index, compression=self.compression, priority=self.priority,
                    file_offset=self.offset, stored_size=self.stored_size,
                    consumed_size=self.consumed_size, opaque_tail_bytes=self.stored_size-self.consumed_size,
                    decoded_size=len(self.data), decoded_sha256=sha256(self.data).hexdigest())


@dataclass(frozen=True)
class MadsPack:
    source: bytes
    sections: tuple[PackSection, ...]
    end: int
    version: str = "2.0"

    @classmethod
    def read(cls, source):
        raw = snapshot(source)
        require(len(raw) >= 176 and raw[:14] in (b'MADSPACK 1.0\x1a\x00', b'MADSPACK 2.0\x1a\x00'), 'not MADSPACK 1.0/2.0')
        version = raw[9:12].decode('ascii')
        count = struct.unpack_from('<H', raw, 14)[0]
        require(1 <= count <= 16, 'MADSPACK section count outside fixed directory')
        at, expanded, sections = 176, 0, []
        for index in range(count):
            kind, priority, size, packed = struct.unpack_from('<BBII', raw, 16 + 10*index)
            require(kind in (0, 1, 3), 'unknown MADSPACK compression')
            expanded += size
            require(expanded <= MAX_EXPANDED and packed <= len(raw)-at,
                    'MADSPACK expansion or source extent exceeds bounds')
            stored = raw[at:at+packed]
            if kind == 0:
                require(size == packed, 'stored MADSPACK sizes disagree')
                decoded, consumed = stored, packed
            elif kind == 3 or (kind == 1 and version == '1.0'):
                from .codec_dcl import decode_dcl
                decoded, consumed = decode_dcl(stored, size)
            else:
                decoded, consumed = decode_fab(stored, size)
            sections.append(PackSection(index, kind, priority, at, packed, consumed, decoded))
            at += packed
        return cls(raw, tuple(sections), at, version)

    def metadata(self):
        return dict(format='madspack-' + self.version, source_sha256=sha256(self.source).hexdigest(),
                    size=len(self.source), opaque_tail_bytes=len(self.source)-self.end,
                    sections=[dict(part.metadata(), codec=(
                        'raw' if part.compression == 0 else 'pkware-dcl' if
                        part.compression == 3 or self.version == '1.0' else 'fab'))
                        for part in self.sections], execution=False)


@dataclass(frozen=True)
class HagMember:
    index: int
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class HagArchive:
    source: bytes
    members: tuple[HagMember, ...]

    @classmethod
    def read(cls, source):
        raw = snapshot(source, MAX_ARCHIVE)
        require(len(raw) >= 18 and raw[:16] == b'MADSCONCAT 1.0\x1a\x00', 'not MADSCONCAT 1.0 HAG')
        count = struct.unpack_from('<H', raw, 16)[0]
        table_end = 18 + 22*count
        require(1 <= count <= 32768 and table_end <= len(raw), 'truncated/oversized HAG directory')
        members, intervals = [], []
        for index in range(count):
            offset, size, name_raw = struct.unpack_from('<II14s', raw, 18 + 22*index)
            require(b'\0' in name_raw, 'HAG member name lacks terminator')
            name = name_raw.split(b'\0', 1)[0].decode('ascii', 'strict')
            require(name not in ('', '.', '..') and all(32 <= ord(c) < 127 and c not in '/\\:' for c in name),
                    'unsafe HAG member name')
            require(table_end <= offset <= len(raw) and size <= len(raw)-offset,
                    'HAG member outside payload')
            members.append(HagMember(index, name, offset, size))
            if size:
                intervals.append((offset, offset+size))
        # Exact alias ranges are allowed and retain distinct directory identities.
        extents = sorted(set(intervals))
        require(all(a[1] <= b[0] for a, b in zip(extents, extents[1:])), 'partially overlapping HAG members')
        return cls(raw, tuple(members))

    def select(self, member):
        if type(member) is int:
            bounded_int(member, 'HAG member index', 0, len(self.members)-1)
            selected = self.members[member]
        else:
            require(type(member) is str and member, 'select HAG member name or integer index')
            matches = [item for item in self.members if item.name.casefold() == member.casefold()]
            require(len(matches) == 1, 'HAG member absent or ambiguous; select an index')
            selected = matches[0]
        require(selected.size <= MAX_RESOURCE, 'HAG member exceeds decoder resource limit')
        return selected, self.source[selected.offset:selected.offset+selected.size]

    def metadata(self):
        return dict(format='mads-hag-1.0', source_sha256=sha256(self.source).hexdigest(),
                    size=len(self.source), member_count=len(self.members),
                    members=[dict(index=m.index, name=m.name, offset=m.offset, size=m.size) for m in self.members],
                    execution=False)


def read_cnd(source):
    """Inspect saved conversation defaults/import slots, not live engine pointers."""
    pack = MadsPack.read(source)
    header = Cursor(pack.sections[0].data)
    current, flags_count, variables_count, imports_count = (header.u16() for _ in range(4))
    # Remaining header fields include saved host/runtime workspace. Do not use
    # its apparent live-list counts to allocate or validate initial defaults.
    opaque_header_bytes = header.end - header.at
    require(len(pack.sections) == (4 if imports_count else 3), 'CND section count disagrees with imports')
    pos = 1
    imports = ()
    if imports_count:
        raw = pack.sections[pos].data
        require(len(raw) == 2*imports_count, 'CND imports length mismatch')
        imports = tuple(v[0] for v in struct.iter_unpack('<H', raw))
        require(all(v < variables_count for v in imports), 'CND import variable outside table')
        pos += 1
    flags = pack.sections[pos].data
    variables = pack.sections[pos+1].data
    require(len(flags) == 2*flags_count and len(variables) == 6*variables_count,
            'CND flags/variables length mismatch')
    return dict(format='mads-conversation-defaults-1', source_sha256=sha256(pack.source).hexdigest(),
                current_node_raw=current, imports=list(imports), variable_count=variables_count,
                opaque_header_bytes=opaque_header_bytes,
                entry_flag_count=flags_count,
                variables=[dict(index=i, stored_kind=k, value=v, stored_segment=s, live_pointer_bound=False)
                           for i, (k, v, s) in enumerate(struct.iter_unpack('<HhH', variables))],
                entry_flags=[v[0] for v in struct.iter_unpack('<H', flags)],
                pack=pack.metadata(), runtime_state=False)
