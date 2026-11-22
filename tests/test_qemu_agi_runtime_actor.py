"""Portable native actor execution with authored, asset-free views and planes.

These tests compile the production C module itself. No QEMU, installed game,
Python semantic interpreter or renderer is used to derive the expectations.
"""
import ctypes as C
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/qemu-agi/overlay/target/agi"
U8 = C.c_uint8
U32 = C.c_uint32
BYTE_ARRAY = U8 * 256
PLANE = U8 * (160 * 168)

ANIMATED, DRAWN, UPDATE, CYCLING = 1, 2, 4, 8
IGNORE_HORIZON, IGNORE_OBJECTS, IGNORE_BLOCKS = 16, 32, 64
WATER, LAND, FIXED_PRIORITY, FIXED_LOOP = 128, 256, 512, 1024
UPDATE_POSITION, VIEW_REPLACED, DONT_UPDATE = 2048, 4096, 8192
DIDNT_MOVE, MOTION_ACTIVE, VIEW_BOUND, BLOCKED = 16384, 32768, 65536, 131072


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
        ("actors", Actor * 256), ("loaded_views", BYTE_ARRAY),
        ("priority_bands", U8 * 168), ("horizon", U32),
        ("block_active", U32), ("player_control", U32), ("priority_base", U32),
        ("block_x1", C.c_int32), ("block_y1", C.c_int32),
        ("block_x2", C.c_int32), ("block_y2", C.c_int32),
        ("rng_state", U32), ("ticks", C.c_uint64),
    ]


class Geometry(C.Structure):
    _fields_ = [(n, U32) for n in "loop_count cel_count width height".split()]


GEOMETRY_FN = C.CFUNCTYPE(C.c_int, C.c_void_p, U8, U8, U8, C.POINTER(Geometry))
RANDOM_FN = C.CFUNCTYPE(U32, C.c_void_p, C.POINTER(U32), U32)


class Callbacks(C.Structure):
    _fields_ = [("opaque", C.c_void_p), ("geometry", GEOMETRY_FN),
                ("priority", C.POINTER(U8)), ("priority_size", C.c_size_t),
                ("random", RANDOM_FN)]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("portable native actor verification requires a C compiler")
    out = tmp_path_factory.mktemp("agi_actor") / "runtime_actor.so"
    subprocess.run([
        compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-fPIC", "-shared", str(SOURCE / "runtime_actor.c"), "-o", str(out),
    ], check=True, capture_output=True, text=True)
    dll = C.CDLL(str(out))
    state_args = [C.POINTER(World), C.POINTER(U8), C.POINTER(U8),
                  C.POINTER(Callbacks)]
    dll.agi_runtime_world_init.argtypes = [C.POINTER(World)]
    dll.agi_runtime_world_init.restype = None
    dll.agi_runtime_actor_command.argtypes = [
        C.POINTER(World), U32, C.POINTER(U8), C.c_size_t,
        C.POINTER(U8), C.POINTER(U8), C.POINTER(Callbacks),
    ]
    dll.agi_runtime_actor_command.restype = C.c_int
    dll.agi_runtime_actor_tick.argtypes = [C.POINTER(World), U32, *state_args[1:]]
    dll.agi_runtime_actor_tick.restype = C.c_int
    for name in ("prepare", "finish"):
        fn = getattr(dll, f"agi_runtime_actor_{name}")
        fn.argtypes = state_args
        fn.restype = C.c_int
    dll.agi_runtime_actor_error.argtypes = [C.c_int]
    dll.agi_runtime_actor_error.restype = C.c_char_p
    return dll


