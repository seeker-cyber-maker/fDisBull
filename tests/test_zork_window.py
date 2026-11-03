"""Authored, relocatable door source fixtures; no original game text or bytes."""
from __future__ import annotations

import copy
import hashlib

import pytest

from fdisbull.zmachine import decode_v3
from fdisbull.zork_intents import canonical_digest
from fdisbull.zork_uil import FORMAT as IR_FORMAT, lower_instruction
from fdisbull.zork_window import recover_window, verify_window


def _word(data, address, value):
    data[address:address + 2] = value.to_bytes(2, "big")


def _text(text):
    values = [0 if char == " " else ord(char) - ord("a") + 6 for char in text]
    values.extend([5] * (-len(values) % 3))
    words = [(values[i] << 10) | (values[i + 1] << 5) | values[i + 2]
             for i in range(0, len(values), 3)]
    words[-1] |= 0x8000
    return b"".join(word.to_bytes(2, "big") for word in words)


class _Assembler:
    """Encode this authored program independently of the recovery recognizer."""

    TWO = {"je": 1, "test_attr": 10, "set_attr": 11, "clear_attr": 12,
           "store": 13, "loadw": 15, "add": 20, "sub": 21, "mul": 22}
    ONE = {"jz": 0, "inc": 5, "dec": 6, "ret": 11, "jump": 12, "print_paddr": 13}
    ZERO = {"rtrue": 0, "rfalse": 1, "print_ret": 3, "ret_popped": 8, "new_line": 11}
    VAR = {"call": 0, "storew": 1, "random": 7}

    def __init__(self, data, address):
        self.data, self.cursor = data, address
        self.pcs, self.labels, self.fixups = [], {}, []

    def label(self, name):
        self.labels[name] = self.cursor

    def emit(self, op, args=(), *, store=None, branch=None, text=None):
        start = self.cursor
        self.pcs.append(start)
        kinds = [2 if kind == "v" else 0 if kind == "w" or value > 255 else 1
                 for kind, value in args]
        raw = bytearray()
        if op in self.TWO or op in self.VAR:
            raw.append((0xC0 + self.TWO[op]) if op in self.TWO else (0xE0 + self.VAR[op]))
            types = kinds + [3] * (4 - len(kinds))
            raw.append(sum(value << (6 - 2 * index) for index, value in enumerate(types)))
        elif op in self.ONE:
            assert len(args) == 1
            raw.append(0x80 + 0x10 * kinds[0] + self.ONE[op])
        else:
            assert not args
            raw.append(0xB0 + self.ZERO[op])
        for (_, value), kind in zip(args, kinds):
            raw.extend(value.to_bytes(2 if kind == 0 else 1, "big"))
        if store is not None:
            raw.append(store)
        if branch is not None:
            when, target = branch
            self.fixups.append((start + len(raw), when, target))
            raw.extend(b"\x00\x00")
        if text is not None:
            raw.extend(_text(text))
        self.data[start:start + len(raw)] = raw
        self.cursor += len(raw)
        return start

    def jump(self, target):
        pc = self.emit("jump", (("w", 0),))
        self.fixups.append((pc + 1, None, target))

    def finish(self):
        for address, when, target in self.fixups:
            if type(target) is bool:
                value = int(target)
            else:
                value = self.labels[target] - address
            if when is None:
                _word(self.data, address, value & 65535)
            else:
                _word(self.data, address, (0x8000 if when else 0) | (value & 0x3FFF))


