#!/usr/bin/env python3
"""Collect private cycle-state and deferred draw packets from exact fragments."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from fdisbull.agi_resources import V2Resources
from binding_catalog import decode_catalog
from binding_scene_trial import (
    _validate_binding_state, _validate_journal, _write_packet_inputs, prepare_case,
)
from draw_intent_harness import DRAW_INTENT_PROFILE, EVENTS_SCHEMA, STATE_SCHEMA
from harness import HarnessError
from resource_scene_trial import PALETTE, _write_json
from scene_harness import _bounded_timeout


def prepare_intent_case(game_dir, spec):
    """Retain the binding collector's exact contiguous source and asset inputs.

    ``endpoint`` selects either a stopped final draw or completion of every
    copied action followed by an explicitly authored return. ``stop_opcode``
    names the final copied action; it is not necessarily an unsupported opcode.
    """
    if type(spec) is not dict or spec.get("endpoint") not in ("authored_return", "pending_draw"):
        raise ValueError("Intent case requires authored_return or pending_draw endpoint")
    if spec["endpoint"] == "pending_draw" and spec.get("stop_opcode") != 35:
        raise ValueError("Pending draw requires a final draw instruction")
    prepared = prepare_case(game_dir, {key: value for key, value in spec.items() if key != "endpoint"})
    if spec["endpoint"] == "authored_return" and any(site["opcode"] == 35 for site in prepared["sites"]):
        raise ValueError("Authored-return fragment cannot cross a pending draw")
    if any(site["opcode"] == 35 for site in prepared["sites"][:-1]):
        raise ValueError("A fragment cannot cross an earlier pending draw")
    if spec["endpoint"] == "pending_draw" and prepared["sites"][-1]["bytes"][1] not in spec["actors"]:
        raise ValueError("Pending draw actor must be selected for the requested preview")
    prepared["spec"] = deepcopy(spec)
    return prepared


def validate_intent(state, *, code, catalog):
    """Validate the exact opt-in profile, committed pose and pending descriptor."""
    result = _validate_binding_state(state, code=code, catalog=catalog,
        profile=DRAW_INTENT_PROFILE, schema=STATE_SCHEMA,
        statuses=("ready", "budget", "return", "fault", "external", "effect"))
    guest = result["guest"]
    if "pending_effect" not in guest or type(guest.get("pc")) is not int \
            or not 0 <= guest["pc"] <= len(code) or type(guest.get("retired")) is not int \
            or not 0 <= guest["retired"] < 2**64:
        raise HarnessError("Intent snapshot has invalid pending/control fields")
    pending = guest["pending_effect"]
    if guest["status"] != "effect":
        if pending is not None:
            raise HarnessError("Only an effect stop may carry a pending request")
        return result
    keys = {"kind", "reason", "pc", "opcode", "bytes", "actor", "retired",
            "committed", "completion_available"}
    if type(pending) is not dict or set(pending) != keys \
            or pending["kind"] != "draw" or pending["reason"] != "draw_requires_host" \
            or type(pending["pc"]) is not int or pending["pc"] != guest["pc"] \
            or type(pending["opcode"]) is not int or pending["opcode"] != 35 \
            or type(pending["actor"]) is not int or not 0 <= pending["actor"] < 16 \
            or type(pending["bytes"]) is not list or len(pending["bytes"]) != 2 \
            or any(type(value) is not int for value in pending["bytes"]) \
            or pending["bytes"] != [35, pending["actor"]] \
            or pending["retired"] is not False or pending["committed"] is not False \
            or pending["completion_available"] is not False or guest.get("fault") is not None:
        raise HarnessError("Invalid or falsely completed pending draw")
    pc, actor = pending["pc"], guest["actors"][pending["actor"]]
    if list(code[pc:pc + 2]) != pending["bytes"] or not actor["view_bound"]:
        raise HarnessError("Pending draw source or loaded pose differs")
    return result


def validate_intent_reset(state, *, code, catalog):
    """Establish the zero-reset entry claim before a fragment is executed."""
    result = validate_intent(state, code=code, catalog=catalog)
    guest = result["guest"]
    if guest["status"] != "ready" or guest["pc"] != 0 or guest["retired"] != 0 \
            or guest.get("fault") is not None or guest["pending_effect"] is not None \
            or guest["loaded_views"] or any(guest["variables"]) or any(guest["flags"]):
        raise HarnessError("Intent fragment requires an explicit zero-reset entry")
    for actor in guest["actors"]:
        if any(value != 0 for name, value in actor.items() if name not in ("id", "motion", "cycle")):
            raise HarnessError("Intent fragment requires zero-reset actor state")
    return result


def validate_intent_journal(initial, state, events, *, prepared):
    """Include the authored return, or exclude the unretired pending draw."""
    prelude = prepared["prelude"]
    expected = [{"fragment_pc": pc, "bytes": list(prelude[pc:pc + 2]), "opcode": 30}
                for pc in range(0, len(prelude), 2)]
    if prepared["spec"]["endpoint"] == "authored_return":
        expected += prepared["sites"] + [{"fragment_pc": len(prepared["code"]) - 1,
                                         "bytes": [0], "opcode": 0}]
    else:
        expected += prepared["sites"][:-1]
    return _validate_journal(initial, state, events, code=prepared["code"], expected=expected,
        schema=EVENTS_SCHEMA, actor_ops=(33, 37, 38, 41, 42, 43, 44, 47, 48, 70, 71))


def collect(binary, game_dir, output, spec, *, timeout=10.0):
    """Own one bounded native run and retain a self-contained private packet."""
    from draw_intent_harness import QemuAGIDrawIntent

    timeout = _bounded_timeout(timeout)
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures = output / "native-failures"
    failures.mkdir()
    report = {"schema": "agi-draw-intent-collection-1", "status": "running",
              "parameters": {"maximum_children": 1, "resumes": 1, "step_budget": 80,
                             "timeout_seconds": timeout, "maximum_asset_bytes": 4 * 1024 * 1024}}
    stage = "prepare"
    try:
        prepared = prepare_intent_case(game_dir, spec)
        code, catalog = prepared["code"], prepared["catalog"]
        report["source_manifest"] = prepared["source_manifest"]
        stage = "native_capture"
        with QemuAGIDrawIntent(binary, code, catalog, timeout=timeout, evidence_dir=failures) as vm:
            report["binary_sha256"] = vm.binary_sha256
            initial = validate_intent_reset(vm.state(), code=code, catalog=catalog)
            report["initial_state"] = initial
            vm.configure(mask=3, capacity=256, step_budget=80)
            state, events = vm.run(), vm.events()
            if state != vm.state() or events != vm.events():
                raise HarnessError("Stopped intent capture changed")
            report["final_state"] = validate_intent(state, code=code, catalog=catalog)
            report["events"] = events
        guest, last = state["guest"], prepared["sites"][-1]
        if spec["endpoint"] == "authored_return":
            expected_retired = len(spec["views"]) + len(prepared["sites"]) + 1
            if guest["status"] != "return" or guest["pc"] != len(code) \
                    or guest["pending_effect"] is not None or guest["fault"] is not None:
                raise HarnessError("Native execution did not complete the authored return")
            endpoint = {"kind": "authored_return", "fragment_pc": len(code) - 1,
                        "bytes": [0], "original_source_address": None,
                        "retired": True, "committed": True}
        else:
            expected_retired = len(spec["views"]) + len(prepared["sites"]) - 1
            if guest["status"] != "effect" or guest["pc"] != last["fragment_pc"] \
                    or guest["pending_effect"]["bytes"] != last["bytes"]:
                raise HarnessError("Native execution did not stop at the exact pending draw")
            endpoint = {"kind": "pending_draw", **last, "retired": False, "committed": False}
        if guest["retired"] != expected_retired:
            raise HarnessError("Native retirement count differs from exact fragment endpoint")
        report["journal_validation"] = validate_intent_journal(initial, state, events, prepared=prepared)
        if any(not guest["actors"][number]["view_bound"] for number in spec["actors"]):
            raise HarnessError("A selected actor did not acquire a native VIEW binding")
        if V2Resources(game_dir).manifest() != prepared["source_manifest"]:
            raise HarnessError("Game inputs changed during collection")
        stage = "packet_write"
        helper = output / "helper"
        assets, documents = _write_packet_inputs(helper, prepared,
            (("README.md", "DRAW_INTENT_PACKET.md"),
             ("DRAW_INTENT_PROFILE.md", "DRAW_INTENT_PROFILE.md"),
             ("VIEW_BINDING_PROFILE.md", "VIEW_BINDING_PROFILE.md")))
        pending = deepcopy(guest["pending_effect"])
        request = None if pending is None else {
            "native_descriptor": pending, "source": deepcopy(state["source"]),
            "site": deepcopy(last), "committed_pose": deepcopy(guest["actors"][pending["actor"]]),
            "position_repair_completed": False, "sprite_buffers_updated": False,
            "presentation_established": False,
            "unresolved": ["position_repair", "collision_and_priority_effects",
                           "sprite_composition", "presentation"]}
        catalog_metadata = decode_catalog(catalog)
        catalog_metadata.pop("profile")
        packet = {"schema": "fdisbull-agi-draw-intent-packet-1", "id": spec["id"],
                  "qualification": "native_cycle_state_and_deferred_draw_in_explicit_reset_fragment",
                  "source_manifest": prepared["source_manifest"], "logic": prepared["logic"],
                  "views": prepared["views"], "fragment_mapping": prepared["mapping"],
                  "sites": prepared["sites"], "selected_actors": spec["actors"],
                  "catalog": {"file": "catalog.bin", "format": "FDBAGIV1", **catalog_metadata},
                  "entry": {"kind": "authored_reset_with_executed_load_prologue",
                            "horizon": spec["horizon"], "original_room_checkpoint": False,
                            "load_prologue_bytes": list(prepared["prelude"]), "authored_return_bytes": [0],
                            "initial_snapshot": initial},
                  "native": {"binary_sha256": report["binary_sha256"],
                             "snapshot": state, "observations": events},
                  "execution_endpoint": endpoint, "draw_request": request,
                  "picture": {"resource": prepared["picture"],
                              "selection_basis": "explicit_preview_background_not_native_picture_state"},
                  "cel_assets": prepared["cels"], "assets": assets, "documents": documents,
                  "render_contract": {"kind": "diagnostic_unoccluded_layer", "width": 160, "height": 168,
                                      "axes": "x_right_y_down", "anchor": "lower_left_baseline",
                                      "top_row": "y-height+1", "clip": "canvas_bounds",
                                      "palette_rgb": PALETTE, "priority_compositing": False,
                                      "draw_order": spec["actors"], "establishes_visibility": False,
                                      "establishes_presentation": False},
                  "unknowns": ["Original room entry/path and inherited actor state are not qualified.",
                               "Pose and cycling are native results within the explicit reset/catalog model.",
                               "Picture choice and preview order are external inputs.",
                               "Pending draw has not repaired position, updated sprites or presented pixels.",
                               "Cycling controls do not advance a motion/cycle tick.",
                               "No original instruction after the selected endpoint has executed."]}
        _write_json(helper / "packet.json", packet)
        report.update(status="completed", packet="helper/packet.json", inputs_unchanged=True,
                      expected_retired=expected_retired, execution_endpoint=endpoint)
    except BaseException as error:
        report.update(status="failed", stage=stage, error={"type": type(error).__name__, "message": str(error)})
        _write_json(output / "report.json", report)
        raise
    _write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "game-dir", "case-json", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    path = Path(args.case_json)
    if path.stat().st_size > 8192:
        parser.error("case-json exceeds 8192 bytes")
    report = collect(args.binary, args.game_dir, args.output, json.loads(path.read_text()), timeout=args.timeout)
    print(json.dumps({"status": report["status"], "packet": report["packet"]}))


if __name__ == "__main__":
    main()
