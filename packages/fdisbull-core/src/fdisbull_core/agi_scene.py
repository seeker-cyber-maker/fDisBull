"""Stopped actor-position projection for the bounded QEMU AGI pilot.

This module consumes caller-owned JSON observations. It neither owns a live VM
nor changes its controls. Current snapshot facts and continuity of the observed
history are separate: resynchronization repairs the former, never the latter.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re


PROFILE = "agi-2917-scalar-position-pilot-1"
_COORDINATES = ("x", "y", "prev_x", "prev_y")
_UINT64 = (1 << 64) - 1
_STATUSES = {"ready", "budget", "return", "fault", "external"}


class SceneInputError(ValueError):
    """An observation is malformed, stale, or belongs to another attachment."""


def _object(value, name):
    if not isinstance(value, dict):
        raise SceneInputError(f"{name} must be an object")
    return value


def _uint(value, name, maximum=_UINT64, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise SceneInputError(f"{name} is outside its integer range")
    return value


def _session(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise SceneInputError("session_id must be a nonempty string of at most 256 characters")
    return value


def _source(value):
    value = _object(value, "source")
    digest = value.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise SceneInputError("source.sha256 must be a lowercase SHA-256 digest")
    if value.get("profile") != PROFILE:
        raise SceneInputError("unsupported AGI scene profile")
    return {"sha256": digest,
            "size": _uint(value.get("size"), "source.size", 65536, 1),
            "logic_id": _uint(value.get("logic_id"), "source.logic_id", 0),
            "profile": PROFILE}


def _position(value, name):
    value = _object(value, name)
    return {key: _uint(value.get(key), f"{name}.{key}", 255)
            for key in _COORDINATES}


def _snapshot(value):
    value = _object(value, "state")
    if value.get("schema") != "fdisbull-agi-native-state-1":
        raise SceneInputError("unsupported native state schema")
    source = _source(value.get("source"))
    guest = _object(value.get("guest"), "guest")
    if not isinstance(guest.get("status"), str) or guest["status"] not in _STATUSES:
        raise SceneInputError("scene state requires a stopped guest")
    actors = guest.get("actors")
    if not isinstance(actors, list) or len(actors) != 16:
        raise SceneInputError("expected 16 ordered actors")
    normalized = []
    for index, actor in enumerate(actors):
        actor = _object(actor, "actor")
        if _uint(actor.get("id"), "actor.id", 15) != index:
            raise SceneInputError("actors must be ordered by unique id")
        normalized.append({"id": index, **_position(actor, "actor")})
    fault = guest.get("fault")
    if guest["status"] == "fault":
        fault = _object(fault, "fault")
        _uint(fault.get("code"), "fault.code", 7, 1)
        _uint(fault.get("pc"), "fault.pc", 65536)
        _uint(fault.get("opcode"), "fault.opcode", 255)
        if not isinstance(fault.get("name"), str) or not fault["name"]:
            raise SceneInputError("fault must have a name")
    elif fault is not None:
        raise SceneInputError("a non-fault stop cannot carry a fault")
    obs = _object(value.get("observation"), "observation")
    observation = {
        "mask": _uint(obs.get("mask"), "mask", 3),
        "capacity": _uint(obs.get("capacity"), "capacity", 65536),
        "count": _uint(obs.get("count"), "count", 65536),
        **{key: _uint(obs.get(key), key) for key in
           ("eligible", "dropped", "control_generation", "epoch")},
        "per_channel": {},
    }
    channels = _object(obs.get("per_channel"), "per_channel")
    for name in ("disasm", "scene"):
        raw = _object(channels.get(name), name)
        channel = {key: _uint(raw.get(key), f"{name}.{key}")
                   for key in ("eligible", "stored", "dropped")}
        if channel["eligible"] != channel["stored"] + channel["dropped"]:
            raise SceneInputError("channel accounting is inconsistent")
        observation["per_channel"][name] = channel
    for total, channel_key in (("count", "stored"), ("eligible", "eligible"),
                               ("dropped", "dropped")):
        if observation[total] != sum(c[channel_key] for c in observation["per_channel"].values()):
            raise SceneInputError("observation accounting is inconsistent")
    if observation["count"] > observation["capacity"]:
        raise SceneInputError("retained records exceed capacity")
    run = _object(value.get("run"), "run")
    return {"source": source, "actors": normalized,
            "guest": {"pc": _uint(guest.get("pc"), "guest.pc", 65536),
                      "status": guest["status"], "fault": deepcopy(fault)},
            "retired": _uint(guest.get("retired"), "guest.retired"),
            "invocation": _uint(run.get("invocation"), "run.invocation"),
            "observation": observation}


def _checkpoint(state):
    obs = state["observation"]
    return {"epoch": obs["epoch"], "control_generation": obs["control_generation"],
            "retired": state["retired"], "eligible": obs["eligible"],
            "invocation": state["invocation"]}


def _records(envelope, state):
    envelope = _object(envelope, "events")
    if envelope.get("schema") != "fdisbull-agi-native-events-1":
        raise SceneInputError("unsupported native events schema")
    if _source(envelope.get("source")) != state["source"]:
        raise SceneInputError("event source differs from stopped state")
    obs = state["observation"]
    if _uint(envelope.get("epoch"), "events.epoch") != obs["epoch"]:
        raise SceneInputError("events and state describe different epochs")
    events = envelope.get("events")
    if not isinstance(events, list) or len(events) != obs["count"]:
        raise SceneInputError("retained event count differs from state")
    counts = {"retire": 0, "position": 0}
    previous_seq = previous_retired = previous_generation = 0
    result = []
    fingerprints = {}
    for raw in events:
        raw = _object(raw, "event")
        seq = _uint(raw.get("seq"), "event.seq", obs["eligible"], 1)
        retired = _uint(raw.get("retired"), "event.retired", state["retired"], 1)
        generation = _uint(raw.get("control_generation"), "event.control_generation",
                           obs["control_generation"])
        if seq <= previous_seq or retired < previous_retired or generation < previous_generation:
            raise SceneInputError("event order regressed or duplicated")
        previous_seq, previous_retired, previous_generation = seq, retired, generation
        kind = raw.get("kind")
        if not isinstance(kind, str) or kind not in counts:
            raise SceneInputError("unsupported event kind")
        counts[kind] += 1
        pc = _uint(raw.get("pc"), "event.pc", state["source"]["size"] - 1)
        opcode = _uint(raw.get("opcode"), "event.opcode", 255)
        code = raw.get("bytes")
        if not isinstance(code, list) or not 1 <= len(code) <= 255:
            raise SceneInputError("invalid instruction bytes")
        for byte in code:
            _uint(byte, "instruction byte", 255)
        if code[0] != opcode or pc + len(code) > state["source"]["size"]:
            raise SceneInputError("instruction bytes disagree with source extent/opcode")
        _uint(raw.get("next_pc"), "event.next_pc", state["source"]["size"])
        if kind == "position":
            actor = _uint(raw.get("actor"), "event.actor", 15)
            before = _position(raw.get("before"), "before")
            after = _position(raw.get("after"), "after")
            if opcode not in (37, 38) or len(code) != 4 or code[1] != actor \
                    or raw["next_pc"] != pc + 4 or before == after:
                raise SceneInputError("invalid position-change witness")
            if after["x"] != after["prev_x"] or after["y"] != after["prev_y"]:
                raise SceneInputError("position witness violates the selected profile")
            if opcode == 37 and (after["x"], after["y"]) != (code[2], code[3]):
                raise SceneInputError("position witness disagrees with literal operands")
        try:
            encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise SceneInputError("event must contain JSON values") from error
        fingerprints[seq] = hashlib.sha256(encoded).digest()
        result.append(deepcopy(raw))
    if counts["retire"] != obs["per_channel"]["disasm"]["stored"] \
            or counts["position"] != obs["per_channel"]["scene"]["stored"]:
        raise SceneInputError("retained channel counts differ from state")
    return result, fingerprints


def _update(status, reason=None, changes=()):
    return {"status": status, "needs_resync": status == "resync_required",
            "reason": reason, "changes": deepcopy(list(changes))}


class AGISceneConsumer:
    """Project the position profile from one explicitly identified attachment.

    Inputs must describe the same stopped checkpoint. The live adapter must
    enforce that ownership/coherence requirement. Returned dictionaries are
    detached. Failed validation and resync-required results are transactional.
    """

    def __init__(self, state, *, session_id):
        self._session_id = _session(session_id)
        self._state = _snapshot(state)
        self._fingerprints = {}
        self._witnesses = [None] * 16
        self._history_start = _checkpoint(self._state)
        self._gap_count = 0
        self._last_gap = None

    @classmethod
    def from_snapshot(cls, state, *, session_id):
        """Anchor after every eligible event, including records already dropped."""
        return cls(state, session_id=session_id)

    def _compatible(self, state, session_id):
        if _session(session_id) != self._session_id:
            raise SceneInputError("session identity differs; explicitly attach a new consumer")
        if state["source"] != self._state["source"]:
            raise SceneInputError("source identity differs; explicitly attach a new consumer")
        before, after = self._state["observation"], state["observation"]
        if after["epoch"] < before["epoch"] \
                or after["control_generation"] < before["control_generation"] \
                or state["invocation"] < self._state["invocation"]:
            raise SceneInputError("stale checkpoint")
        if after["epoch"] == before["epoch"]:
            if state["retired"] < self._state["retired"]:
                raise SceneInputError("retired count regressed within the same epoch")
            for key in ("count", "eligible", "dropped"):
                if after[key] < before[key]:
                    raise SceneInputError("observation counter regressed")
            for channel in ("disasm", "scene"):
                for key in ("eligible", "stored", "dropped"):
                    if after["per_channel"][channel][key] < before["per_channel"][channel][key]:
                        raise SceneInputError("channel counter regressed")
            if after["mask"] != before["mask"] \
                    and after["control_generation"] == before["control_generation"]:
                raise SceneInputError("observation mask changed without a control generation")

    def view(self):
        """Return current facts as of the recorded stopped checkpoint."""
        state = self._state
        return deepcopy({
            "schema": "fdisbull-agi-scene-view-1",
            "session_id": self._session_id, "source": state["source"],
            "checkpoint": _checkpoint(state), "guest": state["guest"],
            "actors": [{**actor, "witness": self._witnesses[index]}
                       for index, actor in enumerate(state["actors"])],
            "coverage": {
                "history_complete_since_attach": self._gap_count == 0,
                "history_start": self._history_start,
                "gap_count": self._gap_count, "last_gap": self._last_gap,
                "scene_enabled": bool(state["observation"]["mask"] & 2),
            },
        })

    def consume(self, events, state, *, session_id):
        """Validate/apply one complete retained journal at a stopped checkpoint.

        Old records are not replayed. Their fingerprints must agree with every
        previously seen retained record. Only SCENE loss breaks scene history;
        sequence gaps caused exclusively by DISASM drops are allowed.
        """
        candidate = _snapshot(state)
        self._compatible(candidate, session_id)
        records, fingerprints = _records(events, candidate)
        before, after = self._state["observation"], candidate["observation"]
        if after["epoch"] != before["epoch"]:
            return _update("resync_required", "epoch_changed")
        if any(fingerprints.get(seq) != digest for seq, digest in self._fingerprints.items()):
            raise SceneInputError("previously retained event prefix changed")
        work = candidate["retired"] - self._state["retired"]
        if work == 0 and after["eligible"] != before["eligible"]:
            raise SceneInputError("new events appeared without retired work")
        new_records = [event for event in records if event["seq"] > before["eligible"]]
        if any(event["retired"] <= self._state["retired"] for event in new_records):
            raise SceneInputError("new sequence refers to already checkpointed work")
        if any(event["control_generation"] < before["control_generation"]
               for event in new_records):
            raise SceneInputError("new sequence predates the checkpoint control generation")
        if work and after["control_generation"] != before["control_generation"]:
            return _update("resync_required", "control_changed_during_execution")
        if work and not (before["mask"] & 2 and after["mask"] & 2):
            return _update("resync_required", "observation_disabled")
        old_scene, new_scene = before["per_channel"]["scene"], after["per_channel"]["scene"]
        if new_scene["dropped"] > old_scene["dropped"]:
            return _update("resync_required", "scene_records_lost")
        changes = [event for event in new_records if event["kind"] == "position"]
        if len(changes) != new_scene["eligible"] - old_scene["eligible"]:
            return _update("resync_required", "scene_record_gap")
        actors = deepcopy(self._state["actors"])
        witnesses = deepcopy(self._witnesses)
        for event in changes:
            index = event["actor"]
            if _position(actors[index], "actor") != _position(event["before"], "before"):
                return _update("resync_required", "before_state_mismatch")
            actors[index] = {"id": index, **_position(event["after"], "after")}
            witnesses[index] = deepcopy(event)
        if actors != candidate["actors"]:
            return _update("resync_required", "actor_state_mismatch")
        # Commit only after validating the complete batch and final actor state.
        self._state = candidate
        self._fingerprints = fingerprints
        self._witnesses = witnesses
        return _update("applied" if changes else "unchanged", changes=changes)

    def resync(self, state, *, reason, session_id):
        """Adopt current facts promptly, retaining the missing-history boundary."""
        if not isinstance(reason, str) or not reason or len(reason) > 256:
            raise SceneInputError("resync requires a nonempty bounded reason")
        candidate = _snapshot(state)
        self._compatible(candidate, session_id)
        gap = {"reason": reason, "from": _checkpoint(self._state),
               "to": _checkpoint(candidate)}
        self._state = candidate
        self._fingerprints = {}
        self._witnesses = [None] * 16
        self._gap_count += 1
        self._last_gap = gap
        return _update("resynced", reason)


def plan_literal_position_edit(code: bytes, captured_view: dict, *, actor, x, y) -> dict:
    """Plan one same-length literal position edit from a captured scene witness.

    The caller supplies exact raw code and an already captured stopped view.
    This function performs no I/O, captures no observations and mutates neither
    input. It refuses missing or incomplete history and variable-position
    instructions. A harmless stopped control change may leave the witness's
    generation older than the checkpoint or leave SCENE disabled.

    The result describes replacement operands, not an observed new position.
    Editing this static instruction affects every execution of its PC. Later
    assignments, including previously unchanged assignments with no SCENE
    record, may overwrite the requested position. The caller must construct a
    separate candidate from the expected bytes, verify its resulting source
    hash, and observe a fresh bounded execution to assess the actual outcome.
    Consistency checks do not authenticate caller-supplied observations.
    """
    if type(code) is not bytes or not 1 <= len(code) <= 65536:
        raise SceneInputError("code must be immutable bytes of length 1..65536")
    view = _object(captured_view, "captured_view")
    if view.get("schema") != "fdisbull-agi-scene-view-1":
        raise SceneInputError("unsupported scene view schema")
    session_id = _session(view.get("session_id"))
    source = _source(view.get("source"))
    if source["size"] != len(code) or source["sha256"] != hashlib.sha256(code).hexdigest():
        raise SceneInputError("raw code differs from the captured source identity")
    actor = _uint(actor, "actor", 15)
    x, y = _uint(x, "x", 255), _uint(y, "y", 255)

    def checkpoint(value, name):
        value = _object(value, name)
        return {key: _uint(value.get(key), f"{name}.{key}") for key in
                ("epoch", "control_generation", "retired", "eligible", "invocation")}

    current = checkpoint(view.get("checkpoint"), "checkpoint")
    coverage = _object(view.get("coverage"), "coverage")
    if coverage.get("history_complete_since_attach") is not True \
            or _uint(coverage.get("gap_count"), "coverage.gap_count") != 0 \
            or "last_gap" not in coverage or coverage["last_gap"] is not None:
        raise SceneInputError("literal position editing requires complete history without gaps")
    if type(coverage.get("scene_enabled")) is not bool:
        raise SceneInputError("coverage.scene_enabled must be a boolean")
    start = checkpoint(coverage.get("history_start"), "coverage.history_start")
    if start["epoch"] != current["epoch"] or any(
            start[key] > current[key]
            for key in ("control_generation", "retired", "eligible", "invocation")):
        raise SceneInputError("captured history and checkpoint do not form a continuous interval")

    guest = _object(view.get("guest"), "guest")
    if not isinstance(guest.get("status"), str) or guest["status"] not in _STATUSES:
        raise SceneInputError("scene edit planning requires a stopped guest")
    _uint(guest.get("pc"), "guest.pc", source["size"])
    fault = guest.get("fault")
    if guest["status"] == "fault":
        fault = _object(fault, "fault")
        _uint(fault.get("code"), "fault.code", 7, 1)
        _uint(fault.get("pc"), "fault.pc", source["size"])
        _uint(fault.get("opcode"), "fault.opcode", 255)
        if not isinstance(fault.get("name"), str) or not fault["name"]:
            raise SceneInputError("fault must have a name")
    elif fault is not None:
        raise SceneInputError("a non-fault stop cannot carry a fault")

    actors = view.get("actors")
    if not isinstance(actors, list) or len(actors) != 16:
        raise SceneInputError("expected 16 ordered actors")
    for index, item in enumerate(actors):
        item = _object(item, "actor")
        if _uint(item.get("id"), "actor.id", 15) != index:
            raise SceneInputError("actors must be ordered by unique id")
        _position(item, "actor")
    selected = actors[actor]
    position = _position(selected, "selected actor")
    witness = selected.get("witness")
    if witness is None:
        raise SceneInputError("selected actor has no captured position witness")
    witness = _object(witness, "witness")
    if witness.get("kind") != "position":
        raise SceneInputError("expected a position-change witness")
    opcode = _uint(witness.get("opcode"), "witness.opcode", 255)
    if opcode == 38:
        raise SceneInputError("position.v cannot be edited as literal coordinates")
    if opcode != 37:
        raise SceneInputError("literal position editing requires opcode 37")
    if _uint(witness.get("actor"), "witness.actor", 15) != actor:
        raise SceneInputError("position witness identifies a different actor")
    _uint(witness.get("seq"), "witness.seq", current["eligible"], start["eligible"] + 1)
    _uint(witness.get("retired"), "witness.retired", current["retired"], start["retired"] + 1)
    # New work after a stopped attachment must enter a new native invocation.
    if current["invocation"] <= start["invocation"]:
        raise SceneInputError("position witness requires a post-attachment invocation")
    if guest["status"] == "ready":
        raise SceneInputError("a ready guest cannot carry a post-attachment position witness")
    _uint(witness.get("control_generation"), "witness.control_generation",
          current["control_generation"], start["control_generation"])
    pc = _uint(witness.get("pc"), "witness.pc", source["size"] - 4)
    if _uint(witness.get("next_pc"), "witness.next_pc", source["size"]) != pc + 4:
        raise SceneInputError("literal position witness has an inconsistent next PC")
    raw = witness.get("bytes")
    if not isinstance(raw, list) or len(raw) != 4:
        raise SceneInputError("literal position witness requires four instruction bytes")
    expected = [_uint(value, "instruction byte", 255) for value in raw]
    if expected[:2] != [37, actor] or code[pc:pc + 4] != bytes(expected):
        raise SceneInputError("position witness bytes differ from the source instruction")
    before = _position(witness.get("before"), "witness.before")
    after = _position(witness.get("after"), "witness.after")
    if before == after:
        raise SceneInputError("position witness does not describe a change")
    if any(state["x"] != state["prev_x"] or state["y"] != state["prev_y"]
           for state in (before, after)):
        raise SceneInputError("position witness violates the selected profile")
    if (after["x"], after["y"]) != (expected[2], expected[3]) or after != position:
        raise SceneInputError("position witness differs from literal operands or current actor")
    try:
        json.dumps(witness, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise SceneInputError("position witness must contain JSON values") from error

    replacement = [37, actor, x, y]
    candidate = code[:pc] + bytes(replacement) + code[pc + 4:]
    return {
        "schema": "fdisbull-agi-literal-position-edit-1",
        "session_id": session_id, "checkpoint": current, "source": source,
        "actor": actor, "witness": deepcopy(witness), "offset": pc, "length": 4,
        "expected_bytes": expected, "replacement_bytes": replacement,
        "requested_position": {"x": x, "y": y},
        "candidate_source": {**source, "sha256": hashlib.sha256(candidate).hexdigest()},
        "changed": replacement != expected, "write_performed": False,
        "scope": "static_instruction",
    }
