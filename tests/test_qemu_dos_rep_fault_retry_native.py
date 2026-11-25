"""Paired native protected-mode REP MOVSB #GP delivery and retry.

The authored COM fixture faults after two bytes, records the CPU frame in its
handler, widens DS, and retries. Assertions use stopped CPU and RAM state;
before-fetch records are not used as retirement evidence.
"""
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
from support.rep_fault_fixture import (
    COMPLETED_ECX, COMPLETED_EDI, COMPLETED_ESI, COMPLETION_MARKER_VALUE,
    DESTINATION_OFFSET, FAULT_ECX, FAULT_EDI, FAULT_ESI, FAULT_MARKER_VALUE,
    FAULT_PREFIX_DWORD, build,
)
from test_qemu_dos_before_fetch_trace_native import paired_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record


def _n(value):
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
                return _n(values[name])
    raise AssertionError((names, registers))


def _dword(data, offset=0):
    return int.from_bytes(data[offset:offset + 4], "little")


def _qemu_read(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space="physical")["hex"])


def _dosbox_read(call, address, length):
    packet = call("memory.read", {"address": {"space": "physical",
                                                "offset": f"0x{address:08x}"},
                                "length": length})
    data = b64decode(packet["data_base64"], validate=True)
    assert len(data) == length, packet
    return data


def _wait_dosbox(call, operation, *, timeout_ms=15000):
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, "DOSBox-X did not reach the requested PM breakpoint"
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


