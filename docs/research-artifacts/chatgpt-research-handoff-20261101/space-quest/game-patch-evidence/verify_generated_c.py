#!/usr/bin/env python3
"""Compile bounded lifted C and compare it with a separate small SCI-byte interpreter.
This is model validation over explicit property-call summaries, not native gameplay.
"""
from pathlib import Path
import json,subprocess,hashlib,time
import compare_game_patches as p
R=p.ROOT;out=R/'results'
header=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef uint32_t V;
static V acc_in, prev_in, stack_top_in, acc_out, prev_out, next_pc;
static V stack_out[32]; static V counter, detail, local7, prop1a; static int unresolved;
static const V self=0x10000;
static V wrap16(V x){return x&0xffff;}
static int s16(V x){if(x>65535){unresolved=1;return 0;}return x<32768?(int)x:(int)x-65536;}
static V class_ref(unsigned x){return 0x20000|x;}
static V global_ref(unsigned x){return 0x30000|x;}
static V read_selector(V o,unsigned s){if(o==class_ref(124)&&s==582)return counter;if(o==global_ref(1)&&s==291)return detail;unresolved=1;return 0;}
static void write_selector(V o,unsigned s,V v){if(o==class_ref(124)&&s==582)counter=v;else unresolved=1;}
static V read_local(unsigned s){if(s==7)return local7;unresolved=1;return 0;}
static V read_property(V o,unsigned s){if(o==self&&s==26)return prop1a;unresolved=1;return 0;}
static void write_local(unsigned s,V v){if(s==7)local7=v;else unresolved=1;}
static void write_property(V o,unsigned s,V v){if(o==self&&s==26)prop1a=v;else unresolved=1;}
static V UNRESOLVED_object_numeric_lt(V x,V y){(void)x;(void)y;unresolved=1;return 0;}
struct Result{V acc,prev,next,counter,detail,local7,prop1a,stack[32];int unresolved;};
static void reset(V n,V origin,V size){acc_in=n;prev_in=71;stack_top_in=n^1;acc_out=acc_in;prev_out=prev_in;next_pc=origin+size;counter=n;detail=n;local7=n^0x55aa;prop1a=n^65535;unresolved=0;memset(stack_out,0,sizeof(stack_out));}
static struct Result collect(void){struct Result r;memset(&r,0,sizeof(r));r.acc=acc_out;r.prev=prev_out;r.next=next_pc;r.counter=counter;r.detail=detail;r.local7=local7;r.prop1a=prop1a;r.unresolved=unresolved;memcpy(r.stack,stack_out,sizeof(stack_out));return r;}
/* A separate concrete byte-stream interpreter; no symbolic-lifter calls. */
static int vm(const unsigned char *b,unsigned size,unsigned origin,int seedstack){
 V a=acc_in,prev=prev_in,st[32]={0};unsigned sp=0,pc=0;if(seedstack)st[sp++]=stack_top_in;
 while(pc<size){unsigned ext=b[pc++],op=ext>>1,w=(ext&1)?1:2;int arg=0;V left;
  int has=(op==0x18||op==0x19||op==0x1a||op==0x1c||op==0x25||op==0x28||op==0x32||op==0x33||op==0x40||op==0x45||op==0x51);
  if(has){if(op==0x25)w=1;if(pc+w>size)return 1;arg=b[pc++];if(w==2)arg|=b[pc++]<<8;
   if(op==0x18||op==0x19||op==0x1a||op==0x1c){if(w==1&&arg>=128)arg-=256;if(w==2&&arg>=32768)arg-=65536;}}
  switch(op){
   case 0x1a:a=(unsigned)arg&65535;break;
   case 0x1c:st[sp++]=(unsigned)arg&65535;break;
   case 0x1b:st[sp++]=a;break;
   case 0x3b:st[sp++]=0;break;case 0x3c:st[sp++]=1;break;case 0x3d:st[sp++]=2;break;
   case 0x28:a=class_ref(arg);break;case 0x40:a=global_ref(arg);break;
   case 0x45:st[sp++]=read_local(arg);break;case 0x33:st[sp++]=read_property(self,arg);break;
   case 0x51:write_local(arg,a);break;case 0x32:write_property(self,arg,a);break;
   case 0x25:{unsigned n=arg/2;if((arg&1)||sp<n)return 2;unsigned j=sp-n;V sel=st[j],argc=st[j+1];
     if(argc==0)a=read_selector(a,sel);else if(argc==1)write_selector(a,sel,st[j+2]);else return 3;sp=j;break;}
   case 0x01:if(!sp)return 4;left=st[--sp];if(left>65535||a>65535){unresolved=1;a=0;}else a=(left+a)&65535;break;
   case 0x0d:case 0x0f:case 0x11:case 0x12:
     if(!sp)return 5;left=st[--sp];prev=a;
     if(op==0x0d)a=(left==a);
     else if(left>65535||a>65535){unresolved=1;a=0;}
     else if(op==0x0f)a=s16(left)>s16(a);else if(op==0x11)a=s16(left)<s16(a);else a=s16(left)<=s16(a);break;
   case 0x18:if(!a)next_pc=(origin+pc+arg)&65535;break;
   case 0x19:next_pc=(origin+pc+arg)&65535;break;
   default:return 6;
  }
  if(sp>=32)return 7;
 }
 acc_out=a;prev_out=prev;memcpy(stack_out,st,sp*sizeof(V));return 0;
}
'''
selector=json.loads((R/'selectors.json').read_text());functions=[];entries=[]
for rec in p.recipes(selector):
    old=(R/f'resources/script.{rec["script"]:03}').read_bytes();new,off,_,_=p.apply_patch(old,rec)
    for j,(a,z) in enumerate(rec['slices']):
        for phase,data in [('before',old),('after',new)]:
            name=f'{rec["id"]}_{j}_{phase}';origin=off+a;b=data[origin:off+z]
            prestack=(p.e('input','stack_top_in'),) if rec['id']=='generator_branch' else ()
            ir=p.lift(p.decode(b,origin),prestack)
            functions.append(f'static void {name}(void){{\n'+p.render_c(ir)+'}\n')
            functions.append(f'static const unsigned char bytes_{name}[]={{'+','.join(str(x) for x in b)+'};\n')
            entries.append((name,origin,len(b),int(bool(prestack))))
body='\n'.join(functions)+'''\nstruct Case{const char *name;void (*fn)(void);const unsigned char *bytes;unsigned origin,size;int seedstack;};\nstatic struct Case cases[]={\n'''
body+=',\n'.join('{"%s",%s,bytes_%s,%d,%d,%d}'%(n,n,n,o,s,t) for n,o,s,t in entries)+'\n};\n'
body+=r'''
int main(void){unsigned long comparisons=0;unsigned mixed=0;
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  struct Case *c=&cases[i];
  for(unsigned n=0;n<65536;n++){
   reset(n,c->origin,c->size);c->fn();struct Result a=collect();
   reset(n,c->origin,c->size);int err=vm(c->bytes,c->size,c->origin,c->seedstack);struct Result b=collect();
   if(err||memcmp(&a,&b,sizeof(a))){fprintf(stderr,"mismatch %s %u err=%d\n",c->name,n,err);return 1;}
   if(a.unresolved)mixed++;
   if(strcmp(c->name,"bar_detail_predicate_0_before")==0&&a.acc!=(V)(s16(n)<=2))return 2;
   if(strcmp(c->name,"bar_detail_predicate_0_after")==0&&a.acc!=(V)(s16(n)>2))return 3;
   if(strcmp(c->name,"id_card_counter_0_after")==0&&(a.counter!=((n+1)&65535)||a.acc!=(V)(s16((n+1)&65535)<3)||a.unresolved))return 4;
   if(strcmp(c->name,"id_card_counter_0_before")==0&&(a.counter!=((n+1)&65535)||!a.unresolved))return 5;
   if(strcmp(c->name,"generator_branch_0_after")==0&&a.next!=c->origin+c->size)return 6;
   if(strcmp(c->name,"timepod_cel_0_after")==0&&a.stack[2]!=9)return 7;
   comparisons++;
  }
 }
 unsigned equal_checks=0;
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  struct Case *c=&cases[i];if(strncmp(c->name,"generator_branch",16)!=0)continue;
  const unsigned values[]={0,1,32767,32768,65535};
  for(unsigned j=0;j<5;j++){
   unsigned n=values[j];reset(n,c->origin,c->size);stack_top_in=n;c->fn();struct Result a=collect();
   reset(n,c->origin,c->size);stack_top_in=n;int err=vm(c->bytes,c->size,c->origin,c->seedstack);struct Result b=collect();
   if(err||memcmp(&a,&b,sizeof(a))||a.next!=c->origin+c->size||a.acc!=1)return 8;
   equal_checks++;
  }
 }
 if(equal_checks!=10)return 9;
 printf("{\"model_comparisons\":%lu,\"cases\":%u,\"mixed_object_comparisons_preserved_as_unresolved\":%u,\"passed\":true}\n",comparisons,(unsigned)(sizeof(cases)/sizeof(cases[0])),mixed);
 return 0;
}
'''
source=header+body
src=out/'generated_models_and_vm.c';src.write_text(source)
start=time.perf_counter();build=subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra',str(src),'-o',str(out/'verify_c')],capture_output=True,text=True);compile_ms=(time.perf_counter()-start)*1000
(out/'c_compile.stderr').write_text(build.stderr);build.check_returncode()
start=time.perf_counter();run=subprocess.run([str(out/'verify_c')],capture_output=True,text=True);run_ms=(time.perf_counter()-start)*1000
if run.returncode:raise RuntimeError(f'C verification failed {run.returncode}: {run.stderr}')
r=json.loads(run.stdout);r.update(additional_equal_branch_checks=10,compile_ms=compile_ms,execution_ms=run_ms,source_sha256=hashlib.sha256(source.encode()).hexdigest(),compiler=subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],scope='12 selected old/new blocks, each under 65536 typed model inputs; common property-call summaries; not full methods, independent native runtime, or original-DOS behavior')
p.save(out/'c_validation.json',r);print(json.dumps(r,indent=2))
