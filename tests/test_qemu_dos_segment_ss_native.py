"""Paired protected-mode SS-limit #SS retry and in-range control witness."""
from __future__ import annotations

from base64 import b64decode
from contextlib import closing
import os
import shutil
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.segment_ss_fixture import (
    COMPLETION_MARKER_VALUE, CONTROL_OFFSET, FAULT_MARKER_VALUE, FAULT_OFFSET,
    INITIAL_REGISTERS, SS_LIMIT, STACK_POINTER, TARGET_VALUE, build,
)
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record

_GPRS = ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp")
_PRE_FIELDS = tuple(f"pre_{name}" for name in _GPRS) + ("pre_eflags",)
_FAULT_FIELDS = tuple(f"fault_{name}" for name in _GPRS if name != "esp") + (
    "fault_esp", "fault_error", "fault_eip", "fault_cs", "fault_eflags",
    "fault_memory", "fault_ss", "fault_marker",
)
_FINAL_FIELDS = tuple(f"final_{name}" for name in _GPRS) + (
    "final_eflags", "final_memory", "final_ss", "fault_marker", "completion_marker",
)


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


def _snapshot(registers):
    aliases = {"eax": "rax", "ebx": "rbx", "ecx": "rcx", "edx": "rdx",
               "esi": "rsi", "edi": "rdi", "ebp": "rbp", "esp": "rsp"}
    return {name: _reg(registers, name, aliases[name]) for name in _GPRS}


def _read_dosbox(call, address, length):
    packet = call("memory.read", {"address": {"space": "physical",
                                                "offset": f"0x{address:08x}"},
                                "length": length})
    data = b64decode(packet["data_base64"], validate=True)
    assert len(data) == length, packet
    return data


def _read_qemu(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space="physical")["hex"])


def _dosbox_wait(call, operation):
    deadline = time.monotonic() + 15
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, "DOSBox-X did not reach the protected-mode SS breakpoint"
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


def _fields(read, psp, labels, names):
    return {name: _u32(read(psp * 16 + labels[name], 4)) for name in names}


