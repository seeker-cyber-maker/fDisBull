'use strict';
/** A deliberately small total-correctness checker for ordinary numeric heaps.
 * It interprets source ASTs over an inductive range/schema domain. No target
 * is executed, and no source digest is accepted as a substitute for checking.
 */
const crypto = require('node:crypto');
const path = require('node:path');
const U31 = 0x7fffffff, I32_MIN = -0x80000000, SAFE = Number.MAX_SAFE_INTEGER;
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const fail = reason => {throw new Error(reason);};
const number = (lo, hi = lo) => {
  if (!Number.isSafeInteger(lo) || !Number.isSafeInteger(hi) || lo > hi) fail('non_exact_numeric_range');
  return {kind:'number',minimum:lo,maximum:hi,integer:true};
};
const ref = nodes => ({kind:'reference',nodes});
const numeric = x => {if (x?.kind !== 'number') fail('numeric_operand_required');return x;};
const int32 = x => {
  numeric(x);
  if (x.minimum === x.maximum) return number(x.minimum | 0);
  return x.minimum >= I32_MIN && x.maximum <= U31 ? x : number(I32_MIN,U31);
};
const range = x => [x.minimum,x.maximum];
const keyOf = node => {
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'StringLiteral') return node.value;
  fail('unsupported_property_key');
};

