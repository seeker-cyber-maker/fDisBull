"""Bounded independent ZIP segments, including concatenated and SFX archives.

No target execution. Offsets and opaque gaps are retained; directories are not
flattened across archive boundaries. ZIP64, spanning, encryption and links refuse.
"""
from __future__ import annotations
import hashlib
import io
from pathlib import PurePosixPath
import re
import stat
import struct
import unicodedata
import zipfile


def safe_name(name: str) -> str:
    """Portable relative destination, without device names or normalization tricks."""
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise ValueError('invalid member name')
    name = unicodedata.normalize('NFC', name.replace('\\', '/'))
    parts = name.rstrip('/').split('/')
    if any(not p or p in ('.', '..') or p[-1:] in (' ', '.') or
           re.search(r'[\x00-\x1f\x7f:<>"|?*]', p) or
           re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p)
           for p in parts):
        raise ValueError('unsafe archive member name')
    return str(PurePosixPath(*parts))


def zip_segments(data: bytes, *, max_entries: int = 10000) -> dict:
    """Find independently validated ZIP directories, not raw PK marker hits."""
    if not isinstance(data, bytes) or len(data) > 256 * 1024 * 1024:
        raise ValueError('ZIP input exceeds 256 MiB')
    if type(max_entries) is not int or not 1 <= max_entries <= 100000:
        raise ValueError('invalid ZIP entry budget')
    segments, rejected, at, scanned, total = [], [], 0, 0, 0
    while (at := data.find(b'PK\x05\x06', at)) >= 0:
        end_at = at
        at += 4
        scanned += 1
        if scanned > 4096:
            raise ValueError('ZIP directory candidate budget exceeded')
        try:
            if end_at + 22 > len(data):
                raise ValueError('truncated EOCD')
            disk, cd_disk, n_disk, n, cd_size, cd_off, comment = struct.unpack_from('<4H2IH', data, end_at+4)
            if disk or cd_disk or n != n_disk or n == 65535 or cd_size == 0xffffffff or cd_off == 0xffffffff:
                raise ValueError('spanned or ZIP64 archive unsupported')
            end = end_at + 22 + comment
            start = end_at - cd_size - cd_off
            if start < 0 or end > len(data) or n > max_entries - total:
                raise ValueError('invalid directory extent or entry budget')
            central, pos, members, ranges, names = start+cd_off, start+cd_off, [], [], set()
            for index in range(n):
                if pos+46 > end_at or data[pos:pos+4] != b'PK\x01\x02':
                    raise ValueError('invalid central directory')
                fields = struct.unpack_from('<6H3I5H2I', data, pos+4)
                made, needed, flags, method, tm, date, crc, packed, size, nl, el, cl, dn, ia, ea, local = fields
                if flags & (1 | 0x40 | 0x2000) or method not in (0, 8) or dn or needed >= 45:
                    raise ValueError('unsupported ZIP compression/encryption/version')
                if pos+46+nl+el+cl > end_at:
                    raise ValueError('directory member exceeds EOCD')
                raw_name = data[pos+46:pos+46+nl]
                name = raw_name.decode('utf-8' if flags & 0x800 else 'cp437')
                safe = safe_name(name)
                mode = ea >> 16
                if (made >> 8 == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError('nonregular ZIP member')
                directory = name.endswith('/')
                if directory and (size or packed):
                    raise ValueError('directory carries payload')
                if safe.casefold() in names:
                    raise ValueError('duplicate/case-colliding ZIP path')
                names.add(safe.casefold())
                lp = start+local
                if lp < start or lp+30 > central or data[lp:lp+4] != b'PK\x03\x04':
                    raise ValueError('invalid local header')
                ver, lf, lm, lt, ld, lc, lz, lu, ln, le = struct.unpack_from('<5H3I2H', data, lp+4)
                payload = lp+30+ln+le
                if (lf != flags or lm != method or payload+packed > central or
                    data[lp+30:lp+30+ln] != raw_name):
                    raise ValueError('local/central header disagreement')
                if not flags & 8 and (lc, lz, lu) != (crc, packed, size):
                    raise ValueError('local/central size or CRC disagreement')
                record_end = payload+packed
                if flags & 8:
                    descriptor = record_end
                    if data[descriptor:descriptor+4] == b'PK\x07\x08':
                        descriptor += 4
                    if descriptor+12 > central or struct.unpack_from('<3I', data, descriptor) != (crc,packed,size):
                        raise ValueError('data descriptor disagrees with central directory')
                    record_end = descriptor+12
                ranges.append((lp, record_end))
                members.append(dict(index=index, name=safe, directory=directory, size=size,
                                    compressed_size=packed, method=method, crc32=f'{crc:08x}',
                                    local_header_offset=lp, data_offset=payload))
                pos += 46+nl+el+cl
            if pos != end_at:
                raise ValueError('unaccounted central directory bytes')
            for a,b in zip(sorted(ranges), sorted(ranges)[1:]):
                if b[0] < a[1]:
                    raise ValueError('overlapping local members')
            # Confirm the independent standard reader agrees on the chosen segment.
            with zipfile.ZipFile(io.BytesIO(data[start:end])) as z:
                if len(z.infolist()) != n:
                    raise ValueError('ZIP reader count disagreement')
            internal_gaps, cursor = [], start
            for low, high in sorted(ranges):
                if cursor < low: internal_gaps.append(dict(offset=cursor,bytes=low-cursor))
                cursor = high
            if cursor < central: internal_gaps.append(dict(offset=cursor,bytes=central-cursor))
            segments.append(dict(start=start, end=end, central_offset=central, opaque_ranges=internal_gaps,
                                 entries=members, bytes=end-start,
                                 sha256=hashlib.sha256(data[start:end]).hexdigest()))
            total += n
        except (ValueError, UnicodeError, struct.error, zipfile.BadZipFile) as exc:
            rejected.append(dict(offset=end_at, reason=str(exc)))
    segments.sort(key=lambda s:(s['start'],-s['end']))
    outermost, nested = [], []
    for segment in segments:
        if outermost and outermost[-1]['start'] <= segment['start'] and segment['end'] <= outermost[-1]['end']:
            nested.append(dict(start=segment['start'],end=segment['end'],parent_start=outermost[-1]['start']))
        else:
            outermost.append(segment)
    segments = outermost
    for a,b in zip(segments, segments[1:]):
        if b['start'] < a['end']:
            raise ValueError('overlapping independent ZIP candidates')
    gaps, previous = [], 0
    for segment in segments:
        if segment['start'] > previous:
            gaps.append(dict(offset=previous, bytes=segment['start']-previous))
        previous = segment['end']
    if previous < len(data):
        gaps.append(dict(offset=previous, bytes=len(data)-previous))
    if not segments:
        raise ValueError('no admitted ZIP segment' + (': '+rejected[0]['reason'] if rejected else ''))
    return dict(format='zip-segments', segments=segments, entries=sum(len(s['entries']) for s in segments),
                opaque_ranges=gaps, rejected_candidates=rejected,nested_candidates=nested,
                complete_byte_accounting=not gaps and not rejected and not any(s['opaque_ranges'] for s in segments))


def zip_payload(data: bytes, segment: dict, member: dict, *, limit: int) -> bytes:
    if type(limit) is not int or not 0 <= member['size'] <= limit <= 512*1024*1024:
        raise ValueError('ZIP member output budget exceeded')
    with zipfile.ZipFile(io.BytesIO(data[segment['start']:segment['end']])) as z:
        info = z.infolist()[member['index']]
        with z.open(info) as f:
            result = f.read(limit+1)
            if len(result) != member['size'] or f.read(1):
                raise ValueError('ZIP expanded size mismatch')
    # Reading to EOF verifies the central CRC in zipfile.
    return result
