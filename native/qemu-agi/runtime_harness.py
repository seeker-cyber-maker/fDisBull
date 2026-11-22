"""Owned QMP transport for the explicit native AGI runtime package profile.

The native engine owns instruction decoding, execution, resource semantics and
snapshot admission. This client validates identities and command boundaries.
It never advances time, starts a later cycle, supplies input, or acknowledges a
pending request implicitly. Run uses the existing bounded transport; this
client caps event batches at 4096 to fit its 32 MiB QMP line limit. The one-byte
kernel is only the base harness's startup placeholder.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4


def _sibling(name):
    """Load this source-tree sibling without requiring a global sys.path edit."""
    path = Path(__file__).resolve().with_name(name + ".py")
    for key in (name, "_fdisbull_agi_" + name):
        module = sys.modules.get(key)
        if module is not None and Path(getattr(module, "__file__", "")).resolve() == path:
            return module
    key = "_fdisbull_agi_" + name
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(key, None)
        raise
    return module


_base = _sibling("harness")
_pack = _sibling("runtime_pack")
HarnessError, QMPError, QemuAGI = _base.HarnessError, _base.QMPError, _base.QemuAGI
PROFILE = _pack.PROFILE
STATE_SCHEMA = "fdisbull-agi-runtime-state-1"
EVENTS_SCHEMA = "fdisbull-agi-runtime-events-1"
SCENE_SCHEMA = "fdisbull-agi-runtime-scene-1"
REQUEST_SCHEMA = "fdisbull-agi-runtime-request-1"
MAX_SNAPSHOT_BYTES = 8 * 1024**2
MAX_EVENT_CAPACITY = 4096
# Native strings contain CP437 bytes. Their lossless Unicode display can use
# three UTF-8 bytes per glyph; exact bytes remain in guest.pending_storage_hex.
MAX_PENDING_DISPLAY_BYTES = 3 * 4095
_UINT64 = 2**64 - 1
_PENDING_FIELDS = {"id", "opcode", "logic", "pc", "next_pc", "reply", "args", "text"}


def _uint(value, maximum, label, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _text(value, maximum, label):
    if type(value) is not str or "\0" in value or len(value) > maximum:
        raise ValueError(f"{label} requires non-NUL text of at most {maximum} UTF-8 bytes")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} must be valid UTF-8") from error
    if size > maximum:
        raise ValueError(f"{label} exceeds {maximum} UTF-8 bytes")
    return value


def _cp437_bytes(value, maximum, label):
    if type(value) is not str or "\0" in value or len(value) > maximum:
        raise ValueError(f"{label} requires non-NUL text of at most {maximum} native CP437 bytes")
    try:
        encoded = value.encode("cp437")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} is not representable as native CP437 text") from error
    if len(encoded) > maximum:
        raise ValueError(f"{label} exceeds {maximum} native CP437 bytes")
    return encoded


def _same(left, right):
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == \
        json.dumps(right, sort_keys=True, separators=(",", ":"), allow_nan=False)


def runtime_guest_state(state):
    """Copy every architectural field, including newly added native fields."""
    if type(state) is not dict or state.get("schema") != STATE_SCHEMA \
            or type(state.get("guest")) is not dict:
        raise HarnessError("Unsupported AGI runtime state schema")
    return deepcopy(state["guest"])


class QemuAGIRuntime(QemuAGI):
    """One native child bound to exact package bytes and explicit host commands.

    package is a validated JSON bytes object, a package dictionary (encoded
    deterministically), or an explicit filesystem path. Existing byte input is
    never re-encoded: even whitespace is part of package_sha256.

    pending() returns a ticket bound to this harness instance, executable,
    package and complete native pending record. complete()/restore() require
    that ticket and compare it with fresh stopped state before sending once.
    A failed/uncertain QMP command is never replayed automatically.
    """

    profile = PROFILE

    def __init__(self, binary, package, *, timeout=10.0, extra_args=(),
                 evidence_dir=None, transport="stdio"):
        if type(package) is dict:
            raw = _pack.dump_package(package)
        elif type(package) is bytes:
            raw = package
        elif isinstance(package, (str, Path)):
            raw = _pack.read_package_bytes(package)
        else:
            raise ValueError("package must be exact JSON bytes, a dictionary or an explicit path")
        self.package = _pack.load_package(raw)
        self.package_bytes = raw
        self.package_sha256 = sha256(raw).hexdigest()
        self.package_size = len(raw)
        self._logic_codes = {item["id"]: bytes.fromhex(item["code"])
                             for item in self.package["logics"]}
        self._logic_hashes = {item["id"]: item["sha256"] for item in self.package["logics"]}
        self._logic_sizes = {item["id"]: len(item["code"]) // 2 for item in self.package["logics"]}
        self.context_id = uuid4().hex
        self.initial_context = []
        if not isinstance(extra_args, (list, tuple)) \
                or any(type(arg) is not str for arg in extra_args):
            raise ValueError("extra_args must be a sequence of command arguments")
        self._package_temporary = tempfile.TemporaryDirectory(prefix="fdb-agi-runtime-")
        self.package_path = Path(self._package_temporary.name) / "package.json"
        try:
            self.package_path.write_bytes(raw)
            super().__init__(
                binary, b"\0", timeout=timeout,
                extra_args=("-M", f"agi-test,runtime-package={self.package_path}", *extra_args),
                evidence_dir=evidence_dir, transport=transport,
            )
            self.source_sha256 = self.package_sha256
            self.state()
        except BaseException:
            if getattr(self, "_temporary", None) is not None:
                self.close(failed=True)
            elif self._package_temporary is not None:
                self._package_temporary.cleanup()
                self._package_temporary = None
            raise

    def _source(self, value):
        source = value.get("source") if type(value) is dict else None
        if type(source) is not dict or source.get("sha256") != self.package_sha256 \
                or source.get("profile") != PROFILE \
                or type(source.get("logic_id")) is not int \
                or source["logic_id"] not in self._logic_hashes \
                or source.get("logic_sha256") != self._logic_hashes[source["logic_id"]]:
            raise HarnessError("AGI runtime package, profile or current logic identity differs")
        return source

    def _effect(self, value, source, guest):
        if type(value) is not dict or set(value) != _PENDING_FIELDS:
            raise HarnessError("Invalid native pending effect fields")
        try:
            _uint(value["id"], _UINT64, "pending id", 1)
            _uint(value["opcode"], 173, "pending opcode")
            _uint(value["logic"], 255, "pending logic")
            _uint(value["pc"], 65535, "pending pc")
            _uint(value["next_pc"], 65536, "pending next_pc")
            _text(value["text"], MAX_PENDING_DISPLAY_BYTES, "pending display text")
            if value["reply"] not in ("ack", "text", "number", "choice", "menu", "restore") \
                    or type(value["args"]) is not list or len(value["args"]) > 7:
                raise ValueError("Invalid native pending reply or argument list")
            for item in value["args"]:
                _uint(item, 255, "pending argument")
        except (ValueError, TypeError) as error:
            raise HarnessError(str(error)) from error
        if value["logic"] != source["logic_id"] or value["pc"] != guest["pc"] \
                or not value["pc"] < value["next_pc"] <= self._logic_sizes[value["logic"]]:
            raise HarnessError("Native pending effect is outside the current logic")
        return value

    def state(self):
        value = self._json_property("agi-state-json")
        if type(value) is not dict or value.get("schema") != STATE_SCHEMA \
                or type(value.get("guest")) is not dict:
            raise HarnessError("Unsupported AGI runtime state schema")
        source = self._source(value)
        guest = value["guest"]
        if guest.get("status") not in ("ready", "running", "budget", "return",
                                       "pending", "fault", "quit") \
                or type(guest.get("retired")) is not int \
                or not 0 <= guest["retired"] <= _UINT64 \
                or type(guest.get("pc")) is not int or not 0 <= guest["pc"] <= 65536 \
                or "pending_effect" not in guest:
            raise HarnessError("Invalid native runtime status, PC or retirement counter")
        pending = guest["pending_effect"]
        if guest["status"] == "pending":
            self._effect(pending, source, guest)
        elif pending is not None:
            raise HarnessError("Native effect is present outside pending status")
        return value

    def events(self):
        # The native recorder can retain 65536 events, but the inherited QMP
        # transport has a 32 MiB line bound. Refuse an oversized batch before
        # asking QOM to serialize it; never clear retained evidence implicitly.
        observation = self.state().get("observation")
        if type(observation) is not dict or type(observation.get("count")) is not int \
                or not 0 <= observation["count"] <= MAX_EVENT_CAPACITY:
            raise HarnessError(f"This QMP client reads at most {MAX_EVENT_CAPACITY} retained events")
        value = self._json_property("agi-events-json")
        if type(value) is not dict or value.get("schema") != EVENTS_SCHEMA \
                or type(value.get("events")) is not list \
                or len(value["events"]) > MAX_EVENT_CAPACITY:
            raise HarnessError("Unsupported AGI runtime events schema")
        self._source(value)
        return value

    def configure(self, *, mask=None, capacity=None, step_budget=None):
        """Configure native observation within this client's 32 MiB transport."""
        if capacity is not None:
            _uint(capacity, MAX_EVENT_CAPACITY, "QMP event capacity")
        if mask is not None:
            _uint(mask, 3, "observation mask")
        return super().configure(mask=mask, capacity=capacity, step_budget=step_budget)

    def scene(self):
        value = self._json_property("agi-runtime-scene-json")
        if type(value) is not dict or value.get("schema") != SCENE_SCHEMA \
                or type(value.get("width")) is not int or value["width"] != 160 \
                or type(value.get("height")) is not int or value["height"] != 168:
            raise HarnessError("Unsupported AGI runtime scene schema or dimensions")
        self._source(value)
        for name in ("visual", "priority"):
            plane = value.get(name)
            if type(plane) is not str or len(plane) != 160 * 168 * 2 \
                    or re.fullmatch("[0-9a-f]+", plane) is None \
                    or any(color > 15 for color in bytes.fromhex(plane)):
                raise HarnessError(f"Invalid native runtime {name} plane")
        return value

    def _command(self, command):
        self.set("agi-runtime-command", json.dumps(command, ensure_ascii=False,
                                                  separators=(",", ":"), allow_nan=False))
        return self.state()

    def cycle(self):
        """Request the next native cycle; no implicit tick or run is performed."""
        return self._command({"action": "cycle"})

    def tick(self, ticks=1):
        return self._command({"action": "tick", "ticks": _uint(ticks, 4096, "ticks", 1)})

    def sound_tick(self, ticks=1):
        """Advance explicit native 1/60-second sound ticks, independently of world ticks."""
        return self._command({"action": "sound-tick",
                              "ticks": _uint(ticks, 4096, "sound ticks", 1)})

    def input(self, text):
        _cp437_bytes(text, 40, "input")
        return self._command({"action": "input", "text": text})

    def key(self, key, pressed):
        _uint(key, 65535, "key")
        if type(pressed) is not bool:
            raise ValueError("pressed must be Boolean")
        return self._command({"action": "key", "key": key, "pressed": pressed})

    def controller(self, controller):
        return self._command({"action": "controller",
                              "controller": _uint(controller, 255, "controller")})

    @staticmethod
    def _seed_values(values, maximum, label):
        if values is None:
            return {}
        if type(values) is not dict or len(values) > 256:
            raise ValueError(f"{label} must be an explicit mapping of at most 256 slots")
        result = {}
        for key, value in values.items():
            if type(key) is str and re.fullmatch("0|[1-9][0-9]*", key):
                key = int(key)
            _uint(key, 255, label + " index")
            _uint(value, maximum, label + " value")
            key = str(key)
            if key in result:
                raise ValueError(f"duplicate {label} slot")
            result[key] = value
        return result

    def seed(self, *, variables=None, flags=None):
        """Apply explicit initial context only before retirement and without a request."""
        variables = self._seed_values(variables, 255, "variables")
        flags = self._seed_values(flags, 1, "flags")
        before = self.state()
        if before["guest"]["retired"] != 0 or before["guest"]["pending_effect"] is not None:
            raise HarnessError("seed requires zero retired instructions and no pending effect")
        command = {"action": "seed", "variables": variables, "flags": flags}
        result = self._command(command)
        self.initial_context.append(deepcopy(command))
        return result

    def pending(self):
        """Return an owner/package/binary-bound ticket, or None when no request waits."""
        effect = self.state()["guest"]["pending_effect"]
        if effect is None:
            return None
        return {"schema": REQUEST_SCHEMA, "context": self.context_id,
                "package_sha256": self.package_sha256, "binary_sha256": self.binary_sha256,
                "effect": deepcopy(effect)}

    def logic_code(self, logic_id):
        """Return immutable exact code bytes captured from the admitted package."""
        _uint(logic_id, 255, "logic_id")
        if logic_id not in self._logic_codes:
            raise ValueError("logic_id is absent from the runtime package")
        return self._logic_codes[logic_id]

    def logic_source(self, logic_id):
        """Describe a decode source, distinct from the current execution source."""
        code = self.logic_code(logic_id)
        return {"sha256": self._logic_hashes[logic_id], "size": len(code),
                "logic_id": logic_id, "profile": PROFILE,
                "package_sha256": self.package_sha256}

    def decode(self, logic_id, pc=0, limit=64):
        """Read one canonical native page and verify state/event neutrality.

        Only native decode supplies instruction lengths, operands and control
        flow. The existing processor adapter validates them against the exact
        selected package bytes, including unexecuted/unloaded LOGIC resources.
        """
        code = self.logic_code(logic_id)
        _uint(pc, len(code), "decode pc")
        _uint(limit, 64, "decode limit", 1)
        processor = _sibling("processor_harness")
        return processor.read_decode_pages(
            self, code, source=self.logic_source(logic_id), start_pc=pc,
            max_instructions=limit, page_limit=limit,
        )[0]

    def _require_ticket(self, ticket):
        if type(ticket) is not dict:
            raise HarnessError("An exact pending request ticket is required")
        current = self.pending()
        try:
            matches = current is not None and _same(ticket, current)
        except (ValueError, TypeError, RecursionError):
            matches = False
        if not matches:
            raise HarnessError("Pending request is stale, modified or belongs to another owner")
        return current["effect"]

    def complete(self, ticket, *, accepted, text=None, number=None):
        """Complete exactly one current request; cancellation is explicit accepted=False."""
        effect = self._require_ticket(ticket)
        if type(accepted) is not bool:
            raise ValueError("accepted must be an explicit Boolean")
        command = {"action": "complete", "id": effect["id"], "accepted": accepted}
        if not accepted:
            if text is not None or number is not None:
                raise ValueError("A cancelled request cannot carry an ignored reply")
        elif effect["reply"] == "restore":
            raise ValueError("An accepted restore requires restore(ticket, snapshot)")
        elif effect["reply"] == "text":
            encoded = _cp437_bytes(text, 40, "completion text")
            if len(effect["args"]) < 5 or len(encoded) > effect["args"][4]:
                raise ValueError("completion text exceeds the native request's maximum length")
            if number is not None:
                raise ValueError("Text completion cannot carry a number")
            command["text"] = text
        elif effect["reply"] in ("number", "menu"):
            _uint(number, 255, "completion number")
            if text is not None:
                raise ValueError("Numeric completion cannot carry text")
            command["number"] = number
        elif text is not None or number is not None:
            raise ValueError("Acknowledgement/choice completion cannot carry ignored values")
        result = self._command(command)
        pending = result["guest"]["pending_effect"]
        if pending is not None:
            raise HarnessError("Native completion did not consume the exact request")
        return result

    def snapshot(self):
        """Read opaque same-ABI snapshot bytes; this is not a portable game-save format."""
        raw = self.get("agi-runtime-snapshot-hex")
        if type(raw) is not str or not 2 <= len(raw) <= 2 * MAX_SNAPSHOT_BYTES \
                or len(raw) % 2 or re.fullmatch("[0-9a-f]+", raw) is None:
            raise HarnessError("Invalid bounded native runtime snapshot")
        return bytes.fromhex(raw)

    def restore(self, ticket, snapshot):
        effect = self._require_ticket(ticket)
        if effect["reply"] != "restore":
            raise ValueError("restore requires the current native restore request")
        if type(snapshot) is not bytes or not 1 <= len(snapshot) <= MAX_SNAPSHOT_BYTES:
            raise ValueError("restore requires bounded exact native snapshot bytes")
        result = self._command({"action": "restore", "id": effect["id"],
                                "snapshot": snapshot.hex()})
        if result["guest"]["pending_effect"] is not None:
            raise HarnessError("Native restore did not consume the exact request")
        return result

    def close(self, *, failed=False):
        try:
            super().close(failed=failed)
            if failed and self.failure_evidence is not None:
                # Retain identities, never copy a full private game into diagnostics.
                (self.failure_evidence / "runtime-package.json").write_text(
                    json.dumps({"sha256": self.package_sha256, "size": self.package_size,
                                "profile": PROFILE}, indent=2) + "\n", encoding="utf-8")
        finally:
            if self._package_temporary is not None:
                self._package_temporary.cleanup()
                self._package_temporary = None
