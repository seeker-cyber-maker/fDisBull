"""Native protected-mode LOCK and null-DS reference divergences."""
from __future__ import annotations

from base64 import b64decode
from contextlib import closing
import os
from pathlib import Path
import shutil
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.atomic_limit_fixture import (
    COMPLETION_MARKER_VALUE, FAULT_EAX, FAULT_MARKER_VALUE, LOCK_EXPECTED,
    LOCK_OFFSET, LOCK_REPLACEMENT, NULL_VALUE, build,
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


def _u32(data):
    return int.from_bytes(data, "little")


def _qemu_read(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space="physical")["hex"])


def _dosbox_read(call, address, length):
    packet = call("memory.read", {"address": {"space": "physical",
                                                "offset": f"0x{address:08x}"},
                                "length": length})
    data = b64decode(packet["data_base64"], validate=True)
    assert len(data) == length, packet
    return data


def _wait_dosbox(call, operation):
    deadline = time.monotonic() + 15
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, "DOSBox-X did not reach a protected-mode breakpoint"
        stop = call("execution.wait", {"operation_id": operation["operation_id"],
                                       "timeout_ms": min(250, remaining)})
        if not stop.get("running"):
            return stop


def _dosbox_bp(call, selector, offset):
    return call("breakpoints.create", {
        "kind": "execution", "once": False,
        "address": {"space": "segmented", "segment": f"0x{selector:04x}",
                    "offset": f"0x{offset:08x}"},
    })


def _fields_dosbox(call, psp, labels):
    names = ("fault_eax", "fault_ebx", "fault_error", "fault_eip", "fault_cs",
             "fault_eflags", "fault_memory", "fault_marker", "final_eax",
             "final_ebx", "final_eflags", "final_memory", "final_ds",
             "completion_marker")
    return {name: _u32(_dosbox_read(call, psp * 16 + labels[name], 4))
            for name in names}


def _fields_qemu(debug, psp, labels):
    names = ("fault_eax", "fault_ebx", "fault_error", "fault_eip", "fault_cs",
             "fault_eflags", "fault_memory", "fault_marker", "final_eax",
             "final_ebx", "final_eflags", "final_memory", "final_ds",
             "completion_marker")
    return {name: _u32(_qemu_read(debug, psp * 16 + labels[name], 4))
            for name in names}


