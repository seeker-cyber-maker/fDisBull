"""Independent authored acceptance for the opt-in native VIEW binding profile.

Native cases require FDISBULL_QEMU_AGI_BINDING and never discover or build a
runtime. There are no original game resources in these tests. Catalog metadata,
bytecode, expected actors, event positions, and fault boundaries are authored
here without using the production VIEW parser, disassembler, or scene consumer.

One complete module run admits at most 72 owned children and 180 seconds of
wall time, with a 5-second QMP deadline and at most 128 retirements per run.
The two straight-line TCG logs are each capped at 2 MiB when read. Native failure
retention is bounded by the shared harness (1 MiB log plus <=64 KiB catalog per
child); the complete module's retained diagnostic budget is below 82 MiB.
The enclosing qualification command should enforce the same 180-second wall
deadline; an expired or failed command is never retried by this module.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native" / "qemu-agi"))
from harness import HarnessError, QemuAGI
from visual_binding_harness import (
    EVENTS_SCHEMA, STATE_SCHEMA, VIEW_BINDING_PROFILE, QemuAGIViewBinding,
    binding_guest_state,
)


# This is synthetic geometry, not a serialized or decoded original VIEW.
VIEWS = {
    10: [[(2, 3), (7, 5), (9, 8)], [(4, 6), (20, 12)], []],
    11: [[(3, 4)], [(6, 2), (30, 20), (12, 10)]],
    12: [[(160, 168)]],
    13: [[]],
    14: [[(2, 2)]],
}


def authored_catalog(records=None, *, horizon=5):
    """Assemble the documented wire format independently, retaining given order."""
    if records is None:
        records = list(VIEWS.items())
    output = bytearray(b"FDBAGIV1")
    output.extend((horizon, 0))
    output.extend(len(records).to_bytes(2, "little"))
    for view, loops in records:
        output.extend((view, len(loops)))
        output.extend(hashlib.sha256(f"authored-view-{view}".encode("ascii")).digest())
        for cels in loops:
            output.append(len(cels))
            for width, height in cels:
                output.extend((width, height))
    return bytes(output)


CATALOG = authored_catalog()


def actor(index=0, **changed):
    value = {
        "id": index, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0,
        "view_bound": False, "view": 0, "loop": 0, "cel": 0,
        "width": 0, "height": 0, "animated": False, "update": False,
        "cycling": False, "ignore_horizon": False, "update_pos": False,
        "view_replaced": False, "motion": "normal", "cycle": "normal",
        "direction": 0,
    }
    value.update(changed)
    return value


def actor_payload(value):
    return {key: item for key, item in value.items() if key != "id"}


@pytest.fixture(scope="module")
def native_launch():
    configured = os.environ.get("FDISBULL_QEMU_AGI_BINDING")
    if not configured:
        pytest.skip("native binding acceptance requires explicit FDISBULL_QEMU_AGI_BINDING")
    binary = Path(configured).expanduser().resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_BINDING must name an executable candidate binary")
    evidence = os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE")
    started, children = time.monotonic(), 0

    @contextmanager
    def launch(code, *, catalog=CATALOG, binding=True, extra_args=()):
        nonlocal children
        assert children < 72, "authored native child budget exhausted"
        assert time.monotonic() - started < 180, "authored native wall budget exhausted"
        children += 1
        options = {"timeout": 5, "evidence_dir": evidence, "extra_args": extra_args}
        vm = (QemuAGIViewBinding(binary, code, catalog, **options) if binding else
              QemuAGI(binary, code, **options))
        with vm:
            yield vm
        assert time.monotonic() - started < 180, "authored native wall budget exhausted"

    return launch


def test_binding_guest_copy_retains_every_guest_field():
    state = {"schema": STATE_SCHEMA,
             "guest": {"actors": [actor()], "loaded_views": [10],
                       "future_field": {"nested": [4]}}}
    copied = binding_guest_state(state)
    assert copied == state["guest"]
    copied["actors"][0]["x"] = 99
    copied["loaded_views"].append(11)
    copied["future_field"]["nested"].append(5)
    assert state["guest"]["actors"][0]["x"] == 0
    assert state["guest"]["loaded_views"] == [10]
    assert state["guest"]["future_field"] == {"nested": [4]}


@pytest.mark.parametrize("state", [None, [], {}, {"schema": STATE_SCHEMA},
    {"schema": STATE_SCHEMA, "guest": []},
    {"schema": "fdisbull-agi-native-state-1", "guest": {}}])
def test_binding_guest_copy_refuses_wrong_schema(state):
    with pytest.raises(HarnessError):
        binding_guest_state(state)


@pytest.mark.parametrize("catalog", [None, "FDBAGIV1", bytearray(CATALOG), b"", b"x" * 65537])
def test_wrapper_rejects_invalid_catalog_argument_before_child(catalog):
    with pytest.raises(ValueError, match="binary VIEW catalog"):
        QemuAGIViewBinding("/nonexistent/authored-candidate", b"\0", catalog)


@pytest.mark.parametrize("extra_args", [None, "-M", [17]])
def test_wrapper_rejects_invalid_command_arguments_before_child(extra_args):
    with pytest.raises(ValueError, match="extra_args"):
        QemuAGIViewBinding("/nonexistent/authored-candidate", b"\0", CATALOG,
                           extra_args=extra_args)


def test_native_initial_identity_catalog_membership_and_restart_are_immutable(native_launch):
    code = bytes((30, 10, 30, 10, 33, 0, 37, 0, 159, 0, 41, 0, 10, 0))
    with native_launch(code) as vm:
        initial = vm.state()
        initial_guest = binding_guest_state(initial)
        assert initial["source"] == {
            "sha256": hashlib.sha256(code).hexdigest(), "size": 14,
            "logic_id": 0, "profile": VIEW_BINDING_PROFILE,
            "catalog_sha256": hashlib.sha256(CATALOG).hexdigest(),
        }
        assert initial["catalog"] == {
            "sha256": hashlib.sha256(CATALOG).hexdigest(), "size": len(CATALOG),
            "view_count": 5, "loop_count": 8, "cel_count": 11, "horizon": 5,
        }
        assert initial_guest["loaded_views"] == []
        assert initial_guest["horizon"] == 5
        assert initial_guest["actors"] == [actor(i) for i in range(16)]
        for value in initial_guest["actors"]:
            assert all(type(value[key]) is bool for key in (
                "view_bound", "animated", "update", "cycling", "ignore_horizon",
                "update_pos", "view_replaced"))
        vm.configure(mask=3, capacity=64, step_budget=128)
        first = vm.run()
        events = vm.events()
        assert events["schema"] == EVENTS_SCHEMA
        assert events["source"] == initial["source"]
        assert first["guest"]["loaded_views"] == [10]
        loads = [record for record in events["events"] if record["kind"] == "view_load"]
        assert len(loads) == 1
        assert {key: loads[0][key] for key in ("view", "before", "after", "pc")} == {
            "view": 10, "before": False, "after": True, "pc": 0,
        }
        assert type(loads[0]["before"]) is type(loads[0]["after"]) is bool
        # Changing the host path cannot replace the already admitted catalog.
        vm.catalog_path.write_bytes(b"no longer a catalog")
        vm.restart()
        reset = vm.state()
        assert binding_guest_state(reset) == initial_guest
        assert reset["source"] == initial["source"]
        assert reset["catalog"] == initial["catalog"]
        assert vm.events()["events"] == []
        assert reset["observation"]["epoch"] > first["observation"]["epoch"]
        second = vm.run()
        assert binding_guest_state(second) == binding_guest_state(first)
        assert second["catalog"] == first["catalog"]


def test_native_view_loop_cel_transitions_clip_and_preserve_previous_position(native_launch):
    code = bytes((
        30, 10, 30, 11, 30, 12, 37, 0, 150, 0,
        41, 0, 10, 47, 0, 2, 43, 0, 1, 47, 0, 1,
        41, 0, 11, 41, 0, 12, 39, 0, 90, 91, 0,
    ))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=4)
        before = vm.run()
        assert before["guest"]["actors"][0] == actor(x=150, y=0, prev_x=150, prev_y=0)
        # Each row is an independently worked expected result after one opcode.
        expected = [
            (10, 0, 0, 2, 3, 150, 6),
            (10, 0, 2, 9, 8, 150, 7),
            (10, 1, 0, 4, 6, 150, 7),
            (10, 1, 1, 20, 12, 140, 11),
            (11, 1, 1, 30, 20, 130, 19),
            (12, 0, 0, 160, 168, 0, 167),
        ]
        for view, loop, cel, width, height, x, y in expected:
            state = vm.run(step_budget=1)
            assert state["guest"]["actors"][0] == actor(
                x=x, y=y, prev_x=150, prev_y=0, view_bound=True, view=view,
                loop=loop, cel=cel, width=width, height=height,
                view_replaced=True, update_pos=True,
            )
        final = vm.run(step_budget=2)
        assert final["guest"]["status"] == "return"
        assert final["guest"]["variables"][90:92] == [0, 167]
        assert final["guest"]["actors"][1:] == [actor(i) for i in range(1, 16)]
        changes = [r for r in vm.events()["events"] if r["kind"] == "actor"]
        assert [r["pc"] for r in changes] == [6, 10, 13, 16, 19, 22, 25]
        assert changes[0]["before"] == actor_payload(actor())
        assert changes[-1]["after"] == actor_payload(final["guest"]["actors"][0])
        assert all("id" not in r["before"] and "id" not in r["after"] for r in changes)
        assert all(left["after"] == right["before"] for left, right in zip(changes, changes[1:]))
        retire = {r["pc"]: r for r in vm.events()["events"] if r["kind"] == "retire"}
        assert {pc: retire[pc]["resolved_value"] for pc in (0, 2, 4, 10, 13, 16, 19, 22, 25)} == {
            0: 10, 2: 11, 4: 12, 10: 10, 13: 2, 16: 1, 19: 1, 22: 11, 25: 12,
        }
        assert retire[6]["resolved_position"] == {"x": 150, "y": 0}


def test_native_set_loop_keeps_valid_cel_and_resets_invalid_cel(native_launch):
    code = bytes((30, 10, 30, 11, 37, 0, 10, 80, 41, 0, 10, 47, 0, 1,
                  43, 0, 1, 41, 0, 11, 43, 0, 0, 0))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=6)
        first = vm.run()
        assert first["guest"]["actors"][0] == actor(
            x=10, y=80, prev_x=10, prev_y=80, view_bound=True,
            view=10, loop=1, cel=1, width=20, height=12, view_replaced=True)
        second = vm.run(step_budget=1)
        assert second["guest"]["actors"][0] == actor(
            x=10, y=80, prev_x=10, prev_y=80, view_bound=True,
            view=11, loop=1, cel=1, width=30, height=20, view_replaced=True)
        final = vm.run(step_budget=2)
        assert final["guest"]["actors"][0] == actor(
            x=10, y=80, prev_x=10, prev_y=80, view_bound=True,
            view=11, loop=0, cel=0, width=3, height=4, view_replaced=True)


def test_native_clipping_order_has_no_independent_horizon_or_bottom_clamp(native_launch):
    code = bytes((
        30, 14,
        37, 1, 1, 1, 41, 1, 14,
        37, 2, 0, 0, 41, 2, 14,
        37, 3, 200, 250, 41, 3, 14,
        37, 4, 158, 168, 41, 4, 14,
        39, 3, 80, 81, 39, 2, 82, 82,
        3, 80, 255, 3, 81, 1, 38, 3, 80, 81, 39, 3, 83, 84, 0,
    ))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=11)
        state = vm.run()
        common = {"view_bound": True, "view": 14, "width": 2, "height": 2,
                  "view_replaced": True}
        assert state["guest"]["actors"][1] == actor(1, x=1, y=1, prev_x=1, prev_y=1, **common)
        assert state["guest"]["actors"][2] == actor(2, x=0, y=6, update_pos=True, **common)
        assert state["guest"]["actors"][3] == actor(
            3, x=158, y=250, prev_x=200, prev_y=250, update_pos=True, **common)
        assert state["guest"]["actors"][4] == actor(
            4, x=158, y=168, prev_x=158, prev_y=168, **common)
        assert state["guest"]["variables"][80:83] == [158, 250, 6]
        # position.v retains its existing assignment semantics even when bound:
        # it preserves binding/flags and sets previous coordinates, with no
        # implicit geometry-selection pass or independent horizon clamp.
        moved = vm.run(step_budget=128)
        assert moved["guest"]["status"] == "return"
        assert moved["guest"]["actors"][3] == actor(
            3, x=255, y=1, prev_x=255, prev_y=1, update_pos=True, **common)
        assert moved["guest"]["variables"][83:85] == [255, 1]


def test_native_animation_preserves_binding_and_repeat_does_not_clear_sticky_clip(native_launch):
    code = bytes((30, 10, 37, 0, 159, 0, 41, 0, 10, 33, 0,
                  47, 0, 2, 33, 0, 47, 0, 0, 47, 0, 0, 0))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=3)
        clipped = vm.run()
        assert clipped["guest"]["actors"][0] == actor(
            x=158, y=6, prev_x=159, view_bound=True, view=10,
            width=2, height=3, view_replaced=True, update_pos=True)
        animated = vm.run(step_budget=1)
        assert animated["guest"]["actors"][0] == actor(
            x=158, y=6, prev_x=159, view_bound=True, view=10, width=2, height=3,
            view_replaced=True, animated=True, update=True, cycling=True)
        second_clip = vm.run(step_budget=1)
        assert second_clip["guest"]["actors"][0] == actor(
            x=151, y=7, prev_x=159, view_bound=True, view=10, cel=2,
            width=9, height=8, view_replaced=True, update_pos=True,
            animated=True, update=True, cycling=True)
        repeated = vm.run(step_budget=1)
        assert repeated["guest"]["actors"] == second_clip["guest"]["actors"]
        final = vm.run(step_budget=3)
        assert final["guest"]["actors"][0] == actor(
            x=151, y=7, prev_x=159, view_bound=True, view=10,
            width=2, height=3, view_replaced=True, update_pos=True,
            animated=True, update=True, cycling=True)
        changes = [r for r in vm.events()["events"] if r["kind"] == "actor"]
        assert [r["pc"] for r in changes] == [2, 6, 9, 11, 16]


MASK_PROGRAM = bytes((
    3, 50, 10, 31, 50, 30, 10, 33, 0, 33, 0,
    37, 0, 159, 0, 42, 0, 50, 3, 51, 2, 48, 0, 51,
    43, 0, 1, 39, 0, 70, 71, 12, 9, 0,
))
MASK_PCS = [0, 3, 5, 7, 9, 11, 15, 18, 21, 24, 27, 31, 33]


def test_native_all_four_masks_are_neutral_across_warm_restart(native_launch):
    states, events = {}, {}
    with native_launch(MASK_PROGRAM) as vm:
        for mask in (0, 1, 2, 3):
            if mask:
                vm.restart()
            vm.configure(mask=mask, capacity=64, step_budget=128)
            state = vm.run()
            states[mask] = binding_guest_state(state)
            records = vm.events()["events"]
            events[mask] = records
            retire = [r for r in records if r["kind"] == "retire"]
            scene = [r for r in records if r["kind"] != "retire"]
            assert [r["pc"] for r in retire] == (MASK_PCS if mask & 1 else [])
            assert [r["pc"] for r in scene] == ([3, 7, 11, 15, 21, 24] if mask & 2 else [])
            assert state["observation"]["dropped"] == 0
            assert state["observation"]["count"] == state["observation"]["eligible"] == len(records)
            assert state["observation"]["helper_calls"] == (13 if mask & 1 else 8 if mask & 2 else 0)
        assert states[0] == states[1] == states[2] == states[3]
        guest = states[0]
        expected_variables, expected_flags = [0] * 256, [0] * 256
        expected_variables[50], expected_variables[51] = 10, 2
        expected_variables[70], expected_variables[71] = 151, 7
        expected_flags[9] = 1
        assert guest["variables"] == expected_variables
        assert guest["flags"] == expected_flags
        assert guest["actors"] == [actor(
            x=151, y=7, prev_x=159, view_bound=True, view=10, loop=1,
            width=4, height=6, animated=True, update=True, cycling=True,
            view_replaced=True, update_pos=True), *[actor(i) for i in range(1, 16)]]
        assert (guest["loaded_views"], guest["horizon"], guest["pc"], guest["retired"],
                guest["status"], guest["fault"]) == ([10], 5, 34, 13, "return", None)
        # Observation configuration changes only session counters, not payloads.
        normalized = lambda rows: [{k: v for k, v in row.items()
                                   if k not in {"seq", "control_generation"}} for row in rows]
        assert normalized(events[1]) == normalized([r for r in events[3] if r["kind"] == "retire"])
        assert normalized(events[2]) == normalized([r for r in events[3] if r["kind"] != "retire"])


def test_native_variable_operands_record_values_at_retirement(native_launch):
    code = bytes((
        3, 10, 10, 3, 11, 1, 3, 12, 1, 3, 13, 159, 3, 14, 0,
        31, 10, 38, 0, 13, 14, 42, 0, 10, 44, 0, 11, 48, 0, 12,
        3, 10, 99, 3, 11, 99, 3, 12, 99, 3, 13, 99, 3, 14, 99,
        39, 0, 80, 81, 0,
    ))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=128)
        state = vm.run()
        retire = {r["pc"]: r for r in vm.events()["events"] if r["kind"] == "retire"}
        for pc, opcode, raw, value in ((15, 31, [31, 10], 10),
                                     (21, 42, [42, 0, 10], 10),
                                     (24, 44, [44, 0, 11], 1),
                                     (27, 48, [48, 0, 12], 1)):
            assert retire[pc]["opcode"] == opcode
            assert retire[pc]["bytes"] == raw
            assert retire[pc]["resolved_value"] == value
        assert retire[17]["bytes"] == [38, 0, 13, 14]
        assert retire[17]["resolved_position"] == {"x": 159, "y": 0}
        assert state["guest"]["variables"][10:15] == [99] * 5
        assert state["guest"]["variables"][80:82] == [140, 11]
        assert state["guest"]["actors"][0] == actor(
            x=140, y=11, prev_x=159, view_bound=True, view=10, loop=1, cel=1,
            width=20, height=12, view_replaced=True, update_pos=True)


# Eight committed instructions, then one isolated fault. Prefix state is rich
# enough to expose partial mutation of variables, flags, loads, and binding.
FAULT_PREFIX = bytes((3, 200, 7, 12, 200, 30, 10, 30, 13, 37, 0, 159, 0,
                      41, 0, 10, 33, 0, 3, 201, 255))
FAULT_CASES = [
    ([30, 250], "missing_view", 8),
    ([41, 0, 250], "missing_view", 8),
    ([41, 0, 11], "view_not_loaded", 9),
    ([43, 1, 0], "view_unbound", 10),
    ([47, 1, 0], "view_unbound", 10),
    ([43, 0, 3], "invalid_loop", 11),
    ([43, 0, 2], "empty_view_loop", 13),
    ([47, 0, 3], "invalid_cel", 12),
    ([41, 0, 13], "empty_view_loop", 13),
    ([33, 16], "invalid_actor", 3),
    ([41, 16, 10], "invalid_actor", 3),
    ([43, 16, 0], "invalid_actor", 3),
    ([47, 16, 0], "invalid_actor", 3),
    ([31, 201], "missing_view", 8),
    ([42, 0, 201], "missing_view", 8),
    ([44, 0, 201], "invalid_loop", 11),
    ([48, 0, 201], "invalid_cel", 12),
    ([37, 16, 1, 2], "invalid_actor", 3),
    ([39, 16, 202, 203], "invalid_actor", 3),
    ([32, 10], "unsupported_opcode", 1),
    ([34], "unsupported_opcode", 1),
    ([35, 0], "unsupported_opcode", 1),
    ([36, 0], "unsupported_opcode", 1),
    ([45, 0], "unsupported_opcode", 1),
    ([46, 0], "unsupported_opcode", 1),
    ([41], "truncated_instruction", 2),  # Appended return supplies only actor 0.
]


@pytest.mark.parametrize("bad_instruction,name,number", FAULT_CASES,
                         ids=[f"op{item[0][0]}-{item[1]}" for item in FAULT_CASES])
def test_native_fault_is_atomic_and_emits_no_retirement(native_launch, bad_instruction, name, number):
    code = FAULT_PREFIX + bytes(bad_instruction) + b"\0"
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=8)
        before = vm.run()
        before_events = vm.events()
        assert before["guest"]["pc"] == 21 and before["guest"]["retired"] == 8
        assert before["guest"]["status"] == "budget"
        after = vm.run(step_budget=1)
        assert after["guest"]["fault"] == {
            "code": number, "name": name, "pc": 21, "opcode": bad_instruction[0],
        }
        assert after["guest"]["status"] == "fault"
        assert after["run"]["retired"] == 0
        for field, value in before["guest"].items():
            if field not in {"status", "fault"}:
                assert after["guest"][field] == value, field
        # step_budget control legitimately changes control_generation only.
        assert vm.events()["events"] == before_events["events"]
        for field in ("count", "eligible", "dropped", "helper_calls", "per_channel"):
            assert after["observation"][field] == before["observation"][field]


@pytest.mark.parametrize("capacity", [0, 1])
def test_native_saturation_keeps_current_snapshot_and_explicit_loss(native_launch, capacity):
    code = bytes((30, 10, 33, 0, 37, 0, 159, 0, 41, 0, 10, 47, 0, 2, 0))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=capacity, step_budget=128)
        state = vm.run()
        assert state["guest"]["status"] == "return" and state["guest"]["retired"] == 6
        assert state["guest"]["loaded_views"] == [10]
        assert state["guest"]["actors"][0] == actor(
            x=151, y=7, prev_x=159, view_bound=True, view=10, cel=2, width=9, height=8,
            animated=True, update=True, cycling=True, view_replaced=True, update_pos=True)
        assert state["observation"]["eligible"] == 11
        assert state["observation"]["count"] == capacity
        assert state["observation"]["dropped"] == 11 - capacity
        assert state["observation"]["per_channel"] == {
            "disasm": {"eligible": 6, "stored": capacity, "dropped": 6 - capacity},
            "scene": {"eligible": 5, "stored": 0, "dropped": 5},
        }
        events = vm.events()["events"]
        assert len(events) == capacity
        if capacity:
            assert events[0]["kind"] == "retire" and events[0]["pc"] == 0
        vm.clear_events()
        cleared = vm.state()
        assert binding_guest_state(cleared) == binding_guest_state(state)
        assert cleared["observation"]["count"] == cleared["observation"]["eligible"] == 0
        assert vm.events()["events"] == []


def malformed_catalogs():
    one = authored_catalog([(10, [[(2, 3)]])])
    return [
        ("empty", b""),
        ("oversize", b"x" * 65537),
        ("magic", b"badmagic" + one[8:]),
        ("short-header", one[:11]),
        ("reserved", one[:9] + b"\1" + one[10:]),
        ("horizon", one[:8] + b"\xa8" + one[9:]),
        ("zero-views", one[:10] + b"\0\0"),
        ("too-many-views", one[:10] + b"\1\1" + one[12:]),
        ("short-resource-hash", one[:45]),
        ("missing-loop-count", one[:46]),
        ("short-cel", one[:-1]),
        ("zero-loops", authored_catalog([(10, [])])),
        ("zero-width", one[:-2] + b"\0\3"),
        ("wide", one[:-2] + b"\xa1\3"),
        ("zero-height", one[:-1] + b"\0"),
        ("tall", one[:-1] + b"\xa9"),
        ("duplicate-id", authored_catalog([(10, [[(2, 3)]]), (10, [[(2, 3)]])])),
        ("descending-id", authored_catalog([(11, [[(2, 3)]]), (10, [[(2, 3)]])])),
        ("trailing", one + b"\0"),
        ("aggregate-loops", authored_catalog([(i, [[]] * 205) for i in range(5)])),
        ("per-view-cels", authored_catalog([(10, [[(1, 1)] * 205] * 5)])),
        ("aggregate-cels", authored_catalog([(i, [[(1, 1)] * 205] * 4) for i in range(5)])),
    ]


@pytest.mark.parametrize("case,catalog", malformed_catalogs(),
                         ids=[item[0] for item in malformed_catalogs()])
def test_native_catalog_parser_rejects_malformed_before_running(native_launch, tmp_path, case, catalog):
    path = tmp_path / f"{case}.fdbagiv1"
    path.write_bytes(catalog)
    # Use the base transport so zero/oversized files reach native admission;
    # the higher-level wrapper correctly rejects these before child creation.
    with pytest.raises(HarnessError, match="(?i)(catalog|FDBAGIV1)"):
        with native_launch(b"\0", binding=False,
                           extra_args=("-M", f"agi-test,view-catalog={path}")):
            pytest.fail("malformed catalog was admitted")


def test_native_catalog_admits_maximum_view_loop_and_cel_indices(native_launch):
    # 256 views, a 255-loop view, and a 255-cel loop. IDs/indices are genuine
    # maxima in the wire format; geometry and horizon are also at their limits.
    records = [(index, [[(1, 1)]]) for index in range(255)]
    records.append((255, [[(1, 1)]] * 254 + [[(1, 1)] * 254 + [(160, 168)]]))
    catalog = authored_catalog(records, horizon=167)
    code = bytes((30, 255, 41, 0, 255, 43, 0, 254, 47, 0, 254, 0))
    with native_launch(code, catalog=catalog) as vm:
        vm.configure(mask=3, capacity=16, step_budget=128)
        state = vm.run()
        assert state["catalog"]["view_count"] == 256
        assert state["catalog"]["loop_count"] == 510
        assert state["catalog"]["cel_count"] == 764
        assert state["guest"]["status"] == "return"
        assert state["guest"]["loaded_views"] == [255]
        assert state["guest"]["actors"][0] == actor(
            y=168, view_bound=True, view=255, loop=254, cel=254,
            width=160, height=168, update_pos=True, view_replaced=True)


def test_native_catalog_admits_exact_aggregate_and_per_view_limits(native_launch):
    # Four views at 1024 cels each; admitted empty loops bring the aggregate
    # loop count to exactly 1024 without exceeding the 255-loop record limit.
    full = [[(1, 1)] * 255] * 4 + [[(1, 1)] * 4] + [[]] * 250
    records = [(index, full) for index in range(4)] + [(4, [[]] * 4)]
    catalog = authored_catalog(records, horizon=0)
    code = bytes((30, 0, 30, 4, 41, 0, 0, 43, 0, 4, 47, 0, 3, 0))
    with native_launch(code, catalog=catalog) as vm:
        vm.configure(mask=3, capacity=16, step_budget=128)
        state = vm.run()
        assert state["catalog"]["loop_count"] == 1024
        assert state["catalog"]["cel_count"] == 4096
        assert state["guest"]["status"] == "return"
        assert state["guest"]["loaded_views"] == [0, 4]
        assert state["guest"]["actors"][0] == actor(
            view_bound=True, loop=4, cel=3, width=1, height=1, view_replaced=True)


@pytest.mark.parametrize("instruction", [
    [30, 10], [31, 10], [33, 0], [41, 0, 10], [42, 0, 10],
    [43, 0, 0], [44, 0, 0], [47, 0, 0], [48, 0, 0],
], ids=lambda instruction: f"opcode-{instruction[0]}")
def test_native_default_profile_unchanged_and_refuses_each_binding_opcode(native_launch, instruction):
    code = bytes((37, 0, 10, 20, *instruction, 0))
    with native_launch(code, binding=False) as vm:
        vm.configure(mask=3, capacity=16, step_budget=128)
        state, events = vm.run(), vm.events()
        assert state["schema"] == "fdisbull-agi-native-state-1"
        assert events["schema"] == "fdisbull-agi-native-events-1"
        assert state["source"] == events["source"] == {
            "sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
            "logic_id": 0, "profile": "agi-2917-scalar-position-pilot-1",
        }
        assert "catalog" not in state
        assert "loaded_views" not in state["guest"] and "horizon" not in state["guest"]
        assert state["guest"]["actors"][0] == {"id": 0, "x": 10, "y": 20,
                                               "prev_x": 10, "prev_y": 20}
        assert state["guest"]["fault"] == {"code": 1, "name": "unsupported_opcode",
                                            "pc": 4, "opcode": instruction[0]}
        assert state["guest"]["retired"] == 1
        assert [record["kind"] for record in events["events"]] == ["retire", "position"]
        assert all("resolved_value" not in record and "resolved_position" not in record
                   for record in events["events"])


def test_native_zero_mask_omits_tcg_observer_with_enabled_positive_control(native_launch, tmp_path):
    code = bytes((30, 10, 33, 0, 37, 0, 159, 0, 41, 0, 10, 47, 0, 2, 0))
    guests = {}
    for mask in (0, 3):
        log = tmp_path / f"binding-mask-{mask}.tcg.log"
        with native_launch(code, extra_args=("-d", "op", "-D", str(log))) as vm:
            vm.configure(mask=mask, capacity=32, step_budget=128)
            state = vm.run()
            guests[mask] = binding_guest_state(state)
            assert state["guest"]["status"] == "return"
            assert state["guest"]["retired"] == 6
            assert state["observation"]["helper_calls"] == (6 if mask else 0)
        assert 0 < log.stat().st_size <= 2 * 1024 * 1024
        content = log.read_text(encoding="utf-8")
        helpers = {name: len(re.findall(r"\bcall\s+" + name + r"\b", content))
                   for name in ("agi_observe", "agi_binding_observe", "agi_binding", "agi_retire")}
        assert helpers["agi_retire"] == 6  # Positive execution/translation control.
        assert helpers["agi_binding"] > 0  # Semantic binding remains active.
        assert helpers["agi_observe"] + helpers["agi_binding_observe"] == (6 if mask else 0)
    assert guests[0] == guests[3]
