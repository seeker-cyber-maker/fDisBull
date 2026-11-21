"""Bounded scene candidates from CPU-owned AGI instruction records.

This is a structural graph consumer, not an AGI interpreter. Both conditional
edges remain possible; variable operands remain symbolic; a call continuation
does not establish callee return or preserve any incoming state. Saved native
execution and the strict observed-scene planner remain separate evidence.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from hashlib import sha256
import math
import time

from fdisbull.processor import Location, decode_instruction
from harness import HarnessError
from processor_harness import (MAX_PAGE_JSON_BYTES, NativeAGIProcessor, NativePageSizeLimit,
                               _integer, _same, request_decode_page)
from processor_scene import _mapping_rows


SCHEMA = "fdisbull-agi-native-scene-candidates-1"
READ_SCHEMA = "fdisbull-agi-reachable-native-pages-1"
_DOMAINS = frozenset(("actor", "view", "loop", "cel", "picture", "logic", "room",
                      "sound", "message", "inventory_object", "word"))
_PICTURE_OPERATIONS = frozenset(("resource.load_picture", "scene.draw_picture",
    "resource.discard_picture", "scene.overlay_picture", "scene.show_picture",
    "scene.show_priority", "scene.add_to_picture"))
_STOP_BUDGETS = frozenset(("instruction_budget", "edge_budget", "page_budget",
                         "native_row_budget", "native_json_budget", "deadline"))


def _roots(code, roots):
    if type(code) is not bytes or not 1 <= len(code) <= 65536:
        raise ValueError("Require exact 1..65536-byte immutable native input")
    if type(roots) not in (list, tuple) or not 1 <= len(roots) <= 16 \
            or any(not _integer(pc, 0, len(code) - 1) for pc in roots) \
            or len(set(roots)) != len(roots):
        raise ValueError("Require one to sixteen distinct in-range entry PCs")
    return tuple(sorted(roots))


def _graph_limits(max_reached_nodes, max_edges):
    if not _integer(max_reached_nodes, 1, 4096) or not _integer(max_edges, 1, 8192):
        raise ValueError("Graph limits require 1..4096 reached PCs and 1..8192 edges")


def _lookup(processor, code, pc):
    if processor is None:
        return None, None
    decoded = decode_instruction(processor, code, Location(processor.info.address_space, pc))
    fault = processor.fault_at(pc)
    return decoded, None if fault is None else {"kind": "decode_fault", "pc": pc, "error": fault}


def _traverse(lookup, roots, *, max_reached_nodes, max_edges):
    """Walk only returned native successors; never infer instruction lengths."""
    pending, queued, visited = deque(roots), set(roots), set()
    nodes, edges, frontier = {}, [], []
    occupied = {}
    stopped = False
    while pending:
        pc = pending[0]
        if len(visited) >= max_reached_nodes:
            frontier.append({"kind": "instruction_budget", "pc": pc})
            stopped = True
            break
        pending.popleft()
        queued.remove(pc)
        if pc in visited:
            continue
        decoded, boundary = lookup(pc)
        if boundary is not None and boundary["kind"] in _STOP_BUDGETS:
            frontier.append(boundary)
            pending.appendleft(pc)
            stopped = True
            break
        visited.add(pc)
        if decoded is None:
            frontier.append(boundary or {"kind": "missing_native_record", "pc": pc})
            continue
        row = decoded.facts
        nodes[pc] = row
        # Prefetched but unreached extents do not invalidate a demanded start.
        # If two reached extents overlap, retain both native facts and explicitly
        # withhold an unambiguous local-closure claim.
        overlap = None
        for byte in range(pc, pc + row["size"]):
            other = occupied.setdefault(byte, pc)
            if other != pc and overlap is None:
                overlap = other
        if overlap is not None:
            # One witness per reached row proves ambiguity. Enumerating every
            # overlapping pair would turn a bounded graph into quadratic data.
            frontier.append({"kind": "overlapping_instruction_extent", "pc": pc,
                             "other_pc": overlap, "witness_scope": "first_overlapping_reached_extent"})
        for native_edge in row["successors"]:
            if len(edges) >= max_edges:
                frontier.append({"kind": "edge_budget", "pc": pc,
                                 "unvisited_successor": deepcopy(native_edge)})
                stopped = True
                break
            kind = native_edge["kind"]
            qualification = "callee_return_assumed" if kind == "assumed_return" \
                else "unmodeled_effect_fallthrough_assumed" if kind == "assumed_fallthrough" \
                else "condition_outcome_unknown" if kind in ("true", "false") \
                else "native_structural_edge"
            edge = {"from_pc": pc, "kind": kind, "to_pc": native_edge["pc"],
                    "in_range": native_edge["in_range"], "qualification": qualification}
            edges.append(edge)
            if not native_edge["in_range"]:
                frontier.append({"kind": "out_of_range_edge", "pc": pc,
                                 "edge": deepcopy(native_edge)})
            elif native_edge["pc"] not in visited and native_edge["pc"] not in queued:
                pending.append(native_edge["pc"])
                queued.add(native_edge["pc"])
        if stopped:
            break
    return {"nodes": nodes, "edges": edges, "frontier": frontier,
            "pending_pcs": list(pending), "attempted_pcs": len(visited),
            "traversal_exhausted": not pending and not stopped,
            "local_decode_complete": not frontier and not pending and not stopped}


def read_reachable_decode_pages(vm, code, *, roots=(0,), max_native_rows=4096,
        max_reached_nodes=4096, max_pages=128, max_edges=8192, page_limit=64,
        deadline_seconds=30.0, max_native_json_bytes=32 * 1024**2):
    """Acquire a finite recursive graph through the existing stopped CPU owner.

    Linear native pages are cached, but only native successor edges admit work.
    All queried rows count against the acquisition budget, including prefetch.
    There are no resumes or retries. The total deadline is checked before each
    page and bounds that page's QMP operations through the owner's timeout.
    """
    roots = _roots(code, roots)
    _graph_limits(max_reached_nodes, max_edges)
    if not _integer(max_native_rows, 1, 4096) or not _integer(max_pages, 1, 128) \
            or not _integer(page_limit, 1, 64) \
            or not _integer(max_native_json_bytes, 1, 32 * 1024**2) \
            or type(deadline_seconds) not in (int, float) \
            or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 30:
        raise ValueError("Invalid bounded native graph acquisition")
    original_timeout = getattr(vm, "timeout", None)
    if type(original_timeout) not in (int, float) or not math.isfinite(original_timeout) \
            or not 0 < original_timeout <= 5:
        raise ValueError("Native graph acquisition requires a QMP timeout in (0, 5] seconds")
    started = time.monotonic()
    deadline = started + deadline_seconds
    before, events_before = deepcopy(vm.state()), deepcopy(vm.events())
    source = before.get("source") if type(before) is dict else None
    if type(source) is not dict or source.get("sha256") != sha256(code).hexdigest() \
            or type(source.get("size")) is not int or source["size"] != len(code) \
            or type(source.get("logic_id")) is not int or source["logic_id"] != 0 \
            or type(source.get("profile")) is not str or not source["profile"]:
        raise HarnessError("Stopped native input differs from requested immutable code")
    pages, native_rows = [], 0
    admitted_json_bytes = received_json_bytes = page_requests = 0
    processor = None

    def lookup(pc):
        nonlocal processor, native_rows, admitted_json_bytes, received_json_bytes, page_requests
        decoded, fault = _lookup(processor, code, pc)
        if decoded is not None or fault is not None:
            return decoded, fault
        if len(pages) >= max_pages:
            return None, {"kind": "page_budget", "pc": pc}
        if native_rows >= max_native_rows:
            return None, {"kind": "native_row_budget", "pc": pc}
        if admitted_json_bytes >= max_native_json_bytes:
            return None, {"kind": "native_json_budget", "pc": pc}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, {"kind": "deadline", "pc": pc}
        # set/get each checks stopped status, making six QMP commands per page.
        # The finite per-command timeout also prevents a single pending page
        # from extending the acquisition by several full original timeouts.
        vm.timeout = min(float(original_timeout), remaining / 6)
        count = min(page_limit, max_native_rows - native_rows)
        page_requests += 1
        json_limit = min(MAX_PAGE_JSON_BYTES, max_native_json_bytes - admitted_json_bytes)
        try:
            page, size = request_decode_page(vm, code, source, start_pc=pc, limit=count,
                                            max_json_bytes=json_limit, return_size=True)
        except NativePageSizeLimit as error:
            received_json_bytes += error.size
            return None, {"kind": "native_json_budget", "pc": pc,
                          "received_page_bytes": error.size, "admission_limit": error.limit}
        pages.append(page)
        admitted_json_bytes += size
        received_json_bytes += size
        native_rows += len(page["instructions"])
        if processor is None:
            processor = NativeAGIProcessor(code, [page], allow_overlaps=True)
        else:
            processor.add_page(page)
        return _lookup(processor, code, pc)

    after = events_after = None
    try:
        traversal = _traverse(lookup, roots, max_reached_nodes=max_reached_nodes, max_edges=max_edges)
    finally:
        vm.timeout = original_timeout
        after, events_after = deepcopy(vm.state()), deepcopy(vm.events())
        if not _same(before, after) or not _same(events_before, events_after):
            raise HarnessError("Recursive metadata requests changed native state or retained events")
    return {"schema": READ_SCHEMA, "source": deepcopy(source), "pages": pages,
            "roots": list(roots), "frontier": traversal["frontier"],
            "pending_pcs": traversal["pending_pcs"],
            "coverage": {key: traversal[key] for key in
                         ("traversal_exhausted", "local_decode_complete")},
            "budgets": {"max_native_rows": max_native_rows, "max_reached_nodes": max_reached_nodes,
                        "max_pages": max_pages, "max_edges": max_edges, "page_limit": page_limit,
                        "max_page_json_bytes": MAX_PAGE_JSON_BYTES,
                        "max_native_json_bytes": max_native_json_bytes,
                        "deadline_seconds": deadline_seconds, "qmp_timeout_seconds": original_timeout},
            "usage": {"native_rows": native_rows, "pages": len(pages),
                      "page_requests": page_requests, "admitted_json_bytes": admitted_json_bytes,
                      "received_json_bytes": received_json_bytes,
                      "reached_nodes": len(traversal["nodes"]),
                      "attempted_pcs": traversal["attempted_pcs"], "edges": len(traversal["edges"])},
            "before": before, "after": after, "events_before": events_before,
            "events_after": events_after, "native_inputs_unchanged": True, "runs": 0}


def logic_input(payload, logic):
    """Bind a full AGI2 LOGIC payload to raw CPU code without decoding opcodes."""
    if type(payload) is not bytes or not 3 <= len(payload) <= 65535 \
            or not _integer(logic, 0, 255):
        raise ValueError("Require one exact bounded LOGIC resource payload and its number")
    size = int.from_bytes(payload[:2], "little")
    if size < 1 or size + 2 > len(payload):
        raise HarnessError("LOGIC code extent is outside its retained payload")
    code = payload[2:2 + size]
    resource = {"logic": logic, "resource_sha256": sha256(payload).hexdigest(),
                "resource_size": len(payload), "code_start": 2, "code_size": size,
                "code_sha256": sha256(code).hexdigest()}
    mapping = [{"kind": "original", "fragment_span": [0, size],
                "source": {"logic": logic, "resource_sha256": resource["resource_sha256"],
                           "code_span": [0, size], "payload_span": [2, size + 2]}}]
    return {"code": code, "source_mappings": mapping, "resource_mapping": resource}


def _resource_mapping(resource, code, mappings):
    if resource is None:
        return None
    fields = {"logic", "resource_sha256", "resource_size", "code_start", "code_size", "code_sha256"}
    if type(resource) is not dict or set(resource) != fields \
            or not _integer(resource["logic"], 0, 255) \
            or not _integer(resource["resource_size"], len(code) + 2, 65535) \
            or type(resource["code_start"]) is not int or resource["code_start"] != 2 \
            or type(resource["code_size"]) is not int or resource["code_size"] != len(code) \
            or resource["code_sha256"] != sha256(code).hexdigest():
        raise HarnessError("Full LOGIC resource mapping differs from native code")
    expected = [{"kind": "original", "fragment_span": [0, len(code)],
                 "source": {"logic": resource["logic"], "resource_sha256": resource["resource_sha256"],
                            "code_span": [0, len(code)], "payload_span": [2, len(code) + 2]}}]
    if not _same(mappings, expected):
        raise HarnessError("Full LOGIC source mappings differ from the resource identity")
    return deepcopy(resource)


def _operand_references(row, mapping):
    """Use typed CPU roles, never opcode numbers or guessed guest values."""
    groups = [(None, row["operands"])] + [
        (token["pc"], token["operands"]) for token in row["conditions"]
        if token["kind"] == "predicate"]
    for condition_pc, operands in groups:
        for index, operand in enumerate(operands):
            variable = operand["kind"] == "variable"
            if variable and operand["access"] not in ("read", "read_write"):
                continue
            domain = operand["role"] if operand["role"] in _DOMAINS \
                else operand["kind"] if operand["kind"] in _DOMAINS \
                else "variable" if variable else None
            if domain is None:
                continue
            yield {"pc": row["pc"], "condition_pc": condition_pc, "operand_index": index,
                   "operation": row["operation"], "domain": domain, "operand": deepcopy(operand),
                   "resolution": "unresolved" if variable else "literal",
                   "value": None if variable else operand["value"],
                   "reason": "variable_input" if variable else None,
                   "source_mapping": deepcopy(mapping), "runtime_observed": False}


def derive_scene_candidates(*, code, pages, source_mappings, roots=(0,),
        resource_mapping=None, max_reached_nodes=4096, max_edges=8192, max_references=32768):
    """Derive local structural candidates without interpreting any AGI state.

    Full original resources use ``logic_input``'s exact mapping. Explicit
    authored/fragment mappings also support bounded record-level qualification.
    Runtime observations are deliberately not accepted as implied full-source
    execution. The existing strict observed-scene planner handles them.
    """
    roots = _roots(code, roots)
    _graph_limits(max_reached_nodes, max_edges)
    if not _integer(max_references, 1, 32768):
        raise ValueError("Reference limit must be in 1..32768")
    if type(pages) is not list or not 1 <= len(pages) <= 128 \
            or sum(len(page.get("instructions", [])) if type(page) is dict
                   and type(page.get("instructions")) is list else 4097 for page in pages) > 4096:
        raise HarnessError("Discovery requires at most 128 pages and 4096 native rows")
    processor = NativeAGIProcessor(code, pages, allow_overlaps=True)
    _mapping_rows(source_mappings, code, [])
    resource_mapping = _resource_mapping(resource_mapping, code, source_mappings)
    traversal = _traverse(lambda pc: _lookup(processor, code, pc), roots,
                          max_reached_nodes=max_reached_nodes, max_edges=max_edges)
    rows = [traversal["nodes"][pc] for pc in sorted(traversal["nodes"])]
    mappings = _mapping_rows(source_mappings, code, rows)
    references, conditions = [], []
    sites = {"picture_operations": [], "actor_operations": [], "calls": [], "room_changes": []}
    unknown_effects = []
    reference_budget_hit = False
    for row in rows:
        pc = row["pc"]
        if not reference_budget_hit:
            for reference in _operand_references(row, mappings[pc]):
                if len(references) >= max_references:
                    traversal["frontier"].append({"kind": "reference_budget", "pc": pc})
                    reference_budget_hit = True
                    break
                references.append(reference)
        if row["conditions"] or row["operation"] == "control.if":
            conditions.append({"pc": pc, "ordered_tokens": deepcopy(row["conditions"]),
                               "outcome": "unknown", "source_mapping": deepcopy(mappings[pc])})
        site = {"pc": pc, "operation": row["operation"], "source_mapping": deepcopy(mappings[pc])}
        if row["operation"] in _PICTURE_OPERATIONS \
                or any(operand["role"] == "picture" for operand in row["operands"]):
            sites["picture_operations"].append(deepcopy(site))
        if row["effect_class"] == "actor" \
                or any(operand["role"] == "actor" for operand in row["operands"]):
            sites["actor_operations"].append(deepcopy(site))
        if row["operation"] == "control.call":
            sites["calls"].append({**site, "target_resolution": "native_operand_only",
                                   "callee_return": "unknown", "state_effects": "unknown"})
        if row["operation"] == "control.new_room":
            sites["room_changes"].append({**site, "dispatch_and_entry_state": "unknown"})
        if row["effect_class"] == "unknown" or row["operation"] == "control.call":
            unknown_effects.append(pc)
    native_rows = sum(len(page["instructions"]) for page in processor.pages)
    reached = {row["pc"] for row in rows}
    return {"schema": SCHEMA, "source": deepcopy(processor.source),
            "decoder": deepcopy(processor.decoder), "resource_mapping": resource_mapping,
            "source_mappings": deepcopy(source_mappings),
            "roots": [{"pc": pc, "basis": "raw_code_start" if pc == 0 else "caller_declared_entry",
                       "runtime_observed": False} for pc in roots],
            "instruction_pages": deepcopy(processor.pages),
            "nodes": [{"pc": row["pc"], "instruction": deepcopy(row),
                       "source_mapping": deepcopy(mappings[row["pc"]])} for row in rows],
            "edges": traversal["edges"], "references": references, "conditions": conditions,
            "scene_sites": sites, "unknown_state_effect_sites": unknown_effects,
            "frontier": traversal["frontier"], "pending_pcs": traversal["pending_pcs"],
            "coverage": {"traversal_exhausted": traversal["traversal_exhausted"],
                         "local_decode_complete": traversal["local_decode_complete"],
                         "reference_inventory_complete": not reference_budget_hit,
                         "branch_feasibility": "not_evaluated", "state_propagation": "none",
                         "interprocedural_effects": "unknown", "scene_discovery_complete": False},
            "budgets": {"max_native_rows": 4096, "max_pages": 128,
                        "max_reached_nodes": max_reached_nodes, "max_edges": max_edges,
                        "max_references": max_references},
            "usage": {"native_rows": native_rows, "pages": len(processor.pages),
                      "reached_nodes": len(rows), "attempted_pcs": traversal["attempted_pcs"],
                      "edges": len(traversal["edges"]), "references": len(references),
                      "prefetched_unreached_nodes": len({row["pc"] for row in processor.instructions} - reached),
                      "execution_support": dict(sorted(Counter(row["execution_support"] for row in rows).items()))},
            "qualification": "static_scene_candidates_only", "runtime_observed": False,
            "native_draw_completed": False, "presentation_established": False,
            "observed_evidence_links": []}
