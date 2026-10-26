#!/usr/bin/env python3
"""Verify keyboard -> mouse OK -> disk -> fresh guest read, using delivered 0.16.

Requires a user-owned DinoPark directory with the tested DINOSG.001 (PMM).
The game copy and databases go in --work-dir; only evidence goes in --evidence-dir.
No game bytes are patched, no score file is edited by this driver, and neither
session saves or restores an emulator state. Existing directories are refused.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import platform
import shutil
import sys

sys.dont_write_bytecode = True
EXE_SHA = "2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c"
PMM_SHA = "bf7af4fa7b57c96ff67dcd545d4b6873aee70681c0a197844fd73a84c40d32c5"
NAME = "DeepSeek016"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


def entries(data):
    assert len(data) == 250, "Unexpected leaderboard format"
    return [dict(rank=i + 1,
                 name=data[i*25:i*25+21].split(b"\0", 1)[0].decode("ascii"),
                 value=int.from_bytes(data[i*25+21:i*25+25], "little"))
            for i in range(10)]


def run(args):
    delivery, original = args.delivery.resolve(), args.game_dir.resolve()
    work, evidence = args.work_dir.resolve(), args.evidence_dir.resolve()
    assert work != evidence and work not in evidence.parents and evidence not in work.parents
    assert original not in work.parents and original not in evidence.parents
    if any((p / ".git").exists() for p in [work, *work.parents]):
        raise ValueError("Private game copy and databases must be outside Git")
    assert sha((original / "DINOPARK.EXE").read_bytes()) == EXE_SHA
    assert sha((original / "DINOSG.001").read_bytes()) == PMM_SHA
    original_inventory = inventory(original)
    assert NAME not in [x["name"] for x in entries((original / "TOPTEN.DAT").read_bytes())]
    work.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    game = work / "game"
    shutil.copytree(original, game)
    before = (game / "TOPTEN.DAT").read_bytes()
    sys.path.insert(0, str(delivery))
    import fdisbull_delivery
    module = fdisbull_delivery.activate()
    from fdisbull.project import Project
    assert module.__version__ == "0.16.0"
    assert delivery in Path(module.__file__).resolve().parents
    options = fdisbull_delivery.dos_options()
    receipt = dict(format="fdisbull-dinopark-leaderboard-1", version=module.__version__,
                   script_sha256=sha(Path(__file__).read_bytes()),
                   module=str(module.__file__), python=sys.version,
                   platform=platform.platform(), game_exe_sha256=EXE_SHA,
                   pmm_save_sha256=PMM_SHA, name=NAME, sessions=[],
                   native_state_save_calls=0, native_state_restore_calls=0,
                   memory_write_calls=0, register_write_calls=0, code_layers=[],
                   before_topten_sha256=sha(before))

    def save(name, data):
        (evidence / name).write_text(json.dumps(data, indent=2) + "\n")

    def route(p, d, name, steps):
        source = dict(format="fdisbull-script-1", steps=steps)
        save(name + ".script.json", source)
        saved = p.debug_save_script(name, source)
        result = d.script(script_id=saved["script_id"], timeout_ms=120000)
        save(name + ".result.json", result)
        for step in result["steps"]:
            if step["op"] == "click-frame" and step["ok"]:
                frame = step["result"]["frame"]
                p.debug_export(frame["artifact"], evidence / (name + "-" + str(step["index"]) + "-target.png"))
        assert result["ok"], result.get("error")
        return result

    def shot(p, d, name):
        raw = d.screenshot(name + ".png")
        p.debug_export(raw["artifact"], evidence / (name + ".png"))
        grid = p.debug_grid(raw["artifact"], name=name + "-grid8.png", step=8)
        p.debug_export(grid["artifact"], evidence / (name + "-grid8.png"))
        save(name + ".metadata.json", dict(clean=raw, grid=grid))

    def trace(p, d, name):
        result = d.trace(name + ".trace.json", count=128, timeout_ms=10000)
        p.debug_export(result["artifact"], evidence / (name + ".trace.json"))
        save(name + ".metadata.json", result)
        assert result["metadata"]["event_count"] == 128
        assert result["metadata"]["complete"]

    def advance(ms):
        return dict(op="run", guest_ms=ms, timeout_ms=15000,
                    fast_forward=True, expect="guest_time")

    def click(x, y, name):
        return dict(op="click-frame", x=x, y=y, name=name + ".png",
                    grid_step=8, hold_ms=80)

    def load_office(p, d, prefix):
        route(p, d, prefix + "-load-pmm", [advance(35000),
              click(160, 160, "old-game"), advance(1500),
              click(90, 70, "pmm-row"), advance(300),
              click(250, 73, "load-arrow"), advance(3000),
              click(175, 140, "office"), advance(1800)])
        shot(p, d, prefix + "-office")

    def seed(p, d, linear, offset, name):
        result = p.analyze(start=hex(linear), cs="0x27e5", max_instructions=16)
        save(name + "-analysis.json", result)  # Bounded analysis, never claimed stable.
        bp = d.breakpoint("27e5:" + offset)
        save(name + "-breakpoint.json", bp)
        assert bp["bytes_verified"]
        return bp["breakpoint_id"]

    def sell_steps():
        return [click(252, 151, "sell-park"), advance(800),
                click(176, 110, "confirm-sale")]

    # Session 1: normal sale of PMM; type, release the game's modal text editor,
    # then activate OK with the mouse. Ctrl+O sends ASCII 15, a game-supported
    # editor terminator that preserves the buffer without auto-activating OK.
    # Enter would activate the whole dialog; Escape discards the edited text.
    with Project.create(work / "writer.fdb", game / "DINOPARK.EXE", load_segment=0x1000) as p:
        with p.debugger(game_dir=game, **options) as d:
            first = dict(run=d.run_id, pid=d.rpc.process.pid,
                         backend_sha256=d.metadata["emulator_sha256"])
            load_office(p, d, "writer")
            bp = seed(p, d, 0x281c9, "0379", "writer")
            route(p, d, "writer-sell", sell_steps() + [advance(3000)])
            shot(p, d, "name-prompt")
            route(p, d, "writer-type-name", [dict(op="keyboard.type", text=NAME),
                  advance(1600), dict(op="keyboard.press", key="o", modifiers=["ctrl"]), advance(300)])
            memory = d.memory("4020:cce3", length=21)
            assert bytes.fromhex(memory["hex"]).split(b"\0", 1)[0] == NAME.encode()
            save("typed-name-observation.json", {k:v for k,v in memory.items() if k not in ("hex", "data_base64")})
            assert (game / "TOPTEN.DAT").read_bytes() == before
            shot(p, d, "typed-name")
            route(p, d, "writer-click-ok", [click(160, 126, "ok"),
                  dict(op="run", timeout_ms=5000, fast_forward=True, expect="breakpoint")])
            registers = d.registers()
            save("writer-registers.json", registers)
            assert registers["project_address"] == "0x281c9"
            assert (game / "TOPTEN.DAT").read_bytes() == before
            trace(p, d, "writer-entry")
            d.delete_breakpoint(bp)
            route(p, d, "writer-complete", [advance(6000)])
            after = (game / "TOPTEN.DAT").read_bytes()
            matching = [x for x in entries(after) if x["name"] == NAME]
            assert len(matching) == 1 and matching[0]["value"] > 500
            receipt["entry"] = matching[0]
            receipt["after_topten_sha256"] = sha(after)
            shot(p, d, "leaderboard-after-write")
        assert d.rpc.process.poll() is not None
        first["process_reaped"] = True
        receipt["sessions"].append(first)
    print(json.dumps(dict(writer_complete=True, entry=receipt["entry"])), flush=True)

    # Session 2: independent project and emulator, launched from disk; no load_state.
    # Stop after the game's real table reader returns, before any second write.
    with Project.create(work / "reader.fdb", game / "DINOPARK.EXE", load_segment=0x1000) as p:
        with p.debugger(game_dir=game, **options) as d:
            second = dict(run=d.run_id, pid=d.rpc.process.pid,
                          backend_sha256=d.metadata["emulator_sha256"])
            assert second["pid"] != first["pid"] and second["run"] != first["run"]
            load_office(p, d, "fresh")
            entry_bp = seed(p, d, 0x28228, "03d8", "reader-entry")
            return_bp = seed(p, d, 0x28377, "0527", "reader-return")
            route(p, d, "fresh-sell-read", sell_steps() + [
                  dict(op="run", timeout_ms=5000, fast_forward=True, expect="breakpoint")])
            assert d.registers()["project_address"] == "0x28228"
            trace(p, d, "fresh-reader-entry")
            d.delete_breakpoint(entry_bp)
            stopped = d.run(timeout_ms=5000, fast_forward=True)
            save("fresh-reader-return-stop.json", stopped)
            assert stopped["outcome"] == "breakpoint"
            regs = d.registers()
            assert regs["project_address"] == "0x28377"
            save("fresh-reader-return-registers.json", regs)
            # Original instruction is lea ax,[bp-0xfa]; SS names the caller's table.
            table_linear = int(regs["segments"]["ss"], 16)*16 + ((int(regs["general"]["ebp"], 16)-0xfa) & 0xffff)
            loaded = d.call("memory.read", dict(address=dict(space="linear", offset=f"0x{table_linear:08X}"), length=250))
            loaded_bytes = base64.b64decode(loaded["data_base64"])
            assert loaded_bytes == after
            found = [x for x in entries(loaded_bytes) if x["name"] == NAME]
            assert found == [receipt["entry"]]
            receipt["fresh_guest_readback"] = dict(byte_count=len(loaded_bytes),
                sha256=sha(loaded_bytes), project_stop="27e5:0527", observed_entry=found[0],
                full_table_equal_to_written_disk=True, address=loaded["address"])
            save("fresh-guest-readback.json", receipt["fresh_guest_readback"])
            d.delete_breakpoint(return_bp)
            route(p, d, "fresh-name-prompt", [advance(3000)])
            shot(p, d, "fresh-name-prompt-after-readback")
            assert (game / "TOPTEN.DAT").read_bytes() == after
        assert d.rpc.process.poll() is not None
        second["process_reaped"] = True
        receipt["sessions"].append(second)
    current = inventory(game)
    receipt["private_changed_files"] = [k for k in current if original_inventory.get(k) != current[k]]
    assert receipt["private_changed_files"] == ["TOPTEN.DAT"]
    assert set(current) == set(original_inventory)
    assert inventory(original) == original_inventory
    receipt["original_files_unchanged"] = len(original_inventory)
    receipt["ok"] = True
    save("VERIFICATION.json", receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    run(parser.parse_args())
