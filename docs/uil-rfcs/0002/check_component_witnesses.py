#!/usr/bin/env python3
"""Authored contract witnesses; NOT a production UIL validator or UDC.

Run with Python 3.10+ using only its standard library. These tests demonstrate
why selected candidate transformations need guards. They do not exercise
fDisBull, a native ABI, a decompiler, an original game, or a solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import unittest


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compare_u8(left, right, domain=range(256)):
    """Finite exhaustive comparison for the caller-supplied scalar domain only."""
    for value in domain:
        a, b = left(value), right(value)
        if a != b:
            return {"input": value, "left": a, "right": b}
    return None


def closure(bias: int):
    return lambda value: (value + bias) & 255


def trampoline_sum(n: int) -> int:
    """Authored explicit-frame model, not a native stack-elimination transform."""
    frames = []
    while n:
        frames.append(n)
        n -= 1
    result = 0
    while frames:
        result += frames.pop()
    return result


def incorrectly_globalized_sum(n: int) -> int:
    local_slot = [None]
    def run(value: int) -> int:
        if value == 0:
            return 0
        local_slot[0] = value
        partial = run(value - 1)
        return partial + local_slot[0]
    return run(n)


def compile_constant(program: dict) -> bytes:
    """Tiny authored many-to-one emitter used only to exhibit inverse ambiguity."""
    op = program["expression"]
    if op["kind"] == "literal":
        value = op["value"]
    elif op["kind"] == "add":
        value = op["left"] + op["right"]
    else:
        raise ValueError("unsupported authored expression")
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError("outside authored u8 domain")
    return bytes([value])


def capsule(program: dict, output: bytes) -> dict:
    encoded = canonical(program)
    return {"blueprint_hex": encoded.hex(), "blueprint_sha256": digest(encoded),
            "output_sha256": digest(output), "profile": "authored-constant-emitter-v1"}


def recover(output: bytes, record: dict) -> dict:
    if record["profile"] != "authored-constant-emitter-v1":
        raise ValueError("unknown profile")
    raw = bytes.fromhex(record["blueprint_hex"])
    if digest(output) != record["output_sha256"] or digest(raw) != record["blueprint_sha256"]:
        raise ValueError("identity mismatch")
    restored = json.loads(raw)
    if compile_constant(restored) != output:
        raise ValueError("inconsistent blueprint/output")
    return restored


class ContractWitnesses(unittest.TestCase):
    def test_label_rename_keeps_reference(self):
        entities = {"field-1": {"label": "cash", "value": 12}}
        ref = "field-1"
        entities[ref]["label"] = "available_funds"
        self.assertEqual(entities[ref]["value"], 12)
        self.assertEqual(ref, "field-1")

    def test_duplicate_display_labels_need_scope(self):
        symbols = {("room-A", "count"): "field-1", ("room-B", "count"): "field-2"}
        self.assertNotEqual(symbols[("room-A", "count")], symbols[("room-B", "count")])
        candidates = [v for (_, label), v in symbols.items() if label == "count"]
        self.assertEqual(len(candidates), 2)  # An unscoped lookup must report ambiguity.

    def test_equal_mutable_values_are_not_aliases(self):
        separate = {"left": 0, "right": 0}
        separate["left"] = 1
        shared = {"cell": 0}
        shared["cell"] = 1
        self.assertEqual((separate["left"], separate["right"]), (1, 0))
        self.assertNotEqual((shared["cell"], shared["cell"]), (1, 0))

    def test_constant_value_sharing_does_not_imply_identity_sharing(self):
        original = {"a": ("object-A", 7), "b": ("object-B", 7)}
        shared = {"a": ("one-object", 7), "b": ("one-object", 7)}
        self.assertEqual([x[1] for x in original.values()], [x[1] for x in shared.values()])
        self.assertFalse(original["a"][0] == original["b"][0])
        self.assertTrue(shared["a"][0] == shared["b"][0])

    def test_pure_equivalence_exhausts_declared_u8_domain(self):
        self.assertIsNone(compare_u8(lambda x: (x + 1) % 256, lambda x: (x + 1) & 255))

    def test_saturation_is_not_wrap_except_in_narrower_domain(self):
        wrapping = lambda x: (x + 1) & 255
        saturating = lambda x: min(x + 1, 255)
        self.assertEqual(compare_u8(wrapping, saturating), {"input": 255, "left": 0, "right": 255})
        self.assertIsNone(compare_u8(wrapping, saturating, range(255)))

    def test_shared_code_does_not_merge_captured_environment(self):
        a, b = closure(1), closure(2)
        self.assertIs(a.__code__, b.__code__)
        self.assertEqual((a(5), b(5)), (6, 7))

    def test_read_timing_survives_update(self):
        counter = 1
        saved = (counter + 1) & 255
        counter = saved
        correct = saved < 3
        reloaded = ((counter + 1) & 255) < 3
        self.assertTrue(correct)
        self.assertFalse(reloaded)

    def test_explicit_activation_state_matches_reference(self):
        for n in range(33):
            self.assertEqual(trampoline_sum(n), n * (n + 1) // 2)

    def test_one_global_local_slot_breaks_nested_activation(self):
        self.assertEqual(trampoline_sum(2), 3)
        self.assertEqual(incorrectly_globalized_sum(2), 2)

    def test_extra_glue_event_is_observable(self):
        required = [("write", "cash", 7), ("return", 7)]
        bad_glue = [("write", "cash", 7), ("notify", "extra"), ("return", 7)]
        self.assertNotEqual(required, bad_glue)

    def test_segment_aliases_survive_flat_mapping(self):
        a = (0x1000 << 4) + 0x0010
        b = (0x1001 << 4) + 0x0000
        self.assertEqual(a, b)
        storage = {a: 0}
        storage[a] = 9
        self.assertEqual(storage[b], 9)

    def test_endianness_changes_encoding_not_abstract_value(self):
        value = 0x1234
        le, be = value.to_bytes(2, "little"), value.to_bytes(2, "big")
        self.assertNotEqual(le, be)
        self.assertEqual(int.from_bytes(le, "little"), int.from_bytes(be, "big"))

    def test_output_does_not_uniquely_select_blueprint(self):
        a = {"label": "three", "expression": {"kind": "literal", "value": 3}}
        b = {"label": "sum", "expression": {"kind": "add", "left": 1, "right": 2}}
        self.assertNotEqual(canonical(a), canonical(b))
        self.assertEqual(compile_constant(a), compile_constant(b))
        for source in (a, b):
            out = compile_constant(source)
            self.assertEqual(recover(out, capsule(source, out)), source)

    def test_capsule_rejects_changed_output_and_changed_input(self):
        source = {"label": "three", "expression": {"kind": "literal", "value": 3}}
        out = compile_constant(source)
        record = capsule(source, out)
        with self.assertRaises(ValueError):
            recover(b"\x04", record)
        record["blueprint_hex"] = canonical({"expression": {"kind": "literal", "value": 4}}).hex()
        with self.assertRaises(ValueError):
            recover(out, record)

    def test_deduplication_reverse_map_keeps_multiple_origins(self):
        reverse = {"shared-body": ["source-A.operation", "source-B.operation"]}
        self.assertEqual(len(reverse["shared-body"]), 2)
        self.assertNotEqual(reverse["shared-body"], ["source-A.operation"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractWitnesses))
    report = {
        "kind": "authored-contract-witness-checks",
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "passed": result.wasSuccessful(), "python": platform.python_version(),
        "source_sha256": digest(Path(__file__).read_bytes()),
        "scope": "Python-only illustrative counterexamples; not production UDC/provider/dedup tests",
        "finite_comparison": "u8 scalar candidates only; no general equivalence decision procedure",
        "not_tested": ["native memory/ABI", "DOS execution", "decompiler swapping", "fDisBull runtime", "generic reversible compiler"]
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
