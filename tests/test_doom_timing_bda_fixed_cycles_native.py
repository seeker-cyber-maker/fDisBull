"""Opt-in three-arm Doom timing trial with auto and fixed-cycle DOSBox-X.

Attempt 02 of the earlier fixed-cycle run settled at tic 74, beyond its tic-70
target, so it produced no measurement and did not launch QEMU. This trial moves
all arms to tic 80. Effective cycle readback remains unavailable; the receipt
records both requested profiles, not proof that the engine applied either one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from support.doom_le_qemu import PINS, runtime_inputs as qemu_runtime_inputs
from test_doom_timing_bda_paired_native import (
    _dosbox_measure,
    _qemu_measure,
    _sha,
    _source_hashes,
)
from test_doom_timing_bda_window_sweep_native import (
    MAX_OVERSHOOT_MS,
    POLL_WAIT_MS,
)


BUDGET_MS = 900
START_TIC = 80
REQUESTED_DOSBOX_AUTO_CYCLES = "cpu cycles=auto"
REQUESTED_DOSBOX_CYCLES = "cpu cycles=fixed 157600"


def test_paired_doom_timing_bda_fixed_dosbox_cycles(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_TIMING_BDA_FIXED_CYCLES") != "1":
        pytest.skip(
            "Set FDISBULL_REQUIRE_DOOM_TIMING_BDA_FIXED_CYCLES=1 with pinned private runtimes")

    checkout = Path(__file__).resolve().parents[1]
    try:
        Path(tmp_path).resolve(strict=True).relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom timing inputs and receipt must stay outside the checkout")

    source_value = os.environ.get("FDISBULL_DOOM_LE_SOURCE")
    dosbox_value = os.environ.get("FDISBULL_DOSBOX")
    missing = [name for name, value in (
        ("FDISBULL_DOOM_LE_SOURCE", source_value),
        ("FDISBULL_DOSBOX", dosbox_value),
    ) if not value]
    if missing:
        pytest.fail("Fixed-cycle Doom timing inputs missing: " + ", ".join(missing))

    source = Path(source_value).expanduser().resolve(strict=True)
    original_dosbox = Path(dosbox_value).expanduser().resolve(strict=True)
    assert source.is_dir() and original_dosbox.is_file()
    assert os.access(original_dosbox, os.X_OK)
    assert _source_hashes(source) == PINS
    qemu_runtime = qemu_runtime_inputs()
    assert Path(qemu_runtime["firmware"]).is_dir()
    for key in ("boot_image", "executable", "mcopy", "checkpoint_tool"):
        assert _sha(qemu_runtime[key])

    # This test-local launcher preserves DOSBoxRPC's normal constructor args,
    # then appends one requested setting without touching user configuration.
    def cycles_launcher(name, setting):
        launcher = Path(tmp_path) / name
        launcher.write_text(
            "#!" + sys.executable + "\nimport os, sys\n"
            + "native=" + repr(str(original_dosbox)) + "\n"
            + "setting=" + repr(setting) + "\n"
            + "os.execv(native, [native, *sys.argv[1:], '-set', setting])\n"
        )
        launcher.chmod(0o700)
        return launcher, _sha(launcher)

    auto_launcher, auto_launcher_sha256 = cycles_launcher(
        "dosbox-auto-cycles", REQUESTED_DOSBOX_AUTO_CYCLES)
    launcher, launcher_sha256 = cycles_launcher(
        "dosbox-fixed-cycles", REQUESTED_DOSBOX_CYCLES)
    original_dosbox_sha256 = _sha(original_dosbox)

    auto_stage = Path(tmp_path) / "dosbox-auto"
    fixed_stage = Path(tmp_path) / "dosbox-fixed"
    qemu_stage = Path(tmp_path) / "qemu"
    auto_stage.mkdir()
    fixed_stage.mkdir()
    qemu_stage.mkdir()

    auto_result = _dosbox_measure(
        auto_stage, source, auto_launcher, poll_wait_ms=POLL_WAIT_MS,
        max_window_overshoot_ms=MAX_OVERSHOOT_MS,
        target_start_tic=START_TIC, budget_ms=BUDGET_MS)
    fixed_result = _dosbox_measure(
        fixed_stage, source, launcher, poll_wait_ms=POLL_WAIT_MS,
        max_window_overshoot_ms=MAX_OVERSHOOT_MS,
        target_start_tic=START_TIC, budget_ms=BUDGET_MS)
    qemu_result = _qemu_measure(
        qemu_stage, source, qemu_runtime, START_TIC, budget_ms=BUDGET_MS)

    assert auto_result["start_tic"] == fixed_result["start_tic"] == qemu_result["start_tic"] == START_TIC
    assert auto_result["owner_reaped"] and fixed_result["owner_reaped"] and qemu_result["owner_reaped"]
    assert auto_result["guest_time_budget"]["overshoot"] <= MAX_OVERSHOOT_MS
    assert fixed_result["guest_time_budget"]["overshoot"] <= MAX_OVERSHOOT_MS
    assert qemu_result["guest_time_budget"]["overshoot"] <= MAX_OVERSHOOT_MS * 1_000_000
    assert auto_result["intermediate_execution_breakpoints"] == 0
    assert fixed_result["intermediate_execution_breakpoints"] == 0
    assert qemu_result["intermediate_execution_breakpoints"] == 0
    assert auto_result["uninterrupted_guest_continues"] == 1
    assert fixed_result["uninterrupted_guest_continues"] == 1
    assert qemu_result["uninterrupted_guest_continues"] == 1
    assert _source_hashes(source) == PINS
    assert _sha(auto_launcher) == auto_launcher_sha256
    assert _sha(launcher) == launcher_sha256
    assert _sha(original_dosbox) == original_dosbox_sha256

    def observed_difference(left, right):
        return dict(
            doom_leveltime=left["leveltime_delta"] - right["leveltime_delta"],
            bda_ticks=left["bda"]["delta"] - right["bda"]["delta"],
            clock_delta=None,
            clock_delta_note="not subtracted because engine clocks use separate domains")

    receipt = dict(
        format="fdisbull-doom-bda-three-arm-fixed-cycles-trial-1",
        scope=("Three bounded 900 ms E1M1 intervals beginning at pre-increment "
               "leveltime 80: DOSBox-X auto cycles, DOSBox-X requested fixed "
               "cycles, and unchanged QEMU virtual-clock execution."),
        prior_attempt=dict(
            attempt="02",
            outcome="DOSBox fixed-cycle settling ended at tic 74, past the tic-70 target; no measurement and no QEMU run.",
            interpretation="setup failure only; not a timing observation"),
        source_sha256=PINS["DOOM.EXE"],
        private_input_sha256=PINS,
        requested_guest_ms=BUDGET_MS,
        start=dict(kind="pre-increment Doom leveltime", tic=START_TIC),
        dosbox_auto_requested_profile=REQUESTED_DOSBOX_AUTO_CYCLES,
        dosbox_auto_effective_profile_verified=False,
        dosbox_auto_launcher_sha256=auto_launcher_sha256,
        dosbox_requested_profile=REQUESTED_DOSBOX_CYCLES,
        dosbox_effective_profile_verified=False,
        dosbox_launcher_sha256=launcher_sha256,
        dosbox_underlying_binary_sha256=original_dosbox_sha256,
        dosbox_poll_wait_ms=POLL_WAIT_MS,
        maximum_accepted_overshoot_ms=MAX_OVERSHOOT_MS,
        engines=dict(dosbox_auto=auto_result, dosbox_fixed=fixed_result,
                     qemu=qemu_result),
        actual_clock_intervals=dict(
            dosbox_auto_pic_guest_ms=auto_result["engine_clock"]["delta"],
            dosbox_fixed_pic_guest_ms=fixed_result["engine_clock"]["delta"],
            qemu_virtual_ns=qemu_result["engine_clock"]["delta"],
            qemu_virtual_ms=qemu_result["engine_clock"]["delta"] / 1_000_000,
            common_clock_claim="none"),
        observed_deltas=dict(
            dosbox_auto_doom_leveltime=auto_result["leveltime_delta"],
            dosbox_fixed_doom_leveltime=fixed_result["leveltime_delta"],
            qemu_doom_leveltime=qemu_result["leveltime_delta"],
            dosbox_auto_bda_ticks=auto_result["bda"]["delta"],
            dosbox_fixed_bda_ticks=fixed_result["bda"]["delta"],
            qemu_bda_ticks=qemu_result["bda"]["delta"],
            bda_tick_period_ns=54_925_493),
        pairwise_observations=dict(
            dosbox_auto_minus_fixed=observed_difference(auto_result, fixed_result),
            dosbox_fixed_minus_qemu=observed_difference(fixed_result, qemu_result),
            interpretation="descriptive deltas only; no parity or causality claim"),
        endpoint_uncertainty=dict(
            atomic=False,
            dosbox_auto=("Threshold is observed through 10 ms RPC polling, then pause is "
                         "requested; pause and RPC latency remain in elapsed time."),
            dosbox_fixed=("Threshold is observed through 10 ms RPC polling, then pause is "
                          "requested; pause and RPC latency remain in elapsed time."),
            qemu=("QEMU virtual-clock timer requests the stop; its own clock and "
                  "stop receipt are retained independently."),
            bda=("Independent start/end phases are uncalibrated; no shared-clock "
                 "mapping or causality inference is made.")),
        claims=dict(shared_clock="none", causality="none", timing_parity="none"),
        limitations=[
            "Both DOSBox settings are requested on launcher command lines; effective cycle readback is unavailable.",
            "Attempt 02 was a setup miss and produced no timing values; the auto-cycle arm in this receipt is measured in this attempt.",
            "The two engine clocks are separate domains and are reported independently.",
            "A single interval per engine does not establish general timing parity or causality.",
            "BDA tick deltas have independent endpoint phase uncertainty.",
            "Private media, project databases, screenshots, audio and VM states remain outside the checkout.",
        ])
    (Path(tmp_path) / "fixed-cycles-900ms-bda-timing.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
