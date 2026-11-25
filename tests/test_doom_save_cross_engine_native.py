"""Opt-in original Doom save interchange between DOSBox-X and QEMU.

The save file is written by Doom on one engine, admitted as an input to the
other engine, and loaded by Doom there. Commercial files and captures stay in
pytest's private temporary directory. This is a bounded save interchange gate,
not general gameplay or timing parity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from fdisbull.project import Project
from support.doom_gameplay import (
    DOOM_ARGUMENTS, PINS, advance, capture_statusbar, decode_ammo_from_wad,
    digest, launch, runtime_inputs, stage_game,
)


SAVE_NAME = "DOOMSAV0.DSG"
SAVE_LABEL = "PARITY"


@pytest.fixture
def doom_save_runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_SAVE_CROSS_ENGINE") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_SAVE_CROSS_ENGINE=1 for private Doom inputs")
    runtime = runtime_inputs()
    qemu_img = Path(os.environ["FDISBULL_QEMU_IMG"]).expanduser().resolve(strict=True)
    assert qemu_img.is_file() and os.access(qemu_img, os.X_OK)
    runtime["checkpoint_tool"] = qemu_img
    return runtime


def _press(debug, backend, key, *, hold_ms=80):
    result = debug.keyboard_press(key, hold_ms=hold_ms, gap_ms=80)
    assert result
    return _wait_keyboard_idle(debug, backend)


def _wait_keyboard_idle(debug, backend, *, budget_ms=200):
    # A QEMU timed text schedule must fit inside one explicit clock advance;
    # an earlier stop cancels its suffix and requires explicit recovery.
    if backend == "dosbox":
        for _ in range(5):
            receipt = advance(debug, backend, 200)
            state = debug.keyboard_state()["keyboard"]
            if state.get("pending_events", 0) == 0 and state.get("owned_keys", 0) == 0:
                return receipt
    else:
        receipt = advance(debug, backend, budget_ms)
        delivery = receipt.get("input_delivery")
        assert delivery and delivery.get("state") == "dispatched", delivery
        state = debug.keyboard_state()
        if state.get("pending_edges", 0) == 0 and not state.get("leases"):
            return receipt
    raise AssertionError(f"Doom keyboard input did not drain: {state}")


def _ammo(project, debug, runtime, game, root, backend, label, *, settle_ms=0):
    if settle_ms:
        advance(debug, backend, settle_ms)
    frame = capture_statusbar(project, debug, root, label)
    return decode_ammo_from_wad(game / "DOOM.WAD", frame["statusbar"])["value"]


def _frame_delta(root: Path, first: str, second: str) -> int:
    with Image.open(root / f"{first}.png") as left, Image.open(root / f"{second}.png") as right:
        a = left.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        b = right.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        raw = ImageChops.difference(a, b).tobytes()
    return sum(raw[index:index + 3] != b"\0\0\0" for index in range(0, len(raw), 3))


def _launch_qemu(project, runtime, game, *, checkpointed, on_spawn=None):
    options = dict(
        backend="qemu-dos", dos_boot_image=str(runtime["boot"]),
        dos_mcopy=str(runtime["mcopy"]), qemu_transport="pipe",
        qemu_firmware=runtime["firmware"], qemu_clock="virtual",
        dos_arguments=DOOM_ARGUMENTS, boot_timeout_ms=35000,
    )
    if checkpointed:
        options.update(dos_directory=str(game), dos_file_mode="checkpointed",
                      qemu_checkpoint_tool=str(runtime["checkpoint_tool"]))
    else:
        options.update(dos_directory=str(game))
    return project.debugger(str(runtime["qemu"]), game, _on_spawn=on_spawn, **options)


def _save_on_engine(root: Path, runtime, backend: str):
    root.mkdir()
    game = stage_game(root, runtime["source"])
    database = root / "doom-save-source.fdb"
    owners = []
    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        if backend == "dosbox":
            context = launch(project, runtime, game, "dosbox", on_spawn=owners.append)
        else:
            context = _launch_qemu(project, runtime, game, checkpointed=True,
                                   on_spawn=owners.append)
        with context as debug:
            if backend == "qemu-dos":
                assert debug.dos_process_info()["state"] == "active"
            assert _ammo(project, debug, runtime, game, root, backend, "save-start",
                         settle_ms=40000) == 50
            _press(debug, backend, "f2")
            _press(debug, backend, "enter")
            assert debug.keyboard_type(SAVE_LABEL, hold_ms=30, gap_ms=30)
            _wait_keyboard_idle(debug, backend, budget_ms=600)
            _press(debug, backend, "enter")
            advance(debug, backend, 700)
            if backend == "dosbox":
                save_path = game / SAVE_NAME
                assert save_path.is_file(), f"Doom did not create {SAVE_NAME}"
                save_bytes = save_path.read_bytes()
            else:
                # Doom's protected-mode runtime can legitimately change DOS
                # allocation ownership. Use the full VM/workspace snapshot,
                # which captures disk state without claiming process MCB ownership.
                debug.save_machine_state("doom-save-and-workspace.qcow2",
                                         max_bytes=128 * 1024 * 1024)
                save_bytes = debug.workspace_read(SAVE_NAME)["data"]
            label = save_bytes[:24].split(b"\0", 1)[0].rstrip(b" ")
            assert label == SAVE_LABEL.encode("ascii"), label
            assert save_bytes[24:40].split(b"\0", 1)[0] == b"version 109"
            assert save_bytes[40:43] == bytes((1, 1, 1)), save_bytes[40:43]
            assert len(save_bytes) >= 100
            assert _ammo(project, debug, runtime, game, root, backend, "save-after") == 50
    returncodes = [owner.poll() for owner in owners]
    assert owners and all(code is not None for code in returncodes)
    return dict(data=save_bytes, owner_cleanup=dict(status="reaped_only", returncodes=returncodes))


def _load_on_engine(root: Path, runtime, backend: str, save_bytes: bytes):
    root.mkdir()
    game = stage_game(root, runtime["source"])
    (game / SAVE_NAME).write_bytes(save_bytes)
    admitted = hashlib.sha256((game / SAVE_NAME).read_bytes()).hexdigest()
    assert admitted == hashlib.sha256(save_bytes).hexdigest()
    database = root / "doom-save-target.fdb"
    owners = []
    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        if backend == "dosbox":
            context = project.debugger(
                str(runtime["dosbox"]), game, dos_arguments=DOOM_ARGUMENTS,
                _on_spawn=owners.append)
        else:
            context = project.debugger(
                str(runtime["qemu"]), game, backend="qemu-dos",
                dos_directory=str(game), dos_file_mode="checkpointed",
                dos_boot_image=str(runtime["boot"]), dos_mcopy=str(runtime["mcopy"]),
                qemu_transport="pipe", qemu_firmware=runtime["firmware"],
                qemu_clock="virtual", qemu_checkpoint_tool=str(runtime["checkpoint_tool"]),
                dos_arguments=DOOM_ARGUMENTS, boot_timeout_ms=35000,
                _on_spawn=owners.append)
        with context as debug:
            if backend == "qemu-dos":
                assert debug.dos_process_info()["state"] == "active"
                staged = debug.workspace_read(SAVE_NAME)
                assert staged["sha256"] == admitted
                assert hashlib.sha256(staged["data"]).hexdigest() == admitted
            assert _ammo(project, debug, runtime, game, root, backend, "load-start",
                         settle_ms=40000) == 50
            assert debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            _wait_keyboard_idle(debug, backend, budget_ms=700)
            assert _ammo(project, debug, runtime, game, root, backend, "load-before") == 49
            _press(debug, backend, "f3")
            advance(debug, backend, 700)
            capture_statusbar(project, debug, root, "load-menu")
            menu_delta = _frame_delta(root, "load-before", "load-menu")
            assert menu_delta > 5000, f"F3 did not produce a distinct load-menu frame: {menu_delta}"
            _press(debug, backend, "enter")
            advance(debug, backend, 700)
            advance(debug, backend, 2000)
            after = capture_statusbar(project, debug, root, "load-after-settle")
            restored_frame_delta = _frame_delta(root, "load-menu", "load-after-settle")
            colors = after["statusbar"].getcolors(maxcolors=600)
            assert colors is not None
            (root / "post-load-observation.json").write_text(json.dumps(dict(
                backend=backend, guest_settle_ms=2000,
                screenshot_sha256=after["sha256"], dimensions=after["dimensions"],
                restored_view_changed_pixels=restored_frame_delta,
                statusbar_crop_rgb_counts=[dict(count=count, rgb=list(rgb))
                                           for count, rgb in sorted(colors, key=lambda item: item[1])]),
                sort_keys=True, indent=2) + "\n")
            loaded_ammo = decode_ammo_from_wad(game / "DOOM.WAD", after["statusbar"])["value"]
            assert restored_frame_delta > 5000, (
                f"{backend} did not leave the load menu: {restored_frame_delta}")
            assert loaded_ammo == 50, f"{backend} did not restore the cross-engine save: {loaded_ammo}"
    returncodes = [owner.poll() for owner in owners]
    assert owners and all(code is not None for code in returncodes)
    return dict(backend=backend, save_sha256=admitted, save_size=len(save_bytes),
                load_menu_changed_pixels=menu_delta, restored_view_changed_pixels=restored_frame_delta,
                loaded_ammo=loaded_ammo,
                owner_cleanup=dict(status="reaped_only", returncodes=returncodes))


def test_original_doom_save_load_crosses_dosbox_qemu(tmp_path, doom_save_runtime):
    """Each backend loads the exact game-written save from the other backend."""
    runtime = doom_save_runtime
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    binaries = {"dosbox": digest(runtime["dosbox"]), "qemu": digest(runtime["qemu"])}
    boot_sha256 = digest(runtime["boot"])
    producer_runs = {}
    producer_saves = {}
    progress = dict(
        scope="bounded original Doom save interchange; private inputs and captures remain in pytest temp",
        producer_sha256=binaries, boot_sha256=boot_sha256, saves={}, owner_cleanup={}, loads=[])
    progress_path = tmp_path / "cross-engine-save-progress.json"
    for producer in ("dosbox", "qemu-dos"):
        producer_runs[producer] = _save_on_engine(tmp_path / f"save-{producer}", runtime, producer)
        save = producer_runs[producer]["data"]
        producer_saves[producer] = save
        progress["owner_cleanup"]["save-" + producer] = producer_runs[producer]["owner_cleanup"]
        progress["saves"][producer] = dict(
            size=len(save), sha256=hashlib.sha256(save).hexdigest())
        progress_path.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")
    crossed = [
        _load_on_engine(tmp_path / "load-qemu-from-dosbox", runtime, "qemu-dos", producer_saves["dosbox"]),
        _load_on_engine(tmp_path / "load-dosbox-from-qemu", runtime, "dosbox", producer_saves["qemu-dos"]),
    ]
    progress["loads"] = crossed
    progress_path.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")
    assert crossed[0]["save_sha256"] == hashlib.sha256(producer_saves["dosbox"]).hexdigest()
    assert crossed[1]["save_sha256"] == hashlib.sha256(producer_saves["qemu-dos"]).hexdigest()
    assert {"dosbox": digest(runtime["dosbox"]), "qemu": digest(runtime["qemu"])} == binaries
    assert digest(runtime["boot"]) == boot_sha256
    for name, expected in PINS.items():
        assert digest(runtime["source"] / name) == expected
    progress["scope"] = "original Doom saves cross-loaded in both directions; E1M1 ammo 50 restored from 49"
    progress_path.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")