def _run_dosbox(runtime, directory, code, labels):
    game = directory / "dosbox"
    game.mkdir()
    (game / "REPFAULT.COM").write_bytes(code)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        start = rpc.call("session.start", {
            "target": {"command": "REPFAULT.COM", "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        sid = start["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": sid, **(params or {})}, timeout_ms=10000)

        entry = call("state.get_registers")
        assert entry["cpu_mode"] == "real", entry
        psp = _reg(entry, "cs") & 0xFFFF
        pm_ready = _dosbox_bp(call, psp, labels["pm_ready"])
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == pm_ready["breakpoint_id"], stop
        ready = call("state.get_registers")
        assert ready["cpu_mode"] == "protected", ready
        assert ready["address_context"]["code_bits"] == 32, ready["address_context"]
        assert _reg(ready, "cs") == 8, ready
        call("breakpoints.delete", {"breakpoint_id": pm_ready["breakpoint_id"]})

        # Install native linear breakpoint requests via RPC. The source-level
        # DOSBox debugger wrapper correctly refuses protected-mode addresses.
        handler_bp = _dosbox_bp(call, 8, labels["gp_handler"])
        completion_bp = _dosbox_bp(call, 8, labels["completion_stop"])
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == handler_bp["breakpoint_id"], stop
        fault = call("state.get_registers")
        assert fault["cpu_mode"] == "protected", fault
        assert _reg(fault, "cs") == 8, fault
        assert _reg(fault, "cx", "ecx") & 0xFFFFFFFF == FAULT_ECX, fault
        assert _reg(fault, "esi", "rsi") & 0xFFFFFFFF == FAULT_ESI, fault
        assert _reg(fault, "edi", "rdi") & 0xFFFFFFFF == FAULT_EDI, fault
        assert _n(fault["instruction_pointer"]) == labels["gp_handler"], fault

        esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
        stack_base = psp * 16
        frame = _dosbox_read(call, stack_base + esp, 16)
        assert _dword(frame, 0) == 0
        assert _dword(frame, 4) == labels["rep_ip"]
        assert _dword(frame, 8) == 8
        saved_eflags = _dword(frame, 12)
        assert saved_eflags & 0x2, hex(saved_eflags)
        buffer_base = _dword(_dosbox_read(call, stack_base + labels["buffer_base"], 4))
        destination_before = _dosbox_read(call, buffer_base + DESTINATION_OFFSET, 4)
        assert int.from_bytes(destination_before, "little") == FAULT_PREFIX_DWORD

        # Leave the handler breakpoint armed so a second #GP fails this run
        # instead of being silently accepted as completion.
        stop = _wait_dosbox(call, call("execution.continue"))
        assert stop["stop_reason"]["breakpoint_id"] == completion_bp["breakpoint_id"], stop
        complete = call("state.get_registers")
        assert complete["cpu_mode"] == "protected", complete
        assert _n(complete["instruction_pointer"]) == labels["completion_stop"], complete
        metadata_base = stack_base
        fields = {
            "fault_error": _dword(_dosbox_read(call, metadata_base + labels["fault_error"], 4)),
            "fault_eip": _dword(_dosbox_read(call, metadata_base + labels["fault_eip"], 4)),
            "fault_cs": _dword(_dosbox_read(call, metadata_base + labels["fault_cs"], 4)),
            "fault_eflags": _dword(_dosbox_read(call, metadata_base + labels["fault_eflags"], 4)),
            "fault_ecx": _dword(_dosbox_read(call, metadata_base + labels["fault_ecx"], 4)),
            "fault_esi": _dword(_dosbox_read(call, metadata_base + labels["fault_esi"], 4)),
            "fault_edi": _dword(_dosbox_read(call, metadata_base + labels["fault_edi"], 4)),
            "fault_destination": _dword(_dosbox_read(call, metadata_base + labels["fault_destination"], 4)),
            "fault_marker": _dword(_dosbox_read(call, metadata_base + labels["fault_marker"], 4)),
            "final_ecx": _dword(_dosbox_read(call, metadata_base + labels["final_ecx"], 4)),
            "final_esi": _dword(_dosbox_read(call, metadata_base + labels["final_esi"], 4)),
            "final_edi": _dword(_dosbox_read(call, metadata_base + labels["final_edi"], 4)),
            "completion_marker": _dword(_dosbox_read(call, metadata_base + labels["completion_marker"], 4)),
        }
        destination_after = _dosbox_read(call, buffer_base + DESTINATION_OFFSET, 4)
        return dict(frame=frame, fields=fields, destination_before=destination_before,
                    destination_after=destination_after, psp=psp)


def _run_qemu(runtime, directory, disk, code, labels):
    directory.mkdir()
    source = directory / "REPFAULT.COM"
    source.write_bytes(code)
    project = Project.create(directory / "rep-fault.fdb", source, image="com")
    with project:
        project.analyze(max_instructions=256)
        game = directory / "qemu"
        game.mkdir()
        (game / source.name).write_bytes(code)
        options = launch_options({
            "executable": str(runtime["qemu"]),
            "mcopy": os.environ["FDISBULL_QEMU_DOS_MCOPY"],
            "firmware": runtime["firmware"],
        }, runtime["disk"])
        with project.debugger(str(runtime["qemu"]), game, **options) as debug:
            info = process_record(debug)
            pm_ready_bp = debug.breakpoint(com_address(info, labels["pm_ready"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert pm_ready_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            ready = debug.registers()
            assert ready["cpu_mode"] == "protected", ready
            assert ready["address_state"]["code_bits"] == 32, ready["address_state"]
            assert _reg(ready, "cs") == 8, ready
            debug.delete_breakpoint(pm_ready_bp["breakpoint_id"])

            handler_bp = debug.breakpoint(com_address(info, labels["gp_handler"]))
            completion_bp = debug.breakpoint(com_address(info, labels["completion_stop"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            if handler_bp["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"]:
                observed = debug.registers()
                psp_base = (_reg(info, "psp_segment") & 0xFFFF) * 16
                allocated_base = _dword(_qemu_read(debug, psp_base + labels["buffer_base"], 4))
                raise AssertionError(dict(
                    stop=stop["session"]["stop_reason"],
                    ecx=_reg(observed, "rcx"), esi=_reg(observed, "rsi"),
                    edi=_reg(observed, "rdi"),
                    ds=observed.get("address_state", {}).get("segments", {}).get("ds"),
                    destination=_qemu_read(debug, allocated_base + DESTINATION_OFFSET, 4).hex(),
                ))
            fault = debug.registers()
            assert fault["cpu_mode"] == "protected", fault
            assert _reg(fault, "cs") == 8, fault
            assert _reg(fault, "cx", "ecx", "rcx") & 0xFFFFFFFF == FAULT_ECX, fault
            assert _reg(fault, "esi", "rsi") & 0xFFFFFFFF == FAULT_ESI, fault
            assert _reg(fault, "edi", "rdi") & 0xFFFFFFFF == FAULT_EDI, fault
            assert _n(fault["instruction_pointer"]) == labels["gp_handler"], fault

            esp = _reg(fault, "esp", "rsp") & 0xFFFFFFFF
            psp = _reg(info, "psp_segment") & 0xFFFF
            frame = _qemu_read(debug, psp * 16 + esp, 16)
            assert _dword(frame, 0) == 0
            assert _dword(frame, 4) == labels["rep_ip"]
            assert _dword(frame, 8) == 8
            saved_eflags = _dword(frame, 12)
            assert saved_eflags & 0x2, hex(saved_eflags)
            metadata_base = psp * 16
            buffer_base = _dword(_qemu_read(
                debug, metadata_base + labels["buffer_base"], 4))
            destination_before = _qemu_read(debug, buffer_base + DESTINATION_OFFSET, 4)
            assert int.from_bytes(destination_before, "little") == FAULT_PREFIX_DWORD

            # QEMU's persistent execution breakpoint re-stops at the same
            # handler PC on continue. Step the first CLI, then rearm it so a
            # second #GP remains distinguishable from successful retry.
            debug.delete_breakpoint(handler_bp["breakpoint_id"])
            first_handler_step = debug.step(timeout_ms=5000)
            assert first_handler_step["outcome"] == "step", first_handler_step
            assert _n(debug.registers()["instruction_pointer"]) == labels["gp_handler"] + 1
            handler_guard = debug.breakpoint(com_address(info, labels["gp_handler"]))
            stop = debug.run(timeout_ms=15000)
            assert stop["outcome"] == "breakpoint", stop
            assert completion_bp["breakpoint_id"] in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            assert handler_guard["breakpoint_id"] not in stop["session"]["stop_reason"]["breakpoint_ids"], stop
            complete = debug.registers()
            assert complete["cpu_mode"] == "protected", complete
            assert _n(complete["instruction_pointer"]) == labels["completion_stop"], complete
            fields = {
                name: _dword(_qemu_read(debug, metadata_base + labels[name], 4))
                for name in (
                    "fault_error", "fault_eip", "fault_cs", "fault_eflags",
                    "fault_ecx", "fault_esi", "fault_edi", "fault_destination",
                    "fault_marker", "final_ecx", "final_esi", "final_edi",
                    "completion_marker",
                )
            }
            destination_after = _qemu_read(debug, buffer_base + DESTINATION_OFFSET, 4)
    assert source.read_bytes() == code
    return dict(frame=frame, fields=fields, destination_before=destination_before,
                destination_after=destination_after, psp=psp)


def test_native_qemu_dosbox_protected_rep_movsb_gp_retry_and_completion(
        paired_runtime, tmp_path):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        pytest.skip("NASM is required for the authored protected-mode COM fixture")
    code, labels = build(tmp_path / "fixture", nasm)
    dosbox = _run_dosbox(paired_runtime, tmp_path, code, labels)
    qemu = _run_qemu(paired_runtime, tmp_path / "qemu", paired_runtime["disk"], code, labels)

    for result in (qemu, dosbox):
        assert _dword(result["frame"], 0) == 0, result
        assert _dword(result["frame"], 4) == labels["rep_ip"], result
        assert _dword(result["frame"], 8) == 8, result
        assert _dword(result["frame"], 12) == result["fields"]["fault_eflags"], result
        assert result["fields"]["fault_error"] == 0, result
        assert result["fields"]["fault_eip"] == labels["rep_ip"], result
        assert result["fields"]["fault_cs"] == 8, result
        assert result["fields"]["fault_ecx"] == FAULT_ECX, result
        assert result["fields"]["fault_esi"] == FAULT_ESI, result
        assert result["fields"]["fault_edi"] == FAULT_EDI, result
        assert result["fields"]["fault_destination"] == FAULT_PREFIX_DWORD, result
        assert result["fields"]["fault_marker"] == FAULT_MARKER_VALUE, result
        assert result["destination_before"] == b"AB\0\0", result
        assert result["fields"]["final_ecx"] == COMPLETED_ECX, result
        assert result["fields"]["final_esi"] == COMPLETED_ESI, result
        assert result["fields"]["final_edi"] == COMPLETED_EDI, result
        assert result["fields"]["completion_marker"] == COMPLETION_MARKER_VALUE, result
        assert result["destination_after"] == b"ABCD", result

    # The native engines may set RF differently in the fault-pushed EFLAGS.
    # Retain each full frame above; compare the stable error/EIP/CS words and
    # all guest-visible handler state except that one recorded flags word.
    assert qemu["frame"][:12] == dosbox["frame"][:12]
    assert {k: v for k, v in qemu["fields"].items() if k != "fault_eflags"} == {
        k: v for k, v in dosbox["fields"].items() if k != "fault_eflags"
    }
