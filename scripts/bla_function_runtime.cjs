#!/usr/bin/env node
'use strict';
/** Complete-export differential oracle with explicit private-heap observations.
 * Original BLA artifacts stay external. VM wrappers are diagnostic isolation,
 * not a claim that node:vm is a hostile-code security boundary.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {analyze} = require('./bla_function_analysis.cjs');

const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const stable = x => JSON.stringify(x);
const hash = x => sha(stable(x));
const equal = (a, b, label) => {if (stable(a) !== stable(b)) throw Error('Differential mismatch: ' + label);};
const identifier = x => {
  if (typeof x !== 'string' || !/^[$A-Z_a-z][$\w]*$/.test(x)) throw Error('Invalid observation identifier');
  return x;
};
const valueRecord = x => Buffer.isBuffer(x) ? {type: 'buffer', hex: x.toString('hex')} :
  typeof x === 'string' ? {type: 'string', value: x} : {type: typeof x, value: x};

function load(root, item) {
  if (!item || typeof item.path !== 'string' || !/^[0-9a-f]{64}$/.test(item.sha256)) throw Error('Invalid source receipt');
  const file = path.resolve(root, item.path);
  if (!file.startsWith(path.resolve(root) + path.sep)) throw Error('Source outside selected root');
  const stat = fs.statSync(file);
  if (!stat.isFile() || stat.size > 1024 * 1024) throw Error('Target extent exceeds bound');
  const source = fs.readFileSync(file, 'utf8');
  if (sha(source) !== item.sha256) throw Error('Source hash mismatch');
  return source;
}

function heapChanges(before, after, prefix = '') {
  if (stable(before) === stable(after)) return [];
  if (before === null || after === null || typeof before !== 'object' || typeof after !== 'object') return [prefix];
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
  return keys.flatMap(k => heapChanges(before[k], after[k], prefix ? prefix + '.' + k : k));
}

function makeRealm(source, runtime, seedBase, commitment, mode = 'actual_crypto', instrument = false) {
  const events = [], writes = [];
  let hashNumber = 0, cipher = null;
  const bridge = {events, writes};
  const buffer = Object.freeze({
    from(...args) {
      events.push({op: 'Buffer.from', args: args.map(valueRecord)});
      return Buffer.from(...args);
    },
    alloc(...args) {
      events.push({op: 'Buffer.alloc', args: args.map(valueRecord)});
      if (mode === 'buffer_alloc_throw') throw new RangeError('authored Buffer.alloc failure');
      return Buffer.alloc(...args);
    },
  });
  const createHash = algorithm => {
    const id = ++hashNumber;
    events.push({op: 'crypto.createHash', algorithm, id});
    if (mode === 'create_throw') throw new Error('authored createHash failure');
    const native = crypto.createHash(algorithm);
    const updates = [];
    const wrapped = {
      update(data, encoding) {
        events.push({op: 'crypto.update', id, data: valueRecord(data), encoding: encoding ?? null});
        if (mode === 'update_throw') throw new Error('authored update failure');
        updates.push(data); native.update(data, encoding); return wrapped;
      },
      digest(encoding) {
        events.push({op: 'crypto.digest', id, encoding: encoding ?? null});
        if (mode === 'digest_throw') throw new Error('authored digest failure');
        if (mode !== 'actual_crypto' && mode !== 'create_throw' && mode !== 'update_throw' && mode !== 'digest_throw') {
          if (id === 1 && encoding === 'hex') return commitment.keySha256;
          if (id === 2 && encoding === undefined) {
            if (!cipher || cipher.length < 6 || (cipher.length - 1) % 32 < 5) throw Error('Unsupported modeled cipher layout');
            const mask = Buffer.alloc(32, 0x41);
            const prefix = Buffer.from(mode === 'bad_prefix' ? 'NOPE!' : 'FLAG{');
            for (let i = 0; i < prefix.length; i++) mask[i] = cipher[i] ^ prefix[i];
            mask[(cipher.length - 1) % 32] = cipher[cipher.length - 1] ^ 0x7d;
            return mask;
          }
          if (id === 3 && encoding === 'hex') return mode === 'bad_final_hash' ? '0'.repeat(64) : commitment.flagSha256;
        }
        return native.digest(encoding);
      },
    };
    return wrapped;
  };
  const requireStub = name => {
    events.push({op: 'require', name});
    if (name !== 'node:crypto') throw Error('Target requested an unadmitted module');
    return Object.freeze({createHash});
  };
  requireStub.main = Object.freeze({});
  const module = {exports: {}};
  const context = vm.createContext({Buffer: buffer, process: Object.freeze({
      hrtime: Object.freeze({bigint: () => BigInt(seedBase)}), pid: 42,
      execArgv: Object.freeze([]), argv: Object.freeze([]),
      exit: () => {throw Error('CLI exit outside exported-function contract');},
    }), console: Object.freeze({log: () => {throw Error('Unexpected console effect');},
      error: () => {throw Error('Unexpected console effect');}})},
    {codeGeneration: {strings: false, wasm: false}});
  const heap = runtime?.heapName ? identifier(runtime.heapName) : null;
  const seed = runtime?.seedName ? identifier(runtime.seedName) : null;
  const corpus = runtime?.corpusName ? identifier(runtime.corpusName) : null;
  const heapStep = runtime?.heapStepName ? identifier(runtime.heapStepName) : null;
  const heapProof = runtime?.shadowHeapProof;
  if (heapProof?.status === 'proved' && heapProof.source?.sha256 !== sha(source))
    throw Error('Shadow-heap proof source mismatch');
  const assertHeapInvariant = value => {
    if (heapProof?.status === 'proved') {
      const {checkHeapInvariant} = require('./bla_shadow_heap_proof.cjs');
      if (!checkHeapInvariant(value, heapProof)) throw Error('Shadow-heap invariant failed');
    }
  };
  const cipherName = identifier(runtime?.cipherName || 'FLAG_CIPHER_HEX');
  const suffix = `\n;return {exports:module.exports, capture:()=>JSON.parse(JSON.stringify(${heap || 'null'})),` +
    `heap:()=>${heap || 'null'}, setHeap:value=>{${heap ? heap + '=value;' : ''}},` +
    `step:${heapStep ? 'delta=>' + heapStep + '(delta)' : 'null'},` +
    'exportState:()=>JSON.parse(JSON.stringify({SCOPE:module.exports.SCOPE,KEY_SHA256:module.exports.KEY_SHA256,' +
    'FLAG_SHA256:module.exports.FLAG_SHA256,LICENSE_RPC:module.exports.LICENSE_RPC})),' +
    `info:()=>({seed:${seed || 'null'},corpusDigest:${corpus ? corpus + '(0)' : 'null'},cipher:${cipherName}})};`;
  const original = source.replace(/^#![^\n]*/, line => ' '.repeat(line.length));
  const wrapperSource = '(function(exports,require,module,__filename,__dirname){\n' + original + suffix + '\n})';
  const executionReceipt = {source_sha256: sha(source), commonjs_wrapper_sha256: sha(wrapperSource),
    observer_suffix_sha256: sha(suffix), hashbang_masked: original !== source,
    function_bodies_rewritten: false, private_heap_proxy: Boolean(instrument && heap),
    shadow_heap_proof_source_bound: heapProof?.status === 'proved'};
  const wrapper = new vm.Script(wrapperSource,
    {filename: 'hash-bound-bla-module.cjs'}).runInContext(context, {timeout: 1000});
  context.__wrapper = wrapper; context.__require = requireStub; context.__module = module;
  context.__realm = vm.runInContext('__wrapper(__module.exports,__require,__module,"target.cjs",".")', context,
                                   {timeout: 1000});
  const realm = context.__realm;
  const plain = value => JSON.parse(JSON.stringify(value));
  const info = plain(vm.runInContext('__realm.info()', context, {timeout: 500}));
  cipher = Buffer.from(info.cipher, 'hex');
  if (realm.exports.KEY_SHA256 !== commitment.keySha256 || realm.exports.FLAG_SHA256 !== commitment.flagSha256)
    throw Error('Target commitment mismatch');
  if (seed !== null && (info.seed & 3) !== 1) throw Error('Intact-corpus seed guard invariant failed');
  if (corpus !== null) {
    const name = corpus.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = source.match(new RegExp(name + '\\(0\\) === (\\d+)'));
    const expected = runtime.expectedCorpusDigest ?? (match ? Number(match[1]) : NaN);
    if (!Number.isInteger(expected) || info.corpusDigest !== expected) throw Error('Actual corpus digest differs from seed guard');
    info.expectedCorpusDigest = expected;
  }
  const initialization = {events: [...events], heap: plain(realm.capture()), globals: Object.getOwnPropertyNames(context).sort()};
  if (heap) assertHeapInvariant(initialization.heap);
  events.length = 0;
  function instrumentHeap() {
    if (!instrument || !heap) return;
    const cache = new WeakMap();
    const proxify = (object, prefix) => {
      if (!object || typeof object !== 'object') return object;
      if (cache.has(object)) return cache.get(object);
      const proxy = new Proxy(object, {
        get(target, key) {return proxify(Reflect.get(target, key), prefix ? prefix + '.' + String(key) : String(key));},
        set(target, key, value) {
          const property = prefix ? prefix + '.' + String(key) : String(key);
          const before = target[key]; const ok = Reflect.set(target, key, value);
          writes.push({path: property, before, after: value}); return ok;
        },
      });
      cache.set(object, proxy); return proxy;
    };
    realm.setHeap(proxify(realm.heap(), ''));
  }
  instrumentHeap();
  function observe(expression) {
    hashNumber = 0; events.length = 0; writes.length = 0;
    const before = plain(vm.runInContext('__realm.capture()', context, {timeout: 500}));
    if (heap) assertHeapInvariant(before);
    const exportsBefore = plain(vm.runInContext('__realm.exportState()', context, {timeout: 500}));
    context.__coercionTrace = [];
    const result = plain(vm.runInContext(`(()=>{try {const value=${expression};` +
      'return {kind:"return",value,input_effects:__coercionTrace};}' +
      'catch(error){return {kind:"throw",name:error.name,message:error.message,input_effects:__coercionTrace};}})()', context, {timeout: 500}));
    const after = plain(vm.runInContext('__realm.capture()', context, {timeout: 500}));
    if (heap) assertHeapInvariant(after);
    const exportsAfter = plain(vm.runInContext('__realm.exportState()', context, {timeout: 500}));
    return {result, events: [...events], before, after, exportsBefore, exportsAfter,
            writes: [...writes], changes: heapChanges(before, after),
            heapInvariantChecked: Boolean(heap && heapProof?.status === 'proved')};
  }
  function call(name, input) {
    return observe(`__realm.exports[${JSON.stringify(name)}]((${input}))`);
  }
  function installHeap(value) {
    if (!heap) throw Error('No private heap boundary');
    assertHeapInvariant(value);
    context.__heapPayload = stable(value);
    vm.runInContext('__realm.setHeap(JSON.parse(__heapPayload))', context, {timeout: 500});
    instrumentHeap();
  }
  function step(delta) {
    if (!heapStep || !Number.isSafeInteger(delta)) throw Error('No numeric private-step boundary');
    context.__stepDelta = delta;
    return observe('__realm.step(__stepDelta)');
  }
  return {call, step, installHeap, info, initialization, executionReceipt};
}

