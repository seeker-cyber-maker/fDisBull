"""Native QEMU single-step boundaries for terminal REP cases.

All guest programs are authored here. These assertions use debugger stop state
and CPU/memory state to establish what one step executed; trace fetch records
alone do not certify instruction completion.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_qemu_dos_process_native import (
    com_address, launch_options, process_disk, process_record, process_runtime,
)


REP_IP = 0x10A
NEXT_IP = 0x10C
SOURCE_IP = 0x10E
DEST_IP = 0x111


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _word(registers, name):
    values = registers.get("general", registers.get("registers", {}))
    for key in (name, "e" + name, "r" + name):
        if key in values:
            return _number(values[key]) & 0xFFFF
    raise AssertionError((name, registers))


def _flags(registers):
    values = registers.get("general", registers.get("registers", {}))
    for key in ("eflags", "rflags", "flags"):
        if key in values:
            return _number(values[key]) & 0xFFFF
    raise AssertionError(("flags", registers))


def _state(debug, info, destination=DEST_IP):
    registers = debug.registers()
    memory = debug.memory(com_address(info, destination), length=3, space="physical")
    return dict(ip=_number(registers["instruction_pointer"]),
                cx=_word(registers, "cx"), si=_word(registers, "si"),
                di=_word(registers, "di"), flags=_flags(registers),
                destination=memory["hex"])


def _at_rep(debug, info):
    bp = debug.breakpoint(com_address(info, REP_IP))
    stopped = debug.run(timeout_ms=10000)
    assert stopped["outcome"] == "breakpoint", stopped
    debug.delete_breakpoint(bp["breakpoint_id"])


@pytest.mark.parametrize(("count", "expected"), [
    (0, dict(ip=NEXT_IP, cx=0, si=SOURCE_IP, di=DEST_IP,
             destination="000000")),
    (1, dict(ip=NEXT_IP, cx=0, si=SOURCE_IP + 1, di=DEST_IP + 1,
             destination="410000")),
    (3, dict(ip=NEXT_IP, cx=0, si=SOURCE_IP + 3, di=DEST_IP + 3,
             destination="414243")),
])
def test_qemu_rep_movsb_terminal_step_count_zero_one_and_three(
        tmp_path, process_runtime, process_disk, count, expected):
    # MOV SI,010Eh; MOV DI,0111h; MOV CX,count; CLD; REP MOVSB; JMP $;
    # The destination is zero-filled and source bytes are ABC.
    program = bytearray.fromhex("be0e01bf1101b90300fcf3a4ebfe414243000000")
    program[7:9] = count.to_bytes(2, "little")
    program = bytes(program)
    source = tmp_path / f"REP{count}.COM"
    source.write_bytes(program)
    with Project.create(tmp_path / f"rep{count}.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)
        qemu_dir = tmp_path / f"qemu{count}"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(program)
        with project.debugger(
            str(process_runtime["executable"]), qemu_dir,
            **launch_options(process_runtime, process_disk),
        ) as debug:
            info = process_record(debug)
            _at_rep(debug, info)
            before = _state(debug, info)
            assert {key: before[key] for key in ("ip", "cx", "si", "di", "destination")} == dict(
                ip=REP_IP, cx=count, si=SOURCE_IP, di=DEST_IP,
                destination="000000"), before

            for remaining in range(count - 1, 0, -1):
                step = debug.step(timeout_ms=5000)
                assert step["outcome"] == "step", step
                partial = _state(debug, info)
                assert partial["ip"] == REP_IP and partial["cx"] == remaining, partial
                copied = count - remaining
                assert partial["si"] == SOURCE_IP + copied, partial
                assert partial["di"] == DEST_IP + copied, partial
                assert partial["destination"] == (b"ABC"[:copied] + bytes(3 - copied)).hex(), partial
            step = debug.step(timeout_ms=5000)
            assert step["outcome"] == "step", step
            after = _state(debug, info)

        assert {key: after[key] for key in expected} == expected, after
        assert source.read_bytes() == program


def test_qemu_repe_cmpsb_stops_at_conditional_termination(tmp_path, process_runtime, process_disk):
    # MOV SI,010Eh; MOV DI,0111h; MOV CX,3; CLD; REPE CMPSB; JMP $;
    # Source ABC and destination AXC mismatch on comparison two.
    program = bytes.fromhex("be0e01bf1101b90300fcf3a6ebfe414243415843")
    source = tmp_path / "REPE.COM"
    source.write_bytes(program)
    with Project.create(tmp_path / "repe.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)
        qemu_dir = tmp_path / "qemu-repe"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(program)
        with project.debugger(
            str(process_runtime["executable"]), qemu_dir,
            **launch_options(process_runtime, process_disk),
        ) as debug:
            info = process_record(debug)
            _at_rep(debug, info)
            before = _state(debug, info)
            assert before["ip"] == REP_IP and before["cx"] == 3, before
            assert before["si"] == SOURCE_IP and before["di"] == DEST_IP, before

            first = debug.step(timeout_ms=5000)
            assert first["outcome"] == "step", first
            partial = _state(debug, info)
            assert partial["ip"] == REP_IP and partial["cx"] == 2, partial
            assert partial["si"] == SOURCE_IP + 1 and partial["di"] == DEST_IP + 1, partial
            assert partial["flags"] & 0x40, partial  # First comparison matched.
            second = debug.step(timeout_ms=5000)
            assert second["outcome"] == "step", second
            after = _state(debug, info)

    assert after["ip"] == NEXT_IP, after
    assert after["cx"] == 1 and after["si"] == SOURCE_IP + 2, after
    assert after["di"] == DEST_IP + 2, after
    assert after["flags"] & 0x40 == 0, after  # ZF clear on the mismatching compare.
    assert after["destination"] == "415843", after
    assert source.read_bytes() == program


def test_qemu_mid_rep_cross_session_cold_restore_resumes_remaining_iterations(
        tmp_path, process_runtime, process_disk):
    checkpoint_tool_value = os.environ.get("FDISBULL_QEMU_IMG")
    assert checkpoint_tool_value, "FDISBULL_QEMU_IMG is required for the cold-restore REP case"
    checkpoint_tool = Path(checkpoint_tool_value).expanduser().resolve(strict=True)
    assert checkpoint_tool.is_file() and os.access(checkpoint_tool, os.X_OK), checkpoint_tool

    program = bytes.fromhex("be0e01bf1101b90300fcf3a4ebfe414243000000")
    source = tmp_path / "REPCHECK.COM"
    source.write_bytes(program)
    database = tmp_path / "rep-checkpoint.fdb"
    with Project.create(database, source, image="com") as project:
        project.analyze(max_instructions=64)
        qemu_dir = tmp_path / "qemu-original"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(program)
        options = launch_options(process_runtime, process_disk,
                                qemu_checkpoint_tool=str(checkpoint_tool))
        with project.debugger(str(process_runtime["executable"]), qemu_dir,
                              **options) as debug:
            info = process_record(debug)
            _at_rep(debug, info)
            partial = debug.step(timeout_ms=5000)
            assert partial["outcome"] == "step", partial
            after_one = _state(debug, info)
            assert after_one["ip"] == REP_IP, after_one
            assert after_one["cx"] == 2 and after_one["si"] == SOURCE_IP + 1, after_one
            assert after_one["di"] == DEST_IP + 1, after_one
            assert after_one["destination"] == "410000", after_one
            saved = debug.save_state()
            artifact = saved["artifact"]
            old_owner = debug.vm.process
        assert old_owner.poll() is not None

    # Reopen the project and restore into a fresh native owner.
    with Project(database) as project:
        restored_dir = tmp_path / "qemu-restored"
        restored_dir.mkdir()
        (restored_dir / source.name).write_bytes(program)
        with project.debugger(str(process_runtime["executable"]), restored_dir,
                              **options) as debug:
            fresh_owner = debug.vm.process
            restored = debug.load_state(artifact)
            assert restored["source_binding_restored"] is True, restored
            assert old_owner.poll() is not None
            assert debug.vm.process is not fresh_owner
            info = debug.dos_process_info()
            after_restore = _state(debug, info)
            assert after_restore["ip"] == REP_IP, after_restore
            assert after_restore["cx"] == 2 and after_restore["si"] == SOURCE_IP + 1, after_restore
            assert after_restore["di"] == DEST_IP + 1, after_restore
            assert after_restore["destination"] == "410000", after_restore

            first_remaining = debug.step(timeout_ms=5000)
            assert first_remaining["outcome"] == "step", first_remaining
            after_two = _state(debug, info)
            assert after_two["ip"] == REP_IP, after_two
            assert after_two["cx"] == 1 and after_two["si"] == SOURCE_IP + 2, after_two
            assert after_two["di"] == DEST_IP + 2, after_two
            assert after_two["destination"] == "414200", after_two

            final = debug.step(timeout_ms=5000)
            assert final["outcome"] == "step", final
            terminal = _state(debug, info)
            assert terminal["ip"] == NEXT_IP, terminal
            assert terminal["cx"] == 0 and terminal["si"] == SOURCE_IP + 3, terminal
            assert terminal["di"] == DEST_IP + 3, terminal
            assert terminal["destination"] == "414243", terminal
    assert source.read_bytes() == program


def test_qemu_virtual_clock_rep_movsb_normal_run_reaches_following_breakpoint(
        tmp_path, process_runtime, process_disk):
    # Authored count=3 MOVSB fixture. Run without manual stepping under the
    # virtual/icount clock profile to cover translated normal execution.
    program = bytes.fromhex("be0e01bf1101b90300fcf3a4ebfe414243000000")
    source = tmp_path / "REPVIRTUAL.COM"
    source.write_bytes(program)
    with Project.create(tmp_path / "rep-virtual.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)
        qemu_dir = tmp_path / "qemu-virtual"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(program)
        with project.debugger(
            str(process_runtime["executable"]), qemu_dir,
            **launch_options(process_runtime, process_disk, qemu_clock="virtual"),
        ) as debug:
            info = process_record(debug)
            breakpoint = debug.breakpoint(com_address(info, NEXT_IP))
            stopped = debug.run(timeout_ms=10000)
            assert stopped["outcome"] == "breakpoint", stopped
            assert breakpoint["breakpoint_id"] in stopped["session"]["stop_reason"][
                "breakpoint_ids"], stopped
            terminal = _state(debug, info)

    assert terminal["ip"] == NEXT_IP, terminal
    assert terminal["cx"] == 0, terminal
    assert terminal["si"] == SOURCE_IP + 3 and terminal["di"] == DEST_IP + 3, terminal
    assert terminal["destination"] == "414243", terminal
    assert source.read_bytes() == program
