"""Opt-in QEMU Doom E1M1 pistol endpoint followed by ordinary DOS guest exit.

Private inputs and captures stay under pytest's private temp directory. The
test records key dispatch and exit evidence without assigning sole causation
to an input callback or treating QEMU shutdown as guest completion.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from fdisbull.project import Project
from support.doom_gameplay import capture_statusbar, decode_ammo_from_wad
from support.doom_le_qemu import CODE_OFFSET, DATA_OFFSET, PINS, runtime_inputs as qemu_runtime_inputs, stage_game
from test_doom_leveltime_paired_native import _qemu_rebind_at_endpoint, _qemu_site, _qemu_wait_tic
from test_doom_pistol_sfx_paired_native import (
    BDA_ADDRESS, BDA_TICKS_PER_DAY, CONTROL_END_TIC, CORRELATION_THRESHOLD,
    MAX_AUDIO_FRAMES, QEMU_ARGUMENTS, QEMU_CONTROL_BUDGET_MS,
    QEMU_SHOT_BUDGET_MS, SHOT_END_TIC,
    START_TIC, _qemu_advance_to_tic, _qemu_bda, _qemu_capture_window, _read_dspistol,
    _sample_correlation, _sha, _source_hashes,
)


def _directory_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): _sha(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def _public_exit(debug, result):
    assert result.get("outcome") == "guest_exit", result
    process = result.get("process", {})
    assert process.get("state") == "exited", process
    termination = process.get("termination", {})
    assert termination.get("type") == "normal" and termination.get("code") == 0, termination
    assert result.get("session", {}).get("state") == "stopped", result
    assert debug.dos_process_info() == process
    assert debug.vm.process.poll() is None, "QEMU itself should still be alive at DOS guest return"
    return process


def _assert_dispatched_chord(observation):
    assert observation.get("state") == "dispatched", observation
    assert observation.get("edge_count") == 2, observation
    press = observation.get("press", {})
    assert press.get("dispatched_count") == 2, press
    assert [edge.get("down") for edge in press.get("steps", [])] == [True, False], press


def _remove_source_breakpoint(debug, pc: int, breakpoint_id: str) -> list[str]:
    # The public QEMU machine API rejects duplicate user aliases at one PC.
    # Check that registry invariant, delete the exact owned ID, then verify it.
    def matches(row):
        return row.get("access") == "x" and row.get("address") == pc

    before = [identifier for identifier, row in debug.breakpoints.items() if matches(row)]
    assert before == [breakpoint_id], before
    debug.delete_breakpoint(breakpoint_id)
    after = [identifier for identifier, row in debug.breakpoints.items() if matches(row)]
    assert not after, after
    return before


def _changed_pixels(before: Path, after: Path) -> int:
    with Image.open(before) as left, Image.open(after) as right:
        left_frame = left.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        right_frame = right.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        diff = ImageChops.difference(left_frame, right_frame).tobytes()
    return sum(diff[index:index + 3] != b"\0\0\0" for index in range(0, len(diff), 3))


def test_qemu_doom_e1m1_pistol_endpoint_then_normal_guest_exit(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_QEMU_PISTOL_EXIT") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_QEMU_PISTOL_EXIT=1 for pinned private Doom inputs")
    checkout = Path(__file__).resolve().parents[1]
    output = Path(tmp_path).resolve(strict=True)
    try:
        output.relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom databases, screenshots, audio, and receipts must stay outside the checkout")

    qemu_runtime = qemu_runtime_inputs()
    source_value = os.environ.get("FDISBULL_DOOM_LE_SOURCE")
    if not source_value:
        raise RuntimeError("Set FDISBULL_DOOM_LE_SOURCE for the private pinned Doom source")
    source = Path(source_value).expanduser().resolve(strict=True)
    assert _source_hashes(source) == PINS
    reference, reference_rate = _read_dspistol(source / "DOOM.WAD")
    game = stage_game(output, source)
    hashes_before = _directory_hashes(game)
    assert {name: hashes_before.get(name) for name in PINS} == PINS, hashes_before
    owners = []
    database = output / "doom-quit.fdb"
    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        options = dict(backend="qemu-dos", dos_directory=str(game),
            dos_boot_image=str(qemu_runtime["boot_image"]), dos_mcopy=str(qemu_runtime["mcopy"]),
            qemu_transport="pipe", qemu_firmware=qemu_runtime["firmware"],
            qemu_audio="sb16-opl", qemu_retrace="precise", qemu_clock="virtual",
            qemu_checkpoint_tool=str(qemu_runtime["checkpoint_tool"]),
            dos_arguments=QEMU_ARGUMENTS, boot_timeout_ms=35_000)
        with project.debugger(qemu_runtime["executable"], game, _on_spawn=owners.append, **options) as debug:
            pc, counter, instruction = _qemu_site(project, debug, output / "source-binding.json")
            breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
            start_tic, _, breakpoint_id = _qemu_wait_tic(debug, pc, counter, breakpoint_id, START_TIC)
            start_binding = _qemu_rebind_at_endpoint(debug, pc, counter, START_TIC)
            start_clock, start_bda = debug.clock_observe(), _qemu_bda(debug)

            capture_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert capture_start["state"] == "capturing", capture_start
            control, breakpoint_id = _qemu_capture_window(debug, project, output, "qemu-no-shot",
                pc, counter, breakpoint_id, CONTROL_END_TIC, QEMU_CONTROL_BUDGET_MS)
            control_match = _sample_correlation(control["audio"]["pcm"], control["audio"]["rate"],
                reference, reference_rate, reference_samples=2048)
            assert control_match["score"] < CORRELATION_THRESHOLD, control_match
            control_view = capture_statusbar(project, debug, output, "control-end")
            control_ammo = decode_ammo_from_wad(game / "DOOM.WAD", control_view["statusbar"])
            assert control_ammo["value"] == 50, control_ammo

            before_view = capture_statusbar(project, debug, output, "before-shot")
            before_ammo = decode_ammo_from_wad(game / "DOOM.WAD", before_view["statusbar"])
            assert before_ammo["value"] == 50, before_ammo
            shot_clock, shot_bda = debug.clock_observe(), _qemu_bda(debug)
            shot_start = debug.audio_start(max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert shot_start["state"] == "capturing", shot_start
            shot_press = debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            assert shot_press.get("state") == "armed", shot_press
            shot_tick, breakpoint_id = _qemu_advance_to_tic(debug, pc, counter, breakpoint_id,
                SHOT_END_TIC, QEMU_SHOT_BUDGET_MS)
            endpoint_binding = _qemu_rebind_at_endpoint(debug, pc, counter, SHOT_END_TIC)
            endpoint_clock, endpoint_bda = debug.clock_observe(), _qemu_bda(debug)
            shot_edges = debug.input_schedule_observe()
            _assert_dispatched_chord(shot_edges)
            shot_stop = debug.audio_stop()
            assert shot_stop["state"] == "stopped" and shot_stop["dropped_frames"] == 0, shot_stop
            shot_artifact = debug.capture_audio("qemu-shot.wav")
            shot_wav = output / "qemu-shot.wav"
            project.debug_export(shot_artifact["artifact"], shot_wav)
            from test_doom_pistol_sfx_paired_native import _wav_pcm
            shot_audio = _wav_pcm(shot_wav.read_bytes(), finalized=True)
            shot_match = _sample_correlation(shot_audio["pcm"], shot_audio["rate"], reference,
                reference_rate, reference_samples=len(reference))
            after_view = capture_statusbar(project, debug, output, "after-shot")
            after_ammo = decode_ammo_from_wad(game / "DOOM.WAD", after_view["statusbar"])
            assert after_ammo["value"] == 49, after_ammo
            assert shot_match["score"] >= CORRELATION_THRESHOLD, shot_match

            # The tested endpoint is now pinned: original WAD ammo 50→49 and
            # a WAD-derived DSPISTOL match in the bounded audio capture.
            removed_breakpoints = _remove_source_breakpoint(debug, pc, breakpoint_id)
            f10_press = debug.keyboard_press("f10", hold_ms=120, gap_ms=60)
            assert f10_press.get("state") == "armed", f10_press
            before_quit = debug.screenshot(name="before-quit.png")
            before_quit_path = output / "before-quit.png"
            project.debug_export(before_quit["artifact"], before_quit_path)
            prompt_advance = debug.clock_advance(500_000_000, timeout_ms=15_000)
            prompt_budget = prompt_advance.get("clock_budget", {})
            assert prompt_budget.get("deadline_reached") is True, prompt_advance
            assert prompt_budget.get("elapsed_ns", 0) >= 500_000_000, prompt_advance
            f10_edges = debug.input_schedule_observe()
            _assert_dispatched_chord(f10_edges)
            assert prompt_advance.get("outcome") not in ("guest_exit", "guest_tsr", "exited"), prompt_advance
            prompt_image = debug.screenshot()
            prompt_path = output / "quit-prompt.png"
            project.debug_export(prompt_image["artifact"], prompt_path)
            prompt_delta = _changed_pixels(before_quit_path, prompt_path)
            assert prompt_delta > 500, f"F10 produced no distinct normalized frame transition: {prompt_delta}"
            y_press = debug.keyboard_press("y", hold_ms=120, gap_ms=60)
            assert y_press.get("state") == "armed", y_press

            exit_result = None
            exit_edges = None
            for _ in range(40):
                exit_result = debug.clock_advance(250_000_000, timeout_ms=15_000)
                exit_edges = debug.input_schedule_observe()
                if exit_result.get("outcome") in ("guest_exit", "guest_tsr", "exited"):
                    break
            process = _public_exit(debug, exit_result)
            assert exit_edges is not None, "Y input observation was not retained"
            run_id = debug.run_id
            evidence = dict(
                scope="one pinned original Doom E1M1 QEMU run: pistol/audio endpoint, then F10/Y dispatch followed by public normal DOS guest exit",
                source_pins=PINS, runtime_sha256=_sha(qemu_runtime["executable"]),
                boot_sha256=_sha(qemu_runtime["boot_image"]), qemu_argument=QEMU_ARGUMENTS,
                source_site=dict(pc=pc, counter=counter, inc_bytes=instruction.hex(),
                    object_index=1, object_offset=CODE_OFFSET, counter_object=3, counter_offset=DATA_OFFSET),
                endpoint=dict(start_tic=start_tic, control_end_tic=CONTROL_END_TIC,
                    shot_end_tic=shot_tick, start_binding=start_binding["binding_id"],
                    endpoint_binding=endpoint_binding["binding_id"],
                    clock_ns=dict(start=start_clock["virtual_ns"], shot=shot_clock["virtual_ns"],
                                  endpoint=endpoint_clock["virtual_ns"]),
                    bda_raw_ticks=dict(address=hex(BDA_ADDRESS), start=start_bda,
                        shot=shot_bda, endpoint=endpoint_bda,
                        shot_delta=(endpoint_bda-shot_bda) % BDA_TICKS_PER_DAY)),
                gameplay=dict(ammo_before=before_ammo["value"], ammo_after=after_ammo["value"],
                    ammo_wad_sha256=after_ammo["wad_sha256"], shot_edges=shot_edges,
                    control_audio_correlation=control_match,
                    shot_audio=dict(sha256=_sha(shot_wav), frames=shot_audio["frames"],
                        rate=shot_audio["rate"], channels=shot_audio["channels"],
                        dropped_frames=shot_stop["dropped_frames"], correlation=shot_match)),
                quit=dict(f10_arm=f10_press, f10_observation=f10_edges,
                    prompt_advance=prompt_advance, prompt_screenshot_sha256=prompt_image["sha256"],
                    prompt_changed_pixels=prompt_delta,
                    prompt_frame_claim="normalized frames differ by >500 pixels; no prompt OCR/classification",
                    removed_source_breakpoint_ids=removed_breakpoints,
                    y_arm=y_press, y_observation=exit_edges,
                    attribution="F10 and Y were dispatched before guest_exit; this does not prove exclusive causal role or guest consumption."),
                guest_exit=dict(result=exit_result, process=process,
                    qemu_alive_at_guest_return=debug.vm.process.poll() is None),
                config_side_effects="recorded from complete staged-game pre/post path and hash inventories",
                api_run_id=run_id)

    assert owners and all(owner.poll() is not None for owner in owners), [owner.poll() for owner in owners]
    assert all(owner.returncode == 0 for owner in owners), [owner.returncode for owner in owners]
    hashes_after = _directory_hashes(game)
    expected_names = {path.relative_to(game).as_posix() for path in game.rglob("*") if path.is_file()}
    changed = {name: dict(before=hashes_before.get(name), after=hashes_after.get(name))
               for name in sorted(set(hashes_before) | set(hashes_after))
               if hashes_before.get(name) != hashes_after.get(name)}
    unexpected = sorted(name for name in changed if name != "DEFAULT.CFG")
    assert not unexpected, {"unexpected_staged_file_changes": unexpected, "changed": changed}
    assert _source_hashes(source) == PINS
    evidence["config_changes"] = dict(changed=changed, default_cfg_changed="DEFAULT.CFG" in changed,
                                      staged_file_count=len(expected_names), owner_returncodes=[o.returncode for o in owners])
    evidence["source_after"] = _source_hashes(source)
    (output / "qemu-doom-pistol-guest-exit.json").write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
