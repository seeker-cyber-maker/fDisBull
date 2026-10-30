"""Recover one door interaction from its already-resolved source definitions.

This bounded recognizer follows the kitchen-window callback's typed references
to OPEN-CLOSE and its shuffle-bag helper. It qualifies the selected operations;
it is not a general decompiler. Other callback branches, parser admission and
the scheduler remain residual. Source coordinates and implementation details
belong to UDL, while UIL describes the requested door state and narration.
"""
from __future__ import annotations

import copy
import hashlib

from .zmachine import decode_ztext
from .zork_intents import canonical_digest, verify_mapped_instruction, verify_witness
from .zork_scenes import _Evidence, _routine, _word


UIL_FORMAT = "fdisbull-door-interaction-uil-1"
UDL_FORMAT = "fdisbull-zork-door-udl-1"
DOOR = "kitchen_window"
HISTORY = "initial_ajar_hint_dismissed"
REPEAT = "already_requested_state"


def _int(value, low, high, role):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid window " + role)
    return value


def _value(row, index, variable=False):
    try:
        operand = row["operands"][index]
        if (operand["kind"] == "variable") != variable:
            raise ValueError("Window source operand has the wrong reference role")
        return _int(operand["value"], 0, 255 if variable else 65535, "operand")
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Window source operand is missing") from exc


def _expect(row, op, operands=(), *, store=None, branch=False):
    """Compare operand roles as well as values; constants are never variables."""
    if (row["op"] != op or len(row["operands"]) != len(operands)
            or row.get("store") != store or ("branch" in row) != branch):
        raise ValueError("Unsupported window source operation: " + op)
    for index, (variable, value) in enumerate(operands):
        if _value(row, index, variable) != value:
            raise ValueError("Window source operand contradicts " + op)


def _branch(row, *, when, target=None, returns=None):
    branch = row.get("branch", {})
    if (branch.get("when") is not when or branch.get("target") != target
            or branch.get("return") is not returns):
        raise ValueError("Window source branch contradicts the recovered rule")


def _jump(row, target):
    _expect(row, "jump", ((False, _value(row, 0)),))
    offset = _value(row, 0)
    signed = offset if offset < 32768 else offset - 65536
    if row["end"] + signed - 2 != target:
        raise ValueError("Window source jump leaves its qualified continuation")


def _rows(data, program, start, count):
    rows, cursor = [], start
    for _ in range(count):
        row = verify_mapped_instruction(data, program, cursor)
        if row["end"] <= cursor or row["end"] - start > 4096:
            raise ValueError("Window source slice exceeds its byte budget")
        rows.append(row)
        cursor = row["end"]
    return rows


def _function(data, program, packed, locals_count):
    routine = _routine(data, packed)
    if routine["locals"] != [0] * locals_count:
        raise ValueError("Window source routine has unsupported initial locals")
    expected = {"entry": routine["entry"], "locals": routine["locals"],
                "guard": data[routine["header"]:routine["entry"]].hex()}
    if program.get("functions", {}).get(str(routine["header"])) != expected:
        raise ValueError("Window routine does not match retained IR")
    return {key: routine[key] for key in ("packed", "header", "entry", "locals")}


def _callback_layout(data, record, dynamic_end, evidence, guards):
    """Read only this object's bounded property list, without a whole-game scan."""
    table = _word(data, record + 7)
    if not record + 9 <= table < dynamic_end:
        raise ValueError("Window property table overlaps its record or exceeds memory")
    guards.append(evidence.add("window-object-pointer", record + 7, record + 9,
                               "window property-table identity"))
    guards.append(evidence.add("window-name-length", table, table + 1,
                               "window property-list boundary"))
    cursor = table + 1 + 2 * data[table]
    if cursor >= dynamic_end:
        raise ValueError("Window object name exceeds dynamic memory")
    if data[table] and decode_ztext(data, table + 1)[1] != cursor:
        raise ValueError("Window object short-name extent is inconsistent")
    previous, found = 32, None
    for _ in range(32):
        if cursor >= dynamic_end:
            raise ValueError("Window property list is truncated")
        header = data[cursor]
        guards.append(evidence.add(f"window-property-{cursor:x}", cursor, cursor + 1,
                                   "window property layout"))
        if not header:
            if found is None:
                raise ValueError("Window action property is absent")
            return table, found
        number, size = header & 31, (header >> 5) + 1
        if not 1 <= number < previous or cursor + 1 + size > dynamic_end:
            raise ValueError("Window properties are not bounded and descending")
        if number == 17:
            if size != 2:
                raise ValueError("Window action property must contain a packed word")
            found = cursor + 1
        previous, cursor = number, cursor + 1 + size
    raise ValueError("Window property-list budget exceeded")