class Machine:
    def __init__(self, lib):
        self.lib = lib
        self.world = World()
        self.vars, self.flags = BYTE_ARRAY(), BYTE_ARRAY()
        self.plane = PLANE(*([4] * (160 * 168)))
        # Deliberately nonuniform dimensions exercise loop/cel rebinding.
        self.views = {
            1: [[(4, 4), (5, 5), (6, 6)] for _ in range(4)],
            2: [[(2, 2)]],
            3: [[(8, 8)], [(3, 3), (4, 4)]],
        }

        @GEOMETRY_FN
        def geometry(_, view, loop, cel, out):
            loops = self.views.get(view)
            if loops is None:
                return 0
            out[0].loop_count = len(loops)
            if loop < len(loops):
                out[0].cel_count = len(loops[loop])
                if cel < len(loops[loop]):
                    out[0].width, out[0].height = loops[loop][cel]
            return 1

        @RANDOM_FN
        def random(_, state, upper):
            # Reproducible state-only callback: no hidden cursor or host RNG.
            state[0] = (state[0] * 1664525 + 1013904223) & 0xFFFFFFFF
            return state[0] % upper

        self.geometry, self.random = geometry, random
        self.callbacks = Callbacks(None, geometry, self.plane, len(self.plane), random)
        lib.agi_runtime_world_init(C.byref(self.world))
        for view in self.views:
            self.world.loaded_views[view] = 1

    def command(self, opcode, *args, result=1):
        data = (U8 * len(args))(*args)
        actual = self.lib.agi_runtime_actor_command(
            C.byref(self.world), opcode, data, len(args), self.vars, self.flags,
            C.byref(self.callbacks),
        )
        assert actual == result, self.lib.agi_runtime_actor_error(actual).decode()
        return actual

    def tick(self, count=1, result=1):
        actual = self.lib.agi_runtime_actor_tick(
            C.byref(self.world), count, self.vars, self.flags, C.byref(self.callbacks),
        )
        assert actual == result, self.lib.agi_runtime_actor_error(actual).decode()

    def phase(self, name, result=1):
        actual = getattr(self.lib, f"agi_runtime_actor_{name}")(
            C.byref(self.world), self.vars, self.flags, C.byref(self.callbacks),
        )
        assert actual == result, self.lib.agi_runtime_actor_error(actual).decode()

    def actor(self, ident=1, x=30, y=80, view=1, cycling=False):
        self.command(33, ident)
        self.command(37, ident, x, y)
        self.command(41, ident, view)
        self.command(35, ident)
        if not cycling:
            self.command(70, ident)
        return self.world.actors[ident]

    def snapshot(self):
        return bytes(self.world), bytes(self.vars), bytes(self.flags)


@pytest.fixture
def m(lib):
    return Machine(lib)


def test_initial_bands_full_actor_range_and_atomic_argument_errors(m):
    assert m.world.horizon == 36 and m.world.player_control == 1
    assert list(m.world.priority_bands[:49]) == [4] * 48 + [5]
    assert list(m.world.priority_bands[156:]) == [14] * 12
    a = m.actor(255)
    assert a.flags & (ANIMATED | DRAWN | UPDATE) == ANIMATED | DRAWN | UPDATE
    assert a.step_size == a.step_time == a.cycle_time == 1
    for opcode, args, error in [(33, (), -1), (34, (1,), -1), (35, (1, 2), -1),
                                (92, (1,), 0), (146, (), 0), (256, (), 0)]:
        before = m.snapshot()
        m.command(opcode, *args, result=error)
        assert m.snapshot() == before
    before = m.snapshot()
    m.tick(4097, result=-14)
    assert m.snapshot() == before
    m.tick(0)
    assert m.snapshot() == before


def test_view_binding_fallback_and_top_edge_horizon_distinction(m):
    a = m.world.actors[1]
    m.command(37, 1, 159, 20)
    m.command(41, 1, 1)
    assert (a.x, a.y, a.prev_x, a.prev_y) == (156, 20, 159, 20)
    assert a.flags & UPDATE_POSITION
    m.command(43, 1, 3)
    m.command(47, 1, 2)
    m.command(41, 1, 2)
    assert (a.loop, a.cel, a.width, a.height) == (0, 0, 2, 2)
    m.command(37, 1, 12, 1)
    m.command(41, 1, 1)
    assert (a.y, a.prev_y) == (37, 1)
    m.command(61, 1)
    m.command(37, 1, 12, 1)
    m.command(47, 1, 2)
    assert a.y == 5
    m.command(62, 1)
    assert not a.flags & IGNORE_HORIZON


