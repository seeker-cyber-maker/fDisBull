"""Standalone consumer for the versioned word16 UIL execution profile.

Only typed arithmetic, memory, control, and declared data-layout operations are
executed here. There is no source instruction decoder, original VM, compiler,
or dependency on the fdisbull analysis package. Source identity guards protect
ahead-of-time mappings from silently executing changed code.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


FORMAT = "fdisbull-uil-word16-1"
CHECKPOINT_FORMAT = "fdisbull-uil-word16-state-1"
MAX_PROGRAM_BYTES = 128 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024
MAX_TEXT = 1024 * 1024
MAX_STACK = 65536
MAX_FRAMES = 4096
_TEMP = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ALPHABETS = ("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
              " \n0123456789.,!?_#'\"/\\-:()")
_EXTRA = "äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿"
_CALC_ARITY = {name: 2 for name in
               ("add", "sub", "mul", "div", "mod", "and", "or", "xor", "shl", "shr",
                "eq", "ne", "lt", "gt", "le", "ge")}
_CALC_ARITY.update({name: 1 for name in ("not", "u16", "s16", "mem8", "mem16")})
_CALC_ARITY.update(any=None, all=None)
_LIBRARY_ARITY = {
    "tree.parent": 1, "tree.sibling": 1, "tree.child": 1, "tree.detach": 1,
    "tree.insert": 2, "tree.name": 1, "attribute.test": 2, "attribute.set": 2,
    "attribute.clear": 2, "property.get": 2, "property.address": 2,
    "property.next": 2, "property.put": 3, "property.length": 1,
    "text.decode": 1, "text.character": 1, "text.number": 1,
}


class Word16Error(ValueError):
    """Invalid program/state or an explicitly unsupported execution boundary."""


def _integer(value, label="integer", low=None, high=None):
    if type(value) is not int or (low is not None and value < low) or (high is not None and value > high):
        raise Word16Error(f"Invalid {label}")
    return value


def _keys(value, required, optional=(), label="record"):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise Word16Error(f"Invalid {label} fields")


def _hex(value, label, maximum):
    if not isinstance(value, str) or len(value) % 2 or len(value) > maximum * 2 or not re.fullmatch(r"[0-9a-f]*", value):
        raise Word16Error(f"Invalid {label}")
    return bytes.fromhex(value)


def _u16(value):
    return _integer(value) & 65535


def _s16(value):
    value = _u16(value)
    return value - 65536 if value & 32768 else value


def _bounded_integer(value):
    return _integer(value, "arithmetic intermediate", -(2**63), 2**63)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _json_load(stream, maximum):
    data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise Word16Error("JSON input exceeds its byte budget")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise Word16Error("Duplicate JSON object key")
            out[key] = value
        return out
    def bad_constant(_):
        raise Word16Error("Nonfinite JSON number")
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Word16Error("Invalid JSON input") from exc


def _validate_expression(expr, depth=0):
    if depth > 48:
        raise Word16Error("Expression nesting exceeds budget")
    if type(expr) in (int, bool, str):
        if type(expr) is int and abs(expr) > 2**63:
            raise Word16Error("Integer literal exceeds budget")
        if isinstance(expr, str) and len(expr) > MAX_TEXT:
            raise Word16Error("Text literal exceeds budget")
        return
    if not isinstance(expr, dict):
        raise Word16Error("Invalid expression")
    if "tmp" in expr:
        _keys(expr, ("tmp",), label="temporary")
        if not isinstance(expr["tmp"], str) or not _TEMP.fullmatch(expr["tmp"]):
            raise Word16Error("Invalid temporary name")
        return
    _keys(expr, ("calc", "args"), label="calculation")
    name, args = expr["calc"], expr["args"]
    if name not in _CALC_ARITY or not isinstance(args, list) or len(args) > 16:
        raise Word16Error("Unsupported calculation")
    arity = _CALC_ARITY[name]
    if arity is not None and len(args) != arity:
        raise Word16Error("Invalid calculation arity")
    for item in args:
        _validate_expression(item, depth + 1)


def _validate_nodes(nodes, count, depth=0):
    if depth > 32 or not isinstance(nodes, list) or len(nodes) > 4096:
        raise Word16Error("Invalid node list or nesting budget")
    shapes = {
        "let": (("name", "value"), ()), "read_var": (("index", "dest"), ("indirect",)),
        "write_var": (("index", "value"), ("indirect",)),
        "write_mem": (("address", "width", "value"), ()), "push": (("value",), ()),
        "pop": (("dest",), ()), "if": (("condition", "then"), ("else",)),
        "goto": (("target",), ()), "call": (("target", "args", "store", "resume"), ()),
        "return": (("value",), ()), "emit": (("value",), ()),
        "random": (("range", "dest"), ()), "library": (("name", "args"), ("dest",)),
        "input": (("text", "parse", "resume"), ()),
        "persist": (("mode", "success", "failure", "resume"), ()),
        "restart": ((), ()), "quit": ((), ()), "host": (("action", "args"), ()),
    }
    expression_fields = {"index", "value", "address", "condition", "target", "range", "text", "parse"}
    for node in nodes:
        count[0] += 1
        if count[0] > 2_000_000 or not isinstance(node, dict) or node.get("op") not in shapes:
            raise Word16Error("Unsupported node or node budget")
        op = node["op"]
        required, optional = shapes[op]
        _keys(node, ("op", *required), optional, "node")
        for key in expression_fields & node.keys():
            _validate_expression(node[key])
        for key in ("dest", "name" if op == "let" else "dest"):
            if key in node and (not isinstance(node[key], str) or not _TEMP.fullmatch(node[key])):
                raise Word16Error("Invalid destination temporary")
        if "indirect" in node and type(node["indirect"]) is not bool:
            raise Word16Error("Invalid indirect flag")
        if "width" in node and (type(node["width"]) is not int or node["width"] not in (8, 16)):
            raise Word16Error("Invalid memory width")
        if "args" in node:
            if not isinstance(node["args"], list) or len(node["args"]) > 16:
                raise Word16Error("Invalid argument list")
            for expr in node["args"]:
                _validate_expression(expr)
        if op == "library" and (node["name"] not in _LIBRARY_ARITY or len(node["args"]) != _LIBRARY_ARITY[node["name"]]):
            raise Word16Error("Unsupported library call")
        if op == "host" and node["action"] not in ("status", "window", "split", "output_stream", "input_stream", "sound"):
            raise Word16Error("Unsupported host action")
        if op == "persist" and node["mode"] not in ("save", "restore"):
            raise Word16Error("Unsupported persistence mode")
        if "resume" in node:
            _integer(node["resume"], "resume PC", 0, 131072)
        if op == "call":
            _integer(node["store"], "call store", 0, 255)
        for key in ("then", "else", "success", "failure"):
            if key in node:
                _validate_nodes(node[key], count, depth + 1)


def validate_program(program):
    """Validate the complete profile, including unselected branches."""
    _keys(program, ("format", "role", "source", "entry", "memory", "layout", "blocks", "functions"), ("qualification",), label="program")
    if program["format"] != FORMAT or program["role"] != "uil":
        raise Word16Error("Unsupported UIL format or role")
    source = program["source"]
    if not isinstance(source, dict) or not isinstance(source.get("sha256"), str) or not _DIGEST.fullmatch(source["sha256"]) or source.get("version") != 3:
        raise Word16Error("Invalid source identity")
    memory = program["memory"]
    _keys(memory, ("initial", "writable_end"), label="memory")
    initial = _hex(memory["initial"], "initial memory", 131072)
    if len(initial) < 64:
        raise Word16Error("Memory is too short")
    _integer(memory["writable_end"], "writable boundary", 64, min(len(initial), 65536))
    layout = program["layout"]
    _keys(layout, ("globals", "objects", "dictionary", "abbreviations", "declared_bytes"), label="layout")
    for key, value in layout.items():
        _integer(value, f"layout {key}", 0, len(initial))
    if layout["declared_bytes"] != len(initial):
        raise Word16Error("Declared memory length mismatch")
    if layout["globals"] + 480 > memory["writable_end"] or layout["objects"] + 62 > memory["writable_end"] or layout["abbreviations"] + 192 > len(initial):
        raise Word16Error("Layout table exceeds memory")
    blocks, functions = program["blocks"], program["functions"]
    if not isinstance(blocks, dict) or not 1 <= len(blocks) <= 131072 or not isinstance(functions, dict) or len(functions) > 65536:
        raise Word16Error("Invalid program tables")
    count = [0]
    for key, block in blocks.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise Word16Error("Invalid block identity")
        address = _integer(int(key), "block address", 0, len(initial) - 1)
        _keys(block, ("guard", "nodes", "next"), label="block")
        guard = _hex(block["guard"], "block guard", len(initial))
        if not guard or address + len(guard) > len(initial) or initial[address:address + len(guard)] != guard:
            raise Word16Error("Block guard does not bind initial bytes")
        _integer(block["next"], "block continuation", 0, len(initial))
        _validate_nodes(block["nodes"], count)
    for key, function in functions.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise Word16Error("Invalid function identity")
        address = _integer(int(key), "function address", 0, len(initial) - 1)
        _keys(function, ("guard", "locals", "entry"), label="function")
        guard = _hex(function["guard"], "function guard", 31)
        if not guard or initial[address:address + len(guard)] != guard:
            raise Word16Error("Function guard does not bind initial bytes")
        if not isinstance(function["locals"], list) or len(function["locals"]) > 15:
            raise Word16Error("Invalid local defaults")
        for value in function["locals"]:
            _integer(value, "local default", 0, 65535)
        _integer(function["entry"], "function entry", 0, len(initial) - 1)
        if str(function["entry"]) not in blocks:
            raise Word16Error("Function entry is missing")
    _integer(program["entry"], "initial entry", 0, len(initial) - 1)
    if str(program["entry"]) not in blocks:
        raise Word16Error("Initial entry is missing")
    return program


def load_program(path):
    """Load bounded plain or gzip JSON; compressed size never bypasses the cap."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        program = _json_load(stream, MAX_PROGRAM_BYTES)
    return validate_program(program)


