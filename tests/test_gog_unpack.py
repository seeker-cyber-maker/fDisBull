"""Authored native GOG adapter contract tests; no original payloads or subprocesses."""

import hashlib
import json
import sqlite3
from pathlib import Path
import pytest
from fdisbull.cli import main, respond
from fdisbull.gog_unpack import _safe_inventory
from fdisbull.native_inno import (
    InnoRefused,
    Cursor,
    parse_call,
    safe_path,
    undo_call_filter_5309,
)


@pytest.fixture
def native_fixture(tmp_path, monkeypatch):
    from fdisbull import gog_unpack as module

    source = tmp_path / "installer.exe"
    source.write_bytes(b"authored setup data")
    content = {
        "GAME/MAIN.EXE": b"MZ" + bytes(126),
        "GAME/SOUND.DRV": b"MZ" + bytes(70),
        "GAME/DATA.TXT": b"authored game data",
    }
    events = []

    class Fake:
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

        @property
        def inventory(self):
            return [{"path": p} for p in content]

        def extract_selected(self, out, selected, *, emit_manifest, deadline):
            events.append(("extract", tuple(selected), emit_manifest))
            out = Path(out)
            out.mkdir()
            written = []
            for path in selected:
                child = out / path
                child.parent.mkdir(parents=True, exist_ok=True)
                payload = content[path]
                child.write_bytes(payload)
                written.append(
                    {
                        "path": path,
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            return written

    def opened(path, *, deadline):
        events.append(("opened", str(path)))
        return Fake()

    monkeypatch.setattr(module.NativeInno, "open", opened)
    return source, content, events, module


def test_discoverable():
    methods = respond({"method": "help"})["result"]["methods"]
    assert "gog-list" in methods and "gog-unpack" in methods


def test_native_list_does_not_execute_installer(native_fixture, tmp_path):
    source, content, events, _ = native_fixture
    got = respond(
        {"method": "gog-list", "params": {"path": str(source)}},
        default_project=str(tmp_path / "unused.fdb"),
    )
    assert got["ok"], got
    assert got["result"]["files"] == sorted(content)
    assert got["result"]["extractor"]["requires_innoextract"] is False
    assert all(event[0] != "extract" for event in events)
    assert not (tmp_path / "unused.fdb").exists()


def test_reconstruct_and_preserve_manifest(native_fixture, tmp_path):
    source, content, events, _ = native_fixture
    dst = tmp_path / "private"
    response = respond(
        {"method": "gog-unpack", "params": {"path": str(source), "output": str(dst)}}
    )
    assert response["ok"], response
    result = response["result"]
    assert {a["path"]: a["sha256"] for a in result["files"]} == {
        name: hashlib.sha256(payload).hexdigest() for name, payload in content.items()
    }
    assert all(
        (dst / name).read_bytes() == payload for name, payload in content.items()
    )
    assert (dst / "gog-unpack-manifest.json").is_file()
    assert result["installer_executed"] is False
    assert len([e for e in events if e[0] == "extract"]) == 1


def test_include_and_cli(native_fixture, tmp_path, capsys):
    source, content, events, _ = native_fixture
    assert (
        main(
            [
                "gog-unpack",
                "--include",
                "GAME/MAIN.EXE",
                str(source),
                str(tmp_path / "selected"),
            ]
        )
        == 0
    )
    response = json.loads(capsys.readouterr().out)
    assert response["ok"], response
    assert [a["path"] for a in response["result"]["files"]] == ["GAME/MAIN.EXE"]
    assert events[-1][1] == ("GAME/MAIN.EXE",)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("GAME/", ["GAME/DATA.TXT", "GAME/MAIN.EXE", "GAME/SOUND.DRV"]),
        ("*.EXE", ["GAME/MAIN.EXE"]),
        ("game/main.exe", ["GAME/MAIN.EXE"]),
    ],
)
def test_include_matches_directory_prefix_glob_and_case(
    native_fixture, pattern, expected
):
    source, _, _, _ = native_fixture
    response = respond(
        {"method": "gog-list", "params": {"path": str(source), "include": [pattern]}}
    )
    assert response["ok"], response
    assert response["result"]["files"] == expected


