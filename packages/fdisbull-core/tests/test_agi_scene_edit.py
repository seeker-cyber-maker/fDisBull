"""Source-bound literal-position plans, using independently authored views.

These checks describe a static instruction edit, not a predicted replay result.
Neither the planner nor the consumer creates the expected fixture state.
"""
from copy import deepcopy
import hashlib

import pytest

from fdisbull_core.agi_scene import SceneInputError, plan_literal_position_edit


# assignn(v1,7); position(0,10,20); position(1,30,40); return.
CODE = bytes.fromhex("03010725000a1425011e2800")
EDITED_ACTOR_ZERO = bytes.fromhex("0301072500323c25011e2800")
EDITED_ACTOR_ONE = bytes.fromhex("03010725000a14250100ff00")
PROFILE = "agi-2917-scalar-position-pilot-1"


def source(code):
    return {"sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
            "logic_id": 0, "profile": PROFILE}


def position(x=0, y=0):
    return {"x": x, "y": y, "prev_x": x, "prev_y": y}


def authored_view():
    witnesses = [
        {"kind": "position", "seq": 1, "retired": 2, "control_generation": 3,
         "pc": 3, "opcode": 37, "bytes": [37, 0, 10, 20], "next_pc": 7,
         "actor": 0, "before": position(), "after": position(10, 20),
         "note": {"labels": ["authored witness"]}},
        {"kind": "position", "seq": 2, "retired": 3, "control_generation": 3,
         "pc": 7, "opcode": 37, "bytes": [37, 1, 30, 40], "next_pc": 11,
         "actor": 1, "before": position(), "after": position(30, 40)},
    ]
    actors = [{"id": i, **position(), "witness": None} for i in range(16)]
    actors[0].update(position(10, 20), witness=witnesses[0])
    actors[1].update(position(30, 40), witness=witnesses[1])
    return {
        "schema": "fdisbull-agi-scene-view-1", "session_id": "authored-edit-view",
        "source": source(CODE),
        "checkpoint": {"epoch": 1, "control_generation": 3, "retired": 4,
                       "eligible": 2, "invocation": 1},
        "guest": {"pc": 12, "status": "return", "fault": None},
        "actors": actors,
        "coverage": {
            "history_complete_since_attach": True,
            "history_start": {"epoch": 1, "control_generation": 3, "retired": 0,
                              "eligible": 0, "invocation": 0},
            "gap_count": 0, "last_gap": None, "scene_enabled": True,
        },
    }


def replace(view, path, value):
    current = view
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def plan(view=None, code=CODE, **arguments):
    return plan_literal_position_edit(
        code, authored_view() if view is None else view,
        **{"actor": 0, "x": 50, "y": 60, **arguments},
    )


def test_plan_binds_exact_source_instruction_and_changes_only_coordinate_bytes():
    view = authored_view()
    before = deepcopy(view)
    result = plan(view)
    assert result == {
        "schema": "fdisbull-agi-literal-position-edit-1",
        "session_id": "authored-edit-view", "checkpoint": view["checkpoint"],
        "source": source(CODE), "actor": 0,
        "witness": view["actors"][0]["witness"], "offset": 3, "length": 4,
        "expected_bytes": [37, 0, 10, 20], "replacement_bytes": [37, 0, 50, 60],
        "requested_position": {"x": 50, "y": 60},
        "candidate_source": source(EDITED_ACTOR_ZERO), "changed": True,
        "write_performed": False, "scope": "static_instruction",
    }
    assert CODE[result["offset"]:result["offset"] + result["length"]] == bytes(result["expected_bytes"])
    patched = CODE[:3] + bytes(result["replacement_bytes"]) + CODE[7:]
    assert patched == EDITED_ACTOR_ZERO
    assert [i for i, pair in enumerate(zip(CODE, patched)) if pair[0] != pair[1]] == [5, 6]
    assert view == before


