"""Synthetic checks for the Civ media decoders; no private assets are used."""

from __future__ import annotations

import struct
from pathlib import Path

from examples.civ import civ_media


def pack_codes(codes, width=9):
    bits = 0
    count = 0
    out = bytearray()
    for code in codes:
        bits |= code << count
        count += width
        while count >= 8:
            out.append(bits & 0xFF)
            bits >>= 8
            count -= 8
    if count:
        out.append(bits & 0xFF)
    return bytes(out)


def image_chunk(width, height, codes, tag=b"X0", max_width=11):
    payload = struct.pack("<HHB", width, height, max_width) + pack_codes(codes)
    if width == 0 and height == 0:
        payload = struct.pack("<HH", 0, 0)
    return tag + struct.pack("<H", len(payload)) + payload


def m0_chunk(entries):
    payload = bytes([0, len(entries) - 1]) + b"".join(bytes(entry) for entry in entries)
    return b"M0" + struct.pack("<H", len(payload)) + payload


def test_x0_lzw_and_90h_rle_round_trip():
    # LZW codes produce 01 02 03 90 03; RLE expands the final run to 03 03.
    data = image_chunk(5, 1, [1, 2, 3, 0x90, 3])
    image = civ_media.decode_pic(data)
    assert (image["kind"], image["width"], image["height"]) == ("X0", 5, 1)
    assert image["pixels"] == bytes([1, 2, 3, 3, 3])
    assert image["lzw_bytes"] == 5
    assert image["rle_bytes"] == 5


def test_x1_nibbles_are_low_first():
    data = image_chunk(3, 1, [0x12, 0x30], tag=b"X1")
    image = civ_media.decode_pic(data)
    assert image["pixels"] == bytes([2, 1, 0])


def test_m0_palette_and_palette_only_file():
    data = m0_chunk([(63, 0, 0), (0, 63, 0)]) + image_chunk(0, 0, [])
    image = civ_media.decode_pic(data)
    assert image["width"] == image["height"] == 0
    assert image["palette"][0] == (63, 0, 0)
    assert image["palette"][1] == (0, 63, 0)
    palette = civ_media.decode_palette(data)
    assert palette["entries"] == [(63, 0, 0), (0, 63, 0)]


def test_fonts_cv_layout_and_glyph_rows():
    first, last = 0x20, 0x21
    start = 20
    widths = bytes([2, 2])
    header = bytes([first, last, 1, 0, 2, 0, 0, 0])
    bitmap = bytes([0x80, 0x40, 0x20, 0x10])
    data = bytearray(start + len(bitmap))
    struct.pack_into("<HH", data, 0, 1, start)
    data[10:12] = widths
    data[12:20] = header
    data[start:] = bitmap
    parsed = civ_media.parse_fonts(bytes(data))
    assert parsed["count"] == 1
    font = parsed["fonts"][0]
    assert (font.first, font.last, font.height, font.bytes_per_row) == (
        0x20,
        0x21,
        2,
        1,
    )
    assert font.widths == widths
    assert font.glyph(0x20) == bytes([0x80, 0x20])
    assert font.glyph(0x21) == bytes([0x40, 0x10])
    sheet = civ_media.font_sheet(font, columns=2)
    assert sheet["width"] > 0 and sheet["height"] == 2


def test_world_projection_extracts_page2_layers():
    pixels = bytearray(320 * 200)
    x, y = 2, 3
    pixels[y * 320 + x] = 2  # Grassland
    pixels[y * 320 + x + 160] = 0x0B  # unit present, owner 3
    pixels[(y + 100) * 320 + x] = 0x02  # irrigation
    pixels[(y + 150) * 320 + x] = 0x01  # railroad
    pixels[(y + 100) * 320 + x + 80] = 0x04  # known mine
    world = civ_media.extract_world_map(bytes(pixels))
    index = y * 80 + x
    assert world["terrain"][index] == 3
    assert world["terrain_colour"][index] == 2
    assert world["unit"][index] is True
    assert world["owner"][index] == 3
    assert world["improvements"][index] == 0x12
    assert world["known"][index] == 0x04
    assert world["rows"][y][x] == "F"  # Forest; uppercase marks the unit
    assert len(world["rows"]) == 50 and len(world["rows"][0]) == 80


def test_media_names_are_executable_references_only():
    names = civ_media.media_names(
        b"\x00SP257.PIC\x00fonts.cv\x00CIVIL0.SVE\x00not_media.txt\x00"
    )
    assert names == ["CIVIL0.SVE", "FONTS.CV", "NOT_MEDIA.TXT", "SP257.PIC"]


def test_extract_assets_writes_manifest_and_png(tmp_path):
    exe = tmp_path / "CIV.EXE"
    exe.write_bytes(b"\x00TEST.PIC\x00")
    assets = tmp_path / "assets"
    assets.mkdir()
    image = m0_chunk([(63, 0, 0), (0, 63, 0)]) + image_chunk(2, 1, [1, 2])
    (assets / "TEST.PIC").write_bytes(image)
    out = tmp_path / "out"
    manifest = civ_media.extract_assets(exe, assets, out)
    assert manifest["embedded_media"] is False
    record = manifest["assets"][0]
    assert record["name"] == "TEST.PIC"
    assert record["width"] == 2 and record["height"] == 1
    assert Path(record["png"]).is_file()
    assert json_load(out / "manifest.json")["assets"][0]["sha256"] == civ_media.sha256(
        image
    )


def json_load(path):
    import json

    return json.loads(Path(path).read_text())
