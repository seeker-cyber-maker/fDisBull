/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Independent authored-script pilot; see PROVENANCE.md. */
#include "early.h"
#include <string.h>
static const char *const names[]={
 "stop","yield","move","add","subtract","increment","decrement","jump",
 "equal","not_equal","zero","nonzero","greater_equal","less_equal","less",
 "greater","place_actor","unknown"
};
const char *scumm_op_name(unsigned op){return names[op<=S_UNKNOWN?op:S_UNKNOWN];}
static bool arg(const uint8_t *c,size_t len,size_t *p,ScummInsn *i,unsigned kind,unsigned width)
{
 if(i->count>=3 || *p>len || width>len-*p)return false;
 ScummArg *a=&i->arg[i->count++];
 a->kind=kind;a->width=width;a->value=c[*p];
 if(width==2)a->value|=(uint16_t)c[*p+1]<<8;
 *p+=width;return true;
}
static bool val(const uint8_t *c,size_t len,size_t *p,ScummInsn *i,unsigned bit,unsigned width)
{
 bool variable=(i->opcode&bit)!=0;
 return arg(c,len,p,i,variable?S_VAR:S_IMM,variable?1:width);
}
bool scumm_decode(unsigned version,const uint8_t *code,size_t len,uint32_t pc,ScummInsn *i)
{
 size_t p=pc;unsigned word=version?2:1,base;bool ok=true,branch=false;
 memset(i,0,sizeof(*i));i->pc=pc;i->target=-1;i->op=S_UNKNOWN;
 if(version>2){i->fault=S_BAD_VERSION;return false;}
 if(!code || len>SCUMM_CODE_MAX || pc>=len){i->fault=S_BAD_PC;return false;}
 i->opcode=code[p++];base=i->opcode&0x7f;
 switch(i->opcode){
 case 0x00:case 0xa0:i->op=S_STOP;break;
 case 0x10:case 0x80:if(i->opcode==(version?0x80:0x10))i->op=S_YIELD;break;
 case 0x18:i->op=S_JUMP;branch=true;break;
 case 0x46:case 0xc6:i->op=i->opcode==0x46?S_INC:S_DEC;ok=arg(code,len,&p,i,S_DEST,1);break;
 case 0x2c:
  if(!version)break;
  i->op=S_MOVE;ok=arg(code,len,&p,i,S_DEST,1)&&arg(code,len,&p,i,S_IMM,1);break;
 case 0x28:case 0xa8:
  i->op=i->opcode==0x28?S_ZERO:S_NONZERO;i->conditional=1;branch=true;
  ok=arg(code,len,&p,i,S_VAR,1);break;
 default:
  if((i->opcode&0x1f)==1){
   i->op=S_PLACE;
   ok=val(code,len,&p,i,0x80,1)&&val(code,len,&p,i,0x40,1)&&val(code,len,&p,i,0x20,1);
  }else if(base==0x1a||base==0x5a||base==0x3a){
   i->op=base==0x1a?S_MOVE:base==0x5a?S_ADD:S_SUB;
   ok=arg(code,len,&p,i,S_DEST,1)&&val(code,len,&p,i,0x80,word);
  }else if(base==0x48||base==0x08||base==0x04||base==0x38||base==0x44||base==0x78){
   i->op=base==0x48?S_EQ:base==0x08?S_NE:base==0x04?S_GE:base==0x38?S_LE:base==0x44?S_LT:S_GT;
   i->conditional=1;branch=true;
   ok=arg(code,len,&p,i,S_VAR,1)&&val(code,len,&p,i,0x80,word);
  }
 }
 if(i->op==S_UNKNOWN){i->fault=S_OPCODE;return false;}
 if(branch&&ok){
  if(p>len||len-p<2)ok=false;
  else{uint32_t raw=code[p]|((uint32_t)code[p+1]<<8);p+=2;
       i->target=(int32_t)p+(raw<32768?(int32_t)raw:(int32_t)raw-65536);}
 }
 if(!ok){i->fault=S_TRUNCATED;return false;}
 i->next=(uint32_t)p;i->size=(uint8_t)(p-pc);return true;
}
static bool value(unsigned version,const ScummState *s,const ScummArg *a,uint16_t *v)
{
 unsigned index=a->value;
 if(a->kind==S_IMM){*v=index;return true;}
 if(a->kind==S_VAR && version && index>=14 && index<=16)index=s->vars[index];
 if(index>=256)return false;
 *v=s->vars[index];return true;
}
static void emit(ScummTrace *t,unsigned ch,const ScummInsn *i,const uint8_t *code,
                 const ScummState *s,unsigned actor,ScummActor before,ScummActor after)
{
 if(!t||!(t->mask&(1u<<ch)))return;
 uint64_t seq=++t->sequence;++t->eligible[ch];
 if(t->count>=t->capacity||t->count>=SCUMM_EVENT_MAX){++t->dropped[ch];return;}
 ScummEvent *e=&t->events[t->count++];memset(e,0,sizeof(*e));
 e->seq=seq;e->retired=s->retired;e->pc=i->pc;e->next=s->pc;
 e->opcode=i->opcode;e->size=i->size;e->channel=ch;e->actor=actor;
 e->before=before;e->after=after;memcpy(e->bytes,code+i->pc,i->size);
}
bool scumm_step(unsigned version,const uint8_t *code,size_t len,ScummState *s,ScummTrace *t)
{
 ScummInsn i;uint16_t a=0,b=0,c=0;unsigned dest=0,actor=0;
 ScummActor before={0},after={0};bool scene=false,cond=true;uint32_t next;
 if(s->status==S_RETURN||s->status==S_FAULT)return false;
 if(!scumm_decode(version,code,len,s->pc,&i))goto fault;
 next=i.next;
 if(i.count&&i.arg[0].kind==S_DEST)dest=i.arg[0].value;
 if(i.count&&!value(version,s,&i.arg[0],&a))goto badvar;
 if(i.count>1&&!value(version,s,&i.arg[1],&b))goto badvar;
 if(i.count>2&&!value(version,s,&i.arg[2],&c))goto badvar;
 switch(i.op){
 case S_MOVE:s->vars[dest]=b;break;
 case S_ADD:s->vars[dest]=(uint16_t)(a+b);break;
 case S_SUB:s->vars[dest]=(uint16_t)(a-b);break;
 case S_INC:case S_DEC:{
  ScummArg r=i.arg[0];r.kind=S_VAR;
  if(!value(version,s,&r,&a))goto badvar;
  s->vars[dest]=(uint16_t)(a+(i.op==S_INC?1:-1));break;}
 case S_JUMP:cond=false;break;
 case S_EQ:cond=a==b;break;
 case S_NE:cond=a!=b;break;
 case S_ZERO:cond=a==0;break;
 case S_NONZERO:cond=a!=0;break;
 case S_GE:cond=b>=a;break;
 case S_LE:cond=b<=a;break;
 case S_LT:cond=b<a;break;
 case S_GT:cond=b>a;break;
 case S_PLACE:
  if(a==0||a>=SCUMM_ACTORS){i.fault=S_BAD_ACTOR;goto fault;}
  actor=a;before=s->actors[actor];after=(ScummActor){b,c,1};
  s->actors[actor]=after;scene=before.x!=after.x||before.y!=after.y||before.bound!=after.bound;break;
 case S_STOP:case S_YIELD:break;
 default:i.fault=S_OPCODE;goto fault;
 }
 if(!cond){
  if(i.target<0||(uint32_t)i.target>=len){i.fault=S_BAD_BRANCH;goto fault;}
  next=(uint32_t)i.target;
 }
 s->pc=next;++s->retired;s->status=i.op==S_STOP?S_RETURN:i.op==S_YIELD?S_WAIT:S_RUNNING;
 emit(t,0,&i,code,s,0,(ScummActor){0},(ScummActor){0});
 if(scene)emit(t,1,&i,code,s,actor,before,after);
 return true;
badvar:i.fault=S_BAD_VAR;
fault:s->status=S_FAULT;s->fault=i.fault;s->fault_opcode=i.opcode;return false;
}
