"""Independent packed AGI processor descriptions and bounded behavior batches.

One authored source holds the complete 29-command description union and static
malformed cases. Nine owned children cover both description profiles, one
coherent program across all masks, and six isolated execution boundaries.
No compiler, discovery, original resource or per-opcode process loop is used.
"""
from contextlib import contextmanager
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
from draw_intent_harness import QemuAGIDrawIntent
from harness import HarnessError, QemuAGI, guest_state
from processor_harness import NativeAGIProcessor, read_decode_pages, validate_decode_page
from processor_scene import derive_scene_plan
from visual_binding_harness import QemuAGIViewBinding
from fdisbull.processor import Location, decode_instruction

SCHEMA = "fdisbull-agi-native-instructions-2"
DECODER = {"identity": "fdisbull.qemu.agi", "version": "2", "address_unit": "byte",
           "encoding": "agi-2.917", "decode_policy": "structural-1"}
PROFILES = {"scalar": "agi-2917-scalar-position-pilot-1",
            "binding": "agi-2917-view-binding-pilot-1",
            "intent": "agi-2917-draw-intent-pilot-1"}
SCALAR_OPS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 37, 38, 39, 254, 255}
CATALOG = (b"FDBAGIV1" + bytes((5, 0, 1, 0, 10, 1))
           + sha256(b"authored-processor-view-10").digest() + bytes((1, 2, 3)))
LIMITS = {"children": 10, "expected_children": 9, "run_calls": 14,
          "expected_run_calls": 12, "wall_seconds": 120, "qmp_seconds": 5,
          "retirements_per_run": 128}


def variable(role, index, access="read"):
    return {"role": role, "kind": "variable", "width": 8, "access": access, "index": index}


def flag(index, access="read"):
    return {"role": "flag", "kind": "flag", "width": 1, "access": access, "index": index}


def literal(role, kind, value, *, width=8, access="reference"):
    return {"role": role, "kind": kind, "width": width, "access": access, "value": value}


def immediate(role, value):
    return literal(role, "u8", value, access="read")


def displacement(value, *, signed=False):
    return literal("displacement", "s16" if signed else "u16", value,
                   width=16, access="read")


