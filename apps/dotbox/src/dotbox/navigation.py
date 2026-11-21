"""Bounded, state-bound cardinal movement proposals from supplied geometry.

No Client, guest input, actor placement, live observation or state restoration
is performed. Checking a supplied scene cannot establish that it is still live.
Long geometric legs require a separately qualified, interruptible controller.
"""

import argparse
import hashlib
import json
import sys

from . import scenes
from .scene_geometry import integer
from .spatial_map import _encoded, plan_route, validate_spatial_map


FORMAT = "dotbox-movement-plan-1"
MAX_MAP_FILE_BYTES = 2 * 1024 * 1024
MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_CONDITIONS_BYTES = 1024 * 1024
CLAIM = ("Route relative to supplied geometry and caller-reported scene/state only; "
         "no live freshness, collision, control, arrival or execution verification")
POLICY = {"headings": "cardinal", "optimize": ["distance", "turns"],
          "portals": "blocked", "unknown": "unavailable"}


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _conditions(document, conditions):
    if conditions is None:
        conditions = {}
    if (not isinstance(conditions, dict) or len(conditions) > 128
            or any(not isinstance(key, str) or not key
                   or type(value) not in (bool, type(None))
                   for key, value in conditions.items())):
        raise ValueError("Conditions require at most 128 named boolean or unknown values")
    normalized = {layer["when"]: None for layer in document["layers"] if "when" in layer}
    normalized.update(conditions)
    if len(normalized) > 128:
        raise ValueError("Declared and supplied conditions exceed the 128-name budget")
    encoded = _encoded(normalized)
    if len(encoded) > MAX_CONDITIONS_BYTES:
        raise ValueError("Conditions exceed the one MiB JSON budget")
    # Omitted declared conditions and explicit null mean the same unknown state.
    return json.loads(encoded)


def _inputs(map_doc, scene_packet, conditions):
    validate_spatial_map(map_doc)
    document = json.loads(_encoded(map_doc))
    packet = scenes.validate_scene(scene_packet)
    if "state_context" not in packet:
        raise ValueError("Movement proposals require scene state_context")
    if document["source"]["sha256"] != packet["source_sha256"]:
        raise ValueError("Map source hash differs from the scene source")
    if document["source"]["room"] != packet["scene_id"]:
        raise ValueError("Map room differs from the scene room")
    return document, packet, _conditions(document, conditions)


def _binding(document, packet, conditions):
    # The map's context is provider provenance, not a scene observation ID.
    result = {"map_sha256": _digest(document), "source": document["source"],
              "scene_sha256": scenes._digest(packet), "scene_id": packet["scene_id"],
              "edition": packet["edition"], "observation_id": packet["observation_id"],
              "state_context": packet["state_context"], "space": document["space"],
              "actor": document["actor"], "conditions": conditions}
    if "selection_sha256" in packet:
        result["selection_sha256"] = packet["selection_sha256"]
    return result


def _legs(path):
    """Preserve all cardinal cells while compressing adjacent equal headings."""
    directions = {(0, -1): "up", (-1, 0): "left", (1, 0): "right", (0, 1): "down"}
    legs = []
    for first, second in zip(path, path[1:]):
        direction = directions[(second[0] - first[0], second[1] - first[1])]
        if legs and legs[-1]["direction"] == direction:
            legs[-1]["end"] = list(second)
            legs[-1]["steps"] += 1
        else:
            legs.append({"start": list(first), "end": list(second),
                         "direction": direction, "steps": 1})
    return legs


def plan_movement(map_doc, start, goal, *, scene_packet, conditions=None, maxnodes=10000):
    """Bind a deterministic route proposal to exact canonical map/scene content.

    Coordinates are actor anchors in the map's declared game space. This does
    not read them from the live game or map them to screen coordinates. The
    required state context is retained for a later owner-aware live check.
    Hashes identify canonical JSON content, not original file whitespace.
    """
    integer(maxnodes, 1, 100000)
    document, packet, conditions = _inputs(map_doc, scene_packet, conditions)
    route = plan_route(document, start, goal, conditions=conditions, maxnodes=maxnodes)
    result = {"format": FORMAT, **_binding(document, packet, conditions),
              "start": list(start), "goal": list(goal), "max_nodes": maxnodes,
              "policy": json.loads(_encoded(POLICY)), **route, "legs": _legs(route["path"]),
              "execution": "not_performed", "live_applicability": "unverified", "claim": CLAIM}
    result["plan_sha256"] = _digest(result)
    if len(_encoded(result)) > MAX_PLAN_BYTES:
        raise ValueError("Movement proposal exceeds the 16 MiB JSON budget")
    return result


