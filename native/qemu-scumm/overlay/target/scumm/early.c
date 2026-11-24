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
/* v2 verb resources copy encoded strings, not plain C strings. A 0xff
 * escape consumes its command and, except for 1/2/3/8, two argument bytes
 * which may themselves be zero. The caller retains this exact source span. */
static bool verb_name_end(const uint8_t *code,size_t len,size_t *p,uint32_t pc)
{
 size_t end=(size_t)pc+SCUMM_INSN_MAX;
 if(end>len)end=len;
 while(*p<end){
  unsigned ch=code[(*p)++];
  if(!ch)return true;
  if(ch!=0xff)continue;
  if(*p==end)return false;
  unsigned command=code[(*p)++];
  if(command!=1&&command!=2&&command!=3&&command!=8){
   if(end-*p<2)return false;
   *p+=2;
  }
 }
 return false;
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
     /* Keep the complete x/y/selector/preposition/name payload while also
      * exposing the variable-aware selector and literal prep as operands. */
     i->payload_pc=p;
     if(len-p<4)ok=false;else{
      p+=2;
      ok=val(code,len,&p,i,0x80,1)&&arg(code,len,&p,i,S_IMM,1)&&
         verb_name_end(code,len,&p,i->pc);
      if(ok)i->payload_size=p-i->payload_pc;
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
bool scumm_scene_op(unsigned op)
{
 return op==S_PLACE||op==S_ACTOR_CONFIG||op==S_RESOURCE||
        op==S_CURSOR||op==S_CUTSCENE||op==S_VERB;
}
void scumm_trace_clear(ScummTrace *t)
{
 t->count=0;t->sequence=0;t->helper_calls=0;
 memset(t->eligible,0,sizeof(t->eligible));
 memset(t->stored,0,sizeof(t->stored));
 memset(t->dropped,0,sizeof(t->dropped));
 ++t->epoch;
}
void scumm_control_snapshot(const ScummState *s,const ScummRuntime *r,ScummControl *c)
{
 static const unsigned vars[]={21,26,27,28,29,38};
 memset(c,0,sizeof(*c));
 if(r){
  c->user_state=r->user_state;c->user_put=r->user_put;
  c->cursor_visible=r->cursor_visible;c->current_room=r->current_room;
  c->camera_mode=r->camera_mode;c->cutscene_active=r->cutscene_active;
  c->saved_user_state=r->saved_user_state;c->saved_room=r->saved_room;
  c->saved_camera_mode=r->saved_camera_mode;c->saved_cursor=r->saved_cursor;
  c->override_pc=r->override_pc;c->override_script=r->override_script;
  c->sentence_count=r->sentence_count;c->ui_revision=r->ui_revision;
 }
 for(unsigned k=0;k<6;k++)c->vars[k]=s->vars[vars[k]];
}
static void emit(ScummTrace *t,unsigned ch,const ScummEvent *capture,const uint8_t *code)
{
 uint64_t seq=++t->sequence;++t->eligible[ch];
 if(t->count>=t->capacity||t->count>=SCUMM_EVENT_MAX){++t->dropped[ch];return;}
 ScummEvent *e=&t->events[t->count++];*e=*capture;
 e->seq=seq;e->channel=ch;e->control_generation=t->control_generation;
 if(!ch)e->kind=S_EVENT_RETIRE;
 memcpy(e->bytes,code+e->pc,e->size);++t->stored[ch];
}
void scumm_observe(ScummTrace *t,const ScummEvent *capture,const uint8_t *code)
{
 if(!t||!(t->mask&SCUMM_OBS_MASK)||!capture||!capture->size)return;
 ++t->helper_calls;
 if(t->mask&SCUMM_OBS_DISASM)emit(t,0,capture,code);
 if((t->mask&SCUMM_OBS_SCENE)&&capture->kind!=S_EVENT_RETIRE)
  emit(t,1,capture,code);
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
 for(unsigned slot=0;slot<SCUMM_VERBS;slot++){
  r->verbs[slot].color=2;
  r->verbs[slot].charset=1;
 }
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
bool scumm_execute_runtime(unsigned version,const uint8_t *code,size_t len,
                           ScummState *s,unsigned mask,ScummEvent *capture,
                           ScummRuntime *runtime)
{
 ScummInsn i;uint16_t a=0,b=0,c=0;unsigned dest=0,actor=0;
 bool cond=true;uint32_t next;
 ScummRuntime *r=runtime&&runtime->enabled?runtime:NULL;
 ScummEvent *obs=NULL;
 if(capture)capture->size=0;
 if(s->status==S_RETURN||s->status==S_FAULT||s->status==S_BLOCKED)return false;
 if(r&&version!=2){
  s->status=S_FAULT;s->fault=S_BAD_VERSION;s->fault_opcode=0;return false;
 }
 if(r)r->blocked_reason=S_BLOCK_NONE;
 if(!scumm_decode(version,code,len,s->pc,&i))goto fault;
 /* Retirement is a mandatory architectural counter, independent of the
  * optional journal. Reject its overflow before executing any effect. */
 if(s->retired==UINT64_MAX){i.fault=S_COUNTER_EXHAUSTED;goto fault;}
 if(capture&&((mask&SCUMM_OBS_DISASM)||
              ((mask&SCUMM_OBS_SCENE)&&scumm_scene_op(i.op)))){
  obs=capture;memset(obs,0,sizeof(*obs));
 }
 next=i.next;
 if(i.count&&i.arg[0].kind==S_DEST)dest=i.arg[0].value;
 if(i.count&&!value(version,s,&i.arg[0],&a))goto badvar;
 if(i.count>1&&!value(version,s,&i.arg[1],&b))goto badvar;
 if(i.count>2&&!value(version,s,&i.arg[2],&c))goto badvar;
 if(obs&&(mask&SCUMM_OBS_DISASM)&&i.count&&i.arg[0].kind==S_DEST){
  obs->has_destination=1;obs->destination=dest;
  obs->destination_before=s->vars[dest];
 }
 switch(i.op){
 case S_MOVE:s->vars[dest]=b;break;
 case S_ADD:s->vars[dest]=(uint16_t)(a+b);break;
 case S_SUB:s->vars[dest]=(uint16_t)(a-b);break;
 case S_INC:case S_DEC:{
  ScummArg input=i.arg[0];input.kind=S_VAR;
  if(!value(version,s,&input,&a))goto badvar;
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
  if(obs&&obs->has_destination){obs->destination=dest;obs->destination_before=s->vars[dest];}
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
  if(a==0&&i.subop==5&&b<=255){
   if(obs&&(mask&SCUMM_OBS_SCENE)&&s->default_talk_color!=b){
    obs->kind=S_EVENT_DEFAULT_COLOR;
    obs->before_color=s->default_talk_color;obs->after_color=b;
   }
   s->default_talk_color=(uint8_t)b;break;
  }
  if(a==0||a>=SCUMM_ACTORS||b>255){i.fault=S_BAD_ACTOR;goto fault;}
  actor=a;
  if(i.subop==2&&(version==1?a:code[i.payload_pc])>=32){i.fault=S_BAD_ACTOR;goto fault;}
  if(obs&&(mask&SCUMM_OBS_SCENE))obs->before=s->actors[actor];
  switch(i.subop){
  case 1:s->actors[actor].sound=(uint8_t)b;break;
  case 2:{unsigned slot=version==1?a:code[i.payload_pc];
   s->actors[actor].palette[slot]=(uint8_t)b;s->actors[actor].palette_known[slot]=1;break;}
  case 3:s->actors[actor].name_pc=i.payload_pc;s->actors[actor].name_size=i.payload_size;break;
  case 4:s->actors[actor].costume=(uint8_t)b;break;
  case 5:s->actors[actor].talk_color=(uint8_t)b;break;
  default:i.fault=S_OPCODE;goto fault;
  }
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->actor=actor;obs->after=s->actors[actor];
   if(memcmp(&obs->before,&obs->after,sizeof(ScummActor)))obs->kind=S_EVENT_ACTOR;
  }
  break;
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
  }
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->resource_type=type;obs->resource_id=a;obs->before_resource=r->resources[type][a];
  }
  if(command==1){
   r->resources[type][a].resident=1;
  }else{
   /* Lock/unlock validates the directory slot, but never loads its bytes. */
   r->resources[type][a].locked=command&1;
  }
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->after_resource=r->resources[type][a];
   if(obs->before_resource.resident!=obs->after_resource.resident||
      obs->before_resource.locked!=obs->after_resource.locked)obs->kind=S_EVENT_RESOURCE;
  }
  break;}
 case S_CUTSCENE:
  if(!r||!i.subop)goto blocked; /* Exit requires camera/room semantics. */
  if(r->cutscene_active){r->blocked_reason=S_BLOCK_CUTSCENE_NESTED;goto blocked;}
  if(r->script_id==2){r->blocked_reason=S_BLOCK_SENTENCE_OWNER;goto blocked;}
  if(r->ui_revision==UINT64_MAX){i.fault=S_COUNTER_EXHAUSTED;goto fault;}
  if(obs&&(mask&SCUMM_OBS_SCENE))scumm_control_snapshot(s,r,&obs->before_control);
  r->saved_user_state=r->user_state|(r->user_put?0x10:0);
  r->saved_cursor=s->vars[21];r->saved_room=r->current_room;
  r->saved_camera_mode=r->camera_mode;r->cutscene_active=1;
  s->vars[21]=200;set_user_state(r,0x0f);
  r->sentence_count=0;
  /* Sentence script 2 is absent: this profile has only the bound current
   * script, and entry from script 2 was rejected before any mutation. */
  s->vars[26]=s->vars[38];s->vars[27]=s->vars[28]=s->vars[29]=0;
  r->override_pc=0;++r->ui_revision;
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->kind=S_EVENT_CONTROL;scumm_control_snapshot(s,r,&obs->after_control);
  }
  break;
 case S_CURSOR:
  if(!r)goto blocked;
  if(r->ui_revision==UINT64_MAX){i.fault=S_COUNTER_EXHAUSTED;goto fault;}
  if(obs&&(mask&SCUMM_OBS_SCENE))scumm_control_snapshot(s,r,&obs->before_control);
  if(a&255)s->vars[21]=a&255;
  set_user_state(r,a>>8);++r->ui_revision;
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->kind=S_EVENT_CONTROL;scumm_control_snapshot(s,r,&obs->after_control);
  }
  break;
 case S_VERB:{
  if(!r)goto blocked;
  unsigned slot=0;
  if(a==255){
   /* Mode lookup deliberately falls back to reserved slot zero, and ID
    * zero may match the first ordinary empty slot. Saved slots do not match. */
   for(unsigned k=1;k<SCUMM_VERBS;k++)
    if(r->verbs[k].id==b&&!r->verbs[k].saveid){slot=k;break;}
  }else{
   /* Resolve the full variable value before adding one; never narrow an
    * invalid selector to a byte or let UINT16_MAX wrap into slot zero. */
   if(b>=SCUMM_VERBS-1){i.fault=S_BAD_VERB;goto fault;}
   slot=(unsigned)b+1;
  }
  if(r->ui_revision==UINT64_MAX){i.fault=S_COUNTER_EXHAUSTED;goto fault;}
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->kind=S_EVENT_VERB;obs->verb_slot=slot;
   obs->before_verb=r->verbs[slot];obs->before_ui_revision=r->ui_revision;
  }
  ScummVerb *verb=&r->verbs[slot];
  if(!a){
   verb->id=0;verb->mode=0;verb->saveid=0;
   verb->name_pc=0;verb->name_size=0;
  }else if(a==255){
   verb->mode=(uint8_t)c;
  }else{
   static const uint8_t keys[]="qwertasdfgzxcvb";
   verb->id=a;
   verb->x=(uint16_t)code[i.payload_pc]*8;
   verb->y=(uint16_t)code[i.payload_pc+1]*8;
   verb->color=2;verb->hicolor=14;verb->dimcolor=8;
   verb->type=0;verb->charset=0;verb->mode=1;
   verb->saveid=0;verb->key=slot<sizeof(keys)?keys[slot-1]:0;
   verb->center=0;verb->imgindex=0;verb->prep=(uint8_t)c;
   verb->name_pc=i.payload_pc+4;verb->name_size=i.payload_size-5;
  }
  /* Every accepted verb operation invalidates the authored UI once, even
   * if its slot fields were already equal. No drawing or hover is implied. */
  ++r->ui_revision;
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->after_verb=*verb;obs->after_ui_revision=r->ui_revision;
  }
  break;}
 case S_START_SCRIPT:case S_STOP_SCRIPT:case S_CHAIN_SCRIPT:
 case S_LOAD_ROOM:case S_ACTOR_ROOM:
 case S_LIGHTS:case S_ANIMATE:case S_WALK:case S_PRINT:case S_OVERRIDE:
  goto blocked;
 case S_NOP:break;
 case S_PLACE:
  if(a==0||a>=SCUMM_ACTORS){i.fault=S_BAD_ACTOR;goto fault;}
  actor=a;
  if(obs&&(mask&SCUMM_OBS_SCENE))obs->before=s->actors[actor];
  s->actors[actor].x=b;s->actors[actor].y=c;s->actors[actor].bound=1;
  if(obs&&(mask&SCUMM_OBS_SCENE)){
   obs->actor=actor;obs->after=s->actors[actor];
   if(obs->before.x!=obs->after.x||obs->before.y!=obs->after.y||
      obs->before.bound!=obs->after.bound)obs->kind=S_EVENT_ACTOR;
  }
  break;
 case S_STOP:case S_YIELD:break;
 default:i.fault=S_OPCODE;goto fault;
 }
 if(!cond){
  if(i.target<0||(uint32_t)i.target>=len){i.fault=S_BAD_BRANCH;goto fault;}
  next=(uint32_t)i.target;
 }
 s->pc=next;++s->retired;s->status=i.op==S_STOP?S_RETURN:i.op==S_YIELD?S_WAIT:S_RUNNING;
 if(obs){
  obs->pc=i.pc;obs->next=next;obs->opcode=i.opcode;obs->size=i.size;
  obs->retired=s->retired;obs->insn=i;obs->branch_taken=!cond;
  obs->resolved[0]=a;obs->resolved[1]=b;obs->resolved[2]=c;
  if(obs->has_destination)obs->destination_after=s->vars[obs->destination];
 }
 return true;
blocked:
 if(r&&!r->blocked_reason)r->blocked_reason=S_BLOCK_UNIMPLEMENTED;
 s->status=S_BLOCKED;s->fault_opcode=i.opcode;return false;
badvar:i.fault=S_BAD_VAR;
fault:s->status=S_FAULT;s->fault=i.fault;s->fault_opcode=i.opcode;return false;
}
bool scumm_step_runtime(unsigned version,const uint8_t *code,size_t len,
                       ScummState *s,ScummTrace *t,ScummRuntime *runtime)
{
 ScummEvent capture;unsigned mask=t?t->mask&SCUMM_OBS_MASK:0;
 bool ok=scumm_execute_runtime(version,code,len,s,mask,mask?&capture:NULL,runtime);
 if(ok&&mask)scumm_observe(t,&capture,code);
 return ok;
}
bool scumm_step(unsigned version,const uint8_t *code,size_t len,
                ScummState *s,ScummTrace *t)
{
 return scumm_step_runtime(version,code,len,s,t,NULL);
}
