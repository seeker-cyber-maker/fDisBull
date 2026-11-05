"""Compare one real KQ1 scene transition across DOSBox, ScummVM and Z.

The live runners write private receipts. This module only accepts completed
receipts for the exact authored route, then creates a small *partial* IL scene.
It does not turn matching endpoints into whole-engine equivalence.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Any

from fdisbull.il_scenes import ILSceneBackend


FORMAT = "fdisbull-kq1-scene-run-1"
TASK = "kq1-room1-to16-physical-1"
CARROT_TASK = "kq1-room1-carrot-repeat-physical-1"
SOURCE_AGI_SHA256 = "5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74"
LIMIT = 1024 * 1024


def _read_json(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > LIMIT:
        raise ValueError("Receipt exceeds 1 MiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate receipt key")
            result[key] = value
        return result

    value = json.loads(data, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Receipt must be an object")
    return value


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _state(value: Any, expected_room: int) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"room", "score"}:
        raise ValueError("Expected bounded room/score state")
    if any(type(value[k]) is not int or not 0 <= value[k] <= 255 for k in value):
        raise ValueError("State fields must be u8")
    if value != {"room": expected_room, "score": 0}:
        raise ValueError("Route boundary differs from task specification")
    return value


def _frame(value: Any, backend: str) -> None:
    if not isinstance(value, dict) or not _is_digest(value.get("sha256")):
        raise ValueError("Stored frame digest missing")
    for key in ("width", "height", "frame_id"):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ValueError("Stored frame metadata missing")
    expected = ("last_completed_guest_frame" if backend == "dosbox-x"
                else "last_committed_scummvm_display")
    if value.get("source") != expected:
        raise ValueError("Frame has the wrong backend completion boundary")
    if backend == "scummvm-agi" and (type(value.get("commit_revision")) is not int
                                      or value["commit_revision"] < 0):
        raise ValueError("ScummVM committed frame revision missing")


def validate_run(value: dict[str, Any], backend: str) -> dict[str, Any]:
    """Validate evidence shape and fixed observable outcomes, not provenance truth."""
    if value.get("format") != FORMAT or value.get("task") != TASK or value.get("backend") != backend:
        raise ValueError("Wrong receipt task or backend")
    if value.get("status") != "complete" or value.get("policy") != "physical":
        raise ValueError("Only completed physical-play runs qualify")
    if value.get("interventions") != []:
        raise ValueError("Intervened route is a different experiment")
    source = value.get("source")
    if (not isinstance(source, dict) or source.get("agi_sha256") != SOURCE_AGI_SHA256
            or not _is_digest(source.get("manifest_sha256"))):
        raise ValueError("Wrong or unbound KQ1 source")
    runtime = value.get("runtime")
    if not isinstance(runtime, dict) or not _is_digest(runtime.get("binary_sha256")):
        raise ValueError("Runtime binary identity missing")
    if runtime.get("version") is not None and (not isinstance(runtime["version"], str) or not runtime["version"]):
        raise ValueError("Invalid reported runtime version")
    boundaries = value.get("boundaries")
    if not isinstance(boundaries, dict) or set(boundaries) != {"start", "end"}:
        raise ValueError("Both route boundaries are required")
    if any(not isinstance(boundaries[name], dict) for name in ("start", "end")):
        raise ValueError("Invalid route boundary")
    _state(boundaries["start"].get("state"), 1)
    _state(boundaries["end"].get("state"), 16)
    _frame(boundaries["start"].get("frame"), backend)
    _frame(boundaries["end"].get("frame"), backend)
    if (backend == "dosbox-x" and boundaries["end"]["frame"]["frame_id"]
            <= boundaries["start"]["frame"]["frame_id"]):
        raise ValueError("End frame is not newer than start frame")
    if (backend == "scummvm-agi" and boundaries["end"]["frame"]["commit_revision"]
            <= boundaries["start"]["frame"]["commit_revision"]):
        raise ValueError("ScummVM display did not commit a newer frame")
    timings = value.get("timing_ms")
    if not isinstance(timings, dict):
        raise ValueError("Timing phases missing")
    for key in ("startup", "route", "observation", "teardown", "inclusive"):
        number = timings.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid {key} duration")
    if timings["inclusive"] + 0.001 < timings["startup"] + timings["route"] + timings["teardown"]:
        raise ValueError("Inclusive duration cannot omit phases")
    if timings["observation"] > timings["route"] + 0.001:
        raise ValueError("Observation is nested within route time")
    return value


def partial_scene() -> dict[str, Any]:
    """Authored projection of this one transition, with no game-script claim."""
    variables = {"$room": {"type": "u8", "initial": 1},
                 "$score": {"type": "u8", "initial": 0}}
    room_is = lambda n: {"op": "eq", "left": {"var": "$room"}, "right": n}
    return {
        "format": "fdisbull-il-scene-1",
        "programs": {"north": {
            "format": "fdisbull-il-1", "role": "uil", "variables": variables,
            "resources": {}, "body": [
                {"id": "only-room-1", "op": "require", "condition": room_is(1)},
                {"id": "enter-room-16", "op": "set", "var": "$room", "value": 16},
            ],
        }},
        "contexts": [
            {"id": "room-1", "title": "Room 1", "description": "Partial room projection.", "when": room_is(1)},
            {"id": "room-16", "title": "Room 16", "description": "Partial room projection.", "when": room_is(16)},
        ],
        "objects": [{"id": "north", "context": "room-1", "label": "north", "aliases": ["n"],
                     "description": "Move to the adjacent room.",
                     "bindings": [{"verb": "go", "program": "north"}]}],
        "partial": True,
    }


def compare(dos: dict[str, Any], scummvm: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_run(dos, "dosbox-x")
    validate_run(scummvm, "scummvm-agi")
    if dos["source"]["manifest_sha256"] != scummvm["source"]["manifest_sha256"]:
        raise ValueError("Backends used different source file inventories")

    scene = partial_scene()
    z = ILSceneBackend(scene)
    before = z.observe()
    if not before["complete"] or before["context"]["id"] != "room-1":
        raise ValueError("Z scene start differs")
    action = z.act({"verb": "go", "target": "north", "item": None,
                    "context_token": before["context"]["token"]})
    after = z.observe()
    if (action.get("status") != "success" or not action.get("complete")
            or not after.get("complete") or after["context"]["id"] != "room-16"
            or z.state != {"$room": 16, "$score": 0}):
        raise ValueError("Z scene failed its bounded transition")

    report = {
        "format": "fdisbull-kq1-scene-comparison-1", "task": TASK,
        "scope": "one authored physical room transition and matching partial Z state",
        "source": dos["source"],
        "runs": {"dosbox-x": {"receipt_sha256": _digest(dos), "timing_ms": dos["timing_ms"],
                            "runtime": dos["runtime"]},
                 "scummvm-agi": {"receipt_sha256": _digest(scummvm), "timing_ms": scummvm["timing_ms"],
                                 "runtime": scummvm["runtime"]}},
        "matched_fields": ["room", "score"],
        "scene": {"sha256": _digest(scene), "start": before["context"]["id"],
                  "action": "go north", "end": after["context"]["id"]},
        "claim_ceiling": "matched declared endpoints; no route, pixel, scheduler, or whole-engine equivalence",
    }
    return report, scene


def _carrot_state(value: Any, phase: str, backend: str) -> None:
    if not isinstance(value, dict):
        raise ValueError("Carrot boundary state missing")
    keys = {"room", "score", "carrot_flag_77", "ego_y", "direction"}
    keys |= {"message_window"} if backend == "dosbox-x" else {"at_modal", "modal_revision"}
    if set(value) != keys:
        raise ValueError("Carrot boundary state fields differ")
    if phase == "start":
        expected = (1, 0, False)
    elif phase == "arrival":
        expected = (16, 0, False)
    else:
        expected = (16, 2, True)
    if (value["room"], value["score"], value["carrot_flag_77"]) != expected:
        raise ValueError(f"Carrot {phase} differs from task outcome")
    if (type(value["room"]) is not int or type(value["score"]) is not int
            or type(value["carrot_flag_77"]) is not bool):
        raise ValueError("Carrot variable or flag has the wrong type")
    if (type(value["ego_y"]) is not int or type(value["direction"]) is not int
            or value["direction"] != 0 or not 0 <= value["ego_y"] <= 199):
        raise ValueError("Carrot ego position or settled movement is invalid")
    if phase != "start" and value["ego_y"] > 140:
        raise ValueError("Carrot action was outside the qualified reach")
    if backend == "dosbox-x":
        if value["message_window"] is not False:
            raise ValueError("DOS message remained open at boundary")
    elif value["at_modal"] is not False or type(value["modal_revision"]) is not int:
        raise ValueError("ScummVM modal remained open at boundary")


def validate_carrot_run(value: dict[str, Any], backend: str) -> dict[str, Any]:
    """Validate a fixed rich scene trace, without authenticating its operator."""
    if value.get("format") != FORMAT or value.get("task") != CARROT_TASK or value.get("backend") != backend:
        raise ValueError("Wrong carrot receipt task or backend")
    if value.get("status") != "complete" or value.get("policy") != "physical" or value.get("interventions") != []:
        raise ValueError("Only complete unintervened physical captures qualify")
    source, runtime = value.get("source"), value.get("runtime")
    if (not isinstance(source, dict) or source.get("agi_sha256") != SOURCE_AGI_SHA256
            or not _is_digest(source.get("manifest_sha256"))):
        raise ValueError("Wrong KQ1 source identity")
    if not isinstance(runtime, dict) or not _is_digest(runtime.get("binary_sha256")):
        raise ValueError("Runtime binary identity missing")
    if not _is_digest(runtime.get("python_manifest_sha256")) or not isinstance(runtime.get("python_sources"), dict):
        raise ValueError("Python provider identity missing")
    if (not runtime["python_sources"]
            or any(not isinstance(name, str) or not _is_digest(digest)
                   for name, digest in runtime["python_sources"].items())
            or _digest(runtime["python_sources"]) != runtime["python_manifest_sha256"]):
        raise ValueError("Python provider inventory differs from its digest")
    boundaries = value.get("boundaries")
    phases = ("start", "arrival", "carrot", "repeat")
    if not isinstance(boundaries, dict) or set(boundaries) != set(phases):
        raise ValueError("All carrot boundaries are required")
    previous_frame = -1
    for phase in phases:
        boundary = boundaries[phase]
        if not isinstance(boundary, dict) or set(boundary) != {"state", "frame"}:
            raise ValueError("Malformed carrot boundary")
        _carrot_state(boundary["state"], phase, backend)
        _frame(boundary["frame"], backend)
        frame = boundary["frame"]
        ordinal = frame["frame_id"] if backend == "dosbox-x" else frame["commit_revision"]
        if ordinal <= previous_frame:
            raise ValueError("Frames were not stored in increasing completed order")
        previous_frame = ordinal
    carrot = boundaries["carrot"]["state"]
    repeated = boundaries["repeat"]["state"]
    if any(carrot[key] != repeated[key]
           for key in ("room", "score", "carrot_flag_77", "ego_y", "direction")):
        raise ValueError("Repeat take changed game state")
    if backend == "scummvm-agi":
        revisions = [boundaries[phase]["state"]["modal_revision"] for phase in phases]
        if not (revisions[0] == revisions[1] and revisions[2] >= revisions[1] + 2
                and revisions[3] >= revisions[2] + 2):
            raise ValueError("ScummVM modal transitions were not witnessed")
    commands = value.get("commands")
    if (not isinstance(commands, list) or len(commands) != 2
            or [item.get("command") for item in commands] != ["get carrot", "get carrot"]
            or [item.get("result") for item in commands] != ["taken", "refused-no-state-change"]):
        raise ValueError("Carrot take and repeat refusal are required")
    for index, item in enumerate(commands):
        witness = item.get("witness")
        if not isinstance(witness, dict) or witness.get("state") != boundaries[("carrot", "repeat")[index]]["state"]:
            raise ValueError("Command witness differs from stored boundary")
        if backend == "dosbox-x":
            if witness.get("opened") is not True or witness.get("dismissed") is not True:
                raise ValueError("DOS message did not open and close")
        elif (type(witness.get("opened_revision")) is not int
              or type(witness.get("closed_revision")) is not int
              or witness["opened_revision"] >= witness["closed_revision"]
              or witness["closed_revision"] != witness["state"]["modal_revision"]):
            raise ValueError("ScummVM message open and close revisions missing")
    inputs = value.get("inputs")
    if not isinstance(inputs, list) or len(inputs) < 7:
        raise ValueError("Physical route input ledger missing")
    if any(not isinstance(item, dict) or item.get("kind") not in ("press", "type")
           or not isinstance(item.get("value"), str)
           or item.get("delivery") not in ("accepted", "queued") for item in inputs):
        raise ValueError("Physical input delivery ledger is incomplete")
    controls = value.get("route_control_calls")
    control_keys = {"guest_runs", "state_reads", "memory_reads", "engine_state_reads",
                    "keyboard_state_reads", "keyboard_submissions", "screenshots"}
    if (not isinstance(controls, dict) or set(controls) != control_keys
            or any(type(controls[key]) is not int or controls[key] < 0 for key in control_keys)
            or controls["guest_runs"] < 1 or controls["state_reads"] < 1
            or controls["screenshots"] != 3 or controls["keyboard_submissions"] != len(inputs)):
        raise ValueError("Route control-call accounting is incomplete")
    if backend == "dosbox-x":
        if controls["memory_reads"] != 4 * controls["state_reads"]:
            raise ValueError("DOS state-read accounting differs from memory reads")
    elif controls["engine_state_reads"] != controls["state_reads"]:
        raise ValueError("ScummVM state-read accounting differs from engine calls")
    timings = value.get("timing_ms")
    if not isinstance(timings, dict):
        raise ValueError("Carrot timing phases missing")
    for key in ("startup", "route", "observation", "teardown", "inclusive"):
        number = timings.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid {key} duration")
    if timings["inclusive"] + 0.001 < sum(timings[k] for k in ("startup", "route", "teardown")):
        raise ValueError("Inclusive timing omitted a phase")
    if timings["observation"] > timings["startup"] + timings["route"] + 0.001:
        raise ValueError("Observation timing exceeds its enclosing phases")
    return value


def partial_carrot_scene() -> dict[str, Any]:
    """Authored projection of observed f77/score effects and repeat guard."""
    variables = {"$room": {"type": "u8", "initial": 1},
                 "$score": {"type": "u8", "initial": 0},
                 "$f77_carrot": {"type": "bool", "initial": False}}
    room_is = lambda n: {"op": "eq", "left": {"var": "$room"}, "right": n}
    carrot_is = lambda held: {"op": "eq", "left": {"var": "$f77_carrot"}, "right": held}
    def program(body):
        return {"format": "fdisbull-il-1", "role": "uil", "variables": variables,
                "resources": {}, "body": body}
    return {
        "format": "fdisbull-il-scene-1",
        "programs": {
            "north": program([
                {"id": "only-room-1", "op": "require", "condition": room_is(1)},
                {"id": "enter-room-16", "op": "set", "var": "$room", "value": 16},
            ]),
            "take-carrot": program([
                {"id": "only-room-16", "op": "require", "condition": room_is(16)},
                {"id": "only-once", "op": "require", "condition": carrot_is(False)},
                {"id": "carry-carrot", "op": "set", "var": "$f77_carrot", "value": True},
                {"id": "award-score", "op": "set", "var": "$score", "value": 2},
            ]),
        },
        "contexts": [
            {"id": "room-1", "title": "Room 1", "description": "Partial KQ1 projection.", "when": room_is(1)},
            {"id": "room-16", "title": "Room 16", "description": "Partial KQ1 projection.", "when": room_is(16)},
        ],
        "objects": [
            {"id": "north", "context": "room-1", "label": "north", "aliases": ["n"],
             "description": "Move north.", "bindings": [{"verb": "go", "program": "north"}]},
            {"id": "carrot", "context": "room-16", "label": "carrot", "aliases": [],
             "description": "A carrot in this room.",
             "bindings": [{"verb": "take", "program": "take-carrot"}],
             "visible_when": carrot_is(False), "inventory_when": carrot_is(True)},
        ],
        "partial": True,
    }


def compare_carrot(dos: dict[str, Any], scummvm: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    validate_carrot_run(dos, "dosbox-x")
    validate_carrot_run(scummvm, "scummvm-agi")
    if dos["source"]["manifest_sha256"] != scummvm["source"]["manifest_sha256"]:
        raise ValueError("Carrot backends used different source file inventories")
    scene = partial_carrot_scene()
    z = ILSceneBackend(scene)
    before = z.observe()
    north = z.act({"verb": "go", "target": "north", "item": None,
                   "context_token": before["context"]["token"]})
    arrival = z.observe()
    take = z.act({"verb": "take", "target": "carrot", "item": None,
                  "context_token": arrival["context"]["token"]})
    after_take = z.observe()
    stable = dict(z.state)
    repeat = z.act({"verb": "take", "target": "carrot", "item": None,
                    "context_token": after_take["context"]["token"]})
    after_repeat = z.observe()
    if (not before["complete"] or before["context"]["id"] != "room-1"
            or north.get("status") != "success" or arrival["context"]["id"] != "room-16"
            or take.get("status") != "success" or stable != {"$room": 16, "$score": 2, "$f77_carrot": True}
            or repeat.get("status") != "rejected" or not repeat.get("complete")
            or after_repeat["context"]["id"] != "room-16" or z.state != stable):
        raise ValueError("Partial Z scene failed the bounded carrot trace")
    replay = {"format": "fdisbull-kq1-scene-replay-1", "scene_sha256": _digest(scene),
              "actions": [{"action": "go north", "status": north["status"]},
                          {"action": "take carrot", "status": take["status"]},
                          {"action": "take carrot", "status": repeat["status"], "message": repeat["message"]}],
              "final": {"context": after_repeat["context"]["id"], "state": stable},
              "complete": True}
    report = {"format": "fdisbull-kq1-scene-comparison-1", "task": CARROT_TASK,
              "scope": "authored room transition, carrot effect and repeat refusal",
              "source": dos["source"],
              "runs": {backend: {"receipt_sha256": _digest(run), "timing_ms": run["timing_ms"],
                                 "runtime": run["runtime"], "input_count": len(run["inputs"]),
                                 "route_control_calls": run["route_control_calls"]}
                       for backend, run in (("dosbox-x", dos), ("scummvm-agi", scummvm))},
              "matched_fields": ["room", "score", "carrot_flag_77", "message open and close", "repeat state unchanged"],
              "scene": {"sha256": _digest(scene), "replay_sha256": _digest(replay)},
              "claim_ceiling": "matched stated effects and guard; no text, pixels, route, scheduler or whole-engine equivalence"}
    return report, scene, replay


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("transition", "carrot"), default="transition")
    parser.add_argument("--dos-receipt", type=Path, required=True)
    parser.add_argument("--scummvm-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("Output directory already exists")
    try:
        dos = _read_json(args.dos_receipt)
        scummvm = _read_json(args.scummvm_receipt)
        if args.task == "carrot":
            report, scene, replay = compare_carrot(dos, scummvm)
        else:
            report, scene = compare(dos, scummvm)
            replay = None
        output.mkdir(mode=0o700, parents=True)
        os.chmod(output, 0o700)
        (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
        (output / "scene.json").write_text(json.dumps(scene, indent=2) + "\n")
        if replay is not None:
            (output / "replay.json").write_text(json.dumps(replay, indent=2) + "\n")
        print(json.dumps({"complete": True, "comparison": str(output / "comparison.json"),
                          "scene": str(output / "scene.json")}))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"complete": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
