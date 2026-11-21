"""Small immutable control vocabularies in an independent DotBox control store.

Every use selects an immutable revision explicitly. There is no implicit latest
revision, executable plugin, automatic discovery, or certified game outcome.
The manifest layout/ID scheme is adapted from fDisBull input_macros.py at
ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9, with no runtime import of fDisBull.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re

from .input_macros import expand_macro, identifier, validate_macro_set
from .keyboard_input import validate_keyboard as _validate_keyboard


MAX_CONTROLS = 32
MAX_STEPS = 16
MAX_QUEUED_MS = 1000
MAX_DEFINITION_BYTES = 48 * 1024
CONTROL_FORMAT = "dotbox-control-set-1"
_DDL = """CREATE TABLE IF NOT EXISTS dotbox_control_sets(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 parent TEXT, created TEXT NOT NULL, author TEXT NOT NULL,
 sha256 TEXT NOT NULL, document TEXT NOT NULL)"""


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Control vocabulary must be bounded JSON data") from error


def _controls(definition):
    return definition["controls" if definition["format"] == CONTROL_FORMAT else "macros"]


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")


class ActionInterrupted(RuntimeError):
    """Some input may have been accepted; preserve progress without replay."""

    def __init__(self, revision, name, completed_steps, active_step, cause, *, coordination=None):
        super().__init__(str(cause)[:500])
        self.progress = {
            "revision": revision, "name": name,
            "completed_steps": completed_steps, "active_step": active_step,
            "outcome": "unknown; input may have been accepted",
            "effects": "not replayed or rolled back; observe before continuing",
        }
        if coordination is not None:
            self.progress["coordination"] = coordination


def _revision(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected an immutable control revision ID")
    return value


class HarnessLibrary:
    def __init__(self, project, *, version=1, validate_keyboard=None):
        if validate_keyboard is None:
            validate_keyboard = _validate_keyboard
        self.project = project
        self.version = version
        self.validate_keyboard = validate_keyboard
        self._expand = expand_macro
        self._validate = validate_macro_set

    def _steps(self, steps):
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise ValueError(f"Controls require 1..{MAX_STEPS} input steps")
        if any(isinstance(step, dict) and step.get("op") == "mouse.click" for step in steps):
            if len(steps) != 1:
                raise ValueError("A mouse control requires exactly one click, without mixed steps")
            params = {key: value for key, value in steps[0].items() if key != "op"}
            if (set(params) - {"x", "y", "width", "height", "button", "hold_ms"}
                    or not {"x", "y", "width", "height"} <= set(params)):
                raise ValueError("Mouse controls require absolute x/y and original frame width/height only")
            for field in ("width", "height"):
                _integer(params[field], field, 1, 4096)
            _integer(params["x"], "x", 0, params["width"] - 1)
            _integer(params["y"], "y", 0, params["height"] - 1)
            params.setdefault("button", "left")
            params.setdefault("hold_ms", 80)
            if params["button"] not in ("left", "right", "middle"):
                raise ValueError("button must be left, right or middle")
            _integer(params["hold_ms"], "hold_ms", 1, MAX_QUEUED_MS)
            return [{"op": "click", "params": params}], params["hold_ms"]
        result, queued = [], 0
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Each control step must be an object")
            op = step.get("op")
            if op == "keyboard.press":
                allowed, required, method = {"op", "key", "modifiers", "hold_ms", "gap_ms"}, "key", "key"
            elif op == "keyboard.type":
                allowed, required, method = {"op", "text", "hold_ms", "gap_ms"}, "text", "type"
            else:
                raise ValueError("Controls support keyboard.press, keyboard.type and mouse.click")
            if set(step) - allowed or required not in step:
                raise ValueError("Unsupported or missing control step fields")
            params = {key: value for key, value in step.items() if key != "op"}
            params.setdefault("hold_ms", 40)
            params.setdefault("gap_ms", 40)
            for field in ("hold_ms", "gap_ms"):
                if type(params[field]) is not int or not 1 <= params[field] <= 1000:
                    raise ValueError(f"{field} must be an integer in 1..1000")
            if not isinstance(params[required], str) or params[required].startswith("$"):
                raise ValueError("Control input must be literal, without symbolic references")
            if method == "key":
                params.setdefault("modifiers", [])
            self.validate_keyboard(**params)
            count = len(params["text"]) if method == "type" else 1
            queued += count * (params["hold_ms"] + params["gap_ms"])
            if queued > MAX_QUEUED_MS:
                raise ValueError(f"Control exceeds {MAX_QUEUED_MS} ms queued-input budget")
            result.append({"op": method, "params": params})
        return result, queued

    def _definition(self, definition):
        encoded = _encode(definition).encode()
        if len(encoded) > MAX_DEFINITION_BYTES:
            raise ValueError("Control vocabulary exceeds 48 KiB")
        if not isinstance(definition, dict):
            raise ValueError("Expected a control vocabulary object")
        if definition.get("format") == CONTROL_FORMAT:
            if set(definition) - {"format", "name", "controls", "provenance"}:
                raise ValueError("Unsupported control vocabulary fields")
            identifier(definition.get("name"))
            controls = definition.get("controls")
            if not isinstance(controls, dict) or not controls:
                raise ValueError("Expected at least one named control")
            for name, control in controls.items():
                identifier(name)
                if not isinstance(control, dict) or set(control) - {"authority", "steps", "context", "evidence"}:
                    raise ValueError("Invalid control declaration")
            doc = deepcopy(definition)
        else:
            doc = self._validate(definition)
        if len(_controls(doc)) > MAX_CONTROLS:
            raise ValueError(f"Control vocabulary exceeds {MAX_CONTROLS} controls")
        for macro in _controls(doc).values():
            if (macro.get("authority", "player-input") != "player-input"
                    or macro.get("parameters") or macro.get("outputs")):
                raise ValueError("Controls require fixed player-input steps without parameters or outputs")
            self._steps(macro.get("steps"))
        return doc

    @staticmethod
    def _summary(info):
        return {
            "revision": info["id"], "name": info["definition"]["name"],
            "parent": info["parent"], "binding": info["binding"],
            "controls": sorted(_controls(info["definition"])),
            "claim": "Authored controls; input delivery is not verified game progress",
            "binding_scope": "original executable bytes; game resources not inventoried",
        }

    def save(self, definition, *, parent=None):
        doc = self._definition(definition)
        if parent is not None:
            previous = self.info(_revision(parent))
            if previous["definition"]["name"] != doc["name"]:
                raise ValueError("Parent must belong to the same control vocabulary")
        # Keep the legacy definition format and immutable manifest ID scheme.
        # Both formats now use the same standalone metadata table.
        with self.project.transaction(True):
            binding = self._binding()
            document = {"definition": doc, "binding": binding, "author": "dotbox", "parent": parent}
            encoded = _encode(document)
            revision = hashlib.sha256(encoded.encode()).hexdigest()
            self.project.db.execute(_DDL)
            self.project.db.execute(
                "INSERT OR IGNORE INTO dotbox_control_sets VALUES (?,?,?,?,?,?,?)",
                (revision, binding["version"], parent, datetime.now(timezone.utc).isoformat(),
                 "dotbox", revision, encoded))
            info = self.info(revision)
        return {**self._summary(info), "id": info["id"]}

    def _binding(self):
        version = self.project.version(self.version)
        return {"version": version["id"], "version_sha256": version["sha256"],
                "source_sha256": self.project.source_binding_sha256(version["id"])}

    def _has_controls(self):
        return self.project.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dotbox_control_sets'").fetchone() is not None

    def _row(self, revision):
        if not self._has_controls():
            return None
        return self.project.db.execute(
            "SELECT * FROM dotbox_control_sets WHERE id=?", (revision,)).fetchone()

    def info(self, revision):
        revision = _revision(revision)
        row = self._row(revision)
        if row is None:
            raise ValueError("Unknown control revision for selected source version")
        else:
            encoded = row["document"]
            if not isinstance(encoded, str) or len(encoded.encode()) > MAX_DEFINITION_BYTES + 2048:
                raise ValueError("Control record exceeds its document budget")
            try:
                document = json.loads(encoded)
            except (ValueError, RecursionError) as error:
                raise ValueError("Invalid persisted control document") from error
            if (hashlib.sha256(_encode(document).encode()).hexdigest() != revision
                    or row["sha256"] != revision):
                raise ValueError("Control manifest hash mismatch")
            if (not isinstance(document, dict)
                    or set(document) != {"definition", "binding", "author", "parent"}
                    or row["parent"] != document["parent"] or row["author"] != document["author"]):
                raise ValueError("Control record metadata mismatch")
            if not isinstance(document["author"], str) or not 1 <= len(document["author"]) <= 256:
                raise ValueError("Invalid control record author")
            if document["parent"] is not None:
                _revision(document["parent"])
            binding = self._binding()
            if row["version"] != binding["version"] or document["binding"] != binding:
                raise ValueError("Control source binding mismatch")
            info = {key: row[key] for key in ("id", "version", "parent", "author", "sha256", "created")}
            info.update(document)
        self._definition(info["definition"])
        return {**info, **self._summary(info)}

    def list(self):
        # Immutable store metadata only; there is no selected/latest head.
        version = self.project.version(self.version)["id"]
        infos = []
        if self._has_controls():
            infos += [self.info(row["id"]) for row in self.project.db.execute(
                "SELECT id FROM dotbox_control_sets WHERE version=? ORDER BY rowid", (version,))]
        infos.sort(key=lambda info: info["created"])
        rows, admitted = [], 0
        for info in reversed(infos):
            try:
                self._definition(info["definition"])
            except ValueError:
                continue  # General debugger macros are outside this small facade.
            admitted += 1
            if len(rows) < 64:
                rows.append(self._summary(info))
        return {"revisions": rows, "truncated": admitted > len(rows)}

    def plan(self, revision, name):
        info = self.info(revision)
        controls = _controls(info["definition"])
        if not isinstance(name, str) or name not in controls:
            raise ValueError("Unknown control in selected revision")
        if info["definition"]["format"] == CONTROL_FORMAT:
            steps, queued = self._steps(controls[name]["steps"])
        else:
            expanded = self._expand(info["definition"], name, allowed_authorities=("player-input",))
            steps, queued = self._steps(expanded["script"]["steps"])
        return {"revision": info["id"], "name": name, "steps": steps,
                "queued_guest_ms": queued}
