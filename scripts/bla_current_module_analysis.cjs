'use strict';
/** Conservative source inventory for current BLA modules and LASIK views.
 * No target source is evaluated and no cleanup is promoted to equivalence.
 * Graphs/slices describe binding-aware syntactic dependencies, not a universal
 * JavaScript information-flow or control-flow proof.
 */
const crypto=require('node:crypto'),path=require('node:path');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const UNKNOWN=Symbol('unknown');
const META=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens','errors','shorthand']);
function clean(x){if(Array.isArray(x))return x.map(clean);if(!x||typeof x!=='object')return x;const o={};for(const k of Object.keys(x).sort())if(!META.has(k)&&x[k]!=null)o[k]=clean(x[k]);return o;}
const canon=x=>JSON.stringify(clean(x));
const fail=r=>{throw Error(r);};
const receipt=(n,s)=>({source_offsets:[n.start,n.end],source_region_sha256:sha(s.slice(n.start,n.end))});
const safePath=s=>typeof s==='string'&&s.length<=160&&/^[A-Za-z0-9_./:@#-]+$/.test(s)&&!s.startsWith('/')&&!s.split('/').includes('..');
const safeSpecifier=s=>typeof s==='string'&&s.length<=160&&/^[A-Za-z0-9_./:@#-]+$/.test(s)?s:null;
const property=n=>!n?.computed&&n?.property?.type==='Identifier'?n.property.name:n?.computed&&n.property.type==='StringLiteral'?n.property.value:null;

function inventory({source,modulePath,babelRoot,privateRuntimeMetadata}){
 const parser=require(path.join(babelRoot,'@babel/parser')),traverse=require(path.join(babelRoot,'@babel/traverse')).default;
 const ast=parser.parse(source,{sourceType:'unambiguous'});let program;
 traverse(ast,{Program(p){program=p;p.stop();}});
 const seedName=Object.keys(program.scope.bindings).find(n=>/^runtimeSeed/.test(n));
 const seedProof=seedName?require('./bla_seed_invariant.cjs').proveSeedInvariant({source,babelRoot,seedName}):{status:'not_present'};
 const seedBinding=program.scope.bindings[seedName];
 function value(n,scope,seen=new Set()){
  if(!n)return UNKNOWN;if(['StringLiteral','NumericLiteral','BooleanLiteral'].includes(n.type))return n.value;if(n.type==='NullLiteral')return null;
  if(n.type==='Identifier'){const b=scope.getBinding(n.name);if(!b||seen.has(b)||b.constantViolations.length||!b.path.isVariableDeclarator())return UNKNOWN;const next=new Set(seen);next.add(b);return value(b.path.node.init,b.path.scope,next);}
  if(n.type==='CallExpression'&&n.callee.type==='MemberExpression'&&!n.callee.computed&&n.callee.object.name==='Object'&&!scope.getBinding('Object')&&n.callee.property.name==='freeze'&&n.arguments.length===1&&n.arguments[0].type==='ArrayExpression')return value(n.arguments[0],scope,seen);
  if(n.type==='ArrayExpression'){const xs=n.elements.map(e=>value(e,scope,seen));return xs.includes(UNKNOWN)?UNKNOWN:xs;}
  if(n.type==='ConditionalExpression'){const t=value(n.test,scope,seen);return typeof t==='boolean'?value(t?n.consequent:n.alternate,scope,seen):UNKNOWN;}
  if(n.type==='BinaryExpression'){
   const a=value(n.left,scope,seen),b=value(n.right,scope,seen);
   if(n.operator==='+'&&a!==UNKNOWN&&b!==UNKNOWN&&['string','number'].includes(typeof a)&&['string','number'].includes(typeof b))return a+b;
   if(['===','!=='].includes(n.operator)&&n.right.type==='NumericLiteral'&&[0,1].includes(n.right.value)){
    const mask=n.left,c=mask?.left;if(mask?.type!=='BinaryExpression'||mask.operator!=='&'||c?.type!=='CallExpression'||c.arguments.length!==2||c.callee.type!=='MemberExpression'||c.callee.computed
      ||c.callee.object.name!=='Math'||c.callee.property.name!=='imul'||scope.getBinding('Math'))return UNKNOWN;
    const seeded=(x,op)=>x?.type==='BinaryExpression'&&x.operator===op&&x.left.type==='Identifier'&&x.left.name===seedName&&scope.getBinding(seedName)===seedBinding
       &&x.right.type==='NumericLiteral'&&Number.isInteger(x.right.value)&&x.right.value>=0&&x.right.value<=0xffffffff?x.right.value:null;
    const square=seeded(c.arguments[0],'^'),consecutive=seeded(c.arguments[0],'|');let residue;
    if(mask.right.value===7&&seedProof.status==='proved'&&square!==null&&square===seeded(c.arguments[1],'^')){
     const r=[1,5].map(x=>Math.imul(x^square,x^square)&7);if(r[0]!==r[1])return UNKNOWN;residue=r[0];
    }else if(mask.right.value===1&&seedProof.status==='proved'&&consecutive!==null&&c.arguments[1].type==='BinaryExpression'&&c.arguments[1].operator==='+'
      &&c.arguments[1].right.value===1&&canon(c.arguments[1].left)===canon(c.arguments[0]))residue=0;else return UNKNOWN;
    return n.operator==='==='?residue===n.right.value:residue!==n.right.value;
   }
  }
  return UNKNOWN;
 }
 function pruned(p){for(let q=p;q.parentPath;q=q.parentPath){const parent=q.parentPath,n=parent.node;
   if(n.type==='IfStatement'||n.type==='ConditionalExpression'){const t=value(n.test,parent.scope);if(typeof t==='boolean'&&((q.key==='consequent'&&!t)||(q.key==='alternate'&&t)))return true;}
   if(n.type==='LogicalExpression'&&q.key==='right'){const t=value(n.left,parent.scope);if(t!==UNKNOWN&&((n.operator==='&&'&&!t)||(n.operator==='||'&&t)))return true;}
  }return false;}
 const functions=[],nodeToId=new Map(),functionPaths=new Map();
 program.traverse({Function(p){const id='fn:'+p.node.start;nodeToId.set(p.node,id);functionPaths.set(id,p);
  functions.push({id,name:p.node.id?.name||null,kind:p.node.type,async:!!p.node.async,generator:!!p.node.generator,parameter_count:p.node.params.length,
   ...receipt(p.node,source),ast_sha256:sha(canon(p.node)),syntactically_pruned:pruned(p)});}});
 const owner=p=>{const f=p.getFunctionParent();return f?nodeToId.get(f.node):'$init';};
 function callable(p){if(!p)return null;const n=p.node;
  if(['FunctionExpression','ArrowFunctionExpression','FunctionDeclaration','ObjectMethod'].includes(n.type))return nodeToId.get(n);
  if(n.type!=='Identifier')return null;const b=p.scope.getBinding(n.name);if(!b||b.constantViolations.length)return null;
  if(b.path.isFunctionDeclaration())return nodeToId.get(b.path.node);
  if(b.path.isVariableDeclarator()&&['FunctionExpression','ArrowFunctionExpression'].includes(b.path.node.init?.type))return nodeToId.get(b.path.node.init);
  return null;
 }
 function imported(p){const n=p.node;if(n.type!=='Identifier')return null;const b=p.scope.getBinding(n.name);if(!b||b.constantViolations.length||!b.path.isVariableDeclarator())return null;
  const init=b.path.get('init');if(init.node?.type!=='CallExpression'||init.node.callee.type!=='Identifier'||init.node.callee.name!=='require'||init.scope.getBinding('require')||init.node.arguments.length!==1)return null;
  const spec=value(init.node.arguments[0],init.scope);if(typeof spec!=='string')return null;
  if(b.path.node.id.type==='Identifier')return {module:spec,member:null};
  if(b.path.node.id.type==='ObjectPattern'){const prop=b.path.node.id.properties.find(x=>x.type==='ObjectProperty'&&x.value?.type==='Identifier'&&x.value.name===n.name&&!x.computed);if(prop)return {module:spec,member:prop.key.name??prop.key.value};}
  return null;
 }
 function operation(p){const n=p.node;if(n.type==='Identifier'){
   const imp=imported(p);if(imp)return {kind:'imported_call',module:imp.module,member:imp.member};
   if(n.name==='require'&&!p.scope.getBinding('require'))return {kind:'require'};
   if(['eval','Function','setTimeout','setInterval','queueMicrotask'].includes(n.name)&&!p.scope.getBinding(n.name))return {kind:'dynamic_or_scheduled',name:n.name};return {kind:'unresolved_call'};
  }
  if(n.type==='MemberExpression'){
   const prop=property(n),imp=imported(p.get('object'));if(imp&&prop)return {kind:'imported_call',module:imp.module,member:prop};
   if(n.object.type==='Identifier'&&!p.scope.getBinding(n.object.name)&&['process','console','Buffer','WebAssembly','Object','Math','Reflect','JSON','globalThis'].includes(n.object.name))return {kind:'global_method',global:n.object.name,member:prop};
   return {kind:'unresolved_method',member:prop};
  }return {kind:'unresolved_callee'};
 }
 if(privateRuntimeMetadata){const candidates=[];program.traverse({CallExpression(p){
   const c=p.node.callee;if(pruned(p)||c.type!=='MemberExpression'||property(c)!=='includes'||c.object.type!=='Identifier'||p.node.arguments.length!==1||p.node.arguments[0].type!=='Identifier')return;
   const array=p.scope.getBinding(c.object.name),input=p.scope.getBinding(p.node.arguments[0].name),fn=p.getFunctionParent();
   if(!array||array.scope!==program.scope||array.constantViolations.length||!array.path.isVariableDeclarator()||array.path.parent.kind!=='const'||array.referencePaths.length!==1
      ||!input?.path.isVariableDeclarator()||input.path.parent.kind!=='const'||!fn?.node.async||p.parentPath.node.type!=='IfStatement'||p.key!=='test')return;
   const init=input.path.node.init,arg=init?.left,values=value(array.path.node.init,array.path.scope);
   if(init?.type!=='LogicalExpression'||init.operator!=='||'||init.right.type!=='StringLiteral'||init.right.value!==''||arg?.type!=='MemberExpression'||!arg.computed||arg.property.value!==2
      ||arg.object.type!=='MemberExpression'||property(arg.object)!=='argv'||arg.object.object.name!=='process'||input.path.scope.getBinding('process')
      ||!Array.isArray(values)||values.length!==3||values.some(x=>typeof x!=='string'||x.length!==16||Buffer.byteLength(x)!==16)||new Set(values).size!==3)return;
   candidates.push({honeypotInputs:values,qualifier:receipt(p.node,source),array:receipt(array.path.node.init,source)});
  }});privateRuntimeMetadata.source_sha256=sha(source);if(candidates.length===1)Object.assign(privateRuntimeMetadata,{status:'source_qualified_literal_candidates',...candidates[0]});
   else Object.assign(privateRuntimeMetadata,{status:'unknown',reason:'retired_input_boundary_not_unique'});}
 const calls=[],effects=[],requires=[],reflections=[],writes=[],unknowns=[];
 program.traverse({CallExpression(p){const direct=callable(p.get('callee')),op=operation(p.get('callee')),item={owner:owner(p),callee:direct,operation:op,argument_count:p.node.arguments.length,
    syntactically_pruned:pruned(p),...receipt(p.node,source)};
   if(op.module){item.operation={...op,module:safeSpecifier(op.module),module_sha256:sha(op.module)};}
   if(op.kind==='require'){const spec=p.node.arguments.length===1?value(p.node.arguments[0],p.scope):UNKNOWN;item.required_module=typeof spec==='string'?safeSpecifier(spec):null;
    if(typeof spec==='string')item.required_module_sha256=sha(spec);requires.push(item);}
   calls.push(item);
   if(direct)return;
   const rawModule=op.module?.replace(/^node:/,'');let kind;
   if(rawModule==='fs'&&['readFileSync','readFile','createReadStream'].includes(op.member))kind='filesystem_read';
   else if(rawModule==='vm')kind='javascript_vm';else if(rawModule==='crypto')kind='crypto_provider';
   else if(rawModule==='inspector')kind='debugger_environment';
   else if(op.global==='WebAssembly')kind='wasm_provider';else if(op.global==='console')kind='console_output';
   else if(op.global==='process'&&['exit','abort'].includes(op.member))kind='process_termination';
   else if(op.global==='Object'&&op.member==='defineProperty')kind='property_definition';
   else if(op.global==='globalThis'&&op.member==='addEventListener')kind='event_registration';
   else if(op.kind==='dynamic_or_scheduled')kind=op.name==='eval'||op.name==='Function'?'dynamic_code':'scheduled_callback';
   else if(op.kind==='require')kind='module_load';
   if(kind)effects.push({...item,kind});
   if(['unresolved_call','unresolved_callee','unresolved_method'].includes(op.kind))unknowns.push({kind:'unresolved_call_target',owner:item.owner,...receipt(p.node,source)});
  },MemberExpression(p){const n=p.node,prop=property(n);
   if(prop==='toString'&&n.object.type==='MemberExpression'&&property(n.object)==='prototype'&&n.object.object.name==='Function'&&!p.scope.getBinding('Function'))reflections.push({kind:'native_function_source_reflection',owner:owner(p),syntactically_pruned:pruned(p),...receipt(n,source)});
   if(n.object.type==='Identifier'&&n.object.name==='process'&&!p.scope.getBinding('process')&&['execArgv','env','argv'].includes(prop))reflections.push({kind:prop==='argv'?'cli_argument_read':'process_environment_read',owner:owner(p),syntactically_pruned:pruned(p),...receipt(n,source)});
  },ReferencedIdentifier(p){if(['__filename','__dirname'].includes(p.node.name)&&!p.scope.getBinding(p.node.name))reflections.push({kind:'module_source_location',name:p.node.name,owner:owner(p),syntactically_pruned:pruned(p),...receipt(p.node,source)});},
  AssignmentExpression(p){const l=p.node.left;writes.push({owner:owner(p),target:l.type==='MemberExpression'&&l.object.type==='Identifier'&&!p.scope.getBinding(l.object.name)?{global:l.object.name,property:property(l)}:{kind:l.type},syntactically_pruned:pruned(p),...receipt(p.node,source)});},
 });
 const exports=[];
 program.traverse({AssignmentExpression(p){const l=p.node.left;if(l.type!=='MemberExpression'||l.object.name!=='module'||property(l)!=='exports'||p.scope.getBinding('module'))return;
   if(p.node.operator!=='='||p.node.right.type!=='ObjectExpression'){unknowns.push({kind:'dynamic_export_surface',...receipt(p.node,source)});return;}
   for(const prop of p.get('right.properties')){const n=prop.node,key=n.key?.name??n.key?.value;if(n.type!=='ObjectProperty'||n.computed||typeof key!=='string'){unknowns.push({kind:'dynamic_export_member',...receipt(n,source)});continue;}
    const fn=callable(prop.get('value'));exports.push({key:/^[A-Za-z_$][\w$]{0,80}$/.test(key)?key:null,key_sha256:sha(key),function:fn,...receipt(n,source)});}
  }});
 const roots=['$init',...exports.map(x=>x.function).filter(Boolean)],reached=new Set(roots),queue=[...roots];
 while(queue.length){const id=queue.shift();for(const c of calls)if(c.owner===id&&!c.syntactically_pruned&&c.callee&&!reached.has(c.callee)){reached.add(c.callee);queue.push(c.callee);}}
 // Methods/callbacks/dynamic imports are deliberately not guessed. Reachability
 // here is a may-reach subset under direct calls, with unresolved boundaries kept.
 const firstAwaits=[];for(const f of functions.filter(x=>x.async)){const fp=functionPaths.get(f.id);let first=null;fp.traverse({Function(p){p.skip();},AwaitExpression(p){if(!pruned(p)&&(!first||p.node.start<first.start))first=p.node;}});if(first)firstAwaits.push({function:f.id,...receipt(first,source)});}
 const initAsyncCalls=calls.filter(c=>c.owner==='$init'&&c.callee&&functions.find(f=>f.id===c.callee)?.async&&!c.syntactically_pruned);
 const topLevel=ast.program.body.map(n=>({kind:n.type,execution:n.type==='FunctionDeclaration'?'inert_declaration':'executed_during_module_evaluation',...receipt(n,source)}));
 function graphPath(root,dest){const q=[[root]],seen=new Set([root]);while(q.length){const xs=q.shift(),end=xs.at(-1);if(end===dest)return xs;for(const c of calls.filter(c=>c.owner===end&&c.callee&&!c.syntactically_pruned))if(!seen.has(c.callee)){seen.add(c.callee);q.push([...xs,c.callee]);}}return null;}
 const fingerprints=[];
 for(const f of functions){const fsReads=effects.filter(e=>e.owner===f.id&&e.kind==='filesystem_read'&&!e.syntactically_pruned),hashes=effects.filter(e=>e.owner===f.id&&e.kind==='crypto_provider'&&e.operation.member==='createHash'&&!e.syntactically_pruned);
  if(!fsReads.length||!hashes.length)continue;
  const fp=functionPaths.get(f.id),updates=[],hashBindings=new Map(),digestReturns=[];
  function chosen(n,scope){if(n?.type==='ConditionalExpression'){const t=value(n.test,scope);return typeof t==='boolean'?chosen(t?n.consequent:n.alternate,scope):null;}return n;}
  fp.traverse({Function(p){p.skip();},VariableDeclarator(p){if(pruned(p)||p.node.id.type!=='Identifier')return;const init=chosen(p.node.init,p.scope),binding=p.scope.getBinding(p.node.id.name);
   if(!init||!binding||binding.constantViolations.length||p.parent.kind!=='const'||!hashes.some(h=>h.source_offsets[0]===init.start)||init.arguments.length!==1||value(init.arguments[0],p.scope)!=='sha256')return;
   hashBindings.set(binding,{binding_definition:receipt(p.node,source),creation:receipt(init,source)});
  }});
  fp.traverse({Function(p){p.skip();},ReturnStatement(p){if(pruned(p))return;const n=chosen(p.node.argument,p.scope);if(n?.type==='CallExpression'&&n.callee.type==='MemberExpression'&&property(n.callee)==='digest'&&n.callee.object.type==='Identifier'){
    const b=p.scope.getBinding(n.callee.object.name);if(hashBindings.has(b))digestReturns.push({binding:b,receipt:receipt(p.node,source)});}},
   CallExpression(p){if(pruned(p)||p.node.callee.type!=='MemberExpression'||property(p.node.callee)!=='update'||p.node.callee.object.type!=='Identifier')return;
    const b=p.scope.getBinding(p.node.callee.object.name);if(!hashBindings.has(b))return;
    for(const read of fsReads)if(p.node.arguments.some(n=>n.start<=read.source_offsets[0]&&n.end>=read.source_offsets[1]))updates.push({...receipt(p.node,source),binding:b,filesystem_read_offsets:read.source_offsets});}});
  const linked=updates.filter(u=>digestReturns.some(r=>r.binding===u.binding));if(!linked.length)continue;
  const linkedReceipts=linked.map(({binding,...u})=>({...u,hash_binding:hashBindings.get(binding),digest_returns:digestReturns.filter(r=>r.binding===binding).map(r=>r.receipt)}));
  const linkedReadOffsets=new Set(linked.map(u=>u.filesystem_read_offsets.join(':')));
  const paths=[],sourceInputs=[];
  function relativeBase(p,seen=new Set()){
   if(p.node.type==='Identifier'&&p.node.name==='__dirname'&&!p.scope.getBinding('__dirname'))return '.';
   if(p.node.type==='Identifier'){const b=p.scope.getBinding(p.node.name);if(!b||seen.has(b)||b.constantViolations.length||!b.path.isVariableDeclarator()||!b.path.node.init)return null;const next=new Set(seen);next.add(b);return relativeBase(b.path.get('init'),next);}
   if(p.node.type==='CallExpression'){const op=operation(p.get('callee'));if(op.module?.replace(/^node:/,'')!=='path'||op.member!=='join'||!p.node.arguments.length)return null;
    const first=relativeBase(p.get('arguments.0'),seen),rest=p.node.arguments.slice(1).map(n=>value(n,p.scope));if(first===null||rest.some(x=>typeof x!=='string'||x.startsWith('/')))return null;return path.posix.normalize(path.posix.join(first,...rest));}
   return null;
  }
  fp.traverse({Function(p){p.skip();},CallExpression(p){if(!linkedReadOffsets.has([p.node.start,p.node.end].join(':')))return;const file=p.get('arguments.0');if(file?.node?.type!=='CallExpression')return;
   const op=operation(file.get('callee'));if(op.module?.replace(/^node:/,'')!=='path'||op.member!=='join'||file.node.arguments.length!==2)return;
   const base=relativeBase(file.get('arguments.0')),name=file.get('arguments.1');if(base===null||name.node.type!=='Identifier')return;
   const binding=name.scope.getBinding(name.node.name),loop=binding?.path.findParent(q=>q.isForOfStatement());if(!loop||binding.path.node.init)return;
   const members=value(loop.node.right,loop.scope);if(!Array.isArray(members)||!members.length||!members.every(x=>typeof x==='string'&&safePath(x)&&/\.(cjs|mjs|js|json)$/.test(x)))return;
   paths.push(...members);sourceInputs.push({base_relative_to_module_directory:base,paths:members,...receipt(file.node,source)});
  }});
  const sites=[];for(const call of calls.filter(c=>c.callee===f.id&&!c.syntactically_pruned)){
   let cp;program.traverse({CallExpression(p){if(p.node.start===call.source_offsets[0]){cp=p;p.stop();}}});if(!cp)continue;
   let parentCall=cp.parentPath;while(parentCall&&!parentCall.isFunction()&&!parentCall.isCallExpression())parentCall=parentCall.parentPath;
   const consumer=parentCall?.isCallExpression()?{callee:callable(parentCall.get('callee')),argument_index:parentCall.node.arguments.findIndex(n=>n.start<=cp.node.start&&n.end>=cp.node.end),...receipt(parentCall.node,source)}:null;
   let declaration=cp.findParent(p=>p.isVariableDeclarator());const binding=declaration?.node.id.type==='Identifier'?declaration.scope.getBinding(declaration.node.id.name):null;
   const ownerPath=functionPaths.get(call.owner),definitions=[];
   if(ownerPath){ownerPath.traverse({Function(p){p.skip();},VariableDeclarator(p){if(pruned(p)||p.node.id.type!=='Identifier'||!p.node.init)return;const b=p.scope.getBinding(p.node.id.name),deps=new Set(),init=p.get('init');if(init.isReferencedIdentifier()){const d=init.scope.getBinding(init.node.name);if(d)deps.add(d);}init.traverse({ReferencedIdentifier(q){const d=q.scope.getBinding(q.node.name);if(d)deps.add(d);}});definitions.push({binding:b,depends:deps,node:p.node});}});}
   const dependent=new Set(binding?[binding]:[]);let changed=true;while(changed){changed=false;for(const d of definitions)if(!dependent.has(d.binding)&&[...d.depends].some(x=>dependent.has(x))){dependent.add(d.binding);changed=true;}}
   const comparisons=[],returns=[];if(ownerPath)ownerPath.traverse({Function(p){p.skip();},CallExpression(p){const op=operation(p.get('callee'));if(op.module?.replace(/^node:/,'')==='crypto'&&op.member==='timingSafeEqual'&&!pruned(p)){
     let relevant=false;p.traverse({ReferencedIdentifier(q){if(dependent.has(q.scope.getBinding(q.node.name)))relevant=true;}});if(relevant)comparisons.push(receipt(p.node,source));}},ReturnStatement(p){if(pruned(p))return;let relevant=false;p.traverse({ReferencedIdentifier(q){if(dependent.has(q.scope.getBinding(q.node.name)))relevant=true;}});if(relevant)returns.push(receipt(p.node,source));}});
   sites.push({caller:call.owner,call:call,immediate_argument_consumer:consumer,assigned_binding:binding?{name:binding.identifier.name,...receipt(binding.identifier,source)}:null,
    downstream_definitions:definitions.filter(d=>dependent.has(d.binding)).map(d=>({name:d.binding.identifier.name,...receipt(d.node,source)})),crypto_acceptance_comparisons:comparisons,dependent_returns:returns});
  }
  fingerprints.push({function:f.id,source_files:paths,source_inputs:sourceInputs,filesystem_reads:fsReads,hash_creations:hashes,hash_updates_with_file_bytes:linkedReceipts,returned_hash_state_link_checked:true,
   admitted_export_paths:exports.map(e=>({export:e.key,path:graphPath(e.function,f.id)})).filter(x=>x.path),consumption_sites:sites,
   interpretation:'Binding-aware syntactic file-byte-to-hash and return/argument dependencies; not a proof that all inputs reach the path or that arbitrary code rewrites preserve its result'});
 }
 return {module_path:modulePath,source:{sha256:sha(source),bytes:Buffer.byteLength(source)},seed_guard_premise:{status:seedProof.status,certificate_sha256:seedProof.certificate_sha256||null,remaining_conditions:seedProof.remaining_conditions||[],branch_pruning:'Only under the attached standard-intrinsic/clock conditions; no arbitrary host context proof'},
  top_level:topLevel,functions,calls,effects,requires,exports,reflection:reflections,writes,unresolved_boundaries:unknowns,
  inventory_completeness:{effect_inventory_exhaustive:false,reason:'Identified calls/writes/reflection are retained; arbitrary getters/proxies, constructors, callbacks, dynamic property receivers, import effects and implicit coercions require separate contracts'},
  direct_call_reachability:{roots,may_reached:[...reached],qualification:'May-reach closure over resolved direct binding calls only, with source-proved branches pruned; callback/receiver/exception/control-flow reachability remains unresolved and this is not a complete runtime call graph'},
  initialization_execution_model:{async_entry_calls:initAsyncCalls,first_awaits:firstAwaits,await_qualification:'Lexically first non-pruned await per async function; not a general control-flow first-suspension proof',
   note:initAsyncCalls.length?'Top-level async call starts synchronously, then module evaluation may continue at suspension before Promise settlement; an earlier native process.exit can preempt the tail':'Top-level synchronous work executes in statement order; assigning process.exitCode schedules later process termination and does not preempt following statements'},
  source_integrity_slices:fingerprints,limitations:['No universal JavaScript equivalence or information-flow proof','No inferred callback/method targets or complete exception/control-flow proof',
   'Hash receiver identity is syntactic; receiver member writes, method replacement or escaping aliases require separate native-provider/state contracts',
   'A source hash binds evidence; a matched call inventory or successful input is not semantic equivalence','Source reflection, environment, filesystem/provider state, initialization and asynchronous settlement remain observable']};
}

function analyzeCurrentModules({originalModules,reducedModules,babelRoot,entryPaths=[]}={}){
 const result={format:'fdisbull-bla-current-module-analysis-1',status:'observational_equivalence_unproved',source_execution:false};
 try{
  if(typeof babelRoot!=='string'||!Array.isArray(originalModules)||!Array.isArray(reducedModules)||!originalModules.length||originalModules.length>16||originalModules.length!==reducedModules.length)fail('invalid_module_inventory');
  const check=xs=>{if(new Set(xs.map(x=>x.path)).size!==xs.length)fail('duplicate_module_path');let total=0;for(const m of xs){if(!safePath(m.path)||typeof m.source!=='string'||m.source.length>2*1024*1024)fail('invalid_module_source');total+=m.source.length;}if(total>12*1024*1024)fail('aggregate_source_budget');};check(originalModules);check(reducedModules);
  if(canon(originalModules.map(x=>x.path).sort())!==canon(reducedModules.map(x=>x.path).sort())||!Array.isArray(entryPaths)||entryPaths.some(x=>!originalModules.some(m=>m.path===x)))fail('module_pairing');
  result.entry_paths=entryPaths;result.modules=originalModules.map(original=>{const reduced=reducedModules.find(m=>m.path===original.path),a=inventory({source:original.source,modulePath:original.path,babelRoot}),b=inventory({source:reduced.source,modulePath:reduced.path,babelRoot});
   const matched=a.functions.filter(f=>f.name&&b.functions.some(g=>g.name===f.name&&g.ast_sha256===f.ast_sha256)).map(f=>({name:f.name,ast_sha256:f.ast_sha256}));
   return {module_path:original.path,status:original.source===reduced.source?'byte_identical':'observational_equivalence_unproved',original:a,reduced:b,
    comparison:{source_bytes_equal:original.source===reduced.source,exact_named_function_asts:matched,export_key_sets_equal:canon(a.exports.map(x=>x.key_sha256).sort())===canon(b.exports.map(x=>x.key_sha256).sort()),
     initialization_statement_counts:[a.top_level.length,b.top_level.length],source_integrity_helper_counts:[a.source_integrity_slices.length,b.source_integrity_slices.length],
     warning:'Counts, names, matching AST fragments and accepted keys are scoped evidence; unmatched executed effects or source integrity dependencies cannot be discarded'}};});
  const sources=new Map(result.modules.map(m=>[m.module_path,m]));
  result.changed_source_integrity_inputs=[];
  for(const m of result.modules)for(const side of ['original','reduced'])for(const f of m[side].source_integrity_slices)for(const input of f.source_inputs)for(const relative of input.paths){
   const candidate=path.posix.normalize(path.posix.join(path.posix.dirname(m.module_path),input.base_relative_to_module_directory,relative)),pair=sources.get(candidate);
   if(pair&&!pair.comparison.source_bytes_equal)result.changed_source_integrity_inputs.push({reader_module:m.module_path,side,helper:f.function,read_module:candidate,
     original_source_sha256:pair.original.source.sha256,reduced_source_sha256:pair.reduced.source.sha256,
     interpretation:'A source-byte read feeding a returned digest names a changed module; digest/acceptance preservation requires a separate contract or witness'});
  }
  result.project_call_graph={qualification:'Binding-resolved direct local/imported CommonJS calls and module loads only; may-reach is not a complete callback, exception, coercion or dynamic-receiver graph',sides:{}};
  for(const side of ['original','reduced']){
   const edges=[],roots=[];
   for(const entry of entryPaths)roots.push({module:entry,function:'$init',kind:'entrypoint'});
   for(const m of result.modules){const inv=m[side];for(const ex of inv.exports)if(ex.function)roots.push({module:m.module_path,function:ex.function,kind:'admitted_export',export:ex.key});
    for(const call of inv.calls){if(call.syntactically_pruned)continue;
     if(call.callee)edges.push({caller_module:m.module_path,caller:call.owner,callee_module:m.module_path,callee:call.callee,kind:'direct_local',source_offsets:call.source_offsets});
     const spec=call.operation.kind==='require'?call.required_module:call.operation.module;if(typeof spec!=='string'||!spec.startsWith('.'))continue;
     const normalized=path.posix.normalize(path.posix.join(path.posix.dirname(m.module_path),spec));
     const target=[normalized,normalized+'.cjs',normalized+'.js',normalized+'/index.cjs',normalized+'/index.js'].find(x=>sources.has(x));if(!target)continue;
     if(call.operation.kind==='require')edges.push({caller_module:m.module_path,caller:call.owner,callee_module:target,callee:'$init',kind:'commonjs_load',source_offsets:call.source_offsets});
     else{const members=sources.get(target)[side].exports.filter(x=>x.key===call.operation.member&&x.function);if(members.length===1)edges.push({caller_module:m.module_path,caller:call.owner,callee_module:target,callee:members[0].function,kind:'imported_export',export:members[0].key,source_offsets:call.source_offsets});}
    }
   }
   const key=(m,f)=>m+'::'+f,reached=new Set(roots.map(r=>key(r.module,r.function))),queue=[...reached];
   while(queue.length){const at=queue.shift();for(const edge of edges)if(key(edge.caller_module,edge.caller)===at){const next=key(edge.callee_module,edge.callee);if(!reached.has(next)){reached.add(next);queue.push(next);}}}
   result.project_call_graph.sides[side]={roots,edges,may_reach:[...reached]};
  }
  result.claim='Conservative source-bound inventory and dependency slices for originals and reductions; whole-module equivalence remains unproved';
  result.certificate_sha256=sha(canon(result));return result;
 }catch(error){return {...result,status:'unknown',reason:error instanceof Error&&/^[a-z][a-z0-9_]{0,80}$/.test(error.message)?error.message:'module_inventory_failed'};}
}
/** Private runtime-only extraction. Never include its honeypotInputs in reports. */
function extractCurrentV6RuntimeMetadata({source,babelRoot}={}){
 try{if(typeof source!=='string'||source.length>2*1024*1024||typeof babelRoot!=='string')fail('invalid_source');const runtime={};inventory({source,modulePath:'vault.cjs',babelRoot,privateRuntimeMetadata:runtime});return runtime;}
 catch(_){return {status:'unknown',reason:'runtime_metadata_extraction_failed'};}
}
module.exports={analyzeCurrentModules,extractCurrentV6RuntimeMetadata};
