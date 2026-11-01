"""Standalone Python/JavaScript realizations of the indexed common UIL.

The compiler emits real functions, expressions, branches and bounded loops.
Only typed values and descriptors are retained as data in the generated source;
no UIL AST, decoder, fDisBull import or runtime AST interpreter is embedded.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path


FORMAT = 'fdisbull-common-uil-udc-1'
MAX_STEPS = 4_000_000


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


_PYTHON_RUNTIME = r'''import copy
import hashlib
import json
import re
import sys

class Refused(Exception):
    pass

def owned(value):
    return copy.deepcopy(value)

def trace_values(values):
    result = []; cells = 0
    for value in values:
        if type(value) is list and len(value) > TRACE_LIMITS['array_inline']:
            raw = json.dumps(value,separators=(',',':')).encode('utf-8')
            result.append({'kind':'array-summary','length':len(value),'sha256':hashlib.sha256(raw).hexdigest()})
            cells += 4
        elif type(value) is str and len(value.encode('utf-8')) > TRACE_LIMITS['text_inline_bytes']:
            raw = value.encode('utf-8')
            result.append({'kind':'text-summary','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
            cells += 4
        else:
            result.append(owned(value))
            cells += max(1,len(value)) if type(value) is list else 1
    return result,cells

def typed(value, desc):
    typ = desc['type']
    if typ.endswith('-array'):
        return (type(value) is list and len(value) == desc['length'] and
                all(typed(v, {'type': typ[:-6]}) for v in value))
    if typ == 'bool': return type(value) is bool
    if typ == 'text': return type(value) is str and len(value.encode('utf-8')) <= 1048576
    if typ == 'resource': return type(value) is int and 0 <= value < (1 << 31)
    width = int(typ[1:])
    low, high = (0, (1 << width)-1) if typ[0] == 'u' else (-(1 << (width-1)), (1 << (width-1))-1)
    return type(value) is int and low <= value <= high

def checked(value, desc):
    if not typed(value, desc): raise Refused('Value outside declared type')
    return owned(value)

def protocol_args(values, descriptors):
    if type(values) is not list or len(values) != len(descriptors): raise Refused('Argument count differs')
    result = []
    for value, desc in zip(values, descriptors):
        typ = desc['type']
        if typ[0] in 'ui' and typ[1:].isdigit() and type(value) is str:
            if len(value)>21 or not re.fullmatch(r'0|-?[1-9][0-9]*', value): raise Refused('Expected exact integer')
            value = int(value)
        result.append(checked(value, desc))
    return result

def wrap(value, typ):
    if typ == 'bool': return value != 0
    width = int(typ[1:]); value = int(value) % (1 << width)
    return value - (1 << width) if typ[0] == 'i' and value >= (1 << (width-1)) else value

def operation(op, typ, values):
    a = values[0]
    if op == 'not': return not a
    if op == 'cast': return wrap(a, typ)
    if op == 'parity_even': return (int(a) & 255).bit_count() % 2 == 0
    if op == 'select': return owned(values[1] if a else values[2])
    b = values[1]
    if op == 'eq': return a == b
    if op == 'ne': return a != b
    if op == 'lt': return a < b
    if op == 'le': return a <= b
    if op == 'gt': return a > b
    if op == 'ge': return a >= b
    if op in ('div', 'mod'):
        if b == 0: raise Refused('Zero divisor')
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0): q = -q
        return wrap(q if op == 'div' else a-q*b, typ)
    if op in ('shl', 'shr'):
        if not 0 <= b < int(typ[1:]): raise Refused('Shift count outside width')
        return wrap(a << b if op == 'shl' else a >> b, typ)
    if op == 'add': value = a+b
    elif op == 'sub': value = a-b
    elif op == 'mul': value = a*b
    elif op == 'and': value = a & b
    elif op == 'or': value = a | b
    elif op == 'xor': value = a ^ b
    else: raise Refused('Unsupported emitted operation')
    return wrap(value, typ)

def load(array, index):
    if type(index) is not int or not 0 <= index < len(array): raise Refused('Array load outside bounds')
    return array[index]

def store(array, index, value):
    if type(index) is not int or not 0 <= index < len(array): raise Refused('Array store outside bounds')
    array[index] = value

def bind(initial, types, slots, args):
    if type(args) is not list or len(args) != len(slots): raise Refused('Argument count differs')
    frame = owned(initial)
    for slot, value in zip(slots, args): frame[slot] = checked(value, types[slot])
    return frame

def assign(frame, slots, values, types):
    if len(slots) != len(values): raise Refused('Result count differs')
    copies = [checked(value, types[slot]) for slot, value in zip(slots, values)]
    for slot, value in zip(slots, copies): frame[slot] = value

class Context:
    def __init__(self):
        self.steps = 0; self.frames = []; self.events = []; self.calls = []
        self.trace_cells = 0; self.event_bytes = 0
    def enter(self, budget):
        if len(self.frames) >= MAX_DEPTH: raise Refused('Call depth exhausted')
        self.frames.append(budget)
    def leave(self): self.frames.pop()
    def charge(self):
        self.steps += 1
        if self.steps > MAX_STEPS: raise Refused('Execution budget exhausted')
        for i in range(len(self.frames)):
            self.frames[i] -= 1
            if self.frames[i] < 0: raise Refused('Execution budget exhausted')
    def begin_call(self, metadata, values):
        if len(self.calls) >= TRACE_LIMITS['calls']: raise Refused('invocation trace budget exhausted')
        logged, cells = trace_values(values)
        if self.trace_cells+cells+1 > TRACE_LIMITS['cells']: raise Refused('invocation trace budget exhausted')
        self.trace_cells += cells+1
        receipt = {**metadata,'inputs':logged,'outputs':[],'status':'entered'}
        self.calls.append(receipt)
        return receipt
    def complete_call(self, receipt, values):
        logged, cells = trace_values(values)
        if self.trace_cells+cells > TRACE_LIMITS['cells']: raise Refused('invocation trace budget exhausted')
        self.trace_cells += cells
        receipt['outputs'] = logged; receipt['status'] = 'complete'
    def effect(self, service, values):
        index = values[0]
        if type(index) is not int or not 0 <= index < len(RESOURCES): raise Refused('Resource outside catalog')
        expected = {'text.show':'text', 'image.show':'graphic', 'sound.play':'sound',
                    'music.start':'music', 'music.stop':'music'}[service]
        if RESOURCES[index]['kind'] != expected: raise Refused('Resource kind differs from service')
        event = {'service':service,'inputs':owned(values),'resource':owned(RESOURCES[index])}
        size = len(json.dumps(event,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        if len(self.events) >= TRACE_LIMITS['events'] or self.event_bytes+size > TRACE_LIMITS['event_bytes']:
            raise Refused('effect event budget exhausted')
        self.event_bytes += size; self.events.append(event)
'''


_JAVASCRIPT_RUNTIME = r'''import readline from 'node:readline';
import {createHash} from 'node:crypto';

class Refused extends Error {}
const owned = value => Array.isArray(value) ? value.map(owned) :
    value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).map(([k,v])=>[k,owned(v)])) : value;
function traceValues(values){
  const result=[];let cells=0;
  for(const value of values){
    if(Array.isArray(value)&&value.length>TRACE_LIMITS.array_inline){
      const raw=JSON.stringify(value.map(v=>Number(v)));
      result.push({kind:'array-summary',length:value.length,sha256:createHash('sha256').update(raw,'utf8').digest('hex')});cells+=4;
    }else if(typeof value==='string'&&Buffer.byteLength(value,'utf8')>TRACE_LIMITS.text_inline_bytes){
      const raw=Buffer.from(value,'utf8');
      result.push({kind:'text-summary',bytes:raw.length,sha256:createHash('sha256').update(raw).digest('hex')});cells+=4;
    }else{result.push(owned(value));cells+=Array.isArray(value)?Math.max(1,value.length):1;}
  }
  return {values:result,cells};
}
const integer = value => {
  if (typeof value === 'bigint') return value;
  if (typeof value === 'number' && Number.isSafeInteger(value)) return BigInt(value);
  if (typeof value === 'string' && value.length<=21 && /^(0|-?[1-9][0-9]*)$/.test(value)) return BigInt(value);
  throw new Refused('Expected exact integer');
};
function validText(value){
  if(typeof value!=='string'||Buffer.byteLength(value,'utf8')>1048576)return false;
  for(let i=0;i<value.length;i++){
    const c=value.charCodeAt(i);
    if(c>=0xd800&&c<=0xdbff){const d=value.charCodeAt(++i);if(!(d>=0xdc00&&d<=0xdfff))return false;}
    else if(c>=0xdc00&&c<=0xdfff)return false;
  }
  return true;
}
function checked(value, desc) {
  const typ=desc.type;
  if(typ.endsWith('-array')) {
    if(!Array.isArray(value)||value.length!==desc.length)throw new Refused('Array shape differs');
    return value.map(v=>checked(v,{type:typ.slice(0,-6)}));
  }
  if(typ==='bool') {if(typeof value!=='boolean')throw new Refused('Expected boolean');return value;}
  if(typ==='text') {if(!validText(value))throw new Refused('Expected text');return value;}
  if(typ==='resource') {if(!Number.isSafeInteger(value)||value<0||value>=2147483648)throw new Refused('Expected resource index');return value;}
  const v=integer(value), width=BigInt(typ.slice(1));
  const low=typ[0]==='u'?0n:-(1n<<(width-1n)), high=typ[0]==='u'?(1n<<width)-1n:(1n<<(width-1n))-1n;
  if(v<low||v>high)throw new Refused('Value outside declared type');
  return v;
}
function wrap(value,typ) {
  if(typ==='bool')return value!==0n && value!==0 && value!==false;
  value=typeof value==='boolean'?(value?1n:0n):integer(value);
  const width=BigInt(typ.slice(1)),mod=1n<<width;
  value=((value%mod)+mod)%mod;
  return typ[0]==='i'&&value>=(1n<<(width-1n))?value-mod:value;
}
function operation(op,typ,values) {
  const a=values[0],b=values[1];
  if(op==='not')return !a;
  if(op==='cast')return wrap(a,typ);
  if(op==='parity_even'){let x=a&255n,n=0;while(x){n+=Number(x&1n);x>>=1n;}return n%2===0;}
  if(op==='select')return owned(a?values[1]:values[2]);
  if(op==='eq')return a===b;
  if(op==='ne')return a!==b;
  if(op==='lt')return a<b;
  if(op==='le')return a<=b;
  if(op==='gt')return a>b;
  if(op==='ge')return a>=b;
  if((op==='div'||op==='mod')&&b===0n)throw new Refused('Zero divisor');
  if((op==='shl'||op==='shr')&&(b<0n||b>=BigInt(typ.slice(1))))throw new Refused('Shift count outside width');
  let v;
  if(op==='add')v=a+b;else if(op==='sub')v=a-b;else if(op==='mul')v=a*b;
  else if(op==='div')v=a/b;else if(op==='mod')v=a%b;
  else if(op==='and')v=a&b;else if(op==='or')v=a|b;else if(op==='xor')v=a^b;
  else if(op==='shl')v=a<<b;else if(op==='shr')v=a>>b;
  else throw new Refused('Unsupported emitted operation');
  return wrap(v,typ);
}
function arrayIndex(array,index){
  if(typeof index!=='bigint'||index<0n||index>=BigInt(array.length))throw new Refused('Array index outside bounds');
  return Number(index);
}
function load(array,index){return array[arrayIndex(array,index)];}
function store(array,index,value){array[arrayIndex(array,index)]=value;}
function bind(initial,types,slots,args){
  if(!Array.isArray(args)||args.length!==slots.length)throw new Refused('Argument count differs');
  const frame=owned(initial);slots.forEach((slot,i)=>frame[slot]=checked(args[i],types[slot]));return frame;
}
function assign(frame,slots,values,types){
  if(slots.length!==values.length)throw new Refused('Result count differs');
  const copies=slots.map((slot,i)=>checked(values[i],types[slot]));
  slots.forEach((slot,i)=>frame[slot]=copies[i]);
}
class Context {
  constructor(){this.steps=0;this.frames=[];this.events=[];this.calls=[];this.traceCells=0;this.eventBytes=0;}
  enter(budget){if(this.frames.length>=MAX_DEPTH)throw new Refused('Call depth exhausted');this.frames.push(budget);}
  leave(){this.frames.pop();}
  charge(){this.steps++;if(this.steps>MAX_STEPS)throw new Refused('Execution budget exhausted');for(let i=0;i<this.frames.length;i++){this.frames[i]--;if(this.frames[i]<0)throw new Refused('Execution budget exhausted');}}
  beginCall(metadata,values){
    if(this.calls.length>=TRACE_LIMITS.calls)throw new Refused('invocation trace budget exhausted');
    const logged=traceValues(values);
    if(this.traceCells+logged.cells+1>TRACE_LIMITS.cells)throw new Refused('invocation trace budget exhausted');
    this.traceCells+=logged.cells+1;
    const receipt={...metadata,inputs:logged.values,outputs:[],status:'entered'};this.calls.push(receipt);return receipt;
  }
  completeCall(receipt,values){
    const logged=traceValues(values);
    if(this.traceCells+logged.cells>TRACE_LIMITS.cells)throw new Refused('invocation trace budget exhausted');
    this.traceCells+=logged.cells;receipt.outputs=logged.values;receipt.status='complete';
  }
  effect(service,values){
    const index=values[0],expected={'text.show':'text','image.show':'graphic','sound.play':'sound','music.start':'music','music.stop':'music'}[service];
    if(!Number.isSafeInteger(index)||index<0||index>=RESOURCES.length)throw new Refused('Resource outside catalog');
    if(RESOURCES[index].kind!==expected)throw new Refused('Resource kind differs from service');
    const event={service,inputs:owned(values),resource:owned(RESOURCES[index])},size=Buffer.byteLength(JSON.stringify(event),'utf8');
    if(this.events.length>=TRACE_LIMITS.events||this.eventBytes+size>TRACE_LIMITS.event_bytes)throw new Refused('effect event budget exhausted');
    this.eventBytes+=size;this.events.push(event);
  }
}
const publicValue=value=>typeof value==='bigint'?(value>=-9007199254740991n&&value<=9007199254740991n?Number(value):value.toString()):
  Array.isArray(value)?value.map(publicValue):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,publicValue(v)])):value;
'''


class _Emitter:
    def __init__(self, target):
        self.js = target == 'javascript'
        self.lines = []
        self.serial = 0

    def line(self, text='', indent=0):
        self.lines.append('    '*indent + text)

    def value(self, value):
        return _json(value) if self.js else repr(value)

    def expr(self, node):
        if 'var' in node:
            return 'f['+str(node['var'])+']'
        if 'const' in node:
            return 'c['+str(node['const'])+']'
        if node['op'] == 'load':
            return 'load(f['+str(node['array'])+'],'+self.expr(node['index'])+')'
        args = ','.join(self.expr(v) for v in node['args'])
        return 'operation('+self.value(node['op'])+','+self.value(node['type'])+',['+args+'])'

    def block(self, nodes, indent, function, table):
        for node in nodes:
            op = node['op']
            if op == 'group':
                self.block(node['body'], indent, function, table)
                continue
            self.line('ctx.charge()'+(';' if self.js else ''), indent)
            end = ';' if self.js else ''
            if op == 'set':
                self.line('f['+str(node['dst'])+']=checked('+self.expr(node['value'])+','+table+'['+str(node['dst'])+'])'+end, indent)
            elif op == 'store':
                self.line('store(f['+str(node['array'])+'],'+self.expr(node['index'])+','+self.expr(node['value'])+')'+end, indent)
            elif op == 'if':
                condition = self.expr(node['condition'])
                self.line(('if ('+condition+') {' if self.js else 'if '+condition+':'), indent)
                if node['then']: self.block(node['then'], indent+1, function, table)
                elif not self.js: self.line('pass', indent+1)
                if self.js:
                    self.line('} else {', indent)
                else:
                    self.line('else:', indent)
                if node['else']: self.block(node['else'], indent+1, function, table)
                elif not self.js: self.line('pass', indent+1)
                if self.js: self.line('}', indent)
            elif op == 'while':
                counter='loop'+str(self.serial); self.serial+=1
                self.line(('let '+counter+'=0;' if self.js else counter+'=0'), indent)
                self.line('while (true) {' if self.js else 'while True:', indent)
                self.line('ctx.charge()'+end, indent+1)
                condition=self.expr(node['condition'])
                self.line('if (!('+condition+')) break;' if self.js else 'if not ('+condition+'): break', indent+1)
                self.line('if ('+counter+'>='+str(node['limit'])+") throw new Refused('Loop limit exhausted');" if self.js else 'if '+counter+'>='+str(node['limit'])+": raise Refused('Loop limit exhausted')", indent+1)
                self.line(counter+('++;' if self.js else '+=1'), indent+1)
                self.block(node['body'], indent+1, function, table)
                if self.js: self.line('}', indent)
            elif op in ('call','invoke'):
                name = ('fn'+str(node['function'])) if op == 'call' else ('invoke'+str(node['block']))
                temp='result'+str(self.serial);self.serial+=1
                args='['+','.join(self.expr(v) for v in node['inputs'])+']'
                if op == 'call':
                    self.line(('const ' if self.js else '')+temp+'='+name+'(ctx,'+args+')'+end,indent)
                    outputs=function['program_functions'][node['function']]['outputs']
                    result_values='['+','.join(temp+'['+str(i)+']' for i in outputs)+']'
                else:
                    self.line(('const ' if self.js else '')+temp+'='+name+'(ctx,'+args+')'+end,indent)
                    result_values=temp
                self.line('assign(f,'+self.value(node['outputs'])+','+result_values+','+table+')'+end,indent)
            elif op == 'require':
                condition=self.expr(node['condition'])
                self.line('if (!('+condition+")) throw new Refused('Requirement refused');" if self.js else 'if not ('+condition+"): raise Refused('Requirement refused')",indent)
            elif op == 'effect':
                args='['+','.join(self.expr(v) for v in node['inputs'])+']'
                self.line('ctx.effect('+self.value(node['service'])+','+args+')'+end,indent)
            elif op == 'return':
                self.line('return f'+end,indent)
            else:
                raise ValueError('unsupported common UIL statement')

    def function(self, name, function, constants, initial, program_functions):
        types=function['variables'];table=name+'_types';const=name+'_constants';init=name+'_initial'
        if self.js:
            self.line('const '+table+'='+_json(types)+';')
            self.line('const '+const+'='+_json(constants)+';')
            self.line('const '+init+'='+_json(initial)+';')
            self.line('function '+name+'(ctx,args) {')
            self.line('const f=bind('+init+','+table+','+_json(function['inputs'])+',args),c='+const+';',1)
        else:
            self.line(table+'='+repr(types));self.line(const+'='+repr(constants));self.line(init+'='+repr(initial))
            self.line('def '+name+'(ctx,args):')
            self.line('f=bind('+init+','+table+','+repr(function['inputs'])+',args);c='+const,1)
        self.line('ctx.enter('+str(function['max_steps'])+')'+(';' if self.js else ''),1)
        self.line('try {' if self.js else 'try:',1)
        self.block(function['body'],2,{'program_functions':program_functions},table)
        self.line('return f'+(';' if self.js else ''),2)
        if self.js:
            self.line('} finally {ctx.leave();}',1);self.line('}')
        else:
            self.line('finally: ctx.leave()',1)
        self.line()


def _literal_values(values, descriptors):
    """Decode presentation integers without narrowing them through a host float."""
    return [int(v) if d['type'][0] in 'ui' and d['type'][1:].isdigit() else deepcopy(v)
            for v,d in zip(values, descriptors)]


def _js_values(values, descriptors):
    """JS source values are type-checked at construction, preserving uint64."""
    return '['+','.join('checked('+_json(v)+','+_json(d)+')' for v,d in zip(values,descriptors))+']'


def _source(program, presentation, resolved, plan, identities, target, trace_limits):
    from .common_uil import default_value
    emitter=_Emitter(target);js=emitter.js
    emitter.line(_JAVASCRIPT_RUNTIME if js else _PYTHON_RUNTIME)
    for name,value in [('MAX_STEPS',MAX_STEPS),('MAX_DEPTH',plan['max_call_depth']),
                       ('RESOURCES',presentation['resources']),('IDENTITIES',identities),('TRACE_LIMITS',trace_limits)]:
        emitter.line(('const ' if js else '')+name+'='+emitter.value(value)+(';' if js else ''))
    for index,fn in enumerate(program['functions']):
        data=presentation['functions'][index]
        constants=_literal_values(data['constants'],fn['constants'])
        initial=_literal_values(data['initial'],fn['variables'])
        if js:
            constants=_js_values(data['constants'],fn['constants'])
            initial=_js_values(data['initial'],fn['variables'])
        # JS expressions are written verbatim only after strict descriptor/value validation.
        start=len(emitter.lines)
        emitter.function('fn'+str(index),fn,constants,initial,program['functions'])
        if js:
            emitter.lines[start+1]='const fn'+str(index)+'_constants='+constants+';'
            emitter.lines[start+2]='const fn'+str(index)+'_initial='+initial+';'
    for index,impl in sorted(resolved.items()):
        fn=impl['function'];defaults=[default_value(d) for d in fn['variables']]
        constants=_literal_values(impl['constants'],fn['constants'])
        start=len(emitter.lines)
        emitter.function('impl'+str(index),fn,constants,defaults,[])
        if js:
            emitter.lines[start+1]='const impl'+str(index)+'_constants='+_js_values(impl['constants'],fn['constants'])+';'
            emitter.lines[start+2]='const impl'+str(index)+'_initial='+_js_values(defaults,fn['variables'])+';'
        receipt={'block':index,'semantic_id':program['imports'][index]['semantic_id'],
                 'implementation':impl['id'],'language':impl['language']}
        ins=fn['inputs'];outs=fn['outputs'];types=fn['variables'];name='invoke'+str(index)
        if js:
            emitter.line('function '+name+'(ctx,args) {')
            emitter.line('const values=args.map((v,i)=>checked(v,'+_json([types[i] for i in ins])+"[i]));",1)
            emitter.line('const receipt=ctx.beginCall('+_json(receipt)+',values);',1)
            emitter.line('try {',1)
            emitter.line('const f=impl'+str(index)+'(ctx,values);',2)
            emitter.line('const result='+_json(outs)+'.map(i=>checked(f[i],'+_json(types)+'[i]));',2)
            emitter.line('ctx.completeCall(receipt,result);return result;',2)
            emitter.line('} catch(error){receipt.status="refused";receipt.error=String(error.message||error);throw error;}',1)
            emitter.line('}')
        else:
            emitter.line('def '+name+'(ctx,args):')
            emitter.line('if type(args) is not list or len(args)!='+str(len(ins))+": raise Refused('Argument count differs')",1)
            emitter.line('values=[checked(v,d) for v,d in zip(args,'+repr([types[i] for i in ins])+')]',1)
            emitter.line('receipt=ctx.begin_call('+repr(receipt)+',values)',1)
            emitter.line('try:',1)
            emitter.line('f=impl'+str(index)+'(ctx,values)',2)
            emitter.line('result=[checked(f[i],'+repr(types)+'[i]) for i in '+repr(outs)+']',2)
            emitter.line('ctx.complete_call(receipt,result);return result',2)
            emitter.line('except (Refused,ValueError,TypeError,KeyError,IndexError,RecursionError) as error:',1)
            emitter.line("receipt['status']='refused';receipt['error']=str(error);raise",2)
    entry=program['entry'];fn=program['functions'][entry]
    if js:
        emitter.line('function execute(request) {')
        emitter.line('const ctx=new Context();let original=owned(fn'+str(entry)+'_initial);',1)
        emitter.line('try {',1)
        emitter.line("if(!request||Array.isArray(request)||Object.keys(request).length!==1||!Object.hasOwn(request,'inputs'))throw new Refused('Expected inputs request');",2)
        emitter.line('original=bind(original,fn'+str(entry)+'_types,'+_json(fn['inputs'])+',request.inputs);',2)
        emitter.line('const state=fn'+str(entry)+'(ctx,request.inputs);',2)
        emitter.line('if(ctx.events.length)return {...IDENTITIES,status:"pending_host",outputs:[],state:original,proposed_state:state,events:ctx.events,calls:ctx.calls,steps:ctx.steps};',2)
        emitter.line('return {...IDENTITIES,status:"complete",outputs:'+_json(fn['outputs'])+'.map(i=>owned(state[i])),state,events:[],calls:ctx.calls,steps:ctx.steps};',2)
        emitter.line('} catch(error) {return {...IDENTITIES,status:"refused",outputs:[],state:original,events:[],calls:ctx.calls,steps:ctx.steps,error:String(error.message||error)};}',1)
        emitter.line('}')
        emitter.line("for await (const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})) {")
        emitter.line('try {process.stdout.write(JSON.stringify(publicValue(execute(JSON.parse(line))))+"\\n");}',1)
        emitter.line('catch(error){process.stdout.write(JSON.stringify({status:"refused",outputs:[],state:[],events:[],calls:[],error:String(error.message||error)})+"\\n");}',1)
        emitter.line('}')
    else:
        emitter.line('def execute(request):')
        emitter.line('ctx=Context();original=owned(fn'+str(entry)+'_initial)',1)
        emitter.line('try:',1)
        emitter.line("if type(request) is not dict or set(request)!={'inputs'}: raise Refused('Expected inputs request')",2)
        emitter.line('args=protocol_args(request[\'inputs\'],'+repr([fn['variables'][i] for i in fn['inputs']])+')',2)
        emitter.line('original=bind(original,fn'+str(entry)+'_types,'+repr(fn['inputs'])+',args)',2)
        emitter.line('state=fn'+str(entry)+'(ctx,args)',2)
        emitter.line("if ctx.events: return {**IDENTITIES,'status':'pending_host','outputs':[],'state':original,'proposed_state':state,'events':ctx.events,'calls':ctx.calls,'steps':ctx.steps}",2)
        emitter.line("return {**IDENTITIES,'status':'complete','outputs':[owned(state[i]) for i in "+repr(fn['outputs'])+"],'state':state,'events':[],'calls':ctx.calls,'steps':ctx.steps}",2)
        emitter.line('except (Refused,ValueError,TypeError,KeyError,IndexError,RecursionError) as error:',1)
        emitter.line("return {**IDENTITIES,'status':'refused','outputs':[],'state':original,'events':[],'calls':ctx.calls,'steps':ctx.steps,'error':str(error)}",2)
        emitter.line("if __name__=='__main__':")
        emitter.line('for line in sys.stdin:',1)
        emitter.line('try: result=execute(json.loads(line))',2)
        emitter.line('except (ValueError,TypeError) as error:',2)
        emitter.line("result={'status':'refused','outputs':[],'state':[],'events':[],'calls':[],'error':str(error)}",3)
        emitter.line('print(json.dumps(result,separators=(",",":"),ensure_ascii=False,allow_nan=False))',2)
    return '\n'.join(emitter.lines)+'\n'


def compile_program(program, presentation, catalog, orchestration, output_dir, target='python'):
    """Emit a deterministic, standalone source realization in a new private root.

    Compilation here is UIL-to-source lowering. Executing the emitted source is
    a separate qualification gate; no host effects are performed by it.
    """
    from .common_uil import digest, validate_program, validate_presentation, validate_realization
    from .uil_catalog import validate_catalog
    from .uil_runtime import TRACE_LIMITS
    if target not in ('python','javascript'):
        raise ValueError('choose python or javascript')
    program=deepcopy(program);presentation=deepcopy(presentation)
    catalog=deepcopy(catalog);orchestration=deepcopy(orchestration)
    validate_program(program);validate_presentation(program,presentation);validate_catalog(catalog)
    qualified=validate_realization(program,presentation,catalog,orchestration)
    resolved=qualified['resolved']
    destination=Path(output_dir).expanduser().absolute()
    if os.path.lexists(destination): raise ValueError('choose a new code-generation output')
    destination=destination.resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('generated realizations must stay outside Git')
    trace_limits=deepcopy(TRACE_LIMITS)
    closure={'program':program,'presentation':presentation,'catalog':catalog,'orchestration':orchestration,
             'target':target,'generator_profile':'common-uil-standalone-1',
             'generator_sha256':_sha(Path(__file__).read_bytes()),'aggregate_max_steps':MAX_STEPS,
             'diagnostic_limits':trace_limits}
    identities={k+'_sha256':digest(v) for k,v in [('program',program),('presentation',presentation),
                ('catalog',catalog),('orchestration',orchestration)]}
    identities['closure_sha256']=digest(closure)
    source=_source(program,presentation,resolved,orchestration,identities,target,trace_limits)
    filename='program.mjs' if target=='javascript' else 'program.py'
    raw=source.encode('utf-8')
    selected=[{'import':index,**{k:deepcopy(impl[k]) for k in ('id','language','source','assurance')},
               'semantic_id':program['imports'][index]['semantic_id']} for index,impl in sorted(resolved.items())]
    manifest={'format':FORMAT,'stage':'source-emitted','target':target,'entry':program['entry'],
              **identities,'closure':closure,'artifacts':{filename:_sha(raw)},
              'selected_implementations':selected,'shims':deepcopy(qualified['shims']),
              'ownership':'copy-in-copy-out','max_call_depth':orchestration['max_call_depth'],
              'integer_protocol':'exact JSON integers; decimal strings accepted for integer inputs; JavaScript emits unsafe integers as decimal strings',
              'budget_policy':'one charge per non-group statement and while condition; child work charges all active frames and aggregate budget',
              'diagnostic_limits':deepcopy(trace_limits),
              'aggregate_max_steps':MAX_STEPS,'runtime_ast_interpreter':False,'host_effect_execution':False,
              'execution':False,'scope':'standalone emitted function/control code; source/original fidelity and execution require separate evidence'}
    manifest['realization_sha256']=digest(manifest)
    destination.mkdir(parents=True)
    with (destination/filename).open('xb') as stream: stream.write(raw)
    with (destination/'manifest.json').open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n')
    return manifest
