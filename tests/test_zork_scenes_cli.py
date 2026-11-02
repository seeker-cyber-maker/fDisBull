"""Scene export/player boundaries use authored data, never bundled game assets."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

from fdisbull.cli import main
from fdisbull.zork_intents import canonical_digest, source_witness
from fdisbull.zork_scene_export import export_scenes
from fdisbull.zork_scenes import FORMAT, UDL_FORMAT, verify_bindings
from test_scene_intents import document
from test_zork_intents_mapper import authored_bindings, authored_story
from test_zork_scene_dispatch import _uil as dispatch_document


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "player"))
from fdisbull_player import __main__ as player_main
from fdisbull_player import scene_runtime


def _file_boundary_package(base):
    """An integrity-valid envelope for testing export, not a scene recovery claim.

The real producer is replaced only at its file-writer seam. The real source
integrity verifier, filesystem preflight, serialization and receipt execute.
Game-effect correspondence has separate authored and original-story checks.
    """
    image = bytes.fromhex(base["low_level_ir"]["memory"]["initial"])
    uil, dispatch = document(), dispatch_document()
    udl = {
        "format": UDL_FORMAT, "source": copy.deepcopy(base["low_level_ir"]["source"]),
        "initial_image_sha256": hashlib.sha256(image).hexdigest(),
        "base_intents_sha256": canonical_digest(base), "uil_sha256": canonical_digest(uil),
        "dispatch_uil_sha256": canonical_digest(dispatch),
        "witnesses": {"authored": source_witness(image, 0x400, 0x404, "authored file-boundary source")},
        "runtime_guards": ["authored"],
        "selection": {"source_operations": {"authored_source": 0x400}},
        "movement": {"source_operations": []}, "exits": {},
        "qualification": {"status": "authored_file_boundary_fixture", "all_game_intent_recovered": False},
    }
    package = {"format": FORMAT, "base_intents": copy.deepcopy(base),
               "uil": uil, "dispatch_uil": dispatch, "udl": udl}
    verify_bindings(package)
    return package


def _never_recover(*args, **kwargs):
    pytest.fail("Export preflight must stop before source recovery")


def test_cli_refuses_other_story_editions_and_preserves_inputs(authored_story, tmp_path, capsys):
    before = authored_story.read_bytes()
    destination = tmp_path / "scenes.json.gz"
    assert main(["zork-scenes", str(authored_story), "--output", str(destination)]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "stopped"
    assert "exact Zork I R88" in receipt["error"]
    assert not destination.exists()
    assert authored_story.read_bytes() == before


@pytest.mark.parametrize("option", ["output", "uil", "udl", "dispatch"])
def test_every_existing_destination_is_refused_before_recovery(
        authored_story, tmp_path, capsys, monkeypatch, option):
    from fdisbull import zork_scene_export
    monkeypatch.setattr(zork_scene_export, "recover_scenes", _never_recover)
    output = tmp_path / "new-package.json"
    keep = tmp_path / "keep.json"
    keep.write_bytes(b"preserve exactly")
    argv = ["zork-scenes", str(authored_story), "--output", str(keep if option == "output" else output)]
    if option != "output":
        argv += ["--" + option, str(keep)]
    assert main(argv) == 1
    assert "replace existing" in json.loads(capsys.readouterr().out)["error"]
    assert keep.read_bytes() == b"preserve exactly"
    assert not output.exists()


@pytest.mark.parametrize("alias", ["lexical", "directory_symlink"])
def test_duplicate_export_views_are_refused_after_path_resolution(
        authored_story, tmp_path, capsys, monkeypatch, alias):
    from fdisbull import zork_scene_export
    monkeypatch.setattr(zork_scene_export, "recover_scenes", _never_recover)
    output = tmp_path / "new.json"
    if alias == "lexical":
        duplicate = tmp_path / "." / "new.json"
    else:
        link = tmp_path / "linked-parent"
        link.symlink_to(tmp_path, target_is_directory=True)
        duplicate = link / "new.json"
    assert main(["zork-scenes", str(authored_story), "--output", str(output),
                 "--dispatch", str(duplicate)]) == 1
    assert "distinct" in json.loads(capsys.readouterr().out)["error"]
    assert not output.exists()


@pytest.mark.parametrize("input_kind", ["story", "intents"])
@pytest.mark.parametrize("alias", ["exact", "symlink", "hardlink"])
def test_export_never_replaces_story_or_preserved_conversion_aliases(
        authored_story, tmp_path, capsys, monkeypatch, input_kind, alias):
    from fdisbull import zork_scene_export
    monkeypatch.setattr(zork_scene_export, "recover_scenes", _never_recover)
    intents = tmp_path / "preserved-intents.json"
    intents.write_bytes(b'{"preserved":true}')
    source = authored_story if input_kind == "story" else intents
    before = source.read_bytes()
    destination = source
    if alias != "exact":
        destination = tmp_path / (alias + ".json")
        if alias == "symlink":
            destination.symlink_to(source)
        else:
            destination.hardlink_to(source)
    output = tmp_path / "new-package.json"
    assert main(["zork-scenes", str(authored_story), "--intents", str(intents),
                 "--output", str(output), "--udl", str(destination)]) == 1
    message = json.loads(capsys.readouterr().out)["error"]
    assert ("replace the story" if alias != "hardlink" else "replace existing") in message
    assert source.read_bytes() == destination.read_bytes() == before
    assert not output.exists()


def test_malformed_preserved_package_stops_without_any_export(authored_story, tmp_path, monkeypatch, capsys):
    from fdisbull import zork_scene_export
    monkeypatch.setattr(zork_scene_export, "recover_scenes", _never_recover)
    source = tmp_path / "broken.json.gz"
    source.write_bytes(gzip.compress(b'{"not complete"', mtime=0))
    before = source.read_bytes()
    output = tmp_path / "new.json"
    assert main(["zork-scenes", str(authored_story), "--intents", str(source),
                 "--output", str(output)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "stopped"
    assert not output.exists()
    assert source.read_bytes() == before


def test_game_derived_views_cannot_be_written_into_a_git_checkout(
        authored_story, tmp_path, monkeypatch, capsys):
    from fdisbull import zork_scene_export
    monkeypatch.setattr(zork_scene_export, "recover_scenes", _never_recover)
    checkout = tmp_path / "checkout"
    marker = checkout / ".git"
    marker.mkdir(parents=True)
    (marker / "HEAD").write_text("ref: refs/heads/main\n")
    output = tmp_path / "new-package.json"
    derived = checkout / "dispatch.json"
    assert main(["zork-scenes", str(authored_story), "--output", str(output),
                 "--dispatch", str(derived)]) == 1
    assert "outside a Git checkout" in json.loads(capsys.readouterr().out)["error"]
    assert not output.exists() and not derived.exists()


def test_export_writes_exact_embedded_views_and_preserves_existing_intents(
        authored_story, authored_bindings, tmp_path, monkeypatch, capsys):
    from fdisbull import zork_scene_export
    package = _file_boundary_package(authored_bindings)
    prior = tmp_path / "preserved.json.gz"
    prior.write_bytes(gzip.compress(json.dumps(authored_bindings).encode(), mtime=0))
    prior_bytes, story_bytes = prior.read_bytes(), authored_story.read_bytes()
    observed = []

    def recovered(story, base_intents):
        observed.append((story, base_intents))
        return package

    monkeypatch.setattr(zork_scene_export, "recover_scenes", recovered)
    output, uil, udl, dispatch = (tmp_path / name for name in
                                ("scenes.json.gz", "world.json", "bindings.json.gz", "dispatch.json"))
    assert main(["zork-scenes", str(authored_story), "--intents", str(prior),
                 "--output", str(output), "--uil", str(uil), "--udl", str(udl),
                 "--dispatch", str(dispatch)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert observed == [(str(authored_story), authored_bindings)]
    assert json.loads(gzip.decompress(output.read_bytes())) == package
    assert json.loads(uil.read_text()) == package["uil"]
    assert json.loads(gzip.decompress(udl.read_bytes())) == package["udl"]
    assert json.loads(dispatch.read_text()) == package["dispatch_uil"]
    assert set(receipt["outputs"]) == {"package", "uil", "udl", "dispatch_uil"}
    for role, path in (("package", output), ("uil", uil), ("udl", udl), ("dispatch_uil", dispatch)):
        assert receipt["outputs"][role]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert receipt["outputs"][role]["bytes"] == path.stat().st_size
    assert receipt["bindings"]["all_game_intent_recovered"] is False
    assert prior.read_bytes() == prior_bytes and authored_story.read_bytes() == story_bytes


def test_failed_source_integrity_is_not_exported(authored_story, authored_bindings, tmp_path, monkeypatch):
    from fdisbull import zork_scene_export
    package = _file_boundary_package(authored_bindings)
    package["uil"]["entry_scene"] = "changed_after_binding"
    monkeypatch.setattr(zork_scene_export, "recover_scenes", lambda *args, **kwargs: package)
    output, uil = tmp_path / "new.json", tmp_path / "new-uil.json"
    with pytest.raises(ValueError, match="digest changed"):
        export_scenes(authored_story, output=output, uil=uil)
    assert not output.exists() and not uil.exists()


@pytest.mark.parametrize("kind,module", [
    ("scenes", "scene_runtime"), ("intents", "intent_runtime"), ("uil", "word16"),
])
def test_player_flags_route_to_selected_consumer_with_all_continuation_options(monkeypatch, kind, module):
    import importlib
    consumer = importlib.import_module("fdisbull_player." + module)
    received = []
    monkeypatch.setattr(consumer, "main", lambda argv: received.append(argv) or 7)
    monkeypatch.setattr(sys, "argv", ["fdisbull-player", "--" + kind, "game.json.gz", "--seed", "27",
                                    "--commands", "commands.json", "--checkpoint", "checkpoint.json",
                                    "--resume", "resume.json", "--transcript", "transcript.json"])
    assert player_main.main() == 7
    assert received == [["game.json.gz", "--seed", "27", "--commands", "commands.json",
                         "--checkpoint", "checkpoint.json", "--resume", "resume.json",
                         "--transcript", "transcript.json"]]


@pytest.mark.parametrize("other", ["uil", "intents", "package", "connect", "backend-command"])
def test_scene_player_rejects_conflicting_source_modes(monkeypatch, capsys, other):
    monkeypatch.setattr(sys, "argv", ["fdisbull-player", "--scenes", "scene.json", "--" + other, "other"])
    with pytest.raises(SystemExit) as error:
        player_main.main()
    assert error.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [
    ["--live"], ["--quiet"], ["--save-dir", "state"], ["--agent-command", "agent"],
    ["--batch-plan", "plan.json", "--batch-journal", "journal.json"],
])
def test_scene_player_rejects_other_command_protocols_before_opening_inputs(monkeypatch, capsys, extra):
    monkeypatch.setattr(scene_runtime, "main", _never_recover)
    monkeypatch.setattr(sys, "argv", ["fdisbull-player", "--scenes", "absent.json", *extra])
    with pytest.raises(SystemExit) as error:
        player_main.main()
    assert error.value.code == 2
    assert "own" in capsys.readouterr().err


@pytest.mark.parametrize("output_flag,input_name", [
    ("checkpoint", "package"), ("transcript", "package"),
    ("checkpoint", "commands"), ("transcript", "commands"), ("transcript", "resume"),
])
@pytest.mark.parametrize("alias", ["exact", "symlink", "hardlink"])
def test_scene_player_preserves_every_input_alias_before_loading_package(
        tmp_path, monkeypatch, capsys, output_flag, input_name, alias):
    paths = {name: tmp_path / (name + ".json") for name in ("package", "commands", "resume")}
    for name, path in paths.items():
        path.write_text(json.dumps({"input": name}))
    source = paths[input_name]
    output = source
    if alias != "exact":
        output = tmp_path / (alias + ".json")
        if alias == "symlink":
            output.symlink_to(source)
        else:
            output.hardlink_to(source)
    before = {name: path.read_bytes() for name, path in paths.items()}
    monkeypatch.setattr(scene_runtime, "load_package", _never_recover)
    monkeypatch.setattr(sys, "argv", ["fdisbull-player", "--scenes", str(paths["package"]),
                                    "--commands", str(paths["commands"]), "--resume", str(paths["resume"]),
                                    "--" + output_flag, str(output)])
    assert player_main.main() == 1
    assert "would replace" in capsys.readouterr().err
    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_scene_player_reports_malformed_package_without_checkpoint_write(tmp_path, monkeypatch, capsys):
    package = tmp_path / "bad.json"
    package.write_bytes(b"not json")
    checkpoint = tmp_path / "checkpoint.json"
    monkeypatch.setattr(sys, "argv", ["fdisbull-player", "--scenes", str(package),
                                    "--checkpoint", str(checkpoint)])
    assert player_main.main() == 1
    assert "Program player stopped" in capsys.readouterr().err
    assert package.read_bytes() == b"not json"
    assert not checkpoint.exists()
