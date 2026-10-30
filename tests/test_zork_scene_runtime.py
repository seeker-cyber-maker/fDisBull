"""Operational contracts with authored state and the actual scene/IR methods.

These unit fixtures deliberately bypass only the complete Zork package
constructor. Package/source correspondence has separate independent tests.
Effects use the real Word16 memory, object tree, frames, output and return code;
the fixtures do not replace those collaborators with mocks.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.scene_runtime import SceneRuntime, _stats
from fdisbull_player.word16 import MAX_STACK, Word16Error, Word16Runtime
from test_scene_intents import document
from test_uil_word16_runtime import authored


class RecordingSceneRuntime(SceneRuntime):
    def _write(self, address, width, value):
        super()._write(address, width, value)
        self.physical_writes.append((address, width, value, "".join(self._text)))

    def _write_var(self, index, value, indirect=False):
        if index == self.fail_variable:
            raise Word16Error("authored variable write fault")
        return super()._write_var(index, value, indirect)


def runtime_fixture(*, nested_input=False):
    blocks = {pc: [{"op": "quit"}] for pc in (
        1600, 1601, 1700, 1701, 1710, 1711, 1720, 1721, 1730, 1731, 1740, 1802,
    )}
    blocks[1801] = ([{"op": "input", "text": 1300, "parse": 1350, "resume": 1802}]
                    if nested_input else [{"op": "return", "value": 1}])
    blocks[1851] = [{"op": "return", "value": 2}]
    blocks[1900] = [{"op": "write_mem", "address": 1001, "width": 8, "value": 7},
                    {"op": "return", "value": 2}]
    program = authored(blocks)
    program["functions"] = {
        "1800": {"guard": "00", "locals": [0, 1, 0, 0, 0, 0], "entry": 1801},
        "1850": {"guard": "00", "locals": [], "entry": 1851},
    }
    runtime = RecordingSceneRuntime.__new__(RecordingSceneRuntime)
    runtime.physical_writes = []
    runtime.fail_variable = None
    Word16Runtime.__init__(runtime, program)
    runtime.scene_uil = document()
    runtime.scene_udl = {
        "runtime_guards": [], "exits": {}, "resources": {},
        "scenes": {name: {"object": number, "structure_guards": []}
                   for name, number in (("courtyard", 1), ("square", 2), ("dock", 3))},
        "facts": {"tide_is_low": {"address": 68}},
        "doors": {"iron_gate": {"object": 5, "address": 699, "mask": 16,
                                "structure_guards": [], "name_dependencies": []}},
        "handlers": {
            "guarded_route": {"kind": "routine", "header": 1850, "guard_witnesses": []},
            "missing_direction": {"kind": "source_region", "entry": 1900, "guard_witnesses": []},
        },
        "selection": {
            "locals": [0] * 5, "current_scene_global": 16, "direction_global": 17,
            "source_operations": {"direct_travel": 1700, "conditional_travel": 1710,
                                  "door_travel": 1720, "routine_call": 1730},
            "residual_frame_locals": {"property_address": 1, "property_size": 2,
                                      "failure_resource": 3, "door_object": 4, "routine_result": 5},
            "residual_arrival": {"header": 1800}, "refusal_return": 2,
            "referent": {"object_global": 21, "scene_global": 22},
        },
        "movement": {
            "locals": [0, 1, 0, 0, 0, 0], "vehicle_local": 5, "destination_local": 1,
            "actor_global": 19, "current_scene_global": 16, "qualified_actor": 4,
            "guard_witnesses": [], "continuation": 1740,
        },
    }
    exit_number = 0
    for scene in runtime.scene_uil["scenes"].values():
        for exit_ in scene["exits"].values():
            size = {"direct": 1, "blocked": 2, "routine": 3, "conditional": 4, "door": 5}[exit_["kind"]]
            runtime.scene_udl["exits"][exit_["id"]] = {
                "guard_witnesses": [], "address": 1102 + 8 * exit_number, "size": size,
                "failure_packed": 333 if "failure_resource" in exit_ else 0,
            }
            exit_number += 1
    runtime.scene_udl["resources"] = {
        name: {"dependencies": []} for name in runtime.scene_uil["resources"]}
    runtime._scene_objects = {1: "courtyard", 2: "square", 3: "dock"}
    runtime._directions = {31: "north", 30: "east", 28: "south", 29: "west",
                           23: "up", 22: "down"}
    runtime._scene_witnesses = {}
    runtime.scene_stats = _stats()
    runtime._scene_segments = []
    runtime.frames.append({"locals": [0] * 5, "base": 0, "resume": 1601, "store": 20})
    runtime._write_var(16, 1)
    runtime._write_var(17, 31)
    runtime._write_var(19, 4)
    # Actual containment: adventurer in courtyard; another object in square.
    runtime._write(runtime._object(1) + 6, 8, 4)
    runtime._write(runtime._object(4) + 4, 8, 1)
    runtime._write(runtime._object(2) + 6, 8, 6)
    runtime._write(runtime._object(6) + 4, 8, 2)
    runtime.physical_writes.clear()
    return runtime


def move_fixture():
    runtime = runtime_fixture()
    runtime.frames[-1]["locals"] = [2, 1, 1, 1, 0, 1]
    return runtime


def dispatch_fixture(*, stack_selector=False, store=1):
    runtime = runtime_fixture()
    runtime._dispatch_witnesses = {
        name: (1100, 1101, bytes(runtime.memory[1100:1101]))
        for name in ("site", "table", "pointer", "routine")}
    runtime._dispatch_udl = {
        "tables": {"actions": {"witness": "table", "pointer_witness": "pointer"}},
        "handlers": {"handler.look": {"routine_header": 1800, "witness": "routine"}},
    }
    runtime._action_numbers = {7: {"id": "look"}}
    runtime._actions = {"look": {"id": "look", "handler": "handler.look", "before_handler": None}}
    site = {
        "id": "verb_action", "frame_local_count": 5, "witness": "site",
        "selector": {"kind": "table", "table": "actions",
                     "index": {"variable": 0} if stack_selector else {"constant": 7}},
        "arguments": [], "store": store, "return_pc": 1701, "source_pcs": [1700, 1701],
    }
    return runtime, site


@pytest.mark.parametrize("direction,flag,door,destination,resume", [
    (31, 0, 0, 2, 1701),
    (28, 1, 0, 3, 1711),
    (29, 0, 16, 2, 1721),
])
def test_travel_preserves_its_specific_original_return_continuation(
        direction, flag, door, destination, resume):
    runtime = runtime_fixture()
    runtime._write_var(17, direction)
    runtime._write_var(18, flag)
    runtime._write(699, 8, door)
    runtime.stack[:] = [9, 8]
    assert runtime._select_exit() is True
    assert runtime._read_var(16) == 1  # Selection requests travel; it does not arrive.
    assert runtime.pc == 1801
    assert runtime.frames[-1]["resume"] == resume
    assert runtime.frames[-1]["locals"][0] == destination
    assert runtime.frames[-1]["base"] == 2
    rule = runtime.scene_uil["scenes"]["courtyard"]["exits"][runtime._directions[direction]]
    source = runtime.scene_udl["exits"][rule["id"]]
    assert runtime.frames[-2]["locals"] == [source["address"], source["size"], 0,
                                          5 if direction == 29 else 0, 0]
    assert runtime.stack == [9, 8]
    # The real residual return machinery reaches this same continuation.
    Word16Runtime._nodes(runtime, runtime.blocks[1801]["nodes"], {})
    assert runtime.pc == resume
    assert runtime.stack == [9, 8, 1]


@pytest.mark.parametrize("direction", [31, 28, 29])
def test_nested_residual_input_and_checkpoint_keep_materialized_caller_locals(direction):
    runtime = runtime_fixture(nested_input=True)
    runtime._write_var(17, direction)
    runtime._write_var(18, 1)
    runtime._write(699, 8, 16)
    assert runtime._select_exit()
    Word16Runtime._nodes(runtime, runtime.blocks[1801]["nodes"], {})
    assert runtime.pending_input == {"text": 1300, "parse": 1350, "resume": 1802}
    rule = runtime.scene_uil["scenes"]["courtyard"]["exits"][runtime._directions[direction]]
    source = runtime.scene_udl["exits"][rule["id"]]
    expected = [source["address"], source["size"], 0, 5 if direction == 29 else 0, 0]
    assert runtime.frames[-2]["locals"] == expected
    checkpoint = runtime.snapshot()
    fresh = runtime_fixture(nested_input=True)
    fresh.restore(checkpoint)
    assert fresh.snapshot() == checkpoint
    assert fresh.frames[-2]["locals"] == expected


def test_routine_exit_calls_the_named_residual_and_stores_its_result_in_local_five():
    runtime = runtime_fixture()
    runtime._write_var(17, 23)
    assert runtime._select_exit()
    assert runtime.pc == 1851
    assert runtime.frames[-1]["resume"] == 1731
    assert runtime.frames[-1]["store"] == 5
    Word16Runtime._nodes(runtime, runtime.blocks[1851]["nodes"], {})
    assert runtime.pc == 1731
    assert runtime.frames[-1]["locals"][4] == 2
    assert runtime.scene_stats["residual_handlers"] == {"guarded_route": 1}


def test_missing_direction_preserves_the_original_residual_body():
    runtime = runtime_fixture()
    runtime._write_var(17, 22)
    frames = copy.deepcopy(runtime.frames)
    assert runtime._select_exit()
    assert runtime.pc == 1900
    assert runtime.frames == frames
    Word16Runtime._nodes(runtime, runtime.blocks[1900]["nodes"], {})
    assert runtime.memory[1001] == 7
    assert runtime.pc == 1601
    assert runtime._read_var(20) == 2


def test_closed_door_keeps_fragment_order_then_both_discourse_writes():
    runtime = runtime_fixture()
    runtime._write_var(17, 29)
    runtime.physical_writes.clear()
    assert runtime._select_exit()
    assert runtime._text == ["The ", "iron gate", " is shut.", "\n"]
    assert runtime._read_var(21) == 5
    assert runtime._read_var(22) == 1
    assert runtime._read_var(20) == 2
    assert [(address, value) for address, width, value, text in runtime.physical_writes] == [
        (74, 5), (76, 1), (72, 2)]
    assert all(text == "The iron gate is shut.\n" for _, _, _, text in runtime.physical_writes)
    assert runtime._scene_segments[-1]["completed_realizations"] == [
        {"type": "referent_object_changed", "entity": "iron_gate"},
        {"type": "referent_scene_changed", "scene": "courtyard"},
    ]


def test_refusal_with_a_memory_output_stream_falls_back_without_any_effect():
    runtime = runtime_fixture()
    runtime._write_var(17, 29)
    runtime.host["memory_streams"] = [{"table": 1000, "count": 0}]
    before = runtime.snapshot()
    assert runtime._select_exit() is False
    assert runtime.snapshot() == before
    assert runtime.scene_stats["fallbacks"] == {"scene_refusal_memory_stream_unqualified": 1}


def test_live_flag_changes_the_decision_without_changing_the_uil_definition():
    runtime = runtime_fixture()
    runtime._write_var(17, 28)
    definition = copy.deepcopy(runtime.scene_uil)
    runtime._write_var(18, 65535)
    assert runtime._select_exit()
    assert runtime.frames[-1]["locals"][0] == 3
    assert runtime.scene_uil == definition
    assert runtime._text == []


def test_changed_source_dependency_falls_back_before_output_or_return():
    runtime = runtime_fixture()
    runtime._write_var(17, 30)
    runtime._scene_witnesses["refusal"] = (1100, 1101, b"\x99")
    runtime.scene_udl["resources"]["wall"]["dependencies"] = ["refusal"]
    before = runtime.snapshot()
    assert runtime._select_exit() is False
    assert runtime.snapshot() == before
    assert runtime.scene_stats["fallbacks"] == {"source_dependency_changed:refusal": 1}


def test_actual_on_foot_relocation_preserves_tree_order_and_write_order():
    runtime = move_fixture()
    actor, origin, target, other = [runtime._object(n) for n in (4, 1, 2, 6)]
    assert runtime._move_actor()
    assert runtime._link(4, 4) == 2
    assert runtime._link(1, 6) == 0
    assert runtime._link(2, 6) == 4
    assert runtime._link(4, 5) == 6
    assert runtime._link(6, 4) == 2
    assert runtime._read_var(16) == 2
    assert runtime.pc == 1740
    assert [(address, width, value) for address, width, value, _ in runtime.physical_writes] == [
        (origin + 6, 8, 0), (actor + 4, 8, 0), (actor + 5, 8, 0),
        (actor + 4, 8, 2), (actor + 5, 8, 6), (target + 6, 8, 4), (64, 16, 2),
    ]
    assert runtime.scene_stats["primitive_hits"] == {"scene.move_actor": 1}


def test_same_scene_travel_still_performs_the_source_tree_insertion():
    runtime = move_fixture()
    runtime.frames[-1]["locals"][0] = 1
    assert runtime._move_actor()
    assert runtime._link(4, 4) == 1
    assert runtime._link(1, 6) == 4
    assert runtime._read_var(16) == 1
    assert len(runtime.physical_writes) == 7


def test_vehicle_path_stays_residual_and_does_not_mutate_state():
    runtime = move_fixture()
    runtime.frames[-1]["locals"][4] = 6
    before = runtime.snapshot()
    assert runtime._move_actor() is False
    assert runtime.snapshot() == before
    assert runtime.scene_stats["fallbacks"] == {"move_frame_or_vehicle_not_qualified": 1}


def test_invalid_source_tree_is_detected_before_the_first_relocation_write():
    runtime = move_fixture()
    runtime._write(runtime._object(1) + 6, 8, 0)
    runtime.physical_writes.clear()
    before = runtime.snapshot()
    with pytest.raises(Word16Error, match="absent"):
        runtime._move_actor()
    assert runtime.snapshot() == before
    assert runtime.physical_writes == []


def test_relocation_fault_retains_the_completed_containment_realization():
    runtime = move_fixture()
    runtime.fail_variable = 16
    with pytest.raises(Word16Error, match="authored variable write fault"):
        runtime._move_actor()
    assert runtime._link(4, 4) == 2  # Completed source object-tree update remains authoritative.
    assert runtime._read_var(16) == 1
    record = runtime._scene_segments[-1]
    assert record["status"] == "commit_fault"
    assert record["completed_realizations"] == [{
        "type": "actor_containment_changed", "actor": "adventurer",
        "origin": "courtyard", "destination": "square"}]
    assert record["completed_effects"] == []  # The composite relocation has not completed.
    assert runtime.scene_stats["fallbacks"] == {}


def test_discourse_fault_retains_output_and_the_completed_object_assignment():
    runtime = runtime_fixture()
    runtime._write_var(17, 29)
    runtime.fail_variable = 22
    with pytest.raises(Word16Error, match="authored variable write fault"):
        runtime._select_exit()
    assert runtime._text == ["The ", "iron gate", " is shut.", "\n"]
    assert runtime._read_var(21) == 5
    assert runtime._read_var(22) == 0
    record = runtime._scene_segments[-1]
    assert record["status"] == "commit_fault"
    assert len(record["completed_effects"]) == 4
    assert record["completed_realizations"] == [
        {"type": "referent_object_changed", "entity": "iron_gate"}]
    assert runtime.scene_stats["fallbacks"] == {}


def test_resolved_dispatch_consumes_source_arguments_but_never_pushes_a_target():
    runtime, site = dispatch_fixture(stack_selector=True)
    runtime.stack[:] = [15, 7]
    site["arguments"] = [{"variable": 0}]
    assert runtime._dispatch(site)
    assert runtime.stack == []
    assert runtime.frames[-1]["base"] == 0
    assert runtime.frames[-1]["locals"][0] == 15
    assert runtime.pc == 1801
    assert runtime.scene_stats["selected_handlers"] == {"handler.look": 1}
    assert runtime.scene_stats["replaced_source_blocks"] == 2


def test_resolved_call_preflight_fault_does_not_consume_source_arguments():
    runtime, site = dispatch_fixture(stack_selector=True)
    runtime.stack[:] = [15, 7]
    site["arguments"] = [{"variable": 0}]
    site["return_pc"] = 1999
    before = runtime.snapshot()
    with pytest.raises(Word16Error, match="continuation"):
        runtime._dispatch(site)
    assert runtime.snapshot() == before


def test_null_handler_stores_zero_and_continues_without_a_spurious_frame():
    runtime, site = dispatch_fixture()
    runtime._actions["look"]["handler"] = None
    frames = len(runtime.frames)
    assert runtime._dispatch(site)
    assert len(runtime.frames) == frames
    assert runtime.frames[-1]["locals"][0] == 0
    assert runtime.pc == 1701
    assert runtime.scene_stats["selected_handlers"] == {"null_handler": 1}


def test_selector_consumption_can_free_the_slot_needed_by_a_stack_return():
    runtime, site = dispatch_fixture(stack_selector=True, store=0)
    runtime.stack[:] = [0] * (MAX_STACK - 1) + [7]
    assert runtime._dispatch(site)
    assert len(runtime.stack) == MAX_STACK - 1
    Word16Runtime._nodes(runtime, runtime.blocks[1801]["nodes"], {})
    assert len(runtime.stack) == MAX_STACK
    assert runtime.stack[-1] == 1

