'use strict';
/** Source-bound module/CLI composition. Target source is parsed, never run.
 * Full-global initialization and the terminating CLI are separate observations:
 * a private-looking global getter is still an observable module side effect.
 */
const crypto=require('node:crypto'),path=require('node:path');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const META=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens','errors','shorthand']);
function clean(x){if(Array.isArray(x))return x.map(clean);if(!x||typeof x!=='object')return x;const o={};for(const k of Object.keys(x).sort())if(!META.has(k)&&x[k]!=null)o[k]=clean(x[k]);return o;}
const canonical=x=>JSON.stringify(clean(x));
const fail=r=>{throw Error(r);};
const CORE=['sha256Hex','deriveFlagMask','decodeFlagCipher','tryUnlock'];
const CLI=['printUsage','main'];
const CONSTANTS=['SCOPE','KEY_SHA256','FLAG_SHA256','FLAG_CIPHER_HEX','LICENSE_RPC'];
const UNKNOWN=Symbol('unknown');
const member=(n,a,b)=>n?.type==='MemberExpression'&&!n.computed&&n.object.type==='Identifier'&&n.object.name===a&&n.property.name===b;
const literal=n=>n&&['StringLiteral','NumericLiteral','BooleanLiteral','NullLiteral'].includes(n.type)?(n.type==='NullLiteral'?null:n.value):UNKNOWN;
const sourceReceipt=(n,s)=>({source_offsets:[n.start,n.end],source_region_sha256:sha(s.slice(n.start,n.end))});

// Authored semantic profiles, independent of challenge source bytes/messages.
const MAIN_PROFILE=`function main(){const input=process.argv[2]||"";if(!input){printUsage();process.exit(1);}const result=tryUnlock(input);if(result){console.log("message"+result);process.exit(0);}console.error("message");process.exit(1);}`;
const USAGE_PROFILE=`function printUsage(){console.log("message");}`;
const GLOBAL_PROFILE=`(function decorate(){try{
 const host=typeof globalThis!=="undefined"?globalThis:typeof window!=="undefined"?window:{};
 const argv=typeof process!=="undefined"&&Array.isArray(process.execArgv)?process.execArgv.join(" "):"";
 const observed=argv.includes("marker")||argv.includes("marker")||Boolean(host&&(host.__playwright||host.__puppeteer_evaluation_script__||host.frida||host._frida_||host.navigator&&host.navigator.webdriver));
 const vault=Object.freeze({classification:"data",securityBoundary:"data",status:"data",enclaveCid:16,transport:"data",inspectorObserved:observed,attestationNotice:"data",sessionEpoch:1});
 if(host&&typeof Object.defineProperty==="function"&&!host["property"]){Object.defineProperty(host,"property",{configurable:true,enumerable:false,get:function(){return vault;}});}
 if(host&&typeof host.addEventListener==="function"){
  const listener=function callback(ev){return ev&&ev.type?vault.sessionEpoch:0;};
  host.addEventListener("event",listener,{passive:true});
 }
}catch(_){}})();`;

const CRYPTO_PROFILE=`if(typeof process!=="undefined"&&typeof process.getBuiltinModule==="function"){
 const provider=process.getBuiltinModule("node:crypto");
 if(provider&&typeof provider.createHash==="function"){
  const salts=["salt","salt","salt","salt"];
  for(let salt=0;salt<salts.length;salt++){
   let digest=provider.createHash("sha256").update("prefix"+salts[salt]+"suffix").digest();
   for(let round=0;round<8;round++){
    digest=provider.createHash("sha256").update(digest).update("separator"+salts[salt]+"separator"+round).digest();
   }
   if(typeof provider.createHmac==="function"){provider.createHmac("sha256",digest).update("prefix"+salts[salt]).digest();}
  }
 }
}`;

