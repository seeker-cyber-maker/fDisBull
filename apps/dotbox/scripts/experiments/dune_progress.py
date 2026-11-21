"""Bounded ordinary-click continuation for the private Dune experiment.

The caller supplies an already-owned, session-bound native ``call`` adapter and
the pure ``dune_ui_reader.describe`` function. This module does not launch a
guest, take ownership, restore state, select a story action, or call a model.
Keep one controller in the same native process. Cold text-mode checkpoint loads
have not qualified rendered continuation; the separately observed graphics-primed
restore workaround does not make arbitrary cross-process loads equivalent.

``observe()`` returns a descriptive stopped observation. ``await_ready()`` waits
without input for an observed input-loop boundary and returns an actionable
token. ``perform(token, ...)`` rechecks that observation, queues one original left click, witnesses the selected
control at D326, and waits for D214 input-loop evidence, released input, completed
frames and a stable control structure. These are separate observations, not a
claim that every animation, deferred effect or story operation has completed.

Budgets limit admitted frames/stops and host admission between synchronous RPCs.
An individual RPC may outlast the host budget. On any RPC exception the outcome
is uncertain and NO further native call is made, including cleanup. Unexpected
stops are preserved. Only this controller's surviving probes are removed when
the target is known stopped. A partial attempt is never automatically replayed.

Screenshots, RAM, reports and original game files belong outside the repository.
This is an edition-bound experiment, not DotBox's player-facing ownership API.
"""
from __future__ import annotations

import base64
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import uuid


SOURCE_SHA256 = "32439602abe95e0ff778653ad58052bfed56a73e103b92f079455daa2ee886e7"
SOURCE_SIZE = 74757
CS, DS, HEADER, RAM_BYTES = 0x0824, 0x16F3, 0x200, 0xA0000
DISPATCH, INPUT_LOOP = 0xD326, 0xD214
ROW_CALLBACKS = (0xCE85, 0xCE80, 0xCE7B, 0xCE76, 0xCE71)
TALK_LABEL = '" TALK TO ME "'
_MODULE_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ProgressError(RuntimeError):
    pass


class UnexpectedStop(ProgressError):
    def __init__(self, message, evidence=None):
        super().__init__(message)
        self.evidence = evidence


