"""Check scene UIL/UDL correspondence without importing the producer or decoder.

The preserved executable IR is the reference implementation. This consumer
checks the initial image, source operation operands, table entries, names/text,
routine headers and the live guards required by each specialization. It does
not infer handler intent, execute a story, or regard a hash as a semantic proof.
"""
from __future__ import annotations

import hashlib
import re

from . import scene_intents
from .intent_runtime import validate_package as validate_intents
from .word16 import Word16Error, Word16Runtime, _canonical, _integer


FORMAT = "fdisbull-zork-scene-package-1"
UDL_FORMAT = "fdisbull-zork-scene-udl-1"
DISPATCH_FORMAT = "fdisbull-game-dispatch-uil-1"
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,191}\Z")
_PROPERTY_ROLES = {17: "action", 2: "container_action", 9: "description"}
_STAGES = [
    ("actor_action", "actor.action", [], None),
    ("scene_before_action", "actor.scene.action", [], "before_action"),
    ("verb_before_action", "action.before_handler", [], None),
    ("indirect_object_action", "indirect_object.action", ["has_indirect_object"], None),
    ("container_action", "direct_object.parent.container_action",
     ["has_direct_object", "is_not_walk", "direct_object_has_parent"], None),
    ("direct_object_action", "direct_object.action", ["has_direct_object", "is_not_walk"], None),
    ("verb_action", "action.handler", [], None),
]


def _need(condition, message):
    if not condition:
        raise Word16Error(message)


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bounded(value, low, high, label):
    return _integer(value, label, low, high)


def _identity(value):
    _need(isinstance(value, str) and _ID.fullmatch(value), "Invalid scene binding identity")
    return value


def _covered(spans, intervals):
    intervals = sorted(intervals)
    for start, end in spans:
        for left, right in intervals:
            if left > start:
                break
            if right > start:
                start = right
            if start >= end:
                break
        if start < end:
            return False
    return True


