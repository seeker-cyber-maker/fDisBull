"""Finite scene batches for the explicitly supplied native Sarien kernel.

No compiler or guest is started here. One candidate library is loaded for the
module. The optional private reference library contains verbatim pinned Sarien
helpers; its source and build command are maintained outside the repository.
"""
from copy import deepcopy
import ctypes as C
from hashlib import sha256
import importlib.util
import os
from pathlib import Path

import pytest


NATIVE = Path(__file__).parents[1] / "native" / "qemu-agi"
_spec = importlib.util.spec_from_file_location("sarien_scene_batch_adapter", NATIVE / "sarien_scene.py")
adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adapter)
WIDTH, HEIGHT = 160, 168
ANIMATED, DRAWN, IGNORE_OBJECTS, IGNORE_BLOCKS = 1, 2, 4, 8
ON_WATER, ON_LAND, IGNORE_HORIZON, FIXED_PRIORITY = 16, 32, 64, 128


@pytest.fixture(scope="module")
def kernel():
    path = os.environ.get("FDISBULL_AGI_SCENE_LIBRARY")
    if not path:
        pytest.skip("explicit native scene library not supplied")
    digest = os.environ.get("FDISBULL_AGI_SCENE_LIBRARY_SHA256")
    assert digest, "the native scene library requires its exact SHA-256"
    return adapter.SarienScene(path, expected_sha256=digest)


def actor(identifier=0, *, x=20, y=50, width=1, height=1,
          flags=ANIMATED | DRAWN, priority=9, prev_x=None, prev_y=None):
    return dict(id=identifier, x=x, y=y, prev_x=x if prev_x is None else prev_x,
                prev_y=y if prev_y is None else prev_y, width=width, height=height,
                flags=flags, priority=priority)


def plane(value, changes=()):
    result = bytearray([value]) * (WIDTH * HEIGHT)
    for x, y, color in changes:
        result[y * WIDTH + x] = color
    return bytes(result)


def placement_case(name, expected, *, actors=None, priority=None, bands=None,
                   horizon=0, max_attempts=64, exhausted=False):
    actors = [actor()] if actors is None else actors
    x, y, level, attempts, trigger, water = expected
    return dict(name=name, inputs=dict(
        priority=plane(4) if priority is None else priority,
        bands=bytes([4]) * HEIGHT if bands is None else bands,
        actors=actors, target_id=actors[0]["id"], horizon=horizon,
        max_attempts=max_attempts), expected=dict(
        status="budget_exhausted" if exhausted else "ok", x=x, y=y,
        priority=level, attempts=attempts, ego_trigger=trigger, ego_water=water))