function sanitizedCall(record) {
  return {result_kind: record.result.kind,
    result_type: record.result.kind === 'throw' ? record.result.name :
                 record.result.value === null ? 'null' : typeof record.result.value,
    input_effects: record.result.input_effects?.length || 0,
    input_effects_sha256: hash(record.result.input_effects || []),
    exception_name: record.result.kind === 'throw' ? record.result.name : null,
    exception_message_sha256: record.result.kind === 'throw' ? hash(record.result.message) : null,
    result_sha256: hash(record.result), ordered_calls: record.events.length,
    ordered_calls_sha256: hash(record.events), heap_before_sha256: hash(record.before),
    heap_after_sha256: hash(record.after), heap_changed_paths: record.changes.length,
    exports_before_sha256: hash(record.exportsBefore), exports_after_sha256: hash(record.exportsAfter),
    heap_changed_paths_sha256: hash(record.changes), recorded_writes: record.writes.length,
    recorded_writes_sha256: hash(record.writes), heap_invariant_checked: record.heapInvariantChecked};
}

/** Independent concrete oracle: BigInt modular arithmetic instead of JS bitwise
 * evaluation. This finite cross-check does not establish the static induction.
 */
function referenceShadowHeapStep(input, delta) {
  if (typeof delta !== 'number' || !Number.isSafeInteger(delta)) throw Error('Unsupported oracle delta');
  const heap = JSON.parse(stable(input));
  const signed32 = x => BigInt.asIntN(32, x);
  const low31 = x => Number(BigInt.asUintN(31, x));
  const d = signed32(BigInt(delta)) ^ BigInt(heap.tick) | 1n;
  const mask = signed32(signed32(d * 0x9e3779b9n) ^ (BigInt(heap.rollingMask) >> 7n));
  heap.tick = low31(BigInt(heap.tick) + 1n);
  heap.rollingMask = low31(mask ^ 0x5bd1e995n);
  for (const offset of [0, 1, 2, 3, 4, 5, 6, 7]) {
    const index = (input.cursor + offset) % heap.slots.length;
    const slot = heap.slots[index];
    const mix = BigInt(low31(mask ^ signed32(BigInt(index + 1) * 0x85ebca6bn)));
    const next0 = low31(BigInt(slot.words[0]) ^ mix);
    const next1 = low31((BigInt(slot.words[1]) + BigInt(next0)) ^ (mix >> 3n));
    const next2 = low31(BigInt(slot.words[2]) ^ BigInt(next1) ^ 0x27d4eb2dn);
    const next3 = low31((BigInt(slot.words[3]) ^ BigInt(next2)) + BigInt(offset));
    slot.words = [next0, next1, next2, next3];
    slot.epoch = low31(BigInt(slot.epoch) + 1n);
    slot.hmacTag = low31(BigInt(slot.hmacTag) ^ BigInt(next0));
  }
  heap.cursor = (input.cursor + 8) % heap.slots.length;
  const roll = (mask & 0x7fffn) | 1n;
  for (const field of ['splitShareA', 'splitShareB'])
    heap[field] = heap[field].map(value => Number(BigInt(value) ^ roll));
  for (const field of Object.keys(heap.diffEnvelope)) {
    const found = /^state_diff_frontier_(\d+)$/.exec(field);
    if (!found) throw Error('Unsupported oracle frontier');
    heap.diffEnvelope[field] = low31(BigInt(heap.diffEnvelope[field]) ^ (mask + BigInt(found[1]) * 37n));
  }
  return {heap, result: heap.rollingMask};
}

