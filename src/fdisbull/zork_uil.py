"""Ahead-of-time v3 source mapping into an executable, versioned UIL profile.

The independent player consumes arithmetic, memory, control, and layout-library
nodes. It never imports this module or decodes a source instruction. We retain a
finite superset of legal instruction starts to close indirect calls and jumps;
candidate starts are not asserted to be reachable code.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from .zmachine import decode_v3, decode_ztext, inspect_story


FORMAT = "fdisbull-uil-word16-1"
UDL_FORMAT = "fdisbull-udl-v3-word16-1"
Z_FORMAT = "fdisbull-z-word16-view-1"

_ARITY = {
    "je": (2, 4), "jl": (2, 2), "jg": (2, 2), "dec_chk": (2, 2),
    "inc_chk": (2, 2), "jin": (2, 2), "test": (2, 2), "or": (2, 2),
    "and": (2, 2), "test_attr": (2, 2), "set_attr": (2, 2),
    "clear_attr": (2, 2), "store": (2, 2), "insert_obj": (2, 2),
    "loadw": (2, 2), "loadb": (2, 2), "get_prop": (2, 2),
    "get_prop_addr": (2, 2), "get_next_prop": (2, 2), "add": (2, 2),
    "sub": (2, 2), "mul": (2, 2), "div": (2, 2), "mod": (2, 2),
    "jz": (1, 1), "get_sibling": (1, 1), "get_child": (1, 1),
    "get_parent": (1, 1), "get_prop_len": (1, 1), "inc": (1, 1),
    "dec": (1, 1), "print_addr": (1, 1), "remove_obj": (1, 1),
    "print_obj": (1, 1), "ret": (1, 1), "jump": (1, 1),
    "print_paddr": (1, 1), "load": (1, 1), "not": (1, 1),
    "rtrue": (0, 0), "rfalse": (0, 0), "print": (0, 0),
    "print_ret": (0, 0), "nop": (0, 0), "save": (0, 0),
    "restore": (0, 0), "restart": (0, 0), "ret_popped": (0, 0),
    "pop": (0, 0), "quit": (0, 0), "new_line": (0, 0),
    "show_status": (0, 0), "verify": (0, 0), "call": (1, 4),
    "storew": (3, 3), "storeb": (3, 3), "put_prop": (3, 3),
    "read": (2, 2), "print_char": (1, 1), "print_num": (1, 1),
    "random": (1, 1), "push": (1, 1), "pull": (1, 1),
    "split_window": (1, 1), "set_window": (1, 1),
    "output_stream": (1, 2), "input_stream": (1, 1),
    "sound_effect": (1, 4),
}


def _tmp(name):
    return {"tmp": name}


def _calc(name, *args):
    return {"calc": name, "args": list(args)}


def _u16(value):
    return _calc("u16", value)


def _s16(value):
    return _calc("s16", value)


def _branch_path(instruction, value):
    """Resolve the source's branch polarity into ordinary control primitives."""
    branch = instruction["branch"]
    if value != branch["when"]:
        return [{"op": "goto", "target": instruction["end"]}]
    if branch["return"] is not None:
        return [{"op": "return", "value": int(branch["return"])}]
    return [{"op": "goto", "target": branch["target"]}]


