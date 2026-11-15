"""Actual DOS COM/MZ/TSR acceptance for the native QEMU process slice.

Supply FDISBULL_QEMU_DOS, FDISBULL_QEMU_DOS_BOOT_IMAGE,
FDISBULL_QEMU_DOS_MCOPY, and optionally FDISBULL_QEMU_DOS_FIRMWARE.
NASM selects an assembler for the authored larger probes. Required-native
flags turn missing inputs into failures; no vendor image is stored in Git.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import (
    BASELINE_CONFIG, BASELINE_MARKER, character_driver, com_exit, digest, large_mz_exit,
    maximum_com_exit, mz_exit, nested_exec,
    prepare_dos_baseline, relocated_module, remapped_int20, resident_com,
    startup_probe,
)


def number(value):
    return int(value, 0) if isinstance(value, str) else value


def live_word(registers, *names):
    for name in names:
        if name in registers["registers"]:
            return int(registers["registers"][name], 16) & 0xffff
    raise AssertionError("Native register is absent: " + "/".join(names))


@pytest.fixture(scope="module")
def process_runtime():
    required = any(os.environ.get(name) == "1" for name in (
        "FDISBULL_REQUIRE_QEMU_DOS", "FDISBULL_REQUIRE_QEMU_DOS_OS"))
    selected = {
        "executable": os.environ.get("FDISBULL_QEMU_DOS"),
        "boot_image": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": os.environ.get("FDISBULL_QEMU_DOS_MCOPY"),
        "nasm": os.environ.get("NASM") or shutil.which("nasm"),
    }
    missing = [name for name, value in selected.items() if not value]
    if missing:
        message = "Native DOS process inputs missing: " + ", ".join(missing)
        if required:
            pytest.fail(message)
        pytest.skip(message)
    # mcopy is commonly a multicall symlink to mtools. Preserve its invocation
    # name; resolving it before subprocess launch changes the selected command.
    result = {name: (Path(value).expanduser().absolute() if name == "mcopy"
                     else Path(value).expanduser().resolve(strict=True))
              for name, value in selected.items()}
    for name, path in result.items():
        assert path.is_file(), (name, path)
        if name != "boot_image":
            assert os.access(path, os.X_OK), (name, path)
    result["firmware"] = os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE")
    return result


@pytest.fixture(scope="module")
def process_disk(process_runtime, tmp_path_factory):
    directory = tmp_path_factory.mktemp("native-dos-process-baseline")
    return prepare_dos_baseline(
        process_runtime["boot_image"], directory / "dos-baseline.img",
        process_runtime["mcopy"],
    )


def launch_options(runtime, disk, **extra):
    options = dict(
        backend="qemu-dos", dos_boot_image=str(disk["image"]),
        dos_mcopy=str(runtime["mcopy"]), dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe", qemu_firmware=runtime["firmware"],
        boot_timeout_ms=15000,
    )
    options.update(extra)
    return options


def create_project(directory, code, *, mz=False, filename=None):
    directory = Path(directory)
    binary = directory / (filename or ("TARGET.EXE" if mz else "TARGET.COM"))
    binary.write_bytes(code)
    project = Project.create(
        directory / "program.fdb", binary, **({} if mz else {"image": "com"}))
    return binary, project


def process_record(debug):
    info = debug.dos_process_info()
    assert info["state"] == "active", info
    assert debug.contexts()["selected"] == "machine"
    status = debug.status()
    assert status["state"] == "stopped", status
    assert status["process"] == info
    return info


def com_address(info, offset):
    mapping = info["source_mapping"]
    # Native public addresses remain machine addresses, not static project PCs.
    return number(mapping["runtime_base"]) + offset - 0x100


def read_bytes(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space="physical")["hex"])


def assert_completion(debug, result, *, resident=False, exit_code=None):
    assert result["outcome"] == ("guest_tsr" if resident else "guest_exit"), result
    assert not result["timed_out"]
    process = result["process"]
    assert process["state"] == ("resident" if resident else "exited")
    assert process["termination"]["type"] == ("resident" if resident else "normal")
    if exit_code is not None:
        assert process["termination"]["code"] == exit_code
    # A completed DOS process is different from an exited emulator process.
    assert result["session"]["state"] == "stopped", result
    assert debug.status()["state"] == "stopped"
    assert debug.status()["process"] == process
    assert debug.dos_process_info() == process
    assert debug.vm.process.poll() is None
    return process


def test_native_com_original_entry_exit_and_persisted_evidence(
        tmp_path, process_runtime, process_disk):
    code = com_exit(37)
    binary, project = create_project(tmp_path, code, filename="ORIGINAL LONG NAME.COM")
    source_sha = hashlib.sha256(code).hexdigest()
    with project:
        with project.debugger(process_runtime["executable"], tmp_path,
                              **launch_options(process_runtime, process_disk)) as debug:
            info = process_record(debug)
            registers = debug.registers()
            psp = number(info["psp_segment"])
            entry = info["entry"]
            assert number(entry["cs"]) == psp
            assert number(entry["ip"]) == 0x100
            assert live_word(registers, "cs") == psp
            assert live_word(registers, "ds") == psp
            assert live_word(registers, "es") == psp
            assert number(registers["instruction_pointer"]) == 0x100
            assert number(registers["linear_pc"]) == psp * 16 + 0x100
            mapping = info["source_mapping"]
            assert number(mapping["static_base"]) == project.regions(1)[0].start
            assert number(mapping["runtime_base"]) == psp * 16 + 0x100
            assert mapping["module_size"] == len(code)
            assert read_bytes(debug, psp * 16, 2) == b"\xcd\x20"
            assert read_bytes(debug, psp * 16 + 0x100, len(code)) == code
            assert debug.metadata["source_sha256"] == source_sha
            trace = debug.trace("com-entry.json", count=1, timeout_ms=1000)
            assert trace["metadata"]["complete"]
            frame = debug.screenshot("com-entry.png")
            finished = assert_completion(
                debug, debug.run(timeout_ms=3000), exit_code=37)
            assert number(finished["psp_segment"]) == psp
            run_id, native = debug.run_id, debug.vm.process
        assert native.poll() is not None
    assert binary.read_bytes() == code
    assert digest(process_disk["image"]) == process_disk["prepared_sha256"]
    with Project(tmp_path / "program.fdb") as reopened:
        runs = reopened.debug_runs()
        assert runs["live_state_verified"] is False
        saved = next(run for run in runs["runs"] if run["id"] == run_id)
        assert saved["state"] == "exited"
        assert saved["metadata"]["source_sha256"] == source_sha
        events = [json.loads(row["evidence"]) for row in reopened.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? ORDER BY sequence",
            (run_id,))]
        exits = [event for event in events if event.get("outcome") == "guest_exit"]
        assert exits, "Live completion must also survive project reopening"
        assert exits[-1]["process"] == finished
        exported = tmp_path / "saved-com-entry.json"
        reopened.debug_export(trace["artifact"], exported)
        saved_trace = json.loads(exported.read_text())
        assert saved_trace["events"][0]["bytes"] == "90"
        assert number(saved_trace["events"][0]["address"]) == psp * 16 + 0x100
        picture = tmp_path / "saved-com-entry.png"
        reopened.debug_export(frame["artifact"], picture)
        assert picture.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_native_one_byte_ret_uses_dos_startup_stack(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, b"\xc3")
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        entry = info["entry"]
        stack = number(entry["ss"]) * 16 + number(entry["sp"])
        assert read_bytes(debug, stack, 2) == b"\x00\x00"
        assert read_bytes(debug, com_address(info, 0x100), 1) == b"\xc3"
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=0)


@pytest.mark.parametrize("high_load", [False, True], ids=["relocated", "high-load"])
def test_native_mz_uses_observed_load_segment_and_stack(
        high_load, tmp_path, process_runtime, process_disk):
    code, fixture = mz_exit(high_load=high_load)
    binary, project = create_project(tmp_path, code, mz=True)
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        registers = debug.registers()
        psp = number(info["psp_segment"])
        # The expected image segment comes from a live CS and our authored
        # header, independently of the implementation's reported source map.
        load_segment = live_word(registers, "cs") - fixture["relative_cs"]
        entry = info["entry"]
        assert number(entry["cs"]) == load_segment + fixture["relative_cs"]
        assert number(entry["ip"]) == fixture["entry_ip"]
        assert number(entry["ss"]) == load_segment + fixture["relative_ss"]
        assert number(entry["sp"]) == fixture["sp"]
        assert live_word(registers, "ss") == number(entry["ss"])
        assert live_word(registers, "rsp", "esp", "sp") == fixture["sp"]
        assert live_word(registers, "rax", "eax", "ax") == number(entry["ax"])
        assert live_word(registers, "ds") == psp
        assert live_word(registers, "es") == psp
        mapping = info["source_mapping"]
        assert number(mapping["load_segment"]) == load_segment
        assert number(mapping["runtime_base"]) == load_segment * 16
        assert number(mapping["static_base"]) == project.regions(1)[0].start
        assert mapping["module_size"] == fixture["module_size"]
        if high_load:
            assert load_segment > psp + 0x10, (load_segment, psp)
        else:
            assert number(entry["ss"]) != number(entry["cs"])
        expected = relocated_module(fixture, load_segment)
        assert read_bytes(debug, load_segment * 16, len(expected)) == expected
        assert read_bytes(debug, number(registers["linear_pc"]), 1) == b"\x90"
        assert_completion(
            debug, debug.run(timeout_ms=3000), exit_code=fixture["exit_code"])
    assert binary.read_bytes() == code


def test_native_psp_tail_fcbs_environment_and_dta_are_real_dos_state(
        tmp_path, process_runtime, process_disk):
    code, symbols = startup_probe(tmp_path, process_runtime["nasm"])
    _, project = create_project(tmp_path, code)
    tail = " ALPHA.TXT BRAVO.BIN /Q"
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk, dos_arguments=tail)) as debug:
        info = process_record(debug)
        psp = number(info["psp_segment"])
        stop = debug.breakpoint(com_address(info, symbols["finished_ip"]))
        result = debug.run(timeout_ms=3000)
        assert result["outcome"] == "breakpoint", result
        assert debug.dos_process_info()["state"] == "active"
        report = read_bytes(debug, com_address(info, symbols["report_ip"]),
                            symbols["report_size"])
        assert report[:4] == b"DPR2"
        ds, es, ss, sp, environment, parent, dta_segment, dta_offset, dos_ax, dos_bx = (
            struct.unpack_from("<10H", report, 4))
        assert ds == es == ss == psp
        assert sp == number(info["entry"]["sp"])
        assert environment != 0
        assert parent != psp
        assert (dta_segment, dta_offset) == (psp, 0x80)
        assert dos_ax & 0xff >= 3
        assert dos_bx >> 8 == 0xfd, "The required FreeDOS fixture must execute DOS"
        assert report[32] == len(tail)
        assert report[33:33 + len(tail)] == tail.encode("ascii")
        assert report[33 + len(tail)] == 13
        assert report[160:172] == b"\x00ALPHA   TXT"
        assert report[176:188] == b"\x00BRAVO   BIN"
        assert BASELINE_MARKER + b"\x00" in report[192:448]
        debug.delete_breakpoint(stop["breakpoint_id"])
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=0)
    assert digest(process_disk["image"]) == process_disk["prepared_sha256"]


def test_native_large_mz_verifies_every_loaded_byte_across_read_chunks(
        tmp_path, process_runtime, process_disk):
    code, fixture = large_mz_exit()
    assert fixture["module_size"] == 0x14000 > 65536
    binary, project = create_project(tmp_path, code, mz=True, filename="LARGE.EXE")
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        registers = debug.registers()
        load_segment = live_word(registers, "cs") - fixture["relative_cs"]
        base = load_segment * 16
        entry, mapping = info["entry"], info["source_mapping"]
        assert number(mapping["load_segment"]) == load_segment
        assert number(mapping["runtime_base"]) == base
        assert mapping["module_size"] == fixture["module_size"]
        assert number(entry["cs"]) == load_segment + fixture["relative_cs"]
        assert number(entry["ip"]) == fixture["entry_ip"]
        assert number(entry["ss"]) == load_segment + fixture["relative_ss"]
        assert live_word(registers, "ss") == number(entry["ss"])
        assert live_word(registers, "rsp", "esp", "sp") == fixture["sp"]
        assert number(entry["sp"]) == fixture["sp"]
        assert mapping["loader_writes"] == []
        expected = relocated_module(fixture, load_segment)
        # The public memory operation retains its per-request cap. Both the
        # entry validation and these independent reads must cover the tail.
        actual = b"".join(read_bytes(debug, base + offset,
                                    min(65536, len(expected) - offset))
                          for offset in range(0, len(expected), 65536))
        assert actual == expected
        assert actual[-len(fixture["tail"]):] == fixture["tail"]
        assert read_bytes(debug, number(registers["linear_pc"]), 1) == b"\x90"
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=42)
    assert binary.read_bytes() == code


@pytest.mark.parametrize("interrupt27", [False, True], ids=["int21-ah31", "int27"])
def test_native_tsr_retains_its_mcb_and_interrupt_handler(
        interrupt27, tmp_path, process_runtime, process_disk):
    code, symbols = resident_com(interrupt27=interrupt27)
    _, project = create_project(tmp_path, code)
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        active = process_record(debug)
        psp = number(active["psp_segment"])
        vector_address = symbols["interrupt"] * 4
        before = read_bytes(debug, vector_address, 4)
        finished = assert_completion(
            debug, debug.run(timeout_ms=3000), resident=True,
            exit_code=symbols["exit_code"])
        assert number(finished["psp_segment"]) == psp
        pointer = read_bytes(debug, vector_address, 4)
        offset, segment = struct.unpack("<HH", pointer)
        assert pointer != before
        assert (segment, offset) == (psp, symbols["handler_ip"])
        assert read_bytes(debug, segment * 16 + offset,
                          len(symbols["handler"])) == symbols["handler"]
        mcb = read_bytes(debug, (psp - 1) * 16, 16)
        assert mcb[0] in (ord("M"), ord("Z"))
        owner, paragraphs = struct.unpack_from("<HH", mcb, 1)
        assert owner == psp
        assert paragraphs >= symbols["paragraphs"]
        assert segment * 16 + offset < (psp + paragraphs) * 16


def test_native_nested_exec_does_not_complete_the_selected_parent(
        tmp_path, process_runtime, process_disk):
    code, symbols = nested_exec(tmp_path, process_runtime["nasm"])
    _, project = create_project(tmp_path, code, filename="PARENT.COM")
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        psp = number(info["psp_segment"])
        stop = debug.breakpoint(com_address(info, symbols["after_child_ip"]))
        result = debug.run(timeout_ms=4000)
        assert result["outcome"] == "breakpoint", result
        assert debug.dos_process_info()["state"] == "active"
        assert read_bytes(debug, com_address(info, symbols["marker_ip"]), 2) == b"\xef\xbe"
        assert read_bytes(debug, com_address(info, symbols["child_status_ip"]), 2) == b"\x25\x00"
        debug.delete_breakpoint(stop["breakpoint_id"])
        finished = assert_completion(
            debug, debug.run(timeout_ms=3000), exit_code=17)
        assert number(finished["psp_segment"]) == psp


def test_native_remapped_int20_is_not_a_fabricated_exit(
        tmp_path, process_runtime, process_disk):
    code, symbols = remapped_int20(tmp_path, process_runtime["nasm"])
    _, project = create_project(tmp_path, code)
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        stop = debug.breakpoint(com_address(info, symbols["park_ip"]))
        result = debug.run(timeout_ms=3000)
        assert result["outcome"] == "breakpoint", result
        assert read_bytes(debug, com_address(info, symbols["counter_ip"]), 2) == b"\x01\x00"
        assert debug.dos_process_info()["state"] == "active"
        debug.delete_breakpoint(stop["breakpoint_id"])
        bounded = debug.run(timeout_ms=40)
        assert bounded["outcome"] == "timeout" and bounded["timed_out"]
        assert debug.dos_process_info()["state"] == "active"


def test_native_loop_and_explicit_close_do_not_invent_guest_completion(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, b"\xeb\xfe")
    with project:
        with project.debugger(
                process_runtime["executable"], tmp_path,
                **launch_options(process_runtime, process_disk)) as debug:
            process_record(debug)
            result = debug.run(timeout_ms=40)
            assert result["outcome"] == "timeout" and result["timed_out"]
            assert debug.dos_process_info()["state"] == "active"
            assert not debug.dos_process_info().get("termination")
            native, run_id = debug.vm.process, debug.run_id
        assert native.poll() is not None
        events = [json.loads(row["evidence"]) for row in project.db.execute(
            "SELECT evidence FROM debug_events WHERE run=?", (run_id,))]
        assert not any(event.get("outcome") in ("guest_exit", "guest_tsr")
                       for event in events)


def test_native_changed_program_is_refused_before_qemu_spawn(
        tmp_path, process_runtime, process_disk):
    binary, project = create_project(tmp_path, com_exit(37))
    spawned = []
    with project:
        binary.write_bytes(com_exit(42))
        with pytest.raises((ValueError, DebuggerError), match="source|changed|hash|identity"):
            project.debugger(
                process_runtime["executable"], tmp_path, _on_spawn=spawned.append,
                **launch_options(process_runtime, process_disk))
        assert not spawned


def test_unreachable_startup_never_publishes_an_active_process(
        tmp_path, process_runtime):
    image_directory = tmp_path / "unready"
    image_directory.mkdir()
    disk = prepare_dos_baseline(
        process_runtime["boot_image"], image_directory / "unready.img",
        process_runtime["mcopy"],
        batch=b"@echo off\r\n:WAIT\r\ngoto WAIT\r\n")
    _, project = create_project(tmp_path, com_exit(37))
    spawned = []
    with project:
        with pytest.raises((ValueError, DebuggerError, TimeoutError),
                           match="ready|readiness|timed|timeout|startup|deadline"):
            project.debugger(
                process_runtime["executable"], tmp_path, _on_spawn=spawned.append,
                **launch_options(process_runtime, disk, boot_timeout_ms=1500))
        assert all(process.poll() is not None for process in spawned)
        assert not project._live_debuggers
    assert digest(disk["image"]) == disk["prepared_sha256"]


def test_native_process_info_is_exposed_through_retained_json_workspace(
        tmp_path, process_runtime, process_disk):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    _, project = create_project(tmp_path, com_exit(42))
    with project:
        pass
    database = tmp_path / "program.fdb"
    workspace = DebugWorkspace()

    def invoke(method, **params):
        reply = respond(
            {"method": method, "params": {"project": str(database), **params}},
            debugger=workspace)
        assert reply["ok"], reply
        return reply["result"]

    try:
        started = invoke(
            "debug-launch", executable=str(process_runtime["executable"]),
            game_dir=str(tmp_path), **launch_options(process_runtime, process_disk))
        run = started["run"]
        active = invoke("debug-dos-process", run=run)
        assert active["state"] == "active"
        assert invoke("debug-status", run=run)["process"] == active
        result = invoke("debug-run", run=run, timeout_ms=3000)
        assert result["outcome"] == "guest_exit", result
        assert result["process"]["termination"]["code"] == 42
        assert invoke("debug-dos-process", run=run) == result["process"]
        assert invoke("debug-stop", run=run)["process_reaped"]
    finally:
        workspace.close()


def test_native_preserved_config_initializes_and_registers_authored_sys_driver(
        tmp_path, process_runtime):
    driver, symbols = character_driver(tmp_path, process_runtime["nasm"])
    assert driver[symbols["init_seen"]:symbols["init_seen"] + 2] == b"\x00\x00"
    config = b"DEVICE=A:\\FDBTEST.SYS\r\n" + BASELINE_CONFIG
    image_directory = tmp_path / "with-driver"
    image_directory.mkdir()
    disk = prepare_dos_baseline(
        process_runtime["boot_image"], image_directory / "driver-dos.img",
        process_runtime["mcopy"], config=config,
        extra_files={"FDBTEST.SYS": driver})
    _, project = create_project(tmp_path, com_exit(37))
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, disk)) as debug:
        info = process_record(debug)
        observation = info["drivers"]
        assert observation["status"] == "observed", observation
        matches = [header for header in observation["headers"]
                   if header["name"] == symbols["name"]]
        assert len(matches) == 1, observation
        registered = matches[0]
        assert registered["character"] is True
        assert registered["attributes"] == 0x8000
        assert registered["strategy_offset"] == symbols["strategy"]
        assert registered["interrupt_offset"] == symbols["interrupt"]
        address = number(registered["address"])
        assert read_bytes(debug, address + 10, 8) == b"FDBTEST$"
        assert read_bytes(debug, address + symbols["init_seen"], 2) == b"\x5a\xa5"
        preserved = debug.metadata["process_disk"]["preserved_configuration"]["FDCONFIG.SYS"]
        assert preserved["size"] == len(config)
        assert preserved["sha256"] == hashlib.sha256(config).hexdigest()
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=37)
    assert digest(disk["image"]) == disk["prepared_sha256"]


def test_native_mz_loader_stack_word_has_exact_provenance(
        tmp_path, process_runtime, process_disk):
    # DOS EXEC load-only pushes the initial AX word before returning SS:SP.
    # In this valid high-load image that word overlaps initialized file bytes.
    # Its source is deliberately nonzero so ordinary zero padding cannot hide
    # the loader mutation. Only the exact documented write is accounted for.
    code, fixture = mz_exit(high_load=True, stack_word=0xbeef)
    binary, project = create_project(tmp_path, code, mz=True)
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        registers = debug.registers()
        load_segment = live_word(registers, "cs") - fixture["relative_cs"]
        mapping, entry = info["source_mapping"], info["entry"]
        base = load_segment * 16
        address = number(entry["ss"]) * 16 + number(entry["sp"]) - 2
        offset = address - base
        assert offset == 0x3fe
        assert number(entry["ax"]) == live_word(registers, "rax", "eax", "ax") == 0
        expected = bytearray(relocated_module(fixture, load_segment))
        assert expected[offset:offset + 2] == b"\xef\xbe"
        after = struct.pack("<H", number(entry["ax"]))
        writes = mapping["loader_writes"]
        assert writes == [{
            "kind": "load-only-initial-ax",
            "runtime_address": address,
            "file_offset": 64 + offset,
            "module_offset": offset,
            "before_hex": "efbe",
            "after_hex": after.hex(),
        }]
        expected[offset:offset + 2] = after
        assert read_bytes(debug, base, len(expected)) == bytes(expected)
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=42)
    assert binary.read_bytes() == code
    assert binary.read_bytes()[64 + offset:64 + offset + 2] == b"\xef\xbe"


def test_native_bad_return_report_invalidates_binding_and_reaps_machine(
        tmp_path, process_runtime, process_disk):
    from fdisbull.dos_process_helper import REPORT_MAGIC
    _, project = create_project(tmp_path, com_exit(37))
    with project:
        with project.debugger(
                process_runtime["executable"], tmp_path,
                **launch_options(process_runtime, process_disk)) as debug:
            active = process_record(debug)
            native, run_id = debug.vm.process, debug.run_id
            # Version 1's report begins four bytes into the helper COM, after
            # its entry jump. Assert the protocol magic before corrupting one
            # nonce byte through an ordinary guarded machine-memory write.
            report = number(active["parent_psp_segment"]) * 16 + 0x104
            assert read_bytes(debug, report, len(REPORT_MAGIC)) == REPORT_MAGIC
            address = report + 8
            before = read_bytes(debug, address, 1)
            changed = bytes([before[0] ^ 1])
            debug.write_memory(address, changed.hex(), expected_hex=before.hex(),
                               space="physical")
            with pytest.raises((ValueError, DebuggerError), match="nonce|report"):
                debug.run(timeout_ms=3000)
            assert native.poll() is not None
            failed = debug.dos_process_info()
            assert failed["state"] == "observation_failed", failed
            assert failed["capture_epoch"] != active["capture_epoch"]
            assert failed["source_mapping"]["live"] is False
            assert failed["source_mapping"]["live_ranges"] == []
            assert failed["termination"] is None
            saved = next(run for run in project.debug_runs()["runs"]
                         if run["id"] == run_id)["metadata"]["process"]
            assert saved["state"] == "observation_failed"
            assert saved["source_mapping"]["live"] is False
            assert saved["termination"] is None
    with Project(tmp_path / "program.fdb") as reopened:
        saved = next(run for run in reopened.debug_runs()["runs"]
                     if run["id"] == run_id)["metadata"]["process"]
        assert saved["state"] == "observation_failed"
        assert saved["source_mapping"]["live"] is False
        assert saved["termination"] is None


def test_native_maximum_com_accounts_for_both_exact_stack_writes(
        tmp_path, process_runtime, process_disk):
    code = maximum_com_exit(37)
    assert len(code) == 0xff00 and code[-4:] == b"\xef\xbe\xfe\xca"
    binary, project = create_project(tmp_path, code, filename="FULL.COM")
    with project, project.debugger(
            process_runtime["executable"], tmp_path,
            **launch_options(process_runtime, process_disk)) as debug:
        info = process_record(debug)
        entry, mapping = info["entry"], info["source_mapping"]
        psp = number(info["psp_segment"])
        base = psp * 16 + 0x100
        assert number(entry["ss"]) == psp
        assert number(entry["sp"]) == 0xfffe
        assert number(entry["ax"]) == live_word(debug.registers(), "rax", "eax", "ax") == 0
        assert number(mapping["runtime_base"]) == base
        assert mapping["module_size"] == len(code)
        writes = mapping["loader_writes"]
        assert len(writes) == 2
        by_kind = {write["kind"]: write for write in writes}
        assert set(by_kind) == {"com-near-return-zero", "load-only-initial-ax"}
        assert by_kind["com-near-return-zero"] == {
            "kind": "com-near-return-zero",
            "runtime_address": psp * 16 + 0xfffe,
            "file_offset": 0xfefe,
            "module_offset": 0xfefe,
            "before_hex": "feca",
            "after_hex": "0000",
        }
        assert by_kind["load-only-initial-ax"] == {
            "kind": "load-only-initial-ax",
            "runtime_address": psp * 16 + 0xfffc,
            "file_offset": 0xfefc,
            "module_offset": 0xfefc,
            "before_hex": "efbe",
            "after_hex": "0000",
        }
        assert read_bytes(debug, base, len(code)) == code[:-4] + b"\x00" * 4
        assert_completion(debug, debug.run(timeout_ms=3000), exit_code=37)
    assert binary.read_bytes() == code
