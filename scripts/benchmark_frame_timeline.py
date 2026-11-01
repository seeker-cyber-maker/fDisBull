#!/usr/bin/env python3
"""Bounded native full-state frame/input timeline comparison.

Run with the selected checkout's dependencies and PYTHONPATH=src::

    python scripts/benchmark_frame_timeline.py --backend /absolute/dosbox-x \
        --output /private/new-external-directory --trials 3 --frames 24

The same saved starting state and authored input plan serve manual Anchor
Stones, automatic timeline, and a pinned Anchor Stone plus timeline. All arms
retain full native state AND an image at the initial boundary and each frame.
Each trial also runs a separate unrecorded baseline with the same frame/input
work and no retained state history. Its one final PNG is verification only;
the baseline retains less information than the three recording modes.
Frame units are native completed-renderer-frame -> safe-fetch boundaries;
they are not a fixed 60 Hz clock. This script never downloads game assets.

The caller must admit bulk output storage before invoking this benchmark. Its
private output retains authored code, states, images, and a project database.
It performs no Git, network, installation, hosted CI, or release operations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import struct
import time


COM_ORIGIN = 0x100
MODULE_BYTES = 512
DATA_OFFSETS = {"count": 0x204, "sum": 0x206, "last": 0x208}
CONTROL_WORDS = (0x1e61, 0x3062, 0x2e63)  # BIOS scan/ASCII words for a, b, c.
EXPECTED = {"count": 3, "sum": 0x7d26, "last": 0x2e63}
CPU_FIELDS = ("cpu_mode", "general", "segments", "instruction_pointer", "flags")
MODES = ("manual_anchor_stones", "automatic_timeline", "anchor_plus_timeline")
MIB = 1024 * 1024

# Authored 16-bit COM, ORG 100h. The stack and BIOS are outside the file-backed
# span. No guest file writes, interrupt hooks, timers, or assets are involved.
#   push cs; pop ds; mov ax,13h; int 10h
#   mov ax,0a000h; mov es,ax; xor di,di
# poll: mov ah,1; int 16h; jz draw
#   xor ax,ax; int 16h; inc word [204h]; add [206h],ax; mov [208h],ax
# draw: mov al,[204h]; mov es:[di],al; jmp poll
FIXTURE_CODE = bytes.fromhex(
    "0e1fb81300cd10b800a08ec031ffb401cd16740f31c0cd16"
    "ff06040201060602a30802a00402268805ebe3"
)


def authored_com():
    """Return complete authored static bytes, also reusable by native tests."""
    module = bytearray(MODULE_BYTES)
    module[:len(FIXTURE_CODE)] = FIXTURE_CODE
    module[0x200 - COM_ORIGIN:0x204 - COM_ORIGIN] = b"FTL1"
    return bytes(module)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def frame_plan(frames):
    """Edges apply immediately before the transition with this zero-based index."""
    require(type(frames) is int and 16 <= frames <= 120, "frames must be in 16..120")
    return [
        {"frame": index, "edges": [{"key": key, "pressed": pressed}]}
        for index, key, pressed in (
            (0, "a", True), (2, "a", False), (6, "b", True),
            (8, "b", False), (12, "c", True), (14, "c", False),
        )
    ]


def expected_controls(completed):
    """Independent BIOS-key oracle after a completed frame transition."""
    words = [word for frame, word in zip((0, 6, 12), CONTROL_WORDS) if frame < completed]
    return {"count": len(words), "sum": sum(words) & 0xffff,
            "last": words[-1] if words else 0}


def expected_module(controls):
    data = bytearray(authored_com())
    for name, offset in DATA_OFFSETS.items():
        struct.pack_into("<H", data, offset - COM_ORIGIN, controls[name])
    return bytes(data)


def observe(session):
    registers = session.registers()
    address = f"{session.dos['load_segment']:04x}:{COM_ORIGIN:04x}"
    ram = bytes.fromhex(session.memory(address, length=MODULE_BYTES)["hex"])
    require(len(ram) == MODULE_BYTES, "Incomplete authored mapped-RAM observation")
    controls = {name: struct.unpack_from("<H", ram, offset - COM_ORIGIN)[0]
                for name, offset in DATA_OFFSETS.items()}
    return {"cpu": {key: registers[key] for key in CPU_FIELDS}, "ram": ram,
            "controls": controls}


def check_oracle(snapshot, completed):
    expected = expected_controls(completed)
    require(snapshot["cpu"]["cpu_mode"] == "real", "Authored fixture left real mode")
    require(snapshot["controls"] == expected,
            f"Authored key-consumption oracle differs at frame {completed}: "
            f"{snapshot['controls']} != {expected}")
    require(snapshot["ram"] == expected_module(expected),
            "Authored code or non-control mapped RAM changed")


def observation_record(snapshot):
    return {"cpu": snapshot["cpu"], "mapped_ram_bytes": len(snapshot["ram"]),
            "mapped_ram_sha256": digest(snapshot["ram"]), "controls": snapshot["controls"]}


def equal_state(left, right):
    result = {"cpu_equal": left["cpu"] == right["cpu"],
              "all_mapped_ram_equal": left["ram"] == right["ram"]}
    require(all(result.values()), "CPU or authored mapped RAM differs at the same frame boundary")
    return result


def new_output(value):
    path = Path(value).expanduser().absolute()
    require(not path.exists(), "--output must name a new directory")
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "--output must have no symlink ancestry")
        bare = ((parent / "HEAD").is_file() and (parent / "objects").is_dir()
                and (parent / "refs").is_dir())
        require(not (parent / ".git").exists() and not (parent / ".git").is_symlink()
                and not bare, "--output must be outside Git")
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def serializable(value):
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def write_report(path, report):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(serializable(report), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def inventory(project):
    return {item["id"]: item for item in project.debug_artifacts()["artifacts"]}


def artifact_growth(before, after, *, exclude=()):
    added = [item for key, item in after.items() if key not in before and key not in exclude]
    return {"new_artifacts": len(added), "new_artifact_kinds": dict(Counter(i["kind"] for i in added)),
            "durable_state_bytes": sum(i["size"] for i in added if i["kind"] == "state"),
            "durable_image_bytes": sum(i["size"] for i in added if i["kind"] == "screenshot"),
            "durable_all_artifact_bytes": sum(i["size"] for i in added),
            "excluded_verification_export_artifacts": len(exclude),
            "accounting": "Logical payload sizes; not filesystem allocated bytes or resident memory."}


class Meter:
    """Count explicit Python API calls and underlying native RPC dispatches.

    Counters do not measure model turns. Native RPC times include transport and
    serialization; they do not include Python manifest checks or persistence.
    Every public call is assigned a phase so verification/setup stay separate.
    """
    def __init__(self, session, result=None):
        self.session = session
        self.result = result
        self.operations = []
        self.rpc_samples = []
        self.phase = "unclassified"
        self.original = session.rpc.call

    def __enter__(self):
        self.started = time.perf_counter_ns()
        def dispatch(method, *args, **kwargs):
            started = time.perf_counter_ns()
            try:
                return self.original(method, *args, **kwargs)
            finally:
                self.rpc_samples.append({"method": method, "phase": self.phase,
                                         "elapsed_ns": time.perf_counter_ns() - started})
        self.session.rpc.call = dispatch
        return self

    def __exit__(self, *unused):
        self.session.rpc.call = self.original
        if self.result is not None:
            self.result["arm_wall_ns"] = time.perf_counter_ns() - self.started
            self.result["arm_wall_scope"] = ("Includes setup, alignment, verification, status, cleanup, "
                "and durable report rewrites. Different report-write cadence makes this a diagnostic total, "
                "not the equal-workload performance comparison; use summed public API timings.")
            self.result["measurements"] = self.report()
            self.result["backend_rpc_samples"] = self.rpc_samples
            self.result["caller_operation_samples"] = self.operations
            self.result["native_component_timings"] = self.components()

    def call(self, phase, name, function, *args, **kwargs):
        previous = self.phase
        self.phase = phase
        started = time.perf_counter_ns()
        try:
            return function(*args, **kwargs)
        finally:
            self.operations.append({"phase": phase, "method": name,
                                    "elapsed_ns": time.perf_counter_ns() - started})
            self.phase = previous

    def report(self):
        phases = sorted({sample["phase"] for sample in self.operations + self.rpc_samples})
        result = {}
        for phase in phases:
            calls = [s for s in self.operations if s["phase"] == phase]
            rpc = [s for s in self.rpc_samples if s["phase"] == phase]
            result[phase] = {"caller_api_calls": len(calls),
                             "caller_methods": dict(Counter(s["method"] for s in calls)),
                             "caller_elapsed_ns": sum(s["elapsed_ns"] for s in calls),
                             "backend_rpc_dispatches": len(rpc),
                             "backend_rpc_methods": dict(Counter(s["method"] for s in rpc)),
                             "backend_rpc_elapsed_ns": sum(s["elapsed_ns"] for s in rpc)}
        return result

    def components(self):
        methods = {"capture": {"state.save", "video.screenshot"},
                   "advance": {"frame.step"}, "restore": {"state.load"}}
        recording = {"capture", "advance", "input", "pin", "advance_with_automatic_capture"}
        result = {"scope": "Native RPC wall time, including transport; Python host work is excluded.",
                  "recording_public_call_wall_ns": sum(s["elapsed_ns"] for s in self.operations
                                                        if s["phase"] in recording),
                  "recording_caller_api_calls": sum(s["phase"] in recording for s in self.operations),
                  "recording_backend_rpc_dispatches": sum(s["phase"] in recording for s in self.rpc_samples)}
        for component, names in methods.items():
            phases = recording if component != "restore" else {"restore"}
            samples = [s for s in self.rpc_samples if s["phase"] in phases and s["method"] in names]
            result[component + "_rpc_elapsed_ns"] = sum(s["elapsed_ns"] for s in samples)
            result[component + "_rpc_dispatches"] = len(samples)
        return result


def state_ref(saved):
    return {key: saved[key] for key in ("artifact", "sha256", "size")}


def measure_manual_capture(session, meter, name):
    state = meter.call("capture", "save_anchor_stone", session.save_anchor_stone,
                       name + ".sav", max_bytes=8 * MIB)
    image = meter.call("capture", "screenshot", session.screenshot, name + ".png", hooks=False)
    return {"state": state_ref(state), "image": state_ref(image)}


def run_inputs(session, meter, plan, frames, timeout_ms, *, phase="resume_verification"):
    edges = {item["frame"]: item["edges"] for item in plan}
    for index in range(frames):
        if index in edges:
            meter.call(phase, "frame_inputs", session.frame_inputs, edges[index])
        result = meter.call(phase, "advance_frames", session.advance_frames,
                            frames=1, timeout_ms=timeout_ms)
        require(isinstance(result, dict), "Frame advance did not return a receipt")


def run_unrecorded_baseline(project, session, initial_artifact, initial, trial_number,
                            frames, plan, timeout_ms, persist, result):
    """Same forward work without history, per-frame capture, or per-frame reads."""
    result.update(status="running", history_state_captures=0, history_images=0,
                  retained_history_points=0, _snapshots={})
    with Meter(session, result) as meter:
        meter.call("setup", "load_anchor_stone", session.load_anchor_stone, initial_artifact)
        equal_state(meter.call("verification", "observe", observe, session), initial)
        result["common_start_alignment"] = meter.call("alignment", "advance_frames", session.advance_frames,
                                                      frames=1, timeout_ms=timeout_ms)
        require(result["common_start_alignment"].get("completed_frames") == 1,
                "Unrecorded baseline S0 alignment was incomplete")
        aligned = meter.call("verification", "observe", observe, session)
        check_oracle(aligned, 0)
        result["_snapshots"][0] = aligned
        result["aligned_initial_state"] = observation_record(aligned)
        before = inventory(project)
        edges = {item["frame"]: item["edges"] for item in plan}
        receipts = []
        for index in range(frames):
            if index in edges:
                meter.call("input", "frame_inputs", session.frame_inputs, edges[index])
            receipt = meter.call("advance", "advance_frames", session.advance_frames,
                                 frames=1, timeout_ms=timeout_ms)
            require(receipt.get("completed_frames") == 1, "Unrecorded frame advancement was incomplete")
            receipts.append(receipt)
        result["frame_receipts"] = receipts
        endpoint = meter.call("verification", "observe", observe, session)
        check_oracle(endpoint, frames)
        result["_snapshots"][frames] = endpoint
        result["endpoint"] = observation_record(endpoint)
        image = meter.call("verification", "screenshot", session.screenshot,
                           f"t{trial_number}-unrecorded-endpoint.png", hooks=False)
        result["endpoint_image"] = state_ref(image)
        result["storage_after_forward_work"] = artifact_growth(
            before, inventory(project), exclude=[image["artifact"]])
        result["verification_image_bytes"] = image["size"]
        result["retained_information"] = (
            "No per-frame native states or images. One final PNG and initial/final CPU/RAM reads are verification only. "
            "The common seed Anchor belongs to shared setup and is excluded from every arm.")
        result["retry_loop_cost"] = baseline_retry_cost(meter)
        result["status"] = "passed"
        persist()


def baseline_retry_cost(meter):
    """Common seed load + alignment + forward input/frame work; no verification."""
    phases = {"setup", "alignment", "input", "advance"}
    calls = [sample for sample in meter.operations if sample["phase"] in phases]
    rpc = [sample for sample in meter.rpc_samples if sample["phase"] in phases]
    forward = {"input", "advance"}
    return {"scope": "One seed-Anchor load, one S0 alignment frame, and the fixed input/frame plan; verification and report IO excluded.",
            "public_call_wall_ns": sum(sample["elapsed_ns"] for sample in calls),
            "caller_api_calls": len(calls), "backend_rpc_dispatches": len(rpc),
            "forward_public_call_wall_ns": sum(sample["elapsed_ns"] for sample in calls if sample["phase"] in forward),
            "forward_caller_api_calls": sum(sample["phase"] in forward for sample in calls),
            "forward_backend_rpc_dispatches": sum(sample["phase"] in forward for sample in rpc)}


def run_mode(project, session, initial_artifact, initial, mode, trial_number,
             frames, plan, timeout_ms, persist, result):
    """Run an arm. Validation is outside timed capture/advance/restore phases."""
    result.update(status="running", mode=mode, points=[], restores=[], _snapshots={})
    verification_image_ids = []
    with Meter(session, result) as meter:
        meter.call("setup", "load_anchor_stone", session.load_anchor_stone, initial_artifact)
        equal_state(meter.call("verification", "observe", observe, session), initial)
        # Native load deliberately invalidates its completed-frame cache. All
        # arms use the same explicit, unmeasured one-frame alignment to define
        # S0. Never silently advance only one arm to obtain an image.
        result["common_start_alignment"] = meter.call("alignment", "advance_frames", session.advance_frames,
                                                      frames=1, timeout_ms=timeout_ms)
        require(result["common_start_alignment"].get("completed_frames") == 1,
                "Common start frame alignment was incomplete")
        aligned = meter.call("alignment", "observe", observe, session)
        check_oracle(aligned, 0)
        result["aligned_initial_state"] = observation_record(aligned)
        result["_snapshots"][0] = aligned
        before = inventory(project)
        points = result["points"]
        if mode == MODES[0]:
            points.append(measure_manual_capture(session, meter, f"t{trial_number}-manual-0"))
            result["initial_image"] = points[0]["image"]
            edges = {item["frame"]: item["edges"] for item in plan}
            for index in range(frames):
                if index in edges:
                    meter.call("input", "frame_inputs", session.frame_inputs, edges[index])
                receipt = meter.call("advance", "advance_frames", session.advance_frames,
                                     frames=1, timeout_ms=timeout_ms)
                require(receipt.get("completed_frames") == 1, "Manual frame advancement was incomplete")
                result.setdefault("frame_receipts", []).append(receipt)
                points.append(measure_manual_capture(
                    session, meter, f"t{trial_number}-manual-{index + 1}"))
                if index + 1 in (frames - 1, frames - 4, frames):
                    snapshot = meter.call("verification", "observe", observe, session)
                    check_oracle(snapshot, index + 1)
                    result["_snapshots"][index + 1] = snapshot
                persist()
            result["capture_accounting"] = {
                "cumulative_captures": len(points), "retained_points": len(points),
                "cumulative_state_bytes": sum(p["state"]["size"] for p in points),
                "cumulative_image_bytes": sum(p["image"]["size"] for p in points),
                "ring_retained_bytes": None,
                "retained_logical_bytes": sum(p[k]["size"] for p in points for k in ("state", "image")),
                "retention": "Caller retains every durable Anchor Stone and image; no ring."}
            result["point_selection_bookkeeping"] = {
                "caller_state_artifact_ids_retained": len(points),
                "caller_image_artifact_ids_retained": len(points),
                "caller_frame_to_artifact_mappings": len(points),
                "restore_target_selections": 3,
                "target_selection": "Caller indexes the saved frame-to-Anchor mapping."}
            endpoint_image = points[-1]["image"]
        else:
            started = meter.call("capture", "timeline_start", session.timeline_start,
                                 max_frames=frames, max_bytes=64 * MIB,
                                 max_state_bytes=8 * MIB, max_image_bytes=2 * MIB,
                                 max_captures=4096)
            result["timeline_start"] = started
            initial_image = meter.call("verification", "timeline_image", session.timeline_image,
                                       f"t{trial_number}-{mode}-initial.png")
            result["initial_image"] = state_ref(initial_image)
            verification_image_ids.append(initial_image["artifact"])
            if mode == MODES[2]:
                pinned = meter.call("pin", "timeline_pin", session.timeline_pin,
                                    f"t{trial_number}-coarse-anchor.sav")
                result["pinned_anchor"] = pinned
            advanced = meter.call("advance_with_automatic_capture", "timeline_advance",
                                  session.timeline_advance, frames=frames, inputs=plan,
                                  timeout_ms=timeout_ms)
            result["timeline_advance"] = advanced
            require(advanced.get("completed_frames") == frames, "Automatic frame advancement was incomplete")
            status = meter.call("status", "timeline_status", session.timeline_status)
            result["recorded_timeline_status"] = status
            # The raw receipt remains authoritative. Normalized accounting is
            # populated by the public timeline-accounting adapter below.
            result["capture_accounting"] = timeline_accounting(status)
            result["point_selection_bookkeeping"] = {
                "caller_state_artifact_ids_retained": int(mode == MODES[2]),
                "caller_image_artifact_ids_retained": 0,
                "caller_frame_to_artifact_mappings": 0,
                "restore_target_selections": 3,
                "target_selection": "Relative frame count, managed by the timeline.",
                "pinned_coarse_fallback": mode == MODES[2]}
            # Export one cached image only for verification; this adds a
            # durable artifact, but performs no native capture.
            endpoint_image = meter.call("verification", "timeline_image", session.timeline_image,
                                        f"t{trial_number}-{mode}-endpoint.png")
            verification_image_ids.append(endpoint_image["artifact"])
        result["storage_after_record"] = artifact_growth(before, inventory(project), exclude=verification_image_ids)
        result["verification_cached_image_exports"] = verification_image_ids
        endpoint = meter.call("verification", "observe", observe, session)
        check_oracle(endpoint, frames)
        result["_snapshots"][frames] = endpoint
        result["endpoint"] = observation_record(endpoint)
        result["endpoint_image"] = state_ref(endpoint_image)
        previous = 0
        for depth in (1, 4, frames):
            relative = depth - previous
            target = frames - depth
            if mode == MODES[0]:
                selected = points[target]["state"]
                restored = meter.call("restore", "load_anchor_stone", session.load_anchor_stone,
                                      selected["artifact"])
                require(restored["sha256"] == selected["sha256"], "Manual restore used different state bytes")
            else:
                restored = meter.call("restore", "timeline_rewind", session.timeline_rewind,
                                      frames=relative)
                require(restored.get("rewound_frames") == relative
                        and restored.get("timeline", {}).get("cursor") == target,
                        "Timeline rewind selected the wrong logical frame")
            snapshot = meter.call("verification", "observe", observe, session)
            check_oracle(snapshot, target)
            if target in result["_snapshots"]:
                equal_state(snapshot, result["_snapshots"][target])
            result["_snapshots"][target] = snapshot
            result["restores"].append({"relative_frames": relative,
                "cumulative_depth": depth, "target_frame": target,
                "elapsed_ns": next(s["elapsed_ns"] for s in reversed(meter.operations) if s["phase"] == "restore"),
                "result": restored, "observation": observation_record(snapshot)})
            previous = depth
            persist()
        if mode != MODES[0]:
            result["timeline_before_stop"] = meter.call("status", "timeline_status", session.timeline_status)
            meter.call("cleanup", "timeline_stop", session.timeline_stop)
        # Identical replay after a genuine full-state rewind to point zero.
        # It is a separate verification phase with no new per-frame capture.
        run_inputs(session, meter, plan, frames, timeout_ms)
        repeat = meter.call("resume_verification", "observe", observe, session)
        check_oracle(repeat, frames)
        result["resume_repeat"] = {"equality": equal_state(repeat, endpoint),
            "endpoint": observation_record(repeat)}
        repeat_image = meter.call("resume_verification", "screenshot", session.screenshot,
                                  f"t{trial_number}-{mode}-repeat.png", hooks=False)
        require(repeat_image["sha256"] == endpoint_image["sha256"],
                "Resumed frame/input replay changed the endpoint PNG")
        result["resume_repeat"]["png_sha256_equal"] = True
        if mode == MODES[2]:
            pinned = result["pinned_anchor"]
            fallback = meter.call("coarse_fallback", "load_anchor_stone", session.load_anchor_stone,
                                  pinned["artifact"])
            result["coarse_fallback"] = {"restore": fallback,
                "initial_state_equality": equal_state(
                    meter.call("verification", "observe", observe, session), aligned)}
        result["measurements"] = meter.report()
        result["backend_rpc_samples"] = meter.rpc_samples
        result["caller_operation_samples"] = meter.operations
        result["storage_after_verification"] = artifact_growth(before, inventory(project))
        result["status"] = "passed"
        persist()


def timeline_accounting(status):
    """Validate public accounting instead of silently estimating missing values."""
    # Kept in one small seam because the new public receipt is versioned with
    # the implementation. Required names deliberately fail clearly on drift.
    required = ("captures_used", "state_bytes_used", "image_bytes_used", "input_bytes_used", "bytes_used",
                "state_payload_bytes", "image_payload_bytes", "points")
    require(all(key in status for key in required),
            "Timeline status lacks benchmark accounting fields: "
            + ", ".join(key for key in required if key not in status))
    require(isinstance(status["points"], list), "Timeline points must be a list")
    require(status["captures_used"] == len(status["points"]),
            "Equal-workload recording unexpectedly evicted points or discarded a branch")
    state = sum(point["state_bytes"] for point in status["points"])
    image = sum(point["image_bytes"] for point in status["points"])
    state_payload = sum(point["checkpoint_size"] for point in status["points"])
    image_payload = sum(point["image_size"] for point in status["points"])
    require(state == status["state_bytes_used"] and image == status["image_bytes_used"]
            and state + image + status["input_bytes_used"] == status["bytes_used"]
            and state_payload == status["state_payload_bytes"]
            and image_payload == status["image_payload_bytes"],
            "Timeline ring accounting is inconsistent with its retained points")
    return {"cumulative_captures": status["captures_used"],
            "retained_points": len(status["points"]),
            "cumulative_state_bytes": state_payload,
            "cumulative_image_bytes": image_payload,
            "cumulative_state_bytes_including_metadata": state,
            "cumulative_image_bytes_including_metadata": image,
            "cumulative_bytes_derivation": "All captures retained; no eviction or branch during recording.",
            "ring_retained_bytes": status["bytes_used"],
            "ring_input_journal_bytes": status["input_bytes_used"],
            "retained_logical_bytes": status["bytes_used"],
            "retention": "In-memory full-state/image ring; durable pins are reported separately."}


def trial_comparison(trial, frames):
    modes = trial["modes"]
    baseline = modes[MODES[0]]
    checks = {}
    unrecorded = trial["unrecorded_baseline"]
    checks["unrecorded_baseline"] = {str(point): equal_state(
        baseline["_snapshots"][point], unrecorded["_snapshots"][point]) for point in (0, frames)}
    require(unrecorded["endpoint_image"]["sha256"] == baseline["endpoint_image"]["sha256"],
            "Unrecorded baseline produced a different final PNG")
    checks["unrecorded_baseline"]["endpoint_png_equal"] = True
    for mode in MODES[1:]:
        arm = modes[mode]
        checks[mode] = {str(point): equal_state(baseline["_snapshots"][point], arm["_snapshots"][point])
                        for point in (0, frames - 4, frames - 1, frames)}
        require(arm["endpoint_image"]["sha256"] == baseline["endpoint_image"]["sha256"],
                "Different modes produced different final PNG bytes")
        require(arm["initial_image"]["sha256"] == baseline["initial_image"]["sha256"],
                "Different modes produced different aligned initial PNG bytes")
        checks[mode]["aligned_initial_png_equal"] = True
        checks[mode]["endpoint_png_equal"] = True
        require(arm["capture_accounting"]["cumulative_captures"] == frames + 1,
                "Modes did not capture the same number of full-state/image points")
    return checks


def overhead_against_unrecorded(trial):
    """Recording overhead for the same forward plan; restores stay separate."""
    baseline = trial["unrecorded_baseline"]
    base_ns = baseline["retry_loop_cost"]["forward_public_call_wall_ns"]
    base_native = baseline["native_component_timings"]["advance_rpc_elapsed_ns"]
    require(base_ns > 0 and base_native > 0, "Unrecorded baseline timing denominator must be positive")
    comparisons = {}
    for mode, arm in trial["modes"].items():
        components = arm["native_component_timings"]
        forward_ns = components["recording_public_call_wall_ns"]
        comparisons[mode] = {
            "unrecorded_forward_public_call_wall_ns": base_ns,
            "recording_forward_public_call_wall_ns": forward_ns,
            "recording_overhead_ns": forward_ns - base_ns,
            "recording_to_unrecorded_forward_ratio": forward_ns / base_ns,
            "native_frame_advance_rpc_ratio": components["advance_rpc_elapsed_ns"] / base_native,
            "restores_excluded": True,
            "information_difference": "Baseline retains zero history snapshots; recording mode retains initial + every completed frame, with PNGs. This measures recording overhead, not equal-information speedup."}
    return comparisons


def summary(trials):
    complete = [trial for trial in trials if trial["status"] == "passed"]
    result = {"completed_trials": len(complete), "modes": {}}
    if complete:
        baselines = [trial["unrecorded_baseline"] for trial in complete]
        result["unrecorded_baseline"] = {"samples": len(baselines), "history_state_captures": 0,
            "retained_history_points": 0, "forward_public_call_wall_median_ns": statistics.median(
                arm["retry_loop_cost"]["forward_public_call_wall_ns"] for arm in baselines),
            "retry_loop_public_call_wall_median_ns": statistics.median(
                arm["retry_loop_cost"]["public_call_wall_ns"] for arm in baselines),
            "forward_caller_api_calls_median": statistics.median(
                arm["retry_loop_cost"]["forward_caller_api_calls"] for arm in baselines),
            "forward_backend_rpc_dispatches_median": statistics.median(
                arm["retry_loop_cost"]["forward_backend_rpc_dispatches"] for arm in baselines),
            "native_frame_advance_rpc_median_ns": statistics.median(
                arm["native_component_timings"]["advance_rpc_elapsed_ns"] for arm in baselines)}
    for mode in MODES:
        arms = [trial["modes"][mode] for trial in complete]
        if not arms:
            continue
        phases = sorted({phase for arm in arms for phase in arm["measurements"]})
        result["modes"][mode] = {"samples": len(arms), "phase_medians": {
            phase: {key: statistics.median(arm["measurements"].get(phase, {}).get(key, 0) for arm in arms)
                    for key in ("caller_api_calls", "caller_elapsed_ns", "backend_rpc_dispatches")}
            for phase in phases}, "native_component_medians": {
                key: statistics.median(arm["native_component_timings"][key] for arm in arms)
                for key in ("recording_public_call_wall_ns", "recording_caller_api_calls",
                            "recording_backend_rpc_dispatches", "capture_rpc_elapsed_ns",
                            "advance_rpc_elapsed_ns", "restore_rpc_elapsed_ns")}}
        result["modes"][mode]["restore_medians_by_depth"] = [
            {"cumulative_depth": arm_sample["cumulative_depth"],
             "relative_frames": arm_sample["relative_frames"],
             "elapsed_ns": statistics.median(arm["restores"][index]["elapsed_ns"] for arm in arms)}
            for index, arm_sample in enumerate(arms[0]["restores"])]
        result["modes"][mode]["capture_accounting_medians"] = {
            key: statistics.median(arm["capture_accounting"][key] for arm in arms)
            for key in ("cumulative_captures", "retained_points", "cumulative_state_bytes", "cumulative_image_bytes")}
        result["modes"][mode]["ring_retained_bytes_median"] = (
            statistics.median(arm["capture_accounting"]["ring_retained_bytes"] for arm in arms)
            if mode != MODES[0] else None)
        result["modes"][mode]["recording_to_unrecorded_forward_ratio_median"] = statistics.median(
            trial["forward_recording_overhead"][mode]["recording_to_unrecorded_forward_ratio"] for trial in complete)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--output", required=True, help="New private external directory; storage admission is caller-owned")
    parser.add_argument("--trials", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--frames", type=int, choices=range(16, 121), default=24)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args(argv)
    require(1 <= args.timeout_ms <= 600000, "--timeout-ms must be in 1..600000")
    backend = args.backend.expanduser().resolve(strict=True)
    require(backend.is_file() and os.access(backend, os.X_OK), "--backend must name an executable file")
    output = new_output(args.output)
    report_path = output / "report.json"
    report = {"format": "fdisbull-frame-timeline-benchmark-1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
        "backend": {"path": str(backend), "size": backend.stat().st_size,
                    "sha256": digest(backend.read_bytes())},
        "configuration": {"trials": args.trials, "frames": args.frames,
                          "timeout_ms": args.timeout_ms, "input_plan": frame_plan(args.frames)},
        "claim_boundary": "Authored-fixture microbenchmark. Three recording modes retain equal full-state/image histories. "
            "The separate unrecorded baseline performs the same frame/input work with zero retained history snapshots and one verification PNG. "
            "Native completed renderer frames ending at safe fetch; variable cadence, not fixed 60 Hz. "
            "Caller API operations are not model turns. Logical sizes are not physical allocation. "
            "Cold startup, verification, status, and cleanup costs are reported separately. "
            "Every arm restores the same seed Anchor then explicitly aligns one completed frame to S0; "
            "alignment costs are separate and aligned CPU/RAM/PNG must match across modes. "
            "Native RPC phase costs exclude Python manifests, persistence, and other host overhead. "
            "No RNG policy, Windows/Wine, arbitrary-game, or whole-machine equivalence qualification.",
        "trials": []}
    persist = lambda: write_report(report_path, report)
    previous_store = os.environ.get("FDISBULL_TARGET_STORE")
    os.environ["FDISBULL_TARGET_STORE"] = str(output / "target-objects")
    try:
        persist()
        from fdisbull.project import Project
        import fdisbull.debugger as debugger_module
        repo = Path(__file__).resolve().parents[1]
        require(Path(debugger_module.__file__).resolve() == repo / "src/fdisbull/debugger.py",
                "Imported debugger is not the benchmark checkout")
        report["implementation_files"] = {str(path.relative_to(repo)): digest(path.read_bytes())
            for path in (Path(__file__).resolve(), repo / "src/fdisbull/debugger.py",
                         repo / "src/fdisbull/debug_timeline.py", repo / "src/fdisbull/keyboard_input.py")
            if path.is_file()}
        guest = output / "guest"
        guest.mkdir(mode=0o700)
        binary = guest / "TIMELINE.COM"
        data = authored_com()
        binary.write_bytes(data)
        report["fixture"] = {"source": "Static authored COM in benchmark_frame_timeline.py",
            "bytes": len(data), "sha256": digest(data), "data_guest_offsets": DATA_OFFSETS,
            "expected_final_controls": EXPECTED, "no_guest_file_writes": True}
        cold_start = time.perf_counter_ns()
        with Project.create(output / "benchmark.fdb", binary, image="com") as project:
            with project.debugger(backend, guest, version=1) as session:
                for name in ("advance_frames", "frame_inputs", "timeline_start", "timeline_advance",
                             "timeline_rewind", "timeline_status", "timeline_pin", "timeline_image", "timeline_stop"):
                    require(callable(getattr(session, name, None)), f"Required API is unavailable: {name}")
                require(session.rpc.capabilities.get("frame_timeline"), "Backend lacks native frame timeline support")
                require(session.rpc.capabilities.get("save_states"), "Backend lacks native save states")
                session.advance_frames(frames=3, timeout_ms=args.timeout_ms)
                initial = observe(session)
                check_oracle(initial, 0)
                saved = session.save_anchor_stone("common-start.sav", max_bytes=8 * MIB)
                report["cold_start_common_fixture"] = {"elapsed_ns": time.perf_counter_ns() - cold_start,
                    "includes": "Project creation, process startup, three warmup renderer frames, oracle read, one common Anchor Stone",
                    "excluded_from_mode_timings": True, "checkpoint": state_ref(saved),
                    "seed_state": observation_record(initial),
                    "measured_point_zero": "One identical explicit completed-frame alignment after restoring this seed."}
                report["native_capabilities"] = session.rpc.capabilities
                report["session_metadata"] = session.metadata
                persist()
                for number in range(1, args.trials + 1):
                    order = list(MODES[number % len(MODES):] + MODES[:number % len(MODES)])
                    trial = {"trial": number, "status": "running", "mode_order": order, "modes": {}}
                    report["trials"].append(trial)
                    unrecorded = {}
                    trial["unrecorded_baseline"] = unrecorded
                    try:
                        run_unrecorded_baseline(project, session, saved["artifact"], initial, number,
                                                args.frames, frame_plan(args.frames), args.timeout_ms,
                                                persist, unrecorded)
                    except Exception as error:
                        unrecorded.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                        trial["status"] = "failed"
                        persist()
                        raise
                    for mode in order:
                        arm = {}
                        trial["modes"][mode] = arm
                        try:
                            run_mode(project, session, saved["artifact"], initial, mode, number,
                                     args.frames, frame_plan(args.frames), args.timeout_ms, persist, arm)
                        except Exception as error:
                            arm.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
                            trial["status"] = "failed"
                            persist()
                            raise
                    trial["cross_mode_state_equality"] = trial_comparison(trial, args.frames)
                    trial["forward_recording_overhead"] = overhead_against_unrecorded(trial)
                    trial["status"] = "passed"
                    persist()
        report["status"] = "passed"
    except KeyboardInterrupt:
        report.update(status="interrupted", error={"type": "KeyboardInterrupt", "message": "Benchmark interrupted"})
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    finally:
        if previous_store is None:
            os.environ.pop("FDISBULL_TARGET_STORE", None)
        else:
            os.environ["FDISBULL_TARGET_STORE"] = previous_store
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["summary"] = summary(report["trials"])
        persist()
    print(json.dumps({"status": report["status"], "report": str(report_path), "summary": report["summary"]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
