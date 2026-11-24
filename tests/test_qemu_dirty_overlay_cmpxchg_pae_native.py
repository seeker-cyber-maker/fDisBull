"""Paired native CMPXCHG witnesses on high-backed execute overlays."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.le_dirty_overlay_bochs import run as bochs_phase
from support.le_remap_qemu import qemu_dos_options
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from test_qemu_dos_process_native import process_runtime as process_runtime


MODES = ("pae-4k-high", "pae-2m-high", "pse36-4m-high")
ARITHMETIC_FLAGS = 0x8D5
LAYER_FAULT = "guest self-modified an execution-layer backing byte"


def _observe_store(debug, offsets, before_pc, physical):
    stop = debug.run(timeout_ms=10000)
    assert stop["outcome"] == "stopped", stop
    assert stop["layer_conflict"]["fault"] == LAYER_FAULT, stop
    assert stop["layer_conflict"]["execution-bytes"] == 0
    assert stop["session"]["stop_reason"]["breakpoint_ids"] == []
    pc = int(stop["registers"]["linear_pc"], 16)
    assert pc == before_pc + (8 if offsets["cmpxchg_lock"] else 7)
    registers = stop["registers"]["registers"]
    flags = int(next(registers[k] for k in ("eflags", "rflags") if k in registers), 16)
    assert flags & 0x40
    ram = debug.vm.debugger()
    assert ram.memory(physical, 1, space="physical") == b"\x5a"
    assert ram.memory(physical & 0xFFFFFFFF, 1, space="physical") == b"\x90"
    assert debug.memory(offsets["unrelated"], length=1, space="virtual")["hex"] == "a5"
    sentinel = debug.memory(offsets["sentinel"], length=1, space="virtual")["hex"]
    assert sentinel == "90"
    with pytest.raises(DebuggerError, match="layer.*faulted"):
        debug.run(timeout_ms=100)
    return {"pc": pc, "ram": "5a", "sentinel": sentinel}, flags & ARITHMETIC_FLAGS


def _run(debug, offsets, physical):
    fallback = debug.breakpoint(offsets["sentinel_store"] + 7)["breakpoint_id"]
    # The sibling store, failed compare, and changed-value success execute in
    # one call. The guest records the mismatch before changing RAM.
    changed, changed_flags = _observe_store(debug, offsets, offsets["cmp_succeeded"], physical)
    failed_al = debug.memory(offsets["cmp_result_al"], length=1, space="virtual")["hex"]
    failed_ram = debug.memory(offsets["cmp_result_ram"], length=1, space="virtual")["hex"]
    assert failed_al == failed_ram == "90"

    # Rebind to the value written by the first match. The second match writes
    # the existing value and must still report an overlap.
    debug.layers([])
    debug.layer_patch("Same-value CMPXCHG backing", hex(offsets["watched"]), space="linear",
                      kind="execute", expected_hex="5a", data_hex="cc")
    same, same_flags = _observe_store(debug, offsets, offsets["cmp_same"], physical)
    debug.layers([])
    continuation = debug.run(timeout_ms=10000)
    assert continuation["outcome"] == "breakpoint", continuation
    assert continuation["session"]["stop_reason"]["breakpoint_ids"] == [fallback]
    assert debug.memory(offsets["sentinel"], length=1, space="virtual")["hex"] == "cc"
    raw_flags = bytes.fromhex(
        debug.memory(offsets["cmp_result_flags"], length=12, space="virtual")["hex"]
    )
    flags = [int.from_bytes(raw_flags[i:i + 4], "little") & ARITHMETIC_FLAGS for i in (0, 4, 8)]
    assert flags[0] & 0x40 == 0
    assert flags[1:] == [changed_flags, same_flags]
    return dict(changed=changed, same=same, failed_al=int(failed_al, 16),
                failed_ram=int(failed_ram, 16), flags=flags)


@pytest.mark.parametrize("paging_mode", MODES)
@pytest.mark.parametrize("locked", (False, True), ids=("plain", "lock"))
def test_dirty_high_execute_overlay_cmpxchg_live_and_unprimed_cold(
    tmp_path, process_runtime, paging_mode, locked
):
    if not all(os.environ.get(name) for name in ("FDISBULL_QEMU_IMG", "FDISBULL_BOCHS")):
        pytest.skip("Select QEMU machine checkpoints and the independent Bochs debugger")
    (tmp_path / "build").mkdir()
    fixture = build_paged_ldt_fixture(
        tmp_path / "build", str(process_runtime["nasm"]), tracking=True,
        paging_mode=paging_mode, dirty_overlay_writes=True,
        dirty_overlay_cmpxchg=True, cmpxchg_lock=locked,
    )
    source = tmp_path / "game" / "REMAP.EXE"
    source.parent.mkdir()
    source.write_bytes(fixture["path"].read_bytes())
    prepare_dos_baseline(process_runtime["boot_image"], tmp_path / "boot.img",
                         process_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG)
    offsets = fixture["dirty_write_offsets"]
    cfg = dict(source=str(source), sha256=fixture["sha256"], paging_mode=paging_mode,
               high_physical=True, low_alias_marker="0f0b", dirty_write_offsets=offsets)
    (tmp_path / "config.json").write_text(json.dumps(cfg, indent=2))
    options = qemu_dos_options(tmp_path, cfg)
    before = bochs_phase(tmp_path, "before")
    reference = before["observations"]
    physical = reference["final"]["values"]["watched"]["physical"]
    assert physical > 0xFFFFFFFF
    database = tmp_path / "cmpxchg-overlay.fdb"
    owners = []
    executable = str(process_runtime["executable"])
    with Project.create(database, source, image="mz") as project:
        with project.debugger(executable, source.parent, _on_spawn=owners.append, **options) as debug:
            entry = debug.breakpoint(fixture["entry_address"])["breakpoint_id"]
            stopped = debug.run(timeout_ms=30000)
            assert stopped["outcome"] == "breakpoint", stopped
            debug.delete_breakpoint(entry)
            registers = debug.registers()
            layer = debug.layer_patch("CMPXCHG backing watch", hex(offsets["watched"]),
                                      space="linear", kind="execute", expected_hex="90", data_hex="cc")
            assert debug.layers()["active"] == [layer["layer"]]
            assert [tuple(span) for span in layer["native_binding"]["spans"]] == [(physical, 1)]
            checkpoint = debug.save_machine_state()["artifact"]
            hot = _run(debug, offsets, physical)
        with project.debugger(executable, source.parent, _on_spawn=owners.append, **options) as debug:
            initial = debug.registers()
            assert initial["cpu_mode"] == "real" and initial["address_state"]["paging"] is False
            control = initial["address_state"]["control"]
            assert int(control["CR0"], 16) & 0x80000000 == 0
            assert int(control["CR4"], 16) & 0x30 == 0
            restored = debug.load_machine_state(checkpoint, timeout_ms=60000)
            assert restored["machine_state_restored"] and not restored["protected_source_rebound"]
            restored_layer = restored["controls"]["layers"][layer["layer"]]
            assert restored_layer != layer["layer"]
            assert debug.layers()["active"] == [restored_layer]
            recovered = debug.registers()
            assert recovered["linear_pc"] == registers["linear_pc"]
            assert recovered["address_state"]["control"] == registers["address_state"]["control"]
            cold = _run(debug, offsets, physical)
    assert len(owners) == 2 and owners[0] is not owners[1]

    after = bochs_phase(tmp_path, "after")
    assert after["restore_before_guest_execution"] and before["pid"] != after["pid"]
    assert reference == after["observations"]
    assert hot == cold == {
        "changed": reference["steps"]["changed"], "same": reference["steps"]["same"],
        "failed_al": reference["failed_al"], "failed_ram": reference["failed_ram"],
        "flags": [flags & ARITHMETIC_FLAGS for flags in reference["flags"]],
    }
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg["sha256"]
    (tmp_path / "cmpxchg-native-result.json").write_text(json.dumps({
        "mode": paging_mode, "locked": locked, "checkpoint": checkpoint,
        "physical": physical, "bochs_live": before, "bochs_cold": after,
        "qemu_live": hot, "qemu_cold": cold,
        "source_sha256": cfg["sha256"],
    }, indent=2) + "\n")
