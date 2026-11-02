"""Authored common-UIL contracts for the bounded collect-coins experiment."""
from __future__ import annotations

from fdisbull.common_uil import digest, validate_program, validate_presentation
from fdisbull.uil_catalog import build_catalog, function_semantic_id
from fdisbull.uil_runtime import execute_program


BLOCKS = ("normalize", "award", "apply")
DOMAINS = {
    "normalize": {"kind": "declared-subset", "description": "raw:i16 in [-8,8]"},
    "award": {"kind": "declared-subset", "description": "count:u16 in [0,3]"},
    "apply": {"kind": "declared-subset", "description": "score:u16 in [0,10]; points:u16 in [0,7]"},
}
MODES = {
    "singles": {"blocks": list(BLOCKS), "files": ["normalize.c", "award.c", "apply.c"], "macro": 1},
    "pair": {"blocks": ["normalize", "award"], "files": ["pair.c"], "macro": 2},
    "triple": {"blocks": list(BLOCKS), "files": ["turn.c"], "macro": 3},
}


def v(slot):
    return {"var": slot}


def c(slot):
    return {"const": slot}


def e(op, typ, *args):
    return {"op": op, "type": typ, "args": list(args)}


def set_(dst, value):
    return {"op": "set", "dst": dst, "value": value}


def function(types, constants, inputs, outputs, body):
    return {"variables": [{"type": t} for t in types],
            "constants": [{"type": t} for t in constants],
            "inputs": inputs, "outputs": outputs, "max_steps": 16, "body": body}


def definitions():
    clamped = e("select", "i16", e("lt", "bool", v(0), c(0)), c(0),
                e("select", "i16", e("gt", "bool", v(0), c(1)), c(1), v(0)))
    normalize = function(["i16", "u16"], ["i16", "i16"], [0], [1],
                         [set_(1, e("cast", "u16", clamped))])
    award = function(["u16", "u16"], ["u16"] * 4, [0], [1],
                     [set_(1, e("add", "u16", e("mul", "u16", v(0), c(0)),
                                e("select", "u16", e("eq", "bool", v(0), c(1)), c(2), c(3))))])
    total = e("add", "u16", v(0), v(1))
    apply = function(["u16", "u16", "u16", "bool"], ["u16"], [0, 1], [2, 3],
                     [set_(2, e("select", "u16", e("gt", "bool", total, c(0)), c(0), total)),
                      set_(3, e("eq", "bool", v(2), c(0)))])
    bindings = [{"constants": ["0", "3"], "initial": ["0", "0"]},
                {"constants": ["2", "3", "1", "0"], "initial": ["0", "0"]},
                {"constants": ["10"], "initial": ["0", "0", "0", False]}]
    return [normalize, award, apply], bindings


def envelope(functions, bindings, entry=0):
    capabilities = ["core.scalar@1"] + (["core.calls@1"] if len(functions) > 1 else [])
    program = {"format": "fdisbull-common-uil-1", "capabilities": capabilities,
               "imports": [], "functions": functions, "entry": entry}
    presentation = {"format": "fdisbull-uil-presentation-1", "program_sha256": digest(program),
                    "functions": bindings, "resources": []}
    validate_program(program)
    validate_presentation(program, presentation)
    return {"program": program, "presentation": presentation}


def contracts():
    fs, bs = definitions()
    documents = {name: envelope([fn], [binding]) for name, fn, binding in zip(BLOCKS, fs, bs)}
    pair = function(["i16", "u16", "u16"], [], [0], [1, 2], [
        {"op": "call", "function": 0, "inputs": [v(0)], "outputs": [1]},
        {"op": "call", "function": 1, "inputs": [v(1)], "outputs": [2]},
    ])
    turn = function(["i16", "u16", "u16", "u16", "u16", "bool"], [], [0, 1], [2, 3, 4, 5], [
        {"op": "call", "function": 0, "inputs": [v(0)], "outputs": [2]},
        {"op": "call", "function": 1, "inputs": [v(2)], "outputs": [3]},
        {"op": "call", "function": 2, "inputs": [v(1), v(3)], "outputs": [4, 5]},
    ])
    documents["pair"] = envelope(fs[:2] + [pair], bs[:2] + [{"constants": [], "initial": ["0"] * 3}], 2)
    documents["turn"] = envelope(fs + [turn], bs + [{"constants": [], "initial": ["0"] * 5 + [False]}], 3)
    return documents


def evaluate(name, inputs):
    doc = contracts()[name]
    result = execute_program(doc["program"], doc["presentation"], inputs=list(inputs), max_steps=128)
    if result["status"] != "complete":
        raise ValueError("fixture unexpectedly refused: " + str(result))
    return result["outputs"]


def cases(name):
    if name in ("normalize", "pair"):
        return [(raw,) for raw in range(-8, 9)]
    if name == "award":
        return [(count,) for count in range(4)]
    if name == "apply":
        return [(score, points) for score in range(11) for points in range(8)]
    if name == "turn":
        return [(raw, score) for raw in range(-8, 9) for score in range(11)]
    raise ValueError("unknown contract")


def catalog(source_by_name=None):
    fs, bs = definitions()
    specs = []
    for name, fn, binding in zip(BLOCKS, fs, bs):
        if source_by_name is not None and name not in source_by_name:
            continue
        source = {"origin": "authored collect-coins model", "block": name}
        if source_by_name is not None:
            source.update(source_by_name[name])
        specs.append({"language": "common", "origin_language": "common" if source_by_name is None else "c-declared",
                      "function": fn, "constants": binding["constants"], "source": source})
    result = build_catalog(specs)
    if result["rejected"]:
        raise ValueError(result["rejected"])
    return result


def semantic_ids():
    fs, bs = definitions()
    return {name: function_semantic_id(fn, binding["constants"]) for name, fn, binding in zip(BLOCKS, fs, bs)}