class Word16Runtime:
    """Execute a prelowered UIL graph with one authoritative memory and stack."""

    def __init__(self, program, seed=12, random_tape=None):
        validate_program(program)
        self.program = copy.deepcopy(program)
        self.package_digest = hashlib.sha256(_canonical(self.program)).hexdigest()
        self.initial = bytes.fromhex(program["memory"]["initial"])
        self.writable_end = program["memory"]["writable_end"]
        self.layout = dict(program["layout"])
        self.blocks = {int(k): v for k, v in self.program["blocks"].items()}
        self.functions = {int(k): v for k, v in self.program["functions"].items()}
        self._guards = {k: bytes.fromhex(v["guard"]) for k, v in self.blocks.items()}
        self._function_guards = {k: bytes.fromhex(v["guard"]) for k, v in self.functions.items()}
        self.seed = _integer(seed, "seed", 0, 0xffffffff)
        self.random_tape = self._validate_tape(random_tape)
        self.executed_blocks = set()
        self._game_slot = None
        self._initialize()

    @staticmethod
    def _validate_tape(tape):
        if tape is None:
            return None
        if not isinstance(tape, list) or len(tape) > 1_000_000:
            raise Word16Error("Invalid random tape")
        copied = []
        for row in tape:
            _keys(row, ("range", "value"), label="random tape item")
            n = _integer(row["range"], "random range", 1, 32767)
            copied.append({"range": n, "value": _integer(row["value"], "random value", 1, n)})
        return copied

    def _initialize(self, flags2=None):
        self.memory = bytearray(self.initial)
        if flags2 is not None:
            self.memory[16:18] = flags2
        self.pc = self.program["entry"]
        self.frames = [{"locals": [], "base": 0, "resume": None, "store": None}]
        self.stack = []
        self.pending_input = None
        self.halted = False
        self.halt_reason = None
        self.fault = None
        self.rng = {"a": self.seed, "interval": 0, "counter": 0}
        self.tape_index = 0
        self.random_log = []
        self.host = {"window": 0, "split": 0, "screen": True,
                     "transcript": bool(int.from_bytes(self.memory[16:18], "big") & 1),
                     "commands": False, "input_stream": 0, "memory_streams": []}
        self._text = []
        self._events = []
        self._text_size = 0

    def _bounds(self, address, size, write=False):
        _integer(address, "memory address", 0)
        _integer(size, "memory size", 0)
        end = self.writable_end if write else len(self.memory)
        if address + size > end:
            raise Word16Error("Memory write outside dynamic region" if write else "Memory read out of bounds")

    def _read(self, address, width=8):
        size = width // 8
        self._bounds(address, size)
        return int.from_bytes(self.memory[address:address + size], "big")

    def _write(self, address, width, value):
        size = width // 8
        self._bounds(address, size, True)
        value = _integer(value) & ((1 << width) - 1)
        self.memory[address:address + size] = value.to_bytes(size, "big")
        if address < 18 and address + size > 16:
            self.host["transcript"] = bool(self._read(16, 16) & 1)

    def _pop(self, indirect=False):
        if len(self.stack) <= self.frames[-1]["base"]:
            raise Word16Error("Current frame stack underflow")
        return self.stack[-1] if indirect else self.stack.pop()

    def _push(self, value):
        if len(self.stack) >= MAX_STACK:
            raise Word16Error("Stack budget exceeded")
        self.stack.append(_u16(value))

    def _read_var(self, index, indirect=False):
        _integer(index, "variable index", 0, 255)
        if index == 0:
            return self._pop(indirect)
        if index < 16:
            if index > len(self.frames[-1]["locals"]):
                raise Word16Error("Local variable does not exist")
            return self.frames[-1]["locals"][index - 1]
        return self._read(self.layout["globals"] + 2 * (index - 16), 16)

    def _write_var(self, index, value, indirect=False):
        _integer(index, "variable index", 0, 255)
        value = _u16(value)
        if index == 0:
            if indirect:
                self._pop(True)
                self.stack[-1] = value
            else:
                self._push(value)
        elif index < 16:
            if index > len(self.frames[-1]["locals"]):
                raise Word16Error("Local variable does not exist")
            self.frames[-1]["locals"][index - 1] = value
        else:
            self._write(self.layout["globals"] + 2 * (index - 16), 16, value)

    def _expr(self, expr, temps):
        if not isinstance(expr, dict):
            return expr
        if "tmp" in expr:
            try:
                return temps[expr["tmp"]]
            except KeyError as exc:
                raise Word16Error("Temporary read before assignment") from exc
        name = expr["calc"]
        args = [self._expr(x, temps) for x in expr["args"]]
        if name == "eq": return args[0] == args[1]
        if name == "ne": return args[0] != args[1]
        if name in ("not", "any", "all"):
            if any(type(x) is not bool for x in args):
                raise Word16Error("Boolean operation requires booleans")
            return not args[0] if name == "not" else (any(args) if name == "any" else all(args))
        for arg in args:
            _bounded_integer(arg)
        a = args[0]
        if name == "u16": return _u16(a)
        if name == "s16": return _s16(a)
        if name == "mem8": return self._read(a)
        if name == "mem16": return self._read(a, 16)
        b = args[1]
        if name == "add": return _bounded_integer(a + b)
        if name == "sub": return _bounded_integer(a - b)
        if name == "mul": return _bounded_integer(a * b)
        if name in ("div", "mod"):
            if b == 0:
                raise Word16Error("Division by zero")
            quotient = abs(a) // abs(b)
            if (a < 0) != (b < 0): quotient = -quotient
            return quotient if name == "div" else a - quotient * b
        if name == "and": return a & b
        if name == "or": return a | b
        if name == "xor": return a ^ b
        if name in ("shl", "shr"):
            _integer(b, "shift count", 0, 63)
            return _bounded_integer(a << b if name == "shl" else a >> b)
        if name == "lt": return a < b
        if name == "gt": return a > b
        if name == "le": return a <= b
        if name == "ge": return a >= b
        raise Word16Error("Unsupported calculation")

    def _object(self, number):
        _integer(number, "object number", 1, 255)
        address = self.layout["objects"] + 62 + 9 * (number - 1)
        self._bounds(address, 9, True)
        return address

    def _link(self, obj, offset):
        return 0 if obj == 0 else self._read(self._object(obj) + offset)

    def _detach(self, obj):
        record = self._object(obj)
        parent, sibling = self._read(record + 4), self._read(record + 5)
        if parent:
            parent_record = self._object(parent)
            current = self._read(parent_record + 6)
            previous, seen = None, set()
            while current != obj:
                if not current or current in seen:
                    raise Word16Error("Object is absent from its parent's child list")
                seen.add(current)
                previous = current
                current = self._link(current, 5)
            target = parent_record + 6 if previous is None else self._object(previous) + 5
            self._write(target, 8, sibling)
        self._write(record + 4, 8, 0)
        self._write(record + 5, 8, 0)

    def _properties(self, obj):
        table = self._read(self._object(obj) + 7, 16)
        at = table + 1 + 2 * self._read(table)
        previous = 32
        out = []
        for _ in range(32):
            header = self._read(at)
            at += 1
            if header == 0:
                return out
            number, size = header & 31, (header >> 5) + 1
            if not 0 < number < previous:
                raise Word16Error("Invalid property ordering")
            self._bounds(at, size)
            out.append((number, at, size))
            previous = number
            at += size
        raise Word16Error("Property list exceeds budget")

    @staticmethod
    def _character(number):
        _integer(number, "character", 0, 1023)
        if number == 0: return ""
        # Retain Infocom's indentation controls until the output destination is
        # known. A memory stream must receive 9/11 rather than expanded spaces.
        if number == 9: return "\t"
        if number == 11: return "\v"
        if number == 13: return "\n"
        if 32 <= number <= 126: return chr(number)
        if 155 <= number < 155 + len(_EXTRA): return _EXTRA[number - 155]
        raise Word16Error("Unsupported output character")

    @staticmethod
    def _character_code(character):
        if character == "\t": return 9
        if character == "\v": return 11
        if character == "\n": return 13
        if 32 <= ord(character) <= 126: return ord(character)
        if character in _EXTRA: return 155 + _EXTRA.index(character)
        raise Word16Error("Unsupported input/output character")

    def _decode_text(self, address, seen=(), limit=None):
        if address in seen or len(seen) >= 16:
            raise Word16Error("Cyclic or excessive text abbreviation")
        at, codes = address, []
        while True:
            if limit is not None and at + 2 > limit:
                raise Word16Error("Text exceeds declared short-name extent")
            word = self._read(at, 16)
            at += 2
            codes.extend(((word >> 10) & 31, (word >> 5) & 31, word & 31))
            if word & 32768: break
            if len(codes) > 131072:
                raise Word16Error("Text decoding budget exceeded")
        output, alphabet, i = [], 0, 0
        while i < len(codes):
            code = codes[i]
            i += 1
            if code in (4, 5):
                alphabet = code - 3
                continue
            if code == 0:
                output.append(" ")
            elif code in (1, 2, 3):
                if i >= len(codes):
                    break  # A final incomplete construction has no output.
                entry = 32 * (code - 1) + codes[i]
                i += 1
                target = 2 * self._read(self.layout["abbreviations"] + entry * 2, 16)
                output.append(self._decode_text(target, seen + (address,)))
            elif alphabet == 2 and code == 6:
                if i + 1 >= len(codes): break
                output.append(self._character(codes[i] * 32 + codes[i + 1]))
                i += 2
            else:
                output.append(_ALPHABETS[alphabet][code - 6])
            alphabet = 0
            if len(output) > MAX_TEXT:
                raise Word16Error("Decoded text exceeds output budget")
        result = "".join(output)
        if len(result) > MAX_TEXT:
            raise Word16Error("Decoded text exceeds output budget")
        return result

    def _library(self, name, args):
        for arg in args:
            _integer(arg)
        if name.startswith("tree."):
            op, obj = name[5:], args[0]
            if op in ("parent", "sibling", "child"):
                return self._link(obj, {"parent": 4, "sibling": 5, "child": 6}[op])
            if op == "detach":
                self._detach(obj)
                return None
            if op == "insert":
                destination = args[1]
                self._object(obj)
                dest_record = self._object(destination)
                ancestor, seen = destination, set()
                while ancestor:
                    if ancestor == obj or ancestor in seen:
                        raise Word16Error("Insertion would create an object cycle")
                    seen.add(ancestor)
                    ancestor = self._link(ancestor, 4)
                self._detach(obj)
                record = self._object(obj)
                first = self._read(dest_record + 6)
                self._write(record + 4, 8, destination)
                self._write(record + 5, 8, first)
                self._write(dest_record + 6, 8, obj)
                return None
            if op == "name":
                table = self._read(self._object(obj) + 7, 16)
                words = self._read(table)
                return self._decode_text(table + 1, limit=table + 1 + words * 2) if words else ""
        if name.startswith("attribute."):
            obj, bit = args
            _integer(bit, "attribute bit", 0, 31)
            at = self._object(obj) + bit // 8
            mask, old = 128 >> (bit % 8), self._read(at)
            op = name[10:]
            if op == "test": return bool(old & mask)
            self._write(at, 8, old | mask if op == "set" else old & ~mask)
            return None
        if name.startswith("property."):
            op = name[9:]
            if op == "length":
                return 0 if args[0] == 0 else (self._read(args[0] - 1) >> 5) + 1
            obj, number = args[:2]
            _integer(number, "property number", 0 if op == "next" else 1, 31)
            properties = self._properties(obj)
            if op == "next" and number == 0:
                return properties[0][0] if properties else 0
            match = next((row for row in properties if row[0] == number), None)
            if match is None:
                if op == "get": return self._read(self.layout["objects"] + 2 * (number - 1), 16)
                if op == "address": return 0
                raise Word16Error("Requested property does not exist")
            _, at, size = match
            if op == "address": return at
            if op == "next":
                index = properties.index(match) + 1
                return properties[index][0] if index < len(properties) else 0
            if size not in (1, 2):
                raise Word16Error("Scalar property must occupy one or two bytes")
            if op == "get": return self._read(at, size * 8)
            if op == "put":
                self._write(at, size * 8, args[2])
                return None
        if name == "text.decode": return self._decode_text(args[0])
        if name == "text.character": return self._character(args[0])
        if name == "text.number": return str(args[0])
        raise Word16Error("Unsupported layout library")

    def _emit(self, value):
        if not isinstance(value, str):
            raise Word16Error("Text emission requires a string")
        self._text_size += len(value.encode("utf-8"))
        if self._text_size > MAX_TEXT:
            raise Word16Error("Per-run output budget exceeded")
        streams = self.host["memory_streams"]
        if streams:
            stream = streams[-1]
            codes = [self._character_code(c) for c in value]
            self._bounds(stream["table"] + 2 + stream["count"], len(codes), True)
            if stream["count"] + len(codes) > 65535:
                raise Word16Error("Memory text stream exceeds word count")
            start = stream["table"] + 2 + stream["count"]
            self.memory[start:start + len(codes)] = bytes(codes)
            stream["count"] += len(codes)
            return
        # Headless unwrapped presentation: source indentation and sentence-gap
        # controls become spaces. Their exact ZSCII bytes survive memory output.
        expanded = value.replace("\t", "   ").replace("\v", "  ")
        self._text_size += len(expanded.encode("utf-8")) - len(value.encode("utf-8"))
        if self._text_size > MAX_TEXT:
            raise Word16Error("Expanded text exceeds per-run output budget")
        value = expanded
        if self.host["screen"] and self.host["window"] == 0:
            self._text.append(value)
        if value:
            self._events.append({"type": "text", "window": self.host["window"],
                                 "screen": self.host["screen"], "transcript": self.host["transcript"], "text": value})

    def _random(self, n):
        _integer(n, "random range", -32768, 32767)
        if n <= 0:
            seed = -n
            if seed == 0:
                self.rng = {"a": self.seed, "interval": 0, "counter": 0}
            elif seed < 1000:
                self.rng.update(interval=seed, counter=0)
            else:
                self.rng = {"a": seed, "interval": 0, "counter": 0}
            result = 0
        elif self.random_tape is not None:
            if self.tape_index >= len(self.random_tape):
                raise Word16Error("Random tape exhausted")
            item = self.random_tape[self.tape_index]
            if item["range"] != n:
                raise Word16Error("Random tape range mismatch")
            result = item["value"]
            self.tape_index += 1
        elif self.rng["interval"]:
            result = self.rng["counter"] % n + 1
            self.rng["counter"] = (self.rng["counter"] + 1) % self.rng["interval"]
        else:
            # Declared Frotz 2.44 compatibility policy; no Frotz code is loaded.
            self.rng["a"] = (0x015A4E35 * self.rng["a"] + 1) & 0xffffffff
            result = ((self.rng["a"] >> 16) & 0x7fff) % n + 1
        self.random_log.append({"range": n, "value": result})
        return result

    def _host(self, action, args):
        for arg in args:
            _integer(arg)
        if action == "status":
            if args: raise Word16Error("Status takes no arguments")
            self._events.append({"type": "status", **self._score()})
            return
        if action == "window":
            if len(args) != 1 or args[0] not in (0, 1):
                raise Word16Error("Unsupported window")
            self.host["window"] = args[0]
        elif action == "split":
            if len(args) != 1 or not 0 <= args[0] <= 255:
                raise Word16Error("Invalid window split")
            self.host["split"] = args[0]
            if args[0] == 0: self.host["window"] = 0
        elif action == "input_stream":
            if len(args) != 1 or args[0] not in (0, 1):
                raise Word16Error("Unsupported input stream")
            self.host["input_stream"] = args[0]
        elif action == "output_stream":
            if not 1 <= len(args) <= 2:
                raise Word16Error("Invalid output stream arguments")
            stream = _s16(args[0])
            if stream == 0: return
            if abs(stream) in (1, 2, 4):
                key = {1: "screen", 2: "transcript", 4: "commands"}[abs(stream)]
                self.host[key] = stream > 0
                if abs(stream) == 2:
                    flags = self._read(16, 16)
                    self._write(16, 16, flags | 1 if stream > 0 else flags & ~1)
            elif stream == 3:
                if len(args) != 2 or len(self.host["memory_streams"]) >= 16:
                    raise Word16Error("Invalid memory output stream")
                self._bounds(args[1], 2, True)
                self.host["memory_streams"].append({"table": args[1], "count": 0})
            elif stream == -3:
                if not self.host["memory_streams"]:
                    raise Word16Error("Memory output stream is not active")
                item = self.host["memory_streams"].pop()
                self._write(item["table"], 16, item["count"])
            else:
                raise Word16Error("Unsupported output stream")
        elif action == "sound":
            if not args or args[0] not in (1, 2):
                raise Word16Error("Only declared simple sound events are supported")
        else:
            raise Word16Error("Unsupported host action")
        self._events.append({"type": action, "args": args})

    def _goto(self, target):
        _integer(target, "control target", 0, len(self.memory) - 1)
        if target not in self.blocks:
            raise Word16Error(f"Missing lowered control target {target:#x}")
        self.pc = target

    def _return(self, value):
        value = _u16(value)
        if len(self.frames) == 1:
            self.halted, self.halt_reason = True, "returned_from_root"
            return
        frame = self.frames.pop()
        del self.stack[frame["base"]:]
        self._write_var(frame["store"], value)
        self._goto(frame["resume"])

    def _nodes(self, nodes, temps):
        for node in nodes:
            op = node["op"]
            expr = lambda field: self._expr(node[field], temps)
            if op == "let": temps[node["name"]] = expr("value")
            elif op == "read_var": temps[node["dest"]] = self._read_var(expr("index"), node.get("indirect", False))
            elif op == "write_var": self._write_var(expr("index"), expr("value"), node.get("indirect", False))
            elif op == "write_mem": self._write(expr("address"), node["width"], expr("value"))
            elif op == "push": self._push(expr("value"))
            elif op == "pop": temps[node["dest"]] = self._pop()
            elif op == "if":
                condition = expr("condition")
                if type(condition) is not bool: raise Word16Error("Conditional requires boolean")
                if self._nodes(node["then"] if condition else node.get("else", []), temps): return True
            elif op == "goto":
                self._goto(expr("target"))
                return True
            elif op == "call":
                target = expr("target")
                _integer(target, "call target", 0, len(self.memory) - 1)
                args = [self._expr(x, temps) for x in node["args"]]
                for value in args: _integer(value)
                if target == 0:
                    self._write_var(node["store"], 0)
                    self._goto(node["resume"])
                    return True
                if target not in self.functions:
                    raise Word16Error(f"Missing lowered function target {target:#x}")
                function, guard = self.functions[target], self._function_guards[target]
                if self.memory[target:target + len(guard)] != guard:
                    raise Word16Error("Unsupported self-modified function header")
                if len(self.frames) >= MAX_FRAMES:
                    raise Word16Error("Call frame budget exceeded")
                locals_ = list(function["locals"])
                for i, value in enumerate(args[:len(locals_)]): locals_[i] = _u16(value)
                self.frames.append({"locals": locals_, "base": len(self.stack),
                                    "resume": node["resume"], "store": node["store"]})
                self._goto(function["entry"])
                return True
            elif op == "return":
                self._return(expr("value"))
                return True
            elif op == "emit": self._emit(expr("value"))
            elif op == "random": temps[node["dest"]] = self._random(expr("range"))
            elif op == "library":
                result = self._library(node["name"], [self._expr(x, temps) for x in node["args"]])
                if "dest" in node: temps[node["dest"]] = result
            elif op == "input":
                text, parse = expr("text"), expr("parse")
                self._bounds(text, 1, True)
                if parse: self._bounds(parse, 2, True)
                self._host("status", [])
                self.pending_input = {"text": text, "parse": parse, "resume": node["resume"]}
                self.pc = node["resume"]
                return True
            elif op == "persist":
                if node["mode"] == "save":
                    transferred = self._nodes(node["success"], temps)
                    if not transferred: self._goto(node["resume"])
                    self._game_slot = self._state(include_slot=False, include_output=False)
                    self._events.append({"type": "save", "success": True})
                elif self._game_slot is not None:
                    text, events, size = self._text, self._events, self._text_size
                    flags = bytes(self.memory[16:18])
                    slot = self._game_slot
                    self.restore(slot)
                    self._game_slot = slot
                    self.memory[16:18] = flags
                    self.host["transcript"] = bool(int.from_bytes(flags, "big") & 1)
                    self._text, self._events, self._text_size = text, events, size
                    self._events.append({"type": "restore", "success": True})
                else:
                    transferred = self._nodes(node["failure"], temps)
                    if not transferred: self._goto(node["resume"])
                    self._events.append({"type": "restore", "success": False})
                return True
            elif op == "restart":
                text, events, size = self._text, self._events, self._text_size
                self._initialize(bytes(self.memory[16:18]))
                self._text, self._events, self._text_size = text, events, size
                self._events.append({"type": "restart"})
                return True
            elif op == "quit":
                self.halted, self.halt_reason = True, "quit"
                return True
            elif op == "host": self._host(node["action"], [self._expr(x, temps) for x in node["args"]])
            else: raise Word16Error("Unsupported execution node")
        return False

    def _score(self):
        base = self.layout["globals"]
        return {"location": self._read(base, 16), "score": _s16(self._read(base + 2, 16)), "moves": self._read(base + 4, 16)}

    def run(self, max_steps=2_000_000):
        _integer(max_steps, "step budget", 1, 100_000_000)
        if self.fault is not None:
            raise Word16Error("Execution is faulted; restore a qualified checkpoint")
        steps = 0
        try:
            while not self.halted and self.pending_input is None and steps < max_steps:
                block = self.blocks.get(self.pc)
                if block is None:
                    raise Word16Error(f"Missing lowered control target {self.pc:#x}")
                guard = self._guards[self.pc]
                if self.memory[self.pc:self.pc + len(guard)] != guard:
                    raise Word16Error(f"Unsupported self-modified code at {self.pc:#x}")
                self.executed_blocks.add(self.pc)
                steps += 1
                if not self._nodes(block["nodes"], {}):
                    self._goto(block["next"])
        except (Word16Error, IndexError, KeyError, TypeError, OverflowError) as exc:
            self.fault = str(exc)
            raise Word16Error(f"UIL execution failed at {self.pc:#x}: {exc}") from exc
        status = "halted" if self.halted else "input" if self.pending_input is not None else "budget_exhausted"
        result = {"status": status, "text": "".join(self._text), "steps": steps, "pc": self.pc,
                  **self._score(), "events": self._events}
        if self.halt_reason is not None: result["halt_reason"] = self.halt_reason
        self._text, self._events, self._text_size = [], [], 0
        return result

    @staticmethod
    def _dictionary_word(codes):
        chars = []
        for code in codes:
            character = Word16Runtime._character(code)
            if code == 32:
                chars.append(0)
            else:
                found = False
                for alphabet, letters in enumerate(_ALPHABETS):
                    if character in letters and not (alphabet == 2 and letters.index(character) == 0):
                        if alphabet: chars.append(alphabet + 3)
                        chars.append(letters.index(character) + 6)
                        found = True
                        break
                if not found: chars.extend((5, 6, code >> 5, code & 31))
            if len(chars) >= 6: break
        chars = (chars + [5] * 6)[:6]
        first = (chars[0] << 10) | (chars[1] << 5) | chars[2]
        last = 32768 | (chars[3] << 10) | (chars[4] << 5) | chars[5]
        return first.to_bytes(2, "big") + last.to_bytes(2, "big")

    @staticmethod
    def _command_codes(text):
        if not isinstance(text, str) or len(text.encode("utf-8")) > 4096 or any(c in text for c in "\x00\r\n"):
            raise Word16Error("Command must be one bounded line")
        return [Word16Runtime._character_code(c) for c in text.lower()]

    def _input_bytes(self, text, pending):
        codes = self._command_codes(text)
        maximum = self._read(pending["text"]) - 1
        if maximum < 0: raise Word16Error("Invalid text input capacity")
        codes = codes[:maximum]
        self._bounds(pending["text"] + 1, len(codes) + 1, True)
        parse = pending["parse"]
        if not parse: return codes, []
        capacity = self._read(parse)
        self._bounds(parse, 2 + 4 * capacity, True)
        dictionary = self.layout["dictionary"]
        separator_count = self._read(dictionary)
        self._bounds(dictionary + 1, separator_count + 3)
        separators = set(self.memory[dictionary + 1:dictionary + 1 + separator_count])
        at = dictionary + 1 + separator_count
        entry_size = self._read(at)
        count = abs(_s16(self._read(at + 1, 16)))
        start = at + 3
        if entry_size < 4: raise Word16Error("Invalid dictionary entry size")
        self._bounds(start, entry_size * count)
        lookup = {bytes(self.memory[start + i * entry_size:start + i * entry_size + 4]): start + i * entry_size for i in range(count)}
        tokens, index = [], 0
        while index < len(codes) and len(tokens) < capacity:
            if codes[index] == 32:
                index += 1
                continue
            begin = index
            index += 1
            if codes[begin] not in separators:
                while index < len(codes) and codes[index] != 32 and codes[index] not in separators: index += 1
            key = self._dictionary_word(codes[begin:index])
            tokens.append((lookup.get(key, 0), index - begin, begin + 1))
        return codes, tokens

    def command(self, text, max_steps=2_000_000):
        if self.pending_input is None or self.halted or self.fault is not None:
            raise Word16Error("Command requires a live pending input boundary")
        _integer(max_steps, "step budget", 1, 100_000_000)
        pending = self.pending_input
        codes, tokens = self._input_bytes(text, pending)
        address = pending["text"] + 1
        self.memory[address:address + len(codes) + 1] = bytes(codes) + b"\0"
        parse = pending["parse"]
        if parse:
            self._write(parse + 1, 8, len(tokens))
            for index, (word, length, position) in enumerate(tokens):
                at = parse + 2 + index * 4
                self._write(at, 16, word)
                self._write(at + 2, 8, length)
                self._write(at + 3, 8, position)
        if self.host["transcript"] or self.host["commands"]:
            self._events.append({"type": "input_echo", "text": text, "transcript": self.host["transcript"], "commands": self.host["commands"]})
        self.pending_input = None
        self.pc = pending["resume"]
        return self.run(max_steps=max_steps)

    def _state(self, include_slot=True, include_output=True):
        return {"format": CHECKPOINT_FORMAT, "package_sha256": self.package_digest,
                "memory": self.memory.hex(), "pc": self.pc, "frames": copy.deepcopy(self.frames),
                "stack": list(self.stack), "pending_input": copy.deepcopy(self.pending_input),
                "halted": self.halted, "halt_reason": self.halt_reason, "fault": self.fault,
                "seed": self.seed, "rng": dict(self.rng), "random_tape": copy.deepcopy(self.random_tape),
                "tape_index": self.tape_index, "random_log": copy.deepcopy(self.random_log),
                "host": copy.deepcopy(self.host), "output": list(self._text) if include_output else [],
                "events": copy.deepcopy(self._events) if include_output else [],
                "output_size": self._text_size if include_output else 0,
                "game_slot": copy.deepcopy(self._game_slot) if include_slot else None}

    def snapshot(self):
        return self._state()

    def _validate_state(self, state, nested=False):
        required = ("format", "package_sha256", "memory", "pc", "frames", "stack", "pending_input", "halted", "halt_reason", "fault", "seed", "rng", "random_tape", "tape_index", "random_log", "host", "output", "events", "output_size", "game_slot")
        _keys(state, required, label="checkpoint")
        if state["format"] != CHECKPOINT_FORMAT or state["package_sha256"] != self.package_digest:
            raise Word16Error("Checkpoint belongs to another program/profile")
        memory = _hex(state["memory"], "checkpoint memory", len(self.initial))
        if len(memory) != len(self.initial) or memory[self.writable_end:] != self.initial[self.writable_end:]:
            raise Word16Error("Checkpoint changes immutable memory")
        pc = _integer(state["pc"], "checkpoint PC", 0, len(memory))
        if type(state["halted"]) is not bool:
            raise Word16Error("Invalid halted flag")
        if state["halt_reason"] not in (None, "quit", "returned_from_root"):
            raise Word16Error("Invalid halt reason")
        if state["fault"] is not None and (not isinstance(state["fault"], str) or len(state["fault"]) > 4096):
            raise Word16Error("Invalid fault state")
        stack, frames = state["stack"], state["frames"]
        if not isinstance(stack, list) or len(stack) > MAX_STACK or not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
            raise Word16Error("Invalid checkpoint stacks")
        for value in stack: _integer(value, "stack value", 0, 65535)
        previous_base = 0
        for index, frame in enumerate(frames):
            _keys(frame, ("locals", "base", "resume", "store"), label="frame")
            base = _integer(frame["base"], "frame base", previous_base, len(stack))
            previous_base = base
            if not isinstance(frame["locals"], list) or len(frame["locals"]) > 15:
                raise Word16Error("Invalid frame locals")
            for value in frame["locals"]: _integer(value, "local", 0, 65535)
            if index == 0:
                if base != 0 or frame["locals"] or frame["resume"] is not None or frame["store"] is not None:
                    raise Word16Error("Invalid root frame")
            else:
                _integer(frame["resume"], "return PC", 0, len(memory) - 1)
                if frame["resume"] not in self.blocks: raise Word16Error("Missing return block")
                store = _integer(frame["store"], "return variable", 0, 255)
                if 0 < store < 16 and store > len(frames[index - 1]["locals"]):
                    raise Word16Error("Return local does not exist")
        pending = state["pending_input"]
        if pending is not None:
            _keys(pending, ("text", "parse", "resume"), label="pending input")
            _integer(pending["text"], "text buffer", 0, self.writable_end - 1)
            _integer(pending["parse"], "parse buffer", 0, self.writable_end - 2)
            if pending["resume"] != pc or pc not in self.blocks or state["halted"]:
                raise Word16Error("Invalid input continuation")
        elif not state["halted"] and state["fault"] is None and pc not in self.blocks:
            raise Word16Error("Missing checkpoint block")
        _integer(state["seed"], "checkpoint seed", 0, 0xffffffff)
        rng = state["rng"]
        _keys(rng, ("a", "interval", "counter"), label="random state")
        _integer(rng["a"], "random accumulator", 0, 0xffffffff)
        interval = _integer(rng["interval"], "random interval", 0, 999)
        _integer(rng["counter"], "random counter", 0, max(0, interval - 1))
        tape = self._validate_tape(state["random_tape"])
        _integer(state["tape_index"], "random tape cursor", 0, len(tape) if tape is not None else 0)
        if not isinstance(state["random_log"], list) or len(state["random_log"]) > 1_000_000:
            raise Word16Error("Invalid random log")
        for row in state["random_log"]:
            _keys(row, ("range", "value"), label="random result")
            n = _integer(row["range"], "logged range", -32768, 32767)
            _integer(row["value"], "logged value", 1 if n > 0 else 0, n if n > 0 else 0)
        host = state["host"]
        _keys(host, ("window", "split", "screen", "transcript", "commands", "input_stream", "memory_streams"), label="host state")
        _integer(host["window"], "window", 0, 1)
        _integer(host["split"], "window split", 0, 255)
        _integer(host["input_stream"], "input stream", 0, 1)
        for field in ("screen", "transcript", "commands"):
            if type(host[field]) is not bool: raise Word16Error("Invalid host flag")
        if not isinstance(host["memory_streams"], list) or len(host["memory_streams"]) > 16:
            raise Word16Error("Invalid memory streams")
        for stream in host["memory_streams"]:
            _keys(stream, ("table", "count"), label="memory stream")
            at = _integer(stream["table"], "stream table", 0, self.writable_end - 2)
            _integer(stream["count"], "stream count", 0, min(65535, self.writable_end - at - 2))
        if not isinstance(state["output"], list) or any(not isinstance(x, str) for x in state["output"]) or sum(len(x.encode("utf-8")) for x in state["output"]) > MAX_TEXT:
            raise Word16Error("Invalid pending output")
        _integer(state["output_size"], "output size", 0, MAX_TEXT)
        if not isinstance(state["events"], list) or len(state["events"]) > MAX_TEXT or len(_canonical(state["events"])) > MAX_CHECKPOINT_BYTES:
            raise Word16Error("Invalid pending events")
        if nested and state["game_slot"] is not None:
            raise Word16Error("Nested saved-game slots are invalid")
        if state["game_slot"] is not None:
            self._validate_state(state["game_slot"], nested=True)
        return memory

    def restore(self, snapshot):
        """Validate every field and nested slot before changing live state."""
        state = copy.deepcopy(snapshot)
        memory = self._validate_state(state)
        self.memory = bytearray(memory)
        self.pc, self.frames, self.stack = state["pc"], state["frames"], state["stack"]
        self.pending_input, self.halted = state["pending_input"], state["halted"]
        self.halt_reason, self.fault = state["halt_reason"], state["fault"]
        self.seed, self.rng = state["seed"], state["rng"]
        self.random_tape, self.tape_index = state["random_tape"], state["tape_index"]
        self.random_log, self.host = state["random_log"], state["host"]
        self._text, self._events, self._text_size = state["output"], state["events"], state["output_size"]
        self._game_slot = state["game_slot"]

    def save_checkpoint(self, path):
        _atomic_json(path, self.snapshot())

    def load_checkpoint(self, path):
        with Path(path).open("rb") as stream:
            state = _json_load(stream, MAX_CHECKPOINT_BYTES)
        self.restore(state)


