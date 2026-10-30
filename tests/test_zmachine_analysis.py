"""Public processor analysis on authored stories, independent of Zork payloads."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.zmachine_analysis import analyze_story, disassemble_story
from test_zmachine import image


def story(tmp_path, code, *, patches=()):
    data = image()
    data[900:900 + len(code)] = code
    for offset, payload in patches:
        data[offset:offset + len(payload)] = payload
    data[28:30] = (sum(data[64:]) & 65535).to_bytes(2, "big")
    path = tmp_path / "authored.z3"
    path.write_bytes(data)
    return path


def test_recursive_branch_paths_and_loop_are_deduplicated(tmp_path):
    # Both alternatives are kept even though this literal condition is true.
    # The processor describes encoding, not path feasibility.
    path = story(tmp_path, bytes.fromhex("90 00 c5 b4 b1 00 b0"))
    result = analyze_story(path)
    assert [row["offset"] for row in result["instructions"]] == [900, 903, 904, 906]
    assert result["worklist_drained"] and result["complete"]
    assert not result["runtime_reachability_proven"]
    path = story(tmp_path, bytes.fromhex("8c ff ff"))  # End 903 - 1 - 2 = 900.
    result = analyze_story(path)
    assert result["instruction_count"] == 1
    assert result["worklist_drained"] and not result["frontier"]


def test_budget_stop_exposes_pending_work_and_is_not_complete(tmp_path):
    path = story(tmp_path, bytes.fromhex("90 00 c5 b4 b1 00 b0"))
    result = analyze_story(path, max_instructions=1)
    assert result["instruction_count"] == result["decode_attempts"] == 1
    assert result["status"] == "instruction_budget"
    assert not result["complete"] and not result["worklist_drained"]
    assert sorted(item["offset"] for item in result["frontier"]) == [903, 906]


def test_call_target_is_code_after_header_and_defaults(tmp_path):
    path = story(tmp_path, bytes.fromhex("e0 3f 01 e0 10 ba"),
                 patches=[(960, bytes.fromhex("02 12 34 ab cd b0"))])
    result = analyze_story(path)
    assert [row["offset"] for row in result["instructions"]] == [900, 905, 965]
    assert result["routine_candidates"][0]["routine_header"] == 960
    assert result["routine_candidates"][0]["entry"] == 965
    assert result["routine_candidates"][0]["call_sites"] == [900]
    assert result["routine_candidates"][0]["classification"] == "candidate"


def test_unknown_target_does_not_become_a_complete_graph(tmp_path):
    path = story(tmp_path, bytes.fromhex("ac 10"))
    result = analyze_story(path)
    assert result["worklist_drained"] and not result["complete"]
    assert result["status"] == "partial"
    assert result["unresolved_transfers"][0]["kind"] == "branch"
    assert result["unresolved_transfers"][0]["target"] is None


def test_decode_failure_is_evidence_and_other_branch_is_still_examined(tmp_path):
    path = story(tmp_path, bytes.fromhex("90 00 c5 be 00 00 b0"))
    result = analyze_story(path)
    assert [row["offset"] for row in result["instructions"]] == [900, 906]
    assert result["decode_attempts"] == 3
    assert result["issues"][0]["kind"] == "decode_error"
    assert result["issues"][0]["offset"] == 903
    assert not result["complete"]


def test_conflicting_instruction_interpretations_are_reported(tmp_path):
    # A branch names the first operand byte of an add on the other path.
    path = story(tmp_path, bytes.fromhex("90 00 c3 14 b0 02 10 ba"))
    result = analyze_story(path)
    assert {row["offset"] for row in result["instructions"]} == {900, 903, 904, 907}
    assert any(issue["kind"] == "overlapping_instructions" for issue in result["issues"])
    assert not result["complete"]


def test_explicit_roots_and_source_identity_are_preserved(tmp_path):
    path = story(tmp_path, b"\xba", patches=[(960, b"\xb0")])
    original = path.read_bytes()
    result = analyze_story(path, entry_points=["0x3c0", 960])
    assert result["entry_points"] == [960]
    assert [row["offset"] for row in result["instructions"]] == [960]
    assert result["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert result["source"]["sha256"] in result["processor"]["address_space"]
    assert path.read_bytes() == original


@pytest.mark.parametrize("entries", [[], "0x384", [True], [63], [1024], [900] * 257])
def test_bad_roots_refused(tmp_path, entries):
    with pytest.raises(ValueError, match="entry"):
        analyze_story(story(tmp_path, b"\xba"), entry_points=entries)


@pytest.mark.parametrize("limit", [0, -1, True, 100001, "10"])
def test_bad_budget_refused(tmp_path, limit):
    path = story(tmp_path, b"\xba")
    with pytest.raises(ValueError, match="max_instructions"):
        analyze_story(path, max_instructions=limit)
    with pytest.raises(ValueError, match="max_instructions"):
        disassemble_story(path, max_instructions=limit)


def test_linear_listing_stops_at_terminal_flow_and_preserves_next_offset(tmp_path):
    path = story(tmp_path, bytes.fromhex("b4 b1 be"))
    result = disassemble_story(path)
    assert result["mode"] == "linear"
    assert [row["op"] for row in result["instructions"]] == ["nop", "rfalse"]
    assert result["status"] == "control_flow_boundary"
    assert result["next_offset"] is None
    limited = disassemble_story(path, max_instructions=1)
    assert limited["status"] == "instruction_budget"
    assert limited["next_offset"] == 901 and not limited["complete"]


def test_same_processor_dispatch_is_used_for_recursive_and_linear_queries(tmp_path, monkeypatch):
    from fdisbull import processor
    original = processor.decode_instruction
    calls = []

    def observed(adapter, program, location):
        calls.append(adapter.info.identity)
        return original(adapter, program, location)

    monkeypatch.setattr(processor, "decode_instruction", observed)
    path = story(tmp_path, b"\xba")
    analyze_story(path)
    disassemble_story(path)
    assert calls == ["fdisbull.zmachine.v3"] * 2


def test_public_methods_are_standalone_even_in_a_project_session(tmp_path):
    path = story(tmp_path, b"\xba")
    for method in ("zmachine-disasm", "zmachine-analyze"):
        reply = respond({"method": method, "params": {"path": str(path)}},
                        default_project=str(tmp_path / "does-not-exist.fdb"))
        assert reply["ok"], reply
        assert reply["result"]["instruction_count"] == 1
    assert not (tmp_path / "does-not-exist.fdb").exists()
    reply = respond({"method": "zmachine-analyze", "params": {"path": str(path), "bogus": 3}})
    assert not reply["ok"]


def test_public_cli_uses_module_and_reports_invalid_input(tmp_path):
    path = story(tmp_path, b"\xba", patches=[(960, b"\xb0")])
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    command = [sys.executable, "-m", "fdisbull", "zmachine-analyze", str(path),
               "--entry", "0x3c0", "--max-instructions", "10"]
    run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr + run.stdout
    reply = json.loads(run.stdout)
    assert reply["ok"] and reply["result"]["entry_points"] == [960]
    run = subprocess.run(command[:-1] + ["0"], env=env, capture_output=True, text=True, timeout=15)
    assert run.returncode == 1
    assert not json.loads(run.stdout)["ok"]
