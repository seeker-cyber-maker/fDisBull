"""Authored source fixtures for scene extraction; no original game assets."""
from __future__ import annotations

import copy
import hashlib

import pytest

from fdisbull._zork_scene_symbols import SCENE_SYMBOLS
from fdisbull.zork_scenes import (
    DIRECTIONS, _Evidence, _associate_scenes, _lower_exit, _object_ids, _objects, _routine,
    recover_scenes,
)


def _ztext(text):
    """A deliberately small independent encoder for authored lowercase prose."""
    codes = [0 if char == " " else ord(char) - ord("a") + 6 for char in text]
    codes.extend([5] * (-len(codes) % 3))
    words = [(codes[i] << 10) | (codes[i + 1] << 5) | codes[i + 2]
             for i in range(0, len(codes), 3)]
    words[-1] |= 0x8000
    return b"".join(word.to_bytes(2, "big") for word in words)


@pytest.fixture
def scene_image():
    """Two rooms and one door with all five compiler exit conventions."""
    data = bytearray(2048)
    data[0] = 3
    data[24:26] = (600).to_bytes(2, "big")
    # Two parented rooms plus a door. Object records start after 31 defaults.
    for number, name, parent, properties in (
        (1, "hall", 0, [(31, b"\x02"), (30, (700 // 2).to_bytes(2, "big")),
                         (29, (900 // 2).to_bytes(2, "big") + b"\x00"),
                         (28, b"\x02\x10\x00\x00"),
                         (27, b"\x02\x03\x00\x00\x00")]),
        (2, "garden", 0, []),
        (3, "gate", 0, []),
    ):
        record = 64 + 62 + 9 * (number - 1)
        table = 200 + (number - 1) * 100
        encoded = _ztext(name)
        data[record + 4] = parent
        data[record + 7:record + 9] = table.to_bytes(2, "big")
        data[table] = len(encoded) // 2
        data[table + 1:table + 1 + len(encoded)] = encoded
        cursor = table + 1 + len(encoded)
        for number_, value in properties:
            data[cursor] = ((len(value) - 1) << 5) | number_
            data[cursor + 1:cursor + 1 + len(value)] = value
            cursor += 1 + len(value)
        data[cursor] = 0
    text = _ztext("the path is blocked")
    data[700:700 + len(text)] = text
    data[900:904] = bytes([1, 0, 7, 0xB0])  # one local initialized to seven; return true
    return bytes(data)


def _fixture_objects(image):
    return _objects(image, table=64, count=3, dynamic_end=600)


def _decode(image, prop_number):
    objects = _fixture_objects(image)
    evidence = _Evidence(image, 600)
    definition, binding = _lower_exit(
        image, objects[1]["properties"][prop_number],
        identity="hall.exit." + DIRECTIONS[prop_number],
        scene_ids={1: "hall", 2: "garden"}, fact_ids={16: "passage_enabled"},
        door_ids={3: "gate"}, handler="authored_exit", evidence=evidence)
    return definition, binding, evidence


def test_object_catalog_reads_names_properties_and_mutable_fields(scene_image):
    objects = _fixture_objects(scene_image)
    assert [x["name"] for x in objects.values()] == ["hall", "garden", "gate"]
    assert list(objects[1]["properties"]) == [31, 30, 29, 28, 27]
    assert objects[1]["properties"][31]["bytes"] == "02"
    assert objects[1]["record"] == 126
    assert objects[1]["parent"] == 0


def test_exit_destination_is_resolved_once_to_a_scene_name(scene_image):
    definition, binding, _ = _decode(scene_image, 31)
    assert definition == {"id": "hall.exit.north", "kind": "direct", "destination": "garden"}
    assert binding["destination"] == 2
    assert "address" not in definition


def test_blocked_exit_extracts_the_actual_resource_without_a_hidden_newline(scene_image):
    definition, binding, evidence = _decode(scene_image, 30)
    assert definition == {"id": "hall.exit.east", "kind": "blocked",
                          "failure_resource": "hall.exit.east.refusal"}
    assert evidence.resources[definition["failure_resource"]] == "the path is blocked"
    assert binding["size"] == 2
    assert evidence.resource_bindings[definition["failure_resource"]]["address"] == 700


def test_routine_exit_gets_a_resolved_entry_but_stays_explicit_residual(scene_image):
    definition, binding, _ = _decode(scene_image, 29)
    assert definition == {"id": "hall.exit.west", "kind": "routine", "residual": "authored_exit"}
    assert binding["routine"] == {"kind": "routine", "packed": 450,
                                  "header": 900, "entry": 903, "locals": [7]}
    assert "destination" not in definition


def test_live_global_selector_is_a_named_condition_not_its_initial_value(scene_image):
    definition, binding, _ = _decode(scene_image, 28)
    assert definition == {"id": "hall.exit.south", "kind": "conditional",
                          "destination": "garden", "fact": "passage_enabled"}
    assert binding["fact"] == "passage_enabled"
    assert binding["failure_packed"] == 0
    assert "initial" not in definition


def test_open_door_selector_is_a_named_entity_not_a_stack_operand(scene_image):
    definition, binding, _ = _decode(scene_image, 27)
    assert definition == {"id": "hall.exit.northeast", "kind": "door",
                          "destination": "garden", "door": "gate"}
    assert binding["door"] == "gate"
    assert binding["failure_packed"] == 0


@pytest.mark.parametrize("prop_number", [28, 27])
def test_conditional_and_door_refusal_text_is_extracted_when_present(scene_image, prop_number):
    obj = _fixture_objects(scene_image)[1]
    at = obj["properties"][prop_number]["address"]
    changed = bytearray(scene_image)
    changed[at + 2:at + 4] = (350).to_bytes(2, "big")
    definition, binding, evidence = _decode(bytes(changed), prop_number)
    assert evidence.resources[definition["failure_resource"]] == "the path is blocked"
    assert binding["failure_packed"] == 350


@pytest.mark.parametrize("prop_number", [29, 27])
def test_unqualified_layout_padding_is_not_silently_dropped(scene_image, prop_number):
    prop = _fixture_objects(scene_image)[1]["properties"][prop_number]
    changed = bytearray(scene_image)
    changed[prop["address"] + prop["size"] - 1] = 1
    with pytest.raises(ValueError, match="padding"):
        _decode(bytes(changed), prop_number)


@pytest.mark.parametrize("prop_number,index,value,error", [
    (31, 0, 3, "destination"),
    (28, 1, 17, "selector"),
    (27, 1, 2, "selector"),
])
def test_unresolved_references_are_not_invented(scene_image, prop_number, index, value, error):
    prop = _fixture_objects(scene_image)[1]["properties"][prop_number]
    changed = bytearray(scene_image)
    changed[prop["address"] + index] = value
    with pytest.raises(ValueError, match=error):
        _decode(bytes(changed), prop_number)


def test_exit_source_extent_must_match_the_record_being_lifted(scene_image):
    prop = copy.deepcopy(_fixture_objects(scene_image)[1]["properties"][31])
    prop["bytes"] = "01"
    with pytest.raises(ValueError, match="source extent"):
        _lower_exit(scene_image, prop, identity="hall.exit.north", scene_ids={1: "hall", 2: "garden"},
                    fact_ids={}, door_ids={}, handler=None, evidence=_Evidence(scene_image, 600))


def test_property_pointer_cannot_reinterpret_record_bytes_as_scene_data(scene_image):
    changed = bytearray(scene_image)
    changed[133:135] = (126).to_bytes(2, "big")
    with pytest.raises(ValueError, match="overlaps records"):
        _fixture_objects(bytes(changed))


def test_property_headers_must_be_descending_without_duplicate_fields(scene_image):
    objects = _fixture_objects(scene_image)
    changed = bytearray(scene_image)
    at = objects[1]["properties"][30]["header"]
    changed[at] = (1 << 5) | 31
    with pytest.raises(ValueError, match="descending"):
        _fixture_objects(bytes(changed))


def test_short_name_layout_mismatch_is_rejected(scene_image):
    changed = bytearray(scene_image)
    changed[200] += 1
    with pytest.raises(ValueError, match="short-name length"):
        _fixture_objects(bytes(changed))


@pytest.mark.parametrize("packed", [0, 1, 1024, 65535, True, -1])
def test_invalid_callback_headers_are_refused(scene_image, packed):
    with pytest.raises(ValueError):
        _routine(scene_image, packed)


def test_callback_local_limit_and_instruction_entry_are_both_checked(scene_image):
    changed = bytearray(scene_image)
    changed[900] = 16
    with pytest.raises(ValueError, match="local header"):
        _routine(bytes(changed), 450)
    changed[900] = 0
    changed[901] = 0xB4  # valid nop entry
    assert _routine(bytes(changed), 450)["entry"] == 901


def test_runtime_structure_guards_do_not_freeze_parent_or_attributes(scene_image):
    objects = _fixture_objects(scene_image)
    evidence = _Evidence(scene_image, 600)
    guards = evidence.structure(objects[1])
    record = objects[1]["record"]
    assert all(not (evidence.witnesses[name]["start"] < record + 7
                    and evidence.witnesses[name]["end"] > record)
               for name in guards)
    assert any(evidence.witnesses[name]["start"] == record + 7 for name in guards)


def test_text_witnesses_include_abbreviation_pointer_and_expansion(scene_image):
    changed = bytearray(scene_image)
    changed[600:602] = (700 // 2).to_bytes(2, "big")
    # abbreviation group 1, entry 0, plus an unused alphabet shift padding
    changed[800:802] = ((1 << 10) | 5 | 0x8000).to_bytes(2, "big")
    evidence = _Evidence(bytes(changed), 600)
    evidence.text("message", 800)
    assert evidence.resources["message"] == "the path is blocked"
    spans = {(x["start"], x["end"]) for x in evidence.witnesses.values()}
    assert (800, 802) in spans
    assert (600, 602) in spans
    assert any(start == 700 for start, end in spans)


def test_evidence_is_source_bound_not_a_hash_only_label(scene_image):
    evidence = _Evidence(scene_image, 600)
    evidence.add("named", 700, 702, "authored packed text")
    witness = evidence.witnesses["named"]
    assert witness["bytes"] == scene_image[700:702].hex()
    assert witness["sha256"] == hashlib.sha256(scene_image[700:702]).hexdigest()
    with pytest.raises(ValueError, match="Conflicting"):
        evidence.add("named", 702, 704, "different extent")


def test_sanitized_profile_is_a_closed_named_graph_with_explicit_unresolved_calls():
    names = {row[0] for row in SCENE_SYMBOLS}
    numbers = {row[1] for row in SCENE_SYMBOLS}
    assert len(names) == len(numbers) == 110
    exits = [exit_ for row in SCENE_SYMBOLS for exit_ in row[4]]
    assert len(exits) == 352
    assert all(destination in names for _, kind, destination, _ in exits
               if kind in ("direct", "conditional", "door"))
    assert sum(kind == "routine" for _, kind, _, _ in exits) == 7
    assert len({qualifier for _, kind, _, qualifier in exits if kind == "routine"}) == 4
    assert sum(direction == "land" for direction, _, _, _ in exits) == 6


def test_object_metadata_ids_disambiguate_duplicate_names_without_source_offsets():
    objects = {1: {"name": "garden"}, 2: {"name": "garden"}, 3: {"name": "gate"}}
    result = _object_ids(objects, {1: "garden"})
    assert result[1] == "garden"
    assert result[2] == "garden_2"
    assert result[3] == "gate"
    assert set(result) == set(objects)


def test_graph_association_resolves_duplicate_rooms_without_numeric_hints():
    # All titles are deliberately identical; profile object hints deliberately
    # disagree. Only the graph can establish entry -> middle -> endpoint.
    def room(target):
        return {"parent": 99, "name": "identical", "properties": {} if target is None else {
            31: {"size": 1, "bytes": bytes([target]).hex()}}}
    objects = {20: room(30), 30: room(None), 10: room(20)}
    declarations = (
        ("entry", 777, None, False, (("north", "direct", "middle", None),)),
        ("middle", 778, None, False, (("north", "direct", "endpoint", None),)),
        ("endpoint", 779, None, False, ()),
    )
    assert _associate_scenes(objects, room_root=99, declarations=declarations) == {
        "entry": 10, "middle": 20, "endpoint": 30}


def test_symmetric_graph_is_kept_ambiguous_instead_of_guessed_from_object_order():
    objects = {number: {"parent": 99, "properties": {31: {
        "size": 1, "bytes": bytes([number]).hex()}}} for number in (1, 2)}
    declarations = (
        ("first", 1, None, False, (("north", "direct", "first", None),)),
        ("second", 2, None, False, (("north", "direct", "second", None),)),
    )
    with pytest.raises(ValueError, match="ambiguous"):
        _associate_scenes(objects, room_root=99, declarations=declarations)


def test_public_recovery_refuses_other_valid_story_editions_before_using_a_base(tmp_path):
    raw = bytearray(2048)
    raw[0] = 3
    for at, value in ((2, 1), (4, 1024), (6, 1024), (8, 900), (10, 544),
                      (12, 64), (14, 1024), (24, 640), (26, 1024)):
        raw[at:at + 2] = value.to_bytes(2, "big")
    raw[18:24] = b"000001"
    raw[900:904] = bytes([0, 4, 0, 0])
    raw[1024] = 0xBA
    raw[28:30] = (sum(raw[64:]) & 65535).to_bytes(2, "big")
    path = tmp_path / "authored.z3"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="exact Zork I"):
        recover_scenes(path, base_intents={"not": "used"})

