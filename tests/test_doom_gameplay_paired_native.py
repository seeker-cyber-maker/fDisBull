"""Opt-in bounded private Doom E1M1 input witness across DOSBox-X and QEMU.

This tests one physical Ctrl input and an original-WAD-derived ammo HUD change
from 50 to 49 per engine. It is not a general compatibility, frame-equivalence,
save/load, or parity test.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.doom_gameplay import (
    DOOM_ARGUMENTS,
    PINS,
    advance,
    capture_statusbar,
    decode_ammo_from_wad,
    digest,
    launch,
    runtime_inputs,
    stage_game,
    statusbar_delta,
)


@pytest.fixture
def doom_runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_GAMEPLAY_PAIRED") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_GAMEPLAY_PAIRED=1 for private Doom inputs")
    return runtime_inputs()


def _run_backend(root: Path, runtime, backend: str):
    root.mkdir()
    game = stage_game(root, runtime["source"])
    source_before = {name: digest(game / name) for name in PINS}
    database = root / "doom-gameplay.fdb"
    owner = None
    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        with launch(project, runtime, game, backend) as debug:
            owner = debug.rpc.process if backend == "dosbox" else debug.vm.process
            if backend == "qemu-dos":
                assert debug.dos_process_info()["state"] == "active"

            # The identical direct E1M1 arguments bypass the startup menu and
            # disable unrelated sound/mouse behavior on both engines.
            advance(debug, backend, 40000)
            before = capture_statusbar(project, debug, root, "before-control")
            before_ammo = decode_ammo_from_wad(game / "DOOM.WAD", before["statusbar"])
            assert before_ammo["value"] == 50, before_ammo
            advance(debug, backend, 700)
            control = capture_statusbar(project, debug, root, "after-control")
            control_ammo = decode_ammo_from_wad(game / "DOOM.WAD", control["statusbar"])
            assert control_ammo["value"] == 50, control_ammo
            control_delta = statusbar_delta(before, control)
            assert control_delta == 0, (
                "The ammo HUD region changed during the no-input control interval; "
                "cannot attribute a later pixel change to Ctrl"
            )
            assert debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            advance(debug, backend, 700)
            after = capture_statusbar(project, debug, root, "after-shot")
            after_ammo = decode_ammo_from_wad(game / "DOOM.WAD", after["statusbar"])
            assert after_ammo["value"] == 49, after_ammo
            delta = statusbar_delta(control, after)
            assert delta > 0, "The stored Doom status-bar crop did not change after Ctrl"
            run_id = debug.run_id
        assert owner.poll() is not None

    for name, expected in source_before.items():
        assert digest(game / name) == expected == PINS[name]
    assert digest(runtime["boot"]) == runtime["boot_sha256"]
    with Project(database) as project:
        rows = {row["id"]: row for row in project.debug_runs()["runs"]}
        row = rows[run_id]
        assert row["ended"] is not None
        assert row["metadata"]["source_sha256"] == PINS["DOOM.EXE"]
    return dict(backend=backend, launch_arguments=DOOM_ARGUMENTS,
                source_sha256=PINS["DOOM.EXE"],
                ammunition=dict(before=before_ammo["value"], control=control_ammo["value"],
                                after_physical_ctrl=after_ammo["value"],
                                decoder_wad_sha256=before_ammo["wad_sha256"],
                                decoder_lumps=before_ammo["lumps"]),
                before=dict(artifact=before["artifact"], sha256=before["sha256"]),
                after=dict(artifact=after["artifact"], sha256=after["sha256"]),
                control_changed_pixels=control_delta, ammo_region_changed_pixels=delta,
                run_id=run_id, emulator_owner_reaped=True,
                emulator_owner_returncode=owner.returncode,
                guest_doom_exit_observed=False)


def test_original_doom_e1m1_physical_input_has_bounded_paired_hud_observation(
        tmp_path, doom_runtime):
    """Run the same bounded direct-start shot slice, retaining each engine's frames."""
    # Keep DOSBox-X first and use the already established default engine
    # explicitly. QEMU is selected only for this paired test invocation.
    dosbox = _run_backend(tmp_path / "dosbox", doom_runtime, "dosbox")
    qemu = _run_backend(tmp_path / "qemu", doom_runtime, "qemu-dos")
    assert {name: digest(doom_runtime["source"] / name) for name in PINS} == PINS
    assert {backend: digest(doom_runtime[backend]) for backend in ("dosbox", "qemu")} == doom_runtime["binary_sha256"]
    assert dosbox["source_sha256"] == qemu["source_sha256"] == PINS["DOOM.EXE"]
    assert dosbox["ammo_region_changed_pixels"] > 0
    assert qemu["ammo_region_changed_pixels"] > 0
    (tmp_path / "paired-gameplay.json").write_text(
        json.dumps(dict(scope="one bounded E1M1 Ctrl input; exact WAD-patch decode 50→49 with stable control; no parity claim",
                        runtime_sha256=doom_runtime["binary_sha256"],
                        boot_sha256=doom_runtime["boot_sha256"],
                        dosbox=dosbox, qemu=qemu), sort_keys=True, indent=2) + "\n")