def test_selected_actor_and_byte_boundary_coordinates_preserve_other_instructions():
    result = plan(actor=1, x=0, y=255)
    assert result["offset"] == 7 and result["actor"] == 1
    assert result["expected_bytes"] == [37, 1, 30, 40]
    assert result["replacement_bytes"] == [37, 1, 0, 255]
    assert result["candidate_source"] == source(EDITED_ACTOR_ONE)
    assert CODE[:7] + bytes(result["replacement_bytes"]) + CODE[11:] == EDITED_ACTOR_ONE


def test_same_coordinates_produce_an_explicit_noop_plan():
    result = plan(x=10, y=20)
    assert result["changed"] is False and result["write_performed"] is False
    assert result["expected_bytes"] == result["replacement_bytes"] == [37, 0, 10, 20]
    assert result["candidate_source"] == result["source"] == source(CODE)
    assert result["scope"] == "static_instruction"


def test_plan_and_captured_view_do_not_share_mutable_records():
    view = authored_view()
    result = plan(view)
    expected = deepcopy(result)
    view["source"]["sha256"] = "00" * 32
    view["checkpoint"]["eligible"] = 99
    view["actors"][0]["witness"]["note"]["labels"][0] = "changed input"
    view["actors"][0]["witness"]["after"]["x"] = 99
    assert result == expected
    mutated_input = deepcopy(view)
    result["source"]["size"] = 99
    result["checkpoint"]["retired"] = 99
    result["witness"]["bytes"][2] = 99
    result["witness"]["note"]["labels"].append("changed result")
    assert view == mutated_input


def test_harmless_stopped_control_change_does_not_expire_a_valid_witness():
    view = authored_view()
    view["checkpoint"]["control_generation"] = 6
    view["coverage"]["scene_enabled"] = False
    result = plan(view)
    assert result["checkpoint"]["control_generation"] == 6
    assert result["witness"]["control_generation"] == 3
    assert result["replacement_bytes"] == [37, 0, 50, 60]


def test_later_same_coordinate_assignment_does_not_change_the_static_edit_target():
    code = bytes.fromhex("25000a1425000a1400")
    view = authored_view()
    view["source"] = source(code)
    view["checkpoint"].update(retired=3, eligible=1)
    view["guest"]["pc"] = 9
    view["actors"][1].update(position(), witness=None)
    witness = view["actors"][0]["witness"]
    witness.update(pc=0, next_pc=4, retired=1)
    result = plan(view, code)
    assert result["offset"] == 0 and result["scope"] == "static_instruction"
    assert result["replacement_bytes"] == [37, 0, 50, 60]
    # The later literal is deliberately untouched. A replay may overwrite the
    # requested coordinates; the planner makes no final-state prediction.
    candidate = bytes(result["replacement_bytes"]) + code[4:]
    assert candidate == bytes.fromhex("2500323c25000a1400")
    assert result["candidate_source"] == source(candidate)


@pytest.mark.parametrize("arguments", [
    {"actor": True}, {"actor": -1}, {"actor": 16},
    {"x": True}, {"x": -1}, {"x": 256},
    {"y": True}, {"y": -1}, {"y": 256}, {"x": 1.5},
], ids=["actor-bool", "actor-negative", "actor-range", "x-bool", "x-negative",
        "x-range", "y-bool", "y-negative", "y-range", "coordinate-float"])
def test_actor_and_coordinate_arguments_require_bounded_integers(arguments):
    view = authored_view()
    before = deepcopy(view)
    with pytest.raises(SceneInputError):
        plan(view, **arguments)
    assert view == before


@pytest.mark.parametrize("bad_code", [CODE.hex(), bytearray(CODE)], ids=["text", "mutable-bytes"])
def test_source_input_requires_immutable_bytes(bad_code):
    with pytest.raises(SceneInputError):
        plan(code=bad_code)


def test_changed_unrelated_source_byte_invalidates_the_plan():
    changed = bytes.fromhex("03020725000a1425011e2800")
    assert changed[3:7] == CODE[3:7]
    with pytest.raises(SceneInputError):
        plan(code=changed)


@pytest.mark.parametrize("field,value", [
    ("sha256", "ab" * 32), ("size", 13), ("profile", "another-profile"), ("logic_id", 1),
])
def test_source_identity_tuple_must_match_the_supported_program(field, value):
    view = authored_view()
    view["source"][field] = value
    with pytest.raises(SceneInputError):
        plan(view)


