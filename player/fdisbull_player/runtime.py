"""Small explicitly declared transition runtime; not a UIL or AGI interpreter."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid

MIN_INT = -(2 ** 63)
MAX_INT = 2 ** 63 - 1
MAX_ACTION_TICKS = 10000


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate checkpoint field")
        result[key] = value
    return result


def _valid_json(value):
    if value is None or type(value) in (bool, str):
        return True
    if type(value) is int:
        return MIN_INT <= value <= MAX_INT
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_valid_json(item) for item in value)
    if type(value) is dict:
        return all(isinstance(key, str) and _valid_json(item) for key, item in value.items())
    return False


class LocalRuntime:
    def __init__(self, package, save_dir=None):
        if not isinstance(package, dict) or package.get("format") != "fdisbull-text-slice-1":
            raise ValueError("Unsupported package format")
        self.package = copy.deepcopy(package)
        self.package_hash = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.save_dir = Path(save_dir) if save_dir is not None else None
        self.epoch = ""
        self.state = copy.deepcopy(package.get("state", {}))
        if not isinstance(self.state, dict) or not all(isinstance(k, str) for k in self.state):
            raise ValueError("Invalid state")
        if any(type(v) is int and not MIN_INT <= v <= MAX_INT for v in self.state.values()):
            raise ValueError("Integer state out of range")
        if "contexts" in package:
            self.contexts = copy.deepcopy(package["contexts"])
            self.context_id = package.get("initial_context")
        else:
            context = copy.deepcopy(package.get("context"))
            if not isinstance(context, dict):
                raise ValueError("Invalid context")
            self.context_id = context.get("id")
            self.contexts = {self.context_id: {"context": context, "objects": package.get("objects", []),
                                                "partial": package.get("partial", False)}}
        if (not isinstance(self.contexts, dict) or not isinstance(self.context_id, str)
                or self.context_id not in self.contexts
                or not all(isinstance(k, str) and isinstance(v, dict)
                           and isinstance(v.get("context"), dict) and v["context"].get("id") == k
                           and isinstance(v.get("objects", []), list)
                           and isinstance(v.get("partial", False), bool)
                           for k, v in self.contexts.items())):
            raise ValueError("Invalid contexts")
        if not all(isinstance(package.get(k, []), list) for k in ("inventory", "actions", "scheduled")):
            raise ValueError("Invalid package lists")
        self.inventory = copy.deepcopy(package.get("inventory", []))
        entities = self.inventory + [o for c in self.contexts.values() for o in c.get("objects", [])]
        if (not all(isinstance(o, dict) and isinstance(o.get("id"), str) and o["id"] for o in entities)
                or len({o["id"] for o in entities}) != len(entities)):
            raise ValueError("Object identities must be unique")
        self.entity_ids = frozenset(o["id"] for o in entities)
        self.entity_catalog = {o["id"]: copy.deepcopy(o) for o in entities}
        self.tick = 0
        self.revision = 0
        self.events = []

    def _checkpoint_path(self, name):
        if self.save_dir is None or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError("Checkpoint storage or name unavailable")
        return self.save_dir / (name + ".json")

    def save(self, slot="live"):
        try:
            path = self._checkpoint_path(slot)
            payload = {"format": "fdisbull-player-checkpoint-1", "package_hash": self.package_hash,
                       "state": self.state, "context": self.context_id, "tick": self.tick,
                       "events": self.events, "inventory": [o["id"] for o in self.inventory],
                       "positions": {k: [o["id"] for o in v.get("objects", [])]
                                     for k, v in self.contexts.items()}}
            data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Checkpoint too large")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp, path)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            return {"status": "saved", "complete": True, "checkpoint": slot, "slot": slot}
        except (OSError, ValueError, TypeError, OverflowError):
            return {"status": "incomplete", "complete": False, "checkpoint": None, "slot": slot}

    def load(self, checkpoint="live"):
        def failure(status):
            return {"status": status, "complete": status == "missing", "checkpoint": checkpoint}
        try:
            path = self._checkpoint_path(checkpoint)
            try:
                with path.open("rb") as stream:
                    data = stream.read(8 * 1024 * 1024 + 1)
            except FileNotFoundError:
                return failure("missing")
            if len(data) > 8 * 1024 * 1024:
                return failure("incomplete")
            saved = json.loads(data, object_pairs_hook=_unique_object)
            if not isinstance(saved, dict) or set(saved) != {"format", "package_hash", "state", "context", "tick", "events", "inventory", "positions"}:
                return failure("incomplete")
            state, positions, inventory, events = saved["state"], saved["positions"], saved["inventory"], saved["events"]
            if (saved["format"] != "fdisbull-player-checkpoint-1" or saved["package_hash"] != self.package_hash
                    or not isinstance(state, dict) or not _valid_json(state) or set(state) != set(self.state)
                    or any(type(state[k]) is not type(self.state[k]) or (type(state[k]) is int and not MIN_INT <= state[k] <= MAX_INT) for k in state)
                    or not isinstance(saved["context"], str) or saved["context"] not in self.contexts
                    or type(saved["tick"]) is not int or not 0 <= saved["tick"] <= MAX_INT
                    or not isinstance(events, list) or not all(isinstance(e, dict) and set(e) == {"tick", "name"} and type(e["tick"]) is int and 0 <= e["tick"] <= saved["tick"] and isinstance(e["name"], str) for e in events)
                    or any(events[i]["tick"] > events[i+1]["tick"] for i in range(len(events)-1))
                    or not isinstance(positions, dict) or set(positions) != set(self.contexts)
                    or not isinstance(inventory, list) or not all(isinstance(v, list) for v in positions.values())):
                return failure("incomplete")
            ids = inventory + [item for room in positions.values() for item in room]
            if not all(isinstance(i, str) for i in ids) or len(ids) != len(self.entity_ids) or set(ids) != self.entity_ids:
                return failure("incomplete")
            self.state = copy.deepcopy(state)
            self.context_id = saved["context"]
            self.tick = saved["tick"]
            self.events = copy.deepcopy(events)
            self.inventory = [copy.deepcopy(self.entity_catalog[i]) for i in inventory]
            for key, ids_in_room in positions.items():
                self.contexts[key]["objects"] = [copy.deepcopy(self.entity_catalog[i]) for i in ids_in_room]
            self.epoch = uuid.uuid4().hex + ":"
            self.revision = 0
            return {"status": "restored", "complete": True, "checkpoint": checkpoint}
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            return failure("incomplete")

    def observe(self):
        profile = self.contexts[self.context_id]
        c = copy.deepcopy(profile["context"])
        c["token"] = self.epoch + str(self.revision)
        return {"complete": True, "context": c,
                "objects": copy.deepcopy(profile.get("objects", [])),
                "inventory": copy.deepcopy(self.inventory),
                "coverage": {"partial": profile.get("partial", False)}}

    def _validate_effects(self, effects):
        if not isinstance(effects, list):
            return False
        for effect in effects:
            if not isinstance(effect, dict):
                return False
            op = effect.get("op")
            fields = {"set": {"op", "key", "value"}, "add": {"op", "key", "value"},
                      "event": {"op", "name"}, "context": {"op", "id"}, "carry": {"op", "id"},
                      "drop": {"op", "id"}, "stop": {"op"}}
            if not isinstance(op, str) or op not in fields or set(effect) != fields[op]:
                return False
            if op == "set":
                if not isinstance(effect.get("key"), str) or effect["key"] not in self.state or "value" not in effect:
                    return False
                if (type(effect["value"]) is not type(self.state[effect["key"]])
                        or (type(effect["value"]) is int and not MIN_INT <= effect["value"] <= MAX_INT)):
                    return False
            elif op == "add":
                if (not isinstance(effect.get("key"), str) or effect["key"] not in self.state
                        or type(self.state[effect["key"]]) is not int
                        or type(effect.get("value")) is not int
                        or not MIN_INT <= effect["value"] <= MAX_INT):
                    return False
            elif op == "context":
                if not isinstance(effect.get("id"), str) or effect["id"] not in self.contexts:
                    return False
            elif op in ("carry", "drop"):
                if not isinstance(effect.get("id"), str) or effect["id"] not in self.entity_ids:
                    return False
            elif op == "event":
                if not isinstance(effect.get("name"), str):
                    return False
            elif op != "stop":
                return False
        return True

    def _valid_guard(self, guard):
        if not isinstance(guard, dict):
            return False
        if set(guard) == {"carrying"}:
            return isinstance(guard["carrying"], str) and guard["carrying"] in self.entity_ids
        return (set(guard) == {"key", "equals"} and isinstance(guard.get("key"), str)
                and guard["key"] in self.state
                and type(guard["equals"]) is type(self.state[guard["key"]]))

    def _guard_holds(self, guard):
        if "carrying" in guard:
            return any(o["id"] == guard["carrying"] for o in self.inventory)
        return self.state[guard["key"]] == guard["equals"]

    def _apply(self, effects):
        for effect in effects:
            op = effect["op"]
            if op == "set":
                self.state[effect["key"]] = effect["value"]
            elif op == "add":
                value = self.state[effect["key"]] + effect["value"]
                if not MIN_INT <= value <= MAX_INT:
                    raise ValueError("Integer overflow")
                self.state[effect["key"]] = value
            elif op == "context":
                self.context_id = effect["id"]
            elif op in ("carry", "drop"):
                room = self.contexts[self.context_id].setdefault("objects", [])
                source, destination = (room, self.inventory) if op == "carry" else (self.inventory, room)
                matches = [obj for obj in source if obj["id"] == effect["id"]]
                if len(matches) != 1:
                    raise ValueError("Object is not in the required location")
                source.remove(matches[0])
                destination.append(matches[0])
            elif op == "event":
                self.events.append({"tick": self.tick, "name": effect["name"]})
            elif op == "stop":
                return False
        return True

    def act(self, request):
        def outcome(status, message, complete=True):
            return {"status": status, "complete": complete, "message": message, "observation": self.observe()}
        if request.get("context_token") != self.epoch + str(self.revision):
            return outcome("rejected", "Context changed.")
        visible = self.observe()["objects"] + self.observe()["inventory"]
        target = request.get("target")
        item = request.get("item")
        if (not isinstance(target, str) or not any(isinstance(o, dict) and o.get("id") == target
                and isinstance(o.get("verbs"), list) and request.get("verb") in o["verbs"] for o in visible)
                or (item is not None and not any(isinstance(o, dict) and o.get("id") == item for o in visible))):
            return outcome("incomplete", "Action is outside the declared slice.", False)
        matches = [a for a in self.package.get("actions", []) if isinstance(a, dict)
                   and a.get("context", self.context_id) == self.context_id
                   and all(a.get(k) == request.get(k) for k in ("verb", "target", "item"))]
        if len(matches) != 1:
            return outcome("incomplete", "Action is outside the declared slice.", False)
        action = matches[0]
        guards = action.get("guards", [])
        steps = action.get("steps", [])
        scheduled = self.package.get("scheduled", [])
        if (not set(action) <= {"verb", "target", "item", "context", "guards", "steps", "status", "message", "rejected_message"}
                or not isinstance(action.get("rejected_message", ""), str)
                or action.get("status", "success") not in ("success", "accepted", "rejected", "incomplete")
                or not isinstance(action.get("message", ""), str)
                or not isinstance(guards, list) or not isinstance(steps, list)
                or not all(self._valid_guard(g) for g in guards)
                or not all(isinstance(s, dict) and set(s) <= {"ticks", "effects"} and type(s.get("ticks", 0)) is int and s.get("ticks", 0) >= 0
                           and self._validate_effects(s.get("effects", [])) for s in steps)
                or sum(s.get("ticks", 0) for s in steps) > MAX_ACTION_TICKS
                or not all(isinstance(e, dict) and set(e) == {"tick", "effects"} and type(e.get("tick")) is int and e["tick"] >= 0
                           and self._validate_effects(e.get("effects", [])) for e in scheduled)):
            return outcome("incomplete", "A required definition is unknown.", False)
        if not all(self._guard_holds(g) for g in guards):
            return outcome("rejected", str(action.get("rejected_message", "Action rejected.")))
        # Run a shadow copy first so arithmetic failures cannot commit earlier effects.
        shadow = copy.deepcopy(self)
        try:
            shadow._run_steps(steps, scheduled)
        except ValueError:
            return outcome("incomplete", "A required definition is unknown.", False)
        complete = self._run_steps(steps, scheduled)
        if not complete:
            self.revision += 1
            return outcome("incomplete", "Execution stopped after partial effects.", False)
        self.revision += 1
        status = action.get("status", "success")
        if status not in ("success", "accepted", "rejected", "incomplete"):
            return outcome("incomplete", "Outcome definition is unknown.", False)
        return outcome(status, str(action.get("message", "")), status != "incomplete")

    def _run_steps(self, steps, scheduled):
        for step in steps:
            if not self._apply(step.get("effects", [])):
                return False
            for _ in range(step.get("ticks", 0)):
                self.tick += 1
                for event in scheduled:
                    if event["tick"] == self.tick and not self._apply(event.get("effects", [])):
                        return False
        return True