def test_geometry_faults_are_precise_and_atomic(m):
    a = m.actor()
    cases = [(41, (1, 250), -2), (43, (1, 4), -5), (47, (1, 3), -6),
             (43, (2, 0), -4), (49, (2, 100), -4)]
    for op, args, fault in cases:
        before = m.snapshot()
        m.command(op, *args, result=fault)
        assert m.snapshot() == before
    m.world.loaded_views[3] = 0
    before = m.snapshot()
    m.command(41, 1, 3, result=-3)
    assert m.snapshot() == before
    m.views[2] = [[]]
    before = m.snapshot()
    m.command(41, 1, 2, result=-7)
    assert m.snapshot() == before
    m.views[2] = [[(161, 1)]]
    before = m.snapshot()
    m.command(41, 1, 2, result=-8)
    assert m.snapshot() == before
    assert (a.view, a.loop, a.cel) == (1, 0, 0)


def test_variable_bindings_getters_priority_and_position(m):
    a = m.actor(1)
    m.vars[20:26] = (1, 2, 2, 9, 60, 90)
    m.command(42, 1, 20)
    m.command(44, 1, 21)
    m.command(48, 1, 22)
    for op, expected in [(49, 2), (50, 2), (51, 2), (52, 1), (53, 4)]:
        m.command(op, 1, 100)
        assert m.vars[100] == expected
    m.command(55, 1, 23)
    m.command(57, 1, 100)
    assert m.vars[100] == 9 and a.flags & FIXED_PRIORITY
    m.command(56, 1)
    m.command(38, 1, 24, 25)
    m.command(39, 1, 101, 102)
    assert (m.vars[101], m.vars[102], a.prev_x, a.prev_y) == (60, 90, 60, 90)
    m.vars[30], m.vars[31] = 255, 254
    m.command(40, 1, 30, 31)
    assert (a.x, a.y, a.prev_x, a.prev_y) == (59, 88, 60, 90)
    assert a.flags & UPDATE_POSITION
    m.command(147, 1, 20, 70)
    assert (a.x, a.y) == (20, 70)
    m.command(148, 1, 24, 25)
    assert (a.x, a.y) == (60, 90)
    m.vars[30], m.vars[31] = 128, 128
    m.command(40, 1, 30, 31)
    assert (a.x, a.y) == (0, 37)
    m.command(63, 42)
    assert m.world.horizon == 42


def test_draw_erase_unanimate_and_reanimation(m):
    m.command(33, 1)
    before = m.snapshot()
    m.command(35, 1, result=-4)
    assert m.snapshot() == before
    m.command(37, 1, 20, 20)
    m.command(41, 1, 1)
    m.command(35, 1)
    a = m.world.actors[1]
    assert (a.y, a.prev_y) == (37, 37)
    assert a.flags & DRAWN
    m.command(35, 1)
    m.command(36, 1)
    assert not a.flags & DRAWN
    m.command(35, 1)
    m.command(34)
    assert not a.flags & (ANIMATED | DRAWN)
    m.command(33, 1)
    assert a.flags == VIEW_BOUND | ANIMATED | UPDATE | CYCLING
    m.command(35, 1)
    assert a.flags & DRAWN


def test_control_plane_spiral_is_west_first_and_failure_is_finite(m):
    m.command(33, 1)
    m.command(37, 1, 20, 80)
    m.command(41, 1, 2)
    m.plane[80 * 160 + 21] = 0
    m.command(35, 1)
    assert (m.world.actors[1].x, m.world.actors[1].y) == (19, 80)
    m.plane[:] = [0] * len(m.plane)
    before = m.snapshot()
    m.command(147, 1, 20, 80, result=-11)
    assert m.snapshot() == before
    m.command(54, 1, 15)
    m.command(147, 1, 20, 80)
    assert (m.world.actors[1].x, m.world.actors[1].y) == (20, 80)


