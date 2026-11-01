from fdisbull.shadowrun_scene_assets import (
    PlaneScroll,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    UnsupportedVDPState,
    _tile,
    decode_plane_maps,
    decode_uniform_scroll,
    decode_vdp_snapshot,
    mosaic_world_views,
    mosaic_absolute_world_views,
)
from dataclasses import replace
import fdisbull.shadowrun_scene_assets as scene_assets


def _set_vram_byte(vram: bytearray, address: int, value: int) -> None:
    vram[address ^ 1] = value


def _set_vram_word(vram: bytearray, address: int, value: int) -> None:
    _set_vram_byte(vram, address, (value >> 8) & 0xFF)
    _set_vram_byte(vram, address + 1, value & 0xFF)


def _snapshot():
    vram = bytearray(0x10000)
    cram = bytearray(0x80)
    vsram = bytearray(0x80)
    regs = bytearray(0x20)
    # Mode 5, H40, 64x32 planes, table bases matching a common layout.
    regs[1] = 0x04
    regs[2] = 0x30  # Plane A at C000
    regs[3] = 0x3C  # Window at F000
    regs[4] = 0x07  # Plane B at E000
    regs[5] = 0x68  # SAT at D000
    regs[12] = 0x81
    regs[16] = 0x01
    # First tile: pixels [1, 2, 3, 4, 5, 6, 7, 8] on every row.
    for y in range(8):
        for x in range(8):
            value = x + 1
            address = 32 + y * 4 + (x >> 1)
            old = vram[address ^ 1]
            vram[address ^ 1] = ((value << 4) | (old & 15)) if not (x & 1) else ((old & 0xF0) | value)
    # Plane A uses tile 0, priority low; Plane B uses tile 0 with priority high.
    _set_vram_word(vram, 0xC000, 1)
    _set_vram_word(vram, 0xE000, 0xA001)
    # A one-tile sprite at screen (8, 8), with its first source pixel visible.
    sat = bytearray(0x400)
    for address, value in ((0, 136), (2, 0x0000), (4, 0x2001), (6, 136)):
        _set_vram_word(sat, address, value)
    cram[4:6] = bytes((0x49, 0x00))
    cram[6:8] = bytes((0x92, 0x00))
    return bytes(vram), bytes(cram), bytes(vsram), bytes(regs), bytes(sat)


def test_decode_returns_composited_palette_indices_and_separate_sprite():
    vram, cram, vsram, regs, sat = _snapshot()
    scene = decode_vdp_snapshot(vram, cram, vsram, regs, sat=sat)

    assert (scene.width, scene.height) == (SCREEN_WIDTH, SCREEN_HEIGHT)
    assert len(scene.background) == SCREEN_WIDTH * SCREEN_HEIGHT
    # High-priority Plane B covers the low-priority Plane A at its first pixel.
    assert scene.background[0] == 17
    assert scene.background[1] == 18
    assert scene.palette_words[2] == 0x0049
    assert scene.palette_rgb[2] == (32, 32, 32)
    assert scene.palette_rgb[3] == (65, 68, 65)
    assert len(scene.sprites) == 1
    sprite = scene.sprites[0]
    assert (sprite.x, sprite.y, sprite.width, sprite.height) == (8, 8, 8, 8)
    assert sprite.palette == 1
    assert sprite.pixels[:8] == bytes(range(1, 9))
    assert set(dict(scene.input_hashes)) == {"vram", "cram", "vsram", "registers", "sat"}
    assert scene.source_layout


def test_sprite_flips_and_shadow_highlight_tags_are_separate():
    vram, cram, vsram, regs, _ = _snapshot()
    vram = bytearray(vram)
    regs = bytearray(regs)
    regs[12] |= 0x08
    sat = bytearray(0x400)
    # Palette zero, horizontal+vertical flip. tile 0 includes palette colors 1..8.
    for address, value in ((0, 136), (2, 0x0001), (4, 0x1801), (6, 136)):
        _set_vram_word(sat, address, value)
    scene = decode_vdp_snapshot(bytes(vram), cram, vsram, bytes(regs), sat=bytes(sat))
    sprite = scene.sprites[0]
    assert sprite.hflip and sprite.vflip
    assert sprite.pixels[:8] == bytes(range(8, 0, -1))
    assert set(sprite.effects) == {0}


