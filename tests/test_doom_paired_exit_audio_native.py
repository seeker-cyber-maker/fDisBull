"""Opt-in paired Doom pistol audio capture through normal DOS guest exit.

Runs the established QEMU and DOSBox-X native witnesses against the same
pinned original Doom E1M1 inputs. It compares bounded outcomes and each
engine's finite capture evidence; it makes no PCM waveform or onset parity
claim. Private guest media, WAV files, VM state, and receipts stay in pytest's
temporary directory outside the checkout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from support.doom_le_qemu import PINS
from test_doom_dosbox_quit_capture_native import _run_dosbox
from test_doom_pistol_sfx_paired_native import _read_dspistol, _sha, CORRELATION_THRESHOLD
from test_doom_qemu_pistol_guest_exit_native import (
    test_qemu_doom_e1m1_pistol_endpoint_then_normal_guest_exit as _run_qemu_witness,
)


def test_paired_doom_pistol_audio_then_normal_guest_exit(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_PAIRED_EXIT_AUDIO") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_PAIRED_EXIT_AUDIO=1 for paired private Doom inputs and runtimes")

    required = (
        "FDISBULL_DOOM_LE_SOURCE", "FDISBULL_DOSBOX",
        "FDISBULL_QEMU_DOS", "FDISBULL_QEMU_DOS_BOOT_IMAGE",
        "FDISBULL_QEMU_DOS_MCOPY", "FDISBULL_QEMU_IMG",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        pytest.fail("Paired native Doom inputs/runtimes missing: " + ", ".join(missing))

    checkout = Path(__file__).resolve().parents[1]
    output = Path(tmp_path).resolve(strict=True)
    try:
        output.relative_to(checkout)
    except ValueError:
        pass
    else:
        pytest.fail("Private Doom databases, captures, VM states, and receipts must stay outside the checkout")

    source = Path(os.environ["FDISBULL_DOOM_LE_SOURCE"]).expanduser().resolve(strict=True)
    assert {name: _sha(source / name) for name in PINS} == PINS
    reference, reference_rate = _read_dspistol(source / "DOOM.WAD")

    # Reuse the established QEMU proof, including its own opt-in guard and
    # owner-reap assertions, then consume only its sanitized JSON receipt.
    qemu_root = output / "qemu"
    qemu_root.mkdir()
    qemu_gate = "FDISBULL_REQUIRE_DOOM_QEMU_PISTOL_EXIT"
    prior_qemu_gate = os.environ.get(qemu_gate)
    os.environ[qemu_gate] = "1"
    try:
        _run_qemu_witness(qemu_root)
    finally:
        if prior_qemu_gate is None:
            os.environ.pop(qemu_gate, None)
        else:
            os.environ[qemu_gate] = prior_qemu_gate
    qemu_receipt_path = qemu_root / "qemu-doom-pistol-guest-exit.json"
    qemu = json.loads(qemu_receipt_path.read_text())
    assert qemu["source_pins"] == PINS
    assert qemu["endpoint"]["start_tic"] == 64
    assert qemu["endpoint"]["control_end_tic"] == 84
    assert qemu["endpoint"]["shot_end_tic"] == 114
    assert qemu["gameplay"]["ammo_before"] == 50
    assert qemu["gameplay"]["ammo_after"] == 49
    assert qemu["gameplay"]["shot_audio"]["correlation"]["score"] >= CORRELATION_THRESHOLD
    assert qemu["gameplay"]["shot_audio"]["frames"] > 0
    assert qemu["gameplay"]["shot_audio"]["dropped_frames"] == 0
    termination = qemu["guest_exit"]["process"]["termination"]
    assert termination["type"] == "normal" and termination["code"] == 0
    assert termination["resident"] is False
    assert qemu["guest_exit"]["qemu_alive_at_guest_return"] is True
    assert qemu["config_changes"]["owner_returncodes"]
    assert all(code == 0 for code in qemu["config_changes"]["owner_returncodes"])

    # The paired wrapper is the sole opt-in. Mirror the private environment
    # contract of the standalone DOSBox-X test without invoking a pytest
    # fixture from Python code.
    dosbox = Path(os.environ["FDISBULL_DOSBOX"]).expanduser().resolve(strict=True)
    assert dosbox.is_file() and os.access(dosbox, os.X_OK)
    dosbox_runtime = dict(source=source, dosbox=dosbox, source_sha256=PINS,
                          dosbox_sha256=_sha(dosbox))
    dosbox_result = _run_dosbox(output / "dosbox", dosbox_runtime, reference, reference_rate)
    assert dosbox_result["source_sha256"] == PINS
    assert dosbox_result["leveltime"]["start"] == 64
    assert dosbox_result["leveltime"]["control_end"] == 84
    assert dosbox_result["leveltime"]["shot_end"] == 114
    assert dosbox_result["shot"]["ammo_before"] == 50
    assert dosbox_result["shot"]["ammo_after"] == 49
    assert dosbox_result["shot"]["dspistol_correlation"]["score"] >= CORRELATION_THRESHOLD
    assert dosbox_result["quit"]["exit"]["kind"] == "guest_exit"
    assert dosbox_result["quit"]["exit"]["requested_exit_code"] == 0
    assert dosbox_result["quit"]["exit"]["resident"] is False
    assert dosbox_result["audio"]["header_finalized"] is True
    assert dosbox_result["audio"]["riff_bytes"] == dosbox_result["audio"]["riff_declared_bytes"]
    assert dosbox_result["owner_cleanup"] == {"reaped": True, "returncode": 0}
    assert {name: _sha(source / name) for name in PINS} == PINS

    paired = {
        "format": "fdisbull-doom-paired-exit-audio-1",
        "scope": "paired source-bound pistol outcome and normal nonresident guest exits; finite engine capture only",
        "source_pins": PINS,
        "landmarks": {"start_tic": 64, "control_end_tic": 84, "shot_end_tic": 114},
        "outcomes": {
            "qemu": {"ammo": [qemu["gameplay"]["ammo_before"], qemu["gameplay"]["ammo_after"]],
                     "guest_exit": qemu["guest_exit"]["process"]["termination"],
                     "capture_frontier": {"unit": "captured_pcm_frames", "frames": qemu["gameplay"]["shot_audio"]["frames"],
                                          "dropped_frames": qemu["gameplay"]["shot_audio"]["dropped_frames"]},
                     "owner_returncodes": qemu["config_changes"]["owner_returncodes"]},
            "dosbox_x": {"ammo": [dosbox_result["shot"]["ammo_before"], dosbox_result["shot"]["ammo_after"]],
                         "guest_exit": dosbox_result["quit"]["exit"],
                         "capture_extent": {"unit": "finalized_RIFF_and_data_bytes",
                                            "riff_bytes": dosbox_result["audio"]["riff_bytes"],
                                            "data_bytes": dosbox_result["audio"]["data_bytes"],
                                            "frames": dosbox_result["audio"]["frames"]},
                         "owner_cleanup": dosbox_result["owner_cleanup"]},
        },
        "audio_claim_limit": "DSPISTOL is independently correlated in each engine; no PCM waveform or onset parity is claimed",
    }
    (output / "doom-paired-exit-audio.json").write_text(json.dumps(paired, sort_keys=True, indent=2) + "\n")
