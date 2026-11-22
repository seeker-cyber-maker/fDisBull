"""Canonical native pages across LOGIC resources; no host opcode interpreter."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.processor import Location, decode_instruction
from test_qemu_agi_full_descriptors import (
    ACTION_NAMES, ACTION_WIDTHS, PREDICATE_NAMES, PREDICATE_WIDTHS,
)


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native/qemu-agi"
sys.path.insert(0, str(NATIVE))
from harness import HarnessError
from processor_harness import (
    DECODER, DECODER_V2, NativeAGIProcessor, SCHEMA, SCHEMA_V2,
    read_decode_pages, validate_decode_page,
)
from runtime_harness import QemuAGIRuntime
from runtime_pack import PROFILE, build_package, dump_package


SET_STRING = bytes([114, 2, 1])
KEY = bytes([121, 65, 0, 17])
CODE = SET_STRING + KEY + b"\0"


def source(code=CODE, logic=7, package="a" * 64):
    return {"sha256": sha256(code).hexdigest(), "size": len(code), "logic_id": logic,
            "profile": PROFILE, "package_sha256": package}


def operand(role, kind, value, access):
    return {"role": role, "kind": kind, "width": 8, "access": access, "value": value}


def page_fixture():
    return {
        "schema": SCHEMA_V2, "decoder": deepcopy(DECODER_V2), "source": source(),
        "evidence": "static_decode", "traversal": "linear", "start_pc": 0,
        "limit": 64, "next_pc": len(CODE), "stop": "end", "error": None,
        "instructions": [
            {"pc": 0, "opcode": 114, "size": 3, "bytes": list(SET_STRING),
             "mnemonic": "set.string", "operation": "string.assign",
             "operands": [operand("destination", "string", 2, "write"),
                          operand("message", "message", 1, "reference")],
             "conditions": [], "successors": [{"kind": "fallthrough", "pc": 3, "in_range": True}],
             "effect_class": "host", "execution_support": "native"},
            {"pc": 3, "opcode": 121, "size": 4, "bytes": list(KEY),
             "mnemonic": "set.key", "operation": "input.set_key",
             "operands": [operand("ascii", "u8", 65, "read"),
                          operand("scan_code", "u8", 0, "read"),
                          operand("controller", "controller", 17, "write")],
             "conditions": [], "successors": [{"kind": "fallthrough", "pc": 7, "in_range": True}],
             "effect_class": "host", "execution_support": "native"},
            {"pc": 7, "opcode": 0, "size": 1, "bytes": [0], "mnemonic": "return",
             "operation": "control.return", "operands": [], "conditions": [], "successors": [],
             "effect_class": "control", "execution_support": "native"},
        ],
    }


def test_schema2_string_controller_and_runtime_source_are_accepted():
    page = page_fixture()
    validated = validate_decode_page(page, code=CODE, source=source())
    assert validated == page and validated is not page
    processor = NativeAGIProcessor(CODE, [page])
    for pc in (0, 3, 7):
        row = decode_instruction(processor, CODE, Location(processor.info.address_space, pc))
        assert row.facts == next(item for item in page["instructions"] if item["pc"] == pc)
    assert processor.instructions[0]["operands"][0]["kind"] == "string"
    assert processor.instructions[1]["operands"][2]["kind"] == "controller"


@pytest.mark.parametrize("change", [
    {"logic_id": -1}, {"logic_id": 256}, {"logic_id": True},
    {"package_sha256": None}, {"package_sha256": "A" * 64},
    {"package_sha256": "a" * 63}, {"sha256": "0" * 64},
    {"size": len(CODE) + 1}, {"size": True},
])
def test_runtime_source_rejects_wrong_domains_and_code_identity(change):
    page = page_fixture()
    expected = page["source"] | change
    page["source"] = expected
    with pytest.raises(HarnessError):
        validate_decode_page(page, code=CODE, source=expected)


def test_runtime_requires_package_identity_and_schema2_legacy_requires_logic_zero():
    page = page_fixture()
    del page["source"]["package_sha256"]
    with pytest.raises(HarnessError):
        validate_decode_page(page, code=CODE, source=page["source"])
    page = page_fixture()
    page.update(schema=SCHEMA, decoder=deepcopy(DECODER))
    with pytest.raises(HarnessError):
        validate_decode_page(page, code=CODE, source=page["source"])
    for profile in ("agi-2917-scalar-position-pilot-1",
                    "agi-2917-view-binding-pilot-1", "agi-2917-draw-intent-pilot-1"):
        page = page_fixture()
        page["source"].update(profile=profile)
        del page["source"]["package_sha256"]
        with pytest.raises(HarnessError):
            validate_decode_page(page, code=CODE, source=page["source"])
        page["source"]["logic_id"] = 0
        assert validate_decode_page(page, code=CODE, source=page["source"]) == page
        page.update(schema=SCHEMA, decoder=deepcopy(DECODER))
        with pytest.raises(HarnessError, match="operand kind"):
            validate_decode_page(page, code=CODE, source=page["source"])


def test_same_bytes_have_distinct_processor_spaces_for_logic_and_package():
    processors = []
    for logic, package in ((7, "a" * 64), (8, "a" * 64), (7, "b" * 64)):
        page = page_fixture()
        page["source"] = source(logic=logic, package=package)
        processors.append(NativeAGIProcessor(CODE, [page]))
    assert len({item.info.address_space for item in processors}) == 3
    with pytest.raises(HarnessError):
        processors[0].add_page(processors[1].pages[0])
    with pytest.raises(ValueError):
        processors[0].decode(CODE, Location(processors[1].info.address_space, 0))


def test_runtime_page_reader_selects_logic_and_checks_full_inspection_neutrality():
    class Boundary:
        def __init__(self):
            self.calls, self.changed = [], False
            self.mutate = False

        def state(self):
            return {"source": {"sha256": "a" * 64, "profile": PROFILE},
                    "guest": {"current_logic": 0, "future_field": self.changed}}

        def events(self):
            return {"events": [{"seq": 1, "unchanged": True}]}

        def set(self, name, value):
            self.calls.append((name, value))

        def get(self, name):
            assert name == "agi-decode-json"
            if self.mutate:
                self.changed = True
            return json.dumps(page_fixture())

    vm = Boundary()
    assert read_decode_pages(vm, CODE, source=source(), max_instructions=64) == [page_fixture()]
    assert vm.calls == [("agi-decode-logic", 7), ("agi-decode-pc", 0), ("agi-decode-limit", 64)]
    vm.mutate = True
    with pytest.raises(HarnessError, match="changed native state"):
        read_decode_pages(vm, CODE, source=source(), max_instructions=64)


def test_source_path_runtime_reuses_processor_without_native_directory_on_sys_path():
    script = r'''
import importlib.util
from pathlib import Path
import sys
path = Path(sys.argv[1])
assert str(path.parent) not in sys.path
spec = importlib.util.spec_from_file_location("_runtime_path_test", path)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
processor = runtime._sibling("processor_harness")
assert processor.HarnessError is runtime.HarnessError
assert processor.RUNTIME_PROFILE == runtime.PROFILE
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((
        str(ROOT / "src"), str(ROOT / "packages/fdisbull-core/src"),
    ))
    result = subprocess.run([sys.executable, "-c", script, str(NATIVE / "runtime_harness.py")],
                            cwd=ROOT, env=environment, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("runtime processor acceptance requires explicit FDISBULL_QEMU_AGI")
    path = Path(configured).expanduser().resolve()
    expected = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256")
    before = sha256(path.read_bytes()).hexdigest()
    if expected:
        assert before == expected
    yield path
    assert sha256(path.read_bytes()).hexdigest() == before


def packed_actions():
    raw, starts = bytearray(), []
    for opcode, width in enumerate(ACTION_WIDTHS):
        starts.append(len(raw))
        raw.extend([opcode, *range(1, width + 1)])
    raw.append(174)  # retained native unsupported-opcode boundary
    return bytes(raw), starts


def packed_predicates():
    raw = bytearray()
    for opcode, width in enumerate(PREDICATE_WIDTHS):
        args = [2, 0x34, 0x12, 0xFF, 0] if opcode == 14 else list(range(1, width + 1))
        raw.extend([255, opcode, *args, 255, 0, 0])
    raw.append(0)
    return bytes(raw)


def test_native_runtime_catalog_all_actions_predicates_and_per_logic_identity(binary):
    actions, starts = packed_actions()
    predicates = packed_predicates()
    data = dump_package(build_package(logics=[
        {"id": 0, "code": b"\0", "messages": []},
        {"id": 7, "code": actions, "messages": []},
        {"id": 8, "code": predicates, "messages": []},
        {"id": 255, "code": predicates, "messages": []},
    ]))
    with QemuAGIRuntime(binary, data, timeout=20) as vm:
        before, events = vm.state(), vm.events()
        rows, pages, pc = [], [], 0
        while True:
            page = vm.decode(7, pc, 64)
            pages.append(page)
            rows.extend(page["instructions"])
            pc = page["next_pc"]
            if page["stop"] != "limit":
                break
        assert [row["mnemonic"] for row in rows] == ACTION_NAMES
        assert [row["pc"] for row in rows] == starts
        assert [row["size"] for row in rows] == [width + 1 for width in ACTION_WIDTHS]
        assert all(row["operation"] != "unmodeled" for row in rows)
        assert pages[-1]["error"]["opcode"] == 174
        assert pages[-1]["error"]["name"] == "unsupported_opcode"
        assert pages[0]["source"] == source(actions, 7, sha256(data).hexdigest())
        assert rows[114]["operands"][0] == operand("destination", "string", 1, "write")
        assert rows[121]["operands"][-1] == operand("controller", "controller", 3, "write")
        processor = NativeAGIProcessor(actions, pages)
        assert processor.instructions == rows
        for logic in (8, 255):
            page = vm.decode(logic, 0, 64)
            tokens = [row["conditions"][0] for row in page["instructions"][:-1]]
            assert [token["mnemonic"] for token in tokens] == list(PREDICATE_NAMES)
            assert tokens[12]["operands"][0]["kind"] == "controller"
            assert [item["kind"] for item in tokens[15]["operands"]] == ["string", "string"]
            assert page["source"] == source(predicates, logic, sha256(data).hexdigest())
        assert vm.state() == before and vm.events() == events
        # Public metadata mutation cannot replace the captured package bytes.
        vm.package["logics"][1]["code"] = "00"
        assert vm.logic_code(7) == actions
        assert vm.decode(7, starts[114], 1)["instructions"][0] == rows[114]
        for args in ((True, 0, 1), (256, 0, 1), (9, 0, 1),
                     (7, len(actions) + 1, 1), (7, 0, 0), (7, 0, 65)):
            with pytest.raises(ValueError):
                vm.decode(*args)
        assert vm.decode(7, len(actions), 1)["instructions"] == []
        assert vm.state() == before and vm.events() == events


def test_native_runtime_decode_remains_neutral_during_call_and_pending_output(binary, monkeypatch):
    from fdisbull import agi

    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime consumer must use native instruction facts")

    monkeypatch.setattr(agi.AGI2917Processor, "decode", forbidden)
    parent = bytes([114, 1, 1, 121, 65, 0, 17, 22, 7, 101, 2, 0])
    callee = bytes([114, 2, 1, 255, 12, 17, 255, 2, 0, 12, 80, 0])
    data = build_package(logics=[
        {"id": 0, "code": parent, "messages": ["parent", "%s1 / %s2"]},
        {"id": 7, "code": callee, "messages": ["child"]},
    ])
    with QemuAGIRuntime(binary, data, timeout=20) as vm:
        vm.configure(mask=3, capacity=64)
        vm.run(step_budget=2)
        assert vm.key(65, True)["guest"]["controllers"][17] == 1
        inside = vm.run(step_budget=1)
        assert inside["source"]["logic_id"] == 7
        assert inside["guest"]["stack_depth"] == 1
        events = vm.events()
        caller_page = vm.decode(0, 0, 64)
        callee_page = vm.decode(7, 0, 64)
        call = next(row for row in caller_page["instructions"] if row["mnemonic"] == "call")
        assert call["operands"] == [operand("logic", "logic", 7, "reference")]
        assert call["successors"] == [{"kind": "assumed_return", "pc": 9, "in_range": True}]
        assert vm.state() == inside and vm.events() == events
        pending = vm.run(step_budget=20)
        assert pending["guest"]["status"] == "pending"
        assert pending["guest"]["flags"][80] == 1
        assert pending["guest"]["pending_effect"]["text"] == "parent / child"
        events = vm.events()
        assert vm.decode(7, 0, 64) == callee_page
        assert vm.decode(0, 0, 64) == caller_page
        assert vm.state() == pending and vm.events() == events
        for logic, page, code in ((0, caller_page, parent), (7, callee_page, callee)):
            processor = NativeAGIProcessor(vm.logic_code(logic), [page])
            decoded = decode_instruction(processor, code, Location(processor.info.address_space, 0))
            assert decoded.facts["operation"] == "string.assign"
