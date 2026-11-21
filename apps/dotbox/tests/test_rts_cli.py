"""The installed-facing offline RTS flow stays separate from input authority."""

import json
from pathlib import Path

from dotbox import cli


def test_world_projection_and_action_preparation_are_input_free(monkeypatch, capsys, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline RTS command constructed a live client")
    monkeypatch.setattr(cli, "Client", forbidden)
    world = Path(__file__).parents[1] / "examples/rts_world.json"
    assert cli.main(["rts", "validate", str(world)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["entity_count"] == 4
    assert cli.main(["rts", "project", str(world)]) == 0
    projected = json.loads(capsys.readouterr().out)["result"]
    assert projected["choices"] == []
    packet = tmp_path / "scene.json"
    packet.write_text(json.dumps(projected))
    store = tmp_path / "state.sqlite"
    assert cli.main(["scene", "record", str(packet), "--store", str(store)]) == 0
    capsys.readouterr()
    assert cli.main(["scene", "look", "--store", str(store)]) == 0
    look = json.loads(capsys.readouterr().out)["result"]
    assert "Allied patrol" in look["narration"] and "Sand creature" in look["narration"]
    assert look["execution"] == "not_performed"
    assert cli.main(["rts", "prepare", str(world), "--primitive", "choose_action", "--arguments", '{"action_id":"move"}']) == 0
    request = json.loads(capsys.readouterr().out)["result"]
    assert request["execution"] == "not_performed" and "token" not in request
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request))
    assert cli.main(["rts", "check", str(request_file), str(world)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == request


def test_cli_rejects_changed_context_and_ambiguous_json(capsys, tmp_path):
    source = Path(__file__).parents[1] / "examples/rts_world.json"
    assert cli.main(["rts", "prepare", str(source), "--primitive", "pan_view", "--arguments", '{"position":[10,5]}']) == 0
    request = tmp_path / "request.json"
    request.write_text(json.dumps(json.loads(capsys.readouterr().out)["result"]))
    value = json.loads(source.read_text())
    value["state_context"]["revision"] += 1
    changed = tmp_path / "world.json"
    changed.write_text(json.dumps(value))
    assert cli.main(["rts", "check", str(request), str(changed)]) == 1
    assert "Stale" in json.loads(capsys.readouterr().err)["error"]
    assert cli.main(["rts", "prepare", str(source), "--primitive", "pan_view", "--arguments", '{"position":[10,5],"position":[11,5]}']) == 1
    assert "Duplicate" in json.loads(capsys.readouterr().err)["error"]


def test_catalog_does_not_promise_routes(capsys):
    assert cli.main(["rts", "primitives"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert len(result["primitives"]) == 8 and result["execution"] == "not_performed"
    assert "availability" in result["claim"]
