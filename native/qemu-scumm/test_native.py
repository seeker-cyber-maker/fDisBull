#!/usr/bin/env python3
"""Bounded native QMP checks for the authored early-SCUMM processor contract.

Only Python's standard library is required. All input scripts are authored here;
no game assets, network services, or portable-core oracle are used. Passing this
suite qualifies these QMP behaviors, not an original SCUMM game or full engine.

Example:
    python test_native.py --qemu /build/qemu-system-scumm --output /private/native.json

SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable


READY, BUDGET, RETURN, WAIT, FAULT, BLOCKED = 0, 2, 3, 4, 5, 6
ARCH_FIELDS = (
    "version", "sha256", "size", "pc", "status", "fault", "fault_opcode",
    "retired", "vars", "actor_placement_model", "default_talk_color",
    "actor_metadata",
)


class CheckFailure(RuntimeError):
    """A public behavior differs from the declared authored-pilot contract."""


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise CheckFailure(f"{label}: expected {expected!r}, observed {actual!r}")


def architecture(state: dict[str, Any]) -> dict[str, Any]:
    return {key: state[key] for key in ARCH_FIELDS}


def expect_vars(state: dict[str, Any], values: dict[int, int]) -> None:
    expected = [0] * 256
    for index, value in values.items():
        expected[index] = value
    expect(state["vars"], expected, "all 256 variables")


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {key: state[key] for key in (
        "version", "size", "pc", "status", "fault", "fault_opcode", "retired",
        "run_retired", "eligible", "dropped",
    )}


class QMP:
    """One owned, time-bounded QEMU child and its line-delimited QMP stream."""

    def __init__(self, binary: Path, version: int, code: bytes, timeout: float,
                 *, log_in_asm: bool = False, resource_manifest: Path | None = None):
        self.binary, self.version, self.code = binary, version, code
        self.timeout = timeout
        self.resource_manifest = resource_manifest
        self.temporary = tempfile.TemporaryDirectory(prefix="scumm-native-")
        self.stderr = tempfile.TemporaryFile()
        self.selector = selectors.DefaultSelector()
        self.process: subprocess.Popen[bytes] | None = None
        self.buffer = bytearray()
        self.command_id = 0
        self.cpu_path = ""
        self.events: list[dict[str, Any]] = []
        self.log_path = Path(self.temporary.name) / "in-asm.log" if log_in_asm else None

    def __enter__(self) -> QMP:
        script = Path(self.temporary.name) / "authored.bin"
        script.write_bytes(self.code)
        try:
            machine = f"scumm-test,version={self.version}"
            if self.resource_manifest is not None:
                machine += ",resource-manifest=" + str(self.resource_manifest).replace(",", ",,")
            arguments = [str(self.binary), "-M", machine,
                 "-accel", "tcg,thread=single", "-kernel", str(script), "-S",
                 "-display", "none", "-serial", "none", "-monitor", "none",
                 "-nodefaults", "-no-user-config", "-qmp", "stdio"]
            if self.log_path is not None:
                arguments.extend(["-d", "in_asm", "-D", str(self.log_path)])
            self.process = subprocess.Popen(arguments,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                bufsize=0,
            )
            assert self.process.stdout is not None
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            greeting = self._read(time.monotonic() + self.timeout)
            if "QMP" not in greeting:
                raise CheckFailure(f"QMP greeting missing: {greeting!r}")
            self.command("qmp_capabilities")
            cpus = self.command("query-cpus-fast")
            expect(len(cpus), 1, "single CPU")
            self.cpu_path = cpus[0]["qom-path"]
            initial = self.state()
            expect(initial["version"], self.version, "explicit machine version")
            expect(initial["size"], len(self.code), "raw script byte count")
            expect(initial["sha256"], hashlib.sha256(self.code).hexdigest(),
                   "raw script identity")
            expect(initial["status"], READY, "initial status")
            return self
        except BaseException:
            self.close()
            raise

    def _stderr_text(self) -> str:
        self.stderr.flush()
        self.stderr.seek(0, os.SEEK_END)
        self.stderr.seek(max(0, self.stderr.tell() - 8192))
        return self.stderr.read().decode("utf-8", errors="replace")

    def _read(self, deadline: float) -> dict[str, Any]:
        while True:
            if b"\n" in self.buffer:
                line, _, remaining = self.buffer.partition(b"\n")
                self.buffer = bytearray(remaining)
                if line.strip():
                    result = json.loads(line)
                    if not isinstance(result, dict):
                        raise CheckFailure("QMP emitted a non-object message")
                    return result
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise CheckFailure(f"QMP deadline exceeded; stderr: {self._stderr_text()}")
            ready = self.selector.select(remaining_time)
            if not ready:
                continue
            chunk = os.read(ready[0][0].fd, 65536)
            if not chunk:
                raise CheckFailure(f"QMP closed unexpectedly; stderr: {self._stderr_text()}")
            self.buffer.extend(chunk)
            if len(self.buffer) > 16 * 1024 * 1024:
                raise CheckFailure("QMP message exceeded the 16 MiB harness bound")

    def command(self, name: str, arguments: dict[str, Any] | None = None,
                *, error: bool = False, deadline: float | None = None) -> Any:
        assert self.process is not None and self.process.stdin is not None
        self.command_id += 1
        packet: dict[str, Any] = {"execute": name, "id": self.command_id}
        if arguments is not None:
            packet["arguments"] = arguments
        self.process.stdin.write(json.dumps(packet).encode() + b"\n")
        self.process.stdin.flush()
        limit = deadline if deadline is not None else time.monotonic() + self.timeout
        while True:
            response = self._read(limit)
            if "event" in response:
                self.events.append(response)
                self.events = self.events[-32:]
                continue
            expect(response.get("id"), self.command_id, f"{name} response identity")
            if error:
                if "error" not in response:
                    raise CheckFailure(f"{name} unexpectedly succeeded: {response!r}")
                return response["error"]
            if "error" in response:
                raise CheckFailure(f"{name} rejected: {response['error']!r}")
            if "return" not in response:
                raise CheckFailure(f"{name} has no return field: {response!r}")
            return response["return"]

    def get(self, prop: str) -> Any:
        return self.command("qom-get", {"path": self.cpu_path, "property": prop})

    def set(self, prop: str, value: Any, *, error: bool = False) -> Any:
        return self.command("qom-set", {"path": self.cpu_path, "property": prop,
                                        "value": value}, error=error)

    def state(self) -> dict[str, Any]:
        return json.loads(self.get("scumm-state-json"))

    def decode(self) -> list[dict[str, Any]]:
        return json.loads(self.get("scumm-decode-json"))["records"]

    def trace(self) -> list[dict[str, Any]]:
        return json.loads(self.get("scumm-events-json"))["records"]

    def run(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        self.command("cont", deadline=deadline)
        while True:
            status = self.command("query-status", deadline=deadline)
            if not status["running"]:
                return self.state()
            # A STOP event may arrive before or after the command response.
            # The authoritative stopped check is query-status, under one bound.
            if time.monotonic() >= deadline:
                raise CheckFailure("guest did not stop within its deadline")
            time.sleep(0.005)

    def reset(self) -> dict[str, Any]:
        """Observe the asynchronous system reset and the cleared CPU state."""
        self.events = [event for event in self.events if event.get("event") != "RESET"]
        deadline = time.monotonic() + self.timeout
        self.command("system_reset", deadline=deadline)
        while time.monotonic() < deadline:
            state = self.state()
            if (any(event.get("event") == "RESET" for event in self.events)
                    and (state["status"], state["pc"], state["retired"]) == (READY, 0, 0)):
                return state
            time.sleep(0.005)
        raise CheckFailure("system_reset did not reset the CPU within its deadline")

    def close(self, *, require_clean: bool = False) -> None:
        process = self.process
        cleanup_problem = None
        if process is not None:
            if process.poll() is None:
                try:
                    self.command("quit", deadline=time.monotonic() + 1)
                    process.wait(timeout=1)
                except (OSError, ValueError, CheckFailure, subprocess.TimeoutExpired) as exc:
                    cleanup_problem = f"QEMU needed forced teardown: {type(exc).__name__}: {exc}"
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            if process.returncode != 0 and cleanup_problem is None:
                cleanup_problem = f"QEMU exited with status {process.returncode}: {self._stderr_text()}"
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        self.selector.close()
        self.stderr.close()
        self.temporary.cleanup()
        if require_clean and cleanup_problem is not None:
            raise CheckFailure(cleanup_problem)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close(require_clean=exc_type is None)


def scalar(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    # 250 + 10 - 3 + 1 - 1 = 257. v0 immediates use one byte; v1/v2 use two.
    code = (bytes.fromhex("1a14fa5a140a3a14034614c61400") if version == 0
            else bytes.fromhex("1a14fa005a140a003a1403004614c61400"))
    sizes = [3, 3, 3, 2, 2, 1] if version == 0 else [4, 4, 4, 2, 2, 1]
    with QMP(binary, version, code, timeout) as qmp:
        records = qmp.decode()
        expect([r["size"] for r in records], sizes, "scalar decode sizes")
        expect([r["op"] for r in records],
               ["move", "add", "subtract", "increment", "decrement", "stop"],
               "scalar decode operations")
        expect(records[0]["args"], [[2, 20, 1], [0, 250, 1 if version == 0 else 2]],
               "scalar operand widths")
        qmp.set("scumm-observation-mask", 3)
        qmp.set("scumm-observation-capacity", 4)
        state = qmp.run()
        expect_vars(state, {20: 257})
        expect((state["pc"], state["status"], state["retired"], state["run_retired"]),
               (len(code), RETURN, 6, 6), "scalar result")
        expect(state["eligible"], [6, 0], "scalar observation eligibility")
        expect(state["dropped"], [2, 0], "scalar observation drops")
        before_trace = qmp.trace()
        sticky = qmp.run()
        expect(architecture(sticky), architecture(state), "sticky return architecture")
        expect(sticky["run_retired"], 0, "sticky return run retirements")
        expect(qmp.trace(), before_trace, "sticky return journal")
        qmp.set("scumm-restart", True)
        reset = qmp.state()
        expect_vars(reset, {})
        expect((reset["pc"], reset["status"], reset["retired"], reset["run_retired"]),
               (0, READY, 0, 0), "restart state")
        expect((reset["eligible"], reset["dropped"], qmp.trace()),
               ([0, 0], [0, 0], []), "restart journal counters")
        expect(qmp.get("scumm-observation-mask"), 3, "restart preserves mask")
        expect(qmp.get("scumm-observation-capacity"), 4, "restart preserves capacity")
        expect(architecture(qmp.run()), architecture(state), "restarted scalar result")
        return state_summary(state)


def system_reset(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    code = (bytes([0x1a, 20, 7, 0x00]) if version == 0
            else bytes([0x1a, 20, 7, 0, 0x00]))
    with QMP(binary, version, code, timeout) as qmp:
        qmp.set("scumm-observation-mask", 3)
        qmp.set("scumm-observation-capacity", 8)
        qmp.set("scumm-step-budget", 100)
        initial = qmp.state()
        result = qmp.run()
        expect((result["status"], result["retired"], result["vars"][20]),
               (RETURN, 2, 7), "pre-reset execution")
        reset = qmp.reset()
        expect(architecture(reset), architecture(initial), "system reset architecture")
        expect((reset["eligible"], reset["dropped"], reset["run_retired"]),
               ([0, 0], [0, 0], 0), "system reset observations")
        expect(qmp.trace(), [], "system reset clears journal")
        expect(qmp.get("scumm-observation-mask"), 3, "system reset preserves mask")
        expect(qmp.get("scumm-observation-capacity"), 8, "system reset preserves capacity")
        expect(qmp.get("scumm-step-budget"), 100, "system reset preserves budget")
        expect(architecture(qmp.run()), architecture(result), "execution after system reset")
        return {"reset_event_observed": True, "final": state_summary(result)}


def budget_and_yield(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    with QMP(binary, version, bytes.fromhex("46144614461400"), timeout) as qmp:
        qmp.set("scumm-step-budget", 2)
        qmp.set("scumm-observation-mask", 1)
        first = qmp.run()
        expect_vars(first, {20: 2})
        expect((first["pc"], first["status"], first["retired"], first["run_retired"]),
               (4, BUDGET, 2, 2), "budget boundary")
        second = qmp.run()
        expect_vars(second, {20: 3})
        expect((second["pc"], second["status"], second["retired"], second["run_retired"]),
               (7, RETURN, 4, 2), "budget resume")
        expect([event["pc"] for event in qmp.trace()], [0, 2, 4, 6],
               "budget resume does not repeat retirements")
    code = bytes([0x46, 20, 0x10 if version == 0 else 0x80, 0x46, 20, 0])
    with QMP(binary, version, code, timeout) as qmp:
        first = qmp.run()
        expect_vars(first, {20: 1})
        expect((first["pc"], first["status"], first["retired"], first["run_retired"]),
               (3, WAIT, 2, 2), "yield boundary")
        second = qmp.run()
        expect_vars(second, {20: 2})
        expect((second["pc"], second["status"], second["retired"], second["run_retired"]),
               (6, RETURN, 4, 2), "yield resume")
        return {"budget": "two plus two retirements", "yield": state_summary(second)}


def sticky_fault_and_block(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    results = []
    # Unknown opcode, truncated immediate, and a decoded external effect.
    effect = bytes([0x42, 7]) if version == 0 else bytes([0x0c, 7, 1])
    fixtures = [(b"\x02", FAULT, 1, 0x02),
                (b"\x1a\x15", FAULT, 2, 0x1a),
                (effect + b"\0", BLOCKED, 0, effect[0])]
    if version:
        fixtures.append((b"\x40\0", BLOCKED, 0, 0x40))
    for suffix, status, fault, opcode in fixtures:
        with QMP(binary, version, b"\x46\x14" + suffix, timeout) as qmp:
            qmp.set("scumm-observation-mask", 3)
            state = qmp.run()
            expect_vars(state, {20: 1})
            expect((state["pc"], state["status"], state["fault"], state["fault_opcode"],
                    state["retired"], state["run_retired"]),
                   (2, status, fault, opcode, 1, 1), "non-retiring terminal boundary")
            before = qmp.trace()
            expect(len(before), 1, "fault/blocked instruction has no retirement event")
            sticky = qmp.run()
            expect(architecture(sticky), architecture(state), "sticky terminal architecture")
            expect(sticky["run_retired"], 0, "sticky terminal run retirements")
            expect(qmp.trace(), before, "sticky terminal journal")
            qmp.set("scumm-restart", True)
            expect(architecture(qmp.run()), architecture(state), "restart after terminal state")
            results.append(state_summary(state))
    return {"boundaries": results}


def observations(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    # Three placements, of which the middle one is unchanged, then stop.
    code = bytes.fromhex("01020507010205070102060700")
    baseline = None
    results = []
    for mask, capacity, drops in [(0, 6, [0, 0]), (3, 0, [4, 2]),
                                  (3, 1, [3, 2]), (3, 6, [0, 0])]:
        with QMP(binary, version, code, timeout) as qmp:
            qmp.set("scumm-observation-mask", mask)
            qmp.set("scumm-observation-capacity", capacity)
            state = qmp.run()
            expect_vars(state, {})
            expect((state["pc"], state["status"], state["retired"]),
                   (13, RETURN, 4), "placement completion")
            expect(state["actor_placement_model"],
                   [[k, 1, 6, 7] if k == 2 else [k, 0, 0, 0] for k in range(32)],
                   "placement architecture")
            if baseline is None:
                baseline = architecture(state)
            expect(architecture(state), baseline, "observation-independent architecture")
            expect(state["eligible"], [4, 2] if mask else [0, 0], "eligible events")
            expect(state["dropped"], drops, "drop-new accounting")
            events = qmp.trace()
            expect(len(events), min(capacity, 6) if mask else 0, "bounded journal size")
            if events:
                expect([event["seq"] for event in events], list(range(1, len(events) + 1)),
                       "journal sequence")
            if mask and capacity == 6:
                expect([event["channel"] for event in events], [0, 1, 0, 0, 1, 0],
                       "retirement and changed-scene ordering")
                expect([event["pc"] for event in events], [0, 0, 4, 8, 8, 12],
                       "event source locations")
                expect(events[1]["before"], [0, 0, 0], "initial scene state")
                expect(events[1]["after"], [1, 5, 7], "first scene effect")
                expect(events[4]["after"], [1, 6, 7], "second changed scene effect")
                qmp.set("scumm-observation-capacity", 5, error=True)
                expect(qmp.get("scumm-observation-capacity"), 6, "reject destructive shrink")
            results.append({"mask": mask, "capacity": capacity,
                            "events": len(events), "dropped": state["dropped"]})
    return {"configurations": results}


def long_range(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    # 3-byte header + 255 little-endian words = one 513-byte instruction.
    instruction = b"\xa6\x01\xff" + b"".join(k.to_bytes(2, "little") for k in range(1, 256))
    expect(len(instruction), 513, "authored range fixture length")
    with QMP(binary, version, instruction + b"\0", timeout) as qmp:
        records = qmp.decode()
        expect([(r["pc"], r["size"], r["next"]) for r in records],
               [(0, 513, 513), (513, 1, 514)], "long instruction decode boundaries")
        expect((records[0]["payload_pc"], records[0]["payload_size"], records[0]["subop"]),
               (3, 510, 2), "long range payload")
        qmp.set("scumm-observation-mask", 1)
        state = qmp.run()
        expect(state["vars"], list(range(256)), "all 255 word stores")
        expect((state["pc"], state["status"], state["retired"]),
               (514, RETURN, 2), "long range native execution")
        events = qmp.trace()
        expect(len(events), 2, "long range event count")
        expect(events[0]["bytes"], instruction.hex(), "complete 513-byte event payload")
        expect((events[0]["next"], events[1]["pc"], events[1]["bytes"]),
               (513, 513, "00"), "native TB boundary after long instruction")
    for length in (1, 2, 3, 512):
        with QMP(binary, version, instruction[:length], timeout) as qmp:
            record = qmp.decode()[0]
            expect((record["fault"], record["size"]), (2, 0), "truncated static decode")
            qmp.set("scumm-observation-mask", 3)
            failed = qmp.run()
            expect_vars(failed, {})
            expect((failed["pc"], failed["status"], failed["fault"], failed["retired"]),
                   (0, FAULT, 2, 0), "truncated range is atomic and non-retiring")
            expect(qmp.trace(), [], "truncated range emits no events")
    return {"full": state_summary(state), "rejected_prefix_lengths": [1, 2, 3, 512]}


def decode_and_controls(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    code = b"\x46\x14" * 70 + b"\0"
    with QMP(binary, version, code, timeout) as qmp:
        initial = qmp.state()
        records = qmp.decode()
        expect(len(records), 64, "bounded decode page size")
        expect([r["pc"] for r in records], list(range(0, 128, 2)), "first decode page")
        qmp.set("scumm-decode-pc", 128)
        records = qmp.decode()
        expect([(r["pc"], r["size"]) for r in records],
               [(128, 2), (130, 2), (132, 2), (134, 2), (136, 2), (138, 2), (140, 1)],
               "remaining decode page")
        qmp.set("scumm-decode-pc", len(code))
        expect(qmp.decode(), [], "decode at end")
        for prop, value in [("scumm-observation-mask", 4),
                            ("scumm-observation-capacity", 4097),
                            ("scumm-step-budget", 0),
                            ("scumm-decode-pc", len(code) + 1),
                            ("scumm-restart", False)]:
            qmp.set(prop, value, error=True)
        expect(architecture(qmp.state()), architecture(initial),
               "decode and rejected controls do not execute the guest")
        return {"first_page": 64, "second_page": 7, "invalid_controls_rejected": 5}


def crossing_page(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    # The initial jump targets 4090: PC-after-jump 3 + signed displacement 4087.
    # The 513-byte range then crosses the 4096-byte guest page boundary.
    jump = bytes.fromhex("18f70f")
    instruction = b"\xa6\x01\xff" + b"".join(k.to_bytes(2, "little") for k in range(1, 256))
    code = jump + bytes(4090 - len(jump)) + instruction + b"\0"
    with QMP(binary, version, code, timeout, log_in_asm=True) as qmp:
        qmp.set("scumm-observation-mask", 1)
        qmp.set("scumm-decode-pc", 4090)
        records = qmp.decode()
        expect([(r["pc"], r["size"], r["next"]) for r in records],
               [(4090, 513, 4603), (4603, 1, 4604)], "cross-page static boundaries")
        state = qmp.run()
        expect(state["vars"], list(range(256)), "cross-page word stores")
        expect((state["pc"], state["status"], state["retired"]),
               (4604, RETURN, 3), "cross-page execution")
        expect([event["pc"] for event in qmp.trace()], [0, 4090, 4603],
               "cross-page native retirement locations")
        assert qmp.log_path is not None
        log = qmp.log_path.read_text()
        # Pinned QEMU 10.0.13's generic target disassembly reads via translator_st.
        # Architectural execution alone would miss an unregistered second page.
        if "unable to read memory" in log:
            raise CheckFailure("QEMU in_asm could not read the cross-page instruction:\n" + log)
        encoded = "".join(re.findall(r"^OBJD-T: ([0-9a-f]+)\s*$", log, re.MULTILINE))
        expect(encoded, (jump + instruction + b"\0").hex(),
               "all translated instruction bytes available to QEMU disassembly")
        return {"state": state_summary(state), "instruction_pc": 4090,
                "instruction_size": 513, "native_log_bytes": len(log.encode()),
                "native_log_sha256": hashlib.sha256(log.encode()).hexdigest(),
                "logged_instruction_bytes": len(bytes.fromhex(encoded))}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="deadline for each bounded QMP operation/run (default: 10 seconds)")
    parser.add_argument("--case", action="append", default=[],
                        help="run only this named case; repeat for multiple cases")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than zero and at most 60 seconds")
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / ".git").exists() and args.output.resolve().is_relative_to(source_root):
        parser.error("--output must be outside the source checkout")
    binary = args.qemu.resolve()
    cases: list[tuple[str, Callable[..., dict[str, Any]], int]] = []
    for version in range(3):
        cases.extend([(f"scalar_v{version}", scalar, version),
                      (f"system_reset_v{version}", system_reset, version),
                      (f"budget_yield_v{version}", budget_and_yield, version),
                      (f"sticky_boundaries_v{version}", sticky_fault_and_block, version),
                      (f"observations_v{version}", observations, version),
                      (f"decode_controls_v{version}", decode_and_controls, version)])
        if version:
            cases.append((f"long_range_v{version}", long_range, version))
            cases.append((f"crossing_page_v{version}", crossing_page, version))
    unknown = sorted(set(args.case) - {case[0] for case in cases})
    if unknown:
        parser.error("unknown --case: " + ", ".join(unknown))
    selected = [case for case in cases if not args.case or case[0] in args.case]
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema": "fdisbull-scumm-native-qualification-1",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(), "python": platform.python_version(),
        "qemu": str(binary), "harness_sha256": sha256_file(Path(__file__)),
        "scope": "Authored early-SCUMM native QMP fixtures; independent expected scalar and control results.",
        "unverified": ["Original-game equivalence and gameplay", "Full resource manager and script scheduler",
                       "Rendering, audio, save migration", "Performance and all opcode semantics",
                       "Optional TCG plugins (upstream instruction lengths are limited to 255 bytes)",
                       "Hosted CI and release qualification"],
        "cases": [],
    }
    if not binary.is_file() or not os.access(binary, os.X_OK):
        report.update(result="inconclusive", error="QEMU executable is absent or not executable")
        exit_code = 2
    else:
        report["qemu_sha256"] = sha256_file(binary)
        for name, function, version in selected:
            case_started = time.monotonic()
            result: dict[str, Any] = {"name": name, "version": version}
            try:
                result.update(result="pass", evidence=function(binary, version, args.timeout))
            except Exception as error:
                result.update(result="fail", error=f"{type(error).__name__}: {error}")
            result["seconds"] = round(time.monotonic() - case_started, 3)
            report["cases"].append(result)
            print(json.dumps({"case": name, "result": result["result"],
                              "seconds": result["seconds"], "error": result.get("error")}), flush=True)
        report["passed"] = sum(case["result"] == "pass" for case in report["cases"])
        report["failed"] = len(report["cases"]) - report["passed"]
        report["result"] = "pass" if not report["failed"] else "fail"
        exit_code = 0 if report["result"] == "pass" else 1
        if sha256_file(binary) != report["qemu_sha256"]:
            report.update(result="inconclusive", error="QEMU executable changed during qualification")
            exit_code = 2
    report["seconds"] = round(time.monotonic() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "output": str(args.output.resolve()),
                      "passed": report.get("passed", 0), "failed": report.get("failed", 0)}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
