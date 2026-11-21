"""Real native acceptance for explicit variable-to-literal placement overrides.

All programs and expected final arrays are independently specified. In particular,
same source assignments do not imply equal final variables after get.posn.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "native" / "qemu-agi" / "variable_scene_edit_harness.py"


def invoke(output, binary, *extra):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT / "packages" / "fdisbull-core" / "src")
    return subprocess.run(
        [sys.executable, str(CLI), "--binary", str(binary), "--output", str(output), *extra],
        capture_output=True, text=True, env=env, timeout=45,
    )


def actor_record(index, position):
    x, y = position
    return {"id": index, "x": x, "y": y, "prev_x": x, "prev_y": y}


def test_native_variable_overrides_report_history_aliases_overwrite_and_propagation(tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("native variable editing requires explicit FDISBULL_QEMU_AGI")
    binary = Path(configured).expanduser().resolve()
    assert binary.is_file() and os.access(binary, os.X_OK)
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    output = tmp_path / "variable-scene-demo.json"
    evidence = tmp_path / "native-failures"
    evidence.mkdir()
    result = invoke(output, binary, "--evidence-dir", str(evidence))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(output)
    report = json.loads(output.read_text())
    assert report["schema"] == "fdisbull-agi-variable-scene-edit-demo-1"
    assert report["status"] == "completed"
    assert report["all_requested_placements_matched"] is False
    assert report["parameters"] == {
        "mask": 2, "capacity": 8, "step_budget": 8, "maximum_children": 8,
        "maximum_resumes_per_child": 1, "timeout": 10.0,
    }
    # name, original/candidate raw bytes, selected PC, historical variable reads,
    # original/candidate actors, original/candidate final variables, instructions,
    # original/candidate SCENE counts and candidate actor-zero witness PC/opcode.
    expected = [
        ("historical_reads", "03070a030814260007080307460308502601070800",
         "03070a03081425001e280307460308502601070800", 6,
         {"x": {"index": 7, "value": 10}, "y": {"index": 8, "value": 20}},
         {0: (10, 20), 1: (70, 80)}, {0: (30, 40), 1: (70, 80)},
         {7: 70, 8: 80}, {7: 70, 8: 80}, 7, (2, 2), (6, 37)),
        ("aliased_variables", "030919260009092601090900",
         "03091925001e282601090900", 3,
         {"x": {"index": 9, "value": 25}, "y": {"index": 9, "value": 25}},
         {0: (25, 25), 1: (25, 25)}, {0: (30, 40), 1: (25, 25)},
         {9: 25}, {9: 25}, 4, (2, 2), (3, 37)),
        ("later_assignment_overrides", "03070a030814260007082600070800",
         "03070a03081425001e282600070800", 6,
         {"x": {"index": 7, "value": 10}, "y": {"index": 8, "value": 20}},
         {0: (10, 20)}, {0: (10, 20)}, {7: 10, 8: 20}, {7: 10, 8: 20},
         5, (1, 2), (10, 38)),
        ("downstream_get_posn", "03070a03081426000708270007082601070800",
         "03070a03081425001e28270007082601070800", 6,
         {"x": {"index": 7, "value": 10}, "y": {"index": 8, "value": 20}},
         {0: (10, 20), 1: (10, 20)}, {0: (30, 40), 1: (30, 40)},
         {7: 10, 8: 20}, {7: 30, 8: 40}, 6, (2, 2), (6, 37)),
    ]
    assert len(report["cases"]) == 4
    sessions = set()
    retired = 0
    for case, (name, original_hex, candidate_hex, pc, reads, original_actors,
               candidate_actors, original_vars, candidate_vars, instructions,
               event_counts, final_witness) in zip(report["cases"], expected):
        assert case["name"] == name
        plan = case["plan"]
        assert plan["schema"] == "fdisbull-agi-variable-position-override-1"
        assert plan["actor"] == 0 and plan["offset"] == pc and plan["length"] == 4
        assert plan["expected_bytes"] == [38, 0, reads["x"]["index"], reads["y"]["index"]]
        assert plan["replacement_bytes"] == [37, 0, 30, 40]
        assert plan["binding_change"] == {"from": "variable", "to": "literal"}
        assert plan["variable_reads"] == reads
        assert plan["read_value_basis"] == "position_witness"
        assert plan["changed"] is True and plan["write_performed"] is False
        assert plan["requested_position_matches_observed"] is False
        assert plan["requested_position"] == {"x": 30, "y": 40}
        assert plan["scope"] == "static_instruction"
        original_code, candidate_code = bytes.fromhex(original_hex), bytes.fromhex(candidate_hex)
        assert [i for i, (a, b) in enumerate(zip(original_code, candidate_code)) if a != b] == [pc, pc + 2, pc + 3]
        assert len(original_code) == len(candidate_code)
        for index, (role, program_hex, actors, variables) in enumerate((
                ("original", original_hex, original_actors, original_vars),
                ("candidate", candidate_hex, candidate_actors, candidate_vars))):
            run = case[role]
            program = bytes.fromhex(program_hex)
            digest = hashlib.sha256(program).hexdigest()
            assert run["program"] == {"hex": program_hex, "size": len(program), "sha256": digest}
            assert run["binary"]["sha256"] == binary_sha
            view = run["capture"]["view"]
            sessions.add(view["session_id"])
            assert view["source"]["sha256"] == digest
            assert view["source"]["size"] == len(program)
            assert view["coverage"]["history_complete_since_attach"] is True
            assert view["coverage"]["gap_count"] == 0
            guest = run["final_state"]["guest"]
            assert guest == {
                "actors": [actor_record(i, actors.get(i, (0, 0))) for i in range(16)],
                "variables": [variables.get(i, 0) for i in range(256)],
                "flags": [0] * 256, "pc": len(program), "retired": instructions,
                "status": "return", "fault": None,
            }
            observation = run["final_state"]["observation"]
            assert observation["mask"] == 2 and observation["count"] == event_counts[index]
            assert observation["eligible"] == event_counts[index] and observation["dropped"] == 0
            assert observation["per_channel"]["disasm"]["eligible"] == 0
            assert observation["per_channel"]["scene"]["eligible"] == event_counts[index]
            retired += guest["retired"]
        before = case["original"]["capture"]["view"]
        after = case["candidate"]["capture"]["view"]
        assert plan["session_id"] == before["session_id"]
        assert plan["checkpoint"] == before["checkpoint"]
        assert plan["source"] == before["source"] and plan["candidate_source"] == after["source"]
        assert plan["witness"] == before["actors"][0]["witness"]
        assert after["actors"][0]["witness"]["pc"] == final_witness[0]
        assert after["actors"][0]["witness"]["opcode"] == final_witness[1]
        x, y = candidate_actors[0]
        expected_variables = []
        expected_other_actors = []
        if name == "downstream_get_posn":
            expected_variables = [{"index": 7, "before": 10, "after": 30},
                                  {"index": 8, "before": 20, "after": 40}]
            expected_other_actors = [{"index": 1, "before": actor_record(1, (10, 20)),
                                      "after": actor_record(1, (30, 40))}]
        assert case["comparison"] == {
            "requested_position": {"x": 30, "y": 40}, "observed_position": {"x": x, "y": y},
            "placement_matched": name != "later_assignment_overrides",
            "candidate_returned": True, "separate_attachments": True,
            "difference_scope": "final_guest_snapshots",
            "final_variables_changes": expected_variables,
            "final_flags_changes": [], "final_other_actor_changes": expected_other_actors,
        }
    assert len(sessions) == 8 and retired == 44
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == binary_sha


def test_variable_cli_preserves_existing_receipt_before_any_launch(tmp_path):
    output = tmp_path / "keep.json"
    output.write_text("previous receipt\n")
    result = invoke(output, tmp_path / "missing-native-binary")
    assert result.returncode != 0 and "FileExistsError" in result.stderr
    assert output.read_text() == "previous receipt\n"


def test_variable_cli_keeps_partial_receipt_on_launch_failure(tmp_path):
    output = tmp_path / "failed.json"
    result = invoke(output, tmp_path / "missing-native-binary")
    assert result.returncode != 0
    report = json.loads(output.read_text())
    assert report["status"] == "failed"
    assert report["failure"]["type"] == "ValueError"
    assert "explicit executable" in report["failure"]["message"]
    assert len(report["cases"]) == 1
    assert report["cases"][0]["original"]["program"]["hex"] == "03070a030814260007080307460308502601070800"
    assert report["cases"][0]["candidate"] == {}
    assert "comparison" not in report["cases"][0]