def _dosbox_observe(runtime, root, code, labels, faulting):
    game = root / "dosbox"
    game.mkdir(parents=True)
    (game / "SS.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        started = rpc.call("session.start", {
            "target": {"command": "SS.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = started["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=10000)

        entry = call("state.get_registers")
        psp = _reg(entry, "cs") & 0xFFFF
        ready_bp = _dosbox_bp(call, psp, labels["ss_ready"])
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == ready_bp["breakpoint_id"], stop
        ready = call("state.get_registers")
        assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
        assert _reg(ready, "ss") == 0x18, ready
        call("breakpoints.delete", {"breakpoint_id": ready_bp["breakpoint_id"]})
        arm_bp = _dosbox_bp(call, 8, labels["arm_stop"])
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == arm_bp["breakpoint_id"], stop
        before_registers = call("state.get_registers")
        read = lambda address, length: _read_dosbox(call, address, length)
        before_fields = _fields(read, psp, labels, _PRE_FIELDS)
        target_offset = FAULT_OFFSET if faulting else CONTROL_OFFSET
        before_memory = _u32(_read_dosbox(call, psp * 16 + target_offset, 4))
        call("breakpoints.delete", {"breakpoint_id": arm_bp["breakpoint_id"]})
        handler_bp = _dosbox_bp(call, 8, labels["ss_handler"])
        completion_bp = _dosbox_bp(call, 8, labels["completion_stop"])
        stop = _dosbox_wait(call, call("execution.continue"))
        if stop["stop_reason"].get("breakpoint_id") != handler_bp["breakpoint_id"]:
            registers = call("state.get_registers")
            final_fields = _fields(read, psp, labels, _FINAL_FIELDS)
            backing = _u32(_read_dosbox(call, psp * 16 + target_offset, 4))
            return dict(first_stop="completion", stop=stop, registers=registers,
                        before_registers=before_registers, before_gprs=_snapshot(before_registers),
                        before_fields=before_fields, before_memory=before_memory,
                        backing=backing, final_fields=final_fields,
                        complete_ip=_number(registers["instruction_pointer"]))

        fault_registers = call("state.get_registers")
        esp = _reg(fault_registers, "esp", "rsp") & 0xFFFFFFFF
        frame = _read_dosbox(call, psp * 16 + esp, 16)
        backing_at_fault = _u32(_read_dosbox(call, psp * 16 + target_offset, 4))
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == completion_bp["breakpoint_id"], stop
        complete_registers = call("state.get_registers")
        fault_fields = _fields(read, psp, labels, _FAULT_FIELDS)
        final_fields = _fields(read, psp, labels, _FINAL_FIELDS)
        return dict(first_stop="handler", frame=frame,
                    before_registers=before_registers, before_gprs=_snapshot(before_registers),
                    before_fields=before_fields, before_memory=before_memory,
                    fault_registers=fault_registers, fault_gprs=_snapshot(fault_registers),
                    fault_fields=fault_fields, backing_at_fault=backing_at_fault,
                    final_fields=final_fields, final_gprs=_snapshot(complete_registers),
                    complete_ip=_number(complete_registers["instruction_pointer"]))


def _qemu_observe(runtime, root, code, labels, faulting):
    root.mkdir()
    source = root / "SS.COM"
    source.write_bytes(code)
    project = Project.create(root / "ss.fdb", source, image="com")
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
            ready_bp = debug.breakpoint(com_address(info, labels["ss_ready"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert ready_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            ready = debug.registers()
            assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
            assert _reg(ready, "ss") == 0x18, ready
            debug.delete_breakpoint(ready_bp["breakpoint_id"])
            arm_bp = debug.breakpoint(com_address(info, labels["arm_stop"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert arm_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            before_registers = debug.registers()
            read = lambda address, length: _read_qemu(debug, address, length)
            before_fields = _fields(read, psp, labels, _PRE_FIELDS)
            target_offset = FAULT_OFFSET if faulting else CONTROL_OFFSET
            before_memory = _u32(read(psp * 16 + target_offset, 4))
            debug.delete_breakpoint(arm_bp["breakpoint_id"])
            handler_bp = debug.breakpoint(com_address(info, labels["ss_handler"]))
            completion_bp = debug.breakpoint(com_address(info, labels["completion_stop"]))
            stop = debug.run(timeout_ms=15000)
            if (stop["outcome"] != "breakpoint" or
                    handler_bp["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"]):
                registers = debug.registers()
                return dict(first_stop="completion", stop=stop, registers=registers,
                            before_registers=before_registers, before_gprs=_snapshot(before_registers),
                            before_fields=before_fields, before_memory=before_memory,
                            backing=_u32(read(psp * 16 + target_offset, 4)),
                            final_fields=_fields(read, psp, labels, _FINAL_FIELDS),
                            complete_ip=_number(registers["instruction_pointer"]))

            fault_registers = debug.registers()
            esp = _reg(fault_registers, "esp", "rsp") & 0xFFFFFFFF
            frame = read(psp * 16 + esp, 16)
            backing_at_fault = _u32(read(psp * 16 + target_offset, 4))
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            stepped = debug.step(timeout_ms=5000)
            assert stepped["outcome"] == "step", stepped
            handler_guard = debug.breakpoint(com_address(info, labels["ss_handler"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert completion_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            assert handler_guard["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            complete_registers = debug.registers()
            fault_fields = _fields(read, psp, labels, _FAULT_FIELDS)
            return dict(first_stop="handler", frame=frame,
                        before_registers=before_registers, before_gprs=_snapshot(before_registers),
                        before_fields=before_fields, before_memory=before_memory,
                        fault_registers=fault_registers, fault_gprs=_snapshot(fault_registers),
                        fault_fields=fault_fields, backing_at_fault=backing_at_fault,
                        final_fields=_fields(read, psp, labels, _FINAL_FIELDS),
                        final_gprs=_snapshot(complete_registers),
                        complete_ip=_number(complete_registers["instruction_pointer"]))


def _assert_pre(result, *, faulting):
    assert result["before_memory"] == TARGET_VALUE, result
    assert result["before_fields"]["pre_esp"] == STACK_POINTER, result
    assert result["before_gprs"]["esp"] == STACK_POINTER, result
    assert result["before_fields"]["pre_ebp"] == (FAULT_OFFSET if faulting else CONTROL_OFFSET), result
    for reg, value in INITIAL_REGISTERS.items():
        assert result["before_fields"][f"pre_{reg}"] == value, result
        assert result["before_gprs"][reg] == value, result
    pre_flags = result["before_fields"]["pre_eflags"]
    reported_flags = _reg(result["before_registers"], "eflags", "rflags", "flags")
    assert ((pre_flags ^ reported_flags) & ~(1 << 16)) == 0, result
    assert pre_flags & 1 and not pre_flags & (1 << 9), result


def _assert_ss_fault_retry(result, labels):
    assert result["first_stop"] == "handler", result
    _assert_pre(result, faulting=True)
    assert _number(result["before_registers"]["instruction_pointer"]) == labels["arm_stop"], result
    frame_bottom = result["fault_fields"]["fault_esp"] - 16
    assert frame_bottom == STACK_POINTER - 16, result
    assert frame_bottom >= 0 and frame_bottom + 15 <= SS_LIMIT, result
    assert _u32(result["frame"][0:4]) == 0, result
    assert _u32(result["frame"][4:8]) == labels["fault_ip"], result
    assert _u32(result["frame"][8:12]) == 8, result
    assert _u32(result["frame"][12:16]) == result["fault_fields"]["fault_eflags"], result
    assert result["fault_fields"]["fault_error"] == 0, result
    assert result["fault_fields"]["fault_eip"] == labels["fault_ip"], result
    assert result["fault_fields"]["fault_cs"] == 8, result
    assert result["fault_fields"]["fault_ss"] == 0x18, result
    assert {key: value for key, value in result["fault_gprs"].items() if key != "esp"} == {
        key: value for key, value in result["before_gprs"].items() if key != "esp"
    }, result
    for reg in INITIAL_REGISTERS:
        assert result["fault_fields"][f"fault_{reg}"] == result["before_fields"][f"pre_{reg}"], result
    assert result["fault_fields"]["fault_esp"] == STACK_POINTER, result
    assert result["fault_fields"]["fault_memory"] == TARGET_VALUE, result
    assert result["backing_at_fault"] == TARGET_VALUE, result
    assert result["fault_fields"]["fault_marker"] == FAULT_MARKER_VALUE, result
    pre_flags = result["before_fields"]["pre_eflags"]
    assert ((result["fault_fields"]["fault_eflags"] ^ pre_flags) & ~(1 << 16)) == 0, result
    assert result["complete_ip"] == labels["completion_stop"], result
    for reg in ("ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"):
        assert result["final_fields"][f"final_{reg}"] == result["before_fields"][f"pre_{reg}"], result
    assert result["final_fields"]["final_eax"] == TARGET_VALUE, result
    assert result["final_fields"]["final_memory"] == TARGET_VALUE, result
    assert result["final_fields"]["final_ss"] == 0x10, result
    assert result["final_fields"]["completion_marker"] == COMPLETION_MARKER_VALUE, result


def _assert_in_range_control(result, labels):
    assert result["first_stop"] == "completion", result
    _assert_pre(result, faulting=False)
    assert result["complete_ip"] == labels["completion_stop"], result
    assert result["backing"] == TARGET_VALUE, result
    assert result["final_fields"]["final_eax"] == TARGET_VALUE, result
    assert result["final_fields"]["final_memory"] == TARGET_VALUE, result
    assert result["final_fields"]["final_ss"] == 0x18, result
    assert result["final_fields"]["fault_marker"] == 0, result
    assert result["final_fields"]["completion_marker"] == COMPLETION_MARKER_VALUE, result
    for reg in ("ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"):
        assert result["final_fields"][f"final_{reg}"] == result["before_gprs"][reg], result
    assert result["final_fields"]["final_eflags"] == result["before_fields"]["pre_eflags"], result


def _assert_dosbox_limit_divergence(result, labels):
    # The frozen DOSBox-X reference completes the out-of-limit SS read.
    assert result["first_stop"] == "completion", result
    _assert_pre(result, faulting=True)
    assert result["complete_ip"] == labels["completion_stop"], result
    assert result["backing"] == TARGET_VALUE, result
    assert result["final_fields"]["final_eax"] == TARGET_VALUE, result
    assert result["final_fields"]["final_ss"] == 0x18, result
    assert result["final_fields"]["fault_marker"] == 0, result
    assert result["final_fields"]["completion_marker"] == COMPLETION_MARKER_VALUE, result
    assert result["final_fields"]["final_eflags"] == result["before_fields"]["pre_eflags"], result


@pytest.mark.parametrize("faulting", [True, False], ids=["outside-ss-limit", "in-range-control"])
def test_native_qemu_dosbox_protected_mode_ss_limit_read(
        paired_runtime, tmp_path, faulting):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode SS fixture")
    code, labels = build(tmp_path / ("fault" if faulting else "control"), nasm,
                         faulting=faulting)
    qemu = _qemu_observe(paired_runtime, tmp_path / "qemu", code, labels, faulting)
    dosbox = _dosbox_observe(paired_runtime, tmp_path / "dosbox", code, labels, faulting)
    if faulting:
        _assert_ss_fault_retry(qemu, labels)
        _assert_dosbox_limit_divergence(dosbox, labels)
    else:
        _assert_in_range_control(qemu, labels)
        _assert_in_range_control(dosbox, labels)