def test_missing_invalid_plane_and_bad_priority_do_not_commit(m):
    a = m.actor()
    for size, index, error in [(1, None, -10), (160 * 168, 0, -10)]:
        m.callbacks.priority_size = size
        if index is not None:
            m.plane[index] = 16
        before = m.snapshot()
        m.tick(result=error)
        assert m.snapshot() == before
        m.plane[0] = 4
    m.callbacks.priority = C.POINTER(U8)()
    before = m.snapshot()
    m.tick(result=-9)
    assert m.snapshot() == before
    before = m.snapshot()
    m.command(54, 1, 16, result=-1)
    assert m.snapshot() == before and a.priority <= 15


def test_ego_water_trigger_and_dynamic_priority(m):
    a = m.actor(0, view=2)
    m.plane[80 * 160 + 30] = 3
    m.plane[80 * 160 + 31] = 3
    m.command(64, 0)
    m.tick()
    assert m.flags[0] == 1 and m.flags[3] == 0
    assert a.priority == 7 and not a.flags & (WATER | LAND)
    m.plane[80 * 160 + 30] = 2
    m.tick()
    assert m.flags[0] == 0 and m.flags[3] == 1
    m.command(54, 0, 15)
    m.tick()
    assert (m.flags[0], m.flags[3]) == (0, 0)
    m.command(56, 0)
    m.command(37, 0, 30, 120)
    m.tick()
    assert a.priority == 11


def test_land_water_and_conditional_control_constraints(m):
    a = m.actor(1, view=2)
    m.plane[:] = [3] * len(m.plane)
    m.command(65, 1)
    before = m.snapshot()
    m.command(147, 1, 30, 80, result=-11)
    assert m.snapshot() == before
    m.command(66, 1)
    m.command(64, 1)
    m.command(147, 1, 30, 80)
    assert a.flags & WATER
    m.plane[:] = [1] * len(m.plane)
    m.command(66, 1)
    before = m.snapshot()
    m.command(147, 1, 30, 80, result=-11)
    assert m.snapshot() == before
    m.command(88, 1)
    m.command(147, 1, 30, 80)
    m.command(89, 1)
    assert not a.flags & IGNORE_BLOCKS


def test_actor_collision_touching_endpoints_ignore_and_crossed_baselines(m):
    a = m.actor(1, x=30, y=80, view=2)
    b = m.actor(2, x=33, y=80, view=2)
    m.vars[20] = 3
    m.command(86, 1, 20)
    m.tick()
    assert a.x == 30 and a.flags & DIDNT_MOVE
    m.command(67, 2)
    m.tick()
    assert a.x == 31
    m.command(68, 2)
    m.command(37, 1, 30, 79)
    m.command(37, 2, 30, 80)
    m.vars[20], m.vars[21] = 5, 2
    m.command(86, 1, 20)
    m.command(79, 1, 21)
    m.tick()
    assert a.y == 79 and b.y == 80


def test_cycle_modes_completion_skip_and_timer(m):
    a = m.actor(1, cycling=True)
    m.command(45, 1)
    m.command(73, 1, 30)
    assert not m.flags[30] and a.flags & DONT_UPDATE
    m.tick()
    assert a.cel == 0 and not a.flags & DONT_UPDATE
    m.tick()
    assert a.cel == 1 and not m.flags[30]
    m.tick()
    assert a.cel == 2 and m.flags[30] and not a.flags & CYCLING
    m.command(75, 1, 31)
    m.command(47, 1, 2)  # explicit cel cancels the initial skip
    m.tick(2)
    assert a.cel == 0 and m.flags[31] and not a.flags & CYCLING
    m.command(74, 1)
    m.tick()
    assert a.cel == 2
    m.command(72, 1)
    m.tick()
    assert a.cel == 0
    m.vars[20] = 2
    m.command(76, 1, 20)
    m.tick()
    assert a.cel == 0 and a.cycle_time_count == 1
    m.tick()
    assert a.cel == 1 and a.cycle_time_count == 2
    m.vars[20] = 0
    m.command(76, 1, 20)
    m.tick(3)
    assert a.cel == 1
    m.command(70, 1)
    m.command(71, 1)
    assert a.flags & CYCLING