def recover_window(data, program, scene_uil, scene_udl, dispatch):
    """Return a deterministic, source-qualified OPEN/CLOSE definition.

    ``dispatch`` is the existing ``recover_dispatch`` result, including its UIL
    and UDL. Nothing supplied by the caller is mutated. Unsupported shapes raise
    rather than silently claiming a recovered interaction. Runtime admission can
    subsequently retain changed or out-of-domain live states as residual IR.
    """
    try:
        return _recover(data, program, scene_uil, scene_udl, dispatch)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Incomplete window source definitions") from exc


def verify_window(data, program, uil, udl):
    """Check the producer's narrow source binding without rebuilding scenes.

    This is provenance and correspondence validation, not an independent proof
    of intent. The standalone player separately checks every selected source
    operation and branch against the semantic contract before execution.
    """
    try:
        if (uil["format"] != UIL_FORMAT or udl["format"] != UDL_FORMAT
                or udl["source"] != program["source"]
                or not isinstance(data, bytes) or program["memory"]["initial"] != data.hex()
                or udl["initial_image_sha256"] != hashlib.sha256(data).hexdigest()
                or udl["uil_sha256"] != canonical_digest(uil)):
            raise ValueError("Window document/source identity changed")
        witnesses = udl["witnesses"]
        if not isinstance(witnesses, dict) or not 1 <= len(witnesses) <= 1024:
            raise ValueError("Window source witnesses exceed their bounded inventory")
        for witness in witnesses.values():
            verify_witness(data, witness)
        guards = udl["runtime_guards"]
        if (not isinstance(guards, list) or not guards or len(guards) != len(set(guards))
                or any(name not in witnesses for name in guards)):
            raise ValueError("Window live guard inventory changed")
        count = 0
        for name, size, locals_count in (("callback", 4, 0), ("helper", 18, 3), ("selection", 17, 6)):
            binding = udl[name]
            routine = _function(data, program, binding["packed"], locals_count)
            if any(binding[key] != value for key, value in routine.items()):
                raise ValueError("Window routine correspondence changed")
            rows = _rows(data, program, binding["entry"], size)
            if (binding["source_operations"] != rows
                    or binding["source_pcs"] != [row["offset"] for row in rows]):
                raise ValueError("Window source operation inventory changed")
            count += len(rows)
        consumer = udl["history"]["consumer_pcs"]
        rows = _rows(data, program, udl["callback"]["source_operations"][-1]["end"], 3)
        if consumer != [row["offset"] for row in rows]:
            raise ValueError("Window history consumer correspondence changed")
        if set(udl["resources"]) != set(uil["resources"]):
            raise ValueError("Window resource inventory changed")
        for name, binding in udl["resources"].items():
            if name == uil["newline_resource"]:
                if (uil["resources"][name] != "\n"
                        or verify_mapped_instruction(data, program, binding["source_operation"])["op"] != "new_line"):
                    raise ValueError("Window newline correspondence changed")
            elif decode_ztext(data, binding["address"])[0] != uil["resources"][name]:
                raise ValueError("Window narrative resource changed")
            if any(dependency not in witnesses for dependency in binding["dependencies"]):
                raise ValueError("Window resource dependency is absent")
        if udl["qualification"]["all_game_intent_recovered"] is not False:
            raise ValueError("Window residual scope must stay explicit")
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Incomplete window binding") from exc
    return {"uil_sha256": udl["uil_sha256"], "replaced_instructions": count,
            "witnesses": len(witnesses), "runtime_guards": len(guards)}


