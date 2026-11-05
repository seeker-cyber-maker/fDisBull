"""Capture a fresh physical KQ1 room-1-to-room-16 route on one real backend.

Keep source games, FDBs, screenshots and these receipts in a private workspace.
This intentionally small scene route tests execution, input, state reads and
stored frames before more complex parser/dialogue and goat routes are attempted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import time

from examples.agi.spatial_trial import native_game, read
from fdisbull.scene_backend_comparison import FORMAT, SOURCE_AGI_SHA256, TASK
from fdisbull.project import Project


def _sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _source_inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Game source contains a symbolic link")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = _sha(path)
    if not files or files.get("AGI") != SOURCE_AGI_SHA256:
        raise ValueError("This route requires the exact qualified AGI 2.917 KQ1 edition")
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return files, sha256(encoded).hexdigest()


def _millis(start, end):
    return round((end - start) * 1000, 3)


def _bounded_state(room, score):
    if any(type(n) is not int or not 0 <= n <= 255 for n in (room, score)):
        raise ValueError("Expected bounded AGI variable bytes")
    return {"room": room, "score": score}


def _dos_state(session, report):
    ds = int(report["resolution"]["ds_linear"], 16)
    values = read(session, ds + 9, 4)
    return _bounded_state(values[0], values[3])


def _scummvm_state(session):
    state = session.engine_state()
    values = state.get("vars")
    if not isinstance(values, list) or len(values) < 4:
        raise ValueError("ScummVM did not expose AGI variable bytes")
    return _bounded_state(values[0], values[3])


def _start_scummvm(session):
    """Pass the observed AGI title room through ordinary queued Enter input."""
    sent_enter = False
    for _ in range(24):
        state = _scummvm_state(session)
        if state == {"room": 1, "score": 0}:
            return int(sent_enter)
        if state["score"] != 0 or state["room"] not in (0, 83):
            raise RuntimeError("ScummVM title flow entered an unexpected state")
        if state["room"] == 83 and not sent_enter:
            reply = session.keyboard_press("enter")
            if type(reply.get("queued")) is not int or reply["queued"] < 1:
                raise RuntimeError("ScummVM title Enter was not queued")
            sent_enter = True
        result = session.run(max_instructions=50000, guest_ms=250, timeout_ms=5000)
        if result.get("outcome") != "guest_time":
            raise RuntimeError("ScummVM title flow did not complete its guest slice")
    raise RuntimeError("ScummVM title flow exceeded bounded startup")


def _frame(project, session, output, name):
    observation = session.screenshot(name, hooks=False)
    metadata = observation.get("metadata", {})
    target = output / name
    project.debug_export(observation["artifact"], target)
    if _sha(target) != metadata.get("sha256"):
        raise ValueError("Exported frame differs from stored artifact")
    result = {"sha256": metadata["sha256"], "width": metadata["width"],
              "height": metadata["height"], "frame_id": metadata["frame_id"],
              "source": ("last_completed_guest_frame" if name.startswith("dos-")
                         else "last_committed_scummvm_display")}
    if name.startswith("dos-"):
        if metadata.get("source") != "last_completed_guest_frame":
            raise ValueError("DOS frame is not a completed guest frame")
    else:
        if metadata.get("frame_origin") != "last committed ScummVM display at AGI pause":
            raise ValueError("ScummVM display is not committed at the AGI pause")
        result["commit_revision"] = metadata["frame_commit_revision"]
    return result


def _press_up(session):
    result = session.keyboard_press("up", hold_ms=100, gap_ms=50)
    if result.get("accepted") is not True and (type(result.get("queued")) is not int or result["queued"] < 1):
        raise RuntimeError("Physical Up input was not confirmed queued")
    return result


def _advance(session, backend):
    if backend == "dosbox-x":
        result = session.run(guest_ms=150, timeout_ms=5000, fast_forward=True, stop_on_hook=True)
        if result.get("outcome") != "guest_time":
            raise RuntimeError("DOS route stopped before the bounded guest slice")
    else:
        result = session.run(max_instructions=50000, guest_ms=150, timeout_ms=5000)
        if result.get("outcome") not in ("guest_time", "budget"):
            raise RuntimeError("ScummVM route stopped before the bounded guest slice")
        if result.get("outcome") == "budget" and not result.get("executed"):
            raise RuntimeError("ScummVM made no bounded execution progress")
    return result


@contextmanager
def _scummvm_game(source, output, binary, game_id):
    game = output / "game"
    shutil.copytree(source, game)
    with Project.create(output / "private.fdb", game / "AGI", arch="x86", bits=16, base=0) as project:
        with project.debugger(binary, game, version=1, backend="scummvm-agi", game_id=game_id) as session:
            yield project, session, game


def capture(source, backend_binary, backend, output, *, game_id="kq1"):
    source = Path(source).resolve(strict=True)
    backend_binary = Path(backend_binary).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists() or source == output or source in output.parents or output in source.parents:
        raise ValueError("Fresh private output must be separate from original game source")
    inventory, inventory_hash = _source_inventory(source)
    if not backend_binary.is_file() or not os.access(backend_binary, os.X_OK):
        raise ValueError("Backend executable is unavailable")
    binary_hash = _sha(backend_binary)
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    receipt = {"format": FORMAT, "task": TASK, "backend": backend,
               "status": "incomplete", "policy": "physical", "interventions": [],
               "source": {"agi_sha256": SOURCE_AGI_SHA256, "manifest_sha256": inventory_hash},
               "runtime": {"binary_sha256": binary_hash, "version": None},
               "boundaries": {}, "timing_ms": {}, "input_count": 0,
               "startup_input_count": 0,
               "input_delivery": ("DOSBox accepted keyboard events" if backend == "dosbox-x"
                                  else "ScummVM events queued; per-event consumption unverified"),
               "claim_ceiling": "one original or compatible-engine room transition"}
    t0 = time.monotonic()
    observation_seconds = 0.0
    route_begin = route_end = startup_end = teardown_begin = None
    try:
        if backend == "dosbox-x":
            context = native_game("kq1", source, output / "dos-work", backend_binary, fair_play=True)
        elif backend == "scummvm-agi":
            context = _scummvm_game(source, output, backend_binary, game_id)
        else:
            raise ValueError("Expected dosbox-x or scummvm-agi")
        with context as opened:
            if backend == "dosbox-x":
                project, session, _, _, _, report, game = opened
                state = lambda: _dos_state(session, report)
            else:
                project, session, game = opened
                state = lambda: _scummvm_state(session)
                receipt["startup_input_count"] = _start_scummvm(session)
            begin_state = state()
            if begin_state != {"room": 1, "score": 0}:
                raise RuntimeError("Fresh game did not present the declared room-1 start")
            first_frame = _frame(project, session, output,
                                 "dos-start.png" if backend == "dosbox-x" else "scummvm-start.png")
            receipt["boundaries"]["start"] = {"state": begin_state, "frame": first_frame}
            startup_end = time.monotonic()
            route_begin = startup_end
            if backend == "scummvm-agi":
                _press_up(session)
                receipt["input_count"] += 1
            for _ in range(200 if backend == "scummvm-agi" else 80):
                if backend == "dosbox-x":
                    _press_up(session)
                    receipt["input_count"] += 1
                _advance(session, backend)
                observed_at = time.monotonic()
                current = state()
                observation_seconds += time.monotonic() - observed_at
                if current["room"] == 16:
                    if current["score"] != 0:
                        raise RuntimeError("Room transition changed score unexpectedly")
                    break
                if current["room"] != 1 or current["score"] != 0:
                    raise RuntimeError("Route entered an unexpected room or score state")
            else:
                raise RuntimeError("Room transition exhausted bounded physical inputs")
            # A completed frame must follow the observed room change. No input is
            # repeated after a failed or ambiguous advance.
            _advance(session, backend)
            observed_at = time.monotonic()
            final_state = state()
            final_frame = _frame(project, session, output,
                                 "dos-end.png" if backend == "dosbox-x" else "scummvm-end.png")
            observation_seconds += time.monotonic() - observed_at
            if final_state != {"room": 16, "score": 0}:
                raise RuntimeError("Final fresh frame no longer has the target state")
            receipt["boundaries"]["end"] = {"state": final_state, "frame": final_frame}
            if (backend == "dosbox-x" and final_frame["frame_id"]
                    <= first_frame["frame_id"]):
                raise RuntimeError("Final frame is not newer")
            if (backend == "scummvm-agi" and final_frame["commit_revision"]
                    <= first_frame["commit_revision"]):
                raise RuntimeError("ScummVM did not commit a newer display")
            route_end = time.monotonic()
            teardown_begin = route_end
        if _source_inventory(source)[0] != inventory:
            raise RuntimeError("Original game source changed during capture")
        if _source_inventory(game)[0] != inventory:
            raise RuntimeError("Private game copy changed during capture")
        receipt["status"] = "complete"
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "detail": str(exc)[:400]}
    finally:
        end = time.monotonic()
        if startup_end is not None:
            receipt["timing_ms"]["startup"] = _millis(t0, startup_end)
        if route_begin is not None:
            receipt["timing_ms"]["route"] = _millis(route_begin, route_end or end)
        receipt["timing_ms"]["observation"] = round(observation_seconds * 1000, 3)
        if teardown_begin is not None:
            receipt["timing_ms"]["teardown"] = _millis(teardown_begin, end)
        receipt["timing_ms"]["inclusive"] = _millis(t0, end)
        (output / "run.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--backend-binary", type=Path, required=True)
    parser.add_argument("--backend", choices=("dosbox-x", "scummvm-agi"), required=True)
    parser.add_argument("--game-id", default="kq1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = capture(args.source, args.backend_binary, args.backend, args.output,
                         game_id=args.game_id)
        print(json.dumps({"complete": result["status"] == "complete", "receipt": str(args.output / "run.json"),
                          "error": result.get("error")}))
        return 0 if result["status"] == "complete" else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"complete": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
