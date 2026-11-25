"""Paired protected-mode INC rights fault, writable control, and reference result."""
from __future__ import annotations

from base64 import b64decode
from contextlib import closing
import os
import shutil
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.segment_rmw_fixture import (
    COMPLETION_MARKER_VALUE, FAULT_MARKER_VALUE, INCREMENTED_VALUE,
    INITIAL_REGISTERS, INITIAL_VALUE, RMW_OFFSET, build,
)
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record

_REGS = ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp")
_PRE_FIELDS = tuple(f"pre_{name}" for name in _REGS)
_FAULT_FIELDS = tuple(f"fault_{name}" for name in _REGS if name != "esp") + (
    "fault_esp", "fault_error", "fault_eip", "fault_cs", "fault_eflags",
    "fault_memory", "fault_ds", "fault_marker",
)
_FINAL_FIELDS = tuple(f"final_{name}" for name in _REGS) + (
    "final_eflags", "final_memory", "final_ds", "completion_marker",
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
    return {name: _reg(registers, name, "r" + name[1:]) & 0xFFFFFFFF
            for name in _REGS}


def _read_dosbox(call, address, length):
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
        assert remaining > 0, "DOSBox-X did not reach the protected-mode RMW breakpoint"
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


def _dosbox_observe(runtime, root, code, labels):
    game = root / "dosbox"
    game.mkdir(parents=True)
    (game / "RMW.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        started = rpc.call("session.start", {
            "target": {"command": "RMW.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = started["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=10000)

        def read(address, length):
            return _read_dosbox(call, address, length)

        entry = call("state.get_registers")
        psp = _reg(entry, "cs") & 0xFFFF
        ready_bp = _dosbox_bp(call, psp, labels["pm_ready"])
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == ready_bp["breakpoint_id"], stop
        ready = call("state.get_registers")
        assert ready["cpu_mode"] == "protected" and _reg(ready, "cs") == 8, ready
        call("breakpoints.delete", {"breakpoint_id": ready_bp["breakpoint_id"]})
        arm_bp = _dosbox_bp(call, 8, labels["arm_stop"])
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == arm_bp["breakpoint_id"], stop
        before_registers = call("state.get_registers")
        base = _u32(_read_dosbox(call, psp * 16 + labels["buffer_base"], 4))
        before_memory = _u32(_read_dosbox(call, base + RMW_OFFSET, 4))
        before_fields = _fields(read, psp, labels, _PRE_FIELDS + ("pre_eflags",))
        ds_before = _reg(before_registers, "ds")
        call("breakpoints.delete", {"breakpoint_id": arm_bp["breakpoint_id"]})
        handler_bp = _dosbox_bp(call, 8, labels["gp_handler"])
        completion_bp = _dosbox_bp(call, 8, labels["completion_stop"])
        stop = _dosbox_wait(call, call("execution.continue"))

        if stop["stop_reason"].get("breakpoint_id") != handler_bp["breakpoint_id"]:
            registers = call("state.get_registers")
            final_fields = _fields(read, psp, labels, _FINAL_FIELDS)
            backing = _u32(_read_dosbox(call, base + RMW_OFFSET, 4))
            return dict(first_stop="completion", stop=stop, registers=registers,
                        before_registers=before_registers, before_gprs=_snapshot(before_registers),
                        before_fields=before_fields, ds_before=ds_before,
                        before_memory=before_memory, backing=backing, final_fields=final_fields,
                        fault_marker=_u32(read(psp * 16 + labels["fault_marker"], 4)),
                        complete_ip=_number(registers["instruction_pointer"]))

        fault_registers = call("state.get_registers")
        esp = _reg(fault_registers, "esp", "rsp") & 0xFFFFFFFF
        frame = _read_dosbox(call, psp * 16 + esp, 16)
        backing_at_fault = _u32(_read_dosbox(call, base + RMW_OFFSET, 4))
        # DOSBox-X returns from its persistent breakpoint without re-stopping.
        stop = _dosbox_wait(call, call("execution.continue"))
        assert stop["stop_reason"].get("breakpoint_id") == completion_bp["breakpoint_id"], stop
        complete_registers = call("state.get_registers")
        fault_fields = _fields(read, psp, labels, _FAULT_FIELDS)
        final_fields = _fields(read, psp, labels, _FINAL_FIELDS)
        return dict(first_stop="handler", frame=frame,
                    before_registers=before_registers, before_gprs=_snapshot(before_registers),
                    before_fields=before_fields, ds_before=ds_before,
                    before_memory=before_memory, backing_at_fault=backing_at_fault,
                    fault_registers=fault_registers, fault_gprs=_snapshot(fault_registers),
                    fault_fields=fault_fields, final_fields=final_fields,
                    complete_registers=complete_registers,
                    final_gprs=_snapshot(complete_registers),
                    complete_ip=_number(complete_registers["instruction_pointer"]))


def _qemu_observe(runtime, root, code, labels):
    root.mkdir()
    source = root / "RMW.COM"
    source.write_bytes(code)
    project = Project.create(root / "rmw.fdb", source, image="com")
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
            arm_bp = debug.breakpoint(com_address(info, labels["arm_stop"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert arm_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            before_registers = debug.registers()
            read = lambda address, length: bytes.fromhex(
                debug.memory(address, length=length, space="physical")["hex"])
            base = _u32(read(psp * 16 + labels["buffer_base"], 4))
            before_memory = _u32(read(base + RMW_OFFSET, 4))
            before_fields = _fields(read, psp, labels, _PRE_FIELDS + ("pre_eflags",))
            ds_before = _reg(before_registers, "ds")
            debug.delete_breakpoint(arm_bp["breakpoint_id"])
            handler_bp = debug.breakpoint(com_address(info, labels["gp_handler"]))
            completion_bp = debug.breakpoint(com_address(info, labels["completion_stop"]))
            stop = debug.run(timeout_ms=15000)
            if (stop["outcome"] != "breakpoint" or
                    handler_bp["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"]):
                registers = debug.registers()
                return dict(first_stop="completion", stop=stop, registers=registers,
                            before_registers=before_registers, before_gprs=_snapshot(before_registers),
                            before_fields=before_fields, ds_before=ds_before,
                            before_memory=before_memory,
                            backing=_u32(read(base + RMW_OFFSET, 4)),
                            final_fields=_fields(read, psp, labels, _FINAL_FIELDS),
                            complete_ip=_number(registers["instruction_pointer"]))

            fault_registers = debug.registers()
            esp = _reg(fault_registers, "esp", "rsp") & 0xFFFFFFFF
            frame = read(psp * 16 + esp, 16)
            backing_at_fault = _u32(read(base + RMW_OFFSET, 4))
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            stepped = debug.step(timeout_ms=5000)
            assert stepped["outcome"] == "step", stepped
            handler_guard = debug.breakpoint(com_address(info, labels["gp_handler"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert completion_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            assert handler_guard["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            complete_registers = debug.registers()
            fault_fields = _fields(read, psp, labels, _FAULT_FIELDS)
            return dict(first_stop="handler", frame=frame,
                        before_registers=before_registers, before_gprs=_snapshot(before_registers),
                        before_fields=before_fields, ds_before=ds_before,
                        before_memory=before_memory, backing_at_fault=backing_at_fault,
                        fault_registers=fault_registers, fault_gprs=_snapshot(fault_registers),
                        fault_fields=fault_fields,
                        final_fields=_fields(read, psp, labels, _FINAL_FIELDS),
                        complete_registers=complete_registers,
                        final_gprs=_snapshot(complete_registers),
                        complete_ip=_number(complete_registers["instruction_pointer"]))


def _assert_pre_state(result, readonly):
    assert result["before_memory"] == INITIAL_VALUE, result
    expected = dict(INITIAL_REGISTERS)
    expected["esp"] = result["before_gprs"]["esp"]
    assert {key: result["before_gprs"][key] for key in expected} == expected, result
    before_flags = result["before_fields"]["pre_eflags"]
    reported_flags = _reg(result["before_registers"], "eflags", "rflags", "flags")
    assert ((before_flags ^ reported_flags) & ~(1 << 16)) == 0, result
    assert before_flags & 1 and not before_flags & (1 << 9), result
    assert result["ds_before"] == (0x20 if readonly else 0x18), result


def _assert_fault_leg(result, labels):
    assert result["first_stop"] == "handler", result
    _assert_pre_state(result, readonly=True)
    assert _number(result["before_registers"]["instruction_pointer"]) == labels["arm_stop"], result
    assert _u32(result["frame"][0:4]) == 0, result
    assert _u32(result["frame"][4:8]) == labels["inc_ip"], result
    assert _u32(result["frame"][8:12]) == 8, result
    assert _u32(result["frame"][12:16]) == result["fault_fields"]["fault_eflags"], result
    assert result["fault_fields"]["fault_error"] == 0, result
    assert result["fault_fields"]["fault_eip"] == labels["inc_ip"], result
    assert result["fault_fields"]["fault_cs"] == 8, result
    assert result["fault_fields"]["fault_ds"] == 0x20, result
    assert {key: value for key, value in result["fault_gprs"].items() if key != "esp"} == {
        key: value for key, value in result["before_gprs"].items() if key != "esp"
    }, result
    assert result["fault_fields"]["fault_esp"] == result["before_gprs"]["esp"], result
    for register in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        assert result["fault_fields"][f"fault_{register}"] == result["before_fields"][f"pre_{register}"], result
    assert result["fault_fields"]["fault_memory"] == INITIAL_VALUE, result
    assert result["backing_at_fault"] == INITIAL_VALUE, result
    assert result["fault_fields"]["fault_marker"] == FAULT_MARKER_VALUE, result
    pre_flags = result["before_fields"]["pre_eflags"]
    fault_flags = result["fault_fields"]["fault_eflags"]
    assert ((fault_flags ^ pre_flags) & ~(1 << 16)) == 0, result
    assert result["complete_ip"] == labels["completion_stop"], result
    # The fixture stores final EAX before using AX to record DS. Compare the
    # saved pre-instrumentation values, not EAX at the completion breakpoint.
    for register in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"):
        assert result["final_fields"][f"final_{register}"] == result["before_gprs"][register], result
    _assert_increment_result(result["final_fields"], writable_ds=0x18)


def _assert_increment_result(fields, writable_ds):
    assert fields["final_memory"] == INCREMENTED_VALUE, fields
    assert fields["final_ds"] == writable_ds, fields
    assert fields["completion_marker"] == COMPLETION_MARKER_VALUE, fields
    flags = fields["final_eflags"]
    # INC 7fffffffh => 80000000h sets OF, SF, AF, PF; clears ZF and
    # preserves the seeded CF=1 while IF remains clear.
    expected_set = (1 << 0) | (1 << 2) | (1 << 4) | (1 << 7) | (1 << 11)
    assert flags & expected_set == expected_set, fields
    assert not flags & (1 << 6), fields
    assert not flags & (1 << 9), fields


def _assert_dosbox_readonly_observation(result, labels):
    # The frozen DOSBox-X reference completes this read-only-segment RMW.
    assert result["first_stop"] == "completion", result
    _assert_pre_state(result, readonly=True)
    assert result["complete_ip"] == labels["completion_stop"], result
    assert _reg(result["registers"], "ds") == 0x20, result
    assert result["backing"] == INCREMENTED_VALUE, result
    assert result["fault_marker"] == 0, result
    _assert_increment_result(result["final_fields"], writable_ds=0x20)


def _assert_writable_control(result, labels):
    assert result["first_stop"] == "completion", result
    _assert_pre_state(result, readonly=False)
    assert result["complete_ip"] == labels["completion_stop"], result
    assert result["backing"] == INCREMENTED_VALUE, result
    assert result["final_fields"]["final_eax"] == result["before_gprs"]["eax"], result
    assert result["final_fields"]["final_ebx"] == result["before_gprs"]["ebx"], result
    assert result["final_fields"]["final_ecx"] == result["before_gprs"]["ecx"], result
    assert result["final_fields"]["final_edx"] == result["before_gprs"]["edx"], result
    assert result["final_fields"]["final_esi"] == result["before_gprs"]["esi"], result
    assert result["final_fields"]["final_edi"] == result["before_gprs"]["edi"], result
    assert result["final_fields"]["final_ebp"] == result["before_gprs"]["ebp"], result
    assert result["final_fields"]["final_esp"] == result["before_gprs"]["esp"], result
    _assert_increment_result(result["final_fields"], writable_ds=0x18)


@pytest.mark.parametrize("readonly", [True, False], ids=["read-only-ds", "writable-control"])
def test_native_qemu_dosbox_protected_mode_inc_dword_segment_rights(
        paired_runtime, tmp_path, readonly):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode RMW fixture")
    code, labels = build(tmp_path / ("readonly" if readonly else "writable"), nasm,
                         readonly=readonly)
    qemu = _qemu_observe(paired_runtime, tmp_path / "qemu", code, labels)
    dosbox = _dosbox_observe(paired_runtime, tmp_path / "dosbox", code, labels)
    if readonly:
        _assert_fault_leg(qemu, labels)
        _assert_dosbox_readonly_observation(dosbox, labels)
    else:
        _assert_writable_control(qemu, labels)
        _assert_writable_control(dosbox, labels)