class SourceReader(Word16Runtime):
    """Use existing read-only layout/text routines without starting execution."""
    def __init__(self, ir):
        self.memory = bytes.fromhex(ir["memory"]["initial"])
        self.layout = ir["layout"]
        self.writable_end = ir["memory"]["writable_end"]
        self.ir = ir
        self._observed_reads = None
        self._object_cache = {}

    def _read(self, address, width=8):
        value = super()._read(address, width)
        if self._observed_reads is not None:
            self._observed_reads.append((address, address + width // 8))
        return value

    def global_address(self, number):
        _bounded(number, 16, 255, "global number")
        address = self.layout["globals"] + 2 * (number - 16)
        self._bounds(address, 2, True)
        return address

    def object_info(self, number):
        if number not in self._object_cache:
            record = self._object(number)
            table = self._read(record + 7, 16)
            self._bounds(table, 1, True)
            words = self._read(table)
            name_end = table + 1 + words * 2
            self._bounds(table, 1 + words * 2, True)
            props = {number: (address, size) for number, address, size in self._properties(number)}
            for address, size in props.values():
                self._bounds(address, size, True)
            spans = [(record + 7, record + 9), (table, table + 1)]
            spans.extend((address - 1, address) for address, _ in props.values())
            terminator = max((address + size for address, size in props.values()), default=name_end)
            _need(self._read(terminator) == 0, "Object property terminator changed")
            spans.append((terminator, terminator + 1))
            name, name_reads = self.text(table + 1, name_end) if words else ("", [])
            self._object_cache[number] = {"record": record, "table": table, "properties": props,
                                          "structure": spans, "name": name, "name_reads": name_reads}
        return self._object_cache[number]

    def text(self, address, limit=None):
        self._observed_reads = []
        try:
            text = self._decode_text(address, limit=limit)
            return text, list(self._observed_reads)
        finally:
            self._observed_reads = None

    def block(self, address):
        _bounded(address, 0, len(self.memory) - 1, "source operation")
        block = self.ir["blocks"].get(str(address))
        _need(block is not None, "Scene source operation is absent from retained IR")
        raw = bytes.fromhex(block["guard"])
        _need(raw and self.memory[address:address + len(raw)] == raw, "Scene operation guard differs from source")
        return block

    def block_span(self, address):
        return address, address + len(bytes.fromhex(self.block(address)["guard"]))

    def routine(self, header, entry, locals_):
        _bounded(header, 64, len(self.memory) - 1, "routine header")
        count = self._read(header)
        _need(count <= 15 and entry == header + 1 + 2 * count, "Routine entry contradicts original local header")
        expected = [self._read(header + 1 + 2 * index, 16) for index in range(count)]
        _need(locals_ == expected, "Routine locals contradict original header")
        function = self.ir["functions"].get(str(header))
        _need(function is not None and function["entry"] == entry and function["locals"] == locals_,
              "Routine correspondence differs from retained IR")
        self.block(entry)
        return header, entry


class Witnesses:
    """Validate bytes once, then prove every specialization guards its dependencies."""
    def __init__(self, source, witnesses):
        _need(isinstance(witnesses, dict) and 1 <= len(witnesses) <= 16384,
              "Missing or excessive scene witnesses")
        self.rows = witnesses
        total = 0
        for identity, row in witnesses.items():
            _identity(identity)
            _need(isinstance(row, dict), "Invalid source witness")
            start = _bounded(row.get("start"), 0, len(source.memory) - 1, "witness start")
            end = _bounded(row.get("end"), start + 1, len(source.memory), "witness end")
            data = bytes.fromhex(row["bytes"])
            total += len(data)
            _need(data == source.memory[start:end] and row.get("sha256") == hashlib.sha256(data).hexdigest(),
                  "Scene witness bytes or digest differ from source")
        _need(total <= 8 * 1024 * 1024, "Scene witness bytes exceed budget")

    def covers(self, names, spans):
        _need(isinstance(names, list) and len(names) <= 16384
              and all(isinstance(name, str) and name in self.rows for name in names),
              "Invalid or missing live guard references")
        intervals = [(self.rows[name]["start"], self.rows[name]["end"]) for name in names]
        _need(_covered(spans, intervals), "Live guards omit a required source dependency")


def _operations(source, address):
    """Resolve expression aliases inside a source block; never execute effects."""
    aliases = {}
    def value(item):
        if isinstance(item, dict):
            if set(item) == {"tmp"}:
                return aliases.get(item["tmp"], item)
            result = {k: value(v) for k, v in item.items()}
            if set(result) == {"calc", "args"} and all(type(x) is int for x in result["args"]):
                args = result["args"]
                if result["calc"] == "mul": return args[0] * args[1]
                if result["calc"] == "add": return args[0] + args[1]
                if result["calc"] == "u16": return args[0] & 65535
            return result
        if isinstance(item, list): return [value(x) for x in item]
        return item
    result = []
    for node in source.block(address)["nodes"]:
        if node["op"] == "let":
            aliases[node["name"]] = value(node["value"])
        elif node["op"] == "read_var":
            key = "indirect_variable" if node.get("indirect", False) else "variable"
            aliases[node["dest"]] = {key: value(node["index"])}
        else:
            item = {key: value(v) for key, v in node.items() if key != "dest"}
            result.append(item)
            if "dest" in node:
                aliases[node["dest"]] = {"result": len(result) - 1}
    return result


def _one(source, address, op, **fields):
    matches = [node for node in _operations(source, address) if node.get("op") == op]
    _need(len(matches) == 1 and all(matches[0].get(key) == val for key, val in fields.items()),
          "Source operation contradicts scene semantic correspondence")
    return matches[0]


def _scene_bindings(source, uil, udl, guards):
    _need(set(udl["scenes"]) == set(uil["scenes"]), "Scene identities do not match UDL")
    _need(set(udl["facts"]) == set(uil["facts"]) and set(udl["doors"]) == set(uil["doors"]),
          "Live scene conditions do not match UDL")
    scene_numbers = {}
    for identity, binding in udl["scenes"].items():
        number = _bounded(binding["object"], 1, 255, "scene object")
        _need(number not in scene_numbers, "Scene identities alias the same source object")
        scene_numbers[number] = identity
        obj = source.object_info(number)
        _need(binding["record"] == obj["record"] and binding["property_table"] == obj["table"],
              "Scene object layout changed")
        _need(uil["scenes"][identity]["name"] == obj["name"], "Scene name differs from original")
        guards.covers(binding["structure_guards"], obj["structure"])
        guards.covers(binding["name_dependencies"], obj["name_reads"])
    for identity, binding in udl["facts"].items():
        address = source.global_address(binding["global"])
        _need(binding["address"] == address and binding["interpretation"] == "nonzero"
              and binding["mutable"] is True, "Conditional exit global correspondence changed")
        _need(binding["initial_value"] == source._read(address, 16)
              and uil["facts"][identity]["initial"] == bool(binding["initial_value"]),
              "Conditional initial value differs from source")
        guards.covers([binding["witness"]], [(address, address + 2)])
    for identity, binding in udl["doors"].items():
        obj = source.object_info(binding["object"])
        _need(binding["record"] == obj["record"] and binding["attribute"] == 11
              and binding["address"] == obj["record"] + 1 and binding["mask"] == 16
              and binding["mutable"] is True, "Door attribute correspondence changed")
        _need(uil["doors"][identity]["name"] == obj["name"]
              and uil["doors"][identity]["initial_open"] == bool(source._read(obj["record"] + 1) & 16),
              "Door initial state or name differs from source")
        guards.covers(binding["structure_guards"], obj["structure"])
        guards.covers(binding["name_dependencies"], obj["name_reads"])
    _need(set(udl["resources"]) == set(uil["resources"]), "Scene resource inventory differs")
    for identity, binding in udl["resources"].items():
        if identity == "newline":
            _need(uil["resources"][identity] == "\n", "Scene newline semantics changed")
            _one(source, binding["source_operation"], "emit", value="\n")
            guards.covers(binding["dependencies"], [source.block_span(binding["source_operation"])])
        else:
            text, reads = source.text(binding["address"])
            _need(text == uil["resources"][identity], "Scene resource differs from original text")
            guards.covers(binding["dependencies"], reads)
            if "source_operation" in binding:
                _one(source, binding["source_operation"], "library", name="text.decode", args=[binding["address"]])
    _need(set(udl["handlers"]) == set(uil["handlers"]), "Residual scene handler inventory differs")
    for identity, binding in udl["handlers"].items():
        if identity == uil["missing_exit"]:
            _need(binding["kind"] == "source_region", "Missing-direction behavior must remain residual")
            source.block(binding["entry"])
            guards.covers(binding["guard_witnesses"], [(binding["entry"], binding["end"])])
        else:
            _need(binding["packed"] * 2 == binding["header"], "Packed scene callback target changed")
            span = source.routine(binding["header"], binding["entry"], binding["locals"])
            guards.covers(binding["guard_witnesses"], [span])
    exit_ids = set()
    directions = udl["selection"]["direction_properties"]
    expected_directions = dict(zip(("north", "east", "west", "south", "northeast", "northwest", "southeast",
                                   "southwest", "up", "down", "in", "out", "land"), range(31, 18, -1)))
    _need(directions == expected_directions, "Direction identity mapping contradicts the source profile")
    for identity, scene in uil["scenes"].items():
        binding = udl["scenes"][identity]
        obj = source.object_info(binding["object"])
        _need((11 in obj["properties"]) == ("description" in binding)
              and (17 in obj["properties"]) == ("handler" in binding),
              "Scene presentation/callback inventory differs from source")
        if "initial_traits" in scene:
            expected_traits = {name: bool(source._read(obj["record"] + bit // 8) & (128 >> (bit % 8)))
                               for name, bit in (("land", 6), ("naturally_lit", 20), ("ruined", 18))}
            _need(scene["initial_traits"] == expected_traits, "Initial scene traits differ from source")
        expected_directions = {name for name, number in directions.items() if number in obj["properties"]}
        _need(set(scene["exits"]) == expected_directions and set(binding["exits"]) == expected_directions,
              "Scene exit inventory differs from original properties")
        if "description" in binding:
            desc = binding["description"]
            _need(obj["properties"].get(11) == (desc["address"], 2)
                  and udl["resources"][desc["resource"]]["address"] == 2 * source._read(desc["address"], 16),
                  "Scene description reference changed")
            guards.covers(desc["guard_witnesses"], [*obj["structure"], (desc["address"], desc["address"] + 2)])
            _need(scene.get("description") == {"kind": "static", "resource": desc["resource"]},
                  "Scene description does not match its source binding")
        if "handler" in binding:
            handler = binding["handler"]
            address, size = obj["properties"].get(17, (None, None))
            _need(size == 2 and source._read(address, 16) == udl["handlers"][handler["id"]]["packed"],
                  "Scene callback reference changed")
            _need(scene.get("on_event") == {"kind": "residual", "handler": handler["id"]},
                  "Scene event does not match its source binding")
            if "description" not in binding:
                _need(scene.get("description") == {"kind": "residual", "handler": handler["id"]},
                      "Scene description callback differs from its source binding")
            guards.covers(handler["guard_witnesses"], [*obj["structure"], (address, address + 2)])
        else:
            _need("on_event" not in scene and ("description" in binding or "description" not in scene),
                  "Scene invents an event or description")
        for direction, rule in scene["exits"].items():
            exit_ids.add(rule["id"])
            row = udl["exits"][rule["id"]]
            prop = directions[direction]
            address, size = obj["properties"][prop]
            raw = source.memory[address:address + size]
            _need(row["scene"] == identity and row["direction"] == direction and row["property"] == prop
                  and row["address"] == address and row["header"] == address - 1
                  and row["size"] == size and row["bytes"] == raw.hex()
                  and binding["exits"][direction] == rule["id"], "Exit source extent or identity changed")
            _need(rule["kind"] == {1: "direct", 2: "blocked", 3: "routine", 4: "conditional", 5: "door"}.get(size),
                  "Exit kind contradicts its original record")
            guards.covers(row["guard_witnesses"], [*obj["structure"], (address - 1, address + size)])
            if size in (1, 4, 5):
                _need(scene_numbers.get(raw[0]) == rule["destination"] and row["destination"] == raw[0],
                      "Exit destination differs from original")
            if size in (4, 5):
                key, definitions = ("fact", udl["facts"]) if size == 4 else ("door", udl["doors"])
                field = "global" if size == 4 else "object"
                _need(definitions[rule[key]][field] == raw[1] and row[key] == rule[key], "Exit predicate source changed")
                _need(row["failure_packed"] == source._read(address + 2, 16), "Residual failure-text local value changed")
            packed = source._read(address if size == 2 else address + 2, 16) if size in (2, 4, 5) else 0
            if packed:
                _need(udl["resources"][rule["failure_resource"]]["address"] == packed * 2,
                      "Exit refusal text reference changed")
            else:
                _need("failure_resource" not in rule, "Exit invents a failure message")
            if size == 3:
                _need(raw[2] == 0 and udl["handlers"][rule["residual"]]["packed"] == source._read(address, 16)
                      and row["handler"] == rule["residual"], "Routine exit target changed")
            if size == 5: _need(raw[4] == 0, "Door exit layout padding changed")
    _need(set(udl["exits"]) == exit_ids, "UDL exit inventory differs from UIL")
    return scene_numbers


def _primitive_bindings(source, uil, udl, guards):
    selection, movement = udl["selection"], udl["movement"]
    common = udl["runtime_guards"]
    # Bind header layout reads used by every projected fact/object/text.
    guards.covers(common, [(8, 16), (24, 26)])
    for binding in (selection, movement):
        span = source.routine(binding["header"], binding["entry"], binding["locals"])
        guards.covers([*common, *binding["guard_witnesses"]], [span])
    _need(len(selection["locals"]) == 5 and len(movement["locals"]) == 6,
          "Scene primitive frame schema changed")
    _need(selection["current_scene_global"] == movement["current_scene_global"], "Scene primitives disagree on current location")
    for number in (selection["current_scene_global"], selection["direction_global"], movement["actor_global"]):
        source.global_address(number)
    operations = selection["source_operations"]
    slots = selection["residual_frame_locals"]
    _need(slots == {"property_address": 1, "property_size": 2, "failure_resource": 3,
                    "door_object": 4, "routine_result": 5}, "Residual selection frame projection changed")
    _need(selection["effect_entry"] == operations["property_lookup"], "Exit selection entry changed")
    for address in operations.values():
        guards.covers([*common, *selection["guard_witnesses"]], [source.block_span(address)])
    _one(source, operations["property_lookup"], "library", name="property.address",
         args=[{"variable": selection["current_scene_global"]}, {"variable": selection["direction_global"]}])
    _one(source, operations["property_lookup"], "write_var", index=slots["property_address"], value={"result": 0})
    missing_test = source.block(operations["property_lookup"])["next"]
    _one(source, missing_test, "if", condition={"calc": "eq", "args": [{"variable": 1}, 0]},
         then=[{"op": "goto", "target": udl["handlers"][uil["missing_exit"]]["entry"]}],
         **{"else": [{"op": "goto", "target": operations["property_length"]}]})
    guards.covers([*common, *selection["guard_witnesses"]], [source.block_span(missing_test)])
    _one(source, operations["property_length"], "library", name="property.length", args=[{"variable": 1}])
    _one(source, operations["property_length"], "write_var", index=slots["property_size"], value={"result": 0})
    for name, index, width, store in (
            ("direct_target", 0, 8, 0), ("conditional_target", 0, 8, 0), ("door_target", 0, 8, 0),
            ("blocked_resource", 0, 16, 0), ("routine_target", 0, 16, 0),
            ("conditional_selector", 1, 8, 0), ("door_selector", 1, 8, slots["door_object"]),
            ("conditional_resource", 1, 16, slots["failure_resource"]),
            ("door_resource", 1, 16, slots["failure_resource"])):
        _one(source, operations[name], "write_var", index=store,
             value=_memory_read({"variable": slots["property_address"]}, index, width), indirect=False)
    _one(source, operations["conditional_value"], "write_var", index=0,
         value={"indirect_variable": {"variable": 0}})
    _one(source, operations["conditional_test"], "if", condition={"calc": "eq", "args": [{"variable": 0}, 0]},
         then=[{"op": "goto", "target": operations["conditional_resource"]}],
         **{"else": [{"op": "goto", "target": operations["conditional_target"]}]})
    _one(source, operations["door_test"], "library", name="attribute.test", args=[{"variable": 4}, 11])
    _one(source, operations["door_test"], "if", condition={"result": 0},
         then=[{"op": "goto", "target": operations["door_target"]}],
         **{"else": [{"op": "goto", "target": operations["door_resource"]}]})
    arrival = selection["residual_arrival"]
    _need(arrival["header"] == movement["header"] and arrival["entry"] == movement["entry"],
          "Exit selection and relocation disagree on arrival routine")
    for name in ("direct_travel", "conditional_travel", "door_travel"):
        _one(source, operations[name], "call", target=arrival["header"], args=[{"variable": 0}],
             store=0, resume=source.block(operations[name])["next"])
    _one(source, operations["routine_call"], "call", target={"calc": "mul", "args": [{"variable": 0}, 2]},
         args=[], store=5, resume=source.block(operations["routine_call"])["next"])
    _need(all(row["source_operation"] == operations["conditional_value"] for row in udl["facts"].values()),
          "Conditional field binds another source operation")
    _need(all(row["source_operation"] == operations["door_test"] for row in udl["doors"].values()),
          "Door field binds another source operation")
    for name in ("blocked_return", "conditional_return", "default_blocked_return", "door_custom_return", "door_return"):
        _one(source, operations[name], "return", value=selection["refusal_return"])
    for resource, name in (("default_blocked", "default_blocked_print"), ("default_closed_prefix", "door_prefix"),
                           ("default_closed_suffix", "door_suffix")):
        _need(udl["resources"][resource]["source_operation"] == operations[name], "Default narration source changed")
    referent = selection["referent"]
    _need(len(referent["source_operations"]) == 2, "Invalid discourse operation inventory")
    for address, number, value in zip(referent["source_operations"],
                                     (referent["object_global"], referent["scene_global"]),
                                     ({"variable": 1}, {"variable": selection["current_scene_global"]})):
        source.global_address(number)
        _one(source, address, "write_var", index=number, value=value)
        guards.covers([*common, *selection["guard_witnesses"]], [source.block_span(address)])
    effects = movement["source_operations"]
    definitions = udl["primitives"]
    _need(set(definitions) == {"scene.select_exit", "scene.move_actor"}
          and definitions["scene.select_exit"]["original_operations"] == operations
          and definitions["scene.move_actor"]["original_operations"] == effects
          and definitions["scene.move_actor"]["source_fields"] == {
              "actor_global": movement["actor_global"], "destination_local": movement["destination_local"],
              "current_scene_global": movement["current_scene_global"]}, "Named primitive source definition differs")
    _need(isinstance(effects, list) and len(effects) == 2 and movement["effect_entry"] == effects[0]
          and source.block(effects[0])["next"] == effects[1]
          and source.block(effects[1])["next"] == movement["continuation"], "Movement source span changed")
    source.block(movement["continuation"])
    for address in effects:
        guards.covers([*common, *movement["guard_witnesses"]], [source.block_span(address)])
    _need(_operations(source, effects[0]) == [{"op": "library", "name": "tree.insert", "args": [
        {"variable": movement["actor_global"]}, {"variable": movement["destination_local"]}]}],
        "Movement effect is not the declared actor relocation")
    _one(source, effects[1], "write_var", index=movement["current_scene_global"], value={"variable": movement["destination_local"]})
    _need(len(_operations(source, effects[1])) == 1, "Movement current-scene effect contains extra work")
    _bounded(movement["destination_local"], 1, 6, "destination local")
    _bounded(movement["vehicle_local"], 1, 6, "vehicle local")
    _bounded(movement["qualified_actor"], 1, 255, "qualified actor")


def _dispatch_shape(uil):
    _need(isinstance(uil, dict) and set(uil) == {"format", "actions", "handlers", "stages",
          "grammar", "selection_semantics", "claim"} and uil["format"] == DISPATCH_FORMAT,
          "Invalid dispatch UIL schema")
    _need(uil["selection_semantics"] == "ordered_first_handled"
          and uil["claim"] == "resolved_rule_selection_with_explicit_residual_bodies",
          "Dispatch claims change the retained-handler contract")
    handlers, actions = uil["handlers"], uil["actions"]
    _need(isinstance(handlers, dict) and 1 <= len(handlers) <= 2048, "Invalid dispatch handler inventory")
    for identity, handler in handlers.items():
        _identity(identity)
        _need(isinstance(handler, dict) and set(handler) == {"role", "representation", "intent_status"}
              and handler["role"] in ("action", "preaction", "container_action", "description")
              and handler["representation"] == "low_level_ir" and handler["intent_status"] == "unrecovered",
              "Dispatch handler must retain its unresolved body")
    _need(isinstance(actions, list) and 1 <= len(actions) <= 256, "Invalid dispatch action inventory")
    ids = set()
    def words(value, empty=False):
        _need(isinstance(value, list) and (empty or value) and len(value) <= 128
              and all(isinstance(x, str) and 0 < len(x) <= 64 for x in value)
              and len(value) == len(set(value)), "Invalid dispatch vocabulary")
    for action in actions:
        _need(isinstance(action, dict) and set(action) == {"id", "handler", "before_handler", "aliases"},
              "Invalid named action")
        _identity(action["id"])
        _need(action["id"] not in ids, "Duplicate named action")
        ids.add(action["id"])
        _need(isinstance(action["handler"], str) and action["handler"] in handlers
              and handlers[action["handler"]]["role"] == "action", "Action handler correspondence changed")
        before = action["before_handler"]
        _need(before is None or isinstance(before, str) and before in handlers
              and handlers[before]["role"] == "preaction", "Preaction handler correspondence changed")
        words(action["aliases"])
    _need(uil["stages"] == [{"id": a, "selector": b, "requires": c, "event": d} for a, b, c, d in _STAGES],
          "Dispatch stage order or conditions changed")
    _need(isinstance(uil["grammar"], list) and 1 <= len(uil["grammar"]) <= 4096, "Invalid grammar inventory")
    for row in uil["grammar"]:
        _need(isinstance(row, dict) and set(row) == {"action", "verbs", "object_count", "prepositions", "status"},
              "Invalid grammar association")
        _need(isinstance(row["action"], str) and row["action"] in ids
              and type(row["object_count"]) is int and row["object_count"] in (0, 1, 2)
              and isinstance(row["prepositions"], list) and len(row["prepositions"]) == 2
              and row["status"] == "syntax_association_parser_filters_remain_residual",
              "Grammar association exceeds recovered parser scope")
        words(row["verbs"])
        for values in row["prepositions"]: words(values, True)


def _operand(value):
    _need(isinstance(value, dict) and len(value) == 1, "Invalid dispatch source operand")
    if "constant" in value: return _bounded(value["constant"], 0, 65535, "constant operand")
    _need("variable" in value, "Invalid dispatch source operand")
    return {"variable": _bounded(value["variable"], 0, 255, "variable operand")}


def _memory_word(base, index):
    return _memory_read(base, index, 16)


def _memory_read(base, index, width):
    displacement = index * (width // 8) if type(index) is int else {"calc": "mul", "args": [index, width // 8]}
    return {"calc": "mem" + str(width), "args": [{"calc": "u16", "args": [{"calc": "add", "args": [base, displacement]}]}]}


def _dispatch_sites(source, dispatch, guards):
    sites = dispatch["sites"]
    _need(isinstance(sites, list) and 1 <= len(sites) <= 1024, "Invalid dispatch site inventory")
    starts, identities = set(), set()
    for site in sites:
        _identity(site["id"])
        pcs = site["source_pcs"]
        _need(isinstance(pcs, list) and len(pcs) in (2, 3) and len(set(pcs)) == len(pcs)
              and site["start"] == pcs[0] and site["call_pc"] == pcs[-1], "Dispatch source span is invalid")
        _need(site["start"] not in starts and site["id"] not in identities, "Duplicate dispatch site")
        starts.add(site["start"]); identities.add(site["id"])
        _need(len(site["source_operations"]) == len(pcs), "Dispatch operation inventory changed")
        for index, (pc, original) in enumerate(zip(pcs, site["source_operations"])):
            block = source.block(pc)
            next_pc = pcs[index + 1] if index + 1 < len(pcs) else site["return_pc"]
            _need(block["next"] == next_pc and original["offset"] == pc
                  and original["end"] == next_pc and original["bytes"] == block["guard"],
                  "Dispatch operation bytes or continuation differ from retained IR")
            guards.covers([site["witness"]], [source.block_span(pc)])
        source.block(site["return_pc"])
        if site["frame_local_count"] is not None:
            _bounded(site["frame_local_count"], 0, 15, "dispatch local count")
        selector = site["selector"]
        producer = pcs[-2]
        if selector["kind"] == "table":
            _need(len(pcs) == 2 and set(selector) == {"kind", "table", "index", "pointer_global"}
                  and selector["table"] in dispatch["tables"], "Invalid dispatch table selector")
            table = dispatch["tables"][selector["table"]]
            _need(selector["pointer_global"] == table["pointer_global"], "Dispatch table pointer differs")
            _one(source, producer, "write_var", index=0, value=_memory_word(
                {"variable": selector["pointer_global"]}, _operand(selector["index"])))
            _need(len(_operations(source, producer)) == 1, "Dispatch table read contains extra operations")
        else:
            _need(selector["kind"] == "property" and set(selector) == {"kind", "object", "property"}
                  and selector["property"] in _PROPERTY_ROLES, "Invalid callback property selector")
            obj = selector["object"]
            if isinstance(obj, dict) and set(obj) == {"parent"}:
                _need(len(pcs) == 3, "Parent callback selector lost its source operation")
                _one(source, pcs[0], "library", name="tree.parent", args=[_operand(obj["parent"])])
                _one(source, pcs[0], "write_var", index=0, value={"result": 0})
                source_object = {"variable": 0}
            else:
                _need(len(pcs) == 2, "Unexpected callback selector prefix")
                source_object = _operand(obj)
            _one(source, producer, "library", name="property.get", args=[source_object, selector["property"]])
            _one(source, producer, "write_var", index=0, value={"result": 0})
            _need(len(_operations(source, producer)) == 2, "Callback property read contains extra operations")
        _need(isinstance(site["arguments"], list) and len(site["arguments"]) <= 3, "Invalid callback arguments")
        expected = {"op": "call", "target": {"calc": "mul", "args": [{"variable": 0}, 2]},
                    "args": [_operand(v) for v in site["arguments"]], "store": site["store"], "resume": site["return_pc"]}
        _need(_operations(source, site["call_pc"]) == [expected], "Callback call disagrees with the source ABI")
    perform = dispatch["perform"]
    function = source.ir["functions"].get(str(perform["routine_header"]))
    _need(function is not None, "PERFORM routine is missing")
    source.routine(perform["routine_header"], perform["entry"], function["locals"])
    _need(perform["local_count"] == len(function["locals"]) == 7, "PERFORM frame convention changed")
    for key in ("action_local", "direct_object_local", "indirect_object_local", "result_local"):
        _bounded(perform[key], 1, 7, key)
    source.global_address(perform["actor_global"]); source.global_address(perform["scene_global"])
    stage_sites = {row["id"]: row for row in sites}
    _need({row[0] for row in _STAGES} <= set(stage_sites), "Named dispatch stages lack source sites")
    expected = {
        "actor_action": {"kind": "property", "object": {"variable": perform["actor_global"]}, "property": 17},
        "scene_before_action": {"kind": "property", "object": {"parent": {"variable": perform["actor_global"]}}, "property": 17},
        "indirect_object_action": {"kind": "property", "object": {"variable": perform["indirect_object_local"]}, "property": 17},
        "container_action": {"kind": "property", "object": {"parent": {"variable": perform["direct_object_local"]}}, "property": 2},
        "direct_object_action": {"kind": "property", "object": {"variable": perform["direct_object_local"]}, "property": 17},
    }
    for name, table in (("verb_before_action", "preactions"), ("verb_action", "actions")):
        expected[name] = {"kind": "table", "table": table, "index": {"variable": perform["action_local"]},
                          "pointer_global": dispatch["tables"][table]["pointer_global"]}
    for name, selector in expected.items():
        site = stage_sites[name]
        _need(site["selector"] == selector and site["frame_local_count"] == 7
              and site["store"] == perform["result_local"], "Named dispatch stage contradicts its source selector")
        _need(site["arguments"] == ([{"constant": 1}] if name == "scene_before_action" else []),
              "Named dispatch event arguments changed")


def _grammar_bindings(source, uil, dispatch, guards):
    grammar = dispatch["grammar"]
    _need(isinstance(grammar, list) and len(grammar) == len(uil["grammar"]), "Grammar provenance inventory differs")
    table = dispatch["grammar_table"]
    address = source.global_address(table["pointer_global"])
    count = _bounded(table["count"], 1, 256, "grammar table count")
    _need(table["pointer_address"] == address and source._read(address, 16) == table["start"],
          "Grammar table root pointer changed")
    guards.covers([table["witness"]], [(table["start"], table["start"] + 2 * count)])
    guards.covers([table["pointer_witness"]], [(address, address + 2)])
    dictionary = source.layout["dictionary"]
    header = dictionary + 1 + source._read(dictionary)
    width = source._read(header)
    words_count = source._read(header + 1, 16)
    words_count = words_count if words_count < 32768 else 65536 - words_count
    words_start = header + 3
    _need(width >= 7 and words_count > 0, "Unsupported source vocabulary layout")
    def word(row, flag, number):
        at = row["address"]
        _need(words_start <= at < words_start + width * words_count and (at - words_start) % width == 0,
              "Grammar spelling is not a dictionary entry")
        text, _ = source.text(at, at + 4)
        flags = source._read(at + 4)
        slot = 5 if flags & 3 == (1 if flag == 0x40 else 0) else 6
        _need(row["text"] == text and flags & flag and source._read(at + slot) == number,
              "Grammar spelling or encoded selector changed")
        return text
    aliases = {row["id"]: set() for row in uil["actions"]}
    verb_numbers = set()
    for row, semantic in zip(grammar, uil["grammar"]):
        number = _bounded(row["verb_number"], 256 - count, 255, "verb selector")
        verb_numbers.add(number)
        pointer = table["start"] + 2 * (255 - number)
        group = source._read(pointer, 16)
        at = row["address"]
        _need(row["pointer"] == pointer and row["group"] == group
              and group + 1 <= at < group + 1 + 8 * source._read(group)
              and (at - group - 1) % 8 == 0, "Grammar row is outside its original group")
        raw = list(source.memory[at:at + 8])
        _need(len(raw) == 8 and row["bytes"] == raw and row["action"] == raw[7]
              and row["object_count"] == raw[0] & 3, "Grammar row bytes or meaning changed")
        action = uil["actions"][row["action"]]["id"]
        verbs = sorted(word(item, 0x40, number) for item in row["words"])
        prepositions = [sorted(word(item, 8, raw[i + 1]) for item in values)
                        for i, values in enumerate(row["preposition_words"])]
        _need(len(prepositions) == 2 and all(bool(values) == bool(raw[i + 1]) for i, values in enumerate(prepositions)),
              "Grammar preposition inventory changed")
        _need(row["prepositions"] == prepositions and semantic["action"] == action
              and semantic["verbs"] == verbs and semantic["prepositions"] == prepositions
              and semantic["object_count"] == row["object_count"], "Grammar UIL differs from its source association")
        aliases[action].update(verbs)
    _need(verb_numbers == set(range(256 - count, 256)), "Grammar table domain is incomplete")
    for action in uil["actions"]:
        _need(action["aliases"] == sorted(aliases[action["id"]]), "Action aliases differ from qualified syntax")


def _dispatch_bindings(source, uil, dispatch, scene_numbers):
    _dispatch_shape(uil)
    _need(dispatch["format"] == "fdisbull-zork-dispatch-udl-1"
          and dispatch["source_sha256"] == source.ir["source"]["sha256"]
          and dispatch["all_game_intent_recovered"] is False, "Dispatch source identity or qualification changed")
    guards = Witnesses(source, dispatch["witnesses"])
    _need(set(dispatch["handlers"]) == set(uil["handlers"]), "Dispatch handler identity inventory differs")
    for identity, row in dispatch["handlers"].items():
        _need(row["packed"] * 2 == row["routine_header"], "Packed dispatch routine changed")
        span = source.routine(row["routine_header"], row["entry"], row["locals"])
        guards.covers([row["witness"]], [span])
    def target(identity, packed, role):
        if packed == 0:
            _need(identity is None, "Null callback acquired an invented handler")
        else:
            _need(identity in dispatch["handlers"] and dispatch["handlers"][identity]["packed"] == packed
                  and uil["handlers"][identity]["role"] == role, "Handler target or role differs from original")
    _need(set(dispatch["tables"]) == {"actions", "preactions"}, "Unsupported dispatch table inventory")
    _need(len(dispatch["actions"]) == len(uil["actions"]), "Dispatch action inventory differs")
    for table in dispatch["tables"].values():
        address = source.global_address(table["pointer_global"])
        _need(table["count"] == len(uil["actions"]) and table["end"] == table["start"] + 2 * table["count"]
              and table["pointer_address"] == address and table["pointer_value"] == table["start"]
              and source._read(address, 16) == table["start"]
              and table["start"] >= source.writable_end, "Dispatch table extent or root pointer changed")
        guards.covers([table["witness"]], [(table["start"], table["end"])])
        guards.covers([table["pointer_witness"]], [(address, address + 2)])
    for number, (row, action) in enumerate(zip(dispatch["actions"], uil["actions"])):
        _need(row["number"] == number and all(row[key] == action[key] for key in ("id", "handler", "before_handler")),
              "Named action does not match its table binding")
        for key, table_name, cell_key, role in (("handler", "actions", "action_cell", "action"),
                                             ("before_handler", "preactions", "preaction_cell", "preaction")):
            cell = dispatch["tables"][table_name]["start"] + 2 * number
            _need(row[cell_key] == cell, "Action table cell changed")
            target(action[key], source._read(cell, 16), role)
    objects = dispatch["objects"]
    _need(isinstance(objects, dict) and 1 <= len(objects) <= 255, "Invalid callback object inventory")
    by_number = {}
    for identity, row in objects.items():
        _identity(identity)
        number = _bounded(row["number"], 1, 255, "callback object number")
        _need(number not in by_number, "Callback object identities are ambiguous")
        by_number[number] = identity
        obj = source.object_info(number)
        _need(row["record"] == obj["record"] and row["property_table"] == obj["table"], "Callback object layout changed")
        guards.covers(row["layout_witnesses"], obj["structure"])
        if number in scene_numbers: _need(identity == scene_numbers[number], "Scene identity differs in callback graph")
    seen = set()
    _need(len(dispatch["properties"]) == len(objects) * len(_PROPERTY_ROLES), "Callback property inventory is incomplete")
    for row in dispatch["properties"]:
        pair = row["object"], row["property"]
        _need(pair not in seen and row["object"] in by_number and row["property"] in _PROPERTY_ROLES,
              "Duplicate or unsupported callback property binding")
        seen.add(pair)
        _need(row["object_id"] == by_number[row["object"]] and row["role"] == _PROPERTY_ROLES[row["property"]],
              "Callback object identity or property role differs")
        obj = source.object_info(row["object"])
        prop = obj["properties"].get(row["property"])
        cell, size = prop if prop is not None else (source.layout["objects"] + 2 * (row["property"] - 1), 2)
        _need(size == row["size"] == 2 and row["cell"] == cell and row["uses_default"] is (prop is None)
              and row["initial_packed"] == source._read(cell, 16), "Callback property value/default correspondence changed")
        target(row["handler"], row["initial_packed"], row["role"])
        guards.covers([row["witness"]], [(cell, cell + 2)])
    for variant in dispatch.get("callback_variants", []):
        target(variant["handler"], variant["packed"], "action")
        _need(variant["property"] == 17, "Unsupported mutable callback property")
        origin = variant["origin"]
        spans = [source.block_span(pc) for pc in variant["source_pcs"]]
        _need(variant["setter_pc"] in variant["source_pcs"], "Mutable callback setter is not witnessed")
        if origin["kind"] == "literal_callback_assignment":
            _one(source, variant["setter_pc"], "library", name="property.put",
                 args=[_operand(variant["target"]), variant["property"], variant["packed"]])
        else:
            _need(origin["kind"] == "room_pseudo_property_pair" and origin["property"] == 4
                  and scene_numbers.get(origin["scene_object"]) == origin["scene"], "Unknown finite callback origin")
            obj = source.object_info(origin["scene_object"])
            address, size = obj["properties"][4]
            cell = origin["cell"]
            _need(size % 4 == 0 and address <= cell <= address + size - 4 and (cell - address) % 4 == 0
                  and origin["property_header"] == address - 1
                  and source._read(cell, 16) == origin["dictionary_word"]
                  and source._read(cell + 2, 16) == variant["packed"], "Pseudo callback does not match its original definition")
            _need(source.text(origin["dictionary_word"])[0] == origin["word"], "Pseudo object word changed")
            _need(set(variant["target"]) == {"object"}, "Pseudo callback has an invalid target")
            _bounded(variant["target"]["object"], 1, 255, "pseudo object")
            _one(source, variant["setter_pc"], "library", name="property.put",
                 args=[variant["target"]["object"], variant["property"], {"variable": 0}])
            spans.append((cell, cell + 4))
        guards.covers(variant["source_witnesses"], spans)
    _dispatch_sites(source, dispatch, guards)
    _grammar_bindings(source, uil, dispatch, guards)
    perform = dispatch["perform"]
    _need(dispatch["actions"][perform["walk_action_number"]]["id"] == perform["walk_action"],
          "WALK action identity changed")


def validate_package(package):
    """Validate every source-bound definition before a mixed consumer starts.

    Metadata records recovered hypotheses and finite evidence. Validation keeps
    those claims separate from correspondence and does not establish whole-game
    intent or equivalence outside executed reference cases.
    """
    try:
        _need(isinstance(package, dict) and set(package) == {"format", "base_intents", "uil", "dispatch_uil", "udl"}
              and package["format"] == FORMAT, "Unsupported scene package")
        base, uil, udl = package["base_intents"], package["uil"], package["udl"]
        validate_intents(base)
        scene_intents.validate_uil(uil)
        source = SourceReader(base["low_level_ir"])
        _need(udl["format"] == UDL_FORMAT and udl["source"] == base["low_level_ir"]["source"]
              and udl["base_intents_sha256"] == _digest(base) and udl["uil_sha256"] == _digest(uil)
              and udl["dispatch_uil_sha256"] == _digest(package["dispatch_uil"])
              and udl["initial_image_sha256"] == hashlib.sha256(source.memory).hexdigest(),
              "Scene package is not bound to its preserved source and semantic documents")
        guards = Witnesses(source, udl["witnesses"])
        scene_numbers = _scene_bindings(source, uil, udl, guards)
        _primitive_bindings(source, uil, udl, guards)
        _dispatch_bindings(source, package["dispatch_uil"], udl["dispatch"], scene_numbers)
        _need(udl["movement"]["qualified_actor"] in {
                  row["number"] for row in udl["dispatch"]["objects"].values()}
              and udl["dispatch"]["perform"]["actor_global"] == udl["movement"]["actor_global"]
              and udl["dispatch"]["perform"]["scene_global"] == udl["movement"]["current_scene_global"],
              "Named moving actor or current scene differs across source bindings")
        _need(udl["qualification"]["all_game_intent_recovered"] is False,
              "Scene package must retain its partial recovery claim")
    except Word16Error:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError) as exc:
        raise Word16Error("Invalid or incomplete scene source correspondence: " + str(exc)) from exc
    return package
