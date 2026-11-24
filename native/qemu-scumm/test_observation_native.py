#!/usr/bin/env python3
"""Authored QMP acceptance checks for SCUMM DISASM and SCENE observations.

The fixtures below are independently authored instruction streams and opaque
resource containers. They exercise the public stopped-CPU interfaces and native
TCG output; no original game payload or portable interpreter is used as an
oracle. Passing these checks does not qualify rendering or a complete engine.

SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Callable

from test_native import (BLOCKED, BUDGET, FAULT, READY, RETURN, WAIT,
                         CheckFailure, QMP, architecture, expect, sha256_file)
from test_runtime_native import digest, fixture, resource, runtime


class Script:
    """Record authored instruction boundaries without consulting the decoder."""

    def __init__(self) -> None:
        self.code = bytearray()
        self.pc: dict[str, int] = {}
        self.bytes: dict[str, bytes] = {}

    def add(self, name: str, instruction: bytes) -> None:
        if name in self.pc:
            raise ValueError(f"duplicate authored instruction {name}")
        self.pc[name] = len(self.code)
        self.bytes[name] = instruction
        self.code.extend(instruction)


def move(index: int, value: int, version: int = 2) -> bytes:
    return bytes([0x1a, index]) + value.to_bytes(2 if version else 1, "little")


def json_property(qmp: QMP, name: str) -> dict[str, Any]:
    return json.loads(qmp.get(name))


def journal(qmp: QMP) -> dict[str, Any]:
    result = json_property(qmp, "scumm-events-json")
    expect(result["schema"], "fdisbull-scumm-events-2", "event schema")
    return result


def scene(qmp: QMP) -> dict[str, Any]:
    result = json_property(qmp, "scumm-scene-json")
    expect(result["schema"], "fdisbull-scumm-scene-1", "scene snapshot schema")
    return result


def source_identity(source: dict[str, Any], version: int, code: bytes,
                    manifest: Path | None = None) -> None:
    expected = {"version": version, "code_sha256": digest(code),
                "code_size": len(code), "profile": "none",
                "manifest_sha256": "", "source_receipt_sha256": "", "script_id": 0}
    if manifest is not None:
        data = json.loads(manifest.read_text())
        expected.update(profile="amiga-v2-isolated",
                        manifest_sha256=digest(manifest.read_bytes()),
                        source_receipt_sha256=data["source_receipt_sha256"],
                        script_id=data["script_id"])
    expect(source, expected, "complete immutable source identity")


def expect_accounting(qmp: QMP, eligible: list[int], stored: list[int],
                      helper_calls: int) -> None:
    state = qmp.state()
    drops = [eligible[k] - stored[k] for k in range(2)]
    expected = {"mask": qmp.get("scumm-observation-mask"),
                "capacity": qmp.get("scumm-observation-capacity"),
                "count": sum(stored), "sequence": sum(eligible),
                "eligible": eligible, "stored": stored, "dropped": drops,
                "helper_calls": helper_calls}
    expect({key: state[key] for key in expected}, expected, "state journal accounting")
    events, snapshot = journal(qmp), scene(qmp)
    expect(events["observation"], expected, "event response accounting")
    expect(snapshot["observation"], expected, "scene response accounting")
    expect((events["epoch"], events["control_generation"]),
           (state["epoch"], state["control_generation"]), "event response identity")
    checkpoint = snapshot["checkpoint"]
    expect((checkpoint["trace_epoch"], checkpoint["control_generation"]),
           (state["epoch"], state["control_generation"]), "scene checkpoint identity")
    for key in ("pc", "status", "fault", "fault_opcode", "retired"):
        expect(checkpoint[key], state[key], "coherent scene checkpoint " + key)


def actor_events(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    authored = Script()
    authored.add("place", bytes([0x01, 2, 5, 6]))
    authored.add("costume", bytes([0x13, 2, 4, 4]))
    authored.add("sound", bytes([0x13, 2, 9, 1]))
    authored.add("talk", bytes([0x13, 2, 6, 5]))
    palette = bytes([0x13, 2, 7, 2]) + (b"\x01" if version == 2 else b"")
    authored.add("palette", palette)
    authored.add("same_palette", palette)
    name = b'N\x80"\\'
    authored.add("name", bytes([0x13, 2, 0, 3]) + name + b"\0")
    authored.add("default_color", bytes([0x13, 0, 9, 5]))
    authored.add("same_color", bytes([0x13, 0, 9, 5]))
    authored.add("stop", b"\0")
    code = bytes(authored.code)
    changed = {"place", "costume", "sound", "talk", "palette", "name", "default_color"}
    with QMP(binary, version, code, timeout) as qmp:
        initial = scene(qmp)
        qmp.set("scumm-observation-mask", 3)
        state = qmp.run()
        expect((state["status"], state["retired"]), (RETURN, 10), "actor fixture retirement")
        snapshot, events = scene(qmp), journal(qmp)
        source_identity(snapshot["source"], version, code)
        expect(events["source"], snapshot["source"], "event and scene source binding")
        expected_order = []
        for ordinal, (name_, pc) in enumerate(authored.pc.items(), 1):
            expected_order.append((0, pc, ordinal))
            if name_ in changed:
                expected_order.append((1, pc, ordinal))
        expect([(r["channel"], r["pc"], r["retired"]) for r in events["records"]],
               expected_order, "retirement precedes its committed scene change")
        replay = copy.deepcopy(initial["actors"])
        color = initial["control"]["default_talk_color"]
        scenes = {r["pc"]: r for r in events["records"] if r["channel"] == 1}
        for record in events["records"]:
            expect(record["bytes"], code[record["pc"]:record["pc"] + record["size"]].hex(),
                   "byte-exact actor event extent")
            expect(record["control_generation"], state["control_generation"],
                   "actor event control generation")
            if record["channel"] == 0:
                expect(record["kind"], "retire", "DISASM record kind")
            elif record["kind"] == "actor":
                actor = record["actor"]
                expect(record["before_actor"], replay[actor], "actor delta continuity")
                replay[actor] = record["after_actor"]
            else:
                expect(record["kind"], "default_talk_color", "global presentation effect kind")
                expect(record["before_color"], color, "global color delta continuity")
                color = record["after_color"]
        expect(snapshot["actors"], replay, "SCENE actor replay reaches authoritative snapshot")
        expect(snapshot["control"]["default_talk_color"], color, "global color replay")
        palette_record = scenes[authored.pc["palette"]]
        slot = 1 if version == 2 else 2
        expected_palette: list[int | None] = [None] * 32
        expected_palette[slot] = 7
        expect(palette_record["before_actor"]["palette"], [None] * 32, "unknown palette slots")
        expect(palette_record["after_actor"]["palette"], expected_palette, "palette-only delta")
        expect(palette_record["before"], palette_record["after"],
               "palette changes need facts beyond legacy placement arrays")
        expect(palette_record["resolved"], [2, 7, 2], "actor resolved arguments")
        name_record = scenes[authored.pc["name"]]
        expect(name_record["after_actor"]["name"],
               {"pc": authored.pc["name"] + 4, "size": len(name), "bytes": name.hex()},
               "source-bound name bytes without encoding or terminator changes")
        actor = snapshot["actors"][2]
        expect({key: actor[key] for key in ("id", "bound", "x", "y", "room",
                                           "costume", "sound", "talk_color")},
               {"id": 2, "bound": 1, "x": 5, "y": 6, "room": 0,
                "costume": 4, "sound": 9, "talk_color": 6}, "complete committed actor facts")
        expect(state["actor_metadata"][2]["room"], 0, "additive legacy actor room")
        expect_accounting(qmp, [10, 7], [10, 7], 10)
        return {"retirements": 10, "scene_changes": 7, "palette_slot": slot,
                "actor_replay": True, "source_bound_name_bytes": len(name)}


def runtime_events(binary: Path, timeout: float) -> dict[str, Any]:
    authored = Script()
    authored.add("seed", move(38, 9))
    authored.add("load", bytes([0x0c, 2, 0x21]))
    authored.add("lock", bytes([0x0c, 2, 0x23]))
    authored.add("same_lock", bytes([0x0c, 2, 0x23]))
    authored.add("unlock", bytes([0x0c, 2, 0x22]))
    authored.add("cursor", bytes([0x60, 7, 0xf6]))
    authored.add("cutscene", b"\x40")
    authored.add("stop", b"\0")
    code = bytes(authored.code)
    with tempfile.TemporaryDirectory(prefix="scumm-observation-bank-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as qmp:
            initial = scene(qmp)
            qmp.set("scumm-observation-mask", 3)
            state = qmp.run()
            snapshot, current = scene(qmp), runtime(qmp)
            source_identity(snapshot["source"], 2, code, manifest)
            records = journal(qmp)["records"]
            scenes = [record for record in records if record["channel"] == 1]
            expect([(record["kind"], record["pc"]) for record in scenes],
                   [("resource", authored.pc[name]) for name in ("load", "lock", "unlock")]
                   + [("control", authored.pc[name]) for name in ("cursor", "cutscene")],
                   "typed committed resource and control changes")
            original = resource({"resources": initial["resources"]["entries"]}, "costume", 2)
            assert original is not None
            previous = {key: value for key, value in original.items() if key not in ("type", "id")}
            expected_flags = [(True, False), (True, True), (True, False)]
            for record, flags in zip(scenes[:3], expected_flags):
                expect((record["type"], record["id"]), ("costume", 2), "resource effect identity")
                expect(record["before_resource"], previous, "resource delta continuity")
                after = record["after_resource"]
                expect((after["resident"], after["locked"]), flags, "logical resource transition")
                expect((after["available"], after["size"], after["sha256"]),
                       (True, original["size"], original["sha256"]), "immutable verified resource identity")
                previous = after
            final_resource = resource(current, "costume", 2)
            assert final_resource is not None
            expect(previous, {key: value for key, value in final_resource.items()
                              if key not in ("type", "id")}, "resource replay reaches runtime snapshot")
            cursor, cutscene = scenes[3:]
            expect(cursor["before_control"]["vars"],
                   {"21": 0, "26": 0, "27": 0, "28": 0, "29": 0, "38": 9},
                   "control observation consumes current variables")
            expect(cursor["after_control"]["vars"]["21"], 7, "cursor commits selected cursor")
            expect([cursor["after_control"][key] for key in
                    ("user_state", "user_put", "cursor_visible", "ui_revision")],
                   [0xe0, 1, 1, 1], "cursor commits UI state")
            expect(cutscene["before_control"], cursor["after_control"], "control delta continuity")
            expect([cutscene["after_control"][key] for key in
                    ("cutscene_active", "saved_user_state", "saved_cursor", "ui_revision")],
                   [1, 0xf0, 7, 2], "cutscene commits saved controls")
            expect(cutscene["after_control"]["vars"],
                   {"21": 200, "26": 9, "27": 0, "28": 0, "29": 0, "38": 9},
                   "cutscene captures committed variable effects")
            expect({key: cutscene["after_control"][key] for key in current["control"]},
                   current["control"], "control event reaches runtime snapshot")
            expect(snapshot["resources"], {"counts": current["counts"], "entries": current["resources"]},
                   "coherent resource scene snapshot")
            expect({key: snapshot["control"][key] for key in cutscene["after_control"]},
                   cutscene["after_control"], "coherent control scene snapshot")
            expect((state["status"], state["retired"]), (RETURN, 8), "runtime observation retirement")
            expect_accounting(qmp, [8, 5], [8, 5], 8)
    return {"resource_changes": 3, "control_changes": 2, "unchanged_lock_omitted": True}


def masks_and_capacity(binary: Path, timeout: float) -> dict[str, Any]:
    # Eight retirements; six change scene facts. Only the scalar seed and stop
    # have no potential scene effect. Expectations are independent of decoding.
    code = (move(38, 9) + bytes([0x01, 2, 5, 6, 0x13, 0, 9, 5,
            0x0c, 2, 0x21, 0x0c, 2, 0x23, 0x60, 7, 0xf6, 0x40, 0]))
    has_scene = [False, True, True, True, True, True, True, False]
    baseline = None
    results = []
    with tempfile.TemporaryDirectory(prefix="scumm-observation-masks-") as temporary:
        manifest = fixture(Path(temporary), code)
        for mask in range(4):
            for capacity in (0, 1, 64):
                with QMP(binary, 2, code, timeout, resource_manifest=manifest) as qmp:
                    qmp.set("scumm-observation-mask", mask)
                    qmp.set("scumm-observation-capacity", capacity)
                    state = qmp.run()
                    observed = (architecture(state), runtime(qmp))
                    if baseline is None:
                        baseline = observed
                    expect(observed, baseline, "mask/capacity independent full execution state")
                    expect((state["status"], state["retired"]), (RETURN, 8), "all-mask completion")
                    channels = []
                    for changed in has_scene:
                        if mask & 1:
                            channels.append(0)
                        if mask & 2 and changed:
                            channels.append(1)
                    retained = channels[:capacity]
                    eligible = [8 if mask & 1 else 0, 6 if mask & 2 else 0]
                    stored = [retained.count(0), retained.count(1)]
                    calls = 8 if mask & 1 else 6 if mask & 2 else 0
                    expect_accounting(qmp, eligible, stored, calls)
                    records = journal(qmp)["records"]
                    expect([record["channel"] for record in records], retained, "shared drop-new prefix")
                    expect([record["seq"] for record in records], list(range(1, len(retained) + 1)),
                           "fresh journal retained sequence")
                    if mask == 2:
                        expect([record["destination"] for record in records], [None] * len(records),
                               "SCENE-only mode avoids DISASM destination capture")
                    results.append({"mask": mask, "capacity": capacity,
                                    "eligible": eligible, "stored": stored, "helper_calls": calls})
    return {"configurations": results, "architecture_and_runtime_equal": True}


def resolved_operands(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    authored = Script()
    for index, value in ((40, 7), (41, 9), (42, 11), (14, 40), (15, 41), (16, 42)):
        authored.add(f"seed_{index}", move(index, value, version))
    authored.add("read14", bytes([0x9a, 50, 14]))
    authored.add("read15", bytes([0xda, 50, 15]))
    authored.add("read16", bytes([0xba, 50, 16]))
    authored.add("increment14", bytes([0x46, 14]))
    authored.add("decrement15", bytes([0xc6, 15]))
    authored.add("decrement16", bytes([0xc6, 16]))
    if version:
        authored.add("pointer", move(20, 60))
        authored.add("indirect_move", bytes([0x0a, 20, 0x34, 0x12]))
        authored.add("indirect_add", bytes([0x2a, 20, 2, 0]))
        authored.add("indirect_subtract", bytes([0x6a, 20, 1, 0]))
    for index in (40, 41, 42, 14, 15, 16):
        authored.add(f"overwrite_{index}", move(index, 99, version))
    expected_value = 5 if version else 39
    width = 2 if version else 1
    # Both branches target their fallthrough. Only a captured branch decision
    # can distinguish them; next_pc alone cannot recover the historic result.
    authored.add("condition_true", bytes([0x48, 50]) + expected_value.to_bytes(width, "little") + b"\0\0")
    authored.add("condition_false", bytes([0x48, 50]) + (expected_value + 1).to_bytes(width, "little") + b"\0\0")
    authored.add("jump", b"\x18\0\0")
    authored.add("stop", b"\0")
    code = bytes(authored.code)
    with QMP(binary, version, code, timeout) as qmp:
        qmp.set("scumm-observation-mask", 1)
        state = qmp.run()
        expect(state["status"], RETURN, "resolved fixture completes")
        records = {record["pc"]: record for record in journal(qmp)["records"]}
        expected = ([([0, 7], 0, 7), ([7, 9], 7, 16), ([16, 11], 16, 5)] if version else
                    [([0, 40], 0, 40), ([40, 41], 40, 81), ([81, 42], 81, 39)])
        for name, (resolved, before, after) in zip(("read14", "read15", "read16"), expected):
            record = records[authored.pc[name]]
            expect(record["resolved"], resolved, "historic variable inputs " + name)
            expect(record["destination"], {"index": 50, "before": before, "after": after},
                   "historic destination " + name)
            expect(record["decoded"]["args"][1], [1, int(name[-2:]), 1], "preserved indirect selector")
        inc_dec = [("increment14", 14, 40, 7 if version else 40, 8 if version else 41),
                   ("decrement15", 15, 41, 9 if version else 41, 8 if version else 40),
                   ("decrement16", 16, 42, 11 if version else 42, 10 if version else 41)]
        for name, index, before, consumed, after in inc_dec:
            record = records[authored.pc[name]]
            expect(record["resolved"], [consumed], "INC/DEC resolved consumed value")
            expect(record["destination"], {"index": index, "before": before, "after": after},
                   "INC/DEC direct destination with versioned read semantics")
        if version:
            for name, before, after, rhs in (("indirect_move", 0, 0x1234, 0x1234),
                                           ("indirect_add", 0x1234, 0x1236, 2),
                                           ("indirect_subtract", 0x1236, 0x1235, 1)):
                record = records[authored.pc[name]]
                expect(record["resolved"], [60, rhs], "historic indirect destination selector")
                expect(record["destination"], {"index": 60, "before": before, "after": after},
                       "resolved indirect write address")
        for name, taken in (("condition_true", False), ("condition_false", True), ("jump", True)):
            record = records[authored.pc[name]]
            expect(record["branch_taken"], taken, "captured branch decision " + name)
            expect(record["next"], record["decoded"]["next"], "authored equal-target branch extent")
        expect(records[authored.pc["stop"]]["branch_taken"], None, "non-branch decision is absent")
        expect([state["vars"][index] for index in (40, 41, 42, 14, 15, 16)],
               [99] * 6, "later values differ from historical inputs")
        expect(state["vars"][50], expected_value, "independent final arithmetic value")
        expect_accounting(qmp, [len(authored.pc), 0], [len(authored.pc), 0], len(authored.pc))
    return {"version": version, "historical_selectors": [14, 15, 16],
            "increment_decrement": 3, "indirect_writes": 3 if version else 0,
            "branch_decisions_at_equal_targets": 3}


def static_queries(binary: Path, version: int, timeout: float) -> dict[str, Any]:
    code = b"\x46\x14" * 70 + b"\0"
    with QMP(binary, version, code, timeout) as qmp:
        initial = qmp.state()
        initial_runtime, initial_events, initial_scene = runtime(qmp), journal(qmp), scene(qmp)
        expect(qmp.get("scumm-decode-limit"), 64, "default decode page size")
        for limit in (1, 17, 64):
            qmp.set("scumm-decode-limit", limit)
            page = json_property(qmp, "scumm-decode-json")
            source_identity(page["source"], version, code)
            expect(page["schema"], "fdisbull-scumm-early-decode-1", "additive decode schema")
            expect((page["start_pc"], page["limit"], page["next_pc"], page["stop"]),
                   (0, limit, limit * 2, "limit"), "bounded decode cursor")
            expect([record["bytes"] for record in page["records"]], ["4614"] * limit,
                   "static disassembly exact instruction bytes")
        qmp.set("scumm-decode-pc", 128)
        page = json_property(qmp, "scumm-decode-json")
        expect((len(page["records"]), page["next_pc"], page["stop"]), (7, len(code), "end"),
               "decode final page extent")
        qmp.set("scumm-decode-pc", len(code))
        page = json_property(qmp, "scumm-decode-json")
        expect((page["records"], page["next_pc"], page["stop"]), ([], len(code), "end"),
               "decode at end remains a pure empty page")
        for prop, value in (("scumm-decode-limit", 0), ("scumm-decode-limit", 65),
                            ("scumm-decode-pc", len(code) + 1)):
            qmp.set(prop, value, error=True)
        expect(qmp.get("scumm-decode-limit"), 64, "invalid decode limit is atomic")
        expect(qmp.state(), initial, "all reads and selectors preserve guest and observer state")
        expect(runtime(qmp), initial_runtime, "query runtime purity")
        expect(journal(qmp), initial_events, "query journal purity")
        expect(scene(qmp), initial_scene, "query scene purity")
    return {"limits": [1, 17, 64], "exact_bytes": True, "pure_queries_and_selectors": True}


def controls_and_reset(binary: Path, timeout: float) -> dict[str, Any]:
    code = move(20, 7) + bytes([0x01, 2, 5, 6]) + move(21, 9) + b"\x80\0"
    control_names = ("scumm-observation-mask", "scumm-observation-capacity", "scumm-step-budget")
    selector_names = ("scumm-decode-pc", "scumm-decode-limit")
    with QMP(binary, 2, code, timeout) as qmp:
        initial, initial_runtime = qmp.state(), runtime(qmp)
        initial_epoch, generation = initial["epoch"], initial["control_generation"]
        for prop in control_names:
            qmp.set(prop, qmp.get(prop))
            generation += 1
            state = qmp.state()
            expect((state["epoch"], state["control_generation"]), (initial_epoch, generation),
                   "accepted no-op control write is a new generation")
        for prop, value in zip(control_names, (3, 64, 2)):
            qmp.set(prop, value)
            generation += 1
        qmp.set("scumm-decode-pc", 4)
        qmp.set("scumm-decode-limit", 1)
        expect(qmp.state()["control_generation"], generation, "selectors preserve control generation")
        first = qmp.run()
        expect((first["status"], first["retired"], first["run_retired"]), (BUDGET, 2, 2),
               "bounded work before observation clear")
        before_runtime = runtime(qmp)
        controls = {prop: qmp.get(prop) for prop in (*control_names, *selector_names)}
        before_clear = qmp.state()
        qmp.set("scumm-observation-clear", False, error=True)
        expect(qmp.state(), before_clear, "rejected clear is atomic")
        qmp.set("scumm-observation-clear", True)
        cleared = qmp.state()
        expect((cleared["epoch"], cleared["control_generation"]),
               (initial_epoch + 1, generation + 1), "clear advances epoch and generation once")
        expect(architecture(cleared), architecture(first), "clear preserves all architectural facts")
        expect(cleared["run_retired"], first["run_retired"], "clear preserves current run accounting")
        expect(runtime(qmp), before_runtime, "clear preserves runtime state")
        expect({prop: qmp.get(prop) for prop in controls}, controls, "clear preserves controls and selectors")
        expect_accounting(qmp, [0, 0], [0, 0], 0)
        second = qmp.run()
        expect((second["status"], second["retired"], second["run_retired"]), (WAIT, 4, 2),
               "continuation retires from the preserved guest PC")
        records = journal(qmp)["records"]
        expect([record["seq"] for record in records], [1, 2], "cleared journal restarts its sequence")
        expect([record["control_generation"] for record in records], [generation + 1] * 2,
               "post-clear records carry the new generation")
        before_restart = qmp.state()
        qmp.set("scumm-restart", True)
        restarted = qmp.state()
        expect((restarted["epoch"], restarted["control_generation"]),
               (before_restart["epoch"] + 1, before_restart["control_generation"] + 1),
               "restart starts a distinct execution identity")
        expect(architecture(restarted), architecture(initial), "restart clears guest architecture")
        expect(runtime(qmp), initial_runtime, "restart clears runtime")
        expect(restarted["run_retired"], 0, "restart clears run accounting")
        expect({prop: qmp.get(prop) for prop in controls}, controls, "restart preserves controls and selectors")
        expect_accounting(qmp, [0, 0], [0, 0], 0)
        qmp.run()
        before_reset = qmp.state()
        reset = qmp.reset()
        expect((reset["epoch"], reset["control_generation"]),
               (before_reset["epoch"] + 1, before_reset["control_generation"] + 1),
               "global reset starts exactly one new identity")
        expect(architecture(reset), architecture(initial), "global reset clears architecture")
        expect(runtime(qmp), initial_runtime, "global reset clears runtime")
        expect({prop: qmp.get(prop) for prop in controls}, controls, "global reset preserves controls and selectors")
        expect_accounting(qmp, [0, 0], [0, 0], 0)
    return {"no_op_control_writes": 3, "clear_preserves_guest_and_run": True,
            "restart_and_global_reset": True, "selectors_preserved": True}


def capacity_growth(binary: Path, timeout: float) -> dict[str, Any]:
    code = bytes([0x01, 2, 5, 6, 0x01, 2, 7, 8, 0])
    with QMP(binary, 2, code, timeout) as qmp:
        qmp.set("scumm-observation-mask", 3)
        qmp.set("scumm-observation-capacity", 1)
        qmp.set("scumm-step-budget", 1)
        first = qmp.run()
        expect_accounting(qmp, [1, 1], [1, 0], 1)
        generation = first["control_generation"]
        qmp.set("scumm-observation-capacity", 3)
        qmp.run()
        records = journal(qmp)["records"]
        expect([record["seq"] for record in records], [1, 3, 4],
               "retained sequence gaps identify dropped events before growth")
        expect([record["channel"] for record in records], [0, 0, 1],
               "growth appends later committed events without overwriting history")
        expect([record["control_generation"] for record in records],
               [generation, generation + 1, generation + 1], "retained records preserve control generations")
        expect_accounting(qmp, [2, 2], [2, 1], 2)
        qmp.run()
        expect_accounting(qmp, [3, 2], [2, 1], 3)
        final = qmp.state()
        qmp.set("scumm-observation-capacity", 2, error=True)
        expect(qmp.state(), final, "destructive shrink rejection preserves generation and journal")
    return {"retained_sequences": [1, 3, 4], "final_dropped": [1, 1]}


def cached_mode_changes(binary: Path, timeout: float) -> dict[str, Any]:
    # Revisit exactly the same two PCs under each observation mask. The actor
    # becomes unchanged after the first visit, but the optional SCENE helper is
    # still reached for its potentially scene-affecting instruction.
    code = bytes([0x01, 2, 5, 6, 0x18, 0xf9, 0xff])
    with QMP(binary, 2, code, timeout) as qmp:
        qmp.set("scumm-step-budget", 2)
        counts = [(0, [0, 0], 0), (1, [2, 0], 2), (2, [2, 0], 3), (3, [4, 0], 5)]
        for iteration, (mask, eligible, calls) in enumerate(counts, 1):
            qmp.set("scumm-observation-mask", mask)
            state = qmp.run()
            expect((state["pc"], state["retired"], state["run_retired"], state["status"]),
                   (0, iteration * 2, 2, BUDGET), "same PCs execute through cached mode changes")
            expect_accounting(qmp, eligible, eligible, calls)
        records = journal(qmp)["records"]
        expect([record["retired"] for record in records], [3, 4, 7, 8],
               "mode-disabled intervals are not fabricated as observed history")
        expect(len({record["control_generation"] for record in records}), 2,
               "retained history separates observed mode generations")
    return {"masks_at_same_pc": [0, 1, 2, 3], "retained_retirements": [3, 4, 7, 8]}


def blocked_effects(binary: Path, timeout: float) -> dict[str, Any]:
    cases = [("room", bytes([0x72, 1, 0]), BLOCKED),
             ("walk", bytes([0x1e, 2, 5, 6, 0]), BLOCKED),
             ("script_start", bytes([0x42, 4, 0]), BLOCKED),
             ("invalid_actor", bytes([0x01, 0, 5, 6, 0]), FAULT),
             ("missing_resource", bytes([0x0c, 3, 0x21, 0]), BLOCKED)]
    for name, code, expected_status in cases:
        with tempfile.TemporaryDirectory(prefix="scumm-observation-blocked-") as temporary:
            manifest = fixture(Path(temporary), code)
            with QMP(binary, 2, code, timeout, resource_manifest=manifest) as qmp:
                initial = scene(qmp)
                qmp.set("scumm-observation-mask", 3)
                decoded = qmp.decode()[0]
                state = qmp.run()
                expect((state["pc"], state["status"], state["retired"]),
                       (0, expected_status, 0), "noncommitted boundary " + name)
                expect(decoded["bytes"], code[:decoded["size"]].hex(), "blocked static intent remains inspectable")
                snapshot = scene(qmp)
                expect(snapshot["actors"], initial["actors"], "blocked operation does not move actors")
                expect(snapshot["resources"], initial["resources"], "blocked operation does not alter resources")
                expect(snapshot["control"], initial["control"], "blocked operation does not apply UI state")
                expect(snapshot["verbs"], initial["verbs"], "blocked operation does not alter verb slots")
                expect_accounting(qmp, [0, 0], [0, 0], 0)
                expect(journal(qmp)["records"], [], "blocked intent is never a committed observation")
                qmp.run()
                expect_accounting(qmp, [0, 0], [0, 0], 0)
    return {"noncommitted_boundaries": [case[0] for case in cases], "observer_calls": 0}


def generated_tcg(binary: Path, timeout: float) -> dict[str, Any]:
    results = []
    for name, code, scene_calls in (("scalar", bytes([0x46, 20, 0]), 0),
                                     ("actor", bytes([0x01, 2, 5, 6, 0]), 1)):
        for mask in range(4):
            with tempfile.TemporaryDirectory(prefix="scumm-observation-tcg-") as temporary:
                directory = Path(temporary)
                log = directory / "operations.log"
                launcher = directory / "qemu-with-operation-log"
                # A private argv-preserving launcher lets the existing QMP
                # owner enable operation logging without changing its API.
                launcher.write_text(f"#!{sys.executable}\nimport os, sys\n"
                    f"os.execv({str(binary)!r}, [{str(binary)!r}, '-d', 'op', '-D', {str(log)!r}] + sys.argv[1:])\n")
                launcher.chmod(0o700)
                with QMP(launcher, 2, code, timeout) as qmp:
                    qmp.set("scumm-observation-mask", mask)
                    state = qmp.run()
                    expect((state["status"], state["retired"]), (RETURN, 2), "logged TCG fixture completes")
                text = log.read_text()
                steps = len(re.findall(r"\bcall\s+scumm_step\b", text))
                observes = len(re.findall(r"\bcall\s+scumm_observe\b", text))
                expected_calls = 2 if mask & 1 else scene_calls if mask & 2 else 0
                expect(steps, 2, "mandatory semantic helper in generated TCG")
                expect(observes, expected_calls, "mask-selected optional generated observer helpers")
                expect(state["helper_calls"], expected_calls, "reached observer calls match successful native execution")
                results.append({"fixture": name, "mask": mask, "semantic_helpers": steps,
                                "observer_helpers": observes, "log_sha256": digest(text.encode())})
    return {"generated_calls": results}


def native_scene_consumer(binary: Path, timeout: float) -> dict[str, Any]:
    from processor_scene import build_scene_packet

    name = b"Dot\x80"
    code = (bytes([0x01, 2, 5, 6, 0x13, 2, 2, 4, 0x13, 2, 7, 2, 1,
                   0x13, 2, 0, 3]) + name + b"\0" +
            bytes([0x13, 0, 9, 5, 0x0c, 2, 0x21, 0x60, 5, 0xf6, 0]))
    with tempfile.TemporaryDirectory(prefix="scumm-observation-consumer-") as temporary:
        manifest = fixture(Path(temporary), code)
        with QMP(binary, 2, code, timeout, resource_manifest=manifest) as qmp:
            qmp.set("scumm-observation-mask", 3)
            state = qmp.run()
            expect((state["status"], state["retired"]), (RETURN, 8), "consumer fixture retirement")
            snapshot = scene(qmp)
            events = journal(qmp)
            page = json_property(qmp, "scumm-decode-json")
            expect(scene(qmp), snapshot, "owned stopped capture remains coherent across queries")
            inputs = copy.deepcopy((snapshot, events, page))
            packet = build_scene_packet(code=code, scene=snapshot, events=events, decode_pages=[page])
            expect((snapshot, events, page), inputs, "consumer does not mutate native capture")
            expect(packet["actors"], snapshot["actors"], "consumer preserves complete native actor model")
            expect(packet["actors"][2]["palette"][1], 7, "native palette reaches consumer")
            expect(packet["actors"][2]["name"]["bytes"], name.hex(), "native byte name reaches consumer")
            expect(packet["control"]["default_talk_color"], 9, "native global color reaches consumer")
            expect(packet["control"]["vars"]["21"], 5, "native cursor reaches consumer")
            entry = resource({"resources": packet["resources"]["entries"]}, "costume", 2)
            assert entry is not None
            expect(entry["resident"], True, "native resource residency reaches consumer")
            expect(len(packet["disassembly"]["retirements"]), 8, "consumer retains native retirements")
            expect(len(packet["committed_changes"]), 7, "consumer retains committed scene effects")
            expect(packet["disassembly"]["static_listing_complete"], True,
                   "complete native static listing is distinct from reachability")
            qualification = packet["qualification"]
            expect(qualification["current_snapshot"], True, "current implemented snapshot is qualified")
            for key in ("history_complete", "control_variable_history_complete", "actor_visibility",
                        "room_rendering", "costume_decode", "screen_presentation"):
                expect(qualification[key], False, "consumer preserves unqualified scope " + key)
    return {"coherent_native_capture": True, "retirements": 8, "committed_changes": 7,
            "palette_name_resource_control_preserved": True, "history_and_rendering_unqualified": True}


def cases() -> dict[str, Callable[[Path, float], dict[str, Any]]]:
    result: dict[str, Callable[[Path, float], dict[str, Any]]] = {}
    for version in (1, 2):
        result[f"actor_events_v{version}"] = lambda binary, timeout, v=version: actor_events(binary, v, timeout)
    for version in range(3):
        result[f"resolved_operands_v{version}"] = lambda binary, timeout, v=version: resolved_operands(binary, v, timeout)
        result[f"static_queries_v{version}"] = lambda binary, timeout, v=version: static_queries(binary, v, timeout)
    result.update(runtime_events=runtime_events, masks_and_capacity=masks_and_capacity,
                  controls_and_reset=controls_and_reset, capacity_growth=capacity_growth,
                  cached_mode_changes=cached_mode_changes, blocked_effects=blocked_effects,
                  generated_tcg=generated_tcg, native_scene_consumer=native_scene_consumer)
    return result


def main() -> int:
    available = cases()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--case", choices=available, action="append")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than zero and at most 60 seconds")
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / ".git").exists() and args.output.resolve().is_relative_to(source_root):
        parser.error("--output must be outside the source checkout")
    binary = args.qemu.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("--qemu must be an executable file")
    binary_hash = sha256_file(binary)
    report: dict[str, Any] = {
        "schema": "fdisbull-scumm-observation-qualification-1",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "qemu": str(binary), "qemu_sha256": binary_hash,
        "harness_sha256": sha256_file(Path(__file__)),
        "scope": "Authored native DISASM/SCENE observation contract; no original game data.",
        "unverified": ["Original-game equivalence", "Rendering and scene composition",
                       "Full scheduler and unsupported opcodes", "Performance and hosted CI"],
        "cases": [],
    }
    for name in args.case or available:
        started = time.monotonic()
        record: dict[str, Any] = {"case": name}
        try:
            record.update(result="pass", evidence=available[name](binary, args.timeout))
        except Exception as error:
            record.update(result="fail", error=f"{type(error).__name__}: {error}")
        record["seconds"] = round(time.monotonic() - started, 3)
        report["cases"].append(record)
        print(json.dumps({key: value for key, value in record.items() if key != "evidence"}), flush=True)
    report["passed"] = sum(record["result"] == "pass" for record in report["cases"])
    report["failed"] = len(report["cases"]) - report["passed"]
    report["result"] = "fail" if report["failed"] else "pass"
    if sha256_file(binary) != binary_hash:
        report.update(result="inconclusive", error="QEMU executable changed during qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "passed": report["passed"],
                      "failed": report["failed"], "output": str(args.output.resolve())}))
    return 0 if report["result"] == "pass" else 2 if report["result"] == "inconclusive" else 1


if __name__ == "__main__":
    raise SystemExit(main())
