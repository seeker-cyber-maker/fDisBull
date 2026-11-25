"""Opt-in one-way Doom save interchange followed by a physical pistol shot.

DOSBox-X writes the pinned E1M1 save; QEMU loads its exact bytes, then one
physical Ctrl shot must consume one round and produce a bounded DSPISTOL WAD
match. The private route does not claim general save, timing, or audio parity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.doom_gameplay import PINS, capture_statusbar, decode_ammo_from_wad, digest, runtime_inputs, stage_game
from support.doom_le_qemu import runtime_inputs as qemu_runtime_inputs
from test_doom_pistol_sfx_paired_native import (
    CORRELATION_THRESHOLD, MAX_AUDIO_FRAMES, QEMU_ARGUMENTS, _read_dspistol,
    _sample_correlation, _sha, _wav_pcm,
)
from test_doom_save_cross_engine_native import _frame_delta, _save_on_engine


@pytest.fixture
def doom_crossload_sfx_runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_CROSSLOAD_SFX") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_CROSSLOAD_SFX=1 for private Doom inputs")
    runtime = runtime_inputs()
    qemu_runtime = qemu_runtime_inputs()
    runtime["qemu"] = qemu_runtime["executable"]
    runtime["boot"] = qemu_runtime["boot_image"]
    runtime["mcopy"] = qemu_runtime["mcopy"]
    runtime["firmware"] = qemu_runtime["firmware"]
    runtime["checkpoint_tool"] = qemu_runtime["checkpoint_tool"]
    return runtime


def _qemu_advance(debug, milliseconds: int):
    stopped = debug.clock_advance(milliseconds * 1_000_000, timeout_ms=60_000)
    budget = stopped["clock_budget"]
    assert budget["deadline_reached"] and budget["elapsed_ns"] >= milliseconds * 1_000_000, stopped
    assert stopped["outcome"] not in ("guest_exit", "guest_tsr", "exited"), stopped
    return stopped


def _qemu_press(debug, key: str, milliseconds: int = 700):
    receipt = debug.keyboard_press(key, hold_ms=80, gap_ms=80)
    assert receipt
    stopped = _qemu_advance(debug, milliseconds)
    state = debug.keyboard_state()
    assert state.get("pending_edges", 0) == 0 and not state.get("leases"), (receipt, state, stopped)
    return receipt


def _capture_qemu(project, debug, root: Path, label: str, expected_frames: int | None = None):
    stopped = debug.audio_stop()
    assert stopped["state"] == "stopped" and stopped["dropped_frames"] == 0, stopped
    assert stopped["frames"] > 0 and stopped["window"] and stopped["epoch"] is not None, stopped
    artifact = debug.capture_audio(label + ".wav")
    path = root / (label + ".wav")
    project.debug_export(artifact["artifact"], path)
    assert _sha(path) == artifact["sha256"]
    wav = _wav_pcm(path.read_bytes(), finalized=True)
    assert wav["rate"] == 32_000 and wav["channels"] == 2, wav
    assert wav["frames"] == stopped["frames"], (wav, stopped)
    return dict(stopped=stopped, wav=wav, sha256=artifact["sha256"], path=path)


def _write_progress(root: Path, progress: dict) -> None:
    (root / "crossload-progress.json").write_text(
        json.dumps(progress, sort_keys=True, indent=2) + "\n")


def _load_dosbox_save_in_qemu(root: Path, runtime: dict, save_bytes: bytes,
                              reference: bytes, reference_rate: int) -> dict:
    root.mkdir(parents=True)
    game = stage_game(root, runtime["source"])
    save_path = game / "DOOMSAV0.DSG"
    save_path.write_bytes(save_bytes)
    save_sha256 = hashlib.sha256(save_bytes).hexdigest()
    assert digest(save_path) == save_sha256
    owners = []
    result = {"backend": "qemu-dos", "save_sha256": save_sha256, "save_size": len(save_bytes)}
    _write_progress(root, dict(phase="staged", destination=result))
    options = dict(
        backend="qemu-dos", dos_directory=str(game), dos_file_mode="checkpointed",
        dos_boot_image=str(runtime["boot"]), dos_mcopy=str(runtime["mcopy"]),
        qemu_transport="pipe", qemu_firmware=runtime["firmware"], qemu_audio="sb16-opl",
        qemu_retrace="precise", qemu_clock="virtual",
        qemu_checkpoint_tool=str(runtime["checkpoint_tool"]), dos_arguments=QEMU_ARGUMENTS,
        boot_timeout_ms=35_000,
    )
    with Project.create(root / "crossload-shot.fdb", game / "DOOM.EXE", image="mz") as project:
        with project.debugger(str(runtime["qemu"]), game, _on_spawn=owners.append, **options) as debug:
            assert debug.dos_process_info()["state"] == "active"
            staged = debug.workspace_read("DOOMSAV0.DSG")
            assert staged["sha256"] == save_sha256
            assert hashlib.sha256(staged["data"]).hexdigest() == save_sha256

            _qemu_advance(debug, 40_000)
            before_load = capture_statusbar(project, debug, root, "before-load")
            before_ammo = decode_ammo_from_wad(game / "DOOM.WAD", before_load["statusbar"])
            assert before_ammo["value"] == 50, before_ammo
            # Prove the destination can consume a round before loading, then
            # require the foreign save to restore 50 before the measured shot.
            _qemu_press(debug, "ctrl")
            after_control = capture_statusbar(project, debug, root, "preload-shot")
            control_ammo = decode_ammo_from_wad(game / "DOOM.WAD", after_control["statusbar"])
            assert control_ammo["value"] == 49, control_ammo
            _qemu_press(debug, "f3")
            menu = capture_statusbar(project, debug, root, "load-menu")
            menu_delta = _frame_delta(root, "preload-shot", "load-menu")
            assert menu_delta > 5000, f"F3 did not produce a distinct load-menu frame: {menu_delta}"
            _qemu_press(debug, "enter")
            _qemu_advance(debug, 2_000)
            loaded = capture_statusbar(project, debug, root, "foreign-save-loaded")
            loaded_ammo = decode_ammo_from_wad(game / "DOOM.WAD", loaded["statusbar"])
            assert loaded_ammo["value"] == 50, loaded_ammo
            result["load"] = dict(ammo=loaded_ammo["value"], screenshot_sha256=loaded["sha256"],
                                  load_menu_changed_pixels=menu_delta,
                                  decoder_wad_sha256=loaded_ammo["wad_sha256"],
                                  save_readback_sha256=staged["sha256"])
            _write_progress(root, dict(phase="foreign-save-loaded", destination=result))

            control_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert control_start["state"] == "capturing"
            _qemu_advance(debug, 400)
            control_capture = _capture_qemu(project, debug, root, "no-shot-control")
            assert control_capture["stopped"]["window"] == control_start["window"]
            control_corr = _sample_correlation(control_capture["wav"]["pcm"], 32_000,
                reference, reference_rate, reference_samples=2048)
            assert control_corr["score"] < CORRELATION_THRESHOLD, control_corr
            control_view = capture_statusbar(project, debug, root, "no-shot-ammo")
            control_after = decode_ammo_from_wad(game / "DOOM.WAD", control_view["statusbar"])
            assert control_after["value"] == 50, control_after
            result["no_shot_control"] = dict(ammo=control_after["value"],
                correlation=control_corr, wav_sha256=control_capture["sha256"],
                screenshot_sha256=control_view["sha256"])
            _write_progress(root, dict(phase="no-shot-control-complete", destination=result))

            shot_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert shot_start["state"] == "capturing"
            input_receipt = debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            assert input_receipt.get("state") == "armed", input_receipt
            _qemu_advance(debug, 1_200)
            scheduled = debug.input_schedule_observe()
            assert scheduled["state"] == "dispatched" and scheduled["edge_count"] == 2, scheduled
            assert [edge["down"] for edge in scheduled["press"]["steps"]] == [True, False], scheduled
            shot_capture = _capture_qemu(project, debug, root, "crossloaded-shot")
            assert shot_capture["stopped"]["window"] == shot_start["window"]
            shot_corr = _sample_correlation(shot_capture["wav"]["pcm"], 32_000,
                reference, reference_rate, reference_samples=len(reference))
            assert shot_corr["score"] >= CORRELATION_THRESHOLD, shot_corr
            shot_view = capture_statusbar(project, debug, root, "crossloaded-shot-ammo")
            shot_ammo = decode_ammo_from_wad(game / "DOOM.WAD", shot_view["statusbar"])
            assert shot_ammo["value"] == 49, shot_ammo
            result["shot"] = dict(control_ammo=control_after["value"], after_ammo=shot_ammo["value"],
                control_correlation=control_corr, shot_correlation=shot_corr,
                input=dict(receipt=input_receipt, observed=scheduled),
                audio=dict(control_wav_sha256=control_capture["sha256"],
                           shot_wav_sha256=shot_capture["sha256"],
                           control_frames=control_capture["wav"]["frames"],
                           shot_frames=shot_capture["wav"]["frames"],
                           dropped_frames=shot_capture["stopped"]["dropped_frames"],
                           onset_claim="bounded in shot capture only; no guest-time calibration"),
                decoder_wad_sha256=shot_ammo["wad_sha256"],
                screenshot_sha256=shot_view["sha256"])
            assert {name: digest(game / name) for name in PINS} == PINS
            _write_progress(root, dict(phase="shot-observed", destination=result))
    returncodes = [owner.poll() for owner in owners]
    assert owners and all(code is not None for code in returncodes), returncodes
    result["owner_cleanup"] = dict(status="reaped_only", returncodes=returncodes)
    return result


def test_original_doom_cross_engine_save_load_then_pistol_sfx(tmp_path, doom_crossload_sfx_runtime):
    checkout = Path(__file__).resolve().parents[1]
    try:
        Path(tmp_path).resolve(strict=True).relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom saves and captures must remain outside the source checkout")
    runtime = doom_crossload_sfx_runtime
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    qemu_runtime = runtime["qemu"]
    dosbox_save = _save_on_engine(tmp_path / "dosbox-save", runtime, "dosbox")
    reference, reference_rate = _read_dspistol(runtime["source"] / "DOOM.WAD")
    progress_path = Path(tmp_path) / "crossload-pistol-sfx-progress.json"
    progress_path.write_text(json.dumps(dict(format="fdisbull-doom-crossload-pistol-sfx-1",
        phase="foreign-save-created", pins=PINS, dosbox_sha256=digest(runtime["dosbox"]),
        save=dict(size=len(dosbox_save["data"]),
                  sha256=hashlib.sha256(dosbox_save["data"]).hexdigest(),
                  producer_cleanup=dosbox_save["owner_cleanup"])), sort_keys=True, indent=2) + "\n")
    qemu_result = _load_dosbox_save_in_qemu(tmp_path / "qemu-load-and-shot", runtime,
        dosbox_save["data"], reference, reference_rate)
    assert qemu_result["load"]["ammo"] == 50
    assert qemu_result["shot"]["control_ammo"] == 50 and qemu_result["shot"]["after_ammo"] == 49
    assert qemu_result["shot"]["control_correlation"]["score"] < CORRELATION_THRESHOLD
    assert qemu_result["shot"]["shot_correlation"]["score"] >= CORRELATION_THRESHOLD
    receipt = dict(format="fdisbull-doom-crossload-pistol-sfx-1",
        scope="one DOSBox-X-created pinned original Doom E1M1 save loaded by QEMU; one no-shot control and one physical Ctrl shot; no general cross-engine save, timing, mixer, or audio parity claim",
        pins=PINS, dosbox_sha256=digest(runtime["dosbox"]), qemu_sha256=digest(qemu_runtime),
        save=dict(size=len(dosbox_save["data"]), sha256=hashlib.sha256(dosbox_save["data"]).hexdigest(),
                  producer_cleanup=dosbox_save["owner_cleanup"]),
        destination=qemu_result,
        reference=dict(lump="DSPISTOL", sample_sha256=hashlib.sha256(reference).hexdigest(),
                       sample_rate_hz=reference_rate, guard_samples_removed_per_end=16,
                       correlation_threshold=CORRELATION_THRESHOLD),
        artifacts="commercial saves, screenshots, WAVs, and databases remain in pytest private temp output")
    receipt["phase"] = "accepted"
    progress_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
