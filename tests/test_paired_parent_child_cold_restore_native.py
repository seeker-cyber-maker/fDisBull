"""Paired cold restore while an EXEC child is current under a selected parent.

This opt-in witness compares only common authored-program outcomes across
DOSBox-X and QEMU. It does not compare native checkpoint bytes or engine APIs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import (
    digest,
    nested_exec,
    prepare_dos_baseline,
    write_image_files,
)
from test_qemu_dosbox_parity_native import (
    _exit_code,
    _memory_bytes,
    _qemu_launch_options,
    _word,
    parity_inputs,
)


REQUIRE = "FDISBULL_REQUIRE_PAIRED_PARENT_CHILD_COLD_RESTORE"
CHILD_KEY = "k"
CHILD_EXIT = 37
PARENT_EXIT = 17
CHILD_PROGRAM = bytes.fromhex(
    # Poll BIOS keyboard, consume exactly one key, return 37 for 'k'.
    "b401cd1674fab400cd163c6b7505b8254ccd21b87f4ccd21"
)
PARENT_MARKER = b"\xef\xbe"


def _segment(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _launch(project, runtime, game, *, qemu):
    if qemu:
        options = _qemu_launch_options(runtime)
        options["qemu_checkpoint_tool"] = str(runtime["checkpoint_tool"])
        options["qemu_clock"] = "virtual"
        return project.debugger(str(runtime["qemu"]), game, **options)
    return project.debugger(str(runtime["dosbox"]), game)


@pytest.fixture
def cold_restore_inputs(request, monkeypatch):
    monkeypatch.setenv("FDISBULL_REQUIRE_QEMU_DOS_OS", "1")
    runtime = request.getfixturevalue("parity_inputs")
    firmware = os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE")
    checkpoint_tool = os.environ.get("FDISBULL_QEMU_IMG") or shutil.which("qemu-img")
    if not firmware:
        pytest.fail("FDISBULL_QEMU_DOS_FIRMWARE is required for checkpoint restore")
    if not checkpoint_tool:
        pytest.fail("Set FDISBULL_QEMU_IMG or install qemu-img for checkpoint restore")
    runtime["checkpoint_tool"] = Path(checkpoint_tool).expanduser().resolve(strict=True)
    runtime["firmware"] = Path(firmware).expanduser().resolve(strict=True)
    assert runtime["firmware"].is_dir()
    runtime["boot_sha256"] = hashlib.sha256(runtime["boot_image"].read_bytes()).hexdigest()
    return runtime


@pytest.mark.skipif(os.environ.get(REQUIRE) != "1",
                    reason=f"Set {REQUIRE}=1 with pinned DOSBox-X/QEMU inputs")
def test_paired_cold_restore_preserves_selected_parent_with_child_current(
        tmp_path, cold_restore_inputs):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.fail(f"Set NASM or install nasm for {REQUIRE}=1")

    parent_code, symbols = nested_exec(tmp_path, nasm)
    parent_path = tmp_path / "PARENT.COM"
    child_path = tmp_path / "CHILD.COM"
    parent_path.write_bytes(parent_code)
    child_path.write_bytes(CHILD_PROGRAM)
    source_sha256 = hashlib.sha256(parent_code).hexdigest()

    boot_dir = tmp_path / "cold-boot"
    boot_dir.mkdir()
    boot = prepare_dos_baseline(
        cold_restore_inputs["boot_image"], boot_dir / "baseline.img",
        cold_restore_inputs["mcopy"])
    write_image_files(boot["image"], boot_dir / "child-overlay",
                      cold_restore_inputs["mcopy"], {"CHILD.COM": CHILD_PROGRAM})
    boot["prepared_sha256"] = digest(boot["image"])
    runtime = dict(cold_restore_inputs, boot=boot)

    database = tmp_path / "parent-child-cold.fdb"
    with Project.create(database, parent_path, image="com") as project:
        project.analyze(max_instructions=128)
        common_results = {}

        for backend in ("dosbox", "qemu-dos"):
            qemu = backend == "qemu-dos"
            game = tmp_path / f"game-{backend}"
            game.mkdir()
            (game / "PARENT.COM").write_bytes(parent_code)
            (game / "CHILD.COM").write_bytes(CHILD_PROGRAM)

            # Keep the launched parent selected while reaching a deterministic
            # child entry stop. A guest-time stop may land inside BIOS INT 16h,
            # where CS is the BIOS segment even though DS still identifies the
            # child PSP.
            with _launch(project, runtime, game, qemu=qemu) as debug:
                parent_psp = _word(debug.registers(), "ds")
                if qemu:
                    selected = debug.dos_process_info()
                    assert selected["state"] == "active", selected
                    assert _segment(selected["psp_segment"]) == parent_psp, selected

                if qemu:
                    stopped = debug.run(timeout_ms=1_000)
                    assert stopped["outcome"] == "timeout", stopped
                else:
                    stopped = debug.run(
                        timeout_ms=10_000, guest_ms=100, fast_forward=True)
                    assert stopped["outcome"] == "guest_time", stopped
                child_registers = debug.registers()
                child_psp = _word(child_registers, "ds")
                assert child_psp != parent_psp

                # Use a raw guest address rather than a source-mapped
                # breakpoint: this is the EXEC child's PSP:0100 entry.
                if qemu:
                    child_entry_bp = debug.breakpoint(16 * child_psp + 0x100)
                else:
                    child_entry_bp = debug.call("breakpoints.create", {
                        "kind": "execution", "once": False,
                            "address": {"space": "segmented", "segment": f"0x{child_psp:04X}",
                                        "offset": "0x00000100"},
                    })
                at_child_entry = debug.run(
                    timeout_ms=10_000,
                    **({} if qemu else {"fast_forward": True}))
                assert at_child_entry["outcome"] == "breakpoint", at_child_entry
                debug.delete_breakpoint(child_entry_bp["breakpoint_id"])
                child_registers = debug.registers()
                assert (_word(child_registers, "cs"),
                        _word(child_registers, "ip", "instruction_pointer")) == (
                            child_psp, 0x100)

                saved = debug.save_state()
                artifact_id = saved["artifact"]
                row = project.db.execute(
                    "SELECT sha256,metadata FROM debug_artifacts WHERE id=?",
                    (artifact_id,)).fetchone()
                assert row is not None
                metadata = json.loads(row["metadata"])
                if not qemu:
                    identity = metadata.get("dos_process_identity")
                    assert identity and identity["psp"] == parent_psp
                    assert identity["sha256"] == row["sha256"]
                owner = debug.rpc.process if not qemu else debug.vm.process

            assert owner.poll() is not None, (backend, owner.returncode)

            # A new debugger owner opens the same compatible project/runtime,
            # then restores the parent-selected snapshot with the child current.
            with _launch(project, runtime, game, qemu=qemu) as restored:
                bootstrap_owner = restored.rpc.process if not qemu else restored.vm.process
                loaded = restored.load_state(artifact_id)
                restored_owner = restored.rpc.process if not qemu else restored.vm.process
                if qemu:
                    assert bootstrap_owner.poll() is not None
                    selected = restored.dos_process_info()
                    assert selected["state"] == "active", selected
                    assert _segment(selected["psp_segment"]) == parent_psp, selected
                else:
                    assert loaded.get("dos_process_identity_bound") is True, loaded

                restored_registers = restored.registers()
                restored_child_psp = _word(restored_registers, "ds")
                assert restored_child_psp == child_psp
                assert _word(restored_registers, "cs") == child_psp
                assert 0x100 <= _word(restored_registers, "ip", "instruction_pointer") < 0x106

                if qemu:
                    parent_breakpoint_address = 16 * parent_psp + symbols["after_child_ip"]
                else:
                    parent_breakpoint_address = (
                        restored.static_base + symbols["after_child_ip"] - 0x100)
                parent_breakpoint = restored.breakpoint(parent_breakpoint_address)

                # The child exits only after consuming 'k'. If its exit is
                # misattributed to the selected parent, this cannot reach the
                # parent's after-child breakpoint.
                key_receipt = restored.keyboard_press(CHILD_KEY, hold_ms=40, gap_ms=40)
                assert key_receipt
                at_parent = restored.run(
                    timeout_ms=10_000,
                    **({} if qemu else {"fast_forward": True}))
                assert at_parent["outcome"] == "breakpoint", at_parent
                parent_registers = restored.registers()
                assert (_word(parent_registers, "cs"),
                        _word(parent_registers, "ip", "instruction_pointer")) == (
                            parent_psp, symbols["after_child_ip"])
                parent_base = parent_psp * 16
                assert _memory_bytes(
                    restored, parent_base + symbols["child_status_ip"], 2,
                    qemu=qemu) == bytes((CHILD_EXIT, 0))
                assert _memory_bytes(
                    restored, parent_base + symbols["marker_ip"], 2,
                    qemu=qemu) == PARENT_MARKER
                if qemu:
                    assert restored.dos_process_info()["state"] == "active"
                    schedule = restored.input_schedule_observe()
                    assert schedule["state"] in ("cancelled", "dispatched"), schedule
                    if schedule["state"] == "cancelled":
                        cancelled = restored.input_cancel_pending()
                        for lease in cancelled["retained_dispatched_holds"]:
                            restored.keyboard_key_up(lease)
                else:
                    status = restored.call("session.status")
                    assert status["state"] == "stopped", status

                restored.delete_breakpoint(parent_breakpoint["breakpoint_id"])
                parent_exit = restored.run(
                    timeout_ms=10_000,
                    **({} if qemu else {"fast_forward": True}))
                assert _exit_code(parent_exit, qemu=qemu) == PARENT_EXIT
                if qemu:
                    final_process = restored.dos_process_info()
                    assert _segment(final_process["psp_segment"]) == parent_psp
                else:
                    info = parent_exit["session"]["stop_reason"]["guest_exit"]
                    assert _segment(info["psp"]) == parent_psp
                final_owner = restored.rpc.process if not qemu else restored.vm.process
                common_results[backend] = dict(
                    child_key=ord(CHILD_KEY), child_exit=CHILD_EXIT,
                    parent_marker=int.from_bytes(PARENT_MARKER, "little"),
                    parent_exit=PARENT_EXIT, parent_psp_preserved=True)

            assert restored_owner.poll() is not None
            assert final_owner.poll() is not None

        assert common_results["dosbox"] == common_results["qemu-dos"]
    assert parent_path.read_bytes() == parent_code
    assert child_path.read_bytes() == CHILD_PROGRAM
    assert hashlib.sha256(parent_path.read_bytes()).hexdigest() == source_sha256
    assert digest(cold_restore_inputs["boot_image"]) == cold_restore_inputs["boot_sha256"]
    assert digest(boot["image"]) == boot["prepared_sha256"]