def _run_dosbox(runtime, root, code, labels, case):
    game = root / "dosbox"
    game.mkdir(parents=True)
    (game / "ATOMIC.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        start = rpc.call("session.start", {
            "target": {"command": "ATOMIC.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = start["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=10000)

        entry = call("state.get_registers")
        psp = _reg(entry, "cs") & 0xFFFF
        ready_bp = _dosbox_bp(call, psp, labels["pm_ready"])
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == ready_bp["breakpoint_id"], stop
        ready = call("state.get_registers")
        assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
        call("breakpoints.delete", {"breakpoint_id": ready_bp["breakpoint_id"]})

        handler_bp = _dosbox_bp(call, 8, labels["gp_handler"])
        completion_bp = _dosbox_bp(call, 8, labels["completion_stop"])
        stop = _wait_dosbox(call, call("execution.continue"))
        if stop["stop_reason"].get("breakpoint_id") != handler_bp["breakpoint_id"]:
            state = call("state.get_registers")
            buffer_base = _u32(_dosbox_read(call, psp * 16 + labels["buffer_base"], 4))
            access_offset = LOCK_OFFSET if case == "lock" else 0
            fields = _fields_dosbox(call, psp, labels)
            return dict(first_stop="completion-or-other",
                        stop_reason=stop["stop_reason"],
                        ip=_number(state["instruction_pointer"]),
                        ds=_reg(state, "ds"),
                        eax=_reg(state, "eax") & 0xFFFFFFFF,
                        ebx=_reg(state, "ebx") & 0xFFFFFFFF,
                        backing=_u32(_dosbox_read(call, buffer_base + access_offset, 4)),
                        fault_marker=fields["fault_marker"],
                        completion_marker=fields["completion_marker"],
                        final_eax=fields["final_eax"],
                        final_memory=fields["final_memory"])

        fault = call("state.get_registers")
        assert fault["cpu_mode"] == "protected" and _reg(fault, "cs") == 8, fault
        assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
        fault_eax = _reg(fault, "eax", "rax") & 0xFFFFFFFF
        fault_ebx = _reg(fault, "ebx", "rbx") & 0xFFFFFFFF
        esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
        frame = _dosbox_read(call, psp * 16 + esp, 16)
        buffer_base = _u32(_dosbox_read(call, psp * 16 + labels["buffer_base"], 4))
        access_offset = LOCK_OFFSET if case == "lock" else 0
        backing_before = _u32(_dosbox_read(call, buffer_base + access_offset, 4))

        # Single-step the handler's initial CLI to resume safely, then rearm
        # its entry breakpoint so a second #GP cannot masquerade as completion.
        call("breakpoints.delete", {"breakpoint_id": handler_bp["breakpoint_id"]})
        stepped = call("execution.step", {"mode": "into"})
        assert stepped["stop_reason"]["kind"] == "step", stepped
        handler_guard = _dosbox_bp(call, 8, labels["gp_handler"])
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == completion_bp["breakpoint_id"], stop
        assert handler_guard["breakpoint_id"] not in stop["stop_reason"].get("breakpoint_ids", [])
        complete = call("state.get_registers")
        fields = _fields_dosbox(call, psp, labels)
        backing_after = _u32(_dosbox_read(call, buffer_base + access_offset, 4))
        return dict(first_stop="handler", frame=frame, live_eax=fault_eax,
                    live_ebx=fault_ebx, backing_before=backing_before,
                    backing_after=backing_after, fields=fields,
                    complete_ip=_number(complete["instruction_pointer"]),
                    completion_ip=labels["completion_stop"])


def _run_qemu(runtime, root, code, labels, case):
    root.mkdir()
    source = root / "ATOMIC.COM"
    source.write_bytes(code)
    project = Project.create(root / "atomic.fdb", source, image="com")
    with project:
        project.analyze(max_instructions=256)
        game = root / "qemu"
        game.mkdir()
        (game / source.name).write_bytes(code)
        options = launch_options({
            "executable": str(runtime["qemu"]),
            "mcopy": os.environ["FDISBULL_QEMU_DOS_MCOPY"],
            "firmware": runtime["firmware"],
        }, runtime["disk"])
        with project.debugger(str(runtime["qemu"]), game, **options) as debug:
            info = process_record(debug)
            psp = _reg(info, "psp_segment") & 0xFFFF
            ready_bp = debug.breakpoint(com_address(info, labels["pm_ready"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert ready_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            ready = debug.registers()
            assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
            debug.delete_breakpoint(ready_bp["breakpoint_id"])

            handler_bp = debug.breakpoint(com_address(info, labels["gp_handler"]))
            completion_bp = debug.breakpoint(com_address(info, labels["completion_stop"]))
            stop = debug.run(timeout_ms=15000)
            if (stop["outcome"] != "breakpoint" or
                    handler_bp["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"]):
                return dict(first_stop="completion-or-other", stop=stop,
                            registers=debug.registers())

            fault = debug.registers()
            assert fault["cpu_mode"] == "protected" and _reg(fault, "cs") == 8, fault
            assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
            fault_eax = _reg(fault, "eax", "rax") & 0xFFFFFFFF
            fault_ebx = _reg(fault, "ebx", "rbx") & 0xFFFFFFFF
            esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
            frame = _qemu_read(debug, psp * 16 + esp, 16)
            buffer_base = _u32(_qemu_read(debug, psp * 16 + labels["buffer_base"], 4))
            access_offset = LOCK_OFFSET if case == "lock" else 0
            backing_before = _u32(_qemu_read(debug, buffer_base + access_offset, 4))

            # A QEMU single-step executes the handler's initial CLI before its
            # persistent breakpoint is rearmed to detect a second exception.
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            stepped = debug.step(timeout_ms=5000)
            assert stepped["outcome"] == "step", stepped
            assert _number(debug.registers()["instruction_pointer"]) == labels["gp_handler"] + 1
            handler_guard = debug.breakpoint(com_address(info, labels["gp_handler"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert completion_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            assert handler_guard["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            complete = debug.registers()
            fields = _fields_qemu(debug, psp, labels)
            backing_after = _u32(_qemu_read(debug, buffer_base + access_offset, 4))
            return dict(first_stop="handler", frame=frame, live_eax=fault_eax,
                        live_ebx=fault_ebx, backing_before=backing_before,
                        backing_after=backing_after, fields=fields,
                        complete_ip=_number(complete["instruction_pointer"]),
                        completion_ip=labels["completion_stop"])


def _assert_probe(result, case, labels):
    assert result["first_stop"] == "handler", result
    frame = result["frame"]
    fields = result["fields"]
    assert _u32(frame[0:4]) == 0, result
    assert _u32(frame[4:8]) == labels["fault_ip"], result
    assert _u32(frame[8:12]) == 8, result
    assert _u32(frame[12:16]) == fields["fault_eflags"], result
    assert fields["fault_error"] == 0, result
    assert fields["fault_eip"] == labels["fault_ip"], result
    assert fields["fault_cs"] == 8, result
    assert fields["fault_marker"] == FAULT_MARKER_VALUE, result
    assert result["complete_ip"] == result["completion_ip"], result
    assert fields["completion_marker"] == COMPLETION_MARKER_VALUE, result

    if case == "lock":
        assert result["live_eax"] == LOCK_EXPECTED, result
        assert result["live_ebx"] == LOCK_REPLACEMENT, result
        assert result["backing_before"] == LOCK_EXPECTED, result
        assert fields["fault_eax"] == LOCK_EXPECTED, result
        assert fields["fault_ebx"] == LOCK_REPLACEMENT, result
        assert fields["fault_memory"] == LOCK_EXPECTED, result
        assert fields["final_eax"] == LOCK_EXPECTED, result
        assert fields["final_memory"] == LOCK_REPLACEMENT, result
        assert fields["final_eflags"] & 0x40, result
    else:
        assert result["live_eax"] == FAULT_EAX, result
        assert fields["fault_eax"] == FAULT_EAX, result
        assert fields["fault_memory"] == NULL_VALUE, result
        assert result["backing_before"] == NULL_VALUE, result
        assert fields["final_eax"] == NULL_VALUE, result
        assert fields["final_memory"] == NULL_VALUE, result
        assert fields["final_ds"] == 0x18, result
    assert result["backing_after"] == fields["final_memory"], result


@pytest.mark.parametrize("case", ["lock", "null"], ids=["lock-cmpxchg-limit", "null-ds-offset-zero"])
def test_native_qemu_faults_where_dosbox_reference_completes(paired_runtime, tmp_path, case):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for authored protected-mode atomic fixtures")
    code, labels = build(tmp_path / f"fixture-{case}", nasm, case=case)
    qemu = _run_qemu(paired_runtime, tmp_path / f"qemu-{case}", code, labels, case)
    dosbox = _run_dosbox(paired_runtime, tmp_path / f"dosbox-{case}", code, labels, case)

    # QEMU enforces these protected-mode accesses. The frozen DOSBox-X build
    # completes both without #GP, so this is a recorded parity gap, not a
    # passing paired-retry claim.
    _assert_probe(qemu, case, labels)
    assert dosbox["first_stop"] == "completion-or-other", dosbox
    assert dosbox["stop_reason"]["kind"] == "breakpoint", dosbox
    assert dosbox["ip"] == labels["completion_stop"], dosbox
    assert dosbox["fault_marker"] == 0, dosbox
    assert dosbox["completion_marker"] == COMPLETION_MARKER_VALUE, dosbox
    if case == "lock":
        assert dosbox["ds"] == 0x20, dosbox
        assert dosbox["backing"] == LOCK_REPLACEMENT, dosbox
        assert dosbox["final_eax"] == LOCK_EXPECTED, dosbox
        assert dosbox["final_memory"] == LOCK_REPLACEMENT, dosbox
    else:
        assert dosbox["ds"] == 0, dosbox
        assert dosbox["backing"] == NULL_VALUE, dosbox
        assert dosbox["final_eax"] != NULL_VALUE, dosbox
        assert dosbox["final_memory"] == NULL_VALUE, dosbox
