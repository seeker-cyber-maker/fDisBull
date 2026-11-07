#!/usr/bin/env python3
"""Inspect and reproduce the known GW32_FIX configuration edit without execution.

This is a research witness for one hash-pinned patcher, not a general patch
parser or a production fDisBull command. The original patcher bytes must be
provided by the caller. This script embeds no original program payload.

The original DOS program reads its six-byte records from absolute file offset
0x1AE. A record is an offset32/expected8/replacement8 tuple, with little-endian
offsets and offset0xFFFFFFFF as the terminator. This witness validates every
expected byte before reconstructing the changed configuration in memory.

The witness deliberately rejects short input and malformed records. The
original patcher does not reliably check DOS read/seek/write errors, so those
strict error checks are safeguards of this verifier, not claimed native behavior.
No supplied file is modified, and no patched configuration is written.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct


PATCH_SIZE = 442
PATCH_SHA256 = "14a89ef5b5249a531f2905c69818a67d79ec968de04a2574723063636eadec49"
TABLE_OFFSET = 0x1AE
MAX_TARGET_BYTES = 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(data: bytes) -> dict:
    """Retain an exact identity without including the supplied file's bytes."""
    return {"size": len(data), "sha256": sha256(data).hexdigest()}


def inspect_patcher(data: bytes) -> dict:
    """Parse only the exact artifact whose table position was statically traced."""
    if len(data) != PATCH_SIZE or sha256(data).hexdigest() != PATCH_SHA256:
        raise ValueError("Patcher identity differs from the inspected GW_FIX.EXE")
    fields = struct.unpack_from("<14H", data)
    if fields[0] != 0x5A4D:
        raise ValueError("Expected the inspected DOS MZ artifact")
    records = []
    cursor = TABLE_OFFSET
    while cursor + 6 <= len(data):
        offset, expected, replacement = struct.unpack_from("<IBB", data, cursor)
        location = cursor
        cursor += 6
        if offset == 0xFFFFFFFF:
            if cursor != len(data):
                raise ValueError("Unexpected bytes after the inspected terminator")
            return {
                "patcher": identity(data),
                "target_filename": "gw.cfg",
                "target_path_scope": "Original patcher uses the current DOS directory",
                "table_offset": TABLE_OFFSET,
                "record_format": "little-endian offset32, expected8, replacement8",
                "records": records,
                "terminator_file_offset": location,
                "mz_declared_size": (fields[2] - 1) * 512 + (fields[1] or 512),
                "mz_header_size": fields[4] * 16,
                "mz_size_inconsistency_is_observed": True,
            }
        records.append({
            "record_file_offset": location,
            "target_offset": offset,
            "expected_value": expected,
            "replacement_value": replacement,
        })
    raise ValueError("Terminator not found")


def reconstruct(target: bytes, records: list[dict]) -> bytes:
    """Preflight every guard, then produce a private in-memory changed copy."""
    if len(target) > MAX_TARGET_BYTES:
        raise ValueError("Research target byte budget exceeded")
    for record in records:
        offset = record["target_offset"]
        if type(offset) is not int or offset < 0:
            raise ValueError("Expected a nonnegative integer target offset")
        if offset >= len(target):
            raise ValueError(f"Target too short for byte at offset {offset:#x}")
        if target[offset] != record["expected_value"]:
            raise ValueError(f"Expected-byte guard failed at offset {offset:#x}")
    output = bytearray(target)
    for record in records:
        output[record["target_offset"]] = record["replacement_value"]
    return bytes(output)


def compare_complete(expected: bytes, candidate: bytes) -> dict:
    """Count overlap and EOF differences separately and compare complete files."""
    changed = [i for i, (left, right) in enumerate(zip(expected, candidate))
               if left != right]
    return {
        "expected": identity(expected),
        "candidate": identity(candidate),
        "equal": expected == candidate,
        "different_overlap_bytes": len(changed),
        "first_overlap_mismatch": changed[0] if changed else None,
        "unmatched_eof_bytes": abs(len(expected) - len(candidate)),
    }


