"""Bounded decoders for the Civilization DOS media formats.

The private game files are not in this repository. This module decodes caller-
supplied bytes using the formats documented in ``docs/CIV_MEDIA_FORMATS.md``:
PIC/PAL chunk streams (E0/M0/X0/X1 with LZW and 90h-RLE), FONTS.CV, the
320x200 page-2 ``.MAP`` image, and a reduced 80x50 world projection.

The decoder is intentionally format-scoped and read-only. It does not execute
the DOS program, guess a palette when a file has none, or treat a rendered page
as live game state. ``.MAP`` is the save-side page-2 image written by the
original; extracting layers from it is an observation of that image, not proof
of the live map fields.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

PIC_TAGS = (b"E0", b"M0", b"X0", b"X1")
MAX_INPUT = 4 * 1024 * 1024
MAX_PIXELS = 1024 * 1024
MAX_CODES = 8 * 1024 * 1024
WIDTH, HEIGHT = 80, 50
MAP_PAGE_WIDTH, MAP_PAGE_HEIGHT = 320, 200

# Civd MAP.C:385.  -1 means the colour carries no terrain.
TERRAIN_BY_COLOUR = (-1, 10, 3, 8, -1, -1, 1, 6, -1, 11, 2, 9, 4, 5, 0, 7)
TERRAIN_NAMES = (
    "Desert",
    "Plains",
    "Grassland",
    "Forest",
    "Hills",
    "Mountains",
    "Tundra",
    "Arctic",
    "Swamp",
    "Jungle",
    "Ocean",
    "River",
)
TERRAIN_GLYPHS = "dPgFhMtAsJ~r"
IMPROVEMENTS = {
    0x01: "city",
    0x02: "irrigation",
    0x04: "mine",
    0x08: "road",
    0x10: "railroad",
    0x20: "fortress",
    0x40: "pollution",
}
MEDIA_SUFFIXES = (".PIC", ".PAL", ".TXT", ".CV", ".CVL", ".SVE", ".MAP")
_MEDIA_NAME = re.compile(
    rb"[A-Za-z0-9_]{1,12}\.(?:PIC|PAL|TXT|CV|CVL|SVE|MAP)", re.IGNORECASE
)


class MediaError(ValueError):
    """The supplied bytes are not a bounded, internally consistent asset."""


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise MediaError("word exceeds input")
    return struct.unpack_from("<H", data, offset)[0]


def _need(ok: object, message: str) -> None:
    if not ok:
        raise MediaError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bits_lsb(data: bytes):
    for byte in data:
        for bit in range(8):
            yield (byte >> bit) & 1


class _BitReader:
    def __init__(self, data: bytes):
        self._bits = _bits_lsb(data)
        self._buffer = 0
        self._count = 0

    def read(self, width: int) -> int | None:
        while self._count < width:
            try:
                self._buffer |= next(self._bits) << self._count
            except StopIteration:
                return None
            self._count += 1
        value = self._buffer & ((1 << width) - 1)
        self._buffer >>= width
        self._count -= width
        return value


def _rle_decode(data: bytes) -> bytes:
    """Decode the 90h-RLE stage used after LZW.

    A 90h 00 pair is a literal 90h. A 90h n pair with n > 1 repeats the
    previous byte n - 1 more times. The n == 1 case is the original's 256-copy
    edge; it does not occur in the sampled release files.
    """
    out = bytearray()
    last: int | None = None
    cursor = 0
    while cursor < len(data):
        value = data[cursor]
        cursor += 1
        if value != 0x90:
            out.append(value)
            last = value
            continue
        if cursor >= len(data):
            break
        count = data[cursor]
        cursor += 1
        if count == 0:
            out.append(0x90)
            last = 0x90
        elif count == 1:
            if last is not None:
                out.extend([last] * 256)
        elif last is not None:
            out.extend([last] * (count - 1))
        _need(len(out) <= MAX_CODES, "RLE output exceeds budget")
    return bytes(out)


def _lzw_decode(stream: bytes, max_width: int) -> bytes:
    _need(9 <= max_width <= 12, "invalid LZW maximum width")
    prefix = [0xFFFF] * 4096
    suffix = bytearray(4096)
    for index in range(256):
        suffix[index] = index
    width = 9
    mask = 0x1FF
    next_code = 0x100
    previous_code = 0
    previous_string = b"\x00"
    reader = _BitReader(stream)
    out = bytearray()

    def string_for(code: int) -> bytes:
        parts = []
        seen = 0
        while code != 0xFFFF:
            _need(0 <= code < 4096 and seen <= 4096, "invalid LZW dictionary chain")
            parts.append(suffix[code])
            code = prefix[code]
            seen += 1
        parts.reverse()
        return bytes(parts)

    while True:
        code = reader.read(width)
        if code is None:
            break
        if code < next_code:
            current = string_for(code)
        elif code == next_code:
            current = previous_string + previous_string[:1]
        else:
            raise MediaError("LZW code is ahead of the dictionary")
        out.extend(current)
        _need(len(out) <= MAX_CODES, "LZW output exceeds budget")
        if next_code < 4096:
            prefix[next_code] = previous_code
            suffix[next_code] = current[0]
            next_code += 1
        previous_code = code
        previous_string = current
        if next_code > mask:
            width += 1
            mask = (mask << 1) | 1
            if width > max_width:
                for index in range(4096):
                    prefix[index] = 0xFFFF
                width = 9
                mask = 0x1FF
                next_code = 0x100
    return bytes(out)


def _palette_from_m0(payload: bytes) -> dict:
    _need(len(payload) >= 2, "truncated M0 palette")
    first, last = payload[0], payload[1]
    _need(
        first <= last and 2 + 3 * (last - first + 1) <= len(payload),
        "invalid M0 length",
    )
    entries = []
    cursor = 2
    for _ in range(first, last + 1):
        entries.append(tuple(payload[cursor : cursor + 3]))
        cursor += 3
    _need(len(entries) == last - first + 1, "truncated M0 entries")
    palette = [(0, 0, 0)] * 256
    for offset, entry in enumerate(entries):
        palette[first + offset] = entry
    return {
        "first": first,
        "last": last,
        "entries": entries,
        "palette": palette,
    }


def decode_pic(data: bytes) -> dict:
    """Decode one PIC/PAL/MAP chunk stream into indexed pixels.

    Returns width, height, kind (X0/X1), chunks, optional M0 palette, raw
    pixels (one byte per pixel, row-major) and SHA-256 identities.
    """
    _need(isinstance(data, bytes) and 0 < len(data) <= MAX_INPUT, "invalid PIC input")
    cursor = 0
    chunks = []
    palette = None
    palette_info = None
    image = None
    while cursor + 4 <= len(data):
        tag = data[cursor : cursor + 2]
        length = _u16(data, cursor + 2)
        cursor += 4
        if tag[:1] == b"X":
            payload = data[cursor:]
            _need(tag in PIC_TAGS, "unknown X chunk")
            _need(len(payload) >= 4, "truncated image header")
            width = _u16(payload, 0)
            height = _u16(payload, 2)
            _need(width * height <= MAX_PIXELS, "image exceeds pixel budget")
            _need(
                width > 0 and height > 0 or width == height == 0,
                "invalid image dimensions",
            )
            if width == height == 0:
                image = (tag, 0, 0, 0, b"")
            else:
                _need(len(payload) >= 5, "truncated image header")
                image = (tag, width, height, payload[4], payload[5:])
            break
        _need(cursor + length <= len(data), "chunk exceeds input")
        payload = data[cursor : cursor + length]
        cursor += length
        chunks.append(
            {"tag": tag.decode("ascii"), "length": length, "sha256": sha256(payload)}
        )
        if tag == b"M0":
            palette_info = _palette_from_m0(payload)
            palette = palette_info["palette"]
        elif tag == b"E0":
            _need(length >= 2, "truncated E0 chunk")
    _need(image is not None, "no X image chunk")
    tag, width, height, max_width, stream = image
    if width == 0 and height == 0:
        return {
            "kind": tag.decode("ascii"),
            "width": 0,
            "height": 0,
            "chunks": chunks,
            "palette": palette,
            "palette_info": palette_info,
            "pixels": b"",
            "sha256": sha256(data),
            "pixel_sha256": sha256(b""),
            "lzw_bytes": 0,
            "rle_bytes": 0,
        }
    lzw = _lzw_decode(stream, max_width)
    rle = _rle_decode(lzw)
    if tag == b"X0":
        needed = width * height
        _need(len(rle) >= needed, "decoded rows are short")
        pixels = rle[:needed]
    else:
        row_bytes = (width + 1) // 2
        needed = row_bytes * height
        _need(len(rle) >= needed, "decoded rows are short")
        pixels = bytearray(width * height)
        cursor = 0
        for row in range(height):
            source = rle[row * row_bytes : (row + 1) * row_bytes]
            for column in range(width):
                byte = source[column // 2]
                pixels[row * width + column] = (
                    (byte & 0x0F) if column % 2 == 0 else (byte >> 4)
                )
        pixels = bytes(pixels)
    return {
        "kind": tag.decode("ascii"),
        "width": width,
        "height": height,
        "chunks": chunks,
        "palette": palette,
        "palette_info": palette_info,
        "pixels": pixels,
        "sha256": sha256(data),
        "pixel_sha256": sha256(pixels),
        "lzw_bytes": len(lzw),
        "rle_bytes": len(rle),
    }


def decode_palette(data: bytes) -> dict:
    """Decode a PAL or return the M0 palette of a PIC."""
    image = decode_pic(data)
    _need(image["palette"] is not None, "asset has no M0 palette")
    return {
        "first": image["palette_info"]["first"],
        "last": image["palette_info"]["last"],
        "entries": image["palette_info"]["entries"],
        "palette": image["palette"],
    }


@dataclass(frozen=True)
class Font:
    number: int
    first: int
    last: int
    bytes_per_row: int
    fixed_advance: int
    height: int
    spacing: int
    extra_rows: int
    widths: bytes
    bitmap: bytes

    @property
    def codes(self) -> int:
        return self.last - self.first + 1

    def glyph(self, code: int) -> bytes:
        _need(self.first <= code <= self.last, "glyph code out of range")
        index = code - self.first
        stride = self.codes * self.bytes_per_row
        rows = self.height + self.extra_rows
        out = bytearray()
        for row in range(rows):
            start = row * stride + index * self.bytes_per_row
            out.extend(self.bitmap[start : start + self.bytes_per_row])
        return bytes(out)


def parse_fonts(data: bytes) -> dict:
    """Parse FONTS.CV.  Returns fonts and a file-level identity."""
    _need(isinstance(data, bytes) and 0 < len(data) <= MAX_INPUT, "invalid font input")
    count = _u16(data, 0)
    _need(1 <= count <= 64, "invalid font count")
    _need(2 + 2 * count <= len(data), "truncated font offset table")
    fonts = []
    for number in range(1, count + 1):
        start = _u16(data, 2 * number)
        _need(8 <= start <= len(data), "font start out of range")
        first, last, bytes_per_row, fixed, height, spacing, extra, _reserved = data[
            start - 8 : start
        ]
        _need(first <= last, "invalid font code range")
        _need(bytes_per_row in (1, 2), "invalid font row width")
        _need(1 <= height <= 64 and extra <= 64, "invalid font height")
        codes = last - first + 1
        widths = b""
        bitmap_start = start
        if fixed == 0:
            widths_start = start - 8 - codes
            _need(widths_start >= 0, "truncated font width table")
            widths = data[widths_start : start - 8]
            for width in widths:
                _need(width <= 32, "font width out of range")
        size = codes * bytes_per_row * (height + extra)
        _need(bitmap_start + size <= len(data), "truncated font bitmap")
        fonts.append(
            Font(
                number=number,
                first=first,
                last=last,
                bytes_per_row=bytes_per_row,
                fixed_advance=fixed,
                height=height,
                spacing=spacing,
                extra_rows=extra,
                widths=widths,
                bitmap=data[bitmap_start : bitmap_start + size],
            )
        )
    return {
        "count": count,
        "fonts": fonts,
        "sha256": sha256(data),
    }


def font_sheet(font: Font, *, columns: int = 16, scale: int = 1) -> dict:
    """Render one font as a 1-bit indexed sheet for PNG inspection."""
    _need(1 <= columns <= 64 and 1 <= scale <= 8, "invalid sheet bounds")
    widths = []
    for code in range(font.first, font.last + 1):
        widths.append(font.fixed_advance or font.widths[code - font.first])
    cell_width = max(widths or [1]) * scale
    cell_height = (font.height + font.extra_rows) * scale
    rows = (font.codes + columns - 1) // columns
    width = max(1, columns * cell_width)
    height = max(1, rows * cell_height)
    pixels = bytearray(width * height)
    for index, code in enumerate(range(font.first, font.last + 1)):
        glyph = font.glyph(code)
        column = index % columns
        row = index // columns
        for y in range(font.height + font.extra_rows):
            for x in range(font.widths[index] if font.widths else cell_width):
                offset = y * font.bytes_per_row + x // 8
                byte = glyph[offset] if offset < len(glyph) else 0
                if byte & (0x80 >> (x % 8)):
                    for sy in range(scale):
                        for sx in range(scale):
                            px = (column * cell_width) + x * scale + sx
                            py = (row * cell_height) + y * scale + sy
                            pixels[py * width + px] = 255
    return {"width": width, "height": height, "pixels": bytes(pixels)}


def write_png(
    path: str | Path, *, width: int, height: int, pixels: bytes, palette=None
) -> None:
    """Write a small indexed or grayscale PNG without external packages."""
    _need(
        width > 0 and height > 0 and len(pixels) == width * height, "invalid PNG pixels"
    )
    if palette is not None:
        _need(len(palette) == 256, "palette must have 256 entries")
        color_type = 3
        plte = b"".join(
            bytes(round(value * 255 / 63) for value in entry) for entry in palette[:256]
        )
        raw = b"".join(
            b"\x00" + pixels[row * width : (row + 1) * width] for row in range(height)
        )
    else:
        color_type = 0
        plte = b""
        raw = b"".join(
            b"\x00" + pixels[row * width : (row + 1) * width] for row in range(height)
        )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    if plte:
        body += chunk(b"PLTE", plte)
    body += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    Path(path).write_bytes(body)


def media_names(data: bytes) -> list[str]:
    """Return the media names named by an executable image, sorted."""
    _need(isinstance(data, bytes), "invalid executable bytes")
    return sorted(
        {match.group(0).decode("ascii").upper() for match in _MEDIA_NAME.finditer(data)}
    )


def terrain_type(colour: int) -> int:
    _need(type(colour) is int and 0 <= colour < 16, "terrain colour out of range")
    return TERRAIN_BY_COLOUR[colour]


def extract_world_map(
    pixels: bytes, *, width: int = MAP_PAGE_WIDTH, height: int = MAP_PAGE_HEIGHT
) -> dict:
    """Extract the original page-2 world projection from one 320x200 image.

    Page 2 stores an 80x50 terrain-colour layer at (x, y), unit ownership at
    (x + 160, y), and improvement/known bits at (x, y + 100)/(x, y + 150) and
    (x + 80, y + 100)/(x + 80, y + 150). See Civ64 SCENES-PLAY 1.1 and Civd
    MAP.C:385 for the colour-to-terrain table.
    """
    _need(
        width == MAP_PAGE_WIDTH and height == MAP_PAGE_HEIGHT,
        "world projection requires 320x200",
    )
    _need(len(pixels) == width * height, "pixel length mismatch")

    def pixel(x: int, y: int) -> int:
        return pixels[y * width + x]

    terrain_colour = []
    terrain = []
    owner = []
    unit = []
    improvements = []
    known = []
    minimap = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            colour = pixel(x, y)
            terrain_colour.append(colour)
            terrain.append(terrain_type(colour))
            unit_value = pixel(x + 160, y)
            owner.append(unit_value & 7)
            unit.append(bool(unit_value & 8))
            low = pixel(x, y + 100) & 0x0F
            high = pixel(x, y + 150) & 0x0F
            improvements.append(low | (high << 4))
            known.append(
                (pixel(x + 80, y + 100) & 0x0F) | ((pixel(x + 80, y + 150) & 0x0F) << 4)
            )
            minimap.append(pixel(240 + x, y))
    glyphs = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            index = y * WIDTH + x
            code = terrain[index]
            glyph = "?" if code < 0 else TERRAIN_GLYPHS[code]
            row.append(glyph.upper() if unit[index] else glyph)
        glyphs.append("".join(row))
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "terrain_colour": terrain_colour,
        "terrain": terrain,
        "owner": owner,
        "unit": unit,
        "improvements": improvements,
        "known": known,
        "minimap": minimap,
        "rows": glyphs,
        "terrain_names": list(TERRAIN_NAMES),
        "improvement_names": IMPROVEMENTS,
        "source": "Civ DOS page 2; Civ64 SCENES-PLAY 1.1; civd MAP.C:385",
    }


def extract_assets(
    exe: str | Path,
    asset_dir: str | Path,
    out_dir: str | Path,
    *,
    include_saves: bool = False,
    all_assets: bool = False,
) -> dict:
    """Decode the media names referenced by ``exe`` and write a manifest.

    The original stores pictures, palettes and fonts as separate files; the
    executable only names them. This function records that distinction. It
    never writes into ``asset_dir`` and refuses to overwrite a non-empty
    output directory.
    """
    exe = Path(exe)
    asset_dir = Path(asset_dir)
    out_dir = Path(out_dir)
    _need(exe.is_file() and asset_dir.is_dir(), "missing executable or asset directory")
    _need(
        not out_dir.exists() or not any(out_dir.iterdir()),
        "output directory is not empty",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    exe_bytes = exe.read_bytes()
    names = media_names(exe_bytes)
    if all_assets:
        names.extend(
            sorted(
                {
                    path.name.upper()
                    for path in asset_dir.iterdir()
                    if path.is_file() and path.suffix.upper() in (".PIC", ".PAL", ".CV")
                }
            )
        )
    if include_saves:
        names.extend(sorted({path.name.upper() for path in asset_dir.glob("*.MAP")}))
    names = sorted(set(names))
    manifest = {
        "format": "fdisbull-civ-media-manifest-1",
        "executable": {
            "path": str(exe),
            "sha256": sha256(exe_bytes),
            "bytes": len(exe_bytes),
        },
        "asset_dir": str(asset_dir),
        "embedded_media": False,
        "note": "CIV.EXE names external media files; no picture/font bytes are embedded by this decoder.",
        "assets": [],
        "missing": [],
    }
    seen: set[str] = set()
    for raw_name in names:
        name = raw_name
        if not (asset_dir / name).is_file() and name[:1].isdigit():
            candidate = name[1:]
            if (asset_dir / candidate).is_file():
                name = candidate
        if name in seen:
            continue
        seen.add(name)
        source = asset_dir / name
        if not source.is_file():
            manifest["missing"].append(raw_name)
            continue
        record = {"name": name, "present": True}
        data = source.read_bytes()
        record.update({"bytes": len(data), "sha256": sha256(data)})
        suffix = source.suffix.upper()
        try:
            if suffix in (".PIC", ".MAP"):
                image = decode_pic(data)
                record.update(
                    {
                        "kind": image["kind"],
                        "width": image["width"],
                        "height": image["height"],
                        "chunks": image["chunks"],
                        "pixel_sha256": image["pixel_sha256"],
                        "has_palette": image["palette"] is not None,
                    }
                )
                stem = out_dir / f"{source.stem}.png"
                if image["width"] and image["height"]:
                    write_png(
                        stem,
                        width=image["width"],
                        height=image["height"],
                        pixels=image["pixels"],
                        palette=image["palette"] if image["palette"] else None,
                    )
                    record["png"] = str(stem)
                if suffix == ".MAP":
                    world = extract_world_map(image["pixels"])
                    record["world"] = {
                        "width": world["width"],
                        "height": world["height"],
                        "rows": world["rows"],
                        "terrain_sha256": sha256(bytes(world["terrain"])),
                    }
            elif suffix == ".PAL":
                palette = decode_palette(data)
                record.update(
                    {
                        "first": palette["first"],
                        "last": palette["last"],
                        "entries": palette["entries"],
                    }
                )
            elif suffix == ".CV":
                parsed = parse_fonts(data)
                record.update(
                    {
                        "font_count": parsed["count"],
                        "fonts": [
                            {
                                "number": font.number,
                                "first": font.first,
                                "last": font.last,
                                "height": font.height,
                                "bytes_per_row": font.bytes_per_row,
                                "fixed_advance": font.fixed_advance,
                            }
                            for font in parsed["fonts"]
                        ],
                    }
                )
                for font in parsed["fonts"]:
                    sheet = font_sheet(font)
                    path = out_dir / f"font-{font.number}.png"
                    write_png(
                        path,
                        width=sheet["width"],
                        height=sheet["height"],
                        pixels=sheet["pixels"],
                    )
                record["font_sheets"] = [
                    str(out_dir / f"font-{font.number}.png") for font in parsed["fonts"]
                ]
        except MediaError as exc:
            record["error"] = str(exc)
        manifest["assets"].append(record)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    """CLI for a private asset directory; output must be a new/empty folder."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, help="CIV.EXE whose media names are scanned")
    parser.add_argument("--assets", required=True, help="directory holding the external media")
    parser.add_argument("--out", required=True, help="new/empty output directory")
    parser.add_argument(
        "--include-saves",
        action="store_true",
        help="also decode CIVILn.MAP page-2 images in the asset directory",
    )
    parser.add_argument(
        "--all-assets",
        action="store_true",
        help="decode every PIC/PAL/CV in the directory, not only EXE-named files",
    )
    args = parser.parse_args(argv)
    manifest = extract_assets(
        args.exe,
        args.assets,
        args.out,
        include_saves=args.include_saves,
        all_assets=args.all_assets,
    )
    summary = {
        "executable_sha256": manifest["executable"]["sha256"],
        "assets": len(manifest["assets"]),
        "missing": len(manifest["missing"]),
        "png": sum(1 for item in manifest["assets"] if "png" in item),
        "font_files": sum(1 for item in manifest["assets"] if "font_sheets" in item),
        "errors": sum(1 for item in manifest["assets"] if "error" in item),
        "manifest": str(Path(args.out) / "manifest.json"),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
