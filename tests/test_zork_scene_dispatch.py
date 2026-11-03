"""Authored fixtures for dispatch recovery; no original story bytes are shipped."""
import copy

import pytest

from fdisbull.zmachine import decode_v3
from fdisbull.zork_scene_dispatch import (
    UIL_FORMAT, _dispatch_sites, _grammar, _object_records, _pseudo_definitions, _routine, _STAGES,
    recover_dispatch, validate_dispatch_uil,
)


def _word(data, address, value):
    data[address:address + 2] = value.to_bytes(2, "big")


def _spell(word):
    # Independent v3 dictionary fixture: six lowercase alphabet characters.
    chars = [ord(x) - ord("a") + 6 for x in word[:6]]
    chars.extend([5] * (6 - len(chars)))
    first = chars[0] << 10 | chars[1] << 5 | chars[2]
    second = 0x8000 | chars[3] << 10 | chars[4] << 5 | chars[5]
    return first.to_bytes(2, "big") + second.to_bytes(2, "big")


def _grammar_fixture():
    data = bytearray(0x800)
    info = {"dictionary": 0x300, "static_memory": 0x200}
    entries = [(_spell("open"), 0x41, 255, 0),
               (_spell("unlock"), 0x41, 255, 0),
               (_spell("walk"), 0x41, 254, 0),
               (_spell("with"), 8, 255, 0),
               # Both verb and preposition; byte six is its verb number.
               (_spell("on"), 0x48, 254, 253)]
    data[0x300] = 0
    data[0x301] = 7
    _word(data, 0x302, len(entries))
    for i, (spelling, *values) in enumerate(entries):
        at = 0x304 + 7 * i
        data[at:at + 7] = spelling + bytes(values)
    for i, group in enumerate((0x480, 0x490, 0x4A0)):
        _word(data, 0x400 + 2 * i, group)
    data[0x480:0x489] = bytes((1, 2, 0, 255, 0, 0, 0, 0, 2))
    data[0x490:0x499] = bytes((1, 1, 254, 0, 0, 0, 0, 0, 1))
    data[0x4A0:0x4A9] = bytes((1, 0, 0, 0, 0, 0, 0, 0, 0))
    return data, info


def test_grammar_resolves_all_aliases_prepositions_and_action_numbers():
    data, info = _grammar_fixture()
    result = _grammar(bytes(data), info, 0x400, 3)
    by_action = {row["action"]: row for row in result}
    assert set(by_action) == {0, 1, 2}
    opening = by_action[2]
    assert opening["object_count"] == 2
    assert opening["prepositions"] == [[], ["with"]]
    assert [x["text"] for x in opening["words"]] == ["open", "unlock"]
    assert (opening["pointer"], opening["group"], opening["address"]) == (0x400, 0x480, 0x481)
    assert by_action[1]["prepositions"] == [["on"], []]
    assert by_action[0]["verb_number"] == 253
    assert by_action[0]["words"][0]["text"] == "on"


@pytest.mark.parametrize("address,value", [(0x488, 3), (0x482, 252), (0x481, 3), (0x480, 0)])
def test_grammar_refuses_unresolved_or_out_of_domain_definitions(address, value):
    data, info = _grammar_fixture()
    data[address] = value
    with pytest.raises(ValueError):
        _grammar(bytes(data), info, 0x400, 3)


def _object_fixture():
    data = bytearray(0x800)
    info = {"objects": 0x100, "static_memory": 0x300}
    # Two nine-byte objects, beginning after 31 default property words.
    _word(data, 0x13E + 7, 0x150)
    _word(data, 0x147 + 7, 0x155)
    data[0x150:0x155] = bytes((0, 0x31, 0x03, 0x00, 0))  # ACTION, packed 0x300.
    data[0x155:0x15A] = bytes((0, 0x29, 0x03, 0x20, 0))  # DESCFCN, packed 0x320.
    return data, info


