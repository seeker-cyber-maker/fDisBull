"""Bounded classic IWAD/PWAD directory snapshots.

Directory order, duplicate names, aliases and empty markers are preserved.
This reader neither executes content nor treats a lookup as a semantic claim.
Format reference: id Software linuxdoom-1.10/w_wad.{h,c} (see docs/WAD_MEDIA.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import struct

MAX_SOURCE = 64 * 1024 * 1024
MAX_LUMPS = 100_000


def wad_name(raw: bytes) -> str:
    return raw.split(b'\0', 1)[0].decode('ascii', errors='backslashreplace')


@dataclass(frozen=True)
class Lump:
    index: int
    offset: int
    size: int
    name_bytes: bytes

    @property
    def name(self) -> str:
        return wad_name(self.name_bytes)

    @property
    def key(self) -> bytes:
        # Compare the meaningful name, case-insensitively; keep original bytes.
        return self.name_bytes.split(b'\0', 1)[0].upper()

    def payload(self, source: bytes) -> bytes:
        return source[self.offset:self.offset + self.size]

    def summary(self, source: bytes | None = None) -> dict:
        result = dict(index=self.index, name=self.name, offset=self.offset, size=self.size)
        if source is not None:
            result['sha256'] = sha256(self.payload(source)).hexdigest()
        return result


@dataclass(frozen=True)
class WadArchive:
    data: bytes
    kind: str
    directory_offset: int
    lumps: tuple[Lump, ...]

    @classmethod
    def parse(cls, data: bytes, *, max_lumps: int = MAX_LUMPS) -> 'WadArchive':
        if not isinstance(data, bytes):
            raise TypeError('WAD requires immutable bytes')
        if type(max_lumps) is not int or not 1 <= max_lumps <= MAX_LUMPS:
            raise ValueError('invalid WAD lump budget')
        if not 12 <= len(data) <= MAX_SOURCE or data[:4] not in (b'IWAD', b'PWAD'):
            raise ValueError('not a bounded classic IWAD/PWAD')
        count, directory = struct.unpack_from('<ii', data, 4)
        if not 0 <= count <= max_lumps or directory < 12 or directory + count * 16 > len(data):
            raise ValueError('WAD directory bounds')
        rows = []
        for index in range(count):
            offset, size, name = struct.unpack_from('<ii8s', data, directory + 16 * index)
            if offset < 0 or size < 0 or offset + size > len(data):
                raise ValueError(f'lump {index} outside source')
            rows.append(Lump(index, offset, size, name))
        return cls(data, data[:4].decode('ascii'), directory, tuple(rows))

    def last(self, name: str) -> Lump | None:
        key = name.encode('ascii').upper()
        return next((x for x in reversed(self.lumps) if x.key == key), None)
