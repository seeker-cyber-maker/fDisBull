"""Recover R88's finite rule bindings, without executing its address dispatcher.

The generated UIL names the selectable rules and their precedence. UDL alone
contains table cells, variable numbers, packed addresses and source operations.
Resolving a rule's identity does not recover its body: every exported handler
is explicitly residual IR, including OPEN outside the existing mailbox slice.
"""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import re

from .processor import Location, decode_instruction
from .zmachine import decode_v3, decode_ztext, inspect_story_bytes
from .zmachine_processor import ZMachineV3Processor


UIL_FORMAT = "fdisbull-game-dispatch-uil-1"
UDL_FORMAT = "fdisbull-zork-dispatch-udl-1"
SOURCE_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"
_IDENTITY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,191}\Z")
_PROPERTY_ROLES = {17: "action", 2: "container_action", 9: "description"}
# These names are qualified action identities, not new effect implementations.
_KNOWN_ACTION_NAMES = {
    0: "verbose", 1: "brief", 2: "super_brief", 3: "diagnose", 4: "inventory",
    5: "quit", 6: "restart", 7: "restore", 8: "save", 9: "score",
    10: "script", 11: "unscript", 12: "version", 13: "verify",
    14: "lamp_on", 18: "put", 28: "burn", 35: "close", 42: "damage",
    43: "open", 79: "look", 93: "take", 137: "walk",
}
_STAGES = (
    ("actor_action", "actor.action", (), None),
    ("scene_before_action", "actor.scene.action", (), "before_action"),
    ("verb_before_action", "action.before_handler", (), None),
    ("indirect_object_action", "indirect_object.action", ("has_indirect_object",), None),
    ("container_action", "direct_object.parent.container_action",
     ("has_direct_object", "is_not_walk", "direct_object_has_parent"), None),
    ("direct_object_action", "direct_object.action", ("has_direct_object", "is_not_walk"), None),
    ("verb_action", "action.handler", (), None),
)
_PERFORM_SITES = {
    0x57F7: "actor_action", 0x5805: "scene_before_action",
    0x5817: "verb_before_action", 0x5828: "indirect_object_action",
    0x5843: "container_action", 0x585B: "direct_object_action",
    0x5869: "verb_action",
}


def _word(data, address):
    if type(address) is not int or not 0 <= address <= len(data) - 2:
        raise ValueError("Dispatch word lies outside the source image")
    return int.from_bytes(data[address:address + 2], "big")


def _routine(data, packed):
    """Resolve one definition's packed value, not a value sampled from a run."""
    if packed == 0:
        return None
    header = packed * 2
    if not 64 <= header < len(data) or data[header] > 15:
        raise ValueError("Dispatch entry has an invalid routine header")
    entry = header + 1 + 2 * data[header]
    if entry >= len(data):
        raise ValueError("Dispatch routine header is truncated")
    decode_v3(data, entry)
    return {"packed": packed, "routine_header": header, "entry": entry,
            "locals": [_word(data, header + 1 + 2 * i) for i in range(data[header])]}


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unnamed"


