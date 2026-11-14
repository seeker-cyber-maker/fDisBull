/* Focused semantic/import checks. The independent C oracle is parity.js. */
"use strict";
const assert = require("node:assert/strict");
const Core = require("../engine.js");
let checks = 0;
function check(name, run) {
    try { run(); ++checks; }
    catch (error) { error.message = name + ": " + error.message; throw error; }
}
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function empty() {
    return {
        number: 0, given: Array.from({length: 6}, () => Array(6).fill(-1)),
        clue_count: 0, clues: [], original_slot: []
    };
}
const straight = Array.from({length: 6}, () => [0, 1, 2, 3, 4, 5]);
const generated = Core.generate("42");
assert.equal(generated.status, 0);
const puzzle = generated.puzzle;
const document = Core.toDocument(puzzle);

check("retained seed zero fingerprint", () => {
    assert.equal(Core.publicFingerprint(Core.generate("0").puzzle), "cd2d37eb3c339602");
});
check("seed42 public document roundtrip", () => {
    assert.deepEqual(Core.toDocument(Core.fromChallenge(JSON.stringify(document))), document);
});
check("public exporter never reads solution", () => {
    const p = copy(puzzle);
    Object.defineProperty(p, "solution", {get() { throw new Error("hidden solution was read"); }});
    assert.deepEqual(Core.toDocument(p), document);
    assert.equal(Core.verifyAnswer(p, puzzle.solution).status, 1);
    assert.equal(Core.analyze(p).status, 1);
});
check("verifier uses public rules instead of a stored target", () => {
    const p = empty();
    p.solution = straight;
    const alternative = straight.map(row => row.slice().reverse());
    assert.equal(Core.verifyAnswer(p, alternative).status, 1);
});
check("incomplete search never calls an empty problem unsatisfiable", () => {
    const r = Core.analyze(empty(), "0");
    assert.equal(r.status, 3);
    assert.equal(r.nodes, "0");
    assert.equal(r.solution_count, 0);
});
check("empty public problem has multiple solutions", () => {
    const r = Core.analyze(empty(), "200000");
    assert.equal(r.status, 2);
    assert.equal(r.solution_count, 2);
    assert.equal(Core.verifyAnswer(empty(), r.first_solution).status, 1);
    assert.equal(Core.verifyAnswer(empty(), r.second_solution).status, 1);
    assert.notDeepEqual(r.first_solution, r.second_solution);
});
check("conflicting givens are logical unsat, not malformed schema", () => {
    const p = empty();
    p.given[0][0] = p.given[0][1] = 0;
    assert.equal(Core.analyze(p).status, 0);
    assert.equal(Core.analyze(p, 0).status, 3);
});
check("reference cards do not constrain an answer", () => {
    const p = empty();
    p.clues = [{type: 7, a: 0, b: 255, c: 255}];
    p.clue_count = 1;
    assert.equal(Core.verifyAnswer(p, straight).status, 1);
});
check("NOT_BETWEEN outer distance remains two", () => {
    assert.equal(Core.relationHolds(6, 0, 3, 2), true);
    assert.equal(Core.relationHolds(6, 0, 1, 2), false);
    assert.equal(Core.relationHolds(6, 0, 4, 5), false);
});
check("repeated operands preserve object identity", () => {
    const p = empty();
    p.clues = [{type: 1, a: 0, b: 0, c: 255}]; p.clue_count = 1;
    assert.equal(Core.analyze(p).status, 0);
    p.clues[0].type = 0;
    assert.equal(Core.analyze(p).status, 2);
});
check("over-capacity puzzle is rejected", () => {
    const p = empty();
    p.clues = Array.from({length: 257}, () => ({type: 7, a: 0, b: 255, c: 255}));
    p.clue_count = p.clues.length;
    assert.equal(Core.analyze(p).status, -1);
});
check("all256 clues are admitted", () => {
    const p = empty();
    p.clues = Array.from({length: 256}, () => ({type: 7, a: 0, b: 255, c: 255}));
    p.clue_count = p.clues.length;
    assert.equal(Core.analyze(p).status, 2);
});
check("noninteger and sparse givens are rejected", () => {
    for (const bad of [NaN, Infinity, 0.5, "0", null]) {
        const p = empty(); p.given[1][1] = bad;
        assert.equal(Core.analyze(p).status, -1);
    }
    const p = empty(); delete p.given[1];
    assert.equal(Core.analyze(p).status, -1);
    p.given[1] = Array(6);
    assert.equal(Core.analyze(p).status, -1);
});
check("answer dimensions, permutations and givens are checked", () => {
    assert.equal(Core.verifyAnswer(puzzle, Array(6)).status, -1);
    const p = empty();
    const bad = copy(straight); bad[0][1] = 0;
    assert.equal(Core.verifyAnswer(p, bad).status, 0);
    p.given[0][0] = 1;
    assert.equal(Core.verifyAnswer(p, straight).status, 0);
    delete bad[0][1];
    assert.equal(Core.verifyAnswer(empty(), bad).status, 0);
});
check("seed roundtrip retains all64 bits", () => {
    const g = Core.generate("18446744073709551615");
    assert.equal(g.status, 0);
    assert.equal(g.report.seed, "18446744073709551615");
    assert.equal(Core.fromChallenge(Core.toDocument(g.puzzle)).source.seed, g.report.seed);
});
check("unsafe numeric and malformed seeds refuse", () => {
    for (const seed of [9007199254740992, -1, "18446744073709551616", "1e2", "+2", " 2", 0.5, null]) {
        const g = Core.generate(seed);
        assert.equal(g.status, -1);
        assert.equal("puzzle" in g, false);
    }
});
check("zero generator budget returns no puzzle", () => {
    const g = Core.generate("42", {node_budget: "0", max_attempts: 16, max_givens: 3});
    assert.equal(g.status, 1);
    assert.equal("puzzle" in g, false);
});
check("generator limit validation refuses excessive givens", () => {
    assert.equal(Core.generate("42", {node_budget: "100", max_attempts: 16, max_givens: 4}).status, -1);
});
check("zero/maximum solver budgets are exact decimal values", () => {
    const p = empty();
    p.given = copy(straight);
    assert.equal(Core.analyze(p, "18446744073709551615").status, 1);
    for (const value of [-1, "1.0", "1e2", "18446744073709551616", 9007199254740992]) {
        assert.equal(Core.analyze(p, value).status, -1);
    }
});

