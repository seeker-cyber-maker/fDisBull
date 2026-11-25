"""Paired native protected-mode scalar DS-limit #GP and retry witness."""
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
from support.scalar_limit_fixture import (
    COMPLETION_MARKER_VALUE, FAULT_EAX, FAULT_MARKER_VALUE, MEMORY_VALUE,
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


def _dosbox_wait(call, operation):
    deadline = time.monotonic() + 15
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, "DOSBox-X did not reach the scalar probe breakpoint"
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


def _dosbox_observe(runtime, game_root, code, labels, scalar_offset):
    game = game_root / "dosbox"
    game.mkdir(parents=True)
    (game / "SCALAR.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        started = rpc.call("session.start", {
            "target": {"command": "SCALAR.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = started["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=10000)

        entry = call("state.get_registers")
        assert entry["cpu_mode"] == "real", entry
        psp = _reg(entry, "cs") & 0xFFFF
        ready_bp = _dosbox_bp(call, psp, labels["pm_ready"])
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == ready_bp["breakpoint_id"], stop
        ready = call("state.get_registers")
        assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
        call("breakpoints.delete", {"breakpoint_id": ready_bp["breakpoint_id"]})
        handler_bp = _dosbox_bp(call, 8, labels["gp_handler"])
        completion_bp = _dosbox_bp(call, 8, labels["completion_stop"])
        stop = _dosbox_wait(call, call("execution.continue"))
        if stop["stop_reason"].get("breakpoint_id") != handler_bp["breakpoint_id"]:
            state = call("state.get_registers")
            return dict(first_stop="completion-or-other", stop=stop, registers=state,
                        psp=psp)

        fault = call("state.get_registers")
        assert fault["cpu_mode"] == "protected", fault
        assert _reg(fault, "cs") == 8, fault
        assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
        assert _reg(fault, "eax", "rax") & 0xFFFFFFFF == FAULT_EAX, fault
        esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
        frame = _dosbox_read(call, psp * 16 + esp, 16)
        buffer_base = _u32(_dosbox_read(call, psp * 16 + labels["buffer_base"], 4))
        source_value = _u32(_dosbox_read(call, buffer_base + scalar_offset, 4))

        # Keep the handler breakpoint armed so a second fault is a stop, not
        # an implicit successful retry.
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == completion_bp["breakpoint_id"], stop
        complete = call("state.get_registers")
        final_eax = _u32(_dosbox_read(call, psp * 16 + labels["final_eax"], 4))
        fault_eax = _u32(_dosbox_read(call, psp * 16 + labels["fault_eax"], 4))
        fault_error = _u32(_dosbox_read(call, psp * 16 + labels["fault_error"], 4))
        fault_eip = _u32(_dosbox_read(call, psp * 16 + labels["fault_eip"], 4))
        fault_cs = _u32(_dosbox_read(call, psp * 16 + labels["fault_cs"], 4))
        fault_eflags = _u32(_dosbox_read(call, psp * 16 + labels["fault_eflags"], 4))
        fault_marker = _u32(_dosbox_read(call, psp * 16 + labels["fault_marker"], 4))
        completion_marker = _u32(_dosbox_read(call, psp * 16 + labels["completion_marker"], 4))
        return dict(first_stop="handler", frame=frame, source_value=source_value,
                    final_eax=final_eax, fault_eax=fault_eax, fault_error=fault_error,
                    fault_eip=fault_eip, fault_cs=fault_cs, fault_eflags=fault_eflags,
                    fault_marker=fault_marker, completion_marker=completion_marker,
                    complete_ip=_number(complete["instruction_pointer"]),
                    completion_ip=labels["completion_stop"])


def _qemu_observe(runtime, disk, root, code, labels, scalar_offset):
    root.mkdir()
    source = root / "SCALAR.COM"
    source.write_bytes(code)
    project = Project.create(root / "scalar.fdb", source, image="com")
    with project:
        project.analyze(max_instructions=256)
        game = root / "qemu"
        game.mkdir()
        (game / source.name).write_bytes(code)
        options = launch_options({
            "executable": str(runtime["qemu"]),
            "mcopy": os.environ["FDISBULL_QEMU_DOS_MCOPY"],
            "firmware": runtime["firmware"],
        }, disk)
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
                            registers=debug.registers(), psp=psp)

            fault = debug.registers()
            assert fault["cpu_mode"] == "protected" and _reg(fault, "cs") == 8, fault
            assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
            assert _reg(fault, "eax", "rax") & 0xFFFFFFFF == FAULT_EAX, fault
            esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
            frame = _qemu_read(debug, psp * 16 + esp, 16)
            buffer_base = _u32(_qemu_read(debug, psp * 16 + labels["buffer_base"], 4))
            source_value = _u32(_qemu_read(debug, buffer_base + scalar_offset, 4))

            # QEMU re-stops at a persistent handler breakpoint on continue.
            # Step its first CLI, then rearm to catch an actual second fault.
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            first_handler_step = debug.step(timeout_ms=5000)
            assert first_handler_step["outcome"] == "step", first_handler_step
            assert _number(debug.registers()["instruction_pointer"]) == labels["gp_handler"] + 1
            handler_guard = debug.breakpoint(com_address(info, labels["gp_handler"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert completion_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            assert handler_guard["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            complete = debug.registers()
            fields = {
                name: _u32(_qemu_read(debug, psp * 16 + labels[name], 4))
                for name in ("final_eax", "fault_eax", "fault_error", "fault_eip",
                             "fault_cs", "fault_eflags", "fault_marker", "completion_marker")
            }
            return dict(first_stop="handler", frame=frame, source_value=source_value,
                        complete_ip=_number(complete["instruction_pointer"]),
                        completion_ip=labels["completion_stop"], **fields)


def _assert_fault_and_retry(result, labels):
    assert result["first_stop"] == "handler", result
    frame = result["frame"]
    assert _u32(frame[0:4]) == 0, result
    assert _u32(frame[4:8]) == labels["scalar_ip"], result
    assert _u32(frame[8:12]) == 8, result
    assert _u32(frame[12:16]) == result["fault_eflags"], result
    assert result["fault_eax"] == FAULT_EAX, result
    assert result["fault_error"] == 0, result
    assert result["fault_eip"] == labels["scalar_ip"], result
    assert result["fault_cs"] == 8, result
    assert result["source_value"] == MEMORY_VALUE, result
    assert result["fault_marker"] == FAULT_MARKER_VALUE, result
    assert result["complete_ip"] == result["completion_ip"], result
    assert result["final_eax"] == MEMORY_VALUE, result
    assert result["completion_marker"] == COMPLETION_MARKER_VALUE, result


@pytest.mark.parametrize("scalar_offset", [0x10000, 0xFFFE],
                         ids=["past-limit", "operand-straddles-limit"])
def test_native_qemu_dosbox_scalar_ds_limit_fault_and_retry(
        paired_runtime, tmp_path, scalar_offset):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode scalar fixture")
    code, labels = build(tmp_path / f"fixture-{scalar_offset:x}", nasm,
                         scalar_offset=scalar_offset)
    qemu = _qemu_observe(paired_runtime, paired_runtime["disk"],
                         tmp_path / f"qemu-case-{scalar_offset:x}", code, labels,
                         scalar_offset)
    dosbox = _dosbox_observe(paired_runtime, tmp_path / f"dosbox-case-{scalar_offset:x}",
                             code, labels, scalar_offset)

    # A QEMU completion-first outcome remains a hard failure; it is returned
    # above only so DOSBox-X's independent reference result is still captured.
    _assert_fault_and_retry(dosbox, labels)
    _assert_fault_and_retry(qemu, labels)
    # QEMU may set RF in the exception-pushed EFLAGS while DOSBox-X may not.
    # Preserve and validate each native frame separately; compare the stable
    # error/EIP/CS words without erasing that engine-specific flag evidence.
    assert qemu["frame"][:12] == dosbox["frame"][:12]
