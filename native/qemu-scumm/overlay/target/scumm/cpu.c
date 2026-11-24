/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Lifecycle scaffold adapted from fDisBull native/qemu-agi. */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "exec/exec-all.h"
#include "exec/cputlb.h"
#include "exec/helper-proto.h"
#include "gdbstub/helpers.h"
#include "hw/core/sysemu-cpu-ops.h"
#include "accel/tcg/cpu-ops.h"
#include "system/runstate.h"
#include "system/tcg.h"
#include "cpu.h"
static bool stopped(Object *obj,Error **errp)
{
 if(!tcg_enabled()||runstate_is_running()||qemu_get_cpu(0)!=CPU(obj)||qemu_get_cpu(1)){
  error_setg(errp,"SCUMM_CONTROL: one stopped TCG CPU required");return false;}
 return true;
}
static void get_uint(Object *obj,Visitor *v,const char *name,void *opaque,Error **errp)
{
 ScummCPU *c=SCUMM_CPU(obj);unsigned f=(uintptr_t)opaque;uint64_t n;
 if(!stopped(obj,errp))return;
 n=f==0?c->env.mask:f==1?c->trace->capacity:f==2?c->env.budget:c->decode_pc;
 visit_type_uint64(v,name,&n,errp);
}
static void set_uint(Object *obj,Visitor *v,const char *name,void *opaque,Error **errp)
{
 ScummCPU *c=SCUMM_CPU(obj);unsigned f=(uintptr_t)opaque;uint64_t n;
 if(!visit_type_uint64(v,name,&n,errp)||!stopped(obj,errp))return;
 if((f==0&&n>3)||(f==1&&(n>SCUMM_EVENT_MAX||n<c->trace->count))||
    (f==2&&(!n||n>1000000000))||(f==3&&n>c->env.code_size)){
  error_setg(errp,"SCUMM_CONTROL: invalid %s",name);return;}
 if(f==0)c->trace->mask=c->env.mask=n;else if(f==1)c->trace->capacity=n;
 else if(f==2)c->env.budget=n;else c->decode_pc=n;
}
static void restart(ScummCPU *c)
{
 memset(&c->env.state,0,sizeof(c->env.state));c->env.run_retired=0;
 memset(c->trace->eligible,0,sizeof(c->trace->eligible));
 memset(c->trace->dropped,0,sizeof(c->trace->dropped));c->trace->count=0;c->trace->sequence=0;
}
static void set_restart(Object *obj,bool value,Error **errp)
{
 if(!stopped(obj,errp))return;
 if(!value){error_setg(errp,"restart requires true");return;}
 restart(SCUMM_CPU(obj));CPU(obj)->exception_index=-1;CPU(obj)->halted=0;
}
static char *get_state(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);ScummState *s=&c->env.state;GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-early-state-1\",\"version\":%u,"
  "\"sha256\":\"%s\",\"size\":%u,\"pc\":%u,\"status\":%u,\"fault\":%u,"
  "\"fault_opcode\":%u,\"retired\":%" PRIu64 ",\"run_retired\":%" PRIu64
  ",\"mask\":%u,\"eligible\":[%" PRIu64 ",%" PRIu64 "],\"dropped\":[%" PRIu64
  ",%" PRIu64 "],\"vars\":[",c->env.version,c->sha256,c->env.code_size,s->pc,
  s->status,s->fault,s->fault_opcode,s->retired,c->env.run_retired,c->env.mask,
  c->trace->eligible[0],c->trace->eligible[1],c->trace->dropped[0],c->trace->dropped[1]);
 for(unsigned k=0;k<256;k++)g_string_append_printf(j,"%s%u",k?",":"",s->vars[k]);
 g_string_append(j,"],\"actor_placement_model\":[");
 for(unsigned k=0;k<SCUMM_ACTORS;k++)g_string_append_printf(j,"%s[%u,%u,%u,%u]",k?",":"",k,
  s->actors[k].bound,s->actors[k].x,s->actors[k].y);
 g_string_append(j,"]}");return g_string_free(j,false);
}
static char *get_decode(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);uint32_t pc=c->decode_pc;GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-early-decode-1\",\"version\":%u,"
  "\"sha256\":\"%s\",\"records\":[",c->env.version,c->sha256);
 for(unsigned n=0;n<64&&pc<c->env.code_size;n++){
  ScummInsn i;bool ok=scumm_decode(c->env.version,c->code,c->env.code_size,pc,&i);
  g_string_append_printf(j,"%s{\"pc\":%u,\"opcode\":%u,\"op\":\"%s\",\"fault\":%u,"
   "\"size\":%u,\"next\":%u,\"branch\":%d,\"conditional\":%u,\"args\":[",
   n?",":"",i.pc,i.opcode,scumm_op_name(i.op),i.fault,i.size,i.next,i.target,i.conditional);
  for(unsigned k=0;k<i.count;k++)g_string_append_printf(j,"%s[%u,%u,%u]",k?",":"",
   i.arg[k].kind,i.arg[k].value,i.arg[k].width);
  g_string_append(j,"]}");if(!ok||!i.size)break;pc=i.next;
 }
 g_string_append(j,"]}");return g_string_free(j,false);
}
static char *get_events(Object *obj,Error **errp)
{
 if(!stopped(obj,errp))return NULL;
 ScummCPU *c=SCUMM_CPU(obj);GString *j=g_string_new(NULL);
 g_string_append_printf(j,"{\"schema\":\"fdisbull-scumm-early-events-1\",\"version\":%u,"
  "\"sha256\":\"%s\",\"records\":[",c->env.version,c->sha256);
 for(unsigned n=0;n<c->trace->count;n++){
  ScummEvent *e=&c->trace->events[n];
  g_string_append_printf(j,"%s{\"seq\":%" PRIu64 ",\"retired\":%" PRIu64
   ",\"channel\":%u,\"pc\":%u,\"next\":%u,\"opcode\":%u,\"bytes\":\"",
   n?",":"",e->seq,e->retired,e->channel,e->pc,e->next,e->opcode);
  for(unsigned k=0;k<e->size;k++)g_string_append_printf(j,"%02x",e->bytes[k]);
  g_string_append_printf(j,"\",\"actor\":%u,\"before\":[%u,%u,%u],\"after\":[%u,%u,%u]}",
   e->actor,e->before.bound,e->before.x,e->before.y,e->after.bound,e->after.x,e->after.y);
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
  if(!probe)helper_scumm_fetch_fault(cpu_env(cs));return false;}
 tlb_set_page(cs,addr&TARGET_PAGE_MASK,addr&TARGET_PAGE_MASK,PAGE_READ|PAGE_EXEC,idx,TARGET_PAGE_SIZE);
 return true;
}
static void enter(CPUState *cs)
{
 CPUArchState *e=cpu_env(cs);
 if(e->state.status==S_RETURN||e->state.status==S_FAULT){
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
 ScummCPUClass *cc=SCUMM_CPU_GET_CLASS(obj);
 if(cc->parent_phases.hold)cc->parent_phases.hold(obj,type);restart(SCUMM_CPU(obj));
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
 c->trace->capacity=SCUMM_EVENT_MAX;c->env.budget=100000;
 const char *n[]={"scumm-observation-mask","scumm-observation-capacity","scumm-step-budget","scumm-decode-pc"};
 for(unsigned k=0;k<4;k++)object_property_add(obj,n[k],"uint64",get_uint,set_uint,NULL,(void *)(uintptr_t)k);
 object_property_add_bool(obj,"scumm-restart",NULL,set_restart);
 object_property_add_str(obj,"scumm-state-json",get_state,NULL);
 object_property_add_str(obj,"scumm-decode-json",get_decode,NULL);
 object_property_add_str(obj,"scumm-events-json",get_events,NULL);
}
static void instance_finalize(Object *obj){g_free(SCUMM_CPU(obj)->trace);}
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
