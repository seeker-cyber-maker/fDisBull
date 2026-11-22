"""One authored stopped-child corpus and one detached scene-graph contract batch.

The corpus is independent of commercial resources. Branches, cycles, terminal
room changes, typed resource references and malformed tails share one source;
native metadata is requested without ever resuming the guest. Pure consumer
checks use explicitly authored records rather than another AGI decoder.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native" / "qemu-agi"))
from harness import HarnessError, QemuAGI
from processor_discovery import derive_scene_candidates, logic_input, read_reachable_decode_pages
from processor_harness import read_decode_pages

SCHEMA = "fdisbull-agi-native-instructions-2"
DECODER = {"identity": "fdisbull.qemu.agi", "version": "2", "address_unit": "byte",
           "encoding": "agi-2.917", "decode_policy": "structural-1"}
LIMITS = {"children": 1, "guest_runs": 0, "instructions": 512,
          "page_limit": 64, "qmp_seconds": 5, "wall_seconds": 30}


def _literal(role, kind, value, *, width=8, access="reference"):
    return {"role": role, "kind": kind, "value": value, "width": width, "access": access}


def _variable(role, index, *, access="read"):
    return {"role": role, "kind": "variable", "index": index, "width": 8, "access": access}


def _flag(index):
    return {"role": "flag", "kind": "flag", "index": index, "width": 1, "access": "read"}


def _immediate(role, value):
    return _literal(role, "u8", value, access="read")


def _displacement(value, *, signed=False):
    return _literal("displacement", "s16" if signed else "u16", value,
                    width=16, access="read")


def _authored_corpus():
    code, rows, labels, fixups, faults = bytearray(), [], {}, [], {}

    def add(label, raw, mnemonic, operation, operands=(), *, effect="resource",
            support="unsupported_profile", edges=None, conditions=()):
        pc = len(code)
        labels[label] = pc
        code.extend(raw)
        row = {"pc": pc, "opcode": raw[0], "size": len(raw), "bytes": list(raw),
               "mnemonic": mnemonic, "operation": operation, "operands": list(operands),
               "conditions": [{**deepcopy(token), "pc": pc + token["pc"]}
                              for token in conditions],
               "successors": [{"kind": "fallthrough", "pc": pc + len(raw)}]
                             if edges is None else edges,
               "effect_class": effect, "execution_support": support}
        rows.append(row)
        return row

    def condition(label, raw, tokens, false_target, *, native=False):
        row = add(label, [255, *raw, 255, 0, 0], "if", "control.if",
                  [_displacement(0)], effect="control",
                  support="native" if native else "unsupported_profile", conditions=tokens,
                  edges=[])
        fixups.append((row, "if", false_target, 0))

    def jump(label, target, adjustment=0):
        row = add(label, [254, 0, 0], "goto", "control.goto",
                  [_displacement(0, signed=True)], effect="control", support="native", edges=[])
        fixups.append((row, "goto", target, adjustment))

    def predicate(opcode, mnemonic, operands):
        return [{"kind": "predicate", "pc": 1, "opcode": opcode,
                 "mnemonic": mnemonic, "operands": operands}]

    # An actual diamond, with two explicit background-variable assignments.
    condition("entry", [7, 1], predicate(7, "isset", [_flag(1)]), "picture_else", native=True)
    add("picture_then", [3, 0, 5], "assignn", "scalar.assign",
        [_variable("destination", 0, access="write"), _immediate("value", 5)],
        effect="scalar", support="native")
    add("load_picture_then", [24, 0], "load.pic", "resource.load_picture", [_variable("picture", 0)])
    add("draw_picture_then", [25, 0], "draw.pic", "scene.draw_picture", [_variable("picture", 0)], effect="host")
    jump("picture_join_jump", "picture_join")
    add("picture_else", [3, 0, 53], "assignn", "scalar.assign",
        [_variable("destination", 0, access="write"), _immediate("value", 53)],
        effect="scalar", support="native")
    add("load_picture_else", [24, 0], "load.pic", "resource.load_picture", [_variable("picture", 0)])
    add("draw_picture_else", [25, 0], "draw.pic", "scene.draw_picture", [_variable("picture", 0)], effect="host")
    add("picture_join", [26], "show.pic", "scene.show_picture", effect="host")
    add("view", [30, 10], "load.view", "resource.load_view", [_literal("view", "view", 10)])
    add("animate", [33, 0], "animate.obj", "object.animate", [_literal("actor", "actor", 0)], effect="actor")
    add("bind", [41, 0, 10], "set.view", "object.set_view",
        [_literal("actor", "actor", 0), _literal("view", "view", 10)], effect="actor")
    condition("pose_condition", [9, 19],
              predicate(9, "has", [_literal("inventory_object", "inventory_object", 19)]), "cel_else")
    add("cel_then", [47, 0, 1], "set.cel", "object.set_cel",
        [_literal("actor", "actor", 0), _literal("cel", "cel", 1)], effect="actor")
    jump("cel_join_jump", "position")
    add("cel_else", [47, 0, 0], "set.cel", "object.set_cel",
        [_literal("actor", "actor", 0), _literal("cel", "cel", 0)], effect="actor")
    add("position", [37, 0, 30, 90], "position", "object.position",
        [_literal("actor", "actor", 0), _immediate("x", 30), _immediate("y", 90)],
        effect="actor", support="native")
    add("draw", [35, 0], "draw", "object.draw", [_literal("actor", "actor", 0)], effect="host")
    for label, opcode, mnemonic, operand in [
        ("call_literal", 22, "call", _literal("logic", "logic", 7)),
        ("call_variable", 23, "call.v", _variable("logic", 9)),
    ]:
        value = operand.get("value", operand.get("index"))
        pc = len(code)
        add(label, [opcode, value], mnemonic, "control.call", [operand], effect="control",
            edges=[{"kind": "assumed_return", "pc": pc + 2}])
    condition("loop", [7, 2], predicate(7, "isset", [_flag(2)]), "room_variable", native=True)
    jump("loop_back", "loop")
    add("room_variable", [19, 8], "new.room.v", "control.new_room", [_variable("room", 8)],
        effect="control", edges=[])
    add("dead_view", [30, 99], "load.view", "resource.load_view", [_literal("view", "view", 99)])
    add("dead_return", [0], "return", "control.return", effect="control", support="native", edges=[])

    # Disconnected islands are queried in the same stopped child.
    add("room_literal", [18, 42], "new.room", "control.new_room", [_literal("room", "room", 42)],
        effect="control", edges=[])
    add("room_dead_view", [30, 98], "load.view", "resource.load_view", [_literal("view", "view", 98)])
    add("room_dead_return", [0], "return", "control.return", effect="control", support="native", edges=[])
    add("multiply", [165, 50, 4], "mul.n", "scalar.multiply",
        [_variable("destination", 50, access="read_write"), _immediate("value", 4)],
        effect="scalar")
    add("multiply_return", [0], "return", "control.return", effect="control", support="native", edges=[])
    jump("interior_jump", "interior_position", adjustment=1)
    add("interior_position", [37, 0, 1, 2], "position", "object.position",
        [_literal("actor", "actor", 0), _immediate("x", 1), _immediate("y", 2)],
        effect="actor", support="native")
    add("interior_return", [0], "return", "control.return", effect="control", support="native", edges=[])
    pc = len(code)
    add("outside_jump", [254, 0, 128], "goto", "control.goto",
        [_displacement(-32768, signed=True)], effect="control", support="native",
        edges=[{"kind": "branch", "pc": pc + 3 - 32768}])

    # Twelve stateful predicates, six 16-bit word references each, exceed both
    # old execution limits while remaining bounded structural descriptors.
    raw, tokens = [252], [{"kind": "or_begin", "pc": 1}]
    for number in range(12):
        words = (257 + number, 2, 65535, 9999, 0, 511)
        tokens.append({"kind": "predicate", "pc": 1 + len(raw), "opcode": 14,
                       "mnemonic": "said", "operands": [
                           _immediate("word_count", 6),
                           *[_literal("word", "word", word, width=16) for word in words]]})
        raw.extend((14, len(words)))
        for word in words:
            raw.extend(word.to_bytes(2, "little"))
    tokens.append({"kind": "or_end", "pc": 1 + len(raw)})
    raw.append(252)
    condition("large_condition", raw, tokens, "large_return")
    add("large_return", [0], "return", "control.return", effect="control", support="native", edges=[])
    # A zero word count has a complete structural frame. Its evaluation is not
    # admitted by the pilot and is not inferred from the count.
    condition("zero_said", [0, 14, 0], [
        {"kind": "predicate", "pc": 1, "opcode": 0, "mnemonic": "false", "operands": []},
        {"kind": "predicate", "pc": 2, "opcode": 14, "mnemonic": "said",
         "operands": [_immediate("word_count", 0)]}], "zero_said_return")
    add("zero_said_return", [0], "return", "control.return", effect="control", support="native", edges=[])

    # Every malformed window has a named query offset; no child per fault.
    for label, raw, number, name in [
        ("unknown_action", [174], 1, "unsupported_opcode"),
        ("unknown_predicate", [255, 19, 255, 0, 0], 5, "unsupported_condition"),
        ("empty_or", [255, 252, 252, 255, 0, 0], 5, "unsupported_condition"),
        ("repeated_not", [255, 253, 253, 7, 0, 255, 0, 0], 5, "unsupported_condition"),
        ("contextual_trace", [149], 14, "contextual_layout"),
        ("predicate_limit", [255, *([7, 0] * 65), 255, 0, 0], 7, "condition_limit"),
        ("truncated_said", [255, 14, 3, 1, 0], 2, "truncated_instruction"),
    ]:
        labels[label] = len(code)
        faults[label] = {"pc": len(code), "opcode": raw[0], "code": number, "name": name}
        code.extend(raw)
    for row, kind, target, adjustment in fixups:
        end = row["pc"] + row["size"]
        destination = labels[target] + adjustment
        delta = destination - end
        code[end - 2:end] = delta.to_bytes(2, "little", signed=kind == "goto")
        row["bytes"] = list(code[row["pc"]:end])
        row["operands"] = [_displacement(delta, signed=kind == "goto")]
        row["successors"] = ([{"kind": "true", "pc": end}, {"kind": "false", "pc": destination}]
                             if kind == "if" else [{"kind": "branch", "pc": destination}])
    for row in rows:
        for edge in row["successors"]:
            edge["in_range"] = 0 <= edge["pc"] < len(code)
    return bytes(code), rows, labels, faults


CODE, ROWS, LABELS, FAULTS = _authored_corpus()
SOURCE = {"sha256": sha256(CODE).hexdigest(), "size": len(CODE), "logic_id": 0,
          "profile": "agi-2917-scalar-position-pilot-1"}
RESOURCE_HASH = sha256(len(CODE).to_bytes(2, "little") + CODE).hexdigest()
MAPPINGS = [{"kind": "original", "fragment_span": [0, len(CODE)], "source": {
    "logic": 23, "resource_sha256": RESOURCE_HASH, "code_span": [0, len(CODE)],
    "payload_span": [2, len(CODE) + 2]}}]


def _page(rows, *, stop="limit", error=None, limit=None):
    start = rows[0]["pc"] if rows else error["pc"]
    return {"schema": SCHEMA, "decoder": deepcopy(DECODER), "source": deepcopy(SOURCE),
            "evidence": "static_decode", "traversal": "linear", "start_pc": start,
            "limit": limit or len(rows) or 1,
            "next_pc": rows[-1]["pc"] + rows[-1]["size"] if rows else start,
            "stop": stop, "instructions": deepcopy(rows), "error": deepcopy(error)}


def _pages():
    chunks = [ROWS[index:index + 32] for index in range(0, len(ROWS), 32)]
    return [_page(chunk, stop="decode_fault" if index == len(chunks) - 1 else "limit",
                  error=FAULTS["unknown_action"] if index == len(chunks) - 1 else None,
                  limit=64 if index == len(chunks) - 1 else len(chunk))
            for index, chunk in enumerate(chunks)]


def _derive(pages=None, **options):
    return derive_scene_candidates(code=CODE, pages=_pages() if pages is None else pages,
                                   source_mappings=deepcopy(MAPPINGS), **options)


def _assert_main_graph(plan):
    reached = {node["pc"] for node in plan["nodes"]}
    expected = {row["pc"] for row in ROWS if row["pc"] < LABELS["dead_view"]}
    assert reached == expected and len(plan["nodes"]) == len(expected)
    assert plan["source"] == SOURCE and plan["decoder"] == DECODER
    assert plan["coverage"]["traversal_exhausted"] is True
    assert plan["coverage"]["local_decode_complete"] is True
    assert plan["coverage"]["branch_feasibility"] == "not_evaluated"
    assert plan["coverage"]["interprocedural_effects"] == "unknown"
    assert plan["coverage"]["scene_discovery_complete"] is False
    expected_edges = {(row["pc"], edge["pc"], edge["kind"])
                      for row in ROWS if row["pc"] in expected for edge in row["successors"]}
    assert {(edge["from_pc"], edge["to_pc"], edge["kind"]) for edge in plan["edges"]} == expected_edges
    assert len(plan["edges"]) == len(expected_edges)
    call_edges = [edge for edge in plan["edges"] if edge["from_pc"] in
                  (LABELS["call_literal"], LABELS["call_variable"])]
    assert len(call_edges) == 2 and all(edge["qualification"] == "callee_return_assumed"
                                       for edge in call_edges)
    for node in plan["nodes"]:
        assert node["source_mapping"] == {"kind": "original", "original_source_address": {
            "logic": 23, "resource_sha256": RESOURCE_HASH, "code_pc": node["pc"],
            "payload_offset": node["pc"] + 2}}
    pictures = [ref for ref in plan["references"] if ref["domain"] == "picture"]
    assert {ref["pc"] for ref in pictures} == {LABELS[key] for key in (
        "load_picture_then", "draw_picture_then", "load_picture_else", "draw_picture_else")}
    assert all(ref["resolution"] == "unresolved" and ref["value"] is None
               and ref["operand"] == _variable("picture", 0) for ref in pictures)
    # Local assignn writers are not a license to invent a reaching-value proof.
    assert all(ref["reason"] == "variable_input" for ref in pictures)
    views = [ref for ref in plan["references"] if ref["domain"] == "view"]
    assert {ref["value"] for ref in views} == {10}
    assert all(ref["resolution"] == "literal" for ref in views)
    calls = [ref for ref in plan["references"] if ref["domain"] == "logic"]
    assert {(ref["pc"], ref["resolution"], ref["value"]) for ref in calls} == {
        (LABELS["call_literal"], "literal", 7), (LABELS["call_variable"], "unresolved", None)}
    rooms = [ref for ref in plan["references"] if ref["domain"] == "room"]
    assert len(rooms) == 1 and rooms[0]["operand"] == _variable("room", 8)
    assert all(item["outcome"] == "unknown" for item in plan["conditions"])
    assert {item["pc"] for item in plan["conditions"]} == {
        LABELS["entry"], LABELS["pose_condition"], LABELS["loop"]}


def test_scene_discovery_host_contract_batch():
    pages = _pages()
    original = deepcopy(pages)
    plan = _derive(pages)
    _assert_main_graph(plan)
    assert pages == original
    prepared = logic_input(len(CODE).to_bytes(2, "little") + CODE, 23)
    assert prepared["code"] == CODE and prepared["source_mappings"] == MAPPINGS
    mapped = _derive(resource_mapping=prepared["resource_mapping"])
    assert mapped["resource_mapping"]["resource_sha256"] == RESOURCE_HASH
    duplicate = _derive(pages + [deepcopy(pages[0])])
    assert duplicate["nodes"] == plan["nodes"] and duplicate["edges"] == plan["edges"]
    roots = (0, LABELS["room_literal"], LABELS["large_condition"], LABELS["zero_said"])
    extra = _derive(roots=roots)
    assert {ref["value"] for ref in extra["references"] if ref["domain"] == "room"} == {None, 42}
    assert LABELS["room_dead_view"] not in {node["pc"] for node in extra["nodes"]}
    large = next(item for item in extra["conditions"] if item["pc"] == LABELS["large_condition"])
    assert len([token for token in large["ordered_tokens"] if token["kind"] == "predicate"]) == 12
    assert large["ordered_tokens"] == next(row["conditions"] for row in ROWS
                                           if row["pc"] == LABELS["large_condition"])
    zero = next(item for item in extra["conditions"] if item["pc"] == LABELS["zero_said"])
    assert zero["ordered_tokens"][0]["mnemonic"] == "false"
    assert zero["ordered_tokens"][0]["operands"] == []
    assert zero["ordered_tokens"][1]["operands"] == [_immediate("word_count", 0)]
    assert zero["outcome"] == "unknown"
    multiply = _derive(roots=(LABELS["multiply"],))
    assert multiply["unknown_state_effect_sites"] == []
    # Archived structural-1 pages may still describe this as catalog-only.
    # Retain their conservative fallback coverage without expecting new native
    # pages to throw away the now-known variable write and immediate input.
    archived_pages = deepcopy(pages)
    for page in archived_pages:
        for row in page["instructions"]:
            if row["pc"] == LABELS["multiply"]:
                row.update(operation="unmodeled", effect_class="unknown",
                           operands=[_immediate("arg0", 50), _immediate("arg1", 4)],
                           successors=[{"kind": "assumed_fallthrough", "pc": row["pc"] + 3,
                                        "in_range": True}])
    unmodeled = _derive(archived_pages, roots=(LABELS["multiply"],))
    assert unmodeled["unknown_state_effect_sites"] == [LABELS["multiply"]]
    assert unmodeled["edges"][0]["qualification"] == "unmodeled_effect_fallthrough_assumed"
    for options, kind in [({"max_reached_nodes": 1}, "instruction_budget"),
                          ({"max_edges": 1}, "edge_budget")]:
        limited = _derive(**options)
        assert limited["coverage"]["traversal_exhausted"] is False
        assert kind in {item["kind"] for item in limited["frontier"]}
    missing = _derive([_page([ROWS[0]])])
    assert missing["coverage"]["local_decode_complete"] is False
    assert "missing_native_record" in {item["kind"] for item in missing["frontier"]}
    outside = _derive(roots=(LABELS["outside_jump"],))
    assert "out_of_range_edge" in {item["kind"] for item in outside["frontier"]}
    interior_row = deepcopy(next(row for row in ROWS if row["pc"] == LABELS["dead_return"]))
    interior_row["pc"] = LABELS["interior_position"] + 1
    interior = _derive([*pages, _page([interior_row])],
                       roots=(LABELS["interior_jump"], LABELS["interior_position"]))
    assert "overlapping_instruction_extent" in {item["kind"] for item in interior["frontier"]}
    fault = _derive(roots=(LABELS["unknown_action"],))
    assert "decode_fault" in {item["kind"] for item in fault["frontier"]}
    reference_limited = _derive(max_references=1)
    assert len(reference_limited["references"]) == 1
    assert reference_limited["coverage"]["reference_inventory_complete"] is False
    assert "reference_budget" in {item["kind"] for item in reference_limited["frontier"]}
    for kind in ("source", "descriptor", "mapping"):
        changed = deepcopy(pages)
        if kind == "source":
            changed[0]["source"]["sha256"] = "0" * 64
        elif kind == "descriptor":
            changed.append(deepcopy(pages[0]))
            changed[-1]["instructions"][0]["mnemonic"] = "contradictory"
        else:
            with pytest.raises(HarnessError):
                derive_scene_candidates(code=CODE, pages=changed,
                    source_mappings=[{"kind": "authored", "fragment_span": [1, len(CODE)], "source": None}])
            continue
        with pytest.raises(HarnessError):
            _derive(changed)
    for options in ({"roots": (True,)}, {"max_reached_nodes": 0}, {"max_edges": 0}):
        with pytest.raises((ValueError, HarnessError)):
            _derive(**options)

    class ReplayOwner:
        """A canned page at the QMP boundary; no bytecode interpretation."""
        timeout = 5.0

        def __init__(self):
            self.selectors = {}
            self.requests = 0
            self.raw = json.dumps(_page(ROWS, stop="decode_fault", error=FAULTS["unknown_action"], limit=64))

        def state(self):
            return {"source": deepcopy(SOURCE), "guest": {"pc": 0, "retired": 0, "status": "ready"}}

        def events(self):
            return {"events": []}

        def set(self, name, value):
            assert name in ("agi-decode-pc", "agi-decode-limit")
            self.selectors[name] = value

        def get(self, name):
            assert name == "agi-decode-json"
            assert self.selectors == {"agi-decode-pc": 0, "agi-decode-limit": 64}
            self.requests += 1
            return self.raw

    owner = ReplayOwner()
    limited = read_reachable_decode_pages(owner, CODE, max_native_json_bytes=1)
    assert limited["pages"] == [] and limited["pending_pcs"] == [0]
    assert limited["coverage"] == {"traversal_exhausted": False, "local_decode_complete": False}
    assert limited["frontier"] == [{"kind": "native_json_budget", "pc": 0,
        "received_page_bytes": len(owner.raw.encode("utf-8")), "admission_limit": 1}]
    assert limited["usage"]["native_rows"] == limited["usage"]["pages"] == 0
    assert limited["usage"]["admitted_json_bytes"] == 0
    assert limited["usage"]["received_json_bytes"] == len(owner.raw.encode("utf-8"))
    assert owner.requests == limited["usage"]["page_requests"] == 1
    assert limited["native_inputs_unchanged"] is True and limited["runs"] == 0
    assert owner.timeout == 5.0


def test_scene_discovery_packed_native_metadata_batch(record_property):
    configured = os.environ.get("FDISBULL_QEMU_AGI_PROCESSOR")
    if not configured:
        pytest.skip("discovery metadata batch requires an explicit FDISBULL_QEMU_AGI_PROCESSOR")
    binary = Path(configured).expanduser().resolve()
    digest = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256", "")
    assert len(digest) == 64 and sha256(binary.read_bytes()).hexdigest() == digest
    started = time.monotonic()
    with QemuAGI(binary, CODE, timeout=LIMITS["qmp_seconds"],
                 evidence_dir=os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE")) as vm:
        initial, events = vm.state(), vm.events()
        assert initial["source"] == SOURCE and initial["guest"]["retired"] == 0
        acquisition = read_reachable_decode_pages(vm, CODE, max_native_rows=LIMITS["instructions"],
            max_reached_nodes=128, max_pages=16, max_edges=256, page_limit=LIMITS["page_limit"],
            deadline_seconds=LIMITS["wall_seconds"])
        pages = acquisition["pages"]
        assert acquisition["native_inputs_unchanged"] is True and acquisition["runs"] == 0
        assert acquisition["before"] == acquisition["after"] == initial
        assert acquisition["events_before"] == acquisition["events_after"] == events
        assert acquisition["coverage"] == {"traversal_exhausted": True, "local_decode_complete": True}
        assert acquisition["frontier"] == [] and acquisition["pending_pcs"] == []
        assert acquisition["usage"]["pages"] == acquisition["usage"]["page_requests"] == 1
        assert pages[-1]["stop"] == "decode_fault" and pages[-1]["error"] == FAULTS["unknown_action"]
        rows = [row for page in pages for row in page["instructions"]]
        assert len(rows) == len(ROWS)
        for actual, expected in zip(rows, ROWS):
            assert actual == expected, expected["pc"]
        by_pc = {row["pc"]: row for row in rows}
        for label, role, kind, value in [("load_picture_then", "picture", "variable", 0),
                                        ("call_literal", "logic", "logic", 7),
                                        ("call_variable", "logic", "variable", 9),
                                        ("room_literal", "room", "room", 42),
                                        ("room_variable", "room", "variable", 8)]:
            row = by_pc[LABELS[label]]
            assert row["execution_support"] == "unsupported_profile"
            assert row["operands"] == [_variable(role, value) if kind == "variable"
                                        else _literal(role, kind, value)]
        large = by_pc[LABELS["large_condition"]]
        assert large["size"] > 64 and large["execution_support"] == "unsupported_profile"
        assert large["conditions"] == next(row["conditions"] for row in ROWS if row["pc"] == large["pc"])
        zero = by_pc[LABELS["zero_said"]]
        assert zero["conditions"][0]["mnemonic"] == "false" and zero["conditions"][0]["operands"] == []
        assert zero["conditions"][1]["operands"] == [_immediate("word_count", 0)]
        assert zero["execution_support"] == "unsupported_profile"
        assert by_pc[LABELS["multiply"]]["effect_class"] == "scalar"
        assert by_pc[LABELS["multiply"]]["execution_support"] == "unsupported_profile"
        _assert_main_graph(_derive(pages))
        for label, expected in FAULTS.items():
            assert time.monotonic() - started < LIMITS["wall_seconds"]
            result = read_decode_pages(vm, CODE, start_pc=LABELS[label], max_instructions=1, page_limit=1)
            assert len(result) == 1 and result[0]["instructions"] == []
            assert result[0]["stop"] == "decode_fault" and result[0]["error"] == expected
        assert vm.state() == initial and vm.events() == events
        assert initial["guest"]["pc"] == 0 and initial["guest"]["status"] == "ready"
    assert time.monotonic() - started < LIMITS["wall_seconds"]
    record_property("discovery_native_children", LIMITS["children"])
    record_property("discovery_guest_runs", LIMITS["guest_runs"])
