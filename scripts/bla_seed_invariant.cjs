'use strict';
/** Source-bound evaluation of the admitted literal-corpus digest and seed.
 * Target code is parsed and checked, never evaluated. Corpus payloads are data;
 * certificates retain lengths, offsets and hashes instead of their contents.
 */
const crypto=require('node:crypto'),path=require('node:path');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const fail=reason=>{throw Error(reason);};
const META=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens','errors']);
function clean(value){
  if(typeof value==='bigint')return {bigint_decimal:value.toString()};
  if(Array.isArray(value))return value.map(clean);
  if(!value||typeof value!=='object')return value;
  const out={};for(const k of Object.keys(value).sort())if(!META.has(k)&&value[k]!=null)out[k]=clean(value[k]);return out;
}
const canonical=value=>JSON.stringify(clean(value));
const NAME=/^[$A-Z_a-z][$\w]*$/;
const MASK=0x7fffc,INITIAL=0x26b5c67b,MULTIPLIER=0x85ebca6b;

// This is a semantic profile with canonical binding identities, not archived
// source text or a source-hash allowlist. Every statement is compared.
const DIGEST_PROFILE=`function __seedproof_digest(__seedproof_local0=0){
 if(!Array.isArray(__seedproof_corpus)||__seedproof_corpus.length<4)return 0;
 let __seedproof_local1=((__seedproof_local0|0)^${INITIAL})>>>0;
 for(let __seedproof_local2=0;__seedproof_local2<__seedproof_corpus.length;__seedproof_local2++){
  const __seedproof_local3=__seedproof_corpus[__seedproof_local2];
  if(!__seedproof_local3||typeof __seedproof_local3.coupledAnchorSymbol!=="string"||typeof __seedproof_local3.triggerPayload!=="string")return 0;
  const __seedproof_local4=__seedproof_local3.coupledAnchorSymbol+"::"+__seedproof_local3.triggerPayload;
  for(let __seedproof_local5=0;__seedproof_local5<__seedproof_local4.length;__seedproof_local5++){
   __seedproof_local1=Math.imul(__seedproof_local1^__seedproof_local4.charCodeAt(__seedproof_local5),${MULTIPLIER})>>>0;
   __seedproof_local1=(__seedproof_local1<<13|__seedproof_local1>>>19)>>>0;
  }
 }
 return __seedproof_local1>>>0;
}`;

/** Independent modular arithmetic for the exact admitted UTF-16 code units. */
function literalCorpusDigest(entries){
  let accumulator=BigInt(INITIAL),units=0;
  for(const entry of entries){
    const text=entry.coupledAnchorSymbol+'::'+entry.triggerPayload;
    units+=text.length;if(units>1024*1024)fail('corpus_iteration_budget');
    for(let j=0;j<text.length;j++){
      accumulator=BigInt.asUintN(32,(accumulator^BigInt(text.charCodeAt(j)))*BigInt(MULTIPLIER));
      accumulator=BigInt.asUintN(32,(accumulator<<13n)|(accumulator>>19n));
    }
  }
  return {value:Number(accumulator),utf16_units:units};
}

