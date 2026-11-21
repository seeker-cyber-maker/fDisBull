"""Compact behavior gate for an explicitly pinned, already-built AGI binary.

This synthetic-only batch does not replace the exhaustive native acceptance
modules. It owns at most eight children and twenty run invocations, each with
a five-second QMP deadline and at most 128 retirements. An enclosing controller
must enforce a 60-second whole-gate deadline including cleanup. This module
stops admitting work after 50 seconds and never retries a failed scenario.

Set FDISBULL_QEMU_AGI_INTENT and FDISBULL_QEMU_AGI_EXPECTED_SHA256 explicitly.
FDISBULL_QEMU_AGI_EVIDENCE selects an existing caller-owned receipt directory.
No game decoder, collector, resource, native build, or expected image is used.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native" / "qemu-agi"))
from harness import HarnessError, QemuAGI
from visual_binding_harness import QemuAGIViewBinding, binding_guest_state
from draw_intent_harness import QemuAGIDrawIntent, intent_guest_state


LIMITS = {"children": 8, "runs": 20, "active_seconds": 50,
          "whole_gate_seconds": 60, "qmp_seconds": 5, "retirements_per_run": 128}
PROFILES = {
    "scalar": (QemuAGI, "agi-2917-scalar-position-pilot-1", "native"),
    "binding": (QemuAGIViewBinding, "agi-2917-view-binding-pilot-1", "binding"),
    "intent": (QemuAGIDrawIntent, "agi-2917-draw-intent-pilot-1", "intent"),
}
SOURCE_FILES = (
    "tests/test_qemu_agi_behavior_batch.py",
    "native/qemu-agi/harness.py",
    "native/qemu-agi/visual_binding_harness.py",
    "native/qemu-agi/draw_intent_harness.py",
    "native/qemu-agi/BEHAVIOR_BATCH.md",
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def actor(index=0, **changes):
    value = {
        "id": index, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0,
        "view_bound": False, "view": 0, "loop": 0, "cel": 0,
        "width": 0, "height": 0, "animated": False, "update": False,
        "cycling": False, "ignore_horizon": False, "update_pos": False,
        "view_replaced": False, "motion": "normal", "cycle": "normal",
        "direction": 0,
    }
    value.update(changes)
    return value


def payload(value):
    return {key: item for key, item in value.items() if key != "id"}


def authored_catalog():
    """Literal synthetic geometry, encoded directly from the wire contract."""
    views = (
        (10, (((2, 3), (7, 5), (9, 8)), ((4, 6), (20, 12)))),
        (11, (((3, 4),), ((6, 2), (30, 20), (12, 10)))),
        (14, (((2, 2),),)),
    )
    result = bytearray(b"FDBAGIV1" + bytes((5, 0, 3, 0)))
    for view, loops in views:
        result.extend((view, len(loops)))
        result.extend(hashlib.sha256(f"behavior-batch-view-{view}".encode("ascii")).digest())
        for cels in loops:
            result.append(len(cels))
            for width, height in cels:
                result.extend((width, height))
    return bytes(result)


CATALOG = authored_catalog()
CATALOG_METADATA = {
    "sha256": sha256(CATALOG), "size": len(CATALOG), "view_count": 3,
    "loop_count": 5, "cel_count": 10, "horizon": 5,
}


def step(label, raw, *, after=None, load=None, resolved=None):
    """Declare expected observations; this helper does not interpret opcodes."""
    return {"label": label, "bytes": bytes(raw), "after": after, "load": load,
            "resolved": {} if resolved is None else resolved}


def compiled(steps):
    return b"".join(row["bytes"] for row in steps)


def expected_trace(steps, generation, mask, capacity):
    """Frame literal state expectations with PCs, retirement and channel data.

    Actor effects, dimensions and positions are supplied in the authored rows;
    no binding, geometry, cycle, instruction decoder or resource model runs.
    """
    actors, loads = [actor(i) for i in range(16)], set()
    records, pc = [], 0
    for retired, row in enumerate(steps, 1):
        raw = row["bytes"]
        common = {"control_generation": generation, "pc": pc, "opcode": raw[0],
                  "bytes": list(raw), "next_pc": pc + len(raw), "retired": retired}
        if mask & 1:
            records.append({"kind": "retire", **common, **row["resolved"]})
        if row["load"] is not None:
            view = row["load"]
            assert view not in loads, "Declare duplicate loads as retirement-only rows"
            loads.add(view)
            if mask & 2:
                records.append({"kind": "view_load", **common, "view": view,
                                "before": False, "after": True})
        if row["after"] is not None:
            after = row["after"]
            number = after["id"]
            before = actors[number]
            assert before != after, "Declare redundant writes as retirement-only rows"
            if mask & 2:
                records.append({"kind": "actor", **common, "actor": number,
                                "before": payload(before), "after": payload(after)})
            actors[number] = deepcopy(after)
        pc += len(raw)
    full = [{"seq": index, **record} for index, record in enumerate(records, 1)]
    return full[:capacity], full, actors, sorted(loads)


# Each row below is an authored expected transition, not a production-model result.
BOUND = {"view_bound": True, "view_replaced": True}
A0 = {"x": 150, "prev_x": 150, "update_pos": True, **BOUND}
A4 = {"view": 10, "view_bound": True, "view_replaced": True}
A5 = {"prev_x": 159, "view": 10, "update_pos": True, **BOUND}
BINDING_STEPS = (
    step("load-10", (30, 10), load=10, resolved={"resolved_value": 10}),
    step("load-11", (30, 11), load=11, resolved={"resolved_value": 11}),
    step("load-14", (30, 14), load=14, resolved={"resolved_value": 14}),
    step("duplicate-load", (30, 10), resolved={"resolved_value": 10}),
    step("geometry-position", (37, 0, 150, 0), after=actor(x=150, prev_x=150),
         resolved={"resolved_position": {"x": 150, "y": 0}}),
    step("top-horizon-repair", (41, 0, 10), after=actor(**A0, view=10, width=2, height=3, y=6),
         resolved={"resolved_value": 10}),
    step("taller-cel", (47, 0, 2), after=actor(**A0, view=10, cel=2, width=9, height=8, y=7),
         resolved={"resolved_value": 2}),
    step("invalid-preserved-cel-falls-back", (43, 0, 1),
         after=actor(**A0, view=10, loop=1, width=4, height=6, y=7), resolved={"resolved_value": 1}),
    step("wider-and-taller", (47, 0, 1),
         after=actor(prev_x=150, x=140, y=11, view=10, loop=1, cel=1, width=20, height=12,
                     update_pos=True, **BOUND), resolved={"resolved_value": 1}),
    step("view-keeps-valid-loop-cel", (41, 0, 11),
         after=actor(prev_x=150, x=130, y=19, view=11, loop=1, cel=1, width=30, height=20,
                     update_pos=True, **BOUND), resolved={"resolved_value": 11}),
    step("loop-falls-back-cel", (43, 0, 0),
         after=actor(prev_x=150, x=130, y=19, view=11, width=3, height=4,
                     update_pos=True, **BOUND), resolved={"resolved_value": 0}),
    step("get-geometry-position", (39, 0, 90, 91)),
    step("bottom-position", (37, 1, 158, 168),
         after=actor(1, x=158, y=168, prev_x=158, prev_y=168),
         resolved={"resolved_position": {"x": 158, "y": 168}}),
    step("no-bottom-clamp", (41, 1, 14),
         after=actor(1, x=158, y=168, prev_x=158, prev_y=168, view=14, width=2, height=2, **BOUND),
         resolved={"resolved_value": 14}),
    step("above-horizon-position", (37, 2, 1, 1), after=actor(2, x=1, y=1, prev_x=1, prev_y=1),
         resolved={"resolved_position": {"x": 1, "y": 1}}),
    step("no-independent-horizon-clamp", (41, 2, 14),
         after=actor(2, x=1, y=1, prev_x=1, prev_y=1, view=14, width=2, height=2, **BOUND),
         resolved={"resolved_value": 14}),
    step("outside-position", (37, 3, 200, 250),
         after=actor(3, x=200, y=250, prev_x=200, prev_y=250),
         resolved={"resolved_position": {"x": 200, "y": 250}}),
    step("right-only-repair", (41, 3, 14),
         after=actor(3, x=158, y=250, prev_x=200, prev_y=250, view=14, width=2, height=2,
                     update_pos=True, **BOUND), resolved={"resolved_value": 14}),
    step("bind-before-animation", (41, 4, 10),
         after=actor(4, **A4, y=6, width=2, height=3, update_pos=True), resolved={"resolved_value": 10}),
    step("first-animation-clears-update-pos", (33, 4),
         after=actor(4, **A4, y=6, width=2, height=3, animated=True, update=True, cycling=True)),
    step("new-sticky-repair", (47, 4, 2),
         after=actor(4, **A4, y=7, cel=2, width=9, height=8, update_pos=True,
                     animated=True, update=True, cycling=True), resolved={"resolved_value": 2}),
    step("repeat-animation-retains-sticky", (33, 4)),
    step("smaller-cel-keeps-position", (47, 4, 0),
         after=actor(4, **A4, y=7, width=2, height=3, update_pos=True,
                     animated=True, update=True, cycling=True), resolved={"resolved_value": 0}),
    step("repeat-cel-is-noop", (47, 4, 0), resolved={"resolved_value": 0}),
    step("view-variable", (3, 50, 10)), step("loop-variable", (3, 51, 1)),
    step("cel-variable", (3, 52, 1)), step("x-variable", (3, 53, 159)),
    step("y-variable", (3, 54, 0)),
    step("duplicate-variable-load", (31, 50), resolved={"resolved_value": 10}),
    step("variable-position", (38, 5, 53, 54), after=actor(5, x=159, prev_x=159),
         resolved={"resolved_position": {"x": 159, "y": 0}}),
    step("variable-view", (42, 5, 50),
         after=actor(5, **A5, x=158, y=6, width=2, height=3), resolved={"resolved_value": 10}),
    step("variable-loop", (44, 5, 51),
         after=actor(5, **A5, x=156, y=6, loop=1, width=4, height=6), resolved={"resolved_value": 1}),
    step("variable-cel", (48, 5, 52),
         after=actor(5, **A5, x=140, y=11, loop=1, cel=1, width=20, height=12),
         resolved={"resolved_value": 1}),
    step("overwrite-view-variable", (3, 50, 99)), step("overwrite-loop-variable", (3, 51, 99)),
    step("overwrite-cel-variable", (3, 52, 99)), step("overwrite-x-variable", (3, 53, 99)),
    step("overwrite-y-variable", (3, 54, 99)),
    step("get-variable-position", (39, 5, 80, 81)), step("ordered-alias", (39, 3, 82, 82)),
    step("flag", (12, 9)), step("return", (0,)),
)
BINDING_CODE = compiled(BINDING_STEPS)
BINDING_VARIABLES = {50: 99, 51: 99, 52: 99, 53: 99, 54: 99,
                     80: 140, 81: 11, 82: 250, 90: 130, 91: 19}


INTENT_STEPS = (
    step("redundant-stop-unbound", (70, 15)),
    step("start-unbound", (71, 15), after=actor(15, cycling=True)),
    step("redundant-start", (71, 15)),
    step("stop-unbound", (70, 15), after=actor(15)),
    step("redundant-stop", (70, 15)),
    step("first-animation", (33, 15), after=actor(15, animated=True, update=True, cycling=True)),
    step("stop-animated", (70, 15), after=actor(15, animated=True, update=True)),
    step("repeat-animation-keeps-stopped", (33, 15)),
    step("load", (30, 10), load=10, resolved={"resolved_value": 10}),
    step("animate-draw-actor", (33, 0), after=actor(animated=True, update=True, cycling=True)),
    step("bind-draw-actor", (41, 0, 10),
         after=actor(y=6, view=10, width=2, height=3, animated=True, update=True,
                     cycling=True, update_pos=True, **BOUND), resolved={"resolved_value": 10}),
    step("unrepaired-draw-position", (37, 0, 255, 0),
         after=actor(x=255, prev_x=255, view=10, width=2, height=3, animated=True,
                     update=True, cycling=True, update_pos=True, **BOUND),
         resolved={"resolved_position": {"x": 255, "y": 0}}),
    step("stop-before-draw", (70, 0),
         after=actor(x=255, prev_x=255, view=10, width=2, height=3, animated=True,
                     update=True, update_pos=True, **BOUND)),
    step("start-before-draw", (71, 0),
         after=actor(x=255, prev_x=255, view=10, width=2, height=3, animated=True,
                     update=True, cycling=True, update_pos=True, **BOUND)),
)
INTENT_PC = len(compiled(INTENT_STEPS))
INTENT_CODE = compiled(INTENT_STEPS) + bytes((35, 0, 3, 200, 99, 0))


FAULT_STEPS = (
    step("prefix-variable", (3, 200, 7)), step("prefix-flag", (12, 200)),
    step("prefix-load", (30, 10), load=10, resolved={"resolved_value": 10}),
    step("prefix-animate", (33, 0), after=actor(animated=True, update=True, cycling=True)),
    step("prefix-position", (37, 0, 10, 80),
         after=actor(x=10, y=80, prev_x=10, prev_y=80, animated=True, update=True, cycling=True),
         resolved={"resolved_position": {"x": 10, "y": 80}}),
    step("prefix-bind", (41, 0, 10),
         after=actor(x=10, y=80, prev_x=10, prev_y=80, view=10, width=2, height=3,
                     animated=True, update=True, cycling=True, **BOUND), resolved={"resolved_value": 10}),
)


def pending_draw(pc):
    return {"kind": "draw", "reason": "draw_requires_host", "pc": pc,
            "opcode": 35, "bytes": [35, 0], "actor": 0,
            "retired": False, "committed": False, "completion_available": False}


def expected_guest(profile, *, steps=(), status="ready", pc=0, variables=None,
                   flags=(), fault=None, pending=None):
    _, _, actors, loads = expected_trace(steps, 0, 0, 0)
    if profile == "scalar":
        actors = [{key: value[key] for key in ("id", "x", "y", "prev_x", "prev_y")}
                  for value in actors]
    values = [0] * 256
    for index, value in (variables or {}).items():
        values[index] = value
    flag_values = [int(index in flags) for index in range(256)]
    guest = {"actors": actors, "variables": values, "flags": flag_values, "pc": pc,
             "retired": len(steps), "status": status, "fault": fault}
    if profile != "scalar":
        guest.update(horizon=5, loaded_views=loads)
    if profile == "intent":
        guest["pending_effect"] = pending
    return guest


class Batch:
    """Own admission budgets and receipts; never reload or mutate a guest."""

    def __init__(self, binary, expected_binary, evidence):
        self.binary, self.expected_binary, self.evidence = binary, expected_binary, evidence
        self.started = time.monotonic()
        self.children, self.runs = [], []
        self.source_hashes = {name: file_sha256(ROOT / name) for name in SOURCE_FILES}
        self.report = {"schema": "fdisbull-agi-behavior-batch-1", "limits": LIMITS,
                       "binary": str(binary), "expected_binary_sha256": expected_binary,
                       "binary_sha256_before": file_sha256(binary), "source_hashes": self.source_hashes,
                       "children": self.children, "runs": self.runs, "outcome": "running"}
        self.active = None
        assert self.report["binary_sha256_before"] == expected_binary, "Candidate binary identity mismatch"
        self.flush()

    def flush(self):
        self.report["elapsed_seconds"] = time.monotonic() - self.started
        self.report["child_attempts"] = len(self.children)
        self.report["children_spawned"] = sum(row.get("pid") is not None for row in self.children)
        self.report["run_calls"] = len(self.runs)
        self.report["native_invocations"] = sum(row.get("native_invocation_advanced", False) for row in self.runs)
        self.report["native_invocations_with_work"] = sum(
            row.get("native_invocation_advanced", False) and row.get("retired", 0) > 0
            for row in self.runs)
        temporary = self.evidence / "batch-receipt.json.tmp"
        temporary.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.evidence / "batch-receipt.json")

    def guard(self):
        assert time.monotonic() - self.started < LIMITS["active_seconds"], "Batch active deadline exhausted"

    def identity(self, vm, state):
        row = self.active
        profile = row["profile"]
        source = {"sha256": row["program_sha256"], "size": row["program_bytes"],
                  "logic_id": 0, "profile": PROFILES[profile][1]}
        if profile != "scalar":
            source["catalog_sha256"] = row["catalog_sha256"]
        assert state["source"] == source
        assert state["schema"] == f"fdisbull-agi-{PROFILES[profile][2]}-state-1"
        assert vm.binary_sha256 == self.expected_binary
        if profile != "scalar":
            assert state["catalog"] == CATALOG_METADATA
        else:
            assert "catalog" not in state

    @contextmanager
    def launch(self, name, code, *, profile="intent", catalog=CATALOG, extra_args=(), reject=False):
        self.guard()
        assert len(self.children) < LIMITS["children"], "Child budget exhausted"
        record = {"name": name, "profile": profile, "program_bytes": len(code),
                  "program_sha256": sha256(code), "expected_startup_rejection": reject,
                  "catalog_sha256": None if profile == "scalar" else sha256(catalog),
                  "catalog_bytes": None if profile == "scalar" else len(catalog),
                  "outcome": "starting"}
        self.children.append(record)
        self.active = record
        self.flush()
        cls = PROFILES[profile][0]
        # Keep the partially initialized object available for PID/exit receipts
        # when the unchanged production constructor rejects native admission.
        vm = cls.__new__(cls)
        initialized = False
        try:
            options = {"timeout": LIMITS["qmp_seconds"], "evidence_dir": self.evidence,
                       "extra_args": extra_args}
            if profile == "scalar":
                cls.__init__(vm, self.binary, code, **options)
            else:
                cls.__init__(vm, self.binary, code, catalog, **options)
            initialized = True
            record["pid"] = vm.process.pid
            record["binary_sha256"] = vm.binary_sha256
            record["outcome"] = "admitted"
            self.flush()
            assert vm.binary_sha256 == self.expected_binary
            yield vm
            assert not reject, "Expected startup rejection was admitted"
            record["outcome"] = "passed"
        except BaseException as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            record["outcome"] = "rejected" if reject and isinstance(error, HarnessError) else "failed"
            if initialized:
                vm.close(failed=True)
                initialized = False
            raise
        finally:
            if initialized:
                vm.close()
            process = getattr(vm, "process", None)
            if process is not None:
                record["pid"] = process.pid
                record["exit_code"] = process.poll()
                record["reaped"] = process.returncode is not None
            record["binary_sha256"] = getattr(vm, "binary_sha256", None)
            record["failure_evidence"] = (str(vm.failure_evidence)
                                           if getattr(vm, "failure_evidence", None) else None)
            self.active = None
            self.flush()
            assert process is not None and process.returncode is not None, "Owned native child was not reaped"

    def run(self, vm, label, *, step_budget=None):
        self.guard()
        assert len(self.runs) < LIMITS["runs"], "Run-call budget exhausted"
        if step_budget is not None:
            assert 1 <= step_budget <= LIMITS["retirements_per_run"]
        effective_budget = vm.get("agi-step-budget") if step_budget is None else step_budget
        assert type(effective_budget) is int and 1 <= effective_budget <= LIMITS["retirements_per_run"]
        before = vm.state()
        row = {"child": self.active["name"], "label": label, "index": len(self.runs) + 1,
               "step_budget": effective_budget, "outcome": "started"}
        self.runs.append(row)
        self.flush()
        state = vm.run(step_budget=step_budget)
        snapshot = f"run-{row['index']:02d}-state.json"
        (self.evidence / snapshot).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        advanced = state["run"]["invocation"] != before["run"]["invocation"]
        row.update(outcome="stopped", state_file=snapshot, status=state["guest"]["status"],
                   pc=state["guest"]["pc"], retired=state["run"]["retired"] if advanced else 0,
                   native_last_run_retired=state["run"]["retired"], native_invocation_advanced=advanced,
                   guest_retired=state["guest"]["retired"],
                   native_invocation=state["run"]["invocation"],
                   native_elapsed_ns=state["run"]["elapsed_ns"], wall_ns=vm.last_run_wall_ns)
        assert state["run"]["retired"] <= LIMITS["retirements_per_run"]
        self.identity(vm, state)
        self.flush()
        return state

    def events(self, vm, label):
        value = vm.events()
        path = f"{self.active['name']}-{label}-events.json"
        (self.evidence / path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        assert value["schema"] == f"fdisbull-agi-{PROFILES[self.active['profile']][2]}-events-1"
        assert value["source"] == vm.state()["source"]
        return value

    def finish(self, error=None):
        self.report["binary_sha256_after"] = file_sha256(self.binary)
        self.report["source_hashes_after"] = {name: file_sha256(ROOT / name) for name in SOURCE_FILES}
        identities_unchanged = (self.report["binary_sha256_after"] == self.expected_binary
                                and self.report["source_hashes_after"] == self.source_hashes)
        clean = all(row.get("reaped") is True for row in self.children)
        self.report["identities_unchanged"] = identities_unchanged
        self.report["all_native_children_reaped"] = clean
        self.report["outcome"] = "passed" if error is None and identities_unchanged and clean else "failed"
        if error is not None:
            self.report["error"] = {"type": type(error).__name__, "message": str(error)}
        self.flush()
        assert identities_unchanged, "Pinned binary or inspected source changed during batch"
        assert clean, "A native child remained unaccounted for"


def verify_journal(batch, vm, state, steps, mask, capacity, scene_helper_calls, label):
    observation = state["observation"]
    rows = batch.events(vm, label)["events"]
    expected, all_rows, _, _ = expected_trace(steps, observation["control_generation"], mask, capacity)
    assert rows == expected
    assert observation["mask"] == mask and observation["capacity"] == capacity
    assert observation["count"] == len(expected)
    assert observation["eligible"] == len(all_rows)
    assert observation["dropped"] == len(all_rows) - len(expected)
    for channel, predicate in (("disasm", lambda row: row["kind"] == "retire"),
                               ("scene", lambda row: row["kind"] != "retire")):
        eligible = sum(predicate(row) for row in all_rows)
        stored = sum(predicate(row) for row in expected)
        assert observation["per_channel"][channel] == {
            "eligible": eligible, "stored": stored, "dropped": eligible - stored}
    helpers = len(steps) if mask & 1 else scene_helper_calls if mask & 2 else 0
    assert observation["helper_calls"] == helpers
    return rows


def behavior_bundle(batch, profile):
    intent = profile == "intent"
    steps, code, helper_calls = ((INTENT_STEPS, INTENT_CODE, 14) if intent else
                                 (BINDING_STEPS, BINDING_CODE, 28))
    final = expected_guest(profile, steps=steps, status="effect" if intent else "return",
                           pc=INTENT_PC if intent else len(code),
                           variables={} if intent else BINDING_VARIABLES,
                           flags=() if intent else (9,),
                           pending=pending_draw(INTENT_PC) if intent else None)
    copy_guest = intent_guest_state if intent else binding_guest_state
    variants = (("mask-0", 0, 256), ("mask-1", 1, 256), ("mask-2", 2, 256),
                ("mask-3", 3, 256), ("capacity-0", 3, 0), ("capacity-1", 3, 1))
    with batch.launch(f"{profile}-bundle", code, profile=profile) as vm:
        initial = vm.state()
        batch.identity(vm, initial)
        assert initial["guest"] == expected_guest(profile)
        assert vm.events()["events"] == []
        if intent:
            assert vm.qmp("qom-get", {"path": "/machine", "property": "draw-intent"}) is True
            with pytest.raises(HarnessError):
                vm.qmp("qom-set", {"path": "/machine", "property": "draw-intent", "value": False})
            assert vm.state() == initial
        guests = []
        last_epoch = initial["observation"]["epoch"]
        for index, (label, mask, capacity) in enumerate(variants):
            if index:
                vm.restart()
                reset = vm.state()
                assert copy_guest(reset) == copy_guest(initial)
                assert reset["source"] == initial["source"] and reset["catalog"] == initial["catalog"]
                assert reset["observation"]["epoch"] > last_epoch
                assert vm.events()["events"] == []
            vm.configure(mask=mask, capacity=capacity, step_budget=128)
            state = batch.run(vm, label)
            assert state["guest"] == final
            assert state["run"]["retired"] == len(steps)
            guests.append(copy_guest(state))
            rows = verify_journal(batch, vm, state, steps, mask, capacity, helper_calls, label)
            last_epoch = state["observation"]["epoch"]
            if not intent and index == 0:
                # The already admitted native catalog must survive this host-file change.
                vm.catalog_path.write_bytes(b"authored changed path, not an admitted replacement")
            if intent and label == "mask-3":
                pending_events = vm.events()
                assert batch.run(vm, "pending-direct-continue") == state
                assert vm.events() == pending_events
                assert all(row["opcode"] != 35 for row in rows)
                vm.clear_events()
                cleared = vm.state()
                assert copy_guest(cleared) == final
                assert cleared["observation"]["epoch"] > last_epoch
                assert cleared["observation"]["count"] == cleared["observation"]["eligible"] == 0
                assert vm.events()["events"] == []
                vm.configure(mask=0, capacity=0, step_budget=1)
                configured = vm.state()
                assert copy_guest(configured) == final
                assert batch.run(vm, "pending-after-clear-configure") == configured
                assert vm.events()["events"] == []
                last_epoch = configured["observation"]["epoch"]
        assert all(guest == final for guest in guests)


def atomic_fault(batch, name, instruction, fault_name, number):
    prefix = compiled(FAULT_STEPS)
    code = prefix + bytes(instruction) + bytes((3, 201, 99, 0))
    with batch.launch(name, code) as vm:
        vm.configure(mask=3, capacity=256, step_budget=len(FAULT_STEPS))
        before = batch.run(vm, "committed-prefix")
        assert before["guest"] == expected_guest("intent", steps=FAULT_STEPS, status="budget",
                                                  pc=len(prefix), variables={200: 7}, flags=(200,))
        rows = verify_journal(batch, vm, before, FAULT_STEPS, 3, 256, 4, "prefix")
        after = batch.run(vm, "fault", step_budget=1)
        expected = deepcopy(before["guest"])
        expected.update(status="fault", fault={"code": number, "name": fault_name,
                                               "pc": len(prefix), "opcode": instruction[0]})
        assert after["guest"] == expected
        assert after["run"]["retired"] == 0
        assert batch.events(vm, "fault")["events"] == rows
        for field in ("count", "eligible", "dropped", "helper_calls", "per_channel"):
            assert after["observation"][field] == before["observation"][field]


def prior_profile(batch, profile):
    code = bytes((37, 0, 10, 20, 35, 0, 0))
    after_actor = actor(x=10, y=20, prev_x=10, prev_y=20)
    position = (step("position", (37, 0, 10, 20), after=after_actor),)
    with batch.launch(f"{profile}-compatibility", code, profile=profile) as vm:
        vm.configure(mask=3, capacity=256, step_budget=128)
        state = batch.run(vm, "unsupported-draw")
        expected = expected_guest(profile, steps=position, status="fault", pc=4,
                                  fault={"code": 1, "name": "unsupported_opcode", "pc": 4, "opcode": 35})
        assert state["guest"] == expected
        assert state["run"]["retired"] == 1
        rows = batch.events(vm, "compatibility")["events"]
        expected_rows, _, _, _ = expected_trace(position, state["observation"]["control_generation"], 3, 256)
        if profile == "scalar":
            expected_rows[1]["kind"] = "position"
            for field in ("before", "after"):
                expected_rows[1][field] = {key: expected_rows[1][field][key]
                                            for key in ("x", "y", "prev_x", "prev_y")}
        else:
            expected_rows[0]["resolved_position"] = {"x": 10, "y": 20}
        assert rows == expected_rows
        assert state["observation"]["count"] == state["observation"]["eligible"] == 2
        assert state["observation"]["dropped"] == 0
        assert state["observation"]["helper_calls"] == 1


def test_native_behavior_batch(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI_INTENT")
    if not configured:
        pytest.skip("behavior batch requires explicit FDISBULL_QEMU_AGI_INTENT")
    binary = Path(configured).expanduser().resolve()
    expected = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256", "")
    assert len(expected) == 64 and all(c in "0123456789abcdef" for c in expected), \
        "An explicit lowercase FDISBULL_QEMU_AGI_EXPECTED_SHA256 is required"
    assert binary.is_file() and os.access(binary, os.X_OK), "Candidate must be executable"
    evidence = Path(os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE", tmp_path)).resolve()
    assert evidence.is_dir(), "Evidence directory must already exist"
    batch = Batch(binary, expected, evidence)
    failure = None
    try:
        behavior_bundle(batch, "binding")
        behavior_bundle(batch, "intent")
        atomic_fault(batch, "invalid-actor", (70, 16), "invalid_actor", 3)
        atomic_fault(batch, "unbound-draw", (35, 1), "view_unbound", 10)
        prior_profile(batch, "scalar")
        prior_profile(batch, "binding")
        with pytest.raises(HarnessError):
            with batch.launch("intent-without-catalog", b"\0", profile="scalar", reject=True,
                              extra_args=("-M", "agi-test,draw-intent=on")):
                pytest.fail("Intent without a catalog was admitted")
        with pytest.raises(HarnessError, match="(?i)(catalog|FDBAGIV1)"):
            with batch.launch("bad-catalog-magic", b"\0", profile="binding", reject=True,
                              catalog=b"BADMAGIC" + CATALOG[8:]):
                pytest.fail("Malformed catalog was admitted")
        # These are completion guards; the receipt records measured lists/counts.
        assert len(batch.children) == LIMITS["children"]
        assert len(batch.runs) == LIMITS["runs"]
        assert all(row["outcome"] in {"passed", "rejected"} for row in batch.children)
    except BaseException as error:
        failure = error
        raise
    finally:
        batch.finish(failure)
