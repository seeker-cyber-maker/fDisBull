"""Experimental Kyra debugger boundary, not a bundled or executable engine.

The peer must implement the documented kyra-emc2-debug-1 protocol. This module
can be exercised against a protocol test double; those tests do not qualify a
ScummVM build. No native launch method or production backend is registered here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
import time
from typing import Any, Protocol

from .processor import Location
from .westwood_emc2 import EMC2Processor
from .westwood_media import parse_emc2

PROTOCOL = "kyra-emc2-debug-1"
PROFILES = {"kyrandia1-dos": "kyra1", "lol1-dos": "lol"}
MAX_WORDS = 262144
READ_BYTES = 4096
MAX_TRACE = 2048
_REQUIRED = {"state.get", "resources.list", "resource.read", "run", "step",
             "break.add", "break.remove"}
_PHASES = {"boot", "emc_before", "emc_after", "backend_yield", "exited"}
_REASONS = {"entry", "breakpoint", "syscall", "budget", "pause", "host_timeout", "quit"}


class KyraProtocolError(ValueError):
    """The peer or a supplied record violates this bounded experiment contract."""


class Peer(Protocol):
    """Existing ScummVMRPC-compatible interface; process ownership is external."""

    def call(self, op: str, params: dict | None = None, *, timeout_ms: int = 15000) -> dict: ...
    def close(self) -> None: ...


def _integer(value: Any, name: str, low: int = 0, high: int = (1 << 53) - 1) -> int:
    if type(value) is not int or not low <= value <= high:
        raise KyraProtocolError(f"{name} must be an integer in {low}..{high}")
    return value


def _hex(value: Any, length: int) -> bytes:
    if (not isinstance(value, str) or len(value) != 2 * length
            or re.fullmatch(r"[0-9a-fA-F]*", value) is None):
        raise KyraProtocolError("resource response must contain exact hexadecimal bytes")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class ScriptBinding:
    """An explicit caller-selected original, with byte and word spaces separate."""

    name: str
    profile: str
    source_sha256: str
    data_sha256: str
    ordr_sha256: str
    data_offset: int
    entries: tuple[int | None, ...]
    data: bytes = field(repr=False)
    ordr: bytes = field(repr=False)
    processor: EMC2Processor = field(repr=False, compare=False)

    @classmethod
    def from_bytes(cls, name: str, source: bytes, *, profile: str) -> ScriptBinding:
        if profile not in PROFILES:
            raise KyraProtocolError("select kyrandia1-dos or lol1-dos explicitly")
        if (not isinstance(name, str) or not name or len(name) > 255
                or any(c in name for c in ("/", "\\", "\0")) or name in (".", "..")):
            raise KyraProtocolError("script name must be a simple advisory member name")
        if not isinstance(source, bytes):
            raise KyraProtocolError("script source must be immutable bytes")
        parsed = parse_emc2(source)
        chunks = parsed["chunks"]
        data = source[chunks["DATA"]["offset"]:chunks["DATA"]["offset"] + chunks["DATA"]["size"]]
        ordr = source[chunks["ORDR"]["offset"]:chunks["ORDR"]["offset"] + chunks["ORDR"]["size"]]
        if not data or len(data) // 2 > MAX_WORDS or len(ordr) // 2 > MAX_WORDS:
            raise KyraProtocolError("script word count exceeds the scaffold budget")
        skip = int(profile == "lol1-dos")
        entries = tuple(None if x == 65535 else x + skip for x in parsed["entry_slots"])
        if any(x is not None and x >= len(data) // 2 for x in entries):
            raise KyraProtocolError("entry adjustment lies outside DATA")
        first = next((i for i, x in enumerate(entries) if x is not None), None)
        if first is None:
            raise KyraProtocolError("script has no admitted entry point")
        processor = EMC2Processor(source, profile=profile, function_index=first)
        return cls(name, profile, parsed["sha256"], sha256(data).hexdigest(),
                   sha256(ordr).hexdigest(), chunks["DATA"]["offset"], entries,
                   data, ordr, processor)

    def location(self, word_offset: int) -> dict:
        _integer(word_offset, "word_offset", 0, len(self.data) // 2 - 1)
        return {"space": "westwood-emc2", "profile": self.profile,
                "source_sha256": self.source_sha256,
                "data_word_offset": word_offset, "data_byte_offset": 2 * word_offset,
                "file_byte_offset": self.data_offset + 2 * word_offset}

    def instruction(self, word_offset: int) -> dict:
        pos = self.location(word_offset)
        decoded = self.processor.decode(
            self.processor.source,
            Location(self.processor.info.address_space, pos["file_byte_offset"]))
        if decoded is None:
            raise KyraProtocolError("no instruction at supplied word offset")
        # Successful decoding at an aligned word is not proof of reachability.
        return {"position": pos, "facts": dict(decoded.facts),
                "reachability": "not_established", "syscall_semantics": "game_specific_unbound"}


@dataclass(frozen=True)
class LoadedBinding:
    resource_id: int
    generation: int
    script: ScriptBinding = field(repr=False)

    def receipt(self) -> dict:
        return {"resource_id": self.resource_id, "generation": self.generation,
                "source_sha256": self.script.source_sha256,
                "data_sha256": self.script.data_sha256,
                "ordr_sha256": self.script.ordr_sha256,
                "profile": self.script.profile,
                "verified_scope": "complete canonical load-snapshot DATA and ORDR",
                "current_unexecuted_words_verified": False,
                "text_verified": False, "archive_search_order_verified": False,
                "original_dos_execution_verified": False}


class KyraScaffold:
    """Read-only VM binding and bounded execution client for an owned RPC peer.

    The RPC peer supplies process ownership, hard host deadlines, framed JSON,
    and fail-closed transport. MR !73 is the intended reusable transport, but its
    Kyra launcher/native JSON wiring is not implemented by this first stage.
    """

    def __init__(self, peer: Peer, *, profile: str):
        if profile not in PROFILES:
            raise KyraProtocolError("unsupported Kyra profile")
        self.peer = peer
        self.profile = profile
        self.closed = False
        self._revision = -1
        self._bindings: dict[int, LoadedBinding] = {}
        self._points: set[int] = set()
        try:
            hello = self._request("hello")
            expected = {"protocol": PROTOCOL, "engine": "kyra",
                        "profile": profile, "game_id": PROFILES[profile],
                        "original_x86_executed": False}
            if any(type(hello.get(k)) is not type(v) or hello.get(k) != v for k, v in expected.items()):
                raise KyraProtocolError("Kyra peer identity/profile mismatch")
            if (not isinstance(hello.get("capabilities"), list)
                    or not all(isinstance(x, str) for x in hello["capabilities"])
                    or not _REQUIRED <= set(hello["capabilities"])):
                raise KyraProtocolError("peer lacks required Kyra debugger capabilities")
            if hello.get("provider") not in ("scummvm", "inhouse", "test-double"):
                raise KyraProtocolError("peer must identify its provider explicitly")
            if re.fullmatch(r"[0-9a-f]{64}", str(hello.get("provider_sha256", ""))) is None:
                raise KyraProtocolError("peer must identify its exact provider build")
            self.hello = hello
            self.capabilities = frozenset(hello["capabilities"])
            self.engine_state()
        except BaseException:
            self.close()
            raise

    def _request(self, operation: str, params: dict | None = None, *, timeout_ms: int = 15000) -> dict:
        _integer(timeout_ms, "timeout_ms", 1, 600000)
        if self.closed:
            raise KyraProtocolError("Kyra scaffold peer is closed")
        try:
            result = self.peer.call(operation, params, timeout_ms=timeout_ms)
            if not isinstance(result, dict):
                raise KyraProtocolError("peer response must be an object")
            return result
        except BaseException:
            # Never replay a call whose execution or response is uncertain.
            self.close()
            raise

    def _position(self, value: Any) -> dict | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise KyraProtocolError("invalid VM position")
        keys = ("resource_id", "generation", "word_offset", "context_id", "span_id", "parent_span_id")
        record = {key: _integer(value.get(key), key, 0 if key in ("word_offset", "parent_span_id") else 1)
                  for key in keys}
        _integer(record["word_offset"], "word_offset", 0, MAX_WORDS - 1)
        bound = self._bindings.get(record["resource_id"])
        record["source_binding"] = None
        if bound is not None:
            if record["generation"] == bound.generation:
                record["source_binding"] = bound.script.location(record["word_offset"])
            else:
                self._bindings.pop(record["resource_id"], None)
        return {"space": "kyra-emc2-vm", **record}

    def engine_state(self, *, timeout_ms: int = 15000) -> dict:
        try:
            state = self._request("state.get", timeout_ms=timeout_ms).get("state")
            if not isinstance(state, dict) or state.get("phase") not in _PHASES:
                raise KyraProtocolError("invalid Kyra execution phase")
            if type(state.get("paused")) is not bool or not state["paused"]:
                raise KyraProtocolError("state reads require a confirmed paused peer")
            revision = _integer(state.get("revision"), "revision")
            if revision < self._revision:
                raise KyraProtocolError("peer state revision moved backwards")
            self._revision = revision
            position = self._position(state.get("position"))
            if state["phase"] in ("emc_before", "emc_after") and position is None:
                raise KyraProtocolError("EMC safe point omitted its VM position")
            return {**state, "position": position, "profile": self.profile,
                    "provider": self.hello["provider"] if hasattr(self, "hello") else None,
                    "original_x86_executed": False,
                    "registers": "not_exposed_in_stage1", "tim_vm": "not_instrumented"}
        except BaseException:
            self.close()
            raise

    def resources(self, *, timeout_ms: int = 15000) -> list[dict]:
        records = self._request("resources.list", timeout_ms=timeout_ms).get("resources")
        try:
            if not isinstance(records, list) or len(records) > 256:
                raise KyraProtocolError("invalid or excessive loaded resources")
            seen = set()
            for record in records:
                if not isinstance(record, dict):
                    raise KyraProtocolError("resource metadata must be an object")
                rid = _integer(record.get("resource_id"), "resource_id", 1)
                if rid in seen:
                    raise KyraProtocolError("duplicate loaded resource ID")
                seen.add(rid)
                _integer(record.get("generation"), "generation", 1)
                for key in ("data_words", "ordr_words"):
                    _integer(record.get(key), key, 0, MAX_WORDS)
                if (record.get("encoding") != "be16-canonical"
                        or not isinstance(record.get("name"), str)
                        or not 1 <= len(record["name"]) <= 255):
                    raise KyraProtocolError("resource encoding/name is invalid")
            live = {(x["resource_id"], x["generation"]) for x in records}
            self._bindings = {rid: b for rid, b in self._bindings.items()
                              if (rid, b.generation) in live}
            return records
        except BaseException:
            self.close()
            raise

    def bind(self, script: ScriptBinding, resource_id: int, *, timeout_ms: int = 15000) -> LoadedBinding:
        if script.profile != self.profile:
            raise KyraProtocolError("script and runtime profiles differ")
        _integer(resource_id, "resource_id", 1)
        _integer(timeout_ms, "timeout_ms", 1, 600000)
        deadline = time.monotonic() + timeout_ms / 1000
        def remaining() -> int:
            ms = int((deadline - time.monotonic()) * 1000)
            if ms < 1:
                raise TimeoutError("source binding exhausted its shared host budget")
            return ms
        revision = self.engine_state(timeout_ms=remaining())["revision"]
        record = next((x for x in self.resources(timeout_ms=remaining())
                       if x["resource_id"] == resource_id), None)
        if record is None or record["name"].casefold() != script.name.casefold():
            raise KyraProtocolError("selected native resource does not match the requested member name")
        if (record["data_words"] * 2 != len(script.data)
                or record["ordr_words"] * 2 != len(script.ordr)):
            raise KyraProtocolError("native word extents differ from original")
        for component, expected in (("DATA", script.data), ("ORDR", script.ordr)):
            for offset in range(0, len(expected), READ_BYTES):
                count = min(READ_BYTES, len(expected) - offset)
                params = {"resource_id": resource_id, "generation": record["generation"],
                          "component": component, "offset": offset, "length": count}
                reply = self._request("resource.read", params, timeout_ms=remaining())
                if (any(type(reply.get(k)) is not type(v) or reply.get(k) != v for k, v in params.items())
                        or type(reply.get("revision")) is not int or reply["revision"] != revision):
                    self.close()
                    raise KyraProtocolError("resource identity or paused revision changed while binding")
                try:
                    observed = _hex(reply.get("hex"), count)
                except KyraProtocolError:
                    self.close()
                    raise
                if observed != expected[offset:offset + count]:
                    raise KyraProtocolError("loaded canonical words differ from caller-selected original")
        if self.engine_state(timeout_ms=remaining())["revision"] != revision:
            self.close()
            raise KyraProtocolError("paused revision changed during binding")
        bound = LoadedBinding(resource_id, record["generation"], script)
        self._bindings[resource_id] = bound
        return bound

    def breakpoint(self, bound: LoadedBinding, word_offset: int) -> dict:
        if self._bindings.get(bound.resource_id) is not bound:
            raise KyraProtocolError("binding is stale or belongs to another session")
        instruction = bound.script.instruction(word_offset)
        record = next((x for x in self.resources() if x["resource_id"] == bound.resource_id), None)
        if record is None or record["generation"] != bound.generation:
            raise KyraProtocolError("resource generation changed; rebind before setting a breakpoint")
        params = {"resource_id": bound.resource_id, "generation": bound.generation,
                  "word_offset": word_offset, "expected_hex": instruction["facts"]["bytes"]}
        reply = self._request("break.add", params)
        try:
            identifier = _integer(reply.get("breakpoint_id"), "breakpoint_id", 1)
        except BaseException:
            self.close()
            raise
        self._points.add(identifier)
        return {"breakpoint_id": identifier, "position": bound.script.location(word_offset),
                "binding": bound.receipt(), "scope": "before EMC dispatch",
                "instruction_boundary_reachability": "not_established"}

    def delete_breakpoint(self, identifier: int) -> dict:
        _integer(identifier, "breakpoint_id", 1)
        if identifier not in self._points:
            raise KyraProtocolError("breakpoint is not owned by this session")
        reply = self._request("break.remove", {"breakpoint_id": identifier})
        if reply.get("removed") is not True:
            self.close()
            raise KyraProtocolError("breakpoint removal was not confirmed")
        self._points.remove(identifier)
        return reply

    def _execute(self, operation: str, *, max_instructions: int, timeout_ms: int) -> dict:
        _integer(max_instructions, "max_instructions", 1, 1000000)
        _integer(timeout_ms, "timeout_ms", 100, 600000)
        deadline = time.monotonic() + timeout_ms / 1000
        before = self.engine_state(timeout_ms=timeout_ms)
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining < 20:
            raise TimeoutError("execution budget expired before dispatch")
        requested = 1 if operation == "step" else max_instructions
        native_ms = max(1, remaining - min(500, max(10, remaining // 5)))
        reply = self._request(operation, {"max_instructions": requested, "max_ms": native_ms},
                              timeout_ms=remaining)
        try:
            stop = reply.get("stop")
            if (not isinstance(stop, dict) or stop.get("reason") not in _REASONS
                    or stop.get("phase") not in _PHASES or stop.get("paused") is not True):
                raise KyraProtocolError("execution returned without a confirmed structured stop")
            revision = _integer(stop.get("revision"), "revision")
            if revision < before["revision"]:
                raise KyraProtocolError("execution receipt has stale state revision")
            self._revision = revision
            completed = _integer(stop.get("completed"), "completed", 0, requested)
            spans = stop.get("completed_spans")
            if (not isinstance(spans, list) or len(spans) > MAX_TRACE
                    or any(type(x) is not int or x < 1 for x in spans)
                    or len(set(spans)) != len(spans) or len(spans) != min(completed, MAX_TRACE)):
                raise KyraProtocolError("invalid completion span evidence")
            target = before["position"]["span_id"] if before["phase"] == "emc_before" else None
            position = self._position(stop.get("position"))
            if stop["phase"] in ("emc_before", "emc_after") and position is None:
                raise KyraProtocolError("EMC stop omitted its position")
            starting_completed = (True if target in spans else
                                  None if target is None or completed > len(spans) else False)
            return {**stop, "position": position,
                    "requested_completed_dispatches": requested,
                    "budget_satisfied": completed == requested,
                    "starting_dispatch_completed": starting_completed,
                    "completion_spans_truncated": completed > len(spans),
                    "completion_scope": "EMC dispatches including nested calls; not original CPU instructions",
                    "original_x86_executed": False, "provider": self.hello["provider"]}
        except BaseException:
            self.close()
            raise

    def run(self, *, max_instructions: int = 10000, timeout_ms: int = 10000) -> dict:
        return self._execute("run", max_instructions=max_instructions, timeout_ms=timeout_ms)

    def step(self, *, timeout_ms: int = 10000) -> dict:
        return self._execute("step", max_instructions=1, timeout_ms=timeout_ms)

    def trace_records(self) -> dict:
        if "trace.get" not in self.capabilities:
            raise KyraProtocolError("peer does not expose bounded traces")
        try:
            reply = self._request("trace.get")
            events = reply.get("events")
            dropped = _integer(reply.get("dropped"), "dropped")
            if not isinstance(events, list) or len(events) > MAX_TRACE:
                raise KyraProtocolError("trace exceeds bounded event capacity")
            mapped = []
            for event in events:
                if not isinstance(event, dict) or event.get("kind") not in ("before", "after"):
                    raise KyraProtocolError("invalid trace event kind")
                position = self._position(event.get("position"))
                if position is None:
                    raise KyraProtocolError("trace event omitted its position")
                mapped.append({**event, "position": position})
            return {"events": mapped, "dropped": dropped, "lossless_window": dropped == 0,
                    "whole_run_complete": False, "original_x86_executed": False}
        except BaseException:
            self.close()
            raise

    def save_state(self, *args, **kwargs):
        raise KyraProtocolError("stage1 does not expose saves or exact VM checkpoints")

    def registers(self, *args, **kwargs):
        raise KyraProtocolError("ScummVM Kyra is not the original DOS CPU; typed VM state is deferred")

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.peer.close()
