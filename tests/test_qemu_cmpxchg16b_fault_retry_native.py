"""Public long-mode overlay checkpoints through guest page-fault retry."""

import json
import os
import hashlib

import pytest

from fdisbull.project import Project
from fdisbull.qemu_le_translation import QEMU_TCG_CMPXCHG16B_IMAGE
from support.cmpxchg16_bochs import run as bochs_phase, snapshot
from support.cmpxchg16_fixture import build, INITIAL, CHANGED
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.le_remap_qemu import qemu_dos_options
from test_qemu_dos_process_native import process_runtime as process_runtime
from test_qemu_layers_native import _stop_at


def layer_target(cfg):
    return ((cfg["target"], "linear") if cfg["high_backing"]
            else (cfg["target_physical"], "physical"))


def observe(debug, cfg):
    reg = debug.registers()
    values = reg["registers"]
    def value(a,b):
        return int(values.get(a,values.get(b)),16)
    reader = debug.vm.debugger()
    if cfg["high_backing"]:
        assert reader.memory(cfg["low_alias"],16,space="physical").hex() == "0f0b"*8
        assert reader.memory(cfg["target"],16,space="physical").hex() == "0f0b"*8
        assert reader.memory(cfg["target"],16,space="virtual") == reader.memory(
            cfg["target_physical"],16,space="physical")
    return snapshot(lambda a,n: reader.memory(a,n,space="physical"),
        dict(pc=int(reg["linear_pc"],16),rax=value("rax","eax"),rdx=value("rdx","edx"),
             flags=value("eflags","rflags")),cfg)


def exercise(debug, cfg, layer):
    fallback = debug.breakpoint(cfg["done"])["breakpoint_id"]
    failure = debug.breakpoint(cfg["failed_after"])["breakpoint_id"]
    stop = debug.run(timeout_ms=10000)
    assert stop["outcome"] == "breakpoint", stop
    assert failure in stop["session"]["stop_reason"]["breakpoint_ids"]
    assert debug.layers()["active"] == [layer]
    assert not stop.get("layer_conflict")
    first = observe(debug,cfg)
    assert first["target"] == INITIAL and first["zf"] is False and len(first["faults"]) == 1
    debug.delete_breakpoint(failure)
    changed = debug.run(timeout_ms=10000)
    assert changed["outcome"] == "stopped", changed
    assert changed["layer_conflict"]["fault"] == "guest self-modified an execution-layer backing byte"
    second = observe(debug,cfg)
    assert second["pc"] == cfg["changed_after"] and second["target"] == CHANGED
    assert second["zf"] and len(second["faults"]) == 2 and second["sentinel"] == "90"
    debug.layers([])
    address, space = layer_target(cfg)
    debug.layer_patch("Same-value CX16",address,space=space,
                      kind="execute",expected_hex=CHANGED,data_hex="cc"*16)
    same = debug.run(timeout_ms=10000)
    assert same["outcome"] == "stopped",same
    assert same["layer_conflict"]["fault"] == "guest self-modified an execution-layer backing byte"
    third = observe(debug,cfg)
    assert third["pc"] == cfg["same_after"] and third["target"] == CHANGED
    assert third["zf"] and len(third["faults"]) == 3 and third["sentinel"] == "90"
    for key,result in zip(("cmp_failed","cmp_changed","cmp_same"),third["faults"],strict=True):
        assert result["error"] == 3 and result["address"] == cfg["target"] and result["rip"] == cfg[key]
    debug.layers([])
    continuation = debug.run(timeout_ms=10000)
    assert continuation["outcome"] == "breakpoint"
    assert fallback in continuation["session"]["stop_reason"]["breakpoint_ids"]
    assert debug.memory(cfg["sentinel"],length=1,space="physical")["hex"] == "5a"
    return dict(failed_after=first,changed_after=second,same_after=third)


