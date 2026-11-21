"""Bind a declared scene-design path over immutable native AGI facts.

This module does not decode instructions, evaluate conditions, propagate guest
variables or execute AGI. Its actor fields are the latest explicit requests on
one caller-selected path, supplemented by missing-only endpoint design inputs.
They are not effective guest state, even when every render field is present.
"""
from __future__ import annotations

from copy import deepcopy
import json

from harness import HarnessError
from processor_discovery import _resource_mapping
from processor_harness import MAX_PAGE_JSON_BYTES, NativeAGIProcessor, _integer
from processor_scene import _mapping_rows


SCHEMA = "fdisbull-agi-bound-scene-recipe-1"
RENDER_FIELDS = ("view", "loop", "cel", "x", "y", "priority")
_BOOL_FIELDS = frozenset(("animated", "cycling", "draw_requested"))
_ACTOR_FIELDS = frozenset(RENDER_FIELDS) | _BOOL_FIELDS
_RESOURCE_DOMAINS = frozenset(("picture", "view", "logic", "room", "sound",
                               "message", "inventory_object", "word"))
_RESOURCE_OPERATIONS = frozenset(("resource.load_picture", "resource.discard_picture",
    "resource.load_view", "resource.discard_view", "resource.load_logic", "resource.load_sound"))
_SCENE_OPERATIONS = frozenset(("scene.draw_picture", "scene.show_picture"))
_FIELD_OPERATIONS = {
    "object.position": ("x", "y"),
    "object.reposition_to": ("x", "y"),
    "object.set_view": ("view",),
    "object.set_loop": ("loop",),
    "object.set_cel": ("cel",),
    "object.set_priority": ("priority",),
}
_BOOL_OPERATIONS = {
    "object.animate": ("animated", True),
    "object.stop_cycling": ("cycling", False),
    "object.start_cycling": ("cycling", True),
    "object.draw": ("draw_requested", True),
    "object.erase": ("draw_requested", False),
}


