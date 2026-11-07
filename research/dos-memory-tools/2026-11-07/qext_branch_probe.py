#!/usr/bin/env python3
"""Reproduce the bounded QEXT.SYS branch comparison from caller-owned files.

Usage:
    python qext_branch_probe.py BEFORE_QEXT AFTER_QEXT NEW_REPORT_JSON

Requires Unicorn (the recorded run used 2.1.4). This script embeds no original
program bytes. It accepts only the two exact source hashes named below and
loads their supplied bytes into isolated emulated memory.

Scope: execute the original MOV/CALL/JE slice beginning at 1000:0FD3 with an
authored input byte and DF=0. Stop BEFORE executing either destination of the
JE at 1000:0FDA. Check that branch outcome and selected register preservation.
This is not a DOS installation, a native QEMM run, an observation of the full
caller, or a claim of complete architectural-state equivalence.

The disassembly addresses were discovered by ordinary fDisBull SYS traversal;
no authored static entry seed was required. Selecting this bounded emulation
start and its register/memory context is an authored experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


EXPECTED_SOURCES = {
    "dv242": "5231ee7940cdd7d0328e4164208cc8aec04cd3f2cac54524a81b8eb03a7d8c2c",
    "dv280": "2026d600b2683ef843e62cdc613ff2c3893ad838a67faa81592c12d8e83e94c3",
}
EXPECTED_SOURCE_SIZE = 5853

# Fixed observed address profile, in a deliberately chosen real-mode segment.
LOAD_BASE = 0x10000
START_OFFSET = 0x0FD3
FALLTHROUGH_OFFSET = 0x0FDC
TAKEN_OFFSET = 0x0FFA
INPUT_OFFSET = 0x7000
INSTRUCTION_BUDGET = 128

# Semantic truth-table oracle, expressed as character codes rather than a
# copied instruction or data payload. The old predicate accepts three extra
# punctuation characters; the new predicate accepts the common set only.
COMMON_SEPARATOR_CODES = {0, 9, 10, 13, 32, 44, 47, 59}
ADDITIONAL_OLD_CODES = {45, 58, 61}  # hyphen, colon, equals sign


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_source(path: Path, tag: str) -> tuple[Path, bytes]:
    """Read an immutable source identity; never edit or synthesize input."""
    path = path.resolve(strict=True)
    require(path.is_file(), f"{tag}: expected a regular source file")
    require(path.stat().st_size == EXPECTED_SOURCE_SIZE,
            f"{tag}: expected exactly {EXPECTED_SOURCE_SIZE} source bytes")
    data = path.read_bytes()
    require(len(data) == EXPECTED_SOURCE_SIZE,
            f"{tag}: source size changed during its read")
    digest = hashlib.sha256(data).hexdigest()
    require(digest == EXPECTED_SOURCES[tag],
            f"{tag}: source SHA256 does not match the fixed QEXT profile: {digest}")
    return path, data


def probe_source(tag: str, path: Path, data: bytes) -> dict:
    import unicorn
    from unicorn.x86_const import (
        UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CS, UC_X86_REG_CX,
        UC_X86_REG_DI, UC_X86_REG_DS, UC_X86_REG_DX, UC_X86_REG_EFLAGS,
        UC_X86_REG_ES, UC_X86_REG_IP, UC_X86_REG_SI, UC_X86_REG_SP,
        UC_X86_REG_SS,
    )

    machine = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_16)
    machine.mem_map(0, 0x50000)
    machine.mem_write(LOAD_BASE, data)
    observed = {"stop": None, "count": 0}
    stop_addresses = {
        LOAD_BASE + FALLTHROUGH_OFFSET,
        LOAD_BASE + TAKEN_OFFSET,
    }

    def on_code(uc, address, size, user_data):
        # The final hook event is counted, but that destination instruction
        # has not executed when emu_stop() is called.
        observed["count"] += 1
        if address in stop_addresses:
            observed["stop"] = address
            uc.emu_stop()

    machine.hook_add(unicorn.UC_HOOK_CODE, on_code)

    cases = []
    for character in range(256):
        observed.update(stop=None, count=0)

        # These are experiment inputs, not claimed observations of DOS state.
        # Reusing one isolated machine per source is safe for this slice:
        # every register/input it consumes is reset; stack scratch is written
        # before being read. No other program or DOS service is executed.
        initial_registers = [
            (UC_X86_REG_CS, 0x1000),
            (UC_X86_REG_DS, 0x2000),
            (UC_X86_REG_ES, 0x1000),
            (UC_X86_REG_SS, 0x3000),
            (UC_X86_REG_SP, 0xFF00),
            (UC_X86_REG_AX, 0xA500),
            (UC_X86_REG_BX, 0x5678),
            (UC_X86_REG_CX, 0x1234),
            (UC_X86_REG_DX, 0x9876),
            (UC_X86_REG_SI, 0x4567),
            (UC_X86_REG_DI, INPUT_OFFSET + 1),
            (UC_X86_REG_EFLAGS, 2),  # DF=0; reserved bit 1 set
        ]
        for register, value in initial_registers:
            machine.reg_write(register, value)

        # The existing MOV at START_OFFSET reads this byte through ES:DI-1.
        # This modifies only emulated scratch, never the caller's input file.
        machine.mem_write(LOAD_BASE + INPUT_OFFSET, bytes([character]))
        machine.emu_start(
            LOAD_BASE + START_OFFSET,
            LOAD_BASE + len(data),
            count=INSTRUCTION_BUDGET,
        )
        require(
            observed["stop"] in stop_addresses,
            f"{tag}, character {character}: no declared edge reached within "
            f"the instruction budget (IP={machine.reg_read(UC_X86_REG_IP):04x})",
        )

        preserved = [
            (UC_X86_REG_CX, 0x1234, "CX"),
            (UC_X86_REG_DI, INPUT_OFFSET + 1, "DI"),
            (UC_X86_REG_ES, 0x1000, "ES"),
            (UC_X86_REG_SP, 0xFF00, "SP"),
            (UC_X86_REG_AX, 0xA500 + character, "AX after input load"),
        ]
        for register, expected, label in preserved:
            require(
                machine.reg_read(register) == expected,
                f"{tag}, character {character}: unexpected {label}",
            )

        cases.append({
            "character": character,
            "stop_address": hex(observed["stop"]),
            "je_taken": observed["stop"] == LOAD_BASE + TAKEN_OFFSET,
            "instruction_hook_events": observed["count"],
            "flags": machine.reg_read(UC_X86_REG_EFLAGS),
        })

    return {
        "tag": tag,
        "path": str(path),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "cases": cases,
    }


def run(before: Path, after: Path) -> dict:
    import unicorn

    inputs = {
        "dv242": read_source(before, "dv242"),
        "dv280": read_source(after, "dv280"),
    }
    rows = [
        probe_source(tag, path, data)
        for tag, (path, data) in inputs.items()
    ]
    states = {row["tag"]: row["cases"] for row in rows}
    old_cases, new_cases = states["dv242"], states["dv280"]

    branch_changes = [
        old["character"]
        for old, new in zip(old_cases, new_cases)
        if old["je_taken"] != new["je_taken"]
    ]
    flags_changes = [
        old["character"]
        for old, new in zip(old_cases, new_cases)
        if old["flags"] != new["flags"]
    ]

    old_oracle = COMMON_SEPARATOR_CODES | ADDITIONAL_OLD_CODES
    require(
        all(case["je_taken"] == (case["character"] in old_oracle)
            for case in old_cases),
        "before: observed JE truth table differs from the declared oracle",
    )
    require(
        all(case["je_taken"] == (case["character"] in COMMON_SEPARATOR_CODES)
            for case in new_cases),
        "after: observed JE truth table differs from the declared oracle",
    )
    require(branch_changes == sorted(ADDITIONAL_OLD_CODES),
            "branch differences do not match the three punctuation cases")

    # This is intentionally recorded separately from branch equality.
    # Comparing only ZF/JE must not be promoted to whole-state equivalence.
    require(len(flags_changes) == 231,
            "arithmetic-flag differences do not reproduce the recorded profile")

    return {
        "schema": "qext-paired-branch-probe-1",
        "producer": {
            "script": Path(__file__).name,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "engine": "Unicorn",
        "engine_version": unicorn.__version__,
        "execution": (
            "original bytes in an authored isolated real-mode context; "
            "not DOS installation/native QEMM qualification"
        ),
        "sources": [
            {key: value for key, value in row.items() if key != "cases"}
            for row in rows
        ],
        "context": {
            "CS": "0x1000", "DS": "0x2000", "ES": "0x1000",
            "SS": "0x3000", "SP": "0xff00", "DF": 0,
            "IP_start": "0xfd3", "char_buffer": "1000:7000",
            "DI": "0x7001", "CX": "0x1234", "AX_before": "0xa500",
            "BX": "0x5678", "DX": "0x9876", "SI": "0x4567",
            "initial_EFLAGS": "0x0002",
            "mapped_linear_range": ["0x00000", "0x50000"],
            "instruction_budget": INSTRUCTION_BUDGET,
            "stop_before_offsets": ["0xfdc", "0xffa"],
        },
        "case_count": 512,
        "complete": True,
        "authored_analysis_seeds": False,
        "authored_execution_context": True,
        "branch_changes": branch_changes,
        "branch_change_characters": [chr(value) for value in branch_changes],
        "flags_change_count": len(flags_changes),
        "max_instruction_hook_events": max(
            case["instruction_hook_events"]
            for row in rows for case in row["cases"]
        ),
        "scope": (
            "JE at 1000:0FDA and CX/DI/ES/SP/AX preservation only; "
            "other flags and whole driver behavior are not declared equivalent"
        ),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path,
                        help="QEXT.SYS from the supplied DESQview 386 2.42 media")
    parser.add_argument("after", type=Path,
                        help="QEXT.SYS from the supplied DESQview 2.80 media")
    parser.add_argument("output", type=Path,
                        help="new JSON receipt path; existing files are refused")
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists; choose a new receipt path")
    require(args.output.parent.is_dir(), "output parent must already exist")

    report = run(args.before, args.after)
    # Exclusive creation prevents overwriting inputs or an earlier receipt.
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({
        "complete": report["complete"],
        "case_count": report["case_count"],
        "branch_change_characters": report["branch_change_characters"],
        "flags_change_count": report["flags_change_count"],
        "max_instruction_hook_events": report["max_instruction_hook_events"],
        "report": str(args.output.resolve()),
    }))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"QEXT probe failed: {error}", file=sys.stderr)
        raise SystemExit(1)