def placement_cases():
    bands = bytearray([4]) * HEIGHT
    bands[37] = 7
    water = plane(4, [(20, 50, 3), (21, 50, 3)])
    trigger = plane(4, [(20, 50, 2)])
    return [
        placement_case("horizon-repair-and-calculated-band", (20, 37, 7, 1, False, False),
                       actors=[actor(y=10, width=3, height=2)], horizon=36, bands=bytes(bands)),
        placement_case("ignore-horizon", (20, 10, 4, 1, False, False),
                       actors=[actor(y=10, flags=ANIMATED | DRAWN | IGNORE_HORIZON)], horizon=36),
        placement_case("right-edge-spiral-order", (157, 49, 4, 10, False, False),
                       actors=[actor(x=159, width=3)]),
        placement_case("adjacent-peer-endpoint-is-overlap", (19, 50, 4, 2, False, False),
                       actors=[actor(), actor(1, x=21)]),
        placement_case("crossed-peer-baseline", (18, 49, 4, 10, False, False),
                       actors=[actor(prev_y=52), actor(1, y=51)]),
        placement_case("target-ignores-peer", (20, 50, 4, 1, False, False),
                       actors=[actor(flags=ANIMATED | DRAWN | IGNORE_OBJECTS), actor(1, x=21)]),
        placement_case("peer-ignores-target", (20, 50, 4, 1, False, False),
                       actors=[actor(), actor(1, x=21, flags=ANIMATED | DRAWN | IGNORE_OBJECTS)]),
        placement_case("conditional-block-observed", (19, 50, 4, 2, False, False),
                       priority=plane(4, [(20, 50, 1)])),
        placement_case("conditional-block-ignored", (20, 50, 4, 1, False, False),
                       actors=[actor(flags=ANIMATED | DRAWN | IGNORE_BLOCKS)],
                       priority=plane(4, [(20, 50, 1)])),
        placement_case("unconditional-block-still-repairs", (19, 50, 4, 2, False, False),
                       actors=[actor(flags=ANIMATED | DRAWN | IGNORE_BLOCKS)],
                       priority=plane(4, [(20, 50, 0)])),
        placement_case("ego-entire-baseline-on-water", (20, 50, 4, 1, False, True),
                       actors=[actor(width=2, flags=ANIMATED | DRAWN | ON_WATER)], priority=water),
        placement_case("land-actor-leaves-all-water-baseline", (19, 50, 4, 2, False, False),
                       actors=[actor(width=2, flags=ANIMATED | DRAWN | ON_LAND)], priority=water),
        placement_case("ego-trigger-with-land", (20, 50, 4, 1, True, False),
                       actors=[actor(width=2)], priority=trigger),
        placement_case("non-ego-does-not-write-ego-flags", (20, 50, 4, 1, False, False),
                       actors=[actor(7, width=2)], priority=trigger),
        placement_case("fixed-priority-15-bypasses-controls", (20, 50, 15, 1, False, False),
                       actors=[actor(flags=ANIMATED | DRAWN | FIXED_PRIORITY | ON_WATER,
                                     priority=15)], priority=plane(0)),
        placement_case("impossible-layout-preserves-original-pose", (20, 10, 9, 7, False, False),
                       actors=[actor(y=10)], priority=plane(0), horizon=36,
                       max_attempts=7, exhausted=True),
    ]


def blit_cases():
    control = plane(4, [(10, 10, 0), (10, 11, 1), (10, 12, 8),
                        (11, 10, 2), (12, 10, 3), (13, 10, 7)])
    return [
        dict(name="control-lookup-water-transparency-and-occlusion",
             inputs=dict(visual=plane(1), priority=control, cel=bytes([2, 3, 4, 8, 5, 6, 15, 7]),
                         x=10, baseline=11, width=4, height=2, transparent=15, actor_priority=6),
             expected=dict(visual=plane(1, [(11, 10, 3), (12, 10, 4), (11, 11, 6), (13, 11, 7)]),
                           priority=bytes(6 if index in (10 * WIDTH + 12, 11 * WIDTH + 11,
                                                       11 * WIDTH + 13) else color
                                          for index, color in enumerate(control)),
                           written_pixels=4, hidden=False)),
        dict(name="control-column-bottom-defaults-to-priority-four",
             inputs=dict(visual=plane(1), priority=plane(4, [(20, 167, 2)]), cel=b"\x09",
                         x=20, baseline=167, width=1, height=1, transparent=15, actor_priority=4),
             expected=dict(visual=plane(1, [(20, 167, 9)]), priority=plane(4, [(20, 167, 2)]),
                           written_pixels=1, hidden=False)),
        dict(name="transparent-cel-is-hidden",
             inputs=dict(visual=plane(1), priority=plane(4), cel=bytes([15]) * 4,
                         x=5, baseline=5, width=2, height=2, transparent=15, actor_priority=7),
             expected=dict(visual=plane(1), priority=plane(4), written_pixels=0, hidden=True)),
        dict(name="opaque-cel-fully-occluded",
             inputs=dict(visual=plane(1), priority=plane(8), cel=b"\x02\x03",
                         x=5, baseline=5, width=2, height=1, transparent=15, actor_priority=7),
             expected=dict(visual=plane(1), priority=plane(8), written_pixels=0, hidden=True)),
        dict(name="equal-priority-later-layer-wins",
             inputs=dict(visual=plane(1), priority=plane(6), cel=b"\x09",
                         x=5, baseline=5, width=1, height=1, transparent=15, actor_priority=6),
             expected=dict(visual=plane(1, [(5, 5, 9)]), priority=plane(6),
                           written_pixels=1, hidden=False)),
    ]


