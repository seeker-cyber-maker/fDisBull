#!/usr/bin/env python3
"""Compare complete original DinoPark view checks with one capture-layer change.

Own one fresh run_session guest. Use its qualified Office -> Bank -> Office ->
Street route, then quit. No finance, purchase, save, restore or replay command is
issued. Runtime inputs, screenshots, projects and receipts remain private.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import sqlite3
import statistics
import subprocess
import time


WARMUPS = 3
VIEWS = ("office", "bank", "shop_street")


class BenchmarkFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise BenchmarkFailure(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(path.read_bytes())


def inventory(root):
    return {p.relative_to(root).as_posix(): file_hash(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def summarize(values):
    ordered = sorted(values)
    require(ordered, "Cannot summarize an empty sample")
    return {"median": statistics.median(ordered),
            "p95": ordered[math.ceil(.95 * len(ordered)) - 1], "samples": len(ordered)}


def selected_environment(pid):
    allowed = {"SDL_AUDIODRIVER", "XDG_CONFIG_HOME"}
    proc = Path(f"/proc/{pid}/environ")
    if proc.is_file():
        fields = (v.decode("utf-8", "replace").partition("=")
                  for v in proc.read_bytes().split(b"\0") if v)
        result = {key: value for key, sep, value in fields if sep and key in allowed}
    else:
        completed = subprocess.run(["ps", "eww", "-p", str(pid)], check=True,
                                   capture_output=True, text=True, timeout=3)
        result = {}
        for key in allowed:
            match = re.search(rf"(?:^|\s){re.escape(key)}=([^\s]+)(?=\s|$)", completed.stdout)
            if match:
                result[key] = match.group(1)
    require(result.get("SDL_AUDIODRIVER") == "dummy", "Actual spawn does not prove dummy audio")
    return result


def db_counts(project):
    return {"total_changes": project.db.total_changes,
            "events": project.db.execute("SELECT count(*) FROM debug_events").fetchone()[0],
            "artifacts": project.db.execute("SELECT count(*) FROM debug_artifacts").fetchone()[0]}


@contextmanager
def bind_capture(scenes, capture):
    previous = scenes.observe_frame
    scenes.observe_frame = capture
    try:
        yield
    finally:
        scenes.observe_frame = previous


@contextmanager
def read_only_native(native, record):
    original = native.rpc.call
    record.update(method_counts={}, forbidden_calls=[])
    allowed = {"video.screenshot", "video.probe", "memory.read", "state.get_registers"}

    def call(method, *args, **kwargs):
        record["method_counts"][method] = record["method_counts"].get(method, 0) + 1
        if method not in allowed:
            record["forbidden_calls"].append(method)
            raise BenchmarkFailure("Execution/input/restore or unsupported RPC during paused checks: " + method)
        return original(method, *args, **kwargs)

    native.rpc.call = call
    try:
        yield
    finally:
        native.rpc.call = original


@contextmanager
def optimized_guards(native, project, record):
    """Guard the complete optimized check; its external event journal is allowed."""
    from PIL import Image
    before_open, before_save = Image.open, Image.Image.save
    counters = {key: 0 for key in ("image_open", "image_save", "export", "artifact",
                                   "database_event", "hooks", "sql_write_attempts")}
    record.update(counters=counters, database_before=db_counts(project))
    patches, missing = [], object()

    def opened(*args, **kwargs):
        counters["image_open"] += 1
        return before_open(*args, **kwargs)

    def saved(*args, **kwargs):
        counters["image_save"] += 1
        raise BenchmarkFailure("Optimized check attempted PNG saving")

    def block(obj, name, key):
        old = vars(obj).get(name, missing)

        def blocked(*args, **kwargs):
            counters[key] += 1
            raise BenchmarkFailure("Optimized check invoked " + name)

        patches.append((obj, name, old))
        setattr(obj, name, blocked)

    def authorize(action, arg1, arg2, database, trigger):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                      sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        counters["sql_write_attempts"] += 1
        return sqlite3.SQLITE_DENY

    try:
        Image.open, Image.Image.save = opened, saved
        block(native, "_event", "database_event")
        block(native, "_artifact", "artifact")
        block(native, "_capture_with_hooks", "hooks")
        block(project, "_debug_artifact", "artifact")
        block(project, "debug_export", "export")
        project.db.set_authorizer(authorize)
        yield
    finally:
        project.db.set_authorizer(None)
        for obj, name, old in reversed(patches):
            if old is missing:
                delattr(obj, name)
            else:
                setattr(obj, name, old)
        Image.open, Image.Image.save = before_open, before_save
        record["database_after"] = db_counts(project)


def verify_guards(record):
    require(record["database_before"] == record["database_after"],
            "Optimized check changed database events/artifacts or total_changes")
    require(record["counters"]["image_open"] == 1, "Optimized indexed PNG did not use exactly one PIL decode")
    require(all(value == 0 for key, value in record["counters"].items() if key != "image_open"),
            "Optimized check used a forbidden side path")


def metadata(frame):
    require(isinstance(frame, dict) and isinstance(frame.get("metadata"), dict), "Invalid capture descriptor")
    return {key: frame["metadata"].get(key) for key in
            ("width", "height", "frame_id", "mode_id", "captured_ticks")}


def no_payload(value):
    if isinstance(value, dict):
        return (not any(k in value for k in ("artifact", "artifact_id", "png_base64", "data_base64")) and
                all(no_payload(v) for v in value.values()))
    if isinstance(value, (list, tuple)):
        return all(no_payload(v) for v in value)
    return not isinstance(value, (bytes, bytearray, memoryview))


def verify_direct(frame, raw_sha, identity):
    require(frame.get("capture") == "direct" and frame.get("persistent") is False and no_payload(frame),
            "Optimized descriptor must be ephemeral and contain no pixels/artifact identity")
    require(frame.get("sha256") == raw_sha and frame["metadata"].get("sha256") == raw_sha,
            "Optimized descriptor raw-RGBA digest mismatch")
    require(metadata(frame) == identity, "Optimized frame identity changed")
    require(frame["metadata"].get("transport", {}).get("encoding") == "png-indexed",
            "Optimized native check did not select advertised indexed PNG")


def points_in(pattern):
    for sample in pattern["samples"]:
        yield sample["x"], sample["y"]
    for other in pattern.get("reject", []):
        yield from points_in(other)


def native_match(pattern, pixels):
    tolerance = pattern["tolerance"]
    hits = sum(all(abs(a - b) <= tolerance for a, b in
                   zip(pixels[(sample["x"], sample["y"])], sample["rgb"], strict=True))
               for sample in pattern["samples"])
    return hits >= pattern["min_matches"] and not any(native_match(p, pixels) for p in pattern.get("reject", []))


def predicate_accuracy(scenes, text, baseline, optimized, identity, authored):
    patterns = {**{"authored:" + name: p for name, p in authored.items()},
                **{"runtime:" + name: p for name, p in text.patterns.items()}}
    coordinates = sorted({point for pattern in patterns.values() for point in points_in(pattern)})
    pixels = {}
    for start in range(0, len(coordinates), 4096):
        selected = coordinates[start:start + 4096]
        probe = text.debug.frame_probe([list(point) for point in selected])
        for key in ("frame_id", "mode_id", "captured_ticks"):
            require(probe.get(key) == identity[key], "Native predicate probe changed " + key)
        for point, sample in zip(selected, probe["samples"], strict=True):
            observed = tuple(sample["rgb"])
            require(observed == baseline.getpixel(point) == optimized.getpixel(point),
                    "Native probe differs from captured RGB at " + str(point))
            pixels[point] = observed
    results = {}
    for name, pattern in patterns.items():
        old, new, native = scenes.matches(baseline, pattern), scenes.matches(optimized, pattern), native_match(pattern, pixels)
        require(old == new == native, "Predicate disagreement: " + name)
        results[name] = {"legacy": old, "optimized": new, "native": native}
    positive = [name for name in VIEWS if scenes.matches(optimized, text.patterns[name])]
    expected = "shop_street" if text.current == "street" else text.current
    require(positive == [expected], "Actual scene is not uniquely positive: " + repr(positive))
    return {"authored_predicates": len(authored), "runtime_predicates": len(text.patterns),
            "native_points": len(coordinates), "all_equal": True, "results": results,
            "positive_view": expected, "negative_views": [v for v in VIEWS if v != expected],
            "modal_branch": "not exercised; no modal requested by the Office/Bank/Street route"}


def benchmark_case(scenes, text, case, iterations, event_state, authored):
    native, project = text.debug.native, text.project
    original_observer = scenes.observe_frame
    expected = "shop_street" if case["scene"] == "street" else case["scene"]
    require(text.current == case["scene"], "Route reached an unexpected scene; further input withheld")
    before_registers, before_balances = native.registers(), scenes.balances(text.debug)
    case.update(status="running", registers_before=before_registers, balances_before=before_balances,
                samples=[], rpc_guard={})
    with read_only_native(native, case["rpc_guard"]):
        legacy_frame, baseline = scenes.take_frame(project, text.debug, "benchmark-" + case["scene"] + "-reference", hooks=False)
        require(baseline.mode == "RGB" and baseline.size == (320, 200), "Unsupported baseline image")
        identity, rgb = metadata(legacy_frame), baseline.tobytes()
        raw_sha = digest(baseline.convert("RGBA").tobytes())
        accuracy_guard = {}
        with optimized_guards(native, project, accuracy_guard):
            direct_frame, direct_image = original_observer(project, text.debug, "benchmark-accuracy")
        verify_guards(accuracy_guard)
        verify_direct(direct_frame, raw_sha, identity)
        require(direct_image.mode == "RGB" and direct_image.size == baseline.size and direct_image.tobytes() == rgb,
                "Full RGB differs between capture layers")
        case.update(frame=identity, rgb_sha256=digest(rgb), raw_rgba_sha256=raw_sha,
                    color_count_rgb=len(set(baseline.getdata())), reference=legacy_frame,
                    direct_descriptor=direct_frame, accuracy_guard=accuracy_guard,
                    predicate_accuracy=predicate_accuracy(scenes, text, baseline, direct_image, identity, authored))
        rng = random.Random(0x5CE0 + len(case["scene"]))
        for round_index in range(WARMUPS + iterations):
            order = ["legacy", "optimized"]
            rng.shuffle(order)
            round_results = {}
            for layer in order:
                captured, guard = {}, {}

                def capture(project_arg, debug_arg, name):
                    started = time.perf_counter_ns()
                    result = (scenes.take_frame(project_arg, debug_arg, name, hooks=False) if layer == "legacy"
                              else original_observer(project_arg, debug_arg, name))
                    captured.update(frame=result[0], image=result[1],
                                    capture_ms=(time.perf_counter_ns() - started) / 1_000_000)
                    return result

                label = f"benchmark-{case['scene']}-round-{round_index:02d}"
                event_before = event_state["count"]

                def complete_check():
                    started = time.perf_counter_ns()
                    found = text.observe_one_of(list(VIEWS), scenes.balances(text.debug), label, wait_slices=0)
                    return found, (time.perf_counter_ns() - started) / 1_000_000

                with bind_capture(scenes, capture):
                    if layer == "optimized":
                        with optimized_guards(native, project, guard):
                            found, elapsed = complete_check()
                        verify_guards(guard)
                    else:
                        found, elapsed = complete_check()
                require(found == expected, "Production observation selected the wrong view")
                require(event_state["count"] == event_before + 1, "Production view check did not journal exactly one event")
                event = event_state["last"]
                require(event.get("phase") == "shop_observation" and event.get("matched_views") == [expected]
                        and event.get("observed_balances") == before_balances,
                        "Production semantic event changed or balances drifted")
                require(metadata(captured["frame"]) == identity and captured["image"].tobytes() == rgb,
                        "Timed capture changed frame identity or full RGB")
                if layer == "optimized":
                    verify_direct(captured["frame"], raw_sha, identity)
                round_results[layer] = {"view_check_ms": elapsed, "capture_ms": captured["capture_ms"],
                    "found": found, "full_rgb_equal": True, "frame_metadata_equal": True,
                    "semantic_journal_events": 1, "guards": guard if layer == "optimized" else None}
            if round_index >= WARMUPS:
                case["samples"].append({"round": round_index - WARMUPS + 1,
                                         "order": order, "results": round_results})
        after_registers, after_balances = native.registers(), scenes.balances(text.debug)
        require(after_registers == before_registers and after_balances == before_balances,
                "Read-only comparisons changed registers or balances")
        after_probe = native.frame_probe([[0, 0], [160, 100], [319, 199]])
        for key in ("frame_id", "mode_id", "captured_ticks"):
            require(after_probe.get(key) == identity[key], "Final probe changed " + key)
        for sample in after_probe["samples"]:
            require(tuple(sample["rgb"]) == baseline.getpixel((sample["x"], sample["y"])), "Final RGB probe differs")
    case.update(status="passed", registers_after=after_registers, balances_after=after_balances,
                registers_identical=True, balances_identical=True, native_final_probe_equal=True,
                timings={layer: {metric: summarize([s["results"][layer][metric] for s in case["samples"]])
                                 for metric in ("view_check_ms", "capture_ms")}
                         for layer in ("legacy", "optimized")})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="new private directory outside Git")
    parser.add_argument("--iterations", type=int, default=30)
    args = parser.parse_args(argv)
    require(1 <= args.iterations <= 1000, "iterations must be in 1..1000")
    repo = Path(__file__).resolve().parents[1]
    backend, game, work = args.backend.expanduser().resolve(strict=True), args.game_dir.expanduser().resolve(strict=True), args.work_dir.expanduser().resolve()
    require(not work.exists() and work.parent.is_dir(), "work-dir must be new with an existing private parent")
    require(not any((p / ".git").exists() for p in (work, *work.parents)), "work-dir must be outside Git")
    require(backend.is_file() and os.access(backend, os.X_OK), "backend must name an executable file")
    original_inventory = inventory(game)
    paths = ([Path(__file__).resolve()] + sorted((repo / "src/fdisbull").rglob("*.py")) +
             sorted((repo / "player").rglob("*.py")) + sorted((repo / "src/fdisbull/data").glob("dinopark*.json")))
    source_hashes = {str(p.relative_to(repo)): file_hash(p) for p in paths}
    report = {"format": "fdisbull-dinopark-scene-check-benchmark-1", "status": "running",
              "platform": platform.platform(), "iterations": args.iterations, "warmups": WARMUPS,
              "capture_layer_change": "production observe_frame versus take_frame(hooks=False); same current source/backend",
              "timing_scope": "complete observe_one_of including expected/observed balance reads and production event journaling",
              "timing_instrumentation": "capture timers and optimized side-effect counters enabled; overhead not subtracted",
              "source_hashes_before": source_hashes,
              "source_bundle_sha256": digest(json.dumps(source_hashes, sort_keys=True).encode()),
              "backend_sha256": file_hash(backend), "original_inventory_before": original_inventory,
              "cases": [], "commands": [], "route_output": [], "spawn": []}
    event_state, state, processes = {"count": 0, "last": None}, {}, []
    report_path = work / "benchmark.json"

    def persist():
        if work.is_dir():
            temporary = report_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            temporary.replace(report_path)

    def event(item):
        event_state["count"] += 1
        event_state["last"] = item

    def spawned(process):
        processes.append(process)
        arguments = list(process.args)
        mute = all(any(arguments[i:i + 2] == ["-set", value] for i in range(len(arguments) - 1))
                   for value in ("mixer nosound=true", "midi mididevice=none"))
        selected = selected_environment(process.pid)
        require(mute, "Actual native spawn did not include mixer and MIDI mute settings")
        report["spawn"].append({"pid": process.pid, "selected_environment": selected,
                                "mixer_and_midi_muted": mute, "window_requested": "-agent-window" in arguments})
        persist()

    previous_store = os.environ.get("FDISBULL_TARGET_STORE")
    os.environ["FDISBULL_TARGET_STORE"] = str(work / "target-objects")
    try:
        from fdisbull import dinopark_scenes as scenes
        require(callable(getattr(scenes, "observe_frame", None)), "Production observe_frame is unavailable")
        authored = {}
        for path in sorted((repo / "src/fdisbull/data").glob("dinopark*.json")):
            for name, pattern in json.loads(path.read_text()).get("scenes", {}).items():
                authored[path.name + ":" + name] = pattern
        require(authored, "No authored DinoPark predicates found")

        def ready(text):
            state["text"] = text
            report["native_session"] = {"run_id": text.debug.run_id, "metadata": text.debug.metadata}
            persist()

        route = [("office", True, "go bank"), ("bank", True, "go office"),
                 ("office", False, "go street"), ("street", True, "quit")]

        def command_reader():
            try:
                index = len(report["commands"])
                require(index < len(route), "Route exhausted; further input withheld")
                expected, measure, command = route[index]
                text = state["text"]
                require(text.current == expected, f"Expected {expected}, reached {text.current}; route stopped")
                if measure:
                    case = {"scene": expected}
                    report["cases"].append(case)
                    benchmark_case(scenes, text, case, args.iterations, event_state, authored)
                    persist()
                report["commands"].append({"scene": text.current, "command": command})
                return command
            except Exception as error:
                report["benchmark_error"] = {"type": type(error).__name__, "message": str(error)}
                persist()
                raise scenes.SceneInterrupted(str(error)) from error

        def output(*values, sep=" ", end="\n", **kwargs):
            report["route_output"].append(sep.join(map(str, values)) + end)

        restart = scenes.run_session(["--backend", str(backend), "--game-dir", str(game), "--work-dir", str(work)],
            command_reader=command_reader, output=output, on_ready=ready, on_event=event, on_spawn=spawned)
        require(restart is None, "Unexpected session restart request")
        require([c["scene"] for c in report["cases"]] == ["office", "bank", "street"] and
                all(c["status"] == "passed" for c in report["cases"]), "Not all three actual scene cases completed")
        require([c["command"] for c in report["commands"]] == ["go bank", "go office", "go street", "quit"],
                "Unexpected command route")
        session_receipt = json.loads((work / "receipt.json").read_text())
        require(session_receipt.get("ok") and session_receipt.get("complete") and session_receipt.get("source_unchanged"),
                "Production run_session did not complete its own receipt")
        report["run_session_receipt"] = {"path": str(work / "receipt.json"), "sha256": file_hash(work / "receipt.json"),
                                         "status": session_receipt["status"], "complete": session_receipt["complete"]}
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    finally:
        if previous_store is None:
            os.environ.pop("FDISBULL_TARGET_STORE", None)
        else:
            os.environ["FDISBULL_TARGET_STORE"] = previous_store
        if not work.exists():
            work.mkdir(mode=0o700)
        report["processes"] = [{"pid": p.pid, "exit_code": p.poll(), "reaped": p.poll() is not None} for p in processes]
        try:
            report["source_hashes_unchanged"] = all(file_hash(repo / name) == expected for name, expected in source_hashes.items())
            report["original_inventory_unchanged"] = inventory(game) == original_inventory
            if (work / "game").is_dir():
                report["private_game_inventory_unchanged"] = inventory(work / "game") == {
                    name: value for name, value in original_inventory.items() if not Path(name).name.upper().startswith("DINOSG.")}
            if (work / "scene.fdb").is_file() and report.get("native_session"):
                from fdisbull.target_storage import TargetStore
                with sqlite3.connect(f"file:{work / 'scene.fdb'}?mode=ro", uri=True) as connection:
                    row = connection.execute("SELECT evidence FROM debug_events WHERE run=? AND operation='close' ORDER BY sequence DESC LIMIT 1",
                                             (report["native_session"]["run_id"],)).fetchone()
                    report["native_close"] = json.loads(TargetStore(work / "target-objects").get(row[0])) if row else None
            require(report["source_hashes_unchanged"] and report["original_inventory_unchanged"] and
                    report.get("private_game_inventory_unchanged"), "Source or game-file hashes changed")
            require(len(processes) == 1 and all(p.poll() == 0 for p in processes) and
                    report.get("native_close", {}).get("process_reaped") is True,
                    "Single owned native process did not exit/reap cleanly with code zero")
        except Exception as error:
            report.update(status="failed", final_check_error={"type": type(error).__name__, "message": str(error)})
        persist()
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "cases_completed": sum(c.get("status") == "passed" for c in report["cases"])}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
