#!/usr/bin/env python3
"""Measure the actual AGI TCG target with interleaved observation modes.

The target's native timer is the primary measurement. Host QMP time is recorded
separately. This is an authored microbenchmark, not a complete AGI engine or a
comparison against ScummVM/DOSBox. No runtime is downloaded or discovered.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

from harness import QemuAGI, guest_state


MODES = {0: "off", 1: "disasm", 2: "scene", 3: "both"}
# Each mode occupies every position once in a four-round cycle.
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (3, 0, 2, 1), (2, 3, 1, 0))


def authored_workloads():
    """Raw AGI code, with a signed backward GOTO and no resource header."""
    scalar = bytes([5, 1, 1, 5, 2, 7, 7, 3, 3, 14, 0])
    sparse = b"".join(bytes([5, 1 if i % 2 == 0 else 2, 1])
                      for i in range(30)) + bytes([38, 0, 1, 2])
    dense = bytes([5, 1, 1, 38, 0, 1, 2, 5, 2, 1, 38, 0, 1, 2])
    values = {}
    for name, body, instructions, positions in (
        ("scalar", scalar, 4, ()),
        ("scene_sparse", sparse, 31, (30,)),
        ("scene_dense", dense, 4, (1, 3)),
    ):
        code = body + b"\xfe" + (-len(body) - 3).to_bytes(2, "little", signed=True)
        values[name] = {"code": code, "cycle_instructions": instructions + 1,
                        "position_ordinals": positions}
    return values


def count_positions(workload, steps):
    cycles, tail = divmod(steps, workload["cycle_instructions"])
    positions = workload["position_ordinals"]
    return cycles * len(positions) + sum(index < tail for index in positions)


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def distribution(values):
    values = sorted(values)
    def percentile(fraction):
        index = (len(values) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (index - lower)
    return {"n": len(values), "median": statistics.median(values),
            "p10": percentile(0.1), "p90": percentile(0.9),
            "minimum": values[0], "maximum": values[-1]}


def checked_run(vm, workload, mask, args, reference):
    vm.restart()
    vm.configure(mask=mask, capacity=args.capacity, step_budget=args.steps)
    state = vm.run()
    guest = guest_state(state)
    if guest["status"] != "budget" or guest["fault"] is not None:
        raise RuntimeError(f"Expected native budget stop, got {guest['status']}")
    if guest["retired"] != args.steps or state["run"]["retired"] != args.steps:
        raise RuntimeError("Native instruction budget did not match requested work")
    if reference is not None and guest != reference:
        raise RuntimeError("Observation mode changed authoritative guest state")
    source = state["source"]
    if source["sha256"] != vm.source_sha256 or source["size"] != len(workload["code"]):
        raise RuntimeError("Native source identity differs from authored program")
    obs = state["observation"]
    expected_disasm = args.steps if mask & 1 else 0
    expected_scene = count_positions(workload, args.steps) if mask & 2 else 0
    expected_calls = args.steps if mask & 1 else expected_scene
    if obs["mask"] != mask or obs["capacity"] != args.capacity:
        raise RuntimeError("Native observation control readback differs")
    if obs["eligible"] != expected_disasm + expected_scene:
        raise RuntimeError("Native eligible-event count differs from authored loop")
    if obs["helper_calls"] != expected_calls:
        raise RuntimeError("Native observation helper-call count differs")
    for name, expected in (("disasm", expected_disasm), ("scene", expected_scene)):
        channel = obs["per_channel"][name]
        if channel["eligible"] != expected or channel["stored"] + channel["dropped"] != expected:
            raise RuntimeError(f"Native {name} event accounting differs")
    if obs["count"] != min(args.capacity, obs["eligible"]) \
            or obs["count"] + obs["dropped"] != obs["eligible"]:
        raise RuntimeError("Native buffer accounting differs")
    if obs["dropped"] and not args.allow_drops:
        raise RuntimeError("Unexpected observation loss in emission benchmark")
    elapsed = state["run"]["elapsed_ns"]
    if type(elapsed) is not int or elapsed <= 0:
        raise RuntimeError("Native elapsed timer must be a positive integer")
    return guest, {
        "mode": MODES[mask], "mask": mask,
        "native_elapsed_ns": elapsed,
        "host_qmp_wall_ns": vm.last_run_wall_ns,
        "retired": state["run"]["retired"],
        "invocation": state["run"]["invocation"],
        "guest_sha256": fingerprint(guest),
        "observation": obs,
    }


def measure(args):
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise ValueError("Use a new output path; prior evidence is not overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    journal_path = output.with_suffix(output.suffix + ".jsonl")
    report = {
        "schema": "fdisbull-agi-observation-benchmark-1",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "python": platform.python_version(),
                     "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None},
        "parameters": {"steps": args.steps, "rounds": args.rounds,
                       "warmups_per_mode": args.warmups, "capacity": args.capacity,
                       "warmup_order": list(args.warmup_order),
                       "allow_drops": args.allow_drops, "readout_rounds": args.readout_rounds},
        "measurement": "Native monotonic interval inside QEMU; QMP wall time recorded separately",
        "scope": "Authored scalar/position microbenchmarks; one instruction per TB; no full engine or other-emulator speed claim",
        "workloads": {},
    }
    with journal_path.open("x", encoding="utf-8") as journal:
        try:
            for name, workload in authored_workloads().items():
                entry = {
                    "code_hex": workload["code"].hex(),
                    "source_sha256": hashlib.sha256(workload["code"]).hexdigest(),
                    "cycle_instructions": workload["cycle_instructions"],
                    "position_ordinals": list(workload["position_ordinals"]),
                    "expected_scene_events": count_positions(workload, args.steps),
                    "samples": [],
                    "readout_samples": [],
                }
                report["workloads"][name] = entry
                with QemuAGI(args.binary, workload["code"], timeout=args.timeout) as vm:
                    report["binary_sha256"] = vm.binary_sha256
                    report["binary"] = str(vm.binary)
                    reference = None
                    for _ in range(args.warmups):
                        for mask in args.warmup_order:
                            guest, _ = checked_run(vm, workload, mask, args, reference)
                            if reference is None:
                                reference = guest
                    for round_number in range(args.rounds):
                        for order, mask in enumerate(ORDERS[round_number % len(ORDERS)]):
                            guest, sample = checked_run(vm, workload, mask, args, reference)
                            if reference is None:
                                reference = guest
                            sample.update({"round": round_number, "order": order})
                            entry["samples"].append(sample)
                            journal.write(json.dumps({"workload": name, **sample}, sort_keys=True) + "\n")
                            journal.flush()
                    entry["guest_sha256"] = fingerprint(reference)
                    # Separate end-to-end readout measurements. They include
                    # stopped validation, native JSON formatting, QMP transport
                    # and both JSON decodes, after the hot-loop timing is done.
                    for readout_round in range(args.readout_rounds):
                        for mask in ORDERS[readout_round % len(ORDERS)]:
                            _, native = checked_run(vm, workload, mask, args, reference)
                            start = time.perf_counter_ns()
                            raw = vm.get("agi-events-json")
                            records = json.loads(raw)
                            wall_ns = time.perf_counter_ns() - start
                            if records["source"]["sha256"] != vm.source_sha256 \
                                    or len(records["events"]) != native["observation"]["count"]:
                                raise RuntimeError("Event readout identity/count differs")
                            row = {"round": readout_round, "mask": mask,
                                   "mode": MODES[mask], "readout_wall_ns": wall_ns,
                                   "events_json_bytes": len(raw.encode("utf-8")),
                                   "records": len(records["events"])}
                            entry["readout_samples"].append(row)
                            journal.write(json.dumps({"workload": name, "readout": row}, sort_keys=True) + "\n")
                            journal.flush()
                            del raw, records
                summary = {}
                off_by_round = {s["round"]: s["native_elapsed_ns"] for s in entry["samples"] if s["mask"] == 0}
                for mask, mode in MODES.items():
                    selected = [s for s in entry["samples"] if s["mask"] == mask]
                    summary[mode] = {
                        "native_ns": distribution([s["native_elapsed_ns"] for s in selected]),
                        "host_qmp_wall_ns": distribution([s["host_qmp_wall_ns"] for s in selected]),
                        "paired_change_percent": distribution([
                            (s["native_elapsed_ns"] / off_by_round[s["round"]] - 1) * 100
                            for s in selected]),
                        "retained_events": selected[0]["observation"]["count"],
                        "dropped_events": selected[0]["observation"]["dropped"],
                        "observation_helper_calls": selected[0]["observation"]["helper_calls"],
                    }
                    readouts = [s for s in entry["readout_samples"] if s["mask"] == mask]
                    summary[mode]["readout_wall_ns"] = distribution([s["readout_wall_ns"] for s in readouts])
                    summary[mode]["events_json_bytes"] = distribution([s["events_json_bytes"] for s in readouts])
                entry["summary"] = summary
                print(json.dumps({"workload": name, "summary": summary}, sort_keys=True), flush=True)
            report["status"] = "passed"
        except BaseException as error:
            report["status"] = "failed"
            report["failure"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Explicit qemu-system-agi executable")
    parser.add_argument("--output", required=True, help="New evidence JSON path outside the checkout")
    parser.add_argument("--steps", type=int, default=32768)
    parser.add_argument("--rounds", type=int, default=31)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--warmup-order", type=int, nargs=4, default=(0, 1, 2, 3),
                        metavar="MASK", help="Permutation of 0 1 2 3; controls first translation order")
    parser.add_argument("--capacity", type=int, default=65536)
    parser.add_argument("--readout-rounds", type=int, default=3)
    parser.add_argument("--allow-drops", action="store_true", help="Separate saturation experiment; report losses explicitly")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if sorted(args.warmup_order) != [0, 1, 2, 3]:
        parser.error("Warmup order must contain each mask 0, 1, 2, 3 exactly once")
    if not 1 <= args.steps <= 1_000_000_000 or not 1 <= args.rounds <= 200 \
            or not 1 <= args.warmups <= 20 or not 0 <= args.capacity <= 65536 \
            or not 1 <= args.readout_rounds <= 10:
        parser.error("Invalid finite steps/rounds/warmups/capacity")
    if not args.allow_drops and args.capacity < 2 * args.steps:
        parser.error("Emission benchmark needs capacity >= 2*steps; use --allow-drops for a separate saturation experiment")
    measure(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
