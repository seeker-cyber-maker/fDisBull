"""Opt-in reverse Doom save interchange plus one DOSBox-X pistol shot.

QEMU writes the pinned E1M1 save, DOSBox-X loads those exact bytes, and one
physical Ctrl input must consume one WAD-decoded round and yield a bounded
DSPISTOL match. Private inputs and retained captures stay in pytest basetemp.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.le import load_runtime_le_carrier
from fdisbull.screenshot_codecs import decode_screenshot
from support.doom_gameplay import PINS, digest, runtime_inputs, stage_game
from support.doom_le_dosbox import placement, read as dosbox_read, reach_site
from test_doom_pistol_sfx_paired_native import (
    CONTROL_END_TIC, CORRELATION_THRESHOLD, CONTROL_REFERENCE_SAMPLES,
    DOSBOX_ARGUMENTS, DOSBOX_CONTROL_BUDGET_MS, DOSBOX_SHOT_BUDGET_MS,
    REFERENCE_GUARD_SAMPLES, SHOT_END_TIC, START_TIC, _DOSBoxView,
    _dosbox_ammo, _dosbox_post_stop_pcm, _dosbox_frontier, _read_dspistol,
    _dosbox_run_ms, _dosbox_wait_tic, _sample_correlation, _sha, _wav_pcm,
)
from test_doom_save_cross_engine_native import _save_on_engine
from test_doom_dosbox_quit_capture_native import _wait_to_tic_traced


SAVE_NAME = "DOOMSAV0.DSG"
TOTAL_DEADLINE_SECONDS = 240
WINDOW_DEADLINE_SECONDS = 30
SHOT_SEARCH_MARGIN_SECONDS = 0.25


@pytest.fixture
def doom_reverse_crossload_runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_REVERSE_CROSSLOAD_SFX") != "1":
        pytest.skip(
            "Set FDISBULL_REQUIRE_DOOM_REVERSE_CROSSLOAD_SFX=1 for private Doom inputs")
    runtime = runtime_inputs()
    qemu_img = Path(os.environ["FDISBULL_QEMU_IMG"]).expanduser().resolve(strict=True)
    if not qemu_img.is_file() or not os.access(qemu_img, os.X_OK):
        raise ValueError(f"QEMU checkpoint tool must be executable: {qemu_img}")
    runtime["checkpoint_tool"] = qemu_img
    return runtime


def _write_progress(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def _snapshot_frontier(capture_dir: Path, root: Path, label: str) -> dict:
    """Copy the currently visible DOSBox payload outside RPC-owned temp storage."""
    observed = _dosbox_frontier(capture_dir)
    retained = root / f"{label}-frontier.wav"
    retained.write_bytes(observed["path"].read_bytes())
    parsed = _wav_pcm(retained.read_bytes(), finalized=False)
    assert parsed["rate"] == 48_000 and parsed["channels"] == 2, parsed
    assert parsed["frames"] >= observed["pcm_frames"], (parsed, observed)
    return dict(frames=observed["pcm_frames"], rate=observed["rate"],
                channels=observed["channels"], retained_path=str(retained),
                retained_sha256=_sha(retained))


def _run_for_ms(call, milliseconds: int) -> dict:
    """Advance a stopped DOSBox session for a bounded guest-time interval."""
    before = call("execution.timing")
    operation = call("execution.continue")
    target_ticks = before["guest_ticks"] + milliseconds
    deadline = time.monotonic() + WINDOW_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        now = call("execution.timing")
        if now["guest_ticks"] >= target_ticks:
            pause = call("execution.pause")
            stopped = call("execution.wait", dict(
                operation_id=pause["operation_id"], timeout_ms=3000))
            assert not stopped.get("running"), stopped
            assert stopped["stop_reason"]["kind"] == "pause", stopped
            return dict(start_ticks=before["guest_ticks"], end_ticks=now["guest_ticks"],
                        requested_ms=milliseconds, operation_id=operation["operation_id"])
        pending = call("execution.wait", dict(
            operation_id=operation["operation_id"], timeout_ms=100))
        assert pending.get("running"), pending
    raise TimeoutError(f"DOSBox-X did not advance {milliseconds} guest milliseconds")


def _press_and_run(call, key: str, milliseconds: int = 700) -> dict:
    receipt = call("input.keyboard.press", dict(key=key, hold_ms=300 if key == "ctrl" else 80,
                                                gap_ms=80))
    assert receipt, (key, receipt)
    return dict(receipt=receipt, advance=_run_for_ms(call, milliseconds))


def _save_frame(view: _DOSBoxView, root: Path, label: str) -> dict:
    encoded, metadata = decode_screenshot(view.call("video.screenshot"))
    path = root / f"{label}.png"
    path.write_bytes(encoded)
    return dict(path=str(path), sha256=hashlib.sha256(encoded).hexdigest(),
                frame_id=metadata.get("frame_id"))


def _load_and_shoot(root: Path, runtime: dict, save_bytes: bytes,
                    reference: bytes, reference_rate: int) -> dict:
    root.mkdir(parents=True)
    game = stage_game(root, runtime["source"])
    save_path = game / SAVE_NAME
    save_sha256 = hashlib.sha256(save_bytes).hexdigest()
    assert not save_path.exists()
    image = load_runtime_le_carrier((game / "DOOM.EXE").read_bytes())
    wrapper = root / "dosbox-capture-wave"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(str(runtime["dosbox"]))
        + ' "$@" -c "ALIAS CAPW=DX-CAPTURE /A /-D"\n')
    wrapper.chmod(0o700)

    progress_path = root / "reverse-crossload-progress.json"
    progress = dict(format="fdisbull-doom-reverse-crossload-sfx-progress-1",
        phase="staged", backend="dosbox", save_size=len(save_bytes),
        save_sha256=save_sha256, source_sha256=PINS,
        dosbox_sha256=_sha(runtime["dosbox"]))
    _write_progress(progress_path, progress)
    rpc = None
    owner = None
    total_deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    try:
        rpc = DOSBoxRPC(wrapper, game)
        owner = rpc.process
        started = rpc.call("session.start", dict(
            target=dict(command="CAPW", arguments=["DOOM.EXE", *DOSBOX_ARGUMENTS.split()]),
            mounts=[dict(drive="C", host_path=str(game))], break_at="entry"))
        session_id = started["session_id"]

        def call(method, parameters=None, *, timeout_ms=15_000):
            assert time.monotonic() < total_deadline, f"reverse cross-load deadline expired at {method}"
            return rpc.call(method, dict(session_id=session_id, **(parameters or {})),
                            timeout_ms=timeout_ms)

        view = _DOSBoxView(call)
        registers = call("state.get_registers")
        assert registers["cpu_mode"] == "real", registers
        call("execution.timing", dict(fast_forward=True))
        # Acquire the same source-bound pre-increment landmarks as the paired
        # pistol gate. The pre-load control shot is at tic 84, not after an
        # unbounded wall/guest-time wait.
        reach_site(view, image)
        site = placement(view, image)
        assert site and site["runtime_address"] == site["cs_base"] + site["ip"], site
        pc, counter = site["runtime_address"], site["runtime_target"]
        assert site["runtime_bytes"] == "ff05" + counter.to_bytes(4, "little").hex(), site
        address = dict(space="segmented", segment=f"0x{site['cs']:04x}",
                       offset=f"0x{pc - site['cs_base']:08x}")
        tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
        assert tic <= START_TIC, tic
        if tic < START_TIC:
            tic, site = _dosbox_wait_tic(call, view, image, pc, counter, address,
                                         START_TIC, tic)
        assert tic == START_TIC, tic
        call("execution.timing", dict(fast_forward=False))
        capture_dir = Path(rpc.temporary.name) / "capture"
        tic, preload_control_run = _dosbox_run_ms(call, view, counter, CONTROL_END_TIC,
                                                  DOSBOX_CONTROL_BUDGET_MS, tic)
        control_tic, _ = _dosbox_wait_tic(call, view, image, pc, counter, address,
                                          CONTROL_END_TIC, tic)
        assert control_tic == CONTROL_END_TIC, control_tic
        no_shot = _dosbox_ammo(view, game)
        assert no_shot["value"] == 50, no_shot
        before_load = no_shot
        shot_start_frontier = _dosbox_frontier(capture_dir)
        pre_load_key = call("input.keyboard.press", dict(key="ctrl", hold_ms=300, gap_ms=80))
        assert pre_load_key
        progress.update(phase="preload-shot-dispatched", source_site=dict(
            start_tic=START_TIC, control_end_tic=control_tic, runtime_pc=pc,
            runtime_counter=counter, instruction_bytes=site["runtime_bytes"]),
            input_receipt=pre_load_key,
            shot_start_frontier_frames=shot_start_frontier["pcm_frames"])
        _write_progress(progress_path, progress)
        sampled_tic, pre_load_shot_run = _dosbox_run_ms(
            call, view, counter, SHOT_END_TIC, DOSBOX_SHOT_BUDGET_MS, CONTROL_END_TIC)
        shot_tic, _, shot_stop_records = _wait_to_tic_traced(
            call, view, image, pc, counter, address, SHOT_END_TIC,
            sampled_tic, progress_path, "preload-shot-source-site-wait")
        assert shot_tic == SHOT_END_TIC, shot_tic
        keyboard_after = call("input.keyboard.state")
        pre_load_after_frame = _save_frame(view, root, "preload-tic114-after-shot")
        depleted = _dosbox_ammo(view, game)
        pre_load_diagnostic = dict(start_tic=START_TIC, control_end_tic=control_tic,
            shot_end_tic=shot_tic, runtime_pc=pc, runtime_counter=counter,
            source_bytes=site["runtime_bytes"], input_receipt=pre_load_key,
            keyboard_after=keyboard_after, after_frame=pre_load_after_frame,
            ammo_before=before_load["value"], no_shot_ammo=no_shot["value"],
            ammo_after=depleted["value"], shot_run=pre_load_shot_run,
            source_stop_records=shot_stop_records)
        if depleted["value"] != 49:
            _write_progress(progress_path, dict(phase="preload-shot-failed",
                diagnostic=pre_load_diagnostic))
        assert depleted["value"] == 49, pre_load_diagnostic

        # Place the QEMU-produced bytes only after the accepted baseline shot.
        # This isolates startup state from the foreign save while retaining an
        # exact stopped-guest admission/readback before Doom opens the slot.
        save_path.write_bytes(save_bytes)
        assert digest(save_path) == save_sha256
        progress.update(phase="foreign-save-admitted", save_sha256=save_sha256,
                        save_size=len(save_bytes), pre_load_shot=pre_load_diagnostic)
        _write_progress(progress_path, progress)

        _press_and_run(call, "f3")
        menu_image, menu_metadata = decode_screenshot(view.call("video.screenshot"))
        (root / "load-menu.png").write_bytes(menu_image)
        menu_sha256 = hashlib.sha256(menu_image).hexdigest()
        assert menu_sha256 != depleted["screenshot_sha256"]
        _press_and_run(call, "enter")
        _run_for_ms(call, 2_000)
        loaded = _dosbox_ammo(view, game)
        assert loaded["value"] == 50, loaded
        progress.update(phase="foreign-save-loaded", load=dict(
            ammo_before_save=before_load["value"], ammo_before_load=depleted["value"],
            ammo_after_load=loaded["value"],
            pre_load_shot=pre_load_diagnostic,
            pre_load_control_run=preload_control_run,
            decoder_wad_sha256=loaded["wad_sha256"],
            save_sha256=save_sha256, menu_frame_id=menu_metadata.get("frame_id"),
            menu_screenshot_sha256=menu_sha256))
        _write_progress(progress_path, progress)

        control_start = _snapshot_frontier(capture_dir, root, "no-shot-start")
        audio_control_run = _run_for_ms(call, 400)
        control_end = _snapshot_frontier(capture_dir, root, "no-shot-end")
        assert control_end["frames"] > control_start["frames"], (control_start, control_end)
        shot_start = _snapshot_frontier(capture_dir, root, "shot-start")
        input_receipt = _press_and_run(call, "ctrl", 1_200)
        shot_end = _snapshot_frontier(capture_dir, root, "shot-end")
        after_shot = _dosbox_ammo(view, game)
        assert after_shot["value"] == 49, after_shot
        assert shot_end["frames"] > shot_start["frames"], (shot_start, shot_end)

        stop = call("session.stop")
        stopped = None
        stop_deadline = time.monotonic() + WINDOW_DEADLINE_SECONDS
        while time.monotonic() < stop_deadline:
            stopped = call("execution.wait", dict(
                operation_id=stop["operation_id"], timeout_ms=250), timeout_ms=1_000)
            if not stopped.get("running"):
                break
        else:
            raise TimeoutError(f"DOSBox-X session.stop did not finish: {stopped!r}")
        files = sorted(capture_dir.glob("*.wav"))
        assert len(files) == 1 and files[0].is_file(), files
        retained_wav = root / "dosbox-crossloaded-shot.wav"
        retained_wav.write_bytes(files[0].read_bytes())
        payload = _dosbox_post_stop_pcm(retained_wav.read_bytes())
        assert payload["rate"] == 48_000 and payload["channels"] == 2, payload
        assert payload["frames"] >= shot_end["frames"], (payload, shot_end)

        control_pcm = payload["pcm"][control_start["frames"] * 4:
                                      control_end["frames"] * 4]
        assert len(control_pcm) // 4 >= round(48_000 * 0.20), len(control_pcm)
        control_corr = _sample_correlation(control_pcm, payload["rate"], reference,
            reference_rate, reference_samples=CONTROL_REFERENCE_SAMPLES)
        assert control_corr["score"] < CORRELATION_THRESHOLD, control_corr

        margin = round(payload["rate"] * SHOT_SEARCH_MARGIN_SECONDS)
        search_start = max(0, shot_start["frames"] - margin)
        search_end = shot_end["frames"]
        shot_pcm = payload["pcm"][search_start * 4:search_end * 4]
        shot_corr = _sample_correlation(shot_pcm, payload["rate"], reference,
            reference_rate, reference_samples=len(reference))
        assert shot_corr["score"] >= CORRELATION_THRESHOLD, shot_corr
        assert shot_corr["onset_frame"] + shot_corr["template_frames"] <= len(shot_pcm) // 4
        assert {name: digest(game / name) for name in PINS} == PINS
        result = dict(backend="dosbox", save=dict(size=len(save_bytes), sha256=save_sha256),
            load=dict(ammo=loaded["value"], before_load=depleted["value"],
                      original_ammo=before_load["value"],
                      pre_load_shot=pre_load_diagnostic,
                      wad_sha256=loaded["wad_sha256"]),
            shot=dict(control_ammo=loaded["value"], after_ammo=after_shot["value"],
                input=input_receipt, wad_sha256=after_shot["wad_sha256"]),
            audio=dict(rate=payload["rate"], channels=payload["channels"],
                control_correlation=control_corr, shot_correlation=shot_corr,
                control_advance=audio_control_run,
                shot_advance=input_receipt["advance"],
                control_window_frames=[control_start["frames"], control_end["frames"]],
                shot_window_frames=[shot_start["frames"], shot_end["frames"]],
                search_frames=[search_start, search_end],
                wav_sha256=_sha(retained_wav),
                capture_completeness=payload["capture_completeness"],
                overflow=None, dropped_frames=None,
                limitation="DX-CAPTURE exposes no native overflow or dropped-frame counter"),
            runtime_sha256=_sha(runtime["dosbox"]),
            artifacts="private save, screenshots, database, and audio remain in pytest basetemp")
        _write_progress(progress_path, dict(phase="shot-observed", destination=result,
                                           stop_reply=stop, terminal_wait=stopped))
        rpc.close()
        assert owner.poll() is not None, "DOSBox-X process owner was not reaped"
        result["owner_cleanup"] = dict(status="reaped", returncode=owner.returncode)
        return result
    finally:
        if rpc is not None:
            rpc.close()


def test_original_doom_qemu_save_load_then_dosbox_pistol_sfx(
        tmp_path, doom_reverse_crossload_runtime):
    checkout = Path(__file__).resolve().parents[1]
    try:
        tmp_path.resolve(strict=True).relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom saves and captures must stay in pytest basetemp")
    runtime = doom_reverse_crossload_runtime
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    dosbox_save = _save_on_engine(tmp_path / "qemu-save", runtime, "qemu-dos")
    reference, reference_rate = _read_dspistol(runtime["source"] / "DOOM.WAD")
    progress_path = tmp_path / "reverse-crossload-pistol-sfx-progress.json"
    progress = dict(format="fdisbull-doom-reverse-crossload-pistol-sfx-1",
        phase="qemu-save-created", pins=PINS,
        qemu_sha256=digest(runtime["qemu"]), dosbox_sha256=digest(runtime["dosbox"]),
        save=dict(size=len(dosbox_save["data"]),
            sha256=hashlib.sha256(dosbox_save["data"]).hexdigest(),
            producer_cleanup=dosbox_save["owner_cleanup"]))
    _write_progress(progress_path, progress)
    dosbox_result = _load_and_shoot(tmp_path / "dosbox-load-and-shot", runtime,
        dosbox_save["data"], reference, reference_rate)
    assert dosbox_result["load"]["ammo"] == 50
    assert dosbox_result["shot"]["control_ammo"] == 50
    assert dosbox_result["shot"]["after_ammo"] == 49
    assert dosbox_result["audio"]["control_correlation"]["score"] < CORRELATION_THRESHOLD
    assert dosbox_result["audio"]["shot_correlation"]["score"] >= CORRELATION_THRESHOLD
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    receipt = dict(format="fdisbull-doom-reverse-crossload-pistol-sfx-1",
        scope="one QEMU-created pinned original Doom E1M1 save loaded by DOSBox-X; one bounded no-shot control and one physical Ctrl shot; no general save, timing, mixer, or audio parity claim",
        pins=PINS, qemu_sha256=digest(runtime["qemu"]),
        dosbox_sha256=digest(runtime["dosbox"]), boot_sha256=digest(runtime["boot"]),
        save=dict(size=len(dosbox_save["data"]),
            sha256=hashlib.sha256(dosbox_save["data"]).hexdigest(),
            producer_cleanup=dosbox_save["owner_cleanup"]),
        destination=dosbox_result,
        reference=dict(lump="DSPISTOL",
            sample_sha256=hashlib.sha256(reference).hexdigest(),
            sample_rate_hz=reference_rate, guard_samples_removed_per_end=REFERENCE_GUARD_SAMPLES,
            correlation_threshold=CORRELATION_THRESHOLD),
        artifacts="commercial save, captures, and database remain in pytest basetemp")
    receipt["phase"] = "accepted"
    progress_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
