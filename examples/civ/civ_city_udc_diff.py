"""Differentially check the Civ city UDC shell against the shared-IL interpreter.

The native shell is a realization of the same UIL state transition.  This
sweep builds one module per boundary state, runs the emitted program, and
compares its observation frame with ``execute_il`` on the primitive program.
It proves interpreter/native agreement for the tested states only; it does not
prove source-to-UIL fidelity.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

from examples.civ.civ_city_buy_udc import build_buy_udc, buy_program
from examples.civ.civ_city_uil import _primitive_program, build_city_udc
from fdisbull.interaction_il import execute_il

CASES = (
    ("default", {"$shield_box": 0, "$shield_delta": 3}),
    ("wrap-high", {"$shield_box": 32767, "$shield_delta": 1}),
    ("wrap-low", {"$shield_box": -32768, "$shield_delta": -1}),
    ("negative-box", {"$shield_box": -5, "$shield_delta": 3}),
    ("disorder-zeroes", {"$shield_box": 7, "$shield_delta": 5, "$disorder": True}),
    (
        "unsanitized-refusal",
        {"$shield_box": 4, "$shield_delta": 2, "$sanitized": False},
    ),
)


def _expected(state: dict) -> dict:
    program = _primitive_program(state)
    merged = {name: value["initial"] for name, value in program["variables"].items()}
    result = execute_il(program, merged)
    if result["status"] == "refused":
        return {"status": "refused", "detail": result["error"]}
    return {
        "status": "committed",
        "state": {
            name: int(value) if isinstance(value, bool) else value
            for name, value in result["state"].items()
        },
    }


def _normalize(frame_state: dict, state: dict) -> dict:
    return {
        name: int(value) if isinstance(state.get(name), bool) else value
        for name, value in frame_state.items()
    }


BUY_CASES = (
    ("default", {"$shield_box": 7, "$treasury": 200, "$item_cost": 4, "$price": 160}),
    (
        "exact-affordable",
        {"$shield_box": 3, "$treasury": 160, "$item_cost": 4, "$price": 160},
    ),
    (
        "insufficient",
        {"$shield_box": 3, "$treasury": 100, "$item_cost": 4, "$price": 160},
    ),
    (
        "wrap-item-cost",
        {"$shield_box": 0, "$treasury": 50, "$item_cost": 4000, "$price": 10},
    ),
    ("zero-price", {"$shield_box": 0, "$treasury": 30, "$item_cost": 1, "$price": 0}),
)
BUY_PUBLIC = ("$shield_box", "$treasury", "$item_cost", "$price")


def run_case(root: Path, work: Path, name: str, initial: dict, target: str) -> dict:
    destination = work / name
    receipt = build_city_udc(
        root,
        destination,
        project_path=work / (name + ".fdb"),
        initial=initial,
        target=target,
    )
    program = destination / "program"
    done = subprocess.run(
        [str(program)], capture_output=True, text=True, timeout=120, check=False
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    frame = json.loads(lines[-1]) if done.returncode == 0 and lines else None
    expected = _expected(initial)
    merged = {
        name_: value["initial"]
        for name_, value in _primitive_program(initial)["variables"].items()
    }
    observed = {
        "returncode": done.returncode,
        "frame": frame,
        "stderr": done.stderr.strip()[-400:],
    }
    if expected["status"] == "refused":
        # Refusal is observable as a nonzero exit with no observation frame; the
        # program writes nothing, so no state is published.
        matched = done.returncode != 0 and frame is None
    else:
        matched = (
            done.returncode == 0
            and frame is not None
            and frame["status"] == 0
            and _normalize(frame["state"], merged) == expected["state"]
        )
    return {
        "case": name,
        "initial": initial,
        "expected": expected,
        "observed": observed,
        "match": bool(matched),
        "native_artifact": receipt["native_build"]["output"]["sha256"],
        "profile": receipt["native_build"]["profile"],
    }


def run_buy_case(root: Path, work: Path, name: str, initial: dict, target: str) -> dict:
    destination = work / name
    receipt = build_buy_udc(
        root,
        destination,
        project_path=work / (name + ".fdb"),
        initial=initial,
        target=target,
    )
    program = destination / "program"
    done = subprocess.run(
        [str(program)], capture_output=True, text=True, timeout=120, check=False
    )
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    frame = json.loads(lines[-1]) if done.returncode == 0 and lines else None
    program_doc = buy_program(initial)
    merged = {n: v["initial"] for n, v in program_doc["variables"].items()}
    result = execute_il(program_doc, merged)
    if result["status"] == "refused":
        expected = {"status": "refused", "detail": result["error"]}
        matched = done.returncode != 0 and frame is None
    else:
        expected = {key: result["state"][key] for key in BUY_PUBLIC}
        matched = (
            done.returncode == 0
            and frame is not None
            and frame["status"] == 0
            and all(frame["state"][key] == expected[key] for key in BUY_PUBLIC)
        )
    observed = {
        "returncode": done.returncode,
        "frame": frame,
        "stderr": done.stderr.strip()[-400:],
    }
    return {
        "case": name,
        "initial": initial,
        "expected": expected,
        "observed": observed,
        "match": bool(matched),
        "native_artifact": receipt["native_build"]["output"]["sha256"],
        "profile": receipt["native_build"]["profile"],
    }


def sweep_buy(
    root: str | Path, work: str | Path, *, target: str, cases=BUY_CASES
) -> dict:
    work_path = Path(work).expanduser().resolve()
    if work_path.exists():
        raise ValueError("sweep work directory must be new")
    work_path.mkdir(parents=True)
    rows = [
        run_buy_case(
            Path(root).expanduser().resolve(), work_path, name, initial, target
        )
        for name, initial in cases
    ]
    return {
        "format": "fdisbull-civ-city-buy-diff-1",
        "target": target,
        "host": {"platform": sys.platform, "machine": platform.machine()},
        "cases": rows,
        "verdict": "match" if all(row["match"] for row in rows) else "mismatch",
        "scope": "interpreter/native agreement for the buy guard and commit; price derivation excluded",
    }


def sweep(root: str | Path, work: str | Path, *, target: str, cases=CASES) -> dict:
    work_path = Path(work).expanduser().resolve()
    if work_path.exists():
        raise ValueError("sweep work directory must be new")
    work_path.mkdir(parents=True)
    rows = [
        run_case(Path(root).expanduser().resolve(), work_path, name, initial, target)
        for name, initial in cases
    ]
    return {
        "format": "fdisbull-civ-city-udc-diff-1",
        "target": target,
        "host": {"platform": sys.platform, "machine": platform.machine()},
        "cases": rows,
        "verdict": "match" if all(row["match"] for row in rows) else "mismatch",
        "scope": (
            "interpreter/native agreement for the tested boundary states; "
            "not source-to-UIL fidelity"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Civ city UDC against the interpreter"
    )
    parser.add_argument("source", help="exact unpacked CIV_UNP.EXE")
    parser.add_argument("work", help="new output directory outside Git")
    parser.add_argument(
        "--target", choices=("linux-x64", "macos-arm64"), default="macos-arm64"
    )
    parser.add_argument("--module", choices=("city", "buy", "all"), default="all")
    args = parser.parse_args(argv)
    if args.module == "city":
        receipt = sweep(args.source, args.work, target=args.target)
    elif args.module == "buy":
        receipt = sweep_buy(args.source, args.work, target=args.target)
    else:
        work = Path(args.work)
        receipt = {
            "format": "fdisbull-civ-city-udc-diff-2",
            "city": sweep(args.source, work / "city", target=args.target),
            "buy": sweep_buy(args.source, work / "buy", target=args.target),
        }
        receipt["verdict"] = (
            "match"
            if all(
                part["verdict"] == "match" for part in (receipt["city"], receipt["buy"])
            )
            else "mismatch"
        )
        receipt["scope"] = (
            "interpreter/native agreement for the modelled transitions; "
            "not source-to-UIL fidelity"
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["verdict"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
