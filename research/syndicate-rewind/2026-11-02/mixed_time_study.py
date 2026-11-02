"""Authored semantic-state study, NOT a native rewind backend or game emulator.

Only produces candidate dictionaries. No memory, register, input, filesystem or
native process adapter is installed. The deliberately narrow modeled profile is
on-foot actors with unchanged inventory ownership and no pending conditions.
A successful result does not authorize a live restore or prove game coherence.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from typing import Any


def fingerprint(state: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def cells(actors: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, actor in sorted(actors.items()):
        xyz = actor["raw"]
        if len(xyz) != 3 or any(type(n) is not int or n < 0 for n in xyz):
            raise ValueError("Invalid exact actor coordinates")
        cell = f"{xyz[0] // 256},{xyz[1] // 256},{xyz[2] // 128}"
        result.setdefault(cell, []).append(key)
    return result


def validate(state: dict[str, Any]) -> None:
    """Validate this fixture's explicit relations, not all Syndicate invariants."""
    for key in ("source", "session", "lineage", "snapshot"):
        if not isinstance(state.get(key), str) or not state[key]:
            raise ValueError(f"Missing fixture identity: {key}")
    for key in ("revision", "epoch", "tick"):
        if type(state.get(key)) is not int or state[key] < 0:
            raise ValueError(f"Invalid fixture counter: {key}")
    if not isinstance(state.get("actors"), dict) or not isinstance(state.get("items"), dict):
        raise ValueError("Invalid fixture entities")
    if state.get("spatial") != cells(state["actors"]):
        raise ValueError("Incoherent fixture spatial index")
    owners = {}
    for aid, actor in state["actors"].items():
        if type(actor.get("generation")) is not int or actor["generation"] < 0:
            raise ValueError("Invalid actor generation")
        if type(actor.get("health")) is not int:
            raise ValueError("Invalid health")
        if not isinstance(actor.get("items"), list) or len(set(actor["items"])) != len(actor["items"]):
            raise ValueError("Invalid inventory")
        for iid in actor["items"]:
            item = state["items"].get(iid)
            if not isinstance(item, dict) or item.get("owner") != aid or iid in owners:
                raise ValueError("Invalid inventory ownership")
            if item.get("raw") != actor["raw"]:
                raise ValueError("Unsettled attachment")
            owners[iid] = aid
    for iid, item in state["items"].items():
        if item.get("owner") is not None and owners.get(iid) != item["owner"]:
            raise ValueError("Dangling owned item")


def compose_fixture(current: dict[str, Any], requests: list[dict[str, Any]],
                    *, expected_current: str) -> dict[str, Any]:
    """Plan one current-base, historical-actor overlay in an authored fixture.

    All requests are checked before returning any candidate. Overlapping actor
    requests are refused, including identical duplicates, rather than silently
    hiding conflicting historical intent. Nothing is executed or auto-resumed.
    """
    validate(current)
    if fingerprint(current) != expected_current:
        raise ValueError("Stale current-state token")
    if not isinstance(requests, list) or not 1 <= len(requests) <= 64:
        raise ValueError("Invalid request batch")
    selected = set()
    prepared = []
    for request in requests:
        if not isinstance(request, dict) or set(request) != {"actor", "past"}:
            raise ValueError("Invalid request")
        aid, past = request["actor"], request["past"]
        if aid in selected:
            raise ValueError("Overlapping actor requests")
        selected.add(aid)
        validate(past)
        for key in ("source", "session", "lineage"):
            if past[key] != current[key]:
                raise ValueError(f"Mismatched {key}")
        if past["tick"] > current["tick"]:
            raise ValueError("Future state is not a rewind source")
        if aid not in current["actors"] or aid not in past["actors"]:
            raise ValueError("Missing actor")
        before, now = past["actors"][aid], current["actors"][aid]
        if before["generation"] != now["generation"]:
            raise ValueError("Actor slot was reused")
        for actor in (before, now):
            if actor.get("vehicle") is not None or actor.get("pending_conditions"):
                raise ValueError("Vehicle or condition closure is not modeled")
            if actor["health"] < 0:
                raise ValueError("Terminal-state restoration is not modeled")
        if set(before["items"]) != set(now["items"]):
            raise ValueError("Inventory ownership changed")
        for iid in now["items"]:
            if past["items"][iid]["generation"] != current["items"][iid]["generation"]:
                raise ValueError("Item slot was reused")
        if list(before["raw"]) in current.get("blocked_raw", []):
            raise ValueError("Historical destination is currently blocked")
        prepared.append((aid, deepcopy(before), past["snapshot"]))
    # Start from CURRENT world. Do not restore global historical CPU or roots.
    candidate = deepcopy(current)
    provenance = []
    for aid, historical, snapshot in prepared:
        # Only this modeled pose/health profile is restored; not an arbitrary blob.
        candidate["actors"][aid]["raw"] = deepcopy(historical["raw"])
        candidate["actors"][aid]["health"] = historical["health"]
        for iid in candidate["actors"][aid]["items"]:
            candidate["items"][iid]["raw"] = deepcopy(historical["raw"])
        provenance.append({"actor": aid, "from_snapshot": snapshot,
                           "fields": ["raw", "health"],
                           "derived": ["owned_item_positions", "spatial_index"]})
    # Rebuild using the CURRENT unselected actors, not old list neighbors.
    candidate["spatial"] = cells(candidate["actors"])
    candidate["revision"] += 1
    candidate["epoch"] += 1
    candidate["snapshot"] = "authored-mix-" + fingerprint({"current": expected_current, "requests": provenance})
    validate(candidate)
    return {"format": "authored-mixed-time-study-1", "candidate": candidate,
            "current_parent": current["snapshot"], "historical_sources": provenance,
            "native_execution": False, "geometry_qualified": False,
            "resume_safe": False, "execution_allowed": False,
            "scope": "Data-only authored fixture; not a native restoration command"}


def fixture_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    past = {"source": "authored-not-game", "session": "s", "lineage": "one",
            "snapshot": "past", "revision": 1, "epoch": 0, "tick": 100,
            "rng": [1, 2], "guard_ammo": 200, "doors": {"d": "closed"},
            "projectiles": ["authored-old-effect"], "blocked_raw": [],
            "actors": {
                "a": {"generation": 1, "raw": [256,256,256], "health": 16,
                      "items": ["w"], "vehicle": None, "pending_conditions": []},
                "b": {"generation": 1, "raw": [512,256,256], "health": 16,
                      "items": [], "vehicle": None, "pending_conditions": []}},
            "items": {"w": {"generation": 1, "owner": "a", "raw": [256,256,256], "ammo": 11}}}
    past["spatial"] = cells(past["actors"])
    now = deepcopy(past)
    now.update(snapshot="now", revision=2, tick=120, rng=[9,10], guard_ammo=190,
               doors={"d":"open"}, projectiles=["authored-current-effect"])
    now["actors"]["a"].update(raw=[1024,768,256], health=6)
    now["actors"]["b"]["raw"] = [1024,1024,256]
    now["items"]["w"].update(raw=[1024,768,256], ammo=10)
    now["spatial"] = cells(now["actors"])
    return past, now
