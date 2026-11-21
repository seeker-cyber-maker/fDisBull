"""Independent authored expectations for an explicit position.v override.

The operation converts one static variable-reading instruction to a literal
instruction. Historical read values come from its witnessed effect, while a
fresh execution must establish the eventual scene. No production consumer or
decoder constructs these fixture observations or expected candidate bytes.
"""
from copy import deepcopy
import hashlib

import pytest

from fdisbull_core.agi_scene import (
    SceneInputError,
    plan_literal_position_edit,
    plan_variable_position_override,
)


# v7=10; v8=20; position.v(0,v7,v8); v7=70; v8=80;
# position.v(1,v7,v8); return. PCs: 0,3,6,10,13,16,20.
CODE = bytes.fromhex("03070a030814260007080307460308502601070800")
OVERRIDDEN_ZERO = bytes.fromhex("03070a03081425001e280307460308502601070800")
OVERRIDDEN_ONE = bytes.fromhex("03070a03081426000708030746030850250100ff00")
PROFILE = "agi-2917-scalar-position-pilot-1"


def source(code):
    return {"sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
            "logic_id": 0, "profile": PROFILE}


def position(x=0, y=0):
    return {"x": x, "y": y, "prev_x": x, "prev_y": y}


def authored_view():
    witnesses = [
        {"kind": "position", "seq": 1, "retired": 3, "control_generation": 3,
         "pc": 6, "opcode": 38, "bytes": [38, 0, 7, 8], "next_pc": 10,
         "actor": 0, "before": position(), "after": position(10, 20),
         "annotation": {"labels": ["authored witness"]}},
        {"kind": "position", "seq": 2, "retired": 6, "control_generation": 3,
         "pc": 16, "opcode": 38, "bytes": [38, 1, 7, 8], "next_pc": 20,
         "actor": 1, "before": position(), "after": position(70, 80)},
    ]
    actors = [{"id": i, **position(), "witness": None} for i in range(16)]
    actors[0].update(position(10, 20), witness=witnesses[0])
    actors[1].update(position(70, 80), witness=witnesses[1])
    return {
        "schema": "fdisbull-agi-scene-view-1", "session_id": "authored-variable-view",
        "source": source(CODE),
        "checkpoint": {"epoch": 1, "control_generation": 3, "retired": 7,
                       "eligible": 2, "invocation": 1},
        "guest": {"pc": 21, "status": "return", "fault": None},
        "actors": actors,
        "coverage": {
            "history_complete_since_attach": True,
            "history_start": {"epoch": 1, "control_generation": 3, "retired": 0,
                              "eligible": 0, "invocation": 0},
            "gap_count": 0, "last_gap": None, "scene_enabled": True,
        },
    }


def override(view=None, code=CODE, **arguments):
    return plan_variable_position_override(
        code, authored_view() if view is None else view,
        **{"actor": 0, "x": 30, "y": 40, **arguments},
    )


def replace(view, path, value):
    current = view
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def alias_view():
    # v9=25; position.v(0,v9,v9); position.v(1,v9,v9); return.
    code = bytes.fromhex("030919260009092601090900")
    view = authored_view()
    view["source"] = source(code)
    view["checkpoint"].update(retired=4)
    view["guest"]["pc"] = 12
    for index, pc, retired in ((0, 3, 2), (1, 7, 3)):
        actor = view["actors"][index]
        actor.update(position(25, 25))
        actor["witness"].update(pc=pc, next_pc=pc + 4, retired=retired,
                                bytes=[38, index, 9, 9], after=position(25, 25))
    return code, view


