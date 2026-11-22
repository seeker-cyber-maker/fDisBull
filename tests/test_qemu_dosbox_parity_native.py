"""Paired public-API witnesses for native DOSBox and QEMU DOS processes.

These tests use the same authored DOS source bytes in both backends. Native execution is
opt-in because the DOSBox binary, QEMU binary, FreeDOS boot image, and mcopy
tool are supplied by the caller. The paired assertions compare the common
register, memory, breakpoint, single-step, source-preservation, and project
history outcomes; they do not claim full DOSBox/QEMU parity.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import (com_exit, mz_exit, nested_exec,
                                         prepare_dos_baseline, relocated_module)


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


def _memory_bytes(debug, linear, length, *, qemu):
    if qemu:
        return bytes.fromhex(debug.memory(linear, length=length, space="physical")["hex"])
    result = debug.call("memory.read", {
        "address": {"space": "linear", "offset": f"0x{linear:08x}"}, "length": length,
    })
    return base64.b64decode(result["data_base64"], validate=True)


def _exit_code(result, *, qemu):
    assert result["outcome"] == "guest_exit", result
    if qemu:
        return result["process"]["termination"]["code"]
    return result["session"]["stop_reason"]["guest_exit"]["requested_exit_code"]


def _owned_process(debug, *, qemu):
    return debug.vm.process if qemu else debug.rpc.process


def _observe_mz(project, runtime, directory, authored, *, qemu, record_property):
    session = (_launch_qemu(project, runtime, directory) if qemu
               else project.debugger(str(runtime["dosbox"]), directory))
    with session as debug:
        initial = debug.registers()
        psp = _word(initial, "ds")
        load = _word(initial, "cs") - authored["relative_cs"]
        assert psp == _word(initial, "es") and psp > 1
        assert _ip(initial) == authored["entry_ip"]
        assert _word(initial, "ss") - load == authored["relative_ss"]
        assert _word(initial, "sp", "esp", "rsp") == authored["sp"]
        psp_header = _memory_bytes(debug, 16 * psp, 2, qemu=qemu)
        assert psp_header == b"\xcd\x20"
        mcb = _memory_bytes(debug, 16 * (psp - 1), 5, qemu=qemu)
        mcb_owner, paragraphs = struct.unpack_from("<HH", mcb, 1)
        assert mcb[:1] in (b"M", b"Z") and mcb_owner == psp
        assert psp + 0x10 <= load < psp + paragraphs
        assert 16 * load + authored["module_size"] <= 16 * (psp + paragraphs)
        if qemu:
            info = debug.dos_process_info()
            assert int(str(info["psp_segment"]), 0) == psp
            assert int(str(info["source_mapping"]["load_segment"]), 0) == load
        module = _memory_bytes(debug, 16 * load, authored["module_size"], qemu=qemu)
        expected = relocated_module(authored, load)
        normalized = bytearray(module)
        if authored["high_load"]:
            assert load > psp + 0x10
            # The high-load image's initialized tail overlaps the loader's
            # SS:SP-2 word. Compare the actual change before projecting the
            # common program bytes. Its raw content is backend-specific.
            stack_offset = 16 * authored["relative_ss"] + authored["sp"] - 2
            assert stack_offset == len(module) - 2
            original_word = expected[stack_offset:]
            actual_word = module[stack_offset:]
            assert original_word == b"\xef\xbe" and actual_word != original_word
            if qemu:
                assert actual_word == struct.pack("<H", _word(initial, "ax", "eax", "rax"))
                assert info["source_mapping"]["loader_writes"] == [{
                    "kind": "load-only-initial-ax",
                    "runtime_address": 16 * load + stack_offset,
                    "file_offset": 64 + stack_offset,
                    "module_offset": stack_offset,
                    "before_hex": original_word.hex(),
                    "after_hex": actual_word.hex(),
                }]
            record_property(("qemu" if qemu else "dosbox") + "_initial_stack_word", actual_word.hex())
            normalized[stack_offset:] = original_word
        assert bytes(normalized) == expected
        for offset, segment in authored["relocations"]:
            address = 16 * segment + offset
            value = struct.unpack_from("<H", normalized, address)[0]
            struct.pack_into("<H", normalized, address, (value - load) & 0xffff)
        assert bytes(normalized) == authored["module"]
        # The first store completes before this independently authored
        # instruction boundary. Observe CPU, the changed data and the DOS exit.
        after_write = 0x20 + 12
        breakpoint = debug.breakpoint((16 * load if qemu else debug.static_base) + after_write)
        options = {} if qemu else {"fast_forward": True}
        stopped = debug.run(timeout_ms=5000, **options)
        assert stopped["outcome"] == "breakpoint", stopped
        at_store = debug.registers()
        assert _ip(at_store) == 12
        assert _word(at_store, "ds") - load == 7
        observed = _memory_bytes(debug, 16 * load + authored["written_offset"], 2, qemu=qemu)
        assert observed == b"\xef\xbe"
        debug.delete_breakpoint(breakpoint["breakpoint_id"])
        exit_code = _exit_code(debug.run(timeout_ms=5000, **options), qemu=qemu)
        assert exit_code == authored["exit_code"]
        child = _owned_process(debug, qemu=qemu)
    assert child.poll() is not None
    return dict(module_sha256=hashlib.sha256(normalized).hexdigest(),
                write=observed.hex(), exit=exit_code)


@pytest.mark.parametrize("high_load", [False, True], ids=["normal", "high-load-request"])
def test_paired_authored_mz_relocation_psp_mcb_write_and_exit(
        tmp_path, parity_inputs, high_load, record_property):
    code, authored = mz_exit(high_load=high_load, stack_word=0xbeef if high_load else None)
    source = tmp_path / "TARGET.EXE"
    source.write_bytes(code)
    with Project.create(tmp_path / "mz-parity.fdb", source) as project:
        project.analyze(max_instructions=64)
        dosbox = _observe_mz(project, parity_inputs, tmp_path, authored, qemu=False, record_property=record_property)
        qemu = _observe_mz(project, parity_inputs, tmp_path, authored, qemu=True, record_property=record_property)
        assert dosbox == qemu
        assert len(project.debug_runs()["runs"]) == 2
    assert source.read_bytes() == code
    assert hashlib.sha256(parity_inputs["boot_image"].read_bytes()).hexdigest() == parity_inputs["boot_sha256"]


def _observe_exec(project, runtime, directory, symbols, *, qemu):
    session = (_launch_qemu(project, runtime, directory) if qemu
               else project.debugger(str(runtime["dosbox"]), directory))
    with session as debug:
        initial = debug.registers()
        psp = _word(initial, "ds")
        assert _ip(initial) == _CODE_OFFSET
        assert psp == _word(initial, "cs")
        # The test compares the parent and child status separately. Stopping on
        # the child's exit as if the parent exited fails at the first barrier.
        native_base = 16 * psp + _CODE_OFFSET
        breakpoint_base = native_base if qemu else debug.static_base
        target = breakpoint_base + symbols["after_child_ip"] - _CODE_OFFSET
        breakpoint = debug.breakpoint(target, **({} if qemu else {"view": "execute"}))
        options = {} if qemu else {"fast_forward": True}
        stopped = debug.run(timeout_ms=5000, **options)
        assert stopped["outcome"] == "breakpoint", stopped
        parent = debug.registers()
        assert (_word(parent, "cs"), _ip(parent)) == (psp, symbols["after_child_ip"])
        marker = _memory_bytes(debug, 16 * psp + symbols["marker_ip"], 2, qemu=qemu)
        status = _memory_bytes(debug, 16 * psp + symbols["child_status_ip"], 2, qemu=qemu)
        assert (marker, status) == (b"\xef\xbe", b"\x25\x00")
        if qemu:
            assert debug.dos_process_info()["state"] == "active"
        debug.delete_breakpoint(breakpoint["breakpoint_id"])
        exit_code = _exit_code(debug.run(timeout_ms=5000, **options), qemu=qemu)
        assert exit_code == 17
        child = _owned_process(debug, qemu=qemu)
    assert child.poll() is not None
    return marker, status, exit_code


def test_paired_authored_nested_exec_keeps_the_selected_parent_until_its_exit(tmp_path, parity_inputs):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        message = "Paired nested EXEC requires an explicit NASM executable"
        if os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    code, symbols = nested_exec(tmp_path, nasm)
    source = tmp_path / "PARENT.COM"
    source.write_bytes(code)
    child = tmp_path / "CHILD.COM"
    child_code = com_exit(37)
    child.write_bytes(child_code)
    # The private disk fixture already supplies the same authored child.
    with Project.create(tmp_path / "exec-parity.fdb", source, image="com") as project:
        project.analyze(max_instructions=128)
        dosbox = _observe_exec(project, parity_inputs, tmp_path, symbols, qemu=False)
        qemu = _observe_exec(project, parity_inputs, tmp_path, symbols, qemu=True)
        assert dosbox == qemu
        assert len(project.debug_runs()["runs"]) == 2
    assert source.read_bytes() == code
    assert child.read_bytes() == child_code
    assert hashlib.sha256(parity_inputs["boot_image"].read_bytes()).hexdigest() == parity_inputs["boot_sha256"]


def _observe_explicit_pause(project, runtime, directory, *, qemu):
    session = (_launch_qemu(project, runtime, directory) if qemu
               else project.debugger(str(runtime["dosbox"]), directory))
    with session as debug:
        psp = _word(debug.registers(), "cs")
        runtime_base = 16 * psp + _CODE_OFFSET
        breakpoint_base = runtime_base if qemu else debug.static_base
        breakpoint = debug.breakpoint(breakpoint_base + _LOOP_OFFSET - _CODE_OFFSET)
        stopped = debug.run(timeout_ms=5000, **({} if qemu else {"fast_forward": True}))
        assert stopped["outcome"] == "breakpoint"
        assert _ip(debug.registers()) == _LOOP_OFFSET
        debug.delete_breakpoint(breakpoint["breakpoint_id"])

        if qemu:
            assert debug.resume()["state"] == "running"
            assert debug.status()["state"] == "running"
            assert debug.pause()["state"] == "stopped"
            assert debug.dos_process_info()["state"] == "active"
        else:
            continued = debug.call("execution.continue")
            running = debug.call("execution.wait", {
                "operation_id": continued["operation_id"], "timeout_ms": 10,
            })
            assert running["running"] is True
            pause = debug.call("execution.pause")
            observed = debug.call("execution.wait", {
                "operation_id": pause["operation_id"], "timeout_ms": 2000,
            })
            assert observed.get("running", False) is False
            assert observed.get("stop_reason", {}).get("kind")

        assert debug.status()["state"] == "stopped"
        after_pause = debug.registers()
        assert _ip(after_pause) == _LOOP_OFFSET
        data = _memory_bytes(debug, 16 * psp + _DATA_OFFSET, 2, qemu=qemu)
        assert data == _STEPPED_WORD.to_bytes(2, "little")
        child = _owned_process(debug, qemu=qemu)
        assert child.poll() is None
    assert child.poll() is not None
    return _ip(after_pause), data


def test_paired_com_resume_and_explicit_pause_keep_the_selected_process(
        tmp_path, parity_inputs):
    source = tmp_path / "TARGET.COM"
    code = _com_fixture()
    source.write_bytes(code)
    with Project.create(tmp_path / "pause-parity.fdb", source, image="com") as project:
        project.analyze(max_instructions=32)
        dosbox = _observe_explicit_pause(project, parity_inputs, tmp_path, qemu=False)
        qemu = _observe_explicit_pause(project, parity_inputs, tmp_path, qemu=True)
        assert dosbox == qemu
    assert source.read_bytes() == code
