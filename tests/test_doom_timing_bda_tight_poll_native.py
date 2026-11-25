"""Opt-in bounded Doom timing comparison with tighter DOSBox-X polling.

This keeps each engine's own observed clock, BDA ticks and source-bound Doom
leveltime delta. DOSBox-X defaults to a 10 ms operation-wait poll and a 20 ms
overshoot cap; bounded environment overrides can probe observer effects.
Endpoints remain non-atomic;
the result classifies whether the earlier three-tic difference persists and
does not assert general timing or gameplay parity.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from support.doom_le_qemu import PINS, runtime_inputs as qemu_runtime_inputs
from test_doom_timing_bda_paired_native import (
    BUDGET_MS,
    START_TIC,
    _dosbox_measure,
    _qemu_measure,
    _sha,
    _source_hashes,
)


DEFAULT_DOSBOX_POLL_WAIT_MS = 10
DEFAULT_DOSBOX_MAX_OVERSHOOT_MS = 20


def test_paired_doom_timing_bda_with_tight_dosbox_poll(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_TIMING_BDA_TIGHT_POLL") != "1":
        pytest.skip(
            "Set FDISBULL_REQUIRE_DOOM_TIMING_BDA_TIGHT_POLL=1 with pinned private runtimes")
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
        pytest.fail("Tight-poll Doom timing inputs missing: " + ", ".join(missing))
    source = Path(source_value).expanduser().resolve(strict=True)
    dosbox = Path(dosbox_value).expanduser().resolve(strict=True)
    assert source.is_dir() and dosbox.is_file() and os.access(dosbox, os.X_OK)
    assert _source_hashes(source) == PINS
    qemu_runtime = qemu_runtime_inputs()
    assert Path(qemu_runtime["firmware"]).is_dir()
    assert _sha(qemu_runtime["boot_image"])
    assert _sha(qemu_runtime["executable"])
    assert _sha(dosbox)
    poll_wait_ms = int(os.environ.get(
        "FDISBULL_DOOM_TIMING_POLL_MS", str(DEFAULT_DOSBOX_POLL_WAIT_MS)))
    max_overshoot_ms = int(os.environ.get(
        "FDISBULL_DOOM_TIMING_MAX_OVERSHOOT_MS",
        str(DEFAULT_DOSBOX_MAX_OVERSHOOT_MS)))
    start_tic_value = os.environ.get("FDISBULL_DOOM_TIMING_START_TIC")
    target_start_tic = None
    if start_tic_value is not None:
        try:
            target_start_tic = int(start_tic_value)
        except ValueError:
            pytest.fail("FDISBULL_DOOM_TIMING_START_TIC must be an integer in 64..200")
        if not START_TIC <= target_start_tic <= 200:
            pytest.fail("FDISBULL_DOOM_TIMING_START_TIC must be in 64..200")

    # The DOSBox endpoint is an observed threshold followed by pause, not an
    # atomic clock stop. An optional target start tic is reacquired from the
    # source site after ordinary-speed settling, so both engines use that tic.
    # QEMU retains its existing native virtual-clock timer.
    dosbox_result = _dosbox_measure(
        tmp_path, source, dosbox, poll_wait_ms=poll_wait_ms,
        max_window_overshoot_ms=max_overshoot_ms,
        target_start_tic=target_start_tic)
    qemu_result = _qemu_measure(
        tmp_path, source, qemu_runtime, dosbox_result["start_tic"])

    assert dosbox_result["start_tic"] >= START_TIC
    assert qemu_result["start_tic"] == dosbox_result["start_tic"]
    assert dosbox_result["owner_reaped"] and qemu_result["owner_reaped"]
    assert dosbox_result["guest_time_budget"]["overshoot"] <= max_overshoot_ms
    assert dosbox_result["intermediate_execution_breakpoints"] == 0
    assert qemu_result["intermediate_execution_breakpoints"] == 0
    assert dosbox_result["uninterrupted_guest_continues"] == 1
    assert qemu_result["uninterrupted_guest_continues"] == 1
    assert _source_hashes(source) == PINS

    qemu_elapsed_ms = qemu_result["engine_clock"]["delta"] / 1_000_000
    dosbox_elapsed_ms = dosbox_result["guest_time_budget"]["elapsed"]
    tic_delta_difference = (dosbox_result["leveltime_delta"]
                            - qemu_result["leveltime_delta"])
    if tic_delta_difference == 3:
        classification = "three_tic_difference_persists"
    elif abs(tic_delta_difference) <= 1:
        classification = "three_tic_difference_not_reproduced"
    else:
        classification = "intermediate_tic_difference"

    receipt = dict(
        format="fdisbull-doom-tight-poll-bda-timing-comparison-2",
        scope=("One source-bound Doom E1M1 window per engine from the common "
               "post-settle pre-increment leveltime. DOSBox-X uses a recorded "
               "operation-wait poll; compare actual engine-local elapsed "
               "windows, BDA deltas and Doom leveltime deltas."),
        source_sha256=PINS["DOOM.EXE"],
        private_input_sha256=PINS,
        native_runtime_sha256=dict(
            dosbox=dosbox_result["runtime_sha256"],
            qemu=qemu_result["runtime_sha256"]),
        start=dict(kind="pre-increment Doom leveltime", tic=dosbox_result["start_tic"],
                   requested_target_tic=target_start_tic,
                   dosbox_post_settle_target_acquisition=(
                       dosbox_result["post_settle_target_acquisition"])),
        requested_guest_ms=BUDGET_MS,
        engines=dict(dosbox=dosbox_result, qemu=qemu_result),
        observed_window_comparison=dict(
            dosbox_pic_ms=dosbox_elapsed_ms,
            qemu_virtual_ms=qemu_elapsed_ms,
            dosbox_minus_qemu_ms=dosbox_elapsed_ms - qemu_elapsed_ms,
            qemu_clock_domain="QEMU_CLOCK_VIRTUAL nanoseconds",
            dosbox_clock_domain="DOSBox-X PIC guest milliseconds",
            common_clock_claim="none"),
        observed_counter_comparison=dict(
            dosbox_doom_tics=dosbox_result["leveltime_delta"],
            qemu_doom_tics=qemu_result["leveltime_delta"],
            dosbox_minus_qemu_tics=tic_delta_difference,
            dosbox_bda_ticks=dosbox_result["bda"]["delta"],
            qemu_bda_ticks=qemu_result["bda"]["delta"],
            dosbox_minus_qemu_bda_ticks=(dosbox_result["bda"]["delta"]
                                         - qemu_result["bda"]["delta"]),
            classification=classification),
        endpoint_uncertainty=dict(
            dosbox=dict(atomic=False, poll_wait_ms=poll_wait_ms,
                        observed_overshoot_ms=dosbox_result["guest_time_budget"]["overshoot"],
                        maximum_accepted_overshoot_ms=max_overshoot_ms,
                        description=("The threshold is observed by RPC polling and then "
                                     "paused; pause/RPC latency is included in elapsed time, "
                                     "and no atomic endpoint is claimed.")),
            qemu=dict(atomic=False,
                      observed_timer_overshoot_ns=qemu_result["guest_time_budget"]["overshoot"],
                      description=("Native virtual timer requests the stop; the recorded "
                                   "clock interval and stop receipt remain the authority.")),
            bda=dict(tick_period_ns=54_925_493,
                     uncertainty=("Independent BDA start/end phases contribute endpoint "
                                  "quantization; raw counts are retained without mapping "
                                  "them to a shared clock."))),
        interpretation_limitations=[
            "A three-tic difference must be interpreted with the recorded DOSBox-X overshoot and poll frequency; one interval does not establish general timing parity or failure.",
            "When FDISBULL_DOOM_TIMING_START_TIC is set, DOSBox-X reaches that pre-increment source site after ordinary-speed settling; acquisition tics and PIC elapsed time are recorded outside the measured window.",
            "A reduced or absent difference is consistent with the earlier command overshoot explaining the observed +3; one interval does not calibrate a timing rate.",
            "The engine clocks are separate domains, and BDA tick phase is not calibrated.",
            "No audio was captured; no audio-frame timing or delivery claim is made.",
            "Private media, project databases, screenshots, audio and VM states remain outside Git.",
        ])
    (tmp_path / "paired-tight-poll-bda-timing.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