def test_plane_color_zero_is_transparent_to_other_plane():
    vram, cram, vsram, regs, sat = _snapshot()
    vram = bytearray(vram)
    _set_vram_word(vram, 0xC000, 0)  # Plane A uses all-zero tile 0.
    scene = decode_vdp_snapshot(bytes(vram), cram, vsram, regs, sat=sat)
    assert scene.background[0] == 17
    assert scene.background_source[0] == 1  # Plane B remains visible.


def test_rejects_invalid_sizes_modes_and_sat_link_loop():
    vram, cram, vsram, regs, sat = _snapshot()
    import pytest

    with pytest.raises(ValueError, match="exactly 65536"):
        decode_vdp_snapshot(vram[:-1], cram, vsram, regs)
    with pytest.raises(UnsupportedVDPState, match="RGB565"):
        decode_vdp_snapshot(vram, cram, vsram, regs, pixel_format="XRGB8888")
    regs = bytearray(regs)
    regs[12] = 0x00
    with pytest.raises(UnsupportedVDPState, match="H32"):
        decode_vdp_snapshot(vram, cram, vsram, bytes(regs))
    regs = bytearray(_snapshot()[3])
    regs[12] &= ~0x01
    with pytest.raises(UnsupportedVDPState, match="invalid H40"):
        decode_vdp_snapshot(vram, cram, vsram, bytes(regs))
    regs = bytearray(_snapshot()[3])
    regs[12] |= 0x02
    with pytest.raises(UnsupportedVDPState, match="interlaced"):
        decode_vdp_snapshot(vram, cram, vsram, bytes(regs))
    regs = bytearray(_snapshot()[3])
    sat = bytearray(sat)
    _set_vram_word(sat, 2, 0x0001)  # entry 0 links to 1
    _set_vram_word(sat, 8 + 2, 0x0001)  # entry 1 links back to itself
    with pytest.raises(UnsupportedVDPState, match="link loop"):
        decode_vdp_snapshot(vram, cram, vsram, regs, sat=bytes(sat))


def test_genesis_tile_pixels_decode_packed_nibbles():
    vram, _, _, _, _ = _snapshot()
    assert _tile(vram, 1)[:8] == bytes(range(1, 9))


def test_full_plane_maps_preserve_native_entries_and_referenced_patterns():
    vram, _, vsram, regs, _ = _snapshot()
    plane_a, plane_b, window = decode_plane_maps(vram, regs)
    assert [(p.name, p.width_cells, p.height_cells) for p in (plane_a, plane_b, window)] == [
        ("plane_a", 64, 32), ("plane_b", 64, 32), ("window", 64, 32)
    ]
    assert plane_a.base_address == 0xC000
    assert plane_a.entries[:2] == (1, 0)
    assert plane_b.entries[0] == 0xA001
    assert plane_a.pattern_tiles == (0, 1)
    assert len(plane_a.pattern_pixels) == 2 * 64
    assert plane_a.pattern_pixels[64:72] == bytes(range(1, 9))
    scroll_a, scroll_b = decode_uniform_scroll(regs, vram, vsram)
    assert (scroll_a.horizontal_native, scroll_a.vertical_native,
            scroll_a.horizontal_map, scroll_a.vertical_map) == (0, 0, 0, 0)
    assert (scroll_b.horizontal_native, scroll_b.vertical_native,
            scroll_b.horizontal_map, scroll_b.vertical_map) == (0, 0, 0, 0)


