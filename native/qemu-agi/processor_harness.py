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
SCHEMA_V2 = "fdisbull-agi-native-instructions-2"
DECODER_V2 = {"identity": "fdisbull.qemu.agi", "version": "2", "address_unit": "byte",
              "encoding": "agi-2.917", "decode_policy": "structural-1"}

# Schema one remains the exact contract of archived execution/scene evidence.
# Schema two broadens structural facts, not the native execution profiles.
_CONTRACTS = {
    SCHEMA: {"decoder": DECODER, "bytes": 64, "operands": 3,
             "tokens": 64, "predicates": 8, "predicate_operands": 2,
             "condition_operands": 16},
    SCHEMA_V2: {"decoder": DECODER_V2, "bytes": 1024, "operands": 7,
                "tokens": 256, "predicates": 64, "predicate_operands": 5,
                "condition_operands": 1024},
}
MAX_PAGE_JSON_BYTES = 8 * 1024**2


class NativePageSizeLimit(HarnessError):
    """A received page was not admitted because its JSON exceeded a bound."""

    def __init__(self, size, limit):
        self.size, self.limit = size, limit
        super().__init__(f"Native page JSON uses {size} bytes; limit is {limit}")


def _same(left, right):
    """Compare JSON values without treating bool as an integer alias."""
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == \
        json.dumps(right, sort_keys=True, separators=(",", ":"))


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _operands(values, maximum=3, *, schema=SCHEMA):
    if type(values) is not list or len(values) > maximum:
        raise HarnessError("Invalid native instruction operands")
    widths = {"variable": 8, "flag": 1, "actor": 8, "view": 8,
              "loop": 8, "cel": 8, "u8": 8, "u16": 16, "s16": 16}
    if schema == SCHEMA_V2:
        widths.update(picture=8, logic=8, room=8, sound=8, message=8,
                      inventory_object=8, word=16)
    for operand in values:
        if type(operand) is not dict or type(operand.get("kind")) is not str \
                or operand["kind"] not in widths:
            raise HarnessError("Unknown native operand kind")
        kind = operand["kind"]
        field = "index" if kind in ("variable", "flag") else "value"
        if set(operand) != {"role", "kind", "width", "access", field} \
                or type(operand["role"]) is not str or not operand["role"] \
                or type(operand["width"]) is not int or operand["width"] != widths[kind] \
                or operand["access"] not in ("read", "write", "read_write", "reference"):
            raise HarnessError("Invalid native operand descriptor")
        lower, upper = (-32768, 32767) if kind == "s16" else \
            (0, 65535) if kind in ("u16", "word") else (0, 255)
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
    contract = _CONTRACTS.get(page.get("schema")) if type(page) is dict \
        and type(page.get("schema")) is str else None
    if type(page) is not dict or set(page) != fields or contract is None \
            or not _same(page["decoder"], contract["decoder"]) or not _same(page["source"], source) \
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
    schema = page["schema"]
    effects = ("scalar", "flag", "control", "resource", "actor", "host")
    edges = ("fallthrough", "branch", "true", "false")
    if schema == SCHEMA_V2:
        effects += ("unknown",)
        edges += ("assumed_return", "assumed_fallthrough")
    for row in rows:
        if type(row) is not dict or set(row) != row_fields \
                or not _integer(row["pc"], 0, len(code) - 1) or row["pc"] != cursor \
                or not _integer(row["size"], 1, min(contract["bytes"], len(code) - cursor)) \
                or not _integer(row["opcode"], 0, 255) or row["opcode"] != code[cursor] \
                or type(row["bytes"]) is not list \
                or any(not _integer(value, 0, 255) for value in row["bytes"]) \
                or row["bytes"] != list(code[cursor:cursor + row["size"]]) \
                or any(type(row[key]) is not str or not row[key] for key in ("mnemonic", "operation")) \
                or row["effect_class"] not in effects \
                or row["execution_support"] not in ("native", "pending_host", "unsupported_profile"):
            raise HarnessError("Native instruction identity or descriptor differs")
        _operands(row["operands"], maximum=contract["operands"], schema=schema)
        conditions = row["conditions"]
        if type(conditions) is not list or len(conditions) > min(row["size"], contract["tokens"]):
            raise HarnessError("Invalid native condition tokens")
        previous, predicates, condition_operands = cursor, 0, 0
        for token in conditions:
            if type(token) is not dict or token.get("kind") not in ("predicate", "or_begin", "or_end", "not") \
                    or not _integer(token.get("pc"), previous + 1, cursor + row["size"] - 1):
                raise HarnessError("Native condition token order or extent differs")
            previous = token["pc"]
            keys = {"kind", "pc"}
            if token["kind"] == "predicate":
                predicates += 1
                if predicates > contract["predicates"]:
                    raise HarnessError("Native condition predicate budget exceeded")
                keys |= {"opcode", "mnemonic", "operands"}
                if not _integer(token.get("opcode"), 0, 255) or token["opcode"] != code[token["pc"]] \
                        or type(token.get("mnemonic")) is not str or not token["mnemonic"]:
                    raise HarnessError("Invalid native predicate identity")
                maximum = 256 if schema == SCHEMA_V2 and token["mnemonic"] == "said" \
                    else contract["predicate_operands"]
                _operands(token.get("operands"), maximum=maximum, schema=schema)
                condition_operands += len(token["operands"])
                if condition_operands > contract["condition_operands"]:
                    raise HarnessError("Native condition operand budget exceeded")
                if schema == SCHEMA_V2 and token["mnemonic"] == "said":
                    operands = token["operands"]
                    count = {"role": "word_count", "kind": "u8", "width": 8,
                             "access": "read", "value": len(operands) - 1}
                    if not operands or not _same(operands[0], count) \
                            or any(operand["role"] != "word" or operand["kind"] != "word"
                                   or operand["access"] != "reference" for operand in operands[1:]):
                        raise HarnessError("Native said operand shape differs")
            if set(token) != keys:
                raise HarnessError("Unexpected native condition fields")
        if type(row["successors"]) is not list or len(row["successors"]) > 2:
            raise HarnessError("Invalid native static successors")
        for edge in row["successors"]:
            if type(edge) is not dict or set(edge) != {"kind", "pc", "in_range"} \
                    or edge["kind"] not in edges \
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


