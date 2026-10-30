"""Independently qualify a door interaction against the preserved executable IR.

The producer follows typed source references. This consumer instead checks the
resulting memory fields, complete operation sequences and control-flow edges in
the already retained Word16 program. Neither a digest nor a plausible title is
accepted as evidence that an operation has the declared game meaning.
"""
from __future__ import annotations

import hashlib

from . import door_intents
from .scene_bindings import Witnesses, _bounded, _digest, _need, _operations
from .word16 import _canonical


FORMAT = "fdisbull-zork-door-udl-1"


def _calc(name, *args):
    return {"calc": name, "args": list(args)}


def _var(number, indirect=False):
    return {"indirect_variable" if indirect else "variable": number}


def _write(number, value, indirect=False):
    return {"op": "write_var", "index": number, "value": value, "indirect": indirect}


def _goto(address):
    return {"op": "goto", "target": address}


def _branch(condition, yes, no):
    return {"op": "if", "condition": condition, "then": [yes], "else": [no]}


def _equal(value, *choices):
    return _calc("any", *(_calc("eq", value, choice) for choice in choices))


def _library(name, *args):
    return {"op": "library", "name": name, "args": list(args)}


def _word(base, offset):
    return _calc("mem16", _calc("u16", _calc("add", base, offset)))