@pytest.mark.parametrize("field,value", [
    ("history_complete_since_attach", False),
    ("history_complete_since_attach", 1),
    ("gap_count", 1), ("last_gap", {"reason": "scene_records_lost"}),
    ("scene_enabled", 1),
])
def test_incomplete_or_inconsistent_history_cannot_authorize_an_edit(field, value):
    view = authored_view()
    view["coverage"][field] = value
    with pytest.raises(SceneInputError):
        plan(view)


@pytest.mark.parametrize("path,value", [
    (("schema",), "fdisbull-agi-native-state-1"),
    (("session_id",), ""),
    (("actors", 1, "id"), 0),
    (("actors", 0, "x"), True),
    (("guest", "status"), "running"),
    (("guest", "status"), "ready"),
], ids=["wrong-schema", "empty-session", "duplicate-actor", "coordinate-bool", "running",
        "ready-with-witness"])
def test_malformed_scene_views_are_rejected(path, value):
    view = authored_view()
    replace(view, path, value)
    with pytest.raises(SceneInputError):
        plan(view)


def test_actor_inventory_must_be_complete():
    view = authored_view()
    view["actors"].pop()
    with pytest.raises(SceneInputError):
        plan(view)


def test_selected_actor_requires_an_observed_instruction_witness():
    with pytest.raises(SceneInputError):
        plan(actor=2)


def test_position_v_is_refused_even_with_matching_source_and_current_coordinates():
    code = bytes.fromhex("03010726000a1425011e2800")
    view = authored_view()
    view["source"] = source(code)
    witness = view["actors"][0]["witness"]
    witness["opcode"] = 38
    witness["bytes"] = [38, 0, 10, 20]
    with pytest.raises(SceneInputError):
        plan(view, code)


@pytest.mark.parametrize("field,value", [
    ("kind", "retire"), ("pc", 4), ("next_pc", 8),
    ("actor", 1), ("opcode", 38), ("bytes", [37, 0, 11, 20]),
    ("bytes", [37, 0, 10]), ("before", position(10, 20)),
    ("before", {"x": 0, "y": 0, "prev_x": 0}),
], ids=["kind", "source-offset", "successor", "actor", "opcode", "source-span",
        "width", "not-a-change", "incomplete-before"])
def test_witness_must_describe_the_selected_literal_instruction(field, value):
    view = authored_view()
    view["actors"][0]["witness"][field] = value
    with pytest.raises(SceneInputError):
        plan(view)


def test_matching_fake_current_position_cannot_override_literal_operands():
    view = authored_view()
    view["actors"][0].update(position(11, 20))
    view["actors"][0]["witness"]["after"] = position(11, 20)
    with pytest.raises(SceneInputError):
        plan(view)


def test_current_position_must_match_the_witness_after_state():
    view = authored_view()
    view["actors"][0].update(position(12, 20))
    with pytest.raises(SceneInputError):
        plan(view)


@pytest.mark.parametrize("path,value", [
    (("actors", 0, "witness", "seq"), 3),
    (("actors", 0, "witness", "retired"), 5),
    (("actors", 0, "witness", "control_generation"), 4),
    (("actors", 0, "witness", "control_generation"), 2),
    (("coverage", "history_start", "eligible"), 1),
    (("coverage", "history_start", "retired"), 2),
    (("coverage", "history_start", "epoch"), 0),
    (("coverage", "history_start", "invocation"), 2),
    (("coverage", "history_start", "invocation"), 1),
    (("checkpoint", "invocation"), 0),
    (("checkpoint", "retired"), True),
], ids=["future-sequence", "future-retirement", "future-generation", "old-generation",
        "sequence-at-attachment", "retirement-at-attachment", "epoch-mismatch",
        "invocation-regression", "no-new-invocation", "no-invocation", "boolean-counter"])
def test_witness_and_history_temporal_bounds_are_enforced(path, value):
    view = authored_view()
    replace(view, path, value)
    with pytest.raises(SceneInputError):
        plan(view)
