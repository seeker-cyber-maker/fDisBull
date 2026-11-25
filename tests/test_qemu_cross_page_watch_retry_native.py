"""Preflight a later-page watchpoint before invalidating an earlier overlay."""

import json
import os
import hashlib

import pytest

from fdisbull.project import Project
from fdisbull.qemu_le_translation import QEMU_TCG_CMPXCHG16B_IMAGE
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.le_dirty_overlay_bochs import run as bochs_phase
from support.le_remap_qemu import qemu_dos_options
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from test_qemu_dos_process_native import process_runtime as process_runtime
from test_qemu_layers_native import _stop_at


def test_cross_page_watchpoint_keeps_overlay_until_store_commits(tmp_path, process_runtime):
    if not all(os.environ.get(k) for k in ("FDISBULL_BOCHS", "FDISBULL_QEMU_IMG")):
        pytest.skip("Select independent Bochs and QEMU checkpoint tooling")
    native_image_sha256 = hashlib.sha256(process_runtime["executable"].read_bytes()).hexdigest()
    assert native_image_sha256 == QEMU_TCG_CMPXCHG16B_IMAGE
    (tmp_path / "build").mkdir()
    fixture = build_paged_ldt_fixture(
        tmp_path / "build", process_runtime["nasm"], paging_mode="pae-4k-high",
        tracking=True, dirty_overlay_writes=True, dirty_overlay_atomic_batch=True)
    source = tmp_path / "game" / "REMAP.EXE"
    source.parent.mkdir()
    source.write_bytes(fixture["path"].read_bytes())
    prepare_dos_baseline(process_runtime["boot_image"], tmp_path / "boot.img",
                         process_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG)
    offsets = fixture["dirty_write_offsets"]
    cfg = dict(source=str(source), sha256=fixture["sha256"], paging_mode="pae-4k-high",
               high_physical=True, low_alias_marker="0f0b", dirty_write_offsets=offsets)
    (tmp_path / "config.json").write_text(json.dumps(cfg, indent=2))
    before = bochs_phase(tmp_path, "before")
    reference = before["observations"]["steps"]["split_store"]

    def commit(debug):
        result = debug.run(timeout_ms=10000)
        assert result["outcome"] == "stopped", result
        assert result["layer_conflict"]["fault"] == "guest self-modified an execution-layer backing byte"
        assert int(result["registers"]["linear_pc"], 16) == offsets["split_store"] + 10
        word = debug.memory(offsets["split_target"], length=4, space="virtual")["hex"]
        sentinel = debug.memory(offsets["sentinel"], length=1, space="virtual")["hex"]
        assert word == reference["split"] == "d4c3b2a1"
        assert sentinel == reference["sentinel"] == "90"
        return dict(pc=int(result["registers"]["linear_pc"], 16), word=word, sentinel=sentinel)

    options = qemu_dos_options(tmp_path, cfg)
    with Project.create(tmp_path / "watch.fdb", source, image="mz") as project:
        with project.debugger(str(process_runtime["executable"]), source.parent, **options) as debug:
            _stop_at(debug, offsets["split_store"])
            assert debug.memory(offsets["split_target"], length=4, space="virtual")["hex"] == "44332211"
            layer = debug.layer_patch("Earlier-page overlay", hex(offsets["split_target"]),
                                      space="linear", kind="execute", expected_hex="44", data_hex="cc")
            debug.breakpoint(offsets["split_target"] + 3, access="w", length=1)
            checkpoint = debug.save_machine_state()["artifact"]
            hot = commit(debug)
        with project.debugger(str(process_runtime["executable"]), source.parent, **options) as debug:
            initial = debug.registers()
            assert initial["cpu_mode"] == "real" and not initial["address_state"]["paging"]
            assert int(initial["address_state"]["control"]["CR4"], 16) & 0x30 == 0
            restored = debug.load_machine_state(checkpoint, timeout_ms=60000)
            assert restored["machine_state_restored"]
            active = restored["controls"]["layers"][layer["layer"]]
            assert debug.layers()["active"] == [active]
            cold = commit(debug)
    after = bochs_phase(tmp_path, "after")
    assert after["restore_before_guest_execution"] and before["pid"] != after["pid"]
    assert before["observations"] == after["observations"]
    assert hot == cold
    (tmp_path / "watch-retry-result.json").write_text(json.dumps(dict(
        checkpoint=checkpoint, native_image_sha256=native_image_sha256,
        bochs_live=before, bochs_cold=after, qemu_live=hot, qemu_cold=cold),
        indent=2) + "\n")