function rejectedChange(name, mutate) {
    check(name, () => {
        const d = copy(document); mutate(d);
        assert.throws(() => Core.fromChallenge(d));
    });
}
rejectedChange("hidden solution at envelope boundary", d => { d.solution = copy(straight); });
rejectedChange("hidden solution at challenge boundary", d => { d.challenge.solution = copy(straight); });
rejectedChange("hidden answer inside source", d => { d.challenge.source.solution = copy(straight); });
rejectedChange("extra clue operand is rejected", d => {
    const binary = d.challenge.clues.find(c => !("c" in c)); binary.c = 0;
});
rejectedChange("mismatched fingerprint", d => { d.challenge.public_fingerprint.hex = "0000000000000000"; });
rejectedChange("mismatched challenge ID", d => { d.challenge.challenge_id += "0"; });
rejectedChange("unknown fingerprint algorithm", d => { d.challenge.public_fingerprint.algorithm = "unknown"; });
rejectedChange("wrong dimensions", d => { d.challenge.columns = 7; });
rejectedChange("unknown predicate semantics", d => { d.challenge.clue_predicates.not_between = "true"; });
rejectedChange("unknown object ID mapping", d => { d.challenge.object_ids.formula = "row + item"; });
rejectedChange("unrecognized source kind", d => { d.challenge.source.kind = "external"; });
rejectedChange("unknown generator version", d => { d.challenge.source.generator_version = 2; });
rejectedChange("seed as JSON number", d => { d.challenge.source.seed = 42; });
rejectedChange("noncanonical seed decimal", d => { d.challenge.source.seed = "042"; });
rejectedChange("numeric source node budget", d => { d.challenge.source.limits.node_budget = 1000000; });
rejectedChange("invalid given object identity", d => { d.challenge.givens[0].object = 99; });
rejectedChange("duplicate given cell", d => { d.challenge.givens.push(copy(d.challenge.givens[0])); });
rejectedChange("invalid clue index", d => { d.challenge.clues[0].index = 1; });
rejectedChange("unknown clue type", d => { d.challenge.clues[0].type = "not_between_entire_complement"; });
rejectedChange("bad operand", d => { d.challenge.clues[0].a = 36; });
rejectedChange("bad slot", d => { d.challenge.clues[0].display_slot = 75; });
rejectedChange("failed response", d => { d.ok = false; });
rejectedChange("wrong response kind", d => { d.kind = "verification"; });
rejectedChange("unknown generation field", d => { d.generation.accepted = true; });
rejectedChange("bad generation classification", d => { d.generation.classification = "multiple"; });
rejectedChange("generation attempts beyond declared source limit", d => { d.generation.attempts = 64; });
rejectedChange("generation nodes beyond declared source limit", d => { d.generation.nodes = "1000001"; });
rejectedChange("successful native source with an empty budget", d => { d.challenge.source.limits.node_budget = "0"; });
rejectedChange("nonenumerable hidden answer", d => {
    Object.defineProperty(d.challenge, "solution", {value: straight});
});
check("imports own all visible arrays and metadata", () => {
    const d = copy(document);
    const p = Core.fromChallenge(d);
    p.clues[0].a = (p.clues[0].a + 1) % 36;
    p.given[0][0] = 5;
    p.source.seed = "3";
    assert.deepEqual(d, document);
});

check("strict JSON accepts ordinary formatting and Unicode key escapes", () => {
    assert.equal(Core.parseJSON(' { "\\u0061" : [true, false, null, 1.5, -2e3] } ').a[4], -2000);
});
check("strict JSON refuses duplicate and escaped duplicate keys", () => {
    for (const text of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}']) {
        assert.throws(() => Core.parseJSON(text), /Duplicate/);
    }
});
check("strict JSON refuses decoded NUL and trailing documents", () => {
    for (const text of ['{"a":"\\u0000"}', '{} {}', '[]\u0000', '\uFEFF{}', '{"a":1,}', '[1,]', '01', '1e999']) {
        assert.throws(() => Core.parseJSON(text));
    }
});
check("strict JSON enforces byte and depth budgets", () => {
    assert.throws(() => Core.parseJSON('"abcdef"', 4), /byte limit/);
    assert.throws(() => Core.parseJSON("[".repeat(70) + "0" + "]".repeat(70)), /nesting/);
});
check("fromChallenge raw text uses duplicate-key boundary", () => {
    const text = JSON.stringify(document).replace('"ok":true', '"ok":false,"ok":true');
    assert.throws(() => Core.fromChallenge(text), /Duplicate/);
});
check("JSON parser does not pollute object prototypes", () => {
    const value = Core.parseJSON('{"__proto__":{"polluted":true}}');
    assert.equal(Object.getPrototypeOf(value), null);
    assert.equal({}.polluted, undefined);
});

console.log(JSON.stringify({suite: "browser-core-boundaries", checks: checks, passed: true}));