def layered_scene():
    return dict(visual=plane(1), priority=plane(4), bands=bytes([4]) * HEIGHT, horizon=0,
                actors=[actor(0, x=50, y=50, width=3, height=2,
                              flags=ANIMATED | FIXED_PRIORITY, priority=5),
                        actor(1, x=51, y=50, width=2, height=2,
                              flags=ANIMATED | FIXED_PRIORITY, priority=7),
                        actor(2, x=50, y=51, width=3, height=3,
                              flags=ANIMATED | FIXED_PRIORITY | IGNORE_OBJECTS, priority=4)],
                layers=[dict(actor_id=0, cel=bytes([2]) * 6, transparent=15),
                        dict(actor_id=1, cel=bytes([3, 15, 3, 3]), transparent=15),
                        dict(actor_id=2, cel=bytes([9]) * 9, transparent=15)])


def test_literal_scene_batch(kernel, record_property):
    placements, blits = placement_cases(), blit_cases()
    record_property("placement_scenes", ",".join(case["name"] for case in placements))
    record_property("blit_scenes", ",".join(case["name"] for case in blits))
    for case in placements:
        original = deepcopy(case["inputs"])
        assert kernel.place(**case["inputs"]) == case["expected"], case["name"]
        assert case["inputs"] == original, case["name"]
    for case in blits:
        original = deepcopy(case["inputs"])
        assert kernel.blit(**case["inputs"]) == case["expected"], case["name"]
        assert case["inputs"] == original, case["name"]


def test_complete_preview_and_rollback_batch(kernel, record_property):
    record_property("preview_scenes", "three-layer-peer-repair-and-occlusion,late-layer-budget-rollback")
    scene = layered_scene()
    original = deepcopy(scene)
    result = kernel.preview(**scene)
    assert scene == original
    assert result["status"] == "preview_complete"
    assert result["visual"] == plane(1, [(50, 49, 2), (51, 49, 2), (52, 49, 2),
                                         (50, 50, 3), (51, 50, 2), (52, 50, 2),
                                         (50, 51, 3), (51, 51, 3), (52, 51, 9)])
    assert result["priority"] == plane(4, [(50, 49, 5), (51, 49, 5), (52, 49, 5),
                                           (50, 50, 7), (51, 50, 5), (52, 50, 5),
                                           (50, 51, 7), (51, 51, 7)])
    expected_actors = deepcopy(scene["actors"])
    for row in expected_actors:
        row["flags"] |= DRAWN
    expected_actors[1].update(x=50, y=51, prev_x=50, prev_y=51)
    assert result["actors"] == expected_actors
    assert [step["placement"]["attempts"] for step in result["steps"]] == [1, 3, 1]
    assert [step["composition"] for step in result["steps"]] == [
        dict(written_pixels=6, hidden=False), dict(written_pixels=3, hidden=False),
        dict(written_pixels=1, hidden=False)]
    assert result["native_draw_committed"] is False
    assert result["presentation_established"] is False

    rollback = dict(visual=plane(1), priority=plane(4, [(30, 60, 0)]),
                    bands=bytes([4]) * HEIGHT, horizon=0, max_attempts=1,
                    actors=[actor(0, x=10, width=2, flags=ANIMATED | FIXED_PRIORITY, priority=5),
                            actor(1, x=30, y=60, flags=ANIMATED | FIXED_PRIORITY, priority=4)],
                    layers=[dict(actor_id=0, cel=b"\x02\x02", transparent=15),
                            dict(actor_id=1, cel=b"\x03", transparent=15)])
    original = deepcopy(rollback)
    failed = kernel.preview(**rollback)
    assert rollback == original
    assert failed["status"] == "budget_exhausted"
    assert {key: failed[key] for key in ("visual", "priority", "actors")} == {
        key: original[key] for key in ("visual", "priority", "actors")}
    assert failed["steps"][0]["composition"] == dict(written_pixels=2, hidden=False)
    assert failed["steps"][1]["placement"] == dict(
        status="budget_exhausted", x=30, y=60, priority=4, attempts=1,
        ego_trigger=False, ego_water=False)
    assert failed["native_draw_committed"] is False
    assert failed["presentation_established"] is False


