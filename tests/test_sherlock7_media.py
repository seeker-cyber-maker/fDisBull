"""Authored PNG rasters and independently specified atlas geometry.

No original pixels, snippets of game resources, or copyrighted image sets are
stored in these fixtures. The tiny PNG writer below uses filter-zero scanlines
so expected channel values do not depend on the production decoder.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import zlib

from PIL import Image
import pytest

from fdisbull.sherlock7_media import decode_png_atlas


SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunk(kind, data=b''):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def raster(width, height):
    return bytes(value for y in range(height) for x in range(width)
                 for value in (x % 256, y % 256, (x + 17 * y) % 256, (x ^ y) % 256))


def png(width=128, height=160, *, pixels=None, metadata=(), idat_parts=1,
        color_type=6, bit_depth=8, scanlines=None, interlace=0):
    if pixels is None:
        pixels = raster(width, height)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    stride = (width * channels * bit_depth + 7) // 8
    if scanlines is None:
        scanlines = b''.join(b'\0' + pixels[y * stride:(y + 1) * stride]
                             for y in range(height))
    compressed = zlib.compress(scanlines)
    block = max(1, (len(compressed) + idat_parts - 1) // idat_parts)
    return (SIGNATURE
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, bit_depth,
                                         color_type, 0, 0, interlace))
            + b''.join(chunk(kind, data) for kind, data in metadata)
            + b''.join(chunk(b'IDAT', compressed[i:i + block])
                       for i in range(0, len(compressed), block))
            + chunk(b'IEND'))


def rgba(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.convert('RGBA')


def test_game_atlas_regions_and_fixed_control_pixels():
    source = png(idat_parts=3)
    report, payloads = decode_png_atlas(source, profile='sherlock7-images')
    assert report['profile'] == 'sherlock7-images'
    assert report['profile_version'] == 1
    assert report['width'] == 128 and report['height'] == 160
    assert report['unit_pixels'] == 16
    assert report['input_executed'] is False
    assert len(report['members']) == 72
    assert len(report['control_pixels']) == 14
    assert report['control_pixels'][1] == {
        'index': 1, 'role': 'transparency-2', 'rgba': [1, 0, 1, 1]}
    # Control pixels are at x=0..13, not x=0,16,32,... .
    assert report['control_pixels'][13]['rgba'] == [13, 0, 13, 13]
    item = next(m for m in report['members'] if m['name'] == 'tile-r3-i5')
    assert item['source_rect'] == dict(x=80, y=64, width=16, height=16)
    assert item['pixel_rect'] == item['source_rect']
    assert item['offset'] is None
    assert item['role'] == 'puzzle-item'
    assert item['category'] == 3 and item['item'] == 5
    assert item['size'] == len(payloads[item['name']])
    assert item['sha256'] == hashlib.sha256(payloads[item['name']]).hexdigest()
    with rgba(payloads['tile-r3-i5']) as tile:
        assert tile.size == (16, 16)
        assert tile.getpixel((0, 0)) == (80, 64, 144, 16)
        assert tile.getpixel((15, 15)) == (95, 79, 158, 16)
        assert item['pixel_sha256'] == hashlib.sha256(tile.tobytes()).hexdigest()
    # Plain metadata, rather than an accidental raw payload or base64 export.
    json.dumps(report)
    assert 'payload' not in report
    assert source == png(idat_parts=3)


def test_game_all_members_recompose_the_entire_raster():
    source = png()
    report, payloads = decode_png_atlas(source, profile='sherlock7-images')
    combined = Image.new('RGBA', (128, 160))
    coverage = bytearray(128 * 160)
    for member in report['members']:
        rectangle = member['source_rect']
        x, y, w, h = (rectangle[n] for n in ('x', 'y', 'width', 'height'))
        with rgba(payloads[member['name']]) as image:
            combined.paste(image, (x, y))
        for row in range(y, y + h):
            for col in range(x, x + w):
                coverage[row * 128 + col] += 1
    assert combined.tobytes() == raster(128, 160)
    assert set(coverage) == {1}


@pytest.mark.parametrize('profile,states', [
    ('kint6-user-buttons', ('normal', 'pressed')),
    ('kint6-user-overlays', ('dark', 'light')),
])
def test_button_and_overlay_rows_have_documented_geometry_and_states(profile, states):
    # A two-pixel unit gives 24x10 images in a two-column, three-row sheet.
    report, payloads = decode_png_atlas(png(48, 30), profile=profile)
    assert report['unit_pixels'] == 2
    assert report['rows'] == 3
    assert len(payloads) == 6
    member = report['members'][-1]
    assert member['row'] == 2 and member['list_number'] == 8
    assert member['state'] == states[1]
    assert member['source_rect'] == dict(x=24, y=20, width=24, height=10)
    with rgba(payloads[member['name']]) as image:
        assert image.getpixel((0, 0)) == (24, 20, 108, 12)
    if profile == 'kint6-user-overlays':
        assert report['control_pixels'] == [
            {'index': 0, 'role': 'transparency-1', 'rgba': [0, 0, 0, 0]}]
    else:
        assert report['control_pixels'] == []


@pytest.mark.parametrize('profile', ['kint6-user-buttons', 'kint6-user-overlays'])
def test_blank_paired_sheets_preserve_all_slots(profile):
    report, payloads = decode_png_atlas(png(48, 30, pixels=bytes(48 * 30 * 4)),
                                       profile=profile)
    assert len(payloads) == 6
    assert [member['list_number'] for member in report['members']] == [6, 6, 7, 7, 8, 8]
    for payload in payloads.values():
        with rgba(payload) as item:
            assert item.tobytes() == bytes(24 * 10 * 4)


def test_raw_alpha_and_color_keys_are_not_silently_reinterpreted():
    pixels = bytearray(raster(128, 160))
    pixels[:8] = bytes([99, 88, 77, 255, 11, 22, 33, 255])
    offset = (16 * 128) * 4
    pixels[offset:offset + 4] = pixels[:4]
    report, payloads = decode_png_atlas(png(pixels=bytes(pixels)), profile='sherlock7-images')
    assert report['transparency']['color_keys_applied'] is False
    assert report['transparency']['color_keys_rgba'] == [
        [99, 88, 77, 255], [11, 22, 33, 255]]
    with rgba(payloads['tile-r0-i0']) as tile:
        assert tile.getpixel((0, 0)) == (99, 88, 77, 255)


@pytest.mark.parametrize('profile,width,height', [
    ('sherlock7-images', 128, 159),
    ('sherlock7-images', 129, 160),
    ('sherlock7-images', 8, 10),
    ('kint6-user-buttons', 47, 30),
    ('kint6-user-overlays', 48, 31),
    ('kint6-user-buttons', 24, 1260),
])
def test_unsupported_geometry_is_refused(profile, width, height):
    with pytest.raises(ValueError, match='geometry|control|251'):
        decode_png_atlas(png(width, height), profile=profile)


@pytest.mark.parametrize('limit', [0, -1, True, '100', 67108865])
def test_invalid_output_limits_are_refused(limit):
    with pytest.raises(ValueError, match='max_output_bytes'):
        decode_png_atlas(png(), profile='sherlock7-images', max_output_bytes=limit)


def test_encoding_budget_is_enforced_before_returning_payloads():
    with pytest.raises(ValueError, match='output budget'):
        decode_png_atlas(png(), profile='sherlock7-images', max_output_bytes=64)


def test_internal_output_budget_is_aggregate_and_accepts_exact_boundary():
    source = png()
    report, payloads = decode_png_atlas(source, profile='sherlock7-images')
    total = sum(len(payload) for payload in payloads.values())
    assert report['encoded_size'] == total
    with pytest.raises(ValueError, match='output budget'):
        decode_png_atlas(source, profile='sherlock7-images', max_output_bytes=total - 1)
    _, exact = decode_png_atlas(source, profile='sherlock7-images', max_output_bytes=total)
    assert exact == payloads


def png_chunks(data):
    result = []
    offset = 8
    while offset < len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        result.append((data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]))
        offset += 12 + length
    return result


def packed_chunks(parts):
    return SIGNATURE + b''.join(chunk(kind, body) for kind, body in parts)


@pytest.mark.parametrize('mutation,message', [
    (lambda c: c[:-1], 'missing IEND'),
    (lambda c: c + [(b'IEND', b'')], 'Trailing data'),
    (lambda c: c[:1] + c, 'Duplicate'),
    (lambda c: c[1:], 'start with IHDR'),
    (lambda c: c[:1] + [(b'ZZZZ', b'')] + c[1:], 'critical'),
    (lambda c: c[:1] + [(b'acTL', struct.pack('>II', 1, 0))] + c[1:], 'Animated'),
    (lambda c: c[:1] + [(b'text', b'')] + c[1:], 'reserved'),
    (lambda c: c[:1] + [(b'tE1T', b'')] + c[1:], 'chunk type'),
    (lambda c: c[:1] + [(b'tRNS', b'\0')] + c[1:], 'transparency'),
    (lambda c: c[:-1] + [(b'IEND', b'X')], 'IEND'),
    (lambda c: [c[0], c[-1]], 'missing image data'),
])
def test_invalid_png_structure_is_refused(mutation, message):
    raw = packed_chunks(mutation(png_chunks(png())))
    with pytest.raises(ValueError, match=message):
        decode_png_atlas(raw, profile='sherlock7-images')


def test_nonconsecutive_idat_is_refused():
    parts = png_chunks(png(idat_parts=3))
    parts.insert(2, (b'tEXt', b'comment\0authored fixture'))
    with pytest.raises(ValueError, match='Nonconsecutive'):
        decode_png_atlas(packed_chunks(parts), profile='sherlock7-images')


def test_crc_and_chunk_bounds_are_checked():
    raw = bytearray(png())
    raw[-1] ^= 1
    with pytest.raises(ValueError, match='CRC'):
        decode_png_atlas(bytes(raw), profile='sherlock7-images')
    with pytest.raises(ValueError, match='Truncated'):
        decode_png_atlas(png()[:-3], profile='sherlock7-images')
    raw = SIGNATURE + struct.pack('>I', 0xffffffff) + b'IDAT'
    with pytest.raises(ValueError, match='Truncated'):
        decode_png_atlas(raw, profile='sherlock7-images')


@pytest.mark.parametrize('edit,message', [
    (lambda compressed: compressed[:-2], 'truncated'),
    (lambda compressed: compressed + zlib.compress(b'extra'), 'concatenated'),
    (lambda compressed: zlib.compress(bytes(128 * 160 * 4 + 161)), 'exceeds'),
    (lambda compressed: zlib.compress(bytes(128 * 160 * 4 + 159)), 'raster length'),
    (lambda compressed: b'invalid stream', 'zlib'),
])
def test_inflation_is_exact_and_bounded(edit, message):
    parts = png_chunks(png())
    parts[1] = (b'IDAT', edit(parts[1][1]))
    with pytest.raises(ValueError, match=message):
        decode_png_atlas(packed_chunks(parts), profile='sherlock7-images')


@pytest.mark.parametrize('width,height,depth,color,message', [
    (32769, 1, 8, 6, 'dimensions'),
    (8192, 10240, 8, 6, 'pixel budget'),
    (0, 160, 8, 6, 'dimensions'),
    (128, 160, 16, 6, 'bit depth'),
    (128, 160, 8, 5, 'color type'),
])
def test_headers_are_rejected_before_raster_inflation(width, height, depth, color, message):
    raw = packed_chunks([
        (b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0)),
        (b'IDAT', b'not a zlib stream'), (b'IEND', b''),
    ])
    with pytest.raises(ValueError, match=message):
        decode_png_atlas(raw, profile='sherlock7-images')


def test_source_and_chunk_budgets():
    with pytest.raises(ValueError, match='input budget'):
        decode_png_atlas(bytes(64 * 1024 * 1024 + 1), profile='sherlock7-images')
    parts = png_chunks(png())
    raw = packed_chunks([parts[0]] + [(b'tEXt', b'')] * 4094 + parts[1:])
    with pytest.raises(ValueError, match='chunk-count budget'):
        decode_png_atlas(raw, profile='sherlock7-images')


@pytest.mark.parametrize('source,profile,message', [
    (b'not png', 'sherlock7-images', 'signature'),
    (bytearray(), 'sherlock7-images', 'bytes'),
    (b'', 'arbitrary', 'profile'),
    (b'', None, 'profile'),
])
def test_invalid_inputs_are_normalized(source, profile, message):
    with pytest.raises(ValueError, match=message):
        decode_png_atlas(source, profile=profile)


def test_invalid_png_filter_is_normalized_to_value_error():
    invalid = b'\x05' + bytes(128 * 4)
    with pytest.raises(ValueError, match='PNG atlas decoding failed'):
        decode_png_atlas(png(scanlines=invalid * 160), profile='sherlock7-images')


def test_metadata_is_ignored_without_changing_pixels():
    # A large compressed ICC body is irrelevant to raw RGBA extraction. Its
    # content is deliberately not a valid ICC profile and must not be parsed.
    source = png(metadata=[(b'iCCP', b'test\0\0' + zlib.compress(b'X' * 1000000)),
                           (b'tEXt', b'Comment\0authored fixture')])
    report, _ = decode_png_atlas(source, profile='sherlock7-images')
    assert report['ignored_metadata_chunks'] == ['iCCP', 'tEXt']
    assert report['source_sha256'] == hashlib.sha256(source).hexdigest()
    assert report['decoded_pixel_sha256'] == hashlib.sha256(raster(128, 160)).hexdigest()


def test_palette_must_precede_transparency_even_for_rgb():
    raw = png(pixels=bytes(128 * 160 * 3), color_type=2,
              metadata=[(b'tRNS', bytes(6)), (b'PLTE', bytes(3))])
    with pytest.raises(ValueError, match='palette ordering'):
        decode_png_atlas(raw, profile='sherlock7-images')


@pytest.mark.parametrize('depth', [1, 2, 4, 8])
def test_palette_and_transparency_samples(depth):
    # Pack alternating zero/one indices independently of the decoder's codec.
    samples = [0, 1] * 64
    row = bytearray(128 * depth // 8)
    for x, value in enumerate(samples):
        row[x * depth // 8] |= value << (8 - depth - (x * depth % 8))
    pixels = bytes(row) * 160
    report, payloads = decode_png_atlas(
        png(pixels=pixels, color_type=3, bit_depth=depth,
            metadata=[(b'PLTE', bytes([9, 8, 7, 6, 5, 4])),
                      (b'tRNS', bytes([0, 127]))]),
        profile='sherlock7-images')
    assert report['source_bit_depth'] == depth
    with rgba(payloads['tile-r0-i0']) as tile:
        assert tile.getpixel((0, 0)) == (9, 8, 7, 0)
        assert tile.getpixel((1, 0)) == (6, 5, 4, 127)


@pytest.mark.parametrize('color,depth,sample,expected', [
    (0, 1, bytes([0b01010101]), [(0, 0, 0, 255), (255, 255, 255, 255)]),
    (0, 2, bytes([0b00010001]), [(0, 0, 0, 255), (85, 85, 85, 255)]),
    (0, 4, bytes([0b00000001]), [(0, 0, 0, 255), (17, 17, 17, 255)]),
    (0, 8, bytes([0, 127]), [(0, 0, 0, 255), (127, 127, 127, 255)]),
    (2, 8, bytes([9, 8, 7, 6, 5, 4]), [(9, 8, 7, 255), (6, 5, 4, 255)]),
    (4, 8, bytes([9, 50, 8, 60]), [(9, 9, 9, 50), (8, 8, 8, 60)]),
])
def test_png_color_variants(color, depth, sample, expected):
    channels = {0: 1, 2: 3, 4: 2}[color]
    length = 128 * 160 * depth * channels // 8
    _, payloads = decode_png_atlas(
        png(pixels=sample * (length // len(sample)), color_type=color, bit_depth=depth),
        profile='sherlock7-images')
    with rgba(payloads['tile-r0-i0']) as tile:
        assert tile.getpixel((0, 0)) == expected[0]
        assert tile.getpixel((1, 0)) == expected[1]


def test_adam7_interlaced_rgba():
    original = raster(128, 160)
    rows = []
    for origin, step in [((0, 0), (8, 8)), ((4, 0), (8, 8)),
                         ((0, 4), (4, 8)), ((2, 0), (4, 4)),
                         ((0, 2), (2, 4)), ((1, 0), (2, 2)),
                         ((0, 1), (1, 2))]:
        for y in range(origin[1], 160, step[1]):
            row = b''.join(original[(y * 128 + x) * 4:(y * 128 + x + 1) * 4]
                           for x in range(origin[0], 128, step[0]))
            rows.append(b'\0' + row)
    report, payloads = decode_png_atlas(
        png(scanlines=b''.join(rows), interlace=1), profile='sherlock7-images')
    assert report['interlaced'] is True
    assert report['decoded_pixel_sha256'] == hashlib.sha256(original).hexdigest()
    with rgba(payloads['tile-r3-i5']) as tile:
        assert tile.getpixel((0, 0)) == (80, 64, 144, 16)
