"""Independent SQLite storage for DotBox's source-bound control metadata.

The immutable manifest/binding shape follows fDisBull input_macros.py at
ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9. This is not an FDB: it contains no
mapped game bytes, analysis, source object store or debugger history. Both
source and version hashes attest the actual supplied executable bytes.
"""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sqlite3


FORMAT = "dotbox-control-store-1"
MAX_PROGRAM_BYTES = 64 * 1024 * 1024
_DDL = """
CREATE TABLE dotbox_store_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE versions(id INTEGER PRIMARY KEY CHECK(id=1), sha256 TEXT NOT NULL);
"""


def _source(program):
    path = Path(program).expanduser().resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_PROGRAM_BYTES:
        raise ValueError("program must be a regular file of 1 byte through 64 MiB")
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_PROGRAM_BYTES:
                raise ValueError("program exceeds 64 MiB")
            sha.update(chunk)
    if size == 0:
        raise ValueError("program must not be empty")
    return {"filename": path.name, "source_sha256": sha.hexdigest()}


class ControlStore:
    """Open a native control store, creating it only with an actual program.

    Existing non-DotBox databases, including FDBs, are rejected before writes.
    Supplying a program on reopen verifies both recorded filename and bytes.
    """

    def __init__(self, path, program=None):
        self.path = Path(path).expanduser().resolve()
        self.db = None
        supplied = _source(program) if program is not None else None
        created = False
        if not self.path.exists():
            if supplied is None:
                raise ValueError("program is required to create a control store")
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            created = True
        try:
            self.db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            if created:
                with self.transaction(True):
                    for statement in _DDL.split(";"):
                        if statement.strip():
                            self.db.execute(statement)
                    self.db.executemany("INSERT INTO dotbox_store_metadata VALUES (?,?)", [
                        ("format", FORMAT), *supplied.items(),
                    ])
                    self.db.execute("INSERT INTO versions VALUES (1,?)", (supplied["source_sha256"],))
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "dotbox_store_metadata" not in tables:
                raise ValueError("Existing database is not a DotBox control store; fDisBull FDB migration is required. Use a new store path; the original was not modified")
            metadata = dict(self.db.execute("SELECT key,value FROM dotbox_store_metadata"))
            if (set(metadata) != {"format", "filename", "source_sha256"}
                    or metadata["format"] != FORMAT
                    or not metadata["filename"] or len(metadata["filename"]) > 4096
                    or Path(metadata["filename"]).name != metadata["filename"]
                    or re.fullmatch(r"[0-9a-f]{64}", metadata["source_sha256"]) is None):
                raise ValueError("Invalid DotBox control store metadata")
            versions = self.db.execute("SELECT id,sha256 FROM versions").fetchall()
            if len(versions) != 1 or tuple(versions[0]) != (1, metadata["source_sha256"]):
                raise ValueError("Invalid DotBox control store source version binding")
            self.meta = {key: metadata[key] for key in ("filename", "source_sha256")}
            if supplied is not None and supplied != self.meta:
                raise ValueError("program filename or source bytes do not match the existing control store")
        except BaseException:
            self.close()
            raise

    def version(self, value=1):
        if type(value) is not int or value != 1:
            raise ValueError("Unknown control store source version; only version 1 is supported")
        row = self.db.execute("SELECT id,sha256 FROM versions WHERE id=1").fetchone()
        if row is None or row["sha256"] != self.meta["source_sha256"]:
            raise ValueError("Control store source version binding mismatch")
        return dict(row)

    def source_binding_sha256(self, version=1):
        return self.version(version)["sha256"]

    @contextmanager
    def transaction(self, write=False):
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield self
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
