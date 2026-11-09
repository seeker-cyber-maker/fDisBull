"""Classic Doom resource codecs, without engine execution or audio synthesis.

Authored Python implementation informed by published format-consuming source.
See docs/WAD_MEDIA.md for references, transformations and unsupported variants.
Pixels retain a separate opacity plane: palette index 255 is NOT transparency.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import struct
import wave

from .wad_archive import wad_name

MAX_PIXELS = 4 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_POSTS = 2_000_000
MAX_TABLE_ROWS = 65_536
MAX_EVENTS = 200_000


class WadDecodeError(ValueError):
    """A format cannot be decoded under the selected, bounded profile."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise WadDecodeError(message)


def _dimensions(width: int, height: int) -> None:
    _require(0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION
             and width * height <= MAX_PIXELS, 'image dimensions exceed profile')


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    indices: bytes
    opacity: bytes
    left: int = 0
    top: int = 0

    def __post_init__(self) -> None:
        _dimensions(self.width, self.height)
        if len(self.indices) != self.width * self.height or len(self.opacity) != len(self.indices):
            raise WadDecodeError('raster plane dimensions disagree')

    def png(self, palette: bytes) -> bytes:
        from PIL import Image
        _require(len(palette) == 768, 'one 256-entry RGB palette required')
        image = Image.frombytes('P', (self.width, self.height), self.indices)
        image.putpalette(palette)
        rgba = image.convert('RGBA')
        rgba.putalpha(Image.frombytes('L', image.size, self.opacity))
        result = io.BytesIO()
        rgba.save(result, format='PNG', optimize=False, compress_level=6)
        return result.getvalue()


def patch_posts(data: bytes, *, tall: bool = False) -> tuple[dict, list[list[tuple[int, bytes]]]]:
    """Validate absolute vanilla post rows; optional explicit tall-post profile.

    Posts are bounded by this lump, not by the next column: columns can alias.
    Classic posts can overlap. Later posts overwrite earlier opaque samples.
    Patch-origin fields are signed and are not texture-placement coordinates.
    """
    _require(len(data) >= 8, 'truncated patch header')
    width, height, left, top = struct.unpack_from('<HHhh', data)
    _dimensions(width, height)
    table_end = 8 + 4 * width
    _require(table_end <= len(data), 'truncated column directory')
    columns = []
    posts = 0
    samples = 0
    for x in range(width):
        cursor = struct.unpack_from('<I', data, 8 + x * 4)[0]
        _require(table_end <= cursor < len(data), 'column offset outside post data')
        runs = []
        previous = -1
        while True:
            _require(cursor < len(data), 'unterminated patch column')
            row = data[cursor]
            if row == 255:
                break
            _require(cursor + 4 <= len(data), 'truncated patch post')
            size = data[cursor + 1]
            end = cursor + size + 4
            _require(end <= len(data), 'patch post exceeds lump')
            effective = previous + row if tall and row <= previous else row
            previous = effective
            _require(effective + size <= height, 'patch post outside declared height')
            posts += 1
            samples += size
            _require(posts <= MAX_POSTS and samples <= MAX_PIXELS * 4, 'patch work budget')
            runs.append((effective, data[cursor + 3:cursor + 3 + size]))
            cursor = end
        columns.append(runs)
    return dict(width=width, height=height, left=left, top=top, posts=posts,
                sample_count=samples, profile='tall-posts' if tall else 'classic-absolute-posts'), columns


def decode_patch(data: bytes, *, tall: bool = False) -> Raster:
    info, columns = patch_posts(data, tall=tall)
    width, height = info['width'], info['height']
    pixels, opacity = bytearray(width * height), bytearray(width * height)
    for x, runs in enumerate(columns):
        for y, samples in runs:
            for dy, value in enumerate(samples):
                index = (y + dy) * width + x
                pixels[index] = value
                opacity[index] = 255
    return Raster(width, height, bytes(pixels), bytes(opacity), info['left'], info['top'])


def decode_flat(data: bytes) -> Raster:
    _require(len(data) == 4096, 'classic flat requires exactly 64x64 indices')
    return Raster(64, 64, data, b'\xff' * 4096)


def decode_palettes(data: bytes) -> tuple[bytes, ...]:
    _require(0 < len(data) <= 768 * 256 and len(data) % 768 == 0, 'invalid PLAYPAL extent')
    return tuple(data[i:i + 768] for i in range(0, len(data), 768))


