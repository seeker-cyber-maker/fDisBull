"""Execute recovered scene rules and direct rule links over explicit residual IR.

The scene evaluator never sees a VM stack or a code address. This compatibility
adapter joins its effects to still-unrecovered code. Original selector blocks
are skipped: source tables/property records only serve as admission witnesses,
while the immutable UIL selects named destinations, predicates and handlers.

The old executable and mailbox-intent consumers remain unchanged. A scene
checkpoint binds this entire package, including both semantic documents.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import sys
from pathlib import Path

from . import door_intents, scene_intents
from .intent_runtime import IntentRuntime, _digest
from .scene_bindings import validate_package
from .word16 import (
    MAX_FRAMES, MAX_STACK, Word16Error, Word16Runtime, _atomic_json, _integer,
    _json_load, _protect_cli_inputs,
)


MAX_PACKAGE_BYTES = 80 * 1024 * 1024
MAX_AUDIT_SEGMENTS = 8192


def load_package(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        return validate_package(_json_load(stream, MAX_PACKAGE_BYTES))


def _stats():
    return {"dispatch_sites": {}, "selected_handlers": {}, "exit_outcomes": {},
            "primitive_hits": {}, "residual_handlers": {}, "fallbacks": {},
            "replaced_source_blocks": 0, "dropped_segments": 0}


class SceneRuntime(IntentRuntime):
    """A runnable semantic progression layer with explicit residual phases.

    Step budgets count consumer dispatches. Recovered effects are atomic with
    respect to that budget; their intermediate physical writes still occur in
    source order. An effect fault is never retried through the old algorithm.
    """

    def __init__(self, package, seed=12, random_tape=None, enable_scenes=True,
                 enable_intents=True, enable_interactions=True):
        validate_package(package)
        self.scene_uil = copy.deepcopy(package["uil"])
        self.scene_udl = copy.deepcopy(package["udl"])
        self.dispatch_uil = copy.deepcopy(package["dispatch_uil"])
        self.enable_scenes = bool(enable_scenes)
        self.enable_interactions = bool(enable_interactions)
        self.interaction_uil = copy.deepcopy(package.get("interaction_uil"))
        self.interaction_udl = (copy.deepcopy(package["udl"]["interaction"])
                                if self.interaction_uil is not None else None)
        self.scene_stats = _stats()
        self.last_scene_recovery = {**_stats(), "segments": []}
        self._scene_segments = []
        super().__init__(package["base_intents"], seed=seed,
                         random_tape=random_tape, enable_intents=enable_intents)
        self.package_digest = _digest(package)
        self._scene_objects = {item["object"]: name
                               for name, item in self.scene_udl["scenes"].items()}
        self._directions = {number: name for name, number in
                            self.scene_udl["selection"]["direction_properties"].items()}
        self._scene_witnesses = self._compile_witnesses(self.scene_udl)
        self._dispatch_udl = self.scene_udl["dispatch"]
        self._dispatch_witnesses = self._compile_witnesses(self._dispatch_udl)
        self._dispatch_sites = {item["start"]: item for item in self._dispatch_udl["sites"]}
        self._action_numbers = {item["number"]: item for item in self._dispatch_udl["actions"]}
        self._actions = {item["id"]: item for item in self.dispatch_uil["actions"]}
        self._callback_bindings = {(item["object"], item["property"]): item
                                   for item in self._dispatch_udl["properties"]}
        self._interaction_witnesses = (self._compile_witnesses(self.interaction_udl)
                                       if self.interaction_udl is not None else {})

    @staticmethod
    def _compile_witnesses(document):
        return {name: (item["start"], item["end"], bytes.fromhex(item["bytes"]))
                for name, item in document["witnesses"].items()}

    def _guard(self, names, *, dispatch=False):
        witnesses = self._dispatch_witnesses if dispatch else self._scene_witnesses
        for name in names:
            start, end, expected = witnesses[name]
            if self.memory[start:end] != expected:
                return "source_dependency_changed:" + name
        return None

    def _fallback(self, reason):
        self._increment(self.scene_stats["fallbacks"], reason)
        return False

    def _audit(self, record):
        if len(self._scene_segments) < MAX_AUDIT_SEGMENTS:
            self._scene_segments.append(record)
        else:
            self.scene_stats["dropped_segments"] += 1

    def _committed(self, record, operation):
        """Retain partial effects and fault evidence; never silently fall back."""
        record.update(status="committing", completed_effects=[], completed_realizations=[])
        try:
            operation(record)
        except (Word16Error, IndexError, KeyError, TypeError, OverflowError) as exc:
            record.update(status="commit_fault", interrupted_effect_status="unknown",
                          error=str(exc))
            self._audit(record)
            raise
        record["status"] = "completed"
        self._audit(record)
        return True

    def scene_state(self):
        """Project live conditions; initial values are never reused as facts."""
        selection = self.scene_udl["selection"]
        return {
            "current_scene": self._scene_objects.get(self._read_var(selection["current_scene_global"])),
            "facts": {name: self._read(item["address"], 16) != 0
                      for name, item in self.scene_udl["facts"].items()},
            "doors": {name: bool(self._read(item["address"]) & item["mask"])
                      for name, item in self.scene_udl["doors"].items()},
        }

    def _peek_operand(self, operand, stack):
        """Plan consumption of source arguments without changing live state.

        Only arguments needed by an unrecovered body retain source transport.
        The recovered routine target itself is never put onto this stack.
        """
        if "constant" in operand:
            return operand["constant"]
        if "parent" in operand:
            return self._link(self._peek_operand(operand["parent"], stack), 4)
        index = operand["variable"]
        if index == 0:
            if len(stack) <= self.frames[-1]["base"]:
                raise Word16Error("Source argument stack underflow")
            return stack.pop()
        return self._read_var(index)

    def _call_preflight(self, header, args, store, resume, stack_depth=None):
        if resume not in self.blocks:
            raise Word16Error("Resolved call has no residual continuation")
        if 1 <= store <= 15 and store > len(self.frames[-1]["locals"]):
            raise Word16Error("Resolved call result has no caller local")
        if store == 0 and (len(self.stack) if stack_depth is None else stack_depth) >= MAX_STACK:
            raise Word16Error("Resolved call result exceeds the stack budget")
        for value in args:
            _integer(value, "residual argument", 0, 65535)
        if not header:
            return
        if header not in self.functions:
            raise Word16Error("Resolved residual routine is absent from retained IR")
        guard = self._function_guards[header]
        if self.memory[header:header + len(guard)] != guard:
            raise Word16Error("Resolved residual routine header changed")
        if len(self.frames) >= MAX_FRAMES:
            raise Word16Error("Call frame budget exceeded")

    def _call(self, header, args, store, resume):
        # This literal call only bridges an explicitly residual body. It does
        # not execute the original load/property/push/pop/packed-address path.
        return Word16Runtime._nodes(self, [{"op": "call", "target": header,
                                            "args": args, "store": store,
                                            "resume": resume}], {})

    def _dispatch(self, site):
        if site["frame_local_count"] is not None and len(self.frames[-1]["locals"]) != site["frame_local_count"]:
            return self._fallback("dispatch_frame_not_qualified:" + site["id"])
        reason = self._guard([site["witness"]], dispatch=True)
        if reason:
            return self._fallback(reason)
        stack = list(self.stack)
        selector = site["selector"]
        if selector["kind"] == "table":
            table = self._dispatch_udl["tables"][selector["table"]]
            reason = self._guard([table["witness"], table["pointer_witness"]], dispatch=True)
            if reason:
                return self._fallback(reason)
            number = self._peek_operand(selector["index"], stack)
            binding = self._action_numbers.get(number)
            if binding is None:
                return self._fallback("action_outside_recovered_table")
            action = self._actions[binding["id"]]
            handler = action["handler" if selector["table"] == "actions" else "before_handler"]
        else:
            number = self._peek_operand(selector["object"], stack)
            binding = self._callback_bindings.get((number, selector["property"]))
            if binding is None:
                return self._fallback("object_outside_recovered_callbacks")
            obj = self._dispatch_udl["objects"][binding["object_id"]]
            reason = self._guard(obj["layout_witnesses"], dispatch=True)
            if reason:
                return self._fallback(reason)
            handler = binding["handler"]
            reason = self._guard([binding["witness"]], dispatch=True)
            if reason:
                # Some callbacks are genuine mutable rule state. Their known
                # alternatives were recovered from source-defined setters and
                # tables, not guessed from a trace. The live word selects an
                # explicit rule identity; it is never used as a code address.
                packed = self._read(binding["cell"], binding["size"] * 8)
                variant = None
                for candidate in self._dispatch_udl.get("callback_variants", []):
                    selected = candidate["target"]
                    target_object = (selected["object"] if "object" in selected
                                     else self._read_var(selected["variable"]))
                    if (target_object == number and candidate["property"] == selector["property"]
                            and candidate["packed"] == packed
                            and self._guard(candidate["source_witnesses"], dispatch=True) is None):
                        variant = candidate
                        break
                if variant is None:
                    return self._fallback(reason)
                handler = variant["handler"]
        args = [self._peek_operand(value, stack) for value in site["arguments"]]
        target = self._dispatch_udl["handlers"][handler] if handler is not None else None
        if target:
            reason = self._guard([target["witness"]], dispatch=True)
            if reason:
                return self._fallback(reason)
        header = target["routine_header"] if target else 0
        self._call_preflight(header, args, site["store"], site["return_pc"], len(stack))
        record = {"mode": "resolved_rule_link", "site": site["id"], "handler": handler,
                  "body": "explicit_residual_ir_with_separately_qualified_intents",
                  "replaced_source_blocks": len(site["source_pcs"])}

        def commit(event):
            self.stack[:] = stack
            self._call(header, args, site["store"], site["return_pc"])
            event["completed_effects"].append({"type": "rule_selected", "handler": handler})
            self._increment(self.scene_stats["dispatch_sites"], site["id"])
            self._increment(self.scene_stats["selected_handlers"], handler or "null_handler")
            self.scene_stats["replaced_source_blocks"] += len(site["source_pcs"])
        return self._committed(record, commit)

    def _plan_guards(self, plan):
        names = list(self.scene_udl["runtime_guards"])
        if plan["exit_id"] is not None:
            names += self.scene_udl["exits"][plan["exit_id"]]["guard_witnesses"]
        else:
            names += self.scene_udl["scenes"][plan["origin"]]["structure_guards"]
        for effect in plan["effects"]:
            if effect["type"] == "narrate":
                if "resource" in effect:
                    names += self.scene_udl["resources"][effect["resource"]]["dependencies"]
                else:
                    door = self.scene_udl["doors"][effect["entity"]]
                    names += door["structure_guards"] + door["name_dependencies"]
            elif effect["type"] == "residual_ir":
                names += self.scene_udl["handlers"][effect["binding"]]["guard_witnesses"]
        return self._guard(names)

    def _select_exit(self):
        binding = self.scene_udl["selection"]
        if len(self.frames) < 2 or self.frames[-1]["locals"] != binding["locals"]:
            return self._fallback("walk_frame_not_qualified")
        direction = self._directions.get(self._read_var(binding["direction_global"]))
        state = self.scene_state()
        if direction is None or state["current_scene"] is None:
            return self._fallback("scene_or_direction_not_recovered")
        plan = scene_intents.evaluate_exit(self.scene_uil, state, direction)
        if plan["status"] == "unknown":
            return self._fallback(plan["reason"])
        if plan["status"] == "refused" and self.host["memory_streams"]:
            # Printing into source memory could change the next packed text
            # dependency during this same plan. The cached semantic resources
            # are admitted only when output cannot alias those dependencies.
            return self._fallback("scene_refusal_memory_stream_unqualified")
        reason = self._plan_guards(plan)
        if reason:
            return self._fallback(reason)
        operations = binding["source_operations"]
        frame_locals = binding["residual_frame_locals"]
        exit_binding = (self.scene_udl["exits"][plan["exit_id"]]
                        if plan["exit_id"] is not None else None)
        rule = (self.scene_uil["scenes"][plan["origin"]]["exits"][direction]
                if exit_binding is not None else None)
        if plan["status"] == "travel":
            header = binding["residual_arrival"]["header"]
            destination = self.scene_udl["scenes"][plan["destination"]]["object"]
            kind = rule["kind"]
            call_operation = {"direct": "direct_travel", "conditional": "conditional_travel",
                              "door": "door_travel"}[kind]
            resume = self.blocks[operations[call_operation]]["next"]
            self._call_preflight(header, [destination], 0, resume)
        elif plan["status"] == "residual":
            handler = self.scene_udl["handlers"][plan["handler"]]
            if handler["kind"] == "routine":
                resume = self.blocks[operations["routine_call"]]["next"]
                self._call_preflight(handler["header"], [], frame_locals["routine_result"], resume)
        record = {"mode": "game_intent_uil", "binding": "scene.select_exit",
                  "origin": plan["origin"], "direction": direction,
                  "outcome": plan["outcome"], "destination": plan["destination"],
                  "effects": copy.deepcopy(plan["effects"])}

        def commit(event):
            if exit_binding is not None:
                # Residual callbacks can suspend for input before this frame
                # returns (the Loud Room does). Materialize its already-known
                # compatibility values so existing snapshots/saves stay exact.
                # These are UDL constants; no property search or stack-carried
                # target is recomputed, and none appears in scene UIL.
                locals_ = self.frames[-1]["locals"]
                locals_[frame_locals["property_address"] - 1] = exit_binding["address"]
                locals_[frame_locals["property_size"] - 1] = exit_binding["size"]
                if rule["kind"] == "door":
                    locals_[frame_locals["door_object"] - 1] = self.scene_udl["doors"][rule["door"]]["object"]
                if plan["status"] == "refused" and rule["kind"] in ("conditional", "door"):
                    locals_[frame_locals["failure_resource"] - 1] = exit_binding["failure_packed"]
            for effect in plan["effects"]:
                kind = effect["type"]
                if kind == "narrate":
                    self._emit(effect["text"])
                elif kind == "referent_changed":
                    ref = binding["referent"]
                    self._write_var(ref["object_global"], self.scene_udl["doors"][effect["entity"]]["object"])
                    event["completed_realizations"].append({"type": "referent_object_changed", "entity": effect["entity"]})
                    self._write_var(ref["scene_global"], self.scene_udl["scenes"][effect["scene"]]["object"])
                    event["completed_realizations"].append({"type": "referent_scene_changed", "scene": effect["scene"]})
                elif kind == "travel_requested":
                    self._call(header, [destination], 0, resume)
                    self._increment(self.scene_stats["residual_handlers"], "scene_arrival")
                elif kind == "residual_ir":
                    if handler["kind"] == "routine":
                        self._call(handler["header"], [], frame_locals["routine_result"], resume)
                    else:
                        self._goto(handler["entry"])
                    self._increment(self.scene_stats["residual_handlers"], effect["binding"])
                else:
                    raise Word16Error("Unsupported scene effect")
                event["completed_effects"].append(copy.deepcopy(effect))
            if plan["status"] == "refused":
                self._return(binding["refusal_return"])
            self._increment(self.scene_stats["exit_outcomes"], plan["outcome"])
            for primitive in plan["executed_intents"]:
                self._increment(self.scene_stats["primitive_hits"], primitive)
        return self._committed(record, commit)

    def _move_actor(self):
        binding = self.scene_udl["movement"]
        frame = self.frames[-1]
        if (len(self.frames) < 2 or len(frame["locals"]) != len(binding["locals"])
                or frame["locals"][binding["vehicle_local"] - 1] != 0):
            return self._fallback("move_frame_or_vehicle_not_qualified")
        actor = self._read_var(binding["actor_global"])
        origin = self._read_var(binding["current_scene_global"])
        target = frame["locals"][binding["destination_local"] - 1]
        if (actor != binding["qualified_actor"] or origin not in self._scene_objects
                or target not in self._scene_objects or self._link(actor, 4) != origin):
            return self._fallback("move_actor_or_scene_not_qualified")
        reason = self._guard([*self.scene_udl["runtime_guards"], *binding["guard_witnesses"]])
        if reason:
            return self._fallback(reason)
        # Validate the complete tree update before its first write. This only
        # qualifies the source-state projection; the UIL owns the relocation.
        current, seen = self._link(origin, 6), set()
        while current != actor:
            if current == 0 or current in seen:
                raise Word16Error("Moving actor is absent from its scene child list")
            seen.add(current)
            current = self._link(current, 5)
        current, seen = target, set()
        while current:
            if current == actor or current in seen:
                raise Word16Error("Scene relocation would create a source object cycle")
            seen.add(current)
            current = self._link(current, 4)
        state = {"current_scene": self._scene_objects[origin],
                 "actor": {"id": "adventurer", "scene": self._scene_objects[origin]}}
        plan = scene_intents.evaluate_relocation(self.scene_uil, state, self._scene_objects[target])
        if plan["status"] != "moved":
            return self._fallback(plan["reason"])
        record = {"mode": "game_intent_uil", "binding": "scene.move_actor",
                  "effects": copy.deepcopy(plan["effects"]), "replaced_source_blocks": 2}

        def commit(event):
            self._library("tree.insert", [actor, target])
            event["completed_realizations"].append({"type": "actor_containment_changed",
                "actor": "adventurer", "origin": self._scene_objects[origin],
                "destination": self._scene_objects[target]})
            self._write_var(binding["current_scene_global"], target)
            event["completed_realizations"].append({"type": "current_scene_changed",
                                                   "destination": self._scene_objects[target]})
            event["completed_effects"].extend(copy.deepcopy(plan["effects"]))
            self._goto(binding["continuation"])
            self._increment(self.scene_stats["primitive_hits"], "scene.move_actor")
            self.scene_stats["replaced_source_blocks"] += 2
        return self._committed(record, commit)

    def _door_interaction(self):
        """Realize a named operation; no source helper or packed call runs here.

        The old shared response table stays the state owner while residual
        handlers still use it. Its current permutation is projected afresh;
        maintaining a private semantic bag would break that shared behavior.
        """
        binding, document = self.interaction_udl, self.interaction_uil
        action_number = self._read_var(binding["action_global"])
        action = next((name for name, value in binding["actions"].items()
                       if value == action_number), None)
        if action is None:
            return self._fallback("door_action_remains_residual")
        if len(self.frames) < 2 or self.frames[-1]["locals"] != binding["callback"]["locals"]:
            return self._fallback("door_callback_frame_not_qualified")
        if self.host["memory_streams"]:
            return self._fallback("door_memory_output_stream_unqualified")
        for name in binding["runtime_guards"]:
            start, end, expected = self._interaction_witnesses[name]
            if self.memory[start:end] != expected:
                return self._fallback("door_source_dependency_changed:" + name)
        door, history, repeat = (binding[key] for key in ("door", "history", "repeat"))
        is_open = bool(self._read(door["address"]) & door["mask"])
        bag = None
        if is_open == document["actions"][action]["is_open"]:
            # The domain guarantees positive RNG ranges and no Word16 wrap.
            # An unknown pointer/item/count/cursor retains the old IR behavior.
            if (self._read(repeat["pointer_address"], 16) != repeat["table_address"]
                    or self._read(repeat["table_address"], 16) != repeat["count_word"]):
                return self._fallback("door_response_table_changed")
            cursor = self._read(repeat["cursor_address"], 16)
            by_packed = {packed: name for name, packed in repeat["resources"].items()}
            order = [by_packed.get(self._read(repeat["items_address"] + index * 2, 16))
                     for index in range(repeat["count"])]
            if (not 0 <= cursor < repeat["count"] or None in order
                    or len(set(order)) != repeat["count"]):
                return self._fallback("door_response_bag_outside_qualified_domain")
            bag = {"order": order, "cursor": cursor}
        state = {"door_open": is_open,
                 "hint_dismissed": self._read(history["address"], 16) != 0,
                 "response_bag": bag}
        plan = door_intents.evaluate_interaction(document, state, action)
        if plan["status"] != "handled":
            return self._fallback("door_" + plan["reason"])
        frame, caller = self.frames[-1], self.frames[-2]
        store, base = frame["store"], frame["base"]
        if (type(store) is not int or not 0 <= store <= 255
                or type(base) is not int or not caller["base"] <= base <= len(self.stack)
                or type(frame["resume"]) is not int or frame["resume"] not in self.blocks
                or 0 < store < 16 and store > len(caller["locals"])
                or store == 0 and base >= MAX_STACK):
            return self._fallback("door_return_contract_unqualified")
        # Removing a helper must not silently remove the old consumer's
        # resource-budget refusal. Its temporary stack depth is at most one.
        if len(self.frames) + (2 if bag is not None else 1) > MAX_FRAMES or len(self.stack) >= MAX_STACK:
            return self._fallback("door_source_call_budget_unqualified")
        if store >= 16:
            self._bounds(self.layout["globals"] + 2 * (store - 16), 2, True)
        record = {"mode": "game_intent_uil", "binding": document["id"],
                  "action": action, "outcome": plan["outcome"],
                  "effects": copy.deepcopy(plan["effects"])}
        if plan["outcome"] in ("opened", "closed"):
            replaced = 10 if plan["outcome"] == "opened" else 12
        else:
            # Four callback operations, seven helper operations and the bag
            # helper; its reset assignment runs only at a cycle boundary.
            replaced = 11 + len(binding["selection"]["source_pcs"]) - int(
                bag["cursor"] + 1 < repeat["count"])
        record["replaced_source_blocks"] = replaced

        def commit(event):
            for effect in plan["effects"]:
                kind = effect["type"]
                if kind == "hint_dismissed":
                    self._write_var(history["global"], history["value"])
                elif kind == "narrate":
                    self._emit(effect["text"])
                elif kind == "door_state_changed":
                    self._library("attribute.set" if effect["is_open"] else "attribute.clear",
                                  [door["object"], door["attribute"]])
                elif kind == "shuffled_response":
                    remaining = repeat["count"] - bag["cursor"]
                    draw = self._random(remaining)
                    event["completed_realizations"].append({"type": "random_draw", "range": remaining, "value": draw})
                    choice = door_intents.select_response(document, bag, draw)
                    chosen, cursor = choice["chosen_position"], choice["cursor_position"]
                    slots = ((chosen, bag["order"][cursor]), (cursor, choice["resource"]))
                    # Both original assignments are observable, even for a
                    # same-slot choice. They occur before the cursor and text.
                    for position, resource in slots:
                        self._write(repeat["items_address"] + position * 2, 16,
                                    repeat["resources"][resource])
                        event["completed_realizations"].append({"type": "response_slot_changed",
                            "position": position, "resource": resource})
                    self._write(repeat["cursor_address"], 16, choice["next_bag"]["cursor"])
                    event["completed_realizations"].append({"type": "response_cursor_changed",
                                                            "cursor": choice["next_bag"]["cursor"]})
                    self._emit(choice["text"])
                    event["completed_realizations"].append({"type": "narrate", "resource": choice["resource"]})
                else:
                    raise Word16Error("Unsupported door interaction effect")
                event["completed_effects"].append(copy.deepcopy(effect))
            self._return(binding["return_value"])
            self.scene_stats["replaced_source_blocks"] += replaced
            for primitive in plan["executed_intents"]:
                self._increment(self.scene_stats["primitive_hits"], primitive)
        return self._committed(record, commit)

    def _nodes(self, nodes, temps):
        block = self.blocks.get(self.pc)
        if self.enable_scenes and block is not None and nodes is block["nodes"]:
            if (getattr(self, "enable_interactions", False) and self.interaction_udl is not None
                    and self.pc == self.interaction_udl["callback"]["entry"]
                    and self._door_interaction()):
                return True
            site = self._dispatch_sites.get(self.pc)
            if site is not None and self._dispatch(site):
                return True
            if self.pc == self.scene_udl["selection"]["effect_entry"] and self._select_exit():
                return True
            if self.pc == self.scene_udl["movement"]["effect_entry"] and self._move_actor():
                return True
        return super()._nodes(nodes, temps)

    def run(self, max_steps=2_000_000):
        if self.fault is not None:
            raise Word16Error("Execution is faulted; restore a qualified checkpoint")
        before = copy.deepcopy(self.scene_stats)
        self._scene_segments = []
        try:
            result = super().run(max_steps=max_steps)
        finally:
            delta = _stats()
            for key, value in self.scene_stats.items():
                delta[key] = ({name: count - before[key].get(name, 0)
                               for name, count in value.items() if count != before[key].get(name, 0)}
                              if isinstance(value, dict) else value - before[key])
            delta["segments"] = copy.deepcopy(self._scene_segments)
            self.last_scene_recovery = delta
        result["scene_recovery"] = copy.deepcopy(delta)
        return result

    def command(self, text, max_steps=2_000_000):
        if self.fault is None:
            self.last_scene_recovery = {**_stats(), "segments": []}
        return super().command(text, max_steps=max_steps)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run recovered Zork scenes with explicit residual game behavior")
    parser.add_argument("package")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--commands")
    parser.add_argument("--transcript")
    parser.add_argument("--checkpoint")
    parser.add_argument("--resume")
    args = parser.parse_args(argv)
    _protect_cli_inputs(args)
    commands = None
    if args.commands:
        with Path(args.commands).open("rb") as stream:
            commands = _json_load(stream, 1024 * 1024)
        if not isinstance(commands, list):
            parser.error("Commands must be a JSON array")
        for command in commands:
            Word16Runtime._command_codes(command)
    runtime = SceneRuntime(load_package(args.package), seed=args.seed)
    if args.resume:
        runtime.load_checkpoint(args.resume)
    transcript = []

    def execute(command=None):
        try:
            result = runtime.run() if command is None else runtime.command(command)
        except Word16Error as exc:
            # A failure cannot overwrite the most recent completed checkpoint.
            transcript.append({"command": command, "status": "fault", "error": str(exc),
                               "recovery": runtime.last_recovery,
                               "scene_recovery": runtime.last_scene_recovery})
            if args.transcript:
                _atomic_json(args.transcript, transcript)
            print("Execution fault; completed effects remain in the fault receipt and the previous checkpoint is retained: " + str(exc), file=sys.stderr)
            return None
        transcript.append({"command": command, **result})
        if result["text"]:
            print(result["text"], end="", flush=True)
        if args.checkpoint:
            runtime.save_checkpoint(args.checkpoint)
        if args.transcript:
            _atomic_json(args.transcript, transcript)
        return result

    result = execute()
    if commands is not None:
        for command in commands:
            if result is None or result["status"] != "input":
                break
            result = execute(command)
    else:
        while result is not None and result["status"] == "input":
            try:
                command = input("> " if sys.stdin.isatty() else "")
            except EOFError:
                break
            result = execute(command)
    return 1 if result is None else 2 if result["status"] == "budget_exhausted" else 0


if __name__ == "__main__":
    raise SystemExit(main())