def packed_corpus():
    code, rows, labels, faults = bytearray(), [], {}, {}

    def add(label, raw, mnemonic, operation, effect, operands=(), *, edges=None, conditions=()):
        pc = len(code)
        raw = bytes(raw)
        labels[label] = pc
        code.extend(raw)
        if edges is None:
            edges = [] if mnemonic == "return" else [("fallthrough", 0)]
        rows.append({"pc": pc, "opcode": raw[0], "size": len(raw), "bytes": list(raw),
                     "mnemonic": mnemonic, "operation": operation, "operands": list(operands),
                     "conditions": [{**deepcopy(token), "pc": pc + token["pc"]} for token in conditions],
                     "successors": [{"kind": kind, "pc": pc + len(raw) + delta}
                                    for kind, delta in edges], "effect_class": effect})

    # The only executed prefix: three committed operations, then an unretired draw.
    add("load", (30, 10), "load.view", "resource.load_view", "resource",
        [literal("view", "view", 10)])
    add("animate", (33, 0), "animate.obj", "object.animate", "actor",
        [literal("actor", "actor", 0)])
    add("bind", (41, 0, 10), "set.view", "object.set_view", "actor",
        [literal("actor", "actor", 0), literal("view", "view", 10)])
    add("draw", (35, 0), "draw", "object.draw", "host", [literal("actor", "actor", 0)])
    add("after-draw-return", (0,), "return", "control.return", "control")
    for label, raw, mnemonic, operation, operands in [
        ("increment", (1, 255), "increment", "scalar.increment", [variable("destination", 255, "read_write")]),
        ("decrement", (2, 17), "decrement", "scalar.decrement", [variable("destination", 17, "read_write")]),
        ("assignn", (3, 17, 255), "assignn", "scalar.assign", [variable("destination", 17, "write"), immediate("value", 255)]),
        ("assignv", (4, 17, 18), "assignv", "scalar.assign", [variable("destination", 17, "write"), variable("value", 18)]),
        ("addn", (5, 17, 250), "addn", "scalar.add", [variable("destination", 17, "read_write"), immediate("value", 250)]),
        ("addv", (6, 17, 18), "addv", "scalar.add", [variable("destination", 17, "read_write"), variable("value", 18)]),
        ("subn", (7, 17, 9), "subn", "scalar.subtract", [variable("destination", 17, "read_write"), immediate("value", 9)]),
        ("subv", (8, 17, 18), "subv", "scalar.subtract", [variable("destination", 17, "read_write"), variable("value", 18)]),
    ]:
        add(label, raw, mnemonic, operation, "scalar", operands)
    add("set", (12, 255), "set", "flag.set", "flag", [flag(255, "write")])
    add("reset", (13, 17), "reset", "flag.reset", "flag", [flag(17, "write")])
    add("toggle", (14, 17), "toggle", "flag.toggle", "flag", [flag(17, "read_write")])
    add("load-variable", (31, 27), "load.view.v", "resource.load_view", "resource", [variable("view", 27)])
    add("position", (37, 15, 10, 20), "position", "object.position", "actor",
        [literal("actor", "actor", 15), immediate("x", 10), immediate("y", 20)])
    add("position-variable", (38, 15, 10, 20), "position.v", "object.position", "actor",
        [literal("actor", "actor", 15), variable("x", 10), variable("y", 20)])
    add("get-position", (39, 15, 10, 10), "get.posn", "object.get_position", "actor",
        [literal("actor", "actor", 15), variable("x", 10, "write"), variable("y", 10, "write")])
    add("set-view-variable", (42, 15, 27), "set.view.v", "object.set_view", "actor",
        [literal("actor", "actor", 15), variable("view", 27)])
    for label, raw, mnemonic, operation, domain, operand in [
        ("set-loop", (43, 15, 2), "set.loop", "object.set_loop", "loop", literal("loop", "loop", 2)),
        ("set-loop-variable", (44, 15, 3), "set.loop.v", "object.set_loop", "loop", variable("loop", 3)),
        ("set-cel", (47, 15, 4), "set.cel", "object.set_cel", "cel", literal("cel", "cel", 4)),
        ("set-cel-variable", (48, 15, 5), "set.cel.v", "object.set_cel", "cel", variable("cel", 5)),
    ]:
        add(label, raw, mnemonic, operation, "actor", [literal("actor", "actor", 15), operand])
    add("stop-cycling", (70, 15), "stop.cycling", "object.stop_cycling", "actor",
        [literal("actor", "actor", 15)])
    add("start-cycling", (71, 15), "start.cycling", "object.start_cycling", "actor",
        [literal("actor", "actor", 15)])
    add("signed-goto", (254, 0, 128), "goto", "control.goto", "control",
        [displacement(-32768, signed=True)], edges=[("branch", -32768)])
    conditions = [
        {"kind": "or_begin", "pc": 1},
        {"kind": "predicate", "pc": 2, "opcode": 1, "mnemonic": "equaln",
         "operands": [variable("left", 2), immediate("right", 7)]},
        {"kind": "not", "pc": 5},
        {"kind": "predicate", "pc": 6, "opcode": 7, "mnemonic": "isset", "operands": [flag(4)]},
        {"kind": "or_end", "pc": 8},
        {"kind": "predicate", "pc": 9, "opcode": 2, "mnemonic": "equalv",
         "operands": [variable("left", 5), variable("right", 6)]},
        {"kind": "predicate", "pc": 12, "opcode": 3, "mnemonic": "lessn",
         "operands": [variable("left", 8), immediate("right", 9)]},
        {"kind": "predicate", "pc": 15, "opcode": 4, "mnemonic": "lessv",
         "operands": [variable("left", 10), variable("right", 11)]},
        {"kind": "predicate", "pc": 18, "opcode": 5, "mnemonic": "greatern",
         "operands": [variable("left", 12), immediate("right", 13)]},
        {"kind": "predicate", "pc": 21, "opcode": 6, "mnemonic": "greaterv",
         "operands": [variable("left", 14), variable("right", 15)]},
    ]
    add("ordered-if", (255, 252, 1, 2, 7, 253, 7, 4, 252, 2, 5, 6,
                       3, 8, 9, 4, 10, 11, 5, 12, 13, 6, 14, 15, 255, 0, 128),
        "if", "control.if", "control", [displacement(32768)],
        edges=[("true", 0), ("false", 32768)], conditions=conditions)
    add("empty-if", (255, 255, 0, 0), "if", "control.if", "control", [displacement(0)],
        edges=[("true", 0), ("false", 0)])
    add("eight-predicates", [255, *([7, 0] * 8), 255, 0, 0], "if", "control.if", "control",
        [displacement(0)], edges=[("true", 0), ("false", 0)],
        conditions=[{"kind": "predicate", "pc": 1 + 2 * i, "opcode": 7,
                     "mnemonic": "isset", "operands": [flag(0)]} for i in range(8)])
    for index in range(70):
        add(f"return-pad-{index}", (0,), "return", "control.return", "control")
    for name, raw, number, fault in [
        ("unknown", (174,), 1, "unsupported_opcode"),
        ("empty-or", (255, 252, 252, 255, 0, 0), 5, "unsupported_condition"),
        ("repeated-not", (255, 253, 253, 7, 0, 255, 0, 0), 5, "unsupported_condition"),
        ("unknown-predicate", (255, 19, 0, 255, 0, 0), 5, "unsupported_condition"),
        ("sixty-five-predicates", [255, *([7, 0] * 65), 255, 0, 0], 7, "condition_limit"),
        ("truncated-position", (37, 0, 7), 2, "truncated_instruction"),
    ]:
        labels[name] = len(code)
        faults[name] = {"pc": len(code), "opcode": raw[0], "code": number, "name": fault}
        code.extend(raw)
    for row in rows:
        for edge in row["successors"]:
            edge["in_range"] = 0 <= edge["pc"] < len(code)
    return bytes(code), rows, labels, faults


