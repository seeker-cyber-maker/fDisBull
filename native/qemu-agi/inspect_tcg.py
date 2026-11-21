#!/usr/bin/env python3
"""Inspect real generated TCG, with positive controls for observation helpers.

This logging run is separate from performance measurements. Inputs are authored
straight-line programs; every translated instruction executes exactly once.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from harness import QemuAGI, guest_state


def inspect(binary, output):
    directory = Path(output).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=False)
    report = {"schema": "fdisbull-agi-tcg-observation-inspection-1",
              "status": "running", "cases": []}
    try:
        for name, code in (("scalar", bytes([3, 1, 7, 0])),
                           ("position", bytes([37, 0, 10, 20, 0]))):
            expected_guest = None
            for mask in (0, 1, 2, 3):
                log = directory / f"{name}-mask-{mask}.tcg.log"
                with QemuAGI(binary, code, extra_args=("-d", "op", "-D", str(log)),
                             evidence_dir=directory) as vm:
                    vm.configure(mask=mask, capacity=8, step_budget=16)
                    state = vm.run()
                    guest = guest_state(state)
                    if guest["status"] != "return" or guest["retired"] != 2:
                        raise RuntimeError("Authored TCG control did not complete")
                    if expected_guest is None:
                        expected_guest = guest
                    elif guest != expected_guest:
                        raise RuntimeError("TCG observation selection changed guest state")
                    report["binary_sha256"] = vm.binary_sha256
                    report["binary"] = str(vm.binary)
                content = log.read_text(encoding="utf-8")
                helpers = {name: len(re.findall(r"\bcall\s+" + re.escape(name) + r"\b", content))
                           for name in ("agi_observe", "agi_retire", "agi_fault")}
                expected = 2 if mask & 1 else int(name == "position" and bool(mask & 2))
                case = {"program": name, "mask": mask,
                        "source_sha256": hashlib.sha256(code).hexdigest(),
                        "expected_observation_calls": expected,
                        "generated_helper_calls": helpers,
                        "runtime_observation_calls": state["observation"]["helper_calls"],
                        "log": log.name, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}
                report["cases"].append(case)
                if helpers["agi_retire"] != 2 or helpers["agi_fault"] != 0:
                    raise RuntimeError("TCG log lacks expected positive execution controls")
                if helpers["agi_observe"] != expected or case["runtime_observation_calls"] != expected:
                    raise RuntimeError("Generated/runtime observation calls differ from selection")
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        (directory / "inspection.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", required=True, help="New private evidence directory")
    args = parser.parse_args()
    report = inspect(args.binary, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