def lower_instruction(instruction):
    """Expand one decoded source operation into ordered shared primitives.

    Operand reads precede every effect and occur left-to-right. This matters for
    stack variables and for instructions whose first operand names a variable.
    """
    name = instruction["op"]
    low, high = _ARITY[name]
    operands = instruction["operands"]
    if not low <= len(operands) <= high:
        raise ValueError("Illegal source operand count")
    nodes = []
    values = []
    for index, operand in enumerate(operands):
        dest = f"a{index}"
        value = operand["value"]
        if operand["kind"] == "variable":
            nodes.append({"op": "read_var", "index": value,
                          "dest": dest, "indirect": False})
        else:
            nodes.append({"op": "let", "name": dest, "value": value})
        values.append(_tmp(dest))

    def store(value):
        nodes.append({"op": "write_var", "index": instruction["store"],
                      "value": value, "indirect": False})

    def branch(condition):
        nodes.append({"op": "if", "condition": condition,
                      "then": _branch_path(instruction, True),
                      "else": _branch_path(instruction, False)})

    def library(lib, args, dest="r"):
        nodes.append({"op": "library", "name": lib, "args": args,
                      **({"dest": dest} if dest is not None else {})})
        return _tmp(dest) if dest is not None else None

    def text_at(address):
        nodes.append({"op": "emit", "value": library("text.decode", [address])})

    if name in ("add", "sub", "mul", "or", "and"):
        store(_u16(_calc(name, *values)))
    elif name in ("div", "mod"):
        store(_u16(_calc(name, *map(_s16, values))))
    elif name == "not":
        store(_calc("xor", values[0], 65535))
    elif name == "je":
        branch(_calc("any", *(_calc("eq", values[0], v) for v in values[1:])))
    elif name in ("jl", "jg"):
        branch(_calc("lt" if name == "jl" else "gt", *map(_s16, values)))
    elif name == "jz":
        branch(_calc("eq", values[0], 0))
    elif name == "test":
        branch(_calc("eq", _calc("and", *values), values[1]))
    elif name in ("inc", "dec", "inc_chk", "dec_chk"):
        nodes.append({"op": "read_var", "index": values[0], "dest": "old",
                      "indirect": True})
        nodes.append({"op": "let", "name": "updated", "value":
                      _u16(_calc("add" if name.startswith("inc") else "sub", _tmp("old"), 1))})
        nodes.append({"op": "write_var", "index": values[0], "value": _tmp("updated"),
                      "indirect": True})
        if name.endswith("_chk"):
            branch(_calc("gt" if name == "inc_chk" else "lt", _s16(_tmp("updated")), _s16(values[1])))
    elif name == "load":
        nodes.append({"op": "read_var", "index": values[0], "dest": "r", "indirect": True})
        store(_tmp("r"))
    elif name == "store":
        nodes.append({"op": "write_var", "index": values[0], "value": values[1], "indirect": True})
    elif name in ("loadb", "loadw", "storeb", "storew"):
        wide = name.endswith("w")
        address = _u16(_calc("add", values[0], _calc("mul", values[1], 2 if wide else 1)))
        if name.startswith("load"):
            store(_calc("mem16" if wide else "mem8", address))
        else:
            nodes.append({"op": "write_mem", "address": address,
                          "width": 16 if wide else 8, "value": values[2]})
    elif name in ("get_parent", "get_child", "get_sibling"):
        result = library("tree." + name[4:], values)
        store(result)
        if name != "get_parent":
            branch(_calc("ne", result, 0))
    elif name == "jin":
        branch(_calc("eq", library("tree.parent", [values[0]]), values[1]))
    elif name == "remove_obj":
        library("tree.detach", values, None)
    elif name == "insert_obj":
        library("tree.insert", values, None)
    elif name in ("test_attr", "set_attr", "clear_attr"):
        result = library("attribute." + name.split("_")[0], values,
                         "r" if name == "test_attr" else None)
        if name == "test_attr":
            branch(result)
    elif name in ("get_prop", "get_prop_addr", "get_next_prop", "get_prop_len"):
        method = {"get_prop": "get", "get_prop_addr": "address",
                  "get_next_prop": "next", "get_prop_len": "length"}[name]
        store(library("property." + method, values))
    elif name == "put_prop":
        library("property.put", values, None)
    elif name == "call":
        nodes.append({"op": "call", "target": _calc("mul", values[0], 2),
                      "args": values[1:], "store": instruction["store"],
                      "resume": instruction["end"]})
    elif name in ("rtrue", "rfalse", "ret"):
        nodes.append({"op": "return", "value": values[0] if name == "ret" else int(name == "rtrue")})
    elif name == "jump":
        nodes.append({"op": "goto", "target": _calc("add", instruction["end"] - 2, _s16(values[0]))})
    elif name == "ret_popped":
        nodes.extend([{"op": "pop", "dest": "r"}, {"op": "return", "value": _tmp("r")}])
    elif name == "pop":
        nodes.append({"op": "pop", "dest": "discard"})
    elif name == "push":
        nodes.append({"op": "push", "value": values[0]})
    elif name == "pull":
        nodes.extend([{"op": "pop", "dest": "r"},
                      {"op": "write_var", "index": values[0], "value": _tmp("r"), "indirect": True}])
    elif name in ("print", "print_ret"):
        text_at(instruction["text_offset"])
        if name == "print_ret":
            nodes.extend([{"op": "emit", "value": "\n"}, {"op": "return", "value": 1}])
    elif name in ("print_addr", "print_paddr"):
        text_at(values[0] if name == "print_addr" else _calc("mul", values[0], 2))
    elif name in ("print_obj", "print_char", "print_num"):
        lib = {"print_obj": "tree.name", "print_char": "text.character", "print_num": "text.number"}[name]
        args = [_s16(values[0])] if name == "print_num" else values
        nodes.append({"op": "emit", "value": library(lib, args)})
    elif name == "new_line":
        nodes.append({"op": "emit", "value": "\n"})
    elif name == "random":
        nodes.append({"op": "random", "range": _s16(values[0]), "dest": "r"})
        store(_tmp("r"))
    elif name == "read":
        nodes.append({"op": "input", "text": values[0], "parse": values[1], "resume": instruction["end"]})
    elif name in ("save", "restore"):
        nodes.append({"op": "persist", "mode": name,
                      "success": _branch_path(instruction, True),
                      "failure": _branch_path(instruction, False),
                      "resume": instruction["end"]})
    elif name in ("restart", "quit"):
        nodes.append({"op": name})
    elif name == "verify":
        # The mapper only accepts a matching source checksum. @verify checks the
        # original file, not writable play-state memory, so its result is bound.
        branch(True)
    elif name == "nop":
        pass
    elif name in ("show_status", "split_window", "set_window", "output_stream", "input_stream", "sound_effect"):
        action = {"show_status": "status", "split_window": "split", "set_window": "window", "sound_effect": "sound"}.get(name, name)
        nodes.append({"op": "host", "action": action, "args": values})
    else:
        raise ValueError(f"No semantic mapping for {name}")
    return {"guard": instruction["bytes"], "nodes": nodes, "next": instruction["end"]}