def make_window_fixture(shift=0):
    """Source references move together; no original routine PC is an input."""
    data = bytearray(0x1400 + shift)
    data[0] = 3
    objects, globals_, abbreviations, dynamic_end = (value + shift for value in (0x100, 0x300, 0x700, 0x800))
    for offset, value in ((8, 0x680 + shift), (10, objects), (12, globals_),
                          (14, dynamic_end), (24, abbreviations)):
        _word(data, offset, value)
    number, record, property_table = 3, objects + 62 + 18, 0x200 + shift
    callback, helper, selection, bag = (value + shift for value in (0x900, 0xA00, 0xB00, 0x600))
    _word(data, record + 7, property_table)
    data[record + 1] = 2  # An unrelated attribute must not become an open-state guard.
    data[property_table:property_table + 5] = bytes((0, 0x31, callback // 512, (callback // 2) & 255, 0))
    cell = property_table + 2
    pointer_address = globals_ + 2 * (68 - 16)
    _word(data, pointer_address, bag)
    resources = {name: 0xD00 + shift + index * 0x20 for index, name in
                 enumerate(("opened", "closed", "reply first", "reply second", "reply third"))}
    for name, address in resources.items():
        encoded = _text(name)
        data[address:address + len(encoded)] = encoded
    for index, value in enumerate([4, 0, *(resources[name] // 2 for name in
                                             ("reply first", "reply second", "reply third"))]):
        _word(data, bag + index * 2, value)
    functions = {}
    assemblers = {}

    def assembler(name, address, count):
        data[address] = count
        entry = address + 1 + 2 * count
        functions[str(address)] = {"entry": entry, "locals": [0] * count,
                                   "guard": data[address:entry].hex()}
        result = _Assembler(data, entry)
        assemblers[name] = result
        return result

    c = assembler("callback", callback, 0)
    c.emit("je", (("v", 136), ("c", 35), ("c", 43)), branch=(False, "hint"))
    c.emit("store", (("c", 67), ("c", 1)))
    c.emit("call", (("w", helper // 2), ("c", number),
                    ("w", resources["opened"] // 2), ("w", resources["closed"] // 2)), store=0)
    c.emit("ret_popped")
    c.label("hint")
    c.emit("je", (("v", 136), ("c", 56)), branch=(False, "residual"))
    c.emit("jz", (("v", 67),), branch=(False, "residual"))
    c.emit("print_ret", text="initial hint")
    c.label("residual")
    c.emit("rfalse")

    h = assembler("helper", helper, 3)
    h.emit("je", (("v", 136), ("c", 43)), branch=(False, "close"))
    h.emit("test_attr", (("v", 1), ("c", 11)), branch=(False, "open_change"))
    h.emit("call", (("w", selection // 2), ("v", 68)), store=0)
    h.emit("print_paddr", (("v", 0),))
    h.jump("open_newline")
    h.label("open_change")
    h.emit("print_paddr", (("v", 2),))
    h.emit("set_attr", (("v", 1), ("c", 11)))
    h.label("open_newline")
    h.emit("new_line")
    h.emit("rtrue")
    h.label("close")
    h.emit("je", (("v", 136), ("c", 35)), branch=(False, False))
    h.emit("test_attr", (("v", 1), ("c", 11)), branch=(False, "close_repeat"))
    h.emit("print_paddr", (("v", 3),))
    h.emit("clear_attr", (("v", 1), ("c", 11)))
    h.jump("close_newline")
    h.label("close_repeat")
    h.emit("call", (("w", selection // 2), ("v", 68)), store=0)
    h.emit("print_paddr", (("v", 0),))
    h.label("close_newline")
    h.emit("new_line")
    h.emit("rtrue")

    s = assembler("selection", selection, 6)
    s.emit("loadw", (("v", 1), ("c", 0)), store=2)
    s.emit("loadw", (("v", 1), ("c", 1)), store=3)
    s.emit("dec", (("c", 2),))
    s.emit("add", (("v", 1), ("c", 2)), store=1)
    s.emit("mul", (("v", 3), ("c", 2)), store=0)
    s.emit("add", (("v", 1), ("v", 0)), store=6)
    s.emit("sub", (("v", 2), ("v", 3)), store=0)
    s.emit("random", (("v", 0),), store=4)
    s.emit("loadw", (("v", 6), ("v", 4)), store=5)
    s.emit("loadw", (("v", 6), ("c", 1)), store=0)
    s.emit("storew", (("v", 6), ("v", 4), ("v", 0)))
    s.emit("storew", (("v", 6), ("c", 1), ("v", 5)))
    s.emit("inc", (("c", 3),))
    s.emit("je", (("v", 3), ("v", 2)), branch=(False, "save_cursor"))
    s.emit("store", (("c", 3), ("c", 0)))
    s.label("save_cursor")
    s.emit("storew", (("v", 1), ("c", 0), ("v", 3)))
    s.emit("ret", (("v", 5),))
    for a in assemblers.values():
        a.finish()
    image = bytes(data)
    source = {"sha256": hashlib.sha256(image).hexdigest(), "version": 3, "authored_fixture": True}
    program = {"format": IR_FORMAT, "role": "uil", "entry": callback + 1,
               "memory": {"initial": image.hex(), "writable_end": dynamic_end},
               "layout": {"objects": objects, "globals": globals_, "abbreviations": abbreviations,
                          "dictionary": 0x680 + shift, "declared_bytes": len(image)},
               "source": source, "functions": functions,
               "blocks": {str(pc): lower_instruction(decode_v3(image, pc))
                          for a in assemblers.values() for pc in a.pcs}}
    scene_uil = {"doors": {"kitchen_window": {"name": "authored gate", "initial_open": False}}}
    scene_udl = {"source": source, "initial_image_sha256": hashlib.sha256(image).hexdigest(),
                 "doors": {"kitchen_window": {"object": number, "record": record,
                            "attribute": 11, "address": record + 1, "mask": 16}}}
    identity = "residual.callback.kitchen_window.action"
    dispatch = {"uil": {}, "udl": {
        "objects": {"kitchen_window": {"number": number, "record": record, "property_table": property_table}},
        "actions": [{"id": "action.open", "number": 43}, {"id": "action.close", "number": 35}],
        "properties": [{"object": number, "object_id": "kitchen_window", "property": 17,
                        "cell": cell, "size": 2, "uses_default": False,
                        "initial_packed": callback // 2, "handler": identity}],
        "handlers": {identity: {"packed": callback // 2, "routine_header": callback,
                                "entry": callback + 1, "locals": []}},
    }}
    return image, program, scene_uil, scene_udl, dispatch


def _mutated(fixture, address, replacement):
    """Rebind authored source honestly, so shape negatives reach their cause."""
    image, program, scene, binding, dispatch = copy.deepcopy(fixture)
    data = bytearray(image)
    data[address:address + len(replacement)] = replacement
    image = bytes(data)
    program["memory"]["initial"] = image.hex()
    program["source"]["sha256"] = hashlib.sha256(image).hexdigest()
    binding["source"] = copy.deepcopy(program["source"])
    binding["initial_image_sha256"] = hashlib.sha256(image).hexdigest()
    for pc in program["blocks"]:
        program["blocks"][pc] = lower_instruction(decode_v3(image, int(pc)))
    for header, function in program["functions"].items():
        function["guard"] = image[int(header):function["entry"]].hex()
    return image, program, scene, binding, dispatch


def test_complete_definition_is_address_free_and_does_not_mutate_inputs():
    fixture = make_window_fixture()
    before = copy.deepcopy(fixture)
    result = recover_window(*fixture)
    assert fixture == before
    assert result["uil"]["resources"] == {
        "window.opened": "opened", "window.closed": "closed",
        "window.repeat.first": "reply first", "window.repeat.second": "reply second",
        "window.repeat.third": "reply third", "newline": "\n"}
    assert result["uil"]["actions"] == {
        "open": {"is_open": True, "resource": "window.opened"},
        "close": {"is_open": False, "resource": "window.closed"}}
    assert result["udl"]["qualification"]["replaced_instruction_count"] == 39
    assert result["udl"]["qualification"]["all_game_intent_recovered"] is False
    assert verify_window(fixture[0], fixture[1], **result)["replaced_instructions"] == 39


def test_all_source_references_relocate_without_changing_intent():
    first = recover_window(*make_window_fixture())
    moved = recover_window(*make_window_fixture(0x200))
    assert moved["uil"] == first["uil"]
    for name in ("callback", "helper", "selection"):
        assert moved["udl"][name]["header"] == first["udl"][name]["header"] + 0x200
    assert moved["udl"]["repeat"]["table_address"] == first["udl"]["repeat"]["table_address"] + 0x200


def test_repeated_recovery_has_identical_canonical_output():
    fixture = make_window_fixture()
    assert canonical_digest(recover_window(*fixture)) == canonical_digest(recover_window(*fixture))


def test_guards_preserve_live_history_open_state_and_bag_permutation():
    result = recover_window(*make_window_fixture())
    udl = result["udl"]
    mutable = [(udl["history"]["address"], 2), (udl["door"]["address"], 1),
               (udl["repeat"]["cursor_address"], 8)]
    for name in udl["runtime_guards"]:
        witness = udl["witnesses"][name]
        assert all(witness["end"] <= start or witness["start"] >= start + size for start, size in mutable)
    assert udl["repeat"]["initial_witness"] not in udl["runtime_guards"]


@pytest.mark.parametrize("role", ["property", "action"])
def test_ambiguous_existing_definitions_are_not_resolved_by_list_order(role):
    fixture = make_window_fixture()
    key = "properties" if role == "property" else "actions"
    fixture[-1]["udl"][key].append(copy.deepcopy(fixture[-1]["udl"][key][0]))
    with pytest.raises(ValueError, match="ambiguous"):
        recover_window(*fixture)


@pytest.mark.parametrize("kind", ["header", "entry", "cell", "object"])
def test_conflicting_dispatch_identity_is_refused(kind):
    fixture = make_window_fixture()
    dispatch = fixture[-1]["udl"]
    if kind in ("header", "entry"):
        key = "routine_header" if kind == "header" else "entry"
        next(iter(dispatch["handlers"].values()))[key] += 2
    else:
        dispatch["properties"][0][kind] += 1
    with pytest.raises(ValueError):
        recover_window(*fixture)


@pytest.mark.parametrize("table_offset,value", [(0, 3), (2, 3), (4, 0), (6, 0xD40 // 2)])
def test_invalid_bag_domains_are_not_normalized(table_offset, value):
    fixture = _mutated(make_window_fixture(), 0x600 + table_offset, value.to_bytes(2, "big"))
    with pytest.raises(ValueError, match="response"):
        recover_window(*fixture)


def test_zero_packed_opening_text_is_not_a_resource_at_zero():
    fixture = make_window_fixture()
    callback = fixture[1]["functions"][str(0x900)]["entry"]
    first = decode_v3(fixture[0], callback)
    second = decode_v3(fixture[0], first["end"])
    call = second["end"]
    changed = _mutated(fixture, call + 5, b"\x00\x00")
    with pytest.raises(ValueError, match="null text"):
        recover_window(*changed)


def test_numerically_equal_code_and_text_references_keep_their_roles():
    fixture = make_window_fixture()
    original = recover_window(*fixture)
    call = original["udl"]["callback"]["source_pcs"][2]
    packed_text = original["udl"]["callback"]["entry"]
    changed = _mutated(fixture, call + 5, packed_text.to_bytes(2, "big"))
    changed = _mutated(changed, packed_text * 2, _text("separate text"))
    recovered = recover_window(*changed)
    assert recovered["uil"]["resources"]["window.opened"] == "separate text"
    assert recovered["udl"]["resources"]["window.opened"]["address"] == 2 * packed_text
    assert recovered["udl"]["callback"]["entry"] == packed_text


def test_output_abbreviation_pointer_and_expansion_are_live_dependencies():
    fixture = make_window_fixture()
    changed = _mutated(fixture, 0xD00, (0x8000 | (1 << 10) | 5).to_bytes(2, "big"))
    changed = _mutated(changed, 0x700, (0xD40 // 2).to_bytes(2, "big"))
    recovered = recover_window(*changed)
    assert recovered["uil"]["resources"]["window.opened"] == "reply first"
    dependencies = recovered["udl"]["resources"]["window.opened"]["dependencies"]
    assert {"text-d00", "abbreviation-700", "text-d40"} <= set(dependencies)
    assert set(dependencies) <= set(recovered["udl"]["runtime_guards"])


def test_null_helper_is_an_unsupported_shape_not_a_routine_at_zero():
    fixture = make_window_fixture()
    call = recover_window(*fixture)["udl"]["callback"]["source_pcs"][2]
    changed = _mutated(fixture, call + 2, b"\x00\x00")
    with pytest.raises(ValueError, match="non-null"):
        recover_window(*changed)


@pytest.mark.parametrize("routine,index", [("callback", 0), ("helper", 1), ("selection", 13)])
def test_branch_polarity_changes_invalidate_the_semantic_shape(routine, index):
    fixture = make_window_fixture()
    result = recover_window(*fixture)
    pc = result["udl"][routine]["source_pcs"][index]
    row = decode_v3(fixture[0], pc)
    address = row["end"] - 2
    changed = _mutated(fixture, address, bytes([fixture[0][address] ^ 0x80]))
    with pytest.raises(ValueError, match="branch"):
        recover_window(*changed)


def test_changed_retained_ir_is_not_accepted_as_the_reference():
    fixture = make_window_fixture()
    fixture[1]["blocks"][str(0x901)]["nodes"] = []
    with pytest.raises(ValueError, match="Low-level IR"):
        recover_window(*fixture)


def test_truncated_routine_fails_with_a_bounded_error():
    fixture = list(make_window_fixture())
    fixture[0] = fixture[0][:0xA10]
    fixture[1]["memory"]["initial"] = fixture[0].hex()
    fixture[3]["initial_image_sha256"] = hashlib.sha256(fixture[0]).hexdigest()
    with pytest.raises(ValueError):
        recover_window(*fixture)


@pytest.mark.parametrize("field", ["uil", "witness", "operations", "guard", "scope"])
def test_binding_verifier_rejects_tampering(field):
    fixture = make_window_fixture()
    result = recover_window(*fixture)
    if field == "uil":
        result["uil"]["resources"]["window.opened"] = "changed"
    elif field == "witness":
        next(iter(result["udl"]["witnesses"].values()))["sha256"] = "0" * 64
    elif field == "operations":
        result["udl"]["helper"]["source_operations"][0]["op"] = "jz"
    elif field == "guard":
        result["udl"]["runtime_guards"].append("missing")
    else:
        result["udl"]["qualification"]["all_game_intent_recovered"] = True
    with pytest.raises(ValueError):
        verify_window(fixture[0], fixture[1], **result)
