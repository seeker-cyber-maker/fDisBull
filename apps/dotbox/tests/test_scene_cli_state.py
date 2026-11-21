"""Installed-resource state sequence and extension admission boundaries."""

from copy import deepcopy
import json

import pytest


@pytest.fixture
def examples(tmp_path):
    from dotbox.kit import export_resources

    root = tmp_path / "kit"
    export_resources(root)
    return root


def test_exported_window_sequence_records_projects_and_refuses_old_choices(examples, monkeypatch, capsys):
    from dotbox import cli

    def forbidden(*args, **kwargs):
        pytest.fail("Offline scene command constructed a live Client")

    monkeypatch.setattr(cli, "Client", forbidden)
    path = examples / "state.sqlite"
    closed = examples / "examples/scene_window_closed.json"
    opened = examples / "examples/scene_window_open.json"
    assert cli.main(["scene", "record", str(closed), "--store", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["status"] == "recorded"
    assert cli.main(["scene", "present", "--store", str(path)]) == 0
    old = json.loads(capsys.readouterr().out)["result"]
    assert "open_window" in old["suggested_choice_ids"]
    assert "lick_window" not in old["suggested_choice_ids"]
    old_args = ["--scene-sha256", old["scene_sha256"], "--observation-id", old["observation_id"]]
    assert cli.main(["scene", "choose", "--store", str(path), "--choice", "open_window", *old_args]) == 0
    intent = json.loads(capsys.readouterr().out)["result"]
    assert intent["execution"] == "not_performed"
    assert intent["state_context"]["revision"] == 1
    assert cli.main(["scene", "record", str(opened), "--store", str(path)]) == 0
    capsys.readouterr()
    assert cli.main(["scene", "choose", "--store", str(path), "--choice", "open_window", *old_args]) == 1
    assert "Stale" in json.loads(capsys.readouterr().err)["error"]
    assert cli.main(["scene", "present", "--store", str(path)]) == 0
    current = json.loads(capsys.readouterr().out)["result"]
    assert "open_window" not in {choice["id"] for choice in current["choices"]}
    assert "close_window" in current["suggested_choice_ids"]
    args = ["--scene-sha256", current["scene_sha256"], "--observation-id", current["observation_id"]]
    assert cli.main(["scene", "choose", "--store", str(path), "--choice", "lick_window", *args]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["execution"] == "not_performed"
    before = path.read_bytes()
    assert cli.main(["scene", "look", "--store", str(path)]) == 0
    description = json.loads(capsys.readouterr().out)["result"]
    assert "window is open" in description["narration"]
    assert "choice_prompt" not in description and description["execution"] == "not_performed"
    assert cli.main(["scene", "memory", "--store", str(path), "--subject", "window"]) == 0
    memory = json.loads(capsys.readouterr().out)["result"]
    assert memory["scope"] == "internal_only"
    assert memory["facts"][0]["value"] is True
    assert memory["facts"][0]["current_in_snapshot"] is True
    assert path.read_bytes() == before


@pytest.mark.parametrize("command", ["present", "look", "choose"])
def test_file_and_store_cannot_silently_select_different_observations(command, examples, capsys):
    from dotbox.scenes import main

    extra = ["--choice", "open_window", "--scene-sha256", "a" * 64, "--observation-id", "old"] if command == "choose" else []
    path = examples / "unopened.sqlite"
    args = [command, str(examples / "examples/scene_window_closed.json"), "--store", str(path), *extra]
    assert main(args) == 1
    assert "exactly one" in json.loads(capsys.readouterr().err)["error"]
    assert not path.exists()


def test_missing_store_read_does_not_start_a_new_session(tmp_path, capsys):
    from dotbox.scenes import main

    path = tmp_path / "missing" / "scene.sqlite"
    assert main(["look", "--store", str(path)]) == 1
    assert "does not exist" in json.loads(capsys.readouterr().err)["error"]
    assert not path.parent.exists()
    assert main(["memory", "--store", ""]) == 1
    assert "store path" in json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize("field,value", [
    ("revision", True), ("revision", 2**63), ("context_token", ""),
    ("ready", 1), ("enabled", "true"), ("suggestion", "force"),
])
def test_state_and_gate_values_cannot_silently_weaken_admission(field, value, examples):
    from dotbox.scenes import validate_scene

    document = json.loads((examples / "examples/scene_window_closed.json").read_text())
    target = document["state_context"] if field in document["state_context"] else document["choices"][0]
    target[field] = value
    with pytest.raises(ValueError):
        validate_scene(document)


@pytest.mark.parametrize("value", [True, 0])
def test_entity_aliases_cannot_report_contradictory_current_values(value, examples):
    from dotbox.scenes import validate_scene

    document = json.loads((examples / "examples/scene_window_closed.json").read_text())
    first = document["facts"][0]
    first["entity_id"] = "stable-window-id"
    document["facts"].append({**first, "id": "alias", "subject": "casement", "value": value})
    with pytest.raises(ValueError, match="Contradictory"):
        validate_scene(document)
    document["facts"][-1]["observation_id"] = "historical"
    validate_scene(document)


def test_entity_identity_preserves_subject_consistency_and_stays_private(examples):
    from dotbox.scenes import look_scene, project_scene, validate_scene

    document = json.loads((examples / "examples/scene_window_closed.json").read_text())
    first = document["facts"][0]
    first["entity_id"] = "PRIVATE_ENTITY_ID"
    for result in (project_scene(document), look_scene(document)):
        assert "PRIVATE_ENTITY_ID" not in json.dumps(result)
    conflicting = deepcopy(document)
    conflicting["facts"].append({**first, "id": "other", "entity_id": "different-window", "value": True})
    with pytest.raises(ValueError, match="Contradictory"):
        validate_scene(conflicting)
