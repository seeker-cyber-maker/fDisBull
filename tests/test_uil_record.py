"""Tests for the indexed UIL record: strings, arrays and print_text."""

from __future__ import annotations

from copy import deepcopy

import pytest

from fdisbull.uil_record import (
    UILRecordInvalid,
    execute_record,
    initial_state,
    validate_record,
)


def record(*, slots=None, body=None):
    return {
        "format": "fdisbull-uil-record-1",
        "role": "uil",
        "slots": slots
        if slots is not None
        else [{"type": "u8", "initial": 0} for _ in range(23)]
        + [
            {"name": "$row23", "type": "string", "initial": "hello", "max_bytes": 16},
            {
                "name": "$map",
                "type": "array",
                "element": "u8",
                "length": 4,
                "initial": [1, 2, 3, 4],
            },
            {"name": "$x", "type": "u8", "initial": 0},
        ],
        "body": body
        if body is not None
        else [{"id": "print", "op": "print_text", "slot": 23, "x": 0, "y": 23}],
    }


def test_print_text_references_slot_23_by_zero_based_index():
    doc = record()
    assert validate_record(doc)
    outcome = execute_record(doc)
    assert outcome["complete"] is True
    assert outcome["events"] == [
        {
            "op": "print_text",
            "block_id": "print",
            "slot": 23,
            "text": "hello",
            "x": 0,
            "y": 23,
            "evidence": [],
        }
    ]
    assert initial_state(doc)[23] == "hello"


def test_strings_are_assignable_and_printable():
    doc = record(
        body=[
            {"id": "set", "op": "set", "slot": 23, "value": "bye"},
            {"id": "print", "op": "print_text", "slot": 23, "x": 4, "y": 5},
        ]
    )
    outcome = execute_record(doc)
    assert outcome["complete"] is True
    assert outcome["state"][23] == "bye"
    assert outcome["events"][0]["text"] == "bye"
    assert (outcome["events"][0]["x"], outcome["events"][0]["y"]) == (4, 5)


def test_array_cells_are_indexed_and_bounded():
    doc = record(
        body=[
            {"id": "set-cell", "op": "set_element", "slot": 24, "index": 2, "value": 9},
            {"id": "bad-cell", "op": "set_element", "slot": 24, "index": 4, "value": 1},
        ]
    )
    outcome = execute_record(doc, initial_state(doc))
    assert outcome["complete"] is False
    assert outcome["state"][24] == [1, 2, 3, 4]
    doc["body"] = doc["body"][:1]
    outcome = execute_record(doc)
    assert outcome["complete"] is True
    assert outcome["state"][24] == [1, 2, 9, 4]


def test_out_of_range_slot_is_rejected_before_execution():
    doc = record()
    doc["body"][0]["slot"] = 25
    with pytest.raises(UILRecordInvalid, match="print_text"):
        validate_record(doc)


def test_print_text_rejects_a_non_string_slot():
    doc = record()
    doc["body"][0]["slot"] = 0
    with pytest.raises(UILRecordInvalid, match="string slot"):
        validate_record(doc)


def test_string_max_bytes_is_enforced():
    doc = record()
    doc["body"] = [{"id": "set", "op": "set", "slot": 23, "value": "x" * 17}]
    with pytest.raises(UILRecordInvalid, match="max_bytes"):
        validate_record(doc)


def test_array_literal_type_is_checked():
    doc = record()
    doc["slots"][24]["initial"] = [1, 2, 3, "four"]
    with pytest.raises(UILRecordInvalid, match="element type"):
        validate_record(doc)


@pytest.mark.parametrize("typ", ["u8", "u16", "u32", "u64", "i8", "i16", "i32", "i64"])
def test_integer_slot_value_can_write_an_array_cell(typ):
    doc = record(
        slots=[
            {"type": "array", "element": "i16", "length": 2, "initial": [-1, 0]},
            {"type": typ, "initial": 9},
            {"type": "u8", "initial": 1},
        ],
        body=[
            {"id": "store", "op": "set_element", "slot": 0,
             "index": {"slot": 2}, "value": {"slot": 1}},
        ],
    )
    assert validate_record(doc)
    state = initial_state(doc)
    outcome = execute_record(doc, state)
    assert outcome["complete"] is True
    assert outcome["state"] == [[-1, 9], 9, 1]
    assert state == [[-1, 0], 9, 1]
    assert doc["slots"][0]["initial"] == [-1, 0]


