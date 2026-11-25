"""Paired REP terminal-step witness for 16-bit address-size count semantics.

The authored real-mode COM sets ECX to 12340001h, then executes a default
16-bit-address-size REP MOVSB. One debugger step must consume CX only, preserve
ECX's high word, advance the 16-bit indexes, copy one byte, and retire at the
following instruction in both native engines.
"""
from __future__ import annotations

import os

from fdisbull.project import Project
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record


# MOV SI,0111h; MOV DI,0114h; MOV ECX,12340001h; CLD; REP MOVSB; JMP $; ABC; ...
PROGRAM = bytes.fromhex("be1101bf140166b901003412fcf3a4ebfe414243000000")
REP_IP = 0x10D
NEXT_IP = 0x10F
SOURCE_IP = 0x111
DEST_IP = 0x114
EXPECTED_ECX = 0x12340000


def _number(value):
    if isinstance(value, str):
        return int(value, 0) if value.lower().startswith("0x") else int(value, 16)
    return int(value)


def _register(registers, *names):
    for values in (registers.get("general", {}), registers.get("registers", {}), registers):
        for name in names:
            if name in values:
                return _number(values[name])
    raise AssertionError((names, registers))


def _snapshot(debug, *, qemu, info=None):
    registers = debug.registers()
    if qemu:
        destination = com_address(info, DEST_IP)
        memory = debug.memory(destination, length=3, space="physical")
    else:
        destination = debug.static_base + DEST_IP - 0x100
        memory = debug.memory(destination, length=3)
    return dict(
        ip=_number(registers.get("instruction_pointer", registers.get("ip"))),
        ecx=_register(registers, "ecx", "rcx"),
        si=_register(registers, "si", "esi", "rsi") & 0xFFFF,
        di=_register(registers, "di", "edi", "rdi") & 0xFFFF,
        destination=memory["hex"],
    )


def _at_rep(debug, address):
    breakpoint = debug.breakpoint(address)
    stopped = debug.run(timeout_ms=10000)
    assert stopped["outcome"] == "breakpoint", stopped
    debug.delete_breakpoint(breakpoint["breakpoint_id"])


def _observe(debug, *, qemu, info=None, rep_address):
    _at_rep(debug, rep_address)
    before = _snapshot(debug, qemu=qemu, info=info)
    assert before == dict(ip=REP_IP, ecx=0x12340001, si=SOURCE_IP,
                          di=DEST_IP, destination="000000"), before
    if qemu:
        step = debug.step(timeout_ms=5000)
        assert step["outcome"] == "step", step
    else:
        step = debug.call("execution.step", {"mode": "into"})
        assert step["stop_reason"]["kind"] == "step", step
    return _snapshot(debug, qemu=qemu, info=info)


def test_paired_dosbox_qemu_16bit_address_size_rep_preserves_ecx_high_word(
        paired_runtime, tmp_path):
    source = tmp_path / "REPADDR.COM"
    source.write_bytes(PROGRAM)
    with Project.create(tmp_path / "rep-address-size.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)

        qemu_dir = tmp_path / "qemu"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(PROGRAM)
        runtime = dict(mcopy=os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                       firmware=paired_runtime["firmware"])
        with project.debugger(
                str(paired_runtime["qemu"]), qemu_dir,
                **launch_options(runtime, paired_runtime["disk"])) as debug:
            info = process_record(debug)
            qemu = _observe(debug, qemu=True, info=info,
                            rep_address=com_address(info, REP_IP))

        dosbox_dir = tmp_path / "dosbox"
        dosbox_dir.mkdir()
        (dosbox_dir / source.name).write_bytes(PROGRAM)
        with project.debugger(str(paired_runtime["dosbox"]), dosbox_dir) as debug:
            assert debug.contexts()["selected"] == "dos-cpu"
            dosbox = _observe(debug, qemu=False,
                              rep_address=debug.static_base + REP_IP - 0x100)

    expected = dict(ip=NEXT_IP, ecx=EXPECTED_ECX, si=SOURCE_IP + 1,
                    di=DEST_IP + 1, destination="410000")
    assert qemu == dosbox == expected
    assert source.read_bytes() == PROGRAM


# MOV ESI,0118h; MOV EDI,011Bh; MOV ECX,1; CLD; 67 REP MOVSB; JMP $; ABC; ...
PROGRAM32 = bytes.fromhex(
    "66be1801000066bf1b01000066b901000000fc67f3a4ebfe414243000000")
REP32_IP = 0x113
NEXT32_IP = 0x116
SOURCE32_IP = 0x118
DEST32_IP = 0x11B


def _snapshot32(debug, *, qemu, info=None):
    registers = debug.registers()
    if qemu:
        destination = com_address(info, DEST32_IP)
        memory = debug.memory(destination, length=3, space="physical")
    else:
        destination = debug.static_base + DEST32_IP - 0x100
        memory = debug.memory(destination, length=3)
    return dict(
        ip=_number(registers.get("instruction_pointer", registers.get("ip"))),
        ecx=_register(registers, "ecx", "rcx"),
        esi=_register(registers, "esi", "rsi"),
        edi=_register(registers, "edi", "rdi"),
        destination=memory["hex"],
    )


def _observe32(debug, *, qemu, info=None, rep_address):
    _at_rep(debug, rep_address)
    before = _snapshot32(debug, qemu=qemu, info=info)
    assert before == dict(ip=REP32_IP, ecx=1, esi=SOURCE32_IP,
                          edi=DEST32_IP, destination="000000"), before
    if qemu:
        step = debug.step(timeout_ms=5000)
        assert step["outcome"] == "step", step
    else:
        step = debug.call("execution.step", {"mode": "into"})
        assert step["stop_reason"]["kind"] == "step", step
    return _snapshot32(debug, qemu=qemu, info=info)


def test_paired_dosbox_qemu_32bit_address_size_rep_terminal_step(
        paired_runtime, tmp_path):
    source = tmp_path / "REPADDR32.COM"
    source.write_bytes(PROGRAM32)
    with Project.create(tmp_path / "rep-address-size-32.fdb", source, image="com") as project:
        project.analyze(max_instructions=64)

        qemu_dir = tmp_path / "qemu"
        qemu_dir.mkdir()
        (qemu_dir / source.name).write_bytes(PROGRAM32)
        runtime = dict(mcopy=os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                       firmware=paired_runtime["firmware"])
        with project.debugger(
                str(paired_runtime["qemu"]), qemu_dir,
                **launch_options(runtime, paired_runtime["disk"])) as debug:
            info = process_record(debug)
            qemu = _observe32(debug, qemu=True, info=info,
                              rep_address=com_address(info, REP32_IP))

        dosbox_dir = tmp_path / "dosbox"
        dosbox_dir.mkdir()
        (dosbox_dir / source.name).write_bytes(PROGRAM32)
        with project.debugger(str(paired_runtime["dosbox"]), dosbox_dir) as debug:
            assert debug.contexts()["selected"] == "dos-cpu"
            dosbox = _observe32(debug, qemu=False,
                                rep_address=debug.static_base + REP32_IP - 0x100)

    expected = dict(ip=NEXT32_IP, ecx=0, esi=SOURCE32_IP + 1,
                    edi=DEST32_IP + 1, destination="410000")
    assert qemu == dosbox == expected
    assert source.read_bytes() == PROGRAM32
