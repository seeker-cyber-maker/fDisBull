#!/usr/bin/env python3
"""Check authored caller/loop obligations without game files or a CPU runner.

This checks a declared 640-column arithmetic domain, not source binding,
ordinary reachability, a production analyzer, memory safety, or a game decoder.
Z3 is optional unless --require-z3 is supplied. No absent solver is a pass.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


def exhaustive_domain() -> dict[str, Any]:
    counts: Counter[int] = Counter()
    pairs = max_iterations = 0
    for left in range(640):
        for right in range(left + 1, 641):
            if (left & 0xFFF8) == (right & 0xFFF8):
                continue
            remainder = right - ((left & 0xFFF8) + 8)
            iterations = 0
            if remainder < 0:
                raise AssertionError("admitted caller gave a negative remainder")
            while remainder > 16:
                remainder -= 16
                iterations += 1
            if not 0 <= remainder <= 16:
                raise AssertionError("tail index outside admitted table")
            counts[remainder] += 1
            max_iterations = max(max_iterations, iterations)
            pairs += 1
    if pairs != 202880 or set(counts) != set(range(17)) or max_iterations != 39:
        raise AssertionError("authored domain census changed")
    # These controls are feasible for the weakened contracts, not admitted callers.
    signed_only = -1
    if not (signed_only <= 16 and signed_only < 0):
        raise AssertionError("signed upper-bound negative control failed")
    disordered = 0 - ((32 & 0xFFF8) + 8)
    if disordered >= 0:
        raise AssertionError("missing endpoint-order negative control failed")
    return {
        "status": "passed",
        "endpoint_pairs": pairs,
        "tail_index_counts": dict(sorted(counts.items())),
        "maximum_middle_iterations": max_iterations,
        "negative_controls": {
            "signed_upper_bound_without_lower_bound": signed_only,
            "lost_endpoint_order_remainder": disordered,
        },
    }


def solver_checks(required: bool) -> dict[str, Any]:
    try:
        import z3
    except ImportError as exc:
        if required:
            raise RuntimeError("--require-z3 needs the optional z3-solver dependency") from exc
        return {"status": "unavailable", "checks": [], "passed": False}
    left, right, remainder = z3.BitVecs("left right remainder", 32)
    initial = right - ((left & z3.BitVecVal(0xFFF8, 32)) + 8)
    cases = [
        ("caller_initial_nonnegative", [left >= 0, left < right, right <= 640,
          (left & 0xFFF8) != (right & 0xFFF8)], z3.Or(initial < 0, initial > 632), "unsat"),
        ("loop_preserves_and_decreases", [remainder >= 0, remainder <= 632, remainder > 16],
         z3.Or(remainder - 16 < 0, remainder - 16 >= remainder), "unsat"),
        ("exit_index_0_through_16", [remainder >= 0, remainder <= 632, z3.Not(remainder > 16)],
         z3.Or(remainder < 0, remainder > 16), "unsat"),
        ("upper_bound_only_counterexample", [z3.Not(remainder > 16)], remainder < 0, "sat"),
        ("lost_order_counterexample", [left >= 0, left <= 640, right >= 0, right <= 640,
          (left & 0xFFF8) != (right & 0xFFF8)], initial < 0, "sat"),
    ]
    results: list[dict[str, Any]] = []
    for name, assumptions, violation, expected in cases:
        solver = z3.Solver()
        solver.set(timeout=5000)
        solver.add(*assumptions, violation)
        result = solver.check()
        if str(result) != expected:
            raise AssertionError(f"{name}: expected {expected}, got {result}")
        record: dict[str, Any] = {"case": name, "expected": expected, "result": str(result)}
        if result == z3.sat:
            record["counterexample"] = {
                str(symbol): solver.model().eval(symbol, model_completion=True).as_long()
                for symbol in (left, right, remainder)
            }
            record["counterexample_encoding"] = "unsigned representation of 32-bit bit vectors"
        results.append(record)
    return {"status": "passed", "version": z3.get_version_string(), "checks": results, "passed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-z3", action="store_true")
    parser.add_argument("--output", type=Path, help="new receipt path; existing files are refused")
    args = parser.parse_args()
    try:
        result = {
            "format": "authored-diagnostic-graphics-model-checks-1",
            "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Authored arithmetic domain only; no source-to-model, native or product conformance claim.",
            "domain": "0 <= left < right <= 640, different 8-column cells; signed 32-bit comparisons",
            "exhaustive": exhaustive_domain(),
            "solver": solver_checks(args.require_z3),
        }
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        print(text, end="")
    except (OSError, RuntimeError, AssertionError) as exc:
        print(f"check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