def test_uniform_scroll_rejects_line_or_cell_dependent_modes():
    import pytest

    vram, _, vsram, regs, _ = _snapshot()
    regs = bytearray(regs)
    regs[11] = 3
    with pytest.raises(UnsupportedVDPState, match="not uniform"):
        decode_uniform_scroll(bytes(regs), vram, vsram)


def test_horizontal_raster_sampling_subtracts_raw_hscroll():
    vram, cram, vsram, regs, sat = _snapshot()
    vram = bytearray(vram)
    regs = bytearray(regs)
    regs[13] = 0x20  # HScroll table at 0x8000, away from pattern data.
    _set_vram_word(vram, 0x8000, 5)
    _set_vram_word(vram, 0x8002, 5)
    scene = decode_vdp_snapshot(bytes(vram), cram, vsram, bytes(regs), sat=sat)
    assert scene.background[0] == 0  # x=0 samples map X=507, beyond the populated cell.
    assert scene.background[10] == 22  # x=10 samples map X=5 in tile 1.
    scroll_a, _ = decode_uniform_scroll(bytes(regs), bytes(vram), vsram)
    assert scroll_a.horizontal_native == 5
    assert scroll_a.horizontal_map == 507


def test_world_mosaic_tracks_coverage_conflicts_and_masks_sat():
    vram, cram, vsram, regs, sat = _snapshot()
    scene = decode_vdp_snapshot(vram, cram, vsram, regs, sat=sat)
    changed = bytearray(scene.background)
    changed[0] = 2
    second = replace(scene, background=bytes(changed))
    mosaic = mosaic_world_views(((scene, PlaneScroll(0, 0, 0, 0)),
                                 (second, PlaneScroll(0, 0, 0, 0))), 512, 256)
    assert (mosaic.width, mosaic.height) == (512, 256)
    assert mosaic.coverage[0] == 2
    assert mosaic.conflicts[0] == 1
    # Screen (8, 8) is covered by the source SAT sprite and is left unknown.
    assert mosaic.coverage[8 * 512 + 8] == 0
    assert mosaic.coverage[0 * 512 + 16] == 2


def test_world_mosaic_can_limit_to_gameplay_viewport():
    vram, cram, vsram, regs, sat = _snapshot()
    scene = decode_vdp_snapshot(vram, cram, vsram, regs, sat=sat)
    mosaic = mosaic_world_views(((scene, PlaneScroll(0, 0, 0, 0)),), 512, 256,
                                screen_crop_width=16)
    assert mosaic.coverage[10 * 512 + 7] == 1
    assert mosaic.coverage[10 * 512 + 16] == 0


def test_plane_decoder_decodes_each_referenced_tile_once(monkeypatch):
    vram, _, _, _, _ = _snapshot()
    calls = 0
    original = scene_assets._tile

    def counted(source, index):
        nonlocal calls
        calls += 1
        return original(source, index)

    monkeypatch.setattr(scene_assets, "_tile", counted)
    cache = {}
    scene_assets._plane_pixel(vram, 0, 64, cache, 0, 0)
    scene_assets._plane_pixel(vram, 0, 64, cache, 1, 0)
    assert calls == 1


def test_absolute_world_mosaic_uses_unwrapped_camera_coordinates():
    vram, cram, vsram, regs, sat = _snapshot()
    scene = decode_vdp_snapshot(vram, cram, vsram, regs, sat=sat)
    mosaic = mosaic_absolute_world_views(((scene, 100, 200),), 100, 200, 512, 480,
                                         screen_crop_width=16)
    assert mosaic.coverage[0] == 1
    assert mosaic.coverage[10 * 512 + 8] == 0  # SAT mask still applies.
    assert mosaic.coverage[0 * 512 + 16] == 0  # Screen crop bounds are respected.
    # A camera beyond the right world edge is clipped, never wrapped to X=0.
    clipped = mosaic_absolute_world_views(((scene, 500, 200),), 0, 200, 512, 480,
                                          screen_crop_width=16, mask_sprites=False)
    assert clipped.coverage[0] == 0
    assert clipped.coverage[15] == 0