function proveShadowHeap({functionNode, heapInitializerNode, heapName, source, babelRoot} = {}) {
  const certificate = {format:'fdisbull-shadow-heap-proof-1',status:'unknown'};
  try {
    if (typeof source !== 'string' || source.length > 2*1024*1024 || typeof heapName !== 'string'
        || functionNode?.type !== 'FunctionDeclaration' || functionNode.async || functionNode.generator
        || functionNode.params.length !== 1 || functionNode.params[0].type !== 'Identifier'
        || functionNode.params[0].name === heapName || functionNode.params[0].name === 'Math'
        || !functionNode.id || ['Math',heapName].includes(functionNode.id.name)
        || typeof babelRoot!=='string') fail('unsupported_function_boundary');
    const parser=require(path.join(babelRoot,'@babel/parser'));
    const traverse=require(path.join(babelRoot,'@babel/traverse')).default;
    const ast=parser.parse(source,{sourceType:'script'});
    const metadata=new Set(['start','end','loc','extra','leadingComments','trailingComments','innerComments','comments','tokens']);
    const canon=value=>{
      if (Array.isArray(value)) return value.map(canon);
      if (!value || typeof value!=='object') return value;
      const out={};for(const key of Object.keys(value).sort()) if(!metadata.has(key)) out[key]=canon(value[key]);return out;
    };
    let functionPath,heapBinding;
    traverse(ast,{FunctionDeclaration(p){
      if(p.node.start===functionNode.start && p.node.end===functionNode.end) functionPath=p;
    }});
    if (!functionPath || !functionPath.parentPath.isProgram()
        || JSON.stringify(canon(functionPath.node))!==JSON.stringify(canon(functionNode))) fail('source_ast_identity');
    heapBinding=functionPath.scope.getBinding(heapName);
    const initializer=heapBinding?.path.node.init;
    if (!heapBinding || !heapBinding.scope.path.isProgram() || !initializer
        || initializer.start!==heapInitializerNode?.start || initializer.end!==heapInitializerNode?.end
        || JSON.stringify(canon(initializer))!==JSON.stringify(canon(heapInitializerNode))) fail('source_heap_identity');
    functionPath.traverse({ReferencedIdentifier(p){
      if ((p.node.name==='Math' && p.scope.getBinding('Math'))
          || (p.node.name===heapName && p.scope.getBinding(heapName)!==heapBinding)) fail('source_binding_identity');
    }});
    let schemaNodes = 0;
    function schema(node, depth = 0) {
      if (++schemaNodes > 20000 || depth > 20) fail('schema_budget');
      if (node?.type === 'NumericLiteral') {
        if (!Number.isInteger(node.value) || node.value < 0 || node.value > U31) fail('initial_numeric_invariant');
        return number(0,U31);
      }
      if (node?.type === 'StringLiteral') return {kind:'string'};
      if (node?.type === 'ArrayExpression') {
        if (node.elements.length > 1024 || node.elements.some(x=>!x)) fail('array_extent_or_hole');
        return {kind:'array',length:node.elements.length,elements:node.elements.map(x=>schema(x,depth+1))};
      }
      if (node?.type === 'ObjectExpression') {
        const properties = Object.create(null);
        for (const p of node.properties) {
          if (p.type !== 'ObjectProperty' || p.computed || p.method || p.shorthand) fail('non_literal_own_data');
          const k=keyOf(p.key);
          if (['__proto__','prototype','constructor'].includes(k) || Object.hasOwn(properties,k)) fail('ambiguous_initial_property');
          properties[k]=schema(p.value,depth+1);
        }
        return {kind:'object',properties};
      }
      fail('non_literal_heap_graph');
    }
    const heap=schema(heapInitializerNode);
    const exactKeys=(object,expected)=>object?.kind==='object' && JSON.stringify(Object.keys(object.properties).sort())===JSON.stringify([...expected].sort());
    if (!exactKeys(heap,['cursor','tick','rollingMask','splitShareA','splitShareB','slots','diffEnvelope'])) fail('unsupported_root_schema');
    const h=heap.properties, slots=h.slots, a=h.splitShareA, b=h.splitShareB, envelope=h.diffEnvelope;
    if (slots.kind!=='array' || slots.length<8 || a.kind!=='array' || a.length<1 || b.kind!=='array'
        || a.length!==b.length || a.elements.some(x=>x.kind!=='number') || b.elements.some(x=>x.kind!=='number')
        || envelope.kind!=='object') fail('unsupported_array_geometry');
    if (slots.elements.some(s=>!exactKeys(s,['slotId','kind','epoch','words','hmacTag'])
        || s.properties.kind.kind!=='string' || ['slotId','epoch','hmacTag'].some(k=>s.properties[k].kind!=='number')
        || s.properties.words.kind!=='array' || s.properties.words.length!==4 || s.properties.words.elements.some(x=>x.kind!=='number')))
      fail('unsupported_slot_schema');
    const frontiers=Object.keys(envelope.properties);
    if (!frontiers.length || frontiers.length>128 || frontiers.some((k,i)=>k!=='state_diff_frontier_'+i || envelope.properties[k].kind!=='number')) fail('unsupported_frontier_schema');
    if (['tick','rollingMask','cursor'].some(k=>h[k].kind!=='number')) fail('unsupported_numeric_schema');
    const cursor=heapInitializerNode.properties.find(p=>keyOf(p.key)==='cursor').value.value;
    if (!Number.isInteger(cursor) || cursor<0 || cursor>=slots.length) fail('initial_cursor_invariant');
    h.cursor=number(0,slots.length-1);

    const env=new Map([[heapName,ref([heap])],[functionNode.params[0].name,number(-SAFE,SAFE)]]);
    const declared=new Set(env.keys()), obligations=[], loops=[];
    let visits=0, maxWrites=0, returns=0;
    const note=(kind,node,details)=>obligations.push({kind,source_offsets:[node.start,node.end],...details});
    const join=values=>{
      if (!values.length) fail('empty_reference');
      if (values.every(v=>v.kind==='number')) return number(Math.min(...values.map(v=>v.minimum)),Math.max(...values.map(v=>v.maximum)));
      if (values.every(v=>v.kind==='object' || v.kind==='array')) return ref([...new Set(values)]);
      if (values.every(v=>v.kind==='string')) return {kind:'string'};
      fail('incompatible_reference_types');
    };
    function members(node, local) {
      if (node.type!=='MemberExpression' || node.optional) fail('unsupported_reference');
      const object=expr(node.object,local);
      if (object.kind!=='reference') fail('own_data_reference_required');
      const index=node.computed ? numeric(expr(node.property,local)) : null;
      const values=[];
      for (const obj of object.nodes) {
        if (obj.kind==='array') {
          if (!node.computed && node.property.type==='Identifier' && node.property.name==='length') {
            values.push({lengthCell:true,...number(obj.length)});continue;
          }
          if (!index || index.minimum<0 || index.maximum>=obj.length) fail('array_access_not_bounded');
          note('bounded_array_access',node,{index:range(index),length:obj.length});
          values.push(...obj.elements.slice(index.minimum,index.maximum+1));
        } else {
          if (node.computed || node.property.type!=='Identifier' || !Object.hasOwn(obj.properties,node.property.name)) fail('property_not_own_data');
          values.push(obj.properties[node.property.name]);
        }
      }
      return values;
    }
    function expr(node, local, depth=0) {
      if (++visits>50000 || depth>100 || !node) fail('expression_budget');
      if (node.type==='NumericLiteral') return number(node.value);
      if (node.type==='BooleanLiteral') return {kind:'boolean',value:node.value};
      if (node.type==='Identifier') {
        if (!local.has(node.name)) fail('external_binding');return local.get(node.name);
      }
      if (node.type==='MemberExpression') return join(members(node,local));
      if (node.type==='UnaryExpression') {
        const x=expr(node.argument,local,depth+1);
        if (node.operator==='!' && x.kind==='reference') return {kind:'boolean',value:false};
        if (node.operator==='-' && x.kind==='number') return number(-x.maximum,-x.minimum);
        if (node.operator==='~') {int32(x);return number(I32_MIN,U31);}
        fail('unsupported_unary_operation');
      }
      if (node.type==='CallExpression') {
        const c=node.callee;
        if (node.optional || c.type!=='MemberExpression' || c.computed || c.object.type!=='Identifier' || c.object.name!=='Math'
            || local.has('Math') || c.property.name!=='imul' || node.arguments.length!==2) fail('unsupported_call');
        for (const x of node.arguments) numeric(expr(x,local,depth+1));
        note('standard_imul_i32',node,{result:[I32_MIN,U31]});return number(I32_MIN,U31);
      }
      if (node.type==='BinaryExpression') {
        const l=numeric(expr(node.left,local,depth+1)), r=numeric(expr(node.right,local,depth+1));
        if (node.operator==='+' || node.operator==='-') {
          const v=node.operator==='+' ? number(l.minimum+r.minimum,l.maximum+r.maximum) : number(l.minimum-r.maximum,l.maximum-r.minimum);
          note('exact_integer_arithmetic',node,{operator:node.operator,left:range(l),right:range(r),result:range(v)});return v;
        }
        if (node.operator==='%') {
          if (l.minimum<0 || r.minimum!==r.maximum || r.minimum<=0) fail('remainder_precondition');
          const v=number(0,Math.min(l.maximum,r.minimum-1));
          note('nonnegative_remainder',node,{dividend:range(l),divisor:r.minimum,result:range(v)});return v;
        }
        if (['&','^','|'].includes(node.operator)) {
          const x=int32(l),y=int32(r);
          let v=number(I32_MIN,U31);
          if (node.operator==='&' && (x.minimum>=0 || y.minimum>=0)) {
            const upper=Math.min(x.minimum>=0?x.maximum:U31,y.minimum>=0?y.maximum:U31);v=number(0,upper);
          } else if (x.minimum>=0 && y.minimum>=0) {
            const maximum=Math.max(x.maximum,y.maximum);
            const bits=maximum===0?0:32-Math.clz32(maximum);v=number(0,2**bits-1);
          }
          note('i32_bitwise_range',node,{operator:node.operator,left:range(x),right:range(y),result:range(v)});return v;
        }
        if (['>>>','>>','<<'].includes(node.operator)) {
          if (r.minimum!==r.maximum || r.minimum<0 || r.minimum>31) fail('unsupported_shift_count');
          const x=int32(l),n=r.minimum;
          const v=node.operator==='>>>' ? number(0, Math.floor((x.minimum>=0?x.maximum:0xffffffff)/2**n))
            : node.operator==='>>' ? number(Math.floor(x.minimum/2**n),Math.floor(x.maximum/2**n)) : number(I32_MIN,U31);
          note('i32_shift_range',node,{operator:node.operator,shift:n,input:range(x),result:range(v)});return v;
        }
        fail('unsupported_binary_operation');
      }
      fail('unsupported_expression');
    }
    function block(statements,local,multiplier=1,inLoop=false) {
      for (let at=0;at<statements.length;at++) {
        const node=statements[at];
        if (node.type==='VariableDeclaration') {
          if (node.kind!=='const') fail('mutable_local_outside_loop_control');
          for (const d of node.declarations) {
            if (d.id.type!=='Identifier' || declared.has(d.id.name) || d.id.name==='Math' || !d.init) fail('local_binding_collision');
            const value=expr(d.init,local);declared.add(d.id.name);local.set(d.id.name,value);
          }
        } else if (node.type==='ExpressionStatement' && node.expression.type==='AssignmentExpression') {
          const assign=node.expression;
          if (assign.operator!=='=' || assign.left.type!=='MemberExpression') fail('unsupported_write');
          const targets=members(assign.left,local),value=numeric(expr(assign.right,local));
          if (targets.some(t=>t.kind!=='number' || t.lengthCell || value.minimum<t.minimum || value.maximum>t.maximum)) fail('write_breaks_inductive_invariant');
          note('invariant_preserving_numeric_write',assign,{value:range(value),target:range(targets[0]),possible_cells:targets.length,executions:multiplier});maxWrites+=multiplier;
        } else if (node.type==='IfStatement') {
          const test=expr(node.test,local);
          if (test.kind!=='boolean' || test.value!==false || node.alternate
              || node.test.type!=='UnaryExpression' || node.test.operator!=='!'
              || node.test.argument.type!=='Identifier' || node.test.argument.name!==heapName
              || node.consequent.type!=='ReturnStatement' || node.consequent.argument?.type!=='NumericLiteral'
              || node.consequent.argument.value!==0) fail('unsupported_control_guard');
          note('unreachable_null_guard',node,{entry_heap_nonnull:true});
        } else if (node.type==='ForStatement') {
          if (inLoop || node.init?.type!=='VariableDeclaration' || node.init.kind!=='let' || node.init.declarations.length!==1) fail('unsupported_loop');
          const d=node.init.declarations[0], test=node.test, update=node.update;
          if (d.id.type!=='Identifier' || declared.has(d.id.name) || d.id.name==='Math' || d.init?.type!=='NumericLiteral' || d.init.value!==0
              || test?.type!=='BinaryExpression' || test.operator!=='<' || test.left.type!=='Identifier' || test.left.name!==d.id.name
              || update?.type!=='UpdateExpression' || update.operator!=='++' || update.argument.type!=='Identifier' || update.argument.name!==d.id.name
              || node.body.type!=='BlockStatement') fail('unsupported_loop_control');
          const bound=numeric(expr(test.right,local));
          if (bound.minimum!==bound.maximum || bound.minimum<1 || bound.maximum>1024) fail('nonconstant_loop_bound');
          const name=d.id.name,inner=new Map(local);declared.add(name);inner.set(name,number(0,bound.maximum-1));
          const before=maxWrites;block(node.body.body,inner,multiplier*bound.maximum,true);
          const loop={source_offsets:[node.start,node.end],iterations:bound.maximum,counter_range:[0,bound.maximum],
            ranking_function:'bound - counter',initial_rank:bound.maximum,decrease:1,exit_rank:0,
            body_numeric_writes:(maxWrites-before)/multiplier,bound_and_counter_immutable_in_body:true};
          loops.push(loop);note('loop_induction_and_rank',node,loop);
        } else if (node.type==='ReturnStatement') {
          if (inLoop || at!==statements.length-1) fail('unsupported_early_return');
          const value=numeric(expr(node.argument,local));note('numeric_return',node,{range:range(value)});returns++;
        } else fail('unsupported_statement');
      }
    }
    block(functionNode.body.body,new Map(env));
    if (returns!==1) fail('missing_total_return');
    certificate.status='proved';
    certificate.method='Source-AST range/schema induction with natural-number loop ranks';
    certificate.source={sha256:sha(source),mutator_offsets:[functionNode.start,functionNode.end],
      mutator_sha256:sha(source.slice(functionNode.start,functionNode.end)),ast_identity_verified:true};
    certificate.invariant={schema:heap,geometry:{slots:slots.length,share_length:a.length,frontier_fields:frontiers.length},
      initialized:true,preserved:true,ordinary_disjoint_own_data_graph:true,arrays_and_object_schema_unchanged:true,
      numeric_leaves:'u31 integers; cursor additionally less than slots.length',delta:'Any safe-integer Number; actual call arguments checked by caller'};
    certificate.termination={proved:true,loops,max_loop_iterations:loops.reduce((n,l)=>n+l.iterations,0),
      recursion:false,unbounded_control:false,normal_numeric_return:true};
    certificate.mutation={max_numeric_writes:maxWrites,external_effects:false,reference_or_length_writes:false};
    certificate.obligations=obligations;
    certificate.discharged_assumptions=['Private numeric heap shape preservation','Mutator termination and absence of language-level exceptions under the entry contract'];
    certificate.remaining_assumptions=['Standard unmodified Math.imul and ordinary built-in object/array semantics',
      'Private ordinary mutable own-data heap has no external aliases, proxies, getters or concurrent observers',
      'ECMAScript Number/bitwise semantics; no resource exhaustion or timing observer'];
    certificate.certificate_sha256=sha(JSON.stringify(certificate));
  } catch (error) {
    // Parser/loader diagnostics can contain source fragments; retain fixed proof
    // reason codes only, never raw exceptions from dependencies or supplied ASTs.
    const reason=error instanceof Error && /^[a-z][a-z0-9_]{0,80}$/.test(error.message) ? error.message : 'proof_failure';
    return {format:certificate.format,status:'unknown',reason};
  }
  return certificate;
}

