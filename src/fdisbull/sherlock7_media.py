"""Bounded Sherlock 7 / KINT 6 PNG atlas readers.

The PNG codec is Pillow. This module implements the documented game-specific
layout above that codec: named rectangles, fixed single-pixel control colors,
and button states. It never executes a game or interprets target-supplied text.

Layout evidence: the owner's Sherlock 7.0 demo English help, Graphics and
User Buttons sections, together with its labeled image-set diagram. These are
authored readers of the format; no game artwork or upstream source is embedded.
See docs/SHERLOCK7_MEDIA.md for the supported profiles and evidence boundary.
"""
from __future__ import annotations

import hashlib
import io
import struct
import zlib

from PIL import Image


PROFILES = ('sherlock7-images', 'kint6-user-buttons', 'kint6-user-overlays')
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024
MAX_DIMENSION = 32768
MAX_CHUNKS = 4096
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

# These fields occupy literal pixels x=0..13, y=0 even when an atlas is scaled.
GAME_CONTROL_ROLES = (
    'transparency-1', 'transparency-2', 'unused-2',
    'horizontal-clue-bin-fill', 'horizontal-clue-bin-frame',
    'vertical-clue-bin-fill', 'vertical-clue-bin-frame',
    'puzzle-fill', 'puzzle-frame', 'selected-clue-outline',
    'what-if-fill', 'what-if-outline', 'unused-12', 'clue-bookmark-outline',
)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _geometry(width, height, profile):
    """Validate the selected profile before inflating or allocating a raster."""
    if profile == 'sherlock7-images':
        if width % 8 or height != (width // 8) * 10:
            raise ValueError('Sherlock 7 image atlas geometry must be 8 by 10 square cells')
        unit = width // 8
        if unit < len(GAME_CONTROL_ROLES):
            raise ValueError('Image atlas control area must hold 14 single-pixel colors')
        return unit, 10
    if width % 24:
        raise ValueError('KINT 6 user sheet geometry requires width=24*unit')
    unit = width // 24
    if not unit or height % (5 * unit):
        raise ValueError('KINT 6 user sheet geometry requires complete 5-unit rows')
    rows = height // (5 * unit)
    if not 1 <= rows <= 251:
        raise ValueError('KINT 6 user sheets support 1..251 rows')
    return unit, rows


def _scanline_size(width, height, bits_per_pixel, interlace):
    """Compute the exact PNG filtered-byte count, including Adam7 pass rows."""
    if not interlace:
        return height * (1 + (width * bits_per_pixel + 7) // 8)
    total = 0
    # The seven passes specified by PNG, not game-specific rendering behavior.
    for x, y, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8),
                         (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2),
                         (0, 1, 1, 2)):
        w = max(0, (width - x + dx - 1) // dx)
        h = max(0, (height - y + dy - 1) // dy)
        if w and h:
            total += h * (1 + (w * bits_per_pixel + 7) // 8)
    return total


def _read_png(data, profile):
    """Check structure and inflation bounds; omit non-raster metadata from PIL.

    ICC/text/EXIF data is not needed for raw pixel extraction. Validating its
    chunk CRC but not parsing it avoids an unrelated metadata decompression
    surface. The original input's digest is still retained in the report.
    """
    if not isinstance(data, bytes):
        raise ValueError('PNG input must be bytes')
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError('PNG source exceeds the 64 MiB input budget')
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Expected a PNG signature')

    position = 8
    count = 0
    width = height = depth = color = interlace = 0
    saw_header = saw_idat = ended_idat = saw_end = False
    palette = transparency = None
    chunks = []
    idat = []
    ignored = set()
    view = memoryview(data)

    while position < len(data):
        count += 1
        if count > MAX_CHUNKS:
            raise ValueError('PNG chunk-count budget exceeded')
        if position + 12 > len(data):
            raise ValueError('Truncated PNG chunk header')
        length = struct.unpack_from('>I', data, position)[0]
        end = position + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG chunk payload')
        kind = data[position + 4:position + 8]
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            raise ValueError('Invalid PNG chunk type')
        if kind[2] & 32:
            raise ValueError('Invalid PNG reserved chunk-type bit')
        body = view[position + 8:end - 4]
        expected_crc = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(view[position + 4:end - 4]) & 0xffffffff != expected_crc:
            raise ValueError('PNG chunk CRC mismatch')
        if not saw_header and kind != b'IHDR':
            raise ValueError('PNG must start with IHDR')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('Animated PNG is unsupported by these atlas profiles')
        if saw_idat and kind != b'IDAT':
            ended_idat = True

        if kind == b'IHDR':
            if saw_header or length != 13:
                raise ValueError('Duplicate or malformed PNG IHDR')
            saw_header = True
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not 0 < width <= MAX_DIMENSION or not 0 < height <= MAX_DIMENSION:
                raise ValueError('PNG dimensions exceed the supported bounds')
            if width * height > MAX_PIXELS:
                raise ValueError('PNG decoded pixel budget exceeded')
            variants = {0: (1, 2, 4, 8), 2: (8,), 3: (1, 2, 4, 8), 4: (8,), 6: (8,)}
            if color not in variants or depth not in variants[color]:
                raise ValueError('Unsupported PNG color type or bit depth (16-bit samples are not decoded)')
            if compression != 0 or filtering != 0 or interlace not in (0, 1):
                raise ValueError('Unsupported PNG compression/filter/interlace method')
            _geometry(width, height, profile)
        elif kind == b'PLTE':
            if palette is not None or transparency is not None or saw_idat or color in (0, 4):
                raise ValueError('Invalid PNG palette ordering or color type')
            if not length or length % 3 or length > 768:
                raise ValueError('Malformed PNG palette')
            if color == 3 and length // 3 > 1 << depth:
                raise ValueError('PNG palette exceeds its indexed bit depth')
            palette = length // 3
        elif kind == b'tRNS':
            if transparency is not None or saw_idat:
                raise ValueError('Invalid PNG transparency ordering')
            if ((color == 0 and length != 2) or (color == 2 and length != 6)
                    or (color == 3 and (palette is None or not 0 < length <= palette))
                    or color in (4, 6)):
                raise ValueError('Malformed PNG transparency chunk')
            transparency = length
        elif kind == b'IDAT':
            if ended_idat:
                raise ValueError('Nonconsecutive PNG IDAT chunks')
            if color == 3 and palette is None:
                raise ValueError('Indexed PNG has no palette')
            saw_idat = True
            idat.append(body)
        elif kind == b'IEND':
            if length or not saw_idat:
                raise ValueError('Malformed PNG IEND or missing image data')
            if end != len(data):
                raise ValueError('Trailing data after PNG IEND')
            saw_end = True
        elif not (kind[0] & 32):
            raise ValueError('Unsupported critical PNG chunk')
        else:
            ignored.add(kind.decode('ascii'))

        if kind in (b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'):
            chunks.append(view[position:end])
        position = end
        if saw_end:
            break
    if not saw_end:
        raise ValueError('PNG is missing IEND')

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    expected = _scanline_size(width, height, channels * depth, interlace)
    compressed = b''.join(idat)
    inflater = zlib.decompressobj()
    try:
        # One extra byte distinguishes an exact image from an inflation bomb.
        # Never call unbounded flush() on an untrusted compressed stream.
        filtered = inflater.decompress(compressed, expected + 1)
    except zlib.error as error:
        raise ValueError('Invalid PNG zlib image stream') from error
    if len(filtered) > expected:
        raise ValueError('PNG inflated raster exceeds the declared pixel budget')
    if (len(filtered) != expected or not inflater.eof
            or inflater.unused_data or inflater.unconsumed_tail):
        raise ValueError('PNG image stream is truncated, concatenated or has an invalid raster length')
    del filtered, compressed
    sanitized = PNG_SIGNATURE + b''.join(chunks)
    metadata = dict(width=width, height=height, source_bit_depth=depth,
                    source_color_type=color, interlaced=bool(interlace),
                    ignored_metadata_chunks=sorted(ignored))
    return sanitized, metadata


def _regions(width, height, profile):
    unit, rows = _geometry(width, height, profile)
    regions = []

    def add(name, role, x, y, w, h, **extra):
        # All arguments here are logical units; source_rect is in decoded pixels.
        rectangle = dict(x=x * unit, y=y * unit, width=w * unit, height=h * unit)
        regions.append(dict(name=name, role=role, source_rect=rectangle,
                            pixel_rect=dict(rectangle), offset=None, **extra))

    if profile == 'sherlock7-images':
        add('control-area', 'control-colors-and-guides', 0, 0, 1, 1)
        add('credits', 'creator-credits', 1, 0, 4, 1)
        add('highlight', 'hint-find-highlight', 5, 0, 1, 1)
        add('empty-clue-vertical', 'empty-vertical-clue-slot', 6, 0, 1, 1)
        add('empty-clue-horizontal', 'empty-horizontal-clue-slot', 7, 0, 1, 1)
        for category in range(8):
            for item in range(8):
                add(f'tile-r{category}-i{item}', 'puzzle-item', item, category + 1, 1, 1,
                    category=category, item=item)
        add('cell-background', 'candidate-cell-background', 0, 9, 1, 1)
        # These remain composite regions: this reader does not invent the
        # per-clue composition behavior or split undocumented overlay variants.
        add('clue-overlays', 'clue-overlay-strip', 1, 9, 5, 1)
        add('bookmark-overlays', 'clue-bookmark-strip', 6, 9, 2, 1)
        return unit, rows, regions, GAME_CONTROL_ROLES

    is_overlay = profile == 'kint6-user-overlays'
    states = ('dark', 'light') if is_overlay else ('normal', 'pressed')
    prefix = 'overlay' if is_overlay else 'button'
    for row in range(rows):
        for column, state in enumerate(states):
            # List items 1..5 are provided by the UI skin; these sheets start at 6.
            add(f'{prefix}-{row + 6:03}-{state}', f'user-{prefix}',
                12 * column, 5 * row, 12, 5, row=row,
                list_number=row + 6, state=state)
    return unit, rows, regions, ('transparency-1',) if is_overlay else ()


class _LimitedPNGBuffer(io.BytesIO):
    """Stop PNG encoding before an output payload exceeds the remaining quota."""

    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ValueError('Atlas encoded output budget exceeded')
        return super().write(data)


def decode_png_atlas(data: bytes, *, profile: str, max_output_bytes=MAX_OUTPUT_BYTES):
    """Return a JSON-safe inventory and named, normalized PNG payloads.

    The caller owns filesystem policy and extraction. max_output_bytes is an
    aggregate internal encoding budget, independent of a caller's selected-file
    export quota. Every exported PNG preserves source channel values as RGBA;
    game color keys are reported but not applied as an undocumented alpha rule.
    """
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError('Unknown PNG atlas profile; select one from PROFILES')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('max_output_bytes must be 1..67108864')
    sanitized, png_info = _read_png(data, profile)
    width, height = png_info['width'], png_info['height']
    unit, rows, regions, controls = _regions(width, height, profile)
    payloads = {}
    members = []
    encoded_size = 0

    try:
        with Image.open(io.BytesIO(sanitized)) as source:
            source.load()
            with source.convert('RGBA') as pixels:
                control_pixels = [dict(index=i, role=role, rgba=list(pixels.getpixel((i, 0))))
                                  for i, role in enumerate(controls)]
                pixel_digest = _sha256(pixels.tobytes())
                for region in regions:
                    r = region['source_rect']
                    bounds = (r['x'], r['y'], r['x'] + r['width'], r['y'] + r['height'])
                    with pixels.crop(bounds) as item:
                        pixel_sha = _sha256(item.tobytes())
                        with _LimitedPNGBuffer(max_output_bytes - encoded_size) as stream:
                            item.save(stream, format='PNG', compress_level=6)
                            payload = stream.getvalue()
                    encoded_size += len(payload)
                    payloads[region['name']] = payload
                    members.append(dict(region, size=len(payload), sha256=_sha256(payload),
                                        encoding='PNG', pixel_format='RGBA',
                                        pixel_sha256=pixel_sha))
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError(f'PNG atlas decoding failed: {error}') from error

    keys = [item['rgba'] for item in control_pixels if item['role'].startswith('transparency-')]
    report = dict(
        format='fdisbull-sherlock7-png-atlas-1', profile=profile, profile_version=1,
        **png_info, unit_pixels=unit, rows=rows,
        source_size=len(data), source_sha256=_sha256(data),
        decoded_pixel_format='RGBA', decoded_pixel_sha256=pixel_digest,
        control_pixels=control_pixels,
        transparency=dict(color_keys_rgba=keys, color_keys_applied=False,
                          policy='Preserve decoded RGBA; report game color keys separately'),
        members=members, encoded_size=encoded_size, input_executed=False,
        qualification='documented-atlas-layout; original runtime rendering unverified',
        profile_selection='explicit; geometry is not an embedded game/version signature',
        unknowns=[
            'Color-key compositing, scaling and clue drawing are not executed by this reader.',
            'Other UI atlases, puzzle caches and KINT bytecode require separate adapters.',
        ],
    )
    return report, payloads
