#!/usr/bin/env python3
"""Independent authored native checks for bounded Amiga-v2 verb state.

The QMP CPU, immutable synthetic bank, and emitted observations are the test
subjects. Expected results are written here from the declared public contract;
the portable interpreter is not used as an oracle. No original game is needed.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import tempfile
import time

from processor_scene import build_scene_packet
from test_native import (BLOCKED, BUDGET, FAULT, READY, RETURN, QMP,
                         architecture, expect, sha256_file)
from test_observation_native import Script, journal, move, scene, expect_accounting, json_property
from test_runtime_native import fixture, runtime


def create(ident, x, y, selector, prep, text=b"", *, variable=False):
    return bytes([0xfa if variable else 0x7a, ident, x, y, selector, prep]) + text + b"\0"


def delete(selector, *, variable=False):
    return bytes([0xfa if variable else 0x7a, 0, selector])


def mode(ident, value):
    return bytes([0x7a, 0xff, ident, value])


def blank(slot):
    result = dict.fromkeys(("id", "x", "y", "hicolor", "dimcolor", "type", "mode",
                           "saveid", "key", "center", "imgindex", "prep"), 0)
    result.update(slot=slot, color=2, charset=1, name={"pc": 0, "size": 0, "bytes": ""})
    return result


def authored(slot, ident, x, y, prep, pc, text):
    result = blank(slot)
    result.update(id=ident, x=x * 8, y=y * 8, hicolor=14, dimcolor=8,
                  charset=0, mode=1, prep=prep,
                  key=ord("qwertasdfgzxcvb"[slot - 1]) if 1 <= slot <= 15 else 0,
                  name={"pc": pc + 6, "size": len(text), "bytes": text.hex()})
    return result


def test_lifecycle(binary, timeout):
    s = Script()
    s.add("selector", move(70, 98))
    s.add("first", create(10, 3, 4, 0, 6, b"Use"))
    escaped = b"A\xff\x04\x00\x00B\xff\x01C"
    s.add("last", create(11, 5, 6, 70, 7, escaped, variable=True))
    s.add("replace", create(12, 7, 8, 0, 2))
    s.add("dim", mode(11, 2))
    s.add("delete", delete(70, variable=True))
    s.add("delete_empty", delete(70, variable=True))
    s.add("missing", mode(250, 7))
    s.add("zero_id", mode(0, 8))
    s.add("stop", b"\0")
    code = bytes(s.code)
    with tempfile.TemporaryDirectory(prefix="scumm-verbs-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            initial = scene(q)
            expect(initial["verbs"], [blank(i) for i in range(100)], "100 reset verb slots")
            q.set("scumm-observation-mask", 3)
            q.set("scumm-step-budget", 1)
            expected = [blank(i) for i in range(100)]
            revision = 0
            for ordinal, name in enumerate(s.pc, 1):
                state = q.run()
                expect((state["status"], state["retired"]),
                       (RETURN if name == "stop" else BUDGET, ordinal), "one verb-step retirement")
                if name == "first":
                    expected[1] = authored(1, 10, 3, 4, 6, s.pc[name], b"Use")
                elif name == "last":
                    expected[99] = authored(99, 11, 5, 6, 7, s.pc[name], escaped)
                elif name == "replace":
                    expected[1] = authored(1, 12, 7, 8, 2, s.pc[name], b"")
                elif name == "dim":
                    expected[99]["mode"] = 2
                elif name in ("delete", "delete_empty"):
                    expected[99].update(id=0, mode=0, saveid=0, name={"pc": 0, "size": 0, "bytes": ""})
                elif name == "missing":
                    expected[0]["mode"] = 7
                elif name == "zero_id":
                    expected[2]["mode"] = 8
                if name not in ("selector", "stop"):
                    revision += 1
                current = scene(q)
                expect(current["verbs"], expected, name + " complete authored slots")
                expect(current["control"]["ui_revision"], revision, name + " UI invalidation")
            final, events = scene(q), journal(q)
            changes = [r for r in events["records"] if r["channel"]]
            expect(len(changes), 8, "exactly one SCENE row per accepted verb operation")
            replay = copy.deepcopy(initial["verbs"])
            for index, row in enumerate(changes):
                expect(row["kind"], "verb", "typed verb record")
                slot = row["before_verb"]["slot"]
                expect(row["before_verb"], replay[slot], "verb before-state continuity")
                expect(row["after_verb"]["slot"], slot, "one selected slot")
                replay[slot] = row["after_verb"]
                expect((row["before_ui_revision"], row["after_ui_revision"]),
                       (index, index + 1), "one redraw request, no rendered-frame claim")
            expect(replay, final["verbs"], "verb observations reach the current snapshot")
            record = next(r for r in changes if r["pc"] == s.pc["last"])
            expect(record["decoded"]["args"], [[0, 11, 1], [1, 70, 1], [0, 7, 1]],
                   "variable-selected create slot is a typed operand")
            expect(record["resolved"], [11, 98, 7], "historical full-width selector")
            q.set("scumm-decode-pc", 0)
            pages = [json_property(q, "scumm-decode-json")]
            expect(pages[0]["stop"], "end", "escaped bytes remain inside their canonical instruction")
            packet = build_scene_packet(code=code, scene=final, events=events, decode_pages=pages)
            expect(packet["verbs"], final["verbs"], "consumer preserves authored verb slots")
            expect(packet["qualification"]["verb_rendering"], False, "headless verb state is not drawing")
            expect_accounting(q, [10, 8], [10, 8], 10)
    return {"retirements": 10, "verb_changes": 8, "escaped_name_bytes": len(escaped),
            "reserved_slot_mode": 7, "absent_and_empty_distinguished": True}


def test_selection(binary, timeout):
    s = Script()
    # Read-indirection selectors 14, 15 and 16 contain the variable indices.
    for index, value in ((14, 80), (15, 81), (16, 82), (80, 0), (81, 14), (82, 98)):
        s.add("seed_" + str(index), move(index, value))
    for name, selector in (("first", 14), ("fifteenth", 15), ("last", 16)):
        s.add(name, create(20, 1, 2, selector, 4, b"Same", variable=True))
    s.add("mode_first", mode(20, 255))
    s.add("delete_first", delete(14, variable=True))
    s.add("mode_next", mode(20, 2))
    s.add("stop", b"\0")
    code = bytes(s.code)
    with tempfile.TemporaryDirectory(prefix="scumm-verb-selection-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            q.set("scumm-observation-mask", 3)
            state = q.run()
            expect((state["status"], state["retired"]), (RETURN, 13), "indirect selector program")
            verbs = scene(q)["verbs"]
            expect((verbs[1]["id"], verbs[1]["mode"], verbs[1]["key"]), (0, 0, ord("q")),
                   "deletion retains keyboard metadata")
            expect((verbs[15]["mode"], verbs[15]["key"], verbs[99]["mode"], verbs[99]["key"]),
                   (2, ord("b"), 1, 0), "lowest duplicate slot and slot-specific keys")
            rows = {r["pc"]: r for r in journal(q)["records"] if r["channel"]}
            expect([rows[s.pc[name]]["resolved"][1] for name in ("first", "fifteenth", "last")],
                   [0, 14, 98], "v2 read indirection resolves the actual selector values")
            expect(rows[s.pc["mode_first"]]["after_verb"]["mode"], 255, "full mode byte is retained")
    return {"indirect_selectors": [14, 15, 16], "duplicate_ids_choose_lowest": True}


def test_masks(binary, timeout):
    code = (create(4, 2, 3, 0, 1, b"Verb") + mode(4, 2) + delete(0)
            + delete(0) + mode(77, 255) + b"\0")
    baseline = None
    with tempfile.TemporaryDirectory(prefix="scumm-verb-masks-") as temporary:
        manifest = fixture(Path(temporary), code)
        for mask in range(4):
            for capacity in (0, 1, 64):
                with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
                    q.set("scumm-observation-mask", mask)
                    q.set("scumm-observation-capacity", capacity)
                    state = q.run()
                    expect((state["status"], state["retired"]), (RETURN, 6), "all-mask verb execution")
                    current = scene(q)
                    observed = (architecture(state), runtime(q), current["verbs"], current["control"])
                    if baseline is None:
                        baseline = observed
                    expect(observed, baseline, "observations cannot change authored verb execution")
                    eligible = [6 if mask & 1 else 0, 5 if mask & 2 else 0]
                    order = [c for i in range(6) for c in (0, 1)
                             if mask & (1 << c) and (c == 0 or i < 5)]
                    stored = [order[:capacity].count(c) for c in (0, 1)]
                    expect_accounting(q, eligible, stored, 6 if mask & 1 else 5 if mask & 2 else 0)
                    before = copy.deepcopy(current)
                    expect(scene(q), before, "verb getter is pure")
                    q.set("scumm-observation-clear", True)
                    expect(scene(q)["verbs"], current["verbs"], "clear keeps verb state")
                    expect(scene(q)["control"], current["control"], "clear keeps UI revision")
    return {"mask_capacity_pairs": 12, "full_runtime_and_verbs_invariant": True}


def test_atomic_rejection(binary, timeout):
    cases = [
        ("delete_slot_100", b"", delete(99), 9),
        ("create_slot_100", b"", create(1, 2, 3, 99, 0, b"No"), 9),
        ("wide_variable", move(70, 65535), delete(70, variable=True), 9),
        ("wide_variable_create", move(70, 256), create(1, 2, 3, 70, 0, b"No", variable=True), 9),
        ("escape_without_command", b"", create(1, 2, 3, 0, 0, b"X")[:-2] + b"\xff", 2),
        ("escape_short_argument", b"", create(1, 2, 3, 0, 0, b"X")[:-2] + b"\xff\x04\0", 2),
        ("missing_terminator", b"", create(1, 2, 3, 0, 0, b"X")[:-1], 2),
        ("instruction_over_bound", b"", create(1, 2, 3, 0, 0, b"A" * 508), 2),
    ]
    for label, prefix, invalid, fault in cases:
        # A prior committed verb proves failure does not erase or partly replace it.
        initial = create(5, 4, 3, 0, 2, b"Prior")
        code = initial + prefix + invalid
        with tempfile.TemporaryDirectory(prefix="scumm-verb-reject-") as temporary:
            manifest = fixture(Path(temporary), code)
            with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
                q.set("scumm-observation-mask", 3)
                q.set("scumm-step-budget", 1 + bool(prefix))
                expect(q.run()["status"], BUDGET, label + " accepted prefix")
                before, snapshot, trace, current_runtime = q.state(), scene(q), journal(q), runtime(q)
                after = q.run()
                expect((after["status"], after["fault"]), (FAULT, fault), label)
                for key in ("pc", "retired", "vars", "actor_metadata", "actor_placement_model"):
                    expect(after[key], before[key], label + " no partial " + key)
                expect(scene(q)["verbs"], snapshot["verbs"], label + " no partial verb")
                expect(runtime(q), current_runtime, label + " no partial runtime")
                expect(journal(q), trace, label + " no retirement or scene record")
                expect(architecture(q.run()), architecture(after), label + " sticky fault")
    return {"atomic_failures": len(cases)}


def test_extent_and_queries(binary, timeout):
    target = 4093
    long_verb = create(25, 255, 255, 98, 255, b"A" * 507)
    expect(len(long_verb), 514, "authored maximum instruction extent")
    code = b"\x18" + (target - 3).to_bytes(2, "little") + b"\0" * (target - 3) + long_verb + b"\0"
    with tempfile.TemporaryDirectory(prefix="scumm-verb-extent-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            before = q.state(), runtime(q), scene(q)
            q.set("scumm-decode-pc", target)
            q.set("scumm-decode-limit", 1)
            decoded = json_property(q, "scumm-decode-json")
            expect((decoded["records"][0]["size"], decoded["next_pc"]), (514, target + 514),
                   "native canonical decode crosses the code-page boundary")
            expect((q.state(), runtime(q), scene(q)), before, "static verb queries are neutral")
            q.set("scumm-observation-mask", 3)
            result = q.run()
            expect((result["status"], result["retired"]), (RETURN, 3), "cross-page verb retires once")
            slot = scene(q)["verbs"][99]
            expect((slot["x"], slot["y"], slot["prep"], slot["name"]["size"]),
                   (2040, 2040, 255, 507), "maximum authored coordinates/name")
            row = next(r for r in journal(q)["records"] if r["kind"] == "verb")
            expect(row["bytes"], long_verb.hex(), "full 514-byte observation")
    return {"instruction_bytes": 514, "cross_page_start": target, "static_reads_neutral": True}


def test_profile_and_reset(binary, timeout):
    code = create(5, 1, 2, 0, 0, b"Run") + b"\0"
    for version in (1, 2):
        with QMP(binary, version, code, timeout) as q:
            q.set("scumm-observation-mask", 3)
            before = scene(q)
            after = q.run()
            expect((after["status"], after["pc"], after["retired"]), (BLOCKED, 0, 0),
                   "verbs require the explicit v2 runtime profile")
            expect(scene(q)["verbs"], before["verbs"], "raw profile leaves verb state untouched")
            expect(journal(q)["records"], [], "blocked operation has no observations")
    with tempfile.TemporaryDirectory(prefix="scumm-verb-reset-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as q:
            initial = scene(q)
            q.set("scumm-observation-mask", 3)
            q.run()
            q.set("scumm-observation-clear", True)
            expect(scene(q)["verbs"][1]["id"], 5, "journal clear preserves verb")
            q.set("scumm-restart", True)
            expect(scene(q)["verbs"], initial["verbs"], "restart restores reset defaults")
            expect(scene(q)["control"], initial["control"], "restart clears UI invalidation")
            expect(q.state()["status"], READY, "restart status")
            q.run()
            q.reset()
            expect(scene(q)["verbs"], initial["verbs"], "system reset restores reset defaults")
            expect(scene(q)["source"], initial["source"], "reset keeps admitted immutable source")
    return {"raw_profiles_blocked": [1, 2], "clear_restart_system_reset": True}


def cases():
    return {"verb_lifecycle": test_lifecycle, "verb_selection": test_selection,
            "verb_masks": test_masks, "verb_atomic_rejection": test_atomic_rejection,
            "verb_extent_and_queries": test_extent_and_queries,
            "verb_profile_and_reset": test_profile_and_reset}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--case", choices=cases(), action="append")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than zero and at most 60 seconds")
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists() and args.output.resolve().is_relative_to(root):
        parser.error("--output must be outside the source checkout")
    if args.output.exists():
        parser.error("--output must name a new evidence file")
    binary = args.qemu.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("--qemu must be an executable file")
    digest = sha256_file(binary)
    report = {"schema": "fdisbull-scumm-verb-qualification-1",
              "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "qemu": str(binary), "qemu_sha256": digest,
              "harness_sha256": sha256_file(Path(__file__)),
              "scope": "Native authored v2 verb state and DISASM/SCENE observations",
              "unverified": ["Original-game equivalence", "Text rendering and hit testing",
                             "Script scheduling and room transitions", "Hosted CI"], "cases": []}
    for name in args.case or cases():
        started = time.monotonic()
        record = {"case": name}
        try:
            record.update(result="pass", evidence=cases()[name](binary, args.timeout))
        except Exception as error:
            record.update(result="fail", error=f"{type(error).__name__}: {error}")
        record["seconds"] = round(time.monotonic() - started, 3)
        report["cases"].append(record)
        print(json.dumps({key: value for key, value in record.items() if key != "evidence"}), flush=True)
    report["passed"] = sum(r["result"] == "pass" for r in report["cases"])
    report["failed"] = len(report["cases"]) - report["passed"]
    report["result"] = "fail" if report["failed"] else "pass"
    if sha256_file(binary) != digest:
        report.update(result="inconclusive", error="Native executable changed during qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("result", "passed", "failed")}))
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
