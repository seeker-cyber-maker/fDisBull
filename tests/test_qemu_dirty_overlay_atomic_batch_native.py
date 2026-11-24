"""Paired CMPXCHG8B and split-store overlay witnesses on high RAM."""

import hashlib
import json
import os

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.le_dirty_overlay_bochs import run as bochs_phase
from support.le_remap_qemu import qemu_dos_options
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from test_qemu_dos_process_native import process_runtime as process_runtime


MODES = ("pae-4k-high", "pae-2m-high", "pse36-4m-high")
LAYER_FAULT = "guest self-modified an execution-layer backing byte"
INITIAL_ATOMIC = "8877665544332211"
MATCHED_ATOMIC = "1122334455667788"


def _memory(debug, address, length):
    return debug.memory(address, length=length, space="virtual")["hex"]


def _register(debug_registers, short, long):
    return int(debug_registers.get(short, debug_registers.get(long)), 16) & 0xFFFFFFFF


def _stop(debug, offsets, expected_pc, atomic_physical, split_backing, low_split_before):
    stop = debug.run(timeout_ms=10000)
    assert stop["outcome"] == "stopped", stop
    assert stop["layer_conflict"]["fault"] == LAYER_FAULT
    assert stop["layer_conflict"]["execution-bytes"] == 0
    assert stop["session"]["stop_reason"]["breakpoint_ids"] == []
    pc = int(stop["registers"]["linear_pc"], 16)
    assert pc == expected_pc
    atomic = _memory(debug, offsets["atomic_target"], 8)
    split = _memory(debug, offsets["split_target"], 4)
    sentinel = _memory(debug, offsets["sentinel"], 1)
    assert sentinel == "90"
    native = debug.vm.debugger()
    assert native.memory(atomic_physical, 8, space="physical").hex() == atomic
    assert native.memory(atomic_physical & 0xFFFFFFFF, 8, space="physical").hex() == INITIAL_ATOMIC
    split_raw = bytes(native.memory(address, 1, space="physical")[0] for address in split_backing)
    assert split_raw.hex() == split
    low_split = bytes(native.memory(address & 0xFFFFFFFF, 1, space="physical")[0]
                      for address in split_backing)
    assert low_split.hex() == low_split_before
    assert _memory(debug, offsets["unrelated"], 1) == "a5"
    registers = stop["registers"]["registers"]
    flags = _register(registers, "eflags", "rflags")
    with pytest.raises(DebuggerError, match="layer.*faulted"):
        debug.run(timeout_ms=100)
    cpu = dict(zf=bool(flags & 0x40), eax=_register(registers, "eax", "rax"),
               edx=_register(registers, "edx", "rdx"))
    return dict(pc=pc, atomic=atomic, split=split, sentinel=sentinel, **cpu), cpu


def _run_batch(debug, offsets, physical, split_backing, low_split_before):
    fallback = debug.breakpoint(offsets["sentinel_store"] + 7)["breakpoint_id"]
    cmp_length = 8 if offsets["cmpxchg_lock"] else 7

    # A single run dirties the backing page, executes the mismatch, and
    # commits the changed-value match. The guest records the mismatch.
    changed, changed_cpu = _stop(debug, offsets, offsets["cmp_succeeded"] + cmp_length,
                                 physical, split_backing, low_split_before)
    assert changed_cpu == dict(zf=True, eax=0x55667788, edx=0x11223344)
    assert changed["atomic"] == MATCHED_ATOMIC and changed["split"] == "44332211"

    debug.layers([])
    debug.layer_patch("CMPXCHG8B same-value target", hex(offsets["atomic_target"]),
                      space="linear", kind="execute", expected_hex=MATCHED_ATOMIC,
                      data_hex="cccccccccccccccc")
    same, same_cpu = _stop(debug, offsets, offsets["cmp_same"] + cmp_length,
                           physical, split_backing, low_split_before)
    assert same_cpu == dict(zf=True, eax=0x44332211, edx=0x88776655)
    assert same["atomic"] == MATCHED_ATOMIC and same["split"] == "44332211"

    debug.layers([])
    point = debug.breakpoint(offsets["split_store"])["breakpoint_id"]
    ready = debug.run(timeout_ms=10000)
    assert ready["outcome"] == "breakpoint"
    assert ready["session"]["stop_reason"]["breakpoint_ids"] == [point]
    debug.delete_breakpoint(point)
    split_layer = debug.layer_patch(
        "Second physical page of split DWORD", hex(offsets["split_target"] + 3),
        space="linear", kind="execute", expected_hex="11", data_hex="cc")
    assert [tuple(span) for span in split_layer["native_binding"]["spans"]] == [
        (split_backing[3], 1)]
    split, _ = _stop(debug, offsets, offsets["split_store"] + 10, physical, split_backing, low_split_before)
    assert split["split"] == "d4c3b2a1" and split["atomic"] == MATCHED_ATOMIC

    debug.layers([])
    continuation = debug.run(timeout_ms=10000)
    assert continuation["outcome"] == "breakpoint"
    assert continuation["session"]["stop_reason"]["breakpoint_ids"] == [fallback]
    assert _memory(debug, offsets["sentinel"], 1) == "cc"
    result = dict(changed=changed, same=same, split=split)
    for key, address_key in (("flags", "atomic_result_flags"),
                             ("eax", "atomic_result_eax"), ("edx", "atomic_result_edx")):
        raw = bytes.fromhex(_memory(debug, offsets[address_key], 12))
        result[key] = [int.from_bytes(raw[i:i + 4], "little") for i in (0, 4, 8)]
    result["zf"] = [bool(flag & 0x40) for flag in result.pop("flags")]
    assert result["zf"] == [False, True, True]
    assert result["eax"] == [0x55667788, 0x55667788, 0x44332211]
    assert result["edx"] == [0x11223344, 0x11223344, 0x88776655]
    return result


