"""Native packet boundary checks with independently specified authored outcomes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "native/qemu-agi/reconstruction_trial.py"


def invoke(path, binary, *extra):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "packages/fdisbull-core/src")
    return subprocess.run([sys.executable, str(CLI), "--binary", str(binary),
                           "--output-dir", str(path), *extra], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=45)


def test_trial_preserves_existing_directory_before_launch(tmp_path):
    out = tmp_path / "existing"; out.mkdir()
    marker = out / "marker"; marker.write_bytes(b"retain")
    result = invoke(out, tmp_path / "missing-binary")
    assert result.returncode != 0
    assert "FileExistsError" in result.stderr
    assert list(out.iterdir()) == [marker]
    assert marker.read_bytes() == b"retain"


def test_trial_retains_failed_launch_and_authored_oracle(tmp_path):
    out = tmp_path / "failed"
    result = invoke(out, tmp_path / "missing-binary")
    assert result.returncode != 0
    receipt = json.loads((out / "collection.json").read_text())
    assert receipt["status"] == "failed" and receipt["failure"]["type"]
    assert len(receipt["runs"]) == 1
    assert (out / "oracle.json").is_file()
    assert not (out / "scene_only").exists()


def test_native_trial_packets_preserve_gap_and_snapshot_boundaries(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI")
    binary = Path(configured).expanduser().resolve()
    output = tmp_path / "trial"
    result = invoke(output, binary)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "collection.json").read_text())
    assert receipt["status"] == "completed"
    assert len(receipt["runs"]) == 6
    assert receipt["parameters"]["maximum_children"] == 6
    assert receipt["parameters"]["maximum_resumes_per_child"] == 1
    # Original code and complete expected guest arrays are independent of the
    # collector's CASES/expected_guest implementation.
    authored = {
        "case01": ("030b34030c5a26020b0c2505071225023c5d27020f1026070f1000",
                   {2: (60, 93), 5: (7, 18), 7: (60, 93)}, {11: 52, 12: 90, 15: 60, 16: 93}, 8, 4),
        "case02": ("03112c2603111103117d2606111125032c2c00",
                   {3: (44, 44), 6: (125, 125)}, {17: 125}, 6, 2),
        "case03": ("250016332501580e25098c912501590f00",
                   {0: (22, 51), 1: (89, 15), 9: (140, 145)}, {}, 5, 4),
    }
    sessions = set()
    for run in receipt["runs"]:
        code_hex, positions, variables, retired, scene_count = authored[run["id"]]
        assert run["program_hex"] == code_hex
        state = run["final_state"]
        actors = []
        for i in range(16):
            x, y = positions.get(i, (0, 0))
            actors.append({"id": i, "x": x, "y": y, "prev_x": x, "prev_y": y})
        assert state["guest"] == {"pc": len(bytes.fromhex(code_hex)), "actors": actors,
                                  "variables": [variables.get(i, 0) for i in range(256)],
                                  "flags": [0] * 256, "status": "return", "fault": None, "retired": retired}
        assert state["source"]["sha256"] == hashlib.sha256(bytes.fromhex(code_hex)).hexdigest()
        assert state["run"]["invocation"] == 1
        assert state["observation"]["per_channel"]["scene"]["eligible"] == scene_count
        sid = run["attachment"]["view"]["session_id"]
        assert sid not in sessions
        sessions.add(sid)
        if run["id"] == "case03":
            assert state["observation"]["per_channel"]["scene"]["dropped"] == 2
            assert run["capture"]["update"]["status"] == "resynced"
            assert run["capture"]["view"]["coverage"]["history_complete_since_attach"] is False
            prefix = [e for e in run["events"]["events"] if e["kind"] == "position"]
            assert [(e["actor"], e["after"]["x"], e["after"]["y"]) for e in prefix] == [(0, 22, 51), (1, 88, 14)]
            assert [e["seq"] for e in run["events"]["events"]] == list(range(1, len(run["events"]["events"]) + 1))
        else:
            assert state["observation"]["dropped"] == 0
    assert sum(run["final_state"]["guest"]["retired"] for run in receipt["runs"]) == 38
    for condition in ("scene_only", "scene_disasm", "snapshot_scene_disasm"):
        packet = json.loads((output / condition / "packet.json").read_text())
        assert packet["condition"] == condition
        assert len(packet["cases"]) == 3
        assert (output / condition / "PROTOCOL.md").read_bytes() == CLI.with_name("SCENE_RECONSTRUCTION_PACKET.md").read_bytes()
        for case in packet["cases"]:
            source_condition = "scene_disasm" if condition == "snapshot_scene_disasm" else condition
            source_run = next(run for run in receipt["runs"] if run["id"] == case["id"] and run["condition"] == source_condition)
            state = source_run["final_state"]
            expected_packet = {
                "id": source_run["id"],
                "attachment_id": source_run["attachment"]["view"]["session_id"],
                "source": state["source"],
                "collection": {"mask_held_constant": True, "cleared_during_interval": False,
                               "restarted_during_interval": False, "stopped_capture_stable": True,
                               "initial_snapshot_supplied": False},
                "checkpoint": {"guest": {key: state["guest"][key] for key in ("pc", "status", "fault", "retired")},
                               "observation": state["observation"],
                               "run": {key: state["run"][key] for key in ("retired", "invocation")}},
                "observations": source_run["events"],
            }
            if condition == "snapshot_scene_disasm":
                expected_packet["captured_scene"] = source_run["capture"]
            # Exact public field projection protects both raw evidence fidelity
            # and the blind trial's withheld-source/guest-array boundary.
            assert case == expected_packet
            assert set(case["checkpoint"]["guest"]) == {"pc", "status", "fault", "retired"}
            assert not {"program_hex", "oracle", "final_state", "variables", "flags"} & set(case)
            assert case["observations"]["source"] == case["source"]
            assert case["collection"]["initial_snapshot_supplied"] is False
            if condition == "scene_only":
                assert all(e["kind"] == "position" for e in case["observations"]["events"])
            if condition == "snapshot_scene_disasm":
                view = case["captured_scene"]["view"]
                assert len(view["actors"]) == 16
                assert view["session_id"] == case["attachment_id"]
                assert view["source"] == case["source"]
                if case["id"] == "case03":
                    assert view["actors"][1]["x"] == 89 and view["actors"][1]["y"] == 15
                    assert view["actors"][9]["x"] == 140 and view["actors"][9]["y"] == 145
                    assert all(a["witness"] is None for a in view["actors"])
            else:
                assert "captured_scene" not in case


def test_native_zero_change_probe_distinguishes_enabled_empty_channel(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI")
    output = tmp_path / "zero-change"
    result = invoke(output, Path(configured).expanduser().resolve(), "--zero-change-probe")
    assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "collection.json").read_text())
    assert receipt["status"] == "completed" and len(receipt["runs"]) == 2
    for run in receipt["runs"]:
        assert run["program_hex"] == "2504000000"
        state = run["final_state"]
        assert state["guest"]["status"] == "return" and state["guest"]["retired"] == 2
        assert state["guest"]["actors"][4] == {"id": 4, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0}
        assert state["observation"]["mask"] & 2
        assert state["observation"]["per_channel"]["scene"] == {"eligible": 0, "stored": 0, "dropped": 0}
        assert run["capture"]["view"]["coverage"]["history_complete_since_attach"] is True
        if run["condition"] == "scene_only":
            assert run["events"]["events"] == []
        else:
            assert [(e["pc"], e["opcode"], e["bytes"]) for e in run["events"]["events"]] == [(0, 37, [37, 4, 0, 0]), (4, 0, [0])]


def test_native_packet_write_failure_is_retained_after_collection(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI")
    output = tmp_path / "packet-io-failure"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "packages/fdisbull-core/src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = """
import pathlib, sys
sys.path.insert(0, sys.argv[3])
import reconstruction_trial
write_bytes = pathlib.Path.write_bytes
def fail_protocol(self, data):
    if self.name == 'PROTOCOL.md':
        raise OSError('injected protocol write failure')
    return write_bytes(self, data)
pathlib.Path.write_bytes = fail_protocol
reconstruction_trial.collect(sys.argv[1], sys.argv[2])
"""
    result = subprocess.run([sys.executable, "-c", code, configured, str(output), str(CLI.parent)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode != 0 and "injected protocol write failure" in result.stderr
    receipt = json.loads((output / "collection.json").read_text())
    assert len(receipt["runs"]) == 6
    assert all(run["final_state"]["guest"]["status"] == "return" for run in receipt["runs"])
    assert receipt["status"] == "failed"
    assert receipt["failure"]["stage"] == "packet_write"
    assert receipt["failure"]["type"] == "OSError"
    assert (output / "oracle.json").is_file()
    assert (output / "scene_only/packet.json").is_file()
    assert not (output / "scene_only/PROTOCOL.md").exists()
