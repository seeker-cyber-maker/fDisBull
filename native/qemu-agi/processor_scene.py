"""Derive scene inputs from CPU facts and a complete stopped native capture.

This first consumer admits an observed straight-line fragment. It validates
committed transitions using the existing native journal contract; it does not
execute AGI, infer original room state, or supply missing presentation policy.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from binding_scene_trial import _validate_journal
from draw_intent_harness import EVENTS_SCHEMA
from draw_intent_trial import validate_intent, validate_intent_reset
from harness import HarnessError
from processor_harness import NativeAGIProcessor, _integer, _same


SCHEMA = "fdisbull-agi-processor-scene-plan-1"


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _mapping_rows(mappings, code, instructions):
    if type(mappings) is not list or not 1 <= len(mappings) <= 128:
        raise HarnessError("Scene plan requires explicit bounded source mappings")
    cursor = 0
    for segment in mappings:
        if type(segment) is not dict or set(segment) != {"kind", "fragment_span", "source"} \
                or segment["kind"] not in ("authored", "original"):
            raise HarnessError("Invalid scene source mapping")
        span = segment["fragment_span"]
        if type(span) is not list or len(span) != 2 \
                or not _integer(span[0], 0, len(code)) or span[0] != cursor \
                or not _integer(span[1], cursor + 1, len(code)):
            raise HarnessError("Scene source mappings must exactly cover contiguous code")
        source = segment["source"]
        if segment["kind"] == "authored":
            if source is not None:
                raise HarnessError("Authored bytes cannot claim an original source address")
        else:
            if type(source) is not dict or set(source) != {"logic", "resource_sha256", "code_span", "payload_span"} \
                    or not _integer(source["logic"], 0, 255) \
                    or type(source["resource_sha256"]) is not str \
                    or len(source["resource_sha256"]) != 64 \
                    or any(c not in "0123456789abcdef" for c in source["resource_sha256"]):
                raise HarnessError("Original mapping lacks exact LOGIC identity")
            for key, minimum in (("code_span", 0), ("payload_span", 2)):
                original = source[key]
                if type(original) is not list or len(original) != 2 \
                        or not _integer(original[0], minimum, 65535) \
                        or not _integer(original[1], original[0] + 1, 65537) \
                        or original[1] - original[0] != span[1] - span[0]:
                    raise HarnessError("Original source extent differs from copied bytes")
            if source["payload_span"] != [value + 2 for value in source["code_span"]]:
                raise HarnessError("Original code and payload coordinates disagree")
        cursor = span[1]
    if cursor != len(code):
        raise HarnessError("Scene source mappings omit bytes")
    result = {}
    for row in instructions:
        segment = next((item for item in mappings
                        if item["fragment_span"][0] <= row["pc"] < item["fragment_span"][1]), None)
        if segment is None or row["pc"] + row["size"] > segment["fragment_span"][1]:
            raise HarnessError("Native instruction crosses a source mapping boundary")
        original = segment["source"]
        if original is not None:
            delta = row["pc"] - segment["fragment_span"][0]
            original = {"logic": original["logic"], "resource_sha256": original["resource_sha256"],
                        "code_pc": original["code_span"][0] + delta,
                        "payload_offset": original["payload_span"][0] + delta}
        result[row["pc"]] = {"kind": segment["kind"], "original_source_address": original}
    return result


def _actor_inputs(row):
    return [operand["value"] for operand in row["operands"]
            if operand["role"] == "actor" and operand["kind"] == "actor"]


def derive_scene_plan(*, code, pages, catalog, initial, state, events, source_mappings, legacy=None):
    """Derive actors, resources and endpoint without using scene recipe labels.

    ``source_mappings`` covers the raw fragment with authored/original spans.
    ``legacy`` optionally contains selected_actors, views and execution_endpoint
    declarations; contradictions are reported, never used as reconstruction
    inputs. Snapshot, static listing, retired history and pending intent retain
    separate evidence. Variable resource values come only from their matching
    retirement records, never from the final variable array.
    """
    initial = validate_intent_reset(initial, code=code, catalog=catalog)
    state = validate_intent(state, code=code, catalog=catalog)
    processor = NativeAGIProcessor(code, pages)
    if not _same(processor.source, state["source"]) or not _same(initial["source"], state["source"]):
        raise HarnessError("Static records and native capture have different source/profile/catalog identities")
    instructions = processor.instructions
    cursor = 0
    for row in instructions:
        if row["pc"] != cursor:
            raise HarnessError("Scene planning requires a contiguous CPU listing from PC zero")
        cursor += row["size"]
    mapped = _mapping_rows(source_mappings, code, instructions)
    by_pc = {row["pc"]: row for row in instructions}
    guest = state["guest"]
    if type(events) is not dict or type(events.get("events")) is not list:
        raise HarnessError("Scene planning requires a complete native journal")
    retirements = [event for event in events["events"]
                   if type(event) is dict and event.get("kind") == "retire"]
    pending = guest["pending_effect"]
    endpoint_pc = guest["pc"]
    endpoint = {"kind": guest["status"], "pc": endpoint_pc,
                "retired": False, "committed": False}
    if guest["status"] == "return":
        if not retirements or type(retirements[-1].get("pc")) is not int:
            raise HarnessError("Native return lacks its retirement witness")
        endpoint_pc = retirements[-1]["pc"]
        row = by_pc.get(endpoint_pc)
        if row is None or row["operation"] != "control.return" \
                or endpoint_pc + row["size"] != guest["pc"] or guest["fault"] is not None:
            raise HarnessError("Native return disagrees with the CPU instruction record")
        endpoint = {"kind": "authored_return" if mapped[endpoint_pc]["kind"] == "authored" else "return",
                    "pc": endpoint_pc, "retired": True, "committed": True,
                    "bytes": deepcopy(row["bytes"]), "source_kind": mapped[endpoint_pc]["kind"],
                    "original_source_address": deepcopy(mapped[endpoint_pc]["original_source_address"])}
        expected_rows = [item for item in instructions if item["pc"] <= endpoint_pc]
    else:
        expected_rows = [item for item in instructions if item["pc"] < endpoint_pc]
        if pending is not None:
            row = by_pc.get(endpoint_pc)
            if row is None or row["operation"] != "object.draw" \
                    or row["execution_support"] != "pending_host" \
                    or _actor_inputs(row) != [pending["actor"]] \
                    or not _same(row["bytes"], pending["bytes"]):
                raise HarnessError("Pending native request differs from the CPU record")
            endpoint = {"kind": "pending_draw", "pc": endpoint_pc,
                        "retired": False, "committed": False,
                        "source_kind": mapped[endpoint_pc]["kind"],
                        "original_source_address": deepcopy(mapped[endpoint_pc]["original_source_address"]),
                        "descriptor": deepcopy(pending),
                        "committed_pose": deepcopy(guest["actors"][pending["actor"]])}
        elif guest["status"] == "fault":
            endpoint["fault"] = deepcopy(guest["fault"])
    expected = []
    path_end = 0
    for index, row in enumerate(expected_rows):
        if row["pc"] != path_end or row["execution_support"] != "native":
            raise HarnessError("Observed path is outside this straight-line scene planner")
        path_end += row["size"]
        returning = guest["status"] == "return" and index == len(expected_rows) - 1
        if returning:
            if row["operation"] != "control.return" or row["successors"]:
                raise HarnessError("Return boundary has inconsistent native successors")
        elif len(row["successors"]) != 1 or row["successors"][0]["kind"] != "fallthrough" \
                or row["successors"][0]["pc"] != path_end:
            raise HarnessError("Observed control flow requires a different scene analysis")
        expected.append({"fragment_pc": row["pc"], "opcode": row["opcode"], "bytes": row["bytes"]})
    if path_end != guest["pc"]:
        raise HarnessError("Native stopped PC is outside the described straight-line prefix")
    actor_ops = tuple({row["opcode"] for row in expected_rows if _actor_inputs(row)})
    journal = _validate_journal(initial, state, events, code=code, expected=expected,
                                schema=EVENTS_SCHEMA, actor_ops=actor_ops)
    by_retirement = {}
    for event in retirements:
        by_retirement.setdefault(event["pc"], []).append(event)
    current_retirement = None
    for event in events["events"]:
        if event["kind"] == "retire":
            current_retirement = event
            continue
        row = by_pc[event["pc"]]
        if event["kind"] == "actor" and _actor_inputs(by_pc[event["pc"]]) != [event["actor"]]:
            raise HarnessError("Committed actor transition contradicts typed CPU operand")
        if event["kind"] == "view_load" and row["operation"] != "resource.load_view":
            raise HarnessError("Committed VIEW load contradicts CPU operation")
        # These checks join two native witnesses; they do not compute an AGI
        # effect. Unchanged writes may legitimately have no SCENE record.
        value = current_retirement.get("resolved_value")
        if value is not None:
            if event["kind"] == "view_load" and event["view"] != value:
                raise HarnessError("Resolved VIEW value contradicts its committed load transition")
            field = {"object.set_view": "view", "object.set_loop": "loop",
                     "object.set_cel": "cel"}.get(row["operation"])
            if event["kind"] == "actor" and field is not None:
                if len([operand for operand in row["operands"] if operand["role"] == field]) != 1 \
                        or event["after"][field] != value:
                    raise HarnessError("Resolved ordinal/resource value contradicts its committed actor transition")
    references, unresolved = [], []
    observed_views, static_views = set(), set()
    for row in instructions:
        for operand in row["operands"]:
            if operand["role"] not in ("view", "loop", "cel"):
                continue
            reference = {"pc": row["pc"], "operation": row["operation"],
                         "operand": deepcopy(operand), "observations": [],
                         "source_mapping": deepcopy(mapped[row["pc"]])}
            if operand["kind"] != "variable":
                reference["static_value"] = operand["value"]
                if operand["role"] == "view":
                    static_views.add(operand["value"])
            for event in by_retirement.get(row["pc"], []):
                value = event.get("resolved_value")
                observation = {"seq": event["seq"], "retired": event["retired"],
                               "evidence": "native_retirement", "resolved_value": value}
                if value is not None and not _integer(value, 0, 255):
                    raise HarnessError("Invalid historical native resource/ordinal value")
                if value is not None and operand["kind"] != "variable" and value != operand["value"]:
                    raise HarnessError("Historical native value contradicts literal CPU operand")
                if value is None:
                    unresolved.append({"kind": "historical_operand_value", "pc": row["pc"],
                                       "role": operand["role"], "retired": event["retired"]})
                elif operand["role"] == "view":
                    observed_views.add(value)
                reference["observations"].append(observation)
            references.append(reference)
    bound = [deepcopy(actor) for actor in guest["actors"] if actor["view_bound"]]
    actor_ids = [actor["id"] for actor in bound]
    current_views = sorted({actor["view"] for actor in bound})
    contradictions = []
    if legacy is not None:
        if type(legacy) is not dict:
            raise HarnessError("Legacy declarations must be a mapping")
        for name, actual in (("selected_actors", actor_ids), ("views", sorted(observed_views))):
            if name in legacy and not _same(legacy[name], actual):
                contradictions.append({"field": name, "declared": deepcopy(legacy[name]), "derived": actual})
        if "execution_endpoint" in legacy:
            declared = legacy["execution_endpoint"]
            actual = {"kind": endpoint["kind"], "fragment_pc": endpoint["pc"]}
            if type(declared) is not dict or any(not _same(declared.get(key), value) for key, value in actual.items()):
                contradictions.append({"field": "execution_endpoint", "declared": deepcopy(declared), "derived": actual})
    if cursor != len(code):
        unresolved.append({"kind": "static_decode_boundary", "pc": cursor,
                           "pages": [{"stop": page["stop"], "error": deepcopy(page["error"])}
                                     for page in processor.pages if page["next_pc"] == cursor]})
    return {"schema": SCHEMA, "source": deepcopy(state["source"]),
            "decoder": deepcopy(processor.pages[0]["decoder"]),
            "instruction_pages": deepcopy(processor.pages), "source_mappings": deepcopy(source_mappings),
            "instructions": [{**deepcopy(row), "source_mapping": deepcopy(mapped[row["pc"]]),
                              "retirements": deepcopy(by_retirement.get(row["pc"], [])),
                              "pending": pending is not None and row["pc"] == pending["pc"]}
                             for row in instructions],
            "static_listing_complete": cursor == len(code), "static_reachability_qualified": False,
            "endpoint": endpoint, "actor_ids": actor_ids, "bound_actors": bound,
            "static_actor_references": sorted({actor for row in instructions for actor in _actor_inputs(row)}),
            "touched_actor_ids": sorted({actor for row in expected_rows for actor in _actor_inputs(row)}),
            "pending_actor_id": None if pending is None else pending["actor"],
            "static_view_ids": sorted(static_views), "observed_view_ids": sorted(observed_views),
            "current_view_ids": current_views, "operand_references": references,
            "loaded_view_ids": deepcopy(guest["loaded_views"]), "journal_validation": journal,
            "observation": deepcopy(state["observation"]),
            "evidence": {"initial_sha256": _digest(initial), "snapshot_sha256": _digest(state),
                         "journal_sha256": _digest(events), "catalog_sha256": sha256(catalog).hexdigest()},
            "legacy_contradictions": contradictions, "unresolved": unresolved,
            "required_preview_policy": ["background", "priority_bands", "actor_flags_and_priority", "draw_order"],
            "original_room_state_qualified": False, "native_draw_completed": False,
            "presentation_established": False}
