"""One narrow real-game comparison across DOSBox and native QEMU.

The opt-in test runs the repository's original, hash-pinned ATTT.COM with the
same physical Q key in both backends. It compares the loaded COM image's
startup and post-move bytes, including the documented Player 1 move. This
does not claim whole-game, rendering, or frame-timing equivalence.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline


_ATTT = Path(__file__).parents[1] / "fixtures/freeware-games/tic-tac-toe/original/learner/ATTT.COM"
_ATTT_SHA256 = "b582a31d28d9a265c38d29ed09dffe0396f47e6bf4497569766c036f6674fc43"
_BOARD_OFFSET = 3  # First of nine initialized space bytes, immediately after the entry jump.


def _number(value):
    return int(value, 0) if isinstance(value, str) else value


@pytest.fixture
def game_runtime(tmp_path):
    required = os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1"
    configured = {
        "dosbox": os.environ.get("FDISBULL_DOSBOX"),
        "qemu": os.environ.get("FDISBULL_QEMU_DOS"),
        "boot_image": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": os.environ.get("FDISBULL_QEMU_DOS_MCOPY") or shutil.which("mcopy"),
    }
    missing = [key for key, value in configured.items() if not value]
    if missing:
        message = "Native game parity inputs missing: " + ", ".join(missing)
        if required:
            pytest.fail(message)
        pytest.skip(message)
    result = {
        "dosbox": Path(configured["dosbox"]).expanduser().resolve(strict=True),
        "qemu": Path(configured["qemu"]).expanduser().resolve(strict=True),
        "boot_image": Path(configured["boot_image"]).expanduser().resolve(strict=True),
        # mcopy may be an mtools multicall symlink; preserve its invocation name.
        "mcopy": Path(configured["mcopy"]).expanduser().absolute(),
    }
    for key in ("dosbox", "qemu", "mcopy"):
        assert result[key].is_file() and os.access(result[key], os.X_OK), result[key]
    assert result["boot_image"].is_file(), result["boot_image"]
    source = _ATTT.read_bytes()
    assert hashlib.sha256(source).hexdigest() == _ATTT_SHA256
    source_copy = tmp_path / "ATTT.COM"
    source_copy.write_bytes(source)
    boot_before = hashlib.sha256(result["boot_image"].read_bytes()).hexdigest()
    result["boot"] = prepare_dos_baseline(
        result["boot_image"], tmp_path / "game-dos-baseline.img", result["mcopy"],
        config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG,
    )
    assert hashlib.sha256(result["boot_image"].read_bytes()).hexdigest() == boot_before
    result.update(source=source_copy, source_bytes=source, source_sha256=_ATTT_SHA256,
                  boot_sha256=boot_before)
    return result


def _launch_qemu(project, directory, runtime):
    return project.debugger(
        str(runtime["qemu"]), directory,
        backend="qemu-dos",
        dos_boot_image=str(runtime["boot"]["image"]),
        dos_mcopy=str(runtime["mcopy"]),
        dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe",
        qemu_firmware=os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
        qemu_clock="virtual",
        boot_timeout_ms=15000,
    )


def _read_dosbox_image(debug, length):
    return bytes.fromhex(debug.memory(debug.static_base, length=length)["hex"])


def _read_qemu_image(debug, length):
    process = debug.dos_process_info()
    assert process["state"] == "active", process
    base = _number(process["source_mapping"]["runtime_base"])
    return bytes.fromhex(debug.memory(base, length=length, space="physical")["hex"])


def _play_one_move(debug, key, *, qemu):
    receipt = debug.keyboard_press(key, hold_ms=80, gap_ms=80)
    assert receipt
    if qemu:
        # Each engine advances its own guest clock; no timer values are compared.
        result = debug.clock_advance(750_000_000, timeout_ms=5000)
        assert result["clock_budget"]["deadline_reached"], result
        assert result["input_delivery"]["state"] == "dispatched", result
    else:
        debug.run(timeout_ms=5000, guest_ms=750, fast_forward=True)


def _observe_dosbox(project, runtime, directory):
    with project.debugger(str(runtime["dosbox"]), directory) as debug:
        assert debug.contexts()["selected"] == "dos-cpu"
        startup = _read_dosbox_image(debug, len(runtime["source_bytes"]))
        _play_one_move(debug, "q", qemu=False)
        moved = _read_dosbox_image(debug, len(runtime["source_bytes"]))
        run_id = debug.run_id
    return {"startup": startup, "after_q": moved, "run_id": run_id}


def _observe_qemu(project, runtime, directory):
    with _launch_qemu(project, directory, runtime) as debug:
        process = debug.dos_process_info()
        assert process["state"] == "active", process
        startup = _read_qemu_image(debug, len(runtime["source_bytes"]))
        _play_one_move(debug, "q", qemu=True)
        moved = _read_qemu_image(debug, len(runtime["source_bytes"]))
        run_id = debug.run_id
        native = debug.vm.process
    assert native.poll() is not None
    return {"startup": startup, "after_q": moved, "run_id": run_id}


def test_original_tic_tac_toe_one_physical_move_has_paired_com_state(
        tmp_path, game_runtime):
    source = game_runtime["source"]
    original = game_runtime["source_bytes"]
    with Project.create(tmp_path / "attt-parity.fdb", source, image="com") as project:
        # Needed by the established DOSBox source projection before it starts.
        project.analyze(max_instructions=4096)
        dosbox = _observe_dosbox(project, game_runtime, tmp_path)
        qemu = _observe_qemu(project, game_runtime, tmp_path)

        # Same exact original fixture, initial loaded image, and one documented
        # Player 1 Q move. The independent game contract maps Q to the top-left
        # square; ATTT's nine initialized board bytes begin at COM offset 0103h.
        assert dosbox["startup"] == qemu["startup"]
        assert dosbox["after_q"] == qemu["after_q"]
        assert dosbox["startup"][_BOARD_OFFSET:_BOARD_OFFSET + 9] == b" " * 9
        assert dosbox["after_q"][_BOARD_OFFSET:_BOARD_OFFSET + 9] == b"x" + b" " * 8
        assert source.read_bytes() == original
        runs = {row["id"]: row for row in project.debug_runs()["runs"]}
        for observation in (dosbox, qemu):
            row = runs[observation["run_id"]]
            assert row["metadata"]["source_sha256"] == _ATTT_SHA256
            # We closed both debuggers with the game still running. Their
            # terminal history labels differ; neither proves a guest DOS exit.
            assert row["ended"] is not None
        assert len(project.debug_runs()["runs"]) == 2
    assert hashlib.sha256(game_runtime["boot_image"].read_bytes()).hexdigest() == game_runtime["boot_sha256"]