def compile_story(path):
    """Convert a complete checksum-qualified story to a source-independent UIL.

    Exhaustive-offset lowering prevents observed-play traces from deciding what
    game code survives. Every legal original instruction start can be dispatched,
    including indirect destinations; invalid starts fail rather than being decoded
    by the runtime. Reachability is a separate, explicitly unclaimed property.
    """
    info = inspect_story(path)
    raw = Path(path).read_bytes()
    image = raw[:info["declared_bytes"]]
    blocks, evidence, rejected, op_counts = {}, {}, Counter(), Counter()
    for address in range(64, len(image)):
        try:
            instruction = decode_v3(image, address)
            block = lower_instruction(instruction)
        except ValueError as exc:
            rejected[str(exc).split(" at ")[0]] += 1
            continue
        blocks[str(address)] = block
        evidence[str(address)] = instruction
        op_counts[instruction["op"]] += 1
    if str(info["initial_pc"]) not in blocks:
        raise ValueError("Initial PC has no supported semantic mapping")
    functions = {}
    for address in range(64, len(image), 2):
        count = image[address]
        if count > 15:
            continue
        end = address + 1 + 2 * count
        if end >= len(image) or str(end) not in blocks:
            continue
        functions[str(address)] = {
            "guard": image[address:end].hex(), "entry": end,
            "locals": [int.from_bytes(image[n:n + 2], "big") for n in range(address + 1, end, 2)],
        }
    source = {"sha256": info["sha256"], "version": info["version"],
              "release": info["release"], "serial": info["serial_text"],
              "file_bytes": info["file_bytes"], "declared_bytes": len(image),
              "trailing_bytes": info["trailing_bytes"],
              "trailing_sha256": hashlib.sha256(raw[len(image):]).hexdigest(),
              "checksum": info["checksum"]}
    program = {
        "format": FORMAT, "role": "uil", "source": source,
        "entry": info["initial_pc"],
        "memory": {"initial": image.hex(), "writable_end": info["static_memory"]},
        "layout": {key: info[key] for key in ("globals", "objects", "dictionary", "abbreviations", "declared_bytes")},
        "blocks": blocks, "functions": functions,
        "qualification": {
            "conversion": "ahead_of_time_semantic_lowering",
            "coverage": "all_valid_original_instruction_starts_in_declared_image",
            "candidate_starts_are_reachable_code": False,
            "original_engine_required": False,
            "runtime_instruction_decoder": False,
            "code_mutation": "explicit_guard_failure",
            "all_paths_behaviorally_verified": False,
            "high_level_intent_names_recovered": False,
        },
    }
    mapping = {
        "format": UDL_FORMAT, "role": "udl", "source": source,
        "target_format": FORMAT,
        "method": "exhaustive_original_offset_decode_then_ordered_semantic_expansion",
        "instruction_candidates": evidence,
        "function_candidates": functions,
        "counts": {"attempted_offsets": len(image) - 64,
                   "mapped_candidates": len(blocks), "function_candidates": len(functions),
                   "source_operations": dict(sorted(op_counts.items())),
                   "rejected_offsets": dict(sorted(rejected.items()))},
        "assumptions": ["v3 default alphabet and encoding", "checksum-qualified original source",
                        "executed instruction and routine-header bytes retain original values"],
        "claim_boundary": "Complete low-level mapping; candidate boundaries do not prove reachability or high-level intent.",
    }
    return program, mapping