def _atomic_json(path, value):
    path = Path(path)
    payload = _canonical(value)
    if len(payload) > MAX_CHECKPOINT_BYTES:
        raise Word16Error("Checkpoint/output exceeds byte budget")
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _same_path(left, right):
    """Identify lexical/symlink and existing hardlink aliases before CLI writes."""
    left, right = Path(left).resolve(), Path(right).resolve()
    if left == right:
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False


def _protect_cli_inputs(args):
    inputs = [("package", args.package)]
    if args.commands:
        inputs.append(("commands", args.commands))
    outputs = [(name, getattr(args, name)) for name in ("checkpoint", "transcript")
               if getattr(args, name)]
    for output_name, output in outputs:
        for input_name, source in inputs:
            if _same_path(output, source):
                raise Word16Error(f"--{output_name} would replace the {input_name} input")
    if args.checkpoint and args.transcript and _same_path(args.checkpoint, args.transcript):
        raise Word16Error("Checkpoint and transcript outputs must be distinct")
    # Resuming and refreshing one checkpoint is intentional. A transcript has
    # different semantics and must never replace that resume input.
    if args.resume and args.transcript and _same_path(args.resume, args.transcript):
        raise Word16Error("--transcript would replace the resume input")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a self-contained word16 UIL program")
    parser.add_argument("package")
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--commands", help="JSON list of command strings")
    parser.add_argument("--transcript")
    parser.add_argument("--checkpoint", help="Write complete state after every input turn")
    parser.add_argument("--resume", help="Restore a compatible checkpoint before execution")
    args = parser.parse_args(argv)
    try:
        _protect_cli_inputs(args)
        commands = None
        if args.commands:
            with Path(args.commands).open("rb") as stream:
                commands = _json_load(stream, 1024 * 1024)
            if not isinstance(commands, list):
                raise Word16Error("--commands must contain a JSON list of strings")
            for command in commands:
                Word16Runtime._command_codes(command)
    except Word16Error as exc:
        parser.error(str(exc))
    runtime = Word16Runtime(load_program(args.package), seed=args.seed)
    if args.resume: runtime.load_checkpoint(args.resume)
    transcript = []
    def record(result, command=None):
        transcript.append({"command": command, **result})
        if result["text"]: print(result["text"], end="", flush=True)
        if args.checkpoint: runtime.save_checkpoint(args.checkpoint)
        if args.transcript: _atomic_json(args.transcript, transcript)
        return result
    result = record(runtime.run())
    if commands is not None:
        for command in commands:
            if result["status"] != "input": break
            result = record(runtime.command(command), command)
    else:
        while result["status"] == "input":
            try:
                command = input("" if not sys.stdin.isatty() else "> ")
            except EOFError:
                break
            result = record(runtime.command(command), command)
    if result["status"] == "budget_exhausted":
        print("Execution budget exhausted; state remains resumable.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