function checkHeapInvariant(heap,certificate) {
  try {
    if (certificate?.status!=='proved' || !certificate.invariant?.schema) return false;
    const seen=new Set();
    function check(value,schema) {
      if (schema.kind==='number') return Number.isSafeInteger(value) && value>=schema.minimum && value<=schema.maximum;
      if (schema.kind==='string') return typeof value==='string';
      if (!value || typeof value!=='object' || seen.has(value)) return false;
      seen.add(value);
      const descriptors=Object.getOwnPropertyDescriptors(value),symbols=Object.getOwnPropertySymbols(value);
      if (symbols.length) return false;
      if (schema.kind==='array') {
        if (!Array.isArray(value) || value.length!==schema.length || Object.keys(descriptors).length!==schema.length+1) return false;
        if (!descriptors.length || !Object.hasOwn(descriptors.length,'value') || descriptors.length.writable!==true) return false;
        return schema.elements.every((s,i)=>{
          const d=descriptors[i];return d && Object.hasOwn(d,'value') && d.writable && d.enumerable && d.configurable && check(d.value,s);
        });
      }
      if (schema.kind!=='object' || Array.isArray(value)) return false;
      const expected=Object.keys(schema.properties);
      return Object.keys(descriptors).length===expected.length && expected.every(k=>{
        const d=descriptors[k];return d && Object.hasOwn(d,'value') && d.writable && d.enumerable && d.configurable && check(d.value,schema.properties[k]);
      });
    }
    return check(heap,certificate.invariant.schema);
  } catch (_) {return false;}
}

module.exports={proveShadowHeap,checkHeapInvariant};
