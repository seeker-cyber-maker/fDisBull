"""Private, source-bound planning metadata; never executes a probe or game input."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import uuid


FORMAT = "dotbox-learning-1"
DEFAULT_SECONDS = 15.0
DEFAULT_PROBES = 2
_DDL = """
CREATE TABLE learning_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE focuses(id TEXT PRIMARY KEY, context TEXT UNIQUE NOT NULL, detail TEXT NOT NULL,
 clock_id TEXT NOT NULL, started REAL NOT NULL, deadline REAL NOT NULL, max_probes INTEGER NOT NULL,
 probes INTEGER NOT NULL, last_tick REAL NOT NULL, state TEXT NOT NULL, retire_reason TEXT);
CREATE UNIQUE INDEX one_active_focus ON focuses(state) WHERE state='active';
CREATE TABLE results(id TEXT PRIMARY KEY, focus_id TEXT NOT NULL REFERENCES focuses(id), document TEXT NOT NULL);
"""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value, name, *, empty=False, limit=1024):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f"{name} must be bounded text (at most {limit} characters)")
    return value


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected a lowercase SHA-256 digest")
    return value


def clock_identity():
    """Bind monotonic time to a real boot; refuse an unsupported identity guess."""
    if sys.platform.startswith("linux"):
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        try:
            namespace = ("time", os.stat("/proc/self/ns/time").st_ino)
        except FileNotFoundError:
            # Some supported Linux runtimes expose no time namespace. Preserve
            # the real boot binding and distinguish their process namespace.
            namespace = ("pid", os.stat("/proc/self/ns/pid").st_ino)
    elif sys.platform == "darwin":
        boot = subprocess.check_output(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
                                       text=True, timeout=2).strip()
        namespace = "host"
    else:
        raise ValueError("A stable boot/monotonic clock identity is unavailable")
    uuid.UUID(boot)
    return hashlib.sha256(f"{sys.platform}:{boot}:{namespace}".encode()).hexdigest()


class LearningStore:
    """One active question with a non-renewing deadline and immutable result references.

    Source hashes, scene applicability and observed results are caller assertions.
    The store does not attest executable bytes, certify outcomes, select a control
    revision, grant ownership, or preempt a model/tool already running.
    """

    def __init__(self, path, source_sha256, *, clock=time.monotonic, clock_id=None, create=True):
        self.source = _sha(source_sha256)
        self.clock = clock
        self.clock_id = _text(clock_id if clock_id is not None else clock_identity(), "clock_id")
        self.path, self.db = Path(path).expanduser().absolute(), None
        if not self.path.exists() and not create:
            raise ValueError("Learning store does not exist; start an explicit focus first")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ValueError("Learning store requires a private owned directory (0700)")
        created = not self.path.exists()
        if created:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Learning store must be a private owned regular file (0600)")
        try:
            self.db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            if created:
                with self._transaction():
                    for statement in _DDL.split(";"):
                        if statement.strip():
                            self.db.execute(statement)
                    self.db.executemany("INSERT INTO learning_meta VALUES (?,?)",
                                        [("format", FORMAT), ("source_sha256", self.source)])
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {"learning_meta", "focuses", "results"}:
                raise ValueError("Existing file is not a DotBox learning store; it was not changed")
            if dict(self.db.execute("SELECT key,value FROM learning_meta")) != {
                    "format": FORMAT, "source_sha256": self.source}:
                raise ValueError("Learning store format or source binding does not match")
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
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _now(self):
        now = self.clock()
        try:
            valid = type(now) in (int, float) and math.isfinite(now) and now >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("Expected a finite nonnegative monotonic clock")
        return float(now)

    def _row(self, focus_id=None):
        if focus_id is None:
            return self.db.execute("SELECT * FROM focuses WHERE state='active'").fetchone()
        row = self.db.execute("SELECT * FROM focuses WHERE id=?", (focus_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown learning focus")
        return row

    def _view(self, row, now):
        detail = json.loads(row["detail"])
        clock_ok = row["clock_id"] == self.clock_id and now >= row["last_tick"]
        reason = ("clock_changed" if row["clock_id"] != self.clock_id else
                  "clock_regressed" if now < row["last_tick"] else
                  "retired" if row["state"] != "active" else
                  "deadline" if now >= row["deadline"] else
                  "probe_limit" if row["probes"] >= row["max_probes"] else "open")
        evidence = self.db.execute("SELECT document FROM results WHERE focus_id=? ORDER BY rowid DESC LIMIT 20",
                                   (row["id"],)).fetchall()
        return {"format": FORMAT, "source_sha256": self.source, "focus_id": row["id"], **detail,
                "state": row["state"], "retire_reason": row["retire_reason"],
                "started_monotonic": row["started"], "deadline_monotonic": row["deadline"],
                "elapsed_seconds": now - row["started"] if clock_ok else None,
                "remaining_seconds": max(0, row["deadline"] - now) if clock_ok else None,
                "probes_admitted": row["probes"], "max_probes": row["max_probes"],
                "budget_state": reason, "can_admit_probe": reason == "open",
                "recommendation": ("reobserve" if not clock_ok else "retired" if row["state"] != "active"
                                   else "use_fallback" if detail["fallback"] else
                                   "investigate" if reason == "open" else "report_block"),
                "recent_results": [json.loads(r[0]) for r in evidence], "scope": "planning_metadata_only"}

    def _remember_time(self, row, now):
        if row["clock_id"] == self.clock_id and now >= row["last_tick"]:
            self.db.execute("UPDATE focuses SET last_tick=? WHERE id=?", (now, row["id"]))

    def status(self, focus_id=None):
        """Inspect metadata and checkpoint its clock; this never touches the game."""
        with self._transaction():
            row, now = self._row(focus_id), self._now()
            if row is None:
                return {"format": FORMAT, "source_sha256": self.source, "focus_id": None,
                        "recommendation": "start_focus", "scope": "planning_metadata_only"}
            view = self._view(row, now)
            self._remember_time(row, now)
            return view

    def focus(self, *, context, scene, goal, question, next_interaction, fallback="",
              budget_seconds=DEFAULT_SECONDS, max_probes=DEFAULT_PROBES, retire_reason=None):
        detail = {k: _text(v, k, empty=k == "fallback") for k, v in {
            "context": context, "scene": scene, "goal": goal, "question": question,
            "next_interaction": next_interaction, "fallback": fallback}.items()}
        if (type(budget_seconds) not in (int, float) or not 0 < budget_seconds <= 180
                or type(max_probes) is not int or not 1 <= max_probes <= 16):
            raise ValueError("Budget must be 0 < seconds <= 180 and 1 <= max_probes <= 16")
        with self._transaction():
            now, active = self._now(), self._row()
            if not math.isfinite(now + budget_seconds) or now + budget_seconds <= now:
                raise ValueError("Learning deadline is outside the monotonic clock range")
            existing = self.db.execute("SELECT * FROM focuses WHERE context=?", (context,)).fetchone()
            if existing:
                previous = json.loads(existing["detail"])
                if existing["state"] != "active" or any(detail[k] != previous[k] for k in ("scene", "goal")):
                    raise ValueError("Retired or changed scene/goal requires a fresh context and explicit retirement")
                detail["started_utc"] = previous["started_utc"]
                self.db.execute("UPDATE focuses SET detail=? WHERE id=?", (_json(detail), existing["id"]))
                self._remember_time(existing, now)
                return self._view(self._row(existing["id"]), now)
            if active:
                _text(retire_reason, "retire_reason")
                if active["clock_id"] == self.clock_id and now < active["last_tick"]:
                    raise ValueError("Clock regressed; a new context cannot repair its time identity")
                self.db.execute("UPDATE focuses SET state='retired',retire_reason=? WHERE id=?",
                                (retire_reason, active["id"]))
            detail["started_utc"] = datetime.now(timezone.utc).isoformat()
            focus_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO focuses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (focus_id, context, _json(detail), self.clock_id, now, now + budget_seconds,
                             max_probes, 0, now, "active", None))
            return self._view(self._row(focus_id), now)

    def admit(self, focus_id):
        """Count permission to attempt research, never permission for game input."""
        _text(focus_id, "focus_id")
        with self._transaction():
            now, row = self._now(), self._row(focus_id)
            view = self._view(row, now)
            self._remember_time(row, now)
            if not view["can_admit_probe"]:
                return {**view, "admitted": False}
            self.db.execute("UPDATE focuses SET probes=probes+1,last_tick=? WHERE id=?", (now, focus_id))
            return {**self._view(self._row(focus_id), now), "admitted": True, "probe_number": row["probes"] + 1}

    def record(self, focus_id, result_status, evidence_ref, evidence_sha256, note=""):
        _text(focus_id, "focus_id")
        if result_status not in {"candidate", "observed", "failed"}:
            raise ValueError("Result must be candidate, observed or failed; these are caller reports")
        payload = {"focus_id": focus_id, "result_status": result_status,
                   "evidence_ref": _text(evidence_ref, "evidence_ref", limit=2048),
                   "evidence_sha256": _sha(evidence_sha256), "note": _text(note, "note", empty=True),
                   "claim": "caller_reported"}
        with self._transaction():
            row, now = self._row(focus_id), self._now()
            record_id = hashlib.sha256(_json(payload).encode()).hexdigest()
            payload.update(record_id=record_id, recorded_utc=datetime.now(timezone.utc).isoformat(),
                           focus_question_at_recording=json.loads(row["detail"])["question"],
                           elapsed_seconds=self._view(row, now)["elapsed_seconds"])
            self.db.execute("INSERT OR IGNORE INTO results VALUES (?,?,?)", (record_id, focus_id, _json(payload)))
            self._remember_time(row, now)
            return json.loads(self.db.execute("SELECT document FROM results WHERE id=?", (record_id,)).fetchone()[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("focus", "status", "admit", "record"):
        command = commands.add_parser(name)
        command.add_argument("--store", required=True)
        command.add_argument("--source-sha256", required=True, help="Caller-supplied executable binding, not an attestation")
        if name != "focus":
            command.add_argument("--focus-id", required=name != "status")
        if name == "focus":
            for flag in ("context", "scene", "goal", "question", "next"):
                command.add_argument("--" + flag, required=True)
            command.add_argument("--fallback", default="", help="Already known applicable control, asserted by caller")
            command.add_argument("--budget-seconds", type=float, default=DEFAULT_SECONDS)
            command.add_argument("--max-probes", type=int, default=DEFAULT_PROBES)
            command.add_argument("--retire-reason")
        if name == "record":
            command.add_argument("--result", choices=("candidate", "observed", "failed"), required=True)
            command.add_argument("--evidence-ref", required=True)
            command.add_argument("--evidence-sha256", required=True)
            command.add_argument("--note", default="")
    args = parser.parse_args(argv)
    try:
        with LearningStore(args.store, args.source_sha256, create=args.command == "focus") as store:
            if args.command == "focus":
                result = store.focus(context=args.context, scene=args.scene, goal=args.goal, question=args.question,
                                     next_interaction=args.next, fallback=args.fallback, budget_seconds=args.budget_seconds,
                                     max_probes=args.max_probes, retire_reason=args.retire_reason)
            elif args.command == "record":
                result = store.record(args.focus_id, args.result, args.evidence_ref, args.evidence_sha256, args.note)
            else:
                result = getattr(store, args.command)(args.focus_id)
        ok = result.get("admitted", True)
        print(_json({"ok": ok, "result": result}))
        return 0 if ok else 1
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(_json({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
