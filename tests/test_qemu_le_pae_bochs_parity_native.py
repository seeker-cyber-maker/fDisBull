"""Paired QEMU/Bochs checks for PAE LE translation and cold restore."""

import hashlib
import os
from pathlib import Path

import pytest
from support.le_remap_bochs import verify_saved_high_checkpoint
from test_qemu_dos_process_native import (
    process_runtime as process_runtime,  # noqa: PLC0414 - expose the shared pytest fixture
)
from test_qemu_le_remap_tracking_native import phases, prepare

from fdisbull.le import load_runtime_le_carrier


@pytest.mark.parametrize(
    ("paging_mode", "expected_page_size"),
    [
        ("pae-4k", 0x1000),
        ("pae-2m", 0x200000),
        ("pae-4k-high", 0x1000),
        ("pae-2m-high", 0x200000),
        ("pse36-4m-high", 0x400000),
    ],
)
def test_pae_tracking_matches_independent_bochs_through_unprimed_cold_restore(
    tmp_path, process_runtime, paging_mode, expected_page_size
):
    """Require independent PAE interpretation and exact hot/cold trace parity."""
    if not all(
        os.environ.get(name)
        for name in ("FDISBULL_BOCHS", "FDISBULL_QEMU_DOS", "FDISBULL_QEMU_IMG")
    ):
        pytest.skip("Select the independent Bochs and QEMU machine checkpoint profiles")
    assert (
        Path(os.environ["FDISBULL_BOCHS"]).resolve()
        != Path(os.environ["FDISBULL_QEMU_DOS"]).resolve()
    )

    cfg = prepare(tmp_path, process_runtime, paging_mode)
    source = Path(cfg["source"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == cfg["sha256"]
    image = load_runtime_le_carrier(source)

    # Bochs is a separate executable and state database; it must not consume or
    # derive its observations from the QEMU trace.
    bochs, bochs_cold = phases(tmp_path, "bochs", timeout=300)
    qemu, qemu_cold = phases(tmp_path, "qemu")

    for hot, cold in ((bochs, bochs_cold), (qemu, qemu_cold)):
        assert len(hot["events"]) == 39
        assert len(cold["events"]) == 32
        assert hot["checkpoint"] == cold["checkpoint"]
        assert hot["events"][cfg["checkpoint_index"] :] == cold["events"]

    assert qemu["binding_id"] != qemu_cold["binding_id"]
    assert qemu["epoch"] != qemu_cold["epoch"]
    assert set(qemu["artifacts"]).isdisjoint(qemu_cold["artifacts"])
    for result in (qemu, qemu_cold):
        entry = result["pae_cpu_context"]["entry"]
        assert entry["mode"] == "real" and not entry["paging"]
        assert not entry["cr4"] & 0x20
        if paging_mode == "pse36-4m-high":
            assert not entry["cr4"] & 0x10
    checkpoint_context = qemu["pae_cpu_context"]["checkpoint"]
    assert checkpoint_context["paging"] and checkpoint_context["cr0"] & 0x80000001 == 0x80000001
    if paging_mode == "pse36-4m-high":
        assert checkpoint_context["cr4"] & 0x10 and not checkpoint_context["cr4"] & 0x20
    else:
        assert checkpoint_context["cr4"] & 0x20
    assert qemu_cold["pae_cpu_context"]["restored"] == checkpoint_context

    # The cold phases start separate engine processes and restore directly from
    # the checkpoint. In particular, the guest setup code must not run first.
    assert bochs["pid"] and bochs_cold["pid"] != bochs["pid"]
    assert bochs["owners"] == [0] and bochs_cold["owners"] == [0]
    assert bochs["binary_sha256"] == bochs_cold["binary_sha256"]
    assert bochs["media_sha256"] == bochs_cold["media_sha256"]
    high_memory = paging_mode.endswith("-high")
    if high_memory:
        verify_saved_high_checkpoint(tmp_path, cfg, bochs, bochs_cold)
        expected_reads = [
            {"address": address, "high": "46cb", "low": "0f0b"}
            for address in (cfg["first_target"], cfg["second_target"])
        ]
        assert qemu["high_alias_reads"] == qemu_cold["high_alias_reads"] == expected_reads
        for result in (bochs, bochs_cold):
            assert result["memory_topology"] == "high-ram-over-4g-sparse"
            expected_aliases = {
                str(cfg["first_target"] & 0xFFFFFFFF),
                str(cfg["second_target"] & 0xFFFFFFFF),
            }
            assert set(result["low_alias_markers"]) == expected_aliases
            assert set(result["low_alias_markers"].values()) == {"0f0b"}
            assert result["max_native_mmu_physical"] > 0xFFFFFFFF
    if paging_mode == "pse36-4m-high":
        feature_bits = (1 << 3) | (1 << 17)
        assert bochs["pse36_cpuid_edx"] == bochs_cold["pse36_cpuid_edx"]
        assert bochs["pse36_cpuid_edx"] & feature_bits == feature_bits
        assert qemu["pse36_cpuid_edx"] == qemu_cold["pse36_cpuid_edx"]
        assert qemu["pse36_cpuid_edx"] & feature_bits == feature_bits
    assert bochs["checkpoint_context"] == bochs_cold["initial_context"]
    checkpoint_clock = bochs["checkpoint_context"]["clock"]
    assert bochs["events"][cfg["checkpoint_index"]]["clock"] == checkpoint_clock
    assert bochs_cold["events"][0]["clock"] == checkpoint_clock

    for result, is_qemu in ((qemu, True), (qemu_cold, True), (bochs, False), (bochs_cold, False)):
        expected_events = len(result["events"])
        if is_qemu:
            assert sum(event["qualified"] for event in result["events"]) == expected_events - 4
            assert sum(not event["qualified"] for event in result["events"]) == 4
        else:
            assert sum(event["cs"] == 8 for event in result["events"]) == 4
        for event in result["events"]:
            qualified = event["qualified"] if is_qemu else event["cs"] != 8
            if not qualified:
                assert event["cs"] == 8 and "obj" not in event
                continue
            if is_qemu:
                assert event["page_size"] == expected_page_size
                assert event["paging_mode"] == ("legacy-32" if paging_mode == "pse36-4m-high" else "pae")
                assert event["entries"] and event["page_attributes"]
            else:
                assert event["page_size"] == expected_page_size
                assert event["paging_mode"] == ("legacy-32" if paging_mode == "pse36-4m-high" else "pae")
                assert event["paging"]
                assert event["walks"]

    for base in (0, cfg["cycle"]):
        visits = [
            e for e in qemu["events"][base : base + cfg["cycle"]] if e["ip"] == cfg["target_ip"]
        ]
        assert [(e["cs"], e["backing"][0]) for e in visits] == [
            (cfg["start_cs"], cfg["first_target"]),
            (cfg["start_cs"], cfg["second_target"]),
            (cfg["selector_b"], cfg["second_target"]),
        ]
        assert all(e["hex"] == "46" for e in visits)
        assert (
            qemu["events"][base + cfg["cycle"]]["esi"]
            == (qemu["events"][base]["esi"] + 3) & 0xFFFFFFFF
        )

    # Compare instruction identity and relative guest register progress. The
    # engines can enter the fixture with different initial ESI values.
    for qevents, bevents in (
        (qemu["events"], bochs["events"]),
        (qemu_cold["events"], bochs_cold["events"]),
    ):
        assert len(qevents) == len(bevents)
        for index, (q, b) in enumerate(zip(qevents, bevents, strict=True)):
            assert (q["cs"], q["ip"], q["pc"]) == (b["cs"], b["ip"], b["pc"]), index
            assert (q["esi"] - qevents[0]["esi"]) & 0xFFFFFFFF == (
                b["esi"] - bevents[0]["esi"]
            ) & 0xFFFFFFFF, index
            if not q["qualified"]:
                assert b["cs"] == 8 and b["paging"]
                continue
            assert b["paging"] and b["ldtr_selector"] == 0x18
            assert q["obj"] == 1 and q["offset"] == b["ip"]
            assert q["hex"] == b["hex"]
            assert q["backing"] == b["backing"]
            if high_memory:
                # This is Bochs' native MMU translation at the stopped guest
                # instruction, not a translation inferred from the page walk.
                assert any(page["physical"] > 0xFFFFFFFF for page in b["mmu_pages"]), index
                assert any(address > 0xFFFFFFFF for address in b["backing"]), index
            native_pages = {page["linear"]: page["physical"] for page in b["mmu_pages"]}
            assert native_pages
            for offset, physical in enumerate(b["backing"]):
                linear = b["pc"] + offset
                linear_page = linear & ~0xFFF
                assert physical == native_pages[linear_page] + (linear & 0xFFF)
            q_path = [
                (
                    {"pdpt": "pdpte", "directory": "pde", "table": "pte"}.get(
                        entry["kind"], entry["kind"]
                    ),
                    entry["physical_address"],
                    entry["value"],
                )
                for entry in q["entries"]
            ]
            b_path = [(entry["level"], entry["address"], entry["value"]) for entry in b["walks"][0]]
            assert [(level, address) for level, address, _ in q_path] == [
                (level, address) for level, address, _ in b_path
            ]
            for (level, _, q_value), (_, _, b_value) in zip(q_path, b_path, strict=True):
                # QEMU TCG can set bit 5 in a legacy PAE PDPTE. The fixture's
                # directory and leaf entries must agree, including A/D bits.
                if level == "pdpte" and q_value != b_value:
                    assert q["entries"][0].get("qemu_tcg_accessed") is True
                    assert not b_value & 0x20 and q_value == b_value | 0x20
                else:
                    assert q_value == b_value
            assert (q["cs_base"], q["cs_limit"]) == (b["cs_base"], b["cs_limit"])
            qdesc, bdesc = bytes.fromhex(q["descriptor"]), bytes.fromhex(b["descriptor"])
            assert qdesc[:5] == bdesc[:5] and qdesc[6:] == bdesc[6:]
            assert qdesc[5] & ~1 == bdesc[5] & ~1
            data = image.regions[0].data[q["offset"] : q["offset"] + len(q["backing"])]
            assert data.hex() == b["hex"]
            assert hashlib.sha256(data).hexdigest() == q["source_instruction_sha256"]

    assert hashlib.sha256(Path(cfg["source"]).read_bytes()).hexdigest() == cfg["sha256"]
