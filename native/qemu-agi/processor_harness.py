"""Read bounded CPU-owned instruction facts through an existing QMP owner.

There is no AGI opcode decoder here. Structural checks bind native records to
the exact loaded bytes; operand meaning and encoded control flow come from the
shared native decoder. Static pages do not establish entry reachability.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from fdisbull.processor import DecodedInstruction, Location, ProcessorInfo, Successor
from harness import HarnessError


SCHEMA = "fdisbull-agi-native-instructions-1"
DECODER = {"identity": "fdisbull.qemu.agi", "version": "1", "address_unit": "byte"}


def _same(left, right):
    """Compare JSON values without treating bool as an integer alias."""
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == \
        json.dumps(right, sort_keys=True, separators=(",", ":"))


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _operands(values, maximum=3):
    if type(values) is not list or len(values) > maximum:
        raise HarnessError("Invalid native instruction operands")
    widths = {"variable": 8, "flag": 1, "actor": 8, "view": 8,
              "loop": 8, "cel": 8, "u8": 8, "u16": 16, "s16": 16}
    for operand in values:
        if type(operand) is not dict or operand.get("kind") not in widths:
            raise HarnessError("Unknown native operand kind")
        kind = operand["kind"]
        field = "index" if kind in ("variable", "flag") else "value"
        if set(operand) != {"role", "kind", "width", "access", field} \
                or type(operand["role"]) is not str or not operand["role"] \
                or type(operand["width"]) is not int or operand["width"] != widths[kind] \
                or operand["access"] not in ("read", "write", "read_write", "reference"):
            raise HarnessError("Invalid native operand descriptor")
        lower, upper = (-32768, 32767) if kind == "s16" else \
            (0, 65535) if kind == "u16" else (0, 255)
        if not _integer(operand[field], lower, upper):
            raise HarnessError("Native operand value is outside its domain")


def validate_decode_page(page, *, code, source, start_pc=None, limit=None):
    """Validate one linear page without decoding or interpreting its opcodes."""
    if type(code) is not bytes or not 1 <= len(code) <= 65536:
        raise HarnessError("Native decode requires exact 1..65536-byte code")
    if type(source) is not dict or source.get("sha256") != sha256(code).hexdigest() \
            or type(source.get("size")) is not int or source["size"] != len(code) \
            or type(source.get("logic_id")) is not int or source["logic_id"] != 0 \
            or type(source.get("profile")) is not str or not source["profile"]:
        raise HarnessError("Native decode source identity differs")
    fields = {"schema", "decoder", "source", "evidence", "traversal", "start_pc",
              "limit", "next_pc", "stop", "instructions", "error"}
    if type(page) is not dict or set(page) != fields or page["schema"] != SCHEMA \
            or not _same(page["decoder"], DECODER) or not _same(page["source"], source) \
            or page["evidence"] != "static_decode" or page["traversal"] != "linear" \
            or not _integer(page["start_pc"], 0, len(code)) \
            or not _integer(page["limit"], 1, 64) \
            or not _integer(page["next_pc"], page["start_pc"], len(code)) \
            or page["stop"] not in ("end", "limit", "decode_fault"):
        raise HarnessError("Invalid native instruction page envelope")
    if start_pc is not None and not _same(page["start_pc"], start_pc) \
            or limit is not None and not _same(page["limit"], limit):
        raise HarnessError("Native page selectors differ from the request")
    rows = page["instructions"]
    if type(rows) is not list or len(rows) > page["limit"]:
        raise HarnessError("Native instruction page exceeded its record limit")
    cursor = page["start_pc"]
    row_fields = {"pc", "opcode", "size", "bytes", "mnemonic", "operation",
                  "operands", "conditions", "successors", "effect_class", "execution_support"}
    for row in rows:
        if type(row) is not dict or set(row) != row_fields \
                or not _integer(row["pc"], 0, len(code) - 1) or row["pc"] != cursor \
                or not _integer(row["size"], 1, min(64, len(code) - cursor)) \
                or not _integer(row["opcode"], 0, 255) or row["opcode"] != code[cursor] \
                or type(row["bytes"]) is not list \
                or any(not _integer(value, 0, 255) for value in row["bytes"]) \
                or row["bytes"] != list(code[cursor:cursor + row["size"]]) \
                or any(type(row[key]) is not str or not row[key] for key in ("mnemonic", "operation")) \
                or row["effect_class"] not in ("scalar", "flag", "control", "resource", "actor", "host") \
                or row["execution_support"] not in ("native", "pending_host", "unsupported_profile"):
            raise HarnessError("Native instruction identity or descriptor differs")
        _operands(row["operands"])
        conditions = row["conditions"]
        if type(conditions) is not list or len(conditions) > row["size"]:
            raise HarnessError("Invalid native condition tokens")
        previous, predicates = cursor, 0
        for token in conditions:
            if type(token) is not dict or token.get("kind") not in ("predicate", "or_begin", "or_end", "not") \
                    or not _integer(token.get("pc"), previous + 1, cursor + row["size"] - 1):
                raise HarnessError("Native condition token order or extent differs")
            previous = token["pc"]
            keys = {"kind", "pc"}
            if token["kind"] == "predicate":
                predicates += 1
                if predicates > 8:
                    raise HarnessError("Native condition predicate budget exceeded")
                keys |= {"opcode", "mnemonic", "operands"}
                if not _integer(token.get("opcode"), 0, 255) or token["opcode"] != code[token["pc"]] \
                        or type(token.get("mnemonic")) is not str or not token["mnemonic"]:
                    raise HarnessError("Invalid native predicate identity")
                _operands(token.get("operands"), maximum=2)
            if set(token) != keys:
                raise HarnessError("Unexpected native condition fields")
        if type(row["successors"]) is not list or len(row["successors"]) > 2:
            raise HarnessError("Invalid native static successors")
        for edge in row["successors"]:
            if type(edge) is not dict or set(edge) != {"kind", "pc", "in_range"} \
                    or edge["kind"] not in ("fallthrough", "branch", "true", "false") \
                    or not _integer(edge["pc"], -(2**31), 2**31 - 1) \
                    or type(edge["in_range"]) is not bool \
                    or edge["in_range"] != (0 <= edge["pc"] < len(code)):
                raise HarnessError("Invalid native static edge")
        cursor += row["size"]
    if page["next_pc"] != cursor:
        raise HarnessError("Native page has a gap or invented instruction extent")
    if page["stop"] == "decode_fault":
        fault = page["error"]
        if len(rows) == page["limit"] \
                or type(fault) is not dict or set(fault) != {"pc", "opcode", "code", "name"} \
                or not _integer(fault["pc"], 0, len(code) - 1) or fault["pc"] != cursor \
                or not _integer(fault["opcode"], 0, 255) or fault["opcode"] != code[cursor] \
                or not _integer(fault["code"], 1, 2**31 - 1) \
                or type(fault["name"]) is not str or not fault["name"]:
            raise HarnessError("Invalid native decode fault boundary")
    elif page["error"] is not None \
            or page["stop"] == "end" and cursor != len(code) \
            or page["stop"] == "limit" and (len(rows) != page["limit"] or cursor >= len(code)):
        raise HarnessError("Native page completion/limit is inconsistent")
    return deepcopy(page)


def read_decode_pages(vm, code, *, start_pc=0, max_instructions=256, page_limit=64):
    """Read a finite static batch; require all stopped native inputs unchanged.

    ``vm`` is the existing sole QMP owner. This function never resumes it.
    A final limit or decode fault remains visible in the returned pages.
    """
    if type(code) is not bytes or not 1 <= len(code) <= 65536 \
            or not _integer(start_pc, 0, len(code)) \
            or not _integer(max_instructions, 1, 4096) or not _integer(page_limit, 1, 64):
        raise ValueError("Invalid bounded native decode request")
    before, events_before = deepcopy(vm.state()), deepcopy(vm.events())
    pages, cursor, remaining = [], start_pc, max_instructions
    try:
        while remaining:
            count = min(page_limit, remaining)
            vm.set("agi-decode-pc", cursor)
            vm.set("agi-decode-limit", count)
            raw = vm.get("agi-decode-json")
            if type(raw) is not str or len(raw) > 2 * 1024**2:
                raise HarnessError("Native decode page must be bounded JSON text")
            try:
                page = json.loads(raw)
            except (ValueError, RecursionError) as error:
                raise HarnessError("Invalid native decode JSON") from error
            page = validate_decode_page(page, code=code, source=before["source"],
                                        start_pc=cursor, limit=count)
            pages.append(page)
            cursor = page["next_pc"]
            remaining -= len(page["instructions"])
            if page["stop"] != "limit":
                break
    finally:
        if not _same(before, vm.state()) or not _same(events_before, vm.events()):
            raise HarnessError("Metadata requests changed native state or retained events")
    return pages


class NativeAGIProcessor:
    """Adapt validated CPU facts to the existing in-process Processor protocol."""

    def __init__(self, code, pages):
        if type(pages) is not list or not 1 <= len(pages) <= 4096:
            raise HarnessError("Native processor requires bounded explicit pages")
        source = pages[0].get("source") if type(pages[0]) is dict else None
        self.pages = [validate_decode_page(page, code=code, source=source) for page in pages]
        self.source, self.code = deepcopy(source), code
        identity = sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.info = ProcessorInfo(DECODER["identity"], DECODER["version"],
            f"agi.raw:{identity}", "byte", ("decode", "static_successors"), None)
        self._rows = {}
        occupied = set()
        for page in self.pages:
            for row in page["instructions"]:
                previous = self._rows.get(row["pc"])
                if previous is not None:
                    if not _same(previous, row):
                        raise HarnessError("Conflicting native descriptions of the same source PC")
                    continue
                extent = set(range(row["pc"], row["pc"] + row["size"]))
                if occupied & extent:
                    raise HarnessError("Native page windows overlap instruction interiors")
                occupied.update(extent)
                self._rows[row["pc"]] = row

    @property
    def instructions(self):
        return [deepcopy(self._rows[pc]) for pc in sorted(self._rows)]

    def decode(self, program, location):
        if type(program) is not bytes or program != self.code:
            raise HarnessError("Processor program differs from its native source")
        if not isinstance(location, Location) or location.space != self.info.address_space:
            raise ValueError("Location is outside the native processor address space")
        row = self._rows.get(location.offset)
        if row is None:
            return None
        edges = tuple(Successor(edge["kind"],
            Location(location.space, edge["pc"]) if edge["in_range"] and edge["pc"] >= 0 else None,
            "native static decode; encoded target " + str(edge["pc"])) for edge in row["successors"])
        return DecodedInstruction(location, deepcopy(row), edges)
