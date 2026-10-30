"""Bounded, read-only inspection through the Z-machine processor interface.

These queries own traversal, not instruction decoding. They keep story-byte
addresses separate from native project addresses and never create a database.
An exhausted worklist covers only the selected static edges; it does not prove
runtime reachability, code immutability, function ownership or game intent.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
from typing import Any

from . import processor as processor_api
from .zmachine_processor import ZMachineV3Processor


MAX_INSTRUCTIONS = 100_000
MAX_ENTRY_POINTS = 256
# Bound aggregate byte-ownership work as well as attempted instruction starts.
# Overlapping, long inline strings must not make a small request unbounded.
MAX_DECODED_BYTES = 8 * 1024 * 1024


def _budget(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_INSTRUCTIONS:
        raise ValueError(f"max_instructions must be an integer in 1..{MAX_INSTRUCTIONS}")
    return value


def _address(value: Any, length: int, label: str) -> int:
    if isinstance(value, str):
        try:
            value = int(value, 0)
        except ValueError:
            raise ValueError(f"{label} must be a story-byte address") from None
    if type(value) is not int or not 64 <= value < length:
        raise ValueError(f"{label} must be in the declared story, after its 64-byte header")
    return value


def _base(adapter: ZMachineV3Processor, mode: str, limit: int) -> dict:
    return {
        "format": "fdisbull-zmachine-analysis-1",
        "mode": mode,
        "processor": asdict(adapter.info),
        "source": dict(adapter.story_info),
        "representation": "source_instruction_facts",
        "runtime_reachability_proven": False,
        "game_intent_recovered": False,
        "max_instructions": limit,
        "max_decoded_bytes": MAX_DECODED_BYTES,
        "assumptions": [
            "The immutable input is a source snapshot, not current VM memory.",
            "Direct call continuations assume that the callee returns.",
            "A decoded target is a candidate boundary, not proof it executes.",
            "Caller-dependent returns are retained without resolving a call stack.",
        ],
    }


def _decode(adapter: ZMachineV3Processor, offset: int) -> dict:
    location = processor_api.Location(adapter.info.address_space, offset)
    instruction = processor_api.decode_instruction(adapter, adapter.program, location)
    if instruction is None:
        raise ValueError("No instruction within the declared story")
    return {
        **instruction.facts,
        "location": asdict(instruction.location),
        "successors": [asdict(edge) for edge in instruction.successors],
    }


def _unresolved(row: dict) -> list[dict]:
    # A return is explicitly caller-dependent, rather than a missing direct
    # target. It stays in the instruction's edges and in the return-site list.
    return [dict(source_offset=row["offset"], **edge)
            for edge in row["successors"]
            if edge["target"] is None and edge["kind"] != "return"]


def disassemble_story(path, *, address=None, max_instructions=40) -> dict:
    """List one bounded source-order slice, ending at unconditional transfer.

    Conditional branches and calls retain all successor facts, but this view
    continues at the next encoded instruction. Use :func:`analyze_story` to
    follow both alternatives and direct callees. No following bytes are read
    after an unconditional jump, return, restart, restore or halt.
    """
    limit = _budget(max_instructions)
    adapter = ZMachineV3Processor.from_file(path)
    info = adapter.story_info
    offset = _address(info["initial_pc"] if address is None else address,
                      info["declared_bytes"], "address")
    result = _base(adapter, "linear", limit)
    result["start_offset"] = offset
    rows, issues, unresolved = [], [], []
    attempts = decoded_bytes = 0
    status = "instruction_budget"
    next_offset = offset
    while attempts < limit:
        attempts += 1
        try:
            row = _decode(adapter, offset)
        except ValueError as error:
            issues.append({"kind": "decode_error", "offset": offset, "error": str(error)})
            status = "decode_error"
            break
        if decoded_bytes + row["size"] > MAX_DECODED_BYTES:
            status = "byte_budget"
            break
        rows.append(row)
        decoded_bytes += row["size"]
        unresolved.extend(_unresolved(row))
        if row["flow"] in ("jump", "indirect_jump", "return", "halt", "restart", "restore"):
            status, next_offset = "control_flow_boundary", None
            break
        next_offset = row["end"]
        if next_offset >= info["declared_bytes"]:
            status, next_offset = "end_of_story", None
            break
        offset = next_offset
    result.update(
        status=status,
        complete=status in ("control_flow_boundary", "end_of_story") and not issues and not unresolved,
        complete_scope="requested_linear_slice_only",
        instructions=rows,
        instruction_count=len(rows),
        decode_attempts=attempts,
        decoded_bytes=decoded_bytes,
        next_offset=next_offset,
        issues=issues,
        unresolved_transfers=unresolved,
    )
    return result


def analyze_story(path, *, entry_points=None, max_instructions=10_000) -> dict:
    """Traverse candidate instructions from explicit roots and static edges.

    The worklist is local to this query. A budget stop exposes its frontier;
    rerunning with the same inputs and budget is deterministic. There is no
    byte sweep, initial-global-value propagation or native .fdb import.
    """
    limit = _budget(max_instructions)
    adapter = ZMachineV3Processor.from_file(path)
    info = adapter.story_info
    if entry_points is None:
        roots = [info["initial_pc"]]
    else:
        if not isinstance(entry_points, (list, tuple)) or not 1 <= len(entry_points) <= MAX_ENTRY_POINTS:
            raise ValueError(f"entry_points must contain 1..{MAX_ENTRY_POINTS} story-byte addresses")
        roots = list(dict.fromkeys(_address(value, info["declared_bytes"], "entry")
                                   for value in entry_points))
    pending = deque(roots)
    queued = set(roots)
    origins = {offset: {"offset": offset, "reason": "explicit_or_initial_entry", "source_offset": None}
               for offset in roots}
    visited, rows, issues, unresolved = set(), {}, [], []
    routines: dict[int, dict] = {}
    byte_owner: dict[int, int] = {}
    header_owner: dict[int, int] = {}
    return_sites = []
    attempts = decoded_bytes = 0
    stopped_by_bytes = False

    while pending and attempts < limit:
        offset = pending.popleft()
        queued.remove(offset)
        visited.add(offset)
        attempts += 1
        try:
            row = _decode(adapter, offset)
        except ValueError as error:
            issues.append({"kind": "decode_error", "offset": offset, "error": str(error)})
            continue
        if decoded_bytes + row["size"] > MAX_DECODED_BYTES:
            # Put the unadmitted candidate back so the frontier is truthful.
            pending.appendleft(offset)
            queued.add(offset)
            stopped_by_bytes = True
            break
        decoded_bytes += row["size"]
        conflicts, headers = set(), set()
        for position in range(offset, row["end"]):
            if position in byte_owner:
                conflicts.add(byte_owner[position])
            else:
                byte_owner[position] = offset
            if position in header_owner:
                headers.add(header_owner[position])
        if conflicts:
            issues.append({"kind": "overlapping_instructions", "offset": offset,
                           "other_starts": sorted(conflicts),
                           "evidence": "Candidate source spans overlap; neither interpretation is promoted to a proven boundary."})
        if headers:
            issues.append({"kind": "instruction_overlaps_routine_header", "offset": offset,
                           "routine_headers": sorted(headers)})
        rows[offset] = row
        unresolved.extend(_unresolved(row))
        if any(edge["kind"] == "return" for edge in row["successors"]):
            return_sites.append(offset)

        call = row.get("call", {})
        header, entry = call.get("routine_header"), call.get("entry")
        if call.get("status") == "routine_candidate" and type(header) is int and type(entry) is int:
            if header not in routines:
                routines[header] = {**call, "classification": "candidate", "call_sites": []}
                occupied = set()
                for position in range(header, entry):
                    header_owner[position] = header
                    if position in byte_owner:
                        occupied.add(byte_owner[position])
                if occupied:
                    issues.append({"kind": "routine_header_overlaps_instruction", "routine_header": header,
                                   "instruction_starts": sorted(occupied)})
            routines[header]["call_sites"].append(offset)

        for edge in row["successors"]:
            target = edge["target"]
            if target is None:
                continue
            if target["space"] != adapter.info.address_space:
                issues.append({"kind": "foreign_successor", "offset": offset, "target": target})
                continue
            destination = target["offset"]
            if destination not in visited and destination not in queued:
                origins[destination] = {"offset": destination, "reason": edge["kind"],
                                        "source_offset": offset}
                pending.append(destination)
                queued.add(destination)

    frontier = [origins[offset] for offset in pending]
    drained = not frontier
    complete = drained and not issues and not unresolved
    status = ("byte_budget" if stopped_by_bytes else "instruction_budget" if frontier else
              "static_worklist_drained" if complete else "partial")
    result = _base(adapter, "recursive", limit)
    result.update(
        status=status,
        complete=complete,
        complete_scope="requested_static_worklist_excluding_caller_dependent_returns",
        worklist_drained=drained,
        entry_points=roots,
        instructions=[rows[offset] for offset in sorted(rows)],
        instruction_count=len(rows),
        decode_attempts=attempts,
        decoded_bytes=decoded_bytes,
        frontier=frontier,
        unresolved_transfers=unresolved,
        return_sites=sorted(return_sites),
        routine_candidates=[routines[offset] for offset in sorted(routines)],
        issues=issues,
    )
    return result
