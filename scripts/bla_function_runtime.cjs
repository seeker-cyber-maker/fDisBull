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
  const cipherName = identifier(runtime?.cipherName || 'FLAG_CIPHER_HEX');
  const suffix = `\n;return {exports:module.exports, capture:()=>JSON.parse(JSON.stringify(${heap || 'null'})),` +
    `heap:()=>${heap || 'null'}, setHeap:value=>{${heap ? heap + '=value;' : ''}},` +
    'exportState:()=>JSON.parse(JSON.stringify({SCOPE:module.exports.SCOPE,KEY_SHA256:module.exports.KEY_SHA256,' +
    'FLAG_SHA256:module.exports.FLAG_SHA256,LICENSE_RPC:module.exports.LICENSE_RPC})),' +
    `info:()=>({seed:${seed || 'null'},corpusDigest:${corpus ? corpus + '(0)' : 'null'},cipher:${cipherName}})};`;
  const original = source.replace(/^#![^\n]*/, line => ' '.repeat(line.length));
  const wrapperSource = '(function(exports,require,module,__filename,__dirname){\n' + original + suffix + '\n})';
  const executionReceipt = {source_sha256: sha(source), commonjs_wrapper_sha256: sha(wrapperSource),
    observer_suffix_sha256: sha(suffix), hashbang_masked: original !== source,
    function_bodies_rewritten: false, private_heap_proxy: Boolean(instrument && heap)};
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
  events.length = 0;
  if (instrument && heap) {
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
  function call(name, input) {
    hashNumber = 0; events.length = 0; writes.length = 0;
    const before = plain(vm.runInContext('__realm.capture()', context, {timeout: 500}));
    const exportsBefore = plain(vm.runInContext('__realm.exportState()', context, {timeout: 500}));
    context.__input = input;
    context.__coercionTrace = [];
    const result = plain(vm.runInContext(`(()=>{try {const value=__realm.exports[${JSON.stringify(name)}]((${input}));` +
      'return {kind:"return",value,input_effects:__coercionTrace};}' +
      'catch(error){return {kind:"throw",name:error.name,message:error.message,input_effects:__coercionTrace};}})()', context, {timeout: 500}));
    const after = plain(vm.runInContext('__realm.capture()', context, {timeout: 500}));
    const exportsAfter = plain(vm.runInContext('__realm.exportState()', context, {timeout: 500}));
    return {result, events: [...events], before, after, exportsBefore, exportsAfter,
            writes: [...writes], changes: heapChanges(before, after)};
  }
  return {call, info, initialization, executionReceipt};
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
    recorded_writes_sha256: hash(record.writes)};
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

module.exports = {run, makeRealm, sanitizedCall};
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