def test_object_bindings_preserve_distinct_identities_and_property_layout():
    data, info = _object_fixture()
    records = _object_records(bytes(data), info, {1: "actor", 2: "hall"})
    assert [x["id"] for x in records] == ["actor", "hall"]
    assert records[0]["properties"] == {17: {"header": 0x151, "cell": 0x152, "size": 2}}
    assert records[1]["properties"] == {9: {"header": 0x156, "cell": 0x157, "size": 2}}
    assert records[0]["property_headers"] == [0x151, 0x154]
    assert records[1]["property_headers"] == [0x156, 0x159]
    assert 2 not in records[0]["properties"]  # Consumer must use the default, not invent a cell.
    generated = _object_records(bytes(data), info)
    assert [x["id"] for x in generated] == ["unnamed", "unnamed_2"]


@pytest.mark.parametrize("identities", [{1: "one"}, {1: "same", 2: "same"}, {1: "bad id", 2: "ok"}])
def test_object_identity_projection_must_be_complete_and_unique(identities):
    data, info = _object_fixture()
    with pytest.raises(ValueError):
        _object_records(bytes(data), info, identities)


def test_property_layout_rejects_repeated_numbers_and_out_of_bounds_pointer():
    data, info = _object_fixture()
    data[0x154:0x158] = bytes((0x31, 0, 0, 0))
    with pytest.raises(ValueError, match="descending"):
        _object_records(bytes(data), info)
    data, info = _object_fixture()
    _word(data, 0x147 + 7, 0x500)
    with pytest.raises(ValueError, match="outside dynamic"):
        _object_records(bytes(data), info)


def test_routine_resolution_skips_default_locals_and_preserves_null():
    data = bytearray(0x800)
    data[0x600:0x606] = bytes((2, 0, 9, 0xFF, 0xFF, 0xB0))
    assert _routine(bytes(data), 0) is None
    assert _routine(bytes(data), 0x300) == {
        "packed": 0x300, "routine_header": 0x600, "entry": 0x605, "locals": [9, 65535]}
    data[0x600] = 16
    with pytest.raises(ValueError, match="invalid routine"):
        _routine(bytes(data), 0x300)


def _pseudo_fixture():
    data, info = _object_fixture()
    data[0x142] = 82
    _word(data, 0x147 + 7, 0x157)
    data[0x150:0x159] = bytes((0, 0x64, 0x05, 0x00, 0x03, 0x00, 0, 0, 0))
    data[0x500:0x504] = _spell("smoke")
    data[0x600:0x602] = bytes((0, 0xB0))
    return data, info


def test_pseudo_callback_variants_come_from_room_definition_pairs():
    data, info = _pseudo_fixture()
    objects = _object_records(bytes(data), info, {1: "hall", 2: "prop"})
    assert _pseudo_definitions(bytes(data), objects, 82) == [{
        "scene": "hall", "scene_object": 1, "word": "smoke", "dictionary_word": 0x500,
        "cell": 0x152, "property_header": 0x151, "packed": 0x300}]
    data[0x142] = 1
    assert _pseudo_definitions(bytes(data), objects, 82) == []


@pytest.mark.parametrize("mutation", ["length", "null", "header"])
def test_pseudo_callback_variants_reject_unqualified_definitions(mutation):
    data, info = _pseudo_fixture()
    if mutation == "length":
        data[0x151] = 0x44  # Three bytes cannot contain a dictionary/callback pair.
        data[0x155] = 0
    elif mutation == "null":
        _word(data, 0x154, 0)
    else:
        data[0x600] = 16
    objects = _object_records(bytes(data), info)
    with pytest.raises(ValueError):
        _pseudo_definitions(bytes(data), objects, 82)


def _rows(hexbytes, start=0x100):
    data = bytes(start) + bytes.fromhex(hexbytes)
    rows = {}
    while start < len(data):
        row = decode_v3(data, start)
        rows[start] = row
        start = row["end"]
    return rows


def test_adjacent_table_dispatch_eliminates_temporary_stack_address():
    # LOADW global 0xab, local2 -> stack; CALL stack, literal7 -> local3.
    rows = _rows("6fab0200 e09f000703")
    [site] = _dispatch_sites(rows, {0xAB: "actions"})
    assert site["selector"] == {"kind": "table", "table": "actions",
                                 "index": {"variable": 2}, "pointer_global": 0xAB}
    assert site["arguments"] == [{"constant": 7}]
    assert (site["start"], site["call_pc"], site["return_pc"], site["store"]) == (0x100, 0x104, 0x109, 3)
    assert site["source_pcs"] == [0x100, 0x104]