def test_override_binds_exact_source_and_explicitly_replaces_variable_reads():
    view = authored_view()
    before = deepcopy(view)
    result = override(view)
    assert result == {
        "schema": "fdisbull-agi-variable-position-override-1",
        "session_id": "authored-variable-view", "checkpoint": view["checkpoint"],
        "source": source(CODE), "actor": 0, "witness": view["actors"][0]["witness"],
        "offset": 6, "length": 4, "expected_bytes": [38, 0, 7, 8],
        "replacement_bytes": [37, 0, 30, 40],
        "requested_position": {"x": 30, "y": 40},
        "candidate_source": source(OVERRIDDEN_ZERO),
        "changed": True, "write_performed": False, "scope": "static_instruction",
        "binding_change": {"from": "variable", "to": "literal"},
        "variable_reads": {"x": {"index": 7, "value": 10},
                           "y": {"index": 8, "value": 20}},
        "read_value_basis": "position_witness",
        "requested_position_matches_observed": False,
    }
    candidate = CODE[:6] + bytes(result["replacement_bytes"]) + CODE[10:]
    assert candidate == OVERRIDDEN_ZERO
    assert [i for i, (a, b) in enumerate(zip(CODE, candidate)) if a != b] == [6, 8, 9]
    assert candidate[:6] == CODE[:6] and candidate[10:] == CODE[10:]
    assert view == before


def test_read_values_are_the_historical_effect_not_variable_ids_or_later_values():
    result = override()
    # The authored code sets these variables to 70/80 after the selected event.
    # The plan's historical read values remain 10/20 and the indices remain 7/8.
    assert result["variable_reads"] == {
        "x": {"index": 7, "value": 10}, "y": {"index": 8, "value": 20},
    }
    assert result["witness"]["retired"] == 3
    assert result["checkpoint"]["retired"] == 7


def test_selecting_other_actor_uses_its_own_witness_and_boundary_coordinates():
    result = override(actor=1, x=0, y=255)
    assert result["offset"] == 16 and result["actor"] == 1
    assert result["expected_bytes"] == [38, 1, 7, 8]
    assert result["replacement_bytes"] == [37, 1, 0, 255]
    assert result["variable_reads"] == {
        "x": {"index": 7, "value": 70}, "y": {"index": 8, "value": 80},
    }
    assert result["candidate_source"] == source(OVERRIDDEN_ONE)


def test_same_observed_coordinates_still_change_the_source_binding():
    result = override(x=10, y=20)
    expected = bytes.fromhex("03070a03081425000a140307460308502601070800")
    assert result["requested_position_matches_observed"] is True
    assert result["changed"] is True and result["write_performed"] is False
    assert result["replacement_bytes"] == [37, 0, 10, 20]
    assert result["candidate_source"] == source(expected)
    assert result["candidate_source"]["sha256"] != result["source"]["sha256"]


def test_aliased_variable_reads_can_be_overridden_with_distinct_literals():
    code, view = alias_view()
    result = override(view, code)
    assert result["variable_reads"] == {
        "x": {"index": 9, "value": 25}, "y": {"index": 9, "value": 25},
    }
    assert result["expected_bytes"] == [38, 0, 9, 9]
    assert result["replacement_bytes"] == [37, 0, 30, 40]
    assert result["candidate_source"] == source(bytes.fromhex("03091925001e282601090900"))


def test_alias_rule_constrains_the_after_values_not_the_previous_actor_position():
    # position(0,2,3); v9=25; position.v(0,v9,v9); return.
    code = bytes.fromhex("250002030309192600090900")
    _, view = alias_view()
    view["source"] = source(code)
    view["actors"][1].update(position(), witness=None)
    view["actors"][0]["witness"].update(pc=7, next_pc=11, seq=2, retired=3,
                                         before=position(2, 3))
    result = override(view, code)
    assert result["offset"] == 7
    assert result["variable_reads"]["x"]["value"] == 25
    assert result["variable_reads"]["y"]["value"] == 25


def test_aliased_variable_cannot_have_two_different_historical_read_values():
    code, view = alias_view()
    view["actors"][0].update(position(25, 26))
    view["actors"][0]["witness"]["after"] = position(25, 26)
    with pytest.raises(SceneInputError):
        override(view, code)


def test_valid_witness_survives_harmless_stopped_controls():
    view = authored_view()
    view["checkpoint"]["control_generation"] = 6
    view["coverage"]["scene_enabled"] = False
    result = override(view)
    assert result["witness"]["control_generation"] == 3
    assert result["checkpoint"]["control_generation"] == 6


