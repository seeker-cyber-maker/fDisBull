"""Indexed UIL records with strings, arrays and ``print_text``.

This is a separate, additive record format. It does not change
``fdisbull-il-1`` or its scene envelope. The motivating gap was a recovered
Civ-style screen record whose variables are addressed by a zero-based slot
index, not by a name, and whose text operation is naturally written as
``print_text(23, x, y)`` where slot 23 holds the string.

The record is a language surface, not a renderer. ``print_text`` emits an
ordered declarative event with the text and coordinates; a host decides how
to draw it. That keeps original-byte evidence and presentation claims separate.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy

SCALAR_TYPES = {
    "bool",
    *(f"{sign}{bits}" for sign in "ui" for bits in (8, 16, 32, 64)),
}
SLOT_TYPES = SCALAR_TYPES | {"string", "array"}
MAX_BYTES = 1024 * 1024
MAX_SLOTS = 4096
MAX_STEPS = 65536
MAX_STRING_BYTES = 65536
MAX_ARRAY_LENGTH = 262144
MAX_BLOCKS = 65536
MAX_DEPTH = 64

_FIELDS = {
    "set": ("slot", "value"),
    "add": ("slot", "value"),
    "subtract": ("slot", "value"),
    "multiply": ("slot", "value"),
    "divide": ("slot", "value"),
    "if": ("condition", "then", "else"),
    "require": ("condition",),
    "print_text": ("slot", "x", "y"),
    "set_element": ("slot", "index", "value"),
}


class UILRecordInvalid(ValueError):
    """The record is malformed or outside the declared bounds."""


def _require(ok: object, message: str) -> None:
    if not ok:
        raise UILRecordInvalid(message)


def _fields(
    value: object, required: tuple[str, ...], optional: tuple[str, ...] = ()
) -> None:
    _require(isinstance(value, dict), "expected object")
    _require(
        set(required) <= set(value) <= set(required) | set(optional),
        "invalid fields",
    )


def _typed(value: object, typ: str) -> bool:
    if typ == "bool":
        return type(value) is bool
    if typ == "string":
        return isinstance(value, str)
    bits = int(typ[1:])
    lo, hi = (
        (0, 2**bits - 1) if typ[0] == "u" else (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
    )
    return type(value) is int and lo <= value <= hi


def _slot_ref(value: object, slots: list[dict]) -> bool:
    if isinstance(value, dict):
        return (
            set(value) == {"slot"}
            and type(value["slot"]) is int
            and 0 <= value["slot"] < len(slots)
        )
    return type(value) in (int, bool, str)


def _slot_type(value: object, slots: list[dict]) -> str | None:
    if isinstance(value, dict):
        _require(
            set(value) == {"slot"} and type(value["slot"]) is int,
            "invalid slot reference",
        )
        _require(0 <= value["slot"] < len(slots), "slot reference out of range")
        return slots[value["slot"]]["type"]
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "integer"
    if type(value) is str:
        return "string"
    return None


def _encode(value: object) -> bytes:
    try:
        return json.dumps(
            value, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise UILRecordInvalid("record must be finite JSON") from exc


def _check_string(value: object, max_bytes: int, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    _require(len(value.encode("utf-8")) <= max_bytes, f"{label} exceeds max_bytes")
    return value


def _check_array(value: object, element: str, length: int, label: str) -> list:
    _require(
        isinstance(value, list) and len(value) == length, f"{label} length mismatch"
    )
    for item in value:
        _require(_typed(item, element), f"{label} element type mismatch")
    return value


def validate_record(document: object) -> bool:
    """Validate a complete indexed record before execution."""
    raw = _encode(document)
    _require(len(raw) <= MAX_BYTES, "record size budget exceeded")
    _fields(document, ("format", "role", "slots", "body"), ("evidence",))
    _require(
        document["format"] == "fdisbull-uil-record-1"
        and document["role"] in ("udl", "uil"),
        "invalid format or role",
    )
    slots = document["slots"]
    _require(isinstance(slots, list) and 1 <= len(slots) <= MAX_SLOTS, "invalid slots")
    seen_names: set[str] = set()
    for index, decl in enumerate(slots):
        _fields(
            decl,
            ("type", "initial"),
            ("name", "max_bytes", "element", "length"),
        )
        typ = decl["type"]
        _require(
            isinstance(typ, str) and typ in SLOT_TYPES, f"invalid slot type at {index}"
        )
        if "name" in decl:
            _require(
                isinstance(decl["name"], str)
                and bool(decl["name"])
                and decl["name"] not in seen_names,
                f"invalid or duplicate slot name at {index}",
            )
            seen_names.add(decl["name"])
        if typ == "string":
            _fields(decl, ("type", "initial", "max_bytes"), ("name",))
            _require(
                type(decl["max_bytes"]) is int
                and 0 <= decl["max_bytes"] <= MAX_STRING_BYTES,
                f"invalid string max_bytes at {index}",
            )
            _check_string(decl["initial"], decl["max_bytes"], f"slot {index} initial")
        elif typ == "array":
            _fields(decl, ("type", "initial", "element", "length"), ("name",))
            element = decl["element"]
            _require(
                isinstance(element, str) and element in SCALAR_TYPES,
                f"invalid array element at {index}",
            )
            _require(
                type(decl["length"]) is int and 1 <= decl["length"] <= MAX_ARRAY_LENGTH,
                f"invalid array length at {index}",
            )
            _check_array(
                decl["initial"], element, decl["length"], f"slot {index} initial"
            )
        else:
            _fields(decl, ("type", "initial"), ("name",))
            _require(
                _typed(decl["initial"], typ), f"slot {index} initial type mismatch"
            )

    evidence = document.get("evidence", {})
    _require(isinstance(evidence, dict), "invalid evidence")
    for key, item in evidence.items():
        _require(
            isinstance(key, str) and bool(key) and isinstance(item, dict),
            "invalid evidence item",
        )
        if "sha256" in item:
            _require(
                isinstance(item["sha256"], str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]),
                "invalid evidence digest",
            )
        if "range" in item:
            value = item["range"]
            _require(
                isinstance(value, list)
                and len(value) == 2
                and all(type(x) is int for x in value)
                and 0 <= value[0] <= value[1],
                "invalid evidence range",
            )

    count = [0]
    ids: set[str] = set()

    def condition(cond: object, depth: int) -> None:
        count[0] += 1
        _require(count[0] <= MAX_BLOCKS, "node budget exceeded")
        _require(depth <= MAX_DEPTH, "depth budget exceeded")
        _require(isinstance(cond, dict), "invalid condition")
        op = cond.get("op")
        if op in ("eq", "ge"):
            _fields(cond, ("op", "left", "right"))
            left, right = cond["left"], cond["right"]
            lt, rt = _slot_type(left, slots), _slot_type(right, slots)
            _require(
                _slot_ref(left, slots) and _slot_ref(right, slots),
                "invalid condition operand",
            )
            if op == "ge":
                _require(
                    lt not in ("bool", "string") and rt not in ("bool", "string"),
                    "ge compares integers only",
                )
            else:
                _require(
                    lt != "array"
                    and rt != "array"
                    and (lt == "bool") == (rt == "bool")
                    and (lt == "string") == (rt == "string"),
                    "incompatible equality",
                )
        elif op == "bit_test":
            _fields(cond, ("op", "value", "bit"))
            _require(
                _slot_ref(cond["value"], slots)
                and _slot_type(cond["value"], slots) not in ("bool", "string"),
                "invalid bit test value",
            )
            _require(
                type(cond["bit"]) is int and 0 <= cond["bit"] < 64,
                "invalid bit index",
            )
        elif op == "not":
            _fields(cond, ("op", "condition"))
            condition(cond["condition"], depth + 1)
        elif op == "and":
            _fields(cond, ("op", "conditions"))
            _require(
                isinstance(cond["conditions"], list) and bool(cond["conditions"]),
                "invalid conjunction",
            )
            for child in cond["conditions"]:
                condition(child, depth + 1)
        else:
            raise UILRecordInvalid("unknown condition")

    def blocks(body: object, depth: int) -> None:
        _require(depth <= MAX_DEPTH, "depth budget exceeded")
        _require(isinstance(body, list), "body must be a list")
        for block in body:
            count[0] += 1
            _require(count[0] <= MAX_BLOCKS, "node budget exceeded")
            _require(isinstance(block, dict), "invalid block")
            op = block.get("op")
            _require(op in _FIELDS, "unknown block")
            _fields(block, ("id", "op", *_FIELDS[op]), ("font", "color", "evidence"))
            ident = block["id"]
            _require(
                isinstance(ident, str) and bool(ident) and ident not in ids,
                "invalid or duplicate block id",
            )
            ids.add(ident)
            refs = block.get("evidence", [])
            _require(
                isinstance(refs, list)
                and all(isinstance(x, str) and x in evidence for x in refs),
                "invalid evidence reference",
            )
            if op in ("set", "add", "subtract", "multiply", "divide"):
                _require(
                    type(block["slot"]) is int and 0 <= block["slot"] < len(slots),
                    "invalid target slot",
                )
                typ = slots[block["slot"]]["type"]
                _require(_slot_ref(block["value"], slots), "invalid value")
                vtyp = _slot_type(block["value"], slots)
                _require(
                    typ not in ("array",)
                    and vtyp not in ("array",)
                    and (typ == "bool") == (vtyp == "bool")
                    and (typ == "string") == (vtyp == "string")
                    and (op == "set" or typ != "bool" and typ != "string"),
                    "incompatible assignment",
                )
                if not isinstance(block["value"], dict):
                    if typ == "string":
                        _check_string(
                            block["value"],
                            slots[block["slot"]]["max_bytes"],
                            "literal string",
                        )
                    else:
                        _require(_typed(block["value"], typ), "literal out of range")
            elif op == "if":
                condition(block["condition"], depth + 1)
                blocks(block["then"], depth + 1)
                blocks(block["else"], depth + 1)
            elif op == "require":
                condition(block["condition"], depth + 1)
            elif op == "print_text":
                _require(
                    type(block["slot"]) is int
                    and 0 <= block["slot"] < len(slots)
                    and slots[block["slot"]]["type"] == "string",
                    "print_text requires a string slot",
                )
                for key in ("x", "y"):
                    _require(
                        _slot_ref(block[key], slots)
                        and _slot_type(block[key], slots) not in ("bool", "string"),
                        "invalid text coordinate",
                    )
                if "font" in block:
                    _require(
                        type(block["font"]) is int and 0 <= block["font"] <= 255,
                        "invalid font",
                    )
                if "color" in block:
                    _require(
                        type(block["color"]) is int and 0 <= block["color"] <= 255,
                        "invalid color",
                    )
            elif op == "set_element":
                _require(
                    type(block["slot"]) is int
                    and 0 <= block["slot"] < len(slots)
                    and slots[block["slot"]]["type"] == "array",
                    "set_element requires an array slot",
                )
                _require(
                    _slot_ref(block["index"], slots)
                    and _slot_type(block["index"], slots) not in ("bool", "string"),
                    "invalid array index",
                )
                element = slots[block["slot"]]["element"]
                _require(_slot_ref(block["value"], slots), "invalid array value")
                vtyp = _slot_type(block["value"], slots)
                _require(
                    (vtyp == "bool") == (element == "bool")
                    and (vtyp == "integer" or element == "bool"),
                    "incompatible array value",
                )
                if not isinstance(block["value"], dict):
                    _require(
                        _typed(block["value"], element), "array literal out of range"
                    )

    blocks(document["body"], 1)
    return True


def initial_state(document: object) -> list:
    validate_record(document)
    return [deepcopy(slot["initial"]) for slot in document["slots"]]


def _value(ref: object, state: list, slots: list[dict]) -> object:
    if isinstance(ref, dict):
        return state[ref["slot"]]
    return ref


def _condition(cond: dict, state: list, slots: list[dict]) -> bool:
    op = cond["op"]
    if op == "eq":
        return _value(cond["left"], state, slots) == _value(cond["right"], state, slots)
    if op == "ge":
        return _value(cond["left"], state, slots) >= _value(cond["right"], state, slots)
    if op == "bit_test":
        return bool(_value(cond["value"], state, slots) & (1 << cond["bit"]))
    if op == "not":
        return not _condition(cond["condition"], state, slots)
    return all(_condition(child, state, slots) for child in cond["conditions"])


def _wrap(value: int, typ: str) -> int:
    bits = int(typ[1:])
    value %= 1 << bits
    if typ[0] == "i" and value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


def execute_record(
    document: object, state: object = None, max_steps: int = 1024
) -> dict:
    """Execute one record atomically; return committed state and text events.

    Arrays and strings never alias the caller's ``state``. Unsupported or
    out-of-range operations refuse with no committed state.
    """
    try:
        validate_record(document)
        _require(
            type(max_steps) is int and 0 <= max_steps <= MAX_STEPS,
            "invalid step budget",
        )
        slots = document["slots"]
        work = initial_state(document) if state is None else deepcopy(state)
        _require(isinstance(work, list) and len(work) == len(slots), "invalid state")
        for index, (value, decl) in enumerate(zip(work, slots)):
            typ = decl["type"]
            if typ == "string":
                _check_string(value, decl["max_bytes"], f"state slot {index}")
            elif typ == "array":
                _check_array(
                    value, decl["element"], decl["length"], f"state slot {index}"
                )
            else:
                _require(_typed(value, typ), f"state slot {index} type mismatch")
        events: list[dict] = []
        visited: list[str] = []
        work_state = deepcopy(work)

        def run(body: list[dict]) -> None:
            for block in body:
                _require(len(visited) < max_steps, "step budget exceeded")
                visited.append(block["id"])
                op = block["op"]
                if op in ("set", "add", "subtract", "multiply", "divide"):
                    index = block["slot"]
                    typ = slots[index]["type"]
                    value = _value(block["value"], work_state, slots)
                    if op == "set":
                        if typ == "string":
                            _check_string(
                                value,
                                slots[index]["max_bytes"],
                                "assignment string",
                            )
                        else:
                            _require(_typed(value, typ), "assignment out of range")
                        work_state[index] = value
                    else:
                        _require(
                            type(value) is int and type(work_state[index]) is int,
                            "arithmetic requires integers",
                        )
                        if op == "divide":
                            _require(value != 0, "division by zero")
                            n = abs(work_state[index]) // abs(value)
                            n = -n if (work_state[index] < 0) != (value < 0) else n
                        elif op == "multiply":
                            n = work_state[index] * value
                        else:
                            n = work_state[index] + (value if op == "add" else -value)
                        work_state[index] = _wrap(n, typ)
                elif op == "if":
                    run(
                        block["then"]
                        if _condition(block["condition"], work_state, slots)
                        else block["else"]
                    )
                elif op == "require":
                    _require(
                        _condition(block["condition"], work_state, slots),
                        "qualification condition not met",
                    )
                elif op == "print_text":
                    event = {
                        "op": "print_text",
                        "block_id": block["id"],
                        "slot": block["slot"],
                        "text": work_state[block["slot"]],
                        "x": _value(block["x"], work_state, slots),
                        "y": _value(block["y"], work_state, slots),
                        "evidence": deepcopy(block.get("evidence", [])),
                    }
                    if "font" in block:
                        event["font"] = block["font"]
                    if "color" in block:
                        event["color"] = block["color"]
                    events.append(event)
                elif op == "set_element":
                    index = _value(block["index"], work_state, slots)
                    _require(
                        type(index) is int
                        and 0 <= index < slots[block["slot"]]["length"],
                        "array index out of range",
                    )
                    value = _value(block["value"], work_state, slots)
                    _require(
                        _typed(value, slots[block["slot"]]["element"]),
                        "array value out of range",
                    )
                    work_state[block["slot"]][index] = value

        run(document["body"])
        return {
            "complete": True,
            "status": "complete",
            "state": work_state,
            "events": events,
            "visited": visited,
        }
    except (UILRecordInvalid, TypeError, KeyError, IndexError, RecursionError) as exc:
        return {
            "complete": False,
            "status": "refused",
            "error": str(exc),
            "state": deepcopy(state),
            "events": [],
            "visited": [],
        }
