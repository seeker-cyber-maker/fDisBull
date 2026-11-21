"""Selected, original-input travel-map actions for the qualified Dune edition.

``MapSelector(controller).prepare(ready_token, site_record=...)`` only reads a
stopped scene. Its private, single-use token binds a rendered point and the
callback/hit-test dependencies to that exact ready observation. ``select``
revalidates them, queues one click, stops before the map callback at D2FE, then
proves its accepted target at 4D74. A later input boundary is separate evidence;
neither event establishes travel arrival or a story commit.

This deliberately supports only menu2794/mode1/gate04 and the complete observed
2176 callback vector, including its idle and held-input slots. It requires
explicit native bounded waiting and the supplied
ProgressController's existing ownership adapter. It does not launch, restore,
take ownership, write game state, invoke a callback directly, or replay input.
All receipts remain in that controller's private evidence directory.

Host time is an admission budget. As with the base controller's cleanup, the
status fence for an already acknowledged observer change may finish after that
deadline; no new input or execution is admitted by this bookkeeping exception.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import uuid


MAP_DISPATCH, MAP_ACCEPT = 0xD2FE, 0x4D74
MAP_VECTOR, MAP_CALLBACK = 0x2176, 0x4D4E
MAP_VECTOR_WORDS = (0x4D9F, MAP_CALLBACK, 0x133D, 0x133D, 0x133D, 0x4D9F, 0x4D9F)
MAP_MENU, MAP_MODE, MAP_GATE = 0x2794, 1, 4
MAP_TABLE, MAX_POINTS = 0xA107, 40
FIRST_SITE, SITE_STRIDE, MAX_SITES = 0x0100, 0x1C, 128
# Half-open qualified code ranges, including the relevant terminating returns.
CODE_RANGES = ((0xD093, 0xD0F2), (0xD214, 0xD219), (0xD26A, 0xD340),
               (0x4D4E, 0x4DF7), (0x6ABD, 0x6AD6), (0x6C0D, 0x6C70))
_MODULE_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _word(registers, name):
    return int(registers["general"][name], 16) & 0xFFFF


def _stop(status):
    return {"state_revision": status["state_revision"], "reason": deepcopy(status.get("last_stop"))}


def _scene_binding(scene):
    """Stable route meaning; hover-selected4258, cursor and timers are not it."""
    menu = scene["menu"]
    rows = deepcopy(menu["rows"])
    for row in rows:
        if "metadata" in row:
            row["metadata"] &= 0x7FFF  # The menu's hover highlight is transient.
    site = scene["site_witness"]
    return {"location": deepcopy(scene["location_key"]),
            "subject": scene["subject_selector_431b"], "mode": scene["ui_mode_4247"],
            "menu": {**{key: deepcopy(menu.get(key)) for key in
                        ("stack_slot", "menu_offset", "page_skip", "paging_mode", "special_row", "visible_rows")},
                     "rows": rows},
            "controls": [{key: deepcopy(control[key]) for key in
                          ("record_offset", "bounds", "active", "value", "callback")}
                         for control in scene["controls"]],
            "site": {key: deepcopy(site[key]) for key in
                     ("current_record_114e", "current_name_candidate", "site_location_context",
                      "map_mode_4247", "map_points_context_active", "rendered_map_points")}}


class MapSelector:
    """One selected map intent, using an existing process-local controller.

    Preparation and selection reports are copies. Modifying a returned target,
    scene or binding cannot modify the private pending intent. A new preparation
    invalidates the previous pending token; every selection attempt consumes it.
    """

    def __init__(self, controller):
        # Research controllers are also loaded directly from retained source
        # paths. Reuse the actual supplied class's helpers and exception types,
        # rather than importing a second, possibly differently named copy.
        namespace = controller._advance_ready.__func__.__globals__
        if namespace.get("ProgressController") not in type(controller).__mro__:
            raise TypeError("MapSelector requires the qualified ProgressController")
        self._error = namespace["ProgressError"]
        self._unexpected = namespace["UnexpectedStop"]
        self._budget_expired = namespace["BudgetExpired"]
        self._context, self._write = namespace["_context"], namespace["_write"]
        self._cs, self._ds = namespace["CS"], namespace["DS"]
        self._input_loop, self._rectangle_dispatch = namespace["INPUT_LOOP"], namespace["DISPATCH"]
        if controller.wait_strategy != "native" or controller.native_limits is None:
            raise self._error("Map selection requires explicit native bounded waiting; no frame fallback is qualified")
        self.controller = controller
        self.implementation_sha256 = _MODULE_SOURCE_SHA256
        self.__pending = None

    def _report(self, kind):
        c = self.controller
        c.sequence += 1
        folder = c.root / f"map-{kind}-{c.sequence:04d}"
        folder.mkdir(mode=0o700)
        report = {"schema": "dune-map-" + ("preparation-1" if kind == "prepare" else "action-1"),
                  "process_epoch": c.epoch, "session_id": c.session_id,
                  "source_sha256": hashlib.sha256(c.source).hexdigest(), "source_size": len(c.source),
                  "controller_source_sha256": c.implementation_sha256,
                  "map_selector_source_sha256": self.implementation_sha256,
                  "strategies": {"wait": c.wait_strategy, "read": c.read_strategy},
                  "outcome": "declined", "input_attempted": False, "input_sent": False,
                  "destination_accepted": False, "acceptance": None,
                  "input_ready": False, "arrival": "unknown", "story_commit": "unknown",
                  "report_path": str(folder / "report.json")}
        return folder, report, time.monotonic(), c.counts.copy(), c.memory_bytes

    def _finish(self, folder, report, started, counts, memory_bytes, *, selections):
        c = self.controller
        report["uncertain_dispatch"] = c.uncertain
        report["continuation_allowed"] = not c.uncertain and not c.continuation_refused
        report["metrics"] = {"host_ms": (time.monotonic() - started) * 1000,
                             "rpc_by_method": dict(c.counts - counts),
                             "memory_bytes_read": c.memory_bytes - memory_bytes,
                             "selection_requests": selections, "model_calls_by_controller": 0,
                             "model_turns_outside_controller": None}
        self._write(folder / "report.json", report)
        return deepcopy(report)

    def _available(self):
        c = self.controller
        if c.uncertain or c.blocked or c.continuation_refused:
            raise self._error("A partial, rejected or uncertain attempt requires external recovery or permitted reconciliation")
        if c.owned or c.deadline is not None:
            raise self._error("The controller has surviving observers or an active operation")

    def _probes(self):
        c = self.controller
        entries = c._rpc("breakpoints.list")["breakpoints"]
        expected = {identifier: probe for identifier, probe in c.owned.items() if probe["active"]}
        if len(entries) != len(expected):
            raise self._unexpected("Map admission found a foreign, missing or changed observer", {"breakpoints": entries})
        for entry in entries:
            probe = expected.get(entry.get("breakpoint_id"))
            address = entry.get("address", {})
            try:
                matches = (probe is not None and entry.get("kind") == "execution" and entry.get("once") is True
                           and address.get("space") == "segmented"
                           and int(address["segment"], 16) == self._cs
                           and int(address["offset"], 16) == probe["offset"])
            except (KeyError, TypeError, ValueError):
                matches = False
            if not matches:
                raise self._unexpected("Map admission found a foreign, missing or changed observer", {"breakpoints": entries})

    def _fence(self, before, after):
        if _stop(before) != _stop(after):
            raise self._unexpected("Map dependencies changed while capturing stopped evidence", {"before": before, "after": after})

    def _code(self):
        return {f"{start:04X}-{end:04X}": self.controller._code(start, end - start)
                for start, end in CODE_RANGES}

    def _route(self):
        c, base = self.controller, self._ds * 16
        gate = c._memory(base + 0x11D6, 1)[0]
        viewport = list(struct.unpack("<4H", c._memory(base + 0x423F, 8)))
        pointer = struct.unpack("<H", c._memory(base + 0x2A5C, 2))[0]
        if pointer != MAP_VECTOR:
            raise self._error("The map callback vector is outside the qualified2176 profile")
        vector = list(struct.unpack("<7H", c._memory(base + pointer, 14)))
        mode = c._memory(base + 0x4247, 1)[0]
        current = struct.unpack("<H", c._memory(base + 0x114E, 2))[0]
        pending = c._memory(base + 0x4235, 1)[0]
        raw = c._memory(base + MAP_TABLE, MAX_POINTS * 6)
        entries, types = [], {}
        for index in range(MAX_POINTS):
            offset = index * 6
            record, x, packed = struct.unpack_from("<3H", raw, offset)
            if record == 0:
                used = raw[:offset + 2]
                break
            # 6C0D dereferences type BEFORE filtering mode. Validate every
            # nonzero pointer, including points for another rendered mode.
            if not (FIRST_SITE <= record < FIRST_SITE + MAX_SITES * SITE_STRIDE
                    and (record - FIRST_SITE) % SITE_STRIDE == 0):
                raise self._error("Map hit-test table contains an unbounded site pointer")
            if record not in types:
                types[record] = c._memory(base + record + 8, 1)[0]
            entries.append({"entry_offset": MAP_TABLE + offset, "site_record": record,
                            "screen_xy": [x, packed & 0xFF], "mode": packed >> 8,
                            "type_byte_0008": types[record]})
        else:
            raise self._error("Map hit-test table has no terminator before the text buffer")
        return {"gate": gate, "viewport": viewport, "pointer": pointer, "vector": vector,
                "mode": mode, "current_record": current, "pending_4235": pending,
                "table_bytes_hex": used.hex(), "table_sha256": hashlib.sha256(used).hexdigest(),
                "entries": entries, "site_types": {str(key): value for key, value in types.items()}}

    def _target(self, scene, frame, route, site_record):
        if (scene["menu"]["menu_offset"] != MAP_MENU or scene["ui_mode_4247"] != MAP_MODE
                or route["mode"] != MAP_MODE or route["gate"] != MAP_GATE
                or route["vector"] != list(MAP_VECTOR_WORDS) or route["pending_4235"] != 0):
            raise self._error("Scene is outside the qualified travel menu2794/mode1/gate04 callback profile")
        site = scene["site_witness"]
        if (site["map_mode_4247"] != MAP_MODE or site["map_points_context_active"] is not True
                or site["current_record_114e"] != route["current_record"]):
            raise self._error("Map mode/current-site witnesses disagree")
        if (frame["width"], frame["height"]) != (320, 200):
            raise self._error("The map requires the qualified320x200 image geometry")
        x0, y0, x1, y1 = route["viewport"]
        if not (0 <= x0 < x1 <= 320 and 0 <= y0 < y1 <= 200):
            raise self._error("Map viewport leaves the qualified image bounds")
        raw_points = [point for point in route["entries"] if point["mode"] == MAP_MODE]
        points = site["rendered_map_points"]
        raw_shape = [{key: point[key] for key in ("entry_offset", "site_record", "screen_xy", "mode")}
                     for point in raw_points]
        scene_shape = [{key: point[key] for key in ("entry_offset", "site_record", "screen_xy", "mode")}
                       for point in points]
        if raw_shape != scene_shape:
            raise self._error("Rendered point candidates disagree with the raw hit-test table")
        for point, raw_point in zip(points, raw_points):
            if point["site"].get("type_byte_0008") != raw_point["type_byte_0008"]:
                raise self._error("Rendered site eligibility disagrees with the raw site record")
        eligible = [point for point in raw_points if point["type_byte_0008"] < 0xFF]
        if len({point["site_record"] for point in eligible}) != len(eligible):
            raise self._error("Eligible map points contain a duplicate site binding")
        matches = [point for point in points if point["site_record"] == site_record]
        if len(matches) != 1:
            raise self._error("Selected site is absent or ambiguous in the rendered map")
        target = matches[0]
        if (target["site"].get("type_byte_0008", 0xFF) >= 0xFF
                or target["mode"] != MAP_MODE or not target["site"].get("name_candidate")):
            raise self._error("Selected rendered point is not eligible for the qualified callback")
        if site_record == route["current_record"]:
            raise self._error("Gate04 refuses the current site as a travel destination")
        x, y = target["screen_xy"]
        if not (0 <= x < 320 and 0 <= y < 200 and x0 <= x < x1 and y0 <= y < y1):
            raise self._error("Selected map point leaves the image or current viewport")
        distances = [(abs(point["screen_xy"][0] - x) + abs(point["screen_xy"][1] - y), point["site_record"])
                     for point in eligible]
        nearest = min(distance for distance, _ in distances)
        winners = [record for distance, record in distances if distance == nearest]
        if nearest >= 9 or winners != [site_record]:
            raise self._error("Map hit-test has no unique eligible target within its distance bound")
        if any(control["active"] and control["bounds"][0] < x < control["bounds"][2]
               and control["bounds"][1] < y <= control["bounds"][3] for control in scene["controls"]):
            raise self._error("Selected map point overlaps an active rectangle route")
        return deepcopy(target)

    def _ready_capture(self, folder, name, expected):
        c = self.controller
        status = c._status()
        if status["state_revision"] != expected["state_revision"] or status.get("last_stop") != expected["stop"]:
            raise self._error("Native state advanced since the selected ready observation")
        self._probes()
        packet = c._snapshot(folder, name, readiness=expected["input_boundary"])
        if packet["scene"] != expected["scene"]:
            raise self._error("The stopped scene changed since the selected ready observation")
        memory_key = "ds_sha256" if c.read_strategy == "full" else "memory_capture"
        if c.read_strategy == "full":
            same_memory = packet[memory_key] == expected[memory_key]
        else:
            same_memory = packet[memory_key]["dependency_sha256"] == expected[memory_key]["dependency_sha256"]
        if not same_memory:
            raise self._error("Dune observation dependencies changed before map admission")
        frame_keys = ("frame_id", "mode_id", "width", "height")
        if any(packet["frame"][key] != expected["frame"][key] for key in frame_keys):
            raise self._error("The selected image identity changed before map admission")
        route, code = self._route(), self._code()
        self._fence(status, c._status())
        return packet, route, code

    def prepare(self, scene_token, *, site_record: int):
        """Bind an explicitly selected site without executing or injecting input."""
        self.__pending = None
        folder, report, started, counts, memory_bytes = self._report("prepare")
        c = self.controller
        report["selected_from_token"], report["requested_site_record"] = scene_token, site_record
        try:
            self._available()
            if type(site_record) is not int or not (FIRST_SITE <= site_record < FIRST_SITE + MAX_SITES * SITE_STRIDE
                                                  and (site_record - FIRST_SITE) % SITE_STRIDE == 0):
                raise self._error("Select one bounded site_record integer")
            if c.latest is None or scene_token != c.latest["scene_token"] or c.ready_token != scene_token:
                raise self._error("Map preparation requires the controller's current await_ready scene token")
            before = deepcopy(c.latest)
            packet, route, code = self._ready_capture(folder, "prepared", before)
            target = self._target(packet["scene"], packet["frame"], route, site_record)
            binding = {"process_epoch": c.epoch, "session_id": c.session_id,
                       "scene_token": scene_token, "state_revision": before["state_revision"],
                       "stop": before["stop"], "scene": _scene_binding(packet["scene"]),
                       "route": route, "code": code, "target": target,
                       "frame": {key: packet["frame"][key] for key in ("frame_id", "mode_id", "width", "height")}}
            token = uuid.uuid4().hex
            self.__pending = deepcopy({"token": token, "before": before, "binding": binding})
            report.update(outcome="prepared", selection_token=token, before=packet, target=target,
                          binding=binding, binding_sha256=_digest(binding))
        except BaseException as error:
            report["outcome"] = ("uncertain_dispatch" if c.uncertain else "unexpected_stop"
                                 if isinstance(error, self._unexpected) else "declined")
            report["error"] = {"type": type(error).__name__, "message": str(error), "evidence": getattr(error, "evidence", None)}
            if c.uncertain or isinstance(error, self._unexpected):
                c.ready_token, c.continuation_refused = None, True
        return self._finish(folder, report, started, counts, memory_bytes, selections=0)

    def _arm(self, offset, status):
        c = self.controller
        retained_stop = c.last_owned_stop == _stop(status)
        try:
            c._arm(offset)
        except BaseException as error:
            if c.uncertain or isinstance(error, self._budget_expired):
                raise
            raise self._unexpected("Map observer creation was not acknowledged as requested",
                                   {"error": str(error), "before": status}) from error
        # Finish the fence for an already acknowledged observer mutation, just
        # as _cleanup finishes observer bookkeeping after host admission ends.
        # _rpc still forbids every native call after uncertainty. Restore the
        # same deadline before any subsequent input or execution admission.
        deadline, c.deadline = c.deadline, None
        try:
            after = c._status()
        finally:
            c.deadline = deadline
        if after["state_revision"] != status["state_revision"] + 1 or after.get("last_stop") != status.get("last_stop"):
            raise self._unexpected("Map observer creation changed more than its expected revision", {"before": status, "after": after})
        if retained_stop:
            c.last_owned_stop = _stop(after)
        return after

    def _wait(self, report, expected, *, max_frames, max_stops, max_guest_ms):
        c = self.controller
        while report["frames_completed"] < max_frames and len(report["hits"]) < max_stops:
            remaining_guest = max_guest_ms - report["bounded_guest_elapsed_ms"]
            if remaining_guest <= 0:
                break
            try:
                reply, site = c._step(max_frames=min(max_frames - report["frames_completed"], c.native_limits["max_frames"]),
                                      max_guest_ms=min(remaining_guest, c.native_limits["max_guest_ms"]))
            except BaseException as error:
                report["failed_wait"] = deepcopy(getattr(error, "evidence", None))
                raise
            budget = reply["bounded"]
            report["native_waits"].append(deepcopy(budget))
            if budget["guest_ticks_before"] != report["last_validated_guest_ticks"]:
                raise self._unexpected("Native guest clock advanced outside the owned map action", {"reply": reply})
            report["last_validated_guest_ticks"] = budget["guest_ticks_after"]
            report["bounded_guest_elapsed_ms"] += budget["guest_elapsed_ms"]
            report["frames_completed"] += budget["frames_completed"]
            if budget["frames_completed"]:
                report["last_completed_frame"] = {key: value for key, value in reply.items() if key != "registers"}
            if site is not None:
                report["hits"].append({"site": f"{self._cs:04X}:{site:04X}", "guest_ticks": reply.get("guest_ticks"),
                                       "stop_reason": deepcopy(reply["stop_reason"]), "registers": deepcopy(reply["registers"])})
                if site != expected:
                    raise self._unexpected("The original click reached a forbidden or unexpected map route", {"expected": expected, "reply": reply})
                return reply
            if budget["stop_cause"] == "guest_time_limit":
                report["timeout_cause"] = "guest_time_limit"
                break
        report["outcome"] = "timeout"
        report.setdefault("timeout_cause", "frame_limit" if report["frames_completed"] >= max_frames
                          else "stop_limit" if len(report["hits"]) >= max_stops else "guest_time_limit")
        return None

    def _at_hook(self, folder, name, reply, binding):
        try:
            return self._capture_hook(folder, name, reply, binding)
        except BaseException as error:
            if (self.controller.uncertain
                    or isinstance(error, (self._unexpected, self._budget_expired))):
                raise
            raise self._unexpected("The selected map route became inapplicable before acceptance",
                                   {"error": str(error), "reply": reply}) from error

    def _capture_hook(self, folder, name, reply, binding):
        c = self.controller
        status = c._status(reply)
        self._probes()
        registers = c._rpc("state.get_registers")
        self._context(registers)
        if (int(registers["instruction_pointer"], 16) != int(reply["registers"]["instruction_pointer"], 16)
                or registers["general"] != reply["registers"]["general"]):
            raise self._unexpected("The map hook registers changed before dependency capture", {"reply": reply, "registers": registers})
        scene, identity = c._scene_capture(folder, name)
        route, code = self._route(), self._code()
        self._fence(status, c._status())
        target = self._target(scene, binding["frame"], route, binding["target"]["site_record"])
        if (_scene_binding(scene) != binding["scene"] or route != binding["route"]
                or code != binding["code"] or target != binding["target"]):
            raise self._unexpected("The selected map route rebound before acceptance", {"scene": scene, "route": route, "reply": reply})
        return {"scene": scene, "route": route, "code": code, "registers": registers, **identity}

    def select(self, selection_token, *, max_frames=600, max_stops=12, host_budget_ms=15000,
               hold_ms=40, stable_frames=2, max_guest_ms=5000):
        """Consume one prepared intent and attempt exactly one original click."""
        if (type(max_frames) is not int or not 1 <= max_frames <= 600
                or type(max_stops) is not int or not 1 <= max_stops <= 32
                or type(stable_frames) is not int or not 2 <= stable_frames <= 10
                or type(hold_ms) is not int or not 1 <= hold_ms <= 1000
                or type(max_guest_ms) is not int or not 1 <= max_guest_ms <= 30000
                or type(host_budget_ms) not in (int, float) or not math.isfinite(host_budget_ms)
                or not 1 <= host_budget_ms <= 60000):
            raise ValueError("Map action budgets are outside the bounded experiment profile")
        pending, self.__pending = self.__pending, None
        folder, report, started, counts, memory_bytes = self._report("select")
        c = self.controller
        report.update(selected_from_token=selection_token, before=None, after=None, hits=[],
                      frames_completed=0, bounded_guest_elapsed_ms=0, native_waits=[],
                      native_limits=deepcopy(c.native_limits), readiness=c._readiness(),
                      bounds={"max_frames": max_frames, "max_stops": max_stops,
                              "host_admission_ms": host_budget_ms, "native_guest_ms": max_guest_ms,
                              "hold_ms": hold_ms, "stable_frames": stable_frames,
                              "observer_bookkeeping_may_finish_after_host_deadline": True})
        report["readiness"]["matched_map_dispatch"] = False
        if pending is None or not isinstance(selection_token, str) or selection_token != pending["token"]:
            # A consumed/foreign token is a local refusal even if an earlier
            # attempt left the controller uncertain. Do not touch that attempt's
            # observers or call any native API while reporting this refusal.
            report["error"] = {"type": self._error.__name__, "message": "Map selection token is absent, stale, already consumed or from another selector", "evidence": None}
            report["cleanup"] = {"status": "none"}
            return self._finish(folder, report, started, counts, memory_bytes, selections=1)
        prior_blocked = c.blocked
        installed_deadline = False
        owns_observers = False
        try:
            self._available()
            before, binding = pending["before"], pending["binding"]
            report.update(before=deepcopy(before), target=deepcopy(binding["target"]), binding_sha256=_digest(binding))
            if (c.epoch != binding["process_epoch"] or c.session_id != binding["session_id"]
                    or c.latest != before or c.ready_token != binding["scene_token"]):
                raise self._error("The prepared map selection no longer names the controller's ready observation")
            c.deadline, installed_deadline = started + host_budget_ms / 1000, True
            packet, route, code = self._ready_capture(folder, "admission", before)
            target = self._target(packet["scene"], packet["frame"], route, binding["target"]["site_record"])
            if route != binding["route"] or code != binding["code"] or target != binding["target"]:
                raise self._error("Map target or callback dependencies changed since preparation")
            report["admission"] = packet
            report["action_timing_before"] = deepcopy(packet["timing"])
            report["last_validated_guest_ticks"] = packet["timing"]["guest_ticks"]
            status = c._status()
            self._fence({"state_revision": before["state_revision"], "last_stop": before["stop"]}, status)
            c.ready_token = None
            owns_observers = True
            status = self._arm(self._rectangle_dispatch, status)
            status = self._arm(MAP_DISPATCH, status)
            c.blocked = True
            report["input_attempted"], report["input_sent"] = True, None
            x, y = target["screen_xy"]
            receipt = c._rpc("input.mouse.click", {"x": x, "y": y, "button": "left", "hold_ms": hold_ms,
                             "frame_id": binding["frame"]["frame_id"], "mode_id": binding["frame"]["mode_id"]})
            report["input_receipt"] = receipt
            report["input_sent"] = receipt.get("accepted") is True and receipt.get("delivery") == "queued"
            if not report["input_sent"]:
                raise self._error("Input receipt does not establish the one expected queued click")
            queued = c._status(receipt)
            if (receipt.get("state_revision") != status["state_revision"] + 1
                    or queued.get("last_stop") != status.get("last_stop")):
                raise self._unexpected("Queued map input changed more than its acknowledged revision",
                                       {"before": status, "receipt": receipt, "after": queued})
            report["queued_stop"] = _stop(queued)
            report["intent_to_queued_ms"] = (time.monotonic() - started) * 1000
            limits = {"max_frames": max_frames, "max_stops": max_stops, "max_guest_ms": max_guest_ms}
            dispatch = self._wait(report, MAP_DISPATCH, **limits)
            if dispatch is not None:
                context = self._at_hook(folder, "dispatch", dispatch, binding)
                report["dispatch_context"] = context
                registers = context["registers"]
                if (_word(registers, "esi") != binding["route"]["pointer"]
                        or [_word(registers, "edx"), _word(registers, "ebx")] != [x, y]):
                    raise self._unexpected("The pre-call vector or pointer coordinates differ from the selected map intent", {"reply": dispatch})
                report["readiness"]["matched_map_dispatch"] = True
                self._arm(MAP_ACCEPT, c._status(dispatch))
                accepted = self._wait(report, MAP_ACCEPT, **limits)
                if accepted is not None:
                    context = self._at_hook(folder, "acceptance", accepted, binding)
                    report["acceptance_context"] = context
                    selected_record = context["scene"]["site_witness"]["selected_record_4258"]
                    register_record = _word(context["registers"], "edi")
                    if selected_record != target["site_record"] or register_record != target["site_record"]:
                        raise self._unexpected("Map acceptance names a different site than the selected intent", {"selected_record": selected_record,
                                               "register_record": register_record, "reply": accepted})
                    report["destination_accepted"] = True
                    report["acceptance"] = {"site": f"{self._cs:04X}:{MAP_ACCEPT:04X}", "target_record": target["site_record"],
                                            "selected_record": selected_record, "register_record": register_record,
                                            "state_revision": accepted["state_revision"], "guest_ticks": accepted["guest_ticks"]}
                    # Retire the forbidden-rectangle observer before the final
                    # snapshot; its deletion revision must not stale a new token.
                    report["acceptance_cleanup"] = c._cleanup()
                    status = c._status()
                    if c.last_owned_stop != _stop(status):
                        raise self._unexpected("Map acceptance stop changed after owned-observer cleanup", {"status": status})
                    self._arm(self._input_loop, status)
                    # _advance_ready consumes the same cumulative counters and
                    # remaining budgets. Its first tick is this phase's start,
                    # not the action's start before the two map hooks.
                    report["timing_before"] = {"guest_ticks": report["last_validated_guest_ticks"]}
                    c._advance_ready(report, folder, stable_frames=stable_frames, **limits)
                    if report["native_waits"]:
                        report["last_validated_guest_ticks"] = report["native_waits"][-1]["guest_ticks_after"]
                    if report["outcome"] == "input_boundary":
                        report["readiness"]["fresh_frame_since_dispatch"] = report.get("last_completed_frame", {}).get("frame_id", -1) > before["frame"]["frame_id"]
                        if not report["readiness"]["fresh_frame_since_dispatch"]:
                            raise self._error("No new completed frame was witnessed after map acceptance")
                        report["after"] = c._snapshot(folder, "after", readiness=report["readiness"])
                        if before["scene"]["menu_admission_sha256"] != report["after"]["scene"]["menu_admission_sha256"]:
                            report["outcome"] = "context_changed"
                        report["input_ready"] = True
                        c.latest = deepcopy(report["after"])
                        c.ready_token = c.latest["scene_token"]
            report["guest_elapsed_ms"] = report["bounded_guest_elapsed_ms"]
        except BaseException as error:
            report["outcome"] = ("uncertain_dispatch" if c.uncertain else "timeout" if isinstance(error, self._budget_expired)
                                 else "unexpected_stop" if isinstance(error, self._unexpected)
                                 else "observation_error" if report["input_attempted"] else "declined")
            report["error"] = {"type": type(error).__name__, "message": str(error), "evidence": getattr(error, "evidence", None)}
            if isinstance(error, self._budget_expired):
                report["timeout_cause"] = "host_admission_limit"
        finally:
            if installed_deadline:
                c.deadline = None
            try:
                report["cleanup"] = c._cleanup() if owns_observers and c.owned else {"status": "none"}
            except BaseException as error:
                report["cleanup"] = {"status": "failed", "error": repr(error)}
                report["outcome"] = "uncertain_dispatch" if c.uncertain else "cleanup_failed"
            success = report["outcome"] in ("input_boundary", "context_changed")
            c.blocked = prior_blocked or (report["input_attempted"] and not success)
            if ((report["input_attempted"] and not success
                 and not (report["outcome"] == "timeout" and report["destination_accepted"] and c.stopped))
                    or report["outcome"] in ("unexpected_stop", "cleanup_failed", "uncertain_dispatch")):
                c.continuation_refused = True
            if not success:
                report["input_ready"] = False
                if report["input_attempted"] or report["outcome"] in ("unexpected_stop", "cleanup_failed", "uncertain_dispatch"):
                    c.ready_token = None
        return self._finish(folder, report, started, counts, memory_bytes, selections=1)