class BudgetExpired(ProgressError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _write(path, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as out:
        out.write(data)


def _address(value):
    if not isinstance(value, dict) or value.get("space") != "segmented":
        raise ValueError("Expected a segmented execution address")
    return int(value["segment"], 16), int(value["offset"], 16)


def _context(registers, *, require_mapping=True):
    if (registers.get("cpu_mode") != "real" or registers.get("code_bits") != 16
            or registers.get("stack_bits") != 16
            or registers.get("address_context", {}).get("paging_enabled") is not False
            or (require_mapping and (int(registers.get("segments", {}).get("cs", "0"), 16) != CS
                                     or int(registers.get("segments", {}).get("ds", "0"), 16) != DS))):
        raise ProgressError("The qualified real-mode Dune code/data mapping changed")


def _neutral(keyboard, mouse):
    return (all(keyboard[name] == 0 for name in ("pending_events", "owned_keys", "queued_guest_ms"))
            and not keyboard["frame_keys"]
            and all(mouse[name] == 0 for name in ("buttons", "owned_buttons", "pending_release_buttons"))
            and not mouse["release_pending"])


def _structure(data):
    """Small raw stability witness; neither complete game state nor readiness."""
    if len(data) != 65536:
        raise ProgressError("The control witness needs one complete data segment")

    def word(offset):
        if not 0 <= offset <= 65534:
            raise ProgressError("A menu/control pointer leaves the data segment")
        return struct.unpack_from("<H", data, offset)[0]

    count, rows = word(0x2184), data[0xFED8]
    if not 1 <= count <= 64 or rows > 5:
        raise ProgressError("Control/row count leaves the bounded edition schema")
    controls = []
    for index in range(count):
        offset = 0x2186 + index * 14
        values = struct.unpack_from("<4H2B2H", data, offset)
        controls.append([offset, *values[:4], bool(values[4] & 0x80), values[7]])
    slot = word(0x2840)
    menu = word(slot)
    if menu > 65534:
        raise ProgressError("Menu header leaves the data segment")
    skip = struct.unpack_from("<b", data, menu + 1)[0]
    entries = [[word(menu + 2 + skip + 4 * row), word(menu + 4 + skip + 4 * row)]
               for row in range(rows)]
    return {"controls": controls, "slot": slot, "menu": menu, "skip": skip,
            "entries": entries, "rows": rows, "special": list(data[0xFED4:0xFED6]),
            "location": [word(4), word(6)], "ui_mode": data[0x4247],
            "subject": word(0x431B),
            "dialogue": [word(0x4311), word(0x4315), data[0x4319]] if menu == 0x2608 else None}


class ProgressController:
    """One process-local controller over the caller's existing owned adapter.

    ``call(method, params, timeout_ms=...)`` must preserve the caller's ownership
    and generation fences where applicable. ``session_id`` alone is not a lease.
    ``reader`` takes conventional RAM at linear address zero and returns a dict.
    Initial input applicability and renderer health remain caller qualification
    requirements; current active rectangles are necessary evidence, not a proof
    that all game contexts are covered by this experimental continuation.
    """

    def __init__(self, call, reader, evidence_root, *, session_id, source_path,
                 wait_strategy="frame", read_strategy="full", capabilities=None,
                 sparse_reader=None, structure_reader=None):
        if wait_strategy not in ("frame", "native") or read_strategy not in ("full", "sparse"):
            raise ValueError("Select explicit frame/native waiting and full/sparse reading")
        self.wait_strategy, self.read_strategy = wait_strategy, read_strategy
        self.sparse_reader, self.structure_reader = sparse_reader, structure_reader
        if read_strategy == "sparse" and (not callable(sparse_reader) or not callable(structure_reader)):
            raise ValueError("Sparse mode requires explicit scene and structure readers")
        self.native_limits = None
        if wait_strategy == "native":
            limits = (capabilities or {}).get("execution", {}).get("bounded_frame_step", {})
            if (limits.get("schema") != "dotbox-bounded-frame-step-1"
                    or type(limits.get("max_frames")) is not int or not 1 <= limits["max_frames"] <= 10000
                    or type(limits.get("max_guest_ms")) is not int or not 1 <= limits["max_guest_ms"] <= 30000):
                raise ProgressError("Native bounded frame-step capability is absent or incompatible; no fallback is implicit")
            self.native_limits = deepcopy(limits)
        self.call_adapter, self.reader = call, reader
        self.implementation_sha256 = _MODULE_SOURCE_SHA256
        self.source_path = Path(source_path).resolve(strict=True)
        self.source = self.source_path.read_bytes()
        if len(self.source) != SOURCE_SIZE or _sha(self.source) != SOURCE_SHA256:
            raise ProgressError("Executable does not match the qualified Dune edition")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("An already-owned native session id is required")
        self.session_id = session_id
        root = Path(evidence_root).expanduser().resolve()
        if (root.is_relative_to(Path(__file__).resolve().parents[2])
                or root.is_relative_to(self.source_path.parent)):
            raise ValueError("Evidence must be outside the repository and game mount")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.epoch = uuid.uuid4().hex
        self.root = root / ("controller-" + self.epoch)
        self.root.mkdir(mode=0o700)
        self.latest = None
        self.ready_token = None
        self.uncertain = False
        self.blocked = False
        self.continuation_refused = False
        self.last_owned_stop = None
        self.stopped = False
        self.deadline = None
        self.owned = {}
        self.counts = Counter()
        self.memory_bytes = 0
        self.sequence = 0

    def _rpc(self, method, params=None, *, timeout_ms=15000):
        if self.uncertain:
            raise ProgressError("Native calls are forbidden after uncertain dispatch")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise BudgetExpired("Cooperative host admission budget expired")
        self.counts[method] += 1
        try:
            result = self.call_adapter(method, {"session_id": self.session_id, **(params or {})}, timeout_ms=timeout_ms)
        except BaseException:
            self.uncertain = True
            raise
        if not isinstance(result, dict) or result.get("session_id") != self.session_id:
            self.uncertain = True
            raise ProgressError("Native response changed or omitted owned session identity")
        return result

    def _status(self, reply=None):
        status = self._rpc("session.status")
        self.stopped = status.get("state") == "stopped"
        if not self.stopped:
            raise UnexpectedStop("Guest is not confirmed stopped", {"reply": reply, "status": status})
        if reply is not None and (reply.get("state_revision") != status.get("state_revision")
                or ("stop_reason" in reply and reply["stop_reason"] != status.get("last_stop"))):
            raise UnexpectedStop("Fresh status differs from the observed stop", {"reply": reply, "status": status})
        return status

    def _memory(self, address, length):
        blocks = []
        for start in range(0, length, 65536):
            size = min(65536, length - start)
            result = self._rpc("memory.read", {"address": {"space": "linear", "offset": f"0x{address + start:08X}"}, "length": size})
            block = base64.b64decode(result["data_base64"], validate=True)
            if len(block) != size:
                raise ProgressError("Native memory length differs from the requested bounded window")
            blocks.append(block)
            self.memory_bytes += size
        return b"".join(blocks)

    def _inputs(self):
        keyboard = self._rpc("input.keyboard.state")["keyboard"]
        mouse = self._rpc("input.mouse.state")["mouse"]
        return {"keyboard": keyboard, "mouse": mouse, "neutral": _neutral(keyboard, mouse)}

    def _code(self, offset, length=5):
        if not 0 < offset <= 0x10000 - length or HEADER + offset + length > len(self.source):
            raise ProgressError("Control/hook is outside the qualified near-code mapping")
        live = self._memory(CS * 16 + offset, length)
        if live != self.source[HEADER + offset:HEADER + offset + length]:
            raise ProgressError("Live hook bytes no longer match the qualified executable")
        return _sha(live)

    def _scene_capture(self, folder, name):
        if self.read_strategy == "full":
            ram = self._memory(0, RAM_BYTES)
            scene = self.reader(ram, ds=DS)
            ds = ram[DS * 16:DS * 16 + 65536]
            _write(folder / (name + ".bin"), ram)
            identity = {"memory_mode": "full", "ram_sha256": _sha(ram),
                        "ram_path": str(folder / (name + ".bin")), "ds_sha256": _sha(ds),
                        "structure_sha256": _digest(_structure(ds))}
        else:
            result = self.sparse_reader(self._memory, ds=DS)
            scene, capture = result["observation"], result["capture"]
            if (capture.get("schema") != "dune-sparse-memory-1"
                    or not capture.get("ranges") or not capture.get("dependencies")
                    or any(not isinstance(capture.get(key), str) or len(capture[key]) != 64
                           for key in ("sha256", "dependency_sha256"))):
                raise ProgressError("Sparse reader omitted its exact dependency/capture identity")
            path = folder / (name + ".sparse.json")
            _write(path, capture)
            identity = {"memory_mode": "sparse", "memory_capture": {
                "schema": capture["schema"], "path": str(path), "sha256": capture["sha256"],
                "dependency_sha256": capture["dependency_sha256"],
                "dependencies": capture["dependencies"], "reads": result["reads"]},
                "structure_sha256": _digest(result["structure_witness"])}
        if not isinstance(scene, dict) or not isinstance(scene.get("menu_admission_sha256"), str):
            raise ProgressError("Reader did not supply the qualified UI-witness contract")
        return scene, identity

    def _structure_digest(self):
        if self.read_strategy == "full":
            return _digest(_structure(self._memory(DS * 16, 65536)))
        result = self.structure_reader(self._memory, ds=DS)
        return _digest(result["structure_witness"])

    def _snapshot(self, folder, name, *, readiness=None):
        before = self._status()
        registers = self._rpc("state.get_registers")
        _context(registers)
        inputs = self._inputs()
        if readiness is not None and (not inputs["neutral"] or int(registers["instruction_pointer"], 16) != INPUT_LOOP):
            raise ProgressError("The qualified input-loop observation no longer matches current input/PC")
        timing = self._rpc("execution.timing")
        scene, memory_identity = self._scene_capture(folder, name)
        frame = self._rpc("video.screenshot")
        png = base64.b64decode(frame.get("data_base64") or frame["png_base64"], validate=True)
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ProgressError("Native screenshot is not a PNG")
        after = self._status()
        if (before.get("state_revision") != after.get("state_revision")
                or before.get("last_stop") != after.get("last_stop")):
            raise UnexpectedStop("Observation changed while capturing stopped evidence", {"before": before, "after": after})
        packet = {"schema": "dune-progress-observation-1", "process_epoch": self.epoch,
                  "session_id": self.session_id, "state_revision": after["state_revision"],
                  "source_sha256": SOURCE_SHA256, "stop": after.get("last_stop"),
                  "registers": registers, "timing": timing, "input": inputs, "scene": scene,
                  **memory_identity,
                  "frame": {**{k: v for k, v in frame.items() if not k.endswith("base64")},
                            "path": str(folder / (name + ".png")), "sha256": _sha(png)},
                  "input_boundary": readiness,
                  "presentation_semantics": "Captured image; agreement with state/text is a separate qualification"}
        packet["scene_token"] = _digest({"epoch": self.epoch, "revision": packet["state_revision"],
                                         "memory": packet.get("ram_sha256") or packet["memory_capture"]["sha256"],
                                         "menu": scene["menu_admission_sha256"],
                                         "input_boundary": readiness})
        _write(folder / (name + ".png"), png)
        _write(folder / (name + ".json"), packet)
        return packet

    def observe(self):
        """Read and retain a stopped packet; does not run the guest or clear a partial attempt."""
        self.sequence += 1
        folder = self.root / f"observation-{self.sequence:04d}"
        folder.mkdir(mode=0o700)
        packet = self._snapshot(folder, "observation")
        self.latest = deepcopy(packet)
        self.ready_token = None
        return packet

    @staticmethod
    def _binding(scene, selected):
        """Resolve route meaning, including fields not retained in the reader hash."""
        control, row, menu = selected["control"], selected["row"], scene["menu"]
        binding = {"admission": scene["menu_admission_sha256"],
                   "menu": {key: menu.get(key) for key in ("stack_slot", "menu_offset", "page_skip", "paging_mode", "special_row", "visible_rows")},
                   "control": {key: control.get(key) for key in ("record_offset", "bounds", "active", "value", "callback")}}
        if row is not None:
            binding["row"] = {key: row.get(key) for key in ("row", "record_offset", "source", "entry_offset", "handler",
                                                           "disabled_by_metadata", "active_rectangle", "bounds", "callback", "label")}
            binding["row"]["metadata_without_highlight"] = row.get("metadata", 0) & 0x7FFF
        return binding

    def _selection(self, scene, control_record, label):
        if (control_record is None) == (label is None):
            raise ProgressError("Select exactly one control_record or exact current label")
        rows = scene["menu"]["rows"]
        if label is not None:
            matched = [row for row in rows if row["label"].get("ascii_only") is True and row["label"]["ascii"] == label]
            if len(matched) != 1:
                raise ProgressError("Label is absent, non-ASCII or ambiguous in the current menu")
            control_record = matched[0].get("record_offset", 0x21E8 + 14 * matched[0]["row"])
        selected = [c for c in scene["controls"] if c["record_offset"] == control_record]
        if len(selected) != 1 or selected[0].get("active") is not True:
            raise ProgressError("Selected control is absent or inactive")
        control = selected[0]
        row = next((r for r in rows if r.get("record_offset", 0x21E8 + 14 * r["row"]) == control_record), None)
        if control["callback"] in ROW_CALLBACKS:
            if (row is None or row.get("disabled_by_metadata") is not False
                    or row.get("active_rectangle") is not True or not row.get("handler")
                    or ROW_CALLBACKS[row["row"]] != control["callback"]):
                raise ProgressError("The current row has no enabled matching dispatch binding")
        x0, y0, x1, y1 = control["bounds"]
        frame = self.latest["frame"]
        if not (0 <= x0 < x1 <= frame["width"] and 0 <= y0 < y1 <= frame["height"]
                and x1 - x0 >= 2 and y1 - y0 >= 2):
            raise ProgressError("Control does not have a qualified interior screen point")
        x, y = (x0 + x1) // 2, (y0 + y1) // 2
        # Conservatively reject overlaps instead of inventing hit-test priority.
        overlaps = [c for c in scene["controls"] if c.get("active") is True
                    and c["bounds"][0] < x < c["bounds"][2]
                    and c["bounds"][1] < y <= c["bounds"][3]]
        if len(overlaps) != 1 or overlaps[0]["record_offset"] != control_record:
            raise ProgressError("Control center overlaps other active rectangles")
        return {"control": control, "row": row, "x": x, "y": y}

    def _arm(self, offset):
        reply = self._rpc("breakpoints.create", {"kind": "execution", "once": True,
                          "address": {"space": "segmented", "segment": f"0x{CS:04X}", "offset": f"0x{offset:08X}"}})
        identifier = reply.get("breakpoint_id")
        if not isinstance(identifier, str) or not identifier:
            self.uncertain = True
            raise ProgressError("Probe creation omitted its owned identity")
        self.owned[identifier] = {"offset": offset, "active": True}
        if reply.get("kind") != "execution" or reply.get("once") is not True or _address(reply.get("address")) != (CS, offset):
            raise ProgressError("Probe receipt differs from the requested definition")

    def _step(self, *, max_frames=1, max_guest_ms=None):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise BudgetExpired("Cooperative host admission budget expired")
        self.stopped = False
        params = ({"max_frames": max_frames, "max_guest_ms": max_guest_ms}
                  if self.wait_strategy == "native" else None)
        reply = self._rpc("frame.step", params)
        status = self._status(reply)
        reason = reply.get("stop_reason", {})
        if self.wait_strategy == "native":
            budget = reply.get("bounded", {})
            names = ("max_frames", "max_guest_ms", "frames_completed", "guest_tick_bits",
                     "guest_ticks_before", "guest_ticks_after", "guest_elapsed_ms")
            valid = (all(type(budget.get(key)) is int for key in names)
                     and budget.get("max_frames") == max_frames and budget.get("max_guest_ms") == max_guest_ms
                     and 0 <= budget.get("frames_completed", -1) <= max_frames
                     and budget.get("guest_tick_bits") in (32, 64))
            if valid:
                modulus = 1 << budget["guest_tick_bits"]
                valid = (0 <= budget["guest_ticks_before"] < modulus and 0 <= budget["guest_ticks_after"] < modulus
                         and budget["guest_elapsed_ms"] == (budget["guest_ticks_after"] - budget["guest_ticks_before"]) % modulus
                         and 0 <= budget["guest_elapsed_ms"] <= max_guest_ms
                         and reply.get("guest_ticks") == budget["guest_ticks_after"]
                         and (budget["frames_completed"] == 0 or reply.get("frame_available") is True))
            cause = budget.get("stop_cause")
            if cause == "frame_limit":
                valid = valid and reason.get("kind") == "frame" and reply.get("completed") is True and budget.get("frames_completed") == max_frames
            elif cause == "guest_time_limit":
                valid = valid and reason.get("kind") == "budget" and reply.get("completed") is False and budget.get("guest_elapsed_ms") == max_guest_ms
            elif cause == "breakpoint":
                valid = valid and reason.get("kind") == "breakpoint" and reply.get("completed") is False
            else:
                valid = False
            if not valid:
                raise UnexpectedStop("Native bounded step returned inconsistent counters/cause", {"reply": reply, "status": status})
            if cause in ("frame_limit", "guest_time_limit"):
                # A budget is resumable only for the controller that validated
                # this exact stopped response. It is not a generic pause.
                self.last_owned_stop = {"state_revision": reply["state_revision"], "reason": deepcopy(reason)}
                return reply, None
        elif reply.get("completed") is True and reason.get("kind") == "frame":
            return reply, None
        probe = self.owned.get(reason.get("breakpoint_id"))
        registers = reply.get("registers", {})
        try:
            address = _address(reason.get("address"))
            pc = (int(registers["segments"]["cs"], 16), int(registers["instruction_pointer"], 16))
        except (KeyError, TypeError, ValueError):
            address, pc = None, None
        if (reply.get("completed") is not False or reason.get("kind") != "breakpoint"
                or probe is None or not probe["active"] or address != (CS, probe["offset"]) or pc != address):
            raise UnexpectedStop("Stop is not an active owned one-shot or completed frame", {"reply": reply, "status": status})
        _context(registers)
        probe["active"] = False
        self.last_owned_stop = {"state_revision": reply["state_revision"], "reason": reason}
        return reply, probe["offset"]

    def _cleanup(self):
        if self.uncertain or not self.stopped:
            return {"status": "preserved_without_native_calls", "owned_ids": list(self.owned)}
        saved_deadline, self.deadline = self.deadline, None
        try:
            removed = []
            for entry in self._rpc("breakpoints.list")["breakpoints"]:
                identifier = entry["breakpoint_id"]
                if identifier in self.owned:
                    before = self._status()
                    retained_stop = self.last_owned_stop == {
                        "state_revision": before["state_revision"], "reason": before.get("last_stop")}
                    reply = self._rpc("breakpoints.delete", {"breakpoint_id": identifier})
                    if reply.get("deleted") is not True or reply.get("breakpoint_id") != identifier:
                        raise ProgressError("Owned probe cleanup was not acknowledged")
                    after = self._status(reply)
                    expected_revisions = ((before["state_revision"] + 1,) if self.wait_strategy == "native"
                                          else (before["state_revision"], before["state_revision"] + 1))
                    if (after.get("last_stop") != before.get("last_stop")
                            or after["state_revision"] not in expected_revisions):
                        raise UnexpectedStop("Probe cleanup changed more than its acknowledged observer revision",
                                             {"before": before, "reply": reply, "after": after})
                    if retained_stop:
                        self.last_owned_stop = {"state_revision": after["state_revision"],
                                                "reason": deepcopy(after.get("last_stop"))}
                    removed.append(identifier)
            remaining = self._rpc("breakpoints.list")["breakpoints"]
            if any(entry["breakpoint_id"] in self.owned for entry in remaining):
                raise ProgressError("Owned probes remain after cleanup")
            self.owned.clear()
            return {"status": "clean", "removed": removed, "foreign_preserved": [entry["breakpoint_id"] for entry in remaining]}
        finally:
            self.deadline = saved_deadline

    @staticmethod
    def _readiness():
        return {"matched_control_dispatch": False, "input_loop_observed": False,
                "input_retired": False, "stable_control_frames": 0,
                "fresh_frame_since_dispatch": False, "fresh_frame_after_input_loop": False}

    def _advance_ready(self, report, folder, *, max_frames, max_stops, stable_frames,
                       max_guest_ms=None, selected=None):
        phase = "dispatch" if selected is not None else "first_loop"
        previous_structure, stable = None, 0
        previous_ticks = (report.get("timing_before") or report["before"]["timing"])["guest_ticks"]
        while report["frames_completed"] < max_frames and len(report["hits"]) < max_stops:
            if self.wait_strategy == "native":
                remaining_guest = max_guest_ms - report["bounded_guest_elapsed_ms"]
                if remaining_guest <= 0:
                    break
                frames = 1 if phase == "settle" else max_frames - report["frames_completed"]
                reply, site = self._step(max_frames=min(frames, self.native_limits["max_frames"]),
                                         max_guest_ms=min(remaining_guest, self.native_limits["max_guest_ms"]))
                budget = reply["bounded"]
                if budget["guest_ticks_before"] != previous_ticks:
                    raise UnexpectedStop("Native guest clock advanced outside the owned wait", {"reply": reply, "previous_ticks": previous_ticks})
                previous_ticks = budget["guest_ticks_after"]
                report["bounded_guest_elapsed_ms"] += budget["guest_elapsed_ms"]
                report["native_waits"].append(deepcopy(budget))
                completed = budget["frames_completed"]
            else:
                reply, site = self._step()
                completed = 1 if site is None else 0
            report["frames_completed"] += completed
            if completed:
                report["last_completed_frame"] = {k: v for k, v in reply.items() if k not in ("registers",)}
                if report["readiness"]["matched_control_dispatch"]:
                    report["readiness"]["fresh_frame_since_dispatch"] = reply.get("frame_id", -1) > report["before"]["frame"]["frame_id"]
            if self.wait_strategy == "native" and reply["bounded"]["stop_cause"] == "guest_time_limit":
                report["timeout_cause"] = "guest_time_limit"
                break
            if site is not None:
                report["hits"].append({"site": f"{CS:04X}:{site:04X}", "guest_ticks": reply.get("guest_ticks"),
                                       "stop_reason": reply["stop_reason"], "registers": reply["registers"]})
                if site == DISPATCH and phase == "dispatch":
                    record = int(reply["registers"]["general"]["edi"], 16) & 0xFFFF
                    if record != selected["control"]["record_offset"]:
                        raise UnexpectedStop("The click selected a different control record", {"observed_record": record, "reply": reply})
                    # A stable record pointer/CE85 wrapper can acquire another
                    # row meaning while input is queued. Re-resolve BEFORE call.
                    current_scene, identity = self._scene_capture(folder, "dispatch")
                    report["dispatch_context"] = {**identity, "scene": current_scene}
                    try:
                        current_selected = self._selection(current_scene, record, None)
                    except ProgressError as error:
                        raise UnexpectedStop("Selected route is no longer applicable at dispatch", {"error": str(error), "reply": reply}) from error
                    before_binding = self._binding(report["before"]["scene"], selected)
                    current_binding = self._binding(current_scene, current_selected)
                    if current_binding != before_binding:
                        raise UnexpectedStop("Selected route rebound before its callback", {"before": before_binding, "at_dispatch": current_binding, "reply": reply})
                    report["readiness"]["matched_control_dispatch"] = True
                    phase = "first_loop"
                    self._arm(INPUT_LOOP)
                elif site == INPUT_LOOP and phase == "first_loop":
                    report["readiness"]["input_loop_observed"] = True
                    phase = "settle"
                elif site == INPUT_LOOP and phase == "final_loop":
                    inputs = self._inputs()
                    current = self._structure_digest()
                    if inputs["neutral"] and current == previous_structure:
                        report["readiness"]["input_retired"] = True
                        report["readiness"]["stable_control_frames"] = stable
                        report["outcome"] = "input_boundary"
                        return
                    phase, stable, previous_structure = "settle", 0, None
                else:
                    raise UnexpectedStop("Owned boundary arrived in an unexpected phase", {"phase": phase, "reply": reply})
            else:
                if phase == "settle":
                    # At least two completed frames after the first owned loop
                    # witness; don't use an unchanged source-cache hash as proof.
                    report["readiness"]["fresh_frame_after_input_loop"] = True
                    inputs = self._inputs()
                    if not inputs["neutral"]:
                        stable, previous_structure = 0, None
                        continue
                    current = self._structure_digest()
                    stable = stable + 1 if current == previous_structure else 1
                    previous_structure = current
                    if stable >= stable_frames:
                        phase = "final_loop"
                        self._arm(INPUT_LOOP)
        report["outcome"] = "timeout"

    def await_ready(self, *, max_frames=1800, max_stops=12, host_budget_ms=30000,
                    stable_frames=2, reconcile_partial=False, max_guest_ms=30000):
        """Wait without input; return a token qualified at the observed loop.

        A flight/animation can leave the prior menu's rectangles in memory.
        This operation waits for code actually to reach the input loop. It does
        not submit or replay any choice. ``reconcile_partial=True`` explicitly
        retires this controller's blocked attempt only after a successful fresh
        boundary; the original attempt's effects remain as observed/unknown.
        """
        if (type(max_frames) is not int or not 1 <= max_frames <= 10000
                or type(max_stops) is not int or not 2 <= max_stops <= 32
                or type(stable_frames) is not int or not 2 <= stable_frames <= 10
                or not 1 <= host_budget_ms <= 30000 or type(reconcile_partial) is not bool
                or type(max_guest_ms) is not int or not 1 <= max_guest_ms <= 30000):
            raise ValueError("Readiness budgets are outside the bounded wait profile")
        if self.uncertain:
            raise ProgressError("Readiness cannot continue after uncertain dispatch")
        if self.continuation_refused:
            raise ProgressError("The preserved stop needs external recovery; an input-free wait cannot resume its rejected route")
        if self.owned:
            raise ProgressError("Surviving owned probes require reconciliation before a new wait")
        self.sequence += 1
        folder = self.root / f"readiness-{self.sequence:04d}"
        folder.mkdir(mode=0o700)
        started, initial_counts, initial_bytes = time.monotonic(), self.counts.copy(), self.memory_bytes
        was_blocked = self.blocked
        self.ready_token = None
        self.deadline = started + host_budget_ms / 1000
        report = {"schema": "dune-progress-readiness-1", "process_epoch": self.epoch,
                  "session_id": self.session_id, "source_sha256": SOURCE_SHA256,
                  "controller_source_sha256": self.implementation_sha256,
                  "input_attempted": False, "input_sent": False, "story_commit": "unknown",
                  "outcome": "declined", "hits": [], "frames_completed": 0,
                  "strategies": {"wait": self.wait_strategy, "read": self.read_strategy},
                  "bounded_guest_elapsed_ms": 0 if self.wait_strategy == "native" else None,
                  "native_waits": [], "native_limits": self.native_limits,
                  "before": self.latest, "after": None, "readiness": self._readiness(),
                  "reconcile_partial_requested": reconcile_partial,
                  "bounds": {"max_frames": max_frames, "max_stops": max_stops,
                             "host_admission_ms": host_budget_ms, "stable_frames": stable_frames,
                             "native_guest_ms": max_guest_ms if self.wait_strategy == "native" else None}}
        try:
            status = self._status()
            reason = status.get("last_stop", {})
            if (reason.get("kind") in ("breakpoint", "budget")
                    and self.last_owned_stop != {"state_revision": status["state_revision"], "reason": reason}):
                raise UnexpectedStop("Readiness cannot resume a breakpoint/budget this controller did not qualify", {"status": status})
            if reason.get("kind") not in ("frame", "pause", "entry", "breakpoint", "budget"):
                raise UnexpectedStop("Readiness cannot resume an unknown stop kind", {"status": status})
            # A verified own guest deadline can stop inside a drawing overlay
            # or interrupt, away from Dune's UI CS/DS. Resume only input-free;
            # hook bytes stay checked and the eventual owned D214 stop must
            # again satisfy the full mapping before any actionable snapshot.
            _context(self._rpc("state.get_registers"),
                     require_mapping=not (self.wait_strategy == "native" and reason.get("kind") == "budget"))
            if self._rpc("breakpoints.list")["breakpoints"]:
                raise ProgressError("Existing probes prevent this private wait's admission")
            report["timing_before"] = self._rpc("execution.timing")
            report["code_bindings"] = {f"{INPUT_LOOP:04X}": self._code(INPUT_LOOP)}
            self._arm(INPUT_LOOP)
            self._advance_ready(report, folder, max_frames=max_frames, max_stops=max_stops,
                                stable_frames=stable_frames, max_guest_ms=max_guest_ms)
            if report["outcome"] == "input_boundary":
                report["after"] = self._snapshot(folder, "after", readiness=report["readiness"])
                report["guest_elapsed_ms"] = (report["bounded_guest_elapsed_ms"] if self.wait_strategy == "native"
                                              else report["after"]["timing"]["guest_ticks"] - report["timing_before"]["guest_ticks"])
                self.latest = deepcopy(report["after"])
                self.ready_token = self.latest["scene_token"]
        except BaseException as error:
            report["outcome"] = ("uncertain_dispatch" if self.uncertain else "timeout" if isinstance(error, BudgetExpired)
                                 else "unexpected_stop" if isinstance(error, UnexpectedStop) else "observation_error")
            report["error"] = {"type": type(error).__name__, "message": str(error), "evidence": getattr(error, "evidence", None)}
        finally:
            self.deadline = None
            try:
                report["cleanup"] = self._cleanup() if self.owned else {"status": "none"}
            except BaseException as error:
                report["cleanup"] = {"status": "failed", "error": repr(error)}
                report["outcome"] = "uncertain_dispatch" if self.uncertain else "cleanup_failed"
            success = report["outcome"] == "input_boundary"
            if not success:
                self.ready_token = None
            if report["outcome"] in ("unexpected_stop", "cleanup_failed", "uncertain_dispatch"):
                self.continuation_refused = True
            self.blocked = was_blocked and not (success and reconcile_partial)
            report["partial_reconciled"] = was_blocked and success and reconcile_partial
            report["continuation_allowed"] = not self.continuation_refused and not self.uncertain
            report["uncertain_dispatch"] = self.uncertain
            report["metrics"] = {"host_ms": (time.monotonic() - started) * 1000,
                                 "rpc_by_method": dict(self.counts - initial_counts),
                                 "memory_bytes_read": self.memory_bytes - initial_bytes,
                                 "selection_requests": 0, "model_calls_by_controller": 0,
                                 "model_turns_outside_controller": None}
            report["report_path"] = str(folder / "report.json")
            _write(folder / "report.json", report)
        return report

    def perform(self, scene_token, *, control_record=None, label=None, max_frames=120,
                max_stops=12, host_budget_ms=15000, hold_ms=80, stable_frames=2, max_guest_ms=5000):
        """Attempt one selected control; return evidence without another model poll.

        A successful ``input_boundary``/``context_changed`` result concerns only
        the witnessed interface boundary. ``story_commit`` is always unknown.
        Any partial or uncertain action blocks further input by this instance;
        the caller must reconcile it instead of retrying the original click.
        """
        if (type(max_frames) is not int or not 1 <= max_frames <= 600
                or type(max_stops) is not int or not 3 <= max_stops <= 32
                or type(stable_frames) is not int or not 2 <= stable_frames <= 10
                or not 1 <= host_budget_ms <= 60000 or type(hold_ms) is not int or not 1 <= hold_ms <= 1000
                or type(max_guest_ms) is not int or not 1 <= max_guest_ms <= 30000):
            raise ValueError("Action budgets are outside the bounded experiment profile")
        if self.uncertain or self.blocked:
            raise ProgressError("A partial/uncertain attempt must be reconciled before further input")
        self.sequence += 1
        folder = self.root / f"action-{self.sequence:04d}"
        folder.mkdir(mode=0o700)
        started, initial_counts, initial_bytes = time.monotonic(), self.counts.copy(), self.memory_bytes
        self.deadline = started + host_budget_ms / 1000
        report = {"schema": "dune-progress-action-1", "process_epoch": self.epoch,
                  "session_id": self.session_id, "source_sha256": SOURCE_SHA256,
                  "controller_source_sha256": self.implementation_sha256,
                  "selected_from_token": scene_token, "input_attempted": False, "input_sent": False,
                  "story_commit": "unknown", "outcome": "declined", "hits": [],
                  "frames_completed": 0, "before": self.latest, "after": None,
                  "strategies": {"wait": self.wait_strategy, "read": self.read_strategy},
                  "bounded_guest_elapsed_ms": 0 if self.wait_strategy == "native" else None,
                  "native_waits": [], "native_limits": self.native_limits,
                  "bounds": {"max_frames": max_frames, "max_stops": max_stops,
                             "host_admission_ms": host_budget_ms, "stable_frames": stable_frames,
                             "native_guest_ms": max_guest_ms if self.wait_strategy == "native" else None},
                  "readiness": self._readiness()}
        try:
            if self.latest is None or scene_token != self.latest["scene_token"]:
                raise ProgressError("Selection token is stale or belongs to another process observation")
            if self.ready_token != scene_token:
                raise ProgressError("Selection needs an await_ready input-loop token; retained rectangles alone are insufficient")
            selected = self._selection(self.latest["scene"], control_record, label)
            report["selected"] = selected
            status = self._status()
            if status["state_revision"] != self.latest["state_revision"] or status.get("last_stop") != self.latest["stop"]:
                raise ProgressError("Native state advanced since the selected observation")
            _context(self._rpc("state.get_registers"))
            if self.read_strategy == "full":
                if _sha(self._memory(DS * 16, 65536)) != self.latest["ds_sha256"]:
                    raise ProgressError("Dune data changed since the selected observation")
            else:
                _, admission = self._scene_capture(folder, "admission")
                report["admission_capture"] = admission
                after_admission = self._status()
                if (status["state_revision"] != after_admission["state_revision"]
                        or status.get("last_stop") != after_admission.get("last_stop")):
                    raise UnexpectedStop("Sparse admission changed while reading dependencies")
                if admission["memory_capture"]["dependency_sha256"] != self.latest["memory_capture"]["dependency_sha256"]:
                    raise ProgressError("Parsed Dune dependencies changed since the selected observation")
            if not self._inputs()["neutral"]:
                raise ProgressError("Action admission requires neutral input")
            if self._rpc("breakpoints.list")["breakpoints"]:
                raise ProgressError("Existing probes prevent this private action's admission")
            report["code_bindings"] = {f"{offset:04X}": self._code(offset)
                                        for offset in (DISPATCH, INPUT_LOOP, selected["control"]["callback"])}
            self._arm(DISPATCH)
            self.ready_token = None
            report["input_attempted"] = True
            report["input_sent"] = None  # A missing acknowledgement cannot establish non-delivery.
            receipt = self._rpc("input.mouse.click", {"x": selected["x"], "y": selected["y"],
                                "button": "left", "hold_ms": hold_ms,
                                "frame_id": self.latest["frame"]["frame_id"], "mode_id": self.latest["frame"]["mode_id"]})
            report["input_receipt"] = receipt
            report["input_sent"] = True
            report["intent_to_queued_ms"] = (time.monotonic() - started) * 1000
            if receipt.get("accepted") is not True or receipt.get("delivery") != "queued":
                raise ProgressError("Input receipt does not establish the expected queued click")
            self._advance_ready(report, folder, max_frames=max_frames, max_stops=max_stops,
                                stable_frames=stable_frames, max_guest_ms=max_guest_ms, selected=selected)
            if report["outcome"] == "input_boundary":
                if not report["readiness"]["fresh_frame_since_dispatch"]:
                    raise ProgressError("No new completed frame was witnessed after dispatch")
                report["after"] = self._snapshot(folder, "after", readiness=report["readiness"])
                before_scene, after_scene = self.latest["scene"], report["after"]["scene"]
                report["changes"] = {key: {"before": before_scene.get(key), "after": after_scene.get(key)}
                                      for key in ("location_key", "subject_selector_431b", "ui_mode_4247", "menu", "controls", "conversation_witness", "text_buffer_candidate")
                                      if before_scene.get(key) != after_scene.get(key)}
                if before_scene["menu_admission_sha256"] != after_scene["menu_admission_sha256"]:
                    report["outcome"] = "context_changed"
                report["guest_elapsed_ms"] = (report["bounded_guest_elapsed_ms"] if self.wait_strategy == "native"
                                              else report["after"]["timing"]["guest_ticks"] - self.latest["timing"]["guest_ticks"])
                self.latest = deepcopy(report["after"])
                self.ready_token = self.latest["scene_token"]
        except BaseException as error:
            report["outcome"] = ("uncertain_dispatch" if self.uncertain else "timeout" if isinstance(error, BudgetExpired)
                                 else "unexpected_stop" if isinstance(error, UnexpectedStop)
                                 else "observation_error" if report["input_attempted"] else "declined")
            report["error"] = {"type": type(error).__name__, "message": str(error),
                               "evidence": getattr(error, "evidence", None)}
        finally:
            self.deadline = None
            try:
                report["cleanup"] = self._cleanup() if self.owned else {"status": "none"}
            except BaseException as error:
                report["cleanup"] = {"status": "failed", "error": repr(error)}
                report["outcome"] = "uncertain_dispatch" if self.uncertain else "cleanup_failed"
            report["uncertain_dispatch"] = self.uncertain
            self.blocked = report["input_attempted"] and report["outcome"] not in ("input_boundary", "context_changed")
            # Reaching a preserved pre-call stop is not permission to execute
            # it later through an input-free wait. Only an already validated
            # route with a certain bounded timeout is continuable here.
            if ((self.blocked and not (report["outcome"] == "timeout"
                                      and report["readiness"]["matched_control_dispatch"] and self.stopped))
                    or report["outcome"] in ("unexpected_stop", "cleanup_failed", "uncertain_dispatch")):
                self.continuation_refused = True
            if self.blocked or report["outcome"] in ("cleanup_failed", "uncertain_dispatch", "unexpected_stop"):
                self.ready_token = None
            report["continuation_allowed"] = not self.continuation_refused and not self.uncertain
            report["metrics"] = {"host_ms": (time.monotonic() - started) * 1000,
                                 "rpc_by_method": dict(self.counts - initial_counts),
                                 "memory_bytes_read": self.memory_bytes - initial_bytes,
                                 "selection_requests": 1, "model_calls_by_controller": 0,
                                 "model_turns_outside_controller": None}
            report["report_path"] = str(folder / "report.json")
            _write(folder / "report.json", report)
        return report


def continue_conversation(controller, scene_token, *, max_actions=6, max_frames=720, host_budget_ms=15000):
    """Repeat the exact observed quoted TALK TO ME route within one conversation.

    This is an explicitly delegated dialogue macro, never a generic automatic
    click-through policy. Each click uses the preceding action's qualified token.
    Stop on a repeated/cyclic dialogue witness, changed menu/subject/site, unavailable
    exact label, any incomplete attempt, or cumulative action/frame/host limits.
    Retain each candidate line without declaring its story meaning or rendering.
    """
    if (type(max_actions) is not int or not 1 <= max_actions <= 12
            or type(max_frames) is not int or not 1 <= max_frames <= 1440
            or not 1 <= host_budget_ms <= 30000):
        raise ValueError("Conversation budgets are outside the bounded macro profile")
    if controller.uncertain or controller.blocked:
        raise ProgressError("A partial/uncertain attempt must be reconciled before a conversation macro")
    if (controller.latest is None or scene_token != controller.latest["scene_token"]
            or controller.ready_token != scene_token):
        raise ProgressError("Conversation macro requires a fresh input-loop token")
    before = deepcopy(controller.latest)
    scene = before["scene"]

    def conversation_context(value):
        site = value.get("site_witness", {})
        return (value["menu"]["menu_offset"], value["subject_selector_431b"],
                _digest(value.get("location_key")), site.get("current_record_114e"), site.get("selected_record_4258"))

    context = conversation_context(scene)
    if context[0] != 0x2608 or not isinstance(scene.get("dialogue_witness_sha256"), str):
        raise ProgressError("Conversation macro requires the qualified conversation context/witness")
    controller.sequence += 1
    folder = controller.root / f"conversation-{controller.sequence:04d}"
    folder.mkdir(mode=0o700)
    started = time.monotonic()
    deadline = started + host_budget_ms / 1000
    initial_counts, initial_bytes = controller.counts.copy(), controller.memory_bytes
    report = {"schema": "dune-progress-conversation-1", "process_epoch": controller.epoch,
              "session_id": controller.session_id, "source_sha256": SOURCE_SHA256,
              "exact_label": TALK_LABEL, "before": before, "after": before,
              "story_commit": "unknown", "outcome": "action_limit", "steps": [],
              "frames_completed": 0,
              "bounds": {"max_actions": max_actions, "max_frames": max_frames,
                         "host_admission_ms": host_budget_ms},
              "macro_source_sha256": _MODULE_SOURCE_SHA256,
              "controller_source_sha256": getattr(controller, "implementation_sha256", None)}
    seen = {scene["dialogue_witness_sha256"]}
    try:
        for index in range(max_actions):
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            remaining_frames = max_frames - report["frames_completed"]
            if remaining_ms < 1 or remaining_frames < 1:
                report["outcome"] = "host_limit" if remaining_ms < 1 else "frame_limit"
                break
            try:
                controller._selection(scene, None, TALK_LABEL)
            except ProgressError as error:
                report["outcome"] = "choice_unavailable"
                report["detail"] = str(error)
                break
            action = controller.perform(scene_token, label=TALK_LABEL, max_frames=min(120, remaining_frames),
                                        host_budget_ms=min(15000, remaining_ms))
            report["frames_completed"] += action["frames_completed"]
            step = {"index": index, "outcome": action["outcome"], "report_path": action["report_path"],
                    "input_attempted": action["input_attempted"], "input_sent": action["input_sent"],
                    "metrics": action["metrics"], "guest_elapsed_ms": action.get("guest_elapsed_ms"),
                    "before_dialogue_witness": scene["dialogue_witness_sha256"]}
            report["steps"].append(step)
            if action["outcome"] not in ("input_boundary", "context_changed"):
                report["outcome"] = "action_incomplete"
                report["detail"] = action["outcome"]
                break
            after = action["after"]
            report["after"] = after
            scene_token, scene = after["scene_token"], after["scene"]
            witness = scene.get("dialogue_witness_sha256")
            step["after_dialogue_witness"] = witness
            step["text_buffer_candidate"] = scene.get("text_buffer_candidate")
            step["conversation_witness"] = scene.get("conversation_witness")
            if conversation_context(scene) != context:
                report["outcome"] = "conversation_context_changed"
                break
            if not isinstance(witness, str):
                report["outcome"] = "witness_unavailable"
                break
            if witness in seen:
                report["outcome"] = "dialogue_repeated"
                break
            seen.add(witness)
    finally:
        report["metrics"] = {"host_ms": (time.monotonic() - started) * 1000,
                             "rpc_by_method": dict(controller.counts - initial_counts),
                             "memory_bytes_read": controller.memory_bytes - initial_bytes,
                             "macro_requests": 1, "model_calls_by_controller": 0,
                             "model_turns_outside_controller": None}
        report["report_path"] = str(folder / "report.json")
        _write(folder / "report.json", report)
    return report
