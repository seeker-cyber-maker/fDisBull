"""Reference-derived, source-bound SCUMM v2 room-transition contract.

This is a host-side planning/receipt validator, NOT the native QEMU room
loader. It deliberately models phase boundaries and cannot mutate a game.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import re

SCHEMA = "fdisbull-scumm-v2-room-transition-1"
PHASES = (
    "run_old_room_exit", "stop_room_owned_scripts",
    "release_room_owned_resources", "admit_target_room",
    "parse_target_room", "reset_room_objects", "rebuild_room_state",
    "initialize_camera_and_actors", "publish_current_room",
    "run_target_entry_script", "run_global_script_5", "complete",
)

class TransitionError(ValueError):
    pass

def _require(ok: bool, message: str) -> None:
    if not ok:
        raise TransitionError(message)

def _digest(value: object, name: str) -> str:
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"{name} must be a lowercase SHA-256")
    return value

def _optional_script(room: dict, name: str) -> dict | None:
    scripts = room.get("room_scripts")
    _require(type(scripts) is dict and name in scripts, "room catalog has no script inventory")
    script = scripts[name]
    if script is None:
        return None
    _require(type(script) is dict and type(script.get("offset")) is int
             and type(script.get("size")) is int and script["size"] >= 0,
             f"{name} script span is malformed")
    return script

def plan_room_transition(*, current_room: dict | None, target_room: dict,
                         target_resource_sha256: str, source: dict,
                         global_script_5_available: bool) -> dict:
    """Build a deterministic phase plan from two admitted room snapshots.

    The current-room snapshot is optional (initial boot). Only room-owned
    scripts/resources are torn down; global scripts are not implicitly killed.
    """
    _digest(target_resource_sha256, "target_resource_sha256")
    _require(type(source) is dict and source.get("version") == 2
             and source.get("profile") == "amiga-v2-isolated",
             "only the qualified Amiga v2 profile is admitted")
    target = target_room.get("room") if type(target_room) is dict else None
    _require(type(target) is dict and type(target.get("id")) is int
             and 1 <= target["id"] <= 255, "target room catalog is invalid")
    _digest(target.get("sha256"), "target room identity")
    _require(target["sha256"] == target_resource_sha256,
             "target room resource identity differs from catalog")
    _require(target_room.get("source") == source,
             "target room source identity differs from requested profile")
    _require(target_room.get("qualification", {}).get("whole_resource_identity_checked") is True,
             "target room was not admitted against a whole-resource identity")
    old = None
    if current_room is not None:
        old = current_room.get("room")
        _require(type(old) is dict and type(old.get("id")) is int,
                 "current room snapshot is invalid")
        _digest(old.get("sha256"), "current room identity")
        _require(current_room.get("source") == source,
                 "cross-profile room transitions are not admitted")
    exit_script = _optional_script(current_room, "exit") if current_room else None
    entry_script = _optional_script(target_room, "entry")
    phases = []
    def add(name: str, *, required: bool = True, evidence: dict | None = None):
        phases.append({"index": len(phases), "phase": name, "required": required,
                       "evidence_contract": evidence or {}})
    add("run_old_room_exit", required=exit_script is not None, evidence={"script_span": exit_script})
    add("stop_room_owned_scripts", evidence={"ownership": "room"})
    add("release_room_owned_resources", evidence={"ownership": "room"})
    add("admit_target_room", evidence={"room_id": target["id"], "resource_sha256": target_resource_sha256})
    add("parse_target_room", evidence={"room_sha256": target["sha256"]})
    add("reset_room_objects", evidence={"object_count": target_room["object_directory"]["count"]})
    add("rebuild_room_state", evidence={"walkboxes_admitted": target_room["walkboxes"]["admitted"]})
    add("initialize_camera_and_actors", evidence={"dimensions_pixels": target_room["dimensions_pixels"]})
    add("publish_current_room", evidence={"room_id": target["id"], "room_sha256": target["sha256"]})
    add("run_target_entry_script", required=entry_script is not None, evidence={"script_span": entry_script})
    add("run_global_script_5", required=bool(global_script_5_available),
        evidence={"script_id": 5, "scope": "global"})
    add("complete")
    payload = {"schema": SCHEMA, "source": deepcopy(source), "previous_room": deepcopy(old),
               "target_room": deepcopy(target), "target_resource_sha256": target_resource_sha256,
               "global_script_5_available": bool(global_script_5_available), "phases": phases,
               "semantics": {"global_scripts_survive_room_teardown": True,
                 "current_room_changes_at": "publish_current_room",
                 "entry_script_runs_after_room_publish": True,
                 "movement_is_not_implied": True, "native_execution_performed": False}}
    payload["plan_sha256"] = sha256(repr(payload).encode()).hexdigest()
    return payload

def validate_phase_receipts(plan: dict, receipts: list[dict]) -> dict:
    """Validate ordered phase receipts; never infer omitted phase success."""
    _require(type(plan) is dict and plan.get("schema") == SCHEMA, "unsupported room transition plan")
    phases = plan.get("phases")
    _require(type(phases) is list and len(phases) == len(PHASES),
             "transition phase inventory is incomplete")
    _require(type(receipts) is list, "phase receipts must be a list")
    by_index = {p.get("index"): p for p in phases if type(p) is dict}
    _require(len(by_index) == len(PHASES), "duplicate or missing phase indices")
    accepted, cursor = [], 0
    for receipt in receipts:
        _require(type(receipt) is dict and type(receipt.get("index")) is int,
                 "phase receipt is malformed")
        while cursor < len(phases) and not phases[cursor]["required"]:
            cursor += 1
        _require(cursor < len(phases), "receipt supplied after all required phases")
        phase = phases[cursor]
        _require(receipt["index"] == phase["index"] and receipt.get("phase") == phase["phase"],
                 "phase receipt is out of order or names a different phase")
        _require(receipt.get("status") == "committed", "phase is not explicitly committed")
        _require(receipt.get("plan_sha256") == plan.get("plan_sha256"),
                 "phase receipt belongs to a different plan")
        evidence = receipt.get("evidence")
        _require(type(evidence) is dict, "phase receipt evidence is missing")
        for key, expected in phase["evidence_contract"].items():
            _require(evidence.get(key) == expected, f"phase evidence mismatch: {key}")
        accepted.append(phase["phase"])
        cursor += 1
    while cursor < len(phases) and not phases[cursor]["required"]:
        cursor += 1
    next_required = phases[cursor]["phase"] if cursor < len(phases) else None
    return {"schema": SCHEMA, "plan_sha256": plan["plan_sha256"],
            "accepted_phases": accepted, "next_required_phase": next_required,
            "complete": next_required is None, "native_execution_performed": False}
