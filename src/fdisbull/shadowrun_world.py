"""Read field profile and collision structures from the pinned Genesis game.

Only numeric offsets and source records are returned. Reading a table is not
proof of runtime reachability, destination semantics, or a complete world.
"""
from dataclasses import dataclass
import hashlib

SOURCE_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
SCENE_COUNT = 56


class WorldFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Collision:
    address: int
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    value: int


@dataclass(frozen=True)
class Scene:
    scene_id: int
    profile: int
    terrain_a: int
    terrain_b: int
    stream_source: int
    collision: tuple[Collision, ...]
    event_table: tuple[int, ...] | None


def _read(data: bytes, address: int, size: int) -> int:
    if address < 0 or address + size > len(data):
        raise WorldFormatError('source range outside ROM')
    return int.from_bytes(data[address:address + size], 'big')


def read_scene(data: bytes, scene_id: int) -> Scene:
    """Read a scene from the exact identified source; reject malformed streams."""
    if type(scene_id) is not int or not 0 <= scene_id < SCENE_COUNT:
        raise WorldFormatError('scene ID must be an integer in the reviewed table')
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise WorldFormatError('source identity mismatch')
    profile = _read(data, 0x3232 + scene_id * 4, 4)
    # 0x3084 copies 0x60 bytes, while 0x313a consumes these two pointers.
    _read(data, profile, 0x60)
    terrain_a = _read(data, profile + 0x14, 4)
    terrain_b = _read(data, profile + 0x1c, 4)
    stream_source = _read(data, profile + 0x18, 4)
    for ptr in (terrain_a, terrain_b):
        _read(data, ptr, 0x1c20)
    cursor = _read(data, profile + 0x26, 4)
    rows = []
    while True:
        x_min = _read(data, cursor, 2)
        if x_min & 0x8000:
            break
        x_max = _read(data, cursor + 2, 2)
        y_min = _read(data, cursor + 4, 2)
        y_max = _read(data, cursor + 6, 2)
        value = _read(data, cursor + 8, 2)
        rows.append(Collision(cursor, x_min, x_max, y_min, y_max, value))
        cursor += 10
    event_ptr = _read(data, profile + 0x4e, 4)
    events = None
    if event_ptr:
        _read(data, event_ptr, 32)
        events = tuple(data[event_ptr:event_ptr + 32])
    return Scene(scene_id, profile, terrain_a, terrain_b, stream_source, tuple(rows), events)


def decode_stream(data: bytes, address: int, *, max_output: int = 65536) -> tuple[bytes, int]:
    """Decode the 0x1610 byte stream, returning output and next source offset.

    Streams are private source data. Invalid distances and runs that exceed the
    declared output length are refused rather than emulating memory corruption.
    This is the compression primitive, not proof of any scene's loader path.
    """
    if type(address) is not int or address < 0:
        raise WorldFormatError('stream address must be a nonnegative integer')
    if type(max_output) is not int or not 1 <= max_output <= 65536:
        raise WorldFormatError('output budget must be an integer from 1 to 65536')
    length = _read(data, address, 2) + 1
    if length > max_output:
        raise WorldFormatError('decoded stream exceeds output budget')
    pos = address + 2
    output = bytearray()
    mask = 0
    flags = 0

    def byte():
        nonlocal pos
        value = _read(data, pos, 1)
        pos += 1
        return value

    while len(output) < length:
        if not mask:
            flags, mask = byte(), 0x80
        compressed = flags & mask
        mask >>= 1
        if not compressed:
            output.append(byte())
            continue
        first = byte()
        if not first & 0x80:
            count = first + 3
            value = byte()
            if len(output) + count > length:
                raise WorldFormatError('run exceeds declared output size')
            output.extend([value] * count)
        else:
            second = byte()
            distance = (second << 3) | ((first >> 4) & 7)
            count = (first & 15) + 3
            if not distance or distance > len(output):
                raise WorldFormatError('invalid backreference')
            if len(output) + count > length:
                raise WorldFormatError('backreference exceeds declared output size')
            for _ in range(count):
                output.append(output[-distance])
    return bytes(output), pos


def decode_scene_stream(data: bytes, scene_id: int) -> tuple[bytes, int]:
    """Decode the profile's flagged stream, if present, into private bytes.

    0x3084 seeds the loader cursor from profile +0x18; 0x29fc checks its
    low bit before calling 0x1610. Intervening runtime mutation remains a
    separate question, so this is a static source candidate, not a replay.
    """
    scene = read_scene(data, scene_id)
    if not scene.stream_source & 1:
        raise WorldFormatError('scene profile does not select compressed stream')
    return decode_stream(data, scene.stream_source & ~1, max_output=0x9900)