def check_movement_plan(plan, map_doc, scene_packet, *, conditions=None):
    """Reject stale or edited proposals by recomputing their bounded route.

    Recalculation checks every cardinal cell, the full footprint, portals and
    current supplied conditions, as well as exact canonical path and legs.
    Content hashes are not signatures. A freshly re-authored canonical proposal
    remains a proposal and never authorizes input or proves live applicability.
    """
    encoded = _encoded(plan)
    if len(encoded) > MAX_PLAN_BYTES or not isinstance(plan, dict) or plan.get("format") != FORMAT:
        raise ValueError("Invalid or oversized movement proposal")
    plan = json.loads(encoded)
    required = {"format", "map_sha256", "source", "scene_sha256", "scene_id", "edition",
                "observation_id", "state_context", "space", "actor", "conditions", "start", "goal",
                "max_nodes", "policy", "status", "path", "distance", "turns", "visited", "legs",
                "execution", "live_applicability", "claim", "plan_sha256"}
    if not required <= set(plan) or set(plan) - required - {"selection_sha256"}:
        raise ValueError("Invalid movement proposal fields")
    integer(plan["max_nodes"], 1, 100000)
    document, packet, normalized = _inputs(map_doc, scene_packet, conditions)
    current = _binding(document, packet, normalized)
    # Compare canonical JSON, not Python equality (where True equals 1).
    old = {key: plan[key] for key in current if key in plan}
    if _encoded(old) != _encoded(current) or ("selection_sha256" in plan) != ("selection_sha256" in packet):
        raise ValueError("Stale movement proposal: map, scene, state or conditions changed")
    claimed = plan["plan_sha256"]
    content = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if not isinstance(claimed, str) or claimed != _digest(content):
        raise ValueError("Invalid movement proposal content hash")
    expected = plan_movement(document, plan["start"], plan["goal"], scene_packet=packet,
                             conditions=normalized, maxnodes=plan["max_nodes"])
    if _encoded(plan) != _encoded(expected):
        raise ValueError("Movement proposal is not the canonical route for these inputs")
    return {"format": "dotbox-movement-plan-check-1", "valid": True,
            "plan_sha256": claimed, "status": plan["status"], "route_available": plan["status"] == "found",
            "execution": "not_performed", "live_applicability": "unverified", "claim": CLAIM}


def self_check():
    """Exercise authored geometry in memory; no game, file, network or input I/O."""
    try:
        document = {
            "format": "fdisbull-spatial-map-1",
            "source": {"sha256": "d" * 64, "context": "authored-map", "room": "study", "resource": "authored"},
            "space": {"name": "authored-grid", "width": 8, "height": 4, "unit": "cell"},
            "actor": {"width": 1, "height": 1, "anchor": [0, 0]},
            "known": {"rect": [0, 0, 8, 4]}, "safe": {"rect": [0, 0, 8, 4]},
            "layers": [{"id": "exit", "kind": "portal", "area": {"rect": [7, 0, 8, 4]}}],
            "evidence": {"authored": {"game_bytes": False}},
        }
        packet = {
            "format": "dotbox-scene-1", "source_sha256": "d" * 64, "edition": "authored",
            "scene_id": "study", "observation_id": "authored-1", "title": "Authored study",
            "facts": [], "choices": [], "guide_sources": [], "guide_claims": [],
            "state_context": {"provider_id": "authored", "session_id": "self-check", "branch_id": "first",
                              "revision": 1, "context_token": "authored-token"},
        }
        straight = plan_movement(document, [0, 1], [6, 1], scene_packet=packet)
        portal = plan_movement(document, [0, 1], [7, 1], scene_packet=packet)
        checks = {
            "straight_compression": straight["distance"] == 6 and straight["turns"] == 0 and len(straight["legs"]) == 1,
            "portal_boundary": portal["status"] == "endpoint_not_clear",
            "bound_proposal": check_movement_plan(straight, document, packet)["valid"],
        }
        return {"ok": all(checks.values()), "checks": checks,
                "scope": "Authored offline route proposals only; no native movement or live freshness qualification"}
    except (ImportError, OSError, ValueError, TypeError, RecursionError) as error:
        return {"ok": False, "error": str(error), "scope": "Offline navigation unavailable or failed"}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _read_json(path, maximum):
    from .inspection import _read_file

    def nonfinite(_value):
        raise ValueError("JSON must not contain nonfinite numbers")

    raw, _ = _read_file(path, max_bytes=maximum)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=scenes._unique_object, parse_constant=nonfinite)


def main(argv=None):
    parser = _Parser(prog="dotbox route", description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
    make = commands.add_parser("plan", help="Propose a bounded cardinal approach without inputs")
    make.add_argument("map")
    make.add_argument("--start", type=int, nargs=2, required=True, metavar=("X", "Y"))
    make.add_argument("--goal", type=int, nargs=2, required=True, metavar=("X", "Y"))
    make.add_argument("--max-nodes", type=int, default=10000)
    verify = commands.add_parser("check", help="Check a proposal against current supplied map and scene")
    verify.add_argument("plan")
    verify.add_argument("--map", required=True)
    for command in (make, verify):
        command.add_argument("--scene", required=True)
        command.add_argument("--conditions")
    try:
        args = parser.parse_args(argv)
        document = _read_json(args.map, MAX_MAP_FILE_BYTES)
        packet = _read_json(args.scene, scenes.MAX_FILE_BYTES)
        conditions = _read_json(args.conditions, MAX_CONDITIONS_BYTES) if args.conditions is not None else None
        if args.operation == "plan":
            result = plan_movement(document, args.start, args.goal, scene_packet=packet,
                                   conditions=conditions, maxnodes=args.max_nodes)
        else:
            proposal = _read_json(args.plan, MAX_PLAN_BYTES * 2)
            # Accept the exact stdout envelope so a redirected plan can be checked.
            if isinstance(proposal, dict) and set(proposal) == {"ok", "result"} and proposal["ok"] is True:
                proposal = proposal["result"]
            result = check_movement_plan(proposal, document, packet, conditions=conditions)
        print(json.dumps({"ok": True, "result": result}, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, RecursionError, ImportError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
