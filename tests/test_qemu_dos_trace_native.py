"""Native source-bound DOS observations over independently authored programs.

These tests execute a caller-supplied FreeDOS disk with stock QEMU. The small
COM/MZ inputs below belong to the tests; no vendor program enters the repository.
Native debugger stop intervals are deliberately not called retired instructions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, mz_exit, prepare_dos_baseline
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, live_word, number, process_disk,
    process_record, process_runtime, read_bytes,
)


@pytest.fixture(scope="module")
def shifted_process_disk(process_runtime, tmp_path_factory):
    """Use more real DOS buffers so the selected program loads elsewhere."""
    directory = tmp_path_factory.mktemp("native-dos-trace-shifted-baseline")
    config = BASELINE_CONFIG.replace(b"BUFFERS=20\r\n", b"BUFFERS=60\r\n")
    assert config != BASELINE_CONFIG
    return prepare_dos_baseline(
        process_runtime["boot_image"], directory / "dos-baseline.img",
        process_runtime["mcopy"], config=config,
    )


def trace_document(project, artifact, directory):
    destination = directory / (artifact + ".json")
    project.debug_export(artifact, destination)
    return json.loads(destination.read_text())


def control_program():
    """Known COM PCs: MOV 100, store 103, INC 106, JMP 107, NOP 10b."""
    # The store's destination at 0130h is data, separate from instruction bytes.
    return bytes.fromhex("b80700a3300140eb02909090ebfe").ljust(0x32, b"\0")


def assert_no_retirement_claim(document):
    assert document["observation_contract"]["backend"] == "qemu-dos"
    assert document["events"]
    assert all(event["observation"]["registers_stage"] == "before-instruction"
               and event["observation"]["instruction_completed"] is not True
               for event in document["events"])


def test_native_source_predicates_observe_registers_before_effects_and_branches(
        tmp_path, process_runtime, process_disk):
    source = control_program()
    binary, project = create_project(tmp_path, source)
    database = project.path
    with project:
        static_base = project.regions(1)[0].start
        with project.debugger(process_runtime["executable"], tmp_path,
                              **launch_options(process_runtime, process_disk)) as debug:
            info = process_record(debug)
            sentinel = com_address(info, 0x130)
            initial = debug.trace_until(
                {"kind": "register", "register": "ip", "equals": 0x100},
                name="initial.json", max_steps=5)
            assert initial["outcome"] == "predicate", initial
            assert initial["matched"] and initial["exact_stop"]
            assert initial["steps"] == initial["attempted_steps"] == 0
            assert number(debug.registers()["instruction_pointer"]) == 0x100

            changed = debug.trace_until(
                {"kind": "register", "register": "ax", "equals": 7},
                name="ax-seven.json", max_steps=5)
            assert changed["outcome"] == "predicate", changed
            assert changed["matched"] and changed["exact_stop"]
            assert changed["steps"] == 1 and changed["source_window_closed"]
            assert number(debug.registers()["instruction_pointer"]) == 0x103
            assert read_bytes(debug, sentinel, 2) == b"\0\0"
            assert changed["matched_event"]["pc"]["project"] == static_base + 3

            regions = [dict(id="setup", space="project", start=static_base,
                            end=static_base + 6),
                       dict(id="body", space="project", start=static_base + 6,
                            end=static_base + 14)]
            region = debug.trace_until({"kind": "region-change"}, regions=regions,
                                       name="region.json", max_steps=5)
            assert region["outcome"] == "predicate" and region["steps"] == 1, region
            assert region["matched_event"]["region"]["id"] == "body"
            assert number(debug.registers()["instruction_pointer"]) == 0x106
            assert read_bytes(debug, sentinel, 2) == b"\x07\0"

            branch = debug.trace_until({"kind": "nonsequential"},
                                       name="branch.json", max_steps=5)
            assert branch["outcome"] == "predicate" and branch["steps"] == 2, branch
            assert branch["matched_event"]["pc"]["project"] == static_base + 11
            assert number(debug.registers()["instruction_pointer"]) == 0x10b
            assert live_word(debug.registers(), "rax", "eax", "ax") == 8
            mnemonic = debug.trace_until({"kind": "mnemonic", "equals": "nop"},
                                         name="mnemonic.json", max_steps=0)
            assert mnemonic["matched"] and mnemonic["steps"] == 0, mnemonic

            budget = debug.trace_until(
                {"kind": "register", "register": "ax", "equals": 99},
                name="budget.json", max_steps=3)
            assert budget["outcome"] == "step_budget" and budget["steps"] == 3, budget
            assert not budget["matched"] and not budget["exact_stop"]
            assert budget["source_window_closed"]

        # Saved queries must continue working after the VM/process epoch closes.
        historical = project.event_trace_query(
            changed["trace_artifact"],
            predicate={"kind": "register", "register": "ax", "equals": 7})
        assert historical["matched_count"] == 1, historical
        assert historical["rows"][0]["pc"]["project"] == static_base + 3
        assert historical["rows"][0]["pc"]["linear"] == com_address(info, 0x103)
        document = trace_document(project, changed["trace_artifact"], tmp_path)
        assert_no_retirement_claim(document)
        assert len(document["events"]) == 2 and document["window"]["closed"]
        assert document["events"][0]["observation"]["instruction_completed"] is None
        assert document["events"][1]["observation"]["instruction_completed"] is False
    with Project(database) as reopened:
        assert reopened.event_trace_query(
            changed["trace_artifact"],
            predicate={"kind": "register", "register": "ax", "equals": 7}) == historical
    assert binary.read_bytes() == source


@pytest.mark.parametrize("action", [
    {"op": "click", "x": 20, "y": 20},
    {"op": "keyboard.press", "key": "a"},
], ids=["mouse", "keyboard"])
def test_native_source_trace_rejects_queued_actions_before_initial_match(
        action, tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, control_program())
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        before = debug.registers()
        artifacts_before = project.db.execute("SELECT count(*) FROM debug_artifacts").fetchone()[0]
        with pytest.raises(ValueError, match="queued input"):
            debug.trace_until({"kind": "register", "register": "ip", "equals": 0x100},
                              action=action, max_steps=1)
        assert debug.registers() == before
        assert project.db.execute("SELECT count(*) FROM debug_artifacts").fetchone()[0] == artifacts_before


def test_native_source_count_trace_keeps_linear_addresses_and_count_steps(
        tmp_path, process_runtime, process_disk):
    source = bytes.fromhex("b807004090ebfe")  # MOV AX,7; INC AX; NOP; JMP $.
    binary, project = create_project(tmp_path, source)
    with project:
        static_base = project.regions(1)[0].start
        with project.debugger(process_runtime["executable"], tmp_path,
                              **launch_options(process_runtime, process_disk)) as debug:
            info = process_record(debug)
            trace = debug.trace("count.json", count=2, timeout_ms=3000)
            assert trace["metadata"]["complete"], trace
            assert number(debug.registers()["instruction_pointer"]) == 0x104
            assert live_word(debug.registers(), "rax", "eax", "ax") == 8
        document = trace_document(project, trace["artifact"], tmp_path)
        assert document["complete"] and document["requested_count"] == 2
        assert len(document["events"]) == 2
        assert [number(item["address"]) for item in document["events"]] == [
            com_address(info, 0x100), com_address(info, 0x103)]
        assert [item["bytes"] for item in document["events"]] == ["b80700", "40"]
        assert [number(item["project_address"]) for item in document["events"]] == [
            static_base, static_base + 3]
        assert document["collector"]["steps"] == document["collector"]["attempted_steps"] == 2
        assert_no_retirement_claim(document)
        assert all(item["observation"]["instruction_completed"] is None
                   for item in document["events"])
        query = project.event_trace_query(trace["artifact"],
            predicate={"kind": "register", "register": "ax", "equals": 7})
        assert query["matched_count"] == 1 and query["rows"][0]["pc"]["project"] == static_base + 3
    assert binary.read_bytes() == source


def test_native_cross_run_register_search_uses_source_sites_and_survives_reopening(
        tmp_path, process_runtime, process_disk, shifted_process_disk):
    # PSP:0082h is the first non-space argument character. Every trial executes
    # the same bytes, but DOS supplies A or B through its real command tail.
    source = bytes.fromhex("31c0a0820090ebfe")  # XOR AX,AX; MOV AL,[82]; NOP; JMP $.
    binary, project = create_project(tmp_path, source)
    database = project.path
    traces, runtime_bases = {}, {}
    with project:
        static_base = project.regions(1)[0].start
        for label, disk, argument in (("A1", process_disk, " A"),
                                      ("A2", shifted_process_disk, " A"),
                                      ("B", shifted_process_disk, " B")):
            with project.debugger(process_runtime["executable"], tmp_path,
                    **launch_options(process_runtime, disk, dos_arguments=argument)) as debug:
                runtime_bases[label] = number(debug.registers()["linear_pc"])
                result = debug.trace_until(
                    {"kind": "pc-range", "space": "project",
                     "start": static_base + 6, "end": static_base + 7},
                    max_steps=4, timeout_ms=3000, name=label + ".json", label=label)
                assert result["outcome"] == "predicate" and result["steps"] == 3, result
                assert result["matched_event"]["registers"]["rax"] & 0xffff == ord(argument[-1])
                traces[label] = result["trace_artifact"]
        assert runtime_bases["A1"] != runtime_bases["A2"], runtime_bases
        selection = {"kind": "pc-range", "space": "project",
                     "start": static_base + 5, "end": static_base + 8}
        register_search = project.event_search_start(
            traces["A1"], feature="register-value", registers=["ax"],
            predicate=selection, label="A1")
        sites = project.event_search_start(traces["A1"], predicate=selection, label="A1")
        ancestor = project.event_search_results(register_search["artifact"])
        for label, mode in (("A2", "retain"), ("B", "exclude")):
            register_search = project.event_search_refine(
                register_search["artifact"], traces[label], mode=mode,
                predicate=selection, label=label)
            sites = project.event_search_refine(
                sites["artifact"], traces[label], mode=mode,
                predicate=selection, label=label)
        saved = project.event_search_results(register_search["artifact"])
        assert saved["candidate_count"] == 2, saved
        assert {row["site"]["address"] for row in saved["rows"]} == {static_base + 5, static_base + 6}
        assert all(row["register"] == "ax" and row["value"] == ord("A")
                   and row["support_trials"] == 2 for row in saved["rows"])
        assert project.event_search_results(sites["artifact"])["candidate_count"] == 0
        assert [item["artifact"] for item in saved["trace_references"]] == list(traces.values())
        assert project.event_search_results(ancestor["search_artifact"]) == ancestor
    with Project(database) as reopened:
        assert reopened.event_search_results(register_search["artifact"]) == saved
    assert binary.read_bytes() == source


def test_native_mz_relocated_operands_share_canonical_source_instruction_identity(
        tmp_path, process_runtime, process_disk, shifted_process_disk):
    source, fixture = mz_exit()
    binary, project = create_project(tmp_path, source, mz=True)
    traces, segments, documents = [], [], []
    with project:
        static_base = project.regions(1)[0].start
        for index, disk in enumerate((process_disk, shifted_process_disk)):
            with project.debugger(process_runtime["executable"], tmp_path,
                                  **launch_options(process_runtime, disk)) as debug:
                before = debug.registers()
                load_segment = live_word(before, "cs") - fixture["relative_cs"]
                segments.append(load_segment)
                result = debug.trace_until(
                    {"kind": "pc-range", "space": "project",
                     "start": static_base + 0x24, "end": static_base + 0x25},
                    max_steps=4, timeout_ms=3000, name=f"mz-{index}.json")
                assert result["outcome"] == "predicate" and result["steps"] == 2, result
                assert live_word(debug.registers(), "rax", "eax", "ax") == load_segment + 7
                assert result["matched_event"]["pc"]["project"] == static_base + 0x24
                traces.append(result["trace_artifact"])
            document = trace_document(project, traces[-1], tmp_path)
            assert_no_retirement_claim(document)
            assert [number(item["address"]) for item in document["events"]] == [
                load_segment * 16 + offset for offset in (0x20, 0x21, 0x24)]
            assert document["events"][1]["bytes"] == (b"\xb8" + struct.pack("<H", load_segment + 7)).hex()
            documents.append(document)
        assert segments[0] != segments[1], segments
        assert documents[0]["events"][1]["bytes"] != documents[1]["events"][1]["bytes"]
        selected = {"kind": "pc-range", "space": "project",
                    "start": static_base + 0x21, "end": static_base + 0x24}
        search = project.event_search_start(traces[0], predicate=selected)
        retained = project.event_search_refine(search["artifact"], traces[1], predicate=selected)
        rows = project.event_search_results(retained["artifact"])["rows"]
        assert len(rows) == 1 and rows[0]["site"]["address"] == static_base + 0x21, rows
        # The project's MZ image has already applied relocations at its static
        # load segment. Its canonical instruction differs from the raw file.
        canonical = b"\xb8" + struct.pack("<H", (static_base // 16) + 7)
        assert rows[0]["site"]["instruction_sha256"] == hashlib.sha256(canonical).hexdigest()
        assert rows[0]["support_trials"] == 2
    assert binary.read_bytes() == source


def test_native_source_trace_preserves_foreign_breakpoint_before_predicate(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, control_program())
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        point = debug.breakpoint(com_address(info, 0x103))
        before = deepcopy(debug.breakpoints)
        stopped = debug.trace_until(
            {"kind": "register", "register": "ax", "equals": 7}, max_steps=5)
        assert stopped["outcome"] == "foreign_stop" and not stopped["matched"], stopped
        assert not stopped["source_window_closed"]
        assert number(debug.registers()["instruction_pointer"]) == 0x103
        assert debug.breakpoints == before
        assert read_bytes(debug, com_address(info, 0x130), 2) == b"\0\0"
        debug.delete_breakpoint(point["breakpoint_id"])
        match = debug.trace_until(
            {"kind": "register", "register": "ax", "equals": 7}, max_steps=0)
        assert match["outcome"] == "predicate" and match["steps"] == 0, match


def test_native_self_modified_boundary_keeps_raw_pc_without_stale_source_site(
        tmp_path, process_runtime, process_disk):
    # MOV BYTE [105h],90h replaces the following INT3 with NOP before reaching it.
    source = bytes.fromhex("c606050190ccebfe")
    binary, project = create_project(tmp_path, source)
    with project:
        static_base = project.regions(1)[0].start
        with project.debugger(process_runtime["executable"], tmp_path,
                              **launch_options(process_runtime, process_disk)) as debug:
            info = process_record(debug)
            stopped = debug.trace_until(
                {"kind": "pc-range", "space": "project",
                 "start": static_base + 5, "end": static_base + 6},
                max_steps=3, timeout_ms=3000)
            assert stopped["outcome"] == "source_boundary" and stopped["steps"] == 1, stopped
            assert not stopped["matched"] and not stopped["source_window_closed"]
            assert number(debug.registers()["instruction_pointer"]) == 0x105
            assert read_bytes(debug, com_address(info, 0x105), 1) == b"\x90"
            document = trace_document(project, stopped["trace_artifact"], tmp_path)
            assert len(document["events"]) == 2 and not document["window"]["closed"]
            boundary = document["events"][-1]
            assert number(boundary["address"]) == com_address(info, 0x105)
            assert boundary["project_address"] is None
            assert boundary["source_qualification"]["qualified"] is False
            assert boundary["observation"]["instruction_completed"] is False
            assert_no_retirement_claim(document)
        raw = project.event_trace_query(stopped["trace_artifact"], predicate={
            "kind": "pc-range", "space": "linear",
            "start": com_address(info, 0x105), "end": com_address(info, 0x106)})
        assert raw["matched_count"] == 1, raw
        assert raw["rows"][0]["pc"]["project"] is None and raw["rows"][0]["site"] is None
        assert not raw["complete"]
    assert binary.read_bytes() == source


def test_native_source_trace_stops_at_protected_mode_transition(
        tmp_path, process_runtime, process_disk):
    # MOV EAX,CR0; OR AL,1; MOV CR0,EAX enters PE with the existing 16-bit CS cache.
    # The test ends there: no DOS service or protected-mode program is invented.
    source = bytes.fromhex("0f20c00c010f22c090ebfe")
    _, project = create_project(tmp_path, source)
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        static_base = project.regions(1)[0].start
        stopped = debug.trace_until(
            {"kind": "pc-range", "space": "project",
             "start": static_base + 8, "end": static_base + 9},
            max_steps=5, timeout_ms=3000)
        assert stopped["outcome"] == "error" and stopped["steps"] == 3, stopped
        assert not stopped["matched"] and not stopped["source_window_closed"]
        assert "real-mode" in stopped["error"]["message"]
        assert debug.registers()["cpu_mode"] == "protected"
        document = trace_document(project, stopped["trace_artifact"], tmp_path)
        assert not document["window"]["closed"]
        assert [number(item["project_address"]) for item in document["events"]] == [
            static_base, static_base + 3, static_base + 5]
        assert_no_retirement_claim(document)


def test_native_source_trace_rechecks_dos_allocation_before_initial_predicate(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, control_program())
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        owner_address = number(info["allocation"]["mcb_segment"]) * 16 + 1
        original = read_bytes(debug, owner_address, 2)
        assert int.from_bytes(original, "little") == number(info["psp_segment"])
        debug.write_memory(owner_address, "0000", expected_hex=original.hex())
        stopped = debug.trace_until(
            {"kind": "register", "register": "ip", "equals": 0x100}, max_steps=1)
        assert stopped["outcome"] == "error" and not stopped["matched"], stopped
        assert stopped["attempted_steps"] == stopped["steps"] == 0
        assert "allocation ownership" in stopped["error"]["message"]
        assert number(debug.registers()["instruction_pointer"]) == 0x100
        document = trace_document(project, stopped["trace_artifact"], tmp_path)
        assert not document["events"] and not document["window"]["closed"]
