#!/usr/bin/env python3
"""Collect authored SCENE/DISASM packets for an independent helper trial.

This is test infrastructure, not a scene renderer. The controller retains the
authored oracle and full snapshots separately from each helper's input bundle.
The main trial uses six fresh children; the zero-change follow-up uses two.
Each owned child receives one bounded resume. An output directory
must be new; partial receipts survive failures. No native binary is built here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

from harness import HarnessError, QemuAGI
from scene_harness import AGISceneHarness, SceneOperationError, _bounded_timeout


# Homegrown cases. Expected final state is independently authored, not computed
# by decoding or interpreting these bytes. A separate reviewer/test owns its oracle.
CASES = (
    {
        "id": "case01",
        "code": bytes((3, 11, 52, 3, 12, 90, 38, 2, 11, 12,
                       37, 5, 7, 18, 37, 2, 60, 93, 39, 2, 15, 16,
                       38, 7, 15, 16, 0)),
        "actors": {2: (60, 93), 5: (7, 18), 7: (60, 93)},
        "variables": {11: 52, 12: 90, 15: 60, 16: 93},
        "retired": 8, "scene_eligible": 4,
        "last_changes": {2: 14, 5: 10, 7: 22},
        "last_assignments": {2: 14, 5: 10, 7: 22},
    },
    {
        "id": "case02",
        "code": bytes((3, 17, 44, 38, 3, 17, 17, 3, 17, 125,
                       38, 6, 17, 17, 37, 3, 44, 44, 0)),
        "actors": {3: (44, 44), 6: (125, 125)},
        "variables": {17: 125},
        "retired": 6, "scene_eligible": 2,
        "last_changes": {3: 3, 6: 10},
        "last_assignments": {3: 14, 6: 10},
    },
    {
        "id": "case03",
        "code": bytes((37, 0, 22, 51, 37, 1, 88, 14,
                       37, 9, 140, 145, 37, 1, 89, 15, 0)),
        "actors": {0: (22, 51), 1: (89, 15), 9: (140, 145)},
        "variables": {},
        "retired": 5, "scene_eligible": 4,
        "last_changes": {0: 0, 1: 12, 9: 8},
        "last_assignments": {0: 0, 1: 12, 9: 8},
    },
)

ZERO_CHANGE_CASES = (
    {
        "id": "zero_change",
        "code": bytes((37, 4, 0, 0, 0)),
        "actors": {4: (0, 0)}, "variables": {},
        "retired": 2, "scene_eligible": 0,
        "last_changes": {}, "last_assignments": {4: 0},
    },
)


def expected_guest(case):
    actors = []
    for index in range(16):
        x, y = case["actors"].get(index, (0, 0))
        actors.append({"id": index, "x": x, "y": y, "prev_x": x, "prev_y": y})
    return {"pc": len(case["code"]), "variables": [case["variables"].get(i, 0) for i in range(256)],
            "flags": [0] * 256, "actors": actors, "status": "return", "fault": None,
            "retired": case["retired"]}


def packet_case(run, *, include_snapshot=False):
    """Select raw evidence, never include original bytes or the final guest arrays."""
    state = run["final_state"]
    result = {
        "id": run["id"], "attachment_id": run["attachment"]["view"]["session_id"],
        "source": deepcopy(state["source"]),
        "collection": {"mask_held_constant": True, "cleared_during_interval": False,
                       "restarted_during_interval": False, "stopped_capture_stable": True,
                       "initial_snapshot_supplied": False},
        "checkpoint": {"guest": {key: state["guest"][key]
                                   for key in ("pc", "status", "fault", "retired")},
                       "observation": deepcopy(state["observation"]),
                       "run": {key: state["run"][key] for key in ("retired", "invocation")}},
        "observations": deepcopy(run["events"]),
    }
    if include_snapshot:
        result["captured_scene"] = deepcopy(run["capture"])
    return result


def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def collect(binary, output, *, timeout=10.0, zero_change_probe=False):
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    failures = output / "native-failures"
    failures.mkdir()
    cases = ZERO_CHANGE_CASES if zero_change_probe else CASES
    oracle = {"schema": "agi-reconstruction-authored-oracle-1", "cases": [
        {"id": case["id"], "program_hex": case["code"].hex(),
         "program_sha256": hashlib.sha256(case["code"]).hexdigest(),
         "guest": expected_guest(case), "scene_eligible": case["scene_eligible"],
         "last_changes": case["last_changes"], "last_assignments": case["last_assignments"]}
        for case in cases]}
    write_json(output / "oracle.json", oracle)
    report = {"schema": "agi-reconstruction-collection-1", "status": "running",
              "trial_id": str(uuid.uuid4()),
              "parameters": {"maximum_children": 2 * len(cases), "maximum_resumes_per_child": 1,
                             "step_budget": 16, "timeout": timeout}, "runs": []}
    packets = {name: {"schema": "fdisbull-agi-reconstruction-packet-1",
                      "condition": name, "cases": []}
               for name in ("scene_only", "scene_disasm", "snapshot_scene_disasm")}
    with (output / "collection.json").open("x", encoding="utf-8") as stream:
        stage = "native_collection"
        try:
            for mask, condition in ((2, "scene_only"), (3, "scene_disasm")):
                for case in cases:
                    capacity = (2 if mask == 2 else 4) if case["id"] == "case03" else 32
                    run = {"id": case["id"], "condition": condition,
                           "program_hex": case["code"].hex()}
                    report["runs"].append(run)
                    with QemuAGI(binary, case["code"], timeout=timeout, evidence_dir=failures) as vm:
                        run["binary"] = {"sha256": vm.binary_sha256, "path": str(vm.binary)}
                        scene = AGISceneHarness(vm)
                        run["attachment"] = scene.attachment
                        run["configuration"] = scene.configure(mask=mask, capacity=capacity, step_budget=16)
                        run["capture"] = scene.run()
                        state = vm.state()
                        run["events"] = vm.events()
                        run["final_state"] = vm.state()
                        if state != run["final_state"]:
                            raise HarnessError("Stopped reconstruction capture changed")
                        if state["guest"] != expected_guest(case):
                            raise HarnessError("Native result differs from authored expected state")
                        if state["source"]["sha256"] != hashlib.sha256(case["code"]).hexdigest():
                            raise HarnessError("Native source identity mismatch")
                        if state["observation"]["per_channel"]["scene"]["eligible"] != case["scene_eligible"]:
                            raise HarnessError("Unexpected SCENE eligibility")
                        packets[condition]["cases"].append(packet_case(run))
                        if mask == 3:
                            packets["snapshot_scene_disasm"]["cases"].append(packet_case(run, include_snapshot=True))
            stage = "packet_write"
            guide = Path(__file__).with_name("SCENE_RECONSTRUCTION_PACKET.md").read_bytes()
            for condition, packet in packets.items():
                bundle = output / condition
                bundle.mkdir()
                write_json(bundle / "packet.json", packet)
                (bundle / "PROTOCOL.md").write_bytes(guide)
            report["status"] = "completed"
        except BaseException as error:
            report["status"] = "failed"
            report["failure"] = {"type": type(error).__name__, "message": str(error), "stage": stage}
            if isinstance(error, SceneOperationError):
                report["failure"].update(operation=error.operation, stage=error.stage, receipts=error.receipts)
            raise
        finally:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output-dir", required=True, help="New private trial directory; never overwritten")
    parser.add_argument("--timeout", type=_bounded_timeout, default=10.0)
    parser.add_argument("--zero-change-probe", action="store_true",
                        help="Separate follow-up with an executed zero-effect position assignment")
    args = parser.parse_args(argv)
    collect(args.binary, args.output_dir, timeout=args.timeout, zero_change_probe=args.zero_change_probe)
    print(str(Path(args.output_dir).expanduser().absolute()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