def _object_records(data, info, object_ids=None):
    """Decode the qualified v3 record array and retain property layout evidence."""
    base = info["objects"] + 62
    first_property = _word(data, base + 7)
    if first_property <= base or (first_property - base) % 9:
        raise ValueError("Object array has no qualified property-table boundary")
    count = (first_property - base) // 9
    if not 1 <= count <= 255 or first_property > info["static_memory"]:
        raise ValueError("Object array exceeds the v3 object domain")
    if object_ids is not None and (not isinstance(object_ids, dict)
            or set(object_ids) != set(range(1, count + 1))
            or any(not isinstance(x, str) or not _IDENTITY.fullmatch(x) for x in object_ids.values())
            or len(set(object_ids.values())) != count):
        raise ValueError("Object identities must cover the qualified array uniquely")
    records = []
    used = defaultdict(int)
    for number in range(1, count + 1):
        record = base + 9 * (number - 1)
        table = _word(data, record + 7)
        if not first_property <= table < info["static_memory"]:
            raise ValueError("Object property table lies outside dynamic property storage")
        words = data[table]
        end_name = table + 1 + 2 * words
        if end_name >= info["static_memory"]:
            raise ValueError("Object short name exceeds dynamic storage")
        name = decode_ztext(data, table + 1)[0] if words else ""
        slug = _slug(name)
        used[slug] += 1
        identity = (object_ids[number] if object_ids is not None else
                    slug if used[slug] == 1 else f"{slug}_{used[slug]}")
        cursor, previous, properties, headers = end_name, 32, {}, []
        for _ in range(32):
            if cursor >= info["static_memory"]:
                raise ValueError("Unterminated object property list")
            size_byte = data[cursor]
            headers.append(cursor)
            if size_byte == 0:
                break
            prop, size = size_byte & 31, (size_byte >> 5) + 1
            if not 1 <= prop < previous or cursor + 1 + size >= info["static_memory"]:
                raise ValueError("Invalid descending property layout")
            properties[prop] = {"header": cursor, "cell": cursor + 1, "size": size}
            previous, cursor = prop, cursor + 1 + size
        else:
            raise ValueError("Object property list exceeds v3 property count")
        records.append({"number": number, "id": identity, "name": name,
                        "record": record, "property_table": table,
                        "name_length_address": table, "property_headers": headers,
                        "properties": properties})
    return records


def _grammar(data, info, verbs, action_count):
    """Recover syntax associations; recognition filters remain source evidence."""
    start = info["dictionary"]
    header = start + 1 + data[start]
    width = data[header]
    count = abs(int.from_bytes(data[header + 1:header + 3], "big", signed=True))
    if width != 7 or not 1 <= count <= 4096 or header + 3 + width * count > len(data):
        raise ValueError("Unsupported R88 dictionary layout")
    words, prepositions, errors = defaultdict(list), defaultdict(list), []
    for i in range(count):
        address = header + 3 + width * i
        flags = data[address + 4]
        # Noun spellings are outside this selector recovery. In particular the
        # original's two clipped dictionary encodings need no guessed expansion.
        if not flags & (0x40 | 8):
            continue
        try:
            text = decode_ztext(data, address)[0]
        except ValueError as exc:
            errors.append({"address": address, "error": str(exc), "flags": flags})
            continue
        item = {"text": text, "address": address}
        if flags & 0x40:
            number = data[address + (5 if flags & 3 == 1 else 6)]
            words[number].append(item)
        if flags & 8:
            number = data[address + (5 if flags & 3 == 0 else 6)]
            prepositions[number].append(item)
    if errors:
        raise ValueError("A dispatch dictionary spelling could not be recovered")
    result = []
    for number, spellings in sorted(words.items()):
        pointer = verbs + 2 * (255 - number)
        group = _word(data, pointer)
        if not info["static_memory"] <= group < len(data):
            raise ValueError("Grammar group is outside static story memory")
        rows = data[group]
        if not 1 <= rows <= 64 or group + 1 + rows * 8 > len(data):
            raise ValueError("Invalid bounded grammar group")
        for index in range(rows):
            address = group + 1 + index * 8
            row = list(data[address:address + 8])
            if row[-1] >= action_count or row[0] & 3 > 2:
                raise ValueError("Grammar references an invalid action or object count")
            for value in row[1:3]:
                if value and value not in prepositions:
                    raise ValueError("Grammar names an unknown preposition")
            result.append({"verb_number": number, "words": spellings,
                           "pointer": pointer, "group": group, "address": address,
                           "bytes": row, "action": row[-1], "object_count": row[0] & 3,
                           "prepositions": [[x["text"] for x in prepositions.get(value, [])]
                                            for value in row[1:3]],
                           "preposition_words": [prepositions.get(value, []) for value in row[1:3]]})
    return result