@pytest.mark.parametrize("paging_mode", MODES)
@pytest.mark.parametrize("locked", (False, True), ids=("plain", "lock"))
def test_atomic_batch_overlay_live_and_unprimed_cold(
    tmp_path, process_runtime, paging_mode, locked
):
    if not all(os.environ.get(name) for name in ("FDISBULL_QEMU_IMG", "FDISBULL_BOCHS")):
        pytest.skip("Select QEMU machine checkpoints and the independent Bochs debugger")
    (tmp_path / "build").mkdir()
    fixture = build_paged_ldt_fixture(
        tmp_path / "build", str(process_runtime["nasm"]), tracking=True,
        paging_mode=paging_mode, dirty_overlay_writes=True,
        dirty_overlay_atomic_batch=True, cmpxchg_lock=locked)
    source = tmp_path / "game" / "REMAP.EXE"
    source.parent.mkdir()
    source.write_bytes(fixture["path"].read_bytes())
    prepare_dos_baseline(process_runtime["boot_image"], tmp_path / "boot.img",
                         process_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG)
    offsets = fixture["dirty_write_offsets"]
    cfg = dict(source=str(source), sha256=fixture["sha256"], paging_mode=paging_mode,
               high_physical=True, low_alias_marker="0f0b", dirty_write_offsets=offsets)
    (tmp_path / "config.json").write_text(json.dumps(cfg, indent=2))
    before = bochs_phase(tmp_path, "before")
    reference = before["observations"]
    physical = reference["backing"]["atomic"][0]
    low_split_before = reference["low_aliases"]["split"]
    split_backing = reference["backing"]["split"]
    assert physical > 0xFFFFFFFF
    assert all(address > 0xFFFFFFFF for address in split_backing)
    assert split_backing[0] // 4096 != split_backing[3] // 4096
    options = qemu_dos_options(tmp_path, cfg)
    owners = []
    executable = str(process_runtime["executable"])
    with Project.create(tmp_path / "atomic.fdb", source, image="mz") as project:
        with project.debugger(executable, source.parent, _on_spawn=owners.append, **options) as debug:
            point = debug.breakpoint(fixture["entry_address"])["breakpoint_id"]
            assert debug.run(timeout_ms=30000)["outcome"] == "breakpoint"
            debug.delete_breakpoint(point)
            registers = debug.registers()
            layer = debug.layer_patch("CMPXCHG8B target", hex(offsets["atomic_target"]),
                                      space="linear", kind="execute", expected_hex=INITIAL_ATOMIC,
                                      data_hex="cccccccccccccccc")
            assert [tuple(span) for span in layer["native_binding"]["spans"]] == [(physical, 8)]
            checkpoint = debug.save_machine_state()["artifact"]
            hot = _run_batch(debug, offsets, physical, split_backing, low_split_before)
        with project.debugger(executable, source.parent, _on_spawn=owners.append, **options) as debug:
            initial = debug.registers()
            control = initial["address_state"]["control"]
            assert initial["cpu_mode"] == "real" and initial["address_state"]["paging"] is False
            assert int(control["CR0"], 16) & 0x80000000 == 0
            assert int(control["CR4"], 16) & 0x30 == 0
            restored = debug.load_machine_state(checkpoint, timeout_ms=60000)
            assert restored["machine_state_restored"] and not restored["protected_source_rebound"]
            new_layer = restored["controls"]["layers"][layer["layer"]]
            assert new_layer != layer["layer"] and debug.layers()["active"] == [new_layer]
            recovered = debug.registers()
            assert recovered["linear_pc"] == registers["linear_pc"]
            assert recovered["address_state"]["control"] == registers["address_state"]["control"]
            cold = _run_batch(debug, offsets, physical, split_backing, low_split_before)
    after = bochs_phase(tmp_path, "after")
    assert len(owners) == 2 and owners[0].pid != owners[1].pid
    assert before["pid"] != after["pid"] and after["restore_before_guest_execution"]
    assert reference == after["observations"]
    expected = dict(changed=reference["steps"]["cmp_succeeded"], same=reference["steps"]["cmp_same"],
                    split=reference["steps"]["split_store"], zf=[bool(f & 0x40) for f in reference["flags"]],
                    eax=reference["eax"], edx=reference["edx"])
    assert hot == cold == expected
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg["sha256"]
    (tmp_path / "atomic-batch-result.json").write_text(json.dumps(dict(
        mode=paging_mode, locked=locked, checkpoint=checkpoint, source_sha256=cfg["sha256"],
        physical=physical, split_backing=split_backing, qemu_live=hot, qemu_cold=cold,
        bochs_live=before, bochs_cold=after), indent=2) + "\n")
