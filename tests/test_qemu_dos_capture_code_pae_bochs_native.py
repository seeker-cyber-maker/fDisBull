"""One-shot QEMU paged capture parity against independent Bochs checkpoints."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from support.le_remap_bochs import verify_saved_high_checkpoint
from support.le_translation_native import integer
from test_qemu_dos_process_native import (
    process_runtime as process_runtime,  # noqa: PLC0414 - expose shared fixture
)
from test_qemu_le_remap_tracking_native import phases, prepare


MODES = (
    ("pae-4k-high", 0x1000),
    ("pae-2m-high", 0x200000),
    ("pse36-4m-high", 0x400000),
)


def _entry_path(payload):
    row = next(
        item
        for item in payload["paged_le_capture"]["linear_walks"]
        if item["address"] == int(payload["runtime_address"], 16)
    )
    return row["walks"][0]["entries"]


def capture_phases(stage):
    helper = Path(__file__).parent / "support" / "le_remap_capture_qemu.py"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in sys.path if p)}
    for phase in ("before", "after"):
        subprocess.run(
            [sys.executable, str(helper), str(stage), phase],
            env=env,
            check=True,
            timeout=300,
        )
    return [
        json.loads((Path(stage) / f"qemu-capture-{phase}.json").read_text())
        for phase in ("before", "after")
    ]


@pytest.mark.parametrize(("paging_mode", "expected_page_size"), MODES)
def test_one_shot_capture_code_matches_bochs_saved_high_checkpoint(
    tmp_path, process_runtime, paging_mode, expected_page_size
):
    if not all(
        os.environ.get(name)
        for name in ("FDISBULL_BOCHS", "FDISBULL_QEMU_DOS", "FDISBULL_QEMU_IMG")
    ):
        pytest.skip("Select independent Bochs and QEMU machine checkpoint profiles")
    assert Path(os.environ["FDISBULL_BOCHS"]).resolve() != Path(
        os.environ["FDISBULL_QEMU_DOS"]
    ).resolve()

    cfg = prepare(tmp_path, process_runtime, paging_mode)
    cfg["boundaries"] = cfg["checkpoint_index"] + 1
    (tmp_path / "config.json").write_text(json.dumps(cfg, indent=2))
    source = Path(cfg["source"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == cfg["sha256"]

    # Bochs saves and independently observes the boundary before QEMU captures.
    bochs, bochs_cold = phases(tmp_path, "bochs", timeout=300)
    before, after = capture_phases(tmp_path)
    assert len(bochs["events"]) == cfg["checkpoint_index"] + 1
    assert len(bochs_cold["events"]) == 1
    assert before["checkpoint"] == after["checkpoint"]
    verify_saved_high_checkpoint(tmp_path, cfg, bochs, bochs_cold, captures=(before, after))
    expected = bochs["events"][cfg["checkpoint_index"]]
    restored = bochs_cold["events"][0]
    assert expected == restored

    for result in (before, after):
        assert result["source_sha256"] == cfg["sha256"]
        assert result["target_pc"] == expected["pc"]
        regs = result["stopped_registers"]
        assert int(regs["registers"]["cs"], 16) == expected["cs"]
        assert int(regs["instruction_pointer"], 16) == expected["ip"]
        fresh = result["fresh_process_registers"]
        assert fresh["cpu_mode"] == "real"
        assert fresh["address_state"]["paging"] is False
        assert integer(fresh["address_state"]["control"]["CR4"]) & 0x30 == 0
        assert set(result["artifacts"]) == {"execute", "ram"}
        assert result["restored_in_fresh_process"] is (result is after)
        expected_alias_reads = [
            {"address": address, "high": "46cb", "low": "0f0b"}
            for address in (cfg["first_target"], cfg["second_target"])
        ]
        assert result["alias_reads"] == expected_alias_reads
        for view in ("execute", "ram"):
            payload = result["payloads"][view]
            analysis = result["analyses"][view]
            assert payload["space"] == "linear" and payload["view"] == view
            assert payload["length"] == 15
            assert payload["qemu_paged_le_source_admission"] == "paged-le-stopped-capture-v1"
            assert result["capture_metadata"][view]["offline_analysis"] == (
                "qualified-paged-le-source-capture"
            )
            assert payload["execution_proven"] is False
            assert payload["identity"]["source_sha256"] == cfg["sha256"]
            assert analysis["source_sha256"] == cfg["sha256"]
            assert analysis["execution_proven"] is False
            assert analysis["artifact"] == result["artifacts"][view]
            assert result["export_receipts"][view]["artifact"] == result["artifacts"][view]
            assert analysis["source_location"]["object_index"] == 1
            assert analysis["source_location"]["object_offset"] == expected["ip"]
            assert analysis["selector"]["cs"] == expected["cs"]
            assert int(analysis["stopped_pc"]["linear"], 16) == expected["pc"]
            assert payload["paged_le_capture"]["linear_walks"]

            q_entries = _entry_path(payload)
            b_entries = expected["walks"][0]
            raw_reads = {
                (row["address"], row["length"]): row["hex"]
                for row in payload["paged_le_capture"]["physical_reads"]
            }
            aliases = {"pdpt": "pdpte", "directory": "pde", "table": "pte"}
            assert [(aliases.get(row["kind"], row["kind"]), row["physical_address"])
                    for row in q_entries] == [(row["level"], row["address"]) for row in b_entries]
            for q_entry, b_entry in zip(q_entries, b_entries, strict=True):
                entry_width = 4 if paging_mode == "pse36-4m-high" else 8
                # qemu_le_translation records the actual physical read for
                # each page-table entry; the retained raw entry must be that read.
                assert q_entry["raw"] == raw_reads[(q_entry["physical_address"], entry_width)]
                if q_entry["value"] != b_entry["value"]:
                    assert q_entry["kind"] == "pdpt"
                    assert q_entry.get("qemu_tcg_accessed") is True
                    assert not b_entry["value"] & 0x20
                    assert q_entry["value"] == b_entry["value"] | 0x20
                else:
                    assert q_entry["value"] == b_entry["value"]

            segments = analysis["address_translation"]["instruction_segments"]
            physical = [
                segment["physical"] + offset
                for segment in segments
                for offset in range(segment["length"])
            ]
            assert physical == expected["backing"]
            captured_span = [
                int(row["physical_address"], 16) + offset
                for row in payload["backing"]
                for offset in range(row["length"])
            ]
            assert captured_span[: len(expected["backing"])] == expected["backing"]
            assert analysis["runtime_bytes"] == expected["hex"]
            assert payload["hex"][: len(expected["hex"])] == expected["hex"]
            capture_walks = [
                row
                for row in payload["paged_le_capture"]["linear_walks"]
                if row["address"] == int(payload["runtime_address"], 16)
                and row["length"] == payload["length"]
            ]
            assert len(capture_walks) == 1
            for walk in capture_walks:
                assert walk["walks"]
                for page in walk["walks"]:
                    assert page["page_size"] == expected_page_size

    for result in (bochs, bochs_cold):
        assert result["max_native_mmu_physical"] > 0xFFFFFFFF
        assert set(result["low_alias_markers"].values()) == {"0f0b"}
    for result in (before, after):
        backed = [
            segment["physical"]
            for segment in result["analyses"]["execute"]["address_translation"]["instruction_segments"]
        ]
        assert any(address > 0xFFFFFFFF for address in backed)
        assert all(address & 0xFFFFFFFF in cfg["low_aliases"] for address in backed)

    assert hashlib.sha256(Path(cfg["source"]).read_bytes()).hexdigest() == cfg["sha256"]
