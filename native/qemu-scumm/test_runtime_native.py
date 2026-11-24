#!/usr/bin/env python3
"""Authored QMP acceptance checks for the isolated Amiga v2 resource context.

No original game data or portable-core oracle is used. Resource files are small
synthetic old-bundle containers. Outputs record checks, never resource bytes.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from test_native import (BLOCKED, BUDGET, FAULT, READY, RETURN, CheckFailure,
                         QMP, architecture, expect, state_summary)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(directory: Path, code: bytes, script_id: int = 1) -> Path:
    """Bind authored code and two opaque resources; most valid slots stay absent."""
    manifest: dict[str, Any] = {
        "schema": "fdisbull-scumm-v2-resources-1",
        "profile": "amiga-v2-isolated",
        "source_receipt_sha256": digest(b"authored resource-context fixture"),
        "script_id": script_id, "code_sha256": digest(code),
        "counts": {"costume": 8, "room": 8, "script": 16, "sound": 8},
        "resources": [],
    }
    for kind, ident, body in (("script", script_id, code),
                              ("script", 4, b"\x00"),
                              ("costume", 2, b"opaque authored costume")):
        whole = (len(body) + 4).to_bytes(2, "little") + b"\x91\xa2" + body
        relative = f"resources/{kind}/{ident:03}.bin"
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(whole)
        manifest["resources"].append({"type": kind, "id": ident,
            "size": len(whole), "sha256": digest(whole), "path": relative})
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return path


def runtime(qmp: QMP) -> dict[str, Any]:
    return json.loads(qmp.get("scumm-runtime-json"))


def resource(state: dict[str, Any], kind: str, ident: int) -> dict[str, Any] | None:
    return next((r for r in state["resources"]
                 if (r["type"], r["id"]) == (kind, ident)), None)


def resource_transactions(binary: Path, timeout: float) -> dict[str, Any]:
    # Lock unavailable sound slot; load costume; unlock sound; load another
    # script without scheduling it; return from the immutable original code.
    code = bytes([0x0c, 3, 0x63, 0x0c, 2, 0x21, 0x0c, 3, 0x62,
                  0x0c, 4, 0x51, 0x00])
    with tempfile.TemporaryDirectory(prefix="scumm-bank-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            q.set("scumm-observation-mask", 3)
            q.set("scumm-step-budget", 1)
            initial = runtime(q)
            expect(initial["enabled"], True, "explicit context enabled")
            expect(initial["manifest_sha256"], digest(manifest.read_bytes()), "manifest identity")
            expect(resource(initial, "script", 1)["resident"], True, "active script residency")
            expect(resource(initial, "script", 4)["resident"], False, "inactive script residency")
            for index, next_pc in enumerate((3, 6, 9, 12, 13), 1):
                result = q.run()
                expect((result["pc"], result["retired"], result["run_retired"]),
                       (next_pc, index, 1), "one effect charged to one-instruction budget")
                expect(result["status"], RETURN if index == 5 else BUDGET, "bounded effect status")
                current = runtime(q)
                if index == 1:
                    record = resource(current, "sound", 3)
                    expect((record["available"], record["resident"], record["locked"]),
                           (False, False, True), "locking does not load")
                if index == 2:
                    expect(resource(current, "costume", 2)["resident"], True, "verified costume loaded")
                if index >= 3:
                    expect(resource(current, "sound", 3), None, "unlocked absent slot has no state")
                if index >= 4:
                    expect(resource(current, "script", 4)["resident"], True, "script bank residency")
                expect(current["code_sha256"], digest(code), "loading cannot replace code")
            expect([event["pc"] for event in q.trace()], [0, 3, 6, 9, 12], "exactly-once retirement")
            q.reset()
            expect(runtime(q), initial, "system reset clears runtime and preserves catalog")
            expect((q.run()["pc"], resource(runtime(q), "sound", 3)["locked"]),
                   (3, True), "resource execution after system reset")
            q.set("scumm-restart", True)
            expect(q.state()["status"], READY, "restart execution")
            expect(runtime(q), initial, "restart clears mutable runtime and preserves catalog")
            return {"checks": 5, "final": state_summary(result)}


def control_observations(binary: Path, timeout: float) -> dict[str, Any]:
    # Cursor shows all UI and input, then begin saves it and hides controls.
    code = bytes([0x1a, 38, 7, 0, 0x1a, 21, 13, 0,
                  0x60, 9, 0xf6, 0x40, 0x0c, 3, 0x53, 0x00])
    baseline = None
    with tempfile.TemporaryDirectory(prefix="scumm-control-") as temporary:
        manifest = fixture(Path(temporary), code)
        for mask in range(4):
            for capacity in (0, 1, 64):
                with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
                    q.set("scumm-observation-mask", mask)
                    q.set("scumm-observation-capacity", capacity)
                    result = q.run()
                    current = runtime(q)
                    expect((result["status"], result["retired"]), (RETURN, 6), "control retirement")
                    expect([result["vars"][n] for n in (21, 26, 27, 28, 29, 38)],
                           [200, 7, 0, 0, 0, 7], "cutscene variables")
                    control = current["control"]
                    expect([control[n] for n in ("user_state", "user_put", "cursor_visible",
                            "cutscene_active", "saved_user_state", "saved_cursor", "ui_revision")],
                           [0, 0, 0, 1, 0xf0, 9, 2], "saved UI and current UI")
                    observed = (architecture(result), current)
                    if baseline is None:
                        baseline = observed
                    expect(observed, baseline, "full architecture and runtime observation invariance")
                    expect(runtime(q), current, "runtime getter is pure")
                    q.set("scumm-restart", True)
                    restarted = runtime(q)
                    expect(restarted["control"]["ui_revision"], 0, "restart UI revision")
                    expect(restarted["control"]["cutscene_active"], 0, "restart cutscene state")
                    expect(restarted["manifest_sha256"], current["manifest_sha256"], "restart source identity")
    return {"observation_pairs": 12, "full_runtime_compared": True}


def atomic_boundaries(binary: Path, timeout: float) -> dict[str, Any]:
    cases = [
        ("missing_load", bytes([0x0c, 3, 0x61]), 1, False, BLOCKED, "resource_bytes_unavailable"),
        ("room_mapper", bytes([0x0c, 200, 0x31]), 1, False, BLOCKED, "room_mapper_required"),
        ("script_start", bytes([0x42, 4]), 1, False, BLOCKED, "unimplemented_effect"),
        ("nested_entry", bytes([0x40, 0x40]), 1, True, BLOCKED, "nested_cutscene"),
        ("camera_exit", bytes([0x40, 0xc0]), 1, True, BLOCKED, "unimplemented_effect"),
        ("sentence_owner", bytes([0x40]), 2, False, BLOCKED, "sentence_script_owner"),
        ("invalid_index", bytes([0x0c, 8, 0x63]), 1, False, FAULT, "none"),
    ]
    for name, code, script_id, prefix, status, reason in cases:
        with tempfile.TemporaryDirectory(prefix="scumm-atomic-") as temporary:
            manifest = fixture(Path(temporary), code, script_id)
            with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
                q.set("scumm-observation-mask", 3)
                if prefix:
                    q.set("scumm-step-budget", 1)
                    expect(q.run()["status"], BUDGET, name + " accepted prefix")
                before, before_runtime, before_trace = q.state(), runtime(q), q.trace()
                result = q.run()
                after_runtime = runtime(q)
                expect((result["status"], after_runtime["blocked_reason"]), (status, reason), name)
                if status == FAULT:
                    expect(result["fault"], 8, "resource index fault")
                for field in ("pc", "retired", "vars", "actor_metadata", "actor_placement_model"):
                    expect(result[field], before[field], name + " no partial " + field)
                changed_reason = after_runtime.pop("blocked_reason")
                before_runtime.pop("blocked_reason")
                expect(after_runtime, before_runtime, name + " no partial runtime")
                expect(q.trace(), before_trace, name + " no retired event")
                expect(architecture(q.run()), architecture(result), name + " sticky terminal")
                expect(runtime(q)["blocked_reason"], changed_reason, name + " stable reason")
    return {"atomic_boundaries": len(cases)}


def immutable_bank(binary: Path, timeout: float) -> dict[str, Any]:
    code = bytes([0x0c, 2, 0x21, 0x00])
    with tempfile.TemporaryDirectory(prefix="scumm-immutable-") as temporary:
        directory = Path(temporary)
        manifest = fixture(directory, code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            original = runtime(q)
            (directory / "resources/costume/002.bin").write_bytes(b"changed after startup")
            manifest.write_text("not a manifest anymore")
            result = q.run()
            expect(result["status"], RETURN, "resident bank needs no post-startup file reads")
            current = runtime(q)
            expect(current["manifest_sha256"], original["manifest_sha256"], "immutable manifest identity")
            expect(resource(current, "costume", 2)["sha256"],
                   resource(original, "costume", 2)["sha256"], "retained verified payload identity")
            q.command("qom-set", {"path": "/machine", "property": "resource-manifest",
                                 "value": str(manifest)}, error=True)
            expect(runtime(q), current, "no live catalog replacement")
    return {"immutable_bank": True}


def rejected_manifests(binary: Path, timeout: float) -> dict[str, Any]:
    cases = ("schema", "profile", "code_hash", "resource_hash", "header_size",
             "duplicate", "count", "missing_script", "absolute", "parent", "symlink",
             "directory_symlink", "nul_path", "oversized", "wrong_version", "wrong_kernel",
             "bound_script", "float_count", "bool_count", "duplicate_key", "fifo", "late_hash")
    for name in cases:
        with tempfile.TemporaryDirectory(prefix="scumm-reject-") as temporary:
            directory = Path(temporary)
            code = b"\x00"
            manifest = fixture(directory, code)
            data = json.loads(manifest.read_text())
            entry = data["resources"][0]
            version = 2
            if name in ("schema", "profile"):
                data[name] = "unknown"
            elif name == "code_hash":
                data["code_sha256"] = "0" * 64
            elif name == "resource_hash":
                entry["sha256"] = "0" * 64
            elif name == "header_size":
                path = directory / entry["path"]
                payload = b"\x04\x00" + path.read_bytes()[2:]
                path.write_bytes(payload)
                entry["sha256"] = digest(payload)
            elif name == "duplicate":
                data["resources"].append(copy.deepcopy(entry))
            elif name == "count":
                data["counts"]["script"] = 257
            elif name == "float_count":
                data["counts"]["script"] = 16.5
            elif name == "bool_count":
                data["counts"]["script"] = True
            elif name == "missing_script":
                data["resources"].pop(0)
            elif name == "absolute":
                entry["path"] = str(directory / entry["path"])
            elif name == "parent":
                entry["path"] = "resources/../" + entry["path"]
            elif name == "nul_path":
                entry["path"] += "\x00ignored"
            elif name == "symlink":
                path = directory / entry["path"]
                saved = path.with_suffix(".actual")
                path.rename(saved)
                path.symlink_to(saved.name)
            elif name == "directory_symlink":
                path = directory / "resources/script"
                saved = directory / "script-actual"
                path.rename(saved)
                path.symlink_to(saved)
            elif name == "wrong_version":
                version = 1
            elif name == "wrong_kernel":
                code = b"\x80"
            elif name == "bound_script":
                path = directory / entry["path"]
                payload = path.read_bytes()[:-1] + b"\x80"
                path.write_bytes(payload)
                entry["sha256"] = digest(payload)
            elif name == "fifo":
                path = directory / entry["path"]
                path.unlink()
                os.mkfifo(path)
            elif name == "late_hash":
                data["resources"][-1]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(data) + "\n")
            if name == "duplicate_key":
                manifest.write_text('{"schema":"ambiguous",' + json.dumps(data)[1:])
            if name == "oversized":
                manifest.write_text(" " * (2 * 1024 * 1024 + 1))
            qmp = QMP(binary, version, code, timeout, resource_manifest=manifest)
            try:
                with qmp:
                    pass
            except CheckFailure as exc:
                if "deadline" in str(exc):
                    raise CheckFailure(name + " hung instead of rejecting") from exc
                expect(qmp.process.returncode if qmp.process else None, 1,
                       name + " clean validation exit (not a crash)")
                diagnostic = ("SCUMM resource-manifest requires version=2"
                              if name == "wrong_version" else "SCUMM_RESOURCE:")
                if diagnostic not in str(exc):
                    raise CheckFailure(name + " lacked a resource admission diagnostic") from exc
            else:
                raise CheckFailure(name + " malformed bank unexpectedly admitted")
    return {"rejected_startups": len(cases)}


CASES = {"resource_transactions": resource_transactions,
         "control_observations": control_observations,
         "atomic_boundaries": atomic_boundaries,
         "immutable_bank": immutable_bank,
         "rejected_manifests": rejected_manifests}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--case", choices=CASES, action="append")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than zero and at most 60 seconds")
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / ".git").exists() and args.output.resolve().is_relative_to(source_root):
        parser.error("--output must be outside the source checkout")
    binary = args.qemu.resolve()
    original_binary_sha256 = digest(binary.read_bytes())
    records = []
    for name in args.case or CASES:
        started = time.monotonic()
        try:
            detail = CASES[name](binary, args.timeout)
            record = {"case": name, "passed": True, "detail": detail}
        except Exception as exc:
            record = {"case": name, "passed": False, "error": str(exc)}
        record["seconds"] = round(time.monotonic() - started, 3)
        records.append(record)
        print(json.dumps(record), flush=True)
    result = {"schema": "fdisbull-scumm-v2-native-checks-1",
              "qemu_sha256": original_binary_sha256,
              "harness_sha256": digest(Path(__file__).read_bytes()),
              "passed": all(r["passed"] for r in records), "cases": records}
    if digest(binary.read_bytes()) != original_binary_sha256:
        result.update(passed=False, error="QEMU executable changed during qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