function crosscheckShadowHeap(source, runtime, seedBase, commitment) {
  const original = makeRealm(source, runtime, seedBase, commitment);
  const diagnostic = makeRealm(source, runtime, seedBase, commitment, 'actual_crypto', true);
  const initial = original.initialization.heap;
  const expectedWrites = 3 + 8 * 6 + initial.splitShareA.length * 2 + Object.keys(initial.diffEnvelope).length;
  assert.equal(expectedWrites, runtime.shadowHeapProof.mutation.max_numeric_writes);
  const deltas = [['zero', 0], ['one', 1], ['negative_one', -1], ['max_i32', 0x7fffffff],
    ['min_i32', -0x80000000], ['max_u32', 0xffffffff], ['max_safe_integer', Number.MAX_SAFE_INTEGER],
    ['min_safe_integer', Number.MIN_SAFE_INTEGER]];
  const rows = [];
  for (const profile of ['zero', 'maximum_u31', 'patterned']) {
    let counter = 0;
    const number = () => profile === 'zero' ? 0 : profile === 'maximum_u31' ? 0x7fffffff :
      Math.imul(++counter, 0x45d9f3b) & 0x7fffffff;
    const shape = JSON.parse(stable(initial));
    shape.tick = number(); shape.rollingMask = number();
    for (const slot of shape.slots) {
      slot.words = slot.words.map(number); slot.epoch = number(); slot.hmacTag = number();
    }
    shape.splitShareA = shape.splitShareA.map(number);
    shape.splitShareB = shape.splitShareB.map(number);
    for (const key of Object.keys(shape.diffEnvelope)) shape.diffEnvelope[key] = number();
    for (const cursor of [0, initial.slots.length - 1]) for (const [label, delta] of deltas) {
      const input = {...shape, cursor};
      const expected = referenceShadowHeapStep(input, delta);
      original.installHeap(input); diagnostic.installHeap(input);
      const actual = original.step(delta), observed = diagnostic.step(delta);
      equal(actual.result, {kind: 'return', value: expected.result, input_effects: []}, 'private-step/reference-result');
      equal(actual.after, expected.heap, 'private-step/reference-state');
      equal(observed.result, actual.result, 'private-step/proxy-result');
      equal(observed.after, actual.after, 'private-step/proxy-state');
      equal(actual.events, [], 'private-step/no-external-calls');
      equal(observed.events, actual.events, 'private-step/proxy-calls');
      equal(actual.exportsBefore, actual.exportsAfter, 'private-step/stable-exports');
      assert.equal(observed.writes.length, expectedWrites);
      rows.push({profile, cursor_boundary: cursor === 0 ? 'first' : 'last', delta_class: label,
        reference_state_sha256: hash(expected.heap), reference_result_sha256: hash(expected.result),
        concrete_reference_equal: true, diagnostic_equal: true, invariant_preserved: true,
        original: sanitizedCall(actual), diagnostic_proxy: sanitizedCall(observed)});
    }
  }
  return {status: 'verified_finite_boundary_crosscheck', cases: rows.length,
    oracle: 'Independent BigInt modular arithmetic transition', invariant_checked_each_boundary: true,
    observation: 'Return, serialized private data, calls and write counts; object-layout preservation is a separate static obligation',
    exact_diagnostic_writes_per_step: expectedWrites, rows, rows_sha256: hash(rows),
    limitation: 'Finite real-source cross-check; the universal shape/termination proof is a separate certificate'};
}

