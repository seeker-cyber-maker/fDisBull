from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import civ_world


def fixture() -> tuple[bytes, bytes]:
    sve = bytearray(civ_world.SVE_SIZE)
    struct.pack_into("<8h", sve, 0, 12, 0, 1, 0, 1000, 0, 1, 0)
    struct.pack_into("<8h", sve, 0x0778, -1, 1, 2, 11, 12, 13, 6, 7)
    struct.pack_into("<8h", sve, 0x06C8, 1, 0, 0, 0, 0, 0, 0, 0)
    sve[0x6970 : 0x6970 + 5] = b"Test\0"
    # One Roman city and one Settlers unit.
    city = 0x1508
    struct.pack_into("<I", sve, city, 1)
    struct.pack_into("<8b", sve, city + 4, 10, 10, 0, 3, 3, 0, 0, 1)
    sve[city + 22] = 0
    sve[city + 23 : city + 26] = b"\xff\xff\xff"
    sve[city + 26 : city + 28] = b"\xff\xff"
    for index in range(8 * 128):
        sve[0x26C0 + index * 12 + 3] = 0xFF
    unit = 0x26C0
    struct.pack_into("<3B", sve, unit, 0, 11, 10)
    struct.pack_into("<9b", sve, unit + 3, 0, 3, 0, -1, -1, -1, 1, -1, -1)
    utype = 0x2308
    sve[utype : utype + 12] = b"Settlers\0\0\0\0"
    page = bytearray(civ_world.PAGE_WIDTH * civ_world.PAGE_HEIGHT)
    for y in range(civ_world.MAP_HEIGHT):
        for x in range(civ_world.MAP_WIDTH):
            page[y * 320 + x] = 10  # Ocean
    page[10 * 320 + 10] = 2  # Forest under the city
    page[10 * 320 + 11] = 1  # Ocean under the unit
    page[(100 + 10) * 320 + 10] = 1  # city flag
    page[10 * 320 + 160 + 10] = 8  # unit-present, civ 0
    page[10 * 320 + 160 + 11] = 8
    sve[0x56C0 + 10 * 50 + 10] = 1
    return bytes(sve), bytes(page)


def test_world_from_synthetic_page():
    sve, page = fixture()
    world = civ_world.world_from_page(
        sve, page, edition="fixture", sve_name="CIVIL0.SVE", map_name="CIVIL0.MAP"
    )
    assert world["dimensions"] == [80, 50]
    assert world["turn"] == 12 and world["year"] == 1000
    assert world["civ_labels"][1] == "Roman"
    assert world["terrain"][10][10] == 3
    assert world["flags"][10][10] & 1
    assert world["unit_owner"][10][10] == 0
    assert world["unit_owner"][10][11] == 0
    assert len(world["cities"]) == 1
    assert world["cities"][0]["owner_label"] == "Roman"
    assert len(world["units"]) == 1
    assert world["units"][0]["type_name"] == "Settlers"
    assert world["stats"]["city_tile_mismatches"] == 0
    assert world["stats"]["unit_tile_mismatches"] == 0
    assert world["source_state_sha256"]
    assert len(civ_world.render_ascii(world).splitlines()) > 50
    html = civ_world.render_html(world)
    assert "<canvas" in html and "Settlers" in html


def test_rle_trailing_run():
    assert civ_world.decode_rle(b"A\x90\x04", 4) == b"AAAA"


def test_real_save_snapshot():
    directory = Path(
        os.environ.get(
            "CIV_SAVE_DIR",
            "/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/targets/civilization-dos-ru-47501",
        )
    )
    sve = directory / "CIVIL0.SVE"
    map_file = directory / "CIVIL0.MAP"
    if not sve.exists() or not map_file.exists():
        pytest.skip("private Civilization I 47501 save pair is not present")
    world = civ_world.read_world(sve, map_file, edition="ru-47501")
    assert world["stats"]["cities"] == 41
    assert world["stats"]["units"] == 172
    assert world["stats"]["declared_cities"] == 41
    assert world["turn"] == 308 and world["year"] == 1540
    assert world["stats"]["terrain_counts"]["Ocean"] == 2969
    assert world["stats"]["city_tile_mismatches"] == 0
    assert world["stats"]["unit_tile_mismatches"] == 1
    assert (
        world["source"]["sve_sha256"]
        == "a6164c93bcb5ee75ba09b407b2dff527a2433993b963c48b3e573c6e06ffc63b"
    )
    assert (
        world["source"]["map_file_sha256"]
        == "ea82bbca9ee1e6c87cc7ed17fa153ab7251c5e94968f35d8eb3bc1f0fff0b922"
    )
    page = civ_world.decode_map(map_file.read_bytes())
    assert len(page) == 64000
    assert len(civ_world.render_ascii(world).splitlines()) == 110
    assert json.dumps(world)[:1] == "{"