def test_refuse_existing_target(native_fixture, tmp_path):
    source, content, events, _ = native_fixture
    (tmp_path / "existing").mkdir()
    (tmp_path / "existing" / "original").write_bytes(b"do not touch")
    response = respond(
        {
            "method": "gog-unpack",
            "params": {"path": str(source), "output": str(tmp_path / "existing")},
        }
    )
    assert not response["ok"]
    assert (tmp_path / "existing" / "original").read_bytes() == b"do not touch"
    assert events == []


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "C:/drive", "a\\b", "dir/../evil", "a\x00b"]
)
def test_refuse_unsafe_paths(path):
    with pytest.raises(ValueError):
        _safe_inventory([path])


@pytest.mark.parametrize(
    "names", [["CASE.DAT", "case.dat"], ["gog-unpack-manifest.json"]]
)
def test_refuse_collisions(native_fixture, names):
    source, content, events, _ = native_fixture
    content.clear()
    content.update({name: b"x" for name in names})
    result = respond({"method": "gog-list", "params": {"path": str(source)}})
    assert not result["ok"]


def test_refuse_unknown_and_empty(native_fixture):
    source, _, _, _ = native_fixture
    response = respond(
        {"method": "gog-list", "params": {"path": str(source), "include": ["missing/"]}}
    )
    assert not response["ok"]


def test_refuse_invalid_timing(native_fixture):
    source, _, _, _ = native_fixture
    response = respond(
        {"method": "gog-list", "params": {"path": str(source), "timeout": 0}}
    )
    assert not response["ok"]


def test_failed_native_extraction_discards_only_new_destination(
    native_fixture, tmp_path, monkeypatch
):
    source, content, events, module = native_fixture

    def broken(self, out, selected, *, emit_manifest, deadline):
        out = Path(out)
        out.mkdir()
        (out / "partial").write_bytes(b"partial")
        raise InnoRefused("synthetic decompression failure")

    original_open = module.NativeInno.open

    def bad_open(path, *, deadline):
        instance = original_open(path, deadline=deadline)
        instance.extract_selected = lambda out, selected, **kw: broken(
            instance, out, selected, **kw
        )
        return instance

    monkeypatch.setattr(module.NativeInno, "open", bad_open)
    out = tmp_path / "new"
    result = respond(
        {"method": "gog-unpack", "params": {"path": str(source), "output": str(out)}}
    )
    assert not result["ok"] and not out.exists()
    assert source.read_bytes() == b"authored setup data"


def test_native_helpers_refuse_malformed():
    for path in ("..", "/abs", "x/../escape", "{foreign}/path", "foo:bar"):
        with pytest.raises(InnoRefused):
            safe_path(path)
    with pytest.raises(InnoRefused):
        parse_call("before_install('x', bad, 2)", "before_install")
    assert parse_call("before_install('md5', 'two''quotes', 2)", "before_install") == [
        "md5",
        "two'quotes",
        "2",
    ]
    assert parse_call("other()", "before_install") is None
    with pytest.raises(InnoRefused):
        Cursor(b"\x01\x00").u32()


def test_executable_filter_preserves_non_opcodes_and_block_boundary():
    assert undo_call_filter_5309(bytes([0x90, 0x90, 0x90])) == bytes([0x90, 0x90, 0x90])
    data = bytes([0x90]) * 0xFFFE + b"\xe8" + b"\x00" * 4
    assert undo_call_filter_5309(data) == data  # x86 opcode crosses 64 KiB block


