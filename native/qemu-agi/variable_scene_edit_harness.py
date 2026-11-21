#!/usr/bin/env python3
"""Demonstrate explicit variable-to-literal AGI placement overrides.

Four authored programs distinguish historical variable reads, aliased variables,
a later placement overwrite, and downstream get.posn propagation. Each original
and candidate runs in a separate owned QEMU child. Final snapshot differences
are reported as observations, not predictions or whole-program guarantees.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fdisbull_core.agi_scene import plan_variable_position_override

from harness import HarnessError
from scene_edit_harness import _candidate_bytes, _run_program
from scene_harness import SceneOperationError, _bounded_timeout


# Authored raw instructions, not game resources. Every selected actor-zero
# witness is position.v; only its four-byte window is replaced with position.
CASES = (
    ("historical_reads", bytes.fromhex("03070a030814260007080307460308502601070800")),
    ("aliased_variables", bytes.fromhex("030919260009092601090900")),
    ("later_assignment_overrides", bytes.fromhex("03070a030814260007082600070800")),
    ("downstream_get_posn", bytes.fromhex("03070a03081426000708270007082601070800")),
)
REQUESTED = {"x": 30, "y": 40}


def _final_differences(original, candidate):
    """Compare the complete final arrays; this does not claim intermediate parity."""
    result = {"difference_scope": "final_guest_snapshots"}
    for name, count in (("variables", 256), ("flags", 256), ("actors", 16)):
        before, after = original.get(name), candidate.get(name)
        if not isinstance(before, list) or not isinstance(after, list) \
                or len(before) != count or len(after) != count:
            raise HarnessError("Final guest arrays do not match the selected AGI profile")
        changes = []
        for index, (old, new) in enumerate(zip(before, after)):
            if old != new and not (name == "actors" and index == 0):
                changes.append({"index": index, "before": old, "after": new})
        key = "final_other_actor_changes" if name == "actors" else "final_" + name + "_changes"
        result[key] = changes
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Explicit qemu-system-agi executable")
    parser.add_argument("--output", required=True, help="New JSON receipt path; never overwritten")
    parser.add_argument("--evidence-dir", help="Existing private directory for failed native runs")
    parser.add_argument("--timeout", type=_bounded_timeout, default=10.0)
    args = parser.parse_args(argv)

    output = Path(args.output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Variable scene demonstration requires a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "fdisbull-agi-variable-scene-edit-demo-1", "status": "running",
        "scope": "Explicit variable-to-literal source override; fresh observed outcomes required",
        "parameters": {"mask": 2, "capacity": 8, "step_budget": 8,
                       "maximum_children": 8, "maximum_resumes_per_child": 1,
                       "timeout": args.timeout},
        "cases": [],
    }
    with output.open("x", encoding="utf-8") as stream:
        try:
            for name, original in CASES:
                case = {"name": name, "original": {}, "candidate": {}}
                report["cases"].append(case)
                view = _run_program(args.binary, original, case["original"],
                                    timeout=args.timeout, evidence_dir=args.evidence_dir,
                                    step_budget=8)
                plan = plan_variable_position_override(original, view, actor=0, **REQUESTED)
                case["plan"] = plan
                candidate = _candidate_bytes(original, plan, original_opcode=38)
                candidate_view = _run_program(
                    args.binary, candidate, case["candidate"], timeout=args.timeout,
                    evidence_dir=args.evidence_dir, step_budget=8,
                )
                if candidate_view["source"] != plan["candidate_source"]:
                    raise HarnessError("Observed candidate identity differs from the override plan")
                if candidate_view["session_id"] == view["session_id"]:
                    raise HarnessError("Original and candidate must have separate attachments")
                if case["original"]["binary"] != case["candidate"]["binary"]:
                    raise HarnessError("Native binary changed between original and candidate")
                observed = {key: candidate_view["actors"][0][key] for key in ("x", "y")}
                case["comparison"] = {
                    "requested_position": dict(REQUESTED), "observed_position": observed,
                    "placement_matched": observed == REQUESTED,
                    "candidate_returned": candidate_view["guest"]["status"] == "return",
                    "separate_attachments": True,
                    **_final_differences(case["original"]["final_state"]["guest"],
                                         case["candidate"]["final_state"]["guest"]),
                }
            report["all_requested_placements_matched"] = all(
                case["comparison"]["placement_matched"] for case in report["cases"]
            )
            report["status"] = "completed"
        except BaseException as error:
            report["status"] = "failed"
            report["failure"] = {"type": type(error).__name__, "message": str(error)}
            if isinstance(error, SceneOperationError):
                report["failure"].update(operation=error.operation, stage=error.stage,
                                         receipts=error.receipts)
                if error.__cause__ is not None:
                    report["failure"]["cause"] = {
                        "type": type(error.__cause__).__name__, "message": str(error.__cause__),
                    }
            raise
        finally:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
