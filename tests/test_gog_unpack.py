"""Authored payloads exercise the native extractor boundary; no game fixtures."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from fdisbull.cli import main, respond


@pytest.fixture
def extractor(tmp_path, monkeypatch):
    # Fake only the external Inno Setup reader, never the importer or filesystem.
    import fdisbull.gog_unpack as module
    installer = tmp_path / "setup owned game.exe"
    installer.write_bytes(b"authored installer input")
    payloads = {"GAME/MAIN.EXE": b"MZ" + bytes(126),
                "GAME/SOUND.DRV": b"MZ" + bytes(70),
                "GAME/DATA.TXT": b"authored game data"}
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs.get("shell", False) is False
        assert args[0] == "/native/innoextract"
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "innoextract 1.9\n", "")
        assert args[-1] == str(installer)
        selected = dict(payloads)
        if "--include" in args:
            include = args[args.index("--include") + 1]
            selected = {n: b for n, b in selected.items() if n.startswith(include)}
        if "--list" in args:
            return subprocess.CompletedProcess(args, 0, "\n".join(selected) + "\n", "")
        assert "--extract" in args
        root = Path(args[args.index("--output-dir") + 1])
        for name, data in selected.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/native/innoextract")
    monkeypatch.setattr(module.subprocess, "run", run)
    return installer, payloads, calls, module


def test_gog_commands_are_discoverable_and_need_no_project():
    response = respond({"method": "help"})
    assert "gog-list" in response["result"]["methods"]
    assert "gog-unpack" in response["result"]["methods"]


def test_list_is_read_only_and_ignores_server_default_project(extractor, tmp_path):
    installer, payloads, calls, _ = extractor
    reply = respond({"method": "gog-list", "params": {"path": str(installer)}},
                    default_project=str(tmp_path / "unused.fdb"))
    assert reply["ok"], reply
    assert reply["result"]["files"] == sorted(payloads)
    assert not any("--extract" in call for call in calls)
    assert not (tmp_path / "unused.fdb").exists()


def test_extract_preserves_bytes_records_hashes_and_discovers_driver(extractor, tmp_path):
    installer, payloads, calls, _ = extractor
    output = tmp_path / "private game"
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(output)}})
    assert reply["ok"], reply
    result = reply["result"]
    for item in result["files"]:
        original = payloads[item["path"]]
        assert (output / item["path"]).read_bytes() == original
        assert item["sha256"] == hashlib.sha256(original).hexdigest()
    assert {i["path"] for i in result["files"] if i["executable_candidate"]} == {
        "GAME/MAIN.EXE", "GAME/SOUND.DRV"}
    assert installer.read_bytes() == b"authored installer input"
    assert (output / "gog-unpack-manifest.json").is_file()
    assert len([c for c in calls if "--extract" in c]) == 1


def test_include_is_used_for_both_inventory_and_extraction(extractor, tmp_path):
    installer, _, calls, _ = extractor
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(tmp_path / "selected"),
        "include": ["GAME/MAIN.EXE"]}})
    assert reply["ok"], reply
    assert [i["path"] for i in reply["result"]["files"]] == ["GAME/MAIN.EXE"]
    assert all("GAME/MAIN.EXE" in c for c in calls if "--version" not in c)


def test_refuses_existing_destination_without_invoking_extractor(extractor, tmp_path):
    installer, _, calls, _ = extractor
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "original").write_bytes(b"keep")
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(existing)}})
    assert not reply["ok"]
    assert "exist" in reply["error"]["message"].lower()
    assert (existing / "original").read_bytes() == b"keep"
    assert calls == []


@pytest.mark.parametrize("name", ["../escape.exe", "/absolute.exe", "C:/drive.exe",
                                   "game/../../escape", "game\\escape.exe"])
def test_rejects_unsafe_inventory_before_extracting(extractor, tmp_path, name):
    installer, payloads, calls, _ = extractor
    payloads.clear()
    payloads[name] = b"authored"
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(tmp_path / "rejected")}})
    assert not reply["ok"]
    assert not any("--extract" in call for call in calls)
    assert not (tmp_path / "rejected").exists()


def test_failed_extraction_removes_only_new_destination(extractor, tmp_path, monkeypatch):
    installer, _, _, module = extractor
    original_run = module.subprocess.run

    def fail_extract(args, **kwargs):
        if "--extract" in args:
            root = Path(args[args.index("--output-dir") + 1])
            (root / "partial").write_bytes(b"partial")
            return subprocess.CompletedProcess(args, 2, "", "invalid compressed stream")
        return original_run(args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", fail_extract)
    output = tmp_path / "failed"
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(output)}})
    assert not reply["ok"]
    assert "invalid compressed stream" in reply["error"]["message"]
    assert not output.exists()
    assert installer.read_bytes() == b"authored installer input"


def test_cli_and_adjacent_multipart_input_receipt(extractor, tmp_path, capsys):
    import json
    installer, _, _, _ = extractor
    part = installer.with_name(installer.stem + "-1.bin")
    part.write_bytes(b"authored multipart input")
    assert main(["gog-unpack", str(installer), str(tmp_path / "cli")]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["ok"]
    assert {i["name"] for i in reply["result"]["inputs"]} == {installer.name, part.name}


def test_missing_reader_has_actionable_error_without_wine_fallback(extractor, monkeypatch):
    installer, _, calls, module = extractor
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    reply = respond({"method": "gog-list", "params": {"path": str(installer)}})
    assert not reply["ok"]
    assert "brew install innoextract" in reply["error"]["message"]
    assert calls == []


@pytest.mark.parametrize("names", [
    ["GAME/MAIN.EXE", "game/main.exe"], ["gog-unpack-manifest.json"]])
def test_collisions_are_refused_before_extraction(extractor, tmp_path, names):
    installer, payloads, calls, _ = extractor
    payloads.clear()
    payloads.update({name: b"authored" for name in names})
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(tmp_path / "collision")}})
    assert not reply["ok"]
    assert not any("--extract" in call for call in calls)


@pytest.mark.parametrize("failure", ["unexpected", "symlink", "timeout", "changed_input"])
def test_incomplete_or_unqualified_results_are_not_published(extractor, tmp_path, monkeypatch, failure):
    installer, _, _, module = extractor
    original_run = module.subprocess.run

    def alter_extract(args, **kwargs):
        result = original_run(args, **kwargs)
        if "--extract" in args:
            root = Path(args[args.index("--output-dir") + 1])
            if failure == "unexpected": (root / "extra").write_bytes(b"extra")
            elif failure == "symlink":
                path = root / "GAME/MAIN.EXE"
                path.unlink()
                path.symlink_to(installer)
            elif failure == "timeout": raise subprocess.TimeoutExpired(args, 300)
            else: installer.write_bytes(b"changed authored input")
        return result

    monkeypatch.setattr(module.subprocess, "run", alter_extract)
    output = tmp_path / failure
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(output)}})
    assert not reply["ok"]
    assert not output.exists()


def test_empty_selection_leaves_no_output(extractor, tmp_path):
    installer, _, calls, _ = extractor
    reply = respond({"method": "gog-unpack", "params": {
        "path": str(installer), "output": str(tmp_path / "empty"), "include": ["absent/"]}})
    assert not reply["ok"]
    assert "No files matched" in reply["error"]["message"]
    assert not any("--extract" in call for call in calls)
