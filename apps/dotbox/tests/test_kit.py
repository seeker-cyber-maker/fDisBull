"""The ordinary installation must carry its tools and operational resources."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_guide_is_available_without_a_game_or_session():
    from dotbox.kit import guide

    text = guide()
    assert "act now" in text
    assert "15 seconds" in text
    assert "dotbox guide --topic" in text


def test_doctor_distinguishes_offline_readiness_from_native_qualification():
    from dotbox.kit import doctor

    report = doctor()
    assert report["offline_learning_ready"] is True
    assert report["native_runtime_qualified"] is False
    assert report["resources"]["verified"] > 15
    assert report["inspection"]["ok"] is True
    assert report["inspection"]["decoder"]["version"] == "1.22.0"
    assert report["learning"]["clock_identity_available"] is True
    assert report["learning"]["store_opened"] is False
    assert report["scenes"]["ok"] is True
    assert report["scenes"]["checks"]["selection_has_no_execution"] is True
    assert report["agi"]["ok"] is True
    assert report["agi"]["qualified_interactions"] == 0
    assert report["navigation"]["ok"] is True
    assert report["navigation"]["checks"]["portal_boundary"] is True


@pytest.mark.parametrize("component", ["agi", "navigation"])
def test_doctor_requires_each_packaged_offline_tool(monkeypatch, component):
    from dotbox import agi, kit, navigation

    module = {"agi": agi, "navigation": navigation}[component]
    monkeypatch.setattr(module, "self_check", lambda: {"ok": False, "error": "authored failure"})
    report = kit.doctor()
    assert report["offline_learning_ready"] is False
    assert report[component]["error"] == "authored failure"


def test_export_has_verified_native_recipe_guides_notices_and_helpers(tmp_path):
    from dotbox.kit import export_resources

    destination = tmp_path / "kit"
    result = export_resources(destination)
    catalog = json.loads((destination / "catalog.json").read_text())
    for name in ("skills/dotbox-play/SKILL.md", "native/build-recipe.json",
                 "native/dosbox-x/COPYING", "native/dosbox-x/NOTICES.md",
                 "scripts/prepare_native.py", "docs/AGENT_START.md",
                 "docs/ENGINE_AWARE_PREPARATION.md", "docs/NAVIGATION.md",
                 "docs/RECOVERY_AND_SAVES.md", "docs/EXTRACTION.md",
                 "docs/AITD_REUSE.md",
                 "examples/navigation_room.json"):
        data = (destination / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == catalog["files"][name]["sha256"]
        assert len(data) == catalog["files"][name]["size"]
    assert result["files"] == len(catalog["files"])
    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o700
        assert (destination / "native/build-recipe.json").stat().st_mode & 0o777 == 0o600
    run = subprocess.run([sys.executable, str(destination / "scripts/prepare_native.py"), "--help"],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "upstream" in run.stdout


def test_export_preserves_existing_destination(tmp_path):
    from dotbox.kit import export_resources

    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("player file")
    with pytest.raises(FileExistsError):
        export_resources(destination)
    assert list(destination.iterdir()) == [marker]
    assert marker.read_text() == "player file"


def test_unknown_guide_topic_is_refused():
    from dotbox.kit import guide

    with pytest.raises(ValueError, match="topic"):
        guide("../../private")


@pytest.mark.parametrize("error_type", [ValueError, subprocess.SubprocessError])
def test_doctor_refuses_readiness_without_a_stable_clock(monkeypatch, error_type):
    from dotbox import kit, learning

    def unavailable():
        raise error_type("Clock identity unavailable")
    monkeypatch.setattr(learning, "clock_identity", unavailable)
    report = kit.doctor()
    assert report["offline_learning_ready"] is False
    assert "Clock identity unavailable" in report["error"]


@pytest.mark.parametrize("alteration", ["bytes", "missing", "catalog", "catalog_list", "manifest_list"])
def test_packaged_resources_refuse_tampering(tmp_path, monkeypatch, alteration):
    from dotbox import kit

    package = tmp_path / "package"
    package.mkdir()
    manifest = kit.resources.files("dotbox").joinpath("resources_manifest.json").read_bytes()
    (package / "resources_manifest.json").write_bytes(manifest)
    kit.export_resources(package / "resources")
    resource = package / "resources/docs/AGENT_START.md"
    if alteration == "bytes":
        resource.write_text("unexpected guide")
    elif alteration == "missing":
        resource.unlink()
    elif alteration == "manifest_list":
        manifest_path = package / "resources_manifest.json"
        document = json.loads(manifest_path.read_text())
        manifest_path.write_text(json.dumps(list(document)))
    else:
        catalog_path = package / "resources/catalog.json"
        catalog = json.loads(catalog_path.read_text())
        if alteration == "catalog_list":
            catalog["files"] = list(catalog["files"])
        else:
            del catalog["files"]["docs/AGENT_START.md"]
        catalog_path.write_text(json.dumps(catalog))
    monkeypatch.setattr(kit.resources, "files", lambda _: package)
    assert kit.doctor()["offline_learning_ready"] is False
    with pytest.raises((ValueError, OSError)):
        kit.guide()
    destination = tmp_path / "refused-export"
    with pytest.raises((ValueError, OSError)):
        kit.export_resources(destination)
    assert not destination.exists()


@pytest.mark.parametrize("arguments", [
    ["guide"], ["doctor"], ["inspect", "--help"], ["learn", "--help"],
    ["scene", "--help"],
])
def test_offline_cli_never_opens_a_live_client(arguments, monkeypatch, capsys):
    from dotbox import cli

    def forbidden(*args, **kwargs):
        pytest.fail("Offline kit tried to construct a live Client")
    monkeypatch.setattr(cli, "Client", forbidden)
    try:
        code = cli.main(arguments)
    except SystemExit as error:
        code = error.code
    assert code == 0
    assert capsys.readouterr().out


def test_top_level_help_discovers_the_kit(capsys):
    from dotbox.cli import main

    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert all(command in output for command in ("doctor", "guide", "inspect", "learn", "kit-export", "scene"))


@pytest.mark.parametrize("name,choice_id,count", [
    ("mailbox", "open_mailbox", 1), ("station", "inspect_radio", 4), ("barrel", "look_inside", 1),
])
def test_exported_scene_examples_work_through_the_offline_cli(tmp_path, monkeypatch, capsys,
                                                            name, choice_id, count):
    from dotbox import cli
    from dotbox.kit import export_resources, guide

    def forbidden(*args, **kwargs):
        pytest.fail("Scene projection/selection opened a live Client")
    monkeypatch.setattr(cli, "Client", forbidden)
    root = tmp_path / "source-kit"
    export_resources(root)
    example = root / "examples" / ("scene_" + name + ".json")
    before = example.read_bytes()
    assert cli.main(["scene", "present", str(example), "--detail", "detailed"]) == 0
    view = json.loads(capsys.readouterr().out)["result"]
    assert len(view["choices"]) == count
    assert "guide_claims" not in view
    if name == "barrel":
        assert "pouch" not in json.dumps(view).lower()
    assert cli.main(["scene", "choose", str(example), "--choice", choice_id,
                     "--scene-sha256", view["scene_sha256"], "--observation-id", view["observation_id"]]) == 0
    intent = json.loads(capsys.readouterr().out)["result"]
    assert intent["execution"] == "not_performed"
    assert intent["choice_id"] == choice_id
    assert example.read_bytes() == before
    assert "conversational interface" in guide("conversation")
    assert "two or three" in guide("guides").lower()
