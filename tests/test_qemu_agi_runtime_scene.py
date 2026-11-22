"""Authored AGI v2 resources exercise the production portable native renderer.

No game files, live interpreter, QEMU binary or Python rendering implementation
is used to obtain expected pixels. Whole-plane comparisons include preserved
backgrounds and transaction failures, rather than only descriptor counts.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/qemu-agi/overlay/target/agi"
U8, U32, SZ = C.c_uint8, C.c_uint32, C.c_size_t
PTR = C.POINTER(U8)
W, H, N = 160, 168, 160 * 168
PLANE = U8 * N
ANIMATED, DRAWN, UPDATE, FIXED_PRIORITY, VIEW_BOUND = 1, 2, 4, 512, 65536


class Geometry(C.Structure):
    _fields_ = [(n, U32) for n in "loop_count cel_count width height".split()]


class ViewCel(C.Structure):
    _fields_ = [("geometry", Geometry), ("transparent", U32), ("mirrored", U32),
                ("data_offset", SZ), ("bytes_consumed", SZ)]


class PictureInfo(C.Structure):
    _fields_ = [("bytes_consumed", SZ), ("commands", U32), ("work_units", U32)]


class BlitInfo(C.Structure):
    _fields_ = [("written_pixels", U32), ("hidden", U32)]


class SceneInfo(C.Structure):
    _fields_ = [("actor_count", U32), ("written_pixels", U32),
                ("draw_order", C.c_uint16 * 256), ("hidden", U8 * 256)]


class Actor(C.Structure):
    _fields_ = (
        [(n, C.c_int32) for n in "x y prev_x prev_y target_x target_y".split()]
        + [(n, U32) for n in (
            "width height prev_width prev_height view loop cel loop_count "
            "cel_count priority flags motion cycle direction step_size step_time "
            "step_time_count cycle_time cycle_time_count motion_flag cycle_flag "
            "saved_step follow_step follow_count"
        ).split()]
    )


class World(C.Structure):
    _fields_ = [
        ("actors", Actor * 256), ("loaded_views", U8 * 256),
        ("priority_bands", U8 * H), ("horizon", U32),
        ("block_active", U32), ("player_control", U32), ("priority_base", U32),
        ("block_x1", C.c_int32), ("block_y1", C.c_int32),
        ("block_x2", C.c_int32), ("block_y2", C.c_int32),
        ("rng_state", U32), ("ticks", C.c_uint64),
    ]


VIEW_SOURCE = C.CFUNCTYPE(C.c_int, C.c_void_p, U8, C.POINTER(PTR), C.POINTER(SZ))


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("native runtime scene tests require a C compiler")
    out = tmp_path_factory.mktemp("agi_scene") / "runtime_scene.so"
    subprocess.run([
        compiler, "-std=c99", "-O2", "-pedantic", "-Wall", "-Wextra", "-Werror",
        "-shared", "-fPIC", str(SOURCE / "runtime_scene.c"), "-o", str(out),
    ], check=True, capture_output=True, text=True)
    dll = C.CDLL(str(out))
    signatures = {
        "decode_picture": [PTR, SZ, C.c_int, PTR, PTR, SZ, C.POINTER(PictureInfo)],
        "view_geometry": [PTR, SZ, U32, U32, C.POINTER(Geometry)],
        "view_cel": [PTR, SZ, U32, U32, PTR, SZ, C.POINTER(ViewCel)],
        "scene_blit": [PTR, PTR, SZ, PTR, SZ, U32, U32, U32,
                       C.c_int32, C.c_int32, U32, C.POINTER(BlitInfo)],
        "scene_compose": [C.POINTER(World), PTR, PTR, SZ, VIEW_SOURCE,
                          C.c_void_p, PTR, PTR, C.POINTER(SceneInfo)],
        "add_to_picture": [PTR, PTR, SZ, PTR, SZ, U32, U32, U32,
                           C.c_int32, C.c_int32, U32, U32, PTR, SZ,
                           C.POINTER(BlitInfo)],
    }
    for name, signature in signatures.items():
        fn = getattr(dll, f"agi_runtime_{name}")
        fn.argtypes, fn.restype = signature, C.c_int
    dll.agi_runtime_scene_error.argtypes = [C.c_int]
    dll.agi_runtime_scene_error.restype = C.c_char_p
    return dll


def buf(data):
    return (U8 * len(data)).from_buffer_copy(bytes(data))


def plane(color):
    return PLANE.from_buffer_copy(bytes([color]) * N)


def decode(lib, data, visual=None, priority=None, clear=1, result=0):
    visual = visual if visual is not None else plane(10)
    priority = priority if priority is not None else plane(11)
    info = PictureInfo()
    actual = lib.agi_runtime_decode_picture(buf(data), len(data), clear,
                                           visual, priority, N, C.byref(info))
    assert actual == result, lib.agi_runtime_scene_error(actual).decode()
    return visual, priority, info


def test_picture_lines_corners_fills_and_channel_selection(lib):
    program = bytes([
        0xF0, 2, 0xF2, 6,
        0xF5, 10, 10, 14, 14, 10, 10,  # x-corner square
        0xF0, 3, 0xF8, 11, 11,
        0xF0, 4, 0xF4, 20, 20, 24, 24, 20, 20,  # y-corner square
        0xF6, 30, 30, 34, 32,
        0xF7, 40, 40, 0x21, 0x9A,
        0xF1, 0xF6, 50, 50, 52, 50,
        0xF3, 0xF0, 7, 0xF6, 60, 60, 62, 60, 0xFF,
    ])
    visual, priority, info = decode(lib, program)
    ev, ep = bytearray([15]) * N, bytearray([4]) * N
    for y in range(10, 15):
        for x in range(10, 15):
            ev[y * W + x] = 2 if x in (10, 14) or y in (10, 14) else 3
            ep[y * W + x] = 6
    points = {(x, y) for x in range(20, 25) for y in range(20, 25)
              if x in (20, 24) or y in (20, 24)}
    points |= {(30, 30), (31, 31), (32, 31), (33, 32), (34, 32)}
    points |= {(40, 40), (41, 41), (42, 41), (41, 40), (41, 39)}
    for x, y in points:
        ev[y * W + x], ep[y * W + x] = 4, 6
    for x in range(50, 53):
        ep[50 * W + x] = 6
    for x in range(60, 63):
        ev[60 * W + x] = 7
    assert bytes(visual) == ev
    assert bytes(priority) == ep
    assert info.bytes_consumed == len(program) and info.commands == 15
    assert len(program) < info.work_units < 1000


def test_picture_overlay_executes_fill_against_previous_image(lib):
    base = bytes([0xF0, 0, 0xF6, 10, 10, 14, 10, 14, 14, 10, 14, 10, 10,
                  0xF0, 2, 0xF8, 11, 11, 0xFF])
    visual, priority, _ = decode(lib, base)
    original = bytes(visual)
    # The enclosed region is already color2, so this fill must do nothing.
    decode(lib, bytes([0xF0, 5, 0xF8, 11, 11, 0xFF]), visual, priority, clear=0)
    assert bytes(visual) == original
    # Filling the white exterior preserves both the old boundary and interior.
    decode(lib, bytes([0xF0, 5, 0xF8, 0, 0, 0xFF]), visual, priority, clear=0)
    assert bytes(visual) == bytes(5 if c == 15 else c for c in original)
    assert bytes(priority) == bytes([4]) * N


def test_picture_fill_plane_rules_end_marker_and_nibble_colors(lib):
    v, p, _ = decode(lib, bytes([0xF2, 0xA9, 0xF8, 0, 0, 0xFF]))
    assert bytes(v) == bytes([15]) * N and bytes(p) == bytes([9]) * N
    # With both channels on, visual white determines the flood region.
    decode(lib, bytes([0xF0, 3, 0xF2, 7, 0xF8, 0, 0, 0xFF]), v, p, clear=0)
    assert bytes(v) == bytes([3]) * N and bytes(p) == bytes([7]) * N
    v, p, info = decode(lib, bytes([0xF0, 15, 0xF2, 8, 0xF8, 0, 0, 0xFF, 0xFB]))
    assert bytes(v) == bytes([15]) * N and bytes(p) == bytes([4]) * N
    assert info.bytes_consumed == 8


@pytest.mark.parametrize("pattern,expected", [
    (0, {(30, 30)}),
    (2, {(30, 28), (29, 29), (30, 29), (31, 29),
         (29, 30), (30, 30), (31, 30), (29, 31), (30, 31), (31, 31), (30, 32)}),
    (0x12, {(x, y) for x in range(29, 32) for y in range(28, 33)}),
    # Seed0 consumes splatter-map bits0..14 in a 3x5 rectangular brush.
    (0x32, {(31, 28), (31, 30), (31, 31), (30, 32)}),
])
def test_picture_pen_and_splatter_pixels(lib, pattern, expected):
    args = [0] if pattern & 0x20 else []
    v, p, _ = decode(lib, bytes([0xF0, 6, 0xF9, pattern, 0xFA, *args, 30, 30, 0xFF]))
    assert {(i % W, i // W) for i, c in enumerate(v) if c != 15} == expected
    assert all(v[y * W + x] == 6 for x, y in expected)
    assert bytes(p) == bytes([4]) * N


@pytest.mark.parametrize("bad", [b"", b"\xFB\xFF", b"\x00\xFF", b"\xF0",
                                   b"\xF6\x01\xFF", b"\xF8\x01\xFF",
                                   b"\xF9\x20\xFA\x00\xFF"])
def test_picture_invalid_streams_preserve_planes_and_receipt(lib, bad):
    v, p = plane(2), plane(9)
    info = PictureInfo()
    C.memset(C.byref(info), 0xA5, C.sizeof(info))
    before = bytes(v), bytes(p), bytes(info)
    assert lib.agi_runtime_decode_picture(buf(bad), len(bad), 1, v, p, N, C.byref(info)) < 0
    assert (bytes(v), bytes(p), bytes(info)) == before


def test_picture_every_truncated_prefix_is_atomic(lib):
    program = bytes([0xF0, 3, 0xF2, 6, 0xF6, 3, 4, 8, 9,
                     0xF9, 0x31, 0xFA, 10, 22, 23, 0xFF])
    for stop in range(len(program)):
        v, p = plane(2), plane(9)
        assert lib.agi_runtime_decode_picture(buf(program[:stop]), stop, 0, v, p, N, None) < 0
        assert bytes(v) == bytes([2]) * N and bytes(p) == bytes([9]) * N


def test_picture_work_limit_does_not_commit_a_partly_replayed_overlay(lib):
    # Repaint the whole canvas white, then fill it again. The finite byte
    # stream is modest, but its repeated flood work exceeds the native cap.
    repaint = bytearray([0xF0, 15, 0xF6, 0, 0, 159, 0])
    right = True
    for y in range(1, H):
        repaint.extend([159 if right else 0, y, 0 if right else 159, y])
        right = not right
    repaint.extend([0xF0, 3, 0xF8, 0, 0])
    program = bytes(repaint) * 200 + b"\xFF"
    v, p, info = plane(2), plane(9), PictureInfo(99, 88, 77)
    before = bytes(v), bytes(p), bytes(info)
    assert lib.agi_runtime_decode_picture(buf(program), len(program), 0, v, p, N, C.byref(info)) == -5
    assert (bytes(v), bytes(p), bytes(info)) == before


def view(width=3, height=2, color=1, transparent=15):
    runs = bytearray()
    for _ in range(height):
        remaining = width
        while remaining:
            n = min(15, remaining)
            runs.append((color << 4) | n)
            remaining -= n
        runs.append(0)
    return bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0,
                  width, height, transparent]) + runs


def mirrored_view():
    # Two distinct loop directories share one cel, whose original loop is0.
    return bytes([0, 0, 2, 0, 0, 9, 0, 12, 0, 1, 6, 0, 1, 3, 0,
                  3, 2, 0x8F, 0x11, 0x21, 0, 0x31, 0x41, 0x51, 0])


def test_view_offsets_geometry_short_rows_and_mirror_once(lib):
    raw = buf(mirrored_view())
    for loop, expected in [(0, [1, 2, 15, 3, 4, 5]), (1, [15, 2, 1, 5, 4, 3])]:
        pixels = buf([0xA5] * 9)
        info = ViewCel()
        assert lib.agi_runtime_view_cel(raw, len(raw), loop, 0, pixels, len(pixels), C.byref(info)) == 0
        assert list(pixels) == expected + [0xA5] * 3
        assert (info.geometry.loop_count, info.geometry.cel_count,
                info.geometry.width, info.geometry.height) == (2, 1, 3, 2)
        assert (info.transparent, info.mirrored, info.data_offset, info.bytes_consumed) == (15, loop, 18, 10)
    for loop, cel, counts in [(2, 0, (2, 0, 0, 0)), (1, 1, (2, 1, 0, 0))]:
        g = Geometry()
        assert lib.agi_runtime_view_geometry(raw, len(raw), loop, cel, C.byref(g)) == 0
        assert tuple(getattr(g, n) for n, _ in g._fields_) == counts


@pytest.mark.parametrize("bad", [
    b"", bytes([0, 0, 0, 0, 0]),
    bytes([0, 0, 1, 0, 0, 0, 0]),  # loop in resource header
    bytes([0, 0, 1, 0, 0, 7, 0, 1, 1, 0]),  # cel in loop table
    view()[:-1],  # missing final row terminator
    view()[:13] + bytes([0x10, 0, 0]),  # zero-length nonzero run
    view()[:13] + bytes([0x14, 0, 0]),  # run longer than row
    view()[:10] + bytes([0, 2, 15, 0, 0]),
])
def test_view_rejects_malformed_resources_without_partial_outputs(lib, bad):
    pixels, info, g = buf([0xA5] * 32), ViewCel(), Geometry()
    C.memset(C.byref(info), 0xA5, C.sizeof(info))
    C.memset(C.byref(g), 0xA5, C.sizeof(g))
    before = bytes(pixels), bytes(info), bytes(g)
    assert lib.agi_runtime_view_cel(buf(bad), len(bad), 0, 0, pixels, len(pixels), C.byref(info)) < 0
    assert lib.agi_runtime_view_geometry(buf(bad), len(bad), 0, 0, C.byref(g)) < 0
    assert (bytes(pixels), bytes(info), bytes(g)) == before


def test_view_validates_structural_boundaries_and_output_capacity(lib):
    raw = bytearray(mirrored_view())
    raw[3:5] = (24).to_bytes(2, "little")  # description begins before last row terminator
    assert lib.agi_runtime_view_cel(buf(raw), len(raw), 0, 0, buf([0] * 6), 6, None) < 0
    original = view()
    pixels = buf([0xA5] * 5)
    assert lib.agi_runtime_view_cel(buf(original), len(original), 0, 0, pixels, 5, None) == -1
    assert list(pixels) == [0xA5] * 5


def test_view_maximum_cel_geometry_uses_only_declared_output(lib):
    data, pixels, info = buf(view(W, H, 6)), buf([0xA5] * (N + 4)), ViewCel()
    assert lib.agi_runtime_view_cel(data, len(data), 0, 0, pixels, N, C.byref(info)) == 0
    assert bytes(pixels[:N]) == bytes([6]) * N and list(pixels[N:]) == [0xA5] * 4
    assert (info.geometry.width, info.geometry.height) == (W, H)


def test_blit_transparency_water_control_readthrough_and_bottom_fallback(lib):
    v, p = plane(15), plane(4)
    # A control line reads down to9: priority8 cannot pass until column12,
    # whose water3 is replaced. Transparent pixel13 never writes either plane.
    p[20 * W + 10] = 1
    p[21 * W + 10] = 2
    p[22 * W + 10] = 9
    p[20 * W + 11] = 9
    p[20 * W + 12] = 3
    pixels, info = buf([2, 3, 4, 15]), BlitInfo()
    assert lib.agi_runtime_scene_blit(v, p, N, pixels, 4, 4, 1, 15, 10, 20, 8, C.byref(info)) == 0
    assert (info.written_pixels, info.hidden) == (1, 0)
    assert list(v[20 * W + 10:20 * W + 14]) == [15, 15, 4, 15]
    assert list(p[20 * W + 10:20 * W + 14]) == [1, 9, 8, 4]
    assert lib.agi_runtime_scene_blit(v, p, N, pixels, 4, 4, 1, 15, 10, 20, 9, C.byref(info)) == 0
    assert (info.written_pixels, info.hidden) == (3, 0)
    assert p[20 * W + 10] == 1
    p[167 * W + 2] = 0
    assert lib.agi_runtime_scene_blit(v, p, N, buf([6]), 1, 1, 1, 15, 2, 167, 4, C.byref(info)) == 0
    assert v[167 * W + 2] == 6 and p[167 * W + 2] == 0


@pytest.mark.parametrize("change", ["palette", "position", "overlap"])
def test_blit_validation_is_atomic(lib, change):
    v, p, pixels, info = plane(15), plane(4), buf([6, 7]), BlitInfo(33, 44)
    x = 159 if change == "position" else 0
    if change == "palette":
        pixels[1] = 16
    out_priority = v if change == "overlap" else p
    before = bytes(v), bytes(p), bytes(info)
    assert lib.agi_runtime_scene_blit(v, out_priority, N, pixels, 2, 2, 1, 15, x, 10, 8, C.byref(info)) < 0
    assert (bytes(v), bytes(p), bytes(info)) == before


class Scene:
    def __init__(self, lib):
        self.lib, self.world = lib, World()
        self.background, self.priority = plane(15), plane(4)
        self.visual, self.composed_priority, self.info = plane(1), plane(2), SceneInfo()
        self.bank = {}
        for y in range(H):
            self.world.priority_bands[y] = max(4, y // 12 + 1)

        @VIEW_SOURCE
        def source(_, ident, data, length):
            raw = self.bank.get(ident)
            if raw is None:
                return 0
            data[0], length[0] = C.cast(raw, PTR), len(raw)
            return 1

        self.source = source

    def actor(self, ident, color, x=30, y=80, priority=8, updating=True, fixed=False):
        self.bank[ident] = buf(view(3, 2, color))
        self.world.loaded_views[ident] = 1
        a = self.world.actors[ident]
        a.x, a.y, a.width, a.height = x, y, 3, 2
        a.view, a.loop_count, a.cel_count, a.priority = ident, 1, 1, priority
        a.flags = ANIMATED | DRAWN | VIEW_BOUND | (UPDATE if updating else 0) | (FIXED_PRIORITY if fixed else 0)
        return a

    def compose(self, expected=0, in_place=False):
        v, p = ((self.background, self.priority) if in_place
                else (self.visual, self.composed_priority))
        actual = self.lib.agi_runtime_scene_compose(
            C.byref(self.world), self.background, self.priority, N,
            self.source, None, v, p, C.byref(self.info))
        assert actual == expected, self.lib.agi_runtime_scene_error(actual).decode()
        return v, p


def test_compose_stationary_updating_priority_and_stable_actor_order(lib):
    s = Scene(lib)
    s.actor(20, 2, updating=False)
    s.actor(1, 3)
    s.actor(2, 6)
    s.compose()
    assert s.info.actor_count == 3
    assert list(s.info.draw_order[:3]) == [20, 1, 2]
    assert s.visual[80 * W + 30] == 6 and s.info.written_pixels == 18
    # Fixed priority9 has sort-row95, regardless of actual baseline.
    a = s.actor(3, 5, y=80, priority=9, fixed=True)
    s.compose()
    assert list(s.info.draw_order[:4]) == [20, 1, 2, 3]
    assert s.visual[80 * W + 30] == 5
    a.priority = 7
    s.compose()
    assert list(s.info.draw_order[:4]) == [20, 3, 1, 2]
    assert s.info.hidden[3] == 1 and s.visual[80 * W + 30] == 6


def test_compose_reconstructs_after_move_erase_and_discard(lib):
    s = Scene(lib)
    a = s.actor(1, 3)
    s.compose()
    assert s.visual[80 * W + 30] == 3
    a.x = 40
    s.compose()
    assert s.visual[80 * W + 30] == 15 and s.visual[80 * W + 40] == 3
    a.flags &= ~DRAWN
    s.compose()
    assert bytes(s.visual) == bytes(s.background) and s.info.actor_count == 0
    a.flags |= DRAWN
    s.world.loaded_views[1] = 0
    s.compose()
    assert bytes(s.visual) == bytes(s.background) and s.info.actor_count == 0
    s.world.loaded_views[1] = 1
    before_world = bytes(s.world)
    s.compose(in_place=True)
    assert s.background[80 * W + 40] == 3 and bytes(s.world) == before_world


def test_compose_failure_after_first_actor_commits_nothing(lib):
    s = Scene(lib)
    s.actor(1, 3)
    s.actor(2, 5)
    s.bank.pop(2)
    before = bytes(s.visual), bytes(s.composed_priority), bytes(s.info), bytes(s.world)
    s.compose(-8)
    assert (bytes(s.visual), bytes(s.composed_priority), bytes(s.info), bytes(s.world)) == before
    s.bank[2] = buf(view(4, 2, 5))  # stale authoritative geometry
    s.compose(-9)
    assert (bytes(s.visual), bytes(s.composed_priority), bytes(s.info), bytes(s.world)) == before


def test_compose_all_actor_slots_and_source_alias_rejection(lib):
    s = Scene(lib)
    for ident in range(256):
        s.actor(ident, ident % 14 + 1)
    s.compose()
    assert s.info.actor_count == 256 and list(s.info.draw_order) == list(range(256))
    assert s.visual[80 * W + 30] == 255 % 14 + 1
    raw = view(3, 2, 6)
    for i, value in enumerate(raw):
        s.visual[i] = value
    s.bank[0] = (U8 * len(raw)).from_buffer(s.visual)
    before = bytes(s.visual), bytes(s.composed_priority), bytes(s.info)
    s.compose(-1)
    assert (bytes(s.visual), bytes(s.composed_priority), bytes(s.info)) == before


def test_add_to_picture_persists_pixels_and_control_margin(lib):
    s = Scene(lib)
    pixels, info = buf([6] * 6), BlitInfo()
    s.priority[73 * W + 30] = 1
    assert lib.agi_runtime_add_to_picture(
        s.background, s.priority, N, pixels, 6, 3, 2, 15,
        30, 80, 0, 2, s.world.priority_bands, H, C.byref(info)) == 0
    assert (info.written_pixels, info.hidden) == (6, 0)
    assert list(s.background[80 * W + 30:80 * W + 33]) == [6] * 3
    assert s.priority[79 * W + 31] == 7  # auto priority from baseline80
    assert s.priority[73 * W + 30] == 1  # preexisting control survives
    assert s.priority[73 * W + 31] == 2
    assert s.priority[80 * W + 31] == 2
    assert s.priority[76 * W + 30] == s.priority[76 * W + 32] == 2
    s.actor(1, 3, x=30, y=80)
    s.compose()
    s.world.actors[1].flags &= ~DRAWN
    s.compose()
    assert bytes(s.visual) == bytes(s.background)
    assert bytes(s.composed_priority) == bytes(s.priority)


def test_add_to_picture_clips_edges_and_rejects_bad_arguments_atomically(lib):
    s = Scene(lib)
    pixels, info = buf([1, 2, 3, 4, 5, 6]), BlitInfo()
    assert lib.agi_runtime_add_to_picture(
        s.background, s.priority, N, pixels, 6, 3, 2, 15,
        159, 0, 8, 4, s.world.priority_bands, H, C.byref(info)) == 0
    assert (info.written_pixels, info.hidden) == (2, 0)
    assert s.background[159] == 1 and s.background[W + 159] == 4
    assert s.background[W] == 15  # no row wrapping
    before = bytes(s.background), bytes(s.priority), bytes(info)
    s.world.priority_bands[10] = 16
    assert lib.agi_runtime_add_to_picture(
        s.background, s.priority, N, pixels, 6, 3, 2, 15,
        20, 80, 8, 2, s.world.priority_bands, H, C.byref(info)) == -10
    assert (bytes(s.background), bytes(s.priority), bytes(info)) == before
