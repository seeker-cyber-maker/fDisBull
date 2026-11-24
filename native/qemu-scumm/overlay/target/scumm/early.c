/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Independent authored-script pilot; see PROVENANCE.md. */
#include "early.h"
#include <string.h>
static const char *const names[]={
 "stop","yield","move","add","subtract","increment","decrement","jump",
 "equal","not_equal","zero","nonzero","greater_equal","less_equal","less",
 "greater","place_actor","set_var_range","actor_config","resource_operation",
 "start_script","stop_script","chain_script","load_room","actor_room","nop",
 "cutscene","cursor","lights","animate_actor","walk_actor","print","verb_op","override",
 "move_indirect","add_indirect","sub_indirect","unknown"
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
 case 0x40:case 0xc0:
  if(version){i->op=S_CUTSCENE;i->subop=(i->opcode==0x40)?1:0;}break;
 case 0x58:
  if(!version)break;
  i->op=S_OVERRIDE;
  if(p>len||len-p<3)ok=false;
  else if(code[p]!=0x18){i->fault=S_OPCODE;return false;}
  else{i->payload_pc=p;i->payload_size=3;p+=3;}break;
 case 0xd8:
  if(!version)break;
  i->op=S_PRINT;goto print_text;
 case 0x26:case 0xa6:
  if(!version)break;
  i->op=S_RANGE;
  ok=arg(code,len,&p,i,S_DEST,1)&&arg(code,len,&p,i,S_IMM,1);
  if(ok){unsigned count=i->arg[1].value,w=(i->opcode&0x80)?2:1;
   i->subop=w;i->payload_pc=p;i->payload_size=count*w;
   if(!count){i->fault=S_BAD_VAR;return false;}
   if(i->payload_size>len-p)ok=false;else p+=i->payload_size;}
  break;
 case 0x2c:
  if(!version)break;
  i->op=S_MOVE;ok=arg(code,len,&p,i,S_DEST,1)&&arg(code,len,&p,i,S_IMM,1);break;
 case 0x28:case 0xa8:
  i->op=i->opcode==0x28?S_ZERO:S_NONZERO;i->conditional=1;branch=true;
  ok=arg(code,len,&p,i,S_VAR,1);break;
 default:
  if(version && (base==0x14)){
   i->op=S_PRINT;ok=val(code,len,&p,i,0x80,1);
print_text:
   if(ok){i->payload_pc=p;
    while(p<len&&p-i->pc<SCUMM_INSN_MAX){
     unsigned ch=code[p++];
     if(!ch){i->payload_size=p-i->payload_pc;break;}
     unsigned low=ch&127;
     if(low>=4&&low<8){if(p>=len){ok=false;break;}++p;}
    }
    if(!i->payload_size)ok=false;
   }
  }else if(version&&base==0x7a){
   i->op=S_VERB;ok=arg(code,len,&p,i,S_IMM,1);
   if(ok){unsigned verb=i->arg[0].value;
    if(!verb)ok=val(code,len,&p,i,0x80,1);
    else if(verb==255)ok=arg(code,len,&p,i,S_IMM,1)&&arg(code,len,&p,i,S_IMM,1);
    else{
     /* New verb layout: x, y, slot, preposition, NUL-terminated name.
      * Keep raw payload for static consumption; no verb effects executed. */
     i->payload_pc=p;
     if(len-p<4)ok=false;else{
      p+=4;
      while(p<len&&p-i->pc<SCUMM_INSN_MAX&&code[p])++p;
      if(p>=len||code[p])ok=false;else{++p;i->payload_size=p-i->payload_pc;}
     }
    }
   }
  }else if(version&&base==0x60){
   i->op=S_CURSOR;ok=val(code,len,&p,i,0x80,word);
  }else if(version&&base==0x70){
   i->op=S_LIGHTS;ok=val(code,len,&p,i,0x80,1)&&arg(code,len,&p,i,S_IMM,1)&&arg(code,len,&p,i,S_IMM,1);
  }else if(version&&(i->opcode&0x3f)==0x11){
   i->op=S_ANIMATE;ok=val(code,len,&p,i,0x80,1)&&val(code,len,&p,i,0x40,1);
  }else if((i->opcode&0x1f)==0x1e){
   i->op=S_WALK;ok=val(code,len,&p,i,0x80,1)&&val(code,len,&p,i,0x40,1)&&val(code,len,&p,i,0x20,1);
  }else if(version&&(base==0x0a||base==0x2a||base==0x6a)){
   i->op=base==0x0a?S_MOVE_IND:base==0x2a?S_ADD_IND:S_SUB_IND;
   ok=arg(code,len,&p,i,S_DEST,1)&&val(code,len,&p,i,0x80,word);
  }else if(version && (i->opcode&0x3f)==0x13){
   i->op=S_ACTOR_CONFIG;
   ok=val(code,len,&p,i,0x80,1)&&val(code,len,&p,i,0x40,1)&&arg(code,len,&p,i,S_IMM,1);
   if(ok){i->subop=i->arg[2].value;
    if(i->subop<1||i->subop>5){i->fault=S_OPCODE;return false;}
    if(i->subop==2&&version==2){
     i->payload_pc=p;i->payload_size=1;if(p>=len)ok=false;else ++p;
    }else if(i->subop==3){
     i->payload_pc=p;
     while(p<len&&p-i->payload_pc<SCUMM_INSN_MAX-5&&code[p])++p;
     if(p>=len||code[p])ok=false;else{i->payload_size=p-i->payload_pc;++p;}
    }
   }
  }else if(version && base==0x0c){
   i->op=S_RESOURCE;ok=val(code,len,&p,i,0x80,1)&&arg(code,len,&p,i,S_IMM,1);
  }else if(base==0x42||base==0x62||(version&&base==0x4a)){
   i->op=base==0x42?S_START_SCRIPT:base==0x62?S_STOP_SCRIPT:S_CHAIN_SCRIPT;
   ok=val(code,len,&p,i,0x80,1);
  }else if(version&&base==0x72){
   i->op=S_LOAD_ROOM;ok=val(code,len,&p,i,0x80,1);
  }else if((i->opcode&0x3f)==0x2d){
   i->op=S_ACTOR_ROOM;ok=val(code,len,&p,i,0x80,1)&&val(code,len,&p,i,0x40,1);
  }else if(version&&(base==0x5c||base==0x6b||base==0x6e)){
   i->op=S_NOP;
  }else if((i->opcode&0x1f)==1){
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
 if(p-pc>SCUMM_INSN_MAX){i->fault=S_TRUNCATED;return false;}
 i->next=(uint32_t)p;i->size=(uint16_t)(p-pc);return true;
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
const char *scumm_block_reason(unsigned reason)
{
 static const char *const reasons[]={"none","unimplemented_effect",
  "resource_bytes_unavailable","room_mapper_required","nested_cutscene",
  "sentence_script_owner"};
 return reasons[reason<=S_BLOCK_SENTENCE_OWNER?reason:S_BLOCK_UNIMPLEMENTED];
}
void scumm_runtime_reset(ScummRuntime *r)
{
 if(!r)return;
 for(unsigned type=0;type<SCUMM_RESOURCE_TYPES;type++)
  for(unsigned id=0;id<SCUMM_RESOURCE_SLOTS;id++){
   r->resources[type][id].resident=0;
   r->resources[type][id].locked=0;
  }
 memset((uint8_t *)r+offsetof(ScummRuntime,user_state),0,
        sizeof(*r)-offsetof(ScummRuntime,user_state));
 if(r->enabled&&r->script_id<SCUMM_RESOURCE_SLOTS&&
    r->resources[S_RES_SCRIPT][r->script_id].available)
  r->resources[S_RES_SCRIPT][r->script_id].resident=1;
}
static void set_user_state(ScummRuntime *r,unsigned flags)
{
 if(flags&4)r->user_state=flags&0xe0;
 if(flags&2)r->user_put=r->cursor_visible=(flags&0x10)!=0;
 /* Freeze/unfreeze operates on an empty set of other slots in this profile.
  * The sole current global script is excluded by the v2 freeze operation. */
}
bool scumm_step_runtime(unsigned version,const uint8_t *code,size_t len,
                       ScummState *s,ScummTrace *t,ScummRuntime *runtime)
{
 ScummInsn i;uint16_t a=0,b=0,c=0;unsigned dest=0,actor=0;
 ScummActor before={0},after={0};bool scene=false,cond=true;uint32_t next;
 ScummRuntime *r=runtime&&runtime->enabled?runtime:NULL;
 if(s->status==S_RETURN||s->status==S_FAULT||s->status==S_BLOCKED)return false;
 if(r&&version!=2){
  s->status=S_FAULT;s->fault=S_BAD_VERSION;s->fault_opcode=0;return false;
 }
 if(r)r->blocked_reason=S_BLOCK_NONE;
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
 case S_MOVE_IND:case S_ADD_IND:case S_SUB_IND:
  dest=s->vars[dest];if(dest>=256)goto badvar;
  s->vars[dest]=i.op==S_MOVE_IND?b:i.op==S_ADD_IND?(uint16_t)(s->vars[dest]+b):(uint16_t)(s->vars[dest]-b);
  break;
 case S_RANGE:{
  unsigned count=i.arg[1].value;
  if(count>256-dest)goto badvar;
  for(unsigned k=0;k<count;k++){
   unsigned pos=i.payload_pc+k*i.subop;
   uint16_t x=code[pos];if(i.subop==2)x|=(uint16_t)code[pos+1]<<8;
   s->vars[dest+k]=x;
  }
  break;}
 case S_ACTOR_CONFIG:
  if(a==0&&i.subop==5&&b<=255){s->default_talk_color=(uint8_t)b;break;}
  if(a==0||a>=SCUMM_ACTORS||b>255){i.fault=S_BAD_ACTOR;goto fault;}
  actor=a;before=s->actors[actor];after=before;
  switch(i.subop){
  case 1:after.sound=(uint8_t)b;break;
  case 2:{unsigned slot=version==1?a:code[i.payload_pc];
   if(slot>=32){i.fault=S_BAD_ACTOR;goto fault;}
   after.palette[slot]=(uint8_t)b;after.palette_known[slot]=1;break;}
  case 3:after.name_pc=i.payload_pc;after.name_size=i.payload_size;break;
  case 4:after.costume=(uint8_t)b;break;
  case 5:after.talk_color=(uint8_t)b;break;
  default:i.fault=S_OPCODE;goto fault;
  }
  s->actors[actor]=after;scene=memcmp(&before,&after,sizeof(before))!=0;break;
 case S_RESOURCE:{
  if(!r)goto blocked;
  unsigned command=b&15,type=SCUMM_RESOURCE_TYPES;
  switch(b>>4){
  case 2:type=S_RES_COSTUME;break;
  case 3:type=S_RES_ROOM;break;
  case 5:type=S_RES_SCRIPT;break;
  case 6:type=S_RES_SOUND;break;
  default:break; /* Invalid resource kinds are deliberate v2 no-ops. */
  }
  if(type==SCUMM_RESOURCE_TYPES)break;
  if(!command)break;
  if(command==1&&type==S_RES_ROOM&&a>127){
   r->blocked_reason=S_BLOCK_ROOM_MAPPER;goto blocked;
  }
  if(command==1&&a==0)break;
  if(a>=r->counts[type]||a>=SCUMM_RESOURCE_SLOTS){i.fault=S_BAD_RESOURCE;goto fault;}
  if(command==1){
   if(!r->resources[type][a].available){r->blocked_reason=S_BLOCK_RESOURCE_MISSING;goto blocked;}
   r->resources[type][a].resident=1;
  }else{
   /* Lock/unlock validates the directory slot, but never loads its bytes. */
   r->resources[type][a].locked=command&1;
  }
  break;}
 case S_CUTSCENE:
  if(!r||!i.subop)goto blocked; /* Exit requires camera/room semantics. */
  if(r->cutscene_active){r->blocked_reason=S_BLOCK_CUTSCENE_NESTED;goto blocked;}
  if(r->script_id==2){r->blocked_reason=S_BLOCK_SENTENCE_OWNER;goto blocked;}
  r->saved_user_state=r->user_state|(r->user_put?0x10:0);
  r->saved_cursor=s->vars[21];r->saved_room=r->current_room;
  r->saved_camera_mode=r->camera_mode;r->cutscene_active=1;
  s->vars[21]=200;set_user_state(r,0x0f);
  r->sentence_count=0;
  /* Sentence script 2 is absent: this profile has only the bound current
   * script, and entry from script 2 was rejected before any mutation. */
  s->vars[26]=s->vars[38];s->vars[27]=s->vars[28]=s->vars[29]=0;
  r->override_pc=0;++r->ui_revision;
  break;
 case S_CURSOR:
  if(!r)goto blocked;
  if(a&255)s->vars[21]=a&255;
  set_user_state(r,a>>8);++r->ui_revision;
  break;
 case S_START_SCRIPT:case S_STOP_SCRIPT:case S_CHAIN_SCRIPT:
 case S_LOAD_ROOM:case S_ACTOR_ROOM:
 case S_LIGHTS:case S_ANIMATE:case S_WALK:case S_PRINT:case S_VERB:case S_OVERRIDE:
  goto blocked;
 case S_NOP:break;
 case S_PLACE:
  if(a==0||a>=SCUMM_ACTORS){i.fault=S_BAD_ACTOR;goto fault;}
  actor=a;before=s->actors[actor];after=before;after.x=b;after.y=c;after.bound=1;
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
blocked:
 if(r&&!r->blocked_reason)r->blocked_reason=S_BLOCK_UNIMPLEMENTED;
 s->status=S_BLOCKED;s->fault_opcode=i.opcode;return false;
badvar:i.fault=S_BAD_VAR;
fault:s->status=S_FAULT;s->fault=i.fault;s->fault_opcode=i.opcode;return false;
}
bool scumm_step(unsigned version,const uint8_t *code,size_t len,
                ScummState *s,ScummTrace *t)
{
 return scumm_step_runtime(version,code,len,s,t,NULL);
}