def _reason(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 512


def _missing_fields(fields):
    return [name for name in RENDER_FIELDS if name not in fields or fields[name]["value"] is None]


def _validate_pages(code, pages):
    if type(code) is not bytes or not 1 <= len(code) <= 65536:
        raise HarnessError("Scene binding requires exact 1..65536-byte native input")
    if type(pages) is not list or not 1 <= len(pages) <= 128 \
            or sum(len(page.get("instructions", [])) if type(page) is dict
                   and type(page.get("instructions")) is list else 4097 for page in pages) > 4096:
        raise HarnessError("Scene binding requires at most 128 pages and 4096 native rows")
    total = 0
    for page in pages:
        try:
            size = len(json.dumps(page, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError, RecursionError) as error:
            raise HarnessError("Scene binding pages must contain bounded JSON values") from error
        total += size
        if size > MAX_PAGE_JSON_BYTES or total > 32 * 1024**2:
            raise HarnessError("Scene binding native-page JSON budget exceeded")
    return NativeAGIProcessor(code, pages, allow_overlaps=True)


def _validate_selections(code, rows, entry_pc, endpoint, branch_choices, operand_bindings,
                         actor_inputs, max_steps):
    if not _integer(entry_pc, 0, len(code) - 1):
        raise HarnessError("Scene entry PC must be an in-range explicit address")
    if type(endpoint) is not dict or set(endpoint) != {"pc", "phase"} \
            or not _integer(endpoint["pc"], 0, len(code) - 1) \
            or endpoint["phase"] not in ("before", "after"):
        raise HarnessError("Scene endpoint requires an in-range PC and before/after phase")
    if not _integer(max_steps, 1, 4096):
        raise HarnessError("Scene path step limit must be in 1..4096")
    if type(branch_choices) is not dict or len(branch_choices) > 4096:
        raise HarnessError("Scene branch choices must be a bounded PC-to-edge dictionary")
    for pc, kind in branch_choices.items():
        if not _integer(pc, 0, len(code) - 1) or type(kind) is not str or kind not in ("true", "false"):
            raise HarnessError("Scene branch choice requires an integer PC and true/false edge")
        row = rows.get(pc)
        if row is None or row["operation"] != "control.if":
            raise HarnessError(f"Branch choice at PC {pc} does not name a native IF")
        if len(row["successors"]) != 2 \
                or {edge["kind"] for edge in row["successors"]} != {"true", "false"}:
            raise HarnessError(f"Native IF at PC {pc} lacks distinct true/false successors")
    if type(operand_bindings) is not list or len(operand_bindings) > 28672:
        raise HarnessError("Scene operand bindings must be a list of at most 28672 uses")
    bindings = {}
    for binding in operand_bindings:
        if type(binding) is not dict \
                or set(binding) != {"pc", "operand_index", "variable", "value", "reason"} \
                or not _integer(binding["pc"], 0, len(code) - 1) \
                or not _integer(binding["operand_index"], 0, 6) \
                or not _integer(binding["variable"], 0, 255) \
                or not _integer(binding["value"], 0, 255) or not _reason(binding["reason"]):
            raise HarnessError("Invalid scene operand binding; require one typed variable use and reason")
        key = (binding["pc"], binding["operand_index"])
        if key in bindings:
            raise HarnessError(f"Duplicate operand binding at PC {key[0]}, operand {key[1]}")
        row = rows.get(key[0])
        operand = row["operands"][key[1]] if row is not None and key[1] < len(row["operands"]) else None
        if operand is None or operand["kind"] != "variable" \
                or operand["access"] not in ("read", "read_write") \
                or operand["index"] != binding["variable"]:
            raise HarnessError(f"Operand binding at PC {key[0]}, operand {key[1]} differs from its native variable read")
        bindings[key] = deepcopy(binding)
    if type(actor_inputs) is not list or len(actor_inputs) > 256:
        raise HarnessError("Scene actor inputs must be a list of at most 256 actors")
    inputs = {}
    for item in actor_inputs:
        if type(item) is not dict or set(item) != {"actor", "fields", "reason"} \
                or not _integer(item["actor"], 0, 255) or not _reason(item["reason"]) \
                or type(item["fields"]) is not dict or not item["fields"] \
                or not set(item["fields"]) <= _ACTOR_FIELDS:
            raise HarnessError("Invalid missing-only actor design input")
        if item["actor"] in inputs:
            raise HarnessError(f"Duplicate actor input for actor {item['actor']}")
        for name, value in item["fields"].items():
            if name in _BOOL_FIELDS:
                valid = type(value) is bool
            else:
                valid = _integer(value, 0, 15 if name == "priority" else 255)
            if not valid:
                raise HarnessError(f"Invalid design field {name} for actor {item['actor']}")
        inputs[item["actor"]] = deepcopy(item)
    return bindings, inputs


def _native_provenance(row, mapping, operand_index=None):
    value = {"basis": "native_requested", "pc": row["pc"], "operation": row["operation"],
             "source_mapping": deepcopy(mapping)}
    if operand_index is not None:
        value["operand_index"] = operand_index
    return value


def _resolve_operands(row, mapping, bindings, used):
    result = []
    for index, operand in enumerate(row["operands"]):
        provenance = _native_provenance(row, mapping, index)
        value = operand.get("value")
        if operand["kind"] == "variable":
            key = (row["pc"], index)
            binding = bindings.get(key)
            if binding is not None:
                used.add(key)
                value = binding["value"]
                provenance["binding"] = {name: binding[name] for name in ("variable", "value", "reason")}
            else:
                provenance["basis"] = "unresolved_variable_request" \
                    if operand["access"] in ("read", "read_write") else "native_destination_reference"
                provenance["variable"] = operand["index"]
        elif operand["kind"] == "flag":
            provenance.update(basis="native_flag_reference", flag=operand["index"])
        result.append({"operand_index": index, "operand": deepcopy(operand),
                       "value": value, "provenance": provenance})
    return result


def _barrier(row):
    if row["effect_class"] == "unknown" or row["operation"] == "unmodeled":
        return "unmodeled_effect"
    if row["operation"] == "control.call":
        return "external_call"
    if row["operation"] == "control.new_room":
        return "external_room_transfer"
    if any(edge["kind"] in ("assumed_return", "assumed_fallthrough") for edge in row["successors"]):
        return "assumed_successor"
    operation = row["operation"]
    if row["effect_class"] in ("actor", "host") or operation.startswith(("object.", "scene.")):
        if operation not in _FIELD_OPERATIONS and operation not in _BOOL_OPERATIONS \
                and operation not in _SCENE_OPERATIONS:
            return "unsupported_scene_operation"
    if row["effect_class"] == "resource" and operation not in _RESOURCE_OPERATIONS:
        return "unsupported_scene_operation"
    return None


def _resource_requests(row, operands, mapping, at_barrier):
    result = []
    for resolved in operands:
        operand = resolved["operand"]
        domain = operand["role"] if operand["role"] in _RESOURCE_DOMAINS \
            else operand["kind"] if operand["kind"] in _RESOURCE_DOMAINS else None
        if domain is not None:
            result.append({"pc": row["pc"], "operation": row["operation"], "domain": domain,
                           "operand_index": resolved["operand_index"], "operand": deepcopy(operand),
                           "value": resolved["value"], "provenance": deepcopy(resolved["provenance"]),
                           "source_mapping": deepcopy(mapping), "at_barrier": at_barrier})
    return result


def _actor_operation(row, operands, actors, draw_requests, mapping):
    expected = ("actor",) + _FIELD_OPERATIONS.get(row["operation"], ())
    roles = [item["operand"]["role"] for item in operands]
    if len(roles) != len(expected) or set(roles) != set(expected):
        raise HarnessError(f"Actor operation at PC {row['pc']} has incompatible native operand roles")
    actor_operand = next(item for item in operands if item["operand"]["role"] == "actor")
    if actor_operand["operand"]["kind"] != "actor":
        raise HarnessError(f"Actor operation at PC {row['pc']} lacks a literal typed actor")
    actor_id = actor_operand["value"]
    actor = actors.setdefault(actor_id, {"actor": actor_id, "fields": {}, "missing_fields": [],
                                        "draw_request_pcs": []})
    for name in _FIELD_OPERATIONS.get(row["operation"], ()):
        value = next(item for item in operands if item["operand"]["role"] == name)
        expected_kind = name if name in ("view", "loop", "cel") else "u8"
        if value["operand"]["kind"] not in (expected_kind, "variable") \
                or value["operand"]["access"] not in ("read", "read_write", "reference"):
            raise HarnessError(f"Actor field {name} at PC {row['pc']} is not a native input")
        actor["fields"][name] = {"value": value["value"], "provenance": deepcopy(value["provenance"])}
    if row["operation"] in _BOOL_OPERATIONS:
        name, value = _BOOL_OPERATIONS[row["operation"]]
        actor["fields"][name] = {"value": value, "provenance": _native_provenance(row, mapping)}
    if row["operation"] == "object.draw":
        actor["draw_request_pcs"].append(row["pc"])
        draw_requests.append({"pc": row["pc"], "actor": actor_id, "source_mapping": deepcopy(mapping),
                              "requested_pose": {"fields": deepcopy(actor["fields"]),
                                                 "missing_fields": _missing_fields(actor["fields"])}})


def derive_bound_scene_recipe(*, code, pages, source_mappings, entry_pc, endpoint,
        branch_choices, operand_bindings, actor_inputs, resource_mapping=None, max_steps=4096):
    """Bind one finite, caller-selected path without interpreting guest state.

    Branch choices name native IF edges. Variable inputs name exact action
    operand uses. Actor inputs fill fields absent from the endpoint's requested
    pose; they cannot override a source request, even an unresolved one.
    Unknown/call/unsupported effects stop before application. A ``before``
    endpoint retains the next native row without consuming that row's inputs.
    """
    processor = _validate_pages(code, pages)
    rows = {row["pc"]: row for row in processor.instructions}
    _mapping_rows(source_mappings, code, [])
    resource_mapping = _resource_mapping(resource_mapping, code, source_mappings)
    bindings, design_inputs = _validate_selections(code, rows, entry_pc, endpoint,
        branch_choices, operand_bindings, actor_inputs, max_steps)
    path, timeline, branches, frontier = [], [], [], []
    actors, draw_requests, scene_requests, resource_requests = {}, [], [], []
    used_bindings, used_choices, seen, occupied = set(), set(), set(), {}
    required_inputs, missing_uses = [], set()
    reached = False
    stop_reason = None
    boundary = None
    pc = entry_pc

    def require_operands(row, operands, mapping, at_barrier):
        for item in operands:
            operand = item["operand"]
            domain = operand["role"] in _RESOURCE_DOMAINS or operand["kind"] in _RESOURCE_DOMAINS
            scene_input = row["operation"].startswith(("object.", "scene."))
            if operand["kind"] != "variable" or operand["access"] not in ("read", "read_write") \
                    or item["value"] is not None or not (domain or scene_input or at_barrier):
                continue
            key = (row["pc"], item["operand_index"])
            if key not in missing_uses:
                missing_uses.add(key)
                required_inputs.append({"kind": "operand_binding", "pc": row["pc"],
                    "operand_index": item["operand_index"], "variable": operand["index"],
                    "role": operand["role"], "source_mapping": deepcopy(mapping), "at_barrier": at_barrier})

    while True:
        if len(path) >= max_steps:
            stop_reason = "step_budget"
            frontier.append({"kind": stop_reason, "pc": pc})
            break
        if pc in seen:
            stop_reason = "repeated_pc"
            frontier.append({"kind": stop_reason, "pc": pc})
            break
        row = rows.get(pc)
        if row is None:
            fault = processor.fault_at(pc)
            stop_reason = "missing_native_record" if fault is None else "decode_fault"
            frontier.append({"kind": stop_reason, "pc": pc, **({"error": fault} if fault else {})})
            break
        mapping = _mapping_rows(source_mappings, code, [row])[pc]
        path.append(pc)
        seen.add(pc)
        overlap = next((occupied[byte] for byte in range(pc, pc + row["size"])
                        if byte in occupied and occupied[byte] != pc), None)
        for byte in range(pc, pc + row["size"]):
            occupied.setdefault(byte, pc)
        native_boundary = {"pc": pc, "instruction": deepcopy(row), "source_mapping": deepcopy(mapping)}
        item = {**deepcopy(native_boundary), "operands": [], "projection": "retained_only"}
        timeline.append(item)
        if overlap is None and pc == endpoint["pc"] and endpoint["phase"] == "before":
            item["projection"] = "endpoint_before"
            reached, stop_reason, boundary = True, "selected_endpoint", native_boundary
            break
        operands = _resolve_operands(row, mapping, bindings, used_bindings)
        item["operands"] = deepcopy(operands)
        stop_reason = "overlapping_instruction_extent" if overlap is not None else _barrier(row)
        resource_requests.extend(_resource_requests(row, operands, mapping, stop_reason is not None))
        require_operands(row, operands, mapping, stop_reason is not None)
        if stop_reason is not None:
            item["projection"] = "barrier"
            boundary = native_boundary
            frontier.append({"kind": stop_reason, "pc": pc,
                             **({"other_pc": overlap} if overlap is not None else {})})
            break
        edges = row["successors"]
        if row["operation"] == "control.if":
            if len(edges) != 2 or {edge["kind"] for edge in edges} != {"true", "false"}:
                raise HarnessError(f"Native IF at PC {pc} lacks distinct true/false successors")
            if pc not in branch_choices:
                item["projection"] = "barrier"
                stop_reason, boundary = "branch_choice_required", native_boundary
                frontier.append({"kind": stop_reason, "pc": pc})
                required_inputs.append({"kind": "branch_choice", "pc": pc,
                                        "choices": ["true", "false"], "source_mapping": deepcopy(mapping)})
                break
            kind = branch_choices[pc]
            used_choices.add(pc)
            edge = next(edge for edge in edges if edge["kind"] == kind)
            branches.append({"pc": pc, "kind": kind, "to_pc": edge["pc"],
                             "ordered_conditions": deepcopy(row["conditions"]),
                             "basis": "caller_declared_edge", "source_mapping": deepcopy(mapping)})
            item["projection"] = "control_selection"
        else:
            if len(edges) > 1:
                raise HarnessError(f"Non-IF native row at PC {pc} has ambiguous successors")
            edge = edges[0] if edges else None
        if row["operation"] in _FIELD_OPERATIONS or row["operation"] in _BOOL_OPERATIONS:
            _actor_operation(row, operands, actors, draw_requests, mapping)
            item["projection"] = "intent_projected"
        elif row["operation"] in _SCENE_OPERATIONS:
            if row["operation"] == "scene.show_picture" and operands \
                    or row["operation"] == "scene.draw_picture" and (len(operands) != 1
                        or operands[0]["operand"]["role"] != "picture"
                        or operands[0]["operand"]["kind"] not in ("picture", "variable")
                        or operands[0]["operand"]["access"] not in ("read", "read_write", "reference")):
                raise HarnessError(f"Picture operation at PC {pc} has incompatible native operand roles")
            scene_requests.append({"pc": pc, "operation": row["operation"],
                                   "operands": deepcopy(operands), "source_mapping": deepcopy(mapping)})
            item["projection"] = "intent_projected"
        if pc == endpoint["pc"] and endpoint["phase"] == "after":
            reached, stop_reason = True, "selected_endpoint"
            break
        if edge is None:
            stop_reason, boundary = "terminal_before_endpoint", native_boundary
            frontier.append({"kind": stop_reason, "pc": pc})
            break
        if not edge["in_range"]:
            stop_reason, boundary = "out_of_range_edge", native_boundary
            frontier.append({"kind": stop_reason, "pc": pc, "edge": deepcopy(edge)})
            break
        pc = edge["pc"]

    unused_choices = sorted(set(branch_choices) - used_choices)
    if unused_choices:
        raise HarnessError(f"Unvisited branch choices: {unused_choices[:16]}")
    unused_bindings = sorted(set(bindings) - used_bindings)
    if unused_bindings:
        raise HarnessError(f"Unvisited operand bindings: {unused_bindings[:16]}")
    for actor_id, design in design_inputs.items():
        if actor_id not in actors:
            raise HarnessError(f"Actor input {actor_id} has no projected operation on the selected path")
        actor = actors[actor_id]
        for name, value in design["fields"].items():
            if name in actor["fields"]:
                raise HarnessError(f"Actor input {actor_id}.{name} would override a source-explicit request")
            actor["fields"][name] = {"value": value, "provenance": {
                "basis": "caller_declared_design_input", "reason": design["reason"],
                "scope": "selected_endpoint"}}
    for actor_id, actor in sorted(actors.items()):
        actor["missing_fields"] = _missing_fields(actor["fields"])
        for name in actor["missing_fields"]:
            required_inputs.append({"kind": "actor_field", "actor": actor_id, "field": name,
                                    "scope": "selected_endpoint"})
    return {"schema": SCHEMA, "source": deepcopy(processor.source), "decoder": deepcopy(processor.decoder),
            "resource_mapping": resource_mapping, "source_mappings": deepcopy(source_mappings),
            "entry": {"pc": entry_pc, "basis": "caller_declared_entry", "runtime_observed": False},
            "endpoint": {"requested": deepcopy(endpoint), "reached": reached, "stopped_pc": pc,
                         "stop_reason": stop_reason, "boundary": boundary},
            "status": "selected_endpoint_reached" if reached else "blocked",
            "path": path, "timeline": timeline, "branches": branches,
            "operand_bindings": [deepcopy(bindings[key]) for key in sorted(used_bindings)],
            "actor_inputs": [deepcopy(design_inputs[key]) for key in sorted(design_inputs)],
            "actors": [actors[key] for key in sorted(actors)], "draw_requests": draw_requests,
            "scene_requests": scene_requests, "resource_requests": resource_requests,
            "required_inputs": required_inputs, "frontier": frontier,
            "budgets": {"max_steps": max_steps, "max_native_rows": 4096, "max_native_pages": 128,
                        "max_native_json_bytes": 32 * 1024**2, "max_operand_bindings": 28672,
                        "max_actors": 256},
            "usage": {"visited_steps": len(path), "native_rows": sum(len(page["instructions"]) for page in pages),
                      "native_pages": len(pages), "branch_choices": len(used_choices),
                      "operand_bindings": len(used_bindings), "actors": len(actors)},
            "coverage": {"selected_path_only": True, "branch_feasibility": "not_evaluated",
                         "state_propagation": "none", "interprocedural_effects": "unknown",
                         "implicit_setter_effects": "not_modeled", "scene_complete": False},
            "qualification": "conditional_designer_recipe", "runtime_observed": False,
            "native_draw_completed": False, "presentation_established": False,
            "effective_actor_state_established": False}
