"""Paired public-API witnesses for native DOSBox and QEMU DOS processes.

These tests use one authored COM source in both backends. Native execution is
opt-in because the DOSBox binary, QEMU binary, FreeDOS boot image, and mcopy
tool are supplied by the caller. The paired assertions compare the common
register, memory, breakpoint, single-step, source-preservation, and project
history outcomes; they do not claim full DOSBox/QEMU parity.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import prepare_dos_baseline


_CODE_OFFSET = 0x100
_DATA_OFFSET = 0x120
_INC_OFFSET = 0x106
_LOOP_OFFSET = 0x10A
_INITIAL_WORD = 0x1234
_STEPPED_WORD = 0x1235


def _com_fixture():
    # mov ax,1234h; mov [0120h],ax; inc word [0120h]; jmp $
    # The padding makes the data word part of the file-backed source view.
    code = bytes.fromhex("b83412a32001ff062001ebfe")
    return code.ljust(_DATA_OFFSET - _CODE_OFFSET + 2, b"\x90")


def _word(registers, *names):
    for name in names:
        value = None
        for values in (registers.get("registers", {}), registers.get("general", {}),
                       registers.get("segments", {}), registers):
            if name in values:
                value = values[name]
                break
        if value is not None:
            if isinstance(value, str):
                value = int(value, 16) if not value.lower().startswith("0x") else int(value, 0)
            return value & 0xFFFF
    raise AssertionError("Expected DOS register is unavailable: " + "/".join(names))


def _ip(registers):
    value = registers.get("instruction_pointer", registers.get("ip"))
    assert value is not None, registers
    if isinstance(value, str):
        return int(value, 16) if not value.lower().startswith("0x") else int(value, 0)
    return value


def _native_inputs():
    required = os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1"
    configured = {
        "dosbox": os.environ.get("FDISBULL_DOSBOX"),
        "qemu": os.environ.get("FDISBULL_QEMU_DOS"),
        "boot_image": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": os.environ.get("FDISBULL_QEMU_DOS_MCOPY") or shutil.which("mcopy"),
    }
    missing = [name for name, value in configured.items() if not value]
    if missing:
        message = "Paired DOS parity inputs missing: " + ", ".join(missing)
        if required:
            pytest.fail(message)
        pytest.skip(message)

    result = {
        "dosbox": Path(configured["dosbox"]).expanduser().resolve(strict=True),
        "qemu": Path(configured["qemu"]).expanduser().resolve(strict=True),
        "boot_image": Path(configured["boot_image"]).expanduser().resolve(strict=True),
        # Preserve the selected mtools command name when it is a multicall
        # symlink; resolving it can change mcopy's behavior.
        "mcopy": Path(configured["mcopy"]).expanduser().absolute(),
    }
    for name in ("dosbox", "qemu", "mcopy"):
        path = result[name]
        if not path.is_file() or not os.access(path, os.X_OK):
            pytest.fail(f"{name} must name an executable file: {path}")
    if not result["boot_image"].is_file():
        pytest.fail(f"boot_image must name a file: {result['boot_image']}")
    return result


@pytest.fixture
def parity_inputs(tmp_path):
    runtime = _native_inputs()
    boot_before = hashlib.sha256(runtime["boot_image"].read_bytes()).hexdigest()
    boot = prepare_dos_baseline(
        runtime["boot_image"], tmp_path / "paired-dos-baseline.img", runtime["mcopy"]
    )
    assert hashlib.sha256(runtime["boot_image"].read_bytes()).hexdigest() == boot_before
    runtime["boot"] = boot
    runtime["boot_sha256"] = boot_before
    return runtime


def _launch_qemu(project, runtime, directory):
    return project.debugger(
        str(runtime["qemu"]),
        directory,
        backend="qemu-dos",
        dos_boot_image=str(runtime["boot"]["image"]),
        dos_mcopy=str(runtime["mcopy"]),
        dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe",
        qemu_firmware=os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
        boot_timeout_ms=15000,
    )


def _observe_dosbox_controls(project, directory, runtime):
    source = directory / "AUTHORED PARITY.COM"
    before = _com_fixture()
    source_digest = hashlib.sha256(before).hexdigest()
    with project.debugger(str(runtime["dosbox"]), directory) as debug:
        # The legacy DOSBox session deliberately records no backend key in
        # run metadata; its public context is the DOS CPU. QEMU DOS selects the
        # machine context instead.
        assert debug.contexts()["selected"] == "dos-cpu"
        initial = debug.registers()
        assert _ip(initial) == _CODE_OFFSET
        assert _word(initial, "cs") == _word(initial, "ds")
        breakpoint = debug.breakpoint(debug.static_base + (_INC_OFFSET - _CODE_OFFSET))
        stopped = debug.run(timeout_ms=10000, fast_forward=True)
        assert stopped["outcome"] == "breakpoint", stopped
        at_inc = debug.registers()
        assert _ip(at_inc) == _INC_OFFSET
        assert _word(at_inc, "ax", "eax", "rax") == _INITIAL_WORD
        data_address = debug.static_base + (_DATA_OFFSET - _CODE_OFFSET)
        before_step = debug.memory(data_address, length=2)["hex"]
        assert before_step == _INITIAL_WORD.to_bytes(2, "little").hex()
        # DOSBox exposes single-step through its legacy RPC; QEMU exposes it as
        # the selected-vCPU session method.
        debug.call("execution.step", {"mode": "into"})
        after_step = debug.memory(data_address, length=2)["hex"]
        assert after_step == _STEPPED_WORD.to_bytes(2, "little").hex()
        run_id = debug.run_id
        target = debug.metadata.get("target")

    assert source.read_bytes() == before
    if target:
        assert not (directory / target).exists()
    runs = {row["id"]: row for row in project.debug_runs()["runs"]}
    assert runs[run_id]["state"] == "exited"
    assert runs[run_id]["metadata"]["source_sha256"] == source_digest
    return {
        "source_sha256": source_digest,
        "initial_ip": _CODE_OFFSET,
        "breakpoint_ip": _INC_OFFSET,
        "ax": _INITIAL_WORD,
        "memory_before_step": before_step,
        "memory_after_step": after_step,
    }


def _observe_qemu_controls(project, directory, runtime):
    source = directory / "AUTHORED PARITY.COM"
    before = _com_fixture()
    source_digest = hashlib.sha256(before).hexdigest()
    with _launch_qemu(project, runtime, directory) as debug:
        assert debug.metadata["backend"] == "qemu-dos"
        process = debug.dos_process_info()
        assert process["state"] == "active"
        mapping = process["source_mapping"]
        raw_base = mapping["runtime_base"]
        runtime_base = int(raw_base, 0) if isinstance(raw_base, str) else raw_base
        initial = debug.registers()
        assert _ip(initial) == _CODE_OFFSET
        assert _word(initial, "cs") == _word(initial, "ds")
        breakpoint = debug.breakpoint(runtime_base + (_INC_OFFSET - _CODE_OFFSET))
        stopped = debug.run(timeout_ms=10000)
        assert stopped["outcome"] == "breakpoint", stopped
        at_inc = debug.registers()
        assert _ip(at_inc) == _INC_OFFSET
        assert _word(at_inc, "ax", "eax", "rax") == _INITIAL_WORD
        data_address = runtime_base + (_DATA_OFFSET - _CODE_OFFSET)
        before_step = debug.memory(data_address, length=2, space="physical")["hex"]
        assert before_step == _INITIAL_WORD.to_bytes(2, "little").hex()
        debug.step(timeout_ms=3000)
        after_step = debug.memory(data_address, length=2, space="physical")["hex"]
        assert after_step == _STEPPED_WORD.to_bytes(2, "little").hex()
        run_id = debug.run_id
        process_handle = debug.vm.process
        assert breakpoint["breakpoint_id"] in debug.breakpoints

    assert process_handle.poll() is not None
    assert source.read_bytes() == before
    assert hashlib.sha256(runtime["boot_image"].read_bytes()).hexdigest() == runtime["boot_sha256"]
    runs = {row["id"]: row for row in project.debug_runs()["runs"]}
    assert runs[run_id]["state"] == "exited"
    assert runs[run_id]["metadata"]["source_sha256"] == source_digest
    return {
        "source_sha256": source_digest,
        "initial_ip": _CODE_OFFSET,
        "breakpoint_ip": _INC_OFFSET,
        "ax": _INITIAL_WORD,
        "memory_before_step": before_step,
        "memory_after_step": after_step,
    }


def test_paired_authored_com_core_register_memory_breakpoint_step_and_history(
        tmp_path, parity_inputs):
    code = _com_fixture()
    source = tmp_path / "AUTHORED PARITY.COM"
    source.write_bytes(code)
    source_hash = hashlib.sha256(code).hexdigest()
    with Project.create(tmp_path / "parity.fdb", source, image="com") as project:
        project.analyze(max_instructions=32)
        dosbox = _observe_dosbox_controls(project, tmp_path, parity_inputs)
        qemu = _observe_qemu_controls(project, tmp_path, parity_inputs)
        # Compare only behavior with a shared authored input and common public
        # contract. Address spaces, stop records, and clock/timing claims differ.
        assert dosbox == qemu
        assert dosbox["source_sha256"] == source_hash
        assert source.read_bytes() == code
        assert len(project.debug_runs()["runs"]) == 2


def test_paired_authored_com_guest_exit_code_when_freedos_is_available(
        tmp_path, parity_inputs):
    code = bytes.fromhex("b8254ccd21")  # mov ax,4c25h; int 21h
    # Match the already-accepted DOSBox guest-exit fixture's neutral filename.
    source = tmp_path / "TARGET.COM"
    source.write_bytes(code)
    source_hash = hashlib.sha256(code).hexdigest()
    with Project.create(tmp_path / "exit-parity.fdb", source, image="com") as project:
        project.analyze(max_instructions=100)
        dosbox_result = _run_exit_dosbox(project, parity_inputs, tmp_path)
        qemu_result = _run_exit_qemu(project, parity_inputs, tmp_path)
        assert dosbox_result == qemu_result == {
            "outcome": "guest_exit",
            "exit_code": 37,
            "source_sha256": source_hash,
        }
        assert source.read_bytes() == code


def _run_exit_dosbox(project, runtime, directory):
    source_hash = project.meta["source_sha256"]
    with project.debugger(str(runtime["dosbox"]), directory) as debug:
        result = debug.run(timeout_ms=5000, guest_ms=1000, fast_forward=True)
        assert result["outcome"] == "guest_exit", result
        info = result["session"]["stop_reason"]["guest_exit"]
        assert info["requested_exit_code"] == 37
        run_id = debug.run_id
    runs = {row["id"]: row for row in project.debug_runs()["runs"]}
    assert runs[run_id]["state"] == "exited"
    return {"outcome": "guest_exit", "exit_code": 37, "source_sha256": source_hash}


def _run_exit_qemu(project, runtime, directory):
    source_hash = project.meta["source_sha256"]
    with _launch_qemu(project, runtime, directory) as debug:
        result = debug.run(timeout_ms=5000)
        assert result["outcome"] == "guest_exit", result
        process = result["process"]
        assert process["termination"]["code"] == 37
        run_id = debug.run_id
    runs = {row["id"]: row for row in project.debug_runs()["runs"]}
    assert runs[run_id]["state"] == "exited"
    return {"outcome": "guest_exit", "exit_code": 37, "source_sha256": source_hash}