STATIC_CODE, STATIC_ROWS, STATIC_LABELS, STATIC_FAULTS = packed_corpus()


def expected_rows(profile):
    rows = deepcopy(STATIC_ROWS)
    for row in rows:
        disabled = profile == "scalar" and row["opcode"] not in SCALAR_OPS \
            or profile == "binding" and row["opcode"] in (35, 70, 71)
        row["execution_support"] = "unsupported_profile" if disabled else \
            "pending_host" if row["opcode"] == 35 else "native"
    return rows


def source_identity(code, profile):
    result = {"sha256": sha256(code).hexdigest(), "size": len(code),
              "logic_id": 0, "profile": PROFILES[profile]}
    if profile != "scalar":
        result["catalog_sha256"] = sha256(CATALOG).hexdigest()
    return result


def page_fixture(rows, *, start=0, limit=64, stop="limit", error=None, profile="intent"):
    return {"schema": SCHEMA, "decoder": deepcopy(DECODER),
            "source": source_identity(STATIC_CODE, profile), "evidence": "static_decode",
            "traversal": "linear", "start_pc": start, "limit": limit,
            "next_pc": rows[-1]["pc"] + rows[-1]["size"] if rows else start,
            "stop": stop, "instructions": deepcopy(rows), "error": deepcopy(error)}


def coherent_program():
    parts = [
        ("saturating-high", (3, 0, 255)), ("increment", (1, 0)),
        ("saturating-low", (3, 1, 0)), ("decrement", (2, 1)),
        ("wrap-seed", (3, 2, 250)), ("add-wrap", (5, 2, 10)), ("sub-wrap", (7, 2, 5)),
        ("copy", (4, 3, 2)), ("add-variable", (6, 3, 2)), ("sub-variable", (8, 3, 2)),
        ("set", (12, 1)), ("toggle", (14, 1)), ("reset", (13, 2)),
        ("loop-seed", (3, 4, 0)), ("loop-increment", (1, 4)),
        ("loop-if", (255, 3, 4, 3, 255, 3, 0)),
        ("loop-goto", (254, 244, 255)),
        ("ordered-if", (255, 252, 1, 4, 3, 253, 7, 2, 252,
                        2, 3, 2, 4, 4, 3, 5, 3, 200, 6, 3, 4, 253, 7, 1, 255, 3, 0)),
        ("branch-value", (3, 5, 99)), ("empty-if", (255, 255, 0, 0)),
        ("position-variable", (38, 0, 4, 5)), ("same-position", (37, 0, 3, 99)),
        ("aliased-get-position", (39, 0, 6, 6)), ("return", (0,)),
    ]
    code, sites = bytearray(), {}
    for name, raw in parts:
        sites[name] = {"pc": len(code), "bytes": list(raw)}
        code.extend(raw)
    # Literal path: two true loop tests, then one false; grouped test succeeds.
    labels = [name for name, _ in parts[:14]]
    labels += ["loop-increment", "loop-if", "loop-goto"] * 2
    labels += ["loop-increment", "loop-if"]
    labels += [name for name, _ in parts[17:]]
    pcs = [sites[name]["pc"] for name in labels]
    return bytes(code), sites, pcs


