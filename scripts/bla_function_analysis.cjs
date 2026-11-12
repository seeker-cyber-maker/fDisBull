"use strict";
/** Source-bound BLA function reduction. No target is evaluated by this module. */
const crypto = require('node:crypto');
const path = require('node:path');
const {proveShadowHeap} = require('./bla_shadow_heap_proof.cjs');
const {proveHeapNoninterference} = require('./bla_heap_noninterference.cjs');
const {composeFunctionEquivalence} = require('./bla_function_equivalence.cjs');
const {proveSeedInvariant} = require('./bla_seed_invariant.cjs');

const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const UNKNOWN = Symbol('unknown');

function cleanNode(value) {
  if (Array.isArray(value)) return value.map(cleanNode);
  if (!value || typeof value !== 'object') return value;
  const result = {};
  for (const key of Object.keys(value).sort()) {
    if (['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens'].includes(key)) continue;
    if (value[key] !== undefined && value[key] !== null) result[key] = cleanNode(value[key]);
  }
  return result;
}
const canonical = node => JSON.stringify(cleanNode(node));

function analyze(templateSource, targetSource, {babelRoot} = {}) {
  if (typeof templateSource !== 'string' || typeof targetSource !== 'string'
      || templateSource.length > 65536 || targetSource.length > 2 * 1024 * 1024 || !babelRoot) {
    throw new Error('Bounded sources and an existing Babel module root are required');
  }
  const parser = require(path.join(babelRoot, '@babel/parser'));
  const traverse = require(path.join(babelRoot, '@babel/traverse')).default;
  const generate = require(path.join(babelRoot, '@babel/generator')).default;
  const parse = text => parser.parse(text, {sourceType: 'script'});
  const template = parse(templateSource), target = parse(targetSource);
  for (const ast of [template,target]) traverse(ast, {Identifier(p) {
    if (/^__v\d+$/.test(p.node.name)) throw new Error('Reserved alpha-normalization namespace appears in source');
  }});
  let program;
  traverse(target, {Program(p) { program = p; p.stop(); }});
  const bindings = program.scope.bindings;
  const heapName = Object.keys(bindings).find(name => /^shadowHeap/.test(name));
  const heapStepName = Object.keys(bindings).find(name => /^stepShadowHeap/.test(name));
  const seedName = Object.keys(bindings).find(name => /^runtimeSeed/.test(name));
  const corpusName = Object.keys(bindings).find(name => /^_deriveContainmentCorpusDigest_/.test(name));
  if (!heapName || !heapStepName || !seedName || !corpusName) throw new Error('Required original BLA bindings absent');
  let expectedCorpusDigest;
  bindings[seedName].path.traverse({BinaryExpression(p) {
    if (p.node.operator === '===' && p.node.left.type === 'CallExpression'
        && p.node.left.callee.name === corpusName && p.node.right.type === 'NumericLiteral') expectedCorpusDigest = p.node.right.value;
  }});
  if (!Number.isInteger(expectedCorpusDigest) || expectedCorpusDigest < 0 || expectedCorpusDigest > 0xffffffff) throw new Error('Expected corpus commitment missing');
  if (bindings[seedName].constantViolations.length || ['Math','String','Buffer'].some(name => bindings[name])) throw new Error('Mutable seed or shadowed intrinsic binding');
  const seedInvariantProof = proveSeedInvariant({source:targetSource,babelRoot,seedName});
  program.traverse({ReferencedIdentifier(p) {
    if ((p.node.name === seedName && p.scope.getBinding(seedName) !== bindings[seedName])
        || (p.node.name === 'Math' && p.scope.getBinding('Math'))) throw new Error('Opaque predicate binding identity is ambiguous');
  }});
  const exported = {};
  for (const node of target.program.body) {
    const expr = node.type === 'ExpressionStatement' && node.expression;
    if (expr && expr.type === 'AssignmentExpression' && expr.left.type === 'MemberExpression'
        && !expr.left.computed && expr.left.object.name === 'module' && expr.left.property.name === 'exports') {
      if (expr.right.type !== 'ObjectExpression') throw new Error('Dynamic export surface unsupported');
      for (const property of expr.right.properties) {
        if (property.type !== 'ObjectProperty' || property.computed || property.value.type !== 'Identifier') throw new Error('Dynamic export binding unsupported');
        exported[property.key.name || property.key.value] = property.value.name;
      }
    }
  }
  if (!exported.tryUnlock || !exported.sha256Hex) throw new Error('Expected exported function boundary missing');
  function declaration(name) {
    const binding = bindings[name];
    if (!binding || binding.path.node.type !== 'FunctionDeclaration' || binding.constantViolations.length) throw new Error('Mutable or missing function binding');
    return binding.path;
  }
  function directInitializerCall(fn) {
    for (const statement of fn.node.body.body) if (statement.type === 'VariableDeclaration') {
      for (const entry of statement.declarations) if (entry.init && entry.init.type === 'CallExpression'
          && entry.init.callee.type === 'Identifier') return entry.init.callee.name;
    }
    throw new Error('Expected direct helper call absent');
  }
  const functionNames = {tryUnlock: exported.tryUnlock, sha256Hex: exported.sha256Hex};
  functionNames.decodeFlagCipher = directInitializerCall(declaration(functionNames.tryUnlock));
  functionNames.deriveFlagMask = directInitializerCall(declaration(functionNames.decodeFlagCipher));
  const originalFunctionOffsets = Object.fromEntries(Object.entries(functionNames).map(([role,name]) => [role,
    [bindings[name].path.node.start,bindings[name].path.node.end]]));
  let cipherName, cryptoBindingName;
  declaration(functionNames.decodeFlagCipher).traverse({CallExpression(p) {
    const callee = p.node.callee;
    if (callee.type === 'MemberExpression' && callee.object.name === 'Buffer' && callee.property.name === 'from'
        && p.node.arguments[0] && p.node.arguments[0].type === 'Identifier') cipherName = p.node.arguments[0].name;
  }});
  for (const node of target.program.body) if (node.type === 'VariableDeclaration') for (const entry of node.declarations) {
    if (entry.id.type === 'ObjectPattern' && entry.init && entry.init.type === 'CallExpression'
        && entry.init.callee.name === 'require' && entry.init.arguments[0]?.value === 'node:crypto') {
      const property = entry.id.properties.find(p => p.type === 'ObjectProperty' && p.key.name === 'createHash');
      if (property) cryptoBindingName = property.value.name;
    }
  }
  if (!cipherName || !cryptoBindingName) throw new Error('Crypto or ciphertext source binding absent');
  const ledger = [], opaqueProofs = [];
  function literal(node) {
    if (node && ['StringLiteral','NumericLiteral','BooleanLiteral','NullLiteral'].includes(node.type)) return node.type === 'NullLiteral' ? null : node.value;
    return UNKNOWN;
  }
  function seedBinary(node, operator) {
    return node && node.type === 'BinaryExpression' && node.operator === operator
      && node.left.type === 'Identifier' && node.left.name === seedName
      && node.right.type === 'NumericLiteral' && Number.isInteger(node.right.value)
      && node.right.value >= 0 && node.right.value <= 0xffffffff ? node.right.value : null;
  }
  function opaque(node) {
    if (!node || node.type !== 'BinaryExpression' || !['===','!=='].includes(node.operator)
        || node.right.type !== 'NumericLiteral' || ![0,1].includes(node.right.value)) return UNKNOWN;
    const mask = node.left;
    if (mask.type !== 'BinaryExpression' || mask.operator !== '&' || mask.right.type !== 'NumericLiteral') return UNKNOWN;
    const call = mask.left;
    if (call.type !== 'CallExpression' || call.arguments.length !== 2 || call.callee.type !== 'MemberExpression'
        || call.callee.computed || call.callee.object.name !== 'Math' || call.callee.property.name !== 'imul') return UNKNOWN;
    let kind, constant, residues, output;
    const square = seedBinary(call.arguments[0], '^');
    const consecutive = seedBinary(call.arguments[0], '|');
    if (mask.right.value === 7 && square !== null && square === seedBinary(call.arguments[1], '^')) {
      kind = 'square_low_three_bits'; constant = square; residues = [1,5];
      const values = residues.map(seed => Math.imul(seed ^ constant, seed ^ constant) & 7);
      if (values[0] !== values[1]) throw new Error('Predicate does not reduce under seed invariant');
      output = values[0];
    } else if (mask.right.value === 1 && consecutive !== null
        && call.arguments[1].type === 'BinaryExpression' && call.arguments[1].operator === '+'
        && call.arguments[1].right.type === 'NumericLiteral' && call.arguments[1].right.value === 1
        && canonical(call.arguments[1].left) === canonical(call.arguments[0])) {
      kind = 'consecutive_product_low_bit'; constant = consecutive; residues = [0,1]; output = 0;
    } else return UNKNOWN;
    const value = node.operator === '===' ? output === node.right.value : output !== node.right.value;
    opaqueProofs.push({kind, constant, mask: mask.right.value, operator: node.operator, comparison: node.right.value,
      reduced: value, source_offsets: [node.start,node.end], source_region_sha256: hash(targetSource.slice(node.start,node.end)),
      proof: 'Exhaustive relevant low-bit residues in the u32 modular ring', residues,
      assumptions: kind === 'square_low_three_bits' ? ['seed & 3 == 1','standard Math.imul'] : ['standard Math.imul']});
    return value;
  }
  function evaluate(node) {
    const value = literal(node);
    if (value !== UNKNOWN) return value;
    if (node?.type === 'BinaryExpression' && node.operator === '+') {
      const left = evaluate(node.left), right = evaluate(node.right);
      if (left !== UNKNOWN && right !== UNKNOWN && (typeof left === 'string' || typeof right === 'string')) return left + right;
    }
    return opaque(node);
  }
  const literalNode = value => ({type: typeof value === 'boolean' ? 'BooleanLiteral' : typeof value === 'string' ? 'StringLiteral' : 'NumericLiteral', value});
  function reduce(ast, source) {
    traverse(ast, {
      BinaryExpression: {exit(p) { const value = evaluate(p.node); if (value !== UNKNOWN) p.replaceWith(literalNode(value)); }},
      ConditionalExpression: {exit(p) {
        const value = literal(p.node.test);
        if (typeof value === 'boolean') {ledger.push({kind:'pure_conditional',source_offsets:[p.node.start,p.node.end]});p.replaceWith(value ? p.node.consequent : p.node.alternate);}
      }},
      IfStatement: {exit(p) {
        const value = literal(p.node.test);
        if (typeof value !== 'boolean') return;
        let declarations = false;
        p.traverse({VariableDeclaration() {declarations = true;}, FunctionDeclaration() {declarations = true;}, ClassDeclaration() {declarations = true;}});
        if (declarations) throw new Error('Guard reduction would alter declaration/hoisting scope');
        ledger.push({kind:'pure_guard',source_offsets:[p.node.start,p.node.end],taken:value});
        const selected = value ? p.node.consequent : p.node.alternate;
        if (!selected) p.remove(); else if (selected.type === 'BlockStatement') p.replaceWithMultiple(selected.body); else p.replaceWith(selected);
      }},
    });
  }
  const heapBinding = bindings[heapName], stepBinding = bindings[heapStepName];
  const stepOriginal = stepBinding.path.node;
  const stepSourceOffsets = [stepOriginal.start,stepOriginal.end];
  const stepSourceHash = hash(targetSource.slice(...stepSourceOffsets));
  let mutatorPure = true;
  const mutatorProperties = new Set(['tick','rollingMask','length','slots','cursor','words','epoch','hmacTag',
    'splitShareA','splitShareB','diffEnvelope','imul']);
  function localWrite(p,node) {
    if (node.type === 'VariableDeclaration') return;
    if (node.type !== 'Identifier' && node.type !== 'MemberExpression') {mutatorPure = false;return;}
    let root = node;
    while (root.type === 'MemberExpression') root = root.object;
    if (root.type !== 'Identifier') {mutatorPure = false;return;}
    const binding = p.scope.getBinding(root.name);
    if (binding !== heapBinding && (!binding || !stepBinding.path.isAncestor(binding.path))) mutatorPure = false;
  }
  stepBinding.path.traverse({
    ReferencedIdentifier(p) {
      const binding = p.scope.getBinding(p.node.name);
      if (p.node.name === heapName && binding === heapBinding) return;
      if (p.node.name === 'Math' && !binding) {
        const member = p.parentPath, call = member.parentPath;
        if (member.isMemberExpression() && !member.node.computed && member.node.object === p.node
            && member.node.property.name === 'imul' && call?.isCallExpression() && call.node.callee === member.node) return;
        mutatorPure = false;
        return;
      }
      if (!binding || !stepBinding.path.isAncestor(binding.path)) mutatorPure = false;
    },
    CallExpression(p) {
      const callee = p.node.callee;
      if (callee.type !== 'MemberExpression' || callee.computed || callee.object.name !== 'Math'
          || callee.property.name !== 'imul' || p.node.arguments.length !== 2) mutatorPure = false;
    },
    MemberExpression(p) {
      const property = p.node.property;
      if ((!p.node.computed && !mutatorProperties.has(property.name) && !/^state_diff_frontier_\d+$/.test(property.name))
          || (p.node.computed && property.type !== 'Identifier' && property.type !== 'NumericLiteral')) mutatorPure = false;
    },
    AssignmentExpression(p) {localWrite(p,p.node.left);},
    UpdateExpression(p) {localWrite(p,p.node.argument);},
    ForInStatement(p) {localWrite(p,p.node.left);},
    ForOfStatement(p) {localWrite(p,p.node.left);},
    UnaryExpression(p) {if (p.node.operator === 'delete') mutatorPure = false;},
    StringLiteral() {mutatorPure = false;}, TemplateLiteral() {mutatorPure = false;},
    ThrowStatement() {mutatorPure = false;}, NewExpression() {mutatorPure = false;},
    Function(p) {if (p.node !== stepOriginal) mutatorPure = false;},
  });
  function data(node) {
    if (node.type === 'NumericLiteral' || node.type === 'StringLiteral') return node.value;
    if (node.type === 'ArrayExpression') return node.elements.map(item => {if (!item) throw new Error('Sparse private heap');return data(item);});
    if (node.type === 'ObjectExpression') {
      const out = Object.create(null);
      for (const property of node.properties) {
        if (property.type !== 'ObjectProperty' || property.computed || property.method) throw new Error('Private heap has accessors/spreads');
        const key = property.key.name || property.key.value;
        if (Object.hasOwn(out,key) || key === '__proto__') throw new Error('Ambiguous private-heap property');
        out[key] = data(property.value);
      }
      return out;
    }
    throw new Error('Private heap initialization is not literal data');
  }
  const heap = data(heapBinding.path.node.init);
  // Archived slot `kind` labels are inert metadata: the numeric mutator may not read them.
  const numericData = (value,key) => typeof value === 'number' || (key === 'kind' && typeof value === 'string')
    || (value && typeof value === 'object' && Object.entries(value).every(([childKey,child]) => numericData(child,childKey)));
  const uint31 = value => Number.isInteger(value) && value >= 0 && value <= 0x7fffffff;
  const heapShape = numericData(heap) && Array.isArray(heap.slots) && heap.slots.length >= 8
    && Number.isInteger(heap.cursor) && heap.cursor >= 0 && heap.cursor < heap.slots.length
    && uint31(heap.tick) && uint31(heap.rollingMask)
    && Array.isArray(heap.splitShareA) && heap.splitShareA.length > 0
    && Array.isArray(heap.splitShareB) && heap.splitShareA.length === heap.splitShareB.length
    && heap.splitShareA.every(uint31) && heap.splitShareB.every(uint31)
    && heap.slots.every(slot => slot && Array.isArray(slot.words) && slot.words.length === 4
      && slot.words.every(uint31) && uint31(slot.epoch) && uint31(slot.hmacTag))
    && heap.diffEnvelope && Object.values(heap.diffEnvelope).every(uint31);
  const heapReferences = heapBinding.referencePaths.map(ref => ({source_offsets:[ref.node.start,ref.node.end],
    owner:ref.getFunctionParent()?.node.id?.name}));
  const stepCalls = stepBinding.referencePaths.map(ref => ({source_offsets:[ref.parentPath.node.start,ref.parentPath.node.end],
    owner:ref.getFunctionParent()?.node.id?.name, direct:ref.parentPath.isCallExpression() && ref.parentPath.node.callee === ref.node,
    ignored:ref.parentPath.parentPath?.isExpressionStatement() || false}));
  let dynamic = false;
  program.traverse({CallExpression(p) {if (p.node.callee.type === 'Identifier' && ['eval','Function'].includes(p.node.callee.name)) dynamic = true;},
    NewExpression(p) {if (p.node.callee.name === 'Function' || p.node.callee.name === 'Proxy') dynamic = true;},
    WithStatement() {dynamic = true;}});
  const privateHeap = heapBinding.path.node.init?.type === 'ObjectExpression'
    && !heapBinding.constantViolations.length && !stepBinding.constantViolations.length
    && heapBinding.referencePaths.every(ref => ref.getFunctionParent()?.node === stepOriginal)
    && stepCalls.every(call => call.direct && call.ignored) && !dynamic && mutatorPure && heapShape;
  if (!privateHeap) throw new Error('Shadow-heap privacy/call discipline audit failed');
  const shadowHeapProof = proveShadowHeap({functionNode:stepOriginal,
    heapInitializerNode:heapBinding.path.node.init,heapName,source:targetSource,babelRoot});
  const heapNoninterference = proveHeapNoninterference({source:targetSource,babelRoot,
    heapName,heapStepName,functionNames,heapProof:shadowHeapProof});
  const globalMap = {...Object.fromEntries(Object.entries(functionNames).map(([role,name]) => [name,role])),
    [cryptoBindingName]:'createHash', [cipherName]:'FLAG_CIPHER_HEX'};
  for (const role of ['SCOPE','KEY_SHA256','FLAG_SHA256','LICENSE_RPC']) {
    if (!exported[role]) throw new Error('Required materialized constant missing');
    globalMap[exported[role]] = role;
  }
  for (const name of Object.keys(globalMap)) if (!bindings[name] || bindings[name].constantViolations.length) throw new Error('Mutable public function/constant dependency');
  const reserved = new Set([...Object.values(globalMap),seedName,heapName,heapStepName,'Math','String','Buffer']);
  for (const [name,role] of Object.entries(globalMap)) if (bindings[role] && bindings[role] !== bindings[name]) throw new Error('Canonical global binding collision');
  program.traverse({Scopable(p) {
    if (p.scope === program.scope) return;
    if (Object.keys(p.scope.bindings).some(name => reserved.has(name))) throw new Error('Reserved intrinsic or semantic binding is locally shadowed');
  }});
  // Materialize only reviewed placeholders; preserve exact target values without publishing them.
  reduce(target, targetSource);
  program.scope.crawl();
  const constants = {};
  for (const role of ['SCOPE','KEY_SHA256','FLAG_SHA256','FLAG_CIPHER_HEX']) {
    const targetName = Object.keys(globalMap).find(name => globalMap[name] === role);
    const value = evaluate(program.scope.bindings[targetName]?.path.node.init);
    if (typeof value !== 'string') throw new Error('Materialized constant is not a reduced string literal');
    constants['%%' + role + '%%'] = value;
  }
  traverse(template, {StringLiteral(p) {if (Object.hasOwn(constants,p.node.value)) p.node.value = constants[p.node.value];}});
  let templateProgram;
  traverse(template,{Program(p) {templateProgram = p;p.stop();}});
  const constantResults = ['SCOPE','KEY_SHA256','FLAG_SHA256','FLAG_CIPHER_HEX','LICENSE_RPC'].map(role => {
    const name = Object.keys(globalMap).find(name => globalMap[name] === role);
    const a = canonical(templateProgram.scope.bindings[role].path.node.init);
    const b = canonical(program.scope.bindings[name].path.node.init);
    return {name:role,equal:a === b,reference_ast_sha256:hash(a),target_ast_sha256:hash(b)};
  });
  const materializedCleanSource = generate(template, {comments:false}).code;
  const selectedFunctions = new Set(Object.values(functionNames).map(name => program.scope.getBinding(name).path.node));
  traverse(target, {CallExpression(p) {
    if (p.node.callee.type === 'Identifier' && p.node.callee.name === heapStepName
        && p.scope.getBinding(heapStepName) === program.scope.getBinding(heapStepName)
        && p.parentPath.isExpressionStatement() && selectedFunctions.has(p.getFunctionParent()?.node)) {
      if (p.node.arguments.length !== 1 || p.node.arguments.some(a => a.type !== 'NumericLiteral' || !Number.isSafeInteger(a.value))) throw new Error('Private heap step argument has unmodeled effects or exceeds the safe-integer proof domain');
      ledger.push({kind:'private_heap_step',source_offsets:[p.node.start,p.node.end],argument_count:p.node.arguments.length});
      p.parentPath.remove();
    }
  }});
  program.scope.crawl();
  for (const [original, role] of Object.entries(globalMap)) if (original !== role) program.scope.rename(original, role);
  function normalizeLocals(ast) {
    traverse(ast, {FunctionDeclaration(p) {
      if (!Object.keys(functionNames).includes(p.node.id.name)) return;
      p.scope.crawl();
      const owned = new Set(Object.values(p.scope.bindings));
      p.traverse({Scopable(q) {for (const binding of Object.values(q.scope.bindings)) owned.add(binding);}});
      const local = [...owned].filter(binding => !Object.values(globalMap).includes(binding.identifier.name))
        .sort((a,b) => a.identifier.start - b.identifier.start);
      local.forEach((binding,index) => binding.scope.rename(binding.identifier.name, '__v' + index));
    }});
  }
  normalizeLocals(template); normalizeLocals(target);
  const functionResults = Object.keys(functionNames).map(role => {
    const clean = template.program.body.find(n => n.type === 'FunctionDeclaration' && n.id.name === role);
    const hardened = target.program.body.find(n => n.type === 'FunctionDeclaration' && n.id.name === role);
    const a = canonical(clean), b = canonical(hardened);
    return {name:role,equal:a===b,clean_ast_sha256:hash(a),hardened_ast_sha256:hash(b),
      target_source_offsets:originalFunctionOffsets[role]};
  });
  const matched = functionResults.every(fn => fn.equal) && constantResults.every(value => value.equal);
  const wholeFunctionEquivalence = composeFunctionEquivalence({templateSource,targetSource,babelRoot,
    functionNames,seedName,heapName,heapStepName,cryptoBindingName,cipherName,globalMap,
    guardProofs:opaqueProofs,contractionLedger:ledger,noninterferenceProof:heapNoninterference,heapProof:shadowHeapProof,seedProof:seedInvariantProof});
  return {report:{format:'fdisbull-bla-function-static-1',status:matched?'structural_correspondence_under_assumptions':'different',
    sources:{template_sha256:hash(templateSource),target_sha256:hash(targetSource)},function_results:functionResults,
    constant_results:constantResults,
    guard_reductions:opaqueProofs,contraction_ledger:ledger,
    mutation_summary:{private_heap:true,heap_references:heapReferences,step_calls:stepCalls,
      mutator_source_offsets:stepSourceOffsets,mutator_source_sha256:stepSourceHash,
      mutator_external_calls:['standard Math.imul'],literal_shape_checked:heapShape,
      initialization:{slots:heap.slots.length,split_share_length:heap.splitShareA.length},
      proof:shadowHeapProof,noninterference:heapNoninterference,
      totality_assumption:shadowHeapProof.status === 'proved' ? null :
        'Source-pinned mutator preserves the ordinary numeric heap shape; no getters/proxies/prototype mutation or concurrent observer',
      discharged_obligations:shadowHeapProof.status === 'proved' ? ['shadow_heap_shape_preservation','shadow_heap_termination'] : [],
      full_state_equivalence:false,observer_relation:'Private heap is retained and may differ; no aliases or permitted observers.'},
    assumptions:[...(seedInvariantProof.status === 'proved' ? [] : ['seed & 3 == 1 (intact corpus)']),
      'standard unmodified intrinsics/prototypes',
      shadowHeapProof.status === 'proved' ? 'ordinary writable private data objects; no proxies, getters or external aliases' :
        'normal initialized private heap with no proxies, getters or external aliases','no timing/resource observer',
      'primitive sha256Hex inputs; controlled synchronous crypto provider','matching materialized constants'],
    whole_function_equivalence:wholeFunctionEquivalence,
    seed_invariant_proof:seedInvariantProof,
    scope:'Complete selected function call closure; composed equivalence is a separate certificate under its observer/call contract; no whole-module equivalence'},
    runtime:{materializedCleanSource,seedName,heapName,corpusName,expectedCorpusDigest,cipherName,heapStepName,cryptoBindingName,shadowHeapProof,
      functionNames,heapNoninterference,wholeFunctionEquivalence,seedInvariantProof,staticQualified:matched}};
}

module.exports = {analyze};