def test_automatic_loop_selection_and_update_step_gates(m):
    a = m.actor()
    m.vars[20], m.vars[21] = 1, 2
    m.command(86, 1, 20)
    m.command(80, 1, 21)
    m.tick()
    assert (a.y, a.loop, a.step_time_count) == (80, 0, 1)
    m.tick()
    assert (a.y, a.loop, a.step_time_count) == (79, 3, 2)
    m.command(45, 1)
    m.vars[20] = 5
    m.command(86, 1, 20)
    m.tick(2)
    assert a.loop == 3
    m.command(46, 1)
    m.tick(2)
    assert a.loop == 2
    m.command(58, 1)
    old = (a.x, a.y, a.step_time_count)
    m.tick(3)
    assert (a.x, a.y, a.step_time_count) == old
    m.command(59, 1)
    m.tick(2)
    assert a.y == old[1] + 1


def test_move_literal_variable_completion_saved_step_and_control(m):
    a = m.actor(0, x=20, y=80, view=2)
    m.vars[20] = 3
    m.command(79, 0, 20)
    m.command(81, 0, 24, 80, 2, 40)
    assert (a.step_size, a.saved_step, m.world.player_control, m.vars[6]) == (2, 3, 0, 3)
    m.tick(2)
    assert a.x == 24 and not m.flags[40]
    m.phase("prepare")
    assert m.flags[40] and a.motion == 0 and a.step_size == 3
    assert m.world.player_control == 1 and a.direction == 0
    m.phase("finish")
    m.vars[21:24] = (27, 80, 1)
    m.command(82, 0, 21, 22, 23, 41)
    m.tick(4)
    assert a.x == 27 and m.flags[41] and a.step_size == 3
    m.command(77, 0)
    assert not m.world.player_control and a.direction == 0
    m.command(78, 0)
    assert m.world.player_control and m.vars[6] == 0
    m.command(85, 0)
    assert a.motion == 0


@pytest.mark.parametrize("direction,x,y,expected,border", [
    (7, 0, 80, (0, 80), 4), (3, 158, 80, (158, 80), 2),
    (1, 40, 37, (40, 37), 1), (5, 40, 167, (40, 167), 3),
])
def test_edge_variables_for_non_ego_actor(m, direction, x, y, expected, border):
    a = m.actor(255, x=x, y=y, view=2)
    m.vars[20] = direction
    m.command(86, 255, 20)
    m.tick()
    assert (a.x, a.y) == expected
    assert (m.vars[4], m.vars[5]) == (255, border)
    assert m.vars[2] == 0


def test_move_to_offscreen_completes_at_border(m):
    a = m.actor(0, x=157, y=80, view=2)
    m.command(81, 0, 250, 80, 2, 50)
    m.tick()
    assert a.x == 158 and m.vars[2] == 2 and m.flags[50]
    assert a.motion == 0 and a.step_size == 1 and m.world.player_control == 1


def test_block_rectangle_uses_strict_crossing_and_ignore(m):
    a = m.actor(1, x=20, y=80, view=2)
    m.vars[20] = 3
    m.command(86, 1, 20)
    m.command(90, 20, 70, 30, 90)
    m.phase("prepare")
    assert a.direction == 0 and a.flags & BLOCKED and a.x == 20
    m.phase("finish")
    assert a.x == 20
    m.command(88, 1)
    m.command(86, 1, 20)
    m.tick()
    assert a.x == 21
    m.command(89, 1)
    m.command(91)
    assert not m.world.block_active


def test_follow_ego_completion_and_deterministic_obstacle_recovery(m):
    m.actor(0, x=40, y=80, view=2)
    a = m.actor(1, x=30, y=80, view=2)
    m.command(67, 1)
    m.command(83, 1, 3, 60)
    m.tick(9)
    assert a.x == 38 and m.flags[60] and a.direction == 0 and a.motion == 0
    m.command(37, 1, 30, 80)
    m.command(83, 1, 3, 61)
    m.phase("prepare")  # first follow cycle uses direct direction
    m.phase("finish")
    a.flags |= DIDNT_MOVE
    before_rng = m.world.rng_state
    m.phase("prepare")
    assert m.world.rng_state != before_rng and 1 <= a.direction <= 8
    assert a.follow_count >= a.step_size
    m.phase("finish")


