#!/usr/bin/env node
/* Independent finite native-C -> browser-JavaScript comparison. The C oracle
 * owns expected values and executes the shipped native sources. No original
 * DOS process is launched. This check does not requalify original -> native.
 *
 * From replica: node web/tests/parity.js --report /private/parity-review.json
 * Optional: --only relations,verify,analyze,generate,candidates,hint,proof,replay,trace
 * Optional: --private-resources /path/to/Resources --skip-private
 * Private bytes are never written into source fixtures or the JSON receipt.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');

const nativeRoot = path.resolve(__dirname, '../..');
const webRoot = path.resolve(__dirname, '..');
const Core = require(path.join(webRoot, 'engine.js'));
const State = require(path.join(webRoot, 'state.js'));
const Proof = require(path.join(webRoot, 'proof.js'));
const Assets = require(path.join(webRoot, 'assets.js'));
const argv = process.argv.slice(2);
function option(name, fallback) {
  const at = argv.indexOf(name);
  if (at < 0) return fallback;
  if (at + 1 >= argv.length || argv[at + 1].startsWith('--')) throw new Error('Missing value for ' + name);
  return argv[at + 1];
}
const selectedKinds = option('--only', '').split(',').filter(Boolean);
const shouldRun = kind => !selectedKinds.length || selectedKinds.includes(kind);
const reportPath = option('--report', null);
const privateRoot = option('--private-resources', path.join(nativeRoot, 'Resources'));
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'sherlock-browser-parity-'));
const cc = process.env.CC || 'cc';
const baseFlags = ['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror'];
const result = {
  format: 'sherlock-browser-parity-1',
  scope: 'Finite execution comparison of the retained native C implementation and JavaScript; no new original DOS or AppKit qualification.',
  node: process.version,
  started_at: new Date().toISOString(),
  counts: {},
  failures: [],
  private_assets: {status: 'not_run'},
  negative_control: null,
  source_hashes: {}
};
let assertions = 0;
function hash(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function checked(label, operation, privateInput = false) {
  try { operation(); }
  catch (error) {
    result.failures.push({case: label, message: privateInput
      ? 'Private input comparison failed; input-bearing diagnostic details were withheld.'
      : String(error.message).slice(0, 4500)});
  }
}
function equal(actual, expected, label) {
  ++assertions;
  assert.deepEqual(actual, expected, label);
}
function execute(executable, args, settings = {}) {
  const child = spawnSync(executable, args, Object.assign({
    cwd: nativeRoot, encoding: 'utf8', timeout: 120000, maxBuffer: 32 * 1024 * 1024
  }, settings));
  if (child.error) throw child.error;
  if (child.status !== 0) throw new Error(`${executable} exited ${child.status}: ${String(child.stderr).slice(0, 3000)}`);
  return child.stdout;
}
function build(output, sources) {
  execute(cc, [...baseFlags, ...sources.map(file => path.join(nativeRoot, file)), '-o', output]);
}
function puzzleShape(puzzle, withAnswer = true) {
  const value = {
    number: puzzle.number, given: puzzle.given,
    clue_count: puzzle.clues.length,
    clues: puzzle.clues,
    original_slot: puzzle.original_slot.slice(0, puzzle.clues.length)
  };
  if (withAnswer) value.solution = puzzle.solution;
  return value;
}
function reportShape(report, keys) {
  const value = {};
  for (const key of keys) value[key] = key === 'reduction_complete' ? Number(report[key]) : report[key];
  return value;
}
function withoutHiddenAnswer(puzzle) {
  const copy = clone(puzzle);
  Object.defineProperty(copy, 'solution', {
    enumerable: true, configurable: true,
    get() { throw new Error('Hidden solution was consulted by a public operation.'); }
  });
  return copy;
}
function hintShape(hint) {
  const out = {};
  for (const key of ['kind','row','column','item','clue_index','explanation']) out[key] = hint[key];
  return out;
}
function stateShape(game) {
  const slots = game.board.clue_slots.map(bank => bank.map((group, index) => {
    const capacity = index ? 21 : 18;
    assert.equal(group.length, 256, 'State retains full native clue-slot capacity.');
    assert.ok(group.slice(capacity).every(value => value === -1), 'No clue leaks outside the visible grid.');
    return group.slice(0, capacity);
  }));
  assert.equal(game.undo_count, game.undo.length, 'Undo count matches the live history.');
  return {
    board: {candidates: game.board.candidates, chosen: game.board.chosen, clue_slots: slots},
    fixed: game.fixed,
    cell_bytes: Array.from({length:6}, (_,row) => Array.from({length:6}, (_,col) => State.cellByte(game,row,col))),
    undo_count: game.undo_count, outcome: game.outcome,
    elapsed_ms: String(game.elapsed_ms), limit_ms: String(game.limit_ms),
    display_time_ms: String(State.displayTimeMs(game)),
    paused: Number(game.paused), hint_pending: Number(game.hint_pending),
    pending_hint: game.pending_hint && game.pending_hint.kind ? hintShape(game.pending_hint) : null
  };
}
function gameFromFixture(fixture) {
  const game = State.createGame(withoutHiddenAnswer(fixture.puzzle), 0);
  const saved = fixture.state;
  game.board.candidates = clone(saved.board.candidates);
  game.board.chosen = clone(saved.board.chosen);
  game.board.clue_slots = saved.board.clue_slots.map(bank => bank.map(group => group.concat(Array(256-group.length).fill(-1))));
  game.fixed = clone(saved.fixed);
  game.elapsed_ms = BigInt(saved.elapsed_ms);
  game.limit_ms = BigInt(saved.limit_ms);
  game.paused = saved.paused;
  game.outcome = saved.outcome;
  game.hint_pending = saved.hint_pending;
  if (saved.pending_hint) game.pending_hint = clone(saved.pending_hint);
  Object.defineProperty(game.puzzle, 'solution', {
    enumerable: true, configurable: true,
    get() { throw new Error('Hidden solution was consulted by state or proof.'); }
  });
  return game;
}
function proofReport(report) {
  return reportShape(report, ['status','node_budget','nodes_used','deletion_checks','reduction_complete']);
}

try {
  result.compiler = execute(cc, ['--version']).split('\n')[0];
  const oraclePath = path.join(temporary, 'parity-oracle');
  build(oraclePath, ['web/tests/parity-oracle.c','core/sherlock_logic.c','state/sherlock_state.c','state/sherlock_hint_proof.c']);
  const oracleText = execute(oraclePath, []);
  result.oracle_output_sha256 = hash(oracleText);
  result.oracle_binary_sha256 = hash(fs.readFileSync(oraclePath));
  const fixtures = oracleText.trim().split('\n').map(line => JSON.parse(line));
  result.oracle_fixtures = fixtures.length;
  const nativeCli = path.join(temporary, 'sherlock-cli');
  build(nativeCli, ['core/sherlock_core.c','core/sherlock_logic.c','state/sherlock_state.c','state/sherlock_hint_proof.c','cli/sherlock_cli.c','cli/main.c']);
  const cli = args => JSON.parse(execute(nativeCli, args));
  for (const fixture of fixtures) {
    if (!shouldRun(fixture.kind)) continue;
    result.counts[fixture.kind] = (result.counts[fixture.kind] || 0) + 1;
    checked(fixture.case, () => {
      const expected = fixture.expected;
      if (fixture.kind === 'relations') {
        let index = 0, mutantDifferences = 0;
        for (let type=0;type<8;type++) for(let a=0;a<6;a++) for(let b=0;b<6;b++) for(let c=0;c<6;c++) {
          const native = fixture.values[index++];
          equal(Number(Core.relationHolds(type,a,b,c)),native,`predicate ${type}:${a},${b},${c}`);
          if (type===6) {
            // A plausible but incorrect NOT_BETWEEN: simply negate BETWEEN.
            const mutant = !(Math.abs(a-c)===2 && a+c===2*b);
            if (Number(mutant)!==native) mutantDifferences++;
          }
        }
        assert.ok(mutantDifferences>0,'The deliberately incorrect NOT_BETWEEN must fail.');
        result.negative_control = {mutation:'NOT_BETWEEN = !BETWEEN', rejected:true, differing_cases:mutantDifferences};
        result.counts.predicate_tuples = index;
      } else if (fixture.kind === 'verify') {
        const answer = clone(fixture.answer), input = withoutHiddenAnswer(fixture.puzzle);
        const observed = Core.verifyAnswer(input, answer);
        equal(reportShape(observed,['status','row','column','clue_index']), expected, fixture.case);
        equal(answer, fixture.answer, 'Verifier leaves submitted answer unchanged.');
        result.counts.hidden_answer_controls = (result.counts.hidden_answer_controls||0)+1;
      } else if (fixture.kind === 'analyze') {
        const observed = Core.analyze(withoutHiddenAnswer(fixture.puzzle), fixture.budget);
        equal(reportShape(observed,['status','solution_count','nodes','first_solution','second_solution']), expected, fixture.case);
        result.counts.hidden_answer_controls = (result.counts.hidden_answer_controls||0)+1;
      } else if (fixture.kind === 'generate') {
        const observed = Core.generate(fixture.seed, fixture.limits || undefined);
        equal(observed.status, expected.status, fixture.case+' status');
        equal(reportShape(observed.report,Object.keys(expected.report)), expected.report, fixture.case+' generation effort');
        if (expected.status===0) {
          equal(puzzleShape(observed.puzzle), puzzleShape(expected.puzzle), fixture.case+' puzzle');
          const canonical = cli(['generate','--seed',fixture.seed]);
          equal(Core.toDocument(observed.puzzle), canonical, fixture.case+' CLI public contract');
          const imported = Core.fromChallenge(canonical);
          equal(puzzleShape(imported,false), puzzleShape(expected.puzzle,false), fixture.case+' imported public semantics');
          assert.ok(!Object.hasOwn(imported,'solution'),'Import must not synthesize or retain an answer.');
          equal(Core.publicFingerprint(withoutHiddenAnswer(observed.puzzle)), canonical.challenge.public_fingerprint.hex, 'Fingerprint ignores hidden solution.');
          equal(Core.verifyAnswer(imported,expected.puzzle.solution).status,1,'Generated native answer verifies in JS.');
          for(let row=0;row<6;row++) {
            const answer=clone(expected.puzzle.solution);
            [answer[row][0],answer[row][1]]=[answer[row][1],answer[row][0]];
            equal(Core.verifyAnswer(imported,answer).status,0,'A changed permutation is rejected by the uniquely solved public challenge.');
            result.counts.generated_wrong_answers=(result.counts.generated_wrong_answers||0)+1;
          }
        } else assert.ok(!observed.puzzle,'Failed generation must not yield a substitute puzzle.');
      } else if (fixture.kind === 'candidates') {
        const masks=clone(fixture.candidates);
        equal(State.checkCandidates(withoutHiddenAnswer(fixture.puzzle),masks,fixture.budget),expected,fixture.case);
        equal(masks,fixture.candidates,'Candidate existence check is read-only.');
        result.counts.hidden_answer_controls=(result.counts.hidden_answer_controls||0)+1;
      } else if (fixture.kind === 'hint') {
        const game=gameFromFixture(fixture), before=stateShape(game);
        const observed=State.findHint(game,fixture.bank,fixture.budget);
        equal(observed.result,expected.result,fixture.case+' return');
        equal(hintShape(observed),expected.hint,fixture.case+' hint');
        equal(stateShape(game),before,'Hint selection is read-only.');
        result.counts.hidden_answer_controls=(result.counts.hidden_answer_controls||0)+1;
      } else if (fixture.kind === 'proof') {
        const game=gameFromFixture(fixture), before=stateShape(game), target=clone(fixture.selected);
        const observed=Proof.explainHint(game,target,fixture.budget);
        equal(observed.status,expected.status,fixture.case+' status');
        equal(proofReport(observed.report),expected.report,fixture.case+' report');
        // Invalid input may omit a record; all valid records are compared fully.
        if(expected.status!==-1) equal(observed.record,expected.record,fixture.case+' exact supporting premises');
        equal(stateShape(game),before,'Proof does not apply a move or charge time.');
        equal(target,fixture.selected,'Proof preserves the exact selected target.');
        result.counts.hidden_answer_controls=(result.counts.hidden_answer_controls||0)+1;
      } else if (fixture.kind === 'replay') {
        const record=clone(fixture.record), observed=Proof.replayHintProof(record,fixture.budget);
        equal(observed.status,expected.status,fixture.case+' status');
        equal(proofReport(observed.report),expected.report,fixture.case+' report');
        equal(record,fixture.record,'Replay does not change its supplied premises.');
      } else if (fixture.kind === 'trace') {
        const game=State.createGame(withoutHiddenAnswer(fixture.puzzle),fixture.limit_seconds);
        Object.defineProperty(game.puzzle,'solution',{enumerable:true,configurable:true,get(){throw new Error('State read hidden answer.');}});
        equal(stateShape(game),fixture.initial,fixture.case+' initial');
        for(let i=0;i<fixture.steps.length;i++) {
          const step=fixture.steps[i], fn=State[step.op];assert.equal(typeof fn,'function','Missing operation '+step.op);
          const observed=fn(game,...step.args);
          if(step.return!==null) equal(observed,step.return,`${fixture.case} step ${i} ${step.op} return`);
          equal(stateShape(game),step.state,`${fixture.case} step ${i} ${step.op} complete observable state`);
          result.counts.state_transitions=(result.counts.state_transitions||0)+1;
          if(step.op==='acceptHint'&&step.return===1)result.counts.hint_applications=(result.counts.hint_applications||0)+1;
        }
        if(fixture.case.startsWith('complete-hint-game-')) {
          equal(game.outcome,1,'Complete native and JS hint games end won.');
          result.counts.complete_hint_games=(result.counts.complete_hint_games||0)+1;
          result.counts.complete_game_hint_applications=(result.counts.complete_game_hint_applications||0)+
            fixture.steps.filter(step=>step.op==='acceptHint'&&step.return===1).length;
        }
      }
    });
  }

  // These are separately admitted, private historical inputs. Their contents
  // never enter a source fixture, generated webpage or evaluation receipt.
  const tablePath=path.join(privateRoot,'sherlock_puzzles.bin');
  if(argv.includes('--skip-private') || selectedKinds.length) {
    result.private_assets={status:'skipped',reason:'Explicit skip or focused kind selection.'};
  } else if(!fs.existsSync(tablePath)) {
    result.private_assets={status:'skipped',reason:'Private original resource table was not supplied.'};
  } else {
    result.private_assets={status:'passed',shi:[],original_numbers:[],input_payloads_exported:false};
    const assetOracle=path.join(temporary,'parity-assets');
    build(assetOracle,['web/tests/parity-assets.c','media/shi.c']);
    for(const file of ['SHERLOCK.SHI','ORGINAL.SHI','BOKSTAVE.SHI','KJETIL.SHI']) checked('asset-'+file,()=>{
      const filename=path.join(privateRoot,'Images',file), input=fs.readFileSync(filename);
      const native=execute(assetOracle,[filename],{encoding:null});
      const decoded=Assets.decodeSHI(new Uint8Array(input));
      equal(Buffer.from(decoded.pixels),native,'Every decoded SHI pixel matches compiled C.');
      equal(Buffer.from(Assets.encodeSHI(decoded)),input,'JS SHI encoding reproduces the admitted bytes.');
      result.private_assets.shi.push({file,bytes:input.length,pixels_compared:native.length,input_sha256:hash(input),pixel_sha256:hash(native)});
    },true);
    checked('original-puzzle-import',()=>{
      const input=fs.readFileSync(tablePath), table=Assets.loadOriginalTable(input);
      const numbers=[0,1,235,32767,32768,65534,65535];
      for(const number of numbers) {
        const puzzle=table.getPuzzle(number), canonical=cli(['puzzle','--number',String(number),'--data',tablePath]);
        equal(Core.toDocument(puzzle),canonical,'Original public challenge '+number+' matches compiled native CLI.');
        assert.ok(!Object.hasOwn(puzzle,'solution'),'Original loader must discard its hidden table answer.');
        result.private_assets.original_numbers.push({number,fingerprint:canonical.challenge.public_fingerprint.hex});
      }
      // Buffer is a Uint8Array subclass with aliasing slice(). Require owned
      // bytes even in Node, where the same adapter is used for verification.
      const original=Core.toDocument(table.getPuzzle(0));
      input.fill(255,16+65537*4,16+65537*4+38);
      equal(Core.toDocument(table.getPuzzle(0)),original,'The table owns validated input bytes, including Node Buffer inputs.');
      result.private_assets.input_ownership_control=true;
    },true);
  }
} catch(error) {
  result.failures.push({case:'harness',message:String(error.stack||error.message)});
} finally {
  const files=['core/sherlock_core.c','core/sherlock_core.h','core/sherlock_logic.c','core/sherlock_logic.h','state/sherlock_state.c','state/sherlock_state.h',
    'state/sherlock_hint_proof.c','state/sherlock_hint_proof.h','media/shi.c','media/shi.h','cli/sherlock_cli.c','cli/main.c',
    'web/engine.js','web/state.js','web/proof.js','web/assets.js','web/tests/parity-oracle.c','web/tests/parity-assets.c','web/tests/parity.js'];
  for(const file of files) {
    const filename=path.join(nativeRoot,file);
    if(fs.existsSync(filename))result.source_hashes[file]=hash(fs.readFileSync(filename));
  }
  result.assertions=assertions;
  result.status=result.failures.length?'failed':'passed';
  if(result.private_assets.status==='passed'&&result.failures.some(x=>x.case.startsWith('asset-')||x.case==='original-puzzle-import'))result.private_assets.status='failed';
  result.completed_at=new Date().toISOString();
  if(reportPath) {fs.mkdirSync(path.dirname(path.resolve(reportPath)),{recursive:true});fs.writeFileSync(reportPath,JSON.stringify(result,null,2)+'\n');}
  console.log(JSON.stringify(result,null,2));
  fs.rmSync(temporary,{recursive:true,force:true});
  if(result.failures.length)process.exitCode=1;
}
