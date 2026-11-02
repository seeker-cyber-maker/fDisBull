"""Bounded typed-C -> existing fdisbull-il-1 adapter, using real Clang AST.

This pilot fixes the C ABI to x86-64 Linux LP64; logical ports are address-free. No C text
pattern matching, source-body execution, or decompiler is substituted for Clang.
Only pure integer functions, forward if/returns, and explicitly bound fixed
buffers are admitted. Signed overflow/implementation-defined casts refuse.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import json
import re
import subprocess
from fdisbull.interaction_il import validate_il, execute_il


class CFrontendRefused(ValueError):
    pass


TYPE_NAMES = {
    'unsigned char': 'u8', 'signed char': 'i8', 'short': 'i16',
    'short int': 'i16', 'unsigned short': 'u16', 'unsigned short int': 'u16',
    'int': 'i32', 'unsigned int': 'u32', 'long': 'i64',
    'long int': 'i64', 'unsigned long': 'u64', 'unsigned long int': 'u64',
    'long long': 'i64', 'unsigned long long': 'u64', '_Bool': 'bool',
}


def bounds(typ):
    if typ == 'bool': return (0, 1)
    width = int(typ[1:])
    return (0, (1 << width)-1) if typ[0]=='u' else (-(1 << (width-1)), (1 << (width-1))-1)


def negate(c): return {'op': 'not', 'condition': c}
def both(*c): return {'op': 'and', 'conditions': list(c)}
def either(a, b): return negate(both(negate(a), negate(b)))
def eq(a, b): return {'op': 'eq', 'left': a, 'right': b}
def bit(v, i): return {'op': 'bit_test', 'value': v, 'bit': i}


def constant_condition(c):
    """Fold only literal conditions; no source spelling or foreign oracle."""
    if c['op']=='eq' and not isinstance(c['left'],dict) and not isinstance(c['right'],dict):
        return c['left']==c['right']
    if c['op']=='bit_test' and type(c['value']) is int:
        return bool(c['value'] & (1<<c['bit']))
    if c['op']=='not':
        x=constant_condition(c['condition']);return None if x is None else not x
    if c['op']=='and':
        values=[constant_condition(x) for x in c['conditions']]
        return False if False in values else True if all(x is True for x in values) else None
    return None


@dataclass(frozen=True)
class Value:
    value: object
    typ: str
    lo: int
    hi: int


@dataclass
class ImportedFunction:
    document: dict
    input_ports: dict
    output_ports: dict
    source_sha256: str
    clang_version: str
    command: list
    ast: dict
    function: str

    def state(self, values):
        if set(values) != set(self.input_ports):
            raise CFrontendRefused('input port set differs from contract')
        state = {k: d['initial'] for k, d in self.document['variables'].items()}
        for label, value in values.items():
            spec = self.input_ports[label]
            if type(value) is not int or not spec['min'] <= value <= spec['max']:
                raise CFrontendRefused('input outside admitted domain: '+label)
            state[label] = value
        return state

    def run(self, values):
        result = execute_il(self.document, self.state(values))
        if result['status'] != 'complete':
            raise CFrontendRefused('UIL refused: '+result.get('error','unknown'))
        return {name: result['state'][label] for name,label in self.output_ports.items()}


class Builder:
    def __init__(self, ast, function, bindings):
        self.ast, self.function, self.bindings = ast, function, bindings or {}
        self.vars, self.inputs, self.outputs = {}, {}, {'return': '$return_value'}
        self.names, self.arrays, self.pointers, self.fixed, self.ranges = {}, {}, {}, {}, {}
        self.readonly = set()
        self.counter = 0
        self.aliases = {n['name']: n['type'].get('desugaredQualType', n['type']['qualType'])
                        for n in ast.get('inner',[]) if n.get('kind')=='TypedefDecl'}
        self.alloc('$returned','bool')

    def typ(self, t):
        text = t.get('desugaredQualType',t.get('qualType','')) if isinstance(t,dict) else t
        if any(x in text.split() for x in ('volatile','_Atomic')):
            raise CFrontendRefused('volatile/atomic behavior needs an effect provider')
        text = re.sub(r'\bconst\b', '', text).strip()
        seen = set()
        while text in self.aliases and text not in seen:
            seen.add(text); text = self.aliases[text]
        if text not in TYPE_NAMES:
            raise CFrontendRefused('unsupported C type: '+text)
        return TYPE_NAMES[text]

    def uid(self, prefix='n'):
        self.counter += 1
        if self.counter > 3000: raise CFrontendRefused('lowering node budget')
        return f'{prefix}{self.counter}'

    def alloc(self, name, typ):
        if name in self.vars: raise CFrontendRefused('duplicate logical label '+name)
        self.vars[name] = {'type':typ, 'initial': False if typ=='bool' else 0}
        self.ranges[name] = bounds(typ)
        return name

    def temporary(self, typ): return self.alloc('$tmp_'+self.uid(), typ)

    def value(self, name, initialized):
        if name not in initialized: raise CFrontendRefused('read before definite initialization: '+name)
        lo,hi = self.ranges[name]
        return Value({'var':name}, self.vars[name]['type'],lo,hi)

    def write(self, body, name, val, op='set'):
        if type(val) is int:
            lo,hi = bounds(self.vars[name]['type'])
            if not lo <= val <= hi:
                tmp=self.temporary('i64' if val<0 else 'u64')
                body.append({'id':self.uid(),'op':'set','var':tmp,'value':val})
                val={'var':tmp}
        body.append({'id':self.uid(),'op':op,'var':name,'value':val})

    def boolean(self, body, condition):
        constant=constant_condition(condition)
        if constant is not None:return Value(constant,'bool',int(constant),int(constant))
        name=self.temporary('bool')
        body.append({'id':self.uid(),'op':'if','condition':condition,
                     'then':[{'id':self.uid(),'op':'set','var':name,'value':True}],
                     'else':[{'id':self.uid(),'op':'set','var':name,'value':False}]})
        return Value({'var':name},'bool',0,1)

    def truth(self, value):
        if value.typ=='pointer': return eq(1,1)
        if value.lo==value.hi==0:return eq(0,1)
        if value.hi<0 or value.lo>0:return eq(1,1)
        return negate(eq(value.value,False if value.typ=='bool' else 0))

    def convert(self, val, typ, body):
        if val.typ=='pointer': raise CFrontendRefused('pointer value used outside fixed-buffer/null contract')
        if typ==val.typ: return val
        if typ=='bool': return self.boolean(body,self.truth(val))
        if val.typ=='bool':
            if type(val.value)is bool:return Value(int(val.value),typ,int(val.value),int(val.value))
            tmp=self.temporary(typ)
            body.append({'id':self.uid(),'op':'if','condition':self.truth(val),
                         'then':[{'id':self.uid(),'op':'set','var':tmp,'value':1}],
                         'else':[{'id':self.uid(),'op':'set','var':tmp,'value':0}]})
            return Value({'var':tmp},typ,0,1)
        lo,hi=bounds(typ)
        if typ[0]=='i' and not (lo<=val.lo and val.hi<=hi):
            raise CFrontendRefused('implementation-defined signed conversion')
        if lo<=val.lo and val.hi<=hi:
            return Value(val.value,typ,val.lo,val.hi)
        tmp=self.temporary(typ)
        self.write(body,tmp,0); self.write(body,tmp,val.value,'add')
        return Value({'var':tmp},typ,lo,hi)

    def comparison(self, op, a, b, body):
        if a.typ!=b.typ: raise CFrontendRefused('Clang comparison conversion not resolved')
        if op in ('==','!='):
            c=eq(a.value,b.value); return c if op=='==' else negate(c)
        if op in ('>','>='): a,b=b,a;op={'>' : '<', '>=':'<='}[op]
        if a.typ=='bool': raise CFrontendRefused('ordered Boolean comparison not admitted')
        if a.hi < b.lo: c=eq(1,1)
        elif a.lo >= b.hi: c=eq(0,1)
        else:
            width=int(a.typ[1:]); diff=self.temporary('u'+str(width))
            self.write(body,diff,0);self.write(body,diff,a.value,'add');self.write(body,diff,b.value,'subtract')
            sa,sb=bit(a.value,width-1),bit(b.value,width-1)
            same=either(both(sa,sb),both(negate(sa),negate(sb)))
            first=both(sa,negate(sb)) if a.typ[0]=='i' else both(negate(sa),sb)
            c=either(first,both(same,bit({'var':diff},width-1)))
        return either(c,eq(a.value,b.value)) if op=='<=' else c

    def ref_id(self,node):
        while node.get('kind') in ('ImplicitCastExpr','ParenExpr'):
            node=node['inner'][0]
        if node.get('kind')!='DeclRefExpr': raise CFrontendRefused('buffer base is not a declared symbol')
        return node['referencedDecl']['id']

    def location(self,node,body,initialized):
        if node['kind']=='DeclRefExpr':
            ident=node['referencedDecl']['id']
            if ident not in self.names: raise CFrontendRefused('unbound/global/constant assignment')
            return self.names[ident]
        if node['kind']=='ArraySubscriptExpr':
            ident=self.ref_id(node['inner'][0]); index=self.expr(node['inner'][1],body,initialized)
            if type(index.value) is not int: raise CFrontendRefused('dynamic buffer index requires another profile')
            cells=self.arrays.get(ident)
            if cells is None or not 0<=index.value<len(cells): raise CFrontendRefused('buffer index out of bounds')
            return cells[index.value]
        raise CFrontendRefused('unsupported assignment location: '+node['kind'])

    def expr(self,n,body,initialized):
        k=n['kind']; children=n.get('inner',[])
        if k=='ParenExpr': return self.expr(children[0],body,initialized)
        if k=='IntegerLiteral':
            typ=self.typ(n['type']); value=int(n['value']);return Value(value,typ,value,value)
        if k=='DeclRefExpr':
            ident=n['referencedDecl']['id']
            if ident in self.pointers:return Value(None,'pointer',1,1)
            if ident in self.fixed:return self.fixed[ident]
            if ident not in self.names:raise CFrontendRefused('unbound declaration/global')
            return self.value(self.names[ident],initialized)
        if k=='ArraySubscriptExpr': return self.value(self.location(n,body,initialized),initialized)
        if k in ('ImplicitCastExpr','CStyleCastExpr'):
            if n.get('castKind')=='ArrayToPointerDecay':
                raise CFrontendRefused('array decay only admitted as a bounded subscript base')
            val=self.expr(children[0],body,initialized)
            if n.get('castKind')=='LValueToRValue':return val
            if n.get('castKind') not in ('IntegralCast','IntegralToBoolean','NoOp'):
                raise CFrontendRefused('unsupported cast '+str(n.get('castKind')))
            return self.convert(val,self.typ(n['type']),body)
        if k=='UnaryOperator':
            op=n['opcode'];a=self.expr(children[0],body,initialized)
            if op=='!':return self.convert(self.boolean(body,negate(self.truth(a))),self.typ(n['type']),body)
            if op=='+':return a
            if op=='-':
                typ=self.typ(n['type']); lo,hi=-a.hi,-a.lo; l,h=bounds(typ)
                if typ[0]=='i' and not(l<=lo and hi<=h):raise CFrontendRefused('possible signed negation overflow')
                tmp=self.temporary(typ);self.write(body,tmp,0);self.write(body,tmp,a.value,'subtract')
                return Value({'var':tmp},typ,lo,hi) if l<=lo and hi<=h else Value({'var':tmp},typ,l,h)
            raise CFrontendRefused('unsupported unary effect/operator '+op)
        if k=='BinaryOperator':
            op=n['opcode']
            if op in ('=',','):raise CFrontendRefused('effectful/nested assignment expression')
            a=self.expr(children[0],body,initialized);b=self.expr(children[1],body,initialized)
            typ=self.typ(n['type'])
            if op in ('==','!=','<','>','<=','>='):
                return self.convert(self.boolean(body,self.comparison(op,a,b,body)),typ,body)
            if op in ('&&','||'):
                # Expressions have no permitted calls, volatile access or mutations.
                ca,cb=self.truth(a),self.truth(b)
                c=both(ca,cb) if op=='&&' else either(ca,cb)
                return self.convert(self.boolean(body,c),typ,body)
            if op in ('+','-'):
                lo,hi=(a.lo+b.lo,a.hi+b.hi) if op=='+' else (a.lo-b.hi,a.hi-b.lo)
                l,h=bounds(typ)
                if typ[0]=='i' and not(l<=lo and hi<=h):raise CFrontendRefused('possible signed arithmetic overflow')
                tmp=self.temporary(typ);self.write(body,tmp,a.value);self.write(body,tmp,b.value,'add' if op=='+' else 'subtract')
                return Value({'var':tmp},typ,lo,hi) if l<=lo and hi<=h else Value({'var':tmp},typ,l,h)
            if op=='*' and type(b.value) is int and 0<=b.value<=16:
                lo,hi=a.lo*b.value,a.hi*b.value;l,h=bounds(typ)
                if typ[0]=='i' and not(l<=lo and hi<=h):raise CFrontendRefused('possible signed multiplication overflow')
                tmp=self.temporary(typ);self.write(body,tmp,0)
                for _ in range(b.value):self.write(body,tmp,a.value,'add')
                return Value({'var':tmp},typ,lo,hi) if l<=lo and hi<=h else Value({'var':tmp},typ,l,h)
            if op in ('&','>>') and type(b.value) is int and a.lo>=0:
                width=int(typ[1:])
                if op=='>>' and not 0<=b.value<width:raise CFrontendRefused('invalid shift count')
                if op=='&' and not 0<=b.value<(1<<width):raise CFrontendRefused('invalid mask')
                tmp=self.temporary(typ);self.write(body,tmp,0)
                shift=b.value if op=='>>' else 0
                maxval=(a.hi>>shift) if op=='>>' else min(a.hi,b.value)
                # Nonnegative admitted ranges bound the required source bits.
                for j in range(maxval.bit_length()):
                    if op=='&' and not (b.value>>j)&1:continue
                    body.append({'id':self.uid(),'op':'if','condition':bit(a.value,j+shift),
                      'then':[{'id':self.uid(),'op':'add','var':tmp,'value':1<<j}], 'else':[]})
                return Value({'var':tmp},typ,0,maxval)
            raise CFrontendRefused('unsupported binary operator '+op)
        raise CFrontendRefused('unsupported expression '+k)

    def assign(self,name,val,body,initialized):
        if name in self.readonly:raise CFrontendRefused('write to read-only input buffer')
        val=self.convert(val,self.vars[name]['type'],body)
        self.write(body,name,val.value);self.ranges[name]=(val.lo,val.hi)
        return initialized|{name}

    def sequence(self,nodes,initialized):
        body=[]; possible_return=False;continues=True
        for node in nodes:
            if not continues:
                raise CFrontendRefused('unreachable statements outside admitted structural profile')
            sub,new_init,mayret,cont=self.statement(node,set(initialized))
            if possible_return:
                sub=[{'id':self.uid(),'op':'if','condition':eq({'var':'$returned'},False),'then':sub,'else':[]}]
            body+=sub;initialized=new_init;possible_return|=mayret;continues=cont
        return body,initialized,possible_return,continues

    def statement(self,n,initialized):
        k=n['kind'];children=n.get('inner',[]);body=[]
        if k=='CompoundStmt':return self.sequence(children,initialized)
        if k=='NullStmt':return body,initialized,False,True
        if k=='DeclStmt':
            for node in children:
                if node['kind']!='VarDecl' or node.get('storageClass') in ('static','extern'):
                    raise CFrontendRefused('nonlocal declaration')
                ident=node['id'];qt=node['type']['qualType'];match=re.fullmatch(r'(.+)\[(\d+)\]',qt)
                if match:
                    size=int(match[2]);typ=self.typ(match[1])
                    if not 1<=size<=32 or node.get('inner'):raise CFrontendRefused('local array shape/initializer unsupported')
                    self.arrays[ident]=[self.alloc('$local_'+self.uid()+'_'+str(i),typ) for i in range(size)]
                    continue
                typ=self.typ(node['type']);name=self.alloc('$local_'+node['name']+'_'+self.uid(),typ)
                self.names[ident]=name
                if node.get('inner'):
                    val=self.expr(node['inner'][-1],body,initialized)
                    initialized=self.assign(name,val,body,initialized)
            return body,initialized,False,True
        if k in ('BinaryOperator','CompoundAssignOperator') and n.get('opcode') in ('=','+=','-='):
            name=self.location(children[0],body,initialized)
            if n['opcode']=='=':val=self.expr(children[1],body,initialized)
            else:raise CFrontendRefused('compound assignment requires explicit promoted arithmetic')
            initialized=self.assign(name,val,body,initialized)
            return body,initialized,False,True
        if k=='ReturnStmt':
            required=set(self.outputs.values())-{'$return_value'}
            if not required <= initialized:
                raise CFrontendRefused('return leaves output cells dependent on unspecified initial memory')
            if len(children)!=1:raise CFrontendRefused('void return unsupported')
            val=self.expr(children[0],body,initialized)
            initialized=self.assign('$return_value',val,body,initialized)
            self.write(body,'$returned',True)
            return body,initialized,True,False
        if k=='IfStmt':
            if n.get('hasInit') or n.get('hasVar') or len(children) not in (2,3):raise CFrontendRefused('unsupported if form')
            val=self.expr(children[0],body,initialized)
            constant=constant_condition(self.truth(val))
            if constant is not None:
                # This is specialization under the admitted input/memory contract.
                chosen=children[1] if constant else children[2] if len(children)==3 else None
                if chosen is None:return body,initialized,False,True
                tail,init,ret,cont=self.statement(chosen,initialized)
                return body+tail,init,ret,cont
            before=dict(self.ranges)
            yes,iy,ry,cy=self.statement(children[1],set(initialized));yr=dict(self.ranges)
            self.ranges.update(before)
            no,ino,rn,cn=self.statement(children[2],set(initialized)) if len(children)==3 else ([],set(initialized),False,True)
            nr=dict(self.ranges)
            constant=constant_condition(self.truth(val))
            if constant is not None:
                self.ranges.update(yr if constant else nr)
                return body+(yes if constant else no), (iy if constant else ino), (ry if constant else rn), (cy if constant else cn)
            for name in set(yr)|set(nr):
                candidates=[r[name] for cont,r in ((cy,yr),(cn,nr)) if cont and name in r]
                if candidates:self.ranges[name]=(min(x[0] for x in candidates),max(x[1] for x in candidates))
            initialized=(iy&ino) if cy and cn else (iy if cy else ino if cn else initialized)
            body.append({'id':self.uid(),'op':'if','condition':self.truth(val),'then':yes,'else':no})
            return body,initialized,ry or rn,cy or cn
        raise CFrontendRefused('unsupported statement '+k)

    def build(self):
        matches=[n for n in self.ast.get('inner',[]) if n.get('kind')=='FunctionDecl' and
                 n.get('name')==self.function and any(x.get('kind')=='CompoundStmt' for x in n.get('inner',[]))]
        if len(matches)!=1:raise CFrontendRefused('requires exactly one matching definition')
        function=matches[0]
        if function.get('variadic'):raise CFrontendRefused('variadic function unsupported')
        ret=self.typ(function['type']['qualType'].split('(')[0].strip())
        self.alloc('$return_value',ret);initialized={'$returned'};parameters=[]
        for param in function['inner']:
            if param['kind']!='ParmVarDecl':continue
            name=param['name'];ident=param['id'];parameters.append(name)
            spec=self.bindings.get(name,{})
            if '*' in param['type']['qualType']:
                if spec.get('kind') not in ('input_buffer','output_buffer'):raise CFrontendRefused('pointer requires explicit fixed-buffer contract')
                cells=spec.get('cells',[])
                if not 1<=len(cells)<=32:raise CFrontendRefused('buffer arity outside profile')
                # Fixed, non-null, disjoint uint32 word buffers only. A
                # pointer-to-pointer is not a flat cell buffer and must not
                # borrow the one-level binding contract.
                pointer_type=param['type'].get('desugaredQualType',param['type']['qualType'])
                if pointer_type.count('*')!=1:raise CFrontendRefused('only one-level fixed buffers are admitted')
                base=pointer_type.replace('*','').strip()
                if self.typ(base)!='u32':raise CFrontendRefused('buffer element type must be uint32')
                labels=[]
                for cell in cells:
                    label=cell['label'];self.alloc(label,'u32');labels.append(label)
                    if spec['kind']=='input_buffer':
                        lo,hi=cell.get('min',0),cell.get('max',0xffffffff)
                        if not 0<=lo<=hi<=0xffffffff:raise CFrontendRefused('invalid input bounds')
                        self.ranges[label]=(lo,hi);self.inputs[label]={'min':lo,'max':hi};initialized.add(label);self.readonly.add(label)
                    else:self.outputs[label]=label
                self.arrays[ident]=labels;self.pointers[ident]=spec['kind']
                continue
            typ=self.typ(param['type']);lo,hi=bounds(typ)
            if spec.get('kind')=='constant':
                val=spec['value']
                if type(val)is not int or not lo<=val<=hi:raise CFrontendRefused('bad constant parameter')
                self.fixed[ident]=Value(val,typ,val,val);continue
            label=spec.get('label','$arg_'+name);self.alloc(label,typ)
            lo,hi=spec.get('min',lo),spec.get('max',hi)
            l,h=bounds(typ)
            if typ=='bool' or not l<=lo<=hi<=h:raise CFrontendRefused('invalid scalar input bounds/type')
            self.ranges[label]=(lo,hi);self.names[ident]=label;self.inputs[label]={'min':lo,'max':hi};initialized.add(label)
        if set(self.bindings)-set(parameters):raise CFrontendRefused('binding names do not match parameters')
        compound=next(x for x in function['inner'] if x['kind']=='CompoundStmt')
        body,_,_,continues=self.statement(compound,initialized)
        if continues:raise CFrontendRefused('not all structural paths return')
        body.append({'id':self.uid(),'op':'require','condition':eq({'var':'$returned'},True)})
        # Input domains are part of the executable contract, not just Python preflight.
        checks=[]
        for label,spec in self.inputs.items():
            typ=self.vars[label]['type'];l,h=bounds(typ);v=Value({'var':label},typ,l,h)
            for op,val in (('>=',spec['min']),('<=',spec['max'])):
                if (op=='>=' and val==l) or (op=='<=' and val==h):continue
                c=self.comparison(op,v,Value(val,typ,val,val),checks)
                checks.append({'id':self.uid(),'op':'require','condition':c})
        doc={'format':'fdisbull-il-1','role':'uil','variables':self.vars,'resources':{},'body':[{'id':self.uid(),'op':'set','var':'$returned','value':False}]+checks+body}
        try:validate_il(doc)
        except ValueError as exc:raise CFrontendRefused('shared IL admission: '+str(exc)) from exc
        return doc,self.inputs,self.outputs


def import_c(source: Path, function: str, *, clang: Path, bindings=None) -> ImportedFunction:
    """Invoke an explicitly selected local Clang on trusted C, not a shell."""
    source=Path(source).resolve();clang=Path(clang)
    if not clang.is_absolute() or not clang.is_file():raise CFrontendRefused('explicit Clang path required')
    raw=source.read_bytes()
    if not raw or len(raw)>131072:raise CFrontendRefused('C source size outside profile')
    command=[str(clang),'-target','x86_64-unknown-linux-gnu','-std=c11','-Werror',
             '-Xclang','-ast-dump=json','-fsyntax-only',str(source)]
    proc=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if source.read_bytes()!=raw:raise CFrontendRefused('source changed during Clang analysis')
    if proc.returncode:raise CFrontendRefused('Clang rejected source: '+proc.stderr[-2000:])
    if len(proc.stdout)>16*1024*1024:raise CFrontendRefused('AST size budget')
    ast=json.loads(proc.stdout)
    doc,inputs,outputs=Builder(ast,function,bindings).build()
    version=subprocess.run([str(clang),'--version'],capture_output=True,text=True,timeout=5).stdout.splitlines()[0]
    return ImportedFunction(doc,inputs,outputs,sha256(raw).hexdigest(),version,command,ast,function)