def test_wander_is_state_deterministic_and_failed_rng_rolls_back(m, lib):
    n = Machine(lib)
    for machine in (m, n):
        machine.actor(0, view=2)
        machine.command(84, 0)
        machine.tick(20)
    assert m.snapshot() == n.snapshot()
    a = m.world.actors[0]
    a.follow_count = 0
    m.callbacks.random = RANDOM_FN()
    before = m.snapshot()
    m.tick(result=-12)
    assert m.snapshot() == before
    bad = RANDOM_FN(lambda _, state, upper: upper)
    m.callbacks.random = bad
    before = m.snapshot()
    m.tick(result=-13)
    assert m.snapshot() == before
    stuck = RANDOM_FN(lambda _, state, upper: 0)
    m.callbacks.random = stuck
    a.follow_count = 1
    a.flags |= DIDNT_MOVE
    before = m.snapshot()
    m.tick(result=-13)
    assert m.snapshot() == before


def test_prepare_logic_finish_ordering_and_no_second_motion_phase(m):
    a = m.actor(0, view=2)
    m.command(84, 0)
    a.follow_count = 0
    start = (a.x, a.y)
    m.phase("prepare")
    prepared_rng = m.world.rng_state
    assert prepared_rng != 1 and m.world.ticks == 0
    assert (a.x, a.y) == start
    # Intervening LOGIC is allowed to override the prepared direction.
    m.vars[6] = 5
    m.phase("finish")
    assert (a.x, a.y) == (start[0], start[1] + 1)
    assert m.world.rng_state == prepared_rng and m.world.ticks == 1
    b = m.actor(1, x=60, y=90, view=2)
    m.command(81, 1, 65, 90, 1, 70)
    m.phase("prepare")
    m.command(77, 1)  # LOGIC stop.motion after motion preparation
    m.phase("finish")
    assert b.x == 60 and b.direction == 0


def test_tick_batch_rolls_back_prior_successful_ticks(m):
    a = m.actor(1, cycling=True)
    m.command(45, 1)
    m.vars[20] = 3
    m.command(86, 1, 20)
    m.views[1][0][2] = (0, 4)  # fault only on the second tick's next cel
    before = m.snapshot()
    m.tick(2, result=-8)
    assert m.snapshot() == before
    m.tick()
    assert a.cel == 1 and a.x == 31 and m.world.ticks == 1


def test_distance_sentinel_saturation_direction_getter_and_force_refresh(m):
    a = m.actor(1, x=0, y=37, view=2)
    b = m.actor(2, x=158, y=167, view=2)
    m.command(69, 1, 2, 100)
    assert m.vars[100] == 254
    m.command(36, 2)
    m.command(69, 1, 2, 100)
    assert m.vars[100] == 255
    m.vars[20] = 8
    m.command(86, 1, 20)
    m.command(87, 1, 100)
    assert m.vars[100] == 8
    a.x += 1
    m.command(60, 1)
    assert a.prev_x == a.x and a.prev_width == a.width
    m.vars[20] = 9
    before = m.snapshot()
    m.command(86, 1, 20, result=-1)
    assert m.snapshot() == before
    assert not b.flags & DRAWN


def test_zero_step_time_and_no_actor_ticks_are_explicit(m):
    m.callbacks.priority = C.POINTER(U8)()
    m.tick(10)
    assert m.world.ticks == 10
    m.callbacks.priority = m.plane
    a = m.actor(1, view=2)
    m.vars[20], m.vars[21] = 3, 0
    m.command(86, 1, 20)
    m.command(80, 1, 21)
    m.tick(3)
    assert a.x == 33 and a.step_time_count == 0
    m.command(79, 1, 21)
    m.tick(3)
    assert a.x == 33
