#!/usr/bin/env python3
"""Benchmark native DOS screenshot encodings on private original DinoPark frames.

The guest is launched from an exact private copy of DINOPARK.EXE and its assets.
Only bounded idle execution is used: this script sends no keys or mouse input and
does not invoke game actions, saves, purchases, or replay facilities. Captured
frames, project data, and reports are private outputs and must stay outside Git.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
import platform
import random
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ENCODINGS = ("png", "png-indexed", "rgba-zstd")
WARMUPS = 3


class BenchmarkError(RuntimeError):
    pass


def require(condition: object, message: str) -> None:
    if not condition:
        raise BenchmarkError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(root: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = {"kind": "symlink", "target": os.readlink(path)}
        elif path.is_file():
            data = path.read_bytes()
            result[str(path.relative_to(root))] = {"kind": "file", "size": len(data), "sha256": sha256(data)}
    return result


def median_p95(values: list[float | int]) -> dict[str, float]:
    require(bool(values), "Cannot summarize an empty sample")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {"median": statistics.median(ordered), "p95": ordered[index], "samples": len(ordered)}


def registers(debug: object) -> dict[str, object]:
    value = debug.call("state.get_registers")
    require(isinstance(value, dict), "state.get_registers returned a non-object")
    return value


def response_encoding(result: dict[str, object], requested: str) -> str:
    actual = result.get("encoding")
    wire_format = result.get("format", "png")
    if requested == "png-indexed":
        require(wire_format == "png" and actual in ("png-indexed", "png"),
                f"Unexpected indexed response format/encoding: {wire_format!r}/{actual!r}")
        if actual == "png":
            require(isinstance(result.get("fallback_reason"), str) and result["fallback_reason"],
                    "PNG fallback omitted fallback_reason")
        else:
            require("fallback_reason" not in result, "Indexed PNG unexpectedly reports a fallback")
    elif requested == "rgba-zstd":
        require(wire_format == "rgba-zstd" and actual in (None, "rgba-zstd"),
                f"Unexpected RGBA-zstd response format/encoding: {wire_format!r}/{actual!r}")
    else:
        # Legacy PNG responses intentionally omit `encoding` to preserve their
        # established wire shape. Accept an explicit `png` alias as well.
        require(wire_format == "png" and actual in (None, "png"),
                f"Unexpected PNG response format/encoding: {wire_format!r}/{actual!r}")
    return str(actual or wire_format)


def decode_response(result: dict[str, object], requested: str, zstd: object) -> tuple[bytes, bytes, str]:
    """Return (RGBA bytes, encoded bytes, actual encoding) with independent checks."""
    actual = response_encoding(result, requested)
    require(type(result.get("width")) is int and result["width"] > 0, "Invalid screenshot width")
    require(type(result.get("height")) is int and result["height"] > 0, "Invalid screenshot height")
    width, height = int(result["width"]), int(result["height"])
    if actual in ("png", "png-indexed"):
        key = "png_base64"
        require(isinstance(result.get(key), str), f"{actual} response omitted {key}")
        encoded = base64.b64decode(result[key], validate=True)
        require(encoded.startswith(b"\x89PNG\r\n\x1a\n"), "PNG signature mismatch")
        from PIL import Image
        import io
        with Image.open(io.BytesIO(encoded)) as image:
            image.load()
            require(image.size == (width, height), "PNG dimensions differ from response metadata")
            rgba = image.convert("RGBA").tobytes()
    else:
        require(result.get("pixel_format") == "RGBA8", "rgba-zstd pixel_format is not RGBA8")
        require(result.get("stride") == width * 4, "rgba-zstd stride mismatch")
        require(result.get("uncompressed_bytes") == width * height * 4, "rgba-zstd byte count mismatch")
        require(isinstance(result.get("data_base64"), str), "rgba-zstd response omitted data_base64")
        encoded = base64.b64decode(result["data_base64"], validate=True)
        rgba = zstd.ZstdDecompressor().decompress(encoded, max_output_size=width * height * 4)
        require(len(rgba) == width * height * 4, "Decompressed RGBA length mismatch")
        require(result.get("raw_sha256") == sha256(rgba), "rgba-zstd raw_sha256 mismatch")
    require(result.get("sha256") == sha256(encoded), "Encoded screenshot sha256 mismatch")
    return rgba, encoded, actual


def pixel_probes(rgba: bytes, width: int, height: int) -> dict[str, list[int]]:
    points = {"top_left": (0, 0), "top_right": (width - 1, 0), "center": (width // 2, height // 2),
              "bottom_left": (0, height - 1), "bottom_right": (width - 1, height - 1)}
    return {name: list(rgba[(y * width + x) * 4:(y * width + x) * 4 + 4])
            for name, (x, y) in points.items()}


def probe_points(width: int, height: int) -> list[list[int]]:
    return [[0, 0], [width - 1, 0], [width // 2, height // 2],
            [0, height - 1], [width - 1, height - 1]]


def sampled_rgb_match(rgba: bytes, width: int, points: list[list[int]], result: dict[str, object]) -> dict[str, object]:
    require(result.get("format") == "rgb-samples" and len(result.get("samples", [])) == len(points),
            "Native frame_probe returned incomplete samples")
    checks = []
    for point, sample in zip(points, result["samples"], strict=True):
        x, y = point
        expected = list(rgba[(y * width + x) * 4:(y * width + x) * 4 + 3])
        observed = sample.get("rgb")
        require([sample.get("x"), sample.get("y")] == point and observed == expected,
                f"frame_probe RGB disagrees with decoded frame at {point}: {observed!r} != {expected!r}")
        checks.append({"point": point, "rgb": observed, "matches_decoded_rgba": True})
    return {"frame_id": result.get("frame_id"), "samples": checks}


def database_counts(project: object) -> dict[str, int]:
    return {"total_changes": project.db.total_changes,
            "events": project.db.execute("SELECT count(*) FROM debug_events").fetchone()[0],
            "artifacts": project.db.execute("SELECT count(*) FROM debug_artifacts").fetchone()[0]}


@contextmanager
def direct_consumer_guards(debug: object, project: object, receipt: dict[str, object]):
    """Count forbidden side paths during direct calls; restore all guards on exit."""
    from PIL import Image

    original_open, original_save = Image.open, Image.Image.save
    active = {"encoding": None}
    counters = {encoding: {"image_open": 0, "image_save": 0, "event_calls": 0,
                           "artifact_calls": 0, "hook_calls": 0, "sqlite_write_attempts": 0}
                for encoding in ENCODINGS}
    receipt.update(counters=counters, database_before=database_counts(project))
    patches = []
    missing = object()

    def count(name: str) -> None:
        require(active["encoding"] in counters, "Direct guard observed a call outside a declared encoding")
        counters[active["encoding"]][name] += 1

    def guarded_open(*args, **kwargs):
        count("image_open")
        require(active["encoding"] != "rgba-zstd", "Direct RGBA-zstd consumer invoked Image.open")
        return original_open(*args, **kwargs)

    def guarded_save(*args, **kwargs):
        count("image_save")
        raise BenchmarkError("Direct consumer invoked Image.save")

    def forbid(obj: object, method: str, counter: str) -> None:
        old_value = vars(obj).get(method, missing)

        def blocked(*args, **kwargs):
            count(counter)
            raise BenchmarkError(f"Direct consumer invoked {method}")

        patches.append((obj, method, old_value))
        setattr(obj, method, blocked)

    allowed_sql = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_RECURSIVE}

    def authorize(action, arg1, arg2, database, trigger):
        if action in allowed_sql:
            return sqlite3.SQLITE_OK
        count("sqlite_write_attempts")
        return sqlite3.SQLITE_DENY

    try:
        Image.open, Image.Image.save = guarded_open, guarded_save
        forbid(debug, "_event", "event_calls")
        forbid(debug, "_artifact", "artifact_calls")
        forbid(debug, "_capture_with_hooks", "hook_calls")
        forbid(project, "_debug_artifact", "artifact_calls")
        project.db.set_authorizer(authorize)
        yield active, counters
    finally:
        project.db.set_authorizer(None)
        for obj, method, old_value in reversed(patches):
            if old_value is missing:
                delattr(obj, method)
            else:
                setattr(obj, method, old_value)
        Image.open, Image.Image.save = original_open, original_save
        receipt["database_after"] = database_counts(project)


def run_direct_phase(debug: object, project: object, frame_record: dict[str, object],
                     reference_rgba: bytes, reference_meta: dict[str, object],
                     wire_examples: dict[str, dict[str, object]], iterations: int,
                     all_samples: dict[str, dict[str, list[float]]]) -> None:
    """Time the complete public API call, including transport and pixel decode."""
    require(callable(getattr(debug, "frame_rgba", None)), "Source client lacks the direct frame_rgba API")
    record = {"samples": [], "guards": {}, "warmups_per_encoding": WARMUPS,
              "timing_scope": "whole debug.frame_rgba call; includes RPC, integrity checks and decode"}
    frame_record["direct_consumer"] = record
    before_registers = debug.registers()
    order_rng = random.Random(0xF12A + int(frame_record["index"]))
    with direct_consumer_guards(debug, project, record["guards"]) as (active, counters):
        for round_index in range(WARMUPS + iterations):
            order = list(ENCODINGS)
            order_rng.shuffle(order)
            results = {}
            for encoding in order:
                active["encoding"] = encoding
                started_ns = time.perf_counter_ns()
                frame = debug.frame_rgba(encoding=encoding)
                direct_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                require(type(frame.pixels) is bytes and frame.pixels == reference_rgba,
                        f"Direct {encoding} pixels differ from the paused PNG reference")
                require((frame.width, frame.height, frame.stride) ==
                        (reference_meta["width"], reference_meta["height"], reference_meta["width"] * 4),
                        f"Direct {encoding} frame layout differs from the reference")
                require(frame.sha256 == sha256(reference_rgba), "Direct consumer raw pixel SHA-256 mismatch")
                require(isinstance(frame.metadata, dict), "Direct consumer metadata is not an object")
                require(frame.metadata.get("sha256") == frame.sha256 and
                        frame.metadata.get("raw_sha256") == frame.sha256,
                        "Direct consumer metadata does not identify the raw RGBA digest")
                for key in ("width", "height", "frame_id", "mode_id", "captured_ticks"):
                    require(frame.metadata.get(key) == reference_meta[key],
                            f"Direct consumer changed same-frame {key}")
                transport = frame.metadata.get("transport")
                require(isinstance(transport, dict), "Direct consumer omitted transport metadata")
                require(transport.get("sha256") == wire_examples[encoding]["encoded_sha256"],
                        "Direct consumer encoded transport SHA differs from the same-frame wire response")
                if encoding == "rgba-zstd":
                    require(transport.get("raw_sha256") == frame.sha256,
                            "Direct RGBA-zstd transport raw digest differs from the pixel digest")
                results[encoding] = {"direct_ms": direct_ms, "raw_sha256": frame.sha256,
                    "stride": frame.stride, "rgba_bytes": len(frame.pixels), "full_rgba_equal": True,
                    "frame_metadata_equal": True, "transport": {key: value for key, value in transport.items()
                        if key not in ("data_base64", "png_base64")}}
                if round_index >= WARMUPS:
                    all_samples[encoding]["direct_consumer_ms"].append(direct_ms)
            if round_index >= WARMUPS:
                record["samples"].append({"round": round_index - WARMUPS + 1,
                                           "order": order, "results": results})
    guard_receipt = record["guards"]
    require(guard_receipt["database_before"] == guard_receipt["database_after"],
            "Direct consumer modified event/artifact counts or SQLite total_changes")
    for encoding, values in counters.items():
        for key in ("image_save", "event_calls", "artifact_calls", "hook_calls", "sqlite_write_attempts"):
            require(values[key] == 0, f"Direct {encoding} guard detected {key}")
        if encoding == "rgba-zstd":
            require(values["image_open"] == 0, "Direct RGBA-zstd consumer opened a PIL image")
    after_registers = debug.registers()
    require(after_registers == before_registers, "Direct consumer changed paused register state")
    record.update(registers_before=before_registers, registers_after=after_registers,
                  registers_identical=True, no_artifact_event_or_hook_calls=True,
                  zstd_no_image_open_or_save=True,
                  per_encoding={encoding: median_p95([sample["results"][encoding]["direct_ms"]
                      for sample in record["samples"]]) for encoding in ENCODINGS})


def selected_spawn_environment(pid: int) -> dict[str, str]:
    """Read only the two expected nonsecret launch variables, never dump env."""
    allow = {"SDL_AUDIODRIVER", "XDG_CONFIG_HOME"}
    proc_env = Path(f"/proc/{pid}/environ")
    if proc_env.is_file():
        entries = proc_env.read_bytes().split(b"\0")
        pairs = [entry.decode("utf-8", "replace") for entry in entries if entry]
    else:
        # macOS has no /proc. `ps` output is held in memory and filtered before
        # recording; no unselected environment values enter the receipt.
        completed = subprocess.run(["ps", "eww", "-p", str(pid)], check=True,
                                   capture_output=True, text=True, timeout=3)
        lines = completed.stdout.splitlines()
        line = lines[-1] if lines else ""
        selected = {}
        for key in allow:
            match = re.search(rf"(?:^|\s){re.escape(key)}=([^\s]+)(?=\s|$)", line)
            if match:
                selected[key] = match.group(1)
        require(selected.get("SDL_AUDIODRIVER") == "dummy",
                "Spawn environment does not prove the dummy audio driver")
        return selected
    selected: dict[str, str] = {}
    for item in pairs:
        key, sep, value = item.partition("=")
        if sep and key in allow:
            selected[key] = value
    require(selected.get("SDL_AUDIODRIVER") == "dummy", "Spawn environment does not prove the dummy audio driver")
    return selected


@contextmanager
def debugger_with_receipt(project: object, backend: Path, game: Path, on_spawn: object,
                          report: dict[str, object], spawned: list[object]):
    """Always retain the close event and observed exit, including failed runs."""
    debug = project.debugger(backend, game, version=1, _on_spawn=on_spawn)
    try:
        with debug:
            yield debug
    finally:
        session = report.get("session")
        run_id = session.get("run_id") if isinstance(session, dict) else debug.run_id
        try:
            row = project.db.execute(
                "SELECT evidence FROM debug_events WHERE run=? AND operation='close' ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            process = spawned[-1] if spawned else None
            exit_code = process.poll() if process is not None else None
            receipt = json.loads(row[0]) if row is not None else None
            if isinstance(session, dict):
                session["close_receipt"] = ({**receipt, "backend_exit_code": exit_code}
                                             if receipt is not None else None)
            report["native_exit"] = {"close_receipt_found": receipt is not None,
                                     "process_reaped": receipt.get("process_reaped") if receipt else None,
                                     "backend_exit_code": exit_code}
        except Exception as error:
            report["native_exit_error"] = {"type": type(error).__name__, "message": str(error)}


def check_output_path(path: Path, repo: Path) -> Path:
    path = path.expanduser().resolve()
    require(not path.exists(), f"--output must be a new directory: {path}")
    require(path != repo and repo not in path.parents, "--output must be outside the Git checkout")
    require(path.parent.is_dir(), "--output parent must already exist on the approved private volume")
    path.mkdir(mode=0o700)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executable", type=Path, required=True, help="native DOSBox-X agent backend")
    parser.add_argument("--game-dir", type=Path, required=True, help="private game copy containing the original executable/assets")
    parser.add_argument("--output", type=Path, required=True, help="new private output directory outside Git")
    parser.add_argument("--iterations", type=int, default=30, help="measured repetitions per encoding and frame")
    parser.add_argument("--guest-ms", type=int, default=15000, help="total bounded idle progression budget in guest milliseconds")
    parser.add_argument("--target", default="DINOPARK.EXE", help="executable filename in --game-dir")
    parser.add_argument("--frames", type=int, default=3, help="distinct naturally reached frames; minimum 3")
    parser.add_argument("--native-patch", type=Path, help="private native backend patch used to build --executable")
    args = parser.parse_args(argv)
    require(1 <= args.iterations <= 1000, "--iterations must be in 1..1000")
    require(1 <= args.guest_ms <= 60000, "--guest-ms must be in 1..60000")
    require(args.frames >= 3 and args.frames <= 10, "--frames must be in 3..10")
    require(Path(args.target).name == args.target and args.target.upper() == "DINOPARK.EXE",
            "--target must name the private original DINOPARK.EXE")

    repo = Path(__file__).resolve().parents[1]
    backend = args.executable.expanduser().resolve(strict=True)
    game = args.game_dir.expanduser().resolve(strict=True)
    source = (game / args.target).resolve(strict=True)
    require(backend.is_file() and os.access(backend, os.X_OK), "--executable must be executable")
    require(source.is_file() and source.parent == game, "--target must be a regular file directly inside --game-dir")
    output = check_output_path(args.output, repo)
    before_game = inventory(game)
    require(any(item.get("kind") == "file" for item in before_game.values()), "--game-dir has no files")
    original_target_hash = before_game[args.target].get("sha256") if args.target in before_game else None
    require(original_target_hash, "Original target hash could not be recorded")
    report_path = output / "report.json"
    report: dict[str, object] = {
        "format": "fdisbull-dos-screenshot-codec-benchmark-1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "machine": platform.machine(), "python": platform.python_version(),
        "backend": {"path": str(backend), "size": backend.stat().st_size, "sha256": sha256(backend.read_bytes())},
        "tested_identity": {},
        "private_game": {"path": str(game), "target": args.target, "inventory_before": before_game,
                         "target_sha256": original_target_hash},
        "configuration": {"iterations": args.iterations, "warmups_per_encoding_per_frame": WARMUPS,
                           "total_guest_budget_ms": args.guest_ms, "frames_requested": args.frames,
                           "encodings": list(ENCODINGS), "measure": True,
                           "direct_consumer": "whole frame_rgba call; randomized codec order",
                           "artifact_calls_per_encoding_per_frame": 5},
        "claim_boundary": "Bounded idle progression and read-only screenshot comparisons on this exact private DinoPark copy/backend. "
                          "No input or game action is sent. Results describe only sampled frames and this host/backend.",
        "frames": [], "timings": {},
    }

    def persist() -> None:
        temporary = report_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(report_path)

    old_store = os.environ.get("FDISBULL_TARGET_STORE")
    os.environ["FDISBULL_TARGET_STORE"] = str(output / "target-objects")
    all_samples: dict[str, dict[str, list[float]]] = {
        enc: {"native_encode_us": [], "rpc_ms": [], "decode_ms": [],
              "direct_consumer_ms": [], "artifact_ms": []}
        for enc in ENCODINGS
    }
    spawned: list[object] = []
    spawn_receipts: list[dict[str, object]] = []

    def on_spawn(process: object) -> None:
        spawned.append(process)
        arguments = list(process.args)
        environment = selected_spawn_environment(process.pid)
        expected_mute = all(("-set" in arguments and value in arguments)
                            for value in ("mixer nosound=true", "midi mididevice=none"))
        require(expected_mute, "Actual native spawn arguments do not include both audio mute settings")
        spawn_receipts.append({"pid": process.pid,
                               "selected_arguments": {"mixer_nosound": "mixer nosound=true" in arguments,
                                   "midi_none": "midi mididevice=none" in arguments,
                                   "agent_window": "-agent-window" in arguments},
                               "selected_environment": environment,
                               "audio_mute_verified": environment.get("SDL_AUDIODRIVER") == "dummy" and expected_mute})

    try:
        import zstandard
        from fdisbull.project import Project
        source_paths = [Path(__file__).resolve()] + sorted((repo / "src/fdisbull").rglob("*.py"))
        if (repo / "player").is_dir():
            source_paths += sorted((repo / "player").rglob("*.py"))
        source_hashes = {str(path.relative_to(repo)):
                         sha256(path.read_bytes()) for path in source_paths}
        identity_material = "\n".join(f"{name}:{digest}" for name, digest in sorted(source_hashes.items())).encode()
        report["tested_identity"] = {"benchmark_script_sha256": source_hashes["scripts/benchmark_dos_screenshot_codecs.py"],
            "client_sources": source_hashes, "client_source_count": len(source_hashes),
            "client_bundle_sha256": sha256(identity_material),
            "native_patch_path": str(args.native_patch.expanduser().resolve()) if args.native_patch else None,
            "native_patch_sha256": sha256(args.native_patch.expanduser().resolve(strict=True).read_bytes()) if args.native_patch else None,
            "native_executable_sha256": sha256(backend.read_bytes()),
            "game_executable_sha256": sha256(source.read_bytes())}
        with Project.create(output / "dinopark.fdb", source, load_segment=0x1000) as project:
            with debugger_with_receipt(project, backend, game, on_spawn, report, spawned) as debug:
                report["session"] = {"run_id": debug.run_id, "metadata": debug.metadata,
                                     "spawn": None}
                capabilities = debug.rpc.capabilities
                report["native_capabilities"] = capabilities
                advertised = capabilities.get("video", {}).get("screenshot_encodings") if isinstance(capabilities.get("video"), dict) else None
                require(isinstance(advertised, list) and set(ENCODINGS).issubset(set(advertised)),
                        f"Backend does not advertise all required screenshot encodings: {advertised!r}")
                require(capabilities.get("video", {}).get("pixel_probe") is True,
                        "Backend does not advertise native video.pixel_probe for independent pixel validation")
                report["session"]["spawn"] = spawn_receipts[-1] if spawn_receipts else None
                require(report["session"]["spawn"] and report["session"]["spawn"]["audio_mute_verified"],
                        "Native process spawn did not provide an auditable audio mute receipt")

                distinct_content: set[str] = set()
                milestones = sorted({min(args.guest_ms, value) for value in
                                     (250, 1000, 3000, 7000, 15000, 30000, 45000, args.guest_ms)})
                elapsed_target = 0
                for milestone in milestones:
                    delta_ms = milestone - elapsed_target
                    if delta_ms <= 0:
                        continue
                    run = debug.run(guest_ms=delta_ms, timeout_ms=60000, fast_forward=True)
                    require(run.get("outcome") == "guest_time" and not run.get("hook_hits"),
                            f"Bounded idle progression ended unexpectedly: {run!r}")
                    elapsed_target = milestone
                    is_final_milestone = milestone == args.guest_ms
                    # Reserve a sample slot for the requested budget endpoint so
                    # long runs include an actual late-game/title frame.
                    if len(report["frames"]) >= args.frames - 1 and not is_final_milestone:
                        continue
                    candidate = debug.call("video.screenshot", {"encoding": "png", "measure": True})
                    candidate_rgba, candidate_png, _ = decode_response(candidate, "png", zstandard)
                    candidate_meta = {key: candidate.get(key) for key in
                                      ("width", "height", "frame_id", "mode_id", "captured_ticks")}
                    content_sha = sha256(candidate_rgba)
                    content_is_new = content_sha not in distinct_content
                    if not content_is_new and not is_final_milestone:
                        continue
                    distinct_content.add(content_sha)
                    frame_index = len(report["frames"])
                    report["frames"].append({"index": frame_index + 1, "status": "running",
                        "progression": {"cumulative_guest_ms": elapsed_target, "run": run},
                        "frame": candidate_meta, "content_rgba_sha256": content_sha,
                        "content_is_new": content_is_new,
                        "color_count_rgba": len({candidate_rgba[offset:offset + 4]
                                                 for offset in range(0, len(candidate_rgba), 4)}),
                        "samples": []})
                    frame_record = report["frames"][-1]
                    reference_rgba = candidate_rgba
                    reference_png = candidate_png
                    reference_meta = candidate_meta
                    (output / f"frame-{frame_index + 1:02d}-reference.png").write_bytes(reference_png)
                    frame_registers_before = debug.registers()
                    points = probe_points(int(reference_meta["width"]), int(reference_meta["height"]))
                    native_probes = debug.frame_probe(points)
                    probe_receipt = sampled_rgb_match(reference_rgba, int(reference_meta["width"]), points, native_probes)
                    if native_probes.get("frame_id") is not None:
                        require(native_probes["frame_id"] == reference_meta["frame_id"],
                                "Native frame_probe did not sample the screenshot's frame_id")

                    order_rng = random.Random(0xD1A0 + frame_index)
                    first_response: dict[str, dict[str, object]] = {}
                    total_rounds = WARMUPS + args.iterations
                    for round_index in range(total_rounds):
                        order = list(ENCODINGS)
                        order_rng.shuffle(order)
                        round_results: dict[str, dict[str, object]] = {}
                        for encoding in order:
                            start = time.perf_counter_ns()
                            response = debug.call("video.screenshot", {"encoding": encoding, "measure": True})
                            rpc_ms = (time.perf_counter_ns() - start) / 1_000_000
                            require(isinstance(response, dict), "video.screenshot returned a non-object")
                            decode_start = time.perf_counter_ns()
                            rgba, encoded, actual = decode_response(response, encoding, zstandard)
                            decode_ms = (time.perf_counter_ns() - decode_start) / 1_000_000
                            metadata = {key: response.get(key) for key in
                                        ("width", "height", "frame_id", "mode_id", "captured_ticks")}
                            require(metadata == reference_meta, "Screenshot read changed frame/mode/ticks within the paused same-frame batch")
                            require(rgba == reference_rgba, f"{encoding} decoded pixels differ from the reference frame")
                            native_us = response.get("encode_us")
                            require(type(native_us) is int and native_us >= 0, "Measured screenshot omitted nonnegative encode_us")
                            if round_index == 0:
                                first_response[encoding] = {"response_metadata": metadata, "actual_encoding": actual,
                                    "fallback_reason": response.get("fallback_reason"), "encoded_sha256": sha256(encoded),
                                    "encoded_bytes": len(encoded), "rgba_sha256": sha256(rgba),
                                    "rgba_bytes": len(rgba), "pixel_probes": pixel_probes(rgba, int(metadata["width"]), int(metadata["height"]))}
                            round_results[encoding] = {"requested_encoding": encoding, "actual_encoding": actual,
                                "encode_us": native_us, "rpc_ms": rpc_ms, "decode_ms": decode_ms,
                                "response_json_bytes": len(json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode()),
                                "base64_chars": len(response.get("png_base64", response.get("data_base64", ""))),
                                "encoded_bytes": len(encoded), "metadata": metadata,
                                "rgba_sha256": sha256(rgba), "encoded_sha256": sha256(encoded)}
                            if round_index >= WARMUPS:
                                all_samples[encoding]["native_encode_us"].append(float(native_us))
                                all_samples[encoding]["rpc_ms"].append(rpc_ms)
                                all_samples[encoding]["decode_ms"].append(decode_ms)
                        if round_index >= WARMUPS:
                            frame_record["samples"].append({"round": round_index - WARMUPS + 1,
                                                             "order": order, "results": round_results})

                    run_direct_phase(debug, project, frame_record, reference_rgba, reference_meta,
                                     first_response, args.iterations, all_samples)
                    direct_probe = debug.frame_probe(points)
                    direct_probe_receipt = sampled_rgb_match(reference_rgba, int(reference_meta["width"]),
                                                             points, direct_probe)
                    require(direct_probe_receipt == probe_receipt,
                            "Native RGB probes changed during the direct consumer phase")
                    frame_record["direct_consumer"]["native_rgb_probe_equal"] = True

                    # Exercise the public source-to-canonical-artifact path in a
                    # separate phase. Keep its storage/transcode latency distinct.
                    artifact_samples: dict[str, list[dict[str, object]]] = {enc: [] for enc in ENCODINGS}
                    export_receipts: dict[str, dict[str, object]] = {}
                    for encoding in ENCODINGS:
                        for repetition in range(5):
                            unique_name = f"codec-frame-{frame_index + 1:02d}-{encoding}-artifact-{repetition + 1:02d}.png"
                            started_ns = time.perf_counter_ns()
                            artifact = debug.screenshot(unique_name, hooks=False, encoding=encoding)
                            artifact_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                            require(artifact.get("kind") == "screenshot" and artifact.get("name") == unique_name,
                                    "Public screenshot API did not store a uniquely named screenshot artifact")
                            stored = project.db.execute("SELECT data,sha256,metadata FROM debug_artifacts WHERE id=?",
                                                         (artifact["artifact"],)).fetchone()
                            require(stored is not None, "Screenshot artifact missing from project database")
                            png_bytes = bytes(stored["data"])
                            require(sha256(png_bytes) == stored["sha256"] == artifact.get("sha256"),
                                    "Stored artifact hash differs from its receipt")
                            from PIL import Image
                            import io
                            with Image.open(io.BytesIO(png_bytes)) as image:
                                image.load()
                                require(image.size == (reference_meta["width"], reference_meta["height"]),
                                        "Canonical artifact dimensions differ from reference")
                                stored_rgba = image.convert("RGBA").tobytes()
                            require(stored_rgba == reference_rgba,
                                    f"Stored canonical PNG pixels differ from reference for {encoding}")
                            stored_meta = json.loads(stored["metadata"])
                            for key in ("frame_id", "mode_id", "captured_ticks", "width", "height"):
                                require(stored_meta.get(key) == reference_meta[key],
                                        f"Stored artifact metadata mismatch for {key}")
                            sample = {"repetition": repetition + 1, "artifact_id": artifact["artifact"],
                                      "artifact_sha256": stored["sha256"], "canonical_png_bytes": len(png_bytes),
                                      "artifact_ms": artifact_ms, "rgba_sha256": sha256(stored_rgba),
                                      "full_rgba_equal": True, "frame_metadata_equal": True}
                            artifact_samples[encoding].append(sample)
                            all_samples[encoding]["artifact_ms"].append(artifact_ms)
                            if repetition == 0:
                                export_path = output / f"frame-{frame_index + 1:02d}-{encoding}-export.png"
                                exported = project.debug_export(artifact["artifact"], export_path)
                                export_bytes = export_path.read_bytes()
                                require(sha256(export_bytes) == exported.get("sha256") == stored["sha256"],
                                        "Exported artifact hash differs from stored artifact")
                                with Image.open(export_path) as image:
                                    image.load()
                                    require(image.convert("RGBA").tobytes() == reference_rgba,
                                            "Reopened exported artifact pixels differ from the reference")
                                export_receipts[encoding] = {"artifact_id": artifact["artifact"],
                                    "path": str(export_path), "sha256": sha256(export_bytes),
                                    "size": len(export_bytes), "reopened_rgba_equal": True}
                    after_registers = debug.registers()
                    require(after_registers == frame_registers_before,
                            "Register state changed during read-only screenshot codec/artifact calls")
                    final_probe = debug.frame_probe(points)
                    final_probe_receipt = sampled_rgb_match(reference_rgba, int(reference_meta["width"]), points, final_probe)
                    require(final_probe_receipt == probe_receipt,
                            "Native RGB probes changed during screenshot codec/artifact calls")
                    frame_record.update(status="passed", reference_png_sha256=sha256(reference_png),
                        native_rgb_probe=probe_receipt, registers_before=frame_registers_before,
                        registers_after=after_registers, encoding_examples=first_response,
                        artifact_samples=artifact_samples, artifact_exports=export_receipts,
                        read_only_check={"registers_identical": True, "frame_id_unchanged": True,
                                         "captured_ticks_unchanged": True, "mode_id_unchanged": True,
                                         "full_rgba_identical": True, "native_rgb_probes_identical": True})
                    persist()
                    if len(report["frames"]) == args.frames:
                        break
                require(len(distinct_content) >= 3 and len(report["frames"]) == args.frames,
                        f"Expected {args.frames} benchmark frames with at least 3 distinct contents; observed "
                        f"{len(report['frames'])} frames and {len(distinct_content)} distinct frame contents "
                        f"within {args.guest_ms} ms of bounded idle progression")
            exit_receipt = report.get("native_exit", {})
            require(exit_receipt.get("close_receipt_found") is True and exit_receipt.get("process_reaped") is True,
                    "Native backend close/process-reaped receipt was not verified")
            require(exit_receipt.get("backend_exit_code") == 0,
                    "Native backend did not exit cleanly with exit code zero")
        hashes_after = {str(path.relative_to(repo)): sha256(path.read_bytes()) for path in source_paths}
        report["tested_identity"]["source_hashes_unchanged"] = hashes_after == source_hashes
        require(hashes_after == source_hashes, "Measured Python source changed during the benchmark")
        require(sha256(backend.read_bytes()) == report["tested_identity"]["native_executable_sha256"],
                "Native executable changed during the benchmark")
        if args.native_patch:
            require(sha256(args.native_patch.expanduser().resolve(strict=True).read_bytes()) ==
                    report["tested_identity"]["native_patch_sha256"], "Native patch source changed during the benchmark")
        report["timings"] = {encoding: {measure: median_p95(values) for measure, values in measures.items()}
                             for encoding, measures in all_samples.items()}
        report["status"] = "passed"
    except KeyboardInterrupt:
        report.update(status="interrupted", error={"type": "KeyboardInterrupt", "message": "Benchmark interrupted"})
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    finally:
        if old_store is None:
            os.environ.pop("FDISBULL_TARGET_STORE", None)
        else:
            os.environ["FDISBULL_TARGET_STORE"] = old_store
        try:
            after_game = inventory(game)
            report["private_game"]["inventory_after"] = after_game
            report["private_game"]["unchanged"] = after_game == before_game
            if after_game != before_game and report.get("status") == "passed":
                report.update(status="failed", error={"type": "BenchmarkError", "message": "Private game copy changed during benchmark"})
        except Exception as error:
            report["private_game"]["inventory_after_error"] = {"type": type(error).__name__, "message": str(error)}
            if report.get("status") == "passed":
                report.update(status="failed", error={"type": type(error).__name__, "message": "Could not verify game-copy hashes after run"})
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        persist()
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "frames_completed": sum(frame.get("status") == "passed" for frame in report.get("frames", []))}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
