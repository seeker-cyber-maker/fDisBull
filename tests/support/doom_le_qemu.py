"""Public-API QEMU controller for the bounded original-Doom LE proof.

Private executables, media, firmware and game files are selected by the caller
and staged outside Git.  The controller uses Project/debugger methods only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from fdisbull.project import Project

PINS = {
    "DOOM.EXE": "4970b0d1fefa45836a5723777d2bb41e7932965782678aca6c2bbeec705b38d4",
    "DOOM.WAD": "6fdf361847b46228cfebd9f3af09cd844282ac75f3edbb61ca4cb27103ce2e7f",
    "AUD512.LMP": "47978643dcc56e0aaec7c234c12e5d9e0f8800b2aab643338d2899be2e9bd213",
    "DEFAULT.CFG": "a5fb4d6791aa01ccb704f7cb6370cff9d69d0b898c30832295e91c53a33baa9d",
}
CODE_OFFSET, DATA_OFFSET = 0x33120, 0x2D354


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path(name, executable=False):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set {name} for the private QEMU Doom LE proof")
    path = Path(value).expanduser().absolute()
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        raise RuntimeError(f"{name} must select a usable file: {path}")
    return path


def runtime_inputs():
    return {
        "executable": _path("FDISBULL_QEMU_DOS", True),
        "boot_image": _path("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": _path("FDISBULL_QEMU_DOS_MCOPY", True),
        "firmware": os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"),
        "checkpoint_tool": _path("FDISBULL_QEMU_IMG", True),
    }


def stage_game(stage, source):
    game = Path(stage) / "game"
    game.mkdir(parents=True, exist_ok=True)
    source = Path(source).resolve(strict=True)
    for name, expected in PINS.items():
        original = source / name
        if not original.is_file() or _digest(original) != expected:
            raise ValueError(f"Pinned private Doom input mismatch: {original}")
        shutil.copyfile(original, game / name)
    assert {name: _digest(game / name) for name in PINS} == PINS
    return game


def _options(runtime, game):
    return dict(backend="qemu-dos", dos_directory=str(game),
        dos_boot_image=str(runtime["boot_image"]), dos_mcopy=str(runtime["mcopy"]),
        qemu_transport="pipe", qemu_firmware=runtime["firmware"],
        qemu_audio="sb16-opl", qemu_retrace="precise",
        qemu_clock="virtual", qemu_checkpoint_tool=str(runtime["checkpoint_tool"]),
        dos_arguments="-playdemo AUD512 -config D:\\DEFAULT.CFG",
        boot_timeout_ms=35000)


def qualified_stop(debug):
    from fdisbull.qemu_dos_le_match import SourceMatchError

    for _ in range(40):
        stop = debug.clock_advance(2_000_000_000, timeout_ms=20000)
        registers = debug.registers()
        state = registers["address_state"]
        assert stop["outcome"] not in ("guest_exit", "guest_tsr", "exited")
        if (registers["cpu_mode"] != "protected" or state["code_bits"] != 32
                or state["paging"] is not False or state["a20"] is not True):
            continue
        try:
            admission = debug.dos_source_admit(expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20000)
        except SourceMatchError as exc:
            if str(exc) != "ambiguous source placement within one object":
                raise
            continue
        if admission["status"] == "admitted":
            binding = debug.dos_source_bind(expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20000)
            if binding["live"]:
                return binding
    raise AssertionError("The guest did not reach a qualified Doom LE boundary")


def stop_at_increment(project, debug, stage):
    binding = qualified_stop(debug)
    exported = stage / "initial-binding.json"
    project.debug_export(binding["artifact"]["artifact"], exported)
    recipe = json.loads(exported.read_bytes())["recipe"]
    bases = {p["object_index"]: p["runtime_base"] for p in recipe["placements"]}
    pc, counter = bases[1] + CODE_OFFSET, bases[3] + DATA_OFFSET
    bp = debug.breakpoint(pc)["breakpoint_id"]
    stopped = debug.run(timeout_ms=30000)
    assert stopped["outcome"] == "breakpoint" and bp in stopped["session"]["stop_reason"]["breakpoint_ids"]
    debug.delete_breakpoint(bp)
    debug.dos_source_bind(expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20000)
    return pc, counter


def run(stage, phase):
    if phase not in ("hot", "cold"):
        raise ValueError("Expected hot or cold")
    runtime = runtime_inputs()
    source = Path(os.environ["FDISBULL_DOOM_LE_SOURCE"])
    hot_path = stage / "qemu-hot.json"
    database = stage / "doom.fdb"
    owners = []
    if phase == "hot":
        game = stage_game(stage, source)
        project = Project.create(database, game / "DOOM.EXE", image="mz")
    else:
        hot = json.loads(hot_path.read_text())
        game = stage / "game"
        project = Project(database)
    with project:
        with project.debugger(runtime["executable"], game, **_options(runtime, game), _on_spawn=owners.append) as debug:
            if phase == "hot":
                pc, target = stop_at_increment(project, debug, stage)
                checkpoint = debug.save_le_source_state("doom-le-state.json", timeout_ms=60000)["artifact"]
            else:
                checkpoint = hot["checkpoint"]
                restored = debug.load_le_source_state(checkpoint, timeout_ms=60000)
                assert restored["protected_source_rebound"] and not restored["source_binding_restored"]
                pc, target = hot["pc"], hot["target"]
            binding = debug.dos_source_binding()
            regs = debug.registers()
            assert binding["live"] and int(regs["linear_pc"], 0) == pc and regs["cpu_mode"] == "protected"
            observed = debug.memory(pc, length=6, space="virtual")["hex"]
            assert int.from_bytes(bytes.fromhex(observed)[2:], "little") == target
            tick = int.from_bytes(bytes.fromhex(debug.memory(target, length=4, space="virtual")["hex"]), "little")
            capture = debug.capture_code(pc, length=6, space="linear", view="execute", name="doom-le.json")
            assert capture["metadata"]["offline_analysis"] == "qualified-le-source-capture", capture["metadata"]
    assert owners and all(owner.poll() == 0 for owner in owners)
    with Project(database) as offline:
        analysis = offline.debug_analyze_le_code(capture["artifact"])
        assert analysis["runtime_bytes"] == observed and len(offline.versions()) == 1
    result = dict(checkpoint=checkpoint, pc=pc, target=target, tick=tick, cpu=regs["registers"],
                  binding_id=binding["binding_id"], epoch=binding["capture_epoch"], analysis=analysis)
    if phase == "cold":
        for field in ("pc","target","tick","cpu"):
            assert result[field] == hot[field], field
        assert result["epoch"] != hot["epoch"] and result["binding_id"] != hot["binding_id"]
        assert analysis["run"] != hot["analysis"]["run"]
    assert all(_digest(source / name) == value for name, value in PINS.items())
    (stage / ("qemu-" + phase + ".json")).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
