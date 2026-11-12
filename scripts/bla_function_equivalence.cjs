'use strict';
/** Checked congruence/stuttering composition for the admitted BLA call closure.
 * Certificates describe a conditional JS observation relation, not unrestricted
 * contextual equivalence or an independently verified ECMAScript implementation.
 */
const crypto=require('node:crypto'),path=require('node:path');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const ROLES=['sha256Hex','deriveFlagMask','decodeFlagCipher','tryUnlock'];
const CONSTANTS=['SCOPE','KEY_SHA256','FLAG_SHA256','FLAG_CIPHER_HEX','LICENSE_RPC'];
const fail=reason=>{throw Error(reason);};
const UNKNOWN=Symbol('unknown');
const metadata=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens']);
function clean(value) {
  if(Array.isArray(value))return value.map(clean);
  if(!value||typeof value!=='object')return value;
  const out={};for(const key of Object.keys(value).sort())if(!metadata.has(key)&&value[key]!=null)out[key]=clean(value[key]);return out;
}
const canonical=x=>JSON.stringify(clean(x));

function composeFunctionEquivalence(options={}) {
  try {
    const {templateSource,targetSource,babelRoot,functionNames,seedName,heapName,heapStepName,
      cryptoBindingName,cipherName,globalMap,guardProofs,contractionLedger,noninterferenceProof,heapProof}=options;
    if(typeof templateSource!=='string'||templateSource.length>65536||typeof targetSource!=='string'||targetSource.length>2*1024*1024
        ||typeof babelRoot!=='string'||!ROLES.every(r=>typeof functionNames?.[r]==='string')
        ||new Set(Object.values(functionNames)).size!==4||!Array.isArray(guardProofs)||!Array.isArray(contractionLedger))fail('invalid_composition_input');
    const parser=require(path.join(babelRoot,'@babel/parser'));
    const traverse=require(path.join(babelRoot,'@babel/traverse')).default;
    const target=parser.parse(targetSource,{sourceType:'script'}),template=parser.parse(templateSource,{sourceType:'script'});
    let program,reference;
    traverse(target,{Program(p){program=p;p.stop();}});traverse(template,{Program(p){reference=p;p.stop();}});
    const bindings=program.scope.bindings;
    for(const p of [program,reference]){
      if(['Math','String','Buffer'].some(n=>p.scope.bindings[n]))fail('global_intrinsic_shadowing');
    }
    for(const r of [...ROLES,...CONSTANTS,'createHash'])if(!reference.scope.bindings[r]||reference.scope.bindings[r].constantViolations.length)fail('reference_dependency_binding');
    for(const [ast,names]of [[template,ROLES],[target,Object.values(functionNames)]]){
      for(const name of names)if(ast.program.body.filter(n=>n.type==='FunctionDeclaration'&&n.id.name===name).length!==1)fail('ambiguous_function_declaration');
    }
    const ni=require('./bla_heap_noninterference.cjs').proveHeapNoninterference({source:targetSource,babelRoot,heapName,heapStepName,functionNames,heapProof});
    if(ni.status!=='proved'||!noninterferenceProof||canonical(ni)!==canonical(noninterferenceProof))fail('noninterference_not_source_bound');
    const map={...globalMap};
    if(Object.keys(map).length!==10||ROLES.some(r=>map[functionNames[r]]!==r)||map[cryptoBindingName]!=='createHash'||map[cipherName]!=='FLAG_CIPHER_HEX'
        ||new Set(Object.values(map)).size!==10||!CONSTANTS.every(r=>Object.values(map).includes(r)))fail('role_mapping_incomplete');
    function exportedBindings(ast){const out={};let assignments=0;
    for(const node of ast.program.body) {
      const e=node.type==='ExpressionStatement'&&node.expression;
      if(e?.type==='AssignmentExpression'&&e.operator==='='&&e.left.type==='MemberExpression'&&!e.left.computed
          &&e.left.object.name==='module'&&e.left.property.name==='exports') {
        if(++assignments!==1||e.right.type!=='ObjectExpression')fail('dynamic_exports');
        for(const p of e.right.properties){const key=p.key?.name||p.key?.value;if(p.type!=='ObjectProperty'||p.computed||p.value.type!=='Identifier'||Object.hasOwn(out,key))fail('dynamic_export_binding');out[key]=p.value.name;}
      }
    }if(assignments!==1)fail('missing_export_boundary');return out;}
    const exports=exportedBindings(target),referenceExports=exportedBindings(template);
    for(const role of ['sha256Hex','tryUnlock',...CONSTANTS.filter(r=>r!=='FLAG_CIPHER_HEX')])if(referenceExports[role]!==role)fail('reference_export_identity');
    if(exports.sha256Hex!==functionNames.sha256Hex||exports.tryUnlock!==functionNames.tryUnlock)fail('export_identity');
    for(const r of CONSTANTS.filter(x=>x!=='FLAG_CIPHER_HEX'))if(map[exports[r]]!==r)fail('constant_export_identity');
    for(const [name,role] of Object.entries(map)) {
      const b=bindings[name];if(!b||b.constantViolations.length)fail('mutable_or_missing_dependency');
      if(ROLES.includes(role)&&b.path.node.type!=='FunctionDeclaration')fail('function_dependency_kind');
      if(bindings[role]&&bindings[role]!==b)fail('canonical_global_collision');
    }
    const cryptoBinding=bindings[cryptoBindingName];
    if(cryptoBinding.path.node.type!=='VariableDeclarator'||cryptoBinding.path.node.id.type!=='ObjectPattern'
        ||!cryptoBinding.path.node.id.properties.some(p=>p.key?.name==='createHash'&&p.value?.name===cryptoBindingName)
        ||cryptoBinding.path.node.init?.type!=='CallExpression'||cryptoBinding.path.node.init.callee.name!=='require'
        ||cryptoBinding.path.node.init.arguments.length!==1||cryptoBinding.path.node.init.arguments[0].value!=='node:crypto')fail('crypto_import_contract');
    const rc=reference.scope.bindings.createHash.path.node;
    if(rc.type!=='VariableDeclarator'||rc.id.type!=='ObjectPattern'||!rc.id.properties.some(p=>p.key?.name==='createHash'&&p.value?.name==='createHash')
        ||rc.init?.type!=='CallExpression'||rc.init.callee.name!=='require'||rc.init.arguments.length!==1||rc.init.arguments[0].value!=='node:crypto')fail('reference_crypto_import_contract');
    const seed=bindings[seedName];
    if(!seed||seed.constantViolations.length)fail('mutable_guard_seed');
    const init=seed.path.node.init,left=init?.left,right=init?.right,test=right?.test;
    if(init?.type!=='BinaryExpression'||init.operator!=='|'||left?.type!=='BinaryExpression'||left.operator!=='&'
        ||left.right.type!=='NumericLiteral'||!Number.isSafeInteger(left.right.value)||(left.right.value&3)!==0
        ||right?.type!=='ConditionalExpression'||right.consequent.type!=='NumericLiteral'||right.consequent.value!==1
        ||right.alternate.type!=='NumericLiteral'||right.alternate.value!==0||test?.type!=='LogicalExpression'||test.operator!=='&&'
        ||test.left.type!=='BinaryExpression'||test.left.operator!=='==='||test.left.left.type!=='UnaryExpression'
        ||test.left.left.operator!=='typeof'||test.left.left.argument.type!=='Identifier'||test.left.right.type!=='StringLiteral'||test.left.right.value!=='function'
        ||test.right.type!=='BinaryExpression'||test.right.operator!=='==='||test.right.left.type!=='CallExpression'
        ||test.right.left.callee.name!==test.left.left.argument.name||test.right.left.arguments.length!==1
        ||test.right.left.arguments[0].type!=='NumericLiteral'||test.right.left.arguments[0].value!==0||test.right.right.type!=='NumericLiteral')fail('seed_invariant_shape');
    const corpusName=test.left.left.argument.name;
    if(!bindings[corpusName]||bindings[corpusName].constantViolations.length)fail('mutable_corpus_dependency');
    const reserved=new Set([...Object.values(map),seedName,'Math','String','Buffer']);
    for(const ast of [target,template])traverse(ast,{Identifier(p){if(/^__v\d+$/.test(p.node.name))fail('canonical_local_collision');}});
    program.traverse({ReferencedIdentifier(p){
      if(p.node.name==='Math'&&p.scope.getBinding('Math'))fail('intrinsic_shadowing');
      if(p.node.name===seedName&&p.scope.getBinding(seedName)!==seed)fail('seed_binding_identity');
    },Scopable(p){if(p.scope!==program.scope&&Object.keys(p.scope.bindings).some(n=>reserved.has(n)))fail('semantic_binding_shadowing');}});
    const proofs=[],ledger=[];
    const literal=n=>n&&['StringLiteral','NumericLiteral','BooleanLiteral','NullLiteral'].includes(n.type)?(n.type==='NullLiteral'?null:n.value):UNKNOWN;
    function seedBinary(n,op){return n?.type==='BinaryExpression'&&n.operator===op&&n.left.type==='Identifier'&&n.left.name===seedName
      &&n.right.type==='NumericLiteral'&&Number.isInteger(n.right.value)&&n.right.value>=0&&n.right.value<=0xffffffff?n.right.value:null;}
    function evaluate(n){
      const value=literal(n);if(value!==UNKNOWN)return value;
      if(n?.type==='BinaryExpression'&&n.operator==='+'){const a=evaluate(n.left),b=evaluate(n.right);if(a!==UNKNOWN&&b!==UNKNOWN&&(typeof a==='string'||typeof b==='string'))return a+b;}
      if(n?.type!=='BinaryExpression'||!['===','!=='].includes(n.operator)||n.right.type!=='NumericLiteral'||![0,1].includes(n.right.value))return UNKNOWN;
      const m=n.left,c=m?.left;if(m?.type!=='BinaryExpression'||m.operator!=='&'||m.right.type!=='NumericLiteral'||c?.type!=='CallExpression'
          ||c.arguments.length!==2||c.callee.type!=='MemberExpression'||c.callee.computed||c.callee.object.name!=='Math'||c.callee.property.name!=='imul')return UNKNOWN;
      let kind,constant,residues,out;
      const square=seedBinary(c.arguments[0],'^'),consecutive=seedBinary(c.arguments[0],'|');
      if(m.right.value===7&&square!==null&&square===seedBinary(c.arguments[1],'^')){
        kind='square_low_three_bits';constant=square;residues=[1,5];const values=residues.map(s=>Math.imul(s^constant,s^constant)&7);
        if(values[0]!==values[1])fail('guard_not_invariant');out=values[0];
      }else if(m.right.value===1&&consecutive!==null&&c.arguments[1].type==='BinaryExpression'&&c.arguments[1].operator==='+'
          &&c.arguments[1].right.value===1&&canonical(c.arguments[1].left)===canonical(c.arguments[0])){
        kind='consecutive_product_low_bit';constant=consecutive;residues=[0,1];out=0;
      }else return UNKNOWN;
      const reduced=n.operator==='==='?out===n.right.value:out!==n.right.value;
      proofs.push({kind,constant,mask:m.right.value,operator:n.operator,comparison:n.right.value,reduced,source_offsets:[n.start,n.end],
        source_region_sha256:sha(targetSource.slice(n.start,n.end)),proof:'Exhaustive relevant low-bit residues in the u32 modular ring',residues,
        assumptions:kind==='square_low_three_bits'?['seed & 3 == 1','standard Math.imul']:['standard Math.imul']});return reduced;
    }
    const lit=v=>({type:typeof v==='string'?'StringLiteral':typeof v==='boolean'?'BooleanLiteral':'NumericLiteral',value:v});
    traverse(target,{
      BinaryExpression:{exit(p){const v=evaluate(p.node);if(v!==UNKNOWN)p.replaceWith(lit(v));}},
      ConditionalExpression:{exit(p){const v=literal(p.node.test);if(typeof v==='boolean'){ledger.push({kind:'pure_conditional',source_offsets:[p.node.start,p.node.end]});p.replaceWith(v?p.node.consequent:p.node.alternate);}}},
      IfStatement:{exit(p){const v=literal(p.node.test);if(typeof v!=='boolean')return;let declarations=false;
        p.traverse({VariableDeclaration(){declarations=true;},FunctionDeclaration(){declarations=true;},ClassDeclaration(){declarations=true;}});if(declarations)fail('guard_declaration_scope');
        ledger.push({kind:'pure_guard',source_offsets:[p.node.start,p.node.end],taken:v});const selected=v?p.node.consequent:p.node.alternate;
        if(!selected)p.remove();else if(selected.type==='BlockStatement')p.replaceWithMultiple(selected.body);else p.replaceWith(selected);}},
    });
    if(canonical(proofs)!==canonical(guardProofs))fail('guard_evidence_mismatch');
    program.scope.crawl();
    const constants={};
    for(const role of CONSTANTS.filter(r=>r!=='LICENSE_RPC')){
      const name=Object.keys(map).find(n=>map[n]===role),v=evaluate(program.scope.bindings[name]?.path.node.init);
      if(typeof v!=='string')fail('constant_not_literal');constants['%%'+role+'%%']=v;
    }
    traverse(template,{StringLiteral(p){if(Object.hasOwn(constants,p.node.value))p.node.value=constants[p.node.value];}});
    const constantResults=CONSTANTS.map(role=>{
      const name=Object.keys(map).find(n=>map[n]===role),a=reference.scope.bindings[role]?.path.node.init,b=program.scope.bindings[name]?.path.node.init;
      if(!a||!b||canonical(a)!==canonical(b))fail('constant_dependency_difference');return {role,ast_sha256:sha(canonical(a))};
    });
    const callsExpected=new Map(ni.selected_calls.map(c=>[c.source_offsets.join(':'),c]));
    let removed=0;
    traverse(target,{CallExpression(p){if(p.node.callee.type==='Identifier'&&p.node.callee.name===heapStepName&&ROLES.some(r=>functionNames[r]===p.getFunctionParent()?.node.id?.name)){
      const key=[p.node.start,p.node.end].join(':'),c=callsExpected.get(key);
      if(!c||!p.parentPath.isExpressionStatement()||p.node.arguments.length!==1||p.node.arguments[0].type!=='NumericLiteral'||!Number.isSafeInteger(p.node.arguments[0].value))fail('heap_stutter_site_mismatch');
      ledger.push({kind:'private_heap_step',source_offsets:[p.node.start,p.node.end],argument_count:1});callsExpected.delete(key);removed++;p.parentPath.remove();
    }}});
    if(callsExpected.size||removed===0||canonical(ledger)!==canonical(contractionLedger))fail('contraction_evidence_mismatch');
    program.scope.crawl();for(const [name,role]of Object.entries(map))if(name!==role)program.scope.rename(name,role);
    function normalize(ast){traverse(ast,{FunctionDeclaration(p){if(!ROLES.includes(p.node.id.name))return;p.scope.crawl();const owned=new Set(Object.values(p.scope.bindings));
      p.traverse({Scopable(q){for(const b of Object.values(q.scope.bindings))owned.add(b);}});
      [...owned].filter(b=>!Object.values(map).includes(b.identifier.name)).sort((a,b)=>a.identifier.start-b.identifier.start)
        .forEach((b,i)=>b.scope.rename(b.identifier.name,'__v'+i));
    }});}
    normalize(template);normalize(target);
    const functionResults=[];
    for(const role of ROLES){const a=template.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===role),b=target.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===role);
      if(!a||!b||canonical(a)!==canonical(b))fail('complete_function_difference');functionResults.push({role,normalized_ast_sha256:sha(canonical(a)),rule:'AST congruence after justified guard rewrites and silent private-step erasure'});}
    // Typed call contracts are checked over both identical bodies. They exclude
    // unresolved global reads, arbitrary method receivers and callback coercion.
    const callGraph=Object.fromEntries(ROLES.map(r=>[r,[]])),leafSites=[],decoderLoops=[],returns={sha256Hex:'string',deriveFlagMask:'buffer',decodeFlagCipher:'string',tryUnlock:'string_or_null'};
    const globals=new Map(CONSTANTS.map(r=>[r,r==='LICENSE_RPC'?'license':'string']));
    function checkFunction(fn){
      if(fn.params.length!==1||fn.params[0].type!=='Identifier'||fn.async||fn.generator)fail('unsupported_callable_boundary');
      const env=new Map(globals),parameter=fn.params[0].name;env.set(parameter,fn.id.name==='sha256Hex'?'primitive':fn.id.name==='tryUnlock'?'any':'string');
      const site=(op,n,receiver,result)=>leafSites.push({function:fn.id.name,operation:op,receiver,result,source:'reference_template',source_offsets:[n.start,n.end]});
      const isNum=t=>['number','byte_or_undefined'].includes(t);
      function expression(n){
        if(n.type==='StringLiteral')return 'string';if(n.type==='NumericLiteral')return 'number';if(n.type==='BooleanLiteral')return 'boolean';if(n.type==='NullLiteral')return 'null';
        if(n.type==='Identifier'){if(!env.has(n.name))fail('unresolved_reference');return env.get(n.name);}
        if(n.type==='TemplateLiteral'){for(const x of n.expressions)if(!['string','number','primitive','boolean','null'].includes(expression(x)))fail('effectful_template_coercion');return 'string';}
        if(n.type==='UnaryExpression'){const t=expression(n.argument);if(n.operator==='typeof')return 'string';if(n.operator==='!'&&t==='boolean')return 'boolean';fail('unsupported_typed_unary');}
        if(n.type==='BinaryExpression'){const a=expression(n.left),b=expression(n.right);
          if(['===','!=='].includes(n.operator))return 'boolean';if(['<','>','<=','>='].includes(n.operator)&&isNum(a)&&isNum(b))return 'boolean';
          if(['^','|','&','%','+','-'].includes(n.operator)&&isNum(a)&&isNum(b))return 'number';if(n.operator==='+'&&a==='string'&&b==='string')return 'string';fail('unsupported_typed_binary');}
        if(n.type==='LogicalExpression'){if(!['&&','||'].includes(n.operator)||expression(n.left)!=='boolean'||expression(n.right)!=='boolean')fail('unsupported_logical_coercion');return 'boolean';}
        if(n.type==='MemberExpression'){
          const t=expression(n.object);if(n.computed){if(t!=='buffer'||!isNum(expression(n.property)))fail('unresolved_index_receiver');return 'byte_or_undefined';}
          if(n.property.name==='length'&&['buffer','string'].includes(t))return 'number';
          if(t==='license'&&n.property.name==='verifyEntitlement')return 'string';fail('unresolved_property_read');
        }
        if(n.type==='CallExpression'){
          const c=n.callee;if(n.optional||n.arguments.some(x=>x.type==='SpreadElement'))fail('unsupported_call_form');
          if(c.type==='Identifier'){
            if(ROLES.includes(c.name)){if(n.arguments.length!==1||expression(n.arguments[0])!=='string')fail('helper_input_contract');callGraph[fn.id.name].push(c.name);return returns[c.name];}
            if(c.name==='String'){if(n.arguments.length!==1||!['primitive','string','number','boolean','null'].includes(expression(n.arguments[0])))fail('String_callback_coercion');site('String',n,'primitive','string');return 'string';}
            if(c.name==='createHash'){if(n.arguments.length!==1||n.arguments[0].type!=='StringLiteral'||n.arguments[0].value!=='sha256')fail('hash_algorithm_contract');site('crypto.createHash',n,'provider','hash');return 'hash';}
            fail('unresolved_direct_call');
          }
          if(c.type!=='MemberExpression'||c.computed||c.optional)fail('unresolved_method_form');
          const method=c.property.name;
          if(c.object.type==='Identifier'&&c.object.name==='Buffer'){
            if(method==='from'&&n.arguments.length===2&&expression(n.arguments[0])==='string'&&n.arguments[1].value==='hex'){site('Buffer.from',n,'provider','buffer');return 'buffer';}
            if(method==='alloc'&&n.arguments.length===1&&isNum(expression(n.arguments[0]))){site('Buffer.alloc',n,'provider','buffer');return 'buffer';}fail('Buffer_leaf_contract');
          }
          const receiver=expression(c.object);
          if(receiver==='hash'&&method==='update'&&n.arguments.length===2&&expression(n.arguments[0])==='string'&&n.arguments[1].value==='utf8'){site('hash.update',n,'hash','hash');return 'hash';}
          if(receiver==='hash'&&method==='digest'&&(n.arguments.length===0||(n.arguments.length===1&&n.arguments[0].value==='hex'))){const result=n.arguments.length?'string':'buffer';site('hash.digest',n,'hash',result);return result;}
          if(receiver==='buffer'&&method==='toString'&&n.arguments.length===1&&n.arguments[0].value==='utf8'){site('buffer.toString',n,'buffer','string');return 'string';}
          if(receiver==='string'&&['startsWith','endsWith'].includes(method)&&n.arguments.length===1&&expression(n.arguments[0])==='string'){site('string.'+method,n,'string','boolean');return 'boolean';}
          fail('method_receiver_contract');
        }
        fail('unsupported_typed_expression');
      }
      let returnCount=0;
      function statements(body,inLoop=false){for(let index=0;index<body.length;index++){const n=body[index];
        if(n.type==='VariableDeclaration'){
          if(n.kind!=='const')fail('unsupported_local_mutation');for(const d of n.declarations){if(d.id.type!=='Identifier'||env.has(d.id.name)||!d.init)fail('typed_binding_collision');env.set(d.id.name,expression(d.init));}
        }else if(n.type==='IfStatement'){
          if(fn.id.name!=='tryUnlock'||inLoop||n.alternate||expression(n.test)!=='boolean'||n.consequent.type!=='ReturnStatement'||n.consequent.argument?.type!=='NullLiteral')fail('unsupported_function_branch');
          returnCount++;
          if(fn.id.name==='tryUnlock'&&index===0){const t=n.test;if(t.type!=='BinaryExpression'||t.operator!=='!=='||t.left.type!=='UnaryExpression'||t.left.operator!=='typeof'||t.left.argument.name!==parameter||t.right.value!=='string')fail('input_string_gate');env.set(parameter,'string');}
        }else if(n.type==='ForStatement'){
          const d=n.init?.declarations?.[0],test=n.test,up=n.update;
          if(inLoop||n.init?.type!=='VariableDeclaration'||n.init.kind!=='let'||n.init.declarations.length!==1||d.id.type!=='Identifier'||env.has(d.id.name)||d.init?.value!==0
              ||test?.type!=='BinaryExpression'||test.operator!=='<'||test.left.name!==d.id.name||test.right.type!=='MemberExpression'||test.right.computed||test.right.property.name!=='length'
              ||up?.type!=='UpdateExpression'||up.operator!=='++'||up.argument.name!==d.id.name||n.body.type!=='BlockStatement'||expression(test.right)!=='number'
              ||expression(test.right.object)!=='buffer')fail('decoder_loop_contract');
          env.set(d.id.name,'number');statements(n.body.body,true);env.delete(d.id.name);
          decoderLoops.push({function:fn.id.name,source:'reference_template',source_offsets:[n.start,n.end],ranking_function:'buffer.length - counter',
            counter_start:0,decrease:1,bound:'Finite immutable safe-integer length of a related fresh Buffer',
            body_effects:'Only numeric indexed Buffer writes; no counter, reference or length reassignment'});
        }else if(n.type==='ExpressionStatement'&&n.expression.type==='AssignmentExpression'){
          const a=n.expression;if(!inLoop||a.operator!=='='||a.left.type!=='MemberExpression'||!a.left.computed||expression(a.left.object)!=='buffer'||!isNum(expression(a.left.property))||!isNum(expression(a.right)))fail('external_or_untyped_write');
        }else if(n.type==='ReturnStatement'){
          if(inLoop||index!==body.length-1)fail('unsupported_early_return');const t=expression(n.argument);if(t!==returns[fn.id.name]&&!(returns[fn.id.name]==='string_or_null'&&t==='string'))fail('return_contract');returnCount++;
        }else fail('unsupported_typed_statement');
      }}
      statements(fn.body.body);if(!returnCount||fn.body.body.at(-1)?.type!=='ReturnStatement')fail('missing_function_return');
      if(fn.id.name==='tryUnlock'&&env.get(parameter)!=='string')fail('missing_string_gate');
    }
    for(const role of ROLES)checkFunction(template.program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name===role));
    const license=reference.scope.bindings.LICENSE_RPC.path.node.init;
    const licenseKeys=license.type==='ObjectExpression'?license.properties.map(p=>p.key?.name||p.key?.value):[];
    if(license.type!=='ObjectExpression'||new Set(licenseKeys).size!==licenseKeys.length||licenseKeys.some(k=>['__proto__','constructor','prototype'].includes(k))
        ||license.properties.some(p=>p.type!=='ObjectProperty'||p.computed||p.method||p.value.type!=='StringLiteral')
        ||!license.properties.some(p=>(p.key.name||p.key.value)==='verifyEntitlement'))fail('public_data_contract');
    const visited=new Set(),active=new Set(),order=[];
    function visit(r){if(active.has(r))fail('recursive_call_contract');if(visited.has(r))return;active.add(r);for(const c of callGraph[r])visit(c);active.delete(r);visited.add(r);order.push(r);}
    for(const r of ROLES)visit(r);
    const result={format:'fdisbull-whole-function-equivalence-1',status:'equivalent_under_contract',
      method:'Source-replayed guard/literal rewrites, private stuttering noninterference, typed leaf-call congruence and acyclic helper composition',
      source:{template_sha256:sha(templateSource),target_sha256:sha(targetSource)},
      noninterference_certificate_sha256:ni.certificate_sha256,guard_ledger_sha256:sha(canonical(proofs)),contraction_ledger_sha256:sha(canonical(ledger)),
      checked_reductions:{opaque_guards:proofs.length,private_stuttering_calls:removed},
      seed_invariant:{immutable:true,low_two_bits:1,rule:'Initialization masks low two bits clear and ORs 1 when the intact-corpus commitment predicate holds',
        condition:'Source corpus callback at initialization returns its embedded expected digest',source:'target',source_offsets:[init.start,init.end]},
      functions:functionResults,constants:constantResults,call_graph:callGraph,composition_order:order,leaf_sites:leafSites,decoder_loops:decoderLoops,
      rules:['Pure total guard/literal rewrite preserves low transition','Total private step is silent and low-state framing; discarded result permits stuttering erasure',
        'Identical typed JS ASTs preserve related primitive/local values and fresh heap graphs',
        'Coupled typed external calls preserve related provider state on normal return and on matching throw, with related values/bytes or equal exception name/message',
        'Acyclic callee contracts substitute into caller bodies, including matching exception propagation',
        'Related public/provider state and preserved private invariants support induction over finite admitted call sequences, including calls after a caught exception'],
      observations:['Return primitive value','Exception name and message','Ordered admitted provider operations and primitive/byte arguments',
        'Related reachable public ordinary data and fresh Buffer/hash typestate'],
      input_domains:{sha256Hex:'ECMAScript primitive values, including undefined/null/boolean/number/bigint/symbol/string',
        tryUnlock:'Any input value; nonstrings return null through the checked type gate before coercion or provider calls',deriveFlagMask:'string',decodeFlagCipher:'string'},
      leaf_contract:{provider:'Coupled total synchronous SHA-256 and Buffer providers on related receiver typestates and identical primitive/byte arguments',
        outcomes:'Provider states remain related on both normal return and matching throw; results are related fresh Buffer/hash graphs and equal primitives, or equal exception name/message; hash.digest() yields 32 bytes and digest(hex) 64 characters; Buffer lengths are finite immutable safe integers',
        preservation:'No callbacks/reentry, stack/source/name/caller inspection, private-state access, public-data mutation or intrinsic/prototype mutation'},
      public_state_contract:'Matching ordinary writable own-data constants; exported LICENSE_RPC string properties remain related string data properties across admitted calls',
      remaining_conditions:['Intact corpus commitment at initialization and immutable selected dependency bindings','Stable standard Math.imul, String and object/array/Buffer semantics',
        'Primitive sha256Hex inputs; no hostile coercion callbacks','Coupled total synchronous typed provider contract and related ordinary public data',
        'No source/name/reflection, exception-stack, timing/resource or concurrent observer'],
      claim:'Whole selected function observation equivalence for all admitted inputs and related entry states; not unrestricted JS contextual or whole-module equivalence',
      full_state_equivalence:false,finite_runtime_checks_are_not_proof:true};
    result.certificate_sha256=sha(canonical(result));return result;
  }catch(error){return {format:'fdisbull-whole-function-equivalence-1',status:'unknown',reason:error instanceof Error&&/^[a-z][a-z0-9_]{0,80}$/.test(error.message)?error.message:'composition_failure'};}
}
module.exports={composeFunctionEquivalence};