function proveSeedInvariant({source,babelRoot,seedName,corpusName}={}){
  const format='fdisbull-seed-invariant-1';
  try{
    if(typeof source!=='string'||source.length>2*1024*1024||typeof babelRoot!=='string'
       ||typeof seedName!=='string'||!NAME.test(seedName)
       ||(corpusName!==undefined&&(typeof corpusName!=='string'||!NAME.test(corpusName))))fail('unsupported_seed_boundary');
    const parser=require(path.join(babelRoot,'@babel/parser'));
    const traverse=require(path.join(babelRoot,'@babel/traverse')).default;
    const ast=parser.parse(source,{sourceType:'script'});let program;
    traverse(ast,{Program(p){program=p;p.stop();}});
    for(const n of ['Math','Array','Number','Date','process'])if(program.scope.getBinding(n))fail('shadowed_seed_intrinsic');
    program.traverse({Identifier(p){if(p.node.name.startsWith('__seedproof_'))fail('canonical_binding_collision');}});
    const seed=program.scope.getBinding(seedName);
    if(!seed||!seed.path.isVariableDeclarator()||seed.scope!==program.scope
       ||seed.path.parent.kind!=='const'||seed.constantViolations.length)fail('mutable_or_missing_seed');
    const init=seed.path.node.init;
    if(init?.type!=='BinaryExpression'||init.operator!=='|'||init.right?.type!=='ConditionalExpression')fail('seed_initializer_profile');
    const test=init.right.test;
    if(test?.type!=='LogicalExpression'||test.operator!=='&&'||test.right?.type!=='BinaryExpression'
       ||test.right.operator!=='==='||test.right.left?.type!=='CallExpression'||test.right.left.callee.type!=='Identifier'
       ||test.right.right.type!=='NumericLiteral'||!Number.isInteger(test.right.right.value)
       ||test.right.right.value<0||test.right.right.value>0xffffffff)fail('seed_commitment_profile');
    const digestName=test.right.left.callee.name,expected=test.right.right.value;
    const digest=program.scope.getBinding(digestName);
    if(!digest||!digest.path.isFunctionDeclaration()||digest.scope!==program.scope||digest.constantViolations.length
       ||!digest.path.parentPath.isProgram()||digestName===seedName)fail('mutable_or_missing_digest');
    const digestNode=digest.path.node;
    if(digestNode.async||digestNode.generator||digestNode.params.length!==1
       ||digestNode.params[0].type!=='AssignmentPattern'||digestNode.params[0].left.type!=='Identifier'
       ||digestNode.params[0].right.type!=='NumericLiteral'||digestNode.params[0].right.value!==0)fail('digest_parameter_profile');
    const corpusCandidates=[];
    digest.path.traverse({CallExpression(p){
      if(p.node.callee.type==='MemberExpression'&&!p.node.callee.computed&&p.node.callee.object.name==='Array'
         &&p.node.callee.property.name==='isArray'&&p.node.arguments.length===1&&p.node.arguments[0].type==='Identifier')
        corpusCandidates.push(p.node.arguments[0].name);
    }});
    if(corpusCandidates.length!==1||(corpusName!==undefined&&corpusName!==corpusCandidates[0]))fail('corpus_binding_profile');
    const arrayName=corpusCandidates[0],corpus=program.scope.getBinding(arrayName);
    if(!corpus||corpus.scope!==program.scope||!corpus.path.isVariableDeclarator()
       ||corpus.path.parent.kind!=='const'||corpus.constantViolations.length
       ||!corpus.path.parentPath.parentPath.isProgram()||corpus.path.node.init?.type!=='ArrayExpression')fail('mutable_or_missing_literal_corpus');
    if(program.node.body.indexOf(seed.path.parentPath.node)!==2
       ||program.node.body[0]!==corpus.path.parentPath.node||corpus.path.parent.declarations.length!==1
       ||program.node.body[1]!==digestNode||seed.path.parent.declarations.length!==1)fail('seed_initialization_prefix');
    if(corpus.referencePaths.length!==4||corpus.referencePaths.some(p=>p.getFunctionParent()?.node!==digestNode))fail('corpus_reference_escape');
    digest.path.traverse({ReferencedIdentifier(p){
      if(['Math','Array'].includes(p.node.name)&&p.scope.getBinding(p.node.name))fail('digest_intrinsic_binding');
      if(p.node.name===arrayName&&p.scope.getBinding(arrayName)!==corpus)fail('digest_corpus_binding');
    }});
    const entries=[];
    const arrayNode=corpus.path.node.init;
    if(arrayNode.elements.length<4||arrayNode.elements.length>1024)fail('corpus_extent');
    for(const node of arrayNode.elements){
      if(node?.type!=='ObjectExpression')fail('corpus_entry_profile');
      const entry=Object.create(null);
      for(const p of node.properties){
        const key=p.key?.type==='Identifier'?p.key.name:p.key?.type==='StringLiteral'?p.key.value:null;
        if(p.type!=='ObjectProperty'||p.computed||p.method||p.shorthand||typeof key!=='string'
           ||['__proto__','prototype','constructor'].includes(key)||Object.hasOwn(entry,key)||p.value.type!=='StringLiteral')fail('corpus_own_string_data');
        entry[key]=p.value.value;
      }
      if(typeof entry.coupledAnchorSymbol!=='string'||typeof entry.triggerPayload!=='string')fail('corpus_required_fields');
      entries.push(entry);
    }
    const evaluated=literalCorpusDigest(entries);
    if(evaluated.value!==expected)fail('intact_corpus_commitment_mismatch');
    const receipts={sha256:sha(source),seed_offsets:[init.start,init.end],seed_initializer_sha256:sha(source.slice(init.start,init.end)),
      corpus_offsets:[arrayNode.start,arrayNode.end],corpus_sha256:sha(source.slice(arrayNode.start,arrayNode.end)),
      digest_offsets:[digestNode.start,digestNode.end],digest_function_sha256:sha(source.slice(digestNode.start,digestNode.end)),ast_identity_verified:true};
    // Global and local renaming is binding-aware. Original source identity is
    // retained above; the normalized AST is compared to the complete profile.
    const locals=new Set(Object.values(digest.path.scope.bindings));
    digest.path.traverse({Scopable(p){for(const b of Object.values(p.scope.bindings))locals.add(b);}});
    const owned=[...locals].sort((a,b)=>a.identifier.start-b.identifier.start);
    if(owned.length!==6)fail('digest_local_binding_profile');
    program.scope.rename(arrayName,'__seedproof_corpus');
    program.scope.rename(digestName,'__seedproof_digest');
    for(let i=0;i<owned.length;i++)owned[i].scope.rename(owned[i].identifier.name,'__seedproof_local'+i);
    const expectedDigest=parser.parse(DIGEST_PROFILE.replace('.length<4','.length<'+entries.length),{sourceType:'script'}).program.body[0];
    if(canonical(digestNode)!==canonical(expectedDigest))fail('digest_statement_profile');
    const initializerProfile=parser.parseExpression(`(typeof process!=="undefined"&&typeof process?.hrtime?.bigint==="function"?
      Number(process.hrtime.bigint()&0x7fffcn):typeof Date!=="undefined"?Date.now()&${MASK}:4)&${MASK}|
      (typeof __seedproof_digest==="function"&&__seedproof_digest(0)===${expected}?1:0)`);
    if(canonical(init)!==canonical(initializerProfile))fail('seed_clock_profile');
    const proof={format,status:'proved',method:'Complete source-profile checking, bounded literal UTF-16 interpretation and universal masked-clock low-bit algebra',
      source:receipts,corpus:{entries:entries.length,utf16_units:evaluated.utf16_units,ordinary_own_string_data:true,no_escaping_references:true,
        initialized_before_seed:true,no_intervening_effectful_statements:true},
      digest:{input:0,expected_value:expected,evaluated_value:evaluated.value,matches:true,arithmetic:'Independent BigInt u32 multiply and rotate, over exact literal UTF-16 code units',
        initial_u32:INITIAL,multiplier_u32:MULTIPLIER,rotation:13,outer_iterations:entries.length,inner_iterations:evaluated.utf16_units,
        termination:'Outer rank corpus.length-i and inner rank text.length-j; literal immutable finite bounds; exact counters'},
      seed:{immutable:true,low_two_bits:1,intact_corpus_condition_discharged:true,clock_mask:MASK,clock_mask_low_two_bits:MASK&3,
        algebra:'(ToInt32(clock)&mask)&3 = 0; proved literal-corpus predicate selects 1, so ((base&mask)|1)&3 = 1',
        clock_branches:[{branch:'process.hrtime.bigint',domain:'Any BigInt returned by the ordinary synchronous clock',
          masking:'BigInt & 0x7fffc then exact Number conversion',base_range:[0,MASK]},
          {branch:'Date.now',domain:'Any Number returned by the ordinary synchronous clock',masking:'ToInt32 followed by & 0x7fffc',base_range:[0,MASK]},
          {branch:'fallback',domain:'Clock interfaces absent',base_value:4}],
        domain:'Every normally initialized admitted clock branch, including negative/wrapped/NaN/infinite Number clock values'},
      obligations:[{rule:'literal_corpus_and_prefix',result:'proved'},
        {rule:'complete_digest_profile_and_pure_read_frame',result:'proved'},
        {rule:'exact_utf16_digest_commitment',result:'proved'},
        {rule:'finite_digest_loops',result:'proved'},
        {rule:'masked_clock_low_bits',result:'proved'},
        {rule:'immutable_seed_binding',result:'proved'}],
      remaining_conditions:['Standard unmodified Array.isArray, String.charCodeAt, Math.imul and Number/BigInt/bitwise semantics',
        'Ordinary synchronous process.hrtime.bigint returns BigInt, or Date.now returns Number, or fallback; no getters/callback reentry during initialization',
        'Successful CommonJS initialization under the admitted source prefix; no resource exhaustion or timing observer'],
      claim:'For the intact source-bound literal corpus, the initialized immutable seed satisfies (seed & 3) === 1 for every admitted clock value'};
    proof.certificate_sha256=sha(canonical(proof));return proof;
  }catch(error){return {format,status:'unknown',reason:error instanceof Error&&/^[a-z][a-z0-9_]{0,80}$/.test(error.message)?error.message:'seed_proof_failure'};}
}
module.exports={proveSeedInvariant,literalCorpusDigest};
