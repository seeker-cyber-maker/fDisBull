#!/usr/bin/env python3
"""Validate and package stopped SCUMM model facts without executing a guest.

The native CPU owns decoding and execution. This standard-library consumer
checks source identity, extents, schemas and witness consistency; it does not
implement a second SCUMM decoder, replay missing history or render a game.

SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re


SCHEMA = "fdisbull-scumm-processor-scene-packet-1"
SCENE_SCHEMA = "fdisbull-scumm-scene-1"
EVENTS_SCHEMA = "fdisbull-scumm-events-2"
DECODE_SCHEMA = "fdisbull-scumm-early-decode-1"
RESOURCE_TYPES = ("costume", "room", "script", "sound")
CONTROL_VARS = ("21", "26", "27", "28", "29", "38")
DECODE_FIELDS = ("op", "next", "branch", "conditional", "subop",
                 "payload_pc", "payload_size", "args")
U64_MAX = (1 << 64) - 1


class SceneInputError(ValueError):
    """A capture is malformed or its source-bound witnesses contradict."""


def _require(condition, message):
    if not condition:
        raise SceneInputError(message)


def _object(value, fields, label, *, exact=False):
    _require(type(value) is dict and set(fields) <= value.keys(),
             f"{label} requires an object with {', '.join(fields)}")
    if exact:
        _require(set(value) == set(fields), f"{label} has unexpected fields")
    return value


def _integer(value, low, high, label):
    _require(type(value) is int and low <= value <= high,
             f"{label} must be an integer in {low}..{high}")
    return value


def _array(value, low, high, label):
    _require(type(value) is list and low <= len(value) <= high,
             f"{label} must be a list of {low}..{high} items")
    return value


def _hash(value, label):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"{label} must be a lowercase SHA-256")


def _digest(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise SceneInputError("Capture must contain ordinary finite JSON values") from error
    _require(len(encoded) <= 32 * 1024 * 1024, "Capture exceeds the 32 MiB JSON bound")
    return sha256(encoded).hexdigest()


def _source(source, code):
    _object(source, ("version", "code_sha256", "code_size", "profile",
                     "manifest_sha256", "source_receipt_sha256", "script_id"),
            "source")
    _integer(source["version"], 0, 2, "source.version")
    _integer(source["code_size"], 1, 65536, "source.code_size")
    _hash(source["code_sha256"], "source.code_sha256")
    _require(source["code_size"] == len(code)
             and source["code_sha256"] == sha256(code).hexdigest(),
             "Source does not identify the exact supplied code")
    _require(source["profile"] in ("none", "amiga-v2-isolated"), "Unknown source profile")
    _integer(source["script_id"], 0, 255, "source.script_id")
    if source["profile"] == "none":
        _require(source["manifest_sha256"] == source["source_receipt_sha256"] == ""
                 and source["script_id"] == 0, "Raw profile has a resource-bank identity")
    else:
        _require(source["version"] == 2 and source["script_id"] > 0,
                 "The resource profile requires v2 and a nonzero script ID")
        _hash(source["manifest_sha256"], "source.manifest_sha256")
        _hash(source["source_receipt_sha256"], "source.source_receipt_sha256")


def _identity(envelope, source, code):
    _source(envelope["source"], code)
    _require(envelope["source"] == source, "Capture sources/profile/catalogs differ")
    if "version" in envelope:
        _integer(envelope["version"], 0, 2, "legacy version")
        _require(envelope["version"] == source["version"], "Legacy version disagrees with source")
    if "sha256" in envelope:
        _require(envelope["sha256"] == source["code_sha256"], "Legacy hash disagrees with source")


def _observation(value, retired):
    _object(value, ("mask", "capacity", "count", "sequence", "eligible", "stored",
                    "dropped", "helper_calls"), "observation")
    _integer(value["mask"], 0, 3, "observation.mask")
    _integer(value["capacity"], 0, 4096, "observation.capacity")
    _integer(value["count"], 0, value["capacity"], "observation.count")
    for key in ("sequence", "helper_calls"):
        _integer(value[key], 0, U64_MAX, "observation." + key)
    for key in ("eligible", "stored", "dropped"):
        for count in _array(value[key], 2, 2, "observation." + key):
            _integer(count, 0, U64_MAX, "observation." + key)
    _require(value["sequence"] == sum(value["eligible"]), "Eligible sequence accounting differs")
    _require(value["count"] == sum(value["stored"]), "Stored count accounting differs")
    _require(max(value["eligible"]) <= value["helper_calls"] <= retired,
             "Observation calls disagree with eligibility or retirement accounting")
    for channel in (0, 1):
        _require(value["eligible"][channel] == value["stored"][channel] + value["dropped"][channel],
                 "Per-channel loss accounting differs")
        _require(value["eligible"][channel] <= retired, "Channel eligibility exceeds retirements")


def _actor(actor, code):
    _object(actor, ("id", "bound", "x", "y", "room", "costume", "sound",
                    "talk_color", "name", "palette"), "actor")
    _integer(actor["id"], 0, 31, "actor.id")
    _integer(actor["bound"], 0, 1, "actor.bound")
    for key in ("x", "y"):
        _integer(actor[key], 0, 65535, "actor." + key)
    for key in ("room", "costume", "sound", "talk_color"):
        _integer(actor[key], 0, 255, "actor." + key)
    for value in _array(actor["palette"], 32, 32, "actor.palette"):
        if value is not None:
            _integer(value, 0, 255, "actor.palette entry")
    name = _object(actor["name"], ("pc", "size", "bytes"), "actor.name")
    pc = _integer(name["pc"], 0, len(code), "actor.name.pc")
    size = _integer(name["size"], 0, 509, "actor.name.size")
    _require(pc + size <= len(code) and type(name["bytes"]) is str
             and name["bytes"] == code[pc:pc + size].hex(), "Actor name bytes/extent differ from code")
    if pc == 0:
        _require(size == 0, "An unassigned actor name must be empty")
    else:
        _require(pc + size < len(code) and code[pc + size] == 0
                 and 0 not in code[pc:pc + size], "Assigned actor name lacks its bounded terminator")


def _control(control, *, snapshot):
    byte_fields = ("user_state", "current_room", "camera_mode", "saved_user_state",
                   "saved_room", "saved_camera_mode")
    bit_fields = ("user_put", "cursor_visible", "cutscene_active")
    word_fields = ("saved_cursor", "override_script", "sentence_count")
    _object(control, byte_fields + bit_fields + word_fields + ("override_pc", "ui_revision", "vars"),
            "control")
    for fields, high in ((byte_fields, 255), (bit_fields, 1), (word_fields, 65535)):
        for key in fields:
            _integer(control[key], 0, high, "control." + key)
    _integer(control["override_pc"], 0, (1 << 32) - 1, "control.override_pc")
    _integer(control["ui_revision"], 0, U64_MAX, "control.ui_revision")
    variables = _object(control["vars"], CONTROL_VARS, "control.vars", exact=True)
    for value in variables.values():
        _integer(value, 0, 65535, "control variable")
    if snapshot:
        _object(control, ("default_talk_color",), "snapshot control")
        _integer(control["default_talk_color"], 0, 255, "control.default_talk_color")
    else:
        _require("default_talk_color" not in control, "Control event includes unrelated global color")


def _resource(resource):
    _object(resource, ("size", "available", "resident", "locked", "sha256"), "resource")
    _integer(resource["size"], 0, 65535, "resource.size")
    for key in ("available", "resident", "locked"):
        _require(type(resource[key]) is bool, "Resource flags must be JSON booleans")
    _require(not resource["resident"] or resource["available"], "Resident resource lacks available bytes")
    if resource["available"]:
        _require(resource["size"] >= 4, "Available resource lacks its four-byte header")
        _hash(resource["sha256"], "resource.sha256")
    else:
        _require(resource["size"] == 0 and resource["sha256"] == "",
                 "Unavailable resource has a byte identity")


def _slot(value, counts):
    _object(value, ("type", "id"), "resource slot")
    _require(value["type"] in RESOURCE_TYPES, "Unknown resource type")
    _integer(value["id"], 0, 255, "resource.id")
    _require(value["id"] < counts[value["type"]], "Resource slot exceeds its declared count")
    return value["type"], value["id"]


def _scene(scene, code):
    _object(scene, ("schema", "source", "checkpoint", "observation", "actors", "resources", "control"),
            "scene")
    _require(scene["schema"] == SCENE_SCHEMA, "Unsupported scene schema")
    _source(scene["source"], code)
    checkpoint = _object(scene["checkpoint"], ("trace_epoch", "control_generation", "retired", "pc",
                                               "status", "fault", "fault_opcode", "blocked_reason"),
                         "checkpoint")
    for key in ("trace_epoch", "control_generation", "retired"):
        _integer(checkpoint[key], 0, U64_MAX, "checkpoint." + key)
    _integer(checkpoint["pc"], 0, len(code), "checkpoint.pc")
    _integer(checkpoint["status"], 0, 6, "checkpoint.status")
    _integer(checkpoint["fault"], 0, 8, "checkpoint.fault")
    _integer(checkpoint["fault_opcode"], 0, 255, "checkpoint.fault_opcode")
    _require((checkpoint["status"] == 5) == (checkpoint["fault"] != 0),
             "Fault code and endpoint status disagree")
    _require(checkpoint["blocked_reason"] in ("none", "unimplemented_effect", "resource_bytes_unavailable",
                                                "room_mapper_required", "nested_cutscene", "sentence_script_owner"),
             "Unknown blocked reason")
    _observation(scene["observation"], checkpoint["retired"])
    actors = _array(scene["actors"], 32, 32, "actors")
    for actor in actors:
        _actor(actor, code)
    _require({actor["id"] for actor in actors} == set(range(32)), "Actor inventory has duplicates or omissions")
    _control(scene["control"], snapshot=True)
    resources = _object(scene["resources"], ("counts", "entries"), "resources")
    counts = _object(resources["counts"], RESOURCE_TYPES, "resource counts", exact=True)
    for count in counts.values():
        _integer(count, 0, 256, "resource count")
    entries = {}
    for entry in _array(resources["entries"], 0, 1024, "resource entries"):
        slot = _slot(entry, counts)
        _resource(entry)
        _require(slot not in entries, "Duplicate resource slot")
        _require(entry["available"] or entry["resident"] or entry["locked"],
                 "Untouched unavailable resource should remain implicit")
        entries[slot] = entry
    if scene["source"]["profile"] == "none":
        _require(not any(counts.values()) and not entries, "Raw profile has resource slots")
    else:
        active = entries.get(("script", scene["source"]["script_id"]))
        _require(active is not None and active["available"] and active["resident"]
                 and active["size"] == len(code) + 4, "Active script lacks the bound code extent/residency")
    return entries


def _decoded(row, pc, size, code, *, success=True):
    _object(row, DECODE_FIELDS, "decoded instruction")
    _require(type(row["op"]) is str and re.fullmatch(r"[a-z_]{1,64}", row["op"]) is not None,
             "Invalid native operation name")
    _integer(row["next"], 0, 65536, "decoded.next")
    _integer(row["branch"], -(1 << 31), (1 << 31) - 1, "decoded.branch")
    _integer(row["conditional"], 0, 1, "decoded.conditional")
    _integer(row["subop"], 0, 255, "decoded.subop")
    _integer(row["payload_pc"], 0, len(code), "decoded.payload_pc")
    _integer(row["payload_size"], 0, 514, "decoded.payload_size")
    for arg in _array(row["args"], 0, 3, "decoded.args"):
        _array(arg, 3, 3, "encoded argument")
        _integer(arg[0], 0, 2, "argument kind")
        _integer(arg[2], 1, 2, "argument width")
        _integer(arg[1], 0, (1 << (8 * arg[2])) - 1, "argument value")
        _require(arg[0] == 0 or arg[2] == 1, "Variable/destination index must have byte width")
    if success:
        _require(row["next"] == pc + size <= len(code), "Encoded successor differs from instruction extent")
        if row["payload_pc"] or row["payload_size"]:
            _require(pc < row["payload_pc"] <= row["next"]
                     and row["payload_pc"] + row["payload_size"] <= row["next"],
                     "Payload lies outside its instruction")


def _extent(row, code):
    _object(row, ("pc", "opcode", "size", "bytes"), "instruction extent")
    pc = _integer(row["pc"], 0, len(code) - 1, "instruction.pc")
    size = _integer(row["size"], 1, 514, "instruction.size")
    _integer(row["opcode"], 0, 255, "instruction.opcode")
    _require(pc + size <= len(code) and row["opcode"] == code[pc]
             and type(row["bytes"]) is str and row["bytes"] == code[pc:pc + size].hex(),
             "Instruction bytes/opcode/extent differ from code")
    return pc, size


def _pages(pages, source, code):
    _require(type(pages) in (list, tuple) and len(pages) <= 1024, "Decode pages must be a bounded sequence")
    by_pc, previous_end = {}, None
    for page_index, page in enumerate(pages):
        _object(page, ("schema", "source", "start_pc", "limit", "next_pc", "stop", "records"), "decode page")
        _require(page["schema"] == DECODE_SCHEMA, "Unsupported decode schema")
        _identity(page, source, code)
        cursor = _integer(page["start_pc"], 0, len(code), "decode start_pc")
        if previous_end is not None:
            _require(cursor == previous_end,
                     "Decode pages must cover one contiguous selected listing")
        limit = _integer(page["limit"], 1, 64, "decode limit")
        records = _array(page["records"], 0, limit, "decode records")
        fault = False
        for index, row in enumerate(records):
            _object(row, ("pc", "opcode", "fault", "size") + DECODE_FIELDS, "static instruction")
            _integer(row["pc"], 0, len(code) - 1, "static instruction.pc")
            _integer(row["opcode"], 0, 255, "static instruction.opcode")
            _require(row["pc"] == cursor and row["opcode"] == code[cursor], "Static listing location differs")
            _integer(row["fault"], 0, 8, "static instruction.fault")
            if row["fault"]:
                _integer(row["size"], 0, 514, "failed instruction.size")
                _decoded(row, cursor, row["size"], code, success=False)
                _require("bytes" not in row and index == len(records) - 1,
                         "Failed decode invents complete bytes or is not the terminal row")
                fault = True
            else:
                pc, size = _extent(row, code)
                _decoded(row, pc, size, code)
                _require(pc not in by_pc, "Duplicate static instruction address")
                by_pc[pc] = row
                cursor += size
        _integer(page["next_pc"], 0, len(code), "decode next_pc")
        _require(page["next_pc"] == cursor, "Decode page end differs from successful extents")
        expected_stop = "decode_fault" if fault else "end" if cursor == len(code) else "limit"
        _require(page["stop"] == expected_stop, "Decode stop disagrees with its records")
        if expected_stop == "limit":
            _require(len(records) == limit, "Decode limit stop lacks the requested number of records")
        if page_index + 1 < len(pages):
            _require(expected_stop == "limit", "Decode pages continue beyond an end/fault boundary")
        previous_end = cursor
    complete = bool(pages) and pages[0]["start_pc"] == 0 and pages[-1]["stop"] == "end"
    return by_pc, complete


def _scene_change(row, scene, code, resources):
    kind = row["kind"]
    if kind == "actor":
        _object(row, ("before_actor", "after_actor"), "actor event")
        before, after = row["before_actor"], row["after_actor"]
        _actor(before, code)
        _actor(after, code)
        _require(before["id"] == after["id"] != 0 and before != after, "Invalid/no-change actor event")
        if "actor" in row:
            _integer(row["actor"], 1, 31, "legacy actor")
            _require(row["actor"] == before["id"], "Legacy actor identity differs")
        for prefix, actor in (("before", before), ("after", after)):
            if prefix in row:
                _require(row[prefix] == [actor["bound"], actor["x"], actor["y"]],
                         "Legacy placement differs from complete actor")
            if prefix + "_metadata" in row:
                _require(row[prefix + "_metadata"] == [actor["costume"], actor["sound"], actor["talk_color"],
                                                       actor["name"]["pc"], actor["name"]["size"]],
                         "Legacy metadata differs from complete actor")
    elif kind == "default_talk_color":
        _object(row, ("before_color", "after_color"), "global color event")
        for key in ("before_color", "after_color"):
            _integer(row[key], 0, 255, key)
        _require(row["before_color"] != row["after_color"], "Unchanged color cannot be a committed delta")
    elif kind == "resource":
        _require(scene["source"]["profile"] == "amiga-v2-isolated", "Resource event requires its runtime profile")
        _object(row, ("before_resource", "after_resource"), "resource event")
        slot = _slot(row, scene["resources"]["counts"])
        before, after = row["before_resource"], row["after_resource"]
        _resource(before)
        _resource(after)
        empty = {"size": 0, "available": False, "resident": False, "locked": False, "sha256": ""}
        current = resources.get(slot, empty)
        for key in ("size", "available", "sha256"):
            _require(before[key] == after[key] == current[key], "Immutable resource binding changed")
        _require(before != after, "Unchanged resource cannot be a committed delta")
    elif kind == "control":
        _require(scene["source"]["profile"] == "amiga-v2-isolated", "Control event requires its runtime profile")
        _object(row, ("before_control", "after_control"), "control event")
        _control(row["before_control"], snapshot=False)
        _control(row["after_control"], snapshot=False)
        _require(row["before_control"] != row["after_control"], "Unchanged control cannot be a committed delta")
        # Generic scalar instructions can write these same variables. Comparing
        # successive control records as if they were a complete chain is wrong.
    else:
        raise SceneInputError("Unknown committed scene kind")


def _events(events, scene, code, resources, static_rows):
    if events is None:
        return [], []
    _object(events, ("schema", "source", "epoch", "control_generation", "observation", "records"), "events")
    _require(events["schema"] == EVENTS_SCHEMA, "Unsupported events schema")
    _identity(events, scene["source"], code)
    checkpoint, observation = scene["checkpoint"], scene["observation"]
    _integer(events["epoch"], 0, U64_MAX, "events.epoch")
    _integer(events["control_generation"], 0, U64_MAX, "events.control_generation")
    _observation(events["observation"], checkpoint["retired"])
    _require(events["epoch"] == checkpoint["trace_epoch"]
             and events["control_generation"] == checkpoint["control_generation"]
             and events["observation"] == observation, "Events and scene are not the same stopped checkpoint")
    records = _array(events["records"], observation["count"], observation["count"], "retained records")
    previous_seq, previous_retired, previous_generation, previous = 0, 0, 0, None
    stored, retirements, changes = [0, 0], [], []
    for row in records:
        _object(row, ("seq", "retired", "control_generation", "channel", "kind", "pc", "next", "opcode",
                      "size", "bytes", "decoded", "resolved", "destination", "branch_taken"), "event")
        _integer(row["seq"], previous_seq + 1, observation["sequence"], "event.seq")
        _integer(row["retired"], max(1, previous_retired), checkpoint["retired"], "event.retired")
        _integer(row["control_generation"], previous_generation, checkpoint["control_generation"],
                 "event.control_generation")
        channel = _integer(row["channel"], 0, 1, "event.channel")
        _require((channel == 0) == (row["kind"] == "retire"), "Event channel and kind disagree")
        pc, size = _extent(row, code)
        _decoded(row["decoded"], pc, size, code)
        _integer(row["next"], 0, len(code), "event.next")
        decoded = row["decoded"]
        resolved = _array(row["resolved"], len(decoded["args"]), len(decoded["args"]), "event.resolved")
        for argument, value in zip(decoded["args"], resolved):
            _integer(value, 0, 65535, "resolved value")
            if argument[0] == 0:
                _require(value == argument[1], "Resolved immediate differs from its encoded value")
        if row["destination"] is not None:
            destination = _object(row["destination"], ("index", "before", "after"), "destination")
            _integer(destination["index"], 0, 255, "destination.index")
            for key in ("before", "after"):
                _integer(destination[key], 0, 65535, "destination." + key)
        is_branch = decoded["op"] == "jump" or decoded["conditional"] == 1
        if is_branch:
            _require(type(row["branch_taken"]) is bool, "Branch lacks a native taken/not-taken result")
            _require(decoded["op"] != "jump" or row["branch_taken"], "Unconditional jump was not taken")
            if row["branch_taken"]:
                _require(0 <= decoded["branch"] < len(code), "Retired branch has an invalid taken target")
        else:
            _require(row["branch_taken"] is None, "Nonbranch instruction has a branch result")
        expected_next = decoded["branch"] if row["branch_taken"] else decoded["next"]
        _require(row["next"] == expected_next, "Actual successor disagrees with the native branch result")
        if pc in static_rows:
            static = static_rows[pc]
            _require(all(decoded[key] == static[key] for key in DECODE_FIELDS)
                     and row["bytes"] == static["bytes"], "Live and static instruction witnesses disagree")
        if previous is not None and row["retired"] == previous_retired:
            common = ("control_generation", "pc", "next", "opcode", "size", "bytes", "decoded",
                      "resolved", "destination", "branch_taken")
            _require(previous["channel"] == 0 and channel == 1
                     and row["seq"] == previous_seq + 1
                     and all(row[key] == previous[key] for key in common),
                     "Same-retirement records disagree or violate DISASM-before-SCENE order")
        if channel:
            _scene_change(row, scene, code, resources)
            changes.append(row)
        else:
            retirements.append(row)
        stored[channel] += 1
        previous_seq, previous_retired, previous_generation, previous = (
            row["seq"], row["retired"], row["control_generation"], row)
    _require(stored == observation["stored"], "Retained channel counts disagree with observation")
    # Capacity can grow after a full buffer dropped events, so retained records
    # need not be a contiguous prefix. Sequence gaps remain explicitly lost.
    _require(previous_seq - len(records) <= sum(observation["dropped"]), "Unexplained retained sequence gaps")
    return retirements, changes


def build_scene_packet(*, code, scene, events=None, decode_pages=()):
    """Return detached source-bound facts from a caller's stopped capture.

    The caller serializes VM access and captures scene/events/scene, requiring
    identical scene reads. This pure function cannot establish that live lock.
    History completeness is deliberately false even when no drops are reported.
    Static pages cover one contiguous selected listing and do not prove reachability.
    """
    _require(type(code) is bytes and 1 <= len(code) <= 65536, "Code must be exact immutable 1..65536-byte input")
    resources = _scene(scene, code)
    static_rows, listing_complete = _pages(decode_pages, scene["source"], code)
    retirements, changes = _events(events, scene, code, resources, static_rows)
    evidence = {"code_sha256": sha256(code).hexdigest(), "scene_sha256": _digest(scene),
                "events_sha256": None if events is None else _digest(events),
                "decode_pages_sha256": _digest(decode_pages)}
    return deepcopy({
        "schema": SCHEMA, "source": scene["source"], "checkpoint": scene["checkpoint"],
        "observation": scene["observation"], "actors": scene["actors"],
        "resources": scene["resources"], "control": scene["control"],
        "disassembly": {"static_pages": list(decode_pages), "retirements": retirements,
                        "static_listing_complete": listing_complete, "static_reachability_qualified": False},
        "committed_changes": changes, "evidence": evidence,
        "qualification": {"current_snapshot": True, "snapshot_scope": "implemented_native_model",
                          "history_scope": "retained_native_records" if events is not None else "not_supplied",
                          "history_complete": False, "control_variable_history_complete": False,
                          "actor_visibility": False, "room_rendering": False,
                          "costume_decode": False, "screen_presentation": False},
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--decode-pages", type=Path, help="JSON array of consecutive native decode pages")
    parser.add_argument("--output", type=Path, required=True, help="New private JSON output file")
    args = parser.parse_args()
    try:
        packet = build_scene_packet(
            code=args.code.read_bytes(), scene=json.loads(args.scene.read_text(encoding="utf-8")),
            events=None if args.events is None else json.loads(args.events.read_text(encoding="utf-8")),
            decode_pages=() if args.decode_pages is None else json.loads(args.decode_pages.read_text(encoding="utf-8")),
        )
        text = json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