const INPUTS = [
  ['empty', '""'], ['short', '"x".repeat(11)'], ['min_length', '"x".repeat(12)'],
  ['max_length', '"x".repeat(96)'], ['too_long', '"x".repeat(97)'],
  ['unicode', '"λ☃😀".repeat(5)'], ['null', 'null'], ['undefined', 'undefined'],
  ['number', '17'], ['boolean', 'true'], ['symbol', 'Symbol("authored")'],
  ['boxed_string', 'new String("authored-key-string")'], ['array', '[1,2,3]'],
  ['coercion_object', '({toString(){__coercionTrace.push("toString");return "authored-coercion";}})'],
  ['primitive_hook', '({[Symbol.toPrimitive](hint){__coercionTrace.push("primitive:"+hint);return "authored-primitive";}})'],
  ['throwing_coercion', '({toString(){__coercionTrace.push("throwing-toString");throw new TypeError("authored coercion failure");}})'],
  ['honeypot', '"/internal/v2/license/verify-entitlement"'],
];

/** Two independent private states share the same public input/provider state.
 * These finite observations cross-check the separate noninterference proof.
 */
function crosscheckFunctionNoninterference(source, runtime, seedBase, commitment) {
  const excluded = new Set(['boxed_string','array','coercion_object','primitive_hook','throwing_coercion']);
  const primitives = [...INPUTS.filter(([name]) => !excluded.has(name)),
    ['nan','NaN'],['positive_infinity','Infinity'],['negative_infinity','-Infinity'],
    ['negative_zero','-0'],['bigint','12345678901234567890n']];
  function privateState(initial, maximum) {
    const state = JSON.parse(stable(initial)), value = maximum ? 0x7fffffff : 0;
    state.tick = value; state.rollingMask = value;
    state.cursor = maximum ? state.slots.length - 1 : 0;
    for (const slot of state.slots) {
      slot.words = slot.words.map(() => value); slot.epoch = value; slot.hmacTag = value;
    }
    state.splitShareA = state.splitShareA.map(() => value);
    state.splitShareB = state.splitShareB.map(() => value);
    for (const name of Object.keys(state.diffEnvelope)) state.diffEnvelope[name] = value;
    return state;
  }
  const rows = [];
  for (const mode of ['actual_crypto','modeled_success','bad_prefix','bad_final_hash',
                       'create_throw','update_throw','digest_throw','buffer_alloc_throw']) {
    const first = makeRealm(source, runtime, seedBase, commitment, mode);
    const second = makeRealm(source, runtime, seedBase, commitment, mode);
    const clean = makeRealm(runtime.materializedCleanSource, null, seedBase, commitment, mode);
    first.installHeap(privateState(first.initialization.heap, false));
    second.installHeap(privateState(second.initialization.heap, true));
    const cases = mode === 'actual_crypto' ? ['sha256Hex','tryUnlock'].flatMap(fn =>
      primitives.map(([label,input]) => ({fn,label,input}))) :
      [{fn:'tryUnlock',label:mode,input:'"authored-contract-key"'}];
    for (const {fn,label,input} of cases) {
      const a = first.call(fn,input), b = second.call(fn,input), reference = clean.call(fn,input);
      if (stable(a.before) === stable(b.before)) throw Error('Distinct private-state premise was lost');
      equal(a.result,b.result,'two-heaps/result'); equal(a.result,reference.result,'two-heaps/clean-result');
      equal(a.events,b.events,'two-heaps/ordered-calls'); equal(a.events,reference.events,'two-heaps/clean-calls');
      equal(a.exportsBefore,b.exportsBefore,'two-heaps/public-entry');
      equal(a.exportsAfter,b.exportsAfter,'two-heaps/public-exit');
      equal(a.exportsAfter,reference.exportsAfter,'two-heaps/clean-public-exit');
      equal(a.exportsBefore,a.exportsAfter,'two-heaps/public-frame');
      if (!a.heapInvariantChecked || !b.heapInvariantChecked) throw Error('Private-state invariant was not checked');
      rows.push({mode,function:fn,input_class:label,entry_heaps_differ:true,
        caller_observations_equal:true,clean_observations_equal:true,heap_invariants_preserved:true,
        first:sanitizedCall(a),second:sanitizedCall(b),clean:sanitizedCall(reference)});
    }
  }
  return {status:'verified_finite_two_heap_crosscheck',cases:rows.length,
    actual_crypto_cases:rows.filter(row => row.mode === 'actual_crypto').length,
    modeled_call_cases:rows.filter(row => row.mode !== 'actual_crypto').length,
    private_profiles:['zero_numeric_cells_first_cursor','maximum_u31_cells_last_cursor'],
    repeated_calls_preserve_related_public_state:true,rows,rows_sha256:hash(rows),
    limitation:'Finite original-code observations; the universal two-run and composition claims are separate source certificates'};
}

