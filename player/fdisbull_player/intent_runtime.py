"""Execute partial game-intent UIL with explicitly retained low-level IR.

The word16 consumer is preserved unchanged. This adapter replaces qualified
source regions with the independent, address-free game-intent evaluator. UDL
definitions project source state, guard the source/ABI, and realize ordered
domain effects. Everything else continues through the retained IR and is counted
as residual execution. Faults retain already executed effects and are reported;
they never silently delegate or retry after mutation.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

from . import game_intents
from .word16 import (
    MAX_PROGRAM_BYTES, Word16Error, Word16Runtime, _atomic_json, _canonical,
    _integer, _json_load, _protect_cli_inputs, validate_program,
)


FORMAT = "fdisbull-zork-intent-package-1"
UDL_FORMAT = "fdisbull-zork-intent-udl-1"
MAX_PACKAGE_BYTES = MAX_PROGRAM_BYTES + 2 * 1024 * 1024


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _source_nodes(ir, pc):
    """Inspect declared IR operands; resolve only local literal aliases.

    This is structural correspondence checking, not an opcode interpreter or
    proof of a whole source routine. Dynamic reads remain symbolic variables.
    """
    block = ir["blocks"].get(str(pc))
    if block is None:
        raise Word16Error("UDL source operation is absent from retained IR")

    def walk(nodes, aliases):
        def resolved(value):
            if isinstance(value, dict) and set(value) == {"tmp"}:
                return aliases.get(value["tmp"], value)
            return value
        for node in nodes:
            item = dict(node)
            for key in ("index", "value"):
                if key in item:
                    item[key] = resolved(item[key])
            if "args" in item:
                item["args"] = [resolved(value) for value in item["args"]]
            if node["op"] == "let":
                aliases[node["name"]] = item["value"]
            elif node["op"] == "read_var":
                aliases[node["dest"]] = {"variable": item["index"]}
            yield item
            for branch in ("then", "else"):
                if branch in node:
                    yield from walk(node[branch], dict(aliases))
    return list(walk(block["nodes"], {}))


def _covered(start, end, intervals):
    for left, right in intervals:
        if left > start:
            break
        if right > start:
            start = right
        if start >= end:
            return True
    return False


def validate_package(package):
    """Bind the separate semantic definition, UDL and preserved IR together.

    Source recovery is the producer's responsibility. This consumer checks the
    declared correspondence and all immutable evidence before allowing execution;
    a package's qualification receipt is not an independently signed proof.
    Authored synthetic definitions can use the same adapter without pretending
    their source is the recovered Zork story.
    """
    if not isinstance(package, dict) or package.get("format") != FORMAT:
        raise Word16Error("Unsupported game-intent package")
    if set(package) != {"format", "low_level_ir", "uil", "udl"}:
        raise Word16Error("Game-intent package has missing or unknown members")
    ir, uil, udl = package["low_level_ir"], package["uil"], package["udl"]
    validate_program(ir)
    game_intents.validate_uil(uil)
    if not isinstance(udl, dict) or udl.get("format") != UDL_FORMAT:
        raise Word16Error("Unsupported UDL definition")
    if udl.get("low_level_ir_sha256") != _digest(ir):
        raise Word16Error("UDL is not bound to this retained low-level IR")
    if udl.get("uil_sha256") != _digest(uil):
        raise Word16Error("UDL is not bound to this game-intent definition")
    if udl.get("source") != ir["source"]:
        raise Word16Error("UDL and retained IR have different source identities")
    image = bytes.fromhex(ir["memory"]["initial"])
    if udl.get("initial_image_sha256") != hashlib.sha256(image).hexdigest():
        raise Word16Error("UDL initial-image identity mismatch")
    witnesses = udl.get("witnesses")
    if not isinstance(witnesses, dict) or not 1 <= len(witnesses) <= 1024:
        raise Word16Error("UDL requires bounded source witnesses")
    total = 0
    for name, witness in witnesses.items():
        if not isinstance(name, str) or not isinstance(witness, dict):
            raise Word16Error("Invalid UDL witness")
        start = _integer(witness.get("start"), "witness start", 0, len(image))
        end = _integer(witness.get("end"), "witness end", start + 1, len(image))
        try:
            data = bytes.fromhex(witness["bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Word16Error("Invalid UDL witness bytes") from exc
        total += len(data)
        if total > 1024 * 1024 or len(data) != end - start:
            raise Word16Error("UDL source witness extent is invalid")
        if image[start:end] != data or hashlib.sha256(data).hexdigest() != witness.get("sha256"):
            raise Word16Error("UDL witness does not match the original image")
    guards = udl.get("runtime_guards")
    if not isinstance(guards, list) or not guards or any(name not in witnesses for name in guards):
        raise Word16Error("Invalid UDL live-source guards")
    objects = udl.get("objects")
    if not isinstance(objects, dict) or not 2 <= len(objects) <= 32:
        raise Word16Error("UDL requires a bounded object correspondence")
    numbers = set()
    for identity, obj in objects.items():
        if not isinstance(identity, str) or not isinstance(obj, dict):
            raise Word16Error("Invalid UDL object correspondence")
        number = _integer(obj.get("number"), "object number", 1, 255)
        if number in numbers:
            raise Word16Error("UDL object identities must be distinct")
        numbers.add(number)
        record = ir["layout"]["objects"] + 62 + (number - 1) * 9
        if obj.get("record") != record or record + 9 > ir["memory"]["writable_end"]:
            raise Word16Error("UDL object-record correspondence mismatch")
        if not isinstance(obj.get("name"), str):
            raise Word16Error("UDL object name is missing")
    fields = udl.get("fields")
    required_fields = {"target.is_container", "target.supports_opening", "target.is_open",
                       "target.opaque", "first_content.description", "discourse.object",
                       "discourse.scene", "current_scene", "turn.count"}
    if not isinstance(fields, dict) or not required_fields <= set(fields):
        raise Word16Error("UDL semantic fields are incomplete")
    if any(not isinstance(field, dict) for field in fields.values()):
        raise Word16Error("Invalid UDL semantic field")
    for name in required_fields:
        field = fields[name]
        if not isinstance(field, dict):
            raise Word16Error("Invalid UDL semantic field")
        kind = field.get("kind")
        if kind == "attribute":
            number = _integer(field.get("number"), "attribute number", 0, 31)
            if field.get("object") not in objects:
                raise Word16Error("UDL attribute names an unknown object")
            record = objects[field["object"]]["record"]
            if field.get("address") != record + number // 8 or field.get("mask") != 128 >> (number % 8):
                raise Word16Error("UDL attribute correspondence mismatch")
        elif kind == "global":
            number = _integer(field.get("number"), "global number", 16, 255)
            address = ir["layout"]["globals"] + 2 * (number - 16)
            if (field.get("address") != address or field.get("width") != 16
                    or address + 2 > ir["memory"]["writable_end"]):
                raise Word16Error("UDL global correspondence mismatch")
        elif kind == "property":
            if field.get("object") not in objects:
                raise Word16Error("UDL property names an unknown object")
            _integer(field.get("number"), "property number", 1, 31)
        else:
            raise Word16Error("Unsupported UDL semantic field representation")
    opening, turn = udl.get("opening"), udl.get("turn")
    if not isinstance(opening, dict) or not isinstance(turn, dict):
        raise Word16Error("UDL entry bindings are missing")
    for binding, key in ((opening, "entry"), (opening, "return_pc"),
                         (turn, "entry"), (turn, "continue")):
        if str(binding.get(key)) not in ir["blocks"]:
            raise Word16Error("UDL continuation is not in the retained IR")
    if str(opening.get("function")) not in ir["functions"]:
        raise Word16Error("UDL opening function is missing")
    if ir["functions"][str(opening["function"])]["entry"] != opening["entry"]:
        raise Word16Error("UDL opening entry contradicts its function")
    for key in ("target", "content"):
        if opening.get(key) not in objects:
            raise Word16Error("UDL opening identity is not declared")
    if opening.get("scene") not in objects:
        raise Word16Error("UDL opening scene identity is missing")
    _integer(opening.get("scene_object"), "opening scene object", 1, 255)
    if objects[opening["scene"]]["number"] != opening["scene_object"]:
        raise Word16Error("UDL scene object correspondence mismatch")
    for key in ("direct_object_global", "action_global"):
        _integer(opening.get(key), key, 16, 255)
    _integer(opening.get("action_value"), "opening action", 0, 65535)
    _integer(opening.get("return_value"), "opening return value", 0, 65535)
    _integer(opening.get("return_store"), "opening return store", 0, 255)
    if opening.get("locals_initial") != ir["functions"][str(opening["function"])]["locals"]:
        raise Word16Error("UDL opening locals disagree with the source function")
    expected_kinds = {
        "target.is_container": {"attribute"}, "target.supports_opening": {"attribute", "property"},
        "target.is_open": {"attribute"}, "target.opaque": {"attribute"},
        "first_content.description": {"property"}, "discourse.object": {"global"},
        "discourse.scene": {"global"}, "current_scene": {"global"}, "turn.count": {"global"},
    }
    for name, kinds in expected_kinds.items():
        field = fields[name]
        if field["kind"] not in kinds:
            raise Word16Error("UDL field kind contradicts its semantic realization: " + name)
        if name.startswith("target.") and field.get("object") != opening["target"]:
            raise Word16Error("UDL target field belongs to another object")
        if name.startswith("first_content.") and field.get("object") != opening["content"]:
            raise Word16Error("UDL content field belongs to another object")
        if name != "target.opaque" and field.get("invert", False):
            raise Word16Error("UDL inversion is unsupported for this field")
        if "invert" in field and type(field["invert"]) is not bool:
            raise Word16Error("UDL field inversion must be Boolean")
    if fields["target.supports_opening"]["kind"] == "property" and fields["target.supports_opening"].get("condition") != "nonzero":
        raise Word16Error("UDL opening-property condition must be nonzero")
    global_roles = ("discourse.object", "discourse.scene", "current_scene", "turn.count")
    if len({fields[name]["number"] for name in global_roles}) != len(global_roles):
        raise Word16Error("UDL global roles must have distinct source fields")
    for name in ("target.is_open", "discourse.object", "discourse.scene", "turn.count"):
        field = fields[name]
        source_nodes = _source_nodes(ir, field.get("source_operation"))
        if field["kind"] == "attribute":
            entities = (objects[field["object"]]["number"], {"variable": opening["direct_object_global"]})
            agrees = any(node["op"] == "library" and node.get("name") == "attribute.set"
                         and len(node["args"]) == 2 and node["args"][0] in entities
                         and node["args"][1] == field["number"] for node in source_nodes)
        else:
            agrees = any(node["op"] == "write_var" and node["index"] == field["number"]
                         for node in source_nodes)
        if not agrees:
            raise Word16Error("UDL field disagrees with its source operation: " + name)
    return_operations = opening.get("return_operations")
    if not isinstance(return_operations, list) or not 1 <= len(return_operations) <= 16:
        raise Word16Error("UDL opening return requires source operations")
    for pc in return_operations:
        values = [node["value"] for node in _source_nodes(ir, pc) if node["op"] == "return"]
        if not values or any(value != opening["return_value"] for value in values):
            raise Word16Error("UDL opening return disagrees with its source operation")
    # Most instruction witnesses are covered by a wider routine guard. Initial
    # property-value evidence is deliberately mutable; code/layout/text is not.
    intervals = sorted((witnesses[name]["start"], witnesses[name]["end"]) for name in guards)
    mutable_values = {field["witness"] for field in fields.values()
                      if field.get("kind") == "property" and "witness" in field}
    for name, witness in witnesses.items():
        if name not in mutable_values and not _covered(witness["start"], witness["end"], intervals):
            raise Word16Error("UDL live guards omit an immutable source witness: " + name)
    for pc in return_operations + [fields[name]["source_operation"] for name in
                                   ("target.is_open", "discourse.object", "discourse.scene", "turn.count")]:
        if not _covered(pc, pc + len(bytes.fromhex(ir["blocks"][str(pc)]["guard"])), intervals):
            raise Word16Error("UDL live guards omit a realized source operation")
    if (turn.get("minimum"), turn.get("maximum"), turn.get("cycle")) != (0, 999, 1000):
        raise Word16Error("Unsupported source-bound player-turn range")
    _integer(turn.get("locals_count"), "turn locals count", 1, 15)
    _integer(turn.get("return_store"), "turn return store", 0, 255)
    if str(turn.get("return_pc")) not in ir["blocks"]:
        raise Word16Error("UDL turn return continuation is missing")
    cursors = turn.get("cursor_equal")
    if (not isinstance(cursors, list) or len(cursors) != 2
            or any(type(index) is not int or not 0 <= index < turn["locals_count"] for index in cursors)):
        raise Word16Error("UDL scheduler cursor correspondence is invalid")
    residuals = udl.get("residuals")
    residual = residuals.get("post_open_source_flag") if isinstance(residuals, dict) else None
    if not isinstance(residual, dict) or residual.get("kind") != "single_block":
        raise Word16Error("The unresolved post-opening effect must retain an IR block")
    if str(residual.get("entry")) not in ir["blocks"]:
        raise Word16Error("Residual source effect is missing from retained IR")
    residual_nodes = ir["blocks"][str(residual["entry"])]["nodes"]
    if (not residual_nodes or any(node["op"] not in ("let", "read_var", "library")
                                  or (node["op"] == "library" and node["name"] != "attribute.set")
                                  or (node["op"] == "read_var"
                                      and (type(node["index"]) is not int or node["index"] < 16))
                                  for node in residual_nodes)):
        raise Word16Error("Residual source flag violates its straight-line effect contract")
    for outcome in uil["interaction"]["outcomes"]:
        for step in outcome["steps"]:
            if "residual_ir" in step and step["residual_ir"] != "post_open_source_flag":
                raise Word16Error("Undeclared executable residual effect")
    if any("residual_ir" in step for step in uil["turn"]["steps"]):
        raise Word16Error("Turn accounting does not authorize another residual effect")
    return package


def load_package(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        return validate_package(_json_load(stream, MAX_PACKAGE_BYTES))


def _empty_stats():
    return {"binding_hits": {}, "primitive_hits": {}, "outcomes": {},
            "low_level_blocks": 0, "residual_bindings": {}, "residual_reasons": {}}


class IntentRuntime(Word16Runtime):
    """A mixed consumer: recovered game intent plus explicit residual IR.

    Semantic operations can fault after partial effects. A step budget counts
    dispatches, not the number of displaced source instructions.
    The original word16 consumer retains its own instruction-level pause behavior.
    """

    def __init__(self, package, seed=12, random_tape=None, enable_intents=True):
        validate_package(package)
        self.uil = copy.deepcopy(package["uil"])
        self.udl = copy.deepcopy(package["udl"])
        self.enable_intents = bool(enable_intents)
        self.recovery_stats = _empty_stats()
        self.last_recovery = {**_empty_stats(), "segments": [], "mode": "low_level_only"}
        self._segments = []
        self._active_intent = False
        self._phase = "unrecovered_initialization"
        self._next_run_kind = None
        super().__init__(package["low_level_ir"], seed=seed, random_tape=random_tape)
        self.low_level_digest = self.package_digest
        # The inherited checkpoint machinery, including nested game-save slots,
        # now binds BOTH representations and the UDL, not merely the backing IR.
        self.package_digest = _digest(package)
        self._object_ids = {item["number"]: identity for identity, item in self.udl["objects"].items()}

    @staticmethod
    def _increment(mapping, key, amount=1):
        mapping[key] = mapping.get(key, 0) + amount

    def _record_low_level_block(self, pc, binding=None):
        """Explicit observation/trap seam; called before original node execution."""
        self.recovery_stats["low_level_blocks"] += 1
        if binding is not None:
            self._increment(self.recovery_stats["residual_bindings"], binding)
        if self._active_intent:
            return
        if (self._segments and self._segments[-1]["mode"] == "low_level_ir"
                and self._segments[-1]["phase"] == self._phase):
            segment = self._segments[-1]
            segment["blocks"] += 1
            segment["last_pc"] = pc
        else:
            self._segments.append({"mode": "low_level_ir", "phase": self._phase,
                                   "blocks": 1, "first_pc": pc, "last_pc": pc})

    def _live_guards(self):
        for identity in self.udl["runtime_guards"]:
            witness = self.udl["witnesses"][identity]
            if self.memory[witness["start"]:witness["end"]] != bytes.fromhex(witness["bytes"]):
                return "live_source_dependency_changed:" + identity
        return None

    def _field_value(self, name):
        field = self.udl["fields"][name]
        if field["kind"] == "global":
            return self._read(field["address"], 16)
        if field["kind"] == "attribute":
            result = bool(self._read(field["address"]) & field["mask"])
            return not result if field.get("invert", False) else result
        if field["kind"] == "property":
            obj = self.udl["objects"][field["object"]]["number"]
            value = self._library("property.get", [obj, field["number"]])
            if field.get("condition") == "nonzero":
                return value != 0
            return value
        raise Word16Error("Unsupported UDL projection")

    def _scene_identity(self, number):
        opening = self.udl["opening"]
        return opening["scene"] if number == opening["scene_object"] else None

    def semantic_state(self):
        """Project only the recovered named fields; unknown names remain None."""
        opening = self.udl["opening"]
        target, content = opening["target"], opening["content"]
        target_number = self.udl["objects"][target]["number"]
        child = self._link(target_number, 6)
        contents = [] if child == 0 else [self._object_ids[child]] if child in self._object_ids else None
        scene_number = self._field_value("current_scene")
        entities = {}
        for identity, obj in self.udl["objects"].items():
            entities[identity] = {
                "name": self._library("tree.name", [obj["number"]]),
                "is_container": None, "supports_opening": None, "is_open": None,
                "opaque": None, "reachable": None, "contents": None,
                "plain_listing": None,
            }
        entities[target].update({
            "is_container": self._field_value("target.is_container"),
            "supports_opening": self._field_value("target.supports_opening"),
            "is_open": self._field_value("target.is_open"),
            "opaque": self._field_value("target.opaque"),
            "reachable": self._link(target_number, 4) == scene_number == opening["scene_object"],
            "contents": contents, "plain_listing": True,
        })
        entities[content]["plain_listing"] = self._field_value("first_content.description") == 0
        return {"entities": entities, "current_scene": self._scene_identity(scene_number),
                "discourse": {"referent": self._object_ids.get(self._field_value("discourse.object")),
                              "scene": self._scene_identity(self._field_value("discourse.scene"))},
                "turn": {"count": self._field_value("turn.count")}}

    def _opening_admission(self):
        changed = self._live_guards()
        if changed:
            return changed
        opening = self.udl["opening"]
        frame = self.frames[-1]
        target = self.udl["objects"][opening["target"]]["number"]
        content = self.udl["objects"][opening["content"]]["number"]
        if self._read_var(opening["direct_object_global"]) != target:
            return "opening_target_not_qualified"
        if self._read_var(opening["action_global"]) != opening["action_value"]:
            return "opening_action_not_qualified"
        if (len(self.frames) < 2 or frame["locals"] != opening["locals_initial"]
                or frame["resume"] != opening["return_pc"] or frame["store"] != opening["return_store"]):
            return "opening_frame_not_qualified"
        if self._field_value("current_scene") != opening["scene_object"]:
            return "opening_scene_not_qualified"
        if self._link(target, 4) != opening["scene_object"]:
            return "opening_target_not_in_scene"
        if self.host["memory_streams"] or self.host["window"] != 0:
            return "opening_output_stream_not_qualified"
        child = self._link(target, 6)
        if child not in (0, content):
            return "opening_contents_not_qualified"
        if child and (self._link(child, 5) != 0 or self._link(child, 4) != target):
            return "opening_content_tree_not_qualified"
        if self._field_value("first_content.description") != 0:
            return "opening_special_description_unrecovered"
        return None

    def _turn_admission(self):
        changed = self._live_guards()
        if changed:
            return changed
        turn = self.udl["turn"]
        value = self._field_value("turn.count")
        if not turn["minimum"] <= value <= turn["maximum"]:
            return "turn_counter_outside_qualified_domain"
        frame = self.frames[-1]
        if (len(self.frames) < 2 or len(frame["locals"]) != turn["locals_count"]
                or frame["resume"] != turn["return_pc"]
                or frame["store"] != turn["return_store"]):
            return "turn_frame_not_qualified"
        left, right = turn["cursor_equal"]
        if frame["locals"][left] != frame["locals"][right]:
            return "turn_scheduler_not_at_end"
        return None

    def _residual_effect(self, identity):
        if identity != "post_open_source_flag":
            raise Word16Error("Undeclared residual invocation")
        binding = self.udl["residuals"][identity]
        pc = binding["entry"]
        block, guard = self.blocks[pc], self._guards[pc]
        if self.memory[pc:pc + len(guard)] != guard:
            raise Word16Error("Residual effect's original bytes changed")
        previous_pc = self.pc
        self.pc = pc
        self._record_low_level_block(pc, binding=identity)
        self.executed_blocks.add(pc)
        transferred = Word16Runtime._nodes(self, block["nodes"], {})
        if transferred or self.pc != pc:
            raise Word16Error("Residual effect violated its straight-line contract")
        self.pc = previous_pc

    def _commit_effects(self, effects):
        for effect in effects:
            kind = effect["type"]
            if kind == "container_opened":
                if effect["entity"] != self.udl["opening"]["target"]:
                    raise Word16Error("Container effect does not match its UDL binding")
                field = self.udl["fields"]["target.is_open"]
                self._write(field["address"], 8, self._read(field["address"]) | field["mask"])
            elif kind == "residual_ir":
                self._residual_effect(effect["binding"])
            elif kind == "narrate":
                self._emit(effect["text"])
            elif kind == "referent_changed":
                opening = self.udl["opening"]
                if effect["entity"] not in self.udl["objects"] or effect["scene"] != opening["scene"]:
                    raise Word16Error("Discourse effect is outside its UDL correspondence")
                obj = self.udl["objects"][effect["entity"]]["number"]
                self._write(self.udl["fields"]["discourse.object"]["address"], 16, obj)
                self._write(self.udl["fields"]["discourse.scene"]["address"], 16, opening["scene_object"])
            elif kind == "turn_counted":
                turn = self.udl["turn"]
                address = self.udl["fields"]["turn.count"]["address"]
                if effect["cycle"] != turn["cycle"] or self._read(address, 16) != effect["before"]:
                    raise Word16Error("Turn effect disagrees with its UDL precondition")
                # UDL realizes the source's observable intermediate write at
                # rollover; the UIL primitive owns the domain result.
                self._write(address, 16, effect["before"] + 1)
                if effect["after"] != effect["before"] + 1:
                    self._write(address, 16, effect["after"])
            else:
                raise Word16Error("Unsupported game-intent effect")

    def _preflight_effects(self, binding, effects):
        """Check every realization before applying any part of an effect plan."""
        opening = self.udl["opening"]
        for effect in effects:
            kind = effect["type"]
            if kind == "container_opened":
                if binding != "mailbox_open" or effect["entity"] != opening["target"]:
                    raise Word16Error("Container effect does not match its UDL binding")
            elif kind == "referent_changed":
                if (binding != "mailbox_open" or effect["entity"] not in self.udl["objects"]
                        or effect["scene"] != opening["scene"]):
                    raise Word16Error("Discourse effect is outside its UDL correspondence")
            elif kind == "narrate":
                if binding != "mailbox_open" or not isinstance(effect["text"], str):
                    raise Word16Error("Narration effect is outside its UDL correspondence")
            elif kind == "turn_counted":
                if (binding != "turn_counter" or effect["cycle"] != self.udl["turn"]["cycle"]
                        or self._field_value("turn.count") != effect["before"]):
                    raise Word16Error("Turn effect disagrees with its UDL precondition")
            elif kind == "residual_ir":
                if binding != "mailbox_open" or effect["binding"] != "post_open_source_flag":
                    raise Word16Error("Undeclared residual invocation")
                pc = self.udl["residuals"][effect["binding"]]["entry"]
                guard = self._guards[pc]
                if self.memory[pc:pc + len(guard)] != guard:
                    raise Word16Error("Residual effect's original bytes changed")
                # Dry-check only the bounded read/attribute operands. This
                # performs no mutation and never invokes the original nodes.
                temps = {}
                for node in self.blocks[pc]["nodes"]:
                    if node["op"] == "let":
                        temps[node["name"]] = self._expr(node["value"], temps)
                    elif node["op"] == "read_var":
                        temps[node["dest"]] = self._read_var(node["index"], node.get("indirect", False))
                    else:
                        args = [self._expr(value, temps) for value in node["args"]]
                        if (len(args) != 2 or args[0] != self.udl["objects"][opening["target"]]["number"]
                                or type(args[1]) is not int or not 0 <= args[1] <= 31):
                            raise Word16Error("Residual flag operands violate their qualified scope")
            else:
                raise Word16Error("Unsupported game-intent effect")
        if binding == "mailbox_open":
            store = opening["return_store"]
            if 1 <= store <= 15 and store > len(self.frames[-2]["locals"]):
                raise Word16Error("Opening return destination is outside the caller frame")

    def _dispatch_intent(self, binding, plan):
        segment = {"mode": "game_intent_uil", "binding": binding,
                   "outcome": plan["outcome"], "effects": copy.deepcopy(plan["effects"])}
        try:
            self._preflight_effects(binding, plan["effects"])
        except (Word16Error, IndexError, KeyError, TypeError, OverflowError) as exc:
            segment.update(status="preflight_fault", completed_effects=[],
                           interrupted_effect=None, error=str(exc))
            self._segments.append(segment)
            raise
        completed = []
        interrupted = None
        self._active_intent = True
        try:
            for effect in plan["effects"]:
                interrupted = effect
                self._commit_effects([effect])
                completed.append(copy.deepcopy(effect))
                interrupted = None
            if binding == "mailbox_open":
                self._return(self.udl["opening"]["return_value"])
                self._phase = "unrecovered_action_bookkeeping"
            else:
                self._goto(self.udl["turn"]["continue"])
                self._phase = "unrecovered_return_and_input_preparation"
        except (Word16Error, IndexError, KeyError, TypeError, OverflowError) as exc:
            segment.update(status="commit_fault", completed_effects=completed,
                           interrupted_effect=copy.deepcopy(interrupted),
                           interrupted_effect_status="unknown" if interrupted is not None else None,
                           error=str(exc))
            self._segments.append(segment)
            raise
        finally:
            self._active_intent = False
        self._increment(self.recovery_stats["binding_hits"], binding)
        self._increment(self.recovery_stats["outcomes"], plan["outcome"])
        for name in plan["executed_intents"]:
            self._increment(self.recovery_stats["primitive_hits"], name)
        self._segments.append(segment)
        return True

    def _nodes(self, nodes, temps):
        block = self.blocks.get(self.pc)
        is_block_entry = block is not None and nodes is block["nodes"]
        if is_block_entry:
            opening, turn = self.udl["opening"], self.udl["turn"]
            if self.enable_intents and self.pc in (opening["entry"], turn["entry"]):
                binding = "mailbox_open" if self.pc == opening["entry"] else "turn_counter"
                reason = self._opening_admission() if binding == "mailbox_open" else self._turn_admission()
                if reason is None:
                    try:
                        if binding == "mailbox_open":
                            plan = game_intents.evaluate_interaction(self.uil, self.semantic_state(), {"target": opening["target"]})
                        else:
                            state = {"entities": {}, "current_scene": None,
                                     "discourse": {"referent": None, "scene": None},
                                     "turn": {"count": self._field_value("turn.count")}}
                            plan = game_intents.evaluate_turn(self.uil, state)
                    except game_intents.GameIntentError as exc:
                        raise Word16Error(str(exc)) from exc
                    if plan["outcome"] != "unrecovered":
                        return self._dispatch_intent(binding, plan)
                    reason = "semantic_domain_unrecovered:" + plan.get("reason", "unspecified")
                self._increment(self.recovery_stats["residual_reasons"], reason)
            if self.pc == opening["return_pc"]:
                self._phase = "unrecovered_action_bookkeeping"
            scheduler_call = self.udl.get("turn", {}).get("scheduler_call")
            if scheduler_call is not None and self.pc == scheduler_call:
                self._phase = "unrecovered_background_scheduler_and_callbacks"
            if self.pc in (turn["continue"], turn["return_pc"]):
                self._phase = "unrecovered_return_and_input_preparation"
            self._record_low_level_block(self.pc)
        return Word16Runtime._nodes(self, nodes, temps)

    def run(self, max_steps=2_000_000):
        if self.fault is not None:
            raise Word16Error("Execution is faulted; restore a qualified checkpoint")
        before = copy.deepcopy(self.recovery_stats)
        self._segments = []
        if self._next_run_kind == "command":
            self._phase = "unrecovered_parser_and_object_resolution"
        self._next_run_kind = None
        try:
            result = super().run(max_steps=max_steps)
        finally:
            delta = _empty_stats()
            for key, value in self.recovery_stats.items():
                if isinstance(value, dict):
                    delta[key] = {name: count - before[key].get(name, 0)
                                  for name, count in value.items() if count != before[key].get(name, 0)}
                else:
                    delta[key] = value - before[key]
            delta["segments"] = copy.deepcopy(self._segments)
            delta["mode"] = "mixed_intent_and_ir" if any(
                s["mode"] == "game_intent_uil" for s in delta["segments"]) else "low_level_only"
            self.last_recovery = delta
        result["recovery"] = copy.deepcopy(delta)
        return result

    def command(self, text, max_steps=2_000_000):
        # Input validation may fail before run() gets a chance to create a
        # receipt. Never attach the preceding turn's receipt to that failure.
        if self.fault is None:
            self.last_recovery = {**_empty_stats(), "segments": [], "mode": "low_level_only"}
        self._next_run_kind = "command"
        return super().command(text, max_steps=max_steps)

    def low_level_snapshot(self):
        """Full source state for parity checks; normalize only package identity."""
        state = super().snapshot()
        current = state
        while current is not None:
            current["package_sha256"] = self.low_level_digest
            current = current["game_slot"]
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run partial game-intent UIL with explicit residual low-level IR")
    parser.add_argument("package")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--commands", help="JSON array of command strings")
    parser.add_argument("--transcript", help="Private output and intent/residual receipts")
    parser.add_argument("--checkpoint", help="Persist complete state after each input turn")
    parser.add_argument("--resume", help="Resume a checkpoint bound to both representations")
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
    runtime = IntentRuntime(load_package(args.package), seed=args.seed)
    if args.resume:
        runtime.load_checkpoint(args.resume)
    transcript = []
    def record(result, command=None):
        transcript.append({"command": command, **result})
        if result["text"]:
            print(result["text"], end="", flush=True)
        if args.checkpoint:
            runtime.save_checkpoint(args.checkpoint)
        if args.transcript:
            _atomic_json(args.transcript, transcript)
        return result
    def execute(command=None):
        try:
            result = runtime.run() if command is None else runtime.command(command)
        except Word16Error as exc:
            if args.transcript:
                transcript.append({"command": command, "status": "fault", "error": str(exc),
                                   "recovery": copy.deepcopy(runtime.last_recovery)})
                _atomic_json(args.transcript, transcript)
            raise
        return record(result, command)
    result = execute()
    if commands is not None:
        for command in commands:
            if result["status"] != "input":
                break
            result = execute(command)
    else:
        while result["status"] == "input":
            try:
                command = input("" if not sys.stdin.isatty() else "> ")
            except EOFError:
                break
            result = execute(command)
    if result["status"] == "budget_exhausted":
        print("Dispatch budget exhausted; state remains resumable.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
