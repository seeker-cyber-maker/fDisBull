"""Observe the authored DOS Snake original for a source-assisted conversion.

The executable, compiler listing, ROM font, full rasters, FDB and observations
are private inputs/outputs. This recipe contains no target payload. It never
patches the executable. One declared RAM-state intervention qualifies the
otherwise hard-to-reach full-board winning frame separately from normal play.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess

from fdisbull.project import Project

TARGET = "f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be"
SCALARS = ("snake_length", "direction", "pending_direction", "paused", "game_status",
           "score", "rng_seed", "tick_count", "key_events", "mouse_events",
           "frame_count", "mouse_present", "food_cell", "turn_queued")
SHELL = ("needs_render", "step_requested", "quit_requested", "mouse_buttons",
         "mouse_x", "mouse_y", "last_tick")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def symbols(build):
    result = {}
    for segment, offset, name in re.findall(
            r"^\s*([0-9A-F]{4}):([0-9A-F]{4})\s+(\w+)\s*$",
            (build / "SNAKE.MAP").read_text(), re.M):
        result[name.lower()] = int(segment, 16) * 16 + int(offset, 16)
    # Compiler listing is retained only as a named address/extent oracle.
    listing = (build / "SNAKE.LST").read_text()
    for name, offset in re.findall(r"^([A-Z_]+)[ .\t]+([0-9A-F]{4})\s+_DATA\b", listing, re.M):
        result[name.lower()] = 0x7a0 + int(offset, 16)
    # These contiguous shell cells follow the public typed word state. Verify
    # source declarations and the independently recorded compiler listing.
    for name, relative in {"last_tick": 0x4cc, "mouse_buttons": 0x4ce,
                           "mouse_x": 0x4d0, "mouse_y": 0x4d2,
                           "needs_render": 0x4d4, "step_requested": 0x4d6,
                           "quit_requested": 0x4d8}.items():
        result[name] = 0x7a0 + relative
    assert all(n in result for n in (*SCALARS, *SHELL, "snake_cells"))
    return result


def observe(target, build, backend, output, vectors):
    from fdisbull import __version__
    from PIL import Image
    target, build, backend = (Path(x).resolve(strict=True) for x in (target, build, backend))
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Choose a new private output")
    git_root = next((p for p in output.parents if (p / ".git").exists()), None)
    if git_root is not None:
        # The established private target package has an empty, remote-free
        # guard repository whose contents are all ignored. It is not a source
        # checkout and must not be confused with permission to write into one.
        tracked = subprocess.check_output(["git", "ls-files"], cwd=git_root)
        remotes = subprocess.check_output(["git", "remote", "-v"], cwd=git_root)
        ignored = subprocess.run(["git", "check-ignore", str(output)], cwd=git_root,
                                 stdout=subprocess.DEVNULL, check=False).returncode == 0
        if tracked or remotes or not ignored:
            raise ValueError("Original observations must remain outside a source repository")
    raw = target.read_bytes()
    assert sha(raw) == TARGET and raw == (build / "SNAKE.EXE").read_bytes()
    output.mkdir(parents=True)
    sym = symbols(build)
    header = struct.unpack_from("<14H", raw)
    module_start = header[4] * 16
    module = raw[module_start:]
    assert module.count(bytes.fromhex("ff06c404")) == 1
    render_end = 0x10000 + module.index(bytes.fromhex("ff06c404")) + 4
    key_reads = [m.start() for m in re.finditer(re.escape(b"\xcd\x16"), module[:0x41d])]
    assert len(key_reads) == 2
    key_return = 0x10000 + key_reads[1] + 2
    assert module.count(b"\xcd\x1a") == 1
    clock_return = 0x10000 + module.index(b"\xcd\x1a") + 2
    assert module.count(bytes.fromhex("ff06c204")) == 1
    mouse_edge = 0x10000 + module.index(bytes.fromhex("ff06c204")) + 4
    records, assets = [], {}
    latest_frame = None
    with Project.create(output / "snake-original.fdb", target) as project:
        analyzed = project.analyze(max_instructions=6000)
        snippets = {}
        for name, offset, size in (
                ("reset", 0x0f1, 0x085), ("step", 0x176, 0x131),
                ("find-food", 0x2a7, 0x04f), ("queue-direction", 0x2f6, 0x039),
                ("keyboard", 0x35a, 0x0c3), ("mouse", 0x41d, 0x0f9),
                ("fill-rectangle", 0x516, 0x044), ("draw-cell", 0x55a, 0x02f),
                ("text", 0x589, 0x064), ("render", 0x5ed, 0x1b3)):
            snippets[name] = project.capture_snippet(
                "snake." + name, [{"address": hex(0x10000 + offset), "size": size}],
                version=1, boundary="Compiler-listing boundary; source-assisted, not blind recovery",
                evidence={"listing_sha256": sha((build / "SNAKE.LST").read_bytes())}, author="snake-source-assisted")
        with project.debugger(backend, target.parent, version=1) as debug:
            pid = debug.rpc.process.pid

            def memory(at, count):
                return base64.b64decode(debug.call("memory.read", {
                    "address": {"space": "linear", "offset": f"0x{at:08X}"},
                    "length": count})["data_base64"])

            def clock():
                return struct.unpack("<I", memory(0x46c, 4))[0]

            def state():
                first = 0x10000 + sym["snake_cells"]
                span = bytes.fromhex(debug.memory(hex(first), length=0x4da)["hex"])
                values = {n: struct.unpack_from("<H", span, sym[n] - sym["snake_cells"])[0]
                          for n in (*SCALARS, *SHELL)}
                values["snake_cells"] = list(struct.unpack_from("<600H", span))
                values["cells"] = values["snake_cells"][:values["snake_length"]]
                values["memory_words"] = values["snake_cells"] + [values[n] for n in (*SCALARS, *SHELL)]
                return values

            def address_bp(where):
                return debug.breakpoint(hex(where))["breakpoint_id"]

            def save_frame(ident):
                nonlocal latest_frame
                data = memory(0xa0000, 64000)
                name = ident + ".vga"
                (output / name).write_bytes(data)
                latest_frame = {"file": name, "sha256": sha(data), "bytes": len(data),
                                "width": 320, "height": 200,
                                "projection": "indexed-vram-after-original-render-before-mouse-show"}
                return latest_frame

            def settle(milliseconds=80, fast_forward=False):
                result = debug.run(guest_ms=milliseconds, fast_forward=fast_forward, timeout_ms=10000)
                assert result["outcome"] == "guest_time", result

            def operate(ident, action=None, intervention=None):
                before = state() if action is not None else None
                before_clock = clock()
                active = {"render": address_bp(render_end)}
                if action and action["kind"] == "key":
                    active["key"] = address_bp(key_return)
                    delivery = debug.keyboard_press(action["key"], hold_ms=25, gap_ms=25)
                elif action and action["kind"] == "mouse":
                    active["mouse"] = address_bp(mouse_edge)
                    shot = debug.screenshot("before-" + ident + ".png")
                    delivery = debug.click(action["x"], action["y"], hold_ms=50,
                                           mode_id=shot["metadata"]["mode_id"])
                else:
                    active["clock"] = address_bp(clock_return)
                    delivery = None
                reads, bios = [], None
                fresh = None
                for _ in range(8):
                    result = debug.run(guest_ms=80, fast_forward=False, timeout_ms=10000)
                    if result["outcome"] == "guest_time":
                        break
                    assert result["outcome"] == "breakpoint", result
                    stop = result["session"]["stop_reason"]["project_address"]
                    if int(stop, 16) == clock_return:
                        registers = debug.registers()
                        reads.append(int(registers["general"]["edx"], 16) & 0xffff)
                        debug.delete_breakpoint(active.pop("clock"))
                    elif int(stop, 16) == key_return:
                        registers = debug.registers()
                        ax = int(registers["general"]["eax"], 16) & 0xffff
                        bios = {"ascii": ax & 255, "scan": ax >> 8}
                        debug.delete_breakpoint(active.pop("key"))
                        active["clock"] = address_bp(clock_return)
                    elif int(stop, 16) == mouse_edge:
                        debug.delete_breakpoint(active.pop("mouse"))
                        active["clock"] = address_bp(clock_return)
                    else:
                        assert int(stop, 16) == render_end
                        fresh = save_frame(ident)
                        debug.delete_breakpoint(active.pop("render"))
                        break
                for bp in active.values():
                    debug.delete_breakpoint(bp)
                settle()
                after = state()
                assert latest_frame is not None
                command = {} if action is None else dict(action)
                if bios:
                    command.update(bios)
                command["clock_low16"] = reads[0] if reads else (before_clock & 0xffff)
                replay = []
                if action is not None and action["kind"] == "mouse":
                    replay = [dict(kind="pointer", x=action["x"], y=action["y"], buttons=1,
                                   clock_low16=command["clock_low16"]),
                              dict(kind="pointer", x=action["x"], y=action["y"], buttons=0,
                                   clock_low16=command["clock_low16"])]
                elif action is not None:
                    replay = [dict(kind="key", ascii=bios["ascii"], scan=bios["scan"],
                                   clock_low16=command["clock_low16"])]
                record = dict(id=ident, input=command, replay=replay, before=before, after=after,
                              before_bios_clock=before_clock, after_bios_clock=clock(),
                              clock_reads=reads, frame=dict(latest_frame, newly_rendered=fresh is not None),
                              delivery=delivery, intervention=intervention)
                records.append(record)
                print(ident, after["cells"][:5], "status", after["game_status"],
                      "frames", after["frame_count"], flush=True)
                return record

            initial = operate("initial")
            assert initial["after"]["cells"] == [308, 307, 306]
            vector = memory(0x10c, 4)
            off, segment = struct.unpack("<HH", vector)
            font = memory(segment * 16 + off, 2048)
            (output / "font8x8.bin").write_bytes(font)
            # Check live ROM glyph bytes against the original-rendered title.
            first_frame = (output / initial["frame"]["file"]).read_bytes()
            title = "SNAKE v1  SCORE 0"
            for index, char in enumerate(title):
                for y in range(8):
                    bits = font[ord(char) * 8 + y]
                    assert [first_frame[y * 320 + index * 8 + x] for x in range(8)] == [
                        15 if bits & (128 >> x) else 0 for x in range(8)]
            shot = debug.screenshot("initial-visible.png")
            project.debug_export(shot["artifact"], output / "initial-visible.png")
            screenshot = Image.open(output / "initial-visible.png").convert("RGB")
            current_vram = memory(0xa0000, 64000)
            colors = {}
            for color in sorted(set(current_vram)):
                counts = Counter(screenshot.getpixel((i % 320, i // 320))
                                 for i, value in enumerate(current_vram) if value == color)
                assert len(counts) == 1
                colors[str(color)] = list(next(iter(counts)))
            assert set(map(int, colors)) == {0, 1, 2, 8, 10, 12, 15}
            palette = {"format": "fdisbull-observed-indexed-palette-1", "colors": colors,
                       "domain": [int(n) for n in colors],
                       "source": "same-pixel native PNG RGB and live VRAM index pairs",
                       "unobserved": [n for n in range(256) if str(n) not in colors]}
            (output / "palette.json").write_text(json.dumps(palette, indent=2) + "\n")
            assets = {"font": dict(file="font8x8.bin", sha256=sha(font), bytes=2048,
                                   source="live INT43 vector", segment=segment, offset=off,
                                   glyph_validation=f"{len(title)} displayed title glyphs, {len(title) * 64} matching pixels"),
                      "palette": dict(file="palette.json", sha256=sha((output / "palette.json").read_bytes()),
                                      observed_indices=palette["domain"])}
            actions = [("ignored-key", {"kind": "key", "key": "x"}),
                       ("reverse-left", {"kind": "key", "key": "left"}),
                       ("arrow-up", {"kind": "key", "key": "up"}),
                       ("queued-down-ignored", {"kind": "key", "key": "down"}),
                       ("up-step", {"kind": "key", "key": "n"})]
            for key in ("left", "down", "right"):
                actions += [("arrow-" + key, {"kind": "key", "key": key}),
                            ("step-" + key, {"kind": "key", "key": "n"})]
            actions += [("reset-before-wasd", {"kind": "key", "key": "r"})]
            for key in "wasd":
                actions += [("wasd-" + key, {"kind": "key", "key": key}),
                            ("wasd-step-" + key, {"kind": "key", "key": "n"})]
            actions += [("reset-before-pointer", {"kind": "key", "key": "r"}),
                        ("pointer-outside", {"kind": "mouse", "x": 16, "y": 32})]
            for name, x, y in (("up", 290, 50), ("left", 268, 74),
                               ("down", 290, 98), ("right", 300, 74)):
                actions += [("pointer-" + name, {"kind": "mouse", "x": x, "y": y}),
                            ("pointer-step-" + name, {"kind": "mouse", "x": 280, "y": 154})]
            actions += [("pointer-unpause", {"kind": "mouse", "x": 280, "y": 130}),
                        ("keyboard-pause", {"kind": "key", "key": "p"}),
                        ("space-unpause", {"kind": "key", "key": "space"}),
                        ("space-pause", {"kind": "key", "key": "space"}),
                        ("pointer-reset", {"kind": "mouse", "x": 280, "y": 178})]
            actions += [(f"ordinary-right-step-{n:02d}", {"kind": "key", "key": "n"}) for n in range(1, 23)]
            actions += [("dead-n-ignored", {"kind": "key", "key": "n"}),
                        ("restart-after-death", {"kind": "key", "key": "r"})]
            for ident, action in actions:
                operate(ident, action)
            assert records[-2]["after"]["game_status"] == 1
            assert records[-1]["after"]["game_status"] == 0

            # Diagnostic state, not ordinary play: native original consumes the
            # final normal N key and performs the winning step and full redraw.
            all_cases = json.loads(Path(vectors).read_text())["cases"]
            winning = next(c for c in all_cases if c["expected"]["game_status"] == 2
                           and c["initial"]["game_status"] == 0)
            base = 0x10000 + sym["snake_cells"]
            desired = bytearray(bytes.fromhex(debug.memory(hex(base), length=0x4cc)["hex"]))
            for name, value in winning["initial"].items():
                if name == "cells":
                    struct.pack_into("<" + "H" * len(value), desired, 0, *value)
                else:
                    struct.pack_into("<H", desired, sym[name] - sym["snake_cells"], value)
            # The core diagnostic vector uses paused=0 because snake_step is
            # scheduler-independent. The native shell must be paused to reach
            # that same core call through its ordinary N-key command.
            struct.pack_into("<H", desired, sym["paused"] - sym["snake_cells"], 1)
            expected = debug.memory(hex(base), length=len(desired))["hex"]
            layer = debug.layer_patch("diagnostic-full-board-state", hex(base),
                                      expected_hex=expected, data_hex=desired.hex(), kind="ram")
            won = operate("diagnostic-full-board-winning-step", {"kind": "key", "key": "n"},
                          intervention={"kind": "ram-state-layer", "layer": layer["layer"],
                                        "ordinary_reachability": False,
                                        "state_sha256": sha(bytes(desired)), "source_case": winning["id"],
                                        "shell_adapter": "paused=1 admits ordinary N single-step"})
            assert won["after"]["game_status"] == 2 and won["after"]["snake_length"] == 600
            # Reset through the actual program before removing the layer.
            # Removing it while the winning state is active can restore bytes
            # still equal to the injected values and would create an unrecorded
            # state transition between two otherwise carried observations.
            operate("reset-after-diagnostic", {"kind": "key", "key": "r"})
            before_removal = state()
            debug.layers([], conflict="keep_changed")
            assert state() == before_removal, "Layer removal changed the carried reset state"
            # A separate finite clock sequence records the observed BIOS ticks
            # accepted by the original scheduler, not an authored speed model.
            operate("timer-unpause", {"kind": "key", "key": "space"})
            before = state()
            for _ in range(30):
                if ((clock() & 0xffff) - before["last_tick"]) & 0xffff >= 3:
                    break
                settle(10)
            now = clock() & 0xffff
            after = state()
            assert ((now - before["last_tick"]) & 0xffff) == 3
            assert after["tick_count"] == before["tick_count"]
            records.append(dict(id="timer-three-ticks-no-step", input={"kind": "clock", "clock_low16": now},
                                replay=[{"kind": "clock", "clock_low16": now}], before=before, after=after,
                                frame=dict(latest_frame, newly_rendered=False), clock_reads=[now],
                                intervention=None, delivery=None, timing_sequence=True))
            for index in range(3):
                before = state()
                step_bp = address_bp(0x10000 + sym["snake_step"])
                result = debug.run(guest_ms=500, fast_forward=True, timeout_ms=10000)
                assert result["outcome"] == "breakpoint", result
                now = clock() & 0xffff
                registers = debug.registers()
                delta = int(registers["general"]["edx"], 16) & 0xffff
                assert ((before["last_tick"] + delta) & 0xffff) == now
                debug.delete_breakpoint(step_bp)
                reads = []
                clock_bp = address_bp(clock_return)
                result = debug.run(guest_ms=500, fast_forward=True, timeout_ms=10000)
                assert result["outcome"] == "breakpoint", result
                reads.append(int(debug.registers()["general"]["edx"], 16) & 0xffff)
                debug.delete_breakpoint(clock_bp)
                render_bp = address_bp(render_end)
                result = debug.run(guest_ms=500, fast_forward=True, timeout_ms=10000)
                assert result["outcome"] == "breakpoint", result
                fresh = save_frame(f"timer-accepted-step-{index + 1}")
                debug.delete_breakpoint(render_bp)
                settle(1)
                after = state()
                assert after["tick_count"] == before["tick_count"] + 1
                records.append(dict(id=f"timer-accepted-step-{index + 1}",
                                    input={"kind": "clock", "clock_low16": now},
                                    replay=[{"kind": "clock", "clock_low16": now}],
                                    before=before, after=after, frame=dict(fresh, newly_rendered=True),
                                    clock_reads=reads, observed_scheduler_delta=delta,
                                    intervention=None, delivery=None, timing_sequence=True))
            operate("timer-pause", {"kind": "key", "key": "p"})

            # Observe quit state before teardown, mode restoration before
            # DOS_Terminate revokes memory access, then native exit code zero.
            before = state()
            exit_bytes = bytes.fromhex("b80300cd10b8004ccd21")
            assert module.count(exit_bytes) == 1
            mode_address = 0x10000 + module.index(exit_bytes)
            key_bp = address_bp(key_return)
            mode_bp = address_bp(mode_address)
            delivery = debug.keyboard_press("escape", hold_ms=25, gap_ms=25)
            result = debug.run(fast_forward=True, timeout_ms=10000)
            assert result["outcome"] == "breakpoint"
            ax = int(debug.registers()["general"]["eax"], 16) & 0xffff
            debug.delete_breakpoint(key_bp)
            result = debug.run(fast_forward=True, timeout_ms=10000)
            assert result["outcome"] == "breakpoint"
            assert int(result["session"]["stop_reason"]["project_address"], 16) == mode_address
            after = state()
            assert after["quit_requested"] == 1
            assert memory(0x449, 1) == b"\x13"
            now = clock() & 0xffff
            records.append(dict(id="escape-quit-before-teardown", input={"kind": "key", "key": "escape",
                                "ascii": ax & 255, "scan": ax >> 8, "clock_low16": now},
                                replay=[{"kind": "key", "ascii": ax & 255, "scan": ax >> 8,
                                         "clock_low16": now}], before=before, after=after,
                                frame=dict(latest_frame, newly_rendered=False),
                                intervention=None, delivery=delivery, lifecycle=True))
            debug.delete_breakpoint(mode_bp)
            terminate_bp = address_bp(mode_address + 5)
            result = debug.run(fast_forward=True, timeout_ms=10000)
            assert result["outcome"] == "breakpoint" and memory(0x449, 1) == b"\x03"
            debug.delete_breakpoint(terminate_bp)
            result = debug.run(guest_ms=100, fast_forward=True, timeout_ms=10000)
            assert result["outcome"] == "guest_exit"
            native_exit = result["session"]["stop_reason"]["guest_exit"]
            assert native_exit["requested_exit_code"] == 0
            lifecycle = {"mode_before": 19, "mode_after": 3, "dos_exit_code": 0,
                         "stop": result["stop"], "native_exit": native_exit,
                         "original_process_exit_observed": True}
        assert debug.rpc.process.poll() is not None
        analysis_status = project.analysis_status()
        stored_artifacts = project.debug_artifacts(version=1)
    assert sha(target.read_bytes()) == TARGET
    with Project(output / "snake-original.fdb") as reopened:
        assert reopened.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for name, receipt in snippets.items():
            assert reopened.snippet_info(receipt["id"])["id"] == receipt["id"]
    document = {"format": "fdisbull-snake-original-observations-1", "status": "passed",
                "identities": {"target_sha256": TARGET, "source_asm_sha256": sha((build / "SNAKE.ASM").read_bytes()),
                               "listing_sha256": sha((build / "SNAKE.LST").read_bytes()),
                               "map_sha256": sha((build / "SNAKE.MAP").read_bytes()),
                               "backend_sha256": sha(backend.read_bytes()), "fdisbull_version": __version__},
                "source_assisted": True, "static_load_base": "0x10000", "symbols": sym,
                "abi_state_words": {**{name: 600 + i for i, name in enumerate(SCALARS)},
                                    **{name: 614 + i for i, name in enumerate(SHELL)}},
                "assets": assets, "observations": records, "snippets": snippets,
                "analysis": analyzed, "analysis_status": analysis_status,
                "runtime_artifacts": stored_artifacts, "process_pid": pid, "process_reaped": True,
                "lifecycle": lifecycle,
                "database_reopened": True, "original_executable_unchanged": True,
                "scope": "Source-assisted native graphics/input observations; clean indexed rasters exclude driver cursor; one declared diagnostic state; no converted backing qualified here"}
    (output / "originals.json").write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({"status": "passed", "observations": len(records),
                      "new_rasters": sum(r["frame"]["newly_rendered"] for r in records),
                      "output": str(output)}))
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "build", "backend", "output", "vectors"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    observe(args.target, args.build, args.backend, args.output, args.vectors)
