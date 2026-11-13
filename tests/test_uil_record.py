"""Tests for the indexed UIL record: strings, arrays and print_text."""

from __future__ import annotations

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