def decode_colormaps(data: bytes) -> list[list[int]]:
    _require(0 < len(data) <= 256 * 4096 and len(data) % 256 == 0, 'invalid COLORMAP extent')
    return [list(data[i:i + 256]) for i in range(0, len(data), 256)]


def decode_pnames(data: bytes) -> list[str]:
    _require(len(data) >= 4, 'truncated PNAMES')
    count = struct.unpack_from('<i', data)[0]
    _require(0 <= count <= MAX_TABLE_ROWS and 4 + 8 * count <= len(data), 'PNAMES bounds')
    return [wad_name(data[4 + 8 * i:12 + 8 * i]) for i in range(count)]


def decode_textures(data: bytes) -> list[dict]:
    _require(len(data) >= 4, 'truncated texture table')
    count = struct.unpack_from('<i', data)[0]
    table_end = 4 + count * 4
    _require(0 <= count <= MAX_TABLE_ROWS and table_end <= len(data), 'texture directory bounds')
    result = []
    work = 0
    for index in range(count):
        offset = struct.unpack_from('<i', data, 4 + 4 * index)[0]
        _require(table_end <= offset and offset + 22 <= len(data), 'texture definition offset')
        name, masked, width, height, obsolete, n = struct.unpack_from('<8sIhhIh', data, offset)
        _dimensions(width, height)
        _require(0 <= n <= 8192 and offset + 22 + n * 10 <= len(data), 'texture patch extent')
        work += n
        _require(work <= MAX_TABLE_ROWS, 'texture patch work budget')
        patches = []
        for j in range(n):
            x, y, ref, step, colormap = struct.unpack_from('<hhhhh', data, offset + 22 + j * 10)
            _require(ref >= 0, 'negative PNAMES reference')
            patches.append(dict(x=x, y=y, pnames_index=ref, stepdir_raw=step, colormap_raw=colormap))
        result.append(dict(index=index, name=wad_name(name), offset=offset, width=width,
                           height=height, masked_raw=masked, column_directory_raw=obsolete,
                           patches=patches))
    return result


def compose_texture(definition: dict, patches: list[Raster]) -> Raster:
    width, height = definition['width'], definition['height']
    _dimensions(width, height)
    _require(len(patches) == len(definition['patches']), 'texture dependencies incomplete')
    pixels, alpha = bytearray(width * height), bytearray(width * height)
    work = 0
    for placement, patch in zip(definition['patches'], patches):
        ox, oy = placement['x'], placement['y']
        x0, x1 = max(0, -ox), min(patch.width, width - ox)
        y0, y1 = max(0, -oy), min(patch.height, height - oy)
        work += max(0, x1 - x0) * max(0, y1 - y0)
        _require(work <= MAX_PIXELS * 16, 'texture composition work budget')
        for y in range(y0, y1):
            for x in range(x0, x1):
                src = y * patch.width + x
                if patch.opacity[src]:
                    dst = (y + oy) * width + x + ox
                    pixels[dst], alpha[dst] = patch.indices[src], 255
    return Raster(width, height, bytes(pixels), bytes(alpha))


def pcm_wav(samples: bytes, rate: int) -> bytes:
    _require(1 <= rate <= 65535, 'invalid PCM sample rate')
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(rate)
        out.writeframes(samples)
    return stream.getvalue()


def decode_dmx(data: bytes) -> tuple[dict, bytes]:
    _require(len(data) >= 8, 'truncated DMX header')
    fmt, rate, count = struct.unpack_from('<HHI', data)
    _require(fmt == 3 and 1 <= rate <= 65535 and count <= len(data) - 8, 'invalid DMX PCM extent/rate')
    # Retain the ENTIRE declared sample block. Playback trimming is a derivative.
    return dict(format=3, channels=1, bits=8, signed=False, sample_rate=rate,
                declared_samples=count, sample_offset=8, trailing_bytes=len(data) - 8 - count,
                dmx_playback_slice=[16, count - 16] if count > 48 else None), data[8:8 + count]


def decode_pc_speaker(data: bytes) -> dict:
    _require(len(data) >= 4, 'truncated PC-speaker header')
    fmt, count = struct.unpack_from('<HH', data)
    _require(fmt == 0 and count <= len(data) - 4, 'invalid PC-speaker extent')
    return dict(format=0, tick_rate_hz=140, codes=list(data[4:4 + count]),
                code_zero='silence', trailing_bytes=len(data) - 4 - count,
                qualification='tone-code sequence; no hardware waveform synthesis')


