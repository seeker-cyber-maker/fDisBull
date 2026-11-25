"""Trace epoch invalidation across hot and cold DOS process restores.

Opt in with FDISBULL_QEMU_TRACE and the standard DOS process checkpoint
inputs. The COM program is authored here; boot media and runtime artifacts
stay in pytest's private temporary directory.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import prepare_dos_baseline
from test_qemu_dos_before_fetch_trace_native import _event_offset
from test_qemu_dos_process_native import com_address, process_record


PROGRAM = bytes.fromhex("b9010040ebfe")  # MOV CX,1; INC AX; JMP $


def _runtime():
    candidate = os.environ.get("FDISBULL_QEMU_TRACE")
    values = {
        "FDISBULL_QEMU_TRACE": candidate,
        "FDISBULL_QEMU_DOS_BOOT_IMAGE": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "FDISBULL_QEMU_DOS_MCOPY": os.environ.get("FDISBULL_QEMU_DOS_MCOPY"),
        "FDISBULL_QEMU_DOS_FIRMWARE": os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
        "FDISBULL_QEMU_IMG": os.environ.get("FDISBULL_QEMU_IMG"),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        pytest.skip("Trace checkpoint test needs selected native inputs: " + ", ".join(missing))
    executable = Path(candidate).expanduser().resolve(strict=True)
    assert executable.is_file() and os.access(executable, os.X_OK), executable
    for key, value in values.items():
        if key == "FDISBULL_QEMU_DOS_FIRMWARE":
            assert Path(value).expanduser().is_dir(), key
        elif key != "FDISBULL_QEMU_TRACE":
            path = Path(value).expanduser().absolute() if key.endswith("MCOPY") else Path(value).expanduser().resolve(strict=True)
            assert path.is_file(), (key, path)
            if key.endswith("MCOPY"):
                assert os.access(path, os.X_OK), (key, path)
    return {
        "executable": executable,
        "mcopy": values["FDISBULL_QEMU_DOS_MCOPY"],
        "firmware": values["FDISBULL_QEMU_DOS_FIRMWARE"],
        "qemu_img": values["FDISBULL_QEMU_IMG"],
        "boot_image": Path(values["FDISBULL_QEMU_DOS_BOOT_IMAGE"]).expanduser().resolve(strict=True),
    }


def _launch(project, runtime, directory, disk):
    return project.debugger(
        str(runtime["executable"]), directory, backend="qemu-dos",
        dos_boot_image=str(disk["image"]), dos_mcopy=str(runtime["mcopy"]),
        dos_startup_batch="FDAUTO.BAT", qemu_transport="pipe",
        qemu_firmware=runtime["firmware"], qemu_checkpoint_tool=runtime["qemu_img"],
        boot_timeout_ms=30000,
    )


def _assert_fresh_inc(debug, info, old_epoch=None):
    started = debug.call("trace.start", {"detail": "normal", "instruction_count": 2})
    assert started.get("active") is True, started
    if old_epoch is not None:
        assert started.get("epoch") != old_epoch, started
    assert debug.step(timeout_ms=5000)["outcome"] == "step"
    page = debug.call("trace.read", {"cursor": None, "limit": 4})
    events = page["events"]
    assert len(events) == 1, page
    event = events[0]
    assert _event_offset(event, runtime_base=com_address(info, 0x100)) == 0x103, event
    native = event["native"]
    assert native["origin"] == "tcg-dispatch", event
    assert native["code-bytes-valid"] is True, event
    assert native["code-bytes"] == "40", event
    assert native["code-byte-count"] == 1, event
    assert native["code-bytes-source"] == "translated-tb", event
    assert native["code-bits"] == 16 and native["x86-context-valid"] is True, event
    runtime_base = com_address(info, 0x100)
    assert native["cs-base"] == runtime_base - 0x100, event
    assert native["cs-selector"] == (runtime_base - 0x100) // 16, event
    assert event["fetch_context"]["translated_bytes"] == dict(
        valid=True, hex="40", count=1, source="translated-tb", unavailable_reason=None)
    assert event["fetch_context"]["x86"]["valid"] is True
    assert page.get("epoch") == started.get("epoch"), page
    stopped = debug.call("trace.stop")
    assert stopped.get("active") is False, stopped
    return started


def test_checkpoint_restore_invalidates_trace_cursor_and_rearms_fresh_epoch(tmp_path):
    runtime = _runtime()
    disk = prepare_dos_baseline(
        runtime["boot_image"], tmp_path / "baseline.img", runtime["mcopy"])
    source = tmp_path / "TRACE-CHECKPOINT.COM"
    source.write_bytes(PROGRAM)
    source_sha = hashlib.sha256(PROGRAM).hexdigest()
    database = tmp_path / "trace-checkpoint.fdb"
    artifact = None
    old_epoch = None

    with Project.create(database, source, image="com") as project:
        hot_dir = tmp_path / "hot"
        hot_dir.mkdir()
        (hot_dir / source.name).write_bytes(PROGRAM)
        with _launch(project, runtime, hot_dir, disk) as debug:
            info = process_record(debug)
            initial = debug.breakpoint(com_address(info, 0x103))
            first = debug.call("trace.start", {"detail": "normal", "instruction_count": 8})
            old_epoch = first["epoch"]
            run = debug.run(timeout_ms=10000)
            assert run["outcome"] == "breakpoint", run
            assert initial["breakpoint_id"] in run["session"]["stop_reason"]["breakpoint_ids"]
            first_page = debug.call("trace.read", {"cursor": None, "limit": 1})
            assert len(first_page["events"]) == 1 and first_page["next_cursor"], first_page
            old_cursor = first_page["next_cursor"]
            debug.delete_breakpoint(initial["breakpoint_id"])
            before_save = debug.call("trace.read", {"cursor": old_cursor, "limit": 4})
            assert len(before_save["events"]) == 1, before_save
            assert before_save["events"][0]["native"]["origin"] == "breakpoint-pre-dispatch"
            saved = debug.save_state()
            artifact = saved["artifact"]
            after_save = debug.call("trace.read", {"cursor": old_cursor, "limit": 4})
            assert after_save["epoch"] == old_epoch, after_save
            assert after_save["events"] == before_save["events"], after_save
            assert after_save["captured_count"] == before_save["captured_count"], after_save
            restore = debug.load_state(artifact)
            assert restore["source_binding_restored"] is True, restore
            restored_info = process_record(debug)
            assert restored_info["capture_epoch"] != info["capture_epoch"]
            assert bytes.fromhex(debug.memory(
                com_address(restored_info, 0x100), length=len(PROGRAM), space="physical")["hex"]) == PROGRAM
            with pytest.raises(DebuggerError, match="invalidated by machine replacement"):
                debug.call("trace.read", {"cursor": old_cursor, "limit": 4})
            fresh = _assert_fresh_inc(debug, restored_info, old_epoch)
            assert fresh["epoch"] != first["epoch"]
            with pytest.raises(DebuggerError, match="another capture epoch"):
                debug.call("trace.read", {"cursor": old_cursor, "limit": 4})

        # An independent owner loading the same artifact starts with no trace
        # primed in host memory; it must still arm and capture the restored COM.
        cold_dir = tmp_path / "cold"
        cold_dir.mkdir()
        (cold_dir / source.name).write_bytes(PROGRAM)
        with _launch(project, runtime, cold_dir, disk) as cold:
            cold.load_state(artifact)
            cold_info = process_record(cold)
            assert bytes.fromhex(cold.memory(
                com_address(cold_info, 0x100), length=len(PROGRAM), space="physical")["hex"]) == PROGRAM
            _assert_fresh_inc(cold, cold_info)
            with pytest.raises(DebuggerError, match="another capture epoch"):
                cold.call("trace.read", {"cursor": old_cursor, "limit": 4})

    assert source.read_bytes() == PROGRAM
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
