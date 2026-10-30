"""Recover explicit scene links from the qualified Zork I R88 object model.

The producer resolves compiled property records and packed routine references
once. The resulting UIL contains scene names, live predicates and requested
effects; the byte layout, interpreter stack and source addresses stay in UDL.
Unknown routine bodies remain named residual IR. The original intent package
is retained unchanged as the executable reference and fallback substrate.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import re

from ._zork_scene_symbols import SCENE_SYMBOLS, SOURCE_REPOSITORY, SOURCE_REVISION
from .zmachine import MAX_STORY_FILE, decode_v3, decode_ztext, inspect_story_bytes
from .zork_intents import (
    STORY_SHA256, _check_ir_identity, canonical_digest, recover_intents,
    source_witness, verify_bindings as verify_intent_bindings,
    verify_mapped_instruction, verify_witness,
)

FORMAT = "fdisbull-zork-scene-package-1"
UIL_FORMAT = "fdisbull-scene-intent-uil-1"
UDL_FORMAT = "fdisbull-zork-scene-udl-1"

DIRECTIONS = dict(zip(range(31, 18, -1), (
    "north", "east", "west", "south", "northeast", "northwest", "southeast",
    "southwest", "up", "down", "in", "out", "land")))
_FACT_GLOBALS = {
    "won_flag": 156, "troll_flag": 157, "rainbow_flag": 158,
    "magic_flag": 159, "low_tide": 160, "lld_flag": 161,
    "empty_handed": 162, "dome_flag": 163, "deflate": 164,
    "cyclops_flag": 165, "false_flag": 166, "coffin_cure": 155,
}
_DOOR_OBJECTS = {"kitchen_window": 235, "trap_door": 183, "grate": 174}
_EXIT_KINDS = {1: "direct", 2: "blocked", 3: "routine", 4: "conditional", 5: "door"}
_RESOURCE_INSTRUCTIONS = {
    "default_blocked": 0x8B26,
    "default_closed_prefix": 0x8B57,
    "default_closed_suffix": 0x8B5C,
}
_SELECTION_OPERATIONS = {
    "property_lookup": 0x8ABA, "property_length": 0x8AC2,
    "direct_target": 0x8AC9, "direct_travel": 0x8ACD,
    "blocked_resource": 0x8AD8, "blocked_print": 0x8ADC,
    "blocked_newline": 0x8ADE, "blocked_return": 0x8ADF,
    "routine_target": 0x8AE5, "routine_call": 0x8AE9,
    "conditional_selector": 0x8B05, "conditional_value": 0x8B09,
    "conditional_test": 0x8B0C, "conditional_target": 0x8B0F,
    "conditional_travel": 0x8B13, "conditional_resource": 0x8B1A,
    "conditional_print": 0x8B21, "conditional_newline": 0x8B23,
    "conditional_return": 0x8B24, "default_blocked_print": 0x8B26,
    "default_blocked_newline": 0x8B31, "default_blocked_return": 0x8B32,
    "door_selector": 0x8B38, "door_test": 0x8B3C,
    "door_target": 0x8B40, "door_travel": 0x8B44,
    "door_resource": 0x8B4B, "door_custom_print": 0x8B52,
    "door_custom_newline": 0x8B54, "door_custom_return": 0x8B55,
    "door_prefix": 0x8B57, "door_name": 0x8B5A,
    "door_suffix": 0x8B5C, "door_newline": 0x8B63,
    "door_remember": 0x8B64, "door_return": 0x8B6A,
}


def _word(data, address):
    if type(address) is not int or not 0 <= address <= len(data) - 2:
        raise ValueError("Scene source word exceeds the image")
    return int.from_bytes(data[address:address + 2], "big")


def _objects(data, *, table, count, dynamic_end):
    """Read v3 records and bounded descending property lists without guessing.

    Object count belongs to the qualified edition profile. A generic v3 header
    does not contain it, and arbitrary bytes beyond the records are not objects.
    """
    if (not isinstance(data, bytes) or type(count) is not int or not 1 <= count <= 255
            or type(table) is not int or type(dynamic_end) is not int
            or not 64 <= table < dynamic_end <= len(data)
            or table + 62 + 9 * count > dynamic_end):
        raise ValueError("Invalid qualified scene object-table extent")
    result = {}
    start = table + 62
    for number in range(1, count + 1):
        record = start + 9 * (number - 1)
        pointer = _word(data, record + 7)
        if not start + 9 * count <= pointer < dynamic_end:
            raise ValueError("Scene property pointer overlaps records or exceeds memory")
        name_end = pointer + 1 + 2 * data[pointer]
        if name_end >= dynamic_end:
            raise ValueError("Scene short-name extent exceeds property memory")
        name = ""
        if data[pointer]:
            name, decoded_end = decode_ztext(data, pointer + 1)
            if decoded_end != name_end:
                raise ValueError("Scene short-name length differs from its encoded extent")
        cursor, previous, props = name_end, 32, {}
        for _ in range(32):
            if cursor >= dynamic_end:
                raise ValueError("Unterminated scene property list")
            header = data[cursor]
            if not header:
                break
            prop, size = header & 31, (header >> 5) + 1
            if not 1 <= prop < previous or cursor + 1 + size > dynamic_end:
                raise ValueError("Scene property list is not bounded and descending")
            props[prop] = {
                "number": prop, "header": cursor, "address": cursor + 1,
                "size": size, "bytes": data[cursor + 1:cursor + 1 + size].hex(),
            }
            cursor += 1 + size
            previous = prop
        else:
            raise ValueError("Scene property-list budget exceeded")
        result[number] = {
            "number": number, "record": record, "property_table": pointer,
            "name": name, "name_start": pointer + 1, "name_end": name_end,
            "terminator": cursor, "parent": data[record + 4],
            "attributes": [i for i in range(32)
                           if data[record + i // 8] & (128 >> (i % 8))],
            "properties": props,
        }
    return result


def _routine(data, packed):
    """A packed code reference resolves to a header, then its instruction entry."""
    if type(packed) is not int or not 1 <= packed <= 65535:
        raise ValueError("Expected a non-null scene routine reference")
    header = 2 * packed
    if not 64 <= header < len(data):
        raise ValueError("Scene routine header exceeds the declared image")
    count = data[header]
    entry = header + 1 + 2 * count
    if count > 15 or entry >= len(data):
        raise ValueError("Scene routine has an invalid local header")
    decode_v3(data, entry)
    return {"kind": "routine", "packed": packed, "header": header, "entry": entry,
            "locals": [_word(data, header + 1 + 2 * n) for n in range(count)]}


class _Evidence:
    """Deduplicated source witnesses with local, explicitly selected live guards."""

    def __init__(self, data, abbreviations):
        self.data = data
        self.abbreviations = abbreviations
        self.witnesses = {}
        self.resources = {}
        self.resource_bindings = {}

    def add(self, name, start, end, role):
        item = source_witness(self.data, start, end, role)
        if name in self.witnesses and self.witnesses[name] != item:
            raise ValueError("Conflicting scene source witness")
        self.witnesses[name] = item
        return name

    def text_dependencies(self, start, ancestry=()):
        if start in ancestry:
            raise ValueError("Cyclic scene text dependency")
        _, end = decode_ztext(self.data, start)
        deps = {self.add(f"text-{start:x}", start, end, "original packed text")}
        codes = []
        for at in range(start, end, 2):
            word = _word(self.data, at)
            codes.extend(((word >> 10) & 31, (word >> 5) & 31, word & 31))
        index = alphabet = 0
        while index < len(codes):
            code = codes[index]
            index += 1
            if code in (1, 2, 3):
                if index >= len(codes):
                    raise ValueError("Truncated scene abbreviation dependency")
                at = self.abbreviations + 2 * (32 * (code - 1) + codes[index])
                index += 1
                deps.add(self.add(f"abbreviation-{at:x}", at, at + 2,
                                  "original abbreviation reference"))
                deps.update(self.text_dependencies(2 * _word(self.data, at), (*ancestry, start)))
            elif code in (4, 5):
                alphabet = code - 3
                continue
            elif alphabet == 2 and code == 6:
                if index + 1 >= len(codes):
                    raise ValueError("Truncated scene ZSCII dependency")
                index += 2
            alphabet = 0
        return sorted(deps)

    def text(self, resource, address):
        text, _ = decode_ztext(self.data, address)
        self.resources[resource] = text
        self.resource_bindings[resource] = {
            "address": address, "dependencies": self.text_dependencies(address)}
        return resource

    def structure(self, obj):
        number, table, record = obj["number"], obj["property_table"], obj["record"]
        guards = [self.add(f"object-{number}-property-pointer", record + 7, record + 9,
                           "object property-table reference"),
                  self.add(f"object-{number}-name-length", table, table + 1,
                           "short-name length and property-list boundary")]
        for prop in obj["properties"].values():
            guards.append(self.add(f"property-header-{prop['header']:x}",
                                   prop["header"], prop["header"] + 1,
                                   "descending property-list structure"))
        guards.append(self.add(f"property-terminator-{obj['terminator']:x}",
                               obj["terminator"], obj["terminator"] + 1,
                               "property-list terminator"))
        return guards


def _lower_exit(data, prop, *, identity, scene_ids, fact_ids, door_ids,
                handler, evidence):
    """Decode one proven table convention into domain conditions and effects.

    This helper is exercised with authored data in ordinary CI. The public
    producer separately requires the exact qualified edition and its complete
    graph profile before invoking it.
    """
    address, size = prop["address"], prop["size"]
    if size not in _EXIT_KINDS or not 0 <= address < address + size <= len(data):
        raise ValueError("Unsupported or truncated scene exit record")
    raw = data[address:address + size]
    if raw.hex() != prop["bytes"]:
        raise ValueError("Scene exit record differs from its source extent")
    kind = _EXIT_KINDS[size]
    out = {"id": identity, "kind": kind}
    binding = {key: prop[key] for key in ("header", "address", "size", "bytes")}
    if kind in ("direct", "conditional", "door"):
        if raw[0] not in scene_ids:
            raise ValueError("Scene exit destination is not a qualified room")
        out["destination"] = scene_ids[raw[0]]
        binding["destination"] = raw[0]
    if kind == "blocked":
        packed = _word(data, address)
        if not packed:
            raise ValueError("Blocked scene exit has a null text reference")
        out["failure_resource"] = evidence.text(identity + ".refusal", 2 * packed)
    elif kind == "routine":
        if not handler:
            raise ValueError("Routine exit lacks a qualified handler symbol")
        if raw[2] != 0:
            raise ValueError("Scene routine-exit layout padding changed")
        out["residual"] = handler
        binding["handler"] = handler
        binding["routine"] = _routine(data, _word(data, address))
    elif kind in ("conditional", "door"):
        names, key = (fact_ids, "fact") if kind == "conditional" else (door_ids, "door")
        if raw[1] not in names:
            raise ValueError("Scene exit selector lacks a qualified named binding")
        out[key] = names[raw[1]]
        binding[key] = names[raw[1]]
        if kind == "door" and raw[4] != 0:
            raise ValueError("Scene door-exit layout padding changed")
        packed = _word(data, address + 2)
        # Only the compatibility frame needs this compiled constant when an
        # unrecovered body suspends before V-WALK returns. UIL uses resources.
        binding["failure_packed"] = packed
        if packed:
            out["failure_resource"] = evidence.text(identity + ".refusal", 2 * packed)
    return out, binding


def _object_ids(objects, room_ids):
    """Stable readable metadata names; duplicates get local ordinals, never PCs."""
    used, result = set(room_ids.values()), dict(room_ids)
    for number, obj in objects.items():
        if number in result:
            continue
        stem = re.sub(r"[^a-z0-9]+", "_", obj["name"].lower()).strip("_") or "unnamed_entity"
        identity, ordinal = stem, 2
        while identity in used:
            identity = f"{stem}_{ordinal}"
            ordinal += 1
        used.add(identity)
        result[number] = identity
    result.update({number: identity for identity, number in _DOOR_OBJECTS.items()
                   if number in objects})
    return result


def _associate_scenes(objects, *, room_root, declarations=SCENE_SYMBOLS):
    """Associate names through the graph, without using profile object numbers.

    Direction sets, exit kinds and recursively constrained destination links
    uniquely identify every room in this edition, even its identically named
    mazes and mines. Ambiguity is an error; iteration order never chooses a
    candidate. The profile's numeric identities are checked independently after
    association, rather than serving as its inputs.
    """
    source = {row[0]: row[4] for row in declarations}
    compiled = {}
    for number, obj in objects.items():
        if obj["parent"] != room_root:
            continue
        exits = {}
        for prop_number, prop in obj["properties"].items():
            if prop_number not in DIRECTIONS:
                continue
            kind = _EXIT_KINDS.get(prop["size"])
            if kind is None:
                raise ValueError("Scene graph contains an unsupported exit convention")
            raw = bytes.fromhex(prop["bytes"])
            if len(raw) != prop["size"]:
                raise ValueError("Scene graph exit length differs from its source record")
            target = raw[0] if kind in ("direct", "conditional", "door") else None
            exits[DIRECTIONS[prop_number]] = (kind, target)
        compiled[number] = exits
    if len(compiled) != len(source) or len(source) != len(declarations):
        raise ValueError("Scene graph does not match the declared room inventory")
    candidates = {}
    for identity, exits in source.items():
        directions = {row[0] for row in exits}
        if any(target is not None and target not in source for _, _, target, _ in exits):
            raise ValueError("Scene declaration references an unknown destination")
        candidates[identity] = {
            number for number, actual in compiled.items()
            if set(actual) == directions and all(actual[direction][0] == kind
                                                for direction, kind, _, _ in exits)}
    changed = True
    while changed:
        changed = False
        singles = [next(iter(values)) for values in candidates.values() if len(values) == 1]
        if len(set(singles)) != len(singles):
            raise ValueError("Scene graph association is not one-to-one")
        for identity, choices in candidates.items():
            remaining = {
                number for number in choices
                if not (len(choices) > 1 and number in singles)
                and all(target is None or compiled[number][direction][1] in candidates[target]
                        for direction, _, target, _ in source[identity])}
            if not remaining:
                raise ValueError("Scene graph contradicts the recovered declarations")
            if remaining != choices:
                candidates[identity] = remaining
                changed = True
    if any(len(choices) != 1 for choices in candidates.values()):
        raise ValueError("Scene graph association remains ambiguous")
    return {identity: next(iter(choices)) for identity, choices in candidates.items()}


def _documents(data, info, program):
    objects = _objects(data, table=info["objects"], count=250,
                       dynamic_end=info["static_memory"])
    associated = _associate_scenes(objects, room_root=82)
    if associated != {row[0]: row[1] for row in SCENE_SYMBOLS}:
        raise ValueError("Qualified scene graph identities changed")
    room_ids = {number: identity for identity, number in associated.items()}
    fact_ids = {number: identity for identity, number in _FACT_GLOBALS.items()}
    door_ids = {number: identity for identity, number in _DOOR_OBJECTS.items()}
    evidence = _Evidence(data, info["abbreviations"])
    uil = {
        "format": UIL_FORMAT, "id": "zork1.r88.scenes", "entry_scene": "west_of_house",
        "resources": evidence.resources, "scenes": {}, "facts": {}, "doors": {},
        "handlers": {"missing_direction": {"representation": "low_level_ir", "role": "exit"}},
        "missing_exit": "missing_direction",
    }
    udl = {
        "format": UDL_FORMAT, "source": copy.deepcopy(program["source"]),
        "initial_image_sha256": hashlib.sha256(data).hexdigest(),
        "witnesses": evidence.witnesses, "runtime_guards": [],
        "scenes": {}, "exits": {}, "facts": {}, "doors": {}, "handlers": {},
        "resources": evidence.resource_bindings,
        "symbol_provenance": {
            "repository": SOURCE_REPOSITORY, "revision": SOURCE_REVISION,
            "paths": ["1dungeon.zil", "1actions.zil", "gverbs.zil"],
            "association": "exit kinds/directions, recursive destination constraints and one-to-one room identity; no numeric-profile or text-name inputs",
            "association_count": 110,
            "runtime_dependency": "none; sanitized qualified naming profile ships with producer",
            "source_edition_identical": False,
            "narrative_source": "qualified binary; later source spelling differences are not imported",
        },
    }
    common = udl["runtime_guards"]
    common.append(evidence.add("header-layout", 8, 16, "dictionary, object, global and static-memory layout"))
    common.append(evidence.add("header-abbreviations", 24, 26, "abbreviation-table reference"))
    for name, start, end in (("walk-selection", 0x8AA4, 0x8B6C),
                             ("goto-header", 0x92B6, 0x92C3),
                             ("move-actor-effects", 0x9355, 0x935B),
                             ("remember-referent", 0x9530, 0x953B)):
        common.append(evidence.add(name, start, end, "qualified original scene primitive operations"))
    for start, end in ((0x8AAF, 0x8B6C), (0x9355, 0x935B), (0x9533, 0x953B)):
        cursor = start
        while cursor < end:
            instruction = verify_mapped_instruction(data, program, cursor)
            cursor = instruction["end"]
        if cursor != end:
            raise ValueError("Scene primitive span does not end at an instruction boundary")
    for resource, address in _RESOURCE_INSTRUCTIONS.items():
        instruction = decode_v3(data, address)
        if instruction["op"] != "print":
            raise ValueError("Scene refusal narrative operation changed")
        evidence.text(resource, instruction["text_offset"])
        udl["resources"][resource]["source_operation"] = address
    evidence.resources["newline"] = "\n"
    evidence.resource_bindings["newline"] = {
        "source_operation": 0x8ADE, "dependencies": ["walk-selection"]}

    for identity, number in _FACT_GLOBALS.items():
        address = info["globals"] + 2 * (number - 16)
        initial = _word(data, address)
        uil["facts"][identity] = {"type": "boolean", "initial": bool(initial)}
        udl["facts"][identity] = {
            "global": number, "address": address, "initial_value": initial,
            "interpretation": "nonzero", "mutable": True,
            "source_operation": 0x8B09,
            "setter_intent": "residual_ir",
            "witness": evidence.add(f"fact-{identity}-initial", address, address + 2,
                                     "initial selector value; read live, never frozen by a guard"),
        }
    for identity, number in _DOOR_OBJECTS.items():
        obj = objects[number]
        uil["doors"][identity] = {"name": obj["name"], "initial_open": 11 in obj["attributes"]}
        udl["doors"][identity] = {
            "object": number, "record": obj["record"], "attribute": 11,
            "address": obj["record"] + 1, "mask": 16, "mutable": True,
            "source_operation": 0x8B3C,
            "structure_guards": evidence.structure(obj),
            "name_dependencies": evidence.text_dependencies(obj["name_start"]),
        }

    def add_handler(identity, role, routine, property_guard=None):
        if identity in udl["handlers"]:
            old = udl["handlers"][identity]
            if any(old[key] != routine[key] for key in ("header", "entry", "locals")):
                raise ValueError("Qualified scene callback symbol has conflicting targets")
            return
        witness = evidence.add(f"routine-header-{routine['header']:x}",
                               routine["header"], routine["entry"], "resolved routine header and initial locals")
        uil["handlers"][identity] = {"representation": "low_level_ir", "role": role}
        udl["handlers"][identity] = {**routine, "guard_witnesses": [witness]}
        if property_guard:
            udl["handlers"][identity]["reference_witness"] = property_guard

    for identity, number, callback, has_description, declared_exits in SCENE_SYMBOLS:
        obj = objects[number]
        structure = evidence.structure(obj)
        scene = {"name": obj["name"], "exits": {}, "initial_traits": {
            "land": 6 in obj["attributes"], "naturally_lit": 20 in obj["attributes"],
            "ruined": 18 in obj["attributes"]}}
        binding = {"object": number, "record": obj["record"],
                   "property_table": obj["property_table"], "structure_guards": structure,
                   "name_dependencies": evidence.text_dependencies(obj["name_start"]), "exits": {}}
        if (11 in obj["properties"]) != has_description:
            raise ValueError("Qualified room description layout changed")
        if has_description:
            prop = obj["properties"][11]
            if prop["size"] != 2:
                raise ValueError("Scene long-description reference has an unsupported size")
            resource = identity + ".description"
            evidence.text(resource, 2 * _word(data, prop["address"]))
            scene["description"] = {"kind": "static", "resource": resource}
            guard = evidence.add(f"description-reference-{number}", prop["address"],
                                 prop["address"] + 2, "initial long-description reference; changes require residual execution")
            binding["description"] = {
                **prop, "resource": resource, "guard_witnesses": [*structure, guard],
                "presentation": "fallback after the room-event handler declines; original display policy remains residual"}
        if (17 in obj["properties"]) != bool(callback):
            raise ValueError("Qualified room callback layout changed")
        if callback:
            prop = obj["properties"][17]
            if prop["size"] != 2:
                raise ValueError("Scene callback reference has an unsupported size")
            routine = _routine(data, _word(data, prop["address"]))
            guard = evidence.add(f"scene-callback-reference-{number}", prop["address"],
                                 prop["address"] + 2, "resolved room-event callback reference")
            add_handler(callback, "room_event", routine, guard)
            scene["on_event"] = {"kind": "residual", "handler": callback}
            binding["handler"] = {"id": callback, "guard_witnesses": [*structure, guard]}
            if not has_description:
                scene["description"] = {"kind": "residual", "handler": callback}
        actual_directions = {DIRECTIONS[p] for p in obj["properties"] if p in DIRECTIONS}
        if actual_directions != {row[0] for row in declared_exits}:
            raise ValueError("Qualified room directional set differs from its source graph")
        for direction, kind, destination, qualifier in declared_exits:
            prop_number = next(p for p, name in DIRECTIONS.items() if name == direction)
            prop = obj["properties"][prop_number]
            exit_id = identity + ".exit." + direction
            definition, exit_binding = _lower_exit(
                data, prop, identity=exit_id, scene_ids=room_ids, fact_ids=fact_ids,
                door_ids=door_ids, handler=qualifier if kind == "routine" else None,
                evidence=evidence)
            if (definition["kind"] != kind or definition.get("destination") != destination
                    or (kind == "conditional" and definition["fact"] != qualifier)
                    or (kind == "door" and definition["door"] != qualifier)):
                raise ValueError("Qualified room exit differs from the recovered named graph")
            value_guard = evidence.add(f"exit-record-{prop['header']:x}", prop["header"],
                                       prop["address"] + prop["size"],
                                       "resolved exit layout and selector; modified records remain IR")
            exit_binding.update({"scene": identity, "direction": direction,
                                 "property": prop_number, "guard_witnesses": [*structure, value_guard]})
            if kind == "routine":
                add_handler(qualifier, "exit", exit_binding.pop("routine"), value_guard)
            scene["exits"][direction] = definition
            binding["exits"][direction] = exit_id
            udl["exits"][exit_id] = exit_binding
        uil["scenes"][identity] = scene
        udl["scenes"][identity] = binding

    udl["handlers"]["missing_direction"] = {
        "kind": "source_region", "entry": 0x8B6C, "end": 0x8BCB,
        "reason": "absence of an exit can include darkness, random risk and death",
        "guard_witnesses": [evidence.add("missing-direction-region", 0x8B6C, 0x8BCB,
                                          "unrecovered missing-direction behavior")],
    }
    udl["selection"] = {
        "header": 0x8AA4, "entry": 0x8AAF, "effect_entry": 0x8ABA,
        "locals": [0, 0, 0, 0, 0], "current_scene_global": 16,
        "direction_global": 134, "walk_action": 137,
        "direction_properties": {name: number for number, name in DIRECTIONS.items()},
        "source_operations": dict(_SELECTION_OPERATIONS),
        "residual_frame_locals": {
            "property_address": 1, "property_size": 2, "failure_resource": 3,
            "door_object": 4, "routine_result": 5,
        },
        "guard_witnesses": ["walk-selection", "remember-referent"],
        "refusal_return": 2,
        "residual_arrival": {"header": 0x92B6, "entry": 0x92C3,
                             "reason": "vehicles, light, hazards, event callbacks, scoring and presentation"},
        "referent": {"object_global": 123, "scene_global": 122,
                     "source_operations": [0x9533, 0x9536]},
    }
    udl["movement"] = {
        "header": 0x92B6, "entry": 0x92C3, "effect_entry": 0x9355,
        "continuation": 0x935B, "locals": [0, 1, 0, 0, 0, 0],
        "actor_global": 127, "current_scene_global": 16,
        "destination_local": 1, "vehicle_local": 5, "qualified_actor": 4,
        "source_operations": [0x9355, 0x9358],
        "guard_witnesses": ["goto-header", "move-actor-effects"],
        "requires": ["six-local GOTO frame", "vehicle local is zero",
                     "actor is the qualified adventurer", "actor parent equals current scene",
                     "destination is a named scene"],
        "scope": "on-foot relocation and current-scene assignment only; prelude/postlude stay residual",
    }
    udl["primitives"] = {
        "scene.select_exit": {
            "inputs": ["current_scene", "direction", "live named facts", "live named door states"],
            "definition": {
                "direct": "request travel to the named destination",
                "blocked": "emit the bound refusal resource and newline, then return fatal action result",
                "conditional": "nonzero live fact selects destination; zero selects custom or default refusal",
                "door": "open door selects destination; closed door selects custom refusal or named-door refusal and discourse update",
                "routine": "request the named residual routine; resolving its target does not recover its body",
                "missing": "request residual missing-direction behavior, including any darkness risk",
            },
            "original_operations": dict(_SELECTION_OPERATIONS),
            "realized_effects": ["travel request", "ordered narration", "remember mentioned door and current scene"],
            "unchanged": "selection does not relocate the actor or count a turn",
        },
        "scene.move_actor": {
            "inputs": ["current actor", "current scene", "named destination"],
            "requires": list(udl["movement"]["requires"]),
            "ordered_effects": ["move the actor into the destination", "set the current scene"],
            "original_operations": [0x9355, 0x9358],
            "source_fields": {"actor_global": 127, "destination_local": 1, "current_scene_global": 16},
            "residual_after": "light, hazards, entry callback, scoring, description, background events and turn completion",
        },
    }
    udl["qualification"] = {
        "status": "candidate", "scene_definitions": len(uil["scenes"]),
        "exit_definitions": len(udl["exits"]),
        "exit_kinds": {kind: sum(x["kind"] == kind for room in uil["scenes"].values()
                                 for x in room["exits"].values()) for kind in _EXIT_KINDS.values()},
        "all_game_intent_recovered": False,
        "recovered": ["named scenes", "explicit directional selection", "live exit predicates",
                      "refusal narration and closed-door discourse effect", "bounded on-foot relocation"],
        "residual": ["input parser", "room and routine-exit handler bodies", "missing direction hazards",
                     "most arrival behavior", "background events", "condition setters", "other game actions"],
        "proof_ceiling": "source-correspondence candidate; execution comparison is a separate receipt",
    }
    return uil, udl, _object_ids(objects, room_ids)


def recover_scenes(story, base_intents=None):
    """Export explicit scene semantics while preserving the supplied conversion.

    Only this exact R88 edition has a qualified symbol/layout profile. The
    bundled profile contains metadata, not copyrighted narrative or bytecode;
    those are extracted from the caller's own source into private outputs.
    """
    with Path(story).open("rb") as stream:
        raw = stream.read(MAX_STORY_FILE + 1)
    info = inspect_story_bytes(raw)
    if info["sha256"] != STORY_SHA256:
        raise ValueError("Scene recovery requires exact Zork I R88 / serial 840726")
    base = recover_intents(story) if base_intents is None else base_intents
    verify_intent_bindings(base)
    program = base["low_level_ir"]
    _check_ir_identity(raw, info, program)
    data = raw[:info["declared_bytes"]]
    uil, udl, object_ids = _documents(data, info, program)
    # This independent producer resolves action tables and object callback
    # references. Its UIL has its own strict schema rather than an opaque
    # extension that the scene evaluator could silently ignore.
    from .zork_scene_dispatch import recover_dispatch
    dispatch = recover_dispatch(raw, object_ids=object_ids)
    udl["dispatch"] = dispatch["udl"]
    udl["base_intents_sha256"] = canonical_digest(base)
    udl["uil_sha256"] = canonical_digest(uil)
    udl["dispatch_uil_sha256"] = canonical_digest(dispatch["uil"])
    package = {"format": FORMAT, "base_intents": copy.deepcopy(base),
               "uil": uil, "dispatch_uil": dispatch["uil"], "udl": udl}
    verify_bindings(package)
    return package


def verify_bindings(package):
    """Verify package/source integrity; route-equivalence requires execution.

    Integrity checks never promote unresolved handler bodies to semantic UIL.
    The independent player additionally checks descriptor semantics and live
    guards before replacing an original operation.
    """
    if not isinstance(package, dict) or package.get("format") != FORMAT:
        raise ValueError("Invalid Zork scene package format")
    try:
        base, uil, udl, dispatch = (package[k] for k in ("base_intents", "uil", "udl", "dispatch_uil"))
        verify_intent_bindings(base)
        if uil["format"] != UIL_FORMAT or udl["format"] != UDL_FORMAT:
            raise ValueError("Invalid scene UIL or UDL format")
        if (canonical_digest(base) != udl["base_intents_sha256"]
                or canonical_digest(uil) != udl["uil_sha256"]
                or canonical_digest(dispatch) != udl["dispatch_uil_sha256"]):
            raise ValueError("Scene package binding digest changed")
        if udl["source"] != base["low_level_ir"]["source"]:
            raise ValueError("Scene and preserved package source identities differ")
        data = bytes.fromhex(base["low_level_ir"]["memory"]["initial"])
        if hashlib.sha256(data).hexdigest() != udl["initial_image_sha256"]:
            raise ValueError("Scene initial source image changed")
        for witness in udl["witnesses"].values():
            verify_witness(data, witness)
        for identity in udl["runtime_guards"]:
            if identity not in udl["witnesses"]:
                raise ValueError("Scene runtime guard has no source witness")
        for address in (*udl["selection"]["source_operations"].values(),
                        *udl["movement"]["source_operations"]):
            verify_mapped_instruction(data, base["low_level_ir"], address)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete scene package bindings") from exc
    return {"source_sha256": udl["source"]["sha256"],
            "base_intents_sha256": udl["base_intents_sha256"], "uil_sha256": udl["uil_sha256"],
            "dispatch_uil_sha256": udl["dispatch_uil_sha256"],
            "scenes": len(uil["scenes"]), "exits": len(udl["exits"]),
            "witnesses": len(udl["witnesses"]),
            "all_game_intent_recovered": False}