def world_view(program):
    """Inventory original records without pretending to infer every room/intent."""
    data = bytes.fromhex(program["memory"]["initial"])
    word = lambda at: int.from_bytes(data[at:at + 2], "big")
    base = program["layout"]["objects"] + 62
    first_properties = word(base + 7)
    count, remainder = divmod(first_properties - base, 9)
    if remainder or not 1 <= count <= 255:
        raise ValueError("Cannot qualify contiguous v3 object-record extent")
    objects = []
    for number in range(1, count + 1):
        at = base + 9 * (number - 1)
        pointer = word(at + 7)
        if pointer < first_properties or pointer >= len(data):
            raise ValueError("Object property pointer contradicts qualified table extent")
        name = decode_ztext(data, pointer + 1)[0] if data[pointer] else ""
        properties = []
        cursor = pointer + 1 + 2 * data[pointer]
        for _ in range(32):
            header = data[cursor]
            if not header:
                break
            size = (header >> 5) + 1
            properties.append({"number": header & 31, "address": cursor + 1,
                               "bytes": data[cursor + 1:cursor + 1 + size].hex()})
            cursor += size + 1
        else:
            raise ValueError("Unterminated object property list")
        objects.append({"id": number, "short_name": name, "source_offset": at,
                        "parent": data[at + 4], "sibling": data[at + 5], "child": data[at + 6],
                        "attributes": [n for n in range(32) if data[at + n // 8] & (128 >> (n % 8))],
                        "properties": properties})
    return {"format": Z_FORMAT, "source": program["source"], "objects": objects,
            "globals": [{"index": n + 16, "initial": word(program["layout"]["globals"] + 2 * n)} for n in range(240)],
            "executable_program": {"format": FORMAT, "entry": program["entry"]},
            "authority": "initial record projection; the UIL execution state owns subsequent behavior",
            "unknown": ["named roles of every flag/property/global", "object versus room classification",
                        "high-level names for all recovered low-level rules"]}


def _private_destination(path):
    path = Path(path).expanduser().resolve()
    for parent in path.parents:
        marker = parent / ".git"
        if (marker.is_dir() and (marker / "HEAD").is_file()) or marker.is_file():
            raise ValueError("Game-derived output must be outside a Git checkout")
    if path.exists():
        raise FileExistsError(f"Refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_document(path, document):
    path = _private_destination(path)
    payload = json.dumps(document, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    if path.suffix == ".gz":
        payload = gzip.compress(payload, mtime=0)
    with path.open("xb") as stream:
        stream.write(payload)
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def convert_story(story, *, output, mapping=None, world=None):
    """Write the requested conversion views and return a compact receipt."""
    # Preflight every destination before doing work or writing any result.
    targets = [p for p in (output, mapping, world) if p]
    if len({str(Path(p).resolve()) for p in targets}) != len(targets):
        raise ValueError("Output paths must be distinct")
    for path in targets:
        _private_destination(path)
    program, source_mapping = compile_story(story)
    projection = world_view(program) if world else None
    outputs = {"uil": write_document(output, program)}
    if mapping:
        outputs["udl"] = write_document(mapping, source_mapping)
    if world:
        outputs["z"] = write_document(world, projection)
    return {"source": program["source"], "counts": source_mapping["counts"], "outputs": outputs}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Map a complete v3 story into standalone executable UIL")
    parser.add_argument("story")
    parser.add_argument("--output", required=True, help="new private .uil.json or .uil.json.gz")
    parser.add_argument("--mapping", help="new private UDL provenance document (.gz supported)")
    parser.add_argument("--world", help="new private Z object/state projection")
    args = parser.parse_args(argv)
    print(json.dumps(convert_story(args.story, output=args.output, mapping=args.mapping, world=args.world), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
