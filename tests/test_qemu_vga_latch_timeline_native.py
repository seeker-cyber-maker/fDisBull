"""Public source-raster history replay for the timed unchained VGA profile."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from fdisbull.qemu_instrumented_checkpoint import VIDEO_LATCH_FORMAT
from fdisbull.qemu_video_checkpoint import LATCH_MODEL, LATCH_PROFILE
from support.dos_process_fixture import assemble, digest
from test_dosbox_frame_source_probe_native import _pixels
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vga_latch_checkpoint_native import _finish, _guest, _logical, _native, _page
from test_qemu_vga_phase_checkpoint_native import _reach


POINTS = [[0, 0], [3, 100], [319, 199]]


@contextmanager
def _workspace(control):
    workspace = DebugWorkspace()
    directory = Path(control["directory"])
    policy = OutputPolicy(artifact_dir=directory / "json-outputs")

    def call(method, *, expect_ok=True, **params):
        with output_policy_context(policy):
            reply = respond({"method": method, "params": {"project": control["database"], **params}},
                            debugger=workspace)
            assert reply["ok"] is expect_ok, reply
            marker = reply.get("result")
            if expect_ok and marker.get("format") == "fdisbull-output-ref-1":
                assert marker["retry_safe"] is False and marker["complete"] is False
                artifact = marker["artifact"]
                output = directory / (artifact["id"] + ".json")
                exported = respond({"method": "output-export",
                                    "params": {"artifact": artifact["id"], "output": str(output)}})
                assert exported["ok"], exported
                data = output.read_bytes()
                assert len(data) == artifact["bytes"] and sha256(data).hexdigest() == artifact["sha256"]
                reply = json.loads(data)
                assert reply["ok"] is True
        return reply["result"] if expect_ok else reply["error"]

    try:
        runtime = control["runtime"]
        options = launch_options(runtime, {"image": control["boot"]}, qemu_clock="virtual",
            qemu_retrace="precise", qemu_checkpoint_tool=control["tool"],
            qemu_video_source_profile=LATCH_PROFILE)
        run = call("debug-launch", executable=runtime["executable"],
                   game_dir=control["directory"], **options)["run"]
        debug = workspace.sessions[run]
        yield call, run, debug
        owner = debug.vm.process
        assert call("debug-stop", run=run)["process_reaped"] and owner.poll() == 0
    finally:
        workspace.close()


def _pending_page(debug, addresses):
    process = process_record(debug)
    a, b, returned_a, flag = (com_address(process, offset) for offset in addresses)
    park(debug, a)
    debug.video_frame_start()
    _finish(debug, 0x4000, 1)
    debug.write_memory(flag, "01", expected_hex="00")
    park(debug, b)
    first_b = _finish(debug, 0x8000, 5)
    line = first_b["frame"]["line-period-ns"]
    _reach(debug, first_b["next-deadline-ns"] + line // 4)
    selection = _native(debug)
    assert selection["pending-page-latch"]["origin-bytes"] == 0x20000
    debug.write_memory(flag, "02", expected_hex="01")
    park(debug, returned_a)
    _reach(debug, selection["next-deadline-ns"] + 2 * 64 * line + line // 2)
    info = _native(debug)
    assert info["rows-sampled"] == 65 and _page(debug) == 0x4000
    assert info["pending-page-latch"] == selection["pending-page-latch"]
    return info


def _stored_png(call, run, timeline, record, destination):
    image = call("debug-timeline-image", run=run, timeline=timeline, point=record["point"])
    assert image["sha256"] == record["frame"]["image"]["sha256"]
    assert image["source_raster"] == record["frame"]["source_raster"]
    assert image["stored_frame"] and image["completed_guest_frame"] is None
    call("debug-export", artifact=image["artifact"], output=str(destination))
    assert digest(destination) == image["sha256"]
    with Image.open(destination) as decoded:
        assert decoded.format == "PNG" and decoded.size == (320, 200)
        return sha256(decoded.convert("RGB").tobytes()).hexdigest()


def _replay(call, run, control, *, label):
    result = call("debug-script", run=run, script_id=control["script_id"], timeout_ms=40000)
    assert result["ok"] and result["completed_steps"] == 4, result
    steps = [step["result"] for step in result["steps"]]
    branch = []
    receipts = []
    for number, (origin, first) in enumerate(((0x20000, 5), (0x10000, 1))):
        history, probe = steps[2 * number:2 * number + 2]
        assert history["completed_frames"] == 1 and history["input_bytes_used"] == 2
        assert not history["current_dirty"]
        point, = history["frames"]
        assert point["frame"]["keys"] == [] and point["frame"]["input"] is None
        state = probe["native"]
        assert state["model"] == LATCH_MODEL and state["frame"]["page-latch"]["origin-bytes"] == origin
        palette = [bytes((value << 2) | (value >> 4) for value in (n, 2 * n, 3 * n))
                   for n in range(17)]
        indices = _pixels(first)
        expected = sha256(b"".join(palette[index] for index in indices)).hexdigest()
        assert probe["samples"] == [
            {"x": x, "y": y, "rgb": list(palette[indices[320 * y + x]])} for x, y in POINTS]
        assert expected == state["frame"]["pixel-sha256"] == point["frame"]["source_raster"]["pixel_sha256"]
        assert _stored_png(call, run, history["timeline"], point,
                           Path(control["directory"]) / f"{label}-{number}.png") == expected
        branch.append({"timeline": history["timeline"], **point})
        receipts.append({"native": _logical(state), "image_sha256": point["frame"]["image"]["sha256"]})
    return receipts, branch


def _public_frame_steps(call, run, debug, expected):
    baseline = _native(debug)["frame-sequence"]
    python_step = debug.call("frame.step", {"timeout_ms": 5000})
    json_advance = call("debug-frame-advance", run=run, frames=1, timeout_ms=5000)
    script = call("debug-save-script", name="step-latched-page.json", script={
        "format": "fdisbull-script-1", "backend": "qemu-dos",
        "steps": [{"op": "frame-advance", "frames": 1, "timeout_ms": 5000}],
    })
    replay = call("debug-script", run=run, script_id=script["script_id"], timeout_ms=8000)
    assert replay["ok"] and replay["completed_steps"] == 1, replay
    script_advance = replay["steps"][0]["result"]
    for batch in (json_advance, script_advance):
        assert batch["frame_profile"] == LATCH_MODEL and batch["completed_frames"] == 1
    frames = [python_step, json_advance["frames"][0], script_advance["frames"][0]]
    for offset, step in enumerate(frames, start=1):
        assert step["completed"] and step["frame_profile"] == LATCH_MODEL
        assert step["frame_id"] == baseline + offset
        frame = step["native_advance"]["frame"]
        assert frame["page-latch"]["origin-bytes"] == expected["page-latch"]["origin-bytes"]
        assert frame["pixel-sha256"] == expected["pixel-sha256"]


def _cold(control):
    with _workspace(control) as (call, run, debug):
        previous = debug.vm.process
        restored = call("debug-timeline-rewind", run=run, timeline=control["root_timeline"],
                        point=control["root_point"], timeout_ms=30000)
        assert debug.vm.process is not previous and previous.poll() == 0
        assert restored["restore"]["restore"]["instrumentation"]["format"] == VIDEO_LATCH_FORMAT
        assert restored["restore"]["frame_readback"]["historical"] == control["historical"]
        saved, live = control["saved"], _native(debug)
        assert live["token"] != saved["token"] and live["epoch"] != saved["epoch"]
        assert _logical(live) == _logical(saved) and _page(debug) == 0x4000
        refusal = call("debug-video-frame-probe", run=run, stream=saved["token"],
                       frame_id=saved["frame"]["frame-id"], points=POINTS, expect_ok=False)
        assert "not the retained raster" in refusal["message"]
        assert _native(debug) == live
        cursor = call("debug-timeline-status", run=run)
        assert cursor["valid"] and cursor["point"] == control["root_point"], cursor["invalid_reason"]
        actual, _ = _replay(call, run, control, label="cold")
        assert actual == control["expected"]
        for number, point in enumerate(control["original_branch"]):
            assert _stored_png(call, run, point["timeline"], point,
                               Path(control["directory"]) / f"retained-{number}.png") == (
                                   point["frame"]["source_raster"]["pixel_sha256"])
        _public_frame_steps(call, run, debug, actual[-1]["native"]["frame"])
    print(json.dumps({"cold_replay": True, "rasters": len(actual), "frame_step_routes": 3}))


@pytest.mark.skipif(os.environ.get("FDISBULL_REQUIRE_QEMU_VGA_LATCH") != "1",
                    reason="Select the exact native QEMU timed VGA latch witness")
def test_unchained_latch_source_timeline_replays_saved_script_in_separate_python(
        tmp_path, clock_runtime, clock_disk, record_property):
    tool = os.environ["FDISBULL_QEMU_IMG"]
    assert digest(clock_runtime["executable"]) == os.environ["FDISBULL_QEMU_VGA_LATCH_SHA256"]
    assert digest(tool) == os.environ["FDISBULL_QEMU_VGA_LATCH_IMG_SHA256"]
    data = assemble(tmp_path, "latch-timeline", _guest(), clock_runtime["nasm"])
    assert data[-12:-8] == b"SVGA"
    binary = tmp_path / "PAGES.COM"
    binary.write_bytes(data)
    database = tmp_path / "latch-timeline.fdb"
    with Project.create(database, binary, image="com"):
        pass
    control = {"database": str(database), "directory": str(tmp_path), "tool": tool,
               "runtime": {key: str(value) if value is not None else None
                           for key, value in clock_runtime.items()},
               "boot": str(clock_disk["image"])}
    with _workspace(control) as (call, run, debug):
        saved = _pending_page(debug, struct.unpack("<4H", data[-8:]))
        root = call("debug-timeline-start", run=run, frame_source="source-raster",
                    max_frames=8, max_bytes=160*1024**2, max_state_bytes=24*1024**2, timeout_ms=30000)
        script = {"format": "fdisbull-script-1", "backend": "qemu-dos", "steps": [
            {"op": "timeline-advance", "frames": 1, "timeout_ms": 15000},
            {"op": "video-frame-probe", "points": POINTS},
        ] * 2}
        stored = call("debug-save-script", name="next-two-latched-rasters.json", script=script)
        control.update(saved=saved, root_timeline=root["timeline"], root_point=root["point"],
                       historical=root["nodes"][0]["frame"]["source_raster"], script_id=stored["script_id"])
        expected, original_branch = _replay(call, run, control, label="initial")
        control.update(expected=expected, original_branch=original_branch)
    capsule = tmp_path / "cold-latch-timeline.json"
    capsule.write_text(json.dumps(control), encoding="utf-8")
    child = subprocess.run([sys.executable, __file__, "--cold", str(capsule)],
                           capture_output=True, text=True, timeout=100)
    assert child.returncode == 0, child.stderr[-8000:]
    assert json.loads(child.stdout) == {"cold_replay": True, "rasters": 2, "frame_step_routes": 3}
    record_property("png_sha256", [receipt["image_sha256"] for receipt in expected])
    assert binary.read_bytes() == data and digest(clock_disk["image"]) == clock_disk["prepared_sha256"]
    assert digest(clock_runtime["boot_image"]) == clock_disk["source_sha256"]


if __name__ == "__main__":
    assert sys.argv[1] == "--cold"
    _cold(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
