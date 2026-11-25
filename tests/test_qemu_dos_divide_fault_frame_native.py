"""Opt-in paired DOSBox-X/QEMU divide-fault before-fetch diagnostic.

Uses the private native inputs selected by test_qemu_dos_before_fetch_trace_native.
The witness checks CPU-created stack state in addition to trace PCs.
"""
from __future__ import annotations

from contextlib import closing
import base64
import os

from fdisbull.dosbox_rpc import DOSBoxRPC
from test_qemu_dos_before_fetch_trace_native import (
    _event_offset, _num, paired_runtime,
)
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record,
)


# 0100: MOV DX,0111; MOV AX,2500; INT 21h installs INT 0; MOV AX,1234;
# XOR BX,BX; DIV BL faults at 010Dh; JMP $ is the saved return destination.
# 0111: PUSH BP; MOV BP,SP; ADD word [BP+2],2; POP BP; IRET.
PROGRAM = bytes.fromhex("ba1101b80025cd21b8341231dbf6f3ebfe5589e5834602025dcf")
DIV_IP = 0x10D
HANDLER_IP = 0x111


def _word(registers, *names):
    sources = [registers]
    sources.extend(registers.get(key, {}) for key in ("general", "segments", "registers")
                   if isinstance(registers.get(key), dict))
    for name in names:
        for values in sources:
            if name in values:
                value = values[name]
                try:
                    return _num(value) & 0xFFFF
                except ValueError:
                    return int(value, 16) & 0xFFFF
    raise AssertionError(f"Missing register {names!r}: {registers!r}")


def _wait_dosbox(call, operation):
    import time
    deadline = time.monotonic() + 5
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, "DOSBox-X did not reach the bounded breakpoint"
        stop = call("execution.wait", {"operation_id": operation["operation_id"],
                                        "timeout_ms": min(250, remaining)})
        if not stop.get("running"):
            return stop


def _dosbox_case(runtime, directory):
    game = directory / "dosbox"
    game.mkdir()
    (game / "FAULT.COM").write_bytes(PROGRAM)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        start = rpc.call("session.start", {
            "target": {"command": "FAULT.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = start["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=5000)

        entry_regs = call("state.get_registers")
        cs = _word(entry_regs, "cs")
        div_bp = call("breakpoints.create", {
            "kind": "execution", "once": False,
            "address": {"space": "segmented", "segment": f"0x{cs:04x}",
                        "offset": f"0x{DIV_IP:08x}"},
        })
        first_stop = _wait_dosbox(call, call("execution.continue"))
        assert first_stop["stop_reason"]["breakpoint_id"] == div_bp["breakpoint_id"]
        before = call("state.get_registers")
        before_sp, before_ax = _word(before, "sp", "esp"), _word(before, "ax", "eax")
        assert _num(before["instruction_pointer"]) == DIV_IP and before_ax == 0x1234
        call("breakpoints.delete", {"breakpoint_id": div_bp["breakpoint_id"]})
        handler_bp = call("breakpoints.create", {
            "kind": "execution", "once": False,
            "address": {"space": "segmented", "segment": f"0x{cs:04x}",
                        "offset": f"0x{HANDLER_IP:08x}"},
        })
        trace = call("trace.start", {"detail": "normal", "instruction_count": 8})
        assert trace.get("active") is True, trace
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == handler_bp["breakpoint_id"]
        after = call("state.get_registers")
        assert _num(after["instruction_pointer"]) == HANDLER_IP
        assert _word(after, "ax", "eax") == before_ax
        ss, sp = _word(after, "ss"), _word(after, "sp", "esp")
        assert sp == (before_sp - 6) & 0xFFFF
        frame = call("memory.read", {
            "address": {"space": "physical", "offset": f"0x{ss * 16 + sp:08x}"},
            "length": 6,
        })
        raw = base64.b64decode(frame["data_base64"], validate=True)
        assert int.from_bytes(raw[0:2], "little") == DIV_IP
        assert int.from_bytes(raw[2:4], "little") == cs
        events, cursor, seen = [], None, set()
        while True:
            page = call("trace.read", {"cursor": cursor, "limit": 8})
            events.extend(page["events"])
            cursor = page.get("next_cursor")
            if cursor is None:
                break
            assert cursor not in seen
            seen.add(cursor)
        call("trace.stop")
        pcs = [_event_offset(e) for e in events]
        assert pcs == [DIV_IP, HANDLER_IP], events
        return pcs, (before_ax, _word(after, "ax", "eax")), (before_sp, sp), raw


def _qemu_case(runtime, directory):
    directory.mkdir()
    _, project = create_project(directory, PROGRAM, filename="FAULT.COM")
    with project:
        with project.debugger(str(runtime["qemu"]), directory,
                **launch_options({"executable": str(runtime["qemu"]),
                                  "mcopy": os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                                  "firmware": runtime["firmware"]}, runtime["disk"])) as debug:
            info = process_record(debug)
            assert _num(info["entry"]["ip"]) == 0x100
            div_bp = debug.breakpoint(com_address(info, DIV_IP))
            assert debug.run(timeout_ms=5000)["outcome"] == "breakpoint"
            before = debug.registers()
            before_sp, before_ax = _word(before, "rsp", "sp"), _word(before, "rax", "ax")
            assert _num(before["instruction_pointer"]) == DIV_IP and before_ax == 0x1234
            debug.delete_breakpoint(div_bp["breakpoint_id"])
            handler_bp = debug.breakpoint(com_address(info, HANDLER_IP))
            trace = debug.call("trace.start", {"detail": "normal", "instruction_count": 8})
            assert trace.get("active") is True, trace
            run = debug.run(timeout_ms=5000)
            assert run["outcome"] == "breakpoint", run
            assert handler_bp["breakpoint_id"] in run["session"]["stop_reason"]["breakpoint_ids"]
            after = debug.registers()
            assert _num(after["instruction_pointer"]) == HANDLER_IP
            assert _word(after, "rax", "ax") == before_ax
            ss, sp = _word(after, "ss"), _word(after, "rsp", "sp")
            assert sp == (before_sp - 6) & 0xFFFF
            frame = bytes.fromhex(debug.memory(ss * 16 + sp, length=6, space="physical")["hex"])
            assert int.from_bytes(frame[:2], "little") == DIV_IP
            assert int.from_bytes(frame[2:4], "little") == _word(after, "cs")
            events, cursor = [], None
            while True:
                page = debug.call("trace.read", {"cursor": cursor, "limit": 8})
                events.extend(page["events"])
                cursor = page.get("next_cursor")
                if cursor is None:
                    break
            debug.call("trace.stop")
            pcs = [_event_offset(e, runtime_base=com_address(info, 0x100)) for e in events]
            assert pcs == [DIV_IP, HANDLER_IP], events
            return pcs, (before_ax, _word(after, "rax", "ax")), (before_sp, sp), frame


def test_native_dosbox_qemu_divide_fault_before_fetch_and_cpu_frame(paired_runtime, tmp_path):
    qemu = _qemu_case(paired_runtime, tmp_path / "qemu")
    dosbox = _dosbox_case(paired_runtime, tmp_path)
    assert qemu[0] == dosbox[0] == [DIV_IP, HANDLER_IP]
    for result in (qemu, dosbox):
        assert result[1] == (0x1234, 0x1234), result
        assert result[2][1] == (result[2][0] - 6) & 0xFFFF, result
        assert int.from_bytes(result[3][:2], "little") == DIV_IP