def controls(patcher: bytes) -> list[dict]:
    """Exercise the witness using authored targets; this does not run DOS code."""
    records = inspect_patcher(patcher)["records"]
    original = bytearray(range(64))
    original[0x10] = 0
    original = bytes(original)
    output = reconstruct(original, records)
    require(output[0x10] == 0x6A and output[:0x10] == original[:0x10]
            and output[0x11:] == original[0x11:] and len(output) == len(original)
            and [i for i, (a, b) in enumerate(zip(original, output)) if a != b] == [0x10],
            "One-byte edit control failed")
    result = [{"name": "one_byte_edit_with_complete_surrounding_preservation", "passed": True}]

    for name, value in (("wrong_expected_byte", 0x7F), ("already_patched_guard", 0x6A)):
        altered = bytearray(original)
        altered[0x10] = value
        try:
            reconstruct(bytes(altered), records)
        except ValueError:
            result.append({"name": name, "passed": True})
        else:
            raise AssertionError(name)

    try:
        reconstruct(original[:0x10], records)
    except ValueError:
        result.append({"name": "strict_offline_short_target_rejection", "passed": True,
                       "scope": "Verifier safeguard; original DOS error behavior is not established by this control"})
    else:
        raise AssertionError("short target was accepted")

    altered_patch = bytearray(patcher)
    altered_patch[-1] ^= 1
    try:
        inspect_patcher(bytes(altered_patch))
    except ValueError:
        result.append({"name": "altered_patcher_identity_rejection", "passed": True})
    else:
        raise AssertionError("altered patcher was accepted")

    outside_edit = bytearray(output)
    outside_edit[2] ^= 1
    checked = compare_complete(output, bytes(outside_edit))
    require(not checked["equal"] and checked["first_overlap_mismatch"] == 2,
            "Outside-edit control missed a mismatch")
    result.append({"name": "candidate_mismatch_outside_patch_byte_detected", "passed": True})

    checked = compare_complete(output, output + b"X")
    require(not checked["equal"] and checked["unmatched_eof_bytes"] == 1,
            "EOF control missed a mismatch")
    result.append({"name": "candidate_extra_eof_byte_detected", "passed": True})
    return result


def bounded_read(path: Path, maximum: int) -> bytes:
    """Apply the research limit before retaining an entire caller-supplied file."""
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"Input exceeds the {maximum}-byte research budget: {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patcher", type=Path, help="Original, exact GW_FIX.EXE")
    parser.add_argument("--target", type=Path, help="Caller-supplied GW.CFG; read only")
    parser.add_argument("--candidate-after", type=Path, help="Optional observed updated configuration")
    parser.add_argument("--controls", action="store_true", help="Run authored offline witness controls")
    parser.add_argument("--report", type=Path, help="New JSON report; existing files are never overwritten")
    args = parser.parse_args()
    if args.candidate_after and not args.target:
        parser.error("--candidate-after requires --target")
    patcher = bounded_read(args.patcher, PATCH_SIZE)
    report = {
        "schema": "gw32-fix-offline-witness-1",
        "scope": "Static, target-specific byte witness; no original program execution or native error-equivalence claim",
        "source_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        **inspect_patcher(patcher),
    }
    if args.controls:
        report["controls"] = controls(patcher)
    if args.target:
        target = bounded_read(args.target, MAX_TARGET_BYTES)
        report["target"] = identity(target)
        try:
            output = reconstruct(target, report["records"])
        except ValueError as error:
            report["expected_bytes_match"] = False
            report["reconstruction_error"] = str(error)
            report["candidate_comparison_performed"] = False
        else:
            report["expected_bytes_match"] = True
            report["reconstructed"] = identity(output)
            report["changed_offsets"] = [i for i, (a, b) in enumerate(zip(target, output)) if a != b]
            report["target_length_preserved"] = len(target) == len(output)
            if args.candidate_after:
                candidate = bounded_read(args.candidate_after, MAX_TARGET_BYTES)
                report["candidate_after"] = compare_complete(output, candidate)
                report["candidate_comparison_performed"] = True
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        print(json.dumps({"report": str(args.report), "controls_passed": len(report.get("controls", [])),
                          "expected_bytes_match": report.get("expected_bytes_match")}))
    else:
        print(encoded, end="")
    return 1 if report.get("expected_bytes_match") is False or (
        args.candidate_after and not report.get("candidate_after", {}).get("equal", False)
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
