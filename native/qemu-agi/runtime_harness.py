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
CHECKPOINT_SCHEMA = "fdisbull-agi-runtime-checkpoint-1"
SCENE_INPUTS_SCHEMA = "fdisbull-agi-runtime-scene-inputs-1"
EVENTS_SCHEMA = "fdisbull-agi-runtime-events-1"
SCENE_SCHEMA = "fdisbull-agi-runtime-scene-1"
SOUND_SCHEMA = "fdisbull-agi-runtime-sound-events-1"
PRESENTATION_SCHEMA = "fdisbull-agi-runtime-presentation-1"
SOUND_COLUMNS = ["seq", "native_epoch", "sequence", "tick", "kind", "channel", "value", "enabled"]
MAX_SOUND_EVENTS = 262144
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
        self._view_hashes = {item["id"]: item["sha256"] for item in self.package["views"]}
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

    def _validate_checkpoint(self, value, schema=CHECKPOINT_SCHEMA):
        if type(value) is not dict or value.get("schema") != schema \
                or type(value.get("guest")) is not dict:
            raise HarnessError("Unsupported AGI runtime checkpoint schema")
        source = self._source(value)
        guest = value["guest"]
        try:
            if guest.get("status") not in ("ready", "running", "budget", "return", "pending", "fault", "quit"):
                raise ValueError("Invalid checkpoint status")
            _uint(guest.get("logic"), 255, "checkpoint LOGIC")
            if guest["logic"] != source["logic_id"]:
                raise ValueError("Checkpoint LOGIC differs from its source")
            _uint(guest.get("pc"), 65536, "checkpoint PC")
            for name in ("retired", "scene_revision", "presentation_revision", "cycle_count", "clock_ticks", "ticks"):
                _uint(guest.get(name), _UINT64, "checkpoint " + name)
            for name in ("cycle_active", "input_enabled"):
                _uint(guest.get(name), 1, "checkpoint " + name)
            _uint(guest.get("cycle_delay"), 255, "checkpoint cycle delay")
            if guest.get("state_encoding") != "agi-runtime-native-abi-1" \
                    or type(guest.get("state_bytes_sha256")) is not str \
                    or re.fullmatch("[0-9a-f]{64}", guest["state_bytes_sha256"]) is None:
                raise ValueError("Checkpoint lacks its architectural identity")
            _uint(guest.get("state_bytes_size"), MAX_SNAPSHOT_BYTES, "checkpoint state size", 1)
            if "fault" not in guest or "pending_effect" not in guest:
                raise ValueError("Checkpoint omits its stopped fault/request state")
            fault = guest["fault"]
            if fault is not None:
                if type(fault) is not dict or set(fault) != {"code", "name", "detail", "logic", "pc"}:
                    raise ValueError("Invalid checkpoint fault")
                _uint(fault["code"], 2**32 - 1, "checkpoint fault code", 1)
                _text(fault["name"], 64, "checkpoint fault name")
                _uint(fault["detail"], 2**32 - 1, "checkpoint fault detail")
                _uint(fault["logic"], 255, "checkpoint fault LOGIC")
                _uint(fault["pc"], 65536, "checkpoint fault PC")
            pending = guest["pending_effect"]
            if guest["status"] == "pending":
                self._effect(pending, source, guest)
            elif pending is not None:
                raise ValueError("Checkpoint request is present outside pending status")
            observation = value.get("observation")
            if type(observation) is not dict or type(observation.get("per_channel")) is not dict:
                raise ValueError("Checkpoint lacks observation accounting")
            _uint(observation.get("mask"), 3, "checkpoint mask")
            limit = _uint(observation.get("limit"), 65536, "checkpoint event limit")
            capacity = _uint(observation.get("capacity"), limit, "checkpoint event capacity")
            _uint(observation.get("count"), capacity, "checkpoint event count")
            for name in ("eligible", "dropped", "helper_calls", "epoch"):
                _uint(observation.get(name), _UINT64, "checkpoint " + name)
            totals = {"stored": 0, "eligible": 0, "dropped": 0}
            for name in ("disasm", "scene"):
                channel = observation["per_channel"].get(name)
                if type(channel) is not dict:
                    raise ValueError("Checkpoint lacks a channel counter")
                for field in totals:
                    totals[field] += _uint(channel.get(field), _UINT64, "checkpoint channel " + field)
                if channel["eligible"] != channel["stored"] + channel["dropped"]:
                    raise ValueError("Checkpoint channel accounting differs")
            if totals != {"stored": observation["count"], "eligible": observation["eligible"], "dropped": observation["dropped"]}:
                raise ValueError("Checkpoint observation totals differ")
            if type(value.get("run")) is not dict:
                raise ValueError("Checkpoint omits run accounting")
            _uint(value["run"].get("retired"), _UINT64, "checkpoint run retirement")
        except (ValueError, TypeError, KeyError) as error:
            raise HarnessError(str(error)) from error
        return value

    def _owned_checkpoint(self, value, schema=CHECKPOINT_SCHEMA):
        self._validate_checkpoint(value, schema)
        value["owner"] = {"context": self.context_id, "binary_sha256": self.binary_sha256}
        return value

    def checkpoint(self):
        """Read compact stopped state, loss counters and architectural identity.

        No image, sound, inventory, text, full actor bank or replay slots are
        transferred. The owner binding allows events(checkpoint=...) to reject
        cross-child or stale supplied captures. Caller access remains serialized.
        """
        return self._owned_checkpoint(self._json_property("agi-runtime-checkpoint-json"))

    def scene_inputs(self):
        """Read native selected actors and actual order, without composing pixels.

        Order validates current actor state, not resource raster visibility.
        Background construction still requires a complete SCENE journal; this
        query never substitutes picture_id or guest replay slots for history.
        """
        value = self._owned_checkpoint(self._json_property("agi-runtime-scene-inputs-json"), SCENE_INPUTS_SCHEMA)
        scene = value.get("scene")
        try:
            if type(scene) is not dict or set(scene) != {"width", "height", "picture_shown", "background_evidence_required", "order_validation", "draw_order", "actors"} \
                    or scene["width"] != 160 or scene["height"] != 168 \
                    or scene["background_evidence_required"] != "complete_scene_journal" \
                    or scene["order_validation"] != "current_actor_state":
                raise ValueError("Unsupported native scene-input contract")
            _uint(scene["picture_shown"], 1, "picture shown")
            actors, order = scene["actors"], scene["draw_order"]
            if type(actors) is not list or type(order) is not list or len(actors) > 256 or len(order) != len(actors):
                raise ValueError("Invalid native actor/order extent")
            ids = []
            for actor in actors:
                if type(actor) is not dict or set(actor) != {"id", "view", "loop", "cel", "x", "y", "priority", "width", "height", "drawn", "view_sha256"} \
                        or actor["drawn"] is not True:
                    raise ValueError("Invalid selected scene actor")
                for name in ("id", "view", "loop", "cel"):
                    _uint(actor[name], 255, "scene actor " + name)
                _uint(actor["priority"], 15, "scene actor priority")
                _uint(actor["x"], 159, "scene actor x")
                _uint(actor["y"], 167, "scene actor baseline")
                _uint(actor["width"], 160, "scene actor width", 1)
                _uint(actor["height"], 168, "scene actor height", 1)
                if actor["x"] + actor["width"] > 160 or actor["y"] + 1 < actor["height"]:
                    raise ValueError("Native scene actor does not fit the canvas")
                if self._view_hashes.get(actor["view"]) != actor["view_sha256"]:
                    raise ValueError("Native scene VIEW differs from the immutable package")
                ids.append(actor["id"])
            if len(set(ids)) != len(ids) or not _same(ids, order):
                raise ValueError("Native scene actor order differs from selected actors")
        except (ValueError, TypeError, KeyError) as error:
            raise HarnessError(str(error)) from error
        return value

    def events(self, *, checkpoint=None, allow_dropped=False):
        # The native recorder can retain 65536 events, but the inherited QMP
        # transport has a 32 MiB line bound. Refuse an oversized batch before
        # asking QOM to serialize it; never clear retained evidence implicitly.
        if type(allow_dropped) is not bool:
            raise ValueError("allow_dropped must be Boolean")
        before = None
        if checkpoint is None:
            observation = self.state().get("observation")
        else:
            before = self.checkpoint()
            if not _same(checkpoint, before):
                raise HarnessError("Supplied checkpoint is stale, modified or belongs to another owner")
            observation = before["observation"]
            if observation["dropped"] and not allow_dropped:
                raise HarnessError("Native observation journal dropped records; explicit incomplete inspection is required")
        if type(observation) is not dict or type(observation.get("count")) is not int \
                or not 0 <= observation["count"] <= MAX_EVENT_CAPACITY:
            raise HarnessError(f"This QMP client reads at most {MAX_EVENT_CAPACITY} retained events")
        value = self._json_property("agi-events-json")
        if type(value) is not dict or value.get("schema") != EVENTS_SCHEMA \
                or type(value.get("events")) is not list \
                or len(value["events"]) > MAX_EVENT_CAPACITY:
            raise HarnessError("Unsupported AGI runtime events schema")
        self._source(value)
        if before is not None:
            if not _same(value.get("source"), before["source"]) \
                    or value.get("epoch") != before["observation"]["epoch"] \
                    or not _same(value.get("observation"), before["observation"]) \
                    or len(value["events"]) != before["observation"]["count"] \
                    or not _same(before, self.checkpoint()):
                raise HarnessError("Event journal differs from its coherent stopped checkpoint")
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

    def presentation(self):
        """Read native device payloads for the current pending request.

        Scene/VIEW pixels and descriptions originate in native resource code.
        This query does not acknowledge output, change the guest, or consume
        input. A headless capture driver or interactive display can use it.
        """
        ticket = self.pending()
        value = self._json_property("agi-runtime-presentation-json")
        if type(value) is not dict or value.get("schema") != PRESENTATION_SCHEMA:
            raise HarnessError("Unsupported native presentation schema")
        self._source(value)
        request = None if ticket is None else {
            key: val for key, val in ticket["effect"].items() if key != "text"}
        if not _same(value.get("request"), request):
            raise HarnessError("Native presentation belongs to a different pending request")
        payload = value.get("presentation")
        if payload is None:
            return value
        kinds = {29: "priority-plane", 110: "shake-screen", 124: "inventory",
                 129: "show-object", 162: "show-object", 133: "actor-status",
                 139: "joystick-calibration"}
        if ticket is None or type(payload) is not dict \
                or payload.get("kind") != kinds.get(request["opcode"]):
            raise HarnessError("Native presentation kind differs from its instruction")

        def pixels(name, length):
            data = payload.get(name)
            if type(data) is not str or len(data) != 2 * length \
                    or re.fullmatch("[0-9a-f]*", data) is None \
                    or any(color > 15 for color in bytes.fromhex(data)):
                raise HarnessError(f"Invalid native presentation {name} pixels")

        def literal(record, name):
            raw = record.get(name + "_hex")
            if type(raw) is not str or len(raw) % 2 or re.fullmatch("[0-9a-f]*", raw) is None \
                    or bytes.fromhex(raw).decode("cp437") != record.get(name):
                raise HarnessError(f"Native {name} differs from its exact CP437 bytes")

        try:
            kind = payload["kind"]
            if kind in ("priority-plane", "shake-screen"):
                if payload.get("width") != 160 or payload.get("height") != 168:
                    raise ValueError("native presentation dimensions differ")
                pixels("visual", 160 * 168); pixels("priority", 160 * 168)
                if kind == "shake-screen":
                    _uint(payload.get("count"), 255, "shake count")
                    frames = payload.get("frames")
                    if payload.get("frame_count") != 4 * payload["count"] \
                            or type(frames) is not list or len(frames) != payload["frame_count"] \
                            or payload.get("restore_original") is not True:
                        raise ValueError("native shake frame extent differs")
            elif kind == "show-object":
                _uint(payload.get("view"), 255, "preview VIEW")
                _uint(payload.get("width"), 160, "preview width", 1)
                _uint(payload.get("height"), 168, "preview height", 1)
                _uint(payload.get("transparent"), 15, "preview transparency")
                pixels("pixels", payload["width"] * payload["height"])
                literal(payload, "description")
                match = [row for row in self.package["views"] if row["id"] == payload["view"]]
                if len(match) != 1 or match[0]["sha256"] != payload.get("view_sha256"):
                    raise ValueError("preview VIEW identity differs from the immutable package")
            elif kind == "inventory":
                entries = payload.get("entries")
                if type(entries) is not list or len(entries) != len(self.package["objects"]):
                    raise ValueError("inventory extent differs from the package")
                for index, entry in enumerate(entries):
                    if type(entry) is not dict or entry.get("id") != index:
                        raise ValueError("inventory identity differs")
                    _uint(entry.get("room"), 255, "inventory room")
                    literal(entry, "name")
                    if entry["name"] != self.package["objects"][index]["name"]:
                        raise ValueError("inventory name differs from the package")
            elif kind == "actor-status":
                if type(payload.get("actor")) is not dict:
                    raise ValueError("actor status is missing")
                _uint(payload["actor"].get("id"), 255, "actor status ID")
            elif payload.get("requires_host_result") is not True:
                raise ValueError("calibration must require an explicit device result")
        except (ValueError, KeyError, TypeError) as error:
            raise HarnessError(f"Invalid native presentation: {error}") from error
        return value

    @staticmethod
    def _capture_mode(capture):
        if capture is not None and (type(capture) is not str or capture not in ("state", "checkpoint")):
            raise ValueError("capture must be 'state', 'checkpoint' or None")
        return capture

    def _capture_result(self, capture):
        return self.state() if capture == "state" else self.checkpoint() if capture == "checkpoint" else None

    def _command(self, command, *, capture="state"):
        self._capture_mode(capture)
        self.set("agi-runtime-command", json.dumps(command, ensure_ascii=False,
                                                  separators=(",", ":"), allow_nan=False))
        return self._capture_result(capture)

    def run(self, *, step_budget=None, capture="state"):
        """Run through the shared bounded stop machinery, then select readout."""
        self._capture_mode(capture)
        self._run_stopped(step_budget=step_budget)
        return self._capture_result(capture)

    def cycle(self, *, capture="state"):
        """Request the next native cycle; no implicit tick or run is performed."""
        return self._command({"action": "cycle"}, capture=capture)

    def tick(self, ticks=1):
        """Explicit manual world steps; normal cycle pacing uses clock()."""
        return self._command({"action": "tick", "ticks": _uint(ticks, 4096, "ticks", 1)})

    def clock(self, ticks=1, *, capture="state"):
        """Advance the20Hz system timer and60Hz sound without moving actors."""
        return self._command({"action": "clock", "ticks": _uint(ticks, 4096, "clock ticks", 1)}, capture=capture)

    def sound_device(self, device):
        """Choose explicit PC speaker0 or four-channel Tandy1 before execution."""
        return self._command({"action": "sound-device", "device": _uint(device, 1, "sound device")})

    def sound_tick(self, ticks=1):
        """Advance explicit native 1/60-second sound ticks, independently of world ticks."""
        return self._command({"action": "sound-tick",
                              "ticks": _uint(ticks, 4096, "sound ticks", 1)})

    def sound_events(self, *, allow_dropped=False):
        """Capture ordered device output independently of DISASM/SCENE.

        Reading does not consume it. The bounded native journal stops retaining
        new records when full; dropped output is an error by default. Explicit
        allow_dropped=True preserves a diagnostic receipt for acknowledging an
        incomplete capture. Native embeddings can instead use the lossless
        committed-output callback without this QMP journal limit.
        """
        if type(allow_dropped) is not bool:
            raise ValueError("allow_dropped must be Boolean")
        value = self._json_property("agi-runtime-sound-json")
        if type(value) is not dict or value.get("schema") != SOUND_SCHEMA \
                or value.get("available") is not True or value.get("columns") != SOUND_COLUMNS \
                or type(value.get("events")) is not list:
            raise HarnessError("Unsupported native sound journal schema")
        self._source(value)
        try:
            for name in ("epoch", "eligible", "dropped", "last_seq", "native_epoch"):
                _uint(value.get(name), _UINT64, "sound " + name)
            _uint(value.get("capacity"), MAX_SOUND_EVENTS, "sound capacity", 1)
            _uint(value.get("count"), value["capacity"], "sound count")
            if value["count"] != len(value["events"]) \
                    or value["count"] + value["dropped"] != value["eligible"] \
                    or value["last_seq"] < value["eligible"]:
                raise ValueError("sound counters do not reconcile")
            prior = None
            first = value["last_seq"] - value["eligible"] + 1
            for index, row in enumerate(value["events"]):
                if type(row) is not list or len(row) != len(SOUND_COLUMNS):
                    raise ValueError("invalid sound event extent")
                for number in row[:4]:
                    _uint(number, _UINT64, "sound sequence/tick")
                _uint(row[4], 2, "sound kind", 1)
                _uint(row[5], 3, "sound channel")
                _uint(row[6], 12276 if row[4] == 1 else 255, "sound device value")
                _uint(row[7], 1, "sound enabled")
                if row[0] != first + index or row[2] == 0 or row[1] > value["native_epoch"]:
                    raise ValueError("sound event identity differs from journal")
                if prior is not None and (row[1] < prior[1] or
                        (row[1] == prior[1] and (row[2] <= prior[2] or row[3] < prior[3]))):
                    raise ValueError("sound events are not in native commit order")
                prior = row
        except (ValueError, KeyError, TypeError) as error:
            raise HarnessError(f"Invalid native sound journal: {error}") from error
        if value["dropped"] and not allow_dropped:
            raise HarnessError(f"Native sound journal dropped {value['dropped']} events; "
                               "use allow_dropped=True only to inspect incomplete evidence")
        value["context"] = self.context_id
        value["binary_sha256"] = self.binary_sha256
        return value

    def clear_sound_events(self, capture):
        """Acknowledge exactly the captured owner/epoch/output prefix once."""
        if type(capture) is not dict or capture.get("context") != self.context_id \
                or capture.get("binary_sha256") != self.binary_sha256:
            raise HarnessError("Sound capture belongs to another owner or executable")
        current = self.sound_events(allow_dropped=True)
        if not _same(capture, current):
            raise HarnessError("Sound capture is stale or modified")
        return self._command({"action": "sound-clear", "epoch": capture["epoch"],
                              "through": capture["last_seq"]})

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