CONTROL_CODE, CONTROL_SITES, CONTROL_PCS = coherent_program()
FAULT_CASES = (
    {"name": "disabled-truncated-view-variable", "code": bytes((31,)), "profile": "scalar",
     "static_error": {"pc": 0, "opcode": 31, "code": 2, "name": "truncated_instruction"},
     "fault": {"pc": 0, "opcode": 31, "code": 1, "name": "unsupported_opcode"}},
    {"name": "disabled-draw-before-actor-validation", "code": bytes((35, 255, 0)), "profile": "binding",
     "static_error": None,
     "fault": {"pc": 0, "opcode": 35, "code": 1, "name": "unsupported_opcode"}},
    {"name": "invalid-if-false-edge-taken", "code": bytes((255, 1, 0, 1, 255, 255, 255, 0)),
     "profile": "scalar", "static_error": None,
     "fault": {"pc": 0, "opcode": 255, "code": 4, "name": "invalid_branch_target"}},
    {"name": "invalid-if-false-edge-not-taken", "code": bytes((255, 1, 0, 0, 255, 255, 255, 0)),
     "profile": "scalar", "static_error": None, "fault": None},
    {"name": "structural-nine-predicates-execution-limit",
     "code": bytes((255, *([7, 0] * 9), 255, 0, 0, 0)), "profile": "scalar",
     "static_error": None,
     "fault": {"pc": 0, "opcode": 255, "code": 7, "name": "condition_limit"}},
    {"name": "structural-predicate-before-truncation-execution-precedence",
     "code": bytes((255, 8)), "profile": "scalar",
     "static_error": {"pc": 0, "opcode": 255, "code": 2, "name": "truncated_instruction"},
     "fault": {"pc": 0, "opcode": 255, "code": 5, "name": "unsupported_condition"}},
)


@pytest.fixture(scope="module")
def native_batch():
    configured = os.environ.get("FDISBULL_QEMU_AGI_PROCESSOR")
    if not configured:
        pytest.skip("processor batch requires an explicit FDISBULL_QEMU_AGI_PROCESSOR")
    binary = Path(configured).expanduser().resolve()
    digest = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256", "")
    assert len(digest) == 64 and sha256(binary.read_bytes()).hexdigest() == digest
    assert os.access(binary, os.X_OK)
    evidence = os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE")
    started, counts = time.monotonic(), {"children": 0, "runs": 0}

    def guard():
        assert time.monotonic() - started < LIMITS["wall_seconds"], "Processor batch wall bound exhausted"

    @contextmanager
    def launch(code, *, profile="scalar"):
        guard()
        assert counts["children"] < LIMITS["children"]
        counts["children"] += 1
        options = {"timeout": LIMITS["qmp_seconds"], "evidence_dir": evidence}
        vm = QemuAGI(binary, code, **options) if profile == "scalar" else \
            (QemuAGIDrawIntent if profile == "intent" else QemuAGIViewBinding)(
                binary, code, CATALOG, **options)
        with vm:
            assert vm.binary_sha256 == digest
            yield vm
        guard()

    def run(vm):
        guard()
        assert counts["runs"] < LIMITS["run_calls"]
        counts["runs"] += 1
        value = vm.run(step_budget=128)
        assert value["run"]["retired"] <= 128
        guard()
        return value

    return launch, run, counts


def one_page(vm, code, *, start, limit):
    pages = read_decode_pages(vm, code, start_pc=start, max_instructions=limit, page_limit=limit)
    assert len(pages) == 1
    return pages[0]


