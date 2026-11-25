"""Persistent QEMU before-execution capture for owned DOS process sessions.

This adapter deliberately preserves native dispatch observations as raw
machine evidence. It does not infer instruction bytes, source identity, mode,
or architectural completion from a program counter.
"""
from __future__ import annotations

from copy import deepcopy
import re
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_control import QMPCommandError
from .qemu_machine import machine_trace_operation


MAX_TRACE_EVENTS = 10_000
MAX_TRACE_PAGE = 4_096
DETAILS = frozenset(("short", "normal", "long", "csip"))
_CURSOR = re.compile(r"qtrace:([0-9a-f]{32}):(\d+):(\d+)\Z")


def _trace_operation(label):
    def decorate(function):
        return machine_trace_operation(function, label=label, default_timeout_ms=15000)
    return decorate


def _uint(value, label, maximum=(1 << 64) - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise DebuggerError("QEMU trace producer returned invalid " + label)
    return value


def _owner(session):
    """Capture the identities that keep one live DOS trace authorized."""
    vm = session.vm
    process = getattr(session, "_process", None)
    if (getattr(session, "closed", False) or vm.qmp is None or vm.process is None
            or vm.process.poll() is not None or not isinstance(process, dict)
            or process.get("state") != "active" or process.get("machine_closed")
            or not process.get("source_mapping", {}).get("live")
            or process.get("capture_epoch") != getattr(session, "_runtime_epoch", None)):
        raise DebuggerError("QEMU before-fetch trace requires the active owned DOS process epoch")
    return dict(session_id=session.session_id, vm=vm, qmp=vm.qmp, process=vm.process,
                source_epoch=session._runtime_epoch, process_nonce=process.get("nonce"))


def _same_owner(session, capture, *, source_epoch=True):
    vm = getattr(session, "vm", None)
    process = getattr(session, "_process", None)
    same_machine = (not getattr(session, "closed", False)
            and vm is capture["vm"] and vm.qmp is capture["qmp"]
            and vm.process is capture["process"] and vm.process is not None
            and vm.process.poll() is None
            and session.session_id == capture["session_id"])
    if not same_machine:
        return False
    return (not source_epoch or (isinstance(process, dict) and not process.get("machine_closed")
            and process.get("state") == "active"
            and process.get("source_mapping", {}).get("live")
            and process.get("nonce") == capture["process_nonce"]
            and session._runtime_epoch == capture["source_epoch"]
            and process.get("capture_epoch") == capture["source_epoch"]))


def _native_page(session, capture, after, limit, *, stop=False, cleanup=False):
    owner = capture["owner"]
    if not _same_owner(session, owner, source_epoch=not cleanup):
        raise DebuggerError("QEMU trace owner or source epoch changed")
    command = "x-fdisbull-trace-stop" if stop else "x-fdisbull-trace-read"
    arguments = {"epoch": capture["producer_epoch"], "after-sequence": after,
                 "max-events": limit}
    raw = owner["qmp"].call(command, arguments)
    if not isinstance(raw, dict):
        raise DebuggerError("QEMU trace producer returned an invalid page")
    if raw.get("epoch") != capture["producer_epoch"]:
        raise DebuggerError("QEMU trace producer epoch changed")
    for key in ("instruction-count", "captured-count", "oldest-sequence", "next-sequence", "dropped-count"):
        _uint(raw.get(key), key)
    if raw["instruction-count"] != capture["instruction_count"]:
        raise DebuggerError("QEMU trace producer count differs from its owner")
    if raw["captured-count"] > capture["instruction_count"]:
        raise DebuggerError("QEMU trace producer exceeded its instruction budget")
    if raw["dropped-count"]:
        raise DebuggerError("QEMU trace ring dropped before-fetch events")
    if type(raw.get("active")) is not bool:
        raise DebuggerError("QEMU trace producer omitted active state")
    events = raw.get("events")
    if not isinstance(events, list) or len(events) > limit:
        raise DebuggerError("QEMU trace producer exceeded the requested page bound")
    if raw["next-sequence"] != raw["captured-count"] + 1:
        raise DebuggerError("QEMU trace producer sequence is inconsistent")
    if raw["oldest-sequence"] > raw["next-sequence"]:
        raise DebuggerError("QEMU trace producer oldest sequence is invalid")
    if after + 1 < raw["oldest-sequence"] and raw["captured-count"]:
        raise DebuggerError("QEMU trace cursor expired in the native ring")
    normalized = []
    previous = after
    for event in events:
        if not isinstance(event, dict):
            raise DebuggerError("QEMU trace producer returned a malformed event")
        sequence = _uint(event.get("sequence"), "event sequence")
        if sequence <= previous or sequence <= after or sequence >= raw["next-sequence"]:
            raise DebuggerError("QEMU trace producer returned duplicate or out-of-order events")
        if event.get("reason") != "before-execution":
            raise DebuggerError("QEMU trace event lacks the before-execution marker")
        if event.get("origin") not in ("tcg-dispatch", "breakpoint-pre-dispatch"):
            raise DebuggerError("QEMU trace event lacks a recognized native origin")
        _uint(event.get("pc"), "event pc")
        _uint(event.get("vcpu"), "event vcpu", 0xffffffff)
        if event["vcpu"] != 0:
            raise DebuggerError("QEMU trace event belongs to an unselected vCPU")
        if event["sequence"] != previous + 1:
            raise DebuggerError("QEMU trace producer omitted a before-fetch event")
        native = {key: event[key] for key in ("sequence", "vcpu", "pc", "reason", "origin")}
        normalized.append(dict(sequence=sequence,
            address={"space": "virtual", "offset": f"0x{event['pc']:X}"},
            native=native,
            observation={"registers_stage": "before-instruction",
                         "instruction_completed": None,
                         "evidence": ("native QEMU breakpoint pre-dispatch stop"
                                      if event["origin"] == "breakpoint-pre-dispatch"
                                      else "native QEMU TCG pre-execution dispatch")}))
        previous = sequence
    if normalized and normalized[0]["sequence"] <= after:
        raise DebuggerError("QEMU trace page did not advance its cursor")
    if raw["captured-count"] and after + 1 < raw["oldest-sequence"]:
        raise DebuggerError("QEMU trace page omitted retained events")
    return raw, normalized


class QemuFetchTraceMixin:
    """Expose trace.start/read/stop on the narrow QEMU DOS RPC facade."""

    _qemu_fetch_trace = None

    def _trace_rpc(self, method, params):
        if params is not None and type(params) is not dict:
            raise ValueError("QEMU trace parameters must be an object")
        params = dict(params or {})
        supplied_session = params.pop("session_id", self.session_id)
        if supplied_session != self.session_id:
            raise ValueError("QEMU trace request belongs to another session lifetime")
        if method == "trace.start":
            if set(params) != {"detail", "instruction_count"}:
                raise ValueError("trace.start requires only detail and instruction_count")
            return self._trace_start(**params)
        if method == "trace.read":
            if set(params) != {"cursor", "limit"}:
                raise ValueError("trace.read requires only cursor and limit")
            return self._trace_read(**params)
        if params:
            raise ValueError("trace.stop takes no parameters")
        return self._trace_stop()

    @_trace_operation("QEMU before-fetch trace start")
    def _trace_start(self, *, detail, instruction_count):
        if type(detail) is not str or detail not in DETAILS:
            raise ValueError("Trace detail must be short, normal, long, or csip")
        if type(instruction_count) is not int or not 1 <= instruction_count <= MAX_TRACE_EVENTS:
            raise ValueError("Trace instruction_count must be 1..10000")
        active = self._qemu_fetch_trace
        if isinstance(active, dict) and active.get("state") in ("starting", "active", "start-uncertain", "stop-uncertain"):
            raise DebuggerError("A QEMU before-fetch trace is already active or uncertain")
        owner = _owner(self)
        if self.status().get("state") != "stopped":
            raise ValueError("QEMU trace.start requires a stopped DOS process")
        if not _same_owner(self, owner):
            raise DebuggerError("QEMU trace owner changed during start admission")
        if "x-fdisbull-trace-start" not in getattr(owner["vm"], "qmp_commands", set()):
            raise ValueError("QEMU native before-fetch trace producer is unavailable")
        capture = dict(state="starting", owner=owner, detail=detail,
                       instruction_count=instruction_count, trace_id=uuid.uuid4().hex,
                       events=[], last_sequence=0, available_sequence=0,
                       captured_count=0)
        self._qemu_fetch_trace = capture
        try:
            raw = owner["qmp"].call("x-fdisbull-trace-start",
                                    {"instruction-count": instruction_count})
            if not isinstance(raw, dict):
                raise DebuggerError("QEMU trace producer returned an invalid start receipt")
            epoch = _uint(raw.get("epoch"), "producer epoch")
            if (raw.get("instruction-count") != instruction_count
                    or raw.get("active") is not True):
                raise DebuggerError("QEMU trace producer did not admit the requested capture")
            capacity = _uint(raw.get("capacity"), "ring capacity", MAX_TRACE_EVENTS)
            first_sequence = _uint(raw.get("next-sequence"), "initial sequence")
            if capacity != instruction_count or first_sequence < 1:
                raise DebuggerError("QEMU trace producer ring cannot retain the requested capture")
            capture.update(state="active", producer_epoch=epoch, capacity=capacity,
                           captured_count=0, last_sequence=first_sequence - 1,
                           available_sequence=first_sequence - 1)
        except BaseException as error:
            if isinstance(error, QMPCommandError):
                self._qemu_fetch_trace = None
            else:
                capture["state"] = "start-uncertain"
                self._trace_close_uncertain(owner["vm"], capture, error, "start")
            raise
        return dict(active=True, detail=detail, instruction_count=instruction_count,
                    trace_id=capture["trace_id"], epoch=epoch, capacity=capacity,
                    next_sequence=first_sequence,
                    cursor=f"qtrace:{capture['trace_id']}:{epoch}:{first_sequence - 1}")

    @_trace_operation("QEMU before-fetch trace read")
    def _trace_read(self, *, cursor, limit):
        if type(limit) is not int or not 1 <= limit <= MAX_TRACE_PAGE:
            raise ValueError("Trace limit must be 1..4096")
        capture = self._qemu_fetch_trace
        if not isinstance(capture, dict) or capture.get("state") not in ("active", "stopped"):
            raise DebuggerError("No QEMU before-fetch trace has been started")
        if cursor is None:
            after = 0
        else:
            if type(cursor) is not str:
                raise ValueError("Trace cursor must be null or an opaque QEMU trace cursor")
            match = _CURSOR.fullmatch(cursor)
            if match is None:
                raise ValueError("Trace cursor must be null or an opaque QEMU trace cursor")
            if (match.group(1) != capture["trace_id"]
                    or int(match.group(2)) != capture["producer_epoch"]):
                raise DebuggerError("QEMU trace cursor belongs to another capture epoch")
            after = int(match.group(3))
        if after > capture["available_sequence"]:
            raise ValueError("Trace cursor is ahead of the producer sequence")
        if capture["state"] == "active":
            raw, events = _native_page(self, capture, after, limit)
            if events:
                known = {item["sequence"] for item in capture["events"]}
                for event in events:
                    if event["sequence"] not in known:
                        capture["events"].append(event)
                capture["last_sequence"] = max(capture["last_sequence"], events[-1]["sequence"])
            active = raw["active"]
            capture["captured_count"] = raw["captured-count"]
            capture["available_sequence"] = raw["next-sequence"] - 1
        else:
            events = [deepcopy(item) for item in capture["events"] if item["sequence"] > after][:limit]
            active = False
        more = bool(events and events[-1]["sequence"] < capture["available_sequence"])
        current = events[-1]["sequence"] if events else after
        current_cursor = f"qtrace:{capture['trace_id']}:{capture['producer_epoch']}:{current}"
        next_cursor = current_cursor if more else None
        return dict(active=active, events=events, next_cursor=next_cursor,
                    cursor=current_cursor, trace_id=capture["trace_id"],
                    epoch=capture["producer_epoch"], requested_count=capture["instruction_count"],
                    captured_count=capture["captured_count"],
                    dropped_count=0)

    @_trace_operation("QEMU before-fetch trace stop")
    def _trace_stop(self):
        capture = self._qemu_fetch_trace
        if not isinstance(capture, dict) or capture.get("state") not in ("active", "stop-uncertain"):
            raise DebuggerError("No active QEMU before-fetch trace has been started")
        if self.status().get("state") != "stopped":
            raise ValueError("QEMU trace.stop requires a stopped DOS process")
        owner = capture["owner"]
        if not _same_owner(self, owner, source_epoch=False):
            capture["state"] = "invalidated"
            raise DebuggerError("QEMU trace owner changed; native capture cannot be safely stopped")
        try:
            tail = []
            raw, events = _native_page(self, capture, capture["last_sequence"], MAX_TRACE_PAGE,
                                       stop=True, cleanup=True)
            if events:
                tail.extend(events)
                capture["events"].extend(events)
                capture["last_sequence"] = events[-1]["sequence"]
            if raw["active"]:
                raise DebuggerError("QEMU trace producer remained active after trace.stop")
            final_count = raw["captured-count"]
            while capture["last_sequence"] < final_count:
                raw, events = _native_page(self, capture, capture["last_sequence"],
                                           MAX_TRACE_PAGE, cleanup=True)
                if not events:
                    raise DebuggerError("QEMU trace stop drain ended before the retained tail")
                tail.extend(events)
                capture["events"].extend(events)
                capture["last_sequence"] = events[-1]["sequence"]
                if raw["captured-count"] != final_count or raw["active"]:
                    raise DebuggerError("QEMU trace stop drain changed its final capture state")
            capture["state"] = "stopped"
            capture["captured_count"] = raw["captured-count"]
            capture["available_sequence"] = raw["next-sequence"] - 1
        except BaseException as error:
            capture["state"] = "stop-uncertain"
            self._trace_close_uncertain(owner["vm"], capture, error, "stop")
            raise
        return dict(active=False, event_count=raw["captured-count"], events=tail,
                    trace_id=capture["trace_id"], epoch=capture["producer_epoch"],
                    requested_count=capture["instruction_count"], dropped_count=0)

    @staticmethod
    def _trace_close_uncertain(vm, capture, error, phase):
        """Close the owned VM when a dispatched native mutation is ambiguous."""
        receipt = dict(phase=phase, state=capture.get("state"), trace_id=capture.get("trace_id"),
                       producer_epoch=capture.get("producer_epoch"),
                       requested_count=capture.get("instruction_count"),
                       observed_event_count=len(capture.get("events", ())),
                       observed_sequences=[event["sequence"] for event in capture.get("events", ())])
        try:
            vm.close()
            receipt["vm_closed"] = True
        except BaseException as cleanup_error:
            receipt["vm_closed"] = False
            receipt["close_error"] = {"type": type(cleanup_error).__name__,
                                       "message": str(cleanup_error)}
        try:
            error.trace_capture_result = receipt
        except BaseException:
            pass
