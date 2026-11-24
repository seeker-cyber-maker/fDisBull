"""Capture stopped paged LE code before and after an unprimed QEMU restore."""

import hashlib
import json
import os
from pathlib import Path

from fdisbull.project import Project
from support.le_remap_qemu import qemu_dos_options
from support.le_translation_native import integer


def run(stage, phase):
    stage = Path(stage)
    assert phase in ("before", "after")
    cfg = json.loads((stage / "config.json").read_text())
    source = Path(cfg["source"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg["sha256"]
    database = stage / "qemu-capture.fdb"
    options = qemu_dos_options(stage, cfg)
    rt = os.environ

    owners = []
    overlay_ids = []
    view_bytes = {}
    native_overlay_reads = {}
    with Project.create(database, source, image="mz") if phase == "before" else Project(database) as project:
        with project.debugger(
            rt["FDISBULL_QEMU_DOS"], source.parent, _on_spawn=owners.append, **options
        ) as debug:
            entry_registers = debug.registers()
            entry_state = entry_registers["address_state"]
            assert entry_registers["cpu_mode"] == "real"
            assert entry_state["paging"] is False
            assert integer(entry_state["control"]["CR0"]) & 0x80000000 == 0
            assert integer(entry_state["control"]["CR4"]) & 0x30 == 0
            if phase == "before":
                bp = debug.breakpoint(cfg["start_pc"])["breakpoint_id"]
                stop = debug.run(timeout_ms=10000)
                assert stop["outcome"] == "breakpoint"
                assert bp in stop["session"]["stop_reason"]["breakpoint_ids"]
                debug.delete_breakpoint(bp)
                for _ in range(cfg["checkpoint_index"]):
                    assert debug.step()["outcome"] == "step"
                overlay_ids = []
                if cfg.get("active_high_overlay"):
                    target = cfg["second_target"]
                    high = debug.vm.debugger().memory(target, 2, space="physical")
                    assert high == b"\x46\xcb"
                    target_pc = int(debug.registers()["linear_pc"], 16)
                    patched = debug.layer_patch(
                        "High-backed execute overlay", hex(target_pc), expected_hex="46",
                        data_hex="4e", kind="execute", space="linear",
                    )
                    spans = patched["native_binding"]["spans"]
                    assert spans == [(target, 1)] or spans == [[target, 1]]
                    overlay_ids.append(patched["layer"])
                    low_address = cfg.get(
                        "low_overlay_address", cfg["second_target"] & 0xFFFFFFFF
                    )
                    low_before = debug.vm.debugger().memory(low_address, 1, space="physical")
                    low_after = bytes((low_before[0] ^ 0xFF,))
                    low = debug.layer_patch(
                        "Wrapped low physical execute overlay", hex(low_address),
                        expected_hex=low_before.hex(), data_hex=low_after.hex(),
                        kind="execute", space="physical",
                    )
                    overlay_ids.append(low["layer"])
                    assert debug.layers()["active"] == overlay_ids
                    assert debug.vm.debugger().memory(low_address, 1, space="physical") == low_before
                    low_ram = debug.code(low_address, length=1, view="ram", space="physical")
                    assert low_ram["hex"] == low_before.hex()
                    low_execute = debug.code(low_address, length=1, view="execute", space="physical")
                    assert low_execute["hex"] == low_after.hex()
                    assert low_execute["active_layers"] == overlay_ids
                checkpoint = debug.save_machine_state()["artifact"]
            else:
                previous = json.loads((stage / "qemu-capture-before.json").read_text())
                checkpoint = previous["checkpoint"]
                restored = debug.load_machine_state(checkpoint, timeout_ms=60000)
                assert restored["machine_state_restored"]
                assert not restored["protected_source_rebound"]
                saved_overlay_ids = previous.get("overlay_ids", [])
                layer_map = restored.get("controls", {}).get("layers", {})
                overlay_ids = [layer_map[layer] for layer in saved_overlay_ids]
                # First stopped observation after direct cold restore: no layer reapply.
                assert debug.layers()["active"] == overlay_ids

            if cfg.get("active_high_overlay"):
                low_address = cfg.get(
                    "low_overlay_address", cfg["second_target"] & 0xFFFFFFFF
                )
                low_base = debug.vm.debugger().memory(low_address, 1, space="physical")
                low_info = debug.layers()
                low_layer = next(
                    layer for layer in low_info["layers"] if layer["id"] == overlay_ids[1]
                )
                assert low_layer["patches"][0]["expected_hex"] == low_base.hex()
                assert low_layer["patches"][0]["data_hex"] == bytes((low_base[0] ^ 0xFF,)).hex()
                assert debug.vm.debugger().memory(low_address, 1, space="physical") == low_base
                low_ram = debug.code(low_address, length=1, view="ram", space="physical")
                assert low_ram["hex"] == low_base.hex()
                low_execute = debug.code(low_address, length=1, view="execute", space="physical")
                assert low_execute["hex"] == low_layer["patches"][0]["data_hex"]
                assert low_execute["active_layers"] == overlay_ids
                def native_observe(address, length):
                    return debug.vm.qmp.call(
                        "x-fdisbull-layer-observe-physical64",
                        {"address": address, "length": length},
                    )

                high_native = native_observe(cfg["second_target"], 2)
                wrapped_native = native_observe(
                    cfg["second_target"] & 0xFFFFFFFF, 2
                )
                low_native = native_observe(low_address, 1)
                assert high_native["data-hex"] == "4ecb"
                assert wrapped_native["data-hex"] == "f00b"
                assert low_native["data-hex"] == low_layer["patches"][0]["data_hex"]
                for observed in (high_native, wrapped_native, low_native):
                    assert observed["generation"] == low_info["generation"]
                    assert observed["execution-bytes"] == 2
                native_overlay_reads = dict(
                    high=high_native,
                    poisoned_wrapped_low=wrapped_native,
                    wrapped_low_overlay=low_native,
                )

            assert not debug.dos_source_binding()["live"]
            before = debug.registers()
            target_pc = int(before["linear_pc"], 16)
            captures = {}
            capture_metadata = {}
            for view in ("execute", "ram"):
                unchanged = debug.registers()
                result = debug.capture_code(
                    target_pc, space="linear", length=15, view=view,
                    name=f"{phase}-{view}.json",
                )
                assert debug.registers() == unchanged
                captures[view] = result["artifact"]
                capture_metadata[view] = result["metadata"]
            reader = debug.vm.debugger()
            alias_reads = []
            for address in (cfg["first_target"], cfg["second_target"]):
                high = reader.memory(address, 2, space="physical")
                low = reader.memory(address & 0xFFFFFFFF, 2, space="physical")
                assert high.hex() == "46cb" and low.hex() == cfg["low_alias_marker"]
                alias_reads.append(dict(address=address, high=high.hex(), low=low.hex()))
            after = debug.registers()
            assert after == before
            assert not debug.dos_source_binding()["live"]
            trial = trial_registers = None
            if cfg.get("active_high_overlay"):
                trial = debug.step()
                assert trial["outcome"] == "step"
                trial_registers = debug.registers()
                esi_before = integer(before["registers"]["rsi"]) & 0xFFFFFFFF
                esi_after = integer(trial_registers["registers"]["rsi"]) & 0xFFFFFFFF
                assert esi_after == (esi_before - 1) & 0xFFFFFFFF

    exit_codes = [owner.poll() for owner in owners]
    assert exit_codes and all(code == 0 for code in exit_codes), exit_codes

    # Reopen only after the native process has exited. This proves that each
    # one-shot artifact is independently analyzable without a live binding.
    analyses = {}
    payloads = {}
    export_receipts = {}
    with Project(database) as offline:
        for view, artifact in captures.items():
            analyses[view] = (
                None if cfg.get("active_high_overlay")
                else offline.debug_analyze_le_code(artifact)
            )
            exported = stage / f"{phase}-{view}-capture-export.json"
            receipt = offline.debug_export(artifact, exported)
            assert receipt["artifact"] == artifact and receipt["size"] > 0
            assert receipt["sha256"] == hashlib.sha256(exported.read_bytes()).hexdigest()
            payloads[view] = json.loads(exported.read_bytes())
            export_receipts[view] = receipt
        if cfg.get("active_high_overlay"):
            for view in ("ram", "execute"):
                assert payloads[view]["active_layers"] == overlay_ids
                assert payloads[view]["space"] == "linear"
                view_bytes[view] = payloads[view]["hex"][:4]
            assert view_bytes == {"ram": "46cb", "execute": "4ecb"}
            assert all(
                capture_metadata[view].get("static_promotion") == "unqualified"
                for view in ("ram", "execute")
            )
            for artifact in captures.values():
                try:
                    offline.debug_promote_code(artifact)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Active-layer high capture was promoted to source")
        assert len(offline.versions()) == 1
    result = dict(
        checkpoint=checkpoint,
        artifacts=captures,
        capture_metadata=capture_metadata,
        analyses=analyses,
        payloads=payloads,
        export_receipts=export_receipts,
        stopped_registers=before,
        fresh_process_registers=entry_registers,
        alias_reads=alias_reads,
        target_pc=target_pc,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        restored_in_fresh_process=phase == "after",
        overlay_ids=overlay_ids,
        view_bytes=view_bytes,
        native_overlay_reads=native_overlay_reads,
        overlay_step=(dict(
            outcome=trial["outcome"],
            esi_before=integer(before["registers"]["rsi"]) & 0xFFFFFFFF,
            esi_after=integer(trial_registers["registers"]["rsi"]) & 0xFFFFFFFF,
        ) if cfg.get("active_high_overlay") else None),
    )
    assert result["source_sha256"] == cfg["sha256"]
    (stage / f"qemu-capture-{phase}.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    import sys

    run(Path(sys.argv[1]), sys.argv[2])
