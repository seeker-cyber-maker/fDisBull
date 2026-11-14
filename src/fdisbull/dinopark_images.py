"""Bounded DinoPark UNC2/UNCS actors and UNCP indexed pictures.

These authored readers preserve pixels, opacity, six-bit palettes and opaque
sequence data. They do not execute a script, synthesize an external actor
palette, emulate clipping or claim original-game compatibility. Hash-only
descriptions are suitable for reports; decoded buffers stay caller-owned.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

MAX_SOURCE = 8 * 1024 * 1024
MAX_SPRITES = 8192
MAX_SEQUENCES = 8192
MAX_FRAMES = 4096
MAX_PIXELS = 16 * 1024 * 1024
MAX_FRAME_PIXELS = 1024 * 1024
MAX_WORK = 128 * 1024 * 1024


@dataclass(frozen=True)
class Sprite:
    index: int
    offset: int
    width: int
    height: int
    bounds: tuple[int, int, int, int]
    commands: bytes
    colors: bytes
    indices: bytes
    opacity: bytes


@dataclass(frozen=True)
class ActorFile:
    magic: str
    sprites: tuple[Sprite, ...]
    sequences: tuple[bytes, ...]
    sequence_offset: int
    sequence_bytes: int
    directory_offset: int | None
    sequence_trailer: bytes
    source_size: int
    source_sha256: str


@dataclass(frozen=True)
class PictureFrame:
    index: int
    offset: int
    declared_size: int
    width: int
    height: int
    stride: int
    palette6: bytes
    row_data: bytes
    indices: bytes
    encoded_bytes: int


@dataclass(frozen=True)
class PictureFile:
    frames: tuple[PictureFrame, ...]
    source_size: int
    source_sha256: str


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _limit(value, maximum, name):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{name} must be a positive integer at most {maximum}')
    return value


def _source(data, limit):
    _limit(limit, MAX_SOURCE, 'max_source_bytes')
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError('Decoder source must be bytes, bytearray or memoryview')
    size = data.nbytes if isinstance(data, memoryview) else len(data)
    if size > limit:
        raise ValueError('DinoPark source byte budget exceeded')
    return bytes(data)


def _sprite_header(data, start, end):
    if start + 16 > end:
        raise ValueError('Truncated ACT sprite header')
    width, height, left, right, top, bottom, commands, colors = struct.unpack_from('<8H', data, start)
    if not 1 <= width <= 4096 or not 1 <= height <= 255 or width * height > MAX_FRAME_PIXELS:
        raise ValueError('Unsupported ACT sprite geometry')
    finish = start + 16 + commands + colors
    if not commands or finish > end:
        raise ValueError('Invalid ACT sprite payload extent')
    return (start, finish, width, height, (left, right, top, bottom), commands, colors)


def _sprite(data, entry, index):
    start, end, width, height, bounds, command_size, _ = entry
    commands = data[start + 16:start + 16 + command_size]
    colors = data[start + 16 + command_size:end]
    pixels = bytearray(width * height)
    opacity = bytearray(width * height)
    x = y = used = 0
    observed_left, observed_top, observed_right, observed_bottom = width, height, -1, -1
    for position, token in enumerate(commands):
        if token == 0:
            if position != len(commands) - 1:
                raise ValueError('Bytes after ACT sprite terminator')
            break
        if token & 0x80:
            y += 1
            x = 0
        count = token & 0x3f
        if y >= height or x + count > width:
            raise ValueError('ACT command leaves declared canvas')
        if token & 0x40:
            if used + count > len(colors):
                raise ValueError('ACT sprite color underflow')
            at = y * width + x
            pixels[at:at + count] = colors[used:used + count]
            opacity[at:at + count] = b'\xff' * count
            used += count
            if count:
                observed_left, observed_right = min(observed_left, x), max(observed_right, x + count - 1)
                observed_top, observed_bottom = min(observed_top, y), max(observed_bottom, y)
        x += count
    else:
        raise ValueError('Missing ACT sprite terminator')
    if used != len(colors):
        raise ValueError('Unconsumed ACT sprite colors')
    if observed_right >= 0 and bounds != (observed_left, observed_right, observed_top, observed_bottom):
        raise ValueError('ACT drawn content differs from declared bounds')
    return Sprite(index, start, width, height, bounds, commands, colors, bytes(pixels), bytes(opacity))


def decode_act(data, *, max_source_bytes=MAX_SOURCE, max_sprites=MAX_SPRITES,
               max_sequences=MAX_SEQUENCES, max_pixels=MAX_PIXELS, max_work=MAX_WORK):
    """Decode indexed actor sprites and masks; preserve sequences as opaque data.

    Before allocating pixel buffers, preflight all record extents and reserve
    cumulative pixels and conservative byte-copy/command work. The supplied
    profile supports UNC2's exact trailing offset directory and legacy UNCS.
    """
    raw = _source(data, max_source_bytes)
    for value, maximum, name in ((max_sprites, MAX_SPRITES, 'max_sprites'),
            (max_sequences, MAX_SEQUENCES, 'max_sequences'), (max_pixels, MAX_PIXELS, 'max_pixels'),
            (max_work, MAX_WORK, 'max_work')):
        _limit(value, maximum, name)
    if len(raw) < 10 or raw[:4] not in (b'UNC2', b'UNCS'):
        raise ValueError('Expected an UNC2/UNCS actor header')
    header = 14 if raw[:4] == b'UNC2' else 10
    if len(raw) < header:
        raise ValueError('Truncated ACT container header')
    count = struct.unpack_from('<H', raw, 4)[0]
    sequences, sequence_bytes = struct.unpack_from('<HH', raw, header - 4)
    if not 1 <= count <= max_sprites or sequences > max_sequences:
        raise ValueError('ACT sprite/sequence count budget exceeded')
    directory = struct.unpack_from('<I', raw, 6)[0] if header == 14 else None
    end = directory if directory is not None else len(raw)
    if not header <= end <= len(raw) or directory is not None and directory + 4 * count != len(raw):
        raise ValueError('ACT directory extent mismatch')
    entries, at, pixels, work = [], header, 0, sequence_bytes
    for _ in range(count):
        entry = _sprite_header(raw, at, end)
        entries.append(entry)
        start, at, width, height, _, commands, colors = entry
        pixels += width * height
        work += 4 * width * height + commands + 2 * colors
        if pixels > max_pixels or work > max_work:
            raise ValueError('ACT decoded pixel/work budget exceeded')
    if directory is not None:
        for index, entry in enumerate(entries):
            if struct.unpack_from('<I', raw, directory + 4 * index)[0] != entry[0]:
                raise ValueError('ACT directory differs from sequential sprite records')
    if end - at != sequence_bytes:
        raise ValueError('ACT sequence area extent mismatch')
    sequence_offset = at
    sequence_ranges = []
    for _ in range(sequences):
        if at + 2 > end:
            raise ValueError('Truncated ACT sequence length')
        length = struct.unpack_from('<H', raw, at)[0]
        at += 2
        if not length or at + length > end:
            raise ValueError('Invalid ACT sequence extent')
        sequence_ranges.append((at, at + length))
        at += length
    trailer = raw[at:end]
    if len(trailer) != (1 if sequences else 0):
        raise ValueError('Unsupported ACT sequence trailer')
    sprites = tuple(_sprite(raw, entry, index) for index, entry in enumerate(entries))
    return ActorFile(raw[:4].decode('ascii'), sprites, tuple(raw[a:b] for a, b in sequence_ranges),
        sequence_offset, sequence_bytes, directory, trailer, len(raw), _sha(raw))


def _picture_rows(stream, expected, compressed):
    if not compressed:
        if len(stream) != expected:
            raise ValueError('PIC raw rows differ from the even-stride extent')
        return stream
    output = bytearray(expected)
    source = target = 0
    while source < len(stream):
        token = stream[source]
        source += 1
        count = token + 1 if token < 128 else 257 - token
        if target + count > expected:
            raise ValueError('PIC run exceeds decoded row extent')
        if token < 128:
            if source + count > len(stream):
                raise ValueError('Truncated PIC literal run')
            output[target:target + count] = stream[source:source + count]
            source += count
        else:
            if source >= len(stream):
                raise ValueError('Truncated PIC repeat run')
            output[target:target + count] = bytes([stream[source]]) * count
            source += 1
        target += count
    if target != expected:
        raise ValueError('PIC compressed rows do not fill declared geometry')
    return bytes(output)


def decode_pic(data, *, max_source_bytes=MAX_SOURCE, max_frames=MAX_FRAMES,
               max_pixels=MAX_PIXELS, max_work=MAX_WORK):
    """Decode every UNCP frame, preserving raw six-bit palette and even stride.

    Widths <=64 use raw rows; wider frames use the recovered literal/repeat
    stream. Row padding is retained in row_data and removed only in indices.
    No RGB expansion policy or original display calibration is assumed.
    """
    raw = _source(data, max_source_bytes)
    for value, maximum, name in ((max_frames, MAX_FRAMES, 'max_frames'),
            (max_pixels, MAX_PIXELS, 'max_pixels'), (max_work, MAX_WORK, 'max_work')):
        _limit(value, maximum, name)
    if len(raw) < 8 or raw[:4] != b'UNCP':
        raise ValueError('Expected an UNCP picture header')
    first = struct.unpack_from('<I', raw, 4)[0]
    if first < 8 or (first - 4) % 4 or first > len(raw):
        raise ValueError('Invalid PIC directory extent')
    count = (first - 4) // 4
    if count > max_frames:
        raise ValueError('PIC frame count budget exceeded')
    offsets = tuple(struct.unpack_from('<I', raw, 4 + 4 * i)[0] for i in range(count))
    if offsets[0] != first or any(a >= b for a, b in zip(offsets, offsets[1:])):
        raise ValueError('PIC offsets must be strictly increasing after the directory')
    entries, pixels, work = [], 0, 0
    for index, start in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(raw)
        if not first <= start < end <= len(raw) or start + 778 > end:
            raise ValueError('Truncated or overlapping PIC frame')
        size, width, height = struct.unpack_from('<IHH', raw, start)
        if size + 4 != end - start:
            raise ValueError('PIC declared frame extent mismatch')
        stride = (width + 1) & ~1
        if not 1 <= width <= 4096 or not 1 <= height <= 4096 or stride * height > MAX_FRAME_PIXELS:
            raise ValueError('Unsupported PIC frame geometry')
        length = struct.unpack_from('<H', raw, start + 776)[0]
        if start + 778 + length != end:
            raise ValueError('PIC encoded stream extent mismatch')
        if any(value > 63 for value in raw[start + 8:start + 776]):
            raise ValueError('PIC palette is outside the six-bit profile')
        pixels += stride * height
        work += 4 * stride * height + 2 * length + 768
        if pixels > max_pixels or work > max_work:
            raise ValueError('PIC decoded pixel/work budget exceeded')
        entries.append((start, end, size, width, height, stride, length))
    frames = []
    for index, (start, end, size, width, height, stride, length) in enumerate(entries):
        rows = _picture_rows(raw[start + 778:end], stride * height, width > 64)
        indices = rows if stride == width else b''.join(rows[y * stride:y * stride + width] for y in range(height))
        frames.append(PictureFrame(index, start, size, width, height, stride,
            raw[start + 8:start + 776], rows, indices, length))
    return PictureFile(tuple(frames), len(raw), _sha(raw))


def palette_rgb(palette6, *, policy):
    """Expand a six-bit palette using an explicitly selected preview policy."""
    if not isinstance(palette6, bytes) or len(palette6) != 768 or any(v > 63 for v in palette6):
        raise ValueError('Expected a 768-byte six-bit RGB palette')
    if policy == 'replicate6':
        return bytes((v << 2) | (v >> 4) for v in palette6)
    if policy == 'shift2':
        return bytes(v << 2 for v in palette6)
    raise ValueError('Palette policy must be replicate6 or shift2')


def describe_act(actor):
    """Describe decoded identities without returning source or pixel buffers."""
    return dict(format='fdisbull-dinopark-act-decoding-1', decoder='dinopark-act',
        source=dict(size=actor.source_size, sha256=actor.source_sha256), variant=actor.magic,
        sprites=[dict(index=s.index, file_offset=s.offset, width=s.width, height=s.height,
            bounds=list(s.bounds), command_bytes=len(s.commands), color_bytes=len(s.colors),
            indices_sha256=_sha(s.indices), opacity_sha256=_sha(s.opacity),
            commands_sha256=_sha(s.commands), colors_sha256=_sha(s.colors)) for s in actor.sprites],
        sequence_count=len(actor.sequences), sequence_bytes=actor.sequence_bytes,
        sequence_offset=actor.sequence_offset, directory_offset=actor.directory_offset,
        sequence_sha256=[_sha(s) for s in actor.sequences],
        sequence_trailer_bytes=len(actor.sequence_trailer), sequence_trailer_sha256=_sha(actor.sequence_trailer),
        decoded_pixels=sum(s.width * s.height for s in actor.sprites), input_executed=False,
        full_sprite_decode=True, sequence_semantics_decoded=False, native_runtime_tested=False,
        unknowns=['Actor palettes are external; opaque sequence control flow, clipping and game playback are not qualified.'])


def describe_pic(picture):
    """Describe complete indexed decoding without source, pixel or palette bytes."""
    return dict(format='fdisbull-dinopark-pic-decoding-1', decoder='dinopark-pic',
        source=dict(size=picture.source_size, sha256=picture.source_sha256),
        frames=[dict(index=f.index, file_offset=f.offset, width=f.width, height=f.height,
            stride=f.stride, encoded_bytes=f.encoded_bytes, indices_sha256=_sha(f.indices),
            padded_rows_sha256=_sha(f.row_data), palette6_sha256=_sha(f.palette6)) for f in picture.frames],
        decoded_pixels=sum(f.stride * f.height for f in picture.frames), palette_bits=6,
        input_executed=False, full_indexed_decode=True, native_runtime_tested=False,
        unknowns=['RGB expansion/display calibration, composition and game playback require separate qualification.'])