def test_property_parent_chain_is_one_binding_and_preserves_real_arguments():
    # GET_PARENT local2 -> stack; GET_PROP stack,17 -> stack;
    # CALL stack, local3, stack -> local4. The final stack argument remains real.
    rows = _rows("a30200 51001100 e0ab00030004")
    [site] = _dispatch_sites(rows, {})
    assert site["selector"] == {"kind": "property", "object": {"parent": {"variable": 2}}, "property": 17}
    assert site["source_pcs"] == [0x100, 0x103, 0x107]
    assert site["arguments"] == [{"variable": 3}, {"variable": 0}]
    assert site["return_pc"] == 0x10D


@pytest.mark.parametrize("sequence", [
    "6f880200 e0bf0004",  # An unrelated mutable table is not an action table.
    "51001100 b4 e0bf0004",  # A gap is not silently swept into the proof.
    "51001000 e0bf0004",  # Unknown property role.
    "51001101 e0bf0104",  # The established transport pattern uses stack0.
    "51001100 e03f030004",  # A literal direct call does not use the property.
])
def test_dispatch_discovery_does_not_guess_unqualified_transport(sequence):
    assert _dispatch_sites(_rows(sequence), {0xAB: "actions"}) == []


def _uil():
    return {"format": UIL_FORMAT,
            "actions": [{"id": "action.open", "handler": "residual.open", "before_handler": None,
                         "aliases": ["open", "unlock"]}],
            "handlers": {"residual.open": {"role": "action", "representation": "low_level_ir", "intent_status": "unrecovered"}},
            "stages": [{"id": identity, "selector": selector, "requires": list(requires), "event": event}
                       for identity, selector, requires, event in _STAGES],
            "grammar": [{"action": "action.open", "verbs": ["open"], "object_count": 1,
                         "prepositions": [[], []], "status": "syntax_association_parser_filters_remain_residual"}],
            "selection_semantics": "ordered_first_handled",
            "claim": "resolved_rule_selection_with_explicit_residual_bodies"}


def test_dispatch_uil_is_address_free_and_keeps_handler_bodies_residual():
    uil = _uil()
    assert validate_dispatch_uil(uil) == uil
    assert uil["handlers"]["residual.open"]["representation"] == "low_level_ir"
    assert [x["id"] for x in uil["stages"]] == [
        "actor_action", "scene_before_action", "verb_before_action", "indirect_object_action",
        "container_action", "direct_object_action", "verb_action"]


@pytest.mark.parametrize("change", [
    lambda x: x.update(entry=0x500),
    lambda x: x.update(claim="complete_game_intent"),
    lambda x: x["handlers"]["residual.open"].update(representation="game_intent_uil"),
    lambda x: x["handlers"]["residual.open"].update(address=0x500),
    lambda x: x["stages"].reverse(),
    lambda x: x["actions"][0].update(handler="missing"),
    lambda x: x["actions"][0].update(handler=[]),
    lambda x: x["actions"][0].update(before_handler=[]),
    lambda x: x["grammar"][0].update(action=[]),
    lambda x: x["grammar"][0].update(object_count=True),
    lambda x: x["grammar"][0].update(prepositions=[[], [] , []]),
])
def test_dispatch_uil_refuses_fabricated_effect_claims_and_malformed_links(change):
    uil = copy.deepcopy(_uil())
    change(uil)
    with pytest.raises(ValueError):
        validate_dispatch_uil(uil)


def test_public_recovery_does_not_borrow_r88_definitions_for_another_source():
    with pytest.raises(ValueError):
        recover_dispatch(b"not a qualified story")
    data = bytearray(4096)
    data[0] = 3
    for offset, value in ((4, 3072), (6, 3072), (8, 1536), (10, 256),
                          (12, 1024), (14, 2048), (24, 64), (26, 2048)):
        _word(data, offset, value)
    data[1537] = 7
    _word(data, 1538, 1)
    data[3072] = 0xB0
    _word(data, 28, sum(data[64:]) & 65535)
    with pytest.raises(ValueError, match="qualified Zork I R88"):
        recover_dispatch(bytes(data))