def _recover(data, program, scene_uil, scene_udl, dispatch):
    if not isinstance(data, bytes) or len(data) < 64:
        raise ValueError("Window recovery requires immutable source bytes")
    if program["memory"]["initial"] != data.hex():
        raise ValueError("Window source image differs from retained IR")
    dynamic_end = _int(program["memory"]["writable_end"], 64, len(data), "dynamic extent")
    for key, offset in (("objects", 10), ("globals", 12), ("abbreviations", 24)):
        if program["layout"][key] != _word(data, offset):
            raise ValueError("Window source layout differs from retained IR")
    if _word(data, 14) != dynamic_end:
        raise ValueError("Window source dynamic extent differs from its header")
    if scene_udl["source"] != program["source"]:
        raise ValueError("Window scene definition belongs to another source")
    image_sha = hashlib.sha256(data).hexdigest()
    if scene_udl["initial_image_sha256"] != image_sha:
        raise ValueError("Window scene image binding changed")
    if DOOR not in scene_uil["doors"]:
        raise ValueError("Named kitchen window is absent from recovered scenes")
    door = copy.deepcopy(scene_udl["doors"][DOOR])
    number = _int(door["object"], 1, 255, "door object")
    record = program["layout"]["objects"] + 62 + 9 * (number - 1)
    if door["record"] != record or record + 9 > dynamic_end:
        raise ValueError("Window door record does not match the object layout")
    attribute = _int(door["attribute"], 0, 31, "open attribute")
    if (attribute != 11 or door["address"] != record + attribute // 8
            or door["mask"] != 128 >> (attribute % 8)):
        raise ValueError("Window open field does not match the object layout")
    evidence = _Evidence(data, program["layout"]["abbreviations"])
    guards = [evidence.add("window-layout", 8, 16, "dictionary/object/global/dynamic memory layout"),
              evidence.add("window-abbreviations", 24, 26, "text abbreviation root")]
    table, cell = _callback_layout(data, record, dynamic_end, evidence, guards)
    source_dispatch = dispatch["udl"]
    properties = [item for item in source_dispatch["properties"]
                  if item["object"] == number and item["property"] == 17]
    if len(properties) != 1:
        raise ValueError("Window callback association is absent or ambiguous")
    prop = properties[0]
    if (prop["object_id"] != DOOR or prop["cell"] != cell or prop["size"] != 2
            or prop["uses_default"] is not False or prop["initial_packed"] != _word(data, cell)):
        raise ValueError("Window callback association contradicts its property")
    obj = source_dispatch["objects"][DOOR]
    if (obj["number"], obj["record"], obj["property_table"]) != (number, record, table):
        raise ValueError("Window dispatch object association changed")
    guards.append(evidence.add("window-callback-value", cell, cell + 2,
                               "admitted live window callback identity"))
    callback = _function(data, program, prop["initial_packed"], 0)
    handler = source_dispatch["handlers"][prop["handler"]]
    if any(handler[key] != callback[target] for key, target in
           (("packed", "packed"), ("routine_header", "header"), ("entry", "entry"), ("locals", "locals"))):
        raise ValueError("Window dispatch handler contradicts its routine")
    actions = {}
    for name in ("open", "close"):
        matches = [item for item in source_dispatch["actions"] if item["id"] == "action." + name]
        if len(matches) != 1:
            raise ValueError("Window action identity is absent or ambiguous")
        actions[name] = _int(matches[0]["number"], 0, 255, "action number")
    if actions["open"] == actions["close"]:
        raise ValueError("Window action identities are not distinct")

    c = _rows(data, program, callback["entry"], 4)
    action_global = _int(_value(c[0], 0, True), 16, 255, "action global")
    history_global = _int(_value(c[1], 0), 16, 255, "history global")
    helper_packed, opening_text, closing_text = (_value(c[2], index) for index in (0, 2, 3))
    _expect(c[0], "je", ((True, action_global), (False, actions["close"]),
                         (False, actions["open"])), branch=True)
    _branch(c[0], when=False, target=c[-1]["end"])
    _expect(c[1], "store", ((False, history_global), (False, 1)))
    _expect(c[2], "call", ((False, helper_packed), (False, number),
                           (False, opening_text), (False, closing_text)), store=0)
    _expect(c[3], "ret_popped")
    helper = _function(data, program, helper_packed, 3)
    h = _rows(data, program, helper["entry"], 18)
    selection_packed = _value(h[2], 0)
    pointer_global = _int(_value(h[2], 1, True), 16, 255, "response pointer global")
    expected_helper = (
        ("je", ((True, action_global), (False, actions["open"])), None, True),
        ("test_attr", ((True, 1), (False, attribute)), None, True),
        ("call", ((False, selection_packed), (True, pointer_global)), 0, False),
        ("print_paddr", ((True, 0),), None, False),
        None,
        ("print_paddr", ((True, 2),), None, False),
        ("set_attr", ((True, 1), (False, attribute)), None, False),
        ("new_line", (), None, False), ("rtrue", (), None, False),
        ("je", ((True, action_global), (False, actions["close"])), None, True),
        ("test_attr", ((True, 1), (False, attribute)), None, True),
        ("print_paddr", ((True, 3),), None, False),
        ("clear_attr", ((True, 1), (False, attribute)), None, False),
        None,
        ("call", ((False, selection_packed), (True, pointer_global)), 0, False),
        ("print_paddr", ((True, 0),), None, False),
        ("new_line", (), None, False), ("rtrue", (), None, False),
    )
    for row, expected in zip(h, expected_helper):
        if expected is not None:
            op, operands, store, branch = expected
            _expect(row, op, operands, store=store, branch=branch)
    _branch(h[0], when=False, target=h[9]["offset"])
    _branch(h[1], when=False, target=h[5]["offset"])
    _branch(h[9], when=False, returns=False)
    _branch(h[10], when=False, target=h[14]["offset"])
    _jump(h[4], h[7]["offset"])
    _jump(h[13], h[16]["offset"])

    selection = _function(data, program, selection_packed, 6)
    s = _rows(data, program, selection["entry"], 17)
    expected_selection = (
        ("loadw", ((True, 1), (False, 0)), 2),
        ("loadw", ((True, 1), (False, 1)), 3),
        ("dec", ((False, 2),), None),
        ("add", ((True, 1), (False, 2)), 1),
        ("mul", ((True, 3), (False, 2)), 0),
        ("add", ((True, 1), (True, 0)), 6),
        ("sub", ((True, 2), (True, 3)), 0),
        ("random", ((True, 0),), 4),
        ("loadw", ((True, 6), (True, 4)), 5),
        ("loadw", ((True, 6), (False, 1)), 0),
        ("storew", ((True, 6), (True, 4), (True, 0)), None),
        ("storew", ((True, 6), (False, 1), (True, 5)), None),
        ("inc", ((False, 3),), None),
        ("je", ((True, 3), (True, 2)), None),
        ("store", ((False, 3), (False, 0)), None),
        ("storew", ((True, 1), (False, 0), (True, 3)), None),
        ("ret", ((True, 5),), None),
    )
    for index, (row, (op, operands, store)) in enumerate(zip(s, expected_selection)):
        _expect(row, op, operands, store=store, branch=index == 13)
    _branch(s[13], when=False, target=s[15]["offset"])

    # The flag name requires its consumer, not only an unexplained STORE.
    hint = _rows(data, program, c[-1]["end"], 3)
    hint_action = _value(hint[0], 1)
    if hint_action in actions.values():
        raise ValueError("Window hint action conflicts with OPEN/CLOSE")
    _expect(hint[0], "je", ((True, action_global), (False, hint_action)), branch=True)
    _expect(hint[1], "jz", ((True, history_global),), branch=True)
    _expect(hint[2], "print_ret")
    _branch(hint[0], when=False, target=hint[-1]["end"])
    _branch(hint[1], when=False, target=hint[-1]["end"])

    global_base = program["layout"]["globals"]
    global_address = lambda number_: global_base + 2 * (number_ - 16)
    history_address, pointer_address = map(global_address, (history_global, pointer_global))
    if len({action_global, history_global, pointer_global}) != 3:
        raise ValueError("Window source state roles alias")
    for address in (global_address(action_global), history_address, pointer_address):
        if not 64 <= address <= dynamic_end - 2:
            raise ValueError("Window global is outside writable memory")
    bag = _word(data, pointer_address)
    if not 64 <= bag <= dynamic_end - 10 or _word(data, bag) != 4:
        raise ValueError("Window response bag does not have three bounded entries")
    cursor = _int(_word(data, bag + 2), 0, 2, "response cursor")
    packed_resources = [_word(data, bag + 4 + 2 * index) for index in range(3)]
    if len(set(packed_resources)) != 3 or 0 in packed_resources:
        raise ValueError("Window response resources must be distinct non-null references")
    if min(opening_text, closing_text) <= 0:
        raise ValueError("Window output has a null text reference")
    resource_ids = ["window.repeat." + word for word in ("first", "second", "third")]
    for name, packed in [("window.opened", opening_text), ("window.closed", closing_text),
                         *zip(resource_ids, packed_resources)]:
        if not 64 <= 2 * packed < len(data):
            raise ValueError("Window packed text lies outside the source image")
        evidence.text(name, 2 * packed)
    evidence.resources["newline"] = "\n"
    evidence.resource_bindings["newline"] = {
        "source_operation": h[7]["offset"], "dependencies": []}
    hint_dependencies = evidence.text_dependencies(hint[2]["text_offset"])
    for name, routine, rows in (("window-callback", callback, c),
                                 ("window-helper", helper, h),
                                 ("window-selection", selection, s)):
        guards.append(evidence.add(name, routine["header"], rows[-1]["end"],
                                   "qualified window semantic source operations"))
        routine["source_pcs"] = [row["offset"] for row in rows]
        routine["source_operations"] = rows
    guards.append(evidence.add("window-hint-consumer", hint[0]["offset"], hint[-1]["end"],
                               "initial-hint state consumer; execution stays residual"))
    guards.append(evidence.add("window-response-pointer", pointer_address, pointer_address + 2,
                               "admitted shared response-table identity"))
    guards.append(evidence.add("window-response-count", bag, bag + 2,
                               "qualified response-table length"))
    initial_witness = evidence.add("window-response-initial", bag + 2, bag + 10,
                                  "initial mutable cursor and item ordering; never a live byte guard")
    guards.extend(name for name in evidence.witnesses
                  if name.startswith(("text-", "abbreviation-")))
    guards = sorted(set(guards))
    mutable_ranges = ((history_address, history_address + 2),
                      (door["address"], door["address"] + 1), (bag + 2, bag + 10))
    if any(left < other_right and other_left < right
           for index, (left, right) in enumerate(mutable_ranges)
           for other_left, other_right in mutable_ranges[index + 1:]):
        raise ValueError("Window mutable semantic fields overlap")
    action_address = global_address(action_global)
    if any(left < action_address + 2 and action_address < right for left, right in mutable_ranges):
        raise ValueError("Window mutable state aliases its action input")
    if any(left < evidence.witnesses[name]["end"] and evidence.witnesses[name]["start"] < right
           for left, right in mutable_ranges for name in guards):
        raise ValueError("Window mutable state aliases a guarded dependency")
    for key in ("newline",):
        evidence.resource_bindings[key]["dependencies"] = ["window-helper"]
    callback.update({"handler": prop["handler"], "object": number, "property": 17,
                     "cell": cell, "residual_continue": c[-1]["end"]})
    uil = {"format": UIL_FORMAT, "id": "zork1.kitchen_window.open_close", "door": DOOR,
           "history_fact": HISTORY, "resources": evidence.resources,
           "actions": {"open": {"is_open": True, "resource": "window.opened"},
                       "close": {"is_open": False, "resource": "window.closed"}},
           "repeat": {"id": REPEAT, "resources": resource_ids,
                      "initial_order": list(resource_ids), "initial_cursor": cursor},
           "newline_resource": "newline"}
    udl = {"format": UDL_FORMAT, "source": copy.deepcopy(program["source"]),
           "initial_image_sha256": image_sha, "callback": callback, "helper": helper,
           "selection": selection,
           "door": {"id": DOOR, **{key: door[key] for key in
                                    ("object", "record", "attribute", "address", "mask")}},
           "history": {"id": HISTORY, "global": history_global, "address": history_address,
                       "value": 1, "consumer_action": hint_action,
                       "consumer_pcs": [row["offset"] for row in hint],
                       "consumer_text_address": hint[2]["text_offset"],
                       "consumer_text_dependencies": hint_dependencies},
           "action_global": action_global, "actions": actions, "return_value": 1,
           "repeat": {"id": REPEAT, "pointer_global": pointer_global,
                      "pointer_address": pointer_address, "table_address": bag,
                      "count_word": 4, "count": 3, "cursor_address": bag + 2,
                      "items_address": bag + 4, "resources": dict(zip(resource_ids, packed_resources)),
                      "initial_order": list(resource_ids), "initial_cursor": cursor,
                      "initial_witness": initial_witness},
           "resources": evidence.resource_bindings, "witnesses": evidence.witnesses,
           "runtime_guards": guards,
           "primitives": {
               "presentation.dismiss_initial_hint": {"source_operations": [c[1]["offset"], hint[1]["offset"]]},
               "door.open": {"source_operations": [h[index]["offset"] for index in (1, 6)]},
               "door.close": {"source_operations": [h[index]["offset"] for index in (10, 12)]},
               "narration.choose_shuffled_response": {"source_operations": selection["source_pcs"],
                                        "order": "draw; selected-slot write; cursor-slot write; cursor advance",
                                        "repeat_scope": "without replacement within a cycle"},
               "narration.emit": {"source_operations": [h[index]["offset"] for index in (3, 5, 7, 11, 15, 16)]},
           },
           "qualification": {
               "method": "resolved callback; bounded consumer shapes; typed literal calls; live-state bindings",
               "replaced_instruction_count": len(c) + len(h) + len(s),
               "consumer_evidence_instruction_count": len(hint),
               "routine_count": 3, "source_instruction_budget": 42,
               "open_close_recovered": True, "other_callback_branches_recovered": False,
               "all_game_intent_recovered": False,
               "turns": "existing turn-count primitive and residual scheduler; no local turn increment",
               "residual": ["parser_and_scope", "stage_admission", "other_window_verbs",
                            "examination_consumer", "scheduler_and_background_events",
                            "unqualified_live_bindings_or_output_streams"],
           }}
    udl["uil_sha256"] = canonical_digest(uil)
    return {"uil": uil, "udl": udl}
