#!/usr/bin/env python3
"""Demonstrate source-linked literal edits through separate owned AGI runs.

This CLI runs two small homegrown raw programs, plans a position edit from each
captured scene witness, and executes each candidate in a fresh QEMU child. The
second program deliberately overwrites the edited position. Completed means the
experiment finished; each comparison separately reports achieved placement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fdisbull_core.agi_scene import plan_literal_position_edit

from harness import HarnessError, QemuAGI
from scene_harness import AGISceneHarness, SceneOperationError, _bounded_timeout


# These are authored instructions, not extracted game resources. Each program
# returns within one four-instruction invocation. Only SCENE is enabled.
CASES = (
    ("direct_placement", bytes.fromhex("25000a1400")),
    ("later_assignment_overrides", bytes.fromhex("25000a1425000a1400")),
)
REQUESTED = {"x": 30, "y": 40}


def _run_program(binary, code, receipt, *, timeout, evidence_dir):
    receipt["program"] = {"hex": code.hex(), "size": len(code),
                          "sha256": hashlib.sha256(code).hexdigest()}
    with QemuAGI(binary, code, timeout=timeout, evidence_dir=evidence_dir) as vm:
        receipt["binary"] = {"path": str(vm.binary), "sha256": vm.binary_sha256}
        scene = AGISceneHarness(vm)
        receipt["attachment"] = scene.attachment
        receipt["configuration"] = scene.configure(mask=2, capacity=8, step_budget=4)
        receipt["capture"] = scene.run()
        receipt["final_state"] = vm.state()
        if receipt["final_state"]["guest"]["status"] != "return":
            raise HarnessError("Authored scene edit program did not return within its bound")
        if receipt["capture"]["view"]["source"]["sha256"] != receipt["program"]["sha256"]:
            raise HarnessError("Captured source does not match the supplied program")
    return receipt["capture"]["view"]


def _candidate_bytes(original, plan):
    """Independently check the preimage and candidate before starting replay."""
    if plan["source"]["sha256"] != hashlib.sha256(original).hexdigest() \
            or plan["source"]["size"] != len(original):
        raise HarnessError("Edit plan does not bind the original source")
    offset = plan["offset"]
    if type(offset) is not int or not 0 <= offset <= len(original) - 4 \
            or plan["length"] != 4:
        raise HarnessError("Edit plan has an invalid instruction span")
    expected = bytes(plan["expected_bytes"])
    replacement = bytes(plan["replacement_bytes"])
    if len(expected) != 4 or len(replacement) != 4 \
            or original[offset:offset + 4] != expected \
            or expected[:2] != bytes((37, 0)) or replacement[:2] != expected[:2]:
        raise HarnessError("Edit plan changed more than the selected literal operands")
    candidate = original[:offset] + replacement + original[offset + 4:]
    if len(candidate) != len(original) \
            or plan["candidate_source"]["size"] != len(candidate) \
            or hashlib.sha256(candidate).hexdigest() != plan["candidate_source"]["sha256"]:
        raise HarnessError("Constructed candidate does not match the edit plan")
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Explicit qemu-system-agi executable")
    parser.add_argument("--output", required=True, help="New JSON receipt path; never overwritten")
    parser.add_argument("--evidence-dir", help="Existing private directory for failed native runs")
    parser.add_argument("--timeout", type=_bounded_timeout, default=10.0)
    args = parser.parse_args(argv)

    output = Path(args.output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Scene edit demonstration requires a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "fdisbull-agi-scene-edit-demo-1", "status": "running",
        "scope": "Authored literal-position pilot; a source edit requires fresh outcome validation",
        "parameters": {"mask": 2, "capacity": 8, "step_budget": 4,
                       "maximum_children": 4, "maximum_resumes_per_child": 1,
                       "timeout": args.timeout},
        "cases": [],
    }
    with output.open("x", encoding="utf-8") as stream:
        try:
            for name, original in CASES:
                case = {"name": name, "original": {}, "candidate": {}}
                report["cases"].append(case)
                view = _run_program(args.binary, original, case["original"],
                                    timeout=args.timeout, evidence_dir=args.evidence_dir)
                plan = plan_literal_position_edit(original, view, actor=0, **REQUESTED)
                case["plan"] = plan
                candidate = _candidate_bytes(original, plan)
                candidate_view = _run_program(
                    args.binary, candidate, case["candidate"],
                    timeout=args.timeout, evidence_dir=args.evidence_dir,
                )
                if candidate_view["source"] != plan["candidate_source"]:
                    raise HarnessError("Observed candidate identity differs from the edit plan")
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