function run(config) {
  if (!config || !Array.isArray(config.targets) || config.targets.length < 1 || config.targets.length > 3 ||
      !/^[0-9a-f]{64}$/.test(config.commitment?.keySha256 || '') ||
      !/^[0-9a-f]{64}$/.test(config.commitment?.flagSha256 || '')) throw Error('Invalid campaign configuration');
  const template = load(config.root, config.template);
  const seeds = config.seedBases || [0, 4660];
  if (!Array.isArray(seeds) || !seeds.length || seeds.length > 4 || seeds.some(s => !Number.isSafeInteger(s) || s < 0 || s > 0x7ffff))
    throw Error('Invalid deterministic seed bases');
  const tiers = [];
  for (const target of config.targets) {
    const source = load(config.root, target);
    const analysis = analyze(template, source, {babelRoot: config.babelRoot});
    if (!analysis.runtime?.staticQualified) throw Error('Static whole-function observer contract not qualified');
    if (analysis.runtime.shadowHeapProof?.status !== 'proved') throw Error('Static shadow-heap proof not qualified');
    if (analysis.runtime.heapNoninterference?.status !== 'proved' ||
        analysis.runtime.wholeFunctionEquivalence?.status !== 'equivalent_under_contract')
      throw Error('Composed whole-function proof not qualified');
    const heapBoundary = crosscheckShadowHeap(source, analysis.runtime, seeds[0], config.commitment);
    const noninterferenceBoundary = crosscheckFunctionNoninterference(source, analysis.runtime, seeds[0], config.commitment);
    const rows = [];
    const seedEvidence = [];
    for (const seedBase of seeds) {
      const original = makeRealm(source, analysis.runtime, seedBase, config.commitment);
      const instrumented = makeRealm(source, analysis.runtime, seedBase, config.commitment, 'actual_crypto', true);
      const clean = makeRealm(analysis.runtime.materializedCleanSource, null, seedBase, config.commitment);
      seedEvidence.push({seed_base: seedBase, actual_seed: original.info.seed,
        corpus_digest: original.info.corpusDigest, expected_corpus_digest: original.info.expectedCorpusDigest,
        seed_low_bits: original.info.seed & 3, invariant_verified: true,
        initial_private_heap_sha256: hash(original.initialization.heap),
        module_initialization_calls_sha256: hash(original.initialization.events),
        module_global_surface_sha256: hash(original.initialization.globals),
        execution_receipts: {target: original.executionReceipt, clean: clean.executionReceipt,
          diagnostic_proxy: instrumented.executionReceipt}});
      for (const fn of ['sha256Hex', 'tryUnlock']) for (const [label, input] of INPUTS) {
        const left = clean.call(fn, input), right = original.call(fn, input), observed = instrumented.call(fn, input);
        equal(right.result, left.result, fn + '/' + label + '/return-or-throw');
        equal(right.events, left.events, fn + '/' + label + '/ordered-calls');
        equal(observed.result, right.result, fn + '/' + label + '/instrumented-return');
        equal(observed.events, right.events, fn + '/' + label + '/instrumented-calls');
        equal(observed.after, right.after, fn + '/' + label + '/instrumented-heap');
        equal(right.exportsBefore, left.exportsBefore, fn + '/' + label + '/entry-export-state');
        equal(right.exportsAfter, left.exportsAfter, fn + '/' + label + '/exit-export-state');
        equal(right.exportsAfter, right.exportsBefore, fn + '/' + label + '/stable-export-state');
        assert.equal(left.before, null); assert.equal(left.after, null);
        if (stable(right.before) === stable(right.after)) throw Error('Expected private shadow-heap mutation was missing');
        rows.push({profile: 'actual_crypto', function: fn, input_class: label, seed_base: seedBase,
                   caller_observations_equal: true, instrumentation_observations_equal: true,
                   clean: sanitizedCall(left), target: sanitizedCall(right), diagnostic_proxy: sanitizedCall(observed)});
      }
      for (const mode of ['modeled_success', 'bad_prefix', 'bad_final_hash', 'create_throw', 'update_throw', 'digest_throw', 'buffer_alloc_throw']) {
        const targetRealm = makeRealm(source, analysis.runtime, seedBase, config.commitment, mode);
        const cleanRealm = makeRealm(analysis.runtime.materializedCleanSource, null, seedBase, config.commitment, mode);
        const observedRealm = makeRealm(source, analysis.runtime, seedBase, config.commitment, mode, true);
        const left = cleanRealm.call('tryUnlock', '"authored-contract-key"');
        const right = targetRealm.call('tryUnlock', '"authored-contract-key"');
        const observed = observedRealm.call('tryUnlock', '"authored-contract-key"');
        equal(right.result, left.result, mode + '/return-or-throw'); equal(right.events, left.events, mode + '/ordered-calls');
        equal(observed.result, right.result, mode + '/instrumented-return');
        equal(observed.events, right.events, mode + '/instrumented-calls');
        equal(observed.after, right.after, mode + '/instrumented-heap');
        equal(right.exportsBefore, left.exportsBefore, mode + '/entry-export-state');
        equal(right.exportsAfter, left.exportsAfter, mode + '/exit-export-state');
        equal(right.exportsAfter, right.exportsBefore, mode + '/stable-export-state');
        assert.equal(left.before, null); assert.equal(left.after, null);
        if (stable(right.before) === stable(right.after)) throw Error('Expected modeled-case private shadow-heap mutation was missing');
        if (mode === 'modeled_success' && (right.result.kind !== 'return' || typeof right.result.value !== 'string')) throw Error('Modeled success branch was not reached');
        if (['bad_prefix', 'bad_final_hash'].includes(mode)) assert.equal(right.result.value, null);
        rows.push({profile: 'modeled_crypto_call_contract', mode, function: 'tryUnlock', seed_base: seedBase,
                   caller_observations_equal: true, instrumentation_observations_equal: true,
                   clean: sanitizedCall(left), target: sanitizedCall(right), diagnostic_proxy: sanitizedCall(observed)});
      }
    }
    const breakers = [];
    {
      const old = makeRealm(source, analysis.runtime, seeds[0], config.commitment);
      const ref = makeRealm(analysis.runtime.materializedCleanSource, null, seeds[0], config.commitment);
      const a = ref.call('sha256Hex', '__realm.exports.sha256Hex');
      const b = old.call('sha256Hex', '__realm.exports.sha256Hex');
      if (stable(a.result) === stable(b.result)) throw Error('Function-source reflection negative did not distinguish the actual functions');
      breakers.push({kind: 'function_source_reflection', outside_observer_contract: true,
                     caller_observations_equal: false, clean: sanitizedCall(a), target: sanitizedCall(b)});
    }
    {
      const old = makeRealm(source, analysis.runtime, seeds[0], config.commitment);
      const ref = makeRealm(analysis.runtime.materializedCleanSource, null, seeds[0], config.commitment);
      const mutate = '({toString(){__coercionTrace.push("mutate-imul");Math.imul=()=>{throw new Error("authored intrinsic failure");};return "authored";}})';
      const firstA = ref.call('sha256Hex', mutate), firstB = old.call('sha256Hex', mutate);
      const a = ref.call('sha256Hex', '"authored-next-call"');
      const b = old.call('sha256Hex', '"authored-next-call"');
      if (a.result.kind !== 'return' || b.result.kind !== 'throw') throw Error('Intrinsic mutation negative did not distinguish the next call');
      breakers.push({kind: 'intrinsic_mutation_across_calls', outside_observer_contract: true,
                     caller_observations_equal: false,
                     first_call_observations_equal: stable(firstA.result) === stable(firstB.result),
                     first_clean: sanitizedCall(firstA), first_target: sanitizedCall(firstB),
                     clean: sanitizedCall(a), target: sanitizedCall(b)});
    }
    tiers.push({tier: target.tier, source_sha256: target.sha256, static: analysis.report,
                guard_evidence: seedEvidence,
                shadow_heap_boundary: heapBoundary,
                noninterference_boundary: noninterferenceBoundary,
                assumption_breakers: breakers,
                actual_crypto_cases: rows.filter(r => r.profile === 'actual_crypto').length,
                modeled_call_cases: rows.filter(r => r.profile === 'modeled_crypto_call_contract').length,
                caller_observations_equal: true, private_heap_effects_equal_to_clean: false,
                rows, rows_sha256: hash(rows),
                assumptions: ['CommonJS module boundary; CLI not invoked', 'Standard intrinsics and intact source corpus',
                  'Private shadow heap excluded from caller-visible state; entry/exit snapshots retained',
                  'Allowlisted node:crypto and Buffer call contract; deterministic process seed'],
                limitations: ['Finite differential checks are not an all-input runtime proof',
                  'Modeled success/failure scenarios are not a valid-key run with actual crypto',
                  'Diagnostic Proxy write ledger is validated against a separate uninstrumented run',
                  'Only diagnostic Proxy rows record writes; zero recorded writes in uninstrumented rows is not zero mutation',
                  'Object coercion fixtures are finite extra observations beyond the primitive-input static contract',
                  'Exception name/message are compared; stack traces and function/source introspection are excluded',
                  'Module-load global properties and timing are outside exported-function observation']});
  }
  return {format: 'fdisbull-bla-function-campaign-1', status: 'verified_finite_function_observations', node: process.version,
          tiers, total_actual_crypto_cases: tiers.reduce((n,t)=>n+t.actual_crypto_cases,0),
          total_modeled_call_cases: tiers.reduce((n,t)=>n+t.modeled_call_cases,0),
          full_state_equivalence: false, whole_program_equivalence: null};
}

module.exports = {run, makeRealm, sanitizedCall, referenceShadowHeapStep, crosscheckShadowHeap, crosscheckFunctionNoninterference};
if (require.main === module) {
  try {
    const input = fs.readFileSync(0, 'utf8');
    if (Buffer.byteLength(input) > 65536) throw Error('Configuration exceeds bound');
    console.log(JSON.stringify(run(JSON.parse(input))));
  } catch (error) {
    console.error('BLA function campaign failed: ' + String(error.message).slice(0, 250));
    process.exitCode = 2;
  }
}
