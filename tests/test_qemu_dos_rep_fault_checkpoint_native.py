"""Cold QEMU restore at a protected-mode REP partial-fault boundary.

The authored COM fixture stops at its #GP handler after copying ``AB``. This
test saves the stopped machine, closes it, restores into a fresh session, then
lets the handler widen DS and retry the remaining REP MOVSB iterations.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from support.rep_fault_fixture import (
    COMPLETED_ECX,
    COMPLETED_EDI,
    COMPLETED_ESI,
    COMPLETION_MARKER_VALUE,
    DESTINATION_OFFSET,
    FAULT_ECX,
    FAULT_EDI,
    FAULT_ESI,
    FAULT_MARKER_VALUE,
    FAULT_PREFIX_DWORD,
    LIMITED_DATA_SELECTOR,
    WIDE_DATA_SELECTOR,
    build,
)
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record


def _number(value):
    if isinstance(value, str):
        return int(value, 0) if value.lower().startswith("0x") else int(value, 16)
    return int(value)


def _reg(registers, *names):
    sources = [registers]
    sources.extend(registers.get(key, {}) for key in ("general", "segments", "registers")
                   if isinstance(registers.get(key), dict))
    for name in names:
        for values in sources:
            if name in values:
                return _number(values[name])
    raise AssertionError((names, registers))


def _dword(data):
    return int.from_bytes(data, "little")


def _read(debug, address, length):
    raw = bytes.fromhex(debug.memory(address, length=length, space="physical")["hex"])
    assert len(raw) == length
    return raw


def _fault_state(debug, info, labels):
    registers = debug.registers()
    assert registers["cpu_mode"] == "protected", registers
    assert _reg(registers, "cs") == 8, registers
    assert _reg(registers, "ds") == LIMITED_DATA_SELECTOR, registers
    ds = registers["address_state"]["segments"]["ds"]
    assert _number(ds["limit"]) == 0xFFFF, ds
    assert _number(registers["instruction_pointer"]) == labels["gp_handler"], registers
    assert _reg(registers, "ecx", "cx", "rcx") & 0xFFFFFFFF == FAULT_ECX, registers
    assert _reg(registers, "esi", "si", "rsi") & 0xFFFFFFFF == FAULT_ESI, registers
    assert _reg(registers, "edi", "di", "rdi") & 0xFFFFFFFF == FAULT_EDI, registers

    psp = _reg(info, "psp_segment") & 0xFFFF
    esp = _reg(registers, "esp", "sp", "rsp") & 0xFFFFFFFF
    frame = _read(debug, psp * 16 + esp, 16)
    assert _dword(frame[0:4]) == 0
    assert _dword(frame[4:8]) == labels["rep_ip"]
    assert _dword(frame[8:12]) == 8

    buffer_base = _dword(_read(debug, psp * 16 + labels["buffer_base"], 4))
    destination = _read(debug, buffer_base + DESTINATION_OFFSET, 4)
    assert _dword(destination) == FAULT_PREFIX_DWORD
    assert _dword(_read(debug, psp * 16 + labels["fault_marker"], 4)) == 0
    assert _dword(_read(debug, psp * 16 + labels["completion_marker"], 4)) == 0
    return dict(frame=frame, destination=destination, psp=psp,
                buffer_base=buffer_base, registers=registers)


def _qemu_options(runtime, disk, checkpoint_tool):
    return launch_options({
        "executable": str(runtime["qemu"]),
        "mcopy": os.environ["FDISBULL_QEMU_DOS_MCOPY"],
        "firmware": runtime["firmware"],
    }, disk, qemu_checkpoint_tool=str(checkpoint_tool))


def test_qemu_rep_partial_fault_checkpoint_cold_restore_and_retry(paired_runtime, tmp_path):
    checkpoint_value = os.environ.get("FDISBULL_QEMU_IMG")
    if not checkpoint_value:
        pytest.skip("FDISBULL_QEMU_IMG is required for cold restore")
    checkpoint_tool = Path(checkpoint_value).expanduser().resolve(strict=True)
    assert checkpoint_tool.is_file() and os.access(checkpoint_tool, os.X_OK), checkpoint_tool

    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode COM fixture")

    code, labels = build(tmp_path / "fixture", nasm, checkpoint_safe=True)
    source = tmp_path / "REPFAULT.COM"
    source.write_bytes(code)
    database = tmp_path / "rep-fault-checkpoint.fdb"
    options = _qemu_options(paired_runtime, paired_runtime["disk"], checkpoint_tool)

    with Project.create(database, source, image="com") as project:
        project.analyze(max_instructions=256)
        first_dir = tmp_path / "qemu-before-restore"
        first_dir.mkdir()
        (first_dir / source.name).write_bytes(code)
        with project.debugger(str(paired_runtime["qemu"]), first_dir,
                              **options) as debug:
            info = process_record(debug)
            allocation = info["allocation"]
            psp_base = _number(info["psp_segment"]) * 16
            assert _number(allocation["start"]) == psp_base, allocation
            assert _number(allocation["end"]) >= psp_base + 0x10002, allocation
            handler_bp = debug.breakpoint(com_address(info, labels["gp_handler"]))
            stopped = debug.run(timeout_ms=15000)
            assert stopped["outcome"] == "breakpoint", stopped
            assert handler_bp["breakpoint_id"] in stopped["session"]["stop_reason"][
                "breakpoint_ids"], stopped

            before = _fault_state(debug, info, labels)
            assert _number(before["registers"]["address_state"]["segments"]["ds"]["limit"]) == 0xFFFF

            # User breakpoints are not part of the machine checkpoint contract.
            # Remove the #GP stop breakpoint while preserving the stopped CPU
            # at the first handler instruction.
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            saved = debug.save_state()
            artifact = saved["artifact"]
            assert project.debug_state_info(artifact)["sha256"] == saved["sha256"]
            old_owner = debug.vm.process
            old_run = debug.run_id
        assert old_owner.poll() is not None

    with Project(database) as project:
        assert project.debug_state_info(artifact)["sha256"] == saved["sha256"]
        restored_dir = tmp_path / "qemu-after-restore"
        restored_dir.mkdir()
        (restored_dir / source.name).write_bytes(code)
        with project.debugger(str(paired_runtime["qemu"]), restored_dir,
                              **options) as debug:
            fresh_owner = debug.vm.process
            fresh_run = debug.run_id
            assert fresh_run != old_run
            restored = debug.load_state(artifact)
            assert restored["source_binding_restored"] is True, restored
            assert fresh_owner.poll() is not None
            assert debug.vm.process is not fresh_owner
            assert debug.vm.process is not old_owner
            assert debug.dos_process_info()["state"] == "active"

            info = debug.dos_process_info()
            after_restore = _fault_state(debug, info, labels)
            assert after_restore["frame"] == before["frame"]
            assert after_restore["destination"] == b"AB\0\0"

            # The checkpoint is at the first handler opcode (CLI). Step that
            # opcode before arming a persistent handler breakpoint, so a later
            # second #GP is observable rather than confused with the restored
            # initial handler entry.
            first_handler_step = debug.step(timeout_ms=5000)
            assert first_handler_step["outcome"] == "step", first_handler_step
            assert _number(debug.registers()["instruction_pointer"]) == labels["gp_handler"] + 1
            handler_guard = debug.breakpoint(com_address(info, labels["gp_handler"]))
            completion_bp = debug.breakpoint(com_address(info, labels["completion_stop"]))
            resumed = debug.run(timeout_ms=15000)
            assert resumed["outcome"] == "breakpoint", resumed
            assert completion_bp["breakpoint_id"] in resumed["session"]["stop_reason"][
                "breakpoint_ids"], (
                    "REP faulted again after cold restore instead of completing once",
                    resumed,
                )
            assert handler_guard["breakpoint_id"] not in resumed["session"]["stop_reason"][
                "breakpoint_ids"], resumed

            complete = debug.registers()
            assert complete["cpu_mode"] == "protected", complete
            assert _number(complete["instruction_pointer"]) == labels["completion_stop"], complete
            assert _reg(complete, "ds") == WIDE_DATA_SELECTOR, complete
            metadata_base = _reg(info, "psp_segment") * 16
            fields = {
                name: _dword(_read(debug, metadata_base + labels[name], 4))
                for name in (
                    "fault_error", "fault_eip", "fault_cs", "fault_eflags",
                    "fault_ecx", "fault_esi", "fault_edi", "fault_destination",
                    "fault_marker", "final_ecx", "final_esi", "final_edi",
                    "completion_marker",
                )
            }
            buffer_base = _dword(_read(debug, metadata_base + labels["buffer_base"], 4))
            assert fields["fault_error"] == 0, fields
            assert fields["fault_eip"] == labels["rep_ip"], fields
            assert fields["fault_cs"] == 8, fields
            assert fields["fault_ecx"] == FAULT_ECX, fields
            assert fields["fault_esi"] == FAULT_ESI, fields
            assert fields["fault_edi"] == FAULT_EDI, fields
            assert fields["fault_destination"] == FAULT_PREFIX_DWORD, fields
            assert fields["fault_marker"] == FAULT_MARKER_VALUE, fields
            assert fields["final_ecx"] == COMPLETED_ECX, fields
            assert fields["final_esi"] == COMPLETED_ESI, fields
            assert fields["final_edi"] == COMPLETED_EDI, fields
            assert fields["completion_marker"] == COMPLETION_MARKER_VALUE, fields
            assert _read(debug, buffer_base + DESTINATION_OFFSET, 4) == b"ABCD"
            assert source.read_bytes() == code
