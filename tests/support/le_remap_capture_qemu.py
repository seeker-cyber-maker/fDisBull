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
                checkpoint = debug.save_machine_state()["artifact"]
            else:
                previous = json.loads((stage / "qemu-capture-before.json").read_text())
                checkpoint = previous["checkpoint"]
                restored = debug.load_machine_state(checkpoint, timeout_ms=60000)
                assert restored["machine_state_restored"]
                assert not restored["protected_source_rebound"]

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

    exit_codes = [owner.poll() for owner in owners]
    assert exit_codes and all(code == 0 for code in exit_codes), exit_codes

    # Reopen only after the native process has exited. This proves that each
    # one-shot artifact is independently analyzable without a live binding.
    analyses = {}
    payloads = {}
    export_receipts = {}
    with Project(database) as offline:
        for view, artifact in captures.items():
            analyses[view] = offline.debug_analyze_le_code(artifact)
            exported = stage / f"{phase}-{view}-capture-export.json"
            receipt = offline.debug_export(artifact, exported)
            assert receipt["artifact"] == artifact and receipt["size"] > 0
            assert receipt["sha256"] == hashlib.sha256(exported.read_bytes()).hexdigest()
            payloads[view] = json.loads(exported.read_bytes())
            export_receipts[view] = receipt
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
    )
    assert result["source_sha256"] == cfg["sha256"]
    (stage / f"qemu-capture-{phase}.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    import sys

    run(Path(sys.argv[1]), sys.argv[2])
