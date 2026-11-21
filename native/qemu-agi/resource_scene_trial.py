#!/usr/bin/env python3
"""Build a private resource/placement packet from explicit AGI design inputs.

This executes a source-linked position fragment, not a complete room. Picture
selection and cel pose are explicit designer inputs. The packet keeps those
candidates separate from native fragment observations and original game state.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture
from fdisbull.agi_resources import V2Resources
from fdisbull_core.agi_scene import plan_literal_position_edit
from fdisbull_core.agi_view import decode_view_cel
from harness import HarnessError, QemuAGI
from scene_harness import AGISceneHarness, SceneOperationError, _bounded_timeout


PALETTE = (
    (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
    (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
    (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
    (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255),
)


def _uint(value, name, maximum=255, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _identity(resource):
    return {key: value for key, value in resource.items() if key != "payload"}


def _resource(resources, kind, number):
    matches = [item for item in resources.resources(kind) if item["number"] == number]
    if len(matches) != 1 or matches[0]["status"] != "ok":
        raise ValueError(f"Selected {kind} resource is absent or invalid")
    return matches[0]


def prepare_case(game_dir, spec):
    """Validate selected source boundaries and decode explicit design assets.

    This performs no execution or reaching-value/path analysis. A script-site
    association never establishes current visibility or a completed room entry.
    """
    if not isinstance(spec, dict) or not isinstance(spec.get("id"), str):
        raise ValueError("A case object with a short id is required")
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", spec["id"]):
        raise ValueError("Invalid case id")
    allowed = {"id", "logic", "picture", "actor", "loop", "cel", "edit_position",
               "position_offset", "view_offset", "draw_offset", "picture_offset",
               "view", "original_position"}
    if set(spec) - allowed:
        raise ValueError("Unknown case specification field")
    for name in ("logic", "picture", "actor", "loop", "cel"):
        _uint(spec.get(name), name, 15 if name == "actor" else 255)
    edit = spec.get("edit_position")
    if not isinstance(edit, list) or len(edit) != 2:
        raise ValueError("edit_position requires two byte coordinates")
    for value in edit:
        _uint(value, "edit coordinate")
    if "view" in spec:
        _uint(spec["view"], "expected view")
    if "original_position" in spec:
        expected_position = spec["original_position"]
        if not isinstance(expected_position, list) or len(expected_position) != 2:
            raise ValueError("original_position requires two byte coordinates")
        for value in expected_position:
            _uint(value, "expected original coordinate")
    resources = V2Resources(game_dir)
    logic = _resource(resources, "logic", spec["logic"])
    payload = logic["payload"]
    layout = logic_layout(payload)
    starts = set(layout["instructions"])
    sites = {}
    for name, opcode, length in (("position", 37, 4), ("view", 41, 3),
                                 ("draw", 35, 2), ("picture", 25, 2)):
        offset = _uint(spec.get(name + "_offset"), name + "_offset", 65535, 2)
        if offset not in starts or offset + length > layout["code_end"]:
            raise ValueError(f"{name} is not an admitted LOGIC instruction boundary")
        raw = payload[offset:offset + length]
        if raw[0] != opcode or (name != "picture" and raw[1] != spec["actor"]):
            raise ValueError(f"{name} site differs from the required operation/actor")
        sites[name] = {"logic": spec["logic"], "resource_sha256": logic["sha256"],
                       "payload_offset": offset, "code_pc": offset - 2,
                       "bytes": list(raw), "qualification": "static_instruction_site"}
    view_id = sites["view"]["bytes"][2]
    if "view" in spec and spec["view"] != view_id:
        raise ValueError("Expected view differs from the selected source instruction")
    if ("original_position" in spec
            and spec["original_position"] != sites["position"]["bytes"][2:]):
        raise ValueError("Expected original position differs from the selected source instruction")
    picture = _resource(resources, "picture", spec["picture"])
    view = _resource(resources, "view", view_id)
    decoded_picture = decode_picture(picture["payload"])
    decoded_cel = decode_view_cel(view["payload"], loop=spec["loop"], cel=spec["cel"])
    code = bytes(sites["position"]["bytes"]) + b"\0"
    return {
        "id": spec["id"], "actor": spec["actor"], "edit_position": list(edit),
        "source_manifest": resources.manifest(), "logic": _identity(logic),
        "sites": sites, "picture": _identity(picture), "view": _identity(view),
        "picture_variable": sites["picture"]["bytes"][1],
        "cel": {key: value for key, value in decoded_cel.items() if key != "pixels"},
        "assets": {"background.idx": decoded_picture["visual"],
                   "priority.idx": decoded_picture["priority"], "cel.idx": decoded_cel["pixels"]},
        "code": code,
    }


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _capture(binary, code, actor, failures, timeout, result):
    with QemuAGI(binary, code, timeout=timeout, evidence_dir=failures) as vm:
        result["binary_sha256"] = vm.binary_sha256
        scene = AGISceneHarness(vm)
        result["attachment"] = scene.attachment
        result["configuration"] = scene.configure(mask=3, capacity=16, step_budget=8)
        result["capture"] = scene.run()
        result["events"] = vm.events()
        state = vm.state()
        if state != vm.state():
            raise HarnessError("Stopped fragment capture changed")
        result["final_state"] = state
        if state["source"]["sha256"] != hashlib.sha256(code).hexdigest():
            raise HarnessError("Fragment source identity differs")
        if state["guest"]["status"] != "return" or state["guest"]["retired"] != 2:
            raise HarnessError("Position fragment did not complete exactly two instructions")
        actual = state["guest"]["actors"][actor]
        if (actual["x"], actual["y"]) != (code[2], code[3]):
            raise HarnessError("Position fragment result differs from literal operands")
        return result


def collect(binary, game_dir, output, spec, *, timeout=10.0):
    """Collect two owned fragments and export a complete packet or failed receipt."""
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures = output / "native-failures"
    failures.mkdir()
    report = {"schema": "agi-resource-scene-collection-1", "status": "running",
              "parameters": {"maximum_children": 2, "resumes_per_child": 1,
                             "step_budget": 8, "timeout": timeout}, "runs": {}}
    stage = "prepare"
    try:
        prepared = prepare_case(game_dir, spec)
        report["source_manifest"] = prepared["source_manifest"]
        original = prepared["code"]
        stage = "original_fragment"
        base = {}
        report["runs"]["original"] = base
        _capture(binary, original, prepared["actor"], failures, timeout, base)
        stage = "edit_plan"
        plan = plan_literal_position_edit(original, base["capture"]["view"],
                                          actor=prepared["actor"],
                                          x=prepared["edit_position"][0], y=prepared["edit_position"][1])
        candidate = bytes(plan["replacement_bytes"]) + b"\0"
        if hashlib.sha256(candidate).hexdigest() != plan["candidate_source"]["sha256"]:
            raise HarnessError("Candidate differs from the detached edit plan")
        report["edit_plan"] = plan
        stage = "edited_fragment"
        edited = {}
        report["runs"]["edited"] = edited
        _capture(binary, candidate, prepared["actor"], failures, timeout, edited)
        # A source proposal for the containing LOGIC. No original file is changed,
        # and fragment success cannot qualify the containing room's behavior.
        source_edit = {"logic": prepared["logic"],
                       "payload_offset": prepared["sites"]["position"]["payload_offset"],
                       "code_pc": prepared["sites"]["position"]["code_pc"],
                       "expected_bytes": plan["expected_bytes"],
                       "replacement_bytes": plan["replacement_bytes"],
                       "write_performed": False, "full_logic_replay_qualified": False}
        stage = "packet_write"
        bundle = output / "helper"
        bundle.mkdir()
        asset_rows = {}
        for name, data in prepared["assets"].items():
            (bundle / name).write_bytes(data)
            asset_rows[name] = {"file": name, "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()}
        packet = {
            "schema": "fdisbull-agi-resource-scene-packet-1", "id": prepared["id"],
            "qualification": "source_bound_design_preview_with_native_position_fragments",
            "source_manifest": prepared["source_manifest"],
            "logic": prepared["logic"], "sites": prepared["sites"],
            "design": {
                "actor": prepared["actor"],
                "picture": {"resource": prepared["picture"],
                            "variable": prepared["picture_variable"],
                            "selected_value": prepared["picture"]["number"],
                            "selection_basis": "explicit_designer_binding_not_runtime_observation"},
                "cel": {"resource": prepared["view"], **prepared["cel"],
                        "selection_basis": "explicit_designer_loop_and_cel"},
                "current_game_visibility": None,
            },
            "render_contract": {"kind": "diagnostic_unoccluded_layer", "width": 160, "height": 168,
                                "axes": "x_right_y_down", "anchor": "lower_left_baseline",
                                "top_row": "y-height+1", "clip": "canvas_bounds",
                                "palette_rgb": PALETTE, "priority_compositing": False,
                                "draw_order": [prepared["actor"]]},
            "assets": asset_rows, "source_edit_proposal": source_edit,
            "fragment_mapping": {"copied_fragment_span": [0, 4],
                                 "source_payload_base": source_edit["payload_offset"],
                                 "source_code_base": source_edit["code_pc"],
                                 "authored_return_pc": 4,
                                 "native_logic_id": 0, "actual_logic": prepared["logic"]["number"],
                                 "containing_logic_executed": False},
            "fragments": {name: {"captured_scene": deepcopy(run["capture"]),
                                 "observations": deepcopy(run["events"])}
                          for name, run in report["runs"].items()},
            "unknowns": ["actual room entry and branch selection", "current game variables/flags",
                         "current actor visibility and animation pose", "complete picture/overlay order",
                         "priority/control occlusion and other actors", "original or replacement engine frame equivalence"],
        }
        _write_json(bundle / "packet.json", packet)
        guide = Path(__file__).with_name("RESOURCE_SCENE_PACKET.md")
        (bundle / "PROTOCOL.md").write_bytes(guide.read_bytes())
        report["packet"] = {"path": "helper/packet.json",
                            "sha256": hashlib.sha256((bundle / "packet.json").read_bytes()).hexdigest()}
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["failure"] = {"stage": stage, "type": type(error).__name__, "message": str(error)}
        if isinstance(error, SceneOperationError):
            report["failure"].update(operation=error.operation, operation_stage=error.stage,
                                     receipts=error.receipts)
        if error.__cause__ is not None:
            report["failure"]["cause"] = {"type": type(error.__cause__).__name__,
                                           "message": str(error.__cause__)}
        raise
    finally:
        _write_json(output / "collection.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--case", required=True, help="Private JSON case specification")
    parser.add_argument("--output-dir", required=True, help="New private output directory")
    parser.add_argument("--timeout", type=_bounded_timeout, default=10.0)
    args = parser.parse_args(argv)
    case_path = Path(args.case)
    if case_path.stat().st_size > 16384:
        raise ValueError("Case specification exceeds 16 KiB")
    spec = json.loads(case_path.read_text())
    collect(args.binary, args.game_dir, args.output_dir, spec, timeout=args.timeout)
    print(str(Path(args.output_dir).expanduser().absolute()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