def test_result_and_input_have_no_shared_mutable_records():
    view = authored_view()
    result = override(view)
    expected = deepcopy(result)
    view["source"]["sha256"] = "00" * 32
    view["checkpoint"]["eligible"] = 99
    view["actors"][0]["witness"]["annotation"]["labels"].append("input changed")
    view["actors"][0]["witness"]["after"]["x"] = 99
    assert result == expected
    input_after = deepcopy(view)
    result["variable_reads"]["x"]["index"] = 42
    result["variable_reads"]["x"]["value"] = 42
    result["witness"]["bytes"][2] = 42
    result["witness"]["annotation"]["labels"].append("result changed")
    result["checkpoint"]["retired"] = 99
    assert view == input_after


def test_existing_literal_api_does_not_silently_convert_position_v():
    with pytest.raises(SceneInputError):
        plan_literal_position_edit(CODE, authored_view(), actor=0, x=30, y=40)


def test_variable_override_api_requires_a_variable_reading_instruction():
    code = bytes.fromhex("03070a03081425000a140307460308502601070800")
    view = authored_view()
    view["source"] = source(code)
    view["actors"][0]["witness"].update(opcode=37, bytes=[37, 0, 10, 20])
    with pytest.raises(SceneInputError):
        override(view, code)


@pytest.mark.parametrize("arguments", [
    {"actor": True}, {"actor": -1}, {"actor": 16},
    {"x": True}, {"x": -1}, {"x": 256}, {"y": True}, {"y": 256},
], ids=["actor-bool", "actor-negative", "actor-range", "x-bool", "x-negative",
        "x-range", "y-bool", "y-range"])
def test_override_arguments_require_bounded_integers(arguments):
    with pytest.raises(SceneInputError):
        override(**arguments)


@pytest.mark.parametrize("bad_code", [bytearray(CODE), b"", b"\x00" * 65537],
                         ids=["mutable", "empty", "oversized"])
def test_raw_source_must_be_immutable_and_bounded(bad_code):
    with pytest.raises(SceneInputError):
        override(code=bad_code)


def test_unrelated_source_byte_change_invalidates_an_otherwise_matching_witness():
    changed = bytes.fromhex("03070b030814260007080307460308502601070800")
    assert changed[6:10] == CODE[6:10]
    with pytest.raises(SceneInputError):
        override(code=changed)


@pytest.mark.parametrize("path,value", [
    (("source", "size"), 20),
    (("source", "profile"), "unknown-profile"),
    (("coverage", "history_complete_since_attach"), False),
    (("coverage", "gap_count"), 1),
    (("coverage", "last_gap"), {"reason": "lost"}),
    (("checkpoint", "epoch"), 2),
    (("checkpoint", "invocation"), 0),
    (("guest", "status"), "ready"),
    (("actors", 0, "witness"), None),
    (("actors", 0, "x"), 11),
    (("actors", 0, "witness", "seq"), 0),
    (("actors", 0, "witness", "retired"), 8),
    (("actors", 0, "witness", "control_generation"), 4),
    (("actors", 0, "witness", "next_pc"), 11),
    (("actors", 0, "witness", "bytes"), [38, 0, 7]),
    (("actors", 0, "witness", "bytes"), [38, 0, 7, True]),
    (("actors", 0, "witness", "bytes"), [38, 0, 8, 7]),
    (("actors", 0, "witness", "actor"), 1),
], ids=["source-size", "profile", "incomplete-history", "gap-count", "gap-record",
        "epoch", "no-new-invocation", "ready-with-witness", "missing-witness",
        "current-position", "old-sequence", "future-retirement", "future-generation",
        "next-pc", "short-instruction", "boolean-variable-index", "different-variable-indices",
        "different-actor"])
def test_source_history_time_and_selected_witness_binding_are_required(path, value):
    view = authored_view()
    replace(view, path, value)
    before = deepcopy(view)
    with pytest.raises(SceneInputError):
        override(view)
    assert view == before
