"""Opt-in matched Doom timing windows at two bounded guest-time budgets.

Each case begins both engines at the source-bound pre-increment leveltime 70.
DOSBox-X uses a 10 ms wait poll and a 20 ms maximum accepted overshoot; QEMU
uses its native virtual-clock timer. Receipts retain each engine's own clock,
BDA and Doom deltas without assigning a parity or failure verdict.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from support.doom_le_qemu import PINS, runtime_inputs as qemu_runtime_inputs
from test_doom_timing_bda_paired_native import (
    _dosbox_measure,
    _qemu_measure,
    _sha,
    _source_hashes,
)


START_TIC = 70
POLL_WAIT_MS = 10
MAX_OVERSHOOT_MS = 20


@pytest.mark.parametrize("budget_ms", [300, 900], ids=["300ms", "900ms"])
def test_paired_doom_timing_bda_window_sweep(tmp_path, budget_ms):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_TIMING_BDA_WINDOW_SWEEP") != "1":
        pytest.skip(
            "Set FDISBULL_REQUIRE_DOOM_TIMING_BDA_WINDOW_SWEEP=1 with pinned private runtimes")
    checkout = Path(__file__).resolve().parents[1]
    try:
        Path(tmp_path).resolve(strict=True).relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom timing states and receipts must stay outside the checkout")

    source_value = os.environ.get("FDISBULL_DOOM_LE_SOURCE")
    dosbox_value = os.environ.get("FDISBULL_DOSBOX")
    missing = [name for name, value in (("FDISBULL_DOOM_LE_SOURCE", source_value),
                                        ("FDISBULL_DOSBOX", dosbox_value)) if not value]
    if missing:
        pytest.fail("Window-sweep Doom timing inputs missing: " + ", ".join(missing))
    source = Path(source_value).expanduser().resolve(strict=True)
    dosbox = Path(dosbox_value).expanduser().resolve(strict=True)
    assert source.is_dir() and dosbox.is_file() and os.access(dosbox, os.X_OK)
    assert _source_hashes(source) == PINS
    qemu_runtime = qemu_runtime_inputs()
    assert Path(qemu_runtime["firmware"]).is_dir()
    assert _sha(qemu_runtime["boot_image"])
    assert _sha(qemu_runtime["executable"])
    assert _sha(dosbox)

    dosbox_result = _dosbox_measure(
        tmp_path, source, dosbox, poll_wait_ms=POLL_WAIT_MS,
        max_window_overshoot_ms=MAX_OVERSHOOT_MS,
        target_start_tic=START_TIC, budget_ms=budget_ms)
    qemu_result = _qemu_measure(
        tmp_path, source, qemu_runtime, dosbox_result["start_tic"],
        budget_ms=budget_ms)

    assert dosbox_result["start_tic"] == qemu_result["start_tic"] == START_TIC
    assert dosbox_result["owner_reaped"] and qemu_result["owner_reaped"]
    assert dosbox_result["guest_time_budget"]["overshoot"] <= MAX_OVERSHOOT_MS
    assert qemu_result["guest_time_budget"]["overshoot"] <= MAX_OVERSHOOT_MS * 1_000_000
    assert dosbox_result["intermediate_execution_breakpoints"] == 0
    assert qemu_result["intermediate_execution_breakpoints"] == 0
    assert dosbox_result["uninterrupted_guest_continues"] == 1
    assert qemu_result["uninterrupted_guest_continues"] == 1
    assert _source_hashes(source) == PINS

    dosbox_elapsed = dosbox_result["engine_clock"]["delta"]
    qemu_elapsed_ns = qemu_result["engine_clock"]["delta"]
    receipt = dict(
        format="fdisbull-doom-bda-window-sweep-1",
        scope=("One source-bound Doom E1M1 interval per engine at matched "
               "pre-increment leveltime 70, using the requested budget in each "
               "engine's own guest-time domain."),
        source_sha256=PINS["DOOM.EXE"],
        private_input_sha256=PINS,
        requested_guest_ms=budget_ms,
        start=dict(kind="pre-increment Doom leveltime", tic=START_TIC),
        dosbox_poll_wait_ms=POLL_WAIT_MS,
        maximum_accepted_overshoot_ms=MAX_OVERSHOOT_MS,
        engines=dict(dosbox=dosbox_result, qemu=qemu_result),
        actual_clock_intervals=dict(
            dosbox_pic_guest_ms=dosbox_elapsed,
            qemu_virtual_ns=qemu_elapsed_ns,
            qemu_virtual_ms=qemu_elapsed_ns / 1_000_000,
            common_clock_claim="none"),
        observed_deltas=dict(
            dosbox_doom_leveltime=dosbox_result["leveltime_delta"],
            qemu_doom_leveltime=qemu_result["leveltime_delta"],
            dosbox_bda_ticks=dosbox_result["bda"]["delta"],
            qemu_bda_ticks=qemu_result["bda"]["delta"],
            bda_tick_period_ns=54_925_493),
        endpoint_uncertainty=dict(
            dosbox=dict(atomic=False,
                        observed_overshoot_ms=dosbox_result["guest_time_budget"]["overshoot"],
                        description=("DOSBox-X threshold is observed by 10 ms RPC polling, "
                                     "then pause is requested; pause/RPC latency remains "
                                     "included in elapsed time.")),
            qemu=dict(atomic=False,
                      observed_overshoot_ns=qemu_result["guest_time_budget"]["overshoot"],
                      description=("The QEMU virtual-clock timer requests the stop; the "
                                   "recorded interval and stop receipt remain authoritative.")),
            bda=dict(uncertainty=("Independent start/end phases are uncalibrated; raw "
                                  "tick deltas are retained without mapping BDA to a "
                                  "shared clock."))),
        limitations=[
            "The two engine clocks are separate domains; their elapsed values are reported independently.",
            "A single interval at each requested window does not establish general timing parity, failure, or a calibrated rate.",
            "BDA tick deltas have independent endpoint phase uncertainty.",
            "No audio was captured, and no audio timing or delivery claim is made.",
            "Private media, project databases, screenshots, audio, and VM states remain outside the checkout.",
        ])
    (tmp_path / f"paired-window-{budget_ms}ms-bda-timing.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
