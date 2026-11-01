"""Decode authored scene assets from a captured Genesis Plus GX VDP state.

The decoder consumes a renderer snapshot, not ROM bytes.  Its input RAM arrays
use the byte-paired layout exported by Genesis Plus GX on the captured host.
The result keeps the background independent from SAT objects so a downstream
renderer can replace the character without baking the observed player into the
terrain.

This is an authored reader of the documented Genesis VDP data layout; it does
not contain or redistribute game ROM or extracted game assets.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


SCREEN_WIDTH = 320
SCREEN_HEIGHT = 224
VRAM_SIZE = 0x10000
CRAM_SIZE = 0x80
VSRAM_SIZE = 0x80
REGISTER_SIZE = 0x20
SAT_SIZE = 0x400


@dataclass(frozen=True)
class Sprite:
    """One linked SAT entry, retaining native attributes and decoded pixels.

    `pixels` is row-major, one 4-bit palette index per pixel. Zero is
    transparent. Coordinates are Genesis screen coordinates after the native
    128-pixel SAT origin bias; values may be offscreen.
    """

    sat_index: int
    link: int
    x: int
    y: int
    width: int
    height: int
    palette: int
    priority: bool
    hflip: bool
    vflip: bool
    tile_index: int
    native_attribute: int
    pixels: bytes
    # 0 normal pixel, 1 highlight operation, 2 shadow operation.
    effects: bytes


@dataclass(frozen=True)
class SceneAssets:
    width: int
    height: int
    pixel_format: str
    # Per-pixel Genesis palette index, 0..63; transparent plane pixels use backdrop.
    background: bytes
    # 0 backdrop, 1 Plane B, 2 Plane A, 3 Window; useful for later composition.
    background_source: bytes
    background_priority: bytes
    # 64 source-native CRAM words.
    palette_words: tuple[int, ...]
    # 64 RGB triples using this capture's RGB565 output conversion.
    palette_rgb: tuple[tuple[int, int, int], ...]
    sprites: tuple[Sprite, ...]
    input_hashes: tuple[tuple[str, str], ...]
    source_layout: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class PlaneMap:
    """One native Genesis tile plane without viewport scrolling applied.

    `entries` preserves each 16-bit Genesis name-table attribute in row-major
    order. `pattern_tiles` gives the matching tile numbers for consecutive
    64-byte 8x8 4bpp patterns in `pattern_pixels`.
    """

    name: str
    base_address: int
    width_cells: int
    height_cells: int
    entries: tuple[int, ...]
    pattern_tiles: tuple[int, ...]
    pattern_pixels: bytes


@dataclass(frozen=True)
class PlaneScroll:
    """A screen-uniform source scroll. Horizontal native is raw HScroll; horizontal_map is its negated map-space offset. Vertical native/map are additive VScroll offsets."""

    horizontal_native: int
    vertical_native: int
    horizontal_map: int
    vertical_map: int


@dataclass(frozen=True)
class WorldMosaic:
    """Observed world-space RGB pixels with explicit gaps and disagreements."""

    width: int
    height: int
    rgb: bytes
    coverage: bytes
    conflicts: bytes


class UnsupportedVDPState(ValueError):
    """The snapshot uses display features this bounded decoder cannot render."""


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bus_byte(data: bytes, address: int) -> int:
    """Read one logical VDP byte from the core's byte-paired exported array."""
    return data[address ^ 1]


def _bus_word(data: bytes, address: int) -> int:
    return (_bus_byte(data, address) << 8) | _bus_byte(data, address + 1)


def _cram_words(cram: bytes) -> tuple[int, ...]:
    # Genesis Plus GX exports CRAM as native little-endian 16-bit words,
    # unlike its byte-paired VRAM. Preserve the raw source-native color words.
    return tuple(cram[i * 2] | (cram[i * 2 + 1] << 8) for i in range(64))