def test_processor_adapter_host_only_static_fact_batch():
    rows = expected_rows("intent")
    pages = [page_fixture(rows[:64]), page_fixture(rows[64:], start=rows[64]["pc"],
             stop="decode_fault", error=STATIC_FAULTS["unknown"])]
    original = deepcopy(pages)
    processor = NativeAGIProcessor(STATIC_CODE, pages)
    assert processor.instructions == rows
    for row in rows:
        decoded = decode_instruction(processor, STATIC_CODE, Location(processor.info.address_space, row["pc"]))
        assert decoded.facts == row
        assert [edge.kind for edge in decoded.successors] == [edge["kind"] for edge in row["successors"]]
        assert [None if edge.target is None else edge.target.offset for edge in decoded.successors] == [
            edge["pc"] if edge["in_range"] else None for edge in row["successors"]]
    processor.instructions[0]["operands"][0]["value"] = 99
    assert processor.instructions == rows and pages == original
    assert processor.decode(STATIC_CODE, Location(processor.info.address_space, STATIC_LABELS["unknown"])) is None
    for kind in ("source", "operand-domain", "edge-range"):
        changed = deepcopy(pages[0])
        if kind == "source":
            changed["source"]["sha256"] = "0" * 64
        elif kind == "operand-domain":
            changed["instructions"][0]["operands"][0]["value"] = True
        else:
            changed["instructions"][0]["successors"][0]["in_range"] = False
        with pytest.raises(HarnessError):
            validate_decode_page(changed, code=STATIC_CODE, source=original[0]["source"])
    shape_cases = []
    oversized = page_fixture([rows[0]], limit=1)
    oversized["instructions"][0].update(size=1025, bytes=list(STATIC_CODE[:1025]))
    oversized["next_pc"] = 1025
    shape_cases.append(oversized)
    excess_operands = page_fixture([rows[0]], limit=1)
    excess_operands["instructions"][0]["operands"] *= 8
    shape_cases.append(excess_operands)
    condition = next(row for row in rows if row["pc"] == STATIC_LABELS["ordered-if"])
    excess_predicate_operands = page_fixture([condition], start=condition["pc"], limit=1)
    excess_predicate_operands["instructions"][0]["conditions"][1]["operands"].extend(
        [immediate("right", 0)] * 255)
    shape_cases.append(excess_predicate_operands)
    eight = next(row for row in rows if row["pc"] == STATIC_LABELS["eight-predicates"])
    overflow_pc = STATIC_LABELS["sixty-five-predicates"]
    overflow_size = 1 + 2 * 65 + 3
    overflow_end = overflow_pc + overflow_size
    overflow = deepcopy(eight)
    overflow.update(pc=overflow_pc, size=overflow_size,
        bytes=list(STATIC_CODE[overflow_pc:overflow_end]), execution_support="unsupported_profile",
        conditions=[{"kind": "predicate", "pc": overflow_pc + 1 + 2 * i,
                     "opcode": 7, "mnemonic": "isset", "operands": [flag(0)]}
                    for i in range(65)],
        successors=[{"kind": kind, "pc": overflow_end, "in_range": overflow_end < len(STATIC_CODE)}
                    for kind in ("true", "false")])
    excess_predicates = page_fixture([overflow], start=overflow_pc, limit=1)
    shape_cases.append(excess_predicates)
    full_page_fault = deepcopy(pages[0])
    full_page_fault["stop"] = "decode_fault"
    full_page_fault["error"] = {"pc": full_page_fault["next_pc"],
        "opcode": STATIC_CODE[full_page_fault["next_pc"]], "code": 1, "name": "unsupported_opcode"}
    shape_cases.append(full_page_fault)
    for changed in shape_cases:
        with pytest.raises(HarnessError):
            validate_decode_page(changed, code=STATIC_CODE, source=original[0]["source"])