def _pseudo_definitions(data, objects, room_parent):
    """Read room-local (dictionary word, callback) pairs used by the parser.

The generated callbacks describe finite setter alternatives. Their bodies and
the parser's rule for choosing a pseudo object remain residual IR.
    """
    result = []
    for obj in objects:
        prop = obj["properties"].get(4)
        if prop is None or data[obj["record"] + 4] != room_parent:
            continue
        if prop["size"] % 4:
            raise ValueError("Pseudo-object definitions must be four-byte pairs")
        for offset in range(0, prop["size"], 4):
            cell = prop["cell"] + offset
            dictionary_word, packed = _word(data, cell), _word(data, cell + 2)
            word = decode_ztext(data, dictionary_word)[0]
            routine = _routine(data, packed)
            if routine is None:
                raise ValueError("Pseudo-object callback must name a routine")
            result.append({"scene": obj["id"], "scene_object": obj["number"], "word": word,
                           "dictionary_word": dictionary_word, "cell": cell,
                           "property_header": prop["header"], "packed": packed})
    return result


def _operand(operand):
    return {"variable" if operand["kind"] == "variable" else "constant": operand["value"]}


def _static_rows(data, seeds, limit=20_000):
    """Discover producer/call pairs only on seeded static paths, never a byte sweep."""
    processor = ZMachineV3Processor(data)
    pending = deque(sorted(seeds))
    queued = set(seeds)
    rows, unknown = {}, []
    while pending:
        if len(rows) >= limit:
            raise ValueError("Dispatch source traversal exceeded its instruction budget")
        address = pending.popleft()
        if address in rows:
            continue
        item = decode_instruction(processor, processor.program,
                                  Location(processor.info.address_space, address))
        if item is None:
            raise ValueError("Dispatch source path is outside the story")
        rows[address] = item.facts
        for edge in item.successors:
            if edge.target is None:
                if edge.kind != "return":
                    unknown.append({"source": address, "kind": edge.kind, "evidence": edge.evidence})
            elif edge.target.offset not in queued:
                queued.add(edge.target.offset)
                pending.append(edge.target.offset)
    return rows, unknown


def _dispatch_sites(rows, table_starts):
    """Compile away known producer-to-stack-to-callee transport chains."""
    previous = {row["end"]: row for row in rows.values()}
    sites = []
    for producer in sorted(rows.values(), key=lambda x: x["offset"]):
        if producer["op"] not in ("get_prop", "loadw") or producer.get("store") != 0:
            continue
        call = rows.get(producer["end"])
        if (not call or call["op"] != "call" or not call["operands"]
                or call["operands"][0] != {"kind": "variable", "value": 0}):
            continue
        operands = producer["operands"]
        start, source_pcs = producer["offset"], [producer["offset"], call["offset"]]
        if producer["op"] == "loadw":
            if operands[0]["kind"] != "variable" or operands[0]["value"] not in table_starts:
                continue
            table = table_starts[operands[0]["value"]]
            selector = {"kind": "table", "table": table,
                        "index": _operand(operands[1]), "pointer_global": operands[0]["value"]}
        else:
            if operands[1]["kind"] == "variable" or operands[1]["value"] not in _PROPERTY_ROLES:
                continue
            obj = _operand(operands[0])
            parent = previous.get(start)
            if (obj == {"variable": 0} and parent and parent["op"] == "get_parent"
                    and parent.get("store") == 0):
                obj = {"parent": _operand(parent["operands"][0])}
                start = parent["offset"]
                source_pcs.insert(0, start)
            selector = {"kind": "property", "object": obj, "property": operands[1]["value"]}
        sites.append({"id": _PERFORM_SITES.get(start, f"source_call_{call['offset']:x}"),
                      "start": start, "call_pc": call["offset"],
                      "return_pc": call["end"], "store": call["store"],
                      "selector": selector,
                      "arguments": [_operand(x) for x in call["operands"][1:]],
                      "source_pcs": source_pcs,
                      "frame_local_count": 7 if start in _PERFORM_SITES else None})
    return sites


