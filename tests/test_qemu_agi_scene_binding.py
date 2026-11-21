"""Independent authored-record batches for explicit conditional scene recipes.

These tests consume CPU-shaped records, never decode an opcode or launch a
guest. Expected paths, use-site values and draw chronology are authored here;
the existing discovery corpus supplies reusable input records, not an oracle.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native/qemu-agi"))
from harness import HarnessError
from processor_scene_binding import derive_bound_scene_recipe
from test_qemu_agi_discovery import (
    CODE, DECODER, LABELS, MAPPINGS, RESOURCE_HASH, ROWS, SCHEMA, SOURCE,
    _immediate, _literal, _page, _pages, _variable,
)


REASON = "Explicit authored design input; not an observed engine value"


def _binding(label, operand_index, variable, value):
    return {"pc": LABELS[label], "operand_index": operand_index,
            "variable": variable, "value": value, "reason": REASON}


def _inputs(*, picture_then=True, cel_then=True):
    branch = "then" if picture_then else "else"
    return {
        "code": CODE, "pages": _pages(), "source_mappings": deepcopy(MAPPINGS),
        "entry_pc": LABELS["entry"],
        "endpoint": {"pc": LABELS["draw"], "phase": "after"},
        "branch_choices": {LABELS["entry"]: "true" if picture_then else "false",
                           LABELS["pose_condition"]: "true" if cel_then else "false"},
        # Deliberately differ from the preceding authored assignn and from each
        # other. The binder must use each source-site input without executing
        # scalar assignments or replacing historical uses with a final value.
        "operand_bindings": [_binding("load_picture_" + branch, 0, 0, 7),
                             _binding("draw_picture_" + branch, 0, 0, 9)],
        "actor_inputs": [{"actor": 0, "fields": {"loop": 0, "priority": 4},
                          "reason": REASON}],
    }


def _actors(recipe):
    return {actor["actor"]: actor for actor in recipe["actors"]}


def _values(actor):
    return {name: field["value"] for name, field in actor["fields"].items()}


def _unobserved(recipe):
    assert recipe["runtime_observed"] is False
    assert recipe["native_draw_completed"] is False
    assert recipe["presentation_established"] is False
    assert "guest" not in recipe and "native_state" not in recipe


@pytest.mark.parametrize("picture_then,cel_then", [(True, True), (True, False),
                                                      (False, True), (False, False)])
def test_selected_branch_batch_keeps_use_site_inputs_and_provenance(picture_then, cel_then):
    inputs = _inputs(picture_then=picture_then, cel_then=cel_then)
    before = deepcopy(inputs)
    recipe = derive_bound_scene_recipe(**inputs)
    branch = "then" if picture_then else "else"
    names = ["entry", "picture_" + branch, "load_picture_" + branch,
             "draw_picture_" + branch]
    if picture_then:
        names.append("picture_join_jump")
    names += ["picture_join", "view", "animate", "bind", "pose_condition",
              "cel_then" if cel_then else "cel_else"]
    if cel_then:
        names.append("cel_join_jump")
    names += ["position", "draw"]
    assert recipe["path"] == [LABELS[name] for name in names]
    assert recipe["schema"] == "fdisbull-agi-bound-scene-recipe-1"
    assert recipe["status"] == "selected_endpoint_reached"
    assert recipe["endpoint"]["reached"] is True
    assert recipe["endpoint"]["stop_reason"] == "selected_endpoint"
    assert recipe["endpoint"]["requested"] == inputs["endpoint"]
    assert recipe["source"] == SOURCE
    timeline = {entry["pc"]: entry for entry in recipe["timeline"]}
    for name, value in (("load_picture_" + branch, 7), ("draw_picture_" + branch, 9)):
        entry = timeline[LABELS[name]]
        assert entry["instruction"]["operands"] == [_variable("picture", 0)]
        assert entry["operands"][0]["value"] == value
        assert entry["operands"][0]["operand_index"] == 0
    assert timeline[LABELS["entry"]]["instruction"]["conditions"] == ROWS[0]["conditions"]

    actor = _actors(recipe)[0]
    assert {key: _values(actor)[key] for key in ("view", "loop", "cel", "x", "y", "priority")} == {
        "view": 10, "loop": 0, "cel": 1 if cel_then else 0, "x": 30, "y": 90,
        "priority": 4,
    }
    assert actor["missing_fields"] == []
    cel_pc = LABELS["cel_then" if cel_then else "cel_else"]
    cel_provenance = actor["fields"]["cel"]["provenance"]
    assert cel_provenance["basis"] == "native_requested"
    assert cel_provenance["pc"] == cel_pc
    assert cel_provenance["operation"] == "object.set_cel"
    assert cel_provenance["source_mapping"] == {
        "kind": "original", "original_source_address": {
            "logic": 23, "resource_sha256": RESOURCE_HASH,
            "code_pc": cel_pc, "payload_offset": cel_pc + 2,
        },
    }
    for name in ("loop", "priority"):
        provenance = actor["fields"][name]["provenance"]
        assert provenance["basis"] == "caller_declared_design_input"
        assert provenance["scope"] == "selected_endpoint"
        assert provenance["reason"] == REASON
    assert actor["draw_request_pcs"] == [LABELS["draw"]]
    assert len(recipe["draw_requests"]) == 1
    draw = recipe["draw_requests"][0]
    assert draw["pc"] == LABELS["draw"]
    # Final design fills must never rewrite an earlier draw's recorded inputs.
    assert set(draw["requested_pose"]["missing_fields"]) == {"loop", "priority"}
    assert "loop" not in draw["requested_pose"]["fields"]
    assert "priority" not in draw["requested_pose"]["fields"]
    _unobserved(recipe)
    assert inputs == before
    actor["fields"]["cel"]["value"] = 99
    timeline[LABELS["entry"]]["instruction"]["conditions"].clear()
    assert inputs == before


def test_missing_scene_inputs_remain_explicit_without_scalar_propagation():
    inputs = _inputs()
    inputs.update(operand_bindings=[], actor_inputs=[])
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["status"] == "selected_endpoint_reached"
    assert set(_actors(recipe)[0]["missing_fields"]) == {"loop", "priority"}
    wanted = {LABELS["load_picture_then"], LABELS["draw_picture_then"]}
    assert {row["pc"] for row in recipe["required_inputs"] if row["kind"] == "operand_binding"} == wanted
    for entry in recipe["timeline"]:
        if entry["pc"] in wanted:
            assert entry["operands"][0]["value"] is None
    _unobserved(recipe)


def test_before_endpoint_records_boundary_without_consuming_or_projecting_it():
    inputs = _inputs()
    inputs["endpoint"]["phase"] = "before"
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["endpoint"]["reached"] is True
    assert recipe["path"][-1] == LABELS["draw"]
    assert recipe["timeline"][-1]["projection"] == "endpoint_before"
    assert recipe["draw_requests"] == []
    assert _actors(recipe)[0]["draw_request_pcs"] == []

    inputs.update(entry_pc=LABELS["load_picture_then"],
                  endpoint={"pc": LABELS["load_picture_then"], "phase": "before"},
                  branch_choices={}, actor_inputs=[],
                  operand_bindings=[_binding("load_picture_then", 0, 0, 7)])
    with pytest.raises(HarnessError):
        derive_bound_scene_recipe(**inputs)

    inputs.update(entry_pc=LABELS["room_variable"],
                  endpoint={"pc": LABELS["room_variable"], "phase": "before"},
                  operand_bindings=[])
    before_room = derive_bound_scene_recipe(**inputs)
    assert before_room["endpoint"]["reached"] is True
    assert before_room["timeline"][-1]["projection"] == "endpoint_before"
    assert before_room["resource_requests"] == []


@pytest.mark.parametrize("case", [
    "unused_branch", "branch_on_non_if", "invalid_branch", "duplicate_binding",
    "unused_binding", "wrong_variable", "wrong_operand", "write_operand",
    "boolean_value", "empty_reason", "duplicate_actor", "unknown_actor_field",
    "known_field_override", "unused_actor", "bad_endpoint_phase", "bad_endpoint_pc",
])
def test_stale_or_invalid_input_batch_rejects_without_mutation(case):
    inputs = _inputs()
    if case == "unused_branch":
        inputs["branch_choices"][LABELS["loop"]] = "true"
    elif case == "branch_on_non_if":
        inputs["branch_choices"][LABELS["draw"]] = "true"
    elif case == "invalid_branch":
        inputs["branch_choices"][LABELS["entry"]] = "fallthrough"
    elif case == "duplicate_binding":
        inputs["operand_bindings"].append(deepcopy(inputs["operand_bindings"][0]))
    elif case == "unused_binding":
        inputs["operand_bindings"].append(_binding("load_picture_else", 0, 0, 53))
    elif case == "wrong_variable":
        inputs["operand_bindings"][0]["variable"] = 1
    elif case == "wrong_operand":
        inputs["operand_bindings"][0]["operand_index"] = 1
    elif case == "write_operand":
        inputs["operand_bindings"].append(_binding("picture_then", 0, 0, 5))
    elif case == "boolean_value":
        inputs["operand_bindings"][0]["value"] = True
    elif case == "empty_reason":
        inputs["operand_bindings"][0]["reason"] = ""
    elif case == "duplicate_actor":
        inputs["actor_inputs"].append(deepcopy(inputs["actor_inputs"][0]))
    elif case == "unknown_actor_field":
        inputs["actor_inputs"][0]["fields"]["made_up"] = 1
    elif case == "known_field_override":
        inputs["actor_inputs"][0]["fields"]["view"] = 10
    elif case == "unused_actor":
        inputs["actor_inputs"].append({"actor": 3, "fields": {"loop": 0}, "reason": REASON})
    elif case == "bad_endpoint_phase":
        inputs["endpoint"]["phase"] = "during"
    elif case == "bad_endpoint_pc":
        inputs["endpoint"]["pc"] = len(CODE)
    before = deepcopy(inputs)
    with pytest.raises((HarnessError, ValueError)):
        derive_bound_scene_recipe(**inputs)
    assert inputs == before


@pytest.mark.parametrize("case,reason", [
    ("call_literal", "external_call"), ("call_variable", "external_call"),
    ("call_on_endpoint", "external_call"), ("unknown_on_endpoint", "unmodeled_effect"),
    ("unmodeled", "unmodeled_effect"), ("room_literal", "external_room_transfer"),
    ("room_variable", "external_room_transfer"), ("room_on_endpoint", "external_room_transfer"),
    ("dead_return", "terminal_before_endpoint"),
    ("loop", "repeated_pc"), ("no_branch", "branch_choice_required"),
    ("missing_record", "missing_native_record"), ("fault", "decode_fault"),
    ("outside_jump", "out_of_range_edge"), ("step_budget", "step_budget"),
])
def test_boundary_batch_does_not_invent_a_continuation(case, reason):
    label = {"no_branch": "entry", "missing_record": "entry",
             "fault": "unknown_action", "step_budget": "entry",
             "call_on_endpoint": "call_literal", "unknown_on_endpoint": "unmodeled",
             "room_on_endpoint": "room_variable"}.get(case, case)
    inputs = {
        "code": CODE, "pages": _pages(), "source_mappings": deepcopy(MAPPINGS),
        "entry_pc": LABELS[label],
        "endpoint": {"pc": LABELS["large_return"], "phase": "after"},
        "branch_choices": {}, "operand_bindings": [], "actor_inputs": [],
    }
    if case == "loop":
        inputs["branch_choices"] = {LABELS["loop"]: "true"}
    elif case == "missing_record":
        inputs.update(pages=[_page([ROWS[0]])], branch_choices={LABELS["entry"]: "true"})
    elif case == "step_budget":
        inputs.update(max_steps=1, branch_choices={LABELS["entry"]: "true"})
    elif case == "call_variable":
        inputs["operand_bindings"] = [_binding("call_variable", 0, 9, 7)]
    elif case in ("room_variable", "room_on_endpoint"):
        inputs["operand_bindings"] = [_binding("room_variable", 0, 8, 42)]
    if case in ("call_on_endpoint", "unknown_on_endpoint", "room_on_endpoint"):
        inputs["endpoint"]["pc"] = LABELS[label]
    before = deepcopy(inputs)
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["status"] == "blocked"
    assert recipe["endpoint"]["reached"] is False
    assert recipe["endpoint"]["stop_reason"] == reason
    if case == "fault":
        assert recipe["path"] == []
        assert recipe["endpoint"]["stopped_pc"] == LABELS[label]
    else:
        assert recipe["path"][0] == LABELS[label]
    assert LABELS["large_return"] not in recipe["path"]
    assert recipe["draw_requests"] == []
    if case in ("call_literal", "call_variable", "call_on_endpoint", "unknown_on_endpoint",
                "unmodeled", "room_literal", "room_variable", "room_on_endpoint", "dead_return"):
        assert recipe["path"] == [LABELS[label]]
    if case == "loop":
        assert recipe["path"][:2] == [LABELS["loop"], LABELS["loop_back"]]
        assert recipe["endpoint"]["stopped_pc"] == LABELS["loop"]
    if case == "call_variable":
        assert recipe["timeline"][0]["operands"][0]["value"] == 7
    if case in ("room_variable", "room_on_endpoint"):
        assert recipe["timeline"][0]["operands"][0]["value"] == 42
        assert LABELS["dead_view"] not in recipe["path"]
    _unobserved(recipe)
    assert inputs == before


@pytest.mark.parametrize("case", ["source_identity", "different_row",
                                  "mapping_gap", "mapping_overlap", "mapping_coordinates"])
def test_source_contract_batch_rejects_conflicting_identity_or_extents(case):
    inputs = _inputs()
    if case == "source_identity":
        inputs["pages"][0]["source"]["sha256"] = "0" * 64
    elif case == "different_row":
        duplicate = deepcopy(inputs["pages"][0])
        duplicate["instructions"][0]["mnemonic"] = "contradictory"
        inputs["pages"].append(duplicate)
    elif case == "mapping_gap":
        inputs["source_mappings"][0]["fragment_span"][0] = 1
    elif case == "mapping_overlap":
        inputs["source_mappings"].append(deepcopy(inputs["source_mappings"][0]))
    elif case == "mapping_coordinates":
        inputs["source_mappings"][0]["source"]["payload_span"][0] += 1
    before = deepcopy(inputs)
    with pytest.raises(HarnessError):
        derive_bound_scene_recipe(**inputs)
    assert inputs == before


def test_prefetched_overlapping_extent_does_not_invalidate_unrelated_selected_path():
    inputs = _inputs()
    interior = deepcopy(next(row for row in ROWS if row["pc"] == LABELS["dead_return"]))
    interior["pc"] = LABELS["interior_position"] + 1
    inputs["pages"].append(_page([interior]))
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["status"] == "selected_endpoint_reached"
    assert LABELS["interior_position"] not in recipe["path"]
    assert interior["pc"] not in recipe["path"]


def _chronology_inputs():
    """A second authored record batch: two draws, a later pose, then erase."""
    code, rows, labels = bytearray(), [], {}

    def add(label, raw, mnemonic, operation, operands=(), effect="actor"):
        pc = len(code)
        code.extend(raw)
        labels[label] = pc
        rows.append({"pc": pc, "opcode": raw[0], "size": len(raw), "bytes": raw,
                     "mnemonic": mnemonic, "operation": operation, "operands": list(operands),
                     "conditions": [], "successors": [{"kind": "fallthrough", "pc": len(code),
                                                         "in_range": True}],
                     "effect_class": effect, "execution_support": "unsupported_profile"})

    actor = _literal("actor", "actor", 0)
    add("bind", [41, 0, 10], "set.view", "object.set_view",
        [actor, _literal("view", "view", 10)])
    add("loop", [43, 0, 0], "set.loop", "object.set_loop", [actor, _literal("loop", "loop", 0)])
    add("cel", [47, 0, 0], "set.cel", "object.set_cel", [actor, _literal("cel", "cel", 0)])
    add("position_input", [38, 0, 10, 11], "position.v", "object.position",
        [actor, _variable("x", 10), _variable("y", 11)])
    add("priority", [54, 0, 5], "set.priority", "object.set_priority", [actor, _immediate("priority", 5)])
    add("draw_first", [35, 0], "draw", "object.draw", [actor], effect="host")
    add("stop", [70, 0], "stop.cycling", "object.stop_cycling", [actor])
    add("position_later", [37, 0, 40, 50], "position", "object.position",
        [actor, _immediate("x", 40), _immediate("y", 50)])
    add("draw_second", [35, 0], "draw", "object.draw", [actor], effect="host")
    add("show", [26], "show.pic", "scene.show_picture", effect="host")
    add("erase", [36, 0], "erase", "object.erase", [actor], effect="host")
    add("return", [0], "return", "control.return", effect="control")
    rows[-1]["successors"] = []
    code = bytes(code)
    source = {**SOURCE, "sha256": sha256(code).hexdigest(), "size": len(code)}
    page = {"schema": SCHEMA, "decoder": deepcopy(DECODER), "source": source,
            "evidence": "static_decode", "traversal": "linear", "start_pc": 0,
            "limit": len(rows), "next_pc": len(code), "stop": "end", "instructions": rows,
            "error": None}
    return {
        "code": code, "pages": [page],
        "source_mappings": [{"kind": "authored", "fragment_span": [0, len(code)], "source": None}],
        "entry_pc": 0, "endpoint": {"pc": labels["show"], "phase": "after"},
        "branch_choices": {}, "actor_inputs": [],
        "operand_bindings": [{"pc": labels["position_input"], "operand_index": index,
                              "variable": variable, "value": value, "reason": REASON}
                             for index, variable, value in ((1, 10, 20), (2, 11, 60))],
    }, labels


@pytest.mark.parametrize("endpoint", ["show", "erase"])
def test_draw_chronology_batch_keeps_each_request_pose_separate(endpoint):
    inputs, labels = _chronology_inputs()
    inputs["endpoint"]["pc"] = labels[endpoint]
    before = deepcopy(inputs)
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["endpoint"]["reached"] is True
    assert [draw["pc"] for draw in recipe["draw_requests"]] == [labels["draw_first"], labels["draw_second"]]
    first, second = [draw["requested_pose"]["fields"] for draw in recipe["draw_requests"]]
    assert (first["x"]["value"], first["y"]["value"]) == (20, 60)
    assert (second["x"]["value"], second["y"]["value"]) == (40, 50)
    assert "cycling" not in first
    assert second["cycling"]["value"] is False
    assert first["x"]["provenance"]["binding"] == {"variable": 10, "value": 20, "reason": REASON}
    assert first["x"]["provenance"]["source_mapping"] == {
        "kind": "authored", "original_source_address": None}
    final = _values(_actors(recipe)[0])
    assert (final["x"], final["y"], final["cycling"]) == (40, 50, False)
    assert final["draw_requested"] is (endpoint == "show")
    assert inputs == before
    _unobserved(recipe)


def test_design_fill_cannot_bypass_a_source_explicit_unresolved_operand():
    inputs, labels = _chronology_inputs()
    inputs.update(operand_bindings=[], endpoint={"pc": labels["draw_first"], "phase": "after"},
                  actor_inputs=[{"actor": 0, "fields": {"x": 20, "y": 60}, "reason": REASON}])
    with pytest.raises(HarnessError):
        derive_bound_scene_recipe(**inputs)


def test_assumed_successor_remains_a_barrier_even_for_a_named_operation():
    inputs = _inputs()
    inputs.update(entry_pc=LABELS["picture_join_jump"], branch_choices={},
                  operand_bindings=[], actor_inputs=[])
    # A consumer must respect an explicitly qualified native edge without
    # guessing from the instruction spelling that continuation is safe.
    for page in inputs["pages"]:
        for row in page["instructions"]:
            if row["pc"] == LABELS["picture_join_jump"]:
                row["successors"][0]["kind"] = "assumed_fallthrough"
    recipe = derive_bound_scene_recipe(**inputs)
    assert recipe["endpoint"]["stop_reason"] == "assumed_successor"
    assert recipe["path"] == [LABELS["picture_join_jump"]]
    assert recipe["endpoint"]["reached"] is False


@pytest.mark.parametrize("case,reason", [
    ("selected_overlap", "overlapping_instruction_extent"),
    ("unsupported_scene", "unsupported_scene_operation"),
])
def test_selected_extent_and_unsupported_effect_boundaries(case, reason):
    def record(pc, raw, mnemonic, operation, operands, successors, effect):
        return {"pc": pc, "opcode": raw[0], "size": len(raw), "bytes": raw,
                "mnemonic": mnemonic, "operation": operation, "operands": operands,
                "conditions": [], "successors": successors, "effect_class": effect,
                "execution_support": "unsupported_profile"}

    actor = _literal("actor", "actor", 0)
    if case == "selected_overlap":
        # position at0, goto at4 targeting1, and a separately supplied return
        # at1. Its byte is indeed zero, but its extent overlaps selected0..3.
        code = bytes([37, 0, 1, 2, 254, 250, 255])
        rows = [record(0, [37, 0, 1, 2], "position", "object.position",
                       [actor, _immediate("x", 1), _immediate("y", 2)],
                       [{"kind": "fallthrough", "pc": 4, "in_range": True}], "actor"),
                record(4, [254, 250, 255], "goto", "control.goto",
                       [_literal("displacement", "s16", -6, width=16, access="read")],
                       [{"kind": "branch", "pc": 1, "in_range": True}], "control")]
        overlap = record(1, [0], "return", "control.return", [], [], "control")
        endpoint = 1
    else:
        code = bytes([60, 0, 0])
        rows = [record(0, [60, 0], "force.update", "object.force_update", [actor],
                       [{"kind": "fallthrough", "pc": 2, "in_range": True}], "actor"),
                record(2, [0], "return", "control.return", [], [], "control")]
        endpoint = 2
    source = {**SOURCE, "sha256": sha256(code).hexdigest(), "size": len(code)}
    page = {"schema": SCHEMA, "decoder": deepcopy(DECODER), "source": source,
            "evidence": "static_decode", "traversal": "linear", "start_pc": 0,
            "limit": len(rows), "next_pc": len(code), "stop": "end",
            "instructions": rows, "error": None}
    pages = [page]
    if case == "selected_overlap":
        pages.append({**deepcopy(page), "start_pc": 1, "limit": 1, "next_pc": 2,
                      "stop": "limit", "instructions": [overlap]})
    recipe = derive_bound_scene_recipe(
        code=code, pages=pages, source_mappings=[{
            "kind": "authored", "fragment_span": [0, len(code)], "source": None}],
        entry_pc=0, endpoint={"pc": endpoint, "phase": "after"},
        branch_choices={}, operand_bindings=[], actor_inputs=[])
    assert recipe["status"] == "blocked"
    assert recipe["endpoint"]["stop_reason"] == reason
    assert recipe["endpoint"]["reached"] is False
    _unobserved(recipe)
