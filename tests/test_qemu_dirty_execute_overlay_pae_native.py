"""Guest writes to an active execute overlay on dirty high physical RAM."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.le_dirty_overlay_bochs import run as bochs_phase
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from support.le_remap_qemu import qemu_dos_options
from test_qemu_dos_process_native import process_runtime as process_runtime


MODES = ("pae-4k-high", "pae-2m-high", "pse36-4m-high")


@pytest.mark.parametrize("paging_mode", MODES)
def test_dirty_high_page_guest_overlay_write_stops_before_sentinel(
    tmp_path, process_runtime, paging_mode
):
    """Run both stores in one native call so no host read separates them."""
    if not os.environ.get("FDISBULL_QEMU_IMG"):
        pytest.skip("Select QEMU machine checkpoint tooling")
    if not os.environ.get("FDISBULL_BOCHS"):
        pytest.skip("Select the independent Bochs debugger")

    (tmp_path / "build").mkdir()
    fixture = build_paged_ldt_fixture(
        tmp_path / "build", str(process_runtime["nasm"]), tracking=True,
        paging_mode=paging_mode, dirty_overlay_writes=True,
    )
    source = tmp_path / "game" / "REMAP.EXE"
    source.parent.mkdir()
    source.write_bytes(fixture["path"].read_bytes())
    prepare_dos_baseline(
        process_runtime["boot_image"], tmp_path / "boot.img",
        process_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG,
    )
    offsets = fixture["dirty_write_offsets"]
    cfg = dict(source=str(source), sha256=fixture["sha256"],
               paging_mode=paging_mode, high_physical=True,
               low_alias_marker="0f0b", dirty_write_offsets=offsets)
    (tmp_path / "config.json").write_text(json.dumps(cfg, indent=2))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["sha256"]

    options = qemu_dos_options(tmp_path, cfg)
    bochs_before = bochs_phase(tmp_path, "before")
    database = tmp_path / "dirty-overlay.fdb"

    def run_stores(debug):
        fallback = debug.breakpoint(offsets["sentinel_store"] + 7)["breakpoint_id"]
        # One uninterrupted guest run performs sibling, watched and sentinel
        # stores in order; the debugger does not inspect between those writes.
        result = debug.run(timeout_ms=10000)
        assert result["outcome"] == "stopped", result
        assert result["layer_conflict"]["fault"] == "guest self-modified an execution-layer backing byte"
        assert int(result["registers"]["linear_pc"], 16) == offsets["sentinel_store"]
        assert result["session"]["stop_reason"]["breakpoint_ids"] == []
        assert debug.memory(offsets["unrelated"], length=1, space="virtual")["hex"] == "a5"
        assert debug.memory(offsets["watched"], length=1, space="virtual")["hex"] == "5a"
        assert debug.memory(offsets["sentinel"], length=1, space="virtual")["hex"] == "90"
        native_reader = debug.vm.debugger()
        final = bochs_before["observations"][2]
        qemu_values = {}
        for name, expected in (("unrelated", "a5"), ("watched", "5a"), ("sentinel", "90")):
            physical = final["values"][name]["physical"]
            observed = native_reader.memory(physical, 1, space="physical").hex()
            assert observed == expected
            qemu_values[name] = dict(linear=offsets[name], physical=physical, hex=observed)
        watched_physical = final["values"]["watched"]["physical"]
        assert native_reader.memory(watched_physical & 0xffffffff, 1, space="physical") == b"\x90"
        result["ram_values"] = qemu_values
        with pytest.raises(DebuggerError, match="layer.*faulted"):
            debug.run(timeout_ms=100)
        # The only breakpoint is past the sentinel. Clearing the fault lets
        # the guest run the deferred instruction and reach that breakpoint.
        debug.layers([])
        continuation = debug.run(timeout_ms=10000)
        assert continuation["outcome"] == "breakpoint", continuation
        assert continuation["session"]["stop_reason"]["breakpoint_ids"] == [fallback]
        assert debug.memory(offsets["sentinel"], length=1, space="virtual")["hex"] == "cc"
        debug.delete_breakpoint(fallback)
        return result

    with Project.create(database, source, image="mz") as project:
        with project.debugger(str(process_runtime["executable"]), source.parent, **options) as debug:
            point = debug.breakpoint(fixture["entry_address"])["breakpoint_id"]
            stopped = debug.run(timeout_ms=30000)
            assert stopped["outcome"] == "breakpoint", stopped
            debug.delete_breakpoint(point)
            registers = debug.registers()
            control = registers["address_state"]["control"]
            cr0, cr4 = int(control["CR0"], 16), int(control["CR4"], 16)
            assert cr0 & 0x80000001 == 0x80000001
            if paging_mode == "pse36-4m-high":
                assert cr4 & 0x10 and not cr4 & 0x20
            else:
                assert cr4 & 0x20
            checkpoint_context = {"cr0": cr0, "cr3": int(control["CR3"], 16), "cr4": cr4,
                                  "linear_pc": int(registers["linear_pc"], 16)}
            base = debug.memory(offsets["watched"], length=1, space="virtual")
            assert base["hex"] == "90"
            layer = debug.layer_patch(
                "Dirty high-page write watch", hex(offsets["watched"]),
                space="linear", kind="execute", expected_hex="90", data_hex="cc",
            )
            assert debug.layers()["active"] == [layer["layer"]]
            target_physical = bochs_before["observations"][0]["values"]["watched"]["physical"]
            spans = layer["native_binding"]["spans"]
            assert spans == [(target_physical, 1)] or spans == [[target_physical, 1]]
            checkpoint = debug.save_machine_state()["artifact"]
            hot = run_stores(debug)

        # A separate native owner restores directly to the pristine entry PC;
        # it performs no guest setup and its watched subpage is unprimed.
        with project.debugger(str(process_runtime["executable"]), source.parent, **options) as receiver:
            initial = receiver.registers()
            assert initial["cpu_mode"] == "real"
            initial_control = initial["address_state"]["control"]
            assert int(initial_control["CR0"], 16) & 0x80000000 == 0
            assert int(initial_control["CR4"], 16) & 0x30 == 0
            restored = receiver.load_machine_state(checkpoint, timeout_ms=60000)
            assert restored["machine_state_restored"]
            assert not restored["protected_source_rebound"]
            layer_map = restored["controls"]["layers"]
            restored_layer = layer_map[layer["layer"]]
            assert restored_layer != layer["layer"]
            assert receiver.layers()["active"] == [restored_layer]
            restored_regs = receiver.registers()
            restored_control = restored_regs["address_state"]["control"]
            assert int(restored_control["CR0"], 16) == checkpoint_context["cr0"]
            assert int(restored_control["CR3"], 16) == checkpoint_context["cr3"]
            assert int(restored_control["CR4"], 16) == checkpoint_context["cr4"]
            assert int(restored_regs["linear_pc"], 16) == checkpoint_context["linear_pc"] == offsets["unrelated_store"]
            cold = run_stores(receiver)

    bochs_after = bochs_phase(tmp_path, "after")
    assert bochs_after["restore_before_guest_execution"]
    assert bochs_after["observations"] == bochs_before["observations"]
    reference_stop = bochs_before["observations"][2]
    assert reference_stop["pc"] == offsets["sentinel_store"]
    assert int(hot["registers"]["linear_pc"], 16) == int(cold["registers"]["linear_pc"], 16)
    assert hot["layer_conflict"]["fault"] == cold["layer_conflict"]["fault"] == "guest self-modified an execution-layer backing byte"
    assert int(hot["registers"]["linear_pc"], 16) == reference_stop["pc"]
    for qemu in (hot, cold):
        qemu_values = qemu["ram_values"]
        for name, qemu_value in qemu_values.items():
            reference_value = reference_stop["values"][name]
            assert qemu_value == {key: reference_value[key] for key in ("linear", "physical", "hex")}
    for phase, result in (("before", hot), ("after", cold)):
        (tmp_path / f"dirty-qemu-{phase}.json").write_text(json.dumps({
            "phase": phase, "checkpoint": checkpoint,
            "source_sha256": fixture["sha256"], "paging_mode": paging_mode,
            "dirty_write_offsets": offsets, "result": result,
        }, indent=2) + "\n")
