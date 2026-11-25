"""QEMU rights fault paired with DOSBox-X's observed reference divergence."""
from __future__ import annotations

from base64 import b64decode
from contextlib import closing
import os
import shutil
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.segment_rights_fixture import (
    COMPLETION_MARKER_VALUE, FAULT_EAX, FAULT_MARKER_VALUE, INITIAL_VALUE,
    STORE_VALUE, build,
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
        assert remaining > 0, "DOSBox-X did not reach the segment-rights probe breakpoint"
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


def _dosbox_observe(runtime, root, code, labels):
    game = root / "dosbox"
    game.mkdir(parents=True)
    (game / "RIGHTS.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        started = rpc.call("session.start", {
            "target": {"command": "RIGHTS.COM", "arguments": []},
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
            return dict(first_stop="completion-or-other", stop=stop,
                        registers=call("state.get_registers"), psp=psp,
                        **_dosbox_completion_fields(call, psp, labels))

        fault = call("state.get_registers")
        assert fault["cpu_mode"] == "protected" and _reg(fault, "cs") == 8, fault
        assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
        esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
        frame = _dosbox_read(call, psp * 16 + esp, 16)
        buffer_base = _u32(_dosbox_read(call, psp * 16 + labels["buffer_base"], 4))
        backing_at_fault = _u32(_dosbox_read(call, buffer_base + 0x100, 4))

        # Keep an entry guard armed to prove the store is retried only once.
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == completion_bp["breakpoint_id"], stop
        complete = call("state.get_registers")
        fields = {
            name: _u32(_dosbox_read(call, psp * 16 + labels[name], 4))
            for name in ("fault_eax", "fault_error", "fault_eip", "fault_cs",
                         "fault_eflags", "fault_memory", "fault_ds", "fault_marker",
                         "final_value", "final_memory", "final_ds", "completion_marker")
        }
        return dict(first_stop="handler", frame=frame, backing_at_fault=backing_at_fault,
                    complete_ip=_number(complete["instruction_pointer"]),
                    completion_ip=labels["completion_stop"], **fields)


def _dosbox_completion_fields(call, psp, labels):
    buffer_base = _u32(_dosbox_read(call, psp * 16 + labels["buffer_base"], 4))
    names = ("fault_marker", "final_value", "final_memory", "final_ds",
             "completion_marker")
    fields = {name: _u32(_dosbox_read(call, psp * 16 + labels[name], 4))
              for name in names}
    fields["backing"] = _u32(_dosbox_read(call, buffer_base + 0x100, 4))
    return fields


def _qemu_observe(runtime, root, code, labels):
    root.mkdir()
    source = root / "RIGHTS.COM"
    source.write_bytes(code)
    project = Project.create(root / "rights.fdb", source, image="com")
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
                            registers=debug.registers(), psp=psp)

            fault = debug.registers()
            assert fault["cpu_mode"] == "protected" and _reg(fault, "cs") == 8, fault
            assert _number(fault["instruction_pointer"]) == labels["gp_handler"], fault
            esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
            frame = _qemu_read(debug, psp * 16 + esp, 16)
            buffer_base = _u32(_qemu_read(debug, psp * 16 + labels["buffer_base"], 4))
            backing_at_fault = _u32(_qemu_read(debug, buffer_base + 0x100, 4))

            # Remove the persistent entry breakpoint, step its CLI, then rearm
            # it as a guard while the handler repairs DS and retries the store.
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
            fields = {
                name: _u32(_qemu_read(debug, psp * 16 + labels[name], 4))
                for name in ("fault_eax", "fault_error", "fault_eip", "fault_cs",
                             "fault_eflags", "fault_memory", "fault_ds", "fault_marker",
                             "final_value", "final_memory", "final_ds", "completion_marker")
            }
            return dict(first_stop="handler", frame=frame, backing_at_fault=backing_at_fault,
                        complete_ip=_number(complete["instruction_pointer"]),
                        completion_ip=labels["completion_stop"], **fields)


def _assert_rights_fault_and_retry(result, labels):
    assert result["first_stop"] == "handler", result
    frame = result["frame"]
    assert _u32(frame[0:4]) == 0, result
    assert _u32(frame[4:8]) == labels["store_ip"], result
    assert _u32(frame[8:12]) == 8, result
    assert _u32(frame[12:16]) == result["fault_eflags"], result
    assert result["fault_eax"] == FAULT_EAX, result
    assert result["fault_error"] == 0, result
    assert result["fault_eip"] == labels["store_ip"], result
    assert result["fault_cs"] == 8, result
    assert result["fault_ds"] == 0x20, result
    assert result["backing_at_fault"] == INITIAL_VALUE, result
    assert result["fault_memory"] == INITIAL_VALUE, result
    assert result["fault_marker"] == FAULT_MARKER_VALUE, result
    assert result["complete_ip"] == result["completion_ip"], result
    assert result["final_ds"] == 0x18, result
    assert result["final_value"] == STORE_VALUE, result
    assert result["final_memory"] == STORE_VALUE, result
    assert result["completion_marker"] == COMPLETION_MARKER_VALUE, result


def _assert_dosbox_rights_divergence(result, labels):
    assert result["first_stop"] == "completion-or-other", result
    assert result["registers"]["cpu_mode"] == "protected", result
    assert _reg(result["registers"], "ds") == 0x20, result
    assert _number(result["registers"]["instruction_pointer"]) == labels["completion_stop"], result
    assert result["backing"] == STORE_VALUE, result
    assert result["fault_marker"] == 0, result
    assert result["final_value"] == STORE_VALUE, result
    assert result["final_memory"] == STORE_VALUE, result
    assert result["final_ds"] == 0x20, result
    assert result["completion_marker"] == COMPLETION_MARKER_VALUE, result


def test_native_qemu_readonly_ds_write_fault_vs_dosbox_reference_divergence(
        paired_runtime, tmp_path):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode rights fixture")
    code, labels = build(tmp_path / "fixture", nasm)
    qemu = _qemu_observe(paired_runtime, tmp_path / "qemu", code, labels)
    dosbox = _dosbox_observe(paired_runtime, tmp_path / "dosbox", code, labels)

    # DOSBox-X is the independent default reference. Its successful store
    # without entering the handler is recorded as a divergence, not parity.
    _assert_dosbox_rights_divergence(dosbox, labels)
    _assert_rights_fault_and_retry(qemu, labels)
