"""Tests for the reduced world-map UIL record."""

from __future__ import annotations

from examples.civ.civ_world_uil import build_record, render_rows
from fdisbull.uil_record import execute_record, validate_record


def test_world_record_uses_zero_based_string_slots_for_rows():
    pixels = bytearray(320 * 200)
    pixels[0] = 2  # Grassland at (0, 0)
    pixels[23 * 320 + 7] = 11  # Jungle at (7, 23)
    pixels[5] = 2
    pixels[160 + 5] = 0x0A  # unit at (5, 0), owner 2
    record = build_record(bytes(pixels))
    assert validate_record(record)
    assert len(record["slots"]) == 50 + 7 + 4
    assert record["slots"][23]["type"] == "string"
    assert record["slots"][23]["name"] == "$map_row_23"
    assert len(record["slots"][23]["initial"]) == 80
    outcome = execute_record(record)
    assert outcome["complete"] is True
    rows = [event["text"] for event in outcome["events"] if event["op"] == "print_text"]
    assert len(rows) == 50
    assert rows[23] == record["slots"][23]["initial"]
    assert rows[23][7] == "J"
    assert rows[0][0] == "F"
    assert rows[0][5] == "F"  # uppercase marks the unit
    assert render_rows(record) == "\n".join(rows)


def test_world_record_keeps_terrain_and_layer_arrays():
    pixels = bytearray(320 * 200)
    pixels[0] = 2
    pixels[160] = 0x0B
    pixels[100 * 320] = 0x02
    pixels[150 * 320] = 0x01
    pixels[100 * 320 + 80] = 0x04
    record = build_record(bytes(pixels))
    slots = record["slots"]
    by_name = {slot["name"]: slot for slot in slots}
    assert by_name["$terrain"]["initial"][0] == 3
    assert by_name["$terrain_colour"]["initial"][0] == 2
    assert by_name["$unit_owner"]["initial"][0] == 3
    assert by_name["$unit_present"]["initial"][0] is True
    assert by_name["$improvements"]["initial"][0] == 0x12
    assert by_name["$known"]["initial"][0] == 0x04
    assert by_name["$minimap"]["initial"][0] == 0
