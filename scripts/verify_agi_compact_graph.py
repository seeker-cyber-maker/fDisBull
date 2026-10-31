#!/usr/bin/env python3
"""Independently compare a compact AGI control graph with source logic bytes.

This bounded verifier checks control-flow structure and opaque instruction
provenance only. It does not execute the game, model AGI effects, or establish
state or runtime parity. Branches are enumerated as structural choices.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "src").is_dir():
    sys.path.insert(0, str(ROOT / "src"))

from fdisbull.agi import load_logic
from fdisbull.agi_layout import _ACTION_WIDTHS, logic_layout
from fdisbull.interaction_il import execute_il, validate_il

MAX_PROJECTION_BYTES = 4 * 1024 * 1024
MAX_SOURCE_NODES = 128
MAX_STRUCTURAL_PATHS = 4096
_MODELED_ACTIONS = {*range(1, 9), 12, 13, 14}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _volume_id(logdir: Path, logic: int) -> int:
    with logdir.open("rb") as stream:
        directory = stream.read(769)
    if len(directory) > 768 or len(directory) % 3:
        raise ValueError("invalid LOGDIR size")
    if logic < 0 or logic * 3 + 3 > len(directory):
        raise ValueError("logic directory entry absent")
    entry = int.from_bytes(directory[logic * 3:logic * 3 + 3], "big")
    if entry & 0xFFFFF == 0xFFFFF:
        raise ValueError("logic resource absent")
    return entry >> 20


def _file_hashes(logdir: Path, volume_dir: Path, volume: int) -> dict[str, str]:
    candidates = [logdir, *(p for p in volume_dir.iterdir()
                            if p.is_file() and p.name.lower() == f"vol.{volume}")]
    if len(candidates) != 2:
        raise ValueError("expected exactly one matching volume file")
    contents = []
    for path in candidates:
        with path.open("rb") as stream:
            limit = 769 if path == logdir else 2 * 1024 * 1024 + 1
            data = stream.read(limit)
        if path == logdir and len(data) > 768:
            raise ValueError("LOGDIR exceeds 768-byte limit")
        if path != logdir and len(data) > 2 * 1024 * 1024:
            raise ValueError("volume exceeds 2 MiB limit")
        contents.append((path.name, _digest(data)))
    return dict(contents)


def _source_graph(code: bytes, layout: dict) -> tuple[dict[int, tuple[int, ...]], set[int]]:
    starts = {offset - 2 for offset in layout["instructions"]}
    ordered = sorted(starts)
    end_of = {pc: ordered[i + 1] if i + 1 < len(ordered) else len(code)
              for i, pc in enumerate(ordered)}

    def successors(pc: int) -> tuple[int, ...]:
        op, end = code[pc], end_of[pc]
        if op == 0:
            return ()
        if op == 0xFE:
            target = end + int.from_bytes(code[end - 2:end], "little", signed=True)
            return (target,)
        if op == 0xFF:
            # The AGI processor reads IF skips as unsigned; do so independently
            # of the layout validator's signed boundary interpretation.
            displacement = int.from_bytes(code[end - 2:end], "little", signed=False)
            if displacement & 0x8000:
                raise ValueError("high-bit IF displacement is outside this verified layout scope")
            target = end + displacement
            return (end, target)
        if op in (22, 23):
            raise ValueError(f"unsupported call opcode at source offset {pc}")
        if op >= len(_ACTION_WIDTHS):
            raise ValueError(f"unsupported action opcode at source offset {pc}")
        return (end,)

    graph: dict[int, tuple[int, ...]] = {}
    pending = [0]
    while pending:
        pc = pending.pop()
        if pc in graph:
            continue
        if pc not in starts:
            raise ValueError(f"control-flow target is not an instruction boundary: {pc}")
        edges = successors(pc)
        if any(target not in starts for target in edges):
            raise ValueError(f"control-flow target leaves the instruction graph at {pc}")
        graph[pc] = edges
        if len(graph) > MAX_SOURCE_NODES:
            raise ValueError("source node budget exceeded")
        pending.extend(edges)

    colors: dict[int, int] = {}

    def visit(pc: int) -> None:
        colors[pc] = 1
        for target in graph[pc]:
            if colors.get(target) == 1:
                raise ValueError("cycles are outside this verifier's acyclic scope")
            if colors.get(target, 0) == 0:
                visit(target)
        colors[pc] = 2

    visit(0)
    return graph, starts


def _structural_paths(graph: dict[int, tuple[int, ...]]) -> list[tuple[int, ...]]:
    paths: list[tuple[int, ...]] = []
    pending = [(0, ())]
    while pending:
        pc, prefix = pending.pop()
        path = prefix + (pc,)
        if not graph[pc]:
            paths.append(path)
            if len(paths) > MAX_STRUCTURAL_PATHS:
                raise ValueError("structural path budget exceeded")
        else:
            pending.extend((target, path) for target in reversed(graph[pc]))
    return paths


def verify(logdir: Path, volume_dir: Path, logic: int, profile: str,
           projection_path: Path) -> dict:
    with projection_path.open("rb") as stream:
        projection_bytes = stream.read(MAX_PROJECTION_BYTES + 1)
    if len(projection_bytes) > MAX_PROJECTION_BYTES:
        raise ValueError("projection exceeds 4 MiB limit")
    projection = json.loads(projection_bytes)
    if not isinstance(projection, dict) or not isinstance(projection.get("uil"), dict):
        raise ValueError("projection must contain a UIL object")
    uil = projection["uil"]
    if uil.get('format') != 'fdisbull-il-2':
        raise ValueError('a compact IL v2 graph is required')
    validate_il(uil)
    if projection.get("qualification") != "control_flow_only":
        raise ValueError("projection is not marked control_flow_only")
    if projection.get("control_flow") != "shared_continuations":
        raise ValueError("projection is not a shared-continuation graph")

    # Capture hashes around all source reads. The output includes only these
    # digests and basename labels, never source bytes or absolute paths.
    source_volume = _volume_id(logdir, logic)
    before = _file_hashes(logdir, volume_dir, source_volume)
    resource = load_logic(logdir, volume_dir, logic, profile=profile)
    layout = logic_layout(resource.payload)
    graph, _ = _source_graph(resource.code, layout)
    after = _file_hashes(logdir, volume_dir, resource.volume)
    if before != after:
        raise ValueError("source inputs changed during verification")

    source_meta = projection.get("source", {})
    if (not isinstance(source_meta,dict) or source_meta.get("logic") != logic or source_meta.get("profile") != profile
            or source_meta.get("resource_sha256") != resource.resource_sha256):
        raise ValueError("projection source identity does not match the selected resource")

    continuations = uil.get("continuations")
    block_sources = projection.get("block_sources")
    if not isinstance(continuations, dict) or not isinstance(block_sources, dict):
        raise ValueError("projection is missing continuation source mappings")
    if len(continuations) > MAX_SOURCE_NODES or len(graph) > MAX_SOURCE_NODES:
        raise ValueError("source node budget exceeded")
    if len(continuations) != len(graph):
        raise ValueError("continuation and source node counts differ")
    by_offset: dict[int, str] = {}
    for continuation_id in continuations:
        source = block_sources.get(continuation_id)
        if not isinstance(source, dict) or source.get("logic") != logic:
            raise ValueError("continuation is missing a valid source coordinate")
        offset = source.get("offset")
        if type(offset) is not int or offset in by_offset:
            raise ValueError("duplicate or invalid continuation source coordinate")
        by_offset[offset] = continuation_id
    if set(by_offset) != set(graph):
        raise ValueError("continuation source coordinates do not cover the selected source graph")

    edge_mismatches = transfer_mismatches = 0
    projected_graph: dict[int, tuple[int, ...]] = {}
    for offset, source_edges in graph.items():
        continuation = continuations[by_offset[offset]]
        transfer = continuation.get("transfer")
        if not isinstance(transfer, dict):
            raise ValueError("invalid continuation transfer")
        opcode = resource.code[offset]
        expected_kind = "return" if opcode == 0 else ("if" if opcode == 0xFF else "goto")
        if transfer.get("op") != expected_kind:
            transfer_mismatches += 1
        if expected_kind == "return":
            target_ids: list[str] = []
        elif expected_kind == "if":
            target_ids = [transfer.get("then"), transfer.get("else")]
        else:
            target_ids = [transfer.get("target")]
        try:
            projected_edges = tuple(block_sources[target]["offset"] for target in target_ids)
        except (KeyError, TypeError) as exc:
            raise ValueError("continuation transfer has an unmapped target") from exc
        projected_graph[offset] = projected_edges
        # Keep true/false edge identity; swapping branches preserves an unordered
        # path set but changes the selected route for every predicate outcome.
        if projected_edges != source_edges:
            edge_mismatches += 1
    if edge_mismatches or transfer_mismatches:
        raise ValueError("projection control-flow differs from the source graph")

    source_paths = _structural_paths(graph)
    projected_paths = _structural_paths(projected_graph)
    path_mismatches = sum(a != b for a, b in zip(sorted(source_paths), sorted(projected_paths)))
    if len(source_paths) != len(projected_paths) or path_mismatches:
        raise ValueError("projection structural paths differ from source branch choices")

    opaque = projection.get("opaque_operations")
    if not isinstance(opaque, list):
        raise ValueError("projection is missing opaque operation mappings")
    opaque_mismatches = 0
    opaque_payloads: list[bytes] = []
    opaque_counts: Counter[int] = Counter()
    opaque_offsets, opaque_ids = set(), set()
    for item in opaque:
        if not isinstance(item, dict) or item.get("logic") != logic:
            opaque_mismatches += 1
            continue
        offset, opcode, block_id = item.get("offset"), item.get("opcode"), item.get("block_id")
        if (type(offset) is not int or offset not in graph or type(opcode) is not int
                or offset in opaque_offsets or not isinstance(block_id,str) or block_id in opaque_ids):
            opaque_mismatches += 1
            continue
        width = _ACTION_WIDTHS[resource.code[offset]] if resource.code[offset] < len(_ACTION_WIDTHS) else -1
        if width < 0 or resource.code[offset] != opcode:
            opaque_mismatches += 1
            continue
        raw = resource.code[offset:offset + 1 + width]
        source = block_sources.get(block_id, {})
        blocks = [block for block in continuations[by_offset[offset]]["body"]
                  if isinstance(block, dict) and block.get("id") == block_id]
        if (not isinstance(source,dict) or source.get("logic") != logic or source.get("offset") != offset
                or len(raw) != 1 + width or len(blocks) != 1
                or blocks[0].get("op") != "opaque"):
            opaque_mismatches += 1
            continue
        references = blocks[0].get('evidence',[])
        source_evidence = [uil.get('evidence',{}).get(ref,{}) for ref in references]
        if not any(item.get('sha256')==resource.resource_sha256
                   and item.get('range')==[offset+2,offset+len(raw)+2]
                   and item.get('instruction_bytes')==raw.hex() for item in source_evidence):
            opaque_mismatches += 1
            continue
        opaque_offsets.add(offset);opaque_ids.add(block_id)
        opaque_payloads.append(raw)
        opaque_counts[opcode] += 1
    # Every non-scalar, non-control action in the selected graph must be
    # represented by exactly one opaque operation. Calls were refused earlier.
    expected_opaque = Counter(
        resource.code[offset] for offset in graph
        if resource.code[offset] not in ({0, 0xFE, 0xFF} | _MODELED_ACTIONS)
    )
    expected_offsets = {offset for offset in graph
        if resource.code[offset] not in ({0,0xFE,0xFF}|_MODELED_ACTIONS)}
    def opaque_block_ids(body):
        result = set()
        for block in body:
            if block['op']=='opaque':result.add(block['id'])
            elif block['op']=='if':
                result |= opaque_block_ids(block['then']) | opaque_block_ids(block['else'])
        return result
    all_opaque_ids = set().union(*(opaque_block_ids(c['body']) for c in continuations.values()))
    if (opaque_counts != expected_opaque or opaque_mismatches or opaque_offsets != expected_offsets
            or opaque_ids != all_opaque_ids):
        raise ValueError("opaque operation mappings do not cover source actions exactly")

    execute_status = "not_attempted_no_opaque"
    execute_event_count = execute_visited_count = 0
    if opaque:
        result = execute_il(uil)
        execute_status = result.get("status", "unknown")
        execute_event_count = len(result.get("events", []))
        execute_visited_count = len(result.get("visited", []))
        if execute_status != "refused" or execute_event_count or execute_visited_count:
            raise ValueError("opaque graph execution did not refuse before effects")
    if _file_hashes(logdir,volume_dir,resource.volume) != before:
        raise ValueError('source inputs changed during verification')

    return {
        "format": "fdisbull-agi-compact-graph-verification-1",
        "qualification": "independent structural control-flow comparison; no state or runtime parity",
        "scope": {"logic": logic, "profile": profile, "branch_semantics": "structural_choices",
                  "cycles": "rejected", "calls": "rejected", "effect_execution": "not_claimed",
                  "predicate_equivalence": "not_claimed"},
        "source": {"resource_sha256": resource.resource_sha256,
                   "directory_sha256": resource.directory_sha256,
                   "volume_sha256": resource.volume_sha256},
        "projection_sha256": _digest(projection_bytes),
        "counts": {"source_nodes": len(graph), "continuations": len(continuations),
                   "source_edges": sum(map(len, graph.values())),
                   "edge_mismatches": edge_mismatches,
                   "transfer_kind_mismatches": transfer_mismatches,
                   "source_structural_paths": len(source_paths),
                   "projection_structural_paths": len(projected_paths),
                   "path_sequence_mismatches": path_mismatches,
                   "opaque_actions": len(opaque), "opaque_mismatches": opaque_mismatches,
                   "opaque_instruction_bytes": sum(map(len, opaque_payloads)),
                   "opaque_raw_bytes_sha256": _digest(b"".join(opaque_payloads))},
        "execution_check": {"status": execute_status, "events": execute_event_count,
                            "visited": execute_visited_count},
        "source_inputs_unchanged": before == after,
        "input_hashes": before,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logdir", type=Path, required=True)
    parser.add_argument("--volume-dir", type=Path, required=True)
    parser.add_argument("--logic", type=int, required=True)
    parser.add_argument("--profile", choices=("2.917",), default="2.917")
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        protected = [args.logdir,args.projection,*[p for p in args.volume_dir.iterdir()
                                                  if p.name.lower().startswith('vol.')]]
        if args.output.resolve() in {p.resolve() for p in protected}:
            raise ValueError('receipt output must not replace a source or projection input')
        result = verify(args.logdir, args.volume_dir, args.logic, args.profile, args.projection)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
