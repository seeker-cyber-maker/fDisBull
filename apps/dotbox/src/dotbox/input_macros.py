"""The fixed player-input subset of fDisBull's immutable macro format.

Provenance: identifier, JSON encoding and document layout adapted from
fDisBull ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9,
src/fdisbull/input_macros.py. DotBox intentionally accepts only its existing
bounded literal keyboard controls; debugger scripts, parameters, aliases,
outputs, nesting and held-key leases are not part of this standalone subset.
"""

from copy import deepcopy
import json
import re


PRIMITIVES = frozenset({"keyboard.press", "keyboard.type"})


def encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Control vocabulary must be bounded JSON data") from error


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.:-]{0,127}", value):
        raise ValueError("Invalid macro identifier")
    return value


def validate_macro_set(definition):
    if (not isinstance(definition, dict)
            or set(definition) - {"format", "name", "macros", "provenance"}
            or definition.get("format") != "fdisbull-macro-set-1"):
        raise ValueError("Expected fdisbull-macro-set-1")
    identifier(definition.get("name"))
    if len(encode(definition).encode()) > 48 * 1024:
        raise ValueError("Control vocabulary exceeds 48 KiB")
    macros = definition.get("macros")
    if not isinstance(macros, dict) or not 1 <= len(macros) <= 32:
        raise ValueError("Expected 1..32 controls")
    for name, macro in macros.items():
        identifier(name)
        if (not isinstance(macro, dict)
                or set(macro) - {"parameters", "authority", "steps", "outputs", "context", "evidence"}):
            raise ValueError("Invalid macro declaration")
        if (not isinstance(macro.get("parameters", {}), dict)
                or not isinstance(macro.get("outputs", {}), dict)):
            raise ValueError("Macro parameters and outputs must be objects")
        if (macro.get("authority", "player-input") != "player-input"
                or macro.get("parameters") or macro.get("outputs")):
            raise ValueError("Controls require fixed player-input steps without parameters or outputs")
        steps = macro.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 16:
            raise ValueError("Controls require 1..16 input steps")
        for step in steps:
            if (not isinstance(step, dict) or not isinstance(step.get("op"), str)
                    or step["op"] not in PRIMITIVES):
                raise ValueError("Unsupported macro operation")
    return deepcopy(definition)


def expand_macro(definition, name, args=None, *, allowed_authorities=("player-input",)):
    definition = validate_macro_set(definition)
    if args not in (None, {}):
        raise ValueError("Runtime parameters are not supported")
    if "player-input" not in allowed_authorities:
        raise ValueError("Macro authority is not allowed: player-input")
    if not isinstance(name, str) or name not in definition["macros"]:
        raise ValueError("Unknown macro")
    # No rewriting: this preserves literal keyboard documents and their IDs.
    return {"script": {"format": "fdisbull-script-1",
                       "steps": definition["macros"][name]["steps"]},
            "outputs": {}, "lineage": []}
