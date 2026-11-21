"""Exercise the authored placement-edit workflow through its real CLI.

Expected byte programs, final positions and event counts are independently
specified. The negative case intentionally completes with placement_matched
false: a later identical assignment was absent from the original scene stream.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "native" / "qemu-agi" / "scene_edit_harness.py"


def invoke(output, binary, *extra):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "packages" / "fdisbull-core" / "src")
    return subprocess.run(
        [sys.executable, str(CLI), "--binary", str(binary), "--output", str(output), *extra],
        capture_output=True, text=True, env=env, timeout=45,
    )


def test_native_literal_edit_reports_achieved_and_overridden_placements(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("native scene editing requires explicit FDISBULL_QEMU_AGI")
    binary = Path(configured).expanduser().resolve()
    assert binary.is_file() and os.access(binary, os.X_OK)
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    output = tmp_path / "scene-edit-demo.json"
    evidence = tmp_path / "native-failures"
    evidence.mkdir()
    result = invoke(output, binary, "--evidence-dir", str(evidence))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(output)
    report = json.loads(output.read_text())
    assert report["schema"] == "fdisbull-agi-scene-edit-demo-1"
    assert report["status"] == "completed"
    assert report["all_requested_placements_matched"] is False
    assert report["parameters"]["maximum_children"] == 4
    assert report["parameters"]["maximum_resumes_per_child"] == 1
    expected = [
        ("direct_placement", "25000a1400", "25001e2800", (30, 40), True, 2, 1, 0),
        ("later_assignment_overrides", "25000a1425000a1400", "25001e2825000a1400",
         (10, 20), False, 3, 2, 4),
    ]
    assert len(report["cases"]) == 2
    sessions = set()
    retired = 0
    for case, (name, original_hex, candidate_hex, position, matched, instructions,
               candidate_events, candidate_pc) in zip(report["cases"], expected):
        assert case["name"] == name
        plan = case["plan"]
        assert plan["schema"] == "fdisbull-agi-literal-position-edit-1"
        assert plan["offset"] == 0 and plan["length"] == 4
        assert plan["expected_bytes"] == [37, 0, 10, 20]
        assert plan["replacement_bytes"] == [37, 0, 30, 40]
        assert plan["requested_position"] == {"x": 30, "y": 40}
        assert plan["write_performed"] is False and plan["changed"] is True
        assert plan["scope"] == "static_instruction"
        assert case["comparison"] == {
            "requested_position": {"x": 30, "y": 40},
            "observed_position": {"x": position[0], "y": position[1]},
            "placement_matched": matched, "candidate_returned": True,
            "separate_attachments": True,
        }
        for role, program_hex, final_position, events, witness_pc in (
                ("original", original_hex, (10, 20), 1, 0),
                ("candidate", candidate_hex, position, candidate_events, candidate_pc)):
            run = case[role]
            program = bytes.fromhex(program_hex)
            digest = hashlib.sha256(program).hexdigest()
            assert run["program"] == {"hex": program_hex, "size": len(program), "sha256": digest}
            assert run["binary"]["sha256"] == binary_sha
            view = run["capture"]["view"]
            sessions.add(view["session_id"])
            assert view["source"]["sha256"] == digest
            assert view["source"]["size"] == len(program)
            assert view["guest"]["status"] == "return"
            assert view["checkpoint"]["retired"] == instructions
            assert view["coverage"]["history_complete_since_attach"] is True
            assert view["coverage"]["gap_count"] == 0
            assert view["actors"][0]["witness"]["pc"] == witness_pc
            for index, actor in enumerate(view["actors"]):
                x, y = final_position if index == 0 else (0, 0)
                assert {key: actor[key] for key in ("id", "x", "y", "prev_x", "prev_y")} == {
                    "id": index, "x": x, "y": y, "prev_x": x, "prev_y": y,
                }
            observation = run["final_state"]["observation"]
            assert observation["mask"] == 2 and observation["count"] == events
            assert observation["dropped"] == 0
            assert observation["per_channel"]["disasm"]["eligible"] == 0
            assert observation["per_channel"]["scene"]["eligible"] == events
            retired += view["checkpoint"]["retired"]
        assert plan["session_id"] == case["original"]["capture"]["view"]["session_id"]
        assert plan["source"] == case["original"]["capture"]["view"]["source"]
        assert plan["candidate_source"] == case["candidate"]["capture"]["view"]["source"]
    assert len(sessions) == 4 and retired == 10
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == binary_sha


def test_edit_cli_preserves_existing_receipt_before_any_launch(tmp_path):
    output = tmp_path / "keep.json"
    output.write_text("previous receipt\n")
    result = invoke(output, tmp_path / "missing-native-binary")
    assert result.returncode != 0
    assert "FileExistsError" in result.stderr
    assert output.read_text() == "previous receipt\n"


def test_edit_cli_keeps_partial_receipt_on_launch_failure(tmp_path):
    output = tmp_path / "failed.json"
    result = invoke(output, tmp_path / "missing-native-binary")
    assert result.returncode != 0
    report = json.loads(output.read_text())
    assert report["status"] == "failed"
    assert report["failure"]["type"] == "ValueError"
    assert "explicit executable" in report["failure"]["message"]
    assert len(report["cases"]) == 1
    assert report["cases"][0]["original"]["program"]["hex"] == "25000a1400"
    assert report["cases"][0]["candidate"] == {}
    assert "comparison" not in report["cases"][0]
