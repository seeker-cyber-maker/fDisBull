"""Paired native REPNE SCASB conditional-stop and terminal-step boundary.

The authored COM scans ABC for 'B'. CPU stop state establishes partial and
terminal stepping; fetch trace records are checked only as subsequent fetches.
"""
from __future__ import annotations

import os

from fdisbull.project import Project
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dos_rep_trace_boundary_native import _next_fetch


# MOV DI,010Dh; MOV CX,3; MOV AL,'B'; CLD; REPNE SCASB; JMP $; data ABC.
PROGRAM = bytes.fromhex("bf0d01b90300b042fcf2aeebfe414243")
REP_IP = 0x109
NEXT_IP = 0x10B
DATA_IP = 0x10D


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _word(registers, name):
    values = registers.get("general", registers.get("registers", {}))
    for key in (name, "e" + name, "r" + name):
        if key in values:
            return _number(values[key]) & 0xFFFF
    raise AssertionError((name, registers))


def _flags(registers):
    if "flags" in registers:
        return _number(registers["flags"]) & 0xFFFF
    values = registers.get("general", registers.get("registers", {}))
    for key in ("eflags", "rflags", "flags"):
        if key in values:
            return _number(values[key]) & 0xFFFF
    raise AssertionError(("flags", registers))


def _snapshot(debug):
    registers = debug.registers()
    return dict(ip=_number(registers["instruction_pointer"]),
                cx=_word(registers, "cx"), di=_word(registers, "di"),
                al=_word(registers, "ax") & 0xFF,
                zf=bool(_flags(registers) & 0x40))


def _step(debug, *, qemu):
    result = debug.step(timeout_ms=5000) if qemu else debug.call(
        "execution.step", {"mode": "into"})
    assert (result["outcome"] == "step" if qemu
            else result["stop_reason"]["kind"] == "step"), result


def _reach_rep(debug, rep_address):
    breakpoint = debug.breakpoint(rep_address)
    stopped = debug.run(timeout_ms=10000)
    assert stopped["outcome"] == "breakpoint", stopped
    debug.delete_breakpoint(breakpoint["breakpoint_id"])


def test_native_dosbox_qemu_repne_scasb_conditional_terminal_step_parity(
        paired_runtime, tmp_path):
    source = tmp_path / "REPNE.COM"
    source.write_bytes(PROGRAM)
    with Project.create(tmp_path / "repne.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)
        qemu_dir = tmp_path / "qemu"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(PROGRAM)
        with project.debugger(
            str(paired_runtime["qemu"]), qemu_dir,
            **launch_options(dict(mcopy=os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                                  firmware=paired_runtime["firmware"]),
                             paired_runtime["disk"]),
        ) as debug:
            info = process_record(debug)
            runtime_base = com_address(info, 0x100)
            _reach_rep(debug, com_address(info, REP_IP))
            qemu_before = _snapshot(debug)
            _step(debug, qemu=True)
            qemu_partial = _snapshot(debug)
            _step(debug, qemu=True)
            qemu_terminal = _snapshot(debug)
            qemu_next_fetch = _next_fetch(
                debug, qemu=True, runtime_base=runtime_base)

        dosbox_dir = tmp_path / "dosbox"
        dosbox_dir.mkdir()
        (dosbox_dir / source.name).write_bytes(PROGRAM)
        with project.debugger(str(paired_runtime["dosbox"]), dosbox_dir) as debug:
            _reach_rep(debug, debug.static_base + REP_IP - 0x100)
            dosbox_before = _snapshot(debug)
            _step(debug, qemu=False)
            dosbox_partial = _snapshot(debug)
            _step(debug, qemu=False)
            dosbox_terminal = _snapshot(debug)
            dosbox_next_fetch = _next_fetch(debug, qemu=False)

    assert qemu_before["ip"] == dosbox_before["ip"] == REP_IP
    for before in (qemu_before, dosbox_before):
        assert before["cx"] == 3 and before["di"] == DATA_IP, before
        assert before["al"] == ord("B"), before

    # First comparison sees A: REPNE continues, CX decreases, ZF remains clear.
    for partial in (qemu_partial, dosbox_partial):
        assert partial["ip"] == REP_IP, partial
        assert partial["cx"] == 2 and partial["di"] == DATA_IP + 1, partial
        assert partial["zf"] is False, partial
    assert qemu_partial == dosbox_partial

    # Second comparison sees B: REPNE terminates early with CX still nonzero.
    for terminal in (qemu_terminal, dosbox_terminal):
        assert terminal["ip"] == NEXT_IP, terminal
        assert terminal["cx"] == 1 and terminal["di"] == DATA_IP + 2, terminal
        assert terminal["zf"] is True, terminal
    assert qemu_terminal == dosbox_terminal
    assert qemu_next_fetch == dosbox_next_fetch == [NEXT_IP]
    assert source.read_bytes() == PROGRAM