def validate_dispatch_uil(uil):
    """Validate address-free rule identities; this does not certify their effects."""
    if (not isinstance(uil, dict) or set(uil) != {"format", "actions", "handlers", "stages",
            "grammar", "selection_semantics", "claim"} or uil.get("format") != UIL_FORMAT):
        raise ValueError("Invalid dispatch UIL document")
    if uil["selection_semantics"] != "ordered_first_handled":
        raise ValueError("Unsupported dispatch selection semantics")
    if uil["claim"] != "resolved_rule_selection_with_explicit_residual_bodies":
        raise ValueError("Invalid dispatch recovery claim")
    handlers = uil["handlers"]
    if not isinstance(handlers, dict) or not 1 <= len(handlers) <= 2048:
        raise ValueError("Dispatch handlers are unbounded or missing")
    for identity, handler in handlers.items():
        if (not isinstance(identity, str) or not _IDENTITY.fullmatch(identity)
                or not isinstance(handler, dict)
                or set(handler) != {"role", "representation", "intent_status"}
                or handler["role"] not in ("action", "preaction", "container_action", "description")
                or handler["representation"] != "low_level_ir"
                or handler["intent_status"] != "unrecovered"):
            raise ValueError("Invalid explicit residual handler")
    actions = uil["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 256:
        raise ValueError("Dispatch actions are unbounded or missing")
    ids = set()
    def words(value, empty=False):
        return (isinstance(value, list) and (empty or value) and len(value) <= 128
                and all(isinstance(x, str) and 0 < len(x) <= 64 for x in value)
                and len(value) == len(set(value)))
    for action in actions:
        if (not isinstance(action, dict) or set(action) != {"id", "handler", "before_handler", "aliases"}
                or not isinstance(action["id"], str) or not _IDENTITY.fullmatch(action["id"])
                or action["id"] in ids or not isinstance(action["handler"], str)
                or action["handler"] not in handlers
                or (action["before_handler"] is not None
                    and (not isinstance(action["before_handler"], str) or action["before_handler"] not in handlers))
                or not words(action["aliases"])):
            raise ValueError("Invalid dispatch action")
        if (handlers[action["handler"]]["role"] != "action"
                or (action["before_handler"] is not None
                    and handlers[action["before_handler"]]["role"] != "preaction")):
            raise ValueError("Dispatch action selects a handler with a different role")
        ids.add(action["id"])
    expected = [{"id": identity, "selector": selector, "requires": list(requires),
                 "event": event} for identity, selector, requires, event in _STAGES]
    if uil["stages"] != expected:
        raise ValueError("Dispatch stages do not preserve first-handled precedence")
    grammar = uil["grammar"]
    if not isinstance(grammar, list) or not 1 <= len(grammar) <= 4096:
        raise ValueError("Dispatch grammar associations are unbounded or missing")
    for row in grammar:
        if (not isinstance(row, dict) or set(row) != {"action", "verbs", "object_count", "prepositions", "status"}
                or not isinstance(row["action"], str) or row["action"] not in ids or not words(row["verbs"])
                or type(row["object_count"]) is not int or row["object_count"] not in (0, 1, 2)
                or not isinstance(row["prepositions"], list) or len(row["prepositions"]) != 2
                or any(not words(x, empty=True) for x in row["prepositions"])
                or row["status"] != "syntax_association_parser_filters_remain_residual"):
            raise ValueError("Invalid partial grammar association")
    return uil


def recover_dispatch(data: bytes, *, object_ids=None):
    """Export the exact R88 action/property bindings as separate UIL and UDL.

The producer derives targets from the source's static tables and property
definitions. It never samples an execution stack or freezes a mutable game's
current action, door, condition or scene to its initial value.
    """
    info = inspect_story_bytes(data)
    if info["sha256"] != SOURCE_SHA256:
        raise ValueError("Dispatch recovery requires the qualified Zork I R88 story")
    global_address = lambda number: info["globals"] + 2 * (number - 16)
    action_start, preaction_start, prep_start, verb_start = (
        _word(data, global_address(number)) for number in (0xAB, 0xAC, 0xAA, 0xAD))
    if (action_start, preaction_start, prep_start, verb_start) != (0x3893, 0x39B7, 0x3ADB, 0x2E53):
        raise ValueError("Qualified dispatch table layout is inconsistent")
    count = (preaction_start - action_start) // 2
    objects = _object_records(data, info, object_ids)
    source_grammar = _grammar(data, info, verb_start, count)
    aliases = defaultdict(set)
    for row in source_grammar:
        aliases[row["action"]].update(word["text"] for word in row["words"])
    if set(aliases) != set(range(count)):
        raise ValueError("Action table has entries without recovered syntax associations")

    uil = {"format": UIL_FORMAT, "actions": [], "handlers": {}, "stages": [], "grammar": [],
           "selection_semantics": "ordered_first_handled",
           "claim": "resolved_rule_selection_with_explicit_residual_bodies"}
    udl = {"format": UDL_FORMAT, "source_sha256": info["sha256"], "actions": [],
           "handlers": {}, "properties": [], "objects": {}, "sites": [],
           "tables": {}, "witnesses": {}, "grammar": source_grammar,
           "grammar_table": {}, "callback_variants": [],
           "all_game_intent_recovered": False}

    def witness(identity, start, end, role, *, mutable=False):
        value = data[start:end]
        if not value or not 0 <= start < end <= info["declared_bytes"]:
            raise ValueError("Dispatch witness is outside the declared image")
        udl["witnesses"][identity] = {"start": start, "end": end, "bytes": value.hex(),
                                     "sha256": hashlib.sha256(value).hexdigest(),
                                     "role": role, "mutable": mutable}
        return identity

    def handler(identity, packed, role):
        routine = _routine(data, packed)
        if routine is None:
            return None
        uil["handlers"][identity] = {"role": role, "representation": "low_level_ir",
                                     "intent_status": "unrecovered"}
        routine["witness"] = witness(f"routine_{routine['routine_header']:x}",
                                    routine["routine_header"], routine["entry"], "routine_header")
        udl["handlers"][identity] = routine
        return identity

    used = set()
    action_ids = {}
    for number in range(count):
        # A lexical rule name is only a selection identity. Variant ordinals
        # distinguish shared spellings without pretending the bodies are known.
        candidates = sorted(aliases[number], key=lambda x: (len(x) == 1, len(x), x))
        name = _KNOWN_ACTION_NAMES.get(number, _slug(candidates[0]))
        identity, suffix = "action." + name, 2
        while identity in used:
            identity = f"action.{name}.variant_{suffix}"
            suffix += 1
        used.add(identity)
        action_ids[number] = identity
        default = handler("residual." + identity, _word(data, action_start + 2 * number), "action")
        if default is None:
            raise ValueError("R88 default action unexpectedly has no routine")
        before = handler("residual.before." + identity,
                         _word(data, preaction_start + 2 * number), "preaction")
        uil["actions"].append({"id": identity, "handler": default,
                               "before_handler": before, "aliases": sorted(aliases[number])})
        udl["actions"].append({"number": number, "id": identity, "handler": default,
                               "before_handler": before, "action_cell": action_start + 2 * number,
                               "preaction_cell": preaction_start + 2 * number})
    for row in source_grammar:
        uil["grammar"].append({"action": action_ids[row["action"]],
                               "verbs": sorted(x["text"] for x in row["words"]),
                               "object_count": row["object_count"], "prepositions": row["prepositions"],
                               "status": "syntax_association_parser_filters_remain_residual"})
    uil["stages"] = [{"id": identity, "selector": selector, "requires": list(requires), "event": event}
                     for identity, selector, requires, event in _STAGES]
    for name, start, end, number in (("actions", action_start, preaction_start, 0xAB),
                                    ("preactions", preaction_start, prep_start, 0xAC)):
        udl["tables"][name] = {"start": start, "end": end, "count": count,
                               "pointer_global": number, "pointer_address": global_address(number),
                               "pointer_value": start,
                               "witness": witness(name, start, end, "static_dispatch_table"),
                               "pointer_witness": witness(name + "_pointer", global_address(number),
                                                           global_address(number) + 2, "mutable_table_pointer", mutable=True)}
    verb_count = len({row["verb_number"] for row in source_grammar})
    if {row["verb_number"] for row in source_grammar} != set(range(256 - verb_count, 256)):
        raise ValueError("Grammar table does not have a contiguous qualified domain")
    udl["grammar_table"] = {
        "start": verb_start, "count": verb_count, "pointer_global": 0xAD,
        "pointer_address": global_address(0xAD),
        "witness": witness("grammar_table", verb_start, verb_start + 2 * verb_count,
                           "static_grammar_pointer_table"),
        "pointer_witness": witness("grammar_pointer", global_address(0xAD), global_address(0xAD) + 2,
                                   "mutable_grammar_pointer", mutable=True),
    }
    roots = {info["initial_pc"]}
    for obj in objects:
        guards = [witness(f"object_{obj['number']}_pointer", obj["record"] + 7,
                          obj["record"] + 9, "property_table_pointer", mutable=True),
                  witness(f"object_{obj['number']}_name_length", obj["property_table"],
                          obj["property_table"] + 1, "property_layout", mutable=True)]
        for address in obj["property_headers"]:
            guards.append(witness(f"property_header_{address:x}", address, address + 1,
                                  "property_layout", mutable=True))
        udl["objects"][obj["id"]] = {"number": obj["number"], "record": obj["record"],
                                      "property_table": obj["property_table"], "layout_witnesses": guards}
        for number, role in _PROPERTY_ROLES.items():
            prop = obj["properties"].get(number)
            if prop is not None and prop["size"] != 2:
                raise ValueError("Callback property must have a full packed word")
            cell = prop["cell"] if prop else info["objects"] + 2 * (number - 1)
            packed = _word(data, cell)
            identity = handler(f"residual.callback.{obj['id']}.{role}", packed, role)
            udl["properties"].append({"object": obj["number"], "object_id": obj["id"],
                                      "property": number, "role": role, "cell": cell,
                                      "size": 2, "uses_default": prop is None,
                                      "initial_packed": packed, "handler": identity,
                                      "witness": witness(f"callback_value_{cell:x}", cell, cell + 2,
                                                         "mutable_callback_binding", mutable=True)})
        # Three-byte direction properties contain an explicit exit callback.
        # They seed discovery here; scene semantics and bindings belong to the
        # scene producer, so this module does not duplicate those rules.
        for number, prop in obj["properties"].items():
            if number >= 19 and prop["size"] == 3:
                routine = _routine(data, _word(data, prop["cell"]))
                if routine is not None:
                    roots.add(routine["entry"])
    # The pseudo-object's ACTION property is deliberately rewritten from the
    # current room's PSEUDO pairs. Retain those finite definitions instead of
    # treating every legitimate rewrite as an unknown address.
    pseudo_source = witness("pseudo_callback_setter", 0x6990, 0x69C3,
                            "pseudo_pair_lookup_and_callback_assignment")
    pseudo_by_packed = {}
    pseudo_identities = set()
    for definition in _pseudo_definitions(data, objects, 82):
        packed = definition["packed"]
        if packed not in pseudo_by_packed:
            name = "residual.pseudo." + _slug(definition["word"])
            base_name, suffix = name, 2
            while name in pseudo_identities:
                name = f"{base_name}.variant_{suffix}"
                suffix += 1
            pseudo_identities.add(name)
            pseudo_by_packed[packed] = handler(name, packed, "action")
        cell = definition["cell"]
        udl["callback_variants"].append({
            "target": {"object": 13}, "property": 17, "packed": packed,
            "handler": pseudo_by_packed[packed], "setter_pc": 0x69BE,
            "origin": {"kind": "room_pseudo_property_pair", "property": 4,
                       **{key: definition[key] for key in ("scene", "scene_object", "word", "dictionary_word", "cell", "property_header")}},
            "source_pcs": [0x6990, 0x6998, 0x699B, 0x699F, 0x69A6, 0x69AA,
                           0x69AE, 0x69B2, 0x69B6, 0x69BA, 0x69BE],
            "source_witnesses": [pseudo_source,
                witness(f"pseudo_pair_{cell:x}", cell, cell + 4, "pseudo_callback_definition", mutable=True)],
        })
    # DEAD-FUNCTION is also an ordinary finite rule choice. Its implementation
    # remains residual; no player-death behavior is inferred from this binding.
    death_assignment = decode_v3(data, 0x10872)
    if (death_assignment["op"] != "put_prop" or death_assignment["operands"][:2] != [
            {"kind": "variable", "value": 0x7F}, {"kind": "small", "value": 17}]
            or death_assignment["operands"][2]["kind"] == "variable"):
        raise ValueError("Actor callback assignment does not match its source definition")
    death_packed = death_assignment["operands"][2]["value"]
    death_handler = handler("residual.actor.dead_action", death_packed, "action")
    udl["callback_variants"].append({
        "target": {"variable": 0x7F}, "property": 17, "packed": death_packed,
        "handler": death_handler, "setter_pc": 0x10872,
        "origin": {"kind": "literal_callback_assignment"},
        "source_pcs": [0x10872],
        "source_witnesses": [witness("actor_dead_callback_setter", 0x10872, 0x10878,
                                     "literal_callback_assignment")],
    })
    roots.update(value["entry"] for value in udl["handlers"].values())
    rows, unresolved = _static_rows(data, roots)
    sites = _dispatch_sites(rows, {0xAB: "actions", 0xAC: "preactions"})
    if not set(_PERFORM_SITES).issubset({site["start"] for site in sites}):
        raise ValueError("Qualified dispatcher source patterns were not found")
    for site in sites:
        site["witness"] = witness(f"dispatch_site_{site['start']:x}", site["start"],
                                  site["return_pc"], "source_dispatch_operations")
        site["source_operations"] = [decode_v3(data, address) for address in site["source_pcs"]]
    udl["sites"] = sites
    udl["discovery"] = {"root_count": len(roots), "instruction_count": len(rows),
                         "worklist_drained": True, "unresolved_transfers": unresolved,
                         "all_runtime_targets_proven": False}
    udl["perform"] = {"routine_header": 0x577C, "entry": 0x578B, "local_count": 7,
                       "action_local": 1, "direct_object_local": 2, "indirect_object_local": 3,
                       "result_local": 4, "actor_global": 0x7F, "scene_global": 0x10,
                       "walk_action": action_ids[137], "walk_action_number": 137}
    udl["compatibility"] = {
        "static_tables": "immutable_by_story_memory_contract",
        "mutable_pointers_and_properties": "compare_live_binding_before_replacement",
        "changed_binding": "explicit_residual_ir_fallback",
        "handler_bodies": "residual_ir; existing separately_qualified_intents_may_replace_subregions",
        "parser": "original_filters_and_reference_resolution_remain_residual",
    }
    validate_dispatch_uil(uil)
    return {"uil": uil, "udl": udl}
