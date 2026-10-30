"""Source-binding failures with authored fixtures, never licensed story data."""
import copy
import hashlib
from pathlib import Path

import pytest

from fdisbull.zmachine import inspect_story
from fdisbull.zork_intents import (
    FORMAT, UDL_FORMAT, _check_ir_identity, build_intent_document, canonical_digest, recover_intents,
    source_witness, verify_bindings, verify_mapped_instruction, verify_witness,
)
from fdisbull.zork_uil import compile_story


@pytest.fixture
def authored_story(tmp_path):
    """An authored add2+3 then quit program, unrelated to the qualified game."""
    raw = bytearray(0x800)
    raw[0] = 3
    for at, value in ((2, 1), (4, 0x400), (6, 0x400), (8, 900),
                      (10, 544), (12, 64), (14, 0x400), (24, 640),
                      (26, len(raw) // 2)):
        raw[at:at + 2] = value.to_bytes(2, "big")
    raw[18:24] = b"000001"
    raw[613:615] = (615).to_bytes(2, "big")
    raw[900:904] = bytes([0, 4, 0, 0])
    raw[0x400:0x405] = bytes([0x14, 2, 3, 0x10, 0xBA])
    raw[28:30] = (sum(raw[64:]) & 0xFFFF).to_bytes(2, "big")
    path = tmp_path / "authored.z3"
    path.write_bytes(raw)
    return path


@pytest.fixture
def authored_bindings(authored_story):
    program, _ = compile_story(authored_story)
    resources = {name: name.upper() for name in (
        "opening_prefix", "opening_middle", "article", "punctuation",
        "newline", "already_open", "opened_empty")}
    uil = build_intent_document(resources)
    image = bytes.fromhex(program["memory"]["initial"])
    udl = {"format": UDL_FORMAT, "source": copy.deepcopy(program["source"]),
           "initial_image_sha256": hashlib.sha256(image).hexdigest(),
           "low_level_ir_sha256": canonical_digest(program), "uil_sha256": canonical_digest(uil),
           "witnesses": {"arithmetic": source_witness(image, 0x400, 0x404, "authored arithmetic")},
           "runtime_guards": ["arithmetic"]}
    return {"format": FORMAT, "low_level_ir": program, "uil": uil, "udl": udl}


def test_unqualified_edition_is_rejected_even_with_matching_low_level_ir(authored_story):
    program, _ = compile_story(authored_story)
    assert program["source"]["sha256"] == inspect_story(authored_story)["sha256"]
    with pytest.raises(ValueError, match="exact Zork I"):
        recover_intents(authored_story, program)


def test_source_operation_must_match_the_ir_being_replaced(authored_story):
    program, _ = compile_story(authored_story)
    raw = authored_story.read_bytes()
    assert verify_mapped_instruction(raw, program, 0x400)["op"] == "add"
    # Preserve the raw source bytes but change the lowered operation's input.
    # A matching source hash alone must not qualify that different computation.
    program["blocks"]["1024"]["nodes"][0]["value"] = 99
    with pytest.raises(ValueError, match="does not match the source operation"):
        verify_mapped_instruction(raw, program, 0x400)


@pytest.mark.parametrize("field", ["version", "release", "serial", "file_bytes",
                                  "declared_bytes", "trailing_bytes", "trailing_sha256", "checksum"])
def test_source_identity_includes_metadata_not_only_the_hash(authored_story, field):
    raw = authored_story.read_bytes()
    info = inspect_story(authored_story)
    program, _ = compile_story(authored_story)
    _check_ir_identity(raw, info, program)
    previous = program["source"][field]
    program["source"][field] = previous + 1 if isinstance(previous, int) else previous + "changed"
    assert program["source"]["sha256"] == info["sha256"]
    with pytest.raises(ValueError, match="source identity"):
        _check_ir_identity(raw, info, program)


def test_binding_checks_accept_an_authored_consistent_package(authored_bindings):
    result = verify_bindings(authored_bindings)
    assert result["witnesses"] == 1
    assert result["runtime_guards"] == 1


@pytest.mark.parametrize("part", ["low_level_ir", "uil"])
def test_semantic_or_residual_program_change_invalidates_binding(authored_bindings, part):
    package = copy.deepcopy(authored_bindings)
    if part == "low_level_ir":
        package[part]["blocks"]["1024"]["next"] += 1
    else:
        # The condition determines whether the recovered game intent executes.
        package[part]["interaction"]["outcomes"][0]["when"][0]["eq"] = False
    with pytest.raises(ValueError, match="binding digest changed"):
        verify_bindings(package)


def test_different_mapping_source_is_not_accepted(authored_bindings):
    authored_bindings["udl"]["source"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source identities differ"):
        verify_bindings(authored_bindings)


def test_recomputed_ir_digest_does_not_hide_changed_source_image(authored_bindings):
    package = authored_bindings
    raw = bytearray.fromhex(package["low_level_ir"]["memory"]["initial"])
    raw[0x401] = 99
    package["low_level_ir"]["memory"]["initial"] = raw.hex()
    package["udl"]["low_level_ir_sha256"] = canonical_digest(package["low_level_ir"])
    with pytest.raises(ValueError, match="Initial source image digest changed"):
        verify_bindings(package)


def test_recomputed_image_digest_still_does_not_hide_witness_mismatch(authored_bindings):
    package = authored_bindings
    raw = bytearray.fromhex(package["low_level_ir"]["memory"]["initial"])
    raw[0x401] = 99
    package["low_level_ir"]["memory"]["initial"] = raw.hex()
    package["udl"]["low_level_ir_sha256"] = canonical_digest(package["low_level_ir"])
    package["udl"]["initial_image_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="Source witness"):
        verify_bindings(package)


def test_witness_hash_without_matching_bytes_cannot_authorize_source():
    raw = b"author-created fixture"
    witness = source_witness(raw, 0, 6, "authored data")
    witness["bytes"] = b"forged".hex()
    witness["sha256"] = hashlib.sha256(b"forged").hexdigest()
    with pytest.raises(ValueError, match="Source witness"):
        verify_witness(raw, witness)


def test_missing_runtime_guard_evidence_is_rejected(authored_bindings):
    authored_bindings["udl"]["runtime_guards"].append("missing-text-dependency")
    with pytest.raises(ValueError, match="no source witness"):
        verify_bindings(authored_bindings)


def test_address_free_definition_exposes_conditions_effects_and_residuals():
    resources = {name: "authored " + name for name in (
        "opening_prefix", "opening_middle", "article", "punctuation",
        "newline", "already_open", "opened_empty")}
    doc = build_intent_document(resources)
    forbidden = {"address", "offset", "pc", "opcode", "register", "source_bytes"}

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(doc)
    outcomes = {row["id"]: row for row in doc["interaction"]["outcomes"]}
    first = outcomes["opened_with_contents"]["steps"]
    assert first[0] == {"intent": "container.open", "entity": "target"}
    assert first[1] == {"residual_ir": "post_open_source_flag"}
    assert first[-3]["intent"] == "discourse.remember_mentioned_object"
    assert outcomes["already_open"]["steps"] == [
        {"intent": "narration.emit", "resource": "already_open"},
        {"intent": "narration.emit", "resource": "newline"}]
    assert doc["turn"]["requires"] == [{"field": "turn.count", "range": [0, 999]}]
    assert doc["turn"]["id"] == "count_player_action"


def test_canonical_bindings_do_not_depend_on_dictionary_order():
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})
    assert canonical_digest({"a": 1}) != canonical_digest({"a": True})
