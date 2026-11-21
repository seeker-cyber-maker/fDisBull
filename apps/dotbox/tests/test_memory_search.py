"""The shared kernel is usable through DotBox without a live game or full fDisBull."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dotbox import cli


def _context(length=8):
    return {"source_sha256": hashlib.sha256(b"authored source").hexdigest(),
            "run_id": "authored-run", "address_space": "authored-linear",
            "region": {"start": 4096, "length": length}, "task_id": "score-candidates",
            "mapping_id": "authored-mapping", "version_id": "authored-version"}


def _json(path, value):
    path.write_text(json.dumps(value))
    return path


def _call(capsys, *arguments):
    assert cli.main(["memory-search", *map(str, arguments)]) == 0
    output = capsys.readouterr()
    assert not output.err
    reply = json.loads(output.out)
    assert reply["ok"] is True and reply["runtime_observed"] is False
    return reply["result"]


def test_api_uses_the_shared_implementation_and_keeps_live_edits_out():
    from dotbox import memory_search
    from fdisbull_core import memory_search as shared

    for name in ("snapshot_metadata", "validate_snapshot", "start_search",
                 "validate_search", "refine_search", "search_results"):
        assert getattr(memory_search, name) is getattr(shared, name)
    assert not hasattr(memory_search, "plan_edit")
    assert memory_search.self_check()["ok"] is True


def test_cli_retains_full_candidates_and_pages_results_without_live_calls(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Client", lambda *a, **k: pytest.fail("offline search opened a live client"))
    before, after = tmp_path / "before.bin", tmp_path / "after.bin"
    before.write_bytes(bytes.fromhex("0a0014001e002800"))
    after.write_bytes(bytes.fromhex("0a00170021002800"))
    context = _json(tmp_path / "context.json", _context())
    snapshots = [tmp_path / "before.json", tmp_path / "after.json"]
    for path, snapshot, capture in zip((before, after), snapshots, ("before", "after")):
        result = _call(capsys, "snapshot", path, "--context", context,
                       "--capture-id", capture, "--output", snapshot)
        assert result["artifact_kind"] == "snapshot"
        assert result["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
        assert "data" not in json.loads(snapshot.read_text())
    initial, refined = tmp_path / "initial.json", tmp_path / "refined.json"
    result = _call(capsys, "start", before, "--snapshot", snapshots[0],
                   "--width", "2", "--stride", "2", "--output", initial)
    assert result["candidate_count"] == 4
    result = _call(capsys, "refine", initial, before, after,
                   "--before-snapshot", snapshots[0], "--after-snapshot", snapshots[1],
                   "--mode", "delta", "--delta", "3", "--output", refined)
    assert result["candidate_count"] == 2
    state = json.loads(refined.read_text())
    assert state["candidate_count"] == 2 and state["complete"] is True
    page = _call(capsys, "results", refined, after, "--snapshot", snapshots[1],
                 "--before", before, "--before-snapshot", snapshots[0], "--limit", "1")
    assert page["candidate_count"] == 2 and page["truncated"] is True
    assert page["next_offset"] == 1
    assert [(row["offset"], row["value"], row["previous_value"]) for row in page["rows"]] == [(2, 23, 20)]
    last = _call(capsys, "results", refined, after, "--snapshot", snapshots[1], "--offset", "1")
    assert [(row["offset"], row["value"]) for row in last["rows"]] == [(4, 33)]
    assert last["truncated"] is False
    assert before.read_bytes() == bytes.fromhex("0a0014001e002800")
    assert after.read_bytes() == bytes.fromhex("0a00170021002800")
    assert all(path.stat().st_mode & 0o077 == 0 for path in (*snapshots, initial, refined))


@pytest.mark.parametrize("problem", ["context", "bytes", "capture"])
def test_refinement_refuses_incompatible_observations_without_output(tmp_path, capsys, problem):
    from dotbox.memory_search import snapshot_metadata, start_search

    before, after = b"\x01\x02", b"\x01\x03"
    context = _context(2)
    previous = snapshot_metadata(before, context=context, capture_id="before")
    next_context = dict(context, run_id="other") if problem == "context" else context
    current = snapshot_metadata(after, context=next_context,
                                capture_id="before" if problem == "capture" else "after")
    before_path, after_path = tmp_path / "before.bin", tmp_path / "after.bin"
    before_path.write_bytes(before)
    after_path.write_bytes(b"\xff\x03" if problem == "bytes" else after)
    state = _json(tmp_path / "state.json", start_search(before, previous))
    before_meta = _json(tmp_path / "before.json", previous)
    after_meta = _json(tmp_path / "after.json", current)
    output = tmp_path / "refused.json"
    assert cli.main(["memory-search", "refine", str(state), str(before_path), str(after_path),
                     "--before-snapshot", str(before_meta), "--after-snapshot", str(after_meta),
                     "--mode", "changed", "--output", str(output)]) == 1
    reply = capsys.readouterr()
    assert not reply.out and json.loads(reply.err)["ok"] is False
    assert not output.exists()


def test_outputs_are_new_private_files_outside_git(tmp_path, capsys):
    source = tmp_path / "frozen.bin"
    source.write_bytes(b"\x01\x02")
    context = _json(tmp_path / "context.json", _context(2))
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    repository = tmp_path / "repo"
    repository.mkdir(mode=0o700)
    (repository / ".git").mkdir()
    alias = tmp_path / "alias.json"
    alias.symlink_to(source)
    for destination in (source, alias, shared / "report.json", repository / "report.json"):
        assert cli.main(["memory-search", "snapshot", str(source), "--context", str(context),
                         "--capture-id", "fixture", "--output", str(destination)]) == 1
        assert json.loads(capsys.readouterr().err)["ok"] is False
    assert source.read_bytes() == b"\x01\x02"
    assert not (shared / "report.json").exists()
    assert not (repository / "report.json").exists()


def test_cli_rejects_oversized_input_and_invalid_json(tmp_path, capsys):
    from dotbox import memory_search

    source = tmp_path / "large.bin"
    with source.open("wb") as stream:
        stream.truncate(memory_search._kernel.MAX_SNAPSHOT_BYTES + 1)
    context = _json(tmp_path / "context.json", _context())
    output = tmp_path / "output.json"
    args = ["memory-search", "snapshot", str(source), "--context", str(context),
            "--capture-id", "fixture", "--output", str(output)]
    assert cli.main(args) == 1
    assert "budget" in json.loads(capsys.readouterr().err)["error"]
    source.write_bytes(b"\x01")
    context.write_text('{"source_sha256": NaN}')
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert not output.exists()


def test_shared_api_imports_in_an_isolated_interpreter_without_full_fdisbull(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src"
    script = """
import importlib.abc, json, sys
class RefuseFullApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == 'fdisbull' or name.startswith('fdisbull.'):
            raise AssertionError('Full fDisBull application imported')
sys.meta_path.insert(0, RefuseFullApplication())
sys.path.insert(0, sys.argv[1])
from dotbox.memory_search import self_check
result = self_check()
assert result['ok']
assert not any(name.startswith('dotbox.native_') for name in sys.modules)
print(json.dumps(result))
"""
    result = subprocess.run([sys.executable, "-I", "-c", script, str(source)],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["ok"] is True
