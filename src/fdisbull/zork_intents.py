"""Recover a bounded game-intent model over the preserved Zork low-level IR.

The old executable profile is deliberately left unchanged. This producer adds
an address-free interaction definition and separate UDL evidence connecting its
fields and effects to one qualified source edition. Unrecovered operations stay
explicitly executable as low-level IR; a source coordinate is never an intent.

Generated documents contain licensed, source-derived text and bytes. Keep them
outside the checkout, just like the original conversion's private outputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .zmachine import decode_v3, decode_ztext, inspect_story
from .zork_uil import FORMAT as LOW_LEVEL_FORMAT, compile_story, lower_instruction


FORMAT = "fdisbull-zork-intent-package-1"
UIL_FORMAT = "fdisbull-game-intent-uil-1"
UDL_FORMAT = "fdisbull-zork-intent-udl-1"
STORY_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"

# These source coordinates belong only to UDL. The domain model below has none.
_REGIONS = {
    "opening-function": (0x8084, 0x80F7),
    "content-list-function": (0x8E58, 0x8EAA),
    "remember-referent-function": (0x9530, 0x953B),
    "turn-completion-prefix": (0x54C4, 0x54F7),
}
_INSTRUCTION_REGIONS = ((0x8089, 0x80F7), (0x8E65, 0x8EAA),
                        (0x9533, 0x953B), (0x54CD, 0x54F7))
_FUNCTIONS = {0x8084: (0x8089, 2), 0x8E58: (0x8E65, 6),
              0x9530: (0x9533, 1), 0x54C4: (0x54CD, 4)}
_RESOURCE_SOURCES = {
    "opening_prefix": (0x80DC, "print"),
    "opening_middle": (0x80E7, "print"),
    "article": (0x8E7F, "print"),
    "punctuation": (0x80F4, "print_ret"),
    "already_open": (0x809A, "print_ret"),
    "opened_empty": (0x80B1, "print_ret"),
}


def canonical_digest(document):
    """Bind a JSON value independently of formatting and dictionary order."""
    data = json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _word(data, at):
    if at < 0 or at + 2 > len(data):
        raise ValueError("Source word exceeds the qualified image")
    return int.from_bytes(data[at:at + 2], "big")


def _record(data, number):
    if not 1 <= number <= 255:
        raise ValueError("Source object number is outside v3 range")
    at = _word(data, 10) + 62 + 9 * (number - 1)
    if at + 9 > len(data):
        raise ValueError("Source object record exceeds the qualified image")
    return at


def source_witness(data, start, end, role):
    """Retain an exact source/data witness, without promoting its meaning."""
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(data)
            or not isinstance(role, str) or not role):
        raise ValueError("Invalid source witness extent")
    raw = data[start:end]
    return {"start": start, "end": end, "bytes": raw.hex(),
            "sha256": hashlib.sha256(raw).hexdigest(), "role": role}


def verify_witness(data, witness):
    """A witness hash alone is insufficient: its bytes must match the source."""
    if not isinstance(witness, dict):
        raise ValueError("Invalid source witness")
    try:
        expected = source_witness(data, witness["start"], witness["end"], witness["role"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid source witness") from exc
    if witness != expected:
        raise ValueError("Source witness bytes, digest or extent changed")


def verify_mapped_instruction(data, program, address):
    """Qualify the replaced IR operation against its original instruction."""
    instruction = decode_v3(data, address)
    expected = lower_instruction(instruction)
    if program.get("blocks", {}).get(str(address)) != expected:
        raise ValueError(f"Low-level IR does not match the source operation at {address:#x}")
    return instruction


def build_intent_document(resources):
    """An address-free game interaction; source layout belongs only to UDL.

    The higher-level evaluator owns these conditions and outcomes. In
    particular, it chooses whether opening happens and whether a newly mentioned
    content object becomes the referent. The residual source flag is visible as
    unresolved work between the opening and the output, not given a guessed name.
    """
    emit = lambda resource: {"intent": "narration.emit", "resource": resource}
    opened = [{"intent": "container.open", "entity": "target"},
              {"residual_ir": "post_open_source_flag"}]
    return {
        "format": UIL_FORMAT,
        "id": "zork1.open-mailbox-bounded",
        "resources": dict(resources),
        "interaction": {
            "id": "open_container",
            "parameters": {"target": "entity"},
            "requires": [{"field": "target." + name, "eq": True}
                         for name in ("is_container", "supports_opening", "reachable", "opaque")],
            "outcomes": [
                {"id": "already_open", "when": [{"field": "target.is_open", "eq": True}],
                 "steps": [emit("already_open"), emit("newline")]},
                {"id": "opened_empty",
                 "when": [{"field": "target.is_open", "eq": False},
                          {"field": "target.contents_count", "eq": 0}],
                 "steps": copy.deepcopy(opened) + [emit("opened_empty"), emit("newline")]},
                {"id": "opened_with_contents",
                 "when": [{"field": "target.is_open", "eq": False},
                          {"field": "target.contents_count", "eq": 1},
                          {"field": "first_content.plain_listing", "eq": True}],
                 "steps": copy.deepcopy(opened) + [
                     emit("opening_prefix"), {"intent": "narration.name", "entity": "target"},
                     emit("opening_middle"), emit("article"),
                     {"intent": "narration.name", "entity": "first_content"},
                     {"intent": "discourse.remember_mentioned_object",
                      "entity": "first_content", "scene": "current_scene"},
                     emit("punctuation"), emit("newline")]},
            ],
        },
        "turn": {"id": "count_player_action",
                 "requires": [{"field": "turn.count", "range": [0, 999]}],
                 "steps": [{"intent": "turn.count_player_action", "cycle": 1000}]},
    }


def _check_ir_identity(raw, info, program):
    data = raw[:info["declared_bytes"]]
    expected_source = {
        "sha256": info["sha256"], "version": info["version"],
        "release": info["release"], "serial": info["serial_text"],
        "file_bytes": info["file_bytes"], "declared_bytes": len(data),
        "trailing_bytes": info["trailing_bytes"],
        "trailing_sha256": hashlib.sha256(raw[len(data):]).hexdigest(),
        "checksum": info["checksum"],
    }
    if (not isinstance(program, dict) or program.get("format") != LOW_LEVEL_FORMAT
            or program.get("source") != expected_source):
        raise ValueError("Low-level IR has a different source identity or format")
    expected_layout = {name: info[name] for name in
                       ("globals", "objects", "dictionary", "abbreviations", "declared_bytes")}
    if (program.get("entry") != info["initial_pc"] or program.get("layout") != expected_layout
            or program.get("memory") != {"initial": data.hex(), "writable_end": info["static_memory"]}):
        raise ValueError("Low-level IR source memory, layout or entry changed")


def verify_bindings(package):
    """Check immutable program/model/source bindings on a generated package.

    This verifies provenance integrity. It does not independently prove the
    recovered semantic meaning or extend the stated behavioral coverage.
    """
    if not isinstance(package, dict) or package.get("format") != FORMAT:
        raise ValueError("Invalid intent package format")
    try:
        program, uil, udl = (package[key] for key in ("low_level_ir", "uil", "udl"))
        if udl["format"] != UDL_FORMAT or uil["format"] != UIL_FORMAT:
            raise ValueError("Invalid intent or mapping format")
        if (canonical_digest(program) != udl["low_level_ir_sha256"]
                or canonical_digest(uil) != udl["uil_sha256"]):
            raise ValueError("Low-level IR or higher-level UIL binding digest changed")
        if program["source"] != udl["source"]:
            raise ValueError("Mapping and low-level IR source identities differ")
        data = bytes.fromhex(program["memory"]["initial"])
        if hashlib.sha256(data).hexdigest() != udl["initial_image_sha256"]:
            raise ValueError("Initial source image digest changed")
        for witness in udl["witnesses"].values():
            verify_witness(data, witness)
        for name in udl["runtime_guards"]:
            if name not in udl["witnesses"]:
                raise ValueError("Runtime guard has no source witness")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete intent package bindings") from exc
    return {"source_sha256": udl["source"]["sha256"],
            "low_level_ir_sha256": udl["low_level_ir_sha256"], "uil_sha256": udl["uil_sha256"],
            "witnesses": len(udl["witnesses"]), "runtime_guards": len(udl["runtime_guards"])}


def recover_intents(story, low_level_ir=None):
    """Recover one qualified interaction while retaining all other executable IR.

    A supplied IR is never modified. Its canonical identity and all selected
    source-operation mappings are checked before constructing the new bindings.
    The original full-story conversion remains the residual execution substrate.
    """
    info = inspect_story(story)
    if info["sha256"] != STORY_SHA256:
        raise ValueError("Intent recovery requires exact Zork I R88 / serial 840726")
    raw = Path(story).read_bytes()
    if hashlib.sha256(raw).hexdigest() != info["sha256"]:
        raise ValueError("Source story changed during recovery")
    data = raw[:info["declared_bytes"]]
    program = compile_story(story)[0] if low_level_ir is None else low_level_ir
    _check_ir_identity(raw, info, program)
    witnesses, guards = {}, []

    def witness(name, start, end, role, runtime_guard=False):
        item = source_witness(data, start, end, role)
        if name in witnesses and witnesses[name] != item:
            raise ValueError("Conflicting source witness identity")
        witnesses[name] = item
        if runtime_guard and name not in guards:
            guards.append(name)
        return name

    instructions = {}
    for start, end in _INSTRUCTION_REGIONS:
        address = start
        while address < end:
            instruction = verify_mapped_instruction(data, program, address)
            instructions[address] = instruction
            witness(f"instruction-{address:x}", address, instruction["end"], "original operation")
            address = instruction["end"]
        if address != end:
            raise ValueError("Selected source region ends inside an instruction")
    scheduler_call = verify_mapped_instruction(data, program, 0x5774)
    if (scheduler_call["op"] != "call" or scheduler_call["operands"] != [
            {"kind": "large", "value": 0x54C4 // 2}]
            or scheduler_call.get("store") != 7 or scheduler_call["end"] != 0x5779):
        raise ValueError("Source scheduler call or return convention changed")
    witness("scheduler-call", 0x5774, 0x5779, "residual scheduler invocation and return ABI", True)
    for address, (entry, count) in _FUNCTIONS.items():
        expected = {"entry": entry, "locals": [_word(data, at) for at in
                    range(address + 1, entry, 2)], "guard": data[address:entry].hex()}
        if data[address] != count or program["functions"].get(str(address)) != expected:
            raise ValueError(f"Low-level IR function binding changed at {address:#x}")
    for name, (start, end) in _REGIONS.items():
        witness(name, start, end, "qualified executable source and routine header", True)
    witness("header-layout", 8, 16, "dictionary/object/global/static-memory pointers", True)
    witness("header-abbreviations", 24, 26, "abbreviation-table pointer", True)

    def text_dependencies(start, ancestry=()):
        if start in ancestry:
            raise ValueError("Cyclic source text dependency")
        _, end = decode_ztext(data, start)
        dependencies = {witness(f"text-{start:x}", start, end, "packed text", True)}
        codes = []
        for at in range(start, end, 2):
            word = _word(data, at)
            codes.extend(((word >> 10) & 31, (word >> 5) & 31, word & 31))
        index, alphabet = 0, 0
        while index < len(codes):
            code = codes[index]
            index += 1
            if code in (1, 2, 3):
                if index >= len(codes):
                    raise ValueError("Truncated abbreviation dependency")
                at = info["abbreviations"] + 2 * (32 * (code - 1) + codes[index])
                index += 1
                dependencies.add(witness(f"abbreviation-{at:x}", at, at + 2,
                                         "abbreviation pointer", True))
                dependencies.update(text_dependencies(2 * _word(data, at), (*ancestry, start)))
            elif code in (4, 5):
                alphabet = code - 3
                continue
            elif alphabet == 2 and code == 6:
                if index + 1 >= len(codes):
                    raise ValueError("Truncated source ZSCII dependency")
                index += 2
            alphabet = 0
        return sorted(dependencies)

    resources, resource_bindings = {}, {}
    for name, (address, expected_op) in _RESOURCE_SOURCES.items():
        instruction = instructions[address]
        if instruction["op"] != expected_op:
            raise ValueError("Source narrative operation changed")
        text_at = instruction["text_offset"]
        resources[name] = decode_ztext(data, text_at)[0]
        resource_bindings[name] = {
            "kind": "inline_packed_text", "instruction": address, "text_offset": text_at,
            "witnesses": [f"instruction-{address:x}", *text_dependencies(text_at)],
        }
    resources["newline"] = "\n"  # An explicit print_ret semantic effect.
    return_printers = [address for address, opcode in _RESOURCE_SOURCES.values()
                       if opcode == "print_ret"]
    resource_bindings["newline"] = {
        "kind": "print_return_newline", "operations": return_printers,
        "witnesses": [f"instruction-{address:x}" for address in return_printers],
    }

    objects = {}
    for name, number in (("mailbox", 160), ("leaflet", 161), ("west_of_house", 180)):
        at = _record(data, number)
        table = _word(data, at + 7)
        name_end = table + 1 + 2 * data[table]
        pointer_witness = witness(name + "-property-pointer", at + 7, at + 9,
                                  "property/name table pointer", True)
        name_witness = witness(name + "-name", table, name_end, "short-name layout and packed text", True)
        name_dependencies = [pointer_witness, name_witness, *text_dependencies(table + 1)]
        objects[name] = {"number": number, "record": at,
                         "name": decode_ztext(data, table + 1)[0], "name_witness": name_witness,
                         "name_dependencies": name_dependencies}
        # Only structural headers are runtime guards. Property values, attributes,
        # object links and referent globals remain legitimate mutable play state.
        cursor = name_end
        for _ in range(32):
            header = data[cursor]
            witness(f"{name}-property-header-{cursor:x}", cursor, cursor + 1,
                    "property-list layout", True)
            cursor += 1
            if header == 0:
                break
            cursor += (header >> 5) + 1
        else:
            raise ValueError("Unterminated source property list")

    def attribute(object_name, number, invert=False):
        result = {"kind": "attribute", "object": object_name, "number": number,
                  "address": objects[object_name]["record"] + number // 8,
                  "mask": 128 >> (number % 8)}
        if invert:
            result["invert"] = True
        return result

    def global_word(number):
        return {"kind": "global", "number": number,
                "address": info["globals"] + 2 * (number - 16), "width": 16}

    def source_property(object_name, number, condition):
        """Record a property's initial value without freezing its runtime value."""
        table = _word(data, objects[object_name]["record"] + 7)
        cursor = table + 1 + 2 * data[table]
        address, size = info["objects"] + 2 * (number - 1), 2
        for _ in range(32):
            header = data[cursor]
            cursor += 1
            if not header:
                break
            length = (header >> 5) + 1
            if header & 31 == number:
                address, size = cursor, length
                break
            cursor += length
        initial = data[address] if size == 1 else _word(data, address)
        evidence = witness(f"{object_name}-property-value-{number}", address, address + size,
                           "initial property value; mutable at runtime")
        return {"kind": "property", "object": object_name, "number": number,
                "condition": condition, "initial": initial, "witness": evidence}

    fields = {
        "target.is_container": attribute("mailbox", 19),
        "target.is_open": attribute("mailbox", 11),
        "target.opaque": attribute("mailbox", 12, True),
        "target.supports_opening": source_property("mailbox", 10, "nonzero"),
        "target.parent": {"kind": "link", "object": "mailbox", "offset": 4},
        "target.child": {"kind": "link", "object": "mailbox", "offset": 6},
        "first_content.parent": {"kind": "link", "object": "leaflet", "offset": 4},
        "first_content.sibling": {"kind": "link", "object": "leaflet", "offset": 5},
        "first_content.description": source_property("leaflet", 14, "zero"),
        "discourse.object": global_word(0x7B), "discourse.scene": global_word(0x7A),
        "current_scene": global_word(0x10), "turn.count": global_word(0x12),
        "source_flags.mailbox_attribute_3": attribute("mailbox", 3),
        "source_flags.leaflet_attribute_3": attribute("leaflet", 3),
    }
    for name, address in (("target.is_open", 0x80A3), ("discourse.object", 0x9533),
                          ("discourse.scene", 0x9536), ("turn.count", 0x54EC)):
        fields[name]["source_operation"] = address

    def primitive(meaning, operations, kind="game_intent"):
        return {"meaning": meaning, "kind": kind, "operations": operations,
                "witnesses": [f"instruction-{pc:x}" for pc in operations]}

    uil = build_intent_document(resources)
    udl = {
        "format": UDL_FORMAT, "source": copy.deepcopy(program["source"]),
        "initial_image_sha256": hashlib.sha256(data).hexdigest(),
        "low_level_ir_sha256": canonical_digest(program), "uil_sha256": canonical_digest(uil),
        "objects": objects, "fields": fields, "witnesses": witnesses, "runtime_guards": guards,
        "resource_bindings": resource_bindings,
        "primitives": {
            "container.open": primitive("Establish the closed container's open state; already-open outcome is selected by UIL.", [0x8089, 0x808E, 0x8092, 0x8096, 0x80A3]),
            "narration.emit": primitive("Emit named source-derived presentation fragments in declared order.", [0x809A, 0x80B1, 0x80DC, 0x80E7, 0x8E7F, 0x80F4], "presentation_support"),
            "narration.name": primitive("Present the qualified entity's short name.", [0x80E5, 0x8E82], "presentation_support"),
            "discourse.remember_mentioned_object": primitive("Remember the single mentioned content object and its location for later pronoun resolution.", [0x8EA3, 0x9533, 0x9536]),
            "turn.count_player_action": primitive("Count a completed player action modulo 1000 within the qualified 0..999 domain; no callback intent is implied.", [0x54EC, 0x54F2]),
        },
        "opening": {"function": 0x8084, "entry": 0x8089,
                    "return_pc": 0x5871, "return_store": 4, "return_value": 1,
                    "return_operations": [0x809A, 0x80B1, 0x80F4],
                    "locals_initial": [0, 0], "action_global": 0x88, "action_value": 43,
                    "direct_object_global": 0x86, "scene_object": 180,
                    "target": "mailbox", "content": "leaflet", "scene": "west_of_house",
                    "target_object": 160, "content_object": 161,
                    "qualified_contents": ["empty", "single_leaflet"],
                    "fallback": "execute_original_low_level_ir"},
        "turn": {"entry": 0x54EC, "continue": 0x54F5, "minimum": 0, "maximum": 999,
                 "cycle": 1000, "field": "turn.count", "function": 0x54C4,
                 "return_pc": 0x5779, "return_store": 7, "scheduler_call": 0x5774,
                 "locals_count": 4, "end_guard": 0x54E8, "cursor_equal": [0, 1],
                 "fallback": "execute_original_low_level_ir"},
        "residuals": {
            "post_open_source_flag": {"kind": "single_block", "entry": 0x80A6, "continue": 0x80A9,
                                      "operations": [0x80A6], "witnesses": ["instruction-80a6"],
                                      "reason": "Attribute 3 is used for several object-history roles; a universal game meaning is unresolved."},
            "command_binding": {"reason": "Original tokenization, parsing, pronoun validation, accessibility and action dispatch remain low-level IR."},
            "post_action_processing": {"entry": 0x5871,
                                       "reason": "Post-action dispatch and progression to the scheduler are not recovered intent."},
            "turn_callbacks": {"entry": 0x54CD,
                               "reason": "Background callbacks, timers, random draws and their object/state effects remain original low-level IR."},
            "return_to_input": {"entry": 0x54F5,
                                "reason": "Scheduler return, cleanup, prompt and next-input preparation remain low-level IR."},
            "unsupported_interactions": {"reason": "Every other command and unmatched mailbox state remains low-level IR, without an intent-recovery claim."},
        },
        "interaction_envelope": [
            {"residual_ir": "command_binding"}, {"uil": "interaction", "binding": "opening"},
            {"residual_ir": "post_action_processing"}, {"residual_ir": "turn_callbacks"},
            {"uil": "turn", "binding": "turn"}, {"residual_ir": "return_to_input"}],
        "qualification": {"scope": "one source-bound mailbox interaction with explicit residual execution",
                          "all_game_intent_recovered": False, "unrecovered_execution": "retained_low_level_ir",
                          "attribute_3_meaning": "unresolved", "property_10_meaning": "nonzero source gate; capacity name not established"},
    }
    package = {"format": FORMAT, "low_level_ir": program, "uil": uil, "udl": udl}
    verify_bindings(package)
    return package