@pytest.mark.parametrize("nested", [False, True], ids=["direct", "unselected-branch"])
@pytest.mark.parametrize(
    "block,error",
    [
        ({"id": "bad", "op": "print_text", "slot": 23,
          "x": {"slot": 24}, "y": 0}, "text coordinate"),
        ({"id": "bad", "op": "print_text", "slot": 23,
          "x": 0, "y": {"slot": 24}}, "text coordinate"),
        ({"id": "bad", "op": "require", "condition":
          {"op": "ge", "left": {"slot": 24}, "right": 0}}, "ge compares integers"),
        ({"id": "bad", "op": "require", "condition":
          {"op": "ge", "left": 0, "right": {"slot": 24}}}, "ge compares integers"),
        ({"id": "bad", "op": "require", "condition":
          {"op": "bit_test", "value": {"slot": 24}, "bit": 0}}, "bit test value"),
        ({"id": "bad", "op": "set_element", "slot": 24,
          "index": {"slot": 24}, "value": 9}, "array index"),
    ],
    ids=["text-x", "text-y", "ge-left", "ge-right", "bit-test", "array-index"],
)
def test_array_operand_is_rejected_before_any_execution(block, error, nested):
    body = [block]
    if nested:
        body = [{"id": "branch", "op": "if",
                 "condition": {"op": "eq", "left": 0, "right": 1},
                 "then": body, "else": []}]
    doc = record(body=body)
    before = deepcopy(doc)
    state = [deepcopy(slot["initial"]) for slot in doc["slots"]]
    with pytest.raises(UILRecordInvalid, match=error):
        validate_record(doc)
    outcome = execute_record(doc, state)
    assert outcome["complete"] is False
    assert outcome["events"] == []
    assert outcome["visited"] == []
    assert outcome["state"] == state
    assert doc == before


@pytest.mark.parametrize("typ,value", [("u16", 256), ("i16", -1)])
def test_integer_array_write_keeps_runtime_range_checks_and_atomic_refusal(typ, value):
    doc = record(
        slots=[
            {"type": "array", "element": "u8", "length": 1, "initial": [5]},
            {"type": typ, "initial": value},
            {"type": "string", "initial": "before", "max_bytes": 6},
        ],
        body=[
            {"id": "print", "op": "print_text", "slot": 2, "x": 0, "y": 0},
            {"id": "store", "op": "set_element", "slot": 0,
             "index": 0, "value": {"slot": 1}},
        ],
    )
    assert validate_record(doc)
    state = initial_state(doc)
    outcome = execute_record(doc, state)
    assert outcome["complete"] is False
    assert outcome["error"] == "array value out of range"
    assert outcome["events"] == []
    assert outcome["state"] == [[5], value, "before"]
    assert state == [[5], value, "before"]


def test_boolean_array_accepts_boolean_literals_and_slots():
    doc = record(
        slots=[
            {"type": "array", "element": "bool", "length": 2,
             "initial": [False, True]},
            {"type": "bool", "initial": False},
        ],
        body=[
            {"id": "literal", "op": "set_element", "slot": 0,
             "index": 0, "value": True},
            {"id": "slot", "op": "set_element", "slot": 0,
             "index": 1, "value": {"slot": 1}},
        ],
    )
    outcome = execute_record(doc)
    assert outcome["complete"] is True
    assert outcome["state"] == [[True, False], False]


@pytest.mark.parametrize("element,typ,value", [("u8", "bool", True), ("bool", "u8", 1)])
def test_array_write_does_not_coerce_between_booleans_and_integers(element, typ, value):
    doc = record(
        slots=[
            {"type": "array", "element": element, "length": 1,
             "initial": [False if element == "bool" else 0]},
            {"type": typ, "initial": value},
        ],
        body=[{"id": "store", "op": "set_element", "slot": 0,
               "index": 0, "value": {"slot": 1}}],
    )
    with pytest.raises(UILRecordInvalid, match="incompatible array value"):
        validate_record(doc)
