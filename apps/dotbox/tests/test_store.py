"""Source attestation and failure-closed native control-store persistence."""

import hashlib
import sqlite3

import pytest

from dotbox.harness import HarnessLibrary
from dotbox.store import ControlStore, MAX_PROGRAM_BYTES


def program(tmp_path, name="PLAY.COM", content=b"\xb8\x00\x4c\xcd\x21"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_store_attests_actual_filename_and_file_hash_without_imported_bytes(tmp_path):
    source = program(tmp_path)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    path = tmp_path / "controls.db"
    with ControlStore(path, source) as store:
        assert store.meta == {"filename": "PLAY.COM", "source_sha256": expected}
        assert store.version(1) == {"id": 1, "sha256": expected}
        assert store.source_binding_sha256(1) == expected
        assert {row[0] for row in store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")} == {"dotbox_store_metadata", "versions"}
    with ControlStore(path) as reopened:
        assert reopened.meta == {"filename": "PLAY.COM", "source_sha256": expected}
    with ControlStore(path, source) as verified:
        assert verified.version(1)["sha256"] == expected
    assert source.read_bytes() not in path.read_bytes()


def test_missing_store_requires_a_real_program_without_creating_a_file(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(ValueError, match="program is required"):
        ControlStore(path)
    assert not path.exists()
    with pytest.raises(FileNotFoundError):
        ControlStore(path, tmp_path / "absent.com")
    assert not path.exists()


@pytest.mark.parametrize("change", ["bytes", "filename"])
def test_reopening_with_a_different_program_rejects_without_changing_store(tmp_path, change):
    source = program(tmp_path)
    path = tmp_path / "controls.db"
    with ControlStore(path, source):
        pass
    before = path.read_bytes()
    other = program(tmp_path, "OTHER.COM", source.read_bytes()) if change == "filename" else source
    if change == "bytes":
        source.write_bytes(b"different program")
    with pytest.raises(ValueError, match="filename or source bytes"):
        ControlStore(path, other)
    assert path.read_bytes() == before


@pytest.mark.parametrize("value", [0, 2, None, True, 1.0, "1"])
def test_store_has_exactly_one_unpatched_source_version(tmp_path, value):
    with ControlStore(tmp_path / "controls.db", program(tmp_path)) as store:
        with pytest.raises(ValueError, match="version"):
            store.version(value)
        with pytest.raises(ValueError, match="version"):
            store.source_binding_sha256(value)


def test_existing_fdb_requires_explicit_migration_and_remains_byte_identical(tmp_path):
    path = tmp_path / "existing.fdb"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE versions(id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL);
            CREATE TABLE regions(version INTEGER, data BLOB);
            INSERT INTO metadata VALUES ('filename','PLAY.COM');
            INSERT INTO regions VALUES (1,x'b8004ccd21');
        """)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="FDB migration is required"):
        ControlStore(path, program(tmp_path))
    assert path.read_bytes() == original
    with sqlite3.connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='dotbox_store_metadata'").fetchone()


def test_transaction_rolls_back_own_mutations_and_close_is_idempotent(tmp_path):
    store = ControlStore(tmp_path / "controls.db", program(tmp_path))
    with pytest.raises(RuntimeError, match="abort"):
        with store.transaction(True):
            store.db.execute("INSERT INTO versions VALUES (1, 'unreachable') ON CONFLICT(id) DO UPDATE SET sha256='changed'")
            raise RuntimeError("abort")
    assert store.version(1)["sha256"] == store.meta["source_sha256"]
    store.close()
    store.close()
    assert store.db is None


@pytest.mark.parametrize("content", [b"", None])
def test_source_size_limits_precede_store_creation(tmp_path, content):
    source = program(tmp_path, content=content or b"")
    if content is None:
        with source.open("wb") as output:
            output.truncate(MAX_PROGRAM_BYTES + 1)
    path = tmp_path / "controls.db"
    with pytest.raises(ValueError, match="regular file"):
        ControlStore(path, source)
    assert not path.exists()


@pytest.mark.parametrize("mutation", ["format", "source", "version", "filename"])
def test_reopen_rejects_corrupt_attestation_metadata(tmp_path, mutation):
    path = tmp_path / "controls.db"
    with ControlStore(path, program(tmp_path)) as store:
        if mutation == "version":
            store.db.execute("UPDATE versions SET sha256=?", ("0" * 64,))
        else:
            key, value = {"format": ("format", "future-unknown-format"),
                          "source": ("source_sha256", "invalid"),
                          "filename": ("filename", "../PLAY.COM")}[mutation]
            store.db.execute("UPDATE dotbox_store_metadata SET value=? WHERE key=?", (value, key))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="store"):
        ControlStore(path)
    assert path.read_bytes() == original


def test_version_tampering_also_rejects_an_existing_library(tmp_path):
    with ControlStore(tmp_path / "controls.db", program(tmp_path)) as store:
        library = HarnessLibrary(store)
        with store.transaction(True):
            store.db.execute("UPDATE versions SET sha256=?", ("0" * 64,))
        with pytest.raises(ValueError, match="binding mismatch"):
            library.save({"format": "dotbox-control-set-1", "name": "move", "controls": {
                "left": {"steps": [{"op": "keyboard.press", "key": "left"}]}}})
