'use strict';
/** Source-bound private-state noninterference and ignored-step erasure.
 * The heap transition checker supplies totality and a private numeric-write
 * frame. This checker establishes that the frame cannot escape into the
 * selected caller's low state, and that the call's arguments/result add no
 * observable work. It does not equate arbitrary JS observation contexts.
 */
const crypto = require('node:crypto');
const path = require('node:path');
const {proveShadowHeap} = require('./bla_shadow_heap_proof.cjs');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const fail = reason => {throw new Error(reason);};
const identifier = name => typeof name === 'string' && /^[$A-Z_a-z][$\w]*$/.test(name);
const stable = value => {
  if (Array.isArray(value)) return value.map(stable);
  if (!value || typeof value !== 'object') return value;
  const result = Object.create(null);
  for (const key of Object.keys(value).sort()) result[key] = stable(value[key]);
  return result;
};
const digest = value => sha(JSON.stringify(stable(value)));

function proveHeapNoninterference({source,babelRoot,heapName,heapStepName,functionNames,heapProof} = {}) {
  const format = 'fdisbull-heap-noninterference-1';
  try {
    if (typeof source !== 'string' || source.length > 2 * 1024 * 1024 || typeof babelRoot !== 'string'
        || !identifier(heapName) || !identifier(heapStepName) || heapName === heapStepName
        || !functionNames || typeof functionNames !== 'object' || Array.isArray(functionNames)) fail('unsupported_boundary');
    const roles = Object.keys(functionNames);
    if (!roles.length || roles.length > 8 || roles.some(role=>!identifier(role) || !identifier(functionNames[role]))
        || new Set(Object.values(functionNames)).size !== roles.length) fail('ambiguous_selected_functions');
    const parser = require(path.join(babelRoot,'@babel/parser'));
    const traverse = require(path.join(babelRoot,'@babel/traverse')).default;
    const ast = parser.parse(source,{sourceType:'script'});
    let program;
    traverse(ast,{Program(p){program=p;p.stop();}});
    const heap = program.scope.getBinding(heapName), step = program.scope.getBinding(heapStepName);
    if (!heap || heap.scope !== program.scope || !heap.path.isVariableDeclarator()
        || !heap.path.parentPath.parentPath.isProgram() || !heap.path.node.init
        || !step || step.scope !== program.scope || !step.path.isFunctionDeclaration()
        || !step.path.parentPath.isProgram() || heap.constantViolations.length || step.constantViolations.length)
      fail('mutable_or_missing_private_binding');
    const selected = new Map();
    for (const role of roles) {
      const binding = program.scope.getBinding(functionNames[role]);
      if (!binding || binding.scope !== program.scope || !binding.path.isFunctionDeclaration()
          || !binding.path.parentPath.isProgram() || binding.constantViolations.length
          || binding === step || binding === heap) fail('mutable_or_missing_selected_binding');
      selected.set(binding.path.node,role);
    }
    // Dynamic code can introduce unrecorded lexical references. Constructors
    // obtained indirectly through the standard constructor property are also
    // outside this deliberately closed source profile.
    program.traverse({
      ReferencedIdentifier(p) {if (['eval','Function'].includes(p.node.name)) fail('dynamic_code_reference');},
      WithStatement() {fail('dynamic_scope');},
      MemberExpression(p) {
        const n=p.node;
        if ((!n.computed && n.property.type==='Identifier' && n.property.name==='constructor')
            || (n.computed && n.property.type==='StringLiteral' && n.property.value==='constructor')) fail('dynamic_constructor_reference');
      },
    });
    const stepNode = step.path.node;
    const heapReferences = heap.referencePaths.map(reference=>{
      if (reference.getFunctionParent()?.node !== stepNode) fail('private_heap_reference_escapes');
      return [reference.node.start,reference.node.end];
    });
    if (!heapReferences.length) fail('unused_private_heap');
    const actual = proveShadowHeap({functionNode:stepNode,heapInitializerNode:heap.path.node.init,
      heapName,source,babelRoot});
    if (actual.status !== 'proved' || actual.source?.sha256 !== sha(source)
        || actual.source?.ast_identity_verified !== true || actual.invariant?.initialized !== true
        || actual.invariant?.preserved !== true || actual.invariant?.ordinary_disjoint_own_data_graph !== true
        || actual.invariant?.arrays_and_object_schema_unchanged !== true
        || actual.termination?.proved !== true || actual.termination?.normal_numeric_return !== true
        || actual.termination?.unbounded_control !== false || actual.termination?.recursion !== false
        || actual.mutation?.external_effects !== false || actual.mutation?.reference_or_length_writes !== false)
      fail('private_transition_not_total_and_framed');
    if (heapProof !== undefined && digest(heapProof) !== digest(actual)) fail('stale_or_forged_heap_certificate');
    const calls = [], selectedCalls = [];
    for (const reference of step.referencePaths) {
      const call = reference.parentPath, statement = call.parentPath;
      if (!call.isCallExpression() || call.node.optional || call.node.callee !== reference.node
          || !statement?.isExpressionStatement() || statement.node.expression !== call.node)
        fail('private_transition_reference_escapes');
      const owner = reference.getFunctionParent()?.node;
      const role = selected.get(owner);
      const receipt = {source_offsets:[call.node.start,call.node.end],selected:role !== undefined,
        result_discarded:true};
      if (role !== undefined) {
        if (call.node.arguments.length !== 1 || call.node.arguments[0].type !== 'NumericLiteral'
            || !Number.isSafeInteger(call.node.arguments[0].value)) fail('selected_argument_has_unproved_effects');
        receipt.role = role;
        receipt.argument_domain = 'safe_integer_Number';
        receipt.argument_evaluation = 'pure_literal';
        receipt.call_sha256 = sha(source.slice(call.node.start,call.node.end));
        selectedCalls.push(receipt);
      }
      calls.push(receipt);
    }
    if (!selectedCalls.length) fail('no_selected_private_steps');
    const sourceReceipt = {sha256:sha(source),mutator_sha256:actual.source.mutator_sha256,
      mutator_offsets:actual.source.mutator_offsets,
      heap_initializer_sha256:sha(source.slice(heap.path.node.init.start,heap.path.node.init.end)),
      heap_initializer_offsets:[heap.path.node.init.start,heap.path.node.init.end],ast_identity_verified:true};
    const proof = {format,status:'proved',method:'Private numeric write frame, lexical no-escape audit and ignored total-step erasure',
      source:sourceReceipt,heap_certificate_sha256:actual.certificate_sha256,
      relation:{entry:'The two runs have equal low state and independently arbitrary private heaps satisfying the same invariant',
        private_states_need_not_equal:true,low_projection:'All permitted caller state and ordered collaborator observations excluding the private heap',
        exit:'Both private steps terminate normally, preserve their invariants, leave low state unchanged and emit the empty observable trace',
        step_result_relation:'Numeric private results may differ; every selected call discards the result',
        caller_erasure:'Each selected step is a finite silent stutter and may be replaced by skip in the admitted caller context'},
      audit:{heap_binding_lexical:true,heap_reference_count:heapReferences.length,
        source_initial_separation_established:true,private_own_data_ownership_preserved:true,
        heap_references_owned_by_exact_mutator:true,heap_reference_offsets_sha256:digest(heapReferences),
        private_aliases_escape:false,private_values_read_by_selected_callers:false,
        private_transition_binding_immutable:true,all_transition_references_direct_ignored:true,
        module_callsite_count:calls.length,outside_selected_callsite_count:calls.length-selectedCalls.length,
        selected_callsite_count:selectedCalls.length,selected_arguments_pure_safe_integers:true,
        mutator_writes_only_private_numeric_cells:true,observable_mutator_calls:[],
        mutator_language_exceptions:false,termination_sensitive:true},
      selected_calls:selectedCalls,
      obligations:[
        {rule:'initial_separation',result:'proved',basis:'Fresh disjoint literal own-data heap; immutable lexical binding and no reference outside the exact mutator'},
        {rule:'private_frame',result:'proved',basis:'Recomputed source-bound transition proof admits only local scalar expressions, private numeric writes and standard pure Math.imul'},
        {rule:'no_high_to_low_flow',result:'proved',basis:'Private fields are unread by selected callers; no aliases escape; every transition result is discarded'},
        {rule:'normal_termination',result:'proved',basis:'Recomputed invariant/ranking certificate establishes normal completion for every admitted heap and safe-integer delta'},
        {rule:'silent_argument_and_result',result:'proved',basis:'Selected direct calls evaluate one pure safe-integer numeric literal and discard the numeric result'},
        {rule:'two_run_stuttering',result:'proved',basis:'The private frame preserves equal low projections independently for each high heap, enabling silent-step erasure'},
      ],
      scope:'Selected function call sites after CommonJS initialization; other callable closures and module initialization are not erased',
      remaining_assumptions:[
        'Ordinary private writable own-data heaps satisfying the proved invariant, with no external aliases, proxies, getters or concurrent observers',
        'Stable standard Math.imul and ordinary JavaScript object/array semantics; safe-integer numeric step arguments',
        'The observer excludes timing, resource exhaustion, debugger/process introspection, source/name reflection and exception stacks',
        'Only the selected call sites are erased; composition must separately close the remaining function/collaborator call graph',
      ]};
    proof.certificate_sha256 = digest(proof);
    return proof;
  } catch (error) {
    const reason = error instanceof Error && /^[a-z][a-z0-9_]{0,80}$/.test(error.message) ? error.message : 'noninterference_proof_failure';
    return {format,status:'unknown',reason};
  }
}

module.exports = {proveHeapNoninterference};