def _library_config(tmp_path, content, *, intake="accepted", registry_name="library.sqlite3"):
    root = tmp_path / "games"
    root.mkdir(exist_ok=True)
    registry = tmp_path / registry_name
    connection = sqlite3.connect(registry)
    try:
        connection.execute(
            "CREATE TABLE inputs (sha256 TEXT, path TEXT, size INTEGER, intake_status TEXT)"
        )
        connection.executemany(
            "INSERT INTO inputs VALUES (?, ?, ?, ?)",
            [
                (
                    hashlib.sha256(payload).hexdigest(),
                    name,
                    len(payload),
                    intake,
                )
                for name, payload in content.items()
            ],
        )
        connection.commit()
    finally:
        connection.close()
    config = tmp_path / "libraries.json"
    config.write_text(
        json.dumps(
            {
                "game_root": str(root),
                "database_root": str(tmp_path),
                "registry": str(registry),
            }
        )
    )
    return config


def test_library_match_retains_output_hashes(native_fixture, tmp_path):
    source, content, _, _ = native_fixture
    config = _library_config(tmp_path, content)
    response = respond(
        {
            "method": "gog-unpack",
            "params": {
                "path": str(source),
                "output": str(tmp_path / "private"),
                "library_config": str(config),
            },
        }
    )
    assert response["ok"], response
    result = response["result"]
    assert result["library"]["status"] == "matched"
    assert result["library"]["present"] == len(content)
    assert result["library"]["match_count"] == len(content)
    assert result["library"]["already_present"] is True
    assert result["library"]["already_intaken"] is True
    assert result["library"]["intake"] == ["accepted"]
    assert result["library"]["matches"][0]["records"][0]["intake_status"] == "accepted"
    assert {
        item["path"]: item["sha256"] for item in result["files"]
    } == {
        name: hashlib.sha256(payload).hexdigest() for name, payload in content.items()
    }


def test_library_lists_registered_carrier(native_fixture, tmp_path):
    source, content, _, _ = native_fixture
    config = _library_config(
        tmp_path,
        {"installer.exe": source.read_bytes()},
    )
    response = respond(
        {
            "method": "gog-list",
            "params": {"path": str(source), "library_config": str(config)},
        }
    )
    assert response["ok"], response
    library = response["result"]["library"]
    assert library["status"] == "matched"
    assert library["checked"] == 1
    assert library["present"] == 1
    assert library["matches"][0]["records"][0]["path"] == "installer.exe"


def test_library_reports_partial_registration(native_fixture, tmp_path):
    source, content, _, _ = native_fixture
    partial = dict(content)
    partial.pop("GAME/DATA.TXT")
    config = _library_config(tmp_path, partial)
    response = respond(
        {
            "method": "gog-unpack",
            "params": {
                "path": str(source),
                "output": str(tmp_path / "private"),
                "library_config": str(config),
            },
        }
    )
    assert response["ok"], response
    library = response["result"]["library"]
    assert library["status"] == "partial"
    assert library["present"] == 2
    assert library["unregistered"][0]["path"] == "GAME/DATA.TXT"


def test_library_absent_does_not_block_unpack(native_fixture, tmp_path):
    source, content, _, _ = native_fixture
    response = respond(
        {
            "method": "gog-unpack",
            "params": {
                "path": str(source),
                "output": str(tmp_path / "private"),
                "library_config": str(tmp_path / "absent.json"),
            },
        }
    )
    assert response["ok"], response
    assert response["result"]["library"]["status"] == "not_configured"
    assert (tmp_path / "private" / "GAME" / "MAIN.EXE").is_file()


def test_library_missing_registry_is_reported(native_fixture, tmp_path):
    source, content, _, _ = native_fixture
    config = tmp_path / "libraries.json"
    config.write_text(
        json.dumps(
            {
                "game_root": str(tmp_path),
                "database_root": str(tmp_path),
                "registry": str(tmp_path / "missing.sqlite3"),
            }
        )
    )
    response = respond(
        {
            "method": "gog-list",
            "params": {"path": str(source), "library_config": str(config)},
        }
    )
    assert response["ok"], response
    assert response["result"]["library"]["status"] == "unavailable"
