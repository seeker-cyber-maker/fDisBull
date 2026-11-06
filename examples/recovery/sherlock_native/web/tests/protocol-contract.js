#!/usr/bin/env node
/* Browser protocol boundary checks; --native also compares complete JSON with
 * a freshly compiled retained C CLI. No original resource or emulator is used. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const C = require('../engine.js'), S = require('../state.js'), P = require('../proof.js');
const V = require('../protocol.js');
const clone = value => JSON.parse(JSON.stringify(value));
let checks = 0, nativeComparisons = 0;
function test(name, operation) {
    try { operation(); checks++; }
    catch (error) { error.message = name + ': ' + error.message; throw error; }
}
const generated = C.generate('42').puzzle, answer = clone(generated.solution);
const puzzle = C.fromChallenge(C.toDocument(generated));
Object.defineProperty(puzzle, 'solution', {get() { throw new Error('A hidden answer was read.'); }});
const identity = C.toChallenge(puzzle);
const session = {
    format: 'sherlock-browser-session-1', saved_at: '2026-11-06T00:00:00.000Z',
    game: S.exportGame(S.createGame(puzzle)),
    ui: {mode: 'remove', bank: 0, selected_cell: [0, 0], hint_display_ms: null}, art_name: 'Built-in symbols'
};
const capture = {
    format: 'sherlock-browser-repro-1', browser_version: 1,
    native_reference: 'ee62716e53f84c3f02814db4d7ff3a8884f2f152', note: 'Observed board',
    session: clone(session), provenance: 'generated-v1', challenge: C.toDocument(puzzle),
    recent_actions: [{action: 'new', source: clone(puzzle.source), elapsed_ms: '0'}],
    last_hint_evidence: null,
    assets: {art_name: 'Built-in symbols', original_table_loaded: false, table_name: '', bytes_included: false}
};
test('canonical successful verification shape', () => {
    const before = JSON.stringify(answer), result = V.verify(puzzle, answer);
    assert.deepEqual(Object.keys(result), ['format','kind','ok','challenge_id','source','public_fingerprint','accepted','reason','violation']);
    assert.equal(result.kind, 'verification'); assert.equal(result.ok, true); assert.equal(result.accepted, true);
    assert.equal(result.challenge_id, identity.challenge_id); assert.deepEqual(result.source, identity.source);
    assert.deepEqual(result.public_fingerprint, identity.public_fingerprint);
    assert.deepEqual(result.violation, {row: null, column: null, clue_index: null});
    assert.equal(JSON.stringify(answer), before); assert.ok(!JSON.stringify(result).includes('solution'));
    assert.deepEqual(V.verify(puzzle, {solution: answer}), result);
    assert.deepEqual(V.verify(puzzle, JSON.stringify({solution: answer})), result);
});
test('logical rejection remains a successful verification operation', () => {
    const invalid = clone(answer); invalid[0][0] = invalid[0][1];
    const result = V.verify(puzzle, invalid);
    assert.equal(result.ok, true); assert.equal(result.accepted, false);
    assert.equal(result.violation.row, 0); assert.equal(typeof result.violation.column, 'number');
});
test('canonical analysis shape and no witness leakage', () => {
    const result = V.analyze(puzzle);
    assert.deepEqual(Object.keys(result), ['format','kind','ok','challenge_id','source','public_fingerprint','classification','solutions_found','solution_count_is_exact','nodes','node_budget','reason']);
    assert.equal(result.classification, 'unique'); assert.equal(result.solutions_found, 1);
    assert.equal(result.solution_count_is_exact, true); assert.equal(result.node_budget, '200000');
    assert.ok(!Object.hasOwn(result, 'first_solution')); assert.ok(!Object.hasOwn(result, 'second_solution'));
    const unknown = V.analyze(puzzle, '0');
    assert.equal(unknown.classification, 'unknown'); assert.equal(unknown.solution_count_is_exact, false);
    assert.equal(unknown.nodes, '0'); assert.equal(unknown.node_budget, '0');
    assert.equal(V.analyze(puzzle, '18446744073709551615').node_budget, '18446744073709551615');
});
test('multiple and unsat count exactness', () => {
    const plain = {number: 0, given: Array.from({length:6},()=>Array(6).fill(-1)), clues: [], original_slot: []};
    const multiple = V.analyze(plain);
    assert.equal(multiple.classification, 'multiple'); assert.equal(multiple.solutions_found, 2);
    assert.equal(multiple.solution_count_is_exact, false);
    plain.given[0][0] = 0; plain.given[0][1] = 0;
    const unsat = V.analyze(plain);
    assert.equal(unsat.classification, 'unsat'); assert.equal(unsat.solutions_found, 0);
    assert.equal(unsat.solution_count_is_exact, true);
});
const answerText = JSON.stringify(answer);
const malformed = [
    '', 'null', '[]', '{}', '[[]]', answerText + ' x', answerText.slice(0,-1),
    answerText.replace(/\d/, '6'), answerText.replace(/\d/, '-0'), answerText.replace(/\d/, '1.0'),
    answerText.replace(/\d/, '1e0'), answerText.replace(/\d/, '01'), answerText.replace(/\d/, 'true'),
    '{"solution":'+answerText+',"solution":'+answerText+'}',
    '{"solution":'+answerText+',"accepted":true}',
    '{"solutiön":'+answerText+'}', '{"solution\\u0000":'+answerText+'}',
    '{"solutio\\q":'+answerText+'}', '{"\\u007golution":'+answerText+'}', '\ufeff'+answerText
];
for (const text of malformed) test('malformed answer has native error envelope ' + checks, () => {
    const result = V.verify(puzzle, text);
    assert.deepEqual(Object.keys(result), ['format','kind','ok','error']);
    assert.equal(result.kind, 'error'); assert.equal(result.ok, false); assert.equal(result.error.code, 'invalid_answer');
    assert.equal(typeof result.error.message, 'string'); assert.ok(Number.isInteger(result.error.byte_offset));
});
test('equivalent escaped solution key is admitted', () => {
    assert.equal(V.verify(puzzle, '{"solu\\u0074ion":'+answerText+'}').accepted, true);
});
test('answer byte limit and malformed object input', () => {
    assert.deepEqual(V.verify(puzzle, ' '.repeat(65537)), {
        format: 'sherlock-cli-1', kind: 'error', ok: false,
        error: {code: 'answer_too_large', message: 'The JSON answer exceeds 65536 bytes.', path: '-'}
    });
    const sparse = clone(answer); delete sparse[0][0];
    assert.equal(V.verify(puzzle, sparse).error.code, 'invalid_answer');
    const accessor = {}; Object.defineProperty(accessor, 'solution', {enumerable:true,get(){throw new Error('getter ran');}});
    assert.equal(V.verify(puzzle, accessor).error.code, 'invalid_answer');
});
test('invalid budget and engine errors use closed error envelopes', () => {
    for (const budget of [-1, '1.0', '1e0', '18446744073709551616', Number.MAX_SAFE_INTEGER+1, null]) {
        const result = V.analyze(puzzle, budget);
        assert.equal(result.kind, 'error'); assert.equal(result.ok, false); assert.equal(result.error.code, 'invalid_arguments');
    }
    assert.equal(V.verify({}, answer).error.code, 'puzzle_error');
    assert.equal(V.analyze({}).error.code, 'puzzle_error');
});
test('session unwrap and old optional UI field', () => {
    const before = JSON.stringify(session), result = V.unwrap(session);
    assert.equal(result.incoming, session.game); assert.equal(result.ui, session.ui);
    assert.equal(JSON.stringify(session), before);
    assert.deepEqual(V.unwrap(JSON.stringify(session)), result);
    const old = clone(session); delete old.saved_at; delete old.art_name; delete old.ui.hint_display_ms;
    assert.equal(V.unwrap(old).incoming, old.game);
    old.ui.hint_display_ms = '18446744073709551615'; assert.equal(V.unwrap(old).ui.hint_display_ms, old.ui.hint_display_ms);
});
test('capture unwrap including genuine hint evidence', () => {
    const game = S.createGame(puzzle), result = S.requestHint(game);
    assert.equal(result, 1);
    const proof = P.explainHint(game, game.pending_hint);
    const current = clone(capture);
    current.session.game = S.exportGame(game); current.session.ui.hint_display_ms = '0';
    current.last_hint_evidence = proof;
    current.recent_actions.push({action:'hint-offered',bank:0,target:clone(game.pending_hint),elapsed_ms:'0'});
    const before = JSON.stringify(current), unwrapped = V.unwrap(current);
    assert.equal(unwrapped.incoming, current.session.game); assert.equal(JSON.stringify(current), before);
    assert.deepEqual(V.unwrap(JSON.stringify(current)).incoming, current.session.game);
});
const invalidSessions = [
    s=>{s.solution=answer;}, s=>{s.extra=true;}, s=>{s.ui.solution=answer;}, s=>{s.ui.extra=true;},
    s=>{s.ui.mode='win';}, s=>{s.ui.bank=2;}, s=>{s.ui.selected_cell=[0,6];}, s=>{delete s.ui.selected_cell[0];},
    s=>{s.ui.hint_display_ms='01';}, s=>{s.ui.hint_display_ms='18446744073709551616';}, s=>{s.ui.hint_display_ms=0;},
    s=>{s.saved_at='tomorrow';}, s=>{s.art_name={};}, s=>{s.game.format='other';},
    s=>{s.game.puzzle.solution=answer;}, s=>{s.game.puzzle.clues[0].answer=0;},
    s=>{s.ui.selected_cell[Symbol('hidden')]=1;}
];
for (const change of invalidSessions) test('invalid session is rejected without mutation ' + checks, () => {
    const bad = clone(session); change(bad);
    const before = JSON.stringify(bad); assert.throws(()=>V.unwrap(bad)); assert.equal(JSON.stringify(bad), before);
});
const invalidCaptures = [
    c=>{c.solution=answer;}, c=>{c.browser_version=2;}, c=>{c.native_reference='unknown';},
    c=>{c.assets.bytes_included=true;}, c=>{c.assets.pixels=[0];},
    c=>{c.assets.original_table_loaded='false';}, c=>{c.assets.solution=answer;},
    c=>{c.recent_actions[0].answer=answer;}, c=>{c.recent_actions[0].extra=true;},
    c=>{c.recent_actions[0].source.solution=answer;}, c=>{c.recent_actions[0].elapsed_ms='-1';},
    c=>{c.last_hint_evidence={status:1,record:{solution:answer},report:{}};},
    c=>{c.challenge=C.toDocument(C.generate('43').puzzle);},
    c=>{c.challenge.challenge.clues[0].solution=answer;}, c=>{c.session.ui.extra=true;}
];
for (const change of invalidCaptures) test('invalid capture is rejected ' + checks, () => {
    const bad = clone(capture); change(bad); assert.throws(()=>V.unwrap(bad));
});
test('raw saves and public challenges pass through to their semantic owner', () => {
    assert.equal(V.unwrap(session.game).incoming, session.game);
    assert.equal(V.unwrap(identity).incoming, identity);
    assert.equal(V.unwrap(identity).ui, null);
    assert.throws(()=>V.unwrap('{"format":"sherlock-browser-session-1","format":"sherlock-browser-session-1"}'));
    const getter = {}; Object.defineProperty(getter, 'format', {enumerable:true,get(){throw new Error('getter ran');}});
    assert.throws(()=>V.unwrap(getter), /accessors/);
});
test('UMD installs the browser namespace', () => {
    const context = vm.createContext({TextEncoder});
    for (const file of ['engine.js','assets.js','protocol.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'), context, {filename:file});
    assert.deepEqual(Object.keys(context.SherlockProtocol), ['verify','analyze','unwrap']);
    assert.equal(vm.runInContext('SherlockProtocol.analyze(SherlockCore.generate("42").puzzle).classification',context), 'unique');
});

if (process.argv.includes('--native')) {
    const nativeRoot = path.resolve(__dirname,'../..'), temporary = fs.mkdtempSync(path.join(os.tmpdir(),'sherlock-protocol-'));
    const executable = path.join(temporary,'sherlock-cli');
    try {
        const sources = ['cli/main.c','cli/sherlock_cli.c','core/sherlock_core.c','core/sherlock_logic.c','state/sherlock_state.c','state/sherlock_hint_proof.c'];
        const built = spawnSync(process.env.CC || 'cc', ['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror',...sources.map(s=>path.join(nativeRoot,s)),'-o',executable], {encoding:'utf8',timeout:60000});
        assert.equal(built.status,0,built.stderr || String(built.error));
        function cli(args,input) {
            const result = spawnSync(executable,args,{input,encoding:'utf8',timeout:15000});
            assert.equal(result.error,undefined); assert.ok([0,1,2,3,4].includes(result.status));
            return JSON.parse(result.stdout);
        }
        for (const seed of ['0','42','9007199254740993','18446744073709551615']) {
            const canonical = C.generate(seed).puzzle, solution = clone(canonical.solution);
            for (const budget of ['0','1','200000','18446744073709551615']) {
                assert.deepEqual(V.analyze(canonical,budget),cli(['analyze','--seed',seed,'--max-nodes',budget])); nativeComparisons++;
            }
            const rejected = clone(solution); rejected[0][0] = rejected[0][1];
            for (const text of [JSON.stringify(solution),JSON.stringify({solution}),JSON.stringify(rejected)]) {
                assert.deepEqual(V.verify(canonical,text),cli(['verify','--seed',seed,'--solution','-'],text)); nativeComparisons++;
            }
        }
        for (const text of malformed.concat([' '.repeat(65537),'{"solu\\u0074ion":'+answerText+'}'])) {
            assert.deepEqual(V.verify(puzzle,text),cli(['verify','--seed','42','--solution','-'],text)); nativeComparisons++;
        }
        for (const budget of ['-1','1.0','1e0','18446744073709551616']) {
            assert.deepEqual(V.analyze(puzzle,budget),cli(['analyze','--seed','42','--max-nodes',budget])); nativeComparisons++;
        }
    } finally { fs.rmSync(temporary,{recursive:true,force:true}); }
}
console.log(JSON.stringify({suite:'browser-protocol-contract',checks,native_comparisons:nativeComparisons,passed:true}));
