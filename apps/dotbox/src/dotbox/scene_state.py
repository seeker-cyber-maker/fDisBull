"""Private provider observation memory, without a second game-state engine.

Provider revisions order observations before delivery. Recording a packet never
executes an action, applies predicted effects or certifies live freshness. Facts
omitted by a later sparse observation remain historical reports, not current
facts, and are never silently changed to false or removed.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat

from . import scenes


FORMAT = "dotbox-scene-state-1"
CLAIM = "Persisted provider reports only; no independent recognition or live freshness verification"
_DDL = """
CREATE TABLE scene_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE scene_head(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
 scene_sha256 TEXT NOT NULL, document TEXT NOT NULL);
CREATE TABLE scene_facts(identity TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
 revision INTEGER NOT NULL, document TEXT NOT NULL);
"""


def _binding(packet):
    context = packet["state_context"]
    return {"source_sha256": packet["source_sha256"], "edition": packet["edition"],
            "selection_sha256": packet.get("selection_sha256"),
            **{key: context[key] for key in ("provider_id", "session_id", "branch_id")}}


def _as_of(packet, digest):
    return {"observed_revision": packet["state_context"]["revision"],
            "observed_scene_id": packet["scene_id"], "observed_observation_id": packet["observation_id"],
            "observed_scene_sha256": digest}


def _identity(packet, fact):
    if "entity_id" in fact:
        return ["entity", fact["entity_id"], fact["predicate"]]
    return ["scene", packet["scene_id"], fact["subject"], fact["predicate"]]


class SceneStore:
    """Latest snapshot and last reported facts for one provider session branch.

    A provider assigns each revision at coherent observation time, before a
    result is queued or sent to a worker. Arrival time cannot order snapshots.
    Restores and forks require a different branch and a new store; this object
    has no reset or merge operation. Reopening does not reobserve the game.
    Provider entity IDs join observations across scenes. Without one, a subject
    is local to its scene; unrelated objects with the same label stay separate.
    """

    def __init__(self, path, *, create=False):
        self.path, self.db = Path(path).expanduser().absolute(), None
        if self.path.is_symlink():
            raise ValueError("Scene store must be a private owned regular file (0600)")
        if not self.path.exists() and not create:
            raise ValueError("Scene store does not exist; record an observation with create=True first")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ValueError("Scene store requires a private owned directory (0700)")
        created = not self.path.exists()
        if created:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Scene store must be a private owned regular file (0600)")
        try:
            self.db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            if created:
                with self._transaction(write=True):
                    for statement in _DDL.split(";"):
                        if statement.strip():
                            self.db.execute(statement)
                    self.db.execute("INSERT INTO scene_meta VALUES ('format',?)", (FORMAT,))
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {"scene_meta", "scene_head", "scene_facts"}:
                raise ValueError("Existing file is not a DotBox scene store; it was not changed")
            meta = dict(self.db.execute("SELECT key,value FROM scene_meta"))
            if meta.get("format") != FORMAT or set(meta) - {"format", "binding", "latest_outcome"}:
                raise ValueError("Scene store format does not match")
            columns = [row[1] for row in self.db.execute("PRAGMA table_info(scene_facts)")]
            if columns != ["identity", "subject", "predicate", "revision", "document"]:
                raise ValueError("Scene store fact identity format does not match")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    @contextmanager
    def _transaction(self, *, write=False):
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _head(self):
        row = self.db.execute("SELECT * FROM scene_head WHERE id=1").fetchone()
        if row is None:
            raise ValueError("Scene store has no recorded observation")
        packet = scenes.validate_scene(json.loads(row["document"]))
        if ("state_context" not in packet or packet["state_context"]["revision"] != row["revision"]
                or scenes._digest(packet) != row["scene_sha256"]):
            raise ValueError("Stored scene snapshot identity does not match")
        return packet

    def record(self, packet):
        """Record a newer provider snapshot; never apply an action's expected effects."""
        packet = scenes.validate_scene(packet)
        if "state_context" not in packet:
            raise ValueError("Persistent scene observations require state_context")
        binding, revision, digest = _binding(packet), packet["state_context"]["revision"], scenes._digest(packet)
        with self._transaction(write=True):
            old_binding = self.db.execute("SELECT value FROM scene_meta WHERE key='binding'").fetchone()
            if old_binding is not None and json.loads(old_binding[0]) != binding:
                raise ValueError("Scene source, edition, selection or provider/session/branch binding differs; use a new store")
            previous = self.db.execute("SELECT revision,scene_sha256 FROM scene_head WHERE id=1").fetchone()
            status = "recorded"
            if previous is not None:
                if revision < previous["revision"]:
                    raise ValueError("Stale provider revision; delayed observations cannot replace current state")
                if revision == previous["revision"]:
                    if digest != previous["scene_sha256"]:
                        raise ValueError("Conflicting observation at the same provider revision")
                    status = "unchanged"
            if status == "recorded":
                if old_binding is None:
                    self.db.execute("INSERT INTO scene_meta VALUES ('binding',?)", (scenes._encode(binding),))
                self.db.execute("INSERT OR REPLACE INTO scene_head VALUES (1,?,?,?)",
                                (revision, digest, scenes._encode(packet)))
                for fact in scenes._current(packet):
                    identity = _identity(packet, fact)
                    report = {**fact, "identity_scope": identity[0], **_as_of(packet, digest)}
                    self.db.execute("INSERT OR REPLACE INTO scene_facts VALUES (?,?,?,?,?)",
                                    (scenes._encode(identity), fact["subject"], fact["predicate"],
                                     revision, scenes._encode(report)))
                if "outcome" in packet:
                    outcome = {"outcome": packet["outcome"], **_as_of(packet, digest)}
                    self.db.execute("INSERT OR REPLACE INTO scene_meta VALUES ('latest_outcome',?)",
                                    (scenes._encode(outcome),))
            return {"format": FORMAT, "status": status, "revision": revision,
                    "scene_id": packet["scene_id"], "observation_id": packet["observation_id"],
                    "scene_sha256": digest, "scope": "persisted_snapshot_only", "claim": CLAIM}

    def current(self):
        """Return the latest stored packet, without refreshing its live state."""
        with self._transaction():
            return self._head()

    def memory(self, subject=None, limit=128):
        """Internal last reports; absence from the latest packet is historical."""
        if subject is not None:
            scenes._text(subject, "subject", 256)
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("Memory limit must be an integer in 1..256")
        with self._transaction():
            packet = self._head()
            revision = packet["state_context"]["revision"]
            query = "SELECT document FROM scene_facts"
            parameters = []
            if subject is not None:
                query += " WHERE subject=?"
                parameters.append(subject)
            query += " ORDER BY revision DESC,subject,predicate,identity LIMIT ?"
            rows = self.db.execute(query, (*parameters, limit + 1)).fetchall()
            reports = [json.loads(row[0]) for row in rows[:limit]]
            for report in reports:
                report["current_in_snapshot"] = report["observed_revision"] == revision
            row = self.db.execute("SELECT value FROM scene_meta WHERE key='latest_outcome'").fetchone()
            outcome = json.loads(row[0]) if row is not None else None
            if outcome is not None:
                outcome["current_in_snapshot"] = outcome["observed_revision"] == revision
            return {"format": "dotbox-scene-memory-1", "scope": "internal_only", "binding": _binding(packet),
                    "head": {"revision": revision, "scene_id": packet["scene_id"],
                             "observation_id": packet["observation_id"], "scene_sha256": scenes._digest(packet)},
                    "facts": reports, "latest_outcome": outcome, "has_more": len(rows) > limit,
                    "claim": CLAIM}

    def present(self, detail="normal", choice_limit=3):
        with self._transaction():
            return {**scenes.project_scene(self._head(), detail=detail, choice_limit=choice_limit),
                    "scope": "persisted_snapshot_only"}

    def look(self, detail="normal"):
        with self._transaction():
            return {**scenes.look_scene(self._head(), detail=detail), "scope": "persisted_snapshot_only"}

    def choose(self, choice_id, expected_scene_sha256, expected_observation_id):
        """Select atomically against the stored head; the live provider must recheck."""
        with self._transaction():
            return {**scenes.select_choice(self._head(), choice_id, expected_scene_sha256, expected_observation_id),
                    "scope": "persisted_snapshot_only"}