def request_decode_page(vm, code, source, *, start_pc, limit,
                        max_json_bytes=MAX_PAGE_JSON_BYTES, return_size=False):
    """Request one bounded page through the existing stopped QMP owner."""
    if type(code) is not bytes or not 1 <= len(code) <= 65536 \
            or not _integer(start_pc, 0, len(code)) or not _integer(limit, 1, 64) \
            or not _integer(max_json_bytes, 1, MAX_PAGE_JSON_BYTES) or type(return_size) is not bool:
        raise ValueError("Invalid native page selectors")
    vm.set("agi-decode-pc", start_pc)
    vm.set("agi-decode-limit", limit)
    raw = vm.get("agi-decode-json")
    if type(raw) is not str:
        raise HarnessError("Native decode page must be bounded JSON text")
    size = len(raw.encode("utf-8"))
    if size > max_json_bytes:
        raise NativePageSizeLimit(size, max_json_bytes)
    try:
        page = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise HarnessError("Invalid native decode JSON") from error
    page = validate_decode_page(page, code=code, source=source, start_pc=start_pc, limit=limit)
    return (page, size) if return_size else page


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
            page = request_decode_page(vm, code, before["source"], start_pc=cursor, limit=count)
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

    def __init__(self, code, pages, *, allow_overlaps=False):
        if type(pages) is not list or not 1 <= len(pages) <= 4096:
            raise HarnessError("Native processor requires bounded explicit pages")
        if type(allow_overlaps) is not bool:
            raise ValueError("allow_overlaps must be Boolean")
        source = pages[0].get("source") if type(pages[0]) is dict else None
        first = validate_decode_page(pages[0], code=code, source=source)
        self.pages = []
        self.source, self.code = deepcopy(source), code
        self.decoder, self.schema = deepcopy(first["decoder"]), first["schema"]
        self.allow_overlaps = allow_overlaps
        identity = sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.info = ProcessorInfo(self.decoder["identity"], self.decoder["version"],
            f"agi.raw:{identity}", "byte", ("decode", "static_successors"), None)
        self._rows, self._faults, self._occupied = {}, {}, set()
        for page in pages:
            self.add_page(page)

    def add_page(self, page):
        """Add immutable CPU facts, preserving the chosen decoder/source identity.

        Overlaps remain rejected by default, including for the observed scene
        consumer. A recursive static consumer may retain overlapping records
        explicitly and qualify only the extents it actually reaches.
        """
        if len(self.pages) >= 4096:
            raise HarnessError("Native processor page budget exceeded")
        page = validate_decode_page(page, code=self.code, source=self.source)
        if page["schema"] != self.schema or not _same(page["decoder"], self.decoder):
            raise HarnessError("Native pages have different decoder contracts")
        new_rows, occupied = {}, set()
        for row in page["instructions"]:
            previous = self._rows.get(row["pc"])
            if row["pc"] in self._faults or previous is not None and not _same(previous, row):
                raise HarnessError("Conflicting native descriptions of the same source PC")
            if previous is not None:
                continue
            extent = set(range(row["pc"], row["pc"] + row["size"]))
            if not self.allow_overlaps and (self._occupied | occupied) & extent:
                raise HarnessError("Native page windows overlap instruction interiors")
            occupied.update(extent)
            new_rows[row["pc"]] = row
        fault = page["error"]
        if fault is not None:
            previous = self._faults.get(fault["pc"])
            if fault["pc"] in self._rows or previous is not None and not _same(previous, fault):
                raise HarnessError("Conflicting native fault at the same source PC")
        self.pages.append(page)
        self._rows.update(new_rows)
        self._occupied.update(occupied)
        if fault is not None:
            self._faults[fault["pc"]] = fault

    def fault_at(self, pc):
        return deepcopy(self._faults.get(pc))

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
