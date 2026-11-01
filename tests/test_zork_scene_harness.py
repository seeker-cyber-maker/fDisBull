import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("zork_scene_harness", Path(__file__).parents[1] / "examples/zork_text/scene_harness.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeAdapter:
    def __init__(self, response=None, error=None):
        self.ready = {"status": " West of House   Score: 0", "screen_sha256": "before", "lines": ["status", "Room", ">"]}
        self.response, self.error, self.commands = response, error, []

    def command(self, command):
        self.commands.append(command)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    (tmp_path / "DATA").mkdir()
    (tmp_path / "_ZORK1.COM").write_bytes(b"interpreter")
    (tmp_path / "DATA" / "ZORK1.DAT").write_bytes(b"story")
    ids = {"interpreter_sha256": module.sha256(tmp_path / "_ZORK1.COM"),
           "story_sha256": module.sha256(tmp_path / "DATA" / "ZORK1.DAT"), "backend_sha256": "backend"}
    monkeypatch.setattr(module, "PROFILE", {k: ids[k] for k in ("interpreter_sha256", "story_sha256")})
    return tmp_path, ids


def test_records_individual_boundaries_and_fresh_response(inputs, tmp_path):
    root, ids = inputs
    after = {"status": " West of House   Score: 0", "screen_sha256": "after",
             "lines": ["status", "Room", ">open mailbox", "Opening the small mailbox reveals a leaflet.", "", ">"],
             "text": ">open mailbox\nOpening the small mailbox reveals a leaflet.\n\n>"}
    adapter = FakeAdapter(after)
    with (tmp_path / "journal").open("x+") as journal:
        harness = module.SceneHarness(adapter, root, ids, "run", journal)
        event = harness.act("open_mailbox")
        journal.seek(0)
        records = [json.loads(line) for line in journal]
    assert [record["kind"] for record in records] == ["session", "intent", "result"]
    assert event["verdict"] == "observed_expected_response"
    assert event["acceptance"] == "unknown" and event["persistence"] == "unknown"
    assert adapter.commands == ["open mailbox"]


def test_wrong_scene_and_changed_story_never_send_input(inputs, tmp_path):
    root, ids = inputs
    adapter = FakeAdapter()
    with (tmp_path / "journal").open("x+") as journal:
        harness = module.SceneHarness(adapter, root, ids, "run", journal)
        assert harness.act("go_west")["input"] == "not_sent"
        (root / "DATA" / "ZORK1.DAT").write_bytes(b"different story")
        assert harness.act("open_mailbox")["input"] == "not_sent"
    assert adapter.commands == []


def test_missing_echo_stays_unknown_and_delivery_failure_is_retained(inputs, tmp_path):
    root, ids = inputs
    after = {"status": " West of House   Score: 0", "screen_sha256": "after",
             "lines": ["status", "Room", "Opening the small mailbox reveals a leaflet.", ">"],
             "text": "Opening the small mailbox reveals a leaflet.\n>"}
    adapter = FakeAdapter(after)
    with (tmp_path / "journal").open("x+") as journal:
        harness = module.SceneHarness(adapter, root, ids, "run", journal)
        assert harness.act("open_mailbox")["verdict"] == "unknown"
        adapter.error = RuntimeError("lost connection")
        result = harness.act("open_mailbox")
        assert result["kind"] == "indeterminate" and result["outcome"] == "unknown"
        journal.seek(0)
        records = [json.loads(line) for line in journal]
    assert [r["kind"] for r in records][-2:] == ["intent", "indeterminate"]


def test_old_echo_cannot_be_used_as_a_new_result():
    before = {"lines": ["status", ">open mailbox", "Opening the small mailbox reveals a leaflet.", "", ">"]}
    after = {"lines": ["status", ">open mailbox", "Opening the small mailbox reveals a leaflet.", "", ">"]}
    assert module.response_after_command(before, after, "open mailbox") is None
