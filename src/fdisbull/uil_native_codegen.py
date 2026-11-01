"""Ahead-of-time C/assembly realization and a bounded typed binary protocol.

No source files are written by the emitter. The C compiler owns platform ABIs;
the generated program owns independent frames, staged state and effect plans.
Native call diagnostics intentionally observe identities/counts, not arguments.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import threading

from .common_uil import (digest, default_value, expression_type, presentation_value,
                         typed, validate_realization, validate_type, SERVICES, RESOURCE_KINDS)
from .uil_runtime import TRACE_LIMITS


FORMAT = 'fdisbull-uil-native-sources-1'
ABI = 'fdisbull-uil-native-u64-stream-1'
TARGETS = ('macos-arm64', 'linux-x64', 'windows-x64')
ALU = ('add', 'sub', 'mul', 'and', 'or', 'xor')
LIMITS = {'max_steps':4000000, 'max_frame_cells':1048576,
          'max_heap_cells':4194304, 'max_json_bytes':4194304,
          'max_records':4096, 'max_input_bytes':134217728,
          'max_output_bytes':268435456}
INPUT_MAGIC = b'FUILIN1\0'
OUTPUT_MAGIC = b'FUILOUT1'


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cstr(value):
    # Fixed-width octal escapes cannot absorb a following hex/octal digit.
    return '"'+''.join(chr(b) if 32 <= b < 127 and b not in (34,92)
                       else '\\%03o' % b for b in value.encode('utf-8'))+'"'


def _cells(desc):
    return desc.get('length', 1)


def _layout(function):
    offsets=[];total=0
    for desc in function['variables']:
        offsets.append(total);total += _cells(desc)
    if total > LIMITS['max_frame_cells']:
        raise ValueError('native frame exceeds admitted cell budget')
    return offsets,total


def _width(typ):
    return 1 if typ=='bool' else (31 if typ=='resource' else int(typ[1:]))


def _bits(value, desc):
    typ=desc['type']
    return int(value) & ((1 << _width(typ))-1)


def _literal(value):
    return 'UINT64_C('+str(value)+')'


def _trace_cost(descriptors):
    return sum(4 if d.get('length',0)>TRACE_LIMITS['array_inline'] else
               max(1,d.get('length',1)) for d in descriptors)


_C_RUNTIME = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
typedef struct {uint32_t block,status;const char *error;} FdbCall;
typedef struct {
 uint32_t steps,depth,used[32],budgets[32],call_count,event_count,trace_cells;
 size_t heap_cells,event_bytes;const char *error;
 FdbCall calls[1024];char *events[256];
} FdbContext;
typedef struct {char *data;size_t length;int failed;} FdbJson;
static int fail(FdbContext *c,const char *message){if(!c->error){c->error=message;}return 1;}
static uint64_t mask(unsigned width){return width==64?UINT64_MAX:((UINT64_C(1)<<width)-1);}
static uint64_t *allocate(FdbContext *c,size_t count){
 size_t n=count?count:1;uint64_t *p;
 if(n>FDB_HEAP_CELLS || c->heap_cells>FDB_HEAP_CELLS-n){fail(c,"native heap cell budget exhausted");return NULL;}
 p=(uint64_t*)calloc(n,sizeof(uint64_t));if(!p){fail(c,"native allocation refused");return NULL;}
 c->heap_cells+=n;return p;
}
static void release(FdbContext *c,uint64_t *p,size_t count){if(p){free(p);c->heap_cells-=count?count:1;}}
static int enter(FdbContext *c,uint32_t budget){
 if(c->depth>=FDB_MAX_DEPTH){return fail(c,"orchestration call depth exhausted");}
 c->used[c->depth]=0;c->budgets[c->depth++]=budget;return 0;
}
static int charge(FdbContext *c){
 uint32_t i;c->steps++;if(c->steps>FDB_MAX_STEPS){return fail(c,"aggregate step budget exhausted");}
 for(i=0;i<c->depth;i++){if(++c->used[i]>c->budgets[i]){return fail(c,"function step budget exhausted");}}
 return 0;
}
static uint64_t cast_value(uint64_t value,unsigned in_width,int in_signed,unsigned out_width){
 if(in_signed && (value&(UINT64_C(1)<<(in_width-1)))){value|=~mask(in_width);}
 return value&mask(out_width);
}
static uint64_t compare_value(uint64_t a,uint64_t b,unsigned width,int sign,unsigned op){
 if(op==0){return a==b;}
 if(op==1){return a!=b;}
 if(sign){uint64_t bit=UINT64_C(1)<<(width-1);a^=bit;b^=bit;}
 if(op==2){return a<b;}
 if(op==3){return a<=b;}
 if(op==4){return a>b;}
 return a>=b;
}
static uint64_t divide_value(FdbContext *c,uint64_t a,uint64_t b,unsigned width,int sign,int remainder){
 uint64_t m=mask(width),aa=a,bb=b,q;int negative_a=0,negative_b=0;
 if(!b){fail(c,"integer division by zero");return 0;}
 if(sign){uint64_t bit=UINT64_C(1)<<(width-1);negative_a=(a&bit)!=0;negative_b=(b&bit)!=0;
  if(negative_a){aa=(UINT64_C(0)-a)&m;}
  if(negative_b){bb=(UINT64_C(0)-b)&m;}}
 q=remainder?aa%bb:aa/bb;
 if(remainder?negative_a:(negative_a!=negative_b)){q=UINT64_C(0)-q;}
 return q&m;
}
static uint64_t shift_value(FdbContext *c,uint64_t a,uint64_t b,unsigned width,int sign,int right){
 uint64_t result;if(b>=width){fail(c,"invalid shift count");return 0;}
 if(!right){return (a<<b)&mask(width);}
 result=a>>b;
 if(sign && b && (a&(UINT64_C(1)<<(width-1)))){result|=UINT64_MAX<<(width-(unsigned)b);}
 return result&mask(width);
}
static uint64_t parity(uint64_t a){unsigned n=0;a&=255;while(a){n+=(unsigned)(a&1);a>>=1;}return !(n&1);}
static int begin_call(FdbContext *c,uint32_t block,uint32_t input_cost,uint32_t *index){
 if(c->call_count>=FDB_CALLS || input_cost+1>FDB_TRACE_CELLS-c->trace_cells){return fail(c,"invocation trace budget exhausted");}
 c->trace_cells+=input_cost+1;*index=c->call_count++;
 c->calls[*index].block=block;c->calls[*index].status=0;c->calls[*index].error=NULL;return 0;
}
static int complete_call(FdbContext *c,uint32_t index,uint32_t cost){
 if(cost>FDB_TRACE_CELLS-c->trace_cells){c->calls[index].status=2;c->calls[index].error="invocation trace budget exhausted";return fail(c,c->calls[index].error);}
 c->trace_cells+=cost;c->calls[index].status=1;return 0;
}
static void append(FdbJson *j,const char *s){size_t n=strlen(s);if(j->failed){return;}
 if(n>FDB_JSON_BYTES-j->length){j->failed=1;return;}memcpy(j->data+j->length,s,n);j->length+=n;j->data[j->length]=0;}
static void number(FdbJson *j,uint64_t value){char text[32];snprintf(text,sizeof(text),"%" PRIu64,value);append(j,text);}
static void string(FdbJson *j,const char *value){const unsigned char *p=(const unsigned char*)value;char text[8];append(j,"\"");
 for(;*p;p++){if(*p=='"'){append(j,"\\\"");}else if(*p=='\\'){append(j,"\\\\");}else if(*p<32){snprintf(text,sizeof(text),"\\u%04x",*p);append(j,text);}else{text[0]=(char)*p;text[1]=0;append(j,text);}}append(j,"\"");}
static int effect(FdbContext *c,unsigned service,uint64_t resource,uint64_t looping){
#if FDB_RESOURCES == 0
 (void)service;(void)resource;(void)looping;
 return fail(c,"effect resource is unavailable");
#else
 const char *name,*payload;char head[128];int prefix;size_t bytes;char *event;
 if(resource>=FDB_RESOURCES){return fail(c,"effect resource is unavailable");}
 name=fdb_service_name(service);payload=fdb_resource_json((unsigned)resource);
 if(fdb_resource_kind((unsigned)resource)!=fdb_service_kind(service)){return fail(c,"effect resource kind differs");}
 prefix=snprintf(head,sizeof(head),"{\"service\":\"%s\",\"inputs\":[%" PRIu64 "%s],\"resource\":",name,resource,
   service==3?(looping?",true":",false"):"");
 if(prefix<0 || (size_t)prefix>=sizeof(head)){return fail(c,"effect framing failure");}
 bytes=(size_t)prefix+strlen(payload)+1;
 if(c->event_count>=FDB_EVENTS || bytes>FDB_EVENT_BYTES-c->event_bytes){return fail(c,"effect event budget exhausted");}
 event=(char*)malloc(bytes+1);if(!event)return fail(c,"native allocation refused");
 memcpy(event,head,(size_t)prefix);memcpy(event+prefix,payload,strlen(payload));event[bytes-1]='}';event[bytes]=0;
 c->event_bytes+=bytes;c->events[c->event_count++]=event;return 0;
#endif
}
static int read_exact(void *out,size_t count){return count==0 || fread(out,1,count,stdin)==count;}
static int read32(uint32_t *v){unsigned char b[4];if(!read_exact(b,4)){return 0;}*v=(uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;return 1;}
static int read64(uint64_t *v){unsigned char b[8];unsigned i;if(!read_exact(b,8)){return 0;}*v=0;for(i=0;i<8;i++){*v|=(uint64_t)b[i]<<(i*8);}return 1;}
static int write32(uint32_t v){unsigned char b[4];unsigned i;for(i=0;i<4;i++){b[i]=(unsigned char)(v>>(i*8));}return fwrite(b,1,4,stdout)==4;}
static int write64(uint64_t v){unsigned char b[8];unsigned i;for(i=0;i<8;i++){b[i]=(unsigned char)(v>>(i*8));}return fwrite(b,1,8,stdout)==8;}
static int write_cells(const uint64_t *v,size_t n){size_t i;for(i=0;i<n;i++){if(!write64(v[i])){return 0;}}return 1;}
'''


class _CEmitter:
    def __init__(self, functions, styles):
        self.functions=functions;self.styles=styles;self.lines=[];self.temp=0;self.loop=0
        self.plans={};self.ssa={};self.ssa_types=[]

    def line(self, value, depth=1):
        self.lines.append(' '*depth+value)

    def temporary(self, expression):
        name='t['+str(self.temp)+']';self.temp+=1
        self.line(name+'='+expression+';');return name

    def expression(self, expr, fn, offsets, constants, symbol):
        if 'ssa' in expr:return self.ssa[expr['ssa']]
        if 'var' in expr:
            slot=expr['var'];at=offsets[slot]
            return 'f+'+str(at) if 'length' in fn['variables'][slot] else self.temporary('f['+str(at)+']')
        if 'const' in expr:
            index=expr['const'];desc=fn['constants'][index]
            return _literal(_bits(constants[index],desc))
        op=expr['op']
        if op=='load':
            index=self.expression(expr['index'],fn,offsets,constants,symbol);desc=fn['variables'][expr['array']]
            self.line('if('+index+'>='+str(desc['length'])+'u){fail(c,"array load out of bounds");goto done;}')
            return self.temporary('f['+str(offsets[expr['array']])+'+(size_t)'+index+']')
        args=[self.expression(v,fn,offsets,constants,symbol) for v in expr['args']]
        typ=expr['type'];width=_width(typ);sign=int(typ.startswith('i'))
        if op in ALU:
            helper=symbol+'_'+op+'_'+self.styles[symbol][op].replace('-','_')
            result=helper+'('+','.join(args)+')&mask('+str(width)+')'
        elif op=='cast':
            source=self.type_of(expr['args'][0],fn)['type']
            result='('+args[0]+'!=0)' if typ=='bool' else 'cast_value('+args[0]+','+str(_width(source))+','+str(int(source.startswith('i')))+','+str(width)+')'
        elif op=='not':result='!'+args[0]
        elif op=='parity_even':result='parity('+args[0]+')'
        elif op=='select':result='('+args[0]+'?'+args[1]+':'+args[2]+')'
        elif op in ('eq','ne','lt','le','gt','ge'):
            source=self.type_of(expr['args'][0],fn)['type']
            result='compare_value('+','.join(args)+','+str(_width(source))+','+str(int(source.startswith('i')))+','+str(('eq','ne','lt','le','gt','ge').index(op))+')'
        elif op in ('div','mod'):
            result='divide_value(c,'+','.join(args)+','+str(width)+','+str(sign)+','+str(int(op=='mod'))+')'
        elif op in ('shl','shr'):
            result='shift_value(c,'+','.join(args)+','+str(width)+','+str(sign)+','+str(int(op=='shr'))+')'
        else:raise ValueError('unsupported native expression')
        result=self.temporary(result)
        if op in ('div','mod','shl','shr'):self.line('if(c->error){goto done;}')
        return result

    def type_of(self, expr, fn):
        if 'ssa' in expr:return self.ssa_types[expr['ssa']]
        if 'op' in expr and expr['op']!='load':return {'type':expr['type']}
        return expression_type(expr,fn)

    def body(self, nodes, fn, offsets, constants, symbol):
        for node in nodes:
            op=node['op']
            if op=='group':self.body(node['body'],fn,offsets,constants,symbol);continue
            self.line('if(charge(c)){goto done;}')
            if op=='set':
                value=self.expression(node['value'],fn,offsets,constants,symbol);slot=node['dst'];desc=fn['variables'][slot]
                self.line('memmove(f+'+str(offsets[slot])+','+value+','+str(desc['length'])+'u*sizeof(uint64_t));' if 'length' in desc else 'f['+str(offsets[slot])+']='+value+';')
            elif op=='store':
                index=self.expression(node['index'],fn,offsets,constants,symbol)
                value=self.expression(node['value'],fn,offsets,constants,symbol);desc=fn['variables'][node['array']]
                self.line('if('+index+'>='+str(desc['length'])+'u){fail(c,"array store out of bounds");goto done;}')
                self.line('f['+str(offsets[node['array']])+'+(size_t)'+index+']='+value+';')
            elif op=='if':
                condition=self.expression(node['condition'],fn,offsets,constants,symbol)
                self.line('if('+condition+'){');self.body(node['then'],fn,offsets,constants,symbol)
                self.line('}else{');self.body(node['else'],fn,offsets,constants,symbol);self.line('}')
            elif op=='while':
                loop='loop'+str(self.loop);self.loop+=1
                self.line('{uint32_t '+loop+'=0;for(;;){if(charge(c)){goto done;}')
                condition=self.expression(node['condition'],fn,offsets,constants,symbol)
                self.line('if(!'+condition+'){break;}')
                self.line('if('+loop+'++>='+str(node['limit'])+'u){fail(c,"loop bound exhausted");goto done;}')
                self.body(node['body'],fn,offsets,constants,symbol);self.line('}}')
            elif op in ('call','invoke'):
                callee=('fn'+str(node['function'])) if op=='call' else ('imp'+str(node['block']))
                child=self.functions[callee];child_offsets,_=_layout(child)
                inc=sum(_cells(child['variables'][s]) for s in child['inputs']);outc=sum(_cells(child['variables'][s]) for s in child['outputs'])
                values=[self.expression(v,fn,offsets,constants,symbol) for v in node['inputs']]
                self.line('{uint64_t *a=allocate(c,'+str(inc)+'),*r=allocate(c,'+str(outc)+');')
                self.line('if(!a||!r){release(c,a,'+str(inc)+');release(c,r,'+str(outc)+');goto done;}')
                at=0
                for value,slot in zip(values,child['inputs']):
                    desc=child['variables'][slot];n=_cells(desc)
                    self.line('memcpy(a+'+str(at)+','+value+','+str(n)+'u*sizeof(uint64_t));' if 'length' in desc else 'a['+str(at)+']='+value+';');at+=n
                self.line('if('+callee+'(c,a,r,NULL)){release(c,a,'+str(inc)+');release(c,r,'+str(outc)+');goto done;}')
                at=0
                for slot,child_slot in zip(node['outputs'],child['outputs']):
                    n=_cells(child['variables'][child_slot]);self.line('memcpy(f+'+str(offsets[slot])+',r+'+str(at)+','+str(n)+'u*sizeof(uint64_t));');at+=n
                self.line('release(c,a,'+str(inc)+');release(c,r,'+str(outc)+');}')
            elif op=='require':
                value=self.expression(node['condition'],fn,offsets,constants,symbol)
                self.line('if(!'+value+'){fail(c,"required condition failed");goto done;}')
            elif op=='effect':
                values=[self.expression(v,fn,offsets,constants,symbol) for v in node['inputs']]
                service=('text.show','image.show','sound.play','music.start','music.stop').index(node['service'])
                self.line('if(effect(c,'+str(service)+','+values[0]+','+(values[1] if len(values)>1 else '0')+')){goto done;}')
            elif op=='return':self.line('goto success;')
            else:raise ValueError('unsupported native statement')

    def function(self, symbol, fn, constants, initial):
        from .uil_dataflow import scalar_value_plan
        self.lines=[];self.temp=0;self.loop=0;offsets,total=_layout(fn)
        plan=scalar_value_plan(fn);self.plans[symbol]=plan;final=[];self.ssa={}
        if plan is None:self.body(fn['body'],fn,offsets,constants,symbol)
        else:
            self.ssa_types=plan['value_types']
            for slot,value in enumerate(plan['initial_values']):self.ssa[value]=self.temporary('f['+str(offsets[slot])+']')
            for node in plan['body']:
                self.line('if(charge(c)){goto done;}')
                if node['op']=='define':self.ssa[node['value']]=self.expression(node['expression'],fn,offsets,constants,symbol)
                elif node['op']=='require':
                    value=self.expression(node['condition'],fn,offsets,constants,symbol)
                    self.line('if(!'+value+'){fail(c,"required condition failed");goto done;}')
                elif node['op']=='return':self.line('goto success;')
                elif node['op']!='alias':raise ValueError('unsupported native scalar value plan')
            final=['f['+str(offsets[slot])+']='+self.ssa[value]+';' for slot,value in enumerate(plan['final_values'])]
        body=self.lines;nt=self.temp
        if nt>LIMITS['max_frame_cells']:raise ValueError('native temporary cell budget exceeded')
        lines=['static int '+symbol+'(FdbContext *c,const uint64_t *args,uint64_t *out,uint64_t *state){',
               'uint64_t *f=allocate(c,'+str(total)+'),*t=allocate(c,'+str(nt)+');int entered=0,ok=0;',
               'if(!f||!t){goto done;}']
        for i,(value,desc) in enumerate(zip(initial,fn['variables'])):
            values=value if 'length' in desc else [value]
            element={'type':desc['type'].split('-')[0]}
            for j,v in enumerate(values):
                bits=_bits(v,element)
                if bits:lines.append('f['+str(offsets[i]+j)+']='+_literal(bits)+';')
        at=0
        for slot in fn['inputs']:
            n=_cells(fn['variables'][slot]);lines.append('memcpy(f+'+str(offsets[slot])+',args+'+str(at)+','+str(n)+'u*sizeof(uint64_t));');at+=n
        lines += ['if(enter(c,'+str(fn['max_steps'])+')){goto done;}', 'entered=1;',*body,'success:', 'if(c->error){goto done;}',*final]
        at=0
        for slot in fn['outputs']:
            n=_cells(fn['variables'][slot]);lines.append('memcpy(out+'+str(at)+',f+'+str(offsets[slot])+','+str(n)+'u*sizeof(uint64_t));');at+=n
        lines += ['if(state){memcpy(state,f,'+str(total)+'u*sizeof(uint64_t));}', 'ok=1;',
                  'done:if(entered){c->depth--;}', 'release(c,t,'+str(nt)+');release(c,f,'+str(total)+');return ok?0:1;}']
        return '\n'.join(lines)+'\n'


def _numeric_sources(styles, target):
    lines=['#include <stdint.h>','#include <stddef.h>',
           '#if defined(__GNUC__) || defined(__clang__)','#define FDB_NOINLINE __attribute__((noinline))','#else','#error GNU-compatible compiler required','#endif',
           'static uint64_t counts['+str(len(styles))+'][6];',
           'void fdb_math_reset(void){size_t i,j;for(i=0;i<'+str(len(styles))+';i++){for(j=0;j<6;j++){counts[i][j]=0;}}}',
           'uint64_t fdb_math_count(unsigned module,unsigned op){return module<'+str(len(styles))+'&&op<6?counts[module][op]:0;}']
    prototypes=['void fdb_math_reset(void);','uint64_t fdb_math_count(unsigned,unsigned);'];bindings=[]
    for module,(symbol,ops) in enumerate(styles.items()):
        for index,op in enumerate(ALU):
            style=ops[op];helper=symbol+'_'+op+'_'+style.replace('-','_')
            prototypes.append('uint64_t '+helper+'(uint64_t,uint64_t);')
            lines.append('FDB_NOINLINE uint64_t '+helper+'(uint64_t a,uint64_t b){counts['+str(module)+']['+str(index)+']++;')
            if style=='portable-c':
                token={'add':'+','sub':'-','mul':'*','and':'&','or':'|','xor':'^'}[op]
                lines.append('return a'+token+'b;}')
            elif style=='native-asm':
                if target=='macos-arm64':
                    instruction={'add':'add','sub':'sub','mul':'mul','and':'and','or':'orr','xor':'eor'}[op]
                    lines.append('uint64_t r;__asm__ __volatile__("'+instruction+' %0, %1, %2":"=r"(r):"r"(a),"r"(b):"cc");return r;}')
                else:
                    instruction={'add':'addq','sub':'subq','mul':'imulq','and':'andq','or':'orq','xor':'xorq'}[op]
                    lines.append('__asm__ __volatile__("'+instruction+' %1, %0":"+r"(a):"r"(b):"cc");return a;}')
            else:raise ValueError('unsupported native arithmetic provider')
            bindings.append({'symbol':symbol,'operation':op,'provider':style,'helper':helper,'module':module})
    return '\n'.join(lines)+'\n','\n'.join(prototypes)+'\n',bindings


def _resources(resources):
    kinds={'text':0,'graphic':1,'sound':2,'music':3};services=('text.show','image.show','sound.play','music.start','music.stop')
    lines=['static const char *fdb_service_name(unsigned service){static const char *names[5]={'+','.join(_cstr(s) for s in services)+'};return service<5?names[service]:"unsupported";}',
           'static unsigned fdb_service_kind(unsigned service){static const unsigned kinds[5]={0,1,2,3,3};return service<5?kinds[service]:99;}',
           'static unsigned fdb_resource_kind(unsigned index){switch(index){']
    lines += ['case '+str(i)+':return '+str(kinds[r['kind']])+';' for i,r in enumerate(resources)]
    lines += ['default:return 99;}}','static const char *fdb_resource_json(unsigned index){switch(index){']
    lines += ['case '+str(i)+':return '+_cstr(_json(r))+';' for i,r in enumerate(resources)]
    return '\n'.join(lines+['default:return "null";}}'])+'\n'


def _render_diagnostics(identities, imports, bindings):
    prefix=_json({**identities,'call_observation':'identity-and-counts-only'})[:-1]
    def append_fragment(text):return 'append(j,'+_cstr(text)+');'
    lines=['static int diagnostics(FdbContext *c,unsigned status,FdbJson *j){uint32_t i;int comma=0;',
           'append(j,'+_cstr(prefix+',"status":')+');string(j,status==0?"complete":status==1?"pending_host":"refused");',
           append_fragment(',"steps":')+'number(j,c->steps);',
           'if(c->error){'+append_fragment(',"error":')+'string(j,c->error);}',
           append_fragment(',"calls":[')+'for(i=0;i<c->call_count;i++){if(i){append(j,",");}switch(c->calls[i].block){']
    for index,metadata in imports.items():
        lines.append('case '+str(index)+':append(j,'+_cstr(_json(metadata)[:-1])+');break;')
    lines += ['default:return 1;}'+append_fragment(',"status":')+'string(j,c->calls[i].status==1?"complete":c->calls[i].status==2?"refused":"entered");',
              'if(c->calls[i].error){'+append_fragment(',"error":')+'string(j,c->calls[i].error);}append(j,"}");}',
              append_fragment('],"events":[')+'if(status==1){for(i=0;i<c->event_count;i++){if(i){append(j,",");}append(j,c->events[i]);}}',
              append_fragment('],"arithmetic_calls":[')]
    for binding in bindings:
        symbol=binding['symbol'];kind='functions' if symbol.startswith('fn') else 'imports';index=int(symbol[2:] if kind=='functions' else symbol[3:])
        data={'kind':kind,'index':index,'operation':binding['operation'],'provider':binding['provider']}
        lines += ['{uint64_t n=fdb_math_count('+str(binding['module'])+','+str(ALU.index(binding['operation']))+');if(n){if(comma){append(j,",");}comma=1;append(j,'+_cstr(_json(data)[:-1]+',"calls":')+');number(j,n);append(j,"}");}}']
    lines += ['append(j,"]}");return j->failed;}']
    return '\n'.join(lines)+'\n'


def _main_source(entry, initial, abi):
    offsets,total=_layout(entry);ic=abi['input_cells'];oc=abi['output_cells'];lines=[]
    lines += ['static int execute_stream(void){unsigned char magic[8];uint32_t records,cells,record;size_t i;',
              'if(!read_exact(magic,8)||memcmp(magic,"FUILIN1\\0",8)||!read32(&records)||!read32(&cells)||records>FDB_MAX_RECORDS||cells!='+str(ic)+'){return 2;}',
              'if(fwrite("FUILOUT1",1,8,stdout)!=8||!write32(records)){return 2;}',
              'for(record=0;record<records;record++){FdbContext *c=(FdbContext*)calloc(1,sizeof(FdbContext));',
              'uint64_t *args=(uint64_t*)calloc('+str(max(1,ic))+',8),*original=(uint64_t*)calloc('+str(max(1,total))+',8),*state=(uint64_t*)calloc('+str(max(1,total))+',8),*out=(uint64_t*)calloc('+str(max(1,oc))+',8);',
              'FdbJson j;unsigned status;int bad=0;j.data=(char*)malloc(FDB_JSON_BYTES+1);j.length=0;j.failed=0;',
              'if(!c||!args||!original||!state||!out||!j.data){free(c);free(args);free(original);free(state);free(out);free(j.data);return 2;}j.data[0]=0;']
    if ic:
        lines.append('for(i=0;i<'+str(ic)+';i++){if(!read64(args+i)){bad=1;}}')
    at=0
    for slot in entry['inputs']:
        desc=entry['variables'][slot];n=_cells(desc);typ=desc['type'].split('-')[0];bits=_width(typ)
        # Every u64 bit pattern is canonical; do not emit a tautological bound.
        if bits<64:
            lines += ['for(i=0;i<'+str(n)+';i++){if(args['+str(at)+'+i]>mask('+str(bits)+')){bad=1;}}']
        at+=n
    lines += ['if(bad){free(c);free(args);free(original);free(state);free(out);free(j.data);return 2;}']
    for index,(desc,value) in enumerate(zip(entry['variables'],initial)):
        element={'type':desc['type'].split('-')[0]}
        for j,v in enumerate(value if 'length' in desc else [value]):
            bits=_bits(v,element)
            if bits:lines.append('original['+str(offsets[index]+j)+']='+_literal(bits)+';')
    at=0
    for slot in entry['inputs']:
        n=_cells(entry['variables'][slot]);lines.append('memcpy(original+'+str(offsets[slot])+',args+'+str(at)+','+str(n)+'u*8);');at+=n
    lines += ['fdb_math_reset();status=fn'+str(abi['entry'])+'(c,args,out,state)?2:(c->event_count?1:0);',
              'if(diagnostics(c,status,&j)){bad=1;}',
              'if(!bad && (!write32((uint32_t)j.length)||!write64('+str(total)+')||!write64(status==0?'+str(oc)+':0)||!write64(status==1?'+str(total)+':0)||fwrite(j.data,1,j.length,stdout)!=j.length)){bad=1;}',
              'if(!bad && !write_cells(status==0?state:original,'+str(total)+')){bad=1;}',
              'if(!bad && status==0 && !write_cells(out,'+str(oc)+')){bad=1;}',
              'if(!bad && status==1 && !write_cells(state,'+str(total)+')){bad=1;}',
              'for(i=0;i<c->event_count;i++){free(c->events[i]);}',
              'free(c);free(args);free(original);free(state);free(out);free(j.data);if(bad){return 2;}}',
              'if(fgetc(stdin)!=EOF || ferror(stdin) || fflush(stdout)){return 2;}', 'return 0;}',
              '#ifndef FDB_NATIVE_NO_MAIN', 'int main(void){', '#ifdef _WIN32', '_setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);', '#endif',
              'return execute_stream();}', '#endif']
    return '\n'.join(lines)+'\n'


def _legacy_adapter(functions, entry):
    def effects(body):
        for node in body:
            if node['op']=='effect':return True
            if node['op'] in ('while','group') and effects(node['body']):return True
            if node['op']=='if' and (effects(node['then']) or effects(node['else'])):return True
        return False
    ins=[entry['variables'][s] for s in entry['inputs']];outs=[entry['variables'][s] for s in entry['outputs']]
    admitted=(len(ins)==len(outs)==1 and ins[0]==outs[0] and ins[0]['type']=='u32-array'
              and not any(effects(fn['body']) for fn in functions.values()))
    return ({'available':True,'symbol':'fdb_block','words':ins[0]['length'],'ownership':'serialized-host-copy-in-copy-out',
             'status':{'complete':0,'refused':1},'cut':0,'capture_local':False,
             'projection':'one u32 array output; other entry slots are invocation-local'} if admitted else
            {'available':False,'reason':'requires one same-length u32-array input/output and an effects-free closure'})


def _legacy_sources(adapter, entry_index):
    header='''#ifndef FDISBULL_COMMON_NATIVE_CORE_1
#define FDISBULL_COMMON_NATIVE_CORE_1
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifndef FDISBULL_NATIVE_MEMORY_ABI_1
#define FDISBULL_NATIVE_MEMORY_ABI_1
typedef struct { uint32_t status, steps, cut; } FdbBlockResult;
#endif
/* The host owns a writable array of the declared length and serializes calls.
 * Local capture is unsupported. Refusal leaves every caller word unchanged. */
'''
    header+='#define FDB_NATIVE_ARENA_ADAPTER '+str(int(adapter['available']))+'\n'
    if not adapter['available']:
        return header+'/* No legacy arena symbol: this entry has a different contract. */\n#endif\n',''
    words=adapter['words']
    header+='#define FDB_NATIVE_ARENA_WORDS '+str(words)+'u\n#ifdef __cplusplus\nextern "C" {\n#endif\nFdbBlockResult fdb_block(uint32_t *words);\n#ifdef __cplusplus\n}\n#endif\n#endif\n'
    source='''FdbBlockResult fdb_block(uint32_t *words){
 FdbBlockResult result={1u,0u,0u};FdbContext *c;uint64_t *a,*o;size_t i;
 if(!words){return result;}
 c=(FdbContext*)calloc(1,sizeof(FdbContext));
 a=(uint64_t*)calloc(FDB_NATIVE_ARENA_WORDS,sizeof(uint64_t));
 o=(uint64_t*)calloc(FDB_NATIVE_ARENA_WORDS,sizeof(uint64_t));
 if(!c||!a||!o){free(c);free(a);free(o);return result;}
 for(i=0;i<FDB_NATIVE_ARENA_WORDS;i++){a[i]=words[i];}
 fdb_math_reset();
'''
    source+='if(!fn'+str(entry_index)+'(c,a,o,NULL) && !c->error && !c->event_count){\n'
    source+='for(i=0;i<FDB_NATIVE_ARENA_WORDS;i++){if(o[i]>UINT32_MAX){break;}}\n'
    source+='if(i==FDB_NATIVE_ARENA_WORDS){for(i=0;i<FDB_NATIVE_ARENA_WORDS;i++){words[i]=(uint32_t)o[i];}result.status=0u;}}\n'
    source+='result.steps=c->steps;for(i=0;i<c->event_count;i++){free(c->events[i]);}\nfree(c);free(a);free(o);return result;}\n'
    return header,source


def emit_native_sources(program, presentation, catalog, orchestration, *, target, link_lock):
    """Return native source/ABI metadata; validate before producing any output."""
    from .uil_link import validate_native_link, native_operation_arithmetic
    from . import uil_dataflow
    if target not in TARGETS:raise ValueError('unsupported native target')
    program,presentation,catalog,orchestration,link_lock=deepcopy((program,presentation,catalog,orchestration,link_lock))
    resolved=validate_realization(program,presentation,catalog,orchestration)['resolved'];validate_native_link(link_lock)
    identities={name+'_sha256':digest(value) for name,value in [('program',program),('presentation',presentation),('catalog',catalog),('orchestration',orchestration)]}
    if link_lock['target']!=target or link_lock['closure']!=identities:raise ValueError('native lock closure/target differs')
    functions={'fn'+str(i):fn for i,fn in enumerate(program['functions'])}
    functions.update({'imp'+str(i):impl['function'] for i,impl in sorted(resolved.items())})
    for fn in functions.values():
        if any(d['type']=='text' for d in fn['variables']+fn['constants']):raise ValueError('native profile does not admit text-typed slots')
        _layout(fn)
    styles={}
    for symbol in functions:
        kind='functions' if symbol.startswith('fn') else 'imports';index=int(symbol[2:] if kind=='functions' else symbol[3:])
        styles[symbol]={op:native_operation_arithmetic(link_lock,kind,index,op) for op in ALU}
    entry=program['functions'][program['entry']]
    legacy_adapter=_legacy_adapter(functions,entry)
    abi={'format':ABI,'entry':program['entry'],'word':'u64-le-bit-pattern','input_types':[entry['variables'][i] for i in entry['inputs']],
         'state_types':entry['variables'],'output_types':[entry['variables'][i] for i in entry['outputs']],
         'call_observation':'identity-and-counts-only','limits':deepcopy(LIMITS),'trace_limits':deepcopy(TRACE_LIMITS),
         'legacy_arena_adapter':legacy_adapter}
    for name in ('input','state','output'):abi[name+'_cells']=sum(_cells(d) for d in abi[name+'_types'])
    closure={'program':program,'presentation':presentation,'catalog':catalog,'orchestration':orchestration,'link_lock':link_lock,'target':target,
             'abi':abi,'generator_sha256':_sha(Path(__file__).read_bytes()),
             'dataflow_generator_sha256':_sha(Path(uil_dataflow.__file__).read_bytes()),'profile':'typed-u64-c11-aot-1'}
    identities.update(closure_sha256=digest(closure),link_lock_sha256=link_lock['sha256'])
    numeric,prototypes,bindings=_numeric_sources(styles,target)
    defines={'FDB_MAX_STEPS':LIMITS['max_steps'],'FDB_HEAP_CELLS':LIMITS['max_heap_cells'],'FDB_JSON_BYTES':LIMITS['max_json_bytes'],
             'FDB_MAX_RECORDS':LIMITS['max_records'],'FDB_MAX_DEPTH':orchestration['max_call_depth'],'FDB_RESOURCES':len(presentation['resources']),
             'FDB_CALLS':TRACE_LIMITS['calls'],'FDB_TRACE_CELLS':TRACE_LIMITS['cells'],'FDB_EVENTS':TRACE_LIMITS['events'],'FDB_EVENT_BYTES':TRACE_LIMITS['event_bytes']}
    native_header,legacy_source=_legacy_sources(legacy_adapter,program['entry'])
    header='#include <stdint.h>\n#include "native-core.h"\n'+prototypes+'\n'+'\n'.join('#define '+key+' '+str(value)+'u' for key,value in defines.items())+'\n'
    source=header+_resources(presentation['resources'])+_C_RUNTIME
    source+='\n'.join('static int '+symbol+'(FdbContext*,const uint64_t*,uint64_t*,uint64_t*);' for symbol in functions)+'\n'
    emitter=_CEmitter(functions,styles)
    for index,fn in enumerate(program['functions']):
        p=presentation['functions'][index]
        constants=[presentation_value(v,d) for v,d in zip(p['constants'],fn['constants'])]
        initial=[presentation_value(v,d) for v,d in zip(p['initial'],fn['variables'])]
        source+=emitter.function('fn'+str(index),fn,constants,initial)
    import_meta={}
    for index,impl in sorted(resolved.items()):
        fn=impl['function'];constants=[presentation_value(v,d) for v,d in zip(impl['constants'],fn['constants'])]
        # Impl and invocation wrapper are separate actual native functions.
        body=emitter.function('imp'+str(index),fn,constants,[default_value(d) for d in fn['variables']])
        body=body.replace('static int imp'+str(index)+'(', 'static int backing'+str(index)+'(',1)
        source+=body
        ins=[fn['variables'][i] for i in fn['inputs']];outs=[fn['variables'][i] for i in fn['outputs']]
        import_meta[index]={'block':index,'semantic_id':program['imports'][index]['semantic_id'],'implementation':impl['id'],'language':impl['language'],
                            'observation':'identity-and-counts-only','input_count':len(ins),'output_count':len(outs),
                            'input_trace_cells':_trace_cost(ins),'output_trace_cells':_trace_cost(outs)}
        source+='static int imp'+str(index)+'(FdbContext *c,const uint64_t *a,uint64_t *o,uint64_t *state){uint32_t call=0;\n'
        source+='if(begin_call(c,'+str(index)+','+str(_trace_cost(ins))+',&call)){return 1;}\n'
        source+='if(backing'+str(index)+'(c,a,o,state)){c->calls[call].status=2;c->calls[call].error=c->error;return 1;}\n'
        source+='return complete_call(c,call,'+str(_trace_cost(outs))+');}\n'
    source+=legacy_source+_render_diagnostics(identities,import_meta,bindings)
    initial=[presentation_value(v,d) for v,d in zip(presentation['functions'][program['entry']]['initial'],entry['variables'])]
    source+=_main_source(entry,initial,abi)
    sources={'program.c':source,'numeric.c':numeric,'native-core.h':native_header}
    return {'format':FORMAT,'stage':'source-only','target':target,'profile':'typed-u64-c11-aot-1',
            **identities,'sources':sources,'abi':abi,'closure':closure,'link_lock':link_lock,'arithmetic_bindings':bindings,
            'call_bindings':{str(i):metadata for i,metadata in import_meta.items()},
            'scalar_value_plans':emitter.plans,
            'legacy_arena_adapter':deepcopy(legacy_adapter),
            'source_artifacts':{name:_sha(text.encode()) for name,text in sources.items()},'native_execution':False,
            'host_effect_execution':False,'runtime_ast_interpreter':False,
            'scope':'native pure kernel and planned effects; no window/media execution; import diagnostics observe identity/counts only'}


def _admit_abi(manifest):
    abi=manifest.get('abi')
    if type(abi) is not dict or abi.get('format')!=ABI or abi.get('word')!='u64-le-bit-pattern':raise ValueError('unsupported native ABI')
    expected={'format','entry','word','input_types','state_types','output_types','call_observation','limits','trace_limits','input_cells','state_cells','output_cells','legacy_arena_adapter'}
    if set(abi)!=expected or type(abi['entry']) is not int or not 0<=abi['entry']<256 or abi['limits']!=LIMITS or abi['trace_limits']!=TRACE_LIMITS or abi['call_observation']!='identity-and-counts-only':raise ValueError('native ABI policy differs')
    closure=manifest.get('closure')
    if type(closure) is not dict or closure.get('abi')!=abi or digest(closure)!=manifest.get('closure_sha256'):raise ValueError('native ABI closure differs')
    for name in ('input','state','output'):
        types=abi.get(name+'_types')
        if type(types) is not list or len(types)>(1024 if name=='state' else 256):raise ValueError('invalid native typed slots')
        for desc in types:
            validate_type(desc)
            if desc['type']=='text':raise ValueError('native text slots unsupported')
        count=sum(_cells(d) for d in types)
        if type(abi.get(name+'_cells')) is not int or abi[name+'_cells']!=count or count>LIMITS['max_frame_cells']:raise ValueError('native cell layout differs')
    return abi


def _admit_diagnostics(manifest,row):
    required={'program_sha256','presentation_sha256','catalog_sha256','orchestration_sha256','closure_sha256','link_lock_sha256',
              'status','steps','call_observation','calls','events','arithmetic_calls'}
    if set(row)-required-{'error'} or not required<=set(row):raise ValueError('native diagnostic fields differ')
    if 'error' in row and (type(row['error']) is not str or len(row['error'].encode())>1024):raise ValueError('native diagnostic error outside bounds')
    if row['status']=='refused' and not row.get('error'):raise ValueError('native refusal lacks diagnosis')
    if row['status']!='refused' and 'error' in row:raise ValueError('completed native transaction has an error')
    profile=manifest.get('source_profile',manifest);bindings=profile.get('call_bindings',{})
    cells=0;refused=False
    for call in row['calls']:
        if type(call) is not dict or type(call.get('block')) is not int or str(call['block']) not in bindings:raise ValueError('native call identity is unavailable')
        expected=bindings[str(call['block'])]
        if any(call.get(k)!=v for k,v in expected.items()) or set(call)-set(expected)-{'status','error'}:raise ValueError('native call binding differs')
        if call.get('status') not in ('complete','refused') or refused:raise ValueError('native call completion differs')
        if call['status']=='refused':
            refused=True
            if row['status']!='refused' or type(call.get('error')) is not str or len(call['error'].encode())>1024:raise ValueError('invalid native call refusal')
        elif 'error' in call:raise ValueError('completed native call has an error')
        cells+=1+expected['input_trace_cells']+(expected['output_trace_cells'] if call['status']=='complete' else 0)
    if cells>TRACE_LIMITS['cells']:raise ValueError('native call trace exceeds budget')
    resources=manifest['closure']['presentation']['resources'];event_bytes=0
    for event in row['events']:
        if type(event) is not dict or set(event)!={'service','inputs','resource'} or event.get('service') not in SERVICES:raise ValueError('invalid native event service')
        signature=SERVICES[event['service']];values=event['inputs']
        if type(values) is not list or len(values)!=len(signature) or any(not typed(v,{'type':t}) for v,t in zip(values,signature)):raise ValueError('native event argument types differ')
        index=values[0]
        if index>=len(resources) or event['resource']!=resources[index] or resources[index]['kind']!=RESOURCE_KINDS[event['service']]:raise ValueError('native event resource differs')
        event_bytes+=len(json.dumps(event,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    if event_bytes>TRACE_LIMITS['event_bytes'] or bool(row['events'])!=(row['status']=='pending_host'):raise ValueError('native event observation differs')
    if type(row['arithmetic_calls']) is not list:raise ValueError('invalid native arithmetic observations')
    allowed={}
    for binding in profile.get('arithmetic_bindings',[]):
        symbol=binding['symbol'];kind='functions' if symbol.startswith('fn') else 'imports'
        index=int(symbol[2:] if kind=='functions' else symbol[3:])
        allowed[(kind,index,binding['operation'])]=binding['provider']
    seen=set()
    if len(row['arithmetic_calls'])>len(allowed):raise ValueError('native arithmetic observation count differs')
    for call in row['arithmetic_calls']:
        if type(call) is not dict or set(call)!={'kind','index','operation','provider','calls'} or type(call['index']) is not int:raise ValueError('invalid native arithmetic observation')
        key=(call['kind'],call['index'],call['operation'])
        if key not in allowed or key in seen or allowed[key]!=call['provider'] or type(call['calls']) is not int or not 0<call['calls']<=LIMITS['max_steps']*1000000:raise ValueError('native arithmetic provider/count differs')
        seen.add(key)


def _flatten(values, descriptors):
    if type(values) is not list or len(values)!=len(descriptors):raise ValueError('native input arity differs')
    result=[]
    for value,desc in zip(values,descriptors):
        if not typed(value,desc):raise ValueError('native input value/type differs')
        element={'type':desc['type'].split('-')[0]}
        result.extend(_bits(v,element) for v in (value if 'length' in desc else [value]))
    return result


def _encode_records(manifest, records):
    abi=_admit_abi(manifest)
    if type(records) is not list or len(records)>LIMITS['max_records']:raise ValueError('native record count exceeds profile')
    size=16+len(records)*abi['input_cells']*8
    if size>LIMITS['max_input_bytes']:raise ValueError('native input stream budget exceeded; use smaller batches')
    parts=[INPUT_MAGIC,struct.pack('<II',len(records),abi['input_cells'])]
    for values in records:
        cells=_flatten(values,abi['input_types'])
        parts.append(struct.pack('<'+'Q'*len(cells),*cells))
    return b''.join(parts)


def encode_native_inputs(manifest, inputs):
    """Encode one exact entry argument list; arrays remain typed fixed arrays."""
    return _encode_records(manifest,[inputs])


def _restore(cells, descriptors):
    values=[];at=0
    for desc in descriptors:
        typ=desc['type'].split('-')[0];width=_width(typ);n=_cells(desc);out=[]
        for raw in cells[at:at+n]:
            if raw>=(1<<width):raise ValueError('noncanonical native typed cell')
            out.append(bool(raw) if typ=='bool' else raw-(1<<width) if typ.startswith('i') and raw>=(1<<(width-1)) else raw)
        values.append(out if 'length' in desc else out[0]);at+=n
    return values


def decode_native_results(manifest, raw):
    """Validate framing, identities and typed cell ranges before returning rows."""
    abi=_admit_abi(manifest)
    if not isinstance(raw,bytes) or len(raw)>LIMITS['max_output_bytes'] or len(raw)<12 or raw[:8]!=OUTPUT_MAGIC:raise ValueError('invalid native result stream')
    count=struct.unpack_from('<I',raw,8)[0]
    if count>LIMITS['max_records']:raise ValueError('native result count exceeds profile')
    at=12;results=[]
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate native diagnostic key')
            result[k]=v
        return result
    for _ in range(count):
        if len(raw)-at<28:raise ValueError('truncated native result header')
        n,sc,oc,pc=struct.unpack_from('<IQQQ',raw,at);at+=28
        if n>LIMITS['max_json_bytes'] or n>len(raw)-at:raise ValueError('native diagnostic length outside bounds')
        def constant(value):raise ValueError('nonfinite native diagnostic constant')
        try:row=json.loads(raw[at:at+n],object_pairs_hook=pairs,parse_constant=constant)
        except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError('invalid native diagnostic JSON') from exc
        at+=n
        if type(row) is not dict or row.get('status') not in ('complete','pending_host','refused'):raise ValueError('invalid native result status')
        for key in ('program_sha256','presentation_sha256','catalog_sha256','orchestration_sha256','closure_sha256','link_lock_sha256'):
            if row.get(key)!=manifest.get(key):raise ValueError('native result realization identity differs')
        expected=(abi['state_cells'],abi['output_cells'] if row['status']=='complete' else 0,abi['state_cells'] if row['status']=='pending_host' else 0)
        if (sc,oc,pc)!=expected:raise ValueError('native result typed body shape differs')
        if 8*(sc+oc+pc)>len(raw)-at:raise ValueError('truncated native result cells')
        if type(row.get('steps')) is not int or not 0<=row['steps']<=LIMITS['max_steps']+1:raise ValueError('invalid native step count')
        if row.get('call_observation')!='identity-and-counts-only' or type(row.get('calls')) is not list or len(row['calls'])>TRACE_LIMITS['calls']:raise ValueError('invalid native call observation')
        if type(row.get('events')) is not list or len(row['events'])>TRACE_LIMITS['events']:raise ValueError('invalid native events')
        _admit_diagnostics(manifest,row)
        for name,ncells,types in [('state',sc,abi['state_types']),('outputs',oc,abi['output_types']),('proposed_state',pc,abi['state_types'])]:
            if ncells:
                cells=struct.unpack_from('<'+'Q'*ncells,raw,at);at+=ncells*8
                row[name]=_restore(cells,types)
            elif name!='proposed_state' or row['status']=='pending_host':row[name]=[]
        results.append(row)
    if at!=len(raw):raise ValueError('trailing native result bytes')
    return results


def run_native_records(command, manifest, inputs, cwd=None, timeout=60):
    """Run owned streaming probes with bounded in-memory I/O; never write logs."""
    if type(command) not in (list,tuple) or not command or any(type(v) is not str or '\0' in v for v in command):raise ValueError('native command requires explicit argv')
    if type(timeout) not in (int,float) or not 0<timeout<=3600:raise ValueError('invalid native timeout')
    data=_encode_records(manifest,inputs);overflow=threading.Event();outputs=[];errors=[]
    process=subprocess.Popen(command,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def read(stream,chunks,limit):
        count=0
        while True:
            block=stream.read(65536)
            if not block:break
            count+=len(block)
            if count>limit:overflow.set();process.kill();break
            chunks.append(block)
    def write():
        try:process.stdin.write(data);process.stdin.close()
        except (BrokenPipeError,OSError):pass
    threads=[threading.Thread(target=read,args=(process.stdout,outputs,LIMITS['max_output_bytes']),daemon=True),
             threading.Thread(target=read,args=(process.stderr,errors,65536),daemon=True),threading.Thread(target=write,daemon=True)]
    for thread in threads:thread.start()
    try:process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill();process.wait();raise ValueError('native probe timed out; no retry or fallback') from None
    finally:
        for thread in threads:thread.join(timeout=2)
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream is not None and not stream.closed:stream.close()
    if overflow.is_set():raise ValueError('native probe output budget exhausted')
    if process.returncode:raise ValueError('native probe failed with exit '+str(process.returncode)+': '+b''.join(errors)[-1024:].decode(errors='replace'))
    results=decode_native_results(manifest,b''.join(outputs))
    if len(results)!=len(inputs):raise ValueError('native response count differs from requests')
    return results