def _normal(value):
    """Fold only the constant arithmetic used by original relative jumps."""
    if isinstance(value, list):
        return [_normal(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _normal(item) for key, item in value.items()}
    if set(result) == {"calc", "args"} and all(type(x) is int for x in result["args"]):
        args = result["args"]
        if result["calc"] == "s16" and len(args) == 1:
            return (args[0] & 65535) - (65536 if args[0] & 32768 else 0)
        if result["calc"] == "u16" and len(args) == 1:
            return args[0] & 65535
        if result["calc"] == "add" and len(args) == 2:
            return args[0] + args[1]
        if result["calc"] == "mul" and len(args) == 2:
            return args[0] * args[1]
    return result


def _expect(source, address, operations, reads=()):
    _need(_canonical(_normal(_operations(source, address))) == _canonical(_normal(operations)),
          "Door source operation contradicts recovered intent")
    # Reading variable zero consumes a stack value. Count/order also matter:
    # expression substitution alone would hide an unused extra pop.
    aliases, actual_reads = {}, []

    def resolve(value):
        if isinstance(value, dict):
            if set(value) == {"tmp"}:
                return aliases.get(value["tmp"], value)
            return _normal({key: resolve(item) for key, item in value.items()})
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    for node in source.block(address)["nodes"]:
        if node["op"] == "let":
            aliases[node["name"]] = resolve(node["value"])
        elif node["op"] == "read_var":
            actual_reads.append((resolve(node["index"]), node.get("indirect", False)))
            aliases[node["dest"]] = {"read": len(actual_reads) - 1}
    expected_reads = [(item, False) if type(item) is int else item for item in reads]
    _need(_canonical(actual_reads) == _canonical(expected_reads),
          f"Door source operand consumption changed at {address:#x}")


def _region(source, binding, count, locals_, guards, names):
    _need(binding["locals"] == locals_ and all(type(value) is int for value in binding["locals"]),
          "Door routine local contract changed")
    source.routine(binding["header"], binding["entry"], binding["locals"])
    _bounded(binding["packed"], 1, 65535, "packed door routine")
    _need(binding["packed"] * 2 == binding["header"], "Door routine reference is not a packed routine")
    pcs = binding["source_pcs"]
    _need(isinstance(pcs, list) and len(pcs) == count and pcs[0] == binding["entry"]
          and all(type(pc) is int for pc in pcs), "Door source slice has an invalid boundary")
    for index, pc in enumerate(pcs):
        span = source.block_span(pc)
        _need(type(source.block(pc)["next"]) is int and source.block(pc)["next"] == span[1],
              "Door retained instruction extent changed")
        if index + 1 < len(pcs):
            _need(span[1] == pcs[index + 1], "Door source slice is not contiguous")
    guards.covers(names, [(binding["header"], source.block_span(pcs[-1])[1])])
    return pcs


def _check_program(source, uil, udl, guards):
    names = udl["runtime_guards"]
    callback = _region(source, udl["callback"], 4, [], guards, names)
    helper = _region(source, udl["helper"], 18, [0, 0, 0], guards, names)
    pick = _region(source, udl["selection"], 17, [0] * 6, guards, names)
    action, actions = udl["action_global"], udl["actions"]
    history, door, repeat = udl["history"], udl["door"], udl["repeat"]
    res = udl["resources"]
    opening = res[uil["actions"]["open"]["resource"]]["address"] // 2
    closing = res[uil["actions"]["close"]["resource"]]["address"] // 2
    residual = source.block_span(callback[-1])[1]
    ret = {"op": "return", "value": 1}
    _expect(source, callback[0], [_branch(_equal(_var(action), actions["close"], actions["open"]),
                                        _goto(callback[1]), _goto(residual))], [action])
    _expect(source, callback[1], [_write(history["global"], 1, True)])
    _expect(source, callback[2], [{"op": "call", "target": udl["helper"]["header"],
                                  "args": [door["object"], opening, closing],
                                  "store": 0, "resume": callback[3]}])
    _expect(source, callback[3], [{"op": "pop"}, {"op": "return", "value": {"result": 0}}])

    def print_packed(pc, variable):
        _expect(source, pc, [_library("text.decode", _calc("mul", _var(variable), 2)),
                            {"op": "emit", "value": {"result": 0}}], [variable])

    _expect(source, helper[0], [_branch(_equal(_var(action), actions["open"]),
                                      _goto(helper[1]), _goto(helper[9]))], [action])
    for index, positive, negative in ((1, 2, 5), (10, 11, 14)):
        _expect(source, helper[index], [_library("attribute.test", _var(1), door["attribute"]),
                _branch({"result": 0}, _goto(helper[positive]), _goto(helper[negative]))], [1])
    for index in (2, 14):
        _expect(source, helper[index], [{"op": "call", "target": udl["selection"]["header"],
                "args": [_var(repeat["pointer_global"])], "store": 0,
                "resume": helper[index + 1]}], [repeat["pointer_global"]])
    for index, variable in ((3, 0), (5, 2), (11, 3), (15, 0)):
        print_packed(helper[index], variable)
    for index, destination in ((4, 7), (13, 16)):
        _expect(source, helper[index], [_goto(helper[destination])])
    _expect(source, helper[6], [_library("attribute.set", _var(1), door["attribute"])], [1])
    _expect(source, helper[12], [_library("attribute.clear", _var(1), door["attribute"])], [1])
    for index in (7, 16):
        _expect(source, helper[index], [{"op": "emit", "value": "\n"}])
    for index in (8, 17):
        _expect(source, helper[index], [ret])
    _expect(source, helper[9], [_branch(_equal(_var(action), actions["close"]),
                _goto(helper[10]), {"op": "return", "value": 0})], [action])

    # This complete small helper establishes the uniform remaining-choice
    # domain, both swap writes, immediate cursor wrap and returned resource.
    rows = [
        ([_write(2, _word(_var(1), 0))], [1]),
        ([_write(3, _word(_var(1), 2))], [1]),
        ([_write(2, _calc("u16", _calc("sub", _var(2, True), 1)), True)], [(2, True)]),
        ([_write(1, _calc("u16", _calc("add", _var(1), 2)))], [1]),
        ([_write(0, _calc("u16", _calc("mul", _var(3), 2)))], [3]),
        ([_write(6, _calc("u16", _calc("add", _var(1), _var(0))))], [1, 0]),
        ([_write(0, _calc("u16", _calc("sub", _var(2), _var(3))))], [2, 3]),
        ([{"op": "random", "range": _calc("s16", _var(0))}, _write(4, {"result": 0})], [0]),
        ([_write(5, _word(_var(6), _calc("mul", _var(4), 2)))], [6, 4]),
        ([_write(0, _word(_var(6), 2))], [6]),
        ([{"op": "write_mem", "address": _calc("u16", _calc("add", _var(6), _calc("mul", _var(4), 2))),
          "width": 16, "value": _var(0)}], [6, 4, 0]),
        ([{"op": "write_mem", "address": _calc("u16", _calc("add", _var(6), 2)),
          "width": 16, "value": _var(5)}], [6, 5]),
        ([_write(3, _calc("u16", _calc("add", _var(3, True), 1)), True)], [(3, True)]),
        ([_branch(_equal(_var(3), _var(2)), _goto(pick[14]), _goto(pick[15]))], [3, 2]),
        ([_write(3, 0, True)], []),
        ([{"op": "write_mem", "address": _calc("u16", _calc("add", _var(1), 0)),
          "width": 16, "value": _var(3)}], [1, 3]),
        ([{"op": "return", "value": _var(5)}], [5]),
    ]
    for pc, (operations, reads) in zip(pick, rows, strict=True):
        _expect(source, pc, operations, reads)

    # The field's game meaning is qualified by its consumer as well as its
    # writer. The examination body itself remains residual execution.
    hint = history["consumer_pcs"]
    _need(isinstance(hint, list) and len(hint) == 3 and hint[0] == residual,
          "Initial-hint consumer is not the callback's residual continuation")
    for left, right in zip(hint, hint[1:]):
        _need(source.block_span(left)[1] == right, "Initial-hint consumer slice changed")
    end = source.block_span(hint[-1])[1]
    _expect(source, hint[0], [_branch(_equal(_var(action), history["consumer_action"]),
                _goto(hint[1]), _goto(end))], [action])
    _expect(source, hint[1], [_branch(_calc("eq", _var(history["global"]), 0),
                _goto(hint[2]), _goto(end))], [history["global"]])
    _expect(source, hint[2], [_library("text.decode", history["consumer_text_address"]),
                {"op": "emit", "value": {"result": 0}}, {"op": "emit", "value": "\n"}, ret])
    guards.covers(names, [(hint[0], end)])
    _, reads = source.text(history["consumer_text_address"])
    guards.covers(history["consumer_text_dependencies"], reads)
    guards.covers(names, reads)
    _need(callback[-1] < udl["callback"]["residual_continue"] == residual,
          "Door callback residual continuation changed")
    definitions = {
        "presentation.dismiss_initial_hint": {"source_operations": [callback[1], hint[1]]},
        "door.open": {"source_operations": [helper[index] for index in (1, 6)]},
        "door.close": {"source_operations": [helper[index] for index in (10, 12)]},
        "narration.choose_shuffled_response": {
            "source_operations": pick,
            "order": "draw; selected-slot write; cursor-slot write; cursor advance",
            "repeat_scope": "without replacement within a cycle"},
        "narration.emit": {"source_operations": [helper[index] for index in (3, 5, 7, 11, 15, 16)]},
    }
    _need(_canonical(udl["primitives"]) == _canonical(definitions),
          "Door primitive source correspondence changed")


def validate_binding(source, uil, udl, scene_uil, scene_udl, dispatch_uil, dispatch_udl):
    """Check one closed interaction document and every executable UDL binding."""
    door_intents.validate_uil(uil)
    _need(udl["format"] == FORMAT and udl["source"] == source.ir["source"]
          and udl["initial_image_sha256"] == hashlib.sha256(source.memory).hexdigest(),
          "Door interaction source identity changed")
    if "uil_sha256" in udl:
        _need(udl["uil_sha256"] == _digest(uil), "Door UIL binding digest changed")
    guards = Witnesses(source, udl["witnesses"])
    names = udl["runtime_guards"]
    guards.covers(names, [(8, 16), (24, 26)])
    door, history, repeat, callback = (udl[key] for key in ("door", "history", "repeat", "callback"))
    for record, keys in ((door, ("record", "address")), (history, ("address",)),
                         (repeat, ("pointer_address", "table_address", "cursor_address", "items_address")),
                         (callback, ("cell", "residual_continue"))):
        for key in keys:
            _bounded(record[key], 0, len(source.memory) - 1, "door source " + key)
    _bounded(door["attribute"], 0, 31, "door attribute")
    _bounded(door["mask"], 1, 255, "door attribute mask")
    _bounded(callback["object"], 1, 255, "door callback object")
    _bounded(callback["property"], 1, 31, "door callback property")
    _need(uil["door"] == door["id"] and door["id"] in scene_uil["doors"],
          "Interaction door is absent from the recovered scene world")
    existing = scene_udl["doors"][door["id"]]
    _need(all(door[key] == existing[key] for key in ("object", "record", "attribute", "address", "mask"))
          and door["attribute"] == 11, "Interaction and exit-door state bindings disagree")
    obj = source.object_info(door["object"])
    _need(door["record"] == obj["record"] and door["address"] == obj["record"] + 1
          and door["mask"] == 16, "Interaction open-state field changed")
    guards.covers(names, obj["structure"])
    _need(callback["object"] == door["object"] and callback["property"] == 17
          and obj["properties"].get(17) == (callback["cell"], 2)
          and source._read(callback["cell"], 16) == callback["packed"],
          "Door callback is not the object's qualified action definition")
    guards.covers(names, [(callback["cell"], callback["cell"] + 2)])
    matches = [row for row in dispatch_udl["properties"]
               if row["object"] == door["object"] and row["property"] == 17]
    _need(len(matches) == 1 and matches[0]["handler"] == callback["handler"],
          "Door callback differs from the recovered dispatch link")
    handler = dispatch_udl["handlers"][callback["handler"]]
    _need(handler["routine_header"] == callback["header"] and handler["entry"] == callback["entry"],
          "Door routine entry differs across source bindings")
    for name, number in udl["actions"].items():
        _bounded(number, 0, 255, "door action number")
        _need(any(row["number"] == number and row["id"] == "action." + name
                  for row in dispatch_udl["actions"]), "Door action identity contradicts dispatch")
    _need(set(udl["actions"]) == {"open", "close"}
          and type(udl["return_value"]) is int and udl["return_value"] == 1,
          "Door action or handled-result contract changed")
    action_address = source.global_address(udl["action_global"])
    _need(history["id"] == uil["history_fact"] and type(history["value"]) is int and history["value"] == 1
          and history["address"] == source.global_address(history["global"]),
          "Initial-hint history correspondence changed")
    _need(repeat["id"] == uil["repeat"]["id"]
          and repeat["pointer_address"] == source.global_address(repeat["pointer_global"])
          and source._read(repeat["pointer_address"], 16) == repeat["table_address"],
          "Shared response table pointer correspondence changed")
    table, count = repeat["table_address"], repeat["count"]
    _bounded(count, 1, 32, "qualified response count")
    _bounded(repeat["count_word"], 2, 33, "source response count")
    _bounded(repeat["initial_cursor"], 0, count - 1, "initial response cursor")
    source._bounds(table, (count + 2) * 2, True)
    _need(repeat["count_word"] == count + 1 == source._read(table, 16)
          and repeat["cursor_address"] == table + 2 and repeat["items_address"] == table + 4
          and repeat["initial_cursor"] == source._read(table + 2, 16) == uil["repeat"]["initial_cursor"],
          "Shared response table layout changed")
    resources = repeat["resources"]
    _need(set(resources) == set(uil["repeat"]["resources"]) and len(resources) == count
          and len(set(resources.values())) == count
          and repeat["initial_order"] == uil["repeat"]["initial_order"],
          "Shared response bag resource domain changed")
    for index, identity in enumerate(repeat["initial_order"]):
        _bounded(resources[identity], 1, 65535, "packed response text")
        _need(source._read(table + 4 + index * 2, 16) == resources[identity]
              and resources[identity] * 2 == udl["resources"][identity]["address"],
              "Response bag item is not its qualified packed text reference")
    _need(set(udl["resources"]) == set(uil["resources"]), "Door resource inventories disagree")
    for identity, binding in udl["resources"].items():
        if identity == uil["newline_resource"]:
            _expect(source, binding["source_operation"], [{"op": "emit", "value": "\n"}])
            spans = [source.block_span(binding["source_operation"])]
        else:
            _bounded(binding["address"], 0, len(source.memory) - 1, "door resource address")
            _need(binding["address"] % 2 == 0, "Door text reference must be packed text")
            text, spans = source.text(binding["address"])
            _need(text == uil["resources"][identity], "Door resource differs from source text")
        guards.covers(binding["dependencies"], spans)
        guards.covers(names, spans)
    _check_program(source, uil, udl, guards)

    # Guarded resources must remain immutable during the replacement. The live
    # shuffle bag is deliberately excluded from these byte-equality guards.
    mutable = [(history["address"], history["address"] + 2),
               (door["address"], door["address"] + 1),
               (table + 2, table + (count + 2) * 2)]
    controls = [(action_address, action_address + 2),
                (repeat["pointer_address"], repeat["pointer_address"] + 2), (table, table + 2)]
    for index, (left, right) in enumerate(mutable):
        _need(all(right <= a or left >= b for a, b in mutable[index + 1:] + controls),
              "Door mutable state aliases another semantic input")
        _need(all(right <= udl["witnesses"][name]["start"] or left >= udl["witnesses"][name]["end"]
                  for name in names), "Door mutable state aliases a cached source dependency")
    _need(udl["qualification"]["all_game_intent_recovered"] is False,
          "Door recovery must retain its explicit residual scope")
    return udl