def test_bounded_admission_batch(kernel, record_property):
    record_property("rejected_scenes", "unknown-actor-flag,late-invalid-cel-color")
    bad_actor = placement_cases()[0]["inputs"]
    bad_actor["actors"][0]["flags"] |= 256
    original = deepcopy(bad_actor)
    with pytest.raises(adapter.SceneInputError):
        kernel.place(**bad_actor)
    assert bad_actor == original
    bad_cel = dict(visual=plane(1), priority=plane(4), cel=b"\x02\x10",
                   x=5, baseline=5, width=2, height=1, transparent=15, actor_priority=7)
    original = deepcopy(bad_cel)
    with pytest.raises(adapter.SceneInputError):
        kernel.blit(**bad_cel)
    assert bad_cel == original


class _ReferenceActor(C.Structure):
    _fields_ = [(name, C.c_int32) for name in
                ("id", "x", "y", "prev_x", "prev_y", "width", "height")] + [
                    ("flags", C.c_uint32), ("priority", C.c_uint32)]


class _ReferencePlacement(C.Structure):
    _fields_ = [("status", C.c_int32), ("x", C.c_int32), ("y", C.c_int32)] + [
        (name, C.c_uint32) for name in ("priority", "attempts", "ego_trigger", "ego_water")]


@pytest.fixture(scope="module")
def reference():
    path = os.environ.get("FDISBULL_AGI_SCENE_REFERENCE_LIBRARY")
    if not path:
        pytest.skip("optional pinned upstream reference library not supplied")
    digest = os.environ.get("FDISBULL_AGI_SCENE_REFERENCE_LIBRARY_SHA256")
    assert digest and sha256(Path(path).read_bytes()).hexdigest() == digest
    lib = C.CDLL(str(Path(path).resolve(strict=True)))
    pointer = C.POINTER(C.c_uint8)
    lib.sarien_reference_place.argtypes = [pointer, pointer, C.c_int32,
        C.POINTER(_ReferenceActor), C.c_uint32, C.c_uint32, C.c_uint32,
        C.POINTER(_ReferencePlacement)]
    lib.sarien_reference_place.restype = C.c_int
    lib.sarien_reference_blit.argtypes = [pointer, pointer, pointer, C.c_int32,
        C.c_int32, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32,
        C.POINTER(C.c_uint32)]
    lib.sarien_reference_blit.restype = C.c_int
    return lib


def _buffer(value):
    return (C.c_uint8 * len(value)).from_buffer_copy(value)


def _reference_place(lib, inputs):
    rows = (_ReferenceActor * len(inputs["actors"]))(*[
        _ReferenceActor(*(row[name] for name, _ in _ReferenceActor._fields_))
        for row in inputs["actors"]])
    output = _ReferencePlacement()
    status = lib.sarien_reference_place(
        _buffer(inputs["priority"]), _buffer(inputs["bands"]), inputs["horizon"],
        rows, len(rows), inputs["target_id"], inputs["max_attempts"], C.byref(output))
    assert status == 0, "finite feasible reference scene exceeded its guard"
    return dict(status="ok", x=output.x, y=output.y, priority=output.priority,
                attempts=output.attempts, ego_trigger=bool(output.ego_trigger),
                ego_water=bool(output.ego_water))


def _reference_blit(lib, inputs):
    visual, priority = _buffer(inputs["visual"]), _buffer(inputs["priority"])
    hidden = C.c_uint32()
    status = lib.sarien_reference_blit(
        visual, priority, _buffer(inputs["cel"]), inputs["x"], inputs["baseline"],
        inputs["width"], inputs["height"], inputs["transparent"],
        inputs["actor_priority"], C.byref(hidden))
    assert status == 0
    return dict(visual=bytes(visual), priority=bytes(priority), hidden=bool(hidden.value))


def test_pinned_upstream_differential_batch(kernel, reference, record_property):
    placements = [case for case in placement_cases() if case["expected"]["status"] == "ok"]
    blits = blit_cases()
    record_property("upstream_commit", "aaef5e667757385b5b3650cc1f7365908720f7e6")
    record_property("differential_placement_scenes", len(placements))
    record_property("differential_blit_scenes", len(blits))
    for case in placements:
        assert kernel.place(**case["inputs"]) == _reference_place(reference, case["inputs"]), case["name"]
    for case in blits:
        observed = kernel.blit(**case["inputs"])
        expected = _reference_blit(reference, case["inputs"])
        assert {key: observed[key] for key in expected} == expected, case["name"]
