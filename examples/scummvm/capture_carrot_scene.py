"""Capture a fresh KQ1 room transition, carrot take, and repeat refusal.

Both backends receive physical keyboard actions. The game source remains
unmodified; each attempt gets a separate private receipt, including failures.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from examples.agi.spatial_trial import native_game, read
from examples.scummvm.capture_transition import (
    _advance, _frame, _millis, _press_up, _scummvm_game, _source_inventory,
    _start_scummvm,
)
from fdisbull.scene_backend_comparison import CARROT_TASK, FORMAT, SOURCE_AGI_SHA256


def _python_inventory(backend):
    root = Path(__file__).resolve().parents[2]
    paths = ["examples/scummvm/capture_carrot_scene.py",
             "examples/scummvm/capture_transition.py",
             "src/fdisbull/project.py"]
    if backend == "dosbox-x":
        paths.extend(("examples/agi/spatial_trial.py", "src/fdisbull/debugger.py",
                      "src/fdisbull/dosbox_rpc.py", "src/fdisbull/runtime_observations.py"))
    elif backend == "scummvm-agi":
        paths.extend(("src/fdisbull/scummvm_debugger.py", "src/fdisbull/scummvm_rpc.py"))
    else:
        raise ValueError("Expected dosbox-x or scummvm-agi")
    sources = {name: sha256((root / name).read_bytes()).hexdigest() for name in paths}
    digest = sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return sources, digest


class _CountedSession:
    """Count task-level control calls without changing the backend session."""

    def __init__(self, session):
        self.session = session
        self.calls = {key: 0 for key in ("guest_runs", "state_reads", "memory_reads",
                                         "engine_state_reads", "keyboard_state_reads",
                                         "keyboard_submissions", "screenshots")}

    def __getattr__(self, name):
        return getattr(self.session, name)

    def run(self, *args, **kwargs):
        self.calls["guest_runs"] += 1
        return self.session.run(*args, **kwargs)

    def call(self, method, *args, **kwargs):
        if method == "memory.read":
            self.calls["memory_reads"] += 1
        return self.session.call(method, *args, **kwargs)

    def engine_state(self, *args, **kwargs):
        self.calls["engine_state_reads"] += 1
        return self.session.engine_state(*args, **kwargs)

    def keyboard_state(self, *args, **kwargs):
        self.calls["keyboard_state_reads"] += 1
        return self.session.keyboard_state(*args, **kwargs)

    def keyboard_press(self, *args, **kwargs):
        self.calls["keyboard_submissions"] += 1
        return self.session.keyboard_press(*args, **kwargs)

    def keyboard_type(self, *args, **kwargs):
        self.calls["keyboard_submissions"] += 1
        return self.session.keyboard_type(*args, **kwargs)

    def screenshot(self, *args, **kwargs):
        self.calls["screenshots"] += 1
        return self.session.screenshot(*args, **kwargs)

    def clear(self):
        for key in self.calls:
            self.calls[key] = 0


def _dos_state(session, report):
    ds = int(report["resolution"]["ds_linear"], 16)
    actor = int(report["resolution"]["actor_linear"], 16)
    values = read(session, ds + 9, 7)
    flags = read(session, ds + 0x109, 32)
    return {"room": values[0], "score": values[3],
            "carrot_flag_77": bool(flags[77 // 8] & (0x80 >> (77 % 8))),
            "ego_y": int.from_bytes(read(session, actor + 5, 2), "little", signed=True),
            "direction": values[6],
            "message_window": bool(int.from_bytes(read(session, ds + 0xd15, 2), "little"))}


def _scummvm_state(session):
    state = session.engine_state()
    values, flags = state.get("vars"), state.get("flags")
    if not isinstance(values, list) or len(values) < 7 or not isinstance(flags, list) or len(flags) <= 77:
        raise ValueError("ScummVM AGI variables and flags are unavailable")
    ego = next((obj for obj in state.get("screen_objects", []) if obj.get("id") == 0), None)
    if ego is None or type(ego.get("y")) is not int:
        raise ValueError("ScummVM ego screen object is unavailable")
    return {"room": values[0], "score": values[3], "carrot_flag_77": flags[77],
            "ego_y": ego["y"], "direction": values[6],
            "at_modal": state.get("at_modal"), "modal_revision": state.get("modal_revision")}


def _idle_dos(session):
    keyboard = session.keyboard_state().get("keyboard", {})
    return all(type(keyboard.get(key)) is int and keyboard[key] == 0
               for key in ("pending_events", "owned_keys", "queued_guest_ms"))


def _input(session, backend, kind, value):
    if kind == "type":
        result = (session.keyboard_type(value, hold_ms=30, gap_ms=30)
                  if backend == "dosbox-x" else session.keyboard_type(value))
    elif kind == "press":
        result = (session.keyboard_press(value, hold_ms=30, gap_ms=30)
                  if backend == "dosbox-x" else session.keyboard_press(value))
    else:
        raise ValueError("Unknown physical input")
    if result.get("accepted") is not True and not (type(result.get("queued")) is int
                                                    and result["queued"] > 0):
        raise RuntimeError("Keyboard action was not confirmed queued")
    return {"kind": kind, "value": value,
            "delivery": "accepted" if result.get("accepted") is True else "queued"}


def _up(session, ledger, purpose):
    result = _press_up(session)
    ledger.append({"kind": "press", "value": "up", "purpose": purpose,
                   "delivery": "accepted" if result.get("accepted") is True else "queued"})


def _route(session, backend, observe, ledger):
    if backend == "scummvm-agi":
        _up(session, ledger, "start northward movement")
    seen_room_16 = False
    entered_room_16_at_bottom = False
    arrival = None
    for _ in range(200 if backend == "scummvm-agi" else 100):
        if backend == "dosbox-x":
            _up(session, ledger, "continue northward movement")
        _advance(session, backend)
        current = observe()
        if current["score"] != 0 or current["carrot_flag_77"] is not False:
            raise RuntimeError("Movement unexpectedly changed the carrot or score")
        if current["room"] == 16:
            seen_room_16 = True
            # The DOS room variable can turn 16 before the ego is relocated
            # from room 1's north edge to room 16's south edge. Do not treat
            # that transient state as reaching the carrot.
            if current["ego_y"] >= 150:
                entered_room_16_at_bottom = True
            if entered_room_16_at_bottom and current["ego_y"] <= 140:
                arrival = current
                break
        elif current["room"] != 1 or seen_room_16:
            raise RuntimeError("Movement left the qualified room route")
    if arrival is None:
        raise RuntimeError("Physical movement did not reach room 16 at the carrot")
    # In this AGI edition the same direction key toggles movement off.
    # Check the resulting state rather than assuming delivery changed it.
    _up(session, ledger, "stop northward movement")
    _advance(session, backend)
    stopped = observe()
    if stopped["room"] != 16 or stopped["direction"] != 0 or stopped["ego_y"] > 140:
        raise RuntimeError(f"Physical movement did not settle at the carrot: before={arrival}, after={stopped}")
    return stopped


def _dos_command(session, observe, ledger, *, expected_score, expected_flag):
    if not _idle_dos(session) or observe()["message_window"]:
        raise RuntimeError("DOS keyboard or prior message is not settled")
    ledger.append(_input(session, "dosbox-x", "type", "get carrot"))
    for _ in range(16):
        if _idle_dos(session):
            break
        _advance(session, "dosbox-x")
    if not _idle_dos(session):
        raise RuntimeError("Typed command did not settle")
    ledger.append(_input(session, "dosbox-x", "press", "enter"))
    opened = False
    dismissed = False
    for _ in range(24):
        _advance(session, "dosbox-x")
        current = observe()
        if current["message_window"]:
            opened = True
            if not _idle_dos(session):
                continue
            ledger.append(_input(session, "dosbox-x", "press", "enter"))
            dismissed = True
            continue
        if opened and dismissed and _idle_dos(session):
            if current["room"] != 16 or current["score"] != expected_score or current["carrot_flag_77"] is not expected_flag:
                raise RuntimeError("DOS command produced an unexpected state")
            return {"opened": opened, "dismissed": dismissed, "state": current}
    raise RuntimeError("DOS command did not open and close its message window")


def _scummvm_command(session, observe, ledger, *, expected_score, expected_flag):
    initial = observe()
    if initial["at_modal"] is not False or type(initial["modal_revision"]) is not int:
        raise RuntimeError("ScummVM previous message is not settled")
    ledger.append(_input(session, "scummvm-agi", "type", "get carrot"))
    ledger.append(_input(session, "scummvm-agi", "press", "enter"))
    opened = None
    for _ in range(24):
        _advance(session, "scummvm-agi")
        current = observe()
        if current["at_modal"] is True and current["modal_revision"] > initial["modal_revision"]:
            opened = current["modal_revision"]
            ledger.append(_input(session, "scummvm-agi", "press", "enter"))
            break
    if opened is None:
        raise RuntimeError("ScummVM command did not open a witnessed message box")
    for _ in range(24):
        _advance(session, "scummvm-agi")
        current = observe()
        if current["at_modal"] is False and current["modal_revision"] > opened:
            if current["room"] != 16 or current["score"] != expected_score or current["carrot_flag_77"] is not expected_flag:
                raise RuntimeError("ScummVM command produced an unexpected state")
            return {"opened_revision": opened, "closed_revision": current["modal_revision"],
                    "state": current}
    raise RuntimeError("ScummVM message box did not close")


def capture(source, backend_binary, backend, output, *, game_id="kq1"):
    source = Path(source).resolve(strict=True)
    backend_binary = Path(backend_binary).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists() or source == output or source in output.parents or output in source.parents:
        raise ValueError("Fresh private output must be separate from original game source")
    inventory, manifest_hash = _source_inventory(source)
    python_sources, python_hash = _python_inventory(backend)
    if not backend_binary.is_file() or not os.access(backend_binary, os.X_OK):
        raise ValueError("Backend executable is unavailable")
    receipt = {"format": FORMAT, "task": CARROT_TASK, "backend": backend,
               "status": "incomplete", "policy": "physical", "interventions": [],
               "source": {"agi_sha256": SOURCE_AGI_SHA256, "manifest_sha256": manifest_hash},
               "runtime": {"binary_sha256": sha256(backend_binary.read_bytes()).hexdigest(),
                           "python_manifest_sha256": python_hash,
                           "python_sources": python_sources, "version": None},
               "boundaries": {}, "commands": [], "inputs": [], "timing_ms": {},
               "route_control_calls": {},
               "startup_input_count": 0,
               "input_delivery": ("DOSBox accepted keyboard events" if backend == "dosbox-x"
                                  else "ScummVM events queued; per-event consumption unverified"),
               "claim_ceiling": "one room transition, one carrot pickup, one repeat refusal"}
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    t0 = time.monotonic()
    startup_end = route_end = teardown_begin = None
    observation_seconds = 0.0
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
                session = _CountedSession(session)
                raw_observe = lambda: _dos_state(session, report)
            else:
                project, session, game = opened
                session = _CountedSession(session)
                receipt["startup_input_count"] = _start_scummvm(session)
                raw_observe = lambda: _scummvm_state(session)

            def observe():
                nonlocal observation_seconds
                beginning = time.monotonic()
                session.calls["state_reads"] += 1
                result = raw_observe()
                observation_seconds += time.monotonic() - beginning
                return result

            def stored_frame(name):
                nonlocal observation_seconds
                beginning = time.monotonic()
                result = _frame(project, session, output, name)
                observation_seconds += time.monotonic() - beginning
                return result

            start = observe()
            receipt["boundaries"]["start"] = {"state": start,
                "frame": stored_frame("dos-start.png" if backend == "dosbox-x" else "scummvm-start.png")}
            if (start["room"], start["score"], start["carrot_flag_77"]) != (1, 0, False):
                raise RuntimeError("Fresh KQ1 source did not begin at the qualified state")
            startup_end = time.monotonic()
            session.clear()  # route controls start after the qualified room-1 frame
            arrival = _route(session, backend, observe, receipt["inputs"])
            receipt["boundaries"]["arrival"] = {"state": arrival,
                "frame": stored_frame("dos-arrival.png" if backend == "dosbox-x" else "scummvm-arrival.png")}
            command = _dos_command if backend == "dosbox-x" else _scummvm_command
            first = command(session, observe, receipt["inputs"], expected_score=2, expected_flag=True)
            receipt["commands"].append({"command": "get carrot", "result": "taken", "witness": first})
            receipt["boundaries"]["carrot"] = {"state": observe(),
                "frame": stored_frame("dos-carrot.png" if backend == "dosbox-x" else "scummvm-carrot.png")}
            repeated = command(session, observe, receipt["inputs"], expected_score=2, expected_flag=True)
            receipt["commands"].append({"command": "get carrot", "result": "refused-no-state-change",
                                        "witness": repeated})
            receipt["boundaries"]["repeat"] = {"state": observe(),
                "frame": stored_frame("dos-repeat.png" if backend == "dosbox-x" else "scummvm-repeat.png")}
            stable_keys = ("room", "score", "carrot_flag_77", "ego_y", "direction")
            after_first = receipt["boundaries"]["carrot"]["state"]
            after_repeat = receipt["boundaries"]["repeat"]["state"]
            if any(after_repeat[key] != after_first[key] for key in stable_keys):
                raise RuntimeError("Repeat action changed the observed game state")
            receipt["route_control_calls"] = dict(session.calls)
            route_end = time.monotonic()
            teardown_begin = route_end
        if _source_inventory(source)[0] != inventory or _source_inventory(game)[0] != inventory:
            raise RuntimeError("Game source or private copy changed during capture")
        if _python_inventory(backend)[0] != python_sources:
            raise RuntimeError("Python runtime source changed during capture")
        receipt["status"] = "complete"
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "detail": str(exc)[:400]}
    finally:
        end = time.monotonic()
        if startup_end is not None:
            receipt["timing_ms"]["startup"] = _millis(t0, startup_end)
            receipt["timing_ms"]["route"] = _millis(startup_end, route_end or end)
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
        result = capture(args.source, args.backend_binary, args.backend, args.output, game_id=args.game_id)
        print(json.dumps({"complete": result["status"] == "complete", "receipt": str(args.output / "run.json"),
                          "error": result.get("error")}))
        return 0 if result["status"] == "complete" else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"complete": False, "error": type(exc).__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