def test_packed_native_description_and_pending_scene_batch(native_batch):
    launch, run, _ = native_batch
    for profile in ("intent", "scalar"):
        with launch(STATIC_CODE, profile=profile) as vm:
            initial, initial_events = vm.state(), vm.events()
            assert initial["source"] == source_identity(STATIC_CODE, profile)
            assert vm.get("agi-decode-pc") == 0 and vm.get("agi-decode-limit") == 64
            rows = expected_rows(profile)
            pages = read_decode_pages(vm, STATIC_CODE, max_instructions=256, page_limit=7)
            assert [row for page in pages for row in page["instructions"]] == rows
            assert pages[-1]["stop"] == "decode_fault"
            assert pages[-1]["error"] == STATIC_FAULTS["unknown"]
            assert {row["opcode"] for row in rows} == SCALAR_OPS | {30, 31, 33, 35, 41, 42, 43, 44, 47, 48, 70, 71}
            pad = one_page(vm, STATIC_CODE, start=STATIC_LABELS["return-pad-0"], limit=64)
            assert len(pad["instructions"]) == 64 and pad["stop"] == "limit"
            assert all(row["mnemonic"] == "return" and row["successors"] == [] for row in pad["instructions"])
            for name, error in STATIC_FAULTS.items():
                page = one_page(vm, STATIC_CODE, start=STATIC_LABELS[name], limit=64)
                assert page["stop"] == "decode_fault" and page["instructions"] == []
                assert page["error"] == error and page["next_pc"] == error["pc"]
            end = one_page(vm, STATIC_CODE, start=len(STATIC_CODE), limit=1)
            assert end["stop"] == "end" and end["instructions"] == [] and end["error"] is None
            assert end["next_pc"] == len(STATIC_CODE)
            # A caller-selected operand byte is describable, not a discovered entry.
            interior = one_page(vm, STATIC_CODE, start=3, limit=1)
            assert interior["instructions"][0]["pc"] == 3
            assert interior["instructions"][0]["mnemonic"] == "return"
            with pytest.raises(HarnessError):
                NativeAGIProcessor(STATIC_CODE, [*pages, interior])
            for property_name, invalid in (("agi-decode-pc", -1),
                    ("agi-decode-pc", len(STATIC_CODE) + 1), ("agi-decode-limit", 0),
                    ("agi-decode-limit", 65)):
                previous = vm.get(property_name)
                with pytest.raises(HarnessError):
                    vm.set(property_name, invalid)
                assert vm.get(property_name) == previous
            assert vm.get("agi-decode-json") == vm.get("agi-decode-json")
            assert vm.state() == initial and vm.events() == initial_events
            if profile == "intent":
                vm.configure(mask=3, capacity=64)
                stopped = run(vm)
                events = vm.events()
                assert stopped["guest"]["status"] == "effect"
                assert stopped["guest"]["retired"] == 3 and stopped["guest"]["pc"] == 7
                descriptor = {"kind": "draw", "reason": "draw_requires_host", "pc": 7,
                              "opcode": 35, "bytes": [35, 0], "actor": 0,
                              "retired": False, "committed": False, "completion_available": False}
                assert stopped["guest"]["pending_effect"] == descriptor
                pending_page = one_page(vm, STATIC_CODE, start=7, limit=3)
                assert pending_page["instructions"] == rows[3:6]
                assert [item["pc"] for item in events["events"] if item["kind"] == "retire"] == [0, 2, 4]
                assert vm.state() == stopped and vm.events() == events
                plan = derive_scene_plan(code=STATIC_CODE, pages=pages, catalog=CATALOG,
                    initial=initial, state=stopped, events=events,
                    source_mappings=[{"kind": "authored", "fragment_span": [0, len(STATIC_CODE)], "source": None}],
                    legacy={"selected_actors": [15], "views": [99],
                            "execution_endpoint": {"kind": "authored_return", "fragment_pc": 9}})
                assert plan["actor_ids"] == plan["touched_actor_ids"] == [0]
                assert plan["static_actor_references"] == [0, 15]
                assert plan["observed_view_ids"] == plan["current_view_ids"] == [10]
                assert plan["pending_actor_id"] == 0 and plan["endpoint"]["kind"] == "pending_draw"
                assert plan["endpoint"]["retired"] is plan["endpoint"]["committed"] is False
                assert plan["endpoint"]["descriptor"] == descriptor
                variable_view = next(item for item in plan["operand_references"]
                                     if item["pc"] == STATIC_LABELS["load-variable"])
                assert variable_view["operand"] == variable("view", 27)
                assert "static_value" not in variable_view and variable_view["observations"] == []
                assert {item["field"] for item in plan["legacy_contradictions"]} == {
                    "selected_actors", "views", "execution_endpoint"}
                assert plan["static_listing_complete"] is False and plan["static_reachability_qualified"] is False
                assert vm.state() == stopped and vm.events() == events
                altered_events = deepcopy(events)
                next(item for item in altered_events["events"]
                     if item["kind"] == "retire" and item["pc"] == 0)["resolved_value"] = 11
                with pytest.raises(HarnessError):
                    derive_scene_plan(code=STATIC_CODE, pages=pages, catalog=CATALOG,
                        initial=initial, state=stopped, events=altered_events,
                        source_mappings=[{"kind": "authored", "fragment_span": [0, len(STATIC_CODE)], "source": None}])


