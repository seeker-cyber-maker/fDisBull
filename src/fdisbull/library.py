"""Read-only checks against an fDisBull Game/Database Library registry.

The library is a host-local session catalog, not an FDB.  This module only
consumes registered SHA-256 identities.  It never creates a library, writes a
registry, hashes files, or treats a match as proof of semantic validity.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from collections.abc import Iterable
from urllib.parse import quote

DEFAULT_CONFIG = Path.home() / ".config" / "fdisbull" / "libraries.json"
DEFAULT_DATABASE_ROOT = Path.home() / ".local" / "share" / "fdisbull" / "databases"
SCOPE = (
    "Exact SHA-256 equality with registered library rows. A match establishes "
    "registered content identity only; it does not prove intake success, "
    "semantic validity, loader support or runtime acceptance."
)
_DIGEST_NAMES = {"sha256", "content_sha256", "digest", "content_digest", "hash"}
_META_NAMES = (
    "path",
    "name",
    "file",
    "member",
    "intake",
    "status",
    "edition",
    "game",
    "analysis",
    "source",
    "size",
    "operation",
)


def _as_path(value):
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return None


def _first_path(config, keys):
    for key in keys:
        value = config.get(key)
        if isinstance(value, dict):
            value = value.get("path") or value.get("root")
        path = _as_path(value)
        if path is not None:
            return path
    roots = config.get("roots")
    if isinstance(roots, dict):
        for key in keys:
            path = _as_path(roots.get(key))
            if path is not None:
                return path
    return None


def _first_value(config, keys):
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _load_config(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as error:
        return None, f"cannot read libraries config: {error}"
    if not isinstance(data, dict):
        return None, "libraries config must be a JSON object"
    return data, None


def _connect_readonly(path):
    uri = "file:" + quote(str(path.resolve()), safe="/:") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _quote_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _tables(connection):
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _columns(connection, table):
    return [
        row[1]
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
    ]


def _digest_columns(columns):
    return [
        column
        for column in columns
        if column.casefold() in _DIGEST_NAMES
        or "sha256" in column.casefold()
        or "digest" in column.casefold()
    ]


def _meta_columns(columns, digest):
    found = []
    for column in columns:
        if column == digest:
            continue
        lowered = column.casefold()
        if any(token in lowered for token in _META_NAMES):
            found.append(column)
    return found[:12]


def _safe_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)


def _lookup(connection, wanted):
    matches = {}
    for table in _tables(connection):
        columns = _columns(connection, table)
        for digest_column in _digest_columns(columns):
            metadata = _meta_columns(columns, digest_column)
            selected = [digest_column, *metadata]
            projection = ", ".join(_quote_identifier(name) for name in selected)
            for offset in range(0, len(wanted), 400):
                batch = wanted[offset : offset + 400]
                placeholders = ",".join("?" for _ in batch)
                query = (
                    f"SELECT {projection} FROM {_quote_identifier(table)} "
                    f"WHERE lower({_quote_identifier(digest_column)}) IN ({placeholders})"
                )
                for row in connection.execute(query, batch):
                    digest = str(row[0]).lower()
                    if len(digest) != 64:
                        continue
                    record = {
                        "table": table,
                        "sha256": digest,
                        **{
                            name: _safe_value(row[name])
                            for name in metadata
                            if row[name] is not None
                        },
                    }
                    matches.setdefault(digest, []).append(record)
    return matches


def _intake_value(record):
    for key, value in record.items():
        if key.casefold() in {"intake_status", "intake", "intake_result"}:
            return value
    for key, value in record.items():
        if key.casefold() in {"status", "state"}:
            return value
    return "unknown"


class LibraryIndex:
    """A discovered, read-only library configuration and registry."""

    def __init__(
        self, config, config_path, game_root, database_root, registry, error=None
    ):
        self.config = config
        self.config_path = config_path
        self.game_root = game_root
        self.database_root = database_root
        self.registry = registry
        self.error = error

    @property
    def configured(self):
        return self.config is not None

    def check(self, entries: Iterable[tuple[str, str]]) -> dict:
        """Check ``(path, sha256)`` pairs against registered library rows."""
        rows = []
        seen = set()
        for path, digest in entries:
            key = str(digest).lower()
            if len(key) != 64 or key in seen:
                continue
            seen.add(key)
            rows.append((str(path), key))
        result = {
            "format": "fdisbull-library-check-1",
            "status": "not_configured",
            "config": str(self.config_path) if self.config_path else None,
            "game_root": str(self.game_root) if self.game_root else None,
            "database_root": str(self.database_root) if self.database_root else None,
            "registry": str(self.registry) if self.registry else None,
            "checked": len(rows),
            "present": 0,
            "scope": SCOPE,
        }
        if not rows:
            result["status"] = "empty"
            return result
        if not self.configured:
            result["detail"] = (
                "No libraries.json was found or supplied; no registered identity was checked."
            )
            return result
        if self.registry is None or not self.registry.is_file():
            result["status"] = "unavailable"
            result["detail"] = (
                "The configured library registry is absent or not a regular file."
            )
            return result
        wanted = sorted({digest for _, digest in rows})
        try:
            connection = _connect_readonly(self.registry)
            try:
                found = _lookup(connection, wanted)
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as error:
            result["status"] = "unavailable"
            result["detail"] = f"cannot query library registry: {error}"
            return result
        matched = []
        unregistered = []
        present = 0
        intake_values = set()
        for path, digest in rows:
            records = found.get(digest, [])
            if records:
                present += 1
                intake = [_intake_value(record) for record in records[:3]]
                intake_values.update(value for value in intake if value != "unknown")
                matched.append(
                    {
                        "path": path,
                        "sha256": digest,
                        "records": records[:3],
                        "record_count": len(records),
                        "intake": intake,
                    }
                )
            else:
                unregistered.append({"path": path, "sha256": digest})
        result.update(
            status=(
                "matched"
                if present == len(rows)
                else "partial"
                if present
                else "not_found"
            ),
            present=present,
            matches=matched[:64],
            match_count=len(matched),
            unregistered=unregistered[:64],
            unregistered_count=len(unregistered),
            already_present=present == len(rows),
            already_intaken=present == len(rows) and bool(intake_values),
            intake=sorted(intake_values) if intake_values else "unknown",
        )
        return result


def discover(config_path=None):
    """Find the configured Game/Database Library roots without creating them."""
    explicit = config_path is not None
    if config_path is None:
        config_path = os.environ.get("FDISBULL_LIBRARIES_CONFIG") or DEFAULT_CONFIG
    path = Path(config_path).expanduser()
    config = None
    error = None
    if path.is_file():
        config, error = _load_config(path)
    elif explicit or path.exists():
        error = "libraries config is not a regular file"
    game_root = None
    database_root = None
    registry = None
    if config is not None:
        game_root = _first_path(
            config, ("game_root", "games", "game_library", "game_library_root")
        )
        database_root = _first_path(
            config,
            ("database_root", "databases", "database_library", "database_library_root"),
        )
        registry = _first_path(
            config, ("registry", "registry_path", "database_library_registry")
        )
    if registry is None and database_root is not None:
        registry = database_root / "library.sqlite3"
    if registry is None and DEFAULT_DATABASE_ROOT.is_dir():
        registry = DEFAULT_DATABASE_ROOT / "library.sqlite3"
    return LibraryIndex(config, path, game_root, database_root, registry, error=error)


def check_library(entries, config_path=None):
    """Convenience wrapper used by format adapters."""
    return discover(config_path).check(entries)