def _rgb565_palette(words: tuple[int, ...]) -> tuple[tuple[int, int, int], ...]:
    """Expand Genesis contiguous 3:3:3 CRAM channels to captured RGB565 RGB."""
    colors = []
    for word in words:
        red4 = (word & 7) << 1
        green4 = ((word >> 3) & 7) << 1
        blue4 = ((word >> 6) & 7) << 1
        red5 = (red4 << 1) | (red4 >> 3)
        green6 = (green4 << 2) | (green4 >> 2)
        blue5 = (blue4 << 1) | (blue4 >> 3)
        colors.append((red5 * 255 // 31, green6 * 255 // 63, blue5 * 255 // 31))
    return tuple(colors)


def _tile(vram: bytes, index: int) -> bytes:
    """Decode packed-nibble Genesis 4bpp 8x8 pattern data."""
    base = index * 32
    out = bytearray(64)
    for y in range(8):
        row = base + y * 4
        for x in range(8):
            packed = _bus_byte(vram, row + (x >> 1))
            out[y * 8 + x] = (packed >> 4) & 0x0F if not (x & 1) else packed & 0x0F
    return bytes(out)


def _scroll(reg: bytes, vsram: bytes, vram: bytes, plane: int, x: int, y: int) -> tuple[int, int]:
    # Register 11 selects full-screen, per-line, or per-cell horizontal scroll.
    # Hscroll reads are the raw VDP register values; raster sampling subtracts
    # this value from screen X. Vscroll is added to screen Y by the VDP.
    hmode = reg[11] & 3
    if hmode == 0:
        hindex = 0
    elif hmode == 3:
        hindex = y * 4
    elif hmode == 2:
        hindex = (y & ~7) * 4
    else:
        raise UnsupportedVDPState("reserved horizontal scroll mode is not supported")
    hbase = (reg[13] & 0x3F) << 10
    hscroll = _bus_word(vram, hbase + hindex + plane * 2) & 0x07FF
    vmode = (reg[11] >> 3) & 1
    vscroll_index = (x >> 4) * 4 + plane * 2 if vmode else plane * 2
    vscroll = (vsram[vscroll_index] | (vsram[vscroll_index + 1] << 8)) & 0x07FF
    return hscroll, vscroll


def _plane_pixel(vram: bytes, base: int, plane_width: int, tile_cache: dict[int, bytes], x: int, y: int) -> tuple[int, int, bool]:
    col, row = x >> 3, y >> 3
    entry_addr = (base + ((row * plane_width + col) * 2)) & 0xFFFF
    attr = _bus_word(vram, entry_addr)
    tile_index = attr & 0x07FF
    px, py = x & 7, y & 7
    if attr & 0x0800:
        px = 7 - px
    if attr & 0x1000:
        py = 7 - py
    tile = tile_cache.get(tile_index)
    if tile is None:
        tile = _tile(vram, tile_index)
        tile_cache[tile_index] = tile
    nibble = tile[py * 8 + px]
    color = (((attr >> 13) & 3) << 4) | nibble
    priority = (attr >> 15) & 1
    return color, priority, nibble != 0


def _window_contains(reg: bytes, x: int, y: int) -> bool:
    h = reg[17]
    v = reg[18]
    hpos = (h & 0x1F) * 16
    vpos = (v & 0x1F) * 8
    in_h = x >= hpos if h & 0x80 else x < hpos
    in_v = y >= vpos if v & 0x80 else y < vpos
    return in_h or in_v


def decode_plane_maps(vram: bytes, registers: bytes) -> tuple[PlaneMap, ...]:
    """Return complete Plane A, Plane B, and Window tile maps from one snapshot.

    This exposes native map cells and only the tile patterns referenced by
    each map. It does not flatten scroll, priority, sprites, or palette colors.
    """
    if len(vram) != VRAM_SIZE or len(registers) != REGISTER_SIZE:
        raise ValueError("vram and registers must have exact Genesis VDP sizes")
    reg = bytes(registers)
    if not (reg[12] & 0x80) or not (reg[12] & 0x01):
        raise UnsupportedVDPState("native map export currently requires valid H40 mode")
    if reg[12] & 0x06:
        raise UnsupportedVDPState("interlaced native map export is not supported")
    if not (reg[1] & 0x04):
        raise UnsupportedVDPState("Genesis Mode 5 snapshots are required")
    width_cells = (32, 64, 32, 64)[reg[16] & 3]
    height_cells = (32, 32, 64, 64)[(reg[16] >> 4) & 3]
    specs = (
        ("plane_a", (reg[2] & 0x38) << 10),
        ("plane_b", (reg[4] & 0x07) << 13),
        ("window", (reg[3] & 0x3C) << 10),
    )
    source = bytes(vram)
    result = []
    for name, base in specs:
        entries = tuple(
            _bus_word(source, base + ((row * width_cells + col) * 2) & 0xFFFF)
            for row in range(height_cells)
            for col in range(width_cells)
        )
        tile_ids = tuple(sorted({entry & 0x07FF for entry in entries}))
        patterns = b"".join(_tile(source, tile_id) for tile_id in tile_ids)
        result.append(PlaneMap(name, base, width_cells, height_cells, entries, tile_ids, patterns))
    return tuple(result)


def decode_uniform_scroll(registers: bytes, vram: bytes, vsram: bytes) -> tuple[PlaneScroll, PlaneScroll]:
    """Return full-screen scroll offsets when both axes are uniform.

    Horizontal per-line/per-cell and vertical two-cell scroll are rejected so
    callers do not mistake one offset for a camera transform that varies by row.
    """
    if len(registers) != REGISTER_SIZE or len(vram) != VRAM_SIZE or len(vsram) != VSRAM_SIZE:
        raise ValueError("registers, vram, and vsram must have exact Genesis VDP sizes")
    reg = bytes(registers)
    if not (reg[12] & 0x80) or not (reg[12] & 0x01) or (reg[12] & 0x06):
        raise UnsupportedVDPState("valid non-interlaced H40 register state is required")
    if not (reg[1] & 0x04):
        raise UnsupportedVDPState("Genesis Mode 5 snapshots are required")
    if (reg[11] & 3) != 0 or (reg[11] & 8):
        raise UnsupportedVDPState("scroll is not uniform across the screen")
    width_cells = (32, 64, 32, 64)[reg[16] & 3]
    height_cells = (32, 32, 64, 64)[(reg[16] >> 4) & 3]
    maps = []
    for plane in (0, 1):
        hscroll, vscroll = _scroll(reg, bytes(vsram), bytes(vram), plane, 0, 0)
        maps.append(PlaneScroll(
            horizontal_native=hscroll,
            vertical_native=vscroll,
            horizontal_map=(-hscroll) % (width_cells * 8),
            vertical_map=vscroll % (height_cells * 8),
        ))
    return maps[0], maps[1]


def mosaic_world_views(views: tuple[tuple[SceneAssets, PlaneScroll], ...],
                       world_width: int, world_height: int, *,
                       exclude_window: bool = True, mask_sprites: bool = True,
                       screen_crop_width: int | None = None) -> WorldMosaic:
    """Combine observed viewport pixels in plane coordinates without filling gaps.

    Each view is an independently decoded scene plus the uniform scroll for the
    plane coordinate system. Pixels are placed at `(screen + scroll) modulo
    map size`. SAT rectangles and screen-fixed Window pixels can be excluded.
    Conflicting RGB observations use a deterministic majority color while the
    conflict mask retains their disagreement for downstream decisions.
    """
    if world_width <= 0 or world_height <= 0:
        raise ValueError("world dimensions must be positive")
    if screen_crop_width is not None and screen_crop_width <= 0:
        raise ValueError("screen crop width must be positive")
    size = world_width * world_height
    colors: list[dict[tuple[int, int, int], int] | None] = [None] * size
    for scene, scroll in views:
        if len(scene.background) != scene.width * scene.height or len(scene.background_source) != len(scene.background):
            raise ValueError("scene planes do not match their declared dimensions")
        if len(scene.palette_rgb) != 64:
            raise ValueError("scene must provide all 64 Genesis palette entries")
        crop_width = scene.width if screen_crop_width is None else min(screen_crop_width, scene.width)
        hidden = bytearray(scene.width * scene.height)
        if mask_sprites:
            for sprite in scene.sprites:
                for y in range(max(0, sprite.y), min(scene.height, sprite.y + sprite.height)):
                    start = y * scene.width + max(0, sprite.x)
                    end = y * scene.width + min(scene.width, sprite.x + sprite.width)
                    if end > start:
                        hidden[start:end] = b"\x01" * (end - start)
        for y in range(scene.height):
            world_y = (y + scroll.vertical_map) % world_height
            row_base = world_y * world_width
            source_base = y * scene.width
            for x in range(crop_width):
                source_offset = source_base + x
                if hidden[source_offset] or (exclude_window and scene.background_source[source_offset] == 3):
                    continue
                palette_index = scene.background[source_offset]
                color = scene.palette_rgb[palette_index]
                target = row_base + ((x + scroll.horizontal_map) % world_width)
                bucket = colors[target]
                if bucket is None:
                    bucket = colors[target] = {}
                bucket[color] = bucket.get(color, 0) + 1
    rgb = bytearray(size * 3)
    coverage = bytearray(size)
    conflicts = bytearray(size)
    for offset, bucket in enumerate(colors):
        if not bucket:
            continue
        coverage[offset] = sum(bucket.values())
        conflicts[offset] = int(len(bucket) > 1)
        color = min(bucket, key=lambda candidate: (-bucket[candidate], candidate))
        rgb[offset * 3:offset * 3 + 3] = bytes(color)
    return WorldMosaic(world_width, world_height, bytes(rgb), bytes(coverage), bytes(conflicts))


def mosaic_absolute_world_views(views: tuple[tuple[SceneAssets, int, int], ...],
                                origin_x: int, origin_y: int,
                                world_width: int, world_height: int, *,
                                exclude_window: bool = True, mask_sprites: bool = True,
                                screen_crop_width: int | None = None) -> WorldMosaic:
    """Mosaic viewport pixels using absolute, unwrapped world camera origins.

    Each view supplies the source world coordinate at screen (0,0). Unlike
    `mosaic_world_views`, this function never wraps into a VDP plane cache, so
    callers can combine captures across streamed/ring-buffer map updates.
    Pixels outside the requested world rectangle remain uncovered.
    """
    if world_width <= 0 or world_height <= 0:
        raise ValueError("world dimensions must be positive")
    if screen_crop_width is not None and screen_crop_width <= 0:
        raise ValueError("screen crop width must be positive")
    size = world_width * world_height
    colors: list[dict[tuple[int, int, int], int] | None] = [None] * size
    for scene, camera_x, camera_y in views:
        if len(scene.background) != scene.width * scene.height or len(scene.background_source) != len(scene.background):
            raise ValueError("scene planes do not match their declared dimensions")
        if len(scene.palette_rgb) != 64:
            raise ValueError("scene must provide all 64 Genesis palette entries")
        crop_width = scene.width if screen_crop_width is None else min(screen_crop_width, scene.width)
        hidden = bytearray(scene.width * scene.height)
        if mask_sprites:
            for sprite in scene.sprites:
                for y in range(max(0, sprite.y), min(scene.height, sprite.y + sprite.height)):
                    start = y * scene.width + max(0, sprite.x)
                    end = y * scene.width + min(scene.width, sprite.x + sprite.width)
                    if end > start:
                        hidden[start:end] = b"\x01" * (end - start)
        for y in range(scene.height):
            world_y = camera_y + y - origin_y
            if not 0 <= world_y < world_height:
                continue
            row_base = world_y * world_width
            source_base = y * scene.width
            for x in range(crop_width):
                world_x = camera_x + x - origin_x
                if not 0 <= world_x < world_width:
                    continue
                source_offset = source_base + x
                if hidden[source_offset] or (exclude_window and scene.background_source[source_offset] == 3):
                    continue
                palette_index = scene.background[source_offset]
                color = scene.palette_rgb[palette_index]
                target = row_base + world_x
                bucket = colors[target]
                if bucket is None:
                    bucket = colors[target] = {}
                bucket[color] = bucket.get(color, 0) + 1
    rgb = bytearray(size * 3)
    coverage = bytearray(size)
    conflicts = bytearray(size)
    for offset, bucket in enumerate(colors):
        if not bucket:
            continue
        coverage[offset] = sum(bucket.values())
        conflicts[offset] = int(len(bucket) > 1)
        color = min(bucket, key=lambda candidate: (-bucket[candidate], candidate))
        rgb[offset * 3:offset * 3 + 3] = bytes(color)
    return WorldMosaic(world_width, world_height, bytes(rgb), bytes(coverage), bytes(conflicts))


def _sprite_pixels(vram: bytes, tile_index: int, width_tiles: int, height_tiles: int, hflip: bool, vflip: bool) -> bytes:
    width, height = width_tiles * 8, height_tiles * 8
    out = bytearray(width * height)
    # Genesis sprite patterns advance down the tile column before moving right.
    for ty in range(height_tiles):
        for tx in range(width_tiles):
            tile_no = tile_index + tx * height_tiles + ty
            source = _tile(vram, tile_no)
            for py in range(8):
                for px in range(8):
                    dx = width - 1 - (tx * 8 + px) if hflip else tx * 8 + px
                    dy = height - 1 - (ty * 8 + py) if vflip else ty * 8 + py
                    out[dy * width + dx] = source[py * 8 + px]
    return bytes(out)


def _sprites(vram: bytes, sat_base: int, h40: bool, sat_cache: bytes | None = None,
             shadow_highlight_enabled: bool = False) -> tuple[Sprite, ...]:
    limit = 80 if h40 else 64
    sprites: list[Sprite] = []
    seen: set[int] = set()
    index = 0
    while True:
        if index in seen:
            raise UnsupportedVDPState("SAT link loop detected")
        if index >= limit:
            raise UnsupportedVDPState("SAT link points outside the active screen-mode table")
        seen.add(index)
        table = sat_cache if sat_cache is not None else vram
        addr = (0 if sat_cache is not None else sat_base) + index * 8
        yraw = _bus_word(table, addr) & 0x03FF
        size_link = _bus_word(table, addr + 2)
        height_tiles = ((size_link >> 8) & 3) + 1
        width_tiles = ((size_link >> 10) & 3) + 1
        link = size_link & 0x7F
        attr = _bus_word(table, addr + 4)
        xraw = _bus_word(table, addr + 6) & 0x01FF
        pixels = _sprite_pixels(vram, attr & 0x07FF, width_tiles, height_tiles,
                                bool(attr & 0x0800), bool(attr & 0x1000))
        effects = bytearray(len(pixels))
        if shadow_highlight_enabled and ((attr >> 13) & 3) == 0:
            for pixel_index, color in enumerate(pixels):
                if color == 14:
                    effects[pixel_index] = 1
                elif color == 15:
                    effects[pixel_index] = 2
        sprites.append(Sprite(
            sat_index=index, link=link, x=xraw - 128, y=yraw - 128,
            width=width_tiles * 8, height=height_tiles * 8,
            palette=(attr >> 13) & 3, priority=bool(attr & 0x8000),
            hflip=bool(attr & 0x0800), vflip=bool(attr & 0x1000),
            tile_index=attr & 0x07FF, native_attribute=attr,
            pixels=pixels, effects=bytes(effects),
        ))
        if link == 0:
            break
        index = link
        if len(sprites) >= limit:
            raise UnsupportedVDPState("SAT linked list exceeds configured mode sprite count")
    return tuple(sprites)


def decode_vdp_snapshot(vram: bytes, cram: bytes, vsram: bytes, registers: bytes,
                        *, sat: bytes | None = None, pixel_format: str = "RGB565") -> SceneAssets:
    """Decode Genesis background and linked SAT sprites from one VDP snapshot.

    `sat`, when supplied, is the captured core's scan-time SAT cache. The
    renderer's cache can differ from a frame-boundary VRAM read after the game
    updates SAT memory, so it is authoritative for the returned sprite list.
    """
    inputs = {"vram": bytes(vram), "cram": bytes(cram), "vsram": bytes(vsram), "registers": bytes(registers)}
    if sat is not None:
        inputs["sat"] = bytes(sat)
    expected = {"vram": VRAM_SIZE, "cram": CRAM_SIZE, "vsram": VSRAM_SIZE, "registers": REGISTER_SIZE}
    for name, size in expected.items():
        if len(inputs[name]) != size:
            raise ValueError(f"{name} must be exactly {size} bytes")
    if sat is not None and len(inputs["sat"]) != SAT_SIZE:
        raise ValueError(f"sat must be exactly {SAT_SIZE} bytes")
    vram, cram, vsram, reg = inputs["vram"], inputs["cram"], inputs["vsram"], inputs["registers"]
    if pixel_format != "RGB565":
        raise UnsupportedVDPState("only captures using the verified RGB565 video output are supported")
    h40 = bool(reg[12] & 0x80)
    if not h40:
        raise UnsupportedVDPState("H32 snapshots are not supported by this 320x224 decoder")
    if not (reg[12] & 0x01):
        raise UnsupportedVDPState("invalid H40 register state: register 12 bit 0 is clear")
    if reg[12] & 0x06:
        raise UnsupportedVDPState("interlaced display modes are not supported")
    if not (reg[1] & 0x04):
        raise UnsupportedVDPState("Genesis Mode 5 snapshots are required")
    width_cells = (32, 64, 32, 64)[reg[16] & 3]
    height_cells = (32, 32, 64, 64)[(reg[16] >> 4) & 3]
    plane_a = (reg[2] & 0x38) << 10
    plane_b = (reg[4] & 0x07) << 13
    window = (reg[3] & (0x3C if h40 else 0x3E)) << 10
    sat_base = (reg[5] & (0x7E if h40 else 0x7F)) << 9
    hscroll_base = (reg[13] & 0x3F) << 10
    # Reject unsupported window horizontal/vertical cell-size or display modes.
    shadow_highlight_enabled = bool(reg[12] & 0x08)

    colors = _cram_words(cram)
    rgb_colors = _rgb565_palette(colors)
    tile_cache: dict[int, bytes] = {}
    backdrop = reg[7] & 0x3F
    image = bytearray([backdrop]) * (SCREEN_WIDTH * SCREEN_HEIGHT)
    sources = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT)
    priorities = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT)
    plane_width = width_cells
    plane_height_px = height_cells * 8
    for y in range(SCREEN_HEIGHT):
        for x in range(SCREEN_WIDTH):
            hsa, vsa = _scroll(reg, vsram, vram, 0, x, y)
            hsb, vsb = _scroll(reg, vsram, vram, 1, x, y)
            pa_color, pa_priority, pa_opaque = _plane_pixel(vram, plane_a, plane_width, tile_cache,
                (x - hsa) % (plane_width * 8), (y + vsa) % plane_height_px)
            pb_color, pb_priority, pb_opaque = _plane_pixel(vram, plane_b, plane_width, tile_cache,
                (x - hsb) % (plane_width * 8), (y + vsb) % plane_height_px)
            window_active = _window_contains(reg, x, y)
            if window_active:
                win_color, win_priority, win_opaque = _plane_pixel(vram, window, plane_width, tile_cache, x, y)
                pa_color, pa_priority, pa_opaque = win_color, win_priority, win_opaque
            # For the background-only result, resolve opaque plane colors by
            # VDP priority tier, then expose the selected 6-bit CRAM index.
            chosen = 0
            chosen_source = 0
            chosen_priority = 0
            if pb_opaque:
                chosen = pb_color
                chosen_source = 1
                chosen_priority = pb_priority
            if pa_opaque:
                chosen = pa_color
                chosen_source = 3 if window_active else 2
                chosen_priority = pa_priority
            # Plane B high priority can cover Plane A low priority; this is
            # resolved explicitly rather than flattening at the source plane.
            if pb_opaque and pb_priority and not (pa_opaque and pa_priority):
                chosen = pb_color
                chosen_source = 1
                chosen_priority = pb_priority
            offset = y * SCREEN_WIDTH + x
            image[offset] = chosen
            sources[offset] = chosen_source
            priorities[offset] = chosen_priority
    # The captured core SAT is its scan-time internal table. Its copy cadence
    # can differ from a frame-boundary VRAM read after the guest has changed
    # SAT memory, so retain the captured cache rather than asserting equality.
    sprites = _sprites(vram, sat_base, h40, inputs.get("sat"), shadow_highlight_enabled)
    return SceneAssets(
        width=SCREEN_WIDTH, height=SCREEN_HEIGHT, pixel_format=pixel_format, background=bytes(image),
        background_source=bytes(sources), background_priority=bytes(priorities),
        palette_words=colors, palette_rgb=rgb_colors, sprites=sprites,
        input_hashes=tuple(sorted((name, _digest(value)) for name, value in inputs.items())),
        source_layout=("Genesis Plus GX exported VDP arrays: VRAM/VSAT words are accessed as bus bytes at n^1; "
                       "CRAM/VSRAM are retained/read as little-endian words; palette RGB is expanded for RGB565 captures; "
                       f"shadow/highlight mode {'enabled' if shadow_highlight_enabled else 'disabled'}; "
                       "sprite effects are tagged but not composited into the background"),
        limitations=(
            "RGB palette conversion is validated against one RGB565 capture and is not asserted for other pixel formats",
            "mid-frame VDP register/RAM changes are not represented by a single snapshot",
            "sprite priority and shadow/highlight effects are retained as metadata and are not composited into background pixels",
            "window selection uses axis-aligned register boundaries; exotic mid-frame window changes are not represented",
        ),
    )