_CONTROLLER_MAP = (0, 32, 1, 7, 10, 11, 91, 93, 64, 67, 120, 123, 126, 127, 121)


def _vlq(value: int) -> bytes:
    _require(0 <= value <= 0x0fffffff, 'MIDI delta outside four-byte range')
    parts = [value & 127]
    value >>= 7
    while value:
        parts.append((value & 127) | 128)
        value >>= 7
    return bytes(reversed(parts))


def decode_mus(data: bytes) -> dict:
    """Parse bounded MUS event records into absolute ticks at 140 Hz.

    Keep original channel numbers and source byte offsets. Conversion is not
    instrument synthesis, looping policy or proof of an original sound device.
    """
    _require(len(data) >= 16 and data[:4] == b'MUS\x1a', 'invalid MUS header')
    length, start, primary, secondary, count, reserved = struct.unpack_from('<6H', data, 4)
    _require(16 + 2 * count <= start <= len(data) and start + length <= len(data)
             and primary <= 15 and secondary <= 15, 'MUS header extent/channels')
    instruments = list(struct.unpack_from('<' + 'H' * count, data, 16))
    cursor, end, tick = start, start + length, 0
    velocity = [127] * 16
    events = []
    warnings = []

    def read_byte() -> int:
        nonlocal cursor
        _require(cursor < end, 'truncated MUS event')
        v = data[cursor]
        cursor += 1
        return v

    while cursor < end:
        _require(len(events) < MAX_EVENTS, 'MUS event budget')
        offset = cursor
        descriptor = read_byte()
        kind, channel = (descriptor >> 4) & 7, descriptor & 15
        row = dict(tick=tick, channel=channel, offset=offset)
        if kind == 6:
            row['event'] = 'end'
            events.append(row)
            return dict(format='mus-events-1', tick_rate_hz=140, primary_channels=primary,
                        secondary_channels=secondary, instruments=instruments, reserved=reserved,
                        score_offset=start, score_length=length, total_ticks=tick,
                        unconsumed_score_bytes=end - cursor, trailing_bytes=len(data) - end,
                        events=events, warnings=warnings)
        if kind == 0:
            row.update(event='note_off', note=read_byte() & 127, velocity=0)
        elif kind == 1:
            note = read_byte()
            if note & 128:
                velocity[channel] = read_byte() & 127
            row.update(event='note_on', note=note & 127, velocity=velocity[channel])
        elif kind == 2:
            row.update(event='pitch_bend', value=read_byte() * 64)
        elif kind == 3:
            control = read_byte()
            _require(10 <= control <= 14, 'unsupported MUS system event')
            row.update(event='control', controller=_CONTROLLER_MAP[control], value=0, mus_controller=control)
        elif kind == 4:
            control, value = read_byte(), read_byte()
            _require(control <= 9, 'unsupported MUS controller')
            if control == 0:
                row.update(event='program', program=value & 127)
            else:
                if value > 127:
                    warnings.append(dict(offset=offset, reason='controller value clamped for MIDI', raw_value=value))
                row.update(event='control', controller=_CONTROLLER_MAP[control], value=min(value, 127),
                           mus_controller=control)
        else:
            raise WadDecodeError(f'unsupported MUS event type {kind}')
        events.append(row)
        if descriptor & 128:
            delay = 0
            for _ in range(4):
                b = read_byte()
                delay = (delay << 7) | (b & 127)
                if b < 128:
                    break
            else:
                raise WadDecodeError('MUS delay exceeds four-byte profile')
            tick += delay
            _require(tick <= 0x0fffffff, 'MUS duration budget')
    raise WadDecodeError('MUS score lacks end event')


def mus_midi(score: dict) -> bytes:
    """Type-0 MIDI, 70 PPQN at 500000 us/quarter = 140 source ticks/s.

    Fixed injective channel mapping leaves MIDI channel 9 for MUS percussion 15.
    No synthesizer, substitute samples, or music looping is implied.
    """
    track = bytearray(b'\x00\xff\x51\x03\x07\xa1\x20')
    previous = 0
    for event in score['events']:
        channel = event['channel']
        mapped = 9 if channel == 15 else channel if channel < 9 else channel + 1
        delta = event['tick'] - previous
        previous = event['tick']
        kind = event['event']
        if kind == 'end':
            message = b'\xff\x2f\x00'
        elif kind == 'note_on':
            message = bytes((0x90 | mapped, event['note'], event['velocity']))
        elif kind == 'note_off':
            message = bytes((0x80 | mapped, event['note'], 0))
        elif kind == 'program':
            message = bytes((0xc0 | mapped, event['program']))
        elif kind == 'pitch_bend':
            message = bytes((0xe0 | mapped, event['value'] & 127, event['value'] >> 7))
        else:
            message = bytes((0xb0 | mapped, event['controller'], event['value']))
        track.extend(_vlq(delta))
        track.extend(message)
    return b'MThd' + struct.pack('>IHHH', 6, 0, 1, 70) + b'MTrk' + struct.pack('>I', len(track)) + bytes(track)


