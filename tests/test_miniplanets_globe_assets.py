"""Original-data checks are opt-in; original art never enters the checkout."""
from collections import Counter
from functools import lru_cache
import math
import os
from pathlib import Path

import pytest

from fdisbull.udl_miniplanets_full import checked_rom, globe_assets, _slz


@pytest.fixture(scope='module')
def original():
    value = os.environ.get('FDISBULL_MINIPLANETS_ROM')
    if not value:
        pytest.skip('requires the private original Miniplanets ROM')
    path = Path(value)
    return checked_rom(path.read_bytes()), Path(os.environ.get('FDISBULL_MINIPLANETS_UPSTREAM', str(path.parent)))


@pytest.fixture(scope='module')
def assets(original):
    return globe_assets(original[0])


@lru_cache(maxsize=None)
def _reference_tile(raw):
    """Independently unpack original row pixels into the declared 3-color map."""
    low, high = bytearray(8), bytearray(8)
    for row in range(8):
        for column in range(8):
            packed = raw[row * 4 + column // 2]
            pixel = packed & 15 if column & 1 else packed >> 4
            mapped = (pixel + 4) // 5 if pixel else 0
            low[row] |= (mapped & 1) << (7 - column)
            high[row] |= ((mapped >> 1) & 1) << (7 - column)
    return bytes(low + high)


def _reference_patterns(rom):
    """Source AnimGlobe rules: water/8, fire/4, belts +/-Anim from H/V."""
    globe = _slz(rom, 0x5FE8)
    belt = _slz(rom, 0x9D60)
    result = []
    for animation in range(32):
        for kind in range(35):
            if kind == 3 or kind >= 23:
                buffer = rom[0x7960:0x8B60]
                base = (animation // 8) * 1152
            elif kind == 18:
                buffer = rom[0x8B60:0x9D60]
                base = ((animation // 4) % 4) * 1152
            elif kind in (11, 12, 13, 14):
                buffer = belt
                phase = ((-animation if kind in (11, 13) else animation) % 8) // 2
                base = (4608 if kind in (11, 12) else 0) + phase * 1152
            else:
                buffer = globe
                word = int.from_bytes(rom[0xA4CE + kind * 2:0xA4D0 + kind * 2], 'big')
                base = ((word & 2047) - 0x343) * 32
            for variant in range(9):
                for row in range(2):
                    for column in range(2):
                        start = base + variant * 128 + (column * 2 + row) * 32
                        result.append(_reference_tile(buffer[start:start + 32]))
    result.extend(_reference_tile(globe[i * 32:(i + 1) * 32]) for i in range(504, 552))
    return result


def projection_metrics(rom, assets):
    source = rom[0xA537:0x1A537]
    errors_x, errors_y, overlaps, anchor_collisions = [], [], [], []
    for view in range(256):
        coverage, anchors = Counter(), Counter()
        for sprite in range(64):
            at = view * 64 + sprite
            record = assets['projection'][at * 4:at * 4 + 4]
            x = int.from_bytes(source[at:at + 1], 'big', signed=True)
            y = int.from_bytes(source[16384 + at:16385 + at], 'big', signed=True)
            row, column = divmod(record[0], 16)
            assert row < 15 and column < 15
            assert record[1:] == bytes((source[32768 + at], source[49152 + at], 0))
            errors_x.append((column + 8) * 8 - (120 + x))
            errors_y.append((row + 12) * 8 - (144 + y))
            anchors[(row, column)] += 1
            for dy in range(2):
                for dx in range(2):
                    coverage[(row + dy, column + dx)] += 1
        overlaps.append(sum(n > 1 for n in coverage.values()))
        anchor_collisions.append(sum(n - 1 for n in anchors.values()))
    return {'views': 256, 'source_sprites_per_view': 64,
            'coordinates_checked': len(errors_x),
            'x_axis_error_max': max(map(abs, errors_x)),
            'y_axis_error_max': max(map(abs, errors_y)),
            'x_axis_error_rms': math.sqrt(sum(x*x for x in errors_x) / len(errors_x)),
            'y_axis_error_rms': math.sqrt(sum(x*x for x in errors_y) / len(errors_y)),
            'quantized_overlapping_cells_per_view_min': min(overlaps),
            'quantized_overlapping_cells_per_view_max': max(overlaps),
            'quantized_duplicate_anchors_per_view_max': max(anchor_collisions)}


@pytest.mark.parametrize(('offset', 'relative'), [
    (0x5FE8, 'src-data/globe/globe.4bpp'),
    (0x9D60, 'src-data/globe/belt.4bpp'),
])
def test_slz_matches_official_uncompressed_source_files(original, offset, relative):
    rom, upstream = original
    expected = upstream / relative
    if not expected.is_file():
        pytest.skip('official decompressed source files are not beside the private ROM')
    assert _slz(rom, offset) == expected.read_bytes()


@pytest.mark.parametrize(('offset', 'length', 'relative', 'key'), [
    (0xA537, 65536, 'table.lut', None),
    (0x1A537, 65536, 'objects.lut', 'objects'),
    (0x2A537, 65536, 'rafts.lut', 'rafts'),
    (0x3A537, 12288, 'ending.lut', 'ending'),
])
def test_projection_tables_are_exact_source_bytes(original, assets, offset, length, relative, key):
    rom, upstream = original
    expected = upstream / 'data/globe' / relative
    if not expected.is_file():
        pytest.skip('official LUT source files are not beside the private ROM')
    assert rom[offset:offset + length] == expected.read_bytes()
    if key:
        assert assets[key] == expected.read_bytes()


def test_all_256_views_retain_lookup_order_and_bound_quantization(original, assets):
    metrics = projection_metrics(original[0], assets)
    assert metrics['coordinates_checked'] == 16384
    assert metrics['x_axis_error_max'] == metrics['y_axis_error_max'] == 4
    assert assets['metrics']['projection_axis_error_max_pixels'] == 4


def test_all_32_animation_phases_match_source_orientation_and_report_art_loss(original, assets):
    sources = _reference_patterns(original[0])
    mapping = b''.join(assets['terrain_frames']) + assets['ending_ids']
    assert len(sources) == len(mapping) == 40368
    approximate = weighted = 0
    for expected, number in zip(sources, mapping):
        actual = assets['chr'][number * 16:(number + 1) * 16]
        alpha_error = sum(((expected[y] | expected[y + 8]) ^ (actual[y] | actual[y + 8])).bit_count() for y in range(8))
        bit_error = sum((a ^ b).bit_count() for a, b in zip(expected, actual))
        approximate += actual != expected
        weighted += 8 * alpha_error + bit_error
    assert len(set(sources)) == assets['metrics']['unique_adapted_patterns']
    assert approximate == assets['metrics']['approximated_pattern_instances']
    assert weighted == assets['metrics']['weighted_pattern_distance_total']
    assert assets['terrain_ids'] == assets['terrain_frames'][0] + assets['ending_ids']
    # Real and fake springs deliberately share the original appearance.
    for frame in assets['terrain_frames']:
        assert frame[9 * 36:10 * 36] == frame[10 * 36:11 * 36]


def test_player_quad_is_row_major_nearest_two_times_the_authored_glyph(assets):
    def pixel(tile, x, y):
        return ((tile[y] >> (7 - x)) & 1) | (((tile[y + 8] >> (7 - x)) & 1) << 1)
    source = assets['chr'][4096:4112]
    for y in range(16):
        for x in range(16):
            number = 32 + (y // 8) * 2 + x // 8
            tile = assets['chr'][4096 + number * 16:4112 + number * 16]
            assert pixel(tile, x % 8, y % 8) == pixel(source, x // 2, y // 2)
