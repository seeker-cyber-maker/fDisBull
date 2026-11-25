"""Opt-in DOSBox-X Doom shot, normal quit, and finalized DX-CAPTURE WAV.

The selected Doom MZ child must report a normal DOS_Terminate after cleanup.
The test inspects the capture file only after that guest exit and requires the
RIFF and data extents to agree before describing it as finalized.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import struct
import time

from PIL import Image, ImageChops
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.le import load_runtime_le_carrier
from fdisbull.screenshot_codecs import decode_screenshot
from support.doom_gameplay import digest, stage_game
from support.doom_le_qemu import PINS
from support.doom_le_dosbox import placement, read as dosbox_read, reach_site
from test_doom_pistol_sfx_paired_native import (
    CONTROL_END_TIC, CONTROL_REFERENCE_SAMPLES, CORRELATION_THRESHOLD,
    DOSBOX_ARGUMENTS, DOSBOX_CONTROL_BUDGET_MS, DOSBOX_SHOT_BUDGET_MS,
    REFERENCE_GUARD_SAMPLES, _DOSBoxView, _dosbox_ammo, _dosbox_frontier,
    SHOT_END_TIC, _dosbox_run_ms, _dosbox_wait_tic, _read_dspistol,
    _sample_correlation, _sha,
)


TOTAL_DEADLINE_SECONDS = 240
WINDOW_DEADLINE_SECONDS = 30
QUIT_EXIT_DEADLINE_SECONDS = 30
MAX_CAPTURE_BYTES = 128 * 1024 * 1024
TICK_LIMIT = 100_000
START_TIC = 64
SOURCE_WAIT_TOTAL_SECONDS = 15
SOURCE_WAIT_PER_STOP_SECONDS = 2


@pytest.fixture
def doom_dosbox_quit_runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_DOSBOX_QUIT_CAPTURE") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_DOSBOX_QUIT_CAPTURE=1 for private Doom inputs")
    missing = [name for name in ("FDISBULL_DOOM_LE_SOURCE", "FDISBULL_DOSBOX")
               if not os.environ.get(name)]
    if missing:
        pytest.fail("Private Doom inputs missing: " + ", ".join(missing))
    source = Path(os.environ["FDISBULL_DOOM_LE_SOURCE"]).expanduser().resolve(strict=True)
    dosbox = Path(os.environ["FDISBULL_DOSBOX"]).expanduser().resolve(strict=True)
    if not source.is_dir() or not dosbox.is_file() or not os.access(dosbox, os.X_OK):
        raise ValueError("Expected a private Doom directory and executable DOSBox-X")
    hashes = {name: digest(source / name) for name in PINS}
    if hashes != PINS:
        raise ValueError(f"Pinned private Doom source identity mismatch: {hashes}")
    return dict(source=source, dosbox=dosbox, source_sha256=hashes,
                dosbox_sha256=digest(dosbox))


def _write_progress(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def _frame(view: _DOSBoxView, root: Path, label: str) -> dict:
    reply = view.call("video.screenshot")
    encoded, metadata = decode_screenshot(reply)
    path = root / f"{label}.png"
    path.write_bytes(encoded)
    with Image.open(io.BytesIO(encoded)) as image:
        normalized = image.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        normalized.load()
    return dict(path=path, sha256=hashlib.sha256(encoded).hexdigest(),
                frame_id=metadata.get("frame_id"))


def _changed_pixels(root: Path, before: str, after: str) -> int:
    with Image.open(root / f"{before}.png") as left, Image.open(root / f"{after}.png") as right:
        a = left.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        b = right.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        raw = ImageChops.difference(a, b).tobytes()
    return sum(raw[i:i + 3] != b"\0\0\0" for i in range(0, len(raw), 3))


def _finalized_wav(raw: bytes) -> dict:
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("DX-CAPTURE output lacks a complete RIFF/WAVE header")
    riff_size = struct.unpack_from("<I", raw, 4)[0]
    if riff_size + 8 != len(raw):
        raise ValueError(f"RIFF extent is not finalized: declared={riff_size + 8}, actual={len(raw)}")
    cursor = 12
    fmt = None
    data = None
    while cursor + 8 <= len(raw):
        kind = raw[cursor:cursor + 4]
        size = struct.unpack_from("<I", raw, cursor + 4)[0]
        start = cursor + 8
        end = start + size
        if end > len(raw):
            raise ValueError(f"WAV {kind!r} chunk extends beyond the finalized file")
        if kind == b"fmt ":
            if fmt is not None or size < 16:
                raise ValueError("WAV must contain one valid fmt chunk")
            fmt = struct.unpack_from("<HHIIHH", raw, start)
        elif kind == b"data":
            if data is not None:
                raise ValueError("WAV contains multiple data chunks")
            data = dict(offset=start, bytes=size, end=end)
        cursor = end + (size & 1)
    if cursor != len(raw) or fmt is None or data is None:
        raise ValueError("WAV chunks do not exactly cover a complete file")
    code, channels, rate, byte_rate, align, bits = fmt
    if (code, channels, rate, byte_rate, align, bits) != (1, 2, 48_000, 192_000, 4, 16):
        raise ValueError(f"Expected 48 kHz signed 16-bit stereo PCM, received {fmt}")
    if data["end"] != len(raw) or data["bytes"] <= 0 or data["bytes"] % align:
        raise ValueError("WAV data chunk is not the final aligned PCM payload")
    return dict(rate=rate, channels=channels, sample_width=2, frames=data["bytes"] // align,
                data_offset=data["offset"], data_bytes=data["bytes"], riff_bytes=len(raw),
                header_finalized=True, pcm=raw[data["offset"]:data["end"]])


def _wait_finalized_capture(capture_dir: Path, deadline: float) -> tuple[Path, dict]:
    previous = None
    stable = 0
    while time.monotonic() < deadline:
        files = sorted(capture_dir.glob("*.wav")) if capture_dir.exists() else []
        if len(files) != 1:
            time.sleep(0.05)
            continue
        path = files[0]
        if path.stat().st_size > MAX_CAPTURE_BYTES:
            raise ValueError(f"DX-CAPTURE exceeds bounded size: {path.stat().st_size}")
        raw = path.read_bytes()
        try:
            parsed = _finalized_wav(raw)
        except ValueError:
            previous = None
            stable = 0
            time.sleep(0.05)
            continue
        identity = hashlib.sha256(raw).hexdigest()
        if identity == previous:
            stable += 1
        else:
            stable = 1
            previous = identity
        if stable >= 2:
            return path, dict(**{k: v for k, v in parsed.items() if k != "pcm"}, sha256=identity)
        time.sleep(0.05)
    raise TimeoutError("DX-CAPTURE did not produce a stable finalized RIFF/WAVE before deadline")


def _complete_run(call, deadline: float) -> dict:
    operation = call("execution.continue")
    op_id = operation["operation_id"]
    while time.monotonic() < deadline:
        stopped = call("execution.wait", dict(operation_id=op_id, timeout_ms=250))
        if stopped.get("running"):
            continue
        return stopped
    raise TimeoutError("Doom did not report DOS guest completion before the host deadline")


def _wait_to_tic_traced(call, view: _DOSBoxView, image, pc: int, counter: int,
                        address: dict, target: int, initial_tic: int,
                        progress_path: Path, phase: str) -> tuple[int, dict, list[dict]]:
    """Reach one exact leveltime stop with short bounded, retained observations."""
    deadline = time.monotonic() + SOURCE_WAIT_TOTAL_SECONDS
    tic = initial_tic
    records: list[dict] = []
    unchanged_stops = 0

    def persist(update: dict):
        try:
            existing = json.loads(progress_path.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing.update(update)
        _write_progress(progress_path, existing)

    def fail(reason: str, diagnostic: dict):
        persist(dict(phase=phase, wait_status="failed",
            target_tic=target, last_tic=tic, source_wait_records=records,
            failure=reason, terminal_diagnostic=diagnostic))
        raise AssertionError(f"{phase} failed: {reason}; diagnostic={diagnostic}")

    def stop_diagnostic() -> dict:
        try:
            observed = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            regs = view.registers()
            current = placement(view, image)
            timing = call("execution.timing")
            return dict(tic=observed, guest_ticks=timing.get("guest_ticks"),
                cs=regs.get("cs"), ip=regs.get("ip"), placement=None if current is None else dict(
                    runtime_address=current.get("runtime_address"),
                    runtime_target=current.get("runtime_target"),
                    runtime_bytes=current.get("runtime_bytes")))
        except Exception as error:
            return dict(observation_error=repr(error))

    while tic < target:
        if time.monotonic() >= deadline:
            fail("overall 15s source-site wait expired", dict(previous_tic=tic))
        guest_before = call("execution.timing")
        stepped = call("execution.step", dict(mode="into"), timeout_ms=3_000)
        if stepped.get("stop_reason", {}).get("kind") != "step":
            fail("pre-breakpoint step returned a foreign stop", dict(
                step_reply=stepped, observation=stop_diagnostic()))
        point = call("breakpoints.create", dict(kind="execution", once=True, address=address))
        operation = call("execution.continue")
        op_deadline = min(deadline, time.monotonic() + SOURCE_WAIT_PER_STOP_SECONDS)
        stopped = None
        while time.monotonic() < op_deadline:
            stopped = call("execution.wait", dict(
                operation_id=operation["operation_id"], timeout_ms=100))
            if not stopped.get("running", False):
                break
        else:
            pause = call("execution.pause")
            pause_result = call("execution.wait", dict(
                operation_id=pause["operation_id"], timeout_ms=500))
            diagnostic = dict(operation_id=operation["operation_id"],
                expected_breakpoint_id=point.get("breakpoint_id"),
                timeout_seconds=SOURCE_WAIT_PER_STOP_SECONDS, pause_result=pause_result,
                observation=stop_diagnostic())
            fail("one-shot source-site breakpoint exceeded the 2s wait", diagnostic)

        reason = stopped.get("stop_reason", {})
        observation = stop_diagnostic()
        record = dict(tic=observation.get("tic"), guest_ticks_before=guest_before.get("guest_ticks"),
            guest_ticks_after=observation.get("guest_ticks"), stop_reason=reason.get("kind"),
            breakpoint_id=reason.get("breakpoint_id"),
            expected_breakpoint_id=point.get("breakpoint_id"), cs=observation.get("cs"),
            ip=observation.get("ip"), placement=observation.get("placement"))
        records.append(record)
        persist(dict(phase=phase, wait_status="running",
            target_tic=target, last_tic=record["tic"], source_wait_records=records))
        if reason.get("kind") != "breakpoint" or reason.get("breakpoint_id") != point.get("breakpoint_id"):
            fail("foreign or unexpected stop reason", dict(stop=stopped, record=record))
        current = observation.get("placement") or {}
        if current.get("runtime_address") != pc or current.get("runtime_target") != counter:
            fail("stop placement differs from Doom source site", dict(stop=stopped, record=record))
        current_tic = record["tic"]
        if not isinstance(current_tic, int) or current_tic < tic:
            fail("leveltime regressed or became unavailable", dict(stop=stopped, record=record,
                previous_tic=tic))
        if current_tic == tic:
            unchanged_stops += 1
            # The first source stop can observe the same counter as the last
            # timer pause when it lands immediately before INC. A second
            # unchanged source-site visit proves no forward progress.
            if unchanged_stops > 1:
                fail("leveltime failed to advance across consecutive source stops",
                     dict(stop=stopped, record=record, previous_tic=tic))
        else:
            unchanged_stops = 0
        if current_tic > target:
            fail("leveltime passed requested endpoint", dict(stop=stopped, record=record,
                previous_tic=tic))
        tic = current_tic
    if tic != target:
        fail("source-site stop count ended before target", dict(last_tic=tic))
    persist(dict(phase=phase, wait_status="complete",
        target_tic=target, last_tic=tic, source_wait_records=records))
    return tic, placement(view, image), records


def _run_dosbox(root: Path, runtime: dict, reference: bytes, reference_rate: int) -> dict:
    root.mkdir(parents=True)
    game = stage_game(root, runtime["source"])
    source_before = {name: digest(game / name) for name in PINS}
    assert source_before == PINS, source_before
    cfg_before = source_before["DEFAULT.CFG"]
    image = load_runtime_le_carrier((game / "DOOM.EXE").read_bytes())
    wrapper = root / "dosbox-capture-wave"
    wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(str(runtime["dosbox"]))
        + ' "$@" -c "ALIAS CAPW=DX-CAPTURE /A /-D"\n')
    wrapper.chmod(0o700)
    rpc = None
    owner = None
    session_id = None
    progress_path = root / "quit-capture-progress.json"
    progress = dict(format="fdisbull-doom-dosbox-quit-capture-progress-1",
        phase="staged", source_sha256=source_before, config_before_sha256=cfg_before,
        runtime_sha256=runtime["dosbox_sha256"], session_stop_used=False)
    _write_progress(progress_path, progress)
    total_deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    exit_observation = None
    final_wav_path = None
    finalized = None
    owner_close_before_cfg = None
    try:
        rpc = DOSBoxRPC(wrapper, game)
        owner = rpc.process
        assert rpc.capabilities.get("lifecycle", {}).get("dos_guest_exit") is True, rpc.capabilities
        progress["lifecycle_capability"] = True
        started = rpc.call("session.start", dict(
            target=dict(command="CAPW", arguments=["DOOM.EXE", *DOSBOX_ARGUMENTS.split()]),
            mounts=[dict(drive="C", host_path=str(game))], break_at="entry"))
        session_id = started["session_id"]

        def call(method, parameters=None, *, timeout_ms=15_000):
            assert time.monotonic() < total_deadline, f"Doom quit/capture deadline expired at {method}"
            return rpc.call(method, dict(session_id=session_id, **(parameters or {})), timeout_ms=timeout_ms)

        view = _DOSBoxView(call)
        regs = call("state.get_registers")
        assert regs["cpu_mode"] == "real", regs
        selected_psp = int(regs["segments"]["ds"], 16)
        call("execution.timing", dict(fast_forward=True))
        reach_site(view, image)
        site = placement(view, image)
        assert site and site["runtime_address"] == site["cs_base"] + site["ip"]
        pc, counter = site["runtime_address"], site["runtime_target"]
        assert site["runtime_bytes"] == "ff05" + counter.to_bytes(4, "little").hex()
        startup_tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
        assert startup_tic <= START_TIC, startup_tic
        address = dict(space="segmented", segment=f"0x{site['cs']:04x}",
                       offset=f"0x{pc - site['cs_base']:08x}")
        if startup_tic < START_TIC:
            prepared_tic, site = _dosbox_wait_tic(
                call, view, image, pc, counter, address, START_TIC, startup_tic)
        else:
            prepared_tic = startup_tic
        assert prepared_tic == START_TIC, prepared_tic
        assert placement(view, image)["runtime_address"] == pc
        progress.update(phase="source-bound-tic-landmark", leveltime={
            "startup_observation": startup_tic, "prepared_preincrement_tic": prepared_tic,
            "runtime_pc": pc, "counter": counter})
        _write_progress(progress_path, progress)
        call("execution.timing", dict(fast_forward=False))
        capture_dir = Path(rpc.temporary.name) / "capture"
        start_frontier = _dosbox_frontier(capture_dir)
        assert start_frontier["rate"] == 48_000 and start_frontier["channels"] == 2

        sampled_control_tic, control_run = _dosbox_run_ms(
            call, view, counter, CONTROL_END_TIC, DOSBOX_CONTROL_BUDGET_MS,
            prepared_tic)
        control_tic, _ = _dosbox_wait_tic(
            call, view, image, pc, counter, address, CONTROL_END_TIC,
            sampled_control_tic)
        assert control_tic == CONTROL_END_TIC
        control_frontier = _dosbox_frontier(capture_dir)
        control = _dosbox_ammo(view, game)
        assert control["value"] == 50, control
        assert control_frontier["pcm_frames"] > start_frontier["pcm_frames"]
        progress.update(phase="no-shot-control", control_ammo=control["value"],
                        control_frontier=control_frontier["pcm_frames"])
        _write_progress(progress_path, progress)

        shot_start_tic = control_tic
        shot_start_frontier = _dosbox_frontier(capture_dir)
        input_receipt = call("input.keyboard.press", dict(key="ctrl", hold_ms=300, gap_ms=80))
        assert input_receipt
        sampled_shot_tic, shot_run = _dosbox_run_ms(
            call, view, counter, SHOT_END_TIC, DOSBOX_SHOT_BUDGET_MS,
            shot_start_tic)
        shot_end_tic, shot_site, shot_stop_records = _wait_to_tic_traced(
            call, view, image, pc, counter, address, SHOT_END_TIC,
            sampled_shot_tic, progress_path, "post-shot-source-site-wait")
        assert shot_end_tic == SHOT_END_TIC
        shot_end_frontier = _dosbox_frontier(capture_dir)
        after_shot = _dosbox_ammo(view, game)
        assert after_shot["value"] == 49, after_shot
        shot_window_start = shot_start_frontier["pcm_frames"]
        shot_window_end = shot_end_frontier["pcm_frames"]
        assert shot_window_start < shot_window_end, (shot_start_frontier, shot_end_frontier)
        progress.update(phase="shot-observed", ammo_before=control["value"],
            ammo_after=after_shot["value"], shot_start_frontier=shot_window_start,
            shot_end_frontier=shot_window_end, shot_site=shot_site,
            post_run_source_stop_records=shot_stop_records,
            control_run=control_run, shot_run=shot_run)
        _write_progress(progress_path, progress)

        before_quit_frame = _frame(view, root, "before-quit")
        f10_receipt = call("input.keyboard.press", dict(key="f10", hold_ms=120, gap_ms=60))
        progress.update(phase="f10-queued", f10_input=f10_receipt,
                        f10_keyboard_before=call("input.keyboard.state"))
        _write_progress(progress_path, progress)
        quit_prompt_tic, _ = _dosbox_run_ms(
            call, view, counter, TICK_LIMIT, 500, shot_end_tic)
        quit_prompt = _frame(view, root, "quit-prompt")
        prompt_delta = _changed_pixels(root, "before-quit", "quit-prompt")
        progress.update(phase="f10-observed", f10_keyboard_after=call("input.keyboard.state"),
                        quit_prompt_tic=quit_prompt_tic,
                        quit_prompt_changed_pixels=prompt_delta)
        _write_progress(progress_path, progress)
        assert prompt_delta > 500, f"F10 did not display a distinct Doom quit prompt: {prompt_delta}"
        progress.update(phase="quit-prompt-observed", quit_prompt_changed_pixels=prompt_delta)
        _write_progress(progress_path, progress)

        y_receipt = call("input.keyboard.press", dict(key="y", hold_ms=80, gap_ms=80))
        assert y_receipt
        exit_observation = _complete_run(call, time.monotonic() + QUIT_EXIT_DEADLINE_SECONDS)
        # Public execution.wait terminal shape: state=exited plus the selected
        # process stop_reason.kind=guest_exit and retained DOS_Terminate record.
        assert exit_observation.get("state") == "exited", exit_observation
        assert exit_observation.get("stop_reason", {}).get("kind") == "guest_exit", exit_observation
        guest_exit = exit_observation["stop_reason"]["guest_exit"]
        assert guest_exit["requested_exit_code"] == 0 and guest_exit["resident"] is False, guest_exit
        assert guest_exit["source"] == "DOS_Terminate"
        assert guest_exit["stage"] == "after-process-cleanup"
        assert int(guest_exit["psp"], 16) == selected_psp, (guest_exit, selected_psp)
        progress.update(phase="normal-guest-exit", guest_exit={
            "requested_exit_code": guest_exit["requested_exit_code"],
            "resident": guest_exit["resident"], "source": guest_exit["source"],
            "stage": guest_exit["stage"], "psp": guest_exit["psp"]})
        _write_progress(progress_path, progress)

        # Finalization is attributed to the DOS guest exit. Do not call
        # session.stop or close the native owner before the strict WAV check.
        final_wav_path, finalized = _wait_finalized_capture(
            capture_dir, time.monotonic() + WINDOW_DEADLINE_SECONDS)
        if finalized["riff_bytes"] > MAX_CAPTURE_BYTES:
            raise ValueError(f"Finalized capture exceeds bounded copy limit: {finalized['riff_bytes']}")
        retained_wav = root / "doom-final.wav"
        retained_wav.write_bytes(final_wav_path.read_bytes())
        assert _sha(retained_wav) == finalized["sha256"]
        cfg_after_guest_exit = digest(game / "DEFAULT.CFG")

        final_bytes = retained_wav.read_bytes()
        parsed = _finalized_wav(final_bytes)
        final_frames = parsed["frames"]
        assert final_frames >= shot_window_end
        capture_tail_frames = final_frames - shot_window_end
        # The control and shot searches use their separately bracketed live
        # frontiers. Quit-prompt and post-shot buffering stay classified as tail.
        control_start_frame = start_frontier["pcm_frames"]
        control_end_frame = control_frontier["pcm_frames"]
        control_pcm = parsed["pcm"][control_start_frame * 4:control_end_frame * 4]
        assert len(control_pcm) // 4 >= round(48_000 * 0.2), len(control_pcm) // 4
        control_match = _sample_correlation(control_pcm, parsed["rate"], reference,
            reference_rate, reference_samples=CONTROL_REFERENCE_SAMPLES)
        assert control_match["score"] < CORRELATION_THRESHOLD, control_match
        shot_pcm = parsed["pcm"][shot_window_start * 4:shot_window_end * 4]
        assert len(shot_pcm) // 4 >= round(48_000 * 0.5), len(shot_pcm) // 4
        shot_match = _sample_correlation(shot_pcm, parsed["rate"], reference,
            reference_rate, reference_samples=len(reference))
        assert shot_match["score"] >= CORRELATION_THRESHOLD, shot_match

        progress.update(phase="wav-finalized", wav_sha256=finalized["sha256"],
            wav_bytes=finalized["riff_bytes"], wav_frames=final_frames,
            shot_window_frames=[shot_window_start, shot_window_end],
            capture_tail_frames=capture_tail_frames,
            config_side_effects=dict(before_sha256=cfg_before,
                after_guest_exit_sha256=cfg_after_guest_exit,
                changed_at_guest_exit=(cfg_after_guest_exit != cfg_before)))
        _write_progress(progress_path, progress)

        result = dict(backend="dosbox", runtime_sha256=runtime["dosbox_sha256"],
            source_sha256=source_before, config=dict(path="DEFAULT.CFG", before_sha256=cfg_before,
                after_guest_exit_sha256=cfg_after_guest_exit,
                changed_at_guest_exit=(cfg_after_guest_exit != cfg_before)),
            site=dict(runtime_pc=pc, leveltime_counter=counter, instruction_bytes=site["runtime_bytes"]),
            leveltime=dict(start=prepared_tic, startup_observation=startup_tic,
                control_end=control_tic,
                shot_start=shot_start_tic, shot_end=shot_end_tic, quit_prompt=quit_prompt_tic),
            control=dict(ammo=control["value"], frames=[control_start_frame, control_end_frame],
                         dspistol_correlation=control_match),
            shot=dict(input=input_receipt, ammo_before=control["value"], ammo_after=after_shot["value"],
                frames=[shot_window_start, shot_window_end], dspistol_correlation=shot_match),
            quit=dict(f10_input=f10_receipt, prompt_screenshot_sha256=quit_prompt["sha256"],
                prompt_changed_pixels=prompt_delta, y_confirmation_input=y_receipt,
                exit=dict(state="exited", kind="guest_exit", requested_exit_code=guest_exit["requested_exit_code"],
                    resident=guest_exit["resident"], source=guest_exit["source"],
                    stage=guest_exit["stage"], psp=guest_exit["psp"])),
            audio=dict(header_finalized=True, capture_completeness="not_claimed",
                sample_format="s16", rate=parsed["rate"], channels=parsed["channels"],
                riff_bytes=parsed["riff_bytes"], riff_declared_bytes=parsed["riff_bytes"],
                data_bytes=parsed["data_bytes"], frames=final_frames,
                shot_window_frames=[shot_window_start, shot_window_end],
                post_shot_capture_tail_frames=capture_tail_frames,
                tail_scope="includes audio buffered after the observed shot frontier and quit prompt/exit; excluded from shot match",
                sha256=finalized["sha256"]),
            owner_cleanup=None)
        progress.update(phase="verified-before-owner-close", result=result)
        _write_progress(progress_path, progress)
    finally:
        if rpc is not None:
            rpc.close()
    assert owner is not None and owner.poll() is not None
    assert owner.returncode == 0, owner.returncode
    cfg_after_owner_close = digest(game / "DEFAULT.CFG")
    game_after = {name: digest(game / name) for name in PINS if name != "DEFAULT.CFG"}
    expected_nonconfig = {name: PINS[name] for name in game_after}
    assert game_after == expected_nonconfig
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    result["config"]["after_owner_close_sha256"] = cfg_after_owner_close
    result["config"]["changed_on_owner_close"] = cfg_after_owner_close != result["config"]["after_guest_exit_sha256"]
    result["config"]["changed_from_pinned_input"] = cfg_after_owner_close != cfg_before
    result["owner_cleanup"] = dict(reaped=True, returncode=owner.returncode)
    progress.update(phase="accepted", result=result)
    _write_progress(progress_path, progress)
    return result


def test_original_doom_dosbox_quit_finalizes_pistol_capture(tmp_path, doom_dosbox_quit_runtime):
    checkout = Path(__file__).resolve().parents[1]
    try:
        Path(tmp_path).resolve(strict=True).relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom inputs and captures must stay outside the checkout")
    runtime = doom_dosbox_quit_runtime
    assert {name: digest(runtime["source"] / name) for name in PINS} == PINS
    reference, reference_rate = _read_dspistol(runtime["source"] / "DOOM.WAD")
    result = _run_dosbox(tmp_path / "dosbox-quit-capture", runtime, reference, reference_rate)
    assert result["quit"]["exit"]["requested_exit_code"] == 0
    assert result["quit"]["exit"]["source"] == "DOS_Terminate"
    assert result["audio"]["header_finalized"] is True
    assert result["audio"]["riff_bytes"] == result["audio"]["riff_declared_bytes"]
    assert result["shot"]["ammo_before"] == 50 and result["shot"]["ammo_after"] == 49
    assert result["shot"]["dspistol_correlation"]["score"] >= CORRELATION_THRESHOLD
    assert result["owner_cleanup"] == dict(reaped=True, returncode=0)
    _write_progress(Path(tmp_path) / "doom-dosbox-quit-capture-result.json", dict(
        format="fdisbull-doom-dosbox-quit-capture-1", phase="accepted", result=result,
        reference=dict(lump="DSPISTOL", rate_hz=reference_rate,
            sha256=hashlib.sha256(reference).hexdigest(),
            guard_samples_removed_per_end=REFERENCE_GUARD_SAMPLES),
        scope="one pinned original Doom E1M1 DOSBox-X shot, F10/Y normal DOS quit, strict finalized DX-CAPTURE RIFF/data extents; capture tail excluded from shot correlation"))