def test_refactored_scalar_condition_control_program_all_masks(native_batch):
    launch, run, _ = native_batch
    variables = [0] * 256
    variables[:7] = [255, 0, 255, 255, 3, 99, 99]
    actors = [{"id": i, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0} for i in range(16)]
    actors[0].update(x=3, y=99, prev_x=3, prev_y=99)
    baseline = None
    with launch(CONTROL_CODE) as vm:
        for mask, capacity in ((0, 128), (1, 128), (2, 128), (3, 128), (3, 1)):
            vm.restart()
            vm.configure(mask=mask, capacity=capacity)
            state = run(vm)
            events = vm.events()["events"]
            guest = guest_state(state)
            assert guest["status"] == "return" and guest["fault"] is None
            assert guest["variables"] == variables and guest["flags"] == [0] * 256
            assert guest["actors"] == actors
            assert guest["retired"] == len(CONTROL_PCS) and guest["pc"] == len(CONTROL_CODE)
            baseline = guest if baseline is None else baseline
            assert guest == baseline
            retire = [item for item in events if item["kind"] == "retire"]
            scene = [item for item in events if item["kind"] == "position"]
            assert [item["pc"] for item in retire] == (CONTROL_PCS[:1] if capacity == 1 else
                                                       CONTROL_PCS if mask & 1 else [])
            assert [item["pc"] for item in scene] == ([CONTROL_SITES["position-variable"]["pc"]]
                                                       if mask & 2 and capacity > 1 else [])
            for index, item in enumerate(retire):
                expected_next = CONTROL_PCS[index + 1] if index + 1 < len(CONTROL_PCS) else len(CONTROL_CODE)
                assert item["next_pc"] == expected_next and item["retired"] == index + 1
                assert item["bytes"] == next(site["bytes"] for site in CONTROL_SITES.values()
                                               if site["pc"] == item["pc"])
            if scene:
                assert scene[0]["actor"] == 0
                assert scene[0]["before"] == {"x": 0, "y": 0, "prev_x": 0, "prev_y": 0}
                assert scene[0]["after"] == {"x": 3, "y": 99, "prev_x": 3, "prev_y": 99}
            observation = state["observation"]
            assert observation["per_channel"]["disasm"]["eligible"] == (len(CONTROL_PCS) if mask & 1 else 0)
            assert observation["per_channel"]["scene"]["eligible"] == (1 if mask & 2 else 0)
            assert observation["dropped"] == (len(CONTROL_PCS) if capacity == 1 else 0)
            assert observation["helper_calls"] == (len(CONTROL_PCS) if mask & 1 else 2 if mask & 2 else 0)
            saved_events = vm.events()
            one_page(vm, CONTROL_CODE, start=CONTROL_SITES["loop-if"]["pc"], limit=2)
            assert vm.state() == state and vm.events() == saved_events


def test_isolated_branch_and_disabled_profile_precedence_batch(native_batch, record_property):
    launch, run, counts = native_batch
    for case in FAULT_CASES:
        with launch(case["code"], profile=case["profile"]) as vm:
            page = one_page(vm, case["code"], start=0, limit=2)
            assert page["error"] == case["static_error"], case["name"]
            if case["code"][0] == 35:
                assert page["instructions"][0]["execution_support"] == "unsupported_profile"
                assert page["instructions"][0]["operands"] == [literal("actor", "actor", 255)]
            if case["name"].startswith("invalid-if-false-edge"):
                row = page["instructions"][0]
                assert row["operands"] == [displacement(65535)]
                assert row["successors"] == [{"kind": "true", "pc": 7, "in_range": True},
                                               {"kind": "false", "pc": 65542, "in_range": False}]
            if case["name"] == "structural-nine-predicates-execution-limit":
                row = page["instructions"][0]
                assert row["execution_support"] == "unsupported_profile"
                assert len([token for token in row["conditions"] if token["kind"] == "predicate"]) == 9
            vm.configure(mask=3, capacity=16)
            state = run(vm)
            assert state["guest"]["fault"] == case["fault"], case["name"]
            events = vm.events()["events"]
            if case["fault"] is not None:
                assert state["guest"]["status"] == "fault" and state["guest"]["pc"] == 0
                assert state["guest"]["retired"] == 0 and events == []
                assert state["guest"]["variables"] == state["guest"]["flags"] == [0] * 256
            else:
                assert state["guest"]["status"] == "return" and state["guest"]["pc"] == 8
                assert state["guest"]["retired"] == 2
                assert [item["pc"] for item in events] == [0, 7]
                assert [item["next_pc"] for item in events] == [7, 8]
    assert counts == {"children": LIMITS["expected_children"], "runs": LIMITS["expected_run_calls"]}
    record_property("processor_native_children", counts["children"])
    record_property("processor_run_calls", counts["runs"])