def inspect_midi(data: bytes) -> dict:
    """Bound MIDI chunks for lossless pass-through; no event semantics inferred."""
    _require(len(data) >= 14 and data[:4] == b'MThd', 'invalid MIDI header')
    length = struct.unpack_from('>I', data, 4)[0]
    _require(length >= 6 and 8 + length <= len(data), 'MIDI header bounds')
    fmt, count, division = struct.unpack_from('>HHH', data, 8)
    _require(fmt <= 2 and 0 < count <= 1024 and (fmt != 0 or count == 1), 'MIDI track profile')
    _require(division != 0, 'MIDI division must be nonzero')
    if division & 0x8000:
        _require((division >> 8) in (232, 231, 227, 226) and (division & 255) != 0, 'MIDI SMPTE division profile')
    cursor = 8 + length
    for _ in range(count):
        _require(cursor + 8 <= len(data) and data[cursor:cursor + 4] == b'MTrk', 'MIDI track header')
        size = struct.unpack_from('>I', data, cursor + 4)[0]
        cursor += 8 + size
        _require(cursor <= len(data), 'MIDI track extent')
    return dict(type=fmt, tracks=count, division_raw=division, trailing_bytes=len(data) - cursor,
                qualification='bounded chunks; original MIDI copied unchanged')


def decode_genmidi(data: bytes) -> dict:
    _require(data[:8] == b'#OPL_II#' and len(data) >= 8 + 175 * 36, 'unsupported GENMIDI profile')
    rows = []
    names_start = 8 + 175 * 36
    has_names = len(data) >= names_start + 175 * 32
    for i in range(175):
        at = 8 + i * 36
        flags, fine, note = struct.unpack_from('<HBB', data, at)
        voices = []
        for v in range(2):
            p = at + 4 + v * 16
            keys = ('tremolo', 'attack', 'sustain', 'waveform', 'scale', 'level')
            voices.append(dict(modulator=dict(zip(keys, data[p:p + 6])), feedback=data[p + 6],
                               carrier=dict(zip(keys, data[p + 7:p + 13])), unused=data[p + 13],
                               base_note_offset=struct.unpack_from('<h', data, p + 14)[0]))
        row = dict(index=i, flags=flags, fine_tuning=fine, fixed_note=note, voices=voices)
        if has_names:
            row['name'] = data[names_start + i * 32:names_start + (i + 1) * 32].split(b'\0')[0].decode('cp437')
        rows.append(row)
    return dict(format='genmidi-opl-instruments-1', instruments=rows,
                names_present=has_names, trailing_bytes=len(data) - names_start - (175 * 32 if has_names else 0),
                qualification='register parameters, not a synthesizer or SoundFont')


def decode_endoom(data: bytes) -> dict:
    _require(len(data) == 4000, 'ENDOOM requires 80x25 character/attribute pairs')
    # Unicode graphic equivalents for CP437 control glyphs, never terminal codes.
    low = ' ☺☻♥♦♣♠•◘○◙♂♀♪♫☼►◄↕‼¶§▬↨↑↓→←∟↔▲▼'
    def glyph(value: int) -> str:
        return low[value] if value < 32 else '⌂' if value == 127 else bytes([value]).decode('cp437')
    cells = [dict(code=data[i], glyph=glyph(data[i]), attribute=data[i + 1],
                  foreground=data[i + 1] & 15, background=(data[i + 1] >> 4) & 7,
                  blink=bool(data[i + 1] & 128)) for i in range(0, 4000, 2)]
    return dict(width=80, height=25, cells=cells,
                text='\n'.join(''.join(c['glyph'] for c in cells[y * 80:(y + 1) * 80]) for y in range(25)),
                qualification='CP437 text and attributes; no original-font or blink-timing rendering')