@pytest.mark.parametrize("high_backing",(False,True),ids=("low","high"))
@pytest.mark.parametrize("locked",(False,True),ids=("plain","lock"))
def test_cmpxchg16b_fault_retry_and_active_overlay_cold_restore(
        tmp_path,process_runtime,locked,high_backing):
    if not all(os.environ.get(k) for k in ("FDISBULL_BOCHS","FDISBULL_QEMU_IMG")):
        pytest.skip("Select independent Bochs and QEMU checkpoint tooling")
    native_image_sha256 = hashlib.sha256(process_runtime["executable"].read_bytes()).hexdigest()
    assert native_image_sha256 == QEMU_TCG_CMPXCHG16B_IMAGE
    fixture = build(tmp_path/"game",process_runtime["nasm"],
                    locked=locked,high_backing=high_backing)
    source = fixture.pop("path")
    cfg = dict(source=str(source),high_physical=high_backing,**fixture)
    (tmp_path/"config.json").write_text(json.dumps(cfg,indent=2))
    prepare_dos_baseline(process_runtime["boot_image"],tmp_path/"boot.img",
                         process_runtime["mcopy"],config=b"SWITCHES=/F\r\n"+BASELINE_CONFIG)
    reference = bochs_phase(tmp_path,"before")
    options = qemu_dos_options(tmp_path,cfg)
    from fdisbull.qemu_dos import prepare_dos_profile
    if not high_backing:
        options["guest_profile"] = prepare_dos_profile(tmp_path/"boot.img",cpu="max")
    with Project.create(tmp_path/"cx16.fdb",source,image="mz") as project:
        with project.debugger(str(process_runtime["executable"]),source.parent,**options) as debug:
            _stop_at(debug,cfg["entry"])
            registers = debug.registers()
            assert registers["cpu_mode"] == "long"
            if high_backing:
                assert debug.vm.debugger().memory(cfg["target"],16,space="virtual").hex() == INITIAL
                assert debug.vm.debugger().memory(cfg["target_physical"],16,space="physical").hex() == INITIAL
                assert debug.vm.debugger().memory(cfg["low_alias"],16,space="physical").hex() == "0f0b"*8
                with pytest.raises(ValueError,match="High RAM layer writes are unsupported"):
                    debug.layer_patch("Refused high RAM write",cfg["target"],space="linear",
                                      kind="ram",expected_hex=INITIAL,data_hex=CHANGED)
                assert debug.layers()["active"] == []
            address, space = layer_target(cfg)
            layer = debug.layer_patch("CX16 target",address,space=space,
                                      kind="execute",expected_hex=INITIAL,data_hex="cc"*16)
            checkpoint = debug.save_machine_state()["artifact"]
            hot = exercise(debug,cfg,layer["layer"])
        with project.debugger(str(process_runtime["executable"]),source.parent,**options) as debug:
            initial = debug.registers()
            assert initial["cpu_mode"] == "real" and not initial["address_state"]["paging"]
            assert int(initial["address_state"]["control"]["CR4"],16)&0x30 == 0
            restored = debug.load_machine_state(checkpoint,timeout_ms=60000)
            assert restored["machine_state_restored"] and not restored["protected_source_rebound"]
            active = restored["controls"]["layers"][layer["layer"]]
            assert active != layer["layer"] and debug.layers()["active"] == [active]
            recovered = debug.registers()
            assert recovered["registers"] == registers["registers"]
            assert recovered["address_state"] == registers["address_state"]
            cold = exercise(debug,cfg,active)
    reference_cold = bochs_phase(tmp_path,"after")
    assert reference_cold["restore_before_guest_execution"]
    assert hot == cold == reference["observations"] == reference_cold["observations"]
    (tmp_path/"cx16-result.json").write_text(json.dumps(dict(
        locked=locked,high_backing=high_backing,target_physical=cfg["target_physical"],
        checkpoint=checkpoint,
        qemu_live=hot,qemu_cold=cold,bochs_live=reference,bochs_cold=reference_cold,
        source_sha256=cfg["sha256"],native_image_sha256=native_image_sha256),indent=2)+"\n")
