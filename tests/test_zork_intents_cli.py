"""Private export boundaries; authored fixtures do not qualify a Zork edition."""
import gzip
import json

from fdisbull.cli import main
from fdisbull.zork_intent_export import export_intents
from test_zork_intents_mapper import authored_bindings, authored_story


def test_cli_refuses_an_unqualified_edition_without_writing(authored_story, tmp_path, capsys):
    destination = tmp_path / "partial-intents.json.gz"
    assert main(["zork-intents", str(authored_story), "--output", str(destination)]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert "exact Zork I" in receipt["error"]
    assert not destination.exists()


def test_preflight_checks_every_destination_before_creating_any(authored_story, tmp_path, capsys):
    destination, keep = tmp_path / "new-package.json", tmp_path / "keep.json"
    keep.write_text("preserve")
    assert main(["zork-intents", str(authored_story), "--output", str(destination),
                 "--uil", str(keep)]) == 1
    assert "replace existing" in json.loads(capsys.readouterr().out)["error"]
    assert keep.read_text() == "preserve"
    assert not destination.exists()


def test_duplicate_and_input_destinations_are_rejected(authored_story, tmp_path, capsys):
    original = authored_story.read_bytes()
    destination = tmp_path / "new.json"
    assert main(["zork-intents", str(authored_story), "--output", str(destination),
                 "--udl", str(destination)]) == 1
    assert "distinct" in json.loads(capsys.readouterr().out)["error"]
    assert main(["zork-intents", str(authored_story), "--output", str(authored_story)]) == 1
    assert "replace the story" in json.loads(capsys.readouterr().out)["error"]
    assert not destination.exists()
    assert authored_story.read_bytes() == original


def test_export_writes_the_exact_embedded_views_without_changing_supplied_ir(
        authored_story, authored_bindings, tmp_path, monkeypatch):
    # This unit test isolates file export. Real edition recovery and consumer
    # execution are qualified by separate source and behavioral checks.
    from fdisbull import zork_intent_export
    package = authored_bindings
    package["udl"]["qualification"] = {"all_game_intent_recovered": False}
    source = tmp_path / "preserved-ir.json.gz"
    source.write_bytes(gzip.compress(json.dumps(package["low_level_ir"]).encode(), mtime=0))
    original = source.read_bytes()
    observed = []

    def recovered(story, low_level_ir):
        observed.append((story, low_level_ir))
        return package

    monkeypatch.setattr(zork_intent_export, "recover_intents", recovered)
    output, uil, udl = (tmp_path / name for name in ("new.json.gz", "uil.json", "udl.json.gz"))
    result = export_intents(authored_story, output=output, ir=source, uil=uil, udl=udl)
    assert observed == [(authored_story, package["low_level_ir"])]
    assert source.read_bytes() == original
    assert json.loads(gzip.decompress(output.read_bytes())) == package
    assert json.loads(uil.read_text()) == package["uil"]
    assert json.loads(gzip.decompress(udl.read_bytes())) == package["udl"]
    assert set(result["outputs"]) == {"package", "uil", "udl"}
    assert result["qualification"]["all_game_intent_recovered"] is False
