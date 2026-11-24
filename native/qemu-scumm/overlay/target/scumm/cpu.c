/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Lifecycle scaffold adapted from fDisBull native/qemu-agi. */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qemu/error-report.h"
#include "exec/exec-all.h"
#include "exec/cputlb.h"
#include "exec/helper-proto.h"
#include "gdbstub/helpers.h"
#include "hw/core/sysemu-cpu-ops.h"
#include "accel/tcg/cpu-ops.h"
#include "system/runstate.h"
#include "system/tcg.h"
#include "cpu.h"
static const char *const resource_types[] = {"costume", "room", "script", "sound"};
static const char *const event_kinds[] = {
 "retire", "actor", "default_talk_color", "resource", "control", "verb"
};
static bool stopped(Object *obj,Error **errp)
{
 if(!tcg_enabled()||runstate_is_running()||qemu_get_cpu(0)!=CPU(obj)||qemu_get_cpu(1)){
  error_setg(errp,"SCUMM_CONTROL: one stopped TCG CPU required");return false;}
 return true;
}
static bool control_available(const ScummCPU *c,Error **errp)
{
 if(c->trace->control_generation==UINT64_MAX||c->trace->epoch==UINT64_MAX){
  error_setg(errp,"SCUMM_CONTROL: generation exhausted");return false;}
 return true;
}
static void get_uint(Object *obj,Visitor *v,const char *name,void *opaque,Error **errp)
{
 ScummCPU *c=SCUMM_CPU(obj);unsigned f=(uintptr_t)opaque;uint64_t n;
 if(!stopped(obj,errp))return;
 n=f==0?c->env.mask:f==1?c->trace->capacity:f==2?c->env.budget:
   f==3?c->decode_pc:c->decode_limit;
 visit_type_uint64(v,name,&n,errp);
}
static void set_uint(Object *obj,Visitor *v,const char *name,void *opaque,Error **errp)
{
 ScummCPU *c=SCUMM_CPU(obj);unsigned f=(uintptr_t)opaque;uint64_t n;
 if(!visit_type_uint64(v,name,&n,errp)||!stopped(obj,errp))return;
 if((f==0&&n>SCUMM_OBS_MASK)||(f==1&&(n>SCUMM_EVENT_MAX||n<c->trace->count))||
    (f==2&&(!n||n>1000000000))||(f==3&&n>c->env.code_size)||
    (f==4&&(!n||n>64))){
  error_setg(errp,"SCUMM_CONTROL: invalid %s",name);return;}
 if(f<3&&!control_available(c,errp))return;
 if(f==0)c->trace->mask=c->env.mask=n;else if(f==1)c->trace->capacity=n;
 else if(f==2)c->env.budget=n;else if(f==3)c->decode_pc=n;else c->decode_limit=n;
 if(f<3)c->trace->control_generation++;
 /* Decode selectors are host queries. The observation mask is a TB key. */
}
static void restart(ScummCPU *c)
{
 memset(&c->env.state,0,sizeof(c->env.state));c->env.run_retired=0;
 scumm_runtime_reset(&c->runtime);
 memset(&c->observation_pending,0,sizeof(c->observation_pending));
 scumm_trace_clear(c->trace);
 c->trace->control_generation++;
}
static void set_restart(Object *obj,bool value,Error **errp)
{
 if(!stopped(obj,errp))return;
 if(!value){error_setg(errp,"restart requires true");return;}
 if(!control_available(SCUMM_CPU(obj),errp))return;
 restart(SCUMM_CPU(obj));CPU(obj)->exception_index=-1;CPU(obj)->halted=0;
}
static void set_clear(Object *obj,bool value,Error **errp)
{
 ScummCPU *c=SCUMM_CPU(obj);
 if(!stopped(obj,errp))return;
 if(!value){error_setg(errp,"observation clear requires true");return;}
 if(!control_available(c,errp))return;
 scumm_trace_clear(c->trace);
 memset(&c->observation_pending,0,sizeof(c->observation_pending));
 c->trace->control_generation++;
}
static void json_bytes(GString *j,const uint8_t *bytes,size_t count)
{
 g_string_append_c(j,'"');
 for(size_t n=0;n<count;n++)g_string_append_printf(j,"%02x",bytes[n]);
 g_string_append_c(j,'"');
}
static void json_source(GString *j,const ScummCPU *c)
{
 g_string_append_printf(j,"{\"version\":%u,\"code_sha256\":\"%s\",\"code_size\":%u,"
  "\"profile\":\"%s\",\"manifest_sha256\":\"%s\","
  "\"source_receipt_sha256\":\"%s\",\"script_id\":%u}",
  c->env.version,c->sha256,c->env.code_size,
  c->runtime.enabled?"amiga-v2-isolated":"none",
  c->bank?c->bank->manifest_sha256:"",c->bank?c->bank->source_receipt_sha256:"",
  c->runtime.script_id);
}
static void json_observation(GString *j,const ScummTrace *t)
{
 g_string_append_printf(j,"{\"mask\":%u,\"capacity\":%u,\"count\":%u,"
  "\"sequence\":%" PRIu64 ",\"eligible\":[%" PRIu64 ",%" PRIu64 "],"
  "\"stored\":[%" PRIu64 ",%" PRIu64 "],\"dropped\":[%" PRIu64 ",%" PRIu64 "],"
  "\"helper_calls\":%" PRIu64 "}",t->mask,t->capacity,t->count,t->sequence,
  t->eligible[0],t->eligible[1],t->stored[0],t->stored[1],
  t->dropped[0],t->dropped[1],t->helper_calls);
}
static void json_actor(GString *j,const ScummCPU *c,const ScummActor *a,unsigned id)
{
 g_assert(a->name_pc<=c->env.code_size&&a->name_size<=c->env.code_size-a->name_pc);
 g_string_append_printf(j,"{\"id\":%u,\"bound\":%u,\"x\":%u,\"y\":%u,\"room\":%u,"
  "\"costume\":%u,\"sound\":%u,\"talk_color\":%u,\"name\":{\"pc\":%u,"
  "\"size\":%u,\"bytes\":",id,a->bound,a->x,a->y,a->room,a->costume,a->sound,
  a->talk_color,a->name_pc,a->name_size);
 json_bytes(j,c->code+a->name_pc,a->name_size);
 g_string_append(j,"},\"palette\":[");
 for(unsigned p=0;p<32;p++){
  if(p)g_string_append_c(j,',');
  if(a->palette_known[p])g_string_append_printf(j,"%u",a->palette[p]);
  else g_string_append(j,"null");
 }
 g_string_append(j,"]}");
}
static void json_verb(GString *j,const ScummCPU *c,const ScummVerb *v,unsigned slot)
{
 g_assert(slot<SCUMM_VERBS&&v->name_pc<=c->env.code_size&&
          v->name_size<=c->env.code_size-v->name_pc);
 g_string_append_printf(j,"{\"slot\":%u,\"id\":%u,\"x\":%u,\"y\":%u,"
  "\"color\":%u,\"hicolor\":%u,\"dimcolor\":%u,\"type\":%u,\"charset\":%u,"
  "\"mode\":%u,\"saveid\":%u,\"key\":%u,\"center\":%u,\"imgindex\":%u,\"prep\":%u,"
  "\"name\":{\"pc\":%u,\"size\":%u,\"bytes\":",slot,v->id,v->x,v->y,v->color,
  v->hicolor,v->dimcolor,v->type,v->charset,v->mode,v->saveid,v->key,v->center,
  v->imgindex,v->prep,v->name_pc,v->name_size);
 json_bytes(j,c->code+v->name_pc,v->name_size);
 g_string_append(j,"}}");
}
static void json_verbs(GString *j,const ScummCPU *c)
{
 g_string_append_c(j,'[');
 for(unsigned slot=0;slot<SCUMM_VERBS;slot++){
  if(slot)g_string_append_c(j,',');
  json_verb(j,c,&c->runtime.verbs[slot],slot);
 }
 g_string_append_c(j,']');
}
static void json_control(GString *j,const ScummControl *r,const ScummState *state)
{
 static const unsigned variable_ids[]={21,26,27,28,29,38};
 g_string_append_printf(j,"{\"user_state\":%u,\"user_put\":%u,\"cursor_visible\":%u,"
  "\"current_room\":%u,\"camera_mode\":%u,\"cutscene_active\":%u,"
  "\"saved_user_state\":%u,\"saved_cursor\":%u,\"saved_room\":%u,"
  "\"saved_camera_mode\":%u,\"override_pc\":%u,\"override_script\":%u,"
  "\"sentence_count\":%u,\"ui_revision\":%" PRIu64,
  r->user_state,r->user_put,r->cursor_visible,r->current_room,r->camera_mode,
  r->cutscene_active,r->saved_user_state,r->saved_cursor,r->saved_room,
  r->saved_camera_mode,r->override_pc,r->override_script,r->sentence_count,r->ui_revision);
 if(state)g_string_append_printf(j,",\"default_talk_color\":%u",state->default_talk_color);
 g_string_append(j,",\"vars\":{");
 for(unsigned n=0;n<G_N_ELEMENTS(variable_ids);n++)
  g_string_append_printf(j,"%s\"%u\":%u",n?",":"",variable_ids[n],r->vars[n]);
 g_string_append(j,"}}");
}
static void json_resource_fields(GString *j,const ScummResource *r,const char *sha256)
{
 g_string_append_printf(j,"\"size\":%u,\"available\":%s,\"resident\":%s,"
  "\"locked\":%s,\"sha256\":\"%s\"",r->size,r->available?"true":"false",
  r->resident?"true":"false",r->locked?"true":"false",sha256);
}
static void json_resources(GString *j,const ScummCPU *c)
{
 const ScummRuntime *r=&c->runtime;bool comma=false;
 g_string_append(j,"{\"counts\":{");
 for(unsigned type=0;type<SCUMM_RESOURCE_TYPES;type++)
  g_string_append_printf(j,"%s\"%s\":%u",type?",":"",resource_types[type],r->counts[type]);
 g_string_append(j,"},\"entries\":[");
 for(unsigned type=0;type<SCUMM_RESOURCE_TYPES;type++)
  for(unsigned id=0;id<r->counts[type];id++){
   const ScummResource *e=&r->resources[type][id];
   if(!e->available&&!e->resident&&!e->locked)continue;
   g_string_append_printf(j,"%s{\"type\":\"%s\",\"id\":%u,",comma?",":"",resource_types[type],id);
   json_resource_fields(j,e,c->bank?c->bank->sha256[type][id]:"");
   g_string_append_c(j,'}');comma=true;
  }
 g_string_append(j,"]}");
}
static char *get_state(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);ScummState *s=&c->env.state;GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-early-state-1\",\"version\":%u,"
  "\"sha256\":\"%s\",\"size\":%u,\"pc\":%u,\"status\":%u,\"fault\":%u,"
  "\"fault_opcode\":%u,\"retired\":%" PRIu64 ",\"run_retired\":%" PRIu64
  ",\"mask\":%u,\"epoch\":%" PRIu64 ",\"control_generation\":%" PRIu64
  ",\"count\":%u,\"capacity\":%u,\"sequence\":%" PRIu64
  ",\"stored\":[%" PRIu64 ",%" PRIu64 "],\"helper_calls\":%" PRIu64
  ",\"eligible\":[%" PRIu64 ",%" PRIu64 "],\"dropped\":[%" PRIu64
  ",%" PRIu64 "],\"vars\":[",c->env.version,c->sha256,c->env.code_size,s->pc,
  s->status,s->fault,s->fault_opcode,s->retired,c->env.run_retired,c->env.mask,
  c->trace->epoch,c->trace->control_generation,c->trace->count,c->trace->capacity,
  c->trace->sequence,c->trace->stored[0],c->trace->stored[1],c->trace->helper_calls,
  c->trace->eligible[0],c->trace->eligible[1],c->trace->dropped[0],c->trace->dropped[1]);
 for(unsigned k=0;k<256;k++)g_string_append_printf(j,"%s%u",k?",":"",s->vars[k]);
 g_string_append(j,"],\"actor_placement_model\":[");
 for(unsigned k=0;k<SCUMM_ACTORS;k++)g_string_append_printf(j,"%s[%u,%u,%u,%u]",k?",":"",k,
  s->actors[k].bound,s->actors[k].x,s->actors[k].y);
 g_string_append_printf(j,"],\"default_talk_color\":%u,\"actor_metadata\":[",s->default_talk_color);
 for(unsigned k=0;k<SCUMM_ACTORS;k++){
  ScummActor *a=&s->actors[k];
  g_string_append_printf(j,"%s{\"actor\":%u,\"room\":%u,\"costume\":%u,\"sound\":%u,\"talk_color\":%u,\"name_pc\":%u,\"name_size\":%u,\"palette\":[",k?",":"",k,a->room,a->costume,a->sound,a->talk_color,a->name_pc,a->name_size);
  for(unsigned p=0;p<32;p++) {
   if(a->palette_known[p])g_string_append_printf(j,"%s%u",p?",":"",a->palette[p]);
   else g_string_append(j,p?",null":"null");
  }
  g_string_append(j,"]}");
 }
 g_string_append(j,"]}");return g_string_free(j,false);
}
static char *get_scene(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);ScummState *s=&c->env.state;ScummControl control;
 GString *j=g_string_new("{\"schema\":\"fdisbull-scumm-scene-1\",\"source\":");
 json_source(j,c);
 g_string_append_printf(j,",\"checkpoint\":{\"trace_epoch\":%" PRIu64
  ",\"control_generation\":%" PRIu64 ",\"retired\":%" PRIu64
  ",\"pc\":%u,\"status\":%u,\"fault\":%u,\"fault_opcode\":%u,\"blocked_reason\":\"%s\"},"
  "\"observation\":",c->trace->epoch,c->trace->control_generation,s->retired,s->pc,
  s->status,s->fault,s->fault_opcode,scumm_block_reason(c->runtime.blocked_reason));
 json_observation(j,c->trace);
 g_string_append(j,",\"actors\":[");
 for(unsigned id=0;id<SCUMM_ACTORS;id++){
  if(id)g_string_append_c(j,',');
  json_actor(j,c,&s->actors[id],id);
 }
 g_string_append(j,"],\"resources\":");json_resources(j,c);
 g_string_append(j,",\"verbs\":");json_verbs(j,c);
 scumm_control_snapshot(s,&c->runtime,&control);
 g_string_append(j,",\"control\":");json_control(j,&control,s);
 g_string_append_c(j,'}');return g_string_free(j,false);
}
static char *get_runtime(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);ScummRuntime *r=&c->runtime;
 const char *types[]={"costume","room","script","sound"};
 GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-v2-runtime-1\","
  "\"enabled\":%s,\"profile\":\"%s\",\"code_sha256\":\"%s\","
  "\"manifest_sha256\":\"%s\",\"source_receipt_sha256\":\"%s\","
  "\"script_id\":%u,\"blocked_reason\":\"%s\",\"counts\":{",
  r->enabled?"true":"false",r->enabled?"amiga-v2-isolated":"none",c->sha256,
  c->bank?c->bank->manifest_sha256:"",c->bank?c->bank->source_receipt_sha256:"",
  r->script_id,scumm_block_reason(r->blocked_reason));
 for(unsigned type=0;type<SCUMM_RESOURCE_TYPES;type++)
  g_string_append_printf(j,"%s\"%s\":%u",type?",":"",types[type],r->counts[type]);
 g_string_append_printf(j,"},\"control\":{\"user_state\":%u,\"user_put\":%u,"
  "\"cursor_visible\":%u,\"current_room\":%u,\"camera_mode\":%u,"
  "\"cutscene_active\":%u,\"saved_user_state\":%u,\"saved_cursor\":%u,"
  "\"saved_room\":%u,\"saved_camera_mode\":%u,\"override_pc\":%u,"
  "\"override_script\":%u,\"sentence_count\":%u,\"ui_revision\":%" PRIu64 "},\"resources\":[",
  r->user_state,r->user_put,r->cursor_visible,r->current_room,r->camera_mode,
  r->cutscene_active,r->saved_user_state,r->saved_cursor,r->saved_room,
  r->saved_camera_mode,r->override_pc,r->override_script,r->sentence_count,r->ui_revision);
 bool comma=false;
 for(unsigned type=0;type<SCUMM_RESOURCE_TYPES;type++)
  for(unsigned id=0;id<r->counts[type];id++){
   ScummResource *e=&r->resources[type][id];
   if(!e->available&&!e->resident&&!e->locked)continue;
   g_string_append_printf(j,"%s{\"type\":\"%s\",\"id\":%u,\"size\":%u,"
    "\"available\":%s,\"resident\":%s,\"locked\":%s,\"sha256\":\"%s\"}",
    comma?",":"",types[type],id,e->size,e->available?"true":"false",
    e->resident?"true":"false",e->locked?"true":"false",c->bank?c->bank->sha256[type][id]:"");
   comma=true;
  }
 g_string_append(j,"],\"verbs\":");json_verbs(j,c);
 g_string_append_c(j,'}');return g_string_free(j,false);
}
static void json_args(GString *j,const ScummInsn *i)
{
 g_string_append_c(j,'[');
 for(unsigned k=0;k<i->count;k++)g_string_append_printf(j,"%s[%u,%u,%u]",k?",":"",
  i->arg[k].kind,i->arg[k].value,i->arg[k].width);
 g_string_append_c(j,']');
}
static void json_decoded(GString *j,const ScummInsn *i)
{
 g_string_append_printf(j,"{\"op\":\"%s\",\"next\":%u,\"branch\":%d,\"conditional\":%u,"
  "\"subop\":%u,\"payload_pc\":%u,\"payload_size\":%u,\"args\":",
  scumm_op_name(i->op),i->next,i->target,i->conditional,i->subop,i->payload_pc,i->payload_size);
 json_args(j,i);g_string_append_c(j,'}');
}
static char *get_decode(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);uint32_t pc=c->decode_pc;
 const char *stop="end";GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-early-decode-1\",\"version\":%u,"
  "\"sha256\":\"%s\",\"source\":",c->env.version,c->sha256);
 json_source(j,c);
 g_string_append_printf(j,",\"start_pc\":%u,\"limit\":%u,\"records\":[",pc,c->decode_limit);
 for(unsigned n=0;n<c->decode_limit&&pc<c->env.code_size;n++){
  ScummInsn i;bool ok=scumm_decode(c->env.version,c->code,c->env.code_size,pc,&i);
  g_string_append_printf(j,"%s{\"pc\":%u,\"opcode\":%u,\"op\":\"%s\",\"fault\":%u,"
   "\"size\":%u,\"next\":%u,\"branch\":%d,\"conditional\":%u,\"subop\":%u,\"payload_pc\":%u,\"payload_size\":%u,\"args\":",
   n?",":"",i.pc,i.opcode,scumm_op_name(i.op),i.fault,i.size,i.next,i.target,i.conditional,i.subop,i.payload_pc,i.payload_size);
  json_args(j,&i);
  if(ok&&i.size){
   g_string_append(j,",\"bytes\":");json_bytes(j,c->code+i.pc,i.size);
  }
  g_string_append_c(j,'}');
  /* Retain the legacy fault row, but never advance it as a successful extent. */
  if(!ok||!i.size){stop="decode_fault";break;}
  pc=i.next;
  stop=pc==c->env.code_size?"end":"limit";
 }
 g_string_append_printf(j,"],\"next_pc\":%u,\"stop\":\"%s\"}",pc,stop);
 return g_string_free(j,false);
}
static char *get_events(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-events-2\",\"version\":%u,"
  "\"sha256\":\"%s\",\"source\":",c->env.version,c->sha256);
 json_source(j,c);
 g_string_append_printf(j,",\"epoch\":%" PRIu64 ",\"control_generation\":%" PRIu64
  ",\"observation\":",c->trace->epoch,c->trace->control_generation);
 json_observation(j,c->trace);g_string_append(j,",\"records\":[");
 for(unsigned n=0;n<c->trace->count;n++){
  const ScummEvent *e=&c->trace->events[n];
  g_assert(e->kind<G_N_ELEMENTS(event_kinds)&&e->size<=SCUMM_INSN_MAX);
  g_string_append_printf(j,"%s{\"seq\":%" PRIu64 ",\"retired\":%" PRIu64
   ",\"control_generation\":%" PRIu64 ",\"channel\":%u,\"kind\":\"%s\","
   "\"pc\":%u,\"next\":%u,\"opcode\":%u,\"size\":%u,\"bytes\":",
   n?",":"",e->seq,e->retired,e->control_generation,e->channel,event_kinds[e->kind],
   e->pc,e->next,e->opcode,e->size);
  json_bytes(j,e->bytes,e->size);
  g_string_append(j,",\"decoded\":");json_decoded(j,&e->insn);
  g_string_append(j,",\"resolved\":[");
  for(unsigned k=0;k<e->insn.count;k++)g_string_append_printf(j,"%s%u",k?",":"",e->resolved[k]);
  g_string_append(j,"],\"destination\":");
  if(e->has_destination)g_string_append_printf(j,"{\"index\":%u,\"before\":%u,\"after\":%u}",
   e->destination,e->destination_before,e->destination_after);
  else g_string_append(j,"null");
  g_string_append(j,",\"branch_taken\":");
  if(e->insn.op==S_JUMP||e->insn.conditional)g_string_append(j,e->branch_taken?"true":"false");
  else g_string_append(j,"null");
  /* Preserve the early-pilot placement/metadata arrays for existing readers. */
  g_string_append_printf(j,",\"actor\":%u,\"before\":[%u,%u,%u],\"after\":[%u,%u,%u],"
   "\"before_metadata\":[%u,%u,%u,%u,%u],\"after_metadata\":[%u,%u,%u,%u,%u]",
   e->actor,e->before.bound,e->before.x,e->before.y,e->after.bound,e->after.x,e->after.y,
   e->before.costume,e->before.sound,e->before.talk_color,e->before.name_pc,e->before.name_size,
   e->after.costume,e->after.sound,e->after.talk_color,e->after.name_pc,e->after.name_size);
  switch(e->kind){
  case S_EVENT_ACTOR:
   g_string_append(j,",\"before_actor\":");json_actor(j,c,&e->before,e->actor);
   g_string_append(j,",\"after_actor\":");json_actor(j,c,&e->after,e->actor);break;
  case S_EVENT_DEFAULT_COLOR:
   g_string_append_printf(j,",\"before_color\":%u,\"after_color\":%u",e->before_color,e->after_color);break;
  case S_EVENT_RESOURCE:{
   g_assert(e->resource_type<SCUMM_RESOURCE_TYPES&&e->resource_id<SCUMM_RESOURCE_SLOTS);
   const char *sha256=c->bank?c->bank->sha256[e->resource_type][e->resource_id]:"";
   g_string_append_printf(j,",\"type\":\"%s\",\"id\":%u,\"before_resource\":{",
    resource_types[e->resource_type],e->resource_id);
   json_resource_fields(j,&e->before_resource,sha256);
   g_string_append(j,"},\"after_resource\":{");json_resource_fields(j,&e->after_resource,sha256);
   g_string_append_c(j,'}');break;
  }
  case S_EVENT_CONTROL:
   g_string_append(j,",\"before_control\":");json_control(j,&e->before_control,NULL);
   g_string_append(j,",\"after_control\":");json_control(j,&e->after_control,NULL);break;
  case S_EVENT_VERB:
   g_string_append(j,",\"before_verb\":");json_verb(j,c,&e->before_verb,e->verb_slot);
   g_string_append(j,",\"after_verb\":");json_verb(j,c,&e->after_verb,e->verb_slot);
   g_string_append_printf(j,",\"before_ui_revision\":%" PRIu64
    ",\"after_ui_revision\":%" PRIu64,e->before_ui_revision,e->after_ui_revision);break;
  default:break;
  }
  g_string_append_c(j,'}');
 }
 g_string_append(j,"]}");return g_string_free(j,false);
}
static vaddr get_pc(CPUState *cs){return cpu_env(cs)->state.pc;}
static void set_pc(CPUState *cs,vaddr pc){cpu_env(cs)->state.pc=pc;}
static void sync_tb(CPUState *cs,const TranslationBlock *tb){set_pc(cs,tb->pc);}
static void restore(CPUState *cs,const TranslationBlock *tb,const uint64_t *d){set_pc(cs,d[0]);}
static int mmu_index(CPUState *cs,bool ifetch){return MMU_USER_IDX;}
static bool has_work(CPUState *cs){return false;}
static bool interrupt(CPUState *cs,int request){return false;}
static hwaddr phys_debug(CPUState *cs,vaddr addr){return addr<SCUMM_CODE_MAX?addr:(hwaddr)-1;}
static bool tlb_fill(CPUState *cs,vaddr addr,int size,MMUAccessType access,int idx,bool probe,uintptr_t retaddr)
{
 if(addr>=SCUMM_CODE_MAX||size<1||(vaddr)size>SCUMM_CODE_MAX-addr||access==MMU_DATA_STORE){
  if(!probe){helper_scumm_fetch_fault(cpu_env(cs));}
  return false;}
 tlb_set_page(cs,addr&TARGET_PAGE_MASK,addr&TARGET_PAGE_MASK,PAGE_READ|PAGE_EXEC,idx,TARGET_PAGE_SIZE);
 return true;
}
static void enter(CPUState *cs)
{
 CPUArchState *e=cpu_env(cs);
 if(e->state.status==S_RETURN||e->state.status==S_FAULT||e->state.status==S_BLOCKED){
  e->run_retired=0;
  vm_stop(RUN_STATE_PAUSED);cs->exception_index=EXCP_INTERRUPT;return;}
 if(e->state.status!=S_RUNNING){e->run_retired=0;e->state.status=S_RUNNING;}
}
static void leave(CPUState *cs)
{
 if(cpu_env(cs)->state.status==S_RUNNING&&(cs->stop||!runstate_is_running()))
  cpu_env(cs)->state.status=S_READY;
}
static int gdb_read(CPUState *cs,GByteArray *buf,int reg){return reg==0?gdb_get_reg32(buf,get_pc(cs)):0;}
static int gdb_write(CPUState *cs,uint8_t *buf,int reg){return 0;}
static const char *gdb_arch(CPUState *cs){return "scumm";}
static void reset_hold(Object *obj,ResetType type)
{
 ScummCPU *c=SCUMM_CPU(obj);
 ScummCPUClass *cc=SCUMM_CPU_GET_CLASS(obj);
 /* Reset has no Error ** channel; reject before parent or guest mutation. */
 if(c->trace->control_generation==UINT64_MAX||c->trace->epoch==UINT64_MAX){
  error_report("SCUMM_CONTROL: reset rejected: generation exhausted");return;}
 if(cc->parent_phases.hold){cc->parent_phases.hold(obj,type);}
 restart(c);
}
static void realize(DeviceState *dev,Error **errp)
{
 CPUState *cs=CPU(dev);ScummCPUClass *cc=SCUMM_CPU_GET_CLASS(dev);
 Error *err=NULL;cpu_exec_realizefn(cs,&err);
 if(err){error_propagate(errp,err);return;}
 qemu_init_vcpu(cs);cpu_reset(cs);cc->parent_realize(dev,errp);
}
static void instance_init(Object *obj)
{
 ScummCPU *c=SCUMM_CPU(obj);c->trace=g_new0(ScummTrace,1);
 c->trace->capacity=SCUMM_EVENT_MAX;c->env.budget=100000;c->decode_limit=64;
 const char *n[]={"scumm-observation-mask","scumm-observation-capacity","scumm-step-budget","scumm-decode-pc","scumm-decode-limit"};
 for(unsigned k=0;k<G_N_ELEMENTS(n);k++)object_property_add(obj,n[k],"uint64",get_uint,set_uint,NULL,(void *)(uintptr_t)k);
 object_property_add_bool(obj,"scumm-restart",NULL,set_restart);
 object_property_add_bool(obj,"scumm-observation-clear",NULL,set_clear);
 object_property_add_str(obj,"scumm-state-json",get_state,NULL);
 object_property_add_str(obj,"scumm-scene-json",get_scene,NULL);
 object_property_add_str(obj,"scumm-decode-json",get_decode,NULL);
 object_property_add_str(obj,"scumm-events-json",get_events,NULL);
 object_property_add_str(obj,"scumm-runtime-json",get_runtime,NULL);
}
static void instance_finalize(Object *obj)
{ScummCPU *c=SCUMM_CPU(obj);g_free(c->trace);scumm_resource_bank_free(c->bank);}
static const struct SysemuCPUOps sysemu_ops={.has_work=has_work,.get_phys_page_debug=phys_debug};
static const TCGCPUOps tcg_ops={.initialize=scumm_tcg_init,.translate_code=scumm_cpu_translate_code,
 .synchronize_from_tb=sync_tb,.restore_state_to_opc=restore,.cpu_exec_enter=enter,.cpu_exec_exit=leave,
 .cpu_exec_halt=has_work,.cpu_exec_interrupt=interrupt,.tlb_fill=tlb_fill};
static void class_init(ObjectClass *oc,void *data)
{
 DeviceClass *dc=DEVICE_CLASS(oc);CPUClass *cc=CPU_CLASS(oc);ScummCPUClass *sc=SCUMM_CPU_CLASS(oc);
 device_class_set_parent_realize(dc,realize,&sc->parent_realize);
 resettable_class_set_parent_phases(RESETTABLE_CLASS(oc),NULL,reset_hold,NULL,&sc->parent_phases);
 cc->mmu_index=mmu_index;cc->get_pc=get_pc;cc->set_pc=set_pc;
 cc->gdb_read_register=gdb_read;cc->gdb_write_register=gdb_write;
 cc->gdb_core_xml_file="scumm-core.xml";cc->gdb_arch_name=gdb_arch;
 cc->tcg_ops=&tcg_ops;cc->sysemu_ops=&sysemu_ops;
}
static const TypeInfo cpu_type={.name=TYPE_SCUMM_CPU,.parent=TYPE_CPU,.instance_size=sizeof(ScummCPU),
 .instance_init=instance_init,.instance_finalize=instance_finalize,
 .class_size=sizeof(ScummCPUClass),.class_init=class_init};
static void register_types(void){type_register_static(&cpu_type);}
type_init(register_types)
