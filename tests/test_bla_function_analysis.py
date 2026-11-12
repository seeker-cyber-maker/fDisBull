"""Authored boundary fixtures for the optional Babel source reducer.

These fixtures contain no archived challenge source, keys, or recovered flags.
The external Babel dependency is optional; the campaign never installs it.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
KNOWN_BABEL = Path(
    "/Volumes/CODEX/Codex_Projects/BLA-Crackmes-Sol-20261111/lasik-src/node_modules"
)


TEMPLATE = r'''
const {createHash} = require("node:crypto");
const SCOPE = "%%SCOPE%%";
const KEY_SHA256 = "%%KEY_SHA256%%";
const FLAG_SHA256 = "%%FLAG_SHA256%%";
const FLAG_CIPHER_HEX = "%%FLAG_CIPHER_HEX%%";
const LICENSE_RPC = {verifyEntitlement: "/fixture"};
function sha256Hex(value) {
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}
function deriveFlagMask(key) {
  return createHash("sha256").update(`fixture|${SCOPE}|${key}`, "utf8").digest();
}
function decodeFlagCipher(key) {
  const mask = deriveFlagMask(key);
  const cipher = Buffer.from(FLAG_CIPHER_HEX, "hex");
  return cipher.toString("utf8");
}
function tryUnlock(key) {
  if (typeof key !== "string") return null;
  if (sha256Hex(key) !== KEY_SHA256) return null;
  const flag = decodeFlagCipher(key);
  return flag;
}
module.exports = {tryUnlock, sha256Hex, LICENSE_RPC, SCOPE, KEY_SHA256, FLAG_SHA256};
'''


def target_source():
    heap = {
        "cursor": 0,
        "tick": 1,
        "rollingMask": 1,
        "splitShareA": [1],
        "splitShareB": [2],
        "slots": [dict(words=[0, 0, 0, 0], epoch=0, hmacTag=0) for _ in range(8)],
        "diffEnvelope": {"fixture": 0},
    }
    target = TEMPLATE
    for role, value in {
        "SCOPE": "fixture.scope",
        "KEY_SHA256": "fixture-key-commitment",
        "FLAG_SHA256": "fixture-result-commitment",
        "FLAG_CIPHER_HEX": "00",
    }.items():
        target = target.replace(f"%%{role}%%", value)
    for name, argument in (
        ("sha256Hex", "value"),
        ("deriveFlagMask", "key"),
        ("decodeFlagCipher", "key"),
        ("tryUnlock", "key"),
    ):
        target = target.replace(
            f"function {name}({argument}) {{",
            f"function {name}({argument}) {{\n  stepShadowHeapFixture(1);",
        )
    return (
        "const runtimeSeedFixture = (_deriveContainmentCorpusDigest_fixture(0) === 1 ? 1 : 0);\n"
        "function _deriveContainmentCorpusDigest_fixture() { return 1; }\n"
        f"const shadowHeapFixture = {json.dumps(heap)};\n"
        "function stepShadowHeapFixture(delta) {\n"
        "  const amount = Math.imul(delta, 1);\n"
        "  shadowHeapFixture.tick = (shadowHeapFixture.tick + amount) & 2147483647;\n"
        "  return shadowHeapFixture.tick;\n"
        "}\n"
        + target
    )


@pytest.fixture(scope="module")
def analyze():
    node = shutil.which("node")
    babel_root = Path(os.environ.get("FDISBULL_BABEL_ROOT", str(KNOWN_BABEL)))
    if not node or not (babel_root / "@babel/parser/package.json").is_file():
        pytest.skip("Node and an existing Babel root are required for optional static analysis")
    driver = r'''
const fs = require('node:fs');
const {analyze} = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
try {
  const value = analyze(input.template, input.target, {babelRoot:process.argv[2]});
  process.stdout.write(JSON.stringify({report:value.report, staticQualified:value.runtime.staticQualified,
    expectedCorpusDigest:value.runtime.expectedCorpusDigest}));
} catch (error) {
  process.stdout.write(JSON.stringify({error:error.message}));
}
'''

    def invoke(source, template=TEMPLATE):
        result = subprocess.run(
            [node, "-e", driver, str(REPOSITORY / "scripts/bla_function_analysis.cjs"), str(babel_root)],
            input=json.dumps({"template": template, "target": source}),
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    return invoke


def test_complete_authored_closure_requires_private_state_projection(analyze):
    result = analyze(target_source())
    assert "error" not in result
    assert result["staticQualified"] is True
    assert result["expectedCorpusDigest"] == 1
    report = result["report"]
    assert report["status"] == "structural_correspondence_under_assumptions"
    assert len(report["function_results"]) == 4
    assert all(item["equal"] for item in report["function_results"])
    assert all(item["equal"] for item in report["constant_results"])
    assert report["mutation_summary"]["full_state_equivalence"] is False
    assert len([entry for entry in report["contraction_ledger"] if entry["kind"] == "private_heap_step"]) == 4
    serialized = json.dumps(report)
    assert "fixture-key-commitment" not in serialized
    assert "fixture-result-commitment" not in serialized


def test_proved_false_guard_and_literal_fragments_reduce(analyze):
    source = target_source().replace(
        'return createHash("sha256").update(String(value), "utf8").digest("hex");',
        'if ((Math.imul(runtimeSeedFixture ^ 7, runtimeSeedFixture ^ 7) & 7) === 0) return "unreachable";\n'
        'return createHash("sha" + "256").update(String(value), "utf8").digest("hex");',
    )
    result = analyze(source)
    assert result["staticQualified"] is True
    assert result["report"]["guard_reductions"][0]["reduced"] is False


@pytest.mark.parametrize(
    "before,after",
    [
        ("stepShadowHeapFixture(1);", 'stepShadowHeapFixture((console.log("effect"), 1));'),
        ("const amount = Math.imul(delta, 1);", 'console.log("effect"); const amount = Math.imul(delta, 1);'),
        ("const amount = Math.imul(delta, 1);", "Math.imul = 0; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "const alias = Math; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "const alias = Math.imul; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "shadowHeapFixture.constructor.prototype.injected = 1; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", 'const key = "constructor"; shadowHeapFixture[key].prototype.injected = 1; const amount = 1;'),
        ("const amount = Math.imul(delta, 1);", "shadowHeapFixture.toString.injected = 1; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "shadowHeapFixture.slots.push.injected = 1; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "unboundGlobal = 1; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "runtimeSeedFixture = 1; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "unboundGlobal++; const amount = 1;"),
        ("const amount = Math.imul(delta, 1);", "for (unboundGlobal in shadowHeapFixture.slots) {} const amount = 1;"),
        ("function sha256Hex(value) {", "function sha256Hex(value) { const Math = {imul: () => 0};"),
        ("function sha256Hex(value) {", "function sha256Hex(value) { const runtimeSeedFixture = 1; if ((Math.imul(runtimeSeedFixture ^ 0, runtimeSeedFixture ^ 0) & 7) === 1) return 0;"),
        ("const {createHash} = require(\"node:crypto\");", 'const {createHash} = require("node:crypto"); createHash = () => 0;'),
        ("function sha256Hex(value) {", "function sha256Hex(createHash) {"),
        ("function sha256Hex(value) {", "function sha256Hex(__v0) {"),
        ("const runtimeSeedFixture =", "let runtimeSeedFixture ="),
    ],
)
def test_unproved_effects_and_binding_changes_fail_closed(analyze, before, after):
    source = target_source().replace(before, after)
    if before == "const runtimeSeedFixture =":
        source += "\nruntimeSeedFixture = 5;\n"
    result = analyze(source)
    assert "error" in result


@pytest.mark.parametrize("declaration", ["var hoisted = 1;", "let local = 1;", "function local() {}", "class Local {}"])
def test_guard_contraction_preserves_declaration_scope(analyze, declaration):
    source = target_source().replace(
        "function sha256Hex(value) {",
        "function sha256Hex(value) {\n"
        f"if ((Math.imul(runtimeSeedFixture ^ 7, runtimeSeedFixture ^ 7) & 7) === 0) {{ {declaration} }}",
    )
    result = analyze(source)
    assert "error" in result
    assert "declaration/hoisting" in result["error"]


@pytest.mark.parametrize(
    "before,after",
    [
        ('verifyEntitlement: "/fixture"', 'verifyEntitlement: "/changed"'),
        ('return cipher.toString("utf8");', 'return cipher.toString("hex");'),
        ('if (typeof key !== "string") return null;', 'if (typeof key === "string") return null;'),
    ],
)
def test_observable_changes_remain_differences(analyze, before, after):
    result = analyze(target_source().replace(before, after))
    assert "error" not in result
    assert result["staticQualified"] is False
    assert result["report"]["status"] == "different"


def test_effectful_guard_is_retained_as_difference(analyze):
    source = target_source().replace(
        "function sha256Hex(value) {",
        'function sha256Hex(value) { if (console.log("observable")) return null;',
    )
    result = analyze(source)
    assert "error" not in result
    assert result["staticQualified"] is False


def test_heap_reference_ownership_uses_function_identity(analyze):
    source = target_source() + """
function unrelatedFixture() {
  return function stepShadowHeapFixture() { return shadowHeapFixture; };
}
"""
    result = analyze(source)
    assert "error" in result
    assert "privacy/call discipline" in result["error"]


def test_prebound_external_write_is_not_a_mutator_local(analyze):
    source = "let outsideFixture = 0;\n" + target_source().replace(
        "const amount = Math.imul(delta, 1);",
        "outsideFixture = 1; const amount = Math.imul(delta, 1);",
    )
    result = analyze(source)
    assert "error" in result
    assert "privacy/call discipline" in result["error"]
