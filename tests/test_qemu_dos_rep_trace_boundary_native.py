"""Paired partial-REP progress and terminal step parity.

The private DOS boot image and selected native executables come from the
existing paired trace fixture. Fetch records do not certify retirement.
"""
from __future__ import annotations

import os

from fdisbull.project import Project
from test_qemu_dos_before_fetch_trace_native import _event_offset, paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record


# MOV SI,010Eh; MOV DI,0111h; MOV CX,3; CLD; REP MOVSB; JMP $;
# source ABC; destination 000. Each debugger step should move one byte.
PROGRAM = bytes.fromhex("be0e01bf1101b90300fcf3a4ebfe414243000000")
REP_IP = 0x10A
DEST_IP = 0x111


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _word(registers, name):
    values = registers.get("general", registers.get("registers", {}))
    for key in (name, "e" + name, "r" + name):
        if key in values:
            return _number(values[key]) & 0xFFFF
    raise AssertionError((name, registers))


def _snapshot(debug, *, qemu, destination):
    registers = debug.registers()
    memory = (debug.memory(destination, length=3, space="physical") if qemu
              else debug.memory(destination, length=3))
    return dict(ip=_number(registers["instruction_pointer"]),
                cx=_word(registers, "cx"), si=_word(registers, "si"),
                di=_word(registers, "di"), destination=memory["hex"])


def _observe(debug, *, qemu, rep_address, destination, runtime_base=None):
    breakpoint = debug.breakpoint(rep_address)
    stopped = debug.run(timeout_ms=10000)
    assert stopped["outcome"] == "breakpoint", stopped
    debug.delete_breakpoint(breakpoint["breakpoint_id"])
    before = _snapshot(debug, qemu=qemu, destination=destination)
    assert before == dict(ip=REP_IP, cx=3, si=0x10E, di=DEST_IP,
                          destination="000000"), before

    started = debug.call("trace.start", {"detail": "normal", "instruction_count": 8})
    assert started["active"] is True, started
    progress = []
    for _ in range(3):
        step = (debug.step(timeout_ms=5000) if qemu
                else debug.call("execution.step", {"mode": "into"}))
        assert (step["outcome"] == "step" if qemu
                else step["stop_reason"]["kind"] == "step"), step
        progress.append(_snapshot(debug, qemu=qemu, destination=destination))
    page = debug.call("trace.read", {"cursor": None, "limit": 8})
    stopped_trace = debug.call("trace.stop")
    assert stopped_trace["active"] is False, stopped_trace
    events = page["events"]
    offsets = [_event_offset(event, runtime_base=runtime_base) for event in events]
    assert offsets == [REP_IP] * 3, (offsets, events)
    assert stopped_trace["event_count"] == 3, stopped_trace
    assert all(event.get("observation", {}).get("instruction_completed") is not True
               for event in events), events
    return dict(before=before, progress=progress, offsets=offsets,
                events=events, trace_version=started.get("trace_version"))


def _next_fetch(debug, *, qemu, runtime_base=None):
    debug.call("trace.start", {"detail": "normal", "instruction_count": 2})
    step = (debug.step(timeout_ms=5000) if qemu
            else debug.call("execution.step", {"mode": "into"}))
    assert (step["outcome"] == "step" if qemu
            else step["stop_reason"]["kind"] == "step"), step
    page = debug.call("trace.read", {"cursor": None, "limit": 2})
    stopped = debug.call("trace.stop")
    assert stopped["event_count"] == 1, stopped
    return [_event_offset(event, runtime_base=runtime_base)
            for event in page["events"]]


def test_dosbox_qemu_partial_rep_fetch_progress_and_terminal_step_parity(paired_runtime, tmp_path):
    source = tmp_path / "REP.COM"
    source.write_bytes(PROGRAM)
    with Project.create(tmp_path / "rep.fdb", source, image="com") as project:
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
            base = com_address(info, 0x100)
            qemu = _observe(debug, qemu=True, rep_address=com_address(info, REP_IP),
                            destination=com_address(info, DEST_IP), runtime_base=base)
            qemu_next_fetch = _next_fetch(debug, qemu=True, runtime_base=base)
            qemu_tail = _snapshot(debug, qemu=True,
                                  destination=com_address(info, DEST_IP))
        dosbox_dir = tmp_path / "dosbox"
        dosbox_dir.mkdir()
        (dosbox_dir / source.name).write_bytes(PROGRAM)
        with project.debugger(str(paired_runtime["dosbox"]), dosbox_dir) as debug:
            dosbox = _observe(debug, qemu=False,
                              rep_address=debug.static_base + REP_IP - 0x100,
                              destination=debug.static_base + DEST_IP - 0x100)
            dosbox_next_fetch = _next_fetch(debug, qemu=False)

    shared_progress = [
        dict(ip=REP_IP, cx=2, si=0x10F, di=0x112, destination="410000"),
        dict(ip=REP_IP, cx=1, si=0x110, di=0x113, destination="414200"),
    ]
    assert qemu["progress"][:2] == dosbox["progress"][:2] == shared_progress
    # The third step must stop at the following JMP on both engines. Fetch
    # records alone do not certify completion; the debugger stop and CPU/RAM
    # state establish this bounded step parity.
    terminal = dict(cx=0, si=0x111, di=0x114, destination="414243")
    assert qemu["progress"][2] == dict(ip=0x10C, **terminal)
    assert dosbox["progress"][2] == dict(ip=0x10C, **terminal)
    assert qemu_tail == dict(ip=0x10C, **terminal)
    assert qemu_next_fetch == [0x10C]
    assert dosbox_next_fetch == [0x10C]
    assert qemu["offsets"] == dosbox["offsets"] == [REP_IP] * 3
    assert qemu["trace_version"] == 2
    assert [event["native"]["origin"] for event in qemu["events"]] == [
        "tcg-dispatch"] * 3
    assert [event["native"]["code-bytes"] for event in qemu["events"]] == [
        "f3a4"] * 3
    assert source.read_bytes() == PROGRAM