function proveModuleEquivalence({templateSource,targetSource,babelRoot}={}){
 const format='fdisbull-bla-module-equivalence-1';
 const result={format,status:'unknown',source:{},finite_runtime_checks_are_not_proof:true,full_state_equivalence:false};
 try{
  if(typeof templateSource!=='string'||templateSource.length>65536||typeof targetSource!=='string'||targetSource.length>2*1024*1024||typeof babelRoot!=='string')fail('invalid_module_boundary');
  result.source={template_sha256:sha(templateSource),target_sha256:sha(targetSource)};
  const {analyze}=require('./bla_function_analysis.cjs');
  const checked=analyze(templateSource,targetSource,{babelRoot}),r=checked.runtime;
  if(r.wholeFunctionEquivalence?.status!=='equivalent_under_contract')fail('selected_function_composition_unproved');
  if(r.seedInvariantProof?.status!=='proved')fail('module_seed_initialization_unproved');
  result.selected_function_equivalence={status:r.wholeFunctionEquivalence.status,certificate_sha256:r.wholeFunctionEquivalence.certificate_sha256};
  const parser=require(path.join(babelRoot,'@babel/parser')),traverse=require(path.join(babelRoot,'@babel/traverse')).default;
  const parse=s=>parser.parse(s,{sourceType:'script'});
  const target=parse(targetSource),template=parse(templateSource);let program,reference;
  traverse(target,{Program(p){program=p;p.stop();}});traverse(template,{Program(p){reference=p;p.stop();}});
  const intrinsics=['Math','String','Buffer','Array','Object','Boolean','Number','Date','process','globalThis','window','module','require','console'];
  for(const p of [program,reference])if(intrinsics.some(n=>p.scope.bindings[n]))fail('module_intrinsic_shadowing');
  for(const ast of [target,template])traverse(ast,{Identifier(p){if(/^__moduleproof_/.test(p.node.name))fail('module_canonical_collision');}});
  function exportsOf(ast){const entries=[],statements=[];for(const n of ast.program.body){const e=n.type==='ExpressionStatement'&&n.expression;
   if(e?.type==='AssignmentExpression'&&member(e.left,'module','exports')){if(e.operator!=='='||e.right.type!=='ObjectExpression')fail('dynamic_module_exports');statements.push(n);
    for(const p of e.right.properties){const k=p.key?.name??p.key?.value;if(p.type!=='ObjectProperty'||p.computed||p.value.type!=='Identifier'||typeof k!=='string'||entries.some(x=>x[0]===k))fail('dynamic_module_export');entries.push([k,p.value.name]);}}}
   if(statements.length!==1)fail('module_export_count');return {entries:Object.fromEntries(entries),statement:statements[0]};}
  const exp=exportsOf(target),refExp=exportsOf(template);
  const expectedKeys=['tryUnlock','sha256Hex','LICENSE_RPC','SCOPE','KEY_SHA256','FLAG_SHA256'].sort();
  if(canonical(Object.keys(exp.entries).sort())!==canonical(expectedKeys)||canonical(Object.keys(refExp.entries).sort())!==canonical(expectedKeys))fail('module_export_surface');
  function dispatchOf(ast){const found=ast.program.body.filter(n=>n.type==='IfStatement'&&n.test.type==='BinaryExpression'&&n.test.operator==='==='
    &&member(n.test.left,'require','main')&&n.test.right.type==='Identifier'&&n.test.right.name==='module');
   if(found.length!==1)fail('module_cli_dispatch');const n=found[0],b=n.consequent;
   if(n.alternate||b.type!=='BlockStatement'||b.body.length!==1||b.body[0].type!=='ExpressionStatement'||b.body[0].expression.type!=='CallExpression'
      ||b.body[0].expression.arguments.length||b.body[0].expression.callee.type!=='Identifier')fail('module_cli_dispatch');return {statement:n,name:b.body[0].expression.callee.name};}
  const dispatch=dispatchOf(target),refDispatch=dispatchOf(template);
  if(refDispatch.name!=='main')fail('reference_cli_identity');
  function functionBinding(p,name){const b=p.scope.bindings[name];if(p.node.body.filter(n=>n.type==='FunctionDeclaration'&&n.id.name===name).length!==1||!b||!b.path.isFunctionDeclaration()||b.constantViolations.length||!b.path.parentPath.isProgram())fail('module_callable_identity');return b;}
  const main=functionBinding(program,dispatch.name),refMain=functionBinding(reference,'main');
  const usageCandidates=[];main.path.traverse({CallExpression(p){if(p.node.callee.type==='Identifier'&&p.node.arguments.length===0&&p.node.callee.name!==r.heapStepName
      &&!Object.values(r.functionNames).includes(p.node.callee.name))usageCandidates.push(p.node.callee.name);}});
  if(usageCandidates.length!==1)fail('module_usage_identity');const usage=functionBinding(program,usageCandidates[0]);
  functionBinding(reference,'printUsage');
  const functionNames={...r.functionNames,main:main.identifier.name,printUsage:usage.identifier.name};
  const ni=require('./bla_heap_noninterference.cjs').proveHeapNoninterference({source:targetSource,babelRoot,heapName:r.heapName,heapStepName:r.heapStepName,functionNames,heapProof:r.shadowHeapProof});
  if(ni.status!=='proved')fail('cli_private_noninterference_unproved');
  const map={...Object.fromEntries(Object.entries(r.functionNames).map(([role,name])=>[name,role])),[r.cryptoBindingName]:'createHash',[r.cipherName]:'FLAG_CIPHER_HEX',
   [main.identifier.name]:'main',[usage.identifier.name]:'printUsage'};
  for(const role of CONSTANTS.filter(x=>x!=='FLAG_CIPHER_HEX'))map[exp.entries[role]]=role;
  if(Object.keys(map).length!==12||new Set(Object.values(map)).size!==12)fail('module_role_mapping');
  for(const [name,role]of Object.entries(map)){const b=program.scope.bindings[name];if(!b||b.constantViolations.length||(program.scope.bindings[role]&&program.scope.bindings[role]!==b))fail('module_role_collision');}
  // The core checker independently discharges the low-two-bit premise and every
  // selected heap transition. Replaying guards here includes both CLI functions.
  const reductions=[];
  function seedBinary(n,op){return n?.type==='BinaryExpression'&&n.operator===op&&n.left.type==='Identifier'&&n.left.name===r.seedName
    &&n.right.type==='NumericLiteral'&&Number.isInteger(n.right.value)&&n.right.value>=0&&n.right.value<=0xffffffff?n.right.value:null;}
  function evaluate(n){const v=literal(n);if(v!==UNKNOWN)return v;
   if(n?.type==='BinaryExpression'&&n.operator==='+'){const a=evaluate(n.left),b=evaluate(n.right);if(a!==UNKNOWN&&b!==UNKNOWN&&(typeof a==='string'||typeof b==='string'))return a+b;}
   if(n?.type!=='BinaryExpression'||!['===','!=='].includes(n.operator)||n.right.type!=='NumericLiteral'||![0,1].includes(n.right.value))return UNKNOWN;
   const m=n.left,c=m?.left;if(m?.type!=='BinaryExpression'||m.operator!=='&'||c?.type!=='CallExpression'||c.arguments.length!==2||!member(c.callee,'Math','imul'))return UNKNOWN;
   let value;const square=seedBinary(c.arguments[0],'^'),consecutive=seedBinary(c.arguments[0],'|');
   if(m.right.value===7&&square!==null&&square===seedBinary(c.arguments[1],'^')){const values=[1,5].map(x=>Math.imul(x^square,x^square)&7);if(values[0]!==values[1])fail('module_guard_not_invariant');value=values[0];}
   else if(m.right.value===1&&consecutive!==null&&c.arguments[1].type==='BinaryExpression'&&c.arguments[1].operator==='+'
      &&c.arguments[1].right.value===1&&canonical(c.arguments[1].left)===canonical(c.arguments[0]))value=0;else return UNKNOWN;
   reductions.push(sourceReceipt(n,targetSource));return n.operator==='==='?value===n.right.value:value!==n.right.value;
  }
  const lit=v=>({type:typeof v==='string'?'StringLiteral':typeof v==='boolean'?'BooleanLiteral':'NumericLiteral',value:v});
  traverse(target,{BinaryExpression:{exit(p){const v=evaluate(p.node);if(v!==UNKNOWN)p.replaceWith(lit(v));}},
   ConditionalExpression:{exit(p){const v=literal(p.node.test);if(typeof v==='boolean')p.replaceWith(v?p.node.consequent:p.node.alternate);}},
   IfStatement:{exit(p){const v=literal(p.node.test);if(typeof v!=='boolean')return;let declarations=false;p.traverse({VariableDeclaration(){declarations=true;},FunctionDeclaration(){declarations=true;},ClassDeclaration(){declarations=true;}});
    if(declarations)fail('module_guard_declaration_scope');const selected=v?p.node.consequent:p.node.alternate;if(!selected)p.remove();else if(selected.type==='BlockStatement')p.replaceWithMultiple(selected.body);else p.replaceWith(selected);}}});
  const sites=new Map(ni.selected_calls.map(c=>[c.source_offsets.join(':'),c]));let erased=0;
  traverse(target,{CallExpression(p){if(p.node.callee.type!=='Identifier'||p.node.callee.name!==r.heapStepName||!Object.values(functionNames).includes(p.getFunctionParent()?.node.id?.name))return;
   const key=[p.node.start,p.node.end].join(':');if(!sites.has(key)||!p.parentPath.isExpressionStatement()||p.node.arguments.length!==1||p.node.arguments[0].type!=='NumericLiteral'||!Number.isSafeInteger(p.node.arguments[0].value))fail('module_private_step_site');sites.delete(key);erased++;p.parentPath.remove();}});
  if(sites.size)fail('module_private_step_count');
  program.scope.crawl();for(const [name,role]of Object.entries(map))if(name!==role)program.scope.rename(name,role);
  function normalizeFunctions(ast,roles){traverse(ast,{FunctionDeclaration(p){if(!roles.includes(p.node.id.name))return;const owned=new Set(Object.values(p.scope.bindings));p.traverse({Scopable(q){for(const b of Object.values(q.scope.bindings))owned.add(b);}});
   [...owned].sort((a,b)=>a.identifier.start-b.identifier.start).forEach((b,i)=>b.scope.rename(b.identifier.name,'__moduleproof_local'+i));}});}
  normalizeFunctions(target,CLI);normalizeFunctions(template,CLI);
  const cliFunctions=[];for(const role of CLI){const a=template.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===role),b=target.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===role);
   if(!a||!b||canonical(a)!==canonical(b))fail('complete_cli_function_difference');cliFunctions.push({role,normalized_ast_sha256:sha(canonical(a))});}
  // Check the complete reference control flow, not just a list of allowed calls.
  // Diagnostic string contents may vary, but remain bound by AST comparison.
  function messagesOnly(n){const out=clean(n);function visit(x){if(!x||typeof x!=='object')return;if(x.type==='StringLiteral'&&x.value!=='')x.value='message';for(const v of Object.values(x))Array.isArray(v)?v.forEach(visit):visit(v);}visit(out);return out;}
  const profile=parse(MAIN_PROFILE);normalizeFunctions(profile,['main']);
  if(canonical(messagesOnly(refMain.path.node))!==canonical(messagesOnly(profile.program.body[0])))fail('reference_cli_exit_profile');
  const usageNode=template.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='printUsage');
  const usageProfile=parse(USAGE_PROFILE).program.body[0].body.body[0];
  if(usageNode.async||usageNode.generator||usageNode.params.length||!usageNode.body.body.length||usageNode.body.body.length>32
    ||usageNode.body.body.some(n=>canonical(messagesOnly(n))!==canonical(usageProfile)))fail('reference_usage_profile');
  // Compare the complete executed prefix, retaining statement order. Only the
  // source-proved corpus/clock/heap prefix and inert function declarations differ.
  const material=parse(r.materializedCleanSource);
  const targetPrefix=target.program.body.slice(4,target.program.body.indexOf(dispatch.statement)+1).filter(n=>n.type!=='FunctionDeclaration');
  const referencePrefix=material.program.body.filter(n=>n.type!=='FunctionDeclaration');
  if(target.program.body[3]?.type!=='VariableDeclaration'||target.program.body[3].declarations.length!==1
    ||target.program.body[3].declarations[0].id.name!==r.heapName||canonical(targetPrefix)!==canonical(referencePrefix))fail('module_executed_prefix_difference');
  if(canonical(target.program.directives)!==canonical(template.program.directives))fail('module_directive_difference');
  result.cli={status:'equivalent_under_contract',functions:cliFunctions,dispatch:{...sourceReceipt(dispatch.statement,targetSource),checked_require_main_identity:true},
   termination:{profile:'All normal paths end in immediate process.exit(1), process.exit(0), or process.exit(1); matching throws abort module evaluation',
    normal_exit_paths:['missing argv[2]: usage then exit 1','truthy tryUnlock result: grant then exit 0','falsey tryUnlock result: denial then exit 1'],post_dispatch_initializers_unreachable:true},
   initialization_prefix:{status:'proved_under_contract',seed_certificate_sha256:r.seedInvariantProof.certificate_sha256,heap_certificate_sha256:r.shadowHeapProof.certificate_sha256,
    complete_shared_statement_order_equal:true},noninterference_certificate_sha256:ni.certificate_sha256,
   checked_reductions:{opaque_guards:reductions.length,private_stuttering_calls:erased},
   observer_contract:['Node CommonJS entrypoint with require.main === module, ordinary process.argv[2] string or undefined, immediate native process.exit',
    'Ordered normal console.log/error UTF-8 writes and process exit status; crypto/Buffer and console operations complete normally',
    'Native unmodified process.exit/console, no exit event handlers, callbacks/reentry, write failures or provider throws; unhandled-exception formatting is outside this CLI contract',
    'Standard immutable intrinsics/prototypes and ordinary clock; no reflection/source/stack, timing/resource or concurrent observer'],
   remaining_conditions:r.wholeFunctionEquivalence.remaining_conditions,
   claim:'Whole terminating CLI trace equivalence under the explicit Node entrypoint/I/O contract; not whole-module initialization equivalence',
   valid_key_acceptance_witness:'not_established_by_static_equivalence'};
  result.commonjs_exports={status:'pending_initialization_audit',keys:expectedKeys,functions_certificate_sha256:r.wholeFunctionEquivalence.certificate_sha256,
   observation:'Same six own enumerable export keys; related primitive constants and ordinary LICENSE_RPC string data; callable relation uses the selected function contract and related entry provider states, not function identity/name/source',
   provider_initialization_contract:'Native synchronous crypto/Buffer providers, private per-hash state and no global provider counters/callbacks; discarded decorator calculations do not change future provider results; provider call traces during require remain different'};
  // Audit every remaining top-level initializer. Private, unused bindings alone
  // are insufficient: calls are accepted only through pure allocation profiles.
  function pure(n){if(!n)fail('missing_private_initializer');
   if(['StringLiteral','NumericLiteral','BooleanLiteral','NullLiteral'].includes(n.type)){if(n.type==='NumericLiteral'&&!Number.isFinite(n.value))fail('nonfinite_private_literal');return n.type==='StringLiteral'?'string':n.type==='NumericLiteral'?'number':'primitive';}
   if(n.type==='ArrayExpression'){for(const e of n.elements){if(e)pure(e);}return 'fresh';}
   if(n.type==='ObjectExpression'){const keys=new Set();for(const p of n.properties){const k=p.key?.name??p.key?.value;if(!['ObjectProperty','ObjectMethod'].includes(p.type)||p.computed||typeof k!=='string'||['__proto__','constructor','prototype'].includes(k)||keys.has(k))fail('private_object_profile');keys.add(k);
     if(p.type==='ObjectMethod'){if(p.kind!=='method')fail('private_accessor_initializer');}else pure(p.value);}return 'fresh';}
   if(n.type==='BinaryExpression'){const a=pure(n.left),b=pure(n.right);if(['^','|','&','>>>','>>','<<','-','*','%'].includes(n.operator)&&a==='number'&&b==='number')return 'number';if(n.operator==='+'&&['number','string'].includes(a)&&['number','string'].includes(b))return a==='string'||b==='string'?'string':'number';fail('private_numeric_expression');}
   if(n.type==='CallExpression'&&member(n.callee,'Object','freeze')&&n.arguments.length===1&&pure(n.arguments[0])==='fresh')return 'fresh';
   if(n.type==='CallExpression'&&n.arguments.length===1&&n.arguments[0].type==='NumericLiteral'&&n.arguments[0].value===0
      &&n.callee.type==='MemberExpression'&&!n.callee.computed&&n.callee.property.name==='fill'){
    const a=n.callee.object;if(a.type==='NewExpression'&&a.callee.name==='Array'&&a.arguments.length===1&&a.arguments[0].type==='NumericLiteral'&&Number.isSafeInteger(a.arguments[0].value)&&a.arguments[0].value>=0&&a.arguments[0].value<=65536)return 'fresh';}
   fail('unmodeled_executed_initializer');
  }
  function alphaExpression(statement){const ast={type:'File',program:{type:'Program',sourceType:'script',body:[structuredClone(statement)],directives:[]}};
   traverse(ast,{FunctionExpression(p){const owned=new Set(Object.values(p.scope.bindings));p.traverse({Scopable(q){for(const b of Object.values(q.scope.bindings))owned.add(b);}});let i=0;
    if(p.node.id){p.scope.rename(p.node.id.name,'__moduleproof_self'+p.node.start);}
    [...owned].sort((a,b)=>(a.identifier.start??0)-(b.identifier.start??0)).forEach(b=>{if(b.identifier===p.node.id)return;b.scope.rename(b.identifier.name,'__moduleproof_iife'+i++);});p.skip();}});
   return ast.program.body[0];}
  function shape(n){const out=clean(n);function visit(x){if(!x||typeof x!=='object')return;if(x.type==='StringLiteral'&&!['undefined','function',' ','sha256','node:crypto'].includes(x.value))x.value='data';if(x.type==='NumericLiteral'&&x.value!==0)x.value=1;
    if(x.type==='FunctionExpression'&&x.id)x.id.name='__moduleproof_self';for(const v of Object.values(x))Array.isArray(v)?v.forEach(visit):visit(v);}visit(out);return out;}
  const expectedGlobal=alphaExpression(parse(GLOBAL_PROFILE).program.body[0]);
  function globalEffect(n){
   const expr=n.expression,fn=expr?.callee;if(n.type!=='ExpressionStatement'||expr?.type!=='CallExpression'||expr.arguments.length||fn?.type!=='FunctionExpression'||fn.async||fn.generator||fn.params.length)fail('unmodeled_executed_statement');
   const block=fn.body.body[0]?.block,stmts=block?.body;if(fn.body.body.length!==1||fn.body.body[0]?.type!=='TryStatement'||!stmts||![6,7].includes(stmts.length))fail('unmodeled_global_initializer');
   const install=stmts[4],events=stmts[5],calls=events?.consequent?.body;
   const key=install?.test?.right?.argument?.property,definition=install?.consequent?.body?.[0]?.expression;
   if(key?.type!=='StringLiteral'||['__proto__','constructor','prototype'].includes(key.value)||definition?.arguments?.[1]?.value!==key.value||!key.value.length)fail('global_property_identity');
   if(!calls||calls.length<2||calls.length>33)fail('global_listener_profile');
   const first=clean(calls[1]);for(const call of calls.slice(1))if(canonical(shape(call))!==canonical(shape(first)))fail('global_listener_profile');
   const copy=structuredClone(n),copyCalls=copy.expression.callee.body.body[0].block.body[5].consequent.body;
   copyCalls.splice(2);
   let cryptoCalls=null,expected=expectedGlobal;
   if(stmts.length===7){
    const cryptoBlock=stmts[6]?.consequent?.body?.[1]?.consequent?.body;
    const salts=cryptoBlock?.[0]?.declarations?.[0]?.init;
    const rounds=cryptoBlock?.[1]?.body?.body?.[1]?.test?.right;
    if(salts?.type!=='ArrayExpression'||salts.elements.length!==4||salts.elements.some(x=>x.type!=='StringLiteral')
      ||rounds?.type!=='NumericLiteral'||rounds.value!==8)fail('global_crypto_bounds');
    const prof=parse(GLOBAL_PROFILE.replace('}catch(_){}})();',CRYPTO_PROFILE+'}catch(_){}})();')).program.body[0];
    expected=alphaExpression(prof);cryptoCalls={when:'process.getBuiltinModule and native crypto methods are available',sha256:36,hmac_sha256:4,
      discarded:true,ranking_functions:['4 - salt index','8 - round index'],normal_native_provider_contract:true};
   }
   if(canonical(shape(alphaExpression(copy)))!==canonical(shape(expected)))fail('global_initializer_profile');
   return {kind:'global_own_getter_installation',...sourceReceipt(n,targetSource),property_name_sha256:sha(key.value),descriptor:{configurable:true,enumerable:false,getter:true,setter:false},
    effect:'When the property is absent, installs an observable globalThis own getter returning a frozen private data object',
    conditional_crypto_calls:cryptoCalls,conditional_event_registrations:calls.length-1,event_host:'globalThis.addEventListener when it is a function and all registrations complete normally; absent in ordinary Node',
    ordinary_node_writes:'One global own property plus the separately recorded conditional native crypto footprint; no console writes; swallowed initialization exceptions'};
  }
  const inventory=[],effects=[];
  const runtimeStateProfile=parser.parseExpression('(typeof process!=="undefined"&&process.pid?process.pid&0xff:42)|1');
  try{
   for(const n of target.program.body){const before=n.end<=dispatch.statement.end;let kind;
    if(n.type==='FunctionDeclaration')kind='inert_lexical_function_declaration';
    else if(before)kind='source_checked_initialization_prefix';
    else if(n.type==='VariableDeclaration'){
     if(n.kind!=='const')fail('mutable_tail_declaration');for(const d of n.declarations){if(d.id.type!=='Identifier'||!program.scope.bindings[d.id.name]||program.scope.bindings[d.id.name].constantViolations.length)fail('private_tail_binding');
      if(canonical(d.init)!==canonical(runtimeStateProfile))pure(d.init);}kind='pure_private_allocation_or_numeric_initializer';
    }else if(n.type==='ExpressionStatement'&&n.expression.type==='UnaryExpression'&&n.expression.operator==='void'&&n.expression.argument.type==='Identifier'
       &&program.scope.bindings[n.expression.argument.name]?.path.isFunctionDeclaration())kind='pure_hoisted_function_read';
    else {effects.push(globalEffect(n));kind='checked_global_decorator';}
    inventory.push({kind,...sourceReceipt(n,targetSource)});
   }
   if(new Set(effects.map(e=>e.property_name_sha256)).size!==effects.length)fail('duplicate_global_effect_key');
   result.commonjs_exports.status='related_after_successful_initialization';
   result.initialization={status:effects.length?'different':'equivalent_under_contract',top_level_inventory:inventory,global_effects:effects,
    contract:'Normal CommonJS require in a fresh Node realm; standard unmodified intrinsics/clock and native synchronous crypto, no addEventListener, absent named global property; no callbacks/reentry, timing/resource or source/stack observer',
    all_executed_initializers_classified:true,uncalled_declarations_not_executed:true,
    counterexample:effects.length?{observer:'Reflect.ownKeys(globalThis) and Object.getOwnPropertyDescriptor after successful CommonJS require',
      clean_global_own_property_delta:0,target_global_own_property_delta:effects.length,property_name_sha256:effects.map(x=>x.property_name_sha256),
      evidence:'Source-checked IIFE installs the getter; all later executed statements are checked pure allocations/reads or other independent installations; no erasure/replacement'}:null};
   result.status=effects.length?'different':'equivalent_under_contract';
   result.claim=effects.length?'CommonJS whole-module equivalence is refuted by a checked initialization effect; the separately terminating CLI is equivalent under its explicit contract':'Whole admitted module observations are equivalent under the explicit CommonJS/CLI contracts';
  }catch(error){result.commonjs_exports.status='unknown';result.initialization={status:'unknown',reason:error.message,top_level_inventory:inventory,global_effects:effects,all_executed_initializers_classified:false};
   result.status='unknown';result.claim='CLI equivalence is separately certified; complete CommonJS initialization effects remain unproved';}
  result.certificate_sha256=sha(canonical(result));return result;
 }catch(error){result.reason=error instanceof Error&&/^[a-z][a-z0-9_]{0,80}$/.test(error.message)?error.message:'module_composition_failure';return result;}
}
module.exports={proveModuleEquivalence};
