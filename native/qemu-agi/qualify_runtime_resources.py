#!/usr/bin/env python3
"""Run explicit private resource cases through native AGI under every observation mask.

This is a qualification controller, not an opcode interpreter. The caller supplies
canonical runtime packages, initial variables/flags, a native instruction budget,
and independently obtained expected planes/fields. All output belongs in an
explicit private directory, outside the source checkout when game data is used.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import time

from runtime_harness import QemuAGIRuntime
from runtime_pack import load_package


SCHEMA = "fdisbull-agi-runtime-qualification-1"
MODES = ((0, 0), (1, 4096), (2, 4096), (3, 4096), (3, 1))


def digest(data):
    return sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_json(path, value):
    path.write_bytes(json_bytes(value))


def exact_file(base, record, maximum):
    if type(record) is not dict or set(record) != {"path", "sha256"}:
        raise ValueError("A file reference requires exactly path and sha256")
    if type(record["path"]) is not str or not record["path"] \
            or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
        raise ValueError("Invalid file reference")
    path = (base / record["path"]).resolve()
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if not data or len(data) > maximum or digest(data) != record["sha256"]:
        raise ValueError(f"File size/hash mismatch: {path}")
    return path, data


def field(value, path):
    if type(path) is not list or not path:
        raise ValueError("Expected-field path must be a nonempty list")
    for key in path:
        if type(value) is dict and type(key) is str:
            value = value[key]
        elif type(value) is list and type(key) is int and 0 <= key < len(value):
            value = value[key]
        else:
            raise ValueError(f"Invalid expected-field path: {path!r}")
    return value


def prepare(manifest_path):
    raw = manifest_path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("Qualification manifest exceeds 1 MiB")
    manifest = json.loads(raw)
    if type(manifest) is not dict or set(manifest) != {"schema", "cases"} \
            or manifest["schema"] != SCHEMA or type(manifest["cases"]) is not list \
            or not 1 <= len(manifest["cases"]) <= 32:
        raise ValueError("Invalid qualification manifest")
    names, cases = set(), []
    for case in manifest["cases"]:
        required = {"name", "scope", "package", "seed", "step_budget", "expected_fields", "expected_planes"}
        if type(case) is not dict or set(case) != required:
            raise ValueError("Unexpected qualification case fields")
        name = case["name"]
        if type(name) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name) or name in names:
            raise ValueError("Case names must be unique, bounded path components")
        names.add(name)
        if type(case["scope"]) is not str or not case["scope"].strip():
            raise ValueError("Each case must explicitly describe its qualification scope")
        if type(case["step_budget"]) is not int or not 1 <= case["step_budget"] <= 100000:
            raise ValueError("Qualification step budget must be 1..100000")
        if type(case["seed"]) is not dict or set(case["seed"]) - {"variables", "flags"}:
            raise ValueError("Only explicit initial variables and flags may be seeded")
        if type(case["expected_fields"]) is not list or not case["expected_fields"]:
            raise ValueError("Each case needs independent expected native state fields")
        for expected in case["expected_fields"]:
            if type(expected) is not dict or set(expected) != {"path", "value"} \
                    or type(expected["path"]) is not list or not expected["path"]:
                raise ValueError("Invalid expected state field")
        package_path, package_bytes = exact_file(manifest_path.parent, case["package"], 64 * 1024 * 1024)
        load_package(package_bytes)
        if type(case["expected_planes"]) is not dict or set(case["expected_planes"]) - {"visual", "priority"}:
            raise ValueError("Only visual/priority scene plane comparisons are supported")
        planes = {}
        for plane, reference in case["expected_planes"].items():
            path, data = exact_file(manifest_path.parent, reference, 160 * 168)
            if len(data) != 160 * 168 or any(pixel > 15 for pixel in data):
                raise ValueError("An expected plane must contain 160x168 four-bit indices")
            planes[plane] = (path, data)
        cases.append((case, package_path, package_bytes, planes))
    return raw, cases


def qualify(manifest_path, binary, expected_binary_sha256, output):
    manifest_path, binary, output = map(lambda p: Path(p).resolve(), (manifest_path, binary, output))
    manifest_raw, cases = prepare(manifest_path)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_binary_sha256):
        raise ValueError("An explicit lowercase binary SHA-256 is required")
    if digest(binary.read_bytes()) != expected_binary_sha256:
        raise ValueError("Native executable does not match the admitted binary")
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_bytes(manifest_raw)
    receipt = {
        "schema": SCHEMA, "started_at": datetime.now(timezone.utc).isoformat(),
        "manifest": {"path": str(manifest_path), "sha256": digest(manifest_raw)},
        "binary": {"path": str(binary), "sha256": expected_binary_sha256},
        "controller": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).read_bytes())},
        "argv": sys.argv, "native_children": 0, "cases": [], "passed": False,
    }
    write_json(output / "receipt.json", receipt)
    started = time.monotonic()
    try:
        for case, package_path, package_bytes, expected_planes in cases:
            case_dir = output / case["name"]
            case_dir.mkdir()
            (case_dir / "package.json").write_bytes(package_bytes)
            result = {"name": case["name"], "scope": case["scope"],
                      "package": {"path": str(package_path), "sha256": digest(package_bytes)},
                      "runs": [], "passed": True}
            receipt["cases"].append(result)
            reference_guest, reference_scene = None, None
            for mask, capacity in MODES:
                run_dir = case_dir / f"mask-{mask}-capacity-{capacity}"
                run_dir.mkdir()
                with QemuAGIRuntime(binary, package_bytes, evidence_dir=run_dir) as vm:
                    receipt["native_children"] += 1
                    vm.configure(mask=mask, capacity=capacity)
                    if case["seed"]:
                        vm.seed(**case["seed"])
                    state = vm.run(step_budget=case["step_budget"])
                    guest = state["guest"]
                    events = vm.events()
                    scene = vm.scene()
                    after_inspection = vm.state()
                    fields = [{**expected, "actual": field(state, expected["path"]),
                               "equal": type(field(state, expected["path"])) is type(expected["value"])
                                        and field(state, expected["path"]) == expected["value"]}
                              for expected in case["expected_fields"]]
                    planes = {}
                    for plane in ("visual", "priority"):
                        actual = bytes.fromhex(scene[plane])
                        (run_dir / f"{plane}.idx").write_bytes(actual)
                        if plane in expected_planes:
                            path, expected = expected_planes[plane]
                            differences = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
                            planes[plane] = {
                                "expected_path": str(path), "expected_sha256": digest(expected),
                                "actual_sha256": digest(actual), "mismatches": len(differences),
                                "first_mismatches": [{"x": i % 160, "y": i // 160,
                                                      "actual": actual[i], "expected": expected[i]}
                                                     for i in differences[:32]],
                            }
                    scene_planes = (scene["visual"], scene["priority"])
                    if reference_guest is None:
                        reference_guest, reference_scene = guest, scene_planes
                    observation = state["observation"]
                    checks = {
                        "expected_fields": all(item["equal"] for item in fields),
                        "expected_planes": all(item["mismatches"] == 0 for item in planes.values()),
                        "full_guest_equal_across_observation": guest == reference_guest,
                        "scene_equal_across_observation": scene_planes == reference_scene,
                        "inspection_did_not_mutate_guest": after_inspection["guest"] == guest,
                        "inspection_did_not_mutate_observation": after_inspection["observation"] == observation,
                        "retained_event_count": len(events["events"]) == observation["count"],
                        "disabled_recorder_is_empty": bool(mask) or (not events["events"] and not observation["eligible"]),
                        "full_recorder_has_no_loss": capacity == 1 or observation["dropped"] == 0,
                    }
                    for name, value in (("state", state), ("events", events), ("scene", scene)):
                        write_json(run_dir / f"{name}.json", value)
                    write_json(run_dir / "command.json", {
                        "argv": vm.command, "binary_sha256": vm.binary_sha256,
                        "package_sha256": vm.package_sha256, "initial_context": vm.initial_context,
                        "mask": mask, "capacity": capacity, "step_budget": case["step_budget"],
                    })
                    row = {"mask": mask, "capacity": capacity, "checks": checks,
                           "expected_fields": fields, "planes": planes,
                           "guest_json_sha256": digest(json_bytes(guest)),
                           "observation": observation, "passed": all(checks.values())}
                    result["runs"].append(row)
                    result["passed"] &= row["passed"]
                    write_json(run_dir / "result.json", row)
                write_json(output / "receipt.json", receipt)
            print(json.dumps({"case": case["name"], "passed": result["passed"], "runs": len(result["runs"])}), flush=True)
        receipt["binary_unchanged"] = digest(binary.read_bytes()) == expected_binary_sha256
        receipt["passed"] = receipt["binary_unchanged"] and all(case["passed"] for case in receipt["cases"])
    except BaseException as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(args.manifest, args.binary, args.binary_sha256, args.output)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
